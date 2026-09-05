"""E3-06 — one section that is both a gradebook and a term's worth of answers, and the sweep's names.

Six test modules need the same three things, and no fixture in this repository
answers any of them on its own:

  - **A section the AGS client can really post to *and* that the participation
    formula can really score.** `tests/fixtures/ags_client.py`'s `ags_sections`
    gives the first — a registered platform, a section bound to its own
    deployment, and the line-item container the launch advertises — and
    `tests/fixtures/grading.py`'s `GradingWorld` gives the second — a term, its
    weeks, a cohort whose course weeks are not its term weeks, students enrolled
    on chosen dates, and answers carrying chosen verdicts. They cannot simply be
    used side by side: the first seeds committed rows on `committed_rows`'
    connection and the second seeds uncommitted rows on `db_session`'s, so a
    sweep handed either session sees half the world. `SweptWorld` below is
    `GradingWorld` built **onto a section that already exists**, on
    `committed_rows`' session throughout, which is the one shape that puts both
    halves in front of one call.

  - **What is in `grade_sync`, planted by the test and read back.**
    `docs/MISTAKES.md` entry 31 is named in this ticket's own traps list: the
    idempotence case starts from a row written by something other than the run
    under test. `GradeSyncRows` is that writer, and its reader answers *every*
    row for a pair newest-first, because ADR 0124 makes "the latest row" the
    lookup and a reader that could only answer one row could not also say the
    older one survived.

  - **The names E3-06's work order settles.** They are spelled here, not
    discovered, because the work order settles every one of them (D1 to D7).
    Discovery would be inventing an interface the ticket has already fixed.

**Every guard is a plain function called from a test body, never a fixture.**
`docs/MISTAKES.md` entry 44: on a tree where E3-06 is unbuilt each module must
go red as a FAILED naming the deliverable, not as an ERROR in somebody's setup.
`grading_module`, `named_in` and `tasks_module` are imported from
`tests/fixtures/line_item_creation.py` rather than written again, which is the
same rule one file over.

**Nothing here computes a score, a percentage, a ledger or a timestamp.** Every
expected value in these suites comes from `participation_scores` — E3-03's
deliverable, already built and asserted by its own seven modules — or from the
platform's own record of what it was sent. A fixture that derived any of them
would be a second implementation for the tests to agree with
(`docs/MISTAKES.md` entry 19), and criterion 4's whole subject is a comparison
between the formula's ledger and the platform's copy of it.

**The environment, and it is a requirement this file makes of its callers.**
Nothing here builds `Settings` — but the five module guards below (`sweep_function`,
`score_timestamp_text`, `grace_days`, `post_scores_task` and `schedules_module`)
import `app.services.grading`, `app.jobs.tasks` and `app.jobs.schedules`, and
`app.jobs.tasks` imports `app.db`, which builds `Settings()` at module scope. So
**every module that calls one of them must have `configured_env` somewhere in its
fixture chain** (`docs/MISTAKES.md` entry 40). The six integration modules get it
from `window_settings` (`tests/fixtures/survey_windows.py`), which states
`ENVIRONMENT=development` and `INSTITUTION_TIMEZONE=America/New_York` over
`configured_env`'s documented values; the unit module has no database and no
clock, so it declares an autouse `_a_stated_environment` of its own.

That sentence is here because its absence cost a red CI run: the unit module
passed on every developer machine, where `.env` is exported, and failed on the
xdist worker that happened to run it first, on a `ConfigurationError` naming
`DATABASE_URL`. A fixture is where the declaration belongs, and the import is
this file's.

Development is required twice over: it is the only environment where the clock
override applies at all (ADR 0109 part 4), and it is what makes the mock
platform's own cleartext gradebook address reachable (ADR 0081).
"""

from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

import pytest

from fixtures.ags_client import (
    SCORE_COMMENT_MEMBER,
    SCORE_GIVEN_MEMBER,
    SCORE_MAXIMUM_SENT_MEMBER,
    SCORE_TIMESTAMP_MEMBER,
    SCORE_USER_MEMBER,
    SECTION_CONTAINER_COLUMN,
    SECTION_LINE_ITEM_COLUMN,
    rewrite_section,
    scores_posted,
)
from fixtures.grading import (
    ENDED_ON_COLUMN,
    ENROLLMENT_TABLE,
    INSUFFICIENT,
    NONSENSE,
    SUBSTANTIVE,
    GradingWorld,
    Student,
    score_fields,
)
from fixtures.line_item_creation import (
    REQUEST_LINE_ITEM_CREATION,
    grading_module,
    named_in,
    tasks_module,
)
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import (
    COHORT_SECTION_MODALITY,
    COHORT_SECTION_ORDINAL,
    FALL_2026_TERM_WEEKS,
    INSTITUTION_TIMEZONE,
    SECTION_CODE_COLUMN,
    SECTION_END_COLUMN,
    SECTION_LENGTH_COLUMN,
    SECTION_START_COLUMN,
    SECTION_TABLE,
    SEEDED_COHORTS,
    TERM_TABLE,
    WEEK_NUMBER_COLUMN,
    WEEK_TABLE,
    Fall2026,
)

