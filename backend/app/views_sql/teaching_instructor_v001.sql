-- The one door the roster sync writes a teaching instructor's assignment through —
-- E1-11's security review, F2; ADR 0043, ADR 0090, ADR 0096.
--
-- The review's MEDIUM: E1-11 gave `pulse_app` a table-wide `INSERT` on
-- `public.role_assignment` so the sync could write the teaching instructor's row.
-- `guard_write` refuses only an `INSTRUCTOR` row, and that is a *Python* rule — so
-- the connection every screen in the product runs on could write a `CARE`
-- assignment, which is the row E0-10's reveal definers check for before they
-- return a name (SPEC §6.2, §4). A grant cannot bound a column's *value*: there is
-- no `GRANT INSERT (role = 'INSTRUCTOR')`. So the grant is gone and the one
-- legitimate write goes through this function, whose body writes `'INSTRUCTOR'` and
-- whose signature has nowhere to put another role — exactly the way
-- `roster_email_v001.sql` bounds its write to an address and never a name.
--
-- The owner is `pulse_instructor_definer`, a NOLOGIN role that exists for nothing
-- else, so "the definer's privileges" is a list you can read in this file against
-- this body (ADR 0043). It holds `INSERT` and `SELECT` on `public.role_assignment`
-- and nothing anywhere else — not `person`, not `user_identity`, so a caller of
-- this function can reach no name through it.
--
-- **The `SELECT` is for the existence check, not a conflict clause.**
-- `role_assignment` carries no unique constraint — ADR 0009 leaves "two chairs of
-- one department" writable — so `ON CONFLICT` has nothing to name. The sync runs
-- hourly and calls this once per section it syncs, and two rows for one person and
-- section is a purview grant recorded twice (E11's people surfaces render it, and
-- §2.1 computes purview by walking these rows). So the function is idempotent on
-- its own: it inserts only where no such `INSTRUCTOR` assignment already exists.
-- That is defence in depth beside the sync's own `assignment_scope` check and its
-- `guard_write` call — the write is guarded in three places and none of them is the
-- only one.
--
-- **`reports_to` is NULL**, because SPEC §2.1 and ADR 0044 keep supervision edges
-- out of E1: they are E9's admin surface, and an edge written here would be a
-- supervision claim no human made. The primary key is generated in the body with
-- `gen_random_uuid()`, matching `UuidPrimaryKey`'s server default.
--
-- SET search_path names pg_temp last (ADR 0027: omitting it is what puts it
-- first), every relation is schema-qualified, parameters are typed, and there is
-- no dynamic SQL.

DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_instructor_definer'
    ) THEN
        CREATE ROLE pulse_instructor_definer NOLOGIN;
    END IF;
END
$do$;

GRANT INSERT, SELECT ON public.role_assignment TO pulse_instructor_definer;

CREATE OR REPLACE FUNCTION public.record_teaching_instructor(
    in_person_id uuid,
    in_section_id uuid
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    -- The role is the body's and never the caller's, which is the whole reason
    -- this is a function rather than a grant. Idempotent: the hourly sync calls
    -- this once per section, and a second identical row is a purview grant recorded
    -- twice on a table no UNIQUE constraint guards.
    IF NOT EXISTS (
        SELECT 1
          FROM public.role_assignment AS held
         WHERE held.person_id = in_person_id
           AND held.section_id = in_section_id
           AND held.role = 'INSTRUCTOR'
    ) THEN
        INSERT INTO public.role_assignment (id, person_id, role, section_id, reports_to)
        VALUES (pg_catalog.gen_random_uuid(), in_person_id, 'INSTRUCTOR', in_section_id, NULL);
    END IF;
END;
$$;

ALTER FUNCTION public.record_teaching_instructor(uuid, uuid)
    OWNER TO pulse_instructor_definer;

REVOKE ALL ON FUNCTION public.record_teaching_instructor(uuid, uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.record_teaching_instructor(uuid, uuid) TO pulse_app;
