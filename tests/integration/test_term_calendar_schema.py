"""The academic calendar is enforced by Postgres — ticket E0-06.

All six acceptance criteria. Almost all of it needs a real server, for the reason
E0-05 gives: a constraint that lives in the application is exactly what SPEC §8
and this ticket refuse, and the only way to tell the two apart is to ask the
database.

Criteria 3 and 5 both compare a row against its term's length, and both were
unwritable until the ticket said where that length comes from — `term` stores it
rather than deriving it from the two dates. Criterion 3 splits across the line
the ticket draws: the database owns uniqueness over `(term_id, number)` and the
range, and the no-gaps half is a property over the producer function this ticket
ships, because contiguity is not expressible as a row-level constraint in
Postgres. **The producer is the one identifier in this file that no ticket
spells, and it is found rather than named** — see `week_producer` below.

**No test here names a constraint.** When the criteria were written the ticket
left the cross-table mechanism open between a trigger, a composite foreign key
carrying the term's length, and something else, so nothing asserted about it
could be more than "the database refused the row". [ADR
0018](../../docs/adr/0018-cross-table-length-rules-are-enforced-by-a-composite-foreign-key.md)
has since settled it, and the tests below do hold that mechanism — the copy of
its term's length that a `week` row carries, that a row may not supply it freely,
and what happens to it when the term is edited. They still name no constraint: a
name here is produced by `Base.metadata`'s convention rather than chosen, so
holding one would report a rename as a regression. Criterion 5's own tests are
untouched by the ADR and still do nothing but write a row and see whether the
database keeps it.

**What this module reads, and what it deliberately does not.** Two views of the
same schema, used for different questions, and the split is not the one E0-05
made:

  - **Reflected** — what Postgres holds. Used for the existence criterion, for
    finding which columns are timestamps, and for counting indexes.
  - **Declared** — `Base.metadata`, reached through `app.models`. Used for every
    write. E0-05 inserted through reflected tables, and could: none of its
    criteria were about client-side behaviour. Criterion 4 here is. Postgres
    *accepts* a naive datetime into a `timestamptz` column — it casts it using
    the session `TimeZone` — so "a naive datetime cannot be written to any
    timestamp column" cannot be a database constraint, and the guard has to sit
    on the column type where every writer meets it. Inserting through the
    declared table is what puts the guard in the path. It also means the ORM's
    own idea of the schema is what gets exercised, which is the side a later
    service will write through.

Both views name the same tables, so nothing here needs an ORM class name — the
ticket names four tables and no classes.

**Both views also agree about what a column's type is**, and they have to. Every
question this module asks of a type goes through `stored_type`, which resolves a
declared `TypeDecorator` through to the type it decorates. Reflection never sees
a decorator and so was always right by accident; the seeding helper read the
declared class and was not, which stopped both criterion-4 tests inside their own
fixture against the very implementation the criterion forces
([E0-06-01](../../docs/disputes/E0-06-01.md)). One helper now answers for both,
so the next edit cannot re-split them.

**Two column names in this file are guesses and are marked as ones.** The ticket
gives both `term` and `start_letter_map` a "length in weeks" without spelling
either column, so each is a named constant with a candidate list, following the
precedent the shared seeding helper sets and the correction E0-05 went through:
`tests/fixtures/supervision.py` guessed `number`, the ticket then spelled
`lms_number`, and the constant is
what made the fix a one-line change. Everything else this file needs is spelled
by a ticket — `letter`, `number`, `lms_section_code`, `term_id`, `course_id` —
or reached without a name at all: ancestors are found by following foreign keys,
and timestamps by their type.

**Why there is a row-seeding helper rather than literal INSERTs.** A survey
window sits at the bottom of two chains — a section under a course under a
prefix, and a week under a term — and almost none of the columns on the way are
named by the ticket. `seed_row` walks the table, fills what the schema requires,
and follows foreign keys to build whatever ancestors are missing, sharing one
`chain` so a section and a week seeded for the same window land in the same term.
A failure raised from inside it means the schema needs a value it cannot invent:
that is a broken test rather than a red one, and its message says so and names
the column.
"""

import string
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from inspect import isfunction
from itertools import count
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
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
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.exc import DatabaseError, StatementError
from sqlalchemy.types import TypeDecorator

pytestmark = pytest.mark.integration

# The four tables E0-06's scope names.
CALENDAR_TABLES = ("term", "week", "survey_window", "start_letter_map")

# Spelled by the ticket: "**The letter column is named `letter`.** It takes no
# `lms_` prefix". An earlier draft of this file carried two candidate spellings
# because the ticket named none.
START_LETTER_COLUMN = "letter"

# The week ordinal, spelled by criterion 3: "the database enforces uniqueness
# over `(term_id, number)`".
WEEK_NUMBER_COLUMN = "number"

# **This file's choice**, both of them. The ticket gives `term` a "length in
# weeks" and `start_letter_map` a "length in weeks" without spelling either
# column; SPEC §8 writes the analogous section column `length_weeks`. Candidates
# so a rename is a one-line change, and `require_column` prints both sides when
# neither is there.
TERM_LENGTH_COLUMNS = ("length_weeks", "length")
LETTER_LENGTH_COLUMNS = ("length_weeks", "length")

# Not this file's choice. E0-05 created `section.lms_section_code`, and E0-06's
# scope writes `section.term_id` out in full.
SECTION_CODE_COLUMN = "lms_section_code"
SECTION_TERM_COLUMN = "term_id"
SECTION_COURSE_COLUMN = "course_id"
COURSE_NUMBER_COLUMN = "lms_number"

# Two well-formed section codes per SPEC §2.2's `{startLetter}{ordinal}{modality}`
# — the spec's own examples. Used where a test needs two codes that differ.
SECTION_CODE = "R3WW"
OTHER_SECTION_CODE = "Q2FF"

# Two start letters from the Fall 2026 seed map in SPEC §2.2 (12-week U/R/Q).
# Fixture data, not rows any migration inserts.
START_LETTER = "Q"
OTHER_START_LETTER = "R"

# Criterion 5's isolating case, taken from the criterion itself: "a 15-week
# letter in a 12-week summer term". Every number here is a length SPEC §2.2
# allows — summer terms are 12 weeks, and 15 is a course length with its own
# letters (15-week V/D) — so a plain range check over §2.2's lengths accepts the
# refused row and the test still fails. That is the whole point of choosing 15
# over 500.
SUMMER_TERM_WEEKS = 12
LETTER_FITTING_THE_TERM = 12
LETTER_LONGER_THAN_THE_TERM = 15
FITTING_LETTER = "Q"
OVERLONG_LETTER = "V"

# SPEC §2.2's other reference length: fall and spring run 18 weeks. Used where a
# test needs a term in which a row that is wrong for a summer term would be
# perfectly ordinary.
FALL_TERM_WEEKS = 18

# The institution timezone SPEC §3.1 defaults to. Used to prove an aware value
# keeps its instant across a write when the offset is not zero.
INSTITUTION_TIMEZONE = ZoneInfo("America/New_York")

# ---------------------------------------------------------------------------
# Values the seeding helper invents. Guesses about *values* only — nothing here
# decides that a column exists or what it is called, and nothing here is read by
# an assertion. They are chosen to be mutually consistent so that a cross-column
# check constraint cannot reject the helper's own rows and leave a test failing
# inside its fixture: an 18-week fall term (SPEC §2.2) running 8/17 to 12/20,
# start letters 18 weeks or shorter, week numbers inside 1..18, and a window that
# opens Friday 18:00 and closes Sunday 23:59:59 in the institution timezone
# (SPEC §3.1), expressed here in UTC.
# ---------------------------------------------------------------------------

TERM_START = date(2026, 8, 17)
TERM_END = date(2026, 12, 20)
DEFAULT_LENGTH_WEEKS = 18
WEEK_NUMBER_CEILING = 18

WINDOW_OPENS_AT = datetime(2026, 8, 21, 22, 0, tzinfo=UTC)
WINDOW_CLOSES_AT = datetime(2026, 8, 24, 3, 59, 59, tzinfo=UTC)

DATE_HINTS = (("start", TERM_START), ("begin", TERM_START), ("end", TERM_END))
DATETIME_HINTS = (
    ("open", WINDOW_OPENS_AT),
    ("close", WINDOW_CLOSES_AT),
    ("end", WINDOW_CLOSES_AT),
)
STRING_HINTS = (
    ("timezone", "America/New_York"),
    ("email", "nobody@example.invalid"),
    ("url", "https://example.invalid"),
    ("uri", "https://example.invalid"),
)
LENGTH_FRAGMENTS = ("length", "weeks", "duration")

_UNIQUE = count(1)
_INTEGER_COUNTERS: dict[tuple[str, str], Any] = {}


@pytest.fixture(autouse=True)
def _restart_the_integer_counters() -> None:
    """Give each test its own small integers, so week 1 is week 1 every time.

    The counters below hand out 1, 2, 3… per column so that a `week.number` the
    helper invents lands inside a term rather than at 47. They are module-level,
    so without this they would keep climbing across the module and eventually
    walk out of an 18-week term — failing a later test inside its own seeding
    for a reason the test is not about.
    """
    _INTEGER_COUNTERS.clear()


# ---------------------------------------------------------------------------
# Reaching the schema.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def reflected_tables(migrated_engine: Any) -> dict[str, Table]:
    """Every table the migrated database holds, reflected once.

    Reflected rather than imported, and the whole schema rather than a named
    subset: `MetaData.reflect(only=[...])` raises when one of the names is
    absent, and a fixture error is not a failing test. A missing table is
    reported by `require_table` below, or by the existence test, in words.
    """
    metadata = MetaData()
    metadata.reflect(bind=migrated_engine)
    return dict(metadata.tables)


