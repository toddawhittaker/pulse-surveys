"""The results payload carries the student's own latest accepted score, as posted (SPEC §3.3, §3.4).

`participation` is the newest `grade_sync` row of outcome `posted` for the
session's own user in the section being read: a later `failed` row does not
replace it, a classmate's row and the student's row in another section never
reach it, and it is absent before the first post. Every read goes through the
built application, which connects as `pulse_app`, so the table's grant is
exercised and not the migrating connection's (`docs/MISTAKES.md` entry 46).
"""

from datetime import timedelta
from typing import Any

import pytest
from fixtures.the_hold import (
    AWAITING,
    HELD_WEEK,
    LEAD_FACULTY,
    LIVE_FROM,
    PARTICIPATION,
    REQUIRED,
    STATE,
    WEEK_BEFORE,
    HoldWorld,
    report_opens,
)

pytestmark = pytest.mark.integration

FIRST = ("100.00", "Week 1: 3 of 3 items")
SECOND = ("61.50", "Week 1: 3 of 3 items; Week 2: 1 of 3 items")
LATER_FAILED = ("40.00", "a later attempt that never reached the platform")
CLASSMATES = ("77.70", "the classmate's own ledger")
OTHER_SECTIONS = ("12.30", "the same student's ledger in another section")


def post(
    world: HoldWorld,
    student_id: Any,
    section_id: Any,
    text: tuple[str, str],
    *,
    minutes: int,
    ok: bool,
) -> None:
    """One `grade_sync` row, written as the superuser, `minutes` after the opening of week 1."""
    moment = report_opens(WEEK_BEFORE) + timedelta(minutes=minutes)
    world.rows.seed(
        "grade_sync",
        {},
        section_id=section_id,
        user_id=student_id,
        score_text=text[0],
        ledger_text=text[1],
        score_timestamp=moment,
        outcome="posted" if ok else "failed",
        response_code=200 if ok else 401,
        created_at=moment,
    )
    world.rows.commit()


def test_the_payload_carries_the_latest_posted_row_as_sent_and_not_a_later_failure(
    hold: HoldWorld,
) -> None:
    """Two posted rows then a failed one: the later posted row, character for character.

    **The mutations this kills:** the newest row of any outcome (the failed one is
    returned); the oldest posted row; a value re-formatted on the way out (`61.50`
    would become `61.5`). **The near miss:** the failed row is the newest of all.
    """
    world = hold
    student = world.a_student("score-own", world.taught)
    post(world, student.user_id, world.taught, FIRST, minutes=1, ok=True)
    post(world, student.user_id, world.taught, SECOND, minutes=2, ok=True)
    post(world, student.user_id, world.taught, LATER_FAILED, minutes=3, ok=False)
    world.stand_after_the_opening(WEEK_BEFORE)

    served = world.payload(student, course_week=WEEK_BEFORE)[PARTICIPATION]

    assert served == {"score_text": SECOND[0], "ledger_text": SECOND[1]}


def test_the_payload_carries_only_the_students_own_row_for_this_section(hold: HoldWorld) -> None:
    """A classmate's later row, and the student's own row in another section, are never served.

    **The mutations this kills:** the lookup keyed by section alone (the classmate's
    later row wins); keyed by user alone (the other section's later row wins).
    """
    world = hold
    student = world.a_student("score-mine", world.taught)
    classmate = world.a_student("score-classmate", world.taught)
    post(world, student.user_id, world.taught, FIRST, minutes=1, ok=True)
    post(world, classmate.user_id, world.taught, CLASSMATES, minutes=2, ok=True)
    # The same user, enrolled in the sibling section too, with a later row there.
    world.names.enrol.enrol(
        user_id=student.user_id,
        section_id=world.sibling_section,
        started_on=LIVE_FROM,
        ended_on=None,
    )
    world.rows.commit()
    post(world, student.user_id, world.sibling_section, OTHER_SECTIONS, minutes=3, ok=True)
    world.stand_after_the_opening(WEEK_BEFORE)

    served = world.payload(student, course_week=WEEK_BEFORE)[PARTICIPATION]
    classmates_view = world.payload(classmate, course_week=WEEK_BEFORE)[PARTICIPATION]

    assert served == {"score_text": FIRST[0], "ledger_text": FIRST[1]}
    assert classmates_view == {"score_text": CLASSMATES[0], "ledger_text": CLASSMATES[1]}


def test_the_member_is_absent_before_the_first_post_and_after_only_failures(
    hold: HoldWorld,
) -> None:
    """No `posted` row: `participation` is null, not a zero and not an empty record."""
    world = hold
    none_yet = world.a_student("score-none", world.taught)
    only_failed = world.a_student("score-failed", world.taught)
    post(world, only_failed.user_id, world.taught, LATER_FAILED, minutes=1, ok=False)
    world.stand_after_the_opening(WEEK_BEFORE)

    assert world.payload(none_yet, course_week=WEEK_BEFORE)[PARTICIPATION] is None
    assert world.payload(only_failed, course_week=WEEK_BEFORE)[PARTICIPATION] is None


def test_the_score_is_served_in_a_held_week_too(hold: HoldWorld) -> None:
    """An `awaiting` week still carries the student's own score: it is not an aggregate."""
    world = hold
    world.a_policy(
        course=world.own_course,
        setter=world.person(world.names.lead).person_id,
        role=LEAD_FACULTY,
        mode=REQUIRED,
        set_at=report_opens(HELD_WEEK) - timedelta(days=1),
    )
    student = world.a_student("score-held", world.taught)
    post(world, student.user_id, world.taught, SECOND, minutes=1, ok=True)
    world.stand_after_the_opening(HELD_WEEK)

    body = world.payload(student, course_week=HELD_WEEK)

    assert body[STATE] == AWAITING
    assert body[PARTICIPATION] == {"score_text": SECOND[0], "ledger_text": SECOND[1]}
