"""E4-06 — the Monday summary job: the names it is driven through, and the world it walks.

Six test modules need the same four things, and no fixture in this repository
answers any of them:

  - **A section-week whose survey window has closed, carrying comments in
    chosen streams.** `tests/fixtures/report_views.py`'s `ReportWorld` already
    seeds a term, its eighteen weeks, a section whose course weeks are not its
    term weeks, E3-02's `question.stream` on SPEC §3.2's five questions, and
    responses whose answers this suite chose. What it does not do is put the
    development clock somewhere that makes a week *closed*, which is the whole
    of what this job selects on. `SummaryWorld` below is `ReportWorld` on
    `committed_rows`' session with the clock moved by hand.

  - **A gateway that answers per stream and can be made to fail on one
    section.** The job makes two `summarize_stream` calls per section-week and
    each is a separate model call (ADR 0148), so a double that answered the
    same object twice would hand back an answer about the stream nobody asked
    for and the task would refuse it — which is a red about E4-05 rather than
    about this job. `StreamAwareGateway` reads which stream it was asked about
    off the comments in the prompt, and raises for a section whose comments
    carry a marker the test planted.

  - **`weekly_summary`, read back on a connection that sees commits.** The task
    opens its own session through `app.db` — which connects as `pulse_app`, the
    role production runs on (`tests/fixtures/database.py`) — so a suite holding
    a transaction open since it seeded would read the table as it was and report
    that the job wrote nothing.

  - **The names E4-06's work order settles**, spelled here rather than
    discovered, because the work order settles them and a test that went looking
    would agree with an implementation that built something else and called it
    something similar (`docs/MISTAKES.md` entry 19).

**Every guard is a plain function called from a test body, never a fixture.**
`docs/MISTAKES.md` entry 44: on a tree where E4-06 is unbuilt each module must
go red as a FAILED naming the deliverable, not as an ERROR in somebody's setup.
`named_in` and `tasks_module` are imported from
`tests/fixtures/line_item_creation.py` rather than written again, which is
entry 13's rule one file over.

**Nothing here decides what the job should answer.** This file seeds rows, moves
a clock, and hands the job a gateway whose answers the caller chose; every
expectation is the test's. A fixture that composed the row it then read back
would be a second implementation for the suite to agree with
(`docs/MISTAKES.md` entry 30).

**The environment is a requirement this file makes of its callers**, and
`summary_job_environment` is how it is met. The task imports `app.db`, which
builds `Settings()` at module scope, and it reads the development clock — which
applies only where `ENVIRONMENT` is `development` (ADR 0109 part 4). Both are
stated rather than inherited (`docs/MISTAKES.md` entry 40).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

import pytest

from fixtures.clock import DEVELOPMENT, ENVIRONMENT_VARIABLE, INSTITUTION_TIMEZONE_VARIABLE
from fixtures.line_item_creation import named_in, tasks_module
from fixtures.report_views import ReportWorld
from fixtures.summary_task import COMMENT_THEME as COMMENT_THEME_CONTRACT
from fixtures.summary_task import (
    COURSE_STREAM,
    EMPTY_WEEK_PROMPT_VERSION,
    EMPTY_WEEK_SUMMARY,
    INSTRUCTOR_STREAM,
    SUMMARY_PROMPT_VERSION,
    WEEKLY_SUMMARY_OUTPUT,
    SummaryApi,
)
from fixtures.survey_windows import INSTITUTION_TIMEZONE, WINDOWS_BY_TERM_WEEK

# ADR 0054's marker for "no model answered", which lives in `app.ai.gateway`
# because the gateway is what knows one did not. An empty stream reaches no
# provider (ADR 0148 point 3), so this is what its stored row must name — and it
# is the value that makes "the provenance is read off the record, never
# re-derived from a constant" a measurable claim rather than a convention.
NOT_A_MODEL = "NOT_A_MODEL"

# ---------------------------------------------------------------------------
# The contract E4-06's work order settles, spelled once.
# ---------------------------------------------------------------------------

# SPEC §13 puts the task definitions in `backend/app/jobs/tasks.py`, and the
# work order appends this one there beside E3-06's `post_participation_scores`.
TASKS_MODULE = "app.jobs.tasks"
SUMMARY_JOB_TASK = "generate_weekly_summaries"

# The seam. The work order: "the walk accepts an optional `gateway: AIGateway |
# None` seam threaded to `summarize_stream` (default `process_gateway()`)". It is
# read off the *task*, because the task is the one name the work order settles —
# where the walk itself lives is the implementer's, and a test that imported a
# service module by a guessed name would be deciding that.
GATEWAY_PARAMETER = "gateway"

# The beat entry, and the slot the ticket settles: Monday 02:50, after E3-06's
# provider-free passback at 02:20 and before instructors read (SPEC §3.1's
# "reports available after window close Monday morning").
SCHEDULES_MODULE = "app.jobs.schedules"
BEAT_SCHEDULE_NAME = "BEAT_SCHEDULE"
BEAT_ENTRY_NAME = "generate-weekly-summaries"
BEAT_DAY_OF_WEEK = "mon"
BEAT_HOUR = "2"
BEAT_MINUTE = "50"

# ---------------------------------------------------------------------------
# E4-02's table, transcribed. See `tests/integration/test_report_schema.py` for
# the same transcription from the other side: two readings of one settled schema
# is deliberate, so a rename fails at a name in both rather than moving both
# sides of one comparison at once (`docs/MISTAKES.md` entry 19).
# ---------------------------------------------------------------------------

WEEKLY_SUMMARY_TABLE = "weekly_summary"
SUMMARY_SECTION_COLUMN = "section_id"
SUMMARY_WEEK_COLUMN = "week_id"
SUMMARY_STREAM_COLUMN = "stream"
SUMMARY_TEXT_COLUMN = "summary_text"
SUMMARY_RESPONSE_COUNT_COLUMN = "response_count"
SUMMARY_THEMES_COLUMN = "themes"
SUMMARY_PROMPT_VERSION_COLUMN = "prompt_version"
SUMMARY_MODEL_ID_COLUMN = "model_id"
SUMMARY_GENERATED_AT_COLUMN = "generated_at"
SUMMARY_ID_COLUMN = "id"

# The two values `weekly_summary.stream` stores, as E4-02 settles them.
STORED_INSTRUCTOR_STREAM = "INSTRUCTOR"
STORED_COURSE_STREAM = "COURSE"
STORED_STREAMS = (STORED_INSTRUCTOR_STREAM, STORED_COURSE_STREAM)

# E4-02's append-only moderation record. `decided_at` is what makes "the latest
# row governs" a question with an answer, so this suite always states it.
MODERATION_STATE_TABLE = "moderation_state"
MODERATION_ANSWER_COLUMN = "answer_id"
MODERATION_STATE_COLUMN = "state"
MODERATION_DECIDED_AT_COLUMN = "decided_at"

PUBLISHED = "PUBLISHED"
FLAGGED_COLLAPSED = "FLAGGED_COLLAPSED"
EXCLUDED = "EXCLUDED"
KEPT = "KEPT"

# SPEC §3.2's question positions, as `tests/fixtures/report_views.py` plants
# them: position 2 is the instructor comment and position 4 the course comment.
# Named here so a test says "an instructor comment" rather than "position 2".
INSTRUCTOR_COMMENT_POSITION = 2
COURSE_COMMENT_POSITION = 4
INSTRUCTOR_RATING_POSITION = 1
COURSE_RATING_POSITION = 3

# ---------------------------------------------------------------------------
# This suite's own values. None is a claim about anything the system decides.
# ---------------------------------------------------------------------------

# The two cohorts every world here is built on. Both start in term week 7
# (`SEEDED_COHORTS`), so term week 7 is course week 1 for each — a section whose
# course weeks are not its term weeks, which is the only kind that can tell the
# two axes apart — and the two sections share a week row, so a test about one
# section's rows cannot pass because it read the other's.
A_COHORT = "Q"
ANOTHER_COHORT = "F"

# The term week every world closes. Any of the eighteen would do; this one is
# chosen because both cohorts above are running in it.
A_CLOSED_TERM_WEEK = 7

# How far either side of a window's close the clock is stood. A minute rather
# than a microsecond, for `tests/fixtures/grading.py`'s reason: an offset clock
# (ADR 0109) is still moving while it is read, so a boundary cannot be stood on
# exactly, and a minute is four orders of magnitude inside the week it has to be
# told apart from.
A_MINUTE = timedelta(seconds=60)

# Where inside a day the clock is stood when a test needs a date rather than an
# instant. Noon, so the date is the same one read in UTC and in
# `America/New_York`.
NOON = 12

# The marker every planted comment of a stream carries, and the *only* way the
# gateway double below can know which stream it was asked about. Tokens that
# appear nowhere else in this repository, so a match is evidence
# (`docs/MISTAKES.md` entry 3): an ordinary word would also appear in the prompt
# template, and the double would then answer confidently about the wrong stream.
INSTRUCTOR_MARK = "Kq7ZvNb2Xt"
COURSE_MARK = "Pw4LmRc9Yd"
STREAM_MARKS = {INSTRUCTOR_STREAM: INSTRUCTOR_MARK, COURSE_STREAM: COURSE_MARK}

# What the double answers with when nothing else is asked for. A model id no
# constant in `app.ai.tasks` could be, which is what makes "the row names the
# model that answered" a measurement rather than two copies of one literal
# (ADR 0148's consequence: E4-06 reads the provenance off `record.summary`,
# "without re-deriving either from a constant").
A_MODEL_ID = "e4-06-job-test-model-7c1f"
A_SUMMARY_TEXT = "Several comments describe the Thursday session as too fast."

# A theme claiming one comment, which every stream that reaches the gateway has
# at least one of. The task refuses a theme claiming more comments than the week
# held (ADR 0148 point 5), so a default any larger would fail a stream with one
# comment for a reason having nothing to do with this ticket.
A_THEME_LABEL = "pace of the Thursday session"
A_THEME_COUNT = 1


def comment_text(stream_token: str, nonce: str) -> str:
    """One comment for `stream_token`, carrying its stream marker and a caller's nonce.

    The marker is what the gateway double reads the stream off; the nonce is what
    a test reads back — out of the prompt, to say which comments fed the call, or
    out of a log stream, to say that none of them did.
    """
    return f"{STREAM_MARKS[stream_token]} {nonce} the session's pacing is what this is about."


# ---------------------------------------------------------------------------
# The deliverables, named where a test can fail on them rather than error.
# ---------------------------------------------------------------------------

TASK_IS_OWED = (
    f"E4-06's work order appends `{SUMMARY_JOB_TASK}` to `{TASKS_MODULE}`, on the shape every "
    "other entry in that module takes: fireable by beat with no arguments, opening its own "
    "session. For every section and course week whose survey window has closed and which has no "
    "`weekly_summary` rows, it gathers the week's comments per stream, calls E4-05's "
    "`summarize_stream`, and stores one row per stream. It takes an optional "
    f"`{GATEWAY_PARAMETER}` so a test can substitute the provider — the seam E4-05 already "
    "publishes on `summarize_stream`, threaded through."
)


def summary_task() -> Any:
    """`generate_weekly_summaries`, or a failure naming the deliverable that owes it."""
    return named_in(tasks_module(), SUMMARY_JOB_TASK, TASK_IS_OWED)


def schedules_module() -> Any:
    """`app.jobs.schedules`, imported where a test can fail on it rather than error."""
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
            "one place this project's periodic work is declared, and E4-06 adds the "
            f"{BEAT_ENTRY_NAME!r} entry to it."
        )


def run_job(*, gateway: Any = None) -> Any:
    """Fire the task the way beat would, with a gateway substituted if one is given.

    The signature is bound by name rather than by trying call shapes until one
    stops raising, which is `tests/fixtures/report_views.py`'s device for
    `recompute_response_validity` and `tests/fixtures/summary_task.py`'s for
    `summarize_stream`: a helper that swallowed a `TypeError` would report a
    design nobody chose as working.

    **Two properties are asserted here rather than tolerated**, because both are
    the work order's and a driver that worked around either would hide it:

      - the task takes no *required* argument, since a beat entry fires it with
        none;
      - it accepts `gateway`, since without that seam no test in this suite can
        put a provider failure or a known answer in front of the walk, and the
        criteria about both would be unwritable.

    Where the walk itself lives is not asserted. The work order leaves it to the
    implementer — the task, or a service module — and every criterion in this
    suite is about what the walk *does*.
    """
    import inspect

    task = summary_task()
    underlying = getattr(task, "run", task)
    signature = inspect.signature(underlying)
    parameters = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]
    required = [parameter.name for parameter in parameters if parameter.default is parameter.empty]
    if required:
        pytest.fail(
            f"`{SUMMARY_JOB_TASK}{signature}` requires {required}. The beat entry fires it with no "
            "arguments at all, so a required parameter is a policy decision (which sections, since "
            "when, which provider) written into a signature where nobody reviewing the schedule "
            "would look."
        )
    if gateway is not None and not any(
        parameter.name == GATEWAY_PARAMETER for parameter in parameters
    ):
        pytest.fail(
            f"`{SUMMARY_JOB_TASK}{signature}` offers no `{GATEWAY_PARAMETER}` parameter. E4-06's "
            "work order settles the walk's optional gateway seam, defaulting to "
            "`process_gateway()`, and it is the only way a test can stand a provider failure or a "
            "known answer in front of this walk. Without it, criterion 2 (a provider failure "
            "mid-walk) and every assertion about what is stored are unwritable — which is an "
            "interface question for the ticket rather than something this fixture may guess at."
        )
    if gateway is None:
        return task()
    return task(**{GATEWAY_PARAMETER: gateway})


# ---------------------------------------------------------------------------
# The gateway doubles.
# ---------------------------------------------------------------------------


class _NoUsage:
    """A `TaskUsage` reporting nothing, for the entry point that returns one."""

    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_write_tokens = 0
    total_tokens = 0
    requests = 0
    details: dict[str, int] = {}  # noqa: RUF012


class StreamAwareGateway:
    """A gateway that answers about whichever stream's comments it was sent.

    **It is not a stand-in for a provider**, and the answers are supplied so the
    *job's* behaviour around them can be asserted: which rows it writes, what
    provenance it copies onto them, and what it does when one call fails
    (`docs/MISTAKES.md` entry 30 — a value a fixture supplies is not a value the
    suite can measure). Whether a summary is any good is SPEC §9.3's question and
    `tests/evals/summary/` is where it is asked.

    **The stream is read off the comments rather than off a call counter.** The
    job makes two calls per section-week and E4-05's task refuses an answer whose
    stream is not the one asked for (ADR 0148 point 2), so a double that answered
    in a fixed order would redden this suite the first time a walk visited the
    streams the other way round — a red about an order the ticket never settles.
    Every comment this suite plants carries its stream's marker, so the answer
    follows the request.

    **`fail_on` is a string planted in one section's comments**, which is how a
    provider failure is aimed at one section-week and not at the walk. It raises
    the caller's exception object, so the test names the class it is asserting
    about rather than this file naming one for it.

    Both entry points the repository already uses are answered — `run_task` and
    `run_task_with_usage` — because which of them the task reaches is not
    something a fixture may decide. Anything else fails naming what was reached.
    """

    def __init__(
        self,
        api: Any,
        *,
        fail_on: str | None = None,
        failure: BaseException | None = None,
        model_id: str = A_MODEL_ID,
        summary: str = A_SUMMARY_TEXT,
        themes: dict[str, Sequence[tuple[str, int]]] | None = None,
    ) -> None:
        self.__dict__["api"] = api
        self.__dict__["fail_on"] = fail_on
        self.__dict__["failure"] = failure
        self.__dict__["model_id"] = model_id
        self.__dict__["summary"] = summary
        self.__dict__["themes"] = themes or {
            INSTRUCTOR_STREAM: ((A_THEME_LABEL, A_THEME_COUNT),),
            COURSE_STREAM: ((A_THEME_LABEL, A_THEME_COUNT),),
        }
        self.__dict__["calls"] = []
        self.__dict__["prompts"] = []

    def _answer(self, kwargs: dict[str, Any]) -> Any:
        self.calls.append(dict(kwargs))
        prompt = str(kwargs.get("prompt", ""))
        self.prompts.append(prompt)

        if self.fail_on is not None and self.fail_on in prompt:
            if self.failure is None:  # pragma: no cover - a broken test, not a red
                pytest.fail(
                    "This double was told what to fail on and given no failure to raise, so the "
                    "call it was supposed to refuse would be answered instead."
                )
            raise self.failure

        asked = [token for token, mark in STREAM_MARKS.items() if mark in prompt]
        if len(asked) != 1:
            pytest.fail(
                f"The prompt this double was handed carries the markers of {asked} streams, and it "
                "reads the stream it is answering about off exactly one. Every comment this suite "
                f"plants carries its stream's marker ({STREAM_MARKS}); a prompt with both means the "
                "walk sent one stream's comments into the other's call, which is the cross-stream "
                "bleed ADR 0148 splits the calls to prevent, and a prompt with neither means it "
                "sent comments this suite did not plant.\n\n"
                f"The prompt was: {prompt[:400]!r}"
            )
        token = asked[0]

        output_model = self.api.contract(WEEKLY_SUMMARY_OUTPUT)
        theme_model = self.api.contract(COMMENT_THEME_CONTRACT)
        return output_model(
            stream=self.api.stream(token),
            summary=self.summary,
            themes=tuple(
                theme_model(label=label, comment_count=count) for label, count in self.themes[token]
            ),
            prompt_version=self.api.constant(SUMMARY_PROMPT_VERSION),
            model_id=self.model_id,
        )

    def run_task(self, **kwargs: Any) -> Any:
        return self._answer(kwargs)

    def run_task_with_usage(self, **kwargs: Any) -> Any:
        return self._answer(kwargs), _NoUsage()

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"The walk reached `{name}` on the gateway. This double answers `run_task` and "
            "`run_task_with_usage`, the two entry points this repository already uses; a third is "
            "an interface question for the ticket rather than something a fixture should guess at."
        )


class UnreachableGateway:
    """A gateway that fails on any use at all, for asserting that none was made.

    The device `tests/fixtures/summary_task.py`'s `RefusingGateway` uses, and for
    its reason: a run over zero closed weeks must reach no provider, and the way
    to assert that without naming the method a call would travel through is to
    make every attribute fail.
    """

    def __init__(self) -> None:
        self.__dict__["reached"] = []

    def __getattr__(self, name: str) -> Any:
        self.reached.append(name)
        pytest.fail(
            f"The walk reached `{name}` on the gateway for a run with no closed section-week to "
            "summarize. A run that finds nothing to do makes no model call at all — an empty walk "
            "that still spends a provider request is a bill nobody chose, every Monday, per "
            "section."
        )


# ---------------------------------------------------------------------------
# The world, and reading `weekly_summary` back.
# ---------------------------------------------------------------------------


def require_summary_table(tables: dict[str, Any]) -> Any:
    """`weekly_summary` off `Base.metadata`, or a failure naming what is missing.

    Called from a test body, never from a fixture, so a tree without E4-02's
    migration produces a FAILED naming the table rather than an ERROR raised
    inside somebody's setup (`docs/MISTAKES.md` entry 44).
    """
    table = tables.get(WEEKLY_SUMMARY_TABLE)
    if table is None:
        pytest.fail(
            f"There is no `{WEEKLY_SUMMARY_TABLE}` table (there are {sorted(tables)}). E4-02 "
            "creates it in `backend/app/models/report.py` — one row per section, course week and "
            "stream, carrying the summary text, the response count it drew from, the themes, and "
            "SPEC §7.4's provenance pair — and E4-06 is the only thing that writes one."
        )
    missing = [
        column
        for column in (
            SUMMARY_SECTION_COLUMN,
            SUMMARY_WEEK_COLUMN,
            SUMMARY_STREAM_COLUMN,
            SUMMARY_TEXT_COLUMN,
            SUMMARY_RESPONSE_COUNT_COLUMN,
            SUMMARY_THEMES_COLUMN,
            SUMMARY_PROMPT_VERSION_COLUMN,
            SUMMARY_MODEL_ID_COLUMN,
            SUMMARY_GENERATED_AT_COLUMN,
        )
        if column not in table.c
    ]
    if missing:
        pytest.fail(
            f"`{WEEKLY_SUMMARY_TABLE}` declares no {missing} — it declares "
            f"{[column.name for column in table.columns]}. E4-02 settles every one of them and "
            "this suite reads them by those names; a column spelled some other way is a one-line "
            "change at the top of `tests/fixtures/summary_job.py`."
        )
    return table


def themes_text(stored: Any) -> str:
    """Whatever the themes column holds, as one string a test can search.

    The column's storage type is E4-02's and this suite does not pin it: what is
    asserted is that the themes the model produced reached the row, which is true
    of a JSON array, of a list of objects, and of anything else that keeps the
    labels and the counts. A reader that decoded one shape would be asserting the
    shape instead.
    """
    try:
        return json.dumps(stored, default=str)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return str(stored)


class SummaryWorld:
    """One term, its weeks, sections in two cohorts, and a clock a test moves.

    Everything about the calendar, the question set and the answers is
    `ReportWorld`'s and is not re-implemented here; what this adds is the clock —
    which is what makes a week *closed*, and therefore the whole of what the job
    selects on — and a reader for the table the job writes.
    """

    def __init__(self, world: ReportWorld, rows: Any, overrides: Any) -> None:
        self.world = world
        self.rows = rows
        self.overrides = overrides

    # -- building -------------------------------------------------------------

    def build(self, cohort: str = A_COHORT) -> SummaryWorld:
        """Seed the term, its eighteen weeks, one section of `cohort`, and the question set."""
        self.world.build(cohort=cohort)
        return self

    def add_section(self, cohort: str) -> Any:
        """A second section, of another cohort, in the same term and over the same weeks."""
        return self.world.section(cohort)

    def section_id(self, cohort: str = A_COHORT) -> Any:
        return self.world.section_id(cohort)

    def week_id(self, term_week: int = A_CLOSED_TERM_WEEK) -> Any:
        return self.world.week_id(term_week)

    def respond(
        self,
        subject: str,
        *,
        cohort: str = A_COHORT,
        term_week: int = A_CLOSED_TERM_WEEK,
        instructor_comment: str | None = None,
        course_comment: str | None = None,
    ) -> dict[int, Any]:
        """One student's whole response for a section-week, with the comments given.

        Both ratings are always answered and both comments are optional, which is
        SPEC §3.2's own shape: a comment is required only where its rating is two
        or below, so a week of nine responses carrying three comments is the
        ordinary case rather than a contrivance — and it is the case that tells
        `response_count` apart from `len(comments)`.

        Answers to the two comment positions are omitted rather than blanked when
        no text is given: E2-05 refuses an `answer` holding no value, so an absent
        row is the only spelling this schema has for a question left blank.
        """
        student = self.world.student(subject, cohorts=(cohort,))
        answers: dict[int, Any] = {INSTRUCTOR_RATING_POSITION: 4, COURSE_RATING_POSITION: 4}
        if instructor_comment is not None:
            answers[INSTRUCTOR_COMMENT_POSITION] = instructor_comment
        if course_comment is not None:
            answers[COURSE_COMMENT_POSITION] = course_comment
        _response, written = self.world.respond(
            student, term_week=term_week, answers=answers, cohort=cohort
        )
        return written

    def decide(self, answer: Any, state: str, *, decided_at: datetime) -> Any:
        """Append one `moderation_state` row about one comment.

        Appended, always: E4-02 settles the record as append-only with the latest
        row governing, so a second decision is a new row rather than an edit
        (ADR 0145). `decided_at` is required and never defaulted — which of two
        rows is the latest is the whole subject of the near miss this suite plants.
        """
        table = self.world.tables.get(MODERATION_STATE_TABLE)
        if table is None:
            pytest.fail(
                f"There is no `{MODERATION_STATE_TABLE}` table (there are "
                f"{sorted(self.world.tables)}). E4-02 creates it as SPEC §5.2's lifecycle in "
                "append-only form, and this suite plants rows in it to prove the summary job's "
                "moderation filter is real rather than vacuous."
            )
        return self.world.seed(
            MODERATION_STATE_TABLE,
            {},
            **{
                MODERATION_ANSWER_COLUMN: answer[self.world.key_of("answer")],
                MODERATION_STATE_COLUMN: state,
                MODERATION_DECIDED_AT_COLUMN: decided_at,
            },
        )

    def plant_summary(
        self,
        *,
        cohort: str,
        term_week: int,
        stream: str,
        summary_text: str,
        response_count: int,
        prompt_version: str,
        model_id: str,
        generated_at: datetime,
        themes: Any = None,
    ) -> Any:
        """One `weekly_summary` row this suite wrote, with every value the caller's.

        **The idempotence case starts from rows the run under test did not
        produce**, which is `docs/MISTAKES.md` entry 31 — "'running it twice is
        safe' was tested only against a database the loader itself had filled".
        A second run compared against a first run's output cannot tell "left
        alone" from "rewritten identically", because the writer would produce the
        same values either way; a row carrying values no run of this job could
        produce can.

        Nothing is defaulted. `generated_at` in particular is the caller's,
        because whether it moved is the whole question a rewrite is detected by.
        """
        require_summary_table(self.world.tables)
        return self.world.seed(
            WEEKLY_SUMMARY_TABLE,
            {},
            **{
                SUMMARY_SECTION_COLUMN: self.section_id(cohort),
                SUMMARY_WEEK_COLUMN: self.week_id(term_week),
                SUMMARY_STREAM_COLUMN: stream,
                SUMMARY_TEXT_COLUMN: summary_text,
                SUMMARY_RESPONSE_COUNT_COLUMN: response_count,
                SUMMARY_THEMES_COLUMN: [] if themes is None else themes,
                SUMMARY_PROMPT_VERSION_COLUMN: prompt_version,
                SUMMARY_MODEL_ID_COLUMN: model_id,
                SUMMARY_GENERATED_AT_COLUMN: generated_at,
            },
        )

    def commit(self) -> None:
        """Make everything seeded so far visible to the connection the task opens."""
        self.rows.commit()

    # -- the clock ------------------------------------------------------------

    def closes_at(self, term_week: int = A_CLOSED_TERM_WEEK) -> datetime:
        """When one term week's survey window closes, from the hand-written calendar.

        `tests/fixtures/survey_windows.py` writes all thirty-six instants out by
        hand rather than deriving them, and a control test reads each back into
        `America/New_York` and requires SPEC §3.1's Friday-to-Sunday rhythm. This
        suite reads them and computes nothing.
        """
        return WINDOWS_BY_TERM_WEEK[term_week][1]

    def clock_to(self, instant: datetime) -> datetime:
        """Move the development clock to `instant`, committed so every connection sees it.

        The task opens its own session, so an override written inside this suite's
        transaction would leave the job reading real time — which in a suite whose
        calendar is Fall 2026 means a walk over whichever weeks happen to have
        closed on the day CI runs.
        """
        self.overrides.set(pretend_now=instant, anchored_at=datetime.now(UTC))
        return instant

    def clock_after(self, term_week: int = A_CLOSED_TERM_WEEK) -> datetime:
        """Stand the clock a minute after one week's window closed."""
        return self.clock_to(self.closes_at(term_week) + A_MINUTE)

    def clock_before(self, term_week: int = A_CLOSED_TERM_WEEK) -> datetime:
        """Stand the clock a minute before one week's window closes — inside the window."""
        return self.clock_to(self.closes_at(term_week) - A_MINUTE)

    # -- reading `weekly_summary` back ----------------------------------------

    def summaries(self, *, section_id: Any = None) -> list[dict[str, Any]]:
        """Every stored summary, or every one for a section, on a connection that sees commits.

        This suite's transaction is ended first so a row the task's own connection
        committed is visible: the job opens a session of its own, and a session
        holding a transaction since it seeded would go on seeing the table as it
        was — which reads as "the job wrote nothing".
        """
        from sqlalchemy import select

        table = require_summary_table(self.world.tables)
        self.rows.commit()
        statement = select(table)
        if section_id is not None:
            statement = statement.where(table.c[SUMMARY_SECTION_COLUMN] == section_id)
        return [dict(row) for row in self.rows.session.execute(statement).mappings()]

    def summaries_by_stream(self, *, section_id: Any) -> dict[str, dict[str, Any]]:
        """One section's summaries for one week, keyed by the stream each is about.

        Two things are reported here rather than indexed away, because a mapping
        would hide both behind rows that look correct. Two rows for one section,
        week and stream is E4-02's uniqueness rule broken. Rows for **two weeks**
        mean the caller's world has more than one closed week in it, and a mapping
        keyed by stream alone would answer with whichever the walk wrote last — so
        every assertion made through this reader would be about an arbitrary week.
        """
        rows = self.summaries(section_id=section_id)
        weeks = {str(row[SUMMARY_WEEK_COLUMN]) for row in rows}
        if len(weeks) > 1:  # pragma: no cover - a broken test, not a red
            pytest.fail(
                f"This section carries summaries for {sorted(weeks)} and this reader keys them by "
                "stream alone, so it cannot say which week an assertion is about. A test with more "
                "than one closed week reads `summaries()` and says which week it means."
            )
        found: dict[str, dict[str, Any]] = {}
        for row in rows:
            stream = str(row[SUMMARY_STREAM_COLUMN])
            if stream in found:  # pragma: no cover - a red, not a branch
                pytest.fail(
                    f"Two `{WEEKLY_SUMMARY_TABLE}` rows exist for one section, week and the "
                    f"{stream} stream. E4-02 makes that grain unique, so this is either a "
                    "constraint that did not land or a walk that wrote twice."
                )
            found[stream] = row
        return found

    def identity_of(self, rows: Sequence[dict[str, Any]]) -> dict[Any, tuple[Any, ...]]:
        """Each row's key and the three values a rewrite would change.

        The primary key says the row was not replaced; `generated_at` says it was
        not rewritten in place with a fresh instant; the text and the provenance
        say its content is the one that was there. A count would say none of that
        — a walk that deleted two rows and wrote two more keeps the count exactly.
        """
        return {
            row[SUMMARY_ID_COLUMN]: (
                row[SUMMARY_GENERATED_AT_COLUMN],
                row[SUMMARY_TEXT_COLUMN],
                row[SUMMARY_PROMPT_VERSION_COLUMN],
                row[SUMMARY_MODEL_ID_COLUMN],
                row[SUMMARY_RESPONSE_COUNT_COLUMN],
            )
            for row in rows
        }


