-- The workload statistics, the week's counts, and **the hours' own counts**,
-- over an arbitrary set of sections — ticket E5-04's fix round, SPEC §4.1
-- item 7, §5.1, ADR 0041, ADR 0139, ADR 0165, ADR 0166.
--
-- v001 is unchanged in every respect but one: this body answers two more
-- numbers. Everything that file records — why a function rather than a view,
-- why SECURITY DEFINER, why an empty set answers no rows, why the figures agree
-- with benchmark_cohort_week by construction, why no minimum is applied here —
-- still holds and is not restated.
--
-- **What changed, and why it is a confidentiality fix rather than a feature.**
-- A security review of E5-04 found that a workload figure was sealed against
-- `respondent_count` and `section_count`, which count everybody who answered
-- *anything* that week. The workload mean and median are computed over the
-- responses that carry hours — the LEFT JOIN below, which ADR 0165 keeps on
-- purpose so that a week with responses and no hours holds its true counts
-- beside two null figures. So the two numbers diverge exactly when some
-- responders leave the hours blank, and they diverge in the disclosing
-- direction: two students' hours could be shown as a figure over fifteen
-- people. SPEC §4.1 item 7 suppresses a figure below the minimum, and the
-- minimum is about the people behind *that figure* — docs/MISTAKES.md entry 50
-- is the record of a threshold crossed by a count of something else.
--
-- **Both currencies, because a guard is named in every currency the thing it
-- guards is held in.** `workload_respondent_count` counts the distinct
-- **people** whose hours the two statistics average, and
-- `workload_section_count` counts the distinct **sections** those hours came
-- from. A fix that corrected only the first would still show a mean over one
-- section's hours as a mean over five sections.
--
-- **The week's overall counts stay, and both are still answered.**
-- `response_count`, `respondent_count` and `section_count` are what the week
-- *was*, which is the number a rating figure or a later reader may legitimately
-- want, and removing them would make this a different function rather than a
-- corrected one. The caller picks the pair that belongs to the figure it is
-- sealing; `app.services.benchmarks` does that in one place.
--
-- **No grant changes.** The two counts are computed from
-- `response.user_id`, `section.id` and `answer.workload_hours`, every one of
-- which `pulse_benchmark_definer` already holds column-grain SELECT on —
-- benchmark_definer_v001.sql lists its whole reach and ADR 0165's 2026-09-13
-- amendment names every pair. This file adds nothing to it, and the
-- column-equality test is what keeps that true rather than this sentence.
--
-- **DROP and CREATE rather than CREATE OR REPLACE, and the reason is measured
-- rather than assumed.** Postgres refuses to replace a function whose return
-- type changes, and two more OUT columns in a RETURNS TABLE is a changed return
-- type: `CREATE OR REPLACE` answers `cannot change return type of existing
-- function` (42P13). So the revision drops the old body and creates this one,
-- and the owner, the REVOKE and the EXECUTE grant below are re-issued because a
-- dropped function takes its ACL with it.

DROP FUNCTION IF EXISTS public.benchmark_set_week(uuid[]);

CREATE FUNCTION public.benchmark_set_week(
    section_ids uuid[]
)
RETURNS TABLE (
    course_week integer,
    workload_mean numeric,
    workload_median numeric,
    response_count bigint,
    respondent_count bigint,
    section_count bigint,
    workload_respondent_count bigint,
    workload_section_count bigint
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT
        counted.number
            - floor((taught.start_date - scheduled.start_date)::numeric / 7)::integer,
        avg(hours.workload_hours),
        (percentile_cont(0.5) WITHIN GROUP (ORDER BY hours.workload_hours))::numeric,
        count(DISTINCT submitted.id),
        count(DISTINCT submitted.user_id),
        count(DISTINCT taught.id),
        count(DISTINCT submitted.user_id)
            FILTER (WHERE hours.workload_hours IS NOT NULL),
        count(DISTINCT taught.id)
            FILTER (WHERE hours.workload_hours IS NOT NULL)
    FROM public.response AS submitted
    JOIN public.section AS taught ON taught.id = submitted.section_id
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
    WHERE taught.id = ANY(section_ids)
    GROUP BY
        counted.number - floor((taught.start_date - scheduled.start_date)::numeric / 7)::integer
    ORDER BY 1;
$$;

ALTER FUNCTION public.benchmark_set_week(uuid[])
    OWNER TO pulse_benchmark_definer;

REVOKE ALL ON FUNCTION public.benchmark_set_week(uuid[]) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.benchmark_set_week(uuid[]) TO pulse_app;
