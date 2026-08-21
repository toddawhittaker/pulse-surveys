"""The tool's launch door: `POST /lti/login` and `POST /lti/launch` — ticket E0-18.

E0-18 PR 1 builds the *tool* side of an LTI 1.3 launch, which every previous
ticket deliberately did not: E0-14 built a platform that produces launches and
said in as many words that validating them was somebody else's work. This module
is that somebody. Everything below is asserted over HTTP against the application
`app.main:create_app()` returns, with the mock platform served in process through
the one seam E0-18 designs for it.

**What is deliberately not here.** E0-18's own boundary section gives E1 the
depth: replay windows, clock-skew tolerance, cookieless iframes, platform-side
state storage, provisioning, any `user` row for a mock subject, any session that
outlives the entry flow, and any purview computation. So there is no test below of
a replayed nonce, of a launch arriving twice, or of what a landing page would show
if it had content. What *is* here is the set E0-18's own acceptance criteria name —
"bad signature, wrong `aud`, unknown `iss`, unknown `deployment_id`, stale `exp`,
mismatched `state`, mismatched `nonce`" — one case each, because "absence of basic
state/nonce/signature checks is not tolerable even briefly".

**Every refusal is posed by changing exactly one thing** about a launch that is
otherwise the same launch as the happy path above it. That matters more here than
almost anywhere else in this suite: a 4xx is a 4xx, so a case that got three things
wrong at once would be satisfied by an implementation that checks any one of them,
and `docs/MISTAKES.md` entry 3 is precisely that failure. Where the one thing
cannot be changed on the token — the platform signs with a key nothing here holds —
it is changed on the *registration*, which is the other half of every comparison
the tool makes.

**The landing role comes from the verified token.** E0-18: "the landing role comes
from the verified token, not from the database", so the two happy paths below
assert that a Learner's launch lands on the student view and an Instructor's on the
instructor view, with the other four testids absent. Absent as well as present,
because a page carrying every view is a page that is right about none of them.

**Four things arrived in the third review round**, and they are the last three
sections of this module. One door reads one roles vocabulary, which needs launches
carrying claims no seeded person produces — so those are signed by `suite_key_set`
against a registration pointing at it, with a control test that says the machinery
itself is accepted. The login cookie carries `Secure` outside development and does
not carry it inside. A `state` or a `nonce` that is not ASCII is refused rather
than crashed, and the refusal still burns the single-use cookie. And no refusal
page repeats the server-side key set address the tool failed to reach.

**Where the values come from.** Nothing about the mock platform is transcribed
here. The issuer, client ID and deployment ID are read out of the OIDC
third-party-initiated login request its launch page publishes — the same source
`tests/integration/test_mock_lms_launch.py` uses, and the only place a platform
announces itself — and the key set URL comes out of its discovery document. Which
launch belongs to a student and which to an instructor is learned by minting them
and reading the LIS roles claim, rather than by naming a seeded user identifier.
"""

from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# The mock platform's configuration surface, from `mock-lms/app/config.py`. Set so
# that the platform's launch form posts at *this* tool and its authorization
# endpoint accepts this tool's `redirect_uri` — `resolve_launch` compares that
# value exactly, so the tool has to build it from `PUBLIC_BASE_URL` and the two
# have to agree.
MOCK_LMS_TOOL_LOGIN_URL_VARIABLE = "MOCK_LMS_TOOL_LOGIN_URL"
MOCK_LMS_TOOL_LAUNCH_URL_VARIABLE = "MOCK_LMS_TOOL_LAUNCH_URL"
MOCK_LMS_ISSUER_VARIABLE = "MOCK_LMS_ISSUER"

# Where the tool is configured to send a browser to begin the launch. **Chosen so
# that no implementation could arrive at it by accident**: E0-18 puts the
# platform's browser-facing authorization endpoint in a settings field because
# `lti_platform` has no column for it, and a redirect built from anything else —
# the issuer plus a guessed path, a constant in the source — would agree with the
# real mock and disagree with this. `.invalid` is reserved by RFC 2606.
CONFIGURED_AUTHORIZATION_ENDPOINT = "http://lti-platform.invalid/e0-18-configured-authorize"

# An issuer no `lti_platform` row will ever carry. Used for the login endpoint's
# unknown-issuer case and for the second platform instance whose launches nobody
# registered.
UNREGISTERED_ISSUER = "http://platform-nobody-registered.invalid"

# The LTI 1.3 claims this module reads. Spelled as the specification spells them,
# for the reason `test_mock_lms_launch.py` gives: a claim under a different name is
# a claim no conformant library reads.
LTI_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/"
DEPLOYMENT_ID_CLAIM = LTI_CLAIM + "deployment_id"
ROLES_CLAIM = LTI_CLAIM + "roles"

# The two LIS v2 membership roles E0-18's landing rule dispatches on. Not this
# file's choice: LTI 1.3 draws roles from the LIS vocabularies, and the mock emits
# these URIs because SPEC §7.3 asks for strict core.
MEMBERSHIP_ROLE = "http://purl.imsglobal.org/vocab/lis/v2/membership#"
INSTRUCTOR_ROLE_URI = f"{MEMBERSHIP_ROLE}Instructor"
LEARNER_ROLE_URI = f"{MEMBERSHIP_ROLE}Learner"

# A third role from the same LIS vocabulary, which E0-18 gives this door no view
# for. It is a real membership role a real LMS emits — a mentor is a parent or an
# advisor watching a learner — so a launch carrying it is well formed and names
# somebody this system has nothing to show. Used for the no-recognised-role case.
MENTOR_ROLE_URI = f"{MEMBERSHIP_ROLE}Mentor"

# The roles SPEC §2 gives the **web** door, spelled as `test_web_login_door.py`
# spells them. They appear in this module only as values to smuggle *into* a
# launch: they are what an LMS administrator would name if the launch door read
# the web door's vocabulary. Each one is checked against the roles the provider
# actually publishes before it is used, so this is a live vocabulary rather than
# three strings this file invented (`docs/MISTAKES.md` entry 3).
WEB_DOOR_ROLES = ("CARE", "VP_ACADEMICS", "ADMIN")

# `ENVIRONMENT`, spelled as `tests/unit/test_docs_exposure.py` spells it, and the
# two values that matter: the one a laptop carries and the one a deployment does.
ENVIRONMENT_VARIABLE = "ENVIRONMENT"
DEVELOPMENT = "development"
PRODUCTION = "production"

# The cookie attribute that keeps a browser from sending the launch cookie over
# plain HTTP, spelled as RFC 6265 §4.1.2.5 spells it, lowercased at the comparison
# because a `Set-Cookie` attribute name is case-insensitive.
SECURE_ATTRIBUTE = "secure"

# A `state` that is well formed as a form field and not representable as ASCII.
# `secrets.compare_digest` raises `TypeError` rather than answering `False` when
# either side is a `str` outside ASCII, so this is the value that separates "the
# tool compared and refused" from "the tool crashed on the way to comparing".
NON_ASCII_STATE = "é"
NON_ASCII_NONCE = "é"

