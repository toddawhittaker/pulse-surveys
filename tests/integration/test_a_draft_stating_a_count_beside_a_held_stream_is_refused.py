"""A draft that states a count of commenters in a week with a held stream is refused — residue A.

E7-04's work order, residue A from the breakdown review (PR #306): "for a held
stream, a draft that states a number of comments or students (digits or number
words next to comment/student/response/classmate/of you) is refused as an invalid
answer, tested with a planted summary whose prose carries a count; its twin, a
shown stream's draft stating a count, is accepted."

**Why it exists.** Decision 12 keeps a held stream's per-theme counts out of the
prompt. A summary's *prose* is not a count field, and a `summary.v3` paragraph may
well say "two students raised the dataset" — so the prose path can hand the model
the number the theme path withholds, and a draft can repeat it to every student.
SPEC §5.2: in a small week "a per-week count ... would say how many of the few who
responded" did something.

**The two worlds differ in one thing.** Both plant a course-stream summary whose
prose states a count. In the first the course stream holds one commenter and is
held; in the second it holds the configured threshold of commenters and is shown.
Which is which is read off the instructor's report (work-order decision 4), never
assumed.

**What the drafts lift.** Nothing: every draft here shares fewer than twenty
normalized characters with every comment in the week (asserted), so a refusal is
the count rule's and not the reuse guard's.

**Marked `invariant`**: the number of commenters in a held stream reaching every
student is §4.1 item 3's threshold crossed by arithmetic rather than by text.
"""

from typing import Any

