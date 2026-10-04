"""The teaching grant ends through one guarded door, and leaves a record — E5.1-02, criterion 3.

"The grant is ended through a `SECURITY DEFINER` function that is a sibling of
`record_teaching_instructor`. The runtime role still holds no `DELETE` on
`role_assignment`, and a grant query asserts that. The function refuses any
assignment that is not section-scoped `INSTRUCTOR`." And: "The same function writes
a row to a new append-only table, `ended_teaching_grant`, in the same transaction
… The runtime role can insert into that table only through the function; it holds
no `UPDATE` or `DELETE` on it. A test through the production connection shows that
a grant cannot be ended without its row, and that the row survives the deletion."

**Why a function and not a grant.** A grant cannot bound a column's *value*:
`DELETE` on `role_assignment` would let the connection every screen runs on delete
a `CARE` row, or a lead's, as readily as a teaching grant. The function's body
chooses what it may end, which is the argument `record_teaching_instructor` was
built on (ADR 0096) arriving from the other direction.

**Every call and every privilege question is put to `pulse_app`'s own connection**
(`application_session`), never to the migration owner or to a superuser that has
switched roles (`docs/MISTAKES.md` entry 46). The one exception is the Care
denial, which acts as `pulse_care` the way
`test_the_roster_definers_answer_a_point_query_and_nothing_more.py` already does.
Rows are seeded and read back on the superuser connection, which is the only one
that can see `role_assignment` and `ended_teaching_grant` at all.

**Every privilege absence has a control that finds a privilege `pulse_app`
certainly holds** (`docs/MISTAKES.md` entry 35): `INSERT` on `nrps_call`, which
the roster sync has written through since E1-11 and
`test_identity_grants.py::RUNTIME_BASE_TABLE_PRIVILEGES` records.

**Every refusal is a refused statement with its SQLSTATE**, never an empty
result: a missing table (42P01) or a missing function (42883) "fails" too, and
says something else entirely.

**The interface is E5.1-02's work order's** (D1, D2): `public.end_teaching_
instructor(assignment_id uuid, nrps_call_id uuid, ended_on date)`, owned by the
NOLOGIN role `pulse_grant_end_definer`, refusing with SQLSTATE 42501; and the
table's six named columns. Nothing here discovers either.

**How a red reads.** Each test calls `require_the_grant_ending_definer` or
`require_the_ended_teaching_grant_table` as its first statement, so a missing
deliverable is a FAILED naming it, never an ERROR at setup (`docs/MISTAKES.md`
entry 44). The test that `pulse_app` holds no `DELETE` on `role_assignment` is
the "still" in the criterion, and it goes red if the ending is built on a grant
instead.
"""

from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

import pytest
from fixtures.roster_sync import (
    END_TEACHING_INSTRUCTOR,
    END_TEACHING_INSTRUCTOR_CALL,
    ENDED_TEACHING_GRANT_TABLE,
    GRANT_END_DEFINER_ROLE,
    ended_teaching_grants,
    require_the_ended_teaching_grant_table,
    require_the_grant_ending_definer,
)
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

APPLICATION_ROLE = "pulse_app"
CARE_ROLE = "pulse_care"
INSUFFICIENT_PRIVILEGE = "42501"

INSTRUCTOR = "INSTRUCTOR"

# Every table privilege Postgres has, so "nothing" is checked against all of them.
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")

# The day a direct call says the grant ended. A fixed date rather than today,
# because the function records what it is handed and the assertion compares it.
AN_ENDING_DAY = date(2026, 10, 2)

CURRENT_ROLE = "SELECT current_user"
HAS_TABLE_PRIVILEGE = "SELECT has_table_privilege(:relation, :privilege)"
# The columns of one relation the current role holds a privilege on, at column
# grain. `has_column_privilege` answers for privileges held by membership and for
# a whole-table grant as well, so a role holding either is found.
HELD_COLUMNS = """
    SELECT a.attname
    FROM pg_attribute a
    WHERE a.attrelid = to_regclass(:relation)
      AND a.attnum > 0
      AND NOT a.attisdropped
      AND (
          has_column_privilege(a.attrelid, a.attnum, 'SELECT')
          OR has_column_privilege(a.attrelid, a.attnum, 'INSERT')
          OR has_column_privilege(a.attrelid, a.attnum, 'UPDATE')
          OR has_column_privilege(a.attrelid, a.attnum, 'REFERENCES')
      )
"""

