"""E0-09 — role assignments and the supervision graph.

`supervision_graph` is shared for the reason every other shared thing is, and
with one more of its own. Two modules ask it the same question — the schema tests
and the Hypothesis properties over generated graphs — and E0-09's definition of
done asks for "a fixture builder for the assistant-dean shape that E9 will
reuse", so a copy in a test module would be a copy E9 has to find. It carries a
fourth copy of the row-seeding helper that
`tests/integration/test_org_containment_schema.py`, `test_term_calendar_schema.py`
and `test_identity_schema.py` each hold; merging the other three is a refactor
that would edit three tickets' modules, so this one is written here rather than
imported from any of them. What the builder refuses to decide — what a scope node
is made of, and how a role is spelled — is written on the class.

E0-10's `seed_rows` sits beside it and is built out of the same helper: its Care
reveal can only be asserted against an identity that exists, and the seeding it
needs is "one row of whatever table, with its ancestors" rather than a graph
shape.

E0-11 adds `supervision_graph_on`, which is the same builder on a session the
caller opened rather than on `db_session`: the ticket's migration has to answer
for rows that were already stored when it runs, and no fixture here could reach
that state before.

**Nothing here seeds into a schema that is not `Base.metadata`'s, and nothing
here can.** `seed_row` writes through the declared tables and reads every
declared column back, so the database it is pointed at has to be at head. That is
a rule about this helper rather than about any one migration, it is stated on
`seed_row` and on `supervision_graph_on` below, and `seed_row` fails saying so
when a caller breaks it. A test whose *subject* is an older revision seeds while
the database is at head and walks it back down afterwards — see
`tests/integration/test_the_upgrade_refuses_a_stored_edge_that_does_not_climb.py`,
which is the one caller that needs to.

**This module is the one home of the two mutable caches** `_GRAPH_UNIQUE` and
`_GRAPH_INTEGER_COUNTERS`. They are what guarantee that no two seeded rows in a
test collide, so a second copy of either would hand out a value that is unique
only within the module holding it. Anything that needs them imports this module's
functions rather than keeping counters of its own.
"""

import importlib
import string
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import count
from typing import Any
from uuid import uuid4

import pytest

from fixtures.database import DatabaseUnderTest

# E0-09 — role assignments and the supervision graph.
# ---------------------------------------------------------------------------

# Spelled by the ticket and by SPEC §8's table list, so not this file's choice.
ROLE_ASSIGNMENT_TABLE = "role_assignment"
LEAD_FACULTY_MAPPING_TABLE = "lead_faculty_mapping"
E0_09_TABLES = (ROLE_ASSIGNMENT_TABLE, LEAD_FACULTY_MAPPING_TABLE)

# SPEC §2.1's containment hierarchy, outermost first. Used to build a sibling
# node at a given level: everything strictly above it is kept, everything at or
# below it is built fresh.
CONTAINMENT_ORDER = ("institution", "college", "department", "prefix", "course", "section")

# The three columns E0-09 and SPEC §8 both spell — `person_id`, `role`,
# `scope_node_id` — plus `reports_to`. Each is a candidate list rather than a
# literal, because the ticket's prose spelling and a model's column name are
# allowed to differ and a rename should be a one-line change here rather than a
# rewrite of two test modules. The spelled name is always first.
ROLE_COLUMN_CANDIDATES = ("role", "role_name", "role_code")
REPORTS_TO_CANDIDATES = (
    "reports_to",
    "reports_to_id",
    "reports_to_assignment_id",
    "parent_assignment_id",
    "supervisor_assignment_id",
)
SCOPE_ID_CANDIDATES = ("scope_node_id", "scope_id", "org_node_id", "node_id")
SCOPE_KIND_CANDIDATES = (
    "scope_node_kind",
    "scope_kind",
    "scope_node_type",
    "scope_type",
    "node_kind",
    "node_type",
    "scope_level",
)

# How each role is spelled, as exact alternatives matched case-insensitively
# against whatever the `role` column enumerates. Five of the nine come straight
# out of SPEC §2.1's canonical chain — `INSTRUCTOR(section) → LEAD_FACULTY(course)
# → CHAIR(department) → DEAN(college) → VP_ACADEMICS` — and `CARE` out of E0-09's
# own scope; the rest are **this file's choice** of the obvious spelling, with one
# or two alternatives each. Matching is exact rather than by substring on purpose:
# `DEAN` is a substring of `ASSISTANT_DEAN`, and a fuzzy match that resolved the
# two to one enum value would silently make every assistant-dean test a second
# dean test.
ROLE_ALIASES = {
    "INSTRUCTOR": ("INSTRUCTOR",),
    "LEAD_FACULTY": ("LEAD_FACULTY", "LEAD"),
    "CHAIR": ("CHAIR", "DEPARTMENT_CHAIR", "DEPT_CHAIR"),
    "ASSISTANT_DEAN": ("ASSISTANT_DEAN", "ASST_DEAN"),
    "DEAN": ("DEAN",),
    "VP_ACADEMICS": ("VP_ACADEMICS", "VPAA", "VP_OF_ACADEMICS"),
    "CARE": ("CARE",),
    "ADMIN": ("ADMIN",),
    "STUDENT": ("STUDENT",),
}

# The kind of containment node each role is scoped to. E0-09's scope: "a chair
# scoped to a department, a dean to a college, a lead to a course, **Care and
# Admin to the institution**"; SPEC §2.1's table gives the instructor a section
# and the VP the institution, and puts the assistant dean on "the same node as
# the dean". `STUDENT` is deliberately absent: §2.1 attaches a student to "own
# responses" rather than to a node, and no ticket says a student holds a
# `role_assignment` row at all.
ROLE_SCOPE_GRAIN = {
    "INSTRUCTOR": "section",
    "LEAD_FACULTY": "course",
    "CHAIR": "department",
    "ASSISTANT_DEAN": "college",
    "DEAN": "college",
    "VP_ACADEMICS": "institution",
    "CARE": "institution",
    "ADMIN": "institution",
}

# Distinguishes "no parent was asked for" from "the parent is explicitly NULL",
# which a nullable column needs: `seed_row` honours an override that is `None`.
UNSET = object()

