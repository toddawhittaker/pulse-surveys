-- What the authorization chokepoint may read, re-stated over the re-versioned
-- assignment_scope — ticket E1-13, SPEC §8, ADR 0001, ADR 0041.
--
-- E1-13 replaces public.assignment_scope with a _v002 carrying ADR 0026's two
-- entry-door columns, and a privilege cannot outlive the object it is on: the
-- DROP VIEW that precedes the CREATE takes pulse_app's SELECT with it. So the
-- grant is re-made here, and re-made for all three views rather than for the one
-- that moved.
--
-- **All three, deliberately.** GRANT is idempotent, so re-stating the two views
-- this ticket does not touch costs nothing and buys the property that this file
-- is the whole answer to "what may the chokepoint read" at the revision that
-- executes it — the same reason identity_grants_v002.sql re-states E0-10's whole
-- set rather than the one grant its own revision changed. A file that listed only
-- the difference would have to be read beside its predecessor to be understood,
-- and the predecessor is the one nobody opens.
--
-- **USAGE ON SCHEMA public is not granted again here**, exactly as
-- authz_grants_v001.sql says: identity_grants_v001.sql grants it and its own
-- downgrade is the only thing in the tree that takes it back, an ACL entry
-- records no history, and a second grant here would be indistinguishable from
-- that one.
--
-- **The downgrade has nothing to revoke**, unchanged from v001. Every grant this
-- file makes is on a view, and the revision's downgrade drops and re-creates the
-- view it re-versions, which takes this grant with it before re-stating v001's.

GRANT SELECT ON public.assignment_scope TO pulse_app;
GRANT SELECT ON public.lead_faculty_course TO pulse_app;
GRANT SELECT ON public.containment_path TO pulse_app;
