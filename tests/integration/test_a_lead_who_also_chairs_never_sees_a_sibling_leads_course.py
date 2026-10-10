"""A lead who also chairs the department sees no course another lead leads — E6-09, done-when 6.

> A person leads course A and chairs the department holding course B, which
> another person leads. B's comment is absent from the queue and the log, and a
> decision on it gets 404 and writes no row. A's comment and an unled course's
> comment are present.

SPEC §4.1 item 2: a Lead Faculty assignment never grants a sibling lead's course.
SPEC §2.1 and §5.2: a chair reviews "the courses of their department that have no
lead". One person holding both grants is the case neither single-grant test
reaches (`docs/MISTAKES.md` entries 35 and 53: the guard is defeated one level
out, by the second currency a privilege is held in). A union written as "the
courses I lead, plus my department's courses" — rather than "plus my department's
*unled* courses" — hands this person every sibling lead's course.

**The world** is `tests/fixtures/lead_review.py`'s: the own course (A) led by
`lead`, the sibling course (B) led by `sibling_lead`, and the unmapped course
falling to the chair — all in one department. `lead` is given a `CHAIR` grant on
that department, read back before anything else. **Two canaries in every read**:
A's comment (the lead grant) and the unled course's (the chair grant), so a read
that answered nothing, or answered for only one of the two grants, is red
(`docs/MISTAKES.md` entry 3). B's comment is shown to be in the sibling lead's own
queue, so its absence here is about the grant and not about a comment nobody sees.

**Which failure a red is.** The rule may hold today; this is the §4.1 assertion the
boundary review found missing, and the mutation below is what shows it can go red.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.instructor_decisions import STORED_EXCLUDED
from fixtures.lead_review import (
    AS_INSTRUCTOR,
    CHAIR_ROLE,
    EXCLUDE,
    LOG_REASON,
    NOT_IN_QUEUE,
    SIBLING_COHORT,
    UNMAPPED_COHORT,
    LeadReviewWorld,
    Reader,
    is_success,
    lead_sentence_of,
    the_list_in,
)
from fixtures.moderation import HARMFUL
from fixtures.report_api import FIRST_HELD_WEEK, FULL_WEEK, TAUGHT_COHORT, strings_in
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

FRAGMENT = 40

OWN_REASON = "E6-09 lead and chair: excluded in the course they lead"
UNLED_REASON = "E6-09 lead and chair: excluded in their department's unled course"
SIBLING_REASON = "E6-09 lead and chair: excluded in the course another lead leads"
SIBLING_LOGGED_TEXT = "E6-09 a harmful comment in the sibling lead's course, logged"


def the_lead_also_chairs(review: LeadReviewWorld) -> Reader:
    """`lead`, given a `CHAIR` grant on the department; the grant is read back first."""
    reader = review.lead
    before = len(review.graph.assignments_of(reader.person_id))
    review.graph.assign(CHAIR_ROLE, scope=review.department, person=reader.person_id)
    review.rows.commit()
    after = len(review.graph.assignments_of(reader.person_id))
    assert after == before + 1, (
        f"The lead held {before} assignments and holds {after} after a chair grant on the "
        "department; without both hats this is the plain sibling test."
    )
    return reader


def a_held_harmful(review: LeadReviewWorld, text_: str, cohort: str) -> Any:
    return review.plant(
        course_week=FIRST_HELD_WEEK,
        stream=COURSE_STREAM,
        text=text_,
        verdict=HARMFUL,
        cohort=cohort,
    )


def test_a_lead_who_also_chairs_never_sees_a_sibling_leads_comment_in_the_queue(
    lead_review: LeadReviewWorld,
) -> None:
    """The queue: A's and the unled course's held comments present, B's absent.

    **The mutation this kills:** the chair half of the reader's grant taken as the
    whole department's courses whenever the reader also leads one (or the two
    grants unioned before the unled filter is applied), which puts B in the
    queue. **The near miss:** a chair grant dropped for a person who also leads —
    the unled course's canary is lost.
    """
    review = lead_review
    reader = the_lead_also_chairs(review)
    own = a_held_harmful(review, "E6-09 lead and chair: own course held comment", TAUGHT_COHORT)
    unled = a_held_harmful(review, "E6-09 lead and chair: unled course held", UNMAPPED_COHORT)
    sibling_text = "E6-09 lead and chair: the sibling lead's course held comment"
    sibling = a_held_harmful(review, sibling_text, SIBLING_COHORT)

    assert str(sibling) in review.queued_ids(review.sibling_lead), (
        "The sibling lead's own queue lacks the sibling course's comment, so its absence below "
        "would prove nothing about the grant."
    )
    answered = review.queue(reader)
    assert answered.status_code == 200, f"The queue answered {answered.status_code}."
    body = answered.json()
    queued = {str(item.get("answer_id")) for item in the_list_in(body, "The queue read")}
    assert str(own) in queued and str(unled) in queued, (
        f"The canaries: the lead-and-chair's queue carries {sorted(queued)}, without "
        f"{'their led course' if str(own) not in queued else 'their unled course'}. Both grants "
        "count; a read missing either is not the read this test is about."
    )
    assert str(sibling) not in queued, (
        "The lead-and-chair's queue carries a comment from the course another lead leads. SPEC "
        "§4.1 item 2: a lead's grant never reaches a sibling lead's course, and a chair's reaches "
        "only the department's courses with no lead."
    )
    assert not [value for value in strings_in(body) if sibling_text[:FRAGMENT] in value], (
        "The sibling course's held comment text is in the lead-and-chair's queue."
    )


def test_a_lead_who_also_chairs_never_sees_a_sibling_leads_row_in_the_log(
    lead_review: LeadReviewWorld,
) -> None:
    """The log: A's and the unled course's rows present, B's absent.

    **The mutation this kills:** the log scoped by the union of the reader's
    grants with the chair half widened to the department. **The near miss:** the
    lead half or the chair half dropped (a canary is lost).
    """
    review = lead_review
    reader = the_lead_also_chairs(review)
    for text_, cohort, reason in (
        ("E6-09 lead and chair: own course comment, logged", TAUGHT_COHORT, OWN_REASON),
        ("E6-09 lead and chair: unled course comment, logged", UNMAPPED_COHORT, UNLED_REASON),
        (SIBLING_LOGGED_TEXT, SIBLING_COHORT, SIBLING_REASON),
    ):
        comment = review.plant(
            course_week=FULL_WEEK,
            stream=INSTRUCTOR_STREAM,
            text=text_,
            verdict=HARMFUL,
            cohort=cohort,
        )
        review.plant_decision(
            comment,
            STORED_EXCLUDED,
            decided_by=review.door.a_person(),
            decided_as=AS_INSTRUCTOR,
            reason=reason,
        )

    siblings = [row.get(LOG_REASON) for row in review.log_rows(review.sibling_lead)]
    assert SIBLING_REASON in siblings, (
        "The sibling lead's own log lacks the sibling course's row, so its absence below would "
        "prove nothing."
    )
    answered = review.log(reader)
    assert answered.status_code == 200, f"The log answered {answered.status_code}."
    reasons = [row.get(LOG_REASON) for row in review.log_rows(reader)]
    assert OWN_REASON in reasons and UNLED_REASON in reasons, (
        f"The canaries: the lead-and-chair's log carries the reasons {reasons}; it must carry both "
        f"{OWN_REASON!r} (their led course) and {UNLED_REASON!r} (their unled course)."
    )
    assert SIBLING_REASON not in reasons, (
        "The lead-and-chair's log carries a row from the course another lead leads. SPEC §4.1 "
        "item 2 and §5.2: a leader reads the log over their own grant."
    )
    assert not [
        value for value in strings_in(answered.json()) if SIBLING_LOGGED_TEXT[:FRAGMENT] in value
    ], "The sibling course's comment text is in the lead-and-chair's log."


def test_a_lead_who_also_chairs_is_refused_a_decision_on_a_sibling_leads_comment(
    lead_review: LeadReviewWorld,
) -> None:
    """The door: 404 with the governed sentence and no row for B; A's and the unled accepted.

    **The mutation this kills:** the leader door admitting any comment in the
    reader's chaired department, which writes B's comment under the reader's name.
    **The controls:** the same reader's exclusions of A's comment and of the unled
    course's comment are accepted, and an id nothing holds gets the same answer B
    gets.
    """
    review = lead_review
    reader = the_lead_also_chairs(review)
    own = a_held_harmful(review, "E6-09 lead and chair: own, decidable", TAUGHT_COHORT)
    unled = a_held_harmful(review, "E6-09 lead and chair: unled, decidable", UNMAPPED_COHORT)
    sibling = a_held_harmful(review, "E6-09 lead and chair: the sibling's", SIBLING_COHORT)

    before = review.rows_of(sibling)
    refused = review.decide(reader, sibling, EXCLUDE)
    assert refused.status_code == NOT_IN_QUEUE, (
        f"The lead-and-chair's exclusion of a sibling lead's comment was answered "
        f"{refused.status_code}, not {NOT_IN_QUEUE}. Body begins {refused.text[:400]!r}."
    )
    lead_sentence_of(refused, "The refusal of a sibling lead's comment to a lead who chairs")
    assert review.rows_of(sibling) == before, "A refused decision on the sibling's comment wrote."
    nothing = review.decide(reader, uuid4(), EXCLUDE)
    assert (nothing.status_code, nothing.text) == (refused.status_code, refused.text), (
        f"An id nothing holds was answered {nothing.status_code} {nothing.text[:200]!r} and the "
        f"sibling's comment {refused.status_code} {refused.text[:200]!r}; the same 404."
    )
    for comment, what in ((own, "their led course"), (unled, "their department's unled course")):
        accepted = review.decide(reader, comment, EXCLUDE)
        assert is_success(accepted.status_code), (
            f"The control: the lead-and-chair's exclusion of a comment in {what} was answered "
            f"{accepted.status_code}, so the refusal above may be a door that refuses everything."
        )
