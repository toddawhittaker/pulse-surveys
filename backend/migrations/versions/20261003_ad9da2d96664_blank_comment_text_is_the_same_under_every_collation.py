"""blank comment text is the same under every collation

Revision ID: ad9da2d96664
Revises: c8b7f89fc195
Create Date: 2026-10-03 00:00:00.000000

E5.1-12, from the privacy and authorization review of PR #273 recorded in
`docs/disputes/E5.1-12-01.md`. `c8b7f89fc195` gave the `report_comment` view a
blank-text test built on the `[:space:]` class plus eight escapes. That class
follows the collation: it agreed with Python's `str.strip()` under the
project's en_US.utf8 and let fifteen Unicode spaces count as text under
`COLLATE "C"`. `report_comment_v003.sql` lists every character `strip` removes
by code point and names no class, so the test means the same thing under every
collation. `app.services.reporting` carries the same list for the summary
gather.

**A new file and a new revision rather than an edit to v002**, because v002 had
been pushed for review and ADR 0041 makes a `views_sql/` file immutable from
that point.

**Replaced on the way up, dropped and recreated on the way down**, the shape
`c8b7f89fc195` uses. The body changes only its last filter and keeps its five
columns in order, so `CREATE OR REPLACE VIEW` applies and the view's one grant,
`pulse_app`'s `SELECT`, survives it. v002's file also says `CREATE OR REPLACE
VIEW`, so the downgrade could replace the body in place as well; it drops and
recreates instead, and re-issues that grant, so that the downgrade does not
depend on what the file being restored happens to say. Nothing in this tree
builds on the view, so the drop needs no `CASCADE`.

**No table, column, type or index is touched**, so `alembic check` has nothing
to compare here.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "ad9da2d96664"
down_revision: str | Sequence[str] | None = "c8b7f89fc195"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMMENT_VIEW = "report_comment"

# What the downgrade removes and puts back. No `IF EXISTS`: a database without
# the view is not at this revision, and the downgrade should say so.
DROP_THE_VIEW = f"DROP VIEW public.{COMMENT_VIEW}"
RESTORE_THE_APPLICATION_READ = f"GRANT SELECT ON public.{COMMENT_VIEW} TO pulse_app"


def upgrade() -> None:
    """Apply this revision: blank comment text is a list of code points, not a class."""
    op.execute(read_sql(f"{COMMENT_VIEW}_v003"))


def downgrade() -> None:
    """Reverse this revision: v002's body, and the application's read of it.

    A database walked back to here treats fifteen Unicode spaces as text under
    `COLLATE "C"` again, which is the defect this revision corrects.
    """
    op.execute(DROP_THE_VIEW)
    op.execute(read_sql(f"{COMMENT_VIEW}_v002"))
    op.execute(RESTORE_THE_APPLICATION_READ)
