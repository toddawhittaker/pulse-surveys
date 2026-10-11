"""E7-02 — the hold: the policy of record, the student's week state, the one writer, the route.

Six test modules ask the same route and the same two writers the same questions,
so the driving lives here and each module asserts (`docs/MISTAKES.md` entry 13).
Nothing in this repository answers any of it yet.

**The names E7-02's work order settles, transcribed once** (its "Settled
decisions"):

  - decision 1: `response_policy.course_id` (M2, ADR 0193), and the writer
    `app.services.response_loop.record_policy(session, *, setter_person_id, role,
    prefix_id, mode)`, which writes one row per course the setter is responsible
    for in the prefix and returns the rows;
  - decision 2: the policy of record for a section-week is the latest row by
    `sequence` for the section's course with `set_at <= report_opens_at(...)`;
    none is encouraged;
  - decision 3: the four states `awaiting`, `published`, `on-behalf`,
    `unanswered`; `on-behalf` iff the first row's role is `LEAD_FACULTY` or
    `CHAIR`; the text is the latest row's, the author the first row's;
  - decision 4: the route `GET …/student/sections/{section_id}/weeks/{course_week}/results`
    in `app.api.student`, answering `StudentWeekResults {state, response}` with
    `StudentResponse {text, author_name, author_role, published_at}`, `response`
    `None` for `awaiting` and `unanswered`;
  - decision 5: every refusal is one 404 carrying one sentence from
    `app/copy/response_loop.py`;
  - decision 6: the writer `publish_response(session, *, section_id, course_week,
    author_person_id, role, ai_seeded, body) -> InstructorResponse`;
  - decision 7: both writers stamp their time from `services/clock.now`.

**What the work order leaves open, and this file therefore does not choose.**
Which module holds the two payload classes (`app.schemas.response_loop` or
`app.schemas.student`; both are looked in). Which row's `published_at` and which
row's `author_role` the payload carries when a section-week has more than one row:
no test here asserts either across an edit. How the writer refuses what the table
refuses (any exception is a refusal; a `TypeError` is an interface mismatch).

**The world** is E7-01's (`tests/fixtures/staff_names.py`), which is E6-05's
lead-review world with every staff member named: one prefix holding the own
course (sections `F1WW`, taught by `TEACHER_NAME`, and `Q1WW`, taught by
`SIBLING_SECTION_TEACHER_NAME`), the sibling course (cohort `Y`, its own lead) and
the unmapped course (cohort `4`, no lead, so it falls to the chair). All four
cohorts start on 2026-09-28, in term week 7, so course week N is term week
`TERM_WEEK_OF_COURSE_WEEK[N]` in every one of them and its report opens at
`REPORT_OPENS_BY_TERM_WEEK` of that term week (`tests/fixtures/report_api.py`, written
by hand and checked against the calendar there).

**The calendar, and why nothing here is dated from today.** Every enrollment
starts on its section's first day (2026-09-28) and an ended one ends on
`ENDED_ON` (2026-10-01): both in the past under the real clock on any day these
tests run and under every instant this file pretends. So whether the route judges
a live enrollment against the development clock or the staff-name definer judges
it against the database's own date, both readings agree (`staff_names`' module
docstring raises exactly that question). Every pretended instant is a fixed 2026
instant counted from a report opening, never from today (the calendar bomb the
ticket names).

**Students are minted, not launched.** The mock platform offers one learner, so a
second launched student is not available; a minted `STUDENT` session naming a
`user` and no person is what a launch issues (ADR 0028), minted through E6-05's
`LeadReviewWorld.minted` exactly as `tests/fixtures/named_sets.py` mints one.

**Every policy and response row is written by somebody who holds the role**,
because E7-01's guard triggers refuse anybody else on every connection, and M2's
amended trigger refuses a policy row whose setter is not responsible for its
course. The seeding writes as the superuser and names every column, so a row's
`set_at` or `published_at` is the instant a test chose, to the second.

**Every read is made through the built application** (which connects as
`pulse_app`) or on `application_session`, never on the superuser that seeds
(`docs/MISTAKES.md` entry 46). Every guard on a deliverable is a plain function
called from a test body, so an unbuilt tree is a FAILED naming it, never an ERROR
in setup (entry 44). **Nothing here decides an answer**: it plants, calls and
reads back, and every expectation is written in the test that makes it (entries
19 and 30).
"""

import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from importlib import import_module
from typing import Any, NamedTuple
from uuid import uuid4

import pytest

