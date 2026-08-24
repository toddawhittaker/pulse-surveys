-- What the authorization chokepoint may read — ticket E0-11, SPEC §8, ADR 0001.
--
-- E0-10 left pulse_app holding SELECT on public.section_roster and
-- public.section_enrollment_count and on nothing else, and said in
-- identity_grants_v001.sql that the rest was this ticket's to decide: "what
-- pulse_app may read is E0-11's decision, made with the authorization chokepoint
-- that needs it." This file is that decision, and it is three views.
--
-- The shape is the same sentence E0-10 wrote: pulse_app reads views and never a
-- base table. It holds nothing on public.role_assignment, public.
-- lead_faculty_mapping or any of the six containment tables, so a resolver that
-- reached past these views would be refused by the server rather than by
-- whoever reviews it — measured the same way E0-10 measured its own claim, with
-- SET ROLE pulse_app and a direct select on each base table.
--
-- **Nothing here touches public.user_identity, public.person or public.user.**
-- That absence is the guarantee and it is deliberately not written as a REVOKE:
-- a table carries no privilege for anybody until one is granted, so a REVOKE
-- would read as the control while changing nothing, and the day somebody adds a
-- GRANT it would still be sitting there looking like protection.
-- identity_grants_v001.sql makes the same argument at more length.
--
-- **USAGE ON SCHEMA public is not granted again here**, although these views
-- need it. identity_grants_v001.sql grants it to pulse_app and its own downgrade
-- is the only thing in the tree that takes it back; an ACL entry records no
-- history, so a second grant here would be indistinguishable from that one and
-- the matching revoke in this revision's downgrade would remove both. This
-- revision depends on that one, so the privilege is always in place before these
-- views exist.
--
-- **The downgrade has nothing to revoke.** Every grant this file makes is on a
-- view the revision drops, and a privilege cannot outlive the object it is on —
-- which is the rule identity_grants_v001.sql's revision states and then has to
-- work around for the grants it makes on surviving tables. This one makes none.

GRANT SELECT ON public.assignment_scope TO pulse_app;
GRANT SELECT ON public.lead_faculty_course TO pulse_app;
GRANT SELECT ON public.containment_path TO pulse_app;
