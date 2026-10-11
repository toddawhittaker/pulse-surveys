-- Who may set a response policy, checked for the one course the row covers — E7-02, M2,
-- SPEC §5.3, ADR 0193, amending `response_loop_guard_v001.sql`'s policy half.
--
-- M2 gives every `response_policy` row a `course_id`: a policy row covers one course,
-- fixed when it is written, because lead mappings keep no history and "who was
-- responsible for this course when the week's report opened" cannot be asked later
-- (ADR 0193). So the setter is checked against that course, not against the prefix:
--
--   `LEAD_FACULTY`: a `LEAD_FACULTY` assignment and the Lead Faculty mapping for the
--   row's course;
--   `CHAIR`: a `CHAIR` assignment on the course's department, where nobody leads the
--   course (ruling 5: for a led course the chair reads the policy and cannot change it).
--
-- The same two rules `authz.lead_review_courses` answers, and the same ones the
-- response half of v001 applies to an on-behalf author. That the course belongs to
-- the row's prefix is not checked here: M2's composite key
-- `(course_id, prefix_id) → course (id, prefix_id)` refuses a row where they disagree.
-- The department is read from the course's own prefix so that the check and the key
-- agree about which department that is.
--
-- A refusal raises SQLSTATE 42501 with a message that names no person.
--
-- Only the function body changes. The trigger v001 created already calls this
-- function by name, the owner `pulse_response_guard_definer` already reads every
-- column this body reads, and `pulse_app` still holds no `EXECUTE` on it.

CREATE OR REPLACE FUNCTION public.response_policy_is_set_by_its_role()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    the_department_id uuid;
    holds boolean;
BEGIN
    SELECT its_prefix.department_id
      INTO the_department_id
      FROM public.course AS covered
      JOIN public.prefix AS its_prefix ON its_prefix.id = covered.prefix_id
     WHERE covered.id = NEW.course_id;

    holds := CASE NEW.role
        WHEN 'LEAD_FACULTY' THEN EXISTS (
            SELECT 1
              FROM public.role_assignment AS held
             WHERE held.person_id = NEW.set_by_person_id
               AND held.role = 'LEAD_FACULTY'
        ) AND EXISTS (
            SELECT 1
              FROM public.lead_faculty_mapping AS mapped
             WHERE mapped.person_id = NEW.set_by_person_id
               AND mapped.course_id = NEW.course_id
        )
        WHEN 'CHAIR' THEN EXISTS (
            SELECT 1
              FROM public.role_assignment AS chairing
             WHERE chairing.person_id = NEW.set_by_person_id
               AND chairing.role = 'CHAIR'
               AND chairing.department_id = the_department_id
        ) AND NOT EXISTS (
            SELECT 1
              FROM public.lead_faculty_mapping AS mapped
             WHERE mapped.course_id = NEW.course_id
        )
        ELSE false
    END;

    IF holds IS NOT TRUE THEN
        RAISE EXCEPTION 'a policy is set only by someone who holds its role for the course'
            USING ERRCODE = '42501';
    END IF;

    RETURN NEW;
END;
$$;

ALTER FUNCTION public.response_policy_is_set_by_its_role()
    OWNER TO pulse_response_guard_definer;
REVOKE ALL ON FUNCTION public.response_policy_is_set_by_its_role() FROM PUBLIC;
