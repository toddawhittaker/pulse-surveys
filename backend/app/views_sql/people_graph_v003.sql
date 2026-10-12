-- A course is led only by a Lead Faculty holder — E9-14, amending ADR 0200.
--
-- "Led" had two definitions: a `lead_faculty_mapping` row, and a `LEAD_FACULTY`
-- assignment. A course mapped to a person holding no `LEAD_FACULTY` assignment
-- counts as led, so it does not fall to its chair (SPEC §2.1), yet the review
-- queue reads a lead only through that assignment (ADR 0190), so the course's
-- harmful comments reached nobody's queue. These two replacements keep the
-- mapping table inside the assignment table: every mapped person holds at least
-- one `LEAD_FACULTY` assignment.
--
--   - `admin_map_lead_course` refuses a person holding no `LEAD_FACULTY`
--     assignment with `admin_people.lead_needs_the_lead_role`. Any one will do:
--     the assignment is scoped to a course, but the rule is that the person
--     holds the role, so a new lead's assignment need not be at the course
--     being mapped;
--   - `admin_revoke_role` refuses to revoke a `LEAD_FACULTY` assignment while
--     its person still has mappings, with `admin_people.lead_still_leads_courses`
--     and the count of mappings in the detail field, as digits, as
--     `assignment_has_reports` carries its count. The admin unmaps first.
--
-- The CSV import calls the same two functions (ADR 0204), so a mapping file
-- naming such a person is refused at its line.
--
-- **The two are serialized on the assignment rows.** Under READ COMMITTED, a
-- map that checked the assignment and a revoke that counted no mapping could
-- each commit and leave a mapping with no lead. So the map takes `FOR KEY
-- SHARE` on the person's `LEAD_FACULTY` rows, and the revoke takes `FOR
-- UPDATE` on the row it deletes before it counts; whichever comes second waits,
-- and then reads what the first committed. `pulse_people_graph_definer` holds
-- `UPDATE (reports_to)` on `role_assignment`, which a locking read needs.
--
-- Everything else is v001's, statement for statement: the admin check, the
-- other refusals and their order, and the one audit insert outside every
-- exception block. Same names and signatures, so `CREATE OR REPLACE` keeps each
-- function's owner and `EXECUTE` grant; both are restated below so this file
-- says what it leaves behind. SET search_path names pg_temp last (ADR 0027),
-- every relation is schema-qualified, parameters are typed, and there is no
-- dynamic SQL.


-- W4. Revoke an assignment, which deletes it (ruling 7).
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
    held_person_id uuid;
    revoked_person_id uuid;
    revoked_role public.assignment_role;
    revoked_scope_node_id uuid;
    reporting_count bigint;
    mapping_count bigint;
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM public.role_assignment AS acting
         WHERE acting.person_id = in_actor_person_id
           AND acting.role = 'ADMIN'
    ) THEN
        RAISE EXCEPTION 'admin_people.actor_not_an_admin' USING ERRCODE = 'raise_exception';
    END IF;

    -- Locked, so a concurrent map of this person waits for the revoke, and the
    -- mapping count below cannot miss a mapping committed in between.
    SELECT held.role, held.person_id INTO held_role, held_person_id
      FROM public.role_assignment AS held
     WHERE held.id = in_assignment_id
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'admin_people.no_such_assignment' USING ERRCODE = 'raise_exception';
    END IF;

    IF held_role = 'INSTRUCTOR' THEN
        RAISE EXCEPTION 'admin_people.instructor_is_lms_owned' USING ERRCODE = 'raise_exception';
    END IF;

    IF held_role = 'LEAD_FACULTY' THEN
        SELECT count(*) INTO mapping_count
          FROM public.lead_faculty_mapping AS mapped
         WHERE mapped.person_id = held_person_id;
        IF mapping_count > 0 THEN
            RAISE EXCEPTION 'admin_people.lead_still_leads_courses'
                USING ERRCODE = 'raise_exception', DETAIL = mapping_count::text;
        END IF;
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


-- W6. Map a course to its lead, who must hold a `LEAD_FACULTY` assignment. One
-- lead per course, by the existing unique constraint on
-- `lead_faculty_mapping.course_id`; changing a course's lead is an unmap
-- followed by a map, two audit rows.
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

    -- Locked until the commit, so a concurrent revoke of the last of them waits
    -- and then counts this mapping; a revoke that committed first has deleted
    -- its row, which this read then does not find.
    PERFORM 1
       FROM public.role_assignment AS lead
      WHERE lead.person_id = in_person_id
        AND lead.role = 'LEAD_FACULTY'
        FOR KEY SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'admin_people.lead_needs_the_lead_role' USING ERRCODE = 'raise_exception';
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


ALTER FUNCTION public.admin_revoke_role(uuid, uuid) OWNER TO pulse_people_graph_definer;
ALTER FUNCTION public.admin_map_lead_course(uuid, uuid, uuid) OWNER TO pulse_people_graph_definer;

REVOKE ALL ON FUNCTION public.admin_revoke_role(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_map_lead_course(uuid, uuid, uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.admin_revoke_role(uuid, uuid) TO pulse_app;
GRANT EXECUTE ON FUNCTION public.admin_map_lead_course(uuid, uuid, uuid) TO pulse_app;
