"""A student's posted score names nothing but the reader's own row — E8-05, done-when 2.

> 2. **A student's score names nothing but the reader's own row.** The
>    participation isolation test (a classmate's row, the same student's row in
>    another section, a later failed row) moves into an `invariant`-marked module
>    named for the denial, asserting in its body.

`participation` is the newest `grade_sync` row of outcome `posted` for the
session's own user in the section being read (ruling 4, SPEC §3.3 and §5.4). A
classmate's row is another person's grade: serving it on this page would be the
one place in the student surface that names an individual's data (§4.1, §5.4:
"never other individuals' raw identifiable data"). So the isolation half lives
in CI's isolated §4.1 pass, where a skip is a failure, and the module name
carries the denial shape that demands the marker.

Moved here from `test_the_results_payload_carries_the_students_own_posted_score.py`,
which keeps the absence and held-week tests. **Each denial sits beside its
present twin in the same world**: the reader's own row is served, and the
classmate reads their own row, so an empty answer cannot pass (`docs/MISTAKES.md`
entry 3). Every read goes through the built application as `pulse_app` (entry 46).
"""

from datetime import timedelta
from typing import Any

import pytest
from fixtures.the_hold import (
    LIVE_FROM,
    PARTICIPATION,
    WEEK_BEFORE,
    HoldWorld,
    report_opens,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

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
    """One `grade_sync` row, written as the superuser, `minutes` after the opening of week 1.

    Copied from the module these tests moved out of, which still uses it.
    """
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


def test_the_score_is_the_latest_posted_row_and_never_a_later_failure(hold: HoldWorld) -> None:
    """Two posted rows then a failed one: the later posted row, and no trace of the failure.

    **The mutations this kills:** the newest row of any outcome (the failed
    attempt's score and ledger are served); the oldest posted row; a value
    re-formatted on the way out (`61.50` becoming `61.5`). **The near miss:** the
    failed row is the newest of all, and the posted row before it is served.
    """
    world = hold
    student = world.a_student("score-own", world.taught)
    post(world, student.user_id, world.taught, FIRST, minutes=1, ok=True)
    post(world, student.user_id, world.taught, SECOND, minutes=2, ok=True)
    post(world, student.user_id, world.taught, LATER_FAILED, minutes=3, ok=False)
    world.stand_after_the_opening(WEEK_BEFORE)

    answered = world.results(student, course_week=WEEK_BEFORE)
    served = world.payload(student, course_week=WEEK_BEFORE)[PARTICIPATION]

    assert served == {
        "score_text": SECOND[0],
        "ledger_text": SECOND[1],
    }, f"The student's own latest posted row is {SECOND}; the payload serves {served!r}."
    leaked = [text for text in LATER_FAILED if text in answered.text]
    assert leaked == [], f"The page serves the failed attempt's {leaked}."


def test_the_score_names_neither_a_classmates_row_nor_the_readers_row_in_another_section(
    hold: HoldWorld,
) -> None:
    """A classmate's later row, and the reader's later row in another section, never reach her.

    The classmate reads their own row (the present twin, and the control that
    the classmate's row is servable at all); the reader reads hers, and neither
    the classmate's score and ledger nor her other section's appear anywhere in
    what she was served.

    **The mutations this kills:** the lookup keyed by section alone (the
    classmate's later row wins); keyed by user alone (the other section's later
    row wins); and the latest row of the section served "as a class figure".
    **The near misses:** the reader's own row, and the classmate's own read.
    """
    world = hold
    student = world.a_student("score-mine", world.taught)
    classmate = world.a_student("score-classmate", world.taught)
    post(world, student.user_id, world.taught, FIRST, minutes=1, ok=True)
    post(world, classmate.user_id, world.taught, CLASSMATES, minutes=2, ok=True)
    world.names.enrol.enrol(
        user_id=student.user_id,
        section_id=world.sibling_section,
        started_on=LIVE_FROM,
        ended_on=None,
    )
    world.rows.commit()
    post(world, student.user_id, world.sibling_section, OTHER_SECTIONS, minutes=3, ok=True)
    world.stand_after_the_opening(WEEK_BEFORE)

    answered = world.results(student, course_week=WEEK_BEFORE)
    served = world.payload(student, course_week=WEEK_BEFORE)[PARTICIPATION]
    classmates_view = world.payload(classmate, course_week=WEEK_BEFORE)[PARTICIPATION]

    assert classmates_view == {
        "score_text": CLASSMATES[0],
        "ledger_text": CLASSMATES[1],
    }, f"The classmate reads {classmates_view!r}, not their own row. A broken world, not a red."
    assert served == {
        "score_text": FIRST[0],
        "ledger_text": FIRST[1],
    }, f"The reader's own row in this section is {FIRST}; the payload serves {served!r}."
    leaked = [text for text in (*CLASSMATES, *OTHER_SECTIONS) if text in answered.text]
    assert leaked == [], f"The reader's page serves another row's {leaked}."
