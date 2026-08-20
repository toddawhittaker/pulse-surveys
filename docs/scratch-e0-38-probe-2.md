# Second scratch probe for E0-38

The first inert-path verification ran against base `a7419ad`. Five commits landed
after it and three of them changed `.github/workflows/ci.yml` in the very job
that verification exercises: the classifier invocation gained a `--` separator,
the push branch was rewritten so only a pull request can be inert, `lint-python`
gained a repository-wide sweep step, and three jobs gained notice steps and
changed conditions.

So the record certified a workflow that no longer exists. This file exists to run
the inert path against the workflow as it actually stands. Its branch is deleted
once the run has been read.
