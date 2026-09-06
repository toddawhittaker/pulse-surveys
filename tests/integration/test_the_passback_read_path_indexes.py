"""The two indexes the passback's own read paths need — E3-08's boundary round, DM-H1 and DM-M1.

Two findings from the data-model review, both facts about the migrated catalog,
so they are asserted against it together and each in its own test because each
fails for its own reason.

**DM-H1 — `ags_call (section_id, called_at)`.** E3-02's call log is at SPEC
§6.1's grain of one HTTP call to a platform service, and the sweep reads it: once
per delivery, for the latest row of the section it is about. Until this index the
only thing on that table was its primary key, so every one of those reads is a
sequential scan of a table that grows by a row per student per week for every
section in the deployment and is never purged before E13. It is the same shape,
on the same kind of table, as the finding E1's boundary review recorded as M5 for
`nrps_call` — "2,006 buffers per staff-launch debounce probe against 5" — and
`tests/integration/test_the_nrps_call_log_is_indexed_for_the_debounce_probe.py`
is that one's test. This is its sibling, and the two are worth reading together.

**DM-M1 — `section.term_id`.** The sweep walks sections whose term has not yet
ended past its grace days (E3-06's `TERM_SWEEP_GRACE_DAYS`), which is a join from
`section` to `term` on every run. A foreign key does not index its own column in
Postgres, which is exactly the kind of thing that is true, widely known, and
missed anyway — and the join is on the *many* side, so the missing index costs a
scan of every section in the institution per sweep.

**What is not asserted here, said out loud.** Neither index's *name* is pinned,
and neither is the direction of its columns. `indexes_leading_with` matches on
leading key columns in any order, so a migration is free to spell either as it
likes and `alembic check` (`tests/integration/test_alembic_baseline.py`) is what
keeps the declaration and the database in step. A name here would be this module
choosing something the round leaves to the migration. The `ags_call` model
docstring's claim that "nothing reads this table on a request path" is corrected
by the implementer in the same change; it is prose in `backend/app/models/`, and
a test carrying a copy of the sentence it checks is `docs/MISTAKES.md` entry 19.

**Why the columns are the pair rather than `section_id` alone.** The read is "the
latest row for this section", which is an equality on `section_id` and an ordered
take on `called_at`. An index on `section_id` alone still makes the planner sort
every row a busy section has accumulated over a term. That is the near miss the
first test is written around, and it is the same one E1's M5 finding landed on:
the fix there was explicitly the *composite*, not the single column.

The catalog reader is `tests/fixtures/indexes.py`, and its own control — two
temporary indexes differing in column order and in a descending flag — is
`tests/integration/test_the_nrps_call_log_is_indexed_for_the_debounce_probe.py`.
That control is what makes a green here mean the index is present rather than
that the reader has gone blind.

**Which failure a red here is.** Both tests are expected **RED** until the
migration lands, as a FAILED naming the missing index — never an error: the
catalog read is a plain call in the test body and `indexes_on` fails with its own
sentence if the table is not there at all.
"""

from typing import Any

import pytest
from fixtures.indexes import index_key_columns, indexes_leading_with

pytestmark = pytest.mark.integration

AGS_CALL = "ags_call"
SECTION = "section"

# The pair the sweep's per-delivery read filters and orders on. `section_id` is
# the column §6.1's console is read by and `called_at` is the instant that
# decides which row is the latest — spelled as `tests/fixtures/ags_client.py`
# spells them, and as `tests/fixtures/grade_sweep.py` reads them back.
LATEST_CALL_COLUMNS = ("section_id", "called_at")

# The join column the sweep's term-bound walk reaches `term` through. E0-06 puts
# it on `section`; Postgres indexes neither side of a foreign key on its own.
TERM_JOIN_COLUMN = "term_id"

# A column on `ags_call` that nothing indexes and this round adds no index for.
# The negative half of the reader's control: a matcher answering "yes" for
# anything would satisfy both assertions below without reading a catalog at all.
AN_UNINDEXED_COLUMN = "response_code"


def indexes_on(engine: Any, table: str) -> dict[str, list[tuple[str, bool]]]:
    """Every index on one migrated table, as its key columns in order.

    `tests/integration/test_the_sweep_and_week_axis_indexes.py`'s helper and its
    reason: a table the reader cannot see at all reports no indexes, which is
    indistinguishable from a table with none — and every assertion resting on
    that would be about nothing.
    """
    with engine.connect() as connection:
        read = index_key_columns(connection, table)
    assert read, (
        f"The catalog reports no index at all on `{table}`, not even a primary key's. Either the "
        "table is not there or this reader is looking somewhere the migrated schema is not, and "
        "every assertion resting on it would be about nothing."
    )
    return read


