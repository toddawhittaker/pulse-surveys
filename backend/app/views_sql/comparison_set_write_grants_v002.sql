-- UPDATE on a named comparison set narrowed to the columns an edit writes —
-- ticket E5-14, SPEC §5.1, ADR 0173, and the E5 boundary review's data-model
-- finding.
--
-- comparison_set_write_grants_v001.sql granted UPDATE on the whole of
-- public.comparison_set. An edit (app.services.comparison_sets.edit_set) writes
-- four columns: the name, the declared length and level, and updated_at. A
-- table-wide grant also let the application connection rewrite
-- created_by_person_id, which is the whole of who may edit or delete a set (ADR
-- 0173), and created_at and id, which are the record that the set was written
-- at all (ADR 0174). No route writes any of them after the insert, so the grant
-- is narrowed to what is spent.
--
-- **The REVOKE comes first and takes the table-wide grant only.** INSERT and
-- DELETE stay as v001 granted them, and so does E5-04's SELECT.

REVOKE UPDATE ON public.comparison_set FROM pulse_app;
GRANT UPDATE (name, length_weeks, level, updated_at) ON public.comparison_set TO pulse_app;
