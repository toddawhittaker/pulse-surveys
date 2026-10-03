-- The four columns more that the benchmark definer reads — ticket E5-14, SPEC §4.1
-- item 7, §5.1, ADR 0165, and the owner's "freeze at close" ruling of 2026-09-22.
--
-- benchmark_definer_v001.sql created pulse_benchmark_definer and granted it the
-- eighteen columns v001 and v002 of the two set functions read. The v003 bodies
-- count a response toward a course week only once it was fixed by that week's
-- cutoff, and deciding that needs two facts the owner could not read:
--
--   - `response.last_submitted_at`, when the answer was last changed;
--   - `survey_window (section_id, week_id, closes_at)`, when the window that
--     answer was given in closed. `section_id` and `week_id` are the join key
--     from a response to its window; `closes_at` is the instant compared.
--
-- **Column-grain, as ADR 0165 settles for this owner**, and nothing else on
-- `survey_window`: not `id`, not `opens_at`, not `term_id`. None of the four
-- columns reaches a person; `response.user_id`, already granted, is still the
-- only one that does, and it is still grouped away inside both bodies.
--
-- **The downgrade revokes exactly these four**, by name, so the v001 grants
-- below this revision stay where they are.

GRANT SELECT (last_submitted_at) ON public.response TO pulse_benchmark_definer;
GRANT SELECT (section_id, week_id, closes_at) ON public.survey_window
    TO pulse_benchmark_definer;
