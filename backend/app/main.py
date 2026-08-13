"""FastAPI application factory (SPEC §13).

Run it with `uvicorn app.main:create_app --factory`. There is no module-level
application object on purpose: settings are read when the app is built, so a
missing variable fails one startup loudly instead of at import time, in
whichever module happened to import this one first.
"""

from fastapi import FastAPI

from app import __version__
from app.api import health
from app.config import Settings


def create_app() -> FastAPI:
    """Build the application.

    Raises `app.config.ConfigurationError` when a required environment variable
    is absent or malformed. Not `pydantic.ValidationError`: `Settings.__init__`
    converts that one and never lets it escape, because it retains the values it
    was given and this failure is printed to the container startup log. Anything
    catching a failed startup wants `ConfigurationError`.
    """
    settings = Settings()

    app = FastAPI(
        title="Pulse Surveys",
        version=__version__,
        summary="Weekly course feedback, confidential by construction.",
    )
    # One settings object per application, reachable from any handler through
    # `request.app.state.settings`. Not a module-level singleton and not
    # cached: two apps in one process (tests, or a future embedded runner) must
    # be able to hold different configurations.
    app.state.settings = settings
    app.include_router(health.router)

    return app
