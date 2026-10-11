"""Figures are the student's own section only, and no count — E8-01, done-when 7.

> 7. **Figures are the student's own section only, and never a benchmark.** …
>    The payload has no response count, no classmate count, no response rate and
>    no workload mean (ruling 6, §5.4).

SPEC §4.1 item 1: students never see "other sections". The structural half of
done-when 7 (no benchmark, comparison, university or cohort member on any
student model) is `tests/unit/test_the_student_payload_schema_carries_nothing_of_
a_benchmark.py`; the route sweep is `test_every_student_route_carries_nothing_of_
a_benchmark.py`. This module is the runtime half over the new figures.

**The sibling section is the discriminator.** `Q1WW` shares the taught
section's course, term and week numbers — exactly what a figure keyed on the
course and week rather than the section would also match. It is given five
instructor-stream commenters of its own in course week 1, each rating the
instructor 4, so a distribution or comment list that took them in is visibly
different, and its own student reading them is the control that they are
readable at all.

**The count walk names stems, not today's spellings** (`docs/MISTAKES.md` entry
53), and is run on a planted payload first, both ways.

**Which failure a red is, before E8-01 lands:** `student_week.read` fails naming
the four members the work order adds.
"""

from typing import Any

import pytest
from fixtures.report_api import FULL_WEEK_COMMENTS, UNTAUGHT_COHORT
from fixtures.report_views import INSTRUCTOR_STREAM
from fixtures.student_week import (
    DISTRIBUTION,
    INSTRUCTOR_NAME,
    TREND,
    WORKLOAD_MEDIAN,
    comment_texts,
    keys_in,
    plant_comment,
    read,
    streams_of,
)
from fixtures.the_hold import HoldWorld

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

WEEK = 1
SIBLING_TEXTS = tuple(
    f"E8-01 the sibling section's comment {index + 1}: the tutor answered every forum post"
    for index in range(5)
)

# Course week 1's instructor ratings in the canonical world are 5, 4, 4 and 3
# (`FULL_WEEK_INSTRUCTOR_RATINGS`, its fifth respondent leaving the question
# unanswered); written out as the non-zero entries a distribution of them has.
OWN_INSTRUCTOR_DISTRIBUTION = {"3": 1, "4": 2, "5": 1}

# The stems a count, a rate or a mean of the workload would be spelled with.
COUNT_STEMS = ("count", "classmate", "respondent", "responses", "rate", "enrol")
WORKLOAD_STEM = "workload"


def non_zero(distribution: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in distribution.items() if value}


def counts_and_means(body: Any) -> list[tuple[str, str]]:
    """Every key naming a count, a rate, a classmate, or a workload figure other than the median.

    A `mean` is allowed only on a trend point (the week's rating mean, §5.4's
    trend); anywhere else it is a mean nobody settled, and the workload's is the
    one ruling 6 and §5.4 leave out.
    """
    found = []
    for where, key in keys_in(body):
        lowered = key.lower()
        if (
            any(stem in lowered for stem in COUNT_STEMS)
            or WORKLOAD_STEM in lowered
            and key != WORKLOAD_MEDIAN
            or lowered == "mean"
            and f".{TREND}[" not in where
        ):
            found.append((where, key))
    return sorted(found)


def test_the_count_walk_finds_each_forbidden_spelling_and_spares_the_settled_members() -> None:
    """The instrument, both ways. **A red here means this module is broken, not the code.**

    **The mutation this kills:** a walk that matched exact names, which a
    `classmates_responded` or a `workload_mean` walks past.
    """
    planted = {
        "response_count": 18,
        "classmates_responded": 18,
        "response_rate": 0.75,
        "workload_mean": 10.0,
        "workload": {"mean": 10.0},
        "streams": [{"trend": [{"course_week": 1, "mean": 4.0}], "comments": []}],
        WORKLOAD_MEDIAN: 9.0,
        "state": "published",
        "published_weeks": [1],
    }
    found = {key for _where, key in counts_and_means(planted)}
    expected = {
        "response_count",
        "classmates_responded",
        "response_rate",
        "workload_mean",
        "workload",
        "mean",
    }
    assert found == expected, f"The walk found {sorted(found)} in the planted payload."
    settled = {"streams": planted["streams"], WORKLOAD_MEDIAN: 9.0, "state": "published"}
    assert counts_and_means(settled) == [], "The walk took a settled member."


