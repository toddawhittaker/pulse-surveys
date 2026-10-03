"""the term axis answers the hours' own counts

Revision ID: e7a2d5c94b31
Revises: c4b8f37e5a19
Create Date: 2026-09-14 01:00:00.000000

The third and last face of E5-04's security finding. `c4b8f37e5a19` corrected the
two set functions, which serve the course-week axis; this corrects
`benchmark_cohort_term_axis`, which serves the term axis that E5-06's preview and
E9 read.

The defect is one sentence in three places: `workload_mean` and
`workload_median` are computed over the responses that carry hours, while
`respondent_count` and `section_count` count everybody who answered anything.
ADR 0165 keeps a cohort week's row when nobody reported hours at all, so the two
populations diverge whenever a responder leaves the question blank — and always
in the disclosing direction, because a figure's own contributors are never more
numerous than the week's. `benchmark_cohort_term_axis_v002.sql` adds
`workload_respondent_count` and `workload_section_count` with the same `FILTER`
shape the two function bodies use, so all three reads agree by construction.

**This widens the sanctioned read surface by two columns, and that was argued
before it was built.** The whole-relation `SELECT` `pulse_app` holds carries the
new columns the moment they exist. The widening is the subject of the ruling
appended to `docs/disputes/E5-04-01.md`, and the two equalities SPEC §4.1 item 1
is enforced through — `BENCHMARK_VIEWS` in `tests/fixtures/benchmark_views.py`
and `SANCTIONED_VIEW_COLUMNS` in `tests/integration/test_identity_grants.py` —
admit the pair with the sentence that says why. Both moved before this revision
was written, which is the order the ruling sets.

**Replaced on the way up, dropped and recreated on the way down, and the
asymmetry is Postgres's rather than a preference.** `CREATE OR REPLACE VIEW`
permits *appending* columns and refuses to remove or reorder them, so the
upgrade is a replacement and the ten existing columns keep their positions;
measured against the migrated database, along with the fact that the
relation-wide grant survives a replacement, so the upgrade issues no `GRANT`.
The downgrade removes two columns, which a replacement cannot do — so it drops
the view and re-issues the one grant the drop took with it.

**No table, column, type or index is touched**, so there is nothing for
`alembic check` to compare: the models describe relations and this revision
describes one view body.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "e7a2d5c94b31"
down_revision: str | Sequence[str] | None = "c4b8f37e5a19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TERM_AXIS_VIEW = "benchmark_cohort_term_axis"

# What the downgrade puts back, and what it has to re-issue afterwards.
#
# The view is `a7c3e9d21f84`'s and outlives this revision, so going back means
# restoring its previous body rather than leaving a hole — `named_set_term_axis`
# calls it, and a database walked back to here still serves reports. Dropping it
# takes its ACL entry with it, so the grant is written out by hand: it is the
# same privilege `benchmark_read_grants_v001.sql` issues, named here for this one
# relation rather than by re-running that file, which would re-grant three other
# views this revision never disturbed.
DROP_THE_WIDENED_VIEW = f"DROP VIEW public.{TERM_AXIS_VIEW}"
RESTORE_THE_APPLICATION_READ = f"GRANT SELECT ON public.{TERM_AXIS_VIEW} TO pulse_app"


def upgrade() -> None:
    """Apply this revision: the term axis answers the counts its workload figures are sealed with."""
    op.execute(read_sql("benchmark_cohort_term_axis_v002"))


def downgrade() -> None:
    """Reverse this revision: the previous body, and the application's read of it.

    A database walked back to here keeps the view, its rows and every report that
    reads it, and loses only the two contributor counts — which returns it to the
    state where a term-axis workload figure is sealed against the cohort week's
    overall counts rather than its own. That is the defect this revision
    corrects, described plainly so that a rollback is a known position rather
    than a surprise.
    """
    op.execute(DROP_THE_WIDENED_VIEW)
    op.execute(read_sql(f"{TERM_AXIS_VIEW}_v001"))
    op.execute(RESTORE_THE_APPLICATION_READ)
