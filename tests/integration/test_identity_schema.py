"""Identity is split from the user key, and the windows are enforced — ticket E0-08.

Acceptance criteria 1, 2, 3, 4, 5 and 7, plus the three scope claims that would
otherwise ship with nothing asserting them (`docs/MISTAKES.md` entry 2): one
identity row per user, a nullable and explicit person-to-user link, and an
enrollment that links a user to a section. Criterion 6 — the marker convention —
is in `tests/integration/test_identity_column_marker.py`, on its own, because it
is the tripwire E0-10 and every later confidentiality test depend on and its
failure should name itself.

The whole ticket is schema, so almost all of it needs a real server, for the
reason E0-05 and E0-06 both give: a constraint that lives in the application is
exactly what SPEC §8 refuses, and the only way to tell the two apart is to ask
the database.

**Criterion 1's second half is not repeated here.** "`alembic check` is clean" is
already asserted by `tests/integration/test_alembic_baseline.py`, which runs
`command.check` against a freshly upgraded database; E0-08's migration lands in
that same chain, so that test starts covering it the moment this one does.
Duplicating it would give two failures for one defect.

**Two views of the schema, used for different questions.**

  - **Reflected** — what Postgres holds, read through the inspector. Used for the
    existence criterion, for criterion 3, and for the half of criterion 4 that is
    about the table rather than about what it accepts. Criterion 3 says a test
    must assert the split "so the split cannot erode", and a model attribute list
    is the wrong side to read: a column that exists in the database and not in
    the model is invisible there, and the erosion this guards against is a table
    being rewritten in a later migration.
  - **Declared** — `Base.metadata`, reached through `app.models`. Used for every
    write, following E0-06's precedent. It matters most for criterion 7: if a
    client secret is protected by a `TypeDecorator` that encrypts on the way in,
    writing through a reflected table would bypass the decorator and store the
    sentinel in plaintext, failing a correct implementation.

**One column name in this file is a guess and is marked as one**, following the
precedent `tests/conftest.py` sets and the correction E0-05 went through: the LMS
user ID on `user`. E0-08 names the facts and not the columns, so it is a named
constant with a candidate list, a deliberate rename is a one-line change here, and
the failure prints both sides.

**The two ends of the enrollment window were the other two, and are not guesses
any more.** E0-08 left their meaning open and named the ticket that would settle
it; E1-11 settled it (ADR 0095), so `ENROLLMENT_START_COLUMN` and
`ENROLLMENT_END_COLUMN` name `started_on` and `ended_on` outright and the fragment
lists that hedged the question have gone. The constants carry why, and it is not
tidying: the same ticket adds a *second* dated pair that no constraint here ranges
over, so inference now has two candidates and no way to choose (dispute E1-11-03).

Everything else is reached without a name at all:
the platform reference, the user and section links, and the person link are found
by following foreign keys.

**Why there is a row-seeding helper rather than literal INSERTs.** An enrollment
sits at the bottom of two chains — a section under a course under a prefix under
a department, and a user under an LTI platform — and almost none of the columns
on the way are named by this ticket. `seed_row` walks the table, fills what the
schema requires, and follows foreign keys to build whatever ancestors are
missing. A failure raised from inside it means the schema needs a value it cannot
invent: that is a broken test rather than a red one, and its message says so and
names the column. It is a third copy of the helper E0-05 and E0-06 each carry;
the three have diverged only in the values they invent, and merging them is a
refactor that would have to edit two other tickets' modules.
"""

import base64
import re
import string
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from importlib import import_module
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
    LargeBinary,
    Numeric,
    String,
    Table,
    Text,
    Uuid,
    cast,
    inspect,
    select,
)
from sqlalchemy.exc import DatabaseError
from sqlalchemy.types import TypeDecorator

pytestmark = pytest.mark.integration

# The tables E0-08's scope names. SPEC §8 lists all six among the core tables.
IDENTITY_TABLES = ("user", "user_identity", "person", "enrollment")
LTI_TABLES = ("lti_platform", "lti_deployment")
E0_08_TABLES = IDENTITY_TABLES + LTI_TABLES

# **This file's choice.** SPEC §4 says responses are keyed to "the LMS user ID
# (`sub` from the launch)" and E0-08 says `user` "is keyed to the LMS user ID",
# but no ticket spells the column. ADR 0014 marks LMS-owned columns with an
# `lms_` prefix, which is why the prefixed spellings come first. `require_column`
# prints both sides when none of them is there.
LMS_USER_ID_COLUMNS = ("lms_user_id", "lms_sub", "lms_id", "lms_subject", "sub", "user_id")

# Two opaque `sub` values, of the shape a platform issues. Short enough to fit a
# narrow column, distinct enough that a failure message identifies which is which.
LMS_USER_ID = "sub-10000001"
OTHER_LMS_USER_ID = "sub-10000002"

# How a column name is recognised as holding a person. E0-08's criterion 3 is
# about "name or email" and the tests below keep that wording, but the tuple is
# **widened by E0-10**, whose fourth criterion is that an identity column
# containing neither word is still caught — so `sortable` and `given`, which the
# older version of this comment named as things it could not see, are now in it.
# The widened set is a superset, so it only makes the assertions below stricter;
# on today's schema it finds nothing the two original fragments did not, which
# dispute E0-10-01 measured rather than assumed.
#
# **There are three copies of this tuple in `tests/`**: here,
# `test_identity_column_marker.py` — which is where the convention is defined and
# where its blind spots are written down — and `test_role_assignment_graph.py`.
# They are copies deliberately: a test module importing a sibling test module
# works only because of where pytest puts `tests/` on `sys.path`, and a collection
# error is not a failing test (`tests/fixtures/__init__.py` says the same of the
# fixtures package: never imported by a test module).
# Change one, change all three. `login_id` and never a bare `login`, which would
# match `role_assignment.permits_web_login` and turn two other modules red.
IDENTITY_NAME_FRAGMENTS = (
    "name",
    "email",
    "login_id",
    "picture",
    "sourcedid",
    "phone",
    "sortable",
    "given",
    "family",
    "surname",
    "address",
    "photo",
    "avatar",
    "username",
)

