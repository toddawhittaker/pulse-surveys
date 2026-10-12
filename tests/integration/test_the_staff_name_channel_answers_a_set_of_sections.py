"""The staff-name channel over a set of sections — E9-03, done-whens 1, 2, 5 and 6, and the grant.

> 1. A leadership page's names for forty sections are read in one definer call: a
>    query-count test over the door with forty sections counts one call.
> 2. For a seeded section, the rows name its live instructor, a published
>    response's author, the course's lead, the department's chair and the
>    college's dean, each with its role. A course with no lead answers no lead
>    row; a department with no chair answers no chair row.
> 5. The door, given a leadership reader and a list containing a section outside
>    their scope, calls the definer without it and answers no row for it.
> 6. With the development clock moved so the UTC date and the institution's date
>    differ, an enrollment ending today in the institution's timezone is answered
>    the same way the survey read answers it.

The reader checks (done-whens 3 and 4) are
`test_the_set_based_staff_name_channel_keeps_each_readers_reach.py`, marked
`invariant`. The settled names are transcribed once in
`tests/fixtures/staff_names_for_sections.py`.

**Every answer is compared whole** where the criterion names who is answered:
the set of (section, role, person) triples, never a search for one name, so a
widened role (the assistant dean read as a dean, a second department's chair)
has a row to show up as.

**Every call is made on `pulse_app`'s connection** (`docs/MISTAKES.md` entry 46).

**Which failure a red is, before E9-03 lands.** The definer tests fail on
`require_v2`, naming `public.section_staff_names(uuid[],uuid,uuid,date)`. The door
tests fail on `the_set_door`, naming the missing `section_ids` keyword. The
catalog test fails on the same missing overload.
"""

from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fixtures.clock import DEVELOPMENT, ENVIRONMENT_VARIABLE, INSTITUTION_TIMEZONE_VARIABLE
from fixtures.roster_sync import institution_today
from fixtures.staff_names import DEFINER_ROLE, Person
from fixtures.staff_names_for_sections import (
    AS_AUTHOR,
    AS_CHAIR,
    AS_DEAN,
    AS_INSTRUCTOR,
    AS_LEAD,
    DEFINER_NAME,
    SETTLEMENT,
    V1_SIGNATURE,
    V2_COLUMNS,
    V2_SIGNATURE,
    SetWorld,
    ask_the_set_door,
    ask_v2,
    definer_calls,
    prepared,
    rows_of,
    statements_sent,
    the_set_door,
)
from fixtures.survey_windows import INSTITUTION_TIMEZONE
from sqlalchemy import text

pytestmark = pytest.mark.integration

FORTY = 40


def triple(section_id: Any, role: str, person: Person | None) -> tuple[str, str, str]:
    assert person is not None, f"The world has no person to answer as {role}."
    return (str(section_id), role, str(person.person_id))


def leadership_scope_of(session: Any, person_id: Any) -> Any:
    """The `ActorScope` `authz.resolve_scope` answers for one person.

    The door's `scope` parameter is the existing `ActorScope` type (the ticket),
    and `resolve_scope` is the existing function that builds one from a person's
    stored assignments. E9-01's `leadership_scope` resolves it from a session; this
    module calls the door directly and has no session to resolve from.
    """
    from app.services import authz

    scope = authz.resolve_scope(session, person_id=person_id)
    session.rollback()
    if not hasattr(getattr(scope, "purview", None), "section_ids"):
        pytest.fail(
            f"`resolve_scope` answered {scope!r}, whose purview carries no `section_ids` (ADR "
            "0046: a purview is a materialised node set per containment level)."
        )
    return scope


# ---------------------------------------------------------------------------
# Done-when 1: one call for many sections.
# ---------------------------------------------------------------------------


