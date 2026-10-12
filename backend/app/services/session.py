"""The session both entry doors issue and every later request reads — ticket E1-08.

The launch door (`app.api.lti`) issues a session here once a launch verifies; the
web door (E1-09) issues the same session type; E1-12 gave a session its stored
identity, which is `person_id` and `user_id` below. It lives in `services/` rather
than in `lti/` because both doors share it, and it is deliberately small: a signed
statement of who arrived, at which door, in what role, and which rows this system
stores for them — no name, no email, no `lms_user_id`, only the opaque `sub` the
launch already carried and two primary keys that name nothing on their own
(SPEC §8, §10).

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

**Ending a session early (ADR 0202).** A token verifies until its `exp`,
so a role switch and a logout end a session by recording its `jti` in
`revoked_session` until that `exp` (`revoke_session`). Every role gate asks
`is_revoked` after the token verifies, and answers a revoked session with the
same refusal an expired one gets. The table purges itself as it is written.

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
from datetime import UTC, datetime
from uuid import UUID, uuid4

import jwt
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import Response

from app.config import Settings, is_development
from app.models.session import RevokedSession
from app.services.authz import Door, LandingRole, resolve_landings

__all__ = [
    "CSRF_COOKIE",
    "SESSION_ALGORITHM",
    "SESSION_COOKIE",
    "SESSION_LIFETIME_SECONDS",
    "SessionAlreadyEndedError",
    "SessionClaims",
    "bearer_token",
    "claim_key",
    "clear_csrf_cookie",
    "clear_session_cookie",
    "fragment_redirect",
    "is_revoked",
    "issue_csrf_token",
    "issue_session",
    "purge_revoked_sessions",
    "revoke_session",
    "session_from_request",
    "set_csrf_cookie",
    "set_session_cookie",
    "switch_session",
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

    **`person_id` and `user_id` are E1-12's, and they are keys rather than
    identity.** `person_id` is the `person` row both doors resolve to — the stored
    identity, by its primary key — and `user_id` is the `user` row a launch's
    subject reaches. Neither names anybody: a name lives on `person` and
    `user_identity`, which `pulse_app` reaches through no path this session opens,
    and what a holder of this token gains is the ability to say *which* row they
    are, which they already proved at the door. E1-13 is what reads assignments
    through `person_id` and enrollment through `user_id`, in
    `app.services.authz.resolve_landing`.

    **Both are `None`-able, and the two absences mean different things.**
    `person_id` is absent for a launch by somebody nobody has put in the people
    graph — a student, per ADR 0028 — which is an ordinary state the session
    carries rather than an error. `user_id` is absent at the web door, which
    resolves a person and no LMS subject at all.
    """

    door: Door
    role: LandingRole
    sub: str
    iss: str | None
    jti: str
    iat: int
    exp: int
    person_id: str | None = None
    user_id: str | None = None


def issue_session(
    *,
    door: Door,
    role: LandingRole,
    sub: str,
    iss: str | None,
    secret: bytes,
    person_id: str | None = None,
    user_id: str | None = None,
    now: int | None = None,
    expires_at: int | None = None,
) -> str:
    """One signed session token, expiring `SESSION_LIFETIME_SECONDS` after `now`.

    **`expires_at`, when given, is the token's `exp` instead** (ADR 0202);
    `iat` is still `now`. The role switch passes the old token's
    `exp`, so a switch is never a refresh: a session lives no longer for having
    changed role, however many times it does.

    `now` is injectable epoch seconds so expiry is testable at the boundary
    without a clock patch; it defaults to the wall clock. `jti` is generated
    fresh every call — a `jti` derived from the claims would be the same value
    for every session a person ever holds, which is exactly what the CSRF binding
    below exists to prevent.

    `door` and `role` are stored by their enum *names* so the token is stable
    against a change in `Door`'s `auto()` numbering; `verified_session` reads them
    back the same way and answers `None` for a name neither enum knows.

    **`person_id` and `user_id` default to `None` rather than being required**,
    and that is about the callers rather than about convenience: the resolution
    that fills them belongs to `app.api.deps`, which is the one place both doors
    reach this function from, and every other caller — the unit suite, a future
    tool that mints a session for something with no stored identity — states what
    it has and nothing else. Both claims are always written, `null` included, so
    the claim set of a session is the same set whichever door issued it and
    "resolved to nobody" is visible rather than inferred from an absence.
    """
    issued_at = int(time.time()) if now is None else now
    payload = {
        "door": door.name,
        "role": role.name,
        "sub": sub,
        "iss": iss,
        "person_id": person_id,
        "user_id": user_id,
        "jti": uuid4().hex,
        "iat": issued_at,
        "exp": issued_at + SESSION_LIFETIME_SECONDS if expires_at is None else expires_at,
    }
    return jwt.encode(payload, secret, algorithm=SESSION_ALGORITHM)


