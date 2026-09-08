"""E4-07 — the world the instructor's Monday report is read over, and the names it is asked through.

Six test modules need the same four things, and no fixture in this repository
answers any of them:

  - **An instructor at the door with a section that is hers, and one that is
    not.** E4-07's authorization is "the requesting session's own taught
    sections, nothing else", resolved from the `teaching_instructor` view — which
    is a `role_assignment` row of role `INSTRUCTOR` scoped to a section
    (`tests/integration/test_the_roster_definers_answer_a_point_query_and_nothing_more.py`
    is where `record_teaching_instructor` writes one). So the world seeds that row
    for one of its two sections and not for the other, and the second section is
    the out-of-scope half of criterion 1's refusal pair.

  - **A term of weeks whose published/unpublished line the test moves.**
    Breakdown decision 6 makes a published week one whose survey window has
    closed, per the clock service, so criterion 3's boundary is a clock position
    rather than a stored flag. Every window this world writes carries SPEC §3.1's
    own Fall 2026 instants (`WINDOWS_BY_TERM_WEEK`, hand-written in
    `tests/fixtures/survey_windows.py`), and `ReportDoor.pretend` puts the
    development clock on either side of one of them.

  - **A section whose course weeks are not its term weeks.** Cohort `F` runs six
    weeks from term week 7 (`SEEDED_COHORTS`, transcribed from `scripts/seed.py`),
    so §2.2's two axes are two different numbers in every assertion here and a
    payload that served one in the other's place is red. `COURSE_WEEK_OF_TERM_WEEK`
    below is written out by hand and checked against the cohort facts by
    `assert_the_cohort_is_what_this_file_says`, so nothing here re-derives the
    start-letter calendar it is measuring (`docs/MISTAKES.md` entry 19).

  - **The names E4-07's work order settles**, spelled once. The module homes
    (`app.api.instructor`, `app.api.deps.require_instructor`,
    `app.services.reporting`, `app.schemas.report`), the two configured
    benchmark minimums, and the payload members the README sketch freezes. A name
    the work order settles is transcribed; a name it does not settle is
    **discovered**, and an ambiguous discovery is a failure naming the ambiguity
    rather than a guess — the device `tests/fixtures/report_views.py` uses for the
    validity service's signature and `tests/fixtures/report_comments.py` uses for
    `moderation_state`'s instant column.

**Two things the ticket and the work order do not settle, and how they are
reached.** Both are recorded here rather than guessed, because a spelling invented
in a fixture is an interface the tests decided:

  - **The two routes' URLs and how they take their parameters.** Nothing in
    `docs/tickets/e4/` names either path. So they are *discovered* the way
    `tests/fixtures/submit.py::submit_route` discovers E2-08's — through the
    module the work order does settle (`app.api.instructor`) — and classified by
    the parameters they declare: the route that names a course week is the report,
    the one that does not is the published-week list. Path parameters and query
    parameters are both filled, so neither spelling is imposed. An application
    where the two cannot be told apart is a failure naming that, and the repair is
    a line in this file rather than in six modules.

  - **The suppression helper's own name, and the name of the type it returns.**
    Work-order decision 5 settles the *mechanism* — "the `comparison` payload
    value is a class whose constructor demands a module-private token only the
    helper holds; the Pydantic schema field takes that type" — and settles no
    spelling for either. So the type is read off the schema field's annotation and
    the helper is the one public callable in `app.services.reporting` annotated to
    return it. Zero or several is a failure naming the ambiguity.

**Nothing here decides what the payload should say.** This file seeds rows, moves
a clock and makes requests; every expectation is written out in the test module
that makes it (`docs/MISTAKES.md` entries 19 and 30). In particular nothing here
divides a rate, counts an enrolment, numbers a course week for a test, or decides
which weeks are published: `COURSE_WEEK_OF_TERM_WEEK` is a hand-written table with
a premise check over it, and every rate a test asserts is arithmetic that test
writes out over the responses it planted.

**Every guard is a plain function called from a test body, never a fixture**
(`docs/MISTAKES.md` entry 44). On a tree where E4-07 is unbuilt each module goes
red as a FAILED naming the missing deliverable — the router, the dependency, the
schema, the helper — rather than as an ERROR in somebody's setup. `report_door`
is the one exception that proves it: it builds a world and a launch, both of which
are E4-03's and E1's machinery and both of which exist on this tree, and it makes
no reference to anything E4-07 owes.

**The environment** (`docs/MISTAKES.md` entry 40): everything here rides
`launch_driver_in`, which rides `tool_doors` and therefore `configured_env` — the
development name, laid down before the application is imported, which is what ADR
0109 requires before a `clock_override` row means anything. Any test that builds
`Settings()` directly asks for `configured_env` in its own chain.
"""

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from typing import Any, NamedTuple
from uuid import uuid4

import pytest

from fixtures.clock import DEVELOPMENT
from fixtures.grading import (
    ENDED_ON_COLUMN,
    ENROLLMENT_TABLE,
    RESPONSE_SECTION_COLUMN,
    STARTED_ON_COLUMN,
)
from fixtures.provisioning import INSTRUCTOR_ROLE_URN, LEARNER_ROLE_URN
from fixtures.report_comments import CommentWorld
from fixtures.report_views import (
    COURSE_STREAM,
    INSTRUCTOR_STREAM,
    SECOND_COHORT,
)
from fixtures.routing import every_route
from fixtures.student_read import (
    AUTHENTICATE_HEADER,
    AUTHENTICATE_SCHEME,
    INSTRUCTOR_LANDING,
    REFUSED_STATUS,
    SESSION_FRAGMENT,
    STUDENT_LANDING,
    decoded,
    scalars_in,
    session_token_at,
)
from fixtures.submit import RESPONSE_TABLE, USER_TABLE
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import (
    SECTION_TABLE,
    SEEDED_COHORTS,
    WINDOWS_BY_TERM_WEEK,
    Fall2026,
)

# ---------------------------------------------------------------------------
# The names E4-07's work order settles, transcribed once.
# ---------------------------------------------------------------------------

# Work-order decision 2: "Router: `backend/app/api/instructor.py`, thin per §13."
# This is how both routes are *found* — see `report_route` — so it is a settled
# fact this file rests on rather than a spelling it invented.
INSTRUCTOR_API_MODULE = "app.api.instructor"

# Decision 2 again: "Both behind a new `require_instructor` dependency in
# `backend/app/api/deps.py`, patterned on `require_student`."
DEPS_MODULE = "app.api.deps"
REQUIRE_INSTRUCTOR = "require_instructor"

# Decision 1: "the read service lives in `backend/app/services/reporting.py`,
# beside the summary walk. No new module." Decision 5 puts the item-7 suppression
# helper in the same file, "benchmark assembly is its §13 mandate".
REPORTING_MODULE = "app.services.reporting"

# Decision 4: "Schema: new `backend/app/schemas/report.py`, mirroring the README
# sketch."
REPORT_SCHEMA_MODULE = "app.schemas.report"

# Decision 5's catalog, **named rather than described** — `docs/MISTAKES.md`
# entry 22's rule is to name the catalog and not the concept, and these two are
# the catalog. Both already exist in `backend/app/config.py`; `.env.example`
# documents them as `BENCHMARK_MIN_SECTIONS_DEFAULT` and
# `BENCHMARK_MIN_RESPONDENTS_DEFAULT` with SPEC §11 question 1's starting values.
CONFIG_MODULE = "app.config"
BENCHMARK_MIN_SECTIONS = "benchmark_min_sections_default"
BENCHMARK_MIN_RESPONDENTS = "benchmark_min_respondents_default"
BENCHMARK_MINIMUMS = (BENCHMARK_MIN_SECTIONS, BENCHMARK_MIN_RESPONDENTS)

# ---------------------------------------------------------------------------
# The payload, as the README sketch freezes it and the work order amends it.
# ---------------------------------------------------------------------------

# `docs/tickets/e4/README.md`'s sketch (~line 213), transcribed member by member.
# Breakdown decision 5 makes it "frozen enough to build against" and makes
# E4-07's Pydantic schema the authority the moment it merges — so a divergence
# from these names is a deliberate act the pull request lists (criterion 8), not
# a rename a test should tolerate quietly.
SECTION_MEMBER = "section"
WEEK_MEMBER = "week"
RATES_MEMBER = "rates"
STREAMS_MEMBER = "streams"
WORKLOAD_MEMBER = "workload"
COMPARISON_MEMBER = "comparison"
SMALL_N_MEMBER = "small_n"

