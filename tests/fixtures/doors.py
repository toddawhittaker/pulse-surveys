"""E0-18 PR 1 — the tool's own two doors, built here and driven in process.

The first group here that drives **this project's own** application rather than a
mock: `tool_doors` builds `app.main.create_app()` against the container database
with the door settings a test chooses, and hands back a `TestClient` whose
`app.state.http` reaches the two mocks in process instead of the network. That
seam is the ticket's design rather than a fixture's convenience — every
server-side fetch a door makes (a platform's JWKS, the provider's token endpoint)
goes through one client, so a test can route it and nothing else has to be
intercepted. `seed_constant` sits beside it and exists for one assertion: the two
mock seeds name one human, and the constant that says so can only be read by
importing a module out of each mock, which the two packages both being called
`app` makes a one-at-a-time affair.
"""

import base64
import importlib
import json
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import pytest

from fixtures.app_imports import mock_package_resolved
from fixtures.database import DatabaseUnderTest, application_environment
from fixtures.lti_platform import MOCK_PACKAGE, split_jws

# ---------------------------------------------------------------------------
# E0-18 PR 1 — the tool's own two doors, built here and driven in process.
# ---------------------------------------------------------------------------

# Where the tool says it lives while these tests run. **This suite's choice**, and
# deliberately not `localhost`: `PUBLIC_BASE_URL` is what `/lti/launch` and
# `/auth/oidc/callback` are derived from, and both mocks compare the address they
# are handed against the one they were configured with, so a value that could also
# be arrived at by accident would let a hardcoded URL pass. RFC 2606 reserves
# `.invalid`, so this can never resolve if it escapes a fixture.
TOOL_PUBLIC_BASE_URL = "http://pulse-tool.invalid"

# The four routes E0-18 adds, spelled by the ticket ("The four routes, and what
# each one does") and by the mocks' own defaults — `mock-lms/app/config.py` posts
# to `/lti/login` and names `/lti/launch` as the target link URI, and
# `mock-idp/app/config.py` returns to `/auth/oidc/callback`. Not this file's
# choice in any part.
TOOL_LTI_LOGIN_PATH = "/lti/login"
TOOL_LTI_LAUNCH_PATH = "/lti/launch"
TOOL_OIDC_LOGIN_PATH = "/auth/oidc/login"
TOOL_OIDC_CALLBACK_PATH = "/auth/oidc/callback"

# The `data-testid` each landing page carries, one per view SPEC §2 gives a door
# to. E0-18: "Give each a `data-testid` the specs address, mirroring the mock IdP's
# convention". PR 2's Playwright specs address the same five, so they are written
# once here rather than once per suite (`docs/MISTAKES.md` entry 13).
LANDING_TESTIDS = (
    "pulse-landing-student",
    "pulse-landing-instructor",
    "pulse-landing-leadership",
    "pulse-landing-care",
    "pulse-landing-admin",
)

# The settings E0-18 adds, under the names its "Configuration: one public base URL,
# two horizons" section describes them by. **These spellings are this suite's
# choice** — the ticket names each value and none of the variables — so a
# deliberate rename is these seven lines and nothing else.
PUBLIC_BASE_URL_VARIABLE = "PUBLIC_BASE_URL"
LTI_AUTHORIZATION_ENDPOINT_VARIABLE = "LTI_PLATFORM_AUTHORIZATION_ENDPOINT"
OIDC_ISSUER_VARIABLE = "OIDC_ISSUER"
OIDC_AUTHORIZATION_ENDPOINT_VARIABLE = "OIDC_AUTHORIZATION_ENDPOINT"
OIDC_TOKEN_ENDPOINT_VARIABLE = "OIDC_TOKEN_ENDPOINT"  # noqa: S105
OIDC_JWKS_URL_VARIABLE = "OIDC_JWKS_URL"
OIDC_CLIENT_ID_VARIABLE = "OIDC_CLIENT_ID"

