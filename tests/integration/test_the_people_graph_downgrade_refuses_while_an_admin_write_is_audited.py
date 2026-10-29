"""E9-02's downgrade refuses while an admin write is audited, and round-trips over none — fix round 1, F8.

From `e9-02-fix-round.md`:

> F8. The guarded downgrade has no test. Add two tests in the shape of the
> `2c3d5a0de424` precedent. One shows the downgrade refuses while an
> admin-write row exists. The other shows an empty round trip: upgrade,
> downgrade to `7f679faf4b8d`, upgrade.

The settled downgrade (interface §8) "raises `RuntimeError` and changes nothing
while any `audit_log` row has an action other than `IDENTITY_REVEAL`". Going down
drops `subject_person_id`, `role`, `scope_node_id` and `parent_assignment_id` and
restores `subject_user_id NOT NULL`, which an admin-write row cannot satisfy —
so a downgrade over one would either fail part-way or erase who was granted what.

The shape is `test_m2_refuses_to_step_over_a_policy_row_in_either_direction.py`'s:
each test migrates a throwaway database (`empty_database`), never the session one
(`docs/MISTAKES.md` entry 12), reads the catalog rather than the models, finds
the refusal as a `RuntimeError` anywhere in the exception's chain, and counts the
row afterwards, so a guard that raised after dropping a column is not mistaken
for one that refused.

**Which failure a red is, at cae46288.** If the guard is there and works, both
are green there already; F8 is that nothing tested it. The refusal is red if the
guard is missing or raises after the drop; the round trip is red if the guard
refuses an empty table or the downgrade leaves a column behind.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.migration_journey import (
    MODEL_SCHEMA,
    columns_the_database_reports,
    migrate,
    session_on,
)
from fixtures.supervision import seed_row
from sqlalchemy import create_engine, text
from test_the_response_records_downgrade_refuses_while_a_row_exists import (
    count,
    is_a_runtime_error,
    refused,
)

pytestmark = pytest.mark.integration

# E9-02's migration chains from E9-03's revision. The E9 README's counters rule has
# the ticket that merges second re-point its `down_revision` to the head it finds;
# E9-03 merged first, so E9-02 re-pointed (the ruling on docs/disputes/E9-02-03.md).
BELOW_E9_02 = "e9b2c4d6a802"
E9_02_REVISION = "e9a1d0c3f201"

AUDIT_LOG = "audit_log"
E9_02_COLUMNS = frozenset({"subject_person_id", "role", "scope_node_id", "parent_assignment_id"})
A_DEFINER = "admin_grant_role"

FUNCTION_EXISTS = text(
    "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
    "WHERE n.nspname = 'public' AND p.proname = :name"
)
SUBJECT_USER_NULLABLE = text(
    "SELECT is_nullable FROM information_schema.columns WHERE table_schema = 'public' "
    "AND table_name = 'audit_log' AND column_name = 'subject_user_id'"
)


def require_the_revision(config: Any) -> None:
    """E9-02's revision is in the history and chains from `e9b2c4d6a802`, or a failure."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(config)
    found = script.get_revision(E9_02_REVISION)
    if found is None:
        pytest.fail(f"No revision `{E9_02_REVISION}`; the E9 README allots it to E9-02.")
    below = found.down_revision
    below = below if isinstance(below, tuple) else (below,)
    if BELOW_E9_02 not in below:
        pytest.fail(f"`{E9_02_REVISION}` chains from {below}, not `{BELOW_E9_02}`.")


def scalar(database: Any, statement: Any, **values: Any) -> Any:
    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            return connection.execute(statement, values).scalar_one_or_none()
    finally:
        engine.dispose()


