"""The import's audit record is written by one admin-checked definer and no other way — E9-06 fix round, Q1 (e).

SPEC §8: "`audit_log` is append-only and includes all re-identifications,
imports (with their dry-run diffs), and admin config edits." The fix round's
settled interface:

  - `public.admin_record_import(actor_person_id uuid, kind text, diff jsonb)`,
    a `SECURITY DEFINER` function in `views_sql/people_graph_v002.sql`, owned by
    `pulse_people_graph_definer`, `EXECUTE` for `pulse_app` only;
  - the same live-`ADMIN` check on the actor as E9-02's writers, refusing with
    SQLSTATE `P0001` and the message `admin_people.actor_not_an_admin`;
  - one `audit_log` row, action `AuditAction.IMPORT_APPLIED`, naming the actor,
    and carrying the kind (`people` or `lead_mappings`) and the diff;
  - `audit_log.detail jsonb`, nullable, with a check that it is non-null exactly
    for `IMPORT_APPLIED`.

**Where the kind and the diff sit inside the row is not settled**, so nothing
here assumes it: the row is read whole as `to_jsonb(audit_log.*)`, the kind is
required to appear in it as a value, and the diff is required to appear in it as
an object holding every member the diff has, equal. Only `detail` being non-null
is asserted by name, because that is settled.

**Every call rides `application_session`** (`pulse_app`, holding only what the
migrations grant; `docs/MISTAKES.md` entry 46), and every read-back rides the
bootstrap identity on a second connection, after the call committed or rolled
back.

**Which failure a red is, at 09778dc5.** The function does not exist, so every
call answers SQLSTATE 42883 and fails the assertion on the named refusal or on
the admin's call succeeding; `AuditAction` has no `IMPORT_APPLIED` and
`audit_log` no `detail`, each a `pytest.fail` naming it. All FAILED, none ERROR.
"""

import importlib
import json
from typing import Any
from uuid import uuid4

import pytest
from fixtures.people_graph import (
    ACTOR_NOT_AN_ADMIN,
    APPLICATION_ROLE,
    NAMED_REFUSAL,
    OWNER_ROLE,
    ROLE_GRANTED,
    Called,
    PeopleGraphWorld,
)
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

FUNCTION = "admin_record_import"
IMPORT_APPLIED = "IMPORT_APPLIED"
KINDS = ("people", "lead_mappings")
INSUFFICIENT_PRIVILEGE = "42501"
CHECK_VIOLATION = "23514"

RECORD = text(
    f"SELECT public.{FUNCTION}(CAST(:actor AS uuid), CAST(:kind AS text), CAST(:diff AS jsonb))"
)

# Every `IMPORT_APPLIED` row whose whole text carries `marker`, read as JSON. The
# action is compared as text so this read runs before the enum value exists.
IMPORT_ROWS = text(
    "SELECT CAST(a.actor_person_id AS text) AS actor, to_jsonb(a) AS whole, "
    "to_jsonb(a) -> 'detail' AS detail FROM public.audit_log a "
    "WHERE CAST(a.action AS text) = 'IMPORT_APPLIED' AND strpos(CAST(to_jsonb(a) AS text), :marker) > 0"
)

DEAN = "a dean"
CARE = "a Care holder"
NOBODY = "a person with no assignment"
NULL_KEY = "a null key"
REFUSED_CALLERS = (DEAN, CARE, NOBODY, NULL_KEY)


def caller(world: PeopleGraphWorld, who: str) -> Any:
    return {DEAN: world.dean, CARE: world.care, NOBODY: world.nobody, NULL_KEY: None}[who]


# ---------------------------------------------------------------------------
# Helpers shared with the HTTP module (imported from here, not copied).
# ---------------------------------------------------------------------------


def import_applied_member() -> Any:
    """`AuditAction.IMPORT_APPLIED`, or a failure naming it."""
    action = importlib.import_module("app.models.audit").AuditAction
    member = getattr(action, IMPORT_APPLIED, None)
    if member is None:
        pytest.fail(
            f"`AuditAction` has no `{IMPORT_APPLIED}`; it has {sorted(m.name for m in action)}. "
            "E9-06's fix round adds it for the import's audit row (SPEC §8)."
        )
    return member


