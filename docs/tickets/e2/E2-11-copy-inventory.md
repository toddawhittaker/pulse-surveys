# E2-11 — The copy-inventory test: §4.1 items 4 and 5 become assertions

**ID:** E2-11
**Branch:** `e2/copy-inventory`
**Depends on:** E2-08, E2-09, E2-10
**Lane:** heavy
**Security-relevant:** this is a §4.1 assertion joining the invariant pass;
the test machinery is the surface.

## Context

§4.1 items 4 and 5 have been "enforced by review only" since E0; §14.3 E2
ends that: "shipped user-facing strings collected and checked against §4.1
items 4 and 5, growing with each later UI epic." The survey is the first
governed surface. The exit criterion is explicit: the test exists **and
reads the survey surface's shipped strings** — an inventory fed by hand is
exactly the copy-drift this rule exists to catch.

Item 4: aggregate language counts sections, never instructors; "needs
attention," never "underperforming"; no ranking, no composite scores. Item 5:
confidentiality copy exactly once per surface — for the survey, in the
submit bar — plain words, no shield or lock iconography.

Read first: SPEC §4.1 items 4–5 and §5.6's non-goals vocabulary; the E2-08 /
E2-09 / E2-10 string modules (built to be read by this test); §10's i18n line
(strings externalized from day one — this test is what makes that line
load-bearing); MISTAKES entry 3 (a pattern searched against text runs against
what it catches *and* what it allows, with a canary); the carried memory that
an inventory needs a source the guarded structure cannot shrink.

## Scope

- The inventory: a collector that reads the shipped strings — the
  externalized frontend string module(s) and the backend-served copy (bounce
  feedback, refusal messages) — per surface, from the source of record, not
  from a copied list. A governed surface registers itself; the collector
  proves non-emptiness per registered surface (an empty surface is a failure,
  not a pass) and carries a canary string it must always find.
- The vocabulary assertions over the inventory: item 4's forbidden terms and
  shapes, item 5's exactly-once confidentiality copy per surface with its
  placement (submit bar) and the no-iconography rule as far as text can carry
  it (icon assets are E2-10's review; the test checks the strings and the one
  place the copy may appear).
- Both directions proven: a planted violation in each rule's direction goes
  red ("underperforming", a second confidentiality sentence, a ranked
  phrase); the shipped copy passes; the canary detects a collector gone blind
  (MISTAKES entries 3, 9).
- The test joins the invariant pass (marked, isolated CI run, skip-is-fail)
  and its docstring names §4.1 items 4 and 5.
- Honest limits stated in the test's docstring: what the collector cannot
  see (a string assembled at runtime, an aria label built in JSX) — stated,
  per the denial-sweep precedent, so the boundary review re-affirms known
  limits rather than discovering them.

## Acceptance criteria

1. The exit clause holds: the test exists and reads the survey surface's
   shipped strings from their source of record.
2. Planted violations red, shipped copy green, canary live — all three run
   in the PR, not argued.
3. The inventory's surface list has a source the code cannot quietly shrink,
   with a planted unregistered-surface control.
4. §4.1's footnotes for items 4 and 5 ("asserted from E2") are re-read and
   still true (MISTAKES entry 1).

## Out of scope

- Report and aggregate surfaces — E4 grows the inventory over them; the
  mechanism built here must make that an addition, not a rebuild.
- Translation/i18n beyond the externalization the collector needs (§10:
  English only at v1).
