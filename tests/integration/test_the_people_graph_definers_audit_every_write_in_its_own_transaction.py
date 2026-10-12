"""Every people-graph write leaves one audit row, in its own transaction — E9-02 done-when 5.

> 5. **Every write is audited, in the same transaction.** Each grant, revoke,
>    edge change, mapping change and linkage change leaves exactly one
>    `audit_log` row naming the action, the acting admin's person, the person
>    written about and, for an assignment, its role and scope node. A Care
>    grant's row carries the `CARE` role. When the audit insert is made to
>    fail, the write is not committed (planted failure, row count unchanged).

Ruling 1 makes this row the control: the editor may grant Care and Admin to
anyone, so the audit row is what E10's access log shows the outside review. What
each action writes is the settled table (interface §4), transcribed into each
test's expectation.

**The planted failure, and why a handler cannot satisfy it.** A committed
`BEFORE INSERT` trigger on `audit_log`, created by the bootstrap identity, raises
SQLSTATE `E9002` with a unique message for rows naming this world's admin and
nobody else (`PeopleGraphWorld.audit_insert_fails_for`). The test requires the
call to fail **with that exact code and message**, the write's effect to be
unchanged on a second connection, and no audit row to exist. So:

  - a definer that wraps the audit insert in `EXCEPTION WHEN OTHERS THEN NULL`
    (or any handler that swallows) answers success: red on "the call failed";
  - one whose handler re-raises as a named refusal (`P0001`) or as anything
    else: red on the SQLSTATE and message;
  - one that writes the audit row in a separate transaction (`dblink`, a
    deferred job): red on the effect, which committed.

Then the trigger is dropped and the same call is made again, and it must
succeed: the failure was the planted one, not something about the call.
`test_the_planted_trigger_fails_an_audit_insert_naming_the_admin_and_no_other`
is the instrument's control, green today.

**Which failure a red is, before E9-02 lands.** Every definer call answers 42883
(no such function), which fails each test's success or SQLSTATE assertion — a
FAILED. The instrument control is green today.
"""

from typing import Any

import pytest
from fixtures.people_graph import (
    AUDITED_WRITES,
    LEAD_MAPPING_CHANGED,
    REPORTS_TO_SET,
    ROLE_GRANTED,
    ROLE_REVOKED,
    WEB_LOGIN_LINKAGE_CHANGED,
    PeopleGraphWorld,
    token,
)
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration


def as_row(row: dict[str, Any]) -> dict[str, Any]:
    """An audit row with every value comparable as text or token."""
    return {
        "action": token(row["action"]),
        "actor_person_id": None if row["actor_person_id"] is None else str(row["actor_person_id"]),
        "subject_person_id": (
            None if row["subject_person_id"] is None else str(row["subject_person_id"])
        ),
        "subject_user_id": row["subject_user_id"],
        "case_id": row["case_id"],
        "role": token(row["role"]),
        "scope_node_id": None if row["scope_node_id"] is None else str(row["scope_node_id"]),
        "parent_assignment_id": (
            None if row["parent_assignment_id"] is None else str(row["parent_assignment_id"])
        ),
    }


def expected_row(
    action: str, actor: Any, subject: Any, role: str | None, scope: Any, parent: Any = None
) -> dict[str, Any]:
    """The settled row (interface §4, with fix round 1's F2): `parent` is a `REPORTS_TO_SET`'s alone."""
    return {
        "action": action,
        "actor_person_id": str(actor),
        "subject_person_id": str(subject),
        "subject_user_id": None,
        "case_id": None,
        "role": role,
        "scope_node_id": None if scope is None else str(scope),
        "parent_assignment_id": None if parent is None else str(parent),
    }


def the_one_new_row(
    world: PeopleGraphWorld, before: list[dict[str, Any]], what: str
) -> dict[str, Any]:
    after = world.audit_rows(world.admin)
    new = after[len(before) :]
    assert len(after) == len(before) + 1 and after[: len(before)] == before, (
        f"{what} left the admin's audit rows {[as_row(r) for r in after]}, where they were "
        f"{[as_row(r) for r in before]}. Done-when 5: exactly one row per write."
    )
    return as_row(new[0])


