"""The indexes E2-16 adds and the two it rules are kept — items 4 and 6.

Two of this ticket's items are facts about the migrated catalog, so they are
asserted together against it, and each is a separate test because each fails for
its own reason.

**Item 4's supporting index.** Criterion 3 asks for the rewrite *and* "the new
index exists": `classification (task, prompt_version)`, the pair the sweep's
floored leg filters on. Rewriting the anti-join without it recovers most of the
72 seconds the boundary review measured and still leaves the leg reading the
whole table to find the floor's rows.

**Item 6's two week-axis indexes.** `ix_response_week_id` and
`ix_survey_window_week_id` serve no query in the tree today — verified by a
whole-tree grep — and the ticket's ruling is to **keep** them, because the read
they anticipate is spec-anchored: SPEC §3.4's participation is "recomputed after
each week closes", which is a read by week. A ruling to keep something is worth
exactly as much as whatever notices it being dropped, so the two tests below are
what notices (`docs/MISTAKES.md` entry 2 — prefer asserting the state that must
hold over the one that happens to).

**What is not asserted here, said out loud.** Item 6's other half retenses the
two model comments from a present-tense §3.4 read to E3's. That is prose in
`app/models/*.py`, and a test asserting it would have to carry a copy of the
sentence it is checking — `docs/MISTAKES.md` entry 19's shape, and a pattern that
goes blind the moment the wording is edited for any other reason. It is left to
review, and the indexes themselves are what this module pins.

**Which index carries the columns is not asserted, and the direction is not
either.** `indexes_leading_with` matches on the leading key columns in any order,
so `(task, prompt_version)` and `(prompt_version, task)` both satisfy the
criterion — both answer an equality lookup on the pair — while an index on
`task` alone, or one that leads with some third column, does not. A name would be
this module choosing a spelling the ticket leaves to the migration, and
`alembic check` (`tests/integration/test_alembic_baseline.py`) is what keeps the
declaration and the database in step whatever it is called.

The catalog reader is `tests/fixtures/indexes.py`, and its own control — two
temporary indexes differing in column order and in a descending flag — is
`tests/integration/test_the_nrps_call_log_is_indexed_for_the_debounce_probe.py`.
"""

from typing import Any

import pytest
from fixtures.indexes import index_key_columns, indexes_leading_with

pytestmark = pytest.mark.integration

CLASSIFICATION = "classification"
RESPONSE = "response"
SURVEY_WINDOW = "survey_window"

# The pair the sweep's floored leg filters on: E0-13's `classification.task` and
# SPEC §7.4's prompt version, which is what tells the character floor's rows from
# a model's (ADR 0054 — "a reader can tell the two apart with no schema
# knowledge", because the floor names itself in exactly these two columns).
SWEEP_FILTER_COLUMNS = ("task", "prompt_version")

# The week axis, as E2-05 spells it on both tables.
WEEK_COLUMN = "week_id"

# A column on `response` that nothing indexes and this ticket adds no index for.
# It is the negative half of the reader's control: a matcher that answered "yes"
# for anything would satisfy all three assertions below without reading a thing.
AN_UNINDEXED_COLUMN = "first_submitted_at"


def indexes_on(engine: Any, table: str) -> dict[str, list[tuple[str, bool]]]:
    """Every index on one migrated table, as its key columns in order."""
    with engine.connect() as connection:
        read = index_key_columns(connection, table)
    assert read, (
        f"The catalog reports no index at all on `{table}`, not even a primary key's. Either the "
        "table is not there or this reader is looking somewhere the migrated schema is not, and "
        "every assertion resting on it would be about nothing."
    )
    return read


