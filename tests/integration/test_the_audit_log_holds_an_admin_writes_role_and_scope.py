"""An admin-write audit row names its role and scope; a linkage row names no scope — E9-14 item 3.

ADR 0200: "The row names the action, the acting admin, the person written about
and, for an assignment or a mapping, the role and scope node." The definers
write that today, and `test_the_people_graph_definers_audit_every_write_in_its_
own_transaction.py` asserts what they write. The E9 boundary data-model review
found nothing in the table holding it: a later writer (E10's access log reads
these rows) could write a grant row with no role, which hides a Care grant from
the outside review SPEC §6.2 relies on.

**The settled interface (E9-14):** two checks on `audit_log`, added by migration
`e9b8c0d2e417`:

  - `ck_audit_log_an_admin_write_names_its_role_and_scope`, two-way for the four
    actions `ROLE_GRANTED`, `ROLE_REVOKED`, `REPORTS_TO_SET` and
    `LEAD_MAPPING_CHANGED`: a row of one of them carries a `role` and a
    `scope_node_id`. "Two-way" is read here as the other direction too: a row of
    any other action does not carry both. (A linkage row may still carry a
    `role` with no scope: ADR 0200's privilege marker.)
  - `ck_audit_log_a_linkage_names_no_scope`: a `WEB_LOGIN_LINKAGE_CHANGED` row
    carries no `scope_node_id`.

**Rows are written as the bootstrap identity inside `db_session`'s rolled-back
transaction**, through the declared model table, because the question is what
the table allows (`test_the_audit_log_still_requires_a_reveals_subject.py`'s
device, copied). PostgreSQL checks a table's `CHECK` constraints in name order,
so each refused row below is built to break exactly one check, and the test
names the check it expects.

**Which failure a red is, before E9-14 lands.** Every refused row is written
today, so each refusal test FAILS on "was written". The accepted rows are green
today and after.
"""

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

AUDIT_TABLE = "audit_log"
ROLE_AND_SCOPE_CHECK = "ck_audit_log_an_admin_write_names_its_role_and_scope"
LINKAGE_CHECK = "ck_audit_log_a_linkage_names_no_scope"
CHECK_VIOLATION = "23514"

# Each admin write, and a role its row would carry.
ADMIN_WRITES = {
    "ROLE_GRANTED": "CARE",
    "ROLE_REVOKED": "DEAN",
    "REPORTS_TO_SET": "CHAIR",
    "LEAD_MAPPING_CHANGED": "LEAD_FACULTY",
}
LINKAGE = "WEB_LOGIN_LINKAGE_CHANGED"
IMPORT = "IMPORT_APPLIED"


def an_action(member: str) -> Any:
    import importlib

    enum = importlib.import_module("app.models.audit").AuditAction
    found = getattr(enum, member, None)
    if found is None:
        pytest.fail(f"`AuditAction` has no `{member}`; E9-02 and E9-06 added it.")
    return found


def a_key(seed_rows: Any, metadata_tables: dict[str, Any], table: str) -> Any:
    row = seed_rows(table)
    return row[next(iter(metadata_tables[table].primary_key.columns)).name]


def insert(db_session: Any, table: Any, values: dict[str, Any]) -> Any:
    """Insert one row in a savepoint, always rolled back; the database error, or `None`."""
    savepoint = db_session.begin_nested()
    try:
        db_session.execute(table.insert().values(**values))
    except DatabaseError as failure:
        savepoint.rollback()
        return failure
    savepoint.rollback()
    return None


def refused_by(failure: Any) -> tuple[Any, Any]:
    orig = getattr(failure, "orig", None)
    diag = getattr(orig, "diag", None)
    return getattr(orig, "sqlstate", None), getattr(diag, "constraint_name", None)


def a_row(
    seed_rows: Any,
    metadata_tables: dict[str, Any],
    member: str,
    *,
    role: Any,
    scope: Any,
) -> dict[str, Any]:
    """One admin-shaped row for `member` naming an actor and a person, with `role` and `scope`."""
    values: dict[str, Any] = {
        "action": an_action(member),
        "actor_person_id": a_key(seed_rows, metadata_tables, "person"),
        "subject_person_id": a_key(seed_rows, metadata_tables, "person"),
        "subject_user_id": None,
        "case_id": None,
        "role": role,
        "scope_node_id": scope,
        "parent_assignment_id": uuid4() if member == "REPORTS_TO_SET" else None,
    }
    return values


# ---------------------------------------------------------------------------
# The four admin writes carry both.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("member", list(ADMIN_WRITES))
def test_an_admin_write_row_naming_its_role_and_scope_is_accepted(
    db_session: Any, seed_rows: Any, metadata_tables: dict[str, Any], member: str
) -> None:
    """CONTROL — green today and after: the row every refusal below is a twin of is well formed.

    Without it, a refusal is satisfied by a row refused for any reason at all
    (`docs/MISTAKES.md` entry 3). **The mutation it kills:** the check written
    the wrong way round, refusing every admin write — and with it every People
    editor write, since the write and its audit row share a transaction.
    """
    values = a_row(seed_rows, metadata_tables, member, role=ADMIN_WRITES[member], scope=uuid4())
    failure = insert(db_session, metadata_tables[AUDIT_TABLE], values)
    assert failure is None, f"A `{member}` row naming its role and scope was refused: {failure!r}."


