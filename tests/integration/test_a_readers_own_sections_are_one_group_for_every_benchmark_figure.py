"""One snapshot per population, and each instructor's own sections subtracted — E5-14 round 4.

The orchestrator's round-4 ruling (reader-independent; it replaces round 3's
reader-group cutoff and the union-*R* remainder), from the E5-14 work order:

1. **Cutoff.** For course week *w*, the cutoff is the earliest week-*w*
   `survey_window.closes_at` among **all sections in A's term with A's length
   and level**, A included. It depends on no reader, so every report over that
   population and week shares one snapshot. Prior terms count in full.
2. **Remainder, per person.** For **each person p** holding an `INSTRUCTOR`
   grant on A, with T(p) = `taught_section_ids(p)` (every term): (b_p) the
   population - T(p) is empty — zero contributors to *that* figure at that week
   and cutoff — or meets both minimums; and for the university, (c_p)
   university - T(p) - default set is empty or meets both. Plus (a): the
   population meets both minimums. A figure is shown only if (a) holds and
   (b_p), (c_p) hold for every p.

**Why round 3's rules were replaced** (the privacy-authz re-check on d7b4561,
two HIGHs, both from co-teaching). The reader-group cutoff was asymmetric: R(A)
was the union over A's instructors, so a co-instructor's earlier-closing section
could cut A earlier than B for the same reader, and one reader got two snapshots
again. And the union-*R* remainder assumed the reader knows all of *R*, when each
instructor knows only the sections *she* teaches — the reviewer's verified scratch
world (Y teaches set-0, X teaches set-1 and set-2) showed a figure Y could reduce
to two sections and six people.

**A section with no instructor** (A3a) has no p, so only (a) applies to it — and
nobody can read its report, because the route requires a teaching grant, so no
test here drives one.

**The world** is `tests/fixtures/report_benchmarks.py`'s cohort — the hero's
lead's default set, three sections and ten people at course week 2, in the hero's
six-week cohort `F` — with sections added by `plant_a_section_beside`, teaching
grants written by `teach`, and answers by `answer_once`.

**Every marked test asserts in its own body.** Every withheld figure has a shown
twin; every "unmoved" read has a proof the figures were real
(`docs/MISTAKES.md` entries 3 and 51).

**Marked `invariant`:** §4.1 item 7.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    COURSE_NUMBER_COLUMN,
    COURSE_NUMBER_FOR_LEVEL,
    COURSE_TABLE,
    PRIOR_TERM,
    UGGR,
)
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
    carries_number,
    hero_window_close,
    numbers_of,
    plant_a_section_beside,
    points_of,
    publish_every_week,
    teach,
    workload_figures,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.survey_windows import WINDOWS_BY_TERM_WEEK

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

STREAMS = (INSTRUCTOR_STREAM, COURSE_STREAM)
REPORTED_WEEK = WEEK_CLEAR

# The hero's own six-week letter; `E` is the same length starting in term week 1
# (and, in the prior term, that term's six-week letter).
SAME_LETTER = "F"
EARLY_LETTER = "E"
PRIOR_LETTER = "E"
# An eight-week letter starting in term week 1: another length, closing week 2 early.
ANOTHER_LENGTH_LETTER = "X"

AN_HOUR = timedelta(hours=1)
A_DAY = timedelta(days=1)

# How many people answer in the prior-term section of the prior-term pair: with
# the two thin outside sections' two, ten people over three sections — both
# minimums exactly — so whether the prior section is in T(p) is the difference.
PRIOR_PEOPLE = 8

# The round-1 cohort's comparison figures at course week 2, by hand over
# `BENCHMARK_WEEKS` in `tests/fixtures/report_benchmarks.py`:
#   instructor 8 x 4 + 2 x 2 = 36 over 10 -> 3.6
#   course     4 x 1 + 6 x 4 = 28 over 10 -> 2.8
#   hours      6 x 7.5 + 4 x 9.5 = 83 over 10 -> 8.3
COMPARISON_AT_WEEK_TWO = {INSTRUCTOR_STREAM: 3.6, COURSE_STREAM: 2.8}
WORKLOAD_MEAN_AT_WEEK_TWO = 8.3


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


def not_shown_at_the_week(door: ReportDoor, section_id: Any = None) -> list[str]:
    """Every comparison and university point at the reported week that is not shown."""
    body, answered = door.payload(course_week=REPORTED_WEEK, section_id=section_id)
    missing = []
    for stream in STREAMS:
        for population in (COMPARISON_POPULATION, UNIVERSITY_POPULATION):
            point = points_of(body, stream, population, answered=answered).get(REPORTED_WEEK)
            if not is_shown(point):
                missing.append(f"{stream} {population}: {point!r}")
    return missing


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


def the_comparison_point(door: ReportDoor, stream: str) -> Any:
    """One panel's default-set point at course week 2."""
    body, answered = door.payload(course_week=REPORTED_WEEK)
    return points_of(body, stream, COMPARISON_POPULATION, answered=answered).get(REPORTED_WEEK)


