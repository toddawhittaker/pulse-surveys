"""The reader's own sections are one group: one frozen instant, sealed on what is left.

Round 3 of E5-14, the orchestrator's revised ruling on the privacy-authz fix pass
on ce9df73 (the owner is away; the rule only withholds more, and it is flagged for
the owner at the epic review):

- *R* is every section, **in any term**, carrying an `INSTRUCTOR` grant for any
  person who holds one on the reported section A. *R* includes A.
- **The populations are resolved as before**: the default set excludes only A;
  the university includes it. The reader's other sections are *counted*.
- **A figure is shown only if** (a) its population meets both minimums; (b) its
  population minus *R* is empty or itself meets both minimums; and, for the
  university figure, (c) the complement — university - *R* - default set — is
  empty or meets both minimums.
- **One cutoff per reader group.** For course week *w*, the cutoff is the
  earliest week-*w* `survey_window.closes_at` among the sections of *R* in A's
  term. Two sections one instructor teaches in one term therefore get
  byte-identical comparison and university figures for the same course week.

**What each rule closes.** The shared cutoff closes the HIGH: two reports of one
population frozen a week apart differ by whatever closed between, one student at a
time. Condition (b) closes the MEDIUM: the reader knows every section she teaches
exactly — its count and its sum — so what a figure hides from her is only the part
outside *R*, and that part is what the minimums must protect. A figure made only of
her own sections hides nothing and is shown (the seeded world's case: one person
teaches the hero and its whole default set).

**The world** is `tests/fixtures/report_benchmarks.py`'s cohort — the hero's
lead's default set, three sections and ten people at course week 2, in the hero's
six-week cohort `F` — with sections added by `plant_a_section_beside` and teaching
grants written by `teach`, the row *R* is resolved from. To isolate condition (b)
the set's three sections are taught by the reader (or a co-instructor) where a test
says so, which moves them into *R* while leaving them in the population.

**Every withheld figure has a shown twin**, the same world with the remainder at
both minimums or absent — which is what rules out a route that withholds
everything. The twins are green today and after; the "withheld" and "unmoved" tests are red
today, because ce9df73 has neither rule (`docs/MISTAKES.md` entries 3 and 51).

**Marked `invariant`:** §4.1 item 7 — a figure a subtraction reduces to one
student is a figure over one student.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from fixtures.benchmark_views import PRIOR_TERM
from fixtures.report_api import ReportDoor
from fixtures.report_benchmarks import (
    COMPARISON_POPULATION,
    FIGURE_FIELD,
    MEAN_FIELD,
    MEDIAN_FIELD,
    REASON_FIELD,
    SUPPRESSED_FIELD,
    UNIVERSITY_POPULATION,
    WEEK_CLEAR,
    PlantedBenchmarkCohort,
    answer_once,
    benchmark_members_of,
    hero_window_close,
    numbers_of,
    plant_a_section_beside,
    points_of,
    publish_every_week,
    teach,
    workload_figures,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

STREAMS = (INSTRUCTOR_STREAM, COURSE_STREAM)
REPORTED_WEEK = WEEK_CLEAR

SAME_LETTER = "F"
PRIOR_LETTER = "E"

AN_HOUR = timedelta(hours=1)
A_DAY = timedelta(days=1)

# How many people answer in the prior-term section of item 3: with the two thin
# outside sections' two, that is ten people over three sections — both minimums
# exactly — so whether the prior section is in *R* is the whole difference.
PRIOR_PEOPLE = 8


def a_cohort(door: ReportDoor, contract: Any, plant: Callable[..., Any]) -> PlantedBenchmarkCohort:
    """The round-1 cohort around the door's own section, committed."""
    cohort = plant(door, minimums=contract.minimums())
    door.commit()
    return cohort


def members(door: ReportDoor, section_id: Any = None) -> dict[str, str]:
    """The benchmark members of one report at the reported week, as canonical JSON."""
    return benchmark_members_of(door, course_week=REPORTED_WEEK, section_id=section_id)


