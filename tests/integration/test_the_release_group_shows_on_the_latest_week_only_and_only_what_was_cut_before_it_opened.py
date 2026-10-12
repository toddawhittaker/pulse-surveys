"""Release batches on the student's page follow ruling 1 — E8-01, done-when 3.

> 3. **Release batches follow ruling 1.** The group appears only on the latest
>    published week's page; never on an earlier week's page; never while any
>    published week of the section is `awaiting`; and it holds only batches cut
>    before the latest week's report opened, tested one second either side of
>    the opening. A comment in a batch never appears under its own week.

**The batches are planted, with the instant each test chose** —
`tests/fixtures/student_week.py`'s docstring says why the cutter cannot place a
cut one second from an opening. Each holds comments the canonical world already
holds: weeks 3 and 4's held instructor-stream comments, each with a `clear`
verdict and so `published`, and in the last test one comment from a week that is
shown.

**Every absence here sits beside its presence in the same world** (entry 3):
the earlier page beside the latest one, the withheld group beside the same group
once nothing is awaiting, the batch cut a second late beside the one cut a
second early, and the week after, where the late batch arrives.

**Which failure a red is, before E8-01 lands:** `student_week.read` fails naming
the four members the work order adds.
"""

import pytest
from fixtures.report_api import FULL_WEEK_COMMENTS, HELD_COMMENTS
from fixtures.report_views import INSTRUCTOR_STREAM
from fixtures.student_week import (
    CUT_BEFORE_OPENING,
    INSTRUCTOR_NAME,
    ONE_SECOND,
    RELEASED,
    STREAM,
    a_batch,
    a_reply_to,
    answer_id_of,
    comment_texts,
    instructor_released_statuses,
    instructor_report,
    instructor_statuses,
    instructor_suppressed,
    plant_comment,
    publish_now,
    read,
    released_texts,
    required_from_the_first_week,
    streams_of,
)
from fixtures.the_hold import AWAITING, STATE, HoldWorld, report_opens

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

LATEST = 4
NEXT = 5
WEEK_THREE = tuple(HELD_COMMENTS[3])
WEEK_FOUR = tuple(HELD_COMMENTS[4])

# A sixth instructor-stream comment for course week 1, released in a batch. The
# week keeps its five canonical commenters outside the batch, so it stays at the
# threshold and shown: the comment's absence under its own week is then about the
# batch and not about the stream being held.
RELEASED_FROM_A_SHOWN_WEEK = (
    "E8-01 released from week one: the seminar room was too small for everyone who came"
)


def test_the_group_shows_on_the_latest_published_weeks_page_and_on_no_earlier_one(
    hold: HoldWorld,
) -> None:
    """One batch, cut before week 4 opened; weeks 1, 3 and 4 read an hour after week 4 opened.

    No policy, so nothing is `awaiting`. Week 4 is the latest published week and
    carries the group, each item under the instructor stream it came from; weeks
    1 and 3 carry `None`.

    **The mutations this kills:** the group on every released page (the earlier
    pages carry it), and the group on the page of the week the batch's comments
    came from (week 3's page carries it). **The near miss:** week 4's page, which
    must carry exactly the batch.
    """
    world = hold
    a_batch(
        world,
        cut_at=report_opens(LATEST) - CUT_BEFORE_OPENING,
        answer_ids=[answer_id_of(world, text) for text in WEEK_THREE],
    )
    student = world.a_student("latest-only", world.taught)
    world.stand_after_the_opening(LATEST)

    latest, _ = read(world, student, LATEST)
    earlier = {week: read(world, student, week) for week in (1, 3)}

    assert sorted(released_texts(latest)) == sorted(WEEK_THREE), (
        f"Week 4, the latest published week, carries the group {latest[RELEASED]!r}; ruling 1 "
        f"shows the batch cut before it opened: {sorted(WEEK_THREE)}."
    )
    assert {item[STREAM] for item in latest[RELEASED]} == {INSTRUCTOR_NAME}, (
        f"The released items name the streams {[item[STREAM] for item in latest[RELEASED]]}; every "
        "batched comment here was written in the instructor stream."
    )
    for week, (body, answered) in earlier.items():
        assert body[RELEASED] is None, (
            f"Course week {week}'s page carries the group {body[RELEASED]!r}. Ruling 1: the latest "
            "published week's page only."
        )
        leaked = [text for text in WEEK_THREE if text in answered.text]
        assert leaked == [], f"Course week {week}'s page served batched text {leaked}."


def test_the_group_waits_while_an_earlier_week_is_awaiting_and_shows_once_it_is_answered(
    hold: HoldWorld,
) -> None:
    """Required; weeks 2 to 4 answered, week 1 not. Week 4's page either side of week 1's publish.

    The awaiting week is the *earliest*, not the one beside the page, so a rule
    that looked only at the week before the latest is visible. E8-01's done-when
    2 has the neighbouring case.

    **The mutations this kills:** "no published week is awaiting" read as "the
    page's own week is not awaiting", or as "the week before is not"; and the
    group withheld for good once it has been withheld. **The near miss:** the
    read after week 1's publish, which must carry the batch.
    """
    world = hold
    required_from_the_first_week(world)
    for course_week in (2, 3, LATEST):
        a_reply_to(world, course_week, f"E8-01 the teacher's reply to course week {course_week}")
    a_batch(
        world,
        cut_at=report_opens(LATEST) - CUT_BEFORE_OPENING,
        answer_ids=[answer_id_of(world, text) for text in WEEK_THREE],
    )
    student = world.a_student("withheld-group", world.taught)
    world.stand_after_the_opening(LATEST)

    first, _ = read(world, student, 1)
    before, before_answer = read(world, student, LATEST)
    publish_now(world, 1, "E8-01 the teacher's late reply to course week one")
    after, _ = read(world, student, LATEST)

    assert first[STATE] == AWAITING, f"Course week 1, required and unanswered, read {first!r}."
    assert before[RELEASED] is None, (
        f"While course week 1 is `awaiting`, week 4 carries the group {before[RELEASED]!r}. Ruling "
        "1: never while any published week of the section is `awaiting`."
    )
    leaked = [text for text in WEEK_THREE if text in before_answer.text]
    assert leaked == [], f"Week 4's page served batched text {leaked} while week 1 was held."
    assert sorted(released_texts(after)) == sorted(
        WEEK_THREE
    ), f"After week 1's publish nothing is awaiting, and week 4 carries {after[RELEASED]!r}."


