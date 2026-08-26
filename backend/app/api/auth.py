"""The web door: `GET /auth/oidc/login` and `GET /auth/oidc/callback` (E0-18, E1-09).

SPEC §2 gives every role except instructor and student a second way in, and
E0-16 built the provider it goes through. This module is the tool's half: an
OAuth 2.0 authorization code flow with PKCE, issuing the session
`app.services.session` defines and redirecting to the route the caller's
**verified** roles claim names.

**A new module, and §13 does not name it.** §13's `api/` list is
`deps.py, lti.py, student.py, instructor.py, leadership.py, care.py, admin.py` —
every one of them a screen's router except the first two, and a web login is not
a screen. `lti.py` is the wrong home because this is not LTI at all, and putting
it in `admin.py` would tie the one door Care and leadership use to the admin
console. So: a module, because nothing fits, and this paragraph is the "the PR
says so" E0-18 asks for.

**The OIDC client is here rather than in `services/`**, which is the other thing
§13 would have supported. It is about eighty lines and has exactly one caller,
and a service module with one caller in one router is a layer rather than a
boundary. It moves the day a second thing redeems a code.

**The client is public: it holds no secret and PKCE is what binds a code to
it.** RFC 7636 with `S256`, never `plain` — `plain` puts the verifier itself in
the redirect a browser writes to its history, which is the one place PKCE exists
to keep it out of. E0-16's provider refuses anything else, so an omission here
would surface as a flow that does not complete rather than as a downgrade.

**The callback URL carries `code`, so a browser writes it into its history.**
E0-18 named this and expected E1's session model to end it; it does not, quite,
because the browser records the address it navigated to whatever that address
answers with. What E1-09 changes is everything downstream: the code in that
history entry is spent, single-use at the provider, and bound to a PKCE verifier
this browser no longer holds — the login cookie is cleared on every way out of
the callback — and the session itself never appears in a URL a browser writes
down, because `fragment_redirect` hands it over in a fragment, which reaches
neither an access log nor a `Referer` header.

**A redirect that carries `error` is a first-class branch, not a missing `code`
(E1-09).** The person cancelled, or the provider declined for them. RFC 6749
§4.1.2.1 says that answer arrives at this same callback, and the branch is taken
before anything else is read: the token endpoint is never called and no code is
ever spent on it, even when a caller sends `error` and `code` together. Which of
two answers the caller gets turns on the returned `state` — a matching one is
this browser's own cancelled login and gets the calm page, anything else is a
redirect this tool cannot account for and gets the ordinary refusal — and what
either answer repeats is nothing: `error_description` and `error_uri` are text
somebody else wrote, and the log line carries the error code alone, and only when
it is one of four known values.
"""

import base64
import hashlib
import logging
import secrets
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from starlette.responses import Response

from app.api.deps import (
    FOUND,
    OIDC_LOGIN_COOKIE,
    cancelled,
    carried_across,
    carry_across,
    clear_carried,
    landing_with_session,
    refused,
    with_query,
)
from app.config import Settings
from app.services.landing import Door
from app.services.tokens import TokenVerificationError, same_opaque_value, verified_claims

router = APIRouter(tags=["auth"])

# This module's own logger, under the `app.` namespace every application logger
# lives in (`app.lti.launch` is the established spelling for a door's).
logger = logging.getLogger(__name__)

# Where this tool answers. The provider's registered redirect URI is built from
# `PUBLIC_BASE_URL` plus `CALLBACK_PATH`, and `mock-idp/app/config.py` defaults
# to the same path, which is what makes the stack work unconfigured.
LOGIN_PATH = "/auth/oidc/login"
CALLBACK_PATH = "/auth/oidc/callback"

# What the tool asks the provider for. `code` because a code flow is the only one
# that keeps the token off the browser's URL bar and out of its history;
# `openid` because that is what makes the response an OpenID Connect one at all
# (OIDC Core 1.0 §3.1.2.1) and without it there is no `id_token` to read a role
# out of. `email` is asked for because E0-18 says to; nothing renders it, and the
# landing pages carry no identifier of any kind.
RESPONSE_TYPE = "code"
SCOPE = "openid email"