# The enrollment window ADR 0023's constraints range over. **Named outright since
# E1-11, and no longer this file's choice.**
#
# It used to be a pair of fragment lists — `("end", "drop", "until", …)` and
# `("start", "begin", "enrol", …)` — because E0-08 said only "an enrollment window
# (start and end)" and `Enrollment`'s own docstring left the meaning open, naming
# the ticket that would settle it: "these two columns are most likely Pulse's
# record of when a student was first and last seen in the roster… E1's roster sync
# is what settles it."
#
# E1-11 settled it, and as predicted (ADR 0095, that ticket's D3): `started_on`
# and `ended_on` are Pulse's own observed record, and the platform's window arrives
# beside them as `lms_window_start` / `lms_window_end` — `lms_`-prefixed under
# E0-05's rule, because the platform owns those values. The table then held two
# dated pairs, discovery-by-fragment matched both, and the helper below could no
# longer answer (dispute E1-11-03).
#
# With the question closed there is nothing left to hedge against, and naming the
# pair is what keeps these five tests about their own subject: ADR 0023's exclusion
# and check constraints range over *these two* columns and over neither of the
# platform's, so a rule that chose its columns by shape could quietly start
# asserting the constraint against the wrong pair.
ENROLLMENT_START_COLUMN = "started_on"
ENROLLMENT_END_COLUMN = "ended_on"

# Fragments naming a stored secret on `lti_platform`, for criterion 7. Broader
# than "client secret" on purpose: the criterion is about key material at rest,
# and a column called `private_key` or `credential` carries the same risk under
# a different name.
SECRET_FRAGMENTS = ("secret", "password", "passphrase", "credential", "private_key", "privatekey")

# The column that proves `lti_platform` is a real table before an absence is
# allowed to mean anything. E0-08's scope names the client ID outright.
CLIENT_ID_FRAGMENT = "client"

# Written into the secret column and read back through raw SQL. Not a credential
# and not copied from one — it is a marker string whose only job is to be
# searched for. Deliberately not named `..._SECRET` or `..._PASSWORD`, so ruff's
# S105 keeps flagging the real thing; `tests/fixtures/database.py` made the same
# choice for the container's credentials.
PLAINTEXT_SENTINEL = "sentinel-value-9d41c7ba0e"
CLIENT_ID_SENTINEL = "client-id-4b8e0257fa"

# ---------------------------------------------------------------------------
# Values the seeding helper invents. Guesses about *values* only — nothing here
# decides that a column exists or what it is called, and nothing here is read by
# an assertion. They are chosen to be mutually consistent with the calendar
# E0-06 enforces, so that a cross-column check constraint cannot reject the
# helper's own rows and leave a test failing inside its fixture: an 18-week fall
# term running 8/17 to 12/20, and enrollment windows inside it.
# ---------------------------------------------------------------------------

TERM_START = date(2026, 8, 17)
TERM_END = date(2026, 12, 20)
DEFAULT_LENGTH_WEEKS = 18
WEEK_NUMBER_CEILING = 18

WINDOW_OPENS_AT = datetime(2026, 8, 21, 22, 0, tzinfo=UTC)
WINDOW_CLOSES_AT = datetime(2026, 8, 24, 3, 59, 59, tzinfo=UTC)

# The enrollment windows every test in the enrollment group is built from, as day
# offsets into the term. Kept well inside 8/17-12/20 so that a schema which ties
# an enrollment to its section's dates does not refuse the helper's own rows.
ENROLLMENT_BASE = TERM_START
ADDED = 0
DROPPED = 30
RE_ADDED = 45
RE_DROPPED = 75
OVERLAPPING_START = 10
OVERLAPPING_END = 40

DATE_HINTS = (("start", TERM_START), ("begin", TERM_START), ("end", TERM_END))
DATETIME_HINTS = (
    ("open", WINDOW_OPENS_AT),
    ("close", WINDOW_CLOSES_AT),
    ("end", WINDOW_CLOSES_AT),
)
LENGTH_FRAGMENTS = ("length", "weeks", "duration")

# Two well-formed section codes per SPEC §2.2's `{startLetter}{ordinal}{modality}`.
SECTION_CODE_COLUMN = "lms_section_code"
COURSE_NUMBER_COLUMN = "lms_number"

_UNIQUE = count(1)
_INTEGER_COUNTERS: dict[tuple[str, str], Any] = {}


@pytest.fixture(autouse=True)
def _restart_the_integer_counters() -> None:
    """Give each test its own small integers, so week 1 is week 1 every time.

    The counters below hand out 1, 2, 3… per column so that an ordinal the helper
    invents lands inside a term rather than at 47. They are module-level, so
    without this they would keep climbing and eventually walk out of an 18-week
    term — failing a later test inside its own seeding for a reason the test is
    not about. Copied from E0-06's module, where the same helper needed it.
    """
    _INTEGER_COUNTERS.clear()


