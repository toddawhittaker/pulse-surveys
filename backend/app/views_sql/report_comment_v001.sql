-- The comments an instructor's report is built from, de-identified and undated —
-- ticket E4-04, SPEC §4, §4.1 items 3 and 6, §5.1, §5.2, ADR 0041, ADR 0147.
--
-- §5.1 asks the instructor's Monday report for "de-identified comments grouped
-- under 'About the instructor' / 'About the course'". This is the row set those
-- groups are drawn from: one row per comment answer that carries text, saying
-- which section and which week it belongs to, which of §5.1's two groups it is
-- in, which answer it is, and what it says.
--
-- **Five columns, and the four that are absent are the guarantee.** There is no
-- `user_id`, no `response_id`, and no instant of any spelling. SPEC §4 keys
-- responses to the LMS user id and never displays identity to an instructor;
-- one line further on it says "timestamps are never shown with comments", and
-- held comments surface "batched so that timing cannot identify an author". A
-- `submitted_at` here would not merely be renderable — it would be the obvious
-- order key, which is the shape E4-04's known traps name: wherever ordering
-- happens, the timestamp must not be the order key in disguise. The order is
-- randomized in `app/services/report_comments.py` and this view has no `ORDER
-- BY` at all.
--
-- **`answer_id` is here on purpose.** A release is a `release_batch_member` row
-- keyed on `answer_id` (ADR 0146), so the weekly cutter has to be able to name
-- the comment it released and the release read has to be able to find it again.
-- It names an `answer` row; a person is two further hops away, through
-- `answer.response_id` and then `response.user_id`, and neither of those columns
-- is selected here.
--
-- **This view suppresses nothing, and that is deliberate.** SPEC §4's small-N
-- rule is a comparison against a count of *responses*, which is a fact about the
-- week rather than about any comment in it, and §5.2's concealment depends on
-- the moderation record, which is append-only and whose latest row governs (ADR
-- 0145). Both are applied above this view, in one reviewable module. A view that
-- tried to hold the threshold would need the response count joined into every
-- row and would still leave the moderation resolution somewhere else — two
-- places deciding one rule. `report_response_counts_v001.sql` states the same
-- stance for the same reason.
--
-- **Keyed by the `week` row, never by a course-week number**, as E4-03's three
-- views are: a section's course week 1 is some term week the cohort's start
-- letter decides (§2.2), and re-deriving that calendar here would be a second
-- copy of an institution rule that already lives in Python. ADR 0147 records the
-- split.
--
-- **The stream comes from the question, not from its ordinal.** `question_set`
-- is versioned (§3.2), so position 2 is the instructor-stream comment in the set
-- that ships today and is not promised to be in the next one. `question.stream`
-- is the fact — E4-02 put it there for exactly this read.
--
-- **Three filters, and none of them is another's spare.** `kind` says what the
-- question asked; `comment_text IS NOT NULL` says the answer carries the value
-- this view reports; the trimmed comparison says it carries something a person
-- wrote. `answer`'s own constraint is `num_nonnulls(rating, comment_text,
-- workload_hours) = 1`, which refuses a row holding nothing and permits a row
-- filling `comment_text` under a question of some other kind — E2-08's write
-- path is what stops that, and a read view is not the place to trust a write
-- path. Without the text filters the read path above would render a blank
-- comment card per rating per response, and an empty string would count toward
-- the cumulative volume that releases a term's held comments.

CREATE VIEW public.report_comment AS
SELECT
    submitted.section_id AS section_id,
    submitted.week_id    AS week_id,
    asked.stream         AS stream,
    written.id           AS answer_id,
    written.comment_text AS comment_text
FROM public.answer AS written
JOIN public.question AS asked ON asked.id = written.question_id
JOIN public.response AS submitted ON submitted.id = written.response_id
WHERE asked.kind = 'comment'
  AND written.comment_text IS NOT NULL
  AND btrim(written.comment_text) <> '';