def test_forty_section_ids_are_read_through_the_door_in_one_definer_call(
    staff_names_for_sections: SetWorld,
) -> None:
    """The chair's door call over forty ids sends the definer exactly one statement.

    The forty are the world's four sections and thirty-six ids naming no section.
    A per-section door sends one statement per id it passes on, so it is caught
    however many of the forty survive the purview filter (four at least, all in
    the chair's department).

    **The mutation this kills:** the door looping over its ids and calling the
    definer (v001 or v002) once per section. **The near miss:** a door that calls
    once and then re-asks v001 per section to fill in a role; it is still more
    than one statement naming the function.
    **The twin:** the one call answered the taught section's instructor, so the
    count is of a call that did its job.
    """
    world = staff_names_for_sections
    names = world.names
    prepared(names)
    assert names.chair is not None and names.teacher is not None
    scope = leadership_scope_of(names.application_session, names.chair.person_id)
    ids = list(names.every_section().values()) + [uuid4() for _ in range(FORTY - 4)]
    assert len(ids) == FORTY

    with statements_sent() as sent:
        answered = ask_the_set_door(
            names.application_session,
            section_ids=ids,
            reader_person_id=names.chair.person_id,
            scope=scope,
        )
    assert sent, (
        "The recorder saw no statement at all while the door ran, so a count of zero or one "
        "would be the recorder's and not the door's (`docs/MISTAKES.md` entry 3)."
    )
    calls = definer_calls(sent)
    assert len(calls) == 1, (
        f"One door call over {FORTY} section ids sent {len(calls)} statements naming "
        f"`{DEFINER_NAME}`:\n" + "\n".join(call.sql[:200] for call in calls[:6]) + "\n\nE9-03 "
        "done-when 1: a leadership page's names for forty sections are read in one definer call."
    )
    instructors = {
        row.person_id for row in rows_of(answered, names.taught) if row.role == AS_INSTRUCTOR
    }
    assert instructors == {str(names.teacher.person_id)}, (
        f"The twin: the one call answered the taught section's instructors as {instructors}, not "
        f"the one teacher; a chair is answered for any section the door passes (ruling 3)."
    )


# ---------------------------------------------------------------------------
# Done-when 2: each role is answered.
# ---------------------------------------------------------------------------


def test_a_section_is_answered_its_instructor_author_lead_chair_and_dean_each_with_its_role(
    staff_names_for_sections: SetWorld,
) -> None:
    """F1WW, asked by its own instructor, after its lead published a response: five rows.

    `(F1WW, INSTRUCTOR, teacher)`, `(F1WW, AUTHOR, lead)`, `(F1WW, LEAD_FACULTY,
    lead)`, `(F1WW, CHAIR, chair)` and `(F1WW, DEAN, dean)`, and nothing else. The
    world also holds an assistant dean of the same college and a vice president,
    another department's chair, a sibling lead, and instructors on three other
    sections; none of them is a row here. Each row's `display_name` is that
    person's own name.

    **The mutations this kill:** a role missing from the union (no dean, no
    chair, no author); the dean row read from `DEAN` or `ASSISTANT_DEAN` (the
    settlement: from `DEAN` only), or from the institution's VP; the chair read at
    college grain (adds the second department's chair); the instructor read at
    course grain (adds the sibling section's teacher); a name read off the wrong
    person (a lead's row carrying the teacher's name).
    """
    world = staff_names_for_sections
    names = world.names
    prepared(names)
    assert names.teacher and names.lead and names.chair
    dean = world.a_dean()
    world.an_assistant_dean()
    world.a_vice_president()
    names.a_response(names.taught, author=names.lead.person_id, role="LEAD_FACULTY")

    answered = ask_v2(
        names.application_session,
        section_ids=[names.taught],
        reader_person_id=names.teacher.person_id,
        reader_date=institution_today(),
    )
    expected = {
        triple(names.taught, AS_INSTRUCTOR, names.teacher),
        triple(names.taught, AS_AUTHOR, names.lead),
        triple(names.taught, AS_LEAD, names.lead),
        triple(names.taught, AS_CHAIR, names.chair),
        triple(names.taught, AS_DEAN, dean),
    }
    assert answered.triples == expected and len(answered.rows) == len(expected), (
        f"F1WW's rows, asked by its instructor, are {sorted(answered.triples)} "
        f"({len(answered.rows)} rows), not {sorted(expected)}. E9-03 done-when 2: its live "
        "instructor, a published response's author, the course's lead, the department's chair and "
        "the college's dean, each with its role."
    )
    people = (names.teacher, names.lead, names.chair, dean)
    named = {str(person.person_id): person.name for person in people}
    wrong = [row for row in answered.rows if row.display_name != named.get(row.person_id)]
    assert not wrong, f"These rows carry a name that is not their person's: {wrong}."


