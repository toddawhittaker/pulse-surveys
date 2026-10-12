"""The people-graph definers write and read for an admin and nobody else — E9-02 done-whens 1 and 9.

> 1. **Only an admin writes.** Each write definer, called with a person key that
>    holds no live `ADMIN` assignment, writes nothing and raises a named
>    refusal; called by an admin, it writes. Tested for every definer with a
>    dean, a Care holder and a person with no assignment as the refused
>    callers, beside the admin as the passing twin. Reached through the
>    connection production uses (MISTAKES entry 46).
>
> 9. **The admin's reads answer no student data.** The read definers' result
>    columns are compared against an allow-list: no `user` key, no
>    `lms_user_id`, no email and no `user_identity` column. A non-admin caller
>    gets nothing.

Names, signatures, the refusal shape (`P0001`, the copy key as the message) and
the reads' exact columns are the settled interface, transcribed once in
`tests/fixtures/people_graph.py`. A null key is a fourth refused caller: the
settled admin check is "`EXISTS (… person_id = in_actor_person_id AND role =
'ADMIN')`. A NULL key fails it."

**What the database check is worth** (the ticket's own paragraph): `pulse_app`
passes the acting admin's key and the database cannot tell whether it is the
session's own. These tests assert that a non-admin key is refused, never that
the database knows who is acting; the route is E9-06's done-when 13.

Also here: the owner's privileges, as the ceiling the settled interface gives
(`test_identity_grants.py` names this test as where they are pinned).

**Which failure a red is, before E9-02 lands.** Every call reaches a function
that does not exist, SQLSTATE 42883, and fails the assertion on the named
refusal or on the admin's call succeeding — a FAILED. The owner test fails on
the role not existing. The world control is green today.
"""

from typing import Any

import pytest
from fixtures.people_graph import (
    ACTOR_NOT_AN_ADMIN,
    APPLICATION_ROLE,
    NAMED_REFUSAL,
    OWNER_ROLE,
    READS,
    WRITES,
    PeopleGraphWorld,
    token,
)
from sqlalchemy import text

pytestmark = pytest.mark.integration

DEAN = "a dean"
CARE = "a Care holder"
NOBODY = "a person with no assignment"
NULL_KEY = "a null key"
REFUSED_CALLERS = (DEAN, CARE, NOBODY, NULL_KEY)


def caller(world: PeopleGraphWorld, who: str) -> Any:
    return {DEAN: world.dean, CARE: world.care, NOBODY: world.nobody, NULL_KEY: None}[who]


# ---------------------------------------------------------------------------
# Control on the world. A red here means the world is broken, not the definers.
# ---------------------------------------------------------------------------


def test_the_world_holds_one_admin_and_three_non_admins(people_graph: PeopleGraphWorld) -> None:
    """CONTROL — green today. Each caller holds exactly the role this module says.

    A "refused dean" who held `ADMIN` too, or an "admin" who held nothing, would
    make every pair below measure the wrong thing (`docs/MISTAKES.md` entry 30:
    the fixture supplying the value under test).
    """
    world = people_graph
    held = {
        "the admin": [token(row["role"]) for row in world.assignments_of(world.admin)],
        DEAN: [token(row["role"]) for row in world.assignments_of(world.dean)],
        CARE: [token(row["role"]) for row in world.assignments_of(world.care)],
        NOBODY: [token(row["role"]) for row in world.assignments_of(world.nobody)],
    }
    assert held == {
        "the admin": ["ADMIN"],
        DEAN: ["DEAN"],
        CARE: ["CARE"],
        NOBODY: [],
    }, f"The callers hold {held}."


