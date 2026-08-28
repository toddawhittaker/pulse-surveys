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

**E1-12 changes what a successful login requires, and this module meets it in one
place.** From that ticket on the door resolves `(issuer, subject)` to a stored
`person` through the `web_login_subject` linkage, and a subject with no row there
lands on a calm no-account page instead of a session. Every login below would
therefore stop landing, in tests about cookies, hints, claims and error redirects
that have nothing to do with identity — `docs/MISTAKES.md` entry 22 exactly. So
the `provider` fixture provisions a linkage for every person the provider
publishes, one person each, and nothing else in this module changes. What a login
*resolves to* is not asserted here at all: that is E1-12's own subject, in
`test_dual_door_identity_merge.py` and
`test_the_unlinked_web_login_lands_on_no_account.py`.

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

**E1-09 changes what a successful web login looks like, and adds the error
branch.** Two things move.

The landing is no longer a `200` carrying inline HTML. E1-08 retired that shape on
the launch door, and E1-09 brings this door onto the same shared session module: a
successful web login answers `302` to `/app/<role>#session=<jwt>` with the session
and CSRF cookies set. So `landed_with_session` replaces `lands_on` throughout, and
the three constants below name E1-04's **route segments** rather than the testids
the old inline page carried. Nothing is deleted here — every test that asserted the
old shape asserts the new one, because each is still about which role a session
lands as, which is the property that did not change.

The second half is new. A refusal arriving as a redirect — the user cancelled, the
provider declined — is a branch this door had no code for at all, and Batch F
(E0-30) taught the mock provider RFC 6749 §4.1.2.1's error redirects so it could be
driven here for real rather than typed into a query string. The last section of
this module is that branch: the calm page when the returned `state` matches the
carried login, the ordinary refusal when it does not, and the four things that must
not happen on either — no session, no code spent, no untrusted text rendered, no
untrusted text logged.
"""

import base64
import json
import logging
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
#
# **The three below are E1-04 route segments now, not testids.** E1-09 puts this
# door on the session-issuing shape E1-08 built, so "lands on the Care view" is a
# `302` to `/app/care#session=<jwt>` rather than a page carrying
# `pulse-landing-care`. The five testids still exist — the SPA renders them at
# those routes — and `door_contract.landing_testids` still names them, which is
# what `refused` reads to say that a refusal served nobody's landing.
LEADERSHIP_ROLES = ("VP_ACADEMICS", "DEAN", "ASSISTANT_DEAN", "CHAIR", "LEAD_FACULTY")
LEADERSHIP_ROUTE = "leadership"
CARE_ROUTE = "care"
ADMIN_ROUTE = "admin"

# The launch-door route the two-hat person reaches by her other assignment.
# E1-04's route group name — was `pulse-landing-instructor`, the testid
# E0-18's inline HTML carried, before E1-08 retired that contract (dispute
# E1-08-03) in favour of a `302` to `/app/<role>#session=`.
INSTRUCTOR_ROLE = "instructor"

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

# ---------------------------------------------------------------------------
# E1-09's error branch.
# ---------------------------------------------------------------------------

# The calm page's `data-testid`, from E1-09's contract. It is not one of the five
# landing testids and it is not the refusal page: three distinguishable answers,
# because "the person cancelled" and "somebody sent this tool an error redirect it
# cannot account for" are different events and the person in front of the screen is
# owed different words for them.
CANCELLED_TESTID = "web-login-cancelled"

# A subject the mock provider's seed does not carry. **This module's own
# spelling**, deliberately not the one `tests/integration/test_mock_idp_error_
# redirects.py` uses: a test module importing its sibling depends on where pytest
# put `tests/` on `sys.path`, and an import error is not a red (see the note on the
# mock platform's variables above). Naming somebody the provider will not sign in
# is how a cancel is produced through a login form that offers no cancel control —
# `mock-idp/app/pages.py` builds one select and one submit button — and RFC 6749
# §4.1.2.1 gives both events the same answer: `access_denied` with the `state`
# echoed.
UNKNOWN_SUBJECT = "e1-09-nobody"

# RFC 6749 §4.1.2.1's codes, and the four E1-09 lets the log repeat verbatim. The
# fifth value is the near miss: a code outside the set, which is logged as the
# literal word below and never echoed. Both halves are needed — a door that logged
# `unrecognized` for everything satisfies the unknown-code test and tells an
# operator nothing, and a door that echoed everything satisfies the four and hands
# an attacker a log-injection surface.
ACCESS_DENIED = "access_denied"
LOGGED_ERROR_CODES = (
    "invalid_request",
    ACCESS_DENIED,
    "unsupported_response_type",
    "invalid_scope",
)
UNRECOGNISED_CODE_LOGGED_AS = "unrecognized"

# Three values that are outside the set, each outside it for a different reason,
# so that only an exact comparison answers "outside" for all three. A single
# stranger is not enough and this file learned that from a mutation battery: the
# first version sent the first of these alone, and a `startswith` comparison and a
# `.lower()` comparison both survived, because a value sharing no prefix and no
# case variant with any member is outside the set under every one of them.
#
# The tail on the third is a newline and a line that reads like a log record,
# which is what a prefix comparison would carry into the log and is the injection
# `backend/app/api/auth.py`'s own module comment names as the reason for the set.
AN_UNKNOWN_ERROR_CODE = "e1-09-not-an-rfc-6749-error-code"
CODES_OUTSIDE_THE_SET = {
    "a code from outside the registry": AN_UNKNOWN_ERROR_CODE,
    "a case variant of a set member": ACCESS_DENIED.upper(),
    "a set member with an injected tail": (
        f"{ACCESS_DENIED}\nWARNING e1-09-injected-log-line: not written by this application"
    ),
}

# Two values a provider — or anyone who can put a browser in front of this
# callback — may write into an error redirect. RFC 6749 §4.1.2.1 puts no grammar on
# either beyond the request encoding, so both are attacker-chosen text, and E1-09
# renders neither, logs neither and echoes neither. Distinct strings, so a failure
# says which one got through, and both are unmistakable in a page or a log line.
UNTRUSTED_DESCRIPTION = "e1-09-untrusted-error-description-marker"
UNTRUSTED_ERROR_URI = "http://attacker.invalid/e1-09-untrusted-error-uri-marker"

# The tool's own logging namespace. `app.lti.launch` (E1-08) is the established
# spelling for a door's logger, so the application's loggers live under `app.`, and
# the scans below read that namespace rather than every record pytest captured:
# `httpx` logging one of the tool's own outbound calls, or a library echoing a URL,
# would otherwise decide both the leak assertion and the code assertion for reasons
# that have nothing to do with what this door wrote. If the web door logs under a
# name outside `app.`, that is a finding to raise rather than a line to widen —
# a log line the application's own namespace does not cover is one nothing here
# reads.
APPLICATION_LOGGER_ROOT = "app"

# The capability table. E0-09 criterion 10: "No LTI claim, no OIDC claim, and no
# LMS role may ever produce a `CARE` assignment." A row here is what *holding* a
# role is in this system — E0-11 resolves every actor's roles out of it and
# nowhere else — so this is the table the claim must not reach.
ASSIGNMENT_TABLE = "role_assignment"

# The two tables a door would write if it provisioned the person it just
# authenticated. E0-18's boundary section gave provisioning to E1 ("E0 does not
# build… any `user` row for a mock subject"), and this assertion was written to
# move deliberately when E1 built it.
#
# **E1-12 built it and the count is still unchanged**, which is that ticket's
# decision rather than an accident: the web door *resolves* an identity and never
# creates one. The linkage is pre-provisioned — by the seed, or by an administrator
# — `pulse_app` holds no grant of any kind on the table it lives in, and a subject
# with no linkage gets a calm page rather than an account. So this stays as it was
# written, and what E1-12 adds beside it is the same assertion made about the
# subject nobody provisioned, in
# `tests/integration/test_the_unlinked_web_login_lands_on_no_account.py`.
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


def session_cookie_names() -> tuple[str, str]:
    """`SESSION_COOKIE` and `CSRF_COOKIE`, or a failure naming where E1-08 put them.

    Read out of the shared session module rather than transcribed, so this suite
    and the launch door's cannot end up asserting about two different cookie names
    (`docs/MISTAKES.md` entry 13). E1-09 issues its sessions through that same
    module — "same type, same custody" — so the names are not this door's to choose.
    """
    try:
        from app.services.session import CSRF_COOKIE, SESSION_COOKIE
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`app.services.session` does not import ({missing}). E1-08's module layout names "
            "`SESSION_COOKIE`/`CSRF_COOKIE` there, and E1-09 issues the web door's session "
            "through the same module."
        )
    return SESSION_COOKIE, CSRF_COOKIE


def cookie_names_set_by(response: Any) -> set[str]:
    """The names of every cookie a response sets, without asserting there are any."""
    return {header.split("=", 1)[0].strip() for header in response.headers.get_list("set-cookie")}


def landed_with_session(response: Any, contract: Any, role: str) -> str:
    """The web login redirected to `/app/<role>#session=<token>`, both cookies set.

    E1-09 puts this door on the shape E1-08 settled for the launch door, and this
    is that door's own `redirected_to_role` assertion made about this one: a `302`
    whose `Location` is `/app/<segment>#session=<token>`, with `pulse_session`
    beside it. The exact-prefix check on `Location` is also what rules out a query
    string sneaking in between the path and the fragment — `/app/care?x=y#session=`
    fails this `startswith` — which is the whole reason the design puts the token in
    a fragment: a fragment reaches neither an access log nor a `Referer` header.

    The CSRF cookie is required here as well as the session cookie, which the launch
    door asserts in its own cookie-attribute test rather than in its redirect
    helper: E1-09's contract for a successful web login is both cookies, and a door
    that set one of the two would leave the SPA with a session it cannot make a
    write with. Returns the token so a caller can go on to say something about it.
    """
    session_cookie, csrf_cookie = session_cookie_names()

    assert response.status_code in (302, 303, 307), (
        f"A completed web login answered {response.status_code} rather than a redirect. Body "
        f"begins {response.text[:400]!r}. E1-09 retires E0-18's `200` + inline HTML landing: the "
        "web door issues a session through E1-08's module and redirects, exactly as the launch "
        "door does."
    )
    location = response.headers.get("location") or ""
    prefix = f"/app/{role}#session="
    assert location.startswith(prefix), (
        f"A completed web login redirected to `{location}`, which does not start with `{prefix}`. "
        "E1-08's interface ruling, which E1-09 adopts unchanged: a 302 whose `Location` is "
        "`/app/<segment>#session=<token>`, segment lowercased."
    )
    token = location[len(prefix) :]
    assert token, f"The redirect `{location}` carries `session=` with an empty token."

    names = cookie_names_set_by(response)
    assert session_cookie in names, (
        f"No `Set-Cookie` names {session_cookie!r} on a web login that redirected to `/app/{role}`."
        f" Cookies set: {sorted(names)}. The redirect carries the session cookie alongside the "
        "fragment token."
    )
    assert csrf_cookie in names, (
        f"No `Set-Cookie` names {csrf_cookie!r} on a web login that redirected to `/app/{role}`. "
        f"Cookies set: {sorted(names)}. E1-08's session model issues the two together; a session "
        "without its CSRF cookie is one the SPA can read and cannot write with."
    )
    return token


def no_session_was_issued(response: Any, what: str) -> None:
    """Nothing in this response hands the caller a session. The forbidden state.

    Three ways a session could leave this door, and all three are checked, because
    a door that stopped setting the cookie and went on redirecting with the fragment
    would satisfy a cookie-only check while handing the token over (`docs/MISTAKES.md`
    entry 2 — assert the forbidden state, and assert all of it).
    """
    session_cookie, csrf_cookie = session_cookie_names()

    names = cookie_names_set_by(response)
    handed = sorted(names & {session_cookie, csrf_cookie})
    assert not handed, (
        f"The tool set {handed} while answering {what}. That is a session, issued on a path that "
        "authenticated nobody."
    )
    location = response.headers.get("location") or ""
    assert "session=" not in location, (
        f"The tool answered {what} with `Location: {location}`, which carries a session token in "
        "the URL. The fragment is how a *successful* login hands the session to the browser."
    )
    assert "session=" not in response.text, (
        f"The body the tool answered {what} with carries `session=`. Body begins "
        f"{response.text[:400]!r}."
    )


def refused(response: Any, contract: Any, what: str) -> None:
    """The tool refused, and handed the caller nothing on the way out.

    **E1-09 adds the second half.** Under E0-18 a landing was a rendered page, so
    "no landing testid in the body" was the whole of what a refusal had to avoid.
    A landing is a session now, so the thing a refusal must not do is issue one —
    and that check is live where the testid check has become a formality kept for
    the door that renders the old inline page.
    """
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
    no_session_was_issued(response, what)


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
    that names who is signed in is legitimate — the session token carries its own
    subject, by construction — and a landing that names *anybody else* has
    enumerated people, which nothing in E1 computes a purview to do (ADR 0003,
    §2.1: `transitive_purview` still raises).
    """
    mine = {value for value in except_for.values() if isinstance(value, str) and value}
    found: list[str] = []
    for user in provider.published_users():
        for member in ("email", "subject"):
            value = user.get(member)
            if isinstance(value, str) and value and value not in mine:
                found.append(value)
    return found


