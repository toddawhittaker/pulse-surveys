"""M2 refuses to step over a policy row in either direction — E7-02's fix round, H1 and H2.

> H1. M2's downgrade: with a policy row planted, `downgrade 2c3d5a0de424` raises
> RuntimeError and the row survives; over an empty table, step down to
> 2c3d5a0de424 and back up; after the step down M1's policy index is back, the
> policy guard checks the setter's role in the prefix again (a v001 behaviour),
> and `response_policy` has no `course_id`.
> H2. M2's `upgrade()` counts `response_policy` rows and raises a readable
> RuntimeError if any exist (planted row at M1 → upgrade refused, row intact).

Why both directions refuse: ADR 0193 makes a policy row cover one course, fixed
when written. Going down drops `course_id`, which would erase which course each
switch covered; going up would have to invent a course for a row that never named
one. Ruling 7 makes the table the record, so neither may happen silently.

**M2 is found, not named**: the one revision whose `down_revision` is M1's id,
`2c3d5a0de424` (`M2_DOWN_REVISION`). Each test migrates a throwaway database
(`empty_database`), never the session one (`docs/MISTAKES.md` entry 12), and
reads the catalog rather than the models, which describe head.

A refusal is the precedent's `RuntimeError`, found anywhere in the exception's
chain, so a SQL error a half-built migration trips over does not pass for one;
and the row is counted afterwards, so a guard that raised after dropping the
column is not mistaken for one that refused.

**Which failure a red is, on 6a7821c1** (per the review): the downgrade over a
row completes (the first test's `failure is not None` fails); the upgrade over a
row at M1 either completes or fails on something other than a `RuntimeError`.
The empty round trip and the three M1-shape checks are expected green there, and
are here as the twins the two refusals need.
"""

from typing import Any

import pytest
from fixtures.migration_journey import (
    MODEL_SCHEMA,
    columns_the_database_reports,
    migrate,
    session_on,
)
from fixtures.staff_names import POLICY_COURSE_COLUMN, RESPONSE_POLICY, require_the_tables
from fixtures.supervision import seed_row
from fixtures.the_hold import M2_DOWN_REVISION
from sqlalchemy import create_engine, inspect
from test_the_response_records_downgrade_refuses_while_a_row_exists import (
    a_lead_in_a_fresh_prefix,
    count,
    is_a_runtime_error,
    plant,
    plant_a_policy_row_at_m1,
    refused,
    write_a_policy_row_at_m1,
)

pytestmark = pytest.mark.integration

# ADR 0192's one index on `response_policy`, which M2 replaced with `(course_id,
# sequence)` (E7-02's work order, decision 1) and its downgrade puts back.
M1_POLICY_INDEX = ["prefix_id", "set_by_person_id", "role", "sequence"]

# What a refusal may not be: the statement naming something that is not there.
NOT_A_REFUSAL = ("42703", "42P01")


