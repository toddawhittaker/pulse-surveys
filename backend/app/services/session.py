"""The session both entry doors issue and every later request reads — ticket E1-08.

The launch door (`app.api.lti`) issues a session here once a launch verifies; the
web door (E1-09) issues the same session type; E1-12 later gives a session its
stored identity. It lives in `services/` rather than in `lti/` because both doors
share it, and it is deliberately small: a signed statement of who arrived, at
which door, in what role — no name, no email, no `lms_user_id`, only the opaque
`sub` the launch already carried (SPEC §8, §10).

**A single symmetric secret, HS256, algorithm passed explicitly both ways.** The
tool issues this token and the tool verifies it, so a symmetric key is the right
shape — unlike the asymmetric platform key `app.services.tokens` verifies. The
key is a `session_secret` setting (`app.config`, ADR 0089): one value shared by
the `api` container and any future replica, so a restart does not log a sitting
person out (which the retired per-process login cookie did, ADR 0078). The
algorithm is named on `jwt.encode` and on `jwt.decode` alike — a verifier that
read `alg` off the token's own header would accept `none` from anyone who can
write a token, which for a browser-held credential is everyone (ADR 0073's
closing condition, applied to this module).

**Sixty minutes** (ADR 0089): one class period or report-review sitting, no
refresh flow designed in E1, and a bound on how long a token the SPA holds in
`sessionStorage` is worth stealing.

**The cookieless survival mechanism.** A launch runs the tool inside the LMS's
cross-site iframe for the whole visit, where a `SameSite=Lax` cookie is dropped
on every in-iframe request and a `SameSite=None` cookie is a third-party cookie
browsers increasingly block. So the session is delivered two ways at once: set as
a cookie *and* handed to the first-party SPA in the landing URL's fragment, which
the SPA captures and thereafter sends as `Authorization: Bearer`.
`session_from_request` reads the Bearer header first and the cookie only when
there is none, so the Bearer path carries the session with no cookie required.

**CSRF, live because of `SameSite=None`.** A double-submit token bound to the
session's `jti` by HMAC: a cookie an attacker tosses in without the secret still
fails, and a token minted for one session does not verify against another's
`jti`. `set_csrf_cookie` is deliberately not `HttpOnly` — the SPA reads it to
echo it in `X-Pulse-CSRF` — while `set_session_cookie` is, because a script that
can read the session token can steal the session. The check itself (only
cookie-authenticated, state-changing requests need it; Bearer requests are exempt
by construction) is consumed by E2's first mutating endpoint; E1-15 carries that
line forward so it cannot arrive unowned.
"""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from uuid import uuid4

import jwt
from fastapi.responses import RedirectResponse
from starlette.requests import Request
from starlette.responses import Response

from app.config import Settings, is_development
from app.services.landing import Door, LandingRole

__all__ = [
    "CSRF_COOKIE",
    "SESSION_ALGORITHM",
    "SESSION_COOKIE",
    "SESSION_LIFETIME_SECONDS",
    "SessionClaims",
    "clear_session_cookie",
    "fragment_redirect",
    "issue_csrf_token",
    "issue_session",
    "session_from_request",
    "set_csrf_cookie",
    "set_session_cookie",
    "verified_session",
    "verify_csrf_token",
]

# The two cookies a valid launch sets. Named here rather than at the call sites
# because a test reads them off the wire and the door writes them, and two copies
# of a cookie name is the drift `docs/MISTAKES.md` entry 13 is about.
SESSION_COOKIE = "pulse_session"
CSRF_COOKIE = "pulse_csrf"

# The one algorithm this module signs and verifies with, passed explicitly on
# both calls. Symmetric, because the tool both issues and checks this token — see
# the module docstring.
SESSION_ALGORITHM = "HS256"

# Sixty minutes (ADR 0089, plan decision 4).
SESSION_LIFETIME_SECONDS = 3600

# The redirect a valid launch answers with. 302 is what the LTI security
# framework and every platform expect; the same value `app.api.deps.FOUND`
# carries, restated here rather than imported so that `services/` does not reach
# up into `api/`.
FOUND = 302

# Where the SPA is mounted (`app.main.SPA_MOUNT`), restated for the same
# layering reason. `fragment_redirect` builds `/app/<role>#session=<token>` from
# it, and `frontend/src/router.tsx`'s basepath is the same string (ADR 0086).
SPA_MOUNT = "/app"


@dataclass(frozen=True)
class SessionClaims:
    """Who arrived, at which door, in what role — and nothing that identifies them.

    `sub` is the platform's opaque subject identifier, which the launch already
    carried and which names no person on its own. `iss` is the platform's issuer
    URL, or `None` for the web door where a session is not platform-issued. The
    fields a token must carry to be a session, and no more: a name, an email or
    an `lms_user_id` here would be a credential the browser holds copies of §8
    keeps in one place.
    """

    door: Door
    role: LandingRole
    sub: str
    iss: str | None
    jti: str
    iat: int
    exp: int


def issue_session(
    *,
    door: Door,
    role: LandingRole,
    sub: str,
    iss: str | None,
    secret: bytes,
    now: int | None = None,
) -> str:
    """One signed session token, expiring `SESSION_LIFETIME_SECONDS` after `now`.

    `now` is injectable epoch seconds so expiry is testable at the boundary
    without a clock patch; it defaults to the wall clock. `jti` is generated
    fresh every call — a `jti` derived from the claims would be the same value
    for every session a person ever holds, which is exactly what the CSRF binding
    below exists to prevent.

    `door` and `role` are stored by their enum *names* so the token is stable
    against a change in `Door`'s `auto()` numbering; `verified_session` reads them
    back the same way and answers `None` for a name neither enum knows.
    """
    issued_at = int(time.time()) if now is None else now
    payload = {
        "door": door.name,
        "role": role.name,
        "sub": sub,
        "iss": iss,
        "jti": uuid4().hex,
        "iat": issued_at,
        "exp": issued_at + SESSION_LIFETIME_SECONDS,
    }
    return jwt.encode(payload, secret, algorithm=SESSION_ALGORITHM)