# An identity provider that is not the mock — E0-39's repair round.
#
# That ticket refuses a `mock-idp` host or the `mock-idp-client` client id in any
# `oidc_*` setting whenever `ENVIRONMENT` is not the development one. `.env.example`
# configures exactly those values, `configured_env` lays the whole documented file
# down, and a good many tests then set `ENVIRONMENT` to `production` or `staging` to
# ask about something else entirely — a cookie's `Secure` attribute, a 404 on
# `/docs`, whether an engine hides its bound parameters. Every one of those would
# stop inside its own setup on a refusal that is not its subject, which is
# `docs/MISTAKES.md` entry 22.
#
# So a test whose subject is *not* the refusal configures a provider that is not the
# mock, and the guard it is actually about is the one that fires. Nothing here is
# reachable and nothing here is fetched: these are placeholders in a domain reserved
# for the purpose.
#
# **`tests/unit/test_oidc_provider_configuration.py` keeps its own copy of this
# idea and does not read these**, deliberately. It is the module that decides what
# "not the mock" means, and a shared constant would let an edit made for some other
# suite's convenience move the background its refusals are measured against.
DEPLOYED_IDENTITY_PROVIDER = {
    OIDC_ISSUER_VARIABLE: "https://idp.example.edu",
    OIDC_AUTHORIZATION_ENDPOINT_VARIABLE: "https://idp.example.edu/oidc/authorize",
    OIDC_TOKEN_ENDPOINT_VARIABLE: "https://idp.example.edu/oidc/token",
    OIDC_JWKS_URL_VARIABLE: "https://idp.example.edu/.well-known/jwks.json",
    OIDC_CLIENT_ID_VARIABLE: "example-client",
}

# Headers that describe one hop rather than the message, and must not be carried
# from the tool's request onto the in-process call that answers it. `host` is
# rewritten by the client below; the other three describe a body length and an
# encoding that are recomputed when the response is rebuilt.
HOP_BY_HOP_HEADERS = frozenset({"host", "content-length", "transfer-encoding", "content-encoding"})


class DoorContract(NamedTuple):
    """The names E0-18's two doors are addressed by, in one place.

    Handed to a test module rather than transcribed into it, because three suites
    address the same five landing testids — this ticket's two integration modules
    and PR 2's Playwright specs — and three copies of "what the student view is
    called" is the shape `docs/MISTAKES.md` entry 13 is about.

    `settings` maps the value the ticket describes to the environment variable this
    suite reads it under. Those spellings are **this suite's choice**; the paths and
    the testids are not — the paths are the mocks' own configured defaults and the
    ticket's route list, and the testid convention is `mock-idp/app/pages.py`'s.
    """

    public_base_url: str
    lti_login: str
    lti_launch: str
    oidc_login: str
    oidc_callback: str
    landing_testids: tuple[str, ...]
    settings: dict[str, str]


def routed_through(
    mocks: Mapping[str, Any],
    around: Callable[[Any, Callable[[], Any]], Any] | None = None,
) -> Any:
    """An `httpx.Client` whose requests reach an in-process mock instead of the network.

    `mocks` is keyed by **host**, so one client serves both doors: the tool's
    launch door fetches a platform's JWKS from `http://mock-lms:8000/...` and its
    web door redeems a code at `http://mock-idp:8000/...`, and the two-hat test
    drives both in one flow. Nothing here rewrites a URL — the settings and the
    seeded `lti_platform.jwks_url` carry the mocks' real advertised addresses, and
    the routing is by host alone, so a door that fetched from somewhere nobody
    configured fails loudly rather than being quietly served.

    `around(request, deliver)` wraps one call, and it is how the two cases that
    cannot be posed any other way are posed: a token endpoint that answers with a
    tampered `id_token`, and one that answers with a correctly signed token that
    expired an hour ago. Both are properties of what arrives at the tool, and the
    tool's own clock and verification run after `deliver()` has returned.

    `httpx.MockTransport` rather than `httpx.ASGITransport`: the latter is an
    *async* transport, so a synchronous `httpx.Client` cannot use it, and the mock
    drivers already hold a `TestClient` with its lifespan entered.
    """
    import httpx

    def deliver(request: Any) -> Any:
        host = request.url.host
        driver = mocks.get(host)
        if driver is None:
            raise RuntimeError(
                f"The tool made a server-side request to `{request.url}`, and no mock is mounted "
                f"at host {host!r} (mounted: {sorted(mocks)}). Either a door is fetching from an "
                "address nothing configured, or this test has to mount the mock that serves it."
            )
        answered = driver.client.request(
            request.method,
            str(request.url),
            content=request.content,
            headers={
                name: value
                for name, value in request.headers.items()
                if name.lower() not in HOP_BY_HOP_HEADERS
            },
        )
        return httpx.Response(
            answered.status_code,
            headers={
                name: value
                for name, value in answered.headers.items()
                if name.lower() not in HOP_BY_HOP_HEADERS
            },
            content=answered.content,
            request=request,
        )

    def handle(request: Any) -> Any:
        if around is None:
            return deliver(request)
        return around(request, lambda: deliver(request))

    return httpx.Client(transport=httpx.MockTransport(handle))


