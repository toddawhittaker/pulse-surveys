"""E4-02 criterion 1 — the migration runs both ways, over rows that are already there.

> `alembic upgrade head` and a full downgrade both succeed against a seeded
> database, and `alembic check` reports no drift.

Three of those four words are the reason this module exists rather than being
covered by `tests/integration/test_alembic_baseline.py`, which upgrades an
**empty** database and is where `alembic check` is asserted for every ticket
(two tests of one rule is `docs/MISTAKES.md` entry 19's shape). What is new here
is *seeded*: this ticket is the first in the epic to add a column to a table that
already holds rows in every environment, and `question.stream` arrives under a
`CHECK` that no existing row can satisfy until the migration fills it. An upgrade
that creates the constraint before the backfill aborts against any database with
a question set in it and passes against an empty one.

**So the backfill is asserted from below the revision, not from above it.** A
database is taken to head, its rows are put there, and it is then walked *down*
until the column is gone and back up — which is the only arrangement in which the
migration's own backfill is the thing that filled the column. Reading the streams
off a freshly seeded database would measure `scripts/seed.py` instead, and would
be green against a migration whose backfill does nothing.

**Two of these tests seed with the demo seed and two plant their own rows**, and
the split is deliberate. `scripts/seed.py` writes SPEC §3.2's five questions, so
it is the real v1 set the backfill exists for and the one criterion 1's word
"seeded" means. It is also exactly five rows at exactly five positions, which
says nothing about the sixth — and the suite itself writes questions at other
positions, so a backfill that covers §3.2's five and no more turns other
modules red inside their own fixtures. The planted half asks that question and
asks nothing about which stream a sixth question gets, because the ticket does
not settle it.

**Each test migrates a database of its own**, so a downgrade here cannot touch
the session database every other integration test reads (`docs/MISTAKES.md`
entry 12).

**Which failure a red is, before the ticket lands.** Each test fails on the
assertion that the migrated schema carries the report tables, or `question.stream`,
at all — a failed assertion naming what is missing, before any migration is run
backwards.
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
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

# The four tables E4-02 creates, and the column it adds to a table that already
# holds rows.
WEEKLY_SUMMARY = "weekly_summary"
MODERATION_STATE = "moderation_state"
RELEASE_BATCH = "release_batch"
RELEASE_BATCH_MEMBER = "release_batch_member"
REPORT_TABLES = (WEEKLY_SUMMARY, MODERATION_STATE, RELEASE_BATCH, RELEASE_BATCH_MEMBER)

QUESTION = "question"
QUESTION_SET = "question_set"
POSITION_COLUMN = "position"
KIND_COLUMN = "kind"
STREAM_COLUMN = "stream"

WORKLOAD_KIND = "workload"
LIKERT_KIND = "likert"
COMMENT_KIND = "comment"

INSTRUCTOR_STREAM = "INSTRUCTOR"
COURSE_STREAM = "COURSE"
STREAMS = (INSTRUCTOR_STREAM, COURSE_STREAM)

# SPEC §3.2's five, by ordinal, and the stream each one asks about: "1. Instructor
# rating … 2. Instructor comment … 3. Course rating … 4. Course comment …
# 5. Workload". The workload question belongs to neither of §5.1's two groups, so
# its stream is nothing at all. **This mapping is read out of the spec**, not out
# of the migration that implements it (`docs/MISTAKES.md` entry 19: a test that
# holds its expectation in a copy of the thing it is checking asserts that the
# code agrees with itself).
STREAM_OF_SPEC_POSITION: dict[int, str | None] = {
    1: INSTRUCTOR_STREAM,
    2: INSTRUCTOR_STREAM,
    3: COURSE_STREAM,
    4: COURSE_STREAM,
    5: None,
}

# Positions outside §3.2's five, planted to ask whether the backfill is total.
# `question_set` is versioned precisely so a set can change (§3.2, §3.4), and the
# seeding walker in this suite invents an ordinal for every question it writes, so
# rows at these positions exist in this repository already.
A_SIXTH_POSITION = 6
A_SEVENTH_POSITION = 7
AN_EIGHTH_POSITION = 8

# How many revisions a walk down may cross before it is called broken rather than
# long. E4-02's revision is the first slot off the head this branch was cut from,
# and two other tickets take the slots beside it, so anything past this is a
# downgrade that is not undoing what it is supposed to undo.
MOST_STEPS_DOWN = 12

SCHEMA_OF_ONE_TABLE = text(
    """
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = :table
    ORDER BY column_name
    """
)

QUESTIONS_WITH_THEIR_STREAMS = text(
    "SELECT position, kind::text AS kind, stream FROM public.question ORDER BY position"
)
QUESTIONS_BELOW_THE_REVISION = text(
    "SELECT position, kind::text AS kind FROM public.question ORDER BY position"
)


def schema_of(database: Any, tables: tuple[str, ...]) -> dict[str, list[tuple[Any, ...]]]:
    """Each table's columns, with type, nullability and default, sorted by name.

    Sorted by name rather than by ordinal position: a re-upgrade that adds a
    dropped column back at the end of the row is the same schema for every purpose
    this project has. `column_default` is in the reading and is not decoration — a
    server default is the difference between a `generated_at` that stamps itself
    and one a writer has to supply (ADR 0016 for the keys, and the same for
    `cut_at`), and a re-upgrade that lost one would otherwise compare equal.
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