# ---------------------------------------------------------------------------
# The contract E3-06's work order settles (D1 to D7), spelled once.
# ---------------------------------------------------------------------------

# D1: the sweep lives in `backend/app/services/grading.py` (SPEC §13 names that
# module "participation formula + AGS passback"). The package root is
# `backend/`, so the import path is `app.services.grading`.
GRADING_MODULE = "app.services.grading"
GRADING_LOGGER = GRADING_MODULE

# D1's public entry point, and the two keys of the dict it answers with. Ints,
# because the task returns the dict and a Celery result has to be serialisable.
SWEEP_FUNCTION = "post_scores_for_all_sections"
POSTED_KEY = "posted"
FAILED_KEY = "failed"

# D5: the one place a wire timestamp is rendered, so a stored `score_timestamp`
# re-renders to the exact bytes originally sent. That is what makes D4's retry
# reconstruction sound, and it is why this is a public name rather than a detail.
SCORE_TIMESTAMP_TEXT = "score_timestamp_text"

# D7: the bound on the walk. A section is swept while
# `term.end_date + TERM_SWEEP_GRACE_DAYS >= clock.today`.
GRACE_DAYS_NAME = "TERM_SWEEP_GRACE_DAYS"
GRACE_DAYS = 14

# D2 and D3: the thin task and the beat entry that fires it.
TASKS_MODULE = "app.jobs.tasks"
TASKS_LOGGER = TASKS_MODULE
POST_SCORES_TASK = "post_participation_scores"
SCHEDULES_MODULE = "app.jobs.schedules"
BEAT_SCHEDULE_NAME = "BEAT_SCHEDULE"
BEAT_ENTRY_NAME = "post-participation-scores-weekly"
BEAT_DAY_OF_WEEK = "mon"
BEAT_HOUR = "2"
BEAT_MINUTE = "20"

# E3-02's append-only log, and the columns SPEC §8 gives it. Transcribed from
# `tests/integration/test_the_passback_tables_record_one_post_per_row.py`'s
# `GRADE_SYNC_REQUIRED` rather than imported, for the reason that module gives
# about not importing an expectation out of what it measures.
GRADE_SYNC_TABLE = "grade_sync"
SCORE_TEXT_COLUMN = "score_text"
SCORE_TIMESTAMP_COLUMN = "score_timestamp"
LEDGER_TEXT_COLUMN = "ledger_text"
OUTCOME_COLUMN = "outcome"
RESPONSE_CODE_COLUMN = "response_code"
CREATED_AT_COLUMN = "created_at"

# The two outcome values, matched case-insensitively by fragment against
# whatever the column declares. Fragments rather than spellings, because E3-02
# settles that the set is two and this file has no business deciding whether
# they are written `posted` or `POSTED`.
POSTED_FRAGMENT = "post"
FAILED_FRAGMENT = "fail"

AGS_CALL_TABLE = "ags_call"

# E0-08's own column, named because the drop boundary is asserted on it.
USER_TABLE = "user"
LMS_USER_ID_COLUMN = "lms_user_id"

# E0-06's `term.end_date`, which D7's bound is measured from. Spelled separately
# from `section.end_date` even though the two tables use one name, because the
# bound is a fact about the *term* and a reader has to be able to see which.
TERM_END_COLUMN = "end_date"

# ---------------------------------------------------------------------------
# This suite's own values. None of them is a claim about anything the system
# decides, and each is chosen so a mutation cannot leave it unchanged.
# ---------------------------------------------------------------------------

# The cohort every world here is built on. `F` runs six weeks from term week 7
# (`SEEDED_COHORTS`), so course week 1 is term week 7 — a section whose course
# weeks are not its term weeks, which is the only kind that can tell the two
# axes apart. E3-03's own suites use it for the same reason.
DEFAULT_COHORT = "F"

# A score string and a ledger nothing in the system would produce, for planting
# a `grade_sync` row that **differs** from what the formula computes. `77.25`
# is not a value the six-week cohort's item arithmetic can reach, and the
# ledger names a week the section does not have.
A_DIFFERING_SCORE = "77.25"
A_DIFFERING_LEDGER = "Week 9: 1 of 5 items"