# RFC 7636's only challenge method worth using, and the only one E0-16's provider
# accepts.
CODE_CHALLENGE_METHOD = "S256"

# Bytes behind the verifier, the state and the nonce. 32 urlsafe bytes is 43
# characters, which is exactly RFC 7636 §4.1's minimum verifier length and is
# drawn from its unreserved alphabet.
OPAQUE_VALUE_BYTES = 32

# How long the tool waits for the token endpoint. Not a setting, for the reason
# `app.services.tokens` gives about the key-set timeout: this request happens
# inside a browser redirect, and there is one right answer.
TOKEN_TIMEOUT_SECONDS = 10.0

# The error codes this tool will repeat in a log line, compared exactly. Four of
# RFC 6749 §4.1.2.1's registry: the ones that tell an operator something they can
# act on — somebody declined (`access_denied`), or this tool's own authorization
# request is malformed, asks for a response type the provider will not issue, or
# asks for a scope it will not grant. Everything else, including the registry's
# remaining members, logs `UNRECOGNISED_ERROR_CODE` instead.
#
# **A closed set, and closed by exact membership.** `error` is as attacker-chosen
# as `error_description` is — anyone who can put a browser in front of this
# callback writes it — so a door that wrote it into a log line verbatim would have
# handed over a log-injection surface through the one parameter it was allowed to
# repeat. A prefix, substring or case-folded comparison is the same hole with more
# steps. Widening the set is a decision with a test behind it, not a line to edit.
LOGGED_ERROR_CODES = frozenset(
    {"invalid_request", "access_denied", "unsupported_response_type", "invalid_scope"}
)
UNRECOGNISED_ERROR_CODE = "unrecognized"


class SessionRefusedError(Exception):
    """A web login cannot be admitted, and why. Carries no token and no claim."""


def callback_url(settings: Settings) -> str:
    """This tool's own callback, from configuration and never from the request.

    The provider compares it exactly, twice — once when the authorization request
    arrives and again when the code is redeemed — so a value taken from the
    incoming `Host` header would be a redirect URI the caller chose, and the
    mistake is invisible behind a correctly configured reverse proxy.
    """
    return f"{settings.public_base_url.rstrip('/')}{CALLBACK_PATH}"


def pkce_pair() -> tuple[str, str]:
    """A verifier and the `S256` challenge derived from it (RFC 7636 §4.1, §4.2)."""
    verifier = secrets.token_urlsafe(OPAQUE_VALUE_BYTES)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def redeem(settings: Settings, http: httpx.Client, code: str, verifier: str) -> str:
    """Exchange an authorization code for the `id_token` it stands for.

    **Server-side, through `app.state.http`**, which is the point of the code
    flow: the token never touches the browser. The verifier goes with it and is
    the only thing proving this is the client that asked for the code, since a
    public client has no secret to present.
    """
    try:
        answered = http.post(
            settings.oidc_token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.oidc_client_id,
                "redirect_uri": callback_url(settings),
                "code_verifier": verifier,
            },
            timeout=TOKEN_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as failure:
        raise SessionRefusedError(
            f"The identity provider's token endpoint could not be reached "
            f"({type(failure).__name__})."
        ) from failure

    if answered.status_code != 200:
        # The provider's own `error` code is not repeated back: RFC 6749 §5.2
        # writes it for a client library, and on a page it would tell an
        # unauthenticated caller which half of their forgery was wrong.
        raise SessionRefusedError(
            "The identity provider would not exchange that authorization code."
        )

    try:
        body = answered.json()
    except ValueError as failure:
        raise SessionRefusedError(
            "The identity provider's token response is not JSON."
        ) from failure

    token = body.get("id_token") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        raise SessionRefusedError(
            "The identity provider's token response carries no `id_token`, so it granted no "
            "session (OIDC Core 1.0 §3.1.3.3)."
        )
    return token


