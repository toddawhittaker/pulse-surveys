"""The audit log relaxes its student subject for the admin's writes and never for a reveal — E9-02.

The ticket, under "The audit row":

> `audit_log.subject_user_id` is NOT NULL today because its one action names a
> student; the migration relaxes it for the new actions, as its own column
> comment says the ticket adding such an action does, and adds a nullable
> subject person column.

and its known trap:

> **The audit column.** Relaxing `subject_user_id` must not let an
> `IDENTITY_REVEAL` row lose its subject: keep a check that the reveal action
> still names one.

The settled interface (`e9-02-interface.md`, §4) spells the mechanism:
`subject_user_id` drops `NOT NULL`; `ck_audit_log_a_reveal_names_its_student`
(`action <> 'IDENTITY_REVEAL' OR subject_user_id IS NOT NULL`) and
`ck_audit_log_an_admin_write_names_its_person` (`action = 'IDENTITY_REVEAL' OR
subject_person_id IS NOT NULL`) are added.

**Rows are written as the bootstrap identity inside `db_session`'s rolled-back
transaction**, through the declared model table, because the question is what
the *table* allows; who may write it is `test_identity_grants.py`'s question,
and what the definers write is
`test_the_people_graph_definers_audit_every_write_in_its_own_transaction.py`'s.

**Which failure a red is, before E9-02 lands.** The two reveal tests that hold
the trap today are green (the column is `NOT NULL`, 23502). The tests naming the
two checks, the relaxation, and the admin-write rows are red: the reveal one on
its SQLSTATE (23502, not 23514), the rest on the missing `AuditAction` member or
model column, each a FAILED in the body.
"""

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

AUDIT_TABLE = "audit_log"
ACTION_COLUMN = "action"
ACTOR_COLUMN = "actor_person_id"
SUBJECT_COLUMN = "subject_user_id"
SUBJECT_PERSON_COLUMN = "subject_person_id"
ROLE_COLUMN = "role"
SCOPE_COLUMN = "scope_node_id"
CASE_COLUMN = "case_id"

AUDIT_MODEL_MODULE = "app.models.audit"
AUDIT_ACTION_ENUM = "AuditAction"
REVEAL_MEMBER = "IDENTITY_REVEAL"
GRANT_MEMBER = "ROLE_GRANTED"

REVEAL_CHECK = "ck_audit_log_a_reveal_names_its_student"
ADMIN_WRITE_CHECK = "ck_audit_log_an_admin_write_names_its_person"

NOT_NULL_VIOLATION = "23502"
CHECK_VIOLATION = "23514"
# Either is the table refusing a reveal row with no subject; anything else (a
# foreign key, a missing column) is a refusal for some other reason.
SUBJECT_REQUIRED_STATES = frozenset({NOT_NULL_VIOLATION, CHECK_VIOLATION})

IS_NULLABLE = text(
    "SELECT is_nullable FROM information_schema.columns "
    "WHERE table_schema = 'public' AND table_name = :table AND column_name = :column"
)


def an_action(member: str) -> Any:
    """`AuditAction.<member>`, or a failure naming what is missing."""
    import importlib

    module = importlib.import_module(AUDIT_MODEL_MODULE)
    enum = getattr(module, AUDIT_ACTION_ENUM, None)
    found = getattr(enum, member, None) if enum is not None else None
    if found is None:
        pytest.fail(
            f"`{AUDIT_MODEL_MODULE}.{AUDIT_ACTION_ENUM}.{member}` is not there. E9-02 adds "
            "`ROLE_GRANTED`, `ROLE_REVOKED`, `REPORTS_TO_SET`, `LEAD_MAPPING_CHANGED` and "
            "`WEB_LOGIN_LINKAGE_CHANGED` beside E0-10's `IDENTITY_REVEAL`."
        )
    return found


def require_columns(metadata_tables: dict[str, Any], *columns: str) -> Any:
    table = metadata_tables[AUDIT_TABLE]
    missing = [column for column in columns if column not in table.c]
    if missing:
        pytest.fail(
            f"The `{AUDIT_TABLE}` model declares no {missing}. E9-02 adds `subject_person_id`, "
            "`role` and `scope_node_id`, nullable, to the model and the table."
        )
    return table