def _plain_import(name: str) -> Any:
    """Import one `app.*` module, answering `None` where it does not exist.

    The signature `SummaryApi` takes, supplied by plain import rather than by
    `import_app_module`, and the distinction is *when* rather than *whether*.
    `import_app_module` drops every `app.*` module out of `sys.modules` before
    importing, and `summary_job_environment` does exactly that once, at setup,
    which is what binds `app.db` to this container (dispute E4-06-02). What must
    not happen is a second drop **mid-test**: these suites hold a committed world
    built through `Base.metadata` and a task that opens its own session, and the
    gateway double reaches for a contract class *while the job is running* — so a
    re-import at that moment would hand the double a `WeeklySummaryOutput` from a
    registry the task under test is not validating against. This importer resolves
    whatever the setup-time import left in `sys.modules` and disturbs nothing.
    """
    import importlib

    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (absent == name or name.startswith(f"{absent}.")):
            raise
        return None


@pytest.fixture
def summary_contracts() -> SummaryApi:
    """E4-05's contracts and constants, reached without disturbing `sys.modules`.

    The same accessor `tests/unit/test_the_weekly_summary_task.py` uses — the same
    named failures for a deliverable that is not there — over the importer above.
    """
    return SummaryApi(_plain_import)


DATABASE_MODULE = "app.db"
ENGINE_ATTRIBUTE = "engine"


