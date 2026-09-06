"""the passback read path gets its two indexes

Revision ID: c4a8e51db9f3
Revises: f3b7d05c9e42
Create Date: 2026-09-05 00:00:00.000000

E3-08's boundary round, DM-H1 and DM-M1. Two reads E3-06's participation sweep
makes on every run had no index behind them, and a missing index is the one class
of defect a correctness test cannot see: a sequential scan answers correctly.

**`ags_call (section_id, called_at)`** — DM-H1. `app.services.grading` records the
status a successful post was answered with by reading the newest `ags_call` row
belonging to that section, once **per delivery**. SPEC §6.1 puts a row here per
HTTP call this tool makes to a platform service — two per score post in the
ordinary case — and nothing purges the table before E13's retention pass, so the
read is a scan of a term's whole call history per student per week. This is the
same access path, on the same shape of table, that the E1 boundary review
measured as M5 against `nrps_call`: 2,006 buffers against 5 at a million rows.

**`section (term_id)`** — DM-M1. The sweep visits a section only while its term is
still open (`term.end_date + TERM_SWEEP_GRACE_DAYS >= today`), which is a join
from `section.term_id` on every run. Postgres indexes neither side of a foreign
key on its own, and this is the many side; neither unique constraint on `section`
serves it, because one leads with `course_id` and one with `id` and Postgres 17
has no skip scan. `app/models/org.py` carried a comment saying an index here was
report-generation rather than a hot path and that E2 would add one "if one turns
out to be needed, with a measurement". E3-06 made it a hot path; that comment is
rewritten in the same change as this revision.

**Both are plain column lists, and that is deliberate.** `a4d61c8f9b27` created
the `nrps_call` composite with a descending expression and stated the cost in its
own docstring — `alembic check` "sees an index by name and not by shape" — and
`d2f6a913c47e` reversed it to two plain columns so the drift gate could compare
the declaration. These two are declared plainly from the start for that reason.
Postgres serves `ORDER BY called_at DESC LIMIT 1` from an ascending index by a
backward scan at the same cost, so nothing is given up.

**Nothing else changes.** No column, no constraint, no grant: `pulse_app` already
holds `SELECT` and `INSERT` on `ags_call` and `SELECT` on `section`, and an index
is not a privilege. `downgrade()` drops exactly the two indexes this revision
creates, leaving a database at `f3b7d05c9e42` holding precisely the indexes that
revision left it holding.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a8e51db9f3"
down_revision: str | Sequence[str] | None = "f3b7d05c9e42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CALL_LOG = "ags_call"
CALL_LOG_INDEX = "ix_ags_call_section_id_called_at"

SECTION = "section"
SECTION_TERM_INDEX = "ix_section_term_id"


def upgrade() -> None:
    """Apply this revision: the two indexes the sweep's reads need."""
    op.create_index(CALL_LOG_INDEX, CALL_LOG, ["section_id", "called_at"], unique=False)
    op.create_index(SECTION_TERM_INDEX, SECTION, ["term_id"], unique=False)


def downgrade() -> None:
    """Reverse this revision: both indexes gone, and nothing else touched."""
    op.drop_index(SECTION_TERM_INDEX, table_name=SECTION)
    op.drop_index(CALL_LOG_INDEX, table_name=CALL_LOG)