# ---------------------------------------------------------------------------
# Reaching the schema.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def declared_tables(migrated_database: Any) -> dict[str, Table]:
    """`Base.metadata`, with every model module registered on it.

    Reached through `app.models` and not through `app.models.identity`, for the
    reason `tests/unit/test_identity_models_registered.py` gives at length:
    `migrations/env.py` imports the package, and a module nobody imported is on
    no metadata. That module is where a missing registration is diagnosed; this
    one only needs something to insert through.

    `Base` comes from `app.models.base` rather than from `app.db`, which builds
    an engine out of `Settings()` at import and would need five variables that
    have nothing to do with a schema.

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
            "through — and nothing for `migrations/env.py` to autogenerate against either."
        )
    return dict(metadata.tables)


def require_table(tables: dict[str, Table], name: str) -> Table:
    """The table called `name`, or a failure saying it is not there."""
    table = tables.get(name)
    if table is None:
        pytest.fail(
            f"There is no `{name}` table (what is there: {sorted(tables)}). E0-08 creates "
            f"{list(E0_08_TABLES)}; the existence test in this module is the assertion for that, "
            "and everything else here needs these tables before it can mean anything."
        )
    return table


def require_column(table: Table, candidates: tuple[str, ...]) -> str:
    """The first of `candidates` that `table` has, or a failure listing both sides."""
    for candidate in candidates:
        if candidate in table.c:
            return candidate
    present = [column.name for column in table.columns]
    pytest.fail(
        f"`{table.name}` has none of the columns {list(candidates)} — it has {present}. E0-08 "
        "names the fact this column holds without spelling the column, so the candidates are a "
        "constant at the top of this file and a deliberate rename is a one-line change here."
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


def foreign_key_columns(table: Table, target: str) -> list[str]:
    """Every column on `table` whose foreign key points at `target`, sorted.

    Found by following the key rather than by guessing a name, so a reference
    spelled any way at all is picked up.
    """
    return sorted(
        {key.parent.name for key in table.foreign_keys if key.column.table.name == target}
    )


def one_foreign_key_column(table: Table, target: str) -> str:
    """The single column on `table` referencing `target`, or a failure saying why not."""
    matches = foreign_key_columns(table, target)
    if not matches:
        referenced = sorted({key.column.table.name for key in table.foreign_keys})
        pytest.fail(
            f"No column on `{table.name}` references `{target}` — the table references "
            f"{referenced}. E0-08's scope gives `{table.name}` that link explicitly."
        )
    if len(matches) > 1:
        pytest.fail(
            f"`{table.name}` references `{target}` from more than one column ({matches}), so "
            "there is no single answer to which of them carries the link."
        )
    return matches[0]


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


def unique_url() -> str:
    """A URL no other seeded row will carry.

    Unique on purpose. An LTI platform is identified by its issuer (SPEC §7.3),
    so `lti_platform` plausibly carries a uniqueness rule over the issuer — and
    two platforms are exactly what the criterion about one LMS ID on two
    platforms needs. A constant issuer would fail that test inside its own
    seeding.
    """
    return f"https://{letters(6).lower()}.example.invalid"


def unique_email() -> str:
    """An address no other seeded row will carry, for the same reason as `unique_url`."""
    return f"{letters(6).lower()}@example.invalid"


# Fragments matched against a string column's name, in order. Each value is
# produced fresh per call so that a uniqueness rule on an issuer, a JWKS URL or
# an email address cannot reject the helper's second row.
STRING_HINTS = (
    ("timezone", lambda: "America/New_York"),
    ("email", unique_email),
    ("issuer", unique_url),
    ("iss", unique_url),
    ("url", unique_url),
    ("uri", unique_url),
    ("jwks", unique_url),
)

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


# Values keyed to a column that a type alone cannot answer for. Both are schema
# rules E0-05 already enforces, so a value the helper invented freely would be
# rejected by a constraint that has nothing to do with E0-08: SPEC §8's
# course-number bands, and SPEC §2.2's section-code shape. Both are drawn fresh
# per call, because both rules have a uniqueness half as well as a shape half.
COLUMN_VALUES = {
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
    """A small integer: a plausible length in weeks, or a low ordinal."""
    lowered = column_name.lower()
    if any(fragment in lowered for fragment in LENGTH_FRAGMENTS):
        return DEFAULT_LENGTH_WEEKS
    counter = _INTEGER_COUNTERS.setdefault((table_name, column_name), count(1))
    return 1 + (next(counter) - 1) % WEEK_NUMBER_CEILING


def stored_type(column: Any) -> Any:
    """The type a column actually stores, with any `TypeDecorator` resolved away.

    **The one place this module decides what a column holds**, used by the
    seeding helper, by the enrollment-window discovery and by the secret-column
    check, so the three cannot answer the question differently. When two callers
    once did, it cost E0-06 a dispute
    ([E0-06-01](../../docs/disputes/E0-06-01.md)): a `TypeDecorator` is not an
    instance of the type it decorates, so a declared guard matched nothing and
    stopped two tests inside their own fixture.

    It matters twice over here. ADR 0019 puts the naive-datetime guard on the
    column type, so an enrollment window spelled as a timestamp is very likely
    decorated; and criterion 7's most plausible implementation is a decorator
    that encrypts on the way in.
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
    elif isinstance(kind, LargeBinary):
        return letters(None).encode()
    elif isinstance(kind, String):
        limit = getattr(kind, "length", None)
        for fragment, maker in STRING_HINTS:
            if fragment in column.name.lower():
                hint = maker()
                if limit is None or len(hint) <= limit:
                    return hint
        return letters(limit)

    # `column.type` and not the unwrapped `kind`: the declared type is what a
    # reader will find in the model, and it is the string that diagnosed
    # E0-06-01.
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
    Passing one that already holds an `lti_platform` row puts the new user on
    that platform, which is how two users come to share a platform rather than
    getting one each — the difference the uniqueness criterion turns on.

    Columns are filled only where the schema requires it: anything generated,
    defaulted or nullable is left to the database — which matters here, since
    every primary key is a server-defaulted `gen_random_uuid()`
    ([ADR 0016](../../docs/adr/0016-primary-keys-are-database-generated-uuids.md))
    and has to be read back with RETURNING rather than predicted.

    An override is honoured even when it is `None`, so a test can insert a null
    into a column and let the database accept or refuse it.
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
    """A fresh chain sharing only the named ancestors with `chain`."""
    return {name: row for name, row in chain.items() if name in keep}


# ---------------------------------------------------------------------------
# The enrollment window ADR 0023 constrains, by name.
# ---------------------------------------------------------------------------


def enrollment_window_columns(enrollment: Table) -> tuple[str, str]:
    """The `(start, end)` columns ADR 0023's constraints range over.

    Named rather than discovered since E1-11 closed the question E0-08 left open;
    the constants at the top of this file carry the reasoning and the record.

    **What this refuses to do is pick the pair by shape.** `enrollment` now carries
    four dated columns, and only two of them are the window the exclusion
    constraint is written over — `lms_window_start` and `lms_window_end` are the
    platform's own values, which no constraint here ranges over and which a sync
    may leave absent entirely (SPEC §3.4, ADR 0048). A helper that went on
    inferring would have two candidate pairs to choose between and no reason to
    prefer either, and the five tests below would be asserting ADR 0023's rule
    against whichever it happened to pick.

    A failure here is a broken test rather than a red one, and it says so.
    """
    missing = [
        name
        for name in (ENROLLMENT_START_COLUMN, ENROLLMENT_END_COLUMN)
        if name not in enrollment.c
    ]
    if missing:
        pytest.fail(
            f"`enrollment` declares no {missing}; its columns are "
            f"{[column.name for column in enrollment.columns]}. E0-08 gives enrollment a window "
            "with a start and an end because E3's participation formula is enrollment-windowed, "
            "and ADR 0095 settles the pair as `started_on`/`ended_on` — Pulse's record of when a "
            "member was first and last seen by a sync, which is what ADR 0023's exclusion and "
            "check constraints range over. If that pair is genuinely renamed, it is renamed in "
            "the constants at the top of this file, in the pull request that renames it."
        )
    return ENROLLMENT_START_COLUMN, ENROLLMENT_END_COLUMN


