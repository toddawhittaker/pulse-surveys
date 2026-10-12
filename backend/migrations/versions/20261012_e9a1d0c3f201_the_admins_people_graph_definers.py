"""the admin's people-graph definers

Revision ID: e9a1d0c3f201
Revises: 7f679faf4b8d
Create Date: 2026-10-12 12:00:00.000000

E9-02, ADR 0200. The admin's writes to the people graph and the admin's reads
under the People & reporting editor (SPEC §6.3), and the audit row each write
leaves:

  - five new `audit_action` values, one per kind of audited write:
    `ROLE_GRANTED`, `ROLE_REVOKED`, `REPORTS_TO_SET`, `LEAD_MAPPING_CHANGED` and
    `WEB_LOGIN_LINKAGE_CHANGED`. Added in an autocommit block, because
    PostgreSQL refuses to use an enum value in the transaction that added it;
  - three nullable columns on `audit_log`: `subject_person_id` (a foreign key to
    `person`, `RESTRICT`, indexed), `role` and `scope_node_id` (no foreign key:
    `role` says which table the id names);
  - `subject_user_id` loses `NOT NULL`, as its own column comment said the
    ticket adding an action that names no student would do. Two checks keep the
    two shapes of row apart: a reveal names its student, and an admin write names
    its person;
  - `people_graph_v001.sql`: the nine write and three read definers, their
    NOLOGIN owner `pulse_people_graph_definer` and its grants, and `EXECUTE` for
    `pulse_app`.

**The downgrade refuses while any audit row records an admin write.** Going down
drops the columns those rows depend on, and the rows are the control the E9 owner
ruling makes the audit (every Care and Admin grant). So it raises `RuntimeError`
before touching anything, as `20261011_2c3d5a0de424` does. Otherwise it drops the
twelve functions, empties their owner (the role itself stays, inert, as every
earlier definer owner does: `DROP ROLE` fails against any object elsewhere in the
cluster), drops the checks, restores `NOT NULL`, and drops the columns. The five
enum values stay: PostgreSQL cannot drop an enum value, and `ADD VALUE IF NOT
EXISTS` makes the next upgrade a no-op for them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.views_sql import read_sql

revision: str = "e9a1d0c3f201"
down_revision: str | Sequence[str] | None = "7f679faf4b8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUDIT_LOG = "audit_log"

NEW_ACTIONS = (
    "ROLE_GRANTED",
    "ROLE_REVOKED",
    "REPORTS_TO_SET",
    "LEAD_MAPPING_CHANGED",
    "WEB_LOGIN_LINKAGE_CHANGED",
)

# Spelled out rather than read from `app.models.audit`: a migration records what
# was applied on the day it ran (E6-01's reasoning).
REVEAL_CHECK = "a_reveal_names_its_student"
REVEAL_CHECK_RULE = "action <> 'IDENTITY_REVEAL' OR subject_user_id IS NOT NULL"
ADMIN_WRITE_CHECK = "an_admin_write_names_its_person"
ADMIN_WRITE_CHECK_RULE = "action = 'IDENTITY_REVEAL' OR subject_person_id IS NOT NULL"

DROP_THE_DEFINERS = (
    "DROP FUNCTION public.admin_create_person(uuid, text, text)",
    "DROP FUNCTION public.admin_edit_person(uuid, uuid, text, text)",
    "DROP FUNCTION public.admin_grant_role(uuid, uuid, public.assignment_role, uuid)",
    "DROP FUNCTION public.admin_revoke_role(uuid, uuid)",
    "DROP FUNCTION public.admin_set_reports_to(uuid, uuid, uuid)",
    "DROP FUNCTION public.admin_map_lead_course(uuid, uuid, uuid)",
    "DROP FUNCTION public.admin_unmap_lead_course(uuid, uuid)",
    "DROP FUNCTION public.admin_link_web_login(uuid, uuid, text, text)",
    "DROP FUNCTION public.admin_unlink_web_login(uuid, uuid)",
    "DROP FUNCTION public.admin_read_people(uuid)",
    "DROP FUNCTION public.admin_read_role_assignments(uuid)",
    "DROP FUNCTION public.admin_read_lead_mappings(uuid)",
)

# Dropping the three audit columns would take only the grants on those columns
# with it, so every grant the owner holds is revoked by name.
EMPTY_THE_DEFINER_ROLE = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_people_graph_definer'
    ) THEN
        REVOKE SELECT (id, identity_name, category),
               INSERT (identity_name, category),
               UPDATE (identity_name, category)
            ON public.person FROM pulse_people_graph_definer;
        REVOKE SELECT, DELETE ON public.role_assignment FROM pulse_people_graph_definer;
        REVOKE INSERT (person_id, role, institution_id, college_id, department_id, course_id,
                       section_id),
               UPDATE (reports_to)
            ON public.role_assignment FROM pulse_people_graph_definer;
        REVOKE SELECT, DELETE ON public.lead_faculty_mapping FROM pulse_people_graph_definer;
        REVOKE INSERT (person_id, course_id)
            ON public.lead_faculty_mapping FROM pulse_people_graph_definer;
        REVOKE SELECT, DELETE ON public.web_login_subject FROM pulse_people_graph_definer;
        REVOKE INSERT (idp_issuer, idp_subject, person_id)
            ON public.web_login_subject FROM pulse_people_graph_definer;
        REVOKE INSERT (action, actor_person_id, subject_person_id, role, scope_node_id)
            ON public.audit_log FROM pulse_people_graph_definer;
    END IF;
END
$$;
"""


