"""The Lead Faculty door — ticket E6-05, criteria 6 and 8, and work order decisions 1 and 4.

> 6. A Lead Faculty member excludes and keeps a queued comment; each is a row with
>    the decider and the stored role. In a shown stream, the instructor's card
>    shows the decision. In a held stream, a test shows that the instructor's
>    payload is the same before and after an exclusion and before and after a
>    keep (ruling 6: there is no held count).
> 8. An instructor decision on a comment in a held stream of their own section is
>    still refused after this ticket, and the same comment is accepted through the
>    Lead Faculty door by its lead.

And decision 1's rules for the door: only from `FLAGGED_COLLAPSED` (the queue
holds only undecided flags), a comment not in the reader's queue is a 404, the
reason is optional for a lead with the same 1–500 bounds when present, the row is
written as `LEAD_FACULTY` or `CHAIR` by whichever grant covers the course, and a
lead has no undo.

**Every decision is asserted on the record**, read on the bootstrap connection in
`sequence` order: exactly one new row, naming the reader's `person` and the role,
or no new row at all for a refusal. The success status is not asserted beyond
being a 2xx, because the work order settles the effect and not the status.

**The held-stream payload is read twice before and twice after** each decision
(`docs/MISTAKES.md` entry 51): a reader who keeps the previous report is
subtracting, so the property is over the sequence, and the first pair is also what
shows the payload is stable enough for "unchanged" to mean anything.

**Which failure a red is, before E6-05 lands.** `lead_routes` fails naming the
routes — a FAILED, never an ERROR (`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import (
    DECIDED_AS_COLUMN,
    DECIDER_COLUMN,
    EXCLUDED,
    IS_UNDO_COLUMN,
    KEPT,
    NOT_FOUND,
    REASON_COLUMN,
    STATE_COLUMN,
    STORED_EXCLUDED,
    STORED_KEPT,
    a_reason,
    require_decision_columns,
)
from fixtures.lead_review import (
    AS_CHAIR,
    AS_LEAD_FACULTY,
    EXCLUDE,
    KEEP,
    NOT_IN_QUEUE,
    OMITTED,
    UNDO,
    UNMAPPED_COHORT,
    LeadReviewWorld,
    Reader,
    is_a_client_refusal,
    is_success,
    lead_sentence_of,
)
from fixtures.moderation import HARMFUL
from fixtures.report_api import DECIDED_BY_YOU_FIELD, FIRST_HELD_WEEK, FULL_WEEK, TAUGHT_COHORT
from fixtures.report_comments import configured_threshold
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = pytest.mark.integration

REASON_BOUND = 500


def held(review: LeadReviewWorld, text: str, *, cohort: str = TAUGHT_COHORT) -> Any:
    """A harmful comment alone in course week 3's course stream, which is held."""
    comment = review.plant(
        course_week=FIRST_HELD_WEEK, stream=COURSE_STREAM, text=text, verdict=HARMFUL, cohort=cohort
    )
    if cohort == TAUGHT_COHORT:
        commenters = review.door.door.rows.commenters_in(FIRST_HELD_WEEK, COURSE_STREAM)
        assert 0 < commenters < configured_threshold(), (
            f"Course week {FIRST_HELD_WEEK}'s course stream holds {commenters} commenters; this "
            "comment is meant to sit in a held stream."
        )
    return comment


def shown(review: LeadReviewWorld, text: str) -> Any:
    """A harmful comment in course week 1's instructor stream, which is shown."""
    comment = review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=text,
        verdict=HARMFUL,
        cohort=TAUGHT_COHORT,
    )
    commenters = review.door.door.rows.commenters_in(FULL_WEEK, INSTRUCTOR_STREAM)
    assert commenters >= configured_threshold(), (
        f"Course week 1's instructor stream holds {commenters} commenters; this comment is meant "
        "to sit in a shown stream."
    )
    return comment


