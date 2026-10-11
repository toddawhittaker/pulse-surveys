-- `pulse_app` names the course a policy row covers — E7-02, M2, SPEC §5.3, ADR 0193.
--
-- M2 adds `response_policy.course_id`: a policy row covers one course, fixed when it
-- is written, because lead mappings keep no history. A setter's switch for a prefix is
-- written as one row per course they answer for there, so the application inserts the
-- course like the rest of the row. Everything else in `response_loop_grants_v001.sql`
-- stands: `SELECT` on both tables, column-grain `INSERT`, and no `UPDATE`, `DELETE`
-- or `TRUNCATE`.

GRANT INSERT (course_id) ON public.response_policy TO pulse_app;