def verified_session(
    settings: Settings,
    http: httpx.Client,
    code: str,
    state: str,
    carried: dict[str, Any] | None,
) -> dict[str, Any]:
    """The claims of a web login this tool is willing to act on.

    `state` is compared **first**, before the code is spent: a callback carrying
    a `state` this tool never issued is one nobody here started, and redeeming
    its code would be this tool completing somebody else's flow.
    """
    if carried is None:
        raise SessionRefusedError(
            "This callback carries no login this tool started, so there is nothing to check its "
            "`state` and `nonce` against. It may simply have taken too long."
        )

    expected_state = str(carried.get("state") or "")
    if not state or not expected_state:
        raise SessionRefusedError(
            "The callback carries no `state`, which every callback must return."
        )
    if not same_opaque_value(state, expected_state):
        raise SessionRefusedError("The callback returns a `state` this tool did not issue.")

    if not code:
        raise SessionRefusedError(
            "The callback carries no `code`, so there is nothing to exchange."
        )

    token = redeem(settings, http, code, str(carried.get("verifier") or ""))

    try:
        claims = verified_claims(
            http,
            token,
            jwks_url=settings.oidc_jwks_url,
            issuer=settings.oidc_issuer,
            audience=settings.oidc_client_id,
        )
    except TokenVerificationError as refusal:
        raise SessionRefusedError(str(refusal)) from refusal

    expected_nonce = str(carried.get("nonce") or "")
    delivered_nonce = str(claims.get("nonce") or "")
    if not delivered_nonce or not expected_nonce:
        raise SessionRefusedError(
            "The session carries no `nonce`, which every session must return."
        )
    if not same_opaque_value(delivered_nonce, expected_nonce):
        raise SessionRefusedError("The session returns a `nonce` this tool did not send.")

    return claims


def loggable_error_code(error: str) -> str:
    """The error code as it may be written to a log, or the one word that stands in.

    The whole of what makes `LOGGED_ERROR_CODES` a closed set: exact membership,
    one fixed word for everything else, and no path by which a string the caller
    chose reaches a log line.
    """
    return error if error in LOGGED_ERROR_CODES else UNRECOGNISED_ERROR_CODE


def cancelled_or_refused(error: str, state: str, carried: dict[str, Any] | None) -> Response:
    """The answer to a callback that came back carrying `error` (E1-09).

    Two answers, and the returned `state` is what decides between them. A `state`
    that matches the login this browser started is the person who cancelled — or a
    provider that declined for them — and they get the calm page: this browser
    began the login that was refused, so the refusal is an account of something it
    did. Anything else is a redirect this tool cannot account for and gets the
    ordinary refusal: a mismatched `state`, no `state` at all, or no readable login
    cookie to compare one against. **An absent value is never a match** — both
    sides have to be there and be equal — because a comparison against an empty
    default would calm every browser with no login in flight, which is precisely
    the browser an attacker sends a forged error redirect to.

    `same_opaque_value` is the one comparison helper for this: constant-time, and
    with an answer rather than a `TypeError` for a `state` outside ASCII
    (`docs/MISTAKES.md` entry 13 — the same hazard the `code` branch already
    works around, and a second copy of the workaround is how one of the two gets
    it wrong).

    **One log line, written before the comparison**, so both ways out of this
    branch are visible and neither can be the one somebody forgets. It carries the
    error code and nothing else — not `error_description`, not `error_uri`, and not
    a code from outside the closed set. `warning` rather than `info` because this
    application configures no logging at all, so an `info` line is one no operator
    would ever see.
    """
    logger.warning("A web login came back refused by the provider: %s", loggable_error_code(error))

    expected = str((carried or {}).get("state") or "")
    if state and expected and same_opaque_value(state, expected):
        return cancelled()
    return refused(
        "That sign-in came back refused by the identity provider, and this tool cannot tell which "
        "sign-in it belongs to. Nobody has been signed in. Start again from where you opened Pulse "
        "Surveys."
    )


