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
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, update

from fixtures.benchmark_views import (
    COHORTS_BY_TERM,
    COURSE_NUMBER_COLUMN,
    COURSE_NUMBER_FOR_LEVEL,
    COURSE_RATING_POSITION,
    COURSE_TABLE,
    CURRENT_TERM,
    LEAD_FACULTY_MAPPING_TABLE,
    PERSON_TABLE,
    UG,
    WORKLOAD_POSITION,
    BenchmarkWorld,
    PlantedSection,
    numbers_in,
)
from fixtures.grading import RESPONSE_SECTION_COLUMN, RESPONSE_WEEK_COLUMN
from fixtures.report_api import (
    BENCHMARK_MIN_RESPONDENTS,
    BENCHMARK_MIN_SECTIONS,
    EITHER_SIDE_OF_A_CLOSE,
    INSTRUCTOR_ROLE,
    PAYLOAD_STREAM_KEY,
    PUBLISHED_WEEKS_FIELD,
    STREAMS_MEMBER,
    TAUGHT_COHORT,
    TERM_WEEK_OF_COURSE_WEEK,
    WEEK_MEMBER,
    ReportDoor,
    member,
)
from fixtures.report_views import FIRST_VERSION
from fixtures.submit import (
    ANSWER_TABLE,
    QUESTION_TABLE,
    RESPONSE_TABLE,
    WORKLOAD_HOURS_COLUMN,
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
    WINDOW_CLOSES_COLUMN,
    WINDOW_SECTION_COLUMN,
    WINDOW_WEEK_COLUMN,
    WINDOWS_BY_TERM_WEEK,
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

# The workload hours the hero's own respondents report **at the reported week**,
# and only there. Two values, because E4-07's world gives the hero two
# respondents in that week; the planter refuses to deal them if that ever stops
# being true, rather than spreading them over a count it did not expect.
#
# **Why this exists.** Without it the hero contributes no hours at all, so the
# university workload pair is *numerically* the comparison pair over the same
# rows — and swapping the two populations behind `workload_benchmark` in the
# assembler changes nothing any test can see. That is `docs/MISTAKES.md` entry
# 30's shape (a world that cannot tell the two answers apart) and it survived the
# mutation battery twice. Both values sit above every hours value the comparison
# set reports, so the union's median moves as well as its mean.
HERO_WORKLOAD_HOURS = (Decimal("13.5"), Decimal("14.5"))

# The course rating the hero's own respondents give in the four benchmark weeks —
# see `_the_hero_answers_the_course_question` for why this planter writes it and
# E4-07's fixture does not. An integer on SPEC §3.2's 1-5 scale, and a value
# nothing reads back as an answer: the university line keeps the hero, and no
# test here hand-computes a university figure, so this exists to make the hero a
# *contributor* to the course panel and for nothing else.
HERO_COURSE_RATING = 3

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
#
# **Written for a respondent minimum of 10**, the value SPEC §11 question 1
# settles (E5-14, 2026-09-22): a week at the minimum holds ten entries per table
# and a week one below it nine. Every even-sized table is split unevenly (6 and 4,
# 8 and 2, 7 and 3), because an even split puts the fifth and sixth values either
# side of the gap and makes the median the mean — two statistics this world has to
# keep apart.
BENCHMARK_WEEKS: dict[int, WeekPlan] = {
    # 6 x 7.5 + 4 x 9.5 = 45 + 38 = 83 over 10 -> mean 8.3; sorted, the fifth and
    # sixth of ten are both 7.5 -> median 7.5.
    # 8 x 4 + 2 x 2 = 36 over 10 -> instructor rating mean 3.6.
    # 4 x 1 + 6 x 4 = 28 over 10 -> course rating mean 2.8.
    WEEK_CLEAR: WeekPlan(
        sections=AT_MINIMUM,
        respondents=AT_MINIMUM,
        hours=(*_repeated(Decimal("7.5"), 6), *_repeated(Decimal("9.5"), 4)),
        instructor_ratings=(*_repeated(4, 8), *_repeated(2, 2)),
        course_ratings=(*_repeated(1, 4), *_repeated(4, 6)),
    ),
    # 6 x 4.5 + 3 x 10.5 = 27 + 31.5 = 58.5 over 9 -> mean 6.5; sorted, the fifth
    # of nine is 4.5 -> median 4.5.
    # 7 x 5 + 2 x 2 = 39 over 9 -> instructor rating mean 39/9.
    # 7 x 4 + 2 x 1 = 30 over 9 -> course rating mean 30/9.
    WEEK_THIN_PEOPLE: WeekPlan(
        sections=AT_MINIMUM,
        respondents=ONE_BELOW,
        hours=(*_repeated(Decimal("4.5"), 6), *_repeated(Decimal("10.5"), 3)),
        instructor_ratings=(*_repeated(5, 7), *_repeated(2, 2)),
        course_ratings=(*_repeated(4, 7), *_repeated(1, 2)),
    ),
    # 8 x 3.5 + 2 x 12.5 = 28 + 25 = 53 over 10 -> mean 5.3; the fifth and sixth of
    # ten are both 3.5 -> median 3.5.
    # 7 x 5 + 3 x 1 = 38 over 10 -> instructor rating mean 3.8.
    # 7 x 4 + 3 x 1 = 31 over 10 -> course rating mean 3.1.
    WEEK_THIN_SECTIONS: WeekPlan(
        sections=ONE_BELOW,
        respondents=AT_MINIMUM,
        hours=(*_repeated(Decimal("3.5"), 8), *_repeated(Decimal("12.5"), 2)),
        instructor_ratings=(*_repeated(5, 7), *_repeated(1, 3)),
        course_ratings=(*_repeated(4, 7), *_repeated(1, 3)),
    ),
    # 6 x 5.5 + 4 x 8.5 = 33 + 34 = 67 over 10 -> mean 6.7; the fifth and sixth of
    # ten are both 5.5 -> median 5.5.
    # 6 x 5 + 4 x 1 = 34 over 10 -> instructor rating mean 3.4.
    # 2 x 1 + 8 x 3 = 26 over 10 -> course rating mean 2.6.
    WEEK_CLEAR_TWIN: WeekPlan(
        sections=AT_MINIMUM,
        respondents=AT_MINIMUM,
        hours=(*_repeated(Decimal("5.5"), 6), *_repeated(Decimal("8.5"), 4)),
        instructor_ratings=(*_repeated(5, 6), *_repeated(1, 4)),
        course_ratings=(*_repeated(1, 2), *_repeated(3, 8)),
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
    # The containment rows E4-07's world already seeded, down to the department.
    # Kept so a test can hang a further course beside the set's without a second
    # institution (SPEC §8 permits one; see `_door_chain`).
    spine: Mapping[str, Any]

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
        _the_hero_answers_the_course_question(world, door, course_week)

    _the_hero_reports_workload_hours(world, door, WEEK_CLEAR)
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
        spine=dict(spine),
    )


def plant_a_section_beside(
    cohort: PlantedBenchmarkCohort,
    label: str,
    *,
    letter: str,
    term: str = CURRENT_TERM,
    led: bool = True,
    course: Mapping[str, Any] | None = None,
    weeks_later: int = 0,
    ordinal: str = COHORT_SECTION_ORDINAL,
) -> PlantedSection:
    """One more section at the set's level, on a course of its own, answered by nobody yet.

    For E5-14's two report-level modules, which need sections the cohort does not
    have: a later-starting cohort of the same length, a prior-term section, and
    sections outside the default set. The course carries the set's number, so its
    level is the set's by construction (ADR 0015); `letter` is looked up in the
    start-letter map of `term`, so the length and the start date are the seed's
    facts rather than this helper's.

    `led` maps the cohort's lead to the new course, which puts the section in the
    hero's default set; left false, the course has no lead at all, so the section
    is in the university population and outside the default set — the
    complement E5-14's university-sealing ruling is about.

    A prior-term section builds the prior term on first use, under the same world.

    **Round 3 (E5-14) adds three knobs**, for the reader-group worlds:
    - `course` hangs the section on an existing course (the hero's, for a
      second section of the same course) instead of a new one; `led` is then
      ignored, because whoever leads that course already does.
    - `weeks_later` starts the section that many weeks after its letter's start
      date, so two sections of one length can close the same course week a week
      apart. Only the stored start date and this world's week arithmetic move;
      the code keeps the letter's shape.
    - `ordinal` keeps two codes on one course and term distinct.
    """
    world = cohort.world
    if term not in world.terms:
        world.build_prior_term()
    letters = COHORTS_BY_TERM[term]
    if letter not in letters:
        pytest.fail(
            f"The {term} term's start-letter map has no {letter!r}; it has {sorted(letters)}."
        )
    length_weeks, first_term_week, start = letters[letter]
    first_term_week += weeks_later
    start += timedelta(days=7 * weeks_later)
    course_chain = dict(cohort.spine)
    if course is None:
        course = world.seed(
            COURSE_TABLE, course_chain, **{COURSE_NUMBER_COLUMN: SHARED_COURSE_NUMBER}
        )
    else:
        course_chain[COURSE_TABLE] = course
        led = False
    course_chain[TERM_TABLE] = world.term_row(term)
    row = world.seed(
        SECTION_TABLE,
        course_chain,
        **{
            SECTION_CODE_COLUMN: f"{letter}{ordinal}{COHORT_SECTION_MODALITY}",
            SECTION_LENGTH_COLUMN: length_weeks,
            SECTION_START_COLUMN: start,
            SECTION_END_COLUMN: start + timedelta(days=length_weeks * 7 - 1),
        },
    )
    planted = PlantedSection(
        label=label,
        row=row,
        term=term,
        cohort=letter,
        level=cohort.level,
        length_weeks=length_weeks,
        first_term_week=first_term_week,
        start_date=start,
        course=course,
    )
    world.sections[label] = planted
    if led:
        world.seed(LEAD_FACULTY_MAPPING_TABLE, {PERSON_TABLE: cohort.lead, COURSE_TABLE: course})
    return planted


def hero_window_close(world: BenchmarkWorld, door: ReportDoor, course_week: int) -> datetime:
    """*T(w)*: the hero section's own `survey_window.closes_at` for one course week, read back.

    Read from the database rather than from the hand-written calendar, because
    the owner's freeze-at-close ruling defines the cutoff as *that row's* close —
    which instant E4-07's world gave it is that fixture's business.
    """
    table = require_table(world.tables, SURVEY_WINDOW_TABLE)
    world.session.flush()
    found = list(
        world.session.execute(
            select(table.c[WINDOW_CLOSES_COLUMN]).where(
                table.c[WINDOW_SECTION_COLUMN] == door.rows.taught_section_id,
                table.c[WINDOW_WEEK_COLUMN] == door.rows.week_id(course_week),
            )
        ).scalars()
    )
    if len(found) != 1:
        pytest.fail(
            f"The hero section has {len(found)} survey windows for course week {course_week}; the "
            "freeze-at-close cutoff is its one window's close, so this world cannot say what "
            "T(w) is."
        )
    return found[0]


def teach(door: ReportDoor, section_id: Any, *, person: Any = None) -> Any:
    """Give `person` (the door's own instructor by default) a teaching grant on one section.

    The same row `plant_a_second_taught_section` in `tests/fixtures/report_api.py`
    writes, for the same reason that fixture gives: E4-07 resolves a request's
    section scope from the `teaching_instructor` view on every read, so a grant
    committed after the launch is in scope for the next request. It is also the
    row E5-14's reader group *R* is resolved from. Answers the person's key.
    """
    who = door.person_id if person is None else person
    if who is None or door.graph is None:
        pytest.fail(
            "This door holds no instructor person, so there is nobody to grant a teaching "
            "scope to."
        )
    door.graph.assign(INSTRUCTOR_ROLE, scope=section_id, person=who)
    return who


def publish_every_week(world: BenchmarkWorld, label: str) -> None:
    """Seed one section's window for every course week it runs, at the hand-written instants.

    A section's report publishes the weeks whose windows have closed, and a
    section nobody answered has no window rows until something seeds them — so
    a section whose *own report* a test reads needs them, answered or not.
    """
    planted = world.section(label)
    for course_week in range(1, planted.length_weeks + 1):
        world.window(label, world.term_week_of(label, course_week))


def answer_once(
    cohort: PlantedBenchmarkCohort,
    label: str,
    *,
    subject: str,
    course_week: int,
    workload: Decimal | None = Decimal("30.0"),
    rating: int = 1,
    last_submitted_at: datetime | None = None,
) -> None:
    """One new student in `label` answers one course week, every question.

    The defaults sit far from every value the cohort plants (hours 3.5-12.5), so
    a row that is counted moves the means it reaches. `workload=None` answers the
    two ratings and leaves the hours unanswered (no `answer` row), which is a
    response with a week row and no hour-reporter.
    """
    world = cohort.world
    student = world.student(subject, enrolled_in=(label,))
    world.respond(
        label,
        course_week=course_week,
        student=student,
        workload=workload,
        instructor_rating=rating,
        course_rating=rating,
        last_submitted_at=last_submitted_at,
    )


def benchmark_members_of(
    door: ReportDoor, *, course_week: int, section_id: Any = None
) -> dict[str, str]:
    """Every benchmark member of one report's payload, as canonical JSON, for byte comparison.

    Both streams' `benchmark` member and the top-level `workload_benchmark`. Read
    for the door's own section unless `section_id` names another the door's
    instructor teaches.
    """
    import json

    body, answered = door.payload(course_week=course_week, section_id=section_id)
    found = {
        f"streams.{key}.{BENCHMARK_MEMBER}": member(
            body, STREAMS_MEMBER, key, BENCHMARK_MEMBER, answered=answered
        )
        for key in PAYLOAD_STREAM_KEY.values()
    }
    found[WORKLOAD_BENCHMARK_MEMBER] = member(body, WORKLOAD_BENCHMARK_MEMBER, answered=answered)
    return {where: json.dumps(held, sort_keys=True) for where, held in found.items()}


def hero_responses(
    world: BenchmarkWorld, door: ReportDoor, course_week: int
) -> list[Mapping[str, Any]]:
    """Every `response` row the hero section holds in one of its course weeks.

    Read back rather than assumed: which of E4-07's respondents answered which
    week is that fixture's business, and a planter that assumed a count would
    write the hero's course ratings onto rows that are not there.
    """
    table = require_table(world.tables, RESPONSE_TABLE)
    world.session.flush()
    rows = world.session.execute(
        select(table).where(
            table.c[RESPONSE_SECTION_COLUMN] == door.rows.taught_section_id,
            table.c[RESPONSE_WEEK_COLUMN] == door.rows.week_id(course_week),
        )
    ).mappings()
    return [dict(row) for row in rows]


def hero_answers_to(
    world: BenchmarkWorld, door: ReportDoor, course_week: int, position: int
) -> int:
    """How many of the hero's responses in one course week answered one question.

    The number a per-stream figure's population is counted in: E5-04 seals every
    figure against the distinct people who answered **that stream**, so "the hero
    contributes to this line" is a claim about answer rows at one position and
    never about responses.
    """
    answers = require_table(world.tables, ANSWER_TABLE)
    response_column = world.report.link(ANSWER_TABLE, RESPONSE_TABLE)
    question_column = world.report.link(ANSWER_TABLE, QUESTION_TABLE)
    question = world.report.questions[FIRST_VERSION][position]
    key = world.key_of(RESPONSE_TABLE)
    response_ids = [row[key] for row in hero_responses(world, door, course_week)]
    if not response_ids:
        return 0
    world.session.flush()
    rows = world.session.execute(
        select(answers.c[response_column]).where(
            answers.c[response_column].in_(response_ids),
            answers.c[question_column] == question[world.key_of(QUESTION_TABLE)],
        )
    )
    return len(list(rows))


def _the_hero_answers_the_course_question(
    world: BenchmarkWorld, door: ReportDoor, course_week: int
) -> None:
    """Give each of the hero's respondents in this week a course rating too.

    **Why this is here, and why it is not in `tests/fixtures/report_api.py`.**
    E4-07's world writes a course rating only in its full week, course week 1
    (the `ANSWERED_BY` loop), so in every week this ticket plants into the hero's
    respondents answer the instructor question and nothing else. E5-04 seals each
    figure against its own contributors — the distinct people who answered *that*
    stream — so without this the university **course** line at a benchmark week
    is computed over the comparison set's rows alone, and the module docstring's
    premise, "the same rows plus the hero", is false in that currency. The ruling
    on `docs/disputes/E5-05-02.md` settles the repair here, in this ticket's own
    fixture: E4-07's world is another ticket's premise and keeps its own answers.

    The rating is written onto the hero's **existing** responses rather than as
    new ones, so no count of people or of responses in E4-07's world moves —
    only which questions those people answered. What the planted world really
    holds is read back from the database by
    `test_the_report_benchmark_world_plants_what_it_claims.py`.
    """
    for response in hero_responses(world, door, course_week):
        world.report.answer(
            response, COURSE_RATING_POSITION, HERO_COURSE_RATING, version=FIRST_VERSION
        )


def _the_hero_reports_workload_hours(
    world: BenchmarkWorld, door: ReportDoor, course_week: int
) -> None:
    """Give the hero's respondents in the reported week their own workload hours.

    **Only the reported week, deliberately.** The hero is in the university
    population and out of the comparison set (E5 breakdown decision 5), so these
    hours are the whole of the difference between the two workload members on the
    wire. Written at one week rather than at all four because the two near-miss
    weeks are about a *comparison* figure being suppressed, and moving the
    university population there would change what those weeks are for.

    E4-07's world writes the hero's hours in its own full week (course week 1)
    and nowhere else, so nothing is overwritten here. The count is a premise
    rather than an assumption: if the hero's respondents in that week are not as
    many as there are values to give them, this stops and says so, because the
    university mean and median the tests assert are arithmetic over exactly these
    values plus the comparison set's.
    """
    responses = hero_responses(world, door, course_week)
    if len(responses) != len(HERO_WORKLOAD_HOURS):
        pytest.fail(
            f"The hero section holds {len(responses)} responses in course week {course_week} and "
            f"`HERO_WORKLOAD_HOURS` carries {len(HERO_WORKLOAD_HOURS)} values. The university "
            "workload mean and median asserted by "
            "`test_the_report_serves_three_lines_per_panel.py` are worked out by hand over exactly "
            "these values and the comparison set's, so a different number of respondents is a "
            "world whose arithmetic nobody has done — `HERO_WORKLOAD_HOURS` in "
            "tests/fixtures/report_benchmarks.py and those expectations move together."
        )
    for response, hours in zip(responses, HERO_WORKLOAD_HOURS, strict=True):
        world.report.answer(response, WORKLOAD_POSITION, hours, version=FIRST_VERSION)


def hero_workload_hours(world: BenchmarkWorld, door: ReportDoor, course_week: int) -> list[Any]:
    """The workload values the hero's respondents actually stored in one course week."""
    answers = require_table(world.tables, ANSWER_TABLE)
    response_column = world.report.link(ANSWER_TABLE, RESPONSE_TABLE)
    question_column = world.report.link(ANSWER_TABLE, QUESTION_TABLE)
    question = world.report.questions[FIRST_VERSION][WORKLOAD_POSITION]
    key = world.key_of(RESPONSE_TABLE)
    response_ids = [row[key] for row in hero_responses(world, door, course_week)]
    if not response_ids:
        return []
    world.session.flush()
    rows = world.session.execute(
        select(answers.c[WORKLOAD_HOURS_COLUMN]).where(
            answers.c[response_column].in_(response_ids),
            answers.c[question_column] == question[world.key_of(QUESTION_TABLE)],
        )
    )
    return [row[0] for row in rows]


def after_the_close_of(course_week: int) -> datetime:
    """An instant safely after one of the hero's course weeks has closed, and before the next.

    The hero's windows carry SPEC §3.1's own Fall 2026 instants
    (`tests/fixtures/survey_windows.py`), and a *published* week is one whose
    window has closed — E4-07's breakdown decision 6 — so where the clock stands
    decides how much of the hero's own term exists. Six hours past the close,
    which is `tests/fixtures/report_api.py`'s own distance from an edge and for
    its reason: ADR 0109's effective instant keeps moving while it is read, so a
    value placed a second from an edge is a boundary nothing can stand on.
    """
    term_week = TERM_WEEK_OF_COURSE_WEEK[course_week]
    _opens_at, closes_at = WINDOWS_BY_TERM_WEEK[term_week]
    return closes_at + EITHER_SIDE_OF_A_CLOSE


def published_course_weeks(body: Any, answered: Any = None) -> list[int]:
    """The course weeks the payload itself says the hero has published.

    Read off the payload rather than counted here, because "the hero section's
    own published weeks" is a fact this ticket does not own: E4-07 computes it
    against the clock, and a series is being held to it. Both spellings the
    member could take are read — a list of week numbers, or a list of objects
    naming a course week — and anything else is a failure naming the ambiguity
    rather than a comparison against a currency this suite guessed at.
    """
    published = member(body, WEEK_MEMBER, PUBLISHED_WEEKS_FIELD, answered=answered)
    if not isinstance(published, list):
        pytest.fail(
            f"`{WEEK_MEMBER}.{PUBLISHED_WEEKS_FIELD}` is {published!r}, which is not a list of "
            "weeks."
        )
    found: list[int] = []
    for entry in published:
        if isinstance(entry, dict) and POINT_WEEK_FIELD in entry:
            found.append(int(entry[POINT_WEEK_FIELD]))
        elif isinstance(entry, int) and not isinstance(entry, bool):
            found.append(int(entry))
        else:
            pytest.fail(
                f"`{WEEK_MEMBER}.{PUBLISHED_WEEKS_FIELD}` holds {entry!r}, which this suite cannot "
                f"read as a course week. It reads a number or an object naming "
                f"`{POINT_WEEK_FIELD}`; a third spelling is taught in `published_course_weeks` in "
                "tests/fixtures/report_benchmarks.py."
            )
    return found


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


# What each object in the benchmark members is made of, as the work order spells
# it. These are the sets the disclosure walk holds every object to: a member that
# is not one of them is a count, a set size or a flag that nothing sealed, and
# "over 2 sections" under a suppression is itself the inference §4.1 item 7
# exists to prevent.
BENCHMARK_POPULATION_MEMBERS = frozenset(POPULATIONS)
SERIES_MEMBERS = frozenset({POINTS_FIELD})
POINT_MEMBERS = frozenset({POINT_WEEK_FIELD, POINT_MEAN_FIELD})
WORKLOAD_FIGURE_MEMBERS = frozenset({MEAN_FIELD, MEDIAN_FIELD})


def benchmark_member_shapes(body: Any, answered: Any = None) -> list[tuple[str, Any, frozenset]]:
    """Every object the benchmark members are made of, with the members it may carry.

    **Every object, not every figure**, which is the repair the E5-05 fix round
    asks for: a count added to a series *point* — beside `course_week` and `mean`,
    where no figure walk would ever look — is the same disclosure as a count
    inside a figure, and it slipped past the first version of that test entirely.
    The walk therefore descends the whole shape: the stream's benchmark member,
    each population's series, each point, each point's figure, the workload
    member, each of its populations, and each of their two statistics.
    """
    found: list[tuple[str, Any, frozenset]] = []
    for stream, key in PAYLOAD_STREAM_KEY.items():
        at = f"streams.{key}.{BENCHMARK_MEMBER}"
        benchmark = member(body, STREAMS_MEMBER, key, BENCHMARK_MEMBER, answered=answered)
        found.append((at, benchmark, BENCHMARK_POPULATION_MEMBERS))
        for population in POPULATIONS:
            series = stream_benchmark(body, stream, population, answered=answered)
            found.append((f"{at}.{population}", series, SERIES_MEMBERS))
            for point in member(series, POINTS_FIELD, answered=answered):
                week = point.get(POINT_WEEK_FIELD) if isinstance(point, dict) else None
                where = f"{at}.{population}.{POINTS_FIELD}[week {week}]"
                found.append((where, point, POINT_MEMBERS))
                if isinstance(point, dict) and POINT_MEAN_FIELD in point:
                    found.append(
                        (f"{where}.{POINT_MEAN_FIELD}", point[POINT_MEAN_FIELD], FIGURE_MEMBERS)
                    )
    workload = member(body, WORKLOAD_BENCHMARK_MEMBER, answered=answered)
    found.append((WORKLOAD_BENCHMARK_MEMBER, workload, BENCHMARK_POPULATION_MEMBERS))
    for population in POPULATIONS:
        figures = workload_figures(body, population, answered=answered)
        at = f"{WORKLOAD_BENCHMARK_MEMBER}.{population}"
        held = member(body, WORKLOAD_BENCHMARK_MEMBER, population, answered=answered)
        found.append((at, held, WORKLOAD_FIGURE_MEMBERS))
        for name, figure in figures.items():
            found.append((f"{at}.{name}", figure, FIGURE_MEMBERS))
    for where, held, _allowed in found:
        if not isinstance(held, dict):
            pytest.fail(
                f"`{where}` is {held!r} rather than an object this walk can read the members of.\n\n"
                f"{BENCHMARK_MEMBERS_ARE_OWED}"
            )
    return found


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


# The read service the report route delegates to. E5-05's work order settles the
# name and the home — "the benchmark members are assembled in
# `app.services.reporting._payload`", reached through `instructor_report` — and
# settles no signature, so the parameters are bound **by name** below, the device
# `tests/fixtures/report_api.py::call_the_helper` uses and for the same reason: a
# signature a record leaves open is a question for the ticket, and a guess
# written into a fixture answers it silently.
REPORT_SERVICE = "instructor_report"
SESSION_PARAMETERS = ("session", "db", "db_session", "connection")
# The reader's own person — the one the route resolves from the session's claims.
# `tests/fixtures/report_api.py` seeds it in `_seed_the_launching_person` and the
# door keeps it as `ReportDoor.person_id`, which is how a test can hand the
# service what a request would have carried.
PERSON_MARK = "person"
SECTION_MARK = "section"
WEEK_MARK = "week"
SETTINGS_MARK = "settings"
NOW_PARAMETERS = ("now", "at", "instant", "as_of")


def an_instructor_report(door: ReportDoor, contract: Any, *, course_week: int) -> Any:
    """The report **object** the service builds for one section and course week.

    **Not a payload re-validated from its own JSON**, which is the repair the
    ruling on `docs/disputes/E5-05-01.md` settles. A served body carries its
    figures as plain mappings, and a mapping validated into a comparison figure
    presents no seal — so `model_validate(body)` over any payload with a *shown*
    figure in it is refused by construction, for every implementation that
    satisfies criterion 1. The seal is deliberately never serialized, because a
    serialized seal is a forgeable one.

    What the response boundary really re-reads is the object the route returns,
    with its figures as sealed instances, and that is what this answers. A test
    can then rewrite one member of it and ask the boundary the only question
    worth asking: does the unsealed figure reach the wire.

    Every parameter is filled by name and an unfillable required one is a failure
    naming it — an interface question for the ticket rather than a guess.
    """
    import inspect

    module = contract.reporting()
    service = getattr(module, REPORT_SERVICE, None)
    if not callable(service):
        pytest.fail(
            f"`{contract.reporting_module_name}` exposes no callable `{REPORT_SERVICE}`; it "
            f"exposes {sorted(name for name in vars(module) if not name.startswith('_'))}. E5-05's "
            "work order names it as the read the route delegates to, and this suite needs the "
            "report *object* rather than its serialized body — see this function's docstring and "
            "the ruling on `docs/disputes/E5-05-01.md`."
        )

    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    unfilled: list[str] = []
    for parameter in inspect.signature(service).parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        lowered = parameter.name.lower()
        if lowered in SESSION_PARAMETERS:
            value: Any = door.world.session
        elif PERSON_MARK in lowered:
            value = _the_readers_person(door)
        elif SECTION_MARK in lowered:
            value = door.rows.taught_section_id
        elif WEEK_MARK in lowered:
            value = course_week
        elif SETTINGS_MARK in lowered:
            value = _settings()
        elif lowered in NOW_PARAMETERS:
            value = datetime.now(UTC)
        elif parameter.default is not parameter.empty:
            continue
        else:
            unfilled.append(parameter.name)
            continue
        if parameter.kind is parameter.POSITIONAL_ONLY:
            positional.append(value)
        else:
            keyword[parameter.name] = value

    if unfilled:
        pytest.fail(
            f"`{REPORT_SERVICE}{inspect.signature(service)}` requires {unfilled}, which this "
            "fixture has nothing to fill from. It supplies a session (a parameter named "
            f"{list(SESSION_PARAMETERS)}), the reader's person (one naming `{PERSON_MARK}`), a "
            f"section id (one naming `{SECTION_MARK}`), a course week (one naming `{WEEK_MARK}`), "
            f"`Settings` (one naming `{SETTINGS_MARK}`) and an instant (one named "
            f"{list(NOW_PARAMETERS)}). A further required input is an interface "
            "question for the ticket — `an_instructor_report` in "
            "tests/fixtures/report_benchmarks.py is where a spelling is taught."
        )

    report = service(*positional, **keyword)
    fields = getattr(type(report), "model_fields", None) or {}
    if not fields:
        pytest.fail(
            f"`{REPORT_SERVICE}` answered {report!r}, which is not a model this suite can rewrite a "
            "member of. The route serves a Pydantic report, and the boundary under test is the "
            "revalidation that report crosses on its way to the wire."
        )
    return report


def _the_readers_person(door: ReportDoor) -> Any:
    """The person the route would have resolved from the session's claims.

    The service takes the reader's own person because the report is scoped to the
    sections that person teaches; a test calling it directly has to hand over what
    a request would have carried, or it is exercising a read nobody could make.
    `tests/fixtures/report_api.py` seeds that person in
    `_seed_the_launching_person` and the door keeps it.

    `None` is a legitimate value of that parameter for a session naming nobody,
    and it is not what these tests want — it is refused here rather than passed
    quietly, because a report read as nobody is a different question from the one
    the smuggling tests ask.
    """
    if door.person_id is None:
        pytest.fail(
            "This door holds no person id, so there is nobody to read the report as. "
            "`report_door` builds the instructor door, which seeds one; a door built for a role "
            "that holds no assignment (the student door) cannot drive the report service."
        )
    return door.person_id


def _settings() -> Any:
    """`Settings`, built the way `tests/fixtures/report_api.py` builds it."""
    from importlib import import_module

    return import_module("app.config").Settings()


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
