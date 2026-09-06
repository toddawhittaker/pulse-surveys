"""Every document that names the Python runtime names the same one — FIX-04.

Four kinds of document declare which Python this project runs on, and until this
module nothing read more than one of them at a time:

  - the `FROM python:` stages in the four Dockerfiles (`backend/`, `mock-lms/`,
    `mock-idp/`, `mock-ai/`), which are the interpreters the images actually ship;
  - `PYTHON_VERSION` in `.github/workflows/ci.yml`, which is the interpreter every
    Python job in the pipeline installs and therefore the one the suite, `ruff` and
    `mypy` run under in CI;
  - `requires-python` in `pyproject.toml`, which is the floor `pip-compile` resolves
    the hash-verified lockfiles against, so it decides which wheels the closure may
    contain;
  - `python_version` under `[tool.mypy]` in `pyproject.toml`, which is the standard
    library and the language level the type check is performed against.

**Nothing else ties them together.** This is `test_types_node_tracks_runtime.py`'s
subject in the other language, and the same split holds: Dependabot's `docker`
ecosystem reads `FROM` lines and proposes an image bump on its own, its
`github-actions` ecosystem updates `uses:` lines and not an `env:` value so nothing
reads `PYTHON_VERSION` at all, and nothing whatever reads `requires-python` or the
mypy setting against either of the other two. Move any one of them and every gate
stays green — while the consequences are not cosmetic. An image ahead of CI ships an
interpreter no gate in this repository has run. CI ahead of the images runs the whole
suite on an interpreter that is not the one deployed. A `requires-python` floor behind
either lets `pip-compile` pick wheels for an older interpreter into the lockfile the
image installs from. A mypy `python_version` behind either type-checks against a
standard library the runtime does not have, and passes.

**The tie is major and minor, and that is a Python-specific choice.** The Node guard
compares majors, because Node's compatibility line is the major. Python's is not:
3.13 and 3.14 are different languages to `mypy`, different ABI tags to every compiled
wheel (`cp313` against `cp314`) and different standard libraries, while 3.14.6 and
3.14.7 are none of those things. Comparing majors here would let a stage left behind
on 3.13 agree with a CI runtime on 3.14, which is the exact defect this module exists
to refuse; comparing whole versions would demand a lockstep patch bump across four
Dockerfiles, a workflow and two `pyproject.toml` settings every time the base image
moves, and the patch is genuinely allowed to differ — the image is pinned to an exact
patch and a digest, and `PYTHON_VERSION: '3.14'` names no patch at all.

**`requires-python` is a range, not a version.** It is written `">=3.14"`, so it is
read here by taking the floor out of the specifier deliberately, and a form this
cannot take a floor from fails rather than being skipped. Running it through the
plain-version pattern the other three go through would refuse the one legal spelling
the project uses.

**Two of FIX-04's seven pinned places are deliberately not read here**: the `3.13`
mention in a `docker-compose.yml` comment and the `python:3.13-slim` mention in a
`pyproject.toml` comment. Both are comments, and both parsers discard them before
this module sees anything — so a guard that claimed to cover them would be claiming
something it cannot do. The ticket's acceptance criterion 3 covers those two by grep;
this module covers the five that are declarations.

**A version this cannot read fails rather than being skipped.** `python:3-slim`,
`python:slim-bookworm` and `python:latest` are all legal image tags, and none of them
has a minor to compare honestly. Guessing one would make the agreement this reports
weaker than the agreement it claims, and CLAUDE.md pins runtimes and images exactly.
"""

import re
import sys
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

# The runtime FIX-04 moves this project to, as major and minor. A literal, and it has
# to be one: every other value in this module is read out of the tree, so comparing
# the tree against itself would be perfectly green on a tree that had not moved at
# all. When the next runtime ticket lands — 3.15 is out of FIX-04's scope until its
# compiled wheels mature — this constant moves in it, with everything below.
PINNED_RUNTIME = "3.14"

# The workflow variable every Python job's `python-version:` reads.
PYTHON_VERSION = "PYTHON_VERSION"

# The `[tool.mypy]` setting naming the language level the type check is performed at.
MYPY_PYTHON_VERSION = "python_version"

# Installed and vendored trees are not this repository's declarations. `.venv` matters
# most: a third-party package installed there can ship a Dockerfile of its own pinning
# whatever Python it likes, and reading it would fail this test for a reason that has
# nothing to do with the runtime this project deploys. The exclusion is proved not to
# have eaten the real files by the control test at the foot of this module.
VENDORED = frozenset({"node_modules", ".venv", "venv", ".git", "site-packages"})

