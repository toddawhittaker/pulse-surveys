"""The hold over the student's figures, comments and batches — E8-01, done-when 1 and 2.

> 1. **A held week serves nothing about the week.** In a required-mode
>    section-week with no response, the payload carries the course label and the
>    state and no figure, no distribution, no workload, no trend point, no
>    comment, no small-N state and no batch. Asserted against the forbidden
>    members, beside a passing twin in one world: the same week after a publish
>    carries each of them.
> 2. **A held week reaches no other page.** With week 3 `awaiting` and week 4
>    released, week 4's trend has no point for week 3 in either stream, and
>    neither week's page serves a batch. After week 3 is published, week 4's
>    trend has the point. Read in that order, as a student meets it.

**The world** is E7-02's hold world over the canonical report world
(`tests/fixtures/report_api.py`): course week 1 holds five instructor-stream
commenters (at the default threshold, so shown) and no course-stream commenter
(so small-N); weeks 3 and 4 hold three and two instructor-stream commenters,
held below the threshold. Every week's figure is different from the others', and
week 3's instructor mean (3.0) is a number that would ride week 4's trend if a
held week leaked.

**Forbidden members, never "only these keys"** (the work order): E8-03 adds
`participation` to the same payload, the student's own posted record, which the
hold does not cover (ruling 4). So the held-week assertion names what may not be
there and walks the body for figure-only keys and numbers, stepping around that
one member by name.

**The sequence** (`docs/MISTAKES.md` entry 51): each test reads, changes the
world the way a week changes, and reads again, in one world, so the absence on
the first read sits beside its presence on the second (entry 3).

**Which failure a red is, before E8-01 lands:** `student_week.read` fails naming
the four members the work order adds.
"""

import pytest
from fixtures.report_api import FULL_WEEK_COMMENTS, HELD_COMMENTS
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.student_week import (
    COURSE_LABEL,
    COURSE_NAME,
    CUT_BEFORE_OPENING,
    DISTRIBUTION,
    FORBIDDEN_WHILE_HELD,
    INSTRUCTOR_NAME,
    KEYS_ONLY_A_FIGURE_CARRIES,
    RELEASED,
    SMALL_N,
    WORKLOAD_MEDIAN,
    a_batch,
    a_reply_to,
    answer_id_of,
    comment_texts,
    instructor_report,
    instructor_statuses,
    instructor_suppressed,
    keys_in,
    numbers_outside_the_own_record,
    publish_now,
    read,
    released_texts,
    required_from_the_first_week,
    streams_of,
    trend_weeks,
)
from fixtures.the_hold import AWAITING, PUBLISHED, STATE, HoldWorld, report_opens

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

FIRST_WEEK = 1
HELD = 3
RELEASED_WEEK = 4

REPLY = "E8-01 the teacher's reply: the reading list is on the course page from today"
LATE_REPLY = "E8-01 the teacher's late reply to week three: the recording is fixed"

BATCHED = (*HELD_COMMENTS[HELD], *HELD_COMMENTS[RELEASED_WEEK])


