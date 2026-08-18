# Pulse Surveys — process

This file holds process only: how work is done in this repo. It does not hold
feature decisions, system behavior, rationale, status, or history.

- What the system does → `docs/SPEC.md`
- Why a construction choice was made → `docs/adr/`
- What is being built next → `docs/tickets/`
- How it should look → `docs/DESIGN_BRIEF.md`, `design/`
- What has already gone wrong here → `docs/MISTAKES.md`, read whole before you
  start; it is the rules, and each links to its incident in `docs/mistakes/`

Before adding a line here, ask whether it would still be true if the process
changed. If yes, it belongs elsewhere. Do not append feature decisions, status,
or changelog entries to this file. Under 150 lines; if it needs to grow,
something in it belongs somewhere else.

**Active epic:** E0 — Foundations. Tickets: `docs/tickets/e0/README.md`.

## Read before you start

On what the system does, the spec governs: where `docs/SPEC.md` and
`docs/DESIGN_BRIEF.md` disagree, the spec wins, and the brief governs anything
the spec does not restate. On how work is done, **this file governs**: where
`CONTRIBUTING.md` disagrees, this file wins — it is the same rules written for
humans, and it is the copy that drifts. If your work contradicts the spec, that
is not yours to resolve alone — raise it and update the spec.

Read the relevant section before touching the code it governs. Do not work from
a summary of it, including this file:

| Before touching | Read |
|---|---|
| any read path, view, or export | §4 and §4.1 — the visibility invariants |
| roles, purview, scoping, `authz.py` | §2.1 — assignments, supervision graph, purview |
| terms, section codes, week axes | §2.2 |
| anything the Care role can reach | §6.2 |
| any model call, prompt, or contract | §7.4 — the single-shot boundary |
| where a module goes | §13 — use an existing module; add one only when nothing fits |
| any UI | `docs/DESIGN_BRIEF.md`, `design/tokens.css`, and §7.6 |
| something someone already built | `docs/adr/` — how it was built and why |

## Branch and pull request discipline

`main` is protected. Never commit to it, never merge into it locally, never
force-push anything anywhere. Every change reaches `main` through a pull
request, and so does every change to an epic branch.

Three tiers. `main` holds reviewed work. One long-lived **epic branch** per epic
in SPEC §14.3, named `epic/e<N>-<kebab-title>`, cut from `main`. One short-lived
**ticket branch** per item in that epic's breakdown, named `e<N>/<kebab-slug>`,
cut from its epic branch. Ticket branches merge into their epic branch by pull
request; epic branches merge into `main` by pull request. No exceptions, no
direct merges either way. `CONTRIBUTING.md` has the branch name tables.

For every unit of work, in order:

1. Confirm which epic branch the work belongs to. Create it from `main` if it
   does not exist yet.
2. Cut a ticket branch from that epic branch. Never work directly on the epic
   branch.
3. Commit in small, coherent steps. The subject line names the ticket:
   `e1/launch-flow: validate state and nonce on LTI launch`.
4. Open a pull request into the epic branch when the ticket is done. Use the
   template: the ticket, the §14.2 definition-of-done items covered, and anything
   deliberately deferred.
5. Stop and wait for Todd. Do not merge on your own judgment that the ticket looks
   finished.

Merge authority splits by target branch. **Never merge an epic branch into
`main`** — that is Todd's call, always, without exception. You may merge a ticket
pull request into its epic branch, but only after Todd has approved it in
writing in the conversation; his approval is the trigger, never your own
assessment. Never use an admin override to bypass a protection rule. Never merge
anything while CI is failing. Never retarget a pull request across epics — close
it and re-cut the branch.

## CI and build discipline

CI is what makes the §14.2 definition of done enforceable instead of
aspirational. Treat a red pipeline as information, never as an obstacle.

**Never merge or mark a pull request ready with red CI.** Not "it's unrelated,"
not "it passes locally." Run `make ci` before pushing; it runs the same gates in
the same order as `.github/workflows/ci.yml`. When the two disagree, the
workflow is right and the Makefile is the bug.

**Never skip, xfail, mark flaky, or delete a failing test to make CI pass.** A
failing test is either finding a real defect or is itself wrong. If the test is
wrong, fix the test in its own commit, separate from the change that provoked
it, and say in the pull request why the old assertion was incorrect. Deleting a
red test and reporting green is a false report about the state of the system.

**The §4.1 invariant suite may never be skipped.** CI runs it in an isolated
pass and treats a skip, an xfail, or an empty collection as a failure, because
in a green checkmark those are indistinguishable from a passing assertion.
`scripts/ci/check_invariants.py` enforces this.

**Never weaken an eval floor to get a gate to pass.** Floors move only in a
deliberate pull request whose subject is moving them and whose body says why the
new number is right. The threat and self-harm recall floor (§9.3) is a hard
gate; lowering it is a safety decision, not a build fix, and it is Todd's call.

**Every pull request gets `/security-review` in a separate session before it is
marked ready** (§14.2 item 3). Record what it found and how each finding was
resolved in the pull request body. On a ⚠ epic it supplements line-by-line human
review of the security-relevant diff; it never replaces it.

**Pin dependency versions and commit lockfiles.** No floating ranges, no
unpinned tool versions in CI. Dependabot proposes upgrades through the same
gates as anything else.

**Do not weaken a gate to get past it.** An ignore rule, an exclusion, a
`continue-on-error`, or a raised budget changes what the project guarantees, and
belongs in its own pull request saying what coverage was given up and why. On
the tolerance flags in `ci.yml`, see ADR 0002.

## Architecture decision records

When a construction decision is **not answered by `docs/SPEC.md`** and a
reasonable engineer might choose differently, write `docs/adr/NNNN-slug.md` **in
the same pull request as the decision**. Four sections, under a page: context,
decision, alternatives rejected and why, consequences.

- **Never write an ADR restating something the spec already decides.** Link to
  the spec section instead.
- **If a decision contradicts the spec, an ADR is not sufficient.** Raise it, and
  update the spec. A record of having gone around the spec is not the same as
  the spec being right.
- The test is both halves: the spec is silent, *and* the choice is contestable.
  Picking a JSON library needs no ADR. Picking how identity separation is
  enforced does.
- Number sequentially, never reuse a number, never renumber. A superseded ADR
  stays in place with a line pointing at its replacement.

## Secrets

Never create, read, modify, or echo a repository secret or an environment
secret. Never add a secret reference to a workflow without asking first — a new
`secrets.*` expression, a new environment binding, or widening an existing one.
Ask, then wait for an answer; do not add it provisionally.

Local secrets live in `.env`, which is gitignored and must stay that way.
`.env.example` carries variable *names* and obviously-fake placeholders, never a
real credential and never a value copied from a working `.env`. A ticket adding a
configuration variable adds its name to `.env.example` in the same pull request.

Do not print the contents of `.env`, paste a credential into a commit message or
a pull request body, or write one into a test fixture, a seed script, or a log
line. If a real secret is needed to run something, say what is needed and let
Todd supply it.