# ---------------------------------------------------------------------------
# Values the seeding helper invents. Guesses about *values* only — nothing here
# decides that a column exists or what it is called, and nothing here is read by
# an assertion. Chosen to be mutually consistent with the calendar E0-06
# enforces, so that a cross-column check constraint cannot reject the helper's
# own rows and leave a test failing inside its fixture: an 18-week fall term
# running 8/17 to 12/20. A copy of `test_identity_schema.py`'s set.
# ---------------------------------------------------------------------------

GRAPH_TERM_START = date(2026, 8, 17)
GRAPH_TERM_END = date(2026, 12, 20)
GRAPH_LENGTH_WEEKS = 18
GRAPH_WEEK_CEILING = 18
GRAPH_WINDOW_OPENS_AT = datetime(2026, 8, 21, 22, 0, tzinfo=UTC)
GRAPH_WINDOW_CLOSES_AT = datetime(2026, 8, 24, 3, 59, 59, tzinfo=UTC)

GRAPH_DATE_HINTS = (
    ("start", GRAPH_TERM_START),
    ("begin", GRAPH_TERM_START),
    ("end", GRAPH_TERM_END),
)
GRAPH_DATETIME_HINTS = (
    ("open", GRAPH_WINDOW_OPENS_AT),
    ("close", GRAPH_WINDOW_CLOSES_AT),
    ("end", GRAPH_WINDOW_CLOSES_AT),
)
GRAPH_LENGTH_FRAGMENTS = ("length", "weeks", "duration")

# Two columns whose value this file has to choose deliberately, because each is
# governed by **two** rules from an earlier ticket and satisfying one of them is
# what breaks the other. A course number has to sit inside SPEC §8's bands *and*
# be unique within its prefix (E0-05's `uq_course_prefix_id_lms_number`); a
# section code has to match §2.2's shape *and* be unique within its course and
# term (E0-06's `UniqueConstraint("course_id", "term_id", "lms_section_code")`).
#
# An earlier version of this file pinned the course number to the constant
# `"150"`, which met the band rule and violated the uniqueness one the moment a
# test asked for a second course under one prefix — `fresh_scope("course")` keeps
# the shared `prefix` row on purpose, because two courses under one prefix is
# what a sibling lead *is*. Three tests were blocked before any assertion ran and
# it took a dispute to settle ([E0-09-01](../../docs/disputes/E0-09-01.md)). Both
# values are now drawn fresh per call.
GRAPH_SECTION_CODE_COLUMN = "lms_section_code"
GRAPH_COURSE_NUMBER_COLUMN = "lms_number"

# The band a generated course number is drawn from: three digits, `100`-`799`,
# which SPEC §8 splits into UG, UGGR and GR. Staying inside a band matters more
# than which band, because the bands are not enforced by a `CHECK`: `course.level`
# is a stored generated column ([ADR 0015](../../docs/adr/0015-course-level-is-a-stored-generated-column.md))
# and an out-of-band number derives `NULL::course_level`, so the row is refused by
# that column's `NOT NULL` and the error names the level rather than the number.
# `000`-`099` is left out only because it needs zero padding to stay three digits,
# and a padded number is a case E0-05's own tests own rather than this fixture's.
GRAPH_COURSE_NUMBER_FIRST = 100
GRAPH_COURSE_NUMBER_LAST = 799

_GRAPH_UNIQUE = count(1)
_GRAPH_INTEGER_COUNTERS: dict[tuple[str, str], Any] = {}


def graph_letters(limit: int | None) -> str:
    """A short, unique, upper-case string that fits a column of length `limit`.

    Upper-case letters and nothing else, because a code column plausibly carries
    a format check and a hex string would trip it — failing a test inside its own
    seeding for a reason it is not about.
    """
    width = max(min(6, limit or 6), 1)
    value = next(_GRAPH_UNIQUE)
    out = []
    for _ in range(width):
        value, remainder = divmod(value, 26)
        out.append(string.ascii_uppercase[remainder])
    return "".join(reversed(out))


def graph_unique_url() -> str:
    """A URL no other seeded row will carry, since an issuer is plausibly unique."""
    return f"https://{graph_letters(6).lower()}.example.invalid"


def graph_unique_email() -> str:
    """An address no other seeded row will carry, for the same reason."""
    return f"{graph_letters(6).lower()}@example.invalid"


GRAPH_STRING_HINTS = (
    ("timezone", lambda: "America/New_York"),
    ("email", graph_unique_email),
    ("issuer", graph_unique_url),
    ("iss", graph_unique_url),
    ("url", graph_unique_url),
    ("uri", graph_unique_url),
    ("jwks", graph_unique_url),
)


def graph_course_number() -> str:
    """A course number no other course in this test carries, inside SPEC §8's bands.

    Counts up from `GRAPH_COURSE_NUMBER_FIRST` rather than wrapping around it, and
    the difference is the whole repair: a generator that wrapped would hand out a
    duplicate again once a test asked for enough courses, and the failure would
    look exactly like the one this replaces — a unique violation on an E0-05
    constraint, raised inside a fixture, from a statement naming no column E0-09
    owns.

    **Per test rather than per session**, which is enough here and is the reason
    it borrows `_GRAPH_INTEGER_COUNTERS`: that dict is cleared by the
    `supervision_graph` fixture for every test, and `db_session` rolls every write
    back at the end of one, so two tests cannot see each other's courses. One
    reset mechanism serves both counters, rather than a second one beside it that
    could drift out of step (`docs/MISTAKES.md` entry 13).

    **Not `graph_letters`, which is what the section code beside it uses.** That
    draws from a session-wide counter one letter wide, so it repeats every 26
    calls; a course number built the same way would reintroduce a rarer and
    order-dependent version of this same defect, and rarer is worse — it would
    surface as a flake in somebody else's ticket.
    """
    counter = _GRAPH_INTEGER_COUNTERS.setdefault(
        ("course", GRAPH_COURSE_NUMBER_COLUMN), count(GRAPH_COURSE_NUMBER_FIRST)
    )
    number = next(counter)
    if number > GRAPH_COURSE_NUMBER_LAST:
        available = GRAPH_COURSE_NUMBER_LAST - GRAPH_COURSE_NUMBER_FIRST + 1
        pytest.fail(
            f"This test asked for more than {available} courses, so the seeding helper has run "
            f"out of three-digit numbers inside SPEC §8's bands. It stops here rather than "
            f"starting again at {GRAPH_COURSE_NUMBER_FIRST}: reusing a number would write a "
            "second course with the same number under the same prefix, which E0-05's "
            "`uq_course_prefix_id_lms_number` refuses — and that failure would be a unique "
            "violation raised inside a fixture rather than a message naming its cause, which is "
            "the shape this generator exists to leave behind. If a test genuinely needs this many "
            "courses, widen the band in tests/fixtures/supervision.py: `000`-`099` is available "
            "with zero padding."
        )
    return str(number)


