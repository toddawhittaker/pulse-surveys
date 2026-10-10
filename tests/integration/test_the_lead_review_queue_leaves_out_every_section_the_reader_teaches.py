"""Ruling 7 on PR #296: a leader's review never shows held text from a section they teach.

SPEC §5.2 and §4.1 item 3: the instructor door refuses an instructor the text of
a comment held below the threshold, because in a tiny week the instructor can
guess who wrote it. A Lead Faculty member or a chair who **also** teaches a
section of a course they review would otherwise read that same held text through
the leadership queue. Ruling 7 closes it:

  - the queue leaves out every section the reader holds an `INSTRUCTOR`
    assignment on;
  - the leadership decision door refuses a comment from such a section with the
    same 404, and the same body, as any comment outside the reader's queue, and
    writes no row;
  - those comments wait for E9.

**The canary is a sibling section of the same course, read in the same request.**
Each absence sits beside a held harmful comment from another section of the very
course the reader reviews, and that comment must be in the queue
(`docs/MISTAKES.md` entry 3). It is also what tells the right rule from its near
miss: a rule keyed on the course rather than the section would hide the sibling
section too, and reds on the canary.

**The exclusion log keeps its rows.** The ruling leaves the log's scope alone,
and the log already withholds the excerpt of held text. So the log test asserts
only that no text of a held comment from the taught section reaches the reader,
beside a shown row whose excerpt does (the canary), and says nothing about
whether that section's rows are listed.

**The mutation every test here kills:** the queue (or the door) built from the
reader's leadership grant alone, ignoring the instructor grants the same person
holds. **The near miss:** the exclusion keyed on the course of a taught section
rather than the section itself.

Marked `invariant`: CI runs these in the isolated §4.1 pass, which treats a skip
as a failure.
"""

from typing import Any, NamedTuple
from uuid import uuid4

