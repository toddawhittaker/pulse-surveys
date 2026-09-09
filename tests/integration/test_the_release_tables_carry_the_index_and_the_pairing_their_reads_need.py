"""What `release_batch` and `release_batch_member` owe the catalog — the boundary review's two schema findings.

E4-02 built the release as a batch row and a membership row (ADR 0146) and E4-04
built the one writer of both (ADR 0152). Two facts about those tables were found
missing at the epic boundary, and neither is visible from any behaviour a test in
this suite drives today: both reads are correct, and both are correct slowly or
loosely.

**The index finding.** `released_comments` walks a section's batches and then the
memberships of each, and `cut_due_release_batches` anti-joins against the
membership table to find what is still held — every Monday, for every section in
the institution. Neither read has an index to use: the membership table is scanned
to find one batch's rows, and the batch table is scanned to find one section's. It
is invisible today because a development database holds a handful of rows, and it
grows with every release ever cut.

**The pairing finding.** `release_batch` carries both a `section_id` and a
`term_id`, and nothing makes them agree. A batch is per section and per term (ADR
0152: "one batch per crossing, holding the whole held set, in one transaction per
section and term"), so a row naming a section of one term and the id of another is
a batch that belongs to no crossing anybody evaluated — and `released_comments`
reads by that pair. Two single-column foreign keys accept it; a composite one
referring to `section (id, term_id)` does not.

**Asserted by columns rather than by name**, which is the rule the sibling module
`test_the_sweep_and_week_axis_indexes.py` states and this one follows: "a name
would be this module choosing a spelling the ticket leaves to the migration".
`indexes_leading_with` matches the leading key columns in any order, so a
migration is free to call its indexes whatever it likes and free to order a
two-column key either way — both orders answer the equality lookup the read makes.
`alembic check` is what keeps the declaration and the database in step.

**What the pairing test does NOT do, said plainly rather than implied.** It reads
the catalog for a composite foreign key; it does not plant a mismatched row and
watch the database refuse it. The behavioural half needs a world holding **two
terms**, and no fixture in this suite builds one — every world here is one term
with sections inside it, so there is no second `term_id` to point a section at that
would not also fail the plain foreign key to `term` and prove nothing about the
pairing. `docs/MISTAKES.md` entry 47's rule ("where a structural guard and a
behavioural test can disagree about one route, write the behavioural one") is
weighed and does not transfer: it is about a route class whose gate is discarded at
dispatch while the class stays visible, and a foreign key in this catalog *is* the
enforcement — PostgreSQL checks it on every write, with no dispatch step in
between. The residual is that this test cannot tell a validated constraint from one
added `NOT VALID`, and that is what the behavioural half would have added. It is
recorded here and carried rather than claimed.

**Which failure a red is.** Both tests read the migrated catalog through fixtures
that already exist, so a red is an assertion about what the catalog holds, never an
error in setup.
"""

from typing import Any

import pytest
from fixtures.indexes import index_key_columns, indexes_leading_with
from sqlalchemy import inspect

pytestmark = pytest.mark.integration

RELEASE_BATCH = "release_batch"
RELEASE_BATCH_MEMBER = "release_batch_member"
SECTION = "section"
RESPONSE = "response"

# E4-02's own spellings, as `tests/fixtures/report_comments.py` transcribes them
# from `tests/integration/test_report_schema.py`.
BATCH_ID_COLUMN = "batch_id"
SECTION_ID_COLUMN = "section_id"
TERM_ID_COLUMN = "term_id"

# The pair a batch is identified by, and the pair `released_comments` reads on.
THE_BATCHS_SCOPE = (SECTION_ID_COLUMN, TERM_ID_COLUMN)

# A column nothing in this schema indexes, borrowed from the sibling module's own
# control. It is on a different table on purpose: what it proves is that the
# matcher can answer **no**, and a matcher that answers yes for anything makes
# every assertion here vacuous (`docs/MISTAKES.md` entry 35 — a guard has to be
# shown refusing as well as finding).
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


def test_the_membership_table_is_indexed_for_the_read_that_walks_one_batch(
    migrated_engine: Any,
) -> None:
    """`release_batch_member` leads an index with `batch_id`.

    `released_comments` reads a section's batches and then, for each, the
    memberships that belong to it — a lookup by `batch_id`. Without an index leading
    with that column the lookup scans the whole membership table, which holds every
    comment this institution has ever released, on a read that happens every time an
    instructor opens the latest published week of a section with a release in it.

    **The mutation this kills:** the index left out of E4-02's migration, which is
    the state the boundary review found. Nothing else in this repository would
    notice: every test here runs against a handful of rows, where a scan and a
    lookup are indistinguishable, and `alembic check` compares the declaration
    against the database rather than against what the reads need.

    **The near miss it must survive:** the unique index on `answer_id` that ADR
    0146 already requires. It exists, it is on this table, and it serves the
    cutter's anti-join — and it cannot serve a lookup by batch, because it does not
    lead with `batch_id`. `indexes_leading_with` is what tells the two apart.
    """
    read = indexes_on(migrated_engine, RELEASE_BATCH_MEMBER)
    covering = indexes_leading_with(read, (BATCH_ID_COLUMN,))

    assert covering, (
        f"No index on `{RELEASE_BATCH_MEMBER}` leads with `{BATCH_ID_COLUMN}`. What it carries: "
        f"{read}.\n\n`released_comments` walks a section's batches and then each batch's "
        "memberships, so a lookup by batch is the read this table exists to serve. The unique "
        "index ADR 0146 puts on `answer_id` does not satisfy it: it leads with the answer, so a "
        "scan for one batch's rows cannot use it."
    )