MISSING = {
    "no role": {"role": None},
    "no scope": {"scope": None},
    "neither": {"role": None, "scope": None},
}


@pytest.mark.parametrize("missing", list(MISSING))
@pytest.mark.parametrize("member", list(ADMIN_WRITES))
def test_an_admin_write_row_missing_its_role_or_scope_is_refused_by_the_named_check(
    db_session: Any, seed_rows: Any, metadata_tables: dict[str, Any], member: str, missing: str
) -> None:
    """Each of the four actions, with no role, no scope or neither: 23514 from the settled check.

    **The mutations it kills:** no check (the row is written); a check over
    some of the four actions only; a check on `role` alone or on the scope
    alone. **The near miss it spares:** the same row with both, accepted above.
    """
    values = a_row(
        seed_rows,
        metadata_tables,
        member,
        **{"role": ADMIN_WRITES[member], "scope": uuid4(), **MISSING[missing]},
    )
    failure = insert(db_session, metadata_tables[AUDIT_TABLE], values)

    assert failure is not None, f"A `{member}` row with {missing} was written."
    assert refused_by(failure) == (CHECK_VIOLATION, ROLE_AND_SCOPE_CHECK), (
        f"The `{member}` row with {missing} was refused with {refused_by(failure)} "
        f"({failure.orig!r}), not by `{ROLE_AND_SCOPE_CHECK}` (23514)."
    )


def test_a_row_of_another_action_carrying_a_role_and_a_scope_is_refused_by_the_two_way_check(
    db_session: Any, seed_rows: Any, metadata_tables: dict[str, Any]
) -> None:
    """The other direction: an import record with a role and a scope node is refused.

    `IMPORT_APPLIED` is the one other admin action (E9-06); its row names the
    acting admin and the diff and nothing else. Read beside the accepted import
    row in `test_the_import_record_definer_answers_only_an_admin.py`, which
    carries no role and no scope.

    **The mutation it kills:** the check written one way only (`action NOT IN
    (...) OR (role IS NOT NULL AND scope_node_id IS NOT NULL)`), which lets any
    other row carry an assignment's shape and read, in E10's log, as a grant.
    **The near miss it spares:** the same import row without the two, accepted.
    """
    table = metadata_tables[AUDIT_TABLE]
    base = {
        "action": an_action(IMPORT),
        "actor_person_id": a_key(seed_rows, metadata_tables, "person"),
        "subject_person_id": None,
        "subject_user_id": None,
        "case_id": None,
        "parent_assignment_id": None,
        "detail": {"kind": "people", "diff": {"added": [], "changed": []}},
    }
    plain = insert(db_session, table, {**base, "role": None, "scope_node_id": None})
    shaped = insert(db_session, table, {**base, "role": "CARE", "scope_node_id": uuid4()})

    assert plain is None, (
        f"The control: an import row with no role and no scope was refused ({plain!r}), so the "
        "refusal below may be about something else."
    )
    assert shaped is not None, "An import row carrying a role and a scope node was written."
    assert refused_by(shaped) == (CHECK_VIOLATION, ROLE_AND_SCOPE_CHECK), (
        f"The import row with a role and scope was refused with {refused_by(shaped)} "
        f"({shaped.orig!r}), not by `{ROLE_AND_SCOPE_CHECK}`."
    )


# ---------------------------------------------------------------------------
# A linkage names no scope.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["CARE", "ADMIN", None])
def test_a_linkage_row_with_no_scope_is_accepted_whatever_privilege_it_records(
    db_session: Any, seed_rows: Any, metadata_tables: dict[str, Any], role: Any
) -> None:
    """CONTROL — green today and after: ADR 0200's linkage row, `CARE`, `ADMIN` or no role, no scope.

    **The mutation it kills:** the role-and-scope check written over every
    action that carries a role, which refuses a Care holder's linkage row.
    """
    values = a_row(seed_rows, metadata_tables, LINKAGE, role=role, scope=None)
    failure = insert(db_session, metadata_tables[AUDIT_TABLE], values)
    assert (
        failure is None
    ), f"A linkage row with role {role!r} and no scope was refused: {failure!r}."


def test_a_linkage_row_naming_a_scope_is_refused_by_the_linkage_check(
    db_session: Any, seed_rows: Any, metadata_tables: dict[str, Any]
) -> None:
    """A `WEB_LOGIN_LINKAGE_CHANGED` row with a scope node and no role: 23514 from the linkage check.

    No role, so the two-way role-and-scope check has nothing to refuse and only
    the linkage check can. **The mutation it kills:** the linkage check
    missing. **The near miss it spares:** the linkage rows above, accepted.
    """
    values = a_row(seed_rows, metadata_tables, LINKAGE, role=None, scope=uuid4())
    failure = insert(db_session, metadata_tables[AUDIT_TABLE], values)

    assert failure is not None, "A linkage row naming a scope node was written."
    assert refused_by(failure) == (CHECK_VIOLATION, LINKAGE_CHECK), (
        f"The linkage row naming a scope was refused with {refused_by(failure)} "
        f"({failure.orig!r}), not by `{LINKAGE_CHECK}` (23514)."
    )
