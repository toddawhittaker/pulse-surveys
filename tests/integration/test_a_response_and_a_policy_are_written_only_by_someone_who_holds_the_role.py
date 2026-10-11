"""The response records are written only by someone who holds the role — E7-01's fix round.

The review of ba5619fb found that `pulse_app` could insert an `instructor_response`
naming any person as its author, and the staff-name definer answers the name of
anyone who has published a response to a section. So one insert of a forged row
followed by one call of the definer handed a student's name, or anybody's, to the
connection every screen runs on. The fix round (work order, "Fix round") settles:

  - **F1.** A `BEFORE INSERT` trigger on `instructor_response` refuses a row unless
    the author holds the stated `role` for the row's section at write time —
    `INSTRUCTOR` a live teaching grant on the section, `LEAD_FACULTY` the
    assignment plus the mapping for the section's course, `CHAIR` the chair of the
    course's department where the course has no lead;
  - **F2.** One author per section-week (ruling 3), serialised by an advisory lock,
    so two writers racing cannot both land;
  - **F3.** The same on `response_policy`: the setter holds the stated role over at
    least one course in the prefix;
  - **F4.** `term_id` on `instructor_response`, with composite keys into
    `section (id, term_id)` and `week (id, term_id)`, so the week is the section's
    term's.

**Every write is made on `pulse_app`'s own connection** (`application_session`,
and `application_engine` for the race), never on the superuser that seeds
(`docs/MISTAKES.md` entry 46).

**Every refusal sits beside its accepted twin**, written with the same columns
and the same statement shape, differing only in the writer or the week
(`docs/MISTAKES.md` entry 3). A refusal is any database error but a missing
column or relation (42703, 42P01): the trigger's own SQLSTATE is the
implementer's, and the twin is what proves the refusal is about the writer and
not about the statement. Each refused row is then counted absent on the superuser
connection, so a guard that raised after writing is not mistaken for one that
refused.

**Marked `invariant`**: the forged author is a §4 confidentiality hole (a name to
`pulse_app`), and every test here asserts in its own body
(`scripts/ci/check_invariant_assertions.py`).

**Which failure a red is, on ba5619fb.** Each refused write is accepted, so the
refusal assertion fails naming the writer; the term test fails on `term_id`
(the column does not exist yet, so the twin's insert is refused with 42703 and
the test fails naming it); the race lands two authors.
"""

import threading
import time
from datetime import UTC, datetime
from typing import Any

import pytest
from fixtures.staff_names import (
    AI_SEEDED_COLUMN,
    DEFINER_CALL,
    INSTRUCTOR_RESPONSE,
    MODE_COLUMN,
    POLICY_PREFIX_COLUMN,
    POLICY_SETTER_COLUMN,
    POLICY_TIME_COLUMN,
    RESPONSE_AUTHOR_COLUMN,
    RESPONSE_BODY_COLUMN,
    RESPONSE_POLICY,
    RESPONSE_SECTION_COLUMN,
    RESPONSE_TERM_COLUMN,
    RESPONSE_TIME_COLUMN,
    ROLE_COLUMN,
    TEACHER_NAME,
    WEEK_COLUMN,
    StaffNameWorld,
    id_references,
    require_the_application_role,
    require_the_definer,
    require_the_tables,
    sqlstate,
)
from fixtures.supervision import require_table, single_primary_key

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# What a refusal may not be: the statement naming something that is not there.
NOT_A_REFUSAL = ("42703", "42P01")

FORGED_AUTHOR_NAME = "Ottoline Forgewright-Never-An-Author"


# ---------------------------------------------------------------------------
# Writing as `pulse_app`.
# ---------------------------------------------------------------------------


def response_values(
    world: StaffNameWorld,
    *,
    section_id: Any,
    author: Any,
    role: str,
    week_index: int = 0,
    week_id: Any = None,
    term_id: Any = None,
) -> dict[str, Any]:
    return {
        RESPONSE_SECTION_COLUMN: section_id,
        RESPONSE_TERM_COLUMN: world.term_of(section_id) if term_id is None else term_id,
        WEEK_COLUMN: world.a_week_of(section_id, week_index) if week_id is None else week_id,
        RESPONSE_AUTHOR_COLUMN: author,
        ROLE_COLUMN: role,
        AI_SEEDED_COLUMN: False,
        RESPONSE_BODY_COLUMN: f"E7-01 fix round: a response by {author} as {role}",
        RESPONSE_TIME_COLUMN: datetime.now(UTC),
    }


