"""The tool's web door: `GET /auth/oidc/login` and `/auth/oidc/callback` — ticket E0-18.

SPEC §2 gives every role except instructor and student a second way in, and E0-16
built the provider it goes through. E0-18 PR 1 builds the tool's half: an
authorization code flow with PKCE, started at `/auth/oidc/login` and finished at
`/auth/oidc/callback`, landing the caller on the empty view their **verified**
roles claim names. Everything below is asserted over HTTP against the application
`app.main:create_app()` returns, with the mock provider served in process through
`app.state.http`.

**The flow is driven the way a browser drives it.** The tool's redirect is read,
its parameters are carried to the provider's own authorization endpoint, an
identity is chosen at the login form, and the `code` and `state` the provider
sends back are delivered to the tool's callback — which then redeems that code
**server-side**, through the seam, with the PKCE verifier only it holds. Nothing
is short-circuited, so the exchange below is the exchange a deployment performs.

**What is deliberately not here.** E0-18's boundary section gives E1 the unified
session, provisioning, the dual-door identity merge and role resolution from the
assignment model. So no test below asserts anything about a `user` row, a session
that outlives the flow, or a purview — `transitive_purview` raises by design (ADR
0003) and the leadership landing view is empty *because* of it. The wrong-door
person — an instructor trying to sign in here — is E0-16's own test and is not
re-proved.

**Four things arrived in the third review round**, and they are the last two
sections of this module. This door reads one roles claim and ignores the LTI one,
which needs sessions carrying claims no seeded person produces — so those are
re-signed by `suite_key_set` inside the same token-endpoint seam, with a control
test saying the machinery itself is accepted. The login cookie carries `Secure`
outside development and does not carry it inside. A `state` that is not ASCII is
refused rather than crashed, and the refusal still burns the single-use cookie.
And no refusal page repeats the server-side key set address the tool failed to
reach.

**Two of the three refusals cannot be posed on the wire**, and the seam is how they
are posed instead: the provider signs with a key nothing here holds, so a token
that is tampered with, or one that expired an hour ago, is produced by wrapping the
tool's own call to the token endpoint rather than by editing a string. Both leave
every other property of the flow intact, which is what keeps a 4xx meaning the one
thing the test names (`docs/MISTAKES.md` entry 3).
"""

from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

# The mock provider's configuration surface, from `mock-idp/app/config.py`. Only
# the redirect URI is set: it is compared exactly, both when the authorization
# request arrives and again when the code is redeemed, so the tool's
# `PUBLIC_BASE_URL` and this value have to be the same address or no flow
# completes at all.
MOCK_IDP_TOOL_REDIRECT_URI_VARIABLE = "MOCK_IDP_TOOL_REDIRECT_URI"

# Where the tool is configured to send a browser to begin a web login. Chosen so
# that no implementation could arrive at it by accident — a redirect built from the
# issuer plus a guessed path, or from the discovery document at request time, would
# agree with the real provider and disagree with this. E0-18 makes the
# browser-facing authorize URL a setting of its own precisely because it is not the
# server-facing one. `.invalid` is reserved by RFC 2606.
CONFIGURED_AUTHORIZATION_ENDPOINT = "http://identity-provider.invalid/e0-18-configured-authorize"

# An issuer the tool is told to expect from a provider that will state a different
# one. Used for the `iss` refusal, and for nothing else.
UNTRUSTED_ISSUER = "http://an-issuer-this-tool-does-not-trust.invalid"

# A client the provider registers nobody under. The tool is configured as this
# client for the `aud` refusal, so the correctly signed token it receives is
# addressed to somebody else. Used there and nowhere else.
UNREGISTERED_CLIENT_ID = "a-client-this-provider-issues-no-token-to"

# The roles §2 gives the web door, and the view E0-18 lands each on: "leadership
# roles → leadership empty view, `CARE` → Care empty view, `ADMIN` → admin empty
# view". The leadership set is §2's reporting chain; Care and Admin are the two
# roles §2 gives this door and no other.
LEADERSHIP_ROLES = ("VP_ACADEMICS", "DEAN", "ASSISTANT_DEAN", "CHAIR", "LEAD_FACULTY")
LEADERSHIP_VIEW = "pulse-landing-leadership"
CARE_VIEW = "pulse-landing-care"
ADMIN_VIEW = "pulse-landing-admin"

# The launch-door view the two-hat person reaches by her other assignment.
INSTRUCTOR_VIEW = "pulse-landing-instructor"

# The mock platform's configuration surface again, for the one test that drives
# both doors. Kept here rather than imported from the launch module: a test module
# importing its sibling depends on where pytest put `tests/` on `sys.path`, and an
# import error is not a red.
MOCK_LMS_TOOL_LOGIN_URL_VARIABLE = "MOCK_LMS_TOOL_LOGIN_URL"
MOCK_LMS_TOOL_LAUNCH_URL_VARIABLE = "MOCK_LMS_TOOL_LAUNCH_URL"

# The LTI 1.3 roles claim, spelled as the specification spells it.
LTI_ROLES_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/roles"

# The LIS v2 membership role the *launch* door dispatches an instructor on. It
# appears here only as a value to smuggle into a web session: it is what an
# identity provider — or anyone who can put a token in front of this door — would
# state if the web door read the launch door's vocabulary.
MEMBERSHIP_ROLE = "http://purl.imsglobal.org/vocab/lis/v2/membership#"
INSTRUCTOR_ROLE_URI = f"{MEMBERSHIP_ROLE}Instructor"

# `ENVIRONMENT`, spelled as `tests/unit/test_docs_exposure.py` spells it, and the
# two values that matter: the one a laptop carries and the one a deployment does.
ENVIRONMENT_VARIABLE = "ENVIRONMENT"
DEVELOPMENT = "development"
PRODUCTION = "production"

# The cookie attribute that keeps a browser from sending the login cookie over
# plain HTTP (RFC 6265 §4.1.2.5), lowercased at the comparison because a
# `Set-Cookie` attribute name is case-insensitive.
SECURE_ATTRIBUTE = "secure"

# A `state` that is well formed as a query parameter and not representable as
# ASCII. `secrets.compare_digest` raises `TypeError` rather than answering `False`
# when either side is a `str` outside ASCII, so this is the value that separates
# "the tool compared and refused" from "the tool crashed on the way to comparing".
NON_ASCII_STATE = "é"

# How far back the provider's clock is wound while the tool redeems its code, to
# obtain a session that is certainly expired and one that certainly is not. The
# pair is the point: without the second, the refusal would be evidence that winding
# the clock breaks a flow rather than evidence that the tool checks `exp`.
CERTAINLY_EXPIRED_SECONDS = 3600
CERTAINLY_STILL_VALID_SECONDS = 30

# What RFC 7636 requires of a public client, and what E0-16's provider refuses
# anything else for.
REQUIRED_CHALLENGE_METHOD = "S256"

# The capability table. E0-09 criterion 10: "No LTI claim, no OIDC claim, and no
# LMS role may ever produce a `CARE` assignment." A row here is what *holding* a
# role is in this system — E0-11 resolves every actor's roles out of it and
# nowhere else — so this is the table the claim must not reach.
ASSIGNMENT_TABLE = "role_assignment"

# The two tables a door would write if it provisioned the person it just
# authenticated. E0-18's boundary section gives provisioning to E1 ("E0 does not
# build… any `user` row for a mock subject"), so today the honest count is
# unchanged; when E1 builds it, this half of the assertion moves in E1's own pull
# request, deliberately and with the reason written down.
PROVISIONING_TABLES = ("user", "person")

# A table the migration itself fills, used as the control on the counter below.
# Without it "nothing was written" and "this connection is reading an empty
# database, or a different one" are the same observation (`docs/MISTAKES.md`
# entry 3).
STAMPED_TABLE = "alembic_version"


def committed_row_count(engine: Any, table: str) -> int:
    """How many rows `table` holds right now, read on a connection of its own.

    A connection per call on purpose. The tool opens its own connection out of
    `DATABASE_URL` and commits on it, and a reader that held one transaction open
    across the whole flow would answer out of the snapshot it started with — so it
    would report "unchanged" whatever the door did, which is the shape of a test
    that passes for a reason unrelated to what it asserts.
    """
    query = text(f'SELECT count(*) FROM public."{table}"')  # noqa: S608
    with engine.connect() as connection:
        return int(connection.execute(query).scalar_one())