GRAPH_COLUMN_VALUES = {
    ("course", GRAPH_COURSE_NUMBER_COLUMN): graph_course_number,
    ("section", GRAPH_SECTION_CODE_COLUMN): lambda: f"{graph_letters(1)}3WW",
}


def stored_type(column: Any) -> Any:
    """The type a column actually stores, with any `TypeDecorator` resolved away.

    A `TypeDecorator` is not an instance of the type it decorates, and dispatching
    on the declared type instead of this one is what cost E0-06 a dispute
    (`docs/MISTAKES.md` entry 13). ADR 0019 puts the naive-datetime guard on a
    column type, so decorated timestamps are expected here rather than exotic.
    """
    from sqlalchemy.types import TypeDecorator

    kind = column.type
    while isinstance(kind, TypeDecorator):
        kind = kind.impl_instance
    return kind


def invented_value(table: Any, column: Any) -> Any:
    """Something a NOT NULL column of unknown purpose will accept.

    Deliberately dumb about meaning and careful about type. A column this cannot
    answer for stops the test with a message naming it, rather than inserting
    `None` and failing later somewhere that reads like a schema defect.
    """
    from sqlalchemy import (
        Boolean,
        Date,
        DateTime,
        Enum,
        Integer,
        LargeBinary,
        Numeric,
        String,
        Uuid,
    )

    maker = GRAPH_COLUMN_VALUES.get((table.name, column.name))
    if maker is not None:
        return maker()

    kind = stored_type(column)
    lowered = column.name.lower()
    if isinstance(kind, Enum):
        values = list(getattr(kind, "enums", ()) or ())
        if values:
            return values[0]
    elif isinstance(kind, Uuid):
        return uuid4()
    elif isinstance(kind, Boolean):
        return False
    elif isinstance(kind, DateTime):
        for fragment, value in GRAPH_DATETIME_HINTS:
            if fragment in lowered:
                return value
        return GRAPH_WINDOW_OPENS_AT
    elif isinstance(kind, Date):
        for fragment, value in GRAPH_DATE_HINTS:
            if fragment in lowered:
                return value
        return GRAPH_TERM_START
    elif isinstance(kind, Integer):
        if any(fragment in lowered for fragment in GRAPH_LENGTH_FRAGMENTS):
            return GRAPH_LENGTH_WEEKS
        counter = _GRAPH_INTEGER_COUNTERS.setdefault((table.name, column.name), count(1))
        return 1 + (next(counter) - 1) % GRAPH_WEEK_CEILING
    elif isinstance(kind, Numeric):
        return Decimal("1")
    elif isinstance(kind, LargeBinary):
        return graph_letters(None).encode()
    elif isinstance(kind, String):
        limit = getattr(kind, "length", None)
        for fragment, maker in GRAPH_STRING_HINTS:
            if fragment in lowered:
                hint = maker()
                if limit is None or len(hint) <= limit:
                    return hint
        return graph_letters(limit)

    pytest.fail(
        f"The seeding helper in tests/fixtures/supervision.py cannot invent a value for "
        f"`{table.name}.{column.name}`, which is NOT NULL, has no default, and is of type "
        f"{column.type!r}. That "
        "is this fixture needing a case added, not a defect in the schema — add the type to "
        "`invented_value`."
    )


# The two SQLSTATEs a database that is behind `Base.metadata` answers a seed with:
# `42703` undefined_column and `42P01` undefined_table. Deliberately these two and
# not "any `DatabaseError`" — a constraint violation is the *subject* of a good
# many callers here, which pass a write to `SupervisionGraph.refusal` precisely to
# be told it was refused, and swallowing one of those would turn a real assertion
# into a message about the schema.
SCHEMA_IS_BEHIND_THE_MODELS = ("42703", "42P01")


def sqlstate_of(failure: BaseException) -> str | None:
    """The SQLSTATE a driver exception carries, under either driver's spelling.

    psycopg 3 spells it `sqlstate` and psycopg 2 spells it `pgcode`; this project
    pins the first (`tests/unit/test_psycopg_driver_pinned.py`) and reading both
    costs one line rather than a future afternoon.
    """
    original = getattr(failure, "orig", failure)
    for attribute in ("sqlstate", "pgcode"):
        code = getattr(original, attribute, None)
        if isinstance(code, str):
            return code
    return None


def require_table(tables: dict[str, Any], name: str) -> Any:
    """The table called `name`, or a failure saying it is not there."""
    table = tables.get(name)
    if table is None:
        pytest.fail(
            f"There is no `{name}` table (what is there: {sorted(tables)}). E0-09 creates "
            f"{list(E0_09_TABLES)} and E0-05 creates {list(CONTAINMENT_ORDER)}; the existence "
            "tests are the assertion for that, and everything else needs the table first."
        )
    return table


def require_column(table: Any, candidates: tuple[str, ...]) -> str:
    """The first of `candidates` that `table` has, or a failure listing both sides."""
    for candidate in candidates:
        if candidate in table.c:
            return candidate
    present = [column.name for column in table.columns]
    pytest.fail(
        f"`{table.name}` has none of the columns {list(candidates)} — it has {present}. The "
        "candidate list is a constant in tests/fixtures/supervision.py, so a deliberate rename is "
        "a one-line change there."
    )


def single_primary_key(table: Any) -> str:
    """The name of `table`'s one primary key column.

    One, because [ADR 0016](../../docs/adr/0016-primary-keys-are-database-generated-uuids.md)
    makes every primary key here a single server-generated uuid.
    """
    columns = list(table.primary_key.columns)
    if len(columns) != 1:
        pytest.fail(
            f"`{table.name}` has {len(columns)} primary key columns "
            f"({[column.name for column in columns]}). ADR 0016 makes every primary key one uuid "
            "with a server default, and these fixtures address rows by it."
        )
    return columns[0].name


