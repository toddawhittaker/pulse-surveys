"""The student's comment reads use `report_comment` and never `answer` — E8-01, done-when 4.

> The read goes through v004, and no student read queries `answer` itself.

`report_comment` v004 is the view that shows a comment only once it holds a
moderation verdict and never a Care-class one (ADR 0187); `answer` is the table
it is built over, which holds every comment ever written, flagged, excluded and
Care-class alike. A student read that touched `answer` beside the view would be a
second statement of what a student may see, and the one that does not know about
verdicts.

**Watched on the wire**, with `tests/fixtures/statements.py`'s recorder (every
statement any engine sends while the block runs), around a direct call of each
read on `pulse_app`'s connection. Each read is required, in the same call, to
return the comments the world holds and to send a statement naming the view, so
"no statement named `answer`" is said of a read that read something (entry 3).

**The matcher is run both ways before it is believed**: a `FROM answer` and a
`JOIN public.answer` are caught, and `answer_id`, `report_comment` and prose
naming the table are spared.

**Which failure a red is, before E8-01 lands:** `student_week.student_read` fails
naming `student_comments` or `student_released_comments`.
"""

import re

import pytest
from fixtures.report_api import FULL_WEEK_COMMENTS, HELD_COMMENTS
from fixtures.report_views import INSTRUCTOR_STREAM
from fixtures.statements import Statement, statements_recorded
from fixtures.student_week import (
    ONE_SECOND,
    STUDENT_COMMENTS,
    STUDENT_RELEASED_COMMENTS,
    a_batch,
    answer_id_of,
    call_student_read,
    text_of,
)
from fixtures.the_hold import HoldWorld, report_opens

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

LATEST = 4

# The table, referenced as a relation: after `FROM` or `JOIN`, optionally
# schema-qualified and quoted, and not followed by another identifier character —
# so `answer_id` and `answer_view` are not it.
READS_THE_ANSWER_TABLE = re.compile(
    r'\b(?:FROM|JOIN)\s+(?:"?public"?\s*\.\s*)?"?answer"?(?![\w"])', re.IGNORECASE
)
READS_THE_COMMENT_VIEW = re.compile(
    r'\b(?:FROM|JOIN)\s+(?:"?public"?\s*\.\s*)?"?report_comment"?(?![\w"])', re.IGNORECASE
)

MUST_CATCH = (
    "SELECT answer.comment_text FROM answer WHERE answer.id = %(id)s",
    'SELECT a.id FROM public.report_comment AS c JOIN public."answer" AS a ON a.id = c.answer_id',
    "SELECT 1 FROM\n    answer AS a",
)
MUST_SPARE = (
    "SELECT report_comment.answer_id, report_comment.comment_text FROM report_comment",
    "SELECT m.answer_id FROM release_batch_member AS m JOIN release_batch AS b ON b.id = 1",
    "SELECT 1 FROM answer_view",
)


def answer_reads(recorded: list[Statement]) -> list[str]:
    return [found.sql for found in recorded if READS_THE_ANSWER_TABLE.search(found.sql)]


def view_reads(recorded: list[Statement]) -> list[str]:
    return [found.sql for found in recorded if READS_THE_COMMENT_VIEW.search(found.sql)]


def test_the_matchers_catch_a_read_of_the_table_and_spare_the_view_and_the_column() -> None:
    """The instrument, both directions. **A red here means this module is broken, not the code.**

    **The mutation this kills:** a matcher that searches for the bare word
    `answer`, which every view read carries as `answer_id`, or one that cannot
    see a schema-qualified, quoted relation.
    """
    for sample in MUST_CATCH:
        assert READS_THE_ANSWER_TABLE.search(sample), f"The matcher missed {sample!r}."
    for sample in MUST_SPARE:
        assert not READS_THE_ANSWER_TABLE.search(sample), f"The matcher took {sample!r}."
    assert READS_THE_COMMENT_VIEW.search(MUST_SPARE[0]), "The view matcher missed the view."
    assert not READS_THE_COMMENT_VIEW.search(MUST_CATCH[0]), "The view matcher took `answer`."


def test_the_students_week_read_returns_the_weeks_comments_through_the_view_alone(
    hold: HoldWorld,
) -> None:
    """`student_comments` for course week 1's instructor stream, on the wire.

    It returns the five comments, at least one statement it sent names
    `report_comment`, and none names `answer`.

    **The mutations this kills:** the read written against `answer` joined to
    `response` and `moderation_state` (a second copy of v004's rule that misses
    the Care exclusion), or the view read and then `answer` read again "for the
    text". **The near miss:** the view read, which must be there.
    """
    world = hold
    with statements_recorded() as recorded:
        returned = call_student_read(
            world,
            STUDENT_COMMENTS,
            section_id=world.taught,
            week_id=world.week_id(1),
            stream=INSTRUCTOR_STREAM,
        )

    assert sorted(text_of(item) for item in returned) == sorted(FULL_WEEK_COMMENTS), (
        f"`{STUDENT_COMMENTS}` returned {[text_of(item) for item in returned]} for a shown stream "
        "holding the five canonical comments."
    )
    assert view_reads(recorded), (
        f"`{STUDENT_COMMENTS}` sent {len(recorded)} statements and none names `report_comment`. "
        "Done-when 4: the read goes through v004."
    )
    assert (
        answer_reads(recorded) == []
    ), f"`{STUDENT_COMMENTS}` read `answer` itself: {answer_reads(recorded)}. Done-when 4."


def test_the_students_released_read_returns_batches_cut_before_the_instant_through_the_view_alone(
    hold: HoldWorld,
) -> None:
    """`student_released_comments` as of week 4's opening, with a batch either side of it.

    It returns the batch cut one second before and not the one cut one second
    after, at least one statement names `report_comment`, and none names
    `answer`.

    **The mutations this kills:** `as_of` accepted and ignored (the late batch
    returned); the instant compared one batch too far (the early batch dropped);
    and the release walked through `answer` rather than through the view. **The
    near miss:** the early batch, which must be returned. Decision 2's exact edge
    — a cut at the opening itself — is not asserted: one second either side is
    the ticket's test, and the route-level module drives it too.
    """
    world = hold
    opening = report_opens(LATEST)
    early = list(HELD_COMMENTS[3])
    late = list(HELD_COMMENTS[4])
    a_batch(world, cut_at=opening - ONE_SECOND, answer_ids=[answer_id_of(world, t) for t in early])
    a_batch(world, cut_at=opening + ONE_SECOND, answer_ids=[answer_id_of(world, t) for t in late])

    with statements_recorded() as recorded:
        returned = call_student_read(
            world,
            STUDENT_RELEASED_COMMENTS,
            section_id=world.taught,
            term_id=world.term_id(),
            stream=INSTRUCTOR_STREAM,
            as_of=opening,
        )

    texts = sorted(text_of(item) for item in returned)
    assert texts == sorted(early), (
        f"`{STUDENT_RELEASED_COMMENTS}` as of {opening.isoformat()} returned {texts}. Decision 2: "
        f"the batch cut a second before that instant ({sorted(early)}), and not the one cut a "
        f"second after it ({sorted(late)})."
    )
    assert view_reads(recorded), (
        f"`{STUDENT_RELEASED_COMMENTS}` sent {len(recorded)} statements and none names "
        "`report_comment`. Done-when 4: the read goes through v004."
    )
    assert (
        answer_reads(recorded) == []
    ), f"`{STUDENT_RELEASED_COMMENTS}` read `answer` itself: {answer_reads(recorded)}."