def contains_value(tree: Any, target: Any) -> bool:
    """Whether `target` equals `tree` or any value nested anywhere inside it."""
    if tree == target:
        return True
    if isinstance(tree, dict):
        return any(contains_value(value, target) for value in tree.values())
    if isinstance(tree, list):
        return any(contains_value(value, target) for value in tree)
    return False


def holds_the_diff(tree: Any, diff: dict[str, Any]) -> bool:
    """Whether some object in `tree` (itself included) has every member of `diff`, each equal.

    A superset match, so the test does not decide whether the diff is stored
    alone, beside the kind, or with the digest; it does decide that every member
    the admin was shown is there with the value they were shown.
    """
    if isinstance(tree, dict):
        if all(key in tree and tree[key] == value for key, value in diff.items()):
            return True
        return any(holds_the_diff(value, diff) for value in tree.values())
    if isinstance(tree, list):
        return any(holds_the_diff(value, diff) for value in tree)
    return False


def a_diff(marker: str) -> dict[str, Any]:
    """A diff-shaped object carrying `marker`, so its row is found among everyone else's."""
    return {
        "added": [{"name": f"E9-06 Imported {marker}", "category": "Dean"}],
        "changed": [],
        "removed": [],
        "unmapped": [],
    }


# ---------------------------------------------------------------------------
# Calling and reading.
# ---------------------------------------------------------------------------


def record(world: PeopleGraphWorld, actor: Any, kind: str, diff: dict[str, Any]) -> Called:
    """One call of the definer as `pulse_app`; committed if it succeeded."""
    values = {
        "actor": None if actor is None else str(actor),
        "kind": kind,
        "diff": json.dumps(diff),
    }
    try:
        value = world.app.execute(RECORD, values).scalar()
    except DatabaseError as failure:
        world.app.rollback()
        return Called(None, failure)
    world.app.commit()
    return Called(value, None)


def import_rows(world: PeopleGraphWorld, marker: str) -> list[dict[str, Any]]:
    world.rows.session.rollback()
    found = world.rows.session.execute(IMPORT_ROWS, {"marker": marker}).mappings().all()
    return [dict(row) for row in found]


# ---------------------------------------------------------------------------
# The row it writes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_the_definer_writes_one_row_naming_the_admin_the_kind_and_the_diff(
    people_graph: PeopleGraphWorld, kind: str
) -> None:
    """An admin's call: one `IMPORT_APPLIED` row, the admin as actor, `detail` set, the kind and the diff in it.

    **The mutations it kills:** no insert; two rows per call; the actor left
    null or written from anything but the argument; `detail` left null; the diff
    summarised (counts) or truncated instead of stored as given; the kind not
    stored. **The near miss it spares:** the other kind, which must not appear
    in the row — so a body writing a constant kind is red for one parameter.
    """
    world = people_graph
    marker = uuid4().hex
    diff = a_diff(marker)
    other = next(k for k in KINDS if k != kind)

    called = record(world, world.admin, kind, diff)

    assert called.failure is None, f"`{FUNCTION}` called by the admin {called.describe()}."
    rows = import_rows(world, marker)
    assert len(rows) == 1, f"The admin's one call left {len(rows)} `IMPORT_APPLIED` rows: {rows}."
    (row,) = rows
    assert row["actor"] == str(world.admin), f"The row names {row['actor']}, not the admin."
    assert row["detail"] is not None, "The row's `detail` is null; settled: non-null for an import."
    assert holds_the_diff(
        row["whole"], diff
    ), f"The row {row['whole']} does not hold the diff {diff} as it was passed."
    assert contains_value(row["whole"], kind), f"The row {row['whole']} does not carry `{kind}`."
    assert not contains_value(
        row["whole"], other
    ), f"The row for a `{kind}` import carries `{other}`: {row['whole']}."


