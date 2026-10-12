"""The edge write refuses an assignment revoked while it waited for the lock — E9-02 fix round 1, F4 and F5.

From `e9-02-fix-round.md`:

> F4. W5 succeeds and writes an audit row even when a concurrent revoke deleted
> the child first. After the UPDATE: `IF NOT FOUND THEN RAISE EXCEPTION
> 'admin_people.no_such_assignment' ...`. Test it with two connections.
> Connection A revokes the child and holds the transaction open. Connection B's
> set blocks. A commits. B must get P0001 `no_such_assignment`, and no
> REPORTS_TO_SET row may exist.
>
> F5. A parent deleted concurrently reaches the caller as a raw 23503 error. Add
> `WHEN foreign_key_violation THEN RAISE EXCEPTION
> 'admin_people.no_such_assignment' ...` to W5's block. Test it with the same
> two-connection shape, with the parent revoked.

**The two-connection shape.** Connection A is a fresh `pulse_app` connection
off `application_engine`; it calls `admin_revoke_role` and does not commit, so
the deleted row stays locked. Connection B is the world's own
`application_session`, which calls `admin_set_reports_to` on a worker thread.
B's existence checks run against its snapshot, in which the row still exists,
so the only thing that can stop B is what happens when its write meets A's lock.

**B is required to be seen waiting on a lock before A commits.** The main thread
polls `pg_stat_activity` for B's backend until it reports `wait_event_type =
'Lock'`. If B never blocks, the race was not exercised — B ran before A's
delete or after it — and the test fails saying so rather than passing on an
ordering nobody chose (`docs/MISTAKES.md` entry 3).

**Every wait is bounded, so a hang fails instead of stalling CI.** B's
connection carries a `statement_timeout`; the poll for the lock gives up after
`BLOCK_WITHIN_SECONDS`; the join after A commits gives up after
`FINISH_WITHIN_SECONDS`. Each bound fails the test with a message naming what
did not happen. The statement timeout is set and reset with its own commits, so
it neither leaks into another test nor is undone by the call's rollback.

**Which failure a red is, at cae46288.** F4: B's UPDATE matches no row after A
commits, W5 writes its audit row and returns, and the test fails on "the call
failed". F5: B's foreign-key check fails after A commits and the raw 23503
reaches the caller, and the test fails on the SQLSTATE.
"""

import threading
import time
from typing import Any

import pytest
from fixtures.people_graph import (
    NAMED_REFUSAL,
    NO_SUCH_ASSIGNMENT,
    REPORTS_TO_SET,
    Called,
    PeopleGraphWorld,
    token,
)
from sqlalchemy import text

pytestmark = pytest.mark.integration

# How long B may take to be seen waiting on A's lock, and to finish once A commits.
BLOCK_WITHIN_SECONDS = 10.0
FINISH_WITHIN_SECONDS = 15.0
POLL_EVERY_SECONDS = 0.05

# The backstop on B's own statement, longer than both bounds above so that the
# bounds, not the timeout, are what a slow run trips first.
B_STATEMENT_TIMEOUT = "30s"

REVOKE_ON_A = "SELECT public.admin_revoke_role(CAST(:actor AS uuid), CAST(:assignment AS uuid))"
WAIT_EVENT = "SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"


def edge_rows(world: PeopleGraphWorld) -> list[dict[str, Any]]:
    return [row for row in world.audit_rows(world.admin) if token(row["action"]) == REPORTS_TO_SET]


