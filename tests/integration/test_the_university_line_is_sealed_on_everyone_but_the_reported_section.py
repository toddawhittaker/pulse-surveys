"""The university line is sealed on everyone but the reader's own section — E5-14, boundary HIGH.

The orchestrator's ruling on the spec-conformance HIGH, as the E5-14 work order
records it:

> The university figure for a week is shown only if (1) its contributors **other
> than the reported section** meet both minimums, and (2) the complement —
> university minus the reported section minus the default set — is either empty
> or itself meets both minimums. The reasons: the reader knows her own section's
> count and sum exactly, and the default set is shown beside the university line,
> so subtraction must never isolate a population below the minimums (§4.1 item
> 7's "every figure computed from a comparison set").

SPEC §4.1 item 7: "No figure computed from a comparison set is shown below the
benchmark minimum — a mean, a median, or any other statistic." A university mean
over the hero plus one other person is, to the hero, a mean over that one person:
she knows her own section's count and sum, so she subtracts them. The two
conditions are the two subtractions a reader of this report can make.

**Paired worlds, both directions, in the round-1 cohort.**
`tests/fixtures/report_benchmarks.py` already plants the first pair: at course
week 3 the set is one *person* short of the respondent minimum and at week 4 one
*section* short, while the hero's own section would lift either over it. Under the
old sealing (the whole population, hero included) those university points were
shown — round 1 asserted exactly that — and under this ruling they are withheld.
Their twin is week 2, where the set clears both minimums on its own: shown. The
second pair adds sections outside the default set at week 2 — a complement below
the minimums (withheld), and one at them (shown); the complement-empty twin is
the base world.

**Every withholding sits beside a figure that arrived in the same payload** —
the university line at the passing week, or the comparison line at the same week
— so a route answering nothing to everybody is red rather than green
(`docs/MISTAKES.md` entry 3).

**Marked `invariant`**: this is §4.1 item 7 at the wire.

**Which failure a red is on today's tree:** the three "withheld" tests fail on
their suppression assertion — the university line is sealed on the whole
population today — and the three "shown" tests pass.
"""

from collections.abc import Callable
from decimal import Decimal
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
    WEEK_THIN_PEOPLE,
    WEEK_THIN_SECTIONS,
    PlantedBenchmarkCohort,
    a_suppressed_figures_complaint,
    numbers_of,
    plant_a_section_beside,
    points_of,
    workload_figures,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

STREAMS = (INSTRUCTOR_STREAM, COURSE_STREAM)
STATISTICS = (MEAN_FIELD, MEDIAN_FIELD)

# The cohort letter every complement section is planted in: the hero's own, so a
# complement section's course week 2 closes at the hero's instant and counts under
# the freeze-at-close ruling as well.
COMPLEMENT_LETTER = "F"

# What a complement respondent answers. Not a value any figure here is asserted
# to carry; the tests ask shown-or-withheld, never which number.
COMPLEMENT_HOURS = Decimal("11.0")
COMPLEMENT_RATING = 2


def assert_withheld(figure: Any, where: str) -> None:
    """One member that must be suppressed: the flag, a reason, no figure, and no number at all."""
    assert (
        isinstance(figure, dict) and figure.get(SUPPRESSED_FIELD) is True
    ), a_suppressed_figures_complaint(figure, where)
    assert figure.get(REASON_FIELD), a_suppressed_figures_complaint(figure, where)
    assert figure.get(FIGURE_FIELD) is None, a_suppressed_figures_complaint(figure, where)
    assert not numbers_of(
        figure
    ), f"{where} says it is suppressed and carries the numbers {numbers_of(figure)}: {figure!r}."


def assert_shown(figure: Any, where: str) -> None:
    """One member that must be shown: not suppressed, and carrying its statistic."""
    assert (
        isinstance(figure, dict) and figure.get(SUPPRESSED_FIELD) is False
    ), f"{where} is {figure!r}, which is not a shown figure."
    assert numbers_of(figure), f"{where} says it is shown and carries no number: {figure!r}."


