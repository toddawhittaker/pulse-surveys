"""What the mock platform reads from its environment, and what it refuses to.

Five values, all of them addresses. Four are the registration a tool is given —
the issuer, the client ID, the deployment ID, and where the tool's own launch
lands — and the fifth is where the launch page posts, which is the tool's
third-party login-initiation URL. E0-14's sixth acceptance criterion is about the
last two being distinct: the form's **action** is the login-initiation URL, and
`target_link_uri` is a claim naming where the tool should put the user.

**A plain dataclass rather than `pydantic-settings`, deliberately.** A
`BaseSettings` subclass reads a `.env` file out of the working directory if it is
configured to, and the working directory of a test run is this repository, whose
`.env` is the *backend's* configuration. A platform that silently absorbed the
application's environment would be a confusing thing to debug and a worse thing
to review. `os.environ` and nothing else.

**Every value has a default, and the defaults are the Compose network.** The
platform has to start with no configuration at all — that is how the test fixture
starts it, and how `uvicorn app.main:create_app --factory` starts it on a laptop.
`docker-compose.yml` states the same values explicitly in the service's
`environment:` block, so an operator changing where the mock points does it in
the Compose file rather than by reading this module. They agree today; if they
ever disagree, the Compose file is the one a deployment reads.

**No entry in `.env.example`, and that is the rule rather than an oversight.** An
entry there earns its place because an `app.config.Settings` field resolves to it
or because a Compose file interpolates it as `${NAME}` (ADR 0008, and the epic
README's "What the built tickets settled"). Neither is true of anything here: the
Compose values are literals, and this class is not that `Settings`. See
`docs/adr/0037-the-mock-platform-is-configured-by-compose-literals.md`.
"""

import os
from dataclasses import dataclass

# The variable names, together, so that a reader can see the whole configuration
# surface of this service in one place — and so that `docker-compose.yml` and
# this module are comparable line by line.
ISSUER_VARIABLE = "MOCK_LMS_ISSUER"
CLIENT_ID_VARIABLE = "MOCK_LMS_CLIENT_ID"
DEPLOYMENT_ID_VARIABLE = "MOCK_LMS_DEPLOYMENT_ID"
TOOL_LOGIN_URL_VARIABLE = "MOCK_LMS_TOOL_LOGIN_URL"
TOOL_LAUNCH_URL_VARIABLE = "MOCK_LMS_TOOL_LAUNCH_URL"

# Where this service answers on the Compose network, and where `api` does. Not
# `localhost`: a launch is a browser redirect between two containers, and the
# issuer is also how a tool looks the registration up, so it has to be the name
# the rest of the stack can resolve.
DEFAULT_ISSUER = "http://mock-lms:8000"
DEFAULT_TOOL_LOGIN_URL = "http://api:8000/lti/login"
DEFAULT_TOOL_LAUNCH_URL = "http://api:8000/lti/launch"

# The registration identifiers. Fixed strings rather than generated ones: a
# developer pastes them into `lti_platform` and `lti_deployment` once, and a
# value that changed per restart would make that registration wrong by morning.
# Marked as belonging to the mock so that one appearing in a real deployment's
# database is recognisable on sight.
DEFAULT_CLIENT_ID = "mock-lms-client"
DEFAULT_DEPLOYMENT_ID = "mock-lms-deployment-1"

# The paths this service answers on. Written once here and used both to declare
# the routes and to build the absolute URLs the discovery document advertises, so
# a tool that follows discovery and a tool that guesses the path arrive at the
# same place. Moving one is a one-line change; moving one of two copies is a
# platform that advertises an endpoint it does not serve.
LAUNCH_PAGE_PATH = "/"
HEALTH_PATH = "/healthz"
DISCOVERY_PATH = "/.well-known/openid-configuration"
JWKS_PATH = "/.well-known/jwks.json"
AUTHORIZATION_PATH = "/oidc/authorize"
REGISTRATION_PATH = "/registration"


class ConfigurationError(RuntimeError):
    """A configured value is missing or empty. Raised at application build time."""


@dataclass(frozen=True)
class PlatformSettings:
    """The mock platform's whole configuration surface."""

    issuer: str
    client_id: str
    deployment_id: str
    tool_login_url: str
    tool_launch_url: str

    @classmethod
    def from_environment(cls, environment: dict[str, str] | None = None) -> "PlatformSettings":
        """Read the environment once, when the application is built.

        Once, and at build time rather than per request, for the reason
        `backend/app/main.py` gives about its own settings: a value read on every
        request is a value that can change under a running process, and a
        platform whose issuer moved between the launch page and the signature
        would produce launches that match no registration.

        The issuer is an **origin**, and the trailing slash is stripped rather
        than tolerated: the endpoint URLs below are built by appending a path to
        it, so an issuer carrying a path prefix would advertise endpoints this
        service does not answer on.
        """
        source = os.environ if environment is None else environment
        settings = cls(
            issuer=source.get(ISSUER_VARIABLE, DEFAULT_ISSUER).rstrip("/"),
            client_id=source.get(CLIENT_ID_VARIABLE, DEFAULT_CLIENT_ID),
            deployment_id=source.get(DEPLOYMENT_ID_VARIABLE, DEFAULT_DEPLOYMENT_ID),
            tool_login_url=source.get(TOOL_LOGIN_URL_VARIABLE, DEFAULT_TOOL_LOGIN_URL),
            tool_launch_url=source.get(TOOL_LAUNCH_URL_VARIABLE, DEFAULT_TOOL_LAUNCH_URL),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        """Refuse an empty value loudly, at startup, naming the variable.

        An empty `MOCK_LMS_TOOL_LOGIN_URL` produces a launch form that posts to
        the page it is on, which looks like a broken tool rather than a missing
        setting. Failing here costs one line in a container log and saves that
        hour.
        """
        empty = sorted(
            variable
            for variable, value in (
                (ISSUER_VARIABLE, self.issuer),
                (CLIENT_ID_VARIABLE, self.client_id),
                (DEPLOYMENT_ID_VARIABLE, self.deployment_id),
                (TOOL_LOGIN_URL_VARIABLE, self.tool_login_url),
                (TOOL_LAUNCH_URL_VARIABLE, self.tool_launch_url),
            )
            if not value.strip()
        )
        if empty:
            raise ConfigurationError(
                f"The mock LTI platform was given empty values for {empty}. Each one is an "
                "address a launch is assembled from; unset the variable to take the default "
                "rather than setting it to nothing."
            )

    @property
    def jwks_url(self) -> str:
        """Where this platform publishes its key set, as a tool would fetch it."""
        return f"{self.issuer}{JWKS_PATH}"

    @property
    def authorization_url(self) -> str:
        """Where a tool sends its authorization request."""
        return f"{self.issuer}{AUTHORIZATION_PATH}"

    @property
    def discovery_url(self) -> str:
        """Where this platform's OIDC discovery document is served."""
        return f"{self.issuer}{DISCOVERY_PATH}"
