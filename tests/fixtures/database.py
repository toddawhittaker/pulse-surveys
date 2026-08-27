"""E0-04 — a real Postgres, with production's role shape, migrated once.

These fixtures are E0-04's own deliverable, so what they choose and what they
refuse to choose is written on each one. Two things are worth knowing before
using them:

  - **The container carries production's role shape**, a bootstrap superuser and
    a separate application role that cannot create a table, because
    [ADR 0009](../../docs/adr/0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)
    names this fixture as the owner of its own provisioning. Without it, tests
    pass under privileges no deployment has.
  - **The environment a migration runs under is assembled in one function**,
    `migration_environment` below, and it supplies what `migrations/env.py`
    reads and nothing besides: `DATABASE_URL` for the address, `DB_SUPERUSER`
    and `DB_SUPERUSER_PASSWORD` for the identity. It used to supply the
    container's coordinates under every spelling E0-04 left open, because that
    ticket named three candidate mechanisms and this file could not choose among
    them.
    [ADR 0012](../../docs/adr/0012-the-migration-environment-builds-its-own-superuser-connection.md)
    chose, and E0-37 item 7 deleted the rest: a fixture still setting
    `ALEMBIC_DATABASE_URL` would let an `env.py` written the rejected way pass
    this whole suite.
  - **The migration leaves the process environment as it found it.** Alembic runs
    in process here, and `migrations/env.py` is a documented reader of `.env`, so
    the upgrade would otherwise load a developer's whole file into `os.environ`
    for the rest of the session — a suite green on that machine and red in CI,
    which has no `.env`. `whole_environment_restored` is what stops it.
"""

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, NamedTuple
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from fixtures.repo import ALEMBIC_INI_PATH, BASE_COMPOSE_PATH, MIGRATIONS_DIR, load_compose

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

# **`pulse_app`, not a test-only name, and E0-10 is what changed it.** E0-04 chose
# `pulse_test_app` when no grant existed anywhere for the name to be wrong about;
# from E0-10 on, every grant in the schema belongs to `pulse_app` — the name
# `.env.example` gives `DB_APP_USER` and the name the migration establishes — so a
# fixture connecting as anything else holds nothing, and `application_engine`
# stops being able to tell a missing grant from a present one. That is precisely
# the failure this fixture exists to prevent: "tests that pass under privileges
# production does not have", now in its mirror image.
#
# It works because the order here is the Compose stack's order exactly:
# `provision_application_role` creates the role before any migration runs, as
# `scripts/db-init` does at `initdb`, and E0-10's migration guards its
# `CREATE ROLE` with a `pg_roles` lookup and applies its `ALTER`/`GRANT`/`REVOKE`
# unconditionally — which is the ticket's "Reconcile first" requirement, asserted
# by `test_alembic_upgrade_head_succeeds_where_the_roles_already_exist`.
TEST_APP_USER = "pulse_app"
TEST_APP_CREDENTIAL = "test-only-app-4b8e0257"

# The Care role, provisioned here for the same reason and by the same route as
# the application role. `scripts/db-init/02-care-role.sh` creates it with a login
# and a password on a Compose volume; a testcontainers Postgres runs no init hook,
# so this file is its provisioning (ADR 0009's table gives this fixture its own
# row). The E0-10 migration creates the role too, guarded, and writes every
# privilege it holds — the script and this fixture only hand it a way to log in,
# which a migration cannot do without keeping a password in the repository.
TEST_CARE_USER = "pulse_care"
TEST_CARE_CREDENTIAL = "test-only-care-71c3f2ad"

TEST_DATABASE = "pulse_test"

DATABASE_URL_VARIABLE = "DATABASE_URL"

# The Care connection's own URL. Not this file's invention and not a choice left
# open: `.env.example` documents it, and its comment says it is "read by
# `app.services.safety` and by nothing else".
CARE_DATABASE_URL_VARIABLE = "CARE_DATABASE_URL"


class DatabaseUnderTest(NamedTuple):
    """One database in the test container, addressed as each of the three roles.

    All three URLs name the same database on the same server. Which one a caller
    reaches for is the whole subject of ADR 0009 and ADR 0001: migrations and
    bootstrap use `superuser_url`, everything the application does uses
    `application_url`, and `care_url` is the one connection in the cluster that
    can execute the audited reveal (SPEC §6.2). The third arrived with E0-10, and
    `.env.example` documents its variables as `CARE_DATABASE_URL`, `DB_CARE_USER`
    and `DB_CARE_PASSWORD`.
    """

    superuser_url: str
    application_url: str
    care_url: str


