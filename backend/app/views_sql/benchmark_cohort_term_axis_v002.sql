-- The term-axis cohort row, with **the hours' own counts** beside the week's —
-- ticket E5-04's fix round, SPEC §4.1 items 1 and 7, §5.1, §2.2, ADR 0041,
-- ADR 0165, ADR 0166, and the ruling appended to docs/disputes/E5-04-01.md.
--
-- v001 is unchanged in every respect but one: this body answers two more
-- columns. Everything that file records — the cohort key, why the axis is keyed
-- by section_start_date rather than by the start letter, why the row is built
-- over the responses with the hours hanging off it on the left, why the absent
-- figures are null rather than nought, why the median is cast back to numeric,
-- and that no minimum is applied here — still holds and is not restated.
--
-- **What changed, and why it is a confidentiality fix rather than a feature.**
-- A security review of E5-04 found the same defect in three places, and this
-- view is the third. workload_mean and workload_median are computed over the
-- responses that carry hours; response_count, respondent_count and
-- section_count count everybody who answered anything. ADR 0165 keeps the row
-- when nobody reported hours at all, so the two populations diverge whenever a
-- responder leaves the question blank — and they diverge in the disclosing
-- direction, because a figure's own contributors are never more numerous than
-- the week's. Two students' hours could be shown as a figure over fifteen
-- people. SPEC §4.1 item 7 suppresses a figure below the minimum and the
-- minimum is about the population *that figure* is computed from, which is
-- docs/MISTAKES.md entry 50's class.
--
-- So workload_respondent_count counts the distinct **people** whose hours the
-- two statistics average, and workload_section_count counts the distinct
-- **sections** those hours came from. Both currencies, because a guard is named
-- in every currency the thing it guards is held in: a fix correcting only the
-- people would still show one section's hours as a figure over five sections.
-- The same FILTER shape the two set functions' _v002 bodies use, over the same
-- LEFT JOIN, so the three reads agree by construction rather than by intention.
--
-- **The week's three counts stay.** They are what the cohort week *was*, which
-- is a true and useful number, and removing them would make this a different
-- view rather than a corrected one. The caller picks the pair belonging to the
-- figure it is sealing, and app.services.benchmarks does that in one place.
--
-- **This widens what pulse_app may read, and the widening is admitted rather
-- than made quietly.** The whole-relation grant in benchmark_read_grants_v001
-- carries the two new columns the moment they exist, so the sanctioned read
-- surface grows by two. That is exactly what SPEC §4.1 item 1's equalities
-- exist to make visible: BENCHMARK_VIEWS in tests/fixtures/benchmark_views.py
-- and SANCTIONED_VIEW_COLUMNS in tests/integration/test_identity_grants.py each
-- admit the pair with the sentence that says why, in the same change. Neither
-- column is a key, neither names a person, and both are aggregate counts of the
-- class this view already exposes.
--
-- **CREATE OR REPLACE rather than DROP, and it is measured rather than
-- assumed.** Postgres permits a replacement that *appends* columns to a view
-- and refuses one that removes or reorders them, so the two counts go last and
-- the ten columns above them keep their positions. Verified against the
-- migrated database, including that the relation-wide GRANT survives the
-- replacement — which is why this file issues none. The revision's downgrade is
-- the case that cannot be a replacement: going back to v001 *removes* two
-- columns, so it drops the view and re-grants what the drop took with it.

CREATE OR REPLACE VIEW public.benchmark_cohort_term_axis AS
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
    count(DISTINCT taught.id)         AS section_count,
    count(DISTINCT submitted.user_id) FILTER (WHERE hours.workload_hours IS NOT NULL)
                        AS workload_respondent_count,
    count(DISTINCT taught.id) FILTER (WHERE hours.workload_hours IS NOT NULL)
                        AS workload_section_count
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
