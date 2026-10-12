-- The staff-name channel over a set of sections — E9-03, SPEC §2.1, §4.1, §5.3,
-- ADR 0201 (which supersedes ADR 0191 in part), ADR 0043.
--
-- v001 (`section_staff_names_v001.sql`) answers one section at a time. E9's tree
-- labels and course headers name a section's instructor, its course's lead, its
-- department's chair and its college's dean, for many sections on one page, so this
-- file adds an overload that answers a set of sections in one call. v001 stays,
-- unchanged, beside it. Same house pattern: the NOLOGIN owner
-- `pulse_staff_name_definer`, privileges listed in this file against this body,
-- `search_path` with `pg_temp` last, typed parameters, every relation
-- schema-qualified, and no dynamic SQL.
--
-- **What it answers.** For each section passed that the reader may read, one row
-- per (section, role, person), with the person's key and `person.identity_name`:
--
--   INSTRUCTOR    the section's live teaching instructors (a section-scoped
--                 `INSTRUCTOR` assignment that exists);
--   AUTHOR        anyone who has published a response to the section;
--   LEAD_FACULTY  the course's lead: the person the Lead Faculty mapping names for
--                 the course, when they hold a `LEAD_FACULTY` assignment, as
--                 reader check (c) below and `authz.lead_review_courses` read it;
--   CHAIR         whoever holds `CHAIR` on the course's department;
--   DEAN          whoever holds `DEAN` on the department's college. Not an
--                 assistant dean and not the vice president.
--
-- A teacher who also published is two rows, one under each role. A course with no
-- lead has no lead row, and a department with no chair has no chair row. Four
-- columns, in this order, and no other column, ever.
--
-- **Whom it answers.** Exactly one reader key is non-null, or the answer is empty.
-- A student is asked about by `p_reader_user_id`, a member of staff by
-- `p_reader_person_id`, and each check runs on its own key only. A section is
-- answered when the reader:
--
--   (a) holds an enrollment in that section that is live on `p_reader_date`,
--       inclusive at both ends, with a null `ended_on` open (user key);
--   (b) holds the `INSTRUCTOR` grant on that section (person key);
--   (c) holds a `LEAD_FACULTY` assignment and the Lead Faculty mapping gives them
--       that section's course (person key); or
--   (d) holds a `CHAIR`, `ASSISTANT_DEAN`, `DEAN` or `VP_ACADEMICS` assignment
--       anywhere (person key). Such a reader is answered for every section passed
--       (the E9 README's ruling 3, as narrowed by its decision 16). This function
--       does not recompute their purview: the Python door
--       (`response_loop.section_staff_names`) passes such a reader only the
--       sections of their resolved purview.
--
-- (a), (b) and (c) are v001's checks, applied to each section on its own, so a
-- student, an instructor or a lead passing a section they do not read gets nothing
-- for it, whatever else the call passes. A reader whose only leadership is
-- `LEAD_FACULTY` stays under (c) (decision 16): the database refuses a sibling
-- lead's section to a lead even when the door passes it. v001's fourth check, the
-- chair of a course nobody leads, is not repeated here, because (d) answers every
-- chair for every section passed, which includes those.
--
-- `CARE` and `ADMIN` are not leadership (SPEC §2, §6.2) and reach nothing here.
--
-- **"Today" is `p_reader_date`**, the reader's date. The door computes it from the
-- application clock (`services.clock.today`) in the institution's timezone, so the
-- check agrees with the survey read near midnight and under the development clock
-- override. The function trusts the date it is handed; ADR 0201 records that.
-- A null date answers no student.
--
-- **The owner holds `SELECT` on exactly the columns this body reads**, which adds
-- `role_assignment.college_id` and `department (id, college_id)` to v001's list,
-- and nothing on `user_identity`, and no write anywhere.

DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_staff_name_definer'
    ) THEN
        CREATE ROLE pulse_staff_name_definer NOLOGIN;
    END IF;
END
$do$;

GRANT SELECT (id, identity_name) ON public.person TO pulse_staff_name_definer;
GRANT SELECT (person_id, role, section_id, department_id, college_id)
    ON public.role_assignment TO pulse_staff_name_definer;
GRANT SELECT (person_id, course_id) ON public.lead_faculty_mapping TO pulse_staff_name_definer;
GRANT SELECT (user_id, section_id, started_on, ended_on)
    ON public.enrollment TO pulse_staff_name_definer;
GRANT SELECT (id, course_id) ON public.section TO pulse_staff_name_definer;
GRANT SELECT (id, prefix_id) ON public.course TO pulse_staff_name_definer;
GRANT SELECT (id, department_id) ON public.prefix TO pulse_staff_name_definer;
GRANT SELECT (id, college_id) ON public.department TO pulse_staff_name_definer;
GRANT SELECT (section_id, author_person_id)
    ON public.instructor_response TO pulse_staff_name_definer;