def moved(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """The members whose serialization differs between two reads."""
    return sorted(where for where in before if before[where] != after.get(where))


def assert_the_week_is_shown(door: ReportDoor, section_id: Any = None) -> None:
    """The control every "unmoved" needs: the compared figures are real ones, not suppressed."""
    body, answered = door.payload(course_week=REPORTED_WEEK, section_id=section_id)
    for stream in STREAMS:
        for population in (COMPARISON_POPULATION, UNIVERSITY_POPULATION):
            points = points_of(body, stream, population, answered=answered)
            assert REPORTED_WEEK in points and numbers_of(points[REPORTED_WEEK]), (
                f"The control failed before the assertion it protects: the {stream} {population} "
                f"figure for course week {REPORTED_WEEK} is {points.get(REPORTED_WEEK)!r}. Two "
                "reads of a suppressed figure are identical whatever the rule."
            )


def the_university_figures(door: ReportDoor, section_id: Any = None) -> dict[str, Any]:
    """One report's university members at the reported week: each panel's point, mean, median."""
    body, answered = door.payload(course_week=REPORTED_WEEK, section_id=section_id)
    found: dict[str, Any] = {
        f"the {stream} university point": points_of(
            body, stream, UNIVERSITY_POPULATION, answered=answered
        ).get(REPORTED_WEEK)
        for stream in STREAMS
    }
    workload = workload_figures(body, UNIVERSITY_POPULATION, answered=answered)
    for name in (MEAN_FIELD, MEDIAN_FIELD):
        found[f"the university workload {name}"] = workload[name]
    return found


def the_set_is_taught_by(door: ReportDoor, cohort: PlantedBenchmarkCohort, person: Any) -> None:
    """Give `person` a teaching grant on each of the cohort's three set sections."""
    for label in cohort.labels:
        teach(door, cohort.world.section_id(label), person=person)


def thin_outside_sections(cohort: PlantedBenchmarkCohort, *, sections: int, people: int) -> None:
    """Sections of the lead's, at the hero's instant, answered at course week 2 by `people`.

    Led, so they are in the default set (and the university); nobody's teaching
    grant is written on them, so they are outside every *R* here.
    """
    labels = [f"outside-{index}" for index in range(sections)]
    for label in labels:
        plant_a_section_beside(cohort, label, letter=SAME_LETTER)
    for index in range(people):
        answer_once(
            cohort,
            labels[index % sections],
            subject=f"e5-14-r3-outside-{index}",
            course_week=REPORTED_WEEK,
        )


def is_withheld(figure: Any) -> bool:
    """A member in the chokepoint's suppressed state: the flag, a reason, no figure, no number."""
    return (
        isinstance(figure, dict)
        and figure.get(SUPPRESSED_FIELD) is True
        and bool(figure.get(REASON_FIELD))
        and figure.get(FIGURE_FIELD) is None
        and not numbers_of(figure)
    )


def is_shown(figure: Any) -> bool:
    """A member shown: not suppressed, and carrying its statistic."""
    return (
        isinstance(figure, dict)
        and figure.get(SUPPRESSED_FIELD) is False
        and bool(numbers_of(figure))
    )


def the_comparison_figures_at_the_week(door: ReportDoor, stream: str) -> dict[str, Any]:
    """The three default-set members at course week 2 — one panel's point, the mean, the median.

    Answered rather than judged, so each test states in its own body whether they
    must be withheld or shown. A missing point is `None`, which is neither.

    **In the "withheld" tests the control is the twin, not a figure in this
    payload.** A passing week of the same series would be the natural in-payload
    control, but in these worlds the thin sections are resolved into the default
    set at every week and answer only at week 2 — whether a remainder of
    sections with no rows that week counts as "empty" is a question the ruling
    does not settle (the E5-14 manifest raises it). The twin tests — same world,
    the remainder at both minimums or absent — are shown, which is what rules out
    a route that withholds everything.
    """
    body, answered = door.payload(course_week=REPORTED_WEEK)
    comparison = points_of(body, stream, COMPARISON_POPULATION, answered=answered)
    workload = workload_figures(body, COMPARISON_POPULATION, answered=answered)
    point = comparison.get(REPORTED_WEEK)
    return {
        f"the {stream} comparison point at course week {REPORTED_WEEK}": point,
        f"the comparison workload {MEAN_FIELD}": workload[MEAN_FIELD],
        f"the comparison workload {MEDIAN_FIELD}": workload[MEDIAN_FIELD],
    }


def not_withheld(figures: dict[str, Any]) -> dict[str, Any]:
    """The members of `figures` that are not in the suppressed state."""
    return {where: figure for where, figure in figures.items() if not is_withheld(figure)}


def not_shown(figures: dict[str, Any]) -> dict[str, Any]:
    """The members of `figures` that are not shown."""
    return {where: figure for where, figure in figures.items() if not is_shown(figure)}


def withheld_message(leaked: dict[str, Any], why: str) -> str:
    return (
        f"These default-set members are not withheld, and {why}: {leaked}.\n\n"
        "The revised ruling shows a figure only if its population minus the reader's own sections "
        "(*R*) is empty or meets both minimums. A suppressed member says `suppressed`, gives a "
        "reason, and carries no number."
    )


def shown_message(missing: dict[str, Any], why: str) -> str:
    return (
        f"These default-set members are not shown, and {why}: {missing}. Condition (a) holds and "
        "the remainder after the reader's sections is empty or at both minimums."
    )


# ---------------------------------------------------------------------------
# Item 1: one cutoff per reader group.
# ---------------------------------------------------------------------------


def a_later_second_section_and_a_section_closing_between(
    door: ReportDoor, cohort: PlantedBenchmarkCohort, *, taught: bool
) -> tuple[Any, datetime]:
    """B — the hero's course, one week later — and X, a led section whose week closes between.

    B is a second section of the hero's own course (the same length and level),
    starting a week after the hero's, so its course week 2 closes a week after
    the hero's. X is one of the lead's sections whose course-week-2 window is
    moved to close a day after the hero's — between the two. `taught` gives the
    door's instructor the teaching grant on B; without it the reader group is
    the hero alone.

    Answers B's section id and *T_A*, the hero's own week-2 close.
    """
    world = cohort.world
    plant_a_section_beside(
        cohort, "b", letter=SAME_LETTER, course=cohort.hero_course, weeks_later=1, ordinal="7"
    )
    publish_every_week(world, "b")
    plant_a_section_beside(cohort, "x", letter=SAME_LETTER)
    t_a = hero_window_close(world, door, REPORTED_WEEK)
    world.window_closing_at("x", REPORTED_WEEK, t_a + A_DAY)
    b_id = world.section_id("b")
    if taught:
        teach(door, b_id)
    door.commit()
    return b_id, t_a


def test_two_sections_one_instructor_teaches_share_one_frozen_snapshot(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """Item 1: A and B, taught by one person, cut at one instant — X is in neither.

    X's course-week-2 window closes a day after A's (*T_A*) and six days before
    B's (*T_B*). A row there, last submitted before X's close, is counted by a
    cutoff of *T_B* and not by one of *T_A*. Under the ruling both reports cut at
    the earliest week-2 close in the reader group, *T_A*, so an answer in X moves
    neither report — the two "unmoved" assertions.

    **And the university figures are the same.** Both university populations
    hold A and B, under one cutoff, so A's and B's university members at a course
    week both have published are identical. The default-set members are *not*
    compared: by the revised ruling A's default set holds B and B's holds A, two
    populations that differ only by the reader's own sections, and the two
    series also cover different published weeks. The ruling on
    `docs/disputes/E5-14-02.md` dropped the earlier byte-identical assertion over
    every member for exactly that reason.

    **The mutation it kills:** each report cut at its own section's close — the
    ce9df73 behaviour — under which B counts X and A does not, and B minus A is
    X's student; the university members then differ too. Also the latest close
    in the group, which moves A.
    **Its near miss** is
    `test_a_one_section_instructors_figures_are_unchanged_by_the_group_rule`.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    b_id, t_a = a_later_second_section_and_a_section_closing_between(
        report_door, cohort, taught=True
    )
    assert_the_week_is_shown(report_door)
    assert_the_week_is_shown(report_door, section_id=b_id)
    a_before, b_before = members(report_door), members(report_door, section_id=b_id)

    answer_once(
        cohort,
        "x",
        subject="e5-14-r3-between",
        course_week=REPORTED_WEEK,
        last_submitted_at=t_a + 12 * AN_HOUR,
    )
    report_door.commit()
    a_after, b_after = members(report_door), members(report_door, section_id=b_id)

    assert not moved(b_before, b_after), (
        f"A response in X, whose course-week-{REPORTED_WEEK} window closed a day after A's and "
        f"before B's, moved {moved(b_before, b_after)} on B's report. A and B are taught by one "
        "person, so the ruling cuts both at the earliest close in the group — A's — and X's row "
        "is in neither. Cut at B's own close, B minus A is that one student."
    )
    assert not moved(a_before, a_after), (
        f"The same response moved {moved(a_before, a_after)} on A's report, whose own close is "
        "before X's."
    )
    a_university = the_university_figures(report_door)
    b_university = the_university_figures(report_door, section_id=b_id)
    differ = sorted(where for where in a_university if a_university[where] != b_university[where])
    assert not differ, (
        f"A's and B's university members at course week {REPORTED_WEEK}, which both sections have "
        f"published, differ in {differ}: A {a_university}, B {b_university}. Both university "
        "populations hold A and B and are cut at one instant, so they are one figure; two of them "
        "differ by whatever closed between the two cuts."
    )


def test_a_one_section_instructors_figures_are_unchanged_by_the_group_rule(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """The control: with B taught by nobody, the reader group is A alone and A's cut is its own.

    **Green today and after.** A red here means the group cutoff reaches beyond
    the reader's sections — the earliest close among *every* section of the
    term, say — or the byte comparison is broken.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    _b_id, t_a = a_later_second_section_and_a_section_closing_between(
        report_door, cohort, taught=False
    )
    assert_the_week_is_shown(report_door)
    before = members(report_door)

    answer_once(
        cohort,
        "x",
        subject="e5-14-r3-between-alone",
        course_week=REPORTED_WEEK,
        last_submitted_at=t_a + 12 * AN_HOUR,
    )
    report_door.commit()

    assert not moved(before, members(report_door)), (
        "A response in a section whose window closed after A's own moved A's figures, with A "
        "taught by an instructor who teaches nothing else."
    )


# ---------------------------------------------------------------------------
# Item 2: the remainder after R is what the minimums are checked on.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_a_default_set_whose_remainder_after_the_readers_sections_is_thin_is_withheld(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """Condition (b): the reader teaches the set's three sections; the rest is two people.

    The default set at course week 2 is the cohort's three sections (ten people)
    plus two thin sections of the lead's, one person each — twelve people over
    five sections, so condition (a) holds. But the hero's instructor teaches the
    three: she knows their counts and sums, and subtracting them leaves two
    people. Population minus *R* is non-empty and below both minimums, so the
    comparison figures are withheld — both panels, and the workload mean and
    median.

    **The control, in the same payload:** course week 5 of the same series,
    where the thin sections answered nothing, so population minus *R* is empty
    and the figure is shown.

    **The mutation it kills:** condition (b) left out, or checked on the
    population minus A only — the ce9df73 rule. **Its near misses** are the two
    tests below: the remainder at both minimums, and no remainder at all.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    the_set_is_taught_by(report_door, cohort, report_door.person_id)
    thin_outside_sections(cohort, sections=2, people=2)
    report_door.commit()

    leaked = not_withheld(the_comparison_figures_at_the_week(report_door, stream))
    assert not leaked, withheld_message(
        leaked, "the default set minus the reader's own sections is two sections and two people"
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_a_default_set_whose_remainder_after_the_readers_sections_clears_both_minimums_is_shown(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """The twin: the same three taught sections, and a remainder at both minimums — shown.

    **Green today and after.** **The mutation it kills:** condition (b) read as
    "the population must hold none of the reader's sections", which withholds
    every multi-section instructor's comparison.
    """
    minimums = report_api_contract.minimums()
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    the_set_is_taught_by(report_door, cohort, report_door.person_id)
    thin_outside_sections(
        cohort,
        sections=minimums[report_api_contract.minimum_sections],
        people=minimums[report_api_contract.minimum_respondents],
    )
    report_door.commit()

    missing = not_shown(the_comparison_figures_at_the_week(report_door, stream))
    assert not missing, shown_message(
        missing, "the remainder after the reader's sections is at both minimums"
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_a_default_set_made_only_of_the_readers_own_sections_is_shown(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """The other twin, and the seeded world's case: the remainder is empty — shown.

    The hero's instructor teaches every section of the default set. A figure
    made only of her own sections tells her nothing she has not seen on her own
    reports, so condition (b) is met by an *empty* remainder and the figure is
    shown on condition (a) alone.

    **Green today and after.** **The mutation it kills:** condition (b) written
    as "population minus *R* meets both minimums", which is never true of an
    empty set and withholds the seeded hero's whole comparison — the
    over-withholding the revised ruling exists to avoid.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    the_set_is_taught_by(report_door, cohort, report_door.person_id)
    report_door.commit()

    missing = not_shown(the_comparison_figures_at_the_week(report_door, stream))
    assert not missing, shown_message(
        missing, "the default set is made only of the reader's own sections"
    )


# ---------------------------------------------------------------------------
# Item 3: a prior-term section the reader taught is counted, but not in the remainder.
# ---------------------------------------------------------------------------


def a_taught_set_a_prior_section_and_two_thin_ones(
    door: ReportDoor, cohort: PlantedBenchmarkCohort, *, prior_taught_by: Any, people: int
) -> str:
    """The set taught by the reader, a led prior-term section, and two thin led sections.

    `people` answer in the prior section at course week 2. Answers its label.
    """
    the_set_is_taught_by(door, cohort, door.person_id)
    plant_a_section_beside(cohort, "prior", letter=PRIOR_LETTER, term=PRIOR_TERM)
    teach(door, cohort.world.section_id("prior"), person=prior_taught_by)
    for index in range(people):
        answer_once(cohort, "prior", subject=f"e5-14-r3-prior-{index}", course_week=REPORTED_WEEK)
    thin_outside_sections(cohort, sections=2, people=2)
    door.commit()
    return "prior"


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_a_prior_term_section_the_reader_taught_is_not_part_of_the_remainder(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """*R* reaches into prior terms: her own last-term section is out of the remainder.

    The remainder after *R* would be the prior section's eight people and the
    two thin sections' two — three sections, ten people, at both minimums — if
    the prior section were not hers. It is hers (a teaching grant "in any term"),
    so the remainder is the two thin sections: withheld.

    **The mutation it kills:** *R* resolved in A's term only. **Its near miss**
    is the twin below, the same prior section taught by somebody else.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    a_taught_set_a_prior_section_and_two_thin_ones(
        report_door, cohort, prior_taught_by=report_door.person_id, people=PRIOR_PEOPLE
    )

    leaked = not_withheld(the_comparison_figures_at_the_week(report_door, stream))
    assert not leaked, withheld_message(
        leaked, "the reader taught the prior-term section too, so the remainder is two people"
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_a_prior_term_section_someone_else_taught_is_part_of_the_remainder(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """The twin: taught by somebody else, the prior section is in the remainder — shown.

    **Green today and after.** **The mutation it kills:** *R* widened to every
    section of the reader's courses, or to every section with a teaching grant.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    a_taught_set_a_prior_section_and_two_thin_ones(
        report_door, cohort, prior_taught_by=report_door.graph.person(), people=PRIOR_PEOPLE
    )

    missing = not_shown(the_comparison_figures_at_the_week(report_door, stream))
    assert not missing, shown_message(
        missing, "the remainder is the prior section and the two thin ones"
    )


def test_a_prior_term_section_the_reader_taught_is_still_counted_in_the_figure(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """Counted in the figure: a shown figure moves when her own prior section gains a row.

    The same world with the remainder at both minimums, so the figure is shown;
    one more response in the prior section she taught moves it. *R* decides
    whether a figure may be shown, never what it is computed over.

    **Green today and after.** **The mutation it kills:** *R* excluded from the
    population — the first round-3 ruling, which the revised one withdrew because
    it emptied the seeded hero's comparison.
    """
    minimums = report_api_contract.minimums()
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    the_set_is_taught_by(report_door, cohort, report_door.person_id)
    plant_a_section_beside(cohort, "prior", letter=PRIOR_LETTER, term=PRIOR_TERM)
    teach(report_door, cohort.world.section_id("prior"), person=report_door.person_id)
    thin_outside_sections(
        cohort,
        sections=minimums[report_api_contract.minimum_sections],
        people=minimums[report_api_contract.minimum_respondents],
    )
    report_door.commit()
    assert_the_week_is_shown(report_door)
    before = members(report_door)

    answer_once(cohort, "prior", subject="e5-14-r3-prior-counted", course_week=REPORTED_WEEK)
    report_door.commit()

    assert moved(before, members(report_door)), (
        "A response in a prior-term section the reader taught moved nothing on a shown figure. "
        "The revised ruling resolves the populations as before — her sections are counted — and "
        "uses *R* only to decide whether a figure may be shown."
    )


# ---------------------------------------------------------------------------
# Item 4: two instructors on A — R is the union.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_a_co_instructors_sections_are_in_the_reader_group(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """*R* is the union: a second instructor on A teaches the set, so the remainder is thin.

    A second person holds a teaching grant on A and on the set's three sections.
    Either instructor reads A's report, so the sections either teaches are in
    *R*; the remainder after *R* is the two thin sections — withheld.

    **The mutation it kills:** *R* resolved from the requesting person's grants
    only, which lets the co-instructor subtract her own sections out of A's
    figure. **Its near miss** is the twin below.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    co_instructor = report_door.graph.person()
    teach(report_door, report_door.rows.taught_section_id, person=co_instructor)
    the_set_is_taught_by(report_door, cohort, co_instructor)
    thin_outside_sections(cohort, sections=2, people=2)
    report_door.commit()

    leaked = not_withheld(the_comparison_figures_at_the_week(report_door, stream))
    assert not leaked, withheld_message(
        leaked, "A's co-instructor teaches the set, so the remainder after the group is two people"
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_sections_taught_by_someone_with_no_grant_on_the_section_stay_in_the_remainder(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """The twin: the set taught by a person with no grant on A — the remainder clears — shown.

    **Green today and after.** **The mutation it kills:** *R* widened to every
    section anyone teaches, which withholds every comparison in an institution
    where every section has an instructor.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    the_set_is_taught_by(report_door, cohort, report_door.graph.person())
    thin_outside_sections(cohort, sections=2, people=2)
    report_door.commit()

    missing = not_shown(the_comparison_figures_at_the_week(report_door, stream))
    assert not missing, shown_message(missing, "the set's instructor holds no grant on A")
