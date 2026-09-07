"""E4-03 criterion 6 — what `report_response_counts` counts, and when it moves.

The view returns `(section_id, week_id, responses, valid_responses)`: how many
responses a section-week holds, and how many of them are valid under SPEC §3.3.
The rates themselves are E4-07's — "the view exposes counts and the service
divides", which is what keeps a division-by-zero rule in one reviewable place —
so what is asserted here is the two numerators the ticket's own §3.3 sentence is
built from.

**Criterion 6 is the one that has a moving part**: "The validity rate reads each
response's current validity verdict, so an asynchronous reclassification changes
it — asserted by adding a classification row, never editing one." SPEC §3.3 makes
that a real sequence rather than a hypothetical: a comment accepted under the
fail-open floor is classified later, and "a later classification that refuses it
lowers the §3.4 participation score for that week, including where the week's
score has already been posted". The same later verdict has to reach this report.

So the second test below walks the whole path: it appends a `classification` row
— the table is append-only under ADR 0055, so a later verdict *is* a new row —
runs `app/services/validity.py`'s own recompute, checks that the column the
service maintains actually moved, and only then reads the view. Three separate
readings, because each of them fails differently: a suite that only read the view
could not tell "the view ignores validity" from "the classification never took
effect", and repairing the wrong one of those is how a broken guard gets shipped
green.

**`response.is_valid` is never written by this suite.** E4-03's work order
settles that the column is maintained by the validity service and read by the
view, so a test that set it directly would be checking that a view can read a
value the test put there (`docs/MISTAKES.md` entry 30) — and would stay green
against a validity service that had stopped maintaining it at all.
"""

from decimal import Decimal

import pytest
from fixtures.grading import NONSENSE
from fixtures.report_views import (
    A_COMMENT,
    A_LATER_VERDICT,
    SECOND_COHORT,
    ReportWorld,
)

pytestmark = pytest.mark.integration

INSTRUCTOR_RATING = 1
INSTRUCTOR_COMMENT = 2
COURSE_RATING = 3
COURSE_COMMENT = 4
WORKLOAD = 5

THE_WEEK = 7
ANOTHER_WEEK = 8

# A submission that answers all five of SPEC §3.2's questions, with both ratings
# above the "required if ≤ 2" threshold so each comment is optional and the two
# verdicts are the only thing that can make the response invalid.
A_COMPLETE_SUBMISSION = {
    INSTRUCTOR_RATING: Decimal("4"),
    INSTRUCTOR_COMMENT: A_COMMENT,
    COURSE_RATING: Decimal("4"),
    COURSE_COMMENT: A_COMMENT,
    WORKLOAD: Decimal("6.5"),
}

RESPONDENTS = 3


def test_the_counts_are_this_sections_responses_for_this_week_and_no_others(
    report_world: ReportWorld,
) -> None:
    """One row per section-week, counting the responses submitted into it.

    Three students submit into the week under test; a fourth submits into the same
    section's next week, and a fifth into another section's copy of the same week.
    All three rows are asserted, so a leak is visible from whichever side it
    happened on.

    **The mutation it exists to survive**: `section_id` or `week_id` dropped from
    the `GROUP BY`, which turns every section-week into the same number — a
    response rate computed against the section's own enrolment at E4-07 would then
    read as several hundred per cent, or as one section's participation shown on
    another's page.
    **The near miss it tolerates**: nothing about validity, which is the next
    test's subject; every response here is left with whatever verdicts its
    comments were given.
    """
    world = report_world.build()
    world.section(SECOND_COHORT)

    for index in range(RESPONDENTS):
        student = world.student(f"e4-03-counted-{index}")
        world.respond(student, term_week=THE_WEEK, answers=A_COMPLETE_SUBMISSION)
    next_week = world.student("e4-03-next-week")
    world.respond(next_week, term_week=ANOTHER_WEEK, answers=A_COMPLETE_SUBMISSION)
    other_section = world.student("e4-03-other-section", cohorts=(SECOND_COHORT,))
    world.respond(
        other_section, term_week=THE_WEEK, cohort=SECOND_COHORT, answers=A_COMPLETE_SUBMISSION
    )

    row = world.counts(term_week=THE_WEEK)
    assert row is not None and row["responses"] == RESPONDENTS, (
        f"`report_response_counts` says {row} for the section-week {RESPONDENTS} students "
        "submitted into. One more response exists in the same section's next term week and one in "
        "another section's copy of this week; neither belongs to this row."
    )

    later = world.counts(term_week=ANOTHER_WEEK)
    assert later is not None and later["responses"] == 1, (
        f"`report_response_counts` says {later} for the section's next term week, which holds one "
        f"response. If it holds {RESPONDENTS + 1}, the week is not part of the view's key."
    )

    elsewhere = world.counts(term_week=THE_WEEK, cohort=SECOND_COHORT)
    assert elsewhere is not None and elsewhere["responses"] == 1, (
        f"`report_response_counts` says {elsewhere} for the other section's copy of the same term "
        "week, which holds one response. If it holds the other section's as well, the section is "
        "not part of the view's key."
    )


