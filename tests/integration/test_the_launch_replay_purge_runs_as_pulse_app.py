"""The launch replay ledger's daily purge, driven to completion as `pulse_app` — ticket E4-14.

The carried defect (`docs/tickets/e4/carried-from-e3.md`, "The daily purge of the
launch replay ledger cannot run"): `app.jobs.tasks.purge_launch_nonces` has raised
`psycopg.errors.InsufficientPrivilege` on every run since E1-08 shipped it, because
`backend/app/views_sql/lti_launch_nonce_grants_v001.sql` grants `pulse_app` `INSERT`
and `DELETE` on `lti_launch_nonce` and withholds `SELECT` — and Postgres requires
`SELECT` on every column a `DELETE ... WHERE` reads. The purge deletes on
`expires_at`. The task's `lti_launch_state` half never runs either, because the
nonce half raises first and the whole task shares one `SessionLocal`.

**Ticket E4-14's fix is a column-scoped grant**, `SELECT (expires_at)` on
`lti_launch_nonce`, spent in a `v002` grants file and its migration.
`tests/integration/test_identity_grants.py` holds the two halves of that record:
`RUNTIME_COLUMN_PRIVILEGES` states the grant exists, and
`test_the_application_role_may_read_the_nonce_ledgers_expiry_and_not_its_nonce`
measures it as a direct query. **This module is the third leg**: acceptance
criterion 1 asks that the driven task complete — expired nonce rows gone,
unexpired rows intact, and the `lti_launch_state` half now also running — proven
by running the task, not by reading the grant or approximating its SQL by hand.

**Driven through a real `pulse_app` login, never the migrating engine**
(`docs/MISTAKES.md` entry 46: "a suite that drives a service through the migrating
engine has not tested the privilege at all"). `purge_launch_nonces` opens its own
`SessionLocal`, which resolves `DATABASE_URL` at import time — so `app.jobs.tasks`
is dropped from `sys.modules` and reimported here after `DATABASE_URL` is pointed
at this container's application role, exactly as `test_db_session.py`'s
`database_module` fixture does for `app.db` alone (that file's own docstring:
"tests that pass under privileges no deployment has").

**Planted through the schema's own seeding helper, not hand-written `INSERT`s.**
`seed_row` (`tests/fixtures/supervision.py`) fills every column this ticket does
not care about from the table's own defaults or from its generic inventor, so
this module only has to state the two columns the ticket is about — `nonce` /
`state` and `expires_at`. The ticket's own trap is a *task* approximated by hand;
the planting is deliberately not that.

**Read back on a connection the task never held**, so "gone" and "intact" are
facts about what another connection can see rather than about what the seeding
session still remembers writing (`docs/MISTAKES.md` entry 3, the same rule
`test_a_failed_line_item_creation_still_records_its_calls.py` states for the
sibling task `create_line_item`).
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

DATABASE_URL_VARIABLE = "DATABASE_URL"
TASKS_MODULE = "app.jobs.tasks"
PURGE_TASK_ATTRIBUTE = "purge_launch_nonces"
NONCE_TABLE = "lti_launch_nonce"
STATE_TABLE = "lti_launch_state"

TASK_IS_OWED = (
    "ADR 0089 gives `app.jobs.tasks.purge_launch_nonces` the daily beat entry that reclaims "
    "the expired tail of both `lti_launch_nonce` and `lti_launch_state` (E1-08). "
    "`tests/unit/test_celery_app.py`'s "
    "`test_the_beat_schedule_holds_exactly_the_entries_that_have_landed` pins the "
    "schedule and the task name; this module drives the task's own body."
)


def purge_task(module: ModuleType) -> Any:
    """`app.jobs.tasks.purge_launch_nonces`, or a failure naming the deliverable that owes it.

    A plain function called from a test body, never a fixture, so a tree missing the
    task reports a FAILED naming it rather than an `AttributeError` raised out of
    somebody's setup (`docs/MISTAKES.md` entry 44).
    """
    task = getattr(module, PURGE_TASK_ATTRIBUTE, None)
    if task is None:
        pytest.fail(
            f"`{module.__name__}` exposes no `{PURGE_TASK_ATTRIBUTE}` — it exposes "
            f"{sorted(name for name in vars(module) if not name.startswith('_'))}. {TASK_IS_OWED}"
        )
    return task


def run_the_task(task: Any) -> BaseException | None:
    """Run the purge, answering what it raised rather than raising it.

    A Celery task called directly executes its body synchronously in this process,
    which is what a worker does with it. Answered rather than propagated so the row
    assertions below run whichever way the call goes, and so today's expected red —
    `InsufficientPrivilege` — is reported by this test's own assertion naming it,
    rather than as a bare traceback out of the test body.
    """
    try:
        task()
    except Exception as escaped:
        return escaped
    return None


@pytest.fixture
def tasks_on_the_application_role(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    migrated_database: Any,
    import_app_module: Callable[[str], ModuleType | None],
) -> ModuleType:
    """`app.jobs.tasks`, imported fresh against a real `pulse_app` login on the container.

    `docs/MISTAKES.md` entry 46: a settled decision that rests on a privilege has to
    be measured on the role it is actually a claim about. Every other fixture in
    this suite that seeds rows connects as the bootstrap superuser
    (`tests/fixtures/database.py::migrated_engine`), which holds every privilege
    there is and would pass this ticket's criterion whether or not the grant
    existed. `app.jobs.tasks` resolves its own `SessionLocal` from `DATABASE_URL`
    at import, so the module is dropped out of `sys.modules` and reimported here
    after `DATABASE_URL` is pointed at `migrated_database.application_url` — the
    same technique `test_db_session.py`'s `database_module` fixture uses for
    `app.db` alone.
    """
    monkeypatch.setenv(DATABASE_URL_VARIABLE, migrated_database.application_url)
    module = import_app_module(TASKS_MODULE)
    if module is None:
        pytest.fail(f"`{TASKS_MODULE}` does not exist. {TASK_IS_OWED}")
    return module


def plant_ledger_rows(committed_rows: Any) -> dict[str, Any]:
    """One expired and one live row in each of the two tables this purge owns.

    Through `seed_row` rather than a hand-written `INSERT`: every column this
    ticket is not about is left to the table's own default or to the generic
    inventor, so this function only states `nonce` / `state` and `expires_at` —
    the two facts the purge's own `WHERE` clauses read. Committed before the task
    runs, because the task opens its own connection and a row still sitting inside
    this session's transaction is invisible to it.
    """
    now = datetime.now(UTC)
    tag = uuid4().hex[:12]
    rows = {
        "expired_nonce": committed_rows.seed(
            NONCE_TABLE, {}, nonce=f"e4-14-expired-{tag}", expires_at=now - timedelta(hours=1)
        ),
        "live_nonce": committed_rows.seed(
            NONCE_TABLE, {}, nonce=f"e4-14-live-{tag}", expires_at=now + timedelta(hours=1)
        ),
        "expired_state": committed_rows.seed(
            STATE_TABLE,
            {},
            state=f"e4-14-expired-state-{tag}",
            nonce=f"e4-14-expired-state-nonce-{tag}",
            expires_at=now - timedelta(hours=1),
        ),
        "live_state": committed_rows.seed(
            STATE_TABLE,
            {},
            state=f"e4-14-live-state-{tag}",
            nonce=f"e4-14-live-state-nonce-{tag}",
            expires_at=now + timedelta(hours=1),
        ),
    }
    committed_rows.commit()
    return rows


def nonce_row_present(committed_rows: Any, nonce: str) -> bool:
    """Whether a row keyed by `nonce` is visible on a connection reading committed work."""
    table = committed_rows.tables[NONCE_TABLE]
    committed_rows.session.rollback()
    found = committed_rows.session.execute(table.select().where(table.c.nonce == nonce)).first()
    return found is not None


def state_row_present(committed_rows: Any, state: str) -> bool:
    """Whether a row keyed by `state` is visible on a connection reading committed work."""
    table = committed_rows.tables[STATE_TABLE]
    committed_rows.session.rollback()
    found = committed_rows.session.execute(table.select().where(table.c.state == state)).first()
    return found is not None


def test_the_purge_task_reclaims_the_expired_tail_of_both_launch_tables(
    tasks_on_the_application_role: ModuleType,
    committed_rows: Any,
) -> None:
    """Criterion 1: all three, from one drive of the real task, as `pulse_app`.

    Expired nonce rows gone, unexpired nonce rows intact, and — the trap the
    ticket names explicitly — the `lti_launch_state` half now also running,
    because on the unfixed tree that half never runs at all: the nonce half
    raises `InsufficientPrivilege` before `purge_expired_launch_states` is ever
    reached, inside the same task and the same `SessionLocal`.

    **The mutation this kills.** A `v002` grant that never lands, or lands
    dropped from the migration chain: the task still raises, `escaped is None`
    fails naming what it raised, and the row assertions below are never reached
    because nothing was cleaned up. A `v002` grant widened to table-wide
    `SELECT` on `lti_launch_nonce`: the task now completes, so this test cannot
    tell that mutation apart — the direct-query test beside
    `RUNTIME_COLUMN_PRIVILEGES` in `test_identity_grants.py` is what catches
    it, by privilege rather than by task behaviour. The state-half call removed
    from `purge_launch_nonces` (the exact latent failure the ticket's own known
    traps name): the task completes without raising, the nonce assertions pass,
    and the two state assertions catch it — `expired_state` stays present.
    An unscoped `DELETE` with no `WHERE` on either table (the carried entry's own
    "the same `DELETE` with no `WHERE` was permitted" near miss): the task
    completes, but `live_nonce` and `live_state` are gone too, and those two
    assertions catch it.

    **The near miss this does not have to prove**: that the grant is column-scoped
    rather than table-wide. That is `test_identity_grants.py`'s question, answered
    by a direct query rather than by what one task happens to select — a task
    written to read only `expires_at` would pass this test unchanged whether the
    grant behind it were column-scoped or table-wide.
    """
    rows = plant_ledger_rows(committed_rows)
    task = purge_task(tasks_on_the_application_role)

    escaped = run_the_task(task)

    assert escaped is None, (
        f"`{PURGE_TASK_ATTRIBUTE}` raised {escaped!r} run as `pulse_app` against a table "
        "holding both an expired and a live row. ADR 0089's daily purge exists to reclaim "
        "the ledger's expired tail; a task that cannot run at all leaves both "
        f"`{NONCE_TABLE}` and `{STATE_TABLE}` growing without bound. E4-14's column-scoped "
        f"`SELECT (expires_at)` on `{NONCE_TABLE}` is what `purge_expired_nonces`' own "
        "`DELETE ... WHERE expires_at < now()` needs and does not yet have."
    )
    assert not nonce_row_present(committed_rows, rows["expired_nonce"]["nonce"]), (
        f"The expired `{NONCE_TABLE}` row this test planted is still there after the task "
        "reported no error. `purge_expired_nonces` is supposed to delete on `expires_at`; a "
        "task that returns cleanly without deleting anything is a different defect from the "
        "one this ticket names, and just as much a failure to reclaim the ledger."
    )
    assert nonce_row_present(committed_rows, rows["live_nonce"]["nonce"]), (
        f"The unexpired `{NONCE_TABLE}` row this test planted is gone after the task ran. A "
        "purge that deletes without its `WHERE` clause — the carried entry's own measured "
        "near miss, 'the same `DELETE` with no `WHERE` was permitted' — would pass the "
        "assertion above and fail this one: it destroys nonces a launch may still replay "
        "against, defeating SPEC §9.1's single-use guarantee for every launch in flight."
    )
    assert not state_row_present(committed_rows, rows["expired_state"]["state"]), (
        f"The expired `{STATE_TABLE}` row this test planted is still there. The carried entry "
        "names this exact latent failure: 'the half of the task that purges `lti_launch_state` "
        "never runs either, because the nonce half raises first.' A fix that only grants the "
        "nonce column back and never reaches the second `DELETE` leaves this table growing "
        "without bound while every other assertion here goes green."
    )
    assert state_row_present(committed_rows, rows["live_state"]["state"]), (
        f"The unexpired `{STATE_TABLE}` row this test planted is gone after the task ran, "
        "which destroys an in-flight launch handshake — `app.lti.in_flight.look_up_launch` "
        "would refuse a legitimate launch whose `state` this purge deleted before the platform "
        "ever redirected back to it."
    )
