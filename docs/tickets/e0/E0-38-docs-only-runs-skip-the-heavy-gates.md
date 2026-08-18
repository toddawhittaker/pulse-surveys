# E0-38 — A documentation-only change should not run the whole pipeline

**ID:** E0-38
**Branch:** `e0/ci-docs-path-filter`
**Depends on:** E0-36

## Context

`.github/workflows/ci.yml` has **no path filtering of any kind**. The `detect`
job probes what *exists in the tree*, never what *changed*, so a pull request
that touches only Markdown runs pytest against testcontainers, builds both
images, brings up the Compose stack, runs Playwright, runs the eval floors and
audits the supply chain.

Measured on the docs-only run for PR #38:

| Job | Duration |
|---|---|
| `Test · pytest + invariants` | 390s |
| `Build · images + Compose health` | 228s |
| `Fast · ruff + mypy` | 197s |
| `Fast · migration drift` | 41s |
| `Supply chain · audit + licenses` | 32s |
| everything else combined | ~27s |

About fifteen minutes of runner time and ten minutes of wall clock to establish
that no Python changed. This epic has produced six documentation-only pull
requests, so it is not a rare shape.

**This ticket exists because the obvious version of it is wrong twice**, and
both traps are this epic's own subject matter rather than general CI advice.

Read first: `.github/workflows/ci.yml`, [ADR 0002](../../adr/0002-ci-gates-ship-tolerant.md),
[E0-36](E0-36-ci-gate-fidelity.md) item 1, and `docs/MISTAKES.md` entries 2, 9
and 34.

## Trap 1: a docs change can break a test, and one already can

`tests/unit/test_ai_contracts.py` **reads `docs/SPEC.md` at test time.** It
parses §7.4's task table and the verdict sets out of the file rather than
copying them into the test, deliberately, so that changing a verdict takes an
edit to the spec — a reviewed act with its own diff — instead of an edit to a
constant nobody reads.

So `docs/**` is not a safe skip set. PR #39 edited `SPEC.md` and pytest was the
one job that had any business running.

The rule this ticket needs is therefore **"documentation except the
documentation something parses"**, and that exception is true when written and
false the first time somebody teaches another test to read another document.
Whatever is built has to fail toward running everything: the skip set is an
allowlist of paths known to be inert, never a denylist of paths known to matter,
and a path nobody has classified runs the full pipeline.

The stronger form, if it is cheap: derive the set of parsed documents from the
tests themselves rather than restating it in the workflow, so that a new
document-reading test cannot silently widen the skip.

## Trap 2: this manufactures a second meaning for `skipped`

`ci` is the single required check branch protection points at, and
[E0-36](E0-36-ci-gate-fidelity.md) item 1 is the finding that it treats
`skipped` as passing — which is why a real `migration-drift` failure currently
prints "All gates green" and exits 0.

A path filter adds a **second, deliberate** producer of `skipped`. If it lands
before E0-36, the two become indistinguishable: "skipped because this diff was
documentation" and "skipped because the job upstream of me failed" are the same
string in `join(needs.*.result)`.

**Hence the dependency on E0-36, which is real rather than tidiness.** After
E0-36 the aggregate check distinguishes them, and this ticket has to keep them
distinguished: a job skipped by the path filter reports its skip in a way the
verdict step recognises as deliberate, and every other skip is still a failure.

The shape that avoids the problem entirely is worth weighing first: keep every
job in `needs` and have the expensive ones **exit early with success** after a
cheap "was anything but inert documentation touched?" step, rather than being
skipped by an `if:`. Then `skipped` keeps exactly one meaning, the aggregate
check needs no new case, and what is lost is a few seconds of runner startup per
job. That is probably the right answer and it is not obviously so, which is why
it is written here rather than decided.

## Do not put `paths-ignore` on the trigger

The naive fix. It makes the workflow not run at all, so the required `CI` check
never reports, and the pull request sits pending forever rather than merging.
Recorded because it is the first thing a search turns up.

## Scope

- A cheap classification step that answers one question: does this diff touch
  anything outside the inert set?
- The inert set, stated as an allowlist. Candidates: `docs/**` **except**
  `docs/SPEC.md` and anything else a test parses, `design/**`, root `*.md`.
- `Test · pytest + invariants`, `Build · images + Compose health`,
  `Test · Playwright e2e`, `Test · AI eval floors` and
  `Supply chain · audit + licenses` short-circuit when the answer is no.
- **`Fast · ruff + mypy` keeps running unconditionally.** It is 197s, and this
  epic's documentation pull requests have repeatedly included docstring edits
  *inside* Python files — which look like documentation and are not a
  documentation-only change. A filter that reads "did any `.py` change" gets
  this right; a filter that reads "did this feel like docs" does not.
- `Fast · migration drift` and `Fast · CI checker self-test` are 41s and 5s.
  Leave them.

## Out of scope

- Making any gate cheaper. This ticket changes when a gate runs, never what it
  checks or how thoroughly.
- Caching, matrix trimming, or runner sizing.
- The aggregate check's `skipped` handling, which is E0-36 item 1 and must
  already be done.

## Acceptance criteria

- [ ] A pull request touching only inert documentation completes without running
      pytest, the image build, Playwright, the evals or the supply-chain audit,
      and the required `CI` check still reports **success** rather than pending.
- [ ] A pull request touching `docs/SPEC.md` runs the full pipeline. Demonstrate
      it, because this is the case the naive version gets wrong.
- [ ] A pull request touching only a docstring inside a `.py` file runs the full
      pipeline.
- [ ] A path in neither set runs the full pipeline. The classification fails
      toward running everything, and a test asserts that by feeding it a path
      nobody has classified.
- [ ] A **real failure is still reported as failure** with the filter in place.
      Verify by pushing an actual defect to a scratch branch, not by reading the
      YAML — the same instruction E0-36 carries, for the same reason.
- [ ] `skipped` still means exactly one thing to the aggregate check, whichever
      shape is chosen.
- [ ] The pull request body states **what coverage was given up**, per
      `CLAUDE.md`: an ignore rule or an exclusion changes what the project
      guarantees and belongs in its own pull request saying so.

## Definition of done

**Tests apply.** The classification is code and gets tested like code;
`scripts/ci/test_ci_scripts.py` and `tests/unit/test_ci_health_gate.py` are the
two existing patterns for asserting on the workflow.

**Docs apply.** ADR 0002 describes the pipeline's tolerance posture and gains a
line, or a new ADR records the short-circuit-versus-skip choice if that turns
out to be contestable — which the section above argues it is.

**AI evals do not apply. Accessibility does not apply.**

**Security review applies but is light.** Nothing here is reachable from a
request. The risk it carries is the ordinary one for this subject: a gate that
does not run is indistinguishable in a green checkmark from a gate that passed,
which is the whole of [E0-36](E0-36-ci-gate-fidelity.md)'s subject arriving one
ticket later and on purpose this time.
