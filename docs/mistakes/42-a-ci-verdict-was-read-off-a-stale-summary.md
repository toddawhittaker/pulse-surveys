# 42. A CI verdict was read off a stale check summary between two pushes

## Instance: A boundary record cited a failed run as green (2026-09-06)

The E3 boundary record (`docs/tickets/e3/boundary-review.md`, "The
verification, in kind") cited CI run 34001273838 on commit 6ebc4a8 as
"completed, successful, head matched." The run had completed with
conclusion `failure` — "Test · pytest + invariants" was red — and was never
re-run. The false green sat in a permanent record, cited alongside two runs
that genuinely were green, and was caught only by the post-merge closing
consistency pass, which re-resolved every cited run by id rather than
trusting the earlier resolution's own report. Corrected 2026-09-06.

## Instance: PR #154 was marked ready on a green that belonged to no run (2026-09-03)

Two commits were pushed to `e2/invariant-pass-coverage` seconds apart. The
first push's run was cancelled as superseded; the second's was still starting
when the pull request's check rollup was queried with a filter for
non-`SUCCESS` conclusions. The filter returned an empty list — there was
nothing failing because the deciding run had barely begun — and the empty list
was reported as "CI is fully green on the final head". PR #154 was marked
ready for review on that report. The real run for the final head
(33754450876) later failed on a genuine finding (a repository-wide sweep
running only in a path-filtered job), and the red pull request was found by
the repository owner, not by the process. Fixed the same day: the failure was
triaged per its guard's own rule, and every later verdict was taken by
resolving the run id, waiting for `status == completed`, and comparing
`headSha` to the exact commit.

## Root cause

A check rollup is a view over whatever runs GitHub currently associates with
the branch, and between a cancellation and a fresh run's first job it can hold
only stale or empty entries. Filtering that view for failures asks "is
anything currently red?" — the question that needed asking was "did the run
for *this* commit complete, and how?", which names a run id and a SHA. The
same shape as entry 36's lesson (a pipe's exit code standing in for a gate's):
an instrument adjacent to the verdict was read in place of the verdict.

## The whole rule

Resolve the run, not the rollup: `gh run list` filtered to the branch (or the
PR's checks) until one run's `headSha` equals the final commit AND
`status == completed`; only that run's `conclusion` is a verdict. A watcher's
exit proves some run ended, not which. This applies to every "green" spoken
aloud: in a report, in a PR body, before `gh pr ready`, before any merge.

**Resolving by id is not the verdict — the conclusion field is.** The second
instance resolved the exact run and the exact commit and still reported
green, because nobody read past `status == completed` to check what it
concluded with. Assert `conclusion == success` explicitly; a run resolved
correctly by id and by head SHA can still have finished with `failure`.