def container_url(container: Any, *, username: str, credential: str, database: str) -> str:
    """A `postgresql+psycopg://` URL for one role against one database."""
    host = container.get_container_host_ip()
    port = container.get_exposed_port(POSTGRES_CONTAINER_PORT)
    return f"postgresql+psycopg://{username}:{credential}@{host}:{port}/{database}"


def migration_environment(database: DatabaseUnderTest) -> dict[str, str]:
    """Exactly what `migrations/env.py` reads to reach `database`, and nothing besides.

    **It used to be four entries wider, and E0-37 item 7 is why they are gone.**
    E0-04 left the mechanism open between a `Settings` field, an Alembic-only
    variable and something `env.py` assembles from the parts, so this function
    set the container's coordinates under every spelling those three could
    read — `ALEMBIC_DATABASE_URL`, and `DB_APP_USER`, `DB_APP_PASSWORD` and
    `DB_NAME` for a connection assembled by hand.
    [ADR 0012](../../docs/adr/0012-the-migration-environment-builds-its-own-superuser-connection.md)
    then chose: the address comes from `DATABASE_URL` and the identity from
    `DB_SUPERUSER` and `DB_SUPERUSER_PASSWORD`, and no new variable is
    introduced anywhere.

    **Keeping the hedge after that decision is what made it a hedge.** An
    `env.py` rewritten to read `ALEMBIC_DATABASE_URL` would pass this entire
    integration suite while being a variable `.env.example` cannot document:
    [ADR 0008](../../docs/adr/0008-env-has-two-readers-and-the-database-credential-is-split.md)
    accepts an entry only where a `Settings` field resolves it or a Compose file
    interpolates it, and `env.py` is neither reader. That is the alternative ADR
    0012 rejected by name, and this fixture was the last thing still making it
    look workable.

    `DATABASE_URL` is set to the *application* role, exactly as it is in
    production. An `env.py` that uses it to connect will fail to create a table,
    which is the failure ADR 0009 exists to keep visible.
    """
    superuser = urlsplit(database.superuser_url)
    return {
        DATABASE_URL_VARIABLE: database.application_url,
        "DB_SUPERUSER": superuser.username or "",
        "DB_SUPERUSER_PASSWORD": superuser.password or "",
    }


