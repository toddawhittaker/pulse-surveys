"""The one writer appends a response row and decides nothing else — E7-02, "The one writer".

The ticket: "A service function that appends a response row and nothing else. It
has no route of its own; 03's routes call it after their own checks. It does not
decide who may publish; it refuses only what the table would refuse, so that the
checks live in one place, the doors (03)."

Work order decision 6: `publish_response(session, *, section_id, course_week,
author_person_id, role, ai_seeded, body) -> InstructorResponse` appends one row,
`term_id` derived from the section; the trigger is the only role check. Decision
7: `published_at` is written from `services/clock.now`.

Every call is made on `pulse_app`'s own connection (`application_session`,
`docs/MISTAKES.md` entry 46) and committed; every row is read back on the
superuser connection.

**Which failure a red is, before E7-02 lands.** Every test fails naming
`publish_response` (`the_service`).
"""

from typing import Any

import pytest
from fixtures.staff_names import (
    AI_SEEDED_COLUMN,
    INSTRUCTOR_RESPONSE,
    RESPONSE_AUTHOR_COLUMN,
    RESPONSE_BODY_COLUMN,
    RESPONSE_POLICY,
    RESPONSE_SECTION_COLUMN,
    RESPONSE_TERM_COLUMN,
    RESPONSE_TIME_COLUMN,
    ROLE_COLUMN,
    WEEK_COLUMN,
    sqlstate,
)
from fixtures.the_hold import (
    CLOCK_PROBE_AFTER_OPENING,
    CLOCK_PROBE_WEEK,
    CLOCK_TOLERANCE,
    HELD_WEEK,
    INSTRUCTOR,
    LEAD_FACULTY,
    NOT_A_REFUSAL,
    PUBLISH_WRITER,
    HoldWorld,
    report_opens,
    the_response_model,
    the_service,
)

pytestmark = pytest.mark.integration

WRITTEN_TEXT = "E7-02 written through the one writer"
REFUSED_TEXT = "E7-02 a sibling lead's response the table refuses"
ON_BEHALF_TEXT = "E7-02 the lead's response an hour after the report opened"


def test_the_writer_appends_one_row_naming_the_sections_term_and_the_course_weeks_week(
    hold: HoldWorld,
) -> None:
    """One call, one new row in the whole table, and nothing written anywhere else.

    Course week 2 of `F1WW` is term week 8: the row's week is term week 8's, so a
    writer that took `course_week` as a term week number (term week 2) names the
    wrong week. `term_id` is the section's own term.

    **The mutations this kill:** `course_week` read as a term week; `term_id`
    left to a default or taken from somewhere other than the section; a writer
    that also writes a policy row, or two response rows; `ai_seeded` or the body
    dropped. **The near miss:** the returned object, an `InstructorResponse`
    carrying the row it wrote.
    """
    world = hold
    teacher = world.person(world.names.teacher)
    world.stand_after_the_opening(HELD_WEEK)
    responses_before = world.count(INSTRUCTOR_RESPONSE)
    policies_before = world.count(RESPONSE_POLICY)

    written = world.publish(
        section_id=world.taught,
        course_week=HELD_WEEK,
        author=teacher.person_id,
        role=INSTRUCTOR,
        body=WRITTEN_TEXT,
        ai_seeded=True,
    )

    assert isinstance(
        written, the_response_model()
    ), f"`{PUBLISH_WRITER}` answered {type(written).__name__}; decision 6: an `InstructorResponse`."
    assert (
        world.count(INSTRUCTOR_RESPONSE) == responses_before + 1
    ), "The writer did not append exactly one `instructor_response` row."
    assert world.count(RESPONSE_POLICY) == policies_before, "The writer wrote a policy row."
    rows = world.rows_of(INSTRUCTOR_RESPONSE, RESPONSE_SECTION_COLUMN, world.taught)
    assert len(rows) == 1, f"`F1WW` holds {len(rows)} response rows after one call."
    row = rows[0]
    assert str(row[WEEK_COLUMN]) == str(world.week_id(HELD_WEEK)), (
        f"The row names week {row[WEEK_COLUMN]}; course week {HELD_WEEK} of `F1WW` is term week 8, "
        f"week {world.week_id(HELD_WEEK)}."
    )
    assert str(row[RESPONSE_TERM_COLUMN]) == str(world.term_id())
    assert str(row[RESPONSE_AUTHOR_COLUMN]) == str(teacher.person_id)
    assert row[ROLE_COLUMN] == INSTRUCTOR
    assert row[AI_SEEDED_COLUMN] is True
    assert row[RESPONSE_BODY_COLUMN] == WRITTEN_TEXT
    assert getattr(written, RESPONSE_BODY_COLUMN, None) == WRITTEN_TEXT


