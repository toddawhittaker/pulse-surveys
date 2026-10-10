-- What the instructor's decision door may write — E6-03, SPEC §5.2, §8, ADR 0189.
--
-- An instructor excludes, keeps or undoes a comment, and each step is one row
-- appended to `public.moderation_state`, naming the comment, its new state, the
-- decider, the role the decision was made under, the stated reason and whether
-- the row undoes an earlier one. Those six columns are what a decision writes,
-- so they are what `pulse_app` may insert, at column grain and nothing wider.
--
-- **What is withheld is the point.** The row's key (ADR 0016's
-- `gen_random_uuid()`), E6-01's `sequence` (the database's insertion order, which
-- decides which row is latest) and `decided_at` (a `now()` default) are the
-- database's to fill, so a decision never names them. There is no `UPDATE` or
-- `DELETE`: the record is append-only, and an undo is a new row. `pulse_app`'s
-- `SELECT` on the table is E4-04's, from a revision far below, and is untouched.
--
-- The routing definer keeps its own table-wide `INSERT`
-- (`moderation_routing_v001.sql`), and the trigger in
-- `moderation_state_router_rows_v001.sql` is what keeps a row with no decider
-- the definer's alone, since this grant includes `answer_id` and `state`.

GRANT INSERT (answer_id, state, decided_by_person_id, decided_as, reason, is_undo)
    ON public.moderation_state TO pulse_app;
