# E8-04 — E8 exit

**ID:** E8-04
**Branch:** `e8/e8-exit`
**Depends on:** all
**Lane:** light
**Why this lane:** drives, a seeder and records. It adds no behaviour.
**Size:** M
**Security-relevant:** the exit drive proves a held week shows a student
nothing and a released week shows only what §4 and §5.2 permit; the boundary
reviews run here.

## Context

SPEC §14.3's E8 exit: "the full weekly loop demos end-to-end from one
student's seat." This ticket drives it on a fresh stack:

- **The survey.** The student answers the week's survey. The window closes,
  moderation runs, and the report opens.
- **Held.** The section is in required mode. On the next launch the landing
  leads with "Week N results are in". The page names the course, shows the
  closed door and the student's own posted score, and nothing about the week.
- **Released.** The instructor publishes. The student reads the response
  first, then the trend, the distributions, the workload median, the
  published comments, a small stream's notice, and the confidentiality line.

It also drives the two response paths no drive reaches (carried from E7): one
drive publishes on behalf of a course, and one reads an unanswered week past
the deadline as the lead. Each runs on a fresh stack and leaves no rows a
rerun trips over.

The world is seeded by a new seeder beside
`scripts/seed_response_loop_exit_story.py`. Every date is derived from the
seeded calendar relative to the real date; the drive pins no date.

This ticket writes the hand-offs. No earlier E8 ticket edits the carried
files' closures; each names the entries it closes in its pull request body.

Read first: E7-09's ticket and `../e7/boundary-review.md` (the record shape);
`carried-from-e7.md` whole; this epic's pull request bodies.

## Owns

- `scripts/seed_student_loop_exit_story.py` (new).
- `tests/e2e/exit-student-loop.spec.ts` (new), the on-behalf drive and the
  unanswered-as-lead drive, and one integration test that reads the seeded
  world through the student's results read, never the seeder's own record
  (MISTAKES entry 58).
- If the `process/` pull request has added `@axe-core/playwright`: an axe scan
  on every page the instructor-report, leadership-moderation,
  instructor-response and leadership-response drives reach.
- `docs/tickets/e8/carried-from-e7.md` and `../e7/carried-from-e6.md`: each
  entry an E8 ticket closed is marked closed with its pull request and merge
  commit.
- `docs/tickets/e9/carried-from-e8.md` (new), under the completeness rule
  `carried-from-e7.md` was written to, with a ledger in source order. It
  includes the stored-summary rule for E9's readers, the Lead Faculty name in
  the student header (ruling 5), `design/LeadershipRollup.dc.html`'s count,
  the chair's department walk and the four other simplifications, and the
  accessibility scan if the package has not landed.
- `docs/tickets/e8/boundary-review.md` (new): the boundary reviews and where
  each finding went.
- `docs/adr/README.md`: a gap line for any allotted ADR number left unused.
- SPEC §14.3's E8 entry, edited to match what was built.
- This README's Merged column.

## Done when

1. **The exit is driven.** One student's seat, on a fresh stack: the survey
   answered; the landing's results lead; the closed door with the course name,
   the posted score and nothing about the week; then, after a publish, the
   response first, the trend, the distributions, the workload median, the
   comments, a small stream's notice and the confidentiality line.
2. **The two carried paths are driven.** One drive publishes on behalf and the
   student reads the lead's name and role. One reads an unanswered week past
   the deadline as the lead. Each runs green twice in a row on one stack.
3. **No pinned date.** The drives and the seeder derive every date from the
   seeded calendar and the real date.
4. **Every E8-owned carried entry is closed** in its source file, each closure
   naming the pull request and the merge commit.
5. **The standing questions are re-asked.** `PERSON_TABLES`; the session-read
   sweep re-affirmed by planting in the results route; the TypeScript 7 peer
   range; every new E8 invariant-marked module collected by the isolated pass.
6. **The hand-off file exists.** `../e9/carried-from-e8.md` lists every entry
   still open, each with an owner and a done-when, and a ledger in source
   order.
7. **The boundary reviews ran** (the full battery CLAUDE.md names for an epic
   boundary), and every finding is fixed in a ticket pull request or carried
   with an owner.

## Shares files with

- `docs/SPEC.md`, `docs/adr/README.md`: every earlier ticket.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 12, 31, 34, 39, 42, 48 and 58.

## Known traps

- **Entry 58.** Verify the seeded world through the reader the claim is about:
  the student page as served, not the seeder's count.
- **The calendar bomb.** Roster sync stamps an enrollment's start from the real
  clock. Derive dates; never pin.
- **Append-only tables.** `instructor_response` and `response_policy` keep
  every row, so a rerun needs its own section-weeks, not a cleanup.
- **Entry 1.** Closing a carried entry means grepping the fact, not the
  heading, across every file that repeats it.

## Not in this ticket

- Any new behaviour. A gap the drive finds becomes a ticket pull request or a
  carried entry.
- Reworking the older drives' pinned dates (a `process/` pull request).