# The definer's own catalog entry.
THE_FUNCTION = """
    SELECT p.prosecdef AS security_definer,
           r.rolname AS owner,
           r.rolsuper AS owner_is_superuser,
           r.rolcanlogin AS owner_can_log_in,
           coalesce(p.proconfig, ARRAY[]::text[]) AS settings,
           coalesce(p.proargnames, ARRAY[]::text[]) AS argument_names,
           array(
               SELECT format_type(a.argtype, NULL)
               FROM unnest(p.proargtypes::oid[]) WITH ORDINALITY AS a(argtype, idx)
               ORDER BY a.idx
           ) AS argument_types
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    JOIN pg_roles r ON r.oid = p.proowner
    WHERE n.nspname = 'public' AND p.proname = :name
"""

# What a role may do to whole relations, and to single columns, anywhere in `public`.
WHOLE_RELATION_PRIVILEGES = """
    SELECT c.relname, p.privilege
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
                            'REFERENCES', 'TRIGGER']) AS p(privilege)
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'v', 'm')
      AND has_table_privilege(:role, c.oid, p.privilege)
"""
COLUMN_GRANTS = """
    SELECT c.relname, a.attname, p.privilege
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
    CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'REFERENCES']) AS p(privilege)
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'v', 'm')
      AND has_column_privilege(:role, c.oid, a.attnum, p.privilege)
"""

# The owner's whole reach, from E5.1-02's work order (D1) and not from the SQL it
# polices (`docs/MISTAKES.md` entry 19): "`SELECT, DELETE ON public.role_assignment`;
# `SELECT (id, section_id, response_code) ON public.nrps_call`; `INSERT ON
# public.ended_teaching_grant`. Nothing else."
GRANT_END_DEFINER_WHOLE_RELATIONS = frozenset(
    {
        ("role_assignment", "SELECT"),
        ("role_assignment", "DELETE"),
        (ENDED_TEACHING_GRANT_TABLE, "INSERT"),
    }
)
GRANT_END_DEFINER_NRPS_CALL_COLUMNS = frozenset({"id", "section_id", "response_code"})


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def sqlstate(failure: Any) -> str | None:
    return getattr(getattr(failure, "orig", None), "sqlstate", None)


def attempted(session: Any, statement: str, parameters: dict[str, Any] | None = None) -> Any:
    """Run `statement` in a savepoint that is **always** rolled back; answer its error or `None`.

    Always rolled back, not committed on success: a statement that *should* be
    refused and is not — a bare `DELETE FROM public.role_assignment` in a world
    where the grant came back — must not delete anything on its way to failing
    the test.
    """
    from sqlalchemy.exc import DatabaseError

    savepoint = session.begin_nested()
    try:
        session.execute(text(statement), parameters or {})
    except DatabaseError as failure:
        savepoint.rollback()
        return failure
    savepoint.rollback()
    return None


def end_grant(session: Any, *, assignment_id: Any, nrps_call_id: Any, ended_on: Any) -> Any:
    """Call the ending definer on `session` and commit; answer the error it raised, or `None`.

    The function's return value is deliberately not handed back: every test here
    asserts the rows the call left, never what it answered (`docs/MISTAKES.md`
    entry 49).
    """
    from sqlalchemy.exc import DatabaseError

    try:
        session.execute(
            text(END_TEACHING_INSTRUCTOR_CALL),
            {"assignment_id": assignment_id, "nrps_call_id": nrps_call_id, "ended_on": ended_on},
        )
    except DatabaseError as failure:
        session.rollback()
        return failure
    session.commit()
    return None


def require_the_application_role(session: Any) -> None:
    """The session really is `pulse_app`, or every assertion below measures somebody else."""
    current = session.execute(text(CURRENT_ROLE)).scalar_one()
    assert current == APPLICATION_ROLE, (
        f"`application_session` connects as {current!r}, not `{APPLICATION_ROLE}`. Every privilege "
        "this module asserts is a claim about the role production runs as (`docs/MISTAKES.md` "
        "entry 46), and a superuser passes every one of them."
    )


def assignment_exists(committed_rows: Any, assignment_id: Any) -> bool:
    from sqlalchemy import select

    graph = committed_rows.graph
    committed_rows.session.rollback()
    table = graph.assignments
    return (
        committed_rows.session.execute(
            select(table.c[graph.assignment_key]).where(
                table.c[graph.assignment_key] == assignment_id
            )
        ).first()
        is not None
    )