# ---------------------------------------------------------------------------
# Done-when 1.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("who", REFUSED_CALLERS)
@pytest.mark.parametrize("function", list(WRITES))
def test_a_write_definer_refuses_a_key_with_no_live_admin_assignment_and_writes_for_an_admin(
    people_graph: PeopleGraphWorld, function: str, who: str
) -> None:
    """Done-when 1, one write and one refused caller per case, with the admin's call beside it.

    The refused call must raise `P0001` with `admin_people.actor_not_an_admin`,
    leave the effect unread-changed on a second connection, and leave no audit
    row naming the caller. Then the admin's call on the same target must succeed
    and change the effect.

    **The mutations it kills:** a write with no admin check; an admin check that
    admits any leadership holder (the dean), any web-door role (the Care holder),
    or any person row at all (the person with no assignment); a check written as
    `NOT EXISTS (… role <> 'ADMIN')`, which admits a person with no assignment;
    a null key compared with `=` in a way that lets it through; the check made
    after the write, with the refusal raised but the row left; the refusal
    raised as some other code or key; `pulse_app` lacking `EXECUTE` (42501,
    which no assertion here accepts). **The near miss it spares:** the admin, on
    the same target in the same world, whose call writes — so a definer that
    refuses everyone is red here too.
    """
    world = people_graph
    prepared = world.prepare(function)
    actor = caller(world, who)
    before = prepared.observe()

    refused = world.call(function, actor, **prepared.params)

    assert (refused.sqlstate, refused.message) == (NAMED_REFUSAL, ACTOR_NOT_AN_ADMIN), (
        f"`{function}` called by {who} {refused.describe()}. Done-when 1: a key holding no live "
        f"`ADMIN` assignment is refused with the named refusal `{ACTOR_NOT_AN_ADMIN}` "
        f"(SQLSTATE {NAMED_REFUSAL})."
    )
    assert prepared.observe() == before, (
        f"`{function}` refused {who} and its effect moved from {before!r} to "
        f"{prepared.observe()!r}. A refusal that writes is the defect with a better message."
    )
    assert (
        world.audit_rows(actor) == []
    ), f"`{function}` refused {who} and left audit rows naming them: {world.audit_rows(actor)}."

    admitted = world.call(function, world.admin, **prepared.params)
    assert admitted.failure is None, (
        f"`{function}` called by the admin, on the target {who} was refused, "
        f"{admitted.describe()}. Without the admin's write the refusal above proves nothing."
    )
    assert (
        prepared.observe() != before
    ), f"`{function}` answered the admin {admitted.value!r} and its effect is still {before!r}."


# ---------------------------------------------------------------------------
# Done-when 9.
# ---------------------------------------------------------------------------


# Named outright by done-when 9 or the settled interface, whatever table holds them.
EXPLICITLY_FORBIDDEN = frozenset({"user_id", "lms_user_id", "idp_subject"})


def columns_only_user_identity_carries(metadata_tables: dict[str, Any]) -> set[str]:
    """`user_identity`'s column names that no `person` column shares.

    Narrowed by the ruling on `docs/disputes/E9-02-01.md`: a name is compared,
    not a source, and ADR 0022 gives `person.identity_name` (a staff member's own
    name, which the people read is settled to return) the same spelling as
    `user_identity.identity_name` (a student's). So only a name `person` does not
    also carry can say a column came from `user_identity`. The set is required
    non-empty, so the check below is never asked of nothing.
    """
    identity = metadata_tables.get("user_identity")
    person = metadata_tables.get("person")
    assert (
        identity is not None and person is not None
    ), "The model declares no `user_identity` or no `person`; the sweep would read nothing."
    only = {column.name for column in identity.columns} - {column.name for column in person.columns}
    assert only, (
        "Every `user_identity` column name is also a `person` column name, so the narrowed "
        "forbidden set is empty and the check below would read nothing."
    )
    return only


@pytest.mark.parametrize("function", list(READS))
def test_a_read_definer_answers_the_admin_exactly_its_allow_listed_columns(
    people_graph: PeopleGraphWorld, metadata_tables: dict[str, Any], function: str
) -> None:
    """Done-when 9's allow-list, asked of the admin, with the rows required non-empty.

    The columns must equal the settled list exactly, and none may be a
    `user_identity` column, a `user` key, `lms_user_id`, `idp_subject` or
    anything naming an email. **Non-empty first** (`docs/MISTAKES.md` entry 3):
    each read must answer a row this world certainly planted — the admin's own
    person, the admin's own assignment, a mapping planted here — or "no
    forbidden column" is a statement about an answer that could be empty for
    any reason.

    **The mutations it kills:** `RETURNS SETOF person` or a `SELECT *`, which
    hands `person.user_id` (one step from a student's LMS key) to the
    connection every screen uses; `idp_subject` added to the people read; an
    email joined in from `user_identity`. **The near miss:** `idp_issuer`, which
    is allowed (it says a web login exists, not whose).
    """
    world = people_graph
    course = world.a_course()
    world.a_mapping(person=world.admin, course=course)
    planted = {
        "admin_read_people": ("person_id", world.admin),
        "admin_read_role_assignments": ("person_id", world.admin),
        "admin_read_lead_mappings": ("course_id", course),
    }

    keys, rows, failure = world.read(function, world.admin)

    assert failure is None, f"`{function}` called by the admin raised {failure!r}."
    column, key = planted[function]
    assert any(str(row.get(column)) == str(key) for row in rows), (
        f"`{function}` answered the admin {len(rows)} rows and none has `{column}` = {key}, a row "
        "this world planted. The column checks below would be about an answer that proves nothing."
    )
    assert (
        tuple(keys) == READS[function]
    ), f"`{function}` answers the columns {keys}; the settled allow-list is {list(READS[function])}."
    explicit = sorted(
        name for name in keys if name in EXPLICITLY_FORBIDDEN or "email" in name.lower()
    )
    assert not explicit, (
        f"`{function}` answers {explicit}. Done-when 9 forbids a `user` key, `lms_user_id` and "
        "any email, and the settled interface keeps `idp_subject` off the reads."
    )
    from_identity = sorted(set(keys) & columns_only_user_identity_carries(metadata_tables))
    assert not from_identity, (
        f"`{function}` answers {from_identity}, which only `user_identity` carries. Done-when 9 "
        "forbids any `user_identity` column."
    )