def verified_session(token: str | None, secret: bytes) -> SessionClaims | None:
    """The claims of `token` once its signature and expiry hold, or `None`.

    One `None` for every way a token can fail to be one this tool issued — absent,
    unsigned, signed with another key, expired, or carrying a `door`/`role` this
    build does not know — like `app.api.auth.carried_across`: the caller's answer
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
            # `.get` rather than `[...]`, unlike every claim above: a session
            # minted before E1-12 carries neither, and a browser holding one for
            # the rest of its hour should read as "no stored identity" rather than
            # as a token this tool did not issue.
            person_id=None if payload.get("person_id") is None else str(payload["person_id"]),
            user_id=None if payload.get("user_id") is None else str(payload["user_id"]),
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
    cookie would not be sent at all — the same predicate `app.api.auth` asks of
    the web door's login cookie, over the one value `app.config.is_development`.
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


def clear_session_cookie(response: Response, settings: Settings) -> None:
    """Delete the session cookie, with the attributes `set_session_cookie` set it with.

    The same `SameSite=None` and the same `Secure` rule, not Starlette's
    defaults: a deletion is itself a `Set-Cookie`, and a browser can refuse a
    `SameSite=Lax` one arriving on a cross-site response, which is every
    response inside the LMS's iframe. Logout (ADR 0202) is the caller.
    """
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=not is_development(settings),
        samesite="none",
    )


def clear_csrf_cookie(response: Response, settings: Settings) -> None:
    """Delete the CSRF cookie, with the attributes `set_csrf_cookie` set it with.

    Logout clears it beside the session cookie: a token bound to an ended
    session verifies against nothing, and a browser holding one has no use for it.
    """
    response.delete_cookie(
        CSRF_COOKIE,
        path="/",
        httponly=False,
        secure=not is_development(settings),
        samesite="none",
    )


def bearer_token(request: Request) -> str | None:
    """The token in `request`'s `Authorization: Bearer` header, or `None` for no such header.

    Split out of `session_from_request` below, whose behaviour is unchanged and
    which is now expressed through it. Two callers need the *same* answer to "did
    this session arrive as a Bearer token", and they need it for different
    reasons: this module reads the session, and `app.api.deps` decides whether
    ADR 0089's double-submit check applies — a Bearer header is not something a
    cross-site form or an image tag can make a browser send, so a request carrying
    one is not a request a browser can be tricked into making. Two readings of
    that question, in two modules, is `docs/MISTAKES.md` entry 13's shape: the day
    one of them starts accepting a different spelling, the exemption widens and
    nothing goes red.

    A `None` answer means "no Bearer header at all", which is not the same as a
    Bearer header carrying nothing: an `Authorization: Bearer` with an empty value
    answers the empty string, so a caller asking "did this arrive by cookie" gets
    `False` for it and the request is judged on the credential it actually
    presented.
    """
    authorization = request.headers.get("authorization")
    if authorization and authorization[:7].lower() == "bearer ":
        return authorization[7:].strip()
    return None


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

    **It does not ask whether the session was revoked** (ADR 0202). That
    needs the database, and this stays a pure read over the request and the
    secret. Every role gate in `app.api.deps` reads through it and then asks
    `is_revoked`, which is the one place a route reads a session (the sweep in
    `tests/unit/test_only_the_dependency_module_reads_a_session_from_a_request.py`).
    Logout is the one caller that wants a revoked session read as well, so that a
    second logout with the same token answers as the first did.
    """
    presented = bearer_token(request)
    if presented is not None:
        return verified_session(presented, secret)
    return verified_session(request.cookies.get(SESSION_COOKIE), secret)


def fragment_redirect(role: LandingRole, token: str) -> RedirectResponse:
    """A 302 to `/app/<role>#session=<token>`, the session carried in the fragment.

    The fragment, never a query string: a fragment reaches neither the access log
    nor a `Referer` header, so the session token the SPA is about to capture is
    not written down anywhere on the way. `<role>` is the role name lowercased,
    which is the SPA route the landing view lives at (`frontend/src/router.tsx`).
    """
    return RedirectResponse(f"{SPA_MOUNT}/{role.name.lower()}#session={token}", status_code=FOUND)


# ---------------------------------------------------------------------------
# Ending a session before its token expires (ADR 0202).
# ---------------------------------------------------------------------------


