-- The per-stream rating figures of a cohort, aligned by course week — ticket
-- E5-03, SPEC §2.2, §5.1, §4.1 items 1 and 7, §8, ADR 0041, ADR 0165, and the
-- ruling on docs/disputes/E5-03-01.md, which settles this view's name and its
-- column list.
--
-- A **cohort** is SPEC §5.1's comparison set expressed as a key: a length, a
-- level, a term and a week. §5.1 requires a match on both length and level —
-- "an 8-week graduate course is never averaged against a 12-week undergraduate
-- one" — and no level is folded into another, so both are key columns and
-- neither is filtered to a list somebody wrote down. A level band nobody
-- thought about gets its own rows rather than being dropped.
--
-- **The week is the course week, never the term week.** §2.2: "averaging
-- week-3-of-course across cohorts that began five weeks apart would be
-- meaningless." The course week is derived per section, as the term week the
-- response hangs on less the whole weeks between the section's own start date
-- and its term's — so a section that began in the term's fourth week has its
-- second course week aligned with the second course week of a section that
-- began in the first. The term axis, which is the other half of §2.2's
-- sentence, is the sibling file benchmark_cohort_rating_term_axis_v001.sql.
--
-- **The term is a key column rather than a filter**, which is what makes §5.1's
-- past-referencing possible: a prior term's cohort is a second row at the same
-- length, level and course week, and E5-04 unions the rows and applies the
-- policy. Nothing here reads a clock, so no answer depends on the day the query
-- runs (ADR 0142).
--
-- **The stream comes from the question, not from its ordinal**, copied from
-- report_rating_distribution_v001.sql and for that file's reason: the question
-- set is versioned (§3.2), so position 1 is the instructor rating in the set
-- that ships today and is not promised to be in the next one. E4-02 put
-- question.stream there for exactly this read.
--
-- **Two filters, and neither is the other's spare** — again as that file
-- records: `kind` says what the question asked, and `rating IS NOT NULL` says
-- the answer carries the value this view reports.
--
-- **`rating_count` counts ratings, and that is its unit.** The figure a minimum
-- is compared against is a count of *people*, and it lives on the
-- workload-and-counts view beside the section count
-- (benchmark_cohort_week_v001.sql). Two numbers called "count" on two views of
-- one ticket is how docs/MISTAKES.md entry 50 starts, so each says its unit out
-- loud.
--
-- **No minimum is applied here and none ever should be** (criterion 7): a
-- one-section cohort has a row. The suppression decision is E5-04's, in one
-- place, and a view that pre-suppressed would leave the service unable to tell
-- a cohort that is too thin from a cohort that has no data.
--
-- **No column here names a person.** A length, a level, a term, a course week,
-- a stream, a mean and a count. The response's author is reached only to be
-- grouped away, and the ruling on docs/disputes/E5-03-01.md withdrew the
-- person-keyed view this ticket's work order asked for: figures over an
-- arbitrary section set are answered by the two SECURITY DEFINER functions
-- instead.

CREATE VIEW public.benchmark_cohort_rating_week AS
SELECT
    taught.length_weeks AS length_weeks,
    offered.level       AS level,
    taught.term_id      AS term_id,
    counted.number
        - floor((taught.start_date - scheduled.start_date)::numeric / 7)::integer
                        AS course_week,
    asked.stream        AS stream,
    avg(given.rating)   AS rating_mean,
    count(*)            AS rating_count
FROM public.answer AS given
JOIN public.question AS asked ON asked.id = given.question_id
JOIN public.response AS submitted ON submitted.id = given.response_id
JOIN public.section AS taught ON taught.id = submitted.section_id
JOIN public.course AS offered ON offered.id = taught.course_id
JOIN public.term AS scheduled ON scheduled.id = taught.term_id
JOIN public.week AS counted ON counted.id = submitted.week_id
WHERE asked.kind = 'likert'
  AND given.rating IS NOT NULL
GROUP BY
    taught.length_weeks,
    offered.level,
    taught.term_id,
    counted.number - floor((taught.start_date - scheduled.start_date)::numeric / 7)::integer,
    asked.stream;
