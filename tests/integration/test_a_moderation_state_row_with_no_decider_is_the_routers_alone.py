"""A `moderation_state` row with no decider is the router's alone — ticket E6-03, M2.

E6-03 gives `pulse_app` column-grain `INSERT` on `answer_id` and `state` (among the
six columns a decision writes), and M2's `CHECK`s accept a decider-less
`FLAGGED_COLLAPSED` row, because that is the routing definer's flag. Together those
would let the application connection write a flag no moderation verdict opened —
a comment hidden from students with no verdict behind it and no decision on record.

**The settled mechanism** (the coordinator's ruling, 2026-10-10): a `BEFORE INSERT`
trigger on `moderation_state` refuses a row whose `decided_by_person_id` is `NULL`
unless `current_user` is `pulse_moderation_definer` — E6-01's pattern on
`classification`, which
`tests/integration/test_identity_grants.py::test_a_moderation_verdict_written_around_the_definer_is_refused_to_every_role_but_its_owner`
asserts. This module asserts its behaviour from both sides:

  - **on `pulse_app`'s production login** (`docs/MISTAKES.md` entry 46): a
    decider-less flag is refused; a decision with a decider is accepted; and the
    definer's own flag still lands when a `harmful` verdict is routed through the
    door on the same connection;
  - **on the bootstrap identity**: the same decider-less flag is refused, and
    accepted when the definer's owner writes it — so the rule is "unless the
    definer", not "if `pulse_app`".

**Why a refusal here is the trigger's and nothing else's.** The refused insert names
`answer_id` and `state` only, a subset of the columns the accepted decision names on
the same connection, so the column grant cannot be what refuses it; and a
decider-less `FLAGGED_COLLAPSED` row satisfies every `CHECK` M2 settles, which the
definer's accepted write proves. Nothing else is left to refuse it.

Marked `invariant`. **Which failure a red is, before E6-03 lands:**
`require_decision_columns` fails naming M2's columns (entry 44).
"""

from typing import Any

import pytest
from fixtures.care_subject import plant_a_comment_answer
from fixtures.instructor_decisions import DECIDER_COLUMN, require_decision_columns
from fixtures.moderation import (
    FLAGGED_COLLAPSED,
    HARMFUL,
    MODERATION_DEFINER_ROLE,
    ROUTING_CALL,
    UNMODERATED,
    moderation_states,
)
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

APPLICATION_ROLE = "pulse_app"

A_ROUTER_SHAPED_ROW = (
    "INSERT INTO public.moderation_state (answer_id, state) "
    "VALUES (CAST(:answer AS uuid), 'FLAGGED_COLLAPSED')"
)
A_DECISION = (
    "INSERT INTO public.moderation_state "
    "(answer_id, state, decided_by_person_id, decided_as, reason, is_undo) VALUES "
    "(CAST(:answer AS uuid), 'FLAGGED_COLLAPSED', CAST(:person AS uuid), 'INSTRUCTOR', "
    "NULL, false)"
)


def sqlstate(failure: Any) -> str | None:
    return getattr(getattr(failure, "orig", None), "sqlstate", None)


def attempted(session: Any, statement: str, parameters: dict[str, Any], role: str = "") -> Any:
    """Run `statement`, as `role` if one is named, in a savepoint always rolled back.

    The rollback also undoes the `SET ROLE`, so no reset runs in an aborted
    transaction and replaces the refusal with an error of its own.
    """
    savepoint = session.begin_nested()
    try:
        if role:
            session.execute(text(f'SET ROLE "{role}"'))
        session.execute(text(statement), parameters)
    except DatabaseError as failure:
        savepoint.rollback()
        return failure
    savepoint.rollback()
    return None


@pytest.fixture
def subjects(committed_rows: Any) -> dict[str, Any]:
    """A committed comment with no verdict (its window closed) and a committed person."""
    planted = plant_a_comment_answer(committed_rows, verdict=UNMODERATED)
    person = committed_rows.seed("person", {})
    committed_rows.commit()
    return {"answer": str(planted.answer_id), "person": str(person["id"])}