def a_call(committed_rows: Any, section_id: Any, response_code: int | None) -> Any:
    """One `nrps_call` row for `section_id`, carrying `response_code`, committed."""
    row = committed_rows.seed(
        "nrps_call",
        {},
        section_id=section_id,
        url=f"https://roster.e5-1-02.invalid/{uuid4().hex[:12]}",
        response_code=response_code,
        members_seen=1 if response_code is not None else None,
        called_at=datetime.now(UTC),
    )
    committed_rows.commit()
    return row["id"]


@pytest.fixture
def a_teaching_grant(committed_rows: Any) -> dict[str, Any]:
    """A section, a person teaching it, a successful roster call of it, and a second section.

    Rows only: nothing here touches a deliverable of this ticket, so a fixture
    is safe from `docs/MISTAKES.md` entry 44 — every guard is in the test bodies.
    """
    graph = committed_rows.graph
    section = graph.scope("section")
    other_section = graph.fresh_scope("section")
    person = graph.person()
    assignment = graph.assign(INSTRUCTOR, scope=section, person=person)
    committed_rows.commit()
    return {
        "section": section,
        "other_section": other_section,
        "person": person,
        "assignment": assignment[graph.assignment_key],
        "call": a_call(committed_rows, section, 200),
    }


# ---------------------------------------------------------------------------
# The privileges `pulse_app` holds, and does not.
# ---------------------------------------------------------------------------


def test_the_application_role_still_holds_no_delete_on_role_assignment(
    application_session: Any, a_teaching_grant: dict[str, Any], committed_rows: Any
) -> None:
    """ "The runtime role still holds no `DELETE` on `role_assignment`, and a grant query asserts that."

    Asked twice, in two currencies, on `pulse_app`'s own connection: the catalog's
    answer, and a bare `DELETE` with no `WHERE` — which needs `DELETE` and nothing
    else, so a 42501 is that privilege and not a missing `SELECT` on the column a
    `WHERE` would read. Rolled back whatever happens.

    **The control** (`docs/MISTAKES.md` entry 35): the same query must find
    `INSERT` on `nrps_call`, which this role certainly holds. A query that answered
    false for everything would satisfy the absence perfectly.

    **The mutation this kills:** ending the grant through `GRANT DELETE ON
    public.role_assignment TO pulse_app` instead of a definer — a grant cannot bound
    the role it deletes, so a `CARE` row would go as readily as a teaching one.
    Green today; red the day that shortcut is taken.
    """
    require_the_application_role(application_session)
    holds = application_session.execute(
        text(HAS_TABLE_PRIVILEGE), {"relation": "public.nrps_call", "privilege": "INSERT"}
    ).scalar_one()
    assert holds is True, (
        "`has_table_privilege` answers that `pulse_app` cannot insert into `nrps_call`, which the "
        "roster sync has done since E1-11. The query is not seeing this role's grants, so its "
        "answer below means nothing."
    )
    may_delete = application_session.execute(
        text(HAS_TABLE_PRIVILEGE), {"relation": "public.role_assignment", "privilege": "DELETE"}
    ).scalar_one()
    assert may_delete is False, (
        "`pulse_app` holds `DELETE` on `role_assignment`. E5.1-02 ends a teaching grant through a "
        "definer precisely because a grant cannot bound which role's row is deleted."
    )
    failure = attempted(application_session, "DELETE FROM public.role_assignment")
    assert failure is not None and sqlstate(failure) == INSUFFICIENT_PRIVILEGE, (
        f"A bare delete of every `public.role_assignment` row on `pulse_app` was answered {failure!r} "
        f"(SQLSTATE {sqlstate(failure)}), not refused with {INSUFFICIENT_PRIVILEGE}."
    )
    assert assignment_exists(
        committed_rows, a_teaching_grant["assignment"]
    ), "The teaching grant this test seeded is gone after a statement that should have been refused."


