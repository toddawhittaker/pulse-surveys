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

**The exclusion log leaves those sections out too (E6-08).** A log row carries
the section, the date, the decider's role, the flag and the reason, so a row from
a taught section tells the reader that their own section held a flagged comment,
roughly when, and a paraphrase of it, even with the excerpt withheld. E6-08 drops
every row whose section the reader holds an `INSTRUCTOR` assignment on. The row is
removed, not redacted. The log tests assert the rows are absent, beside a row
from another section of the same course in the same read (the canary), for a lead
and for a chair.

**The mutation every test here kills:** the queue, the door or the log built from
the reader's leadership grant alone, ignoring the instructor grants the same person
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
    AS_CHAIR,
    AS_LEAD_FACULTY,
    EXCLUDE,
    ITEM_ANSWER_ID,
    LOG_REASON,
    LOG_SECTION_LABEL,
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


def a_logged_exclusion(
    review: LeadReviewWorld, *, text: str, cohort: str, reason: str, decided_as: str, held: bool
) -> Any:
    """One harmful comment in `cohort`, excluded by a person who is not the reader; its answer id.

    `held` puts it in course week 3's course stream with one commenter, below the
    threshold; otherwise it goes in course week 1's instructor stream. Planting
    only: nothing here asserts.
    """
    comment = review.plant(
        course_week=FIRST_HELD_WEEK if held else FULL_WEEK,
        stream=COURSE_STREAM if held else INSTRUCTOR_STREAM,
        text=text,
        verdict=HARMFUL,
        cohort=cohort,
    )
    review.plant_decision(
        comment,
        STORED_EXCLUDED,
        decided_by=review.door.a_person(),
        decided_as=decided_as,
        reason=reason,
    )
    return comment


def test_a_lead_who_teaches_a_section_of_their_led_course_finds_none_of_its_rows_in_the_log(
    lead_review: LeadReviewWorld,
) -> None:
    """E6-08 done-when 1, for a lead: the taught section's log rows are absent, not redacted.

    Another Lead Faculty member excluded a held comment in a section of the led
    course the lead does not teach (the canary), and then two comments in the
    section the lead does teach, one held and one in another week and stream
    whose held-ness this test does not rely on. One read of the log must
    carry the canary row and no row from the taught section. The log read before
    the taught section's rows were planted must equal the one after, so a row
    kept with its members blanked is red too.

    **The mutation this kills:** `exclusion_log` scoped by the leadership grant
    alone, ignoring the reader's instructor assignments (the taught section's two
    rows are listed). **The near misses:** the filter keyed on the taught
    section's course rather than the section (the canary is lost); the row
    redacted rather than removed (the before and after reads differ).
    """
    review = lead_review
    reader = review.lead
    review.teaches(reader, LEADS_TAUGHT_COHORT)
    taught_code = review.code_of(LEADS_TAUGHT_COHORT)
    canary_code = review.code_of(LEADS_CANARY_COHORT)
    canary_reason = "E6-08: excluded in the led course's section the lead does not teach"
    held_text = "E6-08: held harmful text from the lead's taught section, never in the log"
    held_reason = "E6-08: a held comment excluded in the lead's taught section"
    second_reason = "E6-08: a second comment excluded in the lead's taught section"
    a_logged_exclusion(
        review,
        text="E6-08: a held harmful comment in the sibling section, the canary",
        cohort=LEADS_CANARY_COHORT,
        reason=canary_reason,
        decided_as=AS_LEAD_FACULTY,
        held=True,
    )
    before = review.log_rows(reader)
    a_logged_exclusion(
        review,
        text=held_text,
        cohort=LEADS_TAUGHT_COHORT,
        reason=held_reason,
        decided_as=AS_LEAD_FACULTY,
        held=True,
    )
    a_logged_exclusion(
        review,
        text="E6-08: a second harmful comment in the lead's own taught section",
        cohort=LEADS_TAUGHT_COHORT,
        reason=second_reason,
        decided_as=AS_LEAD_FACULTY,
        held=False,
    )

    answered = review.log(reader)
    assert answered.status_code == 200, (
        f"The log answered {answered.status_code} to {reader.label}, who holds a leadership "
        f"grant. Body begins {answered.text[:400]!r}."
    )
    body = answered.json()
    rows = the_list_in(body, f"The log read for {reader.label}")
    canary = [row for row in rows if row.get(LOG_REASON) == canary_reason]
    assert len(canary) == 1, (
        f"The canary: {reader.label}'s log carries {len(canary)} rows for the exclusion in section "
        f"{canary_code}, a section of the course they lead that they do not teach. Either the log "
        "answered nothing, or it left out the whole course rather than the taught section."
    )
    canary_label = str(canary[0].get(LOG_SECTION_LABEL))
    assert canary_code in canary_label and taught_code not in canary_label, (
        f"The canary row's section label is {canary_label!r}, which should name {canary_code!r} "
        f"and not {taught_code!r}. Without that, searching labels for the taught section proves "
        "nothing: a broken test, not a red."
    )
    reasons = [row.get(LOG_REASON) for row in rows]
    assert held_reason not in reasons and second_reason not in reasons, (
        f"{reader.label}'s log lists decisions from section {taught_code}, which they teach. "
        "E6-08: the log drops every row whose section the reader holds an instructor assignment "
        "on, because a row names the section, the date and a paraphrase of a comment the "
        "instructor report withholds from them."
    )
    labels = [str(row.get(LOG_SECTION_LABEL)) for row in rows]
    assert not [label for label in labels if taught_code in label], (
        f"{reader.label}'s log carries rows of section {taught_code}, which they teach: "
        f"{[label for label in labels if taught_code in label]}."
    )
    assert not [
        value for value in strings_in(body) if held_text[:FRAGMENT] in value
    ], f"The text of a held comment from the section {reader.label} teaches is in their log."
    assert rows == before, (
        f"Two exclusions in section {taught_code}, which {reader.label} teaches, changed the "
        f"log from {before!r} to {rows!r}. E6-08: the row is removed, not redacted, so the taught "
        "section's decisions add nothing to the log."
    )


