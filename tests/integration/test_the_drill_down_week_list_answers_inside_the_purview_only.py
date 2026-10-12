"""`GET /leadership/sections/{section_id}/published-weeks`: the drill-down's week list.

A section reached from the roll-up tree carries no week, so the drill-down asks
which weeks the section has a report for and opens the latest, as the
instructor's own page does. The list sits behind the drill-down's purview: a
section outside it and a section that does not exist get the drill-down's one
404 and sentence. The world is the lead-review world, read over HTTP as
`pulse_app` (`docs/MISTAKES.md` entries 46 and 47).
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.moderation import CLEAR
from fixtures.report_api import FULL_WEEK, TAUGHT_COHORT
from fixtures.report_views import INSTRUCTOR_STREAM

pytestmark = pytest.mark.integration

SIBLING_COHORT = "Y"
NOT_FOUND = 404


def weeks_url(section_id: Any) -> str:
    return f"/leadership/sections/{section_id}/published-weeks"


def a_week_in(review: Any, cohort: str) -> None:
    review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=f"A clear comment in the cohort-{cohort} section",
        verdict=CLEAR,
        cohort=cohort,
    )


def test_the_lead_reads_the_same_weeks_the_drill_down_report_carries(lead_review: Any) -> None:
    """The list names the full week, and the report for that week lists the same weeks."""
    review = lead_review
    a_week_in(review, TAUGHT_COHORT)
    section = review.world.section_id(TAUGHT_COHORT)

    listed = review.ask("GET", weeks_url(section), token=review.lead.token)
    assert listed.status_code == 200, listed.text[:300]
    weeks = listed.json()["published_weeks"]
    assert FULL_WEEK in weeks

    report = review.ask(
        "GET",
        f"/leadership/sections/{section}/weeks/{FULL_WEEK}/report",
        token=review.lead.token,
    )
    assert report.status_code == 200, report.text[:300]
    assert report.json()["week"]["published_weeks"] == weeks


def test_a_sibling_section_and_a_missing_one_get_the_drill_downs_one_refusal(
    lead_review: Any,
) -> None:
    """The lead asking for a sibling lead's section and for an id nothing holds: one 404, one body."""
    from app.copy.instructor_report import SECTION_UNAVAILABLE

    review = lead_review
    a_week_in(review, SIBLING_COHORT)
    sibling = review.world.section_id(SIBLING_COHORT)

    own = review.ask("GET", weeks_url(sibling), token=review.sibling_lead.token)
    assert own.status_code == 200, "The sibling lead reads her own section's weeks."

    refusals = [
        review.ask("GET", weeks_url(sibling), token=review.lead.token),
        review.ask("GET", weeks_url(uuid4()), token=review.lead.token),
    ]
    assert [answered.status_code for answered in refusals] == [NOT_FOUND, NOT_FOUND]
    assert {answered.content for answered in refusals} == {refusals[0].content}
    assert refusals[1].json() == {"detail": SECTION_UNAVAILABLE.text}
