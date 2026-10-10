# E6-08 — The exclusion log leaves out taught sections, and no HTTP status caps a comment

**ID:** E6-08
**Branch:** `e6/review-residue`
**Depends on:** E6-05
**Lane:** heavy
**Size:** S
**Security-relevant:** yes. One fix closes a privacy channel. The other closes a
fail-open on the safety classification.

## Context

The re-check of PR #296 (E6-05) at 2e3fedc3 found two MEDs. The review loop
stopped there, as the review tiers set, and this ticket fixes both, tests first.

1. **The log still shows rows from sections the reader teaches.** Ruling 7
   leaves a reader's own taught sections out of the review queue and the leader
   door. The exclusion log still lists decision rows from those sections. A row
   shows the section, the date, the decider's role, the flag and the reason,
   though no excerpt. So a chair who teaches section A learns that A held a
   flagged comment, roughly when, and a paraphrase of it from another reviewer's
   reason. Their own instructor report shows nothing of it (ruling 6). This
   happens with two chairs in one department, or when a course's lead mapping
   changes. Fix: `exclusion_log` drops every row whose section is in
   `authz.taught_section_ids(person_id)`, the same filter `_queue_select` uses.
   The row is removed, not redacted.
2. **An HTTP status can still cap every comment.** E6-05 counts only 413 and
   422 toward the six-attempt moderation cap. Either can come back on every
   request: a self-hosted FastAPI endpoint answers 422 to a parameter it
   rejects, and a proxy with a low body limit answers 413 to most prompts. Every
   comment would then be capped within six hourly sweeps, and its week released
   with no threat or self-harm check. Fix: no HTTP status counts toward the cap.
   Only an answer that came back and was unusable (`AIResponseInvalidError`)
   counts. A refused comment stays held, and its week waits, until E10's Care
   review. Ruling 5 keeps real students away until then.

## Owns

- `backend/app/services/moderation.py` (`exclusion_log`,
  `_counts_toward_the_cap` and its status set).
- `backend/app/ai/gateway.py` (docstrings only, if they name the counting
  statuses).
- The tests for both, from the test author.
- ADR 0190 (one line: the log leaves out taught sections) and ADR 0188 (an
  amendment line: no HTTP status counts). SPEC §5.5 if its exception sentence
  names the log's scope.
- `docs/tickets/e6/E6-07-e6-exit.md`'s E10 carry: a refused comment holds its
  week until Care review.

## Done when

1. A chair who teaches section A of an unled course reads the log. A decision
   row from A is absent. A row from another section of the same course is
   present in the same read (the canary). The same holds for a lead.
2. A provider that answers 413, and one that answers 422, seven sweeps in a row,
   writes no attempt row and strands nothing. After recovery, every comment gets
   its verdict.
3. An unusable answer still counts toward the cap, and six of them cap the
   comment (the existing test stays green).
4. A comment at the cap never releases its week (ruling 8). The whole
   section-week stays out of the comment read, every release batch and the
   summary walk. Pinned by
   `test_a_capped_comment_holds_its_whole_week_from_the_comment_read`,
   `test_a_capped_comment_holds_its_week_out_of_every_release_batch` and
   `test_a_refused_comment_holds_its_weeks_summary_below_the_cap_and_at_it` in
   `test_the_moderation_sweep_moderates_closed_windows.py`, and
   `test_a_week_whose_only_comment_is_capped_gets_no_summary_while_a_no_comment_week_does`
   in `test_the_hourly_summary_walk_and_what_a_stored_summary_shows.py`.

## MISTAKES entries to heed

3 (the canary in the same read), 35 and 53 (find rows the way the reader does),
and 22 (a new rule reaches an earlier ticket's inventory).
