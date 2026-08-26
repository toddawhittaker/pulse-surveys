"""Postgres refuses what E1-10's grant does not name — ticket E1-10.

[ADR 0045](../../docs/adr/0045-the-chokepoint-refuses-an-lms-owned-write-at-table-grain-plus-one-row.md)
names the instrument this module is: "Enforcing it in the database, with a grant.
The right answer eventually, and not available yet. Refusing the *application
role* `INSERT`/`UPDATE` on these tables would be structural rather than a
convention — the ADR 0001 shape — but the launch path and E1's roster sync are the
same connection, so the grant would have to distinguish a sanctioned writer from
an unsanctioned one, and no such separation exists in E0."

E1-10 does not make that separation either: one connection still serves both. What
arrives instead is the **narrowest grant its writer needs**, so that everything
outside it is refused by the server for anybody holding that connection — a
future admin console, a Celery task, a bug in a service module. `guard_write`'s
sanction catalog is the Python half and this is the database half, and neither
replaces the other: the guard knows which *writer* is asking and the database does
not, while the database holds for callers that never ask the guard at all.

**Every test here is a pair, and the permitted half is not ceremony.** A grant
scheme that refused everything satisfies every refusal below and leaves launch-time
ingestion — one of SPEC §2.1's two arrival paths for a course — unable to write
anything at all. So each refusal is asserted beside the write it is one column
away from: `course.lms_title` may be updated and `course.lms_number` may not, on
the same row, in the same test.

**A refusal has to be the grant's.** Every one below requires SQLSTATE `42501`,
`insufficient_privilege`, and not merely "the statement raised". A `NOT NULL`
violation, a `CHECK` on a derived calendar column and a foreign key are all
`DatabaseError`s, and a test that accepted any of them would report a table this
role can write freely as refused (`docs/MISTAKES.md` entry 3).

`tests/integration/test_identity_grants.py` holds the other half of this: the
exact set of what is granted, read out of the catalog and compared as an equality.
That test says what the ACLs contain; this one says what the server does. Both,
not either — a grant recorded in `RUNTIME_COLUMN_PRIVILEGES` that no migration
issues is invisible there and fails here.
"""

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

# `insufficient_privilege` — the class 42 syntax-or-access-rule error Postgres
# raises when a role attempts something no grant covers. Named rather than
# inferred from the message, because a message is localised and a SQLSTATE is not.
INSUFFICIENT_PRIVILEGE = "42501"

# A roster service address that resolves nowhere. Nothing fetches it; it exists so
# the permitted `UPDATE` writes a value distinguishable from whatever the seeding
# helper invented.
AN_ADDRESS = "https://lti-platform.invalid/e1-10/contexts/x/memberships"


def sqlstate_of(failure: BaseException) -> str | None:
    """The SQLSTATE a driver exception carries, under either driver's spelling.

    psycopg 3 spells it `sqlstate` and psycopg 2 spells it `pgcode`; this project
    pins the first (`tests/unit/test_psycopg_driver_pinned.py`) and reading both
    costs one line rather than a future afternoon.
    """
    original = getattr(failure, "orig", failure)
    for name in ("sqlstate", "pgcode"):
        code = getattr(original, name, None)
        if isinstance(code, str):
            return code
    return None


def refused_by_the_server(
    session: Any, statement: str, parameters: dict[str, Any], what: str
) -> None:
    """Require Postgres to refuse `statement` for want of a privilege, and nothing else.

    Run inside a savepoint so a refusal does not leave the session's transaction
    aborted for the assertion that follows it — every test here poses a refusal
    and its permitted twin in one body, and an aborted transaction would make the
    second half fail for the first half's reason.
    """
    savepoint = session.begin_nested()
    try:
        session.execute(text(statement), parameters)
    except DatabaseError as refusal:
        savepoint.rollback()
        code = sqlstate_of(refusal)
        assert code == INSUFFICIENT_PRIVILEGE, (
            f"{what} raised SQLSTATE {code!r} rather than {INSUFFICIENT_PRIVILEGE!r} "
            f"(`insufficient_privilege`): {refusal}. The statement failed, and it failed for a "
            "reason that is not the grant — a constraint, a missing column, a type. A test that "
            "counted that as a refusal would report a relation this role can write freely as one "
            "the database protects."
        )
        return
    savepoint.rollback()
    pytest.fail(
        f"{what} succeeded. SPEC §8: 'LMS-owned data is never hand-edited in Pulse', and §2.1 "
        "makes courses, sections, section codes and the user record the LMS's. E1-10 grants the "
        "application role the narrowest set its launch-time writer needs; anything beyond it is "
        "reachable by every caller on this connection, including the ones that never ask "
        "`guard_write` at all — which is the bypass ADR 0045 records and could not close in E0."
    )


