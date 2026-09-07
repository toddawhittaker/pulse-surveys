"""E4-04 — the world small-N suppression is measured over, and the names it is asked through.

Seven test modules need the same four things, and no fixture in this repository
answers any of them:

  - **A section whose weeks are provably below and above the configured
    threshold, by construction.** E4-04's own known traps put it first: "the
    planted-week fixtures must be provably below and above threshold by
    construction, both sides asserted". So a week is planted by *count of
    responses* and the count is the caller's, and `CommentWorld.responses_in`
    reads back what the database holds for a week so a test can assert both
    sides of the boundary rather than trusting this file.

  - **A week that is closed and a week that is still open, under any clock.**
    The cumulative release may only reach a week whose response count is final,
    and "final" means the window has closed. Every window this world writes
    carries instants **this file chooses** — a closed week opens and closes in
    2020, an open week opens in 2020 and closes in 2099 — so the answer is the
    same whether the implementation reads `app.services.clock` or
    `datetime.now(UTC)`, and the same whether CI runs today or in three years.
    `tests/fixtures/report_views.py`'s calendar cannot do this: SPEC §3.1's
    Fall 2026 instants are in the future today and in the past next year, so a
    suite resting on them would assert the opposite thing on a different date.

  - **Comments a test planted, in the moderation states a test chose.** E4-04's
    second known trap: "a below-threshold test that passes because the week had
    no comments proves nothing. Fixtures plant real comments that would leak."
    Every below-threshold week in these suites carries text, and the text is
    distinctive enough that a leak of it is unmistakable in a failure message.

  - **The names E4-04's work order settles.** They are spelled here rather than
    discovered, because the work order settles every one of them. Discovery
    would be inventing an interface the ticket has already fixed. The one name
    the work order does *not* settle — the instant column on `moderation_state`
    — is discovered, and `decided_at_column` fails naming the ambiguity rather
    than picking.

**Nothing here decides what the service should answer.** This file seeds rows
and reads rows; every expectation is written out in the test module that makes
it (`docs/MISTAKES.md` entries 19 and 30). In particular nothing here counts a
week's responses *for* a test, computes a volume, or decides whether a week is
below the threshold: `configured_threshold` reads `Settings`, and the arithmetic
over it is each module's own and visible in its body.

**Every guard is a plain function called from a test body, never a fixture.**
`docs/MISTAKES.md` entry 44: on a tree where E4-04 is unbuilt each module must
go red as a FAILED naming the deliverable, not as an ERROR in somebody's setup.
`comment_service`, `visible_comments`, `released_comments`, `cut_batches`,
`report_comment_class` and `cut_task` all take that shape, and `comment_world`
hands back an **unbuilt** world for the same reason.

**The environment.** `comment_service()` imports `app.services.report_comments`,
which reaches `app.db` and builds `Settings()` at module scope, so every module
that calls it needs `configured_env` somewhere in its chain
(`docs/MISTAKES.md` entry 40). The integration modules get it through
`db_session`'s own chain and the session baseline in `tests/conftest.py`; the
unit modules declare an autouse fixture of their own, the way
`tests/unit/test_the_participation_sweep_is_scheduled_weekly_and_run_by_a_task.py`
does.
"""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any

import pytest
from sqlalchemy import select, text

from fixtures.clock import DEVELOPMENT
from fixtures.grading import (
    RESPONSE_SECTION_COLUMN,
    RESPONSE_TERM_COLUMN,
    RESPONSE_USER_COLUMN,
    RESPONSE_WEEK_COLUMN,
    SUBSTANTIVE,
    single_column_link,
)
from fixtures.report_views import (
    COURSE_STREAM,
    DEFAULT_COHORT,
    FIRST_VERSION,
    INSTRUCTOR_STREAM,
    ReportWorld,
)
from fixtures.submit import (
    ANSWER_TABLE,
    COMMENT_TEXT_COLUMN,
    QUESTION_SET_TABLE,
    RATING_COLUMN,
    RESPONSE_TABLE,
    USER_TABLE,
)
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import (
    SURVEY_WINDOW_TABLE,
    TERM_TABLE,
    WINDOW_CLOSES_COLUMN,
    WINDOW_OPENS_COLUMN,
    WINDOW_SECTION_COLUMN,
    WINDOW_TERM_COLUMN,
    WINDOW_WEEK_COLUMN,
    Fall2026,
)

# ---------------------------------------------------------------------------
# The contract E4-04's work order settles, spelled once.
# ---------------------------------------------------------------------------

# The module. SPEC §13 puts domain logic under `backend/app/services/`, and the
# work order gives the read path and the cutter a module of their own rather
# than a home in `reporting.py`: this is the one place SPEC §4's suppression is
# decided, and §14.3's E4 entry marks it for line-by-line human review, which is
# a review of a file rather than of a paragraph inside one.
COMMENT_SERVICE_MODULE = "app.services.report_comments"

# The three callables and the one class the work order freezes. Every signature
# below is quoted from it, because a signature a test guessed at is an interface
# the test decided.
COMMENT_CLASS = "ReportComment"
VISIBLE_FUNCTION = "visible_comments"
RELEASED_FUNCTION = "released_comments"
CUT_FUNCTION = "cut_due_release_batches"

