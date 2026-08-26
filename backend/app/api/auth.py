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
"""

import base64
import hashlib
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

    The cookie is cleared whichever way this goes. A `state` is good once, and
    the provider has already spent the code.
    """
    settings: Settings = request.app.state.settings
    carried = carried_across(request.app.state.login_secret, request.cookies.get(OIDC_LOGIN_COOKIE))

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
        answer: Response = refused(str(refusal))
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
