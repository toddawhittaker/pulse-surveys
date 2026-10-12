-- The person ADR 0024 links to each of a set of `user` rows — ticket E9-07's fix round, ADR 0205.
--
-- `resolve_person_for_user(uuid)` (identity_resolution_v001.sql) answers one
-- user per call, and ADR 0094 says a bulk need "must not loop these functions;
-- it needs its own reviewed mechanism". The roll-up figures are that need: a
-- response rate's denominator leaves out a section's staff, and a college node
-- holds thousands of enrolled members. This is the mechanism.
--
-- **The same question, the same answer, the same owner.** It reads
-- `person (id, user_id)` and nothing else, which `pulse_resolve_definer`
-- already holds for the point resolver, so the owner gains no privilege. It
-- answers ids only: one row per supplied user that a person is linked to, and
-- nothing for a user no person points at (a student, ADR 0028). It discloses
-- nothing a caller could not learn by calling the point resolver once per id;
-- what it changes is the number of round trips.
--
-- **Only the ids the caller supplies, and that is no limit on a determined
-- caller.** The body filters on the array it is given, but `pulse_app` can read
-- every `user.id`, so one call over all of them returns the whole user-to-person
-- map. That map is ids only and is what the point resolver gives one id at a
-- time; what this gives up is ADR 0094's point-lookup property, which ADR 0205
-- records as the cost. The narrower design, left unbuilt, is a definer keyed by
-- section that answers only the enrolled users who are staff on that section.

CREATE OR REPLACE FUNCTION public.resolve_persons_for_users(
    in_user_ids uuid[]
)
RETURNS TABLE (user_id uuid, person_id uuid)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT linked.user_id, linked.id
      FROM public.person AS linked
     WHERE linked.user_id = ANY (in_user_ids);
$$;

ALTER FUNCTION public.resolve_persons_for_users(uuid[])
    OWNER TO pulse_resolve_definer;

REVOKE ALL ON FUNCTION public.resolve_persons_for_users(uuid[]) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.resolve_persons_for_users(uuid[]) TO pulse_app;
