"""Sessions open and close, and one test's writes do not reach the next — E0-04.

Acceptance criterion 3: "The testcontainers fixture starts Postgres, applies
migrations, and tears down cleanly; a test that writes a row does not leak into
the next test." The definition of done names the two tests this module owes:
"one integration test proving the session dependency opens and closes a
transaction, and one asserting the rollback fixture isolates writes."

The second of those is a pair rather than a single test, and it has to be. A
test asserting that a row is *absent* passes when the row was never written,
when the fixture handed back a connection to the wrong database, and when the
test that was supposed to write it was never collected — `docs/MISTAKES.md`
entry 3, which is what a lone "the row is gone" assertion is made of. So one
test writes and proves the write landed, and the next reads and proves both that
the write is gone and that it is looking somewhere the write could have been.

**"Tears down cleanly" is not asserted here, and cannot honestly be.** The
container is torn down when the session ends, which is after the last test has
reported. What stands in for it is the `with` block in `postgres_container` —
teardown on the way out of a failing run as well as a passing one — and CI's own
exit status.

The dependency is found rather than named. E0-04 says `backend/app/db.py` holds
"a FastAPI dependency yielding a session per request" and does not say what it
is called, so pinning `get_session` or `get_db` here would turn the ticket's
silence into this suite's decision. What is *not* left open is the shape: a
dependency FastAPI can use is a generator function it can call with no arguments
of its own, and something that has to be handed a session is not one.
"""

import inspect
from collections.abc import Callable
from contextlib import suppress
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

# The fixtures hand back the `DatabaseUnderTest` named tuple defined in
# `tests/conftest.py` — `.superuser_url` and `.application_url`. Annotated `Any`
# rather than imported: a test module importing `conftest` by name works only
# because of where pytest puts `tests/` on `sys.path`, and a collection error is
# not a failing test.

DB_MODULE = "app.db"
DATABASE_URL_VARIABLE = "DATABASE_URL"

SELECT_ONE = "SELECT 1"
CONNECTION_IDENTITY = "SELECT current_database(), current_user"

# A table nothing else declares. Created inside the rolled-back transaction, so
# the pair below needs no cleanup of its own — which is the property under test.
CREATE_ISOLATION_CANARY = "CREATE TABLE e0_04_isolation_canary (note text NOT NULL)"
INSERT_ISOLATION_CANARY = "INSERT INTO e0_04_isolation_canary (note) VALUES (:note)"
SELECT_ISOLATION_CANARY = "SELECT note FROM e0_04_isolation_canary"
TABLE_EXISTS = "SELECT to_regclass(:name)"

ISOLATION_CANARY_TABLE = "e0_04_isolation_canary"
ISOLATION_CANARY_NOTE = "written-by-the-first-test-6c02f9"

# A table the migrated database certainly has, whatever this ticket's baseline
# migration creates — Alembic writes it itself.
ALEMBIC_VERSION_TABLE = "alembic_version"

# The parameter kinds a caller has to supply positionally. A dependency with one
# of these unfilled is not something FastAPI can resolve on its own.
POSITIONAL_PARAMETER_KINDS = (
    inspect.Parameter.POSITIONAL_ONLY,
    inspect.Parameter.POSITIONAL_OR_KEYWORD,
)

# Whether the writing half of the pair below actually ran. The reading half
# asserts an absence, and an absence is satisfied by the write never having
# happened — by a deselection, by a rename, by someone running the second test
# alone to reproduce something. This makes that case say so instead of passing.
_WRITER_RAN = False