@contextmanager
def clock_wound_back(seconds: int) -> Iterator[None]:
    """Move `time.time` back for the body, and put it back afterwards.

    The only way either door's suite can obtain a **correctly signed stale token**.
    Re-encoding a token's `exp` breaks its signature, so a test built that way would
    be refused for the wrong reason and would pass against a tool that checks no
    expiry at all — `docs/MISTAKES.md` entry 3 exactly. Both mocks compute `iat`
    from `time.time()` and `exp` from `iat` plus a lifetime, so winding the clock
    back while one mints produces a token that genuinely expired.

    Scoped as narrowly as the caller makes it: on the launch door the wind lasts
    for the mint, on the web door for the tool's own call to the token endpoint,
    and the tool's clock is the real one when it judges what arrived.
    `monkeypatch` is deliberately not used — `monkeypatch.undo()` inside a test
    would also undo the environment `tool_doors` laid down on the same object.
    """
    real = time.time
    time.time = lambda: real() - seconds  # type: ignore[assignment]
    try:
        yield
    finally:
        time.time = real  # type: ignore[assignment]


def token_with_an_altered_subject(id_token: str) -> str:
    """`id_token` re-encoded from altered claims, keeping its original signature.

    Well formed in every respect except the arithmetic, which is the only thing a
    signature test is asking about. A token corrupted a character at a time is
    usually no longer JSON, so a verifier would refuse it at the decoder and a test
    would read that as a signature check (`docs/MISTAKES.md` entry 3).

    `sub` is the claim moved because moving it changes who the token is about and
    nothing else: every other check either door makes still passes over the result,
    so a refusal can only be the signature.
    """
    header, payload, signature = id_token.split(".")
    claims = dict(split_jws(id_token).claims)
    claims["sub"] = f"{claims.get('sub', '')}-tampered"
    reencoded = (
        base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8")).rstrip(b"=").decode("ascii")
    )
    assert reencoded != payload, (
        "Re-encoding the altered claims produced the original payload, so nothing was tampered "
        "with and the test using this would pass against a verifier that does nothing."
    )
    return f"{header}.{reencoded}.{signature}"


@pytest.fixture
def wind_the_clock_back() -> Callable[[int], Any]:
    """Hand `clock_wound_back` to a door suite. See it for why it exists."""
    return clock_wound_back


@pytest.fixture
def tamper_with() -> Callable[[str], str]:
    """Hand `token_with_an_altered_subject` to a door suite."""
    return token_with_an_altered_subject