def upgrade() -> None:
    """Apply this revision: the audit actions and columns, then the definers."""
    with op.get_context().autocommit_block():
        for action in NEW_ACTIONS:
            op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{action}'")

    op.add_column(AUDIT_LOG, sa.Column("subject_person_id", sa.Uuid(), nullable=True))
    op.add_column(
        AUDIT_LOG,
        sa.Column(
            "role",
            postgresql.ENUM(name="assignment_role", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(AUDIT_LOG, sa.Column("scope_node_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_audit_log_subject_person_id_person"),
        AUDIT_LOG,
        "person",
        ["subject_person_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_audit_log_subject_person_id"), AUDIT_LOG, ["subject_person_id"], unique=False
    )

    op.alter_column(AUDIT_LOG, "subject_user_id", existing_type=sa.Uuid(), nullable=True)
    op.create_check_constraint(op.f(f"ck_audit_log_{REVEAL_CHECK}"), AUDIT_LOG, REVEAL_CHECK_RULE)
    op.create_check_constraint(
        op.f(f"ck_audit_log_{ADMIN_WRITE_CHECK}"), AUDIT_LOG, ADMIN_WRITE_CHECK_RULE
    )

    op.execute(read_sql("people_graph_v001"))


def downgrade() -> None:
    """Reverse this revision.

    Raises `RuntimeError`, having changed nothing, when `audit_log` holds a row
    whose action is not `IDENTITY_REVEAL`: going down would destroy what it
    records.
    """
    connection = op.get_bind()
    # Writes to `audit_log` are blocked from here to the commit (`SHARE` mode lets
    # reads through), so no admin write can land between the count and the drop.
    connection.execute(sa.text(f"LOCK TABLE public.{AUDIT_LOG} IN SHARE MODE"))
    held = connection.execute(
        sa.text(
            f"SELECT count(*) FROM public.{AUDIT_LOG} "  # noqa: S608
            "WHERE action <> 'IDENTITY_REVEAL'"
        )
    ).scalar_one()
    if held:
        raise RuntimeError(
            "This database holds audit rows recording the admin's people-graph writes (role "
            "grants and revocations, reporting lines, lead mappings and web-login linkages): "
            f"{held} of them. Going below this revision drops the columns those rows name their "
            "subject, role and scope in, so it would destroy the record of every Care and Admin "
            "grant. Nothing was changed. Keep the database at this revision, or export those "
            "rows and remove them deliberately first."
        )

    for statement in DROP_THE_DEFINERS:
        op.execute(statement)
    op.execute(EMPTY_THE_DEFINER_ROLE)

    op.drop_constraint(op.f(f"ck_audit_log_{ADMIN_WRITE_CHECK}"), AUDIT_LOG, type_="check")
    op.drop_constraint(op.f(f"ck_audit_log_{REVEAL_CHECK}"), AUDIT_LOG, type_="check")
    op.alter_column(AUDIT_LOG, "subject_user_id", existing_type=sa.Uuid(), nullable=False)

    op.drop_index(op.f("ix_audit_log_subject_person_id"), table_name=AUDIT_LOG)
    op.drop_constraint(
        op.f("fk_audit_log_subject_person_id_person"), AUDIT_LOG, type_="foreignkey"
    )
    op.drop_column(AUDIT_LOG, "scope_node_id")
    op.drop_column(AUDIT_LOG, "role")
    op.drop_column(AUDIT_LOG, "subject_person_id")
