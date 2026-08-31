"""the in-flight launch handshake store

Revision ID: c4f81a2e6b39
Revises: a1b7c93d4e21
Create Date: 2026-08-26 14:10:00.000000

E1-08's dispute E1-08-01 was ruled toward a server-side in-flight store: the
launch handshake's `state` -> `nonce` mapping moves off `pylti1p3`'s cookies and
into `public.lti_launch_state`, so a launch inside a cross-site iframe — where a
third-party cookie is blocked whatever its attributes say — still validates
(ADR 0089, SPEC §7.3). This revision creates that table and grants `pulse_app`
the SELECT, INSERT and DELETE `app.lti.in_flight` needs, executing
`lti_launch_state_grants_v001.sql`.

The reasoning for the table shape and the grant (SELECT to read the nonce back,
INSERT to remember, DELETE to consume-on-refusal and to purge; UPDATE withheld)
is on the model in `app.models.lti` and in the `.sql` file this revision runs.

**`alembic check` compares the table** — it is on `Base.metadata` — and does not
compare the grant, which `tests/integration/test_identity_grants.py` pins as an
equality against `RUNTIME_BASE_TABLE_PRIVILEGES`, extended by E1-08 with this
table's three entries.

**The downgrade drops the table**, and the grant goes with it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "c4f81a2e6b39"
down_revision: str | Sequence[str] | None = "a1b7c93d4e21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)

SCRIPTS = ("lti_launch_state_grants_v001",)


def upgrade() -> None:
    """Create the in-flight handshake store and grant the application role its access."""
    op.create_table(
        "lti_launch_state",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("nonce", sa.Text(), nullable=False),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lti_launch_state")),
        sa.UniqueConstraint("state", name="uq_lti_launch_state_state"),
    )
    op.create_index(
        "ix_lti_launch_state_expires_at", "lti_launch_state", ["expires_at"], unique=False
    )
    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Drop the store; the grant on it goes with the relation."""
    op.drop_index("ix_lti_launch_state_expires_at", table_name="lti_launch_state")
    op.drop_table("lti_launch_state")