@pytest.fixture
def door_contract() -> DoorContract:
    """The paths, testids and setting names E0-18's doors are addressed by."""
    return DoorContract(
        public_base_url=TOOL_PUBLIC_BASE_URL,
        lti_login=TOOL_LTI_LOGIN_PATH,
        lti_launch=TOOL_LTI_LAUNCH_PATH,
        oidc_login=TOOL_OIDC_LOGIN_PATH,
        oidc_callback=TOOL_OIDC_CALLBACK_PATH,
        landing_testids=LANDING_TESTIDS,
        settings={
            "public_base_url": PUBLIC_BASE_URL_VARIABLE,
            "lti_authorization_endpoint": LTI_AUTHORIZATION_ENDPOINT_VARIABLE,
            "oidc_issuer": OIDC_ISSUER_VARIABLE,
            "oidc_authorization_endpoint": OIDC_AUTHORIZATION_ENDPOINT_VARIABLE,
            "oidc_token_endpoint": OIDC_TOKEN_ENDPOINT_VARIABLE,
            "oidc_jwks_url": OIDC_JWKS_URL_VARIABLE,
            "oidc_client_id": OIDC_CLIENT_ID_VARIABLE,
        },
    )


@pytest.fixture
def deployed_identity_provider(
    monkeypatch: pytest.MonkeyPatch,
    configured_env: dict[str, str],
) -> dict[str, str]:
    """Configure an identity provider that is not the mock, and answer what it set.

    For a test that sets `ENVIRONMENT` to a deployment's value and is about
    something else. `configured_env` has just laid down `.env.example`, whose
    provider is the mock; E0-39 refuses that combination, so without this the test
    stops in its own setup on a rule that is not its subject.

    Requested rather than applied globally, because the combination is legal — and
    required — in development, and `tests/unit/test_config_settings.py` asserts that
    the documented file is a working configuration. Laying these over every test
    would take that away.

    Returns the mapping so that a caller which passes settings on rather than
    reading the environment — `tool_doors` below, and `open_web_door` in the web
    door suite — can hand the same five values through its own route.
    """
    for name, value in DEPLOYED_IDENTITY_PROVIDER.items():
        monkeypatch.setenv(name, value)
    return dict(DEPLOYED_IDENTITY_PROVIDER)


@pytest.fixture
def tool_doors(
    monkeypatch: pytest.MonkeyPatch,
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    migrated_database: DatabaseUnderTest,
    import_app_module: Callable[[str], ModuleType | None],
) -> Iterator[Callable[..., Any]]:
    """Build this project's application with the door settings a test chose.

    Three things it does, and each is here rather than in a test module because
    both door suites need all three.

    **The identity provider starts out as one that is not the mock** (E0-39). A
    door test that asks for a deployment's `ENVIRONMENT` is otherwise refused at
    startup over `.env.example`'s `mock-idp` addresses, which is not what any of
    them is about. The web door suite overrides all five with the in-process mock's
    real values, because reaching that provider is its subject; the launch door
    suite never names them at all.

    **The environment is the container's**, laid down by `application_environment`
    over `configured_env`'s placeholders, because the launch door resolves a
    platform out of `lti_platform` and `.env.example` names a Compose service that
    does not resolve here.

    **The application is imported fresh**, through `import_app_module`, so that a
    module which builds something out of `Settings` at import time is built out of
    the settings this test set rather than out of whatever an earlier test left in
    `sys.modules` (`docs/MISTAKES.md` entry 3).

    **`app.state.http` is replaced after the lifespan has run**, not before, so it
    holds this test's routed client whether the implementation builds its client in
    the factory or at startup. That seam is the ticket's design and not a fixture's
    convenience: every server-side fetch either door makes goes through one client,
    which is what lets a test serve the mocks in process without intercepting
    anything else.
    """
    from fastapi.testclient import TestClient

    for name, value in application_environment(migrated_database).items():
        monkeypatch.setenv(name, value)

    opened: list[Any] = []

    def open_the_tool(
        values: Mapping[str, str],
        mocks: Mapping[str, Any] | None = None,
        *,
        around: Callable[[Any, Callable[[], Any]], Any] | None = None,
    ) -> Any:
        for name, value in dict(values).items():
            monkeypatch.setenv(name, value)

        main = import_app_module("app.main")
        assert main is not None, (
            "There is no `app.main` module, so there is no application to open a door on. "
            "E0-01 ships it and `uvicorn app.main:create_app --factory` starts it."
        )
        factory = getattr(main, "create_app", None)
        assert callable(factory), (
            "`app.main` exposes no `create_app`; it exposes "
            f"{sorted(n for n in vars(main) if not n.startswith('_'))}. E0-18's routes are "
            "registered on the application that factory returns."
        )

        client = TestClient(factory(), follow_redirects=False)
        client.__enter__()
        opened.append(client)
        client.app.state.http = routed_through(mocks or {}, around)
        return client

    try:
        yield open_the_tool
    finally:
        for client in reversed(opened):
            client.__exit__(None, None, None)


