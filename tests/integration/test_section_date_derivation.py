"""A section's calendar comes from its code and its term's map — ticket E0-07.

Acceptance criteria 1, 3 (the half that needs a map), 4, 5, 6 and 7, plus the
scope item that puts the four derived columns on `section` and populates them
through this service. Criterion 2 and the grammar are in
`tests/unit/test_section_code_parsing.py`, which needs no database.

**Why these need a real Postgres.** The derivation reads `start_letter_map`, and
that is the whole point of the ticket: a section's length and start date are per
*term* configuration, not constants in the code. A test that handed the service a
map it had built in memory would pass just as well against an implementation that
never looked at the database, which is the defect most worth catching here — a
letter table written into the module works perfectly against Fall 2026 and is
wrong the first time an institution edits its calendar.

**The end-date convention this file asserts, and the evidence for it.** Criterion
4 says `end_date` equals `start_date` plus `length_weeks`, and neither §2.2 nor
the ticket says whether the last day of the section is `start + 7 x weeks` or the
day before it. This file takes the inclusive reading — `start + 7 x weeks - 1` —
and it is not a preference. SPEC §2.2's own seed map decides it: Fall 2026 runs
18 calendar weeks from Monday 8/17, and `Q` is a 12-week letter starting 9/28.
Under the inclusive reading Q's sections end 12/20, the term's last day; under the
exclusive one they end 12/21, one day *outside* the term — which criterion 5 then
requires the service to reject, making a letter the spec itself seeds unusable.
The weekday agrees: sections start Monday and end Sunday, and §3.1 closes the
week's survey window Sunday 23:59:59, so the last window of a section closes on
its end date. `END_DATE_IS_INCLUSIVE` below is the one line that changes if the
ticket settles this the other way, and the failure messages say so.

**What this file does not name.** Nothing inside `app.services.section_codes`:
the callables are discovered by `tests/conftest.py`'s `SectionCodeService`, which
says why at length. Column names are taken from the ticket where it spells them
(`letter`, and the four derived columns) and from a candidate constant where it
does not (a length in weeks, a start date on the map row) — the precedent, and
the reason, are in `tests/integration/test_term_calendar_schema.py`.

**Seeding.** `seed_row` here is a second implementation of the walker in that
module and deliberately a small one: it builds only what a term and a letter map
row need, and it resolves a declared `TypeDecorator` through to what the column
stores, because a helper that dispatches `isinstance` on the declared type dies
inside its own fixture against E0-06's timezone guard — the dispute in
`docs/disputes/E0-06-01.md`, and `docs/MISTAKES.md` entry 13. Consolidating the
two into one shared helper is worth doing and is not this ticket's to do at the
cost of editing a shipped module's fixtures.
"""

import string
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from inspect import signature
from itertools import count
from typing import Any
from uuid import uuid4

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
    select,
)
from sqlalchemy.exc import DatabaseError
from sqlalchemy.types import TypeDecorator

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# SPEC §2.2's Fall 2026 reference calendar, as fixture data. Not rows any
# migration inserts — E0-06 is explicit that the seed map is fixture data.
# ---------------------------------------------------------------------------

# 8/17/2026 is a Monday, and §2.2 gives fall 18 calendar weeks. The end date
# follows from those two under the inclusive reading argued in the module
# docstring: 8/17 + 18x7 - 1 = 12/20, a Sunday.
FALL_2026_START = date(2026, 8, 17)
FALL_2026_WEEKS = 18
FALL_2026_END = date(2026, 12, 20)

MONDAY = 0
SUNDAY = 6

# **This file's reading of criterion 4**, argued in the module docstring from
# §2.2's own seed values. One line to change.
END_DATE_IS_INCLUSIVE = True

# SPEC §2.2's Fall 2026 seed map: "12-week U/R/Q starting 8/17, 9/7, 9/28; 6-week
# E/F/H; 8-week X/Y/Z; 10-week S/T; 15-week V/D; 16-week K; 3-week sections
# numbered 2-7", as `(start position, length in weeks, weeks after the term
# start)`.
#
# **The lengths are the spec's and the offsets are this file's**, except for
# U/R/Q, whose offsets of 0, 3 and 6 weeks reproduce the three dates §2.2
# documents — 8/17, 9/7, 9/28 — and are therefore the spec's too. The rest are
# chosen only so that every cohort fits inside the 18-week term, which is what
# makes the map a valid one to assert against. Nothing is weakened by the
# choice: every assertion below compares the derivation against the row that was
# seeded, so an implementation carrying its own letter table disagrees with the
# fixture rather than agreeing with it by luck.
FALL_2026_SEED_MAP: tuple[tuple[str, int, int], ...] = (
    ("U", 12, 0),
    ("R", 12, 3),
    ("Q", 12, 6),
    ("E", 6, 0),
    ("F", 6, 4),
    ("H", 6, 8),
    ("X", 8, 0),
    ("Y", 8, 4),
    ("Z", 8, 8),
    ("S", 10, 0),
    ("T", 10, 6),
    ("V", 15, 0),
    ("D", 15, 3),
    ("K", 16, 0),
    ("2", 3, 0),
    ("3", 3, 3),
    ("4", 3, 6),
    ("5", 3, 9),
    ("6", 3, 12),
    ("7", 3, 15),
)

# §2.2's documented start dates for the three 12-week letters, spelled out so
# that the offsets above are checked against the spec rather than trusted.
DOCUMENTED_START_DATES = {"U": date(2026, 8, 17), "R": date(2026, 9, 7), "Q": date(2026, 9, 28)}

# §2.2: "Course lengths in weeks: 3, 6, 8, 10, 12, 15, 16 (plus an 18-week
# dissertation length)."
SECTION_LENGTHS = (3, 6, 8, 10, 12, 15, 16, 18)

ALL_STARTS = tuple(entry[0] for entry in FALL_2026_SEED_MAP)

# Start positions §2.2's Fall 2026 map does not hold. `A` is an ordinary letter
# nobody mapped; `1` and `8` sit either side of the 2-7 the spec numbers the
# 3-week sections with, which is where an off-by-one in a range check lands.
UNMAPPED_START = "A"
BELOW_THE_NUMBERED_RANGE = "1"
ABOVE_THE_NUMBERED_RANGE = "8"

# ---------------------------------------------------------------------------
# A second term, of a different length, whose map holds a different set of
# numbered positions. **Every number here is this suite's choice and is marked
# as one**: §2.2 gives summer 12 weeks and seeds no summer map, so unlike the
# Fall 2026 values above there is nothing in the spec to check these against.
#
# 5/11/2026 is a Monday, matching the convention every term in this module
# follows, and 12 weeks from it ends 8/2 — clear of the fall term, which starts
# 8/17, so the two can sit in one institution without any question of overlap.
#
# **The positions are deliberately neither contiguous nor the whole set.** A
# 12-week term has room for four 3-week blocks, and this map labels them 2, 3, 5
# and 7. §2.2 numbers the fall's six blocks 2 through 7; nothing in the spec or
# in E0-06 says a term's numbered positions must run consecutively, and E0-06's
# check on the letter column admits any single character, so this is a map an
# admin can configure. It is chosen this way because of what it rules out —
# see `test_a_numbered_position_is_legal_because_its_row_exists_rather_than_by
# _range`, where 7 being legal and 6 not is what no range rule of any shape can
# reproduce.
#
# `U` is here so the summer map is not digits-only, and because a 12-week letter
# in a 12-week term is E0-06 criterion 5's own boundary: it ends on the term's
# last day.
SUMMER_2026_START = date(2026, 5, 11)
SUMMER_2026_WEEKS = 12
SUMMER_2026_END = date(2026, 8, 2)
THREE_WEEK_LENGTH = 3

SUMMER_2026_SEED_MAP: tuple[tuple[str, int, int], ...] = (
    ("U", 12, 0),
    ("2", THREE_WEEK_LENGTH, 0),
    ("3", THREE_WEEK_LENGTH, 3),
    ("5", THREE_WEEK_LENGTH, 6),
    ("7", THREE_WEEK_LENGTH, 9),
)
SUMMER_STARTS = tuple(entry[0] for entry in SUMMER_2026_SEED_MAP)

# The numbered position the fall map holds and the summer map does not, and the
# higher one the summer map does hold. The pair is the whole subject of the two
# tests that use them: 6 is legal in one term and not in the other, and 7 is
# legal in the term where 6 is not.
LEGAL_IN_FALL_ONLY = "6"
LEGAL_IN_SUMMER_ABOVE_IT = "7"
LEGAL_IN_BOTH = "2"

ONLINE_SUFFIX = "WW"
FACE_TO_FACE_SUFFIX = "FF"

# A calendar that is internally consistent, legal in the Fall 2026 term, and the
# answer to no start position in its map — 6 weeks from 8/24, when every position
# in the seed map starts 0, 3, 4, 6, 8, 9, 12 or 15 weeks in. It is what a
# section's derived columns are seeded with before the service writes them, so
# that "the columns hold the derived values afterwards" cannot be true of a row
# that held them all along (`docs/MISTAKES.md` entry 3). Consistent on purpose:
# a placeholder whose end date disagreed with its own length and start could be
# refused by a check constraint E0-07 is free to add, and the test would die in
# its own seeding.
PLACEHOLDER_LENGTH_WEEKS = 6
PLACEHOLDER_START = FALL_2026_START + timedelta(weeks=1)

# ---------------------------------------------------------------------------
# Column names.
# ---------------------------------------------------------------------------

# Spelled by E0-06: "**The letter column is named `letter`.**", and by its
# criterion 3, "the database enforces uniqueness over `(term_id, number)`".
LETTER_COLUMN = "letter"
WEEK_NUMBER_COLUMN = "number"

# **Candidates, not names.** E0-06 gives `term` and `start_letter_map` a "length
# in weeks" and the map row a start date without spelling any of the three
# columns; `tests/integration/test_term_calendar_schema.py` carries the same
# constant for the same reason, and E0-05's `number` → `lms_number` correction is
# why they are constants rather than literals.
TERM_LENGTH_COLUMNS = ("length_weeks", "length")
TERM_START_COLUMNS = ("start_date", "starts_on", "start")
TERM_END_COLUMNS = ("end_date", "ends_on", "end")
LETTER_LENGTH_COLUMNS = ("length_weeks", "length")
LETTER_START_COLUMNS = ("start_date", "starts_on", "start")

# Spelled by E0-07's scope — "Derive `length_weeks`, `start_date`, `end_date`,
# and `modality`" — and by SPEC §8, which gives `section` a `length_weeks` and
# start/end dates. Used both for the columns on `section` and for the parts of
# whatever the derivation returns.
DERIVED_LENGTH = "length_weeks"
DERIVED_START = "start_date"
DERIVED_END = "end_date"
DERIVED_MODALITY = "modality"
SECTION_DERIVED_COLUMNS = (DERIVED_LENGTH, DERIVED_START, DERIVED_END, DERIVED_MODALITY)

# Not this file's choice: E0-05 created `section.lms_section_code` and
# `course.lms_number` under those names, and E0-05's own criterion is that
# LMS-owned columns carry the prefix.
SECTION_CODE_COLUMN = "lms_section_code"
COURSE_NUMBER_COLUMN = "lms_number"