def window_value(column: Any, offset_days: int) -> date | datetime:
    """A value `offset_days` into the term, of the type the column stores.

    A timestamp gets an aware datetime, because ADR 0019 puts a guard on the
    column type that refuses a naive one — a naive value here would fail inside
    the seeding rather than at the assertion.
    """
    day = ENROLLMENT_BASE + timedelta(days=offset_days)
    if isinstance(stored_type(column), DateTime):
        return datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)
    return day


def seed_enrollment(
    session: Any,
    tables: dict[str, Table],
    chain: dict[str, Any],
    start_offset: int,
    end_offset: int,
    **overrides: Any,
) -> Any:
    """One enrollment row over the window `[start_offset, end_offset]`, in days."""
    enrollment = require_table(tables, "enrollment")
    start_column, end_column = enrollment_window_columns(enrollment)
    window = {
        start_column: window_value(enrollment.c[start_column], start_offset),
        end_column: window_value(enrollment.c[end_column], end_offset),
    }
    return seed_row(session, tables, "enrollment", chain, **window, **overrides)


def identity_spelled(names: Any) -> list[str]:
    """Those of `names` that read as a person's identity — a name, an email, or one of
    the other spellings E0-10 widened `IDENTITY_NAME_FRAGMENTS` to cover."""
    return sorted(name for name in names if any(f in name.lower() for f in IDENTITY_NAME_FRAGMENTS))


# ---------------------------------------------------------------------------
# Criterion 1 — the tables exist.
# ---------------------------------------------------------------------------


def test_upgrade_head_creates_the_identity_and_lti_registration_tables(
    migrated_engine: Any,
) -> None:
    """Criterion 1, first half: `alembic upgrade head` creates all six tables.

    Asserted against the server rather than against `Base.metadata`, because a
    table that is on the metadata and in no migration exists nowhere a deployment
    can reach — the silent failure the epic README's first settled rule is about.
    `tests/unit/test_identity_models_registered.py` asserts the other side of
    that pair.
    """
    present = sorted(inspect(migrated_engine).get_table_names())

    missing = [name for name in E0_08_TABLES if name not in present]
    assert not missing, (
        f"`alembic upgrade head` left no {missing} table. The migrated database holds {present}. "
        "E0-08 creates user, user_identity, person, enrollment, lti_platform and lti_deployment "
        "(SPEC §8); a table spelled differently in the migration is the same defect as one that "
        "was never created, because §8 names these tables and E0-09, E0-10 and E1 all join to "
        "them."
    )


# ---------------------------------------------------------------------------
# Criterion 2 — a user is unique per LMS user ID per platform.
# ---------------------------------------------------------------------------


def test_a_second_user_with_the_same_lms_id_on_one_platform_is_refused(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 2, first half: the same LMS user ID twice on one platform is rejected.

    **Two rows go in before the one that must not.** The first establishes the
    platform and proves the insert path works at all; the second, carrying a
    *different* LMS ID onto the same platform, proves the constraint is not
    simply "one user per platform" — which would satisfy a `pytest.raises` for a
    reason that has nothing to do with the ID (`docs/MISTAKES.md` entry 3). Only
    then does the duplicate mean something.
    """
    user = require_table(declared_tables, "user")
    lms_id = require_column(user, LMS_USER_ID_COLUMNS)
    platform_column = one_foreign_key_column(user, "lti_platform")

    chain: dict[str, Any] = {}
    platform = seed_row(db_session, declared_tables, "lti_platform", chain)
    platform_key = platform[single_primary_key(require_table(declared_tables, "lti_platform"))]

    seed_row(
        db_session,
        declared_tables,
        "user",
        chain,
        **{lms_id: LMS_USER_ID, platform_column: platform_key},
    )

    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "user",
                chain,
                **{lms_id: OTHER_LMS_USER_ID, platform_column: platform_key},
            )
    except DatabaseError as refused:
        pytest.fail(
            f"A second user with a different LMS ID on the same platform was refused: {refused}. "
            "A platform has thousands of users, and until a second one inserts, the refusal "
            "below says nothing about the ID being a duplicate."
        )

    refused_duplicate = False
    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "user",
                chain,
                **{lms_id: LMS_USER_ID, platform_column: platform_key},
            )
    except DatabaseError:
        refused_duplicate = True

    assert refused_duplicate, (
        f"The LMS user ID {LMS_USER_ID!r} was written twice against one platform. E0-08: 'A "
        "`user` is unique per LMS user ID per platform.' Without the constraint one person "
        "acquires two `user` rows, and SPEC §4 keys responses to that ID — so their responses "
        "split across two identities and the participation formula counts them twice."
    )


def test_the_same_lms_id_on_two_platforms_is_two_users(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 2, second half: the ID is unique *within* a platform, not globally.

    This is the half that fails when the constraint is written over the LMS ID
    alone, which is the natural mistake: `sub` looks like a global identifier and
    is only unique per issuer (SPEC §7.3). Nothing would surface it until a
    second platform is registered, which in a single-tenant deployment may be the
    first time a test LMS and a production LMS point at the same tool.
    """
    user = require_table(declared_tables, "user")
    lms_id = require_column(user, LMS_USER_ID_COLUMNS)
    platform_column = one_foreign_key_column(user, "lti_platform")
    platform_key = single_primary_key(require_table(declared_tables, "lti_platform"))

    first: dict[str, Any] = {}
    one = seed_row(db_session, declared_tables, "lti_platform", first)
    second: dict[str, Any] = {}
    two = seed_row(db_session, declared_tables, "lti_platform", second)
    assert one[platform_key] != two[platform_key], (
        "Seeding a second LTI platform returned the first one, so there is no second platform to "
        "put the user on and the assertion below would be about nothing."
    )

    seed_row(
        db_session,
        declared_tables,
        "user",
        first,
        **{lms_id: LMS_USER_ID, platform_column: one[platform_key]},
    )

    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "user",
                second,
                **{lms_id: LMS_USER_ID, platform_column: two[platform_key]},
            )
    except DatabaseError as refused:
        pytest.fail(
            f"The LMS user ID {LMS_USER_ID!r} was accepted on one platform and refused on "
            f"another: {refused}. E0-08: 'the same LMS ID on two platforms is two users'. A "
            "uniqueness rule over the ID alone makes the second platform's user unwritable, and "
            "with it every response that user submits."
        )


