"""a course is led only by a lead faculty holder, and audit rows name their role and scope

Revision ID: e9b8c0d2e417
Revises: e9e5b7d9f605
Create Date: 2026-10-12 17:00:00.000000

E9-14, from the E9 boundary review. Two changes:

  - `people_graph_v003.sql` replaces `admin_map_lead_course` and
    `admin_revoke_role`, same names and signatures, so a course is mapped only to
    a person holding a `LEAD_FACULTY` assignment and a `LEAD_FACULTY`
    assignment is not revoked while its person still has mappings. Two new
    named refusals, `admin_people.lead_needs_the_lead_role` and
    `admin_people.lead_still_leads_courses` (the second carries the count);
  - two checks on `audit_log`. `an_admin_write_names_its_role_and_scope`, two
    way: a `ROLE_GRANTED`, `ROLE_REVOKED`, `REPORTS_TO_SET` or
    `LEAD_MAPPING_CHANGED` row carries a role and a scope node, and no other row
    carries both. `a_linkage_names_no_scope`: a `WEB_LOGIN_LINKAGE_CHANGED` row
    carries no scope node. Every row the definers have written already holds to
    both, so the checks are added as validated.

**The downgrade** restores v001's two definitions, written out below character
for character with `CREATE FUNCTION` changed to `CREATE OR REPLACE FUNCTION`:
a migration records what was applied on the day it ran, so the downgrade
reinstates that and not whatever the database holds. `CREATE OR REPLACE` keeps
each function's owner and grant. Then it drops the two checks. Neither change
holds data, so it needs no guard.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

revision: str = "e9b8c0d2e417"
down_revision: str | Sequence[str] | None = "e9e5b7d9f605"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUDIT_LOG = "audit_log"

# Spelled out rather than read from `app.models.audit`: a migration records what
# was applied on the day it ran (E6-01's reasoning).
ROLE_AND_SCOPE_CHECK = "an_admin_write_names_its_role_and_scope"
ROLE_AND_SCOPE_CHECK_RULE = (
    "(action IN ('ROLE_GRANTED', 'ROLE_REVOKED', 'REPORTS_TO_SET', 'LEAD_MAPPING_CHANGED')) "
    "= (role IS NOT NULL AND scope_node_id IS NOT NULL)"
)
LINKAGE_CHECK = "a_linkage_names_no_scope"
LINKAGE_CHECK_RULE = "action <> 'WEB_LOGIN_LINKAGE_CHANGED' OR scope_node_id IS NULL"

# `people_graph_v001.sql`'s W4, as revision `e9a1d0c3f201` applied it.
V001_REVOKE_ROLE = """
CREATE OR REPLACE FUNCTION public.admin_revoke_role(
    in_actor_person_id uuid,
    in_assignment_id uuid
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    held_role public.assignment_role;
    revoked_person_id uuid;
    revoked_role public.assignment_role;
    revoked_scope_node_id uuid;
    reporting_count bigint;
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM public.role_assignment AS acting
         WHERE acting.person_id = in_actor_person_id
           AND acting.role = 'ADMIN'
    ) THEN
        RAISE EXCEPTION 'admin_people.actor_not_an_admin' USING ERRCODE = 'raise_exception';
    END IF;

    SELECT held.role INTO held_role
      FROM public.role_assignment AS held
     WHERE held.id = in_assignment_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'admin_people.no_such_assignment' USING ERRCODE = 'raise_exception';
    END IF;

    IF held_role = 'INSTRUCTOR' THEN
        RAISE EXCEPTION 'admin_people.instructor_is_lms_owned' USING ERRCODE = 'raise_exception';
    END IF;

    -- `reports_to` is the only reference to this table, so a foreign-key refusal
    -- is assignments still reporting to this one. They are counted after the
    -- refusal; if none is found (they were re-pointed in between), the original
    -- error is raised again rather than a count of zero.
    BEGIN
        DELETE FROM public.role_assignment AS revoked
         WHERE revoked.id = in_assignment_id
        RETURNING revoked.person_id,
                  revoked.role,
                  coalesce(revoked.institution_id, revoked.college_id, revoked.department_id,
                           revoked.course_id, revoked.section_id)
             INTO revoked_person_id, revoked_role, revoked_scope_node_id;
    EXCEPTION
        WHEN foreign_key_violation THEN
            SELECT count(*) INTO reporting_count
              FROM public.role_assignment AS below
             WHERE below.reports_to = in_assignment_id;
            IF reporting_count = 0 THEN
                RAISE;
            END IF;
            RAISE EXCEPTION 'admin_people.assignment_has_reports'
                USING ERRCODE = 'raise_exception', DETAIL = reporting_count::text;
    END;

    -- Deleted by a concurrent revoke between the read above and the delete.
    IF revoked_person_id IS NULL THEN
        RAISE EXCEPTION 'admin_people.no_such_assignment' USING ERRCODE = 'raise_exception';
    END IF;

    INSERT INTO public.audit_log (action, actor_person_id, subject_person_id, role, scope_node_id)
    VALUES ('ROLE_REVOKED', in_actor_person_id, revoked_person_id, revoked_role,
            revoked_scope_node_id);