@pytest.fixture
def summary_job_environment(
    care_service_environment: dict[str, str],
    window_settings: Any,
    migrated_database: Any,
    import_app_module: Callable[[str], ModuleType | None],
) -> Any:
    """`Settings` in a development environment, with `app.db` bound to this container.

    Three things this suite cannot do without, stated rather than inherited
    (`docs/MISTAKES.md` entry 40):

      - **`DATABASE_URL` names this container's application role.**
        `care_service_environment` lays `.env.example`'s whole surface down and
        then overwrites the database variables, which is what any `app.*` import
        reaching `app.db` needs. It matters more here than it usually does: the
        engine `app.db` builds connects as `pulse_app`, so every row this job
        writes is written through the connection production uses, and a missing
        grant is a failure this suite sees rather than one it drives around
        (`docs/MISTAKES.md` entry 46).
      - **`ENVIRONMENT` is `development`**, because the clock override applies
        nowhere else (ADR 0109 part 4) and every test here decides which weeks are
        closed by moving it.
      - **`INSTITUTION_TIMEZONE` is stated**, because SPEC §3.1 puts every window
        instant at a wall-clock time in it.

    **Stating the variable is not enough, and dispute E4-06-02 is what measured
    that.** `app.db` builds its engine *at import time* from a `Settings()` of its
    own (ADR 0013, ADR 0010), and `sys.modules` then keeps the result for the rest
    of the worker — so this environment governs only if `app.db` has not already
    been imported. `tests/integration/test_alembic_baseline.py` imports it while
    `DATABASE_URL` points at a throwaway database that the same test then drops,
    and under `-n 4` which worker gets that module relative to these is not
    something any change here controls. Measured: every behavioural test in this
    ticket failed on `database "e0_04_…" does not exist` when that module ran
    first in the same process, and passed when it did not.

    So the module is **imported through `import_app_module` after the environment
    is laid down**, which drops `app.*` out of `sys.modules` and rebuilds the
    engine against the value this fixture just set. That is the step
    `tests/integration/test_the_launch_replay_purge_runs_as_pulse_app.py`'s
    `tasks_on_the_application_role` already takes, for the same reason and against
    the same module. The objection this file used to carry against
    `import_app_module` — two model registries, and a re-import while the gateway
    double is reaching for a contract class — was about re-importing *mid-test*;
    here it happens at setup, before any world is committed, before the double
    exists, and before `_plain_import` has cached anything.

    **And the binding is asserted rather than assumed**, which is the half that
    survives the next module to import `app.db` first. Without it a mis-binding
    arrives as eighteen connection errors pointing at the walk; with it, it arrives
    as one sentence naming the cause. That is `docs/MISTAKES.md` entry 44's rule
    applied to a hazard rather than to a deliverable — and this is deliberately the
    one guard in this file that does live in a fixture, because what it checks is
    the state of the process this fixture has just configured, and a failure of it
    *is* a setup failure rather than an assertion about the ticket.

    The order of the fixtures above is load-bearing: `care_service_environment` is
    asked for first so its database values are the ones standing when
    `window_settings` builds `Settings` and when the import below runs.
    """
    module = import_app_module(DATABASE_MODULE)
    assert module is not None, (
        f"`{DATABASE_MODULE}` does not exist, so nothing in this suite can reach the connection "
        "the Monday task opens for itself. E0-04 ships it."
    )
    engine = getattr(module, ENGINE_ATTRIBUTE, None)
    reached = getattr(getattr(engine, "url", None), "database", None)
    expected = urlsplit(migrated_database.application_url).path.lstrip("/")
    assert reached == expected, (
        f"`{DATABASE_MODULE}.{ENGINE_ATTRIBUTE}` is bound to {reached!r} and this container's "
        f"database is {expected!r}. `app.db` builds its engine at import time (ADR 0013) and "
        "`sys.modules` keeps it, so a module imported earlier in this worker under some other "
        "`DATABASE_URL` decides where every Celery task in this process connects — dispute "
        "E4-06-02 measured exactly that, with `test_alembic_baseline.py`'s throwaway database "
        "winning the race under `-n 4`. The re-import above is supposed to have undone it. If "
        f"`{DATABASE_MODULE}` has renamed its engine, this reading answers `None` for every run "
        "and that is a one-line change here rather than a fact about the job."
    )
    return window_settings


