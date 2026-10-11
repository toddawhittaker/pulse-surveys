"""No threat or self-harm comment reaches leadership — ticket E6-05, criteria 4 and 9.

> 4. A threat or self-harm comment appears in neither the queue nor the log, at
>    any threshold. Invariant-marked.
> 9. One copy of the Care exclusion. The queue read selects from
>    `public.report_comment` …

SPEC §6.2: a threat or self-harm comment is "suppressed from all instructor and
leadership views", and §5.2: it "bypass[es] this flow entirely". Work order
decision 2 makes view v004 the one place that exclusion lives; the queue gets no
Python copy of it.

**The discriminating case for decision 2 is a comment whose verdicts ran
threat, then harmful.** v004 refuses a comment if *any* of its moderation
verdicts, ever, is Care-class. The later harmful verdict leaves a
`FLAGGED_COLLAPSED` row and a harmful classification on the comment, which is
exactly what the queue joins on — so a queue that rebuilt the exclusion from the
*latest* verdict, or that read the flag rows and classifications without going
through v004, carries it. Only the view's rule keeps it out.

**Denial, not absence.** Every case reads a queued harmful comment of the same
course in the same request (the canary, `docs/MISTAKES.md` entry 3), and the lead's
decision on the Care-class comment is the work order's 404 with its governed
sentence and no row.

Criterion 9's grant half — `pulse_app` gains no grant — is
`tests/integration/test_identity_grants.py`'s, which pins the role's whole grant
set; nothing here restates it.

**Which failure a red is, before E6-05 lands.** `lead_routes` fails naming the
routes — a FAILED, never an ERROR (`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import STORED_EXCLUDED, STORED_FLAGGED
from fixtures.lead_review import (
    AS_INSTRUCTOR,
    EXCLUDE,
    LOG_REASON,
    NOT_IN_QUEUE,
    LeadReviewWorld,
    lead_sentence_of,
)
from fixtures.moderation import HARMFUL, SELF_HARM, THREAT
from fixtures.report_api import FIRST_HELD_WEEK, FULL_WEEK, TAUGHT_COHORT, strings_in
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# Each case: the verdicts routed, in order, and the week the comment sits in.
# Course week 1's instructor stream is at the threshold (shown); course week 3's
# course stream is below it (held). "At any threshold" is both.
CARE_CASES = {
    "threat-in-a-shown-week": ((THREAT,), FULL_WEEK, INSTRUCTOR_STREAM),
    "self-harm-in-a-held-week": ((SELF_HARM,), FIRST_HELD_WEEK, COURSE_STREAM),
    "threat-then-harmful-in-a-held-week": ((THREAT, HARMFUL), FIRST_HELD_WEEK, COURSE_STREAM),
    "self-harm-then-harmful-in-a-shown-week": ((SELF_HARM, HARMFUL), FULL_WEEK, INSTRUCTOR_STREAM),
}


def a_canary(review: LeadReviewWorld, case: str) -> Any:
    return review.plant(
        course_week=FIRST_HELD_WEEK,
        stream=COURSE_STREAM,
        text=f"E6-05 the harmful canary queued beside the {case} comment",
        verdict=HARMFUL,
        cohort=TAUGHT_COHORT,
    )


@pytest.mark.parametrize("case", sorted(CARE_CASES))
def test_a_care_class_comment_is_not_in_the_queue_and_a_decision_on_it_is_refused(
    case: str, lead_review: LeadReviewWorld
) -> None:
    """Criterion 4 over the queue and the door, at both sides of the threshold.

    **The mutations this kill:** a queue that reads `moderation_state` and
    `classification` without v004 (the threat-then-harmful comment is flagged and
    harmful, and is queued); a Python copy of the Care rule keyed on the latest
    verdict (same red); a door that checks only the latest verdict before writing
    (the decision is accepted). **The near miss:** a queue correct for a comment
    whose only verdict is Care-class but wrong for one with a later verdict — the
    first two cases pass it and the last two do not.
    """
    review = lead_review
    verdicts, week, stream = CARE_CASES[case]
    canary = a_canary(review, case)
    text = f"E6-05 a Care-class comment, {case}, that no leadership reader may ever see"
    comment = review.plant(
        course_week=week, stream=stream, text=text, verdict=verdicts, cohort=TAUGHT_COHORT
    )
    if HARMFUL in verdicts:
        states = [row["state"] for row in review.rows_of(comment)]
        assert STORED_FLAGGED in states, (
            f"The {case} comment carries no `{STORED_FLAGGED}` row ({states}), so it is not the "
            "flagged, harmful-verdicted comment a queue without v004 would carry; this case would "
            "not discriminate decision 2."
        )

    answered = review.queue(review.lead)
    queued = {str(item.get("answer_id")) for item in review.items(review.lead)}
    assert str(canary) in queued, "The canary: the lead's queue lacks the harmful comment."
    assert str(comment) not in queued, (
        f"The lead's queue carries the {case} comment. SPEC §6.2 suppresses a threat or self-harm "
        "comment from every leadership view; decision 2 makes v004 the one place that holds."
    )
    assert not [
        value for value in strings_in(answered.json()) if text[:40] in value
    ], f"The queue's body carries the {case} comment's text under some member other than an item."

    before = review.rows_of(comment)
    refused = review.decide(review.lead, comment, EXCLUDE)
    assert refused.status_code == NOT_IN_QUEUE, (
        f"The lead's exclusion of the {case} comment was answered {refused.status_code}, not "
        f"{NOT_IN_QUEUE}. Body begins {refused.text[:400]!r}."
    )
    lead_sentence_of(refused, f"The refusal of the {case} comment")
    assert (
        review.rows_of(comment) == before
    ), f"A refused decision on the {case} comment wrote a row."


def test_a_care_class_comment_is_not_in_the_log_even_with_a_decision_row(
    lead_review: LeadReviewWorld,
) -> None:
    """Criterion 4 over the log: a decision row on a Care-class comment is not a log row.

    A threat comment in a shown week and a self-harm comment in a held week each
    carry an `EXCLUDED` row with a decider and a reason — rows no door here can
    write, planted so that the log has something to leak. A harmful comment's
    exclusion in the same course is the canary.

    **The mutation this kills:** a log over every `moderation_state` row with a
    decider, joined to the answer rather than through the view that holds the
    Care rule — it shows both rows, and a row's excerpt is the comment's text.
    **The near miss:** a log that drops the excerpt for a Care-class comment but
    keeps its row (the date, the section and the reason still say a comment there
    was decided on) — the row is required absent by its reason, not only its text.
    """
    review = lead_review
    canary = review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text="E6-05 the harmful canary whose exclusion is logged",
        verdict=HARMFUL,
        cohort=TAUGHT_COHORT,
    )
    canary_reason = "E6-05 the canary's reason: a personal attack on the instructor"
    review.plant_decision(
        canary,
        STORED_EXCLUDED,
        decided_by=review.door.person_id,
        decided_as=AS_INSTRUCTOR,
        reason=canary_reason,
    )
    planted: dict[str, tuple[str, str]] = {}
    care_cases = (
        (THREAT, FULL_WEEK, INSTRUCTOR_STREAM),
        (SELF_HARM, FIRST_HELD_WEEK, COURSE_STREAM),
    )
    for verdict, week, stream in care_cases:
        text = f"E6-05 a {verdict} comment whose exclusion row must never reach the log"
        comment = review.plant(
            course_week=week, stream=stream, text=text, verdict=verdict, cohort=TAUGHT_COHORT
        )
        reason = f"E6-05 the {verdict} comment's planted reason, which must not be logged"
        review.plant_decision(
            comment,
            STORED_EXCLUDED,
            decided_by=review.door.a_person(),
            decided_as=AS_INSTRUCTOR,
            reason=reason,
        )
        planted[verdict] = (text, reason)

    answered = review.log(review.lead)
    rows = review.log_rows(review.lead)
    reasons = [row.get(LOG_REASON) for row in rows]
    assert canary_reason in reasons, "The canary: the lead's log lacks the harmful exclusion."
    body = strings_in(answered.json())
    for verdict, (text, reason) in planted.items():
        assert reason not in reasons, (
            f"The lead's exclusion log carries the row of a {verdict} comment. SPEC §6.2: a "
            "Care-class comment is suppressed from all leadership views, its decisions included."
        )
        assert not [
            value for value in body if text[:40] in value
        ], f"The log's body carries the {verdict} comment's text."
