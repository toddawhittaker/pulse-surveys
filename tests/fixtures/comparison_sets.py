"""E5-01 — reaching the comparison-set tables without deciding how they are built.

Four modules ask questions about the same two tables — the declared length and
level, the membership rule, the deletion rules, and what the application
connection may do with either — so the names, the vocabularies and the two
seeding helpers live here rather than in four copies (`docs/MISTAKES.md`
entry 13).

**Nothing here asserts anything.** Every function either answers a reading or
stops with `pytest.fail` naming what it could not find, so a broken helper and a
failed criterion are never reported as the same thing. The guards are plain
functions on purpose and every caller calls them as the **first statement of a
test body**, never from a fixture: while E5-01 is unbuilt each module's red has
to be a FAILED naming the missing table, not an ERROR in setup
(`docs/MISTAKES.md` entry 44).

**Two names are spelled here and the rest are discovered.** The ticket spells the
set's own columns — "name, declared length, declared level, creator, timestamps"
— and the breakdown's decision 3 spells the shape, so `comparison_set`,
`length_weeks` and `level` are constants below and a deliberate rename is a
one-line change. The **membership** table is found rather than named: the ticket
says only "its membership relation to courses", so this file looks for the table
that references both `comparison_set` and `course` and reports
`comparison_set_member` as the expected default when there is none. A test that
named it would decide it.

**How the level agreement is written is likewise not decided here.**
`member_of` below passes the set row and the course row as the seeding walker's
*chain*, so whatever columns the membership row carries to hold the agreement —
a denormalized pair under a composite foreign key, or nothing at all beside a
trigger — are filled from those two rows rather than from a column name this
file knows. That keeps the cross-level tests a statement about the criterion
rather than about the mechanism the migration chose.
"""

from typing import Any

import pytest
from sqlalchemy.exc import DatabaseError

from fixtures.supervision import single_primary_key, sqlstate_of

# SPEC §8's table list spells this one, so it is not this file's choice.
COMPARISON_SET_TABLE = "comparison_set"

# What the membership table is expected to be called when there is none to find.
# Reported in a failure message and never used to look one up — the lookup is
# `membership_table` below, which follows the foreign keys.
EXPECTED_MEMBERSHIP_TABLE = "comparison_set_member"

# The table a member names, and the table SPEC §8 derives a level on.
COURSE_TABLE = "course"

# The set's own two declared columns. The ticket names both in prose ("declared
# length, declared level") and the breakdown's decision 3 fixes the pair; the
# spellings are this file's one place to hold them.
LENGTH_COLUMN = "length_weeks"
LEVEL_COLUMN = "level"
NAME_COLUMN = "name"

# The course columns this file writes and reads. `lms_number` is E0-05's and
# `level` is the stored generated column ADR 0015 derives from it — read, never
# re-derived here, which is the ticket's second known trap.
COURSE_NUMBER_COLUMN = "lms_number"
COURSE_LEVEL_COLUMN = "level"

# SPEC §2.2's length set: "Course lengths in weeks: 3, 6, 8, 10, 12, 15, 16 (plus
# an 18-week dissertation length)." Eight values, and the parenthesis is part of
# the sentence rather than an aside — an 18-week section exists.
SPEC_LENGTHS = (3, 6, 8, 10, 12, 15, 16, 18)

# Each length outside that set, paired with the accepted length nearest it. The
# pairing is what makes each refusal a boundary rather than an anecdote: the test
# writes the accepted neighbour first and requires it to be stored, so a schema
# that refused everything cannot pass by refusing this one too.
#
# Every entry is a near miss on purpose. `17` sits between 16 and 18 and is the
# one a range check written as `3 <= n <= 18` accepts; `4`, `5`, `7`, `9`, `11`,
# `13` and `14` are the interior gaps the same range check accepts; `0` and `-1`
# are the two below every band, and a column typed `integer` accepts both.
LENGTHS_OUTSIDE_THE_SET = (
    (-1, 3),
    (0, 3),
    (2, 3),
    (4, 3),
    (5, 6),
    (7, 6),
    (9, 8),
    (11, 10),
    (13, 12),
    (14, 15),
    (17, 16),
    (19, 18),
)

# SPEC §5.1 names the five and §8 bands them: "`DEV`, `UG`, `UGGR`, `GR`, `DR`".
SPEC_LEVELS = ("DEV", "UG", "UGGR", "GR", "DR")

# A course number inside each band, from SPEC §8's table. `040` is the spec's own
# worked example of why a number is text rather than an integer, and `9000` is
# four digits because a three-digit number is valid only in `000`-`799`.
NUMBER_BY_LEVEL = {"DEV": "040", "UG": "300", "UGGR": "550", "GR": "700", "DR": "9000"}