def the_m2_revision(config: Any) -> str:
    """The one revision chaining from M1's id, or a failure naming the work order."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(config)
    above = [
        revision.revision
        for revision in script.walk_revisions()
        if M2_DOWN_REVISION
        in (
            revision.down_revision
            if isinstance(revision.down_revision, tuple)
            else (revision.down_revision,)
        )
    ]
    if len(above) != 1:
        pytest.fail(
            f"{len(above)} revisions chain from `{M2_DOWN_REVISION}` ({above}). E7-02's work order "
            f'gives this ticket M2, with `down_revision = "{M2_DOWN_REVISION}"`.'
        )
    return above[0]


def upgrade_refused(config: Any, revision: str) -> BaseException | None:
    from alembic import command

    try:
        command.upgrade(config, revision)
    except Exception as refusal:
        return refusal
    return None


def policy_index_columns(database: Any) -> list[list[str]]:
    engine = create_engine(database.superuser_url)
    try:
        indexes = inspect(engine).get_indexes(RESPONSE_POLICY)
        return [list(index["column_names"]) for index in indexes]
    finally:
        engine.dispose()


def sqlstate_of(failure: Any) -> str | None:
    original = getattr(failure, "orig", failure)
    for attribute in ("sqlstate", "pgcode"):
        code = getattr(original, attribute, None)
        if isinstance(code, str):
            return code
    return None


def stepped_down_to_m1(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> Any:
    """An empty database brought to head, then walked down through M2 to M1. Its config."""
    require_the_tables(metadata_tables)
    config = alembic_config_pointed_at(empty_database)
    the_m2_revision(config)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    migrate(config, "downgrade", M2_DOWN_REVISION, "stepping below M2 over an empty policy table")
    return config


# ---------------------------------------------------------------------------
# H1 — the downgrade.
# ---------------------------------------------------------------------------


def test_the_m2_downgrade_refuses_while_a_policy_row_exists(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """One policy row at head: `downgrade 2c3d5a0de424` raises `RuntimeError`; the row and its course stay.

    **The mutation this kills:** a downgrade that drops `course_id` over a row,
    erasing which course a switch covered — and a guard that raised after the
    drop, which the column check below catches.
    """
    require_the_tables(metadata_tables)
    config = alembic_config_pointed_at(empty_database)
    m2 = the_m2_revision(config)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    plant(empty_database, metadata_tables, RESPONSE_POLICY)
    assert count(empty_database, RESPONSE_POLICY) == 1, "The planted policy row is not there."

    failure = refused(config, M2_DOWN_REVISION)

    assert failure is not None, (
        f"`alembic downgrade {M2_DOWN_REVISION}` completed over a policy row, dropping the course "
        f"it covered. Fix round H1: the downgrade of {m2} refuses while `response_policy` holds a "
        "row."
    )
    assert is_a_runtime_error(
        failure
    ), f"The downgrade failed with {failure!r}, not `RuntimeError`."
    assert count(empty_database, RESPONSE_POLICY) == 1, "After the refusal the policy row is gone."
    assert POLICY_COURSE_COLUMN in columns_the_database_reports(
        empty_database, RESPONSE_POLICY
    ), "After the refusal `response_policy` has no `course_id`: the guard raised after the drop."


def test_the_m2_downgrade_round_trips_over_an_empty_policy_table(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """Head, down to M1, head again, over no policy rows: `course_id` gone in the middle, then back.

    The twin the refusal above needs. **The mutation this kills:** a guard that
    refuses unconditionally, and a downgrade that does nothing (the middle check).
    """
    config = stepped_down_to_m1(empty_database, metadata_tables, alembic_config_pointed_at)

    at_m1 = columns_the_database_reports(empty_database, RESPONSE_POLICY)
    migrate(config, "upgrade", MODEL_SCHEMA, "re-applying M2 over an empty policy table")
    at_head = columns_the_database_reports(empty_database, RESPONSE_POLICY)

    assert (
        at_m1 and POLICY_COURSE_COLUMN not in at_m1
    ), f"At M1 `response_policy` carries {sorted(at_m1)}; M2's downgrade drops `course_id`."
    assert (
        POLICY_COURSE_COLUMN in at_head
    ), f"Back at head `response_policy` carries {sorted(at_head)}."


def test_the_m2_downgrade_puts_m1s_policy_index_back(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """At M1 after the step down, `response_policy` carries ADR 0192's `(prefix_id, set_by_person_id, role, sequence)`.

    **The mutation this kills:** a downgrade that drops M2's `(course_id,
    sequence)` index with its column and never recreates M1's, leaving the
    schema at M1 different from the one M1 built (`alembic check` would not see
    it from head).
    """
    stepped_down_to_m1(empty_database, metadata_tables, alembic_config_pointed_at)

    indexes = policy_index_columns(empty_database)

    assert M1_POLICY_INDEX in indexes, (
        f"At M1 `response_policy`'s indexes are {indexes}; M1 built {M1_POLICY_INDEX} (ADR 0192) "
        "and M2's downgrade puts it back."
    )


def test_the_m2_downgrade_puts_the_prefix_wide_setter_check_back(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """At M1 the guard is v001's again: a lead in the prefix writes a row with no course; a nobody is refused.

    The twin and the refusal together say which guard is installed. v002's
    per-course trigger reads `NEW.course_id`, which an M1 row has not got, so it
    would refuse the lead's row too (or fail naming the field); no guard at all
    would accept the nobody.

    **The mutations this kill:** a downgrade that leaves v002's trigger function
    in place, and one that drops the guard without restoring v001's.
    """
    stepped_down_to_m1(empty_database, metadata_tables, alembic_config_pointed_at)
    with session_on(empty_database) as session:
        prefix, lead = a_lead_in_a_fresh_prefix(session, metadata_tables)
        nobody = seed_row(session, metadata_tables, "person", {})["id"]

    accepted = write_a_policy_row_at_m1(empty_database, prefix=prefix, setter=lead)
    failure = write_a_policy_row_at_m1(empty_database, prefix=prefix, setter=nobody)

    assert accepted is None, (
        f"At M1 the course's lead could not write a policy row for its prefix: {accepted!r}. "
        "v001's guard accepts a setter who leads a course in the prefix; this is v002's still "
        "installed, or no working guard."
    )
    assert failure is not None and sqlstate_of(failure) not in NOT_A_REFUSAL, (
        f"At M1 a person holding no role wrote a policy row for the prefix and was answered "
        f"{failure!r}. v001's guard refuses them; the downgrade dropped the guard."
    )
    assert count(empty_database, RESPONSE_POLICY) == 1, "The policy table does not hold one row."


# ---------------------------------------------------------------------------
# H2 — the upgrade.
# ---------------------------------------------------------------------------


def test_the_m2_upgrade_refuses_while_a_policy_row_exists_at_m1(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """A policy row at M1: `upgrade` to M2 raises `RuntimeError`; the row stays and gains no course.

    The twin is the empty round trip above, whose step up completes.

    **The mutation this kills:** an `upgrade()` that adds `course_id NOT NULL`
    and fails on the row with a not-null violation (a SQL error, not the
    readable refusal H2 asks for), or one that backfills a course the row never
    named.
    """
    config = stepped_down_to_m1(empty_database, metadata_tables, alembic_config_pointed_at)
    plant_a_policy_row_at_m1(empty_database, metadata_tables)
    assert count(empty_database, RESPONSE_POLICY) == 1, "The planted policy row is not there."

    failure = upgrade_refused(config, MODEL_SCHEMA)

    assert failure is not None, (
        "`alembic upgrade head` completed over a policy row written at M1. Fix round H2: M2's "
        "`upgrade()` refuses while `response_policy` holds a row."
    )
    assert is_a_runtime_error(failure), f"The upgrade failed with {failure!r}, not `RuntimeError`."
    assert count(empty_database, RESPONSE_POLICY) == 1, "After the refusal the policy row is gone."
    assert POLICY_COURSE_COLUMN not in columns_the_database_reports(
        empty_database, RESPONSE_POLICY
    ), "After the refusal `response_policy` carries `course_id`: M2 ran part-way."
