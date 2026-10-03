"""a teaching grant ends when the roster drops it

Revision ID: c5e8a1f3b9d4
Revises: a3f6c1d8e5b7
Create Date: 2026-10-03 00:00:00.000000

E5.1-02. SPEC §2.1 makes the teaching instructor LMS-owned, and until now the
roster sync only ever added that grant. This revision gives it the way to end one:

  - **`ended_teaching_grant`**, the append-only record of every ended grant: the
    assignment's own id (unique, and no foreign key, because the row it names is
    deleted), the person, the section, the role, the day it ended and the roster
    call that ended it. `pulse_app` is granted nothing on it.
  - **`teaching_grant_end_v001.sql`**, which creates the NOLOGIN owner
    `pulse_grant_end_definer` and the `SECURITY DEFINER` function
    `public.end_teaching_instructor`. The function deletes a section-scoped
    `INSTRUCTOR` row and writes its record in the same call, and refuses
    anything else. ADR 0183 records why the grant is deleted rather than
    end-dated.

The table is created first because the SQL file grants on it.

**The downgrade** drops the function and the table, and empties the owner role
and keeps it, which is E0-10's decision for `pulse_reveal_definer` and
`e2c94b6a1f70`'s for the roster definers: a NOLOGIN role holding nothing is
inert, and dropping a role fails against any object elsewhere in the cluster
that depends on it. Each revoke is guarded on the role existing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "c5e8a1f3b9d4"
down_revision: str | Sequence[str] | None = "a3f6c1d8e5b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENDED_TABLE = "ended_teaching_grant"

SCRIPT = "teaching_grant_end_v001"

# The existing enum type, named and never created here: `role_assignment.role`
# owns it.
ASSIGNMENT_ROLE = postgresql.ENUM(name="assignment_role", create_type=False)

# The rule, written here rather than imported, because a migration records what
# was applied and must not change when the model does.
ROLE_IS_INSTRUCTOR = "role = 'INSTRUCTOR'"

EMPTY_THE_DEFINER_ROLE = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_grant_end_definer') THEN
        REVOKE SELECT (id, section_id, response_code) ON public.nrps_call
            FROM pulse_grant_end_definer;
        REVOKE ALL ON public.nrps_call FROM pulse_grant_end_definer;
        REVOKE ALL ON public.role_assignment FROM pulse_grant_end_definer;
    END IF;
END
$$;
"""


def upgrade() -> None:
    """Create the ended-grant record, then the door that writes it."""
    op.create_table(
        ENDED_TABLE,
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("role", ASSIGNMENT_ROLE, nullable=False),
        sa.Column("ended_on", sa.Date(), nullable=False),
        sa.Column("nrps_call_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            ROLE_IS_INSTRUCTOR, name=op.f("ck_ended_teaching_grant_role_is_instructor")
        ),
        sa.ForeignKeyConstraint(
            ["nrps_call_id"],
            ["nrps_call.id"],
            name=op.f("fk_ended_teaching_grant_nrps_call_id_nrps_call"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_ended_teaching_grant_person_id_person"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["section.id"],
            name=op.f("fk_ended_teaching_grant_section_id_section"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ended_teaching_grant")),
        sa.UniqueConstraint("assignment_id", name=op.f("uq_ended_teaching_grant_assignment_id")),
    )
    for column in ("nrps_call_id", "person_id", "section_id"):
        op.create_index(
            op.f(f"ix_ended_teaching_grant_{column}"), ENDED_TABLE, [column], unique=False
        )

    op.execute(read_sql(SCRIPT))


def downgrade() -> None:
    """Close the door, drop the record, empty the owner and keep it."""
    op.execute("DROP FUNCTION IF EXISTS public.end_teaching_instructor(uuid, uuid, date)")
    for column in ("nrps_call_id", "person_id", "section_id"):
        op.drop_index(op.f(f"ix_ended_teaching_grant_{column}"), table_name=ENDED_TABLE)
    op.drop_table(ENDED_TABLE)
    op.execute(EMPTY_THE_DEFINER_ROLE)
