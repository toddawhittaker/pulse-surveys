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

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from fixtures.lead_review import CHAIR_ROLE, LEAD_FACULTY_ROLE, LeadReviewWorld, Reader
from fixtures.supervision import require_table, single_primary_key
from fixtures.clock import ClockOverrides
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


def expected_opening_term(terms: list[dict[str, Any]], today: date) -> str | None:
    """The term the pages open on `today`, read off the answer's own term list.

    The one containing today, the later-started of two that overlap; else the
    latest that has begun; else none. The shared database holds other tests'
    terms too, so the expectation is computed from what the route listed.
    """

    def start(term: dict[str, Any]) -> date:
        return date.fromisoformat(term["start_date"])

    def end(term: dict[str, Any]) -> date:
        return date.fromisoformat(term["end_date"])

    containing = [term for term in terms if start(term) <= today <= end(term)]
    pool = containing or [term for term in terms if start(term) <= today]
    if not pool:
        return None
    return str(max(pool, key=start)["id"])


def context_on(review: LeadReviewWorld, overrides: ClockOverrides, today: date) -> dict[str, Any]:
    """The lead's context with the development clock moved to noon UTC on `today`.

    Noon UTC is the same calendar day in every zone an institution in this
    product sits in, so the institution's day is `today` (ADR 0109).
    """
    overrides.set(
        pretend_now=datetime.combine(today, time(12), tzinfo=UTC), anchored_at=datetime.now(UTC)
    )
    assert review.lead is not None
    return context_for(review, review.lead)


def test_the_term_containing_today_is_the_one_opened(
    lead_review: LeadReviewWorld, committed_clock_overrides: ClockOverrides
) -> None:
    """On the world's term's first day, a term containing that day is opened."""
    term_row = lead_review.world.calendar.term
    first_day = term_row["start_date"]
    body = context_on(lead_review, committed_clock_overrides, first_day)
    opened = body["current_term_id"]
    assert opened is not None
    assert str(opened) == expected_opening_term(body["terms"], first_day)
    term = next(term for term in body["terms"] if str(term["id"]) == str(opened))
    assert (
        date.fromisoformat(term["start_date"]) <= first_day <= date.fromisoformat(term["end_date"])
    )


def test_between_terms_the_latest_term_that_has_begun_is_opened(
    lead_review: LeadReviewWorld, committed_clock_overrides: ClockOverrides
) -> None:
    """With no term containing the day, the latest begun one opens, never a future one."""
    far = date(2999, 1, 1)
    body = context_on(lead_review, committed_clock_overrides, far)
    assert not any(
        date.fromisoformat(term["start_date"]) <= far <= date.fromisoformat(term["end_date"])
        for term in body["terms"]
    ), "A term contains the probe day, so this test reads nothing about the fallback."
    opened = body["current_term_id"]
    assert opened is not None, "Between terms the context opened no term at all."
    assert str(opened) == expected_opening_term(body["terms"], far)


def test_before_any_term_begins_no_term_is_opened(
    lead_review: LeadReviewWorld, committed_clock_overrides: ClockOverrides
) -> None:
    """A day before every listed term opens none, rather than a term not yet begun."""
    listed = context_on(lead_review, committed_clock_overrides, date(2999, 1, 1))["terms"]
    assert listed, "The world lists no term, so this test reads nothing."
    earliest = min(date.fromisoformat(term["start_date"]) for term in listed)
    body = context_on(lead_review, committed_clock_overrides, earliest - timedelta(days=1))
    assert body["current_term_id"] is None


def test_a_request_without_a_session_is_refused(lead_review: LeadReviewWorld) -> None:
    """No session, no context: the leadership gate's 401."""
    answered = lead_review.ask("GET", CONTEXT_PATH, token=None)
    assert answered.status_code == 401
