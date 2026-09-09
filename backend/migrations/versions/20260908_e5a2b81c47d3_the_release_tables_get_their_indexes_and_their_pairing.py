"""the release tables get their indexes and their pairing

Revision ID: e5a2b81c47d3
Revises: c7f41a9d2b60
Create Date: 2026-09-08 00:00:00.000000

E4-15's boundary round, and the two schema findings it triaged. Both are about
`release_batch` and `release_batch_member` — E4-02's tables (ADR 0146), E4-04's
reads (ADR 0152) — and neither is visible from any behaviour in this suite: both
reads are correct, and both are correct slowly or loosely.

**The two indexes.** `released_comments` walks a section's batches for a term and
then the memberships of each; `cut_due_release_batches` anti-joins the membership
table to find what is still held, for every section in the institution, every
Monday. Neither read had an index to use. `release_batch_member` was scanned to
find one batch's rows and `release_batch` was scanned to find one section's, and
both tables grow with every release ever cut. E4-02's own notes on the two columns
said the index should arrive "in the ticket that measured the read rather than in
the ticket that guessed at it"; this is that ticket.

The unique on `release_batch_member.answer_id` is not a substitute for the first
of them: it leads with the answer, so a lookup by batch cannot use it. Postgres 17
has no skip scan, and an index that merely *contains* a column serves no lookup by
it — the same sentence `app/models/survey.py` already carries about
`uq_response_user_id_section_id_week_id`.

**The pairing.** `release_batch` carried a plain key to `section` and a plain key
to `term`, and nothing made the two agree. ADR 0152 cuts one batch per crossing per
section and term, and `released_comments` reads by that pair, so a row naming a
section of one term and the id of another is a release attached to a crossing
nobody evaluated: invisible to its section's real report, or attached to the wrong
term's. Nothing in the service re-checks a pairing it computed itself, which is the
shape of defect that survives every test written against a service — so the
database is where it is refused.

The mechanism is `response`'s and `survey_window`'s and is taken unchanged from
`b1e7d4a90c26`: a composite foreign key over `(section_id, term_id)` referring to
`section (id, term_id)`, which `section` has carried as `uq_section_id_term_id`
since `3f6907349751`. A `CHECK` cannot read another table — the whole of ADR 0018 —
and `term_id` is already on the row, so this costs no column and no backfill. ADR
0146's own argument for leaving the keys plain cited ADR 0145's cost, which was
about adding a column that is not there; that record carries the dated correction.

**The composite replaces the plain key to `section` rather than sitting beside
it**, which is what `b1e7d4a90c26` did for `response`: one check per reference, and
the composite is strictly the stronger. **The plain key to `term` stays.** The
composite implies it — a section's own `term_id` is a foreign key into `term` — and
dropping it is a separate decision about what a batch's term means, which no
finding asked for.

**The downgrade is a true reversal and preserves nothing, because there is nothing
here to preserve.** This revision adds two indexes and swaps one constraint for a
stronger one; it narrows no column and drops no data. A database that goes down and
comes back up holds exactly the rows it held. The one ordering that matters is the
same one the upgrade has in the other direction: the plain key to `section` is put
back before the composite one is dropped, so there is no moment inside the
transaction when a batch's section is unreferenced.

**What this revision does not do.** It adds no grant. `pulse_app` already holds
`SELECT` and `INSERT` on both tables from `d4c1a7e93f26`, which is everything
E4-04's reads and its one writer spend, and an index is not a privilege.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5a2b81c47d3"
down_revision: str | Sequence[str] | None = "c7f41a9d2b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BATCH = "release_batch"
MEMBER = "release_batch_member"
SECTION = "section"

# The two indexes, named the way the convention on `Base.metadata` renders them —
# `ix_%(table_name)s_%(column_0_N_name)s` — so `alembic check` compares the
# declaration against the database and finds nothing.
MEMBER_BATCH_INDEX = "ix_release_batch_member_batch_id"
BATCH_SCOPE_INDEX = "ix_release_batch_section_id_term_id"

# The plain key this revision replaces, as `a1e7c4b60d92` named it, and the
# composite one that takes its place. Both spelled to match the `fk` template
# character for character.
SECTION_FK = "fk_release_batch_section_id_section"
SECTION_TERM_FK = "fk_release_batch_section_id_term_id_section"

SECTION_COLUMN = "section_id"
TERM_COLUMN = "term_id"
BATCH_COLUMN = "batch_id"


def upgrade() -> None:
    """Apply this revision: the two indexes, then the pairing.

    The composite key is created before the plain one is dropped, so there is no
    moment inside this transaction when a batch's section is unreferenced.
    """
    op.create_index(op.f(MEMBER_BATCH_INDEX), MEMBER, [BATCH_COLUMN], unique=False)
    op.create_index(op.f(BATCH_SCOPE_INDEX), BATCH, [SECTION_COLUMN, TERM_COLUMN], unique=False)

    op.create_foreign_key(
        SECTION_TERM_FK,
        BATCH,
        SECTION,
        [SECTION_COLUMN, TERM_COLUMN],
        ["id", TERM_COLUMN],
        ondelete="RESTRICT",
    )
    op.drop_constraint(SECTION_FK, BATCH, type_="foreignkey")


def downgrade() -> None:
    """Reverse this revision: the plain key back, the composite one and both indexes gone."""
    op.create_foreign_key(SECTION_FK, BATCH, SECTION, [SECTION_COLUMN], ["id"], ondelete="RESTRICT")
    op.drop_constraint(SECTION_TERM_FK, BATCH, type_="foreignkey")

    op.drop_index(op.f(BATCH_SCOPE_INDEX), table_name=BATCH)
    op.drop_index(op.f(MEMBER_BATCH_INDEX), table_name=MEMBER)