def test_a_course_with_no_lead_answers_no_lead_row(staff_names_for_sections: SetWorld) -> None:
    """The unmapped course's section: instructor, chair and dean, and no `LEAD_FACULTY` row.

    **The twin, in the same world:** F1WW, asked by its own instructor, carries
    its course's lead row.

    **The mutations this kill:** the lead row read from the department's leads
    (any lead under the same prefix would answer, and the sibling lead is one), or
    the chair answered under the lead role for an unled course (v001's chair limb
    leaking into the role column).
    """
    world = staff_names_for_sections
    names = world.names
    prepared(names)
    assert names.teacher and names.lead and names.chair and names.unmapped_teacher
    dean = world.a_dean()

    twin = ask_v2(
        names.application_session,
        section_ids=[names.taught],
        reader_person_id=names.teacher.person_id,
        reader_date=institution_today(),
    )
    assert (
        triple(names.taught, AS_LEAD, names.lead) in twin.triples
    ), f"The twin: F1WW's rows {sorted(twin.triples)} carry no lead row for its own lead."
    answered = ask_v2(
        names.application_session,
        section_ids=[names.unmapped_section],
        reader_person_id=names.unmapped_teacher.person_id,
        reader_date=institution_today(),
    )
    expected = {
        triple(names.unmapped_section, AS_INSTRUCTOR, names.unmapped_teacher),
        triple(names.unmapped_section, AS_CHAIR, names.chair),
        triple(names.unmapped_section, AS_DEAN, dean),
    }
    assert answered.triples == expected, (
        f"The unmapped course's section answered {sorted(answered.triples)}, not "
        f"{sorted(expected)}. E9-03 done-when 2: a course with no lead answers no lead row."
    )


def test_a_department_with_no_chair_answers_no_chair_row(
    staff_names_for_sections: SetWorld,
) -> None:
    """A section in a second, chairless department of the college: instructor and dean only.

    **The twin, in the same world:** F1WW, asked by its own instructor, carries
    its department's chair row.

    **The mutations this kill:** the chair row read at college grain (both
    departments' chairs in this college would answer), or from any chair at all.
    """
    world = staff_names_for_sections
    names = world.names
    prepared(names)
    assert names.teacher and names.chair
    section = world.a_section_in_a_department_with_no_chair()
    dean = world.a_dean()

    twin = ask_v2(
        names.application_session,
        section_ids=[names.taught],
        reader_person_id=names.teacher.person_id,
        reader_date=institution_today(),
    )
    assert triple(names.taught, AS_CHAIR, names.chair) in twin.triples, (
        f"The twin: F1WW's rows {sorted(twin.triples)} carry no chair row for its department's "
        "chair."
    )
    assert world.chairless_teacher is not None
    answered = ask_v2(
        names.application_session,
        section_ids=[section],
        reader_person_id=world.chairless_teacher.person_id,
        reader_date=institution_today(),
    )
    expected = {
        triple(section, AS_INSTRUCTOR, world.chairless_teacher),
        triple(section, AS_DEAN, dean),
    }
    assert answered.triples == expected, (
        f"The chairless department's section answered {sorted(answered.triples)}, not "
        f"{sorted(expected)}. E9-03 done-when 2: a department with no chair answers no chair row."
    )


def test_a_teacher_who_also_published_is_one_row_under_each_role(
    staff_names_for_sections: SetWorld,
) -> None:
    """The instructor publishes twice to F1WW: exactly two rows name them, `INSTRUCTOR` and `AUTHOR`.

    The settlement: one row per (section, role, person).

    **The mutations this kill:** the author rows read without collapsing to
    people (`UNION ALL` over responses: three rows), and the union collapsed by
    person across roles (one row, so the author role is lost).
    """
    world = staff_names_for_sections
    names = world.names
    prepared(names)
    assert names.teacher is not None
    names.a_response(names.taught, author=names.teacher.person_id, role="INSTRUCTOR")
    names.a_response(names.taught, author=names.teacher.person_id, role="INSTRUCTOR")

    answered = ask_v2(
        names.application_session,
        section_ids=[names.taught],
        reader_person_id=names.teacher.person_id,
        reader_date=institution_today(),
    )
    teacher = str(names.teacher.person_id)
    theirs = sorted(row.role for row in answered.rows if row.person_id == teacher)
    assert theirs == sorted([AS_AUTHOR, AS_INSTRUCTOR]), (
        f"The instructor, who teaches F1WW and published two response rows to it, is named in rows "
        f"with roles {theirs}. The settlement: one row per (section, role, person)."
    )


