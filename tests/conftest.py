"""Fixtures shared by the test suite.

The tests under `tests/unit/` for tickets E0-01 and E0-02 are written from those
tickets' acceptance criteria, not from the implementation. Where a criterion
needs a name the ticket does not spell — an environment variable, a JSON key —
the choice is made once, in a named constant, and marked as the test's choice so
it is cheap to change.

`.env` has two readers from E0-02 onwards: `app.config.Settings` and Compose.
The helpers below parse both sides of that, and they parse the Compose files
once, here, so that two test modules cannot end up disagreeing about what a
Compose file says.

E0-03 adds two fixtures of a different kind — `import_app_module` and
`celery_application_in`. They are here for the same reason as the parsers: the
unit tests and the integration test both need them, and two copies of a rule
about how a module is imported, or about where a Celery application is found,
could drift apart and leave the two suites checking different things.

E0-04 adds the database fixtures, at the bottom of this file: a testcontainers
Postgres on the image the stack deploys, the application role provisioned into
it, `alembic upgrade head` applied once per session, and a transaction-rollback
fixture for per-test isolation. They are the ticket's own deliverable, so what
they choose and what they refuse to choose is written on each one. Two things
are worth knowing before using them:

  - **The container carries production's role shape**, a bootstrap superuser and
    a separate application role that cannot create a table, because
    [ADR 0009](../docs/adr/0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)
    names this fixture as the owner of its own provisioning. Without it, tests
    pass under privileges no deployment has.
  - **The environment a migration runs under is assembled in one function**,
    `migration_environment` below, and the name it invents for the Alembic
    superuser URL is **this suite's choice** rather than the ticket's — E0-04
    leaves the mechanism open between a `Settings` field, an Alembic-only
    variable, and something `env.py` assembles. So the function supplies the
    container's coordinates under every spelling those three could read, and
    changing the name is one constant.

E0-07 adds one more, `section_codes`, at the very bottom. It is here rather than
in a test module because two modules ask the same question of it — the parsing
unit tests and the derivation integration tests — and E0-07 spells the service's
*file* and none of its callables, so "which function parses a code" is a rule
that would drift if it were written twice (`docs/MISTAKES.md` entry 13). What it
does and what it deliberately refuses to decide is written on the class.

E0-14 adds `mock_platform` and `mock_platforms`, below `section_codes`, plus the
JSON Web Signature helpers they hand back results in. Its definition of done asks
for "a reusable fixture that mints a signed launch — E1's launch-validation tests
depend on it, so its interface matters", so the fixture is the ticket's own
deliverable rather than a convenience, and it lives here for the reason every
other shared thing does: E1 will import it, and a second copy would drift. Like
`SectionCodeService`, it discovers the mock platform rather than naming its
parts — what it discovers and what it refuses to decide is written on the class.
"""

import base64
import hashlib
import hmac
import importlib
import inspect
import itertools
import json
import os
import re
import secrets
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from html.parser import HTMLParser
from importlib.machinery import PathFinder
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple
from urllib.parse import parse_qs, urljoin, urlsplit
from uuid import uuid4

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
BASE_COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
OVERRIDE_COMPOSE_PATH = REPO_ROOT / "docker-compose.override.yml"
COMPOSE_PATHS = (BASE_COMPOSE_PATH, OVERRIDE_COMPOSE_PATH)
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

BACKEND_DIR = REPO_ROOT / "backend"
ALEMBIC_INI_PATH = BACKEND_DIR / "alembic.ini"
MIGRATIONS_DIR = BACKEND_DIR / "migrations"

# Compose interpolation. The alternatives are ordered so that `$$` is consumed
# first and registers nothing, which matters: the `$$POSTGRES_USER` in the `db`
# health check reaches the container as a literal `$POSTGRES_USER` and is
# expanded by the shell inside it, out of the environment Compose has already
# built. Compose never looks that name up in `.env`, so counting it would let a
# health check vouch for an entry nothing supplies.
#
# `${NAME}`, `${NAME:-default}`, `${NAME:?error}`, `${NAME:+alt}` and the bare
# `$NAME` all read NAME, so the name is taken and the rest of the expression is
# not parsed.
COMPOSE_INTERPOLATION = re.compile(
    r"\$\$|\$\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)|\$(?P<bare>[A-Za-z_][A-Za-z0-9_]*)"
)


def strip_inline_comment(value: str) -> str:
    """Remove a trailing ` # ...` comment, matching dotenv and Compose behaviour.

    A `#` that is not preceded by whitespace is part of the value, which is how
    `docker compose --env-file` and `python-dotenv` both read it.
    """
    if value[:1] in {"'", '"'}:
        quote = value[0]
        closing = value.find(quote, 1)
        return value[1:closing] if closing != -1 else value[1:]
    head, separator, _ = value.partition(" #")
    return head.rstrip() if separator else value


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse dotenv text into an ordered mapping of variable name to value."""
    entries: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        entries[name.strip()] = strip_inline_comment(value.strip())
    return entries


def load_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML file into a mapping.

    Returns an empty mapping when the file is absent or holds something other
    than a mapping, so a test reports a failed assertion naming the missing
    deliverable rather than a fixture error. Every test that consumes one of
    these asserts it is non-empty first, because "nothing in this file is wrong"
    is true of a file that could not be read.
    """
    if not path.is_file():
        return {}
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return document if isinstance(document, dict) else {}


def load_compose(path: Path) -> dict[str, Any]:
    """Parse one Compose file on its own, with no override merged over it.

    Reading the files separately is deliberate and `docker compose config` is
    not a substitute: it merges the override back in, which hides the one
    property `tests/unit/test_compose_stack.py` exists to check.
    """
    return load_yaml(path)


def interpolated_variables(node: Any) -> set[str]:
    """Every environment variable name a parsed Compose document interpolates.

    Walks the parsed document rather than the file text, and that is the point.
    A parser has already discarded the comments, so a `${DB_NAME}` that someone
    commented out stops counting as a reader at the moment it stops being one.
    Scanning raw text would let a commented-out interpolation go on vouching for
    an `.env.example` entry that nothing supplies.

    Names are uppercased, matching how `test_env_example_sync.py` compares them.
    """
    found: set[str] = set()
    if isinstance(node, str):
        for match in COMPOSE_INTERPOLATION.finditer(node):
            name = match.group("braced") or match.group("bare")
            if name:
                found.add(name.upper())
    elif isinstance(node, dict):
        for key, value in node.items():
            found |= interpolated_variables(key)
            found |= interpolated_variables(value)
    elif isinstance(node, list):
        for item in node:
            found |= interpolated_variables(item)
    return found


@pytest.fixture
def base_compose_path() -> Path:
    """Where the base Compose file must live (SPEC §13). Asserted by the test, not here."""
    return BASE_COMPOSE_PATH


@pytest.fixture
def base_compose() -> dict[str, Any]:
    """`docker-compose.yml` parsed alone, with no override merged in."""
    return load_compose(BASE_COMPOSE_PATH)


@pytest.fixture
def override_compose_path() -> Path:
    """Where the development override lives. Asserted by the test, not here."""
    return OVERRIDE_COMPOSE_PATH


@pytest.fixture
def override_compose() -> dict[str, Any]:
    """`docker-compose.override.yml` parsed alone, with no base file under it.

    Added in E0-03, after a reviewer found that nothing read this file at all
    while `worker` and `beat` configuration had moved into it. Parsed on its own
    for the same reason as the base file: the merged view is what every dynamic
    check already sees, and the questions worth asking here are about what this
    file says by itself.

    YAML anchors are resolved by the parser, so a service that merges
    `<<: *development-source` arrives here holding those keys. That is what makes
    a rule about services reach a shared anchor without this fixture knowing
    anchors exist.
    """
    return load_compose(OVERRIDE_COMPOSE_PATH)


