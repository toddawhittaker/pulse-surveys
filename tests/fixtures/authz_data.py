"""Rows a *second connection* can see, and the chokepoint that reads them.

E0-10's `committed_rows` and `care_service_environment` exist for the one thing
the rest of these fixtures cannot do — `app.services.safety` opens its **own**
connection from `CARE_DATABASE_URL`, so it sees nothing written inside
`db_session`'s transaction, and a test that calls it needs committed rows and an
environment pointing at this container. The Care role itself is provisioned
beside the application role in `fixtures/database.py`, mirroring
`scripts/db-init/02-care-role.sh`: a login and no grant.

E0-26 item 1 adds `care_connections`, a `pulse_care` connection whose transaction
the test controls.

E0-11 adds two, and one of them is unlike everything else here. `authz` reaches
the authorization chokepoint **by name**: E0-11's surface was settled before any
code was written, so there is nothing to discover, and the class exists only to
turn an absent module or an absent symbol into a failed assertion instead of a
collection error. `application_session` is a session on the connection production
serves requests over — `pulse_app`, holding only what the migrations grant it —
because from E0-11 on, "the resolver could read that" is a claim about a grant
and not only about a query.
"""

import importlib
from collections.abc import Callable, Iterator
from contextlib import suppress
from types import ModuleType
from typing import Any

import pytest

from fixtures.database import TEST_CARE_USER, DatabaseUnderTest, application_environment
from fixtures.supervision import _GRAPH_INTEGER_COUNTERS, SupervisionGraph, seed_row

# ---------------------------------------------------------------------------
# E0-10 — rows a *second connection* can see, and the environment that points
# `app.services.safety` at this container.
# ---------------------------------------------------------------------------


class CommittedRows:
    """Seeding for a service that opens its own connection, undone when the test ends.

    Every other database fixture here writes inside `db_session`'s transaction and
    rolls it back, which is the right default and is useless for one case: a
    service that connects for itself sees none of it. `app.services.safety` is
    that case — `CARE_DATABASE_URL` is a second connection by design (ADR 0001:
    "the connection pool is bound to the service module"), so a test that calls
    `reveal_identity` has to hand it committed rows or it is testing a reveal of
    nothing.

    So this commits, and the fixture below removes afterwards **whatever appeared**
    rather than whatever it wrote. That difference is not tidiness: the service's
    own audit row is written on its connection, inside its transaction, and no
    amount of bookkeeping on this side would know its key. A snapshot of every
    single-key table before and after does.
    """

    def __init__(self, session: Any, tables: dict[str, Any]) -> None:
        self.session = session
        self.tables = tables
        self.graph = SupervisionGraph(session, tables)

    def seed(self, name: str, chain: dict[str, Any] | None = None, **overrides: Any) -> Any:
        """One row of `name`, with its ancestors. Not visible elsewhere until `commit`."""
        return seed_row(self.session, self.tables, name, chain, **overrides)

    def commit(self) -> None:
        """Make everything seeded so far visible to every other connection."""
        self.session.commit()


def keyed_tables(tables: dict[str, Any]) -> list[Any]:
    """Every declared table with exactly one primary key column, parents first.

    Sorted by dependency so the caller can delete in reverse and never orphan a
    row. `MetaData.sorted_tables` is what does the sorting — the metadata is
    reached through any one table rather than passed in, because every table here
    comes from the same `Base.metadata`. A self-referential table —
    `role_assignment` — is safe inside one statement: Postgres queues
    referential-integrity checks as after-row triggers and fires them at the end
    of the statement, so a parent and its child leave together.
    """
    if not tables:
        return []
    ordered = next(iter(tables.values())).metadata.sorted_tables
    return [table for table in ordered if len(list(table.primary_key.columns)) == 1]


def row_keys(connection: Any, tables: list[Any]) -> dict[str, set[Any]]:
    """The primary key of every row in each of `tables`, right now."""
    from sqlalchemy import select

    found: dict[str, set[Any]] = {}
    for table in tables:
        key = next(iter(table.primary_key.columns))
        found[table.name] = {row[0] for row in connection.execute(select(key))}
    return found


def delete_rows_added_since(engine: Any, tables: list[Any], before: dict[str, set[Any]]) -> None:
    """Remove every row that appeared since `before` was taken, children first."""
    from sqlalchemy import delete, select

    with engine.begin() as connection:
        for table in reversed(tables):
            key = next(iter(table.primary_key.columns))
            present = {row[0] for row in connection.execute(select(key))}
            added = present - before.get(table.name, set())
            if added:
                connection.execute(delete(table).where(key.in_(list(added))))


