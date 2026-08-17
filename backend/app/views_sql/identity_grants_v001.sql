-- What each role may reach — ticket E0-10, SPEC §8, ADR 0001, ADR 0043.
--
-- The shape is one sentence: pulse_app reads the views and nothing else,
-- pulse_care executes the reveal and nothing else, and **neither connection role
-- holds a privilege of any kind on public.user_identity**. "An instructor screen
-- cannot leak a name because the connection it runs on cannot read the table."
--
-- **There is exactly one grant on public.user_identity in this project, and it is
-- to a role that cannot connect.** pulse_reveal_definer owns the SECURITY DEFINER
-- reveal function and exists for nothing else; it is NOLOGIN, no mechanism
-- anywhere gives it a password, and nobody is a member of it. So the only way to
-- spend that SELECT is to call the function, which writes an audit row in the
-- same transaction. ADR 0043 records why the function has an owner of its own
-- rather than running as whoever applied the migration, and what that does not
-- protect against.
--
-- **Nothing here grants either connection role anything on public.user_identity,
-- and that absence is the guarantee.** A table carries no privilege for anybody
-- until one is granted, so the protection is what this file does *not* say about
-- pulse_app and pulse_care. A REVOKE would be worse than useless: it would read
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
-- marked identity column would hand it over regardless of any grant here. The
-- views keep the migration identity as their owner and the reveal function does
-- not; ADR 0043 states the asymmetry, which is that a view can only ever be a
-- SELECT while a plpgsql body is code executed at request time.
--
-- **The function is the one object that needs a REVOKE.** Postgres grants EXECUTE
-- on a new function to PUBLIC unless a migration says otherwise, so a SECURITY
-- DEFINER function reading identity is, by default, callable by every role in the
-- cluster — including the one every instructor screen runs on. That is the state
-- a migration reaches by not saying anything, which is why the line below is
-- written and why an invariant test asserts pulse_app cannot call it.

GRANT USAGE ON SCHEMA public TO pulse_app, pulse_care, pulse_reveal_definer;

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

-- Everything the reveal function's body does, and nothing else (ADR 0043). Read
-- it against `reveal_student_identity_v001.sql` line by line: it reads
-- role_assignment to check the actor holds a live CARE assignment, inserts the
-- audit row, and reads user_identity. Three statements, three grants, and the
-- function fails loudly the day a fourth statement is added — which is the whole
-- reason this role exists rather than the function running as the migration
-- identity, which is a superuser and would simply have succeeded.
--
-- No INSERT, UPDATE, DELETE or TRUNCATE on user_identity: the reveal reads a
-- name and must never be able to change one. No SELECT on audit_log either — the
-- function writes the record and does not read it back, and E10 owns the review
-- surface §6.2 asks for.
--
-- The foreign keys on audit_log reach person and user, and no grant is needed
-- for them: Postgres runs a referential-integrity check with the referenced
-- table's own rights rather than the writer's. Measured on the pinned image
-- rather than read — this role holds nothing on either table and the insert
-- succeeds.
GRANT SELECT ON public.role_assignment TO pulse_reveal_definer;
GRANT SELECT ON public.user_identity TO pulse_reveal_definer;
GRANT INSERT ON public.audit_log TO pulse_reveal_definer;

-- The owner change, before the ACL below, so the privileges Postgres records are
-- recorded against the role that ends up owning the object. A superuser may
-- grant on an object it does not own and the grantor stored is the owner, so the
-- two lines that follow read the same either way — but doing it in this order
-- means no ACL entry ever names an owner the function no longer has.
ALTER FUNCTION public.reveal_student_identity(uuid, uuid, uuid) OWNER TO pulse_reveal_definer;

REVOKE ALL ON FUNCTION public.reveal_student_identity(uuid, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.reveal_student_identity(uuid, uuid, uuid) TO pulse_care;
