"""E3-03 — the world a participation score is computed over, and the contract it is asked through.

Seven test modules need the same three things: a section whose course weeks are
not its term weeks, students enrolled into it on dates the test chose, and
answers whose comments carry the verdicts the test chose. A copy of any of them
in each module is `docs/MISTAKES.md` entry 13, so all three live here.

**What this file decides, and what it refuses to.** Every table, column and
token below is transcribed from a settled record — E2-05's survey schema, E0-08's
`enrollment`, E1-11's two platform-dated columns (ADR 0095), ADR 0055's
`classification` shape, SPEC §3.2's five questions and SPEC §3.4's ledger line.
The only thing this file invents is which cohort the section is, which subjects
the students carry and which instants the clock is moved to, and each of those is
an *input* the calling test names rather than an answer it reads back
(`docs/MISTAKES.md` entry 30).

**Nothing here computes a score, a denominator, a first enrolled week or a
percentage.** `ledger_line` renders SPEC §3.4's format string and takes all three
of its numbers from the caller; there is no arithmetic in this module at all,
because a fixture that did the arithmetic would be a second implementation for
the tests to agree with (`docs/MISTAKES.md` entry 19).

**The service is imported inside the test body, never in a fixture.**
`grading_module()` is a plain function and `GradingWorld.scores` calls it, so an
absent `app.services.grading` is a **failed test** naming the deliverable rather
than an error in setup — the distinction `tests/fixtures/seed.py` draws about
`pytest.fail` inside a fixture, and the one that decides whether an unimplemented
tree reads as red or as broken.

**The clock, and why nothing here stands exactly on a boundary.** ADR 0109 makes
the development override an *offset* rather than a freeze, so the effective now
keeps moving while it is read and no override can land on an instant. E2-06's
readers take an `at` parameter for that reason; E3-03's contract has no such seam,
so `elapsed_through` and `not_yet_closed` sit a minute either side of a window's
close. A minute is four orders of magnitude inside the week it has to be
distinguished from, and it is far more real time than the two statements between
setting the row and the call can consume.

**The environment** (`docs/MISTAKES.md` entry 40): every module here asks for
`window_settings` from `tests/fixtures/survey_windows.py`, which states
`ENVIRONMENT=development` — the only environment where the clock override applies
at all — and `INSTITUTION_TIMEZONE=America/New_York`, which is the zone SPEC §3.1
puts every window's wall clock in and the zone SPEC §3.4's tier 3 resolves a
`started_on` date in.
"""

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from types import ModuleType
from typing import Any, NamedTuple

import pytest

from fixtures.submit import (
    ANSWER_ID_COLUMN,
    ANSWER_TABLE,
    CLASSIFICATION_TABLE,
    COMMENT_TEXT_COLUMN,
    LIKERT_BOUNDS,
    MAXIMUM_VALUE_COLUMN,
    MINIMUM_VALUE_COLUMN,
    POSITION_COLUMN,
    QUESTION_SET_TABLE,
    QUESTION_TABLE,
    RATING_COLUMN,
    RESPONSE_TABLE,
    SHAPE_OF_POSITION,
    STEP_COLUMN,
    USER_TABLE,
    VERSION_COLUMN,
    WORKLOAD_BOUNDS,
    WORKLOAD_HOURS_COLUMN,
    shape_column,
)
from fixtures.supervision import foreign_key_columns, require_table, single_primary_key
from fixtures.survey_windows import (
    SECTION_TABLE,
    SEEDED_COHORTS,
    SURVEY_WINDOW_TABLE,
    TERM_TABLE,
    WEEK_TABLE,
    WINDOW_CLOSES_COLUMN,
    WINDOW_OPENS_COLUMN,
    WINDOW_SECTION_COLUMN,
    WINDOW_TERM_COLUMN,
    WINDOW_WEEK_COLUMN,
    WINDOWS_BY_TERM_WEEK,
    Fall2026,
)

# ---------------------------------------------------------------------------
# The module contract E3-03's work order settles, spelled once.
# ---------------------------------------------------------------------------

# SPEC §13 puts a service under `backend/app/services/`, and the ticket names the
# file outright: "The whole ticket is one module, `backend/app/services/
# grading.py` (the home SPEC §13 already names for it)".
GRADING_SERVICE_MODULE = "app.services.grading"

# `participation_scores(session, section, *, settings) -> dict[UUID,
# ParticipationScore]`, keyed by the enrollment's user id, with one entry per
# enrolled student who has at least one elapsed enrolled week.
PARTICIPATION_FUNCTION = "participation_scores"

