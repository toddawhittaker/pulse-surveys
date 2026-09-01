"""the application may read and write a survey window

Revision ID: c9b4e0a71d38
Revises: a789f1920de3
Create Date: 2026-09-01 00:00:00.000000

E2-06 is the first code that touches `public.survey_window`. E0-06 created the
table and E2-05 added its cross-term rule; neither granted the runtime role
anything on it, because until this ticket nothing read a window and nothing wrote
one. Both halves of E2-06 run on the connection `pulse_app` holds — the Celery
worker derives the rows hourly, and the `/dev` console reads them to say whether a
section's survey is open — so this revision is where the grant lands, with the
code that spends it. `SELECT, INSERT`, and nothing else.

**The withheld verbs are the load-bearing half, and they are worth stating here
rather than only in the SQL.** No `UPDATE` means the application role
*structurally* cannot reopen or move a window that has closed: no statement it can
issue changes `closes_at`, so a week that has ended cannot be made to accept a
submission by anything short of a superuser connection. SPEC §3.1 puts the report
after the close, so a moved `closes_at` is a week that can still change under a
report already generated. No `DELETE` is the same rule one level up — §3.1 says a
missed week cannot be back-filled, and re-deriving after a calendar edit is E11's
decision on a surface an administrator drives, not something an hourly job can
reach. Together they are also what makes E2-06's "the writer skips an existing
row and rewrites nothing" a property of the database rather than a rule the next
writer has to remember.

The rest of the reasoning — why a base table rather than a read view, why
`pulse_care` is granted nothing, and why `USAGE ON SCHEMA public` is not granted
again — is in `survey_window_grants_v001.sql`, which this revision executes.

**There is no schema change here at all**, so `alembic check` has nothing to
compare: a grant is not part of `Base.metadata` and autogenerate has never emitted
one. That is the ordinary state of every grants file in this tree
(`tool_signing_key_grants_v001.sql`, `clock_override_grants_v001.sql`), and it is
why `tests/integration/test_identity_grants.py` pins what each runtime role holds
as an equality read out of the catalog — the drift gate cannot see this and a
hand-written catalog assertion can.

**This revision turns that equality red until its constant gains the two entries**,
and that is the designed cost rather than a surprise. `RUNTIME_BASE_TABLE_PRIVILEGES`
is deliberately hand-written and not derived from these `.sql` files, so that a
widening cannot justify itself; the entry is raised as `docs/disputes/E2-06-03.md`,
the same shape `docs/disputes/E2-04-02.md` took for `clock_override`.

**The downgrade revokes.** The table is E0-06's and outlives this revision, so
unlike a grant on a table its own revision drops, this one would survive a
downgrade that dropped nothing. The `REVOKE` is written here rather than as a
second `.sql` file: ADR 0041 makes a versioned file the immutable record of what
an upgrade applied, and an un-grant is not a record of anything.

**Chained after `a789f1920de3`**, which is the head this branch was cut from and
the head `alembic heads` reports — E2-04's clock-override revision, which merged
into the epic branch after E2-05's `3f6907349751`. E2-03 and E2-07 add no
revision, so nothing in this round re-chains.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "c9b4e0a71d38"
down_revision: str | Sequence[str] | None = "a789f1920de3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The scripts this revision runs. Written out rather than globbed, for the reason
# E0-10's revision gives: a directory listing is not a dependency order, and a
# file added to the directory does nothing until a revision names it.
SCRIPTS = ("survey_window_grants_v001",)


def upgrade() -> None:
    """Apply this revision."""
    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Undo this revision."""
    op.execute("REVOKE SELECT, INSERT ON public.survey_window FROM pulse_app")