def write(world: StaffNameWorld, table_name: str, values: dict[str, Any]) -> Any:
    """Insert one row as `pulse_app` and commit; the error it raised, or `None`."""
    from sqlalchemy.exc import DatabaseError

    session = world.application_session
    table = world.tables[table_name]
    try:
        session.execute(table.insert().values(**values))
        session.commit()
    except DatabaseError as failure:
        session.rollback()
        return failure
    return None


def write_response(world: StaffNameWorld, **keywords: Any) -> Any:
    return write(world, INSTRUCTOR_RESPONSE, response_values(world, **keywords))


def write_policy(world: StaffNameWorld, *, setter: Any, role: str) -> Any:
    return write(
        world,
        RESPONSE_POLICY,
        {
            POLICY_PREFIX_COLUMN: the_prefix(world),
            POLICY_SETTER_COLUMN: setter,
            ROLE_COLUMN: role,
            MODE_COLUMN: "REQUIRED",
            POLICY_TIME_COLUMN: datetime.now(UTC),
        },
    )


def the_prefix(world: StaffNameWorld) -> Any:
    chain = world.review.world.calendar.chain
    return chain["prefix"][single_primary_key(require_table(world.tables, "prefix"))]


def rows_by(world: StaffNameWorld, table_name: str, column: str, person: Any) -> int:
    """How many rows of `table_name` name `person` in `column`, read on the superuser connection."""
    table = world.tables[table_name]
    session = world.rows.session
    session.rollback()
    found = len(session.execute(table.select().where(table.c[column] == person)).all())
    session.rollback()
    return found


def is_a_refusal(failure: Any) -> bool:
    return failure is not None and sqlstate(failure) not in NOT_A_REFUSAL


def accepted_message(what: str, failure: Any) -> str:
    return (
        f"The twin: {what} was refused ({None if failure is None else sqlstate(failure)}: "
        f"{failure}). Without it, the refusal beside it could be the statement and not the writer."
    )


def prepared(world: StaffNameWorld) -> None:
    require_the_application_role(world.application_session)
    require_the_tables(world.tables)


# ---------------------------------------------------------------------------
# F1 — the author holds the stated role for the section.
# ---------------------------------------------------------------------------


def test_a_response_naming_a_students_person_as_its_author_is_refused(
    staff_names: StaffNameWorld,
) -> None:
    """A student of `F1WW` with a `person` row, as `INSTRUCTOR`: refused; the teacher: accepted.

    **The mutation this kills:** no author check at insert (ba5619fb), under
    which this row lands and the definer then answers the student's name to every
    reader of the section.
    """
    world = staff_names
    prepared(world)
    assert world.teacher is not None
    student = world.a_student("forged-author", world.taught, with_person=True)

    twin = write_response(
        world,
        section_id=world.taught,
        author=world.teacher.person_id,
        role="INSTRUCTOR",
        week_index=1,
    )
    assert twin is None, accepted_message("the section's instructor writing as INSTRUCTOR", twin)
    failure = write_response(
        world, section_id=world.taught, author=student.person_id, role="INSTRUCTOR"
    )
    assert is_a_refusal(failure), (
        f"`pulse_app` wrote a response to F1WW naming a student's person as its INSTRUCTOR "
        f"author, and was answered {failure!r}. Fix round F1: the author holds the stated role "
        "for the section when the row is written."
    )
    assert rows_by(world, INSTRUCTOR_RESPONSE, RESPONSE_AUTHOR_COLUMN, student.person_id) == 0


