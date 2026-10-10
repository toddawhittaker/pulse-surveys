"""A comment of nothing but whitespace never reaches the summary model — E5.1-12 and E6-01.

Dispute E5.1-12-01's ruling sent the blank-text fix to two places: the
`report_comment` view, which decides SPEC §4's threshold, and the summary job's
own gather in `app.services.reporting`. **E6-01 makes them one place**: the gather
reads the view, and its own copy of the blank-comment class is deleted (E6-01
criterion 9). `tests/integration/test_a_whitespace_only_comment_is_not_a_commenter.py`
covers the view. This module covers the gather, through the job, the way every
other summary-job test reaches it — and its second test is the one only a single
blank class can pass: a whitespace-only answer the view does not show holds no
verdict, and its week is summarized anyway, because the wait (E6-01 criterion 8)
counts the comments the view would show.

**Why it matters.** A comment that is only whitespace is not something a student
said. Sent to the model, it is one more numbered "comment" in the week, and every
theme count the model writes is then counted over a week with one comment more
than anybody wrote.

**The whitespace answer is planted straight into `answer`**, past the write
path's `str.strip()`, because the write path would otherwise drop it before the
gather could be asked about it. It is made only of spaces outside ASCII
(U+1680, U+2003, U+2028, U+2029, U+205F, U+3000), none of which PostgreSQL's
one-argument `btrim` removes.
"""

from typing import Any

import pytest
from fixtures.moderation import UNMODERATED
from fixtures.summary_job import (
    A_CLOSED_TERM_WEEK,
    INSTRUCTOR_COMMENT_POSITION,
    INSTRUCTOR_STREAM,
    StreamAwareGateway,
    SummaryWorld,
    comment_text,
)

pytestmark = [pytest.mark.integration]

# The whitespace-only answer. Written as escapes, never as the characters
# themselves (ruff RUF001). Python's `str.strip()` removes all six.
ONLY_UNICODE_SPACES = "\u1680\u2003\u2028\u2029\u205f\u3000"

# Nonces that appear nowhere else in this repository, so finding one in a prompt
# is evidence rather than a coincidence with the prompt template.
PLAIN_NONCE = "Jt6WqRz3Mc"
# The control that carries the whitespace inside real text. If this comment
# reaches the prompt whole, the six characters survive the render path, so their
# absence elsewhere in the prompt means the whitespace-only answer was not sent —
# not that the renderer removed the characters on the way.
CARRIER_NONCE = f"Hn8YsKd4Vb{ONLY_UNICODE_SPACES}Lx2PfTg9Qa"