def test_a_batch_cut_a_second_before_the_opening_shows_and_one_cut_a_second_after_waits(
    hold: HoldWorld,
) -> None:
    """Two batches either side of week 4's opening, by one second; weeks 4 and then 5 read.

    An hour after week 4 opened, week 4's page carries the early batch and none
    of the late one. An hour after week 5 opened, week 5's page carries both, and
    week 4's page, no longer the latest, carries none.

    **The mutations this kills:** the as-of instant taken from the reading clock
    rather than the report's opening (the late batch shows on week 4's page);
    `<=` written for "before" one second out (decision 2: strictly before); the
    instant taken from the previous week's opening (the early batch disappears);
    and the late batch filtered out for good rather than until the next opening.
    **The near misses:** the early batch on week 4, and both on week 5.
    """
    world = hold
    opening = report_opens(LATEST)
    a_batch(
        world,
        cut_at=opening - ONE_SECOND,
        answer_ids=[answer_id_of(world, text) for text in WEEK_THREE],
    )
    a_batch(
        world,
        cut_at=opening + ONE_SECOND,
        answer_ids=[answer_id_of(world, text) for text in WEEK_FOUR],
    )
    student = world.a_student("either-side", world.taught)

    world.stand_after_the_opening(LATEST)
    on_week_four, _ = read(world, student, LATEST)
    world.stand_after_the_opening(NEXT)
    on_week_five, _ = read(world, student, NEXT)
    week_four_later, _ = read(world, student, LATEST)

    assert sorted(released_texts(on_week_four)) == sorted(WEEK_THREE), (
        f"Week 4's page carries {released_texts(on_week_four)}. The batch cut one second before "
        f"week 4's report opened ({sorted(WEEK_THREE)}) shows; the one cut one second after "
        f"({sorted(WEEK_FOUR)}) does not, until the next week's page."
    )
    assert sorted(released_texts(on_week_five)) == sorted((*WEEK_THREE, *WEEK_FOUR)), (
        f"Week 5's page carries {released_texts(on_week_five)}; both batches were cut before week "
        "5's report opened."
    )
    assert week_four_later[RELEASED] is None, (
        f"Once week 5 is published, week 4's page carries {week_four_later[RELEASED]!r}. Ruling 1: "
        "the latest published week's page only."
    )


def test_a_comment_in_a_batch_is_never_shown_under_its_own_week(hold: HoldWorld) -> None:
    """A sixth week-1 instructor comment, released in a batch: on week 4's page, never on week 1's.

    Week 1 keeps its five canonical commenters outside the batch, so its
    instructor stream stays at the threshold and shown — the instructor's report
    says so, and shows the sixth comment in its released list rather than under
    week 1. The student's week-1 page carries the five and not the sixth; week
    4's page carries the sixth in the group.

    **The mutation this kills:** the student's week read filtering the view by
    section, week, stream and status but not by batch membership — the instructor
    read's own rule, dropped in the filter (SPEC §4: "a comment released in a
    batch is never shown again under its own week"). **The near misses:** the five
    week-1 comments, which must stay, and the sixth in the group.
    """
    world = hold
    released = plant_comment(
        world, course_week=1, stream=INSTRUCTOR_STREAM, text=RELEASED_FROM_A_SHOWN_WEEK
    )
    a_batch(world, cut_at=report_opens(LATEST) - CUT_BEFORE_OPENING, answer_ids=[released])
    student = world.a_student("own-week", world.taught)
    world.stand_after_the_opening(LATEST)

    week_one_report = instructor_report(world, 1)
    assert instructor_suppressed(week_one_report, INSTRUCTOR_STREAM) is False, (
        "The instructor's report holds course week 1's instructor stream, so a missing comment "
        "there would be explained by the threshold. A broken world, not a red."
    )
    assert RELEASED_FROM_A_SHOWN_WEEK not in instructor_statuses(week_one_report, INSTRUCTOR_STREAM)
    assert RELEASED_FROM_A_SHOWN_WEEK in instructor_released_statuses(
        instructor_report(world, LATEST)
    ), "The instructor's latest report does not release the planted comment. A broken world."

    week_one, week_one_answer = read(world, student, 1)
    latest, _ = read(world, student, LATEST)

    shown = comment_texts(streams_of(week_one, "Course week 1")[INSTRUCTOR_NAME])
    assert sorted(shown) == sorted(FULL_WEEK_COMMENTS), (
        f"Course week 1's instructor stream carries {shown}; the five canonical comments, and not "
        "the one released in a batch."
    )
    assert (
        RELEASED_FROM_A_SHOWN_WEEK not in week_one_answer.text
    ), "A comment released in a batch is shown under its own week. SPEC §4: never again."
    assert RELEASED_FROM_A_SHOWN_WEEK in released_texts(
        latest
    ), f"Week 4's group carries {released_texts(latest)}, not the released comment."