def test_the_batch_table_is_indexed_for_the_read_that_walks_one_sections_term(
    migrated_engine: Any,
) -> None:
    """`release_batch` leads an index with the section and the term it is scoped by.

    Both of this epic's release reads are per `(section, term)`: `released_comments`
    asks what this section has released this term, and `cut_due_release_batches`
    asks the same question of every section in the institution once a week. Without
    an index leading with that pair, each of those is a scan of every batch ever
    cut.

    **The columns may be in either order** — both answer the equality lookup — and
    an index on the section alone does not satisfy this: a section runs in more than
    one term, and the read is of one term's batches.

    **The mutation this kills:** the same one as its sibling, on the other table,
    and it is a separate test because a migration that adds one index very plausibly
    leaves the other.
    """
    read = indexes_on(migrated_engine, RELEASE_BATCH)
    covering = indexes_leading_with(read, THE_BATCHS_SCOPE)

    assert covering, (
        f"No index on `{RELEASE_BATCH}` leads with {list(THE_BATCHS_SCOPE)}. What it carries: "
        f"{read}.\n\nADR 0152 cuts one batch per crossing per section and term, and both reads in "
        "`app.services.report_comments` are keyed on that pair — the weekly cutter's over every "
        "section in the institution. The columns may be in either order; an index on the section "
        "alone does not satisfy it, because a section runs in more than one term."
    )


def test_the_index_matcher_finds_nothing_for_a_column_nothing_indexes(
    migrated_engine: Any,
) -> None:
    """The negative half of the reader's control. **A red here means this module is broken.**

    Both assertions above are "an index covering these columns exists". A matcher
    that answered yes for any index at all — a comparison that compared nothing, a
    slice that took no columns — satisfies both without reading the catalog, and
    nothing in that green would say so.

    `response.first_submitted_at` is indexed by nothing in this schema, which is the
    fact `test_the_sweep_and_week_axis_indexes.py` already rests its own control on.
    """
    read = indexes_on(migrated_engine, RESPONSE)
    covering = indexes_leading_with(read, (AN_UNINDEXED_COLUMN,))

    assert not covering, (
        f"The matcher reports {covering} as leading with `{AN_UNINDEXED_COLUMN}`, which nothing in "
        "this schema indexes. Either it matches anything — in which case the two assertions in "
        "this module are vacuous — or an index on that column has been added deliberately, and "
        "this control is the line to change."
    )


def test_a_batchs_section_and_term_are_paired_by_a_composite_foreign_key(
    migrated_engine: Any,
) -> None:
    """`release_batch (section_id, term_id)` refers to `section` as one key, not as two.

    A batch is per section and per term, and a section belongs to exactly one term.
    With two single-column foreign keys, a row naming a section of one term and the
    id of another satisfies both and is a batch belonging to a crossing nobody
    evaluated — while `released_comments` reads by that pair, so such a row is
    either invisible for ever or attached to a term its comments were not written
    in. The database is the only place that can refuse it: nothing in the service
    re-checks a pairing it computed itself, which is precisely the shape of defect
    that survives every test written against the service.

    **What is asserted:** that some foreign key on `release_batch` refers to
    `section` and carries **both** columns. The constraint's name is not asserted,
    for the same reason no index name is: the migration owns the spelling.

    **The mutation this kills:** the two single-column foreign keys E4-02 shipped —
    the state the boundary review found, and the one every behaviour in this epic is
    green against.

    **The near miss it must survive:** a composite key that carries the two columns
    and refers to the wrong table — `term` rather than `section` — which would
    constrain nothing about the pairing. The referred table is compared, not just
    the column set.

    **What it does not reach**, and the module docstring carries the reasoning: this
    reads the catalog rather than planting a mismatched row and watching the write
    be refused. A constraint added `NOT VALID` would satisfy this and refuse
    nothing already in the table. The behavioural half needs a world of two terms
    and no fixture here builds one; it is carried rather than claimed.
    """
    with migrated_engine.connect() as connection:
        keys = inspect(connection).get_foreign_keys(RELEASE_BATCH)

    assert keys, (
        f"The catalog reports no foreign key at all on `{RELEASE_BATCH}`, which cannot be right — "
        "the table references a section and a term — so this reader is looking somewhere the "
        "migrated schema is not and the assertion below would be about nothing."
    )

    paired = [
        key
        for key in keys
        if key.get("referred_table") == SECTION
        and set(key.get("constrained_columns") or ()) == set(THE_BATCHS_SCOPE)
    ]
    assert paired, (
        f"No foreign key on `{RELEASE_BATCH}` carries {list(THE_BATCHS_SCOPE)} together against "
        f"`{SECTION}`. What the catalog holds: "
        f"{[(key.get('constrained_columns'), key.get('referred_table'), key.get('referred_columns')) for key in keys]}"
        "\n\nTwo single-column keys accept a batch whose section belongs to one term and whose "
        "`term_id` names another. ADR 0152 cuts one batch per crossing per section and term and "
        "`released_comments` reads by that pair, so such a row is a release attached to a term its "
        "comments were not written in — invisible to the section's real report, or attached to the "
        "wrong one. Nothing in the service re-checks a pairing it computed itself, so the database "
        f"is where this is refused: a composite key over {list(THE_BATCHS_SCOPE)} referring to "
        f"`{SECTION} (id, {TERM_ID_COLUMN})`, which needs that pair to be unique on `{SECTION}`."
    )
