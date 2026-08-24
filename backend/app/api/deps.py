"""What a router needs from the request that is not the request (SPEC §13).

Today that is two things. The first is the short-lived signed cookie both entry
doors use to carry a `state`, a `nonce` and — on the web door — a PKCE verifier
from the redirect that mints them to the redirect that checks them. The second is
the small amount of scaffolding both doors share around their answers: the two
status codes, the refusal page, and the tail that turns verified claims into a
landing view or a refusal and clears the cookie either way. §13 names this module
for "auth context, role scoping, n-threshold guards"; the first of those is what
this is, and the other two arrive with the screens that need them.

**Why a cookie at all.** Both flows leave the tool and come back: `/lti/login`
sends a browser to the platform and `/lti/launch` receives what the platform
signed; `/auth/oidc/login` sends it to the provider and `/auth/oidc/callback`
receives the code. `state` is the cross-site request forgery defence and `nonce`
is the replay defence, and both are only defences if the second request can be
shown to have come from the same browser as the first. Something has to hold
them in between, and in a system with no session model yet the browser is the
only place there is.

**Why it is signed rather than stored.** A row in a table is where E1 puts this
(its breakdown owns platform-side state storage for cookieless iframes), and a
signed cookie is what E0 can have without inventing that schema. Signed rather
than plain because the whole point of `state` is that the caller did not choose
it: an unsigned cookie is a value the caller writes, and comparing a
caller-supplied `state` against a caller-supplied cookie proves nothing at all.

**The secret is per process and is generated at startup.** `app.state` holds
`secrets.token_bytes(32)` minted in `create_app`, so:

* restarting the API invalidates every login that is in flight, and the browser
  gets a refusal rather than a session;
* **more than one API process cannot serve one login**, because the second
  process cannot read the first one's cookie. Compose runs one `api` container
  and E0 is a single-process system, so this is true today and would be the
  first thing to break under a second replica.

Both are stated rather than hidden, and neither is worth fixing here: E1's
unified session model replaces this mechanism outright. What is deliberately
*not* done is to add a configured secret for it — an `.env.example` entry is a
promise that a value is worth setting, and this one has a two-ticket life.

**`Secure` everywhere except development.** The cookie holds the `state` and
`nonce` a launch is judged against, and on the web door the PKCE verifier as
well — which is the whole of what binds an authorization code to this client,
since it is a public one with no secret. A browser sends a cookie without
`Secure` over plain HTTP, so anyone on the path reads all three. The flag cannot
simply be on, either: a `Secure` cookie is not sent to `http://localhost`, and
E0-18 exists to make `docker compose up` launchable-into on a laptop, so an
unconditional flag would refuse every development flow for a `state` mismatch and
look like a broken door. So it is on unless `ENVIRONMENT` is exactly
`development`, which is the same comparison `app/main.py` makes before it serves
`/docs` and the same constant, `app.config.DEVELOPMENT_ENVIRONMENT`. The
comparison is made once, here, rather than at each door: two copies of it is
`docs/MISTAKES.md` entry 13, and one door left insecure is invisible.

**`SameSite=Lax`, not `None`.** An LTI launch is posted back to the tool from
the platform's authorization endpoint, which is a cross-*site* POST in a real
deployment and would need `SameSite=None; Secure` for the cookie to ride along —
and that, in an LMS iframe, is exactly the cookieless problem E1's boundary
section owns. On the development stack every service is `localhost` on a
different port, which is one site, so `Lax` carries. Widening it here would ship
the weaker cookie for the length of E0 and buy a deployment nobody has.
"""

import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import jwt
from fastapi.responses import HTMLResponse
from starlette.responses import Response

from app.config import DEVELOPMENT_ENVIRONMENT, Settings
from app.services.landing import Door, landing_page, landing_role_for, refusal_page

__all__ = [
    "FOUND",
    "LOGIN_COOKIE_LIFETIME_SECONDS",
    "LTI_LOGIN_COOKIE",
    "OIDC_LOGIN_COOKIE",
    "REFUSED",
    "carried_across",
    "carry_across",
    "clear_carried",
    "landing_or_refusal",
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
        secure=settings.environment != DEVELOPMENT_ENVIRONMENT,
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

    Called on the way out of both second legs, whether they admitted the caller
    or refused: a `state` is good once, and one left in the browser is one an
    attacker can replay into a second callback.
    """
    response.delete_cookie(name, path="/")


def refused(reason: str) -> HTMLResponse:
    """A 4xx page carrying the reason and no landing view."""
    return HTMLResponse(refusal_page(reason), status_code=REFUSED)


def landing_or_refusal(
    claims: Mapping[str, Any],
    *,
    door: Door,
    cookie: str,
    no_role_reason: str,
) -> Response:
    """The last step of both second legs: land the caller, or refuse, and clear.

    Verified claims come in; the view their roles name goes out, or `no_role_reason`
    on a refusal page when this door has no view for any role they state. The
    carried cookie is deleted either way, because a `state` is good once.

    `door`, `cookie` and `no_role_reason` are the whole of what differs between
    the launch door and the web door. The two refusal sentences are deliberately
    not the same — each door tells the caller something true only of that door —
    so the sentence is an argument rather than a constant here.
    """
    role = landing_role_for(claims, door=door)
    answer: Response = refused(no_role_reason) if role is None else HTMLResponse(landing_page(role))
    clear_carried(answer, cookie)
    return answer
