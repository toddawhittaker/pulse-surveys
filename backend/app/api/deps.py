"""What a router needs from the request that is not the request (SPEC §13).

Today that is two things. The first is the short-lived signed cookie the **web**
door uses to carry a `state`, a `nonce` and a PKCE verifier from the redirect
that mints them to the redirect that checks them. The launch door carried one
too until E1-08 moved its handshake into a server-side store (ADR 0089); this
cookie is the web door's alone now, and ADR 0093 says why it stays. The second
is the small amount of scaffolding both doors share around their answers: the
two status codes, the four pages a door can answer with that are not a landing,
and the tail that turns verified claims into a session and a landing redirect,
or into one of those pages. §13 names this module for "auth context, role
scoping, n-threshold guards"; the first of those is what this is, and the other
two arrive with the screens that need them.

**The pages themselves live here from E1-13 on.** They were in
`app/services/landing.py`, beside the claims-derived landing seam that ticket
deleted — and this module's paragraph above had described them all along, since
a door's answer is exactly the thing a router needs and is not a domain rule. A
service module left holding four HTML templates and no decision would have been
a module kept alive by its markup.

**Four answers, four testids, because they are four different events**: this
tool refuses your token (`pulse-entry-refused`, a 4xx); you cancelled, or your
provider declined for you (`web-login-cancelled`); Pulse holds no record of you
(`no-account`, E1-12); and Pulse holds your record and nothing in it gives you a
view at this door (`no-access`, E1-13). The last three are 200s, because nothing
went wrong in any of them, and the person in front of the screen is owed the
right words and the right person to ask.

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
from html import escape
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import jwt
from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.config import Settings, is_development
from app.copy.submit import COPY
from app.services.authz import Door, LandingRole, resolve_landing
from app.services.identity import (
    ResolvedIdentity,
    identity_behind_a_launch,
    person_behind_a_web_login,
)
from app.services.session import (
    SessionClaims,
    fragment_redirect,
    issue_csrf_token,
    issue_session,
    session_from_request,
    set_csrf_cookie,
    set_session_cookie,
    verified_session,
)

__all__ = [
    "BEARER_SCHEME",
    "FOUND",
    "LOGIN_COOKIE_LIFETIME_SECONDS",
    "LTI_LOGIN_COOKIE",
    "NOT_A_STUDENT_KEY",
    "NOT_A_STUDENT_STATUS",
    "OIDC_LOGIN_COOKIE",
    "PAGE",
    "REFUSED",
    "cancelled",
    "cancelled_page",
    "carried_across",
    "carry_across",
    "clear_carried",
    "landing_with_session",
    "no_access",
    "no_access_page",
    "no_account",
    "no_account_page",
    "refusal_page",
    "refused",
    "require_student",
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


# ---------------------------------------------------------------------------
# The four pages a door can answer with that are not a landing.
# ---------------------------------------------------------------------------

# What a refused entry says. Deliberately one sentence and a reason, with no
# retry link: there is nowhere for a browser to go from here that is not the
# platform or the provider it came from, and a link built out of a request that
# just failed validation is the open redirect both doors exist to refuse.
REFUSAL_TESTID = "pulse-entry-refused"
REFUSAL_HEADING = "This did not open"

# The sentence each guard's refusal page carries, keyed by the guard's own class
# name — the machine vocabulary ADR 0103 put in `data-reason`, and the only
# thing `refusal_page` takes.
#
# **The page derives its copy rather than being handed it, and that is the
# security property** (E1 boundary fix, M7). This page is answered to anybody
# who can post a form at a door: no session, no authentication, nothing but a
# request. A page with a text parameter is a page half-written by whoever
# provoked it, and the string nearest to hand at every call site is the
# exception that refused — whose `str()` carries whatever a library was told by
# the caller. So the callers pass a name from a closed vocabulary, this mapping
# turns it into a constant, and a name nothing maps gets `DEFAULT_REFUSAL_COPY`.
# There is nowhere for a caller's words to go.
#
# **Keyed by class name and not by class**, so `app.api.deps` imports neither
# door's exceptions: the launch guards live in `app.lti.launch` and the web
# door's in `app.api.auth`, and this module is below both. A guard renamed on
# one side and not here falls to the default — calm, and correct, and visible
# as the wrong copy rather than as a 500 from inside a refusal.
#
# `NonceReplayedError`'s two sentences are `app.lti.replay_guard`'s own words,
# copied whole: `tests/e2e/exit-refused-launches.spec.ts` keeps one prose
# assertion as its copy canary and matches that string.
REFUSAL_COPY: Mapping[str, str] = {
    "SignatureRefused": (
        "This launch could not be verified. Its signature, the algorithm it names, or the key it "
        "was signed with did not hold."
    ),
    "AudienceRefused": "This launch was issued for a different tool than this one.",
    "IssuerRefused": "No registration here exists for the platform that began this launch.",
    "NonceRefused": "This launch carries no `nonce`, or one this tool did not send.",
    "NonceReplayedError": (
        "This launch has already been delivered once. A launch nonce is single-use, and "
        "presenting the same signed launch a second time is refused."
    ),
    "DeploymentRefused": "This launch names a deployment this tool was never installed into.",
    "MessageTypeRefused": "This launch is a message type this tool does not serve.",
    "VersionRefused": "This launch states an LTI version this tool does not speak.",
    "StateRefused": "This launch returns a `state` this tool did not issue, or none at all.",
    "ClockSkewRefused": "This launch was minted too far in the future, or expired too long ago.",
    "AnonymousLaunchRefused": (
        "This launch names nobody. Pulse Surveys shows each person their own work, so a launch "
        "carrying no subject is one it cannot open."
    ),
    "SessionRefusedError": (
        "That sign-in could not be verified, and nobody has been signed in. Start again from "
        "where you opened Pulse Surveys."
    ),
}

# What a guard this mapping does not know is answered with. A constant, and
# every word of it true of any refusal: it reports nothing about what was handed
# in, which is what keeps a guard name nobody mapped from becoming a caller's
# string in the body by way of an f-string that meant to be helpful.
DEFAULT_REFUSAL_COPY = (
    "This tool could not account for what it was handed, and nobody has been signed in. Start "
    "again from where you opened Pulse Surveys."
)

# What a cancelled web login says (E1-09). Calm and non-blaming, per
# `docs/DESIGN_BRIEF.md`'s tone: the person declined to sign in, or the provider
# declined for them, and neither is a fault to report back. It says what is true —
# nothing was changed, nobody is signed in — and stops there. No retry link, for
# the reason above, and not a syllable of what the provider sent:
# `error_description` and `error_uri` are text an attacker chooses, and a page
# that repeated them would be a page whose words they wrote, under this tool's own
# name and styling.
CANCELLED_TESTID = "web-login-cancelled"
CANCELLED_HEADING = "Sign-in did not finish"
CANCELLED_MESSAGE = "Nothing was changed and nobody is signed in. You can start again when ready."

# What a web login by somebody this system has no record of says (E1-12). A third
# answer beside the two above, because it is a third event: the sign-in worked and
# the provider vouched for the person, and Pulse simply holds no record of them.
# "You cancelled", "this tool was handed something it cannot account for" and "we
# do not know you" are three different things to be told, and the person in front
# of the screen is owed the right one — telling somebody their sign-in failed when
# it did not sends them to reset a password that is fine.
#
# It says what to do next, which the other two cannot: there is somebody to ask.
# It names nobody and repeats nothing the provider sent — the subject and the
# address in that token are the provider's text, and this page has nowhere to put
# them.
NO_ACCOUNT_TESTID = "no-account"
NO_ACCOUNT_HEADING = "Pulse Surveys has no account for you yet"
NO_ACCOUNT_MESSAGE = (
    "You signed in correctly and nothing went wrong. Pulse Surveys keeps its own record of who "
    "works here, and there is no record for you yet, so there is nothing to show. Ask whoever "
    "administers Pulse Surveys at your institution to add you."
)

# What somebody Pulse *does* hold a record of is told when nothing in that record
# gives them a view at the door they came in by (E1-13). A fourth answer and a
# fourth event: they are known here, and no live assignment this door admits and
# no live enrollment entitles them to a screen.
#
# The message carries three things and no more. What is true; the LMS-launch hint,
# because SPEC §2.1 gives the instructor the launch and no web login, so "I logged
# in and there is nothing here" is the ordinary way somebody who teaches meets
# this page; and who to ask, which is a different administrator from the one
# `no-account` sends people to.
NO_ACCESS_TESTID = "no-access"
NO_ACCESS_HEADING = "There is nothing in Pulse Surveys for you yet"
NO_ACCESS_MESSAGE = (
    "Nothing went wrong and nobody is at fault. Pulse Surveys keeps its own record of who works "
    "here and who is enrolled, and nothing in yours gives you a view at this door yet. If you "
    "teach, open Pulse Surveys from inside one of your courses in the LMS rather than from here. "
    "Otherwise, ask whoever administers Pulse Surveys at your institution."
)

# The page, as one f-string rather than a template engine: there is one layout,
# it has three slots, and nothing in the locked closure renders templates. The
# style block is inline for the same reason, and it stays inline now that the SPA
# exists: these pages are answered at a door, before any session, and a page that
# pulled a stylesheet out of the SPA's bundle would depend on an asset the person
# being refused may never have loaded.
#
# The markup follows `docs/DESIGN_BRIEF.md` and `design/tokens.css`: chalk ground,
# spruce ink, Literata for the heading and Schibsted Grotesk for the body, the
# flat mist pulse line the brief gives to empty states, and nothing else. Flat is
# what the line means here — nothing has arrived yet. The webfonts are **not**
# linked: an LMS iframe fetching Google Fonts is a third-party request from inside
# somebody's LMS, the stacks fall back to a serif and a grotesque that are already
# there, and the SPA is where the real loading strategy belongs.
PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{heading} · Pulse Surveys</title>
<style>
  :root {{
    --chalk: #F6F8F4;
    --spruce: #1E3932;
    --spruce-60: #5B7269;
    --mist: #93A5A0;
    --marigold-deep: #8F6A10;
    --font-display: 'Literata', Georgia, serif;
    --font-body: 'Schibsted Grotesk', 'Helvetica Neue', sans-serif;
    --space-4: 16px;
    --space-5: 24px;
    --space-7: 48px;
  }}
  :focus-visible {{ outline: 2px solid var(--marigold-deep); outline-offset: 2px; }}
  body {{
    margin: 0;
    background: var(--chalk);
    color: var(--spruce);
    font-family: var(--font-body);
    font-size: 16px;
    line-height: 1.5;
  }}
  main {{ max-width: 720px; margin: 0 auto; padding: var(--space-7) var(--space-5); }}
  h1 {{ font-family: var(--font-display); font-size: 25px; font-weight: 600; margin: 0; }}
  .pulse {{ display: block; margin: var(--space-4) 0; }}
  p {{ color: var(--spruce-60); margin: 0; }}
</style>
</head>
<body>
<main data-testid="{testid}"{reason_attr}>
<h1>{heading}</h1>
<svg class="pulse" width="120" height="8" viewBox="0 0 120 8" aria-hidden="true"
     fill="none" stroke="var(--mist)" stroke-width="2.5" stroke-linecap="round">
  <path d="M2 4 H118"/>
</svg>
<p>{empty_state}</p>
</main>
</body>
</html>
"""


