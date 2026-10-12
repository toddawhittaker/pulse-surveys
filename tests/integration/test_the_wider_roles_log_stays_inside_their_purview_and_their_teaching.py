"""The assistant dean's, dean's and vice president's exclusion log, under §4.1 — E9-14 item 5(a).

ADR 0206 gave these three roles the exclusion log over their purview, less every
section they teach or have taught, and no review queue. The E9 boundary
invariant-coverage review found that rule asserted only in an unmarked module
(`test_the_wider_roles_read_the_log_and_policy_over_their_purview.py`), which
CI's isolated §4.1 pass does not run. This module asserts it, marked.

**Rows are found by their section, not their reason.** After E9-14 item 1 a
withheld row carries no reason for these readers, so "the sibling's reason is
not in the log" would hold of a log that leaked the sibling's row whole
(`docs/MISTAKES.md` entry 3). Each row's section label names the section's code
(`test_the_exclusion_log_shows_both_directions_inside_the_readers_grant.py`
asserts it), and the world's sections have distinct codes, so the label says
which section a row is from whatever else is blanked.

**The world** is the lead-review world (`tests/fixtures/lead_review.py`): lead A
leads the own course (sections `F`, taught by the world's instructor, and `Q`);
sibling lead B leads a course of cohort `Y` under the same prefix. The assistant
dean's purview arrives through the supervision graph: lead A's assignment
reports to them, so their purview is A's course and not B's (ADR 0199). The dean
and the vice president reach the whole college.

**Which failure a red is.** These rules exist on the branch this is written
against, so every test is expected **green**; each docstring names the mutation
that turns it red and the near miss that leaves it green.
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import STORED_EXCLUDED
from fixtures.lead_review import (
    AS_LEAD_FACULTY,
    ASSISTANT_DEAN_ROLE,
    EXCERPT_LENGTH,
    LOG_EXCERPT,
    LOG_SECTION_LABEL,
    LeadReviewWorld,
    Reader,
)
from fixtures.moderation import CLEAR, HARMFUL
from fixtures.report_api import (
    FIRST_HELD_WEEK,
    FULL_WEEK,
    TAUGHT_COHORT,
    UNTAUGHT_COHORT,
    strings_in,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

SIBLING_COHORT = "Y"
DEAN_ROLE = "DEAN"
VP_ROLE = "VP_ACADEMICS"
FORBIDDEN = 403
QUEUE = "/leadership/moderation/queue"

# A stream is shown at five distinct commenters (SPEC §4's default threshold);
# one harmful comment and this many clear ones puts a stream above it.
CLEAR_COMMENTERS = 5
FRAGMENT = 40


def an_assistant_dean_over_the_lead(review: LeadReviewWorld) -> Reader:
    reader = review.a_leader(
        "e9-14-5a-assistant-dean", grants=((ASSISTANT_DEAN_ROLE, review.college),)
    )
    (dean_assignment,) = review.graph.assignments_of(reader.person_id)
    (lead_assignment,) = review.graph.assignments_of(review.lead.person_id)
    review.graph.repoint({review.graph.assignment_key: lead_assignment}, dean_assignment)
    review.rows.commit()
    return reader


def a_dean(review: LeadReviewWorld) -> Reader:
    return review.a_leader("e9-14-5a-dean", grants=((DEAN_ROLE, review.college),))


def a_vice_president(review: LeadReviewWorld) -> Reader:
    institution = review.session.execute(
        text("SELECT institution_id FROM college WHERE id = :college"),
        {"college": review.college},
    ).scalar_one()
    return review.a_leader("e9-14-5a-vice-president", grants=((VP_ROLE, institution),))


READERS = {
    "assistant dean": an_assistant_dean_over_the_lead,
    "dean": a_dean,
    "vice president": a_vice_president,
}


def a_shown_exclusion(review: LeadReviewWorld, cohort: str, text_: str) -> None:
    """A harmful comment in course week 1's instructor stream, made shown, excluded by the lead."""
    for index in range(CLEAR_COMMENTERS):
        review.plant(
            course_week=FULL_WEEK,
            stream=INSTRUCTOR_STREAM,
            text=f"E9-14 5(a) a clear comment in the cohort-{cohort} section, {index}",
            verdict=CLEAR,
            cohort=cohort,
        )
    comment = review.plant(
        course_week=FULL_WEEK, stream=INSTRUCTOR_STREAM, text=text_, verdict=HARMFUL, cohort=cohort
    )
    review.plant_decision(
        comment,
        STORED_EXCLUDED,
        decided_by=review.lead.person_id,
        decided_as=AS_LEAD_FACULTY,
        reason=f"E9-14 5(a) the lead's exclusion in the cohort-{cohort} section",
    )


