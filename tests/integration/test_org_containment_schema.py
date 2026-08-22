"""Containment is enforced by Postgres, and course level is derived — ticket E0-05.

Acceptance criteria 1, 2, 3, 4, 5 and 6. The whole ticket is schema, so almost
all of it needs a real server: a constraint that lives in the application is
exactly what SPEC §8 and this ticket refuse, and the only way to tell the two
apart is to ask the database.

**What this module reads, and what it deliberately does not.** Every table here
is reflected out of the migrated database rather than imported from
`app.models.org`. Two reasons. The criteria are about what Postgres enforces,
and a reflected table is what Postgres holds; and the ticket names six *table*
names but no ORM class names, so importing would mean inventing them. Two unit
modules hold what belongs on the other side of that line:
`tests/unit/test_org_models_registered.py`, because a module nobody imported is
on no metadata and reflection cannot see the difference, and
`tests/unit/test_lms_owned_column_marker.py`, because the criterion about the
`lms_` marker says `Base.metadata` and means it — a marker the ORM does not carry
is not one the authz layer can read.

**Criterion 1's second half is not repeated here.** "`alembic check` is clean"
is already asserted by `tests/integration/test_alembic_baseline.py`, which runs
`command.check` against a freshly upgraded database; E0-05's migration lands in
that same chain, so that test starts covering it the moment this one does.
Duplicating it would give two failures for one defect.

**The two column names this file needs are both spelled by the ticket now**, and
each is a single named constant so a rename is a one-line change. `lms_number`
comes from the ticket's marker decision — the LMS-owned marker is an `lms_` name
prefix, and the course number is LMS-owned — and `level` from SPEC §8, which
writes it in backticks. An earlier draft of this file guessed at both, following
`tests/conftest.py`'s precedent of making such a choice once and marking it; that
guess was wrong about the number, which is why the constant survives even though
the guessing does not.

**Why there is a row-seeding helper rather than literal INSERTs.** A course sits
five levels down a containment chain, and none of the columns on the way are
named by the ticket. `seed_row` walks the reflected table, fills what the schema
requires, and follows foreign keys to build whatever ancestors are missing — so
these tests depend on the *shape* the ticket specifies and not on column names it
leaves open. A failure raised from inside that helper means the schema needs a
value it cannot invent, which is a broken test rather than a red one; its message
says so and names the column.
"""

import string
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import count
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Uuid,
    and_,
    delete,
    inspect,
    update,
)
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

# The six tables E0-05's scope names, in containment order (SPEC §2.1).
CONTAINMENT_TABLES = ("institution", "college", "department", "prefix", "course", "section")

# The ticket spells this one: the LMS-owned marker is an `lms_` name prefix, and
# it gives `lms_number` as the example. Left as a tuple because `require_column`
# takes candidates, and because one place to change a column name is worth
# keeping — an earlier draft of this file guessed `number` and was wrong.
# `tests/unit/test_lms_owned_column_marker.py` is where the prefix itself is
# asserted; here the name is just a name.
COURSE_NUMBER_COLUMNS = ("lms_number",)

# Not this suite's choice: SPEC §8 writes "Course `level`" in backticks, and the
# ticket repeats it.
COURSE_LEVEL_COLUMN = "level"

# SPEC §8's bands, both edges of every one of them plus one interior value each.
# `040` is there because it is the spec's own worked example of why the number is
# text: an integer cannot hold `MATH 040`'s leading zero.
LEVELS_BY_NUMBER = (
    ("000", "DEV"),
    ("040", "DEV"),
    ("099", "DEV"),
    ("100", "UG"),
    ("300", "UG"),
    ("499", "UG"),
    ("500", "UGGR"),
    ("550", "UGGR"),
    ("599", "UGGR"),
    ("600", "GR"),
    ("700", "GR"),
    ("799", "GR"),
    ("8000", "DR"),
    ("9000", "DR"),
    ("9999", "DR"),
)

