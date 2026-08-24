"""The image gate is one check run from two places — ticket E0-36, item 4.

E0-12 added four re-exclusions to `.dockerignore` — `backend/**/*~`, `*.orig`,
`*.rej`, `*.bak` — because `pyproject.toml` ships `app/ai/prompts/**/*` as package
data. Any non-hidden file left in that directory is copied into the build context,
packaged into the wheel and installed into the runtime image. Measured, not
assumed: `scratch-notes.txt` and `validity.v1.md~` are both carried into the
wheel. Delete any of those four lines and every gate stays green, and the failure
they prevent — a key parked beside a prompt while debugging, baked into an image
layer — is invisible in review because the file is untracked.

**A test asserting `.dockerignore`'s text is not acceptable**, and E0-36 says so:
it would pass against a typo'd pattern, which is the same green checkmark over a
context that carried the file anyway. The check has to build the image and inspect
what reached it, which makes it a Docker-gate concern rather than a unit test.

So what this module asserts is the structural half, and only that: the `docker`
job in `.github/workflows/ci.yml` and the `docker-build` target in the `Makefile`
both run such a check, and they run **the same** check rather than two copies that
can drift apart. `scripts/ci/check_job_runtime.sh` is the precedent — the comment
at the top of it says why it is a script and not two copies of the same shell:
"the polling below is the part most easily written wrong, and writing it twice is
writing that mistake twice."

**What this module cannot see.** Whether the shared script actually detects a
planted file. Nothing here executes it, so a script that inspects the wrong image,
greps for the wrong thing, or exits 0 on its own failure would pass every
assertion below. That verification is a mutation on the Docker gate itself — plant
a `backend/app/ai/prompts/*.bak`, run the gate, watch it fail — and it belongs to
whoever runs the gate. What this module holds is the part that would otherwise
rot: the check being wired into both callers, and staying wired into both.

`tests/unit/test_ci_health_gate.py` is the other module about the `docker` job.
This is separate because its subject is the agreement between two files rather
than the contents of one job, and because that module's docstring explains at
length why it handles comments in two opposite ways on purpose — a change there to
share machinery would put that explanation at risk for no gain.
"""

import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE_PATH = REPO_ROOT / "Makefile"

DOCKER_JOB = "docker"
MAKE_TARGET = "docker-build"

# The shared check E0-36 item 4 adds. **This name is the implementer's to
# choose** — the ticket names no module, and what this test asserts is that one
# script does the inspection and that both callers run it, not that it is called
# this. If it lands under another name, this constant moves in the same commit and
# nothing else about the test changes.
IMAGE_CONTENT_CHECK = "scripts/ci/check_image_contents.sh"

# A check script invoked from either caller. Leading `./` is stripped so that
# `./scripts/ci/x.sh` and `scripts/ci/x.sh` are one script, which they are.
SHARED_SCRIPT = re.compile(r"(?:\./)?(?P<path>scripts/ci/[A-Za-z0-9_.-]+)")

# A shell comment and everything after it on the line, cut before a line is read
# as a command — a `#` inside a `run:` block, or inside a Makefile recipe, is a
# line that ships without executing. Truncation rather than a parse, in the same
# direction and for the same reason as `tests/unit/test_ci_health_gate.py`: losing
# a command can only fail red, while fabricating one from text that never runs
# fails green.
SHELL_COMMENT = re.compile(r"#.*$")

# A shell line continuation, joined before anything reads the line. The Makefile's
# `docker-build` recipe is one long continued command, so without this every check
# in it reads as part of a line that was never scanned.
CONTINUATION = re.compile(r"\\\s*\n\s*")


def run_scripts(node: Any) -> list[str]:
    """Every `run:` script anywhere inside a parsed workflow fragment.

    A third copy of a helper that exists in two other modules, for the reason
    `test_ci_migration_and_test_gates.py` gives: sharing it would mean editing
    `test_ci_health_gate.py`, whose docstring explains at length why it treats
    comments in two opposite ways on purpose.
    """
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
    """The lines of a shell script that could execute something, continuations joined."""
    lines: list[str] = []
    for raw in CONTINUATION.sub(" ", script).splitlines():
        line = SHELL_COMMENT.sub("", raw).strip()
        if line:
            lines.append(line)
    return lines