from fixtures.lead_review import SIBLING_COHORT, UNMAPPED_COHORT, LeadReviewWorld
from fixtures.report_api import (
    CLEAR_OF_AN_OPENING,
    REPORT_OPENS_BY_TERM_WEEK,
    TAUGHT_COHORT,
    TERM_WEEK_OF_COURSE_WEEK,
    UNTAUGHT_COHORT,
    assert_the_report_openings_are_what_this_file_says,
)
from fixtures.routing import every_route
from fixtures.staff_names import (
    AI_SEEDED_COLUMN,
    INSTRUCTOR_RESPONSE,
    MODE_COLUMN,
    POLICY_COURSE_COLUMN,
    POLICY_PREFIX_COLUMN,
    POLICY_SETTER_COLUMN,
    POLICY_TIME_COLUMN,
    RESPONSE_AUTHOR_COLUMN,
    RESPONSE_BODY_COLUMN,
    RESPONSE_POLICY,
    RESPONSE_SECTION_COLUMN,
    RESPONSE_TERM_COLUMN,
    RESPONSE_TIME_COLUMN,
    ROLE_COLUMN,
    SEQUENCE_COLUMN,
    WEEK_COLUMN,
    Person,
    StaffNameWorld,
    require_the_tables,
)
from fixtures.student_read import decoded, scalars_in
from fixtures.submit import COPY_MAPPING_NAME, COPY_MODULES_FUNCTION, COPY_PACKAGE, served_text
from fixtures.supervision import foreign_key_columns, require_table, single_primary_key
from fixtures.survey_windows import SEEDED_COHORTS

# ---------------------------------------------------------------------------
# The names E7-02's work order settles, spelled once.
# ---------------------------------------------------------------------------

# Decision 4: the route's module, its path ending, and its two path parameters.
STUDENT_API_MODULE = "app.api.student"
RESULTS_ENDING = "/results"
SECTION_PARAMETER = "section_id"
WEEK_PARAMETER = "course_week"

# Decision 4: the payload, exactly.
STATE = "state"
RESPONSE = "response"
# The amendment before review, A1: the section's course weeks whose report has
# opened at `now`, ascending, in every state (E7-06's page pages through them).
PUBLISHED_WEEKS = "published_weeks"
PAYLOAD_MEMBERS = frozenset({STATE, RESPONSE, PUBLISHED_WEEKS})
# E8-01's work order adds four members, on every state: the course label, the two
# streams, the workload median and the release group (each of the last three
# `None` on a held week); E8-03 adds `participation`, in parallel. They are
# **admitted** here by name and required by nothing in this file, so an E7 test
# goes red only for an E7 reason: E8-01's tests require their members through
# `tests/fixtures/student_week.py::read`, and E8-03's member is that ticket's to
# assert (`docs/MISTAKES.md` entry 22: a new member reaches every fixture).
E8_01_MEMBERS = frozenset({"course_label", "streams", "workload_median", "released"})
MEMBERS_LATER_TICKETS_ADD = E8_01_MEMBERS | frozenset({"participation"})
TEXT = "text"
AUTHOR_NAME = "author_name"
AUTHOR_ROLE = "author_role"
PUBLISHED_AT = "published_at"
RESPONSE_MEMBERS = frozenset({TEXT, AUTHOR_NAME, AUTHOR_ROLE, PUBLISHED_AT})

# Decision 3 (the ticket's "The student's state"): the four states, spelled.
AWAITING = "awaiting"
PUBLISHED = "published"
ON_BEHALF = "on-behalf"
UNANSWERED = "unanswered"
STATES = (AWAITING, PUBLISHED, ON_BEHALF, UNANSWERED)

# Decision 4: the roles an author is shown under, and the payload classes.
AUTHOR_ROLES = ("INSTRUCTOR", "LEAD_FACULTY", "CHAIR")
RESULTS_SCHEMA = "StudentWeekResults"
RESPONSE_SCHEMA = "StudentResponse"
# The ticket owns `schemas/response_loop.py` (new) and `schemas/student.py` "if
# the route's payload sits there"; which one is the implementer's.
SCHEMA_HOMES = ("app.schemas.response_loop", "app.schemas.student")

# Decision 5: one 404, one sentence, in this module.
REFUSED_STATUS = 404
COPY_MODULE = "app.copy.response_loop"

# Decisions 1 and 6: the two writers, and the model the first returns.
SERVICE_MODULE = "app.services.response_loop"
PUBLISH_WRITER = "publish_response"
POLICY_WRITER = "record_policy"
MODEL_MODULE = "app.models.loop"
RESPONSE_MODEL = "InstructorResponse"