@pytest.mark.parametrize("who", REFUSED_CALLERS)
def test_the_definer_refuses_a_key_with_no_live_admin_assignment_and_writes_for_an_admin(
    people_graph: PeopleGraphWorld, who: str
) -> None:
    """The v001 writers' admin check, on the new definer, with the admin's call as the twin.

    **The mutations it kills:** no admin check, so `pulse_app` can enter an
    import nobody made; a check admitting a dean, a Care holder or any person
    row; a null key let through; the refusal raised as another code or key
    (including `pulse_app` lacking `EXECUTE`, 42501); a refusal that still
    writes its row. **The near miss:** the admin, in the same world, whose call
    writes exactly one row — so a definer refusing everyone is red too.
    """
    world = people_graph
    marker = uuid4().hex

    refused = record(world, caller(world, who), "lead_mappings", a_diff(marker))

    assert (refused.sqlstate, refused.message) == (NAMED_REFUSAL, ACTOR_NOT_AN_ADMIN), (
        f"`{FUNCTION}` called by {who} {refused.describe()}. Settled: the same live-`ADMIN` check "
        f"as the v001 writers, refusing with `{ACTOR_NOT_AN_ADMIN}` (SQLSTATE {NAMED_REFUSAL})."
    )
    assert import_rows(world, marker) == [], f"`{FUNCTION}` refused {who} and wrote a row anyway."

    admitted = record(world, world.admin, "lead_mappings", a_diff(marker))
    assert admitted.failure is None, (
        f"`{FUNCTION}` called by the admin {admitted.describe()}. Without the admin's row the "
        "refusal above proves nothing."
    )
    assert len(import_rows(world, marker)) == 1, "The admin's call did not leave exactly one row."


# ---------------------------------------------------------------------------
# No way around it.
# ---------------------------------------------------------------------------


def _insert(session: Any, tables: dict[str, Any], values: dict[str, Any]) -> Any:
    """One `audit_log` insert in a savepoint, always rolled back; the error it raised, or `None`."""
    audit = tables["audit_log"]
    if "detail" not in audit.c:
        pytest.fail(
            "The `audit_log` model has no `detail` column. E9-06's fix round adds it (nullable "
            "`jsonb`, non-null exactly for `IMPORT_APPLIED`)."
        )
    savepoint = session.begin_nested()
    try:
        session.execute(audit.insert().values(**values))
    except DatabaseError as failure:
        savepoint.rollback()
        return failure
    savepoint.rollback()
    return None


def _sqlstate(failure: Any) -> Any:
    return getattr(getattr(failure, "orig", None), "sqlstate", None)


def _an_import_row(world: PeopleGraphWorld, detail: Any) -> dict[str, Any]:
    return {
        "action": import_applied_member(),
        "actor_person_id": world.admin,
        "subject_person_id": None,
        "subject_user_id": None,
        "case_id": None,
        "role": None,
        "scope_node_id": None,
        "parent_assignment_id": None,
        "detail": detail,
    }


def _a_grant_row(world: PeopleGraphWorld, detail: Any) -> dict[str, Any]:
    granted = importlib.import_module("app.models.audit").AuditAction.ROLE_GRANTED
    assert granted.name == ROLE_GRANTED
    return {
        "action": granted,
        "actor_person_id": world.admin,
        "subject_person_id": world.dean,
        "subject_user_id": None,
        "case_id": None,
        "role": "CARE",
        "scope_node_id": None,
        "parent_assignment_id": None,
        "detail": detail,
    }


def test_the_application_role_cannot_insert_an_import_row_directly(
    people_graph: PeopleGraphWorld,
) -> None:
    """`pulse_app` writing an `IMPORT_APPLIED` row itself is refused with 42501; the bootstrap's same row is not.

    **The mutation it kills:** the migration granting `INSERT` on `audit_log`
    (or on its columns) to `pulse_app`, which makes the definer's admin check
    decorative and the append-only log writable by the application. **The near
    miss it spares:** the identical row inserted by the bootstrap identity, which
    must be accepted — so the refusal is the privilege, not the row's shape.
    """
    world = people_graph
    row = _an_import_row(world, {"kind": "people", "diff": a_diff(uuid4().hex)})

    as_application = _insert(world.app, world.rows.tables, row)
    world.app.rollback()
    as_bootstrap = _insert(world.rows.session, world.rows.tables, row)
    world.rows.session.rollback()

    assert as_application is not None, (
        f"`{APPLICATION_ROLE}` inserted an `{IMPORT_APPLIED}` row into `audit_log` directly. The "
        "import's record is written by the admin-checked definer only."
    )
    assert _sqlstate(as_application) == INSUFFICIENT_PRIVILEGE, (
        f"`{APPLICATION_ROLE}`'s direct insert failed with SQLSTATE {_sqlstate(as_application)!r} "
        f"({as_application.orig!r}), not {INSUFFICIENT_PRIVILEGE}: it got past the grant."
    )
    assert as_bootstrap is None, (
        f"The bootstrap identity's identical row was refused ({as_bootstrap!r}), so the refusal "
        "above may be the row's shape rather than the privilege."
    )


