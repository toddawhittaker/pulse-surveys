-- The workload statistics and their counts over a set of sections, each course
-- week counted only from what was fixed by that week's cutoff — ticket E5-14,
-- SPEC §4.1 item 7, §5.1, ADR 0165, ADR 0166, and the owner's "freeze at close"
-- ruling of 2026-09-22.
--
-- v002 is unchanged in every respect but one: which responses a course week
-- counts. Everything v001 and v002 record — why a function rather than a view,
-- why SECURITY DEFINER, why an empty set answers no rows, why no minimum is
-- applied here, why each figure carries its own contributors' counts — still
-- holds and is not restated.
--
-- **What changed, and why it is a confidentiality fix.** The E5 boundary review
-- found that v002 counted every stored response, including responses in a
-- later-starting section whose window for the same course week was still open.
-- The report recomputes its comparison on every read, so a published figure
-- moved one student at a time while that window stayed open, and the difference
-- between two reads was one student's answer. The ruling: a figure for course
-- week w counts a response only if
--
--   - the window it was submitted in (its section's `survey_window` for its
--     week) closed at or before the cutoff for w, and
--   - it was last submitted at or before that cutoff.
--
-- The caller passes the cutoffs. The report passes, for each published course
-- week, the instant its own section's window for that week closed, so a
-- published figure is a function of rows fixed at or before that instant and
-- never moves again. Prior terms therefore count in full.
--
-- **The arguments.** `course_weeks[i]` pairs with `closed_by[i]`, and the
-- function answers rows only for the course weeks it was asked for. Arrays of
-- different lengths pair a week with a null cutoff, and a comparison with null
-- is never true, so that week counts nothing: a caller that gets the arrays out
-- of step gets suppressed figures, never unfrozen ones.
--
-- **A response whose section has no window for its week is not counted.** The
-- window is what says the answer was fixed; with no window row nothing says so.
--
-- **Two more columns for the owner.** The body reads `response.last_submitted_at`
-- and `survey_window (section_id, week_id, closes_at)`, which
-- benchmark_definer_v002.sql grants to pulse_benchmark_definer, column-grain, in
-- the same revision.
--
-- **DROP and CREATE**, because the argument list changes and a function is
-- identified by it: `CREATE OR REPLACE` with three arguments would create a
-- second function beside the one-argument one rather than replacing it. The
-- owner, the REVOKE and the EXECUTE grant below are re-issued because a dropped
-- function takes its ACL with it.

DROP FUNCTION IF EXISTS public.benchmark_set_week(uuid[]);

CREATE FUNCTION public.benchmark_set_week(
    section_ids uuid[],
    course_weeks integer[],
    closed_by timestamptz[]
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
        asked.week_asked,
        avg(hours.workload_hours),
        (percentile_cont(0.5) WITHIN GROUP (ORDER BY hours.workload_hours))::numeric,
        count(DISTINCT placed.response_id),
        count(DISTINCT placed.user_id),
        count(DISTINCT placed.section_id),
        count(DISTINCT placed.user_id)
            FILTER (WHERE hours.workload_hours IS NOT NULL),
        count(DISTINCT placed.section_id)
            FILTER (WHERE hours.workload_hours IS NOT NULL)
    FROM unnest(course_weeks, closed_by) AS asked(week_asked, cutoff)
    JOIN (
        SELECT
            submitted.id                AS response_id,
            submitted.user_id           AS user_id,
            taught.id                   AS section_id,
            submitted.last_submitted_at AS last_submitted_at,
            windowed.closes_at          AS closes_at,
            counted.number
                - floor((taught.start_date - scheduled.start_date)::numeric / 7)::integer
                                        AS course_week
        FROM public.response AS submitted
        JOIN public.section AS taught ON taught.id = submitted.section_id
        JOIN public.term AS scheduled ON scheduled.id = taught.term_id
        JOIN public.week AS counted ON counted.id = submitted.week_id
        JOIN public.survey_window AS windowed
          ON windowed.section_id = submitted.section_id
         AND windowed.week_id = submitted.week_id
        WHERE taught.id = ANY(section_ids)
    ) AS placed
      ON placed.course_week = asked.week_asked
     AND placed.closes_at <= asked.cutoff
     AND placed.last_submitted_at <= asked.cutoff
    LEFT JOIN (
        SELECT
            reported.response_id    AS response_id,
            reported.workload_hours AS workload_hours
        FROM public.answer AS reported
        JOIN public.question AS about ON about.id = reported.question_id
        WHERE about.kind = 'workload'
          AND reported.workload_hours IS NOT NULL
    ) AS hours ON hours.response_id = placed.response_id
    GROUP BY asked.week_asked
    ORDER BY 1;
$$;

ALTER FUNCTION public.benchmark_set_week(uuid[], integer[], timestamptz[])
    OWNER TO pulse_benchmark_definer;

REVOKE ALL ON FUNCTION public.benchmark_set_week(uuid[], integer[], timestamptz[]) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.benchmark_set_week(uuid[], integer[], timestamptz[])
    TO pulse_app;
