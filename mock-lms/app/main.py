"""The mock platform's HTTP surface, and one issuer key per process.

The launch endpoints are E0-14's — the launch page, discovery, the key set, the
registration document and the authorization endpoint — and the LTI Advantage
services below them are E0-15's. The two halves meet in one place: a launch
carries the NRPS and AGS claims, and those claims are the only route by which a
conformant tool learns where the services are.

Run it with `uvicorn app.main:create_app --factory`, the same way the backend is
run. There is no module-level application object, and here that is load-bearing
rather than stylistic: **the issuer key is generated when the application is
built**, so one application is one key, and starting a second platform really is
a second platform. SPEC §9.1 asks for issuer keys generated per test run rather
than fixtures checked into the repository, and a module-level singleton would
quietly turn "per run" into "per import".

The routes are closures over the settings, the seed and the key for the same
reason. Nothing reaches a key through a global, so there is no arrangement of
imports that lets two applications share one.

**Configuration is read here, at build time**, not in a lifespan handler and not
per request. The test fixture in `tests/conftest.py` sets the environment around
the import and the factory call and restores it before lifespan runs, so a
platform that read its issuer in `startup` would read whatever the process
happened to hold — and would pass every test that does not set configuration.

**No launch payload and no roster is logged.** SPEC §10 forbids personally
identifiable information in logs, and a request logger that dumped `id_token`
payloads or membership containers would be a pattern for E1 to copy into a
service whose roster is real people. So nothing here logs: the `id_token` is
returned to the caller and written nowhere, and so is every member.

**What this platform holds changed in E0-15, and the sentence above used to say
it held nothing.** It now holds an email address per seeded person, because
E0-15's scope has NRPS return "email where exposed" — every one of them at a
domain RFC 2606 reserves, so nothing can be delivered to any of them (ADR 0050).
It still holds no name of any kind.

Stated precisely, because "nothing is logged" would be a claim this file cannot
make. Uvicorn's own access log is on, and it records the method, the path and the
status of every request. It never sees an `id_token` — that is returned in a
response body — but an authorization request sent by `GET` rather than by `POST`
carries `state`, `nonce` and `login_hint` in its query string, and the access log
records those. All three are values this platform invented or was handed by a
test; none is a person. Measured against the running container rather than
assumed.

The Advantage routes add nothing to that surface: every one of them carries the
context in its path, and a context identifier is this platform's own invention.
A member's address appears only in a response body.
"""

import json
from typing import Annotated, Any
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.ags import (
    LINE_ITEM_CONTAINER_MEDIA_TYPE,
    LINE_ITEM_MEDIA_TYPE,
    RESULT_CONTAINER_MEDIA_TYPE,
    GradeBook,
    GradeServiceError,
    LineItem,
    result_url,
)
from app.config import (
    AUTHORIZATION_PATH,
    DISCOVERY_PATH,
    HEALTH_PATH,
    JWKS_PATH,
    LAUNCH_PAGE_PATH,
    LINE_ITEM_PATH,
    LINE_ITEMS_PATH,
    MEMBERSHIPS_PATH,
    MOCK_POSTED_SCORES_PATH,
    REGISTRATION_PATH,
    RESULTS_PATH,
    SCORES_PATH,
    PlatformSettings,
)
from app.launch import (
    AuthorizationRequestError,
    id_token_claims,
    resolve_launch,
)
from app.nrps import (
    MEMBERSHIP_CONTAINER_MEDIA_TYPE,
    PAGE_PARAMETER,
    MembershipPageOutOfRangeError,
    membership_page,
)
from app.pages import authorization_response_page, launch_page, registration_values
from app.seed import MockContext, seeded_platform
from app.signing import SIGNATURE_ALGORITHM, IssuerKey

SERVICE_NAME = "mock-lms"

SUMMARY = "A development-only LTI 1.3 platform to launch Pulse from (SPEC §9.2)."

# How an OIDC authorization request arrives when a tool posts it.
FORM_MEDIA_TYPE = "application/x-www-form-urlencoded"


