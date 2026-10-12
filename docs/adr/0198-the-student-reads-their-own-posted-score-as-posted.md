# 0198 — The student's own score is read through one shared helper

**Status:** Accepted
**Date:** 2026-10-11
**Ticket:** [E8-03](../tickets/e8/E8-03-participation-and-next-launch.md)

## Context

SPEC §3.3 and §5.4 (the owner's ruling 4 for E8) put the student's own posted
participation score and ledger on the results page in every state, shown as
posted and never recomputed. The SPEC does not say how "the score the student
last had" is found among `grade_sync` rows, which
[ADR 0124](0124-grade-sync-is-append-only-one-row-per-post.md) keeps one per
post, failed ones included.

## Decision

**One helper, `models.grades.latest_grade_sync(section_id, user_id, outcome=None)`**,
answers both readers of "the newest row": the weekly recompute's comparison
(any outcome) and the student's page (`outcome=POSTED`). The page shows the
`score_text` and `ledger_text` of the last post Pulse knows the platform took,
for the session's own user and the section already found among their live
enrollments, or null before any such row. `score_text` is Pulse's canonical
percentage before AGS scales it to the column's maximum, so the gradebook's
figure can differ from it in scale and value. The ordering is ADR 0124's.

## Alternatives rejected

- **A second query on the student path.** Two readers of "the newest row" would
  be two orderings to keep in step.
- **The newest row of any outcome on the page.** A failed post would show a
  score the platform never took.

## Consequences

- A change to what `grade_sync` stores, or to its ordering, reaches the page
  through the one helper.
