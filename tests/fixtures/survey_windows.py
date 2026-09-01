"""E2-06 — the Fall 2026 survey-window calendar, hand-computed, and the rows to derive it from.

Three suites read the same two things: the instants SPEC §3.1's rhythm produces
over the seeded Fall 2026 calendar, and a term with its eighteen weeks and a
section whose cohort is one of §2.2's start letters. A copy of either in each
module is `docs/MISTAKES.md` entry 13 — one question answered in three places —
so both live here.

**Every instant below is written by hand and none is computed.** That is
`docs/MISTAKES.md` entry 19's rule, and it is the whole reason this table is
thirty-six literals rather than four lines of arithmetic: a test that derived its
expectation with `ZoneInfo` and a `timedelta` would agree with any implementation
that made the same mistake, and the mistakes worth catching here — one zone
conversion per window instead of one per instant, a Friday counted from the
section's start rather than the term week's Monday, an offset frozen at the
term's first week — are all mistakes an obvious re-derivation makes too.

`tests/unit/test_the_fall_2026_window_calendar_is_spec_3_1s_rhythm.py` is the
control on the literals: it reads each one back into `America/New_York` and
requires a Friday at 18:00 and a Sunday at 23:59:59 on the term-week Monday the
seed's calendar puts them on. A red there means this file is wrong and every
assertion resting on it is measuring the wrong thing — not that the service is.

**Nothing here asserts what the service answers.** These fixtures seed rows and
read rows back; what the derivation should produce is the test modules' subject,
and a fixture that encoded it would be a second implementation for the tests to
agree with (`docs/MISTAKES.md` entry 30).
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from importlib import import_module
from types import ModuleType
from typing import Any

import pytest

from fixtures.clock import DEVELOPMENT, INSTITUTION_TIMEZONE_VARIABLE

# ---------------------------------------------------------------------------
# The service, spelled as E2-06's work order settles it.
# ---------------------------------------------------------------------------

# SPEC §13 puts a service under `backend/app/services/`, so the import path is
# `app.services....`. The module is new: `section_codes` is calendar parsing and
# `clock` is time, and neither is window scheduling.
SURVEY_WINDOW_SERVICE_MODULE = "app.services.survey_windows"

# The one writer, and the read-time question. Both signatures are settled by the
# work order: `derive_windows_for_section(session, section, *, settings)` and
# `open_window_for_section(session, section, *, settings, at: datetime | None =
# None) -> SurveyWindow | None`.
#
# **`at` is the seam a boundary can be stood on.** Left `None` — which is every
# production caller — the instant comes from `clock.now`, so the development
# override reaches the answer. A test passes it to land exactly on `opens_at` or
# on `closes_at`, which an offset clock can never do: ADR 0109 makes the effective
# now `real + (pretend_now - anchored_at)`, so it is still moving while it is
# read. A naive value is refused rather than reinterpreted, for ADR 0019's reason
# one layer up from the column.
#
# **`windows_for_section` is deliberately not named here.** The work order settles
# that a pure derivation exists under that name and spells no signature for it, so
# a fixture that called it would be inventing the interface rather than reading
# one. Every assertion in these suites goes through the two functions above and
# through the rows they write.
DERIVE_FUNCTION = "derive_windows_for_section"
OPEN_WINDOW_FUNCTION = "open_window_for_section"

# ---------------------------------------------------------------------------
# The tables these fixtures seed and read. All four names are E0-06's and
# E2-05's, not this file's.
# ---------------------------------------------------------------------------

TERM_TABLE = "term"
WEEK_TABLE = "week"
SECTION_TABLE = "section"
SURVEY_WINDOW_TABLE = "survey_window"

WEEK_NUMBER_COLUMN = "number"
SECTION_CODE_COLUMN = "lms_section_code"

# E0-07's four derived section columns (ADR 0021), and E2-05's window columns.
SECTION_LENGTH_COLUMN = "length_weeks"
SECTION_START_COLUMN = "start_date"
SECTION_END_COLUMN = "end_date"
WINDOW_SECTION_COLUMN = "section_id"
WINDOW_WEEK_COLUMN = "week_id"
WINDOW_TERM_COLUMN = "term_id"
WINDOW_OPENS_COLUMN = "opens_at"
WINDOW_CLOSES_COLUMN = "closes_at"

# ---------------------------------------------------------------------------
# SPEC §2.2's Fall 2026 reference calendar, as `scripts/seed.py` seeds it.
# ---------------------------------------------------------------------------

# SPEC §3.1's default, and `.env.example`'s: "opens Friday 18:00, closes Sunday
# 23:59:59 … in the institution timezone (default `America/New_York`)". Named
# here rather than inherited, because every test that depends on it states it
# (`docs/MISTAKES.md` entry 40).
INSTITUTION_TIMEZONE = "America/New_York"

# `scripts/seed.py`: `TERM_START = date(2026, 8, 17)`, `TERM_END =
# date(2026, 12, 20)`, `TERM_LENGTH_WEEKS = 18`. 8/17 is a Monday and the end date
# is the term's last day, inclusive (ADR 0020).
FALL_2026_TERM_START = date(2026, 8, 17)
FALL_2026_TERM_END = date(2026, 12, 20)
FALL_2026_TERM_WEEKS = 18

MONDAY = 0
FRIDAY = 4
SUNDAY = 6

# SPEC §3.1's rhythm as wall-clock parts, for the control that reads the literals
# below back into the institution's zone.
OPENS_WEEKDAY = FRIDAY
OPENS_WALL_CLOCK = (18, 0, 0)
CLOSES_WEEKDAY = SUNDAY
CLOSES_WALL_CLOCK = (23, 59, 59)

# **The whole of Fall 2026's window calendar, in UTC, written out by hand.**
#
# Term week M's Monday is `2026-08-17 + (M - 1) x 7 days`; the window opens on
# that Monday's Friday at 18:00 and closes on its Sunday at 23:59:59, both in
# `America/New_York`, and both are stored as aware UTC (ADR 0019).
#
# `America/New_York` is UTC-4 while daylight time is in force and UTC-5
# afterwards, and **daylight time ends on Sunday 1 November 2026**, which lands
# inside term week 11. So that week alone opens at UTC-4 and closes at UTC-5:
# 18:00 on Friday 30 October is 22:00Z, and 23:59:59 on Sunday 1 November is
# 04:59:59Z the next morning rather than 03:59:59Z. Weeks 1-10 are UTC-4 at both
# ends; weeks 12-18 are UTC-5 at both ends.
#
# That single row is the mutation target for "one zone conversion per instant,
# not one offset per window", and it is the reason the table is written out in
# full rather than summarised as two offsets and a switch date.
DST_FALL_BACK_SUNDAY = date(2026, 11, 1)
DST_FALL_BACK_TERM_WEEK = 11

WINDOWS_BY_TERM_WEEK: dict[int, tuple[datetime, datetime]] = {
    1: (datetime(2026, 8, 21, 22, 0, 0, tzinfo=UTC), datetime(2026, 8, 24, 3, 59, 59, tzinfo=UTC)),
    2: (datetime(2026, 8, 28, 22, 0, 0, tzinfo=UTC), datetime(2026, 8, 31, 3, 59, 59, tzinfo=UTC)),
    3: (datetime(2026, 9, 4, 22, 0, 0, tzinfo=UTC), datetime(2026, 9, 7, 3, 59, 59, tzinfo=UTC)),
    4: (datetime(2026, 9, 11, 22, 0, 0, tzinfo=UTC), datetime(2026, 9, 14, 3, 59, 59, tzinfo=UTC)),
    5: (datetime(2026, 9, 18, 22, 0, 0, tzinfo=UTC), datetime(2026, 9, 21, 3, 59, 59, tzinfo=UTC)),
    6: (datetime(2026, 9, 25, 22, 0, 0, tzinfo=UTC), datetime(2026, 9, 28, 3, 59, 59, tzinfo=UTC)),
    7: (datetime(2026, 10, 2, 22, 0, 0, tzinfo=UTC), datetime(2026, 10, 5, 3, 59, 59, tzinfo=UTC)),
    8: (datetime(2026, 10, 9, 22, 0, 0, tzinfo=UTC), datetime(2026, 10, 12, 3, 59, 59, tzinfo=UTC)),
    9: (
        datetime(2026, 10, 16, 22, 0, 0, tzinfo=UTC),
        datetime(2026, 10, 19, 3, 59, 59, tzinfo=UTC),
    ),
    10: (
        datetime(2026, 10, 23, 22, 0, 0, tzinfo=UTC),
        datetime(2026, 10, 26, 3, 59, 59, tzinfo=UTC),
    ),
    # Daylight time ends on the Sunday this window closes on.
    11: (
        datetime(2026, 10, 30, 22, 0, 0, tzinfo=UTC),
        datetime(2026, 11, 2, 4, 59, 59, tzinfo=UTC),
    ),
    12: (datetime(2026, 11, 6, 23, 0, 0, tzinfo=UTC), datetime(2026, 11, 9, 4, 59, 59, tzinfo=UTC)),
    13: (
        datetime(2026, 11, 13, 23, 0, 0, tzinfo=UTC),
        datetime(2026, 11, 16, 4, 59, 59, tzinfo=UTC),
    ),
    14: (
        datetime(2026, 11, 20, 23, 0, 0, tzinfo=UTC),
        datetime(2026, 11, 23, 4, 59, 59, tzinfo=UTC),
    ),
    15: (
        datetime(2026, 11, 27, 23, 0, 0, tzinfo=UTC),
        datetime(2026, 11, 30, 4, 59, 59, tzinfo=UTC),
    ),
    16: (datetime(2026, 12, 4, 23, 0, 0, tzinfo=UTC), datetime(2026, 12, 7, 4, 59, 59, tzinfo=UTC)),
    17: (
        datetime(2026, 12, 11, 23, 0, 0, tzinfo=UTC),
        datetime(2026, 12, 14, 4, 59, 59, tzinfo=UTC),
    ),
    18: (
        datetime(2026, 12, 18, 23, 0, 0, tzinfo=UTC),
        datetime(2026, 12, 21, 4, 59, 59, tzinfo=UTC),
    ),
}

# `scripts/seed.py::START_LETTER_MAP`, as `(length in weeks, first term week, the
# start date the seed writes)`.
#
# **The lengths and the dates are transcribed from the seed**; the term-week
# numbers are this file's reading of them and are checked against the dates by
# the control test, so neither number is trusted on its own. §2.2 documents three
# of the dates itself — "12-week U/R/Q starting 8/17, 9/7, 9/28" — and every start
# date in the map falls on a term-week Monday, which is what makes a course week
# map onto a term week at all.
SEEDED_COHORTS: dict[str, tuple[int, int, date]] = {
    "U": (12, 1, date(2026, 8, 17)),
    "R": (12, 4, date(2026, 9, 7)),
    "Q": (12, 7, date(2026, 9, 28)),
    "E": (6, 1, date(2026, 8, 17)),
    "F": (6, 7, date(2026, 9, 28)),
    "H": (6, 13, date(2026, 11, 9)),
    "X": (8, 1, date(2026, 8, 17)),
    "Y": (8, 7, date(2026, 9, 28)),
    "Z": (8, 11, date(2026, 10, 26)),
    "S": (10, 1, date(2026, 8, 17)),
    "T": (10, 9, date(2026, 10, 12)),
    "V": (15, 1, date(2026, 8, 17)),
    "D": (15, 4, date(2026, 9, 7)),
    "K": (16, 1, date(2026, 8, 17)),
    "2": (3, 1, date(2026, 8, 17)),
    "3": (3, 4, date(2026, 9, 7)),
    "4": (3, 7, date(2026, 9, 28)),
    "5": (3, 10, date(2026, 10, 19)),
    "6": (3, 13, date(2026, 11, 9)),
    "7": (3, 16, date(2026, 11, 30)),
}

# The three lengths E2-06's first criterion asks for by name — "at least one 6-,
# 12- and 15-week section" — plus the two that make the offset arithmetic
# visible: `H` starts in term week 13, and `Q` starts in term week 7 and runs
# across the daylight-saving boundary. A cohort starting in the term's first week
# cannot tell a course week from a term week.
CRITERION_ONE_COHORTS = ("E", "U", "V", "H", "Q")

# The rest of a seeded section's code, after its cohort's start position. §2.2:
# `{startLetter}{ordinal}{modality}`, `WW` online. Ordinal 1 because these
# fixtures seed one section per cohort, and `scripts/seed.py` writes `U1WW` and
# `21WW` for the same reason. See `Fall2026.section_row` for why the code is
# named here rather than left to the seeding walker to invent.
COHORT_SECTION_ORDINAL = "1"
COHORT_SECTION_MODALITY = "WW"


@pytest.fixture
def survey_window_service() -> ModuleType:
    """`app.services.survey_windows`, imported here so a missing module fails loudly and once.

    The same shape as `tests/fixtures/clock.py`'s `clock_service`, and for the
    same reason: a `ModuleNotFoundError` at collection time is a broken run, and a
    named failure inside a test is a red that says which deliverable is absent.
    """
    try:
        module = import_module(SURVEY_WINDOW_SERVICE_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (
            absent == SURVEY_WINDOW_SERVICE_MODULE
            or SURVEY_WINDOW_SERVICE_MODULE.startswith(f"{absent}.")
        ):
            raise
        pytest.fail(
            f"`{SURVEY_WINDOW_SERVICE_MODULE}` does not exist. E2-06 ships it under "
            "`backend/app/services/` (SPEC §13) as the one writer of `survey_window`, with "
            f"`{DERIVE_FUNCTION}(session, section, *, settings)` and "
            f"`{OPEN_WINDOW_FUNCTION}(session, section, *, settings)`."
        )
    for name in (DERIVE_FUNCTION, OPEN_WINDOW_FUNCTION):
        if not callable(getattr(module, name, None)):
            pytest.fail(
                f"`{SURVEY_WINDOW_SERVICE_MODULE}` exposes no callable `{name}`; it exposes "
                f"{sorted(n for n in vars(module) if not n.startswith('_'))}. E2-06 settles both "
                "names: one derives a section's whole set of windows from its calendar, and the "
                "other answers which of them is open against the E2-04 clock."
            )
    return module


def model_for(table_name: str) -> Any:
    """The mapped class behind one table, found through the registry rather than named.

    Copied in shape from `tests/integration/test_section_date_derivation.py`: no
    ticket spells an ORM class name for `section`, so importing one by a guessed
    name would be a test deciding it. The service takes a section, so these
    suites have to be able to hand it a real instance.
    """
    base_module = import_module("app.models.base")
    registry = getattr(getattr(base_module, "Base", None), "registry", None)
    if registry is None:
        pytest.fail("`app.models.base.Base` exposes no `registry`, so no mapped class is findable.")

    found = [
        mapper.class_
        for mapper in registry.mappers
        if getattr(mapper.local_table, "name", None) == table_name
    ]
    if len(found) != 1:
        pytest.fail(
            f"{len(found)} mapped classes stand behind the `{table_name}` table ({found}). These "
            "fixtures need exactly one so they can hand the window service a real instance."
        )
    return found[0]


class Fall2026:
    """The seeded Fall 2026 term, its weeks, and a section per start letter.

    One term, eighteen `week` rows and one section per cohort the caller asks
    for, all in a single containment chain so that every section belongs to the
    term whose weeks are here — which is what E2-05's composite keys require of
    any window written over them.

    **The section's calendar is written by this fixture, not derived by anything.**
    `length_weeks` and `start_date` come from `SEEDED_COHORTS` above, transcribed
    from `scripts/seed.py`, and `end_date` is `start + length x 7 - 1` days, the
    inclusive convention ADR 0020 settles. They are *inputs* to the derivation
    under test and never its output, so `docs/MISTAKES.md` entry 30 is satisfied:
    nothing this fixture supplies is a value a test then reads back as an answer.

    `apply_section_code` is deliberately not called. It is E0-07's writer and its
    correctness is `tests/integration/test_section_date_derivation.py`'s subject;
    routing this fixture through it would make every window assertion here rest on
    that service being right as well, and a red would name the wrong ticket.
    """

    def __init__(self, seed: Callable[..., Any], session: Any, tables: dict[str, Any]) -> None:
        self.seed = seed
        self.session = session
        self.tables = tables
        self.chain: dict[str, Any] = {}
        self.term: Any = None
        self.weeks: dict[int, Any] = {}

    def build(self, *, without_term_weeks: tuple[int, ...] = ()) -> "Fall2026":
        """Seed the term and its weeks, optionally leaving some week rows out.

        `without_term_weeks` is ADR 0018's lengthening gap, posed directly: a term
        whose length says eighteen weeks and whose `week` rows do not run to
        eighteen is a state that ADR 0018 measures as reachable by an ordinary
        edit, with "no error, no log line, and every surviving row looking
        correct". E2-06 has to tolerate it loudly, so a test needs to be able to
        build it.

        **The chain is reset on every call, which matters for one caller.** This
        fixture is function-scoped and a Hypothesis property runs its body once per
        example inside a savepoint that is rolled back afterwards — so a chain
        carried over from the previous example holds primary keys of rows that no
        longer exist, and the next section seeded against them is refused by a
        foreign key inside its own fixture. Rebuilding is also what makes each
        example an independent term rather than twenty sections accumulating in one.
        """
        self.chain = {}
        self.weeks = {}
        self.term = self.seed(
            TERM_TABLE,
            self.chain,
            **{
                "length_weeks": FALL_2026_TERM_WEEKS,
                "start_date": FALL_2026_TERM_START,
                "end_date": FALL_2026_TERM_END,
            },
        )
        for number in range(1, FALL_2026_TERM_WEEKS + 1):
            if number in without_term_weeks:
                continue
            self.weeks[number] = self.seed(WEEK_TABLE, self.chain, **{WEEK_NUMBER_COLUMN: number})
        return self

    def section_row(self, letter: str) -> Any:
        """One section of the cohort `letter`, as the inserted row's mapping.

        **The section code is named here rather than invented, and that is
        `docs/disputes/E2-06-01.md`'s repair.** The shared seeding walker fills an
        unnamed `lms_section_code` from `graph_letters(1)`, a session-wide counter
        one letter wide; a `section` row draws it twice — once for its code and once
        for its `lms_context_id` — so the letters advance by two and the alphabet
        closes after thirteen. A test seeding all twenty of §2.2's cohorts under one
        course and one term therefore died on its twelfth, inside its own fixture,
        against E0-06's `uq_section_course_id_term_id_lms_section_code`. That was
        `docs/MISTAKES.md` entry 13's corollary exactly — when a test fails inside
        its own fixture, suspect the fixture first.

        `{letter}1WW` cannot collide across cohorts, because the cohort letters are
        distinct by construction: `SEEDED_COHORTS` is keyed by them, and E0-06 makes
        a start position unique within a term. It is also §2.2's own grammar —
        `{startLetter}{ordinal}{modality}` — and it is what `scripts/seed.py`
        actually writes, `U1WW` and `21WW` among them, so a numbered cohort is
        spelled the way the seed spells it.

        **It is worth more than uniqueness.** Before this, a cohort-`H` section was
        seeded carrying a code beginning with whatever letter the counter happened to
        be on, so the row disagreed with the cohort it was supposed to be — which
        made the missing-week warning's "name the section code" assertion a check
        against an unrelated string. The derivation reads `length_weeks` and
        `start_date` and never the code, so naming it supplies nothing the tests
        then read back as an answer (`docs/MISTAKES.md` entry 30).
        """
        length_weeks, _first_term_week, start = SEEDED_COHORTS[letter]
        return self.seed(
            SECTION_TABLE,
            self.chain,
            **{
                SECTION_CODE_COLUMN: f"{letter}{COHORT_SECTION_ORDINAL}{COHORT_SECTION_MODALITY}",
                SECTION_LENGTH_COLUMN: length_weeks,
                SECTION_START_COLUMN: start,
                SECTION_END_COLUMN: start + timedelta(days=length_weeks * 7 - 1),
            },
        )

    def section(self, letter: str) -> Any:
        """The same section, as the mapped instance the service is handed."""
        return self.instance(SECTION_TABLE, self.section_row(letter))

    def cohort(self, letter: str) -> tuple[Any, Any]:
        """One section of cohort `letter`, as `(the inserted row, the mapped instance)`.

        Both, because a test that reports which section failed needs the row's own
        `lms_section_code` and primary key, and reading them off the instance would
        assume the mapped attribute is spelled the same as the column — which is
        ordinarily true here and is not something any ticket settles.
        """
        row = self.section_row(letter)
        return row, self.instance(SECTION_TABLE, row)

    def key_of(self, table_name: str) -> str:
        """The name of one table's single primary key column (ADR 0016 makes it one uuid)."""
        return next(iter(self.tables[table_name].primary_key.columns)).name

    def instance(self, table_name: str, row: Any) -> Any:
        """The mapped instance behind one seeded row, loaded by its primary key."""
        table = self.tables[table_name]
        key = next(iter(table.primary_key.columns)).name
        loaded = self.session.get(model_for(table_name), row[key])
        if loaded is None:
            pytest.fail(
                f"The seeded `{table_name}` row could not be loaded through its mapped class. It "
                "was inserted through `Base.metadata` on this session's connection, so a miss here "
                "means the mapped class and the table have come apart."
            )
        return loaded

    def windows_of(self, section: Any) -> list[dict[str, Any]]:
        """Every `survey_window` row for one section, by term week, read through Core.

        Through Core and after a flush, so both shapes a writer could take are
        covered: one that adds mapped objects and leaves the unit of work to
        persist them, and one that issues an `INSERT` itself. Reading a
        relationship off the instance would report the first as a success while
        nothing had reached the database.
        """
        from sqlalchemy import select

        windows = self.tables[SURVEY_WINDOW_TABLE]
        weeks = self.tables[WEEK_TABLE]
        section_key = next(iter(self.tables[SECTION_TABLE].primary_key.columns)).name
        week_key = next(iter(weeks.primary_key.columns)).name
        section_id = getattr(section, section_key)

        self.session.flush()
        statement = (
            select(
                weeks.c[WEEK_NUMBER_COLUMN].label("term_week"),
                windows.c[WINDOW_OPENS_COLUMN].label("opens_at"),
                windows.c[WINDOW_CLOSES_COLUMN].label("closes_at"),
                windows.c[WINDOW_WEEK_COLUMN].label("week_id"),
                windows.c[WINDOW_TERM_COLUMN].label("term_id"),
            )
            .select_from(windows.join(weeks, windows.c[WINDOW_WEEK_COLUMN] == weeks.c[week_key]))
            .where(windows.c[WINDOW_SECTION_COLUMN] == section_id)
            .order_by(weeks.c[WEEK_NUMBER_COLUMN])
        )
        return [dict(row) for row in self.session.execute(statement).mappings()]