SECTION_CODE_FIELD = "code"
SECTION_COURSE_LABEL_FIELD = "course_label"
SECTION_LENGTH_FIELD = "length_weeks"

COURSE_WEEK_FIELD = "course_week"
TERM_WEEK_FIELD = "term_week"
PUBLISHED_WEEKS_FIELD = "published_weeks"

RESPONSE_RATE_FIELD = "response_rate"
VALIDITY_RATE_FIELD = "validity_rate"
RESPONSES_FIELD = "responses"
ENROLLED_FIELD = "enrolled"

# Work-order decision 4's first named divergence: "`rates` gains
# `valid_responses` (E4-09's components consume it; the sketch omitted it — the
# recorded E4-09 deferral). Its source is `response.is_valid` per ADR 0147, never
# `classification`."
VALID_RESPONSES_FIELD = "valid_responses"

TREND_FIELD = "trend"
DISTRIBUTION_FIELD = "distribution"
SUMMARY_FIELD = "summary"
COMMENTS_FIELD = "comments"
TREND_MEAN_FIELD = "mean"

COMMENT_TEXT_FIELD = "text"
COMMENT_STATUS_FIELD = "status"

SUPPRESSED_FIELD = "suppressed"

# Work-order decision 4's second named divergence: "a top-level
# `released_from_earlier_weeks` member: the released-comments list ADR 0152 says
# E4-07 places. Present in every report payload as a list; populated only when the
# requested course week is the latest published week, else empty."
RELEASED_MEMBER = "released_from_earlier_weeks"

# How the sketch spells the two streams as payload members, against E4-02's
# stored vocabulary. The sketch nests `streams.instructor` and `streams.course`;
# the column carries `INSTRUCTOR` and `COURSE` (`tests/fixtures/report_views.py`).
# The mapping is the sketch's and is written here so no test module holds a copy.
PAYLOAD_STREAM_KEY = {INSTRUCTOR_STREAM: "instructor", COURSE_STREAM: "course"}

# Every field a comment object in this payload may carry, and nothing else.
# Criterion 4: the service "adds no field, no count, and no ordering information
# beyond" what `visible_comments` and `released_comments` return, and those return
# `ReportComment(text, status, stream)` (`tests/fixtures/report_comments.py`). The
# stream is spelled by the member a comment sits under in `streams`, so it is
# tolerated on the object and not required.
COMMENT_FIELDS_PERMITTED = frozenset({COMMENT_TEXT_FIELD, COMMENT_STATUS_FIELD, "stream"})

# ---------------------------------------------------------------------------
# What a refusal looks like on the wire.
# ---------------------------------------------------------------------------

# Work-order decision 3: "Refusal pair: 404 with one shared body for a section
# outside the session's teaching set and for a section that does not exist —
# indistinguishable in status, body, and shape."
OUT_OF_SCOPE_STATUS = 404

# And decision 2's role refusal: a student or leadership session "is refused these
# routes exactly as a wrong-role session is refused student routes", which is
# `tests/fixtures/student_read.py`'s `REFUSED_STATUS` — 401 with
# `WWW-Authenticate: Bearer`. Imported rather than respelled so the two cannot
# drift into two numbers.
ROLE_REFUSED_STATUS = REFUSED_STATUS

# Where a landing hands the browser its session, per role. Two are
# `tests/fixtures/student_read.py`'s; the third is spelled here from E1-04's route
# group names (`tests/fixtures/landing.py::LEADERSHIP_ROUTE`).
LEADERSHIP_LANDING = f"/app/leadership{SESSION_FRAGMENT}"

# ---------------------------------------------------------------------------
# This suite's own world. None of it is a claim about anything the system
# decides — every value is an input a test names and this file writes down.
# ---------------------------------------------------------------------------

# **A cohort whose course weeks are not its term weeks.** `F` runs six weeks from
# term week 7 (`SEEDED_COHORTS`, transcribed from `scripts/seed.py`), so no wrong
# answer for one axis is the right answer for the other: term week 8 is course
# week 2, and a payload serving 8 where 2 belongs is red rather than plausible.
TAUGHT_COHORT = "F"

# The section the launching instructor does **not** teach. `Q` runs twelve weeks
# from term week 7 under the same containment chain (`Fall2026` seeds every
# section it is asked for under one course), so it differs from the taught section
# in its own row and in nothing above it — which is the shape a scope query that
# joined on the course, the term or the week answers with both.
UNTAUGHT_COHORT = SECOND_COHORT

# **Written out by hand, and checked against the cohort facts rather than derived
# from them** (`docs/MISTAKES.md` entry 19). The report computes this mapping;
# a fixture that computed it the same way would agree with an implementation that
# got it wrong. `assert_the_cohort_is_what_this_file_says` is the premise check
# that keeps this table honest if `SEEDED_COHORTS` ever moves.
COURSE_WEEK_OF_TERM_WEEK = {7: 1, 8: 2, 9: 3, 10: 4, 11: 5, 12: 6}
TERM_WEEK_OF_COURSE_WEEK = {course: term for term, course in COURSE_WEEK_OF_TERM_WEEK.items()}
TAUGHT_TERM_WEEKS = tuple(sorted(COURSE_WEEK_OF_TERM_WEEK))
TAUGHT_LENGTH_WEEKS = 6

# The canonical world's weeks, by what each is *for*. Every one of them is a
# closed window at SPEC §3.1's own Fall 2026 instants, so which weeks are
# published is decided by where `ReportDoor.pretend` puts the clock and by
# nothing else.
#
#   - course week 1 — a week at or above the n-threshold, so its comments are
#     visible and criterion 4 has something to compare;
#   - course weeks 3 and 4 — two under-threshold closed weeks whose comments are
#     held, which is the world ADR 0152's three-legged release gate needs;
#   - course weeks 2 and 5 — the enrolment-window boundary pair (ADR 0147's
#     re-homed criterion 5): the leaver is in one denominator and not the other;
#   - course week 6 — nobody answered, which is criterion 7's whole subject, and
#     it is the latest published week, which is where ADR 0152 puts the released
#     list.
FULL_WEEK = 1
IN_DENOMINATOR_WEEK = 2
FIRST_HELD_WEEK = 3
SECOND_HELD_WEEK = 4
OUT_OF_DENOMINATOR_WEEK = 5
SILENT_WEEK = 6

# When the leaver's enrolment ends: **in the dead space between course week 3's
# window closing and course week 4's opening.** ADR 0020's convention makes
# `ended_on` the last included day, and every date either side of this one is
# asserted from `WINDOWS_BY_TERM_WEEK` in
# `assert_the_leaver_straddles_the_boundary` rather than believed.
#
# **The first version of this constant was 2026-10-18 and was wrong, which is
# worth leaving written down.** "Weeks 1-3 of a 6-week section" reads as "the last
# day of course week 3", and the last day of that week in the institution's own
# zone is the Sunday, 2026-10-18 — but the window it closes with runs to
# 2026-10-19 03:59:59 **UTC**, and every instant this world writes is UTC. So the
# date chosen from the wall clock sat one day *before* the window it was meant to
# be inside, the self-check below caught it, and it took 35 of this ticket's 45
# cases with it. The lesson is the one `docs/MISTAKES.md` entry 19 keeps
# recording from the other end: a date derived by hand from a rhythm agrees with
# whichever reading of that rhythm the deriver had in mind, and the only cure is
# to compare it against the stored instants rather than against the sentence.
#
# **Deliberately not an endpoint.** 2026-10-19 is the true last UTC day of course
# week 3 and would make the pair turn on an edge nobody has settled — whether an
# enrolment ending on the day a window closes is inside that week is exactly the
# kind of question this ticket does not answer. Two days later is inside course
# week 4's calendar span and still before course week 4's *window* opens
# (2026-10-23 22:00 UTC), so under either window-based reading of "enrolled that
# week" she belongs to weeks 1-3 and to none of 4, 5 or 6 — and no assertion in
# this suite touches week 4's denominator, where a Monday-to-Sunday reading and a
# window reading would genuinely differ.
LEAVER_ENDED_ON = date(2026, 10, 21)

