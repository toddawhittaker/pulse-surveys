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
"""

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app import __version__
from app.api import auth, dev, health, lti
from app.config import DEVELOPMENT_ENVIRONMENT, Settings

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


def documentation_is_served(settings: Settings) -> bool:
    """Whether the schema and its documentation get routes at all.

    **Served only when `ENVIRONMENT` is exactly `development`** (ADR 0074). The
    schema is a list of every route this application answers on, and §6.2's
    reveal surface and §5.5's roll-ups are what such a list points at — in a
    system that holds student comment text, handed to any browser an LMS launched
    into an iframe. Keeping it for developers costs one comparison; the value
    compared against is the same one `app/db.py` and `scripts/seed.py` already
    key on, and it is `app.config.DEVELOPMENT_ENVIRONMENT`.
    """
    return settings.environment == DEVELOPMENT_ENVIRONMENT


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

    return app
