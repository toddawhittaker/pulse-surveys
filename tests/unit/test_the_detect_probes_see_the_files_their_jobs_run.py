"""Each `detect` probe sees the file its own job runs — E0-36, review findings 1 and 2.

The `detect` job probes the tree and emits booleans; each gate job runs its real
steps only when its boolean is true, and prints a `::notice::` otherwise (ADR
0002). **A probe that answers false over a tree that has the thing therefore turns
its gate off and reports `success`** — not `skipped`, not `failure` — while the
work it names never runs.

Two probes cannot see what their jobs need:

- **`evals`.** The probe globs `tests/evals/**/*.py`, and `shopt -s globstar` is
  never set, so `**` degrades to a single `*` and the pattern is effectively
  `tests/evals/*/*.py`. Measured: a tree holding `tests/evals/runner.py` and
  `tests/evals/__init__.py` emits `evals=false`. The job runs
  `python -m tests.evals.runner`, which needs exactly the file the probe cannot
  see, so when E2 lands the runner in the obvious place the §9.3 threat and
  self-harm recall floor silently stops running and `CI` stays green. §9.3 is the
  one floor CLAUDE.md calls a hard gate and a safety decision.
- **`e2e`.** `tests/e2e/*.spec.ts` does not descend, so specs at
  `tests/e2e/lms/launch.spec.ts` emit `e2e=false` and §9.2's requirement that both
  entry doors are exercised in every run goes unmet.

**Neither directory exists today, so both probes are correctly answering false
right now.** What is asserted here is the probe's logic over trees that are
planted, not the state of this repository — which is why every case below builds
its own tree and none of them reads the real one.

**Executed, not read.** The probe is pulled out of the parsed workflow, run under
`bash` with `GITHUB_OUTPUT` pointed at a temp file, and judged by what it emits.
A test that read the glob and objected to it would be asserting a mechanism, and
the fix is not this module's to choose: `[ -f tests/evals/runner.py ]` matches how
the `frontend` probe already works — it names the exact file `npm ci` needs — and
`shopt -s globstar` would do as well. Both pass everything below.

**Why this is in scope for a ticket about gate fidelity.** E0-36 puts "anything
about *what* the gates check" out of scope and "whether they can detect it" in.
Nothing here changes what an eval floor measures or which door an e2e spec walks
through; it changes whether the job that runs them runs at all. It is also the
counterexample to item 1's premise, one line away in the file item 1 edits: item 1
makes the aggregate check see a `skipped` job, and this job does not skip. It
succeeds.

This is a separate module from `test_the_aggregate_ci_check_sees_an_upstream_failure.py`
even though both execute a `run:` block out of the same workflow, because shared
machinery is not a shared subject: that module's argument is about GitHub's
`needs` result semantics, and a filesystem probe battery inside it would make its
docstring answer two questions at once.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

DETECT_JOB = "detect"

# A `name=value` line as the probe writes it into `$GITHUB_OUTPUT`.
EMITTED = re.compile(r"^(?P<name>[A-Za-z0-9_-]+)=(?P<value>.*)$")

# Every case is a planted tree and the whole answer the probe must give over it.
# The whole answer rather than the one key each case is about, so that a probe
# which turns `evals` on whenever `e2e` is on cannot pass by being right about the
# key the case is named for.
#
# The first case is the one that makes the rest mean anything: over a tree with
# nothing in it every probe must answer false. A probe that answered true to
# everything would satisfy every other case here perfectly.
CASES = (
    (
        "an empty repository",
        (),
        {"frontend": "false", "e2e": "false", "evals": "false"},
    ),
    (
        "a frontend package manifest",
        ("frontend/package.json",),
        {"frontend": "true", "e2e": "false", "evals": "false"},
    ),
    (
        "the eval runner that `python -m tests.evals.runner` imports",
        ("tests/evals/__init__.py", "tests/evals/runner.py"),
        {"frontend": "false", "e2e": "false", "evals": "true"},
    ),
    (
        "an eval set in a subdirectory beside the runner",
        ("tests/evals/__init__.py", "tests/evals/runner.py", "tests/evals/validity/cases.py"),
        {"frontend": "false", "e2e": "false", "evals": "true"},
    ),
    (
        "an eval directory holding no Python at all",
        ("tests/evals/README.md",),
        {"frontend": "false", "e2e": "false", "evals": "false"},
    ),
    (
        "e2e specs in a flat layout",
        ("tests/e2e/launch.spec.ts",),
        {"frontend": "false", "e2e": "true", "evals": "false"},
    ),
    (
        "e2e specs under a directory per entry door",
        ("tests/e2e/lms/launch.spec.ts", "tests/e2e/idp/login.spec.ts"),
        {"frontend": "false", "e2e": "true", "evals": "false"},
    ),
    (
        "an e2e directory holding no specs",
        ("tests/e2e/README.md",),
        {"frontend": "false", "e2e": "false", "evals": "false"},
    ),
)


def run_scripts(node: Any) -> list[str]:
    """Every `run:` script anywhere inside a parsed workflow fragment."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "run" and isinstance(value, str):
                found.append(value)
            found.extend(run_scripts(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(run_scripts(item))
    return found


def planted_tree(root: Path, files: tuple[str, ...]) -> Path:
    """A repository tree holding exactly `files`, each with a line of content."""
    root.mkdir(parents=True)
    for relative in files:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"planted by {Path(__file__).name}\n", encoding="utf-8")
    return root


def probe_outputs(scripts: list[str], tree: Path, workspace: Path) -> dict[str, str]:
    """Run the probe over `tree` and answer what it wrote to `$GITHUB_OUTPUT`."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.fail(
            "bash is not on PATH, so the probe cannot be executed. This fails rather than "
            "skipping: a skip here is indistinguishable from a probe that answers correctly."
        )

    output = workspace / "github-output"
    output.write_text("", encoding="utf-8")

    for index, script in enumerate(scripts):
        path = workspace / f"probe-{index}.sh"
        path.write_text(script, encoding="utf-8")
        # S603: the executable is a resolved absolute path, and the script is one
        # this test just wrote out of the repository's own workflow file.
        completed = subprocess.run(  # noqa: S603
            [bash, "-e", str(path)],
            cwd=tree,
            env=os.environ | {"GITHUB_OUTPUT": str(output)},
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            pytest.fail(
                f"The `{DETECT_JOB}` job's probe exited {completed.returncode} over a planted "
                f"tree, so it emitted nothing to judge.\n{completed.stderr.strip()}"
            )

    emitted: dict[str, str] = {}
    for line in output.read_text(encoding="utf-8").splitlines():
        match = EMITTED.match(line.strip())
        if match:
            emitted[match.group("name")] = match.group("value")
    return emitted


def test_every_detect_probe_answers_true_over_a_tree_that_holds_what_its_job_runs(
    ci_workflow_path: Path, ci_workflow: dict[str, Any], tmp_path: Path
) -> None:
    """Findings 1 and 2: a probe that cannot see the file turns its gate off and reports success.

    The `evals` case is the consequential one. `python -m tests.evals.runner` needs
    `tests/evals/runner.py`; the probe globs `tests/evals/**/*.py` without
    `globstar`, so it sees that file only one directory deeper than the runner can
    live. On the day E2 lands the runner, every real step in the `evals` job is
    skipped by its own `if:`, the notice step runs, **the job reports success**,
    and the §9.3 threat and self-harm recall floor has not executed. Nothing in the
    pipeline is red and nothing is skipped, so item 1's fix does not see it either.

    The `e2e` case is the same mechanism at lower cost: specs one directory down
    are invisible, so §9.2's both-doors requirement goes unchecked with the job
    green.

    **The empty-tree case comes first in the table and it is not decoration.** Two
    of the cases below assert that a probe answers *true*, and a probe that
    answered true to everything would satisfy both while turning every tolerance
    into a permanent lie in the other direction. The three false cases are what
    make the two true ones mean something.

    **The mutation this survives:** restore
    `compgen -G "tests/evals/**/*.py"` as the `evals` probe in
    `.github/workflows/ci.yml`, or `compgen -G "tests/e2e/*.spec.ts"` as the `e2e`
    probe. **The near miss that must stay green:** any fix that answers the same
    questions — `[ -f tests/evals/runner.py ]`, a `find`, or the existing glob with
    `shopt -s globstar` set — since this judges what the probe emits and not how it
    decides.
    """
    assert (
        ci_workflow
    ), f"{ci_workflow_path} does not exist or parsed to nothing, so there is no probe to run."

    jobs = ci_workflow.get("jobs") or {}
    job = jobs.get(DETECT_JOB)
    assert job, (
        f"{ci_workflow_path} declares no `{DETECT_JOB}` job (it declares {sorted(jobs)}). Every "
        "tolerance in this pipeline is conditioned on what that job emits; if it has been "
        "renamed, rename it here too rather than leaving this module looking for something that "
        "is gone."
    )

    scripts = run_scripts(job)
    assert scripts, (
        f"The `{DETECT_JOB}` job runs no script, so it emits nothing. Every gate conditioned on "
        "`needs.detect.outputs.*` then reads an empty string, takes its tolerant branch, and "
        "reports success having run none of its steps — which is this module's subject arriving "
        "by a different route."
    )

    wrong: list[str] = []
    for index, (case, files, expected) in enumerate(CASES):
        workspace = tmp_path / f"case-{index}"
        workspace.mkdir()
        tree = planted_tree(workspace / "repo", files)
        emitted = probe_outputs(scripts, tree, workspace)
        if emitted != expected:
            wrong.append(
                f"  {case}\n"
                f"    planted:  {list(files) or 'nothing'}\n"
                f"    expected: {expected}\n"
                f"    emitted:  {emitted or 'nothing'}"
            )

    assert not wrong, "\n".join(
        [
            f"The `{DETECT_JOB}` job's probes gave the wrong answer over planted trees:",
            *wrong,
            "",
            "A probe that answers false over a tree that has the thing does not skip its gate — "
            "it turns the real steps off by their own `if:`, runs the `::notice::` step in their "
            "place, and the job reports **success**. So the aggregate `CI` check sees a green job "
            "and nothing anywhere is red or skipped.",
            "",
            "`evals` is the expensive one: the job runs `python -m tests.evals.runner`, and SPEC "
            "§9.3's threat and self-harm recall floor is a hard gate — CLAUDE.md calls lowering "
            "it a safety decision rather than a build fix. A probe that cannot see the runner "
            "does not lower the floor; it stops it executing, which is worse and quieter. `e2e` "
            "is the same shape against §9.2's requirement that both entry doors are exercised in "
            "every run.",
            "",
            "The fix is not prescribed here. What has to hold is that a tree holding the file the "
            "job runs answers true, and a tree without it answers false.",
        ]
    )