CREATE OR REPLACE FUNCTION public.section_staff_names(
    p_section_ids uuid[],
    p_reader_user_id uuid,
    p_reader_person_id uuid,
    p_reader_date date
)
RETURNS TABLE (section_id uuid, role text, person_id uuid, display_name text)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    WITH the_reader AS (
        SELECT (p_reader_user_id IS NULL) <> (p_reader_person_id IS NULL) AS has_one_key,
               -- (d) chair and above, by person key.
               EXISTS (
                   SELECT 1
                     FROM public.role_assignment AS held
                    WHERE held.person_id = p_reader_person_id
                      AND held.role IN ('CHAIR', 'ASSISTANT_DEAN', 'DEAN', 'VP_ACADEMICS')
               ) AS is_chair_or_above,
               -- (c)'s first half, by person key.
               EXISTS (
                   SELECT 1
                     FROM public.role_assignment AS held
                    WHERE held.person_id = p_reader_person_id
                      AND held.role = 'LEAD_FACULTY'
               ) AS is_a_lead
    ),
    the_asked AS (
        SELECT DISTINCT asked.id AS section_id,
               its_course.id AS course_id,
               its_department.id AS department_id,
               its_department.college_id
          FROM public.section AS asked
          JOIN public.course AS its_course ON its_course.id = asked.course_id
          JOIN public.prefix AS its_prefix ON its_prefix.id = its_course.prefix_id
          JOIN public.department AS its_department ON its_department.id = its_prefix.department_id
         WHERE asked.id = ANY (p_section_ids)
    ),
    the_readable AS (
        SELECT the_asked.*
          FROM the_asked
         CROSS JOIN the_reader
         WHERE the_reader.has_one_key
           AND (
                the_reader.is_chair_or_above
                -- (a) a student, by user key: a live enrollment in this section.
                OR EXISTS (
                    SELECT 1
                      FROM public.enrollment AS enrolled
                     WHERE enrolled.user_id = p_reader_user_id
                       AND enrolled.section_id = the_asked.section_id
                       AND enrolled.started_on <= p_reader_date
                       AND (enrolled.ended_on IS NULL OR enrolled.ended_on >= p_reader_date)
                )
                -- (b) the teaching instructor of this section, by person key.
                OR EXISTS (
                    SELECT 1
                      FROM public.role_assignment AS granted
                     WHERE granted.person_id = p_reader_person_id
                       AND granted.role = 'INSTRUCTOR'
                       AND granted.section_id = the_asked.section_id
                )
                -- (c) the Lead Faculty of this section's course, by person key.
                OR (
                    the_reader.is_a_lead
                    AND EXISTS (
                        SELECT 1
                          FROM public.lead_faculty_mapping AS mapped
                         WHERE mapped.person_id = p_reader_person_id
                           AND mapped.course_id = the_asked.course_id
                    )
                )
           )
    ),
    the_named AS (
        SELECT the_readable.section_id, CAST('INSTRUCTOR' AS text) AS role, teaching.person_id
          FROM the_readable
          JOIN public.role_assignment AS teaching
            ON teaching.section_id = the_readable.section_id
           AND teaching.role = 'INSTRUCTOR'
        UNION
        SELECT the_readable.section_id, CAST('AUTHOR' AS text), responded.author_person_id
          FROM the_readable
          JOIN public.instructor_response AS responded
            ON responded.section_id = the_readable.section_id
        UNION
        SELECT the_readable.section_id, CAST('LEAD_FACULTY' AS text), mapped.person_id
          FROM the_readable
          JOIN public.lead_faculty_mapping AS mapped
            ON mapped.course_id = the_readable.course_id
         WHERE EXISTS (
                SELECT 1
                  FROM public.role_assignment AS its_lead_grant
                 WHERE its_lead_grant.person_id = mapped.person_id
                   AND its_lead_grant.role = 'LEAD_FACULTY'
         )
        UNION
        SELECT the_readable.section_id, CAST('CHAIR' AS text), chairing.person_id
          FROM the_readable
          JOIN public.role_assignment AS chairing
            ON chairing.department_id = the_readable.department_id
           AND chairing.role = 'CHAIR'
        UNION
        SELECT the_readable.section_id, CAST('DEAN' AS text), deaning.person_id
          FROM the_readable
          JOIN public.role_assignment AS deaning
            ON deaning.college_id = the_readable.college_id
           AND deaning.role = 'DEAN'
    )
    SELECT the_named.section_id, the_named.role, staff.id, staff.identity_name
      FROM the_named
      JOIN public.person AS staff ON staff.id = the_named.person_id
     ORDER BY the_named.section_id, the_named.role, staff.identity_name, staff.id
$$;

ALTER FUNCTION public.section_staff_names(uuid[], uuid, uuid, date)
    OWNER TO pulse_staff_name_definer;

REVOKE ALL ON FUNCTION public.section_staff_names(uuid[], uuid, uuid, date) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.section_staff_names(uuid[], uuid, uuid, date) TO pulse_app;
