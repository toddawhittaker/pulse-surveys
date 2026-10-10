"""A section a leader has taught stays out of their review — E6-09, done-when 5.

> One authz helper returns the sections a person teaches or has taught (current
> grants plus `ended_teaching_grant`). The queue select, the leader door and the
> exclusion log all use it. A marked test ends a grant through the roster sync's
> own path, then reads the queue and the log: the section's items are absent, and
> a sibling section's are present.

Ruling 7 on PR #296 keeps a leader's own taught sections out of their queue and
log, because the instructor door refuses them that held text (SPEC §5.2, §4.1 item
3). Read off *current* assignments only, the rule lapses the moment the roster
drops the teaching grant — the same person, who saw the section's comments as its
instructor until last week, now reads its held comments as a leader. SPEC §5.2:
"neither sees rows from a section they teach", and a section taught this term is
one they teach for this purpose.

**The grant is ended through the roster sync's own writer**: the `SECURITY
DEFINER` function `public.end_teaching_instructor`, called on `pulse_app`'s own
connection with a successful roster call of the section — the only path that
deletes a teaching grant and writes `ended_teaching_grant` (E5.1-02, ADR 0183).
Before anything is read, the grant is shown gone and its ended row shown written,
so the world is the one the criterion names.

**Every absence sits beside a present canary in the same read**: a sibling section
of the same course, which the reader never taught (`docs/MISTAKES.md` entry 3). A
rule keyed on the course rather than the section loses the canary. **The rows are
found the way the reader finds them**: the queue, the log and the leader door over
HTTP (`docs/MISTAKES.md` entries 35 and 53), for a lead and, one grant out, for a
chair.

ADR 0190 records the reverse case — a lead who later starts teaching the section —
as an accepted residual; nothing here asserts it.

**Which failure a red is, before E6-09 lands.** The queue, log and door read
current assignments only, so the ended section's items are present: the absence
assertions fail naming them.
"""

from datetime import UTC, datetime
from typing import Any, NamedTuple
from uuid import uuid4

import pytest
from fixtures.instructor_decisions import STORED_EXCLUDED
from fixtures.lead_review import (
    AS_LEAD_FACULTY,
    EXCLUDE,
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
    INSTRUCTOR_ROLE,
    TAUGHT_COHORT,
    UNTAUGHT_COHORT,
    strings_in,
)
from fixtures.report_views import COURSE_STREAM
from fixtures.roster_sync import (
    END_TEACHING_INSTRUCTOR_CALL,
    ended_teaching_grants,
    institution_today,
    require_the_ended_teaching_grant_table,
    require_the_grant_ending_definer,
)
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The lead taught `Q1WW` of the course they lead; the canary is `F1WW`, which they
# never taught. The chair taught the unled course's cohort-`4` section; the canary
# is the second section of that course.
LEADS_ENDED_COHORT = UNTAUGHT_COHORT
LEADS_CANARY_COHORT = TAUGHT_COHORT
CHAIRS_ENDED_COHORT = UNMAPPED_COHORT
CHAIRS_CANARY_COHORT = UNMAPPED_SECOND_COHORT

FRAGMENT = 40


class Ended(NamedTuple):
    """A teaching grant that was held and has been ended by the roster's writer."""

    assignment_id: Any
    section_id: Any


def taught_then_ended(
    review: LeadReviewWorld, reader: Reader, cohort: str, application_session: Any
) -> Ended:
    """Give `reader` an instructor grant on `cohort`'s section, then end it as the roster sync does.

    Planting and premise checks only. The grant is ended by calling the ending
    definer on `pulse_app`'s connection, citing a successful roster call of that
    section; the assignment is then read back gone and the `ended_teaching_grant`
    row read back present, or the world is broken and says so.
    """
    session = review.rows.session
    require_the_grant_ending_definer(session)
    require_the_ended_teaching_grant_table(session)
    section = review.world.section_id(cohort)
    held_before = len(review.graph.assignments_of(reader.person_id))
    row = review.graph.assign(INSTRUCTOR_ROLE, scope=section, person=reader.person_id)
    assignment_id = row[review.graph.assignment_key]
    call = review.rows.seed(
        "nrps_call",
        {},
        section_id=section,
        url=f"https://roster.e6-09.invalid/{uuid4().hex[:12]}",
        response_code=200,
        members_seen=1,
        called_at=datetime.now(UTC),
    )
    review.rows.commit()

    application_session.execute(
        text(END_TEACHING_INSTRUCTOR_CALL),
        {
            "assignment_id": assignment_id,
            "nrps_call_id": call["id"],
            "ended_on": institution_today(),
        },
    )
    application_session.commit()

    held_after = len(review.graph.assignments_of(reader.person_id))
    assert held_after == held_before, (
        f"{reader.label} holds {held_after} assignments after the ending, {held_before} before the "
        "instructor grant was given: the grant was not ended, so this is ruling 7's plain case."
    )
    recorded = [
        ended
        for ended in ended_teaching_grants(session)
        if str(ended["assignment_id"]) == str(assignment_id)
    ]
    assert len(recorded) == 1 and str(recorded[0]["section_id"]) == str(section), (
        f"The ending left {recorded} in `ended_teaching_grant` for the grant on section {section}; "
        "the roster's writer records exactly one row naming the section."
    )
    return Ended(assignment_id=assignment_id, section_id=section)