# What each of those two lands on, per E0-18: "Learner → student empty view,
# Instructor → instructor empty view".
STUDENT_VIEW = "pulse-landing-student"
INSTRUCTOR_VIEW = "pulse-landing-instructor"

# How far back the platform's clock is wound to mint a launch that is certainly
# expired, and how far back to mint one that is certainly not. The first is longer
# than any `id_token` lifetime a platform would issue; the second is short enough
# that the token is still inside its own window. **The pair is the point**: without
# the second, a refusal below would be evidence that winding the clock breaks a
# launch rather than evidence that the tool checks `exp`.
CERTAINLY_EXPIRED_SECONDS = 3600
CERTAINLY_STILL_VALID_SECONDS = 30


@pytest.fixture
def platform(mock_platforms: Any, door_contract: Any) -> Any:
    """The mock platform, pointed at this tool's own login and launch URLs.

    Both have to be set. `MOCK_LMS_TOOL_LOGIN_URL` is where its launch form posts,
    which is how a browser reaches `/lti/login` at all; `MOCK_LMS_TOOL_LAUNCH_URL`
    is what `resolve_launch` compares the tool's `redirect_uri` against, exactly,
    which is what makes "the tool builds its redirect URI from `PUBLIC_BASE_URL`" a
    property the platform itself enforces rather than one only a test believes.
    """
    return mock_platforms(
        {
            MOCK_LMS_TOOL_LOGIN_URL_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.lti_login}"
            ),
            MOCK_LMS_TOOL_LAUNCH_URL_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.lti_launch}"
            ),
        }
    )


@pytest.fixture
def jwks_url(platform: Any) -> str:
    """Where the platform publishes the key set a launch has to verify against.

    Out of the discovery document, absolute, because that is the value a tool
    stores in `lti_platform.jwks_url` and fetches server-side. The host in it is
    also what routes the tool's fetch back into the in-process mock, so a door that
    fetched from anywhere else reaches no mock at all and says so.
    """
    document = platform.discovery()
    advertised = (document or {}).get("jwks_uri")
    assert isinstance(advertised, str) and advertised, (
        "The mock platform's discovery document advertises no `jwks_uri` (it carries "
        f"{sorted(document or {})}). That URL is what `lti_platform.jwks_url` holds and what the "
        "tool fetches to verify a launch signature, so without it there is nothing to register."
    )
    return advertised


@pytest.fixture
def registration(platform: Any, jwks_url: str, register_platform: Any) -> Any:
    """The mock platform, registered in `lti_platform` and `lti_deployment`."""
    return register_platform(platform.require_offers()[0], jwks_url)


@pytest.fixture
def open_launch_door(
    tool_doors: Any, door_contract: Any, platform: Any, registration: Any, jwks_url: str
) -> Any:
    """Build the tool for this platform, with settings a test may override.

    A factory rather than one instance, for the same reason `open_web_door` is one:
    three of the cases below are properties of an application built differently —
    one whose `ENVIRONMENT` is a deployment's, and one whose key-set fetch is
    answered by something other than the platform.
    """
    names = door_contract.settings

    def build(*, around: Any = None, environment: str | None = None, **overrides: str) -> Any:
        values = {
            names["public_base_url"]: door_contract.public_base_url,
            names["lti_authorization_endpoint"]: CONFIGURED_AUTHORIZATION_ENDPOINT,
        }
        values.update({names[key]: value for key, value in overrides.items()})
        if environment is not None:
            values[ENVIRONMENT_VARIABLE] = environment
        return tool_doors(values, {urlsplit(jwks_url).hostname: platform}, around=around)

    return build


@pytest.fixture
def tool(open_launch_door: Any) -> Any:
    """The application, configured for this platform and able to reach it in process."""
    return open_launch_door()


@pytest.fixture
def registration_naming_this_suites_key(
    platform: Any, suite_key_set: Any, register_platform: Any
) -> Any:
    """The platform, registered against **this suite's** key set rather than its own.

    Used instead of `registration`, never beside it: two rows registering one
    issuer would leave the door choosing between them, and which one it chose
    would decide the result of every test below.
    """
    return register_platform(platform.require_offers()[0], suite_key_set.jwks_url)


@pytest.fixture
def tool_verifying_against_this_suites_key(
    tool_doors: Any,
    door_contract: Any,
    registration_naming_this_suites_key: Any,
    suite_key_set: Any,
) -> Any:
    """The tool, whose registration points its signature check at `suite_key_set`.

    Only the key set's host is mounted. That is deliberate: the launch door's one
    server-side fetch is the key set named by the registration it resolved, so a
    door reaching any other address fails loudly here instead of being quietly
    served the platform's real keys.
    """
    return tool_doors(
        {
            door_contract.settings["public_base_url"]: door_contract.public_base_url,
            door_contract.settings["lti_authorization_endpoint"]: CONFIGURED_AUTHORIZATION_ENDPOINT,
        },
        {suite_key_set.host: suite_key_set},
    )


@pytest.fixture
def web_vocabulary(mock_idps: Any) -> tuple[str, frozenset[str]]:
    """The claim name and the role spellings the **web** door reads, from the provider.

    Read off the mock provider's published registration document (ADR 0058) rather
    than written down here, and this is the whole reason the tests below mean
    anything. A refusal is a refusal: if this module smuggled a claim name no door
    reads, a launch carrying it would be refused for carrying no role at all, and
    the test would report that as "the launch door ignores the web vocabulary"
    (`docs/MISTAKES.md` entry 3). The claim asserted here is the one
    `test_web_login_door.py::test_the_care_office_lands_on_the_care_view` proves
    the web door honours.
    """
    provider = mock_idps()
    published = frozenset(
        role for user in provider.published_users() for role in (user.get("roles") or [])
    )
    return provider.roles_claim_name(), published


def offer_for_role(platform: Any, role_uri: str) -> Any:
    """The launch the platform's page offers whose signed roles claim carries `role_uri`.

    Found by minting rather than by naming a seeded user, so this module holds no
    copy of `mock-lms/app/seed.py`'s identifiers and cannot go stale against a
    reseeding. The roles claim in the signed token is the ground truth: E0-18's
    landing rule reads the *verified* token, so the offer's own parameters — which
    carry no roles — could not answer this question anyway.
    """
    seen: list[tuple[str | None, Any]] = []
    for offer in platform.require_offers():
        launch = platform.mint(offer)
        roles = launch.claims.get(ROLES_CLAIM) or []
        seen.append((offer.parameters.get("login_hint"), roles))
        if role_uri in roles:
            return offer
    pytest.fail(
        f"No launch the mock platform offers carries the role {role_uri!r}. What it offers: "
        f"{seen}. E0-18 needs a student launch and an instructor launch, and E0-14's criterion 7 "
        "is that the platform provides both."
    )


def initiate(tool: Any, contract: Any, offer: Any, **overrides: str) -> Any:
    """Post the platform's launch form at the tool, the way the browser would."""
    return tool.post(contract.lti_login, data={**offer.parameters, **overrides})


