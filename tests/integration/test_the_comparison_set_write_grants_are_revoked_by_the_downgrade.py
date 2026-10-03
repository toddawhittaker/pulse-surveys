"""The write grants come back off again, and take nothing else with them — E5-06.

Work-order decision 6 ends with one sentence: "Downgrade revokes exactly those
verbs." Nothing else in this repository asserts it, and a grants migration whose
`downgrade` is `pass` is the shape that ships unnoticed — every test about the
*upgrade* stays green, and the revocation is a line of prose
(`docs/MISTAKES.md` entry 2).

**"Exactly those verbs" is the assertion, and it has two halves.** After the
step that takes the writes away, `INSERT` on `comparison_set` must be refused
for want of the privilege — and `SELECT` must still be held, because it is
E5-04's grant sitting below this revision and a downgrade that revoked it would
leave a database one step back from head unable to resolve a named set at all.

**The walk is bounded by the history rather than by a number.** Which revision
carries these grants is not known to this module — it does not exist yet when
this is written, and naming it would pin the test to an identifier a rebase can
move. So the database is walked down one revision at a time until the privilege
is gone, at most as many steps as the script directory holds revisions
(`tests/fixtures/migration_journey.py::most_steps_a_walk_down_may_take`, whose
docstring carries the incident that made the bound derived rather than
hand-written: `docs/disputes/E5-01-02.md`).

**The stop condition is guarded, because two different things can end this
walk.** Far enough down, E5-01's own revision drops the table, and a statement
against a table that is not there is refused too — with `42P01`, for a reason
that has nothing to do with a grant. So the walk requires the table to still be
in the catalog at the step where the privilege went; a walk that ran past it
reports that, rather than reporting a revocation that never happened.

**On a throwaway database, walked back up afterwards.** `empty_database` is a
second database in the session's container, dropped when the test ends, so no
other module meets a half-migrated schema — and the re-upgrade at the end is
what says the pair is a round trip rather than a one-way door.

**Which failure a red here is, before E5-06's migration lands.** The control at
the top fails first, naming the grants file: on a tree where the writes were
never granted there is no revocation to walk towards, and this module says so in
one sentence rather than walking the whole history to say it.
"""

from typing import Any

import pytest
from fixtures.comparison_sets import (
    COMPARISON_SET_TABLE,
    INSUFFICIENT_PRIVILEGE,
    a_write_of,
    refusal_of_statement,
)
from fixtures.migration_journey import (
    MODEL_SCHEMA,
    migrate,
    most_steps_a_walk_down_may_take,
)
from fixtures.supervision import sqlstate_of
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

# The verb E5-06 grants and the verb E5-04 granted below it. The first must go
# on the way down and the second must stay.
THE_WRITE = "INSERT"
THE_READ = "SELECT"

ONE_STEP_DOWN = "-1"

RELATION_EXISTS = text("SELECT to_regclass(:relation) IS NOT NULL")


def state_of(engine: Any, verb: str, tables: dict[str, Any]) -> str | None:
    """The SQLSTATE `verb` on `comparison_set` is refused with, or `None` if it ran.

    `None` and `23502` both mean the privilege is held — Postgres consults the
    grant before it evaluates a constraint — and only `42501` means it is not.
    """
    refused = refusal_of_statement(engine, a_write_of(verb, COMPARISON_SET_TABLE, tables))
    return None if refused is None else sqlstate_of(refused)


def table_is_there(engine: Any) -> bool:
    """Whether `public.comparison_set` is still in the catalog."""
    with engine.connect() as connection:
        return bool(
            connection.execute(
                RELATION_EXISTS, {"relation": f"public.{COMPARISON_SET_TABLE}"}
            ).scalar()
        )


def test_the_downgrade_takes_the_write_verbs_away_and_leaves_the_read(
    empty_database: Any, alembic_config_pointed_at: Any, metadata_tables: dict[str, Any]
) -> None:
    """The revocation, walked to rather than named, with the read asserted beside it.

    **The mutations this kills:** a `downgrade` that does nothing, which leaves a
    database one revision below head holding privileges its schema no longer
    describes — and which makes the whole versioned-grants shape a convention
    rather than a mechanism; a `downgrade` written as `REVOKE ALL ON
    comparison_set FROM pulse_app`, which is one word shorter than the right
    revoke and takes E5-04's read with it, breaking every benchmark on a stack
    that has rolled back one step; and a revoke naming only one of the two
    tables, which this walk sees as the write surviving on the other.

    **The near miss it must not pass on:** the walk reaching E5-01's revision,
    where the table is dropped. That refuses the statement too, with `42P01`, so
    the stop condition requires both the privilege to be gone *and* the table to
    still be there.

    **Expected red before E5-06's migration lands:** the control assertion
    below, naming `comparison_set_write_grants_v001.sql`.
    """
    config = alembic_config_pointed_at(empty_database)
    engine = create_engine(empty_database.application_url)
    try:
        migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")

        assert state_of(engine, THE_WRITE, metadata_tables) != INSUFFICIENT_PRIVILEGE, (
            f"At head, `pulse_app` is refused {THE_WRITE} on `{COMPARISON_SET_TABLE}` for want of "
            "the privilege, so there is no revocation for this walk to find. E5-06's decision 6 "
            "ships `backend/app/views_sql/comparison_set_write_grants_v001.sql` and a migration "
            "that executes it; without the grant, a downgrade that revokes nothing is "
            "indistinguishable from one that works."
        )

        bound = most_steps_a_walk_down_may_take(config)
        taken = 0
        while taken < bound and state_of(engine, THE_WRITE, metadata_tables) != (
            INSUFFICIENT_PRIVILEGE
        ):
            migrate(config, "downgrade", ONE_STEP_DOWN, f"walking down, step {taken + 1}")
            taken += 1

        assert state_of(engine, THE_WRITE, metadata_tables) == INSUFFICIENT_PRIVILEGE, (
            f"After {taken} downgrade step(s) — the whole history, which is {bound} revisions — "
            f"`pulse_app` still holds {THE_WRITE} on `{COMPARISON_SET_TABLE}`. Every revision in "
            "this tree has been undone and the privilege is still there, so the grant is being "
            "made by a migration whose `downgrade` does not take it back."
        )
        assert table_is_there(engine), (
            f"The walk stopped after {taken} step(s) because `public.{COMPARISON_SET_TABLE}` is no "
            "longer in the catalog — it walked past E5-01's own revision, which drops the table. A "
            "statement against a table that is not there is refused for a reason that has nothing "
            "to do with a grant, so this is a downgrade that never revoked anything rather than "
            "one that did."
        )
        assert state_of(engine, THE_READ, metadata_tables) != INSUFFICIENT_PRIVILEGE, (
            f"The step that revoked {THE_WRITE} revoked {THE_READ} as well. E5-04's grant sits "
            "below this revision and is not E5-06's to take: a `REVOKE ALL` on the way down leaves "
            "a database one step behind head unable to resolve a named set at all, which is a "
            "benchmark that disappears rather than a write that is refused."
        )

        migrate(config, "upgrade", MODEL_SCHEMA, "walking back up to the models' schema")
        assert state_of(engine, THE_WRITE, metadata_tables) != INSUFFICIENT_PRIVILEGE, (
            f"After walking back up, `pulse_app` is still refused {THE_WRITE}. The pair is a round "
            "trip: an operator who rolls back and forward again has a working application, and a "
            "grant that only survives the first upgrade does not give them one."
        )
    finally:
        engine.dispose()
