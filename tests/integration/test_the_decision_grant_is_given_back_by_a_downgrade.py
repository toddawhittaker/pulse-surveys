"""E6-03's migration gives its grant and its columns back on the way down — ticket E6-03, M2.

M2 adds four decision columns to `moderation_state` and, through
`backend/app/views_sql/moderation_decision_grants_v001.sql`, gives `pulse_app`
column-grain `INSERT` on the six columns a decision writes. A migration whose
`downgrade()` drops the columns and forgets the `REVOKE` leaves the application
connection able to insert into `moderation_state`'s two older columns — `answer_id`
and `state` — at a revision whose code has no decision door at all: a flag, a keep
or an exclusion written by nothing that revision describes. That is the shape
`test_the_summary_job_grants_are_given_back_by_a_downgrade.py` exists for one ticket
down, and `docs/MISTAKES.md` entry 9 is why it is executed rather than read.

**Where the journey stops.** E6-03's work order fixes M2's `down_revision` as E6-01's
merged revision, `f14324ab936c`, so that is the revision this steps down to; whatever
sits between it and head is M2 (and nothing of E6-02's, which needs no migration of
its own — `docs/tickets/e6/README.md`).

**Both currencies, and the survivor.** `has_column_privilege` sees the column grant
`has_table_privilege` is blind to (entry 35). E4's `SELECT` on the table belongs to
a revision far below and must survive: a `REVOKE ALL ON moderation_state` passes the
absence half and leaves E4-04's suppression path unable to conceal a flag.

**Which failure a red is, before E6-03 lands:** at head there is no `INSERT` on any
column of `moderation_state`, so the control fails naming it.

Each test migrates a database of its own (`empty_database`), so nothing here
touches the session database (`docs/MISTAKES.md` entry 12).
"""

from typing import Any

import pytest
from fixtures.migration_journey import (
    MODEL_SCHEMA,
    columns_the_database_reports,
    migrate,
    require_revision,
)
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

APPLICATION_ROLE = "pulse_app"
TABLE = "moderation_state"

E6_01_REVISION = "f14324ab936c"
WHAT_THE_REVISION_IS = (
    "E6-01's merged revision, which E6-03's work order fixes as M2's `down_revision`: the "
    "routing definer, `threat_case`, `moderation_attempt` and `moderation_state.sequence`. If the "
    "chain was re-pointed at merge, this constant is the one place to change"
)

# Transcribed, not read from the grants file (`docs/MISTAKES.md` entry 19).
DECISION_COLUMNS = ("decided_by_person_id", "decided_as", "reason", "is_undo")
GRANTED_COLUMNS = ("answer_id", "state", *DECISION_COLUMNS)


def column_inserts_held(database: Any) -> set[str]:
    """Every column of `moderation_state` `pulse_app` may insert into, by any mechanism."""
    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            return {
                column
                for column in columns_the_database_reports(database, TABLE)
                if connection.execute(
                    text("SELECT has_column_privilege(:role, :relation, :column, 'INSERT')"),
                    {"role": APPLICATION_ROLE, "relation": f"public.{TABLE}", "column": column},
                ).scalar_one()
            }
    finally:
        engine.dispose()


def holds_select(database: Any) -> bool:
    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            return bool(
                connection.execute(
                    text("SELECT has_table_privilege(:role, :relation, 'SELECT')"),
                    {"role": APPLICATION_ROLE, "relation": f"public.{TABLE}"},
                ).scalar_one()
            )
    finally:
        engine.dispose()


def test_the_decision_columns_and_their_grant_are_given_back_and_the_read_survives(
    empty_database: Any, alembic_config_pointed_at: Any
) -> None:
    """Head, then `f14324ab936c`, then head again — and what `pulse_app` holds at each.

    At head (the control): `INSERT` on exactly the six granted columns, and
    `SELECT` on the table. After stepping down to E6-01's revision: the four
    decision columns are gone, `pulse_app` holds `INSERT` on **no** column of the
    table, and `SELECT` is still there. Back at head: the six again.

    **The mutations this kills:** `downgrade()` dropping the columns and leaving the
    grant on `answer_id` and `state` (a write path at a revision with no door); a
    blanket `REVOKE ALL` on the table (the read E4 spends is taken with it); and an
    upgrade that cannot re-grant after a round trip.
    """
    config = alembic_config_pointed_at(empty_database)
    require_revision(config, E6_01_REVISION, WHAT_THE_REVISION_IS)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")

    at_head = column_inserts_held(empty_database)
    assert at_head == set(GRANTED_COLUMNS), (
        f"At head `{APPLICATION_ROLE}` may insert into {sorted(at_head)} of `{TABLE}`; E6-03's "
        f"grants file gives exactly {sorted(GRANTED_COLUMNS)}. Until that holds, the absence "
        "asserted after the downgrade is about a grant that never existed."
    )
    assert holds_select(empty_database), f"At head `{APPLICATION_ROLE}` cannot read `{TABLE}`."

    migrate(config, "downgrade", E6_01_REVISION, f"stepping from head down to {E6_01_REVISION}")
    remaining = columns_the_database_reports(empty_database, TABLE)
    assert remaining and not (set(DECISION_COLUMNS) & remaining), (
        f"After the downgrade `{TABLE}` has the columns {sorted(remaining)}; M2's four decision "
        "columns are gone and the table itself is E4-02's, so it stays."
    )
    left = column_inserts_held(empty_database)
    assert not left, (
        f"After the downgrade `{APPLICATION_ROLE}` may still insert into {sorted(left)} of "
        f"`{TABLE}`. M2's `downgrade()` revokes the decision grant; without that, the application connection "
        "can write moderation rows at a revision whose code has no decision door."
    )
    assert holds_select(empty_database), (
        f"The downgrade took `{APPLICATION_ROLE}`'s `SELECT` on `{TABLE}`, which E4-04 granted far "
        "below M2. Revoke what M2 granted, by column, and nothing else."
    )

    migrate(config, "upgrade", MODEL_SCHEMA, "re-applying what the downgrade undid")
    again = column_inserts_held(empty_database)
    assert again == set(
        GRANTED_COLUMNS
    ), f"After the round trip `{APPLICATION_ROLE}` may insert into {sorted(again)} of `{TABLE}`."