def require_the_report_schema(database: Any) -> None:
    """Stop unless the migrated database carries what E4-02 adds.

    In the test body rather than in a fixture, so that a tree without the ticket in
    it produces failed assertions naming the missing tables rather than errors in
    setup (`docs/MISTAKES.md` entry 44). This is the intended red while the ticket
    is unbuilt.
    """
    missing = [name for name in REPORT_TABLES if not columns_the_database_reports(database, name)]
    if missing:
        pytest.fail(
            f"After an upgrade to the models' schema the database has no {missing}. E4-02 creates "
            f"{list(REPORT_TABLES)}, and a round trip over tables that are not there compares two "
            "empty lists and calls it a success."
        )
    on_question = columns_the_database_reports(database, QUESTION)
    if STREAM_COLUMN not in on_question:
        pytest.fail(
            f"`{QUESTION}` carries {sorted(on_question)} and none of them is `{STREAM_COLUMN}`. "
            "E4-02 adds it and backfills the rows already there; a walk down looking for a column "
            "that was never added would run to its bound and report the wrong thing."
        )


def walk_down_until_the_stream_column_is_gone(config: Any, database: Any) -> int:
    """Downgrade one revision at a time until `question.stream` is not there, and say how far.

    The walk stands in for a named revision, since this module is written before
    the migration exists. Crossing more than one revision is expected: E4 builds
    several tickets off one head, so whatever landed above this one is undone on
    the way past.
    """
    for step in range(1, MOST_STEPS_DOWN + 1):
        migrate(config, "downgrade", "-1", f"stepping one revision below head, step {step}")
        if STREAM_COLUMN not in columns_the_database_reports(database, QUESTION):
            return step
    pytest.fail(
        f"After {MOST_STEPS_DOWN} downgrade steps `{QUESTION}` still carries `{STREAM_COLUMN}`, so "
        "no revision crossed drops it. E4-02's migration is required to be reversible, and a "
        "`downgrade()` that leaves its own column behind is a database an operator cannot come "
        "back up from: the upgrade then meets a column it is about to add."
    )


def questions_in(database: Any) -> list[dict[str, Any]]:
    """Every question row with its ordinal, its kind and its stream."""
    with session_on(database) as session:
        return [dict(row) for row in session.execute(QUESTIONS_WITH_THEIR_STREAMS).mappings()]


def questions_below_the_revision(database: Any) -> list[dict[str, Any]]:
    """Every question row with its ordinal and its kind, read where there is no stream column."""
    with session_on(database) as session:
        return [dict(row) for row in session.execute(QUESTIONS_BELOW_THE_REVISION).mappings()]


