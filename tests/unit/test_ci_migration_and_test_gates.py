"""The migration and test gates stop tolerating an absent tree — ticket E0-04.

Acceptance criterion 5: "The CI `test` and `migration-drift` jobs run for real
and pass." E0-04's scope names the mechanism: "Enable the CI `migration-drift`
job and the `test` job, removing both tolerance flags."

Both jobs were written whole and then wrapped in a condition, so that a
repository with no `backend/alembic.ini` and no `tests/` would go green rather
than red — `.github/workflows/ci.yml` says so at the top of the `detect` job:
"As each E0 ticket lands, flip the matching `allow-missing` step in that job from
tolerant to enforcing." The flag is `if: needs.detect.outputs.<name> == 'true'`
on every real step, plus a step that prints a notice in its place. While it is
there, a change that deletes `alembic.ini` or breaks collection turns the gate
off instead of failing it, and the pull request still shows a green check.

The passing half of the criterion is the jobs' own business and cannot be
asserted from pytest. What can be asserted is that the tolerance is gone and
that the jobs still run something — and the two have to be asserted together,
because a job whose steps have all been deleted satisfies "no tolerance
condition" perfectly. `tests/unit/test_ci_health_gate.py` is the module that
learned that lesson; this one is separate because its subject is a different
pair of jobs and a different property.

**On duplicated machinery.** The two helpers below are cut-down cousins of the
ones in `test_ci_health_gate.py`. They are not shared, and the reason is that
sharing them would mean editing that module, whose own docstring explains at
length why it handles comments in two opposite ways on purpose. What is copied
here is the part both need and neither may drop: a `#` inside a `run:` block is
a line that ships without executing, so a commented-out `pytest` invocation must
not count as the job running one.
"""

import re
from pathlib import Path
from typing import Any

import pytest

# A shell comment and everything after it on the line, removed before a line is
# read as a command. Truncation rather than a parse: losing a command can only
# fail red, while fabricating one from text that never runs fails green.
SHELL_COMMENT = re.compile(r"#.*$")

# A shell line continuation, joined before anything reads the line.
CONTINUATION = re.compile(r"\\\s*\n\s*")

# The `detect` job's output that each gate was conditioned on, and a command the
# job must still be running once the condition is gone. The commands are the
# ones the ticket and the workflow already name — `alembic upgrade head &&
# alembic check` for the drift gate, `pytest` for the test gate — so this is not
# a new requirement, it is the non-vacuity guard for the requirement above it.
GATES = (
    pytest.param(
        "migration-drift",
        "migrations",
        ("alembic upgrade head", "alembic check"),
        id="migration-drift",
    ),
    pytest.param("test", "pytests", ("pytest",), id="test"),
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


def executed_lines(script: str) -> list[str]:
    """The lines of a `run:` script that could execute something, continuations joined."""
    lines: list[str] = []
    for raw in CONTINUATION.sub(" ", script).splitlines():
        line = SHELL_COMMENT.sub("", raw).strip()
        if line:
            lines.append(line)
    return lines


def conditions(node: Any) -> list[str]:
    """Every `if:` expression anywhere inside a parsed workflow fragment."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "if":
                found.append(str(value))
            found.extend(conditions(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(conditions(item))
    return found


@pytest.mark.parametrize(("job_name", "detect_output", "required_commands"), GATES)
def test_the_gate_runs_for_real_rather_than_when_the_tree_happens_to_exist(
    ci_workflow_path: Path,
    ci_workflow: dict[str, Any],
    job_name: str,
    detect_output: str,
    required_commands: tuple[str, ...],
) -> None:
    """E0-04 turns both gates on, which means deleting their escape hatch.

    The two assertions are one property and cannot be separated. Requiring the
    condition to be gone, on its own, is satisfied by a job with no steps left;
    requiring the commands to be present, on its own, is satisfied by a job that
    still skips every one of them. Together they say the job runs these commands
    unconditionally, which is what "runs for real" means.

    The condition is looked for by name — `needs.detect.outputs.<name>` — rather
    than by the absence of any `if:` at all, because a job may acquire a
    condition for some other reason later and this test should not be the thing
    that stops it. What it must not have is a condition on whether the thing it
    checks exists.
    """
    assert ci_workflow, (
        f"{ci_workflow_path} does not exist or parsed to nothing. The CI pipeline is what "
        "makes the §14.2 definition of done enforceable, so it existing is a precondition of "
        "this test meaning anything."
    )

    jobs = ci_workflow.get("jobs") or {}
    job = jobs.get(job_name)
    assert job, (
        f"{ci_workflow_path} declares no `{job_name}` job (it declares {sorted(jobs)}). "
        "E0-04's fifth criterion is about that job by name; if it has been renamed, rename "
        "it here too rather than leaving this test looking for something that is gone."
    )

    marker = f"detect.outputs.{detect_output}"
    tolerant = [condition for condition in conditions(job) if marker in condition]
    assert not tolerant, "\n".join(
        [
            f"The `{job_name}` job still skips itself when `detect` reports the tree is not "
            "there:",
            *(f"  if: {condition}" for condition in tolerant),
            "",
            "E0-04 enables this gate, and enabling it means removing the tolerance flag as "
            "well as writing the steps. While the condition is there, deleting "
            "`backend/alembic.ini` or breaking test collection turns the gate off instead of "
            "failing it, and the pull request still shows a green check — which is the "
            "failure mode the whole `detect` scheme was built to be temporary about.",
        ]
    )

    executed = [line for script in run_scripts(job) for line in executed_lines(script)]
    missing = [
        command for command in required_commands if not any(command in line for line in executed)
    ]
    assert not missing, "\n".join(
        [
            f"The `{job_name}` job does not run {missing}. It runs: {executed or 'nothing'}.",
            "",
            "This is the other half of the assertion above, and it is not a separate "
            "requirement: a job with its steps commented out or deleted has no tolerance "
            "condition either, so without this the test would pass most enthusiastically "
            "against a gate that had stopped checking anything.",
        ]
    )
