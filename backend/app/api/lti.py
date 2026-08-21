"""The launch door: `POST /lti/login` and `POST /lti/launch` (SPEC §13, §7.3).

§13 names this module for exactly these two endpoints. It is thin on purpose:
the two handlers read a form, hand it to `app.lti.launch`, and turn what comes
back into a page. Every decision about whether a launch holds is in that module,
and the view it lands on is `app.services.landing`'s one function.

**Both handlers are `async def` and do their blocking work in a threadpool**, and
the shape is worth a sentence because it is not the obvious one. The body has to
be read with `await`, so the handler cannot be a plain `def`; but the database
session is synchronous (ADR 0013) and so is the HTTP client the JWKS fetch goes
through, and calling either from inside the event loop blocks every other
request on the process. `run_in_threadpool` is the seam between the two, and it
is where the sync-def handlers of §13's other routers would have run anyway.

**The body is parsed with `parse_qsl` rather than with `Form(...)`.** Starlette's
form parsing asserts on `python-multipart` even for
`application/x-www-form-urlencoded`, and this project does not lock it — the same
constraint both mocks record. An initiation request and a launch are flat
mappings of strings, so `parse_qsl` is the whole of what is needed.

**A refusal is a page, never a redirect**, and never quotes what was sent. The
request that failed is often the one naming where a redirect would go, so
answering it by using that address is how an open redirector is built; and a
launch carries a token, which is a credential §10 keeps out of logs and pages
alike.
"""

from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.api.deps import (
    LTI_LOGIN_COOKIE,
    carried_across,
    carry_across,
    clear_carried,
    with_query,
)
from app.db import get_session
from app.lti.launch import (
    LAUNCH_PATH,
    LOGIN_PATH,
    LaunchRefusedError,
    begin_a_launch,
    verified_launch,
)
from app.services.landing import Door, landing_page, landing_role_for, refusal_page

router = APIRouter(tags=["lti"])

# What a refused launch answers. 400 rather than 401 or 403: nothing here is
# authenticated in the HTTP sense — there is no realm to challenge and no
# credential to re-present — the request itself is the thing that does not hold.
REFUSED = 400

# The redirect a login initiation answers with. 302 is what the LTI 1.3 security
# framework and every platform in the field expect; 303 would also be correct
# after a POST and is not what tools send.
FOUND = 302


def form_body(raw: bytes) -> dict[str, str]:
    """One `application/x-www-form-urlencoded` body as a flat mapping.

    `keep_blank_values` is on so that a parameter sent empty arrives as an empty
    string rather than vanishing: "sent blank" and "not sent" are different
    mistakes, and the refusals below can only tell them apart if the parser does.
    """
    return dict(parse_qsl(raw.decode("utf-8", errors="replace"), keep_blank_values=True))


def refused(reason: str) -> HTMLResponse:
    """A 4xx page carrying the reason and no landing view."""
    return HTMLResponse(refusal_page(reason), status_code=REFUSED)


@router.post(LOGIN_PATH, summary="LTI 1.3 third-party-initiated login")
async def login(request: Request, session: Session = Depends(get_session)) -> Response:
    """Answer a platform's login initiation with an authorization request.

    The `state` and `nonce` minted downstream ride back to `/lti/launch` in a
    short-lived signed cookie (`app.api.deps`), which is the only place this
    process remembers them. E1's platform-storage and cookieless work replaces
    that mechanism.
    """
    settings = request.app.state.settings
    form = form_body(await request.body())
    try:
        initiation = await run_in_threadpool(begin_a_launch, session, settings, form)
    except LaunchRefusedError as refusal:
        return refused(str(refusal))

    response = RedirectResponse(
        with_query(settings.lti_platform_authorization_endpoint, initiation.parameters),
        status_code=FOUND,
    )
    carry_across(
        response,
        LTI_LOGIN_COOKIE,
        request.app.state.login_secret,
        {"state": initiation.state, "nonce": initiation.nonce},
        settings,
    )
    return response


@router.post(LAUNCH_PATH, summary="LTI 1.3 launch: verify the token and render the view")
async def launch(request: Request, session: Session = Depends(get_session)) -> Response:
    """Verify what the platform posted back and render the view its roles name.

    Rendered directly in the response — no session, no redirect. There is nowhere
    else to go in a system that does nothing yet, and inventing a session here is
    the E1 work E0-18's boundary section keeps out.

    The cookie is cleared on the way out whichever way this goes: a `state` is
    good once, and one left in the browser is one an attacker can replay into a
    second launch.
    """
    form = form_body(await request.body())
    carried = carried_across(request.app.state.login_secret, request.cookies.get(LTI_LOGIN_COOKIE))

    try:
        claims = await run_in_threadpool(
            verified_launch, session, request.app.state.http, form, carried
        )
    except LaunchRefusedError as refusal:
        answer: Response = refused(str(refusal))
        clear_carried(answer, LTI_LOGIN_COOKIE)
        return answer

    role = landing_role_for(claims, door=Door.LAUNCH)
    if role is None:
        answer = refused(
            "The launch states no role this tool has a view for, so there is nothing to show you."
        )
        clear_carried(answer, LTI_LOGIN_COOKIE)
        return answer

    answer = HTMLResponse(landing_page(role))
    clear_carried(answer, LTI_LOGIN_COOKIE)
    return answer
