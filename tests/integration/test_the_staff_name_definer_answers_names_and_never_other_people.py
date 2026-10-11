"""The channel answers staff names, never other people — E7-01, done-when 5, and SPEC §4.

> The definer cannot return a student's name, an email address, or any column but
> the name, whatever section is asked. A test that enrols a student whose name is
> distinctive proves it.

`person` holds students as well as staff (the ticket: "A column grant is the wrong
shape: `person` holds students too, and a grant cannot filter rows"), so the
definer is the only thing between `pulse_app` and every name in the institution.
This module asks it from three sides:

  - **what it answers**: a student with a distinctive `person.identity_name`, a
    distinctive `user_identity` name and a distinctive address is enrolled in
    `F1WW`, and every reader in the world asks about every section; no answer
    carries any of the three, nor the student's person key, and every person an
    answer names is a member of staff;
  - **what shape it answers in**: exactly `(person_id uuid, display_name text)`,
    read off the catalog (work order decision 1) and off every live result;
  - **what its owner can reach**: nothing at all on `user_identity`, where the
    address lives, and no write anywhere — ADR 0043's pattern, where "the
    definer's privileges" are a list one can read against one body.

**Which failure a red is, before E7-01 lands.** Every test fails on
`require_the_definer`, naming `public.section_staff_names(uuid,uuid,uuid)`.
"""

from typing import Any

import pytest
from fixtures.staff_names import (
    DEFINER_COLUMNS,
    DEFINER_RESULT,
    DEFINER_ROLE,
    DEFINER_SIGNATURE,
    IDENTITY_NAME_COLUMN,
    STAFF_NAMES,
    TEACHER_NAME,
    StaffNameWorld,
    ask_the_definer,
    require_the_application_role,
    require_the_definer,
)
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

STUDENT_PERSON_NAME = "Quintessa Marrowby-A-Student"
STUDENT_IDENTITY_NAME = "Quintessa Marrowby-Identity-Row"
STUDENT_EMAIL = "quintessa.marrowby@e7-01-student.invalid"

THE_FUNCTION = """
    SELECT p.prosecdef AS security_definer,
           pg_get_function_result(p.oid) AS result,
           r.rolname AS owner,
           r.rolsuper AS owner_is_superuser,
           r.rolcanlogin AS owner_can_log_in,
           coalesce(p.proconfig, ARRAY[]::text[]) AS settings
    FROM pg_proc p
    JOIN pg_roles r ON r.oid = p.proowner
    WHERE p.oid = CAST(:signature AS regprocedure)
"""

WRITES = ("INSERT", "UPDATE", "DELETE", "TRUNCATE")
EVERY_TABLE_PRIVILEGE = (
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "TRUNCATE",
    "REFERENCES",
    "TRIGGER",
)
EVERY_COLUMN_PRIVILEGE = ("SELECT", "INSERT", "UPDATE", "REFERENCES")

RELATIONS_WRITABLE_BY = """
    SELECT c.relname, p.privilege
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN unnest(CAST(:privileges AS text[])) AS p(privilege)
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'v', 'm')
      AND has_table_privilege(:role, c.oid, p.privilege)
    ORDER BY 1, 2
"""
TABLE_PRIVILEGES_ON = """
    SELECT p.privilege
    FROM unnest(CAST(:privileges AS text[])) AS p(privilege)
    WHERE has_table_privilege(:role, CAST(:relation AS regclass), p.privilege)
"""
COLUMN_PRIVILEGES_ON = """
    SELECT a.attname, p.privilege
    FROM pg_attribute a
    CROSS JOIN unnest(CAST(:privileges AS text[])) AS p(privilege)
    WHERE a.attrelid = CAST(:relation AS regclass) AND a.attnum > 0 AND NOT a.attisdropped
      AND has_column_privilege(:role, a.attrelid, a.attnum, p.privilege)
"""
TABLE_OWNER = "SELECT tableowner FROM pg_tables WHERE schemaname = 'public' AND tablename = :name"


def a_distinctive_student(world: StaffNameWorld) -> Any:
    """A student of `F1WW` whose person, identity name and address are all distinctive.

    Given a `person` row as well as a `user` (most launched students have none,
    ADR 0028), because `person.identity_name` is the column the definer reads
    names from: a student with no person row could not be answered by a definer
    that read the wrong rows of the right column, and this one can.
    """
    student = world.a_student("distinctive", world.taught, with_person=True)
    world.name(student.person_id, STUDENT_PERSON_NAME)
    world.web_identity.stored_identity(
        user_id=student.user_id,
        email=STUDENT_EMAIL,
        **{IDENTITY_NAME_COLUMN: STUDENT_IDENTITY_NAME},
    )
    return student


