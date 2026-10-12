"""a set name is unique ignoring case and spacing

Revision ID: e9a7c9e1b807
Revises: e9c3f5a7b403
Create Date: 2026-10-12 09:00:00.000000

E9-05, ADR 0203. Two comparison sets whose names differ only in capitals or
spacing are one cohort to the person choosing between them, so the second is
refused: a unique index on the normalized name, which is the name trimmed, every
inner run of whitespace collapsed to one space, and case-folded.

**Existing near-duplicates are renamed, never deleted.** A set is a stored
definition somebody chose, and a deletion would take its membership with it. So
before the index is built, the rows are grouped by the normalized name and
ordered by `(created_at, id)`: the first row of each group keeps its name, and
each later one is renamed to its own name followed by ` (n)`, with the smallest
`n` from 2 up whose normalized form no row holds at that moment. The renames are
done one at a time in that order, so a rename sees the ones before it. The table
is locked against writes first, so no row can arrive between the renames and
the index.

The renames run in one PL/pgSQL block, so the normalization is Postgres' own
(the expression the index is built on) and `alembic upgrade --sql` emits a script
that does the same work.

**The downgrade drops the index and nothing else.** A renamed row stays renamed:
the old names are not recorded anywhere, and a guess would be a rename nobody
asked for. E5-01's `UNIQUE (name)` is not this revision's and stays.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e9a7c9e1b807"
down_revision: str | Sequence[str] | None = "e9c3f5a7b403"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "uq_comparison_set_normalized_name"

# Spelled here rather than imported from `app.models.benchmark`, so that this
# revision keeps meaning what it meant if the model's constant ever changes.
NORMALIZED = r"lower(btrim(regexp_replace({0}, '\s+', ' ', 'g')))"

RENAME_NEAR_DUPLICATES = rf"""
DO $$
DECLARE
    duplicate record;
    suffix integer;
    candidate text;
BEGIN
    FOR duplicate IN
        SELECT id, name
        FROM (
            SELECT
                id,
                name,
                created_at,
                row_number() OVER (
                    PARTITION BY {NORMALIZED.format("name")}
                    ORDER BY created_at, id
                ) AS place
            FROM public.comparison_set
        ) AS grouped
        WHERE place > 1
        ORDER BY created_at, id
    LOOP
        suffix := 2;
        LOOP
            candidate := duplicate.name || ' (' || suffix || ')';
            EXIT WHEN NOT EXISTS (
                SELECT 1
                FROM public.comparison_set
                WHERE {NORMALIZED.format("name")} = {NORMALIZED.format("candidate")}
            );
            suffix := suffix + 1;
        END LOOP;
        UPDATE public.comparison_set SET name = candidate WHERE id = duplicate.id;
    END LOOP;
END
$$
"""


def upgrade() -> None:
    """Rename near-duplicate set names, then refuse new ones with a unique index."""
    op.execute("LOCK TABLE public.comparison_set IN SHARE ROW EXCLUSIVE MODE")
    op.execute(RENAME_NEAR_DUPLICATES)
    op.execute(f"CREATE UNIQUE INDEX {INDEX} ON public.comparison_set ({NORMALIZED.format('name')})")


def downgrade() -> None:
    """Drop the index. Renamed rows keep their new names."""
    op.execute(f"DROP INDEX public.{INDEX}")