# SPEC §8: "a three-digit number is valid only in `000`-`799`, and a four-digit
# number only in `8000`-`9999`." Everything else is refused at write time rather
# than stored with an absent or guessed level.
#
# Four of these seven catch the same defect from four directions, and it is the
# defect §8 spends a paragraph on: a derivation that casts the text to an integer
# and compares numerically, with no check on the width. Such an implementation
# accepts `40` (a good developmental number once the two digits become 40),
# `0099` (99, developmental — §8's own example of the two spellings that would
# become two rows for one course) and `0100` (100, undergraduate — the same trap
# in the band where nearly every real course lives). `10000` and `12A` are the
# criterion's "not three or four digits at all"; `800`, `999`, `1000` and `7999`
# are the four band edges the criterion names.
REJECTED_NUMBERS = ("800", "999", "1000", "7999", "0099", "0100", "40", "10000", "12A")

# A course number well inside a band, used as the control wherever a test needs
# to prove the insert path works before asserting that something is refused.
VALID_NUMBER = "150"
VALID_LEVEL = "UG"

# Values for a column whose name says what it holds. Guesses about *values*
# only — nothing here decides that a column exists or what it is called. Without
# them a check constraint on, say, a timezone column would reject the seeding
# helper's invented string, and the failure would read as a schema defect.
VALUE_HINTS = (
    ("timezone", "America/New_York"),
    ("email", "nobody@example.invalid"),
    ("url", "https://example.invalid"),
    ("uri", "https://example.invalid"),
)

_UNIQUE = count(1)


@pytest.fixture(scope="session")
def org_tables(migrated_engine: Any) -> dict[str, Table]:
    """Every table the migrated database holds, reflected once.

    Reflected rather than imported, and the whole schema rather than a named
    subset: `MetaData.reflect(only=[...])` raises when one of the names is
    absent, and a fixture error is not a failing test. A missing table is
    reported by `require_table` below, or by the existence test, in words.
    """
    metadata = MetaData()
    metadata.reflect(bind=migrated_engine)
    return dict(metadata.tables)


def require_table(tables: dict[str, Table], name: str) -> Table:
    """The reflected table called `name`, or a failure saying it is not there."""
    table = tables.get(name)
    if table is None:
        pytest.fail(
            f"The migrated database has no `{name}` table (it has {sorted(tables)}). E0-05 "
            f"creates {list(CONTAINMENT_TABLES)}; the existence test in this module is the "
            "assertion for that, and everything else here needs these tables to exist before "
            "it can mean anything."
        )
    return table


def require_column(table: Table, candidates: tuple[str, ...]) -> str:
    """The first of `candidates` that `table` has, or a failure listing both sides."""
    for candidate in candidates:
        if candidate in table.c:
            return candidate
    present = [column.name for column in table.columns]
    pytest.fail(
        f"`{table.name}` has none of the columns {list(candidates)} — it has {present}. Both "
        "names this file needs are spelled by the ticket or by SPEC §8, and both are module "
        "constants at the top of this file, so a deliberate rename is a one-line change here."
    )


def letters(limit: int | None) -> str:
    """A short, unique, upper-case string that fits a column of length `limit`.

    Upper-case letters and nothing else, because a code column plausibly carries
    a format check (`BIOL`, `MATH`) and a hex string would trip it — which would
    fail this suite inside its own seeding helper, for a reason that has nothing
    to do with what the test asserts.
    """
    width = max(min(6, limit or 6), 1)
    value = next(_UNIQUE)
    out = []
    for _ in range(width):
        value, remainder = divmod(value, 26)
        out.append(string.ascii_uppercase[remainder])
    return "".join(reversed(out))


