"""A week waiting on a verdict is reported held, not empty — E6-09, done-when 4.

> In `_payload`, a stream is suppressed when `stream_is_suppressed` says so or the
> section-week is not yet moderated. Test: a week above the threshold with one
> unverdicted comment serves `suppressed` true and no comments.

SPEC §5.2: "a section-week's comments appear together once every comment in it
holds one, so no report shows part of a week". The comment read already returns
nothing for such a week (E6-01). What the payload said about it was the problem: a
stream above the threshold reported `suppressed: false` beside an empty list, which
the page renders as "no comments this week" — a false statement, made to the
instructor while the comments are only waiting on moderation.

**Driven over a sequence of reads** (`docs/MISTAKES.md` entry 51): course week 1 is
read before the waiting comment exists — shown, five comments, not suppressed, the
control — and again after, through the same route. The only thing between the two
reads is one comment with no verdict.

**Which failure a red is, before E6-09 lands.** The second read's `suppressed` is
`false`: the assertion naming it fails.
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import DecisionDoor
from fixtures.report_api import (
    COMMENT_TEXT_FIELD,
    COMMENTS_FIELD,
    FULL_WEEK,
    FULL_WEEK_COMMENTS,
    PAYLOAD_STREAM_KEY,
    SMALL_N_MEMBER,
    STREAMS_MEMBER,
    SUPPRESSED_FIELD,
    strings_in,
)
from fixtures.report_views import INSTRUCTOR_STREAM

pytestmark = pytest.mark.integration

WAITING_TEXT = "E6-09 a comment of course week 1 the moderation sweep has not reached yet"


def the_instructor_stream(body: Any) -> dict[str, Any]:
    return body[STREAMS_MEMBER][PAYLOAD_STREAM_KEY[INSTRUCTOR_STREAM]]


def test_a_week_above_the_threshold_with_one_unverdicted_comment_is_served_suppressed(
    decision_door: DecisionDoor,
) -> None:
    """Read, add one comment with no verdict, read again: `suppressed` true and no comments.

    **The mutation this kills:** `_payload` taking the stream's flag from
    `stream_is_suppressed` alone, which counts commenters and says nothing about
    moderation — the second read then says `suppressed: false` beside an empty
    list, "no comments" for a week holding six. **The near miss:** a flag computed
    from the week's whole state that also hides the first read (the control is
    that read, not suppressed and showing its five comments).
    """
    door = decision_door
    before = the_instructor_stream(door.payload(FULL_WEEK))
    shown = {card[COMMENT_TEXT_FIELD] for card in before[COMMENTS_FIELD]}
    assert before[SMALL_N_MEMBER][SUPPRESSED_FIELD] is False and shown == set(FULL_WEEK_COMMENTS), (
        f"The control: before any comment is waiting, course week 1's instructor stream is "
        f"{before[SMALL_N_MEMBER]!r} and shows {sorted(shown)}; it holds five moderated comments "
        "from five students and is shown in full."
    )

    door.plant_a_comment(
        course_week=FULL_WEEK, stream=INSTRUCTOR_STREAM, text=WAITING_TEXT, verdict=None
    )
    body = door.payload(FULL_WEEK)
    after = the_instructor_stream(body)
    assert after[COMMENTS_FIELD] == [], (
        f"Course week 1 holds a comment with no verdict and its instructor stream shows "
        f"{[card.get(COMMENT_TEXT_FIELD) for card in after[COMMENTS_FIELD]]}. SPEC §5.2: a "
        "section-week's comments appear together once every comment holds a verdict."
    )
    assert after[SMALL_N_MEMBER][SUPPRESSED_FIELD] is True, (
        f"Course week 1's instructor stream is served `small_n` {after[SMALL_N_MEMBER]!r} beside "
        "no comments while one of its six comments waits on moderation. `suppressed: false` with "
        "an empty list tells the instructor the week had no comments, which is false. E6-09 "
        "done-when 4: the stream is suppressed until the section-week is moderated."
    )
    assert not [value for value in strings_in(body) if WAITING_TEXT[:40] in value], (
        "The waiting comment's text is in the served report."
    )
