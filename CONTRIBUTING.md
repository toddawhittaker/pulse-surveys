# Contributing

This repository uses a three-tier branch model. It exists so that `main` always
reflects reviewed, mergeable work, and so that each epic accumulates its tickets
in one place before it lands.

> **`CLAUDE.md` is authoritative on process.** This file is the same rules
> written for humans, with more explanation and examples. Where the two
> disagree, `CLAUDE.md` wins and this file is the bug — it is the copy that
> drifts, because it is the one nobody's tooling reads.

## The three tiers

```
main                     protected; release history
  └── epic/e0-foundations           one long-lived branch per epic (SPEC §14.3)
        ├── e0/compose-stack        one short-lived branch per ticket
        ├── e0/org-containment-schema
        ├── e0/mock-lms-launch
        └── process/orchestrator-rewire   process and tooling, not a ticket
```

**`main` is protected.** Never commit to it, never merge into it locally, never
force-push anything to it. Every change reaches `main` through a pull request.

**Epic branches** are long-lived, one per epic in [SPEC §14.3](docs/SPEC.md),
named `epic/e<N>-<kebab-title>`. They are cut from `main` and merge back into
`main` by pull request when the epic is done.

**Ticket branches** are short-lived, one per ticket listed under an epic in
§14.3, named `e<N>/<kebab-slug>`. They are cut from their epic branch and merge
back into that epic branch by pull request.

**Process branches** carry changes to how the work is done rather than to the
product: `CLAUDE.md`, this file, `.claude/`, the CI workflow. They are named
`process/<kebab-slug>`, they are not tickets and have no number, and they go
through the same pull-request path as everything else — cut from the branch they
will merge back into, reviewed, merged by pull request. In E0 that has meant the
epic branch: `#59`, `#60` and `#63` all merged into `epic/e0-foundations`.

Ticket and process branches merge into their epic branch by pull request. Epic
branches merge into `main` by pull request. Nothing reaches `main` any other way,
and there are no direct merges in either direction.

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

Ticket branch names come from the *Ticket breakdown* line under each epic in
§14.3. Where an epic has been decomposed into numbered tickets under
`docs/tickets/`, those ticket branch names win over the list in the spec —
[`docs/tickets/e0/README.md`](docs/tickets/e0/README.md) is the build order for
E0 and names a branch for each of its tickets.

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

2. **Cut the ticket branch** from the epic branch:

   ```bash
   git checkout epic/e1-entering-the-app
   git pull
   git checkout -b e1/launch-flow
   ```

3. **Commit in small, coherent steps.** Each commit does one thing and its
   subject line names the ticket:

   ```
   e1/launch-flow: validate state and nonce on LTI launch
   ```

4. **Open a pull request into the epic branch** when the ticket is done. The
   template in `.github/pull_request_template.md` asks for the ticket, the §14.2
   definition-of-done items covered, and anything deliberately deferred. Fill
   all three in — the deferred list is how the next ticket knows what it inherits.

   ```bash
   gh pr create --base epic/e1-entering-the-app --fill
   ```

5. **Stop there** and wait for the repository owner. Do not merge because the
   ticket looks finished to you.

## Who may merge what

Merge authority splits by target branch.

| Pull request | Who merges |
|---|---|
| ticket branch → epic branch | the owner, or an agent **after** the owner approves it in writing |
| epic branch → `main` | the owner, always, without exception |

An agent may never merge an epic branch into `main`. An agent may merge its own
ticket pull request into an epic branch, but only once the owner has approved it
in conversation — the owner's approval is the trigger, never the agent's own
judgment that the work is done.

The reasoning: `main` is the branch worth protecting, and an epic landing there
is the decision that deserves a human every time. A ticket landing on an epic
branch is a smaller, more reversible step, and it is still gated on a human
saying yes. What the rule forbids is an agent deciding on its own that
something is ready.

## Rules that hold for everyone, including AI agents

- Never use an admin override to bypass a protection rule.
- Never mark a pull request ready for review while CI is failing.
- Never force-push to `main` or to an epic branch. Force-pushing your own ticket
  branch before review is fine.