def redirect_target(response: Any, purpose: str) -> str:
    """The `Location` of a redirect, or a failure saying what came back instead."""
    assert response.status_code in (302, 303, 307), (
        f"The tool answered {response.status_code} rather than a redirect when {purpose}. Body "
        f"begins {response.text[:300]!r}. E0-18: '`POST /lti/login` ... Answers a 302 to the "
        "platform's authorization endpoint'."
    )
    location = response.headers.get("location")
    assert location, (
        f"The tool answered {response.status_code} with no `Location` header when {purpose}, so "
        "there is nowhere for a browser to go."
    )
    return location


def query_of(url: str) -> dict[str, str]:
    """The query parameters of a URL, as a mapping."""
    return dict(parse_qsl(urlsplit(url).query))


def authorize(platform: Any, parameters: dict[str, str]) -> tuple[str, str | None, str | None]:
    """Answer the tool's authorization request at the platform, as a browser would.

    The parameters are the tool's own, taken off its redirect, so the token that
    comes back carries the tool's `nonce` and the platform hands back the tool's
    `state`. That is what makes the launch below the same launch a browser
    produces, and it is what a launch minted independently could never be.
    """
    path = platform.endpoint(
        "authorization_endpoint",
        ("auth",),
        "receives the tool's authorization request and answers with a signed `id_token`",
    )
    if path in platform.paths("POST"):
        response = platform.client.post(path, data=parameters)
    else:
        response = platform.client.get(path, params=parameters)
    return platform.read_authorization_response(response, path)


def land(tool: Any, contract: Any, id_token: str, state: str | None) -> Any:
    """Deliver a launch to the tool's launch endpoint."""
    body = {"id_token": id_token}
    if state is not None:
        body["state"] = state
    return tool.post(contract.lti_launch, data=body)


def launched(tool: Any, contract: Any, platform: Any, offer: Any) -> Any:
    """One whole launch, from the platform's form to the tool's landing page."""
    started = initiate(tool, contract, offer)
    parameters = query_of(redirect_target(started, "a registered platform began a launch"))
    id_token, state, _ = authorize(platform, parameters)
    return land(tool, contract, id_token, state)


def views_in(response: Any, contract: Any) -> list[str]:
    """Which of the five landing testids the body carries."""
    return [testid for testid in contract.landing_testids if testid in response.text]


def lands_on(response: Any, contract: Any, expected: str) -> None:
    """The response is the landing page for `expected`, and for nothing else."""
    assert response.status_code == 200, (
        f"The launch was answered {response.status_code} rather than 200. Body begins "
        f"{response.text[:400]!r}."
    )
    found = views_in(response, contract)
    assert found == [expected], (
        f"The landing page carries {found or 'no landing testid at all'}, and E0-18 has this "
        f"launch land on `{expected}`. Every other view's testid has to be absent as well as this "
        "one present: a page carrying several is a page that is right about none of them, and it "
        "is what a template rendering all five behind a condition that never fires looks like."
    )


def refused(response: Any, contract: Any, what: str) -> None:
    """The tool refused, and rendered nobody's landing page while doing it."""
    assert 400 <= response.status_code < 500, (
        f"The tool answered {response.status_code} to {what}. E0-18 requires a 4xx: this is auth "
        f"code, and 'absence of basic state/nonce/signature checks is not tolerable even "
        f"briefly'. Body begins {response.text[:400]!r}."
    )
    found = views_in(response, contract)
    assert not found, (
        f"The tool refused {what} with {response.status_code} and still rendered {found}. A "
        "refusal that serves a landing page has admitted the launch and merely said so in the "
        "status line."
    )


def re_signed_launch(
    tool: Any,
    contract: Any,
    platform: Any,
    keys: Any,
    claims_in_token: Any,
    adjust: Any,
) -> Any:
    """A whole launch whose `id_token` was re-signed after `adjust` changed its claims.

    Every part of the flow is the real one — the platform's launch form, the tool's
    own authorization request, the platform's signed answer — and the token
    delivered at the end carries that answer's claims with one thing changed. It is
    signed by `suite_key_set`, which is the key set the registration in front of
    this tool names, so the signature, the issuer, the audience, the deployment,
    the nonce, the state and the expiry are all still correct.

    The one thing changed is the roles vocabulary, which is what makes a 4xx below
    mean the vocabulary. The control that says so is the first test in the section
    that uses this helper: the same flow with the claims re-signed unchanged, which
    is required to land on the student view.
    """
    offer = offer_for_role(platform, LEARNER_ROLE_URI)
    started = initiate(tool, contract, offer)
    parameters = query_of(redirect_target(started, "a registered platform began a launch"))
    id_token, state, _ = authorize(platform, parameters)

    claims = dict(claims_in_token(id_token))
    assert claims.get(ROLES_CLAIM), (
        f"The launch the platform signed carries no `{ROLES_CLAIM}` (it carries "
        f"{sorted(claims)}), so there is no roles claim for this test to change and nothing it "
        "says about which vocabulary the door reads would mean anything."
    )
    adjusted = adjust(dict(claims))
    signed = keys.sign(adjusted)
    assert signed != id_token, "Re-signing produced the platform's own token, so nothing changed."
    return land(tool, contract, signed, state)


# ---------------------------------------------------------------------------
# The landing pages. E0-18: a launch lands on the view its verified roles name.
# ---------------------------------------------------------------------------


def test_a_learner_launch_lands_on_the_student_view(
    tool: Any, door_contract: Any, platform: Any
) -> None:
    """The whole door, end to end, for the role SPEC §2 gives the launch door only.

    Every part of the flow is real: the platform's own launch form is posted at
    `/lti/login`, the tool's redirect is answered at the platform's authorization
    endpoint, and the signed `id_token` that comes back is delivered to
    `/lti/launch`. Nothing is minted independently, so this fails if any link in
    the chain is missing — which is the point of having it before the refusals.
    """
    response = launched(tool, door_contract, platform, offer_for_role(platform, LEARNER_ROLE_URI))

    lands_on(response, door_contract, STUDENT_VIEW)


def test_an_instructor_launch_lands_on_the_instructor_view(
    tool: Any, door_contract: Any, platform: Any
) -> None:
    """The same door, the other role, and the pair is what makes either mean anything.

    A tool that rendered one view for every launch satisfies the test above on its
    own. E0-18's landing rule is a *dispatch* on the verified roles claim, and a
    dispatch is only observable across two inputs.
    """
    response = launched(
        tool, door_contract, platform, offer_for_role(platform, INSTRUCTOR_ROLE_URI)
    )

    lands_on(response, door_contract, INSTRUCTOR_VIEW)


# ---------------------------------------------------------------------------
# `POST /lti/login` — the third-party-initiated login.
# ---------------------------------------------------------------------------


