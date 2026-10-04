# Pulse Surveys — process

This file holds process only: how work is done in this repo. It does not hold
feature decisions, system behavior, rationale, status, or history.

- What the system does → `docs/SPEC.md`
- Why a construction choice was made → `docs/adr/`
- What is being built next → `docs/tickets/`
- How it should look → `docs/DESIGN_BRIEF.md`, `design/`
- What has already gone wrong here → `docs/MISTAKES.md`, the rules (incidents
  in `docs/mistakes/`); read whole once per epic, cited by number in each brief

Before adding a line, ask whether it would still be true if the process
changed; if yes, it belongs elsewhere. Under 150 lines.

**Active epic:** E5.1 — Main review fixes. Tickets: `docs/tickets/e5.1/README.md` (on `epic/e5.1-main-review-fixes`).

## Read before you start

On what the system does, `docs/SPEC.md` governs; the brief governs only what
the spec does not restate. On how work is done, **this file governs** — where
`CONTRIBUTING.md` (the same rules written for humans, and the copy that drifts)
disagrees, this file wins. If your work contradicts the spec, that is not yours
to resolve alone — raise it and update the spec.

Search with the `Grep` tool or `rg`, never `grep -r`: it reads the ignored
`.venv`, `node_modules`, and `.claude/worktrees` and floods the context.

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
direct merges either way. Process and tooling changes (this file, `.claude/`,
CI) ride a `process/<kebab-slug>` branch through the same PR path;
`CONTRIBUTING.md` has the branch name tables.

For every unit of work, in order: confirm the epic branch (create from `main`
if absent); cut the ticket branch from it — never work on the epic branch;
commit in small coherent steps, subject naming the ticket (`e1/launch-flow:
validate state and nonce on LTI launch`); open a PR into the epic branch using
the template; then merge it as the paragraph below says.

**Never merge an epic branch into `main`** — Todd's call, always; he reviews
there, line by line on a ⚠ epic or ⚠ path (SPEC §14.2, §14.3). Every ticket PR, any lane or
epic, merges without him once `.claude/agents/merger.md`'s conditions hold;
only `process/` PRs wait. Never an admin override, a red-CI merge, or a
retargeted PR — close and re-cut.

## How a ticket is built: two lanes

Every ticket's header carries a `**Lane:**` field, set at breakdown time. Heavy
is for security code only, about one ticket in five: the paths in
`.claude/heavy-lane-paths.md`, a ⚠ in the `Lane:` field, or a missing one.
Everything else is light; a ⚠ epic does not make its tickets heavy. Heavy:
`test-author` writes red; builder-heavy confirms the reds, codes to green
without touching a test, and disputes via `docs/disputes/`; a ⚠ ticket adds
`verifier`'s mutation battery. Light: `builder-light` writes code and tests
together. In both, CI's green run, checked by the merger, is the verification. A
light diff reaching a heavy path stops and re-lanes in the PR record.
`architect` designs each epic first: one owning ticket per migration and ADR
number, serial order only where a ticket needs another's code. Tickets may share
files; the breakdown names them, and the second to merge merges in the epic
branch. `explorer` does cheap searches. Mechanics: `.claude/skills/build-ticket`.

## CI and build discipline

CI is what makes the §14.2 definition of done enforceable. A red pipeline is
information, never an obstacle.

**Never merge or mark a pull request ready with red CI.** Not "it's unrelated,"
not "it passes locally." Run `make ci` before pushing; when it disagrees with
`.github/workflows/ci.yml`, the workflow is right and the Makefile is the bug.

**Never skip, xfail, mark flaky, or delete a failing test to make CI pass.** A
failing test is finding a real defect or is itself wrong. If the test is wrong,
fix it in its own commit, separate from the change that provoked it, and say in
the PR why the old assertion was incorrect. Deleting a red test and reporting
green is a false report about the state of the system.

**The §4.1 invariant suite may never be skipped.** CI runs it in an isolated
pass and treats a skip, an xfail, or an empty collection as a failure;
`scripts/ci/check_invariants.py` enforces this.

**Never weaken an eval floor to get a gate to pass.** Floors move only in a
deliberate PR whose subject is moving them. The threat and self-harm recall
floor (§9.3) is a hard gate; lowering it is a safety decision and Todd's call.

**Reviews are tiered.** Each PR's security review runs once, on the head SHA
after the last push: the passes `review-pr` picks from the diff (Sonnet if no
specialist matches), in parallel, diff first. A fix round runs targeted tests,
pushes once, gets one re-check on the new head, and stops (a HIGH there gets one
more); the PR body says so. The epic boundary runs the full Opus battery,
`spec-conformance` and `code-reviewer` included; findings become ticket PRs.

**Pin dependency versions and commit lockfiles.** No floating ranges, no
unpinned tool versions in CI.

**Do not weaken a gate to get past it.** An ignore rule, an exclusion, a
`continue-on-error`, or a raised budget changes what the project guarantees and
belongs in its own PR saying what coverage was given up and why. On the
tolerance flags in `ci.yml`, see ADR 0002.

## Architecture decision records

When a construction decision is **not answered by `docs/SPEC.md`** and a
reasonable engineer might choose differently, write `docs/adr/NNNN-slug.md` **in
the same pull request as the decision**. Four sections, under a page: context,
decision, alternatives rejected and why, consequences.

- **Never restate the spec in an ADR**; link to the section instead.
- **If a decision contradicts the spec, an ADR is not enough.** Update the spec.
- The test is both halves: the spec is silent, *and* the choice is contestable.
- Number sequentially, never reuse a number, never renumber. A superseded ADR
  stays in place with a line pointing at its replacement.

## Secrets

Never create, read, modify, or echo a repository secret or an environment
secret. Never add a secret reference to a workflow — a new `secrets.*`
expression, binding, or widening — without asking first; then wait, do not add
it provisionally.

Local secrets live in `.env`, gitignored and staying that way. `.env.example`
carries variable *names* and obviously-fake placeholders, never a real
credential; a ticket adding a variable adds its name there in the same PR. Do
not print `.env`, paste a credential into a commit or PR body, or write one
into a fixture, seed, or log. If a real secret is needed, say so and let Todd
supply it.
