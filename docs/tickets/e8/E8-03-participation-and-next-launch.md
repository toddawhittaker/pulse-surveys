# E8-03 — Participation and next launch

**ID:** E8-03
**Branch:** `e8/participation-and-next-launch`
**Depends on:** none
**Lane:** light
**Why this lane:** a student's read of their own grade record, through the
results route's existing enrollment check, and a landing card. `grade_sync`
is not an identity, org, audit or Care table, and no invariant test changes.
**Size:** S
**Security-relevant:** a student's own score. A defect here shows one
student another student's score or ledger.

## Context

Two rulings.

- **Ruling 4: the student's own posted score.** SPEC §3.3 promised that the
  results surface would explain a lowered participation score. The results
  payload gains a `participation` member: the student's latest `grade_sync`
  row for the section that the platform accepted (outcome `posted`), with its
  `score_text` and `ledger_text` exactly as sent. The page shows them with one
  fixed sentence: a comment counted at submission can be re-checked later, and
  a week's count can go down. It shows in every state, `awaiting` included,
  because it is the student's own record and not an aggregate. Before any
  score has been posted, the member is absent and the page shows nothing for
  it; no zero and no placeholder (§3.4: absence is the truth before the first
  post).
- **Ruling 3: next launch.** When no survey is open for a section, the
  student's landing card for it leads with "Week N results are in" and the
  link to that week's page, reading the existing latest-results call. With a
  survey open, the card leads with the survey as it does today. A section with
  no published week shows no results lead. There is no stored record of what
  the student has seen.

Read first: SPEC §3.3, §3.4 and §5.4; ADRs 0124, 0125 and 0193;
`services/grading.py` (the latest-row lookup ADR 0124 describes);
`routes/student/StudentWeeklySurvey.tsx`.

## Owns

- `backend/app/services/response_loop.py`: the participation read, keyed by
  the session's own user and the section already found among the student's
  live enrollments.
- `backend/app/schemas/response_loop.py`: the `participation` member and its
  model, with `extra="forbid"`.
- `frontend/src/api/openapi.json` and `wire.gen.ts`, regenerated.
- `frontend/src/routes/student/StudentResults.tsx` and its test: the
  participation block.
- `frontend/src/routes/student/StudentWeeklySurvey.tsx` and its test: the
  results lead on the section card.
- `frontend/src/api/student.ts` and `frontend/src/copy/studentResults.ts`: the
  call and the words.
- ADR **0198** (the score is shown as posted, not recomputed; why the latest
  accepted row; why it shows under the hold).

## Reuse, do not rewrite

`grading.py`'s latest-row lookup for a section and user, if it fits, never a
copy; `student_week_results`' enrollment check; the existing
`readStudentResults` call in `frontend/src/api/student.ts`, called from the
landing rather than copied.

## Done when

1. **The student reads their own score as posted.** With two `posted` rows and
   a later `failed` row for the student, the payload carries the later
   `posted` row's `score_text` and `ledger_text` character for character.
2. **Only the student's own.** With a classmate's later `posted` row in the
   same section, and the student's own row in another section, the payload
   carries only the student's row for this section. A test reaches the read
   through the connection production uses (MISTAKES entry 46).
3. **Absent before the first post.** With no `posted` row, the member is
   absent and the page shows no score, no zero and no placeholder.
4. **Shown in every state,** `awaiting` included, with the fixed sentence
   beside it, from a mocked route.
5. **The landing leads with the newest results.** With no survey open and a
   published week, the section card leads with "Week N results are in" and a
   link to that week. With a survey open, it leads with the survey. With no
   published week, it shows no results lead. When the newest week is
   `awaiting` (required and unanswered), the card shows no results lead either:
   "results are in" over a closed door is the teased data SPEC §5.4 rules out.
   A test pins each of the four cases.
6. **Words and basics.** Every new string is in the copy inventory and passes
   the student-copy rules; the sentence uses no shame language. Keyboard and
   screen reader basics hold.
7. **The records match.** ADR 0198 is written and indexed. ADR 0125, whose
   context says no student-facing view of the score exists, gains a line
   pointing at ADR 0198. Comments that name an E-ticket in the files this
   ticket edits are rewritten.

## Shares files with

- `services/response_loop.py`, `schemas/response_loop.py`, `openapi.json`,
  `wire.gen.ts`: 01, in the same wave.
- `StudentResults.tsx`, its test, `frontend/src/api/student.ts`,
  `frontend/src/copy/studentResults.ts`: 02 after.
- `docs/adr/README.md`: 01 and 04.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 46 and 49.

## Known traps

- **Entry 46.** A test that drives the read through the migrating engine has
  not tested the grant.
- **A failed post is not a score.** The latest row may be a `failed` one; the
  student sees the last score the platform accepted.

## Not in this ticket

- Recomputing the score or announcing a change to it (§3.3).
- A "new since you last looked" marker, or a launch that lands on the results
  page (ruling 3).
- The rest of the results page (02).
