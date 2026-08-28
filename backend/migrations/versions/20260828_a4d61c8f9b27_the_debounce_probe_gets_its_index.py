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

**What this revision does not do.** `ix_nrps_call_section_id` — the single-column
index `e2c94b6a1f70` created — is left exactly where it is. The index below leads
with the same column and therefore serves everything that one served, so it is now
redundant and costs a write on every call row; dropping it is a second decision with
a second downgrade to get right, and it is proposed in this batch's pull request
rather than taken here.

**`alembic check` sees an index by name and not by shape.** With this revision
removed, `check` reports the declaration on `NrpsCall` as an added index; with it in
place `check` is clean. What `check` cannot compare is the expression — it reads the
declaration's key columns as `('section_id',)` — so the assertion that the *right*
index reached the database is
`tests/integration/test_the_nrps_call_log_is_indexed_for_the_debounce_probe.py`,
which reads each key column's position and descending flag out of `pg_index`.

**`downgrade()` drops exactly this index** and nothing else, leaving a database at
`f3a5c92d8e14` with precisely the indexes that revision left it holding.
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
INDEX = "ix_nrps_call_section_id_called_at_desc"


def upgrade() -> None:
    """Apply this revision."""
    op.create_index(INDEX, TABLE, ["section_id", sa.text("called_at DESC")])


def downgrade() -> None:
    """Reverse this revision."""
    op.drop_index(INDEX, table_name=TABLE)
