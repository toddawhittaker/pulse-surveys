-- The per-stream rating mean and its counts over a set of sections, each course
-- week counted only from what was fixed by that week's cutoff — ticket E5-14,
-- SPEC §4.1 item 7, §5.1, ADR 0165, ADR 0166, and the owner's "freeze at close"
-- ruling of 2026-09-22.
--
-- The same change benchmark_set_week_v003.sql makes, to the rating body: a
-- response counts toward course week w only if its own window closed at or
-- before the cutoff for w and it was last submitted at or before that cutoff.
-- That file carries the reasoning, the argument pairing, the null-cutoff
-- behaviour, the no-window rule, the owner's two new columns and the reason for
-- DROP and CREATE; none of it is restated here. v002's columns are answered
-- unchanged.

DROP FUNCTION IF EXISTS public.benchmark_set_rating_week(uuid[]);

CREATE FUNCTION public.benchmark_set_rating_week(
    section_ids uuid[],
    course_weeks integer[],
    closed_by timestamptz[]
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
        asked.week_asked,
        given_about.stream,
        avg(given_about.rating),
        count(*),
        count(DISTINCT placed.user_id),
        count(DISTINCT placed.section_id)
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
    JOIN (
        SELECT
            given.response_id AS response_id,
            given.rating      AS rating,
            asked_about.stream AS stream
        FROM public.answer AS given
        JOIN public.question AS asked_about ON asked_about.id = given.question_id
        WHERE asked_about.kind = 'likert'
          AND given.rating IS NOT NULL
    ) AS given_about ON given_about.response_id = placed.response_id
    GROUP BY asked.week_asked, given_about.stream
    ORDER BY 1, 2;
$$;

ALTER FUNCTION public.benchmark_set_rating_week(uuid[], integer[], timestamptz[])
    OWNER TO pulse_benchmark_definer;

REVOKE ALL ON FUNCTION public.benchmark_set_rating_week(uuid[], integer[], timestamptz[])
    FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.benchmark_set_rating_week(uuid[], integer[], timestamptz[])
    TO pulse_app;
