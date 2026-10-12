-- benchmark_cohort_term_axis is retired: ticket E9-12, E9 README decision 10, ADR 0166.
--
-- Nothing reads it. E9-05 deleted its last reader, named_set_term_axis, and
-- the named-set and roll-up figures read the set functions over the reader's
-- purview instead. A whole-cohort aggregate no page shows is still a read
-- surface pulse_app holds, so it goes.
--
-- The drop is written here rather than inline in the revision because a view's
-- end of life is versioned like its creation (SPEC §13, ADR 0041): the files
-- under views_sql/, folded in name order, say which views a migrated database
-- holds. pulse_app's SELECT is recorded in the view's own ACL and goes with it.
-- The revision's downgrade recreates the view from its previous file.

DROP VIEW public.benchmark_cohort_term_axis;
