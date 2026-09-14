"""E5-03 — the cohorts the benchmark views aggregate, and how a test reads one.

Seven test modules need the same things: sections that differ in exactly one of
length, level, start cohort and term; students who answered the values the test
chose; and one way of reading a row out of one of four views or out of one of
two functions. A copy of any of them in each module is `docs/MISTAKES.md` entry
13, so they all live here.

**What this file decides, and what it refuses to.** Every view name, every
column list and both function signatures below are transcribed from the ruling
on `docs/disputes/E5-03-01.md`, quoted on the constants that carry them. That
ruling exists because they were settled nowhere: the ticket asks for a column
list asserted "against an expected set" and named no columns, and a test author
who filled that gap would have made the design decision under cover of writing
a test. Everything else here is E0-05's containment tables, E0-06's term and
week rows, E2-05's survey tables, E2-06's calendar and E4-02's `question.stream`
— named by the records that built them.

**Nothing here computes a figure a test reads back.** No mean, no median, no
count and no cohort key is derived in this file; every number a test asserts is
arithmetic that test writes out by hand over values it supplied
(`docs/MISTAKES.md` entries 19 and 30). The one derivation this file does make
is which `week` row a response hangs on — `first_term_week + course_week - 1` —
and it is not the value under test: it comes from the start-letter map
transcribed in `tests/fixtures/survey_windows.py`, while the views derive a
course week from the section's stored `start_date` against the term's calendar.
Two independent routes to the same fact, and
`test_the_benchmark_calendar_literals_are_the_seeded_start_letter_map` is the
control that keeps the transcription honest.

**Nothing raises from a fixture.** `benchmark_world` hands back an *unbuilt*
world, and every guard — the view is absent, the function is absent, a column
the suite reads is missing — is a `pytest.fail` reached from a test body
through `require_benchmark_view` or `require_benchmark_function`. On a tree
where E5-03 is unbuilt each module is therefore a **failed** test naming the
missing deliverable rather than an error in somebody's setup, which is
`docs/MISTAKES.md` entry 44's rule and the difference between a red suite and a
broken one.

**The clock is never read.** These views are aggregates over stored rows: they
take no `now`, so no test here moves the development clock and no answer
depends on the date CI runs on. Window rows are seeded because `response` may
reference one, not because anything reads their instants — the same standing
E4-03's fixture has, and the reason ADR 0142's hazard does not arise. A view
that filtered to "the current term" would have to read a clock, and
`test_a_prior_term_section_has_its_own_row_at_the_same_course_week` is where
that shows up.

**Two terms, which is why this world is not `ReportWorld`.** That class binds
every response to the one term its `Fall2026` calendar built, and criterion 5
is about a cohort reaching into a prior one. So the term, the week rows and the
response live here, and the pieces that are term-agnostic — the question set,
an `answer` row, a `user` — are delegated to the `ReportWorld` this wraps
rather than copied (`docs/MISTAKES.md` entry 13).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from typing import Any

import pytest
from sqlalchemy import text

from fixtures.clock import DEVELOPMENT
from fixtures.grading import (
    ENDED_ON_COLUMN,
    ENROLLMENT_TABLE,
    RESPONSE_SECTION_COLUMN,
    RESPONSE_TERM_COLUMN,
    RESPONSE_USER_COLUMN,
    RESPONSE_WEEK_COLUMN,
    STARTED_ON_COLUMN,
    single_column_link,
)
from fixtures.report_views import (
    COURSE_STREAM,
    FIRST_VERSION,
    INSTRUCTOR_STREAM,
    SPEC_QUESTION_LAYOUT,
    SUBMITTED_BEFORE_CLOSE,
    ReportWorld,
)
from fixtures.submit import (
    QUESTION_SET_TABLE,
    RESPONSE_TABLE,
    USER_TABLE,
)
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import (
    COHORT_SECTION_MODALITY,
    COHORT_SECTION_ORDINAL,
    SECTION_CODE_COLUMN,
    SECTION_END_COLUMN,
    SECTION_LENGTH_COLUMN,
    SECTION_START_COLUMN,
    SECTION_TABLE,
    SEEDED_COHORTS,
    SURVEY_WINDOW_TABLE,
    TERM_TABLE,
    WEEK_NUMBER_COLUMN,
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
# The four views and the two functions, as the ruling on E5-03-01 settles them.
# ---------------------------------------------------------------------------

# The object names follow the file names the ruling spells, through
# [ADR 0041](../../docs/adr/0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md),
# which puts a view's SQL in `backend/app/views_sql/<object>_v<NNN>.sql`. That is
# the one rule in this repository mapping a file to a relation, and it is how
# `report_workload_v001.sql` names `report_workload`.
COHORT_RATING_WEEK_VIEW = "benchmark_cohort_rating_week"
COHORT_WEEK_VIEW = "benchmark_cohort_week"
COHORT_RATING_TERM_AXIS_VIEW = "benchmark_cohort_rating_term_axis"
COHORT_TERM_AXIS_VIEW = "benchmark_cohort_term_axis"

# What each view returns, and the whole of it. Quoted from the ruling: "Views,
# column lists as equality sets, in this order; `stream` is a key column, one row
# per stream, the `report_rating_distribution_v001` shape".
#
# **These are equalities rather than floors**, which is criterion 1 in as many
# words: "a test asserts each view's column list against an expected set". Every
# column one of these views returns is a column an instructor's connection may
# read, and a column that arrives without a decision is the failure §4.1 exists
# to prevent. The order is the ruling's and is recorded because the ruling gave
# one; the assertion compares sets, because nothing here promises an order to a
# payload that reads by name.
BENCHMARK_VIEWS: dict[str, tuple[str, ...]] = {
    COHORT_RATING_WEEK_VIEW: (
        "length_weeks",
        "level",
        "term_id",
        "course_week",
        "stream",
        "rating_mean",
        "rating_count",
    ),
    COHORT_WEEK_VIEW: (
        "length_weeks",
        "level",
        "term_id",
        "course_week",
        "workload_mean",
        "workload_median",
        "response_count",
        "respondent_count",
        "section_count",
    ),
    COHORT_RATING_TERM_AXIS_VIEW: (
        "length_weeks",
        "level",
        "term_id",
        "section_start_date",
        "term_week",
        "stream",
        "rating_mean",
        "rating_count",
    ),
    COHORT_TERM_AXIS_VIEW: (
        "length_weeks",
        "level",
        "term_id",
        "section_start_date",
        "term_week",
        "workload_mean",
        "workload_median",
        "response_count",
        "respondent_count",
        "section_count",
    ),
}

# The course-week pair and the term-axis pair, for the tests that make the same
# assertion of both axes. Named rather than derived from the dict above, because
# a rule stated over "the views whose name contains term_axis" would follow a
# rename into saying nothing.
COURSE_WEEK_VIEWS = (COHORT_RATING_WEEK_VIEW, COHORT_WEEK_VIEW)
TERM_AXIS_VIEWS = (COHORT_RATING_TERM_AXIS_VIEW, COHORT_TERM_AXIS_VIEW)
RATING_VIEWS = (COHORT_RATING_WEEK_VIEW, COHORT_RATING_TERM_AXIS_VIEW)
WORKLOAD_VIEWS = (COHORT_WEEK_VIEW, COHORT_TERM_AXIS_VIEW)

# The two `SECURITY DEFINER` functions the ruling puts in place of the withdrawn
# person-keyed view, quoted: "`benchmark_set_rating_week_v001.sql` defining
# `benchmark_set_rating_week(section_ids uuid[])` returning rows `(course_week,
# stream, rating_mean, rating_count)`" and "`benchmark_set_week_v001.sql`
# defining `benchmark_set_week(section_ids uuid[])` returning rows
# `(course_week, workload_mean, workload_median, response_count,
# respondent_count, section_count)`".
SET_RATING_FUNCTION = "benchmark_set_rating_week"
SET_FUNCTION = "benchmark_set_week"

BENCHMARK_FUNCTIONS: dict[str, tuple[str, ...]] = {
    SET_RATING_FUNCTION: ("course_week", "stream", "rating_mean", "rating_count"),
    SET_FUNCTION: (
        "course_week",
        "workload_mean",
        "workload_median",
        "response_count",
        "respondent_count",
        "section_count",
    ),
}

# The argument, spelled by the ruling: one `uuid[]`, named `section_ids`.
SET_FUNCTION_ARGUMENT = "section_ids"
SET_FUNCTION_ARGUMENT_TYPE = "uuid[]"

# The typed wrappers, which the ruling puts in `views_sql/queries.py` under "the
# same two names". The module is the one the org-views sweep already excuses as
# the place statements live (`tests/unit/test_the_org_views_are_read_only_
# through_the_grant.py` names it).
QUERY_MODULE = "app.views_sql.queries"

# How the wrapper is handed its two inputs. **Bound by name, because no record
# settles the signature** — the ruling names the functions and their SQL
# arguments and stops there. This is the device `tests/fixtures/report_views.py`
# uses for `recompute_response_validity` and for the same reason: an interface a
# ruling leaves open is a question for the ticket, and a guess written into a
# fixture answers it silently.
WRAPPER_SESSION_PARAMETERS = ("session", "db", "db_session", "connection")
WRAPPER_SECTION_PARAMETERS = ("section_ids", "sections", "section_id_list", "ids")

# ---------------------------------------------------------------------------
# SPEC §8's level bands, as course numbers. `course.level` is a stored generated
# column (ADR 0015) derived from `lms_number`, so a section's level is planted by
# choosing its course's number and never by writing a level.
# ---------------------------------------------------------------------------

UG = "UG"
UGGR = "UGGR"
GR = "GR"

# One number per level, inside SPEC §8's bands: `100`-`499` is `UG`, `500`-`599`
# is `UGGR`, `600`-`799` is `GR`. Three-digit and unpadded, so none of them is
# the leading-zero case `tests/fixtures/supervision.py` leaves to E0-05's own
# tests. Each course this world plants gets a fresh `prefix`, so the same number
# under two courses does not meet `uq_course_prefix_id_lms_number`.
COURSE_NUMBER_FOR_LEVEL = {UG: "210", UGGR: "540", GR: "640"}

COURSE_NUMBER_COLUMN = "lms_number"
COURSE_TABLE = "course"
DEPARTMENT_TABLE = "department"
CONTAINMENT_SPINE = ("institution", "college", DEPARTMENT_TABLE)

# ---------------------------------------------------------------------------
# The two terms.
# ---------------------------------------------------------------------------

CURRENT_TERM = "current"
PRIOR_TERM = "prior"

# The prior term, written out by hand exactly as `tests/fixtures/survey_windows.py`
# writes Fall 2026 — literals rather than arithmetic, for that file's reason.
# 2026-01-12 is a Monday, eighteen weeks run to 2026-05-17 inclusive (ADR 0020),
# and the whole of it that this suite uses sits before daylight time begins on
# 2026-03-08, so every instant below is UTC-5 at both ends.
PRIOR_TERM_START = date(2026, 1, 12)
PRIOR_TERM_END = date(2026, 5, 17)
PRIOR_TERM_WEEKS = 18

# SPEC §3.1's rhythm over the prior term's first six weeks, in UTC, by hand. Term
# week M's Monday is `2026-01-12 + (M - 1) x 7 days`; the window opens on that
# Monday's Friday at 18:00 and closes on its Sunday at 23:59:59, both in
# `America/New_York`, both stored as aware UTC (ADR 0019).
#
# Six rows rather than eighteen because six is what this suite seeds into, and a
# literal nothing reads is a literal nobody checks. The control
# `test_the_prior_term_window_literals_are_spec_3_1s_rhythm` reads each one back
# into the institution's zone and requires the Friday and the Sunday, so these
# are checked rather than trusted.
PRIOR_WINDOWS_BY_TERM_WEEK: dict[int, tuple[datetime, datetime]] = {
    1: (datetime(2026, 1, 16, 23, 0, 0, tzinfo=UTC), datetime(2026, 1, 19, 4, 59, 59, tzinfo=UTC)),
    2: (datetime(2026, 1, 23, 23, 0, 0, tzinfo=UTC), datetime(2026, 1, 26, 4, 59, 59, tzinfo=UTC)),
    3: (datetime(2026, 1, 30, 23, 0, 0, tzinfo=UTC), datetime(2026, 2, 2, 4, 59, 59, tzinfo=UTC)),
    4: (datetime(2026, 2, 6, 23, 0, 0, tzinfo=UTC), datetime(2026, 2, 9, 4, 59, 59, tzinfo=UTC)),
    5: (datetime(2026, 2, 13, 23, 0, 0, tzinfo=UTC), datetime(2026, 2, 16, 4, 59, 59, tzinfo=UTC)),
    6: (datetime(2026, 2, 20, 23, 0, 0, tzinfo=UTC), datetime(2026, 2, 23, 4, 59, 59, tzinfo=UTC)),
}

# The prior term's start-letter map, in the same `(length, first term week, start
# date)` shape as `SEEDED_COHORTS`. Two letters, because two is what the prior
# term is used for: a 12-week and a 6-week cohort, both starting in its first
# week, so a prior-term row differs from a current-term one in the term and in
# nothing else. The start dates are the prior term's own week-1 Monday, which the
# control asserts.
PRIOR_TERM_COHORTS: dict[str, tuple[int, int, date]] = {
    "U": (12, 1, PRIOR_TERM_START),
    "E": (6, 1, PRIOR_TERM_START),
}

COHORTS_BY_TERM = {CURRENT_TERM: SEEDED_COHORTS, PRIOR_TERM: PRIOR_TERM_COHORTS}
WINDOWS_BY_TERM = {CURRENT_TERM: WINDOWS_BY_TERM_WEEK, PRIOR_TERM: PRIOR_WINDOWS_BY_TERM_WEEK}

# ---------------------------------------------------------------------------
# SPEC §3.2's question positions, as `SPEC_QUESTION_LAYOUT` orders them.
# ---------------------------------------------------------------------------

INSTRUCTOR_RATING_POSITION = 1
COURSE_RATING_POSITION = 3
WORKLOAD_POSITION = 5

# ---------------------------------------------------------------------------
# Reading a view, a function, and the catalog.
# ---------------------------------------------------------------------------

# Every column of one relation in `public`, from `pg_catalog` rather than from
# `information_schema`. The difference matters for one caller: the information
# schema shows a role only the relations it holds a privilege on, so a column
# list read there as `pulse_app` comes back empty for a view nobody granted —
# a missing grant reported as a missing view. Copied in shape from
# `tests/fixtures/report_views.py`, whose docstring carries the measurement.
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

# One function in `public` by name, with what a caller and a security review both
# need to know about it: whether it is `SECURITY DEFINER`, what it takes and what
# it answers.
FUNCTION_SHAPE = """
    SELECT p.oid::regprocedure::text AS signature,
           p.prosecdef AS security_definer,
           pg_get_userbyid(p.proowner) AS owner,
           coalesce(p.proargnames, ARRAY[]::text[]) AS argument_names,
           array(
               SELECT format_type(a.argtype, NULL)
               FROM unnest(p.proargtypes::oid[]) WITH ORDINALITY AS a(argtype, idx)
               ORDER BY a.idx
           ) AS argument_types
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = :name
    ORDER BY 1
