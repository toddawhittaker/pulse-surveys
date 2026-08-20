# 0070 — The expensive gates short-circuit on a documentation-only diff, rather than being skipped

**Status:** Accepted
**Date:** 2026-08-19
**Ticket:** [E0-38](../tickets/e0/E0-38-docs-only-runs-skip-the-heavy-gates.md)

## Context

`.github/workflows/ci.yml` had no path filtering. The `detect` job probes what
*exists* in the tree, never what *changed*, so a pull request touching only
Markdown ran pytest against testcontainers, built both images, brought up the
Compose stack, ran Playwright, ran the eval floors and audited the supply chain.
Measured on the documentation-only run for PR #38: pytest 390s, the image build
228s, about fifteen minutes of runner time and ten of wall clock to establish
that no Python changed. This epic has produced six pull requests of that shape.

Two ways to stop a gate running, and they are not equivalent here.

**Skip the job** with a job-level `if:`. The obvious spelling, and the one every
search turns up.

**Keep the job and short-circuit its steps.** Every job stays unconditional and
stays in the aggregate check's `needs`; each expensive one gains an early step
that switches its real work off.

[SPEC](../SPEC.md) says nothing about either, and a reasonable engineer would
pick the first. E0-38 calls the choice contestable and declines to make it, which
is why this record exists.

## Decision

**Short-circuit.** Every expensive job stays in `ci`'s `needs`, stays
unconditional, and guards its own steps on `needs.changed.outputs.inert`. A
documentation-only run executes every job, each of which does nothing and reports
success.

[E0-36](../tickets/e0/E0-36-ci-gate-fidelity.md) item 1 is what settles it. That
ticket made the aggregate `ci` check treat `skipped` as a **failure**, because a
job whose dependency failed reports `skipped` and a row of those was printing
"All gates green" over a migration that had drifted from its models. It was
verified against the real pipeline: a deliberate drift pushed to a scratch branch
produced `Results: skipped, skipped, skipped, skipped, skipped, skipped, skipped`
and the required check reported failure.

So a job switched off by an `if:` arrives at that verdict as `skipped` and **fails
the one check branch protection points at, on every documentation-only pull
request**. The filter would break the thing it was meant to make cheaper.

The classification lives in a job of its own, `changed`, rather than as a fourth
output on `detect`. Two reasons, and the second is the smaller one: `detect`
answers what exists in the tree and `changed` answers what the diff touched,
which are different questions with different failure modes; and `detect`'s probe
battery compares the *whole* set of outputs that job emits, so a fourth one there
turns a committed E0-36 test red for a reason nobody would enjoy diagnosing.

## Alternatives rejected, and what each costs

**A job-level `if:` on each expensive job.** Rejected on the above. It is cheaper
by a few seconds of runner startup per job — five jobs that do not schedule at
all against five that schedule and exit — and that is the whole of its
advantage.

Taking it would have required the aggregate verdict to distinguish two kinds of
`skipped`: "skipped because a job I needed failed" and "skipped because the diff
was documentation". Those are the same string in `join(needs.*.result)`. The
verdict would need per-job results and a rule about which jobs are allowed to
skip and when — and that is a rule about *why* a job did not run, reconstructed
after the fact from a string that does not carry the reason. E0-36 has just
finished proving the single meaning correct against the real pipeline, and this
would spend that proof on a few seconds per run.

**`paths-ignore` on the workflow trigger.** Rejected because the workflow then
does not run at all, so the required `CI` check never reports and the pull
request sits pending forever rather than merging. Recorded because it is the
first thing a search suggests.

**Removing the expensive jobs from `ci`'s `needs` on a documentation-only run.**
Not expressible — `needs` is static — but the shape is worth naming because it is
the tempting repair if the skip problem is met head-on. A gate outside that graph
cannot fail the required check on *any* run, not just this one.

**Deriving the parsed-document exception from the test suite**, which E0-38
offers as the stronger form. Rejected, and this is the one sub-decision inside
the classifier worth recording. The guard on this classifier sweeps the suite for
every document a test module opens by path and asserts the classifier calls each
one not-inert. If the classifier derived the same set by the same walk, that
guard could not fail: it would be comparing an answer with itself
(`docs/MISTAKES.md` entry 19). Hand-listing keeps the guard able to fail — a new
document-reading test turns the sweep red on the pull request that adds it, with
a message naming the file to except. The cost is one line in
`PARSED_DOCUMENTS`, paid by whoever teaches a test to read a new document, and it
is loud rather than silent.

## Consequences

- **A documentation-only run still costs six job schedules.** Each expensive job
  starts, checks out, prints a `::notice::` and exits. That is the price of the
  decision and it is a few seconds against the fifteen minutes it saves.

  **Six, not five.** `Build · frontend + bundle budget` is the sixth, and the
  ticket, the first version of this record and the pull request body all said
  five. It is free today only because there is no `frontend/` to build; once the
  scaffold lands it is an `npm ci` and a production build, the same order of cost
  as the rest. E0-38's security review found it unguarded and unnamed. It is
  guarded now.