def a_complement(
    cohort: PlantedBenchmarkCohort, *, sections: int, respondents: int, prefix: str
) -> None:
    """Sections outside the default set, at the set's level and length, answering course week 2.

    Each is on a course with **no lead mapping at all**, so it is in the
    university population and outside the hero's default set: exactly the
    complement the ruling names. `respondents` distinct students are dealt
    round-robin over the sections, one response each, answering every question.
    """
    world = cohort.world
    labels = [f"{prefix}-{index}" for index in range(sections)]
    for label in labels:
        plant_a_section_beside(cohort, label, letter=COMPLEMENT_LETTER, led=False)
    for index in range(respondents):
        label = labels[index % sections]
        student = world.student(f"{prefix}-respondent-{index:02d}", enrolled_in=(label,))
        world.respond(
            label,
            course_week=WEEK_CLEAR,
            student=student,
            workload=COMPLEMENT_HOURS,
            instructor_rating=COMPLEMENT_RATING,
            course_rating=COMPLEMENT_RATING,
        )


@pytest.mark.parametrize(
    "thin_week",
    (WEEK_THIN_PEOPLE, WEEK_THIN_SECTIONS),
    ids=("one-person-short", "one-section-short"),
)
@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_the_university_point_is_withheld_when_only_the_readers_own_section_lifts_it(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
    thin_week: int,
) -> None:
    """Condition (1): the others, without the hero, fall short — so the point is withheld.

    At course week 3 the set is one person short of the respondent minimum, and
    at week 4 one section short of the section minimum. The university
    population is the set plus the hero's own section, which lifts either count
    over its minimum — and the hero knows her own count and sum, so a university
    mean at that week is to her a mean over the set's people alone: the very
    figure the comparison line suppresses beside it.

    **The control, in the same payload:** the university point at week 2, where
    the set clears both minimums without the hero, is shown.

    **The mutation it kills:** the university figure sealed on its whole
    population, hero included — which was E5-04's rule and the finding. **Its
    near miss** is `test_the_university_point_is_shown_when_the_others_clear_both_minimums`,
    the twin week where the others alone clear both minimums.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    body, answered = report_door.payload(course_week=WEEK_CLEAR)
    university = points_of(body, stream, UNIVERSITY_POPULATION, answered=answered)

    assert WEEK_CLEAR in university, (
        f"The {stream} panel's university series carries course weeks {sorted(university)} and "
        f"not {WEEK_CLEAR}."
    )
    assert_shown(
        university[WEEK_CLEAR],
        f"The control: the {stream} panel's university point at course week {WEEK_CLEAR}, where "
        "the set clears both minimums without the hero,",
    )
    assert thin_week in university, (
        f"The {stream} panel's university series carries course weeks {sorted(university)} and "
        f"drops {thin_week}. A withheld point is a suppressed point, never a missing one."
    )
    assert_withheld(
        university[thin_week],
        f"The {stream} panel's university point at course week {thin_week} — the set one "
        f"{'person' if thin_week == WEEK_THIN_PEOPLE else 'section'} short, lifted over the "
        "minimum only by the hero's own section —",
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_the_university_point_is_shown_when_the_others_clear_both_minimums(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """The twin of both pairs: others at both minimums, complement empty — shown, and not a copy.

    Course week 2 of the base world: the set clears both minimums on its own and
    every same-length, same-level section in the world is either the hero's or in
    her default set, so the complement is empty. The university point is shown.

    **And it is not the comparison point copied.** The two populations differ by
    the hero's own section, which answered both streams this week, so the two
    points are two different figures. This is the assertion round 1 made in the
    section-minimum test, which the sealing ruling moved here.

    **The mutations it kills:** a sealing rule that withholds the university line
    whenever the hero is in it (over-suppression — the line §5.1 requires would
    never be drawn); and the university series assembled as a copy of the
    comparison series.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    body, answered = report_door.payload(course_week=WEEK_CLEAR)
    comparison = points_of(body, stream, COMPARISON_POPULATION, answered=answered)
    university = points_of(body, stream, UNIVERSITY_POPULATION, answered=answered)

    assert WEEK_CLEAR in comparison and WEEK_CLEAR in university, (
        f"Course week {WEEK_CLEAR} is missing from a {stream} series: comparison "
        f"{sorted(comparison)}, university {sorted(university)}."
    )
    assert_shown(comparison[WEEK_CLEAR], f"The {stream} comparison point at week {WEEK_CLEAR}")
    assert_shown(university[WEEK_CLEAR], f"The {stream} university point at week {WEEK_CLEAR}")
    assert comparison[WEEK_CLEAR] != university[WEEK_CLEAR], (
        f"The {stream} panel's comparison and university points at course week {WEEK_CLEAR} are "
        f"the same figure: {comparison[WEEK_CLEAR]!r}. The university population is the set plus "
        "the hero's own section, which answered this stream this week, so a university point equal "
        "to the comparison point is the comparison series served twice."
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_the_university_line_is_withheld_when_a_thin_complement_could_be_subtracted_out(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """Condition (2): a complement below the minimums, next to a shown default set — withheld.

    One section outside the default set, answered by one person, at course week
    2. The others-than-the-hero clear both minimums (the set plus this one), so
    condition (1) alone would show the university line. But the default set is
    shown beside it, the reader knows her own section, and the university minus
    the two is this one person: the complement is non-empty and below the
    minimums, so the university figures are withheld — the trend point for both
    panels, and the workload mean and median.

    **The control, in the same payload:** the default set's own point and
    workload figures at the same week are shown.

    **The mutation it kills:** condition (2) left out, which shows a university
    mean from which one person's answer is recovered by two subtractions.
    **Its near miss** is
    `test_the_university_line_is_shown_when_the_complement_clears_both_minimums`.
    """
    cohort = benchmark_cohort(report_door, minimums=report_api_contract.minimums())
    a_complement(cohort, sections=1, respondents=1, prefix="e5-14-thin-complement")
    report_door.commit()

    body, answered = report_door.payload(course_week=WEEK_CLEAR)
    comparison = points_of(body, stream, COMPARISON_POPULATION, answered=answered)
    university = points_of(body, stream, UNIVERSITY_POPULATION, answered=answered)
    assert WEEK_CLEAR in comparison and WEEK_CLEAR in university, (
        f"Course week {WEEK_CLEAR} is missing from a {stream} series: comparison "
        f"{sorted(comparison)}, university {sorted(university)}."
    )
    assert_shown(
        comparison[WEEK_CLEAR],
        f"The control: the {stream} comparison point at course week {WEEK_CLEAR}",
    )
    assert_withheld(
        university[WEEK_CLEAR],
        f"The {stream} university point at course week {WEEK_CLEAR}, with one section and one "
        "person outside the default set —",
    )

    comparison_workload = workload_figures(body, COMPARISON_POPULATION, answered=answered)
    university_workload = workload_figures(body, UNIVERSITY_POPULATION, answered=answered)
    for name in STATISTICS:
        assert_shown(comparison_workload[name], f"The control: the comparison workload {name}")
        assert_withheld(
            university_workload[name],
            f"The university workload {name} at course week {WEEK_CLEAR}, beside a complement of "
            "one person —",
        )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_the_university_line_is_shown_when_the_complement_clears_both_minimums(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """Condition (2)'s other side: a complement at both minimums — nothing isolated, shown.

    As many sections outside the default set as the section minimum, answered by
    as many people as the respondent minimum. Subtracting the default set and
    the hero from the university line leaves a population at both minimums, which
    is a benchmark in its own right.

    **The mutation it kills:** condition (2) written as "the complement must be
    empty", which withholds the university line in every institution with more
    than one lead — that is, everywhere. **Its near miss** is the test above.
    """
    minimums = report_api_contract.minimums()
    cohort = benchmark_cohort(report_door, minimums=minimums)
    a_complement(
        cohort,
        sections=minimums[report_api_contract.minimum_sections],
        respondents=minimums[report_api_contract.minimum_respondents],
        prefix="e5-14-full-complement",
    )
    report_door.commit()

    body, answered = report_door.payload(course_week=WEEK_CLEAR)
    university = points_of(body, stream, UNIVERSITY_POPULATION, answered=answered)
    assert (
        WEEK_CLEAR in university
    ), f"The {stream} university series carries {sorted(university)} and not {WEEK_CLEAR}."
    assert_shown(
        university[WEEK_CLEAR],
        f"The {stream} university point at course week {WEEK_CLEAR}, beside a complement at both "
        "minimums,",
    )
    university_workload = workload_figures(body, UNIVERSITY_POPULATION, answered=answered)
    for name in STATISTICS:
        assert_shown(university_workload[name], f"The university workload {name}")
