"""E0-16 — the mock OIDC identity provider, driven the way a client drives one.

`mock_idp` and `mock_idps` are the mock LMS's fixtures again for the other entry
door (SPEC §2, §9.2). Two things about them are worth knowing before use. They
**share** what the two mocks genuinely have in common rather than copying it —
the meta-path finder that resolves a second package called `app`, the
fresh-import machinery, the RS256 verifier and the form reader are one
implementation each, in `fixtures/app_imports.py` and `fixtures/lti_platform.py`,
with the per-ticket failure messages staying with the ticket
(`docs/MISTAKES.md` entry 13). And, like `MockPlatform`, the provider is **driven
the way a client drives one**: the endpoints come out of the discovery document,
the identities come out of the login form, and the one thing E0-16 does not say —
how a client learns the seeded `client_id` and redirect URI — is looked for in
three places and then failed on by name rather than guessed at.

Two things arrived with the review round. That question is settled: the provider
publishes a registration document, and [ADR 0058](../../docs/adr/0058-the-mock-provider-publishes-its-registration-and-its-seed.md)
makes `roles`, `launch_only_roles`, `lms_user_id` and `roles_claim` contract
members of it — so the driver now reads the *people* out of that document as well
as the client, which is what lets a test name one seeded person instead of
asserting over whoever happens to be seeded. And `mock_idp_settings` imports a
class rather than driving a route, because one rule — a redirect URI may carry no
fragment — is enforced when the settings are built and has no request that can
ask it.
"""

import base64
import hashlib
import importlib
import inspect
import re
import secrets
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import parse_qs, urljoin, urlsplit

import pytest

from fixtures.app_imports import import_mock_application, mock_package_resolved
from fixtures.lti_platform import (
    APPLICATION_FACTORY_NAMES,
    MOCK_PACKAGE,
    JsonWebSignature,
    declared_paths,
    form_submissions,
    forms_in,
    local_target,
    split_jws,
    url_with_query,
    verifying_key,
)
from fixtures.repo import BASE_COMPOSE_PATH, REPO_ROOT, load_compose
from fixtures.supervision import ROLE_ALIASES

# ---------------------------------------------------------------------------
# E0-16 — the mock OIDC identity provider, driven the way a client drives one.
# ---------------------------------------------------------------------------

# SPEC §13's layout again, and §7.2's service list: `mock-idp/` holding a
# `Dockerfile` and an `app/`, run as the Compose service `mock-idp`.
MOCK_IDP_DIR = REPO_ROOT / "mock-idp"
MOCK_IDP_SERVICE = "mock-idp"

# Where the ASGI application might sit inside that package, most likely first —
# the same list as the platform's with the platform-shaped names swapped for
# provider-shaped ones. Nothing in E0-16 spells a module, so it is discovered.
MOCK_IDP_MODULES = ("app.main", "app", "app.provider", "app.idp", "app.server", "app.api")

# Where the provider's settings object might sit, and what it might be called.
# `mock-lms/app/config.py` holds `PlatformSettings`, so a provider written beside
# it probably mirrors that; the rest are here so a different arrangement is found
# rather than reported as a missing deliverable. The *factory* name is the review's
# — `ProviderSettings.from_environment` is the callable whose redirect-URI
# validation has no HTTP surface to be reached through, which is why it is
# imported at all.
MOCK_IDP_SETTINGS_MODULES = ("app.config", "app.settings", "app.main", "app")
PROVIDER_SETTINGS_NAMES = ("ProviderSettings", "IdpSettings", "OidcSettings", "Settings")
SETTINGS_FACTORY_NAME = "from_environment"

# **Not this suite's choice.** OpenID Connect Discovery 1.0 §4 fixes this path,
# and E0-16's scope spells it out: "Discovery document at
# `/.well-known/openid-configuration`". A provider serving its metadata anywhere
# else is one no conformant client can configure itself from.
DISCOVERY_PATH = "/.well-known/openid-configuration"

# How many of the identities a login form offers are walked. **This suite's
# choice**, and a bound rather than a rule: E0-16 seeds six roles plus the
# two-hat person, so a form offering more than this is a seed that has grown
# rather than a form this cannot read. Raise it if that happens.
MAX_LOGIN_VARIANTS = 24

# How many internal redirects are followed between the authorization request and
# the page that asks who is signing in. **This suite's choice.** A provider may
# reasonably send `/authorize` to `/login?...` and back; a provider that sends a
# client round more hops than this is looping.
MAX_LOGIN_HOPS = 4

# Input types that are a person typing something this test cannot know. A login
# form built out of these is drivable by a browser and not by a fixture, and the
# right answer is a named failure rather than a guess at a seeded password.
TYPED_INPUT_TYPES = frozenset({"text", "password", "email", "tel", "url", "number", "search"})

# Words that name the field a login form picks a person with, consulted only when
# the form offers more than one set of choices and the ambiguity has to be
# resolved. Read by `MockIdentityProvider.identity_field` below.
IDENTITY_FIELD_HINTS = ("user", "login", "identity", "account", "sub", "person", "email", "name")

# The claims that carry a *person* rather than a *role*, from OIDC Core 1.0 §2
# and §5.1, plus the registered JWT claims. Values under these keys are skipped
# when scanning a session for roles, because a dean called "Dean" is a name and
# not a grant — and a scanner that could not tell the two apart would report a
# reporting role on the Care session that §2 exists to keep clear of one.
PERSONAL_CLAIM_NAMES = frozenset(
    {
        "address",
        "at_hash",
        "aud",
        "azp",
        "birthdate",
        "c_hash",
        "email",
        "email_verified",
        "family_name",
        "gender",
        "given_name",
        "iss",
        "jti",
        "locale",
        "middle_name",
        "name",
        "nickname",
        "nonce",
        "phone_number",
        "phone_number_verified",
        "picture",
        "preferred_username",
        "profile",
        "sub",
        "updated_at",
        "website",
        "zoneinfo",
    }
)