@pytest.fixture
def ci_workflow_path() -> Path:
    """Where the CI workflow lives. Asserted by the test, not here."""
    return CI_WORKFLOW_PATH


@pytest.fixture
def ci_workflow() -> dict[str, Any]:
    """`.github/workflows/ci.yml`, parsed rather than grepped.

    A regex over the text cannot tell a job service's `image:` from any other
    line that spells the same word, and it keeps passing against a workflow
    whose shape has changed underneath it — which is the failure the test that
    uses this exists to make impossible.

    One quirk to know before adding anything that reads a top-level key here:
    PyYAML implements YAML 1.1, so the workflow's `on:` parses to the boolean
    `True` rather than to the string `"on"`. Nothing currently needs it.
    """
    return load_yaml(CI_WORKFLOW_PATH)


@pytest.fixture
def compose_read_variables() -> set[str]:
    """Every variable the Compose files read out of `.env`, uppercased.

    Deliberately asserts nothing, and the direction of that choice matters here.
    An empty set makes the test that consumes it *stricter* rather than weaker —
    it falls back to requiring a `Settings` field — so a Compose file that has
    gone missing or stopped parsing cannot quietly turn an assertion into a
    vacuous pass.
    """
    found: set[str] = set()
    for path in COMPOSE_PATHS:
        found |= interpolated_variables(load_compose(path))
    return found


@pytest.fixture
def interpolated_variables_in() -> Callable[[Any], set[str]]:
    """Hand `interpolated_variables` to a test that needs it on one service.

    `compose_read_variables` above answers "what does the whole stack read", and
    a rule about one service holding one credential needs the same question
    asked of one subtree. The same walker answers both, so the two cannot end up
    disagreeing about what counts as reading a variable — `$$` escaped, defaults
    and error forms unwrapped, commented-out interpolations already discarded by
    the parser.
    """
    return interpolated_variables


@pytest.fixture
def env_example_path() -> Path:
    """Where `.env.example` must live (SPEC §13). Asserted by the test, not here."""
    return ENV_EXAMPLE_PATH


@pytest.fixture
def documented_env() -> dict[str, str]:
    """Every variable documented in `.env.example`, with its placeholder value.

    Deliberately asserts nothing: a missing `.env.example` yields an empty
    mapping, so the test that cares reports a failed assertion rather than a
    fixture error. Tests that could pass vacuously on an empty mapping assert it
    is non-empty themselves.
    """
    if not ENV_EXAMPLE_PATH.is_file():
        return {}
    return parse_dotenv(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def import_app_module() -> Iterator[Callable[[str], ModuleType | None]]:
    """Import an `app.*` module against the environment the test has just set.

    A module that builds something out of `Settings` reads the environment once,
    at import time, and `sys.modules` then keeps the result for the rest of the
    session. So a test that sets `REDIS_URL` and imports `app.jobs.celery_app`
    gets the value it set only if nothing imported that module earlier — and if
    something did, the test passes or fails for a reason it did not choose,
    which is `docs/MISTAKES.md` entry 3 in its purest form. Every `app.*` module
    is therefore dropped from `sys.modules` before the test body runs, and the
    set that was there is put back afterwards, so the interpreter is left as it
    was found.

    The returned callable answers `None` for a module that does not exist, so a
    test reports a failed assertion naming the missing deliverable rather than a
    collection error — the same choice `load_yaml` makes above, for the same
    reason. An `ImportError` raised *inside* a module that does exist propagates
    untouched: a module that is broken and a module that was never written need
    different fixes, and a test must not report them as the same thing.
    """
    saved = {
        name: module
        for name, module in list(sys.modules.items())
        if name == "app" or name.startswith("app.")
    }
    for name in saved:
        sys.modules.pop(name, None)

    def import_module(name: str) -> ModuleType | None:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as exc:
            absent = exc.name
            if absent is not None and (name == absent or name.startswith(f"{absent}.")):
                return None
            raise

    try:
        yield import_module
    finally:
        for name in [n for n in list(sys.modules) if n == "app" or n.startswith("app.")]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


@pytest.fixture
def celery_application_in() -> Callable[[ModuleType], Any]:
    """Find the Celery application a module exposes, whatever it is named.

    This mirrors what `celery -A <module>` itself does — `celery.app.utils.
    find_app` looks for an attribute called `app`, then one called `celery`,
    and failing both scans the module for a `Celery` instance — because the
    worker and beat services reach the application that way and the E0-03 ticket
    names no attribute. Pinning a name here would turn the ticket's silence into
    this test suite's decision.

    What is *not* left open is that the application has to be reachable at module
    level: a factory that has to be called is not something `-A` can use, so a
    module that exposes only one answers `None` here and the test that asked
    fails saying so.

    Returns `None` rather than asserting, so the test does the asserting.
    """
    from celery import Celery

    def find(module: ModuleType) -> Any:
        for name in ("app", "celery", "celery_app"):
            candidate = getattr(module, name, None)
            if isinstance(candidate, Celery):
                return candidate
        for name in sorted(vars(module)):
            candidate = getattr(module, name, None)
            if isinstance(candidate, Celery):
                return candidate
        return None

    return find


@pytest.fixture
def configured_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    documented_env: dict[str, str],
) -> dict[str, str]:
    """A process environment that satisfies every documented variable.

    The working directory is moved to an empty temporary directory first, so a
    developer's own `.env` in the repository root cannot supply a value that the
    test believes it removed.
    """
    monkeypatch.chdir(tmp_path)
    for name, value in documented_env.items():
        monkeypatch.setenv(name, value)
    return dict(documented_env)


# ---------------------------------------------------------------------------
# E0-04 — a real Postgres, with production's role shape, migrated once.
# ---------------------------------------------------------------------------

# The service whose image the container runs. Read out of `docker-compose.yml`
# rather than pinned here for the reason `test_image_pins_agree.py` gives: a
# schema proved against a Postgres the project does not deploy is a proof about
# a different system.
DB_SERVICE_NAME = "db"
POSTGRES_CONTAINER_PORT = 5432

# Credentials for a container that exists for the length of one pytest session
# and is then destroyed. Nothing here was copied from a working `.env` and
# nothing here resembles a real credential (CLAUDE.md, secrets). Named
# `...CREDENTIAL` rather than `...PASSWORD` so ruff's S105 keeps flagging the
# real thing; `tests/unit/test_config_settings.py` made the same choice.
TEST_SUPERUSER = "pulse_test_admin"
TEST_SUPERUSER_CREDENTIAL = "test-only-admin-9d41c7ba"
TEST_APP_USER = "pulse_test_app"
TEST_APP_CREDENTIAL = "test-only-app-4b8e0257"
TEST_DATABASE = "pulse_test"

DATABASE_URL_VARIABLE = "DATABASE_URL"

# **This suite's choice**, and the one name in this file that a construction
# decision could displace. E0-04 settles *which identity* runs migrations —
# `DB_SUPERUSER`, never `Settings.database_url` (ADR 0009) — and deliberately
# leaves the mechanism open: a new `Settings` field, an Alembic-only variable,
# or something `env.py` assembles from the parts. `migration_environment` below
# therefore sets this *and* the parts *and* `DATABASE_URL`, so an `env.py`
# written any of those three ways finds the container. If the implementation
# spells the variable differently, change this constant; nothing else moves.
ALEMBIC_SUPERUSER_URL_VARIABLE = "ALEMBIC_DATABASE_URL"


class DatabaseUnderTest(NamedTuple):
    """One database in the test container, addressed as each of the two roles.

    Both URLs name the same database on the same server. Which one a caller
    reaches for is the whole subject of ADR 0009: migrations and bootstrap use
    `superuser_url`, and everything the application does uses `application_url`.
    """

    superuser_url: str
    application_url: str


