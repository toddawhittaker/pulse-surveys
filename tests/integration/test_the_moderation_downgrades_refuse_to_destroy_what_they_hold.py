"""E6's two migrations refuse a downgrade that would destroy their data — E6-09, done-when 1.

> `e403cc44bfc0`'s downgrade raises `RuntimeError` when any `moderation_state` row
> has a decider. `f14324ab936c`'s raises when `threat_case` or `moderation_state`
> holds a row. … The precedent is `20260904_a7c2f4e18b30`. A data-bearing
> round-trip test on an `empty_database` proves each refusal, and an empty round
> trip still passes.

**What each downgrade would destroy.** `e403cc44bfc0` drops the four decision
columns, so a row naming its decider loses who decided, under which role, why, and
whether it undid something — the exclusion log's whole record (SPEC §8: "there is
no separate exclusion table"). `f14324ab936c` drops `threat_case`, the row a Care
case opens with, and `moderation_state.sequence`, the only order two decisions
written in one transaction have. Below each revision there is nowhere to put any of
it, so the precedent's answer applies: what a downgrade cannot keep it refuses to
lose, and says so (`a7c2f4e18b30`'s guard, which raises `RuntimeError` before it
touches anything).

**Each refusal is asserted three ways**: the downgrade raises, the error is a
`RuntimeError` (the precedent's type, so a SQL error a half-built downgrade trips
over does not pass for a refusal), and the row is still there afterwards — a guard
that raised after dropping the column would satisfy the first two.

**Where each row is planted.** `seed_row` writes through today's models, so it can
only seed at head (`tests/fixtures/supervision.py::seed_row`). A decided
`moderation_state` row and a `threat_case` row are seeded at head. A router-shaped
`moderation_state` row — no decider — is refused at head by `e403cc44bfc0`'s
trigger for any writer but the routing definer, so it is written by plain SQL while
the database stands at `f14324ab936c`, where that trigger does not exist yet.

**The empty round trip is the control**: the same walk over a database holding no
such rows completes in both directions, so a downgrade that refused everything is
red there.

**Which failure a red is, before E6-09 lands.** Each refusal test fails on the
assertion that the downgrade raised: today both downgrades complete and drop the
rows. The empty round trip is green today and must stay green.

Each test migrates a throwaway database (`empty_database`), so nothing here touches
the session database (`docs/MISTAKES.md` entry 12).
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from fixtures.migration_journey import (
    MODEL_SCHEMA,
    columns_the_database_reports,
    migrate,
    require_revision,
    session_on,
    the_revision_below,
)
from fixtures.supervision import require_table, seed_row, single_primary_key
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

DECISIONS_REVISION = "e403cc44bfc0"
ROUTING_REVISION = "f14324ab936c"
WHAT_THE_DECISIONS_REVISION_IS = (
    "E6-03's revision: the decision columns on `moderation_state`, their grant and the "
    "router-rows trigger. If the chain was re-pointed, this constant is the one place to change"
)
WHAT_THE_ROUTING_REVISION_IS = (
    "E6-01's revision: `threat_case`, `moderation_attempt`, `moderation_state.sequence` and the "
    "routing definer. If the chain was re-pointed, this constant is the one place to change"
)

MODERATION_STATE = "moderation_state"
THREAT_CASE = "threat_case"
CLASSIFICATION = "classification"
ANSWER = "answer"
QUESTION = "question"
# SPEC §3.2's instructor comment question, by kind and ordinal.
COMMENT_KIND = "comment"
COMMENT_POSITION = 2
DECIDER_COLUMN = "decided_by_person_id"
SEQUENCE_COLUMN = "sequence"

# A validity verdict, so the `threat_case` row has a classification to name without
# going through the moderation definer, whose trigger refuses a `MODERATION` row
# written any other way. `threat_case` constrains nothing about the task it names.
VALIDITY_TASK = "COMMENT_VALIDITY"
SUBSTANTIVE = "substantive"

A_ROUTER_FLAG = (
    "INSERT INTO public.moderation_state (answer_id, state) "
    "VALUES (CAST(:answer AS uuid), 'FLAGGED_COLLAPSED')"
)


def count(database: Any, statement: str) -> int:
    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            return int(connection.execute(text(statement)).scalar_one())
    finally:
        engine.dispose()


COUNT_DECIDED = (
    "SELECT count(*) FROM public.moderation_state WHERE decided_by_person_id IS NOT NULL"
)
COUNT_MODERATION_STATE = "SELECT count(*) FROM public.moderation_state"
COUNT_THREAT_CASES = "SELECT count(*) FROM public.threat_case"
COUNT_MODERATION_ATTEMPTS = "SELECT count(*) FROM public.moderation_attempt"
MODERATION_ATTEMPT = "moderation_attempt"


def moderation_attempts(database: Any) -> int:
    return count(database, COUNT_MODERATION_ATTEMPTS)


def decided_rows(database: Any) -> int:
    return count(database, COUNT_DECIDED)


def moderation_rows(database: Any) -> int:
    return count(database, COUNT_MODERATION_STATE)


def threat_cases(database: Any) -> int:
    return count(database, COUNT_THREAT_CASES)


def a_comment_answer(session: Any, tables: dict[str, Any], chain: dict[str, Any]) -> Any:
    """One `answer` holding exactly one value, a comment, on a comment-kind question.

    `ck_answer_holds_exactly_one_value` refuses an answer with no value, which is
    what `seed_row` writes when nothing is named. The question is seeded first in
    the same chain so the answer links to it; later seeds in the chain reuse both.
    """
    seed_row(session, tables, QUESTION, chain, kind=COMMENT_KIND, position=COMMENT_POSITION)
    return seed_row(
        session, tables, ANSWER, chain, comment_text="E6-09 a comment a downgrade must not lose"
    )


def refused(config: Any, revision: str) -> BaseException | None:
    """Run `alembic downgrade revision`; answer what it raised, or `None` if it completed."""
    from alembic import command

    try:
        command.downgrade(config, revision)
    except Exception as refusal:
        return refusal
    return None


def is_a_runtime_error(failure: BaseException | None) -> bool:
    """Whether `failure`, or anything it was raised from, is a `RuntimeError`.

    The chain is walked because a migration environment may re-raise; what
    matters is that the guard's own `RuntimeError` is the cause, not a SQL error.
    """
    seen: set[int] = set()
    while failure is not None and id(failure) not in seen:
        if isinstance(failure, RuntimeError):
            return True
        seen.add(id(failure))
        failure = failure.__cause__ or failure.__context__
    return False


def test_the_decision_revision_refuses_to_drop_a_row_that_names_its_decider(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """`e403cc44bfc0` down, over one decided `moderation_state` row: `RuntimeError`, row intact.

    One row, seeded at head through `seed_row`, which names a decider and the
    `INSTRUCTOR` role on every `moderation_state` row it writes. The downgrade to
    `f14324ab936c` must raise `RuntimeError`, and afterwards the row must still be
    there with its decider column.

    **The mutation this kills:** the shipped downgrade, which drops
    `decided_by_person_id`, `decided_as`, `reason` and `is_undo` over the row and
    completes. **The near miss:** a guard that raises *after* dropping the columns
    (the row's decider is gone, so the last assertion is red), and a downgrade
    that fails on some SQL error of its own (not a `RuntimeError`).
    """
    config = alembic_config_pointed_at(empty_database)
    require_revision(config, DECISIONS_REVISION, WHAT_THE_DECISIONS_REVISION_IS)
    require_revision(config, ROUTING_REVISION, WHAT_THE_ROUTING_REVISION_IS)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")

    with session_on(empty_database) as session:
        chain: dict[str, Any] = {}
        a_comment_answer(session, metadata_tables, chain)
        # A keep with no reason: a decision state every `CHECK` accepts with a decider.
        seed_row(session, metadata_tables, MODERATION_STATE, chain, state="KEPT")
    assert decided_rows(empty_database) == 1, (
        "The seeded `moderation_state` row does not name a decider, so this test is not about the "
        "data the refusal protects. `seed_row` names one on every such row it writes."
    )

    failure = refused(config, the_revision_below(config, DECISIONS_REVISION))
    assert failure is not None, (
        f"`alembic downgrade` below {DECISIONS_REVISION} completed over a `moderation_state` row "
        "naming its decider. That drops who decided, under which role, why, and whether it was an "
        "undo — the exclusion log's record. E6-09 done-when 1: the downgrade raises instead."
    )
    assert is_a_runtime_error(failure), (
        f"The downgrade failed with {failure!r}, not a `RuntimeError`. The precedent "
        "(`a7c2f4e18b30`) refuses with a `RuntimeError` naming what would be lost; any other "
        "error is a downgrade that broke, not one that refused."
    )
    assert DECIDER_COLUMN in columns_the_database_reports(empty_database, MODERATION_STATE), (
        f"After the refusal `{MODERATION_STATE}` has no `{DECIDER_COLUMN}`: the guard raised after "
        "the columns were dropped."
    )
    assert decided_rows(empty_database) == 1, "After the refusal the decided row is gone."


def test_the_routing_revision_refuses_to_drop_a_threat_case(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """`f14324ab936c` down, over one `threat_case` row: `RuntimeError`, the case intact.

    The row is seeded at head with no `moderation_state` row anywhere, so
    `e403cc44bfc0`'s own guard has nothing to refuse and the walk reaches
    `f14324ab936c`, which must raise.

    **The mutation this kills:** the shipped downgrade, which drops `threat_case`
    and with it the only record that a Care case opened (SPEC §6.2). **The near
    miss:** a guard that counts `moderation_state` only, which this row does not
    trip.
    """
    config = alembic_config_pointed_at(empty_database)
    require_revision(config, ROUTING_REVISION, WHAT_THE_ROUTING_REVISION_IS)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")

    with session_on(empty_database) as session:
        chain: dict[str, Any] = {}
        a_comment_answer(session, metadata_tables, chain)
        seed_row(
            session,
            metadata_tables,
            CLASSIFICATION,
            chain,
            task=VALIDITY_TASK,
            verdict=SUBSTANTIVE,
            classified_at=datetime.now(UTC),
        )
        seed_row(session, metadata_tables, THREAT_CASE, chain)
    assert threat_cases(empty_database) == 1, "The planted `threat_case` row is not there."
    assert moderation_rows(empty_database) == 0, (
        "A `moderation_state` row exists, so a refusal below could be the decision revision's "
        "rather than this one's."
    )

    failure = refused(config, the_revision_below(config, ROUTING_REVISION))
    assert failure is not None, (
        f"`alembic downgrade` below {ROUTING_REVISION} completed over a `threat_case` row, which "
        "drops the row a Care case opens with. E6-09 done-when 1: the downgrade raises instead."
    )
    assert is_a_runtime_error(
        failure
    ), f"The downgrade failed with {failure!r}, not the precedent's `RuntimeError`."
    assert threat_cases(empty_database) == 1, "After the refusal the `threat_case` row is gone."


def test_the_routing_revision_refuses_to_drop_a_moderation_attempt(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """`f14324ab936c` down, over one `moderation_attempt` row alone: `RuntimeError`, row intact.

    The revision creates `moderation_attempt`, one row per failed moderation call,
    which the attempt cap counts (ADR 0188). Dropping it on the way down loses
    those rows, so a comment at the cap starts counting again from nothing. The
    database holds no `moderation_state` and no `threat_case` row, so only this
    table can make the guard refuse.

    **The mutation this kills:** `moderation_attempt` left out of the tables the
    guard counts, so the downgrade drops it and completes. **The near miss:** the
    other two `f14324ab936c` refusals in this module plant a `threat_case` or a
    `moderation_state` row, which the guard counted before this fix, so neither
    goes red under that mutation; only this test does.
    """
    config = alembic_config_pointed_at(empty_database)
    require_revision(config, ROUTING_REVISION, WHAT_THE_ROUTING_REVISION_IS)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")

    with session_on(empty_database) as session:
        chain: dict[str, Any] = {}
        a_comment_answer(session, metadata_tables, chain)
        seed_row(session, metadata_tables, MODERATION_ATTEMPT, chain)
    assert moderation_attempts(empty_database) == 1, "The planted attempt row is not there."
    assert moderation_rows(empty_database) == 0 and threat_cases(empty_database) == 0, (
        "A `moderation_state` or `threat_case` row exists, so a refusal below could be about that "
        "row rather than the attempt."
    )

    failure = refused(config, the_revision_below(config, ROUTING_REVISION))
    assert failure is not None, (
        f"`alembic downgrade` below {ROUTING_REVISION} completed over a `moderation_attempt` row, "
        "which drops the record the attempt cap counts. E6-09's fix round: the downgrade raises."
    )
    assert is_a_runtime_error(
        failure
    ), f"The downgrade failed with {failure!r}, not the precedent's `RuntimeError`."
    assert moderation_attempts(empty_database) == 1, "After the refusal the attempt row is gone."


def test_the_routing_revision_refuses_to_drop_a_router_flag(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """`f14324ab936c` down, over one router-shaped `moderation_state` row: refused, row intact.

    The row has no decider, so `e403cc44bfc0`'s guard would let it through; it is
    written while the database stands at `f14324ab936c` (see the module
    docstring). The downgrade below `f14324ab936c` must raise `RuntimeError`, and
    the row and its `sequence` must still be there.

    **The mutation this kills:** the shipped downgrade, which drops
    `moderation_state.sequence` — the only order two decisions in one transaction
    have. **The near miss:** a guard that counts only decided rows, which is
    `e403cc44bfc0`'s rule and not this revision's.
    """
    config = alembic_config_pointed_at(empty_database)
    require_revision(config, DECISIONS_REVISION, WHAT_THE_DECISIONS_REVISION_IS)
    require_revision(config, ROUTING_REVISION, WHAT_THE_ROUTING_REVISION_IS)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")

    with session_on(empty_database) as session:
        answer = a_comment_answer(session, metadata_tables, {})
    answer_id = str(answer[single_primary_key(require_table(metadata_tables, ANSWER))])

    migrate(config, "downgrade", ROUTING_REVISION, "stepping down to E6-01's revision, empty")
    engine = create_engine(empty_database.superuser_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(A_ROUTER_FLAG), {"answer": answer_id})
    finally:
        engine.dispose()
    assert moderation_rows(empty_database) == 1, "The router-shaped row was not written."

    failure = refused(config, the_revision_below(config, ROUTING_REVISION))
    assert failure is not None, (
        f"`alembic downgrade` below {ROUTING_REVISION} completed over a `moderation_state` row, "
        "dropping its `sequence`. E6-09 done-when 1: the downgrade raises instead."
    )
    assert is_a_runtime_error(
        failure
    ), f"The downgrade failed with {failure!r}, not the precedent's `RuntimeError`."
    assert SEQUENCE_COLUMN in columns_the_database_reports(empty_database, MODERATION_STATE), (
        f"After the refusal `{MODERATION_STATE}` has no `{SEQUENCE_COLUMN}`: the guard raised after "
        "the column was dropped."
    )
    assert moderation_rows(empty_database) == 1, "After the refusal the router's row is gone."


def test_both_revisions_still_round_trip_over_a_database_holding_none_of_their_rows(
    empty_database: Any, alembic_config_pointed_at: Any
) -> None:
    """The control: head, below `f14324ab936c`, head again — over no rows — completes.

    **The mutation this kills:** a guard that refuses unconditionally (or counts
    a table that is never empty), which makes every downgrade impossible. **The
    middle of the trip is asserted** — `threat_case` is gone below the routing
    revision — so a downgrade that did nothing is not mistaken for one that
    passed.
    """
    config = alembic_config_pointed_at(empty_database)
    require_revision(config, ROUTING_REVISION, WHAT_THE_ROUTING_REVISION_IS)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    assert columns_the_database_reports(empty_database, THREAT_CASE), "No `threat_case` at head."

    below = the_revision_below(config, ROUTING_REVISION)
    migrate(config, "downgrade", below, f"walking an empty database below {ROUTING_REVISION}")
    assert not columns_the_database_reports(
        empty_database, THREAT_CASE
    ), f"Below {ROUTING_REVISION} `threat_case` is still there, so the downgrade did not run."

    migrate(config, "upgrade", MODEL_SCHEMA, "re-applying both revisions")
    assert DECIDER_COLUMN in columns_the_database_reports(
        empty_database, MODERATION_STATE
    ), "After the round trip the decision columns are not back."