# What a Dockerfile is called. `Dockerfile` is what this repository uses; the other two
# spellings are the conventional ones for a second file beside it, and they cost
# nothing to look for. Copied from `test_types_node_tracks_runtime.py`, which asks the
# same question of the same files about the other runtime.
DOCKERFILE_NAMES = ("Dockerfile", "Dockerfile.*", "*.Dockerfile")

# A build stage on the Python image. `FROM`, any number of `--platform=`-style flags,
# an optional registry and namespace, then `python:` and the tag — which ends at the
# digest `@sha256:...` that ADR 0007 requires beside it, or at the whitespace before
# `AS <stage>`. Case-insensitive on the keyword alone, because a Dockerfile
# instruction is case-insensitive and an image name is not.
PYTHON_STAGE = re.compile(
    r"^\s*(?i:FROM)\s+(?:--\S+\s+)*(?:[^\s/]+/)*python:(?P<tag>[^@\s]+)",
    re.MULTILINE,
)

# A version this test can take a major and minor from: at least two dot-separated
# numbers. `3.14` and `3.14.7` are readable; a bare `3`, a variant name (`slim`,
# `latest`) and a range are not — see the module docstring.
READABLE_VERSION = re.compile(r"^\d+\.\d+(\.\d+)*$")

# The floor of a `requires-python` specifier. `>=3.14` and `>=3.14,<3.15` both give
# `3.14`. Only `>=` is read: `>`, `~=` and `==3.14.*` each mean something this module
# would have to guess about, and a guess is what the assertion below refuses to make.
REQUIRES_PYTHON_FLOOR = re.compile(r">=\s*(?P<version>\d+(?:\.\d+)*)")

# The four images this repository builds today, each of which certainly has a Python
# stage. Written down only in the control test, and only so that the collectors above
# can be required to *find* something on a subject that has it.
IMAGES_WITH_A_PYTHON_STAGE = (
    "backend/Dockerfile",
    "mock-lms/Dockerfile",
    "mock-idp/Dockerfile",
    "mock-ai/Dockerfile",
)


def dockerfiles() -> list[Path]:
    """Every Dockerfile this repository declares, installed and vendored trees excluded.

    Structural: the comparison names no file, so a Python stage added in a new image
    joins it by existing rather than by being added to a list here.
    """
    return sorted(
        {
            path
            for pattern in DOCKERFILE_NAMES
            for path in REPO_ROOT.rglob(pattern)
            if path.is_file() and not VENDORED.intersection(path.relative_to(REPO_ROOT).parts)
        }
    )


def python_stage_versions(path: Path) -> set[str]:
    """The version every `FROM python:` stage in one Dockerfile opens its tag with.

    A Python tag is a version followed by an optional variant — `-slim-bookworm`,
    `-alpine` — so the version is everything before the first hyphen. A tag with no
    version there (`slim-bookworm`, `latest`) is returned unchanged and then fails the
    readability assertion naming itself, which keeps that failure one assertion
    instead of two and means this function never has to guess.
    """
    return {
        match.group("tag").split("-", 1)[0]
        for match in PYTHON_STAGE.finditer(path.read_text(encoding="utf-8"))
    }


def values_under(node: Any, key: str) -> set[str]:
    """Every value stored under `key` anywhere in a parsed document.

    Structural rather than positional, the same walker
    `test_types_node_tracks_runtime.py` collects `NODE_VERSION` with, so a
    `PYTHON_VERSION` may sit in the workflow's `env:`, a job's or a step's, and a mypy
    `python_version` may sit in `[tool.mypy]` or in an `overrides` entry, and all of
    them go on being found when any of them move.

    Values are stringified because YAML 1.1 reads an unquoted `3.14` as a float, and a
    guard that ignored the unquoted spelling would answer "found nothing" over a
    workflow that pins the runtime perfectly well.

    This is a second copy of that walker rather than a shared helper, and the copy
    carries the YAML 1.1 workaround with it — which is the half that matters, because
    a docstring explaining the quirk in the other module would not have fixed a reader
    here that did not do it. If a third module needs the same walk, that is the change
    that moves all three into `tests/fixtures/repo.py`, where the other structural
    readers of this repository's own files already live.
    """
    found: set[str] = set()
    if isinstance(node, dict):
        for name, value in node.items():
            if name == key and isinstance(value, str | int | float):
                found.add(str(value))
            found |= values_under(value, key)
    elif isinstance(node, list):
        for item in node:
            found |= values_under(item, key)
    return found


