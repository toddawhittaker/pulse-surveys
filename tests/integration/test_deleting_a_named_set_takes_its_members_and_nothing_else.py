"""Deleting a set removes its membership rows and nothing else — E5-06.

Criterion 4's first clause: "Deleting a set is refused/allowed per E5-01's
member-deletion ADR". ADR 0164 settles that deletion runs in opposite
directions — a set cascades to its membership rows, and a course named by a set
cannot be deleted at all — and work-order decision 4 names the half this ticket
owns: "the test that a set delete removes its members and nothing else".

**"And nothing else" is the assertion, not "and its members".** A cascade
written one join too wide takes the member *courses* with it, and a course is
LMS-owned data the product may not delete at all; one written against the wrong
key takes another set's membership rows, which silently rewrites the cohort
another leader defined. Both leave the set gone and its own members gone, so a
test asserting only that would be green against either.

**The inventory is read before and after.** Every membership row in the
database, every set, every course and every section — counted on the seeding
connection after the route has committed on its own. A delete is the one
operation whose blast radius cannot be read off its response.

**Which failure a red here is, before E5-06 lands.** The path is the work
order's own, so an application without the router answers 404 and the test fails
on the status naming the router — a FAILED, not an error (`docs/MISTAKES.md`
entry 44).
"""

from typing import Any

import pytest
from fixtures.comparison_sets import COURSE_TABLE
from fixtures.named_sets import NamedSetDoor
from fixtures.survey_windows import SECTION_TABLE
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


def count_of(world: Any, table_name: str) -> int:
    """How many rows one table holds right now, on the seeding connection."""
    from fixtures.supervision import require_table

    world.refresh()
    table = require_table(world.tables, table_name)
    return int(world.session.execute(select(func.count()).select_from(table)).scalar_one())


def test_deleting_a_set_removes_its_membership_rows(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """The cascade ADR 0164 settles, driven over HTTP and read back out of the database.

    **The mutation this kills:** a delete that removes the set row and leaves its
    membership rows behind — which the database refuses outright if the foreign
    key is `RESTRICT` and silently orphans if it is not, and which in either case
    is a set that half exists.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    world = named_sets.world
    hers = world.hers
    assert len(world.members_of(hers.set_id)) == len(hers.member_course_ids), (
        "The set this test deletes does not hold the membership rows it was planted with, so "
        "'they are gone afterwards' would be true before the delete ran."
    )

    answered = named_sets.remove(hers.set_id)

    assert answered.status_code == named_set_contract.no_content, (
        f"`DELETE` of her own set answered {answered.status_code} rather than "
        f"{named_set_contract.no_content}. Body begins {answered.text[:400]!r}."
    )
    assert (
        world.set_row(hers.set_id) is None
    ), "The set is still in the database after a 204. The answer is a claim that the row is gone."
    assert world.members_of(hers.set_id) == [], (
        f"The deleted set still holds {world.members_of(hers.set_id)}. ADR 0164 cascades a set's "
        "membership rows with it."
    )


def test_deleting_a_set_leaves_the_other_leaders_set_its_courses_and_its_sections(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """The "and nothing else" half, over every table a wide cascade could reach.

    **The mutations this kills:** a delete that cascades through the membership
    table into `course`, which would delete LMS-owned rows the product never
    writes and never deletes, and which would take every section under them; a
    delete whose `WHERE` names the course rather than the set, removing the
    other leader's membership row for a course both sets happen to name; and a
    delete of the set table with no predicate at all, which answers 204 and
    empties the institution's list.

    **The other leader's set is the near miss that matters**: it survives the
    same request, holding exactly the membership rows it was planted with.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    world = named_sets.world
    theirs = world.theirs
    courses_before = count_of(world, COURSE_TABLE)
    sections_before = count_of(world, SECTION_TABLE)
    their_members_before = len(world.members_of(theirs.set_id))
    all_members_before = len(world.membership_rows())
    assert their_members_before and courses_before and sections_before, (
        "This world has no other leader's set, no courses or no sections, so every survival claim "
        "below is satisfied by emptiness."
    )

    answered = named_sets.remove(world.hers.set_id)
    assert answered.status_code == named_set_contract.no_content, (
        f"`DELETE` answered {answered.status_code}; nothing after this is about a delete that "
        f"happened. Body begins {answered.text[:400]!r}."
    )

    assert world.set_row(theirs.set_id) is not None, (
        "The other leader's set went with this one. A delete that removes more than the set it "
        "names rewrites the cohort somebody else defined, and every figure already published "
        "against it."
    )
    assert len(world.members_of(theirs.set_id)) == their_members_before, (
        f"The other leader's set holds {len(world.members_of(theirs.set_id))} membership rows "
        f"where it held {their_members_before}."
    )
    assert len(world.membership_rows()) == all_members_before - len(world.hers.member_course_ids), (
        f"The database holds {len(world.membership_rows())} membership rows; it held "
        f"{all_members_before} and the deleted set carried "
        f"{len(world.hers.member_course_ids)} of them. Anything else is a cascade reaching rows "
        "this delete does not own."
    )
    assert count_of(world, COURSE_TABLE) == courses_before, (
        f"The database holds {count_of(world, COURSE_TABLE)} courses where it held "
        f"{courses_before}. A course is LMS-owned (SPEC §2.1) and ADR 0164 makes a course named by "
        "a set undeletable, let alone deletable as a side effect of deleting the set."
    )
    assert count_of(world, SECTION_TABLE) == sections_before, (
        f"The database holds {count_of(world, SECTION_TABLE)} sections where it held "
        f"{sections_before}."
    )


def test_a_deleted_set_is_unknown_to_the_route_that_read_it(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """After the 204, the same id is a 404 carrying `SET_UNAVAILABLE`.

    The pair is the read that succeeds before it: the same route, the same id,
    answered 200 and then 404. Without the first half, "a deleted set is
    unknown" is satisfied by a route that never found it.

    **The mutation this kills:** a delete that only marks the row — a
    `deleted_at` nobody reads — leaving the set in every list and every
    resolution while the route reports it gone.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    world = named_sets.world
    expected = named_set_contract.sentence(named_set_contract.set_unavailable)

    before = named_sets.read(world.hers.set_id)
    assert before.status_code == named_set_contract.list_ok, (
        f"The set could not be read before it was deleted ({before.status_code}), so the 404 "
        f"below would say nothing. Body begins {before.text[:400]!r}."
    )

    named_sets.remove(world.hers.set_id)
    after = named_sets.read(world.hers.set_id)

    assert after.status_code == named_set_contract.unknown_set, (
        f"Reading the deleted set answered {after.status_code} rather than "
        f"{named_set_contract.unknown_set}. Body begins {after.text[:400]!r}."
    )
    assert named_set_contract.detail_of(after) == expected, (
        f"The deleted set was refused with {named_set_contract.detail_of(after)!r} rather than "
        f"with the `SET_UNAVAILABLE` sentence {expected!r}."
    )
