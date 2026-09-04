# E3-08 — E3 exit

**ID:** E3-08
**Branch:** `e3/e3-exit`
**Depends on:** all
**Lane:** heavy
**Security-relevant:** the ticket runs the epic-boundary reviews, which is
where the findings that every per-ticket review passed get found.

## Context

SPEC §14.3's E3 exit line: *the mock-LMS gradebook shows correct percentages
across enrollment edge cases.* This ticket drives that against the running
stack rather than asserting it, and then closes the epic: the boundary
reviews of §14.2 item 6, the deferred-file cleanup, and the hand-off note the
next epic's breakdown is written from.

E3 is not a ⚠ epic, so three boundary reviews run rather than four: the exit
review against the running system, the invariant-coverage audit, and the
docs/ADR completeness check. A whole-epic threat model is not mandated. That
is a fact about §14.2, not a judgement that this epic is uninteresting — a
grade posted to a real gradebook is the first thing Pulse writes to a system
of record, and the per-ticket security reviews carry that weight.

What the mock actually seeds, checked against `mock-lms/app/seed.py` rather
than remembered:

- `with_the_add_and_the_drop` seeds a member the platform **did** date
  (`opened_at` is set) together with a drop — so tier 1 and the drops rule
  both have a case.
- `without_an_enrollment_window` seeds a member with no platform dates at
  all, active from the start of the section. That is §3.4's undated tier and
  its accepted under-credit: a student the platform never dated cannot be
  told from a day-one student, so the formula counts them from the section's
  start date whether or not that is when they enrolled.
- A member first seen in a roster sync later than the section's first sync —
  tier 3 — is not seeded today and this ticket either seeds it or drives it
  by running a sync against a changed roster.

Read first: SPEC §14.2 item 6, §14.3's E3 entry, §3.4; ADR 0047 (the
posted-score readback is a mock-only route the backend never calls);
`carried-from-e2.md` whole, because this ticket writes its successor; the
seed functions named above.

## Scope

- The exit proof, end to end against the Compose stack on the development
  clock: the mock gradebook showing the right percentage for each enrollment
  case in the table below, read back through the conformant Result container
  and through `GET /mock/posted-scores` (`mock-lms/app/main.py:858`) **from
  the test only**, never from the backend — ADR 0047's rule.
- The three boundary reviews, their findings triaged, and the final batch
  built inside E3 rather than carried out of it (§14.1's rule: review debt
  ends with its epic).
- The `deferred.md` cleanup pass.
- `docs/tickets/e4/carried-from-e3.md`, complete under the same rule E2's
  successor used: every entry of `carried-from-e2.md` not closed inside E3,
  plus every entry of `deferred.md` still open after the cleanup, whoever
  owns it.
- The `PERSON_TABLES` standing question re-asked of everything E3 added.
- A re-affirmation that the session-read sweep still reaches the modules E3
  added, `backend/app/services/grading.py` above all.
- The TypeScript 7 watch: whether `typescript-eslint` admitted 7.x during E3,
  checked and dated rather than re-carried silently.

## Acceptance criteria

1. Each row of the exit table below is driven against the running stack and
   the gradebook shows the hand-computed percentage. Hand-computed means
   computed from §3.4 by a person, in the test's own comment, not read from
   the implementation — a test that holds its expectation in a copy of the
   thing it is checking is `docs/MISTAKES.md` entry 19.
2. The readback goes through the platform's Result container as well as
   through the mock-only route, and the two agree.
3. No backend code calls `/mock/posted-scores`, asserted rather than
   reviewed.
4. Three boundary reviews are run and their findings recorded with
   resolutions; anything not fixed inside E3 appears in
   `carried-from-e3.md` with an owner and a done-when.
5. `carried-from-e3.md` is complete against the rule stated above, and the
   completeness is demonstrated — each source entry named with what happened
   to it, not asserted in a summary sentence.
6. The `PERSON_TABLES` question is answered for `grade_sync`, `ags_call` and
   any column E3 added to an existing table, with the columns each judgement
   was made against.
7. The session-read sweep is shown to reach `services/grading.py` and the
   AGS client module, by planting a violation rather than by reading the
   sweep's inventory (`docs/MISTAKES.md` entry 9).

## The exit table

| Case | Expected |
|---|---|
| a day-one student who answered every item of every elapsed week | 100% |
| a day-one student who answered four items of five in one week | the hand-computed fraction, and a ledger line reading `4 of 5 items` for that week |
| a missed week | zero of that week's items, the week still in the denominator |
| a platform-dated late add (`with_the_add_and_the_drop`) | denominator starts at the platform's date |
| an undated member active from the start (`without_an_enrollment_window`) | denominator starts at the section's start date — §3.4's accepted under-credit, asserted as the intended behaviour and not as a defect |
| a late add first seen after the section's first roster sync | denominator starts at the week of that sync |
| the dropped member of `with_the_add_and_the_drop` | the score stops updating and the last posted value stands |

## What this ticket owes `carried-from-e3.md`

Named here so the exit cannot forget them.

- **No surface explains the item-based credit rule to anybody.** Ruled at
  breakdown, 2026-09-04, the participation score counts items rather than
  weeks, which means a blank optional comment costs real credit. §3.3's
  helper copy says written feedback counts toward full participation credit
  and no shipped string says what "counts" now costs. E3 ships no student
  surface and no instructor surface, so the AGS score comment's ledger is the
  entire disclosure, and ADR 0125 records that instructors read that ledger
  too. **Owner:** E8's student results view for the student half and E4's
  report surfaces for the instructor half, whichever ships first taking the
  copy question with it; §4.1 items 4 and 5 and the copy inventory govern
  whatever eventually says it. **Done when:** a student can read, on a Pulse
  surface, what a week's participation credit is made of and what leaving an
  optional comment blank costs.
- **Comment de-anonymization by completion pattern**, accepted in ADR 0125 on
  the ground that a weekly-updated score already carries the same signal.
  **Owner:** E4 and E6, the epics that render comments beside a roster, which
  read that record when deciding whether their own suppression rules are
  sufficient. **Done when:** each has stated in writing that its suppression
  holds against a reader who also has the gradebook open, or has changed what
  it suppresses. Nothing is owed inside E3; the entry exists so the accepted
  risk arrives with the surfaces that could realize it.
- **The rewound-clock family**, re-carried with whatever E3-06 and E3-07
  learned about the passback's own interaction with it.
- **Every open entry of `carried-from-e2.md`** that E3 did not close.

## Known traps

- **The gradebook is not the assertion.** An idempotent re-post and an absent
  post leave the same gradebook. Where a test means "posted once", it reads
  the call log; where it means "shows the right number", it reads the
  gradebook.
- **A boundary review's finding round has the defect density of the work it
  reviews.** The stopping rule is decided before the second round rather than
  during it, and "nothing found" is an allowed answer from a reviewer.
- **A review pass goes stale the moment a fix lands on top of it.** Run the
  pass over the fixes, or say plainly that it stopped and why.
- **An index written once and never re-read is the highest-risk record**
  (`docs/MISTAKES.md` entry 1). The E2 boundary review found this epic's
  predecessor index empty; fill the README's Merged column from the merge
  history as the epic goes, not from memory at the end.
- **`carried-from-e3.md` is written by reading `carried-from-e2.md` whole**,
  entry by entry, not by reading a summary of it. Amending a record is not
  reading it.

## Out of scope

- Building anything E4 through E13 owns. The exit ticket closes E3; it does
  not start the next epic, and `docs/tickets/e4/` gets exactly one file from
  this ticket.