@pytest.fixture
def window_settings(settings_in: Any) -> Any:
    """`Settings` in a development environment whose institution timezone is stated.

    **The environment is `development` because the clock override only applies
    there** (ADR 0109, part 4), and every read-path case in E2-06 moves the clock;
    in any other environment the row it writes is dead weight and the service
    would answer real time. **The zone is stated rather than inherited** because
    SPEC §3.1 puts every window at a wall-clock time in it, so a suite whose
    expectations are in `America/New_York` and whose process is in some other zone
    is asserting against two different calendars (`docs/MISTAKES.md` entry 40, and
    `settings_in`'s own docstring for why `configured_env` sits underneath it).

    Here rather than copied into each module for `docs/MISTAKES.md` entry 13's
    reason: two suites ask the same question of the same two variables.
    """
    return settings_in(DEVELOPMENT, **{INSTITUTION_TIMEZONE_VARIABLE: INSTITUTION_TIMEZONE})


@pytest.fixture
def fall_2026(seed_rows: Any, db_session: Any, metadata_tables: dict[str, Any]) -> Fall2026:
    """The seeded Fall 2026 term, unbuilt — the caller decides which weeks exist.

    Returned unbuilt so that the missing-week case does not need a second fixture
    and does not need a `DELETE` against a row a foreign key might hold.
    """
    return Fall2026(seed_rows, db_session, metadata_tables)