def invented_value(table: Table, column: Any) -> Any:
    """Something a NOT NULL column of unknown purpose will accept.

    Deliberately dumb about meaning and careful about type. A column this cannot
    answer for stops the test with a message naming it, rather than inserting
    `None` and failing later somewhere that reads like a schema defect.
    """
    kind = column.type
    if isinstance(kind, Enum):
        values = list(getattr(kind, "enums", ()) or ())
        if values:
            return values[0]
    elif isinstance(kind, Uuid):
        return uuid4()
    elif isinstance(kind, Boolean):
        return False
    elif isinstance(kind, Integer):
        return next(_UNIQUE)
    elif isinstance(kind, Numeric):
        return Decimal("1")
    elif isinstance(kind, DateTime):
        return datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    elif isinstance(kind, Date):
        return date(2026, 8, 17)
    elif isinstance(kind, String):
        limit = getattr(kind, "length", None)
        for fragment, hint in VALUE_HINTS:
            if fragment in column.name.lower() and (limit is None or len(hint) <= limit):
                return hint
        return letters(limit)

    pytest.fail(
        f"The seeding helper in this module cannot invent a value for `{table.name}."
        f"{column.name}`, which is NOT NULL, has no default, and is of type {kind!r}. That is "
        "this test file needing a case added, not a defect in the schema — add the type to "
        "`invented_value`."
    )


def seed_row(
    session: Any,
    tables: dict[str, Table],
    name: str,
    chain: dict[str, Any] | None = None,
    **overrides: Any,
) -> Any:
    """Insert one row into `name`, building whatever ancestors it requires.

    `chain` is the containment chain built so far, keyed by table name. Passing
    one that already holds a `college` row puts the new department under that
    college, which is how the two chains in the contradiction test below come to
    share everything above the level the test is about.

    Columns are filled only where the schema requires it: anything generated,
    defaulted or nullable is left to the database. `level` on `course` is never
    filled unless a test asks for it explicitly, because whether it may be filled
    at all is criterion 5.
    """
    chain = {} if chain is None else chain
    table = require_table(tables, name)
    values: dict[str, Any] = dict(overrides)

    for column in table.columns:
        if column.name in values:
            continue
        if column.computed is not None:
            continue
        if name == "course" and column.name == COURSE_LEVEL_COLUMN:
            continue
        if column.identity is not None:
            continue
        if column.server_default is not None or column.default is not None:
            continue
        if column.foreign_keys and not column.nullable:
            ordered = sorted(column.foreign_keys, key=lambda fk: str(fk.target_fullname))
            target = ordered[0].column
            if target.table.name not in chain:
                # SPEC §8 permits exactly one `institution` row and E0-22's
                # `uq_institution_one_row` holds it, so an ancestor there is the row
                # that is already present rather than a new one. Everywhere else a
                # fresh chain means a fresh ancestor: two chains are two departments,
                # and quietly sharing one would make a test about two a test about one.
                existing = (
                    session.execute(target.table.select().limit(1)).mappings().one_or_none()
                    if target.table.name == "institution"
                    else None
                )
                chain[target.table.name] = (
                    existing
                    if existing is not None
                    else seed_row(session, tables, target.table.name, chain)
                )
            values[column.name] = chain[target.table.name][target.name]
            continue
        if column.nullable:
            continue
        values[column.name] = invented_value(table, column)

    statement = table.insert().values(**values).returning(*table.columns)
    inserted = session.execute(statement).mappings().one()
    chain.setdefault(name, inserted)
    return inserted


def stored_level(row: Any) -> Any:
    """The level as a comparable value, whatever the column's type turned out to be."""
    if COURSE_LEVEL_COLUMN not in row:
        pytest.fail(
            f"`course` has no `{COURSE_LEVEL_COLUMN}` column — the row that came back holds "
            f"{sorted(row)}. SPEC §8 names it, and §2.1 lists it among the derived facts every "
            "instructor and leadership surface reads."
        )
    value = row[COURSE_LEVEL_COLUMN]
    return getattr(value, "value", value)


def matching_primary_key(table: Table, row: Any) -> Any:
    """A WHERE clause selecting exactly `row`, however many columns its key has."""
    columns = list(table.primary_key.columns)
    if not columns:
        pytest.fail(
            f"`{table.name}` has no primary key, so a row cannot be addressed for update or "
            "delete. Every table in SPEC §8 is an entity with an identity."
        )
    return and_(*[column == row[column.name] for column in columns])


