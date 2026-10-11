-- Who may write a response or a policy: checked when the row is written — E7-01's fix
-- round (F1 to F3), SPEC §5.3, ADR 0191, ADR 0192, ADR 0043.
--
-- `pulse_app` inserts `instructor_response` and `response_policy` rows at column grain
-- (`response_loop_grants_v001.sql`), and a grant cannot say *who* a row may name. The
-- staff-name definer (`section_staff_names_v001.sql`) answers the name of anyone who
-- has published a response to a section, so a row naming any person as its author
-- would make it answer that person's name, a student's included. So each table has a
-- `BEFORE INSERT` trigger that refuses a row unless the person it names holds the role
-- it states, there, at that moment:
--
--   - a response's author, for the row's section (F1):
--       `INSTRUCTOR`: the section's `INSTRUCTOR` grant (a grant the roster ended is a
--       deleted row, so it no longer counts);
--       `LEAD_FACULTY`: a `LEAD_FACULTY` assignment and the Lead Faculty mapping for
--       the section's course;
--       `CHAIR`: a `CHAIR` assignment on the course's department, where nobody leads
--       the course.
--     The same three rules as the staff-name definer's staff checks, which are SQL
--     copies of `authz.teaching_instructor_assigned` and `authz.lead_review_courses`.
--   - one author per section-week (F2, the owner's ruling 3 for E7: only the person
--     who first published the week's response may edit it). The check takes a
--     transaction-scoped advisory lock on the section-week first, so two writers
--     racing for one week are serialised: the second waits for the first to commit,
--     then sees its row. The application runs at read committed, where each
--     statement in this function reads a fresh snapshot.
--   - a policy's setter, for the row's prefix (F3):
--       `LEAD_FACULTY`: a `LEAD_FACULTY` assignment and the mapping for at least one
--       course in the prefix;
--       `CHAIR`: a `CHAIR` assignment on the prefix's department.
--
-- A refusal raises SQLSTATE 42501 with a message that names no person.
--
-- **The owner is `pulse_response_guard_definer`**, a NOLOGIN role that exists for
-- nothing else. It holds `SELECT` on exactly the columns these bodies read and writes
-- nothing. `pulse_app` holds no `EXECUTE` on either function: a trigger fires without
-- it, and `PUBLIC`'s default `EXECUTE` is revoked.

DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_response_guard_definer'
    ) THEN
        CREATE ROLE pulse_response_guard_definer NOLOGIN;
    END IF;
END
$do$;

GRANT SELECT (person_id, role, section_id, department_id)
    ON public.role_assignment TO pulse_response_guard_definer;
GRANT SELECT (person_id, course_id)
    ON public.lead_faculty_mapping TO pulse_response_guard_definer;
GRANT SELECT (id, course_id) ON public.section TO pulse_response_guard_definer;
GRANT SELECT (id, prefix_id) ON public.course TO pulse_response_guard_definer;
GRANT SELECT (id, department_id) ON public.prefix TO pulse_response_guard_definer;
GRANT SELECT (section_id, week_id, author_person_id)
    ON public.instructor_response TO pulse_response_guard_definer;

CREATE OR REPLACE FUNCTION public.instructor_response_is_written_by_its_role()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    the_course_id uuid;
    the_department_id uuid;
    holds boolean;
