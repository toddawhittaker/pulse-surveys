"""A named set holding a sibling lead's courses shows a lead nothing of them — E9-05.

> 1. **A sibling lead's set shows nothing of the sibling.** Lead A reads a set
>    made of A's course and sibling lead B's course: every figure equals the
>    figure over A's course alone (or both are suppressed), and B's
>    contribution is absent. Adding B's second course to the set changes no
>    figure A reads. Marked `invariant`.

SPEC §5.5 (ruling 5): a named set's figure "is computed only over the set's
sections inside the reader's purview … so a set built from a sibling lead's
courses shows a Lead Faculty member nothing beyond her own courses." §4.1 item 2:
a Lead Faculty assignment never grants sibling leads' courses.

**The world.** One department; lead A leads course `a`, lead B leads courses
`b` and `b2`; each course has as many sections as the section minimum and as
many respondents as the respondent minimum at course week 2, so every one of
the three is a figure in its own right. Each course's students give values no
other course gives (A 4 and 6.5 hours, B's first 1 and 20.5, B's second 2 and
3.5), so a figure carrying one of them says whose sections it was computed over.

**"Equals" is compared as data**, the whole series: every cohort, every week,
every figure's state and number. **"Absent" is asserted beside a present twin**
(`docs/MISTAKES.md` entry 3): B, reading the same set, is served B's own figure,
so B's contribution is a real figure the set can produce — A is refused it, not
spared it by an empty world.

**Which failure a red is, before E9-05 lands:** a FAILED naming
`named_set_series`, which `app.services.benchmarks` does not expose.
"""

from decimal import Decimal