def test_a_seeded_database_downgrades_all_the_way_to_base(
    demo_databases: Any, alembic_config_pointed_at: Any
) -> None:
    """Criterion 1: a full downgrade succeeds against a database with rows in it.

    "Full" is the word that makes this different from the round trip below: the
    chain is run to `base`, so E4-02's downgrade runs against a populated database
    and then every revision under it does too. What that catches is a downgrade
    that cannot drop what it created while something references it — a foreign key
    from the membership table to `answer`, or a constraint dropped in the wrong
    order — none of which an empty database can show.

    **The seed is the control**, and it is asserted rather than assumed: a seed run
    that failed would leave a database as empty as `test_alembic_baseline.py`'s,
    and the downgrade would then prove nothing this repository did not already
    know (`docs/MISTAKES.md` entry 3). `scripts/seed.py` writes SPEC §3.2's five
    questions among the rest, which is also the population `question.stream`'s
    backfill has to have handled for the upgrade to have got here at all.

    **The mutation it kills:** `downgrade()` left as a `pass`, which is the single
    most likely way this criterion is met without being satisfied — and, one step
    subtler, a downgrade that drops `release_batch` before `release_batch_member`,
    which succeeds on an empty database and refuses on a populated one.
    """
    demo = demo_databases()
    run = demo.run()
    assert run.succeeded, (
        "The demo seed did not run, so what is downgraded below is an empty database and this "
        f"test's subject — a *seeded* one — is not what was measured.\n\n{run.report()}"
    )
    require_the_report_schema(demo.database)

    seeded = questions_in(demo.database)
    assert seeded, (
        f"`{QUESTION}` holds no rows after the seed ran successfully, so the full downgrade below "
        "would be over a database with nothing in the table this ticket alters. "
        "`tests/integration/test_demo_seed_script.py` is where a seed that writes no question set "
        "is diagnosed."
    )

    config = alembic_config_pointed_at(demo.database)
    migrate(config, "downgrade", "base", "taking a seeded database all the way down")

    standing = {
        name: sorted(columns_the_database_reports(demo.database, name))
        for name in (*REPORT_TABLES, QUESTION)
    }
    left = {name: columns for name, columns in standing.items() if columns}
    assert not left, (
        f"After `alembic downgrade base` the database still holds {left}. A full downgrade unwinds "
        "the whole chain, so every table any revision created is gone — a table left behind is one "
        "the next upgrade is about to try to create, and the operator who ran the downgrade is the "
        "only person who has that database."
    )


def test_the_report_schema_is_the_same_after_a_downgrade_and_a_re_upgrade(
    empty_database: Any, alembic_config_pointed_at: Any
) -> None:
    """Criterion 1's other half: down one revision and back up lands on the same schema.

    The comparison is over the four tables E4-02 creates and over `question`,
    which it adds a column to — every column, with its type, its nullability and
    its default. `question` is in the comparison because the ticket's riskiest edit
    is there: it is a table this suite's fixtures build constantly, and a
    re-upgrade that added `stream` back with a different nullability would leave a
    schema that looks right and is not.

    **The control that makes the trip mean anything is asserted in the middle**: at
    the revision below, the four tables and the column really are gone. A
    downgrade that quietly did nothing would round-trip perfectly and prove
    nothing at all (`docs/MISTAKES.md` entry 3).

    **The mutation it kills:** a `downgrade()` that drops the four tables and
    forgets `question.stream`, so the re-upgrade meets a column it is about to add
    and aborts — which is the shape E2-16 was written to repair, one epic back.

    **What this does not assert**, said out loud rather than left looking like
    coverage (`docs/MISTAKES.md` entry 14): that the *values* in the dropped column
    survive the trip. They cannot — the column is dropped — and what replaces them
    on the way up is the backfill, which the two tests below are about.
    """
    config = alembic_config_pointed_at(empty_database)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    require_the_report_schema(empty_database)

    compared = (*REPORT_TABLES, QUESTION)
    before = schema_of(empty_database, compared)

    steps = walk_down_until_the_stream_column_is_gone(config, empty_database)

    standing = {
        name: sorted(columns_the_database_reports(empty_database, name)) for name in REPORT_TABLES
    }
    still_there = {name: columns for name, columns in standing.items() if columns}
    assert not still_there, (
        f"After walking {steps} revision(s) below head, `{QUESTION}.{STREAM_COLUMN}` is gone and "
        f"{still_there} are still here. One revision creates the four tables and adds the column, "
        "so its downgrade takes all five away; a table left behind is one the re-upgrade is about "
        "to try to create, and 'the schema survived the round trip' would then be true of a "
        "migration pair that did nothing in either direction."
    )

    migrate(config, "upgrade", MODEL_SCHEMA, f"re-applying the {steps} revision(s) the walk undid")

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