END;
$$;
"""

# `people_graph_v001.sql`'s W6, as revision `e9a1d0c3f201` applied it.
V001_MAP_LEAD_COURSE = """
CREATE OR REPLACE FUNCTION public.admin_map_lead_course(
    in_actor_person_id uuid,
    in_person_id uuid,
    in_course_id uuid
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM public.role_assignment AS acting
         WHERE acting.person_id = in_actor_person_id
           AND acting.role = 'ADMIN'
    ) THEN
        RAISE EXCEPTION 'admin_people.actor_not_an_admin' USING ERRCODE = 'raise_exception';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM public.person AS named WHERE named.id = in_person_id) THEN
        RAISE EXCEPTION 'admin_people.no_such_person' USING ERRCODE = 'raise_exception';
    END IF;

    -- The person was checked above, so a foreign-key refusal here is the course.
    BEGIN
        INSERT INTO public.lead_faculty_mapping (person_id, course_id)
        VALUES (in_person_id, in_course_id);
    EXCEPTION
        WHEN unique_violation THEN
            RAISE EXCEPTION 'admin_people.course_already_led' USING ERRCODE = 'raise_exception';
        WHEN foreign_key_violation THEN
            RAISE EXCEPTION 'admin_people.no_such_course' USING ERRCODE = 'raise_exception';
    END;

    INSERT INTO public.audit_log (action, actor_person_id, subject_person_id, role, scope_node_id)
    VALUES ('LEAD_MAPPING_CHANGED', in_actor_person_id, in_person_id, 'LEAD_FACULTY',
            in_course_id);
END;
$$;
"""


def upgrade() -> None:
    """Apply this revision: the two checks, then the two definers."""
    op.create_check_constraint(
        op.f(f"ck_audit_log_{ROLE_AND_SCOPE_CHECK}"), AUDIT_LOG, ROLE_AND_SCOPE_CHECK_RULE
    )
    op.create_check_constraint(op.f(f"ck_audit_log_{LINKAGE_CHECK}"), AUDIT_LOG, LINKAGE_CHECK_RULE)
    op.execute(read_sql("people_graph_v003"))


def downgrade() -> None:
    """Reverse this revision: v001's two definers, then the checks dropped."""
    op.execute(V001_REVOKE_ROLE)
    op.execute(V001_MAP_LEAD_COURSE)
    op.drop_constraint(op.f(f"ck_audit_log_{LINKAGE_CHECK}"), AUDIT_LOG, type_="check")
    op.drop_constraint(op.f(f"ck_audit_log_{ROLE_AND_SCOPE_CHECK}"), AUDIT_LOG, type_="check")
