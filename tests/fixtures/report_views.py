"""E4-03 — the world the three report views aggregate, and how a test reads one.

Four test modules need the same things: a section whose course weeks are not its
term weeks, a question set whose questions carry E4-02's `stream`, students who
answered the values the test chose, and one way of reading a row back out of a
view. A copy of any of them in each module is `docs/MISTAKES.md` entry 13, so
they all live here.

**What this file decides, and what it refuses to.** Every table and column below
is transcribed from a settled record — E2-05's survey schema (`response`,
`answer`, `question`, `question_set`, `classification`), E0-08's `enrollment`,
E2-06's `survey_window`, SPEC §3.2's five questions and their two streams — with
one exception, stated here rather than buried: **the three view names, their
column lists and `question.stream`'s vocabulary are E4-03's and E4-02's work
orders**, quoted on the constants that carry them. Nothing else here is this
file's invention, and nothing here computes a mean, a median, a count or a
stream: every number a test asserts is arithmetic the test writes out by hand
over values it supplied, because a fixture that did the arithmetic would be a
second implementation for the tests to agree with (`docs/MISTAKES.md` entries 19
and 30).

**Nothing raises from a fixture.** `report_world` hands back an *unbuilt* world
and every guard — the view is absent, `question.stream` is absent, a column the
suite reads is missing — is a `pytest.fail` reached from a test body through
`ReportWorld.build` or through `require_report_view`. On a tree where E4-03 is
unbuilt each of these modules is therefore a **failed** test naming the missing
deliverable rather than an error in setup, which is `docs/MISTAKES.md` entry 44's
rule and the difference between a red suite and a broken one.

**The clock is never read.** These views are pure aggregates over stored rows:
they take no `now`, so no test here moves the development clock and no answer
here depends on the date CI runs on (the ticket's third known trap). The window
rows are seeded because `response` may reference one, not because anything reads
their instants.

**`tests/fixtures/grading.py` is deliberately not extended.** E3-03's world
plants a question set without a `stream`, its answers carry one fixed value per
shape, and seven modules depend on it; the values a distribution and a median are
asserted over have to be the caller's, and widening that file would put this
ticket's fixture edits in the same file E4-02's branch is changing.
"""

from collections.abc import Mapping, Sequence
from datetime import timedelta
from decimal import Decimal
from importlib import import_module
from typing import Any

import pytest
from sqlalchemy import text

from fixtures.clock import DEVELOPMENT
from fixtures.grading import (
    CLASSIFICATION_TASK_COLUMN,
    CLASSIFICATION_VERDICT_COLUMN,
    CLASSIFIED_AT_COLUMN,
    COMMENT_VALIDITY_TASK,
    ENDED_ON_COLUMN,
    ENROLLMENT_TABLE,
    RESPONSE_IS_VALID_COLUMN,
    RESPONSE_SECTION_COLUMN,
    RESPONSE_TERM_COLUMN,
    RESPONSE_USER_COLUMN,
    RESPONSE_WEEK_COLUMN,
    STARTED_ON_COLUMN,
    SUBSTANTIVE,
    single_column_link,
)
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
    STEP_COLUMN,
    USER_TABLE,
    VERSION_COLUMN,
    WORKLOAD_BOUNDS,
    WORKLOAD_HOURS_COLUMN,
    shape_column,
)
from fixtures.supervision import require_table, single_primary_key
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
    model_for,
)

# ---------------------------------------------------------------------------
# The three views, as E4-03's work order settles them.
# ---------------------------------------------------------------------------

# The object names follow the file names the work order spells —
# `report_rating_distribution_v001.sql`, `report_workload_v001.sql`,
# `report_response_counts_v001.sql` — through
# [ADR 0041](../../docs/adr/0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md),
# which puts a view's SQL in `backend/app/views_sql/<object>_v<NNN>.sql`. That is
# how `section_enrollment_count_v001.sql` names `section_enrollment_count`, and
# it is the one rule in the repository that maps a file to a relation.
RATING_DISTRIBUTION_VIEW = "report_rating_distribution"
WORKLOAD_VIEW = "report_workload"
RESPONSE_COUNTS_VIEW = "report_response_counts"