def department_identifying(prefix: Table, foreign_key: Any) -> bool:
    """Does this foreign key on `course` name a department independently of the prefix?

    Two shapes count, and they are the two ways a schema can let a course and its
    prefix disagree about which department they are in. A column referencing
    `department` directly is the obvious one. A column referencing the *prefix's
    own* department column — the composite-foreign-key shape, `course
    (department_id, prefix_id) → prefix (department_id, id)` — is the other, and
    it is invisible to a check that only looks at which table is referenced.
    """
    referenced = foreign_key.column
    if referenced.table.name == "department":
        return True
    if referenced.table.name != prefix.name:
        return False
    return any(key.column.table.name == "department" for key in referenced.foreign_keys)


def test_upgrade_head_creates_the_six_containment_tables(migrated_engine: Any) -> None:
    """Criterion 1, first half: `alembic upgrade head` creates all six tables.

    Asserted against the server rather than against `Base.metadata`, because a
    table that is on the metadata and in no migration exists nowhere a deployment
    can reach — the silent failure the epic README's first settled rule is about.
    """
    present = sorted(inspect(migrated_engine).get_table_names())

    missing = [name for name in CONTAINMENT_TABLES if name not in present]
    assert not missing, (
        f"`alembic upgrade head` left no {missing} table. The migrated database holds "
        f"{present}. E0-05 creates institution, college, department, prefix, course and "
        "section (SPEC §2.1 containment); a table spelled differently in the migration is the "
        "same defect as one that was never created, because §8 names these tables and every "
        "later schema ticket joins to them."
    )


def test_deleting_a_department_that_has_prefixes_is_refused(
    db_session: Any, org_tables: dict[str, Table]
) -> None:
    """Criterion 6: deleting a department with prefixes attached fails, not cascades.

    **The control deletes a childless department first, and it is not ceremony.**
    The assertion below is that a statement raises, and a statement raises for
    all sorts of reasons that have nothing to do with the constraint under
    test — `docs/MISTAKES.md` entry 3. Deleting a department that has nothing
    under it proves the delete path itself works, so the refusal that follows can
    only be about the prefix.

    What separates a cascade from a refusal is the `pytest.raises` — under
    `ON DELETE CASCADE` the delete succeeds and this test fails there, for not
    raising.

    An earlier version also queried the prefix afterwards and asserted it had
    survived. That assertion could not fail: the delete runs inside a
    `begin_nested()`, so by the time the query ran the savepoint had rolled back
    and the prefix was present whatever the foreign key did. It was removed
    rather than documented — `docs/MISTAKES.md` entry 3 is about assertions that
    cannot fail being read as though they could, and a never-failing assertion
    kept with a comment explaining that it never fails still teaches the pattern.
    """
    department = require_table(org_tables, "department")

    childless = seed_row(db_session, org_tables, "department")
    with db_session.begin_nested():
        removed = db_session.execute(
            delete(department).where(matching_primary_key(department, childless))
        )
    assert removed.rowcount == 1, (
        f"Deleting a department with nothing attached removed {removed.rowcount} rows rather "
        "than 1, so this test cannot tell the refusal below from a delete that never matched "
        "anything in the first place."
    )

    chain: dict[str, Any] = {}
    # The return value is unused; what matters is that the department now has a
    # prefix under it, which is what the delete below has to be refused for.
    seed_row(db_session, org_tables, "prefix", chain)
    parent = chain["department"]

    with pytest.raises(DatabaseError), db_session.begin_nested():
        db_session.execute(delete(department).where(matching_primary_key(department, parent)))


