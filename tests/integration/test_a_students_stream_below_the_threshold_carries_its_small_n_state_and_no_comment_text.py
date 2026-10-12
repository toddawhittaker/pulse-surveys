"""SPEC §4.1 item 3, for students — E8-01, done-when 5.

> 5. **§4.1 item 3, for students.** In a week where a stream has fewer distinct
>    commenters than the threshold, the payload carries no comment text for that
>    stream and carries its small-N state; the other stream at or above the
>    threshold carries its comments. Tested at the threshold and one commenter
>    below it.

> 3. Below the n-threshold — fewer than that many distinct commenters in that
>    stream that week — raw comments in that stream are hidden from instructors
>    and students alike.

**The pair.** Course week 1's course stream holds no commenter in the canonical
world. Each case plants new respondents commenting about the course: the
configured threshold less one, or the threshold itself. The instructor stream
holds the canonical five throughout, which is the shown twin in the same payload.

**The counts are read back** in the unit the threshold is about — distinct
students, `response.user_id` (`docs/MISTAKES.md` entry 50) — through
`CommentWorld.commenters_in`, never trusted from the planting loop, and the
threshold is the configured one rather than a 5 written here.

**Which failure a red is, before E8-01 lands:** `student_week.read` fails naming
the four members the work order adds.
"""

import pytest
from fixtures.report_api import (
    FULL_WEEK_COMMENTS,
    TAUGHT_COHORT,
    TERM_WEEK_OF_COURSE_WEEK,
)
from fixtures.report_comments import configured_threshold
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.student_week import (
    COMMENTS,
    COURSE_NAME,
    INSTRUCTOR_NAME,
    SMALL_N,
    comment_texts,
    plant_comment,
    read,
    streams_of,
)
from fixtures.the_hold import HoldWorld

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

WEEK = 1


def commenters(world: HoldWorld, stream: str) -> int:
    """Distinct students holding a comment in one stream of course week 1, read from the rows."""
    world.door.refresh()
    return world.door.world.commenters_in(
        term_week=TERM_WEEK_OF_COURSE_WEEK[WEEK], stream=stream, cohort=TAUGHT_COHORT
    )


@pytest.mark.parametrize(
    "short_by", [1, 0], ids=["one-commenter-below-the-threshold", "at-the-threshold"]
)
def test_a_stream_is_small_n_with_no_text_below_the_threshold_and_shows_its_comments_at_it(
    hold: HoldWorld, short_by: int
) -> None:
    """The course stream at the threshold less `short_by`; the instructor stream at five.

    One commenter below: the course stream's `small_n` is true, its `comments`
    is empty, and none of its texts appears anywhere in what was served — while
    the instructor stream, in the same payload, is not small-N and carries its
    five. At the threshold: the course stream is not small-N and carries every
    one of its texts.

    **The mutations this kills:** `<=` for `<` (the at-threshold case reads
    small-N); a count of responses or of answers rather than of distinct
    commenters (entry 50); the small-N flag set and the comments served anyway
    ("the page hides them"); the flag computed once for the week rather than per
    stream (the instructor stream is held with it, or the course stream shown
    with it); and the threshold hard-coded rather than configured. **The near
    misses:** the instructor stream in the same payload, and the at-threshold
    case.
    """
    world = hold
    threshold = configured_threshold()
    assert threshold >= 2, f"The configured threshold is {threshold}; one below it plants nobody."
    planted = [
        f"E8-01 course comment {index + 1}: the module page links to last year's dates"
        for index in range(threshold - short_by)
    ]
    for text in planted:
        plant_comment(world, course_week=WEEK, stream=COURSE_STREAM, text=text)
    student = world.a_student(f"threshold-short-by-{short_by}", world.taught)
    world.stand_after_the_opening(WEEK)

    assert commenters(world, COURSE_STREAM) == threshold - short_by, (
        f"Course week 1's course stream holds {commenters(world, COURSE_STREAM)} distinct "
        f"commenters; this case planted {threshold - short_by}. A broken world, not a red."
    )
    assert commenters(world, INSTRUCTOR_STREAM) >= threshold, (
        f"Course week 1's instructor stream holds {commenters(world, INSTRUCTOR_STREAM)} distinct "
        f"commenters, below the threshold {threshold}, so it cannot be the shown twin."
    )

    body, answered = read(world, student, WEEK)
    streams = streams_of(body, "Course week 1")
    course = streams[COURSE_NAME]
    instructor = streams[INSTRUCTOR_NAME]

    assert (
        instructor[SMALL_N] is False
    ), f"The instructor stream, at {commenters(world, INSTRUCTOR_STREAM)} commenters, is small-N."
    assert sorted(comment_texts(instructor)) == sorted(
        FULL_WEEK_COMMENTS
    ), f"The instructor stream carries {comment_texts(instructor)}; it is at the threshold."
    if short_by:
        assert course[SMALL_N] is True, (
            f"The course stream, one commenter below the threshold ({threshold}), carries "
            f"`{SMALL_N}` = {course[SMALL_N]!r}. §4.1 item 3: its comments are hidden and the page "
            "shows the small-N state in their place."
        )
        assert (
            course[COMMENTS] == []
        ), f"The course stream below the threshold carries comments {course[COMMENTS]!r}."
        leaked = [text for text in planted if text in answered.text]
        assert leaked == [], (
            f"The page serves course-stream text {leaked} from a stream below the threshold. "
            "§4.1 item 3: hidden from instructors and students alike."
        )
    else:
        assert (
            course[SMALL_N] is False
        ), f"The course stream, at the threshold ({threshold}), is small-N."
        assert sorted(comment_texts(course)) == sorted(
            planted
        ), f"The course stream at the threshold carries {comment_texts(course)}; it is shown."
