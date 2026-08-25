"""the tool may read its own signing key

Revision ID: d3cb2cf2204e
Revises: 34bf86adb774
Create Date: 2026-08-25 14:57:15.247873

E1-06 publishes the tool's key set at `GET /lti/jwks`, which reads
`public.tool_signing_key` on the connection `pulse_app` holds. E1-05 created that
table and granted the runtime role nothing on it deliberately — ADR 0082: "a
runtime role holding read access to a private key it never opens is a credential
at rest with no owner" — so this revision is where the grant lands, with the code
that spends it. `SELECT`, and nothing else.

The reasoning, including why this is a grant on a base table rather than a read
view and why no write privilege comes with it, is in
`tool_signing_key_grants_v001.sql`, which this revision executes.

**There is no schema change here at all**, so `alembic check` has nothing to
compare: a grant is not part of `Base.metadata` and autogenerate has never
emitted one. That is the ordinary state of every grants file in this tree
(`lti_registration_grants_v001.sql`, `classification_grants_v001.sql`), and it is
why `tests/integration/test_identity_grants.py` pins what each runtime role holds
as an equality read out of the catalog — the drift gate cannot see this and a
hand-written catalog assertion can.

**This revision turns that equality red until its constant gains the entry**, and
that is the designed cost rather than a surprise. The constant is
`RUNTIME_BASE_TABLE_PRIVILEGES` in that module, deliberately hand-written and not
derived from these `.sql` files, so that a widening cannot justify itself. E1-06
carries the widening and the paragraph that makes it legitimate.

**The downgrade revokes.** The table is E1-05's and survives this revision, so
unlike a grant on a table its own revision drops, this one would outlive its
downgrade. The `REVOKE` is written here rather than as a second `.sql` file: ADR
0041 makes a versioned file the immutable record of what an upgrade applied, and
an un-grant is not a record of anything.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "d3cb2cf2204e"
down_revision: str | Sequence[str] | None = "34bf86adb774"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The scripts this revision runs. Written out rather than globbed, for the reason
# E0-10's revision gives: a directory listing is not a dependency order, and a
# file added to the directory does nothing until a revision names it.
SCRIPTS = ("tool_signing_key_grants_v001",)


def upgrade() -> None:
    """Apply this revision."""
    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Undo this revision."""
    op.execute("REVOKE SELECT ON public.tool_signing_key FROM pulse_app")