# What each view returns, and the whole of it. Transcribed from the work order's
# settled decisions 2, 3 and 5: "rows (section_id, week_id, stream, rating,
# responses)", "rows (section_id, week_id, workload_mean, workload_median)",
# "rows (section_id, week_id, responses, valid_responses)".
#
# **These are equalities rather than floors**, which is the ticket's first
# criterion in as many words: "a test asserts the view's column list against an
# expected set — a widened view is a red test, not a quiet diff". A column added
# to one of these views is a column an instructor reads, and it arrives here with
# the sentence that admits it or it does not arrive.
REPORT_VIEWS: dict[str, tuple[str, ...]] = {
    RATING_DISTRIBUTION_VIEW: ("section_id", "week_id", "stream", "rating", "responses"),
    WORKLOAD_VIEW: ("section_id", "week_id", "workload_mean", "workload_median"),
    RESPONSE_COUNTS_VIEW: ("section_id", "week_id", "responses", "valid_responses"),
}

SECTION_COLUMN = "section_id"
WEEK_COLUMN = "week_id"

# ---------------------------------------------------------------------------
# E4-02's column, and SPEC §3.2's two streams.
# ---------------------------------------------------------------------------

# The column E4-02 puts on `question`, spelled exactly as E4-03's work order
# settles it: "`question.stream` — E4-02's column, Text 'INSTRUCTOR'/'COURSE'",
# NULL for the workload question and closed by a `CHECK`. Spelled rather than
# discovered because the work order settles it; a fixture that went looking for
# "some text column carrying two values" would bind to whatever happened to be
# there.
STREAM_COLUMN = "stream"
INSTRUCTOR_STREAM = "INSTRUCTOR"
COURSE_STREAM = "COURSE"

# SPEC §3.2's five questions, read by the sentence in E4-03's own Context: "Q1
# ratings and Q2 comments are the instructor stream, Q3 and Q4 the course stream,
# Q5 the workload figure." The workload question carries no stream at all, which
# is what the `CHECK` E4-02's work order describes requires of it.
SPEC_QUESTION_LAYOUT: tuple[tuple[int, str, str | None], ...] = (
    (1, "rating", INSTRUCTOR_STREAM),
    (2, "comment", INSTRUCTOR_STREAM),
    (3, "rating", COURSE_STREAM),
    (4, "comment", COURSE_STREAM),
    (5, "workload", None),
)

# The same five shapes with the two streams exchanged, for the ticket's seventh
# criterion: "a second question-set version with a different question order still
# maps ratings to the right stream, proven with a planted set". Position 1 is a
# *course* rating here and position 3 an instructor one, so a view that mapped a
# rating by its ordinal rather than by `question.stream` answers this set exactly
# backwards.
SWAPPED_QUESTION_LAYOUT: tuple[tuple[int, str, str | None], ...] = (
    (1, "rating", COURSE_STREAM),
    (2, "comment", COURSE_STREAM),
    (3, "rating", INSTRUCTOR_STREAM),
    (4, "comment", INSTRUCTOR_STREAM),
    (5, "workload", None),
)

FIRST_VERSION = 1
SECOND_VERSION = 2

# ---------------------------------------------------------------------------
# This suite's own values. None of them is a claim about anything the system
# decides — every one is an input a test names and a fixture writes down.
# ---------------------------------------------------------------------------

# **A cohort whose course weeks are not its term weeks.** `F` runs six weeks from
# term week 7 (`SEEDED_COHORTS`, transcribed from `scripts/seed.py`), so a view
# that keyed a row by a course-week number rather than by the `week` row's id
# would answer week 1 where these tests ask about term week 7. The second cohort
# is `Q`, twelve weeks from term week 7, so the two sections share their weeks
# and the cross-section boundary is about the section and nothing else.
DEFAULT_COHORT = "F"
SECOND_COHORT = "Q"

# The stored text of a comment answer: long enough to clear SPEC §3.3's character
# floor, and read back by nothing here. What a comment is *worth* is the validity
# service's answer, never this file's.
A_COMMENT = "the pacing in week 3 was too fast and the reading load doubled"

