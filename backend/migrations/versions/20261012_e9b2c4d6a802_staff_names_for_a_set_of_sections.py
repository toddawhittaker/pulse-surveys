"""staff names for a set of sections

Revision ID: e9b2c4d6a802
Revises: 7f679faf4b8d
Create Date: 2026-10-12 12:00:00.000000

E9-03, ADR 0201. `section_staff_names_v002.sql`: an overload of the staff-name
definer, `public.section_staff_names(uuid[], uuid, uuid, date)`, which answers a
set of sections in one call, one row per (section, role, person), and names each
section's instructors, its responses' authors, its course's lead, its
department's chair and its college's dean. v001's three-argument function stays
as it is. The owner, `pulse_staff_name_definer`, gains `SELECT` on
`role_assignment.college_id` and on `department (id, college_id)`, which the dean
row needs; the file re-grants v001's columns as well, which changes nothing.

**The downgrade** drops the overload and revokes the two reads this revision
added. It holds no data, so it needs no guard.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

revision: str = "e9b2c4d6a802"
down_revision: str | Sequence[str] | None = "7f679faf4b8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DROP_THE_OVERLOAD = "DROP FUNCTION public.section_staff_names(uuid[], uuid, uuid, date)"

# Only what this revision added: v001's grants stay, because v001 reads them.
REVOKE_THE_ADDED_READS = (
    "REVOKE SELECT (college_id) ON public.role_assignment FROM pulse_staff_name_definer",
    "REVOKE SELECT (id, college_id) ON public.department FROM pulse_staff_name_definer",
)


def upgrade() -> None:
    """Apply this revision: the set-based staff-name definer and its owner's two new reads."""
    op.execute(read_sql("section_staff_names_v002"))


def downgrade() -> None:
    """Reverse this revision: drop the overload and the two reads it added."""
    op.execute(DROP_THE_OVERLOAD)
    for statement in REVOKE_THE_ADDED_READS:
        op.execute(statement)
