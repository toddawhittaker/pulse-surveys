"""the purview defect kind, and an index alembic check can compare

Revision ID: d2f6a913c47e
Revises: a4d61c8f9b27
Create Date: 2026-08-31 00:00:00.000000

E2-02, and two changes that travel together only because they are the same
ticket's schema.

**`launch_defect_kind` grows `context_outside_purview`.** The E1 boundary
review's M9: SPEC §7.3's leadership limb admitted any holder of a live
leadership assignment as a staff-launch trigger with no reference to the
launch's context, so a Lead Faculty enrolled as a Learner in a sibling lead's
course could bind that section and store its roster address permanently. The
limb now checks the launcher's own grant against the launched context
(`app.services.authz.leadership_grant_covers`, ADR 0108), and a launch that does
not reach it records this kind instead of binding. The label is added with `IF
NOT EXISTS`, which is what makes re-running the upgrade after a downgrade a
no-op — see the downgrade below.

**`ix_nrps_call_section_id_called_at_desc` becomes
`ix_nrps_call_section_id_called_at`.** `a4d61c8f9b27` created the descending
composite for M5's measured access path — 2,006 buffers per debounce probe
against 5 at a million rows — and stated the limit in its own docstring:
`alembic check` "sees an index by name and not by shape", because the direction
can only be written as a text expression and a text-expression index is not
comparable. So the drift gate that is supposed to catch this index being
dropped, renamed or re-declared read its key columns as `('section_id',)` and
could not compare the declaration at all. The E1 post-merge re-review carried
that as a finding (`docs/tickets/e2/carried-from-e1.md`), and this is its fix.

**The reversal costs the probe nothing, which is why it is available.** The
debounce asks for `ORDER BY called_at DESC LIMIT 1` within one `section_id`, and
Postgres serves that from an ascending index by a backward scan at the same
cost — the ordering of an index is not the ordering of the scan. What is bought
is that both key columns are now plain columns, so `check` compares them and the
declaration on `NrpsCall` is held to the database from here on.

**The create comes before the drop, and the reverse on the way back**, exactly
as `a4d61c8f9b27` ordered its own swap: the debounce probe runs on the request
path of every staff launch, and there is no moment inside either transaction
when `nrps_call` has no index leading with `section_id`.

**The downgrade leaves the label in place.** Postgres cannot remove a value from
an enum type, which is why `b8c41f7d2e05` takes the same stance for the two
kinds it added: the upgrade adds with `IF NOT EXISTS` so that re-running it after
a downgrade succeeds, and a database walked back to `a4d61c8f9b27` carries a
label no writer in that revision's code ever writes. The index half is a true
reversal — the descending composite back, the ascending one gone — so a database
at `a4d61c8f9b27` holds precisely the indexes that revision left it holding.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2f6a913c47e"
down_revision: str | Sequence[str] | None = "a4d61c8f9b27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "nrps_call"

# The kind this revision adds. Spelled out rather than imported from
# `app.models.lti`, for the reason every other revision here gives: a migration
# records what was applied on the day it ran, and a value read from today's code
# would change under a database that has already been migrated.
NEW_DEFECT_KIND = "context_outside_purview"

# The index this revision creates, and the one it replaces. Both are plain
# strings, and `op.f` is called inside the functions below rather than here:
# `op` is a proxy for the migration context and there is none while the revision
# map is importing this file, so a module-scope call raises `AttributeError:
# 'NoneType' object has no attribute 'f'` the moment anything asks the script
# directory for a head.
INDEX = "ix_nrps_call_section_id_called_at"
SUPERSEDED = "ix_nrps_call_section_id_called_at_desc"


def upgrade() -> None:
    """Apply this revision: the new defect kind, and the comparable index in."""
    op.execute(f"ALTER TYPE launch_defect_kind ADD VALUE IF NOT EXISTS '{NEW_DEFECT_KIND}'")
    op.create_index(INDEX, TABLE, ["section_id", "called_at"], unique=False)
    op.drop_index(SUPERSEDED, table_name=TABLE)


def downgrade() -> None:
    """Reverse this revision: the descending composite back, the label left standing."""
    op.create_index(SUPERSEDED, TABLE, ["section_id", sa.text("called_at DESC")])
    op.drop_index(INDEX, table_name=TABLE)
