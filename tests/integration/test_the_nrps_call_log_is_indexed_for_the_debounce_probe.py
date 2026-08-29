"""`nrps_call` is indexed the way the debounce probe reads it — the boundary review's M5.

`docs/tickets/e1/boundary-review.md`: "**M5 — `nrps_call` indexed on `section_id`
alone** (`models/lti.py:1121`). Measured at a million rows laid out hour-major:
2,006 buffers per staff-launch debounce probe against 5 with `(section_id,
called_at DESC)`, growing all term with no purge until E13."

`boundary-fix-plan.md`, batch A item 3: "A migration adds an index on `nrps_call
(section_id, called_at DESC)`; `alembic check` clean; the downgrade drops exactly
it."

**What this module asserts and what it leaves to the gates that already exist.**
The index is asserted here, against the migrated database, by reading the
catalog — because that is the only place an index a migration created actually
exists, and a declaration on `Base.metadata` that no migration ran is reachable
from nowhere a deployment can see. That `alembic check` is clean is *not* asserted
here: `tests/integration/test_alembic_baseline.py` runs `command.check` against a
freshly upgraded database and is where drift between the declaration and the
migration is diagnosed, for every ticket. Two tests of one rule is
`docs/MISTAKES.md` entry 19's shape.

**The reach of the test below, stated exactly, because it is narrower than it
reads.** It answers one question: does an index with these key columns, in this
order, with this direction, exist. It does **not** notice a superseded index left
behind beside it — the `section_id`-only index this one replaces, still there,
still costing every write — because an extra index is not an absent one. That is
`test_alembic_baseline.py`'s catch, through the drift `alembic check` reports
between `Base.metadata` and the database, and it is named here rather than left
for a reader to assume this module covers it (`docs/MISTAKES.md` entry 14: the
boundary of a search said out loud rather than left looking like coverage).

**Column order and sort direction are the whole point, so both are read.** An index
on `section_id` alone is what exists today and is what the measurement condemns; an
index on `(called_at, section_id)` is the same two columns in the order that does
not answer the probe; an ascending `(section_id, called_at)` makes the planner walk
to the oldest row of a section to find its newest. All three are indexes on the
right table over the right columns, and none of them is this criterion — so the
reader below reports each key column's position *and* its descending flag, and the
control proves it can tell those cases apart before anything is asserted with it.
"""

from typing import Any

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

# `roster_contract` and `roster_rows` come from `tests/fixtures/roster_sync.py`,
# `migrated_engine` from `tests/fixtures/database.py`. Reached as fixtures rather
# than imported, for the reason every module in this suite gives.

# Every key column of every index on one table, in order, with its sort direction.
#
# Read from the catalog rather than from a definition string, because what is being
# asserted is a pair of facts about each key column — its position and whether it is
# stored descending — and `pg_get_indexdef` answers them only as prose that has to be
# parsed. `indoption`'s low bit is `INDOPTION_DESC` (`src/include/catalog/pg_index.h`).
# `indkey` and `indoption` are `int2vector`s, whose subscripts start at 0, which is
# why the positions generated from 1 are read one lower. Only key columns are
# considered — `indnkeyatts` is where they stop and any `INCLUDE` payload begins — so
# an index that carries extra non-key columns still answers this question the same way.
INDEX_KEY_COLUMNS = text(
    """
    SELECT i.relname AS index_name,
           s.position AS position,
           a.attname AS column_name,
           (ix.indoption[s.position - 1] & 1) = 1 AS descending
    FROM pg_class AS t
    JOIN pg_index AS ix ON ix.indrelid = t.oid
    JOIN pg_class AS i ON i.oid = ix.indexrelid
    JOIN LATERAL generate_series(1, ix.indnkeyatts) AS s(position) ON TRUE
    JOIN pg_attribute AS a ON a.attrelid = t.oid AND a.attnum = ix.indkey[s.position - 1]
    WHERE t.relname = :table
    ORDER BY i.relname, s.position
    """
)

# The two tables and two indexes the control builds. Temporary, and created inside
# the transaction that reads them: `ON COMMIT DROP` is what keeps a pooled
# connection from carrying them into another test's session
# (`docs/MISTAKES.md` entry 39's neighbourhood — a run that leaves the tree, or the
# database, other than it found it).
PROBE_TABLE = "e1_boundary_index_probe"
PROBE_DESCENDING_INDEX = "e1_boundary_probe_leading_then_trailing_desc"
PROBE_REVERSED_INDEX = "e1_boundary_probe_trailing_then_leading"


def index_key_columns(connection: Any, table: str) -> dict[str, list[tuple[str, bool]]]:
    """Each index on `table`, as its key columns in order with their descending flags."""
    found: dict[str, list[tuple[str, bool]]] = {}
    for row in connection.execute(INDEX_KEY_COLUMNS, {"table": table}).mappings():
        found.setdefault(row["index_name"], []).append(
            (str(row["column_name"]), bool(row["descending"]))
        )
    return found


# ---------------------------------------------------------------------------
# The control. **A red here means this test is broken, not the schema.**
# ---------------------------------------------------------------------------