@router.get(LOGIN_PATH, summary="Start a web login against the identity provider")
def begin_web_login(request: Request) -> Response:
    """Send the browser to the provider with a fresh state, nonce and challenge.

    All three are per flow. A reused `state` is no cross-site request forgery
    defence, a reused `nonce` makes every session a replay of the last, and a
    reused challenge means one verifier opens every code this tool ever gets —
    and every one of the three validates perfectly inside any single flow, so
    nothing but freshness itself can catch a constant.

    Synchronous, and it touches nothing: no database, no network. FastAPI runs it
    in its threadpool, which is where the two blocking things it does not do
    would have run.
    """
    settings: Settings = request.app.state.settings
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(OPAQUE_VALUE_BYTES)
    nonce = secrets.token_urlsafe(OPAQUE_VALUE_BYTES)

    parameters = {
        "response_type": RESPONSE_TYPE,
        "scope": SCOPE,
        "client_id": settings.oidc_client_id,
        "redirect_uri": callback_url(settings),
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": CODE_CHALLENGE_METHOD,
    }
    # `login_hint` is presentational only (OIDC Core 1.0 §3.1.2.1): forwarded so
    # the provider's form can pre-select a person, it never touches state, nonce
    # or PKCE, and it is never read into any security decision — the identity
    # still comes from the verified id_token at the callback. Absent when the
    # caller sent none, so no constant is ever injected.
    login_hint = request.query_params.get("login_hint")
    if login_hint:
        parameters["login_hint"] = login_hint

    authorization_url = with_query(settings.oidc_authorization_endpoint, parameters)
    response = RedirectResponse(authorization_url, status_code=FOUND)
    carry_across(
        response,
        OIDC_LOGIN_COOKIE,
        request.app.state.login_secret,
        {"state": state, "nonce": nonce, "verifier": verifier},
        settings,
    )
    return response


@router.get(CALLBACK_PATH, summary="Finish a web login and issue a session")
async def finish_web_login(request: Request) -> Response:
    """Redeem the code, verify the session, and hand it over — or answer the refusal.

    `async def` for the reason `app.api.lti` gives at length: the exchange and
    the key-set fetch are synchronous, and `run_in_threadpool` is what keeps them
    off the event loop.

    **`error` is read first, and a redirect carrying one goes no further.** RFC
    6749 §4.1.2.1 says a provider sends `error` *or* `code`, never both, so a
    callback carrying both is one nobody conformant sent — and a door that looked
    for `code` first would find one, redeem it, and hand out a session for a login
    it had just been told had failed. Taking the branch first is what makes that
    impossible rather than unlikely: on this path the token endpoint is not
    reached and no code is spent.

    The cookie is cleared whichever way this goes — all three ways, now. A `state`
    is good once; the provider has already spent the code; and the branch a person
    cancelled on is exactly the one where an uncleared cookie leaves the PKCE
    verifier live in a browser that has finished with it.
    """
    settings: Settings = request.app.state.settings
    carried = carried_across(request.app.state.login_secret, request.cookies.get(OIDC_LOGIN_COOKIE))

    error = request.query_params.get("error")
    if error:
        answer: Response = cancelled_or_refused(
            error, request.query_params.get("state") or "", carried
        )
        clear_carried(answer, OIDC_LOGIN_COOKIE)
        return answer

    try:
        claims = await run_in_threadpool(
            verified_session,
            settings,
            request.app.state.http,
            request.query_params.get("code") or "",
            request.query_params.get("state") or "",
            carried,
        )
    except SessionRefusedError as refusal:
        answer = refused(str(refusal))
        clear_carried(answer, OIDC_LOGIN_COOKIE)
        return answer

    landed = landing_with_session(
        claims,
        door=Door.WEB,
        settings=settings,
        secret=request.app.state.session_secret,
        no_role_reason=(
            "That sign-in states no role this tool has a view for, so there is nothing to show "
            "you. SPEC §2 gives instructors and students the LMS launch rather than this door."
        ),
    )
    clear_carried(landed, OIDC_LOGIN_COOKIE)
    return landed