def test_the_login_endpoint_refuses_an_issuer_no_row_registers(
    tool: Any, door_contract: Any, platform: Any
) -> None:
    """Criterion: "unknown issuer is a 4xx page, not a silent 302".

    **Dies if the `lti_platform` lookup is dropped**, which is the shape this takes
    when the redirect is assembled out of the request's own parameters — every
    field a platform needs is right there in the initiation request, so a login
    endpoint that never opens the database works perfectly against the one platform
    anybody tests with and redirects a browser to whoever asked.

    Both halves are asserted. A 4xx alone would be satisfied by a tool that
    redirected *and* returned an error status; the absence of a `Location` is what
    says no browser was sent anywhere.
    """
    offer = platform.require_offers()[0]

    response = initiate(tool, door_contract, offer, iss=UNREGISTERED_ISSUER)

    assert 400 <= response.status_code < 500, (
        f"The tool answered {response.status_code} to a login initiation from "
        f"{UNREGISTERED_ISSUER!r}, which no `lti_platform` row registers. Body begins "
        f"{response.text[:300]!r}."
    )
    assert not response.headers.get("location"), (
        f"The tool sent the browser to {response.headers.get('location')!r} for an unregistered "
        "issuer. E0-18: 'unknown issuer is a 4xx page, not a silent 302' — a redirect built from "
        "an unauthenticated request's own parameters is an open redirect with the launch "
        "protocol's name on it."
    )


def test_the_login_redirect_goes_to_the_configured_authorization_endpoint(
    tool: Any, door_contract: Any, platform: Any
) -> None:
    """Criterion: the redirect targets the platform's authorization endpoint.

    **Dies if the endpoint is derived rather than configured** — assembled from the
    issuer plus a guessed path, or written into the source. E0-23 put service
    addresses out of `lti_platform` until E1, so E0-18's stand-in is a settings
    field, and the value used here is one nothing could arrive at by any other
    route.
    """
    offer = platform.require_offers()[0]

    location = redirect_target(
        initiate(tool, door_contract, offer), "a registered platform began a launch"
    )

    split = urlsplit(location)
    without_query = f"{split.scheme}://{split.netloc}{split.path}"
    assert without_query == CONFIGURED_AUTHORIZATION_ENDPOINT, (
        f"The tool redirected to {without_query!r} and the configured authorization endpoint is "
        f"{CONFIGURED_AUTHORIZATION_ENDPOINT!r}. E0-18 makes that endpoint a setting because "
        "`lti_platform` has no column for it; a value that agrees with the platform by "
        "construction would pass a test written against the real address and would not be "
        "configuration."
    )


def test_the_login_redirect_names_the_registered_client_and_the_tools_own_launch_url(
    tool: Any, door_contract: Any, platform: Any, registration: Any
) -> None:
    """Criterion: the authorization request carries `client_id` and `redirect_uri`.

    **Dies if either is echoed from the request instead of resolved.** Both are
    present in the initiation request the platform posts, so echoing them is the
    natural mistake and is invisible against a correctly configured stack. The
    `client_id` sent in is deliberately *not* the registered one, so a tool that
    echoes fails here and a tool that reads the row does not; the `redirect_uri`
    has to be `PUBLIC_BASE_URL` plus the launch path, which is the comparison
    `resolve_launch` makes exactly and which a value taken from the request's
    `target_link_uri` would also satisfy — so it is asserted against the setting.
    """
    offer = platform.require_offers()[0]
    impostor = "a-client-id-the-request-supplied-and-nothing-registered"

    location = redirect_target(
        initiate(tool, door_contract, offer, client_id=impostor),
        "a registered platform began a launch",
    )
    parameters = query_of(location)

    assert parameters.get("client_id") == registration.client_id, (
        f"The authorization request names client {parameters.get('client_id')!r}. The registered "
        f"client for this issuer is {registration.client_id!r} and the initiation request carried "
        f"{impostor!r} — so the tool took the caller's word for which tool it is."
    )
    expected_redirect = f"{door_contract.public_base_url}{door_contract.lti_launch}"
    assert parameters.get("redirect_uri") == expected_redirect, (
        f"The authorization request's `redirect_uri` is {parameters.get('redirect_uri')!r} and the "
        f"tool's own launch URL is {expected_redirect!r}. E0-18: the mock 'compares `redirect_uri` "
        "exactly against its configured `MOCK_LMS_TOOL_LAUNCH_URL`, so the tool must build it from "
        "its own public base URL setting'."
    )


def test_the_login_redirect_echoes_the_two_hints_the_platform_sent(
    tool: Any, door_contract: Any, platform: Any
) -> None:
    """Criterion: the authorization request carries `login_hint` and `lti_message_hint`.

    **Dies if either is dropped.** They are the platform's own opaque values — who
    is launching and from which placement — and a tool that does not return them
    gets a launch for whoever the platform guesses, or none at all. Nothing else in
    this module would notice: the mock refuses such a request, so the failure
    surfaces as "no `id_token` came back", which reads as a broken platform.
    """
    offer = platform.require_offers()[0]

    parameters = query_of(
        redirect_target(
            initiate(tool, door_contract, offer), "a registered platform began a launch"
        )
    )

    for name in ("login_hint", "lti_message_hint"):
        expected = offer.parameters.get(name)
        assert expected, (
            f"The mock platform's launch form carries no `{name}`, so this test has nothing to "
            f"check it was echoed. It publishes {sorted(offer.parameters)}."
        )
        assert parameters.get(name) == expected, (
            f"The initiation request carried `{name}` {expected!r} and the tool's authorization "
            f"request carries {parameters.get(name)!r}. Both hints are the platform's values and "
            "the tool's whole obligation is to hand them back unchanged."
        )


def test_two_logins_carry_a_fresh_state_and_a_fresh_nonce(
    tool: Any, door_contract: Any, platform: Any
) -> None:
    """Criterion: `state` and `nonce` are fresh per login initiation.

    **Dies against a constant**, which is what a value read out of configuration or
    computed from the request looks like. A fixed `state` is no cross-site request
    forgery defence at all, and a fixed `nonce` makes every launch a replay of the
    last — and neither is visible from a single flow, because one launch with a
    constant nonce validates exactly like one with a fresh one.
    """
    offer = platform.require_offers()[0]

    first = query_of(
        redirect_target(initiate(tool, door_contract, offer), "the first login initiation")
    )
    second = query_of(
        redirect_target(initiate(tool, door_contract, offer), "the second login initiation")
    )

    for name in ("state", "nonce"):
        assert first.get(name), (
            f"The tool's authorization request carries no `{name}` (it carries {sorted(first)}). "
            "Without it there is nothing for the launch endpoint to compare against, and every "
            "state and nonce assertion below is about a value that does not exist."
        )
        assert first[name] != second.get(name), (
            f"Two login initiations carried the same `{name}` ({first[name]!r}). A constant "
            "`state` defends against nothing and a constant `nonce` makes every launch a replay "
            "of the last; both validate perfectly in a single flow."
        )


# ---------------------------------------------------------------------------
# `POST /lti/launch` — one refusal per check, one changed thing per refusal.
# ---------------------------------------------------------------------------


