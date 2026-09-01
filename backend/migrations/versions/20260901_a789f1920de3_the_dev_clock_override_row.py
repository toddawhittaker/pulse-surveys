"""the dev clock override row

Revision ID: a789f1920de3
Revises: 3f6907349751
Create Date: 2026-09-01 00:00:00.000000

E2-04. SPEC §3.1 makes every survey window a wall-clock time in the institution's
timezone, and E2 has to be drivable by hand: what a student sees on a Friday
evening has to be reachable without waiting for one. This revision creates the
single row a developer moves the effective clock with, and opens the three verbs
the application needs on it.

**One row, held by a unique index over a constant.** `(true)` is the same value in
every row, so a second insert collides with the first and the error names the
index — the shape `institution` uses for the same job (`a702938fcc97`, ADR 0072,
which records the `singleton boolean` column measured and rejected there). The
index name is spelled out rather than built by `op.f(...)` for the reason that
revision gives: the `ix` template on `Base.metadata` interpolates a column name and
a textual expression has none to give it, so the model names this index explicitly
too and the two spellings have to match.

**`sa.DateTime(timezone=True)` and not `AwareDateTime`.** The model's columns carry
the decorated type from `app.models.base`, whose whole job is to refuse a naive
value at bind; a migration writes the underlying `timestamp with time zone`, which
is what that decorator's `impl` resolves to. ADR 0019 records the consequence and
every revision here follows it — a migration that imported the decorator would tie
the schema history to a Python type that can be renamed.

**The grants file is executed here** rather than left to a later revision, because
without it `pulse_app` — the role the tool and the worker both connect as — is
refused every statement `app.services.clock` and the `/dev` control make, with
42501 and not with anything the ticket is about.
`clock_override_grants_v001.sql` carries the sentence for each of the three verbs
and for the one withheld.

**`downgrade()` drops the table**, which takes its index and its privileges with
it: a granted privilege belongs to the relation, so there is nothing left to
revoke. A database taken back to `3f6907349751` holds precisely what that revision
left it holding.

**Chained after `3f6907349751`, not after `d2f6a913c47e`.** Both this revision and
`3f6907349751` (E2-05) were written in parallel worktrees off `d2f6a913c47e`; once
E2-05's PR merged into the epic branch, this revision's `down_revision` was moved
onto it so the chain stays linear, with no change to what either revision does.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "a789f1920de3"
down_revision: str | Sequence[str] | None = "3f6907349751"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "clock_override"
ONE_ROW_INDEX = "uq_clock_override_one_row"

SCRIPTS = ("clock_override_grants_v001",)


def upgrade() -> None:
    """Apply this revision: the table, its one-row index, and the three grants."""
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("pretend_now", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anchored_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clock_override")),
    )
    op.create_index(ONE_ROW_INDEX, TABLE, [sa.literal_column("(true)")], unique=True)

    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Reverse this revision: the table goes, and its index and privileges with it."""
    op.drop_index(ONE_ROW_INDEX, table_name=TABLE)
    op.drop_table(TABLE)