# The vocabularies E7-01 settled.
INSTRUCTOR = "INSTRUCTOR"
LEAD_FACULTY = "LEAD_FACULTY"
CHAIR = "CHAIR"
REQUIRED = "REQUIRED"
ENCOURAGED = "ENCOURAGED"

# The landing role a minted student session carries (`LandingRole.STUDENT`).
STUDENT_LANDING_ROLE = "STUDENT"

# M2's guard: a policy row's course, and the migration it chains from.
M2_DOWN_REVISION = "2c3d5a0de424"

# What a refusal may not be: the statement naming something that is not there.
NOT_A_REFUSAL = ("42703", "42P01")

ROUTE_IS_OWED = (
    "E7-02's work order (decision 4) settles one route in `app.api.student`, behind "
    "`require_student`: `GET …/student/sections/{section_id}/weeks/{course_week}/results`, "
    "answering `StudentWeekResults {state, response, published_weeks}` (the last is the "
    "amendment's A1) for one of the student's own sections and "
    "one published course week, through the student's live enrollment."
)
WRITERS_ARE_OWED = (
    f"E7-02's work order settles two writers in `{SERVICE_MODULE}`: decision 6's "
    f"`{PUBLISH_WRITER}(session, *, section_id, course_week, author_person_id, role, ai_seeded, "
    f"body) -> {RESPONSE_MODEL}`, which appends one row and nothing else, and decision 1's "
    f"`{POLICY_WRITER}(session, *, setter_person_id, role, prefix_id, mode)`, which writes one "
    "row per course `authz.lead_review_courses` gives the setter in the prefix and returns them."
)
M2_IS_OWED = (
    "E7-02's work order (decision 1) gives M2 to this ticket: `response_policy.course_id`, NOT "
    "NULL, a foreign key to `course` with `RESTRICT`, the course held in the row's prefix, and "
    "`pulse_app`'s column `INSERT` widened to it (ADR 0193: a policy row covers one course, "
    "fixed when it is written, because lead mappings keep no history)."
)

# ---------------------------------------------------------------------------
# The calendar this file stands on.
# ---------------------------------------------------------------------------

# The week most tests hold or release: course week 2, term week 8, whose report
# opens on Monday 2026-10-12 at 06:00 in New York (10:00 UTC). Not week 1, so the
# week before it exists and has opened, which is the twin the unopened-week
# refusal needs.
HELD_WEEK = 2
WEEK_BEFORE = 1
# The week after the held one, for a response that must not release its neighbour.
WEEK_AFTER = 3

# The boundary the ticket's done-when 4 is tested on: one second.
ONE_SECOND = timedelta(seconds=1)

# How far after an opening the rows a test plants are dated, each before the
# instant the reads are taken at (`CLEAR_OF_AN_OPENING`, an hour). A row dated
# after the reading clock would be judged by a rule this ticket does not state.
FIRST_ROW_AFTER_OPENING = timedelta(minutes=10)
POLICY_CHANGE_AFTER_OPENING = timedelta(minutes=20)
SECOND_ROW_AFTER_OPENING = timedelta(minutes=30)

# An instant every run of this suite is already past, for the two tests that ask
# whether a writer stamps the application clock rather than the real one. Course
# week 1's report opening plus three hours: 2026-10-05 13:00 UTC. No real clock
# will read it again, so an answer within minutes of it can only be the pretended
# one.
CLOCK_PROBE_WEEK = 1
CLOCK_PROBE_AFTER_OPENING = timedelta(hours=3)
CLOCK_TOLERANCE = timedelta(minutes=10)

# When the cohorts this world reads begin, transcribed from `SEEDED_COHORTS`; all
# four start the same day, which `assert_the_cohorts_start_together` checks.
COHORTS_READ_HERE = (TAUGHT_COHORT, UNTAUGHT_COHORT, SIBLING_COHORT, UNMAPPED_COHORT)
LIVE_FROM: date = SEEDED_COHORTS[TAUGHT_COHORT][2]
# An ended enrollment's last day: three days in, before any week this world
# reads has even opened its survey window, let alone its report.
ENDED_ON: date = LIVE_FROM + timedelta(days=3)


