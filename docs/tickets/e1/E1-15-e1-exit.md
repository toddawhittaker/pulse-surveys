# E1-15 — E1 exit: five clauses, both doors, in a browser

**ID:** E1-15
**Branch:** `e1/e1-exit`
**Depends on:** E1-04, E1-08, E1-09, E1-11, E1-12, E1-13, E1-14
**Security-relevant (⚠):** the refusal specs — a proof suite that can only
speak correctly proves nothing (MISTAKES entry 28), so the review's focus is
that the negative specs genuinely exercise the guards.

## Context

E0's lesson, recorded in its README: §14.3 implied an exit criterion and
listed no ticket proving it, and without E0-18 the e2e gate would have stayed
tolerant into E1. This is E1's E0-18. §14.3 E1's exit line has five clauses;
the README's exit table maps each to the tickets it rests on; this ticket
proves all five in a browser against `docker compose up`, and closes the epic's
bookkeeping the way §14.1 requires.

Read first: SPEC §14.3 E1 (the exit line, verbatim — each clause becomes at
least one spec); §9.2; E0-18 for the shape (including its exit-checklist
pattern); the E1-07 mint catalog; `docs/tickets/e0/README.md`'s carried-out
discipline (the model for `carried-from-e1.md`).

## Scope

- Playwright specs, one per clause, named for the clause they prove:
  1. student, instructor, and Dean land on their E1-04 views — student via
     launch; instructor via launch; the Dean via **both** doors in one spec.
  2. the two-hat person enters by both doors; the spec asserts the same
     stored identity row (through whatever honest seam the app exposes for
     the assertion — a dev-only introspection is acceptable if gated per the
     E1-14 verdict's rules and recorded).
  3. a synced section shows correct derived dates — driven end to end:
     staff launch → provision → sync → the dates E0-07's parser derives,
     asserted against the seeded term calendar, not against the parser
     (MISTAKES entry 19: the expectation must not be a copy of the code
     under test).
  4. a replayed launch and a state-tampered launch are refused — via E1-07's
     mints, asserting the refusal page and the absence of a session.
  5. the roster read is authenticated — proven at the e2e level by the sync
     having worked *and* a spec-level assertion that the mock's roster
     endpoint refuses tokenless requests (so the passing state cannot be an
     unauthenticated accident).
- The CI e2e job runs the new specs on every non-inert diff exactly as today;
  no tolerance is added or widened.
- **`docs/tickets/e1/carried-from-e1.md`** written per §14.1: every deferral
  E1 accumulated, one entry each, owner and "done when" — seeded from the
  README's not-do list (the E4 reveal guard hand-off restated; anything E1's
  build rounds added; the local-account fallback and logout questions from
  E1-09 if still unowned).
- The epic-boundary reviews (§14.2 item 6) are not this ticket — they run
  after the epic's last content merge — but this ticket's PR body carries the
  exit checklist the `epic-exit` agent will verify, clause by clause, so the
  boundary review has a stated target.

## Acceptance criteria

1. All five clause-specs pass against the composed stack in CI.
2. Each refusal spec is proven capable of failing: run once against a
   deliberately weakened guard in a scratch tree during the build round
   (never committed), per MISTAKES entry 9 — the PR body records the
   mutation and the red.
3. `carried-from-e1.md` exists; every entry has an owner and a done-when; the
   README's not-do items are each either done, carried, or already owned by a
   later epic's §14.3 entry.
4. The E1 README's build-order table shows every ticket merged or its
   deferral recorded — the state the `epic-exit` agent checks.

## Out of scope

- The epic-boundary reviews themselves (run at the boundary, after this
  merges).
- Any new capability — this ticket proves; it does not build. A clause that
  cannot be proven without new code is a finding against the ticket that owed
  the code, handled as a fix round there, not padded in here.