def test_a_prefix_cannot_sit_outside_a_department(org_tables: dict[str, Table]) -> None:
    """Criterion 6's other half: a department groups one or more prefixes, so a prefix has one.

    E0-05's scope says a department groups one or more prefixes and asks for it as
    a database constraint. The column is non-nullable and does enforce it — and
    until E0-37 item 3 nothing asserted so, which left only the course-to-prefix
    half of that sentence tested.

    **`ON DELETE RESTRICT` does not cover this**, and that is the whole reason
    this test is worth its lines.
    `test_deleting_a_department_that_has_prefixes_is_refused` passes whether or
    not the column is nullable: a nullable foreign key still refuses the delete of
    a department that a prefix points at. So a later change making the column
    nullable turns nothing red, and a prefix belonging to no department becomes
    writable — a subtree with no parent, in the hierarchy every purview
    computation in SPEC §2.1 walks.

    Read out of the catalog rather than probed with an insert. Both would work;
    the catalog is what says the rule *exists*, and `docs/MISTAKES.md` entry 3's
    closing note is that where two rules could refuse the same row, the catalog
    test and the behavioural test see different things and are worth having as
    different tests. Reflection is the catalog: SQLAlchemy reads `attnotnull` for
    it, so what is asserted is what Postgres holds rather than what
    `app/models/org.py` declares.

    **The mutation this test exists for:** `ALTER TABLE prefix ALTER COLUMN
    department_id DROP NOT NULL`, which turns exactly this red and leaves the
    delete-restrict test above green. **The near miss that must stay green:**
    renaming the column, or reaching the department through a composite key,
    since the columns are found by following the foreign key rather than by name.
    """
    prefix = require_table(org_tables, "prefix")
    department = require_table(org_tables, "department")

    to_department = [key for key in prefix.foreign_keys if key.column.table.name == department.name]
    assert to_department, (
        f"`prefix` has no foreign key into `department` — it references "
        f"{sorted({key.column.table.name for key in prefix.foreign_keys})}. SPEC §2.1's "
        "containment order puts a prefix under a department, and the assertion below is about "
        "columns this found: with none, it would report a schema with no containment at all as "
        "correctly constrained."
    )

    nullable = sorted({key.parent.name for key in to_department if key.parent.nullable})
    assert not nullable, (
        f"The prefix columns {nullable} reference `department` and are nullable, so a prefix can "
        "sit under no department at all.\n"
        "\n"
        "E0-05: 'a department groups one or more prefixes', enforced as a database constraint. "
        "The foreign key gives the 'one department' half; this is the half it does not give, and "
        "`ON DELETE RESTRICT` does not give it either — that rule refuses the delete of a "
        "department a prefix points at, and says nothing about a prefix that points at none.\n"
        "\n"
        "An orphaned prefix is a subtree with no parent in the hierarchy §2.1 walks to compute "
        "purview, so nobody's scope reaches it and its courses answer to no chair."
    )


def test_the_containment_foreign_keys_walked_by_parent_are_indexed(
    migrated_engine: Any, org_tables: dict[str, Table]
) -> None:
    """`prefix.department_id` and `section.course_id` carry an index.

    Both were unindexed when E0-05 was first reviewed, and nothing failed: a
    missing index costs a sequential scan, which is invisible on the handful of
    rows a test seeds and grows with every term. That is `docs/MISTAKES.md`
    entry 2 in its performance form — behaviour shipped with nothing asserting
    it — so the fix gets a regression test rather than only a migration.

    **Leading position, not membership.** The column has to be first in some
    index, and an earlier version of this test only checked that it appeared
    somewhere in one. Those differ: a B-tree over `(term_id, course_id)` contains
    `course_id`, and Postgres 17 has no skip scan, so it does not serve an
    equality lookup on `course_id` alone. A future "let us not have two indexes
    on section" cleanup could fold this index into a composite ordered the other
    way, restore the exact defect, and leave the suite green — which is the
    leftmost-prefix rule that also decides whether the other three foreign keys
    need an index of their own.

    Those three are deliberately *not* asserted here, and deliberately have no
    index: `college.institution_id`, `department.college_id` and
    `course.prefix_id` each lead a composite unique constraint, which already
    serves a lookup by parent. Measured, not assumed. Asserting they have *no*
    index would be asserting an absence, which is entry 3's shape, and would go
    red for the right change.
    """
    expected = {("prefix", "department_id"), ("section", "course_id")}

    with migrated_engine.connect() as connection:
        leading = {
            (table_name, index["column_names"][0])
            for table_name, _ in expected
            for index in inspect(connection).get_indexes(table_name)
            if index["column_names"] and index["column_names"][0] is not None
        }

    missing = expected - leading
    assert not missing, (
        f"{sorted(missing)} are foreign keys that no index leads with. A lookup by parent then "
        "reads the whole table, which passes on seed data and degrades every term as sections "
        "accumulate. Note that an index merely *containing* the column is not enough — Postgres "
        "does not skip-scan, so only a leading column serves an equality lookup on its own. See "
        "the comments in `app/models/org.py` for why the other three containment foreign keys "
        "correctly have no index."
    )


