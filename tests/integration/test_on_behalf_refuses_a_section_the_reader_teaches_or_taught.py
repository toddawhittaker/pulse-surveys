"""On behalf refuses a section the reader teaches or has taught — E7-03, done-when 8 (SPEC §4.1).

> **No taught section.** For a lead who also teaches a section of a course they
> lead, every on-behalf route refuses that section with the same 404 as a section
> of a sibling lead's course, and writes no row; the course's other sections are
> served. The same holds for a teaching grant the roster ended. Marked
> `invariant`.

**Refusal, asserted as the same bytes as a sibling's refusal** — the denial shape
§4.1 tests take here: a 404 that differs from the sibling's would tell the reader
which of the two causes it met. **And beside it, the course's other section,
served** to the same reader in the same world, so a door that refuses the reader
everything is red.

**One level out** (`docs/MISTAKES.md` entry 53): a lead whose teaching grant the
roster has ended, and a chair who leads one course and acts as lead for another.
"Taught last term" has no case here: a section belongs to one term, so a section
the reader taught last term is never the current section an on-behalf door is
asked about; the ended grant is this term's once-taught case.

The week is course week 1, past +96h, every course required by whoever answers
for it, nobody answered. The sibling refusal is lead A's (or the chair's) request
for the sibling lead's section — required, unanswered, past +96h, so the only
reason to refuse it is whose it is.

**Which failure a red is, before E7-03 lands.** `find_route` fails naming the
on-behalf route.
"""

from typing import Any

import pytest
from fixtures.lead_review import (
    LEAD_FACULTY_ROLE,
    SIBLING_COHORT,
    UNMAPPED_COHORT,
    Reader,
)
from fixtures.report_api import TAUGHT_COHORT, UNTAUGHT_COHORT
from fixtures.response_loop_doors import (
    CLEAR_PAST,
    NOT_FOUND,
    OK,
    ON_BEHALF_AFTER,
    ON_BEHALF_DOORS,
    ON_BEHALF_READ,
    LoopWorld,
    OnBehalfDoor,
    a_reader_for,
    same_refusal,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]


def windows(world: LoopWorld) -> None:
    for cohort in (UNTAUGHT_COHORT, SIBLING_COHORT, UNMAPPED_COHORT):
        world.hold.windows_for(cohort, 1)


def refused_like_a_sibling(
    world: LoopWorld, door: OnBehalfDoor, reader: Reader, section: Any
) -> tuple[Any, Any, int, int]:
    """The door asked for `section` and for the sibling course's section; both answers, rows, calls."""
    rows, calls = world.response_count(), world.model_calls()
    taught = world.on_behalf(door, reader, section_id=section)
    sibling = world.on_behalf(door, reader, section_id=world.hold.sibling_course_section)
    return taught, sibling, world.response_count() - rows, world.model_calls() - calls


@pytest.mark.parametrize("door", ON_BEHALF_DOORS, ids=lambda door: door.name)
def test_a_lead_who_teaches_a_section_of_their_course_is_refused_it_like_a_siblings(
    response_loop: LoopWorld, door: OnBehalfDoor
) -> None:
    """Lead A teaches `F1WW`: each door's answer for it is the sibling's 404, byte for byte; `Q1WW` is read.

    **The mutations this kill:** the door scoped by `lead_review_courses` alone (A
    reads, drafts over, or publishes into the section they teach); a taught-section
    refusal with its own sentence or status (it tells A which refusal it was); a
    refusal after the model call (decision 6) or after the write. **The near
    miss:** `Q1WW`, the course's other section, read 200 by A.
    """
    world = response_loop
    windows(world)
    world.own_course_required()
    world.sibling_course_required()
    world.review.teaches(world.lead, TAUGHT_COHORT)
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)

    taught, sibling, written, called = refused_like_a_sibling(
        world, door, world.lead, world.hold.taught
    )
    other = world.on_behalf(ON_BEHALF_READ, world.lead, section_id=world.hold.sibling_section)

    assert taught.status_code == NOT_FOUND, (
        f"Lead A's on-behalf {door.name} for `F1WW`, which A teaches, answered "
        f"{taught.status_code}. Done-when 8."
    )
    assert same_refusal(taught, sibling), (
        f"The refusal of the taught section ({taught.text[:200]!r}) is not the refusal of a sibling "
        f"lead's section ({sibling.status_code}, {sibling.text[:200]!r})."
    )
    assert (written, called) == (
        0,
        0,
    ), f"The two refused {door.name} requests wrote {written} rows and made {called} model calls."
    assert other.status_code == OK, (
        f"Lead A's on-behalf read of `Q1WW`, the course's other section, answered "
        f"{other.status_code}; done-when 8: the course's other sections are served."
    )


