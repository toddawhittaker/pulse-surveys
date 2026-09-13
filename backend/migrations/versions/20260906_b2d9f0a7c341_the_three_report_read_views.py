"""the three report read views, and the runtime role's read of them

Revision ID: b2d9f0a7c341
Revises: a1e7c4b60d92
Create Date: 2026-09-06 00:00:00.000000

E4-03. The numbers SPEC §5.1 asks the instructor's Monday report for, computed at
read time from the rows E2 shipped: a per-stream rating distribution, a workload
mean and median, and the response and valid-response counts. All three are keyed
by a section and a `week` row, all three return only the section-weeks that were
answered, and none of them returns a column that names a person (§4.1). ADR 0147
carries the decisions — where a rate is divided, why there is no trend view, and
what E4-07 owns instead.

**Four `views_sql/` scripts and no schema change.** Nothing is created here but
three views and the grants that let `pulse_app` read them, so `alembic check`
compares nothing in this revision: it reads no `pg_class` entry for a view and no
ACL. `446183e8cc5f` measured that and its docstring records it. What notices a
missing view or a widened grant is
`tests/integration/test_identity_grants.py`, `test_identity_column_marker.py`,
`test_identity_separated_views.py` and E4-03's own five modules — three of those
tests are `invariant`-marked, so a skip is a build failure rather than a silent
pass.

**The SQL is read from `backend/app/views_sql/` rather than written out here**,
which is the deliberate exception `446183e8cc5f` states at length: Postgres keeps
no record of the text a `CREATE VIEW` was written with, only a parse tree of
oids, so a view whose SQL lives inside a revision string is a view whose
schema-qualification nothing can check. ADR 0041 makes the file immutable once a
revision has executed it, so the file name fixes what ran.

**Order is stated rather than globbed.** The three views first, because the
grants name them; the grants last. A file added to `views_sql/` does nothing
until a revision names it, which is the safe direction.

**The downgrade drops the three views and writes no REVOKE.** A privilege granted
on a view is recorded in that view's ACL and goes when the view goes, so a revoke
here would be a statement about objects that no longer exist. That is the
difference between this revision and `d3a71b5c8e42`, whose grants are on base
tables that outlive it and which therefore has something to un-grant.

**This revision takes the chain slot below E4-02's.** `report_rating_distribution`
reads `question.stream`, which `a1e7c4b60d92` adds; a database at that revision
and not this one has the column and no view, which is a state E4-07 simply has no
report on. Nothing here creates a type, an index or a constraint, so re-pointing
it under a sibling E4 revision at merge is a one-line change.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "b2d9f0a7c341"
down_revision: str | Sequence[str] | None = "a1e7c4b60d92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The scripts this revision runs, in the order it runs them. The views before the
# grants, because a grant names an object that has to exist.
SCRIPTS = (
    "report_rating_distribution_v001",
    "report_workload_v001",
    "report_response_counts_v001",
    "report_read_grants_v001",
)

# What the downgrade removes, in the reverse of the order the views were created.
# `IF EXISTS` is not used: a downgrade that cannot find what this revision made is
# a database that is not where it says it is, and it should say so.
DROP_VIEWS = (
    "DROP VIEW public.report_response_counts",
    "DROP VIEW public.report_workload",
    "DROP VIEW public.report_rating_distribution",
)


def upgrade() -> None:
    """Apply this revision."""
    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Undo this revision."""
    for statement in DROP_VIEWS:
        op.execute(statement)