def a_held_exclusion(review: LeadReviewWorld, cohort: str, text_: str) -> None:
    """A harmful comment, the one commenter in course week 3's course stream, excluded by the lead."""
    comment = review.plant(
        course_week=FIRST_HELD_WEEK,
        stream=COURSE_STREAM,
        text=text_,
        verdict=HARMFUL,
        cohort=cohort,
    )
    review.plant_decision(
        comment,
        STORED_EXCLUDED,
        decided_by=review.lead.person_id,
        decided_as=AS_LEAD_FACULTY,
        reason=f"E9-14 5(a) the lead's exclusion of a held comment, cohort {cohort}",
    )


def the_log(review: LeadReviewWorld, reader: Reader, role: str) -> tuple[Any, list[dict[str, Any]]]:
    answered = review.log(reader)
    assert answered.status_code == 200, (
        f"The log answered {answered.status_code} to the {role}. Body begins "
        f"{answered.text[:300]!r}."
    )
    return answered.json(), review.log_rows(reader)


def rows_of(
    review: LeadReviewWorld, rows: list[dict[str, Any]], cohort: str
) -> list[dict[str, Any]]:
    code = review.code_of(cohort)
    return [row for row in rows if code in str(row.get(LOG_SECTION_LABEL))]


def text_in(body: Any, text_: str) -> list[str]:
    return [value for value in strings_in(body) if text_[:FRAGMENT] in value]


# ---------------------------------------------------------------------------
# Nothing outside the purview.
# ---------------------------------------------------------------------------


def test_the_assistant_dean_reads_no_row_and_no_text_from_outside_their_purview(
    lead_review: LeadReviewWorld,
) -> None:
    """Lead A's course in, B's course out: no row of B's section and none of its text.

    B's comment is in a **shown** stream, so its row carries its excerpt for
    any reader whose purview holds it: the dean reads it (the control), which
    makes the assistant dean's empty answer about the purview and not about the
    excerpt rule.

    **The mutations it kills:** the wider-role log read over the college's
    containment rather than the reader's purview; the supervision walk dropped,
    so an assistant dean reads nothing (the own-course twin then fails) or
    everything. **The near miss it spares:** A's sections, present by label.
    """
    review = lead_review
    own_text = "E9-14 5(a) a harmful comment in lead A's course, shown"
    sibling_text = "E9-14 5(a) a harmful comment in sibling lead B's course, shown"
    a_shown_exclusion(review, UNTAUGHT_COHORT, own_text)
    a_shown_exclusion(review, SIBLING_COHORT, sibling_text)
    assistant_dean = an_assistant_dean_over_the_lead(review)
    dean = a_dean(review)

    _dean_body, dean_rows = the_log(review, dean, "dean")
    assert [row.get(LOG_EXCERPT) for row in rows_of(review, dean_rows, SIBLING_COHORT)] == [
        sibling_text[:EXCERPT_LENGTH]
    ], (
        "The control: the dean, whose purview is the college, does not read B's shown row with its "
        f"excerpt; the dean's rows are {dean_rows}."
    )

    body, rows = the_log(review, assistant_dean, "assistant dean")
    own = rows_of(review, rows, UNTAUGHT_COHORT)
    assert [row.get(LOG_EXCERPT) for row in own] == [own_text[:EXCERPT_LENGTH]], (
        f"The present twin: the assistant dean's log carries {own} for lead A's untaught section; "
        "that section is in their purview and its row is shown."
    )
    outside = rows_of(review, rows, SIBLING_COHORT)
    assert outside == [], (
        f"The assistant dean's log carries rows of sibling lead B's section: {outside}. ADR 0206: "
        "the wider roles read the log over their purview."
    )
    assert not text_in(body, sibling_text), "B's comment text is in the assistant dean's log."


