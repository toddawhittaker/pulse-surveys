"""A gate that fails must reach the one required check — ticket E0-36, item 1.

`ci` is the single check branch protection points at, and it computes its verdict
from `join(needs.*.result)`. It needs `[fast-gate, test, e2e, evals, docker,
frontend-build, supply-chain]`; `migration-drift`, `lint-python`, `lint-frontend`
and `ci-selftest` reach it only through `fast-gate`.

**A job whose dependency failed is reported `skipped`, not `failure`.** So a real
`migration-drift` failure cascades — `fast-gate` skipped, everything downstream
skipped — the join is `skipped,skipped,…`, the verdict's
`grep -qE 'failure|cancelled'` matches nothing, and the required check prints
"All gates green" and exits 0. That is `docs/MISTAKES.md` entry 34 one level up:
a pipeline printing a line that reads as success over a result it discarded.

**How this is asserted.** Not by reading the YAML for a particular fix. E0-36
names two remedies — treat `skipped` as a failure among `ci`'s needs, or put the
four fast jobs in `ci`'s needs directly — and a test that recognised one of them
would decide the question the ticket leaves open. So the workflow's own job graph
is walked, GitHub's result rules are applied to it (a job whose need did not
succeed is `skipped`), the resulting `${{ }}` expressions are substituted into the
`ci` job's own `run:` script, and that script is executed by `bash`. Whatever
shell the verdict is written in, the question asked of it is the criterion's:
*with `migration-drift` failed, does the aggregate check exit non-zero?*

**This is stricter than the criterion in one respect, deliberately.** The
criterion names `migration-drift`; the sweep below covers every job `ci` depends
on, transitively, including `detect`. That rules out the second remedy *on its
own*: adding the four fast jobs to `ci`'s needs catches a `migration-drift`
failure but not a `detect` failure, which still cascades to an all-`skipped` join.
Treating `skipped` as a failure covers both, and the file supports it: every
`detect`-driven tolerance in `e2e`, `evals`, `frontend-build` and `lint-frontend`
is at the *step* level, so no job in `ci`'s needs is ever legitimately skipped and
a skip there always means an upstream failure.

**That last sentence is true and it is not the whole picture, which is worth
saying here because this module is where somebody will come looking.** Step-level
tolerance is exactly the mechanism by which a job reports **success** over work it
did not do: the real steps are switched off by their own `if:`, a `::notice::`
step runs in their place, and the job is green. E0-36's security review found a
live instance one line away in the file this module's fix edits — the `detect`
job's `evals` probe cannot see `tests/evals/runner.py`, so the job that runs the
§9.3 recall floor would report success without running it. Nothing here is wrong
about `skipped`, and nothing here would notice that. The module named
`test_the_detect_probes_see_the_files_their_jobs_run` is what does.

**What this cannot see, stated so nothing here is cited as more than it is.**
The model assumes the verdict is computed in a `run:` script of the `ci` job, that
`ci` itself runs when upstream failed (its `if: always()`, asserted below), and
that no other job carries a job-level `if:`. Each of those is checked or fails
loudly with a message naming the assumption, rather than being modelled wrongly in
silence. A verdict moved into a step condition, an action, or a reusable workflow
must teach this module the new form; it will go red saying so.

`tests/unit/test_ci_health_gate.py` and `tests/unit/test_ci_migration_and_test_gates.py`
are the two existing patterns for asserting on this workflow. This is a third
module rather than an addition to either, because its subject is neither a
particular job's steps nor a tolerance flag: it is the shape of the dependency
graph and what the aggregate can conclude from it.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

# The one required check, and the gate the criterion names by hand. Both are
# spelled out rather than discovered: if either is renamed this module should say
# so loudly rather than quietly find nothing to check.
AGGREGATE_JOB = "ci"
NAMED_GATE = "migration-drift"

# GitHub's result values that mean "something upstream did not succeed", and so
# make a dependent job skip. `skipped` is in the set because a skip cascades: the
# job after the one that skipped never runs either.
UPSTREAM_TROUBLE = frozenset({"failure", "cancelled", "skipped"})

# The `${{ … }}` expressions this module can evaluate. Anything else is reported
# rather than guessed at — an expression substituted wrongly would produce a
# verdict this test believes and nobody ever ran.
EXPRESSION = re.compile(r"\$\{\{(?P<body>.*?)\}\}", re.DOTALL)
JOIN_WITH_SEPARATOR = re.compile(
    r"^join\(\s*needs\.\*\.result\s*,\s*(?P<quote>['\"])(?P<separator>.*?)(?P=quote)\s*\)$"
)
JOIN_DEFAULT_SEPARATOR = re.compile(r"^join\(\s*needs\.\*\.result\s*\)$")
ONE_RESULT = re.compile(r"^needs\.(?P<job>[A-Za-z0-9_-]+)\.result$")
TO_JSON_NEEDS = re.compile(r"^toJSON\(\s*needs\s*\)$")


def needs_of(job: Any) -> list[str]:
    """The jobs one job waits on, whether it named one or several."""
    declared = (job or {}).get("needs")
    if declared is None:
        return []
    if isinstance(declared, str):
        return [declared]
    return [str(name) for name in declared]


def jobs_of(workflow: dict[str, Any], workflow_path: Path) -> dict[str, Any]:
    """Every job in the workflow, or a failure naming what was read instead."""
    jobs = workflow.get("jobs") or {}
    if not jobs:
        pytest.fail(
            f"{workflow_path} declares no jobs, or did not parse. The CI pipeline is what makes "
            "the §14.2 definition of done enforceable, so it existing is a precondition of this "
            "module meaning anything."
        )
    return dict(jobs)


def aggregate_needs(jobs: dict[str, Any], workflow_path: Path) -> list[str]:
    """The jobs the required check waits on, in the order it declares them."""
    if AGGREGATE_JOB not in jobs:
        pytest.fail(
            f"{workflow_path} declares no `{AGGREGATE_JOB}` job (it declares {sorted(jobs)}). "
            "That job is the single required check branch protection points at; if it has been "
            "renamed, rename it here too rather than leaving this module looking for something "
            "that is gone."
        )
    declared = needs_of(jobs[AGGREGATE_JOB])
    if not declared:
        pytest.fail(
            f"The `{AGGREGATE_JOB}` job waits on nothing, so there is no gate whose failure it "
            "could report. A required check with no needs is green whatever the pipeline did."
        )
    return declared


def upstream_closure(jobs: dict[str, Any], workflow_path: Path) -> list[str]:
    """Every job the required check depends on, directly or through another job."""
    found: set[str] = set()
    pending = list(aggregate_needs(jobs, workflow_path))
    while pending:
        name = pending.pop()
        if name in found:
            continue
        if name not in jobs:
            pytest.fail(
                f"A `needs:` entry names `{name}`, which is not a job in {workflow_path} "
                f"(it declares {sorted(jobs)}). The graph this module walks is broken, so its "
                "conclusions would be too."
            )
        found.add(name)
        pending.extend(needs_of(jobs[name]))
    return sorted(found)


def simulated_results(jobs: dict[str, Any], failing: str | None) -> dict[str, str]:
    """What every job would report if `failing` failed and nothing else did.

    GitHub's rule, and the whole subject of this module: a job runs only when
    every job it needs succeeded, and a job that does not run reports `skipped`
    rather than `failure`. So one failure deep in the graph reaches the aggregate
    as a row of skips.

    The aggregate itself is not given a result — it carries `if: always()` and so
    runs regardless, which is asserted separately before this is trusted.
    """
    results: dict[str, str] = {}

    def result_of(name: str, ancestry: frozenset[str]) -> str:
        if name in results:
            return results[name]
        if name in ancestry:
            pytest.fail(
                f"The job graph contains a cycle through `{name}`, which GitHub would refuse to "
                "run at all. Nothing this module concludes about it would be meaningful."
            )
        outcome = "failure" if name == failing else "success"
        if outcome == "success":
            for parent in needs_of(jobs[name]):
                if parent not in jobs:
                    pytest.fail(
                        f"The `{name}` job needs `{parent}`, which is not a job in this workflow. "
                        "The graph this module walks is broken, so its conclusions would be too."
                    )
                if result_of(parent, ancestry | {name}) in UPSTREAM_TROUBLE:
                    outcome = "skipped"
                    break
        results[name] = outcome
        return outcome

    for name in jobs:
        if name != AGGREGATE_JOB:
            result_of(name, frozenset())
    return results


def rendered(script: str, results: dict[str, str], order: list[str]) -> tuple[str, list[str]]:
    """`script` with every `${{ }}` expression replaced by the value it would hold.

    Answers the rendered script and the expressions that could not be evaluated.
    Unknown expressions are reported rather than dropped: an expression silently
    substituted with the empty string produces a verdict nobody ever ran, which is
    the shape of failure this whole module is about.
    """
    unknown: list[str] = []

    def replace(match: re.Match[str]) -> str:
        body = match.group("body").strip()

        joined = JOIN_WITH_SEPARATOR.match(body)
        if joined:
            return joined.group("separator").join(results[name] for name in order)
        if JOIN_DEFAULT_SEPARATOR.match(body):
            return ",".join(results[name] for name in order)

        single = ONE_RESULT.match(body)
        if single:
            job = single.group("job")
            if job not in results:
                unknown.append(body)
                return ""
            return results[job]

        if TO_JSON_NEEDS.match(body):
            return json.dumps({name: {"result": results[name]} for name in order})

        unknown.append(body)
        return ""

    return EXPRESSION.sub(replace, script), unknown


def aggregate_exit_code(
    jobs: dict[str, Any],
    workflow_path: Path,
    tmp_path: Path,
    failing: str | None,
) -> int:
    """Run the required check's own steps over a pipeline in which `failing` failed.

    The exit code of the first step that fails, or 0 if every step succeeded —
    which is what GitHub does with `bash -e {0}`, the default shell for a `run:`
    block on Linux.
    """
    bash = shutil.which("bash")
    if bash is None:
        pytest.fail(
            "bash is not on PATH, so the verdict script cannot be executed. This fails rather "
            "than skipping: a skip here is indistinguishable from a pipeline that discriminates."
        )

    order = aggregate_needs(jobs, workflow_path)
    results = simulated_results(jobs, failing)
    steps = jobs[AGGREGATE_JOB].get("steps") or []

    scripts: list[str] = []
    for index, step in enumerate(steps):
        if "if" in step:
            pytest.fail(
                f"Step {index} of the `{AGGREGATE_JOB}` job carries an `if:` condition "
                f"({step['if']!r}), and this module does not evaluate step conditions — it runs "
                "every `run:` block the job declares. If the verdict now lives in a condition "
                "rather than in a script, this module has to be taught that form before its "
                "answer means anything."
            )
        shell = step.get("shell")
        if shell is not None and str(shell).split()[0] != "bash":
            pytest.fail(
                f"Step {index} of the `{AGGREGATE_JOB}` job declares `shell: {shell}`, which this "
                "module cannot run. It executes `run:` blocks with bash, as GitHub does by "
                "default on Linux."
            )
        if isinstance(step.get("run"), str):
            scripts.append(step["run"])

    if not scripts:
        pytest.fail(
            f"The `{AGGREGATE_JOB}` job runs no script at all, so there is nothing here that could "
            "report a verdict. A required check with no steps is green whatever the pipeline did, "
            "which is a worse version of the defect this module exists for."
        )

    for index, script in enumerate(scripts):
        text, unknown = rendered(script, results, order)
        if unknown:
            pytest.fail(
                f"The `{AGGREGATE_JOB}` job's verdict uses expressions this module cannot "
                f"evaluate: {sorted(set(unknown))}. It understands `join(needs.*.result, …)`, "
                "`needs.<job>.result` and `toJSON(needs)`. Substituting an expression wrongly "
                "would produce a verdict nobody ever ran, so this fails instead of guessing — "
                "teach `rendered()` the new form."
            )
        path = tmp_path / f"verdict-{index}.sh"
        path.write_text(text, encoding="utf-8")
        # S603: the executable is a resolved absolute path and the argument list
        # is a literal plus a file this test just wrote. Nothing here comes from
        # outside the repository.
        completed = subprocess.run(  # noqa: S603
            [bash, "-e", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return completed.returncode
    return 0


def test_the_aggregate_check_reports_success_when_every_gate_succeeded(
    ci_workflow_path: Path, ci_workflow: dict[str, Any], tmp_path: Path
) -> None:
    """The control, and the first thing to assert: a green pipeline is still green.

    Everything else in this module reads a non-zero exit as "the failure was
    seen". A verdict that exits non-zero whatever it is given would satisfy those
    assertions perfectly while failing every honest build, so the harness is
    required to produce a zero before its non-zeros mean anything
    (`docs/MISTAKES.md` entry 3).

    **The mutation this survives:** widen the verdict's pattern in
    `.github/workflows/ci.yml` to `grep -qE 'failure|cancelled|skipped|success'`.
    **The near miss that must stay green:** widening it to
    `grep -qE 'failure|cancelled|skipped'`, which is E0-36's fix.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)
    code = aggregate_exit_code(jobs, ci_workflow_path, tmp_path, failing=None)
    assert code == 0, (
        f"With every gate reporting success, the `{AGGREGATE_JOB}` job exited {code}. A required "
        "check that fails a clean pipeline blocks every merge, and it also makes every other "
        "assertion in this module vacuous — they read a non-zero exit as evidence that a failure "
        "was noticed."
    )