# The ratings each respondent gives in the full week, by question position: SPEC
# §3.2 puts the instructor rating at 1, the course rating at 3 and the workload
# figure at 5.
#
# **The fifth respondent leaves the instructor rating unanswered**, and that is
# ADR 0147's re-homed criterion 3 written as data: "an absent response
# contributes nothing to the mean (it costs the response rate, not the average)".
# `None` here means no `answer` row at all, which is the faithful record of a
# question nobody answered — E2-05 refuses an answer holding no value and ADR
# 0115 deletes a withdrawn one, so absence is the only spelling this schema has.
#
# **Every number the two streams produce is different, and exact.** The
# instructor mean over the four answered ratings is 4.0 and the course mean over
# all five is 3.0, so a payload averaging the wrong stream, or dividing by the
# response count instead of by the answered count (16/5 = 3.2), lands on a value
# none of the others is. All three are exact in binary, so no assertion here
# turns on a float's spelling.
FULL_WEEK_INSTRUCTOR_RATINGS: tuple[int | None, ...] = (5, 4, 4, 3, None)
FULL_WEEK_COURSE_RATINGS = (4, 4, 3, 3, 1)
FULL_WEEK_WORKLOAD_HOURS = (
    Decimal("6.0"),
    Decimal("8.0"),
    Decimal("9.0"),
    Decimal("11.0"),
    Decimal("16.0"),
)

RATING_POSITION = {INSTRUCTOR_STREAM: 1, COURSE_STREAM: 3}
WORKLOAD_POSITION = 5

# The comment texts this world plants. Distinctive enough that a leak of one is
# unmistakable in a failure message, and long enough to clear SPEC §3.3's
# character floor.
FULL_WEEK_COMMENTS = (
    "E4-07 full week 1: the walkthrough of the first assignment was worth the whole session",
    "E4-07 full week 2: the pacing was fine but the reading list arrived on the Thursday",
    "E4-07 full week 3: office hours clashed with the lab and I could not make either",
    "E4-07 full week 4: the feedback on the draft was specific and I could act on it",
    "E4-07 full week 5: the slides and the recording said different things about the deadline",
)
HELD_COMMENTS = {
    FIRST_HELD_WEEK: (
        "E4-07 held week A1: nobody else posted in the forum so the group task stalled",
        "E4-07 held week A2: the second reading assumed a module I have not taken",
        "E4-07 held week A3: the recording cut out about twenty minutes in",
    ),
    SECOND_HELD_WEEK: (
        "E4-07 held week B1: the workload this week was much heavier than the others",
        "E4-07 held week B2: I would have liked one worked example before the exercise",
    ),
}

# How many responses each week of the canonical world holds. Written out so a
# test can assert the week it is about is on the side of the threshold it needs,
# and `responses_in` reads the database back rather than trusting this table.
RESPONSES_IN_WEEK = {
    FULL_WEEK: 5,
    IN_DENOMINATOR_WEEK: 2,
    FIRST_HELD_WEEK: 3,
    SECOND_HELD_WEEK: 2,
    OUT_OF_DENOMINATOR_WEEK: 1,
    SILENT_WEEK: 0,
}

# The people this world seeds: five respondents who answer in several weeks, and
# one leaver who answers in none. Six rather than one per response, because the
# release gate ADR 0152 settles counts *distinct respondents* behind held
# comments and a world with one person per response could not tell the two
# currencies apart (`docs/MISTAKES.md` entry 50).
RESPONDENTS = 5

# Which respondents answer in which week, by index into the five. The full week is
# everybody; the two held weeks split them so that the held set spans two weeks
# and five distinct people, which is what opens all three legs of ADR 0152's gate.
ANSWERED_BY = {
    FULL_WEEK: (0, 1, 2, 3, 4),
    IN_DENOMINATOR_WEEK: (0, 1),
    FIRST_HELD_WEEK: (0, 1, 2),
    SECOND_HELD_WEEK: (3, 4),
    OUT_OF_DENOMINATOR_WEEK: (0,),
    SILENT_WEEK: (),
}

# Where the development clock starts: after the last of the six windows has
# closed, so every course week of the section is published and a test that wants
# an unpublished week moves the clock back rather than forward. Measured off the
# hand-written calendar rather than written as a literal, because it is a
# *position relative to* an instant this file does not own.
AFTER_THE_LAST_WINDOW = WINDOWS_BY_TERM_WEEK[TAUGHT_TERM_WEEKS[-1]][1] + timedelta(days=1)

# How far either side of a window's close the clock is put for criterion 3's
# pair. Whole hours, because ADR 0109 makes the effective instant
# `real + (pretend_now - anchored_at)` — it keeps moving while it is read, so a
# value placed a second from an edge is a boundary nothing can stand on.
EITHER_SIDE_OF_A_CLOSE = timedelta(hours=6)

# How far back the refused-role student's enrolment starts, **counted from UTC's
# real today and not from the pretended clock.** That distinction is the whole of
# this constant, and it is written down because getting it wrong cost this suite
# a round: the first version seeded the enrolment on `AFTER_THE_LAST_WINDOW`, the
# instant the development clock is moved to, and the launch landed on the calm
# no-access page — an enrolment that has not begun yet on the real day is not a
# live enrolment, so no session was issued and the role gate under test was never
# reached.
#
# Thirty days back with no end date is live under **both** clocks — the real one
# and the 2026 instant this world pretends — which is the point: this suite does
# not know which of the two E1-13's landing judges an enrolment against, and a
# date that is only right under one of them is a fixture betting on an answer.
# Comfortably longer than any timezone offset too, so the window contains the
# institution's today whatever `INSTITUTION_TIMEZONE` says. The invocation is
# copied from the module that already does this —
# `tests/integration/test_the_launch_views_name_nobody.py`'s `landings` fixture,
# `datetime.now(UTC).date() - timedelta(days=ENROLLED_SINCE_DAYS)` — rather than
# rewritten (`docs/MISTAKES.md` entry 37).
STUDENT_ENROLLED_SINCE_DAYS = 30

# ---------------------------------------------------------------------------
# The messages a missing deliverable is reported with.
# ---------------------------------------------------------------------------

ROUTER_IS_OWED = (
    "E4-07's work order settles the router: `backend/app/api/instructor.py`, thin over the read "
    "service per SPEC §13, carrying two GET routes — the report for one section and one course "
    "week, and the published-week list. Both behind `require_instructor`, and the router has to be "
    "registered in `app.main.create_app` for a request to reach it at all."
)

DEPENDENCY_IS_OWED = (
    f"`{DEPS_MODULE}.{REQUIRE_INSTRUCTOR}` — E4-07's work order settles it as the instructor-session "
    "dependency, patterned on `require_student` (~line 281): the role comes from the session claims "
    "and never from a parameter, and a student or leadership session is refused exactly as a "
    "wrong-role session is refused a student route."
)

SCHEMA_IS_OWED = (
    f"`{REPORT_SCHEMA_MODULE}` — E4-07's work order settles a new Pydantic schema module mirroring "
    "the payload sketch in `docs/tickets/e4/README.md`, with `rates.valid_responses` and the "
    f"top-level `{RELEASED_MEMBER}` as its two named divergences. Breakdown decision 5 makes it the "
    "authority over the sketch the moment it merges."
)

REPORTING_IS_OWED = (
    f"`{REPORTING_MODULE}` — E4-07's work order puts the report read service beside the summary "
    "walk rather than in a module of its own, because that module's merged header already claims "
    "E4-07's read side and SPEC §13 names `reporting` for 'distributions, trend lines, benchmark "
    "assembly'. The item-7 suppression helper lives there too (decision 5)."
)

COMPARISON_TYPE_IS_OWED = (
    "the `comparison` field of E4-07's report schema, annotated with the type work-order decision 5 "
    f"settles: a class defined in `{REPORTING_MODULE}` whose constructor demands a module-private "
    "token only the suppression helper holds. SPEC §4.1 item 7 is asserted here as a chokepoint "
    "(breakdown decision 4), and a field typed as a plain dict or a loose model is a chokepoint any "
    "later caller walks around."
)

HELPER_IS_OWED = (
    "the one public callable in "
    f"`{REPORTING_MODULE}` annotated to return the `comparison` field's type — work-order decision "
    "5's suppression helper, the only way that member can be populated. It enforces **both** "
    f"configured minimums, `{BENCHMARK_MIN_SECTIONS}` and `{BENCHMARK_MIN_RESPONDENTS}`; a helper "
    "reading one of two thresholds is the closed-set defeat `docs/MISTAKES.md` entry 22 records."
)


# ---------------------------------------------------------------------------
# The deliverables, named where a test can fail on them rather than error.
# ---------------------------------------------------------------------------


def _module(name: str, owed: str) -> Any:
    """One module, imported where a test can fail on it rather than error.

    A `ModuleNotFoundError` at a test module's top level is a collection error,
    which survives the implementation landing and reads to a hurried eye as a red
    suite (`docs/MISTAKES.md` entry 44). This is a FAILED naming the file. An
    import error raised from *inside* the module — a dependency of its own that is
    missing — is re-raised rather than reported as this module's absence, because
    the two are different defects.
    """
    try:
        return import_module(name)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (absent == name or name.startswith(f"{absent}.")):
            raise
        pytest.fail(f"`{name}` does not exist. {owed}")