def permitted_by_the_server(
    session: Any, statement: str, parameters: dict[str, Any], what: str
) -> None:
    """Require Postgres to allow `statement`, saying what a refusal would cost."""
    savepoint = session.begin_nested()
    try:
        session.execute(text(statement), parameters)
    except DatabaseError as refusal:
        savepoint.rollback()
        pytest.fail(
            f"{what} was refused: {refusal} (SQLSTATE {sqlstate_of(refusal)!r}). Refusing too much "
            "is this scheme's other failure mode and the one no denial test can see: SPEC §7.3 "
            "makes the first staff launch of a section the only thing that discovers it, so an "
            "application connection that cannot write these columns leaves launch-time ingestion "
            "unable to do the job §2.1 gives it."
        )
    savepoint.rollback()


@pytest.fixture
def seeded(committed_rows: Any, metadata_tables: dict[str, Any]) -> dict[str, Any]:
    """A committed course, section and user for the statements below to aim at.

    Committed, because `application_session` is a second connection and sees
    nothing else. Seeded through the superuser connection on purpose: what is
    under test is what `pulse_app` may do to a row, not whether it could create
    one to test against.
    """
    chain: dict[str, Any] = {}
    section = committed_rows.seed("section", chain)
    user = committed_rows.seed("user", {})
    committed_rows.commit()
    return {
        "course": chain["course"],
        "section": section,
        "user": user,
        "tables": metadata_tables,
    }


def key_of(seeded: dict[str, Any], name: str) -> Any:
    """The primary key value of one seeded row (ADR 0016 makes every key one uuid)."""
    table = seeded["tables"][name]
    return seeded[name][next(iter(table.primary_key.columns)).name]


def insert_like(seeded: dict[str, Any], name: str, **changes: Any) -> tuple[str, dict[str, Any]]:
    """A textual `INSERT` copying one seeded row, with `changes` applied.

    For a table whose required foreign keys the application connection has no
    business creating parents for. Copying is what keeps the statement about the
    grant: every other value is one the schema already accepted, so a refusal
    cannot be a constraint this test happened to trip.
    """
    table = seeded["tables"][name]
    row = seeded[name]
    key = next(iter(table.primary_key.columns)).name
    values: dict[str, Any] = {}
    for column in table.columns:
        if column.name == key or column.computed is not None:
            continue
        values[column.name] = changes.get(column.name, row[column.name])
    columns = ", ".join(f'"{column}"' for column in values)
    binds = ", ".join(f":{column}" for column in values)
    # S608 is for SQL assembled out of a variable; every name here comes from
    # `Base.metadata`, and every value travels as a bind parameter.
    statement = f'INSERT INTO public."{name}" ({columns}) VALUES ({binds})'  # noqa: S608
    return statement, values


