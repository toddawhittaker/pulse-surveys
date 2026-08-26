"""FastAPI application factory (SPEC §13).

Run it with `uvicorn app.main:create_app --factory`. There is no module-level
application object on purpose: settings are read when the app is built, so a
missing variable fails one startup loudly instead of at import time, in
whichever module happened to import this one first.

E0-18 gives the factory three things it did not have, and each is here rather
than in a router because each is one per application:

* **the `/docs` and `/openapi.json` gate**, which is a decision about this
  application's reveal surface (ADR 0074);
* **one HTTP client**, on `app.state.http`, through which every outbound fetch
  either entry door makes goes — a platform's JWKS, the identity provider's
  token endpoint and key set. One client is one place to set a timeout, one
  place a test can route, and one connection pool instead of a fresh TCP
  handshake per launch;
* **one per-process secret**, on `app.state.login_secret`, which signs the
  short-lived cookie both doors carry a `state` and a `nonce` in. What that
  costs, and why it is not a configured value, is in `app.api.deps`.

E1-04 gives it a fourth: **the built single-page application, mounted at
`/app`** — SPEC §13's "FastAPI app factory, router mount, SPA static serve".
Nothing else in the Compose stack serves the frontend, and ADR 0086 records why
it is this process rather than a container of its own.
"""

import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app import __version__
from app.api import auth, dev, health, lti
from app.config import Settings, is_development

# What the tool waits for any single outbound request. A per-request timeout
# beats it where a caller sets one; this is the floor, and it exists so that a
# platform that accepts a connection and never answers cannot hold a worker
# thread for the process lifetime. Not a setting: §6.3's configuration surface
# names no timeout, and a knob here would only ever be turned up.
OUTBOUND_TIMEOUT_SECONDS = 10.0

# Bytes behind the per-process cookie signing key. 32 bytes is the block size
# HS256's HMAC-SHA256 is built on; more would be hashed down to it.
LOGIN_SECRET_BYTES = 32

# What FastAPI serves the interactive documentation and the schema at, and the
# three values that switch them off. `None` removes the *route*; it does not stop
# `app.openapi()` producing the schema, which SPEC §7.1 keeps for the future MCP
# server and §13's client generator calls in process.
DOCS_URL = "/docs"
REDOC_URL = "/redoc"
OPENAPI_URL = "/openapi.json"

# Where the built frontend is served, and where it is found.
#
# The mount is `/app` in three files at once and they have to agree: here,
# `frontend/vite.config.ts`'s `base` (which decides the asset URLs the build
# writes) and `frontend/src/router.tsx`'s `basepath` (which decides what the
# client router thinks a path is). ADR 0086 is the record.
#
# The directory is an environment variable with a default rather than a §6.3
# setting, because it is not a deployment's choice: it says where this process
# can find a directory another build step produced, and the only two answers are
# "the repository's `frontend/dist`" on a developer's machine and "the path the
# image copied it to" in a container. `backend/Dockerfile` sets it, and the
# default below is the repository layout — which is why it is resolved from this
# file's location rather than from the working directory.
FRONTEND_DIST_VARIABLE = "FRONTEND_DIST"
SPA_MOUNT = "/app"
SPA_ENTRY_DOCUMENT = "index.html"
DEFAULT_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


