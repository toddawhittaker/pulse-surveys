"""What the mock provider reads from its environment, and what it refuses to.

Three values, all of them addresses. The issuer is who this provider says it is;
the client ID and the redirect URI are the **one registered client** — Pulse —
and where a session is delivered to it. An authorization request names both, so
without them there is no flow at all, which is why they are published rather than
left to be read out of this file (see `MOCK_REGISTRATION_PATH` below and
`docs/adr/0058-the-mock-provider-publishes-its-registration-and-its-seed.md`).

**A plain dataclass rather than `pydantic-settings`, deliberately**, for the
reason `mock-lms/app/config.py` gives: a `BaseSettings` subclass can read a
`.env` file out of the working directory, and the working directory of a test run
is this repository, whose `.env` is the *backend's* configuration. A provider
that silently absorbed the application's environment would be a confusing thing
to debug and a worse thing to review. `os.environ` and nothing else.

**Every value has a default, and the defaults are the Compose network.** The
provider has to start with no configuration at all — that is how the test fixture
starts it, and how `uvicorn app.main:create_app --factory` starts it on a laptop.
`docker-compose.yml` states the same values explicitly in the service's
`environment:` block, so an operator changing where the mock points does it in
the Compose file rather than by reading this module. They agree today; if they
ever disagree, the Compose file is the one a deployment reads.

**No entry in `.env.example`, and that is the rule rather than an oversight.** An
entry there earns its place because an `app.config.Settings` field resolves to it
or because a Compose file interpolates it as `${NAME}` (ADR 0008, and the epic
README's "What the built tickets settled"). Neither is true of anything here: the
Compose values are literals, and this class is not that `Settings`. E0-14 faced
the same choice and ADR 0037 asked E0-16 to reach the same answer or say why not;
this is reaching it, for the same reason — three variables with one correct value
each are three knobs with one setting, in the file an operator reads to deploy
Pulse.
"""

import os
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit

# The variable names, together, so that a reader can see the whole configuration
# surface of this service in one place — and so that `docker-compose.yml` and
# this module are comparable line by line.
ISSUER_VARIABLE = "MOCK_IDP_ISSUER"
CLIENT_ID_VARIABLE = "MOCK_IDP_CLIENT_ID"
REDIRECT_URI_VARIABLE = "MOCK_IDP_TOOL_REDIRECT_URI"

# Where this service answers on the Compose network, and where `api` does. Not
# `localhost`: the issuer is what a client compares an `id_token`'s `iss`
# against, and the redirect is a browser hop between two containers, so both have
# to be names the rest of the stack can resolve.
DEFAULT_ISSUER = "http://mock-idp:8000"
DEFAULT_TOOL_REDIRECT_URI = "http://api:8000/auth/oidc/callback"

# The one registered client: Pulse itself. A fixed string rather than a generated
# one, because a developer pastes it into the tool's configuration once and a
# value that changed per restart would make that configuration wrong by morning.
# Marked as belonging to the mock so that one appearing in a real deployment's
# configuration is recognisable on sight.
DEFAULT_CLIENT_ID = "mock-idp-client"

# The paths this service answers on. Written once here and used both to declare
# the routes and to build the absolute URLs the discovery document advertises, so
# a client that follows discovery and a client that guessed the path arrive at
# the same place. Moving one is a one-line change; moving one of two copies is a
# provider that advertises an endpoint it does not serve.
INDEX_PATH = "/"
HEALTH_PATH = "/healthz"

# **Not a choice.** OpenID Connect Discovery 1.0 §4 fixes this path, and E0-16's
# scope repeats it: a provider serving its metadata anywhere else is one no
# conformant client can configure itself from.
DISCOVERY_PATH = "/.well-known/openid-configuration"

JWKS_PATH = "/.well-known/jwks.json"
AUTHORIZATION_PATH = "/oidc/authorize"
# `noqa: S105` — the rule flags any string assigned to a name carrying "token",
# and this is a URL path. The rule is worth keeping switched on everywhere else:
# it is what would flag a real credential written into this repository.
TOKEN_PATH = "/oidc/token"  # noqa: S105

# Where the login form posts. A separate route from the authorization endpoint on
# purpose: `GET /oidc/authorize` asks who is signing in, and this is the answer,
# so the two are a page and its submission rather than one endpoint that behaves
# differently by method.
LOGIN_PATH = "/oidc/login"

# The registration and seed document, **outside the protocol surface** under the
# `/mock/` prefix ADR 0047 established for exactly this. A client that learned
# this route would have learned something no real provider serves: an
# institutional IdP hands out a `client_id` through a registration process, and
# never lists the people it can sign in. The prefix is also what keeps the word
# "registration" here from having to be advertised as an RFC 7591 dynamic client
# registration endpoint — which this provider does not serve, and an advertised
# endpoint that answers nothing is a record asserting something untrue.
MOCK_REGISTRATION_PATH = "/mock/registration"


# What the authorization response appends to the registered redirect URI
# (RFC 6749 §4.1.2). Named here because `validate()` refuses a registration that
# would collide with them; `app.flow.authorization_response` is what appends them.
RESPONSE_PARAMETERS = frozenset({"code", "state"})


class ConfigurationError(RuntimeError):
    """A configured value is missing or unusable. Raised at application build time."""