def the_comparison_workload(door: ReportDoor) -> dict[str, Any]:
    """The default-set workload mean and median at course week 2."""
    body, answered = door.payload(course_week=REPORTED_WEEK)
    figures = workload_figures(body, COMPARISON_POPULATION, answered=answered)
    return {name: figures[name] for name in (MEAN_FIELD, MEDIAN_FIELD)}


def the_comparison_figures_at_the_week(door: ReportDoor, stream: str) -> dict[str, Any]:
    """The three default-set members at course week 2 — one panel's point, the mean, the median.

    Answered rather than judged, so each test states in its own body whether they
    must be withheld or shown. A missing point is `None`, which is neither.
    """
    found = {f"the {stream} comparison point": the_comparison_point(door, stream)}
    for name, figure in the_comparison_workload(door).items():
        found[f"the comparison workload {name}"] = figure
    return found


def not_withheld(figures: dict[str, Any]) -> dict[str, Any]:
    return {where: figure for where, figure in figures.items() if not is_withheld(figure)}


def not_shown(figures: dict[str, Any]) -> dict[str, Any]:
    return {where: figure for where, figure in figures.items() if not is_shown(figure)}


def the_set_is_taught_by(
    door: ReportDoor, cohort: PlantedBenchmarkCohort, person: Any, *labels: str
) -> None:
    """Give `person` a teaching grant on the named set sections (all three by default)."""
    for label in labels or cohort.labels:
        teach(door, cohort.world.section_id(label), person=person)


def led_sections(
    cohort: PlantedBenchmarkCohort,
    *,
    prefix: str,
    sections: int,
    people: int,
    term: str | None = None,
) -> list[str]:
    """Sections of the lead's, same length and level, answered at course week 2 by `people`.

    In the current term they run the hero's letter and close week 2 at the hero's
    instant; in the prior term, that term's six-week letter (counted in full).
    Nobody's teaching grant is written on them.
    """
    labels = [f"{prefix}-{index}" for index in range(sections)]
    for label in labels:
        if term is None:
            plant_a_section_beside(cohort, label, letter=SAME_LETTER)
        else:
            plant_a_section_beside(cohort, label, letter=PRIOR_LETTER, term=term)
    for index in range(people):
        answer_once(
            cohort,
            labels[index % sections],
            subject=f"e5-14-r4-{prefix}-{index}",
            course_week=REPORTED_WEEK,
        )
    return labels


# ---------------------------------------------------------------------------
# The cutoff: one per (term, length, level, course week), reader-independent.
# ---------------------------------------------------------------------------


def a_later_second_section_and_one_closing_between(
    door: ReportDoor, cohort: PlantedBenchmarkCohort, *, taught: bool
) -> tuple[Any, datetime]:
    """B — the hero's course, a week later — and D, whose week 2 closes a day after A's.

    Answers B's section id and *T_A*, the hero's own week-2 close, which is the
    earliest week-2 close among the term's six-week sections of this level here.
    """
    world = cohort.world
    plant_a_section_beside(
        cohort, "b", letter=SAME_LETTER, course=cohort.hero_course, weeks_later=1, ordinal="7"
    )
    publish_every_week(world, "b")
    plant_a_section_beside(cohort, "d", letter=SAME_LETTER)
    t_a = hero_window_close(world, door, REPORTED_WEEK)
    world.window_closing_at("d", REPORTED_WEEK, t_a + A_DAY)
    b_id = world.section_id("b")
    if taught:
        teach(door, b_id)
    door.commit()
    return b_id, t_a


