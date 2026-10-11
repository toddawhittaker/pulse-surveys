"""What a released week shows a student — E8-01's figures, against SPEC §5.4 and ruling 8.

> Each stream's trend and this week's rating distribution, and the workload
> median (no mean). The trend leaves out every `awaiting` week …

Ruling 8 (the owner's, on E8-01's privacy review) shows the distribution as
`shares`, whole-number percentages summing to 100, and withholds the shares and
the trend mean of any stream-week with fewer raters than `n_threshold`.

The hold's side of these figures is the invariant modules', and the threshold
pairs are `test_a_students_figures_are_shares_and_are_withheld_below_the_
threshold.py`'s. This one asks whether the canonical world's figures are
*right*, written out by hand from what that world plants
(`tests/fixtures/report_api.py`), never derived by the code under test
(`docs/MISTAKES.md` entry 19):

  - Instructor ratings 5, 4, 4, 3 and one unanswered: four raters, below the
    default threshold of five, so no shares and no mean.
  - Course ratings 4, 4, 3, 3, 1: five raters; shares 20, 40, 40 on 1, 3, 4
    (never the counts 1, 2, 2); mean 3.0.
  - Workload hours 6, 8, 9, 11, 16: five answerers; median 9.0, mean 10.0 — so
    a median and a mean are different numbers here, and both are exact in binary.

Each side of the threshold is read back from the rows, not assumed.

Not marked `invariant`: these are figures, not a confidentiality rule.

**Which failure a red is, before the fix round lands:** `streams_of` fails naming
`StudentStream`'s members (`shares` for `distribution`).
"""

import pytest
from fixtures.report_comments import configured_threshold
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.student_week import (
    COMMENTS,
    COURSE_NAME,
    INSTRUCTOR_NAME,
    SHARES,
    SMALL_N,
    WORKLOAD_MEDIAN,
    means_by_week,
    raters_in,
    read,
    streams_of,
    trend_weeks,
)
from fixtures.the_hold import HoldWorld

pytestmark = pytest.mark.integration

COURSE_SHARES = {"1": 20, "2": 0, "3": 40, "4": 40, "5": 0}
COURSE_MEAN = 3.0
WORKLOAD_MEDIAN_HOURS = 9.0
WORKLOAD_MEAN_HOURS = 10.0


def test_course_week_one_carries_the_course_shares_and_mean_and_the_workload_median(
    hold: HoldWorld,
) -> None:
    """Course week 1, unanswered and so released, read an hour after it opened.

    **The mutations this kills:** the streams swapped (the course's figures under
    the instructor); counts served as shares (1, 2, 2); shares that do not sum to
    100 or are keyed by integers; the instructor stream's four-rater figures
    served (ruling 8); the workload mean served under the median's name (10.0 for
    9.0); and the small-N state on the wrong stream. **The near misses:** each
    value above, written out.
    """
    world = hold
    threshold = configured_threshold()
    instructor_raters = raters_in(world, 1, INSTRUCTOR_STREAM)
    course_raters = raters_in(world, 1, COURSE_STREAM)
    assert instructor_raters < threshold <= course_raters, (
        "Course week 1 no longer has its instructor stream below the threshold of raters and its "
        "course stream at it. A broken world, not a red."
    )
    student = world.a_student("figures", world.taught)
    world.stand_after_the_opening(1)

    body, _ = read(world, student, 1)
    streams = streams_of(body, "Course week 1")

    assert streams[COURSE_NAME][SHARES] == COURSE_SHARES, (
        f"The course shares are {streams[COURSE_NAME][SHARES]!r}; ratings 4, 4, 3, 3 and 1 make "
        f"{COURSE_SHARES}."
    )
    assert means_by_week(streams[COURSE_NAME]) == {
        1: COURSE_MEAN
    }, f"The course trend is {streams[COURSE_NAME]['trend']}; week 1's mean is {COURSE_MEAN}."
    instructor_shares = streams[INSTRUCTOR_NAME][SHARES]
    assert (
        instructor_shares is None
    ), f"The instructor stream, at {instructor_raters} raters, carries shares {instructor_shares}."
    assert means_by_week(streams[INSTRUCTOR_NAME]) == {1: None}, (
        f"The instructor trend is {streams[INSTRUCTOR_NAME]['trend']}; ruling 8: the point stays, "
        "its mean `None`."
    )
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
    Every instructor point's mean is `None` (four, two and three raters, all
    below the threshold — ruling 8); the course stream's is 3.0 for week 1 and
    `None` for weeks 2 and 3, which nobody rated. A point with no mean, never a
    missing point (decision 1: one point per published, non-awaiting week).

    **The mutations this kills:** a trend over every published week whatever the
    page (week 2's carries week 3); a week with no mean dropped from the trend,
    which makes a held week and a small one look alike; and a missing mean served
    as 0. **The near miss:** week 3's own point on week 3's page, and the course
    stream's 3.0.
    """
    world = hold
    threshold = configured_threshold()
    small = [raters_in(world, week, INSTRUCTOR_STREAM) for week in (1, 2, 3)]
    assert all(count < threshold for count in small), f"Instructor raters {small}; a broken world."
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
        1: None,
        2: None,
        3: None,
    }, f"Week 3's instructor trend means are {means_by_week(three[INSTRUCTOR_NAME])}."
    assert means_by_week(three[COURSE_NAME]) == {
        1: COURSE_MEAN,
        2: None,
        3: None,
    }, f"Week 3's course trend means are {means_by_week(three[COURSE_NAME])}."