def application_environment(database: DatabaseUnderTest) -> dict[str, str]:
    """Every variable an `app.*` module could need to reach `database` at run time.

    An over-supply, and since E0-37 item 7 the only one left in this file.
    `migration_environment` above made the same choice for the same reason one
    ticket earlier, until ADR 0012 settled which variables Alembic reads and the
    other spellings were deleted; the question *this* one is hedging against is
    still open. `.env.example` gives the Care connection a URL of its own *and* a
    user/password pair, and `app.services.safety` could reasonably read either —
    a whole `CARE_DATABASE_URL`, or the pair against the address in
    `DATABASE_URL`, which is the shape ADR 0012 chose for Alembic. Supplying only
    one would make that choice for the implementer by failing the other, so both
    are set and they agree.

    `DATABASE_URL` names the application role and `CARE_DATABASE_URL` names the
    Care role, never each other and never the superuser — `.env.example` calls
    pointing both at one role "the separation undone in one line", and a fixture
    that did it would test the separation against a database that does not have
    one.
    """
    application = urlsplit(database.application_url)
    care = urlsplit(database.care_url)
    return {
        DATABASE_URL_VARIABLE: database.application_url,
        CARE_DATABASE_URL_VARIABLE: database.care_url,
        "DB_APP_USER": application.username or "",
        "DB_APP_PASSWORD": application.password or "",
        "DB_CARE_USER": care.username or "",
        "DB_CARE_PASSWORD": care.password or "",
        "DB_NAME": care.path.lstrip("/"),
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


@contextmanager
def whole_environment_restored() -> Iterator[None]:
    """Put `os.environ` back exactly as it was afterwards, names added included.

    `environment` above restores the names it was handed. This one restores every
    name there is, because what has to be undone here was not set by this file and
    cannot be listed by it.

    **`backend/migrations/env.py` is a documented third reader of `.env`** — its
    own module docstring says so, "This file is the third reader of `.env`, after
    `Settings` and the Compose files" — and it calls `load_dotenv` on the
    repository root's `.env` at import. `migrated_database` below runs Alembic
    **in process**, so that import loads a developer's whole `.env` into
    `os.environ`, and without this it stays there for the rest of the pytest
    session: `ENVIRONMENT=development` among everything else in the file.

    A session that inherits a developer's `.env` that way passes locally and fails
    in CI, which has no `.env` file at all. That is not hypothetical: it is what
    E1-10's course-number band tests did, and the difference they turned on was
    whether `ENVIRONMENT` was set — absent, the registration-address rules are in
    force and the mock's own cleartext roster address is refused.

    Which names the file holds is a developer's choice rather than this suite's,
    so the whole mapping is snapshotted and the difference put back: names the
    body added are removed, and names it changed are set back to what they were.
    """
    saved = dict(os.environ)
    try:
        yield
    finally:
        for name in [name for name in os.environ if name not in saved]:
            del os.environ[name]
        for name, value in saved.items():
            if os.environ.get(name) != value:
                os.environ[name] = value


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


def provision_care_role(superuser_url: str) -> None:
    """Create the role the Care queue connects as, as `scripts/db-init` does.

    The counterpart to `provision_application_role` above, and it mirrors
    `scripts/db-init/02-care-role.sh` line for line in what it does *and* in what
    it refuses to do: a login, and **no grant of any kind**. Every privilege
    `pulse_care` holds is written by the E0-10 migration, which is the one
    mechanism that runs in all four environments ADR 0009's table lists; a
    fixture that granted anything here would be a second place the grant model
    lives, and the §4.1 assertions would be measuring it rather than the
    migration.

    No `GRANT CONNECT` either, and that is the script's choice rather than an
    omission: Postgres grants `CONNECT` to `PUBLIC` by default, so the role can
    reach the database without one, and the E0-10 grants are what decide what it
    can do once there.
    """
    from sqlalchemy import create_engine, text

    create_role = (
        f'CREATE ROLE "{TEST_CARE_USER}" LOGIN'
        f" PASSWORD '{TEST_CARE_CREDENTIAL}'"
        " NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
    )

    engine = create_engine(superuser_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(text(create_role))
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
    """The container's database, with all three roles, before any migration runs.

    The two runtime roles are created *before* the migration, which is the
    Compose stack's order exactly — `initdb` runs `scripts/db-init` against an
    empty data directory, and the migration meets roles that already exist. E0-10
    requires it to tolerate that (`CREATE ROLE` guarded by a `pg_roles` lookup,
    the `ALTER`/`GRANT`/`REVOKE` applied unconditionally), so this ordering is
    also what exercises the requirement rather than working around it.
    """
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
        care_url=container_url(
            postgres_container,
            username=TEST_CARE_USER,
            credential=TEST_CARE_CREDENTIAL,
            database=TEST_DATABASE,
        ),
    )
    provision_application_role(urls.superuser_url, TEST_DATABASE)
    provision_care_role(urls.superuser_url)
    return urls


@pytest.fixture(scope="session")
def migrated_database(provisioned_database: DatabaseUnderTest) -> DatabaseUnderTest:
    """`alembic upgrade head`, applied once for the whole session.

    **The process environment is restored around the upgrade**, not only the three
    names `migration_environment` sets. Alembic runs here in process, which imports
    `backend/migrations/env.py`, which loads the repository's `.env` — so anything
    in a developer's file would otherwise be left in `os.environ` for every test
    that ran afterwards. `whole_environment_restored` above has the incident.
    """
    from alembic import command

    with whole_environment_restored(), environment(migration_environment(provisioned_database)):
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
    cheaper than a second container, and roles are cluster-wide, so all three
    URLs still name the three roles ADR 0009 and ADR 0001 separate.
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
            care_url=container_url(
                postgres_container,
                username=TEST_CARE_USER,
                credential=TEST_CARE_CREDENTIAL,
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
) -> Iterator[Callable[[DatabaseUnderTest], Any]]:
    """Point Alembic at one database and hand back a `Config` to run commands with.

    The commands stay in the test — `command.upgrade`, `command.check` — because
    which one is being run is the subject of the test that runs it, and a
    fixture that ran them would move the assertion's verb into this file.

    **The environment is restored around the test, not only around the names set
    here.** The command the test runs executes `migrations/env.py`, which loads the
    repository's `.env` into `os.environ`; `monkeypatch` cannot undo that, because
    it only knows the names it set itself. Same hazard as `migrated_database`, in
    the second place that faces it (`docs/MISTAKES.md` entry 13).
    """

    def prepare(database: DatabaseUnderTest) -> Any:
        for name, value in migration_environment(database).items():
            monkeypatch.setenv(name, value)
        return alembic_config()

    with whole_environment_restored():
        yield prepare


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
