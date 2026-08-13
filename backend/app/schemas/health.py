"""The `/healthz` response contract."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """What a healthy API answers with.

    Read by humans, by the Compose health checks (E0-02), and by whatever
    watches the deployment, so the three fields are a stable contract rather
    than a debugging convenience.
    """

    service: str = Field(description="Service name, constant for this application.")
    version: str = Field(description="Version of the running build.")
    environment: str = Field(description="Configured deployment name (`ENVIRONMENT`).")
