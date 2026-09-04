# FIX-02 — The eval set measures fluent off-topic English

**ID:** FIX-02
**Branch:** `fix/eval-fluent-off-topic`
**Depends on:** nothing open (builds on merged E2-18)
**Lane:** heavy — the validity eval set and its composition pin are the eval
gate's own territory; prompt-eval's review fires.
**Security-relevant:** no code path changes; the gate that guards §3.3's
verdicts is what gets stronger.

## Context

Found by the owner on 2026-09-03: "A man a plan a canal panama" and
"Four score and seven years ago" — grammatical English that is not about the
course — went through the dev stack unremarked. In dev that is by design (the
mock judges by marker only). What matters is the real model, and the eval
set's `nonsense` family is all keyboard mash, lorem, and emoji: **no case
measures whether gpt-5.6-luna refuses fluent off-topic English.** Whether the
floors hold over that region is currently unknown, which is the exact state
the suite exists to remove.

This is a deliberate composition change under the E2-18 pin
(`tests/unit/test_the_validity_eval_set_carries_the_cases_the_heuristic_gets_wrong.py`):
the change and the floor-arithmetic re-derivation happen in one PR, on
purpose, with a live re-measure.

## Scope

1. **A fluent off-topic group joins the `nonsense` family** in
   `tests/evals/validity/cases.py`: the owner's two strings verbatim, plus
   the same shape varied — a famous quotation, song-lyric-like lines, weather
   or lunch small talk, a proverb — roughly 8–12 cases, every one grammatical
   English a human instantly reads as not course feedback, lengths straddling
   the 25-character floor like the rest of the family. Expected verdict
   `nonsense` per §3.3 ("did not come through as a comment about the
   course").
2. **The composition pin moves with it**: `EXPECTED_FAMILY_COUNTS` updated in
   the same commit; totality stays two-way.
3. **The floor arithmetic is re-derived, not assumed.** New cases are
   negatives, so the precision floor's tolerated-false-positive count is what
   moves; `tests/evals/validity/floors.py`'s prose states the new
   denominators and what 0.92/0.90 now tolerate. The floor VALUES do not move
   in this PR — if the live measurement breaches a floor, that is a finding
   about the model, reported to the owner, never resolved by lowering a
   number (CLAUDE.md's floor rule; the E10 revisit owns any resizing).
4. **A live re-measure on gpt-5.6-luna** over the whole set (~110 calls,
   about half a cent): the diff touches `tests/evals/`, so CI's eval gate
   fires on its own; run `make evals` locally first off `.env` (the key is
   present on the development machine) and record the measured pair and the
   per-case outcomes for the new group in the PR body. Update the spend
   ledger memory. Expect run-to-run variance of 1–2 cases per the three
   bracketing runs on record.

## Constraints

- The mock provider changes not at all (markers remain the only route to
  `nonsense` in dev; that is recorded design, not a gap).
- No prompt change, no floor change, no contract change. ADR only if the
  measurement forces a genuinely contestable decision; otherwise the PR body
  and the file prose are the record.
- New case ids follow the family's `ns-NNN` numbering; docstrings follow the
  file's register.

## Acceptance criteria

1. The set holds the new group, the composition pin is green at the new
   counts, and deleting one new case turns the pin red (proven once).
2. The live run's measured precision/recall clear the standing floors, with
   the per-case outcomes for the new group recorded in the PR body — or the
   breach is reported to the owner with the numbers, unresolved.
3. `floors.py`'s arithmetic prose matches the new set sizes.

## Out of scope

- Floor values (E10's revisit). Everything in FIX-01. Any mock change.
