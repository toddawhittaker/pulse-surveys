"""The university remainder removes every default set its reader can see — E5-14 round 5.

The privacy-authz final check on b2579f9 found, and verified through the report
route, that (c_p) removed only the reader's own sections and *this report's*
default set. A reader p teaching A (whose course lead L1 leads three more
sections) and S2 (whose course lead L2 leads three more) sees, at one cutoff,
A's default set D1, S2's default set D2, and the university line U on both
reports. U - D1 - D2 - her own two sections is whatever else is there: in the
reviewer's world, one unled section Z with one student, whose rating came back
out of the arithmetic.

**The ruling** (E5-14 work order, round 5), with its closure argument: fix one
reader p, one length and level, one term and one course week at one cutoff. Every
population p can see a figure for is a union of disjoint atoms — (i) p's own
sections; (ii) for each lead of one of p's sections here, that lead's sections
minus p's own; (iii) the rest. If every atom of kinds (ii) and (iii) is empty or
meets both minimums, no figure p can compute isolates fewer. (b_p) already
guarantees (ii); round 5 makes (c_p) guarantee (iii):

> (c_p) becomes: university - T(p) - the union of D(S), over every section S in T(p) **in
> A's term with A's length and level** (D(S) is S's default set as resolved
> today), is empty or meets both minimums.

**The world**, all at course week 2, all six-week sections at the hero's level in
the hero's term, closing week 2 at one instant:

- A — the door's section, taught by p (the door's instructor). Its course is led
  by L1, who leads `tests/fixtures/report_benchmarks.py`'s cohort set: three
  sections, ten people.
- S2 — a section on a new course led by L2, also taught by p. L2 leads three more
  sections, answered by ten people.
- Z — a section on an unled course, answered by one person.

**Every figure is read through the report route with p's own session**, on A's
report and on S2's. The university members (both panels' points, the workload
mean and median) are withheld on both; in the same payload the report's own
default-set figures are shown, which is the proof the route is serving figures
at all. Two twins, same world: without Z (the remainder is empty) and with Z's
course grown to both minimums — shown.

**The mutation this module kills:** (c_p) subtracting only this report's default
set — the b2579f9 behaviour, under which U - T(p) - D(this) still holds the other
lead's whole set and clears the minimums.

**Marked `invariant`** (§4.1 item 7); every test asserts in its own body.

**Written as a new file only**, while a mutation battery runs in this checkout:
the helpers below are local, and nothing existing is changed.
"""

from collections.abc import Callable
from typing import Any

import pytest
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

S2 = "s2"
SECOND_LEAD = "second-lead"


# ---------------------------------------------------------------------------
# Local helpers (nothing existing is changed while the battery runs).
# ---------------------------------------------------------------------------


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


def figures_of(door: ReportDoor, population: str, section_id: Any = None) -> dict[str, Any]:
    """One report's members for one population at course week 2: both points, mean, median."""
    body, answered = door.payload(course_week=REPORTED_WEEK, section_id=section_id)
    found: dict[str, Any] = {
        f"the {stream} {population} point": points_of(
            body, stream, population, answered=answered
        ).get(REPORTED_WEEK)
        for stream in STREAMS
    }
    workload = workload_figures(body, population, answered=answered)
    for name in (MEAN_FIELD, MEDIAN_FIELD):
        found[f"the {population} workload {name}"] = workload[name]
    return found


def answered_sections(
    cohort: PlantedBenchmarkCohort, *, prefix: str, sections: int, people: int, led: bool
) -> list[str]:
    """`sections` of the hero's length and level, answered at week 2 by `people`, round-robin.

    `led` maps the cohort's lead (L1) to their courses; otherwise the courses have
    no lead until a caller maps one.
    """
    labels = [f"{prefix}-{index}" for index in range(sections)]
    for label in labels:
        plant_a_section_beside(cohort, label, letter=SAME_LETTER, led=led)
    for index in range(people):
        answer_once(
            cohort,
            labels[index % sections],
            subject=f"e5-14-r5-{prefix}-{index}",
            course_week=REPORTED_WEEK,
        )
    return labels


def the_reviewers_world(
    door: ReportDoor,
    contract: Any,
    plant: Callable[..., Any],
    *,
    z_sections: int,
    z_people: int,
    l2_sections: int | None = None,
    l2_people: int | None = None,
) -> Any:
    """A (L1), S2 (L2) both taught by p; L2's other sections; Z unled.

    L1's other sections are the round-1 cohort set (three sections, ten people
    at week 2). L2's other sections default to both minimums; `l2_sections` and
    `l2_people` size them otherwise (round 6's lead atom). `z_sections` and
    `z_people` size the unled remainder; zero of each leaves it out. Answers S2's
    section id.
    """
    cohort = plant(door, minimums=contract.minimums())
    world = cohort.world
    minimums = contract.minimums()

    plant_a_section_beside(cohort, S2, letter=SAME_LETTER, led=False)
    publish_every_week(world, S2)
    second_lead_sections = answered_sections(
        cohort,
        prefix="l2",
        sections=minimums[contract.minimum_sections] if l2_sections is None else l2_sections,
        people=minimums[contract.minimum_respondents] if l2_people is None else l2_people,
        led=False,
    )
    world.lead(SECOND_LEAD, S2, *second_lead_sections)
    teach(door, world.section_id(S2))

    if z_sections:
        answered_sections(cohort, prefix="z", sections=z_sections, people=z_people, led=False)
    door.commit()
    return world.section_id(S2)


