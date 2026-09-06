# E4-12 — The report's copy, and the inventory grows over it

**ID:** E4-12
**Branch:** `e4/report-copy-and-inventory`
**Depends on:** E4-08, E4-09, E4-10, E4-11
**Lane:** heavy — the copy-inventory test is invariant-marked and its
collector lives in `tests/fixtures/copy_inventory.py`, a heavy row.
**Security-relevant:** §4.1 items 4 and 5 are confidentiality rules enforced
through copy; this ticket is their enforcement growing over the epic's new
surface.

## Context

The copy-inventory gate has governed shipped strings since E2, growing with
each UI epic. E4 ships the largest user-facing surface yet, and this ticket
is where the inventory provably covers it — plus four carried items that are
all, at bottom, about strings nothing governs:

1. **The gradebook's two instructor-visible strings** — `PULSE_LABEL`
   ("Pulse Participation") and the ledger line format ship into an LMS
   gradebook, and the inventory collects neither. Done when both are
   collected or the inventory records why the gradebook is not a governed
   surface.
2. **The credit-rule explanation, instructor half** — nothing anywhere
   explains §3.4's arithmetic to an instructor reading the ledger in her
   gradebook, or what the validity rate on her report means for credit.
   Scoped to what the report actually shows: this is ambient explanatory
   copy on the report surface, not a participation-score view (E4 renders no
   scores; E8 owes the student half).
3. **The rendered student surface's string convention that nothing sweeps**
   — the carried convention gap; its entry's done-when governs.
4. **The copy collector's symlinked-directory gap** — the collector misses
   strings behind a symlinked directory; close it and prove it against a
   planted symlink.

Read first: SPEC §4.1 items 4 and 5, §5.1;
`tests/unit/test_the_shipped_copy_inventory_holds_to_items_four_and_five.py`
and `tests/fixtures/copy_inventory.py`; the four carried entries via
`carried-from-e3.md`; `backend/app/copy/` and `frontend/src/copy/` layouts.

## Scope

- The inventory's governed surfaces extended over the report's copy modules
  (frontend) and any backend-shipped report strings, with the items-4-and-5
  vocabulary check running over all of it.
- The two gradebook strings collected (the recommendation — they are
  instructor-facing strings Pulse ships, and "the surface is another
  product's UI" is a fact about rendering, not about authorship), or the
  recorded why-not.
- The credit-rule instructor copy, written to the brief's tone rules,
  placed where the report shows the validity rate.
- The convention sweep and the symlink fix, each proven against a planted
  violation.

## Acceptance criteria

1. The inventory's collected-surface list includes every copy module E4
   shipped, proven the collector's own way — and a planted new string in a
   report component that bypasses the copy layout is a red test, not a gap.
2. The vocabulary gate over the new surface passes, and was seen failing
   once against a planted "underperforming" in report copy — the gate is
   known capable of failing on this surface.
3. The gradebook strings: collected and passing, or the recorded decision —
   either way the carried entry's done-when is met and the entry closes in
   `carried-from-e3.md` with what closed it.
4. The credit-rule copy ships on the report surface, in the inventory,
   answering what the validity rate means and that a posted score can move
   down later — without inventing a score display.
5. The symlink gap: a planted symlinked copy directory's strings are
   collected; before the fix, the same plant was provably missed.
6. The string-convention sweep exists per its carried done-when and passes
   over the shipped surfaces.

## Known traps

- **The collector counts in one currency** — the marker-in-two-currencies
  memory: count governed modules with the collector itself, never a
  parallel walk that can disagree with it.
- **Copy edits ripple into e2e assertions** — E4-11's specs assert content;
  landing copy changes here means updating those assertions in the same PR,
  honestly (assert the meaning-bearing part, not the full sentence, where
  the brief allows).
- **Item 4's list is exact** — "needs attention" never "underperforming",
  sections never instructors, no ranking, no composite scores, no
  score-sorting. The gate encodes it; the copy author reads it first.

## Out of scope

- New report features or layout — this ticket ships words and gates, not
  surfaces.
- The student half of the credit-rule explanation — E8.
- Aggregate-language rules on leadership surfaces — E9, when those exist.
