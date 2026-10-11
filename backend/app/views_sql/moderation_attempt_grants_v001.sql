-- What the application may do with a failed moderation attempt — E6-01, ADR 0187.
--
-- `moderation_attempt` holds one row per moderation call that failed. E6-02's
-- sweep writes a row when a call fails and counts a comment's rows before trying
-- again (the attempt cap), on the connection the worker runs on. E6-01 creates
-- the table and issues this grant with it, so that E6-02 needs no migration of
-- its own (`docs/tickets/e6/README.md`, "Counters").
--
-- **SELECT and INSERT, and nothing else**, the same pair `classification`
-- carries: with no `UPDATE`, `DELETE` or `TRUNCATE`, a failed attempt cannot be
-- erased to reset a cap or rewritten to move one.
--
-- **pulse_care is granted nothing.** A failed call says nothing Care needs.
--
-- **The downgrade has nothing to revoke**: the revision drops the table, and a
-- privilege cannot outlive the object it is on.

GRANT SELECT, INSERT ON public.moderation_attempt TO pulse_app;