def a_key(seed_rows: Any, metadata_tables: dict[str, Any], table: str) -> Any:
    row = seed_rows(table)
    return row[next(iter(metadata_tables[table].primary_key.columns)).name]


def insert(db_session: Any, table: Any, values: dict[str, Any]) -> Any:
    """Insert one row in a savepoint; answer the database error, or `None`."""
    savepoint = db_session.begin_nested()
    try:
        db_session.execute(table.insert().values(**values))
    except DatabaseError as failure:
        savepoint.rollback()
        return failure
    savepoint.rollback()
    return None


def sqlstate(failure: Any) -> str | None:
    return getattr(getattr(failure, "orig", None), "sqlstate", None)


def constraint(failure: Any) -> str | None:
    diag = getattr(getattr(failure, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", None)


def a_reveal_row(
    seed_rows: Any, metadata_tables: dict[str, Any], *, subject: Any
) -> dict[str, Any]:
    return {
        ACTION_COLUMN: an_action(REVEAL_MEMBER),
        ACTOR_COLUMN: a_key(seed_rows, metadata_tables, "person"),
        SUBJECT_COLUMN: subject,
        CASE_COLUMN: None,
    }


# ---------------------------------------------------------------------------
# The reveal keeps its student.
# ---------------------------------------------------------------------------


def test_a_reveal_row_naming_its_student_is_accepted(
    db_session: Any, seed_rows: Any, metadata_tables: dict[str, Any]
) -> None:
    """CONTROL — green today and after. The insert the refusals below are twins of is well formed.

    Without it, a refusal is satisfied by an insert refused for any reason at all
    — a missing actor, an append-only trigger, a column renamed
    (`docs/MISTAKES.md` entry 3). A red here means the instrument is broken.
    """
    values = a_reveal_row(
        seed_rows, metadata_tables, subject=a_key(seed_rows, metadata_tables, "user")
    )
    failure = insert(db_session, metadata_tables[AUDIT_TABLE], values)
    assert failure is None, (
        f"A reveal row naming an actor and a student was refused: {failure!r}. The refusal tests "
        "beside this one compare against this insert, so they say nothing until this is green."
    )


def test_a_reveal_row_with_no_student_is_refused_by_the_table(
    db_session: Any, seed_rows: Any, metadata_tables: dict[str, Any]
) -> None:
    """The ticket's trap, held before and after: a reveal row never loses its subject.

    Green today (23502, the column is `NOT NULL`), green after (23514, the
    reveal check). **The mutation it kills:** `ALTER COLUMN subject_user_id DROP
    NOT NULL` with no check beside it. **The near miss it spares:** the same row
    naming its student (the control).
    """
    values = a_reveal_row(seed_rows, metadata_tables, subject=None)
    failure = insert(db_session, metadata_tables[AUDIT_TABLE], values)

    assert failure is not None, (
        f"A `{REVEAL_MEMBER}` row with a null `{SUBJECT_COLUMN}` was written. A reveal row is SPEC "
        "§6.2's record of a re-identification, and one that names no student records nothing."
    )
    assert sqlstate(failure) in SUBJECT_REQUIRED_STATES, (
        f"The subject-less reveal row was refused with SQLSTATE {sqlstate(failure)!r}: "
        f"{failure.orig!r}. A not-null or check refusal is the table requiring the subject; any "
        "other code is a refusal for a reason this test is not about."
    )


def test_a_reveal_row_with_no_student_is_refused_by_the_named_reveal_check(
    db_session: Any, seed_rows: Any, metadata_tables: dict[str, Any]
) -> None:
    """The settled mechanism: once the column is relaxed, `ck_audit_log_a_reveal_names_its_student` refuses.

    **The mutation it kills:** the check written on the wrong action, or
    dropped by a later migration that keeps the column nullable — the row is
    then written. **Expected red before E9-02 lands:** a FAILED on the SQLSTATE
    (23502 from the `NOT NULL` that the migration replaces).
    """
    values = a_reveal_row(seed_rows, metadata_tables, subject=None)
    failure = insert(db_session, metadata_tables[AUDIT_TABLE], values)

    assert failure is not None, f"A `{REVEAL_MEMBER}` row with no student was written."
    assert (sqlstate(failure), constraint(failure)) == (CHECK_VIOLATION, REVEAL_CHECK), (
        f"The subject-less reveal row was refused with SQLSTATE {sqlstate(failure)!r} by "
        f"{constraint(failure)!r}. Settled: `{SUBJECT_COLUMN}` becomes nullable and "
        f"`{REVEAL_CHECK}` is what refuses a reveal row with no student (23514)."
    )


# ---------------------------------------------------------------------------
# The admin's writes name a person and no student.
# ---------------------------------------------------------------------------


def test_the_student_subject_column_admits_a_null_for_the_actions_that_name_no_student(
    db_session: Any,
) -> None:
    """The ticket's "the migration relaxes it for the new actions". Red today.

    **The mutation it kills:** the relaxation forgotten, which makes every
    audited people-graph write fail at its audit insert — and, since the write
    and its audit row share a transaction, every People editor write with it.
    """
    nullable = db_session.execute(
        IS_NULLABLE, {"table": AUDIT_TABLE, "column": SUBJECT_COLUMN}
    ).scalar_one_or_none()

    assert nullable is not None, f"`{AUDIT_TABLE}` has no `{SUBJECT_COLUMN}` column at all."
    assert nullable == "YES", f"`{AUDIT_TABLE}.{SUBJECT_COLUMN}` is still NOT NULL."


def test_an_admin_write_row_naming_its_person_and_no_student_is_accepted(
    db_session: Any, seed_rows: Any, metadata_tables: dict[str, Any]
) -> None:
    """The admitted half of the admin-write pair: a grant row with a subject person, no student.

    **The mutation it kills:** a check that requires a student on every row
    (the reveal check written without its action clause), which refuses every
    audited admin write. **Expected red before E9-02 lands:** a FAILED naming
    the missing `AuditAction.ROLE_GRANTED`.
    """
    action = an_action(GRANT_MEMBER)
    table = require_columns(metadata_tables, SUBJECT_PERSON_COLUMN, ROLE_COLUMN, SCOPE_COLUMN)
    values = {
        ACTION_COLUMN: action,
        ACTOR_COLUMN: a_key(seed_rows, metadata_tables, "person"),
        SUBJECT_PERSON_COLUMN: a_key(seed_rows, metadata_tables, "person"),
        SUBJECT_COLUMN: None,
        CASE_COLUMN: None,
        ROLE_COLUMN: "CARE",
        SCOPE_COLUMN: uuid4(),
    }
    failure = insert(db_session, table, values)
    assert failure is None, (
        f"A `{GRANT_MEMBER}` row naming an actor and a subject person, with no student, was "
        f"refused: {failure!r}."
    )


def test_an_admin_write_row_naming_no_person_is_refused_by_the_named_admin_write_check(
    db_session: Any, seed_rows: Any, metadata_tables: dict[str, Any]
) -> None:
    """The refused half: an admin-write row naming nobody is refused by its check.

    Ticket: "Each row names the acting admin, the person written about". With
    `subject_user_id` relaxed, only `ck_audit_log_an_admin_write_names_its_person`
    stops a row that names neither. **The mutation it kills:** the relaxation
    without that check, which lets a definer write an audit row about nobody.
    **The near miss:** the same row naming its person (above), accepted.
    """
    action = an_action(GRANT_MEMBER)
    table = require_columns(metadata_tables, SUBJECT_PERSON_COLUMN, ROLE_COLUMN, SCOPE_COLUMN)
    values = {
        ACTION_COLUMN: action,
        ACTOR_COLUMN: a_key(seed_rows, metadata_tables, "person"),
        SUBJECT_PERSON_COLUMN: None,
        SUBJECT_COLUMN: None,
        CASE_COLUMN: None,
        ROLE_COLUMN: "CARE",
        SCOPE_COLUMN: uuid4(),
    }
    failure = insert(db_session, table, values)

    assert failure is not None, f"A `{GRANT_MEMBER}` row naming no person was written."
    assert (sqlstate(failure), constraint(failure)) == (CHECK_VIOLATION, ADMIN_WRITE_CHECK), (
        f"The person-less `{GRANT_MEMBER}` row was refused with SQLSTATE {sqlstate(failure)!r} by "
        f"{constraint(failure)!r}, not by `{ADMIN_WRITE_CHECK}` (23514)."
    )
