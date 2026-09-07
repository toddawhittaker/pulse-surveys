-- How many students gave each rating, per section, term week and stream —
-- ticket E4-03, SPEC §3.2, §5.1, §4.1, ADR 0041, ADR 0147.
--
-- §5.1 asks the instructor's Monday report for "this-week rating distributions
-- for both streams". This is that distribution and nothing else: one row per
-- (section, week, stream, rating value) carrying how many submitted ratings of
-- that value the week holds.
--
-- **Keyed by the week row, never by a course-week number.** A section's course
-- week 1 is some term week the cohort's start letter decides (§2.2), and
-- re-deriving that calendar here would be a second copy of an institution rule
-- that already lives in Python. So the key is the `week` row's id, and the
-- course-week label the report prints is applied at E4-07's payload layer.
-- ADR 0147 records the split.
--
-- **Only the weeks that were answered appear.** There is no outer join to the
-- calendar and no zero row: a week nobody answered is absent here, and giving
-- the chart back the gap it needs is E4-07's, in one place. A view that emitted
-- a zero row would make a stored zero and a missing week arrive looking the
-- same.
--
-- **The stream comes from the question, not from its ordinal.** `question_set`
-- is versioned (§3.2), so position 1 is the instructor rating in the set that
-- ships today and is not promised to be in the next one. `question.stream` is
-- the fact — E4-02 put it there for exactly this read — and a `CASE` over
-- `position` would answer a re-ordered set backwards while looking right.
--
-- **Two filters, and neither is the other's spare.** `kind` says what the
-- question asked; `rating IS NOT NULL` says the answer carries the value this
-- view reports. The schema does not make one imply the other: `answer`'s
-- constraint is `num_nonnulls(rating, comment_text, workload_hours) = 1`, which
-- refuses a row holding nothing and permits a row that fills `rating` under a
-- question of some other kind. E2-08's write path is what stops that, and a
-- read view is not the place to trust a write path.
--
-- **No column here names a person.** The rows are a section, a week, a stream,
-- a value and a count. `answer` reaches its author through its response, and
-- that column is not selected, not grouped on and not exposed — which is §4.1's
-- rule for every view an instructor reads.

CREATE VIEW public.report_rating_distribution AS
SELECT
    submitted.section_id AS section_id,
    submitted.week_id    AS week_id,
    asked.stream         AS stream,
    given.rating         AS rating,
    count(*)             AS responses
FROM public.answer AS given
JOIN public.question AS asked ON asked.id = given.question_id
JOIN public.response AS submitted ON submitted.id = given.response_id
WHERE asked.kind = 'likert'
  AND given.rating IS NOT NULL
GROUP BY submitted.section_id, submitted.week_id, asked.stream, given.rating;
