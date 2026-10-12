"""A set wholly outside the reader's purview answers what a thin set inside it answers — E9-05.

> 9. **"Outside" and "thin" look the same.** A set wholly outside the reader's
>    purview answers the same payload shape and suppression marker as a thin set
>    inside it.

SPEC §5.5's ticket text: "A set with no section inside the purview answers
suppressed figures, the same as a thin one, so a reader cannot tell 'outside my
purview' from 'too few'." E9-05's interface makes this hold by construction —
the cohorts come from the reader's purview, never from the set — and this is the
test that it does.

**The world.** Lead A leads course `a`, one section fewer than the section
minimum, answered by the respondent minimum: thin. Lead B leads course `b`, at
both minimums: a set over it is a real figure. A reads {b} (wholly outside) and
{a} (thin inside); the two answers are compared as data.

**The controls.** A's answer is not empty — it carries her cohort — so equality
is not two empty lists; and B, reading {b}, is served b's figure, so the set A
is refused is one that can produce a figure.

Marked `invariant`: this is the denial half of SPEC §4.1 item 2 for named sets —
the answer to a set outside the purview says nothing about what is in it.

**Which failure a red is, before E9-05 lands:** a FAILED naming
`named_set_series`.
"""

from decimal import Decimal

import pytest
from fixtures.named_set_figures import (
    COHORT,
    INSTRUCTOR_FIGURE,
    PurviewWorld,
    as_data,
    carries_value,
    every_figure,
    is_suppressed,
    start_dates,
    start_of,
    the_week,
    week_figures,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

A_RATING, A_HOURS = Decimal("4"), Decimal("6.5")
B_RATING, B_HOURS = Decimal("1"), Decimal("20.5")


def test_a_set_wholly_outside_the_purview_answers_exactly_what_a_thin_set_inside_it_answers(
    purview_world: PurviewWorld,
) -> None:
    """Lead A's answer for {b} equals her answer for the thin {a}: same cohorts, weeks and markers.

    **The mutations this kills:** cohorts taken from the set's sections (A's
    answer for {b} lists b's cohort, or none, and differs from the thin set's);
    an outside set answered with an empty list, a refusal or a different reason
    than "below-minimum"; and the population left unnarrowed, which serves A
    b's figure outright. **The near miss that must stay green:** B's own read of
    {b}, which is shown.
    """
    world = purview_world
    world.build()
    sections, respondents = world.sections_minimum, world.respondents_minimum
    world.course("a", department="home")
    thin = [f"a-{index}" for index in range(sections - 1)]
    for label in thin:
        world.section(label, course="a")
    world.course("b", department="home")
    full = [f"b-{index}" for index in range(sections)]
    for label in full:
        world.section(label, course="b")
    world.lead("lead A", "a")
    world.lead("lead B", "b")
    world.answer(
        thin, respondents=respondents, prefix="e9-05-thin-a", rating=A_RATING, hours=A_HOURS
    )
    world.answer(
        full, respondents=respondents, prefix="e9-05-outside-b", rating=B_RATING, hours=B_HOURS
    )
    world.named_set("outside", "b")
    world.named_set("thin inside", "a")

    outside = world.series("outside", "lead A")
    thin_inside = world.series("thin inside", "lead A")
    theirs = world.series("outside", "lead B")

    assert start_dates(thin_inside) == [start_of(COHORT)], (
        f"Lead A's answer for the thin set inside her purview lists cohorts "
        f"{start_dates(thin_inside)}, not her own one cohort {start_of(COHORT)}; the equality "
        "below would then compare two answers that hold nothing."
    )
    their_week = week_figures(the_week(theirs, start=start_of(COHORT)))
    assert carries_value(their_week[INSTRUCTOR_FIGURE], B_RATING), (
        f"The control failed: lead B, reading the set over her own course, is not served "
        f"{B_RATING}: {as_data(theirs)}."
    )
    unsuppressed = [figure for figure in every_figure(thin_inside) if not is_suppressed(figure)]
    assert not unsuppressed, (
        f"The thin set inside the purview serves figures that are not suppressed: "
        f"{unsuppressed!r}. It holds {sections - 1} sections, one fewer than the minimum."
    )
    assert as_data(outside) == as_data(thin_inside), (
        "Lead A can tell a set wholly outside her purview from a thin set inside it.\n"
        f"  outside:     {as_data(outside)}\n  thin inside: {as_data(thin_inside)}\n"
        "E9-05: 'A set with no section inside the purview answers suppressed figures, the same as "
        'a thin one, so a reader cannot tell "outside my purview" from "too few".\''
    )
