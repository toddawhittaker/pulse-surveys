-- What the application may do to the response loop's two records — E7-01, SPEC §5.3,
-- §8, ADR 0192.
--
-- `public.instructor_response` holds every published response and every edit of
-- one, and `public.response_policy` every policy change. Both are append-only: an
-- edit is a new row and the latest row is what students see (the owner's ruling 3
-- for E7), and the tables are the record of who responded and who set a policy
-- (ruling 7). So `pulse_app` may read them and insert the columns a row names, at
-- column grain and nothing wider.
--
-- **What is withheld is the point**, as on `moderation_state`
-- (`moderation_decision_grants_v001.sql`). Each row's key (`gen_random_uuid()`)
-- and its `sequence` are the database's to fill: `sequence` is the order "latest"
-- is read by (ADR 0187), so a connection that could write it could put one row
-- before another. There is no `UPDATE`, `DELETE` or `TRUNCATE`: a connection that
-- could rewrite a row could change a published response under the students who
-- read it, or re-date the policy that held a week.
--
-- The two time columns are the application's to write, from `services/clock.now`,
-- so that the development clock stays coherent (the ruling on B2 appended to
-- E7-01's work order). Order is never read from them.
--
-- A grant cannot say who a row may name, so who may write each row is checked by a
-- trigger when it is written (`response_loop_guard_v001.sql`).

GRANT SELECT ON public.instructor_response TO pulse_app;
GRANT INSERT (section_id, week_id, term_id, author_person_id, role, ai_seeded, body, published_at)
    ON public.instructor_response TO pulse_app;

GRANT SELECT ON public.response_policy TO pulse_app;
GRANT INSERT (prefix_id, set_by_person_id, role, mode, set_at)
    ON public.response_policy TO pulse_app;