def test_the_application_role_may_correct_a_courses_title_and_may_not_touch_its_number(
    seeded: dict[str, Any], application_session: Any
) -> None:
    """The pair that column-scoped `UPDATE` exists for, on one row, one column apart.

    E1-10's writer corrects `lms_title` — a fallback giving way to the platform's
    real title, or a course the platform renamed — and sets `title_is_fallback`
    beside it. It never revises `lms_number`: the number is what identifies the
    course, SPEC §8 derives `level` from it, and a launch that could rewrite it
    could move a course between levels and orphan every report keyed to the old
    one.

    **The mutation this exists to survive**: `GRANT UPDATE ON public.course TO
    pulse_app` in place of the two column-scoped grants. That is the natural,
    convenient form, it makes every test in the two provisioning modules pass, and
    `test_identity_grants.py`'s equality is the only other thing that would notice.
    Here it is the refusal below that goes green-to-red.
    """
    course = {"id": key_of(seeded, "course")}
    permitted_by_the_server(
        application_session,
        "UPDATE public.course SET lms_title = 'A title the platform supplied' WHERE id = :id",
        course,
        "Updating `course.lms_title` as the application role",
    )
    permitted_by_the_server(
        application_session,
        "UPDATE public.course SET title_is_fallback = true WHERE id = :id",
        course,
        "Updating `course.title_is_fallback` as the application role",
    )
    refused_by_the_server(
        application_session,
        "UPDATE public.course SET lms_number = '321' WHERE id = :id",
        course,
        "Updating `course.lms_number` as the application role",
    )


def test_the_application_role_may_store_a_roster_address_and_may_not_touch_a_derived_calendar(
    seeded: dict[str, Any], application_session: Any
) -> None:
    """The same pair on `section`, and the withheld half is ADR 0021's.

    SPEC §7.3 has a staff launch store the roster service address and a later one
    update it, so `lms_context_memberships_url` is granted. ADR 0021 gives the four
    derived calendar columns "exactly one writer", `apply_section_code`, and E0-35
    put a syntactic sweep behind that rule —
    `tests/unit/test_a_sections_derived_calendar_has_one_assignment_site.py` — which
    reads the source and cannot see a statement assembled at run time. Withholding
    the privilege is the half that holds whatever the source looks like.

    `length_weeks` is the column probed because ADR 0021 records that "no `CHECK`
    constraint ties the three calendar columns to each other", so a value written
    here would be accepted by the schema — which is exactly what makes the refusal
    attributable to the grant rather than to a constraint.
    """
    section = {"id": key_of(seeded, "section")}
    permitted_by_the_server(
        application_session,
        "UPDATE public.section SET lms_context_memberships_url = :address WHERE id = :id",
        {**section, "address": AN_ADDRESS},
        "Storing `section.lms_context_memberships_url` as the application role",
    )
    refused_by_the_server(
        application_session,
        "UPDATE public.section SET length_weeks = 6 WHERE id = :id",
        section,
        "Updating `section.length_weeks` as the application role",
    )
    refused_by_the_server(
        application_session,
        "UPDATE public.section SET lms_section_code = 'Z9FF' WHERE id = :id",
        section,
        "Updating `section.lms_section_code` as the application role",
    )


def test_the_application_role_may_insert_a_user_and_may_never_update_one(
    seeded: dict[str, Any], application_session: Any
) -> None:
    """`user` is insert-if-absent and never rewritten, and the database is what says so.

    ADR 0045: `user` is in the guarded set because "`user.lms_user_id` is the
    `sub` claim verbatim (ADR 0014: the platform supplies the value and Pulse never
    edits it) and §4 keys every response to it". E1-10's writer inserts the row on
    a launch that has never been seen and leaves it alone afterwards, so no
    `UPDATE` is granted on this table in any form — not table-wide and not on a
    column.

    This is the same shape SPEC §8's append-only `classification` grant takes, and
    it is worth more here: `lms_user_id` is the join key every response in the
    product hangs from, so a connection that could rewrite one could reassign a
    term's answers to a different person, silently and with nothing erroring.
    """
    statement, parameters = insert_like(
        seeded, "user", lms_user_id="e1-10-a-subject-nobody-has-launched-as"
    )
    permitted_by_the_server(
        application_session,
        statement,
        parameters,
        "Inserting a `user` row as the application role",
    )
    refused_by_the_server(
        application_session,
        'UPDATE public."user" SET lms_user_id = :sub WHERE id = :id',
        {"sub": "e1-10-a-different-subject", "id": key_of(seeded, "user")},
        "Updating `user.lms_user_id` as the application role",
    )


# The three tables a launch inserts into, and the `DELETE` withheld on each,
# spelled as whole statements rather than assembled from a name. Two reasons: a
# reserved table name has to be quoted and a relation name interpolated into SQL
# is what ruff's `S608` is for, so writing them out costs nothing and reads as
# what it is.
DELETES_THAT_MUST_BE_REFUSED = {
    "course": "DELETE FROM public.course",
    "section": "DELETE FROM public.section",
    "user": 'DELETE FROM public."user"',
}


