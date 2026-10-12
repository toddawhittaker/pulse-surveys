"""The course pages carry the Lead Faculty name — E9-08, done-when 3 and 4.

> 3. **The lead is named.** A student of a section whose course has a lead sees
>    the lead's name in the results payload in every state, `awaiting` included
>    (a staff name is not a figure about the week); the instructor of that
>    section sees it on the report.
> 4. **No lead, no name.** A course with no lead carries no lead name in either
>    payload, and the header shows none (a page test).

SPEC §2.1: "Course-level pages (instructor report, student results) carry the
Lead Faculty name in the header." The header half of done-when 4 is a frontend
page test and is not here; this module asserts both payloads.

**The world** is E7-02's `hold` (`tests/fixtures/the_hold.py`): the taught
section `F1WW` of the own course, led by `LEAD_NAME` and taught by
`TEACHER_NAME`, under a department whose chair is `CHAIR_NAME`. Every name is
distinctive and planted on exactly one person, so a name found in an answer says
who it is. **No lead** is made by `HoldWorld.move_the_lead(course, to=None)`,
which removes the course's mapping and its lead's grant, so the course falls to
its chair (SPEC §2.1) — read back by that method — and every no-lead test reads
the same page **before** the change as its control, so a `null` afterwards is
about the lead and not about a read that answers `null` to everybody.

**Every read is the reader's own, through the built application**: the student's
results routes, and the teaching instructor's report through the report door.

**Which failure a red is, before E9-08 lands:** `lead_name_in` fails naming the
missing member and the interface; the `ValueError` pair fails naming the missing
door.
"""

import json

import pytest
from fixtures.course_page_lead import (
    lead_name_in,
    report_section,
    the_lead_door,
)
from fixtures.staff_names import CHAIR_NAME, LEAD_NAME, TEACHER_NAME
from fixtures.student_week import instructor_report, publish_now, required_from_the_first_week
from fixtures.the_hold import AWAITING, PUBLISHED, STATE, HoldWorld

pytestmark = pytest.mark.integration

WEEK = 1
TEACHERS_REPLY = "E9-08 the teacher's reply, so the week is released"


def test_the_student_reads_her_courses_lead_on_the_closed_door_and_on_the_released_week(
    hold: HoldWorld,
) -> None:
    """Course week 1, required: `awaiting`, then the teacher publishes: the lead's name both times.

    And the no-week route (E7-02's amendment A2) answers it too, on the same week.

    **The mutations this kills:** the name read inside the branch that builds a
    released week's figures, so the closed door carries none — done-when 3's
    "`awaiting` included", and the reason given there: a staff name is not a
    figure about the week; the name taken from the response's author (the
    teacher publishes here, so that reads `TEACHER_NAME`); and the latest route
    left without it. **The near miss:** the released read, which carries the
    same name.
    """
    world = hold
    required_from_the_first_week(world)
    student = world.a_student("lead-every-state", world.taught)
    world.stand_after_the_opening(WEEK)

    held = world.payload(student, course_week=WEEK)
    publish_now(world, WEEK, TEACHERS_REPLY)
    released = world.payload(student, course_week=WEEK)
    latest = world.latest_payload(student)

    assert held[STATE] == AWAITING, f"The required, unanswered week read {held[STATE]!r}."
    held_name = lead_name_in(held, "The closed door's payload")
    assert held_name == LEAD_NAME, (
        f"The closed door carries `lead_name` = {held_name!r}; the section's course is led by "
        f"{LEAD_NAME!r}. Done-when 3: in every state, `awaiting` included."
    )
    assert released[STATE] == PUBLISHED, f"After the publish the week read {released[STATE]!r}."
    released_name = lead_name_in(released, "The released week's payload")
    assert released_name == LEAD_NAME, (
        f"The released week carries `lead_name` = {released_name!r}; the lead is {LEAD_NAME!r}, "
        f"and the response's author ({TEACHER_NAME!r}) is not the lead."
    )
    latest_name = lead_name_in(latest, "The latest-week route's payload")
    assert (
        latest_name == LEAD_NAME
    ), f"The no-week route carries `lead_name` = {latest_name!r}; the lead is {LEAD_NAME!r}."


def test_the_instructor_reads_her_courses_lead_on_her_report(hold: HoldWorld) -> None:
    """The teaching instructor's own report of `F1WW`: `section.lead_name` is the course's lead.

    **The mutations this kills:** the report payload left without the member (only
    the student page given it); the name asked for with a key the instructor's
    session does not carry, so the door refuses and the member reads `null`; and
    the instructor's own name put in its place. **The near miss:** the teacher's
    name, which E9-03's door answers to the same reader for the same section,
    one role row away.
    """
    world = hold
    world.stand_after_the_opening(WEEK)

    section = report_section(instructor_report(world, WEEK), "The instructor's report")

    found = lead_name_in(section, "The report's `section` member")
    assert found == LEAD_NAME, (
        f"The instructor's report carries `section.lead_name` = {found!r}; the section's course is "
        f"led by {LEAD_NAME!r}. Done-when 3: the instructor of that section sees it on the report."
    )


