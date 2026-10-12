"""Ratings as shares, withheld when small — E8-01's fix round, ruling 8 (SPEC §5.4).

> 8. **Ratings as shares, hidden when small.** Students see each stream's
>    distribution as whole-number percentages summing to 100, never counts.
>    Below the n-threshold of distinct raters in a stream-week, the student gets
>    no distribution and no trend mean for that stream-week, only the small-N
>    notice; the workload median follows the same rule on workload answers.

**Why.** E8-01's privacy review: a count histogram summed to the classmate count
(the number ruling 6 forbids), and a small week's mean or median, less the
reader's own answer, gave back what the few classmates answered.

**The settled identifiers** (the coordinator's, the builder matches):
`StudentStream.shares: dict[str, int] | None`, keyed "1" to "5", largest-remainder
percentages summing to exactly 100, `None` when the stream-week's raters (distinct
students with a rating answer in that stream that week) are fewer than
`n_threshold`; `StudentTrendPoint.mean` `None` under the same rule, the point
kept; `workload_median` `None` when the week's distinct workload answerers are
fewer than `n_threshold`. `small_n` stays the comment rule.

**The pairs.** Course week 1's instructor stream has four raters in the
canonical world (its fifth respondent leaves the rating unanswered), and its
course stream five. Each pair plants new raters until the instructor stream sits
at the configured threshold less one, or at the threshold, and reads the counts
back in the unit the rule counts (`docs/MISTAKES.md` entry 50). The course stream,
or another week, is the present twin in the same world. The workload pair is
course week 2, which holds no workload answer in the canonical world.

**Largest remainder** is pinned on a week of eleven raters whose naive rounding
sums to 99, written out by hand (entry 19).

**Which failure a red is, before the fix round lands:** `streams_of` fails naming
`StudentStream`'s members (`shares` for `distribution`).
"""

import statistics
from decimal import Decimal

