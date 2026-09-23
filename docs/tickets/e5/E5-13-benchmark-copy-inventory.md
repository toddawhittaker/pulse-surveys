# E5-13 — The copy inventory grows over the benchmark surfaces

**ID:** E5-13
**Branch:** `e5/benchmark-copy-inventory`
**Depends on:** E5-09, E5-10
**Lane:** heavy
**Security-relevant:** §4.1 items 4 and 5 are enforced through this
inventory; the sweep and its tests live on heavy paths.

## Context

E2 started the copy-inventory test and it grows with each UI epic (E4-12
is the direct precedent). E5 ships new user-facing language in exactly the
place §4.1 item 4 watches: comparison vocabulary. Legends, suppression
notices, set-management copy, the eyebrow's close note (E5-02) — all of it
is collected, and the vocabulary rules are checked globally: sections
counted, never instructors; "needs attention", never "underperforming";
no ranking, no composite scores.

One rule this epic makes newly hot: a benchmark line invites "above/below
average" phrasing, which is comparison language about a *section* and
allowed — but the same shape about an *instructor* is item 4's exact
target. The inventory's job is to make that line reviewable in one place.

Read first: SPEC §4.1 items 4 and 5; the inventory test and collector as
E4-12 left them (including the symlink fix); E4-12's ticket for the
grown-surface conventions; every copy module E5-07 through E5-10 shipped.

## Scope

- The collector reaches every new E5 surface: the overlay legend and
  suppression treatments, the workload comparison block, the named-set
  route, the close note.
- The inventory records grow; item 5's once-per-surface rule is asserted
  for the new leadership surface (its standing confidentiality line, if
  the brief gives it one — follow the brief, and record the answer).
- A vocabulary check for the benchmark register: the banned shapes of
  item 4 swept over the new strings, with the canary discipline (a
  planted violation is caught — the sweep is proven able to see before it
  is believed clean).

## Acceptance criteria

1. The collector's output demonstrably includes strings from each new
   surface — named strings asserted present, so growth is a fact
   (MISTAKES entry 3's non-emptiness rule).
2. A planted ranking phrase in an E5 copy module fails the sweep; removed,
   it passes — both directions, in the PR's evidence.
3. Item 5 asserted over the leadership surface per the brief's answer.
4. No E5 surface ships a string outside the collected layout — swept, with
   the symlink case E4-12 fixed still covered (a regression here is
   silent).
5. The inventory records in the repository are updated in this PR, and
   nothing else claims copy coverage E5 did not give it (entry 1's grep
   for the fact).

## Known traps

- **Sweep last** — this ticket merges after the surfaces it certifies;
  a mid-round sweep certifies claims the next commit falsifies (the
  standing sweep-last rule).
- **The sweep proven by its canary, every run** — entry 3 verbatim.

## Out of scope

- Writing new UI copy — the surface tickets own their words; this ticket
  collects and polices.
- Aggregate-ordering gates — E9's carried entry.