def test_a_held_week_serves_no_figure_comment_or_batch_and_after_its_publish_serves_each(
    hold: HoldWorld,
) -> None:
    """Course week 1, required and unanswered: the label and the state only. Then a publish.

    The first read is the closed door: every forbidden member `None`, no key that
    only a figure, a comment or a batch carries anywhere in the body, no number
    outside the week list and the student's own record, and none of the week's
    five comment texts anywhere in what was served. The second read, after the
    teacher publishes through E7-02's writer, is the twin: the same week carries
    a trend point, a distribution, the five comments, the course stream's small-N
    state, a workload median and a release group.

    **The premise is read through the instructor's report** (`docs/MISTAKES.md`
    entry 58): the instructor stream shows the five comments and the course stream
    is suppressed, so the held read's absences are absences of things that exist.

    **The mutations this kills:** the figures assembled before the hold is
    consulted (streams built, then the state set to `awaiting`); the hold applied
    to `response` only, as E7 left it; the small-N state served on a held week
    ("the course stream is held anyway"); the workload median read off the
    section rather than gated on the state; the release group shown on a held
    page. **The near misses:** the course label and the state, which the held
    week does carry, and the second read, which must carry every member the first
    forbids.
    """
    world = hold
    required_from_the_first_week(world)
    student = world.a_student("held-figures", world.taught)
    world.stand_after_the_opening(FIRST_WEEK)

    report = instructor_report(world, FIRST_WEEK)
    shown = instructor_statuses(report, INSTRUCTOR_STREAM)
    assert set(FULL_WEEK_COMMENTS) <= set(shown), (
        f"The instructor's report for course week 1 shows {sorted(shown)}, not the canonical "
        "world's five comments. A broken world, not a red: the held read below is about them."
    )
    assert instructor_suppressed(report, COURSE_STREAM) is True, (
        "The instructor's report does not hold course week 1's course stream; this world plants "
        "no commenter there, so the twin's small-N state has nothing to be about."
    )

    held, held_answer = read(world, student, FIRST_WEEK)
    publish_now(world, FIRST_WEEK, REPLY)
    released, _ = read(world, student, FIRST_WEEK)

    assert held[STATE] == AWAITING, f"A required, unanswered week read {held[STATE]!r}."
    assert {member: held[member] for member in FORBIDDEN_WHILE_HELD} == {
        member: None for member in FORBIDDEN_WHILE_HELD
    }, (
        f"The held week carries {[(m, held[m]) for m in FORBIDDEN_WHILE_HELD]}. Done-when 1: no "
        "figure, no distribution, no workload, no trend point, no comment, no small-N state and "
        "no batch."
    )
    assert isinstance(held[COURSE_LABEL], str) and held[COURSE_LABEL].strip(), (
        f"The held week carries `{COURSE_LABEL}` = {held[COURSE_LABEL]!r}. Done-when 1: the course "
        "label is the one thing about the course the closed door carries (ruling 2)."
    )
    figure_keys = [found for found in keys_in(held) if found[1] in KEYS_ONLY_A_FIGURE_CARRIES]
    assert figure_keys == [], f"The held week carries figure-only keys at {figure_keys}."
    numbers = numbers_outside_the_own_record(held)
    assert numbers == [], f"The held week carries the number(s) {numbers}. Done-when 1: no figure."
    leaked = [text for text in FULL_WEEK_COMMENTS if text in held_answer.text]
    assert leaked == [], f"The held week served comment text {leaked}."

    assert released[STATE] == PUBLISHED, f"After the publish the week read {released[STATE]!r}."
    streams = streams_of(released, "Course week 1 after its publish")
    for name in (INSTRUCTOR_NAME, COURSE_NAME):
        assert FIRST_WEEK in trend_weeks(streams[name]), (
            f"After the publish the {name} stream's trend has points for "
            f"{trend_weeks(streams[name])}; the twin carries course week 1's."
        )
    instructor = streams[INSTRUCTOR_NAME]
    assert (
        sum(instructor[DISTRIBUTION].values()) > 0
    ), f"After the publish the instructor distribution is {instructor[DISTRIBUTION]}."
    assert set(comment_texts(instructor)) == set(
        FULL_WEEK_COMMENTS
    ), f"After the publish the instructor stream carries {comment_texts(instructor)}."
    assert streams[COURSE_NAME][SMALL_N] is True, "After the publish the course stream is shown."
    assert isinstance(
        released[WORKLOAD_MEDIAN], int | float
    ), f"After the publish `{WORKLOAD_MEDIAN}` is {released[WORKLOAD_MEDIAN]!r}."
    assert isinstance(released[RELEASED], list), (
        f"After the publish course week 1 is the latest published week and nothing is awaiting, so "
        f"ruling 1 shows the group; `{RELEASED}` is {released[RELEASED]!r}."
    )