# ---------------------------------------------------------------------------
# Criterion 3 — identity lives on `user_identity` and nowhere on `user`.
# ---------------------------------------------------------------------------


def test_no_name_or_email_column_exists_on_user(migrated_engine: Any) -> None:
    """Criterion 3: `user` holds the key and the platform reference, and no identity.

    **Read out of Postgres and not out of the model**, because the criterion says
    "so the split cannot erode" and the erosion it names is a table being
    rewritten later. A model attribute list cannot see a column that reached the
    database by some other route, and it is the database that E0-10 grants
    against ([ADR 0001](../../docs/adr/0001-identity-separation-by-database-role.md):
    identity is withheld by a table-level grant precisely because a column-level
    one disappears silently when a table is recreated).

    **The non-vacuity guard runs first and is not ceremony.** "No name or email
    on `user`" is satisfied most thoroughly by a schema that stores no name or
    email anywhere at all — which is `docs/MISTAKES.md` entry 3 exactly. So
    `user_identity` is required to hold both before their absence next door is
    allowed to mean anything.
    """
    inspector = inspect(migrated_engine)
    present = inspector.get_table_names()
    for name in ("user", "user_identity"):
        assert name in present, (
            f"The migrated database has no `{name}` table, so this criterion has nothing to be "
            f"about. E0-08 splits `user` from `user_identity`; the tables it holds are "
            f"{sorted(present)}."
        )

    identity_columns = identity_spelled(
        column["name"] for column in inspector.get_columns("user_identity")
    )
    named = [name for name in identity_columns if "name" in name.lower()]
    emailed = [name for name in identity_columns if "email" in name.lower()]
    assert named and emailed, (
        f"`user_identity` carries {identity_columns} — this file could not find both a name "
        "column and an email column there. E0-08: '`user_identity` is a separate table holding "
        "name and email, one row per user.' Until it holds them, the assertion below passes "
        "against a schema that stores no identity anywhere, which is not the split the ticket is "
        "asking for."
    )

    on_user = identity_spelled(column["name"] for column in inspector.get_columns("user"))
    assert not on_user, (
        f"`user` carries {on_user}. E0-08: `user` 'holds the key and the platform reference — "
        "**no names, no email addresses**', and identity columns live on `user_identity` and "
        "nowhere else. The split is what makes E0-10's protection a table-level grant rather "
        "than a column-level one, and ADR 0001 chose table grain because a column grant "
        "disappears silently the next time the table is recreated. An identity column on `user` "
        "is inside the grant every instructor and leadership read path already has."
    )