# **This file's choice**, matching the unit module's: criterion 3 wants an error
# "naming the offending part", and a message is prose.
START_LETTER_WORDS = ("start letter", "start position", "letter")

# ---------------------------------------------------------------------------
# Values the seeding helper invents.
# ---------------------------------------------------------------------------

# SPEC §3.1's default window — opens Friday 18:00, closes Sunday 23:59:59 in
# America/New_York — expressed in UTC, for any timestamp column the walker meets
# on the way to a term or a week row.
WINDOW_OPENS_AT = datetime(2026, 8, 21, 22, 0, tzinfo=UTC)
WINDOW_CLOSES_AT = datetime(2026, 8, 24, 3, 59, 59, tzinfo=UTC)

STRING_HINTS = (
    ("timezone", "America/New_York"),
    ("email", "nobody@example.invalid"),
    ("url", "https://example.invalid"),
    ("uri", "https://example.invalid"),
)
LENGTH_FRAGMENTS = ("length", "weeks", "duration")

_UNIQUE = count(1)


# ---------------------------------------------------------------------------
# Reaching the schema.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def declared_tables(migrated_database: Any) -> dict[str, Table]:
    """`Base.metadata`, with every model module registered on it.

    Reached through `app.models` rather than through a model module, because
    `migrations/env.py` imports the package and a module nobody imported is on no
    metadata — `tests/unit/test_term_models_registered.py` is where that is
    diagnosed. `Base` comes from `app.models.base` and never from `app.db`, which
    builds an engine out of `Settings()` at import.

    `migrated_database` is depended on and not used: it is what guarantees the
    migration has run before anything inserts through these tables.
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
            "through."
        )
    return dict(metadata.tables)


@pytest.fixture(scope="session")
def reflected_tables(migrated_engine: Any) -> dict[str, Table]:
    """Every table the migrated database holds, reflected once.

    Reflected and not imported, for the section-column test: a column on
    `Base.metadata` that no migration created exists nowhere a deployment can
    reach, which is the silence the epic README's first settled rule is about.
    """
    metadata = MetaData()
    metadata.reflect(bind=migrated_engine)
    return dict(metadata.tables)


def require_table(tables: dict[str, Table], name: str) -> Table:
    """The table called `name`, or a failure saying it is not there."""
    table = tables.get(name)
    if table is None:
        pytest.fail(
            f"There is no `{name}` table (what is there: {sorted(tables)}). E0-05 creates "
            "`section` and E0-06 creates `term` and `start_letter_map`; E0-07 depends on both."
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
        f"gives `{table.name}` this value without spelling the column, so the candidates are a "
        "constant at the top of this file and a deliberate rename is a one-line change here."
    )


def single_primary_key(table: Table) -> str:
    """The name of `table`'s one primary key column (ADR 0016 makes it one uuid)."""
    columns = list(table.primary_key.columns)
    if len(columns) != 1:
        pytest.fail(
            f"`{table.name}` has {len(columns)} primary key columns "
            f"({[column.name for column in columns]}). ADR 0016 makes every primary key one "
            "server-generated uuid, and this module addresses rows by it."
        )
    return columns[0].name


def model_for(table_name: str) -> Any:
    """The mapped class behind one table, found through the registry.

    Found and not named: no ticket spells an ORM class name for `term`, and
    importing one by a guessed name would be this file deciding it. The service
    is most likely written against the models rather than against Core tables, so
    the tests have to be able to hand it a real instance.
    """
    base_module = import_module("app.models.base")
    base = getattr(base_module, "Base", None)
    registry = getattr(base, "registry", None)
    if registry is None:
        pytest.fail("`app.models.base.Base` exposes no `registry`, so no mapped class is findable.")

    found = [
        mapper.class_
        for mapper in registry.mappers
        if getattr(mapper.local_table, "name", None) == table_name
    ]
    if len(found) != 1:
        pytest.fail(
            f"{len(found)} mapped classes stand behind the `{table_name}` table ({found}). This "
            "module needs exactly one so it can hand the derivation a real instance of the "
            "section's term."
        )
    return found[0]


# ---------------------------------------------------------------------------
# Seeding. See the module docstring for why this walker is here.
# ---------------------------------------------------------------------------


def letters(limit: int | None) -> str:
    """A short, unique, upper-case string that fits a column of length `limit`."""
    width = max(min(6, limit or 6), 1)
    value = next(_UNIQUE)
    out = []
    for _ in range(width):
        value, remainder = divmod(value, 26)
        out.append(string.ascii_uppercase[remainder])
    return "".join(reversed(out))


def invented_section_code() -> str:
    """A well-formed section code per §2.2, unique within this session."""
    return f"{letters(1)}3{ONLINE_SUFFIX}"


# The band a generated course number is drawn from: three digits, `100`-`799`,
# which SPEC §8 splits into UG, UGGR and GR. Staying inside a band matters more
# than which band, because the bands are not enforced by a `CHECK`: `course.level`
# is a stored generated column (ADR 0015) and an out-of-band number derives
# `NULL::course_level`, so the row is refused by that column's `NOT NULL` and the
# error names the level rather than the number. `000`-`099` is left out only
# because it needs zero padding to stay three digits, which is a case E0-05's own
# tests own rather than this walker's.
COURSE_NUMBER_FIRST = 100
COURSE_NUMBER_LAST = 799

# Cleared before every test, so the numbers only have to be distinct within one:
# `db_session` rolls every write back at the end of a test, so no course this
# module seeds outlives the test that asked for it. The same mechanism and the
# same reasoning as `_GRAPH_INTEGER_COUNTERS` in `tests/conftest.py`.
_COURSE_NUMBERS: dict[str, Any] = {}


@pytest.fixture(autouse=True)
def _course_numbers_start_again_for_each_test() -> None:
    """Hand the first number in the band to every test, rather than the whole session one each.

    Without it the generator is a session-wide supply of 700 numbers, and this
    module's property tests run twenty-five and forty examples inside one test —
    so a session-wide supply is the shape that runs out. Failing loudly, but
    inside its own seeding and for a reason that has nothing to do with what the
    property asserts, which is exactly what this generator replaced.
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
    importing `tests/conftest.py` as a module rather than letting pytest load it
    as a plugin loads it twice.
    """
    counter = _COURSE_NUMBERS.setdefault(COURSE_NUMBER_COLUMN, count(COURSE_NUMBER_FIRST))
    number = next(counter)
    if number > COURSE_NUMBER_LAST:
        available = COURSE_NUMBER_LAST - COURSE_NUMBER_FIRST + 1
        pytest.fail(
            f"This test asked for more than {available} courses, so the seeding walker has run "
            "out of three-digit numbers inside SPEC §8's bands. It stops here rather than "
            f"starting again at {COURSE_NUMBER_FIRST}: reusing a number would write a second "
            "course with the same number under the same prefix, which E0-05's "
            "`uq_course_prefix_id_lms_number` refuses — and that failure would be a unique "
            "violation raised inside a fixture rather than a message naming its cause, which is "
            "the shape this generator exists to leave behind. If a test genuinely needs this "
            "many courses, widen the band above: `000`-`099` is available with zero padding."
        )
    return str(number)


# Values keyed to a column that a type alone cannot answer for. Both are schema
# rules E0-05 already enforces, so a value the walker invented freely would be
# refused by a constraint that has nothing to do with E0-07: SPEC §8's
# course-number bands, and §2.2's section-code shape. The same two entries, for
# the same reason, as in `tests/integration/test_term_calendar_schema.py`. Both
# are drawn fresh per call, because both rules have a uniqueness half as well as
# a shape half.
COLUMN_VALUES: dict[tuple[str, str], Callable[[], Any]] = {
    ("course", COURSE_NUMBER_COLUMN): course_number,
    ("section", SECTION_CODE_COLUMN): invented_section_code,
}


def stored_type(column: Any) -> Any:
    """The type a column actually stores, with any `TypeDecorator` resolved away.

    E0-06's timezone guard has to live on the column type, so `term`'s and
    `start_letter_map`'s columns can be declared as decorators. A helper that
    dispatched `isinstance` against the declared class would match none of them
    and fail inside its own fixture — `docs/disputes/E0-06-01.md`, and
    `docs/MISTAKES.md` entry 13, which is why this resolution is in the one place
    that asks the question rather than at each call site.
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
        # Timezone-aware, always: E0-06 criterion 4 has every timestamp column
        # refuse a naive value, so a helper that invented one would fail inside
        # its own seeding against the guard that ticket exists to add. The
        # open/close hint keeps a pair of columns in the order an ordering check
        # would want them, taken from SPEC §3.1's Friday 18:00 to Sunday
        # 23:59:59 window expressed in UTC.
        return WINDOW_CLOSES_AT if "clos" in column.name.lower() else WINDOW_OPENS_AT
    elif isinstance(kind, Date):
        return FALL_2026_START
    elif isinstance(kind, Integer):
        lowered = column.name.lower()
        if any(fragment in lowered for fragment in LENGTH_FRAGMENTS):
            return FALL_2026_WEEKS
        return 1
    elif isinstance(kind, Numeric):
        return Decimal("1")
    elif isinstance(kind, String):
        limit = getattr(kind, "length", None)
        for fragment, hint in STRING_HINTS:
            if fragment in column.name.lower() and (limit is None or len(hint) <= limit):
                return hint
        return letters(limit)

    pytest.fail(
        f"The seeding helper in this module cannot invent a value for `{table.name}."
        f"{column.name}`, which is NOT NULL, has no default, and is of type {column.type!r}. "
        "That is this test file needing a case added, not a defect in the schema."
    )


def seed_row(
    session: Any,
    tables: dict[str, Table],
    name: str,
    chain: dict[str, Any] | None = None,
    **overrides: Any,
) -> Any:
    """Insert one row into `name`, building whatever ancestors it requires.

    `chain` is the set of ancestor rows built so far, keyed by table name, so a
    letter map row and the term it belongs to are the same term.

    Columns are filled only where the schema requires it — anything generated,
    defaulted or nullable is left to the database, since every primary key is a
    server-defaulted uuid (ADR 0016) and has to be read back with RETURNING.

    A foreign key column takes its value from the referenced column of the row
    already in the chain, rather than from the ancestor's primary key: ADR 0018
    has `week` and the letter map carry a copy of their term's length through a
    *composite* key, and a helper that only knew about primary keys would leave
    that copy to `invented_value` and write a row that lies about its term.
    """
    chain = {} if chain is None else chain
    table = require_table(tables, name)
    values: dict[str, Any] = dict(overrides)

    for column in table.columns:
        if column.name in values:
            continue
        if column.computed is not None or column.identity is not None:
            continue
        if column.server_default is not None or column.default is not None:
            continue
        if column.foreign_keys and not column.nullable:
            ordered = sorted(column.foreign_keys, key=lambda key: str(key.target_fullname))
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


def seed_term(
    session: Any,
    tables: dict[str, Table],
    chain: dict[str, Any],
    *,
    weeks: int = FALL_2026_WEEKS,
    start: date = FALL_2026_START,
) -> Any:
    """A term of exactly `weeks` weeks, with dates that say the same thing.

    The end date is `start + weeks x 7 - 1`, the same reading
    `tests/integration/test_term_calendar_schema.py` seeds with. E0-06 permits a
    check constraint holding the length and the dates consistent, so a helper
    that set the length and left the dates to `invented_value` could be refused
    by a rule this ticket is not about.
    """
    term = require_table(tables, "term")
    values: dict[str, Any] = {
        require_column(term, TERM_LENGTH_COLUMNS): weeks,
        require_column(term, TERM_START_COLUMNS): start,
        require_column(term, TERM_END_COLUMNS): start + timedelta(days=weeks * 7 - 1),
    }
    return seed_row(session, tables, "term", chain, **values)


def seed_letter(
    session: Any,
    tables: dict[str, Table],
    chain: dict[str, Any],
    *,
    letter: str,
    length_weeks: int,
    start: date,
) -> Any:
    """One row of a term's start-letter map."""
    letter_map = require_table(tables, "start_letter_map")
    values = {
        LETTER_COLUMN: letter,
        require_column(letter_map, LETTER_LENGTH_COLUMNS): length_weeks,
        require_column(letter_map, LETTER_START_COLUMNS): start,
    }
    return seed_row(session, tables, "start_letter_map", chain, **values)


