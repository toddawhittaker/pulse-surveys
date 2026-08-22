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

**Two Advantage surfaces do add to that, and this paragraph used to name only
one.** Most routes carry only a context identifier, which is this platform's own
invention, and a member's address appears in a response body where no log
follows. These two are different, and uvicorn's access log records the path *and*
the query string of every request:

  - `<lineitem>/results/<userId>` puts an LTI `sub` in a **request path**. The
    route is served because AGS makes a `Result`'s `id` a URL and a platform that
    composes one it will not answer is worse; a real platform would put an opaque
    per-result identifier there rather than the user's.
  - `<lineitem>/results?user_id=<sub>` puts the same `sub` in a **query string**.
    That is AGS 2.0's own filter on the Result container and it is honoured here,
    because a tool asking for one student's result and receiving the class is
    holding grades it did not ask for. Since E0-28 item 4 the container is also
    paged, which makes this the route a tool reads results through rather than an
    occasional one — and the `Link` relations this platform builds carry the
    request's query, so **the platform hands the tool a `sub`-bearing URL for
    every page** and a conformant walk re-issues one per page.

On this platform every one of those identifiers is a seeded value describing
nobody, so nothing here is at risk. **Both are shapes E1 must not copy**: on a
real deployment either would write a student's LMS user ID into an access log,
which SPEC §10 forbids, and avoiding the per-user route while walking the
filtered container avoids nothing. Whatever E1 does about this has to cover the
filter and the paging as well as the path.
"""

import json
from typing import Annotated, Any
from urllib.parse import parse_qsl, unquote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.ags import (
    LINE_ITEM_CONTAINER_MEDIA_TYPE,
    LINE_ITEM_MEDIA_TYPE,
    LINE_ITEM_PAGE_SIZE,
    MAX_LINE_ITEM_LIMIT,
    MAX_RESULT_LIMIT,
    RESULT_CONTAINER_MEDIA_TYPE,
    RESULT_MEDIA_TYPE,
    RESULT_PAGE_SIZE,
    GradeBook,
    GradeServiceError,
    LineItem,
    LineItemFilters,
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
    RESULT_PATH,
    RESULTS_PATH,
    SCORES_PATH,
    PlatformSettings,
)
from app.launch import (
    AuthorizationRequestError,
    id_token_claims,
    resolve_launch,
)
from app.nrps import MEMBERSHIP_CONTAINER_MEDIA_TYPE, membership_page
from app.pages import authorization_response_page, launch_page, registration_values
from app.paging import (
    PAGE_PARAMETER,
    PageOutOfRangeError,
    link_header,
    page_count,
    page_size,
    window,
)
from app.seed import MockContext, seeded_platform
from app.signing import SIGNATURE_ALGORITHM, IssuerKey

SERVICE_NAME = "mock-lms"

SUMMARY = "A development-only LTI 1.3 platform to launch Pulse from (SPEC §9.2)."

# How an OIDC authorization request arrives when a tool posts it.
FORM_MEDIA_TYPE = "application/x-www-form-urlencoded"

# How many path segments come before the user identifier in `RESULT_PATH`.
# Counted off `RESULTS_PATH` rather than written as a number, so that moving
# the Advantage paths moves this with them. See `addressed_user_id`.
RESULT_PATH_SEGMENTS_BEFORE_THE_USER = len(RESULTS_PATH.strip("/").split("/"))


def advertised(base: str, query: str) -> str:
    """`base` carrying the query this request arrived with, so a `Link` can keep it.

    The paging helpers build every other page's URL from this one, and they
    replace the page parameter rather than appending to it — so handing them the
    request's whole query is what makes a filtered or limited container advertise
    the second page *of that filter* rather than of everything. A `next` relation
    that quietly drops a filter is the paging defect that looks most like
    working.

    The base is the platform's own absolute URL rather than `request.url`,
    because a tool resolves what a service advertised knowing nothing about the
    host it reached, and `request.url` carries whatever `Host` header arrived.
    """
    return f"{base}?{query}" if query else base


def addressed_user_id(request: Request) -> str:
    """The `userId` a per-user result request addressed, decoded exactly once.

    **Read off the wire rather than off the route parameter, and that is not
    fussiness.** `ags.result_url` percent-encodes the whole identifier with
    `safe=""`, so a `sub` of `a/b` is handed out as `…/results/a%2Fb` and a `sub`
    of `a%2Fb` — an ordinary identifier that happens to look like an encoding —
    is handed out as `…/results/a%252Fb`. They are two students, and one decode
    of each keeps them two. A second decode makes them one, and the platform then
    serves one student's grade to a request about the other, with a 200 (E0-28
    item 9's near miss).

    How many times the path has already been decoded when a route parameter
    reaches this application depends on the server, which is exactly why this
    does not trust it. Measured on 2026-08-21, on one route with one `:path`
    parameter:

      - **uvicorn** decodes once. `a%252Fb` arrives as `a%2Fb`. Correct.
      - **`fastapi.testclient.TestClient`** (starlette 1.6.0, httpx 0.28.1)
        decodes twice: its transport builds the scope with `unquote(path)` where
        `path` is httpx's `URL.path`, which is already decoded. `a%252Fb` arrives
        as `a/b` — the collision above, in the harness every test in this
        repository drives this platform through.

    `raw_path` is the request as it was received, so decoding it here once is
    the same answer under both. ASGI makes `raw_path` optional; where a server
    omits it there is nothing better to fall back on than the route parameter,
    and that fallback is this platform's behaviour under such a server rather
    than a case anything here can fix.

    The number of segments to skip is derived from `RESULTS_PATH` rather than
    written as `6`, so moving the Advantage paths moves this with them.
    """
    raw = request.scope.get("raw_path")
    if not isinstance(raw, bytes):
        return str(request.path_params.get("user_id", ""))
    segments = raw.decode("utf-8", errors="replace").strip("/").split("/")
    return unquote("/".join(segments[RESULT_PATH_SEGMENTS_BEFORE_THE_USER:]))


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
        role: Annotated[str | None, Query()] = None,
        limit: Annotated[str | None, Query()] = None,
        rlid: Annotated[str | None, Query()] = None,
    ) -> JSONResponse:
        """One page of a membership container, and a `Link` header to the next.

        The header is the only place paging is expressed. A next URL in the body
        would read correctly to anyone looking at the response and would leave a
        conformant client syncing page one and calling it the class.

        **NRPS's own three filters are declared here in order to be refused**
        (E0-28 item 2). They were not parameters at all, so FastAPI dropped them
        and the container answered 200 with the whole page: a tool asking for
        `role=…#Instructor` was handed every member and could not tell that from
        a section where everyone teaches. Accepted-and-disregarded is the one
        state a client cannot detect, and it is what lets a reliance on
        server-side filtering ship — a reliance no platform guarantees, because
        NRPS permits a platform to ignore these.

        Refusing rather than implementing `role` is E0-28's ruling, on E0-30 item
        4's strictness argument: a 400 naming the parameter is a sentence the
        tool's author reads once and acts on. They are typed `str` rather than
        `int` for `limit` so that *any* value is refused with this 400 rather
        than some values with FastAPI's own 422 — the fact being reported is that
        the parameter is not implemented, not that its value was unreadable.

        `page` keeps working. It is the cursor the roster walk moves by, and a
        container that refused every query parameter would turn every seeded
        roster into its first page.
        """
        refused = [
            name
            for name, value in (("role", role), ("limit", limit), ("rlid", rlid))
            if value is not None
        ]
        if refused:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"This membership container does not implement NRPS query filtering, and "
                    f"{refused} asks it to. NRPS 2.0 defines `role`, `limit` and `rlid` and "
                    "permits a platform to ignore them, so a tool must filter client-side "
                    "whatever a platform accepts — and this one refuses rather than accepting "
                    f"and disregarding, which a tool cannot tell from a filter that worked. "
                    f"`{PAGE_PARAMETER}` is the one parameter this container implements."
                ),
            )
        context = require_context(context_id)
        try:
            served = membership_page(platform, settings, context, page)
        except PageOutOfRangeError as refusal:
            raise HTTPException(status_code=404, detail=str(refusal)) from refusal
        return JSONResponse(
            served.document,
            media_type=MEMBERSHIP_CONTAINER_MEDIA_TYPE,
            headers={"link": served.link_header},
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

    @app.get(LINE_ITEMS_PATH, summary="AGS 2.0: list a section's line items, filtered and paged")
    def list_line_items(
        request: Request,
        context_id: str,
        resource_link_id: str | None = None,
        resource_id: str | None = None,
        tag: str | None = None,
        limit: Annotated[int | None, Query(ge=1)] = None,
        page: Annotated[int, Query(alias=PAGE_PARAMETER, ge=1)] = 1,
    ) -> JSONResponse:
        """One page of this section's line items, in creation order.

        An array, which is what AGS 2.0 serves for a line item container. Nothing
        is seeded here: §3.4 has the tool create "Pulse Participation" on first
        launch, so a seeded one would let a test mistake a fixture for a stored
        line item.

        The three filters and the paging are AGS's own, and they page exactly as
        the roster does — same module, same `Link` header, same rule that `next`
        appears only where a next page exists. The next URL is built from the
        query this request carried, so a filtered container's second page is the
        second page *of that filter* rather than of everything.
        """
        require_context(context_id)
        found = grades.line_items(
            context_id,
            LineItemFilters(resource_link_id=resource_link_id, resource_id=resource_id, tag=tag),
        )
        size = page_size(limit, LINE_ITEM_PAGE_SIZE, MAX_LINE_ITEM_LIMIT)
        try:
            shown = window(found, page, size)
        except PageOutOfRangeError as refusal:
            raise HTTPException(status_code=404, detail=str(refusal)) from refusal
        base = advertised(settings.line_items_url(context_id), request.url.query)
        header = link_header(base, page, page_count(len(found), size))
        return JSONResponse(
            [line_item.document for line_item in shown],
            media_type=LINE_ITEM_CONTAINER_MEDIA_TYPE,
            headers={"link": header},
        )

    @app.get(LINE_ITEM_PATH, summary="AGS 2.0: one line item")
    def read_line_item(context_id: str, line_item_id: str) -> JSONResponse:
        """The line item at its own `id`, which is what makes that `id` a URL.

        **What this route is for**, because it arrived in E0-15 without a
        criterion and E0-28 item 7 asked for one or for its deletion. AGS 2.0
        defines it, and E3's line-item reconciliation reads it: a tool holding an
        id from a previous term needs to ask whether that line item still exists
        and still carries the maximum it was created with, without listing a
        container and searching it. Keeping it is the ruling — deleting a
        conformant route to re-add it one epic later is churn.

        It also carries item 3's round trip. The platform mints ids with a query
        (`…/3?type_id=3`) and this is where "the platform serves the exact id it
        minted" is asked; a platform that minted one and routed only `…/3` would
        have handed a tool an id it cannot use, and E3 would meet that as a 404
        on a URL the platform itself composed.
        """
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
            # The status comes off the refusal rather than being chosen here.
            # AGS 2.0 fixes 409 for a stale score and leaves the rest to the
            # platform, so which code answers is a fact about the rule that was
            # broken and belongs beside it.
            raise HTTPException(status_code=refusal.status_code, detail=str(refusal)) from refusal
        return JSONResponse({"resultUrl": result_url(line_item, str(payload["userId"]))})

    @app.get(RESULTS_PATH, summary="AGS 2.0: the results for one line item, filtered and paged")
    def read_results(
        request: Request,
        context_id: str,
        line_item_id: str,
        user_id: str | None = None,
        limit: Annotated[int | None, Query(ge=1)] = None,
        page: Annotated[int, Query(alias=PAGE_PARAMETER, ge=1)] = 1,
    ) -> JSONResponse:
        """The conformant `Result` container: the current grade, and nothing else.

        A `Result` has no timestamp and no progress members, so what the tool
        posted cannot be read back here. `GET /mock/posted-scores` is where that
        lives, deliberately outside this namespace (ADR 0047).

        `user_id` is AGS's own filter and is honoured, because a tool asking a
        platform for one student's result and receiving the class is holding
        grades it did not ask for.

        **The container pages, exactly as the roster and the line-item container
        do** — same module, same `Link` header, same rule that `next` appears
        only where a next page exists (E0-28 item 4). It used to answer
        everything in one response, which is a mock smoother than the platforms
        it stands in for: a 200-student section on a platform paging at 50 reads
        back 50 results and 150 apparent non-submitters, and E3 re-posts those
        150 grades every week without ever converging.

        The `Link` URLs are built from the query this request carried, so the
        filter survives into every relation. A container that filtered correctly
        and advertised an unfiltered `first`, `last` or `current` hands a tool
        the whole class the moment it follows one — and it fails open, which is
        the paging defect that looks most like working.
        """
        line_item = require_line_item(context_id, line_item_id)
        found = grades.results(line_item, user_id=user_id)
        size = page_size(limit, RESULT_PAGE_SIZE, MAX_RESULT_LIMIT)
        try:
            shown = window(found, page, size)
        except PageOutOfRangeError as refusal:
            raise HTTPException(status_code=404, detail=str(refusal)) from refusal
        base = advertised(settings.results_url(context_id, line_item_id), request.url.query)
        header = link_header(base, page, page_count(len(found), size))
        return JSONResponse(
            list(shown),
            media_type=RESULT_CONTAINER_MEDIA_TYPE,
            headers={"link": header},
        )

    @app.get(RESULT_PATH, summary="AGS 2.0: one user's result on one line item")
    def read_result(request: Request, context_id: str, line_item_id: str) -> JSONResponse:
        """The result at the URL the platform hands out for it.

        This is the URL a score post answers with as `resultUrl` and the URL
        every `Result` gives as its own `id`. Both were composed and neither was
        served, which is the shape a container test cannot see: the identifier
        looks exactly right and nothing follows it. A tool that follows what a
        platform hands it is doing the right thing.

        A user with no current result is a 404 rather than an empty document —
        "no grade" and "a grade of nothing" are different answers, and a score
        posted with no `scoreGiven` means the first.

        The identifier comes from `addressed_user_id` rather than from the route
        parameter, for the reason that function gives at length: one decode of
        what the wire carried, whatever the server did to the path on the way in.
        """
        line_item = require_line_item(context_id, line_item_id)
        user_id = addressed_user_id(request)
        found = grades.result(line_item, user_id)
        if found is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No result for {user_id!r} on line item {line_item_id!r}. Either no score "
                    "has been accepted for that user, or the last one carried no `scoreGiven`, "
                    "which AGS 2.0 makes a request to clear the result."
                ),
            )
        return JSONResponse(found, media_type=RESULT_MEDIA_TYPE)

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
