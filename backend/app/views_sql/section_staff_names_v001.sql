-- The one channel a member of staff's name reaches a reader through — E7-01, SPEC §5.3,
-- §4.1, ADR 0191, ADR 0043.
--
-- SPEC §5.3 posts an instructor's response "non-anonymously under the instructor's
-- name" and an on-behalf response "attributed honestly to the Lead Faculty", and the
-- survey page names the section's professor. Staff names live in
-- `person.identity_name`, and `pulse_app` holds no privilege on `person`, by design.
-- A column grant is the wrong shape: `person` holds students too, and a grant cannot
-- filter rows. So the read is this function, in the house pattern
-- (`teaching_instructor_v001.sql`): a NOLOGIN owner whose privileges are listed in
-- this file against this body, `search_path` with `pg_temp` last, typed parameters,
-- every relation schema-qualified, and no dynamic SQL.
--
-- **What it answers.** For one section, the names of the section's live teaching
-- instructors (a section-scoped `INSTRUCTOR` assignment that exists; `role_assignment`
-- carries no validity dates, so a grant the roster ended is a deleted row), and the
-- name of anyone who has published a response to that section. Each person once. Two
-- columns, the person key and the name, and no other column, ever.
--
-- **Whom it answers.** Exactly one reader key is non-null, or the answer is empty.
-- A student is asked about by `p_reader_user_id` (a launched student has a `user`
-- and no `person`, ADR 0028), a member of staff by `p_reader_person_id`, and each
-- check runs on its own key only, so one session cannot borrow the other hat's
-- reading. The reader is answered only when they:
--
--   (a) hold an enrollment in this section that is live today — the rule
--       `survey_read._live_enrollments` applies through
--       `enrollment_windows.live_on`, inclusive at both ends, with a null
--       `ended_on` open (user key);
--   (b) hold the `INSTRUCTOR` grant on this section — the three conditions of
--       `authz.teaching_instructor_assigned` (person key); or
--   (c) are responsible for the section's course under `authz.lead_review_courses`:
--       they hold a `LEAD_FACULTY` assignment and the Lead Faculty mapping gives
--       them the course, or they chair the course's department and nobody leads
--       the course (person key).
--
-- Every other reader gets the empty answer a section with no instructor gives. These
-- are SQL copies of Python rules, and ADR 0191 says so: the tests in
-- `test_the_staff_name_channel_answers_no_other_reader.py` hold the copy to the rule
-- over one world holding every reader kind and every one-level-out non-reader.
--
-- **"Today" is the database's UTC date.** The function has no clock parameter, so it
-- cannot see the institution's timezone or the development clock override that
-- `services/clock.today` reads. ADR 0191 records the residual: near midnight the two
-- days differ by the timezone's offset, so the check can disagree with the survey
-- read for a few hours at either end of an enrollment, and under a moved
-- development clock it reads the real date. The survey read asks only about the
-- sections it has already found live, so the definer is the second check there,
-- never the only one.
--
-- **The owner is `pulse_staff_name_definer`**, a NOLOGIN role that exists for
-- nothing else. It holds `SELECT` on exactly the columns this body reads, and
-- nothing on `user_identity`, where the addresses live, and no write anywhere.

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
GRANT SELECT (person_id, role, section_id, department_id)
    ON public.role_assignment TO pulse_staff_name_definer;
GRANT SELECT (person_id, course_id) ON public.lead_faculty_mapping TO pulse_staff_name_definer;
GRANT SELECT (user_id, section_id, started_on, ended_on)
    ON public.enrollment TO pulse_staff_name_definer;
GRANT SELECT (id, course_id) ON public.section TO pulse_staff_name_definer;
GRANT SELECT (id, prefix_id) ON public.course TO pulse_staff_name_definer;
GRANT SELECT (id, department_id) ON public.prefix TO pulse_staff_name_definer;
GRANT SELECT (section_id, author_person_id)
    ON public.instructor_response TO pulse_staff_name_definer;

CREATE OR REPLACE FUNCTION public.section_staff_names(
    p_section_id uuid,
    p_reader_user_id uuid,
    p_reader_person_id uuid
)
RETURNS TABLE (person_id uuid, display_name text)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    WITH the_day AS (
        SELECT CAST(pg_catalog.timezone('UTC', pg_catalog.now()) AS date) AS today
    ),
    the_course AS (
        SELECT its_course.id AS course_id, its_prefix.department_id
          FROM public.section AS asked
          JOIN public.course AS its_course ON its_course.id = asked.course_id
          JOIN public.prefix AS its_prefix ON its_prefix.id = its_course.prefix_id
         WHERE asked.id = p_section_id
    ),
    the_reader_reads_the_section AS (
        SELECT (p_reader_user_id IS NULL) <> (p_reader_person_id IS NULL)
           AND (
                -- (a) a student, by user key: a live enrollment in this section.
                EXISTS (
                    SELECT 1
                      FROM public.enrollment AS enrolled
                      JOIN the_day ON enrolled.started_on <= the_day.today
                     WHERE enrolled.user_id = p_reader_user_id
                       AND enrolled.section_id = p_section_id
                       AND (enrolled.ended_on IS NULL OR enrolled.ended_on >= the_day.today)
                )
                -- (b) the teaching instructor of this section, by person key.
                OR EXISTS (
                    SELECT 1
                      FROM public.role_assignment AS granted
                     WHERE granted.person_id = p_reader_person_id
                       AND granted.role = 'INSTRUCTOR'
                       AND granted.section_id = p_section_id
                )
                -- (c) the Lead Faculty of the course, by person key.
                OR (
                    EXISTS (
                        SELECT 1
                          FROM public.role_assignment AS held
                         WHERE held.person_id = p_reader_person_id
                           AND held.role = 'LEAD_FACULTY'
                    )
                    AND EXISTS (
                        SELECT 1
                          FROM public.lead_faculty_mapping AS mapped
                          JOIN the_course ON the_course.course_id = mapped.course_id
                         WHERE mapped.person_id = p_reader_person_id
                    )
                )
                -- (c) the chair of its department, when nobody leads it, by person key.
                OR (
                    EXISTS (
                        SELECT 1
                          FROM public.role_assignment AS chairing
                          JOIN the_course ON the_course.department_id = chairing.department_id
                         WHERE chairing.person_id = p_reader_person_id
                           AND chairing.role = 'CHAIR'
                    )
                    AND NOT EXISTS (
                        SELECT 1
                          FROM public.lead_faculty_mapping AS mapped
                          JOIN the_course ON the_course.course_id = mapped.course_id
                    )
                )
           ) AS reads
    ),
    the_named AS (
        SELECT teaching.person_id
          FROM public.role_assignment AS teaching
         WHERE teaching.role = 'INSTRUCTOR'
           AND teaching.section_id = p_section_id
        UNION
        SELECT responded.author_person_id
          FROM public.instructor_response AS responded
         WHERE responded.section_id = p_section_id
    )
    SELECT staff.id, staff.identity_name
      FROM public.person AS staff
      JOIN the_named ON the_named.person_id = staff.id
     WHERE (SELECT reads FROM the_reader_reads_the_section) IS TRUE
     ORDER BY staff.identity_name, staff.id
$$;

ALTER FUNCTION public.section_staff_names(uuid, uuid, uuid) OWNER TO pulse_staff_name_definer;

REVOKE ALL ON FUNCTION public.section_staff_names(uuid, uuid, uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.section_staff_names(uuid, uuid, uuid) TO pulse_app;