import pytest
from fixtures.named_set_figures import (
    COHORT,
    INSTRUCTOR_FIGURE,
    WORKLOAD_MEAN,
    PurviewWorld,
    any_carries,
    as_data,
    carries_value,
    start_of,
    the_week,
    week_figures,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

A_RATING, A_HOURS = Decimal("4"), Decimal("6.5")
B_RATING, B_HOURS = Decimal("1"), Decimal("20.5")
B2_RATING, B2_HOURS = Decimal("2"), Decimal("3.5")


def two_leads_and_three_courses(world: PurviewWorld) -> None:
    """Lead A over `a`, lead B over `b` and `b2`, each course a figure of its own at week 2."""
    world.build()
    sections, respondents = world.sections_minimum, world.respondents_minimum
    for course, rating, hours in (
        ("a", A_RATING, A_HOURS),
        ("b", B_RATING, B_HOURS),
        ("b2", B2_RATING, B2_HOURS),
    ):
        world.course(course, department="home")
        labels = [f"{course}-{index}" for index in range(sections)]
        for label in labels:
            world.section(label, course=course)
        world.answer(
            labels,
            respondents=respondents,
            prefix=f"e9-05-sibling-{course}",
            rating=rating,
            hours=hours,
        )
    world.lead("lead A", "a")
    world.lead("lead B", "b", "b2")
    world.named_set("a and b", "a", "b")
    world.named_set("a alone", "a")
    world.named_set("a, b and b2", "a", "b", "b2")


def pooled(*groups: tuple[Decimal, int]) -> Decimal:
    """The mean over several groups of equal answers, by hand: Σ value x count / Σ count."""
    return sum((value * count for value, count in groups), Decimal(0)) / sum(
        count for _value, count in groups
    )


def test_a_lead_reading_a_set_with_a_sibling_leads_course_is_served_her_own_courses_figures_only(
    purview_world: PurviewWorld,
) -> None:
    """Lead A's series over {a, b} is her series over {a}, and carries nothing of b.

    **The controls in the body.** A's series over {a} shows her own week-2
    figure (4, and 6.5 hours) — so the equality is not two empty answers. B,
    reading {a, b}, is served b's figure (1) — so b's contribution exists and
    the set can produce it.

    **The mutations this kills:** the named set's population left unnarrowed (A
    is served the pooled 2.5, or b's own 1); the population narrowed to the
    reader's *teaching* grants instead of her purview; the narrowing applied to
    the cohorts but not to the population (A's cohort, b's sections). **The near
    miss that must stay green:** A's own figure, shown at both minimums.
    """
    world = purview_world
    two_leads_and_three_courses(world)
    respondents = world.respondents_minimum
    start = start_of(COHORT)

    with_sibling = world.series("a and b", "lead A")
    alone = world.series("a alone", "lead A")
    siblings_own = world.series("a and b", "lead B")

    own = week_figures(the_week(alone, start=start))
    assert carries_value(own[INSTRUCTOR_FIGURE], A_RATING) and carries_value(
        own[WORKLOAD_MEAN], A_HOURS
    ), (
        f"The control failed: lead A's series over her own course alone does not show her week-2 "
        f"figures ({A_RATING}, {A_HOURS} hours): {own!r}. Her course stands at both minimums."
    )
    theirs = week_figures(the_week(siblings_own, start=start))
    assert carries_value(theirs[INSTRUCTOR_FIGURE], B_RATING), (
        f"The control failed: lead B, reading the same set, is not served b's own figure "
        f"{B_RATING}: {theirs!r}. Without it, 'A sees nothing of b' could be a set that resolves "
        "nothing at all."
    )

    assert as_data(with_sibling) == as_data(alone), (
        "Lead A's series over a set holding her course and sibling lead B's differs from her "
        "series over her course alone.\n"
        f"  {{a, b}}: {as_data(with_sibling)}\n  {{a}}:    {as_data(alone)}\n"
        "SPEC §5.5: a named-set figure is 'computed only over the set's sections inside the "
        "reader's purview', so a set built from a sibling lead's courses shows a Lead Faculty "
        "member nothing beyond her own courses (§4.1 item 2)."
    )
    leaked = {
        "b's own rating": B_RATING,
        "b's own hours": B_HOURS,
        "the pooled rating over a and b": pooled((A_RATING, respondents), (B_RATING, respondents)),
        "the pooled hours over a and b": pooled((A_HOURS, respondents), (B_HOURS, respondents)),
    }
    served = {name: value for name, value in leaked.items() if any_carries(with_sibling, value)}
    assert not served, (
        f"Lead A's series over {{a, b}} carries {served}: sibling lead B's contribution reached "
        "her through a named set."
    )


def test_adding_the_sibling_leads_second_course_changes_no_figure_the_lead_reads(
    purview_world: PurviewWorld,
) -> None:
    """Done-when 1's last sentence: a set grown by a sibling course is the same series to A.

    **The control:** A's series over {a, b, b2} shows her own figure, so the
    equality is between two served answers.

    **The mutations this kills:** a population narrowed by the *first* sibling
    course only (a closed-set filter written for the case in front of it,
    `docs/MISTAKES.md` entry 53); b2's sections counted because b2's lead is not
    a lead A has been compared against before.
    """
    world = purview_world
    two_leads_and_three_courses(world)
    respondents = world.respondents_minimum
    start = start_of(COHORT)

    smaller = world.series("a and b", "lead A")
    larger = world.series("a, b and b2", "lead A")

    own = week_figures(the_week(larger, start=start))
    assert carries_value(own[INSTRUCTOR_FIGURE], A_RATING), (
        f"The control failed: lead A's series over {{a, b, b2}} does not show her own figure "
        f"{A_RATING}: {own!r}."
    )
    assert as_data(larger) == as_data(smaller), (
        "Adding sibling lead B's second course to the set changed what lead A is served.\n"
        f"  {{a, b}}:     {as_data(smaller)}\n  {{a, b, b2}}: {as_data(larger)}"
    )
    pooled_with_b2 = pooled((A_RATING, respondents), (B2_RATING, respondents))
    assert not any_carries(larger, B2_RATING) and not any_carries(larger, pooled_with_b2), (
        f"Lead A's series over {{a, b, b2}} carries b2's rating {B2_RATING} or the pooled "
        f"{pooled_with_b2}: {as_data(larger)}."
    )