# (action, detail present, accepted). The settled check: `detail` is non-null
# exactly for `IMPORT_APPLIED`. Two boundary pairs.
DETAIL_CASES = {
    "an import with a detail": (IMPORT_APPLIED, True, True),
    "an import with no detail": (IMPORT_APPLIED, False, False),
    "a grant with no detail": (ROLE_GRANTED, False, True),
    "a grant with a detail": (ROLE_GRANTED, True, False),
}


@pytest.mark.parametrize("case", list(DETAIL_CASES))
def test_detail_is_present_exactly_on_an_import_row(
    people_graph: PeopleGraphWorld, case: str
) -> None:
    """The check on `audit_log.detail`, both directions, each beside its accepted twin.

    **The mutations it kills:** no check (an import row with no diff, which is
    the defect SPEC §8 names); a check in one direction only (`detail` allowed
    on other rows, where it could carry anything E10's log then shows).
    **The near misses:** the accepted half of each pair.
    """
    world = people_graph
    action, with_detail, accepted = DETAIL_CASES[case]
    detail = {"kind": "people", "diff": a_diff(uuid4().hex)} if with_detail else None
    row = _an_import_row(world, detail) if action == IMPORT_APPLIED else _a_grant_row(world, detail)

    failure = _insert(world.rows.session, world.rows.tables, row)
    world.rows.session.rollback()

    if accepted:
        assert failure is None, f"{case.capitalize()} was refused: {failure!r}."
    else:
        assert failure is not None, f"{case.capitalize()} was accepted."
        assert _sqlstate(failure) == CHECK_VIOLATION, (
            f"{case.capitalize()} failed with SQLSTATE {_sqlstate(failure)!r} ({failure.orig!r}), "
            f"not {CHECK_VIOLATION} (a check constraint)."
        )


PROC = text(
    "SELECT p.prosecdef AS definer, pg_get_userbyid(p.proowner) AS owner, "
    "p.proacl IS NULL AS default_acl, "
    "ARRAY(SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END "
    "      FROM aclexplode(p.proacl) a "
    "      WHERE a.privilege_type = 'EXECUTE' AND a.grantee <> p.proowner "
    "      ORDER BY 1) AS executors "
    "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
    "WHERE n.nspname = 'public' AND p.proname = :name"
)


def test_the_definer_is_owned_by_the_people_graph_owner_and_executable_by_pulse_app_alone(
    people_graph: PeopleGraphWorld,
) -> None:
    """One function by the name, `SECURITY DEFINER`, owned by `pulse_people_graph_definer`, `EXECUTE` for `pulse_app` only.

    **The mutations it kills:** a `SECURITY INVOKER` body (it would then need
    `pulse_app` to hold `INSERT` on `audit_log`); an owner that is the migration
    identity or a superuser; the default ACL left in place, which lets `PUBLIC`
    — `pulse_care` included — execute it; an `EXECUTE` granted to any other
    role; a second overload with a looser signature.
    """
    world = people_graph
    world.rows.session.rollback()
    found = world.rows.session.execute(PROC, {"name": FUNCTION}).mappings().all()
    world.rows.session.rollback()

    assert len(found) == 1, f"`public.{FUNCTION}` exists {len(found)} times; settled: once."
    (proc,) = found
    assert proc["definer"] is True, f"`{FUNCTION}` is not `SECURITY DEFINER`."
    assert proc["owner"] == OWNER_ROLE, f"`{FUNCTION}` is owned by {proc['owner']!r}."
    assert (
        proc["default_acl"] is False
    ), f"`{FUNCTION}` carries the default ACL, which grants `EXECUTE` to `PUBLIC`."
    assert list(proc["executors"]) == [APPLICATION_ROLE], (
        f"`EXECUTE` on `{FUNCTION}` is held by {list(proc['executors'])}; settled: "
        f"`{APPLICATION_ROLE}` only."
    )
