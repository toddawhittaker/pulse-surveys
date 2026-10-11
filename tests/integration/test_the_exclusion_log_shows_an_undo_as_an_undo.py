"""The exclusion log marks an undo as an undo — E6-09, done-when 7.

> `is_undo` is carried through `LoggedDecision`, the log payload and
> `ExclusionLogRow`, which renders an undo as a reversal. Tests for both sequences:
> exclude then undo; exclude an unflagged comment with a reason, keep it, then undo
> the keep.

SPEC §8 records whether a decision "undoes an earlier decision", and §5.2 makes the
log the anti-cherry-picking trail. Without the marker, an undone keep reads in the
log as a second, fresh exclusion — a person who changed their mind looks like a
person who excluded the comment twice — and an undone exclusion is either absent
or indistinguishable from a decision.

**The field is `is_undo`, a boolean on every log row** (this ticket's done-when
names it; the stored column is `moderation_state.is_undo`). Each step is driven
through the instructor's own decision route, so the rows are the ones the door
writes, and the log is read as the Lead Faculty member who leads the course. Rows
are found by their excerpt: each comment is in course week 1's instructor stream,
which is shown, so its row carries the whole text (it is shorter than the excerpt).

**What the first sequence requires, said exactly.** Undoing an exclusion of a
flagged comment writes a row holding the flag again (`FLAGGED_COLLAPSED`, undo
true). This module requires that row to appear in the log marked `is_undo: true`
beside the exclusion it reverses, which is what "the log shows undo as an undo"
asks of that sequence; it does not assert the undo row's `decision` member, which
the ticket does not settle for a state that is neither an exclusion nor a keep.

**Which failure a red is, before E6-09 lands.** Log rows carry no `is_undo`, so the
first assertion on it fails naming the member.
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import (
    EXCLUDE,
    KEEP,
    OK,
    STORED_EXCLUDED,
    STORED_KEPT,
    UNDO,
)
from fixtures.lead_review import LOG_DECISION, LOG_EXCERPT, LOG_IS_UNDO, LeadReviewWorld
from fixtures.moderation import CLEAR, HARMFUL
from fixtures.report_api import FULL_WEEK, TAUGHT_COHORT
from fixtures.report_views import INSTRUCTOR_STREAM

pytestmark = pytest.mark.integration

A_STATED_REASON = "E6-09 off-topic: it is about another course's lab entirely"


def a_comment(review: LeadReviewWorld, text: str, verdict: str) -> Any:
    return review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=text,
        verdict=verdict,
        cohort=TAUGHT_COHORT,
    )


def decided(review: LeadReviewWorld, comment: Any, action: str, reason: Any = None) -> None:
    """One decision through the instructor's own route, required to succeed."""
    answered = review.door.decide(comment, action, reason)
    assert answered.status_code == OK, (
        f"The instructor's `{action}` was answered {answered.status_code}, so the sequence is not "
        f"the one this test is about. Body begins {answered.text[:400]!r}."
    )


def rows_for(review: LeadReviewWorld, text: str) -> list[dict[str, Any]]:
    """The lead's log rows whose excerpt is this comment's text."""
    return [row for row in review.log_rows(review.lead) if row.get(LOG_EXCERPT) == text]


def marker_of(row: dict[str, Any]) -> Any:
    assert LOG_IS_UNDO in row, (
        f"The log row {row!r} carries no `{LOG_IS_UNDO}`. E6-09 done-when 7: every row says "
        "whether it undoes an earlier decision, so an undo reads as a reversal rather than as a "
        "fresh decision."
    )
    marker = row[LOG_IS_UNDO]
    assert isinstance(marker, bool), f"`{LOG_IS_UNDO}` is {marker!r}, not a boolean."
    return marker


def test_an_exclusion_then_its_undo_are_two_rows_and_only_the_undo_is_marked(
    lead_review: LeadReviewWorld,
) -> None:
    """Exclude a flagged comment, then undo it: the exclusion unmarked, the undo marked.

    **The mutations this kills:** `is_undo` missing from the payload; written as
    a constant (`false` everywhere, or `true` everywhere); and an undo row left
    out of the log, so the trail says the comment is still excluded. **The near
    miss:** the exclusion row marked as an undo because a later undo exists (the
    marker is the row's own, not the comment's).
    """
    review = lead_review
    text = "E6-09 a harmful comment the instructor excluded and then undid"
    comment = a_comment(review, text, HARMFUL)
    decided(review, comment, EXCLUDE)
    decided(review, comment, UNDO)

    rows = rows_for(review, text)
    assert len(rows) == 2, (
        f"The lead's log carries {len(rows)} rows for a comment excluded and then undone: {rows}. "
        "The exclusion and its undo are two decisions, and the log shows both, the undo as a "
        "reversal (E6-09 done-when 7)."
    )
    markers = sorted(marker_of(row) for row in rows)
    assert markers == [False, True], (
        f"The two rows carry `{LOG_IS_UNDO}` {markers}; the exclusion is not an undo and its "
        "reversal is."
    )
    exclusion = next(row for row in rows if row[LOG_IS_UNDO] is False)
    assert (
        exclusion.get(LOG_DECISION) == STORED_EXCLUDED
    ), f"The unmarked row is {exclusion!r}; it is the exclusion, `{STORED_EXCLUDED}`."


def test_an_undone_keep_reads_as_a_reversal_and_not_as_a_second_exclusion(
    lead_review: LeadReviewWorld,
) -> None:
    """Exclude an unflagged comment with a reason, keep it, undo the keep: three rows, one marked.

    The undo restores the state before the keep, `EXCLUDED`, so without the marker
    the log shows two exclusions of one comment and a keep between them.

    **The mutations this kills:** `is_undo` missing or constant; the undo row's
    `decision` rewritten to something other than what was stored. **The near
    miss:** marking every `EXCLUDED` row after a keep as an undo — the first
    exclusion came before the keep and is not one.
    """
    review = lead_review
    text = "E6-09 a clear comment excluded with a reason, kept, then the keep undone"
    comment = a_comment(review, text, CLEAR)
    decided(review, comment, EXCLUDE, A_STATED_REASON)
    decided(review, comment, KEEP)
    decided(review, comment, UNDO)

    rows = rows_for(review, text)
    assert (
        len(rows) == 3
    ), f"The lead's log carries {len(rows)} rows for a comment excluded, kept and un-kept: {rows}."
    described = sorted((str(row.get(LOG_DECISION)), marker_of(row)) for row in rows)
    expected = sorted([(STORED_EXCLUDED, False), (STORED_KEPT, False), (STORED_EXCLUDED, True)])
    assert described == expected, (
        f"The three rows are {described} as (decision, {LOG_IS_UNDO}); the sequence wrote "
        f"{expected}. The undo of the keep restores the exclusion and is marked as an undo, so the "
        "log reads 'excluded, kept, keep undone' rather than 'excluded, kept, excluded again'."
    )
