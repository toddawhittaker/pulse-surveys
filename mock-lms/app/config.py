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
from urllib.parse import quote

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

# The LTI Advantage services (E0-15). Every one of them hangs off a context,
# because that is what NRPS 2.0 and AGS 2.0 scope them to: a roster is one
# section's, and a line item belongs to one section's gradebook. A tool never
# builds these paths — it reads the absolute URLs out of the two service claims
# in the launch — so they are templates here rather than anything a caller
# assembles, and the builders below are the only place they become a URL.
CONTEXT_PATH = "/lti/contexts/{context_id}"
MEMBERSHIPS_PATH = f"{CONTEXT_PATH}/memberships"
LINE_ITEMS_PATH = f"{CONTEXT_PATH}/line_items"
LINE_ITEM_PATH = f"{LINE_ITEMS_PATH}/{{line_item_id}}"
SCORES_PATH = f"{LINE_ITEM_PATH}/scores"
RESULTS_PATH = f"{LINE_ITEM_PATH}/results"

# One user's result, which AGS makes a `Result`'s own `id` and the `resultUrl` a
# score post answers with. It is served because it is handed out: a URL a
# platform composes and does not serve is a link a tool follows once, in the job
# that needed it.
RESULT_PATH = f"{RESULTS_PATH}/{{user_id}}"

# The inspection surface, and the `/mock/` prefix is the point (ADR 0047): a
# conformant AGS `Result` has no timestamp and no progress fields, so what the
# tool posted cannot be read back through the protocol. This route serves it
# outside the AGS namespace, so that a tool which learned it would have learned
# something no real platform serves.
MOCK_POSTED_SCORES_PATH = "/mock/posted-scores"


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

    def absolute(self, path_template: str, **parts: str) -> str:
        """One Advantage URL, absolute, with every part percent-encoded.

        **Absolute, always.** A tool resolves a service URL with no knowledge of
        where the token came from — it may have arrived over a queue or out of a
        session — so a relative path is a service it cannot call. Every service
        URL this platform advertises is built here, which is what keeps that one
        rule in one place.

        `safe=""` on the encoding is deliberate: a context identifier is opaque
        to a tool, so a `/` inside one would silently become a path segment and
        route somewhere else.
        """
        encoded = {name: quote(value, safe="") for name, value in parts.items()}
        return f"{self.issuer}{path_template.format(**encoded)}"

    def memberships_url(self, context_id: str) -> str:
        """Where one section's NRPS roster is served."""
        return self.absolute(MEMBERSHIPS_PATH, context_id=context_id)

    def line_items_url(self, context_id: str) -> str:
        """Where one section's AGS line items are listed and created."""
        return self.absolute(LINE_ITEMS_PATH, context_id=context_id)

    def line_item_url(self, context_id: str, line_item_id: str) -> str:
        """One line item's own URL, which AGS makes its `id`."""
        return self.absolute(LINE_ITEM_PATH, context_id=context_id, line_item_id=line_item_id)

    def results_url(self, context_id: str, line_item_id: str) -> str:
        """Where one line item's AGS Result container is served.

        Built here, from the platform's own paths, because it is what the result
        container's `Link` header is built on — and a `Link` relation composed
        from `request.url` would carry whatever `Host` header arrived rather than
        the address a tool can resolve. See `advertised` in `app.main`.
        """
        return self.absolute(RESULTS_PATH, context_id=context_id, line_item_id=line_item_id)