# The distinctive past instant a planted FAILED row carries, for the retry test.
# **Microseconds on purpose**: `score_timestamp_text` is
# `instant.astimezone(UTC).isoformat()`, so this renders as
# `2026-03-02T14:05:09.123456+00:00` — a string no fresh `datetime.now(UTC)`
# call in this decade can produce by accident, and one that a re-derivation
# through a whole-second clock loses.
A_STORED_TIMESTAMP = datetime(2026, 3, 2, 14, 5, 9, 123456, tzinfo=UTC)

# An instant later than any real clock this suite can run under, for planting a
# score the platform already holds so that the sweep's own post is strictly
# earlier — which is the out-of-order passback AGS answers 409 to (ADR 0052).
# Far future rather than merely later, because the sweep stamps **real** time
# (D6) and this has to beat a real clock rather than a pretended one.
A_FUTURE_TIMESTAMP = "2031-01-01T00:00:00+00:00"

# The score the platform holds in that case, distinct from anything the formula
# produces so a reader can tell which delivery it came from.
A_HELD_SCORE = 88.5

# How far either side of a window's close the development clock is moved.
# `tests/fixtures/grading.py`'s own constant and its reasoning: an offset clock
# (ADR 0109) cannot stand on an instant, so the pair sits a minute apart rather
# than a microsecond, and a minute is four orders of magnitude inside the week
# it has to be distinguished from.
A_MINUTE = timedelta(seconds=60)

A_DAY = timedelta(days=1)

# Where "today" is stood inside the institution's own day when a test moves the
# clock to a date rather than to an instant. Noon, so neither end of the day is
# near a zone boundary and the date is the same one in UTC and in
# `America/New_York` — the two ends of §3.1's own conversion.
NOON = 12

# ---------------------------------------------------------------------------
# The deliverables, named where a test can fail on them rather than error.
# ---------------------------------------------------------------------------

SWEEP_IS_OWED = (
    "E3-06's work order (D1) puts the sweep there, in the module SPEC §13 names 'participation "
    f"formula + AGS passback': `{SWEEP_FUNCTION}(session, *, settings, http=None, resolve=None) -> "
    'dict[str, int]`, answering `{"posted": p, "failed": f}`. For each section with a line item '
    "whose term is still inside the sweep's bound, for each student holding a live enrollment, it "
    "computes through `participation_scores`, compares against the latest `grade_sync` row for "
    "that student and section, and posts through E3-04's client only where they differ."
)

TASK_IS_OWED = (
    f"E3-06's work order (D2) adds `{POST_SCORES_TASK}()` to `{TASKS_MODULE}`, on "
    "`derive_survey_windows`'s shape: no arguments, open a session, call "
    f"`{GRADING_MODULE}.{SWEEP_FUNCTION}`, commit once, return the service's dict."
)

TIMESTAMP_TEXT_IS_OWED = (
    f"E3-06's work order (D5) puts `{SCORE_TIMESTAMP_TEXT}(instant: datetime) -> str` at module "
    "level in `app/services/grading.py`, defined as `instant.astimezone(UTC).isoformat()`. Every "
    "wire timestamp goes through it, so a stored `score_timestamp` re-renders to the exact bytes "
    "originally sent — which is what makes ADR 0052's retry identity reconstructible from the row."
)

GRACE_DAYS_IS_OWED = (
    f"E3-06's work order (D7) puts `{GRACE_DAYS_NAME}: Final[int] = {GRACE_DAYS}` at module level "
    "in `app/services/grading.py`. The sweep walks a section only while `term.end_date + "
    f"{GRACE_DAYS_NAME} >= clock.today`, which gives a finished term two more sweeps — the final "
    "week's post plus one corrective pass — and stops the walk well before §4's retention purge "
    "could have it recompute against deleted comments."
)


def sweep_function() -> Any:
    """`post_scores_for_all_sections`, or a failure naming the deliverable that owes it."""
    return named_in(grading_module(), SWEEP_FUNCTION, SWEEP_IS_OWED)


def score_timestamp_text() -> Any:
    """`score_timestamp_text`, or a failure naming it."""
    return named_in(grading_module(), SCORE_TIMESTAMP_TEXT, TIMESTAMP_TEXT_IS_OWED)


def grace_days() -> Any:
    """`TERM_SWEEP_GRACE_DAYS`, or a failure naming it."""
    return named_in(grading_module(), GRACE_DAYS_NAME, GRACE_DAYS_IS_OWED)


