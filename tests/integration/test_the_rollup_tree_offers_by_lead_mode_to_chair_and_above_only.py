"""By-lead mode is offered from the roles held, to chair and above only — E9-07 done-when 3.

> 3. **By-lead only for chair and above.** A lead's payload offers no by-lead
>    mode and carries no grouping by lead; a chair's does. The gate is decided
>    from the roles held: a lead whose purview is larger than a chair's still
>    gets none.

The interface (the coordinator's settled note): `GET /leadership/rollup?term_id=`
answers `RollupTree {term_id, hierarchy, by_lead}`; `by_lead` is null unless a
grant is `CHAIR`, `ASSISTANT_DEAN`, `DEAN` or `VP_ACADEMICS`; tree nodes carry
`kind` (`college`, `department`, `prefix`, `course`, `section`, `lead`,
`no_lead`), `section_count` and `children`.

**The world** is E6-05's lead-review world (`tests/fixtures/lead_review.py`):
lead A leads the own course (two sections), and its chair holds the department.
This module adds a second chair over a department of its own with nothing in it,
whose purview is smaller than lead A's. Every request rides the built
application as `pulse_app` (`docs/MISTAKES.md` entries 46 and 47).

**Which failure a red is on dac77db5:** the tree cannot read a department's name
(`permission denied for table department`), so each admitted request answers 500
and FAILS on its status.
"""

from typing import Any

import pytest
from fixtures.lead_review import CHAIR_ROLE, LeadReviewWorld, Reader
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import TERM_TABLE

pytestmark = pytest.mark.integration

TREE_PATH = "/leadership/rollup"
BY_LEAD_KINDS = frozenset({"lead", "no_lead"})
DEPARTMENT_TABLE = "department"


def tree_for(review: LeadReviewWorld, reader: Reader) -> dict[str, Any]:
    world = review.world
    term = world.calendar.term[single_primary_key(require_table(world.tables, TERM_TABLE))]
    answered = review.ask("GET", f"{TREE_PATH}?term_id={term}", token=reader.token)
    assert answered.status_code == 200, (
        f"The tree answered {answered.status_code} to {reader.label}; body begins "
        f"{answered.text[:400]!r}. E9-07's attempts file: `GET {TREE_PATH}?term_id=` answers a "
        "leadership session its tree."
    )
    body = answered.json()
    assert isinstance(body, dict) and "hierarchy" in body and "by_lead" in body, (
        f"The tree answered {str(body)[:400]!r}; the settled payload is `{{term_id, hierarchy, "
        "by_lead}}`."
    )
    return body


def kinds_in(nodes: list[dict[str, Any]]) -> set[str]:
    found: set[str] = set()
    for node in nodes:
        found.add(str(node.get("kind")))
        found |= kinds_in(node.get("children") or [])
    return found


def sections_held(body: dict[str, Any]) -> int:
    return sum(int(node.get("section_count") or 0) for node in body["hierarchy"])


def a_chair_of_an_empty_department(review: LeadReviewWorld) -> Reader:
    stored = review.world.seed(DEPARTMENT_TABLE, {})
    review.rows.commit()
    return review.a_leader(
        "the-empty-department-chair",
        grants=((CHAIR_ROLE, review.key(DEPARTMENT_TABLE, stored)),),
    )


def test_a_leads_tree_offers_no_by_lead_mode_and_groups_nothing_by_lead(
    lead_review: LeadReviewWorld,
) -> None:
    """Lead A: `by_lead` is null, and no node anywhere in her hierarchy is a lead group.

    **The control:** her hierarchy is not empty, so "no lead group" is about a
    tree that exists. **The mutation it kills:** by-lead offered to every
    leadership reader; lead groups mixed into a lead's hierarchy.
    """
    review = lead_review
    assert review.lead is not None
    body = tree_for(review, review.lead)
    assert body["hierarchy"], "Lead A's hierarchy is empty; she leads a course with two sections."
    assert body["by_lead"] is None, (
        f"Lead A's tree offers by-lead mode: {str(body['by_lead'])[:400]!r}. Done-when 3: chair "
        "and above only."
    )
    assert not kinds_in(body["hierarchy"]) & BY_LEAD_KINDS, (
        f"Lead A's hierarchy carries node kinds {sorted(kinds_in(body['hierarchy']))}; a lead's "
        "payload carries no grouping by lead."
    )


def test_a_chairs_tree_offers_by_lead_mode_grouped_by_lead_and_no_lead(
    lead_review: LeadReviewWorld,
) -> None:
    """The department chair: `by_lead` is a non-empty list of lead and no-lead groups.

    The chair's department holds two led courses and one unled one, so both
    group kinds are present. **The mutation it kills:** by-lead withheld from a
    chair; unled courses dropped rather than grouped under the chair.
    """
    review = lead_review
    assert review.chair is not None
    body = tree_for(review, review.chair)
    groups = body["by_lead"]
    assert (
        isinstance(groups, list) and groups
    ), f"The chair's tree carries `by_lead` {groups!r}; a chair is offered by-lead mode."
    top = {str(group.get("kind")) for group in groups}
    assert top == BY_LEAD_KINDS, (
        f"The chair's by-lead groups are of kinds {sorted(top)}; her department has led courses "
        "and an unled one, so both `lead` and `no_lead` groups."
    )


def test_a_lead_with_a_larger_purview_than_a_chair_still_gets_no_by_lead_mode(
    lead_review: LeadReviewWorld,
) -> None:
    """Gate by role, not by size: a chair of an empty department gets by-lead; lead A, holding more, does not.

    **The control:** lead A holds strictly more sections than that chair, read
    off each tree. **The mutation it kills:** the gate decided from the
    purview's size (more than one course, more than N sections). **The near
    miss it spares:** an empty by-lead list for the empty department.
    """
    review = lead_review
    assert review.lead is not None
    small_chair = a_chair_of_an_empty_department(review)
    lead_tree = tree_for(review, review.lead)
    chair_tree = tree_for(review, small_chair)

    assert sections_held(lead_tree) > sections_held(chair_tree), (
        f"Lead A holds {sections_held(lead_tree)} sections and the empty department's chair "
        f"{sections_held(chair_tree)}; this pair needs the lead's purview to be the larger. A "
        "broken world, not a red."
    )
    assert isinstance(chair_tree["by_lead"], list), (
        f"The empty department's chair gets `by_lead` {chair_tree['by_lead']!r}; a chair is offered "
        "by-lead mode whatever her purview holds."
    )
    assert lead_tree["by_lead"] is None, (
        f"Lead A, holding more than a chair, is offered by-lead mode "
        f"({str(lead_tree['by_lead'])[:400]!r}). Done-when 3: decided from the roles held."
    )