# ---------------------------------------------------------------------------
# The row each action writes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["CARE", "ADMIN", "DEAN"])
def test_a_grant_leaves_one_row_naming_the_admin_the_grantee_the_role_and_the_scope(
    people_graph: PeopleGraphWorld, role: str
) -> None:
    """`ROLE_GRANTED`: the grantee, the role granted, the scope node granted at. A Care grant carries `CARE`.

    **The mutations it kills:** a grant with no audit insert; the row naming
    the grantee as the actor (or the actor as the subject); the role left null,
    which hides a Care grant from E10's log; the scope left null; a second row
    per grant. **The near miss:** the `DEAN` and `ADMIN` grants, whose rows
    carry their own roles — so "the row says CARE" is not a constant.
    """
    world = people_graph
    target = world.a_person()
    scope = world.scope(role)
    before = world.audit_rows(world.admin)

    granted = world.call("admin_grant_role", world.admin, person=target, role=role, scope=scope)

    assert granted.failure is None, f"Granting `{role}` {granted.describe()}."
    row = the_one_new_row(world, before, f"Granting `{role}`")
    assert row == expected_row(
        ROLE_GRANTED, world.admin, target, role, scope
    ), f"The grant's audit row is {row}."


def test_a_revoke_leaves_one_row_naming_the_deleted_rows_person_role_and_scope(
    people_graph: PeopleGraphWorld,
) -> None:
    """`ROLE_REVOKED`: everything about the row that is gone, read from the row itself.

    **The mutations it kills:** the row's subject, role or scope left null
    because the assignment no longer exists to read them from; the actor
    written as the subject.
    """
    world = people_graph
    holder = world.a_person()
    assignment = world.assignment("CARE", person=holder)
    row_before = world.assignment_row(assignment)
    assert row_before is not None
    scope = world.scope_node_of(row_before)
    before = world.audit_rows(world.admin)

    revoked = world.call("admin_revoke_role", world.admin, assignment=assignment)

    assert revoked.failure is None, f"Revoking {revoked.describe()}."
    row = the_one_new_row(world, before, "Revoking a `CARE` row")
    assert row == expected_row(
        ROLE_REVOKED, world.admin, holder, "CARE", scope
    ), f"The revoke's audit row is {row}."


@pytest.mark.parametrize("change", ["set", "clear"])
def test_an_edge_change_leaves_one_row_naming_the_childs_person_role_and_scope(
    people_graph: PeopleGraphWorld, change: str
) -> None:
    """`REPORTS_TO_SET`, for a set and for a clear: the child's person, role and scope, and the new parent.

    Fix round 1, F2: the row names the new parent in `parent_assignment_id`, or
    NULL when the edge is cleared.

    **The mutations it kills:** the parent's person written as the subject; a
    clear left unaudited (an edge removed with no record); the row's role or
    scope left null; the new parent left off a set (F2), or the old parent
    written on a clear.
    """
    world = people_graph
    child_person = world.a_person()
    dean = world.assignment("DEAN")
    child = world.assignment(
        "CHAIR", person=child_person, reports_to=dean if change == "clear" else None
    )
    child_row = world.assignment_row(child)
    assert child_row is not None
    scope = world.scope_node_of(child_row)
    before = world.audit_rows(world.admin)

    changed = world.call(
        "admin_set_reports_to",
        world.admin,
        assignment=child,
        reports_to=dean if change == "set" else None,
    )

    assert changed.failure is None, f"The edge {change} {changed.describe()}."
    row = the_one_new_row(world, before, f"The edge {change}")
    assert row == expected_row(
        REPORTS_TO_SET,
        world.admin,
        child_person,
        "CHAIR",
        scope,
        parent=dean if change == "set" else None,
    ), f"The edge {change}'s audit row is {row}."


