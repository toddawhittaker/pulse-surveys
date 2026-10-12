"""the sessions ended before their tokens expired

Revision ID: e9c3f5a7b403
Revises: 7f679faf4b8d
Create Date: 2026-10-12 00:00:00.000000

E9-04, ADR 0202. A session is a signed token that verified until its `exp`, and
nothing could end one sooner. The role switch and logout both have to: this
revision creates `revoked_session`, which holds the `jti` of each session ended
early until its token would have expired anyway, and opens the three verbs the
application needs on it. `revoked_session_grants_v001.sql` carries the sentence
for each verb and for the one withheld.

**The `jti` is the primary key.** A revocation is looked up by it on every gated
request, and a second revocation of the same session is an insert that does
nothing on conflict.

**No index on `expires_at`.** The purge deletes rows past it, and the table holds
at most an hour of revocations, because every token lives an hour (ADR 0089).

**`downgrade()` drops the table**, which takes its privileges with it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "e9c3f5a7b403"
down_revision: str | Sequence[str] | None = "7f679faf4b8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "revoked_session"

SCRIPTS = ("revoked_session_grants_v001",)


def upgrade() -> None:
    """Apply this revision: the table and its three grants."""
    op.create_table(
        TABLE,
        sa.Column("jti", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("jti", name=op.f("pk_revoked_session")),
    )

    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Reverse this revision: the table goes, and its privileges with it."""
    op.drop_table(TABLE)
