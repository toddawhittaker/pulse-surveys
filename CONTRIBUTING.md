# Contributing

This repository uses a three-tier branch model. It exists so that `main` always
reflects reviewed, mergeable work, and so that each epic accumulates its seams
in one place before it lands.

## The three tiers

```
main                     protected; release history
  └── epic/e0-foundations        one long-lived branch per epic (SPEC §14.3)
        ├── e0/compose-stack     one short-lived branch per ticket seam
        ├── e0/core-schema
        └── e0/mock-lms
```

**`main` is protected.** Never commit to it, never merge into it locally, never
force-push anything to it. Every change reaches `main` through a pull request.

**Epic branches** are long-lived, one per epic in [SPEC §14.3](docs/SPEC.md),
named `epic/e<N>-<kebab-title>`. They are cut from `main` and merge back into
`main` by pull request when the epic is done.

**Seam branches** are short-lived, one per ticket seam listed under an epic in
§14.3, named `e<N>/<kebab-seam>`. They are cut from their epic branch and merge
back into that epic branch by pull request.

Seam branches merge into their epic branch by pull request. Epic branches merge
into `main` by pull request. There are no exceptions and no direct merges in
either direction.

## Epic branch names

| Epic | Branch |
|---|---|
| E0 — Foundations | `epic/e0-foundations` |
| E1 — Entering the app ⚠ | `epic/e1-entering-the-app` |
| E2 — Weekly survey & validity | `epic/e2-weekly-survey-validity` |
| E3 — Grade passback | `epic/e3-grade-passback` |
| E4 — Instructor Monday report | `epic/e4-instructor-monday-report` |
| E5 — Benchmarks & comparison sets | `epic/e5-benchmarks-comparison-sets` |
| E6 — Moderation & exclusions | `epic/e6-moderation-exclusions` |
| E7 — Response loop | `epic/e7-response-loop` |
| E8 — Student loop closure | `epic/e8-student-loop-closure` |
| E9 — Leadership hierarchy & roll-ups ⚠ | `epic/e9-leadership-rollups` |
| E10 — Care queue & safety ⚠ | `epic/e10-care-queue-safety` |
| E11 — Admin console & observability | `epic/e11-admin-console-observability` |
| E12 — Notifications | `epic/e12-notifications` |
| E13 — Hardening & release ⚠ | `epic/e13-hardening-release` |

Seam names come from the *Ticket seams* line under each epic in §14.3. E0's
seams, for example, are `e0/repo-ci`, `e0/compose-stack`, `e0/core-schema`,
`e0/mock-lms`, `e0/mock-idp`, `e0/ai-gateway-shell`, `e0/authz-skeleton`, and
`e0/seed-script`.

⚠ marks epics that additionally require line-by-line human review of the
security-relevant diff.

## Workflow for a unit of work

1. **Confirm the epic branch.** Check which epic the work belongs to. If its
   branch does not exist, create it from `main`:

   ```bash
   git fetch origin
   git checkout -b epic/e1-entering-the-app origin/main
   git push -u origin epic/e1-entering-the-app
   ```

2. **Cut the seam branch** from the epic branch:

   ```bash
   git checkout epic/e1-entering-the-app
   git pull
   git checkout -b e1/launch-flow
   ```

3. **Commit in small, coherent steps.** Each commit does one thing and its
   subject line names the seam:

   ```
   e1/launch-flow: validate state and nonce on LTI launch
   ```

4. **Open a pull request into the epic branch** when the seam is done. The
   template in `.github/pull_request_template.md` asks for the seam, the §14.2
   definition-of-done items covered, and anything deliberately deferred. Fill
   all three in — the deferred list is how the next seam knows what it inherits.

   ```bash
   gh pr create --base epic/e1-entering-the-app --fill
   ```

5. **Stop there** and wait for the repository owner. Do not merge because the
   seam looks finished to you.

## Who may merge what

Merge authority splits by target branch.

| Pull request | Who merges |
|---|---|
| seam branch → epic branch | the owner, or an agent **after** the owner approves it in writing |
| epic branch → `main` | the owner, always, without exception |

An agent may never merge an epic branch into `main`. An agent may merge its own
seam pull request into an epic branch, but only once the owner has approved it
in conversation — the owner's approval is the trigger, never the agent's own
judgment that the work is done.

The reasoning: `main` is the branch worth protecting, and an epic landing there
is the decision that deserves a human every time. A seam landing on an epic
branch is a smaller, more reversible step, and it is still gated on a human
saying yes. What the rule forbids is an agent deciding on its own that
something is ready.

## Rules that hold for everyone, including AI agents

- Never use an admin override to bypass a protection rule.
- Never mark a pull request ready for review while CI is failing.
- Never force-push to `main` or to an epic branch. Force-pushing your own seam
  branch before review is fine.
- If a seam turns out to belong to a different epic, close the pull request and
  re-cut the branch. Do not retarget across epics.

## CI

`.github/workflows/ci.yml` runs on every pull request and on pushes to epic
branches. `make ci` runs the same gates locally, in the same order, so you can
catch a failure before you push.

| Stage | Gates |
|---|---|
| Fast | CI checker self-test, ruff check and format, mypy, tsc, eslint, migration drift |
| Test | pytest unit and integration with coverage, the §4.1 invariant suite, Playwright e2e, AI eval floors |
| Build | all Docker images, Compose health on api/worker/beat, frontend production build, bundle budget |
| Supply chain | pip-audit, npm audit, MIT license compatibility |

Fast gates run first and everything else waits on them.

Most of the tree does not exist yet, so most jobs currently detect absence and
pass with a note naming the seam that will make them enforcing. Landing that
seam includes removing its tolerance — a seam that adds tests but leaves the
test gate tolerant has not finished.

Two rules worth stating outright. A failing test is never fixed by skipping,
xfailing, or deleting it; if the test is wrong, fix it in its own commit and say
why in the pull request. And an eval floor is never lowered to get a gate to
pass — floors move only in a pull request whose purpose is moving them.

## Secrets

Local secrets live in `.env`, which is gitignored. Its committed counterpart
`.env.example` lists variable names with obviously-fake placeholder values and
never a real credential. A pull request that adds a configuration variable adds
its name to `.env.example` in the same change.

Nobody — contributor or AI agent — creates, reads, modifies, or echoes a
repository or environment secret as a side effect of doing other work, and no
pull request adds a `secrets.*` reference to a workflow without the repository
owner agreeing to it first. Credentials never appear in commit messages, pull
request bodies, test fixtures, seed data, or logs.

## Definition of done

Every epic — and by extension every seam that composes it — carries the five
conditions in [SPEC §14.2](docs/SPEC.md): tests land with the feature, AI evals
are updated when a model task changes, a separate agent runs the adversarial
security review, accessibility is handled in-slice rather than deferred to E13,
and docs cover anything an operator or developer needs. The pull request
template restates these as a checklist.

Testing and security review are not separate epics. They are part of finishing
each one.