def post_scores_task() -> Any:
    """`post_participation_scores`, or a failure naming the deliverable that owes it."""
    return named_in(tasks_module(), POST_SCORES_TASK, TASK_IS_OWED)


def schedules_module() -> Any:
    """`app.jobs.schedules`, imported where a test can fail on it rather than error.

    E2-06 already ships it and `app.jobs.celery_app` wires `BEAT_SCHEDULE` in, so
    on today's tree this answers; the guard is here for the same reason every
    other module guard in this suite is (`docs/MISTAKES.md` entry 44), and
    because an import at a test module's top level would be a collection error
    rather than a red.
    """
    import importlib

    try:
        return importlib.import_module(SCHEDULES_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (
            absent == SCHEDULES_MODULE or SCHEDULES_MODULE.startswith(f"{absent}.")
        ):
            raise
        pytest.fail(
            f"`{SCHEDULES_MODULE}` does not exist. E2-06 ships it with `{BEAT_SCHEDULE_NAME}`, the "
            "one place this project's periodic work is declared, and `app.jobs.celery_app` wires "
            f"it onto the Celery application; E3-06's work order (D3) adds the "
            f"{BEAT_ENTRY_NAME!r} entry to it."
        )


def run_sweep(
    session: Any,
    *,
    settings: Any,
    http: Any,
    resolve: Any = None,
) -> tuple[Any, BaseException | None]:
    """Call the sweep, answering what it returned and what escaped it.

    Answering the exception rather than letting it fly is E3-04's driver's
    choice and it is made here for the same reason: criterion 8 is about a
    sweep that does **not** raise, and a test that let one propagate would
    report the escape as a stack trace over an assertion that never ran.
    Criterion tests assert `raised is None` themselves, in the open, so the
    tolerance is the driver's and never an assertion's.
    """
    sweep = sweep_function()
    keywords: dict[str, Any] = {"settings": settings, "http": http}
    if resolve is not None:
        keywords["resolve"] = resolve
    try:
        return sweep(session, **keywords), None
    except Exception as escaped:
        return None, escaped


# ---------------------------------------------------------------------------
# `grade_sync`, planted by the test and read back newest-first.
# ---------------------------------------------------------------------------


class GradeSyncRows:
    """What is in `grade_sync`, written by this suite and read on a connection that sees commits.

    **Planted by the test, which is this ticket's named trap.**
    `docs/MISTAKES.md` entry 31 — "'running it twice is safe' was tested only
    against a database the loader itself had filled" — is called out by name in
    E3-06's own known-traps section, so the idempotence and re-post cases start
    from rows written here rather than from a first run of the thing under test.

    **The reader answers every row for a pair, newest first.** ADR 0124 makes
    "the latest row for a `(section_id, user_id)` pair" the lookup every reader
    of this table performs, and criterion 3 needs the *older* row to still be
    there afterwards — two questions a `LIMIT 1` cannot answer together.
    """

    def __init__(self, rows: Any, tables: dict[str, Any]) -> None:
        self.rows = rows
        self.tables = tables

    # -- reaching the table --------------------------------------------------

    def table(self) -> Any:
        table = self.tables.get(GRADE_SYNC_TABLE)
        if table is None:
            pytest.fail(
                f"There is no `{GRADE_SYNC_TABLE}` table (there are {sorted(self.tables)}). SPEC §8 "
                "names it and E3-02 builds it: one row per post, append-only, carrying the score as "
                "sent, the timestamp sent with it, the ledger, the outcome, the response code and "
                "the student and section it concerns."
            )
        missing = [
            column
            for column in (
                SCORE_TEXT_COLUMN,
                SCORE_TIMESTAMP_COLUMN,
                LEDGER_TEXT_COLUMN,
                OUTCOME_COLUMN,
                RESPONSE_CODE_COLUMN,
                CREATED_AT_COLUMN,
            )
            if column not in table.c
        ]
        if missing:
            pytest.fail(
                f"`{GRADE_SYNC_TABLE}` declares no {missing} (it declares "
                f"{[column.name for column in table.columns]}). E3-02 settles all six, and E3-06's "
                "comparison reads three of them: the score string, the ledger string and the "
                "timestamp that was sent."
            )
        return table

    def link(self, target: str) -> str:
        """The one column on `grade_sync` whose foreign key names a row of `target`."""
        table = self.table()
        found = sorted(
            {key.parent.name for key in table.foreign_keys if key.column.table.name == target}
        )
        if len(found) != 1:
            pytest.fail(
                f"`{GRADE_SYNC_TABLE}` has {len(found)} foreign keys into `{target}` ({found}); it "
                f"references {sorted({key.column.table.name for key in table.foreign_keys})}. SPEC "
                "§8 gives each row exactly one student and one section, and these tests address "
                "rows through those two columns."
            )
        return found[0]

    def outcomes(self) -> dict[str, str]:
        """The two values `grade_sync.outcome` declares, mapped to what each means.

        Read off the column so this file does not decide the spelling — the
        transcription of `outcome_values` in
        `tests/integration/test_the_passback_tables_record_one_post_per_row.py`,
        and transcribed rather than imported for the reason that module gives
        about two inventories of one closed set.
        """
        table = self.table()
        declared = list(getattr(table.c[OUTCOME_COLUMN].type, "enums", ()) or ())
        if len(declared) != 2:
            pytest.fail(
                f"`{GRADE_SYNC_TABLE}.{OUTCOME_COLUMN}` declares {declared}, which is not the closed "
                "set of two E3-02 settles: a post reached the platform, or it did not. An empty "
                "list means the column carries no enumerated type at all, and this suite cannot "
                "name an outcome it plants without one."
            )
        found: dict[str, str] = {}
        for meaning, fragment in (("posted", POSTED_FRAGMENT), ("failed", FAILED_FRAGMENT)):
            matching = [value for value in declared if fragment in value.lower()]
            if len(matching) != 1:
                pytest.fail(
                    f"`{GRADE_SYNC_TABLE}.{OUTCOME_COLUMN}` declares {declared}, of which "
                    f"{matching} carry {fragment!r}. This file tells the two outcomes apart by "
                    "fragment so the spelling stays E3-02's choice, and it cannot do that against "
                    "these two names."
                )
            found[meaning] = matching[0]
        return found

    # -- planting ------------------------------------------------------------

    def plant(
        self,
        *,
        section_id: Any,
        user_id: Any,
        score_text: str,
        ledger_text: str,
        outcome: str,
        score_timestamp: datetime,
        created_at: datetime,
        response_code: int | None = None,
    ) -> Any:
        """One `grade_sync` row, exactly as this test chose it, committed.

        Every value is the caller's. `created_at` in particular is never
        defaulted: which of two rows is the latest is the whole subject of ADR
        0124's warning, and a fixture that stamped it would be answering that
        question rather than posing it.
        """
        self.table()
        planted = self.rows.seed(
            GRADE_SYNC_TABLE,
            {},
            **{
                self.link(SECTION_TABLE): section_id,
                self.link(USER_TABLE): user_id,
                SCORE_TEXT_COLUMN: score_text,
                LEDGER_TEXT_COLUMN: ledger_text,
                OUTCOME_COLUMN: outcome,
                SCORE_TIMESTAMP_COLUMN: score_timestamp,
                CREATED_AT_COLUMN: created_at,
                RESPONSE_CODE_COLUMN: response_code,
            },
        )
        self.rows.commit()
        return planted

    # -- reading -------------------------------------------------------------

    def for_pair(self, section_id: Any, user_id: Any) -> list[dict[str, Any]]:
        """Every row for one student and section, newest `created_at` first.

        The transaction is ended first so a row the task's own connection
        committed is visible: the sweep may be driven through the Celery task,
        which opens a session of its own, and a session holding a transaction
        since it seeded would go on seeing the table as it was — which this
        suite would read as "nothing was written".
        """
        from sqlalchemy import select

        table = self.table()
        self.rows.commit()
        statement = (
            select(table)
            .where(
                table.c[self.link(SECTION_TABLE)] == section_id,
                table.c[self.link(USER_TABLE)] == user_id,
            )
            .order_by(table.c[CREATED_AT_COLUMN].desc())
        )
        return [dict(row) for row in self.rows.session.execute(statement).mappings()]

    def all_rows(self) -> list[dict[str, Any]]:
        """Every `grade_sync` row there is, for the assertions about absence."""
        self.rows.commit()
        return [dict(row) for row in self.rows.session.execute(self.table().select()).mappings()]

    def calls(self) -> list[dict[str, Any]]:
        """Every `ags_call` row there is, read the same way."""
        table = self.tables.get(AGS_CALL_TABLE)
        if table is None:
            pytest.fail(
                f"There is no `{AGS_CALL_TABLE}` table (there are {sorted(self.tables)}). SPEC §6.1 "
                "puts it at the grain of one HTTP call the tool made to a platform service, and "
                "E3-02 builds it; criterion 2 reads it as the second witness that no call was made."
            )
        self.rows.commit()
        return [dict(row) for row in self.rows.session.execute(table.select()).mappings()]


# ---------------------------------------------------------------------------
# One section that is both a gradebook and a term's worth of answers.
# ---------------------------------------------------------------------------


class SweptWorld(GradingWorld):
    """`GradingWorld`, built onto a section that already exists rather than one it seeds.

    Everything about students, answers, verdicts, windows and the clock is
    inherited unchanged — `student`, `answer_week`, `classify`, `drop`,
    `elapsed_through`, `not_yet_closed`, `scores` and `score_for` are E3-03's
    fixture's and are not re-implemented here. What `build_on` replaces is the
    six lines of `GradingWorld.build` that seed a section of their own, because
    the section this suite needs was seeded by `ags_sections` and is bound to a
    platform, a deployment and a gradebook container that no calendar fixture
    knows how to produce.

    **The term is already the right one.** `fixtures/supervision.py`'s seeding
    walker invents a term running 2026-08-17 to 2026-12-20 over eighteen weeks
    — the Fall 2026 calendar `tests/fixtures/survey_windows.py` writes out by
    hand — so the section's own term needs no rewriting and the hand-written
    window instants apply to it. What is rewritten is the *section's* calendar:
    the cohort's length and start date, which `SEEDED_COHORTS` transcribes from
    `scripts/seed.py`. Those are inputs to the derivation under test and never
    its output (`docs/MISTAKES.md` entry 30).

    **The students carry the platform's own subjects.** `user.lms_user_id` is
    the AGS `userId`, so a score posted for one of these is a score for a
    student the platform demonstrably knows — which is what makes the readback
    from `GET /mock/posted-scores` a statement about this section rather than
    about a string this file made up.
    """

    def __init__(self, calendar: Fall2026, rows: Any) -> None:
        super().__init__(calendar)
        self.rows = rows

    def committed_row(self, table_name: str, key_value: Any) -> dict[str, Any]:
        """One committed row of `table_name`, addressed by its primary key."""
        table = require_table(self.tables, table_name)
        key = single_primary_key(table)
        self.rows.commit()
        found = list(
            self.session.execute(table.select().where(table.c[key] == key_value)).mappings()
        )
        if len(found) != 1:
            pytest.fail(
                f"There are {len(found)} `{table_name}` rows keyed {key_value!r}, and this fixture "
                f"needs exactly one: {[dict(row) for row in found]}."
            )
        return dict(found[0])

    def build_on(self, section_id: Any, *, cohort: str, question_count: int) -> "SweptWorld":
        """Give an existing section a calendar, its windows and a question set."""
        calendar = self.calendar
        self.cohort = cohort
        self.length_weeks, self.first_term_week, start = SEEDED_COHORTS[cohort]

        section = self.committed_row(SECTION_TABLE, section_id)
        term_id = section[self.link(SECTION_TABLE, TERM_TABLE)]
        calendar.term = self.committed_row(TERM_TABLE, term_id)
        calendar.chain = {TERM_TABLE: calendar.term}
        calendar.weeks = {
            number: calendar.seed(WEEK_TABLE, calendar.chain, **{WEEK_NUMBER_COLUMN: number})
            for number in range(1, FALL_2026_TERM_WEEKS + 1)
        }

        rewrite_section(
            self.rows,
            self.tables,
            section_id,
            **{
                SECTION_CODE_COLUMN: f"{cohort}{COHORT_SECTION_ORDINAL}{COHORT_SECTION_MODALITY}",
                SECTION_LENGTH_COLUMN: self.length_weeks,
                SECTION_START_COLUMN: start,
                SECTION_END_COLUMN: start + timedelta(days=self.length_weeks * 7 - 1),
            },
        )
        self.section_row = self.committed_row(SECTION_TABLE, section_id)
        self.section = calendar.instance(SECTION_TABLE, self.section_row)

        self.windows = {
            course_week: self.seed_window(course_week) for course_week in self.course_weeks
        }
        self.plant_question_set(version=1, question_count=question_count)
        self.rows.commit()
        return self

    # -- the clock, in dates rather than instants -----------------------------

    def clock_at(self, overrides: Any, day: date) -> date:
        """Move the development clock to noon of `day` in the institution's zone.

        The two bounds this ticket carries — a term's `end_date` plus the grace
        days, and an enrollment's `ended_on` — are both compared against
        `clock.today`, which SPEC §3.1 resolves in `INSTITUTION_TIMEZONE`. Noon
        is chosen so the date is the same one read in UTC and in
        `America/New_York`, and so an offset clock still moving while it is read
        (ADR 0109) cannot cross a day boundary between two statements.
        """
        pretend_now = datetime(
            day.year, day.month, day.day, NOON, tzinfo=ZoneInfo(INSTITUTION_TIMEZONE)
        )
        overrides.set(pretend_now=pretend_now, anchored_at=datetime.now(UTC))
        return day


class Gradebook(NamedTuple):
    """One section, its platform, its stored line item, and the answers over it."""

    world: SweptWorld
    section: Any
    platform: Any
    context: Any
    line_item: dict[str, Any]
    line_item_url: str | None
    wire: Any

    @property
    def id(self) -> Any:
        return self.section.id

    @property
    def session(self) -> Any:
        return self.world.session

    @property
    def term_end_date(self) -> date:
        """The `end_date` of the term this section belongs to — D7's bound is measured from it."""
        return self.world.calendar.term[TERM_END_COLUMN]

    def posted(self) -> list[dict[str, Any]]:
        """Every score body the platform recorded against this line item, in order."""
        if self.line_item_url is None:
            pytest.fail(
                "This gradebook has no stored line item, so there is no address to read a posted "
                "score back from. Ask the factory for one with `line_item=True`."
            )
        return scores_posted(self.platform, self.line_item_url)

    def scores_url(self) -> str:
        return self.platform.scores_url(self.line_item)

    def ags_calls(self) -> list[Any]:
        """Every request the sweep made over the wire that was not the token grant.

        The token grant is not an AGS call — it is how one is authorised — so it
        is excluded here and asserted separately where a test is about whether
        the platform was reached at all.
        """
        token_path = self.token_path()
        return [call for call in self.wire.calls if call.path != token_path]

    def token_path(self) -> str:
        document = self.platform.discovery() or {}
        url = document.get("token_endpoint")
        assert isinstance(url, str) and url, (
            f"The platform's discovery document advertises no `token_endpoint` (it carries "
            f"{sorted(document)}), so no AGS call could be authorised and nothing in this suite "
            "could reach the gradebook at all."
        )
        from urllib.parse import urlsplit

        return urlsplit(url).path


@pytest.fixture
def gradebooks(
    ags_sections: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
) -> Iterator[Callable[..., Gradebook]]:
    """A section the client can post to, carrying a term's worth of answers.

    `ags_sections` does everything that is not about the calendar — the mock
    platform, its registration, the tool's published key set, the section bound
    to its own deployment, and the AGS container the launch advertises — and
    `SweptWorld` adds the calendar, the windows, the question set and the
    students on top of that same section.

    `line_item` decides whether the section already points at a line item the
    platform serves. `True` creates one out of band through the platform's own
    credentialed helper and stores its `id` on the section, which is the state
    every section is in after its first staff launch (E3-05) and the state the
    posting criteria are about. `False` leaves the column NULL, which is
    criterion 8's first half and D8's line-item backstop.

    `container` is passed straight through to `ags_sections`: `False` gives a
    section with no gradebook address at all, which is criterion 8's second
    half.
    """
    built: list[Gradebook] = []

    def start(
        *,
        cohort: str = DEFAULT_COHORT,
        question_count: int = 5,
        container: str | bool = True,
        line_item: bool = True,
    ) -> Gradebook:
        section = ags_sections(container=container)
        world = SweptWorld(
            Fall2026(committed_rows.seed, committed_rows.session, metadata_tables),
            committed_rows,
        )
        world.people_chain = {"lti_platform": section.synced.registration.platform_row}
        world.build_on(section.id, cohort=cohort, question_count=question_count)

        created: dict[str, Any] = {}
        identifier: str | None = None
        if line_item:
            created = section.platform.create_line_item(section.context.launches[0])
            identifier = section.platform.line_item_id(created)
            section = ags_sections.store_line_item(section, identifier)

        gradebook = Gradebook(
            world=world,
            section=section,
            platform=section.platform,
            context=section.context,
            line_item=created,
            line_item_url=identifier,
            wire=ags_sections.wire,
        )
        built.append(gradebook)
        return gradebook

    start.wire = ags_sections.wire  # type: ignore[attr-defined]
    yield start


@pytest.fixture
def grade_sync_rows(committed_rows: Any, metadata_tables: dict[str, Any]) -> GradeSyncRows:
    """`grade_sync`, planted by this suite and read back newest-first."""
    return GradeSyncRows(committed_rows, metadata_tables)


def students_in(gradebook: Gradebook, count: int) -> list[Student]:
    """`count` students enrolled from the section's first day, carrying real subjects.

    The subjects are the ones the platform will sign a launch for in this
    section's own context, so a posted score names a student the platform knows.
    Where the seeded context offers fewer than `count`, the remainder carry
    subjects of this file's own: a mock platform records a score against
    whatever `userId` it is sent, and what the extra students exist for is the
    per-student branching — "this one failed and that one still posted" — which
    does not depend on the platform recognising them.
    """
    subjects = list(gradebook.section.subjects)
    while len(subjects) < count:
        subjects.append(f"e3-06-student-{len(subjects) + 1}")
    return [gradebook.world.student(subject) for subject in subjects[:count]]


def answered_fully(world: SweptWorld, student: Student, *, through: int) -> None:
    """Every question answered, every comment substantive, for course weeks 1..`through`."""
    for course_week in range(1, through + 1):
        world.answer_week(student, course_week)


def computed(world: SweptWorld, student: Student, *, settings: Any) -> Any:
    """What `participation_scores` says this student's score and ledger are.

    E3-03's answer, never this file's: the sweep's whole subject is a
    comparison between that answer and what `grade_sync` holds, and a fixture
    that computed either side would be a second implementation for the tests to
    agree with (`docs/MISTAKES.md` entry 19).
    """
    return world.score_for(student, settings=settings)


def score_body(entry: Mapping[str, Any]) -> dict[str, Any]:
    """One recorded score body, as the platform stored it."""
    return dict(entry or {})


@pytest.fixture
def sweep_contract() -> Any:
    """The names E3-06's test modules read the sweep through.

    Handed over as a fixture rather than imported, for the reason every fixtures
    module in this suite gives: an import of a fixtures module by name depends
    on where pytest put `tests/` on `sys.path`, and an import error is not a red.
    """

    class SweepContract:
        grading_module_name = GRADING_MODULE
        grading_logger = GRADING_LOGGER
        tasks_module_name = TASKS_MODULE
        tasks_logger = TASKS_LOGGER
        schedules_module_name = SCHEDULES_MODULE

        sweep_name = SWEEP_FUNCTION
        posted_key = POSTED_KEY
        failed_key = FAILED_KEY
        timestamp_text_name = SCORE_TIMESTAMP_TEXT
        grace_days_name = GRACE_DAYS_NAME
        grace_days_value = GRACE_DAYS
        task_name = POST_SCORES_TASK
        beat_schedule_name = BEAT_SCHEDULE_NAME
        beat_entry_name = BEAT_ENTRY_NAME
        beat_day_of_week = BEAT_DAY_OF_WEEK
        beat_hour = BEAT_HOUR
        beat_minute = BEAT_MINUTE
        request_line_item_creation = REQUEST_LINE_ITEM_CREATION

        grade_sync_table = GRADE_SYNC_TABLE
        score_text_column = SCORE_TEXT_COLUMN
        score_timestamp_column = SCORE_TIMESTAMP_COLUMN
        ledger_text_column = LEDGER_TEXT_COLUMN
        outcome_column = OUTCOME_COLUMN
        response_code_column = RESPONSE_CODE_COLUMN
        created_at_column = CREATED_AT_COLUMN
        ags_call_table = AGS_CALL_TABLE
        container_column = SECTION_CONTAINER_COLUMN
        line_item_column = SECTION_LINE_ITEM_COLUMN
        enrollment_table = ENROLLMENT_TABLE
        ended_on_column = ENDED_ON_COLUMN
        lms_user_id_column = LMS_USER_ID_COLUMN

        user_member = SCORE_USER_MEMBER
        given_member = SCORE_GIVEN_MEMBER
        maximum_member = SCORE_MAXIMUM_SENT_MEMBER
        comment_member = SCORE_COMMENT_MEMBER
        timestamp_member = SCORE_TIMESTAMP_MEMBER

        substantive = SUBSTANTIVE
        insufficient = INSUFFICIENT
        nonsense = NONSENSE

        a_differing_score = A_DIFFERING_SCORE
        a_differing_ledger = A_DIFFERING_LEDGER
        a_stored_timestamp = A_STORED_TIMESTAMP
        a_future_timestamp = A_FUTURE_TIMESTAMP
        a_held_score = A_HELD_SCORE
        a_minute = A_MINUTE
        a_day = A_DAY
        default_cohort = DEFAULT_COHORT

        sweep = staticmethod(sweep_function)
        timestamp_text = staticmethod(score_timestamp_text)
        grace = staticmethod(grace_days)
        task = staticmethod(post_scores_task)
        run = staticmethod(run_sweep)
        grading = staticmethod(grading_module)
        tasks = staticmethod(tasks_module)
        schedules = staticmethod(schedules_module)
        named_in = staticmethod(named_in)
        students = staticmethod(students_in)
        answered_fully = staticmethod(answered_fully)
        computed = staticmethod(computed)
        fields = staticmethod(score_fields)
        body = staticmethod(score_body)

    return SweepContract()