# How `lti_platform` and `lti_deployment` might spell the four values a launch is
# checked against. E0-08 created both tables and named the columns in prose rather
# than in a schema this suite may pin, so — like every other module that writes to
# them — the name is discovered from a candidate list, and a deliberate rename is
# one line here.
PLATFORM_ISSUER_COLUMNS = ("issuer", "iss", "issuer_url", "platform_issuer")
PLATFORM_CLIENT_ID_COLUMNS = ("client_id", "oauth_client_id", "tool_client_id", "lti_client_id")
PLATFORM_JWKS_URL_COLUMNS = ("jwks_url", "jwks_uri", "public_jwks_url", "key_set_url", "keyset_url")
DEPLOYMENT_ID_COLUMNS = ("deployment_id", "lti_deployment_id", "platform_deployment_id")


def door_column_named(table: Any, candidates: tuple[str, ...], purpose: str) -> str:
    """The first of `candidates` that `table` carries, or a failure listing both sides."""
    for candidate in candidates:
        if candidate in table.c:
            return candidate
    present = [column.name for column in table.columns]
    pytest.fail(
        f"`{table.name}` has none of the columns {list(candidates)} — it has {present}. That "
        f"column is {purpose}, and E0-08 creates the table. The candidate list is a constant in "
        "tests/fixtures/doors.py, so a deliberate rename is a one-line change."
    )


def announced_by(offer: Any, name: str) -> str:
    """One parameter of a platform's own initiation request, or a failure naming it.

    A launch form *is* the platform announcing its issuer, client ID and deployment
    ID to a tool, so it is where a registration's values are learned — nothing is
    transcribed out of the mock's source.
    """
    value = offer.parameters.get(name)
    if not value:
        pytest.fail(
            f"The mock platform's launch form publishes no `{name}` (it publishes "
            f"{sorted(offer.parameters)}). The OIDC third-party-initiated login request is the "
            "only place a platform announces itself, and without this value there is nothing to "
            "register in `lti_platform` for the tool to find."
        )
    return value


