"""The responses-owed read lists only the reader's own owed weeks — E7-03, decision 4 and done-when 9.

> **The responses-owed read.** For a lead or a chair acting as lead, the
> section-weeks in their own courses that are owed now, with the section label
> and the course week, and no instructor name (E9).
>
> **No sibling course.** No route in this ticket reads, sets, lists or publishes
> for a course outside the reader's own `lead_review_courses`. Marked `invariant`.

Work order decision 4: `GET …/responses-owed` → `[{section_id, section_label,
course_week, on_behalf_open}]` over the reader's `lead_review_courses` minus
`taught_or_once_taught_section_ids`; no instructor name, no time stamp.

**A list read can only show a sibling's week by listing it**, so the sibling half
here is an absence — and every absence is asserted beside a presence in the same
read (`docs/MISTAKES.md` entry 3): the reader's own owed week is required to be
listed, so an empty answer cannot pass.

The world: course week 1 of every section, each course required by whoever
answers for it a day before the week opened, nobody has responded, read at +48h
and one minute (`HTTP_MARGIN`, the moving development clock) and again past
+96h.

**Which failure a red is, before E7-03 lands.** `find_route` fails naming the
owed read.
"""

import pytest
from fixtures.lead_review import SIBLING_COHORT, UNMAPPED_COHORT
from fixtures.report_api import TAUGHT_COHORT, UNTAUGHT_COHORT
from fixtures.response_loop_doors import (
    HTTP_MARGIN,
    ON_BEHALF_AFTER,
    ON_BEHALF_WEEK,
    OWED_AFTER,
    OWED_COURSE_WEEK,
    OWED_ON_BEHALF_OPEN,
    OWED_SECTION_ID,
    LoopWorld,
)
from fixtures.staff_names import STAFF_NAMES
from fixtures.the_hold import FIRST_ROW_AFTER_OPENING, INSTRUCTOR, report_opens

pytestmark = [pytest.mark.integration, pytest.mark.invariant]


def every_course_required(world: LoopWorld) -> None:
    world.hold.windows_for(UNTAUGHT_COHORT, ON_BEHALF_WEEK)
    world.hold.windows_for(SIBLING_COHORT, ON_BEHALF_WEEK)
    world.hold.windows_for(UNMAPPED_COHORT, ON_BEHALF_WEEK)
    world.own_course_required()
    world.sibling_course_required()
    world.unmapped_course_required()


def listed(world: LoopWorld, reader: object) -> dict[str, bool]:
    """The reader's owed entries for course week 1, as {section id: on_behalf_open}."""
    entries = world.owed_entries(reader)
    return {
        str(entry[OWED_SECTION_ID]): entry[OWED_ON_BEHALF_OPEN]
        for entry in entries
        if entry[OWED_COURSE_WEEK] == ON_BEHALF_WEEK
    }


def test_a_lead_is_listed_their_own_courses_owed_sections_and_no_sibling_leads(
    response_loop: LoopWorld,
) -> None:
    """At +48h: lead A is listed `F1WW` and `Q1WW`, on-behalf shut; never the sibling's or the chair's.

    **The mutations this kill:** the list drawn over the prefix or the department
    (the sibling course's section, or the unmapped one, listed for A — §4.1 item 2);
    `on_behalf_open` true at +48h. **The near miss:** A's own two sections, listed.
    """
    world = response_loop
    every_course_required(world)
    world.stand(OWED_AFTER + HTTP_MARGIN)

    found = listed(world, world.lead)

    assert found == {str(world.hold.taught): False, str(world.hold.sibling_section): False}, (
        f"Lead A's owed read at +48h lists {found}; A's course holds `F1WW` and `Q1WW`, owed and "
        "not yet open on behalf. The sibling lead's and the unled course's sections are never A's."
    )


def test_a_chair_acting_as_lead_is_listed_the_unled_courses_section_only(
    response_loop: LoopWorld,
) -> None:
    """Past +96h: the chair is listed the unmapped course's section, on-behalf open; no led course.

    **The mutation this kills:** a chair's list over the whole department (the two
    led courses' sections listed). **The near miss:** the unled course's section,
    listed and open.
    """
    world = response_loop
    every_course_required(world)
    world.stand(ON_BEHALF_AFTER + HTTP_MARGIN)

    found = listed(world, world.chair)

    assert found == {str(world.hold.unmapped_section): True}, (
        f"The chair's owed read past +96h lists {found}; the chair acts as lead for the unled "
        "course's section only."
    )


def test_a_section_the_lead_teaches_is_not_listed_and_the_courses_other_section_is(
    response_loop: LoopWorld,
) -> None:
    """Lead A also teaches `F1WW`: A's list holds `Q1WW` and not `F1WW`.

    **The mutation this kills:** the list over `lead_review_courses` without
    removing `taught_or_once_taught_section_ids`. **The near miss:** `Q1WW`.
    """
    world = response_loop
    every_course_required(world)
    world.review.teaches(world.lead, TAUGHT_COHORT)
    world.stand(OWED_AFTER + HTTP_MARGIN)

    found = listed(world, world.lead)

    assert found == {str(world.hold.sibling_section): False}, (
        f"Lead A, who teaches `F1WW`, is listed {found}. Decision 4: minus the sections the reader "
        "teaches or has taught."
    )


def test_an_answered_week_is_not_listed(response_loop: LoopWorld) -> None:
    """The teacher answered `F1WW`'s week: A's list holds `Q1WW` only.

    **The mutation this kills:** the list ignoring the response. **The near miss:**
    `Q1WW`, unanswered, listed.
    """
    world = response_loop
    every_course_required(world)
    world.hold.a_response(
        section_id=world.hold.taught,
        course_week=ON_BEHALF_WEEK,
        author=world.teacher_id,
        role=INSTRUCTOR,
        body="E7-03 answered before the owed read",
        published_at=report_opens(ON_BEHALF_WEEK) + FIRST_ROW_AFTER_OPENING,
    )
    world.stand(OWED_AFTER + HTTP_MARGIN)

    found = listed(world, world.lead)

    assert found == {str(world.hold.sibling_section): False}, f"Lead A is listed {found}."


def test_the_owed_read_names_no_instructor(response_loop: LoopWorld) -> None:
    """Past +96h, A's owed read carries none of this world's planted staff names.

    **The mutation this kills:** an instructor name on the entry (E9's). **The near
    miss:** the read is required to list A's two sections first, so a clean body
    is a read that carried something.
    """
    world = response_loop
    every_course_required(world)
    world.stand(ON_BEHALF_AFTER + HTTP_MARGIN)

    found = listed(world, world.lead)
    answered = world.owed(world.lead)

    assert set(found) == {str(world.hold.taught), str(world.hold.sibling_section)}, found
    named = [name for name in STAFF_NAMES if name in answered.text]
    assert not named, f"The owed read names {named}. Decision 4: no instructor name."