class SinglePageApp(StaticFiles):
    """Static files, with every unmatched path under the mount answered by `index.html`.

    A single-page application's routes exist in the browser: `/app/student` is
    not a file in the build output, so a plain static mount answers 404 and the
    five landing views are reachable only by navigating from `/app/` — which is
    not how a person arrives, and not how the doors hand over once E1-08 and
    E1-09 land the redirects.

    **The fallback is a fallback and not a catch-all.** A request that matches a
    file gets that file; only a 404 becomes the entry document. Answering
    `index.html` to everything under the mount would serve a page whose every
    script and stylesheet came back as HTML — a blank screen, a console full of
    syntax errors, and 200 throughout.

    Nothing is special-cased about the five routes. A server that knew them
    would be a second copy of the route table, in another language, drifting
    from `frontend/src/router.tsx` the first time E2 adds a route.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        """The file at `path`, or the entry document when there is no such file."""
        try:
            return await super().get_response(path, scope)
        except HTTPException as missing:
            # Only a 404. Any other status — a 405 on a non-GET, a 401 from a
            # permission error — is a refusal this must not convert. (A path
            # that escapes the directory is already a 404 in Starlette, not a
            # 403 as an earlier version of this comment claimed; the security
            # review measured it.)
            if missing.status_code != 404:
                raise
            return await super().get_response(SPA_ENTRY_DOCUMENT, scope)


def frontend_dist() -> Path:
    """Where the built SPA is, read fresh on every call.

    Read here rather than at import time, deliberately. `create_app()` is the
    seam SPEC §13 describes, and a mount decided when the module was first
    imported would be fixed for the whole process by whichever caller imported
    it first — so two applications in one process could not disagree, and a test
    that sets the variable before building an app would be answered by a
    decision taken before it ran.
    """
    configured = os.environ.get(FRONTEND_DIST_VARIABLE)
    return Path(configured) if configured else DEFAULT_FRONTEND_DIST


def documentation_is_served(settings: Settings) -> bool:
    """Whether the schema and its documentation get routes at all.

    **Served only when `ENVIRONMENT` is exactly `development`** (ADR 0074). The
    schema is a list of every route this application answers on, and §6.2's
    reveal surface and §5.5's roll-ups are what such a list points at — in a
    system that holds student comment text, handed to any browser an LMS launched
    into an iframe. Keeping it for developers costs one comparison, and the
    comparison is not made here: `app.config.is_development` is the one predicate
    every reader of `ENVIRONMENT` goes through, over the one value
    `app.config.DEVELOPMENT_ENVIRONMENT`. This function stays because "whether
    the documentation is served" is what the caller below is asking, and that is
    a different question from "is this a developer's machine" that happens to
    have the same answer today.
    """
    return is_development(settings)


def create_app() -> FastAPI:
    """Build the application.

    Raises `app.config.ConfigurationError` when a required environment variable
    is absent or malformed. Not `pydantic.ValidationError`: `Settings.__init__`
    converts that one and never lets it escape, because it retains the values it
    was given and this failure is printed to the container startup log. Anything
    catching a failed startup wants `ConfigurationError`.
    """
    settings = Settings()

    # Built here rather than in the lifespan, so that a caller which never runs
    # one — `TestClient(create_app())` without a `with`, which is how the unit
    # tests reach `/healthz` — still gets an application whose doors work.
    http = httpx.Client(timeout=OUTBOUND_TIMEOUT_SECONDS)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Close the client this factory opened, when the process stops serving.

        The client is closed by name rather than by reading `app.state.http`
        back: a test replaces that attribute with one of its own, and closing
        somebody else's client at shutdown would be this application reaching
        into a fixture.
        """
        try:
            yield
        finally:
            http.close()

    documented = documentation_is_served(settings)
    app = FastAPI(
        title="Pulse Surveys",
        version=__version__,
        summary="Weekly course feedback, confidential by construction.",
        lifespan=lifespan,
        docs_url=DOCS_URL if documented else None,
        redoc_url=REDOC_URL if documented else None,
        openapi_url=OPENAPI_URL if documented else None,
    )
    # One settings object per application, reachable from any handler through
    # `request.app.state.settings`. Not a module-level singleton and not
    # cached: two apps in one process (tests, or a future embedded runner) must
    # be able to hold different configurations.
    app.state.settings = settings
    app.state.http = http
    # Per application, so two applications in one process cannot read each
    # other's login cookies, and per *process*, so a restart invalidates the
    # logins that were in flight. `app.api.deps` states both consequences.
    app.state.login_secret = secrets.token_bytes(LOGIN_SECRET_BYTES)

    app.include_router(health.router)
    app.include_router(lti.router)
    app.include_router(auth.router)
    # The developer test console. Always registered; the handler gates itself on
    # `ENVIRONMENT == development` and answers 404 elsewhere, so production is
    # indistinguishable from a route that does not exist (ADR 0074).
    app.include_router(dev.router)

    # The built frontend, if this checkout has one. After the routers, and under
    # a prefix of its own: a static mount at `/` — or a fallback registered
    # first — swallows the API, and the symptom is an application that serves a
    # beautiful blank page and answers no requests.
    #
    # **Absent is a supported state, not a failure.** `frontend/dist` is
    # gitignored and written by `npm run build`, so the backend suite, the
    # migrations, the seed and every backend developer's checkout run without
    # one. The application comes up regardless and `/app` is a 404 — which says
    # there is no frontend here, where a 200 over an empty tree would say there
    # is one and it has nothing to show.
    dist = frontend_dist()
    if dist.is_dir():
        app.mount(SPA_MOUNT, SinglePageApp(directory=dist, html=True), name="spa")

    return app
