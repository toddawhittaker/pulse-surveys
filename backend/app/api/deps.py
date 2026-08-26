"""What a router needs from the request that is not the request (SPEC §13).

Today that is two things. The first is the short-lived signed cookie the **web**
door uses to carry a `state`, a `nonce` and a PKCE verifier from the redirect
that mints them to the redirect that checks them. The launch door carried one
too until E1-08 moved its handshake into a server-side store (ADR 0089); this
cookie is the web door's alone now, and ADR 0093 says why it stays. The second
is the small amount of scaffolding both doors share around their answers: the
two status codes, the refusal page, the calm page a cancelled web login gets,
and the tail that turns verified claims into a session and a landing redirect,
or into a refusal. §13 names this module for "auth context, role scoping,
n-threshold guards"; the first of those is what this is, and the other two
arrive with the screens that need them.

**Why a cookie at all.** The web login leaves the tool and comes back:
`/auth/oidc/login` sends a browser to the provider and `/auth/oidc/callback`
receives the code. `state` is the cross-site request forgery defence, `nonce` is
the replay defence, and the PKCE verifier is the whole of what binds the code to
this client. All three are only defences if the second request can be shown to
have come from the same browser as the first, so something has to hold them in
between.

**Why it is signed rather than stored — and why it stays a cookie (ADR 0093).**
A row in a table is what E1-08 built for the launch door, because a cookie
cannot survive the LMS's cross-site iframe: browsers block it there whatever its
attributes say. No iframe is involved in a web login. `/auth/oidc/callback` is a
top-level navigation the browser makes to this tool's own address, which a
`SameSite=Lax` cookie rides, so the reason the launch handshake had to move does
not reach this door — and a second, differently shaped handshake store would be
a schema and a purge beat bought for nothing. Signed rather than plain because
the whole point of `state` is that the caller did not choose it: an unsigned
cookie is a value the caller writes, and comparing a caller-supplied `state`
against a caller-supplied cookie proves nothing at all.

**The secret is per process and is generated at startup.** `app.state` holds
`secrets.token_bytes(32)` minted in `create_app`, so:

* restarting the API invalidates every login that is in flight, and the browser
  gets a refusal rather than a session;
* **more than one API process cannot serve one login**, because the second
  process cannot read the first one's cookie. Compose runs one `api` container
  and this is a single-process system, so this is true today and would be the
  first thing to break under a second replica.

Both are stated rather than hidden. A login dying on a restart is the safe
direction for a five-minute in-flight value — unlike the session itself, which is
signed with a *configured* secret precisely so a restart does not log a sitting
person out (ADR 0089). What is deliberately *not* done is to add a configured
secret for this one as well: an `.env.example` entry is a promise that a value is
worth setting, and the price of not making it is the replica limit above, named
in ADR 0093's consequences rather than discovered.

**`Secure` everywhere except development.** The cookie holds the `state`, the
`nonce` and the PKCE verifier — the last of which is the whole of what binds an
authorization code to this client, since it is a public one with no secret. A
browser sends a cookie without `Secure` over plain HTTP, so anyone on the path
reads all three. The flag cannot simply be on, either: a `Secure` cookie is not
sent to `http://localhost`, and `docker compose up` has to be signable-into on a
laptop, so an unconditional flag would refuse every development flow for a
`state` mismatch and look like a broken door. So it is on unless `ENVIRONMENT` is
exactly `development`, which is the same question `app/main.py` asks before it
serves `/docs`, asked through the same predicate, `app.config.is_development`.
The question is asked once, here, rather than at each door: two copies of it is
`docs/MISTAKES.md` entry 13, and one door left insecure is invisible.

**`SameSite=Lax`, not `None`.** The one request that has to carry this cookie is
the provider's redirect back to `/auth/oidc/callback`, which is a top-level GET
navigation — exactly what `Lax` is written to allow, cross-site or not. `None`
would widen the cookie to every cross-site subrequest and buy this door nothing:
the cross-site POST that needed `None`, and the iframe that made even `None`
insufficient, both belonged to the launch door, and neither exists here.
"""