import pytest
from fixtures.instructor_decisions import STORED_EXCLUDED
from fixtures.lead_review import (
    AS_LEAD_FACULTY,
    EXCERPT_LENGTH,
    EXCLUDE,
    ITEM_ANSWER_ID,
    LOG_EXCERPT,
    LOG_REASON,
    NOT_IN_QUEUE,
    UNMAPPED_COHORT,
    UNMAPPED_SECOND_COHORT,
    LeadReviewWorld,
    Reader,
    is_success,
    lead_sentence_of,
    the_list_in,
)
from fixtures.moderation import HARMFUL
from fixtures.report_api import (
    FIRST_HELD_WEEK,
    FULL_WEEK,
    TAUGHT_COHORT,
    UNTAUGHT_COHORT,
    strings_in,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The lead's taught section is the own course's `Q1WW`, which the door's instructor
# does not teach; the canary is the same course's `F1WW`, which the lead does not.
LEADS_TAUGHT_COHORT = UNTAUGHT_COHORT
LEADS_CANARY_COHORT = TAUGHT_COHORT

# The chair's taught section is the unmapped course's `41WW`; the canary is the
# second section the fixture plants in that same course.
CHAIRS_TAUGHT_COHORT = UNMAPPED_COHORT
CHAIRS_CANARY_COHORT = UNMAPPED_SECOND_COHORT

# How much of a comment's text counts as "its text" in a body search: enough to be
# this comment's alone, short enough to catch a truncated copy.
FRAGMENT = 40


def a_held_harmful(review: LeadReviewWorld, text: str, cohort: str) -> Any:
    """A harmful comment in course week 3's course stream, one commenter, below the threshold."""
    return review.plant(
        course_week=FIRST_HELD_WEEK, stream=COURSE_STREAM, text=text, verdict=HARMFUL, cohort=cohort
    )


def one_queue_read(review: LeadReviewWorld, reader: Reader) -> tuple[set[str], list[str]]:
    """One read of the reader's queue: the answer ids it carries, and every string in its body."""
    answered = review.queue(reader)
    assert answered.status_code == 200, (
        f"The queue answered {answered.status_code} to {reader.label}, who holds a leadership "
        f"grant. Body begins {answered.text[:400]!r}."
    )
    body = answered.json()
    items = the_list_in(body, f"The queue read for {reader.label}")
    return {str(item.get(ITEM_ANSWER_ID)) for item in items}, strings_in(body)


class QueueRead(NamedTuple):
    """What one queue read beside a taught section and its canary returned."""

    in_taught: Any
    in_canary: Any
    taught_text: str
    queued: set[str]
    strings: list[str]


def read_the_queue_beside_a_taught_section(
    review: LeadReviewWorld, reader: Reader, *, taught: str, canary: str
) -> QueueRead:
    taught_text = f"E6-05 ruling 7: held harmful in {reader.label}'s own taught section, {taught}"
    canary_text = f"E6-05 ruling 7: held harmful in the sibling section {canary}, the canary"
    in_taught = a_held_harmful(review, taught_text, taught)
    in_canary = a_held_harmful(review, canary_text, canary)
    queued, strings = one_queue_read(review, reader)
    return QueueRead(in_taught, in_canary, taught_text, queued, strings)


class DoorReads(NamedTuple):
    """What the leader door answered, and the taught comment's rows around the refusal."""

    in_taught: Any
    rows_before: Any
    refused: Any
    nothing: Any
    accepted: Any


def decide_beside_a_taught_section(
    review: LeadReviewWorld, reader: Reader, *, taught: str, canary: str
) -> DoorReads:
    in_taught = a_held_harmful(review, f"E6-05 ruling 7: {reader.label} teaches this one", taught)
    in_canary = a_held_harmful(review, f"E6-05 ruling 7: {reader.label} may decide this", canary)
    before = review.rows_of(in_taught)
    refused = review.decide(reader, in_taught, EXCLUDE)
    nothing = review.decide(reader, uuid4(), EXCLUDE)
    accepted = review.decide(reader, in_canary, EXCLUDE)
    return DoorReads(in_taught, before, refused, nothing, accepted)


def test_a_lead_who_teaches_a_section_of_their_led_course_does_not_see_its_held_comments(
    lead_review: LeadReviewWorld,
) -> None:
    """The queue, for a lead: the taught section's held comment absent, the sibling's present.

    **The mutation this kills:** the queue built from the lead grant alone. **The
    near miss:** the exclusion keyed on the course, which loses the canary.
    """
    review = lead_review
    review.teaches(review.lead, LEADS_TAUGHT_COHORT)
    reader = review.lead
    taught, canary = LEADS_TAUGHT_COHORT, LEADS_CANARY_COHORT
    read = read_the_queue_beside_a_taught_section(review, reader, taught=taught, canary=canary)
    assert str(read.in_canary) in read.queued, (
        f"The canary: {reader.label}'s queue lacks the held harmful comment from section "
        f"{review.code_of(canary)}, a section of the course they review that they do not teach. "
        "Either the queue answered nothing, or the rule left out the whole course rather than "
        "the taught section (ruling 7 is per section)."
    )
    assert str(read.in_taught) not in read.queued, (
        f"{reader.label}'s queue carries the held harmful comment from section "
        f"{review.code_of(taught)}, which they teach. Ruling 7: the queue leaves out every section "
        "the reader holds an instructor assignment on, because the instructor door refuses them "
        "that held text (SPEC §5.2, §4.1 item 3)."
    )
    assert not [value for value in read.strings if read.taught_text[:FRAGMENT] in value], (
        f"The text of the held comment from {reader.label}'s own taught section is somewhere in "
        "their queue's body."
    )


def test_a_lead_deciding_on_a_comment_from_a_section_they_teach_gets_the_governed_404(
    lead_review: LeadReviewWorld,
) -> None:
    """The leader door, for a lead: 404, the governed sentence, the not-found body, no row.

    **The mutation this kills:** a door that checks the lead grant alone and
    writes the taught section's comment as `LEAD_FACULTY`. **The control:** the
    same lead's exclusion of the sibling section's comment is accepted, which
    also catches the course-keyed near miss.
    """
    review = lead_review
    review.teaches(review.lead, LEADS_TAUGHT_COHORT)
    reader = review.lead
    taught, canary = LEADS_TAUGHT_COHORT, LEADS_CANARY_COHORT
    door = decide_beside_a_taught_section(review, reader, taught=taught, canary=canary)
    refused = door.refused
    assert refused.status_code == NOT_IN_QUEUE, (
        f"{reader.label}'s exclusion of a held comment from section {review.code_of(taught)}, "
        f"which they teach, was answered {refused.status_code}, not {NOT_IN_QUEUE}. Ruling 7: the "
        "leader door refuses it like any comment outside the queue. Body begins "
        f"{refused.text[:400]!r}."
    )
    lead_sentence_of(refused, f"The refusal of {reader.label}'s own taught section's comment")
    assert (
        review.rows_of(door.in_taught) == door.rows_before
    ), f"A refused decision by {reader.label} on their taught section's comment wrote a row."
    nothing = door.nothing
    assert (nothing.status_code, nothing.text) == (refused.status_code, refused.text), (
        f"An id nothing holds was answered {nothing.status_code} {nothing.text[:200]!r} and the "
        f"taught section's comment {refused.status_code} {refused.text[:200]!r}. Ruling 7: the "
        "same 404 as any comment outside the queue, so the answer says nothing about existence."
    )
    assert is_success(door.accepted.status_code), (
        f"The control: {reader.label}'s exclusion of the held comment from section "
        f"{review.code_of(canary)}, which they review and do not teach, was answered "
        f"{door.accepted.status_code}. Either the door refuses everything, or it refused the whole "
        "course rather than the taught section."
    )


def test_a_chair_who_teaches_a_section_of_an_unled_course_does_not_see_its_held_comments(
    lead_review: LeadReviewWorld,
) -> None:
    """The queue, for a chair: the same rule over the chair's grant, one level out.

    The chair's grant is the department's unled courses, a different currency
    from a lead's course mapping, so a fix applied to the lead grant only would
    pass the lead's test and fail this one. The unmapped course gets a second
    section for the canary.
    """
    review = lead_review
    review.a_second_section_of_the_unmapped_course()
    review.teaches(review.chair, CHAIRS_TAUGHT_COHORT)
    reader = review.chair
    taught, canary = CHAIRS_TAUGHT_COHORT, CHAIRS_CANARY_COHORT
    read = read_the_queue_beside_a_taught_section(review, reader, taught=taught, canary=canary)
    assert str(read.in_canary) in read.queued, (
        f"The canary: {reader.label}'s queue lacks the held harmful comment from section "
        f"{review.code_of(canary)}, a section of the course they review that they do not teach. "
        "Either the queue answered nothing, or the rule left out the whole course rather than "
        "the taught section (ruling 7 is per section)."
    )
    assert str(read.in_taught) not in read.queued, (
        f"{reader.label}'s queue carries the held harmful comment from section "
        f"{review.code_of(taught)}, which they teach. Ruling 7: the queue leaves out every section "
        "the reader holds an instructor assignment on, because the instructor door refuses them "
        "that held text (SPEC §5.2, §4.1 item 3)."
    )
    assert not [value for value in read.strings if read.taught_text[:FRAGMENT] in value], (
        f"The text of the held comment from {reader.label}'s own taught section is somewhere in "
        "their queue's body."
    )


def test_a_chair_deciding_on_a_comment_from_a_section_they_teach_gets_the_governed_404(
    lead_review: LeadReviewWorld,
) -> None:
    """The leader door, for a chair: 404, the governed sentence, the not-found body, no row."""
    review = lead_review
    review.a_second_section_of_the_unmapped_course()
    review.teaches(review.chair, CHAIRS_TAUGHT_COHORT)
    reader = review.chair
    taught, canary = CHAIRS_TAUGHT_COHORT, CHAIRS_CANARY_COHORT
    door = decide_beside_a_taught_section(review, reader, taught=taught, canary=canary)
    refused = door.refused
    assert refused.status_code == NOT_IN_QUEUE, (
        f"{reader.label}'s exclusion of a held comment from section {review.code_of(taught)}, "
        f"which they teach, was answered {refused.status_code}, not {NOT_IN_QUEUE}. Ruling 7: the "
        "leader door refuses it like any comment outside the queue. Body begins "
        f"{refused.text[:400]!r}."
    )
    lead_sentence_of(refused, f"The refusal of {reader.label}'s own taught section's comment")
    assert (
        review.rows_of(door.in_taught) == door.rows_before
    ), f"A refused decision by {reader.label} on their taught section's comment wrote a row."
    nothing = door.nothing
    assert (nothing.status_code, nothing.text) == (refused.status_code, refused.text), (
        f"An id nothing holds was answered {nothing.status_code} {nothing.text[:200]!r} and the "
        f"taught section's comment {refused.status_code} {refused.text[:200]!r}. Ruling 7: the "
        "same 404 as any comment outside the queue, so the answer says nothing about existence."
    )
    assert is_success(door.accepted.status_code), (
        f"The control: {reader.label}'s exclusion of the held comment from section "
        f"{review.code_of(canary)}, which they review and do not teach, was answered "
        f"{door.accepted.status_code}. Either the door refuses everything, or it refused the whole "
        "course rather than the taught section."
    )


def test_no_held_text_from_a_section_the_lead_teaches_reaches_them_through_the_log(
    lead_review: LeadReviewWorld,
) -> None:
    """The log: rows may stay, but no text of a held comment from the taught section is in it.

    A held harmful comment in the lead's taught section, excluded earlier by
    another Lead Faculty member; a shown harmful comment in the sibling section,
    excluded too (the canary, whose excerpt the log carries). Whether the taught
    section's row is listed is deliberately not asserted.

    **The mutation this kills:** the excerpt taken for every row, which hands the
    lead the held text of their own section beside a date. **The near miss:** an
    excerpt dropped from every row, which the canary reds.
    """
    review = lead_review
    review.teaches(review.lead, LEADS_TAUGHT_COHORT)
    held_text = "E6-05 ruling 7: held text from the lead's taught section, never in their log"
    shown_text = "E6-05 ruling 7: a shown comment in the sibling section, its excerpt in the log"
    shown_reason = "E6-05 ruling 7: the sibling section's shown exclusion, the canary"
    held = a_held_harmful(review, held_text, LEADS_TAUGHT_COHORT)
    shown = review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=shown_text,
        verdict=HARMFUL,
        cohort=LEADS_CANARY_COHORT,
    )
    for comment, reason in (
        (held, "E6-05 ruling 7: the taught section's held exclusion"),
        (shown, shown_reason),
    ):
        review.plant_decision(
            comment,
            STORED_EXCLUDED,
            decided_by=review.door.a_person(),
            decided_as=AS_LEAD_FACULTY,
            reason=reason,
        )

    answered = review.log(review.lead)
    rows = review.log_rows(review.lead)
    canary = [row for row in rows if row.get(LOG_REASON) == shown_reason]
    assert len(canary) == 1 and canary[0].get(LOG_EXCERPT) == shown_text[:EXCERPT_LENGTH], (
        f"The canary: the lead's log carries {len(canary)} rows for the sibling section's shown "
        f"exclusion, with excerpts {[row.get(LOG_EXCERPT) for row in canary]}."
    )
    leaked = [value for value in strings_in(answered.json()) if held_text[:FRAGMENT] in value]
    assert not leaked, (
        "The text of a held comment from the section the lead teaches is in their exclusion log. "
        "Ruling 7: a leader never reads held text from their own taught section."
    )