def test_a_launch_whose_payload_was_altered_after_signing_is_refused(
    tool: Any, door_contract: Any, platform: Any, tamper_with: Any
) -> None:
    """Criterion: bad signature. **Dies if the signature is not verified at all.**

    The token is re-encoded from altered claims and keeps its original signature,
    so it is well formed in every respect except the arithmetic — which is the only
    thing being asked about. A token corrupted a character at a time is usually no
    longer JSON, so a tool would refuse it at the decoder and this test would call
    that a signature check.

    The claim altered is `sub`, which changes who the launch is for and nothing
    else: every other check the tool makes still passes, so a 4xx here can only be
    the signature.
    """
    offer = offer_for_role(platform, LEARNER_ROLE_URI)
    started = initiate(tool, door_contract, offer)
    parameters = query_of(redirect_target(started, "a registered platform began a launch"))
    id_token, state, _ = authorize(platform, parameters)

    response = land(tool, door_contract, tamper_with(id_token), state)

    refused(response, door_contract, "a launch whose payload was altered after signing")


def test_a_launch_whose_audience_is_not_the_registered_client_is_refused(
    tool: Any, door_contract: Any, platform: Any, registration: Any
) -> None:
    """Criterion: wrong `aud`. **Dies if the `aud` check is dropped.**

    Posed by moving the registration rather than the token, because the platform
    signs `aud` from its own configuration and nothing here holds its key. The
    launch is minted through the tool's own login, so its `state`, `nonce`, `iss`,
    `deployment_id`, signature and `exp` are all still correct at the moment it is
    delivered; the single difference from the happy path is that the row now
    registers a different client. A 4xx can therefore only be the audience.

    A tool that caches the registration for the life of the process answers 200
    here. That is a finding rather than a false red: E0-18 registers no cache, and
    a launch validated against a registration that has since changed is validated
    against nothing anybody can see.
    """
    offer = offer_for_role(platform, LEARNER_ROLE_URI)
    started = initiate(tool, door_contract, offer)
    parameters = query_of(redirect_target(started, "a registered platform began a launch"))
    id_token, state, _ = authorize(platform, parameters)

    registration.move_the_registered_client_id_to("a-different-tool-entirely")
    response = land(tool, door_contract, id_token, state)

    refused(response, door_contract, "a launch whose `aud` is not the registered client")


def test_a_launch_from_a_platform_no_row_registers_is_refused(
    tool: Any, door_contract: Any, platform: Any, mock_platforms: Any
) -> None:
    """Criterion: unknown `iss`. **Dies if the tool trusts any well-formed token.**

    A second platform instance, with an issuer nothing registers, signing with a
    key set nothing published. The `state` delivered with it is one the tool really
    did issue, so the refusal is not the state check standing in for the
    registration lookup — which is the near miss that matters, because a tool whose
    only real check is `state` would pass a version of this test that reused a
    stranger's state too.

    Several of the tool's checks would each refuse this token, and that is the
    correct shape for this one case: a launch from an unregistered issuer is one
    the tool cannot verify anything about, so what is asserted is that no path
    admits it.
    """
    stranger = mock_platforms(
        {
            MOCK_LMS_ISSUER_VARIABLE: UNREGISTERED_ISSUER,
            MOCK_LMS_TOOL_LOGIN_URL_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.lti_login}"
            ),
            MOCK_LMS_TOOL_LAUNCH_URL_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.lti_launch}"
            ),
        }
    )
    started = initiate(tool, door_contract, platform.require_offers()[0])
    state = query_of(redirect_target(started, "a registered platform began a launch")).get("state")

    foreign = stranger.mint()
    assert foreign.claims.get("iss") == UNREGISTERED_ISSUER, (
        f"The second platform signed a launch whose `iss` is {foreign.claims.get('iss')!r} rather "
        f"than the configured {UNREGISTERED_ISSUER!r}, so it is not the unregistered issuer this "
        "test is about."
    )

    response = land(tool, door_contract, foreign.id_token, state)

    refused(response, door_contract, "a launch from a platform no `lti_platform` row registers")


def test_a_launch_naming_a_deployment_no_row_registers_is_refused(
    tool: Any,
    door_contract: Any,
    platform: Any,
    registration: Any,
    claims_in_token: Any,
) -> None:
    """Criterion: unknown `deployment_id`. **Dies if the deployment claim is never read.**

    The most invisible of the seven, because `lti_deployment` is a table nothing
    else in E0 reads: a tool that resolves the platform by `iss` and stops has a
    working launch door for every test anybody writes. A deployment is what
    distinguishes one installation of a tool in an LMS from another, and a launch
    naming an unregistered one is a launch from a placement this tool was never
    installed into.

    One thing changes from the happy path: the registered deployment identifier.
    """
    offer = offer_for_role(platform, LEARNER_ROLE_URI)
    started = initiate(tool, door_contract, offer)
    parameters = query_of(redirect_target(started, "a registered platform began a launch"))
    id_token, state, _ = authorize(platform, parameters)

    claimed = claims_in_token(id_token).get(DEPLOYMENT_ID_CLAIM)
    assert claimed == registration.deployment_id, (
        f"The launch names deployment {claimed!r} and the registered one is "
        f"{registration.deployment_id!r}, so they already disagree and moving the row would prove "
        "nothing about the tool."
    )

    registration.move_the_registered_deployment_to("a-deployment-of-some-other-installation")
    response = land(tool, door_contract, id_token, state)

    refused(response, door_contract, "a launch naming a deployment no `lti_deployment` row holds")


def test_a_launch_whose_token_expired_an_hour_ago_is_refused(
    tool: Any, door_contract: Any, platform: Any, wind_the_clock_back: Any
) -> None:
    """Criterion: stale `exp`. **Dies if `exp` is never compared to now.**

    The token is genuinely expired and genuinely signed: the platform's clock is
    wound back an hour while it mints, so `iat` and `exp` are both in the past and
    the signature covers them. Nothing else about the launch differs from the happy
    path — same `state`, same `nonce`, same registration, same key.

    Its pair is the next test, and neither is worth much alone.
    """
    offer = offer_for_role(platform, LEARNER_ROLE_URI)
    started = initiate(tool, door_contract, offer)
    parameters = query_of(redirect_target(started, "a registered platform began a launch"))
    with wind_the_clock_back(CERTAINLY_EXPIRED_SECONDS):
        id_token, state, _ = authorize(platform, parameters)

    response = land(tool, door_contract, id_token, state)

    refused(response, door_contract, "a launch whose `id_token` expired an hour ago")


def test_a_launch_minted_seconds_ago_is_still_accepted(
    tool: Any, door_contract: Any, platform: Any, wind_the_clock_back: Any
) -> None:
    """The near miss for the test above: a token that is old and not yet expired.

    **This is what makes the refusal above mean "expired" rather than "minted under
    a wound-back clock".** Without it, an implementation that refused any token
    whose `iat` was not this instant — no clock skew tolerance at all, which E1 is
    the ticket for — would pass the expiry test while being wrong about the thing
    it claims to check, and so would a tool that refused every launch minted this
    way for some reason nobody has looked at.

    The wind-back is short enough to sit inside any `id_token` lifetime a platform
    would issue, so this token is valid by every reading.
    """
    offer = offer_for_role(platform, LEARNER_ROLE_URI)
    started = initiate(tool, door_contract, offer)
    parameters = query_of(redirect_target(started, "a registered platform began a launch"))
    with wind_the_clock_back(CERTAINLY_STILL_VALID_SECONDS):
        id_token, state, _ = authorize(platform, parameters)

    response = land(tool, door_contract, id_token, state)

    lands_on(response, door_contract, STUDENT_VIEW)


