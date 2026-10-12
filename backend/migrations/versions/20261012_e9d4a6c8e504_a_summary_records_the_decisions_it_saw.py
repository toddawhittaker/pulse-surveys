"""a summary records the decisions it saw

Revision ID: e9d4a6c8e504
Revises: e9a7c9e1b807
Create Date: 2026-10-12 12:00:00.000000

ADR 0206. `weekly_summary` gains `moderation_sequence_seen`: the highest
`moderation_state.sequence` about the section-week that the summary walk could
read before it gathered the comments, or 0 when it read none. The leadership
and draft reads withhold a summary whose section-week holds a removal above
that number, which a racing exclusion cannot pass the way it passes a
comparison of two transaction-start times.

**Existing rows are left null and nothing is backfilled.** A null row is judged
by `generated_at`, exactly as every row was before this revision, so no summary
anybody can read today changes. A backfill would have to guess which decisions
the walk saw from instants, which is the comparison this revision replaces.

The downgrade drops the column, and with it every stored sequence; nothing can
recover them. After a downgrade and a re-upgrade every row is null again, so it
is judged by `generated_at` as a row written before this revision is.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e9d4a6c8e504"
down_revision: str | Sequence[str] | None = "e9a7c9e1b807"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "weekly_summary",
        sa.Column("moderation_sequence_seen", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("weekly_summary", "moderation_sequence_seen")