def test_the_index_reader_reports_column_order_and_the_descending_flag(
    migrated_engine: Any,
) -> None:
    """The reader is run against two indexes whose difference is exactly what is asserted.

    The assertion below is "an index over these two columns, in this order, with the
    second one descending". A reader that dropped the order, or that reported every
    column as ascending, would answer that question wrongly in one direction or the
    other and there would be no way to tell from a green.

    So two indexes are built here over one temporary table: `(first, second DESC)`
    and `(second, first)`. The reader has to report them as different — different
    column order, and a descending flag on exactly one column of one of them. Those
    are the two near misses the criterion is written against, in the instrument
    rather than in the schema.

    **A red here means this test is broken, not the schema.**
    """
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE TEMP TABLE {PROBE_TABLE} "
                "(first_column integer, second_column integer) ON COMMIT DROP"
            )
        )
        connection.execute(
            text(
                f"CREATE INDEX {PROBE_DESCENDING_INDEX} ON {PROBE_TABLE} "
                "(first_column, second_column DESC)"
            )
        )
        connection.execute(
            text(
                f"CREATE INDEX {PROBE_REVERSED_INDEX} ON {PROBE_TABLE} "
                "(second_column, first_column)"
            )
        )

        read = index_key_columns(connection, PROBE_TABLE)

    assert read.get(PROBE_DESCENDING_INDEX) == [("first_column", False), ("second_column", True)], (
        f"The reader read `{PROBE_DESCENDING_INDEX}` as {read.get(PROBE_DESCENDING_INDEX)!r}, and "
        "it was created as `(first_column, second_column DESC)`. Every assertion that an index is "
        "ordered and descending rests on this reading; with it wrong, the criterion below is "
        "either unsatisfiable or satisfied by an index nobody asked for. Everything it read: "
        f"{read!r}."
    )
    assert read.get(PROBE_REVERSED_INDEX) == [("second_column", False), ("first_column", False)], (
        f"The reader read `{PROBE_REVERSED_INDEX}` as {read.get(PROBE_REVERSED_INDEX)!r}, and it "
        "was created as `(second_column, first_column)` — the same two columns in the other order, "
        "both ascending. If the reader cannot tell that from the index above, then the near miss "
        "the criterion below is written against is invisible to it."
    )


# ---------------------------------------------------------------------------
# M5 — the index the debounce probe reads.
# ---------------------------------------------------------------------------


def test_nrps_call_carries_an_index_on_section_id_and_called_at_descending(
    migrated_engine: Any, roster_rows: Any, roster_contract: Any
) -> None:
    """M5: the debounce probe's own access path exists in the migrated database.

    D9 makes `nrps_call` the row a staff launch's debounce reads — "skips the
    enqueue when the section has an `nrps_call` row younger than 5 minutes" — which
    is the newest row for one section, and it is read on the request path of every
    staff launch. The review measured what that costs against the index that exists
    today: 2,006 buffers per probe at a million rows laid out hour-major, against 5.

    **The mutation this kills**: leaving the index on `section_id` alone. The probe
    still answers, every other test stays green, and the cost grows all term because
    nothing purges the table until E13.

    **The two near misses this is written around, and both are in the assertion
    rather than in the prose.** `(called_at, section_id)` is the same two columns in
    the order that makes the leading column the one the probe does not filter on. An
    *ascending* `(section_id, called_at)` puts the section's oldest call first, so
    the newest — the one the debounce wants — is at the far end of its range. Column
    order and the descending flag are therefore both compared, and the control above
    is what says the reader can see either of them being wrong.

    The columns are followed rather than spelled: `section_id` is named by the
    foreign key `nrps_call` carries to `section`, for the reason `RosterRows.link`
    gives — a column name guessed right is a column name that will one day be
    guessed wrong, silently.

    Reflected rather than declared, because a declaration no migration created
    exists nowhere a deployment can reach.
    """
    table = roster_contract.nrps_call_table
    section_column = roster_rows.link(table, "section")
    wanted = [(section_column, False), (roster_contract.called_at_column, True)]

    with migrated_engine.connect() as connection:
        read = index_key_columns(connection, table)

    assert read, (
        f"The catalog reports no index at all on `{table}`, not even a primary key's. Either the "
        "table is not there — D9 creates it and `test_the_roster_sync_is_discovered_and_debounced"
        ".py` is where its absence is diagnosed — or this reader is looking somewhere the migrated "
        "schema is not, and the assertion below would be about nothing."
    )
    assert any(columns == wanted for columns in read.values()), (
        f"No index on `{table}` has key columns {wanted!r}. The indexes it carries are {read!r}, "
        "each as `(column, descending)` in key order.\n\n"
        f"The debounce reads the newest `{roster_contract.called_at_column}` for one "
        f"`{section_column}`, on the request path of every staff launch: measured at a million "
        "rows laid out hour-major, 2,006 buffers per probe on `section_id` alone against 5 on "
        "`(section_id, called_at DESC)`, and the table grows all term because nothing purges it "
        "until E13.\n\n"
        f"An index on `{section_column}` alone does not satisfy this, and neither does "
        f"`({roster_contract.called_at_column}, {section_column})` nor an ascending pair — the "
        "column order and the direction are the criterion."
    )
