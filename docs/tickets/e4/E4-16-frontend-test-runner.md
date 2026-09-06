# E4-16 — The frontend test runner

**ID:** E4-16
**Branch:** `e4/frontend-test-runner`
**Depends on:** nothing — and E4-08, E4-09 and E4-10 merge after it
**Lane:** heavy — the diff reaches the root `package.json` and
`.github/workflows/` (the CI-gates row), and a test gate is exactly the kind
of thing the lane exists to guard.
**Security-relevant:** a new dev dependency tree (pinned, lockfile
committed) and a new CI gate; `app-security` fires via the manifest paths.

## Context

E2 deliberately did not add a frontend unit-test runner, with the cost
stated — component-level regressions surface in a browser run instead of a
unit run — and the revisit trigger "when a screen's logic outgrows what the
end-to-end suite pins cheaply" (`docs/tickets/e3/carried-from-e2.md`, passed
through to `carried-from-e3.md`). E4 is that moment, structurally: three
component tickets whose acceptance criteria are component tests, building in
parallel, none of which can execute a test today — `frontend/package.json`
has `dev`, `build`, `typecheck`, `lint` and nothing else, and the Playwright
config runs `tests/e2e/` only.

This ticket exists so the runner arrives as a reviewed decision rather than
inside whichever light ticket's builder hits the wall first — a dependency
choice and a CI gate are heavy-row work and were never going to be light,
whatever ticket they stowed away in.

Read first: the carried entry; `docs/tickets/e1/E1-02-node-workspace-layout.md`
(how the Node toolchain is laid out and why); `.github/workflows/ci.yml`'s
frontend jobs and the change-detection that selects them; ADR 0002 (gate
tolerances); the pin-and-lockfile rule in `CLAUDE.md`.

## Scope

- The runner, pinned, with its lockfile — vitest is the recommendation (it
  shares the Vite toolchain the frontend already builds with, so it adds a
  test runner without adding a second build system), and the choice is
  contestable, so the ADR weighs it.
- The conventions the three component tickets will follow, written into the
  ADR: test files beside components, fixture modules beside tests, what
  renders them (plain DOM assertions vs a testing library — decide once
  here, not three times in parallel).
- One proof test against an existing component (`WeekEyebrow` is sitting
  right there), so the runner demonstrably runs something real.
- The CI gate: a frontend-test step in the job family the change detection
  already routes frontend diffs to, red meaning stop, with no tolerance
  flag (ADR 0002 governs any exception, and none is expected).

## Acceptance criteria

1. The proof test runs and passes locally and in CI, and the CI step is
   provably capable of failing: a planted red component test turns the
   pipeline red, watched once and then removed (the exit-status lesson of
   `docs/MISTAKES.md`'s piped-gate entry: verify the gate's verdict, not
   its output).
2. A frontend diff trips the new gate through the change-detection route; a
   docs-only diff does not — both directions asserted the way the existing
   detection tests assert job selection.
3. Every added package is exactly pinned and the lockfile is committed; the
   exact-pin equality guard and all existing Node-facing gates stay green.
4. The bundle budget gate is untouched — a test runner is dev-only and the
   built bundle proves it by not changing.
5. The ADR records the runner choice, the rejected alternatives, and the
   component-test conventions E4-08/09/10 build to.
6. The carried entry closes in `carried-from-e3.md` with what closed it and
   what tripped the revisit trigger.

## Known traps

- **The TypeScript 7 wait constrains nothing here but versions do** — the
  carried TS7 entry stays untouched; whatever the runner pulls must resolve
  against the pinned `typescript` 6.0.3 without floating anything.
- **A gate added but not routed** — the change-detection classifier decides
  which diffs run which jobs; a new step in an unrouted job is a gate that
  never fires. Criterion 2 is the proof, both directions.
- **Convention drift across three parallel builders** is the failure this
  ticket pre-empts; if the ADR leaves a convention unstated, three tickets
  will state it three ways.

## Out of scope

- Writing the component tests themselves — E4-08, E4-09, E4-10.
- Any change to the e2e suite or Playwright config.
- Retrofitting tests onto E2's survey components beyond the one proof test.