def test_the_aggregate_check_fails_when_a_gate_it_names_directly_fails(
    ci_workflow_path: Path, ci_workflow: dict[str, Any], tmp_path: Path
) -> None:
    """The detection that already works, held while item 1 changes the verdict.

    `test` is in `ci`'s `needs`, so its failure arrives as the string `failure`
    and today's `grep -qE 'failure|cancelled'` catches it. That half is not
    broken, and a fix for the cascade must not cost it — a verdict rewritten to
    look only for `skipped` would pass the sweep below and lose this.

    **The mutation this survives:** delete the `if … exit 1` block from the
    Verdict step, leaving the `echo` lines. **The near miss that must stay
    green:** rewriting the same verdict as a `case` statement over the joined
    results, which means the same thing in different shell.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)
    directly_needed = aggregate_needs(jobs, ci_workflow_path)

    offenders = []
    for name in directly_needed:
        code = aggregate_exit_code(jobs, ci_workflow_path, tmp_path, failing=name)
        if code == 0:
            offenders.append(name)

    assert not offenders, "\n".join(
        [
            f"These jobs are in `{AGGREGATE_JOB}`'s own `needs:` list, and the required check "
            f"still exits 0 when they fail: {offenders}.",
            "",
            "A job named directly in `needs:` reports `failure` when it fails — no cascade, no "
            "ambiguity — so this is the easiest half of the verdict to get right and the one a "
            "rewrite is most likely to drop.",
        ]
    )


def test_no_gate_can_fail_without_the_aggregate_check_reporting_failure(
    ci_workflow_path: Path, ci_workflow: dict[str, Any], tmp_path: Path
) -> None:
    """E0-36 criterion 1, over every job the required check depends on.

    A failing `migration-drift` cascades: `fast-gate` skipped, everything
    downstream skipped, the join all skips, and the verdict's pattern matches
    none of them. The check prints "All gates green" and exits 0, and the one
    required check branch protection points at is green over a migration that
    drifted from its models.

    The sweep is over the transitive closure rather than over the one job the
    criterion names, so a gate added later is covered without anybody remembering
    this file. `detect` is in that closure and is the reason the second remedy
    cannot stand alone: putting the four fast jobs in `ci`'s needs catches
    `migration-drift` and leaves `detect` cascading to an all-skipped join.

    The criterion says to verify by pushing a real drift to a scratch branch
    rather than by reading the YAML, and it is right — this asserts the shape,
    and the push asserts that GitHub agrees with the shape.

    **The mutation this survives:** restore the verdict's pattern in
    `.github/workflows/ci.yml` to `grep -qE 'failure|cancelled'`. **The near miss
    that must stay green:** adding a new fast job to `fast-gate`'s `needs:` — a
    gate that joins the pipeline upstream must not need an edit here.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)

    condition = str(jobs[AGGREGATE_JOB].get("if") or "")
    assert "always()" in condition, (
        f"The `{AGGREGATE_JOB}` job's condition is {condition or 'absent'!r}, so it does not run "
        "when a job it needs has failed — and this module's whole model assumes it does. Without "
        f"`if: always()` the required check is itself skipped on any failure, and a skipped "
        "required check does not block a merge. That is the same defect one layer further out."
    )

    conditioned = sorted(
        name for name in jobs if name != AGGREGATE_JOB and (jobs[name] or {}).get("if") is not None
    )
    assert not conditioned, "\n".join(
        [
            f"These jobs carry a job-level `if:`: {conditioned}.",
            "",
            "This module models GitHub's rule that a job whose need did not succeed reports "
            "`skipped`, and a job-level condition changes that rule for the job that has one. "
            "Rather than model it wrongly in silence, this says so: teach `simulated_results` "
            "the condition, or say here why it cannot change the answer.",
        ]
    )

    closure = upstream_closure(jobs, ci_workflow_path)
    assert NAMED_GATE in closure, (
        f"`{NAMED_GATE}` is not among the jobs `{AGGREGATE_JOB}` depends on (those are "
        f"{closure}). It is the job E0-36's first criterion names, and a sweep that no longer "
        "covers it is a sweep that cannot fail for the reason it was written."
    )

    assert aggregate_exit_code(jobs, ci_workflow_path, tmp_path, failing=None) == 0, (
        f"With every gate reporting success the `{AGGREGATE_JOB}` job already exits non-zero, so "
        "the sweep below would report every job as caught without the verdict looking at "
        "anything. `test_the_aggregate_check_reports_success_when_every_gate_succeeded` is where "
        "that is diagnosed."
    )

    unseen: list[tuple[str, list[str]]] = []
    for name in closure:
        if aggregate_exit_code(jobs, ci_workflow_path, tmp_path, failing=name) == 0:
            results = simulated_results(jobs, name)
            unseen.append(
                (name, [results[need] for need in aggregate_needs(jobs, ci_workflow_path)])
            )

    reported = [
        f"  {name} fails -> the required check sees {seen} and exits 0" for name, seen in unseen
    ]

    assert not unseen, "\n".join(
        [
            f"These jobs can fail while the `{AGGREGATE_JOB}` check reports success:",
            *reported,
            "",
            "A job whose dependency failed is reported `skipped`, not `failure`, so a failure "
            "upstream of `fast-gate` reaches the verdict as a row of skips and "
            "`grep -qE 'failure|cancelled'` matches none of them. The check then prints "
            '"All gates green" and exits 0 — `docs/MISTAKES.md` entry 34, a pipeline printing '
            "a line that reads as success over a result it discarded, this time on the one check "
            "branch protection points at.",
            "",
            "E0-36 names two remedies: treat `skipped` as a failure among `ci`'s needs, or put "
            "the four fast jobs in `ci`'s needs directly, or both. Nothing here prefers one — "
            "the verdict is executed rather than read — but the second on its own leaves "
            "`detect` cascading to an all-skipped join, which is why it appears in this list.",
        ]
    )