def test_a_user_has_at_most_one_identity_row(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Scope: "one row per user". Two identity rows for one user are refused.

    Not one of the seven criteria, and asserted because the scope says it and
    nothing else would (`docs/MISTAKES.md` entry 2). It is load-bearing for
    E0-10: a read path that joins a user to their identity expects one row, and a
    second one silently doubles every joined result — or, worse, makes which name
    is returned depend on the plan.

    The control is a second identity row for a *different* user, so a refusal is
    known to be about the pair rather than about `user_identity` accepting only
    one row in total.
    """
    user_identity = require_table(declared_tables, "user_identity")
    user_key = single_primary_key(require_table(declared_tables, "user"))
    user_column = one_foreign_key_column(user_identity, "user")

    chain: dict[str, Any] = {}
    first_user = seed_row(db_session, declared_tables, "user", chain)
    seed_row(
        db_session, declared_tables, "user_identity", chain, **{user_column: first_user[user_key]}
    )

    second_user = seed_row(db_session, declared_tables, "user", branch_from(chain, "lti_platform"))
    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "user_identity",
                dict(chain),
                **{user_column: second_user[user_key]},
            )
    except DatabaseError as refused:
        pytest.fail(
            f"An identity row for a second user was refused: {refused}. Until two users can each "
            "have one, the refusal below says nothing about a user having two."
        )

    refused_second = False
    try:
        with db_session.begin_nested():
            seed_row(
                db_session,
                declared_tables,
                "user_identity",
                dict(chain),
                **{user_column: first_user[user_key]},
            )
    except DatabaseError:
        refused_second = True

    assert refused_second, (
        "One user was given two `user_identity` rows. E0-08: '`user_identity` is a separate "
        "table holding name and email, **one row per user**.' Nothing in a foreign key says one, "
        "so this needs a uniqueness rule of its own."
    )


# ---------------------------------------------------------------------------
# Scope — the person graph, and what an enrollment links.
# ---------------------------------------------------------------------------


def test_a_person_may_exist_without_a_user(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Scope: "A `person` may or may not correspond to a `user`; the link is nullable and explicit."

    Two halves, and both are the same behaviour: a person who is not an LMS user
    can be recorded. **Explicit** is asserted by there being exactly one foreign
    key joining the two tables — SPEC §2.1 builds the people graph top-down in
    the admin console, and a person matched to a user by name later is the
    ambiguity the explicit link exists to avoid. **Nullable** is asserted on the
    column and then by writing the row: a chair who has never launched the tool
    has no LMS user, and a NOT NULL link makes the graph unbuildable until
    everyone in it has logged into the LMS.

    **The direction is not this file's to choose.** The ticket says the link is
    nullable and explicit and does not say which table carries it, so both are
    looked for. A link on `user` is checked the same way — it has to be nullable,
    since a student who launches the tool is a `user` and is not in the people
    graph at all.
    """
    person = require_table(declared_tables, "person")
    user = require_table(declared_tables, "user")

    on_person = [(person, name) for name in foreign_key_columns(person, "user")]
    on_user = [(user, name) for name in foreign_key_columns(user, "person")]
    links = on_person + on_user
    assert len(links) == 1, (
        f"There are {len(links)} foreign keys joining `person` and `user` "
        f"({[f'{table.name}.{column}' for table, column in links]}). E0-08: 'A `person` may or "
        "may not correspond to a `user`; the link is nullable and explicit.' None means the two "
        "are matched by name somewhere in application code, which is the ambiguity an explicit "
        "link exists to remove; more than one means two links that can disagree about who is "
        "whom."
    )

    table, column = links[0]
    assert table.c[column].nullable, (
        f"`{table.name}.{column}` is NOT NULL, so a person and an LMS user cannot exist without "
        "each other. SPEC §2.1 builds the people graph in the admin console, top-down, and E0-08 "
        "says the link 'is nullable and explicit'. A dean who never launches the tool still "
        "supervises chairs, and purview is computed from this graph; a student who launches is a "
        "user and is in no people graph at all."
    )

    overrides = {column: None} if table.name == "person" else {}
    try:
        with db_session.begin_nested():
            seed_row(db_session, declared_tables, "person", None, **overrides)
    except DatabaseError as refused:
        pytest.fail(
            f"Inserting a person with no user was refused: {refused}. The column is nullable, so "
            "something else — a check constraint, a trigger — is enforcing what the ticket says "
            "must be optional."
        )


def test_an_enrollment_links_a_user_to_a_section(declared_tables: dict[str, Table]) -> None:
    """Scope: "`enrollment` links a `user` to a `section`".

    Both links found by following foreign keys, so neither column name is this
    file's to choose. E3's participation formula reads this row to decide which
    weeks a student was enrolled for; an enrollment that names a person rather
    than a user cannot be joined to a response, which SPEC §4 keys to the LMS
    user ID.
    """
    enrollment = require_table(declared_tables, "enrollment")

    to_user = foreign_key_columns(enrollment, "user")
    to_section = foreign_key_columns(enrollment, "section")
    referenced = sorted({key.column.table.name for key in enrollment.foreign_keys})

    assert to_user, (
        f"`enrollment` references {referenced} and none of them is `user`. E0-08: 'enrollment "
        "links a `user` to a `section`'. SPEC §4 keys responses to the LMS user ID, so an "
        "enrollment that reaches a student any other way cannot be joined to their responses."
    )
    assert to_section, (
        f"`enrollment` references {referenced} and none of them is `section`. An enrollment "
        "without a section cannot answer which weeks a student was enrolled for, which is what "
        "E3's participation formula reads it for."
    )


# ---------------------------------------------------------------------------
# Criterion 4 — the enrollment window runs forwards.
# ---------------------------------------------------------------------------


def test_an_enrollment_ending_before_it_starts_is_refused(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 4: an end date before the start date is rejected.

    The control window goes in first. Any of these statements could be refused
    for a reason that has nothing to do with the ordering — a column this file's
    seeding helper filled badly, a constraint from another ticket — and
    `pytest.raises` cannot tell those apart from the rejection under test
    (`docs/MISTAKES.md` entry 3). An ordinary enrollment inserting immediately
    before, through the same helper and into the same section, can.

    **The backwards row belongs to a second user**, sharing the section and
    nothing else. Criterion 5's rule, whichever way it is settled, is about one
    user and one section, and a backwards window that is also a second row for
    the same pair could be refused by that rule instead of by this one — which
    would leave this test green against a schema that never checks the ordering
    at all.
    """
    enrollment = require_table(declared_tables, "enrollment")
    user_key = single_primary_key(require_table(declared_tables, "user"))
    user_column = one_foreign_key_column(enrollment, "user")

    chain: dict[str, Any] = {}
    try:
        seed_enrollment(db_session, declared_tables, chain, ADDED, DROPPED)
    except DatabaseError as refused:
        pytest.fail(
            f"An enrollment running {ADDED} to {DROPPED} days into the term was refused: "
            f"{refused}. Until an ordinary window inserts, a refusal below says nothing about "
            "the ordering of the two dates."
        )

    other_user = seed_row(db_session, declared_tables, "user", branch_from(chain, "lti_platform"))
    refused_backwards = False
    try:
        with db_session.begin_nested():
            seed_enrollment(
                db_session,
                declared_tables,
                dict(chain),
                DROPPED,
                ADDED,
                **{user_column: other_user[user_key]},
            )
    except DatabaseError:
        refused_backwards = True

    assert refused_backwards, (
        "An enrollment was stored whose end date falls before its start date. E0-08: "
        "'`enrollment` rejects an end date before its start date.' §3.4's tiers resolve a "
        "student's first enrolled week from this pair, and a backwards window describes a "
        "membership that ended before it began — a row that is wrong in a way no later code can "
        "detect, because both dates are perfectly valid on their own."
    )


def test_an_enrollment_that_starts_and_ends_on_the_same_day_is_accepted(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 4's near miss: equal dates are not "before", so they must be allowed.

    A student who adds and drops on the same day is an ordinary record, and the
    criterion says *before*. This is the test that separates a check written
    `end >= start` from one written `end > start`, and only the first satisfies
    the criterion as worded. It goes red on the natural over-tightening rather
    than leaving it to be discovered by a roster sync that cannot write a row.
    """
    chain: dict[str, Any] = {}
    try:
        seed_enrollment(db_session, declared_tables, chain, ADDED, ADDED)
    except DatabaseError as refused:
        pytest.fail(
            f"An enrollment that starts and ends on the same day was refused: {refused}. "
            "Criterion 4 rejects an end date *before* its start date; an equal date is not "
            "before it, and a student who adds and drops in one day is a real row a roster sync "
            "has to be able to write."
        )


def test_the_enrollment_window_ordering_is_stated_as_its_own_check_constraint(
    migrated_engine: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 4, asserted as a constraint rather than as a behaviour.

    **Why a second test for one criterion, and why this one reads the catalog.**
    The behavioural test above cannot fail. Criterion 5 is enforced by an
    exclusion constraint over `daterange(start, end, '[]')`, and Postgres refuses
    to *construct* a range whose end precedes its start — the error is raised
    evaluating the expression, before any constraint is consulted. So a backwards
    window is refused whether or not anything states criterion 4's rule, and
    deleting the check constraint leaves every other test in this module green.
    That is `docs/MISTAKES.md` entry 3 in a shape the entry did not yet have: not
    an absence asserted, and not a missing control — the controls are all there
    and correct — but a refusal supplied by the implementation of a *different*
    rule. The implementer found it and declared it; nothing in this file did.

    So this asks Postgres what the table carries, not what it does. The rule has
    to be stated in its own right, because the day someone changes how overlap is
    enforced — an application-level check, a trigger, a different range bound —
    criterion 4 goes with it silently.

    **What is asserted:** `enrollment` carries at least one CHECK constraint
    whose expression mentions both window columns and contains a relational
    operator. Nothing about its name (the naming convention generates those, and
    a rename is not a regression), nothing about which side of the comparison
    each column sits on, and nothing about `>=` versus `>` — the same-day test
    above is what settles that, and it settles it by behaviour, which is the
    right side to settle it from.

    **What it does not cover**, so that nobody reads it as more than it is
    (`docs/MISTAKES.md` entry 14):

      - **It requires a CHECK constraint specifically.** A trigger, or a domain
        carrying the rule, would satisfy criterion 4 and fail here. That is a
        mechanism this test pins and the ticket does not, and it is pinned
        because a CHECK is the only one of the three that Postgres reports as a
        property *of the table*. If the rule is deliberately stated some other
        way, say so in the pull request and change this test with it.
      - **It does not read the comparison.** A two-column CHECK that compares
        them for something other than ordering would pass. Parsing the
        expression far enough to tell those apart would mean pinning its shape,
        which would fail a perfectly good `COALESCE(ended_on, 'infinity') >=
        started_on` written for a nullable end.
      - **It cannot tell a constraint that is stated from one that is
        redundant.** Whether the check is doing work is a question about the
        other constraint, and criterion 4 does not ask it: the rule is worth
        stating whether or not something else currently implies it.
    """
    enrollment = require_table(declared_tables, "enrollment")
    start_column, end_column = enrollment_window_columns(enrollment)

    constraints = inspect(migrated_engine).get_check_constraints("enrollment")
    stating = []
    for constraint in constraints:
        expression = constraint.get("sqltext") or ""
        mentions_both = all(
            re.search(rf"\b{re.escape(column)}\b", expression)
            for column in (start_column, end_column)
        )
        # `<>` is removed before looking for a comparison so that an inequality
        # test does not read as an ordering one. Both `<` and `>` of it would
        # otherwise match.
        compares = re.search(r"[<>]", re.sub(r"<>", "", expression))
        if mentions_both and compares:
            stating.append(expression)

    assert stating, (
        f"No CHECK constraint on `enrollment` relates `{start_column}` and `{end_column}` by a "
        f"comparison. What the table carries: {[c.get('sqltext') for c in constraints]}. E0-08 "
        "criterion 4: '`enrollment` rejects an end date before its start date.' Note that the "
        "behavioural test in this module passes without this constraint — the exclusion "
        "constraint enforcing criterion 5 refuses a backwards window on its own, because "
        "Postgres will not build a `daterange` whose end precedes its start. So the rule is "
        "currently enforced as a side effect of a different rule, and it disappears the moment "
        "overlap is enforced some other way. State it: a CHECK comparing the two window columns."
    )


# ---------------------------------------------------------------------------
# Criterion 5 — overlapping enrollments. **Decided here as rejection.**
# ---------------------------------------------------------------------------


def test_overlapping_enrollments_for_one_user_and_section_are_refused(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 5, decided as rejection: two overlapping windows for one pair are rejected.

    **The criterion leaves this open and this test closes it one way**, which the
    implementer may dispute: "either rejected or explicitly permitted with a
    documented reason — decide and test it." Rejection is chosen because E3's
    participation formula asks "was this student enrolled in week N", and two
    overlapping rows make that question have two answers with no rule for
    choosing between them; a student counted twice in one week moves the
    denominator of a number posted straight into the LMS gradebook, whose only
    explanation to anybody is the per-week ledger in its AGS comment (§3.4, ADR
    0125) — v1 ships no instructor-facing or student-facing view of it at all.
    Permitting them
    would need that rule written down first, and the ticket does not have one. If
    the pull request permits overlap instead, it owes the documented reason the
    criterion asks for, and this test is what it replaces.

    **Two controls, because a `pytest.raises` here has two innocent
    explanations.** The first enrollment proves the insert path works. A second,
    overlapping enrollment for a *different user* in the same section proves the
    refusal is about the pair and not about the section only tolerating one row
    at a time.
    """
    enrollment = require_table(declared_tables, "enrollment")
    user_key = single_primary_key(require_table(declared_tables, "user"))
    user_column = one_foreign_key_column(enrollment, "user")

    chain: dict[str, Any] = {}
    try:
        seed_enrollment(db_session, declared_tables, chain, ADDED, DROPPED)
    except DatabaseError as refused:
        pytest.fail(
            f"The first enrollment was refused: {refused}. Nothing below can mean anything until "
            "one ordinary enrollment inserts."
        )

    other_user = seed_row(db_session, declared_tables, "user", branch_from(chain, "lti_platform"))
    try:
        with db_session.begin_nested():
            seed_enrollment(
                db_session,
                declared_tables,
                dict(chain),
                OVERLAPPING_START,
                OVERLAPPING_END,
                **{user_column: other_user[user_key]},
            )
    except DatabaseError as refused:
        pytest.fail(
            "An overlapping enrollment for a *different* user in the same section was refused: "
            f"{refused}. Two students are enrolled in a section at the same time by definition, "
            "so a rule that stops this is not the rule criterion 5 is about — and it would make "
            "the refusal below prove nothing."
        )

    refused_overlap = False
    try:
        with db_session.begin_nested():
            seed_enrollment(
                db_session, declared_tables, dict(chain), OVERLAPPING_START, OVERLAPPING_END
            )
    except DatabaseError:
        refused_overlap = True

    assert refused_overlap, (
        "One user was given two overlapping enrollments in one section. E0-08 criterion 5 leaves "
        "the choice open and this suite reads it as rejection: E3's participation formula asks "
        "whether a student was enrolled in week N, and overlapping rows give that question two "
        "answers with no rule for choosing. If overlap is deliberately permitted, the pull "
        "request owes the documented reason the criterion asks for and this test is what it "
        "replaces."
    )


def test_a_re_enrollment_after_the_first_window_closes_is_accepted(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 5's near miss: a drop and a later re-add are two non-overlapping rows.

    This is what separates "overlapping windows are rejected" from "a user may be
    enrolled in a section once, ever" — a unique constraint over
    `(user_id, section_id)` satisfies the test above and fails here. Mid-term
    adds and drops are ordinary (E0-15 seeds them deliberately), and a student
    who drops in week 3 and re-adds in week 8 has two windows that do not touch.
    """
    chain: dict[str, Any] = {}
    seed_enrollment(db_session, declared_tables, chain, ADDED, DROPPED)

    try:
        with db_session.begin_nested():
            seed_enrollment(db_session, declared_tables, dict(chain), RE_ADDED, RE_DROPPED)
    except DatabaseError as refused:
        pytest.fail(
            "A second, non-overlapping enrollment for the same user and section was refused: "
            f"{refused}. The two windows do not touch — day {ADDED} to {DROPPED}, then day "
            f"{RE_ADDED} to {RE_DROPPED} — so this is a drop and a later re-add, which the LMS "
            "sends and E0-15 seeds. A uniqueness rule over the user and section alone rejects "
            "it, and the roster record then cannot say the student was away for two weeks — which "
            "is what E3-06 reads to decide whether a score is still posted for them."
        )


# ---------------------------------------------------------------------------
# Criterion 7 — no client secret in plaintext.
# ---------------------------------------------------------------------------


def test_lti_platform_stores_no_client_secret_in_plaintext(
    db_session: Any, declared_tables: dict[str, Table]
) -> None:
    """Criterion 7: the column either does not exist, or what it stores is not the value.

    Two branches, because the criterion has two. **If no secret-shaped column
    exists**, the criterion is met by the column not existing — LTI 1.3 is
    asymmetric-key and a tool registration needs no shared secret at all — and
    all this test can do is make sure `lti_platform` is a real table first, so
    the absence is an absence in something rather than the absence of everything
    (`docs/MISTAKES.md` entry 3).

    **If one does exist**, a sentinel is written through the declared table — so
    that an encrypting `TypeDecorator` is in the path, which is the most likely
    implementation and which a write through a reflected table would bypass — and
    the stored value is read back through `CAST(... AS text)`. The cast is what
    makes the read honest: its result type is `Text`, so SQLAlchemy uses `Text`'s
    result processing and the decorator's `process_result_value` never runs. A
    plain `SELECT` of the same column would hand back the value decrypted and
    this test would pass against a column storing it in the clear. The sentinel
    must not appear in what comes back, in plain text, as hex (which is how a
    `bytea` renders), or base64-encoded, because encoding is not encryption.

    **The control is the client ID**, written as its own sentinel and read back
    through the same query. It has to come back readable. Without it, a query
    that returned nothing, or a column cast that produced an empty string, would
    satisfy the assertion about the secret while proving nothing at all.

    What this cannot see is disk-level encryption, which SPEC §10 makes the
    deployment's responsibility. So "encrypted at rest" is read here as: the
    value Postgres holds in the column is not the value that was written.
    """
    platform = require_table(declared_tables, "lti_platform")
    columns = [column.name for column in platform.columns]

    # Sorted so that a column naming an id wins over any other `client...`
    # column, since the control below needs the one that certainly holds a
    # readable value.
    client_columns = sorted(
        (
            name
            for name in columns
            if CLIENT_ID_FRAGMENT in name.lower()
            and not any(f in name.lower() for f in SECRET_FRAGMENTS)
        ),
        key=lambda name: (0 if "id" in name.lower() else 1, name),
    )
    assert client_columns, (
        f"`lti_platform` has no column naming a client ID — it has {columns}. E0-08's scope gives "
        "it 'issuer, client ID, deployment IDs, JWKS URL, last fetch'. Until the table holds the "
        "registration it is for, 'it stores no client secret' is true of it the way it is true "
        "of an empty table, which is not what criterion 7 is asking."
    )
    client_column = client_columns[0]

    secret_columns = [name for name in columns if any(f in name.lower() for f in SECRET_FRAGMENTS)]
    if not secret_columns:
        # The first branch of the criterion: the column does not exist. Nothing
        # further to assert — and nothing further that *could* be asserted, since
        # there is no value to go looking for.
        return

    assert len(secret_columns) == 1, (
        f"`lti_platform` carries more than one secret-shaped column ({secret_columns}), and this "
        "test writes into one. Both need checking; add the loop here rather than dropping one."
    )
    secret_column = secret_columns[0]

    written: Any = PLAINTEXT_SENTINEL
    if isinstance(stored_type(platform.c[secret_column]), LargeBinary):
        written = PLAINTEXT_SENTINEL.encode()

    row = seed_row(
        db_session,
        declared_tables,
        "lti_platform",
        None,
        **{secret_column: written, client_column: CLIENT_ID_SENTINEL},
    )

    key = single_primary_key(platform)
    stored = (
        db_session.execute(
            select(
                cast(platform.c[secret_column], Text).label("secret_text"),
                cast(platform.c[client_column], Text).label("client_text"),
            ).where(platform.c[key] == row[key])
        )
        .mappings()
        .one()
    )

    assert CLIENT_ID_SENTINEL in (stored["client_text"] or ""), (
        f"The client ID read back as {stored['client_text']!r} rather than containing "
        f"{CLIENT_ID_SENTINEL!r}. This query is the control: until it can see a value that *was* "
        "written in plain text, the assertion below cannot tell an encrypted secret from a "
        "query that looked in the wrong place."
    )

    secret_text = (stored["secret_text"] or "").lower()
    encodings = {
        "plain text": PLAINTEXT_SENTINEL.lower(),
        "hex, as a bytea renders": PLAINTEXT_SENTINEL.encode().hex().lower(),
        "base64": base64.b64encode(PLAINTEXT_SENTINEL.encode()).decode().lower(),
    }
    found = sorted(how for how, needle in encodings.items() if needle in secret_text)
    assert not found, (
        f"`lti_platform.{secret_column}` gave back the value that was written, as {found}. E0-08 "
        "criterion 7: the column 'either does not exist or is encrypted at rest'. Base64 and hex "
        "are counted here because an encoding is not an encryption — it is reversible by anyone "
        "holding the row. SPEC §10 puts disk encryption on the deployment, so what this asserts "
        "is the part the application owns: the bytes Postgres holds are not the credential. If "
        "LTI 1.3's asymmetric registration means no secret is needed at all, delete the column — "
        "that is the criterion's other branch and it passes this test."
    )