def redirect_target(response: Any, purpose: str) -> str:
    """The `Location` of a redirect, or a failure saying what came back instead."""
    assert response.status_code in (302, 303, 307), (
        f"The tool answered {response.status_code} rather than a redirect when {purpose}. Body "
        f"begins {response.text[:300]!r}. E0-18: '`GET /auth/oidc/login` — starts the code flow "
        "against the mock IdP: 302 to its authorization endpoint'."
    )
    location = response.headers.get("location")
    assert (
        location
    ), f"The tool answered {response.status_code} with no `Location` header when {purpose}."
    return location


def query_of(url: str) -> dict[str, str]:
    """The query parameters of a URL, as a mapping."""
    return dict(parse_qsl(urlsplit(url).query))


def views_in(response: Any, contract: Any) -> list[str]:
    """Which of the five landing testids the body carries."""
    return [testid for testid in contract.landing_testids if testid in response.text]


def lands_on(response: Any, contract: Any, expected: str) -> None:
    """The response is the landing page for `expected`, and for nothing else."""
    assert response.status_code == 200, (
        f"The web login was answered {response.status_code} rather than 200. Body begins "
        f"{response.text[:400]!r}."
    )
    found = views_in(response, contract)
    assert found == [expected], (
        f"The landing page carries {found or 'no landing testid at all'}, and E0-18 has this "
        f"session land on `{expected}`. Every other view's testid has to be absent as well as "
        "this one present: a page carrying several is right about none of them."
    )


def refused(response: Any, contract: Any, what: str) -> None:
    """The tool refused, and rendered nobody's landing page while doing it."""
    assert 400 <= response.status_code < 500, (
        f"The tool answered {response.status_code} to {what}. E0-18 requires a 4xx: this is auth "
        f"code, and the callback is where a token from an unauthenticated caller first reaches "
        f"real tool code. Body begins {response.text[:400]!r}."
    )
    found = views_in(response, contract)
    assert not found, (
        f"The tool refused {what} with {response.status_code} and still rendered {found}. A "
        "refusal that serves a landing page has admitted the session and merely said so in the "
        "status line."
    )


def person_holding(provider: Any, role: str, *, and_a_launch_assignment: bool = False) -> Any:
    """The one seeded person the registration document publishes with `role`.

    Read off `/mock/registration` (ADR 0058) rather than transcribed, so this module
    holds no copy of `mock-idp/app/seed.py` and a reseeding cannot leave it quietly
    asserting over somebody who is no longer there.

    `and_a_launch_assignment` distinguishes the two people who hold Care: the
    office, and the person who also teaches. Without it, "the Care person" is
    whichever of the two the document happens to list first.
    """
    found = [
        user
        for user in provider.published_users()
        if role in (user.get("roles") or [])
        and bool(user.get("launch_only_roles")) == and_a_launch_assignment
    ]
    assert len(found) == 1, (
        f"The registration document publishes {len(found)} people holding {role!r} with "
        f"launch_only_roles {'set' if and_a_launch_assignment else 'empty'}; this test names one. "
        f"It publishes {[user.get('subject') for user in provider.published_users()]}."
    )
    return found[0]


def identifying_strings(provider: Any, except_for: Any) -> list[str]:
    """Every seeded person's address and subject, apart from one person's own.

    The signed-in person's own identifiers are excluded deliberately. A landing
    page naming who is signed in is legitimate; a landing page naming *anybody
    else* has enumerated people, and E0-18 says the leadership and Care views are
    empty by design because nothing here computes a purview to populate them
    (ADR 0003, §2.1).
    """
    mine = {value for value in except_for.values() if isinstance(value, str) and value}
    found: list[str] = []
    for user in provider.published_users():
        for member in ("email", "subject"):
            value = user.get(member)
            if isinstance(value, str) and value and value not in mine:
                found.append(value)
    return found


@pytest.fixture
def provider(mock_idps: Any, door_contract: Any) -> Any:
    """The mock provider, registered to return to this tool's own callback.

    `MOCK_IDP_TOOL_REDIRECT_URI` is compared exactly — on the way in and again at
    the token endpoint — so this is what makes "the tool builds its redirect URI
    from `PUBLIC_BASE_URL`" a property the provider itself enforces rather than one
    only a test believes.
    """
    return mock_idps(
        {
            MOCK_IDP_TOOL_REDIRECT_URI_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.oidc_callback}"
            )
        }
    )


@pytest.fixture
def open_web_door(tool_doors: Any, door_contract: Any, provider: Any) -> Any:
    """Build the tool for this provider, with settings a test may override.

    Every OIDC endpoint comes out of the provider's discovery document, which is
    how a client learns them and which means nothing about the mock's URLs is
    written down here. The host in those URLs is also what routes the tool's
    server-side calls back into the in-process provider, so a door that fetched
    from anywhere else reaches no mock and says so.
    """
    document = provider.discovery()
    registration = provider.registration()
    names = door_contract.settings

    def endpoint(member: str) -> str:
        value = document.get(member)
        assert isinstance(value, str) and value, (
            f"The provider's discovery document advertises no `{member}` (it carries "
            f"{sorted(document)}). That member is how a client configures itself, and E0-18's "
            "settings hold exactly these addresses."
        )
        return value

    def build(*, around: Any = None, environment: str | None = None, **overrides: str) -> Any:
        values = {
            names["public_base_url"]: door_contract.public_base_url,
            names["oidc_issuer"]: endpoint("issuer"),
            names["oidc_authorization_endpoint"]: CONFIGURED_AUTHORIZATION_ENDPOINT,
            names["oidc_token_endpoint"]: endpoint("token_endpoint"),
            names["oidc_jwks_url"]: endpoint("jwks_uri"),
            names["oidc_client_id"]: registration["client_id"],
        }
        values.update({names[key]: value for key, value in overrides.items()})
        if environment is not None:
            values[ENVIRONMENT_VARIABLE] = environment
        host = urlsplit(endpoint("token_endpoint")).hostname
        return tool_doors(values, {host: provider}, around=around)

    return build


@pytest.fixture
def web_jwks_url(provider: Any) -> str:
    """Where this tool is configured to fetch the provider's signing keys.

    Out of the discovery document, like every other endpoint the tool is
    configured with, so the address this module reasons about and the address the
    tool fetches cannot become two different strings.
    """
    advertised = provider.discovery().get("jwks_uri")
    assert isinstance(advertised, str) and advertised, (
        "The provider's discovery document advertises no `jwks_uri` (it carries "
        f"{sorted(provider.discovery())}), so there is no key set address to configure or to "
        "reason about."
    )
    return advertised


@pytest.fixture
def token_endpoint_path(provider: Any) -> str:
    """The path the tool redeems a code at, for the two tests that wrap that call."""
    return urlsplit(provider.discovery()["token_endpoint"]).path


@pytest.fixture
def tool(open_web_door: Any) -> Any:
    """The tool, configured correctly for the running provider."""
    return open_web_door()


def begin(tool: Any, contract: Any) -> dict[str, str]:
    """Start a web login and read the authorization request the tool built."""
    response = tool.get(contract.oidc_login)
    return query_of(redirect_target(response, "a web login was started"))


def sign_in(provider: Any, parameters: dict[str, str], person: Any, **substitutions: str) -> Any:
    """Carry the tool's authorization request to the provider and sign in as `person`.

    `substitutions` replaces one of the tool's own parameters, which is how the
    nonce refusal is posed: the provider puts back whatever it was given, so a
    session carrying a nonce the tool never generated is one parameter different
    from the happy path and identical in every other respect.
    """
    attempt = provider.begin_from(list({**parameters, **substitutions}.items()), "")
    submitted = provider.submit_login(attempt, provider.identity_of(person, attempt))
    assert submitted.code, (
        f"The provider issued no authorization code for {person.get('subject')!r}: it answered "
        f"{submitted.response.status_code} and sent {submitted.location!r}. E0-16's criterion 3 is "
        "that this flow completes, and its own suite asserts it — a failure here is this module "
        "driving the provider wrongly rather than a defect in the tool."
    )
    return submitted