@pytest.fixture(scope="session")
def declared_tables(migrated_database: Any) -> dict[str, Table]:
    """`Base.metadata`, with every model module registered on it.

    Reached through `app.models` and not through `app.models.term`, for the
    reason `tests/unit/test_term_models_registered.py` gives at length:
    `migrations/env.py` imports the package, and a module nobody imported is on
    no metadata. That module is where a missing registration is diagnosed; this
    one only needs something to insert through.

    `Base` comes from `app.models.base` rather than from `app.db`, which builds
    an engine out of `Settings()` at import and would need five variables that
    have nothing to do with a schema.

    `migrated_database` is depended on and not used: it is what guarantees the
    migration has run before anything inserts through these tables. Removing the
    parameter would leave the first test to insert against an unmigrated database
    and fail with a message about a missing relation.
    """
    try:
        import_module("app.models")
        base_module = import_module("app.models.base")
    except ImportError as failure:
        pytest.fail(
            f"Importing the model package raised {failure!r}. E0-04 ships `app/models/base.py` "
            "with the declarative base, and every model module imports `Base` from it."
        )
    metadata = getattr(getattr(base_module, "Base", None), "metadata", None)
    if metadata is None:
        pytest.fail(
            "`app.models.base` exposes no `Base` with `metadata`, so there is nothing to insert "
            "through — and nothing for `migrations/env.py` to autogenerate against either."
        )
    return dict(metadata.tables)


def require_table(tables: dict[str, Table], name: str) -> Table:
    """The table called `name`, or a failure saying it is not there."""
    table = tables.get(name)
    if table is None:
        pytest.fail(
            f"There is no `{name}` table (what is there: {sorted(tables)}). E0-06 creates "
            f"{list(CALENDAR_TABLES)}; the existence test in this module is the assertion for "
            "that, and everything else here needs these tables before it can mean anything."
        )
    return table


def require_column(table: Table, candidates: tuple[str, ...]) -> str:
    """The first of `candidates` that `table` has, or a failure listing both sides."""
    for candidate in candidates:
        if candidate in table.c:
            return candidate
    present = [column.name for column in table.columns]
    pytest.fail(
        f"`{table.name}` has none of the columns {list(candidates)} — it has {present}. E0-06 "
        f"gives `{table.name}` a length in weeks without spelling the column, so the candidates "
        "are a constant at the top of this file and a deliberate rename is a one-line change "
        "here."
    )


def single_primary_key(table: Table) -> str:
    """The name of `table`'s one primary key column.

    One, because [ADR 0016](../../docs/adr/0016-primary-keys-are-database-generated-uuids.md)
    makes every primary key in this schema a single server-generated uuid. A
    composite key would mean that decision had changed, which is worth a failure
    rather than a silent first-column-wins.
    """
    columns = list(table.primary_key.columns)
    if len(columns) != 1:
        pytest.fail(
            f"`{table.name}` has {len(columns)} primary key columns "
            f"({[column.name for column in columns]}). ADR 0016 makes every primary key one uuid "
            "with a server default, and this module addresses rows by it."
        )
    return columns[0].name


def foreign_key_column(table: Table, target: str, target_column: str) -> str:
    """The one column on `table` whose foreign key points at `target.target_column`.

    Found by following the key rather than by guessing a name, so a reference
    spelled any way at all is picked up.

    **The referenced column is part of the question, not decoration.** An earlier
    version of this helper asked only which *table* was referenced, and that
    became wrong the moment [ADR
    0018](../../docs/adr/0018-cross-table-length-rules-are-enforced-by-a-composite-foreign-key.md)
    landed: `week` now references `term` from two columns — the term's key and a
    carried copy of its length — so "the column that points at `term`" has two
    answers and this helper failed on every call. Asking for the referenced
    column distinguishes them, and is how the tests below reach each one without
    naming either.
    """
    matches = sorted(
        {
            key.parent.name
            for key in table.foreign_keys
            if key.column.table.name == target and key.column.name == target_column
        }
    )
    if not matches:
        referenced = sorted(
            f"{key.column.table.name}.{key.column.name}" for key in table.foreign_keys
        )
        pytest.fail(
            f"No column on `{table.name}` references `{target}.{target_column}` — the table "
            f"references {referenced}."
        )
    if len(matches) > 1:
        pytest.fail(
            f"`{table.name}` references `{target}.{target_column}` from more than one column "
            f"({matches}), so there is no single answer to which of them carries it."
        )
    return matches[0]


def matching_primary_key(table: Table, row: Any) -> Any:
    """A WHERE clause selecting exactly `row`."""
    key = single_primary_key(table)
    return table.c[key] == row[key]


# ---------------------------------------------------------------------------
# Seeding.
# ---------------------------------------------------------------------------


def letters(limit: int | None) -> str:
    """A short, unique, upper-case string that fits a column of length `limit`.

    Upper-case letters and nothing else, because a code column plausibly carries
    a format check and a hex string would trip it — which would fail this suite
    inside its own seeding helper, for a reason that has nothing to do with what
    the test asserts.
    """
    width = max(min(6, limit or 6), 1)
    value = next(_UNIQUE)
    out = []
    for _ in range(width):
        value, remainder = divmod(value, 26)
        out.append(string.ascii_uppercase[remainder])
    return "".join(reversed(out))


def section_code() -> str:
    """A well-formed section code per SPEC §2.2, unique within this session."""
    return f"{letters(1)}3WW"


# The band a generated course number is drawn from: three digits, `100`-`799`,
# which SPEC §8 splits into UG, UGGR and GR. Staying inside a band matters more
# than which band, because the bands are not enforced by a `CHECK`: `course.level`
# is a stored generated column (ADR 0015) and an out-of-band number derives
# `NULL::course_level`, so the row is refused by that column's `NOT NULL` and the
# error names the level rather than the number. `000`-`099` is left out only
# because it needs zero padding to stay three digits, which is a case E0-05's own
# tests own rather than this helper's.
COURSE_NUMBER_FIRST = 100
COURSE_NUMBER_LAST = 799

# Cleared before every test, so the numbers only have to be distinct within one:
# `db_session` rolls every write back at the end of a test, so no course this
# module seeds outlives the test that asked for it. The same mechanism and the
# same reasoning as `_GRAPH_INTEGER_COUNTERS` in `tests/fixtures/supervision.py`.
_COURSE_NUMBERS: dict[str, Any] = {}


@pytest.fixture(autouse=True)
def _course_numbers_start_again_for_each_test() -> None:
    """Hand the first number in the band to every test, rather than the whole session one each.

    Without it the generator is a session-wide supply of 700 numbers, and a
    module that seeds enough courses runs out — failing loudly, but inside its own
    seeding and for a reason that has nothing to do with what it asserts, which is
    the shape this generator replaced.
    """
    _COURSE_NUMBERS.clear()


def course_number() -> str:
    """A course number no other course in this test carries, inside SPEC §8's bands.

    **Distinct per call, and that is E0-09's repair arriving here.** This entry
    was the constant `"150"` — well inside a band, and a unique violation the
    moment one test seeds a second course under the same prefix, because E0-05's
    `uq_course_prefix_id_lms_number` is per prefix. No test in this module builds
    two courses today, so the trap was set and not sprung; E0-09 sprang the
    identical one, blocked three tests before any assertion ran, and took a
    dispute to settle (`docs/disputes/E0-09-01.md`).

    **Counting up rather than wrapping** is the whole of it. A generator that
    wrapped would hand out a duplicate once a test asked for enough courses, and
    the failure would look exactly like the one this replaces — a unique violation
    raised inside a fixture, from a statement naming no column this ticket owns.

    **Not `letters()`, which is what the section code beside it uses.** That draws
    one letter from a session-wide counter, so it repeats every 26 calls; a course
    number built the same way would reintroduce a rarer and order-dependent
    version of the same defect, and rarer is worse — it would surface as a flake
    in somebody else's ticket.

    A fourth copy of one generator, and deliberately so: this module carries its
    own copy of the whole seeding walker for the reason its docstring gives, and
    importing `tests/fixtures/supervision.py`, which holds the shared one, would
    couple this module to where pytest happens to put `tests/` on `sys.path`.
    """
    counter = _COURSE_NUMBERS.setdefault(COURSE_NUMBER_COLUMN, count(COURSE_NUMBER_FIRST))
    number = next(counter)
    if number > COURSE_NUMBER_LAST:
        available = COURSE_NUMBER_LAST - COURSE_NUMBER_FIRST + 1
        pytest.fail(
            f"This test asked for more than {available} courses, so the seeding helper has run "
            "out of three-digit numbers inside SPEC §8's bands. It stops here rather than "
            f"starting again at {COURSE_NUMBER_FIRST}: reusing a number would write a second "
            "course with the same number under the same prefix, which E0-05's "
            "`uq_course_prefix_id_lms_number` refuses — and that failure would be a unique "
            "violation raised inside a fixture rather than a message naming its cause, which is "
            "the shape this generator exists to leave behind. If a test genuinely needs this "
            "many courses, widen the band above: `000`-`099` is available with zero padding."
        )
    return str(number)


# Values keyed to a column that a type alone cannot answer for. Both are
# schema rules E0-05 already enforces, so a value the helper invented freely
# would be rejected by a constraint that has nothing to do with E0-06: SPEC §8's
# course-number bands, and SPEC §2.2's section-code shape. Both are drawn fresh
# per call, because both rules have a uniqueness half as well as a shape half.
COLUMN_VALUES: dict[tuple[str, str], Callable[[], Any]] = {
    ("course", COURSE_NUMBER_COLUMN): course_number,
    ("section", SECTION_CODE_COLUMN): section_code,
}


def date_hint(column_name: str) -> date:
    lowered = column_name.lower()
    for fragment, value in DATE_HINTS:
        if fragment in lowered:
            return value
    return TERM_START


def datetime_hint(column_name: str) -> datetime:
    lowered = column_name.lower()
    for fragment, value in DATETIME_HINTS:
        if fragment in lowered:
            return value
    return WINDOW_OPENS_AT


