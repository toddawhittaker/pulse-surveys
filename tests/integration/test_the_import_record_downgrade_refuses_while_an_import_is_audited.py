"""The import-record migration's downgrade refuses while an import is audited, and round-trips over none — E9-06 fix round, Q1 (f).

Settled: the new revision is `e9d4a6b8c905`; it adds `audit_log.detail`, the
`IMPORT_APPLIED` action and `admin_record_import`; its downgrade refuses while an
`IMPORT_APPLIED` row exists, as E9-02's does for its own rows. Going down drops
`detail`, so a downgrade over an import row would erase the diff SPEC §8 says the
log keeps.

The shape is E9-02's
(`test_the_people_graph_downgrade_refuses_while_an_admin_write_is_audited.py`):
a throwaway database (`empty_database`, `docs/MISTAKES.md` entry 12), the
catalog rather than the models, the refusal found as a `RuntimeError` anywhere in
the exception's chain, and the row, the column and the function counted after,
so a guard that raised after dropping something is not mistaken for one that
refused.

**The revision below is read from the script, not spelled.** The brief settles
`down_revision = "e9c3f5a7b403"`, and the E9 README's counters rule has whichever
ticket merges second re-point its `down_revision` to the head it finds, so
pinning the number would turn a correct re-point red.

**Which failure a red is, at 09778dc5.** There is no revision `e9d4a6b8c905`:
both tests fail on `pytest.fail` naming it.
"""

from typing import Any

import pytest
from fixtures.migration_journey import (
    MODEL_SCHEMA,
    columns_the_database_reports,
    migrate,
    session_on,
)
from fixtures.supervision import seed_row
from test_the_people_graph_downgrade_refuses_while_an_admin_write_is_audited import (
    FUNCTION_EXISTS,
    plant_an_admin_write,
    scalar,
)
from test_the_response_records_downgrade_refuses_while_a_row_exists import (
    count,
    is_a_runtime_error,
    refused,
)

pytestmark = pytest.mark.integration

REVISION = "e9d4a6b8c905"
AUDIT_LOG = "audit_log"
DETAIL = "detail"
DEFINER = "admin_record_import"


def the_revision_below(config: Any) -> str:
    """`e9d4a6b8c905`'s single parent, or a failure naming what is missing."""
    from alembic.script import ScriptDirectory

    found = ScriptDirectory.from_config(config).get_revision(REVISION)
    if found is None:
        pytest.fail(
            f"No revision `{REVISION}`. E9-06's fix round adds it for `audit_log.detail`, "
            "`IMPORT_APPLIED` and `admin_record_import`."
        )
    below = found.down_revision
    if not isinstance(below, str):
        pytest.fail(f"`{REVISION}` has down_revision {below!r}; settled: one parent.")
    return below


def plant_an_import(database: Any, tables: dict[str, Any]) -> None:
    """One committed `IMPORT_APPLIED` row at head, naming a real person, with a detail."""
    import importlib

    action = importlib.import_module("app.models.audit").AuditAction
    member = getattr(action, "IMPORT_APPLIED", None)
    if member is None:
        pytest.fail("`AuditAction` has no `IMPORT_APPLIED`; E9-06's fix round adds it.")
    with session_on(database) as session:
        actor = seed_row(session, tables, "person", {})["id"]
        session.execute(
            tables[AUDIT_LOG]
            .insert()
            .values(
                action=member,
                actor_person_id=actor,
                subject_person_id=None,
                subject_user_id=None,
                case_id=None,
                role=None,
                scope_node_id=None,
                parent_assignment_id=None,
                detail={"kind": "lead_mappings", "diff": {"added": [], "changed": []}},
            )
        )


def test_the_downgrade_refuses_while_an_import_row_exists(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """One `IMPORT_APPLIED` row at head: the downgrade raises `RuntimeError`; the row, `detail` and the definer stay.

    **The mutations it kills:** no guard, so `detail` and every import's diff
    are dropped; a guard counting some other action; a guard that raises after
    the column or the function is dropped.
    """
    config = alembic_config_pointed_at(empty_database)
    below = the_revision_below(config)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    plant_an_import(empty_database, metadata_tables)
    assert count(empty_database, AUDIT_LOG) == 1, "The planted import row is not there."

    failure = refused(config, below)

    assert failure is not None, (
        f"`alembic downgrade {below}` completed over an `IMPORT_APPLIED` row. Settled: the "
        "downgrade refuses while such a row exists."
    )
    assert is_a_runtime_error(
        failure
    ), f"The downgrade failed with {failure!r}, not `RuntimeError`."
    assert count(empty_database, AUDIT_LOG) == 1, "After the refusal the import row is gone."
    assert DETAIL in columns_the_database_reports(
        empty_database, AUDIT_LOG
    ), "After the refusal `audit_log.detail` is gone: the guard raised after the drop."
    assert (
        scalar(empty_database, FUNCTION_EXISTS, name=DEFINER) == 1
    ), f"After the refusal `{DEFINER}` is gone: the guard raised after the drop."


def test_the_downgrade_round_trips_over_an_audit_log_holding_only_other_actions(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """A `ROLE_GRANTED` row and no import: down one revision and back up, the import machinery gone in the middle.

    **The mutations it kills:** a guard that refuses unconditionally, or over
    any admin-write row (E9-02's guard copied whole — the `ROLE_GRANTED` row is
    the near miss); a downgrade that leaves `detail` or the definer behind; an
    upgrade that cannot be re-applied after its own downgrade (the action added
    again when it is already there, for one).
    """
    config = alembic_config_pointed_at(empty_database)
    below = the_revision_below(config)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    plant_an_admin_write(empty_database, metadata_tables)
    migrate(config, "downgrade", below, "stepping below the import record over no import row")

    columns_below = columns_the_database_reports(empty_database, AUDIT_LOG)
    definer_below = scalar(empty_database, FUNCTION_EXISTS, name=DEFINER)
    rows_below = count(empty_database, AUDIT_LOG)

    migrate(config, "upgrade", MODEL_SCHEMA, "re-applying the import record after its downgrade")

    assert columns_below and DETAIL not in columns_below, (
        f"Below `{REVISION}` `audit_log` carries {sorted(columns_below)}; the downgrade drops "
        f"`{DETAIL}`."
    )
    assert definer_below == 0, f"Below `{REVISION}` `{DEFINER}` still exists."
    assert rows_below == 1, f"The downgrade left {rows_below} audit rows; the grant row is one."
    assert DETAIL in columns_the_database_reports(
        empty_database, AUDIT_LOG
    ), f"Back at head `audit_log` lacks `{DETAIL}`."
    assert (
        scalar(empty_database, FUNCTION_EXISTS, name=DEFINER) == 1
    ), f"Back at head `{DEFINER}` does not exist."