BEGIN
    SELECT its_course.id, its_prefix.department_id
      INTO the_course_id, the_department_id
      FROM public.section AS asked
      JOIN public.course AS its_course ON its_course.id = asked.course_id
      JOIN public.prefix AS its_prefix ON its_prefix.id = its_course.prefix_id
     WHERE asked.id = NEW.section_id;

    holds := CASE NEW.role
        WHEN 'INSTRUCTOR' THEN EXISTS (
            SELECT 1
              FROM public.role_assignment AS granted
             WHERE granted.person_id = NEW.author_person_id
               AND granted.role = 'INSTRUCTOR'
               AND granted.section_id = NEW.section_id
        )
        WHEN 'LEAD_FACULTY' THEN EXISTS (
            SELECT 1
              FROM public.role_assignment AS held
             WHERE held.person_id = NEW.author_person_id
               AND held.role = 'LEAD_FACULTY'
        ) AND EXISTS (
            SELECT 1
              FROM public.lead_faculty_mapping AS mapped
             WHERE mapped.person_id = NEW.author_person_id
               AND mapped.course_id = the_course_id
        )
        WHEN 'CHAIR' THEN EXISTS (
            SELECT 1
              FROM public.role_assignment AS chairing
             WHERE chairing.person_id = NEW.author_person_id
               AND chairing.role = 'CHAIR'
               AND chairing.department_id = the_department_id
        ) AND NOT EXISTS (
            SELECT 1
              FROM public.lead_faculty_mapping AS mapped
             WHERE mapped.course_id = the_course_id
        )
        ELSE false
    END;

    IF holds IS NOT TRUE THEN
        RAISE EXCEPTION 'a response is written only by someone who holds its role for the section'
            USING ERRCODE = '42501';
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            CAST(NEW.section_id AS text) || ':' || CAST(NEW.week_id AS text), 0
        )
    );
    IF EXISTS (
        SELECT 1
          FROM public.instructor_response AS earlier
         WHERE earlier.section_id = NEW.section_id
           AND earlier.week_id = NEW.week_id
           AND earlier.author_person_id <> NEW.author_person_id
    ) THEN
        RAISE EXCEPTION 'a week''s response is edited only by the person who first published it'
            USING ERRCODE = '42501';
    END IF;

    RETURN NEW;
END;
$$;

ALTER FUNCTION public.instructor_response_is_written_by_its_role()
    OWNER TO pulse_response_guard_definer;
REVOKE ALL ON FUNCTION public.instructor_response_is_written_by_its_role() FROM PUBLIC;

CREATE TRIGGER instructor_response_is_written_by_its_role
    BEFORE INSERT ON public.instructor_response
    FOR EACH ROW EXECUTE FUNCTION public.instructor_response_is_written_by_its_role();

CREATE OR REPLACE FUNCTION public.response_policy_is_set_by_its_role()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    holds boolean;
BEGIN
    holds := CASE NEW.role
        WHEN 'LEAD_FACULTY' THEN EXISTS (
            SELECT 1
              FROM public.role_assignment AS held
             WHERE held.person_id = NEW.set_by_person_id
               AND held.role = 'LEAD_FACULTY'
        ) AND EXISTS (
            SELECT 1
              FROM public.lead_faculty_mapping AS mapped
              JOIN public.course AS led ON led.id = mapped.course_id
             WHERE mapped.person_id = NEW.set_by_person_id
               AND led.prefix_id = NEW.prefix_id
        )
        WHEN 'CHAIR' THEN EXISTS (
            SELECT 1
              FROM public.role_assignment AS chairing
              JOIN public.prefix AS its_prefix ON its_prefix.department_id = chairing.department_id
             WHERE chairing.person_id = NEW.set_by_person_id
               AND chairing.role = 'CHAIR'
               AND its_prefix.id = NEW.prefix_id
        )
        ELSE false
    END;

    IF holds IS NOT TRUE THEN
        RAISE EXCEPTION 'a policy is set only by someone who holds its role in the prefix'
            USING ERRCODE = '42501';
    END IF;

    RETURN NEW;
END;
$$;

ALTER FUNCTION public.response_policy_is_set_by_its_role()
    OWNER TO pulse_response_guard_definer;
REVOKE ALL ON FUNCTION public.response_policy_is_set_by_its_role() FROM PUBLIC;

CREATE TRIGGER response_policy_is_set_by_its_role
    BEFORE INSERT ON public.response_policy
    FOR EACH ROW EXECUTE FUNCTION public.response_policy_is_set_by_its_role();