def complete(tool: Any, contract: Any, submitted: Any) -> Any:
    """Deliver the provider's response to the tool's callback."""
    return tool.get(
        contract.oidc_callback, params={"code": submitted.code, "state": submitted.state}
    )


def logged_in(tool: Any, contract: Any, provider: Any, person: Any, **substitutions: str) -> Any:
    """One whole web login, from `/auth/oidc/login` to the landing page."""
    parameters = begin(tool, contract)
    return complete(tool, contract, sign_in(provider, parameters, person, **substitutions))


# ---------------------------------------------------------------------------
# `GET /auth/oidc/login` — what the tool asks the provider for.
# ---------------------------------------------------------------------------


def test_the_login_endpoint_redirects_to_the_configured_authorization_endpoint(
    tool: Any, door_contract: Any
) -> None:
    """Criterion: a 302 to the provider's authorization endpoint.

    **Dies if the endpoint is derived rather than configured.** E0-18 splits the
    provider's addresses into a browser-facing authorize URL and server-facing
    token and JWKS URLs, because a browser reaches the provider on a published port
    and the tool reaches it by container name — a tool that built one from the other
    works in a test harness and sends a real browser somewhere it cannot resolve.
    """
    location = redirect_target(tool.get(door_contract.oidc_login), "a web login was started")

    split = urlsplit(location)
    without_query = f"{split.scheme}://{split.netloc}{split.path}"
    assert without_query == CONFIGURED_AUTHORIZATION_ENDPOINT, (
        f"The tool redirected to {without_query!r} and the configured authorization endpoint is "
        f"{CONFIGURED_AUTHORIZATION_ENDPOINT!r}. E0-18 makes the browser-facing authorize URL a "
        "setting of its own; a value assembled from the issuer would agree with the provider by "
        "construction and would not be configuration."
    )


