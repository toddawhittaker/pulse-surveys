"""Every statement the database was actually sent, while one call runs.

E2-16 asks two questions that can only be answered by watching the wire. Item 4:
does the floored-comment sweep still send a `NOT IN` anti-join? Item 5: does
window derivation still read once per section? Both are properties of the SQL a
call emits rather than of anything it returns, and neither service exposes its
statements — so this listens where every statement passes, `before_cursor_execute`
on the `Engine` **class**, which covers engines a call builds for itself as well
as the one a test holds.

**It records and decides nothing.** What counts as a read, and which shapes are
refused, are the asking module's subject; this file answers "what was sent", and
the two helpers below are the readings those modules share rather than rules
either of them holds.

**Its own control is
`test_the_statement_recorder_sees_a_statement_it_was_shown`** in
`tests/integration/test_window_derivation_batches_its_reads.py`: a recorder that
saw nothing would make "no `NOT IN` was sent" and "no read was added per section"
both pass against any implementation at all (`docs/MISTAKES.md` entry 3). A red
there means this file is broken, not the service the other module is about.

**The listener is removed in a `finally`.** It is registered on a class, so one
left behind would go on appending to a list from a finished test for the rest of
the session — and the next module's measurement would then include statements
nobody in it issued.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, NamedTuple


class Statement(NamedTuple):
    """One statement as the driver was handed it."""

    sql: str
    executemany: bool


# A `NOT IN` in any of its spellings, as one word-bounded pattern.
#
# **Both forms are refused, and that is the criterion rather than a widening.**
# The measured defect is the anti-join `NOT IN (SELECT …)`, which the planner
# runs as a hashed subplan until the hash outgrows `work_mem` and then rescans
# the inner table once per outer row — 72 seconds at a term's volume. The other
# spelling, a list of identifiers fetched into Python and sent back as
# `NOT IN (:p1, :p2, …)`, is the same anti-join with the unbounded set moved into
# the request instead of the planner. Neither is the shape item 4 asks for, so
# the pattern stops at `NOT IN` and does not look for what follows it.
NOT_IN = re.compile(r"\bNOT\s+IN\b", re.IGNORECASE)

# What a read looks like on the wire. `WITH` is included because a common table
# expression that ends in a `SELECT` is a read written another way, and a
# derivation that batched its reads into one CTE would otherwise be counted as
# having issued none at all.
READ = re.compile(r"^\s*(\(\s*)*(SELECT|WITH)\b", re.IGNORECASE)


@contextmanager
def statements_recorded() -> Iterator[list[Statement]]:
    """Every statement sent to any engine while the block runs, in order."""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    recorded: list[Statement] = []

    def record(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        recorded.append(Statement(str(statement), bool(executemany)))

    event.listen(Engine, "before_cursor_execute", record)
    try:
        yield recorded
    finally:
        event.remove(Engine, "before_cursor_execute", record)


def reads(recorded: list[Statement]) -> list[Statement]:
    """The recorded statements that are reads — the ones a per-row loop multiplies."""
    return [statement for statement in recorded if READ.match(statement.sql)]


def anti_joins(recorded: list[Statement]) -> list[Statement]:
    """The recorded statements carrying a `NOT IN`. See `NOT_IN` for both spellings."""
    return [statement for statement in recorded if NOT_IN.search(statement.sql)]