def instructor_api_module() -> Any:
    """`app.api.instructor`, or a failure naming the router E4-07 owes."""
    return _module(INSTRUCTOR_API_MODULE, ROUTER_IS_OWED)


def reporting_module() -> Any:
    """`app.services.reporting`, or a failure naming it."""
    return _module(REPORTING_MODULE, REPORTING_IS_OWED)


def report_schema_module() -> Any:
    """`app.schemas.report`, or a failure naming it."""
    return _module(REPORT_SCHEMA_MODULE, SCHEMA_IS_OWED)


def require_instructor_dependency() -> Any:
    """`app.api.deps.require_instructor`, or a failure naming the symbol E4-07 owes."""
    module = _module(
        DEPS_MODULE,
        "E1-13 already puts this project's door pages there and E2-09 the student-session "
        "dependency; E4-07 adds the instructor one beside them.",
    )
    found = getattr(module, REQUIRE_INSTRUCTOR, None)
    if not callable(found):
        pytest.fail(
            f"`{DEPS_MODULE}` exposes no callable `{REQUIRE_INSTRUCTOR}`; it exposes "
            f"{sorted(name for name in vars(module) if not name.startswith('_'))}.\n\n"
            f"{DEPENDENCY_IS_OWED}"
        )
    return found


def configured_benchmark_minimums() -> dict[str, int]:
    """`Settings`' two benchmark minimums, by field name, or a failure naming the pair.

    Constructed rather than passed in, for the reason
    `tests/fixtures/report_comments.py::configured_threshold` gives about the
    n-threshold: the claim under test is about *the configured numbers*, and
    comparing against numbers this file invented would assert something else.
    Both are read in one call so that a tree carrying one of the two fails naming
    the missing half — which is the closed-set defeat this whole chokepoint exists
    to stop (`docs/MISTAKES.md` entry 22).
    """
    module = _module(CONFIG_MODULE, "E0-02 ships `Settings`.")
    settings_class = getattr(module, "Settings", None)
    if settings_class is None:
        pytest.fail(f"`{CONFIG_MODULE}` exposes no `Settings`.")
    settings = settings_class()
    found: dict[str, int] = {}
    missing: list[str] = []
    for name in BENCHMARK_MINIMUMS:
        value = getattr(settings, name, None)
        if value is None:
            missing.append(name)
        else:
            found[name] = int(value)
    if missing:
        pytest.fail(
            f"`Settings` has no {missing}. `.env.example` documents both — "
            "`BENCHMARK_MIN_SECTIONS_DEFAULT` and `BENCHMARK_MIN_RESPONDENTS_DEFAULT` — as SPEC "
            "§5.1's benchmark minimum-N, distinct from the section small-N threshold, and SPEC §11 "
            "question 1 names the pair. E4's breakdown decision 4 makes the item-7 helper enforce "
            "**both**."
        )
    return found


def comparison_field_type() -> Any:
    """The type E4-07's schema declares for its `comparison` member.

    **Discovered from the annotation, because the work order settles the mechanism
    and not the spelling.** Decision 5: "the `comparison` payload value is a class
    whose constructor demands a module-private token only the helper holds; the
    Pydantic schema field takes that type." So the type is whatever that field is
    annotated with, and the tests assert properties of it — where it is defined,
    that it refuses construction without the token — rather than its name.

    A `None`-able annotation (`X | None`) is unwrapped to `X`, because "absent" is
    a legitimate spelling for a member nothing has populated and the class under
    the union is still the thing item 7 is about.
    """
    import typing

    module = report_schema_module()
    models = [
        value
        for name, value in vars(module).items()
        if not name.startswith("_")
        and isinstance(value, type)
        and COMPARISON_MEMBER in (getattr(value, "model_fields", None) or {})
    ]
    if len(models) != 1:
        pytest.fail(
            f"`{REPORT_SCHEMA_MODULE}` declares {len(models)} models carrying a "
            f"`{COMPARISON_MEMBER}` field ({[model.__name__ for model in models]}); it declares "
            f"{sorted(name for name in vars(module) if not name.startswith('_'))}.\n\n"
            f"{COMPARISON_TYPE_IS_OWED}"
        )
    annotation = models[0].model_fields[COMPARISON_MEMBER].annotation
    arguments = [argument for argument in typing.get_args(annotation) if argument is not type(None)]
    if typing.get_origin(annotation) is not None and len(arguments) == 1:
        annotation = arguments[0]
    if not isinstance(annotation, type):
        pytest.fail(
            f"The `{COMPARISON_MEMBER}` field is annotated {annotation!r}, which is not a single "
            f"class this suite can ask questions of.\n\n{COMPARISON_TYPE_IS_OWED}"
        )
    return annotation


def suppression_helper() -> Any:
    """The one public callable in `app.services.reporting` that returns the comparison type.

    **Discovered by its return annotation, because no record settles its name.**
    The work order settles that it exists, where it lives and what it enforces;
    a constant here would be this suite choosing a spelling the ticket left open,
    and a discovery that guessed between two candidates would be worse. Zero or
    several is a failure naming the ambiguity, which is the device
    `tests/fixtures/report_views.py::recompute_validity` uses and for the same
    reason.
    """
    import typing

    module = reporting_module()
    wanted = comparison_field_type()
    found: list[Any] = []
    for name, value in vars(module).items():
        if name.startswith("_") or not callable(value):
            continue
        if getattr(value, "__module__", None) != REPORTING_MODULE:
            continue
        try:
            hints = typing.get_type_hints(value)
        except Exception:  # noqa: S112  # pragma: no cover - an unresolvable annotation is not this test's subject
            continue
        returned = hints.get("return")
        candidates = [returned, *typing.get_args(returned)]
        if any(candidate is wanted for candidate in candidates):
            found.append(value)
    if len(found) != 1:
        pytest.fail(
            f"`{REPORTING_MODULE}` exposes {len(found)} public callables returning "
            f"`{wanted.__name__}` ({[entry.__name__ for entry in found]}). This suite needs exactly "
            f"one to drive both minimums through, and it finds it by that return annotation because "
            f"no record settles a name.\n\n{HELPER_IS_OWED}"
        )
    return found[0]


def call_the_helper(figure: Any, *, sections: int, respondents: int) -> Any:
    """Ask the suppression helper for a comparison over `sections` and `respondents`.

    The parameters are bound **by name** because no record settles the signature:
    a parameter naming sections gets the section count, one naming respondents
    gets the respondent count, and the one remaining required parameter gets the
    figure. A parameter this cannot fill stops with a message naming it, which is
    an interface question for the ticket rather than a guess written into a
    fixture (`tests/fixtures/report_views.py::recompute_validity`, same device).
    """
    import inspect

    helper = suppression_helper()
    values: dict[str, Any] = {}
    unfilled: list[str] = []
    for parameter in inspect.signature(helper).parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        lowered = parameter.name.lower()
        if SECTION_PARAMETER_MARK in lowered:
            values[parameter.name] = sections
        elif "respondent" in lowered:
            values[parameter.name] = respondents
        elif parameter.default is parameter.empty:
            unfilled.append(parameter.name)
    if len(unfilled) != 1:
        pytest.fail(
            f"`{helper.__name__}{inspect.signature(helper)}` leaves {unfilled} for this fixture to "
            "fill from the figure, and it can fill exactly one. It supplies a section count (a "
            "parameter naming `section`), a respondent count (one naming `respondent`) and the "
            "figure itself; a further required input is an interface question for the ticket — "
            "`call_the_helper` in tests/fixtures/report_api.py is where a spelling is taught."
        )
    values[unfilled[0]] = figure
    return helper(**values)


# ---------------------------------------------------------------------------
# Finding the two routes, and asking them.
# ---------------------------------------------------------------------------

# A path template's own parameters, `{name}` or `{name:converter}`.
PATH_PARAMETER = re.compile(r"\{([^}/:]+)(?::[^}/]+)?\}")

# How a parameter says which of the two identifiers it carries. Substrings rather
# than exact names, because the ticket settles neither spelling: `section_id`,
# `section`, `sectionId` and `course_week`, `week` all say the same thing, and a
# reader demanding one of them would be choosing the interface.
SECTION_PARAMETER_MARK = "section"
WEEK_PARAMETER_MARK = "week"