def test_the_summary_prompt_carries_the_real_comments_and_not_the_whitespace_only_answer(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """Two real instructor comments and one whitespace-only answer: the prompt carries the two.

    One closed section-week, three students. Two wrote a real instructor-stream
    comment; the third's answer is six non-ASCII spaces, written straight to the
    database. The job runs with a gateway double that records every prompt.

    **The controls, asserted first.** A prompt was sent at all, and both real
    comments are in it. One of the real comments carries the same six spaces
    between two words, so its arrival whole in the prompt proves the characters
    survive the gather and the renderer. The renderer writes each comment
    verbatim (`tests/unit/test_the_weekly_summary_prompt_render.py`).

    **The assertion.** The six-space run appears in the prompt exactly once,
    inside the real comment that carries it. A second occurrence is the
    whitespace-only answer, sent to the model as a comment.

    **What this cannot see.** If the renderer stripped each comment before
    writing it, a gathered whitespace answer would render as an empty block and
    this count would not change. The render test above pins verbatim rendering,
    and the mutation below must be confirmed red against this tree for that
    reason.

    **The mutation it kills:** the gather's filter reverts to the one-argument
    `btrim`, which removes only the ASCII space and so keeps all six characters.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    assert ONLY_UNICODE_SPACES.strip() == "", (
        "The planted answer must be blank to the write path's `str.strip()`, or this test plants "
        "a comment the write path would have kept."
    )

    summary_world.build(summary_job_contract.a_cohort)
    plain = comment_text(INSTRUCTOR_STREAM, PLAIN_NONCE)
    carrier = comment_text(INSTRUCTOR_STREAM, CARRIER_NONCE)
    summary_world.respond(
        "plain-subject",
        cohort=summary_job_contract.a_cohort,
        term_week=A_CLOSED_TERM_WEEK,
        instructor_comment=plain,
    )
    summary_world.respond(
        "carrier-subject",
        cohort=summary_job_contract.a_cohort,
        term_week=A_CLOSED_TERM_WEEK,
        instructor_comment=carrier,
    )
    blank_written = summary_world.respond(
        "blank-subject",
        cohort=summary_job_contract.a_cohort,
        term_week=A_CLOSED_TERM_WEEK,
        instructor_comment=ONLY_UNICODE_SPACES,
    )
    assert INSTRUCTOR_COMMENT_POSITION in blank_written, (
        "The whitespace-only answer was not written to `answer`, so the gather has nothing to "
        "drop and this test would pass on an absent row."
    )
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()

    gateway = StreamAwareGateway(summary_contracts)
    summary_job_contract.run(gateway=gateway)

    assert gateway.prompts, (
        "The walk made no model call for a closed week carrying two real instructor comments, so "
        "there is no prompt to ask what fed it, and the absence below would be an absence in "
        "nothing."
    )
    sent = "\n".join(gateway.prompts)

    assert plain in sent and carrier in sent, (
        f"The prompt does not carry both real comments whole (plain: {plain in sent}, carrying "
        f"the six spaces inside real text: {carrier in sent}). Until both arrive, the count "
        "below cannot tell a dropped whitespace answer from a renderer that altered the "
        "characters."
    )

    occurrences = sent.count(ONLY_UNICODE_SPACES)
    assert occurrences == 1, (
        f"The six-space run appears {occurrences} times in what was sent to the model; once is "
        "the real comment that carries it. A second is a student's whitespace-only answer sent "
        "to the model as a comment, which Python's `str.strip()` treats as blank and the write "
        "path would never have stored."
    )


def test_an_unverdicted_whitespace_only_answer_does_not_hold_its_week_back(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """E6-01 criteria 8 and 9 together: the wait counts what the view shows, and nothing else.

    The same week as the test above, with one difference: the whitespace-only
    answer holds **no moderation verdict**. The two real comments hold `clear`.

    E6-01's work order (decision 5): a section-week is moderated when every comment
    of it that the view would otherwise show — non-blank — holds a verdict. The
    view does not show a whitespace-only answer, so this week is moderated and the
    walk summarizes it, carrying the two real comments.

    **Why this is the test of criterion 9 rather than a variation of the one
    above.** The test above passes against a gather with its own blank copy, as
    long as the copy is right. This one does not, if the wait and the gather
    disagree about what a comment is: a wait that counted raw comment answers would
    find one with no verdict and hold the week back for ever — no moderator will
    ever classify six spaces — and the instructor's thin week would never get the
    summary §5.1 promises it.

    **The mutations this kills:** the wait written over `answer` rather than over
    the view (the week is never summarized), and a gather that reads `answer`
    directly with a blank copy that drifted from the view's.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    summary_world.build(summary_job_contract.a_cohort)
    plain = comment_text(INSTRUCTOR_STREAM, PLAIN_NONCE)
    carrier = comment_text(INSTRUCTOR_STREAM, CARRIER_NONCE)
    for subject, body in (("plain-subject", plain), ("carrier-subject", carrier)):
        summary_world.respond(
            subject,
            cohort=summary_job_contract.a_cohort,
            term_week=A_CLOSED_TERM_WEEK,
            instructor_comment=body,
        )
    blank_written = summary_world.respond(
        "blank-subject",
        cohort=summary_job_contract.a_cohort,
        term_week=A_CLOSED_TERM_WEEK,
        instructor_comment=ONLY_UNICODE_SPACES,
        instructor_moderation=UNMODERATED,
    )
    assert INSTRUCTOR_COMMENT_POSITION in blank_written, (
        "The whitespace-only answer was not written to `answer`, so there is nothing for the wait "
        "to count wrongly and this test would pass on an absent row."
    )
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()

    gateway = StreamAwareGateway(summary_contracts)
    summary_job_contract.run(gateway=gateway)

    stored = summary_world.summaries(
        section_id=summary_world.section_id(summary_job_contract.a_cohort)
    )
    assert stored, (
        "The walk wrote no summary for a closed week whose two real comments hold verdicts. The "
        "third answer is six spaces with no verdict; the view does not show it, so it is not a "
        "comment the week waits for. A wait counting raw answers holds this week back for ever."
    )
    sent = "\n".join(gateway.prompts)
    assert plain in sent and carrier in sent, (
        f"The week was summarized and its two real comments are not both in the call (plain: "
        f"{plain in sent}, carrier: {carrier in sent})."
    )
    assert (
        sent.count(ONLY_UNICODE_SPACES) == 1
    ), "The six-space run reached the model outside the real comment that carries it."
