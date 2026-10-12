# 0206 — The drill-down reuses the report read-only, the wider roles read the log and policy, and a summary records the decisions it saw

**Status:** Accepted, amending [0190](0190-a-lead-reviews-flagged-text-at-any-threshold-and-the-log-withholds-held-text.md) and [0194](0194-the-response-loops-doors-decide-every-refusal-from-the-readers-own-grant-first.md)
**Date:** 2026-10-12
**Ticket:** [E9-09](../tickets/e9/E9-09-drill-down-and-the-wider-roles.md)

## Context

SPEC §5.5 renders the Instructor Monday Report wholesale and read-only for a
leader who drills down to a section, and §5.1 seals its benchmark lines against
that reader. The spec does not say how the report is reached for a leader, what
"read-only" removes from its payload, what the assistant dean, the dean and the
vice president read of the exclusion log and the response policy, or how the
up-chain summary filter (ADR 0195) closes the race in which an exclusion begun
before the summary walk commits after it.

## Decision

**The drill-down is `reporting.leadership_report` beside the instructor's
door, building the same `_payload`.** The section is looked up in the reader's
`ActorScope` purview, from `deps.leadership_scope` only (ADR 0199); outside it
and not existing are one 404 with the report's own sentence, and a week with no
published report is the report's other 404. `_payload` takes the reader as
`leader`, which changes four things: no comment is `decided_by_you`, the stored
summaries pass the removal filter every up-chain reader uses, the seal is handed
the reader's scope (ADR 0203), and the Lead Faculty name is asked with the
reader's scope, so it is read only for a section inside her purview. The hold,
the release batches and §5.2's flag hiding are the instructor's, untouched. The
payload is `InstructorReport` unchanged: it has no composer, and the route is a
`GET`.

**SPEC §4.1 item 5.** The drill-down is the report's surface, so it carries the
report's confidentiality line once, and the page's context-bar words go under
`leadership_rollup.`. The `leadership_response` surface still shows summaries,
counts and ratings only, so it still owes no line.

**The three wider roles read the log and the policy over their purview.**
`moderation.purview_read` is the union of the reader's `ASSISTANT_DEAN`, `DEAN`
and `VP_ACADEMICS` grants, read off the scope; nothing new in `authz.py`. The
log reads the lead's or chair's courses (`lead_review_courses`, as before) and
those sections together, less every section the reader teaches or has taught.
The policy lists every course of the purview, which these roles read and do not set.
The queue keeps its 403 and the on-behalf doors their single 404, each with the
sentence it had: these roles review nothing (SPEC §5.2, §5.3).

**The summary filter compares decision sequences.** The walk reads the highest
`moderation_state.sequence` of the section-week **before** it gathers the
comments, and stores it as `weekly_summary.moderation_sequence_seen` (0 when it
saw none; migration `e9d4a6c8e504`). A row is served when that number is at
least the latest removal's sequence. A row written before the column existed is
null and is judged by `generated_at` as before, so nothing anybody can read
today changes; no backfill guesses what an old walk saw.

## Alternatives rejected

- **A second payload for leaders.** Two answers to what a report says; a
  suppression rule then holds on one and not the other.
- **A new purview helper in `authz.py`.** The grants and their purviews are
  already on the scope `leadership_scope` resolved.
- **Giving the wider roles the queue, or a chair the whole department's log.**
  §5.2 names the lead and, for an unled course, the chair as reviewers.
- **A 403 on the on-behalf doors for these roles.** ADR 0194's one 404 says
  nothing about why a door is shut, and a role-specific status would.
- **Recording the sequence after the gather.** A decision committed between the
  two reads would count as seen though the gather missed it.

## Consequences

- **Residual, accepted:** `sequence` orders inserts, not commits. A removal that
  inserted before another decision in the same section-week, and committed
  after both that decision and the walk's read, sits below the recorded number
  though the walk did not see it. It needs two decisions racing in one
  section-week while its summary is written; holding the walk's read against
  in-flight decisions would make a decision wait on a model call.
- Every reader of a stored summary other than the instructor's own report goes
  through `_summary_rows_since_latest_removal`.