def decided(
    review: LeadReviewWorld,
    reader: Reader,
    comment: Any,
    action: str,
    *,
    stored: str,
    role: str,
    reason: Any = None,
) -> dict[str, Any]:
    """One accepted decision, and the one row it must leave; the row."""
    before = review.rows_of(comment)
    answered = review.decide(reader, comment, action, reason)
    assert is_success(answered.status_code), (
        f"`{action}` by {reader.label} on a comment in their queue was answered "
        f"{answered.status_code}. Body begins {answered.text[:400]!r}."
    )
    after = review.rows_of(comment)
    assert len(after) == len(before) + 1 and after[: len(before)] == before, (
        f"`{action}` by {reader.label} left {len(after)} rows where there were {len(before)}; a "
        "decision appends exactly one row and changes none."
    )
    row = after[-1]
    expected_reason = None if reason is OMITTED else reason
    assert (
        row[STATE_COLUMN],
        str(row[DECIDER_COLUMN]),
        row[DECIDED_AS_COLUMN],
        row[IS_UNDO_COLUMN],
        row[REASON_COLUMN],
    ) == (stored, str(reader.person_id), role, False, expected_reason), (
        f"`{action}` by {reader.label} appended {row!r}. Criterion 6: the row holds {stored!r}, "
        f"names the reader's person ({reader.person_id}) and the stored role {role!r}, is not an "
        f"undo, and carries the reason as sent ({expected_reason!r})."
    )
    return row


def refused_without_a_row(
    review: LeadReviewWorld, reader: Reader, comment: Any, action: str, reason: Any = None
) -> Any:
    before = review.rows_of(comment)
    answered = review.decide(reader, comment, action, reason)
    assert is_a_client_refusal(answered.status_code), (
        f"`{action}` by {reader.label} was answered {answered.status_code}; it is refused here. "
        f"Body begins {answered.text[:400]!r}."
    )
    assert review.rows_of(comment) == before, f"A refused `{action}` wrote a row."
    return answered


@pytest.mark.parametrize("action", [EXCLUDE, KEEP])
def test_a_lead_decision_is_one_row_naming_the_lead_and_the_lead_faculty_role(
    action: str, lead_review: LeadReviewWorld
) -> None:
    """Criterion 6's record: exclude and keep, each one row, decider and `LEAD_FACULTY`.

    The comment then leaves the queue, because the queue holds only undecided
    flags.

    **The mutations this kill:** the decision written with no decider, or as
    `INSTRUCTOR` (the shared write's default); `keep` written as `PUBLISHED`; a
    decided comment left in the queue. **The near miss:** a reason invented for
    a lead's decision (`reason` must be null when none was sent).
    """
    review = lead_review
    require_decision_columns(review.world.tables)
    comment = held(review, f"E6-05 a held harmful comment the lead will {action}")
    stored = STORED_EXCLUDED if action == EXCLUDE else STORED_KEPT

    decided(review, review.lead, comment, action, stored=stored, role=AS_LEAD_FACULTY)

    assert str(comment) not in review.queued_ids(review.lead), (
        f"After the lead's `{action}`, the comment is still in their queue; decision 1 holds only "
        "undecided flags there."
    )


def test_a_chair_decision_on_an_unmapped_course_is_stored_as_chair(
    lead_review: LeadReviewWorld,
) -> None:
    """Decision 1: "Written with `decided_as` LEAD_FACULTY or CHAIR, whichever grant covers it".

    **The mutation this kills:** the role hard-coded to `LEAD_FACULTY` for the
    whole leadership door.
    """
    review = lead_review
    require_decision_columns(review.world.tables)
    comment = held(
        review, "E6-05 a held harmful comment in the unmapped course", cohort=UNMAPPED_COHORT
    )
    decided(review, review.chair, comment, EXCLUDE, stored=STORED_EXCLUDED, role=AS_CHAIR)


def test_a_comment_the_lead_has_decided_is_not_decided_again_through_this_door(
    lead_review: LeadReviewWorld,
) -> None:
    """Decision 1: only from `FLAGGED_COLLAPSED`, and a comment not in the queue is a 404.

    The lead excludes a queued comment, then asks to keep it: 404 with the
    governed sentence, no row.

    **The mutations this kill:** the instructor's transition table borrowed for
    the lead (`keep` from `EXCLUDED` is allowed there); a 409 here, which says
    "this comment exists and is decided" to a reader the queue no longer shows it
    to. **The control** is the first decision, accepted.
    """
    review = lead_review
    require_decision_columns(review.world.tables)
    comment = held(review, "E6-05 a held harmful comment the lead excludes, then tries to keep")
    decided(review, review.lead, comment, EXCLUDE, stored=STORED_EXCLUDED, role=AS_LEAD_FACULTY)

    answered = refused_without_a_row(review, review.lead, comment, KEEP)
    assert answered.status_code == NOT_IN_QUEUE, (
        f"A second decision on a comment the lead already decided was answered "
        f"{answered.status_code}, not {NOT_IN_QUEUE}: it is no longer in their queue."
    )
    lead_sentence_of(answered, "The refusal of a decided comment")


