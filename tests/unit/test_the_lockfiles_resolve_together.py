"""The dev lockfile is resolved against the runtime one — ticket E0-36, item 5.

`make lock` runs `pip-compile` twice: once for `requirements.txt` and once, with
`--extra dev`, for `requirements-dev.txt`. The second resolution currently has no
knowledge of the first, so two independent resolutions of overlapping requirement
sets can — and did — settle on different versions of the same package.
`charset-normalizer` skewed to two versions during E0-13; every test passed and
only `pip-audit` saw it (`docs/MISTAKES.md` entry 25). The fix is `-c
requirements.txt` on the dev compile: the runtime resolution becomes a constraint
on the dev one rather than a sibling of it.

The consequence is worth stating, because it is what makes this a gate-fidelity
item rather than tidying. The test suite runs against `requirements-dev.txt` and
the image ships `requirements.txt`. When the two disagree about a package, every
test in this repository passes against a version of it that is not the version
that deploys — so the suite is green over a closure nobody runs.

**Two things are asserted here, and the second is the criterion rather than the
mechanism.** That the recipe carries the constraint, and that the two lockfiles
in the tree actually agree. The first can be satisfied by a recipe nobody has run;
the second is the property the recipe exists to produce, and it stays true only
while both files are regenerated together.

**On "the recipe has to keep matching `.github/workflows/ci.yml`".** The workflow
runs no `pip-compile` at all — locking is a developer's step, and CI only consumes
what was committed. So "matching" here is not two copies of a command: it is that
every lockfile CI installs from is a file `make lock` writes. A lockfile CI reads
and `make lock` does not produce is one that drifts silently, which is the same
defect this ticket is about in a different place.
"""

import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE_PATH = REPO_ROOT / "Makefile"

RUNTIME_LOCKFILE = "requirements.txt"
DEV_LOCKFILE = "requirements-dev.txt"

LOCK_TARGET = "lock"