def foreign_key_columns(table: Any, target: str) -> list[str]:
    """Every column on `table` whose foreign key points at `target`, sorted.

    Found by following the key rather than by guessing a name, so a reference
    spelled any way at all is picked up — which is the whole mechanism behind
    E0-09's first criterion.
    """
    return sorted(
        {key.parent.name for key in table.foreign_keys if key.column.table.name == target}
    )


# The tables the schema permits at most one row in. `institution` is the only one
# and SPEC §8 is why: a deployment serves one institution, held by
# `uq_institution_one_row` since E0-22. It matters here because every containment
# chain these fixtures build ends at an institution, so a test that builds two
# chains in one transaction used to write two institution rows without meaning
# to — and now the second insert is refused, in a test about something else
# entirely. `chain_row` below reuses the row that is already there.
#
# **Hand-maintained, and nothing checks it against the schema** — PR #54's
# security review raised that (F4) and it is deliberately left as it is while the
# list has one correct entry. A second name added here makes every chain share a
# row at that level, which is the vacuity `chain_row`'s own docstring warns
# about, and the four modules below carrying their own copy of `seed_row` do not
# read this list at all: they spell `"institution"` inline. **Done when** a
# second table needs single-row treatment: derive this list from the single-row
# constraints the schema carries, or assert it against them, and make the four
# copies read it rather than a literal.
SINGLE_ROW_TABLES = ("institution",)


def chain_row(session: Any, tables: dict[str, Any], name: str, chain: dict[str, Any]) -> Any:
    """The row a chain needs at one level: the one already there, or a new one.

    "Already there" is asked only of `SINGLE_ROW_TABLES`. Everywhere else a new
    row is what a fresh chain means — two chains are two departments, and a
    helper that quietly shared one would make a test about two departments a test
    about one.
    """
    if name in SINGLE_ROW_TABLES:
        table = require_table(tables, name)
        existing = session.execute(table.select().limit(1)).mappings().one_or_none()
        if existing is not None:
            return existing
    return seed_row(session, tables, name, chain)


def seed_row(
    session: Any,
    tables: dict[str, Any],
    name: str,
    chain: dict[str, Any] | None = None,
    /,
    **overrides: Any,
) -> Any:
    """Insert one row into `name`, building whatever ancestors it requires.

    **The four parameters are positional-only**, and the `/` is load-bearing:
    `name` is also the name of a column on four of this schema's tables, so
    without it `seed_row(session, tables, "institution", name="…")` is a
    `TypeError` about two values for one argument rather than a row with the
    name the caller asked for. Every call site already passes these four
    positionally.

    `chain` is the set of ancestor rows built so far, keyed by table name, so a
    caller can put two rows under one parent by passing the same chain and two
    rows under different parents by passing different ones.

    Columns are filled only where the schema requires it: anything generated,
    defaulted or nullable is left to the database, which matters because every
    primary key is a server-defaulted `gen_random_uuid()` (ADR 0016) and has to
    be read back with RETURNING rather than predicted. An override is honoured
    even when it is `None`, so a test can write a null and let the database
    accept or refuse it.

    **The database this is pointed at has to be at head**, and that is a property
    of this helper rather than of any one migration. The insert is built from
    `Base.metadata` and the `RETURNING` clause names *every* column that metadata
    declares — whether or not the insert supplied it, and whatever its default is.
    So the moment any revision adds a column to a table this seeds, seeding into a
    database standing before that revision fails: on the `RETURNING` clause if the
    new column is defaulted, and on the insert itself if it is not. No definition
    of the new column avoids it and no choice of column is safe, which is why the
    rule is stated here rather than worked around wherever it next fires.

    That is exactly how it did fire (`docs/disputes/E1-10-01.md`). E0-11's
    migration test seeded through this helper into a database standing at E0-11's
    own revision, said in its own prose that doing so "keeps their columns the ones
    today's models declare", and stayed true for eight revisions — until E1-10
    added `course.title_is_fallback` and two tests about a trigger went red inside
    their own fixture. `docs/MISTAKES.md` entry 22 is the shape: a later ticket's
    legitimate change makes an earlier ticket's tests unrunnable, and the repair is
    on the other side of the test wall. A test whose subject *is* an older revision
    seeds at head and walks the database back down afterwards, which is what that
    module does now.

    The failure below is what turns the next occurrence into a message naming the
    cause. Without it the symptom is `UndefinedColumn` raised inside whichever
    control happened to seed first, which reads as a broken schema rather than as
    this helper being pointed somewhere it cannot go.
    """
    from sqlalchemy.exc import DatabaseError

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
            ordered = sorted(column.foreign_keys, key=lambda fk: str(fk.target_fullname))
            target = ordered[0].column
            if target.table.name not in chain:
                chain[target.table.name] = chain_row(session, tables, target.table.name, chain)
            values[column.name] = chain[target.table.name][target.name]
            continue
        if column.nullable:
            continue
        values[column.name] = invented_value(table, column)

    statement = table.insert().values(**values).returning(*table.columns)
    try:
        inserted = session.execute(statement).mappings().one()
    except DatabaseError as failure:
        if sqlstate_of(failure) not in SCHEMA_IS_BEHIND_THE_MODELS:
            raise
        pytest.fail(
            f"Seeding `{name}` failed because the database does not have something "
            f"`Base.metadata` declares: {failure}\n\n"
            "That is this helper being pointed at a database that is not at head, rather than a "
            "defect in the row or in the schema. The insert and its `RETURNING` clause are both "
            "built from the declared table, so every column today's models carry has to exist "
            "wherever this seeds — see this function's docstring, and "
            "`docs/disputes/E1-10-01.md` for the occasion it was written on.\n\n"
            "Two honest answers. If the test's subject is an older revision, seed while the "
            "database is at head and downgrade afterwards, the way "
            "`tests/integration/test_the_upgrade_refuses_a_stored_edge_that_does_not_climb.py` "
            "does. If the database is meant to be at head, then a model declares something no "
            "migration creates, which is drift — `alembic check` and "
            "`tests/integration/test_alembic_baseline.py` are where that is diagnosed."
        )
    chain.setdefault(name, inserted)
    return inserted