# How a role may be spelled in a session, built from E0-09's `ROLE_ALIASES`
# rather than beside it, so that "how this project spells LEAD_FACULTY" stays one
# fact (`docs/MISTAKES.md` entry 13). Two additions, both for this door only: a
# provider standing in for an institutional IdP may spell the two launch-only
# roles in the LIS vocabulary a platform uses, where a student is a `Learner`.
# They are added rather than pushed back into `ROLE_ALIASES` because that mapping
# is matched against database enum labels, which have no `Learner`.
ROLE_CLAIM_ALIASES = {
    **ROLE_ALIASES,
    "INSTRUCTOR": ("INSTRUCTOR", "TEACHER"),
    "STUDENT": ("STUDENT", "LEARNER"),
}

# Which roles a door may hand out is a ticket's expectation rather than a
# property of the driver, so the three lists E0-16's criteria are written in —
# the six web-login roles, the two launch-only ones, and §2.1's reporting chain —
# live in `tests/integration/test_mock_idp_web_login.py` beside the assertions
# that read them, and are transcribed there from the ticket.

# Fragments that would make a claim name a *purview* — a set of org nodes, or a
# supervision edge — rather than an identity. §2.1's containment levels, plus the
# two words the graph is described in. `scope` on its own is deliberately absent:
# it is an OAuth 2.0 term with a legitimate meaning in a token response, and
# matching it would fail a conformant provider for saying `openid`.
PURVIEW_CLAIM_FRAGMENTS = (
    "purview",
    "college",
    "department",
    "prefix",
    "course",
    "section",
    "scope_node",
    "reports_to",
    "supervis",
)


def pkce_pair() -> tuple[str, str]:
    """One PKCE verifier and its S256 challenge, per RFC 7636 §4.1 and §4.2.

    `secrets.token_urlsafe(48)` produces 64 characters from the unreserved set,
    inside the 43-to-128 the specification allows. The challenge is the
    base64url of the SHA-256 of the *ASCII* verifier with the padding stripped,
    which is the whole of what a provider recomputes.
    """
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def role_token(value: str) -> str:
    """One string from a session, normalised to the shape a role name has.

    A role arrives as a bare word (`chair`), as a phrase (`VP Academics`), or as
    a vocabulary URI (`http://purl.imsglobal.org/vocab/lis/v2/membership#Learner`
    is how a platform spells one). All three are the same claim about a person,
    so the last path, fragment or scheme segment is taken and everything that is
    not a letter or a digit becomes an underscore.
    """
    tail = re.split(r"[/#:]", value.strip())[-1]
    return re.sub(r"[^A-Za-z0-9]+", "_", tail).strip("_").upper()


def role_strings(node: Any) -> Iterator[str]:
    """Every string in a session that could be stating a role.

    Walks the whole claim tree rather than one agreed claim name, because E0-16
    spells no claim: a provider may put roles under `roles`, under a namespaced
    URI, or inside a nested object, and a scan that knew the name would report
    "no instructor role here" about a claim it never looked at.

    Values under the personal claims above are skipped — a name, an email address
    and a preferred username describe the person, not what they may do.
    """
    if isinstance(node, Mapping):
        for name, value in node.items():
            if str(name).lower() in PERSONAL_CLAIM_NAMES:
                continue
            yield from role_strings(value)
    elif isinstance(node, list | tuple):
        for item in node:
            yield from role_strings(item)
    elif isinstance(node, str):
        yield node


def roles_in(claims: Any) -> set[str]:
    """Every role this project recognises, stated anywhere in `claims`.

    Matching is exact against the normalised token rather than by substring, for
    the reason `ROLE_ALIASES` gives: `DEAN` is a substring of `ASSISTANT_DEAN`,
    and a fuzzy match would make every assistant dean a dean. Its own control is
    `tests/integration/test_mock_idp_web_login.py`, which runs it against the
    values it is claimed to catch *and* the values it is claimed to let past —
    `docs/MISTAKES.md` entry 3, since every assertion about a role that is
    *absent* is satisfied by a scanner that finds nothing at all.
    """
    tokens = {role_token(value) for value in role_strings(claims)}
    return {
        role
        for role, aliases in ROLE_CLAIM_ALIASES.items()
        if tokens & {role_token(alias) for alias in aliases}
    }


def purview_claim_names(node: Any) -> set[str]:
    """Every claim name in a session that names a purview rather than a person."""
    found: set[str] = set()
    if isinstance(node, Mapping):
        for name, value in node.items():
            lowered = str(name).lower()
            if any(fragment in lowered for fragment in PURVIEW_CLAIM_FRAGMENTS):
                found.add(str(name))
            found |= purview_claim_names(value)
    elif isinstance(node, list | tuple):
        for item in node:
            found |= purview_claim_names(item)
    return found


class LoginAttempt(NamedTuple):
    """One trip through the provider's login form, refused or not.

    `code` is `None` when the provider did not issue one, whatever it did
    instead — that is the shape criterion 7 needs, because "an instructor cannot
    obtain a session here" is a claim about what did *not* come back and the
    status alone does not say it.
    """

    submission: dict[str, str]
    request: dict[str, str]
    verifier: str
    response: Any
    location: str | None
    code: str | None
    state: str | None

    @property
    def refused(self) -> bool:
        return self.code is None


class WebLogin(NamedTuple):
    """One completed authorization code flow: the session a web login produces."""

    submission: dict[str, str]
    request: dict[str, str]
    verifier: str
    code: str
    state: str | None
    tokens: dict[str, Any]
    id_token: str
    signature: JsonWebSignature

    @property
    def claims(self) -> dict[str, Any]:
        return self.signature.claims

    @property
    def header(self) -> dict[str, Any]:
        return self.signature.header


class AuthorizationAttempt(NamedTuple):
    """An authorization request, taken as far as the page that asks who you are."""

    request: dict[str, str]
    verifier: str
    page_url: str | None
    form: dict[str, Any] | None
    response: Any