import pytest
from fixtures.report_comments import configured_threshold
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.student_week import (
    COURSE_NAME,
    INSTRUCTOR_NAME,
    RATING_KEYS,
    SHARES,
    WHOLE,
    WORKLOAD_MEDIAN,
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

PAIR = pytest.mark.parametrize(
    "short_by", [1, 0], ids=["one-rater-below-the-threshold", "at-the-threshold"]
)

# Every planted instructor rating in the pairs is a 4. Course week 1's own four
# are 5, 4, 4 and 3, so the mean stays exactly 4.0 however many 4s join them.
PLANTED_RATING = 4
MEAN_AT_THE_THRESHOLD = 4.0
COURSE_WEEK_ONE_MEAN = 3.0

# Eleven raters: one 1, two 2s, three 3s, five 4s. Exact shares 9.09, 18.18,
# 27.27 and 45.45; floors 9, 18, 27 and 45 sum to 99, so naive rounding is 99 too,
# and the one point left goes to the largest remainder, the 4s' .45.
ELEVEN_RATINGS = (1, 2, 2, 3, 3, 3, 4, 4, 4, 4, 4)
ELEVEN_SHARES = {"1": 9, "2": 18, "3": 27, "4": 46, "5": 0}
SHARES_WEEK = 6


def bring_week_one_instructor_raters_to(world: HoldWorld, wanted: int) -> None:
    """Plant 4s into course week 1's instructor stream until it holds `wanted` raters."""
    held = raters_in(world, 1, INSTRUCTOR_STREAM)
    assert held <= wanted, (
        f"Course week 1's instructor stream already holds {held} raters, more than the {wanted} "
        "this case needs; the configured threshold is too low for the pair. A broken world."
    )
    plant_ratings(
        world,
        course_week=1,
        stream=INSTRUCTOR_STREAM,
        ratings=[PLANTED_RATING] * (wanted - held),
    )
    assert raters_in(world, 1, INSTRUCTOR_STREAM) == wanted, "The planted raters did not land."


def raw_counts(world_ratings: list[int]) -> dict[str, int]:
    return {key: world_ratings.count(int(key)) for key in RATING_KEYS}


@PAIR
def test_a_streams_shares_are_withheld_below_the_threshold_of_raters_and_shown_at_it(
    hold: HoldWorld, short_by: int
) -> None:
    """Course week 1's instructor shares at the threshold less `short_by` raters.

    One below: `shares` is `None`, while the course stream in the same payload,
    at five raters, carries shares summing to 100. At the threshold: the
    instructor shares are keyed "1" to "5", sum to 100, sit on the ratings given,
    and no share equals that rating's raw count.

    **The mutations this kills:** shares computed for any stream with a rater
    (the small week's histogram, less the reader's own answer, is the others');
    the threshold compared with commenters rather than raters (week 1's
    instructor stream has five commenters and four raters); `<=` for `<`; and
    counts served under the new name. **The near misses:** the course stream's
    shares, and the at-threshold case.
    """
    world = hold
    threshold = configured_threshold()
    bring_week_one_instructor_raters_to(world, threshold - short_by)
    student = world.a_student(f"shares-short-by-{short_by}", world.taught)
    world.stand_after_the_opening(1)

    body, _ = read(world, student, 1)
    streams = streams_of(body, "Course week 1")
    course = streams[COURSE_NAME][SHARES]
    instructor = streams[INSTRUCTOR_NAME][SHARES]

    assert raters_in(world, 1, COURSE_STREAM) >= threshold, "The course twin is below threshold."
    assert isinstance(course, dict) and sum(course.values()) == WHOLE, (
        f"The course stream, at {raters_in(world, 1, COURSE_STREAM)} raters, carries shares "
        f"{course!r}; ruling 8: percentages summing to {WHOLE}."
    )
    if short_by:
        assert instructor is None, (
            f"The instructor stream, one rater below the threshold ({threshold}), carries "
            f"`{SHARES}` = {instructor!r}. Ruling 8: no distribution for a small stream-week."
        )
        return
    assert isinstance(instructor, dict) and set(instructor) == set(
        RATING_KEYS
    ), f"The instructor stream at the threshold carries `{SHARES}` = {instructor!r}."
    assert sum(instructor.values()) == WHOLE, f"The instructor shares sum to {instructor}."
    assert {key for key, share in instructor.items() if share} == {
        "3",
        "4",
        "5",
    }, f"The instructor shares are {instructor}; the ratings given are 3, 4 and 5."
    counts = raw_counts([5, 4, 4, 3] + [PLANTED_RATING] * (threshold - 4))
    equal = [key for key, share in instructor.items() if share and share == counts[key]]
    assert equal == [], f"The shares {instructor} carry the raw counts {counts} at {equal}."


@PAIR
def test_a_weeks_mean_is_withheld_below_the_threshold_on_its_own_page_and_on_a_later_one(
    hold: HoldWorld, short_by: int
) -> None:
    """Course week 1's instructor mean, read on week 1's page and as a point on week 3's.

    One below: the point for week 1 is there, its `mean` `None`, on both pages;
    the course stream's week-1 point, at five raters, carries 3.0 on both. At the
    threshold: the instructor point carries 4.0 on both.

    **The mutations this kills:** the mean withheld on the week's own page and
    served on a later page's trend (the past point is the leak a student reads a
    week later); the point dropped rather than its mean (decision 1 keeps it);
    and the rule applied to the page's week only. **The near misses:** the
    course stream's 3.0, and the at-threshold 4.0.
    """
    world = hold
    threshold = configured_threshold()
    bring_week_one_instructor_raters_to(world, threshold - short_by)
    student = world.a_student(f"mean-short-by-{short_by}", world.taught)
    world.stand_after_the_opening(3)

    pages = {
        week: streams_of(read(world, student, week)[0], f"Course week {week}") for week in (1, 3)
    }

    expected = None if short_by else MEAN_AT_THE_THRESHOLD
    for week, streams in pages.items():
        instructor = means_by_week(streams[INSTRUCTOR_NAME])
        course = means_by_week(streams[COURSE_NAME])
        assert 1 in instructor, f"Week {week}'s page has no instructor point for week 1."
        assert instructor[1] == expected, (
            f"On week {week}'s page the instructor point for week 1 carries {instructor[1]!r}; at "
            f"{threshold - short_by} raters against a threshold of {threshold}, ruling 8 gives "
            f"{expected!r}."
        )
        assert (
            course.get(1) == COURSE_WEEK_ONE_MEAN
        ), f"On week {week}'s page the course point for week 1 carries {course.get(1)!r}."


@PAIR
def test_a_weeks_workload_median_is_withheld_below_the_threshold_of_answerers(
    hold: HoldWorld, short_by: int
) -> None:
    """Course week 2's workload median at the threshold less `short_by` answerers.

    Week 2 holds no workload answer in the canonical world; this case plants
    2, 4, 6 … hours. One below: `workload_median` is `None`, while week 1's page
    in the same world, at five answerers, carries 9.0. At the threshold: the
    median of what was planted.

    **The mutations this kills:** the median served for any week with an
    answer; the threshold read off the week's responses or raters rather than
    its workload answerers. **The near misses:** week 1's 9.0, and the
    at-threshold median.
    """
    world = hold
    threshold = configured_threshold()
    hours = [Decimal(2 * (index + 1)) for index in range(threshold - short_by)]
    plant_workloads(world, course_week=2, hours=hours)
    planted = workload_answerers_in(world, 2)
    assert planted == threshold - short_by, f"Week 2 holds {planted} workload answerers."
    assert workload_answerers_in(world, 1) >= threshold, "Week 1's twin is below threshold."
    student = world.a_student(f"median-short-by-{short_by}", world.taught)
    world.stand_after_the_opening(2)

    week_two, _ = read(world, student, 2)
    week_one, _ = read(world, student, 1)

    assert week_one[WORKLOAD_MEDIAN] == 9.0, f"Week 1's median is {week_one[WORKLOAD_MEDIAN]!r}."
    expected = None if short_by else float(statistics.median(hours))
    assert week_two[WORKLOAD_MEDIAN] == expected, (
        f"Week 2, at {threshold - short_by} workload answerers against a threshold of "
        f"{threshold}, carries `{WORKLOAD_MEDIAN}` = {week_two[WORKLOAD_MEDIAN]!r}; ruling 8 gives "
        f"{expected!r}."
    )


def test_shares_are_whole_percentages_by_largest_remainder_and_sum_to_exactly_one_hundred(
    hold: HoldWorld,
) -> None:
    """Eleven instructor raters in course week 6: shares 9, 18, 27, 46 and 0.

    **The mutations this kills:** naive rounding (99 here, not 100); flooring
    without handing out the remainder; the remainder given to the largest share
    or the first key rather than the largest remainder (the 4s' .45 beats the
    3s' .27); and counts served (1, 2, 3, 5). **The near miss:** the exact
    figures, written out by hand.
    """
    world = hold
    assert configured_threshold() <= len(ELEVEN_RATINGS), "The threshold exceeds eleven raters."
    plant_ratings(world, course_week=SHARES_WEEK, stream=INSTRUCTOR_STREAM, ratings=ELEVEN_RATINGS)
    assert raters_in(world, SHARES_WEEK, INSTRUCTOR_STREAM) == len(ELEVEN_RATINGS)
    naive = sum(round(100 * ELEVEN_RATINGS.count(r) / len(ELEVEN_RATINGS)) for r in range(1, 6))
    assert naive == 99, f"Naive rounding sums to {naive}; the fixture no longer discriminates."
    student = world.a_student("largest-remainder", world.taught)
    world.stand_after_the_opening(SHARES_WEEK)

    body, answered = read(world, student, SHARES_WEEK)
    shares = streams_of(body, "Course week 6")[INSTRUCTOR_NAME][SHARES]

    assert shares == ELEVEN_SHARES, (
        f"Eleven raters (one 1, two 2s, three 3s, five 4s) carry shares {shares!r}; ruling 8's "
        f"largest-remainder percentages are {ELEVEN_SHARES}."
    )
    assert '"distribution"' not in answered.text, "The payload still carries a count histogram."
