"""No figure carries more precision than the page shows — E8-05, done-when 1.

> 1. **No figure carries more precision than the page shows** (privacy-authz
>    MED). The student trend's `mean` and the `workload_median` are rounded on
>    the server to one decimal before they enter the payload. Read beside
>    whole-number shares, an unrounded mean such as 30/7 named the rater count
>    (ruling 8, ruling 6). An invariant-marked test pins it with a seven-rater
>    week: the served mean has at most one decimal and is not the exact quotient.
>    Instructor figures are unchanged.

**Settled:** Python's `round(x, 1)` on the server; the field names unchanged.
So the expected values are written out by hand beside the exact ones they must
not be (`docs/MISTAKES.md` entry 19):

  - seven instructor ratings 5, 5, 4, 4, 4, 4, 4: exact mean 30/7 = 4.2857…,
    served 4.3. A seven in the denominator is what the unrounded figure gave away
    — the classmate count ruling 6 keeps off the page.
  - six workload answers 4, 6, 7, 7.5, 9 and 10: exact median 7.25, served
    `round(7.25, 1)` = 7.2 (7.25 is exact in binary, and Python rounds half to
    even). A median of an even count is where a second decimal appears.

Both are planted into course week 6, which nobody answered in the canonical
world, so nothing else moves either figure. The instructor's report for the
same week is the twin: it keeps the exact quotient.

**Which failure a red is, before E8-05 lands:** the precision assertions, on the
unrounded figures the current tree serves.
"""

from decimal import Decimal

import pytest
from fixtures.report_api import (
    COURSE_WEEK_FIELD,
    PAYLOAD_STREAM_KEY,
    STREAMS_MEMBER,
    TREND_FIELD,
    TREND_MEAN_FIELD,
)
from fixtures.report_comments import configured_threshold
from fixtures.report_views import INSTRUCTOR_STREAM
from fixtures.student_week import (
    INSTRUCTOR_NAME,
    WORKLOAD_MEDIAN,
    instructor_report,
    means_by_week,
    plant_ratings,
    plant_workloads,
    raters_in,
    read,
    streams_of,
    workload_answerers_in,
)
from fixtures.the_hold import HoldWorld

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

WEEK = 6
SEVEN_RATINGS = (5, 5, 4, 4, 4, 4, 4)
EXACT_MEAN = 30 / 7
SERVED_MEAN = 4.3
SIX_HOURS = tuple(Decimal(hours) for hours in ("4", "6", "7", "7.5", "9", "10"))
EXACT_MEDIAN = 7.25
SERVED_MEDIAN = 7.2


def at_most_one_decimal(value: float) -> bool:
    return round(value, 1) == value


def plant_the_week(world: HoldWorld) -> None:
    """Seven ratings and six workload answers in course week 6, read back from the rows."""
    threshold = configured_threshold()
    assert threshold <= len(SIX_HOURS), f"The threshold {threshold} withholds both figures."
    plant_ratings(world, course_week=WEEK, stream=INSTRUCTOR_STREAM, ratings=SEVEN_RATINGS)
    plant_workloads(world, course_week=WEEK, hours=SIX_HOURS)
    assert raters_in(world, WEEK, INSTRUCTOR_STREAM) == len(SEVEN_RATINGS)
    assert workload_answerers_in(world, WEEK) == len(SIX_HOURS)


def test_a_seven_rater_weeks_mean_is_served_to_one_decimal_and_not_as_the_exact_quotient(
    hold: HoldWorld,
) -> None:
    """Course week 6's instructor mean on the student's page: 4.3, never 4.2857….

    **The mutations this kills:** the mean served as computed (30/7, whose
    denominator is the rater count); the rounding done in the page rather than
    the server (the payload still carries the quotient); and a rounding to two
    places (4.29 keeps enough of the quotient to recover a small denominator).
    **The near miss:** the instructor's report for the same week, which keeps
    the exact figure (done-when 1: instructor figures are unchanged).
    """
    world = hold
    plant_the_week(world)
    student = world.a_student("precision-mean", world.taught)
    world.stand_after_the_opening(WEEK)

    body, _ = read(world, student, WEEK)
    served = means_by_week(streams_of(body, "Course week 6")[INSTRUCTOR_NAME]).get(WEEK)

    assert isinstance(served, int | float), f"Week 6's instructor mean is {served!r}."
    assert served != EXACT_MEAN, f"The student's mean is the exact quotient {served}."
    assert at_most_one_decimal(served), f"The student's mean {served} has more than one decimal."
    assert served == SERVED_MEAN, f"The student's mean is {served}; `round(30/7, 1)` is 4.3."


def test_an_even_counts_workload_median_is_served_to_one_decimal(hold: HoldWorld) -> None:
    """Course week 6's workload median on the student's page: 7.2, never 7.25.

    **The mutations this kills:** the median served unrounded; rounded half up
    by hand (7.3) rather than by the settled `round(x, 1)`. **The near miss:**
    the mean beside it, rounded by the same rule.
    """
    world = hold
    plant_the_week(world)
    student = world.a_student("precision-median", world.taught)
    world.stand_after_the_opening(WEEK)

    body, _ = read(world, student, WEEK)
    served = body[WORKLOAD_MEDIAN]

    assert isinstance(served, int | float), f"Week 6's workload median is {served!r}."
    assert served != EXACT_MEDIAN, f"The student's median is the exact {served}."
    assert at_most_one_decimal(served), f"The student's median {served} has two or more decimals."
    assert served == SERVED_MEDIAN, f"The student's median is {served}; `round(7.25, 1)` is 7.2."


def test_the_instructors_report_keeps_the_exact_mean_for_the_same_week(hold: HoldWorld) -> None:
    """Done-when 1: instructor figures are unchanged. The report's week-6 mean is 30/7.

    **The mutation this kills:** the rounding put in the shared mean helper
    (`reporting._mean_of`) rather than in the student's read, which would round
    the instructor's report too. **The near miss:** the student's 4.3, next door.
    """
    world = hold
    plant_the_week(world)
    world.stand_after_the_opening(WEEK)

    report = instructor_report(world, WEEK)
    trend = report[STREAMS_MEMBER][PAYLOAD_STREAM_KEY[INSTRUCTOR_STREAM]][TREND_FIELD]
    means = {point[COURSE_WEEK_FIELD]: point[TREND_MEAN_FIELD] for point in trend}

    assert means.get(WEEK) is not None, f"The instructor's trend for week 6 is {trend}."
    assert abs(float(means[WEEK]) - EXACT_MEAN) < 1e-9, (
        f"The instructor's week-6 mean is {means[WEEK]}; it was 30/7 = {EXACT_MEAN} before E8-05 "
        "and done-when 1 leaves instructor figures unchanged."
    )