def verified_session(token: str | None, secret: bytes) -> SessionClaims | None:
    """The claims of `token` once its signature and expiry hold, or `None`.

    One `None` for every way a token can fail to be one this tool issued — absent,
    unsigned, signed with another key, expired, or carrying a `door`/`role` this
    build does not know — like `app.api.deps.carried_across`: the caller's answer
    is the same refusal in every case, and a reason that told the two apart would
    tell an attacker whether a forgery was well formed.

    The algorithm is pinned to `SESSION_ALGORITHM`, so a token re-signed
    `alg: none` is refused rather than trusted.
    """
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[SESSION_ALGORITHM],
            options={"require": ["exp", "iat"]},
        )
    except jwt.PyJWTError:
        return None
    try:
        door = Door[payload["door"]]
        role = LandingRole[payload["role"]]
        return SessionClaims(
            door=door,
            role=role,
            sub=str(payload["sub"]),
            iss=None if payload.get("iss") is None else str(payload["iss"]),
            jti=str(payload["jti"]),
            iat=int(payload["iat"]),
            exp=int(payload["exp"]),
        )
    except (KeyError, ValueError, TypeError):
        return None


def issue_csrf_token(jti: str, secret: bytes) -> str:
    """A double-submit CSRF token bound to `jti` by HMAC.

    `nonce.mac`, where `mac = HMAC(secret, "<jti>:<nonce>")`: the fresh nonce
    makes each issued token distinct, and the HMAC over the jti is what binds the
    token to one session. A token minted for session A does not verify against
    session B's jti, and a token forged without the secret does not verify at all.
    """
    nonce = secrets.token_urlsafe(16)
    mac = hmac.new(secret, f"{jti}:{nonce}".encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{mac}"


def verify_csrf_token(token: str, jti: str, secret: bytes) -> bool:
    """Whether `token` is a CSRF token `issue_csrf_token` minted for `jti`.

    Constant-time on the MAC comparison, so a caller cannot learn a correct MAC
    one character at a time.
    """
    nonce, separator, mac = token.partition(".")
    if not separator or not mac:
        return False
    expected = hmac.new(secret, f"{jti}:{nonce}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, expected)


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    """Set the session cookie: `HttpOnly`, `SameSite=None`, `Secure` off dev, `path=/`.

    `HttpOnly` because this cookie holds the session token itself and a script
    that can read it can steal the session. `SameSite=None` because the tool is
    inside the LMS's cross-site iframe for the whole visit, so `Lax` would drop
    the cookie on every in-iframe request. `Secure` unless this is development,
    where the browser reaches the tool at `http://localhost` and a `Secure`
    cookie would not be sent at all — the same predicate `app.api.deps` asks of
    the retired login cookie, over the one value `app.config.is_development`.
    """
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_LIFETIME_SECONDS,
        httponly=True,
        secure=not is_development(settings),
        samesite="none",
        path="/",
    )


def set_csrf_cookie(response: Response, token: str, settings: Settings) -> None:
    """Set the CSRF cookie: not `HttpOnly`, otherwise the session cookie's attributes.

    Deliberately readable by script: the SPA echoes it in `X-Pulse-CSRF`, and a
    cookie it cannot read it cannot echo. Everything else matches the session
    cookie, because the CSRF defence only exists because that cookie is
    `SameSite=None`.
    """
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=SESSION_LIFETIME_SECONDS,
        httponly=False,
        secure=not is_development(settings),
        samesite="none",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Delete the session cookie."""
    response.delete_cookie(SESSION_COOKIE, path="/")


def session_from_request(request: Request, secret: bytes) -> SessionClaims | None:
    """The verified session carried by `request`: Bearer header first, cookie fallback.

    The cookieless path (SPEC §7.3) needs the Bearer branch: inside the LMS
    iframe the SPA sends the session it captured from the landing fragment as
    `Authorization: Bearer`, with no cookie riding along. A present Bearer header
    is answered on its own — a valid session in a cookie does not override a
    Bearer header, and an invalid Bearer is not quietly downgraded to whatever
    cookie the browser also sent. The cookie is read only when no Bearer header
    is there at all.

    Reading a session does not consume it: unlike a launch nonce, the same token
    verifies on every later request, which is what lets a session survive
    navigation between landing routes.
    """
    authorization = request.headers.get("authorization")
    if authorization and authorization[:7].lower() == "bearer ":
        return verified_session(authorization[7:].strip(), secret)
    return verified_session(request.cookies.get(SESSION_COOKIE), secret)


def fragment_redirect(role: LandingRole, token: str) -> RedirectResponse:
    """A 302 to `/app/<role>#session=<token>`, the session carried in the fragment.

    The fragment, never a query string: a fragment reaches neither the access log
    nor a `Referer` header, so the session token the SPA is about to capture is
    not written down anywhere on the way. `<role>` is the role name lowercased,
    which is the SPA route the landing view lives at (`frontend/src/router.tsx`).
    """
    return RedirectResponse(f"{SPA_MOUNT}/{role.name.lower()}#session={token}", status_code=FOUND)