- **`skipped` keeps exactly one meaning**, so E0-36's verdict step needs no new
  case and the proof it was given against the real pipeline still holds.
- **A green run now has two shapes**, and the checks interface does not
  distinguish them: every gate passed, and every gate declined to look. The
  `::notice::` line in each short-circuited job is the only thing that says
  which. **Two jobs had the guard and no notice** — `Test · Playwright e2e` and
  `Test · AI eval floors` printed only their older "no specs yet" and "no runner
  yet" lines, so on the first documentation-only run three of the five expensive
  jobs said why they had not worked and two said nothing about it. Worse after
  E0-18: `detect.e2e` turns true, the "no specs yet" step stops firing, and the
  job would have printed nothing at all. Each of those jobs has its own notice
  step now. This is ADR 0002's first consequence — "a tolerant job looks like a
  passing job" — arriving again by a different route, and it is accepted for the
  same reason.
- **The classification is an allowlist, so a *misclassification* costs a slow
  pipeline rather than a skipped gate.** A path nobody has classified runs
  everything, a missing or crashing classifier runs everything, and an empty diff
  runs everything.

  **An earlier version of this line said the failure mode is a slow pipeline
  rather than a skipped gate, full stop, and that was false.** E0-38's security
  review found two ways to reach a skipped gate with the classification behaving
  exactly as designed, and neither is a misclassification:

  - **A repository root file named `-h`.** The classifier was invoked without a
    `--` separator, so argparse parsed the path list and answered before any of
    the reasoning above ran. `-h` exits 0, which is the *inert* answer, and that
    switches off pytest, the §4.1 invariant suite, both image builds, Playwright,
    the evals and the audit with the required check green. `-hx` and `--hel` do
    the same by short-option clustering and abbreviation. Every near miss fails
    safe — `-q` exits 2 and lands in the "neither answer" branch — which is
    exactly why nothing caught it. Closed by passing `--`, and by the script
    refusing leading-dash arguments.
  - **A repository-wide sweep living inside a job the classification switches
    off.** The reasoning above is about `docs/` as a build *input* — nothing
    imports, executes, packages or lints it, and that is true. It is not true of
    `docs/` as a *subject*. `test_no_unresolved_merge_conflicts.py` walks
    `git ls-files` and `test_mock_lms_service.py` walks the tree from the root,
    so a conflict marker or a private key committed in a Markdown file is their
    subject — and a documentation-only pull request is both the shape that
    introduces one and the shape that switched off the sweep. Conflict markers in
    Markdown are `docs/MISTAKES.md` entry 21, which has happened here twice.
    Closed by running those node ids in `lint-python`, which is unconditional,
    and by a guard that fails when a new repository-wide sweep appears anywhere
    else.

  Both were live, both are reachable by ordinary mistake rather than by an
  attacker, and neither is visible to the `PARSED_DOCUMENTS` sweep: that sweep
  reads `/` chains, and a module that enumerates the whole repository builds no
  chain at all. The corrected claim is the one at the top of this item, and it is
  narrower than what it replaces.
- **`README.md` was inert and is also a build input; it is no longer inert.**
  Reversed on E0-38's security review, which asked whether a declared build input
  belongs in the set that switches the build off. It does not. The saving given up
  is README-only pull requests, of which this epic has produced none — the six
  inert pull requests were tickets, ADRs and mistakes files. The original
  reasoning and its cost are kept below, because the reversal is cheap only while
  README-only changes stay rare, and whoever revisits this should see what was
  weighed rather than only the answer.

  The reasoning as it stood: **`README.md` is inert and is also a build input.** `pyproject.toml` declares
  it as the wheel's readme and `backend/Dockerfile` copies it, so a README-only
  pull request no longer builds the image that packages it. The effect is on
  wheel metadata; the sharp edge is that *deleting* it breaks `COPY pyproject.toml
  README.md ./`, and that break would now surface on the next pull request that
  touches anything else rather than on the one that caused it.
- **The classifier is only as good as the path list it is handed**, and that
  list is computed in the workflow rather than in the classifier. Two ways it can
  lie were found by audit and closed: git reports a detected rename as the
  destination alone, so a service module moved into `docs/` arrived as a single
  inert path until `--no-renames` split it; and the step is invoked as
  `bash -e {0}`, so a bare command exiting non-zero ended it before it could emit
  anything — on exit 1, which is the classifier's ordinary "not inert" answer.
  Neither was visible to the classifier's own tests, because neither is about the
  classifier. When this is next changed, the first question is what the diff
  computation might not be saying.
- **A guard with its sense reversed is invisible to the suite.** The wiring test
  reads conditions and does not evaluate them, so `== 'true'` where `!= 'true'`
  was meant passes every assertion. That half is verified by pushing to a scratch
  branch, which is what E0-38's last two criteria ask for and why they ask for it.
