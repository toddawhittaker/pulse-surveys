-- The workload statistics and the three counts of a cohort week, aligned by
-- course week — ticket E5-03, SPEC §2.2, §3.2, §5.1, §4.1 items 1 and 7, §8,
-- ADR 0041, ADR 0165, and the ruling on docs/disputes/E5-03-01.md, which
-- settles this view's name and its column list.
--
-- The cohort key, the course-week derivation and the term-as-a-key-column rule
-- are the same three the rating half of this pair carries, and
-- benchmark_cohort_rating_week_v001.sql is where each is written out. What is
-- different here is the row: one per cohort week, with no stream on it, because
-- the workload question carries no stream (§3.2) and the three counts are about
-- the week rather than about a question.
--
-- **The row is built over the responses, and the hours hang off it.** That is
-- the load-bearing choice in this file. A view built the other way — over the
-- workload answers — drops a whole cohort week the moment nobody reports hours,
-- taking three true counts with it, and E5-04 then reads a week that had data
-- as a week that had none. So the hours are joined in on the left and the two
-- statistics are NULL when nobody submitted any.
--
-- **That is a departure from report_workload_v001.sql rather than a copy of
-- it**, and ADR 0165 records why the two disagree. Every column of that view is
-- a workload figure, so a row of nulls there would be a section week that looks
-- answered and is not; here the row carries response_count, respondent_count
-- and section_count beside the two figures, so withholding it would withhold
-- three true counts to avoid publishing two absent ones.
--
-- **Null, never nought.** A zero mean is a statement about how long a cohort's
-- students worked, made by nobody, and E5-05 renders the comparison workload
-- figure beside a section's own — so a fabricated 0.0 arrives on an
-- instructor's page as a benchmark. There is no coalesce in this file, and the
-- worse shape is the quieter one: averaging a zero in for every response that
-- reported no hours reads a week where one of five students reported four hours
-- as 0.8.
--
-- **The median needs a cast back and the mean does not**, exactly as
-- report_workload_v001.sql records: percentile_cont answers in double precision
-- whatever it is handed, so the ::numeric is what keeps §3.2's "true means and
-- medians" true in exact decimal arithmetic. percentile_cont rather than
-- percentile_disc, because the conventional median of an even-count set is the
-- midpoint of its middle pair. Both aggregates ignore the NULLs the outer join
-- produces, which is what makes a week with no hours a row of nulls rather than
-- a row of zeros.
--
-- **The three counts have three different units, said out loud because
-- docs/MISTAKES.md entry 50 is about a number whose unit nobody stated.**
-- response_count counts submissions; section_count counts sections; and
-- respondent_count counts **people** — a distinct count over the response's
-- author, computed inside this view, because a student may sit in two sections
-- of one cohort and E5-04 compares this figure against a minimum that exists to
-- protect people. It is never summed across anything: sums of distincts are not
-- distinct sums. The key it counts over never leaves the view.
--
-- **No minimum is applied here and none ever should be** (criterion 7): a
-- one-section cohort has a row, and the suppression decision is E5-04's.
--
-- **No column here names a person**: a length, a level, a term, a course week,
-- two statistics and three counts.

CREATE VIEW public.benchmark_cohort_week AS
SELECT
    taught.length_weeks AS length_weeks,
    offered.level       AS level,
    taught.term_id      AS term_id,
    counted.number
        - floor((taught.start_date - scheduled.start_date)::numeric / 7)::integer
                        AS course_week,
    avg(hours.workload_hours) AS workload_mean,
    (percentile_cont(0.5) WITHIN GROUP (ORDER BY hours.workload_hours))::numeric
                        AS workload_median,
    count(DISTINCT submitted.id)      AS response_count,
    count(DISTINCT submitted.user_id) AS respondent_count,
    count(DISTINCT taught.id)         AS section_count
FROM public.response AS submitted
JOIN public.section AS taught ON taught.id = submitted.section_id
JOIN public.course AS offered ON offered.id = taught.course_id
JOIN public.term AS scheduled ON scheduled.id = taught.term_id
JOIN public.week AS counted ON counted.id = submitted.week_id
LEFT JOIN (
    SELECT
        reported.response_id    AS response_id,
        reported.workload_hours AS workload_hours
    FROM public.answer AS reported
    JOIN public.question AS about ON about.id = reported.question_id
    WHERE about.kind = 'workload'
      AND reported.workload_hours IS NOT NULL
) AS hours ON hours.response_id = submitted.id
GROUP BY
    taught.length_weeks,
    offered.level,
    taught.term_id,
    counted.number - floor((taught.start_date - scheduled.start_date)::numeric / 7)::integer;