def integer_hint(table_name: str, column_name: str) -> int:
    """A small integer: a plausible length in weeks, or a low ordinal.

    Small on purpose. A column called `number` on `week` is an ordinal inside a
    term, and a term is 12 or 18 weeks long (SPEC §2.2), so a counter that ran
    freely would seed week 40 and be refused by a range check the test is not
    about.
    """
    lowered = column_name.lower()
    if any(fragment in lowered for fragment in LENGTH_FRAGMENTS):
        return DEFAULT_LENGTH_WEEKS
    counter = _INTEGER_COUNTERS.setdefault((table_name, column_name), count(1))
    return 1 + (next(counter) - 1) % WEEK_NUMBER_CEILING


def stored_type(column: Any) -> Any:
    """The type a column actually stores, with any `TypeDecorator` resolved away.

    **The one place this module decides what a column holds**, used by both the
    seeding helper and the timestamp discovery below, so the two cannot answer
    the question differently. They once did, and it cost a dispute
    ([E0-06-01](../../docs/disputes/E0-06-01.md)): discovery reflected from
    Postgres and so was immune, while seeding read the declared type and
    dispatched `isinstance` against it. A `TypeDecorator` is not an instance of
    the type it decorates, so `survey_window.closes_at` — declared as the guard
    criterion 4 forces — matched nothing and stopped both timestamp tests inside
    their own fixture, before either reached an assertion.

    Unwrapping is done in a loop because one decorator can wrap another. It names
    nothing from `app.models` and pins no interface, which is the point: the
    guard's class is the implementer's to choose, and a helper that recognised it
    by name would be this file deciding it.
    """
    kind = column.type
    while isinstance(kind, TypeDecorator):
        kind = kind.impl_instance
    return kind


def invented_value(table: Table, column: Any) -> Any:
    """Something a NOT NULL column of unknown purpose will accept.

    Deliberately dumb about meaning and careful about type. A column this cannot
    answer for stops the test with a message naming it, rather than inserting
    `None` and failing later somewhere that reads like a schema defect.

    Dispatch is on what the column *stores*, not on the class the model declares
    — see `stored_type` above.
    """
    maker = COLUMN_VALUES.get((table.name, column.name))
    if maker is not None:
        return maker()

    kind = stored_type(column)
    if isinstance(kind, Enum):
        values = list(getattr(kind, "enums", ()) or ())
        if values:
            return values[0]
    elif isinstance(kind, Uuid):
        return uuid4()
    elif isinstance(kind, Boolean):
        return False
    elif isinstance(kind, DateTime):
        return datetime_hint(column.name)
    elif isinstance(kind, Date):
        return date_hint(column.name)
    elif isinstance(kind, Integer):
        return integer_hint(table.name, column.name)
    elif isinstance(kind, Numeric):
        return Decimal("1")
    elif isinstance(kind, String):
        limit = getattr(kind, "length", None)
        for fragment, hint in STRING_HINTS:
            if fragment in column.name.lower() and (limit is None or len(hint) <= limit):
                return hint
        return letters(limit)

    # `column.type` and not the unwrapped `kind`: the declared type is what a
    # reader will find in the model, and it is the string that diagnosed
    # E0-06-01. The wording is unchanged from the version that did so.
    pytest.fail(
        f"The seeding helper in this module cannot invent a value for `{table.name}."
        f"{column.name}`, which is NOT NULL, has no default, and is of type {column.type!r}. "
        "That is this test file needing a case added, not a defect in the schema — add the type "
        "to `invented_value`."
    )


def seed_row(
    session: Any,
    tables: dict[str, Table],
    name: str,
    chain: dict[str, Any] | None = None,
    **overrides: Any,
) -> Any:
    """Insert one row into `name`, building whatever ancestors it requires.

    `chain` is the set of ancestor rows built so far, keyed by table name.
    Passing one that already holds a `term` row puts the new row in that term,
    which is how a survey window's section and its week come to sit in the same
    term rather than in two unrelated ones.

    Columns are filled only where the schema requires it: anything generated,
    defaulted or nullable is left to the database — which matters here, since
    every primary key is a server-defaulted `gen_random_uuid()`
    ([ADR 0016](../../docs/adr/0016-primary-keys-are-database-generated-uuids.md))
    and has to be read back with RETURNING rather than predicted.

    An override is honoured even when it is `None`, so a test can insert a null
    into a column and let the database refuse it.
    """
    chain = {} if chain is None else chain
    table = require_table(tables, name)
    values: dict[str, Any] = dict(overrides)

    for column in table.columns:
        if column.name in values:
            continue
        if column.computed is not None:
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


def branch_from(chain: dict[str, Any], *keep: str) -> dict[str, Any]:
    """A fresh chain sharing only the named ancestors with `chain`.

    Used to build a second term under the same institution, or a second course
    under the same prefix, so that the one thing two rows disagree about is the
    axis the test is about.
    """
    return {name: row for name, row in chain.items() if name in keep}


def seed_term(session: Any, tables: dict[str, Table], chain: dict[str, Any], weeks: int) -> Any:
    """A term of exactly `weeks` weeks, with dates that say the same thing.

    Every test below that is about a term's length has to set that length, and
    `seed_row` on its own would invent one. The dates are set alongside it — any
    column on `term` whose name says start or end — so the two never contradict
    each other. The ticket allows a check constraint holding the length and the
    dates consistent and does not require one; a helper that set only the length
    would fail inside its own fixture against an implementation that took the
    option, and the failure would read as a defect in the schema.

    The end date is inclusive of the last day: `start + weeks * 7 - 1`. That is
    this file's reading, and it is confined to seeded values — nothing here
    asserts anything about it, because the ticket is explicit that the spec does
    not say whether `end_date` is inclusive, which is the reason the length is
    stored rather than derived.
    """
    term = require_table(tables, "term")
    length_column = require_column(term, TERM_LENGTH_COLUMNS)
    values: dict[str, Any] = {length_column: weeks}

    for column in term.columns:
        if not isinstance(column.type, Date):
            continue
        lowered = column.name.lower()
        if "start" in lowered or "begin" in lowered:
            values[column.name] = TERM_START
        elif "end" in lowered:
            values[column.name] = TERM_START + timedelta(days=weeks * 7 - 1)

    return seed_row(session, tables, "term", chain, **values)


def seed_weeks(session: Any, tables: dict[str, Table], chain: dict[str, Any], through: int) -> None:
    """Weeks 1 to `through` for the term already in `chain`.

    Each row's copy of the term's length is filled by `seed_row` following the
    composite foreign key, not by this helper — which is the same route any other
    writer takes and the reason the copy is right without anyone maintaining it
    ([ADR 0018](../../docs/adr/0018-cross-table-length-rules-are-enforced-by-a-composite-foreign-key.md)).
    """
    for number in range(1, through + 1):
        seed_row(session, tables, "week", chain, **{WEEK_NUMBER_COLUMN: number})


def carried_length_column(tables: dict[str, Table]) -> str:
    """The `week` column carrying a copy of its term's length.

    Reached by following the composite foreign key to the `term` column it
    references, so nothing here spells `term_length_weeks`.
    [ADR 0018](../../docs/adr/0018-cross-table-length-rules-are-enforced-by-a-composite-foreign-key.md)
    names it; this module's rule is to find what it can find, so that a rename is
    a schema change rather than a test failure.
    """
    week = require_table(tables, "week")
    term = require_table(tables, "term")
    return foreign_key_column(week, "term", require_column(term, TERM_LENGTH_COLUMNS))


def carried_term_lengths(session: Any, tables: dict[str, Table], term_row: Any) -> list[int]:
    """What every `week` row of one term currently says its term's length is.

    The term row is matched on the primary key alone and deliberately not on the
    length: the caller reads this before and after changing that length, and a
    filter that included the old value would match nothing afterwards and return
    an empty list, which is the shape `docs/MISTAKES.md` entry 3 records.
    """
    week = require_table(tables, "week")
    term = require_table(tables, "term")
    key = single_primary_key(term)
    term_column = foreign_key_column(week, "term", key)
    carried = carried_length_column(tables)
    rows = session.execute(select(week.c[carried]).where(week.c[term_column] == term_row[key]))
    return sorted(rows.scalars())


def week_producer() -> Any:
    """The function E0-06 ships to produce a term's week rows.

    **Found, not named.** No ticket spells this function, and picking a name here
    would make the implementer build to this file rather than to the ticket. So
    the module is scanned for a function it defines itself whose name mentions a
    week, and the answer has to be unambiguous: none, or more than one, is a
    failure that says what was found. A declarative class is not a function, so
    a `Week` model does not compete with it.
    """
    try:
        module = import_module("app.models.term")
    except ModuleNotFoundError:
        pytest.fail(
            "There is no `app.models.term` module. E0-06 puts term, week, survey_window and "
            "start_letter_map there, and ships the function that produces a term's week rows."
        )

    defined: dict[str, Any] = {}
    for name, value in vars(module).items():
        if name.startswith("_") or not isfunction(value):
            continue
        if getattr(value, "__module__", None) != "app.models.term":
            continue
        defined[name] = value

    candidates = {name: value for name, value in defined.items() if "week" in name.lower()}

    if not candidates:
        pytest.fail(
            "`app.models.term` defines no function whose name mentions a week — it defines "
            f"{sorted(defined)}. E0-06's scope: 'This ticket ships the function that produces "
            "those rows for a term', and criterion 3 makes the no-gaps half a tested invariant "
            "over it. This test looks for the function by name rather than importing an agreed "
            "one, because no ticket spells it; if it is there under a name with no 'week' in it, "
            "that is a defect in this test and `week_producer` is the one place to change."
        )
    if len(candidates) > 1:
        pytest.fail(
            f"`app.models.term` defines more than one week-ish function ({sorted(candidates)}), "
            "so this test cannot tell which one produces a term's week rows. Naming one of them "
            "here would pin an interface the ticket leaves open — say in the pull request which "
            "is the producer and narrow `week_producer`."
        )
    return next(iter(candidates.values()))


