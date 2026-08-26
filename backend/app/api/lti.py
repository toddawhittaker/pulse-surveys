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
    launch_landing_or_refusal,
    refused,
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
from app.services.provisioning import provision_from_launch

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

    `pylti1p3`'s `OIDCLogin` (`app.lti.launch.begin_a_launch`) mints the `state`
    and `nonce` and remembers the mapping server-side (`app.lti.in_flight`); this
    handler commits that write so the launch, a separate request, can read it. No
    cookie is set here at all — E0-18's signed login cookie is gone from this door
    and its state/nonce role is the server-side handshake store now (ADR 0089).
    """
    settings = request.app.state.settings
    form = form_body(await request.body())
    try:
        url = await run_in_threadpool(begin_a_launch, session, settings, form)
    except LaunchRefusedError as refusal:
        return refused(str(refusal))

    await run_in_threadpool(session.commit)
    return RedirectResponse(url, status_code=FOUND)


@router.post(LAUNCH_PATH, summary="LTI 1.3 launch: verify the token and issue a session")
async def launch(request: Request, session: Session = Depends(get_session)) -> Response:
    """Verify what the platform posted back, issue a session, and hand it over.

    On a valid launch the door issues the session `app.services.session` defines,
    sets the session and CSRF cookies, and returns a fragment redirect to the
    role's landing route (`launch_landing_or_refusal`) — the response contract
    E1-08 replaces E0-18's inline landing page with.

    The session is committed on both paths, and each commit persists a different
    thing. On success it persists the claimed nonce, which is what makes the
    launch single-use survive to the next request. On a refusal it persists the
    consumed in-flight `state` (`verified_launch` deleted it, burn-after-use), so a
    correct `state` replayed after a refusal finds nothing and is refused too.

    **What a verified launch discovers is written before the landing is resolved**
    (E1-10, ADR 0091). `provision_from_launch` writes the launching subject's
    `user` row on every verified launch and, for a staff launch, the course and
    section its context names — and it runs here rather than after the landing
    because a launch this door has nothing to *show* is still a launch that
    authenticated somebody: a teaching assistant is refused a view and is no less
    a person E1-12 has to be able to link. It never refuses a launch of its own
    accord; an unreadable context is written down and the person lands anyway.

    **Its work gets a commit of its own, after the launch's.** The two are
    independent: the nonce claim and the consumed handshake are what make this
    launch single-use, and they must not be hostage to what provisioning found in
    the context.
    """
    settings = request.app.state.settings
    form = form_body(await request.body())
    try:
        claims = await run_in_threadpool(
            verified_launch, session, request.app.state.http, settings, form
        )
    except LaunchRefusedError as refusal:
        answer: Response = refused(str(refusal))
        await run_in_threadpool(session.commit)
        return answer

    await run_in_threadpool(session.commit)
    await run_in_threadpool(provision_from_launch, session, claims)
    await run_in_threadpool(session.commit)
    return launch_landing_or_refusal(
        claims,
        settings=settings,
        secret=request.app.state.session_secret,
        no_role_reason=(
            "The launch states no role this tool has a view for, so there is nothing to show you."
        ),
    )