def test_a_held_week_reaches_no_later_page_until_it_is_published(hold: HoldWorld) -> None:
    """Weeks 1, 2 and 4 answered, week 3 not: week 4's page, read before and after week 3's publish.

    Read in the order a student meets it: week 3's page, then week 4's, then the
    teacher answers week 3, then week 4's again. A batch holding weeks 3 and 4's
    held comments is cut at 02:40 before week 4's report opens, so a release
    group is there to be withheld.

    Before: week 3 is `awaiting` with no batch; week 4 is published, its trend in
    both streams has points for weeks 1, 2 and 4 and none for 3, and it serves no
    batch (week 3 is published and `awaiting`, ruling 1) and none of the batch's
    text. After: week 4's trend has weeks 1 to 4, and the group carries the
    batch.

    **The mutations this kills:** the trend built over every published week
    without consulting each week's state (week 3's mean, 3.0, rides week 4's
    trend); a held week given a null point rather than none (decision 1:
    "a held week has no point (not a null point)"); the group shown whenever the
    page itself is released (ruling 1 asks about every published week); and the
    trend computed once and cached across the publish. **The near miss:** the
    after-read, which must carry both week 3's point and the batch.
    """
    world = hold
    required_from_the_first_week(world)
    for course_week in (1, 2, RELEASED_WEEK):
        a_reply_to(world, course_week, f"E8-01 the teacher's reply to course week {course_week}")
    a_batch(
        world,
        cut_at=report_opens(RELEASED_WEEK) - CUT_BEFORE_OPENING,
        answer_ids=[answer_id_of(world, text) for text in BATCHED],
    )
    student = world.a_student("held-sequence", world.taught)
    world.stand_after_the_opening(RELEASED_WEEK)

    week_three, week_three_answer = read(world, student, HELD)
    before, before_answer = read(world, student, RELEASED_WEEK)
    publish_now(world, HELD, LATE_REPLY)
    after, _ = read(world, student, RELEASED_WEEK)

    assert week_three[STATE] == AWAITING, f"Course week 3 read {week_three[STATE]!r}."
    assert week_three[RELEASED] is None, f"Held week 3 serves a batch: {week_three[RELEASED]!r}."
    assert before[STATE] == PUBLISHED, f"Course week 4 read {before[STATE]!r}."
    earlier = streams_of(before, "Course week 4 while week 3 is held")
    for name in (INSTRUCTOR_NAME, COURSE_NAME):
        assert trend_weeks(earlier[name]) == [1, 2, RELEASED_WEEK], (
            f"While week 3 is held, week 4's {name} trend has points for "
            f"{trend_weeks(earlier[name])}. Done-when 2: no point for week 3 (decision 1: one point "
            "per published, non-awaiting week up to the page's week)."
        )
    assert before[RELEASED] is None, (
        f"While week 3 is `awaiting`, week 4 serves the group {before[RELEASED]!r}. Ruling 1: never "
        "while any published week of the section is `awaiting`."
    )
    for answer in (week_three_answer, before_answer):
        leaked = [text for text in BATCHED if text in answer.text]
        assert leaked == [], f"A page read while week 3 is held served batched text {leaked}."

    later = streams_of(after, "Course week 4 after week 3's publish")
    for name in (INSTRUCTOR_NAME, COURSE_NAME):
        assert trend_weeks(later[name]) == [1, 2, HELD, RELEASED_WEEK], (
            f"After week 3's publish, week 4's {name} trend has points for "
            f"{trend_weeks(later[name])}; done-when 2: it gains week 3's."
        )
    assert sorted(released_texts(after)) == sorted(BATCHED), (
        f"After week 3's publish nothing is awaiting and week 4 is the latest published week, so "
        f"ruling 1 shows the batch cut before it opened; the group carries {released_texts(after)}."
    )