@pytest.mark.parametrize("change", ["map", "unmap"])
def test_a_mapping_change_leaves_one_row_naming_the_lead_and_the_course(
    people_graph: PeopleGraphWorld, change: str
) -> None:
    """`LEAD_MAPPING_CHANGED`, for a map and an unmap: the lead, `LEAD_FACULTY`, the course.

    **The mutations it kills:** an unmap left unaudited; the course left out of
    the row (it is the scope node); the role left null.
    """
    world = people_graph
    lead = world.a_person()
    # E9-14 item 2: a course is mapped only to a Lead Faculty holder. Seeded
    # directly, so it writes no audit row of its own.
    world.assignment("LEAD_FACULTY", person=lead)
    course = world.a_course()
    if change == "unmap":
        world.a_mapping(person=lead, course=course)
    before = world.audit_rows(world.admin)

    if change == "map":
        called = world.call("admin_map_lead_course", world.admin, person=lead, course=course)
    else:
        called = world.call("admin_unmap_lead_course", world.admin, course=course)

    assert called.failure is None, f"The {change} {called.describe()}."
    row = the_one_new_row(world, before, f"The {change}")
    assert row == expected_row(
        LEAD_MAPPING_CHANGED, world.admin, lead, "LEAD_FACULTY", course
    ), f"The {change}'s audit row is {row}."


# Fix round 1, F1: the linkage row's role is the privilege the linked person
# holds at the time of the write — `CARE` if they hold it, else `ADMIN` if they
# hold it, else NULL. (holds, expected role on the row.)
LINKAGE_HOLDERS = {
    "a Care holder": (("CARE",), "CARE"),
    "an Admin holder": (("ADMIN",), "ADMIN"),
    "a holder of both": (("CARE", "ADMIN"), "CARE"),
    "a person holding neither": (("DEAN",), None),
}


@pytest.mark.parametrize("holder", list(LINKAGE_HOLDERS))
@pytest.mark.parametrize("change", ["link", "unlink"])
def test_a_linkage_change_leaves_one_row_naming_the_person_and_the_privilege_they_hold(
    people_graph: PeopleGraphWorld, change: str, holder: str
) -> None:
    """`WEB_LOGIN_LINKAGE_CHANGED`: the person, the Care or Admin role they hold (F1), no scope.

    Fix round 1, F1: linking an admin's own login to a Care holder is a Care
    grant by another road, so the row carries `CARE` when the person holds it,
    `ADMIN` when they hold that and not Care, and NULL otherwise; `CARE` wins
    for a holder of both. "Neither" is a dean, so a role is present and the NULL
    is a decision, not an absence of rows to read.

    **The mutations it kills:** a linkage change unaudited; the subject written
    as the actor; the role left NULL for a Care holder (F1's finding: the trail
    shows no Care grant); `ADMIN` preferred over `CARE` for a holder of both;
    any held role written (the dean's `DEAN` on the row); the role read from the
    actor rather than the linked person; a scope node written.
    """
    world = people_graph
    holds, role = LINKAGE_HOLDERS[holder]
    person = world.a_person()
    for held in holds:
        world.assignment(held, person=person)
    if change == "unlink":
        world.a_linkage(person=person)
    before = world.audit_rows(world.admin)

    if change == "link":
        called = world.call(
            "admin_link_web_login",
            world.admin,
            person=person,
            issuer="https://e9-02-issuer.invalid",
            subject=f"e9-02-audited-{person}",
        )
    else:
        called = world.call("admin_unlink_web_login", world.admin, person=person)

    assert called.failure is None, f"The {change} {called.describe()}."
    row = the_one_new_row(world, before, f"The {change}")
    assert row == expected_row(
        WEB_LOGIN_LINKAGE_CHANGED, world.admin, person, role, None
    ), f"The {change} for {holder}'s audit row is {row}."


def test_creating_and_editing_a_person_leave_no_audit_row(people_graph: PeopleGraphWorld) -> None:
    """Settled: done-when 5 lists five actions, and person writes are not among them.

    **The mutation it kills:** a person write audited under one of the five
    actions, which E10's log would read as a grant or a linkage. **The near
    miss:** the five audited writes above, each one row.
    """
    world = people_graph
    created = world.call(
        "admin_create_person", world.admin, identity_name="E9-02 Unaudited", category=world.category
    )
    assert created.failure is None, f"Creating a person {created.describe()}."
    edited = world.call(
        "admin_edit_person",
        world.admin,
        person=created.value,
        identity_name="E9-02 Unaudited Edited",
        category=world.category,
    )
    assert edited.failure is None, f"Editing a person {edited.describe()}."
    assert (
        world.audit_rows(world.admin) == []
    ), f"Person writes left audit rows: {[as_row(r) for r in world.audit_rows(world.admin)]}."