def seed_fall_2026(session: Any, tables: dict[str, Table], chain: dict[str, Any]) -> Any:
    """The Fall 2026 term with every start position §2.2's seed map names."""
    term = seed_term(session, tables, chain)
    for letter, length_weeks, offset in FALL_2026_SEED_MAP:
        seed_letter(
            session,
            tables,
            chain,
            letter=letter,
            length_weeks=length_weeks,
            start=FALL_2026_START + timedelta(weeks=offset),
        )
    return term


def seed_summer_2026(session: Any, tables: dict[str, Table], chain: dict[str, Any]) -> Any:
    """A 12-week summer term whose map holds a different set of numbered positions.

    The counterpart to `seed_fall_2026`, and the only other term shape §2.2
    describes: "fall and spring terms are 18 calendar weeks including break;
    summer is 12". What it holds is this suite's choice — see
    `SUMMER_2026_SEED_MAP`.
    """
    term = seed_term(session, tables, chain, weeks=SUMMER_2026_WEEKS, start=SUMMER_2026_START)
    for letter, length_weeks, offset in SUMMER_2026_SEED_MAP:
        seed_letter(
            session,
            tables,
            chain,
            letter=letter,
            length_weeks=length_weeks,
            start=SUMMER_2026_START + timedelta(weeks=offset),
        )
    return term


# ---------------------------------------------------------------------------
# Calling the service.
# ---------------------------------------------------------------------------


def expected_end(start: date, length_weeks: int) -> date:
    """The last day of a section that starts on `start` and runs `length_weeks`.

    The module docstring argues the inclusive reading from §2.2's own seed
    values. `END_DATE_IS_INCLUSIVE` is the one line that changes.
    """
    return start + timedelta(days=length_weeks * 7 - (1 if END_DATE_IS_INCLUSIVE else 0))


def code_for(start_position: str, ordinal: int = 1, suffix: str = ONLINE_SUFFIX) -> str:
    """A section code for one start position, per §2.2's `{start}{ordinal}{modality}`."""
    return f"{start_position}{ordinal}{suffix}"


def derive(
    section_codes: Any, session: Any, tables: dict[str, Table], term_row: Any, code: str
) -> Any:
    """Derive one section's calendar from its code and its term.

    Every value the ticket's sentence mentions is offered — "from the code and
    the section's term, reading `start_letter_map`" — in each shape the service
    could reasonably want it: the session, the code, the term as a mapped
    instance, and the term's key. `SectionCodeService.call` fills the parameters
    the signature actually has and fails naming any it cannot, because E0-07
    spells no signature and a helper that guessed one would make the choice for
    the implementer.
    """
    term_table = require_table(tables, "term")
    key = single_primary_key(term_table)
    instance = session.get(model_for("term"), term_row[key])
    if instance is None:
        pytest.fail(
            "The seeded term could not be loaded through its mapped class, so there is no term "
            "instance to hand the derivation. The row was inserted through `Base.metadata` on "
            "this session's connection, so a miss here means the mapped class and the table have "
            "come apart."
        )
    return section_codes.call(
        section_codes.derive,
        session=session,
        code=code,
        term=instance,
        term_id=term_row[key],
    )


def derived_parts(section_codes: Any, derived: Any) -> tuple[int, date, date]:
    """The length, start date and end date out of whatever the derivation returned."""
    return (
        int(section_codes.part(derived, (DERIVED_LENGTH,), "derived length in weeks")),
        section_codes.part(derived, (DERIVED_START,), "derived start date"),
        section_codes.part(derived, (DERIVED_END,), "derived end date"),
    )


def modality_text(value: Any) -> str:
    """A modality as comparable text, whether it is an enum member or a string.

    Both sides of every modality comparison go through this, so the assertion is
    about the two agreeing rather than about which representation E0-07 chose —
    a question the ticket does not answer. An enum member and its own value
    normalise to the same text, which is what makes "what the column holds" and
    "what the derivation returned" comparable without either being named.
    """
    return str(getattr(value, "value", value)).lower()


def instance_of(session: Any, tables: dict[str, Table], name: str, row: Any) -> Any:
    """The mapped instance behind one seeded row, loaded by its primary key."""
    table = require_table(tables, name)
    key = single_primary_key(table)
    instance = session.get(model_for(name), row[key])
    if instance is None:
        pytest.fail(
            f"The seeded `{name}` row could not be loaded through its mapped class. It was "
            "inserted through `Base.metadata` on this session's connection, so a miss here means "
            "the mapped class and the table have come apart."
        )
    return instance


def seed_placeholder_section(
    session: Any,
    tables: dict[str, Table],
    chain: dict[str, Any],
    *,
    code: str,
    modality: Any,
) -> Any:
    """A section carrying `code` and a calendar that is not the one it implies.

    The four derived columns are set to `PLACEHOLDER_*` — a legal, internally
    consistent calendar that no start position in the seeded map derives — so
    that finding the derived values there afterwards means something was written
    (`docs/MISTAKES.md` entry 3). The modality comes from the caller, which takes
    it from the service's own derivation of the *other* suffix: whatever the
    service returns for a modality is by construction something this column can
    hold, which nothing this file could invent would be.
    """
    return seed_row(
        session,
        tables,
        "section",
        chain,
        **{
            SECTION_CODE_COLUMN: code,
            DERIVED_LENGTH: PLACEHOLDER_LENGTH_WEEKS,
            DERIVED_START: PLACEHOLDER_START,
            DERIVED_END: expected_end(PLACEHOLDER_START, PLACEHOLDER_LENGTH_WEEKS),
            DERIVED_MODALITY: modality,
        },
    )


def apply_code_to_section(
    section_codes: Any,
    session: Any,
    tables: dict[str, Table],
    term_row: Any,
    section: Any,
    code: str,
) -> Any:
    """Run the service's writer against one seeded section.

    Offers the same roles `derive` does plus the section itself, and lets
    `SectionCodeService.call` fill whatever the signature asks for. E0-07 spells
    no signature for this either.
    """
    term_key = single_primary_key(require_table(tables, "term"))
    return section_codes.call(
        section_codes.writer,
        session=session,
        code=code,
        term=instance_of(session, tables, "term", term_row),
        term_id=term_row[term_key],
        section=instance_of(session, tables, "section", section),
    )


def stored_section(session: Any, tables: dict[str, Table], section: Any) -> Any:
    """One section as the database holds it now, read back through Core.

    Through Core and after a flush, so that both shapes a writer could take are
    covered: one that mutates the mapped instance and leaves the unit of work to
    persist it, and one that issues an UPDATE itself. Reading an attribute off
    the instance instead would report the first as a success while nothing had
    reached the database, which is the difference E0-20's subject is about.
    """
    table = require_table(tables, "section")
    key = single_primary_key(table)
    session.flush()
    return session.execute(select(table).where(table.c[key] == section[key])).mappings().one()


def refusal(
    section_codes: Any,
    session: Any,
    tables: dict[str, Table],
    term_row: Any,
    code: str,
    *,
    because: str = "",
) -> BaseException:
    """The exception deriving `code` raised, or a failure saying it raised none.

    `Exception` and not `BaseException`, so that a `pytest.fail` from inside the
    discovery helpers — "there is no such module", "there are two candidate
    derivations" — stays a failure instead of being read as the refusal the test
    was looking for (`docs/MISTAKES.md` entry 3).

    `because` is appended to the message on the path where the code derives
    instead of being refused. That path is the interesting one for some callers
    and not for others: a caller asking about an unknown letter is describing an
    ordinary missing row, while a caller asking about a position that is legal in
    a *different* term is describing a specific wrong implementation, and the
    failure should name it rather than leave the reader to open the file.
    """
    try:
        derived = derive(section_codes, session, tables, term_row, code)
    except Exception as raised:
        return raised
    message = (
        f"Deriving {code!r} returned {derived!r} instead of raising. E0-07 rejects a code the "
        "term's map cannot resolve, and a section that derives anyway carries a calendar nobody "
        "configured."
    )
    pytest.fail(f"{message} {because}" if because else message)


# ---------------------------------------------------------------------------
# Criterion 1 — every letter in the Fall 2026 seed map.
# ---------------------------------------------------------------------------


def test_the_seed_map_offsets_reproduce_the_three_start_dates_the_spec_documents() -> None:
    """The fixture is checked against §2.2 before anything is asserted against it.

    §2.2 documents three start dates — "12-week U/R/Q starting 8/17, 9/7, 9/28" —
    and every other row of `FALL_2026_SEED_MAP` carries an offset this file
    chose. If the three the spec does name did not come out of the offsets, the
    whole fixture would be a calendar of this file's invention and every
    assertion below would be about it rather than about §2.2. It costs one test
    to know that it is not.

    The only test here that needs no database. It is in this module and not in
    the unit suite because it is this module's fixture that it checks.
    """
    seeded = {
        letter: FALL_2026_START + timedelta(weeks=offset)
        for letter, _, offset in FALL_2026_SEED_MAP
        if letter in DOCUMENTED_START_DATES
    }

    assert seeded == DOCUMENTED_START_DATES, (
        f"The seed map in this file puts U, R and Q at {seeded}, and SPEC §2.2 documents "
        f"{DOCUMENTED_START_DATES}. Fix the offsets: the three 12-week letters are the only "
        "rows whose dates the spec gives, and they are what ties the rest of this fixture to a "
        "real calendar."
    )
    assert FALL_2026_START.weekday() == MONDAY, (
        f"{FALL_2026_START} is not a Monday, so the weekday assertions below are about a "
        "calendar §2.2 does not describe."
    )
    assert FALL_2026_START + timedelta(days=FALL_2026_WEEKS * 7 - 1) == FALL_2026_END, (
        "The term's end date and its length disagree, so a section that ends on the term's last "
        "day is not the boundary case this module treats it as."
    )