def test_the_reader_can_tell_an_indexed_column_from_an_unindexed_one(
    migrated_engine: Any,
) -> None:
    """The control, before either absence below is read as a finding.

    `docs/MISTAKES.md` entry 3: a matcher searched against a catalog is a test
    that can go blind and report success. `ags_call` certainly has a primary-key
    index on `id`, and it certainly has none leading with `response_code` — so the
    reader is run against one of each before anything it says about the two
    indexes this round adds is believed.

    **A red here means this module is broken, not the schema.**
    """
    read = indexes_on(migrated_engine, AGS_CALL)

    assert indexes_leading_with(read, ("id",)), (
        f"The reader found no index on `{AGS_CALL}` leading with its primary key, which every "
        f"table in this schema has (ADR 0016 makes it one uuid). It reported {read}. A reader that "
        "cannot find an index that is certainly there cannot be believed when it reports one "
        "missing."
    )
    assert not indexes_leading_with(read, (AN_UNINDEXED_COLUMN,)), (
        f"The reader reports an index on `{AGS_CALL}` leading with `{AN_UNINDEXED_COLUMN}`, which "
        f"nothing in this project asks for. It reported {read}. A matcher that answers yes for any "
        "column would satisfy both assertions below over a schema with no new index in it."
    )


def test_the_call_log_is_indexed_for_the_sweeps_latest_row_read(migrated_engine: Any) -> None:
    """DM-H1: `ags_call` leads with `(section_id, called_at)`.

    The sweep reads this table once per delivery, for the latest call about the
    section it is posting into. With no index the read is a sequential scan of a
    log that gains a row per student per week per section and is purged by nothing
    until E13 — the same defect, on the same shape of table, that E1's boundary
    review measured as M5 on `nrps_call`, where the probe cost 2,006 buffers
    against 5 with the composite in place.

    **The mutation this kills:** the migration shipping the `section.term_id`
    index and not this one, or shipping neither. Both are green against every
    behavioural test in this epic, because a sequential scan returns the right
    answer — a missing index is the one class of defect that is invisible to
    correctness tests entirely, which is why it needs a catalog assertion rather
    than a benchmark nobody runs.

    **The near miss it must survive, and must not be satisfied by:** an index on
    `section_id` alone. That serves the equality and leaves the planner sorting
    every row a busy section accumulated over a term to find the latest one.
    `indexes_leading_with` requires both columns among the leading keys, in either
    order — the order is the migration's to choose and either answers this read.
    """
    read = indexes_on(migrated_engine, AGS_CALL)
    covering = indexes_leading_with(read, LATEST_CALL_COLUMNS)

    assert covering, (
        f"No index on `{AGS_CALL}` leads with {list(LATEST_CALL_COLUMNS)}. What the table carries: "
        f"{read}.\n\nE3-08's boundary round (DM-H1) adds one. SPEC §6.1 puts a row here per HTTP "
        "call this tool made to a platform service, and E3-06's sweep reads the latest row for a "
        "section once per delivery — so without this index that read is a sequential scan of a "
        "table that grows all term and is purged by nothing before E13. An index on `section_id` "
        "alone does not satisfy this: it serves the equality and leaves the ordering to a sort."
    )


def test_section_is_indexed_on_the_term_the_sweeps_walk_joins_through(
    migrated_engine: Any,
) -> None:
    """DM-M1: `section.term_id` carries an index of its own.

    E3-06's walk visits a section only while `term.end_date +
    TERM_SWEEP_GRACE_DAYS >= clock.today`, which is a join from `section` to
    `term` on every sweep. Postgres indexes neither side of a foreign key
    automatically, and this is the *many* side — so without it every run scans
    every section in the institution to find the ones whose term is still open.

    **The mutation this kills:** relying on the foreign-key constraint to have
    produced an index. It is a belief widely enough held that it is worth an
    assertion rather than a review note, and nothing about the sweep's behaviour
    changes when it is wrong.

    **The near miss it must survive:** a composite index that *leads* with
    `term_id` — `(term_id, id)`, say — which serves this join perfectly well.
    `indexes_leading_with` accepts it, because what the read needs is the leading
    column and not a single-column index; an index that leads with something else
    and carries `term_id` second does not serve it and is not accepted.
    """
    read = indexes_on(migrated_engine, SECTION)
    covering = indexes_leading_with(read, (TERM_JOIN_COLUMN,))

    assert covering, (
        f"No index on `{SECTION}` leads with `{TERM_JOIN_COLUMN}`. What the table carries: {read}."
        "\n\nE3-08's boundary round (DM-M1) adds one. E3-06's sweep joins every section to its "
        "term on each run, to apply `TERM_SWEEP_GRACE_DAYS` to the term's end date, and a foreign "
        "key does not index its own column — so the walk scans every section in the deployment "
        "every time. A composite leading with this column satisfies it; one carrying it in second "
        "place does not."
    )
