-- The web door's half of point resolution: an IdP subject to a person id, and
-- nothing else — ticket E1-12, ADR 0094 and ADR 0097.
--
-- identity_resolution_v001.sql answers the launch door's two hops. This file
-- answers the web door's one. An `id_token` identifies its holder by the pair
-- (issuer, sub) and by nothing else, and E1-12 stores which person that pair is
-- in public.web_login_subject — provisioned by the seed or by an administrator,
-- never inferred from a claim, because an address or a name is a value the
-- provider's administrator controls and a person can change.
--
-- **pulse_app holds no grant of any kind on that table**, which is what makes
-- this function the only route rather than the convenient one. A grant at table
-- grain would let the application connection enumerate every subject that has an
-- account here and read which person each one is, and a view cannot help — a view
-- can only be filtered on a column it exposes, so a lookup view re-exposes
-- idp_subject. So this is the same third mechanism the launch half uses (EXECUTE
-- on a SECURITY DEFINER function, per tests/integration/test_identity_grants.py):
-- pulse_app can resolve a subject it already holds from a token it has verified,
-- and can never enumerate the subjects it does not.
--
-- The owner is pulse_resolve_definer, the NOLOGIN role identity_resolution_v001.sql
-- creates and which exists for nothing else (ADR 0043's pattern, ADR 0094). This
-- file adds the sixth and last thing that role may reach: SELECT on
-- public.web_login_subject. That table carries no name and no address — an issuer,
-- an opaque subject and a person id — and this function can return nothing but a
-- uuid.
--
-- NULL is the answer for a subject with no row, and it is a defined state rather
-- than an error: the identity provider asserts that somebody authenticated, never
-- that Pulse has a record of them (SPEC §2 puts every role in Pulse's own
-- records). The door turns that NULL into the calm no-account page.
--
-- SET search_path names pg_temp last (ADR 0027: omitting it is what puts it
-- first), every relation is schema-qualified, parameters are typed, and there is
-- no dynamic SQL.
--
-- Unlike identity_resolution_v001.sql this file ships from E1-12 alone, so it
-- needs no replay guard of its own; CREATE OR REPLACE is used anyway, so that the
-- two files in this scheme are read the same way.

GRANT SELECT ON public.web_login_subject TO pulse_resolve_definer;

CREATE OR REPLACE FUNCTION public.resolve_web_person(
    in_idp_issuer text,
    in_idp_subject text
)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT linked.person_id
      FROM public.web_login_subject AS linked
     WHERE linked.idp_issuer = in_idp_issuer
       AND linked.idp_subject = in_idp_subject;
$$;

ALTER FUNCTION public.resolve_web_person(text, text)
    OWNER TO pulse_resolve_definer;

REVOKE ALL ON FUNCTION public.resolve_web_person(text, text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.resolve_web_person(text, text) TO pulse_app;