def test_a_course_reaches_a_department_only_through_its_prefix(
    db_session: Any, org_tables: dict[str, Table]
) -> None:
    """Criterion 2: a course reaches a department by exactly one path, through its prefix.

    The criterion's own reading is that in a strict tree the violation *cannot be
    expressed* — no row says a course is in a department its prefix is not in —
    and that this is the stronger outcome, not a gap. So the assertion that runs
    every time is the tree itself: one foreign key into `prefix`, not nullable,
    and no second one. The ticket is explicit that a second ancestor reference
    should not be added in order to have something to constrain.

    The second branch is kept for the case where such a reference exists anyway,
    for some reason of its own — a `department_id` on `course`, or the composite
    key `course (department_id, prefix_id) → prefix (department_id, id)`. Then the
    contradiction is a row that can be written down, and the database has to
    refuse it. That branch's control insert is the same guard as everywhere else
    in this file: an insert that raises proves nothing unless the consistent
    version of the same insert succeeds.
    """
    course = require_table(org_tables, "course")
    prefix = require_table(org_tables, "prefix")

    referenced_tables = sorted({key.column.table.name for key in course.foreign_keys})
    to_prefix = [key for key in course.foreign_keys if key.column.table.name == prefix.name]
    assert to_prefix, (
        "`course` has no foreign key to `prefix`, though it references "
        f"{referenced_tables}. SPEC §8: courses belong to exactly one prefix, and E0-05 wants "
        "that as a database constraint rather than an application convention."
    )
    nullable = sorted({key.parent.name for key in to_prefix if key.parent.nullable})
    assert not nullable, (
        f"The course columns {nullable} reference `prefix` but are nullable, so a course can "
        "sit under no prefix at all. 'Exactly one prefix' is two constraints, and this is the "
        "half a foreign key does not give you."
    )
    paths = {key.constraint for key in to_prefix}
    assert len(paths) == 1, (
        f"`course` has {len(paths)} separate foreign keys into `prefix`, so it reaches a "
        "department by more than one path and the two can disagree. Constraints are counted "
        "rather than columns, because a composite key spanning two columns is still one path. "
        "The criterion asks for exactly one."
    )

    contradictory = [key for key in course.foreign_keys if department_identifying(prefix, key)]
    if not contradictory:
        # Nothing on `course` names a department except by way of its prefix, so
        # the contradictory row cannot be written down at all. That is the strict
        # tree the criterion asks for, and the three assertions above are the
        # whole of it: one path, not nullable, not duplicated.
        return

    number_column = require_column(course, COURSE_NUMBER_COLUMNS)
    chain_a: dict[str, Any] = {}
    seed_row(db_session, org_tables, "prefix", chain_a)
    # A second department under the *same* college, so the only thing the two
    # chains disagree about is the department — the axis the criterion names.
    shared = {name: row for name, row in chain_a.items() if name in ("institution", "college")}
    chain_b: dict[str, Any] = dict(shared)
    seed_row(db_session, org_tables, "prefix", chain_b)
    assert chain_b["department"] != chain_a["department"], (
        "Seeding a second prefix reused the first prefix's department, so there is no second "
        "subtree to place a course in and the assertion below would be about nothing."
    )

    consistent = {
        key.parent.name: chain_a[key.column.table.name][key.column.name]
        for key in course.foreign_keys
        if key.column.table.name in chain_a
    }
    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                org_tables,
                "course",
                dict(chain_a),
                **consistent,
                **{number_column: VALID_NUMBER},
            )
    except DatabaseError as refused:
        pytest.fail(
            "A course placed consistently — its prefix and every ancestor it names taken from "
            f"one subtree — was refused: {refused}. The assertion below cannot mean anything "
            "until an ordinary course inserts."
        )

    contradiction = dict(consistent)
    for key in contradictory:
        contradiction[key.parent.name] = chain_b[key.column.table.name][key.column.name]

    with pytest.raises(DatabaseError), db_session.begin_nested():
        seed_row(
            db_session,
            org_tables,
            "course",
            dict(chain_a),
            **contradiction,
            **{number_column: "151"},
        )