# The frozen dataclass the function answers with, and its four fields.
SCORE_CLASS = "ParticipationScore"
SCORE_FIELDS = ("completed", "total", "percentage", "ledger")

# SPEC §3.4's ledger line, transcribed: "a **per-week ledger** in its AGS comment:
# one line per elapsed week, of the form `Week 1: 4 of 5 items`, in course-week
# order". The lines are joined with a newline.
LEDGER_FORMAT = "Week {course_week}: {completed} of {total} items"
LEDGER_JOIN = "\n"

# ---------------------------------------------------------------------------
# The tables and tokens other tickets settled.
# ---------------------------------------------------------------------------

ENROLLMENT_TABLE = "enrollment"
NRPS_CALL_TABLE = "nrps_call"

# **`response`'s four references are spelled, not discovered, and E2-05 is why.**
# `20260903_b1e7d4a90c26_a_response_names_one_terms_section_and_week` gives the
# table *composite consistency* foreign keys beside its plain ones —
# `fk_response_section_id_term_id_section` over `(section_id, term_id)` next to
# `fk_response_section_id_section` — so the question "which column points at
# `section`?" has two correct answers and a discovery rule can choose neither.
# `tests/fixtures/survey_windows.py` spells the same three names for the sibling
# table for the same reason.
#
# This is `docs/MISTAKES.md` entry 13's closing sentence in its own right: the
# first version of this file discovered them, and every test that seeded a
# response failed *inside its own fixture* — red for a reason that had nothing to
# do with the deliverable, and red it would have stayed after a correct
# `grading.py` shipped.
RESPONSE_USER_COLUMN = "user_id"
RESPONSE_SECTION_COLUMN = "section_id"
RESPONSE_WEEK_COLUMN = "week_id"
RESPONSE_TERM_COLUMN = "term_id"

# E0-08's own pair and E1-11's platform pair (ADR 0095, that ticket's D3), named
# rather than discovered for the reason `tests/integration/test_identity_schema.py`
# gives: the table carries two dated pairs now, so a rule that chose by shape
# could assert against the wrong one. §3.4's three tiers are exactly a rule for
# choosing between them, which is what makes both names load-bearing here.
STARTED_ON_COLUMN = "started_on"
ENDED_ON_COLUMN = "ended_on"
LMS_WINDOW_START_COLUMN = "lms_window_start"
LMS_WINDOW_END_COLUMN = "lms_window_end"

# E1-11's roster log, whose earliest row per section is tier 3's comparison
# (ADR 0131): "`nrps_call`: `id` uuid PK, `section_id` FK→section RESTRICT NOT
# NULL indexed, ... `called_at` AwareDateTime NOT NULL."
CALLED_AT_COLUMN = "called_at"

# ADR 0055: one `task` column typed as an enum with one member today, and a
# verdict closed per task by a check constraint — `task <> 'COMMENT_VALIDITY' OR
# verdict IN ('substantive', 'insufficient', 'nonsense')`.
CLASSIFICATION_TASK_COLUMN = "task"
CLASSIFICATION_VERDICT_COLUMN = "verdict"
CLASSIFIED_AT_COLUMN = "classified_at"
COMMENT_VALIDITY_TASK = "COMMENT_VALIDITY"

# The three verdicts, transcribed from SPEC §3.3 — "classified by the AI provider
# as **substantive / insufficient / nonsense**" — and from the ticket's fifth
# criterion, which names the two that refuse. They are spelled here rather than
# imported from `app.services.validity` so that a suite about *credit* does not
# take its expectation from the module that decides *validity*
# (`docs/MISTAKES.md` entry 19); the control in
# `test_the_grading_machinery_stands_up_what_it_claims.py` asserts that these two
# are exactly `REFUSED_VERDICTS`, so a divergence is a red naming this constant
# rather than a suite quietly measuring the wrong set.
SUBSTANTIVE = "substantive"
INSUFFICIENT = "insufficient"
NONSENSE = "nonsense"
REFUSING_VERDICTS = (INSUFFICIENT, NONSENSE)

# `app.services.validity`'s own name for the set, for that control.
VALIDITY_SERVICE_MODULE = "app.services.validity"
REFUSED_VERDICTS_NAME = "REFUSED_VERDICTS"

# The column E3-03 must not read (the ticket's own header: "It does **not** read
# `response.is_valid`"). Named so the test that plants a `False` on it can say
# which record it is holding the module to.
RESPONSE_IS_VALID_COLUMN = "is_valid"

