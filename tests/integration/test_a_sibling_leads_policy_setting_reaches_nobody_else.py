"""A sibling lead's policy setting reaches nobody else — E7-03, done-when 4 (SPEC §4.1 item 2).

> **A sibling lead's setting reaches nobody else.** Sibling lead B sets prefix P
> to required. Lead A's policy read for P still answers encouraged, carries no
> attribution, and is byte-identical to the read before B's change. A chair's
> read of a course in P with a lead shows only that course's own lead's setting.
> Marked `invariant`.

**A pair of reads either side of B's change** (`docs/MISTAKES.md` entry 51): what A
could learn from the difference is the subject, so the two bodies are compared
byte for byte. Before the comparison means anything, A's read is required to be a
real one — a 200 carrying A's own course — so two identical empty answers cannot
pass (entry 3).

**Which failure a red is, before E7-03 lands.** `find_route` fails naming the
policy routes.
"""

import pytest
from fixtures.lead_review import LEAD_FACULTY_ROLE
from fixtures.response_loop_doors import (
    CAN_SET,
    CLEAR_PAST,
    MODE,
    OK,
    SET_BY_ROLE,
    LoopWorld,
)
from fixtures.staff_names import SIBLING_LEAD_NAME
from fixtures.the_hold import ENCOURAGED, REQUIRED, spellings_of

pytestmark = [pytest.mark.integration, pytest.mark.invariant]


def test_lead_as_policy_read_is_byte_identical_either_side_of_the_sibling_leads_change(
    response_loop: LoopWorld,
) -> None:
    """Read as A; B switches P to required (200); read as A again: the same bytes, encouraged, unattributed.

    **The mutations this kill:** A's read carrying the prefix's latest row whoever
    set it (A reads required); a `set_by_role` or setter name on A's own course;
    the sibling's course listed in A's read (its id, or B's name, anywhere in the
    body); any field that moves with the prefix's history (a count, a time). **The
    near miss:** A's own course in the first read, encouraged and settable — so the
    byte comparison is between two real reads.
    """
    world = response_loop
    world.stand(CLEAR_PAST)
    before = world.policy_read(world.lead)
    own = world.policy_courses(world.lead).get(str(world.hold.own_course))
    assert before.status_code == OK and own is not None, (
        f"Lead A's read answered {before.status_code} and carries no own course "
        f"({before.text[:300]!r}), so a byte comparison below would compare nothing."
    )
    assert (own[MODE], own[CAN_SET], own[SET_BY_ROLE]) == (ENCOURAGED, True, None), own

    changed = world.policy_set(world.sibling_lead, REQUIRED)
    assert changed.status_code == OK, (
        f"Sibling lead B's switch answered {changed.status_code}; the change this test is about "
        "did not happen."
    )
    after = world.policy_read(world.lead)

    assert after.status_code == OK
    assert after.content == before.content, (
        f"Lead A's policy read changed when sibling lead B switched the prefix: before "
        f"{before.text[:300]!r}, after {after.text[:300]!r}. Done-when 4: byte-identical."
    )
    leaked = [
        token
        for token in (SIBLING_LEAD_NAME, *spellings_of(world.hold.sibling_course))
        if token in after.text
    ]
    assert not leaked, f"Lead A's read carries {leaked}, which name the sibling lead's course."


def test_a_chairs_read_of_each_led_course_shows_only_that_courses_own_leads_setting(
    response_loop: LoopWorld,
) -> None:
    """B sets required; the chair reads the sibling course required and the own course encouraged.

    **The mutation this kills:** a chair's read that shows the prefix's latest row
    on every led course (the own course reads required). **The near miss:** the
    sibling course, required and attributed to its lead by role.
    """
    world = response_loop
    world.stand(CLEAR_PAST)
    assert world.policy_set(world.sibling_lead, REQUIRED).status_code == OK

    courses = world.policy_courses(world.chair)

    own = courses.get(str(world.hold.own_course))
    sibling = courses.get(str(world.hold.sibling_course))
    assert own is not None and sibling is not None, (
        f"The chair's read carries {sorted(courses)}; both led courses of the department "
        "belong in it."
    )
    assert (sibling[MODE], sibling[SET_BY_ROLE]) == (REQUIRED, LEAD_FACULTY_ROLE), sibling
    assert own[MODE] == ENCOURAGED, (
        f"The chair reads the own course as {own!r} after the sibling lead's switch. Done-when 4: "
        "a chair's read of a led course shows only that course's own lead's setting."
    )