def test_the_summer_seed_map_is_a_calendar_that_term_could_hold() -> None:
    """The summer fixture is checked for consistency before anything rests on it.

    Unlike the fall map above there is nothing in §2.2 to check these numbers
    against — the spec gives summer 12 weeks and seeds no map — so what can be
    checked is that they are a calendar rather than a set of numbers: a Monday
    start like every other term in this module, an end date that agrees with the
    length, and every row fitting inside the term.

    That last one matters more than it looks. A row that ran past the term's end
    would have to be *rejected* under criterion 5, so a summer map with an
    overrunning row would fail the tests below for a reason none of them is
    about, and the failure would read as a defect in the derivation.
    """
    assert SUMMER_2026_START.weekday() == MONDAY, (
        f"{SUMMER_2026_START} is not a Monday, so the summer term does not follow the convention "
        "every other term in this module and §2.2's own seed dates use."
    )
    assert SUMMER_2026_START + timedelta(days=SUMMER_2026_WEEKS * 7 - 1) == SUMMER_2026_END, (
        "The summer term's end date and its length disagree, so a row that fits the length may "
        "still run past the end date."
    )
    assert SUMMER_2026_END < FALL_2026_START, (
        f"The summer term ends {SUMMER_2026_END}, on or after the fall term's start "
        f"{FALL_2026_START}. The two share an institution in the test below, and overlapping "
        "terms would put a question into that contrast which it is not there to answer."
    )

    overrunning = {
        letter: expected_end(SUMMER_2026_START + timedelta(weeks=offset), length_weeks)
        for letter, length_weeks, offset in SUMMER_2026_SEED_MAP
        if expected_end(SUMMER_2026_START + timedelta(weeks=offset), length_weeks) > SUMMER_2026_END
    }
    assert not overrunning, (
        f"These rows of the summer map end after the term does ({SUMMER_2026_END}): "
        f"{overrunning}. Criterion 5 requires the service to reject them, so the tests below "
        "would fail on a fixture rather than on a derivation."
    )
    assert len(set(SUMMER_STARTS)) == len(SUMMER_STARTS), (
        f"The summer map repeats a start position: {list(SUMMER_STARTS)}. E0-06 makes a letter "
        "unique within a term, so the seeding would be refused by the database."
    )