# Tokens that are not one of the five, each paired with the accepted level its
# test writes as a control. Chosen to be near misses rather than nonsense: `ug`
# is the right token in the wrong case, which a `CHECK` written with `lower()`
# accepts; `GRAD` and `PROFESSIONAL` read like levels a later institution might
# ask for; and `''` is what a check phrased as "not empty" is the only guard
# against.
LEVELS_OUTSIDE_THE_FIVE = (
    ("ug", "UG"),
    ("GRAD", "GR"),
    ("PROFESSIONAL", "DR"),
    ("", "DEV"),
)

# The SQLSTATE class Postgres answers an integrity violation with — foreign key,
# not null, unique, check. Asserted as the class rather than as `23514`, because
# which rule refuses a row is the schema's business.
INTEGRITY_VIOLATION = "23"

# The class Postgres answers a value it cannot even convert with — `22P02`,
# invalid text representation, which is what an enumerated type says about a
# label it does not have. Accepted beside the class above wherever the criterion
# is "the database refuses it" and the schema is free to hold the rule as an enum
# **or** as a check: the two refuse at different moments and both are refusals
# about the data. `42703` (undefined column) and `42601` (syntax) are in neither
# class, which is what keeps a broken statement in one of these modules from
# reading as a schema rule.
INVALID_VALUE = "22"
REFUSED_A_VALUE = (INTEGRITY_VIOLATION, INVALID_VALUE)


def require_table(tables: dict[str, Any], name: str, why: str) -> Any:
    """The declared table called `name`, or a failure saying it is not there."""
    table = tables.get(name)
    if table is None:
        pytest.fail(f"There is no `{name}` table (what is there: {sorted(tables)}). {why}")
    return table


def comparison_set_table(tables: dict[str, Any]) -> Any:
    """The declared `comparison_set` table, or the red that says E5-01 is unbuilt."""
    return require_table(
        tables,
        COMPARISON_SET_TABLE,
        "SPEC §8 lists `comparison_set` in its table inventory and E5-01 is the ticket that "
        "builds it, in `backend/app/models/benchmark.py` (SPEC §13) with a migration off head "
        "`e5a2b81c47d3`.",
    )


def membership_table(tables: dict[str, Any]) -> Any:
    """The declared table that names a `comparison_set` and a `course`, found by its keys.

    Found rather than named, because the ticket says only that the model carries
    "its membership relation to courses" — the table's name is the
    implementer's. Exactly one table is expected to reference both; two would
    mean this helper cannot say which one membership lives in, and that is a
    failure rather than a guess.
    """
    found = [
        table
        for name, table in tables.items()
        if name != COMPARISON_SET_TABLE
        and {key.column.table.name for key in table.foreign_keys}
        >= {COMPARISON_SET_TABLE, COURSE_TABLE}
    ]
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        pytest.fail(
            f"{sorted(table.name for table in found)} all reference both `{COMPARISON_SET_TABLE}` "
            f"and `{COURSE_TABLE}`, so this helper cannot say which one holds membership. E5-01 "
            "builds one membership relation; a second table with the same two keys is a design "
            "this file cannot read."
        )
    pytest.fail(
        f"No declared table references both `{COMPARISON_SET_TABLE}` and `{COURSE_TABLE}` (what is "
        f"there: {sorted(tables)}). E5-01's breakdown decision 3 makes a named set "
        "'a stored list of member courses plus one declared length+level pair', so membership is "
        f"a table of its own — `{EXPECTED_MEMBERSHIP_TABLE}` is the expected name and this helper "
        "follows the keys rather than the name, so a different spelling is fine and an absent "
        "table is this red."
    )


def require_columns(table: Any, names: tuple[str, ...], why: str) -> None:
    """Stop unless `table` has every one of `names`, listing what it does have."""
    absent = [name for name in names if name not in table.c]
    if absent:
        pytest.fail(
            f"`{table.name}` has none of {absent} — it has "
            f"{[column.name for column in table.columns]}. {why} Each name is a constant in "
            "tests/fixtures/comparison_sets.py, so a deliberate rename is a one-line change there."
        )


def key_columns_to(table: Any, target_table: str, target_column: str) -> list[str]:
    """Every column on `table` whose foreign key points at one named column of `target_table`.

    Narrower than `fixtures.supervision.foreign_key_columns`, and the narrowing
    is the point: under the composite-key shape this ticket's breakdown settles,
    a membership row references `comparison_set` from **two** columns — its id
    and its level — so a helper that asked only for the target *table* would
    answer with both and a caller wanting the key would get whichever sorted
    first.
    """
    return sorted(
        {
            key.parent.name
            for key in table.foreign_keys
            if key.column.table.name == target_table and key.column.name == target_column
        }
    )