@pytest.fixture
def committed_rows(
    migrated_engine: Any, metadata_tables: dict[str, Any]
) -> Iterator[CommittedRows]:
    """`CommittedRows` on the migrated database, with the database left as it was found.

    The teardown is a diff rather than a rollback, so it also removes what the
    *service under test* wrote — which for E0-10 is the audit row every reveal
    leaves, on a connection this fixture never sees. A test that leaks a row here
    would fail somebody else's non-vacuity guard three tickets from now, which is
    the expensive kind of flake.
    """
    from sqlalchemy.orm import Session

    _GRAPH_INTEGER_COUNTERS.clear()
    tables = keyed_tables(metadata_tables)
    with migrated_engine.connect() as probe:
        before = row_keys(probe, tables)

    connection = migrated_engine.connect()
    session = Session(bind=connection)
    try:
        yield CommittedRows(session, metadata_tables)
    finally:
        session.close()
        connection.close()
        delete_rows_added_since(migrated_engine, tables, before)


@pytest.fixture
def care_service_environment(
    monkeypatch: pytest.MonkeyPatch,
    configured_env: dict[str, str],
    migrated_database: DatabaseUnderTest,
) -> dict[str, str]:
    """Point an `app.*` import at this container, as the application and as Care.

    `configured_env` first, so every documented variable has a value and
    `Settings()` constructs; then the database variables are overwritten with the
    container's, because `.env.example`'s placeholders name the Compose service
    `db` and resolve to nothing here.

    `migrated_database` rather than `provisioned_database`: the Care role can log
    in from the moment the fixture creates it, and it can *do* nothing until the
    E0-10 migration grants it, so a service test against an unmigrated database
    would be measuring the wrong refusal.
    """
    values = application_environment(migrated_database)
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


# ---------------------------------------------------------------------------
# E0-26 item 1 — a `pulse_care` connection whose transaction the test controls.
# ---------------------------------------------------------------------------