def plant_an_admin_write(database: Any, tables: dict[str, Any]) -> None:
    """One `ROLE_GRANTED` row at head, naming two real people, committed."""
    import importlib

    granted = importlib.import_module("app.models.audit").AuditAction.ROLE_GRANTED
    with session_on(database) as session:
        actor = seed_row(session, tables, "person", {})["id"]
        subject = seed_row(session, tables, "person", {})["id"]
        session.execute(
            tables[AUDIT_LOG]
            .insert()
            .values(
                action=granted,
                actor_person_id=actor,
                subject_person_id=subject,
                subject_user_id=None,
                case_id=None,
                role="CARE",
                # E9-14 item 3: a grant row names its scope node, by a check.
                scope_node_id=uuid4(),
                parent_assignment_id=None,
            )
        )


def test_the_downgrade_refuses_while_an_admin_write_row_exists(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """One `ROLE_GRANTED` row at head: `downgrade e9b2c4d6a802` raises `RuntimeError`; the row and its columns stay.

    **The mutations it kills:** no guard, so the downgrade drops
    `subject_person_id` and either fails on restoring `NOT NULL` part-way or
    erases who was granted what; a guard that counts only some actions; a guard
    that raises after the columns are dropped (the column check below).
    """
    config = alembic_config_pointed_at(empty_database)
    require_the_revision(config)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    plant_an_admin_write(empty_database, metadata_tables)
    assert count(empty_database, AUDIT_LOG) == 1, "The planted admin-write row is not there."

    failure = refused(config, BELOW_E9_02)

    assert failure is not None, (
        f"`alembic downgrade {BELOW_E9_02}` completed over an admin-write audit row. Settled: the "
        "downgrade raises `RuntimeError` and changes nothing while such a row exists."
    )
    assert is_a_runtime_error(
        failure
    ), f"The downgrade failed with {failure!r}, not `RuntimeError`."
    assert count(empty_database, AUDIT_LOG) == 1, "After the refusal the audit row is gone."
    present = columns_the_database_reports(empty_database, AUDIT_LOG)
    assert present >= E9_02_COLUMNS, (
        f"After the refusal `audit_log` lacks {sorted(E9_02_COLUMNS - present)}: the guard raised "
        "after the drop."
    )
    assert (
        scalar(empty_database, FUNCTION_EXISTS, name=A_DEFINER) == 1
    ), f"After the refusal `{A_DEFINER}` is gone: the guard raised after the functions were dropped."


def test_the_downgrade_round_trips_over_an_audit_log_with_no_admin_write(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """Head, down to `e9b2c4d6a802`, head again, over no admin-write rows: E9-02 gone in the middle, then back.

    The twin the refusal needs. **The mutations it kills:** a guard that refuses
    unconditionally; a downgrade that leaves a column, the functions or the
    relaxed `subject_user_id` behind (the middle checks); an upgrade that cannot
    be re-applied after its own downgrade.
    """
    config = alembic_config_pointed_at(empty_database)
    require_the_revision(config)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    migrate(config, "downgrade", BELOW_E9_02, "stepping below E9-02 over no admin-write rows")

    below = columns_the_database_reports(empty_database, AUDIT_LOG)
    nullable_below = scalar(empty_database, SUBJECT_USER_NULLABLE)
    definer_below = scalar(empty_database, FUNCTION_EXISTS, name=A_DEFINER)

    migrate(config, "upgrade", MODEL_SCHEMA, "re-applying E9-02 after its own downgrade")

    at_head = columns_the_database_reports(empty_database, AUDIT_LOG)
    assert below and not (E9_02_COLUMNS & below), (
        f"Below E9-02 `audit_log` carries {sorted(below)}; the downgrade drops "
        f"{sorted(E9_02_COLUMNS)}."
    )
    assert nullable_below == "NO", (
        f"Below E9-02 `audit_log.subject_user_id` is nullable ({nullable_below!r}); the downgrade "
        "restores NOT NULL."
    )
    assert definer_below == 0, f"Below E9-02 `{A_DEFINER}` still exists."
    assert (
        at_head >= E9_02_COLUMNS
    ), f"Back at head `audit_log` lacks {sorted(E9_02_COLUMNS - at_head)}."
    assert (
        scalar(empty_database, FUNCTION_EXISTS, name=A_DEFINER) == 1
    ), f"Back at head `{A_DEFINER}` does not exist."
