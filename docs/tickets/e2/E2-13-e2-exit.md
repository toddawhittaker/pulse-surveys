# E2-13 — E2 exit: the four clauses in a browser, and the hand-off

**ID:** E2-13
**Branch:** `e2/e2-exit`
**Depends on:** everything (E2-01 … E2-12)
**Lane:** heavy
**Security-relevant:** the boundary reviews themselves (§14.2 item 6), and
the written re-affirmation this breakdown owes on the denial-module sweep.

## Context

§14.3 E2's exit line has four clauses. This ticket proves each against the
running stack the way E1-15 did, runs the epic-boundary reviews, and writes
`../e3/carried-from-e2.md` for anything E2 hands on.

The Playwright student flow rides the E2-04 dev clock (set a Friday evening;
the alternative is a suite that only passes on weekends) and the E2-07 mock
(deterministic verdicts, no tokens). The e2e memory holds two known traps:
Chromium's Local Network Access rules around the synthetic-iframe wrapper,
and the dev cookies being SameSite=None-without-Secure so the session rides
the Bearer path — both already navigated by E1's specs; copy their shape.

Read first: §14.3 E2's exit line and §14.2 item 6; `tests/e2e/support/doors.ts`
and the E1 exit specs (`exit-*.spec.ts`) as the pattern; the carried block's
denial-module bullet (the decision recorded below); every E2 ticket's
deferred notes as they accumulated in `deferred.md`.

## Scope

- **Clause 1 — a student submits a valid response.** Launch as the seeded
  student through the mock LMS, dev clock on an open window, complete the
  five questions, submit, see the submitted state; the response and its
  classification rows exist.
- **Clause 2 — "it was okay" is bounced with immediate feedback.** Same
  seat: low rating, "it was okay" in the required comment, submit, assert
  the coaching bounce (immediate — no page reload into an error), fix,
  resubmit, succeed. The mock's published rules make the verdict
  deterministic.
- **Clause 3 — the §4.1 item 1 test.** Already E2-09's; here the exit
  verifies it is collected in the isolated invariant pass on the exit
  commit **and re-runs E2-09's loosened-predicate mutation against that
  commit** — collection is presence, not the failing behavior the clause
  names, and anything merged since E2-09 could have loosened the assertion
  under a green suite. Battery discipline applies: commit first, snapshot
  restore, check the mutation landed. The boundary invariant-coverage audit
  separately asks whether every read path E2 added is touched by the suite.
- **Clause 4 — the copy-inventory test exists and reads shipped strings.**
  E2-11's; verified collected and its canary live on the exit commit.
- Also in the browser, because the epic's correctness rests on them: the
  closed-window state (clock moved to Monday), and the fail-open submit
  (mock stalling past the budget) landing as accepted-on-floor.
- **Epic-boundary reviews** (§14.2 item 6): exit review, invariant-coverage
  audit, docs/ADR completeness. E2 is unmarked, so no whole-epic threat model
  is owed — but the per-PR reviews stood in every ticket, and the boundary
  record says so rather than leaving it inferred.
- **The denial-module sweep re-affirmation** — this breakdown's decision on
  the carried bullet: the E2 boundary review re-affirms the two disclosed
  limits of `DENIAL_NAME_SHAPES` in writing (a shape named outside every
  pattern escapes; a shape deleted together with its planted sample is
  green), or reports they no longer hold. If E2-09 added a denial module,
  the review names it against the shapes.
- **The hand-off**: `docs/tickets/e3/carried-from-e2.md`, one entry per
  deferral with owner and done-when, per §14.1. Its completeness rule:
  **every entry of `carried-from-e1.md` not closed inside E2 appears, whoever
  owns it** — the E3/E4/E9/E11/E13-owned entries (signing-key custody, AGS
  token, the reveal-subject guard and its E4 deadline, logout, the web-login
  linkage, the squat repair, the CSP write-time rejection, `PERSON_TABLES`,
  the local-account fallback, the mock-conditional pins) pass through by
  being re-listed, because §14.1 routes every deferral through the epic
  boundary and E3's breakdown reads this file, not E1's. Plus whatever
  E2-12 left of §11 question 4 and everything in E2's own `deferred.md`.
- **The TypeScript 7 watch**: the carried entry's owner is "whichever epic
  is running when `typescript-eslint` admits 7.x". Run
  `npm view typescript-eslint peerDependencies` at exit: if 7.x was admitted
  during E2 and the pair was not moved, say so and carry it with that fact
  rather than silently re-deferring.

## Acceptance criteria

1. All four exit clauses proven by enforced e2e/CI runs on the exit commit —
   the specs are in the enforcing Playwright gate, not a demo script.
2. The three boundary reviews are run fresh at the boundary and their
   findings triaged; findings become E2's final batch, never E3's
   inheritance (§14.2 item 6).
3. The re-affirmation paragraph exists in the boundary record.
4. `carried-from-e2.md` exists and every `deferred.md` entry is either
   closed or carried with an owner — none silently dropped.

## Out of scope

- Merging `epic/e2-weekly-survey-validity` to `main` — Todd's, always.
- Fixing what the boundary reviews find — those are their own tickets in
  E2's final batch, scoped when found.