@pytest.mark.parametrize(("relation", "statement"), sorted(DELETES_THAT_MUST_BE_REFUSED.items()))
def test_the_application_role_cannot_delete_a_row_a_launch_discovered(
    seeded: dict[str, Any], application_session: Any, relation: str, statement: str
) -> None:
    """A launch discovers rows; nothing on this connection removes one.

    `DELETE` is withheld on all three, and the reason is the same as the reason
    `classification` withholds it: a privilege nobody needs is a privilege
    somebody eventually spends. Deleting a `course` takes a term's sections and
    every report keyed to them; deleting a `user` takes the join key §4 hangs
    every response from, which is the same loss one table over.

    The permitted half for these tables is asserted in the two tests above and in
    `test_the_application_role_cannot_read_back_the_defect_it_recorded` below, so
    a scheme that granted nothing at all does not pass here by accident.
    """
    refused_by_the_server(
        application_session,
        statement,
        {},
        f"Deleting from `{relation}` as the application role",
    )


def test_the_application_role_cannot_read_back_the_defect_it_recorded(
    application_session: Any, insert_statement_for: Any
) -> None:
    """`launch_defect` is written and never read on this connection, and that has a consequence.

    E1-10 grants `INSERT` and nothing else: the launch path records a defect and
    moves on, and E11 builds the surface that reads them later, on whatever
    connection that turns out to be. Withholding `SELECT` keeps the read path a
    decision E11 makes rather than one this ticket makes by accident.

    **This is the grant that shapes the writer, so it is worth stating plainly.**
    Without `SELECT`, an `INSERT ... RETURNING id` is refused too — Postgres checks
    the returned columns against the reader's privileges — so the row's primary key
    has to be generated in Python rather than read back. E1-08 hit the identical
    constraint on `lti_launch_nonce` and `test_identity_grants.py` records it
    there: "the primary key is generated in Python rather than read back with
    `RETURNING`". A writer that lets SQLAlchemy fetch the server default fails
    here, on a launch that was otherwise fine.

    The insert beside it is the control: a role that held nothing at all on this
    table would satisfy the refusal and would make the defect unrecordable, which
    is `docs/MISTAKES.md` entry 26 — the fallback path swallowing the defect that
    triggered it.
    """
    statement, parameters = insert_statement_for("launch_defect", kind="unknown_prefix")
    permitted_by_the_server(
        application_session,
        statement,
        parameters,
        "Recording a launch defect as the application role",
    )
    refused_by_the_server(
        application_session,
        "SELECT kind FROM public.launch_defect",
        {},
        "Reading `launch_defect` as the application role",
    )


def test_the_application_role_may_read_the_three_configuration_tables_a_launch_resolves_against(
    application_session: Any,
) -> None:
    """The look-ups, granted as `SELECT` and as nothing else.

    A launch resolves the prefix its context label names, the term whose dates
    contain the day of the launch, and that term's start-letter map row, before it
    writes anything. Without these reads every launch is refused by Postgres with
    42501 rather than by any check the writer makes — which is a 500 in the middle
    of somebody's launch rather than a defect record.

    **`SELECT` alone**, and that is the assertion: §2.1 builds the org and the
    calendar top-down in the admin console, so a launch may not create the
    containment chain it hangs from. The refusal beside each read is what says the
    grant is a read and not a convenience.
    """
    look_ups = {
        "prefix": ("SELECT 1 FROM public.prefix", "DELETE FROM public.prefix"),
        "term": ("SELECT 1 FROM public.term", "DELETE FROM public.term"),
        "start_letter_map": (
            "SELECT 1 FROM public.start_letter_map",
            "DELETE FROM public.start_letter_map",
        ),
    }
    for relation, (read, remove) in sorted(look_ups.items()):
        permitted_by_the_server(
            application_session, read, {}, f"Reading `{relation}` as the application role"
        )
        refused_by_the_server(
            application_session,
            remove,
            {},
            f"Deleting from `{relation}` as the application role",
        )
