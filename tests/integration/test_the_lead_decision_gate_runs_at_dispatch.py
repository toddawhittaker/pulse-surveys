"""The leadership decision's CSRF gate runs at dispatch — ticket E6-05, criterion 7.

> A leadership decision POST with no CSRF token, or from another origin, is
> refused over HTTP against the built application, and the same POST with the
> token succeeds (entry 47).

`docs/MISTAKES.md` entry 47: a sweep over the route table answers "is the
dependency there", never "does the gate run", so the gate is driven here over
HTTP in both directions. **The session rides the cookie**, because ADR 0089's
double-submit check exempts a Bearer header deliberately — every other request
in these suites is Bearer, and a gutted `csrf_verified_leadership` would leave
them all green. "From another origin" is a genuine token minted for a different
session: what a page elsewhere can come by, and what a check comparing the cookie
to the header (rather than verifying it against this session) lets through.

**Each refusal is paired with the accepted request on the same comment**, so a
route that refuses every cookie-borne POST is red on the pair rather than green on
the refusal.

**Which failure a red is, before E6-05 lands.** `lead_routes` fails naming the
routes — a FAILED, never an ERROR (`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import (
    DECIDED_AS_COLUMN,
    DECIDER_COLUMN,
    STATE_COLUMN,
    STORED_EXCLUDED,
    require_decision_columns,
)
from fixtures.lead_review import AS_LEAD_FACULTY, EXCLUDE, MINTED, LeadReviewWorld, is_success
from fixtures.moderation import HARMFUL
from fixtures.report_api import FIRST_HELD_WEEK, TAUGHT_COHORT
from fixtures.report_views import COURSE_STREAM
from fixtures.submit import CSRF_REFUSED_STATUS

pytestmark = pytest.mark.integration

CASES = ("no-token", "another-sessions-token")


@pytest.mark.parametrize("case", CASES)
def test_a_cookie_borne_decision_without_this_sessions_token_is_refused_and_with_it_accepted(
    case: str, lead_review: LeadReviewWorld
) -> None:
    """Criterion 7, both directions, on one queued comment.

    **The mutations this kill:** the POST declared with `require_leadership`
    rather than `csrf_verified_leadership` (both refusals are accepted and write
    a row); the dependency attached somewhere that does not run at dispatch
    (entry 47's shape, same red); a check that compares the cookie to the header
    (the other session's token, sent as both, passes it). **The near miss:** a
    gate that refuses every cookie-borne write — the minted-token request is
    required to succeed and to write the lead's row.
    """
    review = lead_review
    require_decision_columns(review.world.tables)
    comment = review.plant(
        course_week=FIRST_HELD_WEEK,
        stream=COURSE_STREAM,
        text=f"E6-05 a held harmful comment for the CSRF case {case}",
        verdict=HARMFUL,
        cohort=TAUGHT_COHORT,
    )
    token: Any = None
    if case == "another-sessions-token":
        token = review.another_sessions_csrf_token(review.lead.token)

    before = review.rows_of(comment)
    refused = review.decide_as_a_browser(review.lead, comment, EXCLUDE, csrf_token=token)
    assert refused.status_code == CSRF_REFUSED_STATUS, (
        f"A cookie-borne leadership decision with {case} was answered {refused.status_code}, not "
        f"{CSRF_REFUSED_STATUS}. Body begins {refused.text[:400]!r}."
    )
    assert review.rows_of(comment) == before, f"The refused request ({case}) wrote a row."

    accepted = review.decide_as_a_browser(review.lead, comment, EXCLUDE, csrf_token=MINTED)
    assert is_success(accepted.status_code), (
        f"The same decision carrying this session's own CSRF token was answered "
        f"{accepted.status_code}, so the refusal above may be a route refusing every cookie. "
        f"Body begins {accepted.text[:400]!r}."
    )
    row = review.rows_of(comment)[-1]
    assert (row[STATE_COLUMN], str(row[DECIDER_COLUMN]), row[DECIDED_AS_COLUMN]) == (
        STORED_EXCLUDED,
        str(review.lead.person_id),
        AS_LEAD_FACULTY,
    ), f"The accepted cookie-borne decision left {row!r}."
