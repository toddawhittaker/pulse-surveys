-- The per-stream rating figures and **the stream's own counts**, over an
-- arbitrary set of sections — ticket E5-04's fix round, SPEC §4.1 item 7,
-- §5.1, ADR 0041, ADR 0139, ADR 0165, ADR 0166.
--
-- v001 is unchanged in every respect but one: this body answers two more
-- numbers. Everything that file records still holds and is not restated.
--
-- **What changed, and why it is a confidentiality fix rather than a feature.**
-- v001 answered `rating_count`, which counts ratings, and nothing else a
-- minimum can be measured against — no count of people and no count of
-- sections. So `app.services.benchmarks` sealed each trend point with the
-- *week's* counts, taken from `benchmark_set_week`: counts of everybody who
-- answered anything that week, in every section anybody answered in. A security
-- review found the consequence: one stream answered inside a single section
-- could be shown as a figure over five sections, because the section minimum
-- was never evaluated against the population the mean was computed from at all.
-- SPEC §4.1 item 7 is about the figure, and docs/MISTAKES.md entry 50 is the
-- record of a threshold crossed by a count of something else.
--
-- **Both counts are per stream, which is what the GROUP BY already makes them.**
-- The rows are grouped by course week *and* stream, so a count taken inside the
-- group counts only the answers to that stream's question:
-- `rating_respondent_count` is the distinct **people** who rated this stream,
-- and `rating_section_count` is the distinct **sections** those ratings came
-- from. No FILTER is needed here, unlike in the workload body, because the WHERE
-- clause has already restricted the rows to answered ratings.
--
-- **`rating_count` stays and is still a count of ratings.** It is not a number
-- either minimum is measured against and it never was; it is kept because
-- removing it would make this a different function rather than a corrected one,
-- and because a reader wanting "how many answers is this mean over" is asking a
-- real question. The two counts beside it are the ones the seal uses.
--
-- **No grant changes.** Both counts are computed from `response.user_id` and
-- `section.id`, which `pulse_benchmark_definer` already holds column-grain
-- SELECT on — benchmark_definer_v001.sql lists its whole reach and ADR 0165's
-- 2026-09-13 amendment names every pair. This file adds nothing to it, and the
-- column-equality test is what keeps that true rather than this sentence.
--
-- **DROP and CREATE rather than CREATE OR REPLACE**, for the reason
-- benchmark_set_week_v002.sql measures: Postgres refuses to replace a function
-- whose return type changes, and two more OUT columns in a RETURNS TABLE is a
-- changed return type (42P13). The owner, the REVOKE and the EXECUTE grant are
-- re-issued because a dropped function takes its ACL with it.

DROP FUNCTION IF EXISTS public.benchmark_set_rating_week(uuid[]);

CREATE FUNCTION public.benchmark_set_rating_week(
    section_ids uuid[]
)
RETURNS TABLE (
    course_week integer,
    stream text,
    rating_mean numeric,
    rating_count bigint,
    rating_respondent_count bigint,
    rating_section_count bigint
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT
        counted.number
            - floor((taught.start_date - scheduled.start_date)::numeric / 7)::integer,
        asked.stream,
        avg(given.rating),
        count(*),
        count(DISTINCT submitted.user_id),
        count(DISTINCT taught.id)
    FROM public.answer AS given
    JOIN public.question AS asked ON asked.id = given.question_id
    JOIN public.response AS submitted ON submitted.id = given.response_id
    JOIN public.section AS taught ON taught.id = submitted.section_id
    JOIN public.term AS scheduled ON scheduled.id = taught.term_id
    JOIN public.week AS counted ON counted.id = submitted.week_id
    WHERE asked.kind = 'likert'
      AND given.rating IS NOT NULL
      AND taught.id = ANY(section_ids)
    GROUP BY
        counted.number - floor((taught.start_date - scheduled.start_date)::numeric / 7)::integer,
        asked.stream
    ORDER BY 1, 2;
$$;

ALTER FUNCTION public.benchmark_set_rating_week(uuid[])
    OWNER TO pulse_benchmark_definer;

REVOKE ALL ON FUNCTION public.benchmark_set_rating_week(uuid[]) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.benchmark_set_rating_week(uuid[]) TO pulse_app;
