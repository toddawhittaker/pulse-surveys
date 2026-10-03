-- The per-stream rating figures of a start cohort, on §2.2's term axis —
-- ticket E5-03, SPEC §2.2, §5.1, §4.1 items 1 and 7, §8, ADR 0041, ADR 0165,
-- and the ruling on docs/disputes/E5-03-01.md, which settles this view's name
-- and its column list.
--
-- SPEC §2.2 gives two week axes. Course-level pages plot the course week, which
-- is benchmark_cohort_rating_week_v001.sql; aggregate pages plot "the term axis
-- (TERM 01-18) with one line per start cohort and a cohort selector". This is
-- that second axis, and it is the same figures under a different key: the term
-- week the response hangs on, and the start cohort as a line.
--
-- **A start cohort is identified by its start date, not by its start letter.**
-- The letter map is admin-configured per term (§2.2), so an administrator who
-- reuses a letter next term would have two unrelated cohorts drawn as one line;
-- a date is the same cohort in whatever term holds one. ADR 0165 records the
-- choice. `section_start_date` is therefore a key column here and there is no
-- letter anywhere in this file.
--
-- **Nothing in E5 draws these rows.** They are proven by test here so that E9,
-- which does draw them, consumes a read somebody has exercised rather than one
-- written under time pressure inside a ⚠ epic.
--
-- The stream rule, the two filters, the unit of `rating_count`, the absence of
-- any minimum and the absence of any person are all as the course-week rating
-- view records them; that file is the one to read for each.

CREATE VIEW public.benchmark_cohort_rating_term_axis AS
SELECT
    taught.length_weeks AS length_weeks,
    offered.level       AS level,
    taught.term_id      AS term_id,
    taught.start_date   AS section_start_date,
    counted.number      AS term_week,
    asked.stream        AS stream,
    avg(given.rating)   AS rating_mean,
    count(*)            AS rating_count
FROM public.answer AS given
JOIN public.question AS asked ON asked.id = given.question_id
JOIN public.response AS submitted ON submitted.id = given.response_id
JOIN public.section AS taught ON taught.id = submitted.section_id
JOIN public.course AS offered ON offered.id = taught.course_id
JOIN public.week AS counted ON counted.id = submitted.week_id
WHERE asked.kind = 'likert'
  AND given.rating IS NOT NULL
GROUP BY
    taught.length_weeks,
    offered.level,
    taught.term_id,
    taught.start_date,
    counted.number,
    asked.stream;