import pytest
from fixtures.report_comments import configured_threshold
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.response_draft import (
    HELD_COMMENT,
    ORDINARY_SUMMARY_VERSION,
    SHOWN_SUMMARY_RESPONSES,
    SHOWN_SUMMARY_TEXT,
    SHOWN_THEME_A,
    SHOWN_THEME_A_COUNT,
    SMALL_N_SUMMARY_VERSION,
    THE_GUARD_BOUND,
    DraftDoor,
    assert_the_planted_texts_are_what_this_file_says,
    assert_unusable,
    draft_answer,
    longest_shared_run,
    text_of,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The course stream's summary, whose prose carries a count — the residue's
# "planted summary whose prose carries a count".
A_SUMMARY_STATING_A_COUNT = (
    "E7-04 course-stream summary: two students said the dataset question went unanswered."
)
A_COURSE_THEME = "E7-04 the dataset question"
A_COURSE_THEME_COUNT = 2

# The drafts. The counting pair spells the count both ways the residue names.
COUNTING_IN_WORDS = (
    "Thank you for writing. Three of you asked for slower derivations, so I will post "
    "worked steps after each class."
)
COUNTING_IN_DIGITS = (
    "Thank you for writing. 3 students asked for slower derivations, so I will post "
    "worked steps after each class."
)
COUNTING_DRAFTS = (COUNTING_IN_WORDS, COUNTING_IN_DIGITS)

# The near misses in the held week: no count at all, and a number that counts
# worked examples rather than people — the residue's rule is a number "next to
# comment/student/response/classmate/of you", and a guard refusing any digit would
# refuse a response promising "3 worked examples".
COUNTING_NOBODY = (
    "Thank you for writing. You asked for slower derivations, so I will post worked steps "
    "after each class."
)
A_NUMBER_OF_THINGS = (
    "Thank you for writing. You asked for slower derivations, so I will post 3 worked "
    "examples after each class."
)


def a_week(door: DraftDoor, *, course_commenters: int) -> None:
    """Course week 1 with `course_commenters` course comments and both summaries planted."""
    assert_the_planted_texts_are_what_this_file_says()
    door.plant(HELD_COMMENT, stream=COURSE_STREAM)
    for index in range(1, course_commenters):
        door.plant(
            f"E7-04 course commenter {index}: the lab notes were posted promptly enough",
            stream=COURSE_STREAM,
        )
    held = course_commenters < configured_threshold()
    door.plant_summary(
        INSTRUCTOR_STREAM,
        text=SHOWN_SUMMARY_TEXT,
        themes=((SHOWN_THEME_A, SHOWN_THEME_A_COUNT),),
        prompt_version=ORDINARY_SUMMARY_VERSION,
        response_count=SHOWN_SUMMARY_RESPONSES,
    )
    door.plant_summary(
        COURSE_STREAM,
        text=A_SUMMARY_STATING_A_COUNT,
        themes=((A_COURSE_THEME, A_COURSE_THEME_COUNT),),
        prompt_version=SMALL_N_SUMMARY_VERSION if held else ORDINARY_SUMMARY_VERSION,
        response_count=course_commenters,
    )
    body = door.assert_the_streams_are(instructor_held=False, course_held=held)
    served = door.served_summary(body, COURSE_STREAM)
    assert isinstance(served, dict) and A_SUMMARY_STATING_A_COUNT in str(served), (
        f"The report serves {served!r} as the course stream's summary, not the planted prose "
        "stating a count — so the gather would not carry it, and the residue's premise (a "
        "summary whose prose carries a count) is not this world."
    )


def a_held_week(door: DraftDoor) -> None:
    a_week(door, course_commenters=1)


def a_shown_week(door: DraftDoor) -> None:
    a_week(door, course_commenters=configured_threshold())


def drafted(door: DraftDoor, draft: str) -> Any:
    for comment in door.planted:
        assert longest_shared_run(draft, comment) < THE_GUARD_BOUND, (
            f"The draft {draft!r} shares a long run with the planted comment {comment!r}, so a "
            "refusal could be the reuse guard's rather than the count rule's."
        )
    door.provider.script(draft_answer(draft))
    before = len(door.provider.completions)
    answered = door.draft()
    assert (
        len(door.provider.completions) > before
    ), f"The draft answered {answered.status_code} without asking the model."
    return answered


@pytest.mark.parametrize("draft", COUNTING_DRAFTS, ids=("number-word-of-you", "digit-students"))
def test_a_draft_stating_a_count_in_a_week_with_a_held_stream_is_refused(
    draft_door: DraftDoor, draft: str
) -> None:
    """The held world: a draft telling students how many of them said something. 502.

    **The mutation this kills:** the count rule absent, so the prose path carries
    the held stream's number straight into a published response. One parameter
    per spelling the residue names, so a rule matching digits only, or number
    words only, is red on the other. **The near misses:** the shown twin below,
    and the two non-counting drafts in this same held world.
    """
    door = draft_door
    a_held_week(door)
    assert_unusable(
        drafted(door, draft),
        "draft",
        "states a count of students beside a stream held below the threshold, in a week whose "
        "held summary's prose carries a count",
    )


@pytest.mark.parametrize("draft", COUNTING_DRAFTS, ids=("number-word-of-you", "digit-students"))
def test_a_draft_stating_a_count_in_a_week_with_every_stream_shown_is_accepted(
    draft_door: DraftDoor, draft: str
) -> None:
    """The residue's twin: the same drafts when no stream is held. 200, the draft served.

    **The mutation this kills:** the count rule applied to every week — the
    safe-looking over-reach that forbids "five of you asked for..." in a week of
    thirty, where the comments are on the page anyway.
    """
    door = draft_door
    a_shown_week(door)
    assert text_of(drafted(door, draft)) == draft, "The draft route rewrote the model's draft."


@pytest.mark.parametrize(
    "draft", (COUNTING_NOBODY, A_NUMBER_OF_THINGS), ids=("no-number", "a-number-of-things")
)
def test_a_draft_counting_nobody_in_a_week_with_a_held_stream_is_accepted(
    draft_door: DraftDoor, draft: str
) -> None:
    """The held world's own near misses: no number, and a number of worked examples.

    **The mutations this kills:** a rule that refuses every draft in a week with a
    held stream (the first parameter), and one that refuses any digit at all (the
    second) — the residue scopes the rule to a number next to comment, student,
    response, classmate or "of you".
    """
    door = draft_door
    a_held_week(door)
    assert text_of(drafted(door, draft)) == draft, "The draft route rewrote the model's draft."