# `ReportComment`'s whole field list, in order, and nothing else. **An equality
# rather than a floor**, and it is the same rule `test_report_schema.py` applies
# to the membership row's columns one layer down: SPEC §4 says timestamps are
# never shown with comments and batches the release so that timing cannot
# identify an author, so a `week`, a `submitted_at` or a `released_at` field
# arriving on this class is the leak, not a convenience.
COMMENT_FIELDS = ("text", "status", "stream")

# SPEC §5.2's lifecycle as this path reports it. The database stores the
# upper-case spelling (E4-02's `CHECK`); these are what a caller reads, and the
# work order settles both halves. `PUBLISHED_STATUS` is what a comment with no
# `moderation_state` row carries — ADR 0145 makes the initial state the absence
# of a row, so absence and an explicit published row are one status here.
PUBLISHED_STATUS = "published"
KEPT_STATUS = "kept"
FLAGGED_STATUS = "flagged_collapsed"
EXCLUDED_STATUS = "excluded"
COMMENT_STATUSES = (PUBLISHED_STATUS, KEPT_STATUS, FLAGGED_STATUS, EXCLUDED_STATUS)

# E4-02's own spellings, from `tests/integration/test_report_schema.py`.
# Transcribed rather than imported for the reason that module gives about a test
# module importing its sibling: it resolves only because of where pytest puts
# `tests/` on `sys.path`.
MODERATION_STATE_TABLE = "moderation_state"
RELEASE_BATCH_TABLE = "release_batch"
RELEASE_BATCH_MEMBER_TABLE = "release_batch_member"
ANSWER_ID_COLUMN = "answer_id"
STATE_COLUMN = "state"
BATCH_ID_COLUMN = "batch_id"
SECTION_ID_COLUMN = "section_id"
TERM_ID_COLUMN = "term_id"

STORED_PUBLISHED = "PUBLISHED"
STORED_FLAGGED = "FLAGGED_COLLAPSED"
STORED_EXCLUDED = "EXCLUDED"
STORED_KEPT = "KEPT"

# What a stored state means to a caller of this path. The mapping is the work
# order's, written here so a test can plant a state and name the status it
# expects without either module holding a private table.
STATUS_OF_STORED = {
    STORED_PUBLISHED: PUBLISHED_STATUS,
    STORED_FLAGGED: FLAGGED_STATUS,
    STORED_EXCLUDED: EXCLUDED_STATUS,
    STORED_KEPT: KEPT_STATUS,
}

# The view the read path selects comment text through, and its whole column
# list. ADR 0041 maps `backend/app/views_sql/<object>_v<NNN>.sql` to the
# relation, so the file is `report_comment_v001.sql`.
#
# **Five columns and no sixth.** The key of the answer is here because a release
# is a membership row keyed on `answer_id` (ADR 0146) and the cutter has to be
# able to name what it released; the section, the week and the stream are what
# the read is filtered by; and `comment_text` is the payload. What is
# deliberately absent is every currency of a person and every instant: the view
# names no `user_id`, no `response_id` and no `submitted_at`, so nothing an
# instructor's connection can select from it says who wrote a comment or when.
COMMENT_VIEW = "report_comment"
COMMENT_VIEW_COLUMNS = ("section_id", "week_id", "stream", "answer_id", "comment_text")

# The beat entry and the thin task the work order adds, and the slot it settles.
# Monday because SPEC §3.1 closes every window on Sunday at 23:59:59 in the
# institution's timezone, so Monday is the first day a week that has ended can
# be counted at all; 02:40 because the minutes 0, 20, 30 and 45 already belong
# to the roster sync, the participation sweep, the window reconciler and the
# reclassification pass.
TASKS_MODULE = "app.jobs.tasks"
SCHEDULES_MODULE = "app.jobs.schedules"
BEAT_SCHEDULE_NAME = "BEAT_SCHEDULE"
CUT_TASK = "cut_release_batches"
BEAT_ENTRY_NAME = "cut-release-batches-weekly"
BEAT_DAY_OF_WEEK = "mon"
BEAT_HOUR = "2"
BEAT_MINUTE = "40"

# ---------------------------------------------------------------------------
# The messages a missing deliverable is reported with.
# ---------------------------------------------------------------------------

SERVICE_IS_OWED = (
    "E4-04's work order puts the whole of SPEC §4's small-N comment path in "
    "`backend/app/services/report_comments.py` (SPEC §13 puts domain logic under `services/`), "
    "holding the read path and the cutter together so the one place suppression is decided is one "
    "file a reviewer reads whole."
)

VISIBLE_IS_OWED = (
    f"`{VISIBLE_FUNCTION}(session, *, section_id, week_id, stream, rng=None) -> "
    f"tuple[{COMMENT_CLASS}, ...]` — the asked week's comments when that week's response count "
    "reaches the configured threshold, and the empty tuple below it. SPEC §4: below the "
    "n-threshold instructors see distributions and the AI summary but no raw comments."
)

