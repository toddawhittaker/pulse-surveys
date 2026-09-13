"""E5-01 criterion 5 — the migration round-trips, with the schema compared.

> `alembic upgrade`/`downgrade` both succeed; `alembic check` is clean.

**`alembic check` is deliberately not asserted here.**
`tests/integration/test_alembic_baseline.py` runs `command.check` against a
freshly upgraded database for every ticket, and two tests of one rule is
`docs/MISTAKES.md` entry 19's shape. What that module cannot say is whether this
revision comes *back*: `check` compares the declaration against a database at
head and never runs a downgrade at all.

**Schema, not rows.** What is compared is the shape the upgrade produces — every
column of the two new tables with its type, its nullability and its default —
across a downgrade and a re-upgrade. Nothing here requires a downgrade to preserve
values in a table it drops; that is a different property and this ticket's tables
are created rather than altered, so there is nothing to preserve.

**The control that makes the trip mean anything is asserted in the middle**: at
the revision below, both tables really are gone. A `downgrade()` with an empty
body round-trips perfectly and proves nothing (`docs/MISTAKES.md` entry 3), and an
empty body is the single most likely way this criterion is met without being
satisfied.

**The revision is found by walking rather than named**, following
`test_the_passback_schema_survives_a_downgrade.py`, which faced the same problem:
this module is written before the migration exists, so there is no identifier to
pin. The database is walked down one step at a time until `comparison_set` is no
longer there, which is also the assertion that *some* revision drops it. The walk
is bounded and running past the bound is a failure saying so rather than a hang —
and the bound is generous because E5 cuts two migration-adding tickets off one
head, so whatever landed above this one is undone on the way past.

**Each test migrates a database of its own.** `empty_database` is a second
database in the same container, created for one test and dropped after, so a
downgrade here cannot touch the session database every other integration test
reads (`docs/MISTAKES.md` entry 12).

**Which failure a red here is, before E5-01 lands.** Both tests fail on the
assertion that the migrated schema carries `comparison_set` at all — a failed
assertion naming the table, before any migration is run backwards.
"""

from typing import Any

import pytest
from fixtures.comparison_sets import (
    COMPARISON_SET_TABLE,
    EXPECTED_MEMBERSHIP_TABLE,
    LENGTH_COLUMN,
    LEVEL_COLUMN,
    NUMBER_BY_LEVEL,
    assert_refused_for_the_data,
    comparison_set_table,
    course_at,
    member_of,
    membership_table,
    refusal_of,
    require_columns,
    write_set,
)
from fixtures.migration_journey import (
    MODEL_SCHEMA,
    columns_the_database_reports,
    migrate,
    session_on,
)
from fixtures.supervision import seed_row
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

# The two tables E5-01 creates. The membership table is named rather than
# discovered here for the reason the grants module gives: this one asks the
# database's catalog, and a catalog takes a name.
THE_TABLES = (COMPARISON_SET_TABLE, EXPECTED_MEMBERSHIP_TABLE)

# How many revisions the walk down may cross before it is called broken rather
# than long. E5-01's revision takes the first slot off head `e5a2b81c47d3` and
# E5-03 takes the second, so at merge time there may be a handful above it;
# anything past this bound is a downgrade that is not undoing what it should — or
# a `downgrade()` that does nothing, which the control in the middle catches.
MOST_STEPS_DOWN = 12

SCHEMA_OF_ONE_TABLE = text(
    """
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = :table
    ORDER BY column_name
    """
)


def schema_of(database: Any, tables: tuple[str, ...]) -> dict[str, list[tuple[Any, ...]]]:
    """Each table's columns, with type, nullability and default, sorted by name.

    `column_default` is read and is not decoration: a server default is the
    difference between a primary key the database generates and one a writer has
    to supply (ADR 0016), and a re-upgrade that lost one would otherwise compare
    equal. Sorted by name rather than by ordinal, because a column re-added at the
    end of the row is the same schema for every purpose this project has.
    """
    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            return {
                name: [
                    tuple(row) for row in connection.execute(SCHEMA_OF_ONE_TABLE, {"table": name})
                ]
                for name in tables
            }
    finally:
        engine.dispose()


def walk_down_until_the_comparison_tables_are_gone(config: Any, database: Any) -> int:
    """Downgrade one revision at a time until `comparison_set` is not there, and say how far."""
    for step in range(1, MOST_STEPS_DOWN + 1):
        migrate(config, "downgrade", "-1", f"stepping one revision below head, step {step}")
        if not columns_the_database_reports(database, COMPARISON_SET_TABLE):
            return step
    pytest.fail(
        f"After {MOST_STEPS_DOWN} downgrade steps `{COMPARISON_SET_TABLE}` is still in the "
        "database, so no revision crossed drops it. E5-01's migration is required to be "
        "reversible, and a `downgrade()` that leaves its own table behind is the shape E2-16 was "
        "written to repair: an operator who goes down cannot come back up, because the upgrade "
        "then meets a table it is about to create."
    )