def _reason_attribute(guard: str) -> str:
    """The ` data-reason="<guard>"` attribute a refusal container carries.

    Rendered beside `data-testid` so a browser-side refusal spec can name which
    guard fired without reading the prose (E1 cleanup Batch B item 2; ADR 0103).
    Every refusal names a guard now, so there is no attribute-less case: the door
    suites assert the page carries *exactly one* marker, and both an omitted
    attribute and an empty one defeat that.
    """
    return f' data-reason="{escape(guard, quote=True)}"'


def refusal_page(guard: str) -> str:
    """The page a refused launch or a refused web login gets, in the same layout.

    **It carries no landing testid**, and that is a property both door suites
    assert rather than a detail: a refusal that served a landing page has
    admitted the caller and merely said so in the status line. The testid slot is
    filled with a name of its own so the markup stays one template.

    **`guard` is the only thing it takes, and the body copy is derived from it
    rather than handed in** (E1 boundary fix, M7). It is the refusing guard's own
    class name, from the closed vocabulary `REFUSAL_COPY` above is keyed by; the
    sentence a person reads comes out of that mapping, or out of
    `DEFAULT_REFUSAL_COPY` for a name nothing maps. This page is answered to
    anybody who can post a form at a door, so a parameter it could print is a
    parameter an attacker fills — and the value nearest to hand at a call site
    is the exception that refused, which carries whatever a library was told.
    There is now nowhere in this signature to put such a string.

    The name still reaches the `data-reason` attribute (ADR 0103), escaped:
    everything interpolated is a constant or a Python class name today, and the
    escaping is written for the day it is neither.
    """
    return PAGE.format(
        testid=escape(REFUSAL_TESTID, quote=True),
        reason_attr=_reason_attribute(guard),
        heading=escape(REFUSAL_HEADING),
        empty_state=escape(REFUSAL_COPY.get(guard, DEFAULT_REFUSAL_COPY)),
    )


