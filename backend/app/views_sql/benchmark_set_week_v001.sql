-- The workload statistics and the three counts over an arbitrary set of
-- sections — ticket E5-03, SPEC §2.2, §3.2, §5.1, §4.1 items 1 and 7, §8,
-- ADR 0041, ADR 0139, ADR 0165, and the ruling on docs/disputes/E5-03-01.md,
-- which settles this function's name, its argument and the rows it answers.
--
-- The four cohort views answer for a whole cohort, which is a key. E5-04's
-- comparison sets are not keys: a default set is one lead's courses, a named
-- set is a list somebody chose, and each has the hero section taken out of it.
-- Those are subsets of a cohort that the database has no column for, so the set
-- is the argument and the answer is a row per course week.
--
-- **Why a function rather than a grant, which is the whole of the dispute.**
-- Counting distinct *students* across a set requires reading the rows that say
-- which student answered where, and any relation wide enough for the
-- application to do that arithmetic itself is a person-week index spanning
-- every section of a cohort across terms. E5-03's scope forbids exactly that —
-- "section id and numbers, never a person" — and SPEC §8 requires the
-- separation to be structural rather than a convention about callers. So the
-- arithmetic happens here, under an owner the application is not, and numbers
-- come back. A per-section pre-aggregate the caller sums was rejected for the
-- arithmetic it gets wrong: sums of distincts are not distinct sums, and the
-- over-count runs in the direction that lets a thin set past a threshold that
-- exists to protect people (docs/MISTAKES.md entry 50). ADR 0165 carries the
-- argument and the two rejected shapes.
--
-- **SECURITY DEFINER, owned by pulse_benchmark_definer**, whose whole reach is
-- listed in benchmark_definer_v001.sql. Written as SECURITY INVOKER this
-- function would answer with its caller's own reach and buy nothing: today it
-- would still work, and it would stop working the day a base-table grant
-- narrows, for a reason nobody would connect to this file.
--
-- **The figures agree with benchmark_cohort_week_v001.sql by construction**,
-- because they are the same expressions over the same rows: the row is built
-- over the responses, the hours hang off it on the left, the absent figures are
-- null rather than nought, and the median is cast back to numeric. That file
-- records why each of those is what it is. Handed every section of a cohort,
-- this answers what that view answers, and a test sets the two side by side.
--
-- **An empty set answers no rows.** A named set may have no members and a
-- default set may be empty once the hero section is excluded, so an empty array
-- is an ordinary input: `= ANY` of an empty array is false for every row, which
-- is no rows rather than an error and rather than one row of nulls that E5-04
-- would read as a cohort of nobody.
--
-- **No minimum is applied here**; the suppression decision is E5-04's, in one
-- place.
--
-- SET search_path names pg_temp last (ADR 0027: omitting it is what puts it
-- first), every relation is schema-qualified, the parameter is typed, and there
-- is no dynamic SQL.

CREATE OR REPLACE FUNCTION public.benchmark_set_week(
    section_ids uuid[]
)
RETURNS TABLE (
    course_week integer,
    workload_mean numeric,
    workload_median numeric,
    response_count bigint,
    respondent_count bigint,
    section_count bigint
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
        count(DISTINCT taught.id)
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