# ---------------------------------------------------------------------------
# Done-when 5: the door passes purview sections only.
# ---------------------------------------------------------------------------


def test_the_door_sends_the_definer_no_section_outside_the_leadership_scope(
    staff_names_for_sections: SetWorld,
) -> None:
    """The chair's door call over F1WW and a section of another department sends only F1WW.

    The other section sits in a chairless department of the same college, so it
    is outside the chair's resolved purview. **The control:** the definer itself,
    asked directly with the chair's key, answers that section (ruling 3), so the
    only thing that can withhold it is the door. **The twin:** F1WW, in the
    chair's purview, is sent and answered in the same call.

    **The mutation this kills:** the door passing the caller's whole list (E9-12's
    named mutation). **The near miss:** a door that sends the whole list and drops
    the out-of-scope rows afterwards; its answer looks right, and the ids bound
    to the statement show the definer was asked.
    """
    world = staff_names_for_sections
    names = world.names
    prepared(names)
    assert names.chair is not None
    outside = world.a_section_in_a_department_with_no_chair()
    scope = leadership_scope_of(names.application_session, names.chair.person_id)
    held = {str(section) for section in scope.purview.section_ids}
    assert str(names.taught) in held and str(outside) not in held, (
        f"The chair's resolved purview holds F1WW: {str(names.taught) in held}; holds the other "
        f"department's section: {str(outside) in held}. This test needs the first and not the "
        "second. A broken world, not a red."
    )
    control = ask_v2(
        names.application_session,
        section_ids=[outside],
        reader_person_id=names.chair.person_id,
        reader_date=institution_today(),
    )
    assert control.of(outside), (
        "The control: the definer, asked directly with the chair's key, answered nothing for the "
        "other department's section, so a door that withheld it would be indistinguishable from "
        "one that passed it. Ruling 3: a chair is answered for any section passed."
    )

    with statements_sent() as sent:
        answered = ask_the_set_door(
            names.application_session,
            section_ids=[names.taught, outside],
            reader_person_id=names.chair.person_id,
            scope=scope,
        )
    calls = definer_calls(sent)
    assert calls, "The door sent no statement naming the definer; the twin below would fail too."
    bound = "\n".join(call.text for call in calls)
    assert str(names.taught) in bound, (
        "The door's definer call does not carry F1WW, which is in the chair's purview:\n"
        f"{bound[:600]}"
    )
    assert str(outside) not in bound, (
        f"The door sent the definer a section outside the chair's purview:\n{bound[:600]}\n\nE9-03 "
        "done-when 5: the door calls the definer without it."
    )
    assert rows_of(answered, names.taught), "The twin: the door answered nothing for F1WW."
    assert not rows_of(
        answered, outside
    ), f"The door answered {rows_of(answered, outside)} for a section outside the chair's purview."


# ---------------------------------------------------------------------------
# The fix round: the door refuses a call it cannot scope.
#
# The review of the built head found the door fail-open: a chair's, dean's or
# VP's key passed with no `scope` was answered for every section. The ruling:
# `scope` is a required keyword (`ActorScope | None`, no default), so a caller
# that wants no purview filter writes `scope=None` where a reviewer sees it. The
# door's two `ValueError` checks (a scope that is not the reader's own; a user
# key with any scope) had no test (the privacy review's LOW).
# ---------------------------------------------------------------------------


def test_the_door_refuses_a_call_that_does_not_name_a_scope(
    staff_names_for_sections: SetWorld,
) -> None:
    """Called with no `scope` keyword at all, the door raises `TypeError` naming `scope`.

    **The mutation this kills:** a default restored on `scope` (`scope=None`),
    which is the fail-open the review found: a caller who forgets the scope gets
    the definer's broad answer for a chair and above. **The twin** is the next
    test: the same call with `scope=None` written out is answered.
    """
    names = staff_names_for_sections.names
    prepared(names)
    assert names.teacher is not None
    door = the_set_door()
    with pytest.raises(TypeError) as refused:
        door(
            names.application_session,
            section_ids=[names.taught],
            reader_person_id=names.teacher.person_id,
        )
    names.application_session.rollback()
    assert "scope" in str(refused.value), (
        f"The door raised `TypeError: {refused.value}`, which does not name `scope`; the refusal "
        "this test is about is the missing required keyword, not some other `TypeError`."
    )


