"""The results payload carries the student's own latest accepted score, as posted (SPEC §3.3, §3.4).

`participation` is the newest `grade_sync` row of outcome `posted` for the
session's own user in the section being read, absent before the first post and
served in a held week too. Every read goes through the built application, which
connects as `pulse_app`, so the table's grant is exercised and not the migrating
connection's (`docs/MISTAKES.md` entry 46).

**The isolation tests moved out** (E8-05 done-when 2): a later failed row, a
classmate's row and the reader's row in another section are asserted in
`test_the_participation_score_names_nothing_but_the_readers_own_row.py`, inside
the isolated invariant pass.
"""

from datetime import timedelta
from typing import Any

import pytest
from fixtures.the_hold import (
    AWAITING,
    HELD_WEEK,
    LEAD_FACULTY,
    PARTICIPATION,
    REQUIRED,
    STATE,
    WEEK_BEFORE,
    HoldWorld,
    report_opens,
)

pytestmark = pytest.mark.integration

SECOND = ("61.50", "Week 1: 3 of 3 items; Week 2: 1 of 3 items")
LATER_FAILED = ("40.00", "a later attempt that never reached the platform")


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