class RouteShape(NamedTuple):
    """One discovered route: its template, and which parameter carries what."""

    template: str
    path_parameters: tuple[str, ...]
    query_parameters: tuple[str, ...]
    section_parameter: str
    week_parameter: str | None

    @property
    def parameters(self) -> tuple[str, ...]:
        return (*self.path_parameters, *self.query_parameters)


def _query_parameter_names(route: Any) -> tuple[str, ...]:
    """The query parameters FastAPI computed for one route, by name.

    Read off the route's own `dependant` rather than off the endpoint's signature,
    because a signature holds dependencies and body parameters too and this suite
    needs the ones that go in the query string. The attribute is named here rather
    than reached through a `getattr` default for the reason
    `tests/fixtures/routing.py` gives about `original_router`: a FastAPI that
    renames it must fail at a constant a reader can find, not silently report a
    route as taking nothing.
    """
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        pytest.fail(
            f"The route {getattr(route, 'path', '?')!r} carries no `dependant`, so this suite "
            "cannot read the query parameters it declares. On the pinned FastAPI every "
            "`APIRoute` has one; a route object without it is a pin that has moved, and "
            "`_query_parameter_names` in tests/fixtures/report_api.py is the one place that is read."
        )
    return tuple(str(field.name) for field in (getattr(dependant, "query_params", None) or ()))


def _shape_of(route: Any) -> RouteShape:
    """One route's template and parameters, classified into the section and the week."""
    template = str(route.path)
    path_parameters = tuple(PATH_PARAMETER.findall(template))
    query_parameters = _query_parameter_names(route)
    every = (*path_parameters, *query_parameters)
    sections = [name for name in every if SECTION_PARAMETER_MARK in name.lower()]
    weeks = [name for name in every if WEEK_PARAMETER_MARK in name.lower()]
    if len(sections) != 1 or len(weeks) > 1:
        pytest.fail(
            f"The route {template!r} declares parameters {list(every)}, of which {sections} name a "
            f"section and {weeks} name a week. E4-07's two routes each name exactly one section — "
            "the report additionally names one course week — and this suite fills them by name "
            "because the ticket settles no URL. If a parameter is spelled some other way, "
            "`SECTION_PARAMETER_MARK` and `WEEK_PARAMETER_MARK` in tests/fixtures/report_api.py are "
            "the two lines that change."
        )
    return RouteShape(
        template=template,
        path_parameters=path_parameters,
        query_parameters=query_parameters,
        section_parameter=sections[0],
        week_parameter=weeks[0] if weeks else None,
    )


def _names_a_section(route: Any) -> bool:
    """Whether one route declares a parameter naming a section.

    **E4-18's list route declares none, and that is what this is for.** `GET
    /instructor/sections` answers the session's own taught sections and is handed
    nothing, so `_shape_of` — whose whole subject is which parameter carries what —
    has no section parameter to classify and fails on it by name. The routes a
    `RouteShape` describes are the two that take a section, so the list route is
    left out of the shaping rather than turning six E4-07 modules red.
    """
    template = str(route.path)
    every = (*PATH_PARAMETER.findall(template), *_query_parameter_names(route))
    return any(SECTION_PARAMETER_MARK in name.lower() for name in every)


def instructor_route_objects(application: Any) -> list[Any]:
    """The three route objects themselves, for the sweep that reads their dependency graph.

    Beside `instructor_routes` rather than inside it because two questions are
    asked of the same discovery: what a request to each route looks like (the
    shapes), and what sits in each one's dependency graph (the objects). One walk
    answers both (`docs/MISTAKES.md` entry 13).

    **Three since E4-18**, whose list route takes no parameters at all. This walk
    answers with every GET route the module mounts, because the dependency sweep
    is about all of them; `instructor_routes` shapes only the two that name a
    section.
    """
    instructor_api_module()
    found = [
        route
        for route in every_route(application)
        if "GET" in (getattr(route, "methods", None) or set())
        and getattr(getattr(route, "endpoint", None), "__module__", None) == INSTRUCTOR_API_MODULE
    ]
    if len(found) != 3:
        registered = sorted(
            f"{sorted(getattr(route, 'methods', None) or [])} {getattr(route, 'path', '?')} "
            f"({getattr(getattr(route, 'endpoint', None), '__module__', '?')})"
            for route in every_route(application)
        )
        pytest.fail(
            f"`{INSTRUCTOR_API_MODULE}` defines {len(found)} GET routes on the built application; "
            "three are shipped — E4-07's report and published-week list, and E4-18's list of the "
            "sections the session's person teaches, at `GET /instructor/sections`. The "
            f"application registers: {registered}.\n\n{ROUTER_IS_OWED}"
        )
    return found


def instructor_routes(application: Any) -> list[RouteShape]:
    """Every GET route `app.api.instructor` defines that names a section.

    **Discovered, not named.** E4-07's work order settles the module and settles
    no URL, so the module is the fact this reads and the paths are whatever the
    ticket's author registered them at — the shape
    `tests/fixtures/submit.py::submit_route` takes for E2-08's submit route.

    The walk is `fixtures.routing.every_route`, and it has to be: on the pinned
    `fastapi`, `include_router` appends a single `_IncludedRouter` carrying no
    `path` and no `endpoint`, so a walk over `application.routes` sees only what
    the factory registered directly and would answer "zero routes" with the router
    built and with it absent alike (`docs/MISTAKES.md` entry 3, and
    `docs/disputes/E2-04-01.md`). The flattening widens nothing: an application
    whose routers were never registered appends no `_IncludedRouter` to recurse
    into, so a module that defines routes nothing registers still fails here.
    """
    return [
        _shape_of(route)
        for route in instructor_route_objects(application)
        if _names_a_section(route)
    ]


def report_route(application: Any) -> RouteShape:
    """The instructor route that names a course week: the report itself."""
    named = [shape for shape in instructor_routes(application) if shape.week_parameter]
    if len(named) != 1:
        pytest.fail(
            f"{len(named)} of the `{INSTRUCTOR_API_MODULE}` routes naming a section name a course "
            f"week ({[shape.template for shape in named]}). E4-07's report is 'the report for "
            "(section, course week)' and the other is the published-week list for a section, so "
            "exactly one of the two takes a week and that is how they are told apart here. "
            "E4-18's list route names no section and is not among them."
        )
    return named[0]


def published_weeks_route(application: Any) -> RouteShape:
    """The instructor route that names no course week: the published-week list."""
    named = [shape for shape in instructor_routes(application) if not shape.week_parameter]
    if len(named) != 1:
        pytest.fail(
            f"{len(named)} of the `{INSTRUCTOR_API_MODULE}` routes naming a section name no week "
            f"({[shape.template for shape in named]}). See `report_route`."
        )
    return named[0]


def request_for(
    shape: RouteShape, *, section_id: Any, course_week: int | None = None
) -> tuple[str, dict[str, Any]]:
    """The URL and query parameters one request to a discovered route is made with.

    The section travels in the path where the route declares a path parameter for
    it and in the query string where it declares none — both are reasonable
    spellings and E4-07 settles neither, so tolerating the two is what keeps a
    stylistic choice from reddening every test in this ticket
    (`tests/fixtures/submit.py::submission_request` says the same).
    """
    values: dict[str, Any] = {shape.section_parameter: section_id}
    if shape.week_parameter is not None:
        if course_week is None:
            pytest.fail(
                f"The route {shape.template!r} names a course week ({shape.week_parameter}) and this "
                "call supplied none."
            )
        values[shape.week_parameter] = course_week
    url = shape.template
    for name in shape.path_parameters:
        url = re.sub(r"\{" + re.escape(name) + r"(?::[^}/]+)?\}", str(values[name]), url)
    query = {name: values[name] for name in shape.query_parameters if name in values}
    return url, query


# ---------------------------------------------------------------------------
# Reading a payload without holding a copy of its schema.
# ---------------------------------------------------------------------------


def member(body: Any, *path: str, answered: Any = None) -> Any:
    """One member of a decoded payload, by the path the README sketch puts it at.

    A named failure rather than a `KeyError`, because a missing member is exactly
    what a red on this ticket looks like before the schema exists and a traceback
    out of a subscript names nothing. The sketch is quoted in the message so a
    reader can tell a missing member from a renamed one, which is criterion 8's
    difference between a divergence and a defect.
    """
    here: Any = body
    walked: list[str] = []
    for name in path:
        if not isinstance(here, dict) or name not in here:
            available = sorted(here) if isinstance(here, dict) else repr(here)
            pytest.fail(
                f"The report payload carries no `{'.'.join(path)}`: at `{'.'.join(walked) or '.'}` "
                f"it holds {available}.\n\n"
                "`docs/tickets/e4/README.md`'s payload sketch is the contract E4-08 through E4-11 "
                "build fixtures against, and breakdown decision 5 makes E4-07's schema the "
                "authority over it — a member spelled differently is a divergence the pull request "
                "lists (criterion 8), not a rename these tests should absorb quietly."
                + (f"\n\nBody begins {answered.text[:400]!r}." if answered is not None else "")
            )
        here = here[name]
        walked.append(name)
    return here


