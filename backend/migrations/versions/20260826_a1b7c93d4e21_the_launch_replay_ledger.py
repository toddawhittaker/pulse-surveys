"""the launch replay ledger

Revision ID: a1b7c93d4e21
Revises: d3cb2cf2204e
Create Date: 2026-08-26 10:20:00.000000

E1-08 moves launch validation onto pylti1p3 and adds single-use nonces. This
revision creates `public.lti_launch_nonce` — the ledger
`app.lti.replay_guard.claim_nonce` spends a nonce into with
`INSERT ... ON CONFLICT (nonce) DO NOTHING` — and grants `pulse_app` the INSERT
and DELETE it needs there, executing `lti_launch_nonce_grants_v001.sql`.

The reasoning for the table shape (why Postgres rather than Redis, why not a
person table) is on the model in `app.models.lti`, and the reasoning for the
grant (INSERT for the claim, DELETE for the daily purge, SELECT and UPDATE
withheld) is in the `.sql` file this revision runs.

**`alembic check` compares the table** — it is on `Base.metadata` — and does not
compare the grant, which is not part of the metadata and which autogenerate has
never emitted. So the table half of this revision is drift-checked and the grant
half is not; `tests/integration/test_identity_grants.py` pins the grant instead,
as an equality against `RUNTIME_BASE_TABLE_PRIVILEGES`, which E1-08 extends with
this table's two entries.

**The downgrade drops the table**, and the grant goes with it — a privilege on a
relation that no longer exists has nothing to revoke, unlike the grants on tables
that outlive their own revision.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "a1b7c93d4e21"
down_revision: str | Sequence[str] | None = "d3cb2cf2204e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)

# The grant script this revision runs. Named rather than globbed, for the reason
# every revision here gives: a directory listing is not a dependency order.
SCRIPTS = ("lti_launch_nonce_grants_v001",)


def upgrade() -> None:
    """Create the replay ledger and grant the application role its write access."""
    op.create_table(
        "lti_launch_nonce",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("nonce", sa.Text(), nullable=False),
        sa.Column(
            "consumed_at", TIMESTAMP, server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lti_launch_nonce")),
        sa.UniqueConstraint("nonce", name="uq_lti_launch_nonce_nonce"),
    )
    op.create_index(
        "ix_lti_launch_nonce_expires_at", "lti_launch_nonce", ["expires_at"], unique=False
    )
    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Drop the ledger; the grant on it goes with the relation."""
    op.drop_index("ix_lti_launch_nonce_expires_at", table_name="lti_launch_nonce")
    op.drop_table("lti_launch_nonce")
