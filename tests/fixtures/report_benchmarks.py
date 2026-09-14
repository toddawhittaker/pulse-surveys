"""E5-05 — the benchmark cohort one instructor's report is read against, and the members it serves.

Four test modules ask the same two things of this ticket: plant a comparison
population around the section `tests/fixtures/report_api.py`'s door already
teaches, and read the benchmark members out of the payload that door answers
with. A copy of either in each module is `docs/MISTAKES.md` entry 13, so both
live here.

**What this file decides, and what it refuses to.** Every member name below is
transcribed from E5-05's work order, which spells the wire shape member by
member:

    streams.instructor.benchmark = streams.course.benchmark = {
      "comparison": {"points": [{"course_week": 1, "mean": <ComparisonFigure>}]},
      "university": {"points": [...]}
    }
    workload_benchmark = {
      "comparison": {"mean": <ComparisonFigure>, "median": <ComparisonFigure>},
      "university":  {"mean": <ComparisonFigure>, "median": <ComparisonFigure>}
    }

and `<ComparisonFigure>` "serialises as `{"suppressed", "reason", "figure"}`
exactly as the existing top-level `comparison` member does". Nothing here invents
a spelling the work order leaves open: the two schema-level lookups this file does
make — which model the payload is served as, and what type the `comparison` member
is annotated with — are *discovered*, the way `tests/fixtures/report_api.py`
discovers the suppression helper, because E4-07 settled the mechanism and no name.

**Nothing here computes a figure a test reads back.** No mean, no median, no
count. The planter deals a plan the tables below state — how many sections, how
many people, and one hours value and two ratings per person — and every expected
mean or median is arithmetic the test module writes out by hand over those
values (`docs/MISTAKES.md` entries 19 and 30). The two counts a minimum is
compared against are stated per week as an **offset from the configured
minimum**, never as a number transcribed from `Settings`: a week is planted at
the minimum or one below it, and which absolute numbers those are is read from
`Settings` at plant time. The value tables are written for the minimums the
project is configured with today, so a configuration change is a loud failure
here naming the mismatch rather than a world that quietly stops being a boundary.

**Why the cohort is planted around E4-07's own door rather than in a world of its
own.** Criteria 1, 3 and 4 are all about what crosses the wire, and the wire is
the report route. `tests/fixtures/benchmark_views.py`'s `BenchmarkWorld` is the
machinery that plants sections, leads, students and answers, so it is wrapped
around the door's committed world rather than rebuilt: this file seeds the set's
courses and sections itself — because their level has to *equal the hero's*
rather than be chosen from a band — and delegates every student, enrolment,
response and answer to that class.

**Every guard is a plain function reached from a test body, never a fixture**
(`docs/MISTAKES.md` entry 44). `plant_the_benchmark_cohort` is called as the
first statement of a test, so a tree where E5-05 is unbuilt is a wall of FAILEDs
naming the missing member rather than errors inside somebody's setup.

**The environment and the clock** are the door's: `report_door` rides
`launch_driver_in` and therefore `configured_env`, and moves the development
clock past the last of the six windows before the launch, so every course week
this file plants into is closed and published wherever something asks.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, update

from fixtures.benchmark_views import (
    COURSE_NUMBER_COLUMN,
    COURSE_NUMBER_FOR_LEVEL,
    COURSE_TABLE,
    CURRENT_TERM,
    LEAD_FACULTY_MAPPING_TABLE,
    PERSON_TABLE,
    UG,
    BenchmarkWorld,
    PlantedSection,
    numbers_in,
)
from fixtures.report_api import (
    BENCHMARK_MIN_RESPONDENTS,
    BENCHMARK_MIN_SECTIONS,
    PAYLOAD_STREAM_KEY,
    STREAMS_MEMBER,
    TAUGHT_COHORT,
    ReportDoor,
    member,
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
    TERM_TABLE,
)

# ---------------------------------------------------------------------------
# The wire, as E5-05's work order spells it.
# ---------------------------------------------------------------------------

# The per-stream member and the two populations under it.
BENCHMARK_MEMBER = "benchmark"
COMPARISON_POPULATION = "comparison"
UNIVERSITY_POPULATION = "university"

# A series and one of its points.
POINTS_FIELD = "points"
POINT_WEEK_FIELD = "course_week"
POINT_MEAN_FIELD = "mean"

# The top-level workload member and the two figures each population carries.
WORKLOAD_BENCHMARK_MEMBER = "workload_benchmark"
MEAN_FIELD = "mean"
MEDIAN_FIELD = "median"

# One sealed comparison figure, whatever its provenance: "`<ComparisonFigure>`
# serialises as `{"suppressed", "reason", "figure"}` exactly as the existing
# top-level `comparison` member does" (work order, decision 2).
SUPPRESSED_FIELD = "suppressed"
REASON_FIELD = "reason"
FIGURE_FIELD = "figure"
FIGURE_MEMBERS = frozenset({SUPPRESSED_FIELD, REASON_FIELD, FIGURE_FIELD})

# Both populations, for the tests that make the same assertion of each.
POPULATIONS = (COMPARISON_POPULATION, UNIVERSITY_POPULATION)

BENCHMARK_MEMBERS_ARE_OWED = (
    "E5-05's work order settles the wire shape: each stream gains a `benchmark` member carrying a "
    f"`{COMPARISON_POPULATION}` and a `{UNIVERSITY_POPULATION}` series of "
    f"`{{{POINT_WEEK_FIELD}, {POINT_MEAN_FIELD}}}` points, and the payload gains a top-level "
    f"`{WORKLOAD_BENCHMARK_MEMBER}` carrying a `{MEAN_FIELD}` and a `{MEDIAN_FIELD}` for each of "
    "the same two populations. Every figure at every depth is a `ComparisonFigure` sealed by "
    "`comparison_after_suppression`, and the route assembles them — it never computes one."
)

# ---------------------------------------------------------------------------
# The cohort this file plants, and the values in it.
# ---------------------------------------------------------------------------

# The set's sections are cohort `F` — the hero's own start letter, so they run the
# hero's six weeks and their course weeks are the hero's course weeks. Any other
# six-week letter would be equally comparable (benchmarks align by course week,
# §5.1's past-referencing), and sharing the letter keeps one calendar in play.
SET_COHORT = TAUGHT_COHORT

# The lead who leads the hero's course and every set course. SPEC §5.1: "the
# default comparison set is the same Lead Faculty's courses filtered to matching
# length+level", so a world without this mapping has no default set at all.
THE_LEAD = "e5-05-lead"

# The course number every course in this world carries — the hero's is *updated*
# to it, so the hero and the set match on level by construction rather than by a
# level this file chose for one side. `course.level` is a stored generated column
# (ADR 0015), so a level is planted by choosing a number and never by writing one,
# and the control module reads every level back and requires them equal.
SHARED_COURSE_NUMBER = COURSE_NUMBER_FOR_LEVEL[UG]
LEVEL_COLUMN = "level"

# The four course weeks this world is planted into, by what each is for. Course
# week 1 is left alone — it is the week E4-07's own suite reads, and a world that
# changed what that week answers would be this ticket editing another ticket's
# premise.
#
#   - `WEEK_CLEAR` — both minimums cleared: the positive control, and the
#     reported week every "a figure is served" assertion drives.
#   - `WEEK_THIN_PEOPLE` — one person below the respondent minimum, sections
#     cleared.
#   - `WEEK_THIN_SECTIONS` — one section below the section minimum, people
#     cleared.
#   - `WEEK_CLEAR_TWIN` — the passing twin of both, in the same series, so no
#     suppression in this world is asserted anywhere near a series that could be
#     empty (`docs/MISTAKES.md` entries 3 and 9).
WEEK_CLEAR = 2
WEEK_THIN_PEOPLE = 3
WEEK_THIN_SECTIONS = 4
WEEK_CLEAR_TWIN = 5

# Offsets from the configured minimums, named so that "one below" is legible at
# every call site and so that no absolute minimum is written down here.
AT_MINIMUM = 0
ONE_BELOW = -1


@dataclass(frozen=True)
class WeekPlan:
    """What one course week of the comparison set is planted with.

    `sections` and `respondents` are **offsets** from the two configured
    minimums, because the promise §4.1 item 7 makes is about the configured
    numbers and a world written against transcribed ones would stop being a
    boundary the day either moved.

    The three value tuples carry one entry per respondent, in the order the
    planter deals them, so a test can state the multiset it planted and write its
    own arithmetic over it. They are inputs and never outputs: nothing here
    averages anything.
    """

    sections: int
    respondents: int
    hours: tuple[Decimal, ...]
    instructor_ratings: tuple[int, ...]
    course_ratings: tuple[int, ...]


def _repeated(value: Any, times: int) -> tuple[Any, ...]:
    return (value,) * times


# The values, week by week. Written out rather than generated, and chosen so that
# **no figure in this world is a number another figure could also be**: the four
# means, the four medians and the eight rating means are sixteen different
# values, none of them equal to a minimum, a count, a rate, or to anything
# E4-07's own world answers (its hero's workload mean is 10, its median 9, its
# rating means 4 and 3). A suppressed week's figures are therefore absent for the
# reason the test says, rather than absent because they were never distinct.
#
# Every hours value sits on the half-hour, which is the grid SPEC §3.2's workload
# question is answered on; every rating is an integer on the 1-5 Likert scale.
BENCHMARK_WEEKS: dict[int, WeekPlan] = {
    # 8 x 7.5 + 7 x 10.5 = 133.5 over 15 -> mean 8.9, median 7.5.
    # 12 x 4 + 3 x 2 = 54 over 15 -> instructor rating mean 3.6.
    # 6 x 1 + 9 x 4 = 42 over 15 -> course rating mean 2.8.
    WEEK_CLEAR: WeekPlan(
        sections=AT_MINIMUM,
        respondents=AT_MINIMUM,
        hours=(*_repeated(Decimal("7.5"), 8), *_repeated(Decimal("10.5"), 7)),
        instructor_ratings=(*_repeated(4, 12), *_repeated(2, 3)),
        course_ratings=(*_repeated(1, 6), *_repeated(4, 9)),
    ),
    # 10 x 4.5 + 4 x 11.5 = 91 over 14 -> mean 6.5, median 4.5.
    # 10 x 5 + 4 x 2 = 58 over 14 -> instructor rating mean 58/14.
    # 10 x 4 + 4 x 1 = 44 over 14 -> course rating mean 44/14.
    WEEK_THIN_PEOPLE: WeekPlan(
        sections=AT_MINIMUM,
        respondents=ONE_BELOW,
        hours=(*_repeated(Decimal("4.5"), 10), *_repeated(Decimal("11.5"), 4)),
        instructor_ratings=(*_repeated(5, 10), *_repeated(2, 4)),
        course_ratings=(*_repeated(4, 10), *_repeated(1, 4)),
    ),
    # 12 x 3.5 + 3 x 12.5 = 79.5 over 15 -> mean 5.3, median 3.5.
    # 11 x 5 + 4 x 1 = 59 over 15 -> instructor rating mean 59/15.
    # 11 x 4 + 4 x 1 = 48 over 15 -> course rating mean 3.2.
    WEEK_THIN_SECTIONS: WeekPlan(
        sections=ONE_BELOW,
        respondents=AT_MINIMUM,
        hours=(*_repeated(Decimal("3.5"), 12), *_repeated(Decimal("12.5"), 3)),
        instructor_ratings=(*_repeated(5, 11), *_repeated(1, 4)),
        course_ratings=(*_repeated(4, 11), *_repeated(1, 4)),
    ),
    # 8 x 5.5 + 7 x 8.5 = 103.5 over 15 -> mean 6.9, median 5.5.
    # 9 x 5 + 6 x 1 = 51 over 15 -> instructor rating mean 3.4.
    # 3 x 1 + 12 x 3 = 39 over 15 -> course rating mean 2.6.
    WEEK_CLEAR_TWIN: WeekPlan(
        sections=AT_MINIMUM,
        respondents=AT_MINIMUM,
        hours=(*_repeated(Decimal("5.5"), 8), *_repeated(Decimal("8.5"), 7)),
        instructor_ratings=(*_repeated(5, 9), *_repeated(1, 6)),
        course_ratings=(*_repeated(1, 3), *_repeated(3, 12)),
    ),
}


# ---------------------------------------------------------------------------
# The planted world.
# ---------------------------------------------------------------------------


@dataclass
class PlantedBenchmarkCohort:
    """What `plant_the_benchmark_cohort` put in the database, as it was asked for.

    Every count here is the plan's, not a reading of the database: the control
    module reads the counts back through E5-03's own set function and requires
    them to agree, which is what keeps "this week is one person short" a fact
    about rows rather than about a docstring.
    """

    world: BenchmarkWorld
    labels: tuple[str, ...]
    lead: Mapping[str, Any]
    level: Any
    hero_section_id: Any
    hero_course: Mapping[str, Any]
    sections_by_week: dict[int, tuple[str, ...]]
    respondents_by_week: dict[int, tuple[str, ...]]
    plans: Mapping[int, WeekPlan]

    def set_section_ids(self) -> list[Any]:
        """Every section of the default set, in label order."""
        return [self.world.section_id(label) for label in self.labels]

    def course_of(self, label: str) -> Mapping[str, Any]:
        return self.world.course_of(label)


def _door_chain(door: ReportDoor) -> dict[str, Any]:
    """The containment rows E4-07's world already seeded, as a chain to hang courses on.

    Reused rather than seeded again, because SPEC §8 permits one institution: a
    second containment spine under this world would be refused inside this
    fixture, which is `docs/MISTAKES.md` entry 13's closing sentence.
    """
    chain = dict(getattr(door.world.calendar, "chain", {}) or {})
    missing = [name for name in ("department", COURSE_TABLE) if name not in chain]
    if missing:
        pytest.fail(
            f"E4-07's world left no {missing} in its seeding chain; it left {sorted(chain)}. This "
            "planter hangs the comparison set's courses under the department the hero's own course "
            "sits in, because SPEC §8 permits one institution and a second spine would be refused "
            "inside this fixture."
        )
    return chain


def _require_minimums(
    minimums: Mapping[str, int], plans: Mapping[int, WeekPlan]
) -> tuple[int, int]:
    """The two configured minimums, checked against the value tables written for them."""
    sections = minimums[BENCHMARK_MIN_SECTIONS]
    respondents = minimums[BENCHMARK_MIN_RESPONDENTS]
    if sections < 2 or respondents < 2:
        pytest.fail(
            f"`{BENCHMARK_MIN_SECTIONS}` is {sections} and `{BENCHMARK_MIN_RESPONDENTS}` is "
            f"{respondents}. A minimum below two has no value beneath it that is still a "
            "comparison set, so neither near-miss week in this world can be planted at all."
        )
    for course_week, plan in sorted(plans.items()):
        wanted = respondents + plan.respondents
        for name, values in (
            ("hours", plan.hours),
            ("instructor_ratings", plan.instructor_ratings),
            ("course_ratings", plan.course_ratings),
        ):
            if len(values) != wanted:
                pytest.fail(
                    f"Course week {course_week} is planted with {wanted} respondents "
                    f"(`{BENCHMARK_MIN_RESPONDENTS}` is {respondents}), and its `{name}` table in "
                    f"tests/fixtures/report_benchmarks.py holds {len(values)}. The tables are "
                    "written out by hand so that every expected mean and median is arithmetic a "
                    "test writes over them; a changed minimum is a deliberate act that moves "
                    "these tables and the expectations in the test modules together."
                )
        if sections + plan.sections < 1:
            pytest.fail(
                f"Course week {course_week} asks for {sections + plan.sections} sections, which is "
                "not a population at all."
            )
    return sections, respondents


def plant_the_benchmark_cohort(
    door: ReportDoor,
    *,
    minimums: Mapping[str, int],
    plans: Mapping[int, WeekPlan] = BENCHMARK_WEEKS,
) -> PlantedBenchmarkCohort:
    """A default set around the door's own section, answered week by week to `plans`.

    In order: the hero's course is given a course number inside one of SPEC §8's
    bands (so the level both sides match on is a fact rather than a guess); the
    set's courses and sections are seeded under the same department and the same
    number; one Lead Faculty is mapped to all of them, the hero's course
    included; enough students are seeded to answer the widest week; and each
    week's respondents are dealt round-robin across that week's sections and
    answer the values the plan carries.

    **The hero is never in its own comparison set** (E5 breakdown decision 5) and
    this planter does not put it there: the set is the lead's *other* courses'
    sections. The hero's own answers stay exactly what E4-07's world planted, and
    they are what makes the university line — which keeps the whole population —
    a control that differs from the comparison line by the hero alone.

    Called from a test body. Every premise it cannot meet is a `pytest.fail`
    naming it (`docs/MISTAKES.md` entry 44).
    """
    sections, respondents = _require_minimums(minimums, plans)

    world = BenchmarkWorld(door.world)
    calendar = door.world.calendar
    world.terms[CURRENT_TERM] = calendar.term
    world.weeks[CURRENT_TERM] = dict(calendar.weeks)

    chain = _door_chain(door)
    spine = {
        name: chain[name] for name in ("institution", "college", "department") if name in chain
    }
    hero_course = chain[COURSE_TABLE]

    level = _give_every_course_one_level(world, hero_course)

    length_weeks, first_term_week, start = SEEDED_COHORTS[SET_COHORT]
    labels = tuple(f"set-{index}" for index in range(sections))
    for label in labels:
        course_chain = dict(spine)
        course = world.seed(
            COURSE_TABLE, course_chain, **{COURSE_NUMBER_COLUMN: SHARED_COURSE_NUMBER}
        )
        course_chain[TERM_TABLE] = calendar.term
        row = world.seed(
            SECTION_TABLE,
            course_chain,
            **{
                SECTION_CODE_COLUMN: (
                    f"{SET_COHORT}{COHORT_SECTION_ORDINAL}{COHORT_SECTION_MODALITY}"
                ),
                SECTION_LENGTH_COLUMN: length_weeks,
                SECTION_START_COLUMN: start,
                SECTION_END_COLUMN: start + timedelta(days=length_weeks * 7 - 1),
            },
        )
        world.sections[label] = PlantedSection(
            label=label,
            row=row,
            term=CURRENT_TERM,
            cohort=SET_COHORT,
            level=level,
            length_weeks=length_weeks,
            first_term_week=first_term_week,
            start_date=start,
            course=course,
        )

    lead = world.lead(THE_LEAD, *labels)
    world.seed(LEAD_FACULTY_MAPPING_TABLE, {PERSON_TABLE: lead, COURSE_TABLE: dict(hero_course)})

    students: list[Any] = []
    enrolled: list[set[str]] = []
    for index in range(respondents):
        label = labels[index % len(labels)]
        students.append(world.student(f"e5-05-respondent-{index:02d}", enrolled_in=(label,)))
        enrolled.append({label})

    sections_by_week: dict[int, tuple[str, ...]] = {}
    respondents_by_week: dict[int, tuple[str, ...]] = {}
    for course_week, plan in sorted(plans.items()):
        week_labels = labels[: sections + plan.sections]
        answering = range(respondents + plan.respondents)
        for index in answering:
            label = week_labels[index % len(week_labels)]
            if label not in enrolled[index]:
                world.enroll(students[index], label)
                enrolled[index].add(label)
            world.respond(
                label,
                course_week=course_week,
                student=students[index],
                workload=plan.hours[index],
                instructor_rating=plan.instructor_ratings[index],
                course_rating=plan.course_ratings[index],
            )
        sections_by_week[course_week] = week_labels
        respondents_by_week[course_week] = tuple(
            f"e5-05-respondent-{index:02d}" for index in answering
        )

    door.commit()
    return PlantedBenchmarkCohort(
        world=world,
        labels=labels,
        lead=lead,
        level=level,
        hero_section_id=door.rows.taught_section_id,
        hero_course=dict(hero_course),
        sections_by_week=sections_by_week,
        respondents_by_week=respondents_by_week,
        plans=plans,
    )


def _give_every_course_one_level(world: BenchmarkWorld, hero_course: Mapping[str, Any]) -> Any:
    """Put the hero's course on a course number inside a SPEC §8 band, and answer its level.

    The set's courses are seeded with the same number, so the two sides match on
    level because they carry the same input and not because this file wrote a
    level on either of them — `course.level` is a stored generated column
    (ADR 0015). The value is read back rather than assumed, because what §8's
    bands make of a number is the database's answer and not this fixture's.
    """
    table = require_table(world.tables, COURSE_TABLE)
    if LEVEL_COLUMN not in table.c:
        pytest.fail(
            f"`{COURSE_TABLE}` declares no `{LEVEL_COLUMN}` column (it declares "
            f"{[column.name for column in table.columns]}). SPEC §8's level bands are a stored "
            "generated column off `lms_number` (ADR 0015), and a comparison set matches on length "
            "and level exactly (§5.1)."
        )
    key = single_primary_key(table)
    world.session.execute(
        update(table)
        .where(table.c[key] == hero_course[key])
        .values(**{COURSE_NUMBER_COLUMN: SHARED_COURSE_NUMBER})
    )
    world.session.flush()
    level = world.session.execute(
        select(table.c[LEVEL_COLUMN]).where(table.c[key] == hero_course[key])
    ).scalar_one()
    if level is None:
        pytest.fail(
            f"The hero's course carries `{COURSE_NUMBER_COLUMN}` {SHARED_COURSE_NUMBER!r} and its "
            f"`{LEVEL_COLUMN}` came back null, so this world has no level for a comparison set to "
            "match on. SPEC §8's bands are `DEV`, `UG`, `UGGR`, `GR` and `DR`; the number is "
            "`COURSE_NUMBER_FOR_LEVEL` in tests/fixtures/benchmark_views.py, transcribed from "
            "those bands."
        )
    return level


def course_levels(world: BenchmarkWorld, courses: Sequence[Mapping[str, Any]]) -> list[Any]:
    """The stored level of each course row, read back from the database."""
    table = require_table(world.tables, COURSE_TABLE)
    key = single_primary_key(table)
    return [
        world.session.execute(
            select(table.c[LEVEL_COLUMN]).where(table.c[key] == course[key])
        ).scalar_one()
        for course in courses
    ]


def section_lengths(world: BenchmarkWorld, section_ids: Sequence[Any]) -> list[Any]:
    """The stored `length_weeks` of each section, read back from the database."""
    table = require_table(world.tables, SECTION_TABLE)
    key = single_primary_key(table)
    return [
        world.session.execute(
            select(table.c[SECTION_LENGTH_COLUMN]).where(table.c[key] == section_id)
        ).scalar_one()
        for section_id in section_ids
    ]


def lead_faculty_course_ids(world: BenchmarkWorld, person: Mapping[str, Any]) -> set[Any]:
    """Every course one person is mapped to lead, read back from `lead_faculty_mapping`."""
    table = require_table(world.tables, LEAD_FACULTY_MAPPING_TABLE)
    person_key = single_primary_key(require_table(world.tables, PERSON_TABLE))
    person_column = world.report.link(LEAD_FACULTY_MAPPING_TABLE, PERSON_TABLE)
    course_column = world.report.link(LEAD_FACULTY_MAPPING_TABLE, COURSE_TABLE)
    rows = world.session.execute(
        select(table.c[course_column]).where(table.c[person_column] == person[person_key])
    )
    return {row[0] for row in rows}


# ---------------------------------------------------------------------------
# Reading the benchmark members off a payload.
# ---------------------------------------------------------------------------


def stream_benchmark(body: Any, stream: str, population: str, answered: Any = None) -> Any:
    """`streams.<stream>.benchmark.<population>`, or a failure naming what is owed."""
    return member(
        body,
        STREAMS_MEMBER,
        PAYLOAD_STREAM_KEY[stream],
        BENCHMARK_MEMBER,
        population,
        answered=answered,
    )


def points_of(body: Any, stream: str, population: str, answered: Any = None) -> dict[int, Any]:
    """One panel's series as `{course_week: figure}`, by the work order's spelling.

    A week carried twice is a failure here rather than an index that silently
    keeps the last one: a series with a week in it twice is a series a chart draws
    twice, and neither a reader nor this suite could say which of the two is the
    comparison.
    """
    series = stream_benchmark(body, stream, population, answered=answered)
    points = member(series, POINTS_FIELD, answered=answered)
    if not isinstance(points, list):
        pytest.fail(
            f"`streams.{PAYLOAD_STREAM_KEY[stream]}.{BENCHMARK_MEMBER}.{population}."
            f"{POINTS_FIELD}` is {points!r}, which is not a list of points.\n\n"
            f"{BENCHMARK_MEMBERS_ARE_OWED}"
        )
    found: dict[int, Any] = {}
    for point in points:
        if not isinstance(point, dict) or POINT_WEEK_FIELD not in point:
            pytest.fail(
                f"A benchmark point is {point!r}, which names no `{POINT_WEEK_FIELD}`.\n\n"
                f"{BENCHMARK_MEMBERS_ARE_OWED}"
            )
        week = int(point[POINT_WEEK_FIELD])
        if week in found:
            pytest.fail(f"The {population} series carries two points for course week {week}.")
        if POINT_MEAN_FIELD not in point:
            pytest.fail(
                f"The point for course week {week} is {point!r}, which carries no "
                f"`{POINT_MEAN_FIELD}`.\n\n{BENCHMARK_MEMBERS_ARE_OWED}"
            )
        found[week] = _require_a_figure(
            point[POINT_MEAN_FIELD],
            f"`streams.{PAYLOAD_STREAM_KEY[stream]}.{BENCHMARK_MEMBER}.{population}` at course "
            f"week {week}",
        )
    return found


def _require_a_figure(figure: Any, where: str) -> Any:
    """One member that has to be a sealed comparison figure, or a failure naming it."""
    if not isinstance(figure, dict):
        pytest.fail(
            f"{where} is {figure!r} rather than an object. Every benchmark member at every depth "
            f"is a sealed comparison figure, serialising as {sorted(FIGURE_MEMBERS)}: a bare "
            "number is a figure nothing sealed, and `null` is a member no panel can draw a "
            f"suppression notice from.\n\n{BENCHMARK_MEMBERS_ARE_OWED}"
        )
    return figure


def workload_figures(body: Any, population: str, answered: Any = None) -> dict[str, Any]:
    """`workload_benchmark.<population>`, as `{mean, median}`."""
    figures = member(body, WORKLOAD_BENCHMARK_MEMBER, population, answered=answered)
    for name in (MEAN_FIELD, MEDIAN_FIELD):
        if not isinstance(figures, dict) or name not in figures:
            pytest.fail(
                f"`{WORKLOAD_BENCHMARK_MEMBER}.{population}` is {figures!r}, which carries no "
                f"`{name}`. SPEC §5.1 puts both on the report — 'workload mean/median for the "
                "section against comparison-set and university figures' — and §4.1 item 7 covers "
                "'a mean, a median, or any other statistic', so each is suppressed on its own.\n\n"
                f"{BENCHMARK_MEMBERS_ARE_OWED}"
            )
    return {
        name: _require_a_figure(figures[name], f"`{WORKLOAD_BENCHMARK_MEMBER}.{population}.{name}`")
        for name in (MEAN_FIELD, MEDIAN_FIELD)
    }


def every_benchmark_figure(body: Any, answered: Any = None) -> dict[str, Any]:
    """Every comparison figure the benchmark members carry, keyed by where it sits.

    Walked by the wire shape the work order settles rather than by hunting for
    objects that look like figures: the point of criterion 3 is that *each* of
    these members is a sealed figure, so a member missing from the payload is a
    failure naming it here rather than one fewer entry in a set nobody counted.
    """
    found: dict[str, Any] = {}
    for stream, key in PAYLOAD_STREAM_KEY.items():
        for population in POPULATIONS:
            for week, figure in points_of(body, stream, population, answered=answered).items():
                found[f"streams.{key}.{BENCHMARK_MEMBER}.{population}.week {week}"] = figure
    for population in POPULATIONS:
        figures = workload_figures(body, population, answered=answered)
        for name, figure in figures.items():
            found[f"{WORKLOAD_BENCHMARK_MEMBER}.{population}.{name}"] = figure
    for where, figure in sorted(found.items()):
        if not isinstance(figure, dict):
            pytest.fail(
                f"`{where}` is {figure!r} rather than an object. Every benchmark member at every "
                "depth is a sealed comparison figure, which serialises as "
                f"{sorted(FIGURE_MEMBERS)} — a bare number there is a figure nothing sealed, and "
                "`null` is a member a panel cannot draw a suppression notice from.\n\n"
                f"{BENCHMARK_MEMBERS_ARE_OWED}"
            )
    return found


def carries_number(figure: Any, expected: Any) -> bool:
    """Whether a serialized comparison figure holds this number anywhere inside it.

    The number rather than "any number", because a figure may legitimately carry
    members beside the statistic and a reader that counted those would report
    every suppressed figure as shown.
    """
    return any(found == pytest.approx(float(expected)) for found in numbers_of(figure))


def numbers_of(figure: Any) -> list[float]:
    """Every number a serialized comparison figure holds, at any depth.

    **A numeric string counts as a number**, which is the one place this reader
    is wider than `fixtures/benchmark_views.py`'s. E5-05 settles that the figures
    cross the wire and does not settle the JSON type a statistic is written in —
    pydantic serializes a `Decimal` as a string and a `float` as a number, and
    both are spellings of the same statistic. §4.1 item 7 is about the figure
    being *shown*, so a test that only recognised one spelling would read a
    suppressed member off a payload carrying the number as text.
    """
    found = list(numbers_in(figure))
    for text in _strings_in(figure):
        try:
            found.append(float(text))
        except ValueError:
            continue
    return found


def _strings_in(value: Any) -> list[str]:
    """Every string a serialized structure holds, at any depth."""
    if isinstance(value, dict):
        return [found for item in value.values() for found in _strings_in(item)]
    if isinstance(value, list | tuple):
        return [found for item in value for found in _strings_in(item)]
    return [value] if isinstance(value, str) else []


def a_suppressed_figures_complaint(figure: Any, where: str) -> str:
    """The failure message a member that should be suppressed and empty is read with."""
    return (
        f"{where} is {figure!r}.\n\n"
        "The README sketch's rule, which E5-05's criterion 3 quotes: a suppressed member says "
        "`suppressed`, a one-word reason and **nothing else** — no counts, no points, no set size, "
        "because '2 sections' under a suppression is itself the inference §4.1 item 7 exists to "
        "prevent."
    )


# ---------------------------------------------------------------------------
# The schema, for the tests that hand it a figure the chokepoint never sealed.
# ---------------------------------------------------------------------------


def report_payload_model(contract: Any) -> Any:
    """The model the report payload is served as — the wire boundary itself.

    Found by the member E4's sketch puts at the top of the payload, exactly as
    `report_api_contract.comparison_type` finds the comparison type: one model in
    `app.schemas.report` carrying a `comparison` member. A copy of the same walk
    lives in E4-07's own invariant module; it is copied rather than imported
    because a test module is not importable machinery, and this is the shared home
    for the E5-05 modules that need it (`docs/MISTAKES.md` entry 13).
    """
    schema = contract.schema()
    models = [
        value
        for name, value in vars(schema).items()
        if not name.startswith("_")
        and isinstance(value, type)
        and contract.comparison_member in (getattr(value, "model_fields", None) or {})
    ]
    if len(models) != 1:
        pytest.fail(
            f"`{contract.schema_module_name}` declares {len(models)} models carrying a "
            f"`{contract.comparison_member}` member ({[model.__name__ for model in models]}). This "
            "suite needs one to hand a payload to."
        )
    return models[0]


def an_unsealed_figure(figure_type: Any, *, figure: Any) -> Any:
    """A comparison figure carrying a number that no chokepoint ever sealed.

    Built with `model_construct`, which runs neither the constructor nor its token
    check — the documented bypass E4-07's security round found, and the only way a
    test outside `app.services.reporting` can hold such a value at all. It is
    *unsuppressed* and carries the figure, because that is the dangerous state:
    §4.1 item 7 is about the figure, not the flag.

    A field this cannot fill is a failure naming it rather than a guess. That
    matters: E4-07's own version of this helper survived a mutation by filling a
    field with a value its annotation refused, so pydantic objected before the
    guard was ever consulted and the test was green either way.
    """
    fields = dict(getattr(figure_type, "model_fields", None) or {})
    values: dict[str, Any] = {}
    for name in fields:
        if name == SUPPRESSED_FIELD:
            values[name] = False
        elif name == REASON_FIELD:
            values[name] = None
        elif name == FIGURE_FIELD:
            values[name] = figure
        else:
            pytest.fail(
                f"`{figure_type.__name__}` declares a field `{name}` this suite has no value for; "
                f"it fills {sorted(FIGURE_MEMBERS)}, which is what E5-05's work order says a "
                "`ComparisonFigure` serialises as. A fourth member is taught in "
                "`an_unsealed_figure` in tests/fixtures/report_benchmarks.py — and a guess here is "
                "what let a mutation survive the first time."
            )
    missing = sorted(FIGURE_MEMBERS - set(fields))
    if missing:
        pytest.fail(
            f"`{figure_type.__name__}` declares {sorted(fields)} and carries no {missing}. E5-05's "
            "work order settles the serialization as "
            f"{sorted(FIGURE_MEMBERS)}."
        )
    return figure_type.model_construct(**values)


def through_the_boundary(model: Any, report: Any, *, named: str) -> tuple[Any, str | None]:
    """Serialize a report through the schema, answering what the wire got.

    Three outcomes are correct and this reader accepts all three, because E5-05
    settles the property and leaves the mechanism to the implementer: the boundary
    refuses the report, serializing it is refused, or it serializes with the
    figure gone. Only a figure that comes out the other side is a failure.

    **A refusal counts only if it names the member that was tampered with.** A
    reader that counted any exception has a second way to be green — a payload
    that cannot round-trip through its own schema raises here too — and that is
    `docs/MISTAKES.md` entry 3 one level below where a test usually looks for it.
    """
    try:
        validated = model.model_validate(report)
    except Exception as refused:
        return None, _refusal_about(refused, named, "the response boundary refused the report")
    try:
        return validated.model_dump(mode="json"), None
    except Exception as refused:
        return None, _refusal_about(refused, named, "serializing the report was refused")


@pytest.fixture
def benchmark_cohort() -> Callable[..., PlantedBenchmarkCohort]:
    """The planter, handed over as a factory a test calls from its own body.

    A factory rather than a built world, for `docs/MISTAKES.md` entry 44's
    reason: every premise this planter cannot meet — a missing containment chain,
    a level the bands do not answer, a value table written for another minimum —
    has to fail inside the test that asked, so an unbuilt or misconfigured tree is
    a FAILED naming the deliverable rather than an error in somebody's setup.

    It is also what makes this module a plugin rather than a plain import, which
    is how `tests/conftest.py`'s tuple is meant to be read.
    """
    return plant_the_benchmark_cohort


def _refusal_about(refused: BaseException, named: str, what: str) -> str:
    """One refusal, judged: the guard firing on `named`, or a red nothing follows from."""
    errors = getattr(refused, "errors", None)
    located: list[str] = []
    if callable(errors):
        try:
            for error in errors():
                located.extend(str(part) for part in (error.get("loc") or ()))
        except Exception:  # noqa: S110  # pragma: no cover - not this test's subject
            pass
    if named in located or named in str(refused):
        return f"{what} ({type(refused).__name__}: {refused})"
    pytest.fail(
        f"{what}, and the refusal does not name `{named}`: {type(refused).__name__}: {refused}.\n\n"
        "This test will not call that a pass, because it cannot tell a closed chokepoint from a "
        "payload that does not round-trip through its own schema. Either the boundary is refusing "
        "for a reason that has nothing to do with the benchmark figure, or the guard names its "
        "field some other way — `_refusal_about` in tests/fixtures/report_benchmarks.py is where a "
        "spelling is taught."
    )