def recipe_of(makefile: str, target: str) -> str:
    """The recipe lines of one Makefile target, tabs stripped, in order.

    A recipe is the run of tab-indented lines after the target's header. Blank
    lines and comment lines do not end one — make ignores both — so neither ends
    the collection here either; anything else at column zero does.
    """
    header = re.compile(rf"^{re.escape(target)}\s*:")
    collected: list[str] = []
    inside = False
    for raw in makefile.splitlines():
        if not inside:
            if header.match(raw):
                inside = True
            continue
        if raw.startswith("\t"):
            collected.append(raw[1:])
            continue
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        break
    return "\n".join(collected)


def recipe_commands(makefile: str, target: str) -> list[str]:
    """The commands one Makefile target runs, continuations joined and prefixes dropped.

    `@`, `-` and `+` at the start of a recipe line are make's own prefixes rather
    than part of the command, so they are removed before the line is read.
    """
    commands: list[str] = []
    for line in executed_lines(recipe_of(makefile, target)):
        command = line.lstrip("@-+").strip()
        if command:
            commands.append(command)
    return commands


def scripts_invoked(lines: list[str]) -> set[str]:
    """Every `scripts/ci/…` check invoked by any of `lines`."""
    return {match.group("path") for line in lines for match in SHARED_SCRIPT.finditer(line)}


def docker_job_commands(ci_workflow: dict[str, Any]) -> list[str]:
    """Every command the `docker` job runs, in step order."""
    job = (ci_workflow.get("jobs") or {}).get(DOCKER_JOB) or {}
    return [line for script in run_scripts(job) for line in executed_lines(script)]


