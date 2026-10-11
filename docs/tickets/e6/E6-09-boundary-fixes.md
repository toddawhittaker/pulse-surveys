# E6-09 — The boundary review's fixes

**ID:** E6-09
**Branch:** `e6/boundary-fixes`
**Depends on:** E6-07, E6-08
**Lane:** heavy
**Size:** M
**Security-relevant:** yes. It adds §4.1 invariant tests, changes the
exclusion log's and the review queue's scope, and changes two migrations'
downgrades.

## Context

The E6 boundary battery ran over the epic at c1b79714 (`boundary-review.md`).
Under the stopping rule declared before any finding arrived, every confirmed
HIGH and MED is fixed here, tests first. The keyboard focus HIGH on the
instructor's comment cards is E6-10's. Small LOWs are fixed here; the rest are
carried in `../e7/carried-from-e6.md` with an owner and a done-when.

## Owns

- `backend/migrations/versions/20261009_f14324ab936c_*.py` and
  `20261010_e403cc44bfc0_*.py` (downgrades and docstrings only).
- `backend/app/services/moderation.py`, `report_comments.py`, `reporting.py`,
  `authz.py`, `backend/app/schemas/report.py`, `backend/app/ai/gateway.py`
  (docstring), `mock-ai/app/rules.py` (comment).
- The OpenAPI document and `frontend/src/api/wire.gen.ts`, regenerated.
- `frontend/src/api/leadership.ts`, `frontend/src/components/ExclusionLogRow.tsx`
  and `frontend/src/copy/leadershipModerationCopy.ts`, for the undo marker and
  the confidentiality line only.
- Tests, including invariant-marked modules and `tests/evals/threat`,
  `tests/evals/summary` and `tests/evals/moderation/__init__.py`.
- `docs/SPEC.md` §5.2, §5.5 and §8; ADRs 0187, 0188 and 0190 and their index
  rows; `README.md`; `design/CLAUDE.md`; `design/SPEC_ADDITIONS.md`.

## Done when

1. **Downgrades refuse to lose data** (data-model, HIGH). `e403cc44bfc0`'s
   downgrade raises `RuntimeError` when any `moderation_state` row has a
   decider. `f14324ab936c`'s raises when `threat_case` or `moderation_state`
   holds a row. Each docstring says going down destroys that data. The
   precedent is `20260904_a7c2f4e18b30`. A data-bearing round-trip test on an
   `empty_database` proves each refusal, and an empty round trip still passes.
2. **The old-summary rule has a §4.1 test on the served report**
   (invariant-coverage, HIGH). Through the report route, a week holding a
   `summary.v1` row on a thin stream serves no summary for it, and a full
   stream's summary in the same week is served (the control).
3. **The log's excerpt rule has a §4.1 test for every case**
   (invariant-coverage, HIGH). In one marked test, a row from a held stream, a
   row from a week not yet fully moderated, and a row whose comment was shown
   only by a release batch each have `excerpt is None`, and their text appears
   nowhere in the body. A row from a shown week carries its excerpt (the
   control).
4. **A held week does not say "no comments"** (code-reviewer, MED). In
   `_payload`, a stream is suppressed when `stream_is_suppressed` says so or
   the section-week is not yet moderated. Test: a week above the threshold
   with one unverdicted comment serves `suppressed` true and no comments.
5. **An ended teaching grant still keeps the section out** (privacy-authz,
   MED). One authz helper returns the sections a person teaches or has taught
   (current grants plus `ended_teaching_grant`). The queue select, the leader
   door and the exclusion log all use it. A marked test ends a grant through
   the roster sync's own path, then reads the queue and the log: the section's
   items are absent, and a sibling section's are present. ADR 0190 lists the
   reverse case (a lead who later teaches the section) as an accepted residual.
6. **A lead who also chairs sees no sibling-led course** (invariant-coverage,
   MED). A marked test: a person leads course A and chairs the department
   holding course B, which another person leads. B's comment is absent from
   the queue and the log, and a decision on it gets 404 and writes no row. A's
   comment and an unled course's comment are present.
7. **The log shows undo as an undo** (spec-conformance, MED). `is_undo` is
   carried through `LoggedDecision`, the log payload and `ExclusionLogRow`,
   which renders an undo as a reversal. Tests for both sequences: exclude then
   undo; exclude an unflagged comment with a reason, keep it, then undo the
   keep.
8. **The log costs a fixed number of queries** (data-model, MED). The shown
   set is computed once for all the reader's decisions, with grouped queries,
   not once per section, week and stream. A test counts the statements one
   log read issues over at least two section-weeks and two sections, and the
   count does not grow with them.
9. **Marked where they belong** (invariant-coverage, MED and LOW). Mark
   `test_the_lead_review_queue_shows_what_ruling_one_allows.py` and
   `test_a_self_harm_comment_opens_a_threat_case_and_leaves_no_trace_in_the_report.py`
   `invariant`. Add `leaves_no_trace` to the denial-module guard's patterns.
10. **The student-path tripwire watches the moderation service**
    (invariant-coverage, MED). The import sweep in
    `test_the_report_comment_service_names_nothing_a_student_path_can_reach.py`
    covers `app.services.moderation`, with a planted import it must catch.
11. **The queue and log pages carry the confidentiality line**
    (invariant-coverage, MED). They show students' comment text to staff, as
    the instructor report does, so they carry item 5's line like it. The copy
    inventory's record is rewritten, and canary keys prove the collector reads
    `leadershipModerationCopy.ts`.
12. **The eval set covers the prompt's own rules** (prompt-eval, MED). Under
    `tests/evals/threat`: an injection-shaped threat, an injection-shaped
    self-harm disclosure, and a threat that is also abusive (expected
    `threat`). Under `tests/evals/moderation`: a comment that is both harmful
    and private (expected `harmful`), and clear near-misses such as "this exam
    killed me". No floor changes.
13. **The records say what the code does** (adr-docs-completeness and
    spec-conformance, MED and LOW). ADR 0187 gains a ruling-8 amendment and
    its E6-03 blockquote is repaired. ADR 0188's "No cap" rejection and its
    "withholds a comment for good" line are amended. Both index rows say a
    capped comment holds its whole week until a person decides it. SPEC §8's
    `moderation_attempt` sentence says only an unusable answer writes a row.
    SPEC §5.2 and §5.5 and ADR 0190 say the review queue does not wait for its
    week to be moderated (it carries no week, by ruling 1). The
    `moderation.py` module docstring stops saying a refusal counts. The repo
    `README.md` lists the two scheduled jobs and says comments appear after
    the sweep that follows a window's close.
14. **Small corrections.** `survey_windows.closed_by` replaces the two
    `closes_at <` copies (rename the shadowing parameter). `CommentFlag` becomes
    `HeldNoteType | None`. The sweep's error log line names the refusal's HTTP
    status. The small-N summary cases pin `summary.v3`, and the pin test
    checks `SMALL_N_SUMMARY_PROMPT_VERSION`. The stale comments the code
    reviewer and prompt-eval named are corrected. The participation note's
    lines in `design/CLAUDE.md` and `design/SPEC_ADDITIONS.md` are removed.

## MISTAKES entries to heed

3 (the canary in the same read), 22 (a new rule reaches an earlier ticket's
inventory), 35 and 53 (find rows the way the reader does), and 51 (a sequence
of reads).