def test_a_launch_carrying_a_state_the_tool_never_issued_is_refused(
    tool: Any, door_contract: Any, platform: Any
) -> None:
    """Criterion: mismatched `state`. **Dies if `state` is accepted without comparison.**

    The token is the one the tool's own login initiation produced and is correct in
    every claim; only the `state` posted beside it is a value the tool never sent.
    A tool that reads `state` and does not compare it — or compares it to itself —
    passes every other test in this module.
    """
    offer = offer_for_role(platform, LEARNER_ROLE_URI)
    started = initiate(tool, door_contract, offer)
    parameters = query_of(redirect_target(started, "a registered platform began a launch"))
    id_token, _, _ = authorize(platform, parameters)

    response = land(tool, door_contract, id_token, "a-state-this-tool-never-issued")

    refused(response, door_contract, "a launch carrying a `state` the tool never issued")


def test_a_launch_carrying_no_state_at_all_is_refused(
    tool: Any, door_contract: Any, platform: Any
) -> None:
    """The absent case, which an override cannot express and a comparison can miss.

    A tool that compares `state` only when one arrives has no defence at all: an
    attacker simply omits it. This is a different mutation from the test above —
    `if state and state != expected` passes that one and fails this one — so it is
    a case of its own rather than a parameter of that one.
    """
    offer = offer_for_role(platform, LEARNER_ROLE_URI)
    started = initiate(tool, door_contract, offer)
    parameters = query_of(redirect_target(started, "a registered platform began a launch"))
    id_token, _, _ = authorize(platform, parameters)

    response = land(tool, door_contract, id_token, None)

    refused(response, door_contract, "a launch carrying no `state` at all")


def test_a_launch_whose_nonce_is_not_the_one_the_tool_sent_is_refused(
    tool: Any, door_contract: Any, platform: Any
) -> None:
    """Criterion: mismatched `nonce`. **Dies if the nonce is read and not compared.**

    The nonce is the tool's value; the platform's obligation is to put back
    whatever it was given, which `test_mock_lms_launch.py` proves it does. So a
    launch carrying a different nonce is produced by answering the tool's
    authorization request with one parameter changed — everything else, `state`
    included, is the tool's own — and the token is correctly signed over it.

    Without this the nonce is decoration: it is generated, sent, echoed and never
    looked at, and E1's replay work would be built on a value nothing compares.
    """
    offer = offer_for_role(platform, LEARNER_ROLE_URI)
    started = initiate(tool, door_contract, offer)
    parameters = query_of(redirect_target(started, "a registered platform began a launch"))
    assert parameters.get("nonce"), (
        "The tool's authorization request carries no `nonce`, so there is nothing for this test to "
        "substitute and nothing for the launch endpoint to compare."
    )

    id_token, state, _ = authorize(
        platform, {**parameters, "nonce": "a-nonce-the-tool-never-generated"}
    )
    response = land(tool, door_contract, id_token, state)

    refused(response, door_contract, "a launch whose `nonce` is not the one the tool sent")


# ---------------------------------------------------------------------------
# One door, one vocabulary. SPEC §2 gives Care, leadership and admin the web door
# *precisely so* the LMS cannot name those roles, and this is that rule at the
# navigation layer — E0-09 criterion 10's shape, one layer up from the assignment
# table. It is also the premise the Care sweep's exception argues from
# (`tests/unit/test_care_is_not_reachable_from_a_claim.py::EXCEPTIONS`).
# ---------------------------------------------------------------------------


def test_a_launch_re_signed_with_the_registered_key_is_still_accepted(
    tool_verifying_against_this_suites_key: Any,
    door_contract: Any,
    platform: Any,
    suite_key_set: Any,
    claims_in_token: Any,
) -> None:
    """The control for every re-signed case below, and they are worth nothing without it.

    The claims are the platform's own, unchanged, signed again by the key set this
    tool's registration names. If this lands on the student view then the machinery
    — the key, the served JWK Set, the `kid`, the re-encoding — produces launches
    this door accepts, and a refusal in the tests below can only be the one claim
    they changed. If it does *not*, every one of them is a red about the harness
    rather than about the door, and this is where that shows (`docs/MISTAKES.md`
    entry 3).
    """
    response = re_signed_launch(
        tool_verifying_against_this_suites_key,
        door_contract,
        platform,
        suite_key_set,
        claims_in_token,
        lambda claims: claims,
    )

    lands_on(response, door_contract, STUDENT_VIEW)


@pytest.mark.parametrize("web_role", WEB_DOOR_ROLES)
def test_a_launch_naming_a_web_door_role_and_no_lis_role_is_refused(
    tool_verifying_against_this_suites_key: Any,
    door_contract: Any,
    platform: Any,
    suite_key_set: Any,
    claims_in_token: Any,
    web_vocabulary: tuple[str, frozenset[str]],
    web_role: str,
) -> None:
    """**Dies if the launch door consults the web door's vocabulary.**

    SPEC §2 gives Care, leadership and admin a second way in *precisely so* that
    the LMS cannot name those roles: the person who administers the platform writes
    what an `id_token` says, and E0-09 criterion 10 is that no claim may produce a
    Care capability. This is that rule one layer up — at the navigation layer,
    where a launch door that read the web door's roles claim would let the same
    administrator put themselves on the Care screen by adding a claim to a launch.

    The launch is otherwise entirely correct: signed by the registered key set,
    the right issuer, audience, deployment, nonce, state and expiry. Its LIS roles
    claim is empty and it states a web-door role in the web door's own claim. There
    is no view this door may serve for it, so the only answer is a refusal — and
    `refused` requires that no landing testid at all appears, which covers the Care
    page and the other four together.

    The claim name and the role spelling are read off the provider's published
    registration document rather than written here, so this cannot pass by
    smuggling a claim nobody reads.
    """
    claim, published = web_vocabulary
    assert web_role in published, (
        f"The mock provider publishes nobody holding {web_role!r} (it publishes "
        f"{sorted(published)}), so this test is smuggling a role the web door never sees and a "
        "refusal below would say nothing about which vocabulary the launch door reads."
    )

    def adjust(claims: dict[str, Any]) -> dict[str, Any]:
        claims[ROLES_CLAIM] = []
        claims[claim] = [web_role]
        return claims

    response = re_signed_launch(
        tool_verifying_against_this_suites_key,
        door_contract,
        platform,
        suite_key_set,
        claims_in_token,
        adjust,
    )

    refused(
        response,
        door_contract,
        f"a launch whose LIS roles claim is empty and which states {web_role!r} in `{claim}`, the "
        "claim SPEC §2 gives the web door",
    )