def stream_member(body: Any, stream: str, *path: str, answered: Any = None) -> Any:
    """One member under `streams.<instructor|course>`, by the sketch's spelling."""
    return member(body, STREAMS_MEMBER, PAYLOAD_STREAM_KEY[stream], *path, answered=answered)


def every_object(node: Any) -> list[dict[str, Any]]:
    """Every JSON object anywhere inside a decoded payload, at any depth.

    Used by the denial modules: "no comment carries a timestamp, a week or an
    author" is a claim about every object under the comment members, and a reader
    that indexed a fixed path would be silent about a field added one level down.
    """
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        found.append(node)
        for value in node.values():
            found.extend(every_object(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(every_object(item))
    return found


def strings_in(node: Any) -> list[str]:
    """Every string anywhere inside a decoded payload."""
    return [value for value in scalars_in(node) if isinstance(value, str)]


# ---------------------------------------------------------------------------
# The world, and the premises it rests on.
# ---------------------------------------------------------------------------


def a_day_the_student_is_already_enrolled_on() -> date:
    """The day the refused-role student's enrolment starts, against the real clock.

    See `STUDENT_ENROLLED_SINCE_DAYS`. Computed rather than written as a literal,
    because the value that has to be in the past is in the past *when the test
    runs* — a literal would be correct on the day it was written and wrong later,
    which is the failure `tests/fixtures/report_comments.py` avoids from the other
    end by dating its windows in 2020 and 2099.

    This student is a session to be refused and nothing else: she reads no report,
    and her enrolment exists so that E1-13's landing has something to resolve her
    to. Which section she is enrolled in is `landing_ground`'s choice and is not
    this world's taught section, deliberately — the refusal under test is by role,
    and a student enrolled in the section under test would let a 404 stand in for
    the 401 this asserts.
    """
    return datetime.now(UTC).date() - timedelta(days=STUDENT_ENROLLED_SINCE_DAYS)


def assert_the_cohort_is_what_this_file_says() -> None:
    """`COURSE_WEEK_OF_TERM_WEEK` against the transcribed seed, before anything reads it.

    The mapping above is written out by hand precisely so that it is not the
    arithmetic the payload does (`docs/MISTAKES.md` entry 19); this is what keeps
    the literals honest if `scripts/seed.py`'s start-letter map ever moves under
    them. Called from `build_report_world`, which every module reaches, so a
    stale table is a failure naming it rather than six failures about course
    weeks.
    """
    length, first_term_week, _start = SEEDED_COHORTS[TAUGHT_COHORT]
    assert (length, first_term_week) == (TAUGHT_LENGTH_WEEKS, TAUGHT_TERM_WEEKS[0]), (
        f"Cohort {TAUGHT_COHORT!r} runs {length} weeks from term week {first_term_week} in "
        f"`SEEDED_COHORTS`, and this file's hand-written table says {TAUGHT_LENGTH_WEEKS} weeks "
        f"from term week {TAUGHT_TERM_WEEKS[0]}. `COURSE_WEEK_OF_TERM_WEEK` in "
        "tests/fixtures/report_api.py is the table to correct, and it is written out rather than "
        "derived on purpose."
    )


def assert_the_leaver_straddles_the_boundary() -> None:
    """`LEAVER_ENDED_ON` between the two windows the denominator pair is driven over.

    ADR 0147's re-homed criterion 5 is "a student enrolled weeks 1-3 of a 6-week
    section is in week 2's denominator and not week 5's", so a leaving date on the
    wrong side of either window makes both halves of the pair assert nothing while
    one of them still passes. The instants come from
    `tests/fixtures/survey_windows.py`'s hand-written calendar.

    **Two claims, not one, and the second was added after the first caught a
    defect this file shipped.** The outer bounds — after course week 3's window
    closes, before course week 5's opens — are what the *asserted* pair needs. The
    inner bound, before course week 4's window opens, is what the world's own
    description needs: it is the difference between a leaver who was there for
    weeks 1-3 and one who was also there for week 4, and the second is not what
    `ENROLLED_WITH_THE_LEAVER` and this module's docstring say this world is. A
    check stating only what the assertions read would let the constant drift into
    week 4 in silence.
    """
    closed = WINDOWS_BY_TERM_WEEK[TERM_WEEK_OF_COURSE_WEEK[FIRST_HELD_WEEK]][1]
    next_opens = WINDOWS_BY_TERM_WEEK[TERM_WEEK_OF_COURSE_WEEK[SECOND_HELD_WEEK]][0]
    opens = WINDOWS_BY_TERM_WEEK[TERM_WEEK_OF_COURSE_WEEK[OUT_OF_DENOMINATOR_WEEK]][0]
    assert closed.date() <= LEAVER_ENDED_ON < opens.date(), (
        f"The leaver's enrolment ends on {LEAVER_ENDED_ON}, and course week 3's window closes "
        f"{closed.date()} while course week 5's opens {opens.date()}. The pair is only a boundary "
        "if the date sits between them — otherwise one half of it is true for a reason that has "
        "nothing to do with the enrolment window.\n\n"
        "A date chosen from the institution's wall clock lands one day early, which is how this "
        "constant was first written: the Sunday a window closes on locally is the Monday it closes "
        "on in UTC, and every instant this world writes is UTC."
    )
    assert next_opens.date() > LEAVER_ENDED_ON, (
        f"The leaver's enrolment ends on {LEAVER_ENDED_ON} and course week 4's window opens "
        f"{next_opens.date()}, so she is enrolled for part of course week 4 as well. This world is "
        "described everywhere — this module's docstring, `ENROLLED_WITH_THE_LEAVER` in the rates "
        "suite, the pair's own failure messages — as one where six people are enrolled across "
        "course weeks 1-3 and five across 4-6, and a leaver inside week 4 makes that description "
        "false for a week no assertion here reads."
    )


class ReportWorldRows:
    """The rows one instructor's Monday report is read over, and who they belong to.

    A thin record beside `CommentWorld` rather than a subclass of it: everything
    about the term, the section, the question set, the windows and the answers is
    E4-03's and E4-04's fixture machinery and is not re-implemented here. What
    this holds is the handful of keys a test needs to name — the two sections, the
    respondents, the leaver — and the arithmetic-free readers over them.
    """

    def __init__(self, world: CommentWorld) -> None:
        self.world = world
        self.respondents: list[Any] = []
        self.leaver: Any = None

    @property
    def session(self) -> Any:
        return self.world.session

    @property
    def taught_section_id(self) -> Any:
        return self.world.section_id(TAUGHT_COHORT)

    @property
    def untaught_section_id(self) -> Any:
        return self.world.section_id(UNTAUGHT_COHORT)

    @property
    def term_id(self) -> Any:
        return self.world.term_id()

    def week_id(self, course_week: int) -> Any:
        return self.world.week_id(TERM_WEEK_OF_COURSE_WEEK[course_week])

    def responses_in(self, course_week: int) -> int:
        """How many `response` rows the database holds for one course week.

        Read back rather than assumed, for the reason
        `tests/fixtures/report_comments.py::responses_in` gives: a planted "week
        of five" that seeded four satisfies every threshold assertion in these
        suites for the wrong reason.
        """
        return self.world.responses_in(term_week=TERM_WEEK_OF_COURSE_WEEK[course_week])

    def enrolled_user_ids(self) -> list[Any]:
        """Every `user` key this world enrolled, respondents and leaver alike."""
        key = self.world.key_of(USER_TABLE)
        return [row[key] for row in (*self.respondents, self.leaver) if row is not None]

    def stored_response_ids(self) -> list[Any]:
        """Every `response` key in this world's taught section, for the denial sweeps."""
        from sqlalchemy import select

        table = require_table(self.world.tables, RESPONSE_TABLE)
        key = single_primary_key(table)
        self.session.flush()
        statement = select(table.c[key]).where(
            table.c[RESPONSE_SECTION_COLUMN] == self.taught_section_id
        )
        return list(self.session.execute(statement).scalars())


def a_student_enrolled(
    world: CommentWorld, subject: str, *, started_on: date, ended_on: date | None
) -> Any:
    """One `user` enrolled in the taught section over the window the caller chose.

    `CommentWorld.student` seeds an enrolment that never ends, which is right for
    an ordinary respondent and is exactly what ADR 0147's re-homed criterion 5
    cannot use: the boundary is *which* weeks an enrolment covers. So the window
    is always the caller's here, the way `tests/fixtures/landing.py::enrol` keeps
    it the caller's and for the same reason (`docs/MISTAKES.md` entry 30).
    """
    user = world.seed(USER_TABLE, world.people_chain, lms_user_id=subject)
    world.seed(
        ENROLLMENT_TABLE,
        {},
        **{
            world.link(ENROLLMENT_TABLE, USER_TABLE): user[world.key_of(USER_TABLE)],
            world.link(ENROLLMENT_TABLE, SECTION_TABLE): world.section_id(TAUGHT_COHORT),
            STARTED_ON_COLUMN: started_on,
            ENDED_ON_COLUMN: ended_on,
        },
    )
    return user


def build_report_world(world: CommentWorld) -> ReportWorldRows:
    """Seed the canonical world this ticket is measured over, and answer its keys.

    Six closed course weeks at SPEC §3.1's own Fall 2026 instants, two sections,
    five respondents and one leaver — see this module's docstring for what each
    week is for. Everything is an *input*: no rate, no denominator, no course-week
    number and no published-week list is computed here.
    """
    assert_the_cohort_is_what_this_file_says()
    assert_the_leaver_straddles_the_boundary()

    world.build(cohort=TAUGHT_COHORT)
    world.section(UNTAUGHT_COHORT)

    # Every window carries the hand-written calendar's instants, so which weeks are
    # published is a question about where the clock is and about nothing else.
    for term_week in TAUGHT_TERM_WEEKS:
        world.instants[term_week] = WINDOWS_BY_TERM_WEEK[term_week]
        world.window(term_week, TAUGHT_COHORT)

    rows = ReportWorldRows(world)
    _length, _first, section_starts = SEEDED_COHORTS[TAUGHT_COHORT]
    rows.respondents = [
        a_student_enrolled(
            world, f"e4-07-respondent-{index}", started_on=section_starts, ended_on=None
        )
        for index in range(RESPONDENTS)
    ]
    rows.leaver = a_student_enrolled(
        world, "e4-07-leaver", started_on=section_starts, ended_on=LEAVER_ENDED_ON
    )

    for course_week, answering in ANSWERED_BY.items():
        term_week = TERM_WEEK_OF_COURSE_WEEK[course_week]
        for place, index in enumerate(answering):
            comments: dict[str, str] = {}
            ratings: dict[int, Any] = {}
            if course_week == FULL_WEEK:
                comments[INSTRUCTOR_STREAM] = FULL_WEEK_COMMENTS[place]
                ratings = {
                    RATING_POSITION[COURSE_STREAM]: FULL_WEEK_COURSE_RATINGS[place],
                    WORKLOAD_POSITION: FULL_WEEK_WORKLOAD_HOURS[place],
                }
                # A `None` is a question left unanswered, so no `answer` row is
                # written for it at all — see `FULL_WEEK_INSTRUCTOR_RATINGS`.
                if FULL_WEEK_INSTRUCTOR_RATINGS[place] is not None:
                    ratings[RATING_POSITION[INSTRUCTOR_STREAM]] = FULL_WEEK_INSTRUCTOR_RATINGS[
                        place
                    ]
            elif course_week in HELD_COMMENTS:
                comments[INSTRUCTOR_STREAM] = HELD_COMMENTS[course_week][place]
                ratings = {RATING_POSITION[INSTRUCTOR_STREAM]: 3}
            else:
                ratings = {RATING_POSITION[INSTRUCTOR_STREAM]: 4}
            world.submit(
                term_week=term_week,
                comments=comments or None,
                ratings=ratings,
                cohort=TAUGHT_COHORT,
                student=rows.respondents[index],
            )
    return rows


# ---------------------------------------------------------------------------
# The door: a real launch, a real session, and reads made with it.
# ---------------------------------------------------------------------------

# The three roles a test can stand at this door as, and where each lands. The
# roles are `tests/fixtures/supervision.py::ROLE_ALIASES`' spellings; the landings
# are E1-04's route groups. A launch that lands anywhere else is a launch whose
# session is somebody else's, which `session_token_at` refuses outright.
INSTRUCTOR_ROLE = "INSTRUCTOR"
LEADERSHIP_ROLE = "DEAN"
STUDENT_ROLE = "STUDENT"

LANDING_FOR = {
    INSTRUCTOR_ROLE: INSTRUCTOR_LANDING,
    LEADERSHIP_ROLE: LEADERSHIP_LANDING,
    STUDENT_ROLE: STUDENT_LANDING,
}


class ReportDoor:
    """One tool, one session of a chosen role, and reads of E4-07's two routes.

    Six modules drive the same three things — a read as the teaching instructor, a
    read of a section that is not hers, and a read as somebody who is not an
    instructor — so the driving lives here and each module asserts
    (`docs/MISTAKES.md` entry 13).
    """

    def __init__(self, driver: Any, rows: ReportWorldRows, overrides: Any, token: str) -> None:
        self.driver = driver
        self.tool = driver.tool
        self.rows = rows
        self.world = rows.world
        self.overrides = overrides
        self.token = token

    @property
    def application(self) -> Any:
        """The FastAPI application this tool is serving, for the route discovery."""
        return self.tool.app

    def pretend(self, instant: datetime) -> None:
        """Move the development clock to `instant`, committed, as `POST /dev/clock` does.

        The caller names the instant: which side of a window's close the clock
        sits on is the whole of criterion 3.
        """
        self.overrides.set(pretend_now=instant, anchored_at=datetime.now(UTC))

    def commit(self) -> None:
        """Make everything seeded since the last commit visible to the tool's connection."""
        self.world.session.commit()

    def refresh(self) -> None:
        """End this session's transaction, so a read after an HTTP call sees the database.

        The same rollback `tests/fixtures/student_read.py::stored_answer_values`
        takes, and for the same reason: this connection has been open since it
        seeded, and anything the tool or a service committed happened on another
        one — so a read inside the old snapshot answers about a database that has
        moved.
        """
        self.world.session.rollback()

    @contextmanager
    def carrying_no_cookie(self) -> Iterator[None]:
        """Empty this client's cookie jar for the body, and put it back afterwards.

        Without it no request here is credential-free: E1-08 delivers a session as
        a `Set-Cookie` on the landing redirect *as well as* in the URL fragment,
        and `httpx` sends jar cookies on every later request to the same host — so
        a read made through the client the launch was driven with carries that
        person's session whether or not it carries a header, and a request meant to
        be refused is answered. `docs/disputes/E2-09-01.md` measured it. A
        per-request `cookies={}` does not do it, because `httpx` merges request
        cookies *over* the jar rather than replacing it.
        """
        import httpx

        jar = self.tool.cookies
        self.tool.cookies = httpx.Cookies()
        try:
            yield
        finally:
            self.tool.cookies = jar

    # -- the two routes -------------------------------------------------------

    def report(self, *, course_week: int, section_id: Any = None) -> Any:
        """One read of the report route for one section and one course week."""
        shape = report_route(self.application)
        url, query = request_for(
            shape,
            section_id=self.rows.taught_section_id if section_id is None else section_id,
            course_week=course_week,
        )
        return self.tool.get(url, params=query or None, headers=self.credential())

    def published_weeks(self, *, section_id: Any = None) -> Any:
        """One read of the published-week list for one section."""
        shape = published_weeks_route(self.application)
        url, query = request_for(
            shape, section_id=self.rows.taught_section_id if section_id is None else section_id
        )
        return self.tool.get(url, params=query or None, headers=self.credential())

    def credential(self) -> dict[str, str]:
        """This session as a Bearer token.

        Bearer rather than the cookie, because ADR 0089 makes it the path the SPA
        actually uses — "the SPA captures the fragment into `sessionStorage` … and
        sends it as `Authorization: Bearer` thereafter" — and
        `session_from_request` reads the Bearer header before the cookie.
        """
        return {"authorization": f"{AUTHENTICATE_SCHEME} {self.token}"}

    # -- reading an answer ----------------------------------------------------

    def payload(self, *, course_week: int, section_id: Any = None) -> tuple[Any, Any]:
        """The report for one course week, and the response it came in.

        The status is asserted here rather than in every caller, because a body
        decoded off a refusal is a body every later assertion is vacuously true of
        (`docs/MISTAKES.md` entry 3).
        """
        answered = self.report(course_week=course_week, section_id=section_id)
        assert answered.status_code == 200, (
            f"The report for course week {course_week} answered {answered.status_code} rather than "
            f"200 for the section this session teaches. Body begins {answered.text[:400]!r}."
        )
        return decoded(answered, f"The report for course week {course_week}"), answered


def _seed_the_launching_person(
    *, role: str, rows: ReportWorldRows, platform_id: Any, subject: str, identity: Any, graph: Any
) -> dict[str, Any]:
    """The rows that make a launching subject the person a test needs them to be.

    An `INSTRUCTOR` assignment is written **against this world's own taught
    section**, because that is what the `teaching_instructor` view answers over
    and what E4-07's scope query reads: `record_teaching_instructor` writes
    exactly this row (`tests/integration/test_the_roster_definers_answer_a_point_
    query_and_nothing_more.py`), and a fresh scope would make her an instructor of
    somebody else's section.

    `DEAN` is scoped where SPEC §2.1 puts it and deliberately not at this world's
    college: the leadership refusal under test is a refusal **by role**, which the
    401 tells apart from the 404 an out-of-scope section gets, so a purview that
    contained the section would prove the same thing and cost a containment walk.
    Leadership's read of this report is E9's drill-down, not this route.
    """
    person_id = identity.person()
    user_id = identity.user(platform_id=platform_id, subject=subject)
    identity.link_person_to_user(person_id=person_id, user_id=user_id)
    if role == INSTRUCTOR_ROLE:
        graph.assign(INSTRUCTOR_ROLE, scope=rows.taught_section_id, person=person_id)
    else:
        graph.assign(role, person=person_id)
    return {"person_id": person_id, "user_id": user_id}


def _build_report_door(
    role: str,
    launch_driver: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    committed_clock_overrides: Any,
    web_identity: Any,
    landing_ground: Any,
) -> ReportDoor:
    """Seed the world, make the launcher who they are, move the clock, launch — in that order.

    Every step is somebody's existing machinery: the platform is registered and the
    launch is real (`launch_driver`), the subject is read off the launch the
    platform signs rather than copied out of `mock-lms/app/seed.py`, the rows are
    committed because the tool connects for itself (ADR 0001), and the clock is
    moved **before** the launch so the enrolment a student landing rests on is
    judged against the day this world lives in.
    """
    committed_rows.session.info["environment"] = DEVELOPMENT
    world = CommentWorld(Fall2026(committed_rows.seed, committed_rows.session, metadata_tables))
    rows = build_report_world(world)
    committed_rows.commit()

    urn = LEARNER_ROLE_URN if role == STUDENT_ROLE else INSTRUCTOR_ROLE_URN
    offer = launch_driver.offer_for_role(urn)
    claims = launch_driver.claims_of(offer)
    subject = claims.get("sub")
    assert isinstance(subject, str) and subject, (
        f"The {role} launch this platform signs carries no `sub`, so there is no subject to seed a "
        f"`user` row for and no session to read as. The claims it signed: {sorted(claims)}."
    )
    platform_id = launch_driver.registration.platform_row[
        single_primary_key(require_table(metadata_tables, "lti_platform"))
    ]

    overrides = committed_clock_overrides
    overrides.set(pretend_now=AFTER_THE_LAST_WINDOW, anchored_at=datetime.now(UTC))

    if role == STUDENT_ROLE:
        landing_ground().a_student(
            platform_id=platform_id, subject=subject, on=a_day_the_student_is_already_enrolled_on()
        )
    else:
        _seed_the_launching_person(
            role=role,
            rows=rows,
            platform_id=platform_id,
            subject=subject,
            identity=web_identity,
            graph=committed_rows.graph,
        )
    committed_rows.commit()

    landed, _ = launch_driver.launch(offer)
    token = session_token_at(landed, LANDING_FOR[role], f"The seeded {role} launch")
    return ReportDoor(launch_driver, rows, overrides, token)


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------


@pytest.fixture
def report_door_as(
    launch_driver_in: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    committed_clock_overrides: Any,
    web_identity: Any,
    landing_ground: Any,
) -> Callable[[str], ReportDoor]:
    """The door, stood at as a role the caller names. See `_build_report_door`.

    A factory, because criterion 2 is "a student session and a leadership session
    are both refused these routes … driven per role", and a fixture that picked
    one role would make the other's test a copy of this file rather than a drive
    through it.
    """

    def build(role: str = INSTRUCTOR_ROLE) -> ReportDoor:
        return _build_report_door(
            role,
            launch_driver_in(),
            committed_rows,
            metadata_tables,
            committed_clock_overrides,
            web_identity,
            landing_ground,
        )

    return build


@pytest.fixture
def report_door(report_door_as: Callable[[str], ReportDoor]) -> ReportDoor:
    """The teaching instructor at the door, with her own section and one that is not hers."""
    return report_door_as(INSTRUCTOR_ROLE)


@pytest.fixture
def report_api_contract() -> Any:
    """The names E4-07's work order settles, and the readers over them.

    Handed over as a fixture rather than imported, for the reason every fixtures
    module in this suite gives: importing a fixtures module by name depends on
    where pytest put `tests/` on `sys.path`, and an import error is not a red.
    """

    class ReportApiContract:
        api_module = INSTRUCTOR_API_MODULE
        deps_module = DEPS_MODULE
        require_instructor_name = REQUIRE_INSTRUCTOR
        reporting_module_name = REPORTING_MODULE
        schema_module_name = REPORT_SCHEMA_MODULE

        minimum_names = BENCHMARK_MINIMUMS
        minimum_sections = BENCHMARK_MIN_SECTIONS
        minimum_respondents = BENCHMARK_MIN_RESPONDENTS

        section_member = SECTION_MEMBER
        week_member = WEEK_MEMBER
        rates_member = RATES_MEMBER
        streams_member = STREAMS_MEMBER
        workload_member = WORKLOAD_MEMBER
        comparison_member = COMPARISON_MEMBER
        small_n_member = SMALL_N_MEMBER
        released_member = RELEASED_MEMBER

        course_week_field = COURSE_WEEK_FIELD
        term_week_field = TERM_WEEK_FIELD
        published_weeks_field = PUBLISHED_WEEKS_FIELD
        response_rate_field = RESPONSE_RATE_FIELD
        validity_rate_field = VALIDITY_RATE_FIELD
        responses_field = RESPONSES_FIELD
        valid_responses_field = VALID_RESPONSES_FIELD
        enrolled_field = ENROLLED_FIELD
        trend_field = TREND_FIELD
        distribution_field = DISTRIBUTION_FIELD
        summary_field = SUMMARY_FIELD
        comments_field = COMMENTS_FIELD
        trend_mean_field = TREND_MEAN_FIELD
        suppressed_field = SUPPRESSED_FIELD
        comment_fields_permitted = COMMENT_FIELDS_PERMITTED

        out_of_scope_status = OUT_OF_SCOPE_STATUS
        role_refused_status = ROLE_REFUSED_STATUS
        authenticate_header = AUTHENTICATE_HEADER
        authenticate_scheme = AUTHENTICATE_SCHEME

        instructor_stream = INSTRUCTOR_STREAM
        course_stream = COURSE_STREAM
        payload_stream_key = PAYLOAD_STREAM_KEY

        api = staticmethod(instructor_api_module)
        reporting = staticmethod(reporting_module)
        schema = staticmethod(report_schema_module)
        require_instructor = staticmethod(require_instructor_dependency)
        minimums = staticmethod(configured_benchmark_minimums)
        comparison_type = staticmethod(comparison_field_type)
        helper = staticmethod(suppression_helper)
        call_helper = staticmethod(call_the_helper)
        routes = staticmethod(instructor_routes)
        route_objects = staticmethod(instructor_route_objects)
        a_section_that_does_not_exist = staticmethod(a_section_that_does_not_exist)
        report_route = staticmethod(report_route)
        published_weeks_route = staticmethod(published_weeks_route)
        request_for = staticmethod(request_for)
        member = staticmethod(member)
        stream_member = staticmethod(stream_member)
        every_object = staticmethod(every_object)
        strings_in = staticmethod(strings_in)

    return ReportApiContract()


def a_section_that_does_not_exist() -> Any:
    """A section key nothing seeded — the second half of criterion 1's refusal pair.

    A fresh uuid rather than a mangled one, because ADR 0016 makes every key a
    uuid and a malformed value is refused by the route's own parsing before any
    scope query runs — which would make the pair a comparison between a validation
    error and a scope refusal rather than between two scope refusals.
    """
    return uuid4()
