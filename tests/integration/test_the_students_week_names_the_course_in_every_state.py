"""The course is named in every state — E8-01, done-when 9 (ruling 2).

> 9. **The course is named in every state,** `awaiting` included, from
>    `section_codes.course_label`.

**The expectation is built out of the rows**, as the survey page's label tests
build theirs (`tests/integration/test_the_student_read_answer_names_the_course.py`):
the section's own prefix, course, section code and term, read back through
their foreign keys and joined with FIX-01 item 2's settled spelling. Never out of
`section_codes.course_label` itself (`docs/MISTAKES.md` entry 19).

**Two sections of one course.** The taught section and its sibling share the
course and the term, and their labels differ only by the section code — so a
label looked up by course, or taken from the first section of the course, gives
one of them the other's.

**Which failure a red is, before E8-01 lands:** `student_week.read` fails naming
the four members the work order adds.
"""

import pytest
from fixtures.report_api import UNTAUGHT_COHORT
from fixtures.student_week import (
    COURSE_LABEL,
    label_of,
    publish_now,
    read,
    required_from_the_first_week,
)
from fixtures.the_hold import AWAITING, PUBLISHED, STATE, UNANSWERED, HoldWorld

pytestmark = pytest.mark.integration

WEEK = 1


def test_the_closed_door_and_the_released_week_both_name_the_sections_course(
    hold: HoldWorld,
) -> None:
    """Course week 1, required: read `awaiting`, publish, read `published`; one label, both times.

    **The mutations this kills:** the label assembled only on a released week
    (inside the branch that builds the figures), so the closed door names
    nothing — ruling 2's whole point; and a label from another source than
    `section_codes.course_label` (a bare course title, or the course number
    without the section code). **The near miss:** the released read, which
    carries the same label.
    """
    world = hold
    required_from_the_first_week(world)
    student = world.a_student("label-every-state", world.taught)
    world.stand_after_the_opening(WEEK)
    expected = label_of(world, world.taught)

    held, _ = read(world, student, WEEK)
    publish_now(world, WEEK, "E8-01 the teacher's reply, so the week is released")
    released, _ = read(world, student, WEEK)

    assert held[STATE] == AWAITING, f"The required, unanswered week read {held[STATE]!r}."
    assert held[COURSE_LABEL] == expected, (
        f"The closed door names {held[COURSE_LABEL]!r}; ruling 2: the course label, "
        f"{expected!r}, in every state."
    )
    assert released[STATE] == PUBLISHED, f"After the publish the week read {released[STATE]!r}."
    assert (
        released[COURSE_LABEL] == expected
    ), f"The released week names {released[COURSE_LABEL]!r}; the label is {expected!r}."


def test_each_section_of_one_course_is_named_with_its_own_section_code(hold: HoldWorld) -> None:
    """The taught section's student and the sibling section's, each reading course week 1.

    **The mutation this kills:** the label looked up by the course (both
    sections' students read one of the two labels). **The near miss:** the
    taught section's own label, which differs from the sibling's only by its
    section code.
    """
    world = hold
    sibling = world.section_id(UNTAUGHT_COHORT)
    mine = label_of(world, world.taught)
    theirs = label_of(world, sibling)
    assert mine != theirs, f"Both sections compose the label {mine!r}; the pair proves nothing."
    own = world.a_student("label-own", world.taught)
    other = world.a_student("label-sibling", sibling)
    world.windows_for(UNTAUGHT_COHORT, WEEK)
    world.stand_after_the_opening(WEEK)

    own_body, _ = read(world, own, WEEK)
    other_body, _ = read(world, other, WEEK)

    assert own_body[STATE] == UNANSWERED and other_body[STATE] == UNANSWERED
    assert own_body[COURSE_LABEL] == mine, f"The taught section reads {own_body[COURSE_LABEL]!r}."
    assert (
        other_body[COURSE_LABEL] == theirs
    ), f"The sibling section reads {other_body[COURSE_LABEL]!r}; its label is {theirs!r}."