@pytest.mark.parametrize("who", REFUSED_CALLERS)
@pytest.mark.parametrize("function", list(READS))
def test_a_read_definer_answers_a_non_admin_nothing(
    people_graph: PeopleGraphWorld, function: str, who: str
) -> None:
    """Done-when 9's "A non-admin caller gets nothing": zero rows, not an error (settled).

    **The mutations it kills:** a read with no admin check, which answers every
    staff name to any key `pulse_app` passes; a check admitting leadership or
    Care. **The near miss:** the admin's answer to the same read in the same
    world, required non-empty here so that "nothing" is not what everybody gets.
    The world plants people and assignments but no mapping, so one is planted
    here, as the allow-list test above does (the ruling on
    `docs/disputes/E9-02-02.md`).
    """
    world = people_graph
    world.a_mapping(person=world.admin, course=world.a_course())

    _keys, rows, failure = world.read(function, caller(world, who))
    _admin_keys, admin_rows, admin_failure = world.read(function, world.admin)

    assert failure is None, (
        f"`{function}` called by {who} raised {failure!r}. Settled: a non-admin gets zero rows, "
        "not an error."
    )
    assert rows == [], f"`{function}` answered {who} {len(rows)} rows: {rows[:3]}."
    assert admin_failure is None and admin_rows, (
        f"`{function}` answered the admin {len(admin_rows)} rows ({admin_failure!r}), so the "
        f"empty answer to {who} is what everybody gets."
    )


# ---------------------------------------------------------------------------
# The owner.
# ---------------------------------------------------------------------------

# The settled privileges (interface §2), as (relation, column or None, privilege).
# `None` is a table-level privilege.
OWNER_HOLDS = (
    ("person", "id", "SELECT"),
    ("person", "identity_name", "SELECT"),
    ("person", "category", "SELECT"),
    ("person", "identity_name", "INSERT"),
    ("person", "category", "INSERT"),
    ("person", "identity_name", "UPDATE"),
    ("person", "category", "UPDATE"),
    ("role_assignment", None, "SELECT"),
    ("role_assignment", "person_id", "INSERT"),
    ("role_assignment", "role", "INSERT"),
    ("role_assignment", "institution_id", "INSERT"),
    ("role_assignment", "section_id", "INSERT"),
    ("role_assignment", "reports_to", "UPDATE"),
    ("role_assignment", None, "DELETE"),
    ("lead_faculty_mapping", None, "SELECT"),
    ("lead_faculty_mapping", "person_id", "INSERT"),
    ("lead_faculty_mapping", None, "DELETE"),
    ("web_login_subject", None, "SELECT"),
    ("web_login_subject", "idp_subject", "INSERT"),
    ("web_login_subject", None, "DELETE"),
    ("audit_log", "action", "INSERT"),
    ("audit_log", "subject_person_id", "INSERT"),
    ("audit_log", "scope_node_id", "INSERT"),
    # E9-06's fix round: `admin_record_import`, owned by this role, writes the
    # import's diff into `audit_log.detail` (SPEC §8, "imports (with their dry-run
    # diffs)"), so its owner must be able to insert that column.
    ("audit_log", "detail", "INSERT"),
)

# What it must not hold. Each is a widening a body does not need.
OWNER_MUST_NOT_HOLD = (
    ("person", "user_id", "SELECT"),
    ("person", "user_id", "UPDATE"),
    ("person", None, "DELETE"),
    ("role_assignment", "person_id", "UPDATE"),
    ("role_assignment", "role", "UPDATE"),
    ("role_assignment", "institution_id", "UPDATE"),
    ("lead_faculty_mapping", "person_id", "UPDATE"),
    ("web_login_subject", "idp_subject", "UPDATE"),
    ("audit_log", "action", "SELECT"),
    ("audit_log", None, "UPDATE"),
    ("audit_log", None, "DELETE"),
    ("user", "lms_user_id", "SELECT"),
)