- If a ticket turns out to belong to a different epic, close the pull request and
  re-cut the branch. Do not retarget across epics.

## CI

`.github/workflows/ci.yml` runs on every pull request and on pushes to epic
branches. `make ci` runs the same gates locally, in the same order, so you can
catch a failure before you push.

| Stage | Gates |
|---|---|
| Fast | CI checker self-test, ruff check and format, mypy, tsc, eslint, migration drift |
| Test | pytest unit and integration with coverage, the §4.1 invariant suite, Playwright e2e, AI eval floors |
| Build | all Docker images, Compose health on api/worker/beat/mock-lms/mock-idp, frontend production build, bundle budget |
| Supply chain | pip-audit, npm audit, MIT license compatibility |

Fast gates run first and everything else waits on them.

A job whose subject does not exist yet detects the absence and passes with a
note naming the ticket that will make it enforcing. Landing that ticket includes
removing its tolerance — a ticket that adds tests but leaves the test gate
tolerant has not finished. Most of them have now tightened. **The Playwright e2e
job became enforcing with E0-18 (PR #61, 2026-08-21)** — it runs the suite on
every diff that is not wholly inert documentation, and an empty `tests/e2e` now
fails loudly instead of passing with a note. What remains tolerant is the AI eval
floors, which wait for E2's first eval set, and the four frontend gates (`tsc`,
`eslint`, production build, bundle budget), which wait for the frontend scaffold
in E1. The E0 build order has the full table.

Two rules worth stating outright. A failing test is never fixed by skipping,
xfailing, or deleting it; if the test is wrong, fix it in its own commit and say
why in the pull request. And an eval floor is never lowered to get a gate to
pass — floors move only in a pull request whose purpose is moving them.

## Read paths go through `views_sql/`

Instructor and leadership screens read from the views in
`backend/app/views_sql/`, never from the base tables. That is not a style rule:
the connection those screens run on holds no privilege of any kind on
`user_identity`, so a hand-written join that needs a name is refused by Postgres
rather than by a reviewer (SPEC §8,
[ADR 0001](docs/adr/0001-identity-separation-by-database-role.md)). The views are
what make that survivable — they are read with their *owner's* privileges, so
they can expose section membership and counts from tables the reader cannot
touch. `backend/app/views_sql/queries.py` holds a typed helper per view; reach
for one of those before writing SQL.

**Adding a view means adding an invariant test.** A view runs with its owner's
privileges, so the grant model does not protect it: a view that reads an identity
column hands that column to everyone who may read the view. Ship the SQL as a new
versioned file in `views_sql/`
([ADR 0041](docs/adr/0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md)
— never edit one a migration already executes), schema-qualify every relation it
names, and add a `@pytest.mark.invariant` test asserting the §4.1 rule the new
view is subject to. The structural sweep in
`tests/integration/test_identity_column_marker.py` already fails on a view that
reads a marked identity column, including through an alias, so that much you get
for free; what it cannot see is a §4.1 rule nobody has stated yet. From E0-10 the
invariant suite runs with no `--allow-empty`, so a skipped or uncollected
invariant is a build failure rather than a green checkmark.

## Architecture decision records

When a construction decision is not answered by [`docs/SPEC.md`](docs/SPEC.md)
and a reasonable engineer might choose differently, write
`docs/adr/NNNN-slug.md` in the same pull request: context, decision,
alternatives rejected and why, consequences. Under a page.

Do not write one restating something the spec already decides — link to the spec
section instead. If a decision contradicts the spec, an ADR is not sufficient:
raise it, and update the spec.

[`docs/adr/README.md`](docs/adr/README.md) has the format and the index.

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

Every epic — and by extension every ticket that composes it — carries the five
conditions in [SPEC §14.2](docs/SPEC.md): tests land with the feature, AI evals
are updated when a model task changes, a separate agent runs the adversarial
security review, accessibility is handled in-slice rather than deferred to E13,
and docs cover anything an operator or developer needs. The pull request
template restates these as a checklist.

Testing and security review are not separate epics. They are part of finishing
each one.
