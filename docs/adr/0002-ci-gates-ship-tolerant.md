# 0002 — CI gates ship tolerant and name the ticket that enforces them

**Status:** Accepted — recorded retroactively
**Date:** 2026-08-12
**Pull request:** #5 (decision), #6 (this record)

> Written after the fact. The rule in `CLAUDE.md` is to record a decision in the
> pull request that makes it; this one shipped before that rule existed, so the
> reasoning below is reconstructed rather than contemporaneous. Treat the
> alternatives section as slightly generous to the option that won.

## Context

The pipeline in `.github/workflows/ci.yml` was built before any of the code it
checks. [SPEC §14.2](../SPEC.md) makes "CI green" a merge condition and
[§9](../SPEC.md) defines the suites it must run, but at the time there was no
backend, no frontend, no Compose file, and no tests. Every gate had nothing to
run against.

The spec says what the pipeline must eventually enforce. It does not say what
the pipeline should do in the interval where the code does not exist yet, and
that interval spans all of E0.

## Decision

A `detect` job probes the tree and emits booleans. Each gate job runs its real
check when its target exists; otherwise it emits a `::notice::` naming the
ticket that will make it enforcing, and exits 0.

Removing a tolerance is an acceptance criterion of the ticket that lands the
corresponding code, and `docs/tickets/e0/README.md` carries the gate-to-ticket
table.

## Alternatives rejected

**Omit each job until its code exists.** Rejected because the pipeline would
then be written piecemeal, with each ticket inventing its own job and no single
place showing the intended full gate set. Gates nobody is thinking about — the
bundle budget, the license check — are exactly the ones that never get added.

**`continue-on-error: true` on each job.** Rejected because it reports success
in the checks interface while the step actually failed, which is
indistinguishable from a real pass without opening the log. That destroys the
property `CLAUDE.md`'s discipline rules depend on: green means green.

**Let the pipeline fail until each gate is implemented.** Rejected because a
permanently red default branch trains people to ignore red, which is the precise
failure mode the "never merge with red CI" rule exists to prevent.

**Use GitHub path filters to skip jobs.** Rejected as the wrong mechanism: path
filters decide whether a job runs based on what *changed*, not what *exists*, and
a job that never runs never reports. A required check in that state hangs
pending — the same shape as the stuck-job incident on PR #4, where a pending
check with no failing job would have blocked a merge indefinitely.

**Keep a hand-maintained list of enabled gates in a config file.** Equivalent in
effect, rejected because the list drifts from reality. Probing the filesystem
cannot lie about what exists.

## Consequences

- **A tolerant job looks like a passing job** in the checks interface unless
  someone reads the log. The notice and the gate-to-ticket table mitigate this;
  they do not eliminate it. This is the real cost of the decision.
- **Nothing mechanically enforces that a tolerance is removed on time.** If a
  ticket lands its code and forgets its flag, CI stays green and quieter than it
  should be. The acceptance criteria and E0-18's exit checklist are process
  controls, not technical ones. Accepted knowingly.
- The `detect` job adds a few seconds to every run.
- ~~The aggregate `ci` job computes its verdict from `needs.*.result`, so it
  stays correct without edits as individual gates flip from tolerant to
  enforcing.~~ **Amended 2026-08-19 (E0-36 item 1): it did not.** Reading
  `needs.*.result` is not enough on its own, because the result a failure
  produces depends on where in the graph it happens. A job whose dependency
  failed is reported `skipped` rather than `failure`, so a failing
  `migration-drift` reached the verdict as `skipped,skipped,…` — `fast-gate`
  skipped, everything below it skipped — and the pattern that looked for
  `failure|cancelled` matched none of them. The required check printed "All gates
  green" and exited 0 over a migration that had drifted from its models.

  The verdict now treats `skipped` as a failure too, and that is only sound
  because of a property of `ci.yml` rather than of the mechanism: every
  tolerance in that workflow is at the *step* level, so no job the aggregate depends on is
  ever legitimately skipped. A job-level `if:` on any of them would make a skip
  ambiguous again, and
  `tests/unit/test_the_aggregate_ci_check_sees_an_upstream_failure.py` fails and
  says so if one appears.

  **A second amendment, 2026-08-19, to the paragraph above rather than to the
  decision.** That paragraph is true and was read as more reassuring than it is,
  including by the session that wrote it. Step-level tolerance keeps the *skip*
  analysis simple, and it is also the mechanism by which a tolerant job reports
  **success** over work it did not do — the real steps switch themselves off,
  the notice step runs, and the job is green. So "the aggregate now sees a
  failing gate" is true of failures and skips, and says nothing about a gate
  that was quietly turned off.

  What decides that is the `detect` probe, and E0-36's independent security
  review found two of the three answering false over trees that held the thing:
  `tests/evals/**/*.py` needs `shopt -s globstar`, which was never set, and
  `tests/e2e/*.spec.ts` does not descend. Either one silently disables its gate
  with `CI` green, and the `evals` case takes SPEC §9.3's threat and self-harm
  recall floor with it — the floor `CLAUDE.md` calls a hard gate whose lowering
  is a safety decision. Both are fixed, and
  `tests/unit/test_the_detect_probes_see_the_files_their_jobs_run.py` runs each
  probe over planted trees and judges what it emits.

  **This is the real cost of the decision, and it compounds the first
  consequence rather than the aggregate's.** A tolerant gate is only as honest as
  the probe that decides whether it runs, so every probe added under this pattern
  needs a case that plants what its job needs and a case that plants nothing.
  Neither the aggregate check nor a reviewer reading the YAML can supply that.

  The decision above is unaffected — gates still ship tolerant and still name the
  ticket that enforces them. What was wrong was the claim that the aggregate
  needed no edits as they flipped.
- The pattern generalizes badly beyond bootstrap. Once E0 is complete, a new
  tolerant gate should be treated as a smell rather than as this precedent.

## The last tolerance is gone — E2-12, 2026-09-02

The `evals` job printed a notice saying the first eval set and the floors that
gate on it were still to come, and reported success. E2-12 lands both, and the
notice went in the same change, which is what the decision above asks of the
ticket that lands the code. That job's steps now run the real runner behind a
step-level condition — the diff is not inert, and either it touches the AI
surface or the run was dispatched by hand — and a floor breach is a red gate.

**Nothing in `.github/workflows/ci.yml` is tolerant any more**, so the closing
line above stops being a forecast and becomes the standing rule: a new tolerant
gate needs its own argument, made in a ticket, rather than a pointer to this
record.

Two shapes look like the pattern and are not, said here so they are not read as
counter-examples. A step switched off because every changed path is inert
documentation (E0-38), and a step switched off because no changed path is the AI
surface (E2-12), are scoping decisions with a classification behind them — and
each classification is itself executed over planted trees, which is what the
second consequence above says a tolerant gate's probe must be. The difference is
that a tolerant gate reports success over work it *could not* do, and these
report success over work that did not need doing.