def test_the_application_role_holds_nothing_on_the_ended_record(
    application_session: Any, a_teaching_grant: dict[str, Any], committed_rows: Any
) -> None:
    """ "It holds no `UPDATE` or `DELETE` on it", and inserts "only through the function".

    E5.1-02's work order (D2) makes the record append-only by grant: `pulse_app`
    holds nothing on it at all, and the only writer is the definer. So every
    table privilege is asked about, every column, and three statements are tried
    and must be refused — an insert of a well-formed row, an update and a delete,
    each needing only the privilege it is about (no `RETURNING`, no `WHERE`).

    **The control** is `INSERT` on `nrps_call` and `pulse_app`'s columns of it,
    found by the same two queries (`docs/MISTAKES.md` entry 35).

    **The mutations this kills:** any grant to `pulse_app` on the table — an
    `INSERT` that lets the application forge an ending, an `UPDATE` that lets it
    re-date one, a `DELETE` that lets it erase one, a `SELECT` that the record
    does not need to be read through.
    """
    require_the_ended_teaching_grant_table(committed_rows.session)
    require_the_application_role(application_session)
    relation = f"public.{ENDED_TEACHING_GRANT_TABLE}"

    assert application_session.execute(
        text(HAS_TABLE_PRIVILEGE), {"relation": "public.nrps_call", "privilege": "INSERT"}
    ).scalar_one(), "The control failed: `pulse_app` is reported unable to insert into `nrps_call`."
    control_columns = set(
        application_session.execute(text(HELD_COLUMNS), {"relation": "public.nrps_call"}).scalars()
    )
    assert control_columns, (
        "The column query finds no column of `nrps_call` that `pulse_app` holds anything on, so it "
        "cannot see this role's grants and its empty answer below means nothing."
    )

    held = [
        privilege
        for privilege in TABLE_PRIVILEGES
        if application_session.execute(
            text(HAS_TABLE_PRIVILEGE), {"relation": relation, "privilege": privilege}
        ).scalar_one()
    ]
    assert not held, f"`pulse_app` holds {held} on `{relation}`; the work order gives it nothing."
    columns = sorted(
        application_session.execute(text(HELD_COLUMNS), {"relation": relation}).scalars()
    )
    assert not columns, f"`pulse_app` holds a column privilege on `{relation}`: {columns}."

    values = {
        "assignment_id": uuid4(),
        "person_id": a_teaching_grant["person"],
        "section_id": a_teaching_grant["section"],
        "ended_on": AN_ENDING_DAY,
        "nrps_call_id": a_teaching_grant["call"],
    }
    statements = {
        "insert": (
            f"INSERT INTO {relation} "  # noqa: S608 — the relation is this module's constant
            "(assignment_id, person_id, section_id, role, ended_on, nrps_call_id) VALUES "
            "(CAST(:assignment_id AS uuid), CAST(:person_id AS uuid), CAST(:section_id AS uuid), "
            "'INSTRUCTOR', CAST(:ended_on AS date), CAST(:nrps_call_id AS uuid))"
        ),
        "update": f"UPDATE {relation} SET ended_on = CAST(:ended_on AS date)",  # noqa: S608
        "delete": f"DELETE FROM {relation}",  # noqa: S608
    }
    answered = {
        name: attempted(application_session, statement, values)
        for name, statement in statements.items()
    }
    not_refused = {
        name: (failure, sqlstate(failure))
        for name, failure in answered.items()
        if failure is None or sqlstate(failure) != INSUFFICIENT_PRIVILEGE
    }
    assert not not_refused, (
        f"On `pulse_app`, these direct statements on `{relation}` were not refused with "
        f"{INSUFFICIENT_PRIVILEGE}: {not_refused}. Criterion 3: the runtime role inserts only "
        "through the function and holds no `UPDATE` or `DELETE`."
    )


# ---------------------------------------------------------------------------
# What the function ends, what it leaves, and what it refuses.
# ---------------------------------------------------------------------------


def test_ending_a_section_instructor_grant_deletes_it_and_leaves_one_row_naming_it(
    application_session: Any, a_teaching_grant: dict[str, Any], committed_rows: Any
) -> None:
    """The permitting half, through `pulse_app`: the grant goes, and its record stays.

    One call, citing a successful roster call of the grant's own section. After
    it the assignment is gone, and exactly one `ended_teaching_grant` row names
    the assignment, the person, the section, `INSTRUCTOR`, the day handed in and
    the call — and it is still there with the assignment deleted, which is "the
    row survives the deletion".

    **The mutations this kills:** a function that deletes and records nothing, one
    that records and does not delete, one that records the wrong person, section,
    day or call, and a foreign key from the record to `role_assignment` that
    cascades the record away with the grant. **The near miss** is every refusal
    below: a function that refused everything passes all of them, and this is
    what it fails.
    """
    require_the_grant_ending_definer(committed_rows.session)
    require_the_ended_teaching_grant_table(committed_rows.session)
    require_the_application_role(application_session)

    failure = end_grant(
        application_session,
        assignment_id=a_teaching_grant["assignment"],
        nrps_call_id=a_teaching_grant["call"],
        ended_on=AN_ENDING_DAY,
    )
    assert failure is None, (
        f"Ending a section-scoped `INSTRUCTOR` grant, citing a successful call of its own section, "
        f"was refused on `pulse_app`: {failure} (SQLSTATE {sqlstate(failure)})."
    )
    assert not assignment_exists(committed_rows, a_teaching_grant["assignment"]), (
        "The call completed and the teaching grant is still in `role_assignment`; the read "
        "predicates assume an ended grant's row is gone."
    )
    named = [
        row
        for row in ended_teaching_grants(committed_rows.session)
        if row["assignment_id"] == a_teaching_grant["assignment"]
    ]
    assert (
        len(named) == 1
    ), f"The ended grant left {len(named)} rows in `{ENDED_TEACHING_GRANT_TABLE}`: {named}."
    expected = {
        "assignment_id": a_teaching_grant["assignment"],
        "person_id": a_teaching_grant["person"],
        "section_id": a_teaching_grant["section"],
        "role": INSTRUCTOR,
        "ended_on": AN_ENDING_DAY,
        "nrps_call_id": a_teaching_grant["call"],
    }
    differing = {
        column: (named[0].get(column), value)
        for column, value in expected.items()
        if named[0].get(column) != value
    }
    assert not differing, f"The ended row differs from the grant it records: {differing}."