import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import jwt
from fastapi.responses import HTMLResponse
from starlette.responses import Response

from app.config import Settings, is_development
from app.services.landing import Door, cancelled_page, landing_role_for, refusal_page
from app.services.session import (
    fragment_redirect,
    issue_csrf_token,
    issue_session,
    set_csrf_cookie,
    set_session_cookie,
    verified_session,
)

__all__ = [
    "FOUND",
    "LOGIN_COOKIE_LIFETIME_SECONDS",
    "LTI_LOGIN_COOKIE",
    "OIDC_LOGIN_COOKIE",
    "REFUSED",
    "cancelled",
    "carried_across",
    "carry_across",
    "clear_carried",
    "landing_with_session",
    "refused",
    "with_query",
]

# One cookie per door. Two names rather than one shared name because the two
# flows can be in progress at once — the same person opening a report from an
# LMS launch while a web login is half done — and one cookie would have the
# second overwrite the first, producing a refusal on a flow nobody did anything
# wrong in.
LTI_LOGIN_COOKIE = "pulse_lti_login"
OIDC_LOGIN_COOKIE = "pulse_oidc_login"

# How long a login may take. Five minutes is what both mocks give their own
# pending requests, and it is generous for a redirect a browser follows
# immediately. Not a setting: there is one right answer and a knob for it would
# only ever be turned up.
LOGIN_COOKIE_LIFETIME_SECONDS = 300

# The algorithm this module signs with, passed explicitly on the way in *and* on
# the way out. A verifier that read `alg` out of the cookie would accept `none`
# from anyone who could write the cookie, which is everyone.
COOKIE_ALGORITHM = "HS256"

# What a refused launch or sign-in answers. 400 rather than 401 or 403: nothing
# here is authenticated in the HTTP sense — there is no realm to challenge and no
# credential to re-present — the request itself is the thing that does not hold.
REFUSED = 400

# The redirect a login initiation answers with. 302 is what the LTI 1.3 security
# framework and every platform in the field expect; 303 would also be correct
# after a POST and is not what tools send.
FOUND = 302


def with_query(url: str, parameters: Mapping[str, str]) -> str:
    """`url` carrying `parameters`, keeping any query it already had.

    Here rather than in either router because both doors build exactly one
    redirect this way — the launch door's authorization request and the web
    door's — and two copies of "how a redirect is assembled" is the shape
    `docs/MISTAKES.md` entry 13 is about.

    A configured endpoint may legitimately carry a query of its own: a tenant
    identifier, a routing hint. An implementation that appended `?` would
    silently drop it. Built with `urlsplit`/`urlunsplit` rather than by string
    concatenation so that a fragment, if there is one, stays after the query
    where RFC 3986 puts it.
    """
    split = urlsplit(url)
    existing = parse_qsl(split.query, keep_blank_values=True)
    merged = urlencode([*existing, *parameters.items()])
    return urlunsplit((split.scheme, split.netloc, split.path, merged, split.fragment))


def carry_across(
    response: Response,
    name: str,
    secret: bytes,
    values: Mapping[str, str],
    settings: Settings,
) -> None:
    """Put `values` on `response` as a signed, short-lived cookie called `name`.

    `settings` is here for one attribute — `Secure`, which is set unless this is a
    development environment. See the module docstring for why it is conditional
    and why the condition is read here rather than at each door.
    """
    payload: dict[str, Any] = dict(values)
    payload["exp"] = int(time.time()) + LOGIN_COOKIE_LIFETIME_SECONDS
    response.set_cookie(
        name,
        jwt.encode(payload, secret, algorithm=COOKIE_ALGORITHM),
        max_age=LOGIN_COOKIE_LIFETIME_SECONDS,
        httponly=True,
        secure=not is_development(settings),
        samesite="lax",
        path="/",
    )


def carried_across(secret: bytes, sealed: str | None) -> dict[str, Any] | None:
    """What this tool put in the cookie, or `None` if it did not put it there.

    One `None` for every way this can fail — no cookie, a cookie this process
    did not sign, an expired one — because the caller's answer is the same
    refusal in every case, and a refusal that said which would tell an attacker
    whether their forgery was well formed.
    """
    if not sealed:
        return None
    try:
        return jwt.decode(sealed, secret, algorithms=[COOKIE_ALGORITHM])
    except jwt.PyJWTError:
        return None


