"""The launch door, and the tool's key set: `/lti/login`, `/lti/launch`, `/lti/jwks`.

SPEC §13, §7.3. The first two are the launch door E0-18 built; the third is
E1-06's, and it is the other direction of the same asymmetry — a platform signs
a launch and this tool verifies it, and this tool signs a `client_assertion` and
a platform verifies that. All three are thin: the handlers read a form or a
session, hand it to `app.lti.launch` or `app.lti.registration`, and turn what
comes back into a page or a document. Every decision about whether a launch holds
is in the first of those modules, and everything about the key is in the second.

**The two door handlers are `async def` and do their blocking work in a
threadpool**, and the shape is worth a sentence because it is not the obvious
one. The body has to be read with `await`, so neither can be a plain `def`; but
the database session is synchronous (ADR 0013) and so is the HTTP client the
JWKS fetch goes through, and calling either from inside the event loop blocks
every other request on the process. `run_in_threadpool` is the seam between the
two, and it is where the sync-def handlers of §13's other routers would have run
anyway. The key-set handler reads no body, so it is one of those sync defs and
FastAPI puts it in the threadpool itself.

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

from typing import Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.api.deps import (
    FOUND,
    LTI_LOGIN_COOKIE,
    carried_across,
    carry_across,
    clear_carried,
    landing_or_refusal,
    refused,
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
from app.lti.registration import JWKS_PATH, NoSigningKeyError, published_key_set
from app.services.landing import Door

# What a caller is told when this deployment holds no signing key. Short on
# purpose: the route is public in every environment, and the operator's copy of
# this — which table, which command — is in `app.lti.registration`, where
# somebody reading a traceback or the code will find it.
NO_KEY_SET_DETAIL = "This deployment publishes no LTI key set."

# RFC 9110's status for a server that is working and cannot serve this yet.
SERVICE_UNAVAILABLE = 503

router = APIRouter(tags=["lti"])


def form_body(raw: bytes) -> dict[str, str]:
    """One `application/x-www-form-urlencoded` body as a flat mapping.

    `keep_blank_values` is on so that a parameter sent empty arrives as an empty
    string rather than vanishing: "sent blank" and "not sent" are different
    mistakes, and the refusals below can only tell them apart if the parser does.
    """
    return dict(parse_qsl(raw.decode("utf-8", errors="replace"), keep_blank_values=True))


@router.get(JWKS_PATH, summary="This tool's public key set (RFC 7517)")
def jwks(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Publish the public half of the key this tool signs with, and nothing else.

    A platform verifies the `client_assertion` this tool presents at its token
    endpoint against the key set it fetches from here, so a tool that publishes
    none can make no service call at any platform (E1-06 part 4).

    **Registered in every environment, deliberately.** `/docs` (ADR 0074), `/dev`
    (ADR 0079) and the demo seed (ADR 0063) are all gated on `ENVIRONMENT`, so a
    route written beside them inherits that gate without anybody deciding to —
    and a tool whose key set answers 404 in production cannot be registered at a
    real platform at all. There is nothing here to gate: every value it serves is
    public by construction, which is what a public key is for.

    **Never the private half.** `app.lti.registration` assembles the JWK from the
    modulus and the public exponent rather than filtering members out of a
    serialised key pair, so a private member cannot appear through an omission.

    A plain `def`, so FastAPI runs it in a threadpool: the session is synchronous
    (ADR 0013) and reading it from the event loop would block every other request
    on the process.
    """
    try:
        return published_key_set(session)
    except NoSigningKeyError as missing:
        raise HTTPException(status_code=SERVICE_UNAVAILABLE, detail=NO_KEY_SET_DETAIL) from missing


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
        with_query(initiation.authorization_endpoint, initiation.parameters),
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

    return landing_or_refusal(
        claims,
        door=Door.LAUNCH,
        cookie=LTI_LOGIN_COOKIE,
        no_role_reason=(
            "The launch states no role this tool has a view for, so there is nothing to show you."
        ),
    )