def assert_the_cohorts_start_together() -> None:
    """Every cohort read here starts on `LIVE_FROM`, in term week 7. A premise, not a red."""
    for cohort in COHORTS_READ_HERE:
        _length, first_term_week, starts = SEEDED_COHORTS[cohort]
        assert (first_term_week, starts) == (7, LIVE_FROM), (
            f"Cohort {cohort!r} starts in term week {first_term_week} on {starts}; this file "
            f"assumes term week 7 on {LIVE_FROM} for {COHORTS_READ_HERE}, so that course week N is "
            "the same term week in every section it reads. A broken world, not a red."
        )
    first_opening = REPORT_OPENS_BY_TERM_WEEK[TERM_WEEK_OF_COURSE_WEEK[1]]
    assert first_opening.date() > ENDED_ON, (
        f"`ENDED_ON` ({ENDED_ON}) is not before the first report opening ({first_opening}), so "
        "the ended enrollment would be live on some day this file reads."
    )


def report_opens(course_week: int) -> datetime:
    """When course week N's report opens, out of the hand-written table (a premise check first)."""
    assert_the_report_openings_are_what_this_file_says()
    return REPORT_OPENS_BY_TERM_WEEK[TERM_WEEK_OF_COURSE_WEEK[course_week]]


# ---------------------------------------------------------------------------
# The deliverables, named where a test can fail on them rather than error.
# ---------------------------------------------------------------------------


PATH_PARAMETERS = re.compile(r"\{([^}/:]+)(?::[^}/]+)?\}")

LATEST_ROUTE_IS_OWED = (
    "E7-02's amendment before review (A2) settles a second route in `app.api.student`, behind "
    "`require_student`: `GET …/student/sections/{section_id}/results`, with no week, answering "
    "the same payload for the section's latest published week, and the same single 404 when the "
    "section has no published week or for every case the week route refuses."
)


def _results_route_with(application: Any, parameters: set[str], owed: str) -> str:
    """The one GET route of `app.api.student` ending `/results` whose path parameters are these.

    The week route (decision 4) and the latest route (A2) both end `/results`, so
    each is told apart by the parameters its path declares rather than by count.
    """
    mounted = [
        route
        for route in every_route(application)
        if getattr(getattr(route, "endpoint", None), "__module__", None) == STUDENT_API_MODULE
    ]

    def methods(route: Any) -> set[str]:
        return {str(method).upper() for method in (getattr(route, "methods", None) or set())}

    def path(route: Any) -> str:
        return str(getattr(route, "path", "")).rstrip("/")

    found = [
        r
        for r in mounted
        if "GET" in methods(r)
        and path(r).endswith(RESULTS_ENDING)
        and set(PATH_PARAMETERS.findall(path(r))) == parameters
    ]
    if len(found) != 1:
        pytest.fail(
            f"`{STUDENT_API_MODULE}` mounts {len(found)} GET routes ending `{RESULTS_ENDING}` with "
            f"path parameters {sorted(parameters)}; it mounts "
            f"{sorted(f'{sorted(methods(r))} {path(r)}' for r in mounted)}.\n\n{owed}"
        )
    return path(found[0])


def results_route(application: Any) -> str:
    """The week route's path template, found in `app.api.student` (decision 4)."""
    return _results_route_with(application, {SECTION_PARAMETER, WEEK_PARAMETER}, ROUTE_IS_OWED)


def latest_results_route(application: Any) -> str:
    """The no-week route's path template, found in `app.api.student` (amendment A2)."""
    return _results_route_with(application, {SECTION_PARAMETER}, LATEST_ROUTE_IS_OWED)


def results_url(template: str, *, section_id: Any, course_week: Any = None) -> str:
    """The template with its parameters filled by name (the latest route takes no week)."""
    values = {SECTION_PARAMETER: str(section_id), WEEK_PARAMETER: str(course_week)}
    return PATH_PARAMETERS.sub(lambda match: values[match.group(1)], template)


