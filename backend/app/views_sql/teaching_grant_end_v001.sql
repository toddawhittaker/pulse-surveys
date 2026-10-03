-- The one door a teaching grant is ended through — E5.1-02, ADR 0183.
--
-- SPEC §2.1 makes the teaching instructor LMS-owned: the roster says who teaches.
-- `record_teaching_instructor` (teaching_instructor_v001.sql) is the door the
-- roster sync adds that grant through; this is the door it ends one through, when
-- a complete roster walk no longer lists the person as Instructor. The read
-- predicates in `app.services.authz` treat a grant as live while its row exists,
-- so ending a grant means deleting its row.
--
-- **Why a function and not a grant.** `pulse_app` holds no `DELETE` on
-- `public.role_assignment`, and must not: a grant cannot bound which role's row is
-- deleted, so the connection every screen runs on could delete a `CARE` row (the
-- row the reveal definers check) as readily as a teaching one. The body below
-- refuses anything but a section-scoped `INSTRUCTOR` row, and the signature has
-- nowhere to put a role.
--
-- **It ends a grant only on the word of a successful roster call of the same
-- section.** The caller names the `nrps_call` row of the walk that dropped the
-- person. A call that is missing, belongs to another section, or did not answer
-- 2xx is refused. A NULL response code (the call never reached the platform) is
-- not between 200 and 299, and the test is written so that NULL fails it.
--
-- **The record is written in the same call as the deletion.** The deleted row's
-- person, section and role go into `public.ended_teaching_grant` with the day and
-- the call. There is no exception handler and no `ON CONFLICT`: if the insert
-- fails (the table's `UNIQUE (assignment_id)` refusing a second record for one
-- grant, say), the whole call fails and the deletion is rolled back with it. A
-- grant cannot end without its row.
--
-- **A grant that is already gone answers false and writes nothing.** Two syncs of
-- one section can race to end the same grant; the second finds no row, and that is
-- not an error.
--
-- **No `SELECT ... FOR UPDATE`.** It needs `UPDATE` privilege, which the owner
-- does not hold. The `DELETE ... RETURNING` is what decides whether this call
-- ended the grant: a row deleted concurrently returns nothing, and nothing is
-- recorded.
--
-- The owner is `pulse_grant_end_definer`, a NOLOGIN role that exists for nothing
-- else (ADR 0043: one role per door). It holds exactly `SELECT, DELETE` on
-- `public.role_assignment`, `SELECT (id, section_id, response_code)` on
-- `public.nrps_call`, and `INSERT` on `public.ended_teaching_grant`. It is not
-- `pulse_instructor_definer`: a door that may add a teaching grant and a door that
-- may delete one are two doors, and one owner holding both would make each the
-- other's blast radius.
--
-- SET search_path names pg_temp last (ADR 0027), every relation is
-- schema-qualified, parameters are typed, and there is no dynamic SQL.

DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_grant_end_definer'
    ) THEN
        CREATE ROLE pulse_grant_end_definer NOLOGIN;
    END IF;
END
$do$;

GRANT SELECT, DELETE ON public.role_assignment TO pulse_grant_end_definer;
GRANT SELECT (id, section_id, response_code) ON public.nrps_call TO pulse_grant_end_definer;
GRANT INSERT ON public.ended_teaching_grant TO pulse_grant_end_definer;

CREATE OR REPLACE FUNCTION public.end_teaching_instructor(
    in_assignment_id uuid,
    in_nrps_call_id uuid,
    in_ended_on date
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    held_role public.assignment_role;
    held_section_id uuid;
    cited_section_id uuid;
    cited_response_code integer;
    cited_found boolean;
    ended_person_id uuid;
    ended_section_id uuid;
    ended_role public.assignment_role;
BEGIN
    SELECT held.role, held.section_id
      INTO held_role, held_section_id
      FROM public.role_assignment AS held
     WHERE held.id = in_assignment_id;
    IF NOT FOUND THEN
        -- Another sync already ended it.
        RETURN false;
    END IF;

    IF held_role IS DISTINCT FROM 'INSTRUCTOR'::public.assignment_role
       OR held_section_id IS NULL THEN
        RAISE EXCEPTION 'end_teaching_instructor ends only a section-scoped INSTRUCTOR assignment'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    SELECT cited.section_id, cited.response_code
      INTO cited_section_id, cited_response_code
      FROM public.nrps_call AS cited
     WHERE cited.id = in_nrps_call_id;
    cited_found := FOUND;
    IF NOT cited_found
       OR cited_section_id IS DISTINCT FROM held_section_id
       OR NOT coalesce(cited_response_code BETWEEN 200 AND 299, false) THEN
        RAISE EXCEPTION 'end_teaching_instructor needs a successful roster call of the same section'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    DELETE FROM public.role_assignment AS held
     WHERE held.id = in_assignment_id
    RETURNING held.person_id, held.section_id, held.role
         INTO ended_person_id, ended_section_id, ended_role;
    IF NOT FOUND THEN
        RETURN false;
    END IF;

    INSERT INTO public.ended_teaching_grant
        (assignment_id, person_id, section_id, role, ended_on, nrps_call_id)
    VALUES
        (in_assignment_id, ended_person_id, ended_section_id, ended_role, in_ended_on,
         in_nrps_call_id);
    RETURN true;
END;
$$;

ALTER FUNCTION public.end_teaching_instructor(uuid, uuid, date)
    OWNER TO pulse_grant_end_definer;

REVOKE ALL ON FUNCTION public.end_teaching_instructor(uuid, uuid, date) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.end_teaching_instructor(uuid, uuid, date) TO pulse_app;