def a_held_harmful(review: LeadReviewWorld, text_: str, cohort: str) -> Any:
    return review.plant(
        course_week=FIRST_HELD_WEEK,
        stream=COURSE_STREAM,
        text=text_,
        verdict=HARMFUL,
        cohort=cohort,
    )


def read_the_queue(review: LeadReviewWorld, reader: Reader) -> tuple[set[str], list[str]]:
    answered = review.queue(reader)
    assert answered.status_code == 200, (
        f"The queue answered {answered.status_code} to {reader.label}. Body begins "
        f"{answered.text[:400]!r}."
    )
    body = answered.json()
    items = the_list_in(body, f"The queue read for {reader.label}")
    return {str(item.get("answer_id")) for item in items}, strings_in(body)


def assert_the_queue_leaves_out_the_ended_section(
    review: LeadReviewWorld, reader: Reader, *, ended: str, canary: str
) -> None:
    ended_text = f"E6-09 held harmful in section {ended}, which {reader.label} taught until now"
    in_ended = a_held_harmful(review, ended_text, ended)
    in_canary = a_held_harmful(review, f"E6-09 held harmful in sibling section {canary}", canary)

    queued, strings = read_the_queue(review, reader)
    assert str(in_canary) in queued, (
        f"The canary: {reader.label}'s queue lacks the held comment from section "
        f"{review.code_of(canary)}, which they review and never taught. Either the queue answered "
        "nothing or the rule left out the whole course rather than the section."
    )
    assert str(in_ended) not in queued, (
        f"{reader.label}'s queue carries the held comment from section {review.code_of(ended)}, "
        "whose teaching grant the roster ended. E6-09 done-when 5: a section the reader has taught "
        "stays out of their review — the instructor door refused them that held text yesterday."
    )
    assert not [value for value in strings if ended_text[:FRAGMENT] in value], (
        f"The held text from the section {reader.label} taught is in their queue's body."
    )


def test_a_lead_whose_teaching_grant_ended_still_finds_none_of_that_sections_held_comments(
    lead_review: LeadReviewWorld, application_session: Any
) -> None:
    """The queue, for a lead: the ended section's held comment absent, the sibling's present.

    **The mutation this kills:** the queue's taught-section exclusion read from
    current `INSTRUCTOR` assignments only. **The near miss:** the exclusion keyed
    on the course of the ended section, which loses the canary.
    """
    review = lead_review
    reader = review.lead
    taught_then_ended(review, reader, LEADS_ENDED_COHORT, application_session)
    assert_the_queue_leaves_out_the_ended_section(
        review, reader, ended=LEADS_ENDED_COHORT, canary=LEADS_CANARY_COHORT
    )


def test_a_chair_whose_teaching_grant_ended_still_finds_none_of_that_sections_held_comments(
    lead_review: LeadReviewWorld, application_session: Any
) -> None:
    """The queue, for a chair: the same rule over the chair's grant, one level out.

    **The mutation this kills:** the ended-grant union applied to the lead path
    only (`docs/MISTAKES.md` entries 35 and 53: a chair's grant is a different
    currency from a lead's mapping).
    """
    review = lead_review
    review.a_second_section_of_the_unmapped_course()
    reader = review.chair
    taught_then_ended(review, reader, CHAIRS_ENDED_COHORT, application_session)
    assert_the_queue_leaves_out_the_ended_section(
        review, reader, ended=CHAIRS_ENDED_COHORT, canary=CHAIRS_CANARY_COHORT
    )