def race(
    world: PeopleGraphWorld,
    application_engine: Any,
    *,
    revoked: Any,
    child: Any,
    parent: Any,
) -> Called:
    """A revokes `revoked` and holds; B sets `child`'s parent to `parent` and blocks; A commits.

    Answers B's outcome. Fails the test if A's revoke fails, if B is never seen
    waiting on a lock, or if B does not finish after A commits.
    """
    session = world.app
    session.execute(text(f"SET statement_timeout = '{B_STATEMENT_TIMEOUT}'"))
    session.commit()
    b_pid = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
    session.commit()

    a = application_engine.connect()
    outcome: list[Called] = []
    worker: threading.Thread | None = None
    try:
        a.execute(text(REVOKE_ON_A), {"actor": str(world.admin), "assignment": str(revoked)})

        def b() -> None:
            outcome.append(
                world.call("admin_set_reports_to", world.admin, assignment=child, reports_to=parent)
            )

        worker = threading.Thread(target=b, daemon=True)
        worker.start()

        deadline = time.monotonic() + BLOCK_WITHIN_SECONDS
        waiting = None
        while time.monotonic() < deadline and worker.is_alive():
            with world.engine.connect() as probe:
                waiting = probe.execute(text(WAIT_EVENT), {"pid": b_pid}).scalar_one_or_none()
            if waiting == "Lock":
                break
            time.sleep(POLL_EVERY_SECONDS)
        if waiting != "Lock":
            a.rollback()
            worker.join(FINISH_WITHIN_SECONDS)
            pytest.fail(
                f"B's `admin_set_reports_to` was never seen waiting on a lock within "
                f"{BLOCK_WITHIN_SECONDS}s (last wait event {waiting!r}; B finished: "
                f"{not worker.is_alive()}, answering "
                f"{outcome[0].describe() if outcome else 'nothing'}). The race F4 and F5 are "
                "about was not exercised, so nothing here says what W5 does inside it."
            )

        a.commit()
        worker.join(FINISH_WITHIN_SECONDS)
        if worker.is_alive():
            pytest.fail(
                f"B's `admin_set_reports_to` had not finished {FINISH_WITHIN_SECONDS}s after A "
                "committed its revoke. A hang here is a defect, not a slow run."
            )
    finally:
        a.rollback()
        a.close()
        if worker is not None:
            worker.join(FINISH_WITHIN_SECONDS)
        session.rollback()
        session.execute(text("RESET statement_timeout"))
        session.commit()

    assert outcome, "B finished and recorded no outcome."
    return outcome[0]


def test_an_edge_set_on_a_child_revoked_while_it_waited_is_refused_and_unaudited(
    people_graph: PeopleGraphWorld, application_engine: Any
) -> None:
    """F4: the child is revoked under B; B's UPDATE then matches nothing, and W5 must say so.

    **The mutations it kills:** W5 with no `IF NOT FOUND` after its UPDATE, which
    answers success and writes a `REPORTS_TO_SET` row about an assignment that
    no longer exists; a `NOT FOUND` check that raises something other than the
    named refusal; the audit insert made before the UPDATE. **The near miss:**
    the uncontended edge set, which succeeds and writes one row
    (`test_an_edge_change_leaves_one_row_naming_the_childs_person_role_and_scope`).
    """
    world = people_graph
    child = world.assignment("CHAIR")
    parent = world.assignment("DEAN")

    answered = race(world, application_engine, revoked=child, child=child, parent=parent)

    assert answered.failure is not None, (
        f"B's edge set on a child revoked while it waited {answered.describe()}. F4: after the "
        "UPDATE matches no row, W5 raises the named refusal."
    )
    assert (answered.sqlstate, answered.message) == (
        NAMED_REFUSAL,
        NO_SUCH_ASSIGNMENT,
    ), f"B's edge set {answered.describe()}; F4: P0001 with `{NO_SUCH_ASSIGNMENT}`."
    assert world.assignment_row(child) is None, "A's revoke did not delete the child."
    assert (
        edge_rows(world) == []
    ), f"A `{REPORTS_TO_SET}` row exists for an edge that was never set: {edge_rows(world)}."


def test_an_edge_set_to_a_parent_revoked_while_it_waited_is_a_named_refusal(
    people_graph: PeopleGraphWorld, application_engine: Any
) -> None:
    """F5: the parent is revoked under B; B's foreign-key check then fails, and W5 must name it.

    **The mutations it kills:** W5's block with no `foreign_key_violation`
    handler, so the raw 23503 reaches the caller (a 500 at E9-06's route); a
    handler that maps it to another key (`edge_does_not_climb`, say), which
    tells the admin the wrong thing to fix. **The near miss:** the uncontended
    set (above), and F4's child-side race.
    """
    world = people_graph
    child = world.assignment("CHAIR")
    parent = world.assignment("DEAN")

    answered = race(world, application_engine, revoked=parent, child=child, parent=parent)

    assert (answered.sqlstate, answered.message) == (NAMED_REFUSAL, NO_SUCH_ASSIGNMENT), (
        f"B's edge set to a parent revoked while it waited {answered.describe()}; F5: P0001 with "
        f"`{NO_SUCH_ASSIGNMENT}`, not the database's foreign-key error."
    )
    assert world.assignment_row(parent) is None, "A's revoke did not delete the parent."
    assert world.reports_to_of(child) is None, "The child points at a parent that is gone."
    assert (
        edge_rows(world) == []
    ), f"A `{REPORTS_TO_SET}` row exists for an edge that was never set: {edge_rows(world)}."