def clear_carried(response: Response, name: str) -> None:
    """Delete the cookie, because the login it belonged to is over.

    Called on every way out of the web door's callback — the session it issues,
    the refusal, and the cancel branch — because a `state` is good once, and one
    left in the browser is one an attacker can replay into a second callback. The
    launch door had a second caller here until E1-08 moved its handshake into a
    server-side store; it now sets no login cookie to clear (ADR 0089).
    """
    response.delete_cookie(name, path="/")


def refused(reason: str) -> HTMLResponse:
    """A 4xx page carrying the reason and no landing view."""
    return HTMLResponse(refusal_page(reason), status_code=REFUSED)


def cancelled() -> HTMLResponse:
    """The calm page a cancelled or provider-refused web login gets (E1-09).

    A 200 rather than a 4xx, and a page of its own rather than `refused` above,
    because nothing went wrong: somebody declined to sign in, or the provider
    declined for them, and both are ordinary. The distinction is the whole of what
    E1-09's error branch is for — "you cancelled" and "this tool was handed a
    refusal it cannot account for" are different events, and the person in front
    of the screen is owed different words for them.
    """
    return HTMLResponse(cancelled_page())


def landing_with_session(
    claims: Mapping[str, Any],
    *,
    door: Door,
    settings: Settings,
    secret: bytes,
    no_role_reason: str,
) -> Response:
    """The last step of both second legs: issue a session and land, or refuse.

    Verified claims come in; a session `app.services.session` defines goes out,
    handed over as a fragment redirect to the role's landing route with the
    session and CSRF cookies set — or `no_role_reason` on a refusal page when this
    door has no view for any role the claims state. E1-08 put the launch door on
    this shape and E1-09 brought the web door onto it, which is what makes the two
    doors' sessions the same type with the same custody.

    `door` and `no_role_reason` are the whole of what differs between them. The
    two refusal sentences are deliberately not the same — each door tells the
    caller something true only of that door — so the sentence is an argument
    rather than a constant here.

    `landing_role_for(claims, door=door)` is called unchanged — neither ticket
    touches role resolution (E1-13's) — and a caller stating a role this door
    serves no view for is refused rather than landed on a default.

    **Clearing the login cookie is the caller's**, not this function's: the launch
    door has no login cookie left to clear (ADR 0089), and the web door clears its
    own on every way out of the callback rather than on this one.

    The CSRF token is bound to the session's own `jti`, which is read back off the
    issued token: `issue_session` mints the `jti` and returns the token, and
    `verified_session` is the one way to read the claims it put inside.
    """
    role = landing_role_for(claims, door=door)
    if role is None:
        return refused(no_role_reason)
    token = issue_session(
        door=door,
        role=role,
        sub=str(claims.get("sub") or ""),
        # Whoever issued the token this session was minted from: the LMS platform
        # at the launch door, the identity provider at the web door. The same
        # claim at both doors and never `None` — `SessionClaims` types `iss` as
        # `str | None`, but `issue_session` puts the value straight into a JWT
        # payload and PyJWT raises `TypeError` on a non-string `iss`, so `None`
        # is a value that module cannot actually issue. See ADR 0093's
        # consequences, which name the sentence in `app.services.session` this
        # falsifies and the ticket that owns the repair.
        iss=claims.get("iss"),
        secret=secret,
    )
    session = verified_session(token, secret)
    if session is None:
        # A token this function issued with `secret`, read back with the same
        # `secret`, verifies by construction; this guards the type rather than a
        # real state, so a genuine failure here is a bug loud enough to name.
        raise RuntimeError("A session this door just issued failed to verify against its own key.")
    response: Response = fragment_redirect(role, token)
    set_session_cookie(response, token, settings)
    set_csrf_cookie(response, issue_csrf_token(session.jti, secret), settings)
    return response
