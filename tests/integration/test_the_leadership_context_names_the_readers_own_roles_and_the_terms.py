"""`GET /leadership/context`: the reader's own roles, highest first, and every term.

The roll-up pages read this before anything else: the term list is where the
page finds a `term_id` to ask the roll-up for, and the roles are what the
drill-down's read-only context bar names (SPEC §5.5). The roles come from the
session's own scope (ADR 0199), so two leaders asking the same route get two
answers.

**The world** is the lead-review world (`tests/fixtures/lead_review.py`): a lead
of one course and the chair of its department. Every request rides the built
application as `pulse_app` (`docs/MISTAKES.md` entries 46 and 47).
"""

from typing import Any

import pytest
from fixtures.lead_review import CHAIR_ROLE, LEAD_FACULTY_ROLE, LeadReviewWorld, Reader
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import TERM_TABLE

pytestmark = pytest.mark.integration

CONTEXT_PATH = "/leadership/context"
COURSE_TABLE = "course"


def context_for(review: LeadReviewWorld, reader: Reader) -> dict[str, Any]:
    answered = review.ask("GET", CONTEXT_PATH, token=reader.token)
    assert answered.status_code == 200, (
        f"The context answered {answered.status_code} to {reader.label}; body begins "
        f"{answered.text[:400]!r}."
    )
    body = answered.json()
    assert isinstance(body, dict)
    return body


def test_a_lead_and_a_chair_each_read_their_own_role(lead_review: LeadReviewWorld) -> None:
    """The lead reads `LEAD_FACULTY` and the chair `CHAIR`, from one route."""
    review = lead_review
    assert review.lead is not None and review.chair is not None
    assert context_for(review, review.lead)["roles"] == ["LEAD_FACULTY"]
    assert context_for(review, review.chair)["roles"] == ["CHAIR"]


def test_a_reader_holding_two_roles_reads_both_highest_first(
    lead_review: LeadReviewWorld,
) -> None:
    """A chair who also leads a course reads `CHAIR` before `LEAD_FACULTY`.

    The grants are written lead first, so an answer in grant order is red.
    """
    review = lead_review
    two_hats = review.a_leader(
        "the-chair-who-leads",
        grants=(
            (LEAD_FACULTY_ROLE, review.own_course),
            (CHAIR_ROLE, review.department),
        ),
    )
    assert context_for(review, two_hats)["roles"] == ["CHAIR", "LEAD_FACULTY"]


def test_the_terms_carry_the_worlds_term_and_the_current_one_is_listed(
    lead_review: LeadReviewWorld,
) -> None:
    """The world's term is in the list with its length, and `current_term_id` is a listed term or null."""
    review = lead_review
    assert review.lead is not None
    world = review.world
    term_row = world.calendar.term
    term_id = str(term_row[single_primary_key(require_table(world.tables, TERM_TABLE))])

    body = context_for(review, review.lead)
    listed = {str(term["id"]): term for term in body["terms"]}
    assert term_id in listed, f"The world's term {term_id} is not in {sorted(listed)}."
    assert listed[term_id]["length_weeks"] == term_row["length_weeks"]
    starts = [term["start_date"] for term in body["terms"]]
    assert starts == sorted(starts), f"The terms are not oldest first: {starts}."
    current = body["current_term_id"]
    assert current is None or str(current) in listed


def test_a_request_without_a_session_is_refused(lead_review: LeadReviewWorld) -> None:
    """No session, no context: the leadership gate's 401."""
    answered = lead_review.ask("GET", CONTEXT_PATH, token=None)
    assert answered.status_code == 401
