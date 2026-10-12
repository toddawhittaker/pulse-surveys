"""The assistant dean, the dean and the vice president read the log and policy, and review nothing.

SPEC §5.2 and §5.3, as the epic's decision 12 reads them: these three roles read
the exclusion log and the response policy over their purview, read-only; the
review queue and on-behalf publishing stay with the lead and, for an unled
course, the chair. Read through the built application over HTTP in the
lead-review world (`tests/fixtures/lead_review.py`): one college, one
department, the report world's own course (led by `lead`), a sibling course led
by `sibling_lead`, and an unmapped course.

**The assistant dean's purview arrives through the supervision graph** (ADR
0199): their own grant is empty, and here the lead's assignment reports to
them, so their purview is the lead's course and nothing else. That is the
reader for whom "nothing outside it" has an outside in this world: the sibling
course is in the college and not in their purview. The dean and the vice
president reach the whole college.
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import STORED_EXCLUDED
from fixtures.lead_review import (
    AS_CHAIR,
    AS_LEAD_FACULTY,
    ASSISTANT_DEAN_ROLE,
    LOG_REASON,
    Reader,
)
from fixtures.moderation import HARMFUL
from fixtures.report_api import FULL_WEEK, TAUGHT_COHORT, UNTAUGHT_COHORT
from fixtures.report_views import INSTRUCTOR_STREAM
from sqlalchemy import text

pytestmark = pytest.mark.integration

SIBLING_COHORT = "Y"
DEAN_ROLE = "DEAN"
VP_ROLE = "VP_ACADEMICS"
FORBIDDEN = 403
NOT_FOUND = 404

QUEUE = "/leadership/moderation/queue"
LOG = "/leadership/moderation/log"
POLICY = "/leadership/response-policy"

TAUGHT_REASON = "E9 wider roles: an exclusion in the taught section of the own course"
UNTAUGHT_REASON = "E9 wider roles: an exclusion in the untaught section of the own course"
SIBLING_REASON = "E9 wider roles: an exclusion in the sibling lead's course"
UNMAPPED_REASON = "E9 wider roles: the chair's exclusion in the unled course"
UNMAPPED_COHORT = "4"


def an_excluded_comment(
    review: Any, cohort: str, reason: str, decider: Reader, decided_as: str = AS_LEAD_FACULTY
) -> None:
    comment = review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=f"E9 wider roles: a harmful comment in the cohort-{cohort} section",
        verdict=HARMFUL,
        cohort=cohort,
    )
    review.plant_decision(
        comment,
        STORED_EXCLUDED,
        decided_by=decider.person_id,
        decided_as=decided_as,
        reason=reason,
    )


def three_exclusions(review: Any) -> None:
    an_excluded_comment(review, TAUGHT_COHORT, TAUGHT_REASON, review.lead)
    an_excluded_comment(review, UNTAUGHT_COHORT, UNTAUGHT_REASON, review.lead)
    an_excluded_comment(review, SIBLING_COHORT, SIBLING_REASON, review.sibling_lead)


def an_assistant_dean_over_the_lead(review: Any) -> Reader:
    """An assistant dean of the college whom the lead's assignment reports to."""
    reader = review.a_leader("the-assistant-dean", grants=((ASSISTANT_DEAN_ROLE, review.college),))
    (dean_assignment,) = review.graph.assignments_of(reader.person_id)
    (lead_assignment,) = review.graph.assignments_of(review.lead.person_id)
    review.graph.repoint({review.graph.assignment_key: lead_assignment}, dean_assignment)
    review.rows.commit()
    return reader


def a_dean(review: Any) -> Reader:
    return review.a_leader("the-dean", grants=((DEAN_ROLE, review.college),))


def a_vice_president(review: Any) -> Reader:
    institution = review.session.execute(
        text("SELECT institution_id FROM college WHERE id = :college"),
        {"college": review.college},
    ).scalar_one()
    return review.a_leader("the-vice-president", grants=((VP_ROLE, institution),))


def log_reasons(review: Any, reader: Reader) -> set[str]:
    answered = review.ask("GET", LOG, token=reader.token)
    assert (
        answered.status_code == 200
    ), f"The log answered {answered.status_code} to {reader.label}. Body {answered.text[:300]!r}."
    return {str(row.get(LOG_REASON)) for row in answered.json()["rows"]}


def policy_courses(review: Any, reader: Reader) -> dict[str, bool]:
    """Each course the reader's policy read lists, and whether they may set it."""
    answered = review.ask("GET", POLICY, token=reader.token)
    assert (
        answered.status_code == 200
    ), f"The policy read answered {answered.status_code} to {reader.label}."
    return {
        str(course["course_id"]): course["can_set"]
        for prefix in answered.json()["prefixes"]
        for course in prefix["courses"]
    }