@pytest.mark.parametrize("role", ["CARE", "LEAD_FACULTY"], ids=["care", "course-scoped-lead"])
def test_the_function_refuses_an_assignment_that_is_not_a_section_instructor(
    role: str,
    application_session: Any,
    a_teaching_grant: dict[str, Any],
    committed_rows: Any,
) -> None:
    """ "The function refuses any assignment that is not section-scoped `INSTRUCTOR`."

    `CARE` is the row E0-10's reveal definers check before they return a name, so
    a door that could delete one could also erase the Care office's access; a
    course-scoped lead is the ordinary leadership grant. Each is held by its own
    person, at the grain SPEC §2.1 gives the role, so the row is valid and only
    the function's rule can refuse it. The call cites a successful call of a real
    section, so nothing but the assignment's kind is wrong.

    **Refused, intact, unrecorded**: SQLSTATE 42501, the row still there, and no
    ended row naming it. **The pair** is the test above.

    **The mutation this kills:** a body that deletes by id whatever the role.
    """
    require_the_grant_ending_definer(committed_rows.session)
    require_the_ended_teaching_grant_table(committed_rows.session)
    graph = committed_rows.graph
    row = graph.assign(role, person=graph.person())
    committed_rows.commit()
    assignment = row[graph.assignment_key]

    failure = end_grant(
        application_session,
        assignment_id=assignment,
        nrps_call_id=a_teaching_grant["call"],
        ended_on=AN_ENDING_DAY,
    )
    assert failure is not None and sqlstate(failure) == INSUFFICIENT_PRIVILEGE, (
        f"Ending a `{role}` assignment through the teaching-grant door was answered {failure!r} "
        f"(SQLSTATE {sqlstate(failure)}), not refused with {INSUFFICIENT_PRIVILEGE}."
    )
    assert assignment_exists(
        committed_rows, assignment
    ), f"The `{role}` assignment is gone after a refused call."
    recorded = [
        ended
        for ended in ended_teaching_grants(committed_rows.session)
        if ended["assignment_id"] == assignment
    ]
    assert not recorded, f"A refused call left an ended row: {recorded}."


@pytest.mark.parametrize(
    "cited",
    ["another-sections-success", "own-section-failure", "own-section-no-answer", "no-such-call"],
)
def test_the_function_refuses_to_end_a_grant_citing_anything_but_a_successful_call_of_its_section(
    cited: str,
    application_session: Any,
    a_teaching_grant: dict[str, Any],
    committed_rows: Any,
) -> None:
    """A grant ends only on the word of a successful roster call of its own section.

    E5.1-02's work order (D1): a call that is missing, of another section, or
    whose response code is not 2xx, is refused with SQLSTATE 42501. A
    transport failure — `response_code` NULL, ADR 0129's "never reached the
    platform" — is not a success either, and is the case a body written as
    `IF NOT (code BETWEEN 200 AND 299)` lets through, because a comparison with
    NULL is neither true nor false.

    **The pair** is the permitting test above, which cites a 200 of the grant's
    own section on the same grant. **The mutations this kills:** a body that
    checks the call exists and nothing else; one that checks the code and not the
    section; and the NULL-blind comparison.
    """
    require_the_grant_ending_definer(committed_rows.session)
    require_the_ended_teaching_grant_table(committed_rows.session)
    call = {
        "another-sections-success": lambda: a_call(
            committed_rows, a_teaching_grant["other_section"], 200
        ),
        "own-section-failure": lambda: a_call(committed_rows, a_teaching_grant["section"], 500),
        "own-section-no-answer": lambda: a_call(committed_rows, a_teaching_grant["section"], None),
        "no-such-call": uuid4,
    }[cited]()

    failure = end_grant(
        application_session,
        assignment_id=a_teaching_grant["assignment"],
        nrps_call_id=call,
        ended_on=AN_ENDING_DAY,
    )
    assert failure is not None and sqlstate(failure) == INSUFFICIENT_PRIVILEGE, (
        f"Ending a teaching grant citing {cited.replace('-', ' ')} was answered {failure!r} "
        f"(SQLSTATE {sqlstate(failure)}), not refused with {INSUFFICIENT_PRIVILEGE}."
    )
    assert assignment_exists(
        committed_rows, a_teaching_grant["assignment"]
    ), f"The teaching grant is gone after a call citing {cited.replace('-', ' ')}."
    recorded = [
        ended
        for ended in ended_teaching_grants(committed_rows.session)
        if ended["assignment_id"] == a_teaching_grant["assignment"]
    ]
    assert not recorded, f"A refused call left an ended row: {recorded}."