# How long before its window closes a seeded response was submitted, and how long
# before that its comment was classified. Both are inside the window and neither
# is read back; they exist so no row carries an instant that contradicts the
# calendar it belongs to.
SUBMITTED_BEFORE_CLOSE = timedelta(hours=1)
CLASSIFIED_BEFORE_CLOSE = timedelta(minutes=30)

# How far apart two classifications of one comment are placed. A later verdict is
# the current one (`app/services/validity.py` orders by `classified_at`), and an
# hour is far enough that no clock resolution question arises.
A_LATER_VERDICT = timedelta(hours=1)

# ---------------------------------------------------------------------------
# The validity service, for the ticket's sixth criterion.
# ---------------------------------------------------------------------------

# SPEC §13 puts a service under `backend/app/services/`, and E2-08's work order
# names this one. The function is named by a record rather than guessed at:
# `docs/tickets/e3/.attempts/E3-03.md` lists "`backend/app/services/validity.py`
# `recompute_response_validity`" among the docstrings that ticket corrected, and
# E4-03's work order settles what it is for — "`is_valid` is maintained from each
# comment's CURRENT verdict by `app/services/validity.py` … the test drives it
# through the validity service's own recompute, never by editing the column".
#
# **Its signature is settled nowhere**, so `recompute_validity` below binds
# parameters by name and fails naming the one it cannot fill, which is the device
# `tests/fixtures/submit.py` uses for `issue_session` and for `issue_csrf_token`
# and for the same reason: an interface a ticket leaves open is a question for the
# ticket, and a guess written into a fixture answers it silently.
VALIDITY_SERVICE_MODULE = "app.services.validity"
RECOMPUTE_FUNCTION = "recompute_response_validity"

# How the one response the recompute is about is handed over. Two spellings,
# because both are ordinary: the mapped row, or its primary key.
RESPONSE_PARAMETERS = ("response", "response_id")
SESSION_PARAMETERS = ("session", "db", "db_session")


# ---------------------------------------------------------------------------
# Reading a view.
# ---------------------------------------------------------------------------

# Every column of one relation in `public`, from `pg_catalog` rather than from
# `information_schema`. The difference matters for one caller: the information
# schema shows a role only the relations it holds some privilege on, so a
# column list read there as `pulse_app` would come back empty for a view nobody
# granted — which is a *missing grant* reported as a missing view.
RELATION_COLUMNS = """
    SELECT a.attname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
    WHERE n.nspname = 'public'
      AND c.relname = :relation
      AND c.relkind IN ('v', 'm')
    ORDER BY a.attnum
"""


def report_view_columns(connection: Any, view: str) -> tuple[str, ...]:
    """Every column `public.<view>` returns, in order, or an empty tuple if it is not there."""
    rows = connection.execute(text(RELATION_COLUMNS), {"relation": view})
    return tuple(str(row[0]) for row in rows)


def require_report_view(connection: Any, view: str) -> tuple[str, ...]:
    """`view`'s columns, or a failure naming the deliverable that is missing.

    Called as the first statement of a test body rather than from a fixture, so
    that on a tree where E4-03 is unbuilt these modules are **failed** tests
    naming the view rather than errors raised inside somebody's setup
    (`docs/MISTAKES.md` entry 44). The second half — the columns this suite reads
    — is checked here too, because a `SELECT` naming a column the view does not
    have raises `UndefinedColumn` from the driver, which is the same broken red in
    a different coat.
    """
    expected = REPORT_VIEWS[view]
    present = report_view_columns(connection, view)
    if not present:
        pytest.fail(
            f"There is no view `public.{view}` in the migrated database. E4-03 ships it from "
            f"`backend/app/views_sql/{view}_v001.sql`, executed by that ticket's migration the way "
            "the identity-separated views are executed (ADR 0041: the SQL lives in a versioned "
            "file and the revision runs it by name). It is keyed by `(section_id, week_id)` and "
            f"returns {list(expected)}."
        )
    missing = [column for column in expected if column not in present]
    if missing:
        pytest.fail(
            f"`public.{view}` does not return {missing}; it returns {list(present)}. E4-03's work "
            f"order settles this view's rows as {list(expected)}, and every test in this suite "
            "reads them by those names."
        )
    return present


