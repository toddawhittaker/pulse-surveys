-- What each runtime role may reach — ticket E0-10, SPEC §8, ADR 0001.
--
-- The shape is one sentence: pulse_app reads the views and nothing else,
-- pulse_care executes the reveal and nothing else, and neither holds a privilege
-- of any kind on public.user_identity. "An instructor screen cannot leak a name
-- because the connection it runs on cannot read the table."
--
-- **Nothing here mentions public.user_identity, and that is the point.** A table
-- carries no privilege for anybody until one is granted, so the guarantee is what
-- this file does *not* say. A REVOKE would be worse than useless: it would read
-- as the control, and deleting it would change nothing, so the day somebody adds
-- a GRANT the REVOKE would still be sitting there looking like protection.
-- tests/integration/test_identity_grants.py asserts the absence out of
-- has_table_privilege for all seven table privileges, and provokes the refusal
-- separately, because a catalog test cannot see whether the rule works and a
-- behavioural test cannot see whether it exists.
--
-- **A view runs with its owner's privileges, not its reader's.** That is what
-- lets pulse_app read public.section_roster while holding nothing on
-- public.enrollment or public.section, and it is also why the structural test in
-- tests/integration/test_identity_column_marker.py exists: a view that read a
-- marked identity column would hand it over regardless of any grant here.
--
-- **The function is the one object that needs a REVOKE.** Postgres grants EXECUTE
-- on a new function to PUBLIC unless a migration says otherwise, so a SECURITY
-- DEFINER function reading identity is, by default, callable by every role in the
-- cluster — including the one every instructor screen runs on. That is the state
-- a migration reaches by not saying anything, which is why the line below is
-- written and why an invariant test asserts pulse_app cannot call it.

GRANT USAGE ON SCHEMA public TO pulse_app, pulse_care;

GRANT SELECT ON public.section_roster TO pulse_app;
GRANT SELECT ON public.section_enrollment_count TO pulse_app;

-- The one base table pulse_care reads, and it is not a concession. E0-10 puts
-- the CARE check in two places: backend/app/services/safety.py verifies the
-- acting party before it calls anything, and the reveal function verifies again
-- for itself. The service's half needs a connection that can read who holds
-- which assignment, and the only connection it is allowed to hold is this one.
-- public.role_assignment carries a person key, a role and five scope keys — no
-- name, no email address — so this widens what Care can see about *access* and
-- not about people. It is granted to pulse_care alone: what pulse_app may read
-- is E0-11's decision, made with the authorization chokepoint that needs it.
GRANT SELECT ON public.role_assignment TO pulse_care;

REVOKE ALL ON FUNCTION public.reveal_student_identity(uuid, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.reveal_student_identity(uuid, uuid, uuid) TO pulse_care;