def cancelled_page() -> str:
    """The page a cancelled web login gets, in the same layout (E1-09).

    **It takes no argument at all**, and that is the security property rather than
    a convenience: the only thing this door knows about a cancel is what the
    provider's redirect said, every parameter in that redirect is attacker-chosen
    text, and a function with nowhere to put such text cannot be talked into
    rendering it. What the page says is three constants from this module.

    It carries no landing testid, like `refusal_page`, so a cancel serves nobody's
    view; and its own testid is not the refusal's, because a suite — and a person —
    has to be able to tell "you cancelled" from "this tool was handed something it
    could not account for".
    """
    return PAGE.format(
        testid=escape(CANCELLED_TESTID, quote=True),
        reason_attr="",
        heading=escape(CANCELLED_HEADING),
        empty_state=escape(CANCELLED_MESSAGE),
    )


def no_account_page() -> str:
    """The page a verified web login with no stored identity gets (E1-12).

    **Takes no argument, for `cancelled_page`'s reason and one more.** Everything
    this door knows about the person is in a token somebody else wrote, and the
    two values that identify them — the issuer and the subject — are exactly the
    ones a page must not repeat: the first is an address and the second is a
    stable per-person key at the provider, which SPEC §8 and §10 keep off screens
    and out of logs alike. A function with nowhere to put them cannot be talked
    into rendering them.

    It carries no landing testid, so a person with no record here reaches nobody's
    view; and its own testid is none of the other three, because this is a
    distinct event and a suite — and a person — has to be able to tell them apart.

    Rendered in the same layout and answered with the same status as the cancelled
    page: this is not a failure, and a 4xx would be the tool telling somebody who
    signed in correctly that they did something wrong.
    """
    return PAGE.format(
        testid=escape(NO_ACCOUNT_TESTID, quote=True),
        reason_attr="",
        heading=escape(NO_ACCOUNT_HEADING),
        empty_state=escape(NO_ACCOUNT_MESSAGE),
    )


