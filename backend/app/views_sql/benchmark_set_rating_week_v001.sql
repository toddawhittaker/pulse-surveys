-- The per-stream rating figures over an arbitrary set of sections — ticket
-- E5-03, SPEC §3.2, §5.1, §4.1 items 1 and 7, §8, ADR 0041, ADR 0139, ADR 0165,
-- and the ruling on docs/disputes/E5-03-01.md, which settles this function's
-- name, its argument and the rows it answers.
--
-- The rating half of the pair benchmark_set_week_v001.sql opens. Why the
-- building block is a function at all, why it is SECURITY DEFINER, who owns it
-- and what an empty set answers are written out in that file and are the same
-- here.
--
-- **Keyed by course week and stream.** SPEC §5.1 puts the two streams in
-- separate panels, and the stream is read off the question (E4-02's column),
-- never off its position: the question set is versioned, so a rating's ordinal
-- is not its meaning. A stream nobody answered has no row rather than a row
-- with a null mean, which is the same absence-not-zero contract the views
-- carry.
--
-- **`rating_count` counts ratings.** The count of people is respondent_count on
-- the sibling function, and each says its unit out loud because
-- docs/MISTAKES.md entry 50 is about a number whose unit nobody stated.
--
-- SET search_path names pg_temp last (ADR 0027: omitting it is what puts it
-- first), every relation is schema-qualified, the parameter is typed, and there
-- is no dynamic SQL.

CREATE OR REPLACE FUNCTION public.benchmark_set_rating_week(
    section_ids uuid[]
)
RETURNS TABLE (
    course_week integer,
    stream text,
    rating_mean numeric,
    rating_count bigint
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
        count(*)
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