def test_the_upgrade_gives_the_seeded_question_set_the_streams_spec_3_2_describes(
    demo_databases: Any, alembic_config_pointed_at: Any
) -> None:
    """The backfill, over the rows the shipped instrument really consists of.

    SPEC §3.2 numbers the five: the instructor rating and the instructor comment,
    then the course rating and the course comment, then the workload figure, which
    belongs to neither of §5.1's two groups. The column is what carries that fact
    from here on, and every question written before this migration has to be given
    it — there is no other source, so a row the backfill misses is a question no
    later ticket can place.

    **The rows come from `scripts/seed.py` and the expectation comes from the
    spec.** Neither is a copy of the migration (`docs/MISTAKES.md` entry 19), and
    the set is the one criterion 1 means by "a seeded database" rather than five
    rows this module wrote to suit itself.

    **The database is walked below the revision first**, which is the whole design
    of the case: at head the column holds whatever wrote it, and only after the
    column has been dropped and re-added is its content the migration's own doing.
    The control in the middle is that the five rows are still there with the
    column gone — a downgrade that dropped the question set would leave this test
    reading an empty table and finding nothing to disagree with.

    **The mutation it kills:** a backfill that maps every non-workload question to
    one stream, which satisfies both of the ticket's `CHECK`s and puts §3.2's
    course questions into the instructor's group on every screen in the product.
    """
    demo = demo_databases()
    run = demo.run()
    assert run.succeeded, (
        "The demo seed did not run, so there is no seeded question set for the backfill to have "
        f"filled and this test would assert over an empty table.\n\n{run.report()}"
    )
    require_the_report_schema(demo.database)

    config = alembic_config_pointed_at(demo.database)
    steps = walk_down_until_the_stream_column_is_gone(config, demo.database)

    below = questions_below_the_revision(demo.database)
    assert len(below) == len(STREAM_OF_SPEC_POSITION), (
        f"After walking {steps} revision(s) below head the database holds {len(below)} question "
        f"row(s) and the seed writes {len(STREAM_OF_SPEC_POSITION)} — SPEC §3.2's five. A "
        "downgrade that took the rows with the column leaves nothing for the backfill to fill, and "
        "every assertion below would be satisfied by an empty table."
    )

    migrate(config, "upgrade", MODEL_SCHEMA, f"re-applying the {steps} revision(s) the walk undid")

    filled = {row[POSITION_COLUMN]: row[STREAM_COLUMN] for row in questions_in(demo.database)}
    assert filled == STREAM_OF_SPEC_POSITION, (
        f"The backfilled streams are {filled}; SPEC §3.2 describes {STREAM_OF_SPEC_POSITION}. "
        "Questions 1 and 2 ask about the instructor, 3 and 4 about the course materials and "
        "activities, and 5 is hours spent, which §5.1 groups under neither heading. A question in "
        "the wrong group is a comment rendered under the wrong summary on the instructor's report, "
        "on the student's results page and in every roll-up above them — and nothing downstream "
        "can tell, because this column is the only place the fact is written down."
    )


