-- Point resolution of an authenticated subject to row ids, and nothing else —
-- tickets E1-11 and E1-12, ADR 0094.
--
-- Both tickets need the same lookup: the doors resolve a launch subject to its
-- `user` and `person` rows (E1-12), and the roster sync matches NRPS members to
-- `user` rows before it may write an enrollment (E1-11). The column that
-- answers it, `user.lms_user_id`, is exactly the column
-- launch_provisioning_grants_v002.sql revoked from pulse_app: a connection
-- able to read it can enumerate every subject that ever launched and join a
-- response back to the person who gave it. A view cannot help — a view can only
-- be filtered on a column it exposes, so a lookup view re-exposes the column.
--
-- So this is the identity-grant scheme's third mechanism (EXECUTE, per
-- tests/integration/test_identity_grants.py): a SECURITY DEFINER function
-- answers the point query — this subject, this id — while the connection holds
-- no read on the column at all. pulse_app can resolve a subject it already
-- holds from a verified token or a roster document, and can never enumerate
-- subjects it does not.
--
-- The owner is pulse_resolve_definer, a NOLOGIN role that exists for nothing
-- else, so "the definer's privileges" is a list you can read in this file
-- against these bodies (ADR 0043's pattern, ADR 0094). It holds SELECT on five
-- columns and no identity-bearing column among them: ids, the platform
-- reference, and the subject key being matched. It never reads
-- user_identity, and neither function can return anything but a uuid.
--
-- SET search_path names pg_temp last (ADR 0027: omitting it is what puts it
-- first), every relation is schema-qualified, parameters are typed, and there
-- is no dynamic SQL.
--
-- This file ships identically from E1-11 and E1-12, whichever merges first;
-- CREATE OR REPLACE and the guarded role creation keep the second branch's
-- revision a no-op replay. ADR 0094 records the arrangement.

DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_resolve_definer'
    ) THEN
        CREATE ROLE pulse_resolve_definer NOLOGIN;
    END IF;
END
$do$;

GRANT SELECT (id, lti_platform_id, lms_user_id) ON public."user"
    TO pulse_resolve_definer;
GRANT SELECT (id, user_id) ON public.person TO pulse_resolve_definer;

CREATE OR REPLACE FUNCTION public.resolve_platform_user(
    in_lti_platform_id uuid,
    in_lms_user_id text
)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT known.id
      FROM public."user" AS known
     WHERE known.lti_platform_id = in_lti_platform_id
       AND known.lms_user_id = in_lms_user_id;
$$;

CREATE OR REPLACE FUNCTION public.resolve_person_for_user(
    in_user_id uuid
)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT linked.id
      FROM public.person AS linked
     WHERE linked.user_id = in_user_id;
$$;

ALTER FUNCTION public.resolve_platform_user(uuid, text)
    OWNER TO pulse_resolve_definer;
ALTER FUNCTION public.resolve_person_for_user(uuid)
    OWNER TO pulse_resolve_definer;

REVOKE ALL ON FUNCTION public.resolve_platform_user(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.resolve_person_for_user(uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.resolve_platform_user(uuid, text) TO pulse_app;
GRANT EXECUTE ON FUNCTION public.resolve_person_for_user(uuid) TO pulse_app;