class SupervisionGraph:
    """E0-09's assignment graph, built without naming what a scope is made of.

    **What it decides and what it refuses to.** The ticket spells four columns on
    `role_assignment` — `person_id`, `role`, `scope_node_id`, `reports_to` — and
    two table names, and that is all it spells. (SPEC §8 has since been corrected
    to describe the five per-level columns that were actually built; the ticket
    text this fixture was written against is quoted as written.) So the role column, the person
    link and the parent edge are each found here by following a foreign key or by
    a candidate list at the top of this file, and a role's spelling is matched
    against whatever the column enumerates rather than asserted to be a
    particular string.

    **The one thing it cannot find on its own is what a scope node is.** SPEC
    §2.1's containment hierarchy is six separate tables — E0-05 built them that
    way — and there is no single `org_node` table for a `scope_node_id` to
    reference, so "an assignment is scoped to a department" has several
    reasonable schema shapes. Three are supported here:

      - **per-kind foreign keys** — one nullable reference per containment level,
        with the role grain rule expressed as a `CHECK` over which one is
        populated;
      - **a kind column beside the id** — `scope_node_kind` plus an untyped
        `scope_node_id`, which is what the singular name in the ticket suggests;
      - **the id alone**, with the kind implied by the role. Supported because it
        is the reading the singular name suggests most directly, and because
        failing here would stop every test in the suite inside its fixture — but
        it is a shape with nothing for the role grain rule to be enforced by, so
        the role grain tests go red against it. That is criterion 6 reporting
        itself, not this fixture objecting to a design.

    A schema that introduces a unified node table is a fourth shape and a good
    answer, and this fixture cannot seed a node in it without knowing how a node
    of a given kind is spelled there. That failure names itself.

    **Nothing here asserts anything.** Every method either returns a row or fails
    with a message saying which part of the ticket it could not express; the
    assertions live in the test modules, so that a red test and a broken fixture
    are never reported as the same thing.
    """

    def __init__(self, session: Any, tables: dict[str, Any]) -> None:
        self.session = session
        self.tables = tables
        self._chain: dict[str, Any] = {}

    # -- reaching the tables and the columns the ticket names ---------------

    @property
    def assignments(self) -> Any:
        return require_table(self.tables, ROLE_ASSIGNMENT_TABLE)

    @property
    def mappings(self) -> Any:
        return require_table(self.tables, LEAD_FACULTY_MAPPING_TABLE)

    @property
    def assignment_key(self) -> str:
        return single_primary_key(self.assignments)

    @property
    def role_column(self) -> str:
        return require_column(self.assignments, ROLE_COLUMN_CANDIDATES)

    @property
    def person_column(self) -> str:
        """The column carrying `person_id`, found by following the key.

        Found rather than named because the criterion this serves is about where
        the key *points*: SPEC §2.1 computes purview from the Pulse-owned people
        graph, and an assignment keyed to `user` cannot describe a dean who has
        never launched the tool (ADR 0024).
        """
        found = foreign_key_columns(self.assignments, "person")
        if len(found) == 1:
            return found[0]
        referenced = sorted({key.column.table.name for key in self.assignments.foreign_keys})
        pytest.fail(
            f"`{ROLE_ASSIGNMENT_TABLE}` has {len(found)} foreign keys to `person` ({found}); it "
            f"references {referenced}. E0-09 and SPEC §8 both give an assignment a `person_id`, "
            "and every fixture here needs to know which person holds an assignment."
        )

    @property
    def reports_to_column(self) -> str:
        """The parent edge, preferring the column whose key is self-referential.

        The preference is the point. A `reports_to` that references `person` or an
        org table is the defect criterion 1 exists to stop, and looking for the
        self-reference first means the fixture keeps working while the criterion
        test reports it — rather than every test in the module failing at once
        with a message about a column name.
        """
        self_referential = foreign_key_columns(self.assignments, ROLE_ASSIGNMENT_TABLE)
        if len(self_referential) == 1:
            return self_referential[0]
        if len(self_referential) > 1:
            pytest.fail(
                f"`{ROLE_ASSIGNMENT_TABLE}` references itself from more than one column "
                f"({self_referential}), so there is no single answer to which one is the "
                "supervision edge."
            )
        return require_column(self.assignments, REPORTS_TO_CANDIDATES)

    # -- roles --------------------------------------------------------------

    def role_value(self, token: str) -> Any:
        """The value the `role` column uses for `token`.

        Read off the column's own enumeration where there is one, so the enum's
        spelling stays the implementer's decision. A plain string column gets the
        first alias, which is the spelling SPEC §2.1 uses.
        """
        aliases = ROLE_ALIASES[token]
        values = list(getattr(stored_type(self.assignments.c[self.role_column]), "enums", ()) or ())
        if not values:
            return aliases[0]
        for alias in aliases:
            for value in values:
                if value.upper() == alias:
                    return value
        pytest.fail(
            f"The `{self.role_column}` column enumerates {values}, none of which is any of "
            f"{list(aliases)}. SPEC §2.1's canonical chain spells INSTRUCTOR, LEAD_FACULTY, "
            "CHAIR, DEAN and VP_ACADEMICS, and E0-09 spells CARE; if this role is genuinely "
            "spelled some other way, add it to `ROLE_ALIASES` in tests/fixtures/supervision.py."
        )

    # -- scope nodes --------------------------------------------------------

    def scope_shape(self) -> tuple[str, Any]:
        """How this schema says which node an assignment is scoped to."""
        per_kind = {}
        for kind in CONTAINMENT_ORDER:
            columns = foreign_key_columns(self.assignments, kind)
            if len(columns) == 1:
                per_kind[kind] = columns[0]
        if len(per_kind) >= 2:
            return "per_kind", per_kind

        columns = self.assignments.c
        kind_column = next((name for name in SCOPE_KIND_CANDIDATES if name in columns), None)
        id_column = next((name for name in SCOPE_ID_CANDIDATES if name in columns), None)
        if kind_column is not None and id_column is not None:
            elsewhere = sorted(
                {
                    key.column.table.name
                    for key in columns[id_column].foreign_keys
                    if key.column.table.name not in CONTAINMENT_ORDER
                }
            )
            if elsewhere:
                pytest.fail(
                    f"`{ROLE_ASSIGNMENT_TABLE}.{id_column}` references {elsewhere}, which is not "
                    "one of SPEC §2.1's containment tables. That reads as a unified node table, "
                    "which is a good answer to what a singular `scope_node_id` points at and is "
                    "the one shape this fixture cannot build a node in: it would have to know how "
                    f"a node of a given kind is spelled in {elsewhere}. Say so in the pull "
                    "request and teach `scope_overrides` in tests/fixtures/supervision.py how to "
                    "seed one."
                )
            return "kind_and_id", (kind_column, id_column)

        if id_column is not None:
            # An id and nothing else: the kind is implied by the role. Handled
            # rather than refused, because it is the shape the singular
            # `scope_node_id` most naturally suggests, and because refusing it
            # here would stop every test in the suite inside its fixture. What it
            # cannot do is *enforce* the role grain — there is nothing for a
            # foreign key or a check to compare against — so the role grain tests
            # go red against it, which is criterion 6 reporting itself rather than
            # this fixture reporting a shape it dislikes.
            return "id_only", id_column

        pytest.fail(
            f"This fixture cannot tell how `{ROLE_ASSIGNMENT_TABLE}` records the node an "
            f"assignment is scoped to. Its columns are "
            f"{[column.name for column in self.assignments.columns]}, and it references "
            f"{sorted({key.column.table.name for key in self.assignments.foreign_keys})}. E0-09 "
            "wrote `scope_node_id` in the singular — SPEC §8 did too until it was corrected on "
            "2026-08-18 to describe the five per-level columns — but E0-05 built the "
            "containment hierarchy as six separate tables and no ticket says what a single "
            "`scope_node_id` points at. Three shapes are supported — one nullable foreign key per "
            "containment level, a kind column beside an untyped id, or the id alone with the kind "
            "implied by the role — and a fourth (a unified node table) needs this fixture to be "
            "told how a node of a given kind is spelled there. That is a question for the ticket, "
            "not something to guess at here."
        )

    def scope_kind_value(self, kind: str) -> Any:
        """How the kind column spells `kind`, read off its enumeration where there is one."""
        shape, detail = self.scope_shape()
        if shape != "kind_and_id":
            return kind
        kind_column = detail[0]
        values = list(getattr(stored_type(self.assignments.c[kind_column]), "enums", ()) or ())
        if not values:
            return kind
        for value in values:
            if value.upper() == kind.upper():
                return value
        pytest.fail(
            f"`{kind_column}` enumerates {values}, none of which is {kind!r}. The six containment "
            f"levels are {list(CONTAINMENT_ORDER)} (SPEC §2.1), and a scope kind that cannot name "
            "one of them cannot express the role grain rule."
        )

    def can_express(self, kind: str) -> bool:
        """Can this schema even say "scoped to a node of this kind"?

        It answers no only under the per-kind shape, when there is no column for
        that level — a schema with `department_id` and no `prefix_id` cannot
        record a chair scoped to a prefix at all. That is the *strongest* form of
        the role grain rule rather than a gap in it, so the tests that expect a
        wrong pairing to be refused ask this first and count unrepresentable as
        refused. They say so in their message; nothing here decides it silently.
        """
        shape, detail = self.scope_shape()
        return kind in detail if shape == "per_kind" else True

    def scope_overrides(self, kind: str, key: Any) -> dict[str, Any]:
        """The column values that say "scoped to this node of this kind"."""
        shape, detail = self.scope_shape()
        if shape == "per_kind":
            if kind not in detail:
                pytest.fail(
                    f"`{ROLE_ASSIGNMENT_TABLE}` carries a scope reference for {sorted(detail)} and "
                    f"none for `{kind}`, so an assignment scoped to a {kind} is unwritable. E0-09's "
                    "role grain rule is about refusing the wrong kind, not about being unable to "
                    "spell it — a schema where the wrong scope cannot be expressed at all makes "
                    "the criterion untestable rather than satisfied."
                )
            return {detail[kind]: key}
        if shape == "id_only":
            return {detail: key}
        kind_column, id_column = detail
        return {kind_column: self.scope_kind_value(kind), id_column: key}

    def scope(self, kind: str) -> Any:
        """The key of the shared node of `kind`, seeding the containment chain once.

        Shared on purpose: `scope("section")` and `scope("course")` answer for a
        section and the course that holds it, so a fixture built out of these
        calls is one coherent hierarchy rather than six unrelated rows.
        """
        table = require_table(self.tables, kind)
        if kind not in self._chain:
            self._chain[kind] = chain_row(self.session, self.tables, kind, self._chain)
        return self._chain[kind][single_primary_key(table)]

    def new_branch(self, *keep: str) -> dict[str, Any]:
        """A fresh chain sharing only the named ancestors with the shared one."""
        return {name: row for name, row in self._chain.items() if name in keep}

    def fresh_scope(self, kind: str) -> Any:
        """A second node of `kind` under the same ancestors as the shared one.

        This is what makes a sibling: two departments in one college, two courses
        under one prefix. Everything strictly above `kind` in SPEC §2.1's
        containment order is kept, everything at or below it is built again.
        `term` is always kept, since a second section in a second term would be
        a different comparison entirely.

        **An institution is never duplicated**, and since E0-22 that is the
        schema's rule rather than this fixture's caution. It used to read as a
        refusal to answer an open spec question — whether a deployment holds one
        institution or many — and to predict that every test built on this would
        fail inside its own seeding the day the answer was "one". The answer is
        "one" (SPEC §8), `uq_institution_one_row` holds it, and the prediction was
        right: `chain_row` is what keeps those tests seeding, by handing back the
        institution that is already there. Institution-scoped roles share the one
        node.
        """
        if kind not in CONTAINMENT_ORDER:
            pytest.fail(f"{kind!r} is not one of SPEC §2.1's containment levels.")
        if kind == "institution":
            return self.scope(kind)
        keep = (*CONTAINMENT_ORDER[: CONTAINMENT_ORDER.index(kind)], "term")
        branch = self.new_branch(*keep)
        row = seed_row(self.session, self.tables, kind, branch)
        return row[single_primary_key(require_table(self.tables, kind))]

    def key_of(self, table_name: str, row: Any) -> Any:
        """The primary key value of a row from `table_name`."""
        return row[single_primary_key(require_table(self.tables, table_name))]

    # -- people and assignments ---------------------------------------------

    def person(self) -> Any:
        """One new `person` row, with no user linked (ADR 0024: the link is nullable)."""
        row = seed_row(self.session, self.tables, "person", {})
        return self.key_of("person", row)

    def assign(
        self,
        role: str,
        *,
        scope_kind: str | None = None,
        scope: Any = None,
        person: Any = None,
        reports_to: Any = UNSET,
        **overrides: Any,
    ) -> Any:
        """One `role_assignment` row, returned as the inserted mapping.

        `scope_kind` defaults to the kind SPEC §2.1 gives the role, so a test that
        wants a *wrong* kind has to say so — which keeps the role grain criterion
        an assertion rather than a default. `reports_to` is left out of the insert
        entirely unless it is passed, so a schema that defaults it is not
        overridden, and passing `None` writes an explicit null.
        """
        kind = scope_kind or ROLE_SCOPE_GRAIN[role]
        key = self.scope(kind) if scope is None else scope
        values: dict[str, Any] = {
            self.role_column: self.role_value(role),
            self.person_column: self.person() if person is None else person,
            **self.scope_overrides(kind, key),
        }
        if reports_to is not UNSET:
            values[self.reports_to_column] = reports_to
        values.update(overrides)
        return seed_row(
            self.session, self.tables, ROLE_ASSIGNMENT_TABLE, dict(self._chain), **values
        )

    def node(self, role: str, *, reports_to: Any = UNSET) -> Any:
        """An assignment sharing nothing with any other: its own person, its own scope node.

        Used where a test is about the *graph* and not about the rows — the
        generated-graph properties, and the long legal chains. Sharing nothing
        means no uniqueness rule this ticket does not mention (one chair per
        department, one instructor per section) can refuse a row and be read as
        the cycle guard firing.
        """
        return self.assign(
            role,
            scope=self.fresh_scope(ROLE_SCOPE_GRAIN[role]),
            person=self.person(),
            reports_to=reports_to,
        )

    def repoint(self, row: Any, parent: Any) -> None:
        """Point an existing assignment's `reports_to` at `parent` (or at `None`)."""
        table = self.assignments
        key = self.assignment_key
        self.session.execute(
            table.update()
            .where(table.c[key] == row[key])
            .values(**{self.reports_to_column: parent})
        )

    def parent_of(self, assignment_id: Any) -> Any:
        """The stored `reports_to` of one assignment, read back out of the database."""
        from sqlalchemy import select

        table = self.assignments
        return self.session.execute(
            select(table.c[self.reports_to_column]).where(
                table.c[self.assignment_key] == assignment_id
            )
        ).scalar_one()

    def assignments_of(self, person_id: Any) -> list[Any]:
        """Every assignment id one person holds, read back out of the database.

        Read back rather than collected as the rows are written, because the
        question a two-hat test asks is whether the schema kept two rows — and a
        list built in Python holds two either way.
        """
        from sqlalchemy import select

        table = self.assignments
        return list(
            self.session.execute(
                select(table.c[self.assignment_key]).where(table.c[self.person_column] == person_id)
            ).scalars()
        )

    def ancestors(self, assignment_id: Any, limit: int = 64) -> list[Any]:
        """Every assignment reachable by walking `reports_to` upwards, nearest first.

        Bounded, so that a schema which accepted a cycle produces a failed
        assertion in the test that asked rather than a hang in the fixture.
        """
        found: list[Any] = []
        current = self.parent_of(assignment_id)
        while current is not None and len(found) < limit:
            found.append(current)
            current = self.parent_of(current)
        return found

    def lead_mapping(self, *, person: Any = None, course: Any = None) -> Any:
        """One `lead_faculty_mapping` row, both links found by following keys."""
        table = self.mappings
        person_columns = foreign_key_columns(table, "person")
        course_columns = foreign_key_columns(table, "course")
        if len(person_columns) != 1 or len(course_columns) != 1:
            pytest.fail(
                f"`{LEAD_FACULTY_MAPPING_TABLE}` has {person_columns} referencing `person` and "
                f"{course_columns} referencing `course`. E0-09: it 'maps a person to courses they "
                "lead, one lead per course'; SPEC §2.1 calls it 'a mapping of individuals to the "
                "courses they lead'. One of each is what that sentence describes."
            )
        values = {
            person_columns[0]: self.person() if person is None else person,
            course_columns[0]: self.scope("course") if course is None else course,
        }
        return seed_row(
            self.session, self.tables, LEAD_FACULTY_MAPPING_TABLE, dict(self._chain), **values
        )

    # -- attempting a write, and finding out whether it was refused ---------

    def refusal(self, action: Any) -> Any:
        """Run `action`; answer the database error it provoked, or `None`.

        Two things this does that a bare `pytest.raises` does not.

        **It forces any deferred check.** A cycle guard written as a deferrable
        constraint trigger — which is the shape that survives a transaction
        reorganising a subtree — does not fire until commit, and nothing in this
        suite commits. `SET CONSTRAINTS ALL IMMEDIATE` makes the deferred and the
        immediate designs answer at the same moment, so this fixture does not
        quietly decide which one the implementer must pick.

        **It keeps the rows when the write succeeds.** Every control row a test
        writes before the row that must be refused goes in through the same path,
        so a refusal is known to be about the row under test rather than about the
        insert path not working (`docs/MISTAKES.md` entry 3).
        """
        from sqlalchemy import text
        from sqlalchemy.exc import DatabaseError

        savepoint = self.session.begin_nested()
        try:
            action()
            self.session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        except DatabaseError as refused:
            savepoint.rollback()
            return refused
        savepoint.commit()
        return None

    # -- the two shapes the ticket asks to be constructible ------------------

    def assistant_dean_shape(self) -> dict[str, Any]:
        """SPEC §2.1's worked example, as rows.

        "Own led courses  union  every supervised chair's department — a set no single
        containment node holds." So the assistant dean's own led course sits in a
        *third* department, whose chair reports straight to the dean: without
        that, the college node would hold the whole purview and the example would
        not be the example.

        The assistant dean is scoped to the college, the same node as the dean
        (§2.1: "authority comes from the supervision graph, not the scope").
        Computing the purview over this shape is E9's; constructing it is E0-09's
        last criterion.
        """
        college = self.scope("college")
        supervised_department = self.scope("department")

        second = self.new_branch("institution", "college", "term")
        seed_row(self.session, self.tables, "course", second)
        third = self.new_branch("institution", "college", "term")
        led_course_row = seed_row(self.session, self.tables, "course", third)

        assistant_dean_person = self.person()
        dean = self.assign("DEAN", scope=college)
        assistant_dean = self.assign(
            "ASSISTANT_DEAN",
            scope=college,
            person=assistant_dean_person,
            reports_to=dean[self.assignment_key],
        )
        supervised_chairs = [
            self.assign(
                "CHAIR",
                scope=supervised_department,
                reports_to=assistant_dean[self.assignment_key],
            ),
            self.assign(
                "CHAIR",
                scope=self.key_of("department", second["department"]),
                reports_to=assistant_dean[self.assignment_key],
            ),
        ]
        unsupervised_chair = self.assign(
            "CHAIR",
            scope=self.key_of("department", third["department"]),
            reports_to=dean[self.assignment_key],
        )
        led_course = self.key_of("course", led_course_row)
        lead = self.assign(
            "LEAD_FACULTY",
            scope=led_course,
            person=assistant_dean_person,
            reports_to=unsupervised_chair[self.assignment_key],
        )
        self.lead_mapping(person=assistant_dean_person, course=led_course)

        return {
            "college": college,
            "dean": dean,
            "assistant_dean": assistant_dean,
            "assistant_dean_person": assistant_dean_person,
            "supervised_chairs": supervised_chairs,
            "supervised_departments": [
                supervised_department,
                self.key_of("department", second["department"]),
            ],
            "unsupervised_chair": unsupervised_chair,
            "unsupervised_department": self.key_of("department", third["department"]),
            "lead": lead,
            "led_course": led_course,
        }

    def care_and_instructor_person(self) -> dict[str, Any]:
        """E0-09 criterion 9's fixture: one person, a Care hat and a teaching hat.

        Named by the ticket as reused by E0-10 and E0-18, which is why it is here
        rather than in a test module. The instructor assignment carries a
        `reports_to` and the Care assignment does not — §2.1 puts Care outside the
        supervision graph entirely — so the row shape says the thing the ticket
        says: it is capabilities that do not compose, not people.
        """
        person = self.person()
        lead = self.assign("LEAD_FACULTY", scope=self.scope("course"))
        instructor = self.assign(
            "INSTRUCTOR",
            scope=self.scope("section"),
            person=person,
            reports_to=lead[self.assignment_key],
        )
        care = self.assign("CARE", scope=self.scope("institution"), person=person, reports_to=None)
        return {"person": person, "care": care, "instructor": instructor, "lead": lead}