def report_rows(
    connection: Any, view: str, *, section_id: Any, week_id: Any = None
) -> list[dict[str, Any]]:
    """Every row `view` holds for one section, or for one section-week.

    The column list is the constant above rather than `SELECT *`, so a view that
    grew a column is caught by the column-list test with a message about the
    widening instead of quietly appearing in every other assertion here.
    """
    require_report_view(connection, view)
    selected = ", ".join(REPORT_VIEWS[view])
    clause = f"WHERE {SECTION_COLUMN} = :section"
    parameters: dict[str, Any] = {"section": section_id}
    if week_id is not None:
        clause += f" AND {WEEK_COLUMN} = :week"
        parameters["week"] = week_id
    # The relation and the columns are module constants, never a caller's string.
    statement = text(f"SELECT {selected} FROM public.{view} {clause}")  # noqa: S608
    return [dict(row) for row in connection.execute(statement, parameters).mappings()]


def distribution_rows(
    connection: Any, *, section_id: Any, week_id: Any = None
) -> list[tuple[str, Decimal, int]]:
    """The distribution as a sorted list of `(stream, rating, responses)`.

    A **list** rather than a mapping keyed by `(stream, rating)`, deliberately: a
    view that emitted the same pair twice would collapse into one entry under a
    mapping and the count would look right, which is the shape a `GROUP BY`
    missing a column produces.
    """
    rows = report_rows(connection, RATING_DISTRIBUTION_VIEW, section_id=section_id, week_id=week_id)
    return sorted(
        (str(row["stream"]), Decimal(str(row["rating"])), int(row["responses"])) for row in rows
    )


def workload_row(connection: Any, *, section_id: Any, week_id: Any) -> dict[str, Any] | None:
    """The one workload row for a section-week, or `None` where the view yields none.

    More than one row for one `(section_id, week_id)` is a failure of the view's
    own key, so it is reported here rather than being silently indexed away.
    """
    rows = report_rows(connection, WORKLOAD_VIEW, section_id=section_id, week_id=week_id)
    if len(rows) > 1:
        pytest.fail(
            f"`{WORKLOAD_VIEW}` returned {len(rows)} rows for one section-week ({rows}). The work "
            "order keys all three report views by `(section_id, week_id)`, so a second row for one "
            "key is a grouping defect rather than a value this suite can read."
        )
    return rows[0] if rows else None


def response_counts_row(connection: Any, *, section_id: Any, week_id: Any) -> dict[str, Any] | None:
    """The one response-counts row for a section-week, or `None`. See `workload_row`."""
    rows = report_rows(connection, RESPONSE_COUNTS_VIEW, section_id=section_id, week_id=week_id)
    if len(rows) > 1:
        pytest.fail(
            f"`{RESPONSE_COUNTS_VIEW}` returned {len(rows)} rows for one section-week ({rows}). "
            "The work order keys all three report views by `(section_id, week_id)`."
        )
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Driving the validity service.
# ---------------------------------------------------------------------------


