-- The workload statistics and the three counts of a start cohort, on §2.2's
-- term axis — ticket E5-03, SPEC §2.2, §3.2, §5.1, §4.1 items 1 and 7, §8,
-- ADR 0041, ADR 0165, and the ruling on docs/disputes/E5-03-01.md, which
-- settles this view's name and its column list.
--
-- The term axis and the start-date cohort key are as
-- benchmark_cohort_rating_term_axis_v001.sql records them; the row shape, the
-- outer join to the hours, the null-rather-than-nought rule, the median's cast
-- and the three counts' three units are as benchmark_cohort_week_v001.sql
-- records them. This file is the intersection of the two and states nothing
-- new — deliberately, because a rule restated in a fourth place is a rule with
-- four chances to drift.
--
-- One thing is worth saying here rather than by reference. `stream` is a key
-- column on the rating half of this axis and is absent from this half, exactly
-- as on the course-week axis: the workload question carries no stream (§3.2),
-- and the counts are about the week. A pair of views built from one template is
-- where a key column goes missing on the half nobody tested
-- (docs/MISTAKES.md entry 53's class), so both halves of both axes are
-- asserted.
--
-- **No minimum, and no column that names a person.**

CREATE VIEW public.benchmark_cohort_term_axis AS
SELECT
    taught.length_weeks AS length_weeks,
    offered.level       AS level,
    taught.term_id      AS term_id,
    taught.start_date   AS section_start_date,
    counted.number      AS term_week,
    avg(hours.workload_hours) AS workload_mean,
    (percentile_cont(0.5) WITHIN GROUP (ORDER BY hours.workload_hours))::numeric
                        AS workload_median,
    count(DISTINCT submitted.id)      AS response_count,
    count(DISTINCT submitted.user_id) AS respondent_count,
    count(DISTINCT taught.id)         AS section_count
FROM public.response AS submitted
JOIN public.section AS taught ON taught.id = submitted.section_id
JOIN public.course AS offered ON offered.id = taught.course_id
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
    taught.start_date,
    counted.number;