@pytest.mark.parametrize(("number", "level"), LEVELS_BY_NUMBER)
def test_course_level_derives_from_the_course_number(
    db_session: Any, org_tables: dict[str, Table], number: str, level: str
) -> None:
    """Criterion 3: level derives correctly, at both edges of every band in SPEC §8.

    The level is read back off the row the insert returned rather than computed
    anywhere in this file, so what is asserted is what the database stored. The
    number is passed as text and the expected level comes from §8's table; `040`
    is in the set because a derivation that stores the number as an integer loses
    the leading zero and cannot answer for the developmental band at all.
    """
    course = require_table(org_tables, "course")
    number_column = require_column(course, COURSE_NUMBER_COLUMNS)

    row = seed_row(db_session, org_tables, "course", None, **{number_column: number})

    assert stored_level(row) == level, (
        f"Course number {number!r} stored level {stored_level(row)!r}; SPEC §8's bands put it "
        f"in {level!r}. The bands are 000-099 DEV, 100-499 UG, 500-599 UGGR, 600-799 GR and "
        "8000-9999 DR — and they mix widths, so three digits and four digits are not the same "
        "range read twice."
    )


@pytest.mark.parametrize("number", REJECTED_NUMBERS)
def test_a_course_number_in_no_band_is_refused(
    db_session: Any, org_tables: dict[str, Table], number: str
) -> None:
    """Criterion 4: a number in no band fails to insert.

    SPEC §8: "A roster sync carrying an unexpected number is a defect to see, not
    a row to accept." So the assertion is that the write is refused, not that the
    level comes out empty.

    The control insert runs first. Any of these statements could raise for a
    reason that has nothing to do with the number — a column this file's seeding
    helper filled badly, a constraint from a later ticket — and `pytest.raises`
    cannot tell those apart from the rejection under test. A course that inserts
    at number 150 immediately before, through the same helper and into the same
    prefix, can.
    """
    course = require_table(org_tables, "course")
    number_column = require_column(course, COURSE_NUMBER_COLUMNS)
    chain: dict[str, Any] = {}

    try:
        seed_row(db_session, org_tables, "course", chain, **{number_column: VALID_NUMBER})
    except DatabaseError as refused:
        pytest.fail(
            f"The control course at number {VALID_NUMBER!r} was refused: {refused}. Until an "
            "in-band course inserts, a refusal below says nothing about the number."
        )

    with pytest.raises(DatabaseError), db_session.begin_nested():
        seed_row(db_session, org_tables, "course", chain, **{number_column: number})