def test_a_later_classification_that_refuses_a_comment_lowers_the_valid_count(
    report_world: ReportWorld,
) -> None:
    """Criterion 6: the count follows each response's **current** verdict.

    Three students submit complete responses whose comments are classified
    `substantive`. A later `classification` row — appended, never edited — refuses
    one student's instructor comment as `nonsense`, and the validity service is
    asked to recompute that response. The week still holds three responses and now
    holds two valid ones.

    **The three readings, and why each is separate.** The premise is that the
    service moved `response.is_valid`; the subject is that the view's
    `valid_responses` moved with it; and the control is that `responses` did not,
    because a refused comment costs the *validity* rate and never the response
    rate (§3.3). A single assertion over the view could be satisfied by a view
    that counts something else entirely, and a failure would not say which of the
    two halves broke.

    **The mutation it exists to survive**: `count(*) FILTER (WHERE is_valid)`
    written as `count(*)`, which answers three both times; the filter inverted,
    which answers one; and `valid_responses` computed from the `classification`
    rows directly with no ordering, which reports the *first* verdict and so never
    moves at all — the last of those being the exact defect §3.3's fail-open path
    creates, since every floored comment starts out accepted.
    **The near miss it tolerates**: the three responses are otherwise identical,
    so nothing here can pass by counting a shape of submission rather than a
    verdict.
    """
    world = report_world.build()
    submitted = []
    for index in range(RESPONDENTS):
        student = world.student(f"e4-03-validity-{index}")
        submitted.append(world.respond(student, term_week=THE_WEEK, answers=A_COMPLETE_SUBMISSION))
    for response, _answers in submitted:
        world.recompute(response)

    before = world.counts(term_week=THE_WEEK)
    assert before is not None and (before["responses"], before["valid_responses"]) == (
        RESPONDENTS,
        RESPONDENTS,
    ), (
        f"`report_response_counts` says {before} before anything is reclassified. All "
        f"{RESPONDENTS} responses answer every question and every comment is classified "
        "`substantive`, so all of them are valid under SPEC §3.3 — and unless they start valid, "
        "the fall asserted below could be a count that was already wrong."
    )

    refused, answers = submitted[0]
    world.classify(
        answers[INSTRUCTOR_COMMENT],
        NONSENSE,
        classified_at=world.closes_at(THE_WEEK) + A_LATER_VERDICT,
    )
    world.recompute(refused)

    assert world.stored_validity(refused) is False, (
        "The reclassified response's `is_valid` is still true after a `nonsense` verdict was "
        "appended for its comment and `app/services/validity.py`'s recompute was run over it. "
        "That is the premise of this test rather than its subject: SPEC §3.3 makes a "
        "nonsense-flagged response one that reduces the validity rate, and E4-03's work order "
        "settles that the report reads the column this service maintains. Until this moves, the "
        "view has nothing to follow."
    )

    after = world.counts(term_week=THE_WEEK)
    assert after is not None and after["valid_responses"] == RESPONDENTS - 1, (
        f"`report_response_counts` says {after} after one of {RESPONDENTS} responses was "
        "reclassified as invalid. `valid_responses` has to follow each response's current verdict "
        "— SPEC §3.3's validity rate is 'valid responses ÷ responses', and §3.3's own fail-open "
        "path means a comment accepted at submit time can be refused afterwards, including after "
        "the week has been reported. A count that did not move is a report showing a week as "
        "wholly valid when it is not."
    )
    assert after["responses"] == RESPONDENTS, (
        f"`report_response_counts` says {after}: the reclassification changed `responses` as well. "
        "A refused comment costs the validity rate and never the response rate — the student did "
        "submit — so the denominator SPEC §3.3 divides by is unchanged by anything a classifier "
        "later says."
    )