# ---------------------------------------------------------------------------
# The held stream stays withheld.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", sorted(READERS))
def test_a_wider_role_reads_no_excerpt_of_a_held_comment(
    lead_review: LeadReviewWorld, role: str
) -> None:
    """A held course-stream comment's row has no excerpt and its text is nowhere; a shown row's has.

    **The mutation it kills:** the wider-role path building its rows without
    the shown set (`report_comments.shown_under_their_week`), so a dean reads
    held text beside a date. **The near miss it spares:** the shown row in the
    same section, whose excerpt is carried.
    """
    review = lead_review
    held_text = "E9-14 5(a) a held harmful comment the wider roles never read"
    shown_text = "E9-14 5(a) a shown harmful comment in the untaught section"
    a_held_exclusion(review, UNTAUGHT_COHORT, held_text)
    a_shown_exclusion(review, UNTAUGHT_COHORT, shown_text)
    reader = READERS[role](review)

    body, rows = the_log(review, reader, role)
    excerpts = [row.get(LOG_EXCERPT) for row in rows_of(review, rows, UNTAUGHT_COHORT)]
    assert shown_text[:EXCERPT_LENGTH] in excerpts, (
        f"The present twin: the {role}'s rows of the untaught section carry the excerpts "
        f"{excerpts}, not the shown comment's."
    )
    assert sorted(excerpts, key=str) == sorted([shown_text[:EXCERPT_LENGTH], None], key=str), (
        f"The {role}'s rows of the untaught section carry the excerpts {excerpts}; the held "
        "comment's row carries none (SPEC §5.2)."
    )
    assert not text_in(body, held_text), f"The held comment's text is in the {role}'s log."


# ---------------------------------------------------------------------------
# No row of a section the reader teaches.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", sorted(READERS))
def test_a_wider_role_who_teaches_a_section_reads_no_row_of_it_by_its_label(
    lead_review: LeadReviewWorld, role: str
) -> None:
    """The reader teaches the taught section: no row names it; the untaught section's row stays.

    **The mutation it kills:** the wider-role log left without the
    taught-or-once-taught filter (ADR 0206: "less every section the reader
    teaches or has taught"), whose row names the section, the date and a
    paraphrase of a comment the reader's own instructor view governs. **The near
    miss it spares:** the filter keyed on the course, which loses the untaught
    section's row too.
    """
    review = lead_review
    taught_text = "E9-14 5(a) a shown harmful comment in the section the reader teaches"
    a_shown_exclusion(review, TAUGHT_COHORT, taught_text)
    a_shown_exclusion(review, UNTAUGHT_COHORT, "E9-14 5(a) the untaught section's twin")
    reader = READERS[role](review)
    review.teaches(reader, TAUGHT_COHORT)

    body, rows = the_log(review, reader, role)
    assert rows_of(
        review, rows, UNTAUGHT_COHORT
    ), f"The present twin: the {role}'s log lost the untaught section's row too: {rows}."
    taught = rows_of(review, rows, TAUGHT_COHORT)
    assert taught == [], (
        f"The {role} teaches section {review.code_of(TAUGHT_COHORT)} and its log carries rows of "
        f"it: {taught}. SPEC §5.2: neither sees rows from a section they teach or have taught."
    )
    assert not text_in(body, taught_text), f"The taught section's text is in the {role}'s log."


# ---------------------------------------------------------------------------
# No review queue.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", sorted(READERS))
def test_a_wider_role_is_refused_the_review_queue(lead_review: LeadReviewWorld, role: str) -> None:
    """The queue answers 403 with its sentence; the same reader's log answers 200 with rows.

    A refusal, asserted as a refusal: an empty queue would pass "no item" for any
    reason at all. **The mutation it kills:** the queue opened to the wider
    roles (ADR 0206 rejected it: §5.2 names the lead and, for an unled course,
    the chair as reviewers). **The near miss it spares:** the log, which these
    roles do read.
    """
    from app.copy.leadership_moderation import NO_REVIEW_GRANT

    review = lead_review
    review.plant(
        course_week=FIRST_HELD_WEEK,
        stream=COURSE_STREAM,
        text="E9-14 5(a) a harmful comment waiting in lead A's queue",
        verdict=HARMFUL,
        cohort=UNTAUGHT_COHORT,
    )
    a_shown_exclusion(review, UNTAUGHT_COHORT, "E9-14 5(a) the log row the reader reads")
    reader = READERS[role](review)

    _body, rows = the_log(review, reader, role)
    assert rows, f"The control: the {role} reads an empty log, so the refusal below proves nothing."
    queue = review.ask("GET", QUEUE, token=reader.token)
    assert (
        queue.status_code == FORBIDDEN
    ), f"The review queue answered the {role} {queue.status_code}: {queue.text[:300]!r}."
    assert queue.json() == {"detail": NO_REVIEW_GRANT.text}