RELEASED_IS_OWED = (
    f"`{RELEASED_FUNCTION}(session, *, section_id, term_id, stream, rng=None) -> "
    f"tuple[{COMMENT_CLASS}, ...]` — every released batch member's comment for one section, "
    "term and stream, with no week attribution anywhere in the return. SPEC §4: held comments "
    "surface once the section's cumulative comment volume for the term crosses the threshold, "
    "batched so that timing cannot identify an author."
)

CUT_IS_OWED = (
    f"`{CUT_FUNCTION}(session) -> int` — the number of batches cut. It evaluates the crossing "
    "and writes the batch (E4's breakdown decision 7: the crossing is stored rather than "
    "re-derived at read time), one transaction per section and term."
)

COMMENT_CLASS_IS_OWED = (
    f"a frozen dataclass `{COMMENT_CLASS}` carrying exactly {list(COMMENT_FIELDS)}. SPEC §4: "
    "'timestamps are never shown with comments', and the release is batched 'so that timing "
    "cannot identify an author' — so the absence of a week and of an instant is structural "
    "rather than a rendering choice."
)

TASK_IS_OWED = (
    f"E4-04's work order adds `{CUT_TASK}()` to `{TASKS_MODULE}`, on "
    "`derive_survey_windows`' shape: no arguments, open a session, call "
    f"`{COMMENT_SERVICE_MODULE}.{CUT_FUNCTION}`, commit once, return the count."
)

# ---------------------------------------------------------------------------
# This suite's own values. None is a claim about anything the system decides.
# ---------------------------------------------------------------------------

# **A window that has certainly closed, and one that certainly has not**, under
# any clock and on any date CI runs. Both are this file's own instants and
# neither is read back as an answer. The open week opens in the past and closes
# in the far future, which is what "still open" means — not a window that has
# not begun, which is a different state and one no comment can be submitted in.
LONG_PAST_OPENS = datetime(2020, 1, 3, 23, 0, 0, tzinfo=UTC)
LONG_PAST_CLOSES = datetime(2020, 1, 6, 4, 59, 59, tzinfo=UTC)
FAR_FUTURE_CLOSES = datetime(2099, 1, 4, 4, 59, 59, tzinfo=UTC)

# One term week's worth of separation between two planted windows, so two closed
# weeks do not share instants and a reader that ordered by them has something to
# order.
A_WEEK = timedelta(days=7)

# Where inside a window a planted submission and its classification sit. Both
# measured from `opens_at`, so they are inside the window for a closed week and
# for an open one alike; measuring from `closes_at` would put an open week's
# submission in 2099.
SUBMITTED_AFTER_OPEN = timedelta(hours=1)
CLASSIFIED_AFTER_OPEN = timedelta(hours=2)

# How far apart two moderation decisions about one comment are placed, for the
# case where the later one governs (ADR 0145: the record is append-only and the
# latest row governs).
A_LATER_DECISION = timedelta(hours=1)

# SPEC §3.2's two comment questions, by position: Q2 is the instructor stream's
# and Q4 the course stream's (`SPEC_QUESTION_LAYOUT` in
# `tests/fixtures/report_views.py`). Named here so a test says which stream it is
# planting into rather than which ordinal.
COMMENT_POSITION = {INSTRUCTOR_STREAM: 2, COURSE_STREAM: 4}

# A rating question's position, for the view's own exclusion test.
A_RATING_POSITION = 1

# The environment variable `.env.example` documents for SPEC §4's threshold, and
# the spec's own default — read out of the spec rather than out of configuration
# so a default quietly changed in either is a failure rather than a new
# expectation (`docs/MISTAKES.md` entry 19).
N_THRESHOLD_VARIABLE = "N_THRESHOLD_DEFAULT"
SPEC_DEFAULT_N_THRESHOLD = 5


def configured_threshold() -> int:
    """`Settings.n_threshold_default`, or a failure naming the field SPEC §4 makes configuration.

    Constructed rather than passed in, for the reason
    `tests/integration/test_a_resolved_scope_holds_care_beside_the_purview.py`
    gives about the same value: the claim under test is about *the configured
    number*, and comparing against one this file invented would assert something
    else. Every planted week in these suites is sized from this, so nothing here
    hard-codes 5 — E4-04's third known trap.
    """
    module = import_module("app.config")
    settings_class = getattr(module, "Settings", None)
    if settings_class is None:
        pytest.fail(
            "`app.config` exposes no `Settings`. E0-02 ships it and SPEC §4 makes the n-threshold "
            "configuration: 'Threshold value is configurable (default 5).'"
        )
    value = getattr(settings_class(), "n_threshold_default", None)
    if value is None:
        pytest.fail(
            "`Settings` has no `n_threshold_default`. `.env.example` documents "
            f"`{N_THRESHOLD_VARIABLE}` as the responses in a reporting week below which raw "
            "comments stay hidden from instructors and students alike (§4, §4.1 invariant 3)."
        )
    return int(value)


# ---------------------------------------------------------------------------
# The deliverables, named where a test can fail on them rather than error.
# ---------------------------------------------------------------------------


