"""Liveness endpoint.

Deliberately dependency-free: it answers from the settings the application was
built with and touches neither the database nor Redis. A health check that
fails because a downstream is slow tells the orchestrator to restart the one
process that was working.
"""

from fastapi import APIRouter, Request

from app import SERVICE_NAME, __version__
from app.config import Settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness, with the configuration the process is running")
def healthz(request: Request) -> HealthResponse:
    """Report the service, its version, and the environment it was configured with."""
    settings: Settings = request.app.state.settings
    return HealthResponse(
        service=SERVICE_NAME,
        version=__version__,
        environment=settings.environment,
    )
