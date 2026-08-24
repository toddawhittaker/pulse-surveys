"""the reveal commits its record

Revision ID: b336333a2805
Revises: 7b41d2c9e6af
Create Date: 2026-08-20 00:00:00.000000

E0-26 item 1: the audit row and the identity read no longer come apart when the
caller rolls back (SPEC §4, §6.2; ADR 0001, ADR 0043, ADR 0071).

E0-10's `public.reveal_student_identity(uuid, uuid, uuid)` returned identity and
wrote the `audit_log` row in the caller's transaction, and Postgres has already
streamed the result rows to the client by the time the caller decides what to do
with that transaction — so `BEGIN; SELECT * FROM public.reveal_student_identity(…);
ROLLBACK;` returned the name and the address and left `audit_log` empty. This
revision replaces that function with two:

  - `public.record_identity_reveal(uuid, uuid, uuid) RETURNS uuid`, which
    records that a reveal is about to happen and hands back the row's id;
  - `public.reveal_student_identity(uuid) RETURNS TABLE (identity_name text,
    identity_email text)`, which answers only against a record whose writing
    transaction has committed.

**The three-argument function is dropped rather than left beside the new one.**
Postgres overloads on argument types, so creating the one-argument reveal does
not replace the old one, and a door that still opens the old way is not closed.

Nothing here is visible to `alembic check`: it compares `Base.metadata` against
the database, so it reads tables and columns and neither `pg_proc` nor an ACL.
`tests/integration/test_the_reveal_commits_its_record.py` and
`tests/integration/test_identity_grants.py` are the only readers, and the first
is `invariant`-marked so a skip is a build failure. ADR 0043's table measures the
gap; E0-20 item 3b carries it.

**The SQL is read from `backend/app/views_sql/` rather than written out here**,
for the reason `446183e8cc5f` gives at length: a `views_sql/` file carries a
version in its name and is never edited once a revision executes it, so the text
this revision runs is fixed by the file name (ADR 0041). Both files are new
versions rather than edits — `reveal_student_identity_v002.sql` and
`identity_grants_v002.sql` — and `v001` of each stays exactly as `446183e8cc5f`
applied it.

**`downgrade()` puts E0-10's door back, including its defect.** That is what a
downgrade is: the database ends at revision `7b41d2c9e6af` and the reveal there
is the three-argument one. The one thing the drop cannot carry with it is the
definer's new `SELECT` on `audit_log` — a privilege on a table that survives the
downgrade — so it is revoked by hand, guarded on the role existing, exactly as
`446183e8cc5f` revokes the rest.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "b336333a2805"
down_revision: str | Sequence[str] | None = "7b41d2c9e6af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The three-argument reveal, named with its argument types because that is what
# identifies a function in `pg_proc` and because the one-argument reveal created
# a moment later shares its name. No `IF EXISTS`: this revision follows the one
# that created it, so an absence here is a database in a state nobody planned and
# should stop the upgrade rather than be tidied over.
DROP_THE_OLD_DOOR = "DROP FUNCTION public.reveal_student_identity(uuid, uuid, uuid)"

# The scripts `upgrade()` runs, in the order it runs them: the functions before
# the grants that name them.
UPGRADE_SCRIPTS = ("reveal_student_identity_v002", "identity_grants_v002")

# What `downgrade()` runs to put E0-10's door back — the same two scripts one
# version earlier. `identity_grants_v001.sql` re-states every grant E0-10 made,
# which is idempotent for the ones this revision never touched and is what
# restores the owner and the `EXECUTE` on the three-argument function.
DOWNGRADE_SCRIPTS = ("reveal_student_identity_v001", "identity_grants_v001")

DROP_THE_NEW_DOOR = (
    "DROP FUNCTION IF EXISTS public.reveal_student_identity(uuid)",
    "DROP FUNCTION IF EXISTS public.record_identity_reveal(uuid, uuid, uuid)",
)

# The one privilege this revision writes on an object that outlives it, so the one
# thing `downgrade()` has to remove by hand — `446183e8cc5f`'s rule, applied to
# the grant this revision adds. Guarded on the role existing for the reason that
# revision measured: `REVOKE … FROM <role>` is an error rather than a no-op when
# the role is absent, and a downgrade is exactly the moment somebody is already
# dealing with a database in a state nobody planned.
REVOKE_THE_DEFINERS_READ_OF_THE_LOG = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_reveal_definer') THEN
            REVOKE SELECT ON public.audit_log FROM pulse_reveal_definer;
        END IF;
    END
    $$
"""


def upgrade() -> None:
    """Apply this revision."""
    op.execute(DROP_THE_OLD_DOOR)
    for script in UPGRADE_SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Undo this revision."""
    for statement in DROP_THE_NEW_DOOR:
        op.execute(statement)
    for script in DOWNGRADE_SCRIPTS:
        op.execute(read_sql(script))
    op.execute(REVOKE_THE_DEFINERS_READ_OF_THE_LOG)
