"""A Lead Faculty member is never shown the by-lead pivot, in the tree or through its route — E9-14 item 5(c).

SPEC §5.5: "a by-lead-faculty pivot additionally for chair and above over their
purview — never for Lead Faculty (sibling isolation, invariant §4.1.2)." E9-07
built it (`GET /leadership/rollup` answers `by_lead`, null unless a grant is
chair or above; `GET /leadership/rollup/{kind}/{node_id}` answers a `lead` or
`no_lead` group's figures). The E9 boundary invariant-coverage review found it
asserted only in an unmarked module
(`test_the_rollup_tree_offers_by_lead_mode_to_chair_and_above_only.py`), and the
figures route's by-lead kinds never asked of a lead at all. This module asserts
both, marked.

**The group ids are read off the chair's tree** in the same world, so they are
the product's own: a lead holds no by-lead group to read an id from. The lead's
answer for each is compared with the lead's answer for an id nothing holds,
under the same kind: one status, one body, and a 4xx, as E9-07's done-when 11
has it for a node outside the purview.

**Which failure a red is.** E9-07's gate exists on this branch, so every test
here is expected **green**.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.e9_invariant_pass import (
    BY_LEAD_KINDS,
    answer,
    body_of,
    descendants,
    figures_url,
    term_of,
    tree_url,
)
from fixtures.lead_review import LeadReviewWorld

pytestmark = [pytest.mark.integration, pytest.mark.invariant]


def kinds_in(nodes: Any) -> set[str]:
    found: set[str] = set()
    for node in nodes or []:
        found.add(str(node.get("kind")))
        found |= kinds_in(node.get("children"))
    return found


def test_a_leads_tree_carries_no_by_lead_pivot_and_a_chairs_does(
    lead_review: LeadReviewWorld,
) -> None:
    """Lead A's tree: `by_lead` null and no lead group anywhere; the chair's tree: both group kinds.

    **The mutation it kills:** the pivot offered to every leadership reader, or
    decided from the purview's size. **The near miss it spares:** the chair's
    pivot (the twin) and lead A's own hierarchy, required non-empty.
    """
    review = lead_review
    term = term_of(review)
    lead_tree = body_of(review.ask("GET", tree_url(term), token=review.lead.token), "Lead A's tree")
    chair_tree = body_of(
        review.ask("GET", tree_url(term), token=review.chair.token), "The chair's tree"
    )

    groups = chair_tree.get("by_lead") or []
    assert {str(group.get("kind")) for group in groups} == set(BY_LEAD_KINDS), (
        f"The present twin: the chair's by-lead groups are {groups!r}; the chair's department "
        "holds led courses and an unled one."
    )
    assert lead_tree.get("hierarchy"), "Lead A's hierarchy is empty; she leads a course."
    assert "by_lead" in lead_tree and lead_tree["by_lead"] is None, (
        f"Lead A's tree carries `by_lead` {str(lead_tree.get('by_lead'))[:300]!r}. SPEC §5.5: never "
        "for Lead Faculty."
    )
    assert not kinds_in(lead_tree["hierarchy"]) & set(BY_LEAD_KINDS), (
        f"Lead A's hierarchy holds node kinds {sorted(kinds_in(lead_tree['hierarchy']))}; a lead's "
        "tree carries no grouping by lead."
    )


def test_a_lead_asking_for_a_sibling_leads_group_or_the_no_lead_group_is_answered_as_a_missing_node(
    lead_review: LeadReviewWorld,
) -> None:
    """`/rollup/lead/<B's group>` and `/rollup/no_lead/<the group>` from lead A: the missing-node answer.

    **The present twin:** the chair asking the same two URLs is answered 200.
    **The refusal guard:** lead A's answer is a 4xx, so the equality is not two
    empty 200s.

    **The mutations it kills:** the figures route answering a by-lead kind
    without the role gate, so a lead reads sibling lead B's courses' figures
    through B's group (SPEC §4.1 item 2) or the unled courses' through the
    no-lead group; a 403 or another sentence for a group that exists, which
    tells the lead the id is real. **The near miss it spares:** whatever 404 and
    sentence the route answers a node that does not exist.
    """
    review = lead_review
    term = term_of(review)
    chair_tree = body_of(
        review.ask("GET", tree_url(term), token=review.chair.token), "The chair's tree"
    )
    groups = chair_tree.get("by_lead") or []
    siblings = [
        group
        for group in groups
        if group.get("kind") == "lead"
        and any(str(node.get("id")) == str(review.sibling_course) for node in descendants(group))
    ]
    no_lead = [group for group in groups if group.get("kind") == "no_lead"]
    assert len(siblings) == 1 and len(no_lead) == 1, (
        f"The chair's tree holds {len(siblings)} lead groups over B's course and {len(no_lead)} "
        f"no-lead groups ({groups!r}); one of each was expected. A broken world, not a red."
    )

    for kind, group in (("lead", siblings[0]), ("no_lead", no_lead[0])):
        url = figures_url(kind, group["id"], term)
        chairs = answer(review.ask("GET", url, token=review.chair.token))
        leads = answer(review.ask("GET", url, token=review.lead.token))
        missing = answer(
            review.ask("GET", figures_url(kind, uuid4(), term), token=review.lead.token)
        )
        assert chairs[0] == 200, (
            f"The present twin: the chair asking for the {kind} group's figures answered "
            f"{chairs[0]} {str(chairs[1])[:300]!r}."
        )
        assert 400 <= leads[0] < 500, (
            f"Lead A asking for the {kind} group's figures answered {leads[0]} "
            f"{str(leads[1])[:300]!r}. SPEC §5.5: the by-lead pivot is never a lead's."
        )
        assert leads == missing, (
            f"The {kind} group answered lead A {leads}; a {kind} id nothing holds answered "
            f"{missing}. A group that exists is refused exactly as one that does not."
        )