@pytest.mark.parametrize("door", ON_BEHALF_DOORS, ids=lambda door: door.name)
def test_a_lead_whose_teaching_grant_the_roster_ended_is_refused_that_section(
    response_loop: LoopWorld, door: OnBehalfDoor
) -> None:
    """A former teacher of `F1WW`, now a lead of its course: refused it like a sibling; `Q1WW` read.

    **The mutation this kills:** the taught-section exclusion read from live
    teaching grants only (`teaching_instructor_assigned`), so an ended grant
    re-opens the section. **The near miss:** `Q1WW`.
    """
    world = response_loop
    windows(world)
    world.own_course_required()
    world.sibling_course_required()
    former = world.hold.names.a_former_teacher_of_the_taught_section()
    reader = world.review.a_leader(
        "the-former-teacher-lead",
        grants=((LEAD_FACULTY_ROLE, world.hold.own_course),),
        leads=(world.hold.own_course,),
        person_id=former.person_id,
    )
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)

    taught, sibling, written, called = refused_like_a_sibling(
        world, door, reader, world.hold.taught
    )
    other = world.on_behalf(ON_BEHALF_READ, reader, section_id=world.hold.sibling_section)

    assert taught.status_code == NOT_FOUND and same_refusal(taught, sibling), (
        f"The former teacher's on-behalf {door.name} for the section they once taught answered "
        f"{taught.status_code} {taught.text[:200]!r}; a sibling's section answered "
        f"{sibling.status_code} {sibling.text[:200]!r}. Done-when 8: the same 404."
    )
    assert (written, called) == (0, 0), f"The refusals wrote {written} rows, made {called} calls."
    assert (
        other.status_code == OK
    ), f"The former teacher's read of `Q1WW` answered {other.status_code}."


@pytest.mark.parametrize("door", ON_BEHALF_DOORS, ids=lambda door: door.name)
def test_a_chair_who_leads_and_teaches_is_refused_the_taught_section_only(
    response_loop: LoopWorld, door: OnBehalfDoor
) -> None:
    """The chair leads the own course and teaches `F1WW`: refused it like a sibling; `Q1WW` and the unled section read.

    Entry 53's two-hat person. The chair is made the own course's lead (lead A's
    grant moves to the chair), teaches `F1WW`, and still acts as lead for the
    unmapped course.

    **The mutations this kill:** the taught-section exclusion applied under one
    hat and not the other (the lead hat's `F1WW` refused, the chair hat reading
    it through the department); the exclusion widened to the course. **The near
    misses:** `Q1WW` under the lead hat, and the unled section under the chair hat.
    """
    world = response_loop
    windows(world)
    chair = world.chair
    world.hold.move_the_lead(world.hold.own_course, to=chair.person_id)
    world.a_policy_before_the_opening(
        course=world.hold.own_course, setter=chair.person_id, role=LEAD_FACULTY_ROLE
    )
    world.sibling_course_required()
    world.unmapped_course_required()
    world.review.teaches(chair, TAUGHT_COHORT)
    reader = a_reader_for(world, chair.person_id, "the-two-hat-chair")
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)

    taught, sibling, written, called = refused_like_a_sibling(
        world, door, reader, world.hold.taught
    )
    led = world.on_behalf(ON_BEHALF_READ, reader, section_id=world.hold.sibling_section)
    unled = world.on_behalf(ON_BEHALF_READ, reader, section_id=world.hold.unmapped_section)

    assert taught.status_code == NOT_FOUND and same_refusal(taught, sibling), (
        f"The two-hat chair's on-behalf {door.name} for the section they teach answered "
        f"{taught.status_code} {taught.text[:200]!r}; a sibling lead's section answered "
        f"{sibling.status_code} {sibling.text[:200]!r}."
    )
    assert (written, called) == (0, 0), f"The refusals wrote {written} rows, made {called} calls."
    assert (led.status_code, unled.status_code) == (OK, OK), (
        f"The two-hat chair's reads of `Q1WW` and the unled section answered {led.status_code} "
        f"and {unled.status_code}."
    )
