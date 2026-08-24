-- What each role may reach — tickets E0-10 and E0-26, SPEC §8, ADR 0001,
-- ADR 0043, ADR 0071.
--
-- **This supersedes `identity_grants_v001.sql`, and pulse_reveal_definer's grant
-- list is now FOUR, not three.** v001 is still the text E0-10's revision applied
-- and is never edited (ADR 0041), so its header goes on saying three — which was
-- true of the revision that ran it, and is the reason it is not corrected. If you
-- arrived at v001 or at `identity_roles_v001.sql` through a grep and read "three
-- grants", this file is the successor and four is the current number. Two things
-- changed, both from E0-26 item 1 splitting the reveal into two calls:
--
--   * the owner change, the REVOKE and the GRANT EXECUTE name the two new
--     functions rather than the dropped three-argument one;
--   * pulse_reveal_definer gains a fourth grant, SELECT on public.audit_log,
--     because the reveal now reads its subject and its actor out of the committed
--     record instead of taking them from its caller (ADR 0071).
--
-- Everything else is v001 unchanged, restated rather than referred to, so that
-- "what each role holds" stays one file somebody can read against the function
-- bodies in `reveal_student_identity_v002.sql`. ADR 0043's whole argument for a
-- dedicated owner is that its grant list is short enough to do that.
--
-- The shape is one sentence: pulse_app reads the views and nothing else,
-- pulse_care records and spends a reveal and nothing else, and **neither
-- connection role holds a privilege of any kind on public.user_identity**. "An
-- instructor screen cannot leak a name because the connection it runs on cannot
-- read the table."
--
-- **There is exactly one grant on public.user_identity in this project, and it is
-- to a role that cannot connect.** pulse_reveal_definer owns the two SECURITY
-- DEFINER functions and exists for nothing else; it is NOLOGIN, no mechanism
-- anywhere gives it a password, and nobody is a member of it. So the only way to
-- spend that SELECT is to call the reveal, which answers only against an
-- audit_log row that is already committed.
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
-- views keep the migration identity as their owner and the reveal functions do
-- not; ADR 0043 states the asymmetry, which is that a view can only ever be a
-- SELECT while a plpgsql body is code executed at request time.
--
-- **A function is the one kind of object that needs a REVOKE.** Postgres grants
-- EXECUTE on a new function to PUBLIC unless a migration says otherwise, so a
-- SECURITY DEFINER function reading identity is, by default, callable by every
-- role in the cluster — including the one every instructor screen runs on. That
-- is the state a migration reaches by not saying anything, which is why the two
-- REVOKE lines below are written and why an invariant test asserts pulse_app
-- cannot call either function.

GRANT USAGE ON SCHEMA public TO pulse_app, pulse_care, pulse_reveal_definer;

GRANT SELECT ON public.section_roster TO pulse_app;
GRANT SELECT ON public.section_enrollment_count TO pulse_app;

-- The one base table pulse_care reads, and it is not a concession. E0-10 puts
-- the CARE check in two places and E0-26 keeps it there across the split:
-- backend/app/services/safety.py verifies the acting party before it calls
-- anything, and both halves of the door verify again for themselves. The
-- service's half needs a connection that can read who holds which assignment, and
-- the only connection it is allowed to hold is this one. public.role_assignment
-- carries a person key, a role and five scope keys — no name, no email address —
-- so this widens what Care can see about *access* and not about people. It is
-- granted to pulse_care alone: what pulse_app may read is E0-11's decision, made
-- with the authorization chokepoint that needs it.
GRANT SELECT ON public.role_assignment TO pulse_care;

-- Everything the two function bodies do, and nothing else (ADR 0043, ADR 0071).
-- Read it against `reveal_student_identity_v002.sql` line by line:
-- record_identity_reveal reads role_assignment to check the actor holds a live
-- CARE assignment and inserts the audit row; reveal_student_identity reads that
-- audit row back, reads role_assignment to re-check the actor it names, and reads
-- user_identity. Four statements over four objects, four grants, and the
-- functions fail loudly the day a fifth object is named — which is the whole
-- reason this role exists rather than the functions running as the migration
-- identity, which is a superuser and would simply have succeeded.
--
-- **SELECT on public.audit_log is E0-26 item 1's, and it is a real widening.**
-- E0-10's definer could write a record and never read one; this one can read
-- every row of the table — who revealed whom, and when. What bounds it is the two
-- bodies: they read one row by primary key, they select four of its columns, and
-- neither returns any of them to a caller. The reveal needs it because it now
-- takes its subject and its actor *from the committed record* rather than from
-- its caller, which is what makes the record impossible to substitute and the
-- read impossible to take without one. ADR 0071 argues the trade, and
-- test_the_reveal_functions_owner_holds_exactly_the_privileges_its_job_needs
-- pins the set as an equality so a fifth grant is a failure rather than a
-- widening nobody sees.
--
-- Still no INSERT, UPDATE, DELETE or TRUNCATE on user_identity: the reveal reads
-- a name and must never be able to change one. Still no UPDATE or DELETE on
-- audit_log — §8 has the log append-only, and E10 owns the review surface §6.2
-- asks for.
--
-- The foreign keys on audit_log reach person and user, and no grant is needed
-- for them: Postgres runs a referential-integrity check with the referenced
-- table's own rights rather than the writer's. Measured on the pinned image
-- rather than read — this role holds nothing on either table and the insert
-- succeeds.
GRANT SELECT ON public.role_assignment TO pulse_reveal_definer;
GRANT SELECT ON public.user_identity TO pulse_reveal_definer;
GRANT INSERT ON public.audit_log TO pulse_reveal_definer;
GRANT SELECT ON public.audit_log TO pulse_reveal_definer;

-- The owner change, before the ACLs below, so the privileges Postgres records are
-- recorded against the role that ends up owning the object. A superuser may
-- grant on an object it does not own and the grantor stored is the owner, so the
-- lines that follow read the same either way — but doing it in this order means
-- no ACL entry ever names an owner a function no longer has.
ALTER FUNCTION public.record_identity_reveal(uuid, uuid, uuid) OWNER TO pulse_reveal_definer;
ALTER FUNCTION public.reveal_student_identity(uuid) OWNER TO pulse_reveal_definer;

REVOKE ALL ON FUNCTION public.record_identity_reveal(uuid, uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.reveal_student_identity(uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.record_identity_reveal(uuid, uuid, uuid) TO pulse_care;
GRANT EXECUTE ON FUNCTION public.reveal_student_identity(uuid) TO pulse_care;
