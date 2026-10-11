# E7-04 — The AI draft and the draft check

**ID:** E7-04
**Branch:** `e7/ai-draft-and-check`
**Depends on:** none
**Lane:** heavy
**Why this lane:** its refusal of a draft that reuses the words of a comment
students will not see enforces SPEC §4.1 item 3, and that test is marked
`invariant`, as the summary's equivalent is
(`tests/integration/test_a_small_n_summary_never_reuses_a_commenters_words.py`).
**Size:** M
**Security-relevant:** a model writes text that a person may publish to every
student in the section. A defect here puts a held or excluded comment's words in
front of students, or tells an instructor a theme count the stored summary does
not hold.

## Context

SPEC §5.3 gives two advisory modes. The **draft** writes a response "from the
week's actual themes and ratings", editable, never auto-posted. The **draft
check** names the week's themes the draft has not addressed, each with its
comment count; it is re-runnable and clears when the draft changes (the
clearing is the page's, in 05). SPEC §7.4 makes each one call in, one validated
object out. `ResponseDraftOutput` and `DraftCheckOutput` already exist in
`backend/app/ai/contracts.py`; nothing calls them yet.

**The gather sends no comment.** Both tasks are fed the section-week's stored
summaries and their stored themes, and the rating distributions and response
counts. Never raw comments. `_stored_summaries` returns no themes, so this
ticket adds a themes read that applies the same filter: an old-format
(`summary.v1`) row of a held stream gives no themes, as it gives no summary.

**No per-theme count below the threshold (decision 12).** For a stream held
below the threshold, no per-theme count field reaches either task's prompt or
the check's payload. The check names such a theme without a count. A summary's
prose is not a count field and can still carry a number, so in a week with a
held stream a draft carrying any number except one naming a course structure
("week 3") is refused (residue A of the breakdown review, tightened in the fix
round; ADR 0195). A count of comments in a small
week is the count §5.2 rules out as a participation trace. A shown stream's
themes keep their stored counts. That is what keeps the
no-quoting rule (§5.1) and the threshold (§4) intact for a draft students will
read. Because no comment is rendered into these prompts, the carried entry on
forged summary block boundaries does not trigger here; ADR 0195 says so.

**Two structural refusals**, checked in code after the model answers, in the
pattern of `summarize_stream` (refuse an overclaimed count; never log comment
or draft text):

- **The check names only stored themes.** Every theme in `DraftCheckOutput` must
  be one of the section-week's stored themes, with its stored count for a
  shown stream and with no count for a held one. Anything else is refused as
  an invalid answer.
- **The draft reuses no word run from a comment students will not see.** Those
  are the section-week's comments that `report_comment` v004 returns and that
  are excluded, still flagged, or in a stream held below the threshold. The
  check is `_reused_run` against those comments, as
  `refuse_a_summary_reusing_a_comment` does for a summary. The comments are
  read for this comparison only and never returned, logged or sent.

**The instructor's routes.** Draft and check, for one of their own sections and
a published week, behind `csrf_verified_instructor`. 03 adds the lead's
on-behalf routes over the same tasks and gather.

ADR 0195 states that the instructor's gather keeps a summary written before an
exclusion (the instructor already reads that summary and is the author of what
is published; the run refusal blocks quoting), while the on-behalf gather (03)
leaves it out.

Read first: SPEC §4, §4.1, §5.1, §5.3 and §7.4; ADRs 0148 and 0187; the summary
task in `backend/app/ai/tasks.py` and its refusals in `services/reporting.py`;
`tests/evals/moderation/` for typed cases that ship without a floor.

## Owns

- `backend/app/ai/prompts/response_draft.v1.md` and
  `backend/app/ai/prompts/draft_check.v1.md`.
- `backend/app/ai/tasks.py`: the two task functions, through
  `AIGateway.run_task` and `load_prompt`.
- `backend/app/ai/contracts.py`: `CommentTheme.comment_count` is required today,
  so the check's output gains a way to name a held stream's theme with no
  count (decision 12). The weekly summary's contract keeps its required count.
- `backend/app/services/reporting.py`: the gather and the two refusals.
- `backend/app/api/instructor.py` and `backend/app/schemas/report.py`: the two
  routes and their payloads.
- `mock-ai/app/rules.py`: deterministic answers for both tasks, including one
  that reuses a planted comment's words and one that names a theme not stored,
  so the refusals can be driven end to end.
- `tests/evals/response_draft/` and `tests/evals/draft_check/` (new): typed
  cases, no `floors.py`, and no registry slot that a floor would gate.
- `frontend/src/api/openapi.json` and `wire.gen.ts`, regenerated.
- ADR **0195**.

## Reuse, do not rewrite

`AIGateway.run_task`; `load_prompt`; `summarize_stream`'s refusal shape;
`_stored_summaries`, `_rating_counts`, `_response_counts`, `_readable_section`,
`_reused_run` and `refuse_a_summary_reusing_a_comment` in
`services/reporting.py`; `n_threshold`, `stream_is_suppressed` and
`section_week_moderated` in `services/report_comments.py` (comment text only
through `report_comment` v004).

## Done when

1. **The gather sends no comment.** A test plants a distinctive comment in the
   section-week and asserts it appears in neither task's rendered prompt, for a
   shown stream and a held one.
2. **Draft-check themes equal stored ones.** A check answer naming a theme the
   stored summary does not hold, or a shown stream's stored theme with a
   different count, is refused; an answer naming stored themes with their stored counts is
   accepted. An empty list is accepted.
3. **No per-theme count below the threshold.** For a stream held below the
   threshold, no per-theme count field reaches the prompt or the check
   payload. The check names the theme without a count. A summary's prose is
   not a count field and may still state a number, so in a week with a held
   stream a draft carrying any count token (digits, cardinal words, or a
   quantity word such as "both", "half" or "a few"), except one straight after
   a course-structure word such as "week" or "chapter", is refused as an
   invalid answer; the same draft in a week where every stream is shown is
   accepted (residue A of the breakdown review, tightened by the fix round's
   G1). Themes are read through the
   same filter as `_stored_summaries`: an old-format (`summary.v1`) row of a
   held stream gives no themes. Each case is tested beside a shown stream that
   does carry its counts. Marked `invariant`.
4. **A draft that quotes a hidden comment is refused.** A draft reusing a word
   run from an excluded comment, from a still-flagged comment, and from a
   comment in a held stream is each refused, beside a draft reusing a run from
   a published comment in a shown stream, which is accepted. Marked
   `invariant`.
5. **Nothing is logged, and the refusal names nothing.** Neither task logs a
   comment, a summary or the draft text, on success or on refusal. The
   refusal of a draft is byte-identical whichever hidden comment matched, and
   contains no word of the comment or the draft; this is tested with a planted
   distinctive run.
6. **Only the instructor's own section.** Draft and check refuse a section the
   instructor does not teach and a week not yet published, with one refusal
   that names nothing of the section, and run no model call. The gate runs at
   dispatch: no CSRF token is refused over HTTP beside the same request with it.
7. **Mock answers exist.** `mock-ai` answers both tasks, so 05's page and 09's
   drive run without a provider.
8. **Typed eval cases.** Each task has typed cases for the behaviours above, and
   ships no floor.
9. **The records match.** ADR 0195 records the gather, the two refusals, the
   count rule below the threshold, the instructor's summary rule beside 03's, why no floor, and why the forged
   block boundaries entry does not trigger.

## Shares files with

- `api/instructor.py`, `services/reporting.py`: 03 after this merges.
- `openapi.json`, `wire.gen.ts`, `docs/adr/README.md`: 01 and 08 in parallel.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 19, 23, 30, 35 and 50.

## Known traps

- **Entry 30.** The refusal tests must plant the comment and the draft
  separately; a draft built from the fixture's own comment string proves
  nothing about the gather.
- **Entry 50.** A theme's count is a count of comments, not of people. It is
  never a threshold and never feeds one.

## Not in this ticket

- The lead's on-behalf routes (03).
- The composer page and the clearing of a check on edit (05).
- Eval floors for either task.
