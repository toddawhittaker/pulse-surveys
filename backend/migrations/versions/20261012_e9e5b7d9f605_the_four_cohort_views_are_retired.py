"""the four benchmark cohort views are retired, with their grants

Revision ID: e9e5b7d9f605
Revises: e9f6c8e0a706
Create Date: 2026-10-12 16:00:00.000000

E9-12, README decision 10, ADR 0166. `benchmark_cohort_week`,
`benchmark_cohort_rating_week`, `benchmark_cohort_term_axis` and
`benchmark_cohort_rating_term_axis` answer for a whole cohort, institution-wide.
Their last reader was `named_set_term_axis`, which E9-05 deleted; the named-set
and roll-up figures read the set functions over a reader's purview instead. A
view nobody reads is still a read surface `pulse_app` holds, so the four go.

**The upgrade drops the four views, from four versioned files.** Each drop is
the view's next `views_sql/` version (`benchmark_cohort_term_axis_v003`, the
other three `_v002`), not a string here: the directory, folded in name order, is
the record of which views a migrated database holds, and
`test_identity_separated_views.py` reads it that way. `pulse_app`'s `SELECT` on
each is recorded in the view's own ACL and goes with it, so there is no
`REVOKE`. `IF EXISTS` is not used: a database without them is not where this
revision says it is. The two set functions, the definer role and its column
grants stay; the roll-ups read them.

**The downgrade recreates them from the versions before the drops**, which are what
the database held at `e9f6c8e0a706`: `a7c3e9d21f84`'s three `_v001` bodies and
`e7a2d5c94b31`'s `benchmark_cohort_term_axis_v002`, then
`benchmark_read_grants_v001.sql`, which grants `SELECT` on exactly these four to
`pulse_app` and nothing else. `_v002` is `CREATE OR REPLACE`, which creates the
view when none exists.

**No table, column, type or index is touched**, so `alembic check` has nothing
to compare.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "e9e5b7d9f605"
down_revision: str | Sequence[str] | None = "e9f6c8e0a706"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RETIRE_SCRIPTS = (
    "benchmark_cohort_term_axis_v003",
    "benchmark_cohort_rating_term_axis_v002",
    "benchmark_cohort_week_v002",
    "benchmark_cohort_rating_week_v002",
)

# The views first, because the grants file names them.
RESTORE_SCRIPTS = (
    "benchmark_cohort_rating_week_v001",
    "benchmark_cohort_week_v001",
    "benchmark_cohort_rating_term_axis_v001",
    "benchmark_cohort_term_axis_v002",
    "benchmark_read_grants_v001",
)


def upgrade() -> None:
    """Apply this revision: drop the four cohort views, and with them their grants."""
    for script in RETIRE_SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Reverse this revision: the four views as `e9f6c8e0a706` held them, and `pulse_app`'s read."""
    for script in RESTORE_SCRIPTS:
        op.execute(read_sql(script))