def test_the_writer_refuses_what_the_table_refuses_and_nothing_more(hold: HoldWorld) -> None:
    """A sibling lead as `LEAD_FACULTY` on `F1WW`: refused, no row. The course's lead: written.

    The course's lead writes an hour after the report opens — long before
    SPEC §5.3's +96h, which is the on-behalf door's check (E7-03), not the
    writer's. So the writer is shown refusing the table's refusal and accepting
    a row the table accepts that a door would not.

    **The mutations this kill:** a writer that catches the trigger's refusal and
    writes nothing while reporting success, or retries under another role; and a
    writer that grows its own reader check (the 96h clock, a "who may publish"
    rule), which refuses the lead here and puts a second copy of the doors' rule
    where 03 cannot see it.
    """
    world = hold
    sibling_lead = world.person(world.names.sibling_lead)
    lead = world.person(world.names.lead)
    world.stand_after_the_opening(HELD_WEEK)
    writer = the_service(PUBLISH_WRITER)
    session = world.application_session

    refusal: BaseException | None = None
    try:
        writer(
            session,
            section_id=world.taught,
            course_week=HELD_WEEK,
            author_person_id=sibling_lead.person_id,
            role=LEAD_FACULTY,
            ai_seeded=False,
            body=REFUSED_TEXT,
        )
        session.commit()
    except TypeError as mismatch:
        session.rollback()
        pytest.fail(f"`{PUBLISH_WRITER}` refused decision 6's keywords: {mismatch}")
    except Exception as refused:
        refusal = refused
    session.rollback()

    world.publish(
        section_id=world.taught,
        course_week=HELD_WEEK,
        author=lead.person_id,
        role=LEAD_FACULTY,
        body=ON_BEHALF_TEXT,
    )

    assert refusal is not None, (
        "A sibling lead's LEAD_FACULTY response to `F1WW` was written without complaint. E7-01's "
        "trigger refuses it, and the writer refuses what the table refuses."
    )
    assert sqlstate(refusal) not in NOT_A_REFUSAL, f"The refusal was a broken statement: {refusal}"
    bodies = [
        row[RESPONSE_BODY_COLUMN]
        for row in world.rows_of(INSTRUCTOR_RESPONSE, RESPONSE_SECTION_COLUMN, world.taught)
    ]
    assert bodies == [ON_BEHALF_TEXT], (
        f"`F1WW` holds {bodies}: the refused row must be absent and the lead's present. The lead "
        "wrote an hour after the report opened, and the writer leaves the +96h rule to the door."
    )


def test_the_writer_stamps_the_time_from_the_application_clock(hold: HoldWorld) -> None:
    """With the development clock at 2026-10-05 13:00 UTC, `published_at` is within minutes of it.

    No real clock will read that instant again, so a `published_at` near it can
    only have come from `services/clock.now` (decision 7; ADR 0192: "The two time
    columns are written by the application from `services/clock.now`, so the
    development clock stays coherent").

    **The mutations this kill:** `datetime.now(UTC)` in the writer, and a `now()`
    server default — both write the real instant, days or months away.
    """
    world = hold
    teacher = world.person(world.names.teacher)
    pretended = report_opens(CLOCK_PROBE_WEEK) + CLOCK_PROBE_AFTER_OPENING
    world.stand_at(pretended)

    world.publish(
        section_id=world.taught,
        course_week=CLOCK_PROBE_WEEK,
        author=teacher.person_id,
        role=INSTRUCTOR,
        body=WRITTEN_TEXT,
    )

    rows = world.rows_of(INSTRUCTOR_RESPONSE, RESPONSE_SECTION_COLUMN, world.taught)
    assert len(rows) == 1, f"`F1WW` holds {len(rows)} response rows after one call."
    stamped: Any = rows[0][RESPONSE_TIME_COLUMN]
    assert pretended <= stamped <= pretended + CLOCK_TOLERANCE, (
        f"`published_at` is {stamped}; the application clock read {pretended} when the writer ran. "
        "Decision 7: the writer stamps the time from `services/clock.now`."
    )