def test_a_launch_with_no_lis_roles_claim_at_all_and_a_web_door_role_is_refused(
    tool_verifying_against_this_suites_key: Any,
    door_contract: Any,
    platform: Any,
    suite_key_set: Any,
    claims_in_token: Any,
    web_vocabulary: tuple[str, frozenset[str]],
) -> None:
    """The absent case, which an empty list does not cover.

    `claims.get(ROLES_CLAIM, [])` and `claims[ROLES_CLAIM]` behave differently when
    the claim is missing rather than empty — the second raises, and a door that
    catches broadly around it could fall through to a default. A different mutation
    is a different case, which is the reason this module already has a launch with
    no `state` beside the launch with the wrong one.
    """
    claim, published = web_vocabulary
    assert "CARE" in published, (
        f"The mock provider publishes nobody holding 'CARE' (it publishes {sorted(published)}), so "
        "this test is smuggling a role the web door never sees."
    )

    def adjust(claims: dict[str, Any]) -> dict[str, Any]:
        claims.pop(ROLES_CLAIM, None)
        claims[claim] = ["CARE"]
        return claims

    response = re_signed_launch(
        tool_verifying_against_this_suites_key,
        door_contract,
        platform,
        suite_key_set,
        claims_in_token,
        adjust,
    )

    refused(
        response,
        door_contract,
        f"a launch carrying no LIS roles claim at all and stating 'CARE' in `{claim}`",
    )


def test_a_launch_carrying_both_vocabularies_lands_on_the_view_its_lis_role_names(
    tool_verifying_against_this_suites_key: Any,
    door_contract: Any,
    platform: Any,
    suite_key_set: Any,
    claims_in_token: Any,
    web_vocabulary: tuple[str, frozenset[str]],
) -> None:
    """The foreign vocabulary is **ignored**, not merely outranked.

    A launch stating the LIS Learner role and `CARE` in the web door's claim lands
    on the student view. This is the boundary control on the two refusals above: a
    door that refused every launch carrying an unfamiliar claim would satisfy them
    while being wrong about what it does with one, and a door that read both
    vocabularies and happened to prefer the LIS one would pass this and fail those.
    Together the three say the launch door reads one claim and does not look at the
    other.

    It is expected to pass today, and its value is in what it stops the fix from
    being: refusing anything that smells of the web vocabulary is not the fix.
    """
    claim, published = web_vocabulary
    assert "CARE" in published, (
        f"The mock provider publishes nobody holding 'CARE' (it publishes {sorted(published)}), so "
        "the value smuggled below is not one the web door would ever act on."
    )

    def adjust(claims: dict[str, Any]) -> dict[str, Any]:
        claims[ROLES_CLAIM] = [LEARNER_ROLE_URI]
        claims[claim] = ["CARE"]
        return claims

    response = re_signed_launch(
        tool_verifying_against_this_suites_key,
        door_contract,
        platform,
        suite_key_set,
        claims_in_token,
        adjust,
    )

    lands_on(response, door_contract, STUDENT_VIEW)


def test_a_launch_whose_only_lis_role_is_one_this_door_serves_no_view_for_is_refused(
    tool_verifying_against_this_suites_key: Any,
    door_contract: Any,
    platform: Any,
    suite_key_set: Any,
    claims_in_token: Any,
) -> None:
    """**Dies if the door defaults instead of refusing.**

    E0-18 gives this door two dispatches and no third: "Learner → student empty
    view, Instructor → instructor empty view". A launch whose LIS roles claim names
    neither is one this system has no view for, and a door that fell through to a
    default would put a mentor — a parent or an advisor, in the LIS vocabulary — on
    whichever page came last in the `if`. The wrong default here is a person seeing
    a screen nobody decided they should see, and it is the same fall-through the
    web door's admin test exists to catch.

    Nothing else is changed: no web-door claim is added, so a 4xx can only be the
    role. The Mentor URI is from the same LIS membership vocabulary the recognised
    two come from, so this is not a malformed claim either.
    """

    def adjust(claims: dict[str, Any]) -> dict[str, Any]:
        claims[ROLES_CLAIM] = [MENTOR_ROLE_URI]
        return claims

    response = re_signed_launch(
        tool_verifying_against_this_suites_key,
        door_contract,
        platform,
        suite_key_set,
        claims_in_token,
        adjust,
    )

    refused(
        response,
        door_contract,
        f"a launch whose only LIS role is {MENTOR_ROLE_URI!r}, which E0-18 gives this door no view "
        "for",
    )


# ---------------------------------------------------------------------------
# The cookie the login initiation sets, and what a refusal says and does.
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
            "exception that escapes a route is fail-closed and is still a defect: the request gets "
            "no page, and everything the refusal path would have done on the way out — clearing "
            "the single-use cookie, keeping server-side addresses out of the response — did not "
            "happen."
        )


def cookies_set_by(response: Any, purpose: str) -> list[str]:
    """Every `Set-Cookie` header on a response, or a failure saying there were none."""
    headers = response.headers.get_list("set-cookie")
    assert headers, (
        f"The login initiation set no cookie at all when {purpose} (it answered "
        f"{response.status_code} with headers {sorted(response.headers)}). E0-18 puts `state` and "
        "`nonce` 'into a short-lived signed cookie', and with no cookie there is nothing for the "
        "launch endpoint to compare against — and nothing for this test to read an attribute off."
    )
    return headers


def attributes_of(header: str) -> set[str]:
    """The attribute names in one `Set-Cookie`, lowercased, without their values."""
    return {part.split("=", 1)[0].strip().lower() for part in header.split(";")[1:]}


def test_the_login_cookie_is_marked_secure_outside_development(
    open_launch_door: Any, door_contract: Any, platform: Any
) -> None:
    """**Dies if the cookie is issued without `Secure`.**

    The launch cookie carries the `state` and `nonce` a launch is judged against.
    Without `Secure` a browser sends it over plain HTTP, so anyone on the path can
    read it — and this is auth code, where E0-18 says "absence of basic
    state/nonce/signature checks is not tolerable even briefly". The attribute is
    free and the omission is invisible in every test that does not look for it.

    Its pair is the next test: the flag has to be conditional, because a `Secure`
    cookie is not sent to `http://localhost` and would break the development flow
    this whole ticket exists to open.
    """
    tool = open_launch_door(environment=PRODUCTION)
    offer = platform.require_offers()[0]

    response = initiate(tool, door_contract, offer)

    for header in cookies_set_by(response, f"`{ENVIRONMENT_VARIABLE}` was {PRODUCTION!r}"):
        assert SECURE_ATTRIBUTE in attributes_of(header), (
            f"The login initiation set `{header}` with `{ENVIRONMENT_VARIABLE}` set to "
            f"{PRODUCTION!r}, and it carries no `Secure` attribute. That cookie holds the `state` "
            "and `nonce` this door judges a launch by, and without `Secure` a browser will send it "
            "over plain HTTP to anyone who can put a request in front of it."
        )


def test_the_login_cookie_is_not_marked_secure_in_development(
    open_launch_door: Any, door_contract: Any, platform: Any
) -> None:
    """The near miss for the test above: `Secure` unconditionally breaks the laptop.

    E0-18's whole point is that `docker compose up` yields a launchable-into system,
    and a browser reaches it at `http://localhost:8000`. A `Secure` cookie is not
    sent back over that, so the launch that set it is refused for a mismatched
    `state` — which reads as a broken door rather than as a cookie flag.

    Without this, "always set `Secure`" satisfies the requirement above and is the
    wrong fix.
    """
    tool = open_launch_door(environment=DEVELOPMENT)
    offer = platform.require_offers()[0]

    response = initiate(tool, door_contract, offer)

    for header in cookies_set_by(response, f"`{ENVIRONMENT_VARIABLE}` was {DEVELOPMENT!r}"):
        assert SECURE_ATTRIBUTE not in attributes_of(header), (
            f"The login initiation set `{header}` with `{ENVIRONMENT_VARIABLE}` set to "
            f"{DEVELOPMENT!r}. A `Secure` cookie is not sent to `http://localhost`, so every launch "
            "from the mock LMS on a developer's laptop arrives with no cookie and is refused for a "
            "`state` mismatch."
        )


