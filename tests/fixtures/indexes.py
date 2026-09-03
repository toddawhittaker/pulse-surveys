"""What indexes a migrated table actually carries, read from the catalog.

**One reader, because two tickets now ask the same question.** E2-02's
`tests/integration/test_the_nrps_call_log_is_indexed_for_the_debounce_probe.py`
wrote it for the debounce probe's composite; E2-16 asks it of three more indexes
— the sweep's `(task, prompt_version)` support and the two week-axis indexes the
ticket's item 6 rules are kept. A second copy is `docs/MISTAKES.md` entry 13's
shape exactly, so the query and its reader moved here and that module imports
them.

**Nothing here asserts anything.** It answers what the catalog says; which
indexes a table is required to carry is the subject of the module that asks, and
a helper that decided it would be a second place the criterion lives.

**The control on this reader is
`test_the_index_reader_reports_column_order_and_the_descending_flag`**, in the
module the query came from: two temporary indexes over one table, differing in
column order and in one descending flag, both read back. A red there means this
reader is broken and every assertion resting on it is measuring nothing.
"""

from typing import Any

from sqlalchemy import text

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


def index_key_columns(connection: Any, table: str) -> dict[str, list[tuple[str, bool]]]:
    """Each index on `table`, as its key columns in order with their descending flags."""
    found: dict[str, list[tuple[str, bool]]] = {}
    for row in connection.execute(INDEX_KEY_COLUMNS, {"table": table}).mappings():
        found.setdefault(row["index_name"], []).append(
            (str(row["column_name"]), bool(row["descending"]))
        )
    return found


def indexes_leading_with(
    read: dict[str, list[tuple[str, bool]]], columns: tuple[str, ...]
) -> dict[str, list[tuple[str, bool]]]:
    """The indexes in `read` whose first key columns are exactly `columns`, in any order.

    **Leading rather than whole**, because an index that carries more key columns
    after these still answers a lookup on them; and **order-free among the
    leading columns**, because `(a, b)` and `(b, a)` both serve an equality
    lookup on both. Neither tolerance is a guess about the implementation: a
    criterion that says "indexed on these columns" is satisfied by either
    spelling, and pinning one would make this file the place the choice was made
    rather than the ticket.

    What it does **not** tolerate is a different leading column — an index on
    `(a)` alone, or on `(c, a, b)` — because that is the index that does not
    answer the lookup, which is the whole distinction E2-02's own criterion turns
    on.
    """
    width = len(columns)
    return {
        name: keys
        for name, keys in read.items()
        if len(keys) >= width and {column for column, _ in keys[:width]} == set(columns)
    }