def test_a_two_section_instructors_reports_share_one_snapshot(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """One instructor teaches A and B (a week later); D closes between their closes.

    The cutoff is the earliest week-2 close among the term's sections of this
    length and level — A's — for every report of that population, so an answer
    in D moves neither A's report nor B's, and A's and B's university members at
    week 2 are identical (both populations hold A and B). The default-set members
    are not compared: A's default set holds B and B's holds A (the ruling on
    `docs/disputes/E5-14-02.md`).

    **The mutation it kills:** each report cut at its own section's close (the
    ce9df73 behaviour). **Its near miss** is the one-section control below.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    b_id, t_a = a_later_second_section_and_one_closing_between(report_door, cohort, taught=True)
    unshown = not_shown_at_the_week(report_door) + not_shown_at_the_week(report_door, b_id)
    assert not unshown, f"The control failed: these figures are not shown: {unshown}."
    a_before, b_before = members(report_door), members(report_door, section_id=b_id)

    answer_once(
        cohort,
        "d",
        subject="e5-14-r4-between",
        course_week=REPORTED_WEEK,
        last_submitted_at=t_a + 12 * AN_HOUR,
    )
    report_door.commit()
    a_after, b_after = members(report_door), members(report_door, section_id=b_id)

    assert not moved(b_before, b_after), (
        f"A response in D, whose week-{REPORTED_WEEK} window closed a day after A's and before "
        f"B's, moved {moved(b_before, b_after)} on B's report. The cutoff is the earliest close "
        "among the term's sections of this length and level — A's — for every report."
    )
    assert not moved(
        a_before, a_after
    ), f"The same response moved {moved(a_before, a_after)} on A's report."
    a_university = the_university_figures(report_door)
    b_university = the_university_figures(report_door, section_id=b_id)
    differ = sorted(where for where in a_university if a_university[where] != b_university[where])
    assert not differ, (
        f"A's and B's university members at week {REPORTED_WEEK} differ in {differ}: A "
        f"{a_university}, B {b_university}. Both populations hold A and B under one cutoff."
    )


def test_a_one_section_instructors_figures_are_unchanged(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """The control: with B taught by nobody, D still closes after the population's cutoff.

    **Green on d7b4561 and after.** A red here means the cutoff moved later than
    the earliest close in the population.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    _b_id, t_a = a_later_second_section_and_one_closing_between(report_door, cohort, taught=False)
    unshown = not_shown_at_the_week(report_door)
    assert not unshown, f"The control failed: these figures are not shown: {unshown}."
    before = members(report_door)

    answer_once(
        cohort,
        "d",
        subject="e5-14-r4-between-alone",
        course_week=REPORTED_WEEK,
        last_submitted_at=t_a + 12 * AN_HOUR,
    )
    report_door.commit()

    assert not moved(before, members(report_door)), (
        "A response in a section whose window closed after the population's earliest close moved "
        "A's figures."
    )


def a_co_teaching_asymmetry(
    door: ReportDoor, cohort: PlantedBenchmarkCohort
) -> tuple[Any, datetime]:
    """Y teaches A and B; X co-teaches A and teaches C, which closes a week *earlier*.

    - B: the hero's course, a week later, taught by Y (the door's instructor).
    - C: a led section starting a week *before* the hero's, so its week-2 window
      closes a week before A's (*T_C* = *T_A* - 7 days); taught by X, who also
      holds a grant on A.
    - D: a led section of C's start, whose week-2 window is moved to close a day
      after *T_C* — between C's close and A's. (C's start rather than A's, so the
      moved close is still after the window opens.)
    - A prior-term default set at both minimums (three of the lead's prior-term
      six-week sections, ten people). Prior terms count in full, so the week-2
      figures stay shown when the cutoff falls at *T_C*, before the current-term
      set's own close.

    Answers B's id and *T_C*.
    """
    world = cohort.world
    x = door.graph.person()
    teach(door, door.rows.taught_section_id, person=x)
    plant_a_section_beside(
        cohort, "b", letter=SAME_LETTER, course=cohort.hero_course, weeks_later=1, ordinal="7"
    )
    publish_every_week(world, "b")
    teach(door, world.section_id("b"))
    plant_a_section_beside(cohort, "c", letter=SAME_LETTER, weeks_later=-1)
    publish_every_week(world, "c")
    teach(door, world.section_id("c"), person=x)
    t_c = WINDOWS_BY_TERM_WEEK[world.term_week_of("c", REPORTED_WEEK)][1]
    if not t_c < hero_window_close(world, door, REPORTED_WEEK):
        pytest.fail("C's week-2 close is not before A's, so this is not the asymmetry world.")
    plant_a_section_beside(cohort, "d", letter=SAME_LETTER, weeks_later=-1)
    world.window_closing_at("d", REPORTED_WEEK, t_c + A_DAY)
    led_sections(cohort, prefix="prior-set", sections=3, people=10, term=PRIOR_TERM)
    door.commit()
    return world.section_id("b"), t_c


def test_co_teaching_gives_one_reader_one_snapshot(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """The co-teaching asymmetry: A and B share one cutoff although their instructor sets differ.

    Under round 3's reader-group cutoff, A's group was the union over A's
    instructors — Y's A and B, and X's A and C — so A was cut at C's close; B's
    group was Y's alone, so B was cut at A's close. One reader, Y, then read two
    snapshots, and D — closing between them — was in B and not in A: B minus A is
    D's student. Under the round-4 rule both are cut at the earliest week-2 close
    in the term's population, *T_C*, so an answer in D moves neither, and A's and
    B's university members at week 2 are identical.

    **The mutation it kills:** the round-3 reader-group cutoff. **Its near
    miss** is `test_a_two_section_instructors_reports_share_one_snapshot`, where
    the two rules agree.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    b_id, t_c = a_co_teaching_asymmetry(report_door, cohort)
    unshown = not_shown_at_the_week(report_door) + not_shown_at_the_week(report_door, b_id)
    assert not unshown, f"The control failed: these figures are not shown: {unshown}."
    a_before, b_before = members(report_door), members(report_door, section_id=b_id)

    answer_once(
        cohort,
        "d",
        subject="e5-14-r4-co-teaching",
        course_week=REPORTED_WEEK,
        last_submitted_at=t_c + 12 * AN_HOUR,
    )
    report_door.commit()
    a_after, b_after = members(report_door), members(report_door, section_id=b_id)

    assert not moved(b_before, b_after) and not moved(a_before, a_after), (
        f"A response in D, closing between C's close and A's, moved {moved(a_before, a_after)} on "
        f"A's report and {moved(b_before, b_after)} on B's. The cutoff is the earliest week-2 close "
        "among all the term's sections of this length and level — C's — whoever teaches them."
    )
    a_university = the_university_figures(report_door)
    b_university = the_university_figures(report_door, section_id=b_id)
    differ = sorted(where for where in a_university if a_university[where] != b_university[where])
    assert not differ, (
        f"A's and B's university members at week {REPORTED_WEEK} differ in {differ}. One reader "
        "teaches both, so two snapshots of one population are a subtraction away from one student."
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_a_prior_term_section_of_the_same_length_and_level_never_moves_the_cutoff(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """C3: a value pin — with a prior-term peer present, the week-2 figure is the cohort's own.

    One of the lead's prior-term six-week sections, at the hero's level, with its
    windows seeded (its week 2 closed in January). The week-2 comparison stays the
    round-1 cohort's own: 3.6 and 2.8 for the two panels and 8.3 hours (hand
    arithmetic at the top of this module).

    **What this test is, corrected after the round-4 battery.** It is a pin on the
    figure's value, not a killer for the term filter. The verifier showed that,
    with the term filter dropped, a prior-term window maps to a course week
    offset by the gap between the two terms' starts — seven months here, far past
    any section's length — so the January close lands on no course week A has,
    and this figure does not move.

    **What the term filter protects against** is two terms whose starts fall
    within one section length of each other (a short summer term beside a fall
    term, say): a section of the other term would then land on A's course weeks,
    and its earlier close would become A's cutoff. This suite's worlds carry two
    hand-written terms seven months apart and no machinery for a third, so that
    case is recorded as equivalent in practice for these tests (E5-14 manifest,
    Round 5) rather than planted.

    **Its near miss** is the test below, where an earlier close *in* A's term
    does move the cutoff.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    plant_a_section_beside(cohort, "prior", letter=PRIOR_LETTER, term=PRIOR_TERM)
    publish_every_week(cohort.world, "prior")
    report_door.commit()

    point = the_comparison_point(report_door, stream)
    mean = the_comparison_workload(report_door)[MEAN_FIELD]

    assert is_shown(point) and carries_number(point, COMPARISON_AT_WEEK_TWO[stream]), (
        f"The {stream} comparison point at week {REPORTED_WEEK} is {point!r}; the cohort answered "
        f"{COMPARISON_AT_WEEK_TWO[stream]} there. A prior-term section's January close has moved "
        "the cutoff, which is taken among the sections of A's own term."
    )
    assert carries_number(mean, WORKLOAD_MEAN_AT_WEEK_TWO), (
        f"The comparison workload mean at week {REPORTED_WEEK} is {mean!r}; the cohort reported "
        f"{WORKLOAD_MEAN_AT_WEEK_TWO} hours."
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_an_earlier_closing_section_in_the_same_term_does_move_the_cutoff(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """C3's twin: a current-term six-week section starting in week 1 cuts week 2 at *its* close.

    Nobody teaches it, so no reader-group rule would see it. The population rule
    does: its week-2 window closes weeks before the hero's, so the cutoff is its
    close and the cohort's rows — closing at the hero's instant — are out. The
    week-2 comparison no longer carries the cohort's figure.

    **The mutations it kills:** the round-3 reader-group cutoff, and a cutoff
    taken from A's own close.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    plant_a_section_beside(cohort, "early", letter=EARLY_LETTER)
    publish_every_week(cohort.world, "early")
    report_door.commit()

    point = the_comparison_point(report_door, stream)

    assert not carries_number(point, COMPARISON_AT_WEEK_TWO[stream]), (
        f"The {stream} comparison point at week {REPORTED_WEEK} still carries the cohort's "
        f"{COMPARISON_AT_WEEK_TWO[stream]}: {point!r}. A six-week section of this level in A's term "
        "closes week 2 in term week 2, and that is the population's cutoff."
    )


def how_the_week_two_figure_differs(door: ReportDoor, stream: str) -> list[str]:
    """Every way the week-2 comparison differs from the cohort's own hand-computed figures."""
    point = the_comparison_point(door, stream)
    mean = the_comparison_workload(door)[MEAN_FIELD]
    wrong = []
    if not (is_shown(point) and carries_number(point, COMPARISON_AT_WEEK_TWO[stream])):
        wrong.append(f"the {stream} point is {point!r}, not {COMPARISON_AT_WEEK_TWO[stream]}")
    if not carries_number(mean, WORKLOAD_MEAN_AT_WEEK_TWO):
        wrong.append(f"the workload mean is {mean!r}, not {WORKLOAD_MEAN_AT_WEEK_TWO}")
    return wrong


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_an_earlier_closing_section_of_another_length_never_moves_the_cutoff(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """C4: an eight-week section at the hero's level, week 2 closing in term week 2 — no effect.

    It is in A's term, at A's level, and its week-2 window closes six weeks before
    A's. It is not A's length, so it is not in A's population and not in the
    cutoff: the week-2 comparison keeps the cohort's hand-computed 3.6 / 2.8 and
    8.3 hours.

    **The mutation it kills:** the length filter dropped from the cutoff (the
    round-4 battery's C4 survivor), under which this close becomes the cutoff and
    the cohort's rows fall out. **Its near miss** is
    `test_an_earlier_closing_section_in_the_same_term_does_move_the_cutoff`, the
    same early close at A's length.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    plant_a_section_beside(cohort, "eight-weeks", letter=ANOTHER_LENGTH_LETTER)
    publish_every_week(cohort.world, "eight-weeks")
    report_door.commit()

    wrong = how_the_week_two_figure_differs(report_door, stream)
    assert not wrong, (
        f"An eight-week section's earlier week-2 close changed the six-week comparison: {wrong}. "
        "The cutoff is taken among sections of A's length and level only."
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_an_earlier_closing_section_at_another_level_never_moves_the_cutoff(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """C5: a six-week `UGGR` section, week 2 closing in term week 2 — no effect.

    A's length, A's term, an earlier close, and another level: not A's population
    and not in the cutoff. The week-2 comparison keeps the cohort's figures.

    **The mutation it kills:** the level filter dropped from the cutoff (the
    battery's C5 survivor). **Its near miss** is the same-level twin,
    `test_an_earlier_closing_section_in_the_same_term_does_move_the_cutoff`.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    other_level_course = cohort.world.seed(
        COURSE_TABLE,
        dict(cohort.spine),
        **{COURSE_NUMBER_COLUMN: COURSE_NUMBER_FOR_LEVEL[UGGR]},
    )
    plant_a_section_beside(cohort, "uggr-early", letter=EARLY_LETTER, course=other_level_course)
    publish_every_week(cohort.world, "uggr-early")
    report_door.commit()

    wrong = how_the_week_two_figure_differs(report_door, stream)
    assert not wrong, (
        f"A `UGGR` section's earlier week-2 close changed the `UG` comparison: {wrong}. The "
        "cutoff is taken among sections of A's length and level only; levels match exactly."
    )


def test_the_cutoff_is_the_reported_sections_own_close_when_it_is_the_earliest(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """C6b: A counts in its own minimum — when A closes strictly first, the cutoff is A's close.

    The cohort's set is planted with **no answers at all** (an empty plan), so its
    sections have no windows and take no part in the cutoff. A's only current-term
    peer with a week-2 window is B, a section of the hero's course starting a week
    later, whose week-2 window closes a week after A's (*T_B*). The figures come
    from three of the lead's prior-term sections (ten people, counted in full), so
    they are shown whatever the current-term cutoff.

    A response in B, inside B's week-2 window (after *T_A*, before *T_B*), is
    then counted only by a cutoff later than A's own close. The correct cutoff is
    min(*T_A*, *T_B*) = *T_A*, so it moves nothing.

    **The mutation it kills:** A left out of the minimum (the battery's C6b
    survivor) — the minimum taken over A's peers only, which is *T_B* here and
    counts the response. **Its near miss** is the same world read before the
    response: identical figures by construction; and the two-section test above,
    where a peer closing at A's instant hides the mutation.
    """
    cohort = benchmark_cohort(report_door, minimums=report_api_contract.minimums(), plans={})
    world = cohort.world
    plant_a_section_beside(
        cohort, "b", letter=SAME_LETTER, course=cohort.hero_course, weeks_later=1, ordinal="7"
    )
    publish_every_week(world, "b")
    led_sections(cohort, prefix="prior-set", sections=3, people=10, term=PRIOR_TERM)
    report_door.commit()

    t_a = hero_window_close(world, report_door, REPORTED_WEEK)
    b_opens, t_b = WINDOWS_BY_TERM_WEEK[world.term_week_of("b", REPORTED_WEEK)]
    assert t_a < b_opens < t_b, (
        f"B's week-{REPORTED_WEEK} window runs {b_opens.isoformat()} to {t_b.isoformat()}, and "
        f"A's closes {t_a.isoformat()}; this test needs A to close strictly first."
    )
    unshown = not_shown_at_the_week(report_door)
    assert not unshown, f"The control failed: these figures are not shown: {unshown}."
    before = members(report_door)

    answer_once(
        cohort,
        "b",
        subject="e5-14-r5-c6b",
        course_week=REPORTED_WEEK,
        last_submitted_at=b_opens + AN_HOUR,
    )
    report_door.commit()

    assert not moved(before, members(report_door)), (
        f"A response in B's week-{REPORTED_WEEK} window, which closes a week after A's, moved "
        f"{moved(before, members(report_door))} on A's report. A closes first in its population, "
        "so the cutoff is A's own close; a later one means A was left out of the minimum."
    )


# ---------------------------------------------------------------------------
# The remainder, per person p holding a grant on A.
# ---------------------------------------------------------------------------


def the_reviewers_scratch_world(door: ReportDoor, cohort: PlantedBenchmarkCohort) -> None:
    """Y (the door's instructor) teaches set-0; X co-teaches A and teaches set-1 and set-2.

    At course week 2 the round-1 plan deals ten people round-robin: set-0 holds
    four, set-1 and set-2 three each. Y subtracting set-0 leaves two sections and
    six people; X subtracting set-1 and set-2 leaves one section and four.
    """
    x = door.graph.person()
    teach(door, door.rows.taught_section_id, person=x)
    the_set_is_taught_by(door, cohort, door.person_id, cohort.labels[0])
    the_set_is_taught_by(door, cohort, x, *cohort.labels[1:])


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_the_reviewers_co_teaching_world_is_withheld(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """(b_p) per person: each co-instructor's own subtraction leaves too few — withheld.

    The privacy-authz re-check's verified scratch world. Under the union rule,
    *R* covered all three set sections, the remainder was empty, and the figure
    was shown — yet Y knows only set-0, and set-1 plus set-2 is two sections and
    six people. Per person, (b_Y) and (b_X) both fail: withheld.

    **The mutation it kills:** the union-*R* remainder. **Its near miss** is
    the twin below.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    the_reviewers_scratch_world(report_door, cohort)
    report_door.commit()

    leaked = not_withheld(the_comparison_figures_at_the_week(report_door, stream))
    assert not leaked, (
        f"These default-set members are shown: {leaked}. Y teaches set-0 and knows it; set-1 and "
        "set-2 are two sections and six people. The ruling checks the remainder per instructor."
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_the_reviewers_world_with_an_outside_remainder_at_both_minimums_is_shown(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """The twin: the same co-teaching, and an untaught remainder at both minimums — shown.

    **Green on d7b4561 and after.** **The mutation it kills:** a remainder rule
    that withholds whenever two instructors split the set.
    """
    minimums = report_api_contract.minimums()
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    the_reviewers_scratch_world(report_door, cohort)
    led_sections(
        cohort,
        prefix="outside",
        sections=minimums[report_api_contract.minimum_sections],
        people=minimums[report_api_contract.minimum_respondents],
    )
    report_door.commit()

    missing = not_shown(the_comparison_figures_at_the_week(report_door, stream))
    assert not missing, f"These default-set members are not shown: {missing}."


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_a_default_set_made_only_of_the_instructors_own_sections_is_shown(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """One instructor teaches the whole set: T(p) covers it, the remainder is empty — shown.

    The seeded world's case. **Green on d7b4561 and after.** **The mutation it
    kills:** "empty" read as "meets both minimums", which an empty remainder
    never does.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    the_set_is_taught_by(report_door, cohort, report_door.person_id)
    report_door.commit()

    missing = not_shown(the_comparison_figures_at_the_week(report_door, stream))
    assert not missing, f"These default-set members are not shown: {missing}."


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_an_instructors_thin_remainder_is_withheld(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """One instructor teaches the set; the rest is two thin sections, two people — withheld.

    **The mutation it kills:** (b_p) left out, or checked on the population - A
    only. **Its near miss** is the test above (an empty remainder) and the
    reviewer world's twin (a remainder at both minimums).
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    the_set_is_taught_by(report_door, cohort, report_door.person_id)
    led_sections(cohort, prefix="thin", sections=2, people=2)
    report_door.commit()

    leaked = not_withheld(the_comparison_figures_at_the_week(report_door, stream))
    assert not leaked, f"Default-set members shown over a two-person remainder: {leaked}."


def a_taught_set_a_prior_section_and_two_thin_ones(
    door: ReportDoor, cohort: PlantedBenchmarkCohort, *, prior_taught_by: Any
) -> None:
    """The set taught by the door's instructor, a prior-term section, and two thin sections."""
    the_set_is_taught_by(door, cohort, door.person_id)
    plant_a_section_beside(cohort, "prior", letter=PRIOR_LETTER, term=PRIOR_TERM)
    teach(door, cohort.world.section_id("prior"), person=prior_taught_by)
    for index in range(PRIOR_PEOPLE):
        answer_once(cohort, "prior", subject=f"e5-14-r4-prior-{index}", course_week=REPORTED_WEEK)
    led_sections(cohort, prefix="thin", sections=2, people=2)
    door.commit()


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_a_prior_term_section_the_instructor_taught_is_in_her_own_sections(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """T(p) spans every term: her prior-term section is subtracted, leaving two people.

    **The mutation it kills:** T(p) taken in A's term only. **Its near miss** is
    the twin below.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    a_taught_set_a_prior_section_and_two_thin_ones(
        report_door, cohort, prior_taught_by=report_door.person_id
    )

    leaked = not_withheld(the_comparison_figures_at_the_week(report_door, stream))
    assert not leaked, f"Default-set members shown over a two-person remainder: {leaked}."


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_a_prior_term_section_someone_else_taught_is_in_the_remainder(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """The twin: taught by somebody else, the prior section stays in the remainder — shown.

    Remainder: the prior section's eight and the thin sections' two, three
    sections and ten people. **Green on d7b4561 and after.**
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    a_taught_set_a_prior_section_and_two_thin_ones(
        report_door, cohort, prior_taught_by=report_door.graph.person()
    )

    missing = not_shown(the_comparison_figures_at_the_week(report_door, stream))
    assert not missing, f"These default-set members are not shown: {missing}."


def test_a_prior_term_section_the_instructor_taught_is_still_counted_in_the_figure(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """Counted in the figure: a shown figure moves when her own prior section gains a row.

    **Fixed at round 4 so the two reads share one cutoff.** The prior section's
    windows are seeded before the first read, so the answer planted between the
    reads adds a row and nothing else — the round-3 version seeded the window with
    the answer, and its cutoff could move between the reads (the battery's C3
    note). With the term filter in place the prior section never enters the
    cutoff anyway; seeding it first makes this test independent of that.

    **Green on d7b4561 and after.** **The mutation it kills:** T(p) excluded from
    the population (the withdrawn first round-3 ruling).
    """
    minimums = report_api_contract.minimums()
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    the_set_is_taught_by(report_door, cohort, report_door.person_id)
    plant_a_section_beside(cohort, "prior", letter=PRIOR_LETTER, term=PRIOR_TERM)
    publish_every_week(cohort.world, "prior")
    teach(report_door, cohort.world.section_id("prior"), person=report_door.person_id)
    led_sections(
        cohort,
        prefix="outside",
        sections=minimums[report_api_contract.minimum_sections],
        people=minimums[report_api_contract.minimum_respondents],
    )
    report_door.commit()
    unshown = not_shown_at_the_week(report_door)
    assert not unshown, f"The control failed: these figures are not shown: {unshown}."
    before = members(report_door)

    answer_once(cohort, "prior", subject="e5-14-r4-prior-counted", course_week=REPORTED_WEEK)
    report_door.commit()

    assert moved(before, members(report_door)), (
        "A response in a prior-term section the instructor taught moved nothing on a shown "
        "figure. Her sections are counted; T(p) only decides whether a figure may be shown."
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_a_co_instructor_who_teaches_the_set_leaves_a_thin_remainder(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """A second instructor on A teaches the set: her remainder is two thin sections — withheld.

    The door's instructor alone would see a remainder of five sections and twelve
    people; the co-instructor's is two and two. The figure is shown only if
    every instructor's remainder passes.

    **The mutation it kills:** the remainder checked for the requesting person
    only. **Its near miss** is the twin below.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    co_instructor = report_door.graph.person()
    teach(report_door, report_door.rows.taught_section_id, person=co_instructor)
    the_set_is_taught_by(report_door, cohort, co_instructor)
    led_sections(cohort, prefix="thin", sections=2, people=2)
    report_door.commit()

    leaked = not_withheld(the_comparison_figures_at_the_week(report_door, stream))
    assert not leaked, f"These default-set members are shown: {leaked}."


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_sections_taught_by_someone_with_no_grant_on_the_section_stay_in_the_remainder(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """The twin: the set taught by a person with no grant on A — nobody's subtraction — shown.

    **Green on d7b4561 and after.**
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    the_set_is_taught_by(report_door, cohort, report_door.graph.person())
    led_sections(cohort, prefix="thin", sections=2, people=2)
    report_door.commit()

    missing = not_shown(the_comparison_figures_at_the_week(report_door, stream))
    assert not missing, f"These default-set members are not shown: {missing}."


# ---------------------------------------------------------------------------
# B7: "empty" means zero contributors to the figure being sealed.
# ---------------------------------------------------------------------------


def a_taught_set_and_one_outside_respondent(
    door: ReportDoor, cohort: PlantedBenchmarkCohort, *, with_hours: bool
) -> None:
    """The set taught by the door's instructor, and one led section with one respondent.

    With `with_hours` false the respondent answers both ratings and leaves the
    hours unanswered: the outside section has a week row and no hour-reporter.
    """
    the_set_is_taught_by(door, cohort, door.person_id)
    plant_a_section_beside(cohort, "outside", letter=SAME_LETTER)
    answer_once(
        cohort,
        "outside",
        subject="e5-14-r4-b7",
        course_week=REPORTED_WEEK,
        workload=Decimal("30.0") if with_hours else None,
    )
    door.commit()


def test_a_workload_remainder_with_no_hour_reporters_counts_as_empty(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """B7: a workload remainder with a week row and zero hour-reporters is empty.

    "Empty" means zero contributors to the figure being sealed. The outside
    respondent reported no hours, so the workload remainder has no contributor
    and passes; the set's own hours (ten people, three sections) meet (a). So
    the workload mean and median are shown. The **rating** figures' remainder is
    that one respondent — non-empty and below — so the instructor point is
    withheld in the same payload, which is the proof that the outside section is
    in the remainder at all.

    **The mutation it kills:** "empty" read as "no week row", which withholds
    the workload figures here. **Its near miss** is the test below.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    a_taught_set_and_one_outside_respondent(report_door, cohort, with_hours=False)

    workload = the_comparison_workload(report_door)
    point = the_comparison_point(report_door, INSTRUCTOR_STREAM)

    assert is_withheld(point), (
        f"The control failed: the instructor comparison point is {point!r}. Its remainder is one "
        "rating contributor, so it is withheld — without that, the outside section is not in the "
        "remainder and this test says nothing about the workload's."
    )
    assert all(is_shown(figure) for figure in workload.values()), (
        f"The comparison workload figures are {workload}. The workload remainder has a week row "
        "and no hour-reporter, which is empty, so (b_p) passes and (a) holds on the set's hours."
    )


def test_a_workload_remainder_with_one_hour_reporter_is_withheld(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """B7's twin: the same respondent reports hours — the workload remainder is one person.

    **The mutation it kills:** the workload remainder counted by respondents to
    anything rather than by hour-reporters, or "empty" read so loosely that one
    hour-reporter passes.
    """
    cohort = a_cohort(report_door, report_api_contract, benchmark_cohort)
    a_taught_set_and_one_outside_respondent(report_door, cohort, with_hours=True)

    workload = the_comparison_workload(report_door)

    assert all(is_withheld(figure) for figure in workload.values()), (
        f"The comparison workload figures are {workload}. The remainder after the instructor's "
        "own sections is one person who reported hours — non-empty and below both minimums."
    )
