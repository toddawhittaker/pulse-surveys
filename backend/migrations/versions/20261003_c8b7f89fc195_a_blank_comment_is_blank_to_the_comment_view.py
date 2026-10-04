"""a blank comment is blank to the comment view

Revision ID: c8b7f89fc195
Revises: c5e8a1f3b9d4
Create Date: 2026-10-03 00:00:00.000000

E5.1-12, and the ruling appended to `docs/disputes/E5.1-12-01.md`. The
`report_comment` view decided a comment was blank with `btrim(comment_text) <>
''`, and PostgreSQL's one-argument `btrim` trims only the space character. A
comment of spaces, tabs and line breaks therefore counted its author toward SPEC
§4's comment threshold. `report_comment_v002.sql` keeps a comment only if it
holds a character Python's `str.strip()` would keep, by listing every character
`strip` removes by code point. It names no `[:space:]` class, whose meaning
changes with the collation, so the rule is the same under every collation and
leaves nothing to the submission path.

**Replaced on the way up, dropped and recreated on the way down.** The body
changes only its last filter and keeps its five columns in order, so `CREATE OR
REPLACE VIEW` applies and the view's grant survives it: the upgrade issues no
`GRANT`. v001's file says `CREATE VIEW`, so the downgrade drops the view first
and then re-issues the one privilege the drop takes with it, `pulse_app`'s
`SELECT`, which `report_comment_grants_v001.sql` granted and is the only
privilege any revision has granted on this view. That file is not re-run because
it also grants on three tables this revision never disturbs. Nothing in this
tree builds on the view, so the drop needs no `CASCADE`. This is the shape
`e7a2d5c94b31` uses for `benchmark_cohort_term_axis`.

**No table, column, type or index is touched**, so `alembic check` has nothing
to compare here.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "c8b7f89fc195"
down_revision: str | Sequence[str] | None = "c5e8a1f3b9d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMMENT_VIEW = "report_comment"

# What the downgrade removes and puts back. No `IF EXISTS`: a database without
# the view is not at this revision, and the downgrade should say so.
DROP_THE_VIEW = f"DROP VIEW public.{COMMENT_VIEW}"
RESTORE_THE_APPLICATION_READ = f"GRANT SELECT ON public.{COMMENT_VIEW} TO pulse_app"


def upgrade() -> None:
    """Apply this revision: whitespace of every kind is blank to the comment view."""
    op.execute(read_sql(f"{COMMENT_VIEW}_v002"))


def downgrade() -> None:
    """Reverse this revision: v001's body, and the application's read of it.

    A database walked back to here counts a comment of tabs and line breaks as a
    commenter again, which is the defect this revision corrects.
    """
    op.execute(DROP_THE_VIEW)
    op.execute(read_sql(f"{COMMENT_VIEW}_v001"))
    op.execute(RESTORE_THE_APPLICATION_READ)
