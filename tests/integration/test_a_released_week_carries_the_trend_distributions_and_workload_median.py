"""What a released week shows a student — E8-01's figures, against SPEC §5.4.

> Each stream's trend and this week's rating distribution, and the workload
> median (no mean). The trend leaves out every `awaiting` week …

The hold's side of these figures is the invariant modules'. This one asks
whether the figures are *right*: the values a released page carries for the
canonical world's course week 1, written out by hand from what that world
plants (`tests/fixtures/report_api.py`), never derived by the code under test
(`docs/MISTAKES.md` entry 19).

  - Instructor ratings 5, 4, 4, 3 and one unanswered: mean 4.0; non-zero
    distribution `{"3": 1, "4": 2, "5": 1}`.
  - Course ratings 4, 4, 3, 3, 1: mean 3.0; non-zero `{"1": 1, "3": 2, "4": 2}`.
  - Workload hours 6, 8, 9, 11, 16: median 9.0, mean 10.0 — so a median and a
    mean are different numbers here, and both are exact in binary.

**The distribution's shape is the instructor report's** (the work order: keys
"1" to "5", "same shape as the instructor report's rating distribution"), so
each stream's is also compared with the instructor's own for the same week.

Not marked `invariant`: these are figures, not a confidentiality rule.

**Which failure a red is, before E8-01 lands:** `student_week.read` fails naming
the four members the work order adds.
"""

from typing import Any

import pytest
from fixtures.student_week import (
    COMMENTS,
    COURSE_NAME,
    DISTRIBUTION,
    INSTRUCTOR_NAME,
    NAME_OF_STREAM,
    RATING_KEYS,
    SMALL_N,
    WORKLOAD_MEDIAN,
    instructor_distribution,
    instructor_report,
    means_by_week,
    read,
    streams_of,
    trend_weeks,
)
from fixtures.the_hold import HoldWorld

pytestmark = pytest.mark.integration

NON_ZERO = {
    INSTRUCTOR_NAME: {"3": 1, "4": 2, "5": 1},
    COURSE_NAME: {"1": 1, "3": 2, "4": 2},
}
WEEK_ONE_MEAN = {INSTRUCTOR_NAME: 4.0, COURSE_NAME: 3.0}
WORKLOAD_MEDIAN_HOURS = 9.0
WORKLOAD_MEAN_HOURS = 10.0


def non_zero(distribution: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in distribution.items() if value}


def test_course_week_one_carries_its_distributions_trend_point_and_workload_median(
    hold: HoldWorld,
) -> None:
    """Course week 1, unanswered and so released, read an hour after it opened.

    **The mutations this kills:** the streams swapped (the course's ratings under
    the instructor); a distribution keyed by integers, or missing its empty
    buckets, where the instructor report's is keyed "1" to "5"; the workload mean
    served under the median's name (10.0 for 9.0); a mean divided by the response
    count rather than the answered count (3.2 for 4.0); and the small-N state on
    the wrong stream. **The near misses:** each value above, written out.
    """
    world = hold
    student = world.a_student("figures", world.taught)
    world.stand_after_the_opening(1)

    body, _ = read(world, student, 1)
    report = instructor_report(world, 1)
    streams = streams_of(body, "Course week 1")

    for stored, name in NAME_OF_STREAM.items():
        distribution = streams[name][DISTRIBUTION]
        assert set(distribution) == set(RATING_KEYS), (
            f"The {name} distribution is keyed {sorted(distribution)}; the work order: "
            f"{list(RATING_KEYS)}."
        )
        assert non_zero(distribution) == NON_ZERO[name], (
            f"The {name} distribution is {distribution}; course week 1's ratings make "
            f"{NON_ZERO[name]}."
        )
        assert distribution == instructor_distribution(report, stored), (
            f"The student's {name} distribution is {distribution} and the instructor report's is "
            f"{instructor_distribution(report, stored)}; the work order: the same shape."
        )
        means = means_by_week(streams[name])
        assert means == {
            1: WEEK_ONE_MEAN[name]
        }, f"The {name} trend's means are {means}; week 1's is {WEEK_ONE_MEAN[name]}."
    assert body[WORKLOAD_MEDIAN] == WORKLOAD_MEDIAN_HOURS, (
        f"`{WORKLOAD_MEDIAN}` is {body[WORKLOAD_MEDIAN]!r}. Hours 6, 8, 9, 11 and 16 have median "
        f"{WORKLOAD_MEDIAN_HOURS} (and mean {WORKLOAD_MEAN_HOURS}, which §5.4 does not show)."
    )
    assert streams[INSTRUCTOR_NAME][SMALL_N] is False
    assert streams[COURSE_NAME][SMALL_N] is True and streams[COURSE_NAME][COMMENTS] == []


def test_a_weeks_trend_runs_up_to_and_including_its_own_week_and_no_further(
    hold: HoldWorld,
) -> None:
    """An hour after week 3 opened, with nothing required: weeks 2 and 3 read.

    Week 3's trend has points for weeks 1, 2 and 3; week 2's for weeks 1 and 2.
    The means are the canonical world's: instructor 4.0, 4.0 and 3.0; course 3.0
    for week 1 and `None` for weeks 2 and 3, whose respondents rated only the
    instructor — a point with no mean, not a missing point (decision 1: one point
    per published, non-awaiting week).

    **The mutations this kills:** a trend over every published week whatever the
    page (week 2's carries week 3); a week with no ratings dropped from the
    trend, which makes a held week and an unrated one look alike; and a missing
    mean served as 0. **The near miss:** week 3's own point on week 3's page.
    """
    world = hold
    student = world.a_student("trend", world.taught)
    world.stand_after_the_opening(3)

    week_two, _ = read(world, student, 2)
    week_three, _ = read(world, student, 3)
    two = streams_of(week_two, "Course week 2")
    three = streams_of(week_three, "Course week 3")

    for name in (INSTRUCTOR_NAME, COURSE_NAME):
        assert trend_weeks(two[name]) == [1, 2], f"Week 2's {name} trend: {two[name]}."
        assert trend_weeks(three[name]) == [1, 2, 3], f"Week 3's {name} trend: {three[name]}."
    assert means_by_week(three[INSTRUCTOR_NAME]) == {
        1: 4.0,
        2: 4.0,
        3: 3.0,
    }, f"Week 3's instructor trend means are {means_by_week(three[INSTRUCTOR_NAME])}."
    assert means_by_week(three[COURSE_NAME]) == {
        1: 3.0,
        2: None,
        3: None,
    }, f"Week 3's course trend means are {means_by_week(three[COURSE_NAME])}."