def session_dependency_in(module: ModuleType) -> Callable[[], Any] | None:
    """The dependency that yields a session, whatever it is named.

    Structural, in the same spirit as `celery_application_in` in
    `tests/conftest.py`: a generator function — synchronous or asynchronous —
    that can be called with no arguments. FastAPI resolves a dependency by
    calling it, so a callable with a required positional parameter of its own is
    not one, and a plain function that returns a session is not "yielding a
    session per request" and has no teardown half to close it.

    The three conventional names are tried first only so that a module holding
    more than one generator does not make the choice arbitrary. Returns `None`
    rather than asserting, so the test does the asserting.
    """

    def usable(candidate: Any) -> bool:
        if not (inspect.isgeneratorfunction(candidate) or inspect.isasyncgenfunction(candidate)):
            return False
        for parameter in inspect.signature(candidate).parameters.values():
            unfilled = parameter.default is inspect.Parameter.empty
            if unfilled and parameter.kind in POSITIONAL_PARAMETER_KINDS:
                return False
        return True

    for name in ("get_session", "get_db", "get_db_session"):
        candidate = getattr(module, name, None)
        if candidate is not None and usable(candidate):
            return candidate
    for name in sorted(vars(module)):
        candidate = getattr(module, name, None)
        # Defined here, not imported into here: a generator this module happens
        # to have in scope is not a dependency this module offers.
        if usable(candidate) and getattr(candidate, "__module__", None) == module.__name__:
            return candidate
    return None


async def opened(generator: Any) -> Any:
    """The value a generator yields first, synchronous or asynchronous alike."""
    if hasattr(generator, "__anext__"):
        return await generator.__anext__()
    return next(generator)


async def closed(generator: Any) -> None:
    """Run the dependency's teardown the way FastAPI does — by asking for the next value."""
    if hasattr(generator, "__anext__"):
        with suppress(StopAsyncIteration):
            await generator.__anext__()
    else:
        with suppress(StopIteration):
            next(generator)


async def resolve(value: Any) -> Any:
    """`value`, awaited if it needs awaiting.

    So that one test covers a synchronous `Session` and an `AsyncSession` alike.
    E0-04 does not say which, and SPEC §13 says only "SQLAlchemy engine/session",
    so a test that worked with one and errored on the other would be settling a
    question the ticket leaves open.
    """
    return await value if inspect.isawaitable(value) else value


@pytest.fixture
def database_module(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    migrated_database: Any,
    import_app_module: Callable[[str], ModuleType | None],
) -> ModuleType:
    """`app.db`, imported against the migrated container database.

    Imported through `import_app_module` because a module that builds an engine
    out of `Settings` reads the environment once, at import time, and
    `sys.modules` keeps the answer for the rest of the session.
    """
    monkeypatch.setenv(DATABASE_URL_VARIABLE, migrated_database.application_url)
    module = import_app_module(DB_MODULE)
    if module is None:
        pytest.fail(
            f"`{DB_MODULE}` does not exist. E0-04 ships it at `backend/app/db.py` (SPEC §13) "
            "with the engine, the session factory, the declarative `Base`, and the FastAPI "
            "dependency that yields a session per request."
        )
    return module


async def test_the_session_dependency_opens_and_closes_a_transaction(
    database_module: ModuleType,
    migrated_database: Any,
) -> None:
    """The definition of done's first named test.

    Four things are asserted about one dependency, and they are one behaviour:
    it hands out a live session against the configured database, that session
    has a transaction open, two calls are two sessions, and the transaction is
    gone once the dependency finishes.

    **Why the identity check is not padding.** A dependency holding a literal
    URL, or one that fell back to a default, would satisfy every other assertion
    here on a developer's machine with the Compose stack running — while
    exercising a database this test never migrated. Asking the connection which
    database and which role it is on is what ties the assertions to the
    container, and it doubles as the check that the application connects as the
    application role and not as the bootstrap superuser (ADR 0009).

    **Why closing is asserted after the generator is exhausted, rather than by
    watching for a commit.** Whether a request-scoped session commits, rolls
    back, or leaves both to the caller is not something E0-04 settles, and a
    test that required one of those would settle it. What the ticket does
    require is that the transaction not outlive the request: a dependency that
    yields and never resumes leaks a connection per request, and the pool empties
    under load a long way from the code that caused it.
    """
    dependency = session_dependency_in(database_module)
    assert dependency is not None, (
        f"`{DB_MODULE}` exposes no zero-argument generator function that yields a session, so "
        "there is nothing for `Depends(...)` — or for this test — to open a session with. "
        "E0-04 ships a FastAPI dependency yielding a session per request."
    )

    generator = dependency()
    session = await opened(generator)

    value = (await resolve(session.execute(text(SELECT_ONE)))).scalar_one()
    assert value == 1, f"The session answered {value!r} to `{SELECT_ONE}`, so it is not usable."

    configured = urlsplit(migrated_database.application_url)
    expected = (configured.path.lstrip("/"), configured.username)
    actual = tuple((await resolve(session.execute(text(CONNECTION_IDENTITY)))).one())
    assert actual == expected, (
        f"The dependency's session is on database {actual[0]!r} as role {actual[1]!r}, not on "
        f"the container this test migrated ({expected[0]!r} as {expected[1]!r}). Either it "
        f"ignored {DATABASE_URL_VARIABLE}, or it connected as an identity the application is "
        "not supposed to hold."
    )

    assert session.in_transaction(), (
        "The session has no transaction open after issuing a statement, so there is nothing "
        "for the end of the request to close and no unit of work for a handler to commit."
    )

    second = dependency()
    other = await opened(second)
    assert other is not session, (
        "Two calls to the dependency handed back the same session object. It is a session "
        "*per request*: sharing one across requests shares an open transaction, so one "
        "request's uncommitted work becomes visible to another and one request's rollback "
        "discards another's."
    )
    await closed(second)

    await closed(generator)

    assert not session.in_transaction(), (
        "The session still holds an open transaction after the dependency finished. Nothing "
        "closes it now: the connection stays checked out of the pool for the life of the "
        "process, and the rows the request touched stay locked."
    )