def pyproject_document() -> dict[str, Any]:
    """`pyproject.toml`, parsed.

    An absent file gives an empty mapping so the test reports a failed assertion
    naming the missing deliverable rather than an error — `docs/MISTAKES.md` entry 44.
    Called from a test body and never at import time, for the same reason.
    """
    if not PYPROJECT_PATH.is_file():
        return {}
    document = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    return document if isinstance(document, dict) else {}


def requires_python_floor(specifier: str) -> str | None:
    """The lowest version a `requires-python` specifier admits, or `None`.

    `requires-python` is the one declaration here that is a *range* rather than a
    version — `">=3.14"` — so it is read with a pattern of its own. `None` is returned
    for a specifier with no `>=` clause, and the caller fails saying which specifier it
    could not read, rather than skipping the declaration or guessing at a floor.
    """
    match = REQUIRES_PYTHON_FLOOR.search(specifier)
    return match.group("version") if match else None


def major_minor(version: str) -> str:
    """The first two components of a readable version. `3.14.7` and `3.14` both give `3.14`.

    Not the major: see the module docstring. `3.13` and `3.14` are different languages,
    different wheel ABI tags and different standard libraries, and a comparison on the
    leading component alone would call them equal.
    """
    return ".".join(version.split(".")[:2])


def test_every_python_runtime_declaration_names_the_pinned_version(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """The images, CI, the lockfile floor and the type check all say Python 3.14.

    FIX-04 acceptance criterion 3, made mechanical for the five pinned places that are
    declarations rather than comments.

    **The five "found something at all" assertions below are the load-bearing part
    rather than ceremony.** This test compares sets, and empty sets agree with each
    other — so a Dockerfile whose stage moved out of reach of the pattern, a workflow
    that renamed its variable, a `pyproject.toml` that stopped declaring a floor, or a
    reader that simply went blind would each turn this into a passing test that checks
    nothing, which is the exact shape of the defect it exists to catch.

    **The mutations this must kill, in every direction.** One Dockerfile stage moved
    back to `python:3.13.15-slim-bookworm` while the other seven stay on 3.14 — the
    image that then ships an interpreter no gate here runs. `PYTHON_VERSION` alone left
    at `'3.13'` — the whole pipeline, `mypy` and `ruff` included, running on an
    interpreter the images do not have. `python_version` under `[tool.mypy]` alone left
    at `"3.13"` — a type check that passes against a standard library the runtime does
    not ship. `requires-python` alone left at `">=3.13"` — `pip-compile` free to resolve
    the hash-verified closure for an older interpreter. And the mutation inside this
    module: comparing majors, the way the Node guard legitimately does, which makes
    every one of the four above green.

    **The near misses that must stay green.** A patch-level difference between sides —
    the images pinned to `3.14.7-slim-bookworm` while `PYTHON_VERSION` is `'3.14'` and
    `requires-python` is `">=3.14"` — because the tie is major and minor and nothing
    else; that is the shape the tree has after FIX-04 lands, so this test passing at
    all is that near miss being exercised. A base image moving 3.14.7 to 3.14.8 on its
    own, likewise.
    """
    images = dockerfiles()
    assert images, (
        f"No Dockerfile was found under {REPO_ROOT}. This project builds four, and each one "
        "ships an interpreter, so finding none means this test has gone blind rather than "
        "that the images are fine."
    )

    staged = {path: python_stage_versions(path) for path in images}
    built = {version for found in staged.values() for version in found}
    assert built, "\n".join(
        [
            "No Dockerfile in this repository has a `FROM python:` stage:",
            *(f"  {path.relative_to(REPO_ROOT)}" for path in images),
            "",
            "These images ship the interpreter the API, the worker, beat and the three mocks "
            "run on, so finding none means this pattern has stopped seeing them: an `ARG` "
            "holding the image name, or a base image renamed, reads as absence here and must "
            "not. If a stage has genuinely gone, so has the reason for this part of the guard, "
            "and removing it is a decision for the ticket that removes the stage.",
        ]
    )

    runtime = values_under(ci_workflow, PYTHON_VERSION)
    assert ci_workflow and runtime, (
        f"{ci_workflow_path} declares no `{PYTHON_VERSION}` anywhere, or did not parse. Every "
        "Python job in that workflow feeds this value to `actions/setup-python`, so a workflow "
        "without it runs whatever Python the runner image happens to ship — an unpinned "
        "runtime, and one this test cannot name. Renaming the variable is fine; this test "
        "needs telling about the new name in the same change."
    )

    document = pyproject_document()
    assert document, (
        f"{PYPROJECT_PATH} does not exist or parsed to nothing. It carries both the "
        "`requires-python` floor the lockfiles are compiled against and the language level "
        "`mypy` checks at, so this test has nothing to compare without it."
    )

    requires_python = document.get("project", {}).get("requires-python", "")
    assert isinstance(requires_python, str) and requires_python, (
        f"{PYPROJECT_PATH.name} declares no `requires-python` under `[project]`. That value is "
        "the floor `pip-compile` resolves `requirements.txt` and `requirements-dev.txt` "
        "against (ADR 0005), so without it the hash-verified closure may hold wheels built for "
        "an interpreter the images do not run."
    )

    floor = requires_python_floor(requires_python)
    assert floor, (
        f"`requires-python = {requires_python!r}` has no `>=` clause, so this test cannot say "
        "which interpreter it admits as its lowest. A `~=`, a bare `>` or an `==3.14.*` each "
        "mean something slightly different at the boundary, and a guess here would report an "
        "agreement weaker than the one this test claims. Declare a floor, or teach this "
        "pattern the new form in the change that introduces it."
    )

    checked = values_under(document.get("tool", {}).get("mypy", {}), MYPY_PYTHON_VERSION)
    assert checked, (
        f"{PYPROJECT_PATH.name} sets no `{MYPY_PYTHON_VERSION}` under `[tool.mypy]`. Without it "
        "`mypy` checks against whichever interpreter it happens to be running on, so the type "
        "check silently follows the developer's machine instead of the deployed runtime, and "
        "this test has nothing to compare."
    )

    declared = {
        f"{path.relative_to(REPO_ROOT)} `FROM python:`": found
        for path, found in staged.items()
        if found
    }
    declared[f"{ci_workflow_path.name} `{PYTHON_VERSION}`"] = runtime
    declared[f"{PYPROJECT_PATH.name} `requires-python` floor"] = {floor}
    declared[f"{PYPROJECT_PATH.name} `[tool.mypy] {MYPY_PYTHON_VERSION}`"] = checked

    unreadable = sorted(
        version
        for found in declared.values()
        for version in found
        if not READABLE_VERSION.match(version)
    )
    assert not unreadable, "\n".join(
        [
            "These versions have no major and minor this test can compare honestly:",
            *(f"  {version}" for version in unreadable),
            "",
            *(f"  {label}: {sorted(found)}" for label, found in sorted(declared.items())),
            "",
            "A bare major (`python:3-slim`), a moving tag (`latest`, `slim-bookworm`) or a "
            "range resolves to a runtime at pull or install time rather than declaring one, and "
            "Python's compatibility line is the minor: 3.13 and 3.14 are different languages, "
            "different wheel ABI tags and different standard libraries. CLAUDE.md pins "
            "dependency versions, CI runtimes and images; every side of this comparison is "
            "supposed to be exact.",
        ]
    )

    lines = {
        label: {major_minor(version) for version in found} for label, found in declared.items()
    }
    agreed = {line for found in lines.values() for line in found}

    assert len(agreed) == 1, "\n".join(
        [
            "The documents that name this project's Python runtime do not all name the same "
            f"one. They name {sorted(agreed)}:",
            *(
                f"  {label}: {sorted(lines[label])} from {sorted(found)}"
                for label, found in sorted(declared.items())
            ),
            "",
            "No Dependabot ecosystem reads more than one of these: `docker` reads the `FROM` "
            "lines and proposes an image bump on its own, `github-actions` updates `uses:` "
            f"lines and not an `env:` value so nothing reads `{PYTHON_VERSION}` at all, and "
            "nothing reads `requires-python` or the mypy setting against either. An image ahead "
            "of CI ships an interpreter no gate here has run; CI ahead of the images runs the "
            "suite on one that is not deployed; a floor behind either lets `pip-compile` put "
            "wheels for an older interpreter into the closure the image installs from; and a "
            "mypy level behind either type-checks against a standard library that is not there "
            "and passes. Move them together, in the change that decides the runtime.",
        ]
    )

    assert agreed == {PINNED_RUNTIME}, "\n".join(
        [
            f"Every document agrees, and they agree on Python {next(iter(agreed))} rather than "
            f"on {PINNED_RUNTIME}:",
            *(f"  {label}: {sorted(found)}" for label, found in sorted(declared.items())),
            "",
            "FIX-04 moves this project's runtime to Python 3.14 and its acceptance criterion 3 "
            "is that no 3.13 reference remains in the pinned places. This assertion is that "
            "criterion for the five places that are declarations; the two that are comments — "
            "in `docker-compose.yml` and in `pyproject.toml` — are covered by the ticket's "
            "grep, because both parsers discard a comment before this test sees it.",
        ]
    )


def test_the_interpreter_running_this_suite_is_the_pinned_version() -> None:
    """The Python actually executing these tests is 3.14, not merely the declared one.

    The declarations can all agree and every one of them can be ignored: a virtualenv
    built before the move goes on running 3.13 whatever `pyproject.toml` says, and a
    workflow that changed `PYTHON_VERSION` in an `env:` block no job reads installs
    nothing new. This is FIX-04's acceptance criterion 2 — `make ci` passing on a
    rebuilt 3.14 virtualenv — asserted from inside the run rather than trusted.

    **The mutation this must kill:** every declaration moved to 3.14 while the
    interpreter that runs the suite stays on 3.13, in CI or on a developer's machine.
    That is a green pipeline reporting on a runtime the project no longer claims, and
    the whole `pip-compile` re-lock and the `cp314` wheels it pulled would be
    unexercised.

    **The near miss that must stay green:** any patch of 3.14 — 3.14.0 through
    whatever the base image reaches. The declared runtime is `3.14` and the images
    name a patch, so the patch is deliberately not compared here either.

    **Why a literal and not a comparison against the declarations.** Reading
    `PYTHON_VERSION` and comparing the interpreter to it would be perfectly green on a
    tree where nothing had moved at all, which is `docs/MISTAKES.md` entry 3 exactly.
    """
    assert sys.version_info[:2] == (3, 14), (
        f"This suite is running on Python {sys.version_info.major}.{sys.version_info.minor} "
        f"({sys.executable}), and FIX-04 pins the runtime at {PINNED_RUNTIME}. Locally the "
        "virtualenv needs rebuilding from 3.14 and reinstalling from the committed lockfiles; "
        "in CI this means `PYTHON_VERSION` in `.github/workflows/ci.yml` is not what the job "
        "installed, or the job that runs pytest does not read it. Either way every other "
        "result in this run describes an interpreter this project does not deploy."
    )


def test_the_collectors_find_the_python_runtime_this_repository_declares_today(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """Control: the readers see a Python stage in all four images, and see `PYTHON_VERSION`.

    **This test must be green before FIX-04 changes anything and green after.** It
    asserts only that each collector finds *something* where something certainly is,
    and never which version it found, so moving the pins cannot affect it. A red here
    therefore means the tests in this module are broken, not that the code is wrong:
    the Dockerfile glob, the vendored-tree exclusion, the `FROM python:` pattern or
    the workflow walk has stopped seeing a file that has not moved. Read it before
    believing anything the other tests in this module report, in either direction.

    `docs/MISTAKES.md` entry 35's rule is what this is: a guard that only ever reports
    absence cannot tell you which of the things it looks for it can actually see. The
    four paths below are the only file names written down in this module, and they are
    written down here precisely so that the structural collection everywhere else has
    something to be checked against.

    **The mutation this must kill:** any change that makes a collector blind — the
    `.venv` exclusion widened until it swallows a real directory, the pattern anchored
    somewhere a real `FROM` line is not, the glob narrowed to one file name. Each of
    those leaves the agreement test above passing over an empty or shrunken set.

    **The near miss that must stay green:** a fifth image joining the repository, or a
    stage's version changing. This asserts the four are present, not that they are all
    there is.
    """
    found = {str(path.relative_to(REPO_ROOT)) for path in dockerfiles()}
    missing = sorted(set(IMAGES_WITH_A_PYTHON_STAGE) - found)
    assert not missing, (
        f"The Dockerfile collection did not find {missing}; it found {sorted(found)}. These "
        "files are in the repository, so this is the collector going blind — check the glob "
        f"patterns {DOCKERFILE_NAMES} and the vendored-path exclusion {VENDORED}, which is the "
        "part most likely to have swallowed a real directory."
    )

    without_a_stage = sorted(
        name for name in IMAGES_WITH_A_PYTHON_STAGE if not python_stage_versions(REPO_ROOT / name)
    )
    assert not without_a_stage, (
        f"No `FROM python:` stage was found in {without_a_stage}, and every one of those images "
        "is built on the Python base image. The pattern has stopped matching a line that is "
        "there — a registry prefix, a `--platform` flag, an `ARG` holding the image name or a "
        "renamed base would each do it — and while it does, the agreement test above compares a "
        "set with those images silently absent from it. If an image has genuinely stopped being "
        "a Python image, this list changes in the ticket that changes the image."
    )

    assert values_under(ci_workflow, PYTHON_VERSION), (
        f"{ci_workflow_path} declares no `{PYTHON_VERSION}` that the structural walk can find. "
        "It is there today, so this is the walk going blind rather than the workflow being "
        "wrong — and while it is blind the agreement test above simply leaves CI out of the "
        "comparison."
    )


def test_the_comparison_ties_major_and_minor_and_ignores_the_patch() -> None:
    """The comparison line: 3.14.7 and 3.14 agree; 3.13 and 3.14 do not.

    Green before FIX-04 and after — it reads no file and asserts a property of the
    comparison itself. It is here because the comparison is the one place where this
    module can be wrong in a way that leaves every other test green, and because the
    accepted side of the line is not exercised by the tree until the pins have moved.

    **The mutation this must kill:** `major_minor` reduced to the leading component,
    which is what `test_types_node_tracks_runtime.py` legitimately does for Node and
    what a copy of it would do here. Under that mutation 3.13 and 3.14 agree, and every
    assertion in this module goes green over a tree that never moved.

    **The near miss on the other side:** `major_minor` comparing the whole version,
    under which the images' `3.14.7` would disagree with `PYTHON_VERSION`'s `3.14` and
    the pin could not be expressed at all. The first assertion below is that case.
    """
    assert major_minor("3.14.7") == major_minor("3.14"), (
        "An image pinned to an exact patch must agree with a `PYTHON_VERSION` that names none. "
        "This is the accepted side of the line: the base image moves patch by patch under a "
        "digest pin, and demanding that four Dockerfiles, a workflow and two `pyproject.toml` "
        "settings move in lockstep every time would make the guard unusable."
    )

    assert major_minor("3.13.15") != major_minor("3.14"), (
        "A stage left behind on 3.13 must not agree with a runtime on 3.14. This is the refused "
        "side of the line and the whole subject of FIX-04."
    )

    assert major_minor("3.13") != major_minor("3.14"), (
        "3.13 and 3.14 must not compare equal. If they do, the comparison has been reduced to "
        "the major — correct for Node, wrong for Python, and it makes every other assertion in "
        "this module vacuous."
    )


def test_the_requires_python_floor_is_read_out_of_a_range_and_not_a_plain_version() -> None:
    """`requires-python` is a specifier, and its floor is taken out deliberately.

    Green before FIX-04 and after. `requires-python` is the one declaration here that
    is not a version, and running it through `READABLE_VERSION` — the pattern the other
    four go through — would refuse `">=3.14"`, the only spelling this project uses.

    **The mutation this must kill:** the floor read with the plain-version pattern, or
    read by stripping characters until digits appear. The first refuses every legal
    value and the second silently reads a floor out of `"<3.14"`, which declares the
    opposite of one.

    **The refused side of the line:** a specifier with no `>=` clause answers `None`,
    so the test that consumes it fails naming the specifier rather than guessing at a
    boundary or skipping the declaration entirely.
    """
    assert requires_python_floor(">=3.14") == "3.14"
    assert requires_python_floor(">=3.14,<3.15") == "3.14"

    assert requires_python_floor("3.14") is None, (
        "A bare version is not a `requires-python` specifier, and reading a floor out of it "
        "would be this module inventing a rule packaging does not have."
    )
    assert requires_python_floor("<3.15") is None, (
        "An upper bound declares no floor. Reading `3.15` out of it would report the highest "
        "interpreter the project refuses as the lowest one it requires — the agreement test "
        "would then compare CI and the images against a number that means the opposite."
    )
    assert not READABLE_VERSION.match(">=3.14"), (
        "The plain-version pattern must go on refusing a range. This is why `requires-python` "
        "is parsed by a pattern of its own rather than joining the other four: if this ever "
        "matches, someone has widened `READABLE_VERSION` until it accepts specifiers, and the "
        "image tags it also guards would then be free to hold ranges too."
    )