@dataclass(frozen=True)
class ProviderSettings:
    """The mock provider's whole configuration surface."""

    issuer: str
    client_id: str
    redirect_uri: str

    @classmethod
    def from_environment(cls, environment: dict[str, str] | None = None) -> "ProviderSettings":
        """Read the environment once, when the application is built.

        Once, and at build time rather than per request, for the reason
        `backend/app/main.py` gives about its own settings: a value read on every
        request is a value that can change under a running process, and a
        provider whose issuer moved between the discovery document and the
        signature would issue sessions that match no configuration.

        The issuer is an **origin**, and the trailing slash is stripped rather
        than tolerated: OIDC Discovery 1.0 §4.3 compares the issuer to an
        `id_token`'s `iss` exactly, and §4 builds the well-known URL by
        concatenation, so a slash produces either a double slash or a mismatch
        depending on which client reads it.
        """
        source = os.environ if environment is None else environment
        settings = cls(
            issuer=source.get(ISSUER_VARIABLE, DEFAULT_ISSUER).strip().rstrip("/"),
            client_id=source.get(CLIENT_ID_VARIABLE, DEFAULT_CLIENT_ID).strip(),
            redirect_uri=source.get(REDIRECT_URI_VARIABLE, DEFAULT_TOOL_REDIRECT_URI).strip(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        """Refuse an empty or relative value loudly, at startup, naming the variable.

        An empty `MOCK_IDP_TOOL_REDIRECT_URI` produces a provider that refuses
        every authorization request Pulse sends, which looks like a broken tool
        rather than a missing setting. A *relative* one is worse: a browser has
        nothing to resolve it against, so the session would be delivered
        somewhere nobody chose. Failing here costs one line in a container log
        and saves that hour.
        """
        empty = sorted(
            variable
            for variable, value in (
                (ISSUER_VARIABLE, self.issuer),
                (CLIENT_ID_VARIABLE, self.client_id),
                (REDIRECT_URI_VARIABLE, self.redirect_uri),
            )
            if not value
        )
        if empty:
            raise ConfigurationError(
                f"The mock OIDC provider was given empty values for {empty}. Unset the variable "
                "to take the default rather than setting it to nothing."
            )

        relative = sorted(
            variable
            for variable, value in (
                (ISSUER_VARIABLE, self.issuer),
                (REDIRECT_URI_VARIABLE, self.redirect_uri),
            )
            if not urlsplit(value).scheme or not urlsplit(value).netloc
        )
        if relative:
            raise ConfigurationError(
                f"The mock OIDC provider was given relative URLs for {relative}. Both are "
                "absolute by specification: the issuer is what a client compares `iss` against "
                "(OIDC Core 1.0 §3.1.3.7), and the redirect URI is where a browser is sent "
                "(RFC 6749 §3.1.2)."
            )

        # RFC 6749 §3.1.2 forbids a fragment in a redirection URI, in the same
        # sentence that requires it to be absolute. The reason it is checked
        # rather than tolerated: the authorization response appends `code` and
        # `state` to this URI as a query, and a browser given
        # `…/cb#frag?code=…` keeps everything after the `#` client-side, so the
        # code never reaches the tool and the failure reads as a provider that
        # issued nothing. E0-18 is expected to repoint this variable at a
        # published host address, which is exactly when a hand-edited value picks
        # a fragment up.
        # `"#" in ...` rather than `urlsplit(...).fragment`, and the difference is
        # a measured hole rather than a style: a URI ending in a bare `#` has an
        # **empty** fragment, which is falsy, so the truthiness test registered it.
        # What followed was the confusing failure this check exists to prevent,
        # one step later — `urlunsplit` drops the empty fragment from the
        # authorization response, the tool echoes back the address it was actually
        # sent, and the token endpoint refuses the exchange with `invalid_grant`
        # about a `redirect_uri` mismatch nobody can see.
        if "#" in self.redirect_uri:
            raise ConfigurationError(
                f"{REDIRECT_URI_VARIABLE} is {self.redirect_uri!r}, which carries a fragment — "
                "an empty one still counts. RFC 6749 §3.1.2: a redirection endpoint URI MUST NOT "
                "include a fragment component."
            )

        # A query is legal on a redirection URI and this provider merges its own
        # parameters into it. What is not legal is a query that already carries
        # the two names the authorization response appends: the browser would be
        # sent `?state=preset&code=…&state=…`, so this service would emit the
        # duplicate it refuses on the way in — and a client reading the first
        # `state` would compare against a value it never generated.
        preset = sorted(
            name
            for name, _ in parse_qsl(urlsplit(self.redirect_uri).query, keep_blank_values=True)
            if name in RESPONSE_PARAMETERS
        )
        if preset:
            raise ConfigurationError(
                f"{REDIRECT_URI_VARIABLE} is {self.redirect_uri!r}, whose query already carries "
                f"{preset}. The authorization response appends {sorted(RESPONSE_PARAMETERS)} to "
                "this URI (RFC 6749 §4.1.2), so registering either name here produces a redirect "
                "carrying it twice."
            )

    def absolute(self, path: str) -> str:
        """One of this provider's own paths, as a client would call it."""
        return f"{self.issuer}{path}"

    @property
    def discovery_url(self) -> str:
        """Where this provider's metadata document is served."""
        return self.absolute(DISCOVERY_PATH)

    @property
    def jwks_url(self) -> str:
        """Where this provider publishes its key set, as a client would fetch it."""
        return self.absolute(JWKS_PATH)

    @property
    def authorization_url(self) -> str:
        """Where an authorization request is sent."""
        return self.absolute(AUTHORIZATION_PATH)

    @property
    def token_url(self) -> str:
        """Where an authorization code is redeemed."""
        return self.absolute(TOKEN_PATH)
