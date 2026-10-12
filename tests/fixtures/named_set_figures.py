"""E9-05 — named-set figures under the reader's purview, and the seal counting the reader.

E9-05's test modules ask the same things of the same world, so the world lives here
and each module asserts (`docs/MISTAKES.md` entry 13):

  - **Departments, courses and sections placed where a purview can be drawn
    around them.** `BenchmarkWorld` (E5-03) hangs every section under one
    department and one course of its own; a chair, a lead with several courses,
    and a lead whose courses straddle two departments all need more than that.
    `PurviewWorld` adds named departments, named courses with any number of
    sections, and the people and assignments E9-01's purview is resolved from —
    and delegates every student, window and response to `BenchmarkWorld`.
  - **The reader's scope, resolved the way production resolves it**:
    `authz.resolve_scope(session, person_id=…)`, E9-01's chokepoint. The scope
    is never built by hand here, because "the figure is computed over the
    purview" would then be a statement about a value this file chose
    (`docs/MISTAKES.md` entry 30).
  - **The names E9-05's interface settles**, spelled once:
    `named_set_series(session, *, set_id, scope, term_id, settings)` and
    `section_benchmarks(…, scope=…)` in `app.services.benchmarks`;
    `named_set_figures` with `SetUnavailableError` and `TermUnavailableError` in
    `app.services.comparison_sets`; `NamedSetCohort` and `NamedSetWeek` with the
    members the interface lists. Each is looked up inside a test body, so a tree
    where E9-05 is unbuilt is a FAILED naming the missing symbol rather than an
    ERROR (`docs/MISTAKES.md` entry 44).
  - **Readers for what those answer**: one week of a series, its four figures by
    name, a figure's state, and any result as plain data so two answers can be
    compared for equality.

**Nothing here computes a figure a test reads back.** Every count is a literal
or an offset from the configured minimum in the test that plants it, and every
expected mean is arithmetic written in that test (`docs/MISTAKES.md` entries 19
and 30).

**The world's calendar, and why.** Every section is cohort `F` (six weeks,
starting 2026-09-28, term weeks 7 to 12) or, where a second start cohort is the
subject, cohort `H` (six weeks, starting 2026-11-09), at level `UGGR` (course
number 540). `UGGR` and a mid-term cohort are chosen because the university line
is "all same-length+level sections institution-wide": a committed world another
worker leaves behind for a moment is far likelier to be `UG` and start in week
one, and a section of it counted here would move a university figure this
module did not plant. Every section gets a window for every course week, at
SPEC §3.1's hand-written instants, so every week of its cohort has a cutoff; and
every response states its own `last_submitted_at`, one hour before its window
closes, because the named-set read computes its cutoffs from the windows (E9
decision 14) and a stamp the seeding walker invented would decide what counts.

**The clock is pinned** past the end of Fall 2026 (`pinned_benchmark_clock`), so
every week is published wherever the read asks.
"""