def test_a_lead_has_no_undo(lead_review: LeadReviewWorld) -> None:
    """Decision 1: "No undo for a lead" — refused on a decided comment and on a queued one.

    **The mutations this kill:** the instructor's `undo` action accepted by the
    leadership door (it would append a row restoring the flag, with the lead as
    decider); and an `undo` treated as `keep` or `exclude`. **The control** is
    the lead's exclusion of the same comment, accepted between the two refusals.
    """
    review = lead_review
    require_decision_columns(review.world.tables)
    comment = held(review, "E6-05 a held harmful comment the lead cannot undo a decision on")

    refused_without_a_row(review, review.lead, comment, UNDO)
    decided(review, review.lead, comment, EXCLUDE, stored=STORED_EXCLUDED, role=AS_LEAD_FACULTY)
    refused_without_a_row(review, review.lead, comment, UNDO)


# Each case: the reason sent, and whether decision 1's bounds accept it.
REASONS = {
    "omitted": (OMITTED, True),
    "null": (None, True),
    "five-hundred-characters": (a_reason(REASON_BOUND), True),
    "empty": ("", False),
    "blank": ("   \t ", False),
    "five-hundred-and-one-characters": (a_reason(REASON_BOUND + 1), False),
}


@pytest.mark.parametrize("case", sorted(REASONS))
def test_a_leads_reason_is_optional_and_held_to_the_same_bounds_when_present(
    case: str, lead_review: LeadReviewWorld
) -> None:
    """Decision 1: the reason is optional for a lead, with the instructor's 1–500 bounds.

    An accepted reason is stored as sent; a refused one writes no row and is not
    the not-in-queue 404 (the comment is in the queue), and the same comment is
    then accepted with no reason — the control that the refusal was about the
    reason.

    **The mutations this kill:** a reason required of a lead (the omitted and null
    cases are refused); no bound at all (the blank and 501-character cases are
    accepted). **The near miss:** an off-by-one bound — 500 is accepted and 501
    refused.
    """
    review = lead_review
    require_decision_columns(review.world.tables)
    reason, accepted = REASONS[case]
    comment = held(review, f"E6-05 a held harmful comment excluded with a reason that is {case}")

    if accepted:
        decided(
            review,
            review.lead,
            comment,
            EXCLUDE,
            stored=STORED_EXCLUDED,
            role=AS_LEAD_FACULTY,
            reason=reason,
        )
        return
    answered = refused_without_a_row(review, review.lead, comment, EXCLUDE, reason)
    assert answered.status_code != NOT_IN_QUEUE, (
        f"A reason that is {case} was refused as {NOT_IN_QUEUE}, the not-in-queue answer; the "
        "comment is in the lead's queue, so the refusal has to be about the reason."
    )
    decided(review, review.lead, comment, EXCLUDE, stored=STORED_EXCLUDED, role=AS_LEAD_FACULTY)


@pytest.mark.parametrize(("action", "status"), [(EXCLUDE, EXCLUDED), (KEEP, KEPT)])
def test_in_a_shown_stream_the_instructors_card_shows_the_leads_decision(
    action: str, status: str, lead_review: LeadReviewWorld
) -> None:
    """Criterion 6, the shown half: the instructor's card carries the lead's decision.

    **The mutations this kill:** a lead's row the read path does not follow (the
    card stays `flagged_collapsed`); `decided_by_you` true for any decided row
    (the decider is the lead, not the reader).
    """
    review = lead_review
    require_decision_columns(review.world.tables)
    comment = shown(review, f"E6-05 a shown harmful comment the lead will {action}")
    stored = STORED_EXCLUDED if action == EXCLUDE else STORED_KEPT
    decided(review, review.lead, comment, action, stored=stored, role=AS_LEAD_FACULTY)

    for read in (1, 2):
        card = review.door.card(review.door.payload(FULL_WEEK), comment)
        assert card is not None, f"Read {read}: the shown comment is not on the week's report."
        assert (card.get("status"), card.get(DECIDED_BY_YOU_FIELD)) == (status, False), (
            f"Read {read}: after the lead's `{action}`, the instructor's card is {card!r}. It "
            f"reports {status!r}, and `decided_by_you` is false — the lead decided, not the reader."
        )


