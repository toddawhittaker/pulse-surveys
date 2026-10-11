"""the application reads two columns of the ended grant record

Revision ID: b7d2e94c1a05
Revises: e403cc44bfc0
Create Date: 2026-10-11 00:00:00.000000

E6-09, done-when 5, and the ruling on dispute E6-09-01 (option A). ADR 0190's
taught-section rule keeps a lead's or a chair's own taught sections out of their
review queue and exclusion log, and "taught" has to include a grant the roster
has since ended: the person read that section's comments as its instructor, and
must not read its held comments as a leader the day after. Once the roster ends
a grant its `role_assignment` row is deleted (ADR 0183), so `ended_teaching_grant`
is the only record that the person taught the section.

So `pulse_app` gains `SELECT (person_id, section_id)` on that table, read by
`app.services.authz.taught_or_once_taught_section_ids`, and nothing else. The
record's protection is unchanged: `pulse_app` still holds no `INSERT`, `UPDATE`
or `DELETE` on it, so the application cannot forge, re-date or erase an ending,
and every ending is still written only by `public.end_teaching_instructor`.

**The downgrade** revokes exactly that grant, which loses no data.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b7d2e94c1a05"
down_revision: str | Sequence[str] | None = "e403cc44bfc0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANT_THE_TWO_COLUMNS = (
    "GRANT SELECT (person_id, section_id) ON public.ended_teaching_grant TO pulse_app"
)
REVOKE_THE_TWO_COLUMNS = (
    "REVOKE SELECT (person_id, section_id) ON public.ended_teaching_grant FROM pulse_app"
)


def upgrade() -> None:
    """Grant `pulse_app` a read of who taught which section, and nothing more."""
    op.execute(GRANT_THE_TWO_COLUMNS)


def downgrade() -> None:
    """Revoke exactly the two-column read this revision granted."""
    op.execute(REVOKE_THE_TWO_COLUMNS)