async def json_object(request: Request, subject: str) -> dict[str, Any]:
    """Decode a request body as a JSON object, refusing anything else by name.

    The body is read raw and decoded here rather than declared as a typed model
    on the route, and for the score post that is load-bearing rather than
    stylistic: E0-15 records what the tool sent **verbatim**, and a model is
    precisely a thing that fills in defaults, drops members it has no field for
    and re-renders a timestamp. A record that has been through one cannot be used
    to prove what the tool sent.

    The AGS and NRPS media types all end in `+json`, so the decision about what a
    body *is* belongs here rather than to a content-type match: a tool sending
    `application/json` and a tool sending `application/vnd.ims.lis.v1.score+json`
    are sending the same document.
    """
    raw = await request.body()
    try:
        decoded = json.loads(raw)
    except ValueError as failure:
        raise HTTPException(
            status_code=400,
            detail=f"The {subject} is not JSON: {failure}",
        ) from failure
    if not isinstance(decoded, dict):
        raise HTTPException(
            status_code=400,
            detail=(
                f"The {subject} is a JSON {type(decoded).__name__}, not an object. Both AGS 2.0 "
                "bodies this platform accepts are objects."
            ),
        )
    return decoded


def create_app() -> FastAPI:
    """Build the platform: read the environment, seed it, and generate its key."""
    settings = PlatformSettings.from_environment()
    platform = seeded_platform()
    key = IssuerKey.generate()
    grades = GradeBook(settings=settings)

    app = FastAPI(
        title="Pulse Surveys — mock LMS",
        summary=SUMMARY,
        # No OpenAPI schema, and so no `/docs` and no `/redoc`. This service's
        # contract is OIDC and LTI 1.3, and its discovery document describes it
        # to the only audience that matters. Leaving them on would also put a
        # second route carrying the word `auth` in the routing table
        # (`/docs/oauth2-redirect`), which is one more thing for a tool — or a
        # test discovering endpoints by name — to have to disambiguate.
        openapi_url=None,
    )
    app.state.settings = settings

    @app.get(HEALTH_PATH, summary="Liveness, for the Compose health check")
    def healthz() -> dict[str, str]:
        """Answer from nothing but this process. No downstream, no key material."""
        return {"service": SERVICE_NAME, "status": "ok"}

    @app.get(LAUNCH_PAGE_PATH, response_class=HTMLResponse, summary="The launch page")
    def launch() -> HTMLResponse:
        """A form a browser can click through, per E0-14's scope."""
        return HTMLResponse(launch_page(settings, platform))

    @app.get(DISCOVERY_PATH, summary="OIDC discovery")
    def discovery() -> dict[str, Any]:
        """What a tool reads to find the endpoints, rather than guessing paths.

        Only what this platform actually serves is advertised. There is still no
        `token_endpoint` here, and E0-15 did not add one: its Advantage services
        answer unauthenticated, because no ticket yet says what a tool would sign
        a client assertion with. An advertised endpoint that answers nothing is a
        record asserting something untrue.

        The Advantage services are not advertised here either, and that is the
        protocol rather than an omission: NRPS and AGS are announced per launch,
        in the claims of the `id_token`, because both are scoped to the context
        the launch came from. There is no institution-wide roster URL to publish.
        """
        return {
            "issuer": settings.issuer,
            "authorization_endpoint": settings.authorization_url,
            "jwks_uri": settings.jwks_url,
            "response_types_supported": ["id_token"],
            "response_modes_supported": ["form_post"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": [SIGNATURE_ALGORITHM],
            "scopes_supported": ["openid"],
            "claims_supported": ["iss", "sub", "aud", "exp", "iat", "nonce"],
        }

    @app.get(JWKS_PATH, summary="The platform's public key set")
    def jwks() -> dict[str, Any]:
        """The public half of this process's issuer key, and nothing else.

        Built from `public_jwk()`, which assembles the public members rather than
        filtering the private ones out of a serialised pair — the difference
        being that a member nobody thought to filter cannot appear.
        """
        return {"keys": [key.public_jwk()]}

    @app.get(REGISTRATION_PATH, summary="Everything needed to register this platform")
    def registration() -> dict[str, str]:
        """The registration a developer pastes into `lti_platform`, in one fetch.

        E0-14's scope: "seeded platform registration values matching what
        `lti_platform` from E0-08 expects, so a developer can register the mock in
        one step". The keys are the column names, which is what makes "one step"
        literal rather than an exercise in translation.
        """
        return registration_values(settings)

    @app.api_route(
        AUTHORIZATION_PATH,
        methods=["GET", "POST"],
        response_class=HTMLResponse,
        summary="The authorization endpoint: answers with a signed id_token",
    )
    async def authorize(request: Request) -> HTMLResponse:
        """Answer a tool's authorization request with a signed launch.

        Both methods, because OIDC lets the tool choose and a platform that
        accepted only one would make that choice for it.

        The body is parsed with `parse_qsl` rather than through FastAPI's
        `Form(...)` or Starlette's `request.form()`, and that is a locked-closure
        constraint rather than a preference: both of those require
        `python-multipart`, which this project does not lock, and Starlette 1.6
        asserts on it even for `application/x-www-form-urlencoded`. An
        authorization request is a flat mapping of strings, so `parse_qsl` is the
        whole of what is needed.

        `state` comes back exactly as it arrived. That is the platform's whole
        obligation to it: the value is the tool's, and a platform that
        re-encoded it breaks the tool's cross-site request forgery check in a way
        that reads as a bug in the tool.
        """
        if request.method == "POST":
            media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
            if media_type != FORM_MEDIA_TYPE:
                raise HTTPException(
                    status_code=415,
                    detail=(
                        f"The authorization request was posted as {media_type!r}. An OIDC "
                        f"authorization request is {FORM_MEDIA_TYPE!r}."
                    ),
                )
            body = (await request.body()).decode("utf-8", errors="replace")
            parameters = dict(parse_qsl(body, keep_blank_values=True))
        else:
            parameters = dict(request.query_params)

        try:
            resolved = resolve_launch(parameters, settings, platform)
        except AuthorizationRequestError as refusal:
            # 400 rather than a redirect carrying an OIDC error code. The request
            # that failed is often the one naming where to redirect *to*, and
            # answering a bad `redirect_uri` by using it is how an open
            # redirector is built.
            raise HTTPException(status_code=400, detail=str(refusal)) from refusal

        id_token = key.compact_jws(id_token_claims(resolved, settings))
        return HTMLResponse(
            authorization_response_page(
                id_token=id_token,
                state=resolved.state,
                redirect_uri=resolved.redirect_uri,
            )
        )

    # -- LTI Advantage (E0-15) ----------------------------------------------
    #
    # Every route below is reached through a URL the launch advertised, never
    # through a path a tool assembled, and every one of them is scoped to a
    # context: a roster is one section's and a gradebook is one section's. The
    # gradebook is a closure over this application exactly as the issuer key is,
    # so two platforms started in one process hold two gradebooks (ADR 0049).
    #
    # None of them is authenticated. A real platform puts its Advantage services
    # behind an OAuth 2.0 client-credentials grant; E0-14 built no token endpoint
    # and E0-15 specifies none, and the ticket's out-of-scope list says whichever
    # of E1 and E3 needs a token first is where that grant belongs. An endpoint
    # that answered 401 today would answer it to a tool with nothing to present.

    def require_context(context_id: str) -> MockContext:
        """The seeded section, or a 404 that says which identifiers exist."""
        context = platform.context(context_id)
        if context is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No seeded context {context_id!r}. The seeded contexts are "
                    f"{sorted(seeded.context_id for seeded in platform.contexts)}."
                ),
            )
        return context

    def require_line_item(context_id: str, line_item_id: str) -> LineItem:
        """The line item, or a 404 — checking the section exists first.

        The section is resolved before the line item so that a wrong context and
        an unknown line item are two different messages. They fail identically
        otherwise, and the first is a tool addressing the wrong course.
        """
        require_context(context_id)
        line_item = grades.line_item(context_id, line_item_id)
        if line_item is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No line item {line_item_id!r} in context {context_id!r}. This platform "
                    "creates line items only when a tool posts one; it seeds none, because SPEC "
                    "§3.4 has the tool create its own on first launch."
                ),
            )
        return line_item

    @app.get(MEMBERSHIPS_PATH, summary="NRPS 2.0: one section's roster, one page at a time")
    def memberships(
        context_id: str,
        page: Annotated[int, Query(alias=PAGE_PARAMETER, ge=1)] = 1,
    ) -> JSONResponse:
        """One page of a membership container, and a `Link` header to the next.

        The header is the only place paging is expressed. A next URL in the body
        would read correctly to anyone looking at the response and would leave a
        conformant client syncing page one and calling it the class.
        """
        context = require_context(context_id)
        try:
            served = membership_page(platform, settings, context, page)
        except MembershipPageOutOfRangeError as refusal:
            raise HTTPException(status_code=404, detail=str(refusal)) from refusal
        return JSONResponse(
            served.document,
            media_type=MEMBERSHIP_CONTAINER_MEDIA_TYPE,
            headers={"link": served.link_header} if served.link_header else None,
        )

    @app.post(LINE_ITEMS_PATH, summary="AGS 2.0: create a line item in a section")
    async def create_line_item(context_id: str, request: Request) -> JSONResponse:
        """Store one line item and answer with the identifier scores are posted to."""
        require_context(context_id)
        payload = await json_object(request, "line item")
        try:
            created = grades.create_line_item(context_id, payload)
        except GradeServiceError as refusal:
            raise HTTPException(status_code=422, detail=str(refusal)) from refusal
        return JSONResponse(created.document, status_code=201, media_type=LINE_ITEM_MEDIA_TYPE)

    @app.get(LINE_ITEMS_PATH, summary="AGS 2.0: list a section's line items")
    def list_line_items(context_id: str) -> JSONResponse:
        """Every line item this section's gradebook holds, in creation order.

        An array, which is what AGS 2.0 serves for a line item container. Nothing
        is seeded here: §3.4 has the tool create "Pulse Participation" on first
        launch, so a seeded one would let a test mistake a fixture for a stored
        line item.
        """
        require_context(context_id)
        return JSONResponse(
            [line_item.document for line_item in grades.line_items(context_id)],
            media_type=LINE_ITEM_CONTAINER_MEDIA_TYPE,
        )

    @app.get(LINE_ITEM_PATH, summary="AGS 2.0: one line item")
    def read_line_item(context_id: str, line_item_id: str) -> JSONResponse:
        """The line item at its own `id`, which is what makes that `id` a URL."""
        return JSONResponse(
            require_line_item(context_id, line_item_id).document,
            media_type=LINE_ITEM_MEDIA_TYPE,
        )

    @app.post(SCORES_PATH, summary="AGS 2.0: post a score to a line item")
    async def post_score(context_id: str, line_item_id: str, request: Request) -> JSONResponse:
        """Record one score exactly as it arrived, and say where its result is.

        The body is not modelled, defaulted or normalised anywhere between the
        socket and the store — see `json_object` above and ADR 0047.
        """
        line_item = require_line_item(context_id, line_item_id)
        payload = await json_object(request, "score")
        try:
            grades.record_score(line_item, payload)
        except GradeServiceError as refusal:
            raise HTTPException(status_code=422, detail=str(refusal)) from refusal
        return JSONResponse({"resultUrl": result_url(line_item, str(payload["userId"]))})

    @app.get(RESULTS_PATH, summary="AGS 2.0: the results for one line item")
    def read_results(context_id: str, line_item_id: str) -> JSONResponse:
        """The conformant `Result` container: the current grade, and nothing else.

        A `Result` has no timestamp and no progress members, so what the tool
        posted cannot be read back here. `GET /mock/posted-scores` is where that
        lives, deliberately outside this namespace (ADR 0047).
        """
        return JSONResponse(
            grades.results(require_line_item(context_id, line_item_id)),
            media_type=RESULT_CONTAINER_MEDIA_TYPE,
        )

    @app.get(MOCK_POSTED_SCORES_PATH, summary="Mock only: every score this platform was sent")
    def posted_scores() -> JSONResponse:
        """What the tool posted, verbatim, in the order it arrived.

        Outside the AGS namespace on purpose, under a `/mock/` prefix: a tool
        that learned this route would have learned something no real platform
        serves. It is an inspection surface for tests and for whoever is
        debugging a passback, and it is the reason `Result` above did not have to
        be widened into a shape E3 would then be built against (ADR 0047).

        A log rather than a table keyed by student. §3.4 re-posts a section's
        score after every week closes, so the second posting of one student's
        score sits beside the first and the sequence is what shows a repost
        happened.
        """
        return JSONResponse(
            {
                "scores": [
                    {"lineItem": posted.line_item, "score": posted.score}
                    for posted in grades.posted_scores()
                ]
            }
        )

    return app
