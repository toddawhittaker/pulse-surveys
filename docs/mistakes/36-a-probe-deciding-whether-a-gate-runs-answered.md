# Entry 36. A probe deciding whether a gate runs answered false over a tree that had the thing

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*1 instance recorded.*

*(Found by the independent security review of E0-36, PR #45, in the file that
ticket was editing. `.github/workflows/ci.yml`'s `detect` job decides whether the
eval gate and the Playwright gate run, by probing for the files they need. Both
probes answered false over trees that held those files. The `evals` probe used
`compgen -G "tests/evals/**/*.py"` and nothing sets `shopt -s globstar`, so `**`
collapses to a single `*` and the pattern is really `tests/evals/*/*.py` — it
cannot see `tests/evals/runner.py`, which is the exact module the job runs with
`python -m tests.evals.runner`. The `e2e` probe used a flat glob that does not
descend, so specs under `tests/e2e/lms/` were invisible.

**The consequence is not a skipped gate, which is why it survives a check for
skipped gates.** Every real step in those jobs is guarded by its own
`if: needs.detect.outputs.<name> == 'true'`, with a `::notice::` step in their
place. A probe answering false therefore turns the work off and the job reports
**success**. The aggregate `CI` check sees green, nothing is red, nothing is
skipped, and the SPEC §9.3 threat and self-harm recall floor would never have run
once E2 landed the runner in the obvious place. E0-36 item 1 had just been built
to make a failing gate reach the required check by treating `skipped` as a
failure; it could not have seen this, and it was one line away in the same file.

The repairs are different because the questions are different: `evals` names the
file its job imports, matching how the `frontend` probe already works, and `e2e`
uses `find … -print -quit`, which descends without a shell option and so cannot
degrade quietly the way `**` did. The `Makefile` carried both conditions and
moved in the same commit.)*

**What happened.** A tolerant gate pattern — probe for the code, run the real
check if it is there, print a notice if it is not — was introduced so the
pipeline could ship before the code existed (ADR 0002). The pattern is sound. Its
soundness rests entirely on the probe, and nothing tested the probe. Two of the
three probes in the job were wrong, in the same way, from the day they were
written.

**Why it is not the same as entry 34.** That entry is about discarding a result
you have. This is about never obtaining one: the gate does not fail and get
swallowed, it never runs, and the job is honestly reporting that it did nothing
wrong. Both produce a green line over an unexecuted check, and they need
different guards.

**Rule.** A probe that decides whether a gate runs is itself a gate, and it needs
two cases: plant what the job actually runs and require the probe to say yes, and
plant nothing and require it to say no. Assert the whole set of outputs, not the
one you are thinking about, so a probe that turns everything on cannot pass. And
`**` in a shell glob is a single `*` unless `globstar` is set — prefer naming the
file the job needs, or `find`, over a pattern whose meaning depends on a shell
option nobody sets.
