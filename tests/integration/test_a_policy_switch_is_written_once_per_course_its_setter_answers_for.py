"""A policy switch is written as one row per course its setter answers for — E7-02, decision 1.

Ruling 1: "A Lead Faculty member's switch for a prefix covers only the courses in
that prefix that `authz.lead_review_courses` gives them, and never another lead's
courses there." Ruling 5: the chair sets the policy for a course with no lead.
Work order decision 1 (ADR 0193): a policy row covers one course, fixed when
written; `record_policy(session, *, setter_person_id, role, prefix_id, mode)`
writes one row per course `lead_review_courses` gives the setter in the prefix,
in one transaction, and returns the rows. Decision 7: `set_at` from
`services/clock.now`.

**The rows are verified through the reader they exist for** (`docs/MISTAKES.md`
entry 58): beside the row counts, one test records a switch before a week's
report opens and has a student of each course read that week — the switch's own
course held, the sibling's not.

**What is not tested, and why.** That the rows land "in one transaction": no
failure can be injected between two of the writer's inserts from here, so a
writer committing per row is indistinguishable in these tests from one that does
not. Disclosed in the manifest.

**Which failure a red is, before E7-02 lands.** Every test fails naming
`record_policy` (`the_service`), or M2's `course_id`.
"""

from typing import Any

import pytest
from fixtures.lead_review import SIBLING_COHORT
from fixtures.staff_names import (
    MODE_COLUMN,
    POLICY_COURSE_COLUMN,
    POLICY_PREFIX_COLUMN,
    POLICY_SETTER_COLUMN,
    POLICY_TIME_COLUMN,
    RESPONSE_POLICY,
    ROLE_COLUMN,
)
from fixtures.the_hold import (
    AWAITING,
    CHAIR,
    CLOCK_PROBE_AFTER_OPENING,
    CLOCK_PROBE_WEEK,
    CLOCK_TOLERANCE,
    HELD_WEEK,
    LEAD_FACULTY,
    REQUIRED,
    STATE,
    UNANSWERED,
    WEEK_BEFORE,
    HoldWorld,
    report_opens,
    require_the_policy_course,
)

pytestmark = pytest.mark.integration


def courses_of(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row[POLICY_COURSE_COLUMN]) for row in rows}


def returned_courses(returned: list[Any]) -> set[str]:
    found: set[str] = set()
    for row in returned:
        course = getattr(row, POLICY_COURSE_COLUMN, None)
        if course is None and isinstance(row, dict):
            course = row.get(POLICY_COURSE_COLUMN)
        found.add(str(course))
    return found


def test_a_leads_switch_writes_one_row_for_the_course_they_lead(hold: HoldWorld) -> None:
    """The lead switches the prefix to required: one row, for the own course, and none for the others.

    **The mutations this kill:** one row per course in the prefix (the sibling
    lead's and the chair's courses switched by somebody else — ruling 1); one row
    for the prefix with no course; the mode, role or prefix not carried through.
    **The near miss:** the one row the lead is owed, and the writer's answer naming
    it.
    """
    world = hold
    require_the_policy_course(world.tables)
    lead = world.person(world.names.lead)

    returned = world.record(setter=lead.person_id, role=LEAD_FACULTY, mode=REQUIRED)

    rows = world.rows_of(RESPONSE_POLICY, POLICY_SETTER_COLUMN, lead.person_id)
    assert courses_of(rows) == {str(world.own_course)} and len(rows) == 1, (
        f"The lead's switch wrote rows for courses {courses_of(rows)}; the lead leads "
        f"{world.own_course} and nothing else in the prefix (ruling 1)."
    )
    row = rows[0]
    assert (row[ROLE_COLUMN], row[MODE_COLUMN]) == (LEAD_FACULTY, REQUIRED)
    assert str(row[POLICY_PREFIX_COLUMN]) == str(world.prefix)
    assert returned_courses(returned) == {str(world.own_course)}, (
        f"`record_policy` answered rows for {returned_courses(returned)}; decision 1: the rows it "
        "wrote."
    )
    for other in (world.sibling_course, world.unmapped_course):
        assert not world.rows_of(
            RESPONSE_POLICY, POLICY_COURSE_COLUMN, other
        ), f"A row covers course {other}, which the lead does not lead."