def test_a_lead_faculty_response_by_a_sibling_lead_is_refused(staff_names: StaffNameWorld) -> None:
    """The sibling course's lead, as `LEAD_FACULTY`, on `F1WW`: refused; the course's lead: accepted.

    **The mutation this kills:** the `LEAD_FACULTY` branch checking the
    assignment's existence (any course) rather than the mapping for this
    section's course — SPEC §4.1 item 2 at the write.
    """
    world = staff_names
    prepared(world)
    assert world.lead is not None and world.sibling_lead is not None

    twin = write_response(
        world,
        section_id=world.taught,
        author=world.lead.person_id,
        role="LEAD_FACULTY",
        week_index=1,
    )
    assert twin is None, accepted_message("the course's lead writing as LEAD_FACULTY", twin)
    failure = write_response(
        world, section_id=world.taught, author=world.sibling_lead.person_id, role="LEAD_FACULTY"
    )
    assert is_a_refusal(failure), (
        f"A sibling lead wrote a LEAD_FACULTY response to F1WW, in a course they do not lead, and "
        f"was answered {failure!r}. Fix round F1."
    )
    assert (
        rows_by(world, INSTRUCTOR_RESPONSE, RESPONSE_AUTHOR_COLUMN, world.sibling_lead.person_id)
        == 0
    )


def test_a_chair_response_on_a_course_that_has_a_lead_is_refused(
    staff_names: StaffNameWorld,
) -> None:
    """The chair, as `CHAIR`, on `F1WW` (a led course): refused; on the unmapped course: accepted.

    **The mutation this kills:** the `CHAIR` branch without "and the course has no
    lead mapping" — SPEC §5.3: the chair responds on behalf only for a course with
    no lead.
    """
    world = staff_names
    prepared(world)
    assert world.chair is not None

    twin = write_response(
        world, section_id=world.unmapped_section, author=world.chair.person_id, role="CHAIR"
    )
    assert twin is None, accepted_message("the chair writing as CHAIR on the unled course", twin)
    before = rows_by(world, INSTRUCTOR_RESPONSE, RESPONSE_AUTHOR_COLUMN, world.chair.person_id)
    failure = write_response(
        world, section_id=world.taught, author=world.chair.person_id, role="CHAIR"
    )
    assert is_a_refusal(failure), (
        f"The chair wrote a CHAIR response to F1WW, whose course has a lead, and was answered "
        f"{failure!r}. Fix round F1."
    )
    assert (
        rows_by(world, INSTRUCTOR_RESPONSE, RESPONSE_AUTHOR_COLUMN, world.chair.person_id) == before
    )


def test_a_response_under_a_role_the_author_does_not_hold_there_is_refused(
    staff_names: StaffNameWorld,
) -> None:
    """The course's lead, as `INSTRUCTOR` on `F1WW` (which they do not teach): refused.

    One level out (`docs/MISTAKES.md` entry 53): the writer is a legitimate
    author of this section under one role and states another.

    **The mutation this kills:** a check that the author holds *some* qualifying
    role for the section, rather than the stated one — which lets a lead's
    on-behalf response be stored as the instructor's own.
    """
    world = staff_names
    prepared(world)
    assert world.lead is not None

    twin = write_response(
        world,
        section_id=world.taught,
        author=world.lead.person_id,
        role="LEAD_FACULTY",
        week_index=1,
    )
    assert twin is None, accepted_message("the course's lead writing as LEAD_FACULTY", twin)
    failure = write_response(
        world, section_id=world.taught, author=world.lead.person_id, role="INSTRUCTOR"
    )
    assert is_a_refusal(failure), (
        f"The course's lead wrote an INSTRUCTOR response to F1WW, which they do not teach, and was "
        f"answered {failure!r}. Fix round F1: the stated role is the one checked."
    )