"""


def benchmark_view_columns(connection: Any, view: str) -> tuple[str, ...]:
    """Every column `public.<view>` returns, in order, or an empty tuple if it is absent."""
    rows = connection.execute(text(RELATION_COLUMNS), {"relation": view})
    return tuple(str(row[0]) for row in rows)


def require_benchmark_view(connection: Any, view: str) -> tuple[str, ...]:
    """`view`'s columns, or a failure naming the deliverable that is missing.

    Called as the first statement of a test body rather than from a fixture, so
    that on a tree where E5-03 is unbuilt these modules are **failed** tests
    naming the view rather than errors raised inside somebody's setup
    (`docs/MISTAKES.md` entry 44). The second half — the columns this suite
    reads — is checked here too, because a `SELECT` naming a column the view
    does not have raises `UndefinedColumn` from the driver, which is the same
    broken red in a different coat.
    """
    expected = BENCHMARK_VIEWS[view]
    present = benchmark_view_columns(connection, view)
    if not present:
        pytest.fail(
            f"There is no view `public.{view}` in the migrated database. E5-03 ships it from "
            f"`backend/app/views_sql/{view}_v001.sql`, executed by that ticket's migration the way "
            "the report views are executed (ADR 0041: the SQL lives in a versioned file and the "
            "revision runs it by name). The ruling on `docs/disputes/E5-03-01.md` settles its rows "
            f"as {list(expected)}."
        )
    missing = [column for column in expected if column not in present]
    if missing:
        pytest.fail(
            f"`public.{view}` does not return {missing}; it returns {list(present)}. The ruling on "
            f"`docs/disputes/E5-03-01.md` settles this view's rows as {list(expected)}, and every "
            "test in this suite reads them by those names."
        )
    return present


def function_shape(connection: Any, name: str) -> list[dict[str, Any]]:
    """Every function called `name` in `public`, as the catalog describes it."""
    return [
        dict(row) for row in connection.execute(text(FUNCTION_SHAPE), {"name": name}).mappings()
    ]


def require_benchmark_function(connection: Any, name: str) -> dict[str, Any]:
    """One benchmark set function, or a failure naming the file that should define it.

    In a test body, never a fixture, for `require_benchmark_view`'s reason. The
    argument list is checked here as well as the name, because a function of the
    right name taking something other than one `uuid[]` fails the call with
    `UndefinedFunction`, which reads as "the function is missing" and is not.
    """
    found = function_shape(connection, name)
    if not found:
        signature = f"{name}({SET_FUNCTION_ARGUMENT} {SET_FUNCTION_ARGUMENT_TYPE})"
        pytest.fail(
            f"There is no function `public.{name}` in the migrated database. The ruling on "
            f"`docs/disputes/E5-03-01.md` puts it in `backend/app/views_sql/{name}_v001.sql` as a "
            f"`SECURITY DEFINER` function `{signature}` "
            f"returning rows {list(BENCHMARK_FUNCTIONS[name])}, executed by this ticket's "
            "migration. It replaces the person-keyed view the work order asked for, which that "
            "dispute withdrew: the section set goes in, numbers come out, and no row keyed to a "
            "student is ever selectable by the application role."
        )
    if len(found) > 1:
        pytest.fail(
            f"`public.{name}` is overloaded — the catalog holds "
            f"{[row['signature'] for row in found]}. The ruling settles one signature, and a "
            "second overload is a second implementation for `SANCTIONED_APPLICATION_EXECUTE` to "
            "admit and for a caller to pick between by accident."
        )
    shape = found[0]
    types = [str(value) for value in shape["argument_types"]]
    if types != [SET_FUNCTION_ARGUMENT_TYPE]:
        pytest.fail(
            f"`public.{name}` takes {types}; the ruling settles it as one "
            f"`{SET_FUNCTION_ARGUMENT_TYPE}` called `{SET_FUNCTION_ARGUMENT}`. Its signature is "
            f"{shape['signature']}."
        )
    return shape


def benchmark_rows(connection: Any, view: str, **filters: Any) -> list[dict[str, Any]]:
    """Every row `view` holds, narrowed by whichever key columns the caller named.

    The column list is the contract constant rather than `SELECT *`, so a view
    that grew a column is caught by the column-list test with a message about
    the widening instead of appearing quietly in every other assertion here.
    A filter naming a column the view does not have is a failure here rather
    than an `UndefinedColumn` from the driver.
    """
    require_benchmark_view(connection, view)
    contract = BENCHMARK_VIEWS[view]
    unknown = sorted(name for name in filters if name not in contract)
    if unknown:
        pytest.fail(
            f"This suite asked `{view}` for rows narrowed by {unknown}, which it does not return; "
            f"it returns {list(contract)}."
        )
    selected = ", ".join(contract)
    clauses = " AND ".join(f"{name} = :{name}" for name in sorted(filters))
    where = f" WHERE {clauses}" if clauses else ""
    # The relation and every column name are module constants, never a caller's
    # string; the values are bound.
    statement = text(f"SELECT {selected} FROM public.{view}{where}")  # noqa: S608
    return [dict(row) for row in connection.execute(statement, filters).mappings()]


def one_benchmark_row(connection: Any, view: str, **filters: Any) -> dict[str, Any] | None:
    """The single row `view` holds for one whole key, or `None`.

    More than one row for one key is a failure of the view's own grouping, so it
    is reported here rather than being silently indexed away — the shape a
    `GROUP BY` missing a column produces, and the shape that makes a mean look
    right because only the first of two rows was ever read.
    """
    rows = benchmark_rows(connection, view, **filters)
    if len(rows) > 1:
        pytest.fail(
            f"`{view}` returned {len(rows)} rows for one key ({filters}): {rows}. The ruling on "
            f"`docs/disputes/E5-03-01.md` settles this view as {list(BENCHMARK_VIEWS[view])}, "
            "whose key columns the caller has just named in full, so a second row for one key is "
            "a grouping defect rather than a value this suite can read."
        )
    return rows[0] if rows else None


def set_function_rows(
    connection: Any, name: str, section_ids: Sequence[Any]
) -> list[dict[str, Any]]:
    """Every row one benchmark set function answers for a section set.

    The ids are bound as text and cast, rather than interpolated: the function
    takes `uuid[]`, and an array of literals spliced into the statement would be
    a caller's string reaching the SQL. The empty set is deliberately *not*
    routed through here — `EMPTY_SET_CALL` below is a separate statement,
    because an empty Python list gives the driver no element type to infer and
    the resulting error would look like a defect in the function.
    """
    require_benchmark_function(connection, name)
    selected = ", ".join(BENCHMARK_FUNCTIONS[name])
    statement = text(
        f"SELECT {selected} FROM public.{name}(CAST(:ids AS uuid[]))"  # noqa: S608
    )
    parameters = {"ids": [str(value) for value in section_ids]}
    return [dict(row) for row in connection.execute(statement, parameters).mappings()]


def empty_set_call(name: str) -> Any:
    """The same call over an empty section set, with the array written as a literal."""
    selected = ", ".join(BENCHMARK_FUNCTIONS[name])
    return text(f"SELECT {selected} FROM public.{name}(ARRAY[]::uuid[])")  # noqa: S608


def query_module() -> Any:
    """`app.views_sql.queries`, imported where a test can fail on it rather than error."""
    try:
        return import_module(QUERY_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (
            absent == QUERY_MODULE or QUERY_MODULE.startswith(f"{absent}.")
        ):
            raise
        pytest.fail(
            f"`{QUERY_MODULE}` does not exist. It is the module the org-views sweep already "
            "excuses as the place read statements live, and the ruling on "
            "`docs/disputes/E5-03-01.md` puts this ticket's two typed wrappers there under the "
            f"same names as the SQL functions: `{SET_RATING_FUNCTION}` and `{SET_FUNCTION}`."
        )


def query_wrapper(name: str) -> Any:
    """One typed wrapper off that module, or a failure saying it is missing."""
    module = query_module()
    found = getattr(module, name, None)
    if not callable(found):
        defined = sorted(entry for entry in vars(module) if not entry.startswith("_"))
        pytest.fail(
            f"`{QUERY_MODULE}` exposes no callable `{name}`; it exposes {defined}. The ruling on "
            "`docs/disputes/E5-03-01.md` settles that the typed wrappers carry the same two names "
            "as the SQL functions, so this is a missing deliverable rather than a rename to "
            "accommodate here. If it is genuinely spelled some other way, the constant in "
            "tests/fixtures/benchmark_views.py is the one line that changes."
        )
    return found


def call_wrapper(name: str, session: Any, section_ids: Sequence[Any]) -> Any:
    """Call one typed wrapper, binding its parameters by name.

    **Bound by name because the ruling settles the wrapper's name and not its
    signature**, which is the same standing `recompute_validity` has in
    `tests/fixtures/report_views.py`. A required parameter this cannot fill
    stops with a message naming it — an interface question for the ticket rather
    than a guess written into a fixture.
    """
    import inspect

    wrapper = query_wrapper(name)
    available = {
        **{parameter: session for parameter in WRAPPER_SESSION_PARAMETERS},
        **{parameter: list(section_ids) for parameter in WRAPPER_SECTION_PARAMETERS},
    }
    values: dict[str, Any] = {}
    for parameter in inspect.signature(wrapper).parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if parameter.name in available:
            values[parameter.name] = available[parameter.name]
        elif parameter.default is parameter.empty:
            pytest.fail(
                f"`{name}` requires a parameter `{parameter.name}` this fixture has nothing to "
                f"fill from; it offers a session under {list(WRAPPER_SESSION_PARAMETERS)} and a "
                f"section-id sequence under {list(WRAPPER_SECTION_PARAMETERS)}. A third required "
                "input is an interface question for the ticket — `WRAPPER_SECTION_PARAMETERS` in "
                "tests/fixtures/benchmark_views.py is where a spelling is taught."
            )
    return wrapper(**values)


# ---------------------------------------------------------------------------
# The world.
# ---------------------------------------------------------------------------


@dataclass
class PlantedSection:
    """One seeded section and the four facts a test plants it for."""

    label: str
    row: Mapping[str, Any]
    term: str
    cohort: str
    level: str
    length_weeks: int
    first_term_week: int
    start_date: date
    windows: dict[int, Any] = field(default_factory=dict)


class BenchmarkWorld:
    """Two terms, sections that differ in one thing at a time, and what students answered.

    Every row is written through the seeding walker on the session the caller's
    fixture supplies, so a world built on `db_session` is rolled back with the
    test and one built on `committed_rows` is visible to a second connection and
    removed by that fixture's diff.
    """

    def __init__(self, report: ReportWorld) -> None:
        self.report = report
        self.sections: dict[str, PlantedSection] = {}
        self.terms: dict[str, Any] = {}
        self.weeks: dict[str, dict[int, Any]] = {CURRENT_TERM: {}, PRIOR_TERM: {}}
        self._spine: dict[str, Any] = {}

    # -- the session and the tables -----------------------------------------

    @property
    def calendar(self) -> Fall2026:
        return self.report.calendar

    @property
    def session(self) -> Any:
        return self.report.session

    @property
    def tables(self) -> dict[str, Any]:
        return self.report.tables

    def seed(self, table_name: str, chain: dict[str, Any] | None = None, **values: Any) -> Any:
        return self.report.seed(table_name, chain, **values)

    def key_of(self, table_name: str) -> str:
        return single_primary_key(require_table(self.tables, table_name))

    # -- building ------------------------------------------------------------

    def build(self) -> "BenchmarkWorld":
        """Seed the current term, its eighteen weeks, and the question set in force.

        **Everything this world remembers is reset on every call**, which is the
        same rule `Fall2026.build` states and it matters for the same caller: a
        Hypothesis property runs its body once per example inside a savepoint
        that is rolled back afterwards, so a section, a spine or a platform
        registration carried over from the previous example holds primary keys
        of rows that no longer exist — and the next row seeded against them is
        refused by a foreign key inside the fixture, which is
        `docs/MISTAKES.md` entry 13's closing sentence. Resetting is also what
        makes each example an independent world rather than twenty sections
        accumulating in one.
        """
        self.sections = {}
        self.terms = {}
        self.weeks = {CURRENT_TERM: {}, PRIOR_TERM: {}}
        self._spine = {}
        self.report.people_chain.clear()

        self.calendar.build()
        self.terms[CURRENT_TERM] = self.calendar.term
        self.weeks[CURRENT_TERM] = dict(self.calendar.weeks)
        self.report.plant_question_set(version=FIRST_VERSION, layout=SPEC_QUESTION_LAYOUT)
        return self

    def build_prior_term(self) -> "BenchmarkWorld":
        """Seed a second, earlier term with its own eighteen weeks.

        Its own `week` rows, because a course week is derived against the term a
        section belongs to and a prior-term section hanging on this term's weeks
        would be a world that cannot occur. The dates are the literals at the top
        of this file.
        """
        chain: dict[str, Any] = {}
        self.terms[PRIOR_TERM] = self.seed(
            TERM_TABLE,
            chain,
            **{
                "length_weeks": PRIOR_TERM_WEEKS,
                "start_date": PRIOR_TERM_START,
                "end_date": PRIOR_TERM_END,
            },
        )
        for number in range(1, PRIOR_TERM_WEEKS + 1):
            self.weeks[PRIOR_TERM][number] = self.seed(
                WEEK_TABLE, chain, **{WEEK_NUMBER_COLUMN: number}
            )
        return self

    def spine(self) -> dict[str, Any]:
        """A containment chain down to a department, seeded once and shared.

        Shared down to the department and no further, which is exactly what the
        level cases need: each course below it gets a fresh `prefix`, so two
        courses may carry the same `lms_number` without meeting
        `uq_course_prefix_id_lms_number`, and the institution row is seeded once
        because SPEC §8 permits at most one.
        """
        if not self._spine:
            chain: dict[str, Any] = {}
            self.seed(DEPARTMENT_TABLE, chain)
            self._spine = {name: chain[name] for name in CONTAINMENT_SPINE if name in chain}
        return dict(self._spine)

    def term_row(self, term: str = CURRENT_TERM) -> Any:
        row = self.terms.get(term)
        if row is None:
            pytest.fail(
                f"This world has no {term} term. `build()` seeds the current one and "
                "`build_prior_term()` the earlier one; a test that reads across terms calls both."
            )
        return row

    def term_id(self, term: str = CURRENT_TERM) -> Any:
        return self.term_row(term)[self.key_of(TERM_TABLE)]

    def week_id(self, term_week: int, term: str = CURRENT_TERM) -> Any:
        weeks = self.weeks[term]
        if term_week not in weeks:
            pytest.fail(
                f"The {term} term has no week {term_week}; it has {sorted(weeks)}. A response is "
                "hung on a `week` row, so a course week outside the term's calendar is a world "
                "this fixture will not build rather than a row the view should ignore."
            )
        return weeks[term_week][self.key_of(WEEK_TABLE)]

    def plant_section(
        self, label: str, *, cohort: str, level: str, term: str = CURRENT_TERM
    ) -> PlantedSection:
        """One section of `cohort`, under a course of `level`, in `term`.

        The section's calendar is written here and derived by nothing: its
        length and start date come from the start-letter map for its term, and
        `end_date` is `start + length x 7 - 1` days, ADR 0020's inclusive
        convention. They are *inputs* to the derivation under test and never its
        output (`docs/MISTAKES.md` entry 30).

        The level is planted by choosing the course's number, never by writing a
        level: `course.level` is a stored generated column (ADR 0015), so a test
        that wrote one would be asserting against a value it supplied.
        """
        if label in self.sections:
            pytest.fail(f"This world already holds a section labelled {label!r}.")
        cohorts = COHORTS_BY_TERM[term]
        if cohort not in cohorts:
            pytest.fail(
                f"The {term} term's start-letter map has no cohort {cohort!r}; it has "
                f"{sorted(cohorts)}."
            )
        length_weeks, first_term_week, start = cohorts[cohort]

        chain = self.spine()
        self.seed(COURSE_TABLE, chain, **{COURSE_NUMBER_COLUMN: COURSE_NUMBER_FOR_LEVEL[level]})
        chain[TERM_TABLE] = self.term_row(term)
        row = self.seed(
            SECTION_TABLE,
            chain,
            **{
                SECTION_CODE_COLUMN: f"{cohort}{COHORT_SECTION_ORDINAL}{COHORT_SECTION_MODALITY}",
                SECTION_LENGTH_COLUMN: length_weeks,
                SECTION_START_COLUMN: start,
                SECTION_END_COLUMN: start + timedelta(days=length_weeks * 7 - 1),
            },
        )
        planted = PlantedSection(
            label=label,
            row=row,
            term=term,
            cohort=cohort,
            level=level,
            length_weeks=length_weeks,
            first_term_week=first_term_week,
            start_date=start,
        )
        self.sections[label] = planted
        return planted

    def section(self, label: str) -> PlantedSection:
        planted = self.sections.get(label)
        if planted is None:
            pytest.fail(
                f"This world holds no section labelled {label!r}; it holds "
                f"{sorted(self.sections)}."
            )
        return planted

    def section_id(self, label: str) -> Any:
        return self.section(label).row[self.key_of(SECTION_TABLE)]

    def section_ids(self, *labels: str) -> list[Any]:
        return [self.section_id(label) for label in labels]

    def term_week_of(self, label: str, course_week: int) -> int:
        """Which term week one section's course week falls in.

        `first_term_week + course_week - 1`, from the start-letter map. **This is
        an input, not the value under test**: the views derive a course week from
        the section's stored `start_date` against its term's calendar, while this
        reads a transcribed table, so the two agree only if both are right. The
        control that keeps the transcription honest is
        `test_the_benchmark_calendar_literals_are_the_seeded_start_letter_map`.
        """
        planted = self.section(label)
        if not 1 <= course_week <= planted.length_weeks:
            pytest.fail(
                f"Course week {course_week} is outside section {label!r}, which runs "
                f"{planted.length_weeks} weeks. Seeding a response outside a section's own "
                "calendar builds a world that does not occur."
            )
        return planted.first_term_week + course_week - 1

    def window(self, label: str, term_week: int) -> Any:
        """One `survey_window` for one section and term week, at the hand-written instants."""
        planted = self.section(label)
        cached = planted.windows.get(term_week)
        if cached is not None:
            return cached
        instants = WINDOWS_BY_TERM[planted.term]
        if term_week not in instants:
            pytest.fail(
                f"This suite has no window instants written down for {planted.term} term week "
                f"{term_week}; it has {sorted(instants)}. The instants are read by nothing, but a "
                "row carrying an instant that contradicts its own calendar is a world nobody would "
                "trust — so a new week is a literal added to this file, never a computed one."
            )
        opens_at, closes_at = instants[term_week]
        window = self.seed(
            SURVEY_WINDOW_TABLE,
            {},
            **{
                WINDOW_SECTION_COLUMN: self.section_id(label),
                WINDOW_WEEK_COLUMN: self.week_id(term_week, planted.term),
                WINDOW_TERM_COLUMN: self.term_id(planted.term),
                WINDOW_OPENS_COLUMN: opens_at,
                WINDOW_CLOSES_COLUMN: closes_at,
            },
        )
        planted.windows[term_week] = window
        return window

    # -- people ---------------------------------------------------------------

    def student(self, subject: str, *, enrolled_in: Sequence[str] = ()) -> Any:
        """One `user`, enrolled in each labelled section from that section's start date.

        `ReportWorld.student` is not reused for this and the reason is the same
        one this class exists for: it takes cohort letters and reads their start
        dates out of the Fall 2026 map, and half the sections here are in another
        term. The `user` row itself goes through that class, so the platform
        registration every student needs is still seeded in one place.
        """
        user = self.report.student(subject, cohorts=())
        for label in enrolled_in:
            planted = self.section(label)
            self.seed(
                ENROLLMENT_TABLE,
                {},
                **{
                    self.report.link(ENROLLMENT_TABLE, USER_TABLE): user[self.key_of(USER_TABLE)],
                    self.report.link(ENROLLMENT_TABLE, SECTION_TABLE): self.section_id(label),
                    STARTED_ON_COLUMN: planted.start_date,
                    ENDED_ON_COLUMN: None,
                },
            )
        return user

    # -- what a student answered ----------------------------------------------

    def respond(
        self,
        label: str,
        *,
        course_week: int,
        student: Mapping[str, Any] | None = None,
        subject: str | None = None,
        workload: Decimal | None = None,
        instructor_rating: Decimal | None = None,
        course_rating: Decimal | None = None,
    ) -> Any:
        """One `response` in one section's course week, carrying the answers given.

        A position left out gets no `answer` row at all, which is the faithful
        record of a question that was not answered: E2-05 refuses an `answer`
        holding no value, so an absent row is the only spelling this schema has
        for it.

        **Every caller in this suite supplies a workload figure**, and that is
        deliberate rather than incidental: whether a cohort week with responses
        and no workload answers has a row with a null mean or no row at all is a
        question the ruling does not settle, so no test here depends on the
        answer. It is recorded as an open question for ADR 0165 instead of being
        decided by a fixture.
        """
        planted = self.section(label)
        term_week = self.term_week_of(label, course_week)
        window = self.window(label, term_week)
        _opens_at, closes_at = WINDOWS_BY_TERM[planted.term][term_week]

        if student is None:
            if subject is None:
                pytest.fail("`respond` needs either a seeded student or a subject to seed one by.")
            student = self.student(subject, enrolled_in=(label,))

        values: dict[str, Any] = {
            RESPONSE_USER_COLUMN: student[self.key_of(USER_TABLE)],
            RESPONSE_SECTION_COLUMN: self.section_id(label),
            RESPONSE_WEEK_COLUMN: self.week_id(term_week, planted.term),
            RESPONSE_TERM_COLUMN: self.term_id(planted.term),
        }
        if self.report.has_column(RESPONSE_TABLE, "submitted_at"):
            values["submitted_at"] = closes_at - SUBMITTED_BEFORE_CLOSE
        response_table = require_table(self.tables, RESPONSE_TABLE)
        window_column = single_column_link(response_table, SURVEY_WINDOW_TABLE)
        if window_column is not None:
            values[window_column] = window[self.key_of(SURVEY_WINDOW_TABLE)]
        set_column = single_column_link(response_table, QUESTION_SET_TABLE)
        if set_column is not None:
            values[set_column] = self.report.question_sets[FIRST_VERSION][
                self.key_of(QUESTION_SET_TABLE)
            ]
        response = self.seed(RESPONSE_TABLE, {}, **values)

        answers = {
            INSTRUCTOR_RATING_POSITION: instructor_rating,
            COURSE_RATING_POSITION: course_rating,
            WORKLOAD_POSITION: workload,
        }
        for position, value in sorted(answers.items()):
            if value is not None:
                self.report.answer(response, position, value, version=FIRST_VERSION)
        return response

    # -- reading back ----------------------------------------------------------

    def rows(self, view: str, **filters: Any) -> list[dict[str, Any]]:
        """Every row `view` holds under the given key columns, flushed first."""
        self.session.flush()
        return benchmark_rows(self.session, view, **filters)

    def row(self, view: str, **filters: Any) -> dict[str, Any] | None:
        self.session.flush()
        return one_benchmark_row(self.session, view, **filters)

    def cohort_week(
        self, *, length_weeks: int, level: str, course_week: int, term: str = CURRENT_TERM
    ) -> dict[str, Any] | None:
        """The one workload-and-counts row for a whole course-week cohort key."""
        return self.row(
            COHORT_WEEK_VIEW,
            length_weeks=length_weeks,
            level=level,
            term_id=self.term_id(term),
            course_week=course_week,
        )

    def cohort_rating_week(
        self,
        *,
        length_weeks: int,
        level: str,
        course_week: int,
        stream: str,
        term: str = CURRENT_TERM,
    ) -> dict[str, Any] | None:
        """The one rating row for a whole course-week cohort key and one stream."""
        return self.row(
            COHORT_RATING_WEEK_VIEW,
            length_weeks=length_weeks,
            level=level,
            term_id=self.term_id(term),
            course_week=course_week,
            stream=stream,
        )

    def term_axis(
        self,
        *,
        length_weeks: int,
        level: str,
        term_week: int,
        section_start_date: date,
        term: str = CURRENT_TERM,
    ) -> dict[str, Any] | None:
        """The one term-axis row for one start cohort at one term week."""
        return self.row(
            COHORT_TERM_AXIS_VIEW,
            length_weeks=length_weeks,
            level=level,
            term_id=self.term_id(term),
            term_week=term_week,
            section_start_date=section_start_date,
        )

    def set_week(self, *labels: str) -> list[dict[str, Any]]:
        """`benchmark_set_week` over exactly the labelled sections."""
        self.session.flush()
        return set_function_rows(self.session, SET_FUNCTION, self.section_ids(*labels))

    def set_rating_week(self, *labels: str) -> list[dict[str, Any]]:
        """`benchmark_set_rating_week` over exactly the labelled sections."""
        self.session.flush()
        return set_function_rows(self.session, SET_RATING_FUNCTION, self.section_ids(*labels))


@pytest.fixture
def benchmark_world(configured_env: dict[str, str], report_world: ReportWorld) -> BenchmarkWorld:
    """The world E5-03's views are measured over, **unbuilt**.

    Unbuilt for `docs/MISTAKES.md` entry 44's reason: every guard this world
    raises — a missing view, a missing function, a missing `question.stream` —
    has to fire inside a test body so the red is a failure rather than an error
    in setup.

    **`configured_env` is declared rather than inherited**, which is
    `docs/MISTAKES.md` entry 40's rule applied to a new module: the session-wide
    baseline would answer for these tests silently, and under `-n 4` a module
    that states nothing gets whichever environment its worker happened to build.
    Nothing here reads a variable, and that is exactly why the declaration is
    cheap and the omission would be invisible.
    """
    return BenchmarkWorld(report_world)


@pytest.fixture
def committed_benchmark_world(
    configured_env: dict[str, str],
    committed_rows: Any,
    metadata_tables: dict[str, Any],
) -> BenchmarkWorld:
    """The same world, committed, so a second connection can read it.

    The application role connects for itself (ADR 0001: the pool is bound to the
    service), so a test that reads a benchmark view **as `pulse_app`** over real
    rows needs them committed or it is reading an empty view and calling it a
    pass. `committed_rows` removes whatever appeared when the test ends.

    The session states its environment for the reason
    `committed_report_world` states it: Batch C's registration-address rules
    judge a session that states nothing as a deployment, and the seeding
    walker's invented `lti_platform` row carries a development stack's cleartext
    address. Without the stamp this world fails inside its own seeding.
    """
    committed_rows.session.info["environment"] = DEVELOPMENT
    report = ReportWorld(Fall2026(committed_rows.seed, committed_rows.session, metadata_tables))
    return BenchmarkWorld(report)


# The two streams, re-exported so a test module reads one import for the whole
# contract rather than reaching into E4's fixture for half of it.
__all__ = [
    "BENCHMARK_FUNCTIONS",
    "BENCHMARK_VIEWS",
    "COHORT_RATING_TERM_AXIS_VIEW",
    "COHORT_RATING_WEEK_VIEW",
    "COHORT_TERM_AXIS_VIEW",
    "COHORT_WEEK_VIEW",
    "COURSE_RATING_POSITION",
    "COURSE_STREAM",
    "COURSE_WEEK_VIEWS",
    "CURRENT_TERM",
    "GR",
    "INSTRUCTOR_RATING_POSITION",
    "INSTRUCTOR_STREAM",
    "PRIOR_TERM",
    "PRIOR_TERM_COHORTS",
    "PRIOR_TERM_START",
    "PRIOR_TERM_WEEKS",
    "PRIOR_WINDOWS_BY_TERM_WEEK",
    "RATING_VIEWS",
    "SET_FUNCTION",
    "SET_RATING_FUNCTION",
    "TERM_AXIS_VIEWS",
    "UG",
    "UGGR",
    "WORKLOAD_POSITION",
    "WORKLOAD_VIEWS",
    "BenchmarkWorld",
    "PlantedSection",
    "benchmark_rows",
    "benchmark_view_columns",
    "call_wrapper",
    "empty_set_call",
    "function_shape",
    "one_benchmark_row",
    "query_module",
    "query_wrapper",
    "require_benchmark_function",
    "require_benchmark_view",
    "set_function_rows",
]
