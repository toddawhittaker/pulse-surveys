"""Sessions open and close, and one test's writes do not reach the next — E0-04.

Acceptance criterion 3: "The testcontainers fixture starts Postgres, applies
migrations, and tears down cleanly; a test that writes a row does not leak into
the next test." The definition of done names the two tests this module owes:
"one integration test proving the session dependency opens and closes a
transaction, and one asserting the rollback fixture isolates writes."

The second of those asserts an *absence*, and an absence passes when the row was
never written, when the fixture handed back a connection to the wrong database,
and when whatever was supposed to write it never ran — `docs/MISTAKES.md` entry 3,
which is what a lone "the row is gone" assertion is made of. So the write is made,
read back, and only then rolled back, and the reader proves it is looking
somewhere the write could have been before it says the write is gone.

**It used to be two tests, and that shape was incorrect.** The writing half set a
module global and the reading half asserted it, which makes the pair a statement
about the order pytest happens to run them in. CI runs `pytest-xdist -n 4` under
the default load distribution, which gives no same-worker and no ordering
guarantee, so the two halves can land on different workers — and E3-05's added
tests reshuffled the distribution enough to split them. The module went red in CI
and green locally, which is this repository's known reshuffle failure shape: the
repair is the test's own declaration, never the change that exposed it.

So the pair is one test now. It drives the `db_session` fixture's **own generator
function** — found through the plugin registry, called with the fixtures it
declares, and resumed to run the very `finally` block that closes the session and
rolls the transaction back — twice in a row: write and read back in the first
lifetime, and look for what was written in the second. Nothing is copied out of
`tests/fixtures/database.py`, deliberately: a test that re-implemented the
fixture's body would be asserting that SQLAlchemy rolls back, not that this
project's isolation fixture does (`docs/MISTAKES.md` entry 19). Both of the old
guards survive — the write is required to read back before the teardown runs, and
the second lifetime is required to see `alembic_version` before it is allowed to
say the canary is gone — and the premise the module global used to stand in for is
now established inside the same test, where nothing can deselect it.

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
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

# The fixtures hand back the `DatabaseUnderTest` named tuple defined in
# `tests/fixtures/database.py` — `.superuser_url` and `.application_url`.
# Annotated `Any` rather than imported: a test module importing a fixtures module
# by name works only because of where pytest puts `tests/` on `sys.path`, and a
# collection error is not a failing test.

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

# Where the rollback fixture is declared, and what it is called there. Reached
# through pytest's own plugin registry rather than with an `import` statement:
# this module's docstring already refuses that import — "a test module importing a
# fixtures module by name works only because of where pytest puts `tests/` on
# `sys.path`, and a collection error is not a failing test" — and the rule holds
# just as well for the fixture as for the named tuple it hands back.
#
# The name is `tests/conftest.py`'s own spelling in `pytest_plugins`, which is what
# pytest registers the module under.
DATABASE_FIXTURES_PLUGIN = "fixtures.database"
ROLLBACK_FIXTURE = "db_session"


def session_dependency_in(module: ModuleType) -> Callable[[], Any] | None:
    """The dependency that yields a session, whatever it is named.

    Structural, in the same spirit as `celery_application_in` in
    `tests/fixtures/repo.py`: a generator function — synchronous or asynchronous —
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


def the_rollback_fixtures_own_generator(request: pytest.FixtureRequest) -> Callable[..., Any]:
    """The generator function `db_session` is declared as, not a copy of its body.

    Reached rather than reimplemented, and that is the whole reason this test can
    say anything: the subject is *this project's* isolation fixture, so a test that
    wrote its own connect-begin-rollback would be asserting that SQLAlchemy rolls
    back and would stay green through any change to the fixture
    (`docs/MISTAKES.md` entry 19).

    **What `@pytest.fixture` hands back has changed shape across pytest versions**
    — the decorated function itself on older ones, a definition object with the
    function inside it on 8.4 and after — so each known accessor is tried in turn
    and whichever produces a generator function wins. A version that produces none
    fails here, naming what was found, rather than erroring somewhere further in.

    Every failure below is a `pytest.fail` in a helper called from a test body, so
    an environment where the plugin is not registered reads as this test's own red
    (`docs/MISTAKES.md` entry 44).
    """
    module = request.config.pluginmanager.get_plugin(DATABASE_FIXTURES_PLUGIN)
    if module is None:
        module = sys.modules.get(DATABASE_FIXTURES_PLUGIN)
    if module is None:
        pytest.fail(
            f"pytest has no plugin registered as `{DATABASE_FIXTURES_PLUGIN}`, so this test "
            "cannot reach the fixture it is about. `tests/conftest.py` lists it in "
            "`pytest_plugins` under exactly that name."
        )

    declared = getattr(module, ROLLBACK_FIXTURE, None)
    if declared is None:
        pytest.fail(
            f"`{DATABASE_FIXTURES_PLUGIN}` declares no `{ROLLBACK_FIXTURE}`. E0-04's definition "
            "of done owes 'one asserting the rollback fixture isolates writes', and that "
            "fixture is the thing being asserted about."
        )

    candidates: list[Any] = []
    accessor = getattr(declared, "_get_wrapped_function", None)
    if callable(accessor):
        candidates.append(accessor())
    candidates.append(getattr(declared, "__wrapped__", None))
    candidates.append(declared)
    for candidate in candidates:
        if candidate is not None and inspect.isgeneratorfunction(candidate):
            return candidate

    pytest.fail(
        f"`{DATABASE_FIXTURES_PLUGIN}.{ROLLBACK_FIXTURE}` is {declared!r}, and none of the "
        "accessors this test knows about got a generator function out of it. The fixture "
        "yields a session and rolls its transaction back afterwards, so a non-generator here "
        "means either the fixture stopped having a teardown half — which is the property "
        "under test — or pytest has changed how a fixture is stored again, in which case the "
        "accessor list in `the_rollback_fixtures_own_generator` is the one line that changes."
    )


