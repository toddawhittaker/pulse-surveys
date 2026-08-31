-- What the application may do to the relations a launch discovers — ticket
-- E1-10, SPEC §2.1, SPEC §7.3, SPEC §8, ADR 0001, ADR 0045, ADR 0090, ADR 0091.
--
-- This is the first grant in this scheme that lets pulse_app write a relation
-- SPEC §2.1 puts on the *LMS's* side, so it is the one that most needs its
-- reasoning written down.
--
-- **Why any of it.** §2.1 gives courses and sections two arrival paths, "hourly
-- roster sync + launch-time ingestion", and §7.3 makes the first staff launch of
-- a section the only thing that discovers it at all: the scheduled job "has no
-- way of its own to learn that a section exists. So the first staff launch of a
-- section bootstraps every later sync of it." `app.services.provisioning` is
-- that writer and it runs on the connection pulse_app holds, so without these
-- privileges every launch is refused by Postgres with 42501 in the middle of
-- somebody's request rather than by anything the ticket is about.
--
-- **This is the instrument ADR 0045 deferred, arriving narrowed rather than
-- widened.** That record wanted the opposite grant — refusing the application
-- role INSERT/UPDATE on these tables outright — and could not have it, because
-- "the launch path and E1's roster sync are the same connection, so the grant
-- would have to distinguish a sanctioned writer from an unsanctioned one, and no
-- such separation exists in E0." E1-10 does not solve that either: one connection
-- still serves both. What it does is spend the smallest grant its writer needs,
-- so the *database* refuses everything outside it whoever is asking, while
-- `guard_write`'s sanction catalog (ADR 0090) refuses the rest in Python. Two
-- instruments, neither replacing the other: the guard knows which writer is
-- asking and the database does not, and the database holds for callers that
-- never ask the guard at all.
--
-- **The reads** are the look-ups a launch has to make before it may write
-- anything: the prefix its context label names, the term whose dates contain the
-- day of the launch, that term's start-letter map row, and the course, section
-- and user rows an upsert has to find before it decides to insert. SELECT and
-- nothing else on the three configuration tables — §2.1 builds the org and the
-- calendar top-down in the admin console, so a launch may not create the
-- containment chain it hangs from.
--
-- **The writes** are INSERT on course, section and "user", and INSERT on
-- launch_defect. No DELETE and no TRUNCATE anywhere: a launch discovers rows and
-- never removes one, and a connection that could delete a course would take a
-- term's sections and every report keyed to them with it.
--
-- **UPDATE is granted at column grain and nowhere else.** Table-wide UPDATE on
-- section would hand this connection ADR 0021's four derived calendar columns,
-- whose whole rule is that `apply_section_code` is the only thing that writes
-- them — and that rule is otherwise held by a syntactic sweep that reads the
-- source and cannot see a statement assembled at run time. Table-wide UPDATE on
-- course would let a launch revise `lms_number`, which identifies the course and
-- which §8 derives `level` from.
--
--   - course(lms_title) — a launch corrects a fallback title once the platform
--     supplies a real one, and follows the platform when it renames a course.
--     §2.1 makes the title the LMS's, so following it is the rule rather than an
--     edit.
--   - course(title_is_fallback) — Pulse's own record of which of those two the
--     stored title is (ADR 0091), written by the same statement.
--   - section(lms_context_memberships_url) — §7.3's stored roster service
--     address, updated when a later staff launch advertises a different one.
--
-- **"user" gets no UPDATE in any form**, which is the narrowest entry here and
-- deliberate. ADR 0045 puts `user` in the guarded set because "`user.lms_user_id`
-- is the `sub` claim verbatim … and §4 keys every response to it", so the row is
-- insert-if-absent and never rewritten. Withholding UPDATE makes that a property
-- of the database rather than a rule the next writer has to remember — the same
-- shape §8's append-only `classification` grant takes, and worth more here,
-- because a connection that could rewrite one `lms_user_id` could reassign a
-- term's answers to a different person with nothing erroring.
--
-- **launch_defect gets INSERT and not SELECT.** The launch path records a defect
-- and moves on; E11 builds the surface that reads them, on whatever connection
-- that turns out to be. Withholding SELECT keeps that E11's decision, and it
-- shapes the writer: Postgres checks returned columns against the reader's
-- privileges, so `INSERT ... RETURNING` is refused too and the row's primary key
-- is generated in Python. `lti_launch_nonce_grants_v001.sql` took the identical
-- constraint for the identical reason.
--
-- **pulse_care is granted nothing.** The Care surface is the threat queue and the
-- audited reveal (§6.2, ADR 0001); a course, a section and a launch defect are no
-- part of it.
--
-- **USAGE ON SCHEMA public is not granted again here.** identity_grants_v001.sql
-- grants it to pulse_app and identity_grants_v002.sql restates it; an ACL entry
-- records no history, so a third grant would be indistinguishable from those and
-- any matching revoke would remove all of them.
--
-- **The downgrade revokes what this file grants**, except on launch_defect, whose
-- privileges go with the table the same revision drops.
-- `RUNTIME_BASE_TABLE_PRIVILEGES` and `RUNTIME_COLUMN_PRIVILEGES` in
-- `tests/integration/test_identity_grants.py` are the hand-written record this
-- widening is measured against, as equalities in both directions; E1-10 adds its
-- ten table entries and its three column entries there in the same change
-- (ADR 0043).

GRANT SELECT ON public.prefix TO pulse_app;
GRANT SELECT ON public.term TO pulse_app;
GRANT SELECT ON public.start_letter_map TO pulse_app;

GRANT SELECT, INSERT ON public.course TO pulse_app;
GRANT SELECT, INSERT ON public.section TO pulse_app;
GRANT SELECT, INSERT ON public."user" TO pulse_app;

GRANT UPDATE (lms_title, title_is_fallback) ON public.course TO pulse_app;
GRANT UPDATE (lms_context_memberships_url) ON public.section TO pulse_app;

GRANT INSERT ON public.launch_defect TO pulse_app;
