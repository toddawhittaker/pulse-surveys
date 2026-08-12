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
- The aggregate `ci` job computes its verdict from `needs.*.result`, so it stays
  correct without edits as individual gates flip from tolerant to enforcing.
- The pattern generalizes badly beyond bootstrap. Once E0 is complete, a new
  tolerant gate should be treated as a smell rather than as this precedent.
