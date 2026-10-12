"""the org node label view

Revision ID: e9f6c8e0a706
Revises: e9a7c9e1b807
Create Date: 2026-10-12 14:00:00.000000

E9-07, ADR 0205. `org_node_label_v001.sql`: `public.org_node_label (level,
node_id, name, parent_id)`, one row per institution, college, department, prefix
and course, and `SELECT` on it to `pulse_app` and to nobody else. The roll-up
tree names departments and colleges, and `pulse_app` holds nothing on
`institution`, `college` or `department`; the view gives it the four columns and
leaves those tables shut.

**No index.** The breakdown reserved this revision for an index on
`instructor_response (section_id, week_id, sequence)` if `EXPLAIN` over a
term-sized seed asked for one. It did not: the owed read's one statement over
`instructor_response` selects `(section_id, week_id)` by `section_id`, and the
existing `ix_instructor_response_section_id_week_id` answers it. ADR 0205
records the plan.

**The downgrade** drops the view, which takes its grant with it. It holds no
data, so it needs no guard.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

revision: str = "e9f6c8e0a706"
down_revision: str | Sequence[str] | None = "e9a7c9e1b807"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision: the org-node label view and `pulse_app`'s `SELECT` on it."""
    op.execute(read_sql("org_node_label_v001"))


def downgrade() -> None:
    """Reverse this revision: drop the view, and its grant with it."""
    op.execute("DROP VIEW public.org_node_label")
