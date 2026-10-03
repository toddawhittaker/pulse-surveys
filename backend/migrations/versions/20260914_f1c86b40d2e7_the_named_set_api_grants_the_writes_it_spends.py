"""the named-set API grants the writes it spends

Revision ID: f1c86b40d2e7
Revises: e7a2d5c94b31
Create Date: 2026-09-14 00:00:00.000000

E5-06's whole schema change, which is not a schema change at all: five verbs on
two tables, executed from `comparison_set_write_grants_v001.sql`.

`b4d7e2a91c58` created `public.comparison_set` and `public.comparison_set_member`
and granted nothing on either, deliberately — E4-02's precedent, "a privilege
lands in the change that spends it", with the two tickets that would spend one
named in E5-01's own model docstring. `d9e5b13c7a42` was the first, the read
E5-04 resolves a named set through. This is the second and last.
`app.services.comparison_sets` defines, edits and deletes a set on the connection
every request in the product runs on, so without this revision every write from
`app.api.leadership` is refused with 42501.

`INSERT, UPDATE, DELETE` on the set table and `INSERT, DELETE` on the membership
table is the whole of what this revision issues.
`comparison_set_write_grants_v001.sql` names the route each verb is spent by and
the one that is withheld; the short version is that membership is replaced rather
than edited, so nothing on this connection may change a membership row in place.

**No table, column, type or index is touched**, so there is nothing here for a
database with rows in it to do and nothing for `alembic check` to compare: the
models describe relations and this revision describes five privileges.
`tests/integration/test_identity_grants.py` pins them instead, as an equality
against `RUNTIME_BASE_TABLE_PRIVILEGES`, and
`tests/integration/test_the_comparison_set_tables_are_refused_to_the_application_connection.py`
drives all five *and* the withheld one over the application connection rather
than reading the catalog alone (`docs/MISTAKES.md` entry 46).

**Cut from `e7a2d5c94b31`, which was the single head when this was written** —
read off `ScriptDirectory.walk_revisions()` rather than copied from a note. E5-06
is wave 3's only migration, so nothing is expected to re-point around it; if
another branch does cut one off the same head, the second to merge re-points its
own `down_revision` and this docstring's `Revises` line in the same change.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "f1c86b40d2e7"
down_revision: str | Sequence[str] | None = "e7a2d5c94b31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SET_TABLE = "comparison_set"
MEMBER_TABLE = "comparison_set_member"

# What the downgrade takes back, spelled as the exact mirror of the two GRANTs.
# Both relations belong to `b4d7e2a91c58` and outlive this revision, so the
# privileges have to be revoked by hand — a revision that drops nothing takes no
# ACL entry with it. The verbs are named rather than `REVOKE ALL`: `ALL` would
# also remove `d9e5b13c7a42`'s `SELECT`, which sits below this revision and is
# not E5-06's to take, leaving a database one step back from head unable to
# resolve a named set at all — a benchmark that disappears rather than a write
# that is refused.
REVOKE_THE_COMPARISON_SET_WRITES = (
    f"REVOKE INSERT, UPDATE, DELETE ON public.{SET_TABLE} FROM pulse_app",
    f"REVOKE INSERT, DELETE ON public.{MEMBER_TABLE} FROM pulse_app",
)


def upgrade() -> None:
    """Apply this revision: the named-set API's five writes."""
    op.execute(read_sql("comparison_set_write_grants_v001"))


def downgrade() -> None:
    """Reverse this revision: the five writes back, and the read left where it is.

    Both tables, their rows, their composite keys and their checks belong to
    `b4d7e2a91c58` and stay, and so does `d9e5b13c7a42`'s `SELECT`. A database
    walked back to here keeps every named set leadership has defined and loses
    only the application connection's ability to define, change or delete one —
    which is a management surface that refuses rather than a benchmark that is
    wrong.
    """
    for statement in REVOKE_THE_COMPARISON_SET_WRITES:
        op.execute(statement)