def no_access_page() -> str:
    """The page a resolved person with nothing to land on gets (E1-13).

    **Takes no argument**, which is `cancelled_page`'s and `no_account_page`'s
    security property and is the whole of what this page improves on what it
    replaces: both doors used to answer this event with a refusal built from a
    sentence the router handed in, and a parameter is somewhere a role name, a
    stated claim or a subject can arrive. A page assembled from constants cannot
    repeat anything a caller chose, and the door suite asserts exactly that over
    the values the doors held while rendering it.

    It carries no landing testid, so somebody entitled to no view reaches nobody
    else's; and its own testid is none of the other three, for the reason above.
    """
    return PAGE.format(
        testid=escape(NO_ACCESS_TESTID, quote=True),
        reason_attr="",
        heading=escape(NO_ACCESS_HEADING),
        empty_state=escape(NO_ACCESS_MESSAGE),
    )


def refused(guard: str) -> HTMLResponse:
    """A 4xx page naming the guard that refused, and no landing view.

    `guard` is the refusing guard's class name. It reaches the page as the
    `data-reason` marker (ADR 0103) and, through `REFUSAL_COPY`, chooses the
    sentence the page carries — which is the whole of what a caller can affect
    here (E1 boundary fix, M7).
    """
    return HTMLResponse(refusal_page(guard), status_code=REFUSED)


