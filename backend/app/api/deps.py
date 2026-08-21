"""What a router needs from the request that is not the request (SPEC §13).

Today that is one thing: the short-lived signed cookie both entry doors use to
carry a `state`, a `nonce` and — on the web door — a PKCE verifier from the
redirect that mints them to the redirect that checks them. §13 names this module
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
from starlette.responses import Response

__all__ = [
    "LOGIN_COOKIE_LIFETIME_SECONDS",
    "LTI_LOGIN_COOKIE",
    "OIDC_LOGIN_COOKIE",
    "carried_across",
    "carry_across",
    "clear_carried",
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


def carry_across(response: Response, name: str, secret: bytes, values: Mapping[str, str]) -> None:
    """Put `values` on `response` as a signed, short-lived cookie called `name`."""
    payload: dict[str, Any] = dict(values)
    payload["exp"] = int(time.time()) + LOGIN_COOKIE_LIFETIME_SECONDS
    response.set_cookie(
        name,
        jwt.encode(payload, secret, algorithm=COOKIE_ALGORITHM),
        max_age=LOGIN_COOKIE_LIFETIME_SECONDS,
        httponly=True,
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
