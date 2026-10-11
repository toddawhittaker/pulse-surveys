# E7-09 — E7 exit

**ID:** E7-09
**Branch:** `e7/e7-exit`
**Depends on:** all
**Lane:** light
**Size:** M
**Security-relevant:** the exit drive proves a held week shows students nothing,
and the boundary reviews run here.

## Context

SPEC §14.3's E7 exit: "a required-mode section shows nothing to students until
a named human publishes." This ticket drives it on the running stack:

- **Held.** A lead sets required for a prefix. In the next week of a section in
  that prefix, a student reads the closed door: no response, no name, no
  figure.
- **Released by a named human.** The instructor drafts, checks and publishes.
  The student reads the response under the instructor's name. The instructor
  edits it; the student reads the new text and the week stays released.
- **On behalf.** In another section-week of the same prefix with no response,
  the lead sees it owed after 48 hours, and after 96 hours publishes on behalf.
  The student reads the lead's name and role.
- **Not your role.** A student who opens a leadership page reads "not part of
  your role" (08).

The world is seeded by a new seeder beside `scripts/seed_moderation_exit_story.py`,
as E6 did. Every date the drive reads is derived from the seeded calendar
relative to the real date; the drive pins no date.

This ticket also writes the hand-offs. No earlier E7 ticket edits the carried
files; each names the entries it closes in its pull request body.

Read first: E6-07's ticket and `../e6/boundary-review.md` (the record shape);
`carried-from-e6.md` and `carried-requirements.md` whole; this epic's pull
request bodies.

## Owns

- `scripts/seed_response_loop_exit_story.py` (new): a required-mode prefix, a
  lead and a chair seat, two sections, a student in each.
- `tests/e2e/exit-response-loop.spec.ts` (new), and one integration test that
  reads `instructor_response` and `response_policy` themselves for the seeded
  world, never the seeder's own record (MISTAKES entry 58).
- `docs/tickets/e7/carried-from-e6.md` and `carried-requirements.md`: each entry
  an E7 ticket closed is marked closed with its pull request and merge commit.
- `docs/tickets/e8/carried-from-e7.md` (new), under the completeness rule
  `carried-from-e6.md` was written to, with a ledger in source order. It
  includes:
  - for E8: the student results route answers the state and the response
    only; E8 adds aggregates and comments under the same hold, and reads the
    hold through 02's functions, never a copy;
  - for E8: release batches carry no week, so E8 decides how a batch sits beside
    a held week on the student page;
  - for E9: the attention list calls 03's 48-hour predicate; staff names on
    leadership pages; the policy views of the assistant dean, dean and vice
    president;
  - the forged summary block boundaries entry, passed on unchanged to the next
    ticket that renders comments into a prompt;
  - the accessibility scan, if no `process/` pull request added the package;
  - the pinned-date drives, still owed by a `process/` pull request before
    2026-11-23;
  - ruling 5 for E10, repeated.
- `docs/tickets/e7/boundary-review.md` (new): the boundary reviews and where
  each finding went.
- `docs/adr/README.md`: a gap line for any allotted ADR number left unused.
- SPEC §14.3's E7 entry, edited to match what was built.
- This README's Merged column.

## Done when

1. **The exit is driven.** The drive shows the closed door before publish, the
   instructor's named response after it, the edited text after an edit with the
   week still released, and the lead's on-behalf response with name and role.
2. **No pinned date.** The drive and the seeder derive every date from the
   seeded calendar and the real date, and the drive is green whatever day it
   runs.
3. **Every E7-owned carried entry is closed** in its source file, each closure
   naming the pull request and the merge commit.
4. **The standing questions are re-asked.** `PERSON_TABLES` is asked of
   `instructor_response` and `response_policy` (each names a `person` key), and
   the answer recorded. The session-read sweep is re-affirmed by planting in
   E7's new routes. The TypeScript 7 peer range is re-checked. Every new E7
   invariant-marked module is collected by the isolated pass.
5. **The hand-off file exists.** `../e8/carried-from-e7.md` lists every entry
   still open, each with an owner and a done-when, and a ledger in source order.
6. **The boundary reviews ran** (the full battery CLAUDE.md names for an epic
   boundary), and every finding is fixed in a ticket pull request or carried
   with an owner.

## Shares files with

- `docs/SPEC.md`, `docs/adr/README.md`: every earlier ticket.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 12, 34, 39, 42, 48 and 58.

## Known traps

- **Entry 58.** Verify the seeded world through the reader the claim is about:
  the student page as served, not the seeder's count.
- **The calendar bomb.** Roster sync stamps an enrollment's start from the real
  clock, so a reading date before it reads nothing. Derive dates; never pin.
- **Entry 1.** Closing a carried entry means grepping the fact, not the
  heading, across every file that repeats it.

## Not in this ticket

- Any new behaviour. A gap the drive finds becomes a ticket pull request or a
  carried entry.
- Reworking the older drives' pinned dates (a `process/` pull request).
