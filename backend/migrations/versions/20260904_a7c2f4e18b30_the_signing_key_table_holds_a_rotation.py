"""the signing key table holds a rotation

Revision ID: a7c2f4e18b30
Revises: b1e7d4a90c26
Create Date: 2026-09-04 00:00:00.000000

E3-01. One table changes shape so that the tool can hold more than one signing
key at a time; `backend/app/models/lti.py` holds the reasoning beside the
columns and `docs/adr/0127` records the rule.

**`uq_tool_signing_key_one_row` is dropped.** E1-05 put a unique index on the
constant expression `(true)` there, which held the table to a single row and made
the tool's identity provably one key (ADR 0082). It also made rotation
structurally impossible: a rotation needs a period in which the retiring key and
its replacement are published together, and a one-row table has nowhere to put
the second key. What replaces the index is a rule the readers hold — the
published set is every row with `retired_at IS NULL` and the signing key is the
newest of those — so the guarantee moves from the schema into
`app.lti.registration`, which is the cost ADR 0127 records rather than a
side effect.

**`created_at` arrives with a server default and `retired_at` arrives
nullable.** The default is what makes this safe on a database that already holds
a key: a `NOT NULL` column with no default aborts against a table with a row in
it and leaves the database stranded below this revision, which is how E2-05's
revision failed. Every existing row is a key that was supplied before this
revision ran and has not been retired, and `now()` plus NULL says exactly that.

**Nothing is preserved and the downgrade refuses instead.** The two columns are
derivable from nothing — a retirement is a fact only this table records — but
they are also the whole of what a rotation is, so the disposition here is not a
preserve. Below this revision the one-row index is back, and a database holding a
rotation in progress cannot be represented there at all. So the downgrade counts
the rows first and **refuses** when it meets more than one, naming retirement as
the way back to a single key. Discarding the extra rows silently was the
alternative, and it discards private key material a platform may already have
been registered against; keeping the newest and deleting the rest is the same
loss wearing a rule. An operator who wants to go down retires the keys they are
finished with and removes the retired rows deliberately, with the record in front
of them.

**No grants.** `pulse_app` holds `SELECT` on `public.tool_signing_key` as a table
privilege (`tool_signing_key_grants_v001.sql`), and a table privilege covers a
column added afterwards, so neither new column needs a verb — checked against
`RUNTIME_BASE_TABLE_PRIVILEGES` in `tests/integration/test_identity_grants.py`,
which is a table-and-verb inventory and is unchanged by this revision. The write
privileges stay withheld, which is what makes the operator script's privileged
credential the supply path rather than a widening (ADR 0126).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c2f4e18b30"
down_revision: str | Sequence[str] | None = "b1e7d4a90c26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The table this revision reshapes, and the index it takes off. Spelled out
# rather than built by `op.f(...)`: the `ix` naming template interpolates a
# column name and this index is on a textual expression, so E1-05's revision
# spelled it explicitly too and the two spellings have to match.
SIGNING_KEYS = "tool_signing_key"
ONE_ROW_INDEX = "uq_tool_signing_key_one_row"

# `timestamp with time zone`, which is what the model's `AwareDateTime` resolves
# to. A migration writes the underlying type rather than importing the decorator,
# for the reason `a789f1920de3` gives: the decorator's job is to refuse a naive
# value at bind, and importing it would tie the schema history to a Python name.
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    """Apply this revision."""
    op.add_column(
        SIGNING_KEYS,
        sa.Column("created_at", TIMESTAMP, server_default=sa.text("now()"), nullable=False),
    )
    op.add_column(SIGNING_KEYS, sa.Column("retired_at", TIMESTAMP, nullable=True))
    op.drop_index(ONE_ROW_INDEX, table_name=SIGNING_KEYS)


def downgrade() -> None:
    """Undo this revision, or refuse when undoing it would destroy a key.

    The refusal is the whole of the interesting part. Below this revision the
    table holds at most one row, so a database part-way through a rotation has no
    representation there — and every way of forcing one discards the private half
    of a key this deployment may already have signed assertions with. Nothing
    regenerates that, and no platform accepts a replacement for it without a
    re-registration, so this stops and says what to do instead.
    """
    connection = op.get_bind()
    stored = connection.execute(
        sa.text(f"SELECT count(*) FROM public.{SIGNING_KEYS}")  # noqa: S608
    ).scalar_one()
    if stored > 1:
        raise RuntimeError(
            f"`public.{SIGNING_KEYS}` holds {stored} keys and the revision below this one permits "
            "one. Going down would have to discard the private half of a key this deployment may "
            "already have signed assertions with, and nothing regenerates it. Retire the keys this "
            "deployment has finished with (`python scripts/signing_key.py retire <kid>`), delete "
            "the retired rows once no platform can still be verifying against them, and run this "
            "downgrade again with one key left."
        )
    op.create_index(ONE_ROW_INDEX, SIGNING_KEYS, [sa.literal_column("(true)")], unique=True)
    op.drop_column(SIGNING_KEYS, "retired_at")
    op.drop_column(SIGNING_KEYS, "created_at")