def test_the_upgrade_gives_a_stream_to_every_question_it_finds(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """The backfill is total, whatever ordinal a question was written at.

    §3.2's five are the shipped set, and the versioned `question_set` exists
    precisely so that a set can be a different size (§3.2's own sentence, and
    §3.4's denominator "is never a constant"). This suite's fixtures already write
    questions at other ordinals. So the migration meets rows the five-position
    mapping says nothing about, and a `CHECK` created over a row the backfill
    skipped aborts the upgrade — for everyone, on a database nobody can then take
    back down without repeating the trip.

    **What is asserted is that every non-workload question has a stream, and not
    which one.** The ticket settles the mapping for §3.2's five and settles nothing
    for a sixth; a test that demanded a particular answer there would be deciding
    something the ticket left open. What it does demand is that no row is left in
    the state the first `CHECK` forbids — which is a consequence of the constraint
    rather than a policy, since the alternative is an upgrade that does not
    complete.

    **The workload row is the other half**, and it is not decoration: a backfill
    written as "give everything a stream" satisfies the non-null half of this test
    perfectly and breaks the second rule the other way.

    **The values planted at head are not the subject and are not compared.** The
    column is dropped on the way down, so nothing survives to preserve; what is
    read afterwards is whatever the upgrade wrote.

    **The mutation it kills:** a backfill written as `WHERE position IN (1, 2, 3,
    4)`, which fills the shipped set and leaves every other question null — green
    against the seeded set one test up, and an upgrade that aborts against any
    database whose question set has ever changed.
    """
    config = alembic_config_pointed_at(empty_database)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    require_the_report_schema(empty_database)

    planted = {
        A_SIXTH_POSITION: (LIKERT_KIND, INSTRUCTOR_STREAM),
        A_SEVENTH_POSITION: (COMMENT_KIND, COURSE_STREAM),
        AN_EIGHTH_POSITION: (WORKLOAD_KIND, None),
    }
    with session_on(empty_database) as session:
        chain: dict[str, Any] = {}
        for position, (kind, stream) in planted.items():
            seed_row(
                session,
                metadata_tables,
                QUESTION,
                chain,
                **{POSITION_COLUMN: position, KIND_COLUMN: kind, STREAM_COLUMN: stream},
            )

    steps = walk_down_until_the_stream_column_is_gone(config, empty_database)

    below = {row[POSITION_COLUMN] for row in questions_below_the_revision(empty_database)}
    assert below == set(planted), (
        f"After walking {steps} revision(s) below head the question table holds ordinals "
        f"{sorted(below)}, and this test planted {sorted(planted)}. The rows are what the backfill "
        "has to reach, so if the walk took them with it there is nothing left for the upgrade to "
        "get wrong."
    )

    migrate(config, "upgrade", MODEL_SCHEMA, f"re-applying the {steps} revision(s) the walk undid")

    filled = {
        row[POSITION_COLUMN]: (row[KIND_COLUMN], row[STREAM_COLUMN])
        for row in questions_in(empty_database)
    }
    unplaced = sorted(
        position
        for position, (kind, stream) in filled.items()
        if kind != WORKLOAD_KIND and stream not in STREAMS
    )
    assert not unplaced, (
        f"After the re-upgrade, questions at ordinals {unplaced} carry no stream: {filled}. Every "
        "question that is not the workload one belongs to one of SPEC §5.1's two groups, and "
        "E4-02's first `CHECK` says so — so a row the backfill skipped is not merely unplaced, it "
        "is a row that constraint cannot be created over. Which stream a question outside §3.2's "
        "five gets is the migration's choice and this test does not make it; that every one of "
        "them gets one is the difference between an upgrade that completes and an upgrade that "
        "aborts."
    )
    assert filled[AN_EIGHTH_POSITION][1] is None, (
        f"The workload question at ordinal {AN_EIGHTH_POSITION} came back carrying "
        f"{filled[AN_EIGHTH_POSITION][1]!r}. §3.2's workload figure belongs to neither of §5.1's "
        "groups, and a backfill that hands every row a stream satisfies the assertion above and "
        "breaks the same rule from the other side."
    )