def payload_of(answered: Any, what: str) -> dict[str, Any]:
    """A 200's decoded payload, its members held to decision 4's, or a failure saying why.

    The status is required here because a body decoded off a refusal is a body
    every later assertion is vacuously true of (`docs/MISTAKES.md` entry 3). The
    members are decision 4's, all required, and E8-01's and E8-03's admitted
    beside them by name: any other top-level member, or a fifth on the response,
    is a member nobody settled — and for a held week the likeliest one is a count,
    which done-when 1 forbids. (E8-01 changed this check from an equality, because
    its new members reach every payload; `docs/MISTAKES.md` entry 22.)
    """
    if answered.status_code != 200:
        pytest.fail(
            f"{what} answered {answered.status_code}, not 200. Body begins "
            f"{answered.text[:400]!r}.\n\n{ROUTE_IS_OWED}"
        )
    body = decoded(answered, what)
    members = set(body) if isinstance(body, dict) else set()
    unsettled = members - PAYLOAD_MEMBERS - MEMBERS_LATER_TICKETS_ADD
    if not isinstance(body, dict) or not members >= PAYLOAD_MEMBERS or unsettled:
        pytest.fail(
            f"{what} answered {str(body)[:400]!r}. Decision 4 settles `StudentWeekResults` as "
            f"{sorted(PAYLOAD_MEMBERS)}, and E8's tickets add only "
            f"{sorted(MEMBERS_LATER_TICKETS_ADD)} beside them."
        )
    response = body[RESPONSE]
    well_formed = isinstance(response, dict) and set(response) == RESPONSE_MEMBERS
    if response is not None and not well_formed:
        pytest.fail(
            f"{what} carries `response` = {str(response)[:400]!r}. Decision 4 settles "
            f"`StudentResponse` as exactly {sorted(RESPONSE_MEMBERS)}, or `None`."
        )
    weeks = body[PUBLISHED_WEEKS]
    if not isinstance(weeks, list) or not all(
        isinstance(week, int) and not isinstance(week, bool) for week in weeks
    ):
        pytest.fail(
            f"{what} carries `{PUBLISHED_WEEKS}` = {weeks!r}. The amendment's A1 settles "
            "`list[int]`, the course weeks whose report has opened."
        )
    return body


def outside_the_week_list(body: dict[str, Any]) -> dict[str, Any]:
    """The payload without `published_weeks`, whose numbers are course weeks and not counts."""
    return {key: value for key, value in body.items() if key != PUBLISHED_WEEKS}


def numbers_in(body: Any) -> list[Any]:
    """Every scalar in a decoded body that is a number (booleans are not)."""
    return [
        value
        for value in scalars_in(body)
        if isinstance(value, int | float) and not isinstance(value, bool)
    ]


def instant(value: Any, what: str) -> datetime:
    """A payload's ISO instant as an aware datetime, or a failure naming it."""
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        pytest.fail(f"{what} is {value!r}, which is not an ISO 8601 instant.")
    if parsed.tzinfo is None:
        pytest.fail(f"{what} is {value!r}, an instant with no offset (ADR 0019 refuses one).")
    return parsed