HAS_TABLE = "SELECT has_table_privilege(:role, :relation, :privilege)"
HAS_COLUMN = "SELECT has_column_privilege(:role, :relation, :column, :privilege)"
HAS_ANY_COLUMN = "SELECT has_any_column_privilege(:role, :relation, :privilege)"
ROLE_ROW = "SELECT rolcanlogin, rolsuper FROM pg_roles WHERE rolname = :role"


def holds(session: Any, relation: str, column: str | None, privilege: str) -> bool:
    qualified = f'public."{relation}"'
    if column is None:
        return bool(
            session.execute(
                text(HAS_TABLE), {"role": OWNER_ROLE, "relation": qualified, "privilege": privilege}
            ).scalar_one()
        )
    return bool(
        session.execute(
            text(HAS_COLUMN),
            {"role": OWNER_ROLE, "relation": qualified, "column": column, "privilege": privilege},
        ).scalar_one()
    )


def test_the_people_graph_definers_owner_holds_exactly_what_its_writes_need(
    db_session: Any,
) -> None:
    """The settled owner, `pulse_people_graph_definer`: NOLOGIN, its listed privileges, nothing on identity.

    **The positive half is the control** (`docs/MISTAKES.md` entry 35): each
    settled privilege is required to be *found*, so the negative half is not
    satisfied by a role that holds nothing or a probe that sees nothing.

    **The mutations it kills:** the functions owned by the migration identity or
    a superuser (every grant check passes); an owner granted `ALL` on `person`,
    which reads `user_id`; `UPDATE` on `role_assignment.role`, which lets a
    body turn any assignment into `ADMIN`; `SELECT` on `audit_log`, which the
    settled interface withholds; any privilege on `user_identity`.
    """
    role = db_session.execute(text(ROLE_ROW), {"role": OWNER_ROLE}).mappings().one_or_none()
    assert role is not None, (
        f"There is no `{OWNER_ROLE}` role. Settled: one NOLOGIN owner of all twelve people-graph "
        "definers and of E9-06's `admin_record_import`."
    )
    has_detail = db_session.execute(
        text(
            "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'audit_log' AND column_name = 'detail'"
        )
    ).scalar_one()
    assert has_detail == 1, (
        "`audit_log` has no `detail` column. E9-06's fix round adds it (nullable `jsonb`, "
        "non-null exactly for `IMPORT_APPLIED`), and the owner's `INSERT` on it is checked below."
    )
    assert (role["rolcanlogin"], role["rolsuper"]) == (False, False), (
        f"`{OWNER_ROLE}` has login {role['rolcanlogin']} and superuser {role['rolsuper']}; it is a "
        "NOLOGIN, non-superuser owner."
    )

    missing = [entry for entry in OWNER_HOLDS if not holds(db_session, *entry)]
    assert not missing, f"`{OWNER_ROLE}` lacks {missing}, which its bodies need."

    beyond = [entry for entry in OWNER_MUST_NOT_HOLD if holds(db_session, *entry)]
    assert not beyond, f"`{OWNER_ROLE}` holds {beyond}, which no body needs."

    on_identity = [
        privilege
        for privilege in ("SELECT", "INSERT", "UPDATE", "REFERENCES")
        if db_session.execute(
            text(HAS_ANY_COLUMN),
            {"role": OWNER_ROLE, "relation": 'public."user_identity"', "privilege": privilege},
        ).scalar_one()
    ] + [
        privilege
        for privilege in ("DELETE", "TRUNCATE", "TRIGGER")
        if holds(db_session, "user_identity", None, privilege)
    ]
    assert not on_identity, f"`{OWNER_ROLE}` holds {on_identity} on `user_identity`."


def test_the_application_role_may_execute_every_people_graph_definer(db_session: Any) -> None:
    """`pulse_app` holds `EXECUTE` on all twelve, the other half of done-when 2's wall.

    **The mutation it kills:** a function left without its `GRANT EXECUTE … TO
    pulse_app`; every call above then answers 42501 and the editor writes
    nothing. (`test_identity_grants.py`'s equality inventory is the ceiling;
    this is the floor named by function.)
    """
    functions = [*WRITES, *READS]
    found = (
        db_session.execute(
            text(
                "SELECT p.proname, has_function_privilege(:role, p.oid, 'EXECUTE') AS may "
                "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'public' AND p.proname = ANY(:names)"
            ),
            {"role": APPLICATION_ROLE, "names": functions},
        )
        .mappings()
        .all()
    )
    may = {row["proname"]: row["may"] for row in found}
    absent = sorted(name for name in functions if name not in may)
    refused = sorted(name for name, allowed in may.items() if not allowed)
    assert not absent, f"These people-graph definers do not exist: {absent}."
    assert not refused, f"`{APPLICATION_ROLE}` may not execute {refused}."