def test_a_lead_whose_teaching_grant_ended_finds_none_of_that_sections_rows_in_the_log(
    lead_review: LeadReviewWorld, application_session: Any
) -> None:
    """The log, for a lead: the ended section's rows absent, the sibling section's present.

    Another Lead Faculty member excluded a held comment in each section; one read
    of the log must carry the canary's row and no row of the ended section, by
    reason and by section label.

    **The mutation this kills:** `exclusion_log` filtering taught sections from
    current assignments only. **The near miss:** the filter keyed on the course,
    which loses the canary.
    """
    review = lead_review
    reader = review.lead
    taught_then_ended(review, reader, LEADS_ENDED_COHORT, application_session)
    ended_code = review.code_of(LEADS_ENDED_COHORT)
    canary_code = review.code_of(LEADS_CANARY_COHORT)
    canary_reason = "E6-09 excluded in the sibling section the lead never taught"
    ended_reason = "E6-09 excluded in the section the lead taught until the roster ended it"
    ended_text = "E6-09 held harmful text from the section the lead taught, never in their log"
    canary_text = "E6-09 held harmful in the sibling section, the canary"
    for text_, cohort, reason in (
        (canary_text, LEADS_CANARY_COHORT, canary_reason),
        (ended_text, LEADS_ENDED_COHORT, ended_reason),
    ):
        review.plant_decision(
            a_held_harmful(review, text_, cohort),
            STORED_EXCLUDED,
            decided_by=review.door.a_person(),
            decided_as=AS_LEAD_FACULTY,
            reason=reason,
        )

    answered = review.log(reader)
    assert answered.status_code == 200, f"The log answered {answered.status_code} to the lead."
    body = answered.json()
    rows = the_list_in(body, "The log read for the lead")
    canary = [row for row in rows if row.get(LOG_REASON) == canary_reason]
    assert len(canary) == 1 and canary_code in str(canary[0].get(LOG_SECTION_LABEL)), (
        f"The canary: the lead's log carries {canary} for the exclusion in section {canary_code}, "
        "which they lead and never taught; it should carry exactly one row naming that section."
    )
    assert ended_reason not in [row.get(LOG_REASON) for row in rows], (
        f"The lead's log lists the exclusion in section {ended_code}, whose teaching grant the "
        "roster ended. E6-09 done-when 5: a row from a section the reader has taught is removed, "
        "because it names the section, the date and a paraphrase of a held comment."
    )
    assert not [row for row in rows if ended_code in str(row.get(LOG_SECTION_LABEL))], (
        f"The lead's log carries rows of section {ended_code}, which they taught."
    )
    assert not [value for value in strings_in(body) if ended_text[:FRAGMENT] in value], (
        "The held text from the section the lead taught is in their log."
    )


def test_a_lead_deciding_on_a_comment_from_a_section_they_taught_gets_the_governed_404(
    lead_review: LeadReviewWorld, application_session: Any
) -> None:
    """The leader door: 404 with the governed sentence, the not-found body, and no row.

    **The mutation this kills:** the leader door checking current instructor
    grants only, so it writes the ended section's comment as `LEAD_FACULTY`.
    **The control:** the same lead's exclusion of the sibling section's comment
    is accepted, which also catches a course-keyed rule.
    """
    review = lead_review
    reader = review.lead
    taught_then_ended(review, reader, LEADS_ENDED_COHORT, application_session)
    in_ended = a_held_harmful(review, "E6-09 the lead taught this section", LEADS_ENDED_COHORT)
    in_canary = a_held_harmful(review, "E6-09 the lead may decide this", LEADS_CANARY_COHORT)

    before = review.rows_of(in_ended)
    refused = review.decide(reader, in_ended, EXCLUDE)
    assert refused.status_code == NOT_IN_QUEUE, (
        f"The lead's exclusion of a held comment from section "
        f"{review.code_of(LEADS_ENDED_COHORT)}, which they taught until the roster ended the "
        f"grant, was answered {refused.status_code}, not {NOT_IN_QUEUE}. Body begins "
        f"{refused.text[:400]!r}."
    )
    lead_sentence_of(refused, "The refusal of a comment from a section the lead taught")
    assert review.rows_of(in_ended) == before, "A refused decision on it wrote a row."
    nothing = review.decide(reader, uuid4(), EXCLUDE)
    assert (nothing.status_code, nothing.text) == (refused.status_code, refused.text), (
        f"An id nothing holds was answered {nothing.status_code} {nothing.text[:200]!r} and the "
        f"taught section's comment {refused.status_code} {refused.text[:200]!r}; the same 404."
    )
    accepted = review.decide(reader, in_canary, EXCLUDE)
    assert is_success(accepted.status_code), (
        f"The control: the lead's exclusion of the sibling section's comment was answered "
        f"{accepted.status_code}, so the refusal above may be a door that refuses everything."
    )
