"""the benchmark service grants the read it spends

Revision ID: d9e5b13c7a42
Revises: a7c3e9d21f84
Create Date: 2026-09-13 00:00:00.000000

E5-04's whole schema change, which is not a schema change at all: one verb on two
tables, executed from `comparison_set_grants_v001.sql`.

`b4d7e2a91c58` created `public.comparison_set` and `public.comparison_set_member`
and granted nothing on either, deliberately — E4-02's precedent, "a privilege
lands in the change that spends it", with the two tickets that would spend one
named in E5-01's own model docstring. This is the first of them.
`app.services.benchmarks` resolves a named set to the sections its figures are
computed over — the declared length off the set row and the member courses off
the membership table — on the connection every request in the product runs on, so
without this revision every named-set benchmark is refused with 42501.

`SELECT` is the whole of what this revision issues.
`comparison_set_grants_v001.sql` names the sentence the verb comes from and the
verbs it withholds; the short version is that nothing on this connection may
define, edit or delete the cohort an institution is measured against — those are
E5-06's, and a deletion reaches figures that were already published because
benchmarks are past-referencing.

**No table, column, type or index is touched**, so there is nothing here for a
database with rows in it to do and nothing for `alembic check` to compare: the
models describe relations and this revision describes two privileges.
`tests/integration/test_identity_grants.py` pins them instead, as an equality
against `RUNTIME_BASE_TABLE_PRIVILEGES`, and
`tests/integration/test_the_comparison_set_tables_are_refused_to_the_application_connection.py`
drives a read *and* the three refused writes over the application connection
rather than reading the catalog alone (`docs/MISTAKES.md` entry 46).

**Cut from `a7c3e9d21f84`, which was the single head when this was written** —
read off `ScriptDirectory.walk_revisions()` rather than copied from a note. E5-04
is wave 2's only migration, so nothing is expected to re-point around it; if
another branch does cut one off the same head, the second to merge re-points its
own `down_revision` and this docstring's `Revises` line in the same change.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "d9e5b13c7a42"
down_revision: str | Sequence[str] | None = "a7c3e9d21f84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SET_TABLE = "comparison_set"
MEMBER_TABLE = "comparison_set_member"

# What the downgrade takes back, spelled as the exact mirror of the two GRANTs.
# Both relations belong to `b4d7e2a91c58` and outlive this revision, so the
# privileges have to be revoked by hand — a revision that drops nothing takes no
# ACL entry with it. The verb is named rather than `REVOKE ALL`: `ALL` would also
# remove a privilege some later revision granted on the same relation for its own
# reason, which is the ordinary way a rollback quietly widens or narrows
# something it was never about. E5-06's writes will be granted, and revoked, by
# the revision that spends them.
REVOKE_THE_COMPARISON_SET_READ = (
    f"REVOKE SELECT ON public.{SET_TABLE} FROM pulse_app",
    f"REVOKE SELECT ON public.{MEMBER_TABLE} FROM pulse_app",
)


def upgrade() -> None:
    """Apply this revision: the benchmark service's read of a named comparison set."""
    op.execute(read_sql("comparison_set_grants_v001"))


def downgrade() -> None:
    """Reverse this revision: the two reads back, and nothing else disturbed.

    Both tables, their rows, their composite keys and their checks belong to
    `b4d7e2a91c58` and stay. A database walked back to here keeps every named set
    leadership has defined and loses only the application connection's ability to
    read one — which is a benchmark that suppresses rather than a benchmark that
    is wrong.
    """
    for statement in REVOKE_THE_COMPARISON_SET_READ:
        op.execute(statement)