def container_url(container: Any, *, username: str, credential: str, database: str) -> str:
    """A `postgresql+psycopg://` URL for one role against one database."""
    host = container.get_container_host_ip()
    port = container.get_exposed_port(POSTGRES_CONTAINER_PORT)
    return f"postgresql+psycopg://{username}:{credential}@{host}:{port}/{database}"


def migration_environment(database: DatabaseUnderTest) -> dict[str, str]:
    """Every environment variable an `env.py` could need to reach `database`.

    Deliberately over-supplies. E0-04 leaves it open whether Alembic learns the
    superuser connection from a whole URL or assembles one from the parts
    `.env.example` already declares, and a fixture that supplied only one of
    those would make that choice for the implementer — quietly, by failing the
    other option. So the parts and the URL are both set, and they agree: same
    host, same port, same database.

    `DATABASE_URL` is set to the *application* role, exactly as it is in
    production. An `env.py` that uses it to connect will fail to create a table,
    which is the failure ADR 0009 exists to keep visible.
    """
    superuser = urlsplit(database.superuser_url)
    application = urlsplit(database.application_url)
    return {
        ALEMBIC_SUPERUSER_URL_VARIABLE: database.superuser_url,
        DATABASE_URL_VARIABLE: database.application_url,
        "DB_SUPERUSER": superuser.username or "",
        "DB_SUPERUSER_PASSWORD": superuser.password or "",
        "DB_APP_USER": application.username or "",
        "DB_APP_PASSWORD": application.password or "",
        "DB_NAME": superuser.path.lstrip("/"),
    }