def test_a_chairs_switch_writes_one_row_for_the_course_with_no_lead_only(hold: HoldWorld) -> None:
    """The chair switches as `CHAIR`: one row, for the unmapped course; the two led courses get none.

    **The mutation this kills:** the chair's switch covering every course of the
    department, led or not — ruling 5: "For a course that has a lead, the chair
    reads the policy and cannot change it."
    """
    world = hold
    require_the_policy_course(world.tables)
    chair = world.person(world.names.chair)

    world.record(setter=chair.person_id, role=CHAIR, mode=REQUIRED)

    rows = world.rows_of(RESPONSE_POLICY, POLICY_SETTER_COLUMN, chair.person_id)
    assert courses_of(rows) == {str(world.unmapped_course)} and len(rows) == 1, (
        f"The chair's switch wrote rows for courses {courses_of(rows)}; the chair acts as lead "
        f"for {world.unmapped_course} only."
    )


def test_a_lead_of_two_courses_in_the_prefix_writes_a_row_for_each(hold: HoldWorld) -> None:
    """The lead also takes the unled course: one switch writes two rows, one per course.

    **The mutation this kills:** a writer that writes for the first course it
    finds. **The near miss:** the sibling lead's course, still untouched.
    """
    world = hold
    require_the_policy_course(world.tables)
    lead = world.person(world.names.lead)
    world.review.graph.assign(LEAD_FACULTY, scope=world.unmapped_course, person=lead.person_id)
    world.review.graph.lead_mapping(person=lead.person_id, course=world.unmapped_course)
    world.rows.commit()

    world.record(setter=lead.person_id, role=LEAD_FACULTY, mode=REQUIRED)

    rows = world.rows_of(RESPONSE_POLICY, POLICY_SETTER_COLUMN, lead.person_id)
    expected = {str(world.own_course), str(world.unmapped_course)}
    assert courses_of(rows) == expected and len(rows) == 2, (
        f"The switch wrote rows for {courses_of(rows)} ({len(rows)} rows); the lead leads "
        f"{expected}."
    )


def test_a_switch_recorded_before_the_opening_holds_the_leads_course_and_not_the_siblings(
    hold: HoldWorld,
) -> None:
    """Recorded an hour before course week 2 opens; read an hour after, by a student of each course.

    The writer's rows, read through the reader they exist for (entry 58): the
    own course's student reads `awaiting`, the sibling course's `unanswered`.

    **The mutations this kill:** rows the gate cannot find (a `course_id` the
    gate does not read, a `set_at` that is not the application clock's), and a
    switch that reaches the sibling's course.
    """
    world = hold
    lead = world.person(world.names.lead)
    world.windows_for(SIBLING_COHORT, WEEK_BEFORE, HELD_WEEK)
    ours = world.a_student("switched-own", world.taught)
    theirs = world.a_student("switched-sibling", world.sibling_course_section)
    world.stand_before_the_opening(HELD_WEEK)

    world.record(setter=lead.person_id, role=LEAD_FACULTY, mode=REQUIRED)
    world.stand_after_the_opening(HELD_WEEK)

    our_state = world.payload(ours, course_week=HELD_WEEK)[STATE]
    their_state = world.payload(theirs, course_week=HELD_WEEK)[STATE]

    assert our_state == AWAITING, (
        f"The lead's course read {our_state!r} after the lead switched to required an hour before "
        "the report opened."
    )
    assert (
        their_state == UNANSWERED
    ), f"The sibling lead's course read {their_state!r} under the lead's switch (ruling 1)."


def test_a_switch_stamps_set_at_from_the_application_clock(hold: HoldWorld) -> None:
    """With the development clock at 2026-10-05 13:00 UTC, `set_at` is within minutes of it.

    No real clock will read that instant again, so a `set_at` near it can only be
    the application clock's (decision 7). The policy of record compares `set_at`
    with a report's opening, so a real-clock stamp under a moved development clock
    decides the wrong week.

    **The mutations this kill:** `datetime.now(UTC)` in the writer, and a `now()`
    server default.
    """
    world = hold
    require_the_policy_course(world.tables)
    lead = world.person(world.names.lead)
    pretended = report_opens(CLOCK_PROBE_WEEK) + CLOCK_PROBE_AFTER_OPENING
    world.stand_at(pretended)

    world.record(setter=lead.person_id, role=LEAD_FACULTY, mode=REQUIRED)

    rows = world.rows_of(RESPONSE_POLICY, POLICY_SETTER_COLUMN, lead.person_id)
    assert len(rows) == 1, f"The lead's switch wrote {len(rows)} rows."
    stamped = rows[0][POLICY_TIME_COLUMN]
    assert (
        pretended <= stamped <= pretended + CLOCK_TOLERANCE
    ), f"`set_at` is {stamped}; the application clock read {pretended} when the writer ran."