@pytest.fixture
def summary_world(
    summary_job_environment: Any,
    committed_report_world: ReportWorld,
    committed_rows: Any,
    committed_clock_overrides: Any,
) -> Iterator[SummaryWorld]:
    """The world E4-06's job walks, **unbuilt** — the caller decides what is in it.

    Unbuilt for `docs/MISTAKES.md` entry 30's reason: which weeks have closed,
    which streams carry comments and how many students answered are the things
    each criterion is about, so a fixture that chose them would be answering the
    question rather than posing it.

    **`summary_job_environment` is named first on purpose**: it drops and re-imports
    `app.*` to bind `app.db` to this container (dispute E4-06-02), so it runs before
    anything else here holds a reference into those modules. Bind, then build.
    """
    yield SummaryWorld(committed_report_world, committed_rows, committed_clock_overrides)


@pytest.fixture
def summary_job_contract() -> Any:
    """The names E4-06's test modules read the job through.

    Handed over as a fixture rather than imported, for the reason every fixtures
    module here gives: an import of a fixtures module by name depends on where
    pytest put `tests/` on `sys.path`, and an import error is not a red.
    """

    class SummaryJobContract:
        tasks_module_name = TASKS_MODULE
        tasks_logger = TASKS_MODULE
        schedules_module_name = SCHEDULES_MODULE
        task_name = SUMMARY_JOB_TASK
        gateway_parameter = GATEWAY_PARAMETER
        beat_schedule_name = BEAT_SCHEDULE_NAME
        beat_entry_name = BEAT_ENTRY_NAME
        beat_day_of_week = BEAT_DAY_OF_WEEK
        beat_hour = BEAT_HOUR
        beat_minute = BEAT_MINUTE

        table = WEEKLY_SUMMARY_TABLE
        section_column = SUMMARY_SECTION_COLUMN
        week_column = SUMMARY_WEEK_COLUMN
        stream_column = SUMMARY_STREAM_COLUMN
        text_column = SUMMARY_TEXT_COLUMN
        response_count_column = SUMMARY_RESPONSE_COUNT_COLUMN
        themes_column = SUMMARY_THEMES_COLUMN
        prompt_version_column = SUMMARY_PROMPT_VERSION_COLUMN
        model_id_column = SUMMARY_MODEL_ID_COLUMN
        generated_at_column = SUMMARY_GENERATED_AT_COLUMN
        id_column = SUMMARY_ID_COLUMN
        stored_streams = STORED_STREAMS
        stored_instructor = STORED_INSTRUCTOR_STREAM
        stored_course = STORED_COURSE_STREAM

        published = PUBLISHED
        flagged_collapsed = FLAGGED_COLLAPSED
        excluded = EXCLUDED
        kept = KEPT

        a_cohort = A_COHORT
        another_cohort = ANOTHER_COHORT
        closed_term_week = A_CLOSED_TERM_WEEK
        model_id = A_MODEL_ID
        summary_text = A_SUMMARY_TEXT
        a_minute = A_MINUTE
        noon = NOON
        institution_timezone = INSTITUTION_TIMEZONE
        development = DEVELOPMENT
        environment_variable = ENVIRONMENT_VARIABLE
        institution_timezone_variable = INSTITUTION_TIMEZONE_VARIABLE

        empty_week_prompt_version_name = EMPTY_WEEK_PROMPT_VERSION
        empty_week_summary_name = EMPTY_WEEK_SUMMARY
        not_a_model_name = NOT_A_MODEL
        summary_prompt_version_name = SUMMARY_PROMPT_VERSION
        instructor_stream_token = INSTRUCTOR_STREAM
        course_stream_token = COURSE_STREAM

        task = staticmethod(summary_task)
        schedules = staticmethod(schedules_module)
        run = staticmethod(run_job)
        require_table = staticmethod(require_summary_table)
        themes_text = staticmethod(themes_text)
        comment = staticmethod(comment_text)
        named_in = staticmethod(named_in)

    return SummaryJobContract()