def test_a_students_week_carries_her_own_sections_figures_and_comments_and_not_the_siblings(
    hold: HoldWorld,
) -> None:
    """`F1WW`'s student reads course week 1 beside `Q1WW`'s five comments, and `Q1WW`'s too.

    The taught section's instructor distribution is its own four ratings, its
    comments its own five, and no sibling text is anywhere in the body. The
    sibling section's student reads the sibling's five — the control that they
    are there to be leaked.

    **The mutations this kills:** the figures or comments read by course and
    week rather than by section (the sibling's 4s join the distribution, its
    texts join the comments); the section taken from somewhere other than the
    route's own, scoped section. **The near miss:** the sibling student's read
    of the sibling's own comments.
    """
    world = hold
    for text in SIBLING_TEXTS:
        plant_comment(
            world, course_week=WEEK, stream=INSTRUCTOR_STREAM, text=text, cohort=UNTAUGHT_COHORT
        )
    sibling = world.section_id(UNTAUGHT_COHORT)
    assert str(sibling) != str(world.taught), "The sibling section is the taught one."
    own = world.a_student("own-section", world.taught)
    theirs = world.a_student("sibling-section", sibling)
    world.stand_after_the_opening(WEEK)

    body, answered = read(world, own, WEEK)
    sibling_body, _ = read(world, theirs, WEEK)

    sibling_streams = streams_of(sibling_body, "The sibling section's course week 1")
    sibling_texts = comment_texts(sibling_streams[INSTRUCTOR_NAME])
    assert sorted(sibling_texts) == sorted(SIBLING_TEXTS), (
        f"The sibling section's own student reads {sibling_texts}; this world planted five shown "
        "comments there. A broken world, not a red."
    )
    streams = streams_of(body, "The taught section's course week 1")
    instructor = streams[INSTRUCTOR_NAME]
    assert non_zero(instructor[DISTRIBUTION]) == OWN_INSTRUCTOR_DISTRIBUTION, (
        f"The taught section's instructor distribution is {instructor[DISTRIBUTION]}; its own "
        f"ratings make {OWN_INSTRUCTOR_DISTRIBUTION}, and the sibling's five 4s are not hers."
    )
    assert sorted(comment_texts(instructor)) == sorted(
        FULL_WEEK_COMMENTS
    ), f"The taught section's instructor stream carries {comment_texts(instructor)}."
    leaked = [text for text in SIBLING_TEXTS if text in answered.text]
    assert leaked == [], f"The student's page serves the sibling section's comments {leaked}."


def test_a_released_week_carries_no_count_no_rate_and_no_workload_mean(hold: HoldWorld) -> None:
    """Course week 1, released, walked for a count, a rate, a classmate or a workload mean.

    **The mutations this kills:** the instructor report's `rates` block, or its
    `responses` and `enrolled`, carried over to the student "for context" (ruling
    6: no classmate count, §5.4); and the workload block copied whole, mean and
    all (§5.4 lists the median). **The near misses:** `workload_median` and the
    trend's `mean`, which are there — and are required to be, so the walk is over
    a payload that has figures.
    """
    world = hold
    student = world.a_student("no-count", world.taught)
    world.stand_after_the_opening(WEEK)

    body, _ = read(world, student, WEEK)

    keys = {key for _where, key in keys_in(body)}
    assert {WORKLOAD_MEDIAN, "mean"} <= keys, (
        f"The released week carries the keys {sorted(keys)}, without the median or a trend mean, "
        "so the walk below would be over a payload with no figures."
    )
    assert counts_and_means(body) == [], (
        f"The released week carries {counts_and_means(body)}. Ruling 6 and §5.4: no response "
        "count, no classmate count, no response rate and no workload mean."
    )
