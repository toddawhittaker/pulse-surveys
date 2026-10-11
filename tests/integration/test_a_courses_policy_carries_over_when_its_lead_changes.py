"""A course's response policy carries over when its lead changes — E7-10 done-when 9.

> SPEC §5.3 says a course's setting carries over when its lead changes, with a
> test and an ADR 0193 line.

Work-order decision 6 settles the test: the chair sets REQUIRED on an unled
course; then a lead is mapped to it with no row of their own; the next week's
report holds; the lead's policy read shows mode REQUIRED and `can_set` true.

**Why it is the rule.** ADR 0193: a policy row covers one course, fixed when it is
written, and the policy in force for a course is its latest row whoever wrote it.
So the chair's row keeps governing the course after it gains a lead, until the
new lead writes one — and the lead, now responsible, sees it and may change it.

**The world.** The unmapped course (cohort `4`, no lead, so its chair's) under the
one prefix; a student of its section; survey windows for course weeks 1 and 2.
The chair switches the prefix through the policy route an hour after week 1's
report opened, so week 1's policy of record is the default and week 2's is the
chair's row. Lead A is then given the course (the `LEAD_FACULTY` assignment and
the lead mapping, as `LeadReviewWorld.a_leader` writes both) and writes nothing.

**Which failure a red is.** Expected green on the epic head if the policy of
record is already "latest row for the course"; red on the lead's read if it
attributes, filters or offers the switch by the setter's current responsibility.
It is the test the boundary review found missing for a rule SPEC §5.3 did not yet
state.
"""

import pytest
from fixtures.lead_review import LEAD_FACULTY_ROLE, UNMAPPED_COHORT
from fixtures.response_loop_doors import (
    CAN_SET,
    CLEAR_PAST,
    MODE,
    NEXT_WEEK,
    OK,
    ON_BEHALF_WEEK,
    LoopWorld,
)
from fixtures.staff_names import POLICY_COURSE_COLUMN, POLICY_SETTER_COLUMN, RESPONSE_POLICY
from fixtures.the_hold import AWAITING, REQUIRED, STATE

pytestmark = pytest.mark.integration


def test_a_chairs_required_setting_holds_a_course_after_a_lead_is_mapped_to_it(
    response_loop: LoopWorld,
) -> None:
    """Chair sets REQUIRED; a lead is mapped with no row; the next week holds; the lead reads REQUIRED, `can_set` true.

    **The mutations this kills:** the policy of record filtered to rows whose
    setter is still responsible for the course (the chair's row dropped once a
    lead exists, so week 2 is released); the lead's read showing the default
    because no row is theirs; `can_set` computed from "the reader wrote a row"
    rather than from responsibility. **The near miss, in the same world:** course
    week 1, whose report opened before the chair's switch, which does not hold.
    """
    world = response_loop
    hold = world.hold
    hold.windows_for(UNMAPPED_COHORT, ON_BEHALF_WEEK, NEXT_WEEK)
    student = hold.a_student("e7-10-carry-over", hold.unmapped_section)
    world.stand(CLEAR_PAST)

    switched = world.policy_set(world.chair, REQUIRED)
    assert switched.status_code == OK, (
        f"The chair's switch of the prefix answered {switched.status_code}. Body "
        f"{switched.text[:300]!r}."
    )
    graph = world.review.graph
    graph.assign(LEAD_FACULTY_ROLE, scope=hold.unmapped_course, person=world.lead.person_id)
    graph.lead_mapping(person=world.lead.person_id, course=hold.unmapped_course)
    hold.rows.commit()
    rows = hold.rows_of(RESPONSE_POLICY, POLICY_COURSE_COLUMN, hold.unmapped_course)

    world.stand(CLEAR_PAST, course_week=NEXT_WEEK)
    before_the_switch = hold.payload(student, course_week=ON_BEHALF_WEEK)[STATE]
    next_week = hold.payload(student, course_week=NEXT_WEEK)[STATE]
    courses = world.policy_courses(world.lead)

    assert [str(row[POLICY_SETTER_COLUMN]) for row in rows] == [str(world.chair.person_id)], (
        f"The unled course's policy rows are set by {[row[POLICY_SETTER_COLUMN] for row in rows]}; "
        "this case needs exactly the chair's, and none of the new lead's. A broken world."
    )
    assert before_the_switch != AWAITING, (
        f"Course week 1, whose report opened before the chair's switch, reads {before_the_switch!r}: "
        "the hold below would then not be the chair's row's doing."
    )
    assert next_week == AWAITING, (
        f"Course week 2 of the newly led course reads {next_week!r}. Done-when 9: a course's setting "
        "carries over when its lead changes, so the chair's REQUIRED row still holds the week."
    )
    course = courses.get(str(hold.unmapped_course))
    assert (
        course is not None
    ), f"Lead A's policy read carries {sorted(courses)}, not the course they now lead."
    assert (course[MODE], course[CAN_SET]) == (REQUIRED, True), (
        f"Lead A reads the course they now lead as {course!r}. Done-when 9 (work-order decision "
        "6): mode REQUIRED, carried over from the chair's row, and `can_set` true."
    )