def claims_text_of(token: str) -> str:
    """The decoded claim set of a compact JWS, as text, without verifying anything.

    Nothing here is checking a signature — `tests/unit/test_session_module.py` does
    that — and the secret the web door signs with is not a value this suite is
    given. What this is for is the §4.1 scans below, and it exists because a
    base64url payload defeats a substring search completely: a session token
    carrying a name would sail through a scan of the raw response, and the scan
    would report a clean page while the leak sat in the very bytes it read
    (`docs/MISTAKES.md` entry 3).
    """
    parts = token.split(".")
    assert len(parts) == 3, (
        f"The fragment carried {token!r}, which is not a compact JWS (three dot-separated "
        "segments), so there is no claim set to decode and the scan below would be reading a "
        "shorter response than the caller received."
    )
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    decoded = base64.urlsafe_b64decode(padded).decode("utf-8", "replace")
    try:
        json.loads(decoded)
    except ValueError as broken:
        pytest.fail(
            f"The session token's payload does not decode to JSON ({broken}); it decodes to "
            f"{decoded[:200]!r}. A scan over garbage finds nothing and reports a clean session."
        )
    return decoded


def everything_the_caller_received(response: Any, token: str) -> str:
    """The whole of what one redirect hands a browser: status line, headers, body, claims.

    A landing is a `302` now, so `response.text` is empty or nearly so, and a scan
    over it would pass against anything at all. What the caller actually receives is
    the `Location` — fragment included — every `Set-Cookie`, the body, and the claims
    inside the session token, and all four are here.
    """
    parts = [
        response.headers.get("location") or "",
        *response.headers.get_list("set-cookie"),
        response.text,
        claims_text_of(token),
    ]
    return "\n".join(parts)


@pytest.fixture
def published_links() -> dict[str, Any]:
    """Filled by `provider` below: each published subject, and the `person` it resolves to.

    Added by E1-13's reconciliation. One test in this module drives a launch as
    well as a login and has to hang a `user` row off the very `person` the linkage
    names, and the mapping is what says which row that is. Empty until `provider`
    has run, and empty for good while the linkage table does not exist — the same
    tolerance `link_published_people` documents for the red phase.
    """
    return {}


@pytest.fixture
def provider(
    mock_idps: Any,
    door_contract: Any,
    link_published_people: Any,
    published_links: dict[str, Any],
) -> Any:
    """The mock provider, registered to return to this tool's own callback.

    `MOCK_IDP_TOOL_REDIRECT_URI` is compared exactly — on the way in and again at
    the token endpoint — so this is what makes "the tool builds its redirect URI
    from `PUBLIC_BASE_URL`" a property the provider itself enforces rather than one
    only a test believes.

    **Every published person is given a Pulse identity to resolve to, and that is
    E1-12 arriving in this module** (`docs/MISTAKES.md` entry 22). From that ticket
    on, a verified `id_token` is not enough to land: the door resolves
    `(issuer, subject)` through the `web_login_subject` linkage, and a subject with
    no row there gets a calm "no account" page and no session. Without this line
    every successful login below — the dean, the Care office, the administrator, the
    cookie attributes, the login hints, the re-signed sessions — would answer 200
    with that page, in tests whose subject is none of it, and the repair would be on
    the other side of the test wall from whoever met the red.

    So the linkage is provisioned for everybody the provider publishes, which is
    what a deployment whose people all have accounts looks like, and it is one
    person per subject so that nothing here can prove a merge by accident. The
    unlinked case is not lost: it is E1-12's own subject, in
    `tests/integration/test_the_unlinked_web_login_lands_on_no_account.py`, where a
    subject is deliberately left without a row.

    **E1-13 arrives here the same way, through the same fixture** — and this is
    the second time a later ticket's rule has reached this module through it
    (`docs/MISTAKES.md` entry 22). From that ticket the landing comes from the
    assignment model, so a person with a linkage and no assignment lands on a calm
    no-access page: the dean, the Care office, the administrator, the cookie
    attributes, the login hints and the re-signed sessions would all answer 200
    with that page instead of a session, in tests whose subject is none of it. So
    `link_published_people` also writes the assignments the registration document
    says each person holds — their `roles`, plus the `launch_only_roles` the
    two-hat person carries on the other door (ADR 0058 makes both part of the
    published contract). **What that costs**: a landing test in this module can no
    longer be read as evidence that the assignment is what decided, because the
    fixture is what put the assignment there. It is not asked to be — the rule is
    asserted in the open in
    `tests/integration/test_landing_resolves_from_assignments.py`, over rows each
    test writes itself.
    """
    provider = mock_idps(
        {
            MOCK_IDP_TOOL_REDIRECT_URI_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.oidc_callback}"
            )
        }
    )
    published_links.update(link_published_people(provider))
    return provider


