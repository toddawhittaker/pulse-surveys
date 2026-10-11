"""SPEC §14.3's exit for the response loop, in the pytest world, with the two tables read directly.

"A required-mode section shows nothing to students until a named human
publishes." `tests/e2e/exit-response-loop.spec.ts` drives the clause on the
running stack. This module walks the same story through the built
application's routes, and then reads `response_policy` and
`instructor_response` as the superuser, never trusting a route's answer about
what it wrote (`docs/MISTAKES.md` entry 58).

The world is `tests/fixtures/response_loop_doors.py`'s: section `F1WW`
of the own course, taught by `TEACHER_NAME` and led, not taught, by
`LEAD_NAME`. The story, on the moving development clock:

  1. Before course week 1's report opens, the lead switches the prefix to
     required through the policy route.
  2. An hour after course week 2's report opens, a student of the section reads
     both weeks closed: `awaiting`, and no response.
  3. The teacher publishes week 2 through the instructor's route; the student
     reads it under the teacher's name. The teacher edits it; the student reads
     the new text, and the week is still released.
  4. Week 1, now well past report open plus 96 hours, has no response; the
     lead publishes on behalf, and the student reads the lead's name and role.
"""

import pytest
from fixtures.response_loop_doors import (
    CREATED,
    OK,
    ON_BEHALF_PUBLISH,
    LoopWorld,
)
from fixtures.staff_names import (
    LEAD_NAME,
    MODE_COLUMN,
    POLICY_COURSE_COLUMN,
    POLICY_SETTER_COLUMN,
    RESPONSE_AUTHOR_COLUMN,
    RESPONSE_BODY_COLUMN,
    RESPONSE_POLICY,
    ROLE_COLUMN,
    TEACHER_NAME,
    WEEK_COLUMN,
)
from fixtures.the_hold import (
    AUTHOR_NAME,
    AUTHOR_ROLE,
    AWAITING,
    INSTRUCTOR,
    LEAD_FACULTY,
    ON_BEHALF,
    PUBLISHED,
    REQUIRED,
    RESPONSE,
    STATE,
    TEXT,
)

pytestmark = pytest.mark.integration

ON_BEHALF_WEEK = 1
INSTRUCTORS_WEEK = 2

FIRST = "The exit story's first version: the lab report is due on Thursday."
EDITED = "The exit story's edit: the lab report is due on Friday, not Thursday."
LEADS = "The exit story's on-behalf response: we have heard you about the pacing."


def test_a_required_week_is_closed_until_the_teacher_publishes_and_then_the_lead_on_behalf(
    response_loop: LoopWorld,
) -> None:
    world = response_loop
    hold = world.hold
    section = hold.taught
    lead = str(world.lead.person_id)
    teacher = str(world.teacher_id)

    hold.stand_before_the_opening(ON_BEHALF_WEEK)
    switched = world.policy_set(world.lead, REQUIRED)
    assert switched.status_code == OK, (
        f"The lead's switch answered {switched.status_code}. Body {switched.text[:400]!r}."
    )
    policies = [
        (str(row[POLICY_COURSE_COLUMN]), str(row[POLICY_SETTER_COLUMN]), row[MODE_COLUMN])
        for row in hold.rows_of(RESPONSE_POLICY, POLICY_SETTER_COLUMN, world.lead.person_id)
    ]
    assert policies == [(str(hold.own_course), lead, REQUIRED)], (
        f"The lead's switch stored {policies}; expected one required row for the course they lead."
    )

    student = hold.a_student("exit", section)
    hold.stand_after_the_opening(INSTRUCTORS_WEEK)
    for course_week in (ON_BEHALF_WEEK, INSTRUCTORS_WEEK):
        closed = hold.payload(student, course_week=course_week)
        assert (closed[STATE], closed[RESPONSE]) == (AWAITING, None), (
            f"Course week {course_week}, required and unanswered, read {closed!r}: the closed "
            "door has no response, no name and no text."
        )
    assert world.responses_of(section) == [], "Nothing is published yet, so no row exists."

    published = world.instructor("POST", text=FIRST, course_week=INSTRUCTORS_WEEK)
    assert published.status_code == CREATED, (
        f"The teacher's publish answered {published.status_code}. Body {published.text[:400]!r}."
    )
    after_publish = hold.payload(student, course_week=INSTRUCTORS_WEEK)
    edited = world.instructor("PUT", text=EDITED, course_week=INSTRUCTORS_WEEK)
    assert edited.status_code == OK, (
        f"The teacher's edit answered {edited.status_code}. Body {edited.text[:400]!r}."
    )
    after_edit = hold.payload(student, course_week=INSTRUCTORS_WEEK)
    still_closed = hold.payload(student, course_week=ON_BEHALF_WEEK)

    assert (
        after_publish[STATE],
        after_publish[RESPONSE][TEXT],
        after_publish[RESPONSE][AUTHOR_NAME],
        after_publish[RESPONSE][AUTHOR_ROLE],
    ) == (PUBLISHED, FIRST, TEACHER_NAME, INSTRUCTOR)
    assert (
        after_edit[STATE],
        after_edit[RESPONSE][TEXT],
        after_edit[RESPONSE][AUTHOR_NAME],
    ) == (PUBLISHED, EDITED, TEACHER_NAME), (
        f"After the edit the student read {after_edit!r}: the new text, still released."
    )
    assert still_closed[STATE] == AWAITING, (
        f"The teacher's publish of week {INSTRUCTORS_WEEK} released week {ON_BEHALF_WEEK} too: "
        f"{still_closed!r}."
    )

    on_behalf = world.on_behalf(
        ON_BEHALF_PUBLISH, world.lead, section_id=section, course_week=ON_BEHALF_WEEK, text=LEADS
    )
    assert on_behalf.status_code == CREATED, (
        f"The lead's on-behalf publish answered {on_behalf.status_code}. Body "
        f"{on_behalf.text[:400]!r}."
    )
    answered = hold.payload(student, course_week=ON_BEHALF_WEEK)
    assert (
        answered[STATE],
        answered[RESPONSE][TEXT],
        answered[RESPONSE][AUTHOR_NAME],
        answered[RESPONSE][AUTHOR_ROLE],
    ) == (ON_BEHALF, LEADS, LEAD_NAME, LEAD_FACULTY)

    stored = [
        (
            str(row[WEEK_COLUMN]),
            str(row[RESPONSE_AUTHOR_COLUMN]),
            row[ROLE_COLUMN],
            row[RESPONSE_BODY_COLUMN],
        )
        for row in world.responses_of(section)
    ]
    instructors_week = str(hold.week_id(INSTRUCTORS_WEEK))
    on_behalf_week = str(hold.week_id(ON_BEHALF_WEEK))
    assert stored == [
        (instructors_week, teacher, INSTRUCTOR, FIRST),
        (instructors_week, teacher, INSTRUCTOR, EDITED),
        (on_behalf_week, lead, LEAD_FACULTY, LEADS),
    ], f"The section's response rows, by sequence, are {stored}."