def one_key_column_to(table: Any, target_table: str, target_column: str) -> str:
    """The single column of `table` keyed to `target_table (target_column)`."""
    found = key_columns_to(table, target_table, target_column)
    if len(found) != 1:
        pytest.fail(
            f"`{table.name}` has {len(found)} foreign keys to `{target_table} ({target_column})` "
            f"({found}); it references "
            f"{sorted({key.column.table.name for key in table.foreign_keys})}. A membership row "
            "names exactly one set and exactly one course."
        )
    return found[0]


def refusal_of(session: Any, write: Any) -> DatabaseError | None:
    """Run `write` inside a savepoint; answer the database error it provoked, or `None`.

    A savepoint rather than the surrounding transaction, so a refused write
    leaves the session usable for the next assertion, and `SET CONSTRAINTS ALL
    IMMEDIATE` because a rule written as a deferrable constraint does not fire
    until commit and nothing in this suite commits. Copied in behaviour from
    `SupervisionGraph.refusal`, which every schema module in this suite already
    goes through.
    """
    from sqlalchemy import text

    savepoint = session.begin_nested()
    try:
        write()
        session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    except DatabaseError as refused:
        savepoint.rollback()
        return refused
    savepoint.commit()
    return None


def assert_refused_for_the_data(
    refused: DatabaseError | None,
    what: str,
    why: str,
    classes: tuple[str, ...] = (INTEGRITY_VIOLATION,),
) -> None:
    """The write was refused, and refused by a rule about the row rather than about the SQL."""
    assert refused is not None, f"{what} was accepted by the database. {why}"
    state = sqlstate_of(refused)
    assert state is not None and state.startswith(classes), (
        f"{what} was refused with SQLSTATE {state!r}: {refused}. This module expects a refusal in "
        f"class {list(classes)}; anything else — `42703` undefined column, `42601` syntax — means "
        "the statement could not run, so the refusal says nothing about the rule under test."
    )


def write_set(seed: Any, *, length: Any, level: Any, name: Any = None) -> Any:
    """Insert one `comparison_set` declaring this length and this level.

    The creator, the timestamps and anything else the table requires are left to
    the seeding walker: none of them is what these modules are about, and a value
    chosen here would be a second thing a red could be about. `name` is left out
    unless a caller passes one, so the walker's unique value is what two sets
    written by one test carry — the only test that needs two sets to agree on a
    name says so.
    """
    values: dict[str, Any] = {LENGTH_COLUMN: length, LEVEL_COLUMN: level}
    if name is not None:
        values[NAME_COLUMN] = name
    return seed(COMPARISON_SET_TABLE, {}, **values)


def course_at(seed: Any, level: str) -> Any:
    """One `course` whose stored level is `level`, by giving it a number in that band.

    The number is what is chosen and the level is what is read back: SPEC §8
    derives `level` from the course number and ADR 0015 makes it a stored
    generated column, so writing the level directly is neither possible nor the
    thing to do (the ticket's second known trap — one source, read the stored
    column).

    Each course is seeded through a **fresh chain**, so two courses in one test
    sit under two prefixes and a repeated number cannot collide with E0-05's
    `uq_course_prefix_id_lms_number`.
    """
    return seed(COURSE_TABLE, {}, **{COURSE_NUMBER_COLUMN: NUMBER_BY_LEVEL[level]})


def member_of(seed: Any, membership: Any, comparison_set: Any, course: Any) -> Any:
    """Insert one membership row naming this set and this course.

    **Both rows are passed as the walker's chain rather than as column values**,
    and that is what keeps these tests silent about the mechanism. The walker
    fills every non-nullable foreign key from the chain by following the key, so
    a membership row carrying the ticket's plain pair is filled from two columns
    and one carrying the breakdown's denormalized level pair is filled from four
    — from the same two rows either way, with no column name written here. A
    schema that holds the agreement in a trigger instead is filled correctly too.
    """
    return seed(membership.name, {COMPARISON_SET_TABLE: comparison_set, COURSE_TABLE: course})


def members_of(session: Any, membership: Any, comparison_set: Any) -> list[Any]:
    """Every membership row naming this set, read back out of the database."""
    from sqlalchemy import select

    set_key = single_primary_key(comparison_set_table_of(membership))
    column = one_key_column_to(membership, COMPARISON_SET_TABLE, set_key)
    return list(
        session.execute(select(membership).where(membership.c[column] == comparison_set[set_key]))
        .mappings()
        .all()
    )


def comparison_set_table_of(membership: Any) -> Any:
    """The `comparison_set` table, reached from the membership table's own key.

    Reached through the key rather than through the metadata dictionary so that
    `members_of` needs one argument fewer, and so that the table it reads the
    primary key of is provably the one membership references.
    """
    for key in membership.foreign_keys:
        if key.column.table.name == COMPARISON_SET_TABLE:
            return key.column.table
    pytest.fail(
        f"`{membership.name}` references no `{COMPARISON_SET_TABLE}`, so it is not the membership "
        "table `membership_table` claimed to have found. That is a defect in this file rather "
        "than in the schema."
    )