class PlatformRegistration:
    """The `lti_platform` and `lti_deployment` rows a running mock platform matches.

    Committed, because the tool opens its own connection out of `DATABASE_URL` and
    sees nothing that has not been.

    Held as an object rather than a tuple so that a refusal test can move exactly
    one registered value out from under a launch that has already been minted.
    That is the only way to pose "wrong `aud`" and "unknown `deployment_id`" against
    a platform whose signing key nothing here holds — and it keeps those cases to
    *one* difference from the happy path, which is what makes a 4xx mean the thing
    the test names rather than any of three things at once.
    """

    def __init__(self, rows: Any, tables: dict[str, Any], offer: Any, jwks_url: str) -> None:
        for name in ("lti_platform", "lti_deployment"):
            if name not in tables:
                pytest.fail(
                    f"There is no `{name}` table (there are {sorted(tables)}). E0-08 creates it "
                    "and E0-18's launch door resolves every launch through it."
                )
        self.rows = rows
        self.platform_table = tables["lti_platform"]
        self.deployment_table = tables["lti_deployment"]
        self.issuer = announced_by(offer, "iss")
        self.client_id = announced_by(offer, "client_id")
        self.deployment_id = announced_by(offer, "lti_deployment_id")
        self.jwks_url = jwks_url

        self.issuer_column = door_column_named(
            self.platform_table,
            PLATFORM_ISSUER_COLUMNS,
            "how a tool resolves a launch's registration",
        )
        self.client_id_column = door_column_named(
            self.platform_table,
            PLATFORM_CLIENT_ID_COLUMNS,
            "what an `id_token`'s `aud` is compared against",
        )
        self.jwks_column = door_column_named(
            self.platform_table,
            PLATFORM_JWKS_URL_COLUMNS,
            "where the verifying key set is fetched from",
        )
        self.deployment_column = door_column_named(
            self.deployment_table,
            DEPLOYMENT_ID_COLUMNS,
            "what a launch's `deployment_id` claim is matched against",
        )

        chain: dict[str, Any] = {}
        self.platform_row = rows.seed(
            "lti_platform",
            chain,
            **{
                self.issuer_column: self.issuer,
                self.client_id_column: self.client_id,
                self.jwks_column: self.jwks_url,
            },
        )
        self.deployment_row = rows.seed(
            "lti_deployment", chain, **{self.deployment_column: self.deployment_id}
        )
        rows.commit()

    def rewrite(self, table: Any, row: Any, column: str, value: Any) -> None:
        """Change one registered value and commit, so the tool's next read sees it."""
        key = next(iter(table.primary_key.columns)).name
        self.rows.session.execute(
            table.update().where(table.c[key] == row[key]).values(**{column: value})
        )
        self.rows.commit()

    def move_the_registered_client_id_to(self, value: str) -> None:
        """Point the registration at a different tool, leaving everything else alone."""
        self.rewrite(self.platform_table, self.platform_row, self.client_id_column, value)

    def move_the_registered_deployment_to(self, value: str) -> None:
        """Leave the platform registered and the deployment a launch names unknown."""
        self.rewrite(self.deployment_table, self.deployment_row, self.deployment_column, value)


@pytest.fixture
def register_platform(
    committed_rows: Any, metadata_tables: dict[str, Any]
) -> Callable[[Any, str], PlatformRegistration]:
    """Register a running mock platform, so the tool's launch door can resolve it.

    Here rather than in the launch-door module because both door suites need it:
    the two-hat person's launch is driven from the web-login module, and a second
    copy of "which column holds the issuer" is the shape `docs/MISTAKES.md` entry 13
    is about.
    """

    def register(offer: Any, jwks_url: str) -> PlatformRegistration:
        return PlatformRegistration(committed_rows, metadata_tables, offer, jwks_url)

    return register


@pytest.fixture
def seed_constant() -> Callable[[Path, str], Any]:
    """One module-level value out of a mock's `app.seed`, read with the resolution closed after.

    Both mocks' packages are called `app` (SPEC §13), so the meta-path resolution
    `mock_package_resolved` installs can only be open for one of them at a time —
    which is why this reads the *value* out and lets the resolution close, rather
    than handing back a module a caller might touch afterwards. Every constant it
    is asked for is a string, so nothing is lost.

    `dotted` may walk attributes: `"INSTRUCTOR.user_id"` is the platform's
    instructor, whose identifier is a field on a seeded dataclass rather than a
    module-level name.
    """

    def read(mock_dir: Path, dotted: str) -> Any:
        if not mock_dir.is_dir():
            pytest.fail(
                f"{mock_dir} does not exist, so there is no seed module to read {dotted!r} out of."
            )
        with mock_package_resolved(mock_dir):
            module = importlib.import_module(f"{MOCK_PACKAGE}.seed")
            value: Any = module
            walked: list[str] = []
            for part in dotted.split("."):
                if not hasattr(value, part):
                    pytest.fail(
                        f"`{mock_dir.name}/app/seed.py` has no `{'.'.join([*walked, part])}`. "
                        "E0-18's cross-mock test pins the two seeds' own constants to each other, "
                        "so a rename on either side is what this is meant to catch — but a rename "
                        "of the *constant* is a one-line change in the test that names it."
                    )
                value = getattr(value, part)
                walked.append(part)
            return value

    return read