def test_the_door_answers_a_call_that_writes_scope_none(
    staff_names_for_sections: SetWorld,
) -> None:
    """The twin: the same call with `scope=None` is answered the taught section's instructor.

    **The mutation this kills:** a door that refuses `scope=None` outright, so
    single-section callers (the survey page, the instructor report) lose their
    names; and, for the test above, it shows the call shape works once `scope` is
    named, so the `TypeError` there is about the keyword.
    """
    names = staff_names_for_sections.names
    prepared(names)
    assert names.teacher is not None
    answered = ask_the_set_door(
        names.application_session,
        section_ids=[names.taught],
        reader_person_id=names.teacher.person_id,
        scope=None,
    )
    instructors = {
        row.person_id for row in rows_of(answered, names.taught) if row.role == AS_INSTRUCTOR
    }
    assert instructors == {
        str(names.teacher.person_id)
    }, f"The taught section's instructor, asking with `scope=None`, was answered {answered}."


def test_the_door_refuses_a_chairs_key_with_another_leaders_scope_before_any_query(
    staff_names_for_sections: SetWorld,
) -> None:
    """The chair's person key with the lead's `ActorScope`: `ValueError`, and no statement sent.

    A scope resolved for one person and a reader key naming another is a caller
    mixing two readers; the definer would answer the chair broadly over the lead's
    purview. The check must come before the database is asked, so nothing is sent.

    **The mutations this kill:** the scope's person not compared with the reader
    key (the call is answered); the comparison made after the definer call (a
    statement is recorded). **The twin** is the next test.
    """
    names = staff_names_for_sections.names
    prepared(names)
    assert names.chair is not None and names.lead is not None
    lead_scope = leadership_scope_of(names.application_session, names.lead.person_id)
    door = the_set_door()
    with statements_sent() as sent, pytest.raises(ValueError):
        door(
            names.application_session,
            section_ids=[names.taught],
            reader_person_id=names.chair.person_id,
            scope=lead_scope,
        )
    names.application_session.rollback()
    assert sent == [], (
        "The door, handed the chair's key with the lead's scope, raised only after sending "
        f"{[statement.sql[:120] for statement in sent]}. The refusal comes before any query."
    )


def test_the_door_answers_a_chairs_key_with_the_chairs_own_scope(
    staff_names_for_sections: SetWorld,
) -> None:
    """The twin: the chair's key with the chair's own resolved scope is answered for F1WW.

    **The mutation this kills:** the identity check comparing the wrong things
    (always unequal), which refuses every leadership page.
    """
    names = staff_names_for_sections.names
    prepared(names)
    assert names.chair is not None
    scope = leadership_scope_of(names.application_session, names.chair.person_id)
    answered = ask_the_set_door(
        names.application_session,
        section_ids=[names.taught],
        reader_person_id=names.chair.person_id,
        scope=scope,
    )
    assert rows_of(answered, names.taught), (
        "The chair, asking with their own resolved scope about F1WW in their department, was "
        "answered nothing."
    )


def test_the_door_refuses_a_user_key_passed_with_any_scope(
    staff_names_for_sections: SetWorld,
) -> None:
    """A student's user key with a leader's scope: `ValueError`, and no definer call.

    A scope is a leadership reader's, resolved from a person; a student is asked
    by user key and has none. **The twin, in the same test:** the same student
    with `scope=None` is answered.

    **The mutation this kills:** the user-key check removed, so a student's call
    is filtered by a leader's purview and answered under the student check.
    """
    names = staff_names_for_sections.names
    prepared(names)
    assert names.chair is not None
    student = names.a_student("with-a-scope", names.taught)
    twin = ask_the_set_door(
        names.application_session,
        section_ids=[names.taught],
        reader_user_id=student.user_id,
        scope=None,
    )
    assert rows_of(
        twin, names.taught
    ), "The twin: the student of F1WW, asking with `scope=None`, was answered nothing."
    chair_scope = leadership_scope_of(names.application_session, names.chair.person_id)
    door = the_set_door()
    with statements_sent() as sent, pytest.raises(ValueError):
        door(
            names.application_session,
            section_ids=[names.taught],
            reader_user_id=student.user_id,
            scope=chair_scope,
        )
    names.application_session.rollback()
    assert not definer_calls(
        sent
    ), "The door, handed a user key with a leader's scope, called the definer before refusing."


# ---------------------------------------------------------------------------
# Done-when 6: the date is the app clock's.
# ---------------------------------------------------------------------------