def test_a_grant_that_is_already_gone_ends_quietly_and_writes_nothing(
    application_session: Any, a_teaching_grant: dict[str, Any], committed_rows: Any
) -> None:
    """Two syncs can race to end one grant; the second finds nothing and records nothing.

    E5.1-02's work order (D1): no row for the id is not an error ("another sync
    already ended it"). Asserted on the rows: after two calls for the same grant
    there is exactly one ended row, and a call naming an id nobody holds adds
    none.

    **The mutations this kills:** a body that raises when the row is missing —
    one sync's success becomes the next one's failure, every hour — and one that
    records an ending for a grant it did not delete.
    """
    require_the_grant_ending_definer(committed_rows.session)
    require_the_ended_teaching_grant_table(committed_rows.session)
    nobody_holds = uuid4()

    for _ in range(2):
        failure = end_grant(
            application_session,
            assignment_id=a_teaching_grant["assignment"],
            nrps_call_id=a_teaching_grant["call"],
            ended_on=AN_ENDING_DAY,
        )
        assert failure is None, f"Ending the same grant twice raised: {failure}."
    nobody = end_grant(
        application_session,
        assignment_id=nobody_holds,
        nrps_call_id=a_teaching_grant["call"],
        ended_on=AN_ENDING_DAY,
    )
    assert nobody is None, f"Ending a grant nobody holds raised: {nobody}."

    after = ended_teaching_grants(committed_rows.session)
    for_the_grant = [row for row in after if row["assignment_id"] == a_teaching_grant["assignment"]]
    for_nobody = [row for row in after if row["assignment_id"] == nobody_holds]
    assert len(for_the_grant) == 1, (
        f"Two calls for one grant left {len(for_the_grant)} ended rows for it: {for_the_grant}. "
        "Exactly one grant ended, once."
    )
    assert not for_nobody, f"A call naming an id nobody holds recorded an ending: {for_nobody}."


def test_a_grant_cannot_be_ended_without_its_row(
    application_session: Any, a_teaching_grant: dict[str, Any], committed_rows: Any
) -> None:
    """When the record cannot be written, the deletion does not happen either.

    The record is made unwritable the only way a test on `pulse_app` can make it
    so: a row already naming this assignment, planted on the superuser connection,
    which the record's `UNIQUE (assignment_id)` (work order D2) refuses a second
    of. The function's insert then fails, and because the deletion and the insert
    are one call, the deletion must be undone with it.

    **The mutations this kills:** the deletion committed before the insert (two
    transactions, or an `EXCEPTION` block that swallows the insert's failure and
    returns), which ends a grant with no record of who or why; and an insert
    written `ON CONFLICT DO NOTHING`, which does the same while answering success.

    **The pair** is the permitting test above, where nothing is planted and both
    halves happen.
    """
    require_the_grant_ending_definer(committed_rows.session)
    require_the_ended_teaching_grant_table(committed_rows.session)
    committed_rows.session.execute(
        text(
            f"INSERT INTO public.{ENDED_TEACHING_GRANT_TABLE} "  # noqa: S608 — module constant
            "(assignment_id, person_id, section_id, role, ended_on, nrps_call_id) VALUES "
            "(CAST(:assignment_id AS uuid), CAST(:person_id AS uuid), CAST(:section_id AS uuid), "
            "'INSTRUCTOR', CAST(:ended_on AS date), CAST(:nrps_call_id AS uuid))"
        ),
        {
            "assignment_id": a_teaching_grant["assignment"],
            "person_id": a_teaching_grant["person"],
            "section_id": a_teaching_grant["section"],
            "ended_on": AN_ENDING_DAY,
            "nrps_call_id": a_teaching_grant["call"],
        },
    )
    committed_rows.commit()

    failure = end_grant(
        application_session,
        assignment_id=a_teaching_grant["assignment"],
        nrps_call_id=a_teaching_grant["call"],
        ended_on=date(2026, 10, 3),
    )
    assert assignment_exists(committed_rows, a_teaching_grant["assignment"]), (
        f"The function's record could not be written (the call answered {failure!r}) and the grant "
        "was deleted anyway. Criterion 3: a grant cannot be ended without its row."
    )
    assert failure is not None, (
        "The record could not be written and the call answered success. A caller that reads "
        "success here believes a grant ended that did not."
    )


