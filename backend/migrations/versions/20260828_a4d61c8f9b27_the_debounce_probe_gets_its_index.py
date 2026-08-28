"""the debounce probe gets its index

Revision ID: a4d61c8f9b27
Revises: f3a5c92d8e14
Create Date: 2026-08-28 00:00:00.000000

The E1 boundary review's M5. `app.services.roster_sync.request_section_sync` asks
`nrps_call` for the newest `called_at` belonging to one section, and it asks on the
request path of every staff launch while somebody waits (SPEC §7.3's debounce, ADR
0095). The only index the table carried was on `section_id` alone, so the probe had
to read every call row that section had ever made to find the newest one.

Measured on a scratch database at a million rows laid out hour-major — which is how
an hourly walk over every section actually lays them down — the probe touched 2,006
buffers against `section_id` alone and 5 against `(section_id, called_at DESC)`. The
table grows all term, because nothing purges it until E13's retention pass.

**Both halves of the shape are the point.** `section_id` leads because that is the
column the probe filters on and Postgres 17 has no skip scan, so an index that
merely *contains* the column serves no lookup by it. `called_at` is stored
descending so that the row the probe wants sits at the near end of the section's
range; ascending, the planner walks to the section's oldest call to find its newest.

**`ix_nrps_call_section_id` goes, in the same revision.** The single-column index
`e2c94b6a1f70` created leads with the same column as the one below, which therefore
serves every lookup it served — so keeping both bought nothing and cost a second
index write on every call row, and there is one row per HTTP call per section every
hour. E0-06 dropped `ix_section_course_id` for exactly this reason, and `section`,
`college.institution_id`, `department.college_id` and `course.prefix_id` are all
left unindexed on the same argument: an index merely contained by another index's
leading column is a write nobody reads.

**The order within each direction matters.** The composite is created *before* the
old index is dropped, and re-created *after* it on the way back, so there is no
moment inside either transaction when `nrps_call` has no index on `section_id` —
the debounce probe runs on the request path of every staff launch, and a migration
window is not a reason to hand it a sequential scan.

**`alembic check` sees an index by name and not by shape.** With this revision
removed, `check` reports the declaration on `NrpsCall` as an added index; with it in
place `check` is clean. What `check` cannot compare is the expression — it reads the
declaration's key columns as `('section_id',)` — so the assertion that the *right*
index reached the database is
`tests/integration/test_the_nrps_call_log_is_indexed_for_the_debounce_probe.py`,
which reads each key column's position and descending flag out of `pg_index`.

**`downgrade()` restores exactly what was here** — the single-column index back,
the composite gone, nothing else touched — leaving a database at `f3a5c92d8e14`
with precisely the indexes that revision left it holding. Verified rather than
claimed: a scratch round trip compares every index and column in `public` before
and after, and `upgrade → downgrade → upgrade` is the identity.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4d61c8f9b27"
down_revision: str | Sequence[str] | None = "f3a5c92d8e14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "nrps_call"

# The index this revision creates, and the one it supersedes. Both are plain
# strings: `e2c94b6a1f70` created the second through `op.f`, which marks a name as
# already final so the naming convention is not applied to it twice, and the two
# spell the same thing. `op.f` is called **inside** the functions below where it is
# used at all, because `op` is a proxy for the migration context and there is no
# context while the revision map is importing this file — a module-scope call
# raises `AttributeError: 'NoneType' object has no attribute 'f'` the moment
# anything asks the script directory for a head.
INDEX = "ix_nrps_call_section_id_called_at_desc"
SUPERSEDED = "ix_nrps_call_section_id"


def upgrade() -> None:
    """Apply this revision: the composite in, the index it subsumes out."""
    op.create_index(INDEX, TABLE, ["section_id", sa.text("called_at DESC")])
    op.drop_index(op.f(SUPERSEDED), table_name=TABLE)


def downgrade() -> None:
    """Reverse this revision: the single-column index back, the composite out."""
    op.create_index(op.f(SUPERSEDED), TABLE, ["section_id"], unique=False)
    op.drop_index(INDEX, table_name=TABLE)
