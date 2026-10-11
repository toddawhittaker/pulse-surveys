"""A policy toggled after report open changes nothing for that week — E7-03, done-when 5.

> **The policy of record is the policy in force at report open.** A toggle after
> report open changes nothing for that week, through these routes, in both
> directions.

The toggle is made **through the policy route**, an hour after course week 1's
report opens (the route stamps `set_at` from the development clock). Its effect
is read through decision 3's predicates and decision 4's owed read, each pinned
to its own instant. **Each direction is a pair**: course week 1, whose report had
opened before the toggle, keeps the policy it opened under; course week 2, whose
report opens a week later, takes the new one — so a predicate that ignores the
policy entirely cannot pass both halves.

**Which failure a red is, before E7-03 lands.** `find_route` fails naming the
policy write, or `the_predicate` names a predicate.
"""

import pytest
from fixtures.response_loop_doors import (
    CLEAR_PAST,
    HTTP_MARGIN,
    IS_OWED,
    NEXT_WEEK,
    OK,
    ON_BEHALF_WEEK,
    OWED_AFTER,
    OWED_COURSE_WEEK,
    OWED_SECTION_ID,
    LoopWorld,
)
from fixtures.the_hold import ENCOURAGED, REQUIRED, report_opens

pytestmark = pytest.mark.integration


def owed_at_48h(world: LoopWorld, course_week: int) -> bool:
    return world.predicate(
        IS_OWED,
        section_id=world.hold.taught,
        course_week=course_week,
        now=report_opens(course_week) + OWED_AFTER,
    )


@pytest.mark.parametrize(
    ("opened_under", "toggled_to"), [(ENCOURAGED, REQUIRED), (REQUIRED, ENCOURAGED)]
)
def test_a_toggle_after_week_ones_opening_governs_week_two_and_not_week_one(
    response_loop: LoopWorld, opened_under: str, toggled_to: str
) -> None:
    """Week 1 opens under one mode; the lead toggles through the route an hour later.

    Week 1 is owed at +48h exactly when it opened required; week 2 exactly when
    the toggle made it required.

    **The mutations this kill:** the latest policy row read for every week
    (week 1 follows the toggle — required-to-encouraged releases a held week,
    encouraged-to-required holds a shown one); the policy of record taken at
    +48h rather than at report open. **The near miss:** week 2, which must
    follow the toggle.
    """
    world = response_loop
    if opened_under == REQUIRED:
        world.own_course_required()
    world.stand(CLEAR_PAST)

    toggled = world.policy_set(world.lead, toggled_to)
    assert (
        toggled.status_code == OK
    ), f"Lead A's toggle answered {toggled.status_code}. Body {toggled.text[:300]!r}."

    week_one = owed_at_48h(world, ON_BEHALF_WEEK)
    week_two = owed_at_48h(world, NEXT_WEEK)

    assert week_one is (opened_under == REQUIRED), (
        f"Course week 1 opened {opened_under}; after a toggle to {toggled_to} an hour later it "
        f"reads owed={week_one} at +48h. Done-when 5: the toggle changes nothing for that week."
    )
    assert week_two is (
        toggled_to == REQUIRED
    ), f"Course week 2 opened after the toggle to {toggled_to} and reads owed={week_two} at +48h."


def test_the_owed_read_after_a_toggle_to_encouraged_still_lists_the_held_week(
    response_loop: LoopWorld,
) -> None:
    """Required at open; toggled to encouraged an hour later; the owed read at +48h still lists week 1.

    The same direction as above, read through the route a lead actually reads.

    **The mutation this kills:** the owed read applying today's policy rather
    than the week's policy of record. **The near miss:** the owed entry is for
    the taught section's course week 1, the one held.
    """
    world = response_loop
    world.own_course_required()
    world.stand(CLEAR_PAST)
    assert world.policy_set(world.lead, ENCOURAGED).status_code == OK
    world.stand(OWED_AFTER + HTTP_MARGIN)

    entries = world.owed_entries(world.lead)

    listed = {(str(e[OWED_SECTION_ID]), e[OWED_COURSE_WEEK]) for e in entries}
    assert (str(world.hold.taught), ON_BEHALF_WEEK) in listed, (
        f"The owed read lists {sorted(listed)} after a toggle to encouraged made after week 1 "
        "opened required. Done-when 5."
    )