@pytest.fixture
def care_connections(
    migrated_database: DatabaseUnderTest, committed_rows: CommittedRows
) -> Iterator[Callable[[], Any]]:
    """Open `pulse_care` connections whose `BEGIN`, `COMMIT` and `ROLLBACK` are the test's.

    E0-26 item 1 is entirely about what a caller keeps when it rolls **its own**
    transaction back, so that transaction has to be a real top-level one. Every
    other database fixture in this file is deliberately the opposite: `db_session`
    opens a transaction outside the session and has the session join it with a
    savepoint, so a rollback there is a `ROLLBACK TO SAVEPOINT`. The ticket names
    that difference as the thing a wrong implementation is defeated by — "a caller
    that wraps the first call in a `SAVEPOINT` gives the row a subtransaction id" —
    so a test written on `db_session` would be measuring the near miss while
    believing it measured the rollback.

    **A factory rather than one connection**, because the ticket's "done when"
    requires the surviving audit row to be counted from a connection other than the
    one that rolled back. A count taken on the rolling-back connection is a
    statement about what that connection can see and says nothing about what
    survived, and that is the shape of the test this ticket replaces.

    `committed_rows` is depended on rather than used, and the reason is teardown
    order: fixtures are finalised in reverse of setup, so naming it here makes its
    diff-delete run *after* these connections are closed. A `pulse_care` connection
    still holding an uncommitted `audit_log` insert would otherwise block that
    delete on a row lock for as long as the run was willing to wait.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(migrated_database.care_url)
    opened: list[Any] = []

    def open_one() -> Any:
        connection = engine.connect()
        opened.append(connection)
        current = connection.execute(text("SELECT current_user")).scalar_one()
        connection.rollback()
        assert current == TEST_CARE_USER, (
            f"A connection opened on `care_url` authenticates as {current!r} rather than as "
            f"`{TEST_CARE_USER}`. Every refusal a test drives over this connection is supposed to "
            "be attributable to what the Care role may do, and a connection authenticating as "
            "something else would satisfy a refusal test whatever the migration granted — or, if "
            "it were the bootstrap superuser, would satisfy the permitted half and the refused "
            "half at once."
        )
        return connection

    try:
        yield open_one
    finally:
        # Suppressed rather than raised: a connection left inside an aborted
        # transaction is an ordinary outcome of a test whose subject is a refusal,
        # and a teardown that raised would replace the test's own failure with its
        # own.
        for connection in opened:
            with suppress(Exception):
                connection.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# E0-11 — the authorization chokepoint, and the connection it has to work over.
# ---------------------------------------------------------------------------

# SPEC §13 puts the chokepoint here and E0-11's scope repeats the path:
# "`backend/app/services/authz.py` with the interface every caller uses".
AUTHZ_MODULE = "app.services.authz"


class AuthzModule:
    """E0-11's chokepoint, reached by name, with a clear failure when it is absent.

    **Nothing here is discovered, which is what makes it unlike
    `SectionCodeService` above.** E0-07 named a file and none of its callables, so
    that fixture hunts for them by name fragment. E0-11's surface was settled in
    the ticket before any code was written — `AuthzError`,
    `CareIsNotComposableError`, `OutOfPurviewError`, `LmsOwnedWriteRefused`,
    `Purview`, `ActorScope`, `LMS_OWNED_TABLES`, `own_grant`, `resolve_scope`,
    `holds_care`, `transitive_purview`, `guard_write`, `raw_comments_permitted`
    and `scoped_reader` — so a lookup here transcribes that contract rather than
    guessing at one, and a name this cannot find is a deliverable that is not
    there yet.

    **Its whole job is to keep that a failed assertion rather than a collection
    error.** `from app.services.authz import own_grant` at the top of a test
    module makes every test in the file uncollectable while the module is absent,
    and an uncollected test is not a red test: it reports as a broken suite rather
    than as a criterion nobody has met, and the two are fixed by different people.
    `import_app_module` above draws the same distinction for the same reason, and
    like it, a `ModuleNotFoundError` for some *other* module is re-raised
    untouched — a chokepoint that exists and imports something absent and one that
    was never written need different fixes.
    """

    def __init__(self) -> None:
        self._module: ModuleType | None = None

    @property
    def module(self) -> ModuleType:
        """`app.services.authz`, or a failure naming the missing file."""
        if self._module is None:
            try:
                self._module = importlib.import_module(AUTHZ_MODULE)
            except ModuleNotFoundError as failure:
                absent = failure.name
                if absent is None or not (
                    absent == AUTHZ_MODULE or AUTHZ_MODULE.startswith(f"{absent}.")
                ):
                    raise
                pytest.fail(
                    f"There is no `{AUTHZ_MODULE}` module. E0-11's scope puts the authorization "
                    "chokepoint in `backend/app/services/authz.py`: 'the single chokepoint every "
                    "entry point passes through — HTTP, Celery jobs, and the future MCP server' "
                    "(SPEC §13, and `CLAUDE.md`)."
                )
        return self._module

    def symbol(self, name: str) -> Any:
        """One name off the module's agreed surface, or a failure saying it is missing."""
        found = getattr(self.module, name, None)
        if found is None:
            defined = sorted(
                attribute for attribute in vars(self.module) if not attribute.startswith("_")
            )
            pytest.fail(
                f"`{AUTHZ_MODULE}` defines no `{name}` — it defines {defined}. That name is part "
                "of the interface E0-11 settled before any of it was written, so this is a "
                "missing deliverable rather than a rename to accommodate here. If it genuinely "
                "moved, say so in the pull request; `AuthzModule` in tests/fixtures/authz_data.py "
                "is the one place that changes."
            )
        return found

    def __getattr__(self, name: str) -> Any:
        """`authz.own_grant` and `authz.symbol("own_grant")` are the same lookup.

        Only reached for attributes this class does not define itself, so `module`
        and `symbol` above keep their meanings and everything else falls through
        to the contract.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        return self.symbol(name)


@pytest.fixture
def authz(configured_env: dict[str, str]) -> AuthzModule:
    """E0-11's chokepoint. See `AuthzModule` above for what it will and will not do.

    `configured_env` runs first so that every documented variable has a value
    before the import: `resolve_scope` reads the n-threshold from `Settings`
    (§4), and a module that builds one at import time would otherwise fail on
    whichever variable the machine running the suite happens not to have.
    """
    return AuthzModule()


@pytest.fixture
def application_session(
    migrated_database: DatabaseUnderTest, application_engine: Any
) -> Iterator[Any]:
    """A session on the connection the application actually serves requests over.

    `db_session` above connects as the bootstrap superuser, which is right for a
    fixture that has to seed rows and wrong for anything that asks what a read
    path can reach: a superuser passes every grant. From E0-10 on, `pulse_app`
    holds `SELECT` on the read views and on nothing else, so "the resolver read
    the assignment" is a claim about a grant, and it is only true over this
    session.

    Nothing seeded inside `db_session` is visible here — this is a second
    connection, and that transaction has not committed. Pair it with
    `committed_rows`, which is the fixture for exactly that.

    `migrated_database` is depended on and not used: `application_engine` is built
    from `provisioned_database`, which is the state *before* any migration, so
    without this a test could open this session against a database holding no
    views and no grants and read the absence as a refusal.
    """
    from sqlalchemy.orm import Session

    connection = application_engine.connect()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        connection.close()
