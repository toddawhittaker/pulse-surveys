# E9-13 — E9 exit

**ID:** E9-13
**Branch:** `e9/e9-exit`
**Depends on:** all
**Lane:** light
**Why this lane:** drives, a seeder link and records. It adds no behaviour.
**Size:** M
**Security-relevant:** the exit drive proves the worked example resolves the
same from both doors; the boundary reviews run here.

## Context

SPEC §14.3's E9 exit: "the assistant-dean worked example (§2.1) resolves
correctly from either door, and generated-graph properties prove sibling
isolation and transitive unions." The properties are E9-01's and E9-05's;
this ticket drives the rest on a fresh stack.

- **Both doors.** The seeded assistant dean enters by web login (the mock IdP
  already seeds them) and by an LTI launch (a new mock-LMS user linked to the
  same person by `scripts/seed.py`). From each, the roll-up's roots are Math,
  Biology and PSYC 110's prefix; Psychology shows only PSYC 110; and the two
  doors show the same tree.
- **The switch.** From the launch, the two-hat person switches to their other
  role and back, then logs out.
- **Only the university line withheld** (carried from E5): a seeded week in
  which the drill-down shows the comparison line and withholds the university
  line, and the drive asserts the payload and the treatment.

Every date comes from the seeded calendar relative to the real date; the
drive pins no date.

This ticket writes the hand-offs. No earlier E9 ticket edits the carried
files' closures; each names the entries it closes in its pull request body.

Read first: E8-04's ticket and `../e8/boundary-review.md` (the record shape);
`carried-from-e8.md` whole; this epic's pull request bodies.

## Owns

- `scripts/seed.py`: the mock-LMS user linked to the assistant dean.
- `tests/e2e/exit-dean-both-doors.spec.ts` extended, or a new
  `tests/e2e/exit-assistant-dean.spec.ts`, and the university-line drive, each
  with an axe scan on the pages it reaches; one integration test that reads
  the seeded world through E9-07's roll-up read, never the seeder's own record
  (MISTAKES entry 58).
- `docs/tickets/e9/carried-from-e8.md` and the older files' E9 entries: each
  entry an E9 ticket closed is marked closed with its pull request and merge
  commit.
- `docs/tickets/e10/carried-from-e9.md` (new), under the completeness rule
  `carried-from-e8.md` was written to, with a ledger in source order. It
  includes: every Care grant shown in E10's Admin access log (ruling 1, SPEC
  §6.2); conflict-of-interest marking across a revealer's whole purview, now
  possible; the `moderation.py` split and import cycle, with the reason they
  went to E10; and every entry the README marks for re-carrying.
- SPEC §14.3's E9 entry, rewritten at exit as E8's was.
- `docs/adr/README.md`: any ADR number allotted and unused, recorded as a gap.

## Done when

1. **The worked example from both doors.** The drive shows the assistant
   dean's roots and Psychology's single course from the web door and from the
   launch, and the two trees are equal.
2. **The switch and logout** run end to end, and the logged-out token is
   refused.
3. **The university line alone is withheld** in a seeded week, asserted on the
   payload and on the page.
4. **Re-runnable.** Each drive runs green twice in a row on one stack.
5. **The hand-offs.** Every carried entry this epic owned is closed with its
   pull request and merge commit, or re-carried with its reason;
   `carried-from-e9.md` holds the ledger; the standing questions are re-asked
   (`PERSON_TABLES` against 02's and 04's tables).
6. **The records match.** SPEC §14.3's E9 entry says what shipped; unused ADR
   numbers are recorded as gaps; the README's Merged column is filled.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 48, 51 and 58.

## Known traps

- **Entry 58.** The seeded assistant dean's tree is verified through the
  roll-up read, not through the seeder.
- **The calendar bomb.** No literal date.

## Not in this ticket

- New behaviour of any kind.
- The boundary reviews' fixes, which become their own tickets.