def comment_service() -> Any:
    """`app.services.report_comments`, imported where a test can fail on it.

    A `ModuleNotFoundError` at a test module's top level is a collection error,
    which survives the implementation landing and reads to a hurried eye as a
    red suite (`docs/MISTAKES.md` entry 44). This is a FAILED naming the file.
    """
    try:
        return import_module(COMMENT_SERVICE_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (
            absent == COMMENT_SERVICE_MODULE or COMMENT_SERVICE_MODULE.startswith(f"{absent}.")
        ):
            raise
        pytest.fail(f"`{COMMENT_SERVICE_MODULE}` does not exist. {SERVICE_IS_OWED}")


def named_in_service(name: str, owed: str) -> Any:
    """One name off the comment service, or a failure quoting what owes it."""
    module = comment_service()
    found = getattr(module, name, None)
    if found is None:
        pytest.fail(
            f"`{COMMENT_SERVICE_MODULE}` exposes no `{name}`; it exposes "
            f"{sorted(entry for entry in vars(module) if not entry.startswith('_'))}.\n\n{owed}"
        )
    return found


def visible_comments() -> Any:
    """`visible_comments`, or a failure naming it."""
    return named_in_service(VISIBLE_FUNCTION, VISIBLE_IS_OWED)


def released_comments() -> Any:
    """`released_comments`, or a failure naming it."""
    return named_in_service(RELEASED_FUNCTION, RELEASED_IS_OWED)


def cut_batches() -> Any:
    """`cut_due_release_batches`, or a failure naming it."""
    return named_in_service(CUT_FUNCTION, CUT_IS_OWED)


def report_comment_class() -> Any:
    """`ReportComment`, or a failure naming it."""
    return named_in_service(COMMENT_CLASS, COMMENT_CLASS_IS_OWED)


def cut_task() -> Any:
    """`app.jobs.tasks.cut_release_batches`, or a failure naming the deliverable that owes it."""
    try:
        module = import_module(TASKS_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(f"`{TASKS_MODULE}` does not import ({missing}). {TASK_IS_OWED}")
    found = getattr(module, CUT_TASK, None)
    if found is None:
        pytest.fail(
            f"`{TASKS_MODULE}` exposes no `{CUT_TASK}`; it exposes "
            f"{sorted(entry for entry in vars(module) if not entry.startswith('_'))}.\n\n"
            f"{TASK_IS_OWED}"
        )
    return found


def schedules_module() -> Any:
    """`app.jobs.schedules`, imported where a test can fail on it rather than error."""
    try:
        return import_module(SCHEDULES_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{SCHEDULES_MODULE}` does not exist ({missing}). E2-06 ships it with "
            f"`{BEAT_SCHEDULE_NAME}`, the one place this project's periodic work is declared, and "
            f"E4-04 appends the {BEAT_ENTRY_NAME!r} entry to it."
        )


def beat_schedule() -> dict[str, Any]:
    """`BEAT_SCHEDULE`, or a failure naming what declares this project's periodic work."""
    module = schedules_module()
    found = getattr(module, BEAT_SCHEDULE_NAME, None)
    if not isinstance(found, dict):
        pytest.fail(
            f"`{SCHEDULES_MODULE}.{BEAT_SCHEDULE_NAME}` is {found!r}, which is not a mapping. "
            "Celery's `beat_schedule` is a dict of entry name to entry, and these tests read it "
            "by name."
        )
    return found


# ---------------------------------------------------------------------------
# Reading the tables E4-02 built and E4-04 is the first to write.
# ---------------------------------------------------------------------------


def require_report_table(tables: Mapping[str, Any], name: str) -> Any:
    """One of E4-02's tables, or a failure saying it is not there.

    Called from a test body, never from a fixture, so a tree without E4-02
    merged in reports the missing table by name as a FAILED
    (`docs/MISTAKES.md` entry 44).
    """
    table = tables.get(name)
    if table is None:
        pytest.fail(
            f"There is no `{name}` table (what is there: {sorted(tables)}). E4-02 creates the "
            "report schema in `backend/app/models/report.py`; E4-04's migration takes the chain "
            "slot below it, so this branch is built with `e4/report-schema` merged in."
        )
    return table


def decided_at_column(tables: Mapping[str, Any]) -> str:
    """The instant column on `moderation_state`, discovered rather than named.

    **The one name in this file that is not settled by a record.** ADR 0145
    describes the row as "the comment, the state, and when it was decided" and
    spells the first two; `tests/integration/test_report_schema.py` pins
    `answer_id` and `state` and names no third. So it is found by type — the one
    date-or-time column on the table — and an ambiguous answer is a failure
    naming the ambiguity rather than a guess, which is how
    `tests/fixtures/report_views.py` treats the validity service's signature and
    for the same reason.
    """
    table = require_report_table(tables, MODERATION_STATE_TABLE)

    def is_an_instant(column: Any) -> bool:
        spelling = type(column.type).__name__.lower()
        return "date" in spelling or "time" in spelling

    instants = sorted(column.name for column in table.columns if is_an_instant(column))
    if len(instants) != 1:
        pytest.fail(
            f"`{MODERATION_STATE_TABLE}` carries {len(instants)} date-or-time columns ({instants}); "
            f"its whole column list is {[column.name for column in table.columns]}. ADR 0145 gives "
            "the row 'the comment, the state, and when it was decided', and the latest row "
            "governs — so a test that plants two decisions about one comment has to be able to say "
            "which is later, and it needs exactly one column to say it on."
        )
    return instants[0]


class ReleaseRows:
    """What is in `release_batch` and `release_batch_member`, read back by a test.

    **A reader and nothing else.** E4-04 is the only thing in the product that
    writes either table, so a fixture that planted a batch would be supplying
    the value under test (`docs/MISTAKES.md` entry 30) — every batch these
    suites read back was cut by the cutter.
    """

    def __init__(self, session: Any, tables: dict[str, Any]) -> None:
        self.session = session
        self.tables = tables

    def batches(self, *, section_id: Any = None) -> list[dict[str, Any]]:
        """Every `release_batch` row, or every one for a section, newest key order aside."""
        table = require_report_table(self.tables, RELEASE_BATCH_TABLE)
        statement = select(table)
        if section_id is not None:
            statement = statement.where(table.c[SECTION_ID_COLUMN] == section_id)
        self.session.flush()
        return [dict(row) for row in self.session.execute(statement).mappings()]

    def batch_key(self) -> str:
        """The name of `release_batch`'s primary key column (ADR 0016 makes it one uuid)."""
        return single_primary_key(require_report_table(self.tables, RELEASE_BATCH_TABLE))

    def members(self) -> list[dict[str, Any]]:
        """Every `release_batch_member` row there is."""
        table = require_report_table(self.tables, RELEASE_BATCH_MEMBER_TABLE)
        self.session.flush()
        return [dict(row) for row in self.session.execute(select(table)).mappings()]

    def released_answers(self) -> set[Any]:
        """The set of answer keys that are in some batch."""
        return {row[ANSWER_ID_COLUMN] for row in self.members()}

    def identities(self) -> set[tuple[Any, Any, Any]]:
        """Every membership as `(its own key, its batch, its comment)`.

        The row's own key is in the tuple because idempotence is asserted by
        **row identity**: a second run that deleted the memberships and wrote
        equivalent ones back would satisfy an assertion over
        `(batch, comment)` pairs and would have re-released every held comment
        under a new `cut_at`.
        """
        table = require_report_table(self.tables, RELEASE_BATCH_MEMBER_TABLE)
        key = single_primary_key(table)
        return {(row[key], row[BATCH_ID_COLUMN], row[ANSWER_ID_COLUMN]) for row in self.members()}


# ---------------------------------------------------------------------------
# The world.
# ---------------------------------------------------------------------------


class CommentWorld(ReportWorld):
    """`ReportWorld`, with windows this file dates and comments a test plants.

    Everything about the term, the section, the question set and the two streams
    is E4-03's fixture's and is not re-implemented. What is replaced is the
    window instants and the submission, for one reason each:

      - **The instants**, because `WINDOWS_BY_TERM_WEEK` is SPEC §3.1's Fall 2026
        calendar and those instants are in the future on one date and in the past
        on another. A suite whose subject is "this week has closed and that one
        has not" cannot rest on a calendar whose answer depends on when CI ran.
      - **The submission**, because a response's `submitted_at` is derived from
        its window's close in `ReportWorld.respond`, and a week that closes in
        2099 would then hold a submission from 2099. `submit` below measures from
        the window's *open* instead, which is inside the window for a closed week
        and for an open one alike.
    """

    def __init__(self, calendar: Fall2026) -> None:
        super().__init__(calendar)
        # The instants each planted term week's window carries, chosen by the
        # test through `close_week` and `open_week`. A week nothing chose for is
        # a week no test in these suites reads.
        self.instants: dict[int, tuple[datetime, datetime]] = {}
        self.subjects = 0

    # -- the calendar this world writes ---------------------------------------

    def close_week(self, term_week: int) -> "CommentWorld":
        """Plant term week `term_week` with a window that opened and closed in 2020."""
        offset = A_WEEK * term_week
        self.instants[term_week] = (LONG_PAST_OPENS + offset, LONG_PAST_CLOSES + offset)
        return self

    def open_week(self, term_week: int) -> "CommentWorld":
        """Plant term week `term_week` with a window that opened in 2020 and closes in 2099.

        Open rather than not-yet-begun: a window whose `opens_at` were in the
        future would hold no submissions at all, and "no comments because nobody
        could answer" is the state E4-04's second known trap warns about.
        """
        offset = A_WEEK * term_week
        self.instants[term_week] = (LONG_PAST_OPENS + offset, FAR_FUTURE_CLOSES)
        return self

    def window(self, term_week: int, cohort: str = DEFAULT_COHORT) -> Any:
        """One `survey_window` at the instants this world chose for the week.

        Overrides `ReportWorld.window`, which reads SPEC §3.1's calendar. A week
        no test has called `close_week` or `open_week` for is a failure naming
        that, rather than a window silently dated from a calendar whose answer
        moves with the date CI runs on.
        """
        cached = self.windows.get((cohort, term_week))
        if cached is not None:
            return cached
        if term_week not in self.instants:
            pytest.fail(
                f"Term week {term_week} has no window instants. Every week in an E4-04 suite is "
                "planted by `close_week` or `open_week` first, because whether a week has closed "
                "is what decides whether its comments can be released and SPEC §3.1's Fall 2026 "
                "calendar answers that differently depending on the day CI runs."
            )
        opens_at, closes_at = self.instants[term_week]
        window = self.seed(
            SURVEY_WINDOW_TABLE,
            {},
            **{
                WINDOW_SECTION_COLUMN: self.section_id(cohort),
                WINDOW_WEEK_COLUMN: self.week_id(term_week),
                WINDOW_TERM_COLUMN: self.calendar.term[self.key_of(TERM_TABLE)],
                WINDOW_OPENS_COLUMN: opens_at,
                WINDOW_CLOSES_COLUMN: closes_at,
            },
        )
        self.windows[(cohort, term_week)] = window
        return window

    def term_id(self) -> Any:
        """The term every section in this world belongs to — `released_comments` is keyed on it."""
        return self.calendar.term[self.key_of(TERM_TABLE)]

    # -- what a student submitted ---------------------------------------------

    def submit(
        self,
        *,
        term_week: int,
        comments: Mapping[str, str] | None = None,
        ratings: Mapping[int, Any] | None = None,
        cohort: str = DEFAULT_COHORT,
        version: int = FIRST_VERSION,
    ) -> tuple[Any, dict[str, Any]]:
        """One student's whole response for one week, answering the comments given.

        `comments` maps a stream to the text stored for that stream's comment
        question, so a caller says "one instructor-stream comment" rather than
        naming an ordinal. A stream left out gets no `answer` row at all, which
        is the faithful record of a question nobody answered (E2-05 refuses an
        answer holding no value, and ADR 0115 deletes a withdrawn one).

        Every response gets a student of its own, because SPEC §4's threshold
        counts *responses* in a week and E2-05 holds one response per student per
        section-week: two responses from one student is a row the schema refuses,
        and this world's whole job is planting a chosen count.

        Answers back the `response` row and a mapping of stream to the `answer`
        row written for it, so a test can name the comment it planted when it
        asserts what happened to it.
        """
        comments = {} if comments is None else comments
        ratings = {} if ratings is None else ratings
        window = self.window(term_week, cohort)
        opens_at, _closes_at = self.instants[term_week]

        self.subjects += 1
        student = self.student(f"e4-04-subject-{self.subjects}", cohorts=(cohort,))

        values: dict[str, Any] = {
            RESPONSE_USER_COLUMN: student[self.key_of(USER_TABLE)],
            RESPONSE_SECTION_COLUMN: self.section_id(cohort),
            RESPONSE_WEEK_COLUMN: self.week_id(term_week),
            RESPONSE_TERM_COLUMN: self.calendar.term[self.key_of(TERM_TABLE)],
        }
        if self.has_column(RESPONSE_TABLE, "submitted_at"):
            values["submitted_at"] = opens_at + SUBMITTED_AFTER_OPEN
        window_column = single_column_link(
            require_table(self.tables, RESPONSE_TABLE), SURVEY_WINDOW_TABLE
        )
        if window_column is not None:
            values[window_column] = window[self.key_of(SURVEY_WINDOW_TABLE)]
        set_column = single_column_link(
            require_table(self.tables, RESPONSE_TABLE), QUESTION_SET_TABLE
        )
        if set_column is not None:
            values[set_column] = self.question_sets[version][self.key_of(QUESTION_SET_TABLE)]
        response = self.seed(RESPONSE_TABLE, {}, **values)

        written: dict[str, Any] = {}
        for position, rating in sorted(ratings.items()):
            self.answer(response, position, rating, version=version)
        for stream, body in sorted(comments.items()):
            answer = self.answer(response, COMMENT_POSITION[stream], body, version=version)
            self.classify(answer, SUBSTANTIVE, classified_at=opens_at + CLASSIFIED_AFTER_OPEN)
            written[stream] = answer
        return response, written

    def week_of_comments(
        self,
        *,
        term_week: int,
        texts: list[str],
        stream: str = INSTRUCTOR_STREAM,
        cohort: str = DEFAULT_COHORT,
    ) -> list[Any]:
        """One response per text, all in one week — the shape every planted week here has.

        The response count of the week is therefore `len(texts)`, which is what a
        test compares against the configured threshold, and `responses_in` below
        is how it says so from the database rather than from this sentence.
        """
        return [
            self.submit(term_week=term_week, comments={stream: body}, cohort=cohort)[1][stream]
            for body in texts
        ]

    # -- moderation -----------------------------------------------------------

    def moderate(self, answer: Mapping[str, Any], state: str, *, decided_at: Any = None) -> Any:
        """Append one `moderation_state` row for one comment.

        Append, always: ADR 0145 makes the record append-only with the latest row
        governing, so a second decision is a new row rather than an edit.
        `decided_at` is the caller's whenever which row is latest is the subject.
        """
        values: dict[str, Any] = {
            ANSWER_ID_COLUMN: answer[self.key_of(ANSWER_TABLE)],
            STATE_COLUMN: state,
        }
        if decided_at is not None:
            values[decided_at_column(self.tables)] = decided_at
        return self.seed(MODERATION_STATE_TABLE, {}, **values)

    # -- reading the world back ------------------------------------------------

    def responses_in(self, *, term_week: int, cohort: str = DEFAULT_COHORT) -> int:
        """How many `response` rows the database holds for one section-week.

        **The count is read back rather than assumed**, because E4-04's first
        known trap is a fixture bug that breaks this diff silently: a planted
        "week of four" that seeded three responses satisfies every below-threshold
        assertion in these suites for the wrong reason. Every test that plants a
        week asserts this against the configured threshold, on both sides.

        The semantics are `report_response_counts.responses`' — a count of
        `response` rows for the section and week — which is the number SPEC §4's
        "n < 5 responses in a reporting week" is about.
        """
        table = require_table(self.tables, RESPONSE_TABLE)
        self.session.flush()
        statement = select(table).where(
            table.c[RESPONSE_SECTION_COLUMN] == self.section_id(cohort),
            table.c[RESPONSE_WEEK_COLUMN] == self.week_id(term_week),
        )
        return len(list(self.session.execute(statement)))

    def comment_answers_in_term(self, *, cohort: str = DEFAULT_COHORT) -> int:
        """How many comment answers with text the section holds across the whole term.

        The volume SPEC §4's cumulative rule is about, counted the way the work
        order settles it: every comment answer stored for the section in the
        term, every week, every moderation state. Read from the database so a
        test can assert the volume it planted is the volume that is there.
        """
        answers = require_table(self.tables, ANSWER_TABLE)
        responses = require_table(self.tables, RESPONSE_TABLE)
        answer_response = single_column_link(answers, RESPONSE_TABLE)
        if answer_response is None:
            pytest.fail(
                f"No single-column foreign key on `{ANSWER_TABLE}` names a `{RESPONSE_TABLE}` row, "
                "so this reader cannot walk a comment back to the section it was submitted in."
            )
        response_key = single_primary_key(responses)
        self.session.flush()
        statement = (
            select(answers)
            .select_from(
                answers.join(responses, answers.c[answer_response] == responses.c[response_key])
            )
            .where(
                responses.c[RESPONSE_SECTION_COLUMN] == self.section_id(cohort),
                responses.c[RESPONSE_TERM_COLUMN] == self.calendar.term[self.key_of(TERM_TABLE)],
                answers.c[COMMENT_TEXT_COLUMN].is_not(None),
            )
        )
        return len(list(self.session.execute(statement)))

    def answer_key(self, answer: Mapping[str, Any]) -> Any:
        """One planted `answer` row's primary key."""
        return answer[self.key_of(ANSWER_TABLE)]

    def view_rows(
        self, *, cohort: str = DEFAULT_COHORT, term_week: int | None = None
    ) -> list[dict[str, Any]]:
        """Every `report_comment` row for this world's section, or for one of its weeks."""
        return comment_view_rows(
            self.session,
            section_id=self.section_id(cohort),
            week_id=None if term_week is None else self.week_id(term_week),
        )


def comment_view_columns(connection: Any, view: str = COMMENT_VIEW) -> tuple[str, ...]:
    """Every column `public.<view>` returns, in order, or an empty tuple if it is not there.

    Read from `pg_catalog` rather than from `information_schema`, for the reason
    `tests/fixtures/report_views.py` gives: the information schema shows a role
    only the relations it holds a privilege on, so a column list read as
    `pulse_app` would come back empty for a view nobody granted — a missing grant
    reported as a missing view.
    """
    statement = text(
        """
        SELECT a.attname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
        WHERE n.nspname = 'public' AND c.relname = :relation AND c.relkind IN ('v', 'm')
        ORDER BY a.attnum
        """
    )
    return tuple(str(row[0]) for row in connection.execute(statement, {"relation": view}))


def require_comment_view(connection: Any) -> tuple[str, ...]:
    """The view's columns, or a failure naming the deliverable that is missing."""
    present = comment_view_columns(connection)
    if not present:
        pytest.fail(
            f"There is no view `public.{COMMENT_VIEW}` in the migrated database. E4-04 ships it "
            f"from `backend/app/views_sql/{COMMENT_VIEW}_v001.sql`, executed by that ticket's "
            "migration the way every identity-separated view is executed (ADR 0041). It returns "
            f"{list(COMMENT_VIEW_COLUMNS)} — comment-kind answers carrying text, and nothing that "
            "names a person or an instant."
        )
    return present


def comment_view_rows(
    connection: Any, *, section_id: Any, week_id: Any = None
) -> list[dict[str, Any]]:
    """Every `report_comment` row for one section, or for one section-week."""
    require_comment_view(connection)
    selected = ", ".join(COMMENT_VIEW_COLUMNS)
    clause = "WHERE section_id = :section"
    parameters: dict[str, Any] = {"section": section_id}
    if week_id is not None:
        clause += " AND week_id = :week"
        parameters["week"] = week_id
    # The relation and the column list are module constants, never a caller's
    # string, and both keys are bound.
    statement = text(f"SELECT {selected} FROM public.{COMMENT_VIEW} {clause}")  # noqa: S608
    return [dict(row) for row in connection.execute(statement, parameters).mappings()]


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------


@pytest.fixture
def comment_world(fall_2026: Fall2026) -> CommentWorld:
    """The world E4-04's suppression is measured over, **unbuilt**.

    Unbuilt for `docs/MISTAKES.md` entry 44's reason: every guard this world
    raises — a missing `question.stream`, a missing report table, a week nobody
    dated — has to fire inside a test body so that a tree without E4-04 in it is
    a wall of failed assertions rather than a wall of setup errors.
    """
    return CommentWorld(fall_2026)


@pytest.fixture
def committed_comment_world(committed_rows: Any, metadata_tables: dict[str, Any]) -> CommentWorld:
    """The same world, committed, so the application connection can read it.

    ADR 0001 binds the pool to the service, so the application role connects for
    itself: a test that drives this path **as `pulse_app`** over real rows needs
    them committed or it is reading an empty database and calling it a pass
    (`docs/MISTAKES.md` entry 46). `committed_rows` removes whatever appeared.

    The session states its environment for the reason
    `committed_report_world` states its: Batch C's registration-address rules
    judge a session that states nothing as a deployment, and the seeding walker's
    invented `lti_platform` row carries a development stack's cleartext address.
    """
    committed_rows.session.info["environment"] = DEVELOPMENT
    return CommentWorld(Fall2026(committed_rows.seed, committed_rows.session, metadata_tables))


@pytest.fixture
def release_rows(db_session: Any, metadata_tables: dict[str, Any]) -> ReleaseRows:
    """`release_batch` and `release_batch_member`, read back on the seeding session."""
    return ReleaseRows(db_session, metadata_tables)


@pytest.fixture
def committed_release_rows(committed_rows: Any, metadata_tables: dict[str, Any]) -> ReleaseRows:
    """The same two tables on the committed session."""
    return ReleaseRows(committed_rows.session, metadata_tables)


@pytest.fixture
def comment_contract() -> Any:
    """The names E4-04's test modules read the comment path through.

    Handed over as a fixture rather than imported, for the reason every fixtures
    module in this suite gives: importing a fixtures module by name depends on
    where pytest put `tests/` on `sys.path`, and an import error is not a red.
    """

    class CommentContract:
        service_module = COMMENT_SERVICE_MODULE
        tasks_module = TASKS_MODULE
        schedules_module_name = SCHEDULES_MODULE

        comment_class_name = COMMENT_CLASS
        comment_fields = COMMENT_FIELDS
        visible_name = VISIBLE_FUNCTION
        released_name = RELEASED_FUNCTION
        cut_name = CUT_FUNCTION
        task_name = CUT_TASK

        beat_schedule_name = BEAT_SCHEDULE_NAME
        beat_entry_name = BEAT_ENTRY_NAME
        beat_day_of_week = BEAT_DAY_OF_WEEK
        beat_hour = BEAT_HOUR
        beat_minute = BEAT_MINUTE

        view = COMMENT_VIEW
        view_columns = COMMENT_VIEW_COLUMNS

        published = PUBLISHED_STATUS
        kept = KEPT_STATUS
        flagged = FLAGGED_STATUS
        excluded = EXCLUDED_STATUS
        statuses = COMMENT_STATUSES
        status_of_stored = STATUS_OF_STORED

        stored_published = STORED_PUBLISHED
        stored_flagged = STORED_FLAGGED
        stored_excluded = STORED_EXCLUDED
        stored_kept = STORED_KEPT

        instructor_stream = INSTRUCTOR_STREAM
        course_stream = COURSE_STREAM
        rating_position = A_RATING_POSITION
        rating_column = RATING_COLUMN
        a_later_decision = A_LATER_DECISION

        moderation_table = MODERATION_STATE_TABLE
        batch_table = RELEASE_BATCH_TABLE
        member_table = RELEASE_BATCH_MEMBER_TABLE
        answer_id_column = ANSWER_ID_COLUMN
        batch_id_column = BATCH_ID_COLUMN
        section_id_column = SECTION_ID_COLUMN
        term_id_column = TERM_ID_COLUMN

        threshold_variable = N_THRESHOLD_VARIABLE
        spec_default_threshold = SPEC_DEFAULT_N_THRESHOLD

        service = staticmethod(comment_service)
        visible = staticmethod(visible_comments)
        released = staticmethod(released_comments)
        cut = staticmethod(cut_batches)
        comment_class = staticmethod(report_comment_class)
        task = staticmethod(cut_task)
        schedules = staticmethod(schedules_module)
        schedule = staticmethod(beat_schedule)
        threshold = staticmethod(configured_threshold)
        require_table = staticmethod(require_report_table)
        decided_at = staticmethod(decided_at_column)
        view_of = staticmethod(comment_view_columns)
        require_view = staticmethod(require_comment_view)
        view_rows = staticmethod(comment_view_rows)

    return CommentContract()