# ---------------------------------------------------------------------------
# The reviewer's world: withheld on both of p's reports.
# ---------------------------------------------------------------------------


def test_the_university_line_is_withheld_on_the_first_report(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """A's report: U - {A, S2} - D1 - D2 is Z, one section and one person — withheld.

    **The control, in the same payload:** A's own default-set figures (L1's
    three sections, ten people) are shown.

    **The mutation it kills:** (c_p) subtracting only this report's default set,
    D1 — under which the remainder is D2 plus Z, four sections and eleven people,
    and the university line is shown, and U - D1 - D2 - own recovers Z's student.
    **Its near misses** are the two twins below.
    """
    the_reviewers_world(
        report_door, report_api_contract, benchmark_cohort, z_sections=1, z_people=1
    )

    comparison = figures_of(report_door, COMPARISON_POPULATION)
    university = figures_of(report_door, UNIVERSITY_POPULATION)

    unshown = [where for where, figure in comparison.items() if not is_shown(figure)]
    assert not unshown, f"The control failed: A's default-set figures are not shown: {unshown}."
    leaked = {where: figure for where, figure in university.items() if not is_withheld(figure)}
    assert not leaked, (
        f"A's university members are shown: {leaked}. The reader teaches A (lead L1) and S2 "
        "(lead L2) and sees both default sets at this cutoff; the university minus her own "
        "sections and both default sets is one section with one person."
    )


def test_the_university_line_is_withheld_on_the_second_report(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """S2's report, read with the same session: the same remainder, Z — withheld.

    **The control, in the same payload:** S2's own default-set figures (L2's
    three sections, ten people) are shown.

    **The mutation it kills:** the same — on S2's report, (c_p) subtracting only
    D2 leaves D1 plus Z.
    """
    s2_id = the_reviewers_world(
        report_door, report_api_contract, benchmark_cohort, z_sections=1, z_people=1
    )

    comparison = figures_of(report_door, COMPARISON_POPULATION, section_id=s2_id)
    university = figures_of(report_door, UNIVERSITY_POPULATION, section_id=s2_id)

    unshown = [where for where, figure in comparison.items() if not is_shown(figure)]
    assert not unshown, f"The control failed: S2's default-set figures are not shown: {unshown}."
    leaked = {where: figure for where, figure in university.items() if not is_withheld(figure)}
    assert not leaked, (
        f"S2's university members are shown: {leaked}. The remainder after the reader's own "
        "sections and every default set she sees is one section with one person."
    )


# ---------------------------------------------------------------------------
# The twins: shown.
# ---------------------------------------------------------------------------


def test_without_the_unled_section_the_remainder_is_empty_and_the_line_is_shown(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """Twin 1: no Z. U - T(p) - D1 - D2 has no contributor — empty — shown on both reports.

    **Green today and after.** **The mutation it kills:** "empty" read as
    "meets both minimums", or (c_p) withholding whenever the reader sees two
    default sets.
    """
    s2_id = the_reviewers_world(
        report_door, report_api_contract, benchmark_cohort, z_sections=0, z_people=0
    )

    unshown = [
        f"{report}: {where}"
        for report, section_id in (("A", None), ("S2", s2_id))
        for where, figure in figures_of(
            report_door, UNIVERSITY_POPULATION, section_id=section_id
        ).items()
        if not is_shown(figure)
    ]
    assert not unshown, (
        f"These university members are not shown: {unshown}. With no section outside the "
        "reader's own and the two default sets she sees, the remainder is empty."
    )


def test_an_unled_remainder_at_both_minimums_keeps_the_line(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """Twin 2: Z's side grown to three sections and ten people — the remainder clears — shown.

    **Green today and after.** **The mutation it kills:** (c_p) written so that
    any non-empty remainder withholds.
    """
    minimums = report_api_contract.minimums()
    s2_id = the_reviewers_world(
        report_door,
        report_api_contract,
        benchmark_cohort,
        z_sections=minimums[report_api_contract.minimum_sections],
        z_people=minimums[report_api_contract.minimum_respondents],
    )

    unshown = [
        f"{report}: {where}"
        for report, section_id in (("A", None), ("S2", s2_id))
        for where, figure in figures_of(
            report_door, UNIVERSITY_POPULATION, section_id=section_id
        ).items()
        if not is_shown(figure)
    ]
    assert not unshown, (
        f"These university members are not shown: {unshown}. The remainder after the reader's "
        "own sections and both default sets is three sections and ten people."
    )


# ---------------------------------------------------------------------------
# Round 6: every lead atom is itself a university remainder.
#
# The privacy-authz closure-argument check on 0361fb3 found, and verified, that
# the university seal never checked the lead atoms themselves. The world: p
# teaches A (L1's other sections: three and ten people) and S2 (L2's other
# section: one, with one student), and nothing else of this length and level has
# answers. S2's default set is withheld — (b_p) sees to that — but the
# university line is shown on both reports, and U - p's own sections - D(A) is
# L2's lone student. The closure argument's atoms of kind (ii) — each lead's
# sections minus p's own — have to be empty or meet both minimums for the
# *university* figure too, not only for their own default-set figure.
# ---------------------------------------------------------------------------


def a_thin_second_lead(door: ReportDoor, contract: Any, plant: Callable[..., Any]) -> Any:
    """The round-6 world: L2's other sections are one section with one student; no Z."""
    return the_reviewers_world(
        door, contract, plant, z_sections=0, z_people=0, l2_sections=1, l2_people=1
    )


def test_a_thin_lead_atom_withholds_the_university_line_on_the_first_report(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """A's report: L2's atom is one student, and U - own - D(A) is that student — withheld.

    **The control, in the same payload:** A's own default-set figures (L1's
    three sections, ten people) are shown.

    **The mutation it kills:** the lead atoms not checked as university
    remainders — the round-5 code, under which (c_p) finds U - own - D(A) - D(S2)
    empty and shows the line. **Its near misses** are the two twins below: L2's
    atom at both minimums, and L2's atom with no answers at all.
    """
    a_thin_second_lead(report_door, report_api_contract, benchmark_cohort)

    comparison = figures_of(report_door, COMPARISON_POPULATION)
    university = figures_of(report_door, UNIVERSITY_POPULATION)

    unshown = [where for where, figure in comparison.items() if not is_shown(figure)]
    assert not unshown, f"The control failed: A's default-set figures are not shown: {unshown}."
    leaked = {where: figure for where, figure in university.items() if not is_withheld(figure)}
    assert not leaked, (
        f"A's university members are shown: {leaked}. The reader sees A's default set on this "
        "report, and the university minus her own sections and that set is L2's one student."
    )


def test_a_thin_lead_atom_withholds_the_university_line_on_the_second_report(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """S2's report, the same session: withheld too — the same atom is recoverable from here.

    **The control, in the same payload:** S2's own default-set figures are
    withheld — L2's atom is one student, so (b_p) refuses them — which is the
    proof the thin atom is in this world as described. Its twins below are what
    rule out a route that withholds everything.

    **The mutation it kills:** the same.
    """
    s2_id = a_thin_second_lead(report_door, report_api_contract, benchmark_cohort)

    comparison = figures_of(report_door, COMPARISON_POPULATION, section_id=s2_id)
    university = figures_of(report_door, UNIVERSITY_POPULATION, section_id=s2_id)

    shown = [where for where, figure in comparison.items() if not is_withheld(figure)]
    assert not shown, (
        f"The control failed: S2's default-set figures are not withheld: {shown}. L2's other "
        "sections hold one student, so this world is not the one this test describes."
    )
    leaked = {where: figure for where, figure in university.items() if not is_withheld(figure)}
    assert not leaked, (
        f"S2's university members are shown: {leaked}. Read beside A's report's default set, "
        "the university minus the reader's own sections isolates L2's one student."
    )


def test_an_empty_lead_atom_leaves_the_university_line_shown(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """Twin: L2's other section has no answers — an empty atom passes — shown on both reports.

    The twin with L2's atom at both minimums is
    `test_without_the_unled_section_the_remainder_is_empty_and_the_line_is_shown`
    above, which is exactly that world (L2 at both minimums, no Z) and is not
    duplicated here.

    **Green on 0361fb3 and after.** **The mutation it kills:** an atom check that
    treats an empty atom as below the minimums, which withholds the university
    line from every reader whose second lead has not had a week answered yet.
    """
    s2_id = the_reviewers_world(
        report_door,
        report_api_contract,
        benchmark_cohort,
        z_sections=0,
        z_people=0,
        l2_sections=1,
        l2_people=0,
    )

    unshown = [
        f"{report}: {where}"
        for report, section_id in (("A", None), ("S2", s2_id))
        for where, figure in figures_of(
            report_door, UNIVERSITY_POPULATION, section_id=section_id
        ).items()
        if not is_shown(figure)
    ]
    assert not unshown, (
        f"These university members are not shown: {unshown}. L2's other section has no answers, "
        "so its atom is empty, and the rest of the university is L1's three sections and ten people."
    )
