# E2-18 — Three pins the eval gate's own review asked for

**ID:** E2-18
**Branch:** `e2/eval-guard-pins`
**Depends on:** E2-12 (the suite these pins guard)
**Lane:** heavy
**Security-relevant:** no, but every item guards the gate that guards §3.3.

## Context

The epic-boundary prompt-eval review, verified adversarially, found three
enforcement gaps around the eval gate — none live today, each a door open to a
silent future weakening. Record: `docs/tickets/e2/boundary-review.md`, second
round. All three fixes are test machinery; no application behavior changes.

## Scope

1. **Prompt files are pinned by content, not convention.** ADR 0032's
   immutability rule has no test: the eval runner compares version *stems*
   (`tests/evals/runner.py` ~293), so an in-place edit of
   `backend/app/ai/prompts/validity.v2.md` passes every gate and re-measures
   the floors against changed text (verified; the mock guards only the final
   marker line). New test: a recorded hash per committed prompt file, red on
   any byte change, with the rule stated that a prompt change is a NEW
   version file plus a deliberate re-measure — never an edit plus a hash
   bump in the same breath (the test's docstring says where the hash moves
   and what must move with it).
2. **The E2-12-06 dispute fix is pinned.** The eval path must reach the model
   through the live gateway with `EVAL_TIMEOUT_SECONDS`, never through §3.3's
   submit path where a slow answer becomes the 25-character floor (that
   routing voided two full measurement runs). Verified: nothing asserts
   either half; reverting the timeout or the routing is green everywhere and
   caught only by a paid run. Pin both: the timeout constant's relation to
   the task budget, and the routing (the classifier the runner builds is the
   gateway one, not `verdict_for_comment`).
3. **The hard families get size floors.** The set-shape guards hold the
   total (80–140), ten per class, and each hard family non-empty — so a
   98-case set keeping one short-substantive and one long-vacuous case clears
   every structural test while materially easing the floors (the guard's own
   docstring concedes it). Add per-family minimums pinned to the current
   family sizes' neighborhood, with the docstring saying a deliberate
   set-narrowing moves the minimums in its own PR.

## Acceptance criteria

1. Editing one byte of a committed prompt file turns a test red; adding a new
   version file alongside does not.
2. Reverting `EVAL_TIMEOUT_SECONDS` to the §3.3 budget, or routing the eval
   classifier through the submit path, turns a test red — both proven by
   mutation.
3. Shrinking any hard family below its floor turns the shape guard red; the
   current committed set is green.
4. No live provider call anywhere in the new tests.

## Out of scope

- Everything in E2-16 and E2-17. The floors' values (ruled; E10 owns the
  revisit). The model-identifier tie (its carried entry stands).