def test_classification_is_indexed_for_the_sweeps_floor_filter(migrated_engine: Any) -> None:
    """Criterion 3's index half: `classification (task, prompt_version)`.

    The sweep's floored leg selects the rows of one task written under the
    floor's prompt version. Without an index on that pair the leg reads the whole
    of `classification` on every run — and it runs on a beat and on every floored
    submission, at a table that grows with every comment ever classified.

    **The mutation this must kill:** shipping the query rewrite alone. The
    boundary review measured the rewrite at 166ms and the index-only change at
    46s against the 72s original, so neither half is the other's substitute, and
    a rewrite without the index is the version that looks finished.

    **The near miss it must survive:** an index on `task` alone. `task` has one
    value in this schema (`COMMENT_VALIDITY`), so an index on it selects every
    row in the table and buys nothing at all — which is why the leading columns
    have to be the pair rather than either of them.
    """
    read = indexes_on(migrated_engine, CLASSIFICATION)
    covering = indexes_leading_with(read, SWEEP_FILTER_COLUMNS)

    assert covering, (
        f"No index on `{CLASSIFICATION}` leads with {list(SWEEP_FILTER_COLUMNS)}. What it carries: "
        f"{read}.\n\nE2-16 criterion 3 asks for the rewrite *and* the supporting index, and the "
        "measurement is why both: 72 seconds for the `NOT IN` anti-join at ~300k rows, 46 with an "
        "index alone, 166ms with the anti-join rewritten. The sweep's floored leg selects one "
        "task's rows written under the floor's prompt version, and the columns may be in either "
        "order — an index on `task` alone does not satisfy this, because every row in the table "
        "carries the same task."
    )


def test_response_keeps_the_week_axis_index_e3s_week_close_read_will_use(
    migrated_engine: Any,
) -> None:
    """Item 6: `ix_response_week_id` stays. Green today, and that is the whole point.

    The ticket's ruling is that the two speculative week-axis indexes are kept —
    the read they anticipate is SPEC §3.4's "recomputed after each week closes",
    which E3 builds — and that only the model comments claiming that read exists
    today are retensed. Nothing in the repository would have noticed the index
    being dropped instead: it serves no query in the tree, so every test would
    stay green.

    **The mutation this must kill:** the tidier's version of item 6 — deleting
    both unused indexes and retensing nothing, which is a defensible reading of
    the finding and is not the ruling.

    A red here after a deliberate decision to drop the index is this test being
    wrong rather than the schema, and the pull request that drops it is where
    that is said.
    """
    read = indexes_on(migrated_engine, RESPONSE)
    covering = indexes_leading_with(read, (WEEK_COLUMN,))

    assert covering, (
        f"No index on `{RESPONSE}` leads with `{WEEK_COLUMN}`. What it carries: {read}.\n\n"
        "E2-16 item 6 keeps this index rather than dropping it: SPEC §3.4 recomputes "
        "participation after each week closes, which is a read by week, and E3 is where that read "
        f"is built. `ix_{RESPONSE}_section_id_{WEEK_COLUMN}` does not satisfy this — it leads with "
        "the section, so a scan for one week's responses across sections cannot use it."
    )


def test_survey_window_keeps_the_week_axis_index_e3s_week_close_read_will_use(
    migrated_engine: Any,
) -> None:
    """Item 6, the other index: `ix_survey_window_week_id` stays.

    The pair of the test above, and separate from it because the two indexes are
    on different tables and a change that dropped one would very plausibly leave
    the other. Same ruling, same mutation, same reason a green suite would not
    have noticed.
    """
    read = indexes_on(migrated_engine, SURVEY_WINDOW)
    covering = indexes_leading_with(read, (WEEK_COLUMN,))

    assert covering, (
        f"No index on `{SURVEY_WINDOW}` leads with `{WEEK_COLUMN}`. What it carries: {read}.\n\n"
        "E2-16 item 6 keeps this one too. A week-close read asks for every window of a week; "
        "without this index that is a scan of every window in the term."
    )


def test_the_index_matcher_finds_nothing_for_a_column_nothing_indexes(
    migrated_engine: Any,
) -> None:
    """The negative half of the reader's control. **A red here means this module is broken.**

    The three assertions above are all "an index covering these columns exists".
    A matcher that answered yes for any index at all — a comparison that compared
    nothing, a slice that took no columns — satisfies every one of them without
    reading the catalog, and nothing in a green would say so
    (`docs/MISTAKES.md` entry 35: a guard has to be shown refusing as well as
    finding).

    `response.first_submitted_at` is indexed by nothing in this schema and this
    ticket adds no index for it, so the matcher has to answer no.
    """
    read = indexes_on(migrated_engine, RESPONSE)
    covering = indexes_leading_with(read, (AN_UNINDEXED_COLUMN,))

    assert not covering, (
        f"The matcher reports {covering} as leading with `{AN_UNINDEXED_COLUMN}`, which nothing in "
        f"this schema indexes. Either it matches anything — in which case the three assertions in "
        "this module are vacuous — or an index on that column has been added deliberately, and "
        "this control is the line to change."
    )
