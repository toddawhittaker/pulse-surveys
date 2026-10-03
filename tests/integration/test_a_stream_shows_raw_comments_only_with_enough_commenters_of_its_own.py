"""One stream hides while the other shows — ticket E5.1-01, criterion 1.

The owner's ruling 1: raw comments for a stream in a section-week are shown only
when at least the configured threshold of **distinct students commented in that
stream that week**. Below that, the stream's comments are held for release
batches.

The defect this ticket closes is a count of the wrong thing. The comment gate
compared the week's *response* count with the threshold, so a week of six
respondents in which one student wrote about the instructor showed that one
comment — and the gradebook's per-week completion ledger (ADR 0125) can name who
completed that week's instructor comment item. A threshold that protects people
has to be crossed by a count of the people it protects (`docs/MISTAKES.md`
entry 50).

**The world is the ticket's own, sized from the configured threshold.** At SPEC
§4's default of five it is exactly the ticket's sentence: six respondents, one of
whom commented about the instructor and five others about the course. Every count
is read back from the database before anything is asserted about it.

**Marked `invariant`**: §4.1 item 3 — below the n-threshold, raw comments are
hidden from instructors and students alike — and the isolated pass is where a skip
cannot hide it.

**Which failure a red is, before E5.1-01 lands.** The two-stream test fails on an
assertion: the instructor stream answers its one comment. The
`stream_is_suppressed` test fails naming the missing function, through
`comment_contract.is_suppressed()`, inside the test body (`docs/MISTAKES.md`
entry 44).
"""

from typing import Any

import pytest
from fixtures.report_comments import CommentWorld

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# A term week inside cohort `F`'s run (term weeks 7 to 12).
THE_WEEK = 7

A_LABEL = "the problem sets were longer than the time the syllabus gave them"


def plant_the_tickets_week(world: CommentWorld, contract: Any) -> dict[str, list[Any]]:
    """One section-week: one instructor-stream commenter, a threshold of course-stream ones.

    Two disjoint groups of new respondents, so the week's response count is one
    more than the threshold while the instructor stream holds one commenter. All
    three numbers are read back and required to be what this world claims, in the
    test body that calls this (`docs/MISTAKES.md` entry 44: no guard in a fixture).
    """
    threshold = contract.threshold()
    world.build()
    world.close_week(THE_WEEK)
    planted = world.week_by_stream(
        term_week=THE_WEEK, instructor_only=1, course_only=threshold, label=A_LABEL
    )

    responses = world.responses_in(term_week=THE_WEEK)
    instructor = world.commenters_in(term_week=THE_WEEK, stream=contract.instructor_stream)
    course = world.commenters_in(term_week=THE_WEEK, stream=contract.course_stream)
    assert (responses, instructor, course) == (threshold + 1, 1, threshold), (
        f"The week holds {responses} responses, {instructor} instructor-stream commenters and "
        f"{course} course-stream commenters; this test planted {threshold + 1}, 1 and {threshold}. "
        "A world that is not the size it claims makes every assertion below true or false for a "
        "reason nobody chose — E4-04's first known trap, read in E5.1-01's unit."
    )
    return planted


def read(world: CommentWorld, contract: Any, stream: str) -> Any:
    """The comment read for this world's one week, in one stream."""
    return contract.visible()(
        world.session,
        section_id=world.section_id(),
        week_id=world.week_id(THE_WEEK),
        stream=stream,
    )


def test_a_lone_instructor_commenter_is_hidden_while_the_course_streams_five_are_shown(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """Criterion 1, both streams of one week asserted in one test.

    Six respondents at the default threshold: one wrote about the instructor and
    five others about the course. The instructor stream returns no raw comment;
    the course stream returns its five.

    **Both halves are here because either alone is passed by the wrong build.** A
    read that hides everything satisfies the instructor half; a read that shows
    everything satisfies the course half. The course half is asserted first, so an
    empty instructor answer cannot be a read that answers nothing
    (`docs/MISTAKES.md` entry 3).

    **The mutation it kills:** the gate comparing the week's response count with
    the threshold — six responses reach five, so the lone instructor comment is
    shown. **Near misses it also kills:** a count of distinct commenters across
    the whole week (six people commented somewhere), a count of comment answers
    across the week (six), and a stream count whose stream filter was dropped
    (six). Each is at or above the threshold here and shows the one comment.
    **The near miss it must survive:** the course stream, at exactly the
    threshold of commenters, must still be shown — a gate written with `<=` where
    `<` was meant hides it.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 2, (
        f"The configured n-threshold is {threshold}; a single commenter is not below it, so this "
        "world cannot pose criterion 1."
    )
    plant_the_tickets_week(world, contract)

    course = read(world, contract, contract.course_stream)
    assert len(course) == threshold, (
        f"The course stream answered {len(course)} comments: "
        f"{sorted(comment.text for comment in course)}. {threshold} distinct students commented in "
        "it this week, which is the threshold, so SPEC §4 shows them all. Until this half answers, "
        "the instructor stream's emptiness below is what this read gives every stream."
    )

    instructor = read(world, contract, contract.instructor_stream)
    assert tuple(instructor) == (), (
        f"The instructor stream answered {[comment.text for comment in instructor]}. One student "
        f"commented in it this week, and the week holds {threshold + 1} responses.\n\n"
        "The owner's ruling 1: raw comments for a stream are shown only when at least "
        f"{threshold} distinct students commented in that stream that week. A gate counting the "
        "week's responses shows this one comment, and the gradebook's per-week completion ledger "
        "(ADR 0125) narrows its author to whoever completed this week's instructor comment item — "
        "here, one person."
    )


def test_stream_is_suppressed_answers_per_stream_for_the_same_week(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The one public definition (work order D1), asked about both streams of the same week.

    The same world: the instructor stream, with one commenter, is suppressed; the
    course stream, with exactly the threshold of commenters, is not. Both answers
    are asserted, so a function that answers one value for everything is red.

    **The mutation it kills:** `stream_is_suppressed` keyed on the week rather than
    on the stream — the response count, or the week's commenters across both
    streams — which answers the same value for both streams here. **The near miss
    it must survive:** the boundary — the course stream sits exactly on the
    threshold, so `<=` where `<` was meant answers it suppressed.
    """
    contract = comment_contract
    world = comment_world
    assert contract.threshold() >= 2, "The configured n-threshold leaves nothing below it."
    plant_the_tickets_week(world, contract)

    is_suppressed = contract.is_suppressed()

    def answer(stream: str) -> Any:
        return is_suppressed(
            world.session,
            section_id=world.section_id(),
            week_id=world.week_id(THE_WEEK),
            stream=stream,
        )

    course = answer(contract.course_stream)
    instructor = answer(contract.instructor_stream)
    assert (instructor, course) == (True, False), (
        f"`{contract.suppressed_name}` answered {instructor!r} for the instructor stream (one "
        f"commenter) and {course!r} for the course stream (exactly the threshold of commenters). "
        "The work order's D1: true when fewer than the threshold of distinct students commented in "
        "that stream that week, so the answer is (True, False). Two equal answers are a definition "
        "keyed on the week rather than on the stream."
    )