# A pinned requirement, at the start of a line. Hash lines and `# via …`
# annotations are indented, so anchoring at column zero leaves them out without
# having to describe them.
PIN = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*(?P<version>[^\s\\;#]+)")

# A requirements file handed to `pip install` or `pip-audit`. Both spellings, and
# the `=` form of the long one. The leading `(?:^|\s)` is what keeps `-r` out of
# `--require-hashes`.
REQUIREMENTS_FLAG = re.compile(r"(?:^|\s)(?:-r|--requirement)[=\s]+(?P<path>\S+)")

# Where a `pip-compile` invocation writes its result.
OUTPUT_FILE_FLAG = re.compile(r"(?:^|\s)--output-file[=\s]+(?P<path>\S+)")

SHELL_COMMENT = re.compile(r"#.*$")
CONTINUATION = re.compile(r"\\\s*\n\s*")


def normalised(name: str) -> str:
    """A distribution name in PEP 503 form, so `PyYAML` and `pyyaml` are one package."""
    return re.sub(r"[-_.]+", "-", name).lower()


def executed_lines(script: str) -> list[str]:
    """The lines of a shell script that could execute something, continuations joined."""
    lines: list[str] = []
    for raw in CONTINUATION.sub(" ", script).splitlines():
        line = SHELL_COMMENT.sub("", raw).strip()
        if line:
            lines.append(line)
    return lines


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


def recipe_of(makefile: str, target: str) -> str:
    """The recipe lines of one Makefile target, tabs stripped, in order."""
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
    """The commands one Makefile target runs, make's `@`, `-` and `+` prefixes dropped."""
    return [
        command
        for command in (
            line.lstrip("@-+").strip() for line in executed_lines(recipe_of(makefile, target))
        )
        if command
    ]


def pins(path: Path) -> dict[str, set[str]]:
    """Every package a lockfile pins, in PEP 503 form, with the versions it pins it to.

    A set of versions rather than one, so that a file which somehow pins the same
    package twice is visible here rather than resolved silently by whichever line
    was read last.
    """
    found: dict[str, set[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = PIN.match(line)
        if match:
            found.setdefault(normalised(match.group("name")), set()).add(match.group("version"))
    return found


def test_make_lock_compiles_the_dev_lockfile_against_the_runtime_lockfile() -> None:
    """E0-36 criterion 5, first half: the dev resolution is constrained, not independent.

    Without `-c requirements.txt` the two compiles are two separate solves over
    overlapping requirement sets, and nothing requires them to agree. They already
    disagreed once — `charset-normalizer`, during E0-13, caught by `pip-audit` and
    by nothing else in the pipeline.

    **The mutation this survives:** remove `-c requirements.txt` from the second
    `pip-compile` in the `Makefile`'s `lock` recipe. **The near miss that must
    stay green:** spelling it `--constraint=requirements.txt`, or moving it to a
    different position among the flags.
    """
    assert (
        MAKEFILE_PATH.is_file()
    ), f"{MAKEFILE_PATH} does not exist, so there is no recipe to read."

    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    compiles = [
        command for command in recipe_commands(makefile, LOCK_TARGET) if "pip-compile" in command
    ]

    assert compiles, (
        f"The `{LOCK_TARGET}` target runs no `pip-compile` at all, so this test would be "
        "asserting a property of a command that is not there. `make lock` is what regenerates "
        "both lockfiles (ADR 0005); if it has been renamed or replaced, point this test at what "
        "replaced it."
    )

    def writes(command: str) -> str | None:
        match = OUTPUT_FILE_FLAG.search(command)
        return match.group("path").removeprefix("./") if match else None

    dev_compiles = [command for command in compiles if writes(command) == DEV_LOCKFILE]
    runtime_compiles = [command for command in compiles if writes(command) == RUNTIME_LOCKFILE]

    assert runtime_compiles, (
        f"No `pip-compile` in the `{LOCK_TARGET}` target writes `{RUNTIME_LOCKFILE}` (they write "
        f"{[writes(command) for command in compiles]}). The constraint asserted below points at "
        "that file, so if nothing produces it the constraint would name a stale artifact."
    )
    assert dev_compiles, (
        f"No `pip-compile` in the `{LOCK_TARGET}` target writes `{DEV_LOCKFILE}` (they write "
        f"{[writes(command) for command in compiles]}). That is the resolution this criterion is "
        "about; without it there is nothing here to constrain."
    )

    constraint = re.compile(
        rf"(?:^|\s)(?:-c|--constraint)[=\s]+(?:\./)?{re.escape(RUNTIME_LOCKFILE)}\b"
    )

    # Run against the text it claims to catch before it is believed
    # (`docs/MISTAKES.md` entry 3): a pattern that matches nothing reports the
    # constraint missing just as loudly whether it is missing or the pattern has
    # gone blind, and the two failures have different repairs.
    for sample in (
        f"pip-compile -c {RUNTIME_LOCKFILE} --extra dev",
        f"pip-compile --constraint={RUNTIME_LOCKFILE}",
    ):
        assert constraint.search(sample), (
            f"The search in this test does not match {sample!r}, which is the flag it exists to "
            "find. It has gone blind, and the assertion below would fail against a correct recipe."
        )
    assert not constraint.search("pip-compile --output-file=requirements.txt pyproject.toml"), (
        "The search in this test matches a `pip-compile` that merely writes "
        f"`{RUNTIME_LOCKFILE}` rather than one constrained against it, so it would report the "
        "runtime compile as satisfying a criterion about the dev one."
    )

    unconstrained = [command for command in dev_compiles if not constraint.search(command)]

    assert not unconstrained, "\n".join(
        [
            f"The dev lockfile is compiled without `-c {RUNTIME_LOCKFILE}`:",
            *(f"  {command}" for command in unconstrained),
            "",
            "Two independent resolutions of overlapping requirement sets are free to pick "
            "different versions of the same package, and did: `charset-normalizer` skewed to two "
            "versions during E0-13, every test passed, and only `pip-audit` saw it "
            "(`docs/MISTAKES.md` entry 25).",
            "",
            "The suite runs against the dev closure and the image ships the runtime one, so a "
            "skew means the tests are green over a version of a package that never deploys.",
        ]
    )


def test_the_two_lockfiles_pin_every_shared_package_to_one_version() -> None:
    """E0-36 criterion 5, as the property rather than as the flag.

    The recipe above is the mechanism; this is the outcome it exists to produce,
    and it is asserted separately because the two fail apart. A recipe carrying
    the constraint but never re-run leaves the committed files skewed, and that is
    exactly the state E0-13 shipped.

    **The mutation this survives:** change `charset-normalizer==3.5.1` in
    `requirements-dev.txt` to `charset-normalizer==3.5.0`. **The near miss that
    must stay green:** adding a package to `requirements-dev.txt` that is not in
    `requirements.txt` at all — the dev closure is a superset, and packages it
    alone holds are the normal case, not a skew.
    """
    runtime_path = REPO_ROOT / RUNTIME_LOCKFILE
    dev_path = REPO_ROOT / DEV_LOCKFILE

    assert runtime_path.is_file() and dev_path.is_file(), (
        f"One of `{RUNTIME_LOCKFILE}` and `{DEV_LOCKFILE}` is missing. Both are committed (ADR "
        "0005) and both are what CI installs from; with one absent this comparison has one side."
    )

    runtime = pins(runtime_path)
    dev = pins(dev_path)

    assert runtime, f"No pinned requirement was read out of `{RUNTIME_LOCKFILE}`."
    assert dev, f"No pinned requirement was read out of `{DEV_LOCKFILE}`."

    shared = sorted(set(runtime) & set(dev))
    assert shared, (
        f"`{RUNTIME_LOCKFILE}` and `{DEV_LOCKFILE}` have no package in common, which cannot be "
        "true — the dev closure is the runtime closure plus the test tools. Either a file was "
        "read wrongly or the pin pattern has gone blind, and either way the comparison below "
        "would pass having compared nothing."
    )

    skewed = {
        name: sorted(runtime[name] | dev[name])
        for name in shared
        if runtime[name] | dev[name] != runtime[name] & dev[name]
    }

    assert not skewed, "\n".join(
        [
            "These packages are pinned to different versions in the two lockfiles:",
            *(f"  {name}: {versions}" for name, versions in sorted(skewed.items())),
            "",
            "The test suite installs `requirements-dev.txt` and the image ships "
            "`requirements.txt`, so every test above is running against a version of these "
            "packages that no deployment has. This happened once already — "
            "`docs/MISTAKES.md` entry 25 — and `pip-audit` was the only thing that noticed.",
            "",
            "Regenerate both with `make lock`, which compiles the dev resolution under "
            f"`-c {RUNTIME_LOCKFILE}` so the runtime pins bind the dev ones.",
        ]
    )


def test_ci_installs_only_lockfiles_that_make_lock_writes(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """The other half of criterion 5: the workflow still matches the recipe.

    The workflow runs no `pip-compile` — locking is a developer's step and CI
    consumes what was committed — so "matching" is not two copies of one command.
    It is that every requirements file CI installs or audits is one `make lock`
    produces. A lockfile CI reads and nothing regenerates is a file that drifts
    from `pyproject.toml` with nothing to notice, which is this ticket's subject
    in a third place.

    **The mutation this survives:** add
    `pip install --require-hashes -r requirements-test.txt` to a job in
    `.github/workflows/ci.yml` without adding a compile for it to `make lock`.
    **The near miss that must stay green:** adding a third `pip-compile` to
    `make lock` that CI does not install from — `lock` may write more than CI
    reads, and this asserts the direction that matters.
    """
    assert ci_workflow, f"{ci_workflow_path} does not exist or parsed to nothing."

    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    written = {
        match.group("path").removeprefix("./")
        for command in recipe_commands(makefile, LOCK_TARGET)
        for match in [OUTPUT_FILE_FLAG.search(command)]
        if match
    }
    assert written, (
        f"The `{LOCK_TARGET}` target writes no lockfile, so every file CI installs would be "
        "reported as unregenerated and this test would be describing a different defect from the "
        "one it found."
    )

    installed = {
        match.group("path").removeprefix("./")
        for script in run_scripts(ci_workflow)
        for line in executed_lines(script)
        for match in REQUIREMENTS_FLAG.finditer(line)
    }
    assert installed, (
        f"No job in {ci_workflow_path} installs from a requirements file. Every Python job in "
        "this pipeline installs the locked closure with `--require-hashes`; if none does, the "
        "comparison below is vacuous and something much larger has changed."
    )

    unregenerated = sorted(installed - written)

    assert not unregenerated, "\n".join(
        [
            f"CI installs from lockfiles `make {LOCK_TARGET}` does not write: {unregenerated}.",
            f"  the recipe writes: {sorted(written)}",
            f"  the workflow installs: {sorted(installed)}",
            "",
            "A lockfile nothing regenerates drifts from `pyproject.toml` silently, and it is "
            "hash-pinned, so it goes on installing exactly what it always did — including a "
            "version with an advisory against it — while looking as authoritative as the files "
            "that are maintained. Add the compile to `make lock` in the same change (ADR 0005), "
            "or stop installing the file.",
        ]
    )
