---
name: build-ticket
description: Build one ticket through the lane its header names - heavy rides the orchestrated tests-first loop (test-author writes red, builder-heavy confirms the reds and turns them green, and a ⚠ ticket adds the verifier's mutation battery), light rides builder-light, which writes code and tests together, checked by CI; both get one fresh-context security review on the final head and merge through the merger agent. Use when the user says "build E0-05", "build ticket 3", or asks to implement a ticket from docs/tickets/. Cuts the ticket branch and ends with the PR merged into its epic branch.
---

# Build a ticket

Drives one ticket from `docs/tickets/` to a pull request merged into its epic
branch. **You are the
orchestrator: you design, brief, arbitrate, and verify-by-delegation. The
subagents build.** Your brief is where the leverage is — a design decision
settled in the brief stays settled; one left open comes back as a review
finding or a wasted round.

`$1` is the ticket ID (`E0-05`) or a loose ordinal ("ticket 3" means `E0-03`).
If ambiguous, ask — building the wrong ticket wastes a whole loop.

## 0. The lane

Read the ticket header's `**Lane:**` field first. A missing field, a ⚠ in
that field, or doubt means **heavy**. A ⚠ on the epic alone does not; the
path table decides — steps 1 through 7 below.
`**Lane:** light` means step 1, then the **Light lane** section at the end of
this file in place of steps 2–5, then steps 6 and 7 unchanged. If mid-build
the diff reaches a surface CLAUDE.md's lane rule names as heavy (the path
table at .claude/heavy-lane-paths.md), stop and re-lane: what exists becomes
the heavy lane's starting material, the tests get a `test-author` pass before
they are trusted, and the PR records the switch.

## 1. Plan, before any agent

Read the ticket, its epic README row, and the spec sections the ticket names.
Check its dependencies actually merged into the epic branch; if not, stop and
say so.

Check the ticket's planned files against the merger's refused paths
(`.claude/agents/merger.md`: `package.json`, `pyproject.toml`, `.github/`,
`.claude/` and the rest). A ticket that must change one cannot land through
the merger. Split that change into a small `process/` PR for the owner first,
and build the rest of the ticket on top of it once it reaches the epic branch.

Then write the work order — this is the step that used to be skipped and used
to cost two extra rounds:

- **Settle every design decision the ticket leaves open**: module homes,
  contracts between components, exact identifiers tests and code must agree on
  (testids, setting names, error shapes), what is refused vs ignored vs
  defaulted, and any test seam the machinery needs. Verify file:line facts
  against the tree yourself before putting them in a brief — stale line
  numbers are the most common brief defect.
- **Name the traps** the agents cannot know: sweeps and gates their change
  will trip, environment quirks, and the `docs/MISTAKES.md` entries that
  apply to this ticket, cited by number with their rule. You read that file
  whole once per epic; a subagent does not, so its brief carries only the
  entries that apply. Put them in the brief, not in a follow-up.