@contextmanager
def a_rollback_session(request: pytest.FixtureRequest) -> Iterator[Any]:
    """One whole lifetime of the real `db_session` fixture, set up and torn down.

    The arguments are filled from the fixture's own signature through
    `request.getfixturevalue`, so a parameter added to it later is supplied rather
    than turning this into a `TypeError` about a test (`docs/MISTAKES.md` entry 22).

    The exit resumes the generator, which is exactly what pytest does at teardown:
    it runs the `finally` block that closes the session, rolls the transaction back
    and closes the connection. Nothing here decides *how* the fixture isolates —
    only that its own teardown has run.
    """
    make = the_rollback_fixtures_own_generator(request)
    arguments = [request.getfixturevalue(name) for name in inspect.signature(make).parameters]
    generator = make(*arguments)
    session = next(generator)
    try:
        yield session
    finally:
        with suppress(StopIteration):
            next(generator)


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


def test_a_write_in_one_rollback_session_is_gone_from_the_next(
    request: pytest.FixtureRequest,
) -> None:
    """Criterion 3's second half: per-test isolation, in one test rather than two.

    "A test that writes a row does not leak into the next test." Two lifetimes of
    the real `db_session` fixture, one after the other, driven through the
    fixture's own generator so the teardown that runs between them is the fixture's
    own and not this test's idea of it.

    **Both of the old pair's guards are here, and neither is padding.** The write
    is read back *before* the teardown, so "the table is gone" cannot be true
    because nothing was ever written — which is the premise the module global used
    to stand in for, established now inside the same test where nothing can
    deselect it. And the second lifetime has to see `alembic_version` before it is
    allowed to say the canary is absent, because a fixture handing back a
    connection to some other database would otherwise report perfect isolation
    while looking at the wrong server (`docs/MISTAKES.md` entry 3, both times).

    **Why it is one test now.** As a pair it was a statement about the order pytest
    happened to run two functions in, and CI runs `pytest-xdist -n 4` under the
    default load distribution, which promises neither an order nor a shared worker.
    E3-05's added tests reshuffled the distribution and split the pair, and the
    module went red in CI while staying green locally. The repair is the test's own
    declaration; the assertion it makes is unchanged.

    **The table is created inside the session rather than by a migration**, which
    is the sharper version of the criterion: Postgres keeps DDL inside the
    transaction, so if the fixture really rolls back then the table goes with the
    row, and the second lifetime asserts against a name that could not have
    survived by any other route.

    **The teardown is asserted to have happened**, not assumed. A `finally` that
    stopped rolling back would leave the canary committed and the second lifetime
    would find it; a `finally` that stopped running at all would leave the first
    transaction open, and an uncommitted table is invisible to a second connection
    for a reason that has nothing to do with isolation. Requiring the first
    session to be out of its transaction is what tells those two apart.
    """
    with a_rollback_session(request) as first:
        first.execute(text(CREATE_ISOLATION_CANARY))
        first.execute(text(INSERT_ISOLATION_CANARY), {"note": ISOLATION_CANARY_NOTE})

        written = list(first.execute(text(SELECT_ISOLATION_CANARY)).scalars())
        assert written == [ISOLATION_CANARY_NOTE], (
            f"The row written in this session reads back as {written!r}. Until a write lands, "
            "the second lifetime below cannot tell isolation from nothing having happened."
        )

    assert not first.in_transaction(), (
        "The first session still holds an open transaction after the fixture's own teardown "
        "ran, so nothing rolled anything back and the canary is merely invisible rather than "
        "gone. A second connection cannot see an uncommitted table either way, which is "
        "exactly why this is asserted here instead of being read off the absence below."
    )

    with a_rollback_session(request) as second:
        assert second is not first, (
            "Both lifetimes handed back the same session object, so the second is not a fresh "
            "one and 'the previous test's write is gone' is being asked of the transaction that "
            "made it."
        )

        visible = second.execute(text(TABLE_EXISTS), {"name": ALEMBIC_VERSION_TABLE}).scalar()
        assert visible is not None, (
            f"This session cannot see `{ALEMBIC_VERSION_TABLE}`, so it is not looking at the "
            "migrated database — and an assertion that a canary table is absent would pass for "
            "that reason rather than because the first lifetime was rolled back."
        )

        leaked = second.execute(text(TABLE_EXISTS), {"name": ISOLATION_CANARY_TABLE}).scalar()
        assert leaked is None, (
            f"`{ISOLATION_CANARY_TABLE}` still exists, so the first lifetime's transaction was "
            "committed rather than rolled back. Per-test isolation is what keeps a suite's "
            "result independent of the order it runs in; without it, a test passes or fails "
            "depending on what ran before it."
        )