@pytest.fixture
def open_web_door(
    tool_doors: Any,
    door_contract: Any,
    provider: Any,
    deployed_identity_provider: dict[str, str],
) -> Any:
    """Build the tool for this provider, with settings a test may override.

    Every OIDC endpoint comes out of the provider's discovery document, which is
    how a client learns them and which means nothing about the mock's URLs is
    written down here. The host in those URLs is also what routes the tool's
    server-side calls back into the in-process provider, so a door that fetched
    from anywhere else reaches no mock and says so.

    **Except when the test asks for a deployment's `ENVIRONMENT`** — E0-39's repair
    round. That ticket refuses a `mock-idp` host or the mock's client id outside
    development, and the mock advertises itself under the Compose service name, so
    "this tool, in production, pointed at the mock" is a configuration that no
    longer builds. It is also not a configuration any test here is about: the one
    caller that asks for a production environment is the `Secure` cookie pair below,
    whose subject is an attribute on the cookie the login initiation sets, and that
    route redirects the browser to the authorization endpoint without calling the
    provider at all. So a non-development build gets `deployed_identity_provider`'s
    placeholder addresses, which is what a real deployment in that environment would
    hold, and the in-process mock stays routed for the flows that actually redeem a
    code — every one of which runs in development.

    A test's own `overrides` are applied last and still win, so a case that needs a
    particular issuer under a deployment's environment can still say so.
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
        if environment is not None and environment != DEVELOPMENT:
            # E0-39: the mock's addresses and client id are refused outside
            # development, and no caller that asks for a deployment's environment
            # reaches the provider. See this fixture's docstring.
            values.update(deployed_identity_provider)
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
# The landings, one per role §2 gives this door. E1-09 criterion 1: "a seeded
# leadership, Care, and admin identity each logs in and lands on their E1-04
# route with a session."
# ---------------------------------------------------------------------------


def test_the_dean_lands_on_the_leadership_route_with_a_session(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """Criterion 1, the leadership third: a dean's web login reaches `/app/leadership`.

    The whole flow is real — authorization request, login form, code, and a
    server-side exchange carrying the verifier — so this fails if any link is
    missing. It is the first of three, and the three together are what make the
    dispatch on the roles claim observable at all.

    **Dies if the door still answers E0-18's inline `200`**, which is the shape
    E1-09 retires, and dies if it redirects without issuing a session: both cookies
    and a non-empty fragment token are required, so a redirect to the right route
    carrying nothing is a person sent to a page they cannot use.
    """
    response = logged_in(tool, door_contract, provider, person_holding(provider, "DEAN"))

    token = landed_with_session(response, door_contract, LEADERSHIP_ROUTE)

    assert token.count(".") == 2, (
        f"The fragment's `session=` value is {token!r}, which does not have the three dot-"
        "separated segments a compact JWS has, so it is not a signed session token."
    )


def test_the_care_office_lands_on_the_care_route_with_a_session(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """Criterion 1, the Care third: `CARE` → `/app/care` (§6.2, and E0-18's route list).

    The Care office rather than the person who also teaches: she is the subject of
    her own test below, and picking whichever of the two the document listed first
    would make one of these two tests silently about the other.
    """
    response = logged_in(tool, door_contract, provider, person_holding(provider, "CARE"))

    landed_with_session(response, door_contract, CARE_ROUTE)


def test_the_administrator_lands_on_the_admin_route_with_a_session(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """Criterion 1, the admin third: `ADMIN` → `/app/admin`, the last of the three.

    **Dies if the role dispatch falls through to a default.** A tool that landed
    everything it did not recognise on one route passes the leadership test and the
    Care test if Care is checked explicitly; Admin is the case that catches the
    fallback, because it is last in E0-18's precedence order.
    """
    response = logged_in(tool, door_contract, provider, person_holding(provider, "ADMIN"))

    landed_with_session(response, door_contract, ADMIN_ROUTE)


def test_the_web_doors_session_and_csrf_cookies_carry_the_session_adrs_attributes(
    open_web_door: Any, door_contract: Any, provider: Any
) -> None:
    """`HttpOnly` on the session cookie and not on the CSRF one; `SameSite=None`; `path=/`.

    Criterion 1's "with a session" is not only that two cookies appear — it is that
    they are the cookies E1-08's session ADR describes, because E1-09's scope says
    "same type, same custody". **Dies if this door sets its own cookies rather than
    going through the shared module**, which is the tempting shortcut and which
    produces a session that works and a CSRF cookie the SPA cannot read.

    **The production half is not posed here, and that is deliberate rather than an
    omission.** `Secure` flips with `ENVIRONMENT`, and no web login can complete
    outside development in this harness: E0-39 refuses the mock provider's
    addresses there, so `open_web_door(environment=...)` swaps in unreachable
    placeholders and the flow never reaches a token endpoint (see that fixture's
    docstring). The flip is asserted over the same `set_session_cookie` by
    `tests/integration/test_lti_launch_door.py::test_the_session_and_csrf_cookies_carry_the_session_adrs_attributes`,
    parametrized over both environments, and the login cookie's own flip is asserted
    on this door below — the one route that redirects without calling the provider.
    """
    session_cookie, csrf_cookie = session_cookie_names()
    # `environment=DEVELOPMENT` is named rather than left ambient: `open_web_door`
    # only swaps the mock provider out for a non-development environment, so this
    # keeps the flow completable while making the environment the `Secure`
    # assertion below is measured against a value this test set.
    tool = open_web_door(environment=DEVELOPMENT)

    response = logged_in(tool, door_contract, provider, person_holding(provider, "DEAN"))
    landed_with_session(response, door_contract, LEADERSHIP_ROUTE)

    headers = cookies_set_by(response, "a completed web login")
    by_name = {header.split("=", 1)[0].strip(): header for header in headers}
    session_header = by_name[session_cookie]
    csrf_header = by_name[csrf_cookie]

    assert "httponly" in attributes_of(session_header), (
        f"The session cookie carries no `HttpOnly`: {session_header!r}. It holds the session "
        "token itself, and a script that can read it can steal the session."
    )
    assert "httponly" not in attributes_of(csrf_header), (
        f"The CSRF cookie carries `HttpOnly`: {csrf_header!r}. E1-08: `CSRF_COOKIE` is not "
        "`HttpOnly` because the SPA echoes it in `X-Pulse-CSRF`, and a script that cannot read "
        "it cannot echo it."
    )
    for name, header in (("session", session_header), ("CSRF", csrf_header)):
        lowered = header.lower()
        assert "samesite=none" in lowered, (
            f"The {name} cookie does not carry `SameSite=None`: {header!r}. One session module "
            "serves both doors, and the launch door's runs inside a cross-site iframe for the "
            "whole visit."
        )
        assert "path=/" in lowered, f"The {name} cookie does not carry `path=/`: {header!r}."
    assert SECURE_ATTRIBUTE not in attributes_of(session_header), (
        f"The session cookie carries `Secure` under `{ENVIRONMENT_VARIABLE}` "
        f"{DEVELOPMENT!r}: {session_header!r}. A `Secure` cookie is not sent to "
        "`http://localhost`, so every web login on a developer's laptop would land on a page "
        "with no session."
    )


@pytest.mark.invariant
def test_the_leadership_view_names_nobody_but_the_person_signed_in(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """SPEC §4.1 over the one landing that would otherwise list people.

    E0-18: the leadership landing views "are empty *by design* and must not
    traverse" `transitive_purview`, which raises (ADR 0003). So the honest
    assertion is that what the caller receives names nobody but its own caller — a
    landing that enumerated the institution would have obtained that list from
    somewhere, and there is nowhere in E1 it could legitimately have come from.

    **What "what the caller receives" means changed under E1-09, and the scan
    changed with it.** The old shape was a rendered page and `response.text` was
    the whole of it. The new shape is a `302` with an almost empty body, so a scan
    of the body alone would be a scan of nothing — and the part that now carries
    data, the session token in the fragment, is base64url and defeats a substring
    search outright. So the haystack is the `Location`, every `Set-Cookie`, the
    body, and the token's decoded claim set (`docs/MISTAKES.md` entry 3: a test
    that can be satisfied by emptiness is not a test).

    Three guards keep it from passing on emptiness. The redirect has to be the
    leadership one with a session, so a 4xx or a door that was never reached fails
    rather than passes; the token's payload has to decode to JSON, so a scan over
    garbage says so; and the scan is shown finding the very strings it reports
    absent.
    """
    dean = person_holding(provider, "DEAN")
    response = logged_in(tool, door_contract, provider, dean)
    token = landed_with_session(response, door_contract, LEADERSHIP_ROUTE)
    received = everything_the_caller_received(response, token)

    others = identifying_strings(provider, dean)
    assert others, (
        "No seeded person other than the dean publishes an address or a subject, so this test has "
        "nothing to look for and would pass against a landing listing the whole institution."
    )
    canary = " ".join(others)
    assert all(value in canary for value in others), (
        "The scan below cannot find these strings in a sample built out of them, so its silence "
        "about the landing means nothing."
    )

    leaked = sorted({value for value in others if value in received})
    assert not leaked, (
        f"The leadership landing carries {leaked}, which identify seeded people other than the "
        "dean who signed in. That set is read from the whole of what the browser received — the "
        "redirect, its cookies, its body and the session token's claims. Purview is not computed "
        "in E1, so a landing that names people got that list from somewhere §4.1 does not "
        "sanction."
    )


@pytest.mark.invariant
def test_the_care_view_names_nobody_but_the_person_signed_in(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """The same, for the one surface SPEC §6.2 spends a paragraph on.

    E0-18: "The Care page shows a heading and nothing else — read §6.2 before
    writing even that." Care is the one role in this system that can re-identify a
    student, so a Care landing that arrived carrying anybody is the most expensive
    version of this mistake. Same three guards as above, over the same haystack —
    redirect, cookies, body, and the session token's decoded claims.
    """
    care = person_holding(provider, "CARE")
    response = logged_in(tool, door_contract, provider, care)
    token = landed_with_session(response, door_contract, CARE_ROUTE)
    received = everything_the_caller_received(response, token)

    others = identifying_strings(provider, care)
    assert others, (
        "No seeded person other than the Care office publishes an address or a subject, so this "
        "test has nothing to look for."
    )
    canary = " ".join(others)
    assert all(value in canary for value in others), (
        "The scan below cannot find these strings in a sample built out of them, so its silence "
        "about the landing means nothing."
    )

    leaked = sorted({value for value in others if value in received})
    assert not leaked, (
        f"The Care landing carries {leaked}. §6.2 keeps the Care surface to the threat queue and "
        "nothing else, and E1 builds no queue — so any identifier the browser received here came "
        "from a read nothing sanctions."
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
    claim.** It was written as the behavioural half of the exception
    `tests/unit/test_care_is_not_reachable_from_a_claim.py::EXCEPTIONS` used to
    grant `backend/app/services/landing.py`: that exception rested on one factual
    claim — the landing seam chooses a screen and writes nothing — and an exception
    resting on a sentence in a comment is one that stops being true without anybody
    noticing.

    **E1-13 deleted both the module and the exception, and this test is worth more
    rather than less for it.** The landing no longer comes from a claim at all, so
    what is asserted here is the plainer and stronger fact: a verified session
    stating `CARE` reaches this door, is landed, and writes nothing — no
    assignment, no person, no user. A claim is an authentication context and never
    a grant, and the whole flow is driven as the Care person to say so:
    authorization request, login form, code, server-side exchange, the landing
    redirect, and not one row anywhere.

    The Care half is the one that must never move. E0-09: "No LTI claim, no OIDC
    claim, and no LMS role may ever produce a `CARE` assignment… a claim-to-Care
    mapping would let an LMS administrator grant themselves identity access."
    E0-11 resolves what an actor may do out of `role_assignment` and out of
    nothing else, so as long as the claim reaches no row in that table, a forged
    or administrator-granted `CARE` claim buys an empty page.

    The provisioning half was written to move once, deliberately: E0-18's boundary
    gives E1 the `user` row and the dual-door identity merge. **E1-12 landed both
    and this assertion did not move**, because that ticket's answer is that the web
    door resolves an identity and never creates one — the linkage is provisioned
    ahead of a login and `pulse_app` holds no grant on the table carrying it. The
    Care person now has a linkage row, seeded by the `provider` fixture above, so
    she lands with a session as she did before; what must not happen is a row
    appearing here, and that is now a rule of E1-12's as well as an artefact of
    E0's boundary.

    **E1-13 did not move it either, and the count it is measured against changed.**
    That ticket gives the Care person a live `CARE` assignment, seeded by the same
    `provider` fixture ahead of the login, because a person with no assignment
    lands on the calm no-access page. So the assignment count is non-zero before
    the flow begins and must be **unchanged** after it — which is a stricter thing
    to say than it was over an empty table, and is exactly what E0-09's criterion
    10 is about: the row is provisioned by whoever administers Pulse, and the
    claim's job stops at saying who signed in.

    Two guards keep this from passing on nothing having happened: the flow has to
    land on `/app/care` with a session, so a 4xx or a door that was never reached
    fails rather than passes; and the counter is shown reading a table the
    migration filled, so
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
    landed_with_session(response, door_contract, CARE_ROUTE)

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

    landed_with_session(response, door_contract, LEADERSHIP_ROUTE)


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
    published_links: dict[str, Any],
    published_subject: Any,
    web_identity: Any,
) -> None:
    """E0-18: "the two-hat person exists on both doors and both doors open for her".

    §2: "Entry doors are a property of the assignment, not the person." She holds a
    Care assignment, which enters by web login, and an instructor assignment, which
    enters by launch — so the two views she reaches are not a contradiction, they
    are the model working. Her web session states `CARE` and nothing else, because
    her teaching assignment does not open this door; her launch states the LIS
    Instructor role, because it does.

    **The database-level assertion that these are one person is E1-12's, not this
    ticket's**, and E0-18 said so: it needs the dual-door identity merge, and E0
    writes no `user` row for a mock subject. It has since landed —
    `tests/integration/test_dual_door_identity_merge.py` drives the same person
    through both doors and asserts both sessions name one `person` row by its
    primary key — and this test keeps the half that is E0-18's: that each door
    dispatches her on the assignment that opens it.

    What ties the two halves below to one human is
    `mock-idp/app/seed.py::LMS_INSTRUCTOR_USER_ID`, the cross-mock reference
    published as `lms_user_id`, used here to choose which launch to drive. It used
    to be pinned to the platform's own constant by a unit test of E0-18's;
    E1-12 deleted that module, because the fact it stood in for is asserted
    directly now — against what the two mocks *serve* rather than against what they
    spell — in the merge test named above.

    Both doors in one test on purpose. Split in two, each half is satisfied by a
    seed the other person is missing from, and the fact worth asserting — that one
    published identity opens both — is not stated anywhere.

    **Both halves are the redirect shape now.** E1-08 retired the launch door's
    inline `200` + testid contract in favour of a `302` to
    `/app/instructor#session=<jwt>` (dispute E1-08-03), and E1-09 does the same to
    this door, so her Care half is a `302` to `/app/care#session=<jwt>` with the
    session and CSRF cookies set. Neither half is a rendered page any more, and the
    fact this test exists for is untouched by that: one published identity opens
    both doors, and each door dispatches her on the assignment that opens it.

    **Since E1-13, "the assignment that opens it" is literal.** Her two hats are
    rows now: the `provider` fixture writes the `CARE` and `INSTRUCTOR` assignments
    the registration document publishes for her, and this test adds the one thing
    that fixture cannot know — the `user` row for her LMS subject at *this*
    registration, and ADR 0024's link from her `person` to it, without which her
    launch resolves nobody and is answered with the calm no-access page. That is
    the same three-row shape `scripts/seed.py` writes for the mock world, and it is
    what makes both halves below reach a session at all.
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
    landed_with_session(care_landing, door_contract, CARE_ROUTE)

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
    # The authorization endpoint is the registration's since E1-05, not a
    # setting: this suite's subject is which person a launch lands as, so the
    # value only has to be one nothing could reach by accident. `.invalid` is
    # RFC 2606.
    registration = register_platform(
        offers[0], jwks_url, "http://lti-platform.invalid/e0-18-configured-authorize"
    )
    # E1-13: her launch resolves `sub` → `user` → `person`, so the `user` row for
    # her LMS subject at this registration, and ADR 0024's link to the `person` the
    # linkage already names, are what let the launch door reach her instructor
    # assignment at all. `published_links` is where the `provider` fixture recorded
    # which `person` her IdP subject resolves to; hanging the `user` row off any
    # other row would make her two doors two humans, which is the very thing
    # `tests/integration/test_dual_door_identity_merge.py` exists to forbid.
    her_person = published_links.get(published_subject(hers))
    assert her_person is not None, (
        f"No `person` was linked for the two-hat person's IdP subject "
        f"{published_subject(hers)!r}; the fixture linked {sorted(published_links)}. Without it "
        "this test cannot hang her launch-side `user` row off the identity her web login resolves "
        "to, and the two halves below would be about two different people."
    )
    her_user = web_identity.user(
        platform_id=registration.platform_row[web_identity.key_of("lti_platform")],
        subject=lms_user_id,
    )
    web_identity.link_person_to_user(person_id=her_person, user_id=her_user)

    launch_tool = tool_doors(
        {door_contract.settings["public_base_url"]: door_contract.public_base_url},
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

    assert instructor_landing.status_code in (302, 303, 307), (
        f"Her launch answered {instructor_landing.status_code} rather than a redirect. E1-08 "
        "retires the launch door's `200` + inline HTML: `landing_with_session` issues a "
        f"session and redirects. Body begins {instructor_landing.text[:300]!r}."
    )
    location = instructor_landing.headers.get("location") or ""
    prefix = f"/app/{INSTRUCTOR_ROLE}#session="
    assert location.startswith(prefix), (
        f"Her launch redirected to `{location}`, which does not start with `{prefix}`. E1-08's "
        "interface ruling: a 302 whose `Location` is `/app/<segment>#session=<token>`, and her "
        "teaching assignment is what makes the launch door dispatch her to the instructor route."
    )
    assert location[
        len(prefix) :
    ], f"The redirect `{location}` carries `session=` with an empty token."


# ---------------------------------------------------------------------------
# What a roles claim buys at this door, which since E1-13 is nothing.
#
# This section used to read "one door, one vocabulary": `test_lti_launch_door.py`
# asserted that door reads only the LIS roles claim, and these three asserted this
# one reads only `roles_claim` and never the LTI claim. **Both halves of that are
# retired.** E1-13 resolves the landing from the person's live assignments,
# filtered by ADR 0026's door column, so neither door consults a roles claim at
# all — and the three tests below say the stronger thing: the Care officer reaches
# `/app/care` with her own vocabulary present, with a foreign one smuggled in
# beside it, and with her own removed entirely and only the foreign one left.
# Her rows decide, three times over.
#
# The launch-door section this mirrors was rewritten in E1-13's red commit; the
# last of the three here was missed and was rewritten under dispute E1-13-01,
# which is the record of how one half of a stated pair moved without the other.
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
    tool is configured to verify against. If this lands on `/app/care` then the
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
    landed_with_session(response, door_contract, CARE_ROUTE)


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
    role in the LTI claim lands on `/app/care`. This is the boundary control on
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
    landed_with_session(response, door_contract, CARE_ROUTE)


def test_a_session_stating_only_an_lti_roles_claim_lands_where_the_rows_already_said(
    open_web_door: Any,
    door_contract: Any,
    provider: Any,
    token_endpoint_path: str,
    claims_in_token: Any,
    suite_key_set: Any,
) -> None:
    """**Dies if the web door consults either roles vocabulary.**

    The session states the LIS Instructor role and **nothing at all** in this
    door's own roles claim, and the Care officer behind it lands on `/app/care`
    anyway — because she holds a live `CARE` assignment, ADR 0026's
    `permits_web_login` is true for it, and E1-13 gives no roles claim any say in
    which view a person reaches. SPEC §2: "Entry doors are a property of the
    assignment, not the person", and E1-13's scope is "session identity → that
    person's live assignments filtered by the entered door's permission column →
    landing view".

    **Two mutations die here, in opposite directions.** A door that read the LTI
    vocabulary lands her on the instructor view, or refuses because it serves no
    instructor view at this door — either fails the landing assertion. A door that
    read *this* door's own vocabulary finds nothing there at all, since the
    adjustment removes it, and answers the calm no-access page or a refusal — which
    fails the same assertion. Only a door that reads neither and asks her rows
    lands her on Care.

    **Rewritten by dispute E1-13-01, and the reason is worth having here.** It read
    `test_a_session_stating_only_an_lti_roles_claim_is_refused` and required a 4xx,
    which was the correct assertion while the landing came from a claim. Its own
    docstring named its mirror —
    `test_a_launch_naming_a_web_door_role_and_no_lis_role_is_refused` in
    `tests/integration/test_lti_launch_door.py` — and E1-13's red commit rewrote
    that half to `..._lands_where_the_rows_already_said` and missed this one. There
    is no reading of this ticket under which the launch door stops consulting a
    roles claim and the web door goes on doing it.

    **The security property is stronger, not weaker.** The old test protected
    "an LMS-controlled vocabulary must not choose a screen at this door" by
    checking that such a token was refused; the door had to read the claim to
    refuse on it. Now the claim is not read at all, which is the same movement work
    order D10 records for the launch-door half. E0-09 criterion 10 is the rule
    underneath — "The launch or login establishes who someone is; this table
    establishes what they may do" — and a door that reads no vocabulary cannot be
    talked into anything by one.

    **The other direction of the pair is
    `tests/integration/test_landing_resolves_from_assignments.py::test_a_web_login_by_a_linked_person_holding_no_assignment_lands_on_the_calm_page`**:
    a linked person whose token states a role in *this door's own* vocabulary, and
    who holds no assignment, is answered with the calm page. Together they kill a
    door that reads the foreign vocabulary and a door that reads its own. Neither
    alone does: this one is satisfied by a door that reads its own claim and
    happens to agree with her rows, and that one by a door that reads the LTI claim
    and finds none.

    **The canary is kept and is doing more work than before.** The session the
    provider issued has to have carried this door's own roles claim, or the
    adjustment removed nothing and she would be landing on Care with her own
    vocabulary still present — which is the sibling test above, not this one.
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
        "nothing and this test is not posing the question it names — it would be the sibling "
        "above, a session that still states its own vocabulary."
    )
    landed_with_session(response, door_contract, CARE_ROUTE)


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
    return query_of(
        redirect_target(response, f"a web login was started with login_hint {login_hint!r}")
    )


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
    on `/app/leadership` each time. The hint is presentational: it may change what
    the provider's form pre-selects, and nothing about the session the tool ends up
    with. This is the boundary pair for the security test below: that one proves the
    hint cannot override a *different* identity, and this proves it does not disturb
    the matching one.
    """
    dean = person_holding(provider, "DEAN")
    hint = subject_of(dean)

    hinted = logged_in_with_hint(tool, door_contract, provider, hint, dean)
    landed_with_session(hinted, door_contract, LEADERSHIP_ROUTE)

    plain = logged_in(tool, door_contract, provider, dean)
    landed_with_session(plain, door_contract, LEADERSHIP_ROUTE)


def test_a_login_hint_does_not_decide_which_identity_is_signed_in(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """**Dies if `login_hint` is trusted as the identity** rather than the `id_token`.

    The flow is begun hinting the dean and then signed in, at the provider, as the
    administrator. The session that comes back is the administrator's, so the tool
    must land on `/app/admin` — the hint named the dean and it counts for nothing.
    A tool that read `login_hint` into any security decision would land on
    `/app/leadership` here, granting a caller whatever they wrote in a query
    parameter. Identity is the verified `id_token`'s to state and the hint's never
    (§4.1, and E0-09 criterion 10 for why a caller-chosen role must not stick).

    The two landings are distinct routes, and `landed_with_session` compares the
    whole `Location` prefix rather than searching for a substring, so a redirect to
    the leadership route — or to anything but `/app/admin#session=` — fails here
    whichever of the two identities decided it.
    """
    dean_hint = subject_of(person_holding(provider, "DEAN"))
    administrator = person_holding(provider, "ADMIN")

    response = logged_in_with_hint(tool, door_contract, provider, dean_hint, administrator)

    landed_with_session(response, door_contract, ADMIN_ROUTE)


# ---------------------------------------------------------------------------
# E1-09's error branch: the redirect that carries `error` instead of `code`.
#
# Three answers this door has to keep apart. A refusal whose `state` matches the
# login this browser started is the person who cancelled, and they get the calm
# page. A refusal whose `state` does not match — or that arrives with no login
# cookie to compare against — is a redirect this tool cannot account for, and it
# gets the ordinary refusal. Neither issues a session, neither spends a code, and
# neither repeats a syllable of what it was handed.
#
# The genuine article is driven through the provider rather than typed: E0-30
# taught the mock RFC 6749 §4.1.2.1's error redirects for this, and a `state` the
# provider echoed is a different fact from a `state` this file copied out of a
# dictionary. The variants that a conformant provider will not produce — a
# mismatched `state`, an `error` beside a `code`, an error code outside the
# registry — are delivered to the callback directly, which is exactly the shape
# they arrive in when somebody who is not the provider sends them.
# ---------------------------------------------------------------------------


def error_parameters(location: str | None, what: str) -> dict[str, str]:
    """The query of an authorization error redirect, or a failure saying what came back."""
    assert location, f"The provider sent no redirect at all for {what}."
    returned = query_of(location)
    assert returned.get("error"), (
        f"The provider's answer to {what} carries no `error` (it carries {sorted(returned)}). RFC "
        "6749 §4.1.2.1 puts the code in that parameter, and without one there is no error branch "
        "to deliver."
    )
    return returned


def cancelled_at_the_provider(
    tool: Any, contract: Any, provider: Any
) -> tuple[dict[str, str], dict[str, str]]:
    """One real cancel: begin a login at the tool, and be refused at the provider.

    The tool's own authorization request is carried to the provider, and the login
    form is submitted naming a subject the seed does not carry — which is how a
    cancel is produced through a form that has no cancel control, and which
    `tests/integration/test_mock_idp_error_redirects.py` establishes answers
    `access_denied` with the `state` echoed. Answers both halves: the parameters the
    tool sent, and the parameters the provider sent back.

    Nothing is asserted about the provider's answer here beyond its being an error
    redirect at all — `test_the_cancel_driver_reaches_an_access_denied_redirect_carrying_the_tools_own_state`
    is the control that says this machinery produces the shape it claims to, and it
    must be green for anything below to mean anything.
    """
    parameters = begin(tool, contract)
    attempt = provider.begin_from(list(parameters.items()), "")
    form = provider.require_login_form(attempt)
    submission = dict(provider.offered_identities(attempt)[0])
    submission[provider.identity_field(form)] = UNKNOWN_SUBJECT

    submitted = provider.submit_login(attempt, submission)

    return parameters, error_parameters(
        submitted.location, f"a login naming the unknown subject {UNKNOWN_SUBJECT!r}"
    )


def calm_page(response: Any, contract: Any, what: str) -> None:
    """The person cancelled: E1-09's calm page, and no session anywhere on it.

    Distinct from `refused` in every respect a test can see — the status, the
    testid, and the fact that this one is a page somebody is meant to read rather
    than a refusal. Both are checked, because a door that answered the calm page
    with a 4xx would be right about the words and wrong about the event, and a door
    that answered 200 with the refusal's own body would be the reverse.
    """
    assert response.status_code == 200, (
        f"The tool answered {response.status_code} to {what}. E1-09: a refusal carrying the "
        "`state` this browser was sent is the person cancelling, and it lands them on a calm page "
        f"— HTTP 200, server-rendered. Body begins {response.text[:400]!r}."
    )
    assert CANCELLED_TESTID in response.text, (
        f"The tool answered {what} with a 200 that does not carry `{CANCELLED_TESTID}` (body "
        f"begins {response.text[:400]!r}). That testid is E1-09's contract for the calm page, and "
        "it is what tells this suite — and E1-15's browser proof — that the person was met with "
        "the cancel copy rather than with somebody else's screen."
    )
    found = views_in(response, contract)
    assert not found, (
        f"The tool answered {what} with a page carrying {found}. A cancelled login lands nobody "
        "on a landing view."
    )
    no_session_was_issued(response, what)


def application_log_text(caplog: pytest.LogCaptureFixture) -> str:
    """Everything the application's own loggers said, joined.

    Scoped to the `app.` namespace rather than every record pytest captured, for
    the reason `APPLICATION_LOGGER_ROOT` gives: a library that echoed a URL would
    otherwise decide both the leak assertions and the code assertions below.
    """
    records = [
        record
        for record in caplog.records
        if record.name == APPLICATION_LOGGER_ROOT
        or record.name.startswith(f"{APPLICATION_LOGGER_ROOT}.")
    ]
    return "\n".join(record.getMessage() for record in records)


def token_endpoint_spy(token_endpoint_path: str, seen: list[str]) -> Any:
    """An `around` hook that records every call to the provider's token endpoint.

    The forbidden call, watched at the seam rather than inferred from the answer.
    `docs/MISTAKES.md` entry 2: assert the forbidden state — a door that took the
    error branch and *then* redeemed the code anyway would answer exactly the same
    page, and only this sees it.
    """

    def around(request: Any, deliver: Any) -> Any:
        if urlsplit(str(request.url)).path == token_endpoint_path:
            seen.append(str(request.url))
        return deliver()

    return around


# ---------------------------------------------------------------------------
# The machinery, before anything is asserted with it. Two must-be-green
# controls: a red here means these tests are broken, not that the door is.
# ---------------------------------------------------------------------------


def test_the_cancel_driver_reaches_an_access_denied_redirect_carrying_the_tools_own_state(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """The control for every cancel below: the driver really does produce a cancel.

    **Dies if `cancelled_at_the_provider` stops posing the question it names** —
    if the provider signs the unknown subject in, if it answers a page instead of a
    redirect, if it stops echoing the `state`, or if the tool's own authorization
    request stops reaching it. Each of those turns the tests below into statements
    about a flow that never happened, and every one of them would leave those tests
    *green*, because a callback handed nothing useful refuses, and a refusal is what
    half of them expect.

    Green today and green after the implementer's work: it asserts about the mock
    provider and the tool's login initiation, neither of which E1-09 changes.
    """
    parameters, returned = cancelled_at_the_provider(tool, door_contract, provider)

    assert returned.get("error") == ACCESS_DENIED, (
        f"The provider refused the unknown subject as {returned.get('error')!r} rather than "
        f"{ACCESS_DENIED!r}. RFC 6749 §4.1.2.1 assigns that code to a request the resource owner "
        "or the authorization server denied, and it is the code a cancelling person produces."
    )
    assert returned.get("state") == parameters.get("state"), (
        f"The provider sent back `state` {returned.get('state')!r}; the tool's own authorization "
        f"request carried {parameters.get('state')!r}. The tests below turn on the tool comparing "
        "those two, so a driver that cannot deliver a matching pair cannot ask the question."
    )
    assert "code" not in returned, (
        f"The provider's refusal carries a `code` ({returned.get('code')!r}). An error redirect "
        "grants nothing; a refusal that also issues a code is a different event entirely and the "
        "cancel tests below would be about it."
    )


def test_the_application_log_scan_catches_a_description_planted_in_a_log_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Plants the untrusted description on an `app.` logger and requires the catch.

    **Dies if `application_log_text` is satisfied by emptiness** — no records, the
    wrong namespace, a filter that quietly matches nothing — which is the failure
    mode of every leak scan that has stopped finding anything to look for
    (`docs/MISTAKES.md` entry 9: a guard nobody has watched catch its own case is a
    comment). Needs no implementation: it is green now, and if it is not, the
    silence of the log assertions below means nothing whatever they report.
    """
    planted = f"{APPLICATION_LOGGER_ROOT}.e1_09_log_scan_control"
    caplog.set_level(logging.DEBUG)

    logging.getLogger(planted).warning(
        "a refusal line that deliberately repeats what it was handed: %s", UNTRUSTED_DESCRIPTION
    )

    text = application_log_text(caplog)
    assert UNTRUSTED_DESCRIPTION in text, (
        f"The scan read {text!r} from the `{APPLICATION_LOGGER_ROOT}.` namespace and did not find "
        f"{UNTRUSTED_DESCRIPTION!r}, which was just logged there. Every assertion below that a "
        "description did *not* reach a log line is worthless until this passes."
    )


# ---------------------------------------------------------------------------
# The calm page, and the refusal it must not be confused with. Criterion 2's
# integration half and the whole of criterion 3, in pairs.
# ---------------------------------------------------------------------------


def test_a_cancelled_login_whose_state_matches_shows_the_calm_page_and_issues_no_session(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """Criterion 2, and criterion 3's accepting direction. The user cancelled.

    A real cancel, driven through the provider, delivered to the callback the
    browser would have carried it to. **Dies if the door has no error branch at
    all** — today it reads `code`, finds none, and refuses, which is fail-closed and
    is not what the person is owed. **Dies if it issues a session anyway**, which
    `no_session_was_issued` checks in all three places a session could leave: the
    two cookies, the `Location`, and the body.

    Its pair is every refusal below: this is the one case in the whole section
    where the answer is 200, and the three that differ from it by exactly one
    thing — a `state` that does not match, no `state`, no cookie — must not reach
    it.
    """
    _, returned = cancelled_at_the_provider(tool, door_contract, provider)

    response = tool.get(door_contract.oidc_callback, params=returned)

    calm_page(response, door_contract, "a login the person cancelled at the provider")


def test_an_error_redirect_carrying_a_state_the_tool_never_issued_is_refused_not_calmed(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """Criterion 3: the forged error redirect, refused **distinctly** from a real cancel.

    The redirect is a real one — the provider's own `error`, produced by a real
    refusal — and the single thing wrong with it is a `state` this tool never sent.
    That is the shape an attacker sends: a browser that has a login in flight is
    handed somebody else's refusal, and a door that reads `error` and renders the
    calm page without comparing anything shows the cancel copy to a person who
    cancelled nothing, having accepted a redirect it cannot account for.

    **Dies if `state` is checked only when present, or not checked on this branch.**
    Both halves are asserted rather than the status alone: `refused` covers the 4xx
    and the absent session, and the calm testid must be absent, because "refused
    distinctly" is a claim about the two answers being different and a door that
    served the calm page with a 400 would satisfy a status-only check.
    """
    _, returned = cancelled_at_the_provider(tool, door_contract, provider)
    forged = {**returned, "state": "a-state-this-tool-never-issued"}

    response = tool.get(door_contract.oidc_callback, params=forged)

    refused(response, door_contract, "an error redirect carrying a `state` the tool never issued")
    assert CANCELLED_TESTID not in response.text, (
        f"The tool answered an error redirect whose `state` it never issued with a page carrying "
        f"`{CANCELLED_TESTID}`. E1-09 keeps the two apart: the calm page says 'you cancelled', and "
        "this browser cancelled nothing — somebody handed it a refusal belonging to another flow, "
        "or to none."
    )


def test_an_error_redirect_carrying_no_state_at_all_is_refused_not_calmed(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """The absent case, which the mismatch above does not cover.

    `if state and state != carried` passes the test above and fails this one, and
    sending nothing is how that defence is defeated. A different mutation is a
    different case — the same pair the `code` branch already carries
    (`test_a_callback_carrying_no_state_at_all_is_refused`), now on the branch that
    has never had it.
    """
    _, returned = cancelled_at_the_provider(tool, door_contract, provider)
    stateless = {name: value for name, value in returned.items() if name != "state"}

    response = tool.get(door_contract.oidc_callback, params=stateless)

    refused(response, door_contract, "an error redirect carrying no `state` at all")
    assert CANCELLED_TESTID not in response.text, (
        f"The tool answered an error redirect carrying no `state` with `{CANCELLED_TESTID}`. "
        "Nothing was compared, so nothing is known about which login this belongs to."
    )


def test_an_error_redirect_delivered_without_the_login_cookie_is_refused_not_calmed(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """The other side of the comparison: the carried value, rather than the returned one.

    Exactly one thing differs from the calm-page test — the browser is not carrying
    the login cookie — so this separates "the returned `state` looks plausible" from
    "the returned `state` matches the one this browser was actually sent". **Dies if
    an absent or unreadable cookie is treated as a match**, which is what a
    comparison against an empty default does, and which would make every forged
    error redirect a calm page for any browser with no login in flight.

    The cookie is cleared on the client rather than never set, so the flow that
    produced this `state` is the same real flow the calm-page test drives: the
    difference is what the browser sends back, which is the caller's to choose.
    """
    _, returned = cancelled_at_the_provider(tool, door_contract, provider)
    tool.cookies.clear()

    response = tool.get(door_contract.oidc_callback, params=returned)

    refused(response, door_contract, "an error redirect delivered with no login cookie")
    assert CANCELLED_TESTID not in response.text, (
        f"The tool answered an error redirect from a browser carrying no login cookie with "
        f"`{CANCELLED_TESTID}`. There was nothing to compare the returned `state` against, so this "
        "is a redirect the tool cannot account for rather than a cancel it can."
    )


def test_an_error_redirect_carrying_a_code_as_well_never_reaches_the_token_endpoint(
    open_web_door: Any, door_contract: Any, provider: Any, token_endpoint_path: str
) -> None:
    """Criterion 3: `error` wins over `code`, and the code is not spent.

    A conformant provider sends one or the other. This sends both — a real code, one
    the provider genuinely issued for this tool, beside an `error` — because a door
    that looks for `code` first will find one, redeem it, and hand out a session for
    a flow it was told had failed. Fail-safe means the error branch is taken before
    anything else is read.

    **Asserted at the seam, not inferred from the page.** The forbidden thing here
    is a *call*, and a door that redeemed the code and then discarded the token
    would answer exactly the same page as one that never called at all
    (`docs/MISTAKES.md` entry 2). Its pair is the next test, which shows this same
    spy seeing the call when the callback is supposed to make one — without that,
    `not seen` is satisfied by a spy wired to nothing.
    """
    seen: list[str] = []
    tool = open_web_door(around=token_endpoint_spy(token_endpoint_path, seen))

    parameters = begin(tool, door_contract)
    submitted = sign_in(provider, parameters, person_holding(provider, "DEAN"))

    response = tool.get(
        door_contract.oidc_callback,
        params={"code": submitted.code, "state": submitted.state, "error": ACCESS_DENIED},
    )

    assert not seen, (
        f"The tool redeemed its code at the token endpoint ({seen}) while answering a callback "
        f"that stated `error={ACCESS_DENIED}`. The provider said this login failed; spending the "
        "code anyway means an unauthenticated caller can make this tool burn a code, and — if the "
        "exchange succeeds — that `error` decides nothing at all."
    )
    calm_page(response, door_contract, "an error redirect that also carried a code")


def test_a_callback_carrying_a_code_and_no_error_does_reach_the_token_endpoint(
    open_web_door: Any, door_contract: Any, provider: Any, token_endpoint_path: str
) -> None:
    """The control for the test above: the same spy, on the flow that must call.

    **This is what makes `not seen` mean "the door refused to redeem" rather than
    "the spy sees nothing".** One parameter differs between the two tests — the
    `error` — and everything else, the tool, the seam, the spy and the code, is the
    same. A spy watching the wrong path, an `around` hook the fixture never
    installed, or a token endpoint the tool stopped calling would leave that test
    passing and this one failing, which is exactly the direction the information
    should point (`docs/MISTAKES.md` entry 35: require the guard to find the thing
    on a subject that certainly has it).
    """
    seen: list[str] = []
    tool = open_web_door(around=token_endpoint_spy(token_endpoint_path, seen))

    parameters = begin(tool, door_contract)
    submitted = sign_in(provider, parameters, person_holding(provider, "DEAN"))

    response = tool.get(
        door_contract.oidc_callback, params={"code": submitted.code, "state": submitted.state}
    )

    assert seen, (
        "The tool redeemed nothing at the token endpoint on a callback carrying a valid `code` and "
        "a matching `state`. Either this spy watches a path the tool does not call, or the happy "
        "path has stopped exchanging its code — and until this passes, the `error`-wins test above "
        "proves nothing."
    )
    landed_with_session(response, door_contract, LEADERSHIP_ROUTE)


# ---------------------------------------------------------------------------
# What the error branch may repeat, and what it may not: `error_description`
# and `error_uri` are attacker-chosen text; the code is a value from a
# four-member set.
# ---------------------------------------------------------------------------


def test_the_calm_page_never_repeats_the_error_description_or_error_uri(
    tool: Any, door_contract: Any, provider: Any
) -> None:
    """Criterion 3: nothing attacker-supplied is echoed to the browser.

    **Dies if either value reaches the response** — rendered into the page, put in a
    header, or reflected in a redirect. RFC 6749 §4.1.2.1 puts no grammar on either,
    so both are text somebody else wrote, and a page that repeats them is a page
    whose words an attacker chooses: "your account is locked, call this number" over
    the tool's own name and styling, with a link of their choosing beside it.

    Two guards, because this is the shape that passes on emptiness. The calm page
    has to render, so a 404 or a blank body fails rather than passes; and the scan
    is shown finding both markers in a sample built out of them, so a comparison
    that has gone blind says so (`docs/MISTAKES.md` entry 3). The whole response is
    read, headers included, not the body alone.
    """
    _, returned = cancelled_at_the_provider(tool, door_contract, provider)
    hostile = {
        **returned,
        "error_description": UNTRUSTED_DESCRIPTION,
        "error_uri": UNTRUSTED_ERROR_URI,
    }

    response = tool.get(door_contract.oidc_callback, params=hostile)

    calm_page(response, door_contract, "a cancel carrying an untrusted description and URI")
    untrusted = (UNTRUSTED_DESCRIPTION, UNTRUSTED_ERROR_URI)
    canary = " ".join(untrusted)
    assert all(marker in canary for marker in untrusted), (
        "The scan below cannot find these markers in a sample built out of them, so its silence "
        "about the calm page means nothing."
    )
    received = "\n".join([*(f"{n}: {v}" for n, v in response.headers.items()), response.text])
    echoed = sorted(marker for marker in untrusted if marker in received)
    assert not echoed, (
        f"The calm page repeats {echoed} back to the browser. Body begins "
        f"{response.text[:400]!r}. E1-09: `error_description` and `error_uri` are untrusted text — "
        "never rendered, never echoed. The page says what happened in the tool's own words."
    )


@pytest.mark.parametrize("code", LOGGED_ERROR_CODES)
def test_the_error_branch_logs_the_registered_code_and_never_the_description(
    tool: Any, door_contract: Any, provider: Any, caplog: pytest.LogCaptureFixture, code: str
) -> None:
    """Criterion 3: the log line carries the error code, and nothing else it was handed.

    All four members of E1-09's set, one case each, because a closed set is only a
    closed set if each member is shown going through it — a door that recognised
    `access_denied` and called the other three unrecognised would pass a
    single-value test and lose the operator three of the four things this line
    exists to tell them (`docs/MISTAKES.md` entry 35). The near miss is the next
    test, and the pair is the point: without it "log the code" is satisfied by
    echoing whatever arrives.

    **Dies if the description reaches the log.** A log line is not a safe place for
    attacker-chosen text: it is read by an operator, aggregated, and searched, and
    it is where an injected line goes to be believed. §10's no-PII rule is the same
    rule from the other end.
    """
    caplog.set_level(logging.DEBUG)
    _, returned = cancelled_at_the_provider(tool, door_contract, provider)
    hostile = {
        **returned,
        "error": code,
        "error_description": UNTRUSTED_DESCRIPTION,
        "error_uri": UNTRUSTED_ERROR_URI,
    }

    tool.get(door_contract.oidc_callback, params=hostile)

    logged = application_log_text(caplog)
    assert code in logged, (
        f"No log line from the `{APPLICATION_LOGGER_ROOT}.` namespace names {code!r}. Captured: "
        f"{logged!r}. E1-09 lets the log repeat the error code, and only the error code — an "
        "operator who cannot tell `access_denied` from `invalid_scope` cannot tell a person "
        "cancelling from the tool being misconfigured."
    )
    leaked = sorted(
        marker for marker in (UNTRUSTED_DESCRIPTION, UNTRUSTED_ERROR_URI) if marker in logged
    )
    assert not leaked, (
        f"The log carries {leaked}, which arrived in the query string of an error redirect. "
        f"Captured: {logged!r}. E1-09: the log line carries only the error code."
    )


@pytest.mark.parametrize("case", sorted(CODES_OUTSIDE_THE_SET))
def test_an_error_code_outside_the_set_is_logged_as_unrecognized_and_never_echoed(
    tool: Any, door_contract: Any, provider: Any, caplog: pytest.LogCaptureFixture, case: str
) -> None:
    """The near misses for the four above: three values that are not one of them.

    **This is what makes those four mean "recognised" rather than "echoed".** The
    `error` parameter is as attacker-chosen as the description is; a door that
    writes it into a log line verbatim has the same log-injection surface, reached
    through the one parameter it was allowed to repeat. So the set is closed by
    exact comparison, and everything else logs one fixed word.

    **Three values, because "exact" has three ways of being not quite exact**, and
    a single stranger distinguishes none of them — the first version of this test
    sent only a code sharing no prefix and no case variant with any set member, and
    the mutation battery walked past both of the comparisons below.

      - `a code from outside the registry` kills a comparison dropped altogether:
        `error` written to the log with no set consulted.
      - `a case variant of a set member` kills `error.lower() in LOGGED_ERROR_CODES`
        and every other case-fold. `ACCESS_DENIED` is not `access_denied`: RFC 6749
        §4.1.2.1 spells its codes in one case and nothing obliges a caller to.
      - `a set member with an injected tail` kills
        `any(error.startswith(known) for known in ...)` and the `in`-a-string
        substring test. The tail is what a prefix comparison would carry into the
        log — a second line, reading as a record of its own, which is the reason
        `backend/app/api/auth.py`'s own module comment gives for the set existing.

    Each is caught by the *first* assertion rather than the echo check, and that is
    worth knowing when one goes red: under either loose comparison the door
    recognises the value and logs a code, so the word `unrecognized` never appears.
    The echo assertions below it are the second net, for a comparison that answers
    "outside" and repeats the string anyway.
    """
    sent = CODES_OUTSIDE_THE_SET[case]
    caplog.set_level(logging.DEBUG)
    _, returned = cancelled_at_the_provider(tool, door_contract, provider)
    hostile = {**returned, "error": sent, "error_description": UNTRUSTED_DESCRIPTION}

    tool.get(door_contract.oidc_callback, params=hostile)

    logged = application_log_text(caplog)
    assert UNRECOGNISED_CODE_LOGGED_AS in logged, (
        f"No log line from the `{APPLICATION_LOGGER_ROOT}.` namespace carries "
        f"{UNRECOGNISED_CODE_LOGGED_AS!r} for {case} ({sent!r}). Captured: {logged!r}. E1-09 "
        f"compares `error` to {list(LOGGED_ERROR_CODES)} exactly and logs that literal word for "
        "everything else — so a door that answered `unrecognized` for a plain stranger and not "
        "for this one is matching on a prefix, a substring or a case-fold, and its set is not "
        "closed."
    )
    assert sent not in logged, (
        f"The log repeats {sent!r} ({case}) verbatim. Captured: {logged!r}. That parameter is "
        "attacker-chosen text exactly as `error_description` is, and repeating it is the "
        "log-injection surface the closed set exists to remove."
    )
    assert UNTRUSTED_DESCRIPTION not in logged, (
        f"The log carries {UNTRUSTED_DESCRIPTION!r} alongside an unrecognised code. Captured: "
        f"{logged!r}."
    )


# ---------------------------------------------------------------------------
# One login buys one attempt. Both error-branch answers burn the login cookie.
# ---------------------------------------------------------------------------


def test_the_calm_page_burns_the_login_cookie_so_the_matching_code_cannot_be_redeemed_after(
    open_web_door: Any, door_contract: Any, provider: Any, token_endpoint_path: str
) -> None:
    """The calm page clears the login cookie on the way out. Criterion 2's second half.

    **Dies if the error branch renders and returns without clearing.** The cookie
    holds the `state`, the `nonce` and the PKCE verifier — the one secret binding an
    authorization code to this client — and a browser that still carries it after
    the flow has ended is one an attacker gets as many attempts against as they
    like. E0-18 made the refusal path burn it; E1-09 adds a second way out of the
    flow, and a new exit that skips the cleanup is exactly how that guarantee is
    quietly lost.

    Asserted behaviourally rather than by reading a `Set-Cookie`: what matters is
    that the login is over, and the way to show that is that the *correct* code and
    `state` for the same login are refused afterwards. Guarded, because that
    refusal could otherwise be a spent code rather than a burned cookie — the spy
    says the calm page redeemed nothing, so the code is still unspent when it is
    delivered.
    """
    seen: list[str] = []
    tool = open_web_door(around=token_endpoint_spy(token_endpoint_path, seen))

    parameters = begin(tool, door_contract)
    submitted = sign_in(provider, parameters, person_holding(provider, "DEAN"))

    calmed = tool.get(
        door_contract.oidc_callback,
        params={"state": submitted.state, "error": ACCESS_DENIED},
    )
    calm_page(calmed, door_contract, "a cancel carrying the state of a login still in flight")
    assert not seen, (
        f"The calm page redeemed the code at the token endpoint ({seen}), so the refusal below "
        "could be a code that has already been spent rather than a cookie that was burned."
    )

    replayed = answer_to(
        lambda: complete(tool, door_contract, submitted),
        "the correct `code` and `state` for a login the calm page should have ended",
    )

    assert 400 <= replayed.status_code < 500, (
        f"After showing the calm page, the tool answered {replayed.status_code} to the correct "
        "`code` and `state` for the same login. One login buys one attempt: the cookie holding the "
        "state, the nonce and the PKCE verifier is cleared on the way out of the error branch, and "
        "a branch that leaves it in place leaves the verifier live in a browser that has finished "
        "with it."
    )
    no_session_was_issued(replayed, "a code replayed after the calm page")


def test_a_refused_error_redirect_burns_the_login_cookie_too(
    open_web_door: Any, door_contract: Any, provider: Any, token_endpoint_path: str
) -> None:
    """The pair to the test above, on the branch that refuses rather than calms.

    **Dies if only one of the two exits clears the cookie**, which is the likely
    shape of the mistake: the calm page is the branch a developer is thinking about
    when they write the cleanup, and the mismatched-`state` path is the one that
    falls out of an `else`. It is also the branch where leaving the cookie live
    matters most — an attacker who can deliver one forged error redirect can deliver
    a hundred, and every one of them is a free attempt at a browser that is still
    carrying the verifier.

    Same guard as above: the refusal must not have spent the code, or the second
    refusal says nothing about the cookie.
    """
    seen: list[str] = []
    tool = open_web_door(around=token_endpoint_spy(token_endpoint_path, seen))

    parameters = begin(tool, door_contract)
    submitted = sign_in(provider, parameters, person_holding(provider, "DEAN"))

    rejected = tool.get(
        door_contract.oidc_callback,
        params={"state": "a-state-this-tool-never-issued", "error": ACCESS_DENIED},
    )
    refused(rejected, door_contract, "an error redirect carrying a `state` the tool never issued")
    assert not seen, (
        f"The refusal redeemed the code at the token endpoint ({seen}), so the refusal below could "
        "be a spent code rather than a burned cookie."
    )

    replayed = answer_to(
        lambda: complete(tool, door_contract, submitted),
        "the correct `code` and `state` for a login a refused error redirect should have ended",
    )

    assert 400 <= replayed.status_code < 500, (
        f"After refusing an error redirect it could not account for, the tool answered "
        f"{replayed.status_code} to the correct `code` and `state` for the login that browser had "
        "in flight. Both ways out of the error branch clear the single-use cookie."
    )
    no_session_was_issued(replayed, "a code replayed after a refused error redirect")