def test_the_comparison_set_schema_is_the_same_after_a_downgrade_and_a_re_upgrade(
    empty_database: Any, alembic_config_pointed_at: Any
) -> None:
    """Criterion 5: upgrade, downgrade, upgrade, with the schema compared rather than assumed.

    **The mutation it kills:** a `downgrade()` that drops `comparison_set` and
    forgets its membership table, so the re-upgrade meets a table it is about to
    create and aborts — `migrate` reports a step that did not complete as its own
    failure, so that lands as a red here rather than as a puzzle later.

    **The near miss it must survive:** a downgrade that drops both tables with
    `IF EXISTS` and does nothing else. That completes, and the control in the
    middle is what makes it a pass rather than a hole: both tables have to be gone
    at the revision below.

    **What this does not assert**, said out loud rather than left looking like
    coverage (`docs/MISTAKES.md` entry 14): anything about the `course_level`
    enumerated type the level column uses. E5-01 uses the type that already
    exists rather than creating a second one, so a downgrade has nothing to drop
    there — and a downgrade that dropped it anyway would take `course.level` with
    it, which is a failure of the upgrade step this trip runs and would surface as
    one.
    """
    config = alembic_config_pointed_at(empty_database)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")

    before = schema_of(empty_database, THE_TABLES)
    for name in THE_TABLES:
        assert before[name], (
            f"After an upgrade to the models' schema the database reports no columns on "
            f"`{name}`. SPEC §8 lists `comparison_set` in its table inventory and E5-01 creates "
            "it with its membership relation; a round trip over tables that are not there "
            "compares two empty lists and calls it a success."
        )

    steps = walk_down_until_the_comparison_tables_are_gone(config, empty_database)

    left = sorted(name for name in THE_TABLES if columns_the_database_reports(empty_database, name))
    assert not left, (
        f"After walking {steps} revision(s) below head, {left} are still in the database while "
        f"`{COMPARISON_SET_TABLE}` is gone. One migration creates both tables, so its downgrade "
        "drops both; a table left behind is one the re-upgrade is about to try to create."
    )

    migrate(config, "upgrade", MODEL_SCHEMA, "re-applying every revision the walk undid")

    after = schema_of(empty_database, THE_TABLES)
    for name in THE_TABLES:
        assert after[name] == before[name], (
            f"`{name}` is not the same after the round trip.\n"
            f"  before: {before[name]}\n"
            f"  after:  {after[name]}\n"
            "Each row is `(column, type, nullable, default)`. A re-upgrade that changes a type, a "
            "nullability or a server default has produced a database that no longer matches the "
            "one the first upgrade produced, and only the operator who downgraded has it."
        )


def test_the_level_agreement_still_refuses_a_cross_level_member_after_the_round_trip(
    empty_database: Any, alembic_config_pointed_at: Any, metadata_tables: dict[str, Any]
) -> None:
    """The half a column comparison cannot see: the constraints come back too.

    `information_schema.columns` says nothing about a `CHECK`, a `UNIQUE` or a
    foreign key, so the comparison above is satisfied by a re-upgrade that
    re-creates both tables with none of criterion 2's rules on them. That database
    holds every column and accepts the exact row §5.1 says is not a comparison —
    and it is the database an operator who downgraded is left with.

    **The mutation it kills:** the constraints created outside the revision that
    creates the tables — by hand against the development database, or in a later
    revision the walk does not reach — so they exist where the tests ran and on no
    database anybody rebuilds.

    **Its pair is the comparison above**: constraints that came back on tables
    whose columns did not would pass here and fail there.
    """
    require_columns(
        comparison_set_table(metadata_tables),
        (LENGTH_COLUMN, LEVEL_COLUMN),
        "E5-01 gives `comparison_set` a declared length and a declared level.",
    )
    membership = membership_table(metadata_tables)

    config = alembic_config_pointed_at(empty_database)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    steps = walk_down_until_the_comparison_tables_are_gone(config, empty_database)
    migrate(config, "upgrade", MODEL_SCHEMA, f"re-applying the {steps} revision(s) the walk undid")

    with session_on(empty_database) as session:

        def seed(name: str, chain: dict[str, Any] | None = None, **overrides: Any) -> Any:
            return seed_row(session, metadata_tables, name, chain, **overrides)

        stored_set = write_set(seed, length=6, level="UG")
        matching = course_at(seed, "UG")
        control = refusal_of(session, lambda: member_of(seed, membership, stored_set, matching))
        assert control is None, (
            f"After the round trip a matching member was refused: {control}. Until an ordinary "
            "member inserts, the refusal below says nothing about the level rule."
        )

        off_level = course_at(seed, "GR")
        crossed = refusal_of(session, lambda: member_of(seed, membership, stored_set, off_level))
        assert_refused_for_the_data(
            crossed,
            "After a downgrade and a re-upgrade, a GR course named as a member of a UG set",
            "The columns came back and the rule did not. SPEC §5.1's exact level match is the "
            f"whole of what makes a set comparable, and a course numbered "
            f"{NUMBER_BY_LEVEL['GR']!r} in a set declaring `UG` is the row criterion 2 refuses on "
            "a database that has only ever been upgraded.",
        )