def test_a_response_by_a_teacher_whose_grant_the_roster_ended_is_refused(
    staff_names: StaffNameWorld,
) -> None:
    """A former teacher of `F1WW`, as `INSTRUCTOR`: refused; the live teacher: accepted.

    **The mutation this kills:** the `INSTRUCTOR` branch reading taught-or-once-
    taught sections ("a live INSTRUCTOR grant", F1).
    """
    world = staff_names
    prepared(world)
    assert world.teacher is not None
    former = world.a_former_teacher_of_the_taught_section()

    twin = write_response(
        world,
        section_id=world.taught,
        author=world.teacher.person_id,
        role="INSTRUCTOR",
        week_index=1,
    )
    assert twin is None, accepted_message("the live teacher writing as INSTRUCTOR", twin)
    failure = write_response(
        world, section_id=world.taught, author=former.person_id, role="INSTRUCTOR"
    )
    assert is_a_refusal(failure), (
        f"A teacher whose grant the roster ended wrote an INSTRUCTOR response to F1WW and was "
        f"answered {failure!r}. Fix round F1: a live grant."
    )


def test_the_forged_author_exploit_yields_no_name(staff_names: StaffNameWorld) -> None:
    """The reviewers' exploit: insert a forged response, then ask the definer, in one transaction.

    As `pulse_app`: write a response to `F1WW` naming a person with a distinctive
    name (holding no role) as its author, and — inside the same transaction, so a
    later rollback would hide nothing — ask the definer for `F1WW` as its teacher.
    The insert must fail, and no answer may carry the name.

    **The control:** the teacher's answer carries the teacher's name.

    **The mutation this kills:** ba5619fb as it stands, and an author check
    written as a deferred constraint (checked at commit, after the read).
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DatabaseError

    world = staff_names
    prepared(world)
    require_the_definer(world.application_session)
    assert world.teacher is not None
    forged = world.a_named_person(FORGED_AUTHOR_NAME)
    session = world.application_session
    table = world.tables[INSTRUCTOR_RESPONSE]
    values = response_values(world, section_id=world.taught, author=forged, role="INSTRUCTOR")

    inserted = True
    try:
        session.execute(table.insert().values(**values))
    except DatabaseError as failure:
        inserted = False
        assert sqlstate(failure) not in NOT_A_REFUSAL, f"The forged insert broke: {failure}"
        session.rollback()

    rows = (
        session.execute(
            text(DEFINER_CALL),
            {
                "section_id": str(world.taught),
                "reader_user_id": None,
                "reader_person_id": str(world.teacher.person_id),
            },
        )
        .mappings()
        .all()
    )
    names = sorted(str(row["display_name"]) for row in rows)
    session.rollback()

    assert TEACHER_NAME in names, f"The control: the teacher was answered {names}."
    assert not inserted and FORGED_AUTHOR_NAME not in names, (
        f"`pulse_app` inserted a response naming {FORGED_AUTHOR_NAME!r}, who holds no role, as its "
        f"author (inserted={inserted}), and the definer then answered {names} in the same "
        "transaction. Fix round F1: the insert fails, so the name never reaches the channel."
    )


# ---------------------------------------------------------------------------
# F2 — one author per section-week.
# ---------------------------------------------------------------------------


def test_a_second_author_for_one_section_week_is_refused(staff_names: StaffNameWorld) -> None:
    """The teacher writes week 0 of `F1WW` twice (accepted); the lead then writes it (refused).

    Ruling 3: "Only the person who first published the week's response may edit
    it." Both writers are legitimate for the section, so only the one-author rule
    can refuse the second.

    **The mutation this kills:** no one-author rule in the database (left to a
    Python check), or one keyed on the section without the week (the twin's
    second row would be refused).
    """
    world = staff_names
    prepared(world)
    assert world.teacher is not None and world.lead is not None

    first = write_response(
        world, section_id=world.taught, author=world.teacher.person_id, role="INSTRUCTOR"
    )
    edit = write_response(
        world, section_id=world.taught, author=world.teacher.person_id, role="INSTRUCTOR"
    )
    assert first is None and edit is None, accepted_message(
        "the teacher's first response and its edit to one section-week", first or edit
    )
    lead_elsewhere = write_response(
        world,
        section_id=world.taught,
        author=world.lead.person_id,
        role="LEAD_FACULTY",
        week_index=1,
    )
    assert lead_elsewhere is None, accepted_message(
        "the lead's response to another week", lead_elsewhere
    )
    failure = write_response(
        world, section_id=world.taught, author=world.lead.person_id, role="LEAD_FACULTY"
    )
    assert is_a_refusal(failure), (
        f"The lead wrote a second author's response into a section-week the teacher already "
        f"published, and was answered {failure!r}. Fix round F2 (ruling 3)."
    )
    assert rows_by(world, INSTRUCTOR_RESPONSE, RESPONSE_AUTHOR_COLUMN, world.lead.person_id) == 1


def test_two_connections_racing_for_one_section_week_land_exactly_one_author(
    staff_names: StaffNameWorld, application_engine: Any
) -> None:
    """Two `pulse_app` connections, two legitimate authors, one section-week: one author lands.

    The teacher's insert is made and **left uncommitted**; the lead's insert is
    then made on a second connection in a thread; after a pause the first commits,
    and the second is waited for. With F2's advisory lock the second waits on the
    first and then sees its row; without it the second sees nothing uncommitted
    and both land.

    **The mutation this kills:** the one-author check without the lock (a read of
    committed rows only), which two simultaneous publishers defeat.
    """
    world = staff_names
    prepared(world)
    assert world.teacher is not None and world.lead is not None
    table = world.tables[INSTRUCTOR_RESPONSE]
    week = world.a_week_of(world.taught, 2)
    teacher_row = response_values(
        world,
        section_id=world.taught,
        author=world.teacher.person_id,
        role="INSTRUCTOR",
        week_id=week,
    )
    lead_row = response_values(
        world,
        section_id=world.taught,
        author=world.lead.person_id,
        role="LEAD_FACULTY",
        week_id=week,
    )
    outcome: dict[str, Any] = {}

    def second_writer() -> None:
        from sqlalchemy import text
        from sqlalchemy.exc import DatabaseError

        with application_engine.connect() as connection:
            try:
                connection.execute(text("SET statement_timeout = '20s'"))
                connection.execute(table.insert().values(**lead_row))
                connection.commit()
                outcome["second"] = None
            except DatabaseError as failure:
                connection.rollback()
                outcome["second"] = failure

    first = application_engine.connect()
    try:
        first.execute(table.insert().values(**teacher_row))
        racer = threading.Thread(target=second_writer)
        racer.start()
        time.sleep(1.5)
        first.commit()
        racer.join(timeout=30)
        assert not racer.is_alive(), "The second writer never finished: a lock nobody released."
    finally:
        first.close()

    session = world.rows.session
    session.rollback()
    authors = {
        str(row[0])
        for row in session.execute(
            table.select()
            .with_only_columns(table.c[RESPONSE_AUTHOR_COLUMN])
            .where(table.c[RESPONSE_SECTION_COLUMN] == world.taught)
            .where(table.c[WEEK_COLUMN] == week)
        )
    }
    session.rollback()
    assert authors == {str(world.teacher.person_id)}, (
        f"Two connections racing for one section-week left authors {sorted(authors)} (the second "
        f"writer was answered {outcome.get('second')!r}). Fix round F2: the trigger takes an "
        "advisory lock on the section-week, so the second writer waits and is refused."
    )


# ---------------------------------------------------------------------------
# F3 — the policy setter holds the stated role over a course in the prefix.
# ---------------------------------------------------------------------------


def test_a_policy_set_by_a_person_with_no_role_in_the_prefix_is_refused(
    staff_names: StaffNameWorld,
) -> None:
    """A person holding nothing, as `LEAD_FACULTY`: refused; the course's lead: accepted.

    **The mutation this kills:** no setter check (ba5619fb), under which any
    connection can switch a prefix to required and hold every section's week.
    """
    world = staff_names
    prepared(world)
    assert world.lead is not None
    nobody = world.a_named_person("Nobody Holds-A-Prefix")

    twin = write_policy(world, setter=world.lead.person_id, role="LEAD_FACULTY")
    assert twin is None, accepted_message("the course's lead setting the prefix's policy", twin)
    failure = write_policy(world, setter=nobody, role="LEAD_FACULTY")
    assert is_a_refusal(failure), (
        f"A person holding no role in the prefix set its policy as LEAD_FACULTY and was answered "
        f"{failure!r}. Fix round F3."
    )
    assert rows_by(world, RESPONSE_POLICY, POLICY_SETTER_COLUMN, nobody) == 0


def test_a_policy_set_as_chair_by_another_departments_chair_is_refused(
    staff_names: StaffNameWorld,
) -> None:
    """Another department's chair, as `CHAIR`: refused; the prefix's department's chair: accepted.

    **The mutation this kills:** the `CHAIR` branch checking "holds `CHAIR`
    somewhere" rather than on the prefix's department.
    """
    world = staff_names
    prepared(world)
    assert world.chair is not None and world.other_chair is not None

    twin = write_policy(world, setter=world.chair.person_id, role="CHAIR")
    assert twin is None, accepted_message("the department's chair setting policy as CHAIR", twin)
    failure = write_policy(world, setter=world.other_chair.person_id, role="CHAIR")
    assert is_a_refusal(failure), (
        f"Another department's chair set this prefix's policy as CHAIR and was answered "
        f"{failure!r}. Fix round F3."
    )
    assert rows_by(world, RESPONSE_POLICY, POLICY_SETTER_COLUMN, world.other_chair.person_id) == 0


def test_a_policy_under_a_role_the_setter_does_not_hold_is_refused(
    staff_names: StaffNameWorld,
) -> None:
    """The lead, stating `CHAIR`: refused, beside the same lead stating `LEAD_FACULTY`: accepted.

    **The mutation this kills:** a setter check that accepts any qualifying role,
    which lets a lead's switch be recorded as the chair's (ADR 0192's two-hat
    keying reads the stated role).
    """
    world = staff_names
    prepared(world)
    assert world.lead is not None

    twin = write_policy(world, setter=world.lead.person_id, role="LEAD_FACULTY")
    assert twin is None, accepted_message("the lead setting policy as LEAD_FACULTY", twin)
    failure = write_policy(world, setter=world.lead.person_id, role="CHAIR")
    assert is_a_refusal(failure), (
        f"The lead, who holds no CHAIR assignment, set the prefix's policy as CHAIR and was "
        f"answered {failure!r}. Fix round F3."
    )


# ---------------------------------------------------------------------------
# F4 — the week belongs to the section's term.
# ---------------------------------------------------------------------------


def test_a_response_keyed_to_a_week_of_another_term_is_refused(staff_names: StaffNameWorld) -> None:
    """A week of another term, under either term key: refused; the section's own week: accepted.

    **The mutations this kill:** a plain `week_id` key with no term agreement
    (the week of another term is accepted when `term_id` names the section's),
    and a `term_id` that agrees with the week but not the section (the second
    write).
    """
    world = staff_names
    prepared(world)
    assert world.teacher is not None
    foreign_week = world.rows.seed("week", {})
    world.rows.commit()
    week_table = require_table(world.tables, "week")
    foreign_week_id = foreign_week[single_primary_key(week_table)]
    week_term_columns = id_references(week_table, "term")
    assert len(week_term_columns) == 1, f"`week` references `term` by {week_term_columns}."
    foreign_term = foreign_week[week_term_columns[0]]
    assert str(foreign_term) != str(
        world.term_of(world.taught)
    ), "The planted week is in the section's own term, so it cannot test the term rule."

    twin = write_response(
        world, section_id=world.taught, author=world.teacher.person_id, role="INSTRUCTOR"
    )
    assert twin is None, accepted_message("a response keyed to the section's own week", twin)
    by_section_term = write_response(
        world,
        section_id=world.taught,
        author=world.teacher.person_id,
        role="INSTRUCTOR",
        week_id=foreign_week_id,
    )
    by_week_term = write_response(
        world,
        section_id=world.taught,
        author=world.teacher.person_id,
        role="INSTRUCTOR",
        week_id=foreign_week_id,
        term_id=foreign_term,
    )
    assert is_a_refusal(by_section_term) and is_a_refusal(by_week_term), (
        f"A response to F1WW keyed to a week of another term was answered {by_section_term!r} "
        f"under the section's term and {by_week_term!r} under the week's. Fix round F4: "
        "composite keys `(section_id, term_id)` and `(week_id, term_id)`."
    )