def no_access() -> HTMLResponse:
    """The calm page a resolved person with nothing to land on gets (E1-13).

    A 200 and a page of its own, for `cancelled`'s reason applied to a fourth
    event: Pulse holds this person's record and nothing in it — no live
    assignment this door admits, no live enrollment — entitles them to a view.
    That is a real state rather than a fault: a member of staff whose assignment
    has not been entered yet, a student between terms, or somebody whose one role
    belongs to the other door.

    **It replaces both doors' "no role this tool has a view for" refusals.** Those
    were 4xx pages built from a sentence each router passed in, which is what
    `landing_with_session`'s `no_role_reason` parameter was; a person who
    authenticated correctly is owed plain words rather than a refusal, and a page
    that takes no argument cannot repeat anything a caller chose.

    **Answered at both doors, and after `no_account` at the web one.** "Pulse has
    no record of you" and "nothing in your record gives you a view" are different
    things to be told, and they send the person to two different administrators
    for help; E1-12's check runs first and is unchanged.
    """
    return HTMLResponse(no_access_page())


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


def no_account() -> HTMLResponse:
    """The calm page a verified web login with no stored identity gets (E1-12).

    A 200 and a page of its own, for `cancelled`'s reason applied to a different
    event: nothing went wrong. The identity provider vouched for somebody and
    Pulse has no record of them, which SPEC §2 makes an ordinary state — every
    role in this system comes from Pulse's own records, and a provider asserts
    authentication and not membership. A 4xx here would tell somebody who signed
    in correctly that their sign-in failed, and send them to fix a password that
    is fine.

    Answered only at the web door. A launch that resolves to no `person` is not
    this: the launch door has a view for a student, ADR 0028 gives a student a
    `user` row and no person, and the session carries that absence.
    """
    return HTMLResponse(no_account_page())


