"""A node outside the purview is answered exactly as a node that does not exist — E9-07 done-when 11.

> 11. **Out-of-purview ids are refused like missing ones.** A route that takes
>     a node id answers a node outside the purview exactly as a node that does
>     not exist.

The route is the one the attempts file names:
`GET /leadership/rollup/{kind}/{node_id}?term_id=<uuid>`. The kind driven here
is `course`, one of the tree's levels; what status and sentence the refusal
uses is left open, because the criterion is the equality, not a particular
refusal.

**The world** is E6-05's lead-review world (`tests/fixtures/lead_review.py`): lead
A leads the own course, sibling lead B leads a sibling course under the same
prefix, and each holds a leadership session. A's purview holds her course and
not B's, and B's the reverse. Every request rides the built application as
`pulse_app` (`docs/MISTAKES.md` entries 46 and 47).

**Not `invariant`-marked:** the ticket gives the `invariant`-marked tests over
these routes to E9-12.

**Which failure a red is:** if the route answers an out-of-purview course with
its figures, or refuses it differently from a missing one, the equality FAILS;
if the route answers a lead's own course with anything but 200, the control
FAILS first.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.lead_review import LeadReviewWorld
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import TERM_TABLE

pytestmark = pytest.mark.integration

KIND = "course"


def figures_path(kind: str, node_id: Any, term_id: Any) -> str:
    return f"/leadership/rollup/{kind}/{node_id}?term_id={term_id}"


def term_of(review: LeadReviewWorld) -> Any:
    world = review.world
    return world.calendar.term[single_primary_key(require_table(world.tables, TERM_TABLE))]


def answer(response: Any) -> tuple[int, Any]:
    """The status and the whole body, as the reader receives them."""
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    return response.status_code, body


@pytest.mark.parametrize("reader", ("lead", "sibling_lead"))
def test_a_sibling_leads_course_is_refused_exactly_as_a_course_that_does_not_exist(
    lead_review: LeadReviewWorld, reader: str
) -> None:
    """Each lead asks for the other's course and for a random id; the two answers are identical.

    Run in both directions, so a route that happens to refuse one of the two
    courses for a reason unrelated to the purview cannot pass alone.

    **The control:** the same reader's own course answers 200, so the refusals
    are the purview and not a route that refuses everything.
    **The refusal guard:** the out-of-purview answer is a 4xx, so equality is
    not two empty 200s (an absence that would pass for an unrelated reason).

    **The mutations it kills:** the route answering any node's figures without
    checking the purview; the route answering 403 (or a different sentence) for
    a node that exists outside the purview and 404 for one that does not, which
    tells the reader which ids exist. **The near miss it spares:** whatever
    status and sentence the route picks for both.
    """
    review = lead_review
    lead, sibling = review.lead, review.sibling_lead
    assert lead is not None and sibling is not None, "The lead review world has no two leads."
    asker, own, others = (
        (lead, review.own_course, review.sibling_course)
        if reader == "lead"
        else (sibling, review.sibling_course, review.own_course)
    )
    term = term_of(review)

    held = review.ask("GET", figures_path(KIND, own, term), token=asker.token)
    outside = answer(review.ask("GET", figures_path(KIND, others, term), token=asker.token))
    missing = answer(review.ask("GET", figures_path(KIND, uuid4(), term), token=asker.token))

    assert held.status_code == 200, (
        f"The control failed: {asker.label} asking for her own course's figures answered "
        f"{held.status_code}; body begins {held.text[:400]!r}. E9-07's attempts file: `GET "
        "/leadership/rollup/{kind}/{node_id}?term_id=` answers a node in the reader's purview."
    )
    assert 400 <= outside[0] < 500, (
        f"{asker.label} asking for a sibling lead's course answered {outside[0]}; body begins "
        f"{str(outside[1])[:400]!r}. A course outside the purview is refused (SPEC §4.1 item 2)."
    )
    assert outside == missing, (
        f"{asker.label}: a course outside the purview answered {outside[0]} "
        f"{str(outside[1])[:400]!r}; a course that does not exist answered {missing[0]} "
        f"{str(missing[1])[:400]!r}. Done-when 11: the two are answered exactly alike."
    )