@contextmanager
def environment(values: dict[str, str]) -> Iterator[None]:
    """Set `values` in `os.environ` and put the previous contents back after.

    `monkeypatch` would be the idiom, and it is function-scoped, so the
    session-scoped fixture that applies migrations once cannot use it.
    """
    saved = {name: os.environ.get(name) for name in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for name, previous in saved.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous


def alembic_config() -> Any:
    """The project's own Alembic configuration, pointed at its script directory.

    `script_location` is set rather than read, and that is not the test choosing
    where migrations live: SPEC §13 and E0-04 both put them at
    `backend/migrations/`. A relative `script_location` in `alembic.ini`
    resolves against the working directory, which is `backend/` for
    `make migrate` and the repository root for pytest, so leaving it unset would
    fail on where pytest happens to be standing rather than on anything the
    ticket is about.
    """
    from alembic.config import Config

    if not ALEMBIC_INI_PATH.is_file():
        pytest.fail(
            f"{ALEMBIC_INI_PATH} does not exist. E0-04 ships `backend/alembic.ini` and "
            "`backend/migrations/` with `env.py` wired to `Base.metadata` and to the "
            "superuser connection (SPEC §13, ADR 0009)."
        )
    if not MIGRATIONS_DIR.is_dir():
        pytest.fail(
            f"{MIGRATIONS_DIR} does not exist. E0-04 ships the migration environment and one "
            "baseline revision that creates nothing, establishing the revision chain."
        )

    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def provision_application_role(superuser_url: str, database: str) -> None:
    """Create the role the application connects as, as `scripts/db-init` does.

    ADR 0009's provisioning table gives this fixture its own row, and E0-04 owns
    it: `scripts/db-init` runs only where the Compose `initdb` hook exists, and
    a container started by testcontainers has no such hook. Without this, every
    test would run as the cluster superuser — bypassing every grant and every
    row-level security policy — and the suite would be measuring privileges no
    deployment has.

    `NOSUPERUSER` and `CONNECT` and nothing else, matching
    `scripts/db-init/01-application-role.sh`. The credential is inlined into the
    statement because Postgres does not accept bind parameters in `CREATE ROLE`;
    that script uses `\\password` instead, for a reason that does not apply to a
    throwaway container whose credential is in this file.
    """
    from sqlalchemy import create_engine, text

    create_role = (
        f'CREATE ROLE "{TEST_APP_USER}" LOGIN'
        f" PASSWORD '{TEST_APP_CREDENTIAL}'"
        " NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
    )
    grant_connect = f'GRANT CONNECT ON DATABASE "{database}" TO "{TEST_APP_USER}"'

    engine = create_engine(superuser_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(text(create_role))
            connection.execute(text(grant_connect))
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[Any]:
    """A Postgres container on the image `docker-compose.yml` deploys.

    Session-scoped: starting one costs seconds, and the isolation every test
    needs comes from `db_session` rolling its transaction back rather than from
    a fresh server. The `with` block is what tears it down, on the way out of a
    passing run and out of a failing one alike.

    `testcontainers.community.postgres`, not `testcontainers.postgres`: on the
    locked testcontainers 4.15.0 the shorter path raises a DeprecationWarning at
    import, and `filterwarnings = ["error::DeprecationWarning"]` in
    `pyproject.toml` turns that into a collection error.
    """
    from testcontainers.community.postgres import PostgresContainer

    services = load_compose(BASE_COMPOSE_PATH).get("services") or {}
    service = services.get(DB_SERVICE_NAME) or {}
    image = service.get("image") if isinstance(service, dict) else None

    if not isinstance(image, str) or not image:
        pytest.fail(
            f"{BASE_COMPOSE_PATH} declares no image for the `{DB_SERVICE_NAME}` service, so "
            "these tests have no Postgres image to run and cannot fall back to one without "
            "checking the schema against a server the project never deploys."
        )

    with PostgresContainer(
        image=image,
        username=TEST_SUPERUSER,
        password=TEST_SUPERUSER_CREDENTIAL,
        dbname=TEST_DATABASE,
        driver="psycopg",
    ) as container:
        yield container


@pytest.fixture(scope="session")
def provisioned_database(postgres_container: Any) -> DatabaseUnderTest:
    """The container's database, with both roles, before any migration runs."""
    urls = DatabaseUnderTest(
        superuser_url=container_url(
            postgres_container,
            username=TEST_SUPERUSER,
            credential=TEST_SUPERUSER_CREDENTIAL,
            database=TEST_DATABASE,
        ),
        application_url=container_url(
            postgres_container,
            username=TEST_APP_USER,
            credential=TEST_APP_CREDENTIAL,
            database=TEST_DATABASE,
        ),
    )
    provision_application_role(urls.superuser_url, TEST_DATABASE)
    return urls


@pytest.fixture(scope="session")
def migrated_database(provisioned_database: DatabaseUnderTest) -> DatabaseUnderTest:
    """`alembic upgrade head`, applied once for the whole session."""
    from alembic import command

    with environment(migration_environment(provisioned_database)):
        command.upgrade(alembic_config(), "head")
    return provisioned_database


@pytest.fixture
def empty_database(
    postgres_container: Any,
    provisioned_database: DatabaseUnderTest,
) -> Iterator[DatabaseUnderTest]:
    """A database with nothing in it at all, for one test, then dropped.

    "`alembic upgrade head` succeeds against an empty database" is a claim about
    an empty one, and the session database stops being empty the moment the
    first migration lands on it. A second database in the same container is far
    cheaper than a second container, and roles are cluster-wide, so both URLs
    still name the two roles ADR 0009 separates.
    """
    from sqlalchemy import create_engine, text

    name = f"e0_04_{uuid4().hex[:12]}"
    admin = create_engine(provisioned_database.superuser_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        yield DatabaseUnderTest(
            superuser_url=container_url(
                postgres_container,
                username=TEST_SUPERUSER,
                credential=TEST_SUPERUSER_CREDENTIAL,
                database=name,
            ),
            application_url=container_url(
                postgres_container,
                username=TEST_APP_USER,
                credential=TEST_APP_CREDENTIAL,
                database=name,
            ),
        )
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def alembic_config_pointed_at(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[DatabaseUnderTest], Any]:
    """Point Alembic at one database and hand back a `Config` to run commands with.

    The commands stay in the test — `command.upgrade`, `command.check` — because
    which one is being run is the subject of the test that runs it, and a
    fixture that ran them would move the assertion's verb into this file.
    """

    def prepare(database: DatabaseUnderTest) -> Any:
        for name, value in migration_environment(database).items():
            monkeypatch.setenv(name, value)
        return alembic_config()

    return prepare


@pytest.fixture(scope="session")
def migrated_engine(migrated_database: DatabaseUnderTest) -> Iterator[Any]:
    """An engine on the migrated database, connected as the bootstrap identity.

    The bootstrap identity and not the application one, and the reason is worth
    stating because it looks like the wrong choice. Tests seed the rows they
    read back, and the application role deliberately holds nothing but `CONNECT`
    (ADR 0001 line 71, ADR 0009) — so a fixture that seeded as the application
    role would either fail or need a grant this project does not make.
    `app.db`'s own engine connects as the application role, which is what
    `tests/integration/test_db_session.py` exercises.
    """
    from sqlalchemy import create_engine

    engine = create_engine(migrated_database.superuser_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(migrated_engine: Any) -> Iterator[Any]:
    """A session whose every write is rolled back when the test ends.

    The transaction is opened on the connection *outside* the session, and the
    session joins it by creating a savepoint, so a test that commits still ends
    up inside a transaction this fixture can roll back. That is what makes the
    isolation hold against test code that does not know about it — which is the
    only kind of isolation worth having, since a test that has to cooperate to
    stay isolated will eventually not.

    Postgres puts DDL inside the transaction too, so a table created in a test
    is gone with the rest of it.
    """
    from sqlalchemy.orm import Session

    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(scope="session")
def application_engine(provisioned_database: DatabaseUnderTest) -> Iterator[Any]:
    """An engine connected as the application role, holding only what it is granted."""
    from sqlalchemy import create_engine

    engine = create_engine(provisioned_database.application_url)
    yield engine
    engine.dispose()


# ---------------------------------------------------------------------------
# E0-07 — reaching the section-code service without naming what it is made of.
# ---------------------------------------------------------------------------

# Spelled by E0-07's scope: "`backend/app/services/section_codes.py`". The
# package root is `backend/`, so the import path is `app.services....`.
SECTION_CODE_MODULE = "app.services.section_codes"

# What a value the tests can supply is *for*, matched against a parameter's
# name. E0-07 says the derivation takes "the code and the section's term" and
# says nothing about whether a session is passed, whether the term arrives as a
# model instance or a key, or what any of it is called — so the tests offer
# every value they have and let the signature take what it wants. Matching is by
# exact name or by `_`-suffix, longest alias first, so `section_code` is a code
# and `course_week` is a course week rather than a bare week.
SERVICE_ROLES: dict[str, tuple[str, ...]] = {
    "session": ("session", "db"),
    "code": ("code", "section_code"),
    "term": ("term",),
    "term_id": ("term_id",),
    "section": ("section",),
    "course_week": ("course_week", "week"),
}


class SectionCodeService:
    """E0-07's service, found rather than named.

    **Every identifier inside the module is discovered.** The ticket names the
    file and the four values the derivation produces — `length_weeks`,
    `start_date`, `end_date`, `modality` — and nothing else: not the parse
    function, not the derivation function, not the offset function, not the error
    classes, not the shape a parsed code comes back in. Naming any of them here
    would make the implementer build to this fixture instead of to the ticket,
    which is the failure `tests/integration/test_term_calendar_schema.py`'s
    `week_producer` avoids the same way.

    So a callable is looked up by a fragment of its name, and the answer has to
    be unambiguous: none, or two that this cannot choose between, is a failure
    that lists what the module defines and says which choice would settle it.
    Module-level functions and the `classmethod`/`staticmethod` members of
    module-level classes both count, because `SectionCode.parse` and
    `parse_section_code` are equally reasonable and the ticket rules out neither.

    **What this does not do is decide anything.** Where a test needs a name that
    E0-07 leaves open it fails saying so, rather than guessing quietly and
    passing against a design the ticket never asked for.
    """

    def __init__(self) -> None:
        self._module: ModuleType | None = None

    # -- reaching the module and its callables ------------------------------

    @property
    def module(self) -> ModuleType:
        """`app.services.section_codes`, or a failure naming the missing file.

        A `ModuleNotFoundError` for some *other* module is re-raised untouched:
        a service that exists and imports something absent and a service that
        was never written need different fixes, and a test must not report them
        as the same thing. `import_app_module` above makes the same distinction
        for the same reason.
        """
        if self._module is None:
            try:
                self._module = importlib.import_module(SECTION_CODE_MODULE)
            except ModuleNotFoundError as failure:
                absent = failure.name
                if absent is None or not (
                    absent == SECTION_CODE_MODULE or SECTION_CODE_MODULE.startswith(f"{absent}.")
                ):
                    raise
                pytest.fail(
                    f"There is no `{SECTION_CODE_MODULE}` module. E0-07's scope puts the parser "
                    "and the date derivation in `backend/app/services/section_codes.py` (SPEC "
                    "§13 gives `services/` that job, and the ticket names the file)."
                )
        return self._module

    def defined_callables(self) -> dict[str, Any]:
        """Every public callable the service module defines itself.

        Defines *itself*: a function imported from somewhere else is not part of
        this module's surface, and counting one would let an imported `parse`
        from the standard library answer for the ticket's deliverable.
        """
        found: dict[str, Any] = {}
        for name, value in vars(self.module).items():
            if name.startswith("_"):
                continue
            if getattr(value, "__module__", None) != SECTION_CODE_MODULE:
                continue
            if inspect.isfunction(value):
                found[name] = value
            elif inspect.isclass(value):
                for attribute, member in vars(value).items():
                    if attribute.startswith("_") or not isinstance(
                        member, classmethod | staticmethod
                    ):
                        continue
                    bound = getattr(value, attribute, None)
                    if callable(bound):
                        found[f"{name}.{attribute}"] = bound
        return found

    def callable_named_after(self, fragments: tuple[str, ...], purpose: str, quoting: str) -> Any:
        """The one callable whose name carries one of `fragments`.

        Fragments are tried in order, so a module that spells the derivation
        `derive_section_calendar` is found by "deriv" without "calendar" ever
        being consulted. A fragment matching more than one callable stops rather
        than picking: two candidates mean this cannot tell which one the ticket
        is about, and choosing would be the test deciding. A module-level
        function is preferred over a class member of the same name, since a
        `SectionCode.parse` that delegates to `parse` is one deliverable and not
        two.
        """
        defined = self.defined_callables()
        for fragment in fragments:
            matches = {
                name: value
                for name, value in defined.items()
                if fragment in name.rsplit(".", maxsplit=1)[-1].lower()
            }
            if len(matches) > 1:
                unqualified = {name: value for name, value in matches.items() if "." not in name}
                if len(unqualified) == 1:
                    return next(iter(unqualified.values()))
                pytest.fail(
                    f"`{SECTION_CODE_MODULE}` defines more than one callable whose name carries "
                    f"{fragment!r} ({sorted(matches)}), so this cannot tell which one {purpose}. "
                    "Naming one here would pin an interface E0-07 leaves open — say in the pull "
                    "request which it is, and `SectionCodeService` in tests/conftest.py is the "
                    "one place that changes."
                )
            if matches:
                return next(iter(matches.values()))
        pytest.fail(
            f"`{SECTION_CODE_MODULE}` defines no callable whose name carries any of "
            f"{list(fragments)} — it defines {sorted(defined)}. E0-07's scope: {quoting} The "
            "callable is looked for by name rather than imported under an agreed one because no "
            "ticket spells it; if it is there under a name none of these fragments reaches, that "
            "is a defect in this fixture rather than in the service."
        )

    @property
    def parse(self) -> Any:
        """The callable that turns a section code into its three parts."""
        return self.callable_named_after(
            ("parse", "from_code"),
            "parses a section code",
            "'parse a code into start letter, ordinal, and modality; reject malformed codes with "
            "a specific error naming what failed'.",
        )

    @property
    def derive(self) -> Any:
        """The callable that turns a code plus a term into a section's calendar."""
        return self.callable_named_after(
            ("deriv", "calendar", "dates"),
            "derives a section's calendar",
            "'Derive `length_weeks`, `start_date`, `end_date`, and `modality` from the code and "
            "the section's term, reading `start_letter_map`'.",
        )

    @property
    def writer(self) -> Any:
        """The callable that puts a derived calendar onto a section.

        E0-07's scope: "Add the derived section columns and populate them through
        this service, so there is exactly one path that sets them." That sentence
        names a writer and, like everything else here, does not name the
        function — so it is found the same way, by a fragment of its name, with
        "apply" first because applying a code to a section is what the ticket
        describes it doing.
        """
        return self.callable_named_after(
            ("apply", "populate", "assign", "fill", "write"),
            "writes a derived calendar onto a section",
            "'Add the derived section columns and populate them through this service, so there "
            "is exactly one path that sets them'.",
        )

    @property
    def offset(self) -> Any:
        """The callable that relates a section's course weeks to its term's weeks."""
        return self.callable_named_after(
            ("offset", "term_week", "week"),
            "converts between the course-week and term-week axes",
            "'The offset arithmetic belongs here', and the last acceptance criterion: "
            "'Course-week to term-week offset is computed and tested for a section that starts "
            "five weeks into a term'.",
        )

    # -- calling one --------------------------------------------------------

    @staticmethod
    def role_of(parameter_name: str) -> str | None:
        """Which of `SERVICE_ROLES` a parameter called `parameter_name` wants."""
        best: tuple[int, str] | None = None
        for role, aliases in SERVICE_ROLES.items():
            for alias in aliases:
                if (parameter_name == alias or parameter_name.endswith(f"_{alias}")) and (
                    best is None or len(alias) > best[0]
                ):
                    best = (len(alias), role)
        return None if best is None else best[1]

    def call(self, function: Any, **available: Any) -> Any:
        """Call `function`, filling each parameter from the roles offered.

        Binding by parameter name rather than by position, and never by
        `try: ... except TypeError:`, is deliberate. A helper that retried
        several call shapes until one stopped raising would swallow a `TypeError`
        raised *inside* the service, and would report a design the ticket never
        chose as working — the shape of `docs/MISTAKES.md` entry 3. This way a
        parameter that no offered role matches stops the test with a message
        naming it, which is a defect in this fixture or an interface question for
        the ticket, and either way something to see rather than route around.

        One narrow accommodation: a single-parameter callable is handed the one
        value the caller offered, whatever it is named. `parse(raw)` and
        `parse(code)` are the same deliverable, and the parameter's name is not
        something E0-07 decides.
        """
        signature = inspect.signature(function)
        parameters = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
        ]
        if len(parameters) == 1 and len(available) == 1:
            only = next(iter(available.values()))
            if parameters[0].kind is parameters[0].POSITIONAL_ONLY:
                return function(only)
            return function(**{parameters[0].name: only})

        positional: list[Any] = []
        keyword: dict[str, Any] = {}
        for parameter in parameters:
            role = self.role_of(parameter.name)
            if role is None or role not in available:
                if parameter.default is not parameter.empty:
                    continue
                pytest.fail(
                    f"`{getattr(function, '__qualname__', function)}` requires a parameter "
                    f"`{parameter.name}` that this test has nothing to fill from. It is offering "
                    f"{sorted(available)}. E0-07 says the derivation takes 'the code and the "
                    "section's term' and spells no signature, so a parameter outside that is an "
                    "interface question for the ticket — add the role to `SERVICE_ROLES` in "
                    "tests/conftest.py once the pull request says what it is for."
                )
            if parameter.kind is parameter.POSITIONAL_ONLY:
                positional.append(available[role])
            else:
                keyword[parameter.name] = available[role]
        return function(*positional, **keyword)

    # -- reading what came back ---------------------------------------------

    @staticmethod
    def part(subject: Any, candidates: tuple[str, ...], label: str) -> Any:
        """One named part of a parsed or derived result, however it is carried.

        A mapping key or an attribute, because E0-07 does not say whether the
        result is a dataclass, a Pydantic model, a `NamedTuple` or a dict, and
        all four answer to a name. A plain tuple does not, and is a failure here
        rather than an index this file invents an order for.
        """
        for candidate in candidates:
            if isinstance(subject, Mapping) and candidate in subject:
                return subject[candidate]
            if hasattr(subject, candidate):
                return getattr(subject, candidate)
        pytest.fail(
            f"{subject!r} carries none of {list(candidates)}, so this test cannot read the "
            f"{label} out of it. E0-07 names the parts — 'start letter, ordinal, and modality', "
            "and `length_weeks`, `start_date`, `end_date`, `modality` — without saying what "
            "carries them; the candidates are a constant in the test module and a deliberate "
            "rename is a one-line change there."
        )

    @staticmethod
    def raised_by_the_service(failure: BaseException) -> bool:
        """Whether `failure` is an error this project defines, not one that leaked.

        E0-07's definition of done: section codes arrive from the LMS, so confirm
        "no exception type that escapes as a 500". A `KeyError` off a letter-map
        lookup, an `IndexError` off a short string and a `ValueError` out of
        `int()` are all what an unguarded parser raises, and none of them is
        something a caller can catch on purpose.
        """
        return type(failure).__module__.split(".")[0] == "app"


@pytest.fixture
def section_codes() -> SectionCodeService:
    """E0-07's service, reached by discovery. See `SectionCodeService` above."""
    return SectionCodeService()


# ---------------------------------------------------------------------------
# E0-14 — the mock LTI 1.3 platform, driven the way a tool drives one.
# ---------------------------------------------------------------------------

# SPEC §13 spells the directory and the package inside it: `mock-lms/` holding a
# `Dockerfile` and an `app/`. Nothing else about the module layout is written
# down, so the application object is discovered rather than imported by name.
MOCK_LMS_DIR = REPO_ROOT / "mock-lms"
MOCK_LMS_SERVICE = "mock-lms"
MOCK_LMS_PACKAGE = "app"

# Where the ASGI application might sit inside that package, most likely first.
# `backend/` puts its own in `app.main`, so a mock written beside it probably
# does too; the rest are here so that a different arrangement is found rather
# than reported as a missing deliverable.
MOCK_LMS_MODULES = ("app.main", "app", "app.platform", "app.server", "app.api")

# Names a zero-argument application factory might carry, if the mock exposes one
# instead of a module-level instance. `backend/app/main.py` uses `create_app`,
# and `uvicorn --factory` is what makes that legal, so the mock may well too.
APPLICATION_FACTORY_NAMES = ("create_app", "get_app", "make_app", "build_app")

# How many launches a page offering several users, contexts or roles is walked
# for. **This suite's choice**, and a bound rather than a rule: the seeded data
# is meant to be small (E0-15: "this seed data belongs to the mock platform and
# stays small"), and a page offering more combinations than this is still walked,
# just not exhaustively. Raise it if a seed grows and a test starts missing a
# shape it names.
MAX_LAUNCH_VARIANTS = 32

# The parameters a tool sends to a platform's authorization endpoint for a plain
# resource-link launch. These are the OIDC and LTI 1.3 required values, not this
# suite's preferences: `id_token` with `form_post` and `prompt=none` is what the
# LTI 1.3 security framework specifies, and a platform that answered anything
# else would not be strict LTI 1.3 core (SPEC §7.3).
AUTHORIZATION_REQUEST_CONSTANTS = {
    "scope": "openid",
    "response_type": "id_token",
    "response_mode": "form_post",
    "prompt": "none",
}

# The DigestInfo prefix PKCS#1 v1.5 puts in front of a SHA-256 digest, from
# RFC 8017 appendix B.1. Nineteen bytes, and the whole of what makes an RS256
# verification a verification rather than a decode.
SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def base64url_decode(value: str) -> bytes:
    """Decode one base64url segment, supplying the padding JWS omits."""
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class JsonWebSignature(NamedTuple):
    """A compact JWS, split into the parts a verification needs.

    `signing_input` is the exact bytes that were signed — the encoded header and
    payload with the dot between them — and it is kept rather than recomputed so
    that a caller checking a *tampered* token compares against what the tamper
    produced.
    """

    header: dict[str, Any]
    claims: dict[str, Any]
    signing_input: bytes
    signature: bytes


def split_jws(token: str) -> JsonWebSignature:
    """Split a compact JWS, failing with the token in hand if it is not one."""
    parts = token.split(".")
    if len(parts) != 3:
        pytest.fail(
            f"The mock platform issued a value with {len(parts)} dot-separated segments rather "
            "than the three a compact JSON Web Signature has, so it is not a signed `id_token`. "
            f"It begins {token[:64]!r}."
        )
    encoded_header, encoded_claims, encoded_signature = parts
    try:
        header = json.loads(base64url_decode(encoded_header))
        claims = json.loads(base64url_decode(encoded_claims))
    except ValueError as failure:
        # `json.JSONDecodeError` and `binascii.Error` are both `ValueError`
        # subclasses, so this one clause covers a segment that is not base64url
        # and a segment that decodes to something that is not JSON.
        pytest.fail(f"The `id_token`'s header or payload is not base64url-encoded JSON: {failure}")
    return JsonWebSignature(
        header=header,
        claims=claims,
        signing_input=f"{encoded_header}.{encoded_claims}".encode("ascii"),
        signature=base64url_decode(encoded_signature),
    )


def verify_rs256(signing_input: bytes, signature: bytes, key: Mapping[str, Any]) -> bool:
    """Whether `signature` is an RS256 signature over `signing_input` under `key`.

    Written out of `pow` and `hashlib` rather than taken from a library, because
    nothing in this project's locked dependency set verifies a JWS and adding one
    to satisfy a test would decide, from the test side, which JOSE library the
    mock signs with. RSA *verification* is public-exponent modular
    exponentiation and a padding comparison, so the whole of it is below.

    The comparison is against the full PKCS#1 v1.5 encoded message, padding
    included, which is what makes this a real check: a verifier that compared
    only the trailing digest would accept a signature with forged padding, and a
    verifier that only decoded the token would accept anything at all. The tests
    that hand this a wrong key and a tampered payload are what prove it says no.
    """
    if key.get("kty") != "RSA":
        return False
    try:
        modulus = int.from_bytes(base64url_decode(str(key["n"])), "big")
        exponent = int.from_bytes(base64url_decode(str(key["e"])), "big")
    except (KeyError, ValueError, TypeError):
        return False
    if modulus <= 0 or exponent <= 0:
        return False

    width = (modulus.bit_length() + 7) // 8
    if len(signature) != width:
        return False
    numeric = int.from_bytes(signature, "big")
    if numeric >= modulus:
        return False

    encoded = pow(numeric, exponent, modulus).to_bytes(width, "big")
    digest_info = SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(signing_input).digest()
    if width < len(digest_info) + 11:
        return False
    expected = b"\x00\x01" + b"\xff" * (width - len(digest_info) - 3) + b"\x00" + digest_info
    return hmac.compare_digest(encoded, expected)


def verifying_key(signature: JsonWebSignature, key_set: Mapping[str, Any]) -> dict[str, Any] | None:
    """The key in `key_set` that verifies `signature`, or `None` if none does.

    Every key is tried, not just the one the header's `kid` names. That is
    deliberate: whether the header selects the right key and whether the key set
    contains a key that works are two different claims, and one test asserts each.
    Trying only the named key would fold them together, so a mock that published
    the right key under the wrong `kid` would fail both tests with one cause.
    """
    keys = key_set.get("keys")
    if not isinstance(keys, list):
        return None
    for key in keys:
        if isinstance(key, dict) and verify_rs256(
            signature.signing_input, signature.signature, key
        ):
            return key
    return None


class FormReader(HTMLParser):
    """Every form on an HTML page, with the fields it would submit.

    A parser rather than a regular expression, because what is being read is the
    launch page's contract with a browser — a form's action, its method, and the
    named values it carries — and a pattern over markup answers a different
    question that happens to look the same (`docs/MISTAKES.md` entry 3).

    `<select>` options are collected separately from fixed fields, because a
    launch page offering a choice of seeded users is one form with several
    outcomes, and the tests about "an arbitrary seeded user" need each outcome.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self.open_select: str | None = None
        self.open_option: str | None = None
        self.option_text: str = ""

    def current(self) -> dict[str, Any] | None:
        return self.forms[-1] if self.forms else None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): (value or "") for name, value in attrs}
        if tag == "form":
            self.forms.append(
                {
                    "action": attributes.get("action", ""),
                    "method": (attributes.get("method") or "get").lower(),
                    "fields": {},
                    "choices": {},
                }
            )
            return
        form = self.current()
        if form is None:
            return
        if tag in {"input", "textarea"}:
            name = attributes.get("name")
            if name:
                form["fields"][name] = attributes.get("value", "")
        elif tag == "select":
            self.open_select = attributes.get("name") or None
            if self.open_select:
                form["choices"].setdefault(self.open_select, [])
        elif tag == "option" and self.open_select:
            # Closed here as well as on `</option>`, because HTML permits the
            # end tag to be omitted and a page that omits it would otherwise
            # lose every option but the last — which would silently shrink the
            # set of seeded launches the tests walk.
            self.close_option()
            self.open_option = attributes.get("value")
            self.option_text = ""

    def handle_data(self, data: str) -> None:
        if self.open_option is None and self.open_select:
            self.option_text += data

    def close_option(self) -> None:
        form = self.current()
        if form is None or not self.open_select:
            return
        value = self.open_option if self.open_option is not None else self.option_text.strip()
        if value:
            form["choices"][self.open_select].append(value)
        self.open_option = None
        self.option_text = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "option":
            self.close_option()
        elif tag == "select":
            self.close_option()
            self.open_select = None


def forms_in(markup: str) -> list[dict[str, Any]]:
    """Parse `markup` and hand back every form it declares."""
    reader = FormReader()
    reader.feed(markup)
    reader.close()
    return reader.forms


def form_submissions(form: Mapping[str, Any]) -> list[dict[str, str]]:
    """Every set of values `form` could submit, one per combination of choices."""
    choices = form.get("choices") or {}
    names = sorted(name for name, options in choices.items() if options)
    if not names:
        return [dict(form.get("fields") or {})]
    submissions: list[dict[str, str]] = []
    for combination in itertools.islice(
        itertools.product(*(choices[name] for name in names)), MAX_LAUNCH_VARIANTS
    ):
        values = dict(form.get("fields") or {})
        values.update(dict(zip(names, combination, strict=True)))
        submissions.append(values)
    return submissions


class LaunchOffer(NamedTuple):
    """One launch the platform's launch page offers a browser.

    `posts_to` is the form's action — the tool's third-party login-initiation
    URL — and `parameters` is what the form would send it. Those parameters are
    the OIDC third-party-initiated login request, so they are also where a test
    learns the seeded registration's issuer, client ID and deployment ID without
    any endpoint being invented to publish them.
    """

    page: str
    posts_to: str
    method: str
    parameters: dict[str, str]


class SignedLaunch(NamedTuple):
    """The result of driving one launch to the point the tool would receive it."""

    offer: LaunchOffer
    authorization_request: dict[str, str]
    id_token: str
    state: str | None
    posted_to: str | None
    signature: JsonWebSignature

    @property
    def claims(self) -> dict[str, Any]:
        return self.signature.claims

    @property
    def header(self) -> dict[str, Any]:
        return self.signature.header


class MockLmsFinder:
    """Resolve the `app` package out of `mock-lms/` for the duration of an import.

    The mock is a second application whose package is *also* called `app`
    (SPEC §13), and this repository's own `app` is importable in the test
    process. Putting `mock-lms/` on `sys.path` is not enough to win that
    collision: an editable install of the backend registers a meta-path finder,
    and `sys.meta_path` is consulted before `sys.path` is, so a plain
    `import app` would return the backend's package on a developer's machine and
    possibly the mock's in CI — the same test measuring two different programs
    depending on how the project was installed.

    So the resolution is made explicit and temporary: this finder goes on the
    front of `sys.meta_path`, answers for `app` and everything under it out of
    `mock-lms/`, and comes off again. Nothing outside the import sees it.
    """

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname != MOCK_LMS_PACKAGE and not fullname.startswith(f"{MOCK_LMS_PACKAGE}."):
            return None
        parts = fullname.split(".")
        if len(parts) == 1:
            search = [str(MOCK_LMS_DIR)]
        else:
            parent = sys.modules.get(".".join(parts[:-1]))
            search = list(getattr(parent, "__path__", []))
        return PathFinder.find_spec(fullname, search)


def import_mock_lms_application(values: Mapping[str, str]) -> Any:
    """Import the mock platform fresh, under `values`, and return its ASGI app.

    Fresh every time, and that is the property two of E0-14's tests rest on:
    "issuer keys are generated per run" is only observable if a second start of
    the platform is really a second start. Every `app*` module is dropped before
    the import and the previous set is put back after, exactly as
    `import_app_module` does above and for the same reason — a module cached in
    `sys.modules` answers with the environment some earlier test set.

    What is found is a `FastAPI` instance at module level, or a factory that
    returns one. Both are legal — `uvicorn --factory` is how this repository
    starts its own — and E0-14 names neither, so naming one here would make the
    implementer build to this fixture instead of to the ticket.
    """
    from fastapi import FastAPI

    if not MOCK_LMS_DIR.is_dir():
        pytest.fail(
            f"{MOCK_LMS_DIR} does not exist. E0-14's scope is a `mock-lms/` FastAPI application "
            "with a Dockerfile, added to Compose as `mock-lms` (SPEC §13 puts it at "
            "`mock-lms/app/`, and §9.2 says what it is for)."
        )

    saved = {
        name: module
        for name, module in list(sys.modules.items())
        if name == MOCK_LMS_PACKAGE or name.startswith(f"{MOCK_LMS_PACKAGE}.")
    }
    for name in saved:
        sys.modules.pop(name, None)

    finder = MockLmsFinder()
    sys.meta_path.insert(0, finder)
    imported: list[ModuleType] = []
    try:
        with environment(dict(values)):
            for name in MOCK_LMS_MODULES:
                try:
                    module = importlib.import_module(name)
                except ModuleNotFoundError as failure:
                    absent = failure.name
                    if absent is not None and (name == absent or name.startswith(f"{absent}.")):
                        continue
                    raise
                imported.append(module)
                for attribute in sorted(vars(module)):
                    candidate = getattr(module, attribute, None)
                    if isinstance(candidate, FastAPI):
                        return candidate
                for attribute in APPLICATION_FACTORY_NAMES:
                    factory = getattr(module, attribute, None)
                    if callable(factory) and not inspect.isclass(factory):
                        built = factory()
                        if isinstance(built, FastAPI):
                            return built
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)
        for name in [
            n
            for n in list(sys.modules)
            if n == MOCK_LMS_PACKAGE or n.startswith(f"{MOCK_LMS_PACKAGE}.")
        ]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)

    pytest.fail(
        "Nothing under `mock-lms/app/` exposes a FastAPI application. Looked for a module-level "
        f"instance, then a factory named one of {list(APPLICATION_FACTORY_NAMES)}, in "
        f"{list(MOCK_LMS_MODULES)}; imported {[m.__name__ for m in imported] or 'nothing'}. "
        "E0-14's scope is a `mock-lms/` FastAPI application; if it is reachable under a spelling "
        "none of those covers, that is a defect in `MockPlatform` in tests/conftest.py rather "
        "than in the mock, and MOCK_LMS_MODULES there is the one line that changes."
    )


class MockPlatform:
    """E0-14's platform, driven the way a tool drives one rather than by name.

    **Nothing about the mock's URLs is written down**, so nothing here is
    hardcoded that the protocol can supply instead:

      - The launch page is found by *what it serves*: the page carrying a form
        with the OIDC third-party-initiated login parameters. That is the
        definition of a launch page rather than a guess at a path.
      - The registration values a test compares claims against — issuer, client
        ID, deployment ID, target link URI — are read out of that form, because
        those are exactly the parameters the initiation request carries.
      - The authorization endpoint and the key set are taken from the platform's
        OIDC discovery document when it serves one, and otherwise from the one
        route whose path names them.

    Two paths are all this leaves to a fragment match, and each fails with a
    message saying so. **What this does not do is decide anything**: where E0-14
    leaves a name open, a test fails naming the gap rather than passing against
    an interface the ticket never asked for.
    """

    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        from fastapi.testclient import TestClient

        self.values = dict(values or {})
        self.application = import_mock_lms_application(self.values)
        self.client = TestClient(self.application, follow_redirects=False)
        # Entered so the application's lifespan runs: a platform that generates
        # its issuer key on startup has not generated one until it does.
        self.client.__enter__()

    def close(self) -> None:
        self.client.__exit__(None, None, None)

    # -- what the application serves ----------------------------------------

    def paths(self, method: str = "GET") -> list[str]:
        """Every declared path that answers `method` and takes no path parameter."""
        found: list[str] = []
        for route in self.application.routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None) or set()
            if isinstance(path, str) and "{" not in path and method in methods:
                found.append(path)
        return sorted(set(found))

    def path_named_after(self, fragments: tuple[str, ...], purpose: str) -> str:
        """The one route whose path carries one of `fragments`.

        Ambiguity stops rather than picks, the way `callable_named_after` does
        above: two candidates mean this cannot tell which one the ticket is
        about, and choosing would be the test deciding.
        """
        declared = sorted(set(self.paths("GET")) | set(self.paths("POST")))
        for fragment in fragments:
            matches = [path for path in declared if fragment in path.lower()]
            if len(matches) > 1:
                pytest.fail(
                    f"The mock platform declares more than one route whose path carries "
                    f"{fragment!r} ({matches}), so this cannot tell which one {purpose}. E0-14 "
                    "spells no URL, so naming one here would pin an interface the ticket leaves "
                    "open — say in the pull request which it is, and `MockPlatform` in "
                    "tests/conftest.py is the one place that changes."
                )
            if matches:
                return matches[0]
        pytest.fail(
            f"The mock platform declares no route whose path carries any of {list(fragments)} — "
            f"it declares {declared}. This is the endpoint that {purpose}, which E0-14's scope "
            "requires; if it is there under a path none of these fragments reaches, that is a "
            "defect in `MockPlatform` in tests/conftest.py rather than in the mock."
        )

    def discovery(self) -> dict[str, Any] | None:
        """The platform's OIDC discovery document, if it serves one."""
        for path in self.paths("GET"):
            if "openid-configuration" not in path:
                continue
            response = self.client.get(path)
            if response.status_code == 200:
                document = response.json()
                if isinstance(document, dict):
                    return document
        return None

    def endpoint(self, discovered: str, fragments: tuple[str, ...], purpose: str) -> str:
        """An endpoint path, from the discovery document if there is one."""
        document = self.discovery()
        if document:
            advertised = document.get(discovered)
            if isinstance(advertised, str) and advertised:
                return urlsplit(advertised).path or advertised
        return self.path_named_after(fragments, purpose)

    def jwks(self) -> dict[str, Any]:
        """The published key set, as JSON."""
        path = self.endpoint("jwks_uri", ("jwks", "keys"), "serves the platform's public keys")
        response = self.client.get(path)
        assert response.status_code == 200, (
            f"The JWKS endpoint `{path}` answered {response.status_code} rather than 200. E0-14's "
            "second acceptance criterion is that it serves a key that verifies an issued "
            "`id_token`, and a key set nobody can fetch verifies nothing."
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

        Takes a compact JWS string or an already-split one, so a test that has
        tampered with a token can hand over the string it produced rather than
        rebuilding the split. Verification is the arithmetic in `verify_rs256`
        above; this only supplies the key set.
        """
        signature = token if isinstance(token, JsonWebSignature) else split_jws(str(token))
        return verifying_key(signature, self.jwks())

    # -- launches ------------------------------------------------------------

    def offers(self) -> list[LaunchOffer]:
        """Every launch the platform's launch page offers.

        Found by serving rather than by path: a launch page is the page carrying
        a form whose fields are an OIDC third-party-initiated login request, and
        `target_link_uri` plus `login_hint` are the two that request must carry.
        Only `GET` routes with no path parameter are fetched, so nothing here can
        have a side effect.
        """
        offers: list[LaunchOffer] = []
        for path in self.paths("GET"):
            response = self.client.get(path)
            if response.status_code != 200:
                continue
            if "html" not in response.headers.get("content-type", "").lower():
                continue
            for form in forms_in(response.text):
                names = set(form["fields"]) | set(form["choices"])
                if not {"target_link_uri", "login_hint"} <= names:
                    continue
                for parameters in form_submissions(form):
                    offers.append(
                        LaunchOffer(
                            page=path,
                            posts_to=urljoin(f"http://testserver{path}", form["action"]),
                            method=form["method"],
                            parameters=parameters,
                        )
                    )
        return offers

    def require_offers(self) -> list[LaunchOffer]:
        offers = self.offers()
        assert offers, (
            "The mock platform serves no page carrying a form with `target_link_uri` and "
            f"`login_hint` fields. Pages fetched: {self.paths('GET')}. E0-14's scope asks for "
            "'a launch page that posts the form to the tool, so a browser-driven test can click "
            "through a realistic launch', and those two fields are what make that form an OIDC "
            "third-party-initiated login request rather than an arbitrary form."
        )
        return offers

    def mint(
        self,
        offer: LaunchOffer | None = None,
        *,
        state: str | None = None,
        nonce: str | None = None,
    ) -> SignedLaunch:
        """Drive one launch to the point a tool would receive the `id_token`.

        This is E0-14's seventh criterion — "a test can obtain a signed launch
        for an arbitrary seeded user and role without a browser" — and it is done
        by *being* the tool: taking the platform's initiation request, answering
        it with an authorization request the way a tool would, and reading the
        `id_token` out of what comes back. Nothing is called that a real tool
        would not call, so a launch minted here and a launch a browser produces
        are the same launch.
        """
        chosen = offer or self.require_offers()[0]
        request = dict(AUTHORIZATION_REQUEST_CONSTANTS)
        request["state"] = state if state is not None else secrets.token_urlsafe(24)
        request["nonce"] = nonce if nonce is not None else secrets.token_urlsafe(24)
        request["redirect_uri"] = chosen.parameters.get("target_link_uri", "")
        for name in ("login_hint", "lti_message_hint", "client_id", "lti_deployment_id"):
            value = chosen.parameters.get(name)
            if value:
                request[name] = value

        path = self.endpoint(
            "authorization_endpoint",
            ("auth",),
            "receives the tool's authorization request and answers with a signed `id_token`",
        )
        # POST where the route accepts it, GET otherwise. Which of the two a
        # tool uses is the tool's choice under OIDC, so the endpoint's own
        # declaration decides rather than this file.
        if path in self.paths("POST"):
            response = self.client.post(path, data=request)
        else:
            response = self.client.get(path, params=request)

        id_token, returned_state, posted_to = self.read_authorization_response(response, path)
        return SignedLaunch(
            offer=chosen,
            authorization_request=request,
            id_token=id_token,
            state=returned_state,
            posted_to=posted_to,
            signature=split_jws(id_token),
        )

    def read_authorization_response(
        self, response: Any, path: str
    ) -> tuple[str, str | None, str | None]:
        """Pull the `id_token` and the returned `state` out of what the platform sent.

        Both shapes are accepted — the `form_post` auto-submitting form the LTI
        security framework specifies, and a redirect carrying the values in its
        query or fragment — because which one the mock uses is not something
        E0-14 decides, and refusing the second would fail a platform that is
        merely making a different legal choice.
        """
        if response.status_code == 200:
            for form in forms_in(response.text):
                fields = form["fields"]
                if "id_token" in fields:
                    return fields["id_token"], fields.get("state"), form["action"]
        location = response.headers.get("location")
        if location:
            split = urlsplit(location)
            for blob in (split.query, split.fragment):
                pairs = parse_qs(blob)
                if "id_token" in pairs:
                    returned = pairs.get("state") or [None]
                    return pairs["id_token"][0], returned[0], location
        pytest.fail(
            f"The authorization endpoint `{path}` answered {response.status_code} with no "
            "`id_token` in a form and none in a redirect, so no launch was produced. Body begins "
            f"{response.text[:300]!r}. E0-14 issues 'a signed `id_token` carrying the LTI 1.3 "
            "core claims'; the LTI 1.3 security framework returns it by `form_post` to the "
            "tool's redirect URI."
        )


@pytest.fixture
def repo_root() -> Path:
    """The repository root, for the tests that sweep the whole tree."""
    return REPO_ROOT


@pytest.fixture
def mock_lms_dir() -> Path:
    """Where the mock platform must live (SPEC §13). Asserted by the test, not here."""
    return MOCK_LMS_DIR


@pytest.fixture
def mock_lms_service() -> str:
    """The Compose service name SPEC §7.2 gives the mock platform."""
    return MOCK_LMS_SERVICE


@pytest.fixture
def mock_platforms() -> Iterator[Callable[..., MockPlatform]]:
    """Start one or more independent mock platforms, and shut them all down after.

    A factory rather than a single instance because two of E0-14's criteria are
    about *two* platforms: issuer keys generated per run means a second start
    generates a second key, and a key set that verifies its own launches has to
    refuse someone else's. Neither is observable from one instance.
    """
    started: list[MockPlatform] = []

    def start(values: Mapping[str, str] | None = None) -> MockPlatform:
        platform = MockPlatform(values)
        started.append(platform)
        return platform

    try:
        yield start
    finally:
        for platform in reversed(started):
            platform.close()


@pytest.fixture
def mock_platform(mock_platforms: Callable[..., MockPlatform]) -> MockPlatform:
    """One mock platform, started fresh for this test. See `MockPlatform` above."""
    return mock_platforms()


@pytest.fixture
def signed_launch(mock_platform: MockPlatform) -> SignedLaunch:
    """One signed launch off the first seeded offer.

    E0-14's definition of done names this: "a reusable fixture that mints a
    signed launch — E1's launch-validation tests depend on it, so its interface
    matters". `mock_platform.mint(...)` is the interface; this fixture is the
    common case of it.
    """
    return mock_platform.mint()
