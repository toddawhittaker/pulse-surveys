"""SPEC §4.1 item 2 over the review queue and the exclusion log — ticket E6-05, criterion 3.

> A Lead Faculty member never sees a sibling lead's course in the queue or the
> log, and a decision on a sibling's comment is refused and writes no row.
> Invariant-marked, with the reader's own course in the same world as the canary.

**The canary is the reader's own course, read in the same request.** Every
absence below sits beside a presence: the lead's queue carries their own course's
comment and their log carries their own course's row, so a read that answered
nothing is red on the canary (`docs/MISTAKES.md` entry 3). **The refusal is
asserted as a refusal**: the decision on the sibling's comment is the work order's
404 with its one governed sentence, the same body a random id gets, and no row.
**And the sibling's comment is shown to be queueable**: the sibling lead's own
queue carries it, so its absence from this lead's queue is about the grant, not
about a comment nobody could see.

**One level out (`docs/MISTAKES.md` entries 35 and 53).** `resolve_scope` unions
instructor grants with leadership ones, and work order decision 3 adds a
leadership-only own-grant function for exactly that reason. The last test gives
the lead a second hat — an `INSTRUCTOR` assignment on the sibling course's
section — and requires the queue and the log to stay inside the lead grant.

Marked `invariant`: CI runs these in the isolated §4.1 pass, which treats a skip
as a failure.

**Which failure a red is, before E6-05 lands.** `lead_routes` fails naming the
routes — a FAILED, never an ERROR (`docs/MISTAKES.md` entry 44).
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.instructor_decisions import STORED_EXCLUDED
from fixtures.lead_review import (
    AS_INSTRUCTOR,
    EXCLUDE,
    LOG_REASON,
    NOT_IN_QUEUE,
    SIBLING_COHORT,
    LeadReviewWorld,
    lead_sentence_of,
)
from fixtures.moderation import HARMFUL
from fixtures.report_api import FIRST_HELD_WEEK, FULL_WEEK, INSTRUCTOR_ROLE, TAUGHT_COHORT
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

OWN_REASON = "E6-05 own course: excluded for naming the instructor's family member"
SIBLING_REASON = "E6-05 sibling course: excluded for an attack on the sibling's instructor"


def a_held_harmful(review: LeadReviewWorld, text: str, cohort: str) -> Any:
    return review.plant(
        course_week=FIRST_HELD_WEEK, stream=COURSE_STREAM, text=text, verdict=HARMFUL, cohort=cohort
    )


def a_logged_exclusion(review: LeadReviewWorld, text: str, cohort: str, reason: str) -> Any:
    """A harmful comment in a shown week, excluded by somebody, with a reason that names it."""
    comment = review.plant(
        course_week=FULL_WEEK, stream=INSTRUCTOR_STREAM, text=text, verdict=HARMFUL, cohort=cohort
    )
    review.plant_decision(
        comment,
        STORED_EXCLUDED,
        decided_by=review.door.a_person(),
        decided_as=AS_INSTRUCTOR,
        reason=reason,
    )
    return comment


def test_a_lead_never_sees_a_sibling_leads_comment_in_the_queue(
    lead_review: LeadReviewWorld,
) -> None:
    """The queue half: own comment present, sibling's absent, and the sibling's is real.

    **The mutation this kills:** the queue scoped to the prefix (or the
    department) above the led course, which hands every sibling lead's course to
    every lead under it. **The near miss:** a queue scoped correctly for the
    sibling lead but not for this one — both leads' queues are read.
    """
    review = lead_review
    own = a_held_harmful(review, "E6-05 the lead's own held harmful comment", TAUGHT_COHORT)
    sibling = a_held_harmful(review, "E6-05 the sibling course's held harmful", SIBLING_COHORT)

    leads = review.queued_ids(review.lead)
    assert str(own) in leads, "The canary: the lead's queue lacks their own course's comment."
    assert str(sibling) in review.queued_ids(review.sibling_lead), (
        "The sibling lead's own queue lacks the sibling course's comment, so its absence from this "
        "lead's queue would prove nothing about the grant."
    )
    assert str(sibling) not in leads, (
        "The lead's queue carries a comment from a sibling lead's course. SPEC §4.1 item 2: a Lead "
        "Faculty assignment never grants sibling leads' courses."
    )


def test_a_decision_on_a_sibling_leads_comment_is_refused_and_writes_no_row(
    lead_review: LeadReviewWorld,
) -> None:
    """The write half: 404 with the governed sentence, the same answer as an id nothing holds.

    **The mutations this kill:** a door that checks only that the comment is
    flagged (it writes the sibling's comment as `LEAD_FACULTY`); a door whose
    refusal differs from the not-found one (a 403 here says "this exists, and is
    not yours" — the existence leak decision 1 forbids). **The control:** the
    same lead's exclusion of their own course's comment is accepted.
    """
    review = lead_review
    own = a_held_harmful(review, "E6-05 the lead's own comment, decidable", TAUGHT_COHORT)
    sibling = a_held_harmful(review, "E6-05 the sibling's comment, not theirs", SIBLING_COHORT)

    before = review.rows_of(sibling)
    refused = review.decide(review.lead, sibling, EXCLUDE)
    assert refused.status_code == NOT_IN_QUEUE, (
        f"The lead's exclusion of a sibling lead's comment was answered {refused.status_code}, not "
        f"{NOT_IN_QUEUE}. Body begins {refused.text[:400]!r}."
    )
    lead_sentence_of(refused, "The refusal of a sibling's comment")
    assert (
        review.rows_of(sibling) == before
    ), "A refused decision on a sibling's comment wrote a row."

    nothing = review.decide(review.lead, uuid4(), EXCLUDE)
    assert (nothing.status_code, nothing.text) == (refused.status_code, refused.text), (
        f"An id nothing holds was answered {nothing.status_code} {nothing.text[:200]!r} and the "
        f"sibling's comment {refused.status_code} {refused.text[:200]!r}. Decision 1: no existence "
        "leak, so the two answers are the same."
    )

    accepted = review.decide(review.lead, own, EXCLUDE)
    assert 200 <= accepted.status_code < 300, (
        f"The control: the lead's exclusion of their own course's comment was answered "
        f"{accepted.status_code}, so the refusal above may be a door that refuses everything."
    )


def test_a_lead_never_sees_a_sibling_leads_row_in_the_log(lead_review: LeadReviewWorld) -> None:
    """The log half: own row present, sibling's absent, and the sibling's is in the sibling's log.

    **The mutation this kills:** the log scoped wider than the reader's own grant
    — the prefix, the department, or every row there is.
    """
    review = lead_review
    a_logged_exclusion(review, "E6-05 own course comment, logged", TAUGHT_COHORT, OWN_REASON)
    a_logged_exclusion(review, "E6-05 sibling course comment", SIBLING_COHORT, SIBLING_REASON)

    reasons = [row.get(LOG_REASON) for row in review.log_rows(review.lead)]
    siblings = [row.get(LOG_REASON) for row in review.log_rows(review.sibling_lead)]
    assert OWN_REASON in reasons, "The canary: the lead's log lacks their own course's exclusion."
    assert SIBLING_REASON in siblings, (
        "The sibling lead's own log lacks the sibling course's exclusion, so its absence below "
        "would prove nothing."
    )
    assert (
        SIBLING_REASON not in reasons
    ), "The lead's exclusion log carries a sibling lead's course's row. SPEC §4.1 item 2."


def test_a_lead_who_also_teaches_a_sibling_section_still_sees_only_their_led_course(
    lead_review: LeadReviewWorld,
) -> None:
    """One level out: a second hat, an `INSTRUCTOR` grant on the sibling course's section.

    Work order decision 3's function returns the reader's *leadership-role*
    grants. `resolve_scope` would union this instructor grant in, and the
    queue and log would then reach the sibling's course through it.

    **The mutation this kills:** the queue or the log scoped with `resolve_scope`
    (or any union over every assignment the person holds) rather than the
    leadership-only own grant. **The near miss:** the second hat dropped from the
    world — the assignment is read back first, so a world in which it did not
    land is red as a broken premise, not green.
    """
    review = lead_review
    sibling_section = review.world.section_id(SIBLING_COHORT)
    review.graph.assign(INSTRUCTOR_ROLE, scope=sibling_section, person=review.lead.person_id)
    review.rows.commit()
    held = review.graph.assignments_of(review.lead.person_id)
    assert len(held) == 2, (
        f"The lead holds {len(held)} assignments; this test gave them a lead grant and an "
        "instructor grant, and without both it is the plain sibling test again."
    )

    own = a_held_harmful(review, "E6-05 two hats: the led course's held comment", TAUGHT_COHORT)
    sibling = a_held_harmful(review, "E6-05 two hats: the taught section's held", SIBLING_COHORT)
    a_logged_exclusion(review, "E6-05 two hats: own course row", TAUGHT_COHORT, OWN_REASON)
    a_logged_exclusion(review, "E6-05 two hats: taught sibling row", SIBLING_COHORT, SIBLING_REASON)

    queued = review.queued_ids(review.lead)
    assert str(own) in queued, "The canary: the two-hat lead's queue lacks their led course."
    assert str(sibling) not in queued, (
        "The two-hat lead's queue carries a comment from the sibling course they teach a section "
        "of. The queue reads the reader's leadership grant only (decision 3); an instructor hat "
        "is the instructor door's business."
    )
    reasons = [row.get(LOG_REASON) for row in review.log_rows(review.lead)]
    assert OWN_REASON in reasons, "The canary: the two-hat lead's log lacks their led course."
    assert (
        SIBLING_REASON not in reasons
    ), "The two-hat lead's log carries a row from the sibling course they teach a section of."
    before = review.rows_of(sibling)
    refused = review.decide(review.lead, sibling, EXCLUDE)
    assert refused.status_code == NOT_IN_QUEUE and review.rows_of(sibling) == before, (
        f"The two-hat lead's exclusion of the sibling course's comment was answered "
        f"{refused.status_code} and the rows went from {before} to {review.rows_of(sibling)}."
    )