# ---------------------------------------------------------------------------
# This suite's own values. None of them is a claim about anything the system
# decides.
# ---------------------------------------------------------------------------

# **A cohort whose course weeks are not its term weeks.** `F` runs six weeks from
# term week 7 (`SEEDED_COHORTS`, transcribed from `scripts/seed.py`), so course
# week 1 is term week 7 and a ledger line that numbered weeks on the term axis
# would read `Week 7` where §3.4 requires `Week 1`. A cohort starting in term
# week 1 cannot tell the two axes apart, which is why no module here uses one.
DEFAULT_COHORT = "F"

# Where the third and fourth shapes come from for a set that is not §3.2's five.
# The five-question set uses `SHAPE_OF_POSITION` — SPEC §3.2's own order — and any
# other count cycles these three, so every set this file can build carries at
# least one comment (the item whose completion depends on a classification) and at
# least one item that counts by existing alone.
SHAPE_CYCLE = ("rating", "comment", "workload")

# The stored text of a comment answer. Nothing classifies it here — the verdict is
# written as a `classification` row by the caller — so its only requirement is
# that it is a comment somebody could have written.
A_COMMENT = "the pacing in week 3 was too fast and the reading load doubled"

# The values a rating and a workload answer carry. Inside SPEC §3.2's bounds so a
# check constraint cannot refuse this fixture's own rows, and read back by
# nothing: what a completed item is worth is the module's answer, not this file's.
A_RATING = Decimal("4")
A_WORKLOAD = Decimal("6.5")

# How far either side of a window's close the development clock is moved. See the
# module docstring: an offset clock cannot stand on an instant, so the pair sits a
# minute apart rather than a microsecond. The mutation it has to survive is a week
# counted or dropped, which is 10,080 times this gap.
A_MINUTE = timedelta(seconds=60)

# The smallest step a `timestamptz` tells apart (PostgreSQL stores microseconds,
# ADR 0019's column type). Used for the tier-1 boundary, which is a comparison
# between two *stored* instants and therefore can be stood on exactly.
A_MOMENT = timedelta(microseconds=1)


class Student(NamedTuple):
    """One enrolled student: the `user` row, the `enrollment` row, and the key a score is under."""

    subject: str
    user: Mapping[str, Any]
    enrollment: Mapping[str, Any]
    user_id: Any


class Score(NamedTuple):
    """One `ParticipationScore`'s four fields, read through `score_fields`."""

    completed: int
    total: int
    percentage: str
    ledger: str


def ledger_line(course_week: int, completed: int, total: int) -> str:
    """SPEC §3.4's line for one week, with all three numbers supplied by the caller.

    Rendering the format string in one place is `docs/MISTAKES.md` entry 13; the
    numbers are never this file's, which is what keeps it from being a second
    implementation of the formula (entry 19).
    """
    return LEDGER_FORMAT.format(course_week=course_week, completed=completed, total=total)


def ledger_of(lines: Iterable[tuple[int, int, int]]) -> str:
    """The whole ledger for a caller-supplied sequence of `(course week, x, y)` triples."""
    return LEDGER_JOIN.join(ledger_line(week, completed, total) for week, completed, total in lines)


def foreign_key_groups(table: Any, target: str) -> dict[Any, list[str]]:
    """Every foreign key on `table` that points at `target`, grouped by its constraint.

    `fixtures.supervision.foreign_key_columns` answers the union of the columns,
    which is the right answer to a different question: a table carrying both a
    plain key and a composite one reports the composite's other column too. Here
    the constraint is the unit, because "does one column name a parent row" is a
    property of a constraint rather than of the table.
    """
    groups: dict[Any, list[str]] = {}
    for key in table.foreign_keys:
        if key.column.table.name != target:
            continue
        groups.setdefault(key.constraint or key, []).append(key.parent.name)
    return groups


def single_column_link(table: Any, target: str) -> str | None:
    """The one column that names a `target` row on its own, or `None` if there is not exactly one."""
    single = sorted(
        {columns[0] for columns in foreign_key_groups(table, target).values() if len(columns) == 1}
    )
    return single[0] if len(single) == 1 else None


