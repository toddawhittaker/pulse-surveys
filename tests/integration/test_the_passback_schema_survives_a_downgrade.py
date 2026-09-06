"""E3-02 criterion 4 — the migration round-trips, with the schema compared.

> The migration round-trips: upgrade, downgrade, upgrade, with the schema compared
> rather than assumed, and `alembic check` clean.

E2-16 repaired two irreversible revisions after the fact; this one is written
reversible from the start, and this module is what says so before anybody runs
`alembic downgrade` on a real database. The ticket's own known-traps list puts it
plainly: a migration that stops part-way leaves a database nobody has described.

**Schema, not rows, and the criterion says which.** What is compared here is the
shape the upgrade produces: the columns of the two new tables and of `section`,
with their types, their nullability and their defaults, and the indexes on
`grade_sync`. Nothing here requires a downgrade to *preserve* the values in a
column it drops — that is a different property, it is E2-16's criterion rather
than this one, and asserting it here would demand a preserve-and-restore this
ticket never asked for. What it does require is that going down and coming back up
lands on the same schema rather than a similar one.

**The control that makes the trip mean anything is asserted in the middle**: at
the revision below, the two tables and the two new `section` columns really are
gone. A downgrade that quietly did nothing would round-trip perfectly and prove
nothing at all (`docs/MISTAKES.md` entry 3), and an empty `downgrade()` body is
the single most likely way this criterion is met without being satisfied.

**The revision is found by walking rather than named**, and that is deliberate
rather than a shortcut. Every other round-trip module in this suite pins a
revision identifier at the top of the file, which it can because the revision
already existed when the test was written. This one is written before the
migration is, so there is no identifier to pin: the database is walked down one
step at a time until `grade_sync` is no longer there, which is also the assertion
that *some* revision drops it. The walk is bounded, and running past the bound is
a failure saying so rather than a hang.

**Each test migrates a database of its own.** `empty_database` is a second
database in the same container, created for one test and dropped after, so a
downgrade here cannot touch the session database every other integration test
reads (`docs/MISTAKES.md` entry 12).

**`alembic check` is not asserted here.** `tests/integration/test_alembic_baseline.py`
runs `command.check` against a freshly upgraded database and is where drift
between the declaration and the migration is diagnosed, for every ticket. Two
tests of one rule is `docs/MISTAKES.md` entry 19's shape.

**Which failure a red here is.** Before E3-02 lands, both tests fail on the
assertion that the migrated schema carries `grade_sync` at all — a failed
assertion naming the table, before any migration is run backwards.
"""

from typing import Any

import pytest
from fixtures.indexes import index_key_columns
from fixtures.migration_journey import MODEL_SCHEMA, columns_the_database_reports, migrate
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

# The two tables E3-02 creates and the table it adds two columns to.
GRADE_SYNC = "grade_sync"
AGS_CALL = "ags_call"
SECTION = "section"

# The two columns E3-02 adds to `section`, spelled by the work order.
AGS_ADDRESS_COLUMN = "lms_ags_line_items_url"
LINE_ITEM_COLUMN = "ags_line_item_url"

# How many revisions the walk down may cross before it is called broken rather
# than long. E3-02's revision sits at or near the head of a branch with two
# tickets on it, so anything past this is a downgrade that is not undoing what it
# is supposed to undo — or a `downgrade()` that does nothing, which is the failure
# the control in the middle of each test is written against.
MOST_STEPS_DOWN = 12

# What the schema of one table is read as. `column_default` is included and is not
# decoration: a server default is the difference between a primary key the database
# generates and one a writer has to supply (ADR 0016), and between a `created_at`
# that stamps itself and one that does not — and a re-upgrade that lost a default
# would otherwise compare equal.
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

    Sorted by name rather than by ordinal position, deliberately: a re-upgrade that
    adds a dropped column back at the end of the row is the same schema for every
    purpose this project has, and comparing positions would fail a correct
    migration for a reason nobody would want to fix.
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


def indexes_on(database: Any, table: str) -> dict[str, list[tuple[str, bool]]]:
    """Every index on one table, as its key columns in order with their descending flags."""
    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            return index_key_columns(connection, table)
    finally:
        engine.dispose()


def walk_down_until_the_passback_tables_are_gone(config: Any, database: Any) -> int:
    """Downgrade one revision at a time until `grade_sync` is not there, and say how far.

    The walk is what stands in for a named revision, since this module is written
    before the migration exists. Crossing more than one revision is expected and
    harmless: E3 builds two tickets off one head, so whatever landed above this one
    is undone on the way past, and the comparison afterwards is over the objects
    E3-02 owns.
    """
    for step in range(1, MOST_STEPS_DOWN + 1):
        migrate(config, "downgrade", "-1", f"stepping one revision below head, step {step}")
        if not columns_the_database_reports(database, GRADE_SYNC):
            return step
    pytest.fail(
        f"After {MOST_STEPS_DOWN} downgrade steps `{GRADE_SYNC}` is still in the database, so no "
        "revision crossed drops it. E3-02's migration is required to be reversible, and a "
        "`downgrade()` that leaves its own table behind is the shape E2-16 was written to repair: "
        "an operator who goes down cannot come back up, because the upgrade then meets a table it "
        "is about to create."
    )


