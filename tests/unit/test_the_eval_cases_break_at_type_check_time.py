"""A contract change breaks the eval set where SPEC §7.4 says it does — ticket E2-12.

SPEC §7.4, on why every task's output is a Pydantic model:

> The same models serve three purposes without duplication: the runtime contract,
> the API response schema, and the eval fixtures in §9.3 — so an eval case is a
> typed object, not a string comparison.

and SPEC §9.3 states the guarantee that buys:

> Cases are typed objects built from the same Pydantic contracts the tasks return
> (§7.4), so a contract change breaks its evals at type-check time rather than
> silently passing.

E2-12's own scope repeats it — "the validity eval set as typed
`CommentValidityOutput` cases (§7.4 — a contract change breaks evals at
type-check time)".

**That sentence is false unless a type checker reads `tests/evals/`.**
`pyproject.toml` sets `files = ["backend/app"]`, and `.github/workflows/ci.yml`
runs `mypy` bare plus one invocation per mock package. Nothing in that list
reaches `tests/`. So the eval set can be written in typed objects, be entirely
correct today, and go on importing a renamed verdict member or reading a removed
field with nothing anywhere saying so — the property is claimed by three
documents and enforced by none.

This module is the enforcing half. It does not run mypy; it asks whether any
configured invocation would read the eval tree, which is the question a green
`mypy` run cannot answer about itself.

**Red until the implementer's half lands**, since the configuration and the
workflow are both outside `tests/`.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
MAKEFILE = REPO_ROOT / "Makefile"

# The file that has to be type-checked, and the one the workflow's `detect` probe
# already pins by name. If the checker reaches this, it reaches the sets and the
# floors beside it.
EVAL_RUNNER_SOURCE = "tests/evals/runner.py"

# What is checked today, and the canary: the reader below must find this before
# its verdict about anything else is believed. A reader that returned an empty
# set would report "nothing type-checks the eval tree" over a repository where
# everything did, and the failure would read identically.
ALREADY_CHECKED = "backend/app"

# A mypy invocation at the start of a line, with whatever it was given. Anchored
# so a `pip install "mypy==..."` is not read as a run and a commented-out line is
# not read as a command.
MYPY_INVOCATION = re.compile(r"^\s*(?:@)?mypy\b(?P<arguments>[^\n]*)$", re.MULTILINE)

# Arguments that are options rather than paths.
OPTION = re.compile(r"^-")


def pyproject_document() -> dict[str, Any]:
    """`pyproject.toml`, parsed."""
    if not PYPROJECT.is_file():
        pytest.fail(f"{PYPROJECT} does not exist, so nothing here has a configuration to read.")
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def configured_files(document: dict[str, Any]) -> list[str]:
    """The paths a bare `mypy` would check, from `[tool.mypy] files`."""
    mypy = (document.get("tool") or {}).get("mypy") or {}
    declared = mypy.get("files") or []
    if isinstance(declared, str):
        return [declared]
    return [str(entry) for entry in declared]


def invocation_paths(source: str) -> list[list[str]]:
    """The path arguments of every `mypy` command in `source`, one list per command.

    A command with no path arguments is reported as an empty list, which is how a
    bare `mypy` — the one that falls back to the configured `files` — is
    distinguished from one given explicit paths.
    """
    found: list[list[str]] = []
    for match in MYPY_INVOCATION.finditer(source):
        arguments = [
            argument for argument in match.group("arguments").split() if not OPTION.match(argument)
        ]
        found.append(arguments)
    return found


def workflow_scripts() -> str:
    """Every `run:` block in the CI workflow, as one blob of text.

    Read as text rather than through the parsed YAML because what is wanted is
    the shell, and a `run:` block is a string either way. The Makefile below is
    read the same way for the same reason.
    """
    workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    if not workflow.is_file():
        pytest.fail(f"{workflow} does not exist.")
    return workflow.read_text(encoding="utf-8")


def covers(root: str, relative: str) -> bool:
    """Whether checking `root` reaches `relative`."""
    root = root.strip().removeprefix("./").rstrip("/")
    if root in ("", "."):
        return True
    return relative == root or relative.startswith(f"{root}/")


def test_the_type_checker_reads_the_eval_tree() -> None:
    """SPEC §9.3's "breaks its evals at type-check time", made true rather than asserted.

    The eval cases import `ValidityVerdict` and `CommentValidityOutput` out of
    `app.ai.contracts` and the runner reads `.verdict` and `.prompt_version` off
    what a task returns. Every one of those is a claim mypy could check and does
    not, because nothing points it at `tests/`.

    The failure this leaves is the quiet kind. Rename a verdict member, drop a
    field, change an annotation: `backend/app` still type-checks, the unit suite
    still passes because the eval set is not executed by it, and the breakage
    surfaces on the next live eval run — which happens only on an AI-touching
    pull request, which is exactly the pull request that made the change.

    **What is asserted is coverage, not a spelling.** Adding `tests/evals` to
    `[tool.mypy] files`, giving the workflow's `mypy` line an explicit path, or
    checking the whole repository all satisfy it. Which one is the implementer's
    call; that none of them is true today is the finding.

    **The canary runs first.** The reader is required to find `backend/app`,
    which is checked today, before its verdict about the eval tree is believed —
    a reader that had gone blind would report the same thing as a repository that
    checks nothing (`docs/MISTAKES.md` entry 3).

    **The mutation this kills:** ship typed eval cases and quote SPEC §9.3's
    sentence in a docstring, which is what makes the guarantee a convention.
    **The near miss that must stay green:** any invocation that reaches the tree,
    including one that reaches the whole repository.
    """
    document = pyproject_document()
    roots: list[tuple[str, str]] = [
        (f"[tool.mypy] files = {entry!r}", entry) for entry in configured_files(document)
    ]

    for label, source in (
        (".github/workflows/ci.yml", workflow_scripts()),
        (
            "Makefile",
            MAKEFILE.read_text(encoding="utf-8") if MAKEFILE.is_file() else "",
        ),
    ):
        for arguments in invocation_paths(source):
            if not arguments:
                # A bare `mypy` falls back to the configured `files`, already
                # collected above. Counting it as covering everything would make
                # this test pass over exactly today's configuration.
                continue
            roots.extend((f"{label}: mypy {argument}", argument) for argument in arguments)

    assert any(covers(root, f"{ALREADY_CHECKED}/config.py") for _, root in roots), "\n".join(
        [
            "this test's reader found nothing that type-checks "
            f"`{ALREADY_CHECKED}`, which is checked today by `[tool.mypy] files`.",
            f"  what it found: {[label for label, _ in roots] or 'nothing at all'}",
            "",
            "The reader has gone blind, and with it blind the assertion below would report "
            "that nothing checks the eval tree over a repository in which everything is "
            "checked.",
        ]
    )

    reaching = [label for label, root in roots if covers(root, EVAL_RUNNER_SOURCE)]
    assert reaching, "\n".join(
        [
            f"nothing type-checks `{EVAL_RUNNER_SOURCE}`.",
            f"  what is checked: {[label for label, _ in roots]}",
            "",
            "SPEC §9.3: 'Cases are typed objects built from the same Pydantic contracts the "
            "tasks return (§7.4), so a contract change breaks its evals at type-check time "
            "rather than silently passing.' E2-12's scope repeats it. With no checker "
            "reading `tests/evals/`, that sentence describes an intention rather than a "
            "guarantee: a renamed verdict member or a removed field leaves `backend/app` "
            "green, leaves the unit suite green — the eval set is data, not an executed "
            "test — and surfaces on the next live eval run, which is the run the change "
            "itself triggers.",
            "",
            "Any of these fixes it: add `tests/evals` to `[tool.mypy] files`, give the "
            "workflow's `mypy` step an explicit path, or check the repository. Which one is "
            "a decision; having none of them is the defect.",
        ]
    )
