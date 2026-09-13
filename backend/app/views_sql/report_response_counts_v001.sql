-- How many responses a section-week holds, and how many of them are valid —
-- ticket E4-03, SPEC §3.3, §5.1, §4.1, ADR 0041, ADR 0147.
--
-- §5.1 asks the report for a "response rate and validity rate"; §3.3 defines
-- the second as valid responses over responses. This view returns the two
-- numerators and neither quotient. **The divisions are E4-07's**, both of them:
-- the response rate's denominator is the enrolment that week, which is a §3.4
-- enrolment-window rule already written in Python, and a divide-by-zero rule
-- belongs in one reviewable place rather than in three views. ADR 0147 records
-- the split.
--
-- **`valid_responses` counts the column the validity service maintains.**
-- `response.is_valid` is written by `app/services/validity.py` from the current
-- verdicts of a response's comments, and §3.3's fail-open means a comment
-- accepted at submit time can be refused hours later — so this figure has to
-- follow the latest verdict rather than the first one. Reading `classification`
-- here would do the opposite: that table is append-only (ADR 0055), a verdict is
-- a new row, and an aggregate over it with no ordering reports whichever row it
-- meets first. The one place a current verdict is decided stays the one place.
--
-- **Only the weeks that hold responses appear**, keyed by the `week` row, for
-- the reasons written on `report_rating_distribution_v001.sql`: absence rather
-- than a zero row, and course-week labelling at the payload layer.
--
-- **No column here names a person**: a section, a week and two counts.

CREATE VIEW public.report_response_counts AS
SELECT
    submitted.section_id AS section_id,
    submitted.week_id    AS week_id,
    count(*)             AS responses,
    count(*) FILTER (WHERE submitted.is_valid) AS valid_responses
FROM public.response AS submitted
GROUP BY submitted.section_id, submitted.week_id;
