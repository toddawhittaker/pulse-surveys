"""The hourly moderation task releases its advisory lock — E6-05, work order decision 5a.

PR #293's re-check found it (a MEDIUM, fixed here): the sweep holds a Postgres
**session-level** advisory lock, which belongs to one server connection, while
production's session is bound to the *engine*. Every per-comment commit hands the
connection back to the pool, the next statement may check out a different one, and
the unlock can run on a connection that never held the lock. `pg_advisory_unlock`
then answers false, and the lock stays on the first connection, idle in the pool,
for good — every later sweep on any other connection finds it taken and does
nothing. Decision 5a's fix: `moderate_closed_windows` opens one connection and binds
the session to it, so the lock, the commits and the unlock share it.

**Driven through the task itself**, `app.jobs.tasks.moderate_closed_windows`, with
`app.db` re-imported against this container's application role
(`tests/fixtures/summary_job.py::summary_job_environment`) — the session factory and
the pooled engine production uses, not a test-built `Session(bind=engine.connect())`.
The existing overlap test in `test_the_moderation_sweep_moderates_closed_windows.py`
builds its own sessions on `NullPool` connections, which is exactly the arrangement
under which this defect cannot happen.

**The pool is warmed first**, with three idle connections, because the defect needs
the pool to hand back a *different* connection after a commit: SQLAlchemy's
`QueuePool` returns them first in, first out, so a pool holding only the one the
task checked out would hand that same one back every time and hide the hazard.

**Two observables, both read on connections the task never held:** no advisory lock
is held in this database once the task returns, and a second sweep on a fresh
connection takes the lock and moderates a comment planted after the first.

**Not covered here, and said so:** decision 5a also asks for an error-level log
when `pg_advisory_unlock` answers false. With the fix in place the unlock cannot
answer false through any path a test can reach without reaching into the
implementation, so that branch has no assertion in this file.

**Which failure a red is, before the fix:** an assertion — an advisory lock still
held after the task returned, and the second sweep leaving the new comment with no
verdict. Never an import error (`docs/MISTAKES.md` entry 44).
"""

from collections.abc import Iterator
from importlib import import_module
from typing import Any

import pytest
from fixtures.clock import DEVELOPMENT, ENVIRONMENT_VARIABLE
from fixtures.mock_ai import (
    MOCK_AI_PROVIDER_BASE_URL_VARIABLE,
    MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE,
    Endpoint,
)
from fixtures.moderation import CLEAR, UNMODERATED, moderation_verdicts
from fixtures.report_comments import CommentWorld
from fixtures.report_views import INSTRUCTOR_STREAM
from sqlalchemy import text

pytestmark = pytest.mark.integration

CLOSED_WEEK = 7
TASKS_MODULE = "app.jobs.tasks"
TASK_NAME = "moderate_closed_windows"
DATABASE_MODULE = "app.db"

# How many idle connections the pool is given before the task runs: enough that
# a commit followed by a checkout lands on another connection at least twice.
WARMED = 3

ADVISORY_LOCKS_HELD = text(
    "SELECT count(*) FROM pg_locks "
    "WHERE locktype = 'advisory' AND granted "
    "AND database = (SELECT oid FROM pg_database WHERE datname = current_database()) "
    "AND pid <> pg_backend_pid()"
)


@pytest.fixture
def the_task_points_at_the_mock(
    monkeypatch: pytest.MonkeyPatch,
    care_service_environment: dict[str, str],
    mock_ai_endpoint: Endpoint,
) -> Endpoint:
    """The provider variables the task's own gateway reads, laid down before `app.*` is imported.

    The values `test_the_moderation_sweep_moderates_closed_windows.py::gateways`
    sets, set here rather than in the test body because the task builds its
    gateway itself and `summary_job_environment` re-imports the application
    after this runs (`docs/MISTAKES.md` entries 40 and 52).
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, DEVELOPMENT)
    monkeypatch.setenv(MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE, "mock-moderation-v1")
    monkeypatch.setenv(MOCK_AI_PROVIDER_BASE_URL_VARIABLE, mock_ai_endpoint.base_url)
    return mock_ai_endpoint


@pytest.fixture
def the_task_on_the_application_role(
    the_task_points_at_the_mock: Endpoint,
    summary_job_environment: Any,
) -> Iterator[Any]:
    """`moderate_closed_windows`, with `app.db` bound to this container as `pulse_app`.

    The engine is disposed at teardown, which closes every pooled connection and
    with them any session-level lock a defective run left behind — so a red here
    does not strand the lock for the next test in this worker.
    """
    tasks = import_module(TASKS_MODULE)
    task = getattr(tasks, TASK_NAME, None)
    if task is None:
        pytest.fail(f"`{TASKS_MODULE}` exposes no `{TASK_NAME}` (ADR 0188's hourly sweep task).")
    engine = import_module(DATABASE_MODULE).engine
    try:
        yield task
    finally:
        engine.dispose()


@pytest.fixture
def fresh_connections(migrated_engine: Any) -> Iterator[Any]:
    """An engine whose connections really close: none of them can be one the task held."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    engine = create_engine(migrated_engine.url, poolclass=NullPool)
    yield engine
    engine.dispose()