def test_the_application_connection_is_refused_a_router_row_and_the_router_still_writes_one(
    application_session: Any, committed_rows: Any, subjects: dict[str, Any]
) -> None:
    """On `pulse_app`: no decider-less flag by hand, a decision with a decider, the door's flag.

    In order, on the connection production uses:

      1. a decision naming a decider is accepted (the control: the grant admits these
         columns, so the refusal in step 2 is not the grant's);
      2. the same comment's decider-less `FLAGGED_COLLAPSED` row is refused;
      3. a `harmful` verdict routed through `route_moderation_verdict` lands its flag
         — one decider-less `FLAGGED_COLLAPSED` row, read back on the bootstrap
         connection — so the trigger did not shut the door it exists to protect.

    **The mutations this kills:** no trigger (step 2 is accepted: a flag with no
    verdict, written by the application connection); a trigger refusing every
    decider-less row (step 3 leaves no flag — every harmful comment is shown to
    students uncollapsed); and a trigger keyed on `session_user`, which is
    `pulse_app` inside the door too and fails step 3 the same way.
    """
    require_decision_columns(committed_rows.tables)
    current = application_session.execute(text("SELECT current_user")).scalar_one()
    assert current == APPLICATION_ROLE, f"`application_session` connects as {current!r}."

    decision = attempted(application_session, A_DECISION, subjects)
    assert decision is None, (
        f"`{APPLICATION_ROLE}` was refused a decision naming a decider: {decision} (SQLSTATE "
        f"{sqlstate(decision)}). Until it is accepted, the refusal below may be the grant's."
    )
    by_hand = attempted(application_session, A_ROUTER_SHAPED_ROW, subjects)
    assert by_hand is not None, (
        f"`{APPLICATION_ROLE}` inserted a `FLAGGED_COLLAPSED` row with no decider directly. That "
        "is a flag no moderation verdict opened. The ruled trigger refuses a decider-less row "
        f"unless `current_user` is `{MODERATION_DEFINER_ROLE}`."
    )

    application_session.execute(
        text(ROUTING_CALL),
        {
            "answer_id": subjects["answer"],
            "verdict": HARMFUL,
            "prompt_version": "e6-03-trigger-test-prompt",
            "model_id": "e6-03-trigger-test-model",
        },
    )
    application_session.commit()
    committed_rows.session.rollback()
    flags = [
        row
        for row in moderation_states(committed_rows.session, subjects["answer"])
        if row["state"] == FLAGGED_COLLAPSED and row[DECIDER_COLUMN] is None
    ]
    assert len(flags) == 1, (
        f"A `harmful` verdict routed through the door on `{APPLICATION_ROLE}` left the flags "
        f"{flags}. The definer writes the router's flag with no decider, and the trigger lets "
        "exactly that writer through."
    )


def test_the_bootstrap_identity_is_refused_a_router_row_and_the_definer_is_not(
    db_session: Any, seed_rows: Any, metadata_tables: dict[str, Any]
) -> None:
    """The rule is "unless `current_user` is the definer", not "if it is `pulse_app`".

    One comment, one decider-less flag, two writers: `pulse_moderation_definer` —
    accepted (the control, and the proof that no `CHECK` refuses this row) — and the
    bootstrap superuser — refused.

    **The mutation this kills:** a trigger keyed on `pulse_app`, which lets every
    other role — a seed, a fixture, a later ticket's job — write a flag around the
    door. (`tests/fixtures/supervision.py::fill_a_decider` gives every row the
    seeding walker writes a decider for exactly this reason.)
    """
    require_decision_columns(metadata_tables)
    answer = seed_rows("answer", {}, comment_text="e6-03 a comment the decider trigger is about")
    parameters = {"answer": str(answer["id"])}

    by_the_definer = attempted(
        db_session, A_ROUTER_SHAPED_ROW, parameters, role=MODERATION_DEFINER_ROLE
    )
    assert by_the_definer is None, (
        f"`{MODERATION_DEFINER_ROLE}` was refused a decider-less flag: {by_the_definer} (SQLSTATE "
        f"{sqlstate(by_the_definer)}). The router writes exactly this row; until it is accepted, "
        "the refusal below may be a `CHECK` rather than the trigger."
    )
    by_the_bootstrap = attempted(db_session, A_ROUTER_SHAPED_ROW, parameters)
    assert by_the_bootstrap is not None, (
        "The bootstrap identity inserted a decider-less flag directly. The trigger's rule is "
        f"'unless `current_user` is `{MODERATION_DEFINER_ROLE}`' — every writer but the router "
        "names a decider."
    )