- **Name the shared files.** The epic breakdown lists the files this ticket
  shares with others built in parallel. Expect a merge conflict on them;
  step 6 says when to resolve it.
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
format --check` gate). Then commit the tests alone, subject
`e<N>/<slug>: <what>, tests first and red`. No separate verifier pass confirms
the reds; the builder-heavy's first act in step 3 is that check.

## 3. builder-heavy (green)

Spawn `builder-heavy` with the work order, the manifest path, and the settled
rulings restated (pre-arbitrate the objection spots you can foresee — it
prevents churn). Its first act is confirming the reds itself, controls first:
every red is behavioral (an assertion), never an import or fixture error, and
the red/green split matches the manifest. It reports any divergence before
writing code; that goes back to the test author.
`tests/**` is read-only for it (a hook enforces this): a test it believes
wrong gets `docs/disputes/<TICKET>-NN.md` per `docs/disputes/README.md` and a
stop on that item while everything independent proceeds.

It verifies its own work — the named suites, `ruff`, `mypy`, `alembic check`
where schema moved — and commits in small steps, behavior separate from
refactors and from documentation, appending each attempt to
`docs/tickets/e0/.attempts/<TICKET>.md`. For a second attempt within the
ticket, `SendMessage` the same agent rather than spawning fresh — it remembers
what it tried. Never edit the tree while it works in it.

Once it reports green, push the ticket branch and open the pull request into
the epic branch **as a draft**, right here — not at step 7. CI does not run on
a ticket branch until a pull request exists (it triggers on `pull_request` and
on push to `epic/**` only), so the draft PR is what gives CI a run on the
head. Step 7 no longer opens the PR; it updates the body and marks the draft
ready.

## 4. Dispute, if one happens

**You arbitrate.** Read the objection, the test, and the governing spec
section; when the question is about behavior, run it. Rule on sources, never
on argument quality. Three outcomes: the test is wrong (test-author fixes it
with your ruling); the builder-heavy is wrong (send the *reasoning*, not an
order); the spec is silent (**stop and surface to Todd** — this produces a
spec edit or an ADR, and it is the reason the loop exists). Record the ruling
in the dispute file.

## 5. Verify (⚠ tickets only)

A plain heavy ticket has no verifier step: tests first plus CI's green run on
the head, which the merger checks, is the verification. Go to step 6.

A ticket with a ⚠ in its `Lane:` field spawns `verifier`: confirm CI's green
run on this exact commit (totals cross-checked, not re-run locally), then the
mutation battery from the manifest, scoped to each row's named killer test per
verifier.md. No green is believed on its author's word. A survivor is a
decision for you — cover it, or record it as named residue with the reason;
never silently drop it. Commit before any battery runs. The merger needs the
battery tied to the final head: either it ran on that commit, or every later
commit is listed with the targeted re-mutation that covered it (step 6).

## 6. Security review (fresh context, once)

The review runs **once, after the last code push**, on the final head SHA. A
review of an earlier head is stale, and the merger refuses it. So before the
review, merge the current epic branch into the ticket branch if the two
conflict (shared files from step 1 are the usual cause): `git merge` and an
ordinary push, never a rebase or force-push.

Run the reviewers `review-pr` picks from the diff, **in parallel**: the
security pass from its path table, plus `privacy-authz` when its paths match.
Brief each with the branch, the diff range against the epic branch (**name the
base — the default scoping is wrong on ticket branches**), and the instruction
to form its view of the diff *before* reading the ticket. Tell it "Nothing
found" is an allowed answer that must show what it checked. List the ticket's
recorded decisions so it can tell a decision from an oversight — with standing
to challenge any decision it judges unsafe.

Findings get one fix round, and its stopping rule is fixed in advance:

- Fix the findings (tests first on a heavy ticket), run only the targeted
  tests locally, and push once.
- One re-check pass runs on the new head, with the same reviewers. Then the
  loop stops.
- A HIGH found in the re-check is fixed, and that fix gets one more re-check
  on its new head. Nothing else reopens the loop: a MED or LOW found in the
  re-check is resolved by recording it in the PR body as accepted residue,
  with the reason, not by another push.
- On a ⚠ ticket, the round also runs targeted re-mutations of what it touched,
  including any original battery rows whose subject code it modified — never
  a blind re-run of the whole battery.
- The PR body states this stopping rule and the residue left by it.

A fix round has the defect density of the original work, which is why the
re-check exists; the stopping rule is what keeps it from becoming unbounded
re-polish of work the review already accepted.

If the epic branch moves after the review and the ticket branch now
conflicts, resolve it the same way (merge the epic branch in, push). That
push is a code push: it gets one re-check pass on the new head, recorded like
a fix round's.

## 7. Finish

- Record-correcting edits (ADR amendments, MISTAKES bumps, docstrings the
  change falsified) land as the last content commits, after the code stops
  moving.
- Any construction decision the spec does not answer gets its ADR in this PR.
- Remove any CI tolerance this ticket owns per its acceptance criteria.
- Push the final commits; update the draft PR's body: the ticket, the §14.2
  items covered, the security findings and resolutions, the arbitrations, and
  everything deliberately deferred with where it is recorded, and the fix
  round's stopping rule. Every review and battery the body cites names the
  final head SHA; the merger refuses a record tied to an earlier commit. A ⚠
  ticket's body also records the verifier's battery result and the commit it
  ran on, plus any targeted re-mutations after it. Mark it ready for review.
- **Then merge it through the merger agent** once the CLAUDE.md merge
  conditions hold. This applies to both lanes and to ⚠ epics. No one
  approves a ticket PR; Todd reviews at the epic boundary.

## Light lane

For tickets whose header says `**Lane:** light`. Step 1 runs in full — a
lighter loop is not a lighter brief; the work order still settles decisions,
names traps, and draws the boundary. Then:

- Spawn `builder-light` with the work order. It writes implementation and ordinary
  tests together: unit and integration tests asserting the acceptance
  criteria, house style, no manifest, no mutation-naming docstrings, no
  red-first commit ordering. The standing rules hold with no exceptions —
  nothing skipped or xfailed to green, the §4.1 suite untouched, gate
  tolerances moved only where the ticket owns the flip. It commits in small
  steps and appends attempts to the epic's `.attempts/<TICKET>.md`.
- Once it reports green, push the ticket branch and open the pull request into
  the epic branch as a draft — same reason as the heavy lane: no CI run
  exists on a ticket branch until a pull request does.
- No verifier pass. CI runs the same gates (`ruff format --check`, `ruff
  check`, `mypy`, migration drift, the tests), and the merger checks CI's
  green run on the exact head commit. That is the check that does not take
  the builder-light's word. Before calling the build done, run `ruff check` and
  `mypy` on the builder-light's work yourself; a builder-light's "lint passes" has been
  wrong before.
- Steps 6 (security review) and 7 (finish) are identical to the heavy lane.

If a ticket spans sittings, resume the session (`claude --resume`) rather than
starting fresh — the warm builder-heavy's reasoning survives with it; the
attempt log carries only the conclusions.