READERS = {
    "assistant dean": an_assistant_dean_over_the_lead,
    "dean": a_dean,
    "vice president": a_vice_president,
}


def test_the_assistant_dean_reads_the_log_and_policy_of_their_purview_and_nothing_else(
    lead_review: Any,
) -> None:
    """The lead's course is in; the sibling lead's course, in the same college, is out."""
    review = lead_review
    three_exclusions(review)
    reader = an_assistant_dean_over_the_lead(review)

    reasons = log_reasons(review, reader)
    assert {TAUGHT_REASON, UNTAUGHT_REASON} <= reasons, (
        f"The assistant dean's log carries {reasons}; both of the own course's exclusions are in "
        "their purview."
    )
    assert (
        SIBLING_REASON not in reasons
    ), "The assistant dean's log carries the sibling lead's exclusion, outside their purview."

    courses = policy_courses(review, reader)
    assert courses == {str(review.own_course): False}, (
        f"The assistant dean's policy read lists {courses}; their purview is the own course, "
        "which they read and may not set."
    )


@pytest.mark.parametrize("role", ["dean", "vice president"])
def test_the_dean_and_the_vice_president_read_the_whole_college(
    lead_review: Any, role: str
) -> None:
    """Every course of the college in the log and the policy, none of it settable."""
    review = lead_review
    three_exclusions(review)
    reader = READERS[role](review)

    reasons = log_reasons(review, reader)
    assert {
        TAUGHT_REASON,
        UNTAUGHT_REASON,
        SIBLING_REASON,
    } <= reasons, f"The {role}'s log carries {reasons}; all three exclusions are in their purview."
    courses = policy_courses(review, reader)
    expected = {str(review.own_course), str(review.sibling_course), str(review.unmapped_course)}
    assert expected <= set(courses), f"The {role}'s policy read lists {sorted(courses)}."
    assert not any(courses.values()), f"The {role} may set a policy: {courses}."


@pytest.mark.parametrize("role", sorted(READERS))
def test_a_wider_role_who_teaches_a_section_reads_no_log_row_from_it(
    lead_review: Any, role: str
) -> None:
    """The reader teaches the taught section: its row is gone, the untaught section's stays."""
    review = lead_review
    three_exclusions(review)
    reader = READERS[role](review)
    review.teaches(reader, TAUGHT_COHORT)

    reasons = log_reasons(review, reader)
    assert TAUGHT_REASON not in reasons, (
        f"The {role} teaches the section and its log still carries that section's exclusion; "
        "the instructor's own view governs that section (SPEC §5.2)."
    )
    assert (
        UNTAUGHT_REASON in reasons
    ), f"The {role}'s log lost the untaught section's exclusion too: {reasons}."


@pytest.mark.parametrize("role", sorted(READERS))
def test_a_wider_role_still_has_no_queue_and_no_on_behalf_door(lead_review: Any, role: str) -> None:
    """The queue's 403 and the on-behalf door's 404, each with the sentence it already had.

    The control is the same reader's log, read in the same world.
    """
    from app.copy.leadership_moderation import NO_REVIEW_GRANT
    from app.copy.response_loop import ON_BEHALF_UNAVAILABLE

    review = lead_review
    three_exclusions(review)
    reader = READERS[role](review)
    assert log_reasons(review, reader), f"The {role} reads an empty log, so the control is void."

    queue = review.ask("GET", QUEUE, token=reader.token)
    assert queue.status_code == FORBIDDEN
    assert queue.json() == {"detail": NO_REVIEW_GRANT.text}

    taught = review.world.section_id(TAUGHT_COHORT)
    on_behalf = review.ask(
        "GET", f"/leadership/sections/{taught}/weeks/{FULL_WEEK}/on-behalf", token=reader.token
    )
    assert on_behalf.status_code == NOT_FOUND
    assert on_behalf.json() == {"detail": ON_BEHALF_UNAVAILABLE.text}


def test_a_chair_still_reads_only_the_unled_courses_log(lead_review: Any) -> None:
    """The chair holds the department and reads no led course's exclusion: their reach is unchanged."""
    review = lead_review
    three_exclusions(review)
    an_excluded_comment(review, UNMAPPED_COHORT, UNMAPPED_REASON, review.chair, AS_CHAIR)
    reasons = log_reasons(review, review.chair)
    assert UNMAPPED_REASON in reasons, f"The chair's log lacks the unled course's row: {reasons}."
    assert not reasons & {
        TAUGHT_REASON,
        UNTAUGHT_REASON,
        SIBLING_REASON,
    }, f"The chair's log carries a led course's exclusion: {reasons}."