@pytest.fixture(scope="session")
def metadata_tables(migrated_database: DatabaseUnderTest) -> dict[str, Any]:
    """`Base.metadata`, with every model module registered on it.

    Reached through `app.models` and not through the module a ticket names, for
    the reason `tests/unit/test_identity_models_registered.py` gives at length:
    `migrations/env.py` imports the package, and a module nobody imported is on
    no metadata. `Base` comes from `app.models.base` rather than from `app.db`,
    which builds an engine out of `Settings()` at import.

    Declared rather than reflected, because writes go through it: a column
    protected by a `TypeDecorator` is bypassed by a write through a reflected
    table. `migrated_database` is depended on and not used — it is what
    guarantees the migration has run before anything inserts.
    """
    try:
        importlib.import_module("app.models")
        base_module = importlib.import_module("app.models.base")
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


@pytest.fixture
def seed_rows(db_session: Any, metadata_tables: dict[str, Any]) -> Callable[..., Any]:
    """`seed_row` bound to the session whose writes are rolled back after the test.

    E0-10 is what needs it. Every assertion about its Care reveal is about a
    **particular** identity — that the function returned the name that was seeded,
    not that it returned something — and over an unseeded database each of them is
    satisfied by a function that reveals nobody (`docs/MISTAKES.md` entry 3).
    `SupervisionGraph` seeds the containment chain and assignments and nothing
    else, so the choice was a fifth private copy of the seeding helper or this;
    entry 13 says one helper, reached from both places.

    The integer counters are restarted for the same reason `supervision_graph`
    restarts them: a course number is drawn from a 700-wide band, and a counter
    that climbed across the session would eventually fail somebody else's test
    inside its own seeding.
    """
    _GRAPH_INTEGER_COUNTERS.clear()

    def seed(name: str, chain: dict[str, Any] | None = None, **overrides: Any) -> Any:
        return seed_row(db_session, metadata_tables, name, chain, **overrides)

    return seed