def differences(before: Any, after: Any, path: str = "$") -> list[str]:
    """The paths at which two JSON bodies differ, for a failure message that names them."""
    if isinstance(before, dict) and isinstance(after, dict):
        found: list[str] = []
        for key in sorted(set(before) | set(after), key=str):
            if key not in before or key not in after:
                found.append(f"{path}.{key}: {before.get(key)!r} -> {after.get(key)!r}")
            else:
                found.extend(differences(before[key], after[key], f"{path}.{key}"))
        return found
    if before != after:
        return [f"{path}: {before!r} -> {after!r}"]
    return []


@pytest.mark.parametrize("action", [EXCLUDE, KEEP])
def test_in_a_held_stream_the_instructors_payload_is_unchanged_by_the_leads_decision(
    action: str, lead_review: LeadReviewWorld
) -> None:
    """Criterion 6, the held half, over four consecutive reads (ruling 6; entry 51).

    The week is read twice; the lead decides through their own door; the week is
    read twice again. All four bodies are equal: below the threshold the comment
    is never shown, so anything that moved would be a trace of the decision.

    **The mutations this kill:** a held count served again under any name (it
    moves with the decision); a decided held comment surfaced on the instructor's
    report (an excluded or kept comment treated as shown). **The near miss:** a
    payload that is not stable at all — the first pair of reads is compared
    before any decision, so that is a broken test here, not a pass.
    """
    review = lead_review
    require_decision_columns(review.world.tables)
    comment = held(review, f"E6-05 a held harmful comment the lead will {action} unseen")
    stored = STORED_EXCLUDED if action == EXCLUDE else STORED_KEPT

    before = [review.door.payload(FIRST_HELD_WEEK), review.door.payload(FIRST_HELD_WEEK)]
    assert not differences(before[0], before[1]), (
        f"Two reads of course week {FIRST_HELD_WEEK} with nothing between them differ at "
        f"{differences(before[0], before[1])}, so 'unchanged' below cannot be asserted."
    )
    decided(review, review.lead, comment, action, stored=stored, role=AS_LEAD_FACULTY)
    after = [review.door.payload(FIRST_HELD_WEEK), review.door.payload(FIRST_HELD_WEEK)]

    for index, body in enumerate(after, start=3):
        changed = differences(before[0], body)
        assert not changed, (
            f"Read {index} of course week {FIRST_HELD_WEEK}, after the lead's `{action}`, differs "
            f"from read 1 at {changed}. Ruling 6: a held comment's decision leaves no trace."
        )


def test_the_instructor_door_still_refuses_a_held_comment_its_lead_may_decide(
    lead_review: LeadReviewWorld,
) -> None:
    """Criterion 8 and decision 4: each door holds its own check.

    A harmful comment in a held stream of the instructor's own section. The
    instructor's exclusion is refused 404 and writes nothing; the lead's is
    accepted; the instructor's is still refused afterwards.

    **The mutations this kill:** the instructor door's visibility check relaxed
    to "anything in my sections" (or made to accept what the lead door accepts)
    by a shared flag or role argument on the write; and the lead door delegating
    to the instructor door's check (the lead's exclusion is refused).
    """
    review = lead_review
    require_decision_columns(review.world.tables)
    comment = held(review, "E6-05 a held harmful comment both doors are asked about")

    def instructor_refused(when: str) -> None:
        before = review.rows_of(comment)
        answered = review.door.decide(comment, EXCLUDE)
        assert answered.status_code == NOT_FOUND, (
            f"{when}, the instructor's exclusion of a held comment in their own section was "
            f"answered {answered.status_code}, not {NOT_FOUND}. SPEC §5.2: an instructor decides "
            "only on a comment their report currently returns."
        )
        assert review.rows_of(comment) == before, f"{when}, the refused instructor decision wrote."

    instructor_refused("Before the lead decided")
    decided(review, review.lead, comment, EXCLUDE, stored=STORED_EXCLUDED, role=AS_LEAD_FACULTY)
    instructor_refused("After the lead excluded it")