def test_a_write_through_the_rollback_fixture_lands_within_the_test(db_session: Any) -> None:
    """The writing half of the isolation pair, which has to prove it wrote.

    On its own this asserts something nearly trivial — an insert is readable by
    the transaction that made it. Its job is to make the next test mean
    something: if the write silently did not happen, "the row is gone" is true
    for the wrong reason, and the pair would report isolation that nothing had
    tested.

    The table is created here rather than by a migration or a fixture, and that
    is the sharper version of the criterion. Postgres keeps DDL inside the
    transaction, so if `db_session` really rolls back, the table goes with the
    row — and the next test can assert against a name that could not have
    survived by any other route.
    """
    global _WRITER_RAN

    db_session.execute(text(CREATE_ISOLATION_CANARY))
    db_session.execute(text(INSERT_ISOLATION_CANARY), {"note": ISOLATION_CANARY_NOTE})

    written = list(db_session.execute(text(SELECT_ISOLATION_CANARY)).scalars())
    assert written == [ISOLATION_CANARY_NOTE], (
        f"The row written in this test reads back as {written!r}. Until a write lands, the "
        "test below cannot tell isolation from nothing having happened."
    )

    _WRITER_RAN = True


def test_the_next_test_cannot_see_what_the_previous_one_wrote(db_session: Any) -> None:
    """Criterion 3's second half: per-test isolation, asserted from the other side.

    Two guards stand in front of the assertion, and both exist because this is
    an absence:

      - the writing test above must have run, or there was never anything to
        leak and this passes on an empty premise;
      - this session must be able to see the schema at all, checked against
        `alembic_version`. A fixture that handed back a connection to some other
        database would otherwise report perfect isolation while looking at the
        wrong server.
    """
    assert _WRITER_RAN, (
        "The test that writes the canary row did not run before this one, so there is "
        "nothing here to have leaked and this test would pass against a fixture that "
        "isolates nothing. Run the module, not this test on its own."
    )

    visible = db_session.execute(text(TABLE_EXISTS), {"name": ALEMBIC_VERSION_TABLE}).scalar()
    assert visible is not None, (
        f"This session cannot see `{ALEMBIC_VERSION_TABLE}`, so it is not looking at the "
        "migrated database — and an assertion that a canary table is absent would pass for "
        "that reason rather than because the previous test was rolled back."
    )

    leaked = db_session.execute(text(TABLE_EXISTS), {"name": ISOLATION_CANARY_TABLE}).scalar()
    assert leaked is None, (
        f"`{ISOLATION_CANARY_TABLE}` still exists, so the previous test's transaction was "
        "committed or left open rather than rolled back. Per-test isolation is what keeps a "
        "suite's result independent of the order it runs in; without it, a test passes or "
        "fails depending on what ran before it."
    )
