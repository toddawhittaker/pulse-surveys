# E0-36 — Gates that report green over something they did not look at

**ID:** E0-36
**Branch:** `e0/ci-gate-fidelity`
**Depends on:** E0-04

## Context

Five items from four tickets, all living in `.github/workflows/ci.yml`,
`scripts/ci/` and the `Makefile`. They were tracked as [E0-20](E0-20-gate-fidelity.md)
items 1 and 2, [E0-32](E0-32-gate-gaps-the-selftest-found.md) item 1,
[E0-25](E0-25-review-debt-from-e0-09-to-e0-14.md) item 1, and
[E0-29](E0-29-review-debt-from-e0-13.md) item 4c.

They are one subject: **a gate that prints a green line over a check it did not
perform.** That is `docs/MISTAKES.md` entry 2 applied to the build rather than to
application code, and entry 34 — a pipeline discarding a non-zero exit and
printing a line that reads as success — is the same failure already recorded once.

Read first: `.github/workflows/ci.yml`, [ADR 0002](../../adr/0002-ci-gates-ship-tolerant.md),
and `docs/MISTAKES.md` entries 2, 9 and 34.

## Scope

### 1. The aggregate `CI` check cannot see a `migration-drift` failure

The most consequential item here, because `CI` is the single required check
branch protection points at.

`ci` needs `[fast-gate, test, e2e, evals, docker, frontend-build, supply-chain]`.
`migration-drift`, `lint-python`, `lint-frontend` and `ci-selftest` reach it only
through `fast-gate`. **A job whose dependency failed is reported `skipped`, not
`failure`**, so a real `migration-drift` failure cascades: `fast-gate` skipped,
everything downstream skipped, `join(needs.*.result)` is `skipped,skipped,…`, the
verdict step's `grep -qE 'failure|cancelled'` matches nothing, and it prints
"All gates green" and exits 0.

Confirmed still live on this branch: the `needs` list and the verdict step are
unchanged from when E0-04 raised it.

The step's own comment explains why `skipped` was not treated as a failure —
tolerant jobs report success, so this stays honest as the tree fills in. That was
true and the two are now indistinguishable, while the tolerant case shrinks and
the failure case has become reachable.

Treat `skipped` as a failure among `ci`'s needs, or put the four fast jobs in
`ci`'s `needs` directly, or both. `scripts/ci/test_ci_scripts.py` and
`tests/unit/test_ci_health_gate.py` are the two existing patterns for asserting
on the workflow.

### 2. The drift job's two-role shape has nothing asserting it

E0-04 required the `migration-drift` job to use the same database shape the stack
deploys, application role included, or `alembic check` cannot see a grant
problem. Demonstrated during review: delete the "Provision the application role"
step and revert the job's `DATABASE_URL` to the superuser, and all 86 unit tests
still pass and the drift job still passes, because a superuser can create tables.
So [ADR 0012](../../adr/0012-the-migration-environment-builds-its-own-superuser-connection.md)'s
stated consequence is a convention rather than a guarantee.

The `env.py` half *is* guarded — reverting its `.set(username=…, password=…)`
turns three integration tests red and errors five more. Only the CI job's half is
unasserted.

### 3. The invariant gate cannot see a test that asserts nothing

`scripts/ci/check_invariants.py` treats a skip, an xfail and an empty collection
as failures, because in a green checkmark those are indistinguishable from a
passing assertion. **A test that runs and asserts nothing is indistinguishable
too**, and it counts toward the "N invariant test(s) ran, none skipped, none
failed" the checker prints.

Found by `spec-conformance` against a planted fixture whose `invariant`-marked
test body ends after a call.

**The rule, decided 2026-08-19 because the item as written named none.** An
`invariant`-marked test's own body must contain at least one of: an `assert`
statement, a `with pytest.raises(...)` block, or a `pytest.fail(...)` call. A
body whose only statements are calls is refused.

Two things that rule deliberately does not do, and the cost of each:

- **It does not follow a call into a helper.** A test that delegates its whole
  control to a module-level helper which asserts is correct and this rule refuses
  it. That is the accepted cost: chasing calls means choosing how many levels
  deep and whether an imported helper counts, and every answer to that is
  arbitrary. The refusal is loud and the fix is one line in the test.
- **It reads the body statically and does not know whether the assertion
  executed.** An `assert` inside a branch nothing takes satisfies it. This item
  closes the gap between "no assertion is written" and "an assertion passed"; it
  does not close the gap between "an assertion is written" and "it ran".

A shape the rule's two halves point opposite ways on, decided 2026-08-19 so that
the round building the checker is not deciding it: a test whose only assertion
sits inside a nested function it defines and then calls is **allowed**. The
assertion is lexically inside the test, where a reader of the test can see it,
and "helpers are not chased" is about a call leaving the function for something
defined elsewhere. Allowing it is also what an ordinary AST walk of the body does
without extra code, and refusing it would mean writing code to detect a shape
nothing in this repository uses. Nothing in the tree depends on the answer either
way — see the measurement below.

Measured before the rule was chosen: all **24** `invariant`-marked tests in the
tree carry an `assert` in their own body, none inside a nested function, and every
one that uses `pytest.raises` also asserts directly. So the rule is green on the
whole suite today and no existing test moves to satisfy it.

