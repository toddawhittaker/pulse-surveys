"""No sequence of reads serves a lead two figures that differ by a sibling course — E9-05.

> 4. **No subtraction isolates a section outside the purview.** With S = {own
>    course, sibling course X} and S' = {own course}, no pair of figures the
>    reader can be served by this ticket's reads (the named-set figures over S
>    and S', and `section_benchmarks` for the own course's section read with the
>    reader in the seal) differs by a figure over X alone. … Editing a set
>    between two reads to add or drop X changes nothing the reader is served.
>    Marked `invariant`.

`docs/MISTAKES.md` entry 51: a property proven over one payload fails across the
sequence, because a reader who keeps the previous answer subtracts. So the reads
here are driven **in order, the way the reader meets them** — S' first, then S,
then the section's own report, then S' again after X is added to it, again after
X is dropped, and S again after X is dropped from it — and the property is
asserted over all of them.

**The world.** Lead A leads the own courses `a0 … a(n-1)`, one section each, as
many as the section minimum, answered by the respondent minimum (4, 6.5 hours).
Sibling lead B leads course `x`: one section, two respondents (1, 20.5 hours) —
thin, the course a subtraction would expose. Elsewhere, courses `z…` that nobody
here leads hold the minimums' worth of sections and people (2, 3.5 hours), so
the university line is not "A's courses plus X" and stays a benchmark in its own
right.

**What "differs by a figure over X alone" is asserted as.** The named-set reads
are required to be *equal* as data before and after every edit, so their
pairwise differences are empty; and no figure in any answer may carry X's own
statistics, or the statistics of A's courses pooled with X — the number a read
that let X in would serve, from which subtracting S' gives X.

**Which failure a red is, before E9-05 lands:** a FAILED naming
`named_set_series`.
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

OWN_RATING, OWN_HOURS = Decimal("4"), Decimal("6.5")
X_RATING, X_HOURS = Decimal("1"), Decimal("20.5")
ELSEWHERE_RATING, ELSEWHERE_HOURS = Decimal("2"), Decimal("3.5")
X_RESPONDENTS = 2


def own_courses_a_thin_sibling_and_a_university(world: PurviewWorld) -> list[str]:
    """The world in the module docstring; answers the own courses' labels."""
    world.build()
    sections, respondents = world.sections_minimum, world.respondents_minimum
    own = [f"a{index}" for index in range(sections)]
    for course in own:
        world.course(course, department="home")
        world.section(course, course=course)
    world.lead("lead A", *own)
    world.answer(
        own, respondents=respondents, prefix="e9-05-seq-own", rating=OWN_RATING, hours=OWN_HOURS
    )

    world.course("x", department="home")
    world.section("x", course="x")
    world.lead("lead B", "x")
    world.answer(
        ["x"], respondents=X_RESPONDENTS, prefix="e9-05-seq-x", rating=X_RATING, hours=X_HOURS
    )

    elsewhere = [f"z{index}" for index in range(sections)]
    for course in elsewhere:
        world.course(course, department="away")
        world.section(course, course=course)
        world.led_alone(course)
    world.answer(
        elsewhere,
        respondents=respondents,
        prefix="e9-05-seq-elsewhere",
        rating=ELSEWHERE_RATING,
        hours=ELSEWHERE_HOURS,
    )

    world.named_set("S", *own, "x")
    world.named_set("S prime", *own)
    return own


def test_no_read_in_the_sequence_serves_a_figure_that_isolates_the_sibling_course(
    purview_world: PurviewWorld,
) -> None:
    """Every answer in the sequence, compared and swept for X.

    **The control:** the first read shows A's own week-2 figures (4 and 6.5
    hours), so "every answer equal" is a statement about served figures.

    **The mutations this kills:** the named-set population not narrowed to the
    purview (S serves the pooled figure; S minus S' is X); membership resolved
    once and cached across reads while the cohorts are re-read (the edit shows
    up in one and not the other); the reader left out of the section report's
    seal *and* a university line that has only A's courses and X in it — the
    world plants `z…` so that line is not that, and X's own figure is checked
    for anyway. **The near miss that must stay green:** A's own figures, served
    in every read.
    """
    world = purview_world
    own = own_courses_a_thin_sibling_and_a_university(world)
    respondents = world.respondents_minimum
    start = start_of(COHORT)

    answers = {}
    answers["S prime, first"] = world.series("S prime", "lead A")
    answers["S"] = world.series("S", "lead A")
    report = world.section_benchmarks(own[0], reader="lead A")
    world.add_member("S prime", "x")
    answers["S prime, after X is added"] = world.series("S prime", "lead A")
    world.drop_member("S prime", "x")
    answers["S prime, after X is dropped again"] = world.series("S prime", "lead A")
    world.drop_member("S", "x")
    answers["S, after X is dropped"] = world.series("S", "lead A")

    first = week_figures(the_week(answers["S prime, first"], start=start))
    assert carries_value(first[INSTRUCTOR_FIGURE], OWN_RATING) and carries_value(
        first[WORKLOAD_MEAN], OWN_HOURS
    ), (
        f"The control failed: lead A's first read of her own courses does not show her week-2 "
        f"figures ({OWN_RATING}, {OWN_HOURS} hours): {first!r}."
    )

    baseline = as_data(answers["S prime, first"])
    moved = {
        name: as_data(answer) for name, answer in answers.items() if as_data(answer) != baseline
    }
    assert not moved, (
        "Reads of the named set changed across the sequence, so their difference is a figure the "
        f"reader can compute.\n  first read: {baseline}\n  then: {moved}\n"
        "Every set here differs from S' by sibling course X alone, and X lies outside lead A's "
        "purview: SPEC §5.5 computes a named-set figure only over the set's sections inside it."
    )

    pooled_rating = (OWN_RATING * respondents + X_RATING * X_RESPONDENTS) / (
        respondents + X_RESPONDENTS
    )
    pooled_hours = (OWN_HOURS * respondents + X_HOURS * X_RESPONDENTS) / (
        respondents + X_RESPONDENTS
    )
    forbidden = {
        "X's own rating": X_RATING,
        "X's own hours": X_HOURS,
        "A's courses pooled with X, rating": pooled_rating,
        "A's courses pooled with X, hours": pooled_hours,
    }
    everything = {**answers, "the own section's report, read with lead A": report}
    carried = {
        f"{name} in {where}": value
        for where, answer in everything.items()
        for name, value in forbidden.items()
        if any_carries(answer, value)
    }
    assert not carried, (
        f"A figure served to lead A carries {carried}. Each is X's contribution or A's courses "
        "pooled with it, and less the figure over S' it is a figure over X alone — a thin sibling "
        "course outside her purview (SPEC §4.1 items 2 and 7, MISTAKES entry 51)."
    )
