"""A comment of nothing but whitespace does not count toward the threshold — E5.1-12, Part B item 5.

SPEC §4 counts the n-threshold in distinct students *commenting* in one stream in
one week, and §4.1 item 3 hides a stream's raw comments below it. A student whose
answer is spaces and line breaks has said nothing, and counting them as a
commenter lets four real authors be shown as if they were five — the reader then
knows the four visible comments are the whole stream, which is the narrowing the
threshold exists to prevent (`docs/MISTAKES.md` entry 50: a threshold crossed by
a count of something else).

**The whitespace answer is planted straight into `answer`**, past the write path's
strip, because the write path is the layer that would otherwise make it
unreachable: a guard is a guard only once something has been thrown at it
(`tests/fixtures/report_comments.py::CommentWorld.comment_text_under_another_kind`
gives the same argument for the view's kind predicate). It is classified like a
real comment, so the only thing that distinguishes it from the four beside it is
its text, and a green names the count's treatment of blank text rather than a
missing classification.

**Marked `invariant`**: §4.1 item 3, in the isolated pass where a skip fails CI.
"""

from typing import Any

import pytest
from fixtures.report_comments import CommentWorld

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# Two term weeks inside cohort `F`'s run (term weeks 7 to 12), both closed in 2020
# by `CommentWorld.close_week`, so neither turns on the date CI runs.
THIN_WEEK = 7
CONTROL_WEEK = 8

# Spaces, a tab and line breaks: what a textarea holds when somebody presses keys
# and writes nothing. Not empty — an empty string is a different row, and E2-05
# stores a blank optional comment as no row at all.
ONLY_WHITESPACE = "   \t\n  \n "

A_LABEL = "the lab instructions changed between the handout and the session"


def plant(world: CommentWorld, *, term_week: int, real: int, blank: int, stream: str) -> None:
    """`real` students with a real comment and `blank` with whitespace only, in one stream."""
    world.close_week(term_week)
    for index in range(real):
        world.submit(
            term_week=term_week, comments={stream: f"{A_LABEL} (week {term_week}, {index + 1})"}
        )
    for _ in range(blank):
        world.submit(term_week=term_week, comments={stream: ONLY_WHITESPACE})


def test_four_real_commenters_and_one_whitespace_answer_leave_the_stream_suppressed(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """Threshold minus one real commenters plus one whitespace-only answer: suppressed, nothing shown.

    At SPEC §4's default of five, four students wrote something about the
    instructor and a fifth submitted only whitespace. The stream holds four
    commenters, below five, so `stream_is_suppressed` answers true and
    `visible_comments` returns nothing.

    **The control, in the same world:** a second week with the threshold's number
    of real commenters is shown — `visible_comments` returns all of them and
    `stream_is_suppressed` answers false. So an empty answer for the thin week is
    the threshold holding, not a read that answers nothing. And the raw count of
    non-null comment answers in the thin week is read back and required to *reach*
    the threshold, so the whitespace answer is certainly the one that decides it.

    **The mutation that must turn this red:** the blank-text exclusion removed from
    the distinct-commenter count — in `backend/app/services/report_comments.py`'s
    `_commenters_by_stream_week` (ADR 0182), or in the `report_comment` view it
    reads, whichever of the two holds a `btrim(comment_text) <> ''`-shaped
    predicate at HEAD. The count then reaches five, the stream is shown, and its
    four real comments (and the blank one) come back. **The near miss that stays
    green:** the same predicate written as `comment_text ~ '\\S'`, which excludes
    the same row.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 2, f"The configured n-threshold is {threshold}; nothing is below it."
    stream = contract.instructor_stream
    world.build()
    plant(world, term_week=THIN_WEEK, real=threshold - 1, blank=1, stream=stream)
    plant(world, term_week=CONTROL_WEEK, real=threshold, blank=0, stream=stream)

    raw_thin = world.commenters_in(term_week=THIN_WEEK, stream=stream)
    raw_control = world.commenters_in(term_week=CONTROL_WEEK, stream=stream)
    assert (raw_thin, raw_control) == (threshold, threshold), (
        f"The thin week holds {raw_thin} students with a non-null comment and the control week "
        f"{raw_control}; this test planted {threshold} in each ({threshold - 1} real plus one "
        f"whitespace-only, and {threshold} real). Counted without regard to the text, the thin week "
        "reaches the threshold — that is what makes the whitespace answer the deciding one."
    )

    def ask(term_week: int) -> tuple[Any, Any]:
        arguments = {
            "section_id": world.section_id(),
            "week_id": world.week_id(term_week),
            "stream": stream,
        }
        return (
            contract.is_suppressed()(world.session, **arguments),
            tuple(contract.visible()(world.session, **arguments)),
        )

    control_suppressed, control_shown = ask(CONTROL_WEEK)
    assert control_suppressed is False and len(control_shown) == threshold, (
        f"The control week, with {threshold} real commenters, answered suppressed="
        f"{control_suppressed!r} and {len(control_shown)} comments. It is at the threshold and "
        "SPEC §4 shows it; until it is shown, the thin week's emptiness below is what this read "
        "gives every week."
    )

    thin_suppressed, thin_shown = ask(THIN_WEEK)
    assert thin_suppressed is True, (
        f"`{contract.suppressed_name}` answered {thin_suppressed!r} for a week with "
        f"{threshold - 1} real commenters and one whitespace-only answer. A student who wrote "
        "nothing is not a commenter; counting them crosses SPEC §4's threshold with four authors."
    )
    assert thin_shown == (), (
        f"The thin week's stream showed {[comment.text for comment in thin_shown]!r}. "
        f"{threshold - 1} real authors are below the threshold of {threshold}, and the reader of "
        "these comments would know they are the stream's whole content."
    )
