# 0198 — The student reads their own latest accepted score as posted, in every state

**Status:** Accepted
**Date:** 2026-10-11
**Ticket:** [E8-03](../tickets/e8/E8-03-participation-and-next-launch.md)

## Context

SPEC §3.3 promised that the results surface would explain a lowered
participation score: a comment counted at submission can be re-checked later
(classifier re-runs), so a week's count can go down after the student saw it.
[ADR 0125](0125-the-score-comments-per-week-ledger-is-instructor-visible.md) records the
ledger sent beside each score. [ADR 0124](0124-grade-sync-is-append-only-one-row-per-post.md)
keeps every post, failed ones included, as its own row. The owner's ruling 4 for
E8 puts the student's own score on the results page.

## Decision

`StudentWeekResults` gains `participation`: the `score_text` and `ledger_text`
of the newest `grade_sync` row for the session's own user and the section being
read whose outcome is `posted`, or null before any such row exists. The route
adds no parameter; the user comes from the session and the section is the one
already found among that user's live enrollments.

- **Shown as posted, not recomputed.** The strings are the characters sent to
  the platform, so the page and the gradebook cannot disagree about what was
  sent. A recomputed figure would be a second answer to a question the
  gradebook already answers.
- **The latest accepted row, not the latest row.** A `failed` row is an attempt
  and not a score; the student sees the last one the platform took. The lookup
  is `models.grades.latest_grade_sync`, which the weekly recompute's comparison
  now shares, with the ordering ADR 0124 fixes.
- **Shown under the hold.** It is the student's own record and not an aggregate
  of the week, so a held (`awaiting`) week does not hide it. The week's number,
  reply and author stay hidden as before.
- **Absent before the first post.** No zero and no placeholder (SPEC §3.4).
- One fixed sentence sits beside it: a comment counted at submission can be
  re-checked later, and a week's count can go down. It names no cause and no
  fault.

The schema member defaults to null so a payload built without it stays valid.

## Alternatives rejected

- **Recomputing the score for display** (can disagree with the gradebook; ruled out by §3.3).
- **The newest row of any outcome** (a failed post would show a score the platform never accepted).
- **Hiding it while the week is held** (it is the student's own record; the hold protects what others wrote).
- **A separate route** (a second request for a figure every page of this surface shows).

## Consequences

- The student's page can show a score that is newer or older than a re-check
  not yet posted; the sentence says counts can change.
- A future change to what `grade_sync` stores reaches this page directly.