def week_numbers_produced(
    session: Any, tables: dict[str, Table], term: Any, produced: Any
) -> list[int]:
    """The week numbers a producer call yielded, sorted, whatever shape it came in.

    Deliberately incurious about the return type. The ticket says the function
    produces a term's week rows and says nothing about whether it hands them back
    or writes them, so `None` is read as "it wrote them" and the `week` table is
    read instead. Beyond that, a row is asked for its `number` — the one part of
    the shape criterion 3 does spell.
    """
    week = require_table(tables, "week")
    if WEEK_NUMBER_COLUMN not in week.c:
        pytest.fail(
            f"`week` has no `{WEEK_NUMBER_COLUMN}` column — it has "
            f"{[column.name for column in week.columns]}. Criterion 3 spells it: the database "
            f"enforces uniqueness over `(term_id, {WEEK_NUMBER_COLUMN})`."
        )

    if produced is None:
        key = single_primary_key(require_table(tables, "term"))
        term_column = foreign_key_column(week, "term", key)
        rows = session.execute(
            select(week.c[WEEK_NUMBER_COLUMN]).where(week.c[term_column] == term[key])
        )
        return sorted(rows.scalars())

    numbers: list[int] = []
    for item in produced:
        if isinstance(item, int):
            numbers.append(item)
        elif hasattr(item, "keys") and WEEK_NUMBER_COLUMN in item:
            numbers.append(item[WEEK_NUMBER_COLUMN])
        elif hasattr(item, WEEK_NUMBER_COLUMN):
            numbers.append(getattr(item, WEEK_NUMBER_COLUMN))
        else:
            pytest.fail(
                f"The week producer returned {item!r}, which this test cannot read a "
                f"`{WEEK_NUMBER_COLUMN}` off. It handles an integer, a mapping and an object "
                "with the attribute; add the shape here rather than changing the producer to "
                "suit the test."
            )
    return sorted(numbers)


def timestamp_columns(reflected: dict[str, Table]) -> list[tuple[str, str]]:
    """Every timestamp column on the four calendar tables, as `(table, column)`.

    Discovered from the reflected schema because what Postgres calls a timestamp
    is unambiguous, and because these two tests are about columns rather than
    about what the ORM says of them.

    An earlier version of this docstring gave a second reason — that a declared
    `TypeDecorator` "is not an instance of `DateTime` and would be missed" — and
    that is no longer true of this module: the check goes through `stored_type`,
    which resolves a decorator away, so reflected and declared now answer alike.
    Keeping the two in step is the point. When they disagreed, this side was
    immune and the seeding side was not, which is exactly the failure
    [E0-06-01](../../docs/disputes/E0-06-01.md) records.
    """
    found: list[tuple[str, str]] = []
    for name in CALENDAR_TABLES:
        table = reflected.get(name)
        if table is None:
            continue
        found.extend(
            (name, column.name)
            for column in table.columns
            if isinstance(stored_type(column), DateTime)
        )
    return found


# ---------------------------------------------------------------------------
# Criterion 1 — the tables exist.
# ---------------------------------------------------------------------------


def test_upgrade_head_creates_the_four_calendar_tables(migrated_engine: Any) -> None:
    """Criterion 1, first half: `alembic upgrade head` creates all four tables.

    Asserted against the server rather than against `Base.metadata`, because a
    table that is on the metadata and in no migration exists nowhere a deployment
    can reach — the silent failure the epic README's first settled rule is about.
    `tests/unit/test_term_models_registered.py` asserts the other side of that
    pair.

    **Criterion 1's second half is not repeated here.** "`alembic check` is
    clean" is already asserted by `tests/integration/test_alembic_baseline.py`,
    which runs `command.check` against a freshly upgraded database; E0-06's
    migration lands in that same chain, so that test starts covering it the
    moment this one does. Duplicating it would give two failures for one defect.
    """
    present = sorted(inspect(migrated_engine).get_table_names())

    missing = [name for name in CALENDAR_TABLES if name not in present]
    assert not missing, (
        f"`alembic upgrade head` left no {missing} table. The migrated database holds {present}. "
        "E0-06 creates term, week, survey_window and start_letter_map (SPEC §2.2, §8); a table "
        "spelled differently in the migration is the same defect as one that was never created, "
        "because §8 names these tables and E0-07 and E2 both join to them."
    )


# ---------------------------------------------------------------------------
# Criterion 2 — a start letter is unique within a term, and only within one.
# ---------------------------------------------------------------------------


