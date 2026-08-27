-- What the application role may do on the three relations the roster sync writes
-- — ticket E1-11, decision D8, ADR 0001, ADR 0023, SPEC §6.1, §7.3.
--
-- E1-10's `launch_provisioning_grants_v001.sql` is the file this follows, and the
-- rule it follows is the same: a sanctioned writer in `app.services.authz` passes
-- the application-layer chokepoint, and the *database* is what says which verbs
-- that writer's connection actually holds. Neither is the other's backstop — ADR
-- 0045's "a caller can bypass it by not calling it" is why the grant is narrow, and
-- ADR 0090's catalog is why the write is routed.
--
-- **`enrollment`: SELECT, INSERT, and UPDATE on three columns.**
-- The `SELECT` is the lookup that decides insert-or-update: a member already
-- enrolled must not be enrolled twice, and ADR 0023's exclusion constraint would
-- refuse the second row rather than answer the question. The `INSERT` is a member's
-- first sighting and a re-add after a drop, which ADR 0023 makes a second row
-- rather than an edit to the first.
--
-- The `UPDATE` is at **column** grain and the columns withheld are the assertion.
-- `ended_on` closes a window; `lms_window_start` and `lms_window_end` carry the ADR
-- 0048 extension's values, which a platform may revise between syncs (a drop dated
-- after the fact, a start corrected) — `lms_`-prefixed because the platform owns
-- them, and updatable for the same reason `course.lms_title` is. `started_on`,
-- `user_id` and `section_id` are **first-seen facts**: which member, which section,
-- and the day Pulse first saw them, which SPEC §3.4's fallback for an undated late
-- add is computed from. A connection that could rewrite them could re-date a
-- student's whole term.
--
-- **No `DELETE` anywhere.** A drop is a *closed window* rather than a deleted row
-- (ADR 0023, and this ticket's D3: the open and closed rows are the recorded
-- transition), so a connection able to delete an enrollment could erase the record
-- a participation figure is computed from.
--
-- **`role_assignment`: INSERT and no SELECT.** The row is the teaching instructor's
-- `INSTRUCTOR` assignment — SPEC §2.1's fifth owned item, and a purview grant,
-- since the whole oversight surface is computed from these rows. The sync needs to
-- know whether it has already written one and asks `public.assignment_scope`
-- (E0-11's view, which this role already reads) rather than the table, so no
-- table-grain read is spent here. No `UPDATE` and no `DELETE`: a connection able to
-- revise one could revoke a dean's purview.
--
-- **`nrps_call`: SELECT and INSERT.** E1-11's own record (D9), one row per NRPS HTTP
-- call. It is SPEC §6.1's "NRPS and AGS call logs with response codes", the
-- discriminator between a never-synced section and a synced-empty one, and the
-- memory the launch trigger's debounce is measured against — so the sync writes it
-- and reads it back. No `UPDATE` and no `DELETE`, because an append-only log is
-- only append-only if the grant says so.
--
-- Every grant here is recorded in `RUNTIME_BASE_TABLE_PRIVILEGES` and
-- `RUNTIME_COLUMN_PRIVILEGES` in `tests/integration/test_identity_grants.py`, each
-- with the sentence it rests on, and those inventories are equalities.

GRANT SELECT, INSERT ON public.enrollment TO pulse_app;
GRANT UPDATE (ended_on, lms_window_start, lms_window_end) ON public.enrollment TO pulse_app;

GRANT INSERT ON public.role_assignment TO pulse_app;

GRANT SELECT, INSERT ON public.nrps_call TO pulse_app;