def test_a_course_with_no_lead_gives_its_student_a_null_lead_name_and_not_its_chair(
    hold: HoldWorld,
) -> None:
    """The same student, the same week, before and after the course loses its lead.

    Before: `LEAD_NAME` (the control). After `move_the_lead(own_course, to=None)`:
    the member is present and `null`, and the chair the course now falls to is
    named nowhere in the payload.

    **The mutations this kills:** the course's responsible person read instead of
    its lead, so an unled course shows its chair under a "Lead Faculty" heading
    (E9-03's door answers the chair a `CHAIR` row for this section); a
    placeholder string ("", "None", "No lead") in place of `null`; and the member
    dropped when there is no lead. **The near miss:** the read before the change,
    which carries the lead.
    """
    world = hold
    student = world.a_student("no-lead", world.taught)
    world.stand_after_the_opening(WEEK)
    before = world.payload(student, course_week=WEEK)
    read_before = lead_name_in(before, "The payload before the change")
    assert read_before == LEAD_NAME, (
        f"Before the course lost its lead the student read `lead_name` = {read_before!r}, not "
        f"{LEAD_NAME!r}, so a `null` afterwards would prove nothing about the lead."
    )

    world.move_the_lead(world.own_course, to=None)
    after = world.payload(student, course_week=WEEK)

    found = lead_name_in(after, "The payload after the course lost its lead")
    assert found is None, (
        f"A course with no lead carries `lead_name` = {found!r}. Done-when 4: no lead name, and no "
        "placeholder — the member is `null`."
    )
    assert CHAIR_NAME not in json.dumps(after, ensure_ascii=False), (
        f"The unled course's payload names its chair ({CHAIR_NAME!r}). The course falls to the "
        "chair (SPEC §2.1), but the header names the Lead Faculty, and there is none."
    )


def test_a_course_with_no_lead_gives_its_instructor_a_null_lead_name_and_not_her_chair(
    hold: HoldWorld,
) -> None:
    """The teacher's report, before and after the course loses its lead: the lead, then `null`.

    **The mutations this kill:** the instructor's report reading the chair (or
    any `CHAIR` row the door answers) as the lead of an unled course; a
    placeholder; the member dropped. **The near miss:** the report before the
    change, which carries the lead.
    """
    world = hold
    world.stand_after_the_opening(WEEK)
    before = report_section(instructor_report(world, WEEK), "The report before the change")
    read_before = lead_name_in(before, "The report's `section` before the change")
    assert read_before == LEAD_NAME, (
        f"Before the course lost its lead the report read `section.lead_name` = "
        f"{read_before!r}, not {LEAD_NAME!r}; a `null` afterwards would prove nothing."
    )

    world.move_the_lead(world.own_course, to=None)
    after = report_section(instructor_report(world, WEEK), "The report after the change")

    found = lead_name_in(after, "The report's `section` after the course lost its lead")
    assert found is None, (
        f"A course with no lead carries `section.lead_name` = {found!r} on the instructor's "
        "report. Done-when 4: no lead name and no placeholder."
    )
    assert CHAIR_NAME not in json.dumps(after, ensure_ascii=False), (
        f"The unled course's report `section` names its chair ({CHAIR_NAME!r}) as if it were "
        "the lead."
    )


@pytest.mark.parametrize("keys", ["neither", "both"])
def test_the_lead_door_refuses_a_call_that_names_no_reader_or_two(
    hold: HoldWorld, keys: str
) -> None:
    """`section_lead_name` with neither reader key, or with both: `ValueError` (the interface).

    **The mutation this kills:** a door that answers a call naming no reader — the
    shape in which a caller forgets the key and the name is read for nobody in
    particular — or one that accepts both keys and picks whichever admits more.
    **The near miss:** every other test here, which passes exactly one key and is
    answered.
    """
    world = hold
    door = the_lead_door()
    teacher = world.person(world.names.teacher)
    student = world.a_student(f"lead-door-{keys}", world.taught)
    readers = (
        {}
        if keys == "neither"
        else {"reader_user_id": student.user_id, "reader_person_id": teacher.person_id}
    )

    # E9-14 item 4: `scope` is a required keyword, so it is passed (as an own
    # page passes it) and the refusal is about the reader keys alone.
    with pytest.raises(ValueError):
        door(world.application_session, section_id=world.taught, scope=None, **readers)
    world.application_session.rollback()