def validity_service() -> Any:
    """`app.services.validity`, imported where a test can fail on it rather than error."""
    try:
        return import_module(VALIDITY_SERVICE_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (
            absent == VALIDITY_SERVICE_MODULE or VALIDITY_SERVICE_MODULE.startswith(f"{absent}.")
        ):
            raise
        pytest.fail(
            f"`{VALIDITY_SERVICE_MODULE}` does not exist. E2-08 ships it under "
            "`backend/app/services/` as the one place a response's §3.3 validity is decided, and "
            "E4-03's `valid_responses` counts the column it maintains."
        )


def recompute_validity(session: Any, tables: dict[str, Any], response: Mapping[str, Any]) -> Any:
    """Re-decide one response's validity through the service that owns the column.

    **The column is never written by this suite**, which is E4-03's work order in
    as many words: a reclassification has to reach `valid_responses` through
    `response.is_valid` as the service maintains it, so a test that set the column
    itself would assert that the view can read a value the test put there
    (`docs/MISTAKES.md` entry 30).

    The parameters are bound by name because no record settles the signature — see
    `RECOMPUTE_FUNCTION` above. A parameter this cannot fill stops with a message
    naming it, which is an interface question for the ticket rather than a guess.
    """
    import inspect

    module = validity_service()
    function = getattr(module, RECOMPUTE_FUNCTION, None)
    if not callable(function):
        pytest.fail(
            f"`{VALIDITY_SERVICE_MODULE}` exposes no callable `{RECOMPUTE_FUNCTION}`; it exposes "
            f"{sorted(name for name in vars(module) if not name.startswith('_'))}. That name comes "
            "from `docs/tickets/e3/.attempts/E3-03.md`, which lists it as the function whose "
            "docstring E3-03 corrected, and E4-03's work order settles that `response.is_valid` is "
            "maintained from each comment's current verdict by this module. If the recompute is "
            "spelled some other way, this constant in tests/fixtures/report_views.py is the one "
            "line that changes."
        )

    key = single_primary_key(require_table(tables, RESPONSE_TABLE))
    available = {
        "response_id": response[key],
        "response": session.get(model_for(RESPONSE_TABLE), response[key]),
    }
    values: dict[str, Any] = {}
    for parameter in inspect.signature(function).parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if parameter.name in SESSION_PARAMETERS:
            values[parameter.name] = session
        elif parameter.name in RESPONSE_PARAMETERS:
            values[parameter.name] = available[parameter.name]
        elif parameter.default is parameter.empty:
            pytest.fail(
                f"`{RECOMPUTE_FUNCTION}` requires a parameter `{parameter.name}` this fixture has "
                f"nothing to fill from; it offers a session and {list(RESPONSE_PARAMETERS)}. "
                "E4-03's sixth criterion drives one response's validity through this function, so "
                "a third required input is an interface question for the ticket — "
                "`RESPONSE_PARAMETERS` in tests/fixtures/report_views.py is where a spelling is "
                "taught."
            )
    answered = function(**values)
    session.flush()
    return answered


# ---------------------------------------------------------------------------
# The world.
# ---------------------------------------------------------------------------


class ReportWorld:
    """One term, one or two sections, the question sets in force, and answered weeks.

    Everything is written through the seeding walker on the session the caller's
    fixture supplies, so a world built on `db_session` is rolled back with the
    test and one built on `committed_rows` is visible to a second connection and
    removed by that fixture's diff.
    """

    def __init__(self, calendar: Fall2026) -> None:
        self.calendar = calendar
        self.sections: dict[str, Any] = {}
        self.windows: dict[tuple[str, int], Any] = {}
        self.question_sets: dict[int, Any] = {}
        self.questions: dict[int, dict[int, Any]] = {}
        self.shape_of: dict[int, dict[int, str]] = {}
        self.stream_of: dict[int, dict[int, str | None]] = {}
        # One platform registration for every student this world seeds, invented
        # by the seeding walker and shared, so two students differ only in their
        # subject and their enrolments (`tests/fixtures/grading.py` shares one for
        # the same reason).
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

    def link(self, table_name: str, target: str) -> str:
        """The one column on `table_name` that names a `target` row by itself.

        Single-column, for the reason `tests/fixtures/grading.py` gives at length:
        E2-05 gives `response` composite consistency keys beside its plain ones, so
        "which column points at `section`?" has two correct answers and a rule
        counting foreign keys chooses neither.
        """
        found = single_column_link(require_table(self.tables, table_name), target)
        if found is None:
            pytest.fail(
                f"No single-column foreign key on `{table_name}` names a `{target}` row. This "
                "fixture addresses a parent row by one column; `tests/fixtures/grading.py`'s "
                "`link` carries the whole reasoning."
            )
        return found

    # -- building ------------------------------------------------------------

    def build(
        self,
        *,
        cohort: str = DEFAULT_COHORT,
        layout: Sequence[tuple[int, str, str | None]] = SPEC_QUESTION_LAYOUT,
    ) -> "ReportWorld":
        """Seed the term, its eighteen weeks, one section, and the question set in force."""
        self.calendar.build()
        self.section(cohort)
        self.plant_question_set(version=FIRST_VERSION, layout=layout)
        return self

    def section(self, cohort: str = DEFAULT_COHORT) -> Any:
        """One section of `cohort`, seeded once and reused. See `DEFAULT_COHORT`."""
        if cohort not in self.sections:
            self.sections[cohort] = self.calendar.section_row(cohort)
        return self.sections[cohort]

    def section_id(self, cohort: str = DEFAULT_COHORT) -> Any:
        return self.section(cohort)[self.key_of(SECTION_TABLE)]

    def week_id(self, term_week: int) -> Any:
        """The `week` row's key for one term week. The axis these views are keyed on."""
        return self.calendar.weeks[term_week][self.key_of(WEEK_TABLE)]

    def window(self, term_week: int, cohort: str = DEFAULT_COHORT) -> Any:
        """One `survey_window` for one section and term week, at the hand-written instants."""
        cached = self.windows.get((cohort, term_week))
        if cached is not None:
            return cached
        opens_at, closes_at = WINDOWS_BY_TERM_WEEK[term_week]
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

    def plant_question_set(
        self, *, version: int, layout: Sequence[tuple[int, str, str | None]]
    ) -> dict[int, Any]:
        """One `question_set` at `version` carrying `layout`'s questions.

        Each entry is `(position, shape, stream)`. The shape decides which value
        column an answer to it fills and is matched against whatever the schema
        enumerates by `tests/fixtures/submit.py`'s `shape_column`, so E2-05's
        spelling stays E2-05's; the stream is written outright, because E4-02
        settles both its column and its two values.
        """
        stream = self.require_stream_column()
        table = require_table(self.tables, QUESTION_TABLE)
        found = shape_column(table)
        shape_name, members = found if found is not None else (None, {})

        question_set = self.seed(QUESTION_SET_TABLE, {}, **{VERSION_COLUMN: version})
        self.question_sets[version] = question_set
        chain = {QUESTION_SET_TABLE: question_set}

        likert_minimum, likert_maximum, likert_step = LIKERT_BOUNDS
        workload_minimum, workload_maximum, workload_step = WORKLOAD_BOUNDS

        planted: dict[int, Any] = {}
        self.shape_of[version] = {}
        self.stream_of[version] = {}
        for position, shape, stream_value in layout:
            values: dict[str, Any] = {POSITION_COLUMN: position, stream: stream_value}
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
            planted[position] = self.seed(QUESTION_TABLE, chain, **values)
            self.shape_of[version][position] = shape
            self.stream_of[version][position] = stream_value
        self.questions[version] = planted
        return planted

    def require_stream_column(self) -> str:
        """`question.stream`, or a failure naming the ticket that ships it."""
        table = require_table(self.tables, QUESTION_TABLE)
        if STREAM_COLUMN not in table.c:
            pytest.fail(
                f"`{QUESTION_TABLE}` declares no `{STREAM_COLUMN}` (it declares "
                f"{[column.name for column in table.columns]}). E4-02 adds it — Text, "
                f"{INSTRUCTOR_STREAM!r} or {COURSE_STREAM!r} for a rating or a comment and NULL "
                "for the workload question, closed by a `CHECK` — and E4-03's rating distribution "
                "derives its stream from it rather than from a question's position, which is that "
                "ticket's seventh criterion. E4-03's migration takes the chain slot below E4-02's, "
                "so this branch is built with `e4/report-schema` merged in."
            )
        return STREAM_COLUMN

    # -- people ---------------------------------------------------------------

    def student(self, subject: str, *, cohorts: Sequence[str] = (DEFAULT_COHORT,)) -> Any:
        """One `user` enrolled in each of `cohorts`' sections, from each section's start date.

        The enrollment rows are seeded because a respondent who is enrolled
        nowhere is a world that does not occur, and read by nothing here: the
        enrolled denominator is E4-07's, and no view in this ticket names
        `enrollment` at all.
        """
        user = self.seed(USER_TABLE, self.people_chain, lms_user_id=subject)
        for cohort in cohorts:
            _length, _first_term_week, start = SEEDED_COHORTS[cohort]
            self.seed(
                ENROLLMENT_TABLE,
                {},
                **{
                    self.link(ENROLLMENT_TABLE, USER_TABLE): user[self.key_of(USER_TABLE)],
                    self.link(ENROLLMENT_TABLE, SECTION_TABLE): self.section_id(cohort),
                    STARTED_ON_COLUMN: start,
                    ENDED_ON_COLUMN: None,
                },
            )
        return user

    # -- what a student answered ----------------------------------------------

    def respond(
        self,
        student: Mapping[str, Any],
        *,
        term_week: int,
        answers: Mapping[int, Any],
        cohort: str = DEFAULT_COHORT,
        version: int = FIRST_VERSION,
        verdicts: Mapping[int, str] | None = None,
    ) -> tuple[Any, dict[int, Any]]:
        """One `response` for one student, section and term week, with the answers given.

        `answers` maps a question position to the value stored for it — a rating,
        a workload figure, or the text of a comment. **A position left out gets no
        `answer` row at all**, which is the faithful record of a question that was
        not answered: ADR 0115 deletes a withdrawn answer's row, and E2-05 refuses
        an `answer` holding no value, so an absent row is the only spelling this
        schema has for it.

        `verdicts` names the classification written for a comment position; a
        comment answered without one is classified `substantive`, so a caller
        spells only the verdict it is asking about.
        """
        verdicts = {} if verdicts is None else verdicts
        window = self.window(term_week, cohort)
        _opens_at, closes_at = WINDOWS_BY_TERM_WEEK[term_week]

        values: dict[str, Any] = {
            RESPONSE_USER_COLUMN: student[self.key_of(USER_TABLE)],
            RESPONSE_SECTION_COLUMN: self.section_id(cohort),
            RESPONSE_WEEK_COLUMN: self.week_id(term_week),
            RESPONSE_TERM_COLUMN: self.calendar.term[self.key_of(TERM_TABLE)],
        }
        if self.has_column(RESPONSE_TABLE, "submitted_at"):
            values["submitted_at"] = closes_at - SUBMITTED_BEFORE_CLOSE
        # Where `response` names the window or the set it belongs to, the row this
        # world already built is named rather than left to the seeding walker,
        # which would invent a *second* window under a week this section does not
        # have (`tests/fixtures/grading.py` carries the same note).
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

        written: dict[int, Any] = {}
        for position, value in sorted(answers.items()):
            written[position] = self.answer(response, position, value, version=version)
            if self.shape_of[version][position] == "comment":
                self.classify(
                    written[position],
                    verdicts.get(position, SUBSTANTIVE),
                    classified_at=closes_at - CLASSIFIED_BEFORE_CLOSE,
                )
        return response, written

    def answer(
        self,
        response: Mapping[str, Any],
        position: int,
        value: Any,
        *,
        version: int = FIRST_VERSION,
    ) -> Any:
        """One `answer` row, carrying the value column its question's shape uses."""
        shape = self.shape_of[version][position]
        column = {
            "rating": RATING_COLUMN,
            "comment": COMMENT_TEXT_COLUMN,
            "workload": WORKLOAD_HOURS_COLUMN,
        }[shape]
        return self.seed(
            ANSWER_TABLE,
            {},
            **{
                self.link(ANSWER_TABLE, RESPONSE_TABLE): response[self.key_of(RESPONSE_TABLE)],
                self.link(ANSWER_TABLE, QUESTION_TABLE): self.questions[version][position][
                    self.key_of(QUESTION_TABLE)
                ],
                column: value,
            },
        )

    def classify(self, answer: Mapping[str, Any], verdict: str, *, classified_at: Any) -> Any:
        """Append one `classification` row for one comment answer.

        Append, always: ADR 0055 makes the table append-only, so a later verdict is
        a **new row** rather than an edit — which is the shape E4-03's sixth
        criterion requires ("asserted by adding a classification row, never editing
        one").
        """
        return self.seed(
            CLASSIFICATION_TABLE,
            {},
            **{
                ANSWER_ID_COLUMN: answer[self.key_of(ANSWER_TABLE)],
                CLASSIFICATION_TASK_COLUMN: COMMENT_VALIDITY_TASK,
                CLASSIFICATION_VERDICT_COLUMN: verdict,
                CLASSIFIED_AT_COLUMN: classified_at,
            },
        )

    def closes_at(self, term_week: int) -> Any:
        """When one term week's window closes, from the hand-written calendar."""
        return WINDOWS_BY_TERM_WEEK[term_week][1]

    # -- reading back ----------------------------------------------------------

    def recompute(self, response: Mapping[str, Any]) -> Any:
        """`recompute_validity` on this world's session. See that function."""
        self.session.flush()
        return recompute_validity(self.session, self.tables, response)

    def stored_validity(self, response: Mapping[str, Any]) -> Any:
        """`response.is_valid` as the database holds it now, read back through Core.

        A premise rather than a subject: the tests here assert what the *view*
        counts, and this is how they say first that the service moved the column at
        all — so a recompute that did nothing is a red naming the service instead
        of a red naming the view.
        """
        from sqlalchemy import select

        table = require_table(self.tables, RESPONSE_TABLE)
        key = self.key_of(RESPONSE_TABLE)
        if RESPONSE_IS_VALID_COLUMN not in table.c:
            pytest.fail(
                f"`{RESPONSE_TABLE}` declares no `{RESPONSE_IS_VALID_COLUMN}` (it declares "
                f"{[column.name for column in table.columns]}). E2-08 adds it as §3.3's verdict "
                "about a submission as a whole, and E4-03's `valid_responses` counts it."
            )
        self.session.flush()
        statement = select(table.c[RESPONSE_IS_VALID_COLUMN]).where(table.c[key] == response[key])
        return self.session.execute(statement).scalar_one()

    def rows(self, view: str, *, cohort: str = DEFAULT_COHORT, term_week: int | None = None) -> Any:
        """Every row `view` holds for this world's section, flushed first."""
        self.session.flush()
        return report_rows(
            self.session,
            view,
            section_id=self.section_id(cohort),
            week_id=None if term_week is None else self.week_id(term_week),
        )

    def distribution(
        self, *, cohort: str = DEFAULT_COHORT, term_week: int | None = None
    ) -> list[tuple[str, Decimal, int]]:
        """The distribution rows for this world's section, as sorted triples."""
        self.session.flush()
        return distribution_rows(
            self.session,
            section_id=self.section_id(cohort),
            week_id=None if term_week is None else self.week_id(term_week),
        )

    def workload(self, *, term_week: int, cohort: str = DEFAULT_COHORT) -> dict[str, Any] | None:
        self.session.flush()
        return workload_row(
            self.session, section_id=self.section_id(cohort), week_id=self.week_id(term_week)
        )

    def counts(self, *, term_week: int, cohort: str = DEFAULT_COHORT) -> dict[str, Any] | None:
        self.session.flush()
        return response_counts_row(
            self.session, section_id=self.section_id(cohort), week_id=self.week_id(term_week)
        )


@pytest.fixture
def report_world(fall_2026: Fall2026) -> ReportWorld:
    """The world E4-03's views are measured over, **unbuilt**.

    Unbuilt for `docs/MISTAKES.md` entry 30's reason and for entry 44's: which
    question set is in force is what the stream-mapping criterion is about, and
    every guard this world raises — a missing view, a missing `question.stream` —
    has to fire inside a test body so that the red is a failure rather than an
    error in setup.
    """
    return ReportWorld(fall_2026)


@pytest.fixture
def committed_report_world(committed_rows: Any, metadata_tables: dict[str, Any]) -> ReportWorld:
    """The same world, committed, so a second connection can read it.

    The application role connects for itself (ADR 0001: the pool is bound to the
    service), so a test that reads a report view **as `pulse_app`** over real rows
    needs them committed or it is reading an empty view and calling it a pass.
    `committed_rows` removes whatever appeared when the test ends.

    **The session states its environment**, exactly as `db_session` does and for
    the same reason: Batch C's registration-address rules judge a session that
    states nothing as a deployment, and the seeding walker's invented
    `lti_platform` row — the ancestor every `user` needs — carries a development
    stack's cleartext address. Without the stamp this world fails inside its own
    seeding (`docs/MISTAKES.md` entry 13's closing sentence).
    """
    committed_rows.session.info["environment"] = DEVELOPMENT
    return ReportWorld(Fall2026(committed_rows.seed, committed_rows.session, metadata_tables))