def test_no_reader_asking_any_section_is_answered_a_student_or_an_address(
    staff_names: StaffNameWorld,
) -> None:
    """Every reader by every section: only staff come back, in two columns, and never the student.

    **The positive control** is the instructor's own answer for `F1WW`, which must
    carry the instructor's name — a definer answering nobody would satisfy every
    absence below.

    **The mutations this kills:** the instructor set read from everybody attached
    to the section (an enrollment join answers the student as an "instructor");
    `display_name` read from `user_identity` rather than `person` (the address or
    the identity row's name comes back); the result widened by a column (an
    email, a role). **The near miss it must survive:** the student is a reader
    of `F1WW` and is answered its instructor — being a reader is not being named.
    """
    world = staff_names
    require_the_application_role(world.application_session)
    require_the_definer(world.application_session)
    student = a_distinctive_student(world)
    assert world.teacher and world.lead and world.chair and world.other_chair
    assert world.sibling_lead and world.sibling_section_teacher
    # Staff by person key; the student under each key, since they hold both.
    readers = {
        "the instructor": {"reader_person_id": world.teacher.person_id},
        "the lead": {"reader_person_id": world.lead.person_id},
        "the chair": {"reader_person_id": world.chair.person_id},
        "another department's chair": {"reader_person_id": world.other_chair.person_id},
        "a sibling lead": {"reader_person_id": world.sibling_lead.person_id},
        "the sibling section's instructor": {
            "reader_person_id": world.sibling_section_teacher.person_id
        },
        "the student, by user key": {"reader_user_id": student.user_id},
        "the student, by person key": {"reader_person_id": student.person_id},
    }

    seen_names: set[str] = set()
    seen_people: set[str] = set()
    shapes: set[tuple[str, ...]] = set()
    for label, reader in readers.items():
        for section_label, section_id in world.every_section().items():
            answered = ask_the_definer(world.application_session, section_id=section_id, **reader)
            shapes.add(answered.columns)
            seen_names.update(answered.names)
            seen_people.update(answered.person_ids)
            for row in answered.rows:
                assert set(row) == set(DEFINER_COLUMNS), (
                    f"{label} asking about {section_label} was answered a row with "
                    f"{sorted(row)}; the definer answers {list(DEFINER_COLUMNS)} and nothing else."
                )

    control = ask_the_definer(
        world.application_session, section_id=world.taught, reader_person_id=world.teacher.person_id
    )
    assert TEACHER_NAME in control.names, (
        f"The control: the instructor asking about F1WW was answered {control.names}, so every "
        "absence below would be satisfied by a definer that answers nobody."
    )
    assert shapes == {
        DEFINER_COLUMNS
    }, f"The definer answered result shapes {sorted(shapes)}; it answers {DEFINER_COLUMNS} only."
    forbidden = {STUDENT_PERSON_NAME, STUDENT_IDENTITY_NAME, STUDENT_EMAIL}
    assert not seen_names & forbidden, (
        f"The definer answered {sorted(seen_names & forbidden)}, which belong to a student of "
        "F1WW. E7-01 done-when 5: it cannot return a student's name or an email address."
    )
    assert (
        str(student.person_id) not in seen_people
    ), "The definer answered the student's own person key as one of a section's staff."
    strangers = sorted(name for name in seen_names if name not in STAFF_NAMES)
    assert (
        not strangers
    ), f"The definer answered {strangers}, none of whom is a member of staff in this world."


def test_the_definer_declares_exactly_a_person_key_and_a_display_name(
    staff_names: StaffNameWorld,
) -> None:
    """The catalog: `RETURNS TABLE(person_id uuid, display_name text)`, `SECURITY DEFINER`.

    **The mutation this kills:** a third column added to the declaration (an
    email, a role, a flag), which a caller selecting `*` would carry on to a page;
    and the function declared `SECURITY INVOKER`, under which `pulse_app` (which
    holds no privilege on `person`) is refused every name.
    """
    world = staff_names
    require_the_definer(world.application_session)
    session = world.rows.session
    session.rollback()
    found = session.execute(text(THE_FUNCTION), {"signature": DEFINER_SIGNATURE}).mappings().one()
    assert found["result"] == DEFINER_RESULT, (
        f"`{DEFINER_SIGNATURE}` returns `{found['result']}`, not `{DEFINER_RESULT}` (work order "
        "decision 1). 'No other column, ever' (decision 2)."
    )
    assert found["security_definer"], f"`{DEFINER_SIGNATURE}` is not `SECURITY DEFINER`."