def import_mock_idp_application(values: Mapping[str, str]) -> Any:
    """The mock provider's ASGI application. See `import_mock_application` above."""
    return import_mock_application(
        MOCK_IDP_DIR,
        MOCK_IDP_MODULES,
        values,
        absent_directory=(
            f"{MOCK_IDP_DIR} does not exist. E0-16's scope is a `mock-idp/` FastAPI application "
            "with a Dockerfile, added to Compose as `mock-idp` (SPEC §7.2 lists the service and "
            "§9.2 says what it is for: an in-repo OIDC provider so that the second entry door is "
            "exercised in every run)."
        ),
        nothing_found=(
            "Nothing under `mock-idp/app/` exposes a FastAPI application. Looked for a "
            f"module-level instance, then a factory named one of {list(APPLICATION_FACTORY_NAMES)}"
            f", in {list(MOCK_IDP_MODULES)}; imported {{imported}}. If it is reachable under a "
            "spelling none of those covers, that is a defect in `MockIdentityProvider` in "
            "tests/conftest.py rather than in the mock, and MOCK_IDP_MODULES there is the one "
            "line that changes."
        ),
    )


class MockIdentityProvider:
    """E0-16's provider, driven the way a client drives one rather than by name.

    **Nothing about the provider's URLs is written down except the one the
    standard fixes**, so nothing here is hardcoded that the protocol can supply
    instead:

      - The discovery document is fetched from `/.well-known/openid-configuration`,
        which OIDC Discovery 1.0 §4 fixes and E0-16's scope repeats.
      - Every endpoint — authorization, token, JWKS — is read out of that
        document, because that is how a client finds them. A provider that serves
        them at sensible paths and advertises none has built something no
        conformant client can configure itself from, and the right outcome is a
        red rather than a fixture that goes looking.
      - The identities come out of the login form, the way a browser meets them.

    **The one thing E0-16 does not say is how a client learns the seeded
    `client_id` and redirect URI.** A registered client is what an authorization
    request names, so a test cannot start a flow without one. `registration()`
    looks in the three places a reasonable implementation would put it and then
    fails by name; it does not invent one.

    **What this does not do is decide anything.** Where the ticket leaves a name
    open, a test fails saying so rather than passing against an interface nobody
    asked for.
    """

    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        from fastapi.testclient import TestClient

        self.values = dict(values or {})
        self.application = import_mock_idp_application(self.values)
        self.client = TestClient(self.application, follow_redirects=False)
        # Entered so the application's lifespan runs: a provider that generates
        # its signing key on startup has not generated one until it does.
        self.client.__enter__()
        self._discovery: dict[str, Any] | None = None
        self._registration: dict[str, str] | None = None
        self._registration_document: dict[str, Any] | None = None
        self._registration_source: str | None = None

    def close(self) -> None:
        self.client.__exit__(None, None, None)

    # -- what the application serves ----------------------------------------

    def paths(self, method: str = "GET") -> list[str]:
        """Every declared path that answers `method` and takes no path parameter."""
        return declared_paths(self.application, method)

    def discovery(self) -> dict[str, Any]:
        """The provider's metadata document, fetched from the standard path."""
        if self._discovery is None:
            response = self.client.get(DISCOVERY_PATH)
            assert response.status_code == 200, (
                f"`GET {DISCOVERY_PATH}` answered {response.status_code} rather than 200. E0-16's "
                "scope puts the discovery document there and OIDC Discovery 1.0 §4 fixes the "
                "path; a client that cannot fetch it cannot find any other endpoint. Body begins "
                f"{response.text[:200]!r}."
            )
            try:
                document = response.json()
            except ValueError as failure:
                pytest.fail(
                    f"`GET {DISCOVERY_PATH}` served something that is not JSON ({failure}). "
                    "Provider metadata is a JSON object."
                )
            assert isinstance(document, dict) and document, (
                f"`GET {DISCOVERY_PATH}` served {document!r}, which is not a provider metadata "
                "document. OIDC Discovery 1.0 §3 makes it a non-empty JSON object."
            )
            self._discovery = document
        return self._discovery

    def metadata(self, name: str, purpose: str) -> str:
        """One string member of the discovery document, or a failure naming it."""
        document = self.discovery()
        value = document.get(name)
        if not isinstance(value, str) or not value:
            pytest.fail(
                f"The discovery document advertises no `{name}` (it carries {sorted(document)}). "
                f"That member is how a client learns {purpose}, so without it there is nothing to "
                "call — whatever the provider serves and at whatever path."
            )
        return value

    def endpoint_path(self, name: str, purpose: str) -> str:
        """One advertised endpoint, as this in-process client can request it."""
        return local_target(self.metadata(name, purpose))

    def jwks(self) -> dict[str, Any]:
        """The published key set, fetched from the advertised `jwks_uri`."""
        path = self.endpoint_path("jwks_uri", "where the provider publishes its signing keys")
        response = self.client.get(path)
        assert response.status_code == 200, (
            f"The JWKS endpoint `{path}` answered {response.status_code} rather than 200. E0-16's "
            "third criterion is an `id_token` that verifies against the served JWKS, and a key "
            "set nobody can fetch verifies nothing."
        )
        document = response.json()
        assert isinstance(document, dict), (
            f"The JWKS endpoint `{path}` served {document!r}, which is not a JWK Set. RFC 7517 "
            "makes a key set a JSON object with a `keys` member."
        )
        return document

    def published_keys(self) -> list[dict[str, Any]]:
        keys = self.jwks().get("keys")
        return [key for key in keys if isinstance(key, dict)] if isinstance(keys, list) else []

    def verifies(self, token: Any) -> dict[str, Any] | None:
        """The published key that verifies `token`, or `None` if none does.

        The arithmetic is `verify_rs256` above — written out of `pow` and
        `hashlib` because nothing in the locked dependency set verifies a JWS, and
        controlled by its own tests rather than trusted.
        """
        signature = token if isinstance(token, JsonWebSignature) else split_jws(str(token))
        return verifying_key(signature, self.jwks())

    # -- the seeded client --------------------------------------------------

    def registration(self) -> dict[str, str]:
        """The client an authorization request may name, and where it may come back to.

        Looked for in three places, most published first, because E0-16 names
        none and a fixture that pinned one would decide it:

          1. A JSON document the provider serves carrying a `client_id`. The mock
             platform publishes its registration exactly this way
             ([ADR 0036](../../docs/adr/0036-the-mock-platform-publishes-its-registration-as-a-document.md)),
             so a provider written beside it may too.
          2. A form on one of its own pages carrying `client_id` as a field — a
             demo page that starts a flow announces the client the same way the
             launch page announces the platform.
          3. The `mock-idp` service's Compose environment, which is where the mock
             platform's five addresses are written as literals
             ([ADR 0037](../../docs/adr/0037-the-mock-platform-is-configured-by-compose-literals.md)).

        A failure here is a real gap rather than a fixture problem: E1's login
        work and E0-18's Playwright path both have to learn the same two values,
        and if nothing publishes them then every client learns them by reading the
        source.
        """
        if self._registration is None:
            found = (
                self.registration_in_a_document()
                or self.registration_in_a_form()
                or self.registration_in_compose()
            )
            if found is None:
                pytest.fail(
                    "Nothing tells a client which `client_id` this provider will accept or which "
                    "redirect URI it will return to, so no authorization request can be built. "
                    f"Looked for a JSON document carrying `client_id` among {self.paths('GET')}, "
                    "for a form field of that name on those pages, and for a `CLIENT_ID` entry in "
                    f"the `{MOCK_IDP_SERVICE}` service's Compose environment. E0-16 spells none "
                    "of the three, and a fixture that guessed would be deciding it — publish the "
                    "registration the way the mock platform does (ADR 0036), or say in the "
                    "ticket where a client reads it."
                )
            self._registration = found
        return self._registration

    @staticmethod
    def client_registration_in(node: Any) -> dict[str, str] | None:
        """The first mapping anywhere in `node` that names a client and a redirect URI."""
        if isinstance(node, Mapping):
            client = node.get("client_id")
            redirect = node.get("redirect_uri")
            if not isinstance(redirect, str):
                listed = node.get("redirect_uris")
                redirect = listed[0] if isinstance(listed, list) and listed else None
            if isinstance(client, str) and client and isinstance(redirect, str) and redirect:
                return {"client_id": client, "redirect_uri": redirect}
            for value in node.values():
                found = MockIdentityProvider.client_registration_in(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = MockIdentityProvider.client_registration_in(item)
                if found is not None:
                    return found
        return None

    def registration_in_a_document(self) -> dict[str, str] | None:
        """A JSON document the provider serves that names its seeded client.

        The document itself is kept, not only the two values pulled out of it:
        [ADR 0058](../../docs/adr/0058-the-mock-provider-publishes-its-registration-and-its-seed.md)
        makes `launch_only_roles`, `lms_user_id` and `roles_claim` contract
        members of it, which is how a test names one seeded person rather than
        asserting over whichever set of people happens to be there.
        """
        for path in self.paths("GET"):
            if path == DISCOVERY_PATH:
                continue
            response = self.client.get(path)
            if response.status_code != 200:
                continue
            if "json" not in response.headers.get("content-type", "").lower():
                continue
            try:
                document = response.json()
            except ValueError:
                continue
            found = self.client_registration_in(document)
            if found is not None:
                self._registration_document = document if isinstance(document, dict) else None
                self._registration_source = f"the JSON document at `{path}`"
                return found
        return None

    def registration_in_a_form(self) -> dict[str, str] | None:
        """A form on one of the provider's own pages that names its seeded client."""
        for path in self.paths("GET"):
            response = self.client.get(path)
            if response.status_code != 200:
                continue
            if "html" not in response.headers.get("content-type", "").lower():
                continue
            for form in forms_in(response.text):
                found = self.client_registration_in(form["fields"])
                if found is not None:
                    self._registration_source = f"a form on the page at `{path}`"
                    return found
        return None

    @staticmethod
    def registration_in_compose() -> dict[str, str] | None:
        """The client and redirect URI written as Compose literals on the service."""
        services = load_compose(BASE_COMPOSE_PATH).get("services") or {}
        service = services.get(MOCK_IDP_SERVICE)
        block = service.get("environment") if isinstance(service, dict) else None
        if not isinstance(block, dict):
            return None
        values = {str(name).upper(): str(value) for name, value in block.items() if value}
        literal = {name: value for name, value in values.items() if "$" not in value}
        client = next((v for k, v in literal.items() if k.endswith("CLIENT_ID")), None)
        redirect = next((v for k, v in literal.items() if "REDIRECT" in k), None)
        if client and redirect:
            return {"client_id": client, "redirect_uri": redirect}
        return None

    # -- the seeded people, out of the published document (ADR 0058) ---------

    def registration_document(self) -> dict[str, Any]:
        """The whole published registration document, or a failure saying there is none."""
        self.registration()
        if self._registration_document is None:
            pytest.fail(
                "This provider publishes no registration *document*, so the seeded people cannot "
                f"be read off it — the client registration was found in {self._registration_source}"
                ". ADR 0058 makes that document the contract between the two mocks: `roles`, "
                "`launch_only_roles`, `lms_user_id` and `roles_claim` are how E0-18 finds the same "
                "person on both doors, and how a test names one seeded person instead of asserting "
                "over whoever happens to be seeded."
            )
        return self._registration_document

    @staticmethod
    def mappings_carrying(node: Any, member: str) -> list[dict[str, Any]]:
        """Every mapping anywhere in `node` that carries `member` as a key.

        The document's shape below the contract members is not written down, so
        the people are found by what a person *has* — a `roles` list — rather than
        by the name of the array holding them. That keeps this from pinning a key
        ADR 0058 does not fix.
        """
        found: list[dict[str, Any]] = []
        if isinstance(node, Mapping):
            if member in node:
                found.append(dict(node))
            for value in node.values():
                found.extend(MockIdentityProvider.mappings_carrying(value, member))
        elif isinstance(node, list):
            for item in node:
                found.extend(MockIdentityProvider.mappings_carrying(item, member))
        return found

    @staticmethod
    def first_member(node: Any, member: str) -> Any:
        """The first value of `member` found anywhere in `node`, or `None`."""
        if isinstance(node, Mapping):
            if member in node:
                return node[member]
            for value in node.values():
                found = MockIdentityProvider.first_member(value, member)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = MockIdentityProvider.first_member(item, member)
                if found is not None:
                    return found
        return None

    def published_users(self) -> list[dict[str, Any]]:
        """Every seeded person the registration document publishes."""
        found = self.mappings_carrying(self.registration_document(), "roles")
        assert found, (
            "The registration document publishes nobody — no mapping in it carries a `roles` "
            f"member (it carries {sorted(self.registration_document())}). ADR 0058 makes the "
            "seeded people part of that document, and every assertion about who is seeded reads "
            "them from there."
        )
        return found

    def roles_claim_name(self) -> str:
        """The claim a session states its roles in, as the document declares it."""
        declared = self.first_member(self.registration_document(), "roles_claim")
        if not isinstance(declared, str) or not declared:
            pytest.fail(
                "The registration document declares no `roles_claim` (it carries "
                f"{sorted(self.registration_document())}). ADR 0058 makes it a contract member "
                "because it is how a client knows which claim to read a session's roles out of — "
                "without it, every reader guesses, and this suite's own scan is a guess that "
                "happens to work."
            )
        return declared

    def identity_of(self, user: Mapping[str, Any], attempt: AuthorizationAttempt) -> dict[str, str]:
        """The login-form submission that signs in as `user`.

        Matched on the form's *choice* values only, never on its hidden fields:
        the hidden fields carry the client id, the redirect URI and the request's
        own state, and a published person who happened to share one of those
        strings would otherwise match the first submission in the list — which is
        the submission this would have returned anyway, so the test would pass
        having signed in as somebody else.
        """
        form = self.require_login_form(attempt)
        wanted = {value for value in user.values() if isinstance(value, str) and value}
        offered: list[dict[str, str]] = []
        for submission in self.offered_identities(attempt):
            chosen = {name: str(submission[name]) for name in form["choices"] if name in submission}
            offered.append(chosen)
            if wanted & set(chosen.values()):
                return submission
        pytest.fail(
            f"The login form offers no identity matching the published user {user!r} — it offers "
            f"{offered}. A person the registration document publishes and the login form cannot "
            "sign in is a person E0-18 would find on one door and not on the other."
        )

    # -- the authorization code flow ----------------------------------------

    def authorization_request(
        self, *, omitting: Sequence[str] = (), **overrides: str
    ) -> tuple[dict[str, str], str]:
        """A conformant authorization request with PKCE, and the verifier behind it.

        Every value is one OIDC Core 1.0 §3.1.2.1 and RFC 7636 require of a code
        flow with PKCE, so nothing here is a preference. `omitting` sends a
        request with those parameters absent, which an override cannot express —
        and "absent" is the case that matters for a downgrade.
        """
        registration = self.registration()
        verifier, challenge = pkce_pair()
        request = {
            "response_type": "code",
            "scope": "openid",
            "client_id": registration["client_id"],
            "redirect_uri": registration["redirect_uri"],
            "state": secrets.token_urlsafe(24),
            "nonce": secrets.token_urlsafe(24),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        request.update(overrides)
        for name in omitting:
            request.pop(name, None)
        return request, verifier

    def begin(self, *, omitting: Sequence[str] = (), **overrides: str) -> AuthorizationAttempt:
        """Send an authorization request and follow it to the page that asks who you are."""
        request, verifier = self.authorization_request(omitting=omitting, **overrides)
        return self.begin_from(list(request.items()), verifier)

    def begin_from(
        self, parameters: Sequence[tuple[str, str]], verifier: str
    ) -> AuthorizationAttempt:
        """The same, from a parameter *list* rather than a mapping.

        A mapping cannot express a query string that carries one name twice, and
        `client_id=evil&client_id=real` is a request a real client never sends and
        an attacker does. Which of the two a server reads is undefined by RFC 6749
        and decided by the framework underneath it, so a provider that takes the
        last wins for one ordering and loses for the other — which means a test
        written with a mapping cannot ask the question at all.
        """
        path = self.endpoint_path(
            "authorization_endpoint", "where an authorization request is sent"
        )
        response = self.client.get(path, params=list(parameters))
        request = dict(parameters)
        page_url, form, final = self.follow_to_a_login_form(path, response, request)
        return AuthorizationAttempt(
            request=request, verifier=verifier, page_url=page_url, form=form, response=final
        )

    def follow_to_a_login_form(
        self, url: str, response: Any, request: Mapping[str, str]
    ) -> tuple[str | None, dict[str, Any] | None, Any]:
        """Follow the provider's own redirects until a page carrying a form arrives.

        A redirect to the *client's* redirect URI is not followed and ends the
        walk: that is the authorization response, and reaching it without being
        asked anything is a provider that issued a session to whoever asked.
        """
        current, hops = url, 0
        while hops < MAX_LOGIN_HOPS:
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location") or ""
                if not location or location.startswith(str(request.get("redirect_uri", "\0"))):
                    return None, None, response
                current = local_target(urljoin(f"http://testserver{current}", location))
                response = self.client.get(current)
                hops += 1
                continue
            if (
                response.status_code == 200
                and "html" in response.headers.get("content-type", "").lower()
            ):
                forms = forms_in(response.text)
                posting = [form for form in forms if form["method"] == "post"]
                chosen = (posting or forms or [None])[0]
                return current, chosen, response
            return current, None, response
        return current, None, response

    def require_login_form(self, attempt: AuthorizationAttempt) -> dict[str, Any]:
        """The login form, or a failure saying what arrived instead."""
        if attempt.form is None:
            pytest.fail(
                "The authorization request did not reach a page carrying a form, so there is no "
                f"login to drive. The last response was {attempt.response.status_code} for "
                f"`{attempt.page_url}`; the provider serves {self.paths('GET')}. E0-16's scope "
                "asks for 'a login form simple enough for a Playwright test to drive without "
                "brittle selectors', and a provider that answers an authorization request without "
                "asking who is signing in has issued a session to whoever asked."
            )
        typed = [
            control
            for control in attempt.form["controls"]
            if control.get("tag") == "input"
            and control.get("type", "text").lower() in TYPED_INPUT_TYPES
            and not control.get("value")
        ]
        if typed and not attempt.form["choices"]:
            pytest.fail(
                "The login form asks for values this test cannot know — it carries "
                f"{[control.get('name') for control in typed]} and offers no choice of seeded "
                "identity. E0-16 seeds the identities and spells no credential for any of them, "
                "so either the form offers them (a `<select>`, radio buttons or named submit "
                "buttons are all read here) or the ticket has to say what a test signs in with."
            )
        return attempt.form

    def identify(
        self, attempt: AuthorizationAttempt, identity: Mapping[str, str] | None
    ) -> dict[str, str]:
        """One submission for `attempt`'s form, signing in as `identity`.

        The chosen values are the ones the form offers a *choice* of — a
        `<select>`, radio buttons or named submit buttons — and everything else
        comes from this attempt's own form. That is what keeps a caller able to
        say "sign in as this one" without carrying another flow's hidden state
        along with it.
        """
        offered = self.offered_identities(attempt)
        if identity is None:
            return offered[0]
        form = self.require_login_form(attempt)
        wanted = {name: value for name, value in identity.items() if name in form["choices"]}
        for submission in offered:
            if all(submission.get(name) == value for name, value in wanted.items()):
                return submission
        return {**offered[0], **wanted}

    def offered_identities(self, attempt: AuthorizationAttempt) -> list[dict[str, str]]:
        """Every submission the login form could send, one per seeded identity."""
        form = self.require_login_form(attempt)
        submissions = form_submissions(form)[:MAX_LOGIN_VARIANTS]
        assert submissions, (
            "The login form offers nothing to submit, so no identity can sign in. E0-16 seeds six "
            "web-login roles plus the person holding Care and an instructor assignment."
        )
        return submissions

    @staticmethod
    def identity_field(form: Mapping[str, Any]) -> str:
        """The name of the field a login form picks a person with.

        A login form offering seeded identities offers them under one name — the
        `<select>`, the radio group, the named submit buttons. Where a form offers
        more than one set of choices, the one whose name reads as a person is
        taken, and an ambiguity this cannot resolve stops rather than guesses:
        choosing would let a test submit the wrong field and pass for a reason
        unrelated to what it asserts.

        On the driver rather than in a test module because two modules ask it —
        the refusal tests over launch-only identities, and the duplicate-parameter
        tests that send the same name in the query and the body — and two copies
        of "which field names the person" would drift (`docs/MISTAKES.md` entry
        13).
        """
        choices = sorted(name for name, options in form["choices"].items() if options)
        if len(choices) == 1:
            return choices[0]
        hinted = [
            name for name in choices if any(hint in name.lower() for hint in IDENTITY_FIELD_HINTS)
        ]
        if len(hinted) == 1:
            return hinted[0]
        pytest.fail(
            f"The login form offers choices under {choices}, and this cannot tell which one names "
            "the person signing in. Submitting the wrong field would make a refusal a fact about "
            "something else. `IDENTITY_FIELD_HINTS` in tests/conftest.py is the one line that "
            "changes."
        )

    def submit_login(
        self,
        attempt: AuthorizationAttempt,
        submission: Mapping[str, str],
        *,
        query: Mapping[str, str] | None = None,
    ) -> LoginAttempt:
        """Post one identity to the login form and read what came back.

        Asserts nothing about the outcome. Criterion 7 needs a refusal to be
        readable as a refusal rather than as a fixture failure, so the caller
        decides whether a missing code is the answer it wanted.

        `query` puts parameters on the form's action URL *as well as* in the body,
        which is the only way to ask whether a name arriving from two sources is
        seen as one duplicate. A browser never sends that request; something
        pretending to be a browser does.
        """
        form = self.require_login_form(attempt)
        action = urljoin(f"http://testserver{attempt.page_url}", form["action"] or "")
        target = url_with_query(local_target(action), query or {})
        values = dict(submission)
        if form["method"] == "post":
            response = self.client.post(target, data=values)
        else:
            response = self.client.get(target, params=values)
        location, code, state = self.read_authorization_response(response)
        return LoginAttempt(
            submission=values,
            request=dict(attempt.request),
            verifier=attempt.verifier,
            response=response,
            location=location,
            code=code,
            state=state,
        )

    @staticmethod
    def read_authorization_response(response: Any) -> tuple[str | None, str | None, str | None]:
        """The `code` and `state` the provider sent back, wherever it put them.

        A redirect carrying them in the query is the code flow's default response
        mode; a self-submitting form is `form_post`, which is legal and which the
        LTI side of this repository already uses. Which one E0-16 chose is not
        something this file decides, so both are read.
        """
        location = response.headers.get("location")
        if location:
            split = urlsplit(location)
            for blob in (split.query, split.fragment):
                pairs = parse_qs(blob)
                if "code" in pairs:
                    return location, pairs["code"][0], (pairs.get("state") or [None])[0]
            return location, None, None
        if response.status_code == 200:
            for form in forms_in(response.text):
                if "code" in form["fields"]:
                    return (
                        form["action"] or None,
                        form["fields"]["code"],
                        form["fields"].get("state"),
                    )
        return None, None, None

    def redeem(
        self,
        code: str,
        verifier: str | None,
        *,
        omitting: Sequence[str] = (),
        **overrides: str,
    ) -> Any:
        """Exchange an authorization code at the token endpoint. Asserts nothing.

        The body is RFC 6749 §4.1.3's plus RFC 7636's `code_verifier`, form-encoded
        as those specifications require. `verifier` of `None` sends no verifier at
        all, which is the downgrade case and is not the same request as sending a
        wrong one.
        """
        return self.redeem_from(
            list(self.token_body(code, verifier, omitting=omitting, **overrides).items())
        )

    def token_body(
        self,
        code: str,
        verifier: str | None,
        *,
        omitting: Sequence[str] = (),
        **overrides: str,
    ) -> dict[str, str]:
        """What a conformant client posts to redeem `code`.

        Built here rather than inside `redeem` so that a test asking what the
        endpoint does with a *repeated* field can start from the same body a
        correct client sends and add one entry to it — one definition of the
        request, two ways of encoding it (`docs/MISTAKES.md` entry 13).
        """
        registration = self.registration()
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": registration["redirect_uri"],
            "client_id": registration["client_id"],
        }
        if verifier is not None:
            body["code_verifier"] = verifier
        body.update(overrides)
        for name in omitting:
            body.pop(name, None)
        return body

    def redeem_from(
        self,
        parameters: Sequence[tuple[str, str]],
        *,
        query: Mapping[str, str] | None = None,
    ) -> Any:
        """Post one token request as a list of fields, so a name may appear twice.

        Gathered into a mapping of name to values because that is the shape httpx
        form-encodes with `doseq`; the order of the values under one name is what
        decides the question being asked, and it survives the gathering.

        `query` puts parameters on the token endpoint's URL as well as in the
        body. RFC 6749 §3.1's rule is about the *request* rather than about one
        encoding of it, and a name arriving once from each source is the shape
        that looks like two singletons to anything checking one collection at a
        time.
        """
        fields: dict[str, list[str]] = {}
        for name, value in parameters:
            fields.setdefault(name, []).append(value)
        path = self.endpoint_path("token_endpoint", "where an authorization code is redeemed")
        return self.client.post(url_with_query(path, query or {}), data=fields)

    @staticmethod
    def body_of(response: Any) -> dict[str, Any]:
        """A token endpoint response as a mapping, or an empty one if it is not JSON."""
        try:
            document = response.json()
        except ValueError:
            return {}
        return document if isinstance(document, dict) else {}

    def refuse_an_unspecified_client_credential(self, response: Any) -> None:
        """Turn `invalid_client` into a named gap rather than a passing refusal.

        E0-16 describes no client secret, and PKCE is what a public client
        authenticates a code exchange with, so this suite redeems without one. If
        the provider requires a secret, every exchange here fails — and the two
        refusal criteria would then pass for a reason unrelated to what they
        assert, which is `docs/MISTAKES.md` entry 3 exactly. So it is named
        wherever it appears, on the successes and on the refusals alike.
        """
        if self.body_of(response).get("error") == "invalid_client":
            pytest.fail(
                f"The token endpoint answered {response.status_code} `invalid_client`, so it "
                "requires a client credential this suite does not send. E0-16 names no client "
                "secret and PKCE is what a public client proves possession with — if the seeded "
                "client is confidential, the ticket has to say so, because a refusal for this "
                "reason is indistinguishable from the code-replay and verifier-mismatch refusals "
                "two of its criteria are about."
            )

    def tokens(self, response: Any) -> dict[str, Any]:
        """The token endpoint's successful response, or a failure saying what came back."""
        self.refuse_an_unspecified_client_credential(response)
        assert response.status_code == 200, (
            f"The token endpoint answered {response.status_code} rather than 200 for a code "
            "exchange with a matching PKCE verifier. E0-16 criterion 3 is that this flow "
            f"completes end to end. Body begins {response.text[:300]!r}."
        )
        body = self.body_of(response)
        assert body, (
            f"The token endpoint answered 200 with {response.text[:200]!r}, which is not a JSON "
            "object. RFC 6749 §5.1 makes a successful token response one."
        )
        return body

    def login(
        self,
        identity: Mapping[str, str] | None = None,
        *,
        omitting: Sequence[str] = (),
        **overrides: str,
    ) -> WebLogin:
        """Drive one whole authorization code flow, from the form to the `id_token`.

        This is E0-16's third criterion done by *being* a client: an authorization
        request, a login, a code, and an exchange carrying the verifier. Nothing
        is called that a real client would not call, so a session obtained here
        and a session a browser produces are the same session.

        `identity` selects **which** seeded identity signs in, and only that: the
        hidden fields come from this call's own fresh authorization request. A
        submission carried whole from an earlier attempt would post that attempt's
        state, nonce and challenge into this one, and the session would then be
        checked against a request it did not answer — which reads as the provider
        returning the wrong nonce.
        """
        attempt = self.begin(omitting=omitting, **overrides)
        chosen = self.identify(attempt, identity)
        submitted = self.submit_login(attempt, chosen)
        assert submitted.code, (
            f"Signing in as {chosen} produced no authorization code — the provider answered "
            f"{submitted.response.status_code} and sent {submitted.location!r}. Body begins "
            f"{submitted.response.text[:200]!r}."
        )
        response = self.redeem(submitted.code, submitted.verifier)
        body = self.tokens(response)
        id_token = body.get("id_token")
        assert isinstance(id_token, str) and id_token, (
            f"The token response carries no `id_token` (it carries {sorted(body)}). OIDC Core "
            "1.0 §3.1.3.3 makes it the member that distinguishes an OpenID Connect response from "
            "a plain OAuth 2.0 one, and it is the whole of what E0-16 criterion 3 produces."
        )
        return WebLogin(
            submission=submitted.submission,
            request=submitted.request,
            verifier=submitted.verifier,
            code=submitted.code,
            state=submitted.state,
            tokens=body,
            id_token=id_token,
            signature=split_jws(id_token),
        )

    def logins(self) -> list[WebLogin]:
        """One completed session per identity the login form offers."""
        attempt = self.begin()
        return [self.login(identity) for identity in self.offered_identities(attempt)]

    @staticmethod
    def roles(login: WebLogin) -> set[str]:
        """The roles one session states, by the scan `roles_in` above performs."""
        return roles_in(login.claims)


def find_mock_idp_settings_class() -> Any:
    """The provider's settings class, found rather than imported by path.

    Called inside `mock_package_resolved`, and only from the fixture below, which
    keeps that resolution open for the whole test: a settings class is used after
    it is imported, and its `from_environment` reads the environment at call time.

    Looked for by name first and by *capability* second — any class the mock
    defines that carries a `from_environment` — because E0-16 spells no module and
    no class, and a fixture that insisted on one spelling would report a rename as
    a missing deliverable.
    """
    imported: list[str] = []
    candidates: list[Any] = []
    for name in MOCK_IDP_SETTINGS_MODULES:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError as failure:
            absent = failure.name
            if absent is not None and (name == absent or name.startswith(f"{absent}.")):
                continue
            raise
        imported.append(name)
        for attribute, value in vars(module).items():
            if attribute.startswith("_") or not inspect.isclass(value):
                continue
            if getattr(value, "__module__", "").split(".")[0] != MOCK_PACKAGE:
                continue
            if not hasattr(value, SETTINGS_FACTORY_NAME):
                continue
            if attribute in PROVIDER_SETTINGS_NAMES:
                return value
            candidates.append(value)
    if candidates:
        return candidates[0]
    pytest.fail(
        f"Nothing under `mock-idp/app/` defines a class with a `{SETTINGS_FACTORY_NAME}` — looked "
        f"in {list(MOCK_IDP_SETTINGS_MODULES)}, imported {imported or 'nothing'}. That callable is "
        "where the redirect URI is validated, and validation with no HTTP surface can only be "
        "reached by importing it. If it is there under a spelling none of "
        "`PROVIDER_SETTINGS_NAMES` reaches, that constant in tests/conftest.py is the one line "
        "that changes."
    )


@pytest.fixture
def mock_idp_settings() -> Iterator[Any]:
    """The provider's settings class, with `mock-idp/`'s `app` resolving for the test.

    The resolution is held open for the body rather than just for the import, so
    that anything `from_environment` imports when it runs still comes out of the
    mock. See `mock_package_resolved` above.
    """
    if not MOCK_IDP_DIR.is_dir():
        pytest.fail(
            f"{MOCK_IDP_DIR} does not exist, so there is no settings object to import. E0-16's "
            "scope is a `mock-idp/` FastAPI application with a Dockerfile."
        )
    with mock_package_resolved(MOCK_IDP_DIR):
        yield find_mock_idp_settings_class()


@pytest.fixture
def mock_idp_compose_environment() -> dict[str, str]:
    """The literal environment `docker-compose.yml` gives the `mock-idp` service.

    Literal values only — anything carrying a `${...}` is dropped, because this is
    handed to a settings object as if it were the container's environment and an
    uninterpolated string is not a value any container ever sees.

    Deliberately asserts nothing: an absent service yields an empty mapping and
    the test that needs it says so, which is the choice every other Compose
    reader in this file makes.
    """
    services = load_compose(BASE_COMPOSE_PATH).get("services") or {}
    service = services.get(MOCK_IDP_SERVICE)
    block = service.get("environment") if isinstance(service, dict) else None
    if not isinstance(block, dict):
        return {}
    return {
        str(name): str(value)
        for name, value in block.items()
        if value is not None and "$" not in str(value)
    }


@pytest.fixture
def mock_idp_dir() -> Path:
    """Where the mock provider must live (SPEC §13). Asserted by the test, not here."""
    return MOCK_IDP_DIR


@pytest.fixture
def mock_idp_service() -> str:
    """The Compose service name SPEC §7.2 gives the mock provider."""
    return MOCK_IDP_SERVICE


@pytest.fixture
def discovery_path() -> str:
    """The path OIDC Discovery 1.0 §4 fixes, for the test that reasons about it.

    Handed over rather than transcribed a second time, so that the path the
    driver fetches and the path a test says a client would build cannot end up
    being two different strings.
    """
    return DISCOVERY_PATH


@pytest.fixture
def claims_in_token() -> Callable[[str], dict[str, Any]]:
    """Read the claims out of a bare `id_token`, for a test holding one raw.

    `WebLogin.claims` covers every flow that completed; this is for the tests that
    have a token endpoint's *response* in hand and need to say what a session the
    provider should never have issued was carrying. Same splitter either way.
    """
    return lambda token: split_jws(str(token)).claims


@pytest.fixture
def padded() -> Callable[[str], str]:
    """Wrap a value in whitespace that a `.strip()` would remove.

    One helper rather than a literal at each call site, because the review round
    that added it found one defect reaching four parameters — a value trimmed
    before the check that judges it — and a second spelling of "padded" would be
    a second definition of the thing under test (`docs/MISTAKES.md` entry 13).

    A leading space and a trailing newline. Neither is exotic: `base64.encodebytes`
    ends every line with the second, which is how the defect arrived.
    """
    return lambda value: f" {value}\n"


@pytest.fixture
def mock_idps() -> Iterator[Callable[..., MockIdentityProvider]]:
    """Start one or more independent mock providers, and shut them all down after.

    A factory rather than a single instance, for the reason `mock_platforms` is
    one: E0-16's last criterion is that keys are generated at startup, and a
    second start generating a second key is not observable from one instance.
    """
    started: list[MockIdentityProvider] = []

    def start(values: Mapping[str, str] | None = None) -> MockIdentityProvider:
        provider = MockIdentityProvider(values)
        started.append(provider)
        return provider

    try:
        yield start
    finally:
        for provider in reversed(started):
            provider.close()


@pytest.fixture
def mock_idp(mock_idps: Callable[..., MockIdentityProvider]) -> MockIdentityProvider:
    """One mock provider, started fresh for this test. See `MockIdentityProvider`."""
    return mock_idps()


@pytest.fixture
def web_login(mock_idp: MockIdentityProvider) -> WebLogin:
    """One completed web login off the first seeded identity.

    E1's login work and E0-18's Playwright path both build on this door, so the
    interface matters the way `signed_launch`'s does: `mock_idp.login(...)` is the
    interface and this fixture is its common case.
    """
    return mock_idp.login()


@pytest.fixture
def roles_in_claims() -> Callable[[Any], set[str]]:
    """Hand `roles_in` to the test that checks the scanner itself.

    The provider reads a session's roles with this same function, so the control
    and the thing it controls cannot end up disagreeing about what counts as a
    role — which is the whole value of the control (`docs/MISTAKES.md` entry 3:
    run the matcher against the text you claim it catches *and* the text you
    claim it allows).
    """
    return roles_in


@pytest.fixture
def purview_claims_in() -> Callable[[Any], set[str]]:
    """Hand `purview_claim_names` to the test that checks that scanner too."""
    return purview_claim_names