def grading_module() -> ModuleType:
    """`app.services.grading`, imported where a test can fail on it rather than error.

    Called from a test body — through `GradingWorld.scores` — and never from a
    fixture, so that on a tree where E3-03 is unbuilt every module here goes red
    on its own criterion with this sentence attached, instead of erroring in
    setup on somebody's missing import.

    An import error *inside* a module that exists is re-raised rather than
    reported as an absent deliverable: those are different failures and reading
    one as the other sends the next person to the wrong file.
    """
    try:
        return import_module(GRADING_SERVICE_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (
            absent == GRADING_SERVICE_MODULE or GRADING_SERVICE_MODULE.startswith(f"{absent}.")
        ):
            raise
        pytest.fail(
            f"`{GRADING_SERVICE_MODULE}` does not exist. E3-03 ships it under "
            "`backend/app/services/` (SPEC §13) as pure computation over a sync `Session`, with "
            f"`{PARTICIPATION_FUNCTION}(session, section, *, settings) -> dict[UUID, "
            f"{SCORE_CLASS}]` — one entry per enrolled student with at least one elapsed enrolled "
            "week, keyed by the enrollment's user id."
        )


def participation_function() -> Any:
    """The one callable E3-03 owes, or a failure naming it and what it answers."""
    module = grading_module()
    function = getattr(module, PARTICIPATION_FUNCTION, None)
    if not callable(function):
        pytest.fail(
            f"`{GRADING_SERVICE_MODULE}` exposes no callable `{PARTICIPATION_FUNCTION}`; it "
            f"exposes {sorted(name for name in vars(module) if not name.startswith('_'))}. E3-03's "
            f"contract: `{PARTICIPATION_FUNCTION}(session, section, *, settings)`, answering a "
            f"mapping from user id to `{SCORE_CLASS}`."
        )
    return function


def score_fields(value: Any) -> Score:
    """One answered score's four fields, or a failure naming the one that is missing.

    Read through this rather than off the object directly so that a contract that
    came back a field short is a **failed assertion naming the field**, not an
    `AttributeError` in the middle of an arithmetic comparison.
    """
    missing = [name for name in SCORE_FIELDS if not hasattr(value, name)]
    if missing:
        pytest.fail(
            f"The value `{PARTICIPATION_FUNCTION}` answered ({value!r}) carries no {missing}. "
            f"E3-03's `{SCORE_CLASS}` is a frozen dataclass of exactly {list(SCORE_FIELDS)}: the "
            "completed items, the denominator, the canonical percentage string, and the per-week "
            "ledger."
        )
    return Score(*(getattr(value, name) for name in SCORE_FIELDS))


class GradingWorld:
    """One section, its calendar, the question set in force, and students enrolled on chosen dates.

    Everything is written inside `db_session`'s transaction and rolled back with
    it: E3-03's contract is a pure computation handed the same `Session`, so
    nothing here needs to be committed and nothing here can leak into another
    test.

    **The window rows are seeded as well as the calendar they derive from.** The
    work order settles that the elapsed set comes from `windows_for_section`,
    which derives; seeding the matching `survey_window` rows costs six inserts and
    means an implementation that reads the materialized rows instead is measured
    on its arithmetic rather than reddened for its route. The instants are
    `WINDOWS_BY_TERM_WEEK`'s — hand-computed and controlled against SPEC §3.1's
    rhythm by `tests/unit/test_the_fall_2026_window_calendar_is_spec_3_1s_rhythm.py`
    — so the rows are the ones a correct derivation writes.
    """

    def __init__(self, calendar: Fall2026) -> None:
        self.calendar = calendar
        self.cohort = DEFAULT_COHORT
        self.length_weeks = 0
        self.first_term_week = 0
        self.section_row: Any = None
        self.section: Any = None
        self.windows: dict[int, Any] = {}
        self.question_sets: dict[int, Any] = {}
        self.questions: dict[int, Any] = {}
        self.shape_of: dict[int, str] = {}
        self.people_chain: dict[str, Any] = {}

    # -- the session and the tables -----------------------------------------

    @property
    def session(self) -> Any:
        return self.calendar.session

    @property
    def tables(self) -> dict[str, Any]:
        return self.calendar.tables

    def seed(self, table_name: str, chain: dict[str, Any] | None = None, **values: Any) -> Any:
        return self.calendar.seed(table_name, {} if chain is None else chain, **values)

    def key_of(self, table_name: str) -> str:
        return single_primary_key(require_table(self.tables, table_name))

    def has_column(self, table_name: str, column: str) -> bool:
        return column in require_table(self.tables, table_name).c

    # -- building ------------------------------------------------------------

    def build(self, *, cohort: str = DEFAULT_COHORT, question_count: int = 5) -> "GradingWorld":
        """Seed the term, its eighteen weeks, one section of `cohort`, its windows and a set.

        `question_count` is the size of the question set in force. Five is SPEC
        §3.2's, and any other count is what the denominator criterion is asked
        with — the ticket's sixth: "a question set with a different number of
        questions produces a different denominator".
        """
        self.cohort = cohort
        self.length_weeks, self.first_term_week, _start = SEEDED_COHORTS[cohort]
        self.calendar.build()
        self.section_row, self.section = self.calendar.cohort(cohort)
        self.windows = {
            course_week: self.seed_window(course_week) for course_week in self.course_weeks
        }
        self.plant_question_set(version=1, question_count=question_count)
        return self

    @property
    def course_weeks(self) -> list[int]:
        """Every course week the section runs, `1` through its length."""
        return list(range(1, self.length_weeks + 1))

    def term_week_of(self, course_week: int) -> int:
        """The term week one course week falls in. SPEC §2.2's two axes, as arithmetic on inputs."""
        return self.first_term_week + course_week - 1

    def closes_at(self, course_week: int) -> datetime:
        """When one course week's window closes, transcribed from the hand-written calendar."""
        return WINDOWS_BY_TERM_WEEK[self.term_week_of(course_week)][1]

    def opens_at(self, course_week: int) -> datetime:
        """When one course week's window opens, from the same table."""
        return WINDOWS_BY_TERM_WEEK[self.term_week_of(course_week)][0]

    def seed_window(self, course_week: int) -> Any:
        """One `survey_window` row for one course week, at the calendar's own instants."""
        term_week = self.term_week_of(course_week)
        opens_at, closes_at = WINDOWS_BY_TERM_WEEK[term_week]
        return self.seed(
            SURVEY_WINDOW_TABLE,
            {},
            **{
                WINDOW_SECTION_COLUMN: self.section_row[self.key_of(SECTION_TABLE)],
                WINDOW_WEEK_COLUMN: self.calendar.weeks[term_week][self.key_of(WEEK_TABLE)],
                WINDOW_TERM_COLUMN: self.calendar.term[self.key_of(TERM_TABLE)],
                WINDOW_OPENS_COLUMN: opens_at,
                WINDOW_CLOSES_COLUMN: closes_at,
            },
        )

    def plant_question_set(self, *, version: int, question_count: int) -> dict[int, Any]:
        """One `question_set` at `version` carrying `question_count` questions.

        The five-question set is SPEC §3.2's in its own order; any other count
        cycles rating, comment and workload, so every set carries at least one
        comment and at least one item that completes by existing alone. The
        questions this world answers through are always the newest planted set,
        which is how the denominator criterion plants a second version over a
        first.
        """
        question_set = self.seed(QUESTION_SET_TABLE, {}, **{VERSION_COLUMN: version})
        self.question_sets[version] = question_set
        chain = {QUESTION_SET_TABLE: question_set}

        table = require_table(self.tables, QUESTION_TABLE)
        found = shape_column(table)
        shape_name, members = found if found is not None else (None, {})

        likert_minimum, likert_maximum, likert_step = LIKERT_BOUNDS
        workload_minimum, workload_maximum, workload_step = WORKLOAD_BOUNDS

        self.questions = {}
        self.shape_of = {}
        for position in range(1, question_count + 1):
            shape = (
                SHAPE_OF_POSITION[position]
                if question_count == len(SHAPE_OF_POSITION)
                else SHAPE_CYCLE[(position - 1) % len(SHAPE_CYCLE)]
            )
            values: dict[str, Any] = {POSITION_COLUMN: position}
            if shape_name is not None:
                values[shape_name] = members[shape]
            if shape == "rating":
                values[MINIMUM_VALUE_COLUMN] = likert_minimum
                values[MAXIMUM_VALUE_COLUMN] = likert_maximum
                values[STEP_COLUMN] = likert_step
            elif shape == "workload":
                values[MINIMUM_VALUE_COLUMN] = workload_minimum
                values[MAXIMUM_VALUE_COLUMN] = workload_maximum
                values[STEP_COLUMN] = workload_step
            self.questions[position] = self.seed(QUESTION_TABLE, chain, **values)
            self.shape_of[position] = shape
        return self.questions

    @property
    def positions(self) -> list[int]:
        """Every question position in the set currently in force."""
        return sorted(self.questions)

    def comment_positions(self) -> list[int]:
        """The positions whose item completes only if a classification does not refuse it."""
        return [position for position in self.positions if self.shape_of[position] == "comment"]

    # -- people --------------------------------------------------------------

    def student(
        self,
        subject: str,
        *,
        started_on: date | None = None,
        ended_on: date | None = None,
        lms_window_start: datetime | None = None,
        lms_window_end: datetime | None = None,
    ) -> Student:
        """One `user` enrolled in this section, on the dates the caller named.

        Every date is the caller's, with one default: `started_on` falls back to
        the section's own start date, which is the day-one member SPEC §3.4's tier
        2 describes. The platform registration is invented by the shared seeding
        walker and shared across this world's students, so two students differ
        only in their subject and their enrollment.
        """
        user = self.seed(USER_TABLE, self.people_chain, lms_user_id=subject)
        values: dict[str, Any] = {
            self.link(ENROLLMENT_TABLE, USER_TABLE): user[self.key_of(USER_TABLE)],
            self.link(ENROLLMENT_TABLE, SECTION_TABLE): self.section_row[
                self.key_of(SECTION_TABLE)
            ],
            STARTED_ON_COLUMN: SEEDED_COHORTS[self.cohort][2] if started_on is None else started_on,
            ENDED_ON_COLUMN: ended_on,
        }
        if self.has_column(ENROLLMENT_TABLE, LMS_WINDOW_START_COLUMN):
            values[LMS_WINDOW_START_COLUMN] = lms_window_start
            values[LMS_WINDOW_END_COLUMN] = lms_window_end
        enrollment = self.seed(ENROLLMENT_TABLE, {}, **values)
        return Student(
            subject=subject,
            user=user,
            enrollment=enrollment,
            user_id=user[self.key_of(USER_TABLE)],
        )

    def link(self, table_name: str, target: str) -> str:
        """The column on `table_name` that names one row of `target` by itself.

        **Counting foreign keys is the wrong question, and it cost this file a
        round.** E2-05 gives `response` a composite consistency key over
        `(section_id, term_id)` beside the plain `section_id` one, so a rule
        asking "which columns here point at `section`?" gets `section_id` *and*
        `term_id` back and refuses a table that is perfectly well formed. The
        question that has an answer is which **single-column** foreign key names a
        `target` row, because that is the one a seeded row can fill on its own.

        Composite keys are not ignored — the row still has to satisfy them, and it
        does, because every column they range over is filled from the same
        containment chain.
        """
        table = require_table(self.tables, table_name)
        found = single_column_link(table, target)
        if found is None:
            groups = {
                str(getattr(constraint, "name", None) or "<unnamed>"): columns
                for constraint, columns in foreign_key_groups(table, target).items()
            }
            pytest.fail(
                f"No single-column foreign key on `{table_name}` names a `{target}` row. Its keys "
                f"to `{target}` are {groups}, and every column it references there is "
                f"{foreign_key_columns(table, target)}. This fixture addresses a row by one "
                "column; a table that names its parent only through a composite key needs its "
                "column spelled outright, the way `response`'s four are at the top of this file."
            )
        return found

    def require_response_columns(self) -> None:
        """Check `response` really carries the four columns this file spells.

        Spelling a column is faster than discovering one and it goes stale
        silently, so the four are checked once per seeded response and a rename
        fails here — naming the column and the record that settled it — rather
        than inside an `INSERT` that reports an undefined column.
        """
        table = require_table(self.tables, RESPONSE_TABLE)
        missing = [
            column
            for column in (
                RESPONSE_USER_COLUMN,
                RESPONSE_SECTION_COLUMN,
                RESPONSE_WEEK_COLUMN,
                RESPONSE_TERM_COLUMN,
            )
            if column not in table.c
        ]
        if missing:
            pytest.fail(
                f"`{RESPONSE_TABLE}` declares no {missing} (it declares "
                f"{[column.name for column in table.columns]}). E2-05 settles all four — E3-03's "
                "ticket cites `week_id` and `term_id` by line, and E2-08's work order says the "
                f"submit path 'writes `{RESPONSE_TABLE}.{RESPONSE_USER_COLUMN}`'. They are spelled "
                "rather than discovered because the table's composite consistency keys make "
                "discovery ambiguous; see the constants at the top of this file."
            )

    def roster_sync_at(self, called_at: datetime) -> Any:
        """One `nrps_call` row for this section, at the instant the caller named.

        Tier 3's comparison is against the **section's earliest** call (ADR 0131),
        so a test that wants a late first sync seeds one row and a test that wants
        no sync history seeds none — which is the tier-2 state seeded data is in.
        """
        return self.seed(
            NRPS_CALL_TABLE,
            {},
            **{
                self.link(NRPS_CALL_TABLE, SECTION_TABLE): self.section_row[
                    self.key_of(SECTION_TABLE)
                ],
                CALLED_AT_COLUMN: called_at,
            },
        )

    # -- what a student answered ---------------------------------------------

    def answer_week(
        self,
        student: Student,
        course_week: int,
        *,
        positions: Sequence[int] | None = None,
        verdicts: Mapping[int, str] | None = None,
        unclassified: Sequence[int] = (),
        is_valid: bool | None = None,
    ) -> dict[int, Any]:
        """One `response` for one student and week, with an `answer` row per position.

        `positions` defaults to every position in the set — a fully answered week.
        A position left out is an item not completed, which is what a blank
        optional comment is on the wire (ADR 0115 deletes a withdrawn answer's
        row, so an absent row is the faithful record). `verdicts` names the
        verdict written for a comment position; a comment answered without one
        gets `substantive`, so a caller only spells the verdict it is asking
        about. A position named in `unclassified` is answered and left with no
        `classification` row at all — a state the fail-open floor makes
        unreachable in production (`app/ai/tasks.py` writes a floored verdict), and
        which the work order settles as counting if it ever occurred.

        `is_valid` writes the column E3-03 must not read. It is set only where the
        caller names it, so an ordinary row carries whatever the schema defaults
        to and no test here depends on that default.
        """
        answered = self.positions if positions is None else list(positions)
        verdicts = {} if verdicts is None else verdicts

        self.require_response_columns()
        values: dict[str, Any] = {
            RESPONSE_USER_COLUMN: student.user_id,
            RESPONSE_SECTION_COLUMN: self.section_row[self.key_of(SECTION_TABLE)],
            RESPONSE_WEEK_COLUMN: self.calendar.weeks[self.term_week_of(course_week)][
                self.key_of(WEEK_TABLE)
            ],
            RESPONSE_TERM_COLUMN: self.calendar.term[self.key_of(TERM_TABLE)],
        }
        if self.has_column(RESPONSE_TABLE, "submitted_at"):
            values["submitted_at"] = self.closes_at(course_week) - timedelta(hours=1)
        # E2-05 gives `response` a `week_id` and a `term_id` and no ticket says
        # whether it also points at the `survey_window` row. Where it does, the
        # window this week's response belongs to is named rather than left to the
        # seeding walker, which would build a *second* window with invented
        # instants and put the response under a week the section does not have.
        window_column = single_column_link(
            require_table(self.tables, RESPONSE_TABLE), SURVEY_WINDOW_TABLE
        )
        if window_column is not None:
            values[window_column] = self.windows[course_week][self.key_of(SURVEY_WINDOW_TABLE)]
        if is_valid is not None:
            values[RESPONSE_IS_VALID_COLUMN] = is_valid
        response = self.seed(RESPONSE_TABLE, {}, **values)

        rows: dict[int, Any] = {}
        for position in answered:
            rows[position] = self.seed_answer(response, position)
            if self.shape_of[position] == "comment" and position not in unclassified:
                self.classify(
                    rows[position],
                    verdicts.get(position, SUBSTANTIVE),
                    classified_at=self.closes_at(course_week) - timedelta(minutes=30),
                )
        return rows

    def seed_answer(self, response: Mapping[str, Any], position: int) -> Any:
        """One `answer` row on one response, carrying the value column its shape uses."""
        shape = self.shape_of[position]
        value_column = {
            "rating": RATING_COLUMN,
            "comment": COMMENT_TEXT_COLUMN,
            "workload": WORKLOAD_HOURS_COLUMN,
        }[shape]
        value = {"rating": A_RATING, "comment": A_COMMENT, "workload": A_WORKLOAD}[shape]
        return self.seed(
            ANSWER_TABLE,
            {},
            **{
                self.link(ANSWER_TABLE, RESPONSE_TABLE): response[self.key_of(RESPONSE_TABLE)],
                self.link(ANSWER_TABLE, QUESTION_TABLE): self.questions[position][
                    self.key_of(QUESTION_TABLE)
                ],
                value_column: value,
            },
        )

    def classify(
        self,
        answer: Mapping[str, Any],
        verdict: str,
        *,
        classified_at: datetime,
        classification_id: Any = None,
    ) -> Any:
        """Append one `classification` row for one comment answer.

        Append, always: the table is append-only (ADR 0055, and `pulse_app` holds
        `SELECT, INSERT` and nothing else), so the way a later verdict changes the
        answer is a **new row**, which is what the ticket's fifth criterion
        requires a test to demonstrate.

        **`classification_id` exists so one test can make its own kill
        deterministic.** Primary keys here are server-generated random uuids (ADR
        0016), so which of two rows has the larger id is a coin toss — and a test
        distinguishing "the latest by `classified_at`" from "the largest id" then
        kills its mutation only about half the time, which is a test that passes
        for a reason unrelated to what it asserts on the other runs
        (`docs/MISTAKES.md` entry 3). Given an id, the row is planted with it.
        Left `None`, which is every other caller, the database chooses.
        """
        chosen: dict[str, Any] = (
            {}
            if classification_id is None
            else {self.key_of(CLASSIFICATION_TABLE): classification_id}
        )
        return self.seed(
            CLASSIFICATION_TABLE,
            {},
            **chosen,
            **{
                ANSWER_ID_COLUMN: answer[self.key_of(ANSWER_TABLE)],
                CLASSIFICATION_TASK_COLUMN: COMMENT_VALIDITY_TASK,
                CLASSIFICATION_VERDICT_COLUMN: verdict,
                CLASSIFIED_AT_COLUMN: classified_at,
            },
        )

    def classifications_of(self, answer: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Every `classification` row naming one answer, for the append-only control."""
        from sqlalchemy import select

        table = require_table(self.tables, CLASSIFICATION_TABLE)
        statement = select(table).where(
            table.c[ANSWER_ID_COLUMN] == answer[self.key_of(ANSWER_TABLE)]
        )
        return [dict(row) for row in self.session.execute(statement).mappings()]

    def drop(self, student: Student, *, ended_on: date) -> None:
        """Set one enrollment's `ended_on`, the way a roster sync records a drop."""
        from sqlalchemy import update

        table = require_table(self.tables, ENROLLMENT_TABLE)
        key = self.key_of(ENROLLMENT_TABLE)
        self.session.execute(
            update(table)
            .where(table.c[key] == student.enrollment[key])
            .values(**{ENDED_ON_COLUMN: ended_on})
        )

    # -- the clock -----------------------------------------------------------

    def elapsed_through(self, overrides: Any, course_week: int) -> datetime:
        """Move the development clock to a minute after one course week's window closed.

        Every earlier course week has closed too, so the elapsed set is `1 ..
        course_week` — for the section. Which of those weeks a *student* is
        credited with is §3.4's tier question and is never decided here.
        """
        pretend_now = self.closes_at(course_week) + A_MINUTE
        overrides.set(pretend_now=pretend_now, anchored_at=datetime.now(UTC))
        return pretend_now

    def not_yet_closed(self, overrides: Any, course_week: int) -> datetime:
        """The other half of `elapsed_through`: a minute *before* that window closes.

        The elapsed set is then `1 .. course_week - 1`, and for course week 1 it is
        empty — which is the state SPEC §3.4 says has no score at all rather than a
        zero.
        """
        pretend_now = self.closes_at(course_week) - A_MINUTE
        overrides.set(pretend_now=pretend_now, anchored_at=datetime.now(UTC))
        return pretend_now

    # -- asking ---------------------------------------------------------------

    def scores(self, *, settings: Any) -> Mapping[Any, Any]:
        """`participation_scores` over this section, with everything seeded flushed first."""
        function = participation_function()
        self.session.flush()
        return function(self.session, self.section, settings=settings)

    def score_for(self, student: Student, *, settings: Any) -> Score:
        """One student's four fields, or a failure saying the mapping had no entry for them."""
        answered = self.scores(settings=settings)
        if student.user_id not in answered:
            pytest.fail(
                f"`{PARTICIPATION_FUNCTION}` answered no entry for {student.subject!r} (user "
                f"{student.user_id}); it answered keys {sorted(map(str, answered))}. Absence is "
                "E3-03's 'nothing to post' and means the module credits this student with no "
                "elapsed enrolled week at all, which is a different claim from a zero."
            )
        return score_fields(answered[student.user_id])


@pytest.fixture
def grading_world(fall_2026: Fall2026) -> GradingWorld:
    """The world E3-03 is measured over, unbuilt — the caller chooses the cohort and the set.

    Unbuilt for `docs/MISTAKES.md` entry 30's reason: how many questions the set
    in force carries is exactly what the denominator criterion is about, and a
    fixture that chose it would be answering that criterion.
    """
    return GradingWorld(fall_2026)
