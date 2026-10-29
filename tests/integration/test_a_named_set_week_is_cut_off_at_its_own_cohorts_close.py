"""A named-set week counts what its own start cohort's window close had fixed — E9-05.

> 10. **The cutoff is the cohort's own close.** A response submitted after start
>    cohort C's week-N close and before another cohort's does not count in C's
>    week-N figure; one submitted before it does. Tested one second either side
>    (ADR 0178's rule).

README decision 14: "The cutoff of a named-set or roll-up figure is the start
cohort's own week-N window close in the term being viewed." ADR 0178's rule
counts a response if its window had closed by the cutoff and it was last changed
no later.

**The world.** A chair reads a set over two courses in her department: course
`f`, whose sections start with cohort F (2026-09-28), and course `h`, whose
sections start with cohort H (2026-11-09) — the same length and level, so one
set and one reader see both, and H's week-2 window closes six weeks after F's.
Each course is answered at course week 2 by the minimums' worth of people, one
hour before their own window closes (F: 4 and 6.5 hours; H: 3 and 4.5 hours).
One more student in F's first section answers 1 and 30.5 hours and is last
submitted **one second after** F's week-2 close — still six weeks before H's —
or, in the twin, one second before it.

**H's week 2 is asserted in both tests.** Its responses were all submitted after
F's close, so a read cutting every cohort at the earliest close of the term
withholds H's whole week; only a cutoff that is H's own counts them.

**Which failure a red is, before E9-05 lands:** a FAILED naming
`named_set_series`.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fixtures.named_set_figures import (
    COHORT,
    INSTRUCTOR_FIGURE,
    LATER_COHORT,
    WORKLOAD_MEAN,
    PurviewWorld,
    carries_value,
    start_of,
    the_week,
    week_figures,
)

pytestmark = pytest.mark.integration

ONE_SECOND = timedelta(seconds=1)

F_RATING, F_HOURS = Decimal("4"), Decimal("6.5")
H_RATING, H_HOURS = Decimal("3"), Decimal("4.5")
LATE_RATING, LATE_HOURS = Decimal("1"), Decimal("30.5")


def two_cohorts_and_one_response_at_the_edge(world: PurviewWorld, *, offset: timedelta) -> int:
    """The world in the module docstring, the edge response at F's close plus `offset`."""
    world.build()
    sections, respondents = world.sections_minimum, world.respondents_minimum
    world.course("f", department="home")
    world.course("h", department="home")
    f_labels = [f"f-{index}" for index in range(sections)]
    h_labels = [f"h-{index}" for index in range(sections)]
    for label in f_labels:
        world.section(label, course="f", cohort=COHORT)
    for label in h_labels:
        world.section(label, course="h", cohort=LATER_COHORT)
    world.led_alone("f")
    world.led_alone("h")
    world.chair("the chair", "home")
    world.named_set("both cohorts", "f", "h")

    f_close: datetime = world.close_of(f_labels[0])
    h_close: datetime = world.close_of(h_labels[0])
    assert f_close + ONE_SECOND < h_close, (
        f"F's week-2 close {f_close} is not before H's {h_close}; the edge response would not sit "
        "between the two cohorts' closes and the test would be about nothing. A broken world."
    )

    world.answer(
        f_labels, respondents=respondents, prefix="e9-05-cut-f", rating=F_RATING, hours=F_HOURS
    )
    world.answer(
        h_labels, respondents=respondents, prefix="e9-05-cut-h", rating=H_RATING, hours=H_HOURS
    )
    world.answer(
        f_labels[:1],
        respondents=1,
        prefix="e9-05-cut-edge",
        rating=LATE_RATING,
        hours=LATE_HOURS,
        last_submitted_at=f_close + offset,
    )
    return respondents


def test_a_response_one_second_after_its_cohorts_close_is_not_counted_while_another_is_open(
    purview_world: PurviewWorld,
) -> None:
    """F's week 2 holds exactly F's on-time answers; H's week 2 holds all of H's.

    **The mutations this kills:** one cutoff for the whole term at its *latest*
    week-2 close, or H's, which counts the late response (F's mean leaves 4);
    the cutoff `<` written `<=` the wrong way round in time; and one cutoff at
    the term's *earliest* close, which withholds H's week entirely. **The near
    miss:** the twin below, two seconds earlier, which counts it.
    """
    world = purview_world
    two_cohorts_and_one_response_at_the_edge(world, offset=ONE_SECOND)
    series = world.series("both cohorts", "the chair")

    f_week = week_figures(the_week(series, start=start_of(COHORT)))
    h_week = week_figures(the_week(series, start=start_of(LATER_COHORT)))

    assert carries_value(h_week[INSTRUCTOR_FIGURE], H_RATING) and carries_value(
        h_week[WORKLOAD_MEAN], H_HOURS
    ), (
        f"Cohort H's week 2 is {h_week!r}, not {H_RATING} and {H_HOURS} hours. Every H response "
        "was submitted after cohort F's week-2 close and before H's own, so a read that cut H at "
        "F's close withheld them: decision 14 cuts each cohort at its own close."
    )
    assert carries_value(f_week[INSTRUCTOR_FIGURE], F_RATING) and carries_value(
        f_week[WORKLOAD_MEAN], F_HOURS
    ), (
        f"Cohort F's week 2 is {f_week!r}, not {F_RATING} and {F_HOURS} hours. One response there "
        "was last submitted one second after F's week-2 close and is not counted (ADR 0178), "
        "however long cohort H's week 2 stays open."
    )


def test_a_response_one_second_before_its_cohorts_close_is_counted(
    purview_world: PurviewWorld,
) -> None:
    """The twin: the same response, last submitted one second before F's close, counts.

    Each figure is written out by hand over the planted values: the minimum's
    worth of answers at F's value and one at the edge value.

    **The mutation this kills:** a cutoff earlier than the cohort's close (the
    window's opening, or the close less a margin), which drops this response
    too and leaves the test above green on its own.
    """
    world = purview_world
    respondents = two_cohorts_and_one_response_at_the_edge(world, offset=-ONE_SECOND)
    series = world.series("both cohorts", "the chair")

    f_week = week_figures(the_week(series, start=start_of(COHORT)))
    with_it = (F_RATING * respondents + LATE_RATING) / (respondents + 1)
    with_its_hours = (F_HOURS * respondents + LATE_HOURS) / (respondents + 1)

    assert carries_value(f_week[INSTRUCTOR_FIGURE], with_it) and carries_value(
        f_week[WORKLOAD_MEAN], with_its_hours
    ), (
        f"Cohort F's week 2 is {f_week!r}, not {with_it} and {with_its_hours} hours. The edge "
        "response was last submitted one second before F's week-2 close, so it counts."
    )
    h_week = week_figures(the_week(series, start=start_of(LATER_COHORT)))
    assert carries_value(
        h_week[INSTRUCTOR_FIGURE], H_RATING
    ), f"Cohort H's week 2 is {h_week!r}, not {H_RATING}."
