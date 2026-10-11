"""A policy switch through the route holds only the courses the reader answers for — E7-03, done-when 3.

> **Policy scope (rulings 1 and 5).** A lead's switch for a prefix holds the
> courses in it they lead and changes nothing for another lead's course in the
> same prefix. A chair's switch holds the department's unled courses in that
> prefix. A chair's attempt to set the policy of a course with a lead is refused
> and writes no row, and the chair can read that course's setting.

Work order decision 2: `PUT …/response-policy/{prefix_id}` `{mode}` calls 02's
`record_policy` for the reader; 404 with one sentence, and no row, when the reader
can set no course in that prefix. A two-hat lead and chair: the role per course is
what `lead_review_courses` returns for it.

**One level out** (`docs/MISTAKES.md` entry 53): the two-hat person, and a chair of
a *second* department whose read and write must reach nothing in this prefix.

**The rows are read back as the superuser**, by course, so a route that answers
200 and writes for the wrong course is red.

**Which failure a red is, before E7-03 lands.** `find_route` fails naming the
policy routes.

**Two tests carry `invariant`** (E7-10 done-when 7): the lead's switch reaching
nothing of a sibling lead's course, and another department's chair reading and
setting nothing here — SPEC §4.1 item 2's "no sibling course" for the policy
route. The rest are scope rules within the reader's own department.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.lead_review import CHAIR_ROLE, LEAD_FACULTY_ROLE
from fixtures.response_loop_doors import (
    CAN_SET,
    CLEAR_PAST,
    MODE,
    NOT_FOUND,
    OK,
    SET_BY_ROLE,
    LoopWorld,
    a_reader_for,
    same_refusal,
)
from fixtures.staff_names import (
    MODE_COLUMN,
    POLICY_COURSE_COLUMN,
    POLICY_SETTER_COLUMN,
    RESPONSE_POLICY,
    ROLE_COLUMN,
)
from fixtures.the_hold import ENCOURAGED, REQUIRED, sentences_served

pytestmark = pytest.mark.integration


def rows_by_course(world: LoopWorld) -> dict[str, list[tuple[str, str, str]]]:
    """Every policy row, by course: (setter, role, mode), in `sequence` order."""
    found: dict[str, list[tuple[str, str, str]]] = {}
    for course in (world.hold.own_course, world.hold.sibling_course, world.hold.unmapped_course):
        found[str(course)] = [
            (str(row[POLICY_SETTER_COLUMN]), row[ROLE_COLUMN], row[MODE_COLUMN])
            for row in world.hold.rows_of(RESPONSE_POLICY, POLICY_COURSE_COLUMN, course)
        ]
    return found


def assert_success(answered: Any, what: str) -> None:
    assert (
        answered.status_code == OK
    ), f"{what} answered {answered.status_code}, not {OK}. Body {answered.text[:400]!r}."


@pytest.mark.invariant
def test_a_leads_switch_holds_their_course_and_nothing_of_the_sibling_leads(
    response_loop: LoopWorld,
) -> None:
    """Lead A switches the prefix to required: one row, for the own course; none elsewhere.

    **The mutations this kill:** the route writing one row per course in the
    prefix (ruling 1); the route calling `record_policy` with a role other than
    the reader's for the course; the route ignoring the body's mode. **The near
    miss:** the one row A is owed.
    """
    world = response_loop
    world.stand(CLEAR_PAST)

    assert_success(world.policy_set(world.lead, REQUIRED), "Lead A's switch")

    rows = rows_by_course(world)
    lead = str(world.lead.person_id)
    assert rows == {
        str(world.hold.own_course): [(lead, LEAD_FACULTY_ROLE, REQUIRED)],
        str(world.hold.sibling_course): [],
        str(world.hold.unmapped_course): [],
    }, f"Lead A's switch left {rows}. Done-when 3: it holds the course A leads and nothing else."


def test_a_chairs_switch_holds_the_unled_course_only(response_loop: LoopWorld) -> None:
    """The chair switches: one row, for the course with no lead, as `CHAIR`; the led courses none.

    **The mutation this kills:** the chair's switch reaching every course of the
    department (ruling 5: for a course with a lead the chair cannot change it).
    """
    world = response_loop
    world.stand(CLEAR_PAST)

    assert_success(world.policy_set(world.chair, REQUIRED), "The chair's switch")

    rows = rows_by_course(world)
    chair = str(world.chair.person_id)
    assert rows == {
        str(world.hold.own_course): [],
        str(world.hold.sibling_course): [],
        str(world.hold.unmapped_course): [(chair, CHAIR_ROLE, REQUIRED)],
    }, f"The chair's switch left {rows}."


def test_a_chair_with_no_unled_course_in_the_prefix_is_refused_and_can_still_read(
    response_loop: LoopWorld,
) -> None:
    """Every course of the prefix has a lead: the chair's `PUT` is 404, no row; the read shows them.

    The unmapped course is given to lead A, so nothing in the prefix falls to the
    chair. The read is taken after the refusal and shows every course with
    `can_set` false.

    **The mutations this kill:** a refusal that writes first (any row); a chair's
    write that reaches a led course; a chair's read that drops the courses the
    chair cannot set (done-when 3: "the chair can read that course's setting").
    **The near miss:** `test_a_chairs_switch_holds_the_unled_course_only`.
    """
    world = response_loop
    graph = world.review.graph
    graph.assign(LEAD_FACULTY_ROLE, scope=world.hold.unmapped_course, person=world.lead.person_id)
    graph.lead_mapping(person=world.lead.person_id, course=world.hold.unmapped_course)
    world.hold.rows.commit()
    world.stand(CLEAR_PAST)
    before = world.policy_count()

    refused = world.policy_set(world.chair, REQUIRED)

    assert refused.status_code == NOT_FOUND, (
        f"The chair's switch of a prefix with no unled course answered {refused.status_code}, "
        f"not {NOT_FOUND}. Decision 2."
    )
    assert len(sentences_served(refused)) == 1, f"The 404 served {refused.text[:300]!r}."
    assert world.policy_count() == before, "The refused switch wrote a policy row."
    courses = world.policy_courses(world.chair)
    every = {
        str(world.hold.own_course),
        str(world.hold.sibling_course),
        str(world.hold.unmapped_course),
    }
    assert set(courses) == every, (
        f"The chair reads courses {sorted(courses)}; the department's three courses in the prefix "
        f"are {sorted(every)}, each with a lead."
    )
    assert all(
        course[CAN_SET] is False for course in courses.values()
    ), f"The chair's read offers to set {[c for c, v in courses.items() if v[CAN_SET]]}."


def test_a_lead_who_also_chairs_sets_each_course_under_the_role_it_is_held_by(
    response_loop: LoopWorld,
) -> None:
    """Lead A also chairs the department: one switch, a `LEAD_FACULTY` row and a `CHAIR` row.

    Entry 53's two-hat person. The own course is A's as its lead; the unmapped
    course is A's as the chair; the sibling's is neither.

    **The mutations this kill:** one role for every course (the session's first
    grant); a chair hat that reaches the sibling lead's course; a lead hat that
    hides the chair's unled course. **The near miss:** the sibling course, no row.
    """
    world = response_loop
    world.review.graph.assign(
        CHAIR_ROLE, scope=world.review.department, person=world.lead.person_id
    )
    world.hold.rows.commit()
    world.stand(CLEAR_PAST)

    assert_success(world.policy_set(world.lead, REQUIRED), "The two-hat switch")

    rows = rows_by_course(world)
    lead = str(world.lead.person_id)
    assert rows == {
        str(world.hold.own_course): [(lead, LEAD_FACULTY_ROLE, REQUIRED)],
        str(world.hold.sibling_course): [],
        str(world.hold.unmapped_course): [(lead, CHAIR_ROLE, REQUIRED)],
    }, f"The two-hat switch left {rows}. Decision 2: the role per course is the one it is held by."


@pytest.mark.invariant
def test_another_departments_chair_reads_and_sets_nothing_in_this_prefix(
    response_loop: LoopWorld,
) -> None:
    """A chair of a second department: the `PUT` for this prefix is the same 404 as a prefix that is not there.

    Entry 53, one level out from the department.

    **The mutations this kill:** a grant walked up to the college (every chair of
    it answers for every course); a refusal for a real prefix that differs from
    the refusal for an unknown one (which tells a caller the prefix exists).
    **The near miss:** the department's own chair, served in the tests above.
    """
    world = response_loop
    other_chair = world.hold.person(world.hold.names.other_chair)
    other = a_reader_for(world, other_chair.person_id, "other-chair")
    world.stand(CLEAR_PAST)
    before = world.policy_count()

    real = world.policy_set(other, REQUIRED)
    unknown = world.policy_set(other, REQUIRED, prefix=uuid4())
    courses = world.policy_courses(other)

    assert real.status_code == NOT_FOUND, f"The other chair's switch answered {real.status_code}."
    assert same_refusal(real, unknown), (
        f"The refusal for this prefix ({real.text[:200]!r}) differs from the one for a prefix that "
        f"does not exist ({unknown.status_code}, {unknown.text[:200]!r})."
    )
    assert world.policy_count() == before, "The other chair's refused switch wrote a row."
    assert not set(courses) & {
        str(world.hold.own_course),
        str(world.hold.sibling_course),
        str(world.hold.unmapped_course),
    }, f"Another department's chair reads this prefix's courses: {sorted(courses)}."


def test_a_mode_outside_the_vocabulary_is_refused_and_writes_no_row(
    response_loop: LoopWorld,
) -> None:
    """`{mode: "MANDATORY"}` from lead A: a 4xx and no row.

    `docs/MISTAKES.md` entry 29: a value repaired before the check that should
    refuse it. **The mutation this kills:** an unknown mode read as the default
    (`ENCOURAGED`) and written. **The near miss:** the same lead's `REQUIRED`,
    written above.
    """
    world = response_loop
    world.stand(CLEAR_PAST)

    refused = world.policy_set(world.lead, "MANDATORY")

    assert 400 <= refused.status_code < 500, f"An unknown mode answered {refused.status_code}."
    assert world.policy_count() == 0, "An unknown mode was written."


def test_a_chair_reads_a_led_courses_setting_attributed_to_its_lead(
    response_loop: LoopWorld,
) -> None:
    """The sibling lead sets required; the chair's read: that course required, set by `LEAD_FACULTY`.

    **The mutations this kill:** the chair's read of a led course carrying the
    chair's own (unset) default; attribution by name instead of role (E9's);
    `can_set` true on a course the chair cannot set. **The near miss:** the own
    course in the same read — still encouraged.
    """
    world = response_loop
    world.stand(CLEAR_PAST)
    assert_success(world.policy_set(world.sibling_lead, REQUIRED), "The sibling lead's switch")

    courses = world.policy_courses(world.chair)

    sibling = courses.get(str(world.hold.sibling_course))
    own = courses.get(str(world.hold.own_course))
    assert sibling is not None and own is not None, (
        f"The chair's read carries {sorted(courses)}; decision 2 lists a course of the chair's "
        "department that has a lead."
    )
    assert (sibling[MODE], sibling[CAN_SET], sibling[SET_BY_ROLE]) == (
        REQUIRED,
        False,
        LEAD_FACULTY_ROLE,
    ), f"The chair reads the sibling course as {sibling!r}."
    assert (
        own[MODE] == ENCOURAGED and own[CAN_SET] is False
    ), f"The chair reads the own course as {own!r}; nobody set it."
