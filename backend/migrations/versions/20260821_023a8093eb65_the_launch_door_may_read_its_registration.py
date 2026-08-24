"""the launch door may read its registration

Revision ID: 023a8093eb65
Revises: a702938fcc97
Create Date: 2026-08-21 12:00:00.000000

E0-18 builds the LTI launch door, and every launch it admits is resolved through
`public.lti_platform` and `public.lti_deployment`. The connection that resolves
it is `pulse_app`, which held no privilege on either table — E0-08 created them
for a launch flow that did not exist yet, so nothing had needed one. This
revision grants `SELECT` on the two, and nothing else.

The reasoning, including why this is a grant on a base table rather than a read
view and why no write privilege comes with it, is in
`lti_registration_grants_v001.sql`, which this revision executes.

**There is no schema change here at all**, so `alembic check` has nothing to
compare: a grant is not part of `Base.metadata` and autogenerate has never
emitted one. That is the ordinary state of every grants file in this tree
(`classification_grants_v001.sql`, `authz_grants_v001.sql`), and it is why
`tests/integration/test_identity_grants.py` pins what each runtime role holds as
an equality read out of the catalog — the drift gate cannot see this and a
hand-written catalog assertion can.

**This revision turns that equality red until its constant gains the two
entries**, and that is the designed cost rather than a surprise. The constant is
`RUNTIME_BASE_TABLE_PRIVILEGES` in that module, deliberately hand-written and
not derived from these `.sql` files, so that a widening cannot justify itself.
E0-18's pull request carries the widening and the sentence that makes it
legitimate.

**The downgrade revokes.** Both tables are E0-08's and survive this revision, so
unlike a grant on a table its own revision drops, this one would outlive its
downgrade. The two REVOKE statements are written here rather than as a second
`.sql` file: ADR 0041 makes a versioned file the immutable record of what an
upgrade applied, and an un-grant is not a record of anything.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "023a8093eb65"
down_revision: str | Sequence[str] | None = "a702938fcc97"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The scripts this revision runs. Written out rather than globbed, for the reason
# E0-10's revision gives: a directory listing is not a dependency order, and a
# file added to the directory does nothing until a revision names it.
SCRIPTS = ("lti_registration_grants_v001",)


def upgrade() -> None:
    """Apply this revision."""
    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Undo this revision."""
    op.execute("REVOKE SELECT ON public.lti_platform FROM pulse_app")
    op.execute("REVOKE SELECT ON public.lti_deployment FROM pulse_app")