from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from fixtures.benchmark_views import (
    COMPARISON_FIGURE_TYPE,
    COURSE_NUMBER_COLUMN,
    COURSE_TABLE,
    CURRENT_TERM,
    DEPARTMENT_TABLE,
    PINNED_NOW,
    WINDOWS_BY_TERM,
    BenchmarkWorld,
    PlantedSection,
    benchmarks_module,
    numbers_in,
    reporting_symbol,
    serialized_figure,
)
from fixtures.comparison_sets import (
    COMPARISON_SET_TABLE,
    LENGTH_COLUMN,
    LEVEL_COLUMN,
    member_of,
    membership_table,
    one_key_column_to,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import (
    COHORT_SECTION_MODALITY,
    SECTION_CODE_COLUMN,
    SECTION_END_COLUMN,
    SECTION_LENGTH_COLUMN,
    SECTION_START_COLUMN,
    SECTION_TABLE,
    SEEDED_COHORTS,
    TERM_TABLE,
)

# ---------------------------------------------------------------------------
# The names E9-05's interface settles.
# ---------------------------------------------------------------------------

NAMED_SET_SERIES = "named_set_series"
SECTION_BENCHMARKS = "section_benchmarks"
NAMED_SET_COHORT = "NamedSetCohort"
NAMED_SET_WEEK = "NamedSetWeek"

AUTHZ_HELPER = "leadership_section_ids"

COMPARISON_SETS_MODULE = "app.services.comparison_sets"
NAMED_SET_FIGURES = "named_set_figures"
SET_UNAVAILABLE_ERROR = "SetUnavailableError"
TERM_UNAVAILABLE_ERROR = "TermUnavailableError"

# The members of the two value types, as the interface lists them.
COHORT_START_MEMBER = "section_start_date"
COHORT_WEEKS_MEMBER = "weeks"
WEEK_COURSE_WEEK_MEMBER = "course_week"
WEEK_TERM_WEEK_MEMBER = "term_week"
WEEK_RATINGS_MEMBER = "ratings"
WEEK_WORKLOAD_MEMBER = "workload"

# The four figures one week carries, by the name a failure message calls them.
INSTRUCTOR_FIGURE = "instructor rating"
COURSE_FIGURE = "course rating"
WORKLOAD_MEAN = "workload mean"
WORKLOAD_MEDIAN = "workload median"
WEEK_FIGURES = (INSTRUCTOR_FIGURE, COURSE_FIGURE, WORKLOAD_MEAN, WORKLOAD_MEDIAN)

THE_SERVICE_IS_OWED = (
    "E9-05's interface settles `named_set_series(session, *, set_id, scope, term_id, settings) -> "
    "list[NamedSetCohort]` in `app.services.benchmarks`, with `NamedSetCohort(section_start_date, "
    "weeks)` and `NamedSetWeek(course_week, term_week, ratings, workload)`, `ratings` keyed by "
    "`INSTRUCTOR` and `COURSE`; and `section_benchmarks(…, scope)` taking the reader's scope into "
    "the seal, keyword-only and required (`scope=None` for an instructor's own report)."
)

# ---------------------------------------------------------------------------
# The world's calendar and level.
# ---------------------------------------------------------------------------

LEVEL = "UGGR"
LEVEL_NUMBER = "540"
COHORT = "F"
LATER_COHORT = "H"
SIX_WEEKS = 6
THE_COURSE_WEEK = 2
STREAMS = (INSTRUCTOR_STREAM, COURSE_STREAM)

# How long before its own window's close a response says it was last submitted.
BEFORE_THE_CLOSE = timedelta(hours=1)

# The cutoffs `section_benchmarks` is asked with: one week, after every window, so
# every planted response counts and the seal is the only subject.
SECTION_CUTOFFS = {THE_COURSE_WEEK: PINNED_NOW}


def start_of(cohort: str) -> date:
    """A cohort's start date, from the transcribed start-letter map."""
    return SEEDED_COHORTS[cohort][2]


# ---------------------------------------------------------------------------
# Reaching the deliverables from a test body.
# ---------------------------------------------------------------------------


def benchmarks_symbol(name: str) -> Any:
    """One name off `app.services.benchmarks`, or a FAILED naming it."""
    module = benchmarks_module()
    found = getattr(module, name, None)
    if found is None:
        pytest.fail(
            f"`app.services.benchmarks` exposes no `{name}`; it exposes "
            f"{sorted(entry for entry in vars(module) if not entry.startswith('_'))}.\n\n"
            f"{THE_SERVICE_IS_OWED}"
        )
    return found


def comparison_sets_symbol(name: str) -> Any:
    """One name off `app.services.comparison_sets`, or a FAILED naming it."""
    from importlib import import_module

    module = import_module(COMPARISON_SETS_MODULE)
    found = getattr(module, name, None)
    if found is None:
        pytest.fail(
            f"`{COMPARISON_SETS_MODULE}` exposes no `{name}`. E9-05's interface settles "
            f"`{NAMED_SET_FIGURES}(session, *, set_id, scope, term_id, settings)` there, raising "
            f"`{SET_UNAVAILABLE_ERROR}` for an unknown set (checked first) and "
            f"`{TERM_UNAVAILABLE_ERROR}`, a new class in the same module, for an unknown term."
        )
    return found


def figure_type() -> Any:
    """E4-07's `ComparisonFigure`, the one type every benchmark figure is."""
    return reporting_symbol(COMPARISON_FIGURE_TYPE)


# ---------------------------------------------------------------------------
# Reading what the reads answer.
# ---------------------------------------------------------------------------


def member(value: Any, name: str, where: str) -> Any:
    """One member of a value type the interface settles, or a FAILED naming it."""
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
    elif hasattr(value, name):
        return getattr(value, name)
    pytest.fail(f"{where} is {value!r}, which carries no `{name}`.\n\n{THE_SERVICE_IS_OWED}")


def cohorts_of(series: Any) -> list[Any]:
    """The cohorts a series answers, as a list, or a FAILED naming the shape."""
    if not isinstance(series, list | tuple):
        pytest.fail(
            f"`named_set_series` answered {series!r}, not a list of cohorts.\n\n"
            f"{THE_SERVICE_IS_OWED}"
        )
    return list(series)


def start_dates(series: Any) -> list[date]:
    """Every cohort's start date, in the order the series answers them."""
    return [member(cohort, COHORT_START_MEMBER, "A cohort") for cohort in cohorts_of(series)]


def the_week(series: Any, *, start: date, course_week: int = THE_COURSE_WEEK) -> Any:
    """One cohort's one week, or a FAILED saying what the series holds instead.

    Required present rather than looked up optionally: a week of a published
    cohort is a point shown or suppressed, never an absent one, and a reader that
    treated a missing week as "suppressed" would report a dropped point as a
    sealed one (`docs/MISTAKES.md` entry 3).
    """
    found = [
        week
        for cohort in cohorts_of(series)
        if member(cohort, COHORT_START_MEMBER, "A cohort") == start
        for week in member(cohort, COHORT_WEEKS_MEMBER, "A cohort")
        if member(week, WEEK_COURSE_WEEK_MEMBER, "A week") == course_week
    ]
    if len(found) != 1:
        pytest.fail(
            f"The series holds {len(found)} weeks numbered {course_week} in the cohort starting "
            f"{start}; it holds cohorts {start_dates(series)}: {series!r}. Every week of a "
            "published cohort is answered once, shown or suppressed."
        )
    return found[0]


def week_figures(week: Any) -> dict[str, Any]:
    """The four figures one week carries, by name."""
    ratings = member(week, WEEK_RATINGS_MEMBER, "A week")
    workload = member(week, WEEK_WORKLOAD_MEMBER, "A week")
    return {
        INSTRUCTOR_FIGURE: member(ratings, INSTRUCTOR_STREAM, "A week's ratings"),
        COURSE_FIGURE: member(ratings, COURSE_STREAM, "A week's ratings"),
        WORKLOAD_MEAN: member(workload, "mean", "A week's workload"),
        WORKLOAD_MEDIAN: member(workload, "median", "A week's workload"),
    }


def is_suppressed(figure: Any) -> bool:
    """The chokepoint's own suppressed state: the flag, a reason, no figure and no number."""
    held = serialized_figure(figure)
    return (
        held.get("suppressed") is True
        and bool(held.get("reason"))
        and held.get("figure") is None
        and not numbers_in(held)
    )


def is_shown(figure: Any) -> bool:
    """A figure that is shown: not suppressed, and carrying its statistic."""
    held = serialized_figure(figure)
    return held.get("suppressed") is False and held.get("figure") is not None


def carries_value(figure: Any, expected: Any) -> bool:
    """Whether a figure's statistic is this number (to the tolerance a float allows)."""
    held = serialized_figure(figure).get("figure")
    return held is not None and float(held) == pytest.approx(float(expected))


def every_figure(value: Any) -> list[Any]:
    """Every comparison figure inside a result, at any depth, found by type."""
    from fixtures.benchmark_views import figures_in

    return figures_in(value, figure_type())


def any_carries(value: Any, expected: Any) -> bool:
    """Whether any figure anywhere in a result is shown carrying this number."""
    return any(carries_value(figure, expected) for figure in every_figure(value))


def as_data(value: Any) -> Any:
    """Any result as plain data, so two answers can be compared for equality.

    A figure becomes its serialization; a dataclass, its fields; a mapping, a
    dict; a sequence, a list; a date, a uuid or a decimal, its string. Two
    answers equal here carry the same cohorts, weeks, states and numbers.
    """
    kind = figure_type()
    if isinstance(value, kind):
        return serialized_figure(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {entry.name: as_data(getattr(value, entry.name)) for entry in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): as_data(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [as_data(item) for item in value]
    if isinstance(value, date | datetime | UUID | Decimal):
        return str(value)
    dumped = getattr(value, "model_dump", None)
    if callable(dumped):
        return dumped(mode="json")
    held = getattr(value, "__dict__", None)
    if isinstance(held, dict) and held:
        return {key: as_data(item) for key, item in held.items() if not key.startswith("_")}
    return value


# ---------------------------------------------------------------------------
# The world.
# ---------------------------------------------------------------------------


class PurviewWorld:
    """`BenchmarkWorld` with named departments, multi-section courses, people and their hats."""

    def __init__(
        self, world: BenchmarkWorld, graph: Any, authz: Any, settings: Any, minimums: Any
    ) -> None:
        self.world = world
        self.graph = graph
        self.authz = authz
        self.settings = settings
        self._minimums = minimums
        self._departments: dict[str, dict[str, Any]] = {}
        self._courses: dict[str, dict[str, Any]] = {}
        self._ordinals: dict[str, int] = {}
        self._people: dict[str, Any] = {}
        self._sets: dict[str, Any] = {}

    # -- keys -------------------------------------------------------------------

    @property
    def session(self) -> Any:
        return self.world.session

    def key_of(self, table: str) -> str:
        return single_primary_key(require_table(self.world.tables, table))

    @property
    def sections_minimum(self) -> int:
        return int(self._minimums()["benchmark_min_sections_default"])

    @property
    def respondents_minimum(self) -> int:
        return int(self._minimums()["benchmark_min_respondents_default"])

    # -- building ---------------------------------------------------------------

    def build(self) -> "PurviewWorld":
        """The current term, its weeks and the question set; nothing else yet."""
        self.world.build()
        self._departments = {}
        self._courses = {}
        self._ordinals = {}
        self._people = {}
        self._sets = {}
        return self

    def department(self, name: str) -> dict[str, Any]:
        """A department of its own under the world's one college, seeded on first use."""
        if name not in self._departments:
            spine = self.world.spine()
            chain = {level: spine[level] for level in ("institution", "college") if level in spine}
            self.world.seed(DEPARTMENT_TABLE, chain)
            if DEPARTMENT_TABLE not in chain:
                pytest.fail(
                    "Seeding a department left none in the walker's chain; a defect in this "
                    "fixture, not in anything under test."
                )
            self._departments[name] = chain
        return self._departments[name]

    def department_id(self, name: str) -> Any:
        return self.department(name)[DEPARTMENT_TABLE][self.key_of(DEPARTMENT_TABLE)]

    def course(self, name: str, *, department: str) -> Any:
        """A course at `LEVEL` under a fresh prefix of `department`; its row."""
        if name in self._courses:
            pytest.fail(f"This world already holds a course named {name!r}.")
        chain = dict(self.department(department))
        self.world.seed(COURSE_TABLE, chain, **{COURSE_NUMBER_COLUMN: LEVEL_NUMBER})
        self._courses[name] = chain
        self._ordinals[name] = 0
        return chain[COURSE_TABLE]

    def course_row(self, name: str) -> Any:
        if name not in self._courses:
            pytest.fail(
                f"This world holds no course named {name!r}; it holds {sorted(self._courses)}."
            )
        return self._courses[name][COURSE_TABLE]

    def course_id(self, name: str) -> Any:
        return self.course_row(name)[self.key_of(COURSE_TABLE)]

    def section(self, label: str, *, course: str, cohort: str = COHORT) -> PlantedSection:
        """One section of `course` in the current term, with a window for every course week.

        The calendar is the start-letter map's (an input, never an output); the
        ordinal keeps two sections of one course distinct under E0-06's
        `(course, term, code)` uniqueness.
        """
        if label in self.world.sections:
            pytest.fail(f"This world already holds a section labelled {label!r}.")
        self.course_row(course)
        length_weeks, first_term_week, start = SEEDED_COHORTS[cohort]
        self._ordinals[course] += 1
        ordinal = self._ordinals[course]
        if ordinal > 9:
            pytest.fail(f"Course {course!r} has more than nine sections; this fixture numbers 1-9.")
        chain = dict(self._courses[course])
        chain.pop(SECTION_TABLE, None)
        chain[TERM_TABLE] = self.world.term_row()
        row = self.world.seed(
            SECTION_TABLE,
            chain,
            **{
                SECTION_CODE_COLUMN: f"{cohort}{ordinal}{COHORT_SECTION_MODALITY}",
                SECTION_LENGTH_COLUMN: length_weeks,
                SECTION_START_COLUMN: start,
                SECTION_END_COLUMN: start + timedelta(days=length_weeks * 7 - 1),
            },
        )
        planted = PlantedSection(
            label=label,
            row=row,
            term=CURRENT_TERM,
            cohort=cohort,
            level=LEVEL,
            length_weeks=length_weeks,
            first_term_week=first_term_week,
            start_date=start,
            course=self.course_row(course),
        )
        self.world.sections[label] = planted
        for course_week in range(1, length_weeks + 1):
            self.world.window(label, self.world.term_week_of(label, course_week))
        return planted

    def section_id(self, label: str) -> Any:
        return self.world.section_id(label)

    def section_ids(self, *labels: str) -> set[Any]:
        return {self.section_id(label) for label in labels}

    def close_of(self, label: str, course_week: int = THE_COURSE_WEEK) -> datetime:
        """The hand-written close of one section's window for one course week."""
        planted = self.world.section(label)
        term_week = self.world.term_week_of(label, course_week)
        return WINDOWS_BY_TERM[planted.term][term_week][1]

    # -- people and their hats --------------------------------------------------

    def person(self, name: str) -> Any:
        if name not in self._people:
            self._people[name] = self.graph.person()
        return self._people[name]

    def lead(self, name: str, *courses: str) -> Any:
        """A Lead Faculty member: the mapping row and the assignment, per course (E9-01's lead)."""
        person = self.person(name)
        for course in courses:
            self.graph.lead_mapping(person=person, course=self.course_id(course))
            self.graph.assign("LEAD_FACULTY", scope=self.course_id(course), person=person)
        return person

    def led_alone(self, course: str) -> Any:
        """A mapping to a person who leads `course` and nothing else, and holds no assignment.

        So the course's default set is empty by construction — "the same Lead
        Faculty's courses" with no other course in it — whatever a service does
        for a course with no lead at all, which no record this suite reads
        settles.
        """
        person = self.graph.person()
        self.graph.lead_mapping(person=person, course=self.course_id(course))
        return person

    def chair(self, name: str, department: str) -> Any:
        person = self.person(name)
        self.graph.assign("CHAIR", scope=self.department_id(department), person=person)
        return person

    def teach(self, name: str, label: str) -> Any:
        person = self.person(name)
        self.graph.assign("INSTRUCTOR", scope=self.section_id(label), person=person)
        return person

    def scope(self, name: str) -> Any:
        """The reader's `ActorScope`, resolved by E9-01's chokepoint from the person alone."""
        self.session.flush()
        return self.authz.resolve_scope(self.session, person_id=self.person(name))

    def purview_section_ids(self, name: str) -> frozenset[Any]:
        return frozenset(self.scope(name).purview.section_ids)

    # -- what students answered -------------------------------------------------

    def answer(
        self,
        labels: Sequence[str],
        *,
        respondents: int,
        prefix: str,
        rating: Any,
        hours: Any,
        course_rating: Any = None,
        course_week: int = THE_COURSE_WEEK,
        last_submitted_at: datetime | None = None,
    ) -> list[str]:
        """`respondents` new students, dealt round-robin over `labels`, one response each.

        `hours` is one value for everybody or one per respondent. Every response
        states `last_submitted_at`: one hour before its own window closes unless
        the caller names an instant. Answers the subjects, so a test can say who
        answered.
        """
        if respondents and not labels:
            pytest.fail("Respondents dealt over no section answer nowhere.")
        per_person = list(hours) if isinstance(hours, list | tuple) else [hours] * respondents
        if len(per_person) != respondents:
            pytest.fail(f"{respondents} respondents and {len(per_person)} hours values.")
        subjects: list[str] = []
        for index in range(respondents):
            label = labels[index % len(labels)]
            subject = f"{prefix}-{index:02d}"
            student = self.world.student(subject, enrolled_in=(label,))
            stamp = (
                last_submitted_at
                if last_submitted_at is not None
                else self.close_of(label, course_week) - BEFORE_THE_CLOSE
            )
            self.world.respond(
                label,
                course_week=course_week,
                student=student,
                workload=per_person[index],
                instructor_rating=Decimal(rating),
                course_rating=Decimal(rating if course_rating is None else course_rating),
                last_submitted_at=stamp,
            )
            subjects.append(subject)
        return subjects

    def answer_in_both(
        self,
        first: str,
        second: str,
        *,
        subject: str,
        rating: Any,
        hours: Any,
        course_week: int = THE_COURSE_WEEK,
    ) -> None:
        """One student enrolled in two sections who answers the same course week in each.

        Two responses and one person: `docs/MISTAKES.md` entry 50's plant, where a
        count of responses and a count of people differ by exactly one.
        """
        student = self.world.student(subject, enrolled_in=(first,))
        self.world.enroll(student, second)
        for label in (first, second):
            self.world.respond(
                label,
                course_week=course_week,
                student=student,
                workload=hours,
                instructor_rating=Decimal(rating),
                course_rating=Decimal(rating),
                last_submitted_at=self.close_of(label, course_week) - BEFORE_THE_CLOSE,
            )

    # -- named sets -------------------------------------------------------------

    def named_set(self, name: str, *courses: str) -> Any:
        """A named set declaring six weeks at `LEVEL`, with the named member courses."""
        if name in self._sets:
            pytest.fail(f"This world already holds a named set called {name!r}.")
        row = self.world.seed(
            COMPARISON_SET_TABLE, {}, **{LENGTH_COLUMN: SIX_WEEKS, LEVEL_COLUMN: LEVEL}
        )
        membership = membership_table(self.world.tables)
        for course in courses:
            member_of(self.world.seed, membership, row, self.course_row(course))
        self._sets[name] = row
        self.session.flush()
        return row[self.key_of(COMPARISON_SET_TABLE)]

    def set_id(self, name: str) -> Any:
        if name not in self._sets:
            pytest.fail(f"This world holds no named set called {name!r}.")
        return self._sets[name][self.key_of(COMPARISON_SET_TABLE)]

    def add_member(self, set_name: str, course: str) -> None:
        """An edit to a set's membership between two reads: one more member course."""
        member_of(
            self.world.seed,
            membership_table(self.world.tables),
            self._sets[set_name],
            self.course_row(course),
        )
        self.session.flush()

    def drop_member(self, set_name: str, course: str) -> None:
        """An edit to a set's membership between two reads: one member course removed."""
        from sqlalchemy import delete

        membership = membership_table(self.world.tables)
        set_column = one_key_column_to(
            membership, COMPARISON_SET_TABLE, self.key_of(COMPARISON_SET_TABLE)
        )
        course_column = one_key_column_to(membership, COURSE_TABLE, self.key_of(COURSE_TABLE))
        removed = self.session.execute(
            delete(membership).where(
                membership.c[set_column] == self.set_id(set_name),
                membership.c[course_column] == self.course_id(course),
            )
        )
        if removed.rowcount != 1:
            pytest.fail(
                f"Removing course {course!r} from set {set_name!r} removed {removed.rowcount} "
                "membership rows; the edit this test makes is one."
            )
        self.session.flush()

    # -- the reads under test ---------------------------------------------------

    def series(self, set_name: str, reader: str) -> Any:
        """`named_set_series` for one set, read by one person, in this world's term."""
        self.session.flush()
        read = benchmarks_symbol(NAMED_SET_SERIES)
        return read(
            self.session,
            set_id=self.set_id(set_name),
            scope=self.scope(reader),
            term_id=self.world.term_id(),
            settings=self.settings,
        )

    def section_benchmarks(self, label: str, *, reader: str | None = None) -> Any:
        """`section_benchmarks` for one section's course week 2, with or without a reader.

        Without a reader `scope=None` is passed explicitly, which is the call every
        instructor report makes once the parameter has no default (E9-05's fix
        round, P2: a caller that forgets the reader must not be sealed against
        the instructors alone by default). A `section_benchmarks` with no `scope`
        parameter at all is a named failure, not a `TypeError`.
        """
        import inspect

        self.session.flush()
        read = benchmarks_symbol(SECTION_BENCHMARKS)
        if "scope" not in inspect.signature(read).parameters:
            pytest.fail(
                "`section_benchmarks` takes no `scope`. E9-05's interface: "
                "`section_benchmarks(session, *, section_id, course_week, streams, cutoffs, "
                "scope: ActorScope | None)`, keyword-only and required, the reader entering the "
                "seal as one more person whose known sections are her purview and the sections "
                "she teaches (SPEC §5.1); every instructor caller writes `scope=None`."
            )
        return read(
            self.session,
            section_id=self.section_id(label),
            course_week=THE_COURSE_WEEK,
            streams=STREAMS,
            cutoffs=SECTION_CUTOFFS,
            scope=None if reader is None else self.scope(reader),
        )


# ---------------------------------------------------------------------------
# Worlds two seal modules share.
# ---------------------------------------------------------------------------

HERO_RESPONDENTS = 2
HERO_RATING, HERO_HOURS = Decimal("5"), Decimal("1.5")
LEAD_SET_RATING, LEAD_SET_HOURS = Decimal("2"), Decimal("3.5")
REST_OF_U_RATING, REST_OF_U_HOURS = Decimal("3"), Decimal("11.5")


def one_section_course(world: PurviewWorld, label: str, department: str, *, alone: bool) -> None:
    """A course named `label` with one section named `label`; led by nobody else if `alone`."""
    world.course(label, department=department)
    world.section(label, course=label)
    if alone:
        world.led_alone(label)


def the_hero_answers(world: PurviewWorld, label: str = "hero") -> None:
    """Two students answer in one section at course week 2 (5, and 1.5 hours)."""
    world.answer(
        [label],
        respondents=HERO_RESPONDENTS,
        prefix=f"e9-05-seal-{label}",
        rating=HERO_RATING,
        hours=HERO_HOURS,
    )


def a_lead_straddling_the_readers_department(
    world: PurviewWorld, *, lead_set: int, rest: int, chair: str | None
) -> None:
    """`home` holds the hero and `s0`; `s0`'s lead L also leads `l…` in `away`.

    - `home`: the hero (its course led by nobody else, so its default set is
      empty), taught by "the teacher", and `s0`, whose lead L also leads `l1…`
      in `away`. So the default set of `s0` — a section in `home` — less what a
      person holding `home` knows is `l…`, answered by `lead_set` people.
    - `away`: `l…` and `r…`, the rest of the university (each course led by
      nobody else, so no default set reaches it), answered by `rest` people.

    `chair` names who chairs `home`: a separate reader (E9-05 done-whens 7 and
    8), the hero's own instructor (done-when 16), or nobody (its twin).
    """
    world.build()
    sections = world.sections_minimum
    one_section_course(world, "hero", "home", alone=True)
    one_section_course(world, "s0", "home", alone=False)
    lead_set_labels = [f"l{index}" for index in range(1, sections + 1)]
    rest_labels = [f"r{index}" for index in range(1, sections + 1)]
    for label in lead_set_labels:
        one_section_course(world, label, "away", alone=False)
    for label in rest_labels:
        one_section_course(world, label, "away", alone=True)
    world.lead("lead L", "s0", *lead_set_labels)
    world.teach("the teacher", "hero")
    if chair is not None:
        world.chair(chair, "home")

    the_hero_answers(world)
    the_hero_answers(world, "s0")
    world.answer(
        lead_set_labels,
        respondents=lead_set,
        prefix="e9-05-seal-l",
        rating=LEAD_SET_RATING,
        hours=LEAD_SET_HOURS,
    )
    world.answer(
        rest_labels,
        respondents=rest,
        prefix="e9-05-seal-r",
        rating=REST_OF_U_RATING,
        hours=REST_OF_U_HOURS,
    )


def suppressed_count(value: Any) -> int:
    return sum(1 for figure in every_figure(value) if is_suppressed(figure))


def shown_count(value: Any) -> int:
    return sum(1 for figure in every_figure(value) if is_shown(figure))


@pytest.fixture
def purview_world(
    benchmark_world: BenchmarkWorld,
    supervision_graph: Any,
    authz: Any,
    window_settings: Any,
    pinned_benchmark_clock: Any,
) -> PurviewWorld:
    """The world E9-05's service tests are read over, **unbuilt** (`docs/MISTAKES.md` entry 44).

    Every row is on `db_session` and rolled back with the test: the benchmark
    world, the supervision graph and the clock override share that one session,
    which is also the session handed to the reads.
    """
    from fixtures.report_api import configured_benchmark_minimums

    return PurviewWorld(
        benchmark_world,
        supervision_graph,
        authz,
        window_settings,
        configured_benchmark_minimums,
    )
