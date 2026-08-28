"""the assignment view publishes each assignment's doors

Revision ID: f3a5c92d8e14
Revises: e2c94b6a1f70
Create Date: 2026-08-27 00:00:00.000000

E1-13: the landing view is resolved from the assignment model, filtered by the
door the person entered at (SPEC §2.1; ADR 0026, ADR 0028, ADR 0041).

`public.assignment_scope` withheld ADR 0026's two generated entry-door columns,
and `assignment_scope_v001.sql` said so at the time: "a later ticket adding, say,
a validity window to an assignment has to write a `_v002` of this file before any
read path can see it." E1-13 is that ticket. `app.services.authz.resolve_landing`
filters a person's live assignments by `permits_launch` or `permits_web_login`,
so a Care assignment cannot open an LTI launch — a fact about the row rather than
a branch in Python, which is what ADR 0026 decided and what this revision makes
readable.

**The view is dropped before it is created.** `CREATE OR REPLACE VIEW` cannot add
a column in the middle of a projection, and this version adds two at the end of
one; dropping and re-creating is the shape `446183e8cc5f` and `b336333a2805`
already use for a re-versioned object, and it is the reason the grant has to be
re-stated below.

**A privilege cannot outlive the object it is on**, so `DROP VIEW` takes
`pulse_app`'s `SELECT` with it and `authz_grants_v002.sql` re-makes it. Without
that the chokepoint would hold nothing on the view it reads every assignment
through, and every landing in the product would resolve to the no-access page.

**The SQL is read from `backend/app/views_sql/` rather than written out here**,
for the reason `446183e8cc5f` gives at length: a `views_sql/` file carries a
version in its name and is never edited once a revision executes it, so the text
this revision runs is fixed by the file name (ADR 0041). Both files are new
versions rather than edits, and `v001` of each stays exactly as `9a71c4be0d3f`
applied it.

**`alembic check` sees this.** The view is not in `Base.metadata` — nothing in
this repository maps a view — so the comparison is unaffected either way; what it
does compare is `public.role_assignment`, whose two generated columns this
revision does not touch. `tests/integration/test_landing_resolves_from_assignments.py::test_the_assignment_scope_view_publishes_a_door_permission_per_role`
is the assertion that the columns arrive and that `pulse_app` can read them, over
the application connection rather than a superuser one.

**`downgrade()` puts v001 back**, view and grant together, which leaves a database
at revision `e2c94b6a1f70` with exactly the view that revision left it holding.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "f3a5c92d8e14"
down_revision: str | Sequence[str] | None = "e2c94b6a1f70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The view this revision re-versions. No `IF EXISTS` and no `CASCADE`: `9a71c4be0d3f`
# created it and nothing in this tree builds anything on top of it, so an absence
# here is a database in a state nobody planned and should stop the upgrade rather
# than be tidied over, and a dependent object nobody knows about should stop it too.
DROP_THE_VIEW = "DROP VIEW public.assignment_scope"

# The scripts `upgrade()` runs, in the order it runs them: the view before the
# grant that names it.
UPGRADE_SCRIPTS = ("assignment_scope_v002", "authz_grants_v002")

# What `downgrade()` runs to put E0-11's view back — the same two scripts one
# version earlier. `authz_grants_v001.sql` re-states all three of the chokepoint's
# grants, which is idempotent for the two this revision never touched and is what
# restores the one it dropped.
DOWNGRADE_SCRIPTS = ("assignment_scope_v001", "authz_grants_v001")


def upgrade() -> None:
    """Apply this revision."""
    op.execute(DROP_THE_VIEW)
    for script in UPGRADE_SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Undo this revision."""
    op.execute(DROP_THE_VIEW)
    for script in DOWNGRADE_SCRIPTS:
        op.execute(read_sql(script))