def test_course_level_cannot_be_supplied_at_insert(
    db_session: Any, org_tables: dict[str, Table]
) -> None:
    """Criterion 5, insert form: level cannot be set independently of the number.

    The criterion allows either outcome — the write fails, or the supplied value
    is ignored in favour of the derived one — because a generated column refuses
    and a trigger overwrites, and E0-05 leaves that choice open. So both are
    accepted here, and what is refused is the third outcome: a stored level that
    came from the caller.

    The control is the same insert without the level, so a refusal below is known
    to be about the level column rather than about anything else in the row.
    """
    course = require_table(org_tables, "course")
    number_column = require_column(course, COURSE_NUMBER_COLUMNS)
    chain: dict[str, Any] = {}

    control = seed_row(db_session, org_tables, "course", chain, **{number_column: VALID_NUMBER})
    assert stored_level(control) == VALID_LEVEL, (
        f"The control course at number {VALID_NUMBER!r} stored level "
        f"{stored_level(control)!r} rather than {VALID_LEVEL!r}, so this test cannot tell a "
        "level that was ignored from a level that was never derived. "
        "test_course_level_derives_from_the_course_number is where that is asserted."
    )

    refused = False
    supplied: Any = None
    try:
        with db_session.begin_nested():
            row = seed_row(
                db_session,
                org_tables,
                "course",
                chain,
                **{number_column: "151", COURSE_LEVEL_COLUMN: "DR"},
            )
            supplied = stored_level(row)
    except DatabaseError:
        refused = True

    assert refused or supplied == VALID_LEVEL, (
        f"A course inserted with number 151 and level 'DR' stored level {supplied!r}. SPEC §8: "
        'level "derives from the course number and is never set independently of it". Either '
        "the insert has to fail, as a generated column makes it, or the derived value "
        f"({VALID_LEVEL!r}) has to win."
    )


def test_course_level_cannot_be_updated_on_its_own(
    db_session: Any, org_tables: dict[str, Table]
) -> None:
    """Criterion 5, update form: the same rule once the row exists.

    Worth its own test rather than folding into the insert case. A trigger
    written `BEFORE INSERT` and not `BEFORE UPDATE` passes the insert form and
    fails here, and that is the version of this defect that ships: the level is
    right on arrival and drifts later, which is exactly what "stored as a
    generated or trigger-maintained column so it cannot drift from the number"
    is there to stop.
    """
    course = require_table(org_tables, "course")
    number_column = require_column(course, COURSE_NUMBER_COLUMNS)
    row = seed_row(db_session, org_tables, "course", None, **{number_column: VALID_NUMBER})

    refused = False
    stored: Any = None
    try:
        with db_session.begin_nested():
            statement = (
                update(course)
                .where(matching_primary_key(course, row))
                .values(**{COURSE_LEVEL_COLUMN: "DR"})
                .returning(*course.columns)
            )
            stored = stored_level(db_session.execute(statement).mappings().one())
    except DatabaseError:
        refused = True

    assert refused or stored == VALID_LEVEL, (
        f"Updating level to 'DR' on a course numbered {VALID_NUMBER!r} left it {stored!r}. The "
        "number did not change, so the level may not either: the update has to be refused, or "
        f"the derived {VALID_LEVEL!r} has to survive it."
    )


def test_course_level_follows_the_course_number_when_the_number_changes(
    db_session: Any, org_tables: dict[str, Table]
) -> None:
    """Criterion 5's other direction: the level tracks the number it derives from.

    A level that is written once and never recomputed satisfies both tests above —
    it refuses nothing and it ignores nothing, because nothing ever writes to it
    again. This is the assertion that fails in that case, and it is the ticket's
    own words: "so it cannot drift from the number".
    """
    course = require_table(org_tables, "course")
    number_column = require_column(course, COURSE_NUMBER_COLUMNS)
    row = seed_row(db_session, org_tables, "course", None, **{number_column: VALID_NUMBER})
    assert stored_level(row) == VALID_LEVEL, (
        f"The course seeded at number {VALID_NUMBER!r} stored level {stored_level(row)!r} "
        f"rather than {VALID_LEVEL!r}, so the update below would be measuring drift from a "
        "starting point that was already wrong."
    )

    statement = (
        update(course)
        .where(matching_primary_key(course, row))
        .values(**{number_column: "8500"})
        .returning(*course.columns)
    )
    updated = db_session.execute(statement).mappings().one()

    assert stored_level(updated) == "DR", (
        f"After the course number changed from {VALID_NUMBER!r} to '8500' the level is "
        f"{stored_level(updated)!r}, and SPEC §8 puts four-digit 8000-9999 in 'DR'. A level "
        "that keeps its old value is the drift a generated or trigger-maintained column exists "
        "to make impossible."
    )
