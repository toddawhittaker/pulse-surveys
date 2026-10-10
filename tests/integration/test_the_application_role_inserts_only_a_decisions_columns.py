"""`pulse_app` may insert only a decision's columns, as production runs it — E6-03, criterion 8.

> `pulse_app` can insert only the decision columns, proven through the production
> connection (entry 46), and still holds nothing on `threat_case`.

E6-03's grants file, `backend/app/views_sql/moderation_decision_grants_v001.sql`,
gives `pulse_app` column-grain `INSERT` on **exactly the columns a decision writes**:
the comment, the state, the decider, the role it was decided under, the reason and
whether it is an undo. Everything else on the row is the database's to fill — the
key (ADR 0016's `gen_random_uuid()`), E6-01's `sequence`, and `decided_at`, a
`now()` server default (`docs/tickets/e4/deferred.md`) — and stays refused.

**On `application_session`, a real `pulse_app` login on the application engine**
(`tests/fixtures/authz_data.py`): `docs/MISTAKES.md` entry 46 is the record of a
suite that drove a grant through the migrating engine and passed every
grant-shaped failure. Every statement runs in a savepoint that is rolled back.

**Every refusal is SQLSTATE 42501 and sits beside the accepted insert one column
away** (entries 3 and 35): a connection that can do nothing satisfies every
refusal, and a refusal for a constraint is not a refusal for a grant.

The catalog's half — the exact set of column grants — is
`RUNTIME_COLUMN_PRIVILEGES` in `tests/integration/test_identity_grants.py`. E6-01's
direct-write test,
`test_a_moderation_verdict_is_routed_only_through_its_definer.py`, is amended to
this grant in the same change.

**Which failure a red is, before E6-03 lands:** `require_decision_columns` fails
naming M2's columns (entry 44); once they exist and the grant does not, the accepted
insert fails with 42501.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.care_subject import plant_a_comment_answer
from fixtures.instructor_decisions import require_decision_columns
from fixtures.moderation import UNMODERATED
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

APPLICATION_ROLE = "pulse_app"
INSUFFICIENT_PRIVILEGE = "42501"

# A decision as the decision service writes it: every decision column named.
A_DECISION = (
    "INSERT INTO public.moderation_state "
    "(answer_id, state, decided_by_person_id, decided_as, reason, is_undo) VALUES "
    "(CAST(:answer AS uuid), 'EXCLUDED', CAST(:person AS uuid), 'INSTRUCTOR', "
    "'E6-03: a reason written through the grant', false)"
)
# The same decision naming the row's key as well — a column no decision writes.
A_DECISION_NAMING_ITS_KEY = (
    "INSERT INTO public.moderation_state "
    "(id, answer_id, state, decided_by_person_id, decided_as, reason, is_undo) VALUES "
    "(CAST(:key AS uuid), CAST(:answer AS uuid), 'EXCLUDED', CAST(:person AS uuid), "
    "'INSTRUCTOR', 'E6-03: a reason written through the grant', false)"
)


def sqlstate(failure: Any) -> str | None:
    return getattr(getattr(failure, "orig", None), "sqlstate", None)


def attempted(session: Any, statement: str, parameters: dict[str, Any]) -> Any:
    """Run `statement` in a savepoint that is always rolled back; answer its error or `None`."""
    savepoint = session.begin_nested()
    try:
        session.execute(text(statement), parameters)
    except DatabaseError as failure:
        savepoint.rollback()
        return failure
    savepoint.rollback()
    return None


@pytest.fixture
def decision_rows(committed_rows: Any) -> dict[str, Any]:
    """A committed comment and a committed person for a decision to name."""
    planted = plant_a_comment_answer(committed_rows, verdict=UNMODERATED)
    person = committed_rows.seed("person", {})
    committed_rows.commit()
    return {"answer": str(planted.answer_id), "person": str(person["id"])}


def require_the_application_role(session: Any) -> None:
    current = session.execute(text("SELECT current_user")).scalar_one()
    assert current == APPLICATION_ROLE, (
        f"`application_session` connects as {current!r}; every claim here is about "
        f"`{APPLICATION_ROLE}` (`docs/MISTAKES.md` entry 46), and a superuser passes all of them."
    )


def test_the_application_connection_inserts_a_decision_and_nothing_beyond_its_columns(
    application_session: Any, committed_rows: Any, decision_rows: dict[str, Any]
) -> None:
    """The pair, one column apart: a decision is accepted; the same decision naming `id` is refused.

    **The mutations this kills:** no grant at all (the decision service cannot write
    on the connection production runs, and every route test driven through the
    migrating engine still passes — entry 46's exact shape; the accepted half is
    red); and `GRANT INSERT ON moderation_state` table-wide in place of the column
    grant (the refused half is accepted).
    """
    require_decision_columns(committed_rows.tables)
    require_the_application_role(application_session)

    accepted = attempted(application_session, A_DECISION, decision_rows)
    assert accepted is None, (
        f"`{APPLICATION_ROLE}` was refused a decision naming exactly the decision columns: "
        f"{accepted} (SQLSTATE {sqlstate(accepted)}). E6-03's grants file gives it column-grain "
        "`INSERT` on those columns; without it the instructor's door cannot write on the "
        "connection production runs."
    )
    beyond = attempted(
        application_session, A_DECISION_NAMING_ITS_KEY, {**decision_rows, "key": str(uuid4())}
    )
    assert beyond is not None and sqlstate(beyond) == INSUFFICIENT_PRIVILEGE, (
        f"`{APPLICATION_ROLE}` inserting a decision that names the row's own `id` was answered "
        f"{beyond!r} (SQLSTATE {sqlstate(beyond)}), not refused with {INSUFFICIENT_PRIVILEGE}. "
        "The grant is on the columns a decision writes and no others — a table-wide `INSERT` "
        "is what this refusal tells apart from it."
    )


def test_the_application_connection_holds_no_table_wide_insert_and_no_rewrite_of_the_record(
    application_session: Any, committed_rows: Any, decision_rows: dict[str, Any]
) -> None:
    """The record stays append-only, and the column grant is not a table grant in disguise.

    On `pulse_app`'s own login: `UPDATE` and `DELETE` on `moderation_state` are
    refused with 42501, and `has_table_privilege(…, 'INSERT')` is false while
    `has_any_column_privilege(…, 'INSERT')` is true. **The control** is the second of
    those two: the catalog reports the column grant on this very connection, so the
    first is not a reader that cannot see grants.

    **The mutations this kills:** `UPDATE` granted with the insert (an exclusion
    rewritten in place — the trail §5.2's log is built on, gone); `DELETE` (an undo
    written as a deletion); and a table-wide `INSERT`.
    """
    require_decision_columns(committed_rows.tables)
    require_the_application_role(application_session)

    def holds(function: str) -> bool:
        return bool(
            application_session.execute(
                text(f"SELECT {function}('public.moderation_state', 'INSERT')")
            ).scalar_one()
        )

    assert holds("has_any_column_privilege"), (
        f"`{APPLICATION_ROLE}` holds `INSERT` on no column of `moderation_state`, so the "
        "refusals below are a connection that cannot write the table at all."
    )
    assert not holds("has_table_privilege"), (
        f"`{APPLICATION_ROLE}` holds `INSERT` on `moderation_state` table-wide. E6-03 grants it "
        "at column grain, on the columns a decision writes."
    )
    rewrites = {
        "update": "UPDATE public.moderation_state SET state = 'KEPT'",
        "delete": "DELETE FROM public.moderation_state",
    }
    not_refused = {
        name: sqlstate(failure)
        for name, statement in rewrites.items()
        if (failure := attempted(application_session, statement, {})) is None
        or sqlstate(failure) != INSUFFICIENT_PRIVILEGE
    }
    assert not not_refused, (
        f"On `{APPLICATION_ROLE}`, these rewrites of the moderation record were not refused with "
        f"{INSUFFICIENT_PRIVILEGE}: {not_refused}. The record is append-only (SPEC §8)."
    )


def test_the_application_connection_still_holds_nothing_on_threat_case(
    application_session: Any, committed_rows: Any, decision_rows: dict[str, Any]
) -> None:
    """Criterion 8's last clause: E6-03's grant reaches `moderation_state` and nothing beside it.

    `SELECT` and `INSERT` on `threat_case` are both refused with 42501 on
    `pulse_app`'s login. **The control** is the accepted decision in the first test,
    and here the same connection's read of `moderation_state`, which E4-06 granted.

    **The mutation this kills:** a grants file that reaches for the whole moderation
    family — an instructor's connection able to count, or open, Care cases.

    **Green before E6-03 lands, by design**: E6-01 already withholds both. It is the
    guard that stays red-able while E6-03's grants file is written next to it.
    """
    require_the_application_role(application_session)
    readable = attempted(application_session, "SELECT count(*) FROM public.moderation_state", {})
    assert readable is None, f"`{APPLICATION_ROLE}` cannot read `moderation_state`: {readable}."

    statements = {
        "select": "SELECT count(*) FROM public.threat_case",
        "insert": (
            "INSERT INTO public.threat_case (answer_id, classification_id, opened_at) "
            "VALUES (CAST(:answer AS uuid), CAST(:classification AS uuid), now())"
        ),
    }
    parameters = {"answer": decision_rows["answer"], "classification": str(uuid4())}
    not_refused = {
        name: sqlstate(failure)
        for name, statement in statements.items()
        if (failure := attempted(application_session, statement, parameters)) is None
        or sqlstate(failure) != INSUFFICIENT_PRIVILEGE
    }
    assert not not_refused, (
        f"On `{APPLICATION_ROLE}`, these were not refused on `threat_case` with "
        f"{INSUFFICIENT_PRIVILEGE}: {not_refused}. It holds no privilege there of any kind."
    )
