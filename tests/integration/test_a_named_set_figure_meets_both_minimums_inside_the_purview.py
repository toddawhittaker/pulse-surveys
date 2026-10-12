"""A named-set figure meets both benchmark minimums, counted inside the reader's purview — E9-05.

> 3. **The minimums hold.** A named-set figure over fewer than 3 sections or 10
>    distinct respondents inside the purview is suppressed, a mean, a median and
>    a drawn point alike; at exactly 3 and 10 it is shown. Marked `invariant`.

SPEC §4.1 item 7 and §5.1: "Computed from fewer than either, a benchmark line is
suppressed rather than shown thin, and a comparison mean or median is suppressed
rather than shown at all." The minimums are read from `Settings`, never written
down here: every count below is the configured minimum or one less.

**One world, one set, one series, four weeks.** Lead A leads course `a`, whose
sections number the section minimum; the set holds `a` and a course `o` led by
lead B, outside A's purview. Each week of the cohort is planted for one case:

  - week 2: the respondent minimum, in one section fewer than the minimum;
  - week 3: exactly both minimums — **the shown twin of every other week**;
  - week 4: every section, one respondent fewer than the minimum;
  - week 5: as many *responses* as the respondent minimum, from one person fewer
    — one student answers in two sections (`docs/MISTAKES.md` entry 50).

Course `o` is answered heavily in weeks 2, 4 and 5, so each thin week would clear
both minimums if `o`'s sections were counted: the minimum is about what lies
inside the reader's purview, and a count taken over the whole set is a red here.

**Every suppressed week sits beside week 3 in the same series**, shown with the
figures written out by hand below (`docs/MISTAKES.md` entry 3), and a suppressed
week is required to be *present* and suppressed, never dropped.

**Which failure a red is, before E9-05 lands:** a FAILED naming
`named_set_series`.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.named_set_figures import (
    COHORT,
    COURSE_FIGURE,
    INSTRUCTOR_FIGURE,
    WEEK_FIGURES,
    WORKLOAD_MEAN,
    WORKLOAD_MEDIAN,
    PurviewWorld,
    carries_value,
    is_shown,
    is_suppressed,
    start_of,
    the_week,
    week_figures,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

ONE_SECTION_SHORT = 2
AT_BOTH_MINIMUMS = 3
ONE_PERSON_SHORT = 4
RESPONSES_NOT_PEOPLE = 5

# Week 3's values. Two thirds of the respondents report the low hours, so the
# median sits on it and the mean above it: two statistics, two numbers.
INSTRUCTOR_RATING = Decimal("4")
COURSE_RATING = Decimal("2")
LOW_HOURS = Decimal("2.5")
HIGH_HOURS = Decimal("8.5")

# What everybody else answers, and what course `o` (outside A's purview) answers.
OTHER_RATING, OTHER_HOURS = Decimal("3"), Decimal("5.5")
OUTSIDE_RATING, OUTSIDE_HOURS = Decimal("1"), Decimal("20.5")


def the_minimums_world(world: PurviewWorld) -> dict[str, Any]:
    """Course `a` (lead A, the minimum's worth of sections) and course `o` (lead B), one set."""
    world.build()
    sections, respondents = world.sections_minimum, world.respondents_minimum
    world.course("a", department="home")
    labels = [f"a-{index}" for index in range(sections)]
    for label in labels:
        world.section(label, course="a")
    world.course("o", department="away")
    outside = ["o-0", "o-1"]
    for label in outside:
        world.section(label, course="o")
    world.lead("lead A", "a")
    world.lead("lead B", "o")
    world.named_set("the set", "a", "o")

    world.answer(
        labels[:-1],
        respondents=respondents,
        prefix="e9-05-min-sections",
        rating=OTHER_RATING,
        hours=OTHER_HOURS,
        course_week=ONE_SECTION_SHORT,
    )
    high = respondents // 3
    hours = [HIGH_HOURS] * high + [LOW_HOURS] * (respondents - high)
    world.answer(
        labels,
        respondents=respondents,
        prefix="e9-05-min-both",
        rating=INSTRUCTOR_RATING,
        course_rating=COURSE_RATING,
        hours=hours,
        course_week=AT_BOTH_MINIMUMS,
    )
    world.answer(
        labels,
        respondents=respondents - 1,
        prefix="e9-05-min-people",
        rating=OTHER_RATING,
        hours=OTHER_HOURS,
        course_week=ONE_PERSON_SHORT,
    )
    # Week 5: respondents - 2 people answer once each and one person answers in
    # two sections, so there are `respondents` responses from `respondents - 1`
    # people, and every section is answered.
    world.answer(
        labels,
        respondents=respondents - 2,
        prefix="e9-05-min-responses",
        rating=OTHER_RATING,
        hours=OTHER_HOURS,
        course_week=RESPONSES_NOT_PEOPLE,
    )
    world.answer_in_both(
        labels[0],
        labels[1],
        subject="e9-05-min-responses-twice",
        rating=OTHER_RATING,
        hours=OTHER_HOURS,
        course_week=RESPONSES_NOT_PEOPLE,
    )
    for course_week in (ONE_SECTION_SHORT, ONE_PERSON_SHORT, RESPONSES_NOT_PEOPLE):
        world.answer(
            outside,
            respondents=respondents,
            prefix=f"e9-05-min-outside-{course_week}",
            rating=OUTSIDE_RATING,
            hours=OUTSIDE_HOURS,
            course_week=course_week,
        )
    return {"hours": hours, "respondents": respondents, "sections": sections}


def assert_the_shown_twin(series: Any) -> None:
    """Week 3, at exactly both minimums: all four figures shown, each its own number."""
    twin = week_figures(the_week(series, start=start_of(COHORT), course_week=AT_BOTH_MINIMUMS))
    unshown = [name for name in WEEK_FIGURES if not is_shown(twin[name])]
    assert not unshown, (
        f"The control failed: at course week {AT_BOTH_MINIMUMS}, with exactly the configured "
        f"minimums of sections and distinct respondents inside the purview, {unshown} are not "
        f"shown: {twin!r}. §5.1 suppresses a figure 'computed from fewer than' the minimum, so "
        "the minimum itself is shown."
    )


def assert_every_figure_suppressed(series: Any, course_week: int, why: str) -> None:
    week = week_figures(the_week(series, start=start_of(COHORT), course_week=course_week))
    shown = {name: figure for name, figure in week.items() if not is_suppressed(figure)}
    assert not shown, (
        f"At course week {course_week} {why}, and these figures are not suppressed: {shown!r}. "
        "§4.1 item 7: 'a mean, a median, or any other statistic, not only a drawn line'."
    )


def test_a_named_set_week_one_section_short_inside_the_purview_is_suppressed_in_every_figure(
    purview_world: PurviewWorld,
) -> None:
    """Course week 2: the respondent minimum, in one section fewer than the section minimum.

    **The mutations this kills:** the section count taken over the whole set
    (course `o`'s two sections lift it over); the section minimum compared with
    `>` (one short is still short) or not compared at all; one of the four
    figures sealed and the others not. **The near miss:** week 3, every section,
    shown.
    """
    world = purview_world
    the_minimums_world(world)
    series = world.series("the set", "lead A")

    assert_the_shown_twin(series)
    assert_every_figure_suppressed(
        series, ONE_SECTION_SHORT, "the purview holds one section fewer than the minimum"
    )
    assert is_suppressed(
        week_figures(the_week(series, start=start_of(COHORT), course_week=ONE_SECTION_SHORT))[
            WORKLOAD_MEDIAN
        ]
    ), "The workload median at week 2 is shown over too few sections."


def test_a_named_set_week_one_respondent_short_inside_the_purview_is_suppressed_in_every_figure(
    purview_world: PurviewWorld,
) -> None:
    """Course week 4: every section, one distinct respondent fewer than the minimum.

    **The mutations this kills:** the respondent count taken over the whole set
    (course `o`'s students lift it); the respondent minimum compared with `>`;
    the mean sealed and the median not. **The near miss:** week 3, one more
    person, shown.
    """
    world = purview_world
    the_minimums_world(world)
    series = world.series("the set", "lead A")

    assert_the_shown_twin(series)
    assert_every_figure_suppressed(
        series, ONE_PERSON_SHORT, "one fewer person than the minimum answered inside the purview"
    )
    assert is_suppressed(
        week_figures(the_week(series, start=start_of(COHORT), course_week=ONE_PERSON_SHORT))[
            INSTRUCTOR_FIGURE
        ]
    ), "The drawn point at week 4 is shown over too few people."


def test_a_named_set_week_of_enough_responses_from_too_few_people_is_suppressed(
    purview_world: PurviewWorld,
) -> None:
    """Course week 5: the minimum's worth of responses, from one person fewer (entry 50).

    The minimum is "distinct respondents" (§5.1), a promise about people. One
    student answers in two sections here, so a count of responses or of
    (section, student) pairs reaches the minimum and a count of people does not.

    **The mutation this kills:** the respondent minimum compared with a count of
    responses. **The near miss:** week 3, where responses and people are equal
    and at the minimum.
    """
    world = purview_world
    the_minimums_world(world)
    series = world.series("the set", "lead A")

    assert_the_shown_twin(series)
    assert_every_figure_suppressed(
        series,
        RESPONSES_NOT_PEOPLE,
        "the minimum's worth of responses came from one person fewer than the minimum",
    )
    assert is_suppressed(
        week_figures(the_week(series, start=start_of(COHORT), course_week=RESPONSES_NOT_PEOPLE))[
            WORKLOAD_MEAN
        ]
    ), "The workload mean at week 5 is shown over too few people."


def test_a_named_set_week_at_exactly_both_minimums_is_shown_with_its_own_figures(
    purview_world: PurviewWorld,
) -> None:
    """Course week 3: exactly the section minimum and exactly the respondent minimum — shown.

    Each figure carries the number written out here by hand over the values this
    test planted (`docs/MISTAKES.md` entries 19 and 30): the instructor rating
    and the course rating everybody gave, the mean of the hours, and the median,
    which is the majority's value and not the mean.

    **The mutations this kills:** `>` where `>=` belongs (the minimum itself
    suppressed); course `o`'s week-3 answers counted (there are none, so this
    world could not see that — the three tests above do); mean and median
    swapped or one served twice.
    """
    world = purview_world
    planted = the_minimums_world(world)
    hours = planted["hours"]
    expected_mean = sum(hours, Decimal(0)) / len(hours)
    assert expected_mean != LOW_HOURS, "The planted hours make the mean equal the median."
    assert hours.count(LOW_HOURS) * 2 > len(hours), "The low hours are not the majority."

    series = world.series("the set", "lead A")
    week = week_figures(the_week(series, start=start_of(COHORT), course_week=AT_BOTH_MINIMUMS))

    for name, expected in (
        (INSTRUCTOR_FIGURE, INSTRUCTOR_RATING),
        (COURSE_FIGURE, COURSE_RATING),
        (WORKLOAD_MEAN, expected_mean),
        (WORKLOAD_MEDIAN, LOW_HOURS),
    ):
        assert carries_value(week[name], expected), (
            f"The {name} at course week {AT_BOTH_MINIMUMS} — exactly "
            f"{planted['sections']} sections and {planted['respondents']} distinct respondents "
            f"inside the purview — is {week[name]!r}, not {expected}."
        )