def test_the_definer_is_owned_by_its_own_role_and_pins_its_search_path(
    staff_names: StaffNameWorld,
) -> None:
    """ADR 0043's pattern: a NOLOGIN, non-superuser owner of its own, and `pg_temp` last.

    **The mutation this kills:** the function owned by the migration identity (a
    superuser, which can read every name in `person` and `user_identity`); an
    owner that can log in; and a `search_path` without `pg_temp` last, under which
    a caller's temporary `person` table shadows the real one.
    """
    world = staff_names
    require_the_definer(world.application_session)
    session = world.rows.session
    session.rollback()
    found = session.execute(text(THE_FUNCTION), {"signature": DEFINER_SIGNATURE}).mappings().one()
    assert found["owner"] == DEFINER_ROLE, (
        f"`{DEFINER_SIGNATURE}` is owned by {found['owner']!r}, not `{DEFINER_ROLE}` (work order "
        "decision 1)."
    )
    assert not found["owner_is_superuser"] and not found["owner_can_log_in"], (
        f"`{DEFINER_ROLE}` is a superuser or can log in; ADR 0043's owner is NOLOGIN and holds only "
        "what the body reads."
    )
    paths = [setting for setting in found["settings"] if setting.startswith("search_path=")]
    assert len(paths) == 1, f"`{DEFINER_SIGNATURE}` sets no `search_path` ({found['settings']})."
    entries = [entry.strip().strip('"') for entry in paths[0].split("=", 1)[1].split(",")]
    assert (
        entries and entries[-1] == "pg_temp"
    ), f"`{DEFINER_SIGNATURE}`'s search_path is {entries}; ADR 0043 puts `pg_temp` last."


def test_the_definers_owner_holds_nothing_on_user_identity(staff_names: StaffNameWorld) -> None:
    """Not one privilege on `user_identity`, at table grain or on any column.

    The address lives there (ADR 0001); the name the channel answers is
    `person.identity_name` (decision 2), so the owner has no use for the table.

    **The control** (`docs/MISTAKES.md` entry 35): the table's own owner is asked
    the same two questions and found holding privileges, so the probe can see one.

    **The mutation this kills:** `GRANT SELECT ON public.user_identity` (or a
    column of it) to the definer's owner, which puts every student's address one
    function body away from `pulse_app`.
    """
    world = staff_names
    require_the_definer(world.application_session)
    session = world.rows.session
    session.rollback()
    owner = session.execute(text(TABLE_OWNER), {"name": "user_identity"}).scalar_one()

    def held(role: str) -> list[str]:
        on_table = [
            row[0]
            for row in session.execute(
                text(TABLE_PRIVILEGES_ON),
                {
                    "role": role,
                    "relation": "public.user_identity",
                    "privileges": list(EVERY_TABLE_PRIVILEGE),
                },
            )
        ]
        on_columns = [
            f"{row[0]}:{row[1]}"
            for row in session.execute(
                text(COLUMN_PRIVILEGES_ON),
                {
                    "role": role,
                    "relation": "public.user_identity",
                    "privileges": list(EVERY_COLUMN_PRIVILEGE),
                },
            )
        ]
        return on_table + on_columns

    assert held(owner), (
        f"The control: `user_identity`'s own owner {owner!r} is reported holding nothing on it, so "
        "this probe cannot see a privilege at all."
    )
    reached = held(DEFINER_ROLE)
    assert not reached, (
        f"`{DEFINER_ROLE}` holds {reached} on `user_identity`. E7-01 done-when 5: the channel "
        "cannot return an email address, and the owner of a function `pulse_app` may call is the "
        "outer bound of what it can return."
    )


def test_the_definers_owner_writes_nothing(staff_names: StaffNameWorld) -> None:
    """No `INSERT`, `UPDATE`, `DELETE` or `TRUNCATE` on any relation in `public`.

    The channel reads. **The control:** the same probe finds `pulse_app` holding
    a write it certainly holds (`INSERT` on `response`, since E2's submission
    path), so an empty answer is the owner's and not the probe's.

    **The mutation this kills:** a grants file that gives the owner `ALL` on a
    table it reads.
    """
    world = staff_names
    require_the_definer(world.application_session)
    session = world.rows.session
    session.rollback()

    def writable(role: str) -> list[tuple[str, str]]:
        return [
            (row[0], row[1])
            for row in session.execute(
                text(RELATIONS_WRITABLE_BY), {"role": role, "privileges": list(WRITES)}
            )
        ]

    assert ("response", "INSERT") in writable(
        "pulse_app"
    ), "The control: the probe does not find `pulse_app`'s `INSERT` on `response`."
    written = writable(DEFINER_ROLE)
    assert not written, f"`{DEFINER_ROLE}` may write {written}; the name channel only reads."