# ---------------------------------------------------------------------------
# The door itself: its owner, its shape, its reach, and who may open it.
# ---------------------------------------------------------------------------


def test_the_function_is_a_definer_owned_by_its_own_role_and_takes_no_role_argument(
    committed_rows: Any,
) -> None:
    """A sibling of `record_teaching_instructor`, built the way that one is.

    `SECURITY DEFINER`, owned by a NOLOGIN role that exists for this door and is
    not a superuser (ADR 0043: one role per door, so its reach is a list somebody
    can read), with `search_path` pinned so a caller cannot shadow a relation the
    body names (`docs/MISTAKES.md` entry 17). And its signature is `(uuid, uuid,
    date)`: no argument can carry a role, which is what keeps "it ends only a
    teaching grant" a property of the function rather than of its callers.

    **The mutations this kills:** `SECURITY INVOKER` (the call would then need
    `DELETE` on `role_assignment`, which `pulse_app` must not hold); the function
    owned by the migration superuser or by `pulse_instructor_definer`, which would
    widen an existing door's reach; no `search_path`; and a role parameter.
    """
    require_the_grant_ending_definer(committed_rows.session)
    found = (
        committed_rows.session.execute(text(THE_FUNCTION), {"name": END_TEACHING_INSTRUCTOR})
        .mappings()
        .all()
    )
    assert len(found) == 1, (
        f"`public` declares {len(found)} functions called `{END_TEACHING_INSTRUCTOR}`; an overload "
        "is a second way in."
    )
    function = found[0]
    assert function["security_definer"], f"`{END_TEACHING_INSTRUCTOR}` is not `SECURITY DEFINER`."
    assert function["owner"] == GRANT_END_DEFINER_ROLE, (
        f"`{END_TEACHING_INSTRUCTOR}` is owned by {function['owner']!r}, not "
        f"`{GRANT_END_DEFINER_ROLE}` (work order D1)."
    )
    assert not function["owner_is_superuser"] and not function["owner_can_log_in"], (
        f"The owner {function['owner']!r} is a superuser or can log in; a definer owner exists for "
        "nothing but the door."
    )
    assert any(setting.startswith("search_path=") for setting in function["settings"]), (
        f"`{END_TEACHING_INSTRUCTOR}` pins no `search_path` (its settings are "
        f"{list(function['settings'])})."
    )
    assert list(function["argument_types"]) == ["uuid", "uuid", "date"], (
        f"`{END_TEACHING_INSTRUCTOR}` takes {list(function['argument_types'])}; the work order "
        "settles `(assignment_id uuid, nrps_call_id uuid, ended_on date)`."
    )
    naming_a_role = [name for name in function["argument_names"] if "role" in name.lower()]
    assert not naming_a_role, f"A parameter names a role: {naming_a_role}."