def test_every_start_position_in_the_seed_map_derives_the_length_its_map_row_holds(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """Criterion 1: every letter parses to the documented length.

    §2.2 documents a length for all twenty start positions — 12-week U/R/Q,
    6-week E/F/H, 8-week X/Y/Z, 10-week S/T, 15-week V/D, 16-week K, and the
    3-week sections it numbers 2 through 7 — and those are the lengths the
    fixture seeds, so an implementation that disagrees with the map disagrees
    with §2.2 in the same breath.

    Every position is asserted in one test rather than twenty because they are
    one behaviour, and the failure names the positions that were wrong.
    """
    chain: dict[str, Any] = {}
    term = seed_fall_2026(db_session, declared_tables, chain)

    wrong: dict[str, Any] = {}
    for start_position, length_weeks, _ in FALL_2026_SEED_MAP:
        derived = derive(section_codes, db_session, declared_tables, term, code_for(start_position))
        found = int(section_codes.part(derived, (DERIVED_LENGTH,), "derived length in weeks"))
        if found != length_weeks:
            wrong[start_position] = (found, length_weeks)

    assert not wrong, (
        f"These start positions derived the wrong length (found, expected): {wrong}. Criterion "
        "1: every letter in the Fall 2026 seed map parses to the documented length. A length is "
        "not decoration — SPEC §5.1 will only compare a section against others of the same "
        "length and level, so a section 6 weeks long that thinks it is 12 is benchmarked against "
        "a population it is not in."
    )


def test_every_start_position_in_the_seed_map_derives_the_start_date_its_map_row_holds(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """Criterion 1: every letter parses to the documented start date.

    Its own test rather than folded into the length above, because the two fail
    for different reasons and a length read correctly off a row whose date was
    read off another row is a defect worth its own failure message.
    """
    chain: dict[str, Any] = {}
    term = seed_fall_2026(db_session, declared_tables, chain)

    wrong: dict[str, Any] = {}
    for start_position, _, offset in FALL_2026_SEED_MAP:
        expected = FALL_2026_START + timedelta(weeks=offset)
        derived = derive(section_codes, db_session, declared_tables, term, code_for(start_position))
        found = section_codes.part(derived, (DERIVED_START,), "derived start date")
        if found != expected:
            wrong[start_position] = (found, expected)

    assert not wrong, (
        f"These start positions derived the wrong start date (found, expected): {wrong}. "
        "Criterion 1, and §2.2's whole point: the start letter encodes a start date via the "
        "term's map. Every week axis on every report is counted from this date, so a section "
        "reading another cohort's row is off by three weeks in every chart and in the grade "
        "passback denominator (§3.4)."
    )


def test_the_derived_length_follows_the_terms_map_rather_than_a_table_in_the_code(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """§2.2: the start-letter map is per-term admin configuration, not a constant.

    A module-level `{"E": 6, "F": 6, ...}` passes both criterion 1 tests above
    perfectly, because those seed the map §2.2 describes and then check the
    derivation against it. This is the case that separates them: a term whose map
    says `E` is 8 weeks. §2.2 names E as a 6-week letter in Fall 2026, and the
    only reason that is true is that Fall 2026's map row says so — E0-06 stores
    the map per term precisely so that a later term can say something else, and
    E11 gives an admin the screen to change it.

    The term is a second, separate one, so the Fall 2026 map is not edited out
    from under the tests above.
    """
    unusual_length = 8
    documented = {letter: length for letter, length, _ in FALL_2026_SEED_MAP}
    assert documented["E"] != unusual_length, (
        "This test rewrites `E` to a length §2.2 does not give it, and the two lengths have "
        "become the same, so it now proves nothing."
    )

    chain: dict[str, Any] = {}
    term = seed_term(db_session, declared_tables, chain)
    seed_letter(
        db_session,
        declared_tables,
        chain,
        letter="E",
        length_weeks=unusual_length,
        start=FALL_2026_START,
    )

    derived = derive(section_codes, db_session, declared_tables, term, code_for("E"))
    length = int(section_codes.part(derived, (DERIVED_LENGTH,), "derived length in weeks"))

    assert length == unusual_length, (
        f"A term whose map row says `E` runs {unusual_length} weeks derived {length} instead. "
        "The letter map is per-term configuration (§2.2, §6.3, E0-06), so the derivation has to "
        "read the row rather than a table in the module. A hardcoded map passes every test that "
        "seeds §2.2's own values and fails the first time an institution edits its calendar — "
        "silently, with sections whose dates disagree with the configuration on the screen."
    )


def test_a_start_letter_resolves_within_its_own_term_and_not_a_neighbouring_one(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """§2.2: the letter encodes a start date *within the term*.

    Two terms in one institution both map `R`, as every real deployment does —
    Fall 2026's `R` and the next term's `R` are different dates. The other term's
    row is seeded **first**, so a lookup that filters on the letter alone and
    takes what it finds gets the wrong one rather than getting lucky; if the
    implementation raises on the ambiguity instead, that also fails here, which
    is right, because the query has no business being ambiguous.

    This is the near miss the module exists for: nothing about the derived date
    looks wrong. It is a Monday, it is inside a term, and it is three weeks from
    where the section actually starts.
    """
    other: dict[str, Any] = {}
    other_start = FALL_2026_START + timedelta(weeks=FALL_2026_WEEKS)
    other_term = seed_term(db_session, declared_tables, other, start=other_start)
    seed_letter(
        db_session,
        declared_tables,
        other,
        letter="R",
        length_weeks=12,
        start=other_start + timedelta(weeks=1),
    )

    chain = {name: row for name, row in other.items() if name == "institution"}
    term = seed_term(db_session, declared_tables, chain)
    seed_letter(
        db_session,
        declared_tables,
        chain,
        letter="R",
        length_weeks=12,
        start=DOCUMENTED_START_DATES["R"],
    )
    assert chain["term"] != other_term, (
        "Seeding a second term reused the first one, so both letters are in one map and there is "
        "no neighbouring term for the assertion below to be about."
    )

    derived = derive(section_codes, db_session, declared_tables, term, code_for("R"))
    start = section_codes.part(derived, (DERIVED_START,), "derived start date")

    assert start == DOCUMENTED_START_DATES["R"], (
        f"`R1WW` in Fall 2026 derived a start date of {start}, and §2.2 documents "
        f"{DOCUMENTED_START_DATES['R']}. The other term in this test maps `R` to "
        f"{other_start + timedelta(weeks=1)}. A lookup keyed on the letter without its term "
        "finds whichever row it finds — and the answer is a plausible Monday inside a term, so "
        "nothing downstream ever questions it."
    )


# ---------------------------------------------------------------------------
# Criterion 4 — the end date.
# ---------------------------------------------------------------------------


def test_the_end_date_is_the_start_date_plus_the_length_for_every_position_in_the_map(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """Criterion 4: `end_date` equals `start_date` plus `length_weeks`, for every letter.

    Asserted across all twenty start positions rather than one, because the
    failures worth catching are length-dependent: an implementation that adds a
    month per four weeks is right for 8 and wrong for 6, and one that derives the
    end from the *term's* end is right for `Q` alone.

    The inclusive reading is argued in the module docstring from §2.2's own seed
    values. An implementation that lands one day the other side of it fails here
    with the two dates printed, which is the failure to read before changing
    anything: this is the one convention in the file that the spec does not
    state outright.
    """
    chain: dict[str, Any] = {}
    term = seed_fall_2026(db_session, declared_tables, chain)

    wrong: dict[str, Any] = {}
    for start_position, length_weeks, offset in FALL_2026_SEED_MAP:
        start = FALL_2026_START + timedelta(weeks=offset)
        derived = derive(section_codes, db_session, declared_tables, term, code_for(start_position))
        found = section_codes.part(derived, (DERIVED_END,), "derived end date")
        if found != expected_end(start, length_weeks):
            wrong[start_position] = (found, expected_end(start, length_weeks))

    assert not wrong, (
        f"These start positions derived the wrong end date (found, expected): {wrong}. Criterion "
        "4. This file reads 'start date plus length_weeks' inclusively — the last day of the "
        "last week — because §2.2's own map has 12-week `Q` starting 9/28 in a term that ends "
        "12/20, which fits exactly under that reading and overruns the term by one day under the "
        "other. If the ticket means the exclusive reading, `END_DATE_IS_INCLUSIVE` at the top of "
        "this file is the one line that changes, and criterion 5 then rejects a letter §2.2 "
        "seeds."
    )


def test_the_end_date_lands_on_the_weekday_before_the_start_weekday(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """Criterion 4: "landing on the correct weekday", for every letter in the map.

    Every start date in §2.2's Fall 2026 map is a Monday, and under the reading
    argued above every section therefore ends on a Sunday — which is exactly when
    §3.1 closes the week's survey window, so a section's last window closes on
    its last day.

    Separate from the arithmetic above because it fails differently and reads
    differently. An implementation that adds calendar months, or that snaps the
    end to the term's end, produces an end date on some arbitrary weekday, and
    "Thursday" in this failure message says what went wrong faster than two dates
    seven days apart do.
    """
    chain: dict[str, Any] = {}
    term = seed_fall_2026(db_session, declared_tables, chain)
    expected_weekday = SUNDAY if END_DATE_IS_INCLUSIVE else MONDAY

    wrong: dict[str, Any] = {}
    for start_position, _, _ in FALL_2026_SEED_MAP:
        derived = derive(section_codes, db_session, declared_tables, term, code_for(start_position))
        found = section_codes.part(derived, (DERIVED_END,), "derived end date")
        if found.weekday() != expected_weekday:
            wrong[start_position] = found

    assert not wrong, (
        f"These start positions ended on the wrong weekday: {wrong}. Every start date in §2.2's "
        "Fall 2026 map is a Monday, so every section ends on the Sunday that closes its last "
        "survey window (§3.1: the window closes Sunday 23:59:59). A section ending mid-week has "
        "a final week no window covers, or a window that closes after the section is over."
    )


def test_the_last_twelve_week_cohort_ends_on_the_last_day_of_its_term(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """The boundary §2.2's own seed map sits exactly on.

    `Q` is a 12-week letter starting 9/28 in a term that runs 18 weeks from 8/17,
    which ends 12/20. Twelve weeks from 9/28 ends 12/20 — the same day. There is
    no slack in that at all, and that is what makes it worth its own test: it is
    simultaneously the strongest case for the inclusive reading of criterion 4
    and the control for criterion 5's rejection below. A derivation that is one
    day long puts a letter the spec itself seeds outside its own term, and E0-17
    seeds a demo institution from these very values.
    """
    chain: dict[str, Any] = {}
    term = seed_fall_2026(db_session, declared_tables, chain)

    derived = derive(section_codes, db_session, declared_tables, term, code_for("Q"))
    _, start, end = derived_parts(section_codes, derived)

    assert (
        start == DOCUMENTED_START_DATES["Q"]
    ), f"`Q1WW` derived a start of {start}; §2.2 documents {DOCUMENTED_START_DATES['Q']}."
    assert end == FALL_2026_END, (
        f"`Q1WW` — 12 weeks from {DOCUMENTED_START_DATES['Q']} — derived an end date of {end}, "
        f"and the term's last day is {FALL_2026_END}. The two are the same date under the "
        "reading this file takes, and one day apart under the other. A section that ends the day "
        "after its term has an end date criterion 5 requires the service to reject, which would "
        "make `Q` — a letter SPEC §2.2 seeds by name — unusable in the term it is seeded for."
    )


# ---------------------------------------------------------------------------
# Criterion 5 — a section that runs past its term is rejected.
# ---------------------------------------------------------------------------


def test_a_code_whose_section_would_end_after_the_term_is_rejected(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """Criterion 5: a derived end date outside the term's dates is rejected.

    **The control and the refusal differ by one week of start date, and by
    nothing else.** `Q` starts 9/28 and ends exactly on the term's last day;
    `G` here is the same 12-week length one week later, so it ends 12/27, seven
    days past the end of the term. Same term, same length, same modality — the
    only thing that can refuse the second is the comparison against the term's
    own dates.

    Both lengths and both dates are ones §2.2 allows, which is the same
    discipline E0-06 criterion 5 asks for: a range check over the legal lengths
    accepts this row happily, and only a rule that reads this term's end date
    refuses it.

    The letter goes into the map first and is accepted there, because E0-06's
    cross-table rule is about a letter's *length* against its term's — 12 weeks
    in an 18-week term is a perfectly legal row. If a schema refuses it, this
    test dies in its own seeding, and the message below says so: that would mean
    the rejection had moved into the database, which is a design the criterion
    permits and this module would then be asserting in the wrong place.
    """
    overrunning_letter = "G"
    overrunning_start = FALL_2026_START + timedelta(weeks=7)
    assert expected_end(overrunning_start, 12) > FALL_2026_END, (
        "The letter this test seeds does not actually run past the term, so there is nothing for "
        "the service to reject and the assertion below would be about nothing."
    )

    chain: dict[str, Any] = {}
    term = seed_fall_2026(db_session, declared_tables, chain)

    control = derive(section_codes, db_session, declared_tables, term, code_for("Q"))
    _, _, control_end = derived_parts(section_codes, control)
    assert control_end == FALL_2026_END, (
        f"The control — `Q1WW`, which ends on the term's last day — derived {control_end} rather "
        f"than {FALL_2026_END}, so the refusal below cannot be read as being about running past "
        "the term."
    )

    try:
        seed_letter(
            db_session,
            declared_tables,
            chain,
            letter=overrunning_letter,
            length_weeks=12,
            start=overrunning_start,
        )
    except DatabaseError as refused:
        pytest.fail(
            f"The database refused a 12-week letter starting {overrunning_start} in an 18-week "
            f"term: {refused}. E0-06's cross-table rule compares a letter's length against its "
            "term's length, and 12 is less than 18, so this row is legal there. A refusal means "
            "criterion 5 has been enforced in the schema instead of in the service — a design "
            "the criterion permits, and one this test would then be asserting in the wrong "
            "place."
        )

    failure = refusal(
        section_codes, db_session, declared_tables, term, code_for(overrunning_letter)
    )

    assert section_codes.raised_by_the_service(failure), (
        f"Deriving a section that runs past its term raised {failure!r}, which "
        f"`{type(failure).__module__}` defines rather than this project. The rejection has to be "
        "a decision the service made, not an exception that fell out of it — E0-07's definition "
        "of done asks for no exception type that escapes as a 500."
    )


def test_a_start_position_absent_from_the_terms_map_is_refused_and_the_error_names_it(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """Criterion 3: an unknown start letter raises an error naming the offending part.

    `A` is an ordinary letter that Fall 2026's map does not hold. The whole rest
    of the code is well formed, and the term's map holds twenty other positions,
    so nothing but the letter can be what is refused.

    The failure this catches is not a crash. It is a lookup that returns nothing
    and a derivation that carries on with a null length or a `None` start date,
    producing a section whose calendar is empty rather than one that was
    refused — the definition of done's "no code path where a malformed code
    silently produces a valid-looking section".
    """
    chain: dict[str, Any] = {}
    term = seed_fall_2026(db_session, declared_tables, chain)
    assert UNMAPPED_START not in ALL_STARTS, (
        f"{UNMAPPED_START!r} is in the seeded map, so it is not an unknown start letter and this "
        "test is about nothing."
    )

    code = code_for(UNMAPPED_START)
    failure = refusal(section_codes, db_session, declared_tables, term, code)

    assert section_codes.raised_by_the_service(failure), (
        f"Deriving {code!r} raised {failure!r}, which `{type(failure).__module__}` defines rather "
        "than this project. A `KeyError` or a `NoResultFound` off the map lookup is what an "
        "unguarded derivation raises, and neither is something the roster sync can catch and "
        "report."
    )

    message = str(failure).lower()
    assert any(word in message for word in START_LETTER_WORDS), (
        f"Deriving {code!r} raised {failure!r}, whose message names none of "
        f"{list(START_LETTER_WORDS)}. Criterion 3 wants an error 'naming the offending part': "
        "the operator reading it is looking at a roster sync that rejected a section, and needs "
        "to know it is the start letter — most likely a term whose map was never configured for "
        "that cohort."
    )


def test_the_three_kinds_of_malformed_code_raise_errors_a_caller_can_tell_apart(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """Criterion 3's word "distinct", across all three failures it names.

    An unknown start letter, an unknown modality and a missing ordinal. The
    unknown letter is a question about a term's map, which is why the complete
    comparison is here rather than in the unit module — that one asserts the two
    that need no map.

    Distinctness is asserted pairwise, on the type and the message together: one
    anonymous error for all three satisfies "raises an error" and tells the E1
    roster sync nothing about what to put in front of an operator. A single error
    class carrying three different messages passes, and should — the criterion
    asks the caller to be able to tell them apart, not for three classes.
    """
    chain: dict[str, Any] = {}
    term = seed_fall_2026(db_session, declared_tables, chain)

    failures = {
        "unknown start letter": refusal(
            section_codes, db_session, declared_tables, term, code_for(UNMAPPED_START)
        ),
        "unknown modality": refusal(section_codes, db_session, declared_tables, term, "R3ZZ"),
        "missing ordinal": refusal(section_codes, db_session, declared_tables, term, "RWW"),
    }

    fingerprints = {name: (type(failure), str(failure)) for name, failure in failures.items()}
    collisions = [
        (first, second)
        for index, first in enumerate(sorted(fingerprints))
        for second in sorted(fingerprints)[index + 1 :]
        if fingerprints[first] == fingerprints[second]
    ]

    assert not collisions, (
        f"These pairs of failures are indistinguishable — same exception type, same message: "
        f"{collisions}. What was raised: {failures}. Criterion 3: each of the three raises 'a "
        "distinct error naming the offending part'. A code the term's map has no row for and a "
        "code that lost its ordinal are two different things to do something about: the first is "
        "a calendar an admin has not finished configuring, the second is a feed sending "
        "malformed codes."
    )


# ---------------------------------------------------------------------------
# The 3-week sections §2.2 numbers rather than letters.
# ---------------------------------------------------------------------------


def test_every_numbered_three_week_start_derives_three_weeks(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """§2.2: "3-week sections numbered 2-7", and E0-07: "Handle the 3-week case".

    All six, because the failure this is looking for is a parser or a lookup that
    treats a digit differently from a letter, and that can bite at one end of the
    range — the map key stored as text and looked up as a number, or the other
    way round, works for the ones whose spelling survives the round trip.

    Each is asserted on its length and its start date together: a numbered
    position that resolves to the right row is the whole question, and the two
    values are how you can tell it did.
    """
    chain: dict[str, Any] = {}
    term = seed_fall_2026(db_session, declared_tables, chain)
    numbered = [entry for entry in FALL_2026_SEED_MAP if entry[0].isdigit()]
    assert len(numbered) == 6, (
        f"The seed map in this file holds {len(numbered)} numbered start positions; §2.2 numbers "
        "the 3-week sections 2 through 7, which is six of them."
    )

    wrong: dict[str, Any] = {}
    for start_position, length_weeks, offset in numbered:
        derived = derive(section_codes, db_session, declared_tables, term, code_for(start_position))
        found_length, found_start, _ = derived_parts(section_codes, derived)
        expected = (length_weeks, FALL_2026_START + timedelta(weeks=offset))
        if (found_length, found_start) != expected:
            wrong[start_position] = ((found_length, found_start), expected)

    assert not wrong, (
        f"These numbered 3-week start positions derived the wrong (length, start): {wrong}. SPEC "
        "§2.2 numbers the 3-week sections 2 through 7 while every other length is lettered, so "
        "the first character of a code is a start position whether or not it is a letter. Six of "
        "the twenty positions in the Fall 2026 map are numbered, and a derivation that only "
        "handles letters loses every 3-week section in the institution."
    )


@pytest.mark.parametrize("start_position", [BELOW_THE_NUMBERED_RANGE, ABOVE_THE_NUMBERED_RANGE])
def test_a_numbered_start_just_outside_the_range_the_map_holds_is_refused(
    db_session: Any,
    declared_tables: dict[str, Table],
    section_codes: Any,
    start_position: str,
) -> None:
    """The boundary either side of §2.2's "numbered 2-7".

    `1` and `8` are the two near misses: a range check written `2 <= n <= 8` or
    `1 <= n <= 7` accepts one of them, derives from a map row that does not
    exist, and every one of the six real positions goes on passing. They are
    refused here for the same reason `A` is — the term's map has no such row —
    and the point of writing them out is that a digit looks like something a
    numeric range could vouch for, when the only thing that can is the map.
    """
    chain: dict[str, Any] = {}
    term = seed_fall_2026(db_session, declared_tables, chain)
    assert start_position not in ALL_STARTS, (
        f"{start_position!r} is in the seeded map, so it is not outside the range and this test "
        "is about nothing."
    )

    code = code_for(start_position)
    failure = refusal(section_codes, db_session, declared_tables, term, code)

    assert section_codes.raised_by_the_service(failure), (
        f"Deriving {code!r} — a numbered start position the term's map does not hold — raised "
        f"{failure!r}, defined by `{type(failure).__module__}` rather than by this project. §2.2 "
        "numbers the 3-week sections 2 through 7, and what makes a position legal is a row in "
        "the term's map, not the digit being in a range."
    )


def test_the_same_numbered_code_derives_in_one_term_and_is_refused_in_another(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """Which numbered positions exist is the term's, and §2.2's 2-7 is one term's answer.

    An 18-week fall term has room for six 3-week blocks and §2.2 numbers them 2
    through 7. A 12-week summer term has room for four. So `61WW` is an ordinary
    code in the fall and names nothing in the summer, and the difference is data:
    the fall map has a row for 6 and the summer map does not.

    **The same code, two terms, opposite outcomes, in one transaction.** Every
    other numbered test in this module uses the Fall 2026 map alone, and a single
    term cannot show that the range moves — a parser carrying `2 <= n <= 7`
    passes all of them. It fails here, on the summer half, because it accepts a
    position the summer term has no row for and hands back a section with a start
    date read from nowhere.

    **The control is `21WW` in the same summer term.** Position 2 is in both
    maps, so its deriving in the summer proves the term and its map are readable
    and that the refusal below is about position 6 rather than about anything
    else in the row. Without it, a summer term that failed to seed would produce
    the same refusal and read as a pass (`docs/MISTAKES.md` entry 3).

    The two terms share an institution and do not overlap in time — summer ends
    8/2 and fall opens 8/17 — so nothing about the contrast rests on the calendar
    being unusual.
    """
    assert LEGAL_IN_FALL_ONLY in ALL_STARTS, (
        f"{LEGAL_IN_FALL_ONLY!r} is not in the Fall 2026 seed map, so the fall half of this test "
        "is about a position that does not exist there either, and the contrast is not one."
    )
    assert LEGAL_IN_FALL_ONLY not in SUMMER_STARTS, (
        f"{LEGAL_IN_FALL_ONLY!r} is in the summer map, so it is legal in both terms and there is "
        "no contrast to assert."
    )

    chain: dict[str, Any] = {}
    fall = seed_fall_2026(db_session, declared_tables, chain)
    summer_chain = {name: row for name, row in chain.items() if name == "institution"}
    summer = seed_summer_2026(db_session, declared_tables, summer_chain)
    assert summer_chain["term"] != chain["term"], (
        "Seeding the summer term reused the fall one, so both maps are one map and the refusal "
        "below would be about nothing."
    )

    code = code_for(LEGAL_IN_FALL_ONLY)
    _, _, offset = next(entry for entry in FALL_2026_SEED_MAP if entry[0] == LEGAL_IN_FALL_ONLY)
    in_the_fall = derive(section_codes, db_session, declared_tables, fall, code)
    found_length, found_start, _ = derived_parts(section_codes, in_the_fall)

    assert (found_length, found_start) == (
        THREE_WEEK_LENGTH,
        FALL_2026_START + timedelta(weeks=offset),
    ), (
        f"{code!r} derived {(found_length, found_start)} in the 18-week fall term, whose map row "
        f"for {LEGAL_IN_FALL_ONLY!r} says {THREE_WEEK_LENGTH} weeks from "
        f"{FALL_2026_START + timedelta(weeks=offset)}. It has to be an ordinary code somewhere "
        "before its refusal in the summer term means anything."
    )

    control = code_for(LEGAL_IN_BOTH)
    assert LEGAL_IN_BOTH in SUMMER_STARTS and LEGAL_IN_BOTH in ALL_STARTS, (
        f"{LEGAL_IN_BOTH!r} is not in both maps, so it is not a control for a refusal that is "
        "supposed to be about one position rather than about the summer term being unreadable."
    )
    try:
        derive(section_codes, db_session, declared_tables, summer, control)
    except Exception as raised:
        pytest.fail(
            f"The control code {control!r} was refused in the summer term: {raised!r}. Its "
            "position is in the summer map, so until it derives, the refusal below says nothing "
            "about which positions that map holds."
        )

    failure = refusal(
        section_codes,
        db_session,
        declared_tables,
        summer,
        code,
        because=(
            f"This code names position {LEGAL_IN_FALL_ONLY!r}, which the 18-week fall term's map "
            f"holds and this 12-week summer term's map does not — it holds "
            f"{list(SUMMER_STARTS)}. Deriving it here rather than refusing it is what a rule "
            "carrying §2.2's '2-7' as a range in the code does: that range describes the fall "
            "term's map, and a 12-week term has room for four 3-week blocks rather than six. The "
            "section it just produced has a start date that came from no configured row."
        ),
    )

    assert section_codes.raised_by_the_service(failure), (
        f"{code!r} derives in the 18-week fall term and was not refused by the service in the "
        f"12-week summer term, whose map holds {list(SUMMER_STARTS)} and no row for "
        f"{LEGAL_IN_FALL_ONLY!r}: it raised {failure!r}. §2.2's '3-week sections numbered 2-7' "
        "describes one term's map, not the parser — a 12-week term has room for four 3-week "
        "blocks, not six. A rule that hardcodes the fall's range accepts this code and derives a "
        "section whose start date came from no configured row."
    )


def test_every_numbered_position_in_a_twelve_week_terms_map_derives_three_weeks(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """The other half: the shorter term's own positions derive against its own calendar.

    The sibling of `test_every_numbered_three_week_start_derives_three_weeks`,
    which asserts the same thing for the fall. Two terms are needed for the same
    reason two are needed above: a derivation that read the length from the map
    and the start date from somewhere fixed would pass the fall test, because in
    the fall the fixed answer happens to be right.

    Asserted on the length and the start date together, since a numbered position
    resolving to the right row of the right term is the whole question.
    """
    chain: dict[str, Any] = {}
    summer = seed_summer_2026(db_session, declared_tables, chain)
    numbered = [entry for entry in SUMMER_2026_SEED_MAP if entry[0].isdigit()]
    assert numbered, (
        "The summer map in this file holds no numbered positions, so this test would pass "
        "against a service that cannot derive one at all."
    )

    wrong: dict[str, Any] = {}
    for start_position, length_weeks, offset in numbered:
        derived = derive(
            section_codes, db_session, declared_tables, summer, code_for(start_position)
        )
        found_length, found_start, _ = derived_parts(section_codes, derived)
        expected = (length_weeks, SUMMER_2026_START + timedelta(weeks=offset))
        if (found_length, found_start) != expected:
            wrong[start_position] = ((found_length, found_start), expected)

    assert not wrong, (
        f"These numbered positions in the 12-week summer term derived the wrong (length, start): "
        f"{wrong}. Their rows are in that term's map and nowhere else — the term starts "
        f"{SUMMER_2026_START} and the fall term starts {FALL_2026_START}, so a start date read "
        "off the wrong term is off by three months rather than by a week, and every week axis, "
        "survey window and participation denominator (§3.4) counts from it."
    )


def test_a_numbered_position_is_legal_because_its_row_exists_rather_than_by_range(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """No rule of the form "between these two numbers" can produce this answer.

    In the summer map, 7 is legal and 6 is not, while 2, 3 and 5 are legal. Any
    rule that admits a position because its number falls between a low and a high
    bound — `2 <= n <= 7`, or a bound computed from the term's length, or
    anything else of that shape — must admit 6 as soon as it admits both 5 and 7.
    So the pair below cannot be satisfied by a range at all, whatever its
    endpoints and however they are derived. Only a lookup that asks whether the
    row exists gives this answer.

    That is a strictly stronger claim than the two-term contrast above, which
    shows the range *moving* and is still satisfiable by a range computed per
    term: `2 <= n <= term_weeks // 3 + 1` gives 2-7 for eighteen weeks and 2-5
    for twelve, and passes that test and every other one in this module that uses
    the fall map alone. What it cannot do is admit 7 in a twelve-week term, which
    is the first half below — and it is worth knowing that it therefore also
    fails the sibling test that derives every summer position, since that map
    holds 7. This test is where the *reason* is legible: the two positions differ
    only in whether a row exists.

    **Both halves are needed and neither is redundant.** 7 deriving rules out a
    range with a low ceiling; 6 being refused rules out one with a high ceiling.
    Either alone is satisfied by some range.

    A non-contiguous map is a legitimate configuration rather than a contrivance:
    §2.2 makes the map admin-configured data, E0-06 stores it per term, and
    nothing anywhere requires a term to offer every block it has room for. A
    summer that runs four 3-week sessions and labels them by the fall's numbering
    is exactly the sort of thing E11's calendar editor will be used for.
    """
    assert LEGAL_IN_SUMMER_ABOVE_IT in SUMMER_STARTS, (
        f"{LEGAL_IN_SUMMER_ABOVE_IT!r} is not in the summer map, so the half of this test that "
        "rules out a low ceiling is about nothing."
    )
    assert LEGAL_IN_FALL_ONLY not in SUMMER_STARTS, (
        f"{LEGAL_IN_FALL_ONLY!r} is in the summer map, so there is no gap in the numbering and a "
        "range rule survives this test."
    )
    assert LEGAL_IN_FALL_ONLY < LEGAL_IN_SUMMER_ABOVE_IT, (
        f"{LEGAL_IN_FALL_ONLY!r} is not below {LEGAL_IN_SUMMER_ABOVE_IT!r}, so a range admitting "
        "the second need not admit the first and the argument this test rests on does not hold."
    )

    chain: dict[str, Any] = {}
    summer = seed_summer_2026(db_session, declared_tables, chain)

    legal = code_for(LEGAL_IN_SUMMER_ABOVE_IT)
    _, length_weeks, offset = next(
        entry for entry in SUMMER_2026_SEED_MAP if entry[0] == LEGAL_IN_SUMMER_ABOVE_IT
    )
    derived = derive(section_codes, db_session, declared_tables, summer, legal)
    found_length, found_start, _ = derived_parts(section_codes, derived)

    assert (found_length, found_start) == (
        length_weeks,
        SUMMER_2026_START + timedelta(weeks=offset),
    ), (
        f"{legal!r} derived {(found_length, found_start)} in a term whose map row for "
        f"{LEGAL_IN_SUMMER_ABOVE_IT!r} says {length_weeks} weeks from "
        f"{SUMMER_2026_START + timedelta(weeks=offset)}. The row is there, so the position is "
        "legal — a service that refuses it is applying a rule about the number itself, most "
        f"likely a ceiling drawn from the term's {SUMMER_2026_WEEKS} weeks."
    )

    failure = refusal(
        section_codes,
        db_session,
        declared_tables,
        summer,
        code_for(LEGAL_IN_FALL_ONLY),
        because=(
            f"This term's map holds {list(SUMMER_STARTS)}, so position {LEGAL_IN_FALL_ONLY!r} "
            f"has no row while {LEGAL_IN_SUMMER_ABOVE_IT!r} above it does. Deriving it means the "
            "service decided by the number rather than by the map — and no rule of the form "
            "'between a low and a high bound' can admit 5 and 7 while refusing 6, so this is a "
            "range check whatever its endpoints are and however they were computed."
        ),
    )

    assert section_codes.raised_by_the_service(failure), (
        f"In a term whose map holds {list(SUMMER_STARTS)}, position "
        f"{LEGAL_IN_SUMMER_ABOVE_IT!r} derives and position {LEGAL_IN_FALL_ONLY!r} was not "
        f"refused by the service: it raised {failure!r}. There is no row for it. Any rule that "
        f"admits {LEGAL_IN_FALL_ONLY!r} while admitting "
        f"{LEGAL_IN_SUMMER_ABOVE_IT!r} is deciding by the number rather than by the map, and "
        "§2.2 makes the map the configuration that decides — a section derived from a row that "
        "does not exist has a calendar nobody set."
    )


# ---------------------------------------------------------------------------
# Criterion 7 — the course-week to term-week offset.
# ---------------------------------------------------------------------------


def test_the_offset_for_a_section_that_starts_five_weeks_into_its_term(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """Criterion 7, in the case the criterion names.

    A 12-week letter starting five weeks after the term begins: its course week 1
    is the term's week 6, and its course week 3 is the term's week 8. §2.2 needs
    both axes at once — course-level pages plot "WK 01…" with a quiet "TERM 04…"
    sub-label, and aggregate pages plot the term axis with one line per start
    cohort — so the offset is what keeps two charts of the same data from
    disagreeing.

    **Two course weeks, not one.** A function asked only about course week 1 can
    return 6 by adding the offset, and can also return 6 by returning the term
    week the section starts in and ignoring its argument. Asking for course week
    3 as well separates them. And the classic wrong answer is 5 — the difference
    rather than the week — which is a defect that reads as correct in every
    sentence anyone writes about it.

    **Which of the two questions the function answers is read off its
    signature**, because E0-07 says "course-week to term-week offset is computed"
    and does not say whether that is a number or a conversion. A callable that
    takes a course week is asked for the term week of that course week; one that
    does not is asked for the offset between the axes. Both are the same
    arithmetic, and neither is invented here — what is refused is a function that
    is off by one in either reading.

    The term's `week` rows are seeded as well, because the term axis is data
    rather than arithmetic in E0-06 and a lookup that joins to them should find
    them.
    """
    weeks_in = 5
    section_start = FALL_2026_START + timedelta(weeks=weeks_in)

    chain: dict[str, Any] = {}
    term = seed_term(db_session, declared_tables, chain)
    for number in range(1, FALL_2026_WEEKS + 1):
        seed_row(db_session, declared_tables, "week", chain, **{WEEK_NUMBER_COLUMN: number})
    seed_letter(
        db_session, declared_tables, chain, letter="R", length_weeks=12, start=section_start
    )

    term_table = require_table(declared_tables, "term")
    key = single_primary_key(term_table)
    instance = db_session.get(model_for("term"), term[key])
    offered: dict[str, Any] = {
        "session": db_session,
        "code": code_for("R"),
        "term": instance,
        "term_id": term[key],
    }

    function = section_codes.offset
    takes_a_course_week = any(
        section_codes.role_of(name) == "course_week" for name in signature(function).parameters
    )

    if not takes_a_course_week:
        answer = section_codes.call(function, **offered)
        assert int(answer) == weeks_in, (
            f"A section starting {weeks_in} weeks into its term reported an offset of {answer!r} "
            f"rather than {weeks_in}. Its course week 1 is the term's week {weeks_in + 1}, so "
            f"the offset between the two axes is {weeks_in}. An answer of {weeks_in + 1} is the "
            "term week of the section's first week rather than the offset, and every sub-label "
            "on the instructor report is then one week ahead."
        )
        return

    for course_week, term_week in ((1, weeks_in + 1), (3, weeks_in + 3)):
        answer = section_codes.call(function, course_week=course_week, **offered)
        assert int(answer) == term_week, (
            f"Course week {course_week} of a section starting {weeks_in} weeks into its term "
            f"converted to term week {answer!r} rather than {term_week}. §2.2 plots course week "
            "with a term-week sub-label on course-level pages and the term axis on aggregate "
            f"pages; an answer of {term_week - 1} is the offset returned instead of the week, "
            f"and {term_week + 1} or {term_week - 2} is an off-by-one that lines this section's "
            "week up against the wrong week of every other cohort."
        )


# ---------------------------------------------------------------------------
# The derived columns E0-07 adds to `section`.
# ---------------------------------------------------------------------------


def test_the_section_table_carries_the_four_derived_columns(
    reflected_tables: dict[str, Table],
) -> None:
    """E0-07's scope: "Add the derived section columns ... **They are not on `section` yet.**"

    No acceptance criterion carries this, which is `docs/MISTAKES.md` entry 2's
    exact shape: the ticket says E0-05 shipped `section` with its course key and
    its code and nothing else, and that the four derived columns "arrive with the
    code that fills them". A ticket item with nothing asserting it ships or does
    not ship at nobody's notice.

    Read from the migrated database and not from `Base.metadata`, because a
    column on the metadata that no migration created exists nowhere a deployment
    can reach — and `alembic check` reports no drift for a model nobody imported.

    **What is deliberately not asserted here** is that the four are `NOT NULL`.
    "Populate them through this service, so there is exactly one path that sets
    them" is a property of the code's shape rather than of the schema, and
    whether a section may exist for a moment without its calendar is a decision
    E0-07 leaves open — asserting it here would make that choice for the
    implementer from the test suite.
    """
    section = require_table(reflected_tables, "section")
    present = {column.name: column for column in section.columns}

    missing = [name for name in SECTION_DERIVED_COLUMNS if name not in present]
    assert not missing, (
        f"`section` has no {missing} column in the migrated database — it has "
        f"{sorted(present)}. E0-07 adds `length_weeks`, `start_date`, `end_date` and `modality` "
        "and populates them through the service, so that the one path that sets them is the one "
        "that derives them (SPEC §8: 'section `length_weeks` and start/end dates derive from the "
        "section code via `start_letter_map` — LMS-owned data is never hand-edited in Pulse')."
    )

    wrong_types = {
        name: present[name].type
        for name, expected in (
            (DERIVED_LENGTH, Integer),
            (DERIVED_START, Date),
            (DERIVED_END, Date),
        )
        if not isinstance(stored_type(present[name]), expected)
    }
    assert not wrong_types, (
        f"These derived columns on `section` are not of the type the value is: {wrong_types}. A "
        "length in weeks is an integer and a start or end date is a date — §2.2 derives them "
        "from the letter map, whose own columns E0-06 gave those types. A date stored as a "
        "timestamp acquires a time of day nothing sets and a timezone every reader has to guess."
    )


def test_the_service_writes_all_four_derived_columns_onto_a_section(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """E0-07's scope: the derived columns are populated through this service.

    A section is seeded carrying `R1WW` and a calendar that belongs to no start
    position in its term's map — the hand-set state the ticket refuses — the
    service's writer is run against it, and the row is read back. Afterwards all
    four columns hold what the service's own derivation says for that code in
    that term.

    **The before-assertion is not ceremony.** "The columns hold the derived
    values" is equally true of a row that held them all along, so each of the
    four is required to differ first (`docs/MISTAKES.md` entry 3). The
    placeholder modality is taken from the service's derivation of `R1FF`, which
    is why it is both certainly storable in that column and certainly not the
    answer for `R1WW` — that last part resting on
    `test_the_two_modality_suffixes_do_not_parse_to_the_same_value` in the unit
    module, which is where a service that maps both suffixes to one value fails.

    **The expected values come from the derivation rather than from this file.**
    That is the property the ticket's sentence is really about: "exactly one path
    that sets them" means the columns cannot say something the derivation does
    not. Comparing against constants would pass a writer that computes its own
    answer and happens to agree here; comparing against the derivation is what
    holds the two together, and the sibling test below does it across the whole
    map, where a second implementation is most likely to diverge.

    **What this does not cover, and cannot from outside.**

      - *That there is no second writer.* A test can see what the columns hold
        after the service runs; it cannot see that nothing else in the codebase
        assigns them. Closing that needs something the implementation declares —
        a mapper-level guard, or an authz rule at the E0-11 chokepoint — and
        E0-07 leaves the mechanism open, so asserting one here would choose it.
      - *That the columns are `NOT NULL`.* Whether a section may exist for a
        moment without its calendar is a decision the ticket leaves open.
      - *That anything calls the writer.* Roster sync is E1; what is asserted
        here is that the path exists and is the one that produces the values.
    """
    chain: dict[str, Any] = {}
    term = seed_fall_2026(db_session, declared_tables, chain)
    code = code_for("R")

    wanted = derive(section_codes, db_session, declared_tables, term, code)
    wanted_length, wanted_start, wanted_end = derived_parts(section_codes, wanted)
    wanted_modality = section_codes.part(wanted, (DERIVED_MODALITY,), "derived modality")

    face_to_face = derive(
        section_codes,
        db_session,
        declared_tables,
        term,
        code_for("R", suffix=FACE_TO_FACE_SUFFIX),
    )
    placeholder_modality = section_codes.part(face_to_face, (DERIVED_MODALITY,), "derived modality")

    section = seed_placeholder_section(
        db_session, declared_tables, chain, code=code, modality=placeholder_modality
    )

    already_right = [
        name
        for name, wanted_value in (
            (DERIVED_LENGTH, wanted_length),
            (DERIVED_START, wanted_start),
            (DERIVED_END, wanted_end),
        )
        if section[name] == wanted_value
    ]
    if modality_text(section[DERIVED_MODALITY]) == modality_text(wanted_modality):
        already_right.append(DERIVED_MODALITY)
    assert not already_right, (
        f"The seeded section already holds the derived values in {already_right} before the "
        f"service has run: it was seeded with {PLACEHOLDER_LENGTH_WEEKS} weeks from "
        f"{PLACEHOLDER_START} and the face-to-face modality, and {code} derives "
        f"{(wanted_length, wanted_start, wanted_end)} online. Until they differ, finding the "
        "derived values afterwards says nothing about anything having been written."
    )

    apply_code_to_section(section_codes, db_session, declared_tables, term, section, code)
    stored = stored_section(db_session, declared_tables, section)

    wrong = {
        name: (stored[name], wanted_value)
        for name, wanted_value in (
            (DERIVED_LENGTH, wanted_length),
            (DERIVED_START, wanted_start),
            (DERIVED_END, wanted_end),
        )
        if stored[name] != wanted_value
    }
    if modality_text(stored[DERIVED_MODALITY]) != modality_text(wanted_modality):
        wrong[DERIVED_MODALITY] = (stored[DERIVED_MODALITY], wanted_modality)

    assert not wrong, (
        f"After the service ran against a section carrying {code}, these columns hold (stored, "
        f"expected from the derivation): {wrong}. E0-07 adds the four derived columns and "
        "populates them 'through this service, so there is exactly one path that sets them'. A "
        "column left holding the placeholder is one the writer does not touch, and it will be "
        "hand-set by whatever needs it next — which is the state SPEC §2.2 rules out: 'Section "
        "start/end dates derive from the letter + term calendar; nothing is hand-entered per "
        "section.'"
    )


def test_the_written_columns_agree_with_the_derivation_for_every_position_in_the_map(
    db_session: Any, declared_tables: dict[str, Table], section_codes: Any
) -> None:
    """The other half of "exactly one path": the writer cannot have its own arithmetic.

    A writer that re-derives the calendar itself rather than going through the
    derivation is a second path in everything but name, and the test above cannot
    see it — one section, one letter, and any re-implementation that is correct
    for `R` agrees. Where two implementations of the same rule come apart is at
    the edges: the 3-week positions §2.2 numbers rather than letters, the 16-week
    cohort that fills the term, the letter whose section ends on the term's last
    day. So every start position in the seed map is written and compared.

    It is the shape a greedy start-position parse has — right for the lettered
    positions, wrong for every numbered one — which the map-wide tests above
    catch in the derivation and this one catches on the way to the column.

    This still cannot see a second writer that agrees. What it refuses is a
    second writer that disagrees, which is the drift the ticket's "exactly one
    path" exists to prevent, and it is the strongest form of that claim available
    from outside the implementation.
    """
    chain: dict[str, Any] = {}
    term = seed_fall_2026(db_session, declared_tables, chain)

    face_to_face = derive(
        section_codes,
        db_session,
        declared_tables,
        term,
        code_for("R", suffix=FACE_TO_FACE_SUFFIX),
    )
    placeholder_modality = section_codes.part(face_to_face, (DERIVED_MODALITY,), "derived modality")

    wrong: dict[str, Any] = {}
    for start_position, _, _ in FALL_2026_SEED_MAP:
        code = code_for(start_position)
        wanted = derived_parts(
            section_codes, derive(section_codes, db_session, declared_tables, term, code)
        )
        section = seed_placeholder_section(
            db_session, declared_tables, chain, code=code, modality=placeholder_modality
        )
        apply_code_to_section(section_codes, db_session, declared_tables, term, section, code)
        stored = stored_section(db_session, declared_tables, section)
        found = (stored[DERIVED_LENGTH], stored[DERIVED_START], stored[DERIVED_END])
        if found != wanted:
            wrong[start_position] = (found, wanted)

    assert not wrong, (
        f"For these start positions the columns the service wrote disagree with what the same "
        f"service derives for the same code and term (stored, derived): {wrong}. Two answers to "
        "one question mean the writer has arithmetic of its own, and E0-07 puts the derived "
        "columns behind this service precisely so that there is one. The reports read the "
        "columns and the comparison sets read the derivation (SPEC §5.1), so a disagreement here "
        "is a section benchmarked against a cohort its own dates say it is not in."
    )


# ---------------------------------------------------------------------------
# Criterion 6 — the properties. SPEC §9.1: "section-code parsing tests across
# the full start-letter map".
# ---------------------------------------------------------------------------


@contextmanager
def one_example(db_session: Any) -> Iterator[None]:
    """Give one Hypothesis example its own savepoint, rolled back afterwards.

    Not a fixture, and that distinction is the point: a fixture is built once for
    the whole property, so every example would share it and the rows of the first
    would still be there for the second. The rollback has to happen in the test
    *body*, which is what runs per example — the shape
    `tests/integration/test_term_calendar_schema.py` uses for the same reason.
    """
    savepoint = db_session.begin_nested()
    try:
        yield
    finally:
        savepoint.rollback()


@pytest.mark.slow
@settings(
    max_examples=25,
    deadline=None,
    # The database session is function-scoped, so Hypothesis is right to warn
    # that examples share it. Each one runs inside its own savepoint and rolls
    # back, which is the state reset the health check is asking about.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    rows=st.lists(
        st.tuples(
            st.sampled_from(ALL_STARTS),
            st.sampled_from(SECTION_LENGTHS),
            st.integers(min_value=0, max_value=FALL_2026_WEEKS - 1),
        ),
        unique_by=lambda row: row[0],
        min_size=1,
        max_size=6,
    ),
)
def test_every_letter_in_a_generated_map_round_trips_to_a_length_and_a_date_inside_its_term(
    db_session: Any,
    declared_tables: dict[str, Table],
    section_codes: Any,
    rows: list[tuple[str, int, int]],
) -> None:
    """E0-07: "every letter in a seeded map round-trips to a length and a start date inside its term".

    Generated rather than exampled because the failures worth finding are
    combinations: a length that is fine at 6 weeks and overflows at 16, a start
    position that only appears when a map holds both letters and digits, a
    lookup that is right when the map has one row and ambiguous when it has six.
    The twenty positions and eight lengths of §2.2 are more combinations than
    anyone writes out.

    The generated offset is reduced into the room the length leaves, rather than
    filtered, so every example is a map an admin could have configured and no
    examples are thrown away. The case where a letter *does not* fit is the
    subject of the property below, which is a different claim.
    """
    with one_example(db_session):
        chain: dict[str, Any] = {}
        term = seed_term(db_session, declared_tables, chain)

        seeded: list[tuple[str, int, date]] = []
        for start_position, length_weeks, raw_offset in rows:
            offset = raw_offset % (FALL_2026_WEEKS - length_weeks + 1)
            start = FALL_2026_START + timedelta(weeks=offset)
            seed_letter(
                db_session,
                declared_tables,
                chain,
                letter=start_position,
                length_weeks=length_weeks,
                start=start,
            )
            seeded.append((start_position, length_weeks, start))

        for start_position, length_weeks, start in seeded:
            derived = derive(
                section_codes, db_session, declared_tables, term, code_for(start_position)
            )
            found_length, found_start, found_end = derived_parts(section_codes, derived)

            assert (found_length, found_start) == (length_weeks, start), (
                f"`{code_for(start_position)}` derived {(found_length, found_start)} from a map "
                f"row holding {(length_weeks, start)}. The map is the only source for either "
                f"value (§2.2), and this term's map holds {[row[0] for row in seeded]}."
            )
            assert found_end == expected_end(start, length_weeks), (
                f"`{code_for(start_position)}` derived an end date of {found_end}; "
                f"{length_weeks} weeks from {start} ends {expected_end(start, length_weeks)}."
            )
            assert found_start >= FALL_2026_START and found_end <= FALL_2026_END, (
                f"`{code_for(start_position)}` derived {found_start} to {found_end}, outside its "
                f"term ({FALL_2026_START} to {FALL_2026_END}) — and its map row fits inside the "
                "term, so the derivation put it there rather than the configuration."
            )


@pytest.mark.slow
@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    start_position=st.sampled_from(ALL_STARTS),
    length_weeks=st.sampled_from(SECTION_LENGTHS),
    offset=st.integers(min_value=0, max_value=FALL_2026_WEEKS - 1),
    ordinal=st.integers(min_value=1, max_value=9),
)
def test_no_code_derives_a_date_outside_its_term_without_being_rejected(
    db_session: Any,
    declared_tables: dict[str, Table],
    section_codes: Any,
    start_position: str,
    length_weeks: int,
    offset: int,
    ordinal: int,
) -> None:
    """Criterion 6: parsing never succeeds into a derivation that leaves the term.

    "Hypothesis generates letter-map and code combinations without finding a case
    where parsing succeeds but derivation produces a date outside the term."

    Asserted as a biconditional, and that is the whole strength of it. "It is
    rejected when it does not fit" alone is satisfied by a service that rejects
    everything; "the dates are inside the term when it does not raise" alone is
    satisfied by one that raises on every code (`docs/MISTAKES.md` entry 3, in
    both directions at once). So each example asserts exactly one of the two
    outcomes, chosen by whether the seeded row actually fits in the term.

    Unlike the property above, the offset here is *not* reduced into the room the
    length leaves — a 16-week letter starting in the term's fifteenth week is
    exactly the configuration this is about, and E0-06 accepts the row, because
    its cross-table rule compares the letter's length against the term's and 16
    is less than 18.
    """
    start = FALL_2026_START + timedelta(weeks=offset)
    end = expected_end(start, length_weeks)
    fits = end <= FALL_2026_END

    with one_example(db_session):
        chain: dict[str, Any] = {}
        term = seed_term(db_session, declared_tables, chain)
        try:
            seed_letter(
                db_session,
                declared_tables,
                chain,
                letter=start_position,
                length_weeks=length_weeks,
                start=start,
            )
        except DatabaseError as refused:
            pytest.fail(
                f"The database refused a {length_weeks}-week letter starting {start} in an "
                f"{FALL_2026_WEEKS}-week term: {refused}. E0-06's cross-table rule compares the "
                "letter's length against its term's, and every length generated here is at most "
                "the term's. A refusal means the schema also constrains the start date, which "
                "would make criterion 5 the database's rule rather than the service's — a design "
                "the criterion permits, and one this property would then be asserting in the "
                "wrong place."
            )

        code = code_for(start_position, ordinal=ordinal)
        if not fits:
            failure = refusal(section_codes, db_session, declared_tables, term, code)
            assert section_codes.raised_by_the_service(failure), (
                f"{code!r} would run {start} to {end}, past the term's {FALL_2026_END}, and the "
                f"derivation raised {failure!r} — defined by `{type(failure).__module__}` rather "
                "than by this project, so it is not a rejection the service decided on and not "
                "one a caller can catch."
            )
            return

        derived = derive(section_codes, db_session, declared_tables, term, code)
        found_length, found_start, found_end = derived_parts(section_codes, derived)

        assert (found_length, found_start, found_end) == (length_weeks, start, end), (
            f"{code!r} derived {(found_length, found_start, found_end)} from a map row holding "
            f"{(length_weeks, start)} in a term running {FALL_2026_START} to {FALL_2026_END}."
        )
        assert found_start >= FALL_2026_START and found_end <= FALL_2026_END, (
            f"{code!r} derived {found_start} to {found_end}, outside its term "
            f"({FALL_2026_START} to {FALL_2026_END}), and its map row fits inside it."
        )
