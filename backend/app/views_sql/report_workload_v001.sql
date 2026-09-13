-- The workload mean and median a section-week's students submitted — ticket
-- E4-03, SPEC §3.2, §5.1, §4.1, ADR 0041, ADR 0147.
--
-- §5.1 asks for "workload mean/median for the section … (true numeric
-- statistics — §3.2)", and §3.2 stores the figure "as a decimal so reporting
-- can show true means and medians rather than band midpoints". Both halves of
-- that sentence are this file's job: the statistics are computed here, and they
-- are computed in exact decimal arithmetic.
--
-- **The median needs a cast back and the mean does not.** `avg` over a
-- `numeric` column answers in `numeric`. `percentile_cont` answers in `double
-- precision` whatever it is handed — it has no numeric form — so the `::numeric`
-- below is what keeps §3.2's sentence true. Dropping it returns a float that
-- prints the right digits, and every figure E4-07 divides and E5 compares is
-- then a float.
--
-- **`percentile_cont` rather than `percentile_disc` or an offset.** The
-- conventional median of an even-count week is the midpoint of its middle pair;
-- `percentile_disc` picks one of the pair instead, and a hand-rolled
-- `ORDER BY … OFFSET n/2 LIMIT 1` picks one or the other depending on how the
-- offset rounds. All three agree on an odd count, which is why the even case is
-- the one that decides the expression.
--
-- **Only the weeks that carry hours appear**, keyed by the `week` row exactly
-- as the distribution beside it is keyed, and for the reasons written there:
-- absence rather than a zero row, and no course-week arithmetic in SQL. A view
-- built from `response` with an outer join to the hours would emit a row per
-- responding week with a null mean, which reads on a report as a week whose
-- students answered "no hours" and is in fact a week nobody was asked.
--
-- **No column here names a person**: a section, a week, and two statistics over
-- a set of submissions.

CREATE VIEW public.report_workload AS
SELECT
    submitted.section_id AS section_id,
    submitted.week_id    AS week_id,
    avg(given.workload_hours) AS workload_mean,
    (percentile_cont(0.5) WITHIN GROUP (ORDER BY given.workload_hours))::numeric
        AS workload_median
FROM public.answer AS given
JOIN public.question AS asked ON asked.id = given.question_id
JOIN public.response AS submitted ON submitted.id = given.response_id
WHERE asked.kind = 'workload'
  AND given.workload_hours IS NOT NULL
GROUP BY submitted.section_id, submitted.week_id;