def is_revoked(db: Session, jti: str) -> bool:
    """Whether the session with this `jti` was ended before its token expired.

    Asked by every role gate in `app.api.deps` after the token verifies. A row
    that outlived its token (the purge has not run since) still answers `True`,
    which is harmless: the token it names no longer verifies anyway.
    """
    return bool(db.scalar(select(exists().where(RevokedSession.jti == jti))))


def purge_revoked_sessions(db: Session, now: datetime) -> int:
    """Delete every revocation whose token expired before `now`, and say how many.

    `now` is passed in rather than read, so a test needs no clock patch. A row
    expiring exactly at `now` is kept: the signature check refuses a token from
    its `exp` on, and a row kept one instant longer than it is needed costs
    nothing. Does not commit; the caller owns the transaction.
    """
    deleted = db.execute(delete(RevokedSession).where(RevokedSession.expires_at < now))
    return int(getattr(deleted, "rowcount", 0) or 0)


def revoke_session(db: Session, claims: SessionClaims) -> bool:
    """End this session: record its `jti` until its token's own expiry, and purge the rest.

    **An insert that does nothing on conflict**, so revoking a session twice is
    not an error and leaves one row; a second logout with the same token
    answers exactly as the first did.

    **Answers whether this call recorded the revocation** (`RETURNING jti`).
    `False` means the session was already revoked, by a call whose transaction
    committed first: a concurrent insert of the same `jti` waits on the other
    transaction's row and then does nothing. Logout ignores the answer; the
    switch refuses on `False`, so one token switches once (ruling G2).

    **The table purges itself here**, in the same transaction, so no scheduled
    job is needed. The purge reads the real clock and never
    `app.services.clock.now`, for the reason ADR 0109 gives about session
    expiry: the token's `exp` is judged against the real clock by the signature
    check, and a purge on a moved development clock would delete revocations
    of tokens that still verify, bringing ended sessions back.

    Does not commit; the caller owns the transaction.
    """
    purge_revoked_sessions(db, datetime.now(UTC))
    recorded = db.execute(
        insert(RevokedSession)
        .values(jti=claims.jti, expires_at=datetime.fromtimestamp(claims.exp, UTC))
        .on_conflict_do_nothing(index_elements=[RevokedSession.jti])
        .returning(RevokedSession.jti)
    ).first()
    return recorded is not None


def claim_key(value: str | None) -> UUID | None:
    """A row key carried in a session claim, or `None` for an absent or malformed one.

    `app.api.deps.person_of` and `user_of` read their claims through this, as
    does `switch_session`: a value that is not a UUID is a token this deployment
    did not issue in that shape, and it resolves to nobody rather than to a 500.
    """
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


class SessionAlreadyEndedError(Exception):
    """The session a switch was asked from was revoked by another request first (ruling G2).

    Two switches with one token race to revoke it; the one whose insert comes
    back empty lost. Its caller answers as for a revoked token at any gate.
    """


def switch_session(
    db: Session,
    claims: SessionClaims,
    *,
    to: LandingRole,
    secret: bytes,
    settings: Settings,
) -> str | None:
    """A new session in role `to`, revoking this one; or `None`, issuing and revoking nothing.

    SPEC §2 gives a person with several hats a switcher, and a session holds one
    role (ADR 0202): the switch never adds a role to a session, it issues a new
    session in the asked role and ends the old one. Care is therefore never
    combined with a reporting role, and neither is Admin.

    **The person's views are re-read now**, at the session's own door, through
    `app.services.authz.resolve_landings`, never from a list a client or an
    earlier answer supplied. A role the person does not hold, one held only at
    the other door, and one whose assignment was deleted since the list was
    shown all answer `None`.

    **A switch is not a refresh** (ruling G1). The session's own role is refused
    like any role not held, and the new token keeps the old token's `exp`, so
    no sequence of switches keeps a session alive past the hour it was issued
    for.

    **Everything but the role and `iat` is carried over**: the door, the
    subject, the issuer, both row keys and the expiry.

    **The old token is spent once** (ruling G2). It is revoked before the new
    one is issued, in the caller's transaction; if the revocation insert comes
    back empty, another request revoked it first, and this raises
    `SessionAlreadyEndedError` having issued nothing. The caller commits.
    """
    if to is claims.role:
        return None
    held = resolve_landings(
        db,
        door=claims.door,
        person_id=claim_key(claims.person_id),
        user_id=claim_key(claims.user_id),
        settings=settings,
    )
    if to not in held:
        return None
    if not revoke_session(db, claims):
        raise SessionAlreadyEndedError
    return issue_session(
        door=claims.door,
        role=to,
        sub=claims.sub,
        iss=claims.iss,
        secret=secret,
        person_id=claims.person_id,
        user_id=claims.user_id,
        expires_at=claims.exp,
    )