# How far before the real day the pretended day is. Far enough that a definer
# reading the database's own `CURRENT_DATE`, or a door reading the real clock
# rather than the development override, judges the enrollment on a later day.
PRETENDED_DAYS_AGO = 10
LIVE_SINCE_DAYS = 60
# An evening hour in the institution's zone. America/New_York is four or five
# hours behind UTC, so 22:30 there is the next day in UTC whatever the season.
EVENING = time(22, 30)


def an_evening_when_utc_is_already_tomorrow(
    world: SetWorld, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """Move the development clock to 22:30 in the institution's zone; that local day.

    The environment the door's settings are read from is stated here, not
    inherited (`docs/MISTAKES.md` entry 40): the development environment, where
    the override applies, and the institution's zone. **The premise check is this
    helper's**: the pretended instant's UTC date is the day after its local date,
    or the case is not the one done-when 6 names.
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, DEVELOPMENT)
    monkeypatch.setenv(INSTITUTION_TIMEZONE_VARIABLE, INSTITUTION_TIMEZONE)
    zone = ZoneInfo(INSTITUTION_TIMEZONE)
    day = datetime.now(zone).date() - timedelta(days=PRETENDED_DAYS_AGO)
    instant = datetime.combine(day, EVENING, tzinfo=zone).astimezone(UTC)
    assert instant.date() == day + timedelta(days=1), (
        f"22:30 on {day} in {INSTITUTION_TIMEZONE} is {instant.isoformat()} in UTC, the same date; "
        "the case needs the two dates to differ. A broken premise, not a red."
    )
    world.review.door.door.pretend(instant)
    return day


def test_an_enrollment_ending_on_the_institutions_today_is_answered_when_utc_has_moved_on(
    staff_names_for_sections: SetWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The clock reads 22:30 locally, already tomorrow in UTC; an enrollment ending today is live.

    The survey read's rule is `ended_on >= today`, today being the institution's
    date (E5.1-02's work order, D5, as `tests/fixtures/roster_sync.py::
    live_enrollments` states it), so an enrollment ending on the institution's
    today is live, and the door must answer its student.

    **The mutations this kill:** the door passing the UTC date (tomorrow, so the
    enrollment has ended); the door reading the real clock rather than the
    development override (ten days later); the definer ignoring `p_reader_date`
    for `CURRENT_DATE`; and the end compared exclusively (`ended_on > today`).
    """
    world = staff_names_for_sections
    names = world.names
    prepared(names)
    assert names.teacher is not None
    day = an_evening_when_utc_is_already_tomorrow(world, monkeypatch)
    student = world.a_student_enrolled(
        "ends-today",
        names.taught,
        started_on=day - timedelta(days=LIVE_SINCE_DAYS),
        ended_on=day,
    )
    answered = ask_the_set_door(
        names.application_session,
        section_ids=[names.taught],
        reader_user_id=student.user_id,
        scope=None,
    )
    instructors = {
        row.person_id for row in rows_of(answered, names.taught) if row.role == AS_INSTRUCTOR
    }
    assert instructors == {str(names.teacher.person_id)}, (
        f"A student whose enrollment in F1WW ends on the institution's today ({day}), asked at "
        f"22:30 local (already {day + timedelta(days=1)} in UTC), was answered {answered}. The "
        "survey read counts that enrollment live (D5: `ended_on >= today`, in the institution's "
        "zone). E9-03 done-when 6: the door takes the reader's date from the app clock in the "
        "institution's timezone."
    )


def test_an_enrollment_that_ended_the_institutions_yesterday_is_answered_nothing(
    staff_names_for_sections: SetWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same clock; an enrollment that ended yesterday locally is refused, a classmate's is not.

    The other half of the boundary pair above. **The twin, under the same clock
    in the same test:** a classmate with an open enrollment is answered.

    **The mutation this kills:** the end of the enrollment not compared at all
    once the date became a parameter (every enrollment ever made reads as live).
    """
    world = staff_names_for_sections
    names = world.names
    prepared(names)
    day = an_evening_when_utc_is_already_tomorrow(world, monkeypatch)
    started = day - timedelta(days=LIVE_SINCE_DAYS)
    classmate = world.a_student_enrolled("open", names.taught, started_on=started, ended_on=None)
    ended = world.a_student_enrolled(
        "ended-yesterday", names.taught, started_on=started, ended_on=day - timedelta(days=1)
    )

    twin = ask_the_set_door(
        names.application_session,
        section_ids=[names.taught],
        reader_user_id=classmate.user_id,
        scope=None,
    )
    assert rows_of(twin, names.taught), (
        "The twin: a classmate with an open enrollment in F1WW was answered nothing under the same "
        "clock, so the refusal below would mean nothing."
    )
    refused = ask_the_set_door(
        names.application_session,
        section_ids=[names.taught],
        reader_user_id=ended.user_id,
        scope=None,
    )
    assert refused == [], (
        f"A student whose enrollment in F1WW ended on {day - timedelta(days=1)}, the day before the "
        f"institution's today, was answered {refused}. The survey read counts it ended (D5)."
    )


# ---------------------------------------------------------------------------
# The grant: both versions, one owner, executable by the application.
# ---------------------------------------------------------------------------

THE_FUNCTION = """
    SELECT p.prosecdef AS security_definer,
           r.rolname AS owner,
           coalesce(p.proconfig, ARRAY[]::text[]) AS settings
    FROM pg_proc p
    JOIN pg_roles r ON r.oid = p.proowner
    WHERE p.oid = CAST(:signature AS regprocedure)
"""
OVERLOADS = """
    SELECT CAST(CAST(p.oid AS regprocedure) AS text)
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = :name
    ORDER BY 1
"""


def test_both_versions_are_owned_by_the_staff_name_owner_and_the_application_may_call_them(
    staff_names_for_sections: SetWorld,
) -> None:
    """v001 and v002: `SECURITY DEFINER`, owned by `pulse_staff_name_definer`, `pg_temp` last.

    `pulse_app` may execute each, asked on `pulse_app`'s own connection
    (`docs/MISTAKES.md` entry 46), and there is no third function of that name.
    `test_identity_grants.py`'s inventory admits `section_staff_names` by name, so
    an overload granted beside the two would pass it unseen; this is where the
    count of overloads is held. v002 answers its four columns in the settled order.

    **The mutations this kill:** v001 dropped when v002 was added (the
    settlement keeps it); v002 owned by the migration identity, or `SECURITY
    INVOKER` (`pulse_app` holds nothing on `person`); a `search_path` without
    `pg_temp` last (`docs/MISTAKES.md` entry 17: a caller's temporary table
    shadows the real one); `EXECUTE` not granted; a third overload left behind.
    """
    world = staff_names_for_sections
    names = world.names
    prepared(names)
    seeding = names.rows.session
    seeding.rollback()
    for signature in (V1_SIGNATURE, V2_SIGNATURE):
        found = (
            seeding.execute(text(THE_FUNCTION), {"signature": signature}).mappings().one_or_none()
        )
        assert found is not None, f"There is no `{signature}`.\n\n{SETTLEMENT}"
        assert found["security_definer"], f"`{signature}` is not `SECURITY DEFINER`."
        assert (
            found["owner"] == DEFINER_ROLE
        ), f"`{signature}` is owned by {found['owner']!r}, not `{DEFINER_ROLE}`.\n\n{SETTLEMENT}"
        paths = [setting for setting in found["settings"] if setting.startswith("search_path=")]
        entries = (
            [entry.strip().strip('"') for entry in paths[0].split("=", 1)[1].split(",")]
            if paths
            else []
        )
        assert (
            entries and entries[-1] == "pg_temp"
        ), f"`{signature}`'s search_path is {entries}; ADR 0043 puts `pg_temp` last."
        may = names.application_session.execute(
            text(
                "SELECT has_function_privilege(current_user, CAST(:s AS regprocedure), 'EXECUTE')"
            ),
            {"s": signature},
        ).scalar_one()
        names.application_session.rollback()
        assert may is True, f"`pulse_app` may not execute `{signature}`."
    overloads = [row[0] for row in seeding.execute(text(OVERLOADS), {"name": DEFINER_NAME})]
    seeding.rollback()
    assert (
        len(overloads) == 2
    ), f"`public` holds {overloads} named `{DEFINER_NAME}`; the settlement is v001 and v002 only."
    assert names.teacher is not None
    answered = ask_v2(
        names.application_session,
        section_ids=[names.taught],
        reader_person_id=names.teacher.person_id,
        reader_date=institution_today(),
    )
    assert (
        answered.columns == V2_COLUMNS
    ), f"`{V2_SIGNATURE}` answers columns {answered.columns}, not {V2_COLUMNS} in that order."