def test_the_docker_gate_and_the_makefile_run_the_same_shared_checks(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """The two callers of the build gate do not drift apart.

    `CLAUDE.md`: "`make ci` runs the same gates as `.github/workflows/ci.yml`, in
    the same order… when the two drift, the workflow is the source of truth and
    this file is the bug." That has already happened once in this exact pair — the
    workflow named `mock-lms` in its health waits from E0-14 and the Makefile did
    not catch up until E0-16, which the `docker-build` recipe's comment records.

    A check added to one caller and not the other is worse than one added to
    neither: the developer who runs `make docker-build` before pushing is told the
    build is clean by a gate that never ran the check, which is this ticket's whole
    subject one file over.

    **The mutation this survives:** delete `./scripts/ci/check_job_runtime.sh`
    from the `Makefile`'s `docker-build` recipe, leaving it in the workflow.
    **The near miss that must stay green:** reordering the recipe's lines, or
    redirecting an invocation's output with `>/dev/null` as the recipe already
    does elsewhere.
    """
    assert ci_workflow, (
        f"{ci_workflow_path} does not exist or parsed to nothing, so the workflow side of this "
        "comparison is empty and the two sides could not disagree."
    )
    assert MAKEFILE_PATH.is_file(), (
        f"{MAKEFILE_PATH} does not exist. It is the local half of every CI gate; without it this "
        "comparison has one side."
    )

    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    workflow_commands = docker_job_commands(ci_workflow)
    make_commands = recipe_commands(makefile, MAKE_TARGET)

    assert workflow_commands, (
        f"The `{DOCKER_JOB}` job in {ci_workflow_path} runs no commands — it has been renamed, "
        "emptied, or commented out. Everything below compares two sets of scripts, and an empty "
        "set agrees with nothing rather than with everything."
    )
    assert make_commands, (
        f"The `{MAKE_TARGET}` target in {MAKEFILE_PATH} has no recipe. Same reason: this test "
        "compares what two callers run, and a caller that runs nothing makes the comparison "
        "vacuous rather than satisfied."
    )

    in_workflow = scripts_invoked(workflow_commands)
    in_makefile = scripts_invoked(make_commands)

    assert in_workflow, (
        f"The `{DOCKER_JOB}` job invokes no `scripts/ci/` check at all. It runs: "
        f"{workflow_commands}."
    )
    assert in_makefile, (
        f"The `{MAKE_TARGET}` target invokes no `scripts/ci/` check at all. It runs: "
        f"{make_commands}."
    )

    only_in_workflow = sorted(in_workflow - in_makefile)
    only_in_makefile = sorted(in_makefile - in_workflow)

    assert not (only_in_workflow or only_in_makefile), "\n".join(
        [
            "The CI `docker` job and `make docker-build` do not run the same checks:",
            f"  only in {ci_workflow_path.name}: {only_in_workflow or 'nothing'}",
            f"  only in the Makefile: {only_in_makefile or 'nothing'}",
            "",
            "These two are meant to be the same gate run from two places, and a check present in "
            "only one of them is a check that half the people who run the gate never run. The "
            "workflow is the source of truth when they disagree (CLAUDE.md), so the usual repair "
            "is to add the missing line to the Makefile — not to remove it from the workflow.",
        ]
    )


def test_both_docker_gates_inspect_the_built_image_for_what_dockerignore_re_excludes(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """E0-36 criterion 4, as far as a unit test can reach it.

    Deleting `backend/**/*~`, `*.orig`, `*.rej` or `*.bak` from `.dockerignore`
    leaves every gate green while the prompts directory becomes a path by which
    an untracked file — a key parked beside a prompt while debugging — reaches an
    image layer. The check that closes it has to build the image and look inside,
    so it is a script the Docker gate runs; what this asserts is that both callers
    run it, and the same one.

    **This test names the script, and that name is the one thing here that is a
    guess.** The ticket specifies the property and not the file, so the constant
    at the top of this module is the implementer's to set. If it lands as
    something else, move the constant in the same commit; the property being
    asserted does not change.

    **What this does not assert, said plainly**: that the script detects anything.
    A script that inspects the wrong image or exits 0 whatever it finds satisfies
    this test completely. Only running the gate against a planted file can answer
    that, and E0-36's criterion says as much.

    **The mutation this survives:** delete the image-content check from both the
    `docker` job and the `docker-build` recipe — the mutation the test above
    cannot see, because removing it from both keeps the two callers in perfect
    agreement. **The near miss that must stay green:** moving the invocation into
    a different step of the `docker` job, or a different line of the recipe.
    """
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    in_workflow = scripts_invoked(docker_job_commands(ci_workflow))
    in_makefile = scripts_invoked(recipe_commands(makefile, MAKE_TARGET))

    assert in_workflow and in_makefile, (
        "One of the two callers invokes no `scripts/ci/` check at all, so this test would be "
        "reporting a missing check when the truth is that the scan found nothing to read. "
        "`test_the_docker_gate_and_the_makefile_run_the_same_shared_checks` diagnoses that."
    )

    missing = [
        where
        for where, invoked in (
            (str(ci_workflow_path.relative_to(REPO_ROOT)), in_workflow),
            ("Makefile", in_makefile),
        )
        if IMAGE_CONTENT_CHECK not in invoked
    ]

    assert not missing, "\n".join(
        [
            f"`{IMAGE_CONTENT_CHECK}` is not run by: {missing}.",
            f"  the `{DOCKER_JOB}` job runs {sorted(in_workflow)}",
            f"  the `{MAKE_TARGET}` target runs {sorted(in_makefile)}",
            "",
            "E0-12 added four re-exclusions to `.dockerignore` so that editor and merge debris "
            "in `backend/app/ai/prompts/` cannot reach the runtime image, and `pyproject.toml` "
            "ships that whole directory as package data, so the path is real: a `.bak` beside a "
            "prompt is packaged into the wheel and installed into the image. Deleting any of the "
            "four lines leaves every gate green today.",
            "",
            "A test on `.dockerignore`'s text is not the fix — it passes against a typo'd "
            "pattern, which carries the file just as surely. The check builds the image and "
            "inspects what reached it, and it lives in one script both callers run, like "
            "`scripts/ci/check_job_runtime.sh` and for the reason stated at the top of it.",
            "",
            "If the check landed under another name, move `IMAGE_CONTENT_CHECK` at the top of "
            "this module rather than adding a second name to it: two names is the drift this "
            "module exists to refuse.",
        ]
    )

    script = REPO_ROOT / IMAGE_CONTENT_CHECK
    assert script.is_file(), (
        f"Both callers name `{IMAGE_CONTENT_CHECK}` and the file is not in the repository, so "
        "every run of the Docker gate would fail on a missing script rather than on a stray file "
        "in the image."
    )
