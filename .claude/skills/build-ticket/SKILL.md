---
name: build-ticket
description: Build one ticket through the lane its header names - heavy rides the orchestrated tests-first loop (test-author writes red, implementer turns green, verifier proves it by battery), light rides builder-writes-code-and-tests with one fresh verifier pass; both get the fresh-context security review. Use when the user says "build E0-05", "build ticket 3", or asks to implement a ticket from docs/tickets/. Cuts the ticket branch and stops at a PR without merging.
---

# Build a ticket

Drives one ticket from `docs/tickets/` to an open pull request. **You are the
orchestrator: you design, brief, arbitrate, and verify-by-delegation. The
subagents build.** Your brief is where the leverage is — a design decision
settled in the brief stays settled; one left open comes back as a review
finding or a wasted round.

`$1` is the ticket ID (`E0-05`) or a loose ordinal ("ticket 3" means `E0-03`).
If ambiguous, ask — building the wrong ticket wastes a whole loop.

## 0. The lane

Read the ticket header's `**Lane:**` field first. A missing field, a ⚠
anywhere on the ticket, or doubt means **heavy** — steps 1 through 7 below.
`**Lane:** light` means step 1, then the **Light lane** section at the end of
this file in place of steps 2–5, then steps 6 and 7 unchanged. If mid-build
the diff reaches a surface CLAUDE.md's lane rule names as heavy (read paths,
authz, the doors, token handling, guarded writers, key custody, CI gates),
stop and re-lane: what exists becomes the heavy lane's starting material, the
tests get a `test-author` pass before they are trusted, and the PR records
the switch.

## 1. Plan, before any agent

Read the ticket, its epic README row, and the spec sections the ticket names.
Check its dependencies actually merged into the epic branch; if not, stop and
say so.

Then write the work order — this is the step that used to be skipped and used
to cost two extra rounds:

- **Settle every design decision the ticket leaves open**: module homes,
  contracts between components, exact identifiers tests and code must agree on
  (testids, setting names, error shapes), what is refused vs ignored vs
  defaulted, and any test seam the machinery needs. Verify file:line facts
  against the tree yourself before putting them in a brief — stale line
  numbers are the most common brief defect.
- **Name the traps** the agents cannot know: the relevant `docs/MISTAKES.md`
  entries, sweeps and gates their change will trip, environment quirks. Put
  them in the brief, not in a follow-up.
- **Draw the boundary**: what this ticket deliberately does not build, and
  where each deferred thing is recorded.

Cut the ticket branch named in the ticket's `**Branch:**` field, from the
current epic branch.

## 2. Test author (red)

Spawn `test-author` with the work order. It reads the ticket and spec
*directly* — never only your paraphrase; your framing propagating unexamined
into the tests is this workflow's known failure mode. It has no shell and a
hook denies it the implementation; only it may write under `tests/`. Require
of it:

- Every test's docstring names the mutation it must kill, near-misses
  included.
- **Boundary tests in pairs** — both directions of any accepted/refused line.
  The round-3 lesson: a prediction about *which* side holds the hole is often
  wrong, and two-directional tests catch the miss for free.
- New test machinery ships with **must-be-green control tests**, and the rule
  "a red control means the tests are broken, not the code".
- A manifest (scratchpad file): per test, the mutation and predicted colour.
  Predictions are hypotheses the runs check, not facts.
- If the ticket does not say enough to write a test without inventing an
  interface, that is a ticket defect — it reports it; you stop and fix the
  ticket.

