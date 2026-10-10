# E6-07 — E6 exit

**ID:** E6-07
**Branch:** `e6/e6-exit`
**Depends on:** all
**Lane:** light
**Size:** M
**Security-relevant:** the boundary reviews run here, and the exit drive
proves that a Care-class comment leaves no trace on the instructor's page.

## Context

SPEC §14.3's E6 exit: "the anti-cherry-picking trail is visible up-chain, and
a welfare-flagged comment in a 3-response week provably reaches Care with no
trace in the instructor view." This ticket drives it on the running stack:

- **The trail.** An instructor excludes an unflagged comment with a reason, and
  keeps a flagged one. The Lead Faculty member and the department chair each
  find both rows in the exclusion log, with the section, the role, and flagged
  or the reason.
- **The welfare flag.** A section has a 3-response week in which one comment
  carries the mock provider's self-harm marker. After the window closes and the
  sweep runs, a `threat_case` row exists for that comment. The instructor's page
  for that week shows no comment, no count, no participation note and no
  summary text from it, and the empty-week sentence is the same as in a week
  with no comments.

This ticket also writes the hand-offs. No earlier E6 ticket edits the carried
files; each names the entries it closes in its PR body, and this ticket marks
them closed.

Read first: E5.1-09's ticket and `../e5.1/boundary-review.md` (the record
shape), `carried-from-e5.md` whole, `../e5/carried-from-e4.md` and
`../e4/deferred.md`'s moderation entries, and this epic's PR bodies.

## Owns

- The exit story in `scripts/seed_exit_story.py` (or a new seeder beside it):
  the 3-response week with the self-harm marker, an unflagged exclusion with a
  reason, a kept comment, and Lead Faculty and chair seats.
- The Playwright exit drive, and one integration test that asserts the
  `threat_case` row exists for the seeded comment. No product reader of
  `threat_case` exists until E10, so the test reads the table itself, and
  never the seeder's own record of what it wrote (entry 58).
- `docs/tickets/e6/carried-from-e5.md`, `../e5/carried-from-e4.md` and
  `../e4/deferred.md`: each entry an E6 ticket closed is marked closed with its
  PR and merge commit.
- `docs/tickets/e7/carried-from-e6.md` (new), under the completeness rule
  `carried-from-e5.md` was written to, with a ledger in source order. It
  includes a note for E8: student comment reads use `report_comment` v004 and
  show published and kept comments only. It repeats ruling 5 for E10: no
  deployment reaches real students until E10's Care queue exists, because
  until then a `threat_case` row has no reader. And it carries to E10 that a
  comment which reaches E6-02's attempt cap is never routed to Care, so capped
  comments still need E10's Care sweep; and that a comment the provider refuses
  with any HTTP status (a content filter among them, which is likeliest to
  refuse a threat or self-harm disclosure) counts nothing toward the cap, is
  retried every hour, and holds its week until E10's Care review decides it
  (E6-08).
- `docs/tickets/e6/boundary-review.md` (new): the boundary reviews and where each
  finding went.
- `docs/MISTAKES.md`: the note explaining why entries 54 to 57 have no file,
  found from git history.
- `docs/adr/README.md`: a gap line for any allotted ADR number left unused.
- SPEC §14.3's E6 entry, edited to match what was built: the log's scope is the
  reader's own grant, and the log shows the role, not a name.
- This README's Merged column.

## Done when

1. **The trail is driven.** The exit drive shows both log rows to the Lead
   Faculty seat and to the chair seat, and shows neither to an instructor-only
   seat.
2. **The welfare flag is driven.** The drive and the integration test show the
   `threat_case` row and an instructor page with no trace, beside a canary week
   in the same world whose comments do show.
3. **Every E6-owned carried entry is closed** in its source file, and each
   closure names the PR and the merge commit.
4. **The standing questions are re-asked.** `PERSON_TABLES` is asked of
   `threat_case` and of `moderation_state.decided_by_person_id`, and the answer
   is recorded. The session-read sweep is re-affirmed by planting in E6's new
   routes. The TypeScript 7 peer range is re-checked. Every new E6
   invariant-marked module is collected by the isolated pass.
5. **The submit-budget row is closed** in the ledger, citing E5.1-10.
6. **The hand-off file exists.** `../e7/carried-from-e6.md` lists every entry
   still open, each with an owner and a done-when, and a ledger in source order.
7. **The boundary reviews ran** (the full battery the CLAUDE.md review tiers
   name for an epic boundary), and every finding is fixed in a ticket PR or
   carried with an owner.

## Shares files with

- `scripts/seed_*_story.py`: E6-01 before this.
- `docs/SPEC.md`, `docs/adr/README.md`: every earlier ticket.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 12, 34, 39, 42, 48 and 58.

## Known traps

- **Entry 58.** Verify the seeded world through the reader the claim is about:
  the instructor report and the exclusion log as served, not the seeder's own
  count.
- **The calendar bomb.** Pin the clock in the exit world; never rely on today's
  date (ADR 0184's 06:00 Monday opening applies).
- **Entry 42.** A CI verdict is a completed run whose head SHA is the commit
  vouched for.
- **Entry 1.** Closing a carried entry means grepping the fact, not the
  heading, across every file that repeats it.

## Out of scope

- Any new behaviour. A gap the drive finds becomes a ticket PR or a carried
  entry.