@pytest.fixture
def supervision_graph(db_session: Any, metadata_tables: dict[str, Any]) -> SupervisionGraph:
    """E0-09's graph builder, on a session whose writes are rolled back after the test.

    The integer counters are restarted per test, and two things now depend on it.
    An ordinal the seeding helper invents has to land inside an 18-week term
    rather than at 47; and `graph_course_number` draws from the same dict, so the
    restart is what keeps its 700 numbers a per-test budget rather than a
    session-wide one. Without the restart both climb across the session and
    eventually fail a later test inside its own seeding, for a reason that test is
    not about.
    """
    _GRAPH_INTEGER_COUNTERS.clear()
    return SupervisionGraph(db_session, metadata_tables)


@pytest.fixture
def supervision_graph_on(
    metadata_tables: dict[str, Any],
) -> Callable[[Any], SupervisionGraph]:
    """The same builder, on a session and a database the caller opened for itself.

    `supervision_graph` above and `committed_rows` below both bind the builder to
    the session database. E0-11 needs the same rows in a database of its own — one
    it can migrate up and down without touching the session's — and that is
    `empty_database`'s, on a connection the test opens and closes around each
    migration step. The choice was a fifth private copy of the builder or this
    (`docs/MISTAKES.md` entry 13), and the copy is the one nobody updates.

    **It still only seeds a database at head**, and this is the sentence that used
    to say otherwise. It read that E0-11 "needs the same rows in a database
    standing at an **earlier** revision", and that is not something this fixture
    can do: `seed_row` writes through `Base.metadata` and reads back every column
    that metadata declares, so a database standing before any revision that added
    one is a database it cannot write to. The rows and the migration step are
    separable, which is what makes the rule affordable — E0-11's module seeds while
    its database is at head and downgrades afterwards, and the revision under test
    is reached by upgrading into it, which is the step every assertion there is
    about. `docs/disputes/E1-10-01.md` is the occasion this was found on, and
    `seed_row` fails with the reason if a caller tries it anyway.

    The counters are cleared once per test rather than once per call, because a
    test that opens three sessions against one database is still one test's budget
    of course numbers — clearing per call would hand out `100` twice under the
    same prefix and fail E0-05's uniqueness rule inside the fixture.
    """
    _GRAPH_INTEGER_COUNTERS.clear()

    def build(session: Any) -> SupervisionGraph:
        return SupervisionGraph(session, metadata_tables)

    return build