async def landing_with_session(
    claims: Mapping[str, Any],
    *,
    door: Door,
    db: Session,
    settings: Settings,
    secret: bytes,
) -> Response:
    """The last step of both second legs: resolve who this is, issue a session, land.

    Verified claims come in; a session `app.services.session` defines goes out,
    handed over as a fragment redirect to the landing route with the session and
    CSRF cookies set — or one of the two calm pages when there is no view to hand
    over. E1-08 put the launch door on this shape and E1-09 brought the web door
    onto it, which is what makes the two doors' sessions the same type with the
    same custody.

    **`door` is now the whole of what differs between them.** E1-13 removed the
    other difference, `no_role_reason`: each door used to refuse a person with no
    view with a 4xx and a sentence of its own, and both now answer the one calm
    page `no_access` renders out of constants.

    **What the claims are read for here is `sub` and `iss`, and nothing else.**
    E1-13 ends the roles claim's authority over the landing — the view comes from
    `app.services.authz.resolve_landing`, out of the person's own assignments and
    enrollment (ADR 0098), because the person who administers an LMS writes what
    its launches state. §7.3's provisioning still reads that claim lawfully,
    upstream of here, to tell a staff launch from a student one.

    **E1-12 resolves the stored identity here, which is why both doors get it
    from one edit.** A launch's `sub` reaches a `user` row and, through ADR 0024's
    link, a `person`; a web login's `(issuer, sub)` reaches a `person` through the
    linkage table. Both go through `app.services.identity`, which calls ADR 0094's
    point resolvers rather than reading an identity table.

    **Identity is resolved before the landing, and the order is a decision.** At
    the web door a subject with no linkage gets the calm no-account page: "this
    system has no record of you" is true earlier and more simply than "nothing in
    your record gives you a view here", the two send the person to two different
    administrators for help, and the landing resolution needs a person before it
    can ask anything at all.

    **A launch with no `person` still reaches the student question.** That is ADR
    0028's student — a `user` row, an enrollment, and no assignment anywhere — and
    the session carries the absence. Making it a refusal would lock every student
    out of the product on the strength of a table nobody fills in for them.

    **The web door resolves no `user`, so it can never answer student.** §2.1's
    table gives the student row one entry point; `ResolvedIdentity` carries
    `user_id=None` at this door by construction rather than by a branch inside the
    resolver.

    **`async def`, and both blocking calls run in a threadpool.** The session is
    synchronous (ADR 0013) and both callers are `async def` handlers, so a
    database read taken on the event loop would block every other request on the
    process — the same seam `app.api.lti` puts every other blocking call through.
    `resolve_landing` reads the database, so it goes through it too.

    **Clearing the login cookie is the caller's**, not this function's: the launch
    door has no login cookie left to clear (ADR 0089), and the web door clears its
    own on every way out of the callback rather than on this one.

    The CSRF token is bound to the session's own `jti`, which is read back off the
    issued token: `issue_session` mints the `jti` and returns the token, and
    `verified_session` is the one way to read the claims it put inside.
    """
    if door is Door.WEB:
        person = await run_in_threadpool(person_behind_a_web_login, db, claims)
        if person is None:
            return no_account()
        identity = ResolvedIdentity(person_id=person, user_id=None)
    else:
        identity = await run_in_threadpool(identity_behind_a_launch, db, claims)

    role = await run_in_threadpool(
        resolve_landing,
        db,
        door=door,
        person_id=identity.person_id,
        user_id=identity.user_id,
        settings=settings,
    )
    if role is None:
        return no_access()
    token = issue_session(
        door=door,
        role=role,
        sub=str(claims.get("sub") or ""),
        person_id=None if identity.person_id is None else str(identity.person_id),
        user_id=None if identity.user_id is None else str(identity.user_id),
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


# ---------------------------------------------------------------------------
# Role scoping: the dependency a student-only route carries. §13's second phrase
# for this module, arriving with the first screen that needs it (E2-08).
# ---------------------------------------------------------------------------

# What a request with no student session is answered. 401 and not 403, and the
# `WWW-Authenticate` challenge is why: RFC 6750 §3 makes the challenge how a
# client learns the scheme it should present a credential under, and this API is
# presented a session as a Bearer token (SPEC §7.3's cookieless path). 403 would
# say "you are somebody, and not somebody who may do this", which is a statement
# about the caller that this route deliberately never makes.
NOT_A_STUDENT_STATUS = 401
BEARER_SCHEME = "Bearer"

# The registry key of the one sentence both refusals below serve.
NOT_A_STUDENT_KEY = "student.not_a_student"


def require_student(request: Request) -> SessionClaims:
    """The verified session on `request`, if it is a student's; otherwise a 401.

    **An absent session, an invalid one and somebody else's are one answer.** The
    same status, the same challenge and the same sentence, because the differences
    between them are all statements about this route: a body naming the role would
    tell the holder of any session which surfaces exist for which role, and a 403
    for a valid non-student session against a 401 for no session would say the same
    thing in the status line. `app.services.session.session_from_request` already
    collapses "no token", "a token this deployment did not sign" and "an expired
    one" into a single `None` for the same reason.

    **The role comes from the session and not from a claim the platform wrote.**
    `LandingRole` is resolved at the door out of Pulse's own records (E1-13, ADR
    0098) and sealed into the token; what this reads is that resolution.

    The sentence is looked up in `app.copy` rather than written here, because a
    student reads it and E2-11's inventory has to be able to find every string a
    student reads.

    Returns `SessionClaims` — the claims object the doors already issue, not a
    type of its own. What a submit path needs from it is `user_id`, which E1-12
    put there as "the launch-side row", and a second wrapper around it would be a
    second answer to "who is this" for the two modules to disagree about.
    """
    claims = session_from_request(request, request.app.state.session_secret)
    if claims is None or claims.role is not LandingRole.STUDENT:
        raise HTTPException(
            status_code=NOT_A_STUDENT_STATUS,
            detail=COPY[NOT_A_STUDENT_KEY].text,
            headers={"WWW-Authenticate": BEARER_SCHEME},
        )
    return claims
