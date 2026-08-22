# E0-40 — Four gates probe a path that does not exist (Batch I)

**ID:** E0-40
**Branch:** `e0/gate-fidelity`
**Depends on:** E0-18, E0-36 (both merged)

## The findings (epic-boundary exit review, 2026-08-22)

**HIGH.** PR #61 committed the repository's first `package.json`,
`package-lock.json`, and TypeScript (`playwright.config.ts`,
`tests/e2e/*.spec.ts`) — at the repo root. Every Node-facing gate still probes
`frontend/package.json`: the `detect` job's probe (`.github/workflows/ci.yml`
line ~267), the `npm audit` job (working-directory `frontend`, line ~930), the
license scan (~941–963), `tsc`/`eslint` (~367, 372), and the `Makefile`
`lint`/`typecheck`/`audit` branches. All report green over a tree they never
read. This is a live instance of `docs/mistakes/36` — a probe deciding whether
a gate runs answered false over a tree that had the thing. `npm audit` runs
clean at the root today; CI just never calls it.

Three smaller findings ride along because they are the same subject:

- `playwright.config.ts` sets `retries: process.env.CI ? 1 : 0` — a spec that
  fails once and retries green exits zero, so the e2e gate passes over a test
  that failed, against CLAUDE.md's flaky rule, with no ADR.
- `pyproject.toml`'s `testpaths = ["tests/unit", "tests/integration"]` plus
  invariant runners that pass no path means a future `tests/property/`
  invariant file would merge and silently never run; the assertion-scan half
  of the gate counts it, the collection half doesn't, and nothing compares the
  two numbers.
- The `detect` job's `e2e` probe output is emitted and consumed by nothing
  since PR #61 made the e2e gate unconditional (deferred in
  `docs/tickets/e0/.attempts/E0-18.md`; the fidelity test must change in the
  same commit).

## The decisions, settled

1. **The probe tells the truth about where Node code lives.** The `detect`
   output currently named for `frontend/` is split honestly: a `node` probe
   (`[ -f package.json ]`, repo root) gates `npm audit`, the license scan,
   `tsc`, and `eslint`, all running at the repo root; the production-build and
   bundle-budget gates keep waiting on `frontend/package.json`, which is still
   legitimately absent until E1. `Makefile` `lint`/`typecheck`/`audit` follow
   the same split so `make ci` and the workflow agree.
2. **The committed TypeScript gets a toolchain**: a root `tsconfig.json`
   (strict, `noEmit`) covering `playwright.config.ts` and `tests/e2e/`, and an
   eslint flat config over the same files. `typescript`, `eslint`, and
   `typescript-eslint` land in `package.json` **exact-pinned** with the
   lockfile updated — match the pinning style already in `package.json`.
3. **Retries go to zero.** `retries: 0` everywhere; `trace:
   'retain-on-failure'` replaces `on-first-retry` so the debugging artifact
   the retry was buying survives. No ADR — this restores the documented rule
   rather than deciding anything new.
4. **`testpaths = ["tests"]`** — identical collection today (only
   `tests/unit` and `tests/integration` hold Python tests; `tests/e2e` holds
   `.ts` files pytest does not collect), and a new directory is included
   instead of silently dropped. Plus one guard test: the number of unique
   invariant-marked test functions the collector finds under `tests` equals
   the count `scripts/ci/check_invariant_assertions.py tests` reports — the
   two halves of the gate can no longer disagree by a number nobody compares.
5. **The unconsumed `e2e` probe is removed**, with its fidelity test updated
   in the same change (test-author does the test side).
6. **The node gates join the documentation-only short-circuit.** Their E0-38
   exemption was justified by being free (the probe never fired); this ticket
   makes them cost an `npm ci` plus tsc and eslint, so a documentation-only
   diff — which by definition changes no TypeScript and no package manifest —
   short-circuits them exactly as it does the other expensive gates. The
   fidelity test asserts the short-circuit rather than the exemption.
7. **The tsc/eslint job keeps its id and display name** ("Fast · tsc +
   eslint") in this ticket. The display names are what branch protection's
   required-checks list keys on; renaming is deliberately out of scope and
   noted here so nobody reads the stale "frontend" wording as an oversight.
8. **Decisions 3 and 4 get text-level guards**: one test asserting
   `playwright.config.ts` contains `retries: 0` and
   `trace: 'retain-on-failure'`, one asserting `pyproject.toml`'s
   `testpaths` is exactly `["tests"]` — cheap, honest anchors so neither
   silently reverts.

## Scope and acceptance

- `.github/workflows/ci.yml`, `Makefile`: the probe split; audit, license,
  tsc, eslint run at root when root `package.json` exists; `make ci` and the
  workflow agree (the workflow wins where they differ).
- `tsconfig.json`, eslint config, `package.json` + `package-lock.json`: new,
  pinned; `tsc --noEmit` and `eslint` pass over the existing files (fix the
  specs/config only if the checkers find real defects — and say so in the PR).
- `playwright.config.ts`: retries 0, trace retain-on-failure; e2e suite still
  green (4 specs).
- `pyproject.toml`: testpaths; invariant pass still collects 54/36 exactly.
- Tests (test-author): the detect-probe fidelity test and the CI checker
  self-test updated for the new probe truth; the collector-vs-scan equality
  guard, docstring naming the mutation it kills (a new invariant test file in
  an uncollected directory).
- Full suite green; GitHub CI green with the audit/license/tsc/eslint jobs
  visibly **running** on this PR, not skipping.

## File ownership (parallel-build boundary — do not cross)

This ticket may touch only: `.github/workflows/ci.yml`, `Makefile`,
`pyproject.toml` (the `[tool.pytest.ini_options]` block only),
`playwright.config.ts`, `package.json`, `package-lock.json`, new
`tsconfig.json` and eslint config, `scripts/ci/` only if a checker's own logic
must follow the probe split, this ticket file, and under `tests/` only
`tests/unit/test_the_detect_probes_see_the_files_their_jobs_run.py`,
`tests/unit/test_when_only_diff_does_not_run_the_expensive_gates.py`, and a
**new** guard-test file. Never `docker-compose*.yml`, never `.env.example`,
never `backend/`, never `docs/` beyond this ticket file, never
`CONTRIBUTING.md` (E0-42 owns its corrections) — sibling tickets own those in
parallel worktrees.