def test_a_duplicate_start_letter_within_one_term_is_refused(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 2, first half: the same letter twice in one term is rejected.

    **Two rows go in before the one that must not.** The first establishes the
    term and proves the insert path works at all; the second proves the
    constraint is not simply "one row per term", which would satisfy a
    `pytest.raises` for a reason that has nothing to do with the letter
    (`docs/MISTAKES.md` entry 3). Only then does the duplicate mean something.

    What this does not distinguish is a unique constraint over `(term, letter)`
    from one over `(term, start date)`, since both rows carry the same invented
    start date. Distinguishing them would need the start-date column name, which
    the ticket still does not spell, and it is not what criterion 2 asks: the
    criterion as written is "a duplicate start letter within one term is
    rejected", and that is what is asserted.
    """
    letter = START_LETTER_COLUMN

    chain: dict[str, Any] = {}
    seed_row(db_session, declared_tables, "term", chain)
    seed_row(db_session, declared_tables, "start_letter_map", chain, **{letter: START_LETTER})

    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "start_letter_map",
                chain,
                **{letter: OTHER_START_LETTER},
            )
    except DatabaseError as refused:
        pytest.fail(
            f"A second start letter ({OTHER_START_LETTER!r}) in the same term was refused: "
            f"{refused}. A term maps many letters (SPEC §2.2's Fall 2026 seed map has at least "
            "thirteen), and until a second letter inserts, the refusal below says nothing about "
            "duplication."
        )

    refused_duplicate = False
    try:
        with db_session.begin_nested():
            seed_row(
                db_session, declared_tables, "start_letter_map", chain, **{letter: START_LETTER}
            )
    except DatabaseError:
        refused_duplicate = True

    assert refused_duplicate, (
        f"The start letter {START_LETTER!r} was written twice into one term. E0-06: 'A letter is "
        "unique within a term.' Without the constraint, two rows claim different lengths and "
        "start dates for the same letter, and E0-07's derivation of a section's dates from its "
        "code has two answers and no way to choose."
    )


def test_the_same_start_letter_in_two_terms_is_accepted(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 2, second half: the letter is unique *within* a term, not globally.

    This is the half that fails when the constraint is written over the letter
    alone, which is the natural mistake and the one that would be invisible until
    Spring 2027 reuses `Q`. The two terms share their institution, so the only
    thing they disagree about is the term.
    """
    letter = START_LETTER_COLUMN

    first: dict[str, Any] = {}
    seed_row(db_session, declared_tables, "term", first)
    second = branch_from(first, "institution")
    seed_row(db_session, declared_tables, "term", second)
    assert second["term"] != first["term"], (
        "Seeding a second term reused the first one, so there is no second term to place the "
        "letter in and the assertion below would be about nothing."
    )

    seed_row(db_session, declared_tables, "start_letter_map", first, **{letter: START_LETTER})

    try:
        with db_session.begin_nested():
            seed_row(
                db_session, declared_tables, "start_letter_map", second, **{letter: START_LETTER}
            )
    except DatabaseError as refused:
        pytest.fail(
            f"The start letter {START_LETTER!r} was accepted in one term and refused in another: "
            f"{refused}. The map is per-term (SPEC §2.2, E0-06 scope) — Fall 2026's `Q` and the "
            "next fall's `Q` are different lengths and different dates, and a uniqueness rule "
            "that spans terms makes the second one unwritable."
        )


# ---------------------------------------------------------------------------
# Criterion 3 — week rows run 1 to the term length with no gaps. The database
# owns uniqueness and the range; the producer owns contiguity.
# ---------------------------------------------------------------------------


def test_two_week_rows_with_the_same_number_in_one_term_are_refused(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 3, the uniqueness half: `(term_id, number)` is unique.

    Week 2 goes in between the two week 1s, so the refusal is known to be about
    the repeated number and not about a term being allowed one week row
    (`docs/MISTAKES.md` entry 3). Without this, a term can hold two week 3s and
    the term axis SPEC §2.2 plots has two points at the same x.
    """
    chain: dict[str, Any] = {}
    seed_term(db_session, declared_tables, chain, SUMMER_TERM_WEEKS)
    seed_row(db_session, declared_tables, "week", chain, **{WEEK_NUMBER_COLUMN: 1})

    try:
        with db_session.begin_nested():
            seed_row(db_session, declared_tables, "week", chain, **{WEEK_NUMBER_COLUMN: 2})
    except DatabaseError as refused:
        pytest.fail(
            f"A second week in the same term was refused: {refused}. A term has 12 or 18 of "
            "them (SPEC §2.2), so until a second week inserts the refusal below proves nothing."
        )

    refused_duplicate = False
    try:
        with db_session.begin_nested():
            seed_row(db_session, declared_tables, "week", chain, **{WEEK_NUMBER_COLUMN: 1})
    except DatabaseError:
        refused_duplicate = True

    assert refused_duplicate, (
        "Week 1 was written twice into one term. Criterion 3: 'the database enforces uniqueness "
        f"over `(term_id, {WEEK_NUMBER_COLUMN})`'. Two rows for one week give every join through "
        "the week axis a duplicate, which doubles a count long before anyone notices a second "
        "row exists."
    )


def test_the_same_week_number_in_two_terms_is_accepted(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 3: the uniqueness is *within* a term, not across the deployment.

    The half that fails when the constraint is written over `number` alone, or
    when `number` is made a primary key on its own. Every term has a week 1.
    """
    first: dict[str, Any] = {}
    seed_term(db_session, declared_tables, first, SUMMER_TERM_WEEKS)
    seed_row(db_session, declared_tables, "week", first, **{WEEK_NUMBER_COLUMN: 1})

    second = branch_from(first, "institution")
    seed_term(db_session, declared_tables, second, SUMMER_TERM_WEEKS)
    assert second["term"] != first["term"], (
        "Seeding a second term reused the first one, so there is no second term to put week 1 "
        "in and the assertion below would be about nothing."
    )

    try:
        with db_session.begin_nested():
            seed_row(db_session, declared_tables, "week", second, **{WEEK_NUMBER_COLUMN: 1})
    except DatabaseError as refused:
        pytest.fail(
            f"Week 1 was accepted in one term and refused in another: {refused}. Criterion 3 "
            f"scopes the uniqueness to `(term_id, {WEEK_NUMBER_COLUMN})` — every term has a week "
            "1, and a rule that spans terms makes the second term unwritable."
        )


def test_a_week_number_beyond_the_term_length_is_refused(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 3, the range half: the range is *this* term's, not a fixed 18.

    The term is 12 weeks, so week 12 is its last and week 13 is outside it. Both
    numbers are legal in an 18-week fall term, which is what makes this the case
    worth writing: a check constraint hardcoding `number BETWEEN 1 AND 18`
    accepts the control *and* accepts week 13, and fails here rather than
    passing. Week rows enumerate a term's weeks, so a week the term does not
    have is a row nothing can mean.
    """
    chain: dict[str, Any] = {}
    seed_term(db_session, declared_tables, chain, SUMMER_TERM_WEEKS)

    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "week",
                chain,
                **{WEEK_NUMBER_COLUMN: SUMMER_TERM_WEEKS},
            )
    except DatabaseError as refused:
        pytest.fail(
            f"Week {SUMMER_TERM_WEEKS} of a {SUMMER_TERM_WEEKS}-week term was refused: "
            f"{refused}. That is the term's last week and has to fit, or the term is one week "
            "short of itself — and until it inserts, the refusal below says nothing about the "
            "range."
        )

    refused_overrun = False
    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "week",
                chain,
                **{WEEK_NUMBER_COLUMN: SUMMER_TERM_WEEKS + 1},
            )
    except DatabaseError:
        refused_overrun = True

    assert refused_overrun, (
        f"Week {SUMMER_TERM_WEEKS + 1} was written into a {SUMMER_TERM_WEEKS}-week term. "
        "Criterion 3: 'week rows for a term are contiguous from 1 to the term length', and the "
        "database owns the range. Note that the number is a legal week in an 18-week term, so a "
        "range check that does not read the term's own length passes everything above this line "
        "and fails here — which is the defect this case exists to find."
    )


def test_a_week_number_below_one_is_refused(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 3, the range half at the bottom edge: weeks start at 1.

    Its own test rather than folded into the one above, because the two fail for
    different reasons: an upper bound written against a hardcoded 18 and a lower
    bound left off entirely are separate mistakes, and a week 0 quietly becomes
    an off-by-one everywhere the term axis is plotted.
    """
    chain: dict[str, Any] = {}
    seed_term(db_session, declared_tables, chain, SUMMER_TERM_WEEKS)

    try:
        with db_session.begin_nested():
            seed_row(db_session, declared_tables, "week", chain, **{WEEK_NUMBER_COLUMN: 1})
    except DatabaseError as refused:
        pytest.fail(
            f"Week 1 was refused: {refused}. Until the first week of a term inserts, the refusal "
            "below says nothing about where the range starts."
        )

    refused_zero = False
    try:
        with db_session.begin_nested():
            seed_row(db_session, declared_tables, "week", chain, **{WEEK_NUMBER_COLUMN: 0})
    except DatabaseError:
        refused_zero = True

    assert refused_zero, (
        "Week 0 was written into a term. Criterion 3 runs the weeks 'from 1 to the term length', "
        "and SPEC §2.2 labels the axis TERM 01 upward. A week 0 in the table is a row every "
        "later count includes and no chart has a place for."
    )


@pytest.mark.slow
@settings(
    max_examples=25,
    deadline=None,
    # The database session is function-scoped, so Hypothesis is right to warn:
    # examples share it. Each one runs inside its own savepoint and rolls back,
    # which is the state reset the health check is asking about, and a
    # session-scoped session would not give the surrounding module its own
    # isolation.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(weeks=st.integers(min_value=1, max_value=18))
def test_the_week_producer_covers_one_to_the_term_length_with_no_gaps(
    db_session: Any, declared_tables: dict[str, Table], weeks: int
) -> None:
    """Criterion 3, the no-gaps half: the producer's set is exactly 1..N.

    A property rather than an example, as the criterion asks — "exercised across
    generated term lengths rather than one example" — because the failures this
    is looking for are off-by-one and they hide at particular lengths. A producer
    that yields `range(N)` is right about the count and wrong about every number;
    one that yields `range(1, N)` is right until you count; one that yields
    `range(1, N + 2)` is caught only at the top. A single 18-week example finds
    some of those and a single 12-week example finds the same ones.

    The lengths generated run down to 1, which is not a term SPEC §2.2 describes.
    It is generated anyway because a producer that mishandles the degenerate term
    is a real defect and nothing in the ticket forbids a one-week term; if the
    schema turns out to refuse it, that is a range this file should narrow — and
    a decision worth seeing — rather than something to discover in E11.

    Sorted before comparing, because the criterion is about the set: "the set is
    exactly 1..N with no gaps". Comparing sorted lists rather than sets is
    deliberate — a set comparison would forgive a producer that yields week 3
    twice.
    """
    producer = week_producer()

    savepoint = db_session.begin_nested()
    try:
        chain: dict[str, Any] = {}
        try:
            term = seed_term(db_session, declared_tables, chain, weeks)
        except DatabaseError as refused:
            pytest.fail(
                f"A term of {weeks} weeks was refused by the database: {refused}. This property "
                "generates lengths from 1 to 18; if the schema constrains the length more "
                "narrowly than that, the generator here is what changes, and the pull request "
                "should say what the accepted range is and why."
            )

        try:
            produced = producer(term)
        except (TypeError, AttributeError) as failure:
            pytest.fail(
                f"Calling `{producer.__name__}` with the term row raised {failure!r}. The ticket "
                "says the function produces a term's week rows *for a term*, so the term is what "
                "this test passes it, and it passes nothing else — a second argument invented "
                "here would become the interface. If the producer takes something else, say so "
                "in the pull request and this call is the one line that changes."
            )

        numbers = week_numbers_produced(db_session, declared_tables, term, produced)

        assert numbers == list(range(1, weeks + 1)), (
            f"For a {weeks}-week term the producer covers {numbers}, and criterion 3 wants "
            f"exactly {list(range(1, weeks + 1))}. A gap leaves a week of the term with no row, "
            "so every query that walks the week axis skips it silently; a repeat double-counts "
            "it; a number outside the range is a week the term does not have."
        )
    finally:
        savepoint.rollback()


# ---------------------------------------------------------------------------
# ADR 0018 — the composite foreign key keeps the carried length true, so the
# local CHECK is not a weaker check. None of these three holds an acceptance
# criterion: they hold the record that decided how criteria 3 and 5 are
# enforced, and without them the whole trigger-versus-key argument rests on a
# measurement nobody re-runs (`docs/MISTAKES.md` entry 2). The first is the
# carried length being checked when a row is written; the other two are its
# being kept true when the term is edited.
# ---------------------------------------------------------------------------


def test_a_week_row_that_misstates_its_terms_length_is_refused(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """ADR 0018's fourth measurement row, the one it calls "the one that matters".

    The decision's words: "a row that *lies* about its term's length is refused
    by the key, so the local check is not a weaker check." That sentence is what
    the whole design rests on. The local check compares two columns of one row,
    and a check like that is only as good as the second column: if a writer may
    put any number in the carried length, the rule reduces to "a week's number is
    at most whatever the row says", which forbids nothing. The composite foreign
    key is what makes that column mean "this row's term's length", and this is
    the test of that.

    **The row refused here passes the local check.** A 12-week term, week 13,
    claiming a term length of 18: 13 is at most 18, so the check is satisfied and
    the only thing left to refuse it is the key, which finds no term with that id
    and that length. **A row that also failed the local check would prove
    nothing** — insert week 13 claiming 12 and it is refused by the check alone,
    exactly as it would be with no key in the schema at all, and that is already
    asserted by `test_a_week_number_beyond_the_term_length_is_refused`. So the
    three numbers are not interchangeable: the claimed length must be at least
    the week number, so that the check passes, and different from the term's real
    length, so that the key does not. Anyone simplifying this test by making the
    claimed and real lengths agree has deleted it.

    **The control is the same row in a term that really is 18 weeks**, carrying
    the same claimed length and the same number. The two inserts are identical in
    every value except which term they sit in, so the refusal below cannot be
    about week 13 being an odd number to write, or about the carried column being
    supplied explicitly at all.

    Supplying the false value is a per-call override and changes nothing about
    how anything else here seeds: `seed_row` still fills the carried column by
    following the foreign key to the term already in the chain, which is honest
    by construction, and every other test in this module goes on relying on that.
    """
    carried = carried_length_column(declared_tables)
    outside_the_summer_term = SUMMER_TERM_WEEKS + 1
    claimed = {WEEK_NUMBER_COLUMN: outside_the_summer_term, carried: FALL_TERM_WEEKS}

    honest: dict[str, Any] = {}
    seed_term(db_session, declared_tables, honest, FALL_TERM_WEEKS)
    try:
        with db_session.begin_nested():
            seed_row(db_session, declared_tables, "week", honest, **claimed)
    except DatabaseError as refused:
        pytest.fail(
            f"Week {outside_the_summer_term} of a {FALL_TERM_WEEKS}-week term, carrying "
            f"{FALL_TERM_WEEKS} as its term's length, was refused: {refused}. That row is honest "
            "and inside its term, so it has to insert — and until it does, the refusal below "
            "says nothing about the claim being false."
        )

    lying = branch_from(honest, "institution")
    seed_term(db_session, declared_tables, lying, SUMMER_TERM_WEEKS)

    refused_lie = False
    try:
        with db_session.begin_nested():
            seed_row(db_session, declared_tables, "week", lying, **claimed)
    except DatabaseError:
        refused_lie = True

    assert refused_lie, (
        f"A week row was written into a {SUMMER_TERM_WEEKS}-week term claiming its term is "
        f"{FALL_TERM_WEEKS} weeks long, and carrying week {outside_the_summer_term} — which is "
        "outside that term. The local check passed it, because "
        f"{outside_the_summer_term} is at most {FALL_TERM_WEEKS}; ADR 0018 has the composite "
        "foreign key refuse it, because no term has that id and that length. Without the key "
        "the carried column is a number the row supplied rather than its term's length, and the "
        "range rule in criterion 3 stops constraining anything: every row that would violate it "
        "can claim a longer term instead."
    )


def test_shortening_a_term_that_strands_no_week_rewrites_the_carried_lengths(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """ADR 0018: `ON UPDATE CASCADE` rewrites the copy when the term's length changes.

    The decision's own words: the foreign key "is what makes `term_length_weeks`
    mean 'this row's term's length' instead of 'a number this row supplied'", and
    `ON UPDATE CASCADE` "rewrites it when the term's length changes". Everything
    else in this module writes that copy through `seed_row` at insert time, so
    every other test would pass just as well against an ordinary column nobody
    maintains. This is the one that asks whether it is *kept* true.

    **It is the mechanism guard, and it is why the sibling test below does not
    need to name a constraint.** All three of the following were run against a
    mutated schema in PR #21's third reviewer round, and the third is here in the
    form the running corrected it to:

      - Swap the key for the trigger ADR 0018 rejected, which keeps the carried
        column and fills it from a trigger instead: this fails at discovery,
        because the column is left with no key behind it.
      - Swap `ON UPDATE CASCADE` for `RESTRICT`, and it fails at the update.
      - Keep the column and drop the key, and it **also** fails at discovery, not
        on the last assertion. The paragraph used to say the latter, reasoned
        rather than measured, and the reasoning skipped a step: this module never
        spells the carried column, it finds it by following the key to
        `term.length_weeks`, so dropping the key removes the only handle it has.
        A column nobody references is one `carried_length_column` cannot name.

    Two of the three therefore report through `foreign_key_column` rather than
    through an assertion here, and they report the same symptom from two
    different schemas. That is still a red naming the missing thing, but it is
    worth knowing before reading a mutation run: this test says "the copy does
    not track" only where there is a key for it to track through.

    One more thing that run turned up, because it is easy to misread the other
    direction. Dropping the key also reds criterion 3's range test, and not for a
    reason that test is about: with no key to copy from, `seed_row` falls through
    to `invented_value`, which hands any column whose name mentions a length
    `DEFAULT_LENGTH_WEEKS`, so a week 13 arrives claiming an 18-week term and
    satisfies the local check. The range test is not a second guard on the key —
    it is a fixture default meeting a schema that no longer constrains it.

    **Written in the shortening direction on purpose.** Lengthening cascades too,
    and asserting that here would be the more obvious test — but ADR 0018 records
    lengthening as the direction with a known gap, left to E2 or E11, and an
    assertion about it would be coupled to whether a bare lengthening is still
    accepted once that gap is closed. Shortening a term that strands nothing has
    no gap: the weeks are 1..N before and 1..N after, and nothing any later
    ticket does should change what the database makes of it. Nothing here says
    the resulting term is *desirable* — only what the cascade does to the copies.

    The before-assertion is not ceremony. "The copies read 11 afterwards" is
    equally true of a column that has always read 11 and of one nothing ever
    wrote, so the copies are required to start at the term's original length
    before their changing is allowed to mean anything (`docs/MISTAKES.md` entry
    3).
    """
    term = require_table(declared_tables, "term")
    length_column = require_column(term, TERM_LENGTH_COLUMNS)
    shorter = SUMMER_TERM_WEEKS - 1

    chain: dict[str, Any] = {}
    seeded = seed_term(db_session, declared_tables, chain, SUMMER_TERM_WEEKS)
    seed_weeks(db_session, declared_tables, chain, shorter)

    before = carried_term_lengths(db_session, declared_tables, seeded)
    assert before == [SUMMER_TERM_WEEKS] * shorter, (
        f"The {shorter} week rows of a {SUMMER_TERM_WEEKS}-week term carry {before}, not "
        f"{[SUMMER_TERM_WEEKS] * shorter}. They are filled by following the composite foreign "
        "key at insert, so either the seeding did not happen or the copy does not start out "
        "agreeing with the term — and until it does, the assertion below cannot tell a cascade "
        "from a column that already held the answer."
    )

    shortening = (
        update(term).where(matching_primary_key(term, seeded)).values(**{length_column: shorter})
    )
    try:
        applied = db_session.execute(shortening)
    except DatabaseError as refused:
        pytest.fail(
            f"Shortening a {SUMMER_TERM_WEEKS}-week term to {shorter} weeks was refused: "
            f"{refused}. The term holds weeks 1 to {shorter}, so nothing is stranded and there "
            "is nothing for the check on the cascaded rows to reject. A refusal here is either "
            "`ON UPDATE RESTRICT` where ADR 0018 specifies `CASCADE`, or a rule tying the "
            "length to the dates that the term's own dates no longer satisfy."
        )

    assert applied.rowcount == 1, (
        f"The update matched {applied.rowcount} rows rather than 1, so it changed no term and "
        "the reading below would report the copies as they always were."
    )

    after = carried_term_lengths(db_session, declared_tables, seeded)
    assert after == [shorter] * shorter, (
        f"After the term's length changed from {SUMMER_TERM_WEEKS} to {shorter}, its week rows "
        f"carry {after}. ADR 0018 puts a copy of the term's length on every `week` row and keeps "
        "it true with `ON UPDATE CASCADE`, so that the range check comparing a week's number "
        "against it is comparing against the term's real length. A copy that does not follow is "
        "a number the row supplied, and the local check becomes exactly the weaker check the "
        "ADR argues it is not."
    )


def test_shortening_a_term_below_a_week_it_holds_is_refused(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """ADR 0018's central claim: the shortening is refused at the moment of the shortening.

    The decision's measurement table has it as a row — "shortening 18 → 12 with a
    week 18 present: refused" — and the whole argument against the trigger
    alternative rests on it. The trigger version accepts both halves under
    `READ COMMITTED` and leaves "a 6-week term holding weeks [12]", a row no
    query will ever complain about; the key version refuses, because the cascade
    rewrites the week row and the check on that row is re-evaluated. A calendar
    editor that shortens a term is E11, and §6.3 says admins edit the calendar,
    so this is an edit that happens rather than a hypothetical.

    **The control is the same edit, by the same amount, on a term whose last week
    is the one it is being shortened to.** Nothing is stranded there, so it has
    to be accepted, and it rules out every reason a shortening could be refused
    that has nothing to do with the weeks: a check tying the length to the dates,
    which E0-06 permits and does not require; and `ON UPDATE RESTRICT`, which
    would refuse any change to a term a week references. The two halves differ in
    exactly one row — whether week 12 exists.

    **No constraint is named, and that is a decision rather than an inheritance
    of the module's earlier rule.** The rule was "assert the criterion, not the
    mechanism", and it applied while the mechanism was the implementer's to
    choose; ADR 0018 settled that, so naming would be defensible now. It is still
    not what this asserts, for two reasons. A constraint's name here is produced
    by `Base.metadata`'s naming convention from a name in the model, and the epic
    README's rule is that names follow the convention rather than being chosen —
    so a rename is a refactor, and a test holding one reports it as a regression.
    And the mechanism does not go unheld: the sibling test above reads the
    carried length and watches it follow the term, which no other mechanism
    produces at all. What is left for this test is the claim itself, which is
    about an outcome.

    **What a single session cannot show**, and what therefore is not claimed
    here: the concurrency difference. A trigger implementation would pass this
    test, because it refuses the same edit in the same transaction; it differs
    only when the shortening and the insert are two transactions, which needs two
    connections and is the ADR's own measurement rather than this suite's.

    There is no "and afterwards the term still reads 12 weeks" assertion. The
    refused update runs inside `begin_nested()`, so by the time anything could
    query, the savepoint has rolled back and the term reads 12 whatever the
    database did — an assertion that cannot fail, which is the shape
    `docs/MISTAKES.md` entry 3 records and which
    `tests/integration/test_org_containment_schema.py` removed for the same
    reason. What the after-state is good for is the failure message, so it is
    read inside the savepoint and reported there.
    """
    term = require_table(declared_tables, "term")
    length_column = require_column(term, TERM_LENGTH_COLUMNS)
    shorter = SUMMER_TERM_WEEKS - 1

    spare: dict[str, Any] = {}
    control = seed_term(db_session, declared_tables, spare, SUMMER_TERM_WEEKS)
    seed_weeks(db_session, declared_tables, spare, shorter)
    relaxing = (
        update(term).where(matching_primary_key(term, control)).values(**{length_column: shorter})
    )
    try:
        db_session.execute(relaxing)
    except DatabaseError as refused:
        pytest.fail(
            f"The control shortening — a {SUMMER_TERM_WEEKS}-week term holding weeks 1 to "
            f"{shorter}, shortened to {shorter} — was refused: {refused}. Nothing is stranded by "
            "it, so a schema that refuses it refuses shortening for some reason other than the "
            "weeks, and the refusal below would say nothing about week 12."
        )

    chain = branch_from(spare, "institution")
    seeded = seed_term(db_session, declared_tables, chain, SUMMER_TERM_WEEKS)
    seed_weeks(db_session, declared_tables, chain, SUMMER_TERM_WEEKS)

    shortening = (
        update(term).where(matching_primary_key(term, seeded)).values(**{length_column: shorter})
    )
    refused_shortening = False
    left_behind: list[int] = []
    try:
        with db_session.begin_nested():
            db_session.execute(shortening)
            left_behind = carried_term_lengths(db_session, declared_tables, seeded)
    except DatabaseError:
        refused_shortening = True

    assert refused_shortening, (
        f"A {SUMMER_TERM_WEEKS}-week term holding weeks 1 to {SUMMER_TERM_WEEKS} was shortened "
        f"to {shorter} weeks and the database accepted it; its week rows then carried "
        f"{left_behind}. Week {SUMMER_TERM_WEEKS} is now outside its own term, and no later "
        "query will complain, because every rule that could is written against the copy the "
        "cascade has just rewritten. ADR 0018 refuses this at the moment of the shortening — "
        "that is the property it chose the composite foreign key for, over a trigger that "
        "commits the same violation whenever the two edits arrive in different transactions."
    )


# ---------------------------------------------------------------------------
# Criterion 5 — a start letter may not be longer than the term it belongs to.
# ---------------------------------------------------------------------------


def test_a_start_letter_as_long_as_its_term_is_accepted(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 5's boundary: "exceeds" is not "equals".

    A 12-week letter in a 12-week term is the ordinary case — SPEC §2.2's Fall
    2026 map has 12-week U, R and Q — and it is the row an implementation using
    `>=` where the criterion says "exceeds" would refuse. Its own test rather
    than only a control below, because that refusal is a defect in the schema and
    deserves an assertion of its own rather than a message about a fixture.
    """
    letter_map = require_table(declared_tables, "start_letter_map")
    length = require_column(letter_map, LETTER_LENGTH_COLUMNS)

    chain: dict[str, Any] = {}
    seed_term(db_session, declared_tables, chain, SUMMER_TERM_WEEKS)

    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "start_letter_map",
                chain,
                **{START_LETTER_COLUMN: FITTING_LETTER, length: LETTER_FITTING_THE_TERM},
            )
    except DatabaseError as refused:
        pytest.fail(
            f"A {LETTER_FITTING_THE_TERM}-week start letter in a {SUMMER_TERM_WEEKS}-week term "
            f"was refused: {refused}. Criterion 5 rejects a length that *exceeds* the term's, "
            "and a course that runs the whole term is the common case, not the edge — SPEC "
            "§2.2's 12-week U, R and Q sit in an 18-week fall term, and a 12-week summer term "
            "holds a 12-week section."
        )


def test_a_start_letter_longer_than_its_term_is_refused(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 5: a letter longer than its own term is rejected.

    **Every length here is one SPEC §2.2 allows**, which is the criterion's own
    instruction and the reason 500 weeks is not what this relies on: 15 is a
    course length with its own letters in the seed map (15-week V/D), so a plain
    range check over §2.2's lengths accepts it happily. Only a rule that reads
    the row's own term refuses it, and that is the rule criterion 5 is about.

    The control is a 12-week letter in the same 12-week term, so a refusal below
    is known to be about the length rather than about the letter map being
    unwritable (`docs/MISTAKES.md` entry 3).

    Nothing here names a constraint. The ticket leaves the mechanism open between
    a trigger, a composite foreign key carrying the term's length, and something
    else, and owes an ADR for the choice; a test that asserted a constraint name
    or a constraint type would decide it.
    """
    letter_map = require_table(declared_tables, "start_letter_map")
    length = require_column(letter_map, LETTER_LENGTH_COLUMNS)

    chain: dict[str, Any] = {}
    seed_term(db_session, declared_tables, chain, SUMMER_TERM_WEEKS)

    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "start_letter_map",
                chain,
                **{START_LETTER_COLUMN: FITTING_LETTER, length: LETTER_FITTING_THE_TERM},
            )
    except DatabaseError as refused:
        pytest.fail(
            f"The control letter, {LETTER_FITTING_THE_TERM} weeks in a {SUMMER_TERM_WEEKS}-week "
            f"term, was refused: {refused}. Until a letter that fits inserts, the refusal below "
            "says nothing about length."
        )

    refused_overlong = False
    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "start_letter_map",
                chain,
                **{START_LETTER_COLUMN: OVERLONG_LETTER, length: LETTER_LONGER_THAN_THE_TERM},
            )
    except DatabaseError:
        refused_overlong = True

    assert refused_overlong, (
        f"A {LETTER_LONGER_THAN_THE_TERM}-week start letter was written into a "
        f"{SUMMER_TERM_WEEKS}-week term. Criterion 5 rejects it. The length is legal in general "
        "— SPEC §2.2 gives 15-week sections their own letters — so a range check over the "
        "allowed lengths passes this row through; the comparison has to be against this row's "
        "own term. E0-07 derives a section's end date from the letter and the term calendar, and "
        "a letter that outruns its term derives an end date after the term is over."
    )


# ---------------------------------------------------------------------------
# Criterion 4 — timestamps carry an offset, and a naive value is refused.
# ---------------------------------------------------------------------------


def test_a_naive_datetime_cannot_be_written_to_any_timestamp_column(
    db_session: Any,
    declared_tables: dict[str, Table],
    reflected_tables: dict[str, Table],
) -> None:
    """Criterion 4: a naive datetime is refused by every timestamp column.

    **Postgres will not do this for you, and that is the point of the test.** A
    naive value bound to a `timestamptz` column is accepted and silently
    interpreted in the session `TimeZone`, so the guard has to live on the column
    type, where every writer — ORM, Core, a seed script — meets it. That is why
    the insert goes through `Base.metadata` rather than through a reflected
    table: a guard the declared column does not carry is not one "any timestamp
    column" can claim.

    **The control and the mutation differ in exactly one thing: `tzinfo`.** The
    naive value is the aware one with its offset stripped, and the session is
    pinned to UTC first, so an unguarded write would store the very same instant
    the control stored. Any other constraint that accepted the control therefore
    accepts this too, and a refusal can only be about the missing offset
    (`docs/MISTAKES.md` entry 3 — a rejection that comes from somewhere else is
    the failure mode this shape removes).
    """
    columns = timestamp_columns(reflected_tables)
    assert columns, (
        f"None of {list(CALENDAR_TABLES)} has a timestamp column, so this test would pass "
        "against a schema with no timestamps at all. E0-06's `survey_window` models the weekly "
        "open and close (SPEC §3.1: opens Friday 18:00, closes Sunday 23:59:59 in the "
        "institution timezone), which is at least two of them."
    )

    db_session.execute(text("SET TIME ZONE 'UTC'"))

    for table_name, column_name in columns:
        aware = datetime_hint(column_name)
        try:
            with db_session.begin_nested():
                seed_row(db_session, declared_tables, table_name, {}, **{column_name: aware})
        except DatabaseError as refused:
            pytest.fail(
                f"An aware datetime was refused by `{table_name}.{column_name}`: {refused}. "
                "Until the ordinary row inserts, a refusal below says nothing about naivety."
            )

        naive = aware.replace(tzinfo=None)
        refused_naive = False
        try:
            with db_session.begin_nested():
                seed_row(db_session, declared_tables, table_name, {}, **{column_name: naive})
        except (StatementError, ValueError, TypeError):
            refused_naive = True

        assert refused_naive, (
            f"`{table_name}.{column_name}` accepted the naive datetime {naive!r}. Postgres does "
            "not refuse this on its own — it reads the value in the session timezone and stores "
            "whatever instant that happens to name, so the same naive value means two different "
            "moments on two differently configured connections. SPEC §3.1 puts every survey "
            "window in the institution timezone and E0-06 requires timezone-aware timestamps "
            "throughout, so the column type has to refuse a value with no offset."
        )


def test_an_aware_datetime_keeps_its_instant_across_a_write_and_a_read(
    db_session: Any,
    declared_tables: dict[str, Table],
    reflected_tables: dict[str, Table],
) -> None:
    """E0-06 scope: "All timestamps timezone-aware."

    Criterion 4 refuses the value with no offset; this refuses the column that
    throws the offset away. A `timestamp without time zone` accepts an aware
    datetime perfectly happily and hands back a naive one, so a window written at
    18:00 Eastern comes back as 18:00 of nothing in particular — and a schema
    like that passes criterion 4's test the moment a type guard is added on top
    of it.

    The value written is the same *instant* the seeding helper would have used,
    re-expressed in the institution timezone, so any ordering constraint between
    an open and a close is left exactly as it was. The non-zero offset is
    asserted first, because at UTC this test would prove nothing.
    """
    columns = timestamp_columns(reflected_tables)
    assert columns, (
        f"None of {list(CALENDAR_TABLES)} has a timestamp column, so there is nothing to write "
        "and this test would pass vacuously. E0-06's `survey_window` carries the weekly open and "
        "close."
    )

    for table_name, column_name in columns:
        moment = datetime_hint(column_name).astimezone(INSTITUTION_TIMEZONE)
        assert moment.utcoffset() != timedelta(0), (
            f"The value written to `{table_name}.{column_name}` has a zero offset, so a column "
            "that discarded the offset would return an identical instant and this test could "
            "not tell the two apart. SPEC §3.1's default institution timezone is "
            "America/New_York, which is not UTC at any time of year."
        )

        row = seed_row(db_session, declared_tables, table_name, {}, **{column_name: moment})
        stored = row[column_name]

        assert stored is not None and stored.tzinfo is not None, (
            f"`{table_name}.{column_name}` returned {stored!r} for a value written as {moment!r}. "
            "A naive value coming back means the column is `timestamp without time zone`: it "
            "took the offset, dropped it, and left every later reader to guess which zone the "
            "wall-clock belongs to. SPEC §3.1 is explicit that a survey window is a moment in "
            "the institution timezone."
        )
        assert stored == moment, (
            f"`{table_name}.{column_name}` stored {stored!r} for a value written as {moment!r}. "
            "The two name different instants, so the offset was reinterpreted rather than "
            "preserved — a window that opens Friday 18:00 Eastern would open at 18:00 UTC, four "
            "hours early, for everyone."
        )


# ---------------------------------------------------------------------------
# `section.term_id` and the uniqueness rule it makes writable. E0-06's scope
# carries both; the acceptance criteria carry neither, which is
# `docs/MISTAKES.md` entry 2's exact shape — the half of SPEC §8's "sections
# belong to exactly one course and one term" that this ticket exists to close
# would otherwise ship with nothing asserting it.
# ---------------------------------------------------------------------------


def test_a_section_cannot_be_written_without_a_term(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """E0-06 scope: `section.term_id` lands here, non-nullable.

    SPEC §8: sections belong to exactly one course *and one term*. E0-05 could
    only enforce the course half, because `term` did not exist; this is the other
    half, and a nullable column would leave a section belonging to no term at
    all — which E0-07 then cannot derive dates for and E2 cannot schedule.

    The control section goes in first, through the same helper, so the refusal
    below is known to be about the null and not about anything else in the row.
    """
    section = require_table(declared_tables, "section")
    assert SECTION_TERM_COLUMN in section.c, (
        f"`section` has no `{SECTION_TERM_COLUMN}` column — it has "
        f"{[column.name for column in section.columns]}. E0-06's scope spells it out: "
        "'`section.term_id` lands here, non-nullable and referencing `term`'."
    )

    chain: dict[str, Any] = {}
    try:
        seed_row(
            db_session, declared_tables, "section", chain, **{SECTION_CODE_COLUMN: SECTION_CODE}
        )
    except DatabaseError as refused:
        pytest.fail(
            f"An ordinary section was refused: {refused}. Until one inserts, a refusal below "
            "says nothing about the term."
        )

    refused_null = False
    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "section",
                chain,
                **{SECTION_CODE_COLUMN: OTHER_SECTION_CODE, SECTION_TERM_COLUMN: None},
            )
    except DatabaseError:
        refused_null = True

    assert refused_null, (
        f"A section was written with `{SECTION_TERM_COLUMN}` null. SPEC §8 puts every section in "
        "exactly one course and one term, and a section with no term has no calendar: its start "
        "and end dates derive from its code *and* the term's start-letter map (§2.2), so there "
        "is nothing to derive them from."
    )


def test_section_term_id_references_the_term_table(reflected_tables: dict[str, Table]) -> None:
    """E0-06 scope: the term reference points at `term`, in the database.

    Separate from the null test above because the two fail for different reasons.
    A `term_id` that is NOT NULL but references nothing accepts any uuid at all,
    including one that names a row in another table or no row anywhere, and the
    section's calendar is then a dangling pointer rather than a missing one.
    Read from the reflected schema, because a relationship declared only in the
    ORM is not a constraint.
    """
    section = require_table(reflected_tables, "section")
    targets = sorted(
        {
            key.column.table.name
            for key in section.foreign_keys
            if key.parent.name == SECTION_TERM_COLUMN
        }
    )

    assert targets == ["term"], (
        f"`section.{SECTION_TERM_COLUMN}` references {targets or 'nothing'} in the migrated "
        "database. E0-06: '`section.term_id` lands here, non-nullable and referencing `term`'. "
        "Without the foreign key the column holds a uuid that may name no term at all, and "
        "SPEC §8's containment stops being something the database enforces."
    )


def test_a_duplicate_section_code_within_one_course_and_term_is_refused(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """E0-06 scope: the uniqueness rule over `(course_id, term_id, lms_section_code)`.

    A second section with a different code goes in first, so that the refusal is
    known to be about the repeated code and not about a course being allowed only
    one section (`docs/MISTAKES.md` entry 3).
    """
    chain: dict[str, Any] = {}
    seed_row(db_session, declared_tables, "section", chain, **{SECTION_CODE_COLUMN: SECTION_CODE})

    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "section",
                chain,
                **{SECTION_CODE_COLUMN: OTHER_SECTION_CODE},
            )
    except DatabaseError as refused:
        pytest.fail(
            f"A second section with a different code in the same course and term was refused: "
            f"{refused}. A course runs many sections in a term — that is what the ordinal in "
            "`R3WW` counts (SPEC §2.2) — so until this inserts the refusal below proves nothing."
        )

    refused_duplicate = False
    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "section",
                chain,
                **{SECTION_CODE_COLUMN: SECTION_CODE},
            )
    except DatabaseError:
        refused_duplicate = True

    assert refused_duplicate, (
        f"The section code {SECTION_CODE!r} was written twice into one course and term. E0-06: "
        "'a section code identifies a section within a course *and* term'. Two rows with the "
        "same code in the same term give an LTI launch and the roster sync two candidate "
        "sections and no rule for choosing."
    )


def test_the_same_section_code_may_recur_in_a_later_term(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """E0-06 scope: the reason the constraint needed `term_id` before it could be written.

    This is the half that fails when the constraint is over `(course_id,
    lms_section_code)` alone — the shape E0-05 would have had to write without a
    `term` table, and the ticket's stated reason for landing the column here.
    `BIOL 215 R3WW` runs again next fall, and a constraint that forbids it fails
    at roster sync a term later, with nothing in this suite having said so.
    """
    chain: dict[str, Any] = {}
    seed_row(db_session, declared_tables, "section", chain, **{SECTION_CODE_COLUMN: SECTION_CODE})

    later = branch_from(chain, "institution")
    seed_row(db_session, declared_tables, "term", later)
    assert later["term"] != chain["term"], (
        "Seeding a second term reused the first one, so there is no later term to put the "
        "section in and the assertion below would be about nothing."
    )

    next_term = dict(chain) | {"term": later["term"]}
    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "section",
                next_term,
                **{SECTION_CODE_COLUMN: SECTION_CODE},
            )
    except DatabaseError as refused:
        pytest.fail(
            f"The section code {SECTION_CODE!r} was refused in a second term of the same course: "
            f"{refused}. E0-06 lands `section.term_id` precisely so this is legal — a uniqueness "
            "rule without the term 'would forbid the same code recurring next term', and section "
            "codes recur every term by construction (SPEC §2.2: the start letter encodes a "
            "length and a start date *within* a term)."
        )


def test_the_same_section_code_in_two_courses_of_one_term_is_accepted(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """E0-06 scope: the code identifies a section *within a course*, not across the term.

    The other direction of the same rule, and the one that fails if the
    constraint is written over `(term_id, lms_section_code)`. Nothing in a
    section code names its course, so `R3WW` is a code many courses use in the
    same term; the two courses here share a prefix so that the only difference
    between the two sections is the course.
    """
    chain: dict[str, Any] = {}
    seed_row(db_session, declared_tables, "section", chain, **{SECTION_CODE_COLUMN: SECTION_CODE})

    sibling = branch_from(chain, "institution", "college", "department", "prefix")
    seed_row(db_session, declared_tables, "course", sibling, **{COURSE_NUMBER_COLUMN: "151"})
    assert sibling["course"] != chain["course"], (
        "Seeding a second course reused the first one, so there is no sibling course to put the "
        "section in and the assertion below would be about nothing."
    )

    other_course = dict(chain) | {"course": sibling["course"]}
    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "section",
                other_course,
                **{SECTION_CODE_COLUMN: SECTION_CODE},
            )
    except DatabaseError as refused:
        pytest.fail(
            f"The section code {SECTION_CODE!r} was refused in a second course of the same term: "
            f"{refused}. E0-06 scopes the constraint to '(course_id, term_id, "
            "lms_section_code)' — a code is unique within a course and a term, and every course "
            "in a term draws from the same small alphabet of start letters (SPEC §2.2)."
        )


def test_exactly_one_index_on_section_leads_with_course_id(migrated_engine: Any) -> None:
    """E0-06 scope: `ix_section_course_id` goes only if the new constraint replaces it.

    The ticket makes the drop conditional — "**if — and only if — that constraint
    lands leading with `course_id`**" — so this asserts the condition rather than
    an answer, and the same sentence covers both orderings: whatever order the
    unique constraint takes, exactly one index on `section` may lead with
    `course_id`.

      - Constraint leading with `course_id`, `ix_section_course_id` dropped: one.
      - Constraint leading with `course_id`, the index kept as well: two, and
        that is the write cost on every section insert the ticket refuses.
      - Constraint ordered some other way, `ix_section_course_id` kept: one.
      - Constraint ordered some other way and the index dropped anyway: zero, and
        the unindexed foreign key E0-05's review found is back.

    Counting rather than naming, and counting rather than asserting that a name
    is absent: an absence is satisfied by a table that lost all its indexes
    (`docs/MISTAKES.md` entry 3), and a count of exactly one is not.

    Leading position and not membership, for the reason
    `tests/integration/test_org_containment_schema.py` gives: Postgres 17 has no
    skip scan, so an index that merely contains `course_id` does not serve an
    equality lookup on it.
    """
    with migrated_engine.connect() as connection:
        inspector = inspect(connection)
        indexes = inspector.get_indexes("section")
        unique_constraints = inspector.get_unique_constraints("section")

    def leads(columns: Any) -> bool:
        return bool(columns) and columns[0] == SECTION_COURSE_COLUMN

    # Deduplicated by name: the index Postgres builds behind a unique constraint
    # carries the constraint's own name, and the two inspector calls both report
    # it. Counting them separately would read one index as two.
    leading = {index["name"] for index in indexes if leads(index.get("column_names"))}
    leading |= {
        constraint["name"]
        for constraint in unique_constraints
        if leads(constraint.get("column_names"))
    }

    assert len(leading) == 1, (
        f"{len(leading)} indexes on `section` lead with `{SECTION_COURSE_COLUMN}` "
        f"({sorted(leading)}); the schema holds "
        f"{sorted(index['name'] for index in indexes)}. Two means the composite unique index and "
        "`ix_section_course_id` both serve the same equality lookup, which costs a write on "
        "every section insert for no read benefit — drop `ix_section_course_id` in E0-06's "
        "migration. Zero means neither does, and a lookup by course reads the whole table, which "
        "passes on seed data and degrades every term. E0-06's scope makes the drop conditional "
        "on the constraint's column order, so if the constraint does not lead with "
        f"`{SECTION_COURSE_COLUMN}` the index stays."
    )