def test_a_launch_whose_state_is_not_ascii_is_refused_and_the_cookie_is_burned(
    tool: Any, door_contract: Any, platform: Any
) -> None:
    """**Dies if the comparison crashes instead of refusing.**

    `secrets.compare_digest` raises `TypeError` when either side is a `str` holding
    a character outside ASCII, so a `state` of `é` takes a door that compares
    directly out through the error handler rather than through the refusal. The
    crash is fail-closed — nobody is admitted — which is why it survives a suite
    that only asks whether the launch succeeded. What it skips is everything the
    refusal path does on the way out, and on this door that is the single-use
    cookie.

    So both halves are asserted, and the second is the one worth having: after the
    refusal, the launch the tool itself set up — correct `state`, correct token —
    is delivered and must also be refused, because the cookie it would have been
    judged against is gone. `test_a_learner_launch_lands_on_the_student_view` is
    the control for that half: it is this same sequence without the `é` attempt,
    and it answers 200.
    """
    offer = offer_for_role(platform, LEARNER_ROLE_URI)
    started = initiate(tool, door_contract, offer)
    parameters = query_of(redirect_target(started, "a registered platform began a launch"))
    id_token, state, _ = authorize(platform, parameters)
    assert state, "The platform returned no `state`, so there is no correct value to replay below."

    crashed = answer_to(
        lambda: land(tool, door_contract, id_token, NON_ASCII_STATE),
        f"a launch whose `state` was {NON_ASCII_STATE!r}",
    )

    assert crashed.status_code != 500, (
        f"The tool answered 500 to a launch whose `state` was {NON_ASCII_STATE!r}. That is "
        "`secrets.compare_digest` raising `TypeError` on a non-ASCII `str` rather than answering "
        f"`False`. Body begins {crashed.text[:400]!r}."
    )
    refused(crashed, door_contract, f"a launch whose `state` was {NON_ASCII_STATE!r}")

    replayed = answer_to(
        lambda: land(tool, door_contract, id_token, state),
        "the correct `state` for a login initiation whose cookie a refusal should have burned",
    )

    assert 400 <= replayed.status_code < 500, (
        f"After refusing the non-ASCII `state`, the tool answered {replayed.status_code} to the "
        "correct `state` for the same login initiation. The cookie holding it should have been "
        "cleared on the way out of the refusal: one login initiation buys one attempt, and a "
        "refusal that leaves the cookie in place hands an attacker as many tries as they like at "
        "a `state` the browser is still carrying."
    )


def test_a_launch_whose_nonce_is_not_ascii_is_refused_rather_than_crashing(
    tool: Any, door_contract: Any, platform: Any
) -> None:
    """The same hazard on the other value compared the same way (entry 13).

    The nonce is the tool's own, echoed by the platform into the signed token, so a
    non-ASCII nonce is posed by answering the tool's authorization request with one
    parameter changed — the token is correctly signed over it and everything else,
    `state` included, is the tool's own. If the door compares it with
    `secrets.compare_digest`, this is the second place the same `TypeError` lives,
    and a fix applied only to `state` leaves it.
    """
    offer = offer_for_role(platform, LEARNER_ROLE_URI)
    started = initiate(tool, door_contract, offer)
    parameters = query_of(redirect_target(started, "a registered platform began a launch"))
    assert parameters.get("nonce"), (
        "The tool's authorization request carries no `nonce`, so there is nothing to substitute "
        "and nothing for the launch endpoint to compare."
    )

    id_token, state, _ = authorize(platform, {**parameters, "nonce": NON_ASCII_NONCE})
    response = answer_to(
        lambda: land(tool, door_contract, id_token, state),
        f"a launch whose `nonce` was {NON_ASCII_NONCE!r}",
    )

    assert response.status_code != 500, (
        f"The tool answered 500 to a launch whose `nonce` was {NON_ASCII_NONCE!r}. `state` and "
        "`nonce` are compared the same way and the fix belongs in one place: a door that refuses "
        f"one and crashes on the other has the hazard written down in one of the two places facing "
        f"it. Body begins {response.text[:400]!r}."
    )
    refused(response, door_contract, f"a launch whose `nonce` was {NON_ASCII_NONCE!r}")


def test_a_refusal_does_not_name_the_key_set_address_the_tool_could_not_reach(
    open_launch_door: Any, door_contract: Any, platform: Any, jwks_url: str
) -> None:
    """**Dies if the refusal page carries the server-side address it failed to fetch.**

    `lti_platform.jwks_url` is a server-side address — a Compose service name that
    means nothing to a browser and everything to somebody mapping the network
    behind the tool. A refusal that repeats it, in a message or a traceback,
    publishes the tool's internal topology to whoever provoked the fetch, and
    provoking it takes nothing more than delivering a launch.

    The failure is provoked through the seam rather than by misconfiguring the
    tool, so the address in the refusal — if it appears — is the *configured* one
    rather than one this test typed. The host alone is asserted, because that is
    the part that is a network location; a door that named the path and not the
    host would still not be naming a machine.
    """
    split = urlsplit(jwks_url)
    host = split.hostname
    assert host, (
        f"The registered key set URL {jwks_url!r} has no host, so there is no address for this "
        "test to look for and nothing for the tool to fetch."
    )
    fetched: list[str] = []

    def around(request: Any, deliver: Any) -> Any:
        if request.url.host == host and request.url.path == split.path:
            fetched.append(str(request.url))
            return httpx.Response(404, text="no key set here", request=request)
        return deliver()

    tool = open_launch_door(around=around)

    response = answer_to(
        lambda: launched(tool, door_contract, platform, offer_for_role(platform, LEARNER_ROLE_URI)),
        "a launch whose key set the tool could not fetch",
    )

    assert fetched, (
        f"The tool never fetched the registered key set at {jwks_url!r}, so whatever it answered "
        "was decided before any fetch failed and this test is looking at the wrong refusal "
        "(`docs/MISTAKES.md` entry 3)."
    )
    refused(response, door_contract, "a launch whose key set could not be fetched")
    assert response.text.strip(), (
        "The refusal has an empty body, so 'the address is not in it' is true of a page with "
        "nothing in it and says nothing about what the tool would print when it has something to "
        "say."
    )
    assert host not in response.text, (
        f"The refusal page names {host!r}, the host of the key set URL the tool fetches "
        f"server-side ({jwks_url!r}). Body begins {response.text[:400]!r}. That address is a "
        "Compose service name: it is useless to the browser that received it and it is the "
        "network map to anyone else."
    )
