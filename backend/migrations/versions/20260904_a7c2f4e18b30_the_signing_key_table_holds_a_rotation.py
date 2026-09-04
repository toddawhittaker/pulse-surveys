"""the signing key table holds a rotation

Revision ID: a7c2f4e18b30
Revises: c7e2a41b90f5
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

**The downgrade refuses an ambiguous identity, and discards the retired records.**
Below this revision the one-row index is back, so a database holding a rotation
cannot be represented there at all. The disposition is therefore not a preserve —
what a downgrade cannot keep, it has to be explicit about losing — and it splits
in two along the line that actually matters.

*Ambiguity is refused.* The guard counts the **live** keys, the ones with
`retired_at IS NULL`, and stops when it meets more than one. That is the case
where going down would have to choose which of two identities survives, and the
one it discarded may be the private half of a key a platform has already fetched:
nothing regenerates it, and the failure surfaces at that platform as a refused
assertion naming no key. The refusal names retirement as the way back to a single
signing identity, which is a route an operator can actually walk — the guard
counts live keys, so retiring one satisfies it.

*Retired records are discarded.* With one live key (or none), the downgrade
deletes every retired row before restoring the index, because the one-row schema
has nowhere to put them. What is lost is the record of what this deployment used
to sign with, not an identity anything still verifies against. That is the price
of returning to the one-row world, and it is paid by an operator running an
explicit downgrade after the guard's own instruction rather than by anything
silent. `docs/adr/0127` records it as a consequence.

Counting **live** rows rather than stored ones is what makes the two halves
cohere. An earlier draft counted every row and advised retirement, and retirement
keeps the row: an operator following the advice could never satisfy the guard.

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
down_revision: str | Sequence[str] | None = "c7e2a41b90f5"
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
    """Undo this revision: refuse an ambiguous identity, discard the retired records.

    Below this revision the table holds at most one row, so a database part-way
    through a rotation has no representation there. Two different things are at
    stake in that sentence and they get two different answers.

    **More than one live key is refused.** Completing would have to choose which
    identity survives, and the one discarded may be the private half of a key a
    platform has already fetched — nothing regenerates it, no platform accepts a
    replacement without a re-registration, and the failure surfaces over there as
    a refused assertion naming no key. So this stops and says what to do instead.

    **Retired rows are deleted.** They are the record of what this deployment used
    to sign with, not an identity anything still verifies against, and the one-row
    schema has nowhere to put them. They go before the index is restored, which is
    also what makes the restore possible.

    **The guard counts live keys, and that is what makes its own advice
    reachable.** A guard counting every stored row would advise retirement and
    then refuse the retired row it had just been given: an operator following the
    instruction could never satisfy it. Counting the unretired rows means
    `retire` is a route down, and this function finishes the job by removing what
    retirement leaves behind.

    **Zero live keys is permitted too**, and worth saying out loud: a deployment
    that has retired everything is one that can already sign nothing, so there is
    no identity to be ambiguous about — the retired rows go and the table comes
    back empty, which is a state the one-row schema represents perfectly.
    """
    connection = op.get_bind()
    live = connection.execute(
        sa.text(f"SELECT count(*) FROM public.{SIGNING_KEYS} WHERE retired_at IS NULL")  # noqa: S608
    ).scalar_one()
    if live > 1:
        raise RuntimeError(
            f"`public.{SIGNING_KEYS}` holds {live} keys that have not been retired, and the "
            "revision below this one permits a single row. Going down would have to choose which "
            "of them stays as this tool's identity, and the one discarded may be the private half "
            "of a key a platform has already fetched — nothing regenerates it. Retire the keys "
            "this deployment has finished signing with (`python scripts/signing_key.py retire "
            "<kid>`) until one is left, then run this downgrade again: it removes the retired rows "
            "itself, which is the price of going back to a table that holds one key."
        )
    op.execute(sa.text(f"DELETE FROM public.{SIGNING_KEYS} WHERE retired_at IS NOT NULL"))  # noqa: S608
    op.create_index(ONE_ROW_INDEX, SIGNING_KEYS, [sa.literal_column("(true)")], unique=True)
    op.drop_column(SIGNING_KEYS, "retired_at")
    op.drop_column(SIGNING_KEYS, "created_at")
