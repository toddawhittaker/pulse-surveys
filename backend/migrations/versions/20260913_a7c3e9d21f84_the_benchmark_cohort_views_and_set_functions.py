"""the four benchmark cohort views, the two set functions, and their grants

Revision ID: a7c3e9d21f84
Revises: e5a2b81c47d3
Create Date: 2026-09-13 12:00:00.000000

E5-03. The cohort arithmetic under every benchmark figure SPEC §5.1 asks for,
computed at read time over rows that already exist: per-stream rating means, the
workload mean and median, and the three counts, on both of SPEC §2.2's week axes
— the course week for a section's own report, and the term axis with one line
per start cohort for the aggregate pages E9 draws. The ruling on
`docs/disputes/E5-03-01.md` settles the four view names, their column lists, the
two function signatures and the grants; ADR 0165 records the definer choice, the
term-axis cohort key, and the one place these views depart from
`report_workload`.

**Seven `views_sql/` scripts and no schema change.** Nothing is created here but
four views, one role, two functions and the grants that let `pulse_app` reach
them, so `alembic check` compares nothing in this revision: it reads no
`pg_class` entry for a view, no `pg_proc` entry and no ACL. `446183e8cc5f`
measured that and its docstring records it. What notices a missing view or a
widened grant is `tests/integration/test_identity_grants.py`,
`test_identity_column_marker.py`, `test_identity_separated_views.py` and E5-03's
own eleven modules, several of them `invariant`-marked, so a skip is a build
failure rather than a silent pass.

**The SQL is read from `backend/app/views_sql/` rather than written out here**,
which is the deliberate exception `446183e8cc5f` states at length: Postgres keeps
no record of the text a `CREATE VIEW` was written with, only a parse tree of
oids, so a view whose SQL lives inside a revision string is a view whose
schema-qualification nothing can check. ADR 0041 makes the file immutable once a
revision has executed it, so the file name fixes what ran.

**Order is stated rather than globbed**, and here it is load-bearing three
times: the four views first, because the grants file names them; the definer role
before the two functions, because each ends with `ALTER FUNCTION … OWNER TO`;
and the view grants last.

**This revision takes the chain slot after `e5a2b81c47d3`.** E5-01 is being built
in a parallel worktree and takes the other slot off the same head; whichever
merges second re-points, which is a one-line change because nothing here creates
a type, an index or a constraint.

**The downgrade drops what it made and revokes what outlives it.** A privilege
granted on a view is recorded in that view's ACL and goes when the view goes, so
there is nothing to un-grant for the four; the definer role's column grants sit
on base tables that outlive this revision, so they are revoked by hand. The role
itself is emptied and kept rather than dropped, which is E0-10's decision for
`pulse_reveal_definer` and `e2c94b6a1f70`'s for the other three: a NOLOGIN role
holding nothing is inert, and `DROP ROLE` fails against any object elsewhere in
the cluster that still depends on it, which is a confusing way for a downgrade to
stop halfway.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "a7c3e9d21f84"
down_revision: str | Sequence[str] | None = "e5a2b81c47d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The scripts this revision runs, in the order it runs them.
SCRIPTS = (
    "benchmark_cohort_rating_week_v001",
    "benchmark_cohort_week_v001",
    "benchmark_cohort_rating_term_axis_v001",
    "benchmark_cohort_term_axis_v001",
    "benchmark_definer_v001",
    "benchmark_set_week_v001",
    "benchmark_set_rating_week_v001",
    "benchmark_read_grants_v001",
)

# What the downgrade removes, functions before views. `IF EXISTS` is not used on
# the views: a downgrade that cannot find what this revision made is a database
# that is not where it says it is, and it should say so.
DROP_OBJECTS = (
    "DROP FUNCTION IF EXISTS public.benchmark_set_rating_week(uuid[])",
    "DROP FUNCTION IF EXISTS public.benchmark_set_week(uuid[])",
    "DROP VIEW public.benchmark_cohort_term_axis",
    "DROP VIEW public.benchmark_cohort_rating_term_axis",
    "DROP VIEW public.benchmark_cohort_week",
    "DROP VIEW public.benchmark_cohort_rating_week",
)

# The definer role is emptied and kept. Each revoke is guarded on the role
# existing, because `REVOKE … FROM <role>` is an error rather than a no-op when
# the role is absent — and a downgrade is exactly the moment somebody is already
# dealing with a database in a state nobody planned. The grants are revoked at
# column grain because that is the grain they were granted at: `REVOKE … ON
# <table>` does not reach a column-grain ACL entry.
EMPTY_THE_BENCHMARK_DEFINER = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_benchmark_definer') THEN
        REVOKE SELECT (id, user_id, section_id, week_id) ON public.response
            FROM pulse_benchmark_definer;
        REVOKE SELECT (response_id, question_id, rating, workload_hours) ON public.answer
            FROM pulse_benchmark_definer;
        REVOKE SELECT (id, kind, stream) ON public.question FROM pulse_benchmark_definer;
        REVOKE SELECT (id, term_id, start_date) ON public.section FROM pulse_benchmark_definer;
        REVOKE SELECT (id, start_date) ON public.term FROM pulse_benchmark_definer;
        REVOKE SELECT (id, number) ON public.week FROM pulse_benchmark_definer;
        REVOKE ALL ON public.response FROM pulse_benchmark_definer;
        REVOKE ALL ON public.answer FROM pulse_benchmark_definer;
        REVOKE ALL ON public.question FROM pulse_benchmark_definer;
        REVOKE ALL ON public.section FROM pulse_benchmark_definer;
        REVOKE ALL ON public.term FROM pulse_benchmark_definer;
        REVOKE ALL ON public.week FROM pulse_benchmark_definer;
    END IF;
END
$$;
"""


def upgrade() -> None:
    """Apply this revision."""
    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Undo this revision."""
    for statement in DROP_OBJECTS:
        op.execute(statement)
    op.execute(EMPTY_THE_BENCHMARK_DEFINER)
