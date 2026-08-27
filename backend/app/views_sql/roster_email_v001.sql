-- The one door the roster sync writes an email address through — ticket E1-11,
-- decision D7, ADR 0050, ADR 0094.
--
-- SPEC §7.3 has the sync store "email addresses where exposed", and ADR 0050
-- settles what NRPS exposes here: "an address and no name". The table those
-- addresses live in is `public.user_identity`, and E0-10's grant model gives
-- `pulse_app` **no privilege of any kind** on it — that is an `invariant`-marked
-- assertion in tests/integration/test_identity_grants.py, and it is what keeps
-- every address in a deployment out of the connection every instructor screen
-- runs on.
--
-- So the address reaches the table the way ADR 0094 has a subject reach a row id:
-- through a SECURITY DEFINER function, owned by a NOLOGIN role that exists for
-- nothing else and holds exactly the columns the job needs. Three grants, and the
-- list is the blast radius:
--
--   * INSERT (user_id, identity_email) — a member this deployment has an address
--     for and no identity row yet;
--   * UPDATE (identity_email) — an address the platform changed, or withdrew;
--   * SELECT (user_id, identity_email) — an `INSERT … ON CONFLICT (user_id) DO
--     UPDATE` has to see the conflicting row, and the two columns it may see are
--     the two it may write.
--
-- **`identity_name` is in none of the three**, which is what makes "the sync never
-- writes a name" a property of the grant rather than of the body below. A later
-- revision of this function cannot return or overwrite a name without a grant that
-- is a visible diff in a migration; and `tests/integration/
-- test_the_roster_definers_answer_a_point_query_and_nothing_more.py` pins the
-- owner's privileges as an equality, so widening them is not a quiet change.
-- ADR 0043 is the pattern; ADR 0095 records this ticket's own reasoning.
--
-- **Two branches, because "no address" and "the address changed" are different
-- facts.** A member the platform exposes no address for gets **no row at all** —
-- absence is the honest state, and a row per member carrying a null email turns
-- "this deployment holds an address for nobody" into "it holds a record for
-- everybody, empty". A member whose address disappears from a roster it used to be
-- in has the field nulled: a platform that stops exposing addresses is a
-- deployment that has withdrawn them, and Pulse holding one it is no longer told
-- about is identity nobody can account for.
--
-- **Both branches are no-ops when nothing changed**, and that is not tidiness: the
-- sync runs hourly and E1-11 criterion 6 is that a second run against an unchanged
-- roster changes no row. An unconditional `DO UPDATE` would rewrite every identity
-- row every hour, which is a different row for anything that reads `xmin`, a
-- trigger, or a replication stream.
--
-- SET search_path names pg_temp last (ADR 0027: omitting it is what puts it
-- first), every relation is schema-qualified, parameters are typed, and there is
-- no dynamic SQL.

DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_roster_definer'
    ) THEN
        CREATE ROLE pulse_roster_definer NOLOGIN;
    END IF;
END
$do$;

GRANT INSERT (user_id, identity_email) ON public.user_identity TO pulse_roster_definer;
GRANT UPDATE (identity_email) ON public.user_identity TO pulse_roster_definer;
GRANT SELECT (user_id, identity_email) ON public.user_identity TO pulse_roster_definer;

CREATE OR REPLACE FUNCTION public.record_roster_email(
    in_user_id uuid,
    in_identity_email text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF in_identity_email IS NULL THEN
        -- The platform stopped exposing an address for a member it exposes. No
        -- row is created here: a member who never had an address recorded has
        -- nothing to clear, and inventing a row to hold the absence is the state
        -- this function exists not to reach.
        UPDATE public.user_identity AS held
           SET identity_email = NULL
         WHERE held.user_id = in_user_id
           AND held.identity_email IS NOT NULL;
        RETURN;
    END IF;

    INSERT INTO public.user_identity (user_id, identity_email)
    VALUES (in_user_id, in_identity_email)
    ON CONFLICT (user_id) DO UPDATE
       SET identity_email = excluded.identity_email
     WHERE public.user_identity.identity_email IS DISTINCT FROM excluded.identity_email;
END;
$$;

ALTER FUNCTION public.record_roster_email(uuid, text) OWNER TO pulse_roster_definer;

REVOKE ALL ON FUNCTION public.record_roster_email(uuid, text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.record_roster_email(uuid, text) TO pulse_app;
