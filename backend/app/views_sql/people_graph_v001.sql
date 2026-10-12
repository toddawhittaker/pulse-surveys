-- The admin's writes to the people graph, and the admin's reads under the editor
-- — E9-02, ADR 0200.
--
-- SPEC §6.3 puts the People & reporting editor and the Lead Faculty mapping table
-- in the admin console. `pulse_app` holds no write on `person`, `role_assignment`,
-- `lead_faculty_mapping` or `web_login_subject`, and must not: a grant cannot
-- require the caller to be an admin, cannot refuse an `INSTRUCTOR` row, and cannot
-- make a write and its `audit_log` row one transaction. So every write is one of
-- the nine functions below, and the admin's three reads are three more.
--
-- **What the admin check here is worth.** The acting admin's person key is each
-- function's first argument, and the function checks that the key holds a live
-- `ADMIN` assignment. `pulse_app` supplies that key, and the database cannot tell
-- whether it is the session's own. So this check stops a write that names a
-- non-admin key, and nothing more: the real check is the route, `require_admin`
-- in `app/api/deps.py`, with the key taken from the verified session only.
--
-- **Every Pulse-owned role is grantable, to anyone, the acting admin included**
-- (the E9 owner's ruling 1). There is no refusal of `CARE`, of `ADMIN`, or of a
-- grant to oneself. The control is the audit row: every grant, revocation, edge
-- change, mapping change and linkage change writes exactly one `audit_log` row in
-- the same transaction. **That insert sits outside every exception block, with no
-- handler around it**, so an insert that fails fails the whole call and the write
-- is rolled back with it. Creating and editing a person record is not audited.
--
-- **`INSTRUCTOR` is refused** (breakdown decision 11): a teaching grant is the
-- roster sync's, written by `record_teaching_instructor` and ended by
-- `end_teaching_instructor`. Granting one, revoking one, and giving one a parent
-- are each refused here.
--
-- **Revoking deletes** (ruling 7). The `RESTRICT` on `reports_to` refuses to
-- delete an assignment others report to; the revoke turns that refusal into a
-- named one carrying the children's count.
--
-- **How a refusal reaches the caller.** Every named refusal is
-- `RAISE EXCEPTION '<copy key>' USING ERRCODE = 'raise_exception'`, SQLSTATE
-- P0001, whose message is exactly a key in `app/copy/admin_people.py` and names no
-- person and no id. The children's count travels in the detail field, as digits.
-- A missing grant answers 42501 and a broken constraint class 23, so neither can
-- be mistaken for a named refusal. Only the one write statement in each function
-- sits inside a `BEGIN ... EXCEPTION` block, and each handler names the condition
-- it translates; anything else reaches the caller unchanged.
--
-- **One translation is wider than its name.** The edge write catches
-- `check_violation` and answers `edge_does_not_climb`. ADR 0044's trigger also
-- raises `check_violation` when the transaction is REPEATABLE READ, so a write
-- refused for that reason is reported as an edge that does not climb. The
-- application runs READ COMMITTED; ADR 0200 records the cost.
--
-- **The reads answer staff records only.** Names, categories, the web-login
-- issuer, assignments with their scope and parent, and mappings. Never
-- `person.user_id` (one step from a student's LMS key), never `idp_subject`
-- (marked identity-bearing on its table), never a `user_identity` column. A
-- caller whose key holds no live `ADMIN` assignment gets zero rows, not an error.
--
-- The owner is `pulse_people_graph_definer`, a NOLOGIN role that exists for
-- nothing else (ADR 0043: one role per door). Its privileges are the list below
-- and nothing on `user_identity`. It holds `SELECT` on all of `role_assignment`
-- because ADR 0044's trigger runs with the inserting role's rights and reads the
-- graph. It holds no `SELECT` on `audit_log`, so no insert there uses `RETURNING`.
--
-- SET search_path names pg_temp last (ADR 0027), every relation is
-- schema-qualified, parameters are typed, and there is no dynamic SQL.

DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_people_graph_definer'
    ) THEN
        CREATE ROLE pulse_people_graph_definer NOLOGIN;
    END IF;
END
$do$;

GRANT SELECT (id, identity_name, category),
      INSERT (identity_name, category),
      UPDATE (identity_name, category)
    ON public.person TO pulse_people_graph_definer;
GRANT SELECT, DELETE ON public.role_assignment TO pulse_people_graph_definer;
GRANT INSERT (person_id, role, institution_id, college_id, department_id, course_id, section_id),
      UPDATE (reports_to)
    ON public.role_assignment TO pulse_people_graph_definer;
GRANT SELECT, DELETE ON public.lead_faculty_mapping TO pulse_people_graph_definer;
GRANT INSERT (person_id, course_id) ON public.lead_faculty_mapping TO pulse_people_graph_definer;
GRANT SELECT, DELETE ON public.web_login_subject TO pulse_people_graph_definer;
GRANT INSERT (idp_issuer, idp_subject, person_id)
    ON public.web_login_subject TO pulse_people_graph_definer;
GRANT INSERT (action, actor_person_id, subject_person_id, role, scope_node_id)
    ON public.audit_log TO pulse_people_graph_definer;


-- W1. Create a person record. Returns its id. Not audited.
CREATE FUNCTION public.admin_create_person(
    in_actor_person_id uuid,
    in_identity_name text,
    in_category text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    created_id uuid;
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM public.role_assignment AS acting
         WHERE acting.person_id = in_actor_person_id
           AND acting.role = 'ADMIN'
    ) THEN
        RAISE EXCEPTION 'admin_people.actor_not_an_admin' USING ERRCODE = 'raise_exception';
    END IF;

    INSERT INTO public.person (identity_name, category)
    VALUES (in_identity_name, in_category)
    RETURNING id INTO created_id;
    RETURN created_id;
END;
$$;


-- W2. Edit a person record's name and category. Not audited.
CREATE FUNCTION public.admin_edit_person(
    in_actor_person_id uuid,
    in_person_id uuid,
    in_identity_name text,
    in_category text
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

    UPDATE public.person AS edited
       SET identity_name = in_identity_name,
           category = in_category
     WHERE edited.id = in_person_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'admin_people.no_such_person' USING ERRCODE = 'raise_exception';
    END IF;
END;
$$;


-- W3. Grant a role at a scope node. The scope is one id, written to the column
-- the role's level calls for, as `SCOPE_GRAIN_RULE` in `app/models/identity.py`
-- sets out. A role with no column here (a ninth role nobody has placed) writes
-- every column NULL, and the table's own check refuses it. A new grant has no
-- parent; setting one is W5.
CREATE FUNCTION public.admin_grant_role(
    in_actor_person_id uuid,
    in_person_id uuid,
    in_role public.assignment_role,
    in_scope_node_id uuid
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    granted_id uuid;
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM public.role_assignment AS acting
         WHERE acting.person_id = in_actor_person_id
           AND acting.role = 'ADMIN'
    ) THEN
        RAISE EXCEPTION 'admin_people.actor_not_an_admin' USING ERRCODE = 'raise_exception';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM public.person AS held WHERE held.id = in_person_id) THEN
        RAISE EXCEPTION 'admin_people.no_such_person' USING ERRCODE = 'raise_exception';
    END IF;

    IF in_role = 'INSTRUCTOR' THEN
        RAISE EXCEPTION 'admin_people.instructor_is_lms_owned' USING ERRCODE = 'raise_exception';
    END IF;

    IF in_scope_node_id IS NULL THEN
        RAISE EXCEPTION 'admin_people.scope_is_not_the_roles_node'
            USING ERRCODE = 'raise_exception';
    END IF;

    -- The person was checked above, so a foreign-key refusal here is the scope:
    -- the id is not a node at the role's level.
    BEGIN
        INSERT INTO public.role_assignment
            (person_id, role, institution_id, college_id, department_id, course_id)
        VALUES (
            in_person_id,
            in_role,
            CASE WHEN in_role IN ('VP_ACADEMICS', 'CARE', 'ADMIN') THEN in_scope_node_id END,
            CASE WHEN in_role IN ('ASSISTANT_DEAN', 'DEAN') THEN in_scope_node_id END,
            CASE WHEN in_role = 'CHAIR' THEN in_scope_node_id END,
            CASE WHEN in_role = 'LEAD_FACULTY' THEN in_scope_node_id END
        )
        RETURNING id INTO granted_id;
    EXCEPTION
        WHEN foreign_key_violation THEN
            RAISE EXCEPTION 'admin_people.scope_is_not_the_roles_node'
                USING ERRCODE = 'raise_exception';
    END;

    INSERT INTO public.audit_log (action, actor_person_id, subject_person_id, role, scope_node_id)
    VALUES ('ROLE_GRANTED', in_actor_person_id, in_person_id, in_role, in_scope_node_id);

    RETURN granted_id;
END;
$$;


-- W4. Revoke an assignment, which deletes it (ruling 7).
CREATE FUNCTION public.admin_revoke_role(
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


-- W5. Set an assignment's parent, or clear it with a NULL parent. ADR 0044's
-- trigger still decides whether the edge climbs.
CREATE FUNCTION public.admin_set_reports_to(
    in_actor_person_id uuid,
    in_assignment_id uuid,
    in_reports_to uuid
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    child_person_id uuid;
    child_role public.assignment_role;
    child_scope_node_id uuid;
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM public.role_assignment AS acting
         WHERE acting.person_id = in_actor_person_id
           AND acting.role = 'ADMIN'
    ) THEN
        RAISE EXCEPTION 'admin_people.actor_not_an_admin' USING ERRCODE = 'raise_exception';
    END IF;

    SELECT child.person_id,
           child.role,
           coalesce(child.institution_id, child.college_id, child.department_id,
                    child.course_id, child.section_id)
      INTO child_person_id, child_role, child_scope_node_id
      FROM public.role_assignment AS child
     WHERE child.id = in_assignment_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'admin_people.no_such_assignment' USING ERRCODE = 'raise_exception';
    END IF;

    IF in_reports_to IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM public.role_assignment AS parent WHERE parent.id = in_reports_to
    ) THEN
        RAISE EXCEPTION 'admin_people.no_such_assignment' USING ERRCODE = 'raise_exception';
    END IF;

    IF child_role = 'INSTRUCTOR' THEN
        RAISE EXCEPTION 'admin_people.instructor_is_lms_owned' USING ERRCODE = 'raise_exception';
    END IF;

    -- ADR 0044's trigger and the `care_reports_to_nobody` check both refuse with
    -- `check_violation`. So does the trigger's REPEATABLE READ refusal, which is
    -- therefore also reported as an edge that does not climb (see the header).
    BEGIN
        UPDATE public.role_assignment AS child
           SET reports_to = in_reports_to
         WHERE child.id = in_assignment_id;
    EXCEPTION
        WHEN check_violation THEN
            RAISE EXCEPTION 'admin_people.edge_does_not_climb' USING ERRCODE = 'raise_exception';
    END;

    INSERT INTO public.audit_log (action, actor_person_id, subject_person_id, role, scope_node_id)
    VALUES ('REPORTS_TO_SET', in_actor_person_id, child_person_id, child_role,
            child_scope_node_id);
END;
$$;


-- W6. Map a course to its lead. One lead per course, by the existing unique
-- constraint on `lead_faculty_mapping.course_id`; changing a course's lead is an
-- unmap followed by a map, two audit rows.
CREATE FUNCTION public.admin_map_lead_course(
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


-- W7. Unmap a course from its lead.
CREATE FUNCTION public.admin_unmap_lead_course(
    in_actor_person_id uuid,
    in_course_id uuid
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    unmapped_person_id uuid;
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM public.role_assignment AS acting
         WHERE acting.person_id = in_actor_person_id
           AND acting.role = 'ADMIN'
    ) THEN
        RAISE EXCEPTION 'admin_people.actor_not_an_admin' USING ERRCODE = 'raise_exception';
    END IF;

    DELETE FROM public.lead_faculty_mapping AS mapped
     WHERE mapped.course_id = in_course_id
    RETURNING mapped.person_id INTO unmapped_person_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'admin_people.course_not_led' USING ERRCODE = 'raise_exception';
    END IF;

    INSERT INTO public.audit_log (action, actor_person_id, subject_person_id, role, scope_node_id)
    VALUES ('LEAD_MAPPING_CHANGED', in_actor_person_id, unmapped_person_id, 'LEAD_FACULTY',
            in_course_id);
END;
$$;


-- W8. Link a web-login subject to a person (ADR 0097). Both halves are one-to-one,
-- by the table's two unique constraints, told apart by name.
CREATE FUNCTION public.admin_link_web_login(
    in_actor_person_id uuid,
    in_person_id uuid,
    in_idp_issuer text,
    in_idp_subject text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    refused_constraint text;
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM public.role_assignment AS acting
         WHERE acting.person_id = in_actor_person_id
           AND acting.role = 'ADMIN'
    ) THEN
        RAISE EXCEPTION 'admin_people.actor_not_an_admin' USING ERRCODE = 'raise_exception';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM public.person AS linked WHERE linked.id = in_person_id) THEN
        RAISE EXCEPTION 'admin_people.no_such_person' USING ERRCODE = 'raise_exception';
    END IF;

    BEGIN
        INSERT INTO public.web_login_subject (idp_issuer, idp_subject, person_id)
        VALUES (in_idp_issuer, in_idp_subject, in_person_id);
    EXCEPTION
        WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS refused_constraint = CONSTRAINT_NAME;
            IF refused_constraint = 'uq_web_login_subject_idp_issuer_idp_subject' THEN
                RAISE EXCEPTION 'admin_people.subject_linked_to_another'
                    USING ERRCODE = 'raise_exception';
            ELSIF refused_constraint = 'uq_web_login_subject_person_id' THEN
                RAISE EXCEPTION 'admin_people.person_already_linked'
                    USING ERRCODE = 'raise_exception';
            END IF;
            RAISE;
    END;

    INSERT INTO public.audit_log (action, actor_person_id, subject_person_id, role, scope_node_id)
    VALUES ('WEB_LOGIN_LINKAGE_CHANGED', in_actor_person_id, in_person_id, NULL, NULL);
END;
$$;


-- W9. Unlink a person's web login.
CREATE FUNCTION public.admin_unlink_web_login(
    in_actor_person_id uuid,
    in_person_id uuid
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

    IF NOT EXISTS (SELECT 1 FROM public.person AS linked WHERE linked.id = in_person_id) THEN
        RAISE EXCEPTION 'admin_people.no_such_person' USING ERRCODE = 'raise_exception';
    END IF;

    DELETE FROM public.web_login_subject AS linkage
     WHERE linkage.person_id = in_person_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'admin_people.person_not_linked' USING ERRCODE = 'raise_exception';
    END IF;

    INSERT INTO public.audit_log (action, actor_person_id, subject_person_id, role, scope_node_id)
    VALUES ('WEB_LOGIN_LINKAGE_CHANGED', in_actor_person_id, in_person_id, NULL, NULL);
END;
$$;


-- R1. Every person: name, category, and the web-login issuer where one is linked.
CREATE FUNCTION public.admin_read_people(in_actor_person_id uuid)
RETURNS TABLE (person_id uuid, identity_name text, category text, idp_issuer text)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT listed.id,
           listed.identity_name,
           listed.category::text,
           linkage.idp_issuer
      FROM public.person AS listed
      LEFT JOIN public.web_login_subject AS linkage ON linkage.person_id = listed.id
     WHERE EXISTS (
               SELECT 1
                 FROM public.role_assignment AS acting
                WHERE acting.person_id = in_actor_person_id
                  AND acting.role = 'ADMIN'
           )
     ORDER BY listed.identity_name, listed.id;
$$;


-- R2. Every assignment, `INSTRUCTOR` included: its person, role, scope node and
-- parent.
CREATE FUNCTION public.admin_read_role_assignments(in_actor_person_id uuid)
RETURNS TABLE (
    assignment_id uuid,
    person_id uuid,
    role public.assignment_role,
    scope_node_id uuid,
    reports_to uuid
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT listed.id,
           listed.person_id,
           listed.role,
           coalesce(listed.institution_id, listed.college_id, listed.department_id,
                    listed.course_id, listed.section_id),
           listed.reports_to
      FROM public.role_assignment AS listed
     WHERE EXISTS (
               SELECT 1
                 FROM public.role_assignment AS acting
                WHERE acting.person_id = in_actor_person_id
                  AND acting.role = 'ADMIN'
           )
     ORDER BY listed.person_id, listed.id;
$$;


-- R3. Every lead mapping.
CREATE FUNCTION public.admin_read_lead_mappings(in_actor_person_id uuid)
RETURNS TABLE (person_id uuid, course_id uuid)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT mapped.person_id, mapped.course_id
      FROM public.lead_faculty_mapping AS mapped
     WHERE EXISTS (
               SELECT 1
                 FROM public.role_assignment AS acting
                WHERE acting.person_id = in_actor_person_id
                  AND acting.role = 'ADMIN'
           )
     ORDER BY mapped.course_id;
$$;


ALTER FUNCTION public.admin_create_person(uuid, text, text) OWNER TO pulse_people_graph_definer;
ALTER FUNCTION public.admin_edit_person(uuid, uuid, text, text)
    OWNER TO pulse_people_graph_definer;
ALTER FUNCTION public.admin_grant_role(uuid, uuid, public.assignment_role, uuid)
    OWNER TO pulse_people_graph_definer;
ALTER FUNCTION public.admin_revoke_role(uuid, uuid) OWNER TO pulse_people_graph_definer;
ALTER FUNCTION public.admin_set_reports_to(uuid, uuid, uuid) OWNER TO pulse_people_graph_definer;
ALTER FUNCTION public.admin_map_lead_course(uuid, uuid, uuid) OWNER TO pulse_people_graph_definer;
ALTER FUNCTION public.admin_unmap_lead_course(uuid, uuid) OWNER TO pulse_people_graph_definer;
ALTER FUNCTION public.admin_link_web_login(uuid, uuid, text, text)
    OWNER TO pulse_people_graph_definer;
ALTER FUNCTION public.admin_unlink_web_login(uuid, uuid) OWNER TO pulse_people_graph_definer;
ALTER FUNCTION public.admin_read_people(uuid) OWNER TO pulse_people_graph_definer;
ALTER FUNCTION public.admin_read_role_assignments(uuid) OWNER TO pulse_people_graph_definer;
ALTER FUNCTION public.admin_read_lead_mappings(uuid) OWNER TO pulse_people_graph_definer;

REVOKE ALL ON FUNCTION public.admin_create_person(uuid, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_edit_person(uuid, uuid, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_grant_role(uuid, uuid, public.assignment_role, uuid)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_revoke_role(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_set_reports_to(uuid, uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_map_lead_course(uuid, uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_unmap_lead_course(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_link_web_login(uuid, uuid, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_unlink_web_login(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_read_people(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_read_role_assignments(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_read_lead_mappings(uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.admin_create_person(uuid, text, text) TO pulse_app;
GRANT EXECUTE ON FUNCTION public.admin_edit_person(uuid, uuid, text, text) TO pulse_app;
GRANT EXECUTE ON FUNCTION public.admin_grant_role(uuid, uuid, public.assignment_role, uuid)
    TO pulse_app;
GRANT EXECUTE ON FUNCTION public.admin_revoke_role(uuid, uuid) TO pulse_app;
GRANT EXECUTE ON FUNCTION public.admin_set_reports_to(uuid, uuid, uuid) TO pulse_app;
GRANT EXECUTE ON FUNCTION public.admin_map_lead_course(uuid, uuid, uuid) TO pulse_app;
GRANT EXECUTE ON FUNCTION public.admin_unmap_lead_course(uuid, uuid) TO pulse_app;
GRANT EXECUTE ON FUNCTION public.admin_link_web_login(uuid, uuid, text, text) TO pulse_app;
GRANT EXECUTE ON FUNCTION public.admin_unlink_web_login(uuid, uuid) TO pulse_app;
GRANT EXECUTE ON FUNCTION public.admin_read_people(uuid) TO pulse_app;
GRANT EXECUTE ON FUNCTION public.admin_read_role_assignments(uuid) TO pulse_app;
GRANT EXECUTE ON FUNCTION public.admin_read_lead_mappings(uuid) TO pulse_app;
