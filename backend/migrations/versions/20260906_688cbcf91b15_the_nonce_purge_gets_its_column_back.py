"""the nonce purge gets the one column it deletes on

Revision ID: 688cbcf91b15
Revises: c4a8e51db9f3
Create Date: 2026-09-06 00:00:00.000000

E4-14's whole schema change, which is not a schema change at all: one
column-scoped privilege, executed from `lti_launch_nonce_grants_v002.sql`.

`a1b7c93d4e21` created `public.lti_launch_nonce` and deliberately withheld
`SELECT` (E1-08, ADR 0089) — the replay guard's `claim_nonce` never reads the
table, only inserts into it. That withholding also reached a `DELETE` nobody
had written yet: the daily beat task `app.jobs.tasks.purge_launch_nonces`
deletes expired rows on `expires_at`, and Postgres refuses a `DELETE ...
WHERE` whose column the role holds no `SELECT` on. The task has raised
`InsufficientPrivilege` on every run since E1-08 shipped, and because it
shares one `SessionLocal` across both launch tables, the `lti_launch_state`
half of the same task never ran either — `docs/tickets/e4/carried-from-e3.md`,
"The daily purge of the launch replay ledger cannot run." ADR 0150 records why
`SELECT` was withheld in the first place and what this one-column widening
concedes.

**No table, column, type or index is touched**, so there is nothing here for a
database with rows in it to do and nothing for `alembic check` to compare: the
models describe relations and this revision describes a privilege.
`tests/integration/test_identity_grants.py` pins the grant instead, as an
equality against `RUNTIME_COLUMN_PRIVILEGES`, which E4-14 extends with this
column, and as a direct-query negative control beside it.

**Standing note for whoever merges this chain slot** (also on
`lti_launch_state_grants_v001.sql`'s neighbours): E4-02 and E4-03 build in
parallel off the same head, `c4a8e51db9f3`. Whoever merges last re-points
`down_revision` here, this docstring's `Revises` line, and any test constant
naming this revision, to the chain slot actually below it.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "688cbcf91b15"
down_revision: str | Sequence[str] | None = "c4a8e51db9f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NONCE_TABLE = "lti_launch_nonce"
EXPIRES_AT_COLUMN = "expires_at"

# What the downgrade takes back, and it names the column for the same reason
# `e5b83c60f7a1`'s note gives about the line-item column: a privilege granted
# at column grain lives in `pg_attribute.attacl`, and `REVOKE SELECT ON
# public.lti_launch_nonce` does not reach it — it would read as correct, run
# without error, and leave the connection able to read `expires_at` the
# rollback was meant to take away.
#
# It also names the column rather than the table: a table-wide revoke would
# reach nothing, since no table-wide `SELECT` was ever granted here — but
# spelling `(expires_at)` out is what keeps this statement the exact mirror
# of the `GRANT` it reverses rather than a table-grain guess that happens to
# have no effect.
REVOKE_THE_EXPIRY_COLUMN = (
    f"REVOKE SELECT ({EXPIRES_AT_COLUMN}) ON public.{NONCE_TABLE} FROM pulse_app"
)


def upgrade() -> None:
    """Apply this revision: the one column-scoped SELECT the purge's WHERE spends."""
    op.execute(read_sql("lti_launch_nonce_grants_v002"))


def downgrade() -> None:
    """Reverse this revision: the column grant back, and nothing else disturbed.

    The table, its rows, and v001's `INSERT, DELETE` all belong to
    `a1b7c93d4e21` and stay; a database walked back to here keeps the launch
    door's ability to claim a nonce and loses only the daily purge's ability
    to run.
    """
    op.execute(REVOKE_THE_EXPIRY_COLUMN)