# ---------------------------------------------------------------------------
# The planted failure.
# ---------------------------------------------------------------------------


def test_the_planted_trigger_fails_an_audit_insert_naming_the_admin_and_no_other(
    people_graph: PeopleGraphWorld,
) -> None:
    """CONTROL — green today. The instrument fires on the admin's rows, only theirs, and goes away.

    A direct insert by the bootstrap identity of a reveal-shaped row naming the
    admin must fail with the planted code; the same row naming another actor
    must not; and after the block, the admin's row must insert. A red here means
    the planted-failure tests below measure nothing.
    """
    world = people_graph
    tables = world.rows.tables
    audit = tables["audit_log"]
    user = world.rows.seed("user")
    world.rows.commit()
    user_key = user[next(iter(tables["user"].primary_key.columns)).name]

    import importlib

    reveal = importlib.import_module("app.models.audit").AuditAction.IDENTITY_REVEAL

    def attempt(actor: Any) -> Any:
        session = world.rows.session
        savepoint = session.begin_nested()
        try:
            session.execute(
                audit.insert().values(
                    action=reveal, actor_person_id=actor, subject_user_id=user_key, case_id=None
                )
            )
        except DatabaseError as failure:
            savepoint.rollback()
            return failure
        savepoint.rollback()
        return None

    with world.audit_insert_fails_for(world.admin) as (sqlstate, message):
        planted = attempt(world.admin)
        other = attempt(world.dean)
        world.rows.session.rollback()
    after = attempt(world.admin)
    world.rows.session.rollback()

    assert planted is not None, "The planted trigger let the admin's audit row through."
    assert getattr(planted.orig, "sqlstate", None) == sqlstate, f"It raised {planted.orig!r}."
    assert message in str(planted.orig), f"It raised {planted.orig!r}, not the planted message."
    assert other is None, f"The planted trigger refused another actor's row: {other!r}."
    assert (
        after is None
    ), f"The admin's row is still refused after the trigger was dropped: {after!r}."


@pytest.mark.parametrize("function", AUDITED_WRITES)
def test_a_write_whose_audit_insert_fails_is_not_committed(
    people_graph: PeopleGraphWorld, function: str
) -> None:
    """Done-when 5's planted failure, for every audited write, then the same call without it.

    **The mutations it kills:** the audit insert wrapped in a handler that
    swallows (the call succeeds); a handler that re-raises as a named refusal
    or as anything else (the SQLSTATE or message differs); the audit row
    written outside the write's transaction, or the write committed before
    the audit insert (the effect moved); the audit insert made only on some
    paths. **The near miss:** the same call, after the trigger is dropped,
    succeeds and writes — so the failure was the planted one.
    """
    world = people_graph
    prepared = world.prepare(function)
    before = prepared.observe()

    with world.audit_insert_fails_for(world.admin) as (sqlstate, message):
        failed = world.call(function, world.admin, **prepared.params)

    assert failed.failure is not None, (
        f"`{function}` succeeded while its audit insert was made to fail ({failed.describe()}). "
        "A handler around the insert swallowed it, and the write is now unaudited — the one "
        "thing ruling 1 makes the control."
    )
    assert (failed.sqlstate, failed.message) == (sqlstate, message), (
        f"`{function}` {failed.describe()}, not the planted SQLSTATE {sqlstate!r} with "
        f"{message!r}. The audit insert sits outside every handler (settled), so its failure "
        "reaches the caller unchanged."
    )
    assert prepared.observe() == before, (
        f"`{function}`'s audit insert failed and its effect moved from {before!r} to "
        f"{prepared.observe()!r}: the write committed without its audit row."
    )
    assert (
        world.audit_rows(world.admin) == []
    ), f"An audit row exists for the failed `{function}`: {world.audit_rows(world.admin)}."

    retried = world.call(function, world.admin, **prepared.params)
    assert retried.failure is None, (
        f"`{function}` without the planted trigger {retried.describe()}, so the failure above "
        "says nothing about the audit insert."
    )
    assert prepared.observe() != before, f"`{function}`'s retry did not write."
    assert (
        len(world.audit_rows(world.admin)) == 1
    ), f"`{function}`'s retry left {len(world.audit_rows(world.admin))} audit rows, not one."