def test_the_passback_schema_is_the_same_after_a_downgrade_and_a_re_upgrade(
    empty_database: Any, alembic_config_pointed_at: Any
) -> None:
    """Criterion 4: upgrade, downgrade, upgrade, and the schema is compared rather than assumed.

    The comparison is over the two tables E3-02 creates and over `section`, which it
    adds two columns to — every column, with its type, its nullability and its
    default. `section` is in the comparison because the ticket's riskiest edit is
    there: it is a table every fixture in this suite builds, and a downgrade that
    dropped one column too many, or a re-upgrade that added a column back with a
    different type, would leave a schema that looks right and is not.

    **The mutation this kills:** a `downgrade()` that drops the two tables and
    forgets the two `section` columns, so the re-upgrade meets columns it is about
    to add and aborts. That is the E2-16 shape exactly, and today's version of it
    fails on the upgrade step with Alembic's own error rather than on a comparison
    — which is why `migrate` reports a step that did not complete as its own
    failure.

    **The near miss it must survive:** a downgrade that drops the tables with
    `IF EXISTS` and does nothing else. That completes, and the control in the
    middle is what catches it: at the revision below, the two `section` columns
    have to be gone too.

    **What this does not assert**, said out loud rather than left looking like
    coverage (`docs/MISTAKES.md` entry 14): that the *rows* in a dropped column
    survive the trip. A nullable column dropped on the way down and re-added empty
    on the way up satisfies this criterion, which is what the criterion asks for —
    E2-16's is the ticket about preserving values, and this ticket's migration
    creates the tables the values would be in.
    """
    config = alembic_config_pointed_at(empty_database)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")

    compared = (GRADE_SYNC, AGS_CALL, SECTION)
    before = schema_of(empty_database, compared)
    assert before[GRADE_SYNC] and before[AGS_CALL], (
        f"After an upgrade to the models' schema the database reports "
        f"{len(before[GRADE_SYNC])} columns on `{GRADE_SYNC}` and {len(before[AGS_CALL])} on "
        f"`{AGS_CALL}`. E3-02 creates both — SPEC §8 names them in its table list — and a round "
        "trip over tables that are not there compares two empty lists and calls it a success."
    )
    for column in (AGS_ADDRESS_COLUMN, LINE_ITEM_COLUMN):
        assert column in {row[0] for row in before[SECTION]}, (
            f"`{SECTION}` carries no `{column}` after an upgrade to the models' schema; it carries "
            f"{sorted(row[0] for row in before[SECTION])}. E3-02 adds both gradebook columns, and "
            "a comparison across a downgrade would be about a column that was never there."
        )

    steps = walk_down_until_the_passback_tables_are_gone(config, empty_database)

    standing = {name: columns_the_database_reports(empty_database, name) for name in compared}
    assert not standing[AGS_CALL], (
        f"After walking {steps} revision(s) below head, `{GRADE_SYNC}` is gone and `{AGS_CALL}` "
        f"still carries {sorted(standing[AGS_CALL])}. One migration creates both, so its downgrade "
        "drops both; a table left behind is one the re-upgrade is about to try to create."
    )
    left = sorted(
        column for column in (AGS_ADDRESS_COLUMN, LINE_ITEM_COLUMN) if column in standing[SECTION]
    )
    assert not left, (
        f"After walking {steps} revision(s) below head, `{SECTION}` still carries {left}. The same "
        "revision adds them, so a downgrade that leaves them is not undoing it — and 'the schema "
        "survived the round trip' would then be true of a migration pair that did nothing in "
        "either direction."
    )

    migrate(config, "upgrade", MODEL_SCHEMA, "re-applying every revision the walk undid")

    after = schema_of(empty_database, compared)
    for name in compared:
        assert after[name] == before[name], (
            f"`{name}` is not the same after the round trip.\n"
            f"  before: {before[name]}\n"
            f"  after:  {after[name]}\n"
            "Each row is `(column, type, nullable, default)`. A re-upgrade that changes a type, a "
            "nullability or a server default has produced a database that no longer matches the "
            "one the first upgrade produced, and only the operator who downgraded has it."
        )


def test_the_index_the_latest_row_lookup_runs_on_comes_back_with_the_table(
    empty_database: Any, alembic_config_pointed_at: Any
) -> None:
    """The other half of the same trip: an index is part of the schema, not part of the table.

    `grade_sync`'s composite is what makes "the latest row for this student in this
    section" cheap on E3-06's hot path, and it is the easiest thing in a migration
    to lose across a round trip: a downgrade drops the table and takes the index
    with it, and an upgrade that creates the table without re-creating the index
    leaves a database that holds every row and answers every query slowly. Nothing
    else notices — `alembic check` compares the declaration with the database, so it
    would report the drift, but only if the index is declared in the comparable
    ascending form E2-02's lesson requires.

    **The mutation this kills:** the index created outside the revision that creates
    the table — by hand, or in a later revision the downgrade does not reach — so
    that it exists on the database the tests ran against and on no database anybody
    rebuilds.

    **Its pair** is the schema comparison above: without it, an index that came back
    on a table whose columns did not would still pass here.
    """
    config = alembic_config_pointed_at(empty_database)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")

    before = indexes_on(empty_database, GRADE_SYNC)
    assert before, (
        f"The catalog reports no index at all on `{GRADE_SYNC}` after an upgrade to the models' "
        "schema, not even a primary key's — so either the table is not there, which "
        "`test_the_passback_tables_record_one_post_per_row.py` diagnoses by name, or this reader "
        "is looking somewhere the migrated schema is not."
    )

    steps = walk_down_until_the_passback_tables_are_gone(config, empty_database)
    migrate(config, "upgrade", MODEL_SCHEMA, f"re-applying the {steps} revision(s) the walk undid")

    after = indexes_on(empty_database, GRADE_SYNC)
    assert after == before, (
        f"The indexes on `{GRADE_SYNC}` are not the same after the round trip.\n"
        f"  before: {before}\n"
        f"  after:  {after}\n"
        "Each entry is an index name against its key columns as `(column, descending)`. An index "
        "that does not come back leaves the recompute's per-student lookup on a sequential scan "
        "against a table that takes a row per post all term, and nothing raises about it."
    )