**That number was 20 when this section was first written, and the correction is
the item's own subject.** The measurement behind it read decorators only, so it
missed the four tests marked by a module-level `pytestmark = pytest.mark.invariant`
— three in `tests/unit/test_no_service_reads_an_identity_table_directly.py` and one
in `tests/unit/test_care_is_not_reachable_from_a_claim.py`. A checker built to that
measurement would have reported a clean scan over four real §4.1 invariants it
never looked at, which is exactly what this ticket is about. The number to trust is
`pytest -m invariant --collect-only`, which collects 24 functions and 42
parametrized cases; the checker agrees with it, and that agreement is worth
re-checking rather than assuming.

**Where it lives, and why the test wall holds.** The checker is
`scripts/ci/check_invariant_assertions.py`, invoked in the same gate step as
`check_invariants.py` in both `.github/workflows/ci.yml` and the `Makefile`. Its
behavioural self-test — a body ending after a call is refused, a `raises` body is
allowed, a `fail` body is allowed, a helper-delegated body is refused — goes in
`scripts/ci/test_ci_scripts.py`, which is outside `tests/**` and is already the
established home for "this checker exits 1 on that input". Under `tests/**` sit
the two tests the checker cannot write about itself: that both callers invoke it,
with the canary that both still invoke `check_invariants.py`; and an end-to-end
run over planted sample files.

### 4. Nothing asserts `.dockerignore`'s contents

E0-12 added four re-exclusions (`backend/**/*~`, `*.orig`, `*.rej`, `*.bak`)
because `pyproject.toml` ships `app/ai/prompts/**/*` as package data, making the
prompts directory a path by which arbitrary file content reaches the runtime
image. Measured: `scratch-notes.txt` and `validity.v1.md~` are both carried into
the wheel; `.env` is not, because Python's glob skips dotfiles.

Deleting any of those four lines leaves every gate green, and the failure it
prevents — a key parked beside a prompt while debugging, baked into an image
layer — is invisible in review because the file is untracked.

**The check must build the image and inspect what reached it.** A test asserting
the `.dockerignore` *text* is not acceptable: it would pass against a typo'd
pattern. That makes this a Docker-gate concern rather than a unit test.

### 5. `make lock` should compile the dev lockfile against the runtime lockfile

`pip-compile … --extra dev` currently resolves independently of `requirements.txt`.
Two independent resolutions of overlapping requirement sets skewed
`charset-normalizer` to two versions during E0-13; every test passed and only
`pip-audit` saw it (`docs/MISTAKES.md` entry 25). Add `-c requirements.txt` to
the dev compile.

The recipe has to keep matching `.github/workflows/ci.yml`, so **the Makefile and
the workflow move in the same commit**.

## This ticket produces two pull requests

E0-29 item 4b belongs to this subject and cannot ship with it. `regex` and
`tiktoken` classify as `unknown` licence in `scripts/ci/check_licenses.py`: both
are permissive and MIT-distribution compatible — `regex` is `Apache-2.0 AND
CNRI-Python`, and `tiktoken` ships the full MIT text in its `License:` field,
which the checker's `AND` split shatters. The gate is right in outcome and
accidental in mechanism.

`CLAUDE.md` requires a gate change to be its own pull request saying what
coverage changed. **So 4b ships alone**, after the five items above, with a body
stating exactly what the checker now accepts that it did not before. Do not fold
it in to save a round trip.

## Out of scope

- **Anything about what the gates check.** This ticket changes whether they can
  detect it, not what "it" is.
- The catalog comparison ([E0-33](E0-33-catalog-drift-assertions.md)) and the
  view-file guard ([E0-34](E0-34-view-file-identity-guards.md)). Both are gate
  fidelity in spirit; both are test code rather than pipeline code.
- **Weakening any gate to close an item here.** If an item cannot be closed
  without giving up coverage, it is deferred with a reason, not traded.

## Acceptance criteria

- [ ] A deliberately failing `migration-drift` makes the aggregate `CI` check
      report failure. **Verify by pushing a real drift to a scratch branch, not
      by reading the YAML.**
- [ ] Deleting the drift job's provisioning step, or repointing its
      `DATABASE_URL` at the superuser, fails something.
- [ ] An `invariant`-marked test that executes no assertion fails the invariant
      gate, and a test asserts that it does.
- [ ] A gate fails when a file matching one of `.dockerignore`'s prompt-directory
      re-exclusions reaches the built image. Building the image and inspecting it
      is acceptable and probably necessary.
- [ ] `make lock` constrains the dev resolution against `requirements.txt`, and
      `ci.yml` still matches the recipe.
- [ ] Every fix verified by mutation — reintroduce the defect and watch something
      go red — with confirmation that the mutation landed.
- [ ] The licence-checker widening ships as a separate pull request.

## Definition of done

**Tests apply**, and they are most of the ticket.

**Docs apply** if ADR 0002's tolerance argument changes shape once `skipped` is
treated as a failure.

**AI evals do not apply. Accessibility does not apply.**

**Security review applies but is light.** Item 4 is the only one with a
confidentiality consequence and it is build hygiene rather than a reachable path.