Run `ruff format` and `ruff check` on its output yourself (it has no shell — it
cannot format what it writes, and an unformatted test file reddens CI's `ruff
format --check` gate). Have `verifier` run the suite **and `ruff format
--check`**: every red must be behavioral (assertion), never an import or fixture
error, the red/green split must match the manifest, and the tree must be
format-clean. Divergence goes back to the author; a format miss you fix yourself
before committing. Then commit the tests alone, subject
`e<N>/<slug>: <what>, tests first and red`.

## 3. Implementer (green)

Spawn `implementer` with the work order, the manifest path, and the settled
rulings restated (pre-arbitrate the objection spots you can foresee — it
prevents churn). Its first act is confirming the reds itself, controls first.
`tests/**` is read-only for it (a hook enforces this): a test it believes
wrong gets `docs/disputes/<TICKET>-NN.md` per `docs/disputes/README.md` and a
stop on that item while everything independent proceeds.

It verifies its own work — the named suites, `ruff`, `mypy`, `alembic check`
where schema moved — and commits in small steps, behavior separate from
refactors and from documentation, appending each attempt to
`docs/tickets/e0/.attempts/<TICKET>.md`. For a second attempt within the
ticket, `SendMessage` the same agent rather than spawning fresh — it remembers
what it tried. Never edit the tree while it works in it.

## 4. Dispute, if one happens

**You arbitrate.** Read the objection, the test, and the governing spec
section; when the question is about behavior, run it. Rule on sources, never
on argument quality. Three outcomes: the test is wrong (test-author fixes it
with your ruling); the implementer is wrong (send the *reasoning*, not an
order); the spec is silent (**stop and surface to Todd** — this produces a
spec edit or an ADR, and it is the reason the loop exists). Record the ruling
in the dispute file.

## 5. Verify (proven, not reported)

Spawn `verifier`: fresh full-suite runs with exact totals, then the mutation
battery from the manifest. No green is believed on its author's word. A
survivor is a decision for you — cover it, or record it as named residue with
the reason; never silently drop it. Commit before any battery runs.

## 6. Security review (fresh context)

Spawn `app-security` with the branch, the diff range against the epic branch
(**name the base — the default scoping is wrong on ticket branches**), and the
instruction to form its view of the diff *before* reading the ticket. Tell it
"Nothing found" is an allowed answer that must show what it checked. List the
ticket's recorded decisions so it can tell a decision from an oversight — with
standing to challenge any decision it judges unsafe.

Findings get a fix round: **declare the stopping rule before the round starts**
(typically: tests-first fixes, one re-verification, targeted re-mutations, no
further round unless something is red or a HIGH appears), then hold to it and
record rule and residue in the PR body. A fix round has the defect density of
the original work; the round's fixes get verified the same way the original
did.

## 7. Finish

- Record-correcting edits (ADR amendments, MISTAKES bumps, docstrings the
  change falsified) land as the last content commits, after the code stops
  moving.
- Any construction decision the spec does not answer gets its ADR in this PR.
- Remove any CI tolerance this ticket owns per its acceptance criteria.
- Push; open the PR into the epic branch: the ticket, the §14.2 items covered,
  the security findings and resolutions, the arbitrations, and everything
  deliberately deferred with where it is recorded.
- **Then stop. Do not merge.** Todd's written approval in conversation is the
  only merge trigger.

## Light lane

For tickets whose header says `**Lane:** light`. Step 1 runs in full — a
lighter loop is not a lighter brief; the work order still settles decisions,
names traps, and draws the boundary. Then:

- Spawn `builder` with the work order. It writes implementation and ordinary
  tests together: unit and integration tests asserting the acceptance
  criteria, house style, no manifest, no mutation-naming docstrings, no
  red-first commit ordering. The standing rules hold with no exceptions —
  nothing skipped or xfailed to green, the §4.1 suite untouched, gate
  tolerances moved only where the ticket owns the flip. It commits in small
  steps and appends attempts to the epic's `.attempts/<TICKET>.md`.
- Spawn `verifier` for one fresh pass: full suite with exact totals, `ruff
  format --check`, `ruff check`, `mypy`, `alembic check` where schema moved.
  No battery. No green is believed on the builder's word in this lane either.
- Steps 6 (security review) and 7 (finish) are identical to the heavy lane.

If a ticket spans sittings, resume the session (`claude --resume`) rather than
starting fresh — the warm implementer's reasoning survives with it; the
attempt log carries only the conclusions.