def test_the_definer_owner_reaches_exactly_what_ending_a_grant_needs(
    committed_rows: Any,
) -> None:
    """The door's blast radius, as an equality, from the work order's own sentence.

    A `SECURITY DEFINER` function spends its owner's privileges, so the owner's
    grants are what `pulse_app` can be made to reach by calling it. D1: "`SELECT,
    DELETE ON public.role_assignment`; `SELECT (id, section_id, response_code) ON
    public.nrps_call`; `INSERT ON public.ended_teaching_grant`. Nothing else."

    **The control** is that the owner reaches `role_assignment` at all; an owner
    holding nothing satisfies "nothing beyond" perfectly.

    **The mutations this kills:** the owner gaining `UPDATE` or `DELETE` on the
    record (the append-only property, moved one door over), a read of `person` or
    `user_identity`, a whole-table `SELECT` on `nrps_call`, and reuse of
    `pulse_instructor_definer`, whose `INSERT` would then sit beside a `DELETE`.
    """
    require_the_grant_ending_definer(committed_rows.session)
    present = committed_rows.session.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": GRANT_END_DEFINER_ROLE}
    ).scalar_one_or_none()
    assert present is not None, f"There is no `{GRANT_END_DEFINER_ROLE}` role (work order D1)."

    whole = {
        (row[0], row[1])
        for row in committed_rows.session.execute(
            text(WHOLE_RELATION_PRIVILEGES), {"role": GRANT_END_DEFINER_ROLE}
        ).tuples()
    }
    assert ("role_assignment", "DELETE") in whole, (
        f"`{GRANT_END_DEFINER_ROLE}` holds no DELETE privilege on `role_assignment` ({sorted(whole)}), so the "
        "door it owns cannot end anything and the equality below would be about an empty owner."
    )
    assert whole == GRANT_END_DEFINER_WHOLE_RELATIONS, (
        f"`{GRANT_END_DEFINER_ROLE}` holds {sorted(whole)} on whole relations; the work order says "
        f"{sorted(GRANT_END_DEFINER_WHOLE_RELATIONS)}."
    )
    columns = {
        (row[0], row[1], row[2])
        for row in committed_rows.session.execute(
            text(COLUMN_GRANTS), {"role": GRANT_END_DEFINER_ROLE}
        ).tuples()
    }
    wholly_held = {relation for relation, _privilege in GRANT_END_DEFINER_WHOLE_RELATIONS}
    beyond = sorted(
        (relation, column, privilege)
        for relation, column, privilege in columns
        if relation not in wholly_held
        and not (
            relation == "nrps_call"
            and privilege == "SELECT"
            and column in GRANT_END_DEFINER_NRPS_CALL_COLUMNS
        )
    )
    assert (
        not beyond
    ), f"`{GRANT_END_DEFINER_ROLE}` holds column privileges beyond the work order's: {beyond}."
    on_calls = {column for relation, column, privilege in columns if relation == "nrps_call"}
    assert on_calls == GRANT_END_DEFINER_NRPS_CALL_COLUMNS, (
        f"`{GRANT_END_DEFINER_ROLE}` reads {sorted(on_calls)} of `nrps_call`; the work order says "
        f"{sorted(GRANT_END_DEFINER_NRPS_CALL_COLUMNS)}."
    )


def test_the_care_role_may_not_end_a_teaching_grant(
    committed_rows: Any, application_session: Any
) -> None:
    """The door is `pulse_app`'s alone: `pulse_care` is refused it, with the control beside it.

    Postgres grants `EXECUTE` on a new function to `PUBLIC` unless the migration
    revokes it, and `PUBLIC` includes the Care role — whose own live `CARE`
    assignment is what the reveal checks. A door that deletes `role_assignment`
    rows on Care's connection is a door Care should never hold.

    Asserted as a refused call with SQLSTATE 42501, every argument a typed NULL so
    "function does not exist" (42883) cannot stand in for the refusal. **The
    control:** the same call on `pulse_app` is not refused for privilege.

    **The mutation this kills:** the migration's `REVOKE ALL … FROM PUBLIC` left
    out.
    """
    require_the_grant_ending_definer(committed_rows.session)
    nulls = {"assignment_id": None, "nrps_call_id": None, "ended_on": None}

    allowed = attempted(application_session, END_TEACHING_INSTRUCTOR_CALL, nulls)
    assert allowed is None or sqlstate(allowed) != INSUFFICIENT_PRIVILEGE, (
        f"`{APPLICATION_ROLE}` was refused `EXECUTE` on the ending definer ({allowed}), so the Care "
        "refusal below would be satisfied by a door nobody may open."
    )

    session = committed_rows.session
    session.rollback()
    session.execute(text(f'SET ROLE "{CARE_ROLE}"'))
    try:
        assert (
            session.execute(text(CURRENT_ROLE)).scalar_one() == CARE_ROLE
        ), f"`SET ROLE {CARE_ROLE}` did not switch the session, so this would measure the superuser."
        refused = attempted(session, END_TEACHING_INSTRUCTOR_CALL, nulls)
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
    assert refused is not None and sqlstate(refused) == INSUFFICIENT_PRIVILEGE, (
        f"`{CARE_ROLE}` called the teaching-grant ending definer and was answered {refused!r} "
        f"(SQLSTATE {sqlstate(refused)}). `REVOKE ALL ON FUNCTION … FROM PUBLIC` is the line whose "
        "absence produces this."
    )