def test_the_authorization_request_names_the_configured_client_and_the_tools_own_callback(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """Criterion: the request carries `client_id` and `redirect_uri`.

    **Dies if the callback URL is built from the incoming request** — from its
    `Host` header, or from the URL the test client used — rather than from
    `PUBLIC_BASE_URL`. That mistake is invisible behind a correctly configured
    reverse proxy and is how a redirect URI ends up being whatever an attacker's
    `Host` header said.
    """
    parameters = begin(tool, door_contract)

    assert parameters.get("client_id") == provider.registration()["client_id"], (
        f"The authorization request names client {parameters.get('client_id')!r}; the provider "
        f"registers {provider.registration()['client_id']!r}."
    )
    expected = f"{door_contract.public_base_url}{door_contract.oidc_callback}"
    assert parameters.get("redirect_uri") == expected, (
        f"The authorization request's `redirect_uri` is {parameters.get('redirect_uri')!r} and the "
        f"tool's own callback is {expected!r}. The provider compares this exactly, twice, so the "
        "two disagreeing is a flow that cannot complete — and a value taken from the request is "
        "one the caller chose."
    )


def test_the_authorization_request_asks_for_the_code_flow_with_the_openid_scope(
    tool: Any, door_contract: Any
) -> None:
    """Criterion: `response_type=code` and a scope including `openid`.

    **Dies against an implicit-flow request.** `response_type=id_token` returns a
    token in the URL fragment with no code exchange and no PKCE — a downgrade that
    still lands somebody on a landing page, so nothing else in this module would
    notice. `openid` is what makes the response an OpenID Connect one at all
    (OIDC Core 1.0 §3.1.2.1): without it a conformant provider issues no `id_token`
    and there is nothing to read a role out of.
    """
    parameters = begin(tool, door_contract)

    assert parameters.get("response_type") == "code", (
        f"The tool asked for `response_type` {parameters.get('response_type')!r}. E0-18 starts an "
        "authorization *code* flow; anything else skips the server-side exchange and the PKCE "
        "binding with it."
    )
    scopes = (parameters.get("scope") or "").split()
    assert "openid" in scopes, (
        f"The tool asked for scope {parameters.get('scope')!r}, which does not include `openid`. "
        "That value is what distinguishes an OpenID Connect request from a plain OAuth 2.0 one, "
        "and without it there is no `id_token` and no roles claim."
    )


def test_the_authorization_request_carries_an_s256_pkce_challenge(
    tool: Any, door_contract: Any
) -> None:
    """Criterion: PKCE with `S256`.

    **Dies if PKCE is omitted, and dies if it is downgraded to `plain`.** Both
    matter and they are different mutations: a public client with no secret has
    nothing but PKCE binding the code to the client that asked for it, and a `plain`
    challenge puts the verifier itself in the redirect a browser records in its
    history. E0-16's provider refuses anything but `S256`, so an omission surfaces
    as a flow that does not complete — which reads as a broken provider unless
    something asserts this directly.
    """
    parameters = begin(tool, door_contract)

    assert parameters.get("code_challenge"), (
        f"The authorization request carries no `code_challenge` (it carries "
        f"{sorted(parameters)}). The tool is a public client with no secret, so the challenge is "
        "the only thing binding the authorization code to it."
    )
    assert parameters.get("code_challenge_method") == REQUIRED_CHALLENGE_METHOD, (
        f"The challenge method is {parameters.get('code_challenge_method')!r} rather than "
        f"{REQUIRED_CHALLENGE_METHOD!r}. `plain` sends the verifier in the URL, which is the one "
        "place PKCE exists to keep it out of."
    )


def test_two_web_logins_carry_a_fresh_state_and_a_fresh_nonce(
    tool: Any, door_contract: Any
) -> None:
    """Criterion: `state` and `nonce` are per flow.

    **Dies against a constant**, which is what a value read from configuration or
    derived from the client looks like — and which validates perfectly in any
    single flow, so every other test in this module passes against it.
    """
    first = begin(tool, door_contract)
    second = begin(tool, door_contract)

    for name in ("state", "nonce", "code_challenge"):
        assert first.get(
            name
        ), f"The authorization request carries no `{name}` (it carries {sorted(first)})."
        assert first[name] != second.get(name), (
            f"Two web logins carried the same `{name}` ({first[name]!r}). A reused `state` is no "
            "cross-site request forgery defence, a reused `nonce` makes every session a replay, "
            "and a reused challenge means one verifier opens every code this tool ever gets."
        )


# ---------------------------------------------------------------------------
# The landing pages, one per role §2 gives this door.
# ---------------------------------------------------------------------------


def test_the_dean_lands_on_the_leadership_view(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """E0-18's criterion: the dean's web login lands on the leadership view.

    The whole flow is real — authorization request, login form, code, and a
    server-side exchange carrying the verifier — so this fails if any link is
    missing. It is the first of three, and the three together are what make the
    dispatch on the roles claim observable at all.
    """
    response = logged_in(tool, door_contract, provider, person_holding(provider, "DEAN"))

    lands_on(response, door_contract, LEADERSHIP_VIEW)


def test_the_care_office_lands_on_the_care_view(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """`CARE` → the Care empty view (§6.2, and E0-18's route description).

    The Care office rather than the person who also teaches: she is the subject of
    her own test below, and picking whichever of the two the document listed first
    would make one of these two tests silently about the other.
    """
    response = logged_in(tool, door_contract, provider, person_holding(provider, "CARE"))

    lands_on(response, door_contract, CARE_VIEW)


def test_the_administrator_lands_on_the_admin_view(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """`ADMIN` → the admin empty view, the last of the three the web door serves.

    **Dies if the role dispatch falls through to a default.** A tool that landed
    everything it did not recognise on one view passes the leadership test and the
    Care test if Care is checked explicitly; Admin is the case that catches the
    fallback, because it is last in E0-18's precedence order.
    """
    response = logged_in(tool, door_contract, provider, person_holding(provider, "ADMIN"))

    lands_on(response, door_contract, ADMIN_VIEW)


@pytest.mark.invariant
def test_the_leadership_view_names_nobody_but_the_person_signed_in(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """SPEC §4.1 over the one view that would otherwise list people.

    E0-18: the leadership landing views "are empty *by design* and must not
    traverse" `transitive_purview`, which raises (ADR 0003). So the honest
    assertion is that the page names nobody but its own caller — a page that
    enumerated the institution would have obtained that list from somewhere, and
    there is nowhere in E0 it could legitimately have come from.

    Two guards keep this from passing on emptiness, which is what
    `docs/MISTAKES.md` entry 3 is about here. The landing testid has to be present,
    so a 404 or a blank body fails rather than passes; and the scan is shown
    finding the very strings it reports absent, so a search that has gone blind
    says so instead of reporting a clean page.
    """
    dean = person_holding(provider, "DEAN")
    response = logged_in(tool, door_contract, provider, dean)
    lands_on(response, door_contract, LEADERSHIP_VIEW)

    others = identifying_strings(provider, dean)
    assert others, (
        "No seeded person other than the dean publishes an address or a subject, so this test has "
        "nothing to look for and would pass against a page listing the whole institution."
    )
    canary = " ".join(others)
    assert all(value in canary for value in others), (
        "The scan below cannot find these strings in a sample built out of them, so its silence "
        "about the landing page means nothing."
    )

    leaked = sorted({value for value in others if value in response.text})
    assert not leaked, (
        f"The leadership landing page carries {leaked}, which identify seeded people other than "
        "the dean who signed in. E0-18 makes this view empty by design: purview is not computed "
        "in E0, so a page that lists people got that list from somewhere §4.1 does not sanction."
    )


@pytest.mark.invariant
def test_the_care_view_names_nobody_but_the_person_signed_in(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """The same, for the one view SPEC §6.2 spends a paragraph on.

    E0-18: "The Care page shows a heading and nothing else — read §6.2 before
    writing even that." Care is the one role in this system that can re-identify a
    student, so a Care landing page that arrived carrying anybody is the most
    expensive version of this mistake. Same two guards as above, for the same
    reason.
    """
    care = person_holding(provider, "CARE")
    response = logged_in(tool, door_contract, provider, care)
    lands_on(response, door_contract, CARE_VIEW)

    others = identifying_strings(provider, care)
    assert others, (
        "No seeded person other than the Care office publishes an address or a subject, so this "
        "test has nothing to look for."
    )
    canary = " ".join(others)
    assert all(value in canary for value in others), (
        "The scan below cannot find these strings in a sample built out of them, so its silence "
        "about the landing page means nothing."
    )

    leaked = sorted({value for value in others if value in response.text})
    assert not leaked, (
        f"The Care landing page carries {leaked}. §6.2 keeps the Care surface to the threat queue "
        "and nothing else, and E0 builds no queue — so this page has one heading's worth of "
        "content and any identifier on it came from a read nothing sanctions."
    )


@pytest.mark.invariant
def test_the_web_door_writes_no_row_for_the_care_person_it_lands(
    tool: Any,
    door_contract: Any,
    provider: Any,
    migrated_engine: Any,
    committed_rows: Any,
) -> None:
    """The claim produced a page, never a capability. E0-09 criterion 10, behaviourally.

    **Dies if the callback writes an assignment, or provisions a person, from the
    claim.** This is the other half of the exception
    `tests/unit/test_care_is_not_reachable_from_a_claim.py::EXCEPTIONS` grants to
    `backend/app/services/landing.py`. That exception rests on one factual claim —
    the landing seam chooses a screen and writes nothing — and an exception that
    rests on a sentence in a comment is an exception that stops being true without
    anyone noticing. So the sentence is asserted here, against the whole flow, as
    the Care person: authorization request, login form, code, server-side
    exchange, landing page, and not one row anywhere.

    The Care half is the one that must never move. E0-09: "No LTI claim, no OIDC
    claim, and no LMS role may ever produce a `CARE` assignment… a claim-to-Care
    mapping would let an LMS administrator grant themselves identity access."
    E0-11 resolves what an actor may do out of `role_assignment` and out of
    nothing else, so as long as the claim reaches no row in that table, a forged
    or administrator-granted `CARE` claim buys an empty page.

    The provisioning half moves once, deliberately: E0-18's boundary gives E1 the
    `user` row and the dual-door identity merge, and when E1 builds them this
    assertion changes in E1's own pull request with the reason written down. What
    it must not do is start passing quietly because a door began provisioning
    early.

    Two guards keep this from passing on nothing having happened: the flow has to
    land on the Care view, so a 4xx or a door that was never reached fails rather
    than passes; and the counter is shown reading a table the migration filled, so
    a reader pointed at an empty or unmigrated database says so instead of
    reporting a clean flow. `committed_rows` is taken for its teardown alone — it
    removes whatever appeared during the test, so a door that does write leaves a
    failure here rather than a row for somebody else's non-vacuity guard to trip
    over three tickets from now.
    """
    stamped = committed_row_count(migrated_engine, STAMPED_TABLE)
    assert stamped >= 1, (
        f"`public.{STAMPED_TABLE}` holds {stamped} rows, so this counter is reading a database "
        "nothing has migrated — and it would report every table below as empty and unchanged no "
        "matter what the door wrote. The tool and this connection are both configured from "
        "`migrated_database`."
    )
    counted = (ASSIGNMENT_TABLE, *PROVISIONING_TABLES)
    before = {name: committed_row_count(migrated_engine, name) for name in counted}

    care = person_holding(provider, "CARE")
    response = logged_in(tool, door_contract, provider, care)
    lands_on(response, door_contract, CARE_VIEW)

    after = {name: committed_row_count(migrated_engine, name) for name in counted}

    assert after[ASSIGNMENT_TABLE] == before[ASSIGNMENT_TABLE], (
        f"A web login stating `CARE` took `public.{ASSIGNMENT_TABLE}` from "
        f"{before[ASSIGNMENT_TABLE]} rows to {after[ASSIGNMENT_TABLE]}. A claim has produced an "
        "assignment, which is precisely what E0-09 criterion 10 forbids: the person who "
        "administers the identity provider controls what the claim says, and a row in this table "
        "is what the reveal in §6.2 is gated on. The landing seam may choose a screen from a "
        "claim; nothing may grant from one."
    )
    grew = sorted(name for name in PROVISIONING_TABLES if after[name] != before[name])
    assert not grew, (
        f"The web login wrote to {grew} — {[(name, before[name], after[name]) for name in grew]}. "
        "E0-18's boundary section gives provisioning and the dual-door identity merge to E1: 'E0 "
        "does not build any database identity resolution on either door, any `user` row for a mock "
        "subject.' A door that provisions from a claim has decided, ahead of E1 and without the "
        "merge, that this subject is a new human. If E1 is the change that provoked this, move "
        "this assertion in E1's pull request and say what the door now writes."
    )


# ---------------------------------------------------------------------------
# `GET /auth/oidc/callback` — one refusal per check.
# ---------------------------------------------------------------------------


def test_a_callback_carrying_a_state_the_tool_never_issued_is_refused(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """Criterion: mismatched `state`. **Dies if `state` is accepted without comparison.**

    The `code` is a real one the provider just issued for this tool; only the
    `state` beside it is a value the tool never sent. A tool that reads `state` out
    of the query and does not compare it to what it stored passes every other test
    in this module.
    """
    parameters = begin(tool, door_contract)
    submitted = sign_in(provider, parameters, person_holding(provider, "DEAN"))

    response = tool.get(
        door_contract.oidc_callback,
        params={"code": submitted.code, "state": "a-state-this-tool-never-issued"},
    )

    refused(response, door_contract, "a callback carrying a `state` the tool never issued")


def test_a_callback_carrying_no_state_at_all_is_refused(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """The absent case, which the mismatch above does not cover.

    `if state and state != expected` passes the test above and fails this one, and
    it is the defence an attacker defeats by sending nothing. A different mutation
    is a different case.
    """
    parameters = begin(tool, door_contract)
    submitted = sign_in(provider, parameters, person_holding(provider, "DEAN"))

    response = tool.get(door_contract.oidc_callback, params={"code": submitted.code})

    refused(response, door_contract, "a callback carrying no `state` at all")


def test_a_session_carrying_a_nonce_the_tool_never_sent_is_refused(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """Criterion: mismatched `nonce`. **Dies if the nonce is sent and never compared.**

    The provider puts back whatever nonce it was given, so substituting one
    parameter of the tool's own authorization request produces a correctly signed
    session whose nonce the tool never generated. Everything else — `state`, the
    code, the verifier, the audience, the issuer, the signature — is the happy
    path's.

    Without this the nonce is decoration: generated, sent, echoed, never read, and
    E1's replay work built on a value nothing compares.
    """
    parameters = begin(tool, door_contract)
    assert parameters.get("nonce"), (
        "The tool's authorization request carries no `nonce`, so there is nothing to substitute "
        "and nothing for the callback to compare."
    )
    submitted = sign_in(
        provider,
        parameters,
        person_holding(provider, "DEAN"),
        nonce="a-nonce-the-tool-never-generated",
    )

    response = complete(tool, door_contract, submitted)

    refused(response, door_contract, "a session whose `nonce` is not the one the tool sent")


def test_a_session_from_an_issuer_the_tool_does_not_trust_is_refused(
    open_web_door: Any, door_contract: Any, provider: Any
) -> None:
    """Criterion: wrong `iss`. **Dies if `iss` is never compared to the configured issuer.**

    The tool is configured to expect one issuer and the provider states another;
    every other setting still names the running provider, so the flow completes and
    the only thing wrong with what arrives is who says it issued it. OIDC Core 1.0
    §3.1.3.7 makes this comparison mandatory, and without it any provider the tool
    can reach can mint sessions for it.

    If this fails with the tool's fetch reaching no mock at all, that is the same
    finding in a different shape: the tool derived its token and JWKS URLs from the
    issuer instead of reading the settings E0-18 gives them, so pointing the issuer
    somewhere untrusted moved the endpoints too.
    """
    tool = open_web_door(oidc_issuer=UNTRUSTED_ISSUER)

    response = logged_in(tool, door_contract, provider, person_holding(provider, "DEAN"))

    refused(response, door_contract, "a session stating an issuer the tool does not trust")


def test_a_session_whose_audience_is_not_this_tools_client_is_refused(
    open_web_door: Any,
    door_contract: Any,
    provider: Any,
    token_endpoint_path: str,
    claims_in_token: Any,
) -> None:
    """Criterion: wrong `aud`. **Dies if the audience is never compared to the client id.**

    OIDC Core 1.0 §3.1.3.7 requires it, and without it a token minted for any
    other client of the same provider is a session here — which is the whole point
    of an audience: the provider says who a token is *for*, and a client that does
    not read that accepts tokens addressed to somebody else.

    **Posed without breaking the signature**, which is what makes the 4xx mean
    `aud` rather than arithmetic. The tool is configured as a client the provider
    registers nobody under, and the two places that would otherwise refuse the
    flow before the audience is ever read are carried by the real client id
    instead: the authorization request the browser delivers, and the code exchange
    the tool makes server-side, which the seam re-poses through the provider's own
    token endpoint. So the `id_token` that arrives is genuinely signed, genuinely
    fresh, states the trusted issuer and echoes the tool's own nonce — and names an
    audience this tool is not.

    The premise is asserted rather than assumed: the token's `aud` is read back and
    required to name the registered client and not the tool's own. Without that,
    this test would pass just as well against a flow that failed at the exchange
    for a reason nobody looked at (`docs/MISTAKES.md` entry 3).
    """
    registered = provider.registration()["client_id"]
    received: dict[str, Any] = {}

    def around(request: Any, deliver: Any) -> Any:
        if urlsplit(str(request.url)).path != token_endpoint_path:
            return deliver()
        fields = [
            (name, value)
            for name, value in parse_qsl(request.content.decode("utf-8"))
            if name != "client_id"
        ]
        answered = provider.redeem_from([*fields, ("client_id", registered)])
        body = dict(provider.body_of(answered))
        assert answered.status_code == 200 and body.get("id_token"), (
            f"Redeeming the tool's own code as the registered client answered "
            f"{answered.status_code} with {sorted(body)}, so no token was issued and the refusal "
            "below would be a flow that never completed rather than an audience the tool rejected. "
            f"The tool posted {sorted(name for name, _ in fields)} to the token endpoint."
        )
        received["claims"] = claims_in_token(str(body["id_token"]))
        return httpx.Response(answered.status_code, json=body, request=request)

    tool = open_web_door(around=around, oidc_client_id=UNREGISTERED_CLIENT_ID)

    response = logged_in(
        tool, door_contract, provider, person_holding(provider, "DEAN"), client_id=registered
    )

    claims = received.get("claims")
    assert claims, (
        "The tool never redeemed its code at the token endpoint, so no `id_token` reached it and "
        "whatever it answered was decided before any audience was read. This test can only say "
        "something about `aud` if the token arrives."
    )
    audience = claims.get("aud")
    named = audience if isinstance(audience, list) else [audience]
    assert registered in named and UNREGISTERED_CLIENT_ID not in named, (
        f"The token that reached the tool names audience {audience!r}. This test needs it "
        f"addressed to {registered!r} — the provider's registered client — and not to "
        f"{UNREGISTERED_CLIENT_ID!r}, which is what the tool is configured as; otherwise there is "
        "no audience mismatch here and the refusal below would be about something else."
    )

    refused(response, door_contract, "a session whose `aud` names a different client")


def test_a_callback_is_refused_when_the_token_endpoint_answers_with_a_tampered_id_token(
    open_web_door: Any,
    door_contract: Any,
    provider: Any,
    token_endpoint_path: str,
    tamper_with: Any,
) -> None:
    """Criterion: bad signature. **Dies if the `id_token` is decoded and not verified.**

    The token arrives from the token endpoint over a channel the tool trusts, which
    is exactly why it has to be verified anyway: a client that skips the signature
    because the exchange was server-side has made the roles claim a statement by
    whoever answered the connection. The tamper re-encodes altered claims and keeps
    the original signature, so the token is well formed in every respect except the
    arithmetic — a corrupted string would be refused at the decoder and would prove
    nothing.
    """

    def around(request: Any, deliver: Any) -> Any:
        answered = deliver()
        if urlsplit(str(request.url)).path != token_endpoint_path:
            return answered
        body = dict(answered.json())
        # Without this the refusal below could be the exchange having failed for
        # some reason of its own, with nothing tampered at all — a green that says
        # nothing about the signature (`docs/MISTAKES.md` entry 3).
        assert answered.status_code == 200 and body.get("id_token"), (
            f"The token endpoint answered {answered.status_code} with {sorted(body)}, so there was "
            "no `id_token` to tamper with and the tool refused a flow that never completed."
        )
        body["id_token"] = tamper_with(str(body["id_token"]))
        return httpx.Response(answered.status_code, json=body, request=request)

    tool = open_web_door(around=around)

    response = logged_in(tool, door_contract, provider, person_holding(provider, "DEAN"))

    refused(response, door_contract, "a session whose `id_token` was altered after signing")


def test_a_callback_is_refused_when_the_session_expired_an_hour_ago(
    open_web_door: Any,
    door_contract: Any,
    provider: Any,
    token_endpoint_path: str,
    wind_the_clock_back: Any,
) -> None:
    """Criterion: stale `exp`. **Dies if `exp` is never compared to now.**

    The provider's clock is wound back while it mints, and only while it mints, so
    the `id_token` that comes back is genuinely expired and genuinely signed. The
    tool's own clock is the real one when it judges what arrived.

    Its pair is the next test, and neither is worth much alone.
    """

    def around(request: Any, deliver: Any) -> Any:
        if urlsplit(str(request.url)).path != token_endpoint_path:
            return deliver()
        with wind_the_clock_back(CERTAINLY_EXPIRED_SECONDS):
            return deliver()

    tool = open_web_door(around=around)

    response = logged_in(tool, door_contract, provider, person_holding(provider, "DEAN"))

    refused(response, door_contract, "a session whose `id_token` expired an hour ago")


def test_a_session_minted_seconds_ago_is_still_accepted(
    open_web_door: Any,
    door_contract: Any,
    provider: Any,
    token_endpoint_path: str,
    wind_the_clock_back: Any,
) -> None:
    """The near miss for the test above: a session that is old and not yet expired.

    **This is what makes that refusal mean "expired" rather than "minted under a
    wound-back clock".** Without it, a tool that refused every session produced this
    way — for any reason nobody has looked at — would satisfy the expiry test while
    checking nothing, and so would one that demanded an `iat` of this instant.

    The wind-back is short enough to sit inside any `id_token` lifetime a provider
    would issue, so this session is valid by every reading.
    """

    def around(request: Any, deliver: Any) -> Any:
        if urlsplit(str(request.url)).path != token_endpoint_path:
            return deliver()
        with wind_the_clock_back(CERTAINLY_STILL_VALID_SECONDS):
            return deliver()

    tool = open_web_door(around=around)

    response = logged_in(tool, door_contract, provider, person_holding(provider, "DEAN"))

    lands_on(response, door_contract, LEADERSHIP_VIEW)


# ---------------------------------------------------------------------------
# The person who uses both doors. E0-18 criterion 4.
# ---------------------------------------------------------------------------


def test_the_two_hat_person_opens_the_care_view_here_and_the_instructor_view_by_launch(
    tool_doors: Any,
    door_contract: Any,
    provider: Any,
    mock_platforms: Any,
    open_web_door: Any,
    register_platform: Any,
) -> None:
    """E0-18: "the two-hat person exists on both doors and both doors open for her".

    §2: "Entry doors are a property of the assignment, not the person." She holds a
    Care assignment, which enters by web login, and an instructor assignment, which
    enters by launch — so the two views she reaches are not a contradiction, they
    are the model working. Her web session states `CARE` and nothing else, because
    her teaching assignment does not open this door; her launch states the LIS
    Instructor role, because it does.

    **The database-level assertion that these are one person is E1's, not this
    ticket's**, and E0-18 says so: it needs the dual-door identity merge E1's
    breakdown owns, and E0 writes no `user` row for a mock subject. What ties the
    two halves below to one human is `mock-idp/app/seed.py::LMS_INSTRUCTOR_USER_ID`,
    the cross-mock reference published as `lms_user_id` — pinned to the platform's
    own constant by `tests/unit/test_the_mock_seeds_name_one_person.py`, and used
    here to choose which launch to drive.

    Both doors in one test on purpose. Split in two, each half is satisfied by a
    seed the other person is missing from, and the fact worth asserting — that one
    published identity opens both — is not stated anywhere.
    """
    hers = person_holding(provider, "CARE", and_a_launch_assignment=True)
    lms_user_id = hers.get("lms_user_id")
    assert lms_user_id, (
        f"The two-hat person is published without an `lms_user_id` ({hers!r}). ADR 0058 makes it "
        "the member that says which LMS user she is, and without it these are two fixtures rather "
        "than one human."
    )

    web = open_web_door()
    care_landing = logged_in(web, door_contract, provider, hers)
    lands_on(care_landing, door_contract, CARE_VIEW)

    platform = mock_platforms(
        {
            MOCK_LMS_TOOL_LOGIN_URL_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.lti_login}"
            ),
            MOCK_LMS_TOOL_LAUNCH_URL_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.lti_launch}"
            ),
        }
    )
    offers = [
        offer
        for offer in platform.require_offers()
        if offer.parameters.get("login_hint") == lms_user_id
    ]
    assert offers, (
        f"The mock platform offers no launch for {lms_user_id!r}, the LMS user the provider says "
        "she is. The two mocks then name two different people and this test cannot ask its "
        "question."
    )

    assert any(
        "Instructor" in role for role in platform.mint(offers[0]).claims.get(LTI_ROLES_CLAIM) or []
    ), (
        "Her launch carries no instructor role. The assignment that makes her the two-hat person "
        "is her teaching one, and it is the launch door that carries it."
    )

    jwks_url = platform.discovery()["jwks_uri"]
    register_platform(offers[0], jwks_url)
    launch_tool = tool_doors(
        {
            door_contract.settings["public_base_url"]: door_contract.public_base_url,
            door_contract.settings["lti_authorization_endpoint"]: (
                "http://lti-platform.invalid/e0-18-configured-authorize"
            ),
        },
        {urlsplit(jwks_url).hostname: platform},
    )

    started = launch_tool.post(door_contract.lti_login, data=offers[0].parameters)
    parameters = query_of(redirect_target(started, "her launch was initiated"))
    path = platform.endpoint("authorization_endpoint", ("auth",), "answers with a signed token")
    answered = (
        platform.client.post(path, data=parameters)
        if path in platform.paths("POST")
        else platform.client.get(path, params=parameters)
    )
    id_token, state, _ = platform.read_authorization_response(answered, path)
    instructor_landing = launch_tool.post(
        door_contract.lti_launch, data={"id_token": id_token, "state": state}
    )

    lands_on(instructor_landing, door_contract, INSTRUCTOR_VIEW)


# ---------------------------------------------------------------------------
# One door, one vocabulary. This is the launch door's rule from the other side:
# `test_lti_launch_door.py` asserts that door reads only the LIS roles claim, and
# these three assert this one reads only `roles_claim` and never the LTI claim.
# ---------------------------------------------------------------------------


def re_signing(
    keys: Any,
    token_endpoint_path: str,
    claims_in_token: Any,
    adjust: Any,
    seen: list[dict[str, Any]],
) -> Any:
    """An `around` hook that re-signs the `id_token` the token endpoint answered with.

    The exchange is the real one — the tool's own code, its own verifier, the
    provider's own token endpoint — and what comes back is decoded, changed in the
    one place the test is about, and signed by `suite_key_set`. The tool is
    configured to fetch its key set from that same suite key set, so the token that
    arrives is genuinely signed, genuinely fresh, states the trusted issuer and
    echoes the tool's own nonce.

    The key set request is answered here as well, because only the provider's host
    is mounted: delivering it would reach no mock at all.

    `seen` collects the claims as the provider issued them, so a test can assert
    its premise instead of assuming it — that the session really did carry the
    claim it is about (`docs/MISTAKES.md` entry 3).
    """

    def around(request: Any, deliver: Any) -> Any:
        served = keys.serve(request)
        if served is not None:
            return served
        answered = deliver()
        if urlsplit(str(request.url)).path != token_endpoint_path:
            return answered
        body = dict(answered.json())
        assert answered.status_code == 200 and body.get("id_token"), (
            f"The token endpoint answered {answered.status_code} with {sorted(body)}, so there was "
            "no `id_token` to re-sign and whatever the tool answered is about a flow that never "
            "completed."
        )
        claims = dict(claims_in_token(str(body["id_token"])))
        seen.append(claims)
        body["id_token"] = keys.sign(adjust(dict(claims)))
        return httpx.Response(answered.status_code, json=body, request=request)

    return around


def test_a_session_re_signed_by_this_suite_still_lands_the_care_view(
    open_web_door: Any,
    door_contract: Any,
    provider: Any,
    token_endpoint_path: str,
    claims_in_token: Any,
    suite_key_set: Any,
) -> None:
    """The control for the two tests below, and they are worth nothing without it.

    The claims are the provider's own, unchanged, signed again by the key set this
    tool is configured to verify against. If this lands on the Care view then the
    machinery — the key, the served JWK Set, the `kid`, the re-encoding — produces
    sessions this door accepts, and a refusal below can only be the one claim it
    changed. If it does not, the tests below are red about the harness rather than
    about the door, and this is where that shows.
    """
    seen: list[dict[str, Any]] = []
    tool = open_web_door(
        around=re_signing(
            suite_key_set, token_endpoint_path, claims_in_token, lambda claims: claims, seen
        ),
        oidc_jwks_url=suite_key_set.jwks_url,
    )

    response = logged_in(tool, door_contract, provider, person_holding(provider, "CARE"))

    assert seen, "The tool never redeemed its code, so nothing was re-signed and nothing is proved."
    lands_on(response, door_contract, CARE_VIEW)


def test_a_session_also_carrying_an_lti_roles_claim_lands_where_its_own_claim_names(
    open_web_door: Any,
    door_contract: Any,
    provider: Any,
    token_endpoint_path: str,
    claims_in_token: Any,
    suite_key_set: Any,
) -> None:
    """The foreign vocabulary is **ignored**, not merely outranked.

    A session stating `CARE` in this door's own roles claim and the LIS Instructor
    role in the LTI claim lands on the Care view. This is the boundary control on
    the refusal below: a door that refused any session carrying an unfamiliar claim
    would satisfy that one while being wrong about this, and a door that read both
    vocabularies and happened to prefer its own would pass this and fail that.

    Its premise is asserted rather than assumed: the session as the provider issued
    it carries this door's roles claim, and the LTI claim is added on top.
    """
    roles_claim = provider.roles_claim_name()
    seen: list[dict[str, Any]] = []

    def adjust(claims: dict[str, Any]) -> dict[str, Any]:
        claims[LTI_ROLES_CLAIM] = [INSTRUCTOR_ROLE_URI]
        return claims

    tool = open_web_door(
        around=re_signing(suite_key_set, token_endpoint_path, claims_in_token, adjust, seen),
        oidc_jwks_url=suite_key_set.jwks_url,
    )

    response = logged_in(tool, door_contract, provider, person_holding(provider, "CARE"))

    assert seen and seen[0].get(roles_claim), (
        f"The session the provider issued carries no `{roles_claim}` (it carries "
        f"{sorted(seen[0]) if seen else 'nothing — the code was never redeemed'}), so this test is "
        "not about a door choosing between two vocabularies."
    )
    lands_on(response, door_contract, CARE_VIEW)


def test_a_session_stating_only_an_lti_roles_claim_is_refused(
    open_web_door: Any,
    door_contract: Any,
    provider: Any,
    token_endpoint_path: str,
    claims_in_token: Any,
    suite_key_set: Any,
) -> None:
    """**Dies if the web door consults the launch door's vocabulary.**

    The session states the LIS Instructor role and nothing in this door's own roles
    claim. SPEC §2 gives this door the roles the LMS may not name; a door that read
    the LTI claim would take a role vocabulary an LMS administrator controls and
    use it to choose a screen here — the mirror image of the rule
    `test_a_launch_naming_a_web_door_role_and_no_lis_role_is_refused` asserts in
    `tests/integration/test_lti_launch_door.py`.

    There is no view this door may serve for an instructor: E0-18 gives it
    leadership, Care and admin, and the LIS roles belong to the launch door. So the
    only answer is a refusal, and `refused` requires that no landing testid at all
    appears — a door that fell through to a default fails here whichever view it
    chose.
    """
    roles_claim = provider.roles_claim_name()
    seen: list[dict[str, Any]] = []

    def adjust(claims: dict[str, Any]) -> dict[str, Any]:
        claims.pop(roles_claim, None)
        claims[LTI_ROLES_CLAIM] = [INSTRUCTOR_ROLE_URI]
        return claims

    tool = open_web_door(
        around=re_signing(suite_key_set, token_endpoint_path, claims_in_token, adjust, seen),
        oidc_jwks_url=suite_key_set.jwks_url,
    )

    response = logged_in(tool, door_contract, provider, person_holding(provider, "CARE"))

    assert seen and seen[0].get(roles_claim), (
        f"The session the provider issued carries no `{roles_claim}`, so removing it changed "
        "nothing and this test is not posing the question it names."
    )
    refused(
        response,
        door_contract,
        f"a session stating {INSTRUCTOR_ROLE_URI!r} in `{LTI_ROLES_CLAIM}` and nothing in "
        f"`{roles_claim}`",
    )


# ---------------------------------------------------------------------------
# The cookie this door's login sets, and what a refusal says and does.
# ---------------------------------------------------------------------------


def answer_to(deliver: Any, what: str) -> Any:
    """What the tool answered, or a failure saying it raised instead of answering.

    `tool_doors` builds its `TestClient` with `raise_server_exceptions` at the
    default, so an exception escaping a route arrives here rather than as a 500.
    That *is* the crash the tests below are about — a door that stops rather than
    refuses — and it is worth one sentence naming it rather than a traceback that
    reads like a broken test.
    """
    try:
        return deliver()
    except Exception as failure:
        pytest.fail(
            f"The tool raised {type(failure).__name__}: {failure} rather than answering {what}. An "
            "exception that escapes a route is fail-closed and is still a defect: the caller gets "
            "no page, and everything the refusal path would have done on the way out — clearing "
            "the single-use cookie, keeping server-side addresses out of the response — did not "
            "happen."
        )


def cookies_set_by(response: Any, purpose: str) -> list[str]:
    """Every `Set-Cookie` header on a response, or a failure saying there were none."""
    headers = response.headers.get_list("set-cookie")
    assert headers, (
        f"The web login set no cookie at all when {purpose} (it answered {response.status_code} "
        f"with headers {sorted(response.headers)}). E0-18 has the verifier and state ride 'the same "
        "short-lived signed cookie mechanism as the launch door', and with no cookie there is "
        "nothing for the callback to compare against."
    )
    return headers


def attributes_of(header: str) -> set[str]:
    """The attribute names in one `Set-Cookie`, lowercased, without their values."""
    return {part.split("=", 1)[0].strip().lower() for part in header.split(";")[1:]}


def test_the_login_cookie_is_marked_secure_outside_development(
    open_web_door: Any, door_contract: Any
) -> None:
    """**Dies if the cookie is issued without `Secure`.**

    This cookie carries the `state`, the `nonce` and the PKCE verifier. The verifier
    is the only thing binding an authorization code to this client — E0-18 makes
    the tool a public client with no secret — so a cookie a browser will send over
    plain HTTP puts the one secret in the flow on the wire.

    Its pair is the next test: the flag has to be conditional, because a `Secure`
    cookie is not sent to `http://localhost` and would break the development flow
    this ticket exists to open.
    """
    tool = open_web_door(environment=PRODUCTION)

    response = tool.get(door_contract.oidc_login)

    for header in cookies_set_by(response, f"`{ENVIRONMENT_VARIABLE}` was {PRODUCTION!r}"):
        assert SECURE_ATTRIBUTE in attributes_of(header), (
            f"The web login set `{header}` with `{ENVIRONMENT_VARIABLE}` set to {PRODUCTION!r}, "
            "and it carries no `Secure` attribute. That cookie holds the PKCE verifier, which is "
            "the whole of what binds an authorization code to this client."
        )


def test_the_login_cookie_is_not_marked_secure_in_development(
    open_web_door: Any, door_contract: Any
) -> None:
    """The near miss for the test above: `Secure` unconditionally breaks the laptop.

    A browser reaches this tool at `http://localhost:8000` on a developer's
    machine, and does not send a `Secure` cookie there — so the callback finds no
    state, no nonce and no verifier, and refuses a flow that was correct. Without
    this, "always set `Secure`" satisfies the requirement above and is the wrong
    fix.
    """
    tool = open_web_door(environment=DEVELOPMENT)

    response = tool.get(door_contract.oidc_login)

    for header in cookies_set_by(response, f"`{ENVIRONMENT_VARIABLE}` was {DEVELOPMENT!r}"):
        assert SECURE_ATTRIBUTE not in attributes_of(header), (
            f"The web login set `{header}` with `{ENVIRONMENT_VARIABLE}` set to {DEVELOPMENT!r}. "
            "A `Secure` cookie is not sent to `http://localhost`, so every web login on a "
            "developer's laptop comes back to a callback that has nothing to compare."
        )


def test_a_callback_whose_state_is_not_ascii_is_refused_and_the_cookie_is_burned(
    open_web_door: Any, door_contract: Any, provider: Any, token_endpoint_path: str
) -> None:
    """**Dies if the comparison crashes instead of refusing** (and see entry 13).

    `secrets.compare_digest` raises `TypeError` when either side is a `str` holding
    a character outside ASCII, so a `state` of `é` takes a door that compares
    directly out through the error handler rather than through the refusal. The
    crash is fail-closed, which is why a suite that only asks whether the login
    succeeded never sees it; what it skips is what the refusal path does on the way
    out, and here that is the single-use cookie.

    Both halves are asserted. The second — the correct `state` for the same login,
    delivered afterwards, is refused too — is the one worth having, and it is
    guarded: if the door redeemed the code before comparing the state, then the
    second refusal could be a spent code rather than a burned cookie, and that
    guard fires instead of the test passing for the wrong reason.
    """
    exchanges: list[str] = []

    def around(request: Any, deliver: Any) -> Any:
        if urlsplit(str(request.url)).path == token_endpoint_path:
            exchanges.append(str(request.url))
        return deliver()

    tool = open_web_door(around=around)
    parameters = begin(tool, door_contract)
    submitted = sign_in(provider, parameters, person_holding(provider, "DEAN"))

    crashed = answer_to(
        lambda: tool.get(
            door_contract.oidc_callback, params={"code": submitted.code, "state": NON_ASCII_STATE}
        ),
        f"a callback whose `state` was {NON_ASCII_STATE!r}",
    )

    assert crashed.status_code != 500, (
        f"The tool answered 500 to a callback whose `state` was {NON_ASCII_STATE!r}. That is "
        "`secrets.compare_digest` raising `TypeError` on a non-ASCII `str` rather than answering "
        f"`False`. Body begins {crashed.text[:400]!r}."
    )
    refused(crashed, door_contract, f"a callback whose `state` was {NON_ASCII_STATE!r}")
    assert not exchanges, (
        f"The tool redeemed its code at the token endpoint ({exchanges}) while answering a callback "
        "whose `state` it had not accepted. Two things follow: an unauthenticated caller can make "
        "this tool spend a code, and the assertion below could no longer tell a burned cookie from "
        "a code that had already been used."
    )

    replayed = answer_to(
        lambda: complete(tool, door_contract, submitted),
        "the correct `state` for a login whose cookie a refusal should have burned",
    )

    assert 400 <= replayed.status_code < 500, (
        f"After refusing the non-ASCII `state`, the tool answered {replayed.status_code} to the "
        "correct `state` for the same login. The cookie holding the state, the nonce and the PKCE "
        "verifier should have been cleared on the way out of the refusal: one login buys one "
        "attempt, and a refusal that leaves it in place hands an attacker as many tries as they "
        "like at a cookie the browser is still carrying."
    )


def test_a_refusal_does_not_name_the_key_set_address_the_tool_could_not_reach(
    open_web_door: Any, door_contract: Any, provider: Any, web_jwks_url: str
) -> None:
    """**Dies if the refusal page carries the server-side address it failed to fetch.**

    The provider's key set URL is a server-side address — a Compose service name
    that means nothing to a browser and everything to somebody mapping the network
    behind the tool. A refusal that repeats it, in a message or a traceback,
    publishes that topology to whoever provoked the fetch, and provoking it takes
    nothing more than completing a login.

    The failure is provoked through the seam rather than by misconfiguring the
    tool, so an address in the refusal is the configured one rather than one this
    test typed. The host alone is asserted: that is the part that names a machine.
    """
    split = urlsplit(web_jwks_url)
    host = split.hostname
    assert host, (
        f"The configured key set URL {web_jwks_url!r} has no host, so there is no address for this "
        "test to look for."
    )
    fetched: list[str] = []

    def around(request: Any, deliver: Any) -> Any:
        if request.url.host == host and request.url.path == split.path:
            fetched.append(str(request.url))
            return httpx.Response(404, text="no key set here", request=request)
        return deliver()

    tool = open_web_door(around=around)

    response = answer_to(
        lambda: logged_in(tool, door_contract, provider, person_holding(provider, "DEAN")),
        "a session whose key set the tool could not fetch",
    )

    assert fetched, (
        f"The tool never fetched the configured key set at {web_jwks_url!r}, so whatever it "
        "answered was decided before any fetch failed and this test is looking at the wrong "
        "refusal (`docs/MISTAKES.md` entry 3)."
    )
    refused(response, door_contract, "a session whose key set could not be fetched")
    assert response.text.strip(), (
        "The refusal has an empty body, so 'the address is not in it' is true of a page with "
        "nothing in it and says nothing about what the tool prints when it has something to say."
    )
    assert host not in response.text, (
        f"The refusal page names {host!r}, the host of the key set URL the tool fetches "
        f"server-side ({web_jwks_url!r}). Body begins {response.text[:400]!r}. That address is a "
        "Compose service name: useless to the browser that received it, and the network map to "
        "anyone else."
    )


# ---------------------------------------------------------------------------
# `login_hint` on `GET /auth/oidc/login`. The developer test console links here
# with a `login_hint` so the mock provider's form pre-selects a person; the tool
# forwards it as OIDC Core 1.0 §3.1.2.1's presentational hint and nothing more.
# It must reach the authorization request, and it must never decide identity —
# which the `id_token` alone does.
# ---------------------------------------------------------------------------


def subject_of(person: Any) -> str:
    """The `sub` a seeded person signs in under, or a failure saying there is none."""
    subject = person.get("sub")
    assert isinstance(subject, str) and subject, (
        f"The published person {person!r} carries no `sub`, so there is no value to send as a "
        "`login_hint` or to reason about."
    )
    return subject


def begin_with_hint(tool: Any, contract: Any, login_hint: str) -> dict[str, str]:
    """Start a web login carrying `login_hint`, and read the request the tool built."""
    response = tool.get(contract.oidc_login, params={"login_hint": login_hint})
    return query_of(redirect_target(response, f"a web login was started with login_hint {login_hint!r}"))


def logged_in_with_hint(
    tool: Any, contract: Any, provider: Any, login_hint: str, person: Any
) -> Any:
    """One whole web login begun with `login_hint`, signed in as `person`.

    The hint and the person are chosen separately on purpose: the security test
    below starts the flow hinting one identity and signs in as another, which is
    the whole question of whether the hint decides who is signed in.
    """
    parameters = begin_with_hint(tool, contract, login_hint)
    return complete(tool, contract, sign_in(provider, parameters, person))


def test_the_login_endpoint_forwards_login_hint_to_the_authorization_request(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """Criterion: `login_hint` is passed through to the provider's authorization request.

    **Dies if the hint is dropped**, and its pair — a login begun without one —
    **dies if the tool injects a constant `login_hint` of its own.** Both directions
    matter: the console sends the hint so the provider's form can pre-select a
    person, and a tool that forwarded a fixed value instead would pre-select the
    wrong one for every developer. OIDC Core 1.0 §3.1.2.1 spells it `login_hint`.
    """
    hint = subject_of(person_holding(provider, "DEAN"))

    with_hint = begin_with_hint(tool, door_contract, hint)
    assert with_hint.get("login_hint") == hint, (
        f"A web login started with `login_hint={hint!r}` built an authorization request carrying "
        f"`login_hint` {with_hint.get('login_hint')!r}. E0's console links here with the subject to "
        "pre-select, and the tool forwards it verbatim as OIDC Core 1.0 §3.1.2.1's `login_hint`."
    )

    without_hint = begin(tool, door_contract)
    assert not without_hint.get("login_hint"), (
        f"A web login started with no `login_hint` still carried `login_hint` "
        f"{without_hint.get('login_hint')!r} to the provider. The hint is the caller's when it is "
        "sent and nothing when it is not — a constant here would pre-select somebody the developer "
        "never named."
    )


def test_a_login_hint_is_inert_to_the_landing_a_correct_login_reaches(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """Criterion: a login started with a `login_hint` behaves exactly as one without.

    **Dies if the hint changes the outcome of an otherwise identical flow.** The
    dean signs in both ways — hinted as herself and with no hint at all — and lands
    on the leadership view each time. The hint is presentational: it may change what
    the provider's form pre-selects, and nothing about the session the tool ends up
    with. This is the boundary pair for the security test below: that one proves the
    hint cannot override a *different* identity, and this proves it does not disturb
    the matching one.
    """
    dean = person_holding(provider, "DEAN")
    hint = subject_of(dean)

    hinted = logged_in_with_hint(tool, door_contract, provider, hint, dean)
    lands_on(hinted, door_contract, LEADERSHIP_VIEW)

    plain = logged_in(tool, door_contract, provider, dean)
    lands_on(plain, door_contract, LEADERSHIP_VIEW)


def test_a_login_hint_does_not_decide_which_identity_is_signed_in(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """**Dies if `login_hint` is trusted as the identity** rather than the `id_token`.

    The flow is begun hinting the dean and then signed in, at the provider, as the
    administrator. The session that comes back is the administrator's, so the tool
    must land on the admin view — the hint named the dean and it counts for nothing.
    A tool that read `login_hint` into any security decision would land on the
    leadership view here, granting a caller whatever they wrote in a query
    parameter. Identity is the verified `id_token`'s to state and the hint's never
    (§4.1, and E0-09 criterion 10 for why a caller-chosen role must not stick).

    The two views are distinct testids, and `lands_on` requires the admin one
    present *and* every other absent, so a page that carried both — the hint's and
    the token's — is wrong about the one it named.
    """
    dean_hint = subject_of(person_holding(provider, "DEAN"))
    administrator = person_holding(provider, "ADMIN")

    response = logged_in_with_hint(tool, door_contract, provider, dean_hint, administrator)

    lands_on(response, door_contract, ADMIN_VIEW)