def the_service(name: str) -> Any:
    """One of the two writers, or a failure naming the work order."""
    try:
        module = import_module(SERVICE_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(f"`{SERVICE_MODULE}` does not import ({missing}).\n\n{WRITERS_ARE_OWED}")
    function = getattr(module, name, None)
    if not callable(function):
        pytest.fail(
            f"`{SERVICE_MODULE}` exposes no callable `{name}`; it exposes "
            f"{sorted(n for n in vars(module) if not n.startswith('_'))}.\n\n{WRITERS_ARE_OWED}"
        )
    return function


def the_response_model() -> type:
    module = import_module(MODEL_MODULE)
    model = getattr(module, RESPONSE_MODEL, None)
    if not isinstance(model, type):
        pytest.fail(f"`{MODEL_MODULE}` declares no `{RESPONSE_MODEL}` (E7-01's model).")
    return model


def require_the_policy_course(tables: Mapping[str, Any]) -> None:
    """Fail naming M2 when `response_policy` declares no `course_id`."""
    require_the_tables(dict(tables))
    if POLICY_COURSE_COLUMN not in tables[RESPONSE_POLICY].c:
        pytest.fail(
            f"`{RESPONSE_POLICY}` declares {[c.name for c in tables[RESPONSE_POLICY].columns]} and "
            f"no `{POLICY_COURSE_COLUMN}`.\n\n{M2_IS_OWED}"
        )


def response_loop_copy() -> dict[str, str]:
    """Every sentence `app.copy.response_loop` registers, by key (decision 5).

    `tests/fixtures/lead_review.py::lead_moderation_copy`'s device, pointed at the
    module this ticket owns: found through `copy_modules()` and read off its `COPY`
    mapping, the registry's own convention.
    """
    package = import_module(COPY_PACKAGE)
    modules = getattr(package, COPY_MODULES_FUNCTION)()
    found = [module for module in modules if getattr(module, "__name__", None) == COPY_MODULE]
    if len(found) != 1:
        pytest.fail(
            f"`{COPY_PACKAGE}.{COPY_MODULES_FUNCTION}()` enumerates no `{COPY_MODULE}` (it "
            f"enumerates {sorted(getattr(module, '__name__', '?') for module in modules)}). "
            "E7-02's ticket owns that module, and decision 5 puts the route's one refusal "
            "sentence there."
        )
    mapping = getattr(found[0], COPY_MAPPING_NAME, None)
    if not isinstance(mapping, Mapping) or not mapping:
        pytest.fail(f"`{COPY_MODULE}` publishes no `{COPY_MAPPING_NAME}` entries.")
    return {str(key): str(getattr(entry, "text", entry)) for key, entry in mapping.items()}


def sentences_served(answered: Any) -> list[str]:
    """The keys of `app.copy.response_loop` whose sentence the response carries."""
    body = served_text(answered)
    copy = response_loop_copy()
    return sorted(key for key, sentence in copy.items() if sentence and sentence in body)


def a_reply_in(
    rows: Any,
    *,
    section_id: Any,
    term_id: Any,
    week_id: Any,
    author: Any,
    body: str,
    published_at: datetime,
) -> None:
    """One `INSTRUCTOR` response row in somebody else's world, written as the superuser; committed.

    For the two student-route sweeps, whose worlds are not this file's: `rows` is
    whatever seeds and commits there (`committed_rows`, or a world carrying
    `seed` and the door's `commit`). The author must teach the section — E7-01's
    trigger refuses anybody else on every connection.
    """
    rows.seed(
        INSTRUCTOR_RESPONSE,
        {},
        **{
            RESPONSE_SECTION_COLUMN: section_id,
            RESPONSE_TERM_COLUMN: term_id,
            WEEK_COLUMN: week_id,
            RESPONSE_AUTHOR_COLUMN: author,
            ROLE_COLUMN: INSTRUCTOR,
            AI_SEEDED_COLUMN: False,
            RESPONSE_BODY_COLUMN: body,
            RESPONSE_TIME_COLUMN: published_at,
        },
    )
    rows.commit()


def spellings_of(identifier: Any) -> set[str]:
    """A uuid as a response could carry it: hyphenated and bare (`telling_values`' pair)."""
    written = str(identifier)
    return {written, written.replace("-", "")}


# ---------------------------------------------------------------------------
# The world.
# ---------------------------------------------------------------------------


class Student(NamedTuple):
    """One `user`, enrolled in one section, and the `STUDENT` session minted for them."""

    user_id: Any
    token: str
    section_id: Any
    label: str


class HoldWorld:
    """E7-01's named world, with students, windows and rows a test asks for. See the docstring."""

    def __init__(self, names: StaffNameWorld) -> None:
        self.names = names
        self._route: str | None = None

    # -- keys -----------------------------------------------------------------

    @property
    def review(self) -> LeadReviewWorld:
        return self.names.review

    @property
    def rows(self) -> Any:
        return self.names.rows

    @property
    def tables(self) -> dict[str, Any]:
        return self.names.tables

    @property
    def door(self) -> Any:
        """The `ReportDoor` the whole world was built through; its tool serves every read."""
        return self.review.door.door

    @property
    def application_session(self) -> Any:
        return self.names.application_session

    def section_id(self, cohort: str) -> Any:
        return self.review.world.section_id(cohort)

    @property
    def taught(self) -> Any:
        return self.names.taught

    @property
    def sibling_section(self) -> Any:
        return self.names.sibling_section

    @property
    def sibling_course_section(self) -> Any:
        return self.names.sibling_course_section

    @property
    def unmapped_section(self) -> Any:
        return self.names.unmapped_section

    @property
    def own_course(self) -> Any:
        return self.review.own_course

    @property
    def sibling_course(self) -> Any:
        return self.review.sibling_course

    @property
    def unmapped_course(self) -> Any:
        return self.review.unmapped_course

    @property
    def prefix(self) -> Any:
        chain = self.review.world.calendar.chain
        return chain["prefix"][single_primary_key(require_table(self.tables, "prefix"))]

    def person(self, who: Person | None) -> Person:
        assert who is not None, "This world names that person; `build_staff_name_world` did not."
        return who

    def week_id(self, course_week: int) -> Any:
        return self.review.world.week_id(TERM_WEEK_OF_COURSE_WEEK[course_week])

    def term_id(self) -> Any:
        return self.review.world.term_id()

    def code_of(self, cohort: str) -> str:
        return self.review.code_of(cohort)

    # -- the clock ------------------------------------------------------------

    def stand_at(self, moment: datetime) -> None:
        self.door.pretend(moment)

    def stand_after_the_opening(self, course_week: int) -> None:
        """An hour after the week's report opens: whole hours, because ADR 0109's clock drifts."""
        self.stand_at(report_opens(course_week) + CLEAR_OF_AN_OPENING)

    def stand_before_the_opening(self, course_week: int) -> None:
        self.stand_at(report_opens(course_week) - CLEAR_OF_AN_OPENING)

    # -- planting -------------------------------------------------------------

    def windows_for(self, cohort: str, *course_weeks: int) -> None:
        """A survey window for each course week of a cohort's section, at the world's instants."""
        for course_week in course_weeks:
            self.review.world.window(TERM_WEEK_OF_COURSE_WEEK[course_week], cohort)
        self.rows.commit()

    def a_student(self, label: str, section_id: Any, *, ended: bool = False) -> Student:
        """A `user` enrolled from `LIVE_FROM` (to `ENDED_ON` if `ended`), and a minted session."""
        assert_the_cohorts_start_together()
        subject = f"e7-02-{label}-{uuid4().hex[:8]}"
        user_id = self.names.web_identity.user(
            platform_id=self.review._platform_id(), subject=subject
        )
        self.names.enrol.enrol(
            user_id=user_id,
            section_id=section_id,
            started_on=LIVE_FROM,
            ended_on=ENDED_ON if ended else None,
        )
        self.rows.commit()
        token = self.review.minted(
            role=STUDENT_LANDING_ROLE, person_id=None, user_id=user_id, subject=subject
        )
        return Student(user_id=user_id, token=token, section_id=section_id, label=label)

    def a_policy(
        self, *, course: Any, setter: Any, role: str, mode: str, set_at: datetime
    ) -> dict[str, Any]:
        """One `response_policy` row, every column named, written as the superuser; committed."""
        require_the_policy_course(self.tables)
        row = self.rows.seed(
            RESPONSE_POLICY,
            {},
            **{
                POLICY_COURSE_COLUMN: course,
                POLICY_PREFIX_COLUMN: self.prefix,
                POLICY_SETTER_COLUMN: setter,
                ROLE_COLUMN: role,
                MODE_COLUMN: mode,
                POLICY_TIME_COLUMN: set_at,
            },
        )
        self.rows.commit()
        return dict(row)

    def response_values(
        self,
        *,
        section_id: Any,
        course_week: int,
        author: Any,
        role: str,
        body: str,
        published_at: datetime,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            RESPONSE_SECTION_COLUMN: section_id,
            RESPONSE_TERM_COLUMN: self.term_id(),
            WEEK_COLUMN: self.week_id(course_week),
            RESPONSE_AUTHOR_COLUMN: author,
            ROLE_COLUMN: role,
            AI_SEEDED_COLUMN: False,
            RESPONSE_BODY_COLUMN: body,
            RESPONSE_TIME_COLUMN: published_at,
            **extra,
        }

    def a_response(self, **keywords: Any) -> dict[str, Any]:
        """One `instructor_response` row, written as the superuser; committed."""
        require_the_tables(self.tables)
        row = self.rows.seed(INSTRUCTOR_RESPONSE, {}, **self.response_values(**keywords))
        self.rows.commit()
        return dict(row)

    def move_the_lead(self, course: Any, *, to: Any) -> None:
        """The course's responsible person changes: its mapping and its lead's grant go.

        `to` is a person who is mapped to the course and given the `LEAD_FACULTY`
        assignment in their place, or `None`, so the course falls to its chair (SPEC
        §2.1). Read back afterwards: a world where the old lead still holds the
        course is not a change of responsible person.
        """
        graph = self.review.graph
        mappings = graph.mappings
        course_column = foreign_key_columns(mappings, "course")[0]
        person_column = foreign_key_columns(mappings, "person")[0]
        session = self.rows.session
        session.rollback()
        old = [
            row[0]
            for row in session.execute(
                mappings.select()
                .with_only_columns(mappings.c[person_column])
                .where(mappings.c[course_column] == course)
            )
        ]
        session.execute(mappings.delete().where(mappings.c[course_column] == course))
        assignments = graph.assignments
        for person in old:
            session.execute(
                assignments.delete().where(assignments.c[graph.person_column] == person)
            )
        if to is not None:
            graph.assign(LEAD_FACULTY, scope=course, person=to)
            graph.lead_mapping(person=to, course=course)
        self.rows.commit()
        session.rollback()
        now_mapped = {
            str(row[0])
            for row in session.execute(
                mappings.select()
                .with_only_columns(mappings.c[person_column])
                .where(mappings.c[course_column] == course)
            )
        }
        session.rollback()
        assert now_mapped == ({str(to)} if to is not None else set()), (
            f"After the change the course is mapped to {now_mapped}; the change was to "
            f"{to!r}. A broken world, not a red."
        )
        assert old, "The course had no lead before the change, so nothing changed."

    # -- reading --------------------------------------------------------------

    def route(self) -> str:
        if self._route is None:
            self._route = results_route(self.door.application)
        return self._route

    def results(self, student: Student, *, course_week: int, section_id: Any = None) -> Any:
        """One read of the results route as `student`; their own section unless named."""
        url = results_url(
            self.route(),
            section_id=student.section_id if section_id is None else section_id,
            course_week=course_week,
        )
        return self.review.ask("GET", url, token=student.token)

    def payload(self, student: Student, *, course_week: int, section_id: Any = None) -> dict:
        answered = self.results(student, course_week=course_week, section_id=section_id)
        return payload_of(
            answered, f"The results read of course week {course_week} for {student.label}"
        )

    def latest(self, student: Student, *, section_id: Any = None) -> Any:
        """One read of the no-week route (A2) as `student`; their own section unless named."""
        url = results_url(
            latest_results_route(self.door.application),
            section_id=student.section_id if section_id is None else section_id,
        )
        return self.review.ask("GET", url, token=student.token)

    def latest_payload(self, student: Student, *, section_id: Any = None) -> dict:
        answered = self.latest(student, section_id=section_id)
        return payload_of(answered, f"The latest-week results read for {student.label}")

    def rows_of(self, table_name: str, column: str, value: Any) -> list[dict[str, Any]]:
        """Every row of `table_name` whose `column` is `value`, by `sequence`, as the superuser."""
        table = self.tables[table_name]
        session = self.rows.session
        session.rollback()
        statement = table.select().where(table.c[column] == value)
        if SEQUENCE_COLUMN in table.c:
            statement = statement.order_by(table.c[SEQUENCE_COLUMN])
        found = [dict(row) for row in session.execute(statement).mappings()]
        session.rollback()
        return found

    def count(self, table_name: str) -> int:
        table = self.tables[table_name]
        session = self.rows.session
        session.rollback()
        found = len(session.execute(table.select()).all())
        session.rollback()
        return found

    # -- the two writers ------------------------------------------------------

    def publish(
        self,
        *,
        section_id: Any,
        course_week: int,
        author: Any,
        role: str,
        body: str,
        ai_seeded: bool = False,
    ) -> Any:
        """Call decision 6's writer on `pulse_app`'s connection and commit; its answer."""
        writer = the_service(PUBLISH_WRITER)
        session = self.application_session
        try:
            written = writer(
                session,
                section_id=section_id,
                course_week=course_week,
                author_person_id=author,
                role=role,
                ai_seeded=ai_seeded,
                body=body,
            )
        except TypeError as mismatch:
            session.rollback()
            pytest.fail(f"`{PUBLISH_WRITER}` refused decision 6's keywords: {mismatch}")
        session.commit()
        return written

    def record(self, *, setter: Any, role: str, mode: str) -> list[Any]:
        """Call decision 1's writer on `pulse_app`'s connection and commit; the rows it answered."""
        writer = the_service(POLICY_WRITER)
        session = self.application_session
        try:
            written = writer(
                session, setter_person_id=setter, role=role, prefix_id=self.prefix, mode=mode
            )
        except TypeError as mismatch:
            session.rollback()
            pytest.fail(f"`{POLICY_WRITER}` refused decision 1's keywords: {mismatch}")
        session.commit()
        if not isinstance(written, list | tuple):
            pytest.fail(
                f"`{POLICY_WRITER}` answered {type(written).__name__}; decision 1: it returns the "
                "rows it wrote."
            )
        return list(written)


def build_hold_world(names: StaffNameWorld) -> HoldWorld:
    """E7-01's world as it stands, wrapped. The premise checks are this fixture's."""
    assert_the_cohorts_start_together()
    for who in (names.teacher, names.lead, names.sibling_lead, names.chair):
        assert who is not None, "E7-01's world names no teacher, lead, sibling lead or chair."
    return HoldWorld(names)


@pytest.fixture
def hold(staff_names: StaffNameWorld) -> HoldWorld:
    """E7-01's named world, wrapped for E7-02. See the module docstring.

    Builds nothing E7-02 owes: the route, the writers, the copy module and M2's
    column are each looked up inside a test body (`docs/MISTAKES.md` entry 44).
    """
    return build_hold_world(staff_names)