def test_a_chair_who_teaches_a_section_of_an_unled_course_finds_none_of_its_rows_in_the_log(
    lead_review: LeadReviewWorld,
) -> None:
    """E6-08 done-when 1, for a chair: the same rule over the chair's grant, one level out.

    The chair's grant is the department's unled courses, a different currency
    from a lead's course mapping (`docs/MISTAKES.md` entries 35 and 53). Another
    chair excluded a held comment in the unmapped course's second section (the
    canary), and then a held and a second comment in the section the chair
    teaches. One read carries the canary and nothing from the taught section, and
    equals the read taken before the taught section's rows were planted.

    **The mutation this kills:** the taught-section filter applied to the lead
    path only, so a chair's log still lists their taught section's rows. **The
    near misses:** the filter keyed on the course (the canary, in the same
    course, is lost); the row redacted rather than removed (the before and after
    reads differ).
    """
    review = lead_review
    review.a_second_section_of_the_unmapped_course()
    reader = review.chair
    review.teaches(reader, CHAIRS_TAUGHT_COHORT)
    taught_code = review.code_of(CHAIRS_TAUGHT_COHORT)
    canary_code = review.code_of(CHAIRS_CANARY_COHORT)
    canary_reason = "E6-08: excluded in the unled course's section the chair does not teach"
    held_text = "E6-08: held harmful text from the chair's taught section, never in the log"
    held_reason = "E6-08: a held comment excluded in the chair's taught section"
    second_reason = "E6-08: a second comment excluded in the chair's taught section"
    a_logged_exclusion(
        review,
        text="E6-08: a held harmful comment in the unled course's second section, the canary",
        cohort=CHAIRS_CANARY_COHORT,
        reason=canary_reason,
        decided_as=AS_CHAIR,
        held=True,
    )
    before = review.log_rows(reader)
    a_logged_exclusion(
        review,
        text=held_text,
        cohort=CHAIRS_TAUGHT_COHORT,
        reason=held_reason,
        decided_as=AS_CHAIR,
        held=True,
    )
    a_logged_exclusion(
        review,
        text="E6-08: a second harmful comment in the chair's own taught section",
        cohort=CHAIRS_TAUGHT_COHORT,
        reason=second_reason,
        decided_as=AS_CHAIR,
        held=False,
    )

    answered = review.log(reader)
    assert answered.status_code == 200, (
        f"The log answered {answered.status_code} to {reader.label}, who holds a leadership "
        f"grant. Body begins {answered.text[:400]!r}."
    )
    body = answered.json()
    rows = the_list_in(body, f"The log read for {reader.label}")
    canary = [row for row in rows if row.get(LOG_REASON) == canary_reason]
    assert len(canary) == 1, (
        f"The canary: {reader.label}'s log carries {len(canary)} rows for the exclusion in section "
        f"{canary_code}, a section of the unled course they review that they do not teach. Either "
        "the log answered nothing, or it left out the whole course rather than the taught section."
    )
    canary_label = str(canary[0].get(LOG_SECTION_LABEL))
    assert canary_code in canary_label and taught_code not in canary_label, (
        f"The canary row's section label is {canary_label!r}, which should name {canary_code!r} "
        f"and not {taught_code!r}. Without that, searching labels for the taught section proves "
        "nothing: a broken test, not a red."
    )
    reasons = [row.get(LOG_REASON) for row in rows]
    assert held_reason not in reasons and second_reason not in reasons, (
        f"{reader.label}'s log lists decisions from section {taught_code}, which they teach. "
        "E6-08: the log drops every row whose section the reader holds an instructor assignment "
        "on, for a chair's grant as for a lead's."
    )
    labels = [str(row.get(LOG_SECTION_LABEL)) for row in rows]
    assert not [label for label in labels if taught_code in label], (
        f"{reader.label}'s log carries rows of section {taught_code}, which they teach: "
        f"{[label for label in labels if taught_code in label]}."
    )
    assert not [
        value for value in strings_in(body) if held_text[:FRAGMENT] in value
    ], f"The text of a held comment from the section {reader.label} teaches is in their log."
    assert rows == before, (
        f"Two exclusions in section {taught_code}, which {reader.label} teaches, changed the "
        f"log from {before!r} to {rows!r}. E6-08: the row is removed, not redacted, so the taught "
        "section's decisions add nothing to the log."
    )