def a_comment(world: CommentWorld, body: str) -> Any:
    _, written = world.submit(
        term_week=CLOSED_WEEK,
        comments={INSTRUCTOR_STREAM: body},
        moderation={INSTRUCTOR_STREAM: UNMODERATED},
    )
    return world.answer_key(written[INSTRUCTOR_STREAM])


def verdicts_on_a_fresh_connection(engine: Any, answer_id: Any) -> list[str]:
    from sqlalchemy.orm import Session

    with Session(engine) as fresh:
        return [row["verdict"] for row in moderation_verdicts(fresh, answer_id)]


def warm_the_pool() -> Any:
    """Check out `WARMED` connections at once and hand them back, so the pool holds them idle."""
    engine = import_module(DATABASE_MODULE).engine
    held = [engine.connect() for _ in range(WARMED)]
    for connection in held:
        connection.close()
    checkedin = getattr(engine.pool, "checkedin", None)
    if not callable(checkedin) or checkedin() < WARMED:
        pytest.fail(
            f"`{DATABASE_MODULE}.engine`'s pool ({type(engine.pool).__name__}) does not hold "
            f"{WARMED} idle connections after {WARMED} were checked out and returned. Decision 5a's "
            "defect is a pooled connection handed back between commits; a pool that does not keep "
            "connections cannot carry it, and this test's premise does not hold."
        )
    return engine


def test_the_task_leaves_no_lock_held_and_a_later_sweep_on_another_connection_takes_it(
    the_task_on_the_application_role: Any,
    committed_comment_world: CommentWorld,
    committed_rows: Any,
    fresh_connections: Any,
    migrated_engine: Any,
) -> None:
    """Decision 5a: lock, per-comment commits and unlock on one connection, through the task.

    Two closed-window comments, so the task commits between taking the lock and
    releasing it. The pool is warmed, the task runs, and then:

      - both comments hold their verdict, read on a fresh connection — the
        premise that the task ran and committed at all;
      - no advisory lock is held by any server connection in this database;
      - a third comment is planted, and a sweep on a fresh connection — not one
        the task's pool ever held — moderates it.

    **The mutation this kills:** the session bound to the pooled engine, as PR
    #293 shipped it (the unlock runs on another pooled connection, the lock stays
    on the first, and the later sweep finds it taken). **The near miss:** a later
    sweep run through the same pool, which can draw the very connection holding
    the stale lock and re-enter it — which is why the later sweep here runs on a
    connection of its own.
    """
    from sqlalchemy.orm import Session

    from app.ai.gateway import AIGateway
    from app.config import DEVELOPMENT_ENVIRONMENT, Settings
    from app.services.moderation import sweep_unmoderated_comments

    world = committed_comment_world
    world.build()
    world.close_week(CLOSED_WEEK)
    first = a_comment(world, "E605LOCKAQz the lab ran long and the slides were out of date")
    second = a_comment(world, "E605LOCKBQz the reading list arrived on the Thursday")
    committed_rows.commit()

    warm_the_pool()
    the_task_on_the_application_role()

    for answer in (first, second):
        assert verdicts_on_a_fresh_connection(fresh_connections, answer) == [CLEAR], (
            "The task did not moderate a closed-window comment, so it never took the lock and "
            "committed between taking and releasing it; this test measured nothing."
        )

    with migrated_engine.connect() as watcher:
        held = watcher.execute(ADVISORY_LOCKS_HELD).scalar_one()
    assert held == 0, (
        f"{held} advisory lock(s) are still held in this database after the moderation task "
        "returned. Decision 5a: the session is bound to one connection, so the unlock runs where "
        "the lock was taken; a lock left on a pooled connection stops every later sweep."
    )

    third = a_comment(world, "E605LOCKCQz office hours clashed with the lab")
    committed_rows.commit()

    connection = fresh_connections.connect()
    session = Session(bind=connection, info={"environment": DEVELOPMENT_ENVIRONMENT})
    try:
        sweep_unmoderated_comments(session, AIGateway(settings=Settings()))
    finally:
        session.close()
        connection.close()

    assert verdicts_on_a_fresh_connection(fresh_connections, third) == [CLEAR], (
        "A sweep on a fresh connection, after the task had finished, did not moderate a comment "
        "planted after it. The task's lock was not released, so every later run does nothing."
    )
