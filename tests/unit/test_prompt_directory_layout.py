"""Prompts are versioned files, one per task and version — ticket E0-12.

E0-12's scope asks for "`backend/app/ai/prompts/` directory structure, one file
per task and version, with the version-naming scheme documented", and its fifth
acceptance criterion for "a versioned validity prompt and a README stating the
naming scheme". SPEC §13 gives the directory the same description, and §7.4 says
why it has to be a directory of versions rather than a file per task: "every
classification stores prompt version and model ID for reproducibility", and the
threat and self-harm classifier "must be auditable, meaning a specific prompt
version and model ID produced a specific classification for a specific comment".

**A version that can be edited in place is not a version.** That is the property
these tests are built around. A file called `validity.md` satisfies "the prompt
lives in the prompts directory" and satisfies nothing else: the next edit to it
changes what every stored classification claiming that prompt was produced by,
retroactively and with no diff anywhere near the classification table. The
version has to be part of the path so that a second version is a second file.

**Prompt content is deliberately unasserted.** Whether a prompt is any good is a
distribution rather than an assertion, and §9.3 answers it with versioned eval
sets and per-task precision and recall floors. Nothing here reads what a prompt
says beyond checking it is not empty. The one thing worth stating plainly:
nothing in this file can make §9.3's threat and self-harm recall floor easier to
pass, because nothing here asserts anything about a classification.

**The directory also has to survive being packaged, which nothing else in this
module can see.** Every other test here reads the source tree, and the container
does not ship the source tree: `backend/Dockerfile` builds a wheel with
`pip wheel . --no-deps --no-build-isolation` and installs that wheel into the
runtime virtualenv. setuptools puts *modules* in a wheel and leaves every other
file out unless `[tool.setuptools.package-data]` names it, so the prompts
directory can be correctly laid out, correctly documented, correctly versioned,
and absent from the image — which is the only place E0-13's caller ever runs. The
last test in this file builds the wheel and looks inside it.

**Two of these tests search text for a pattern, which is a shape that fails
silently** (`docs/MISTAKES.md` entry 3, third case — a regex that matched nothing
and went green against the exact text it existed to catch). Both carry a canary:
a string that must be present in any README of prompts at all, asserted before
the search that matters, so a search over the wrong file or over an empty string
says so instead of passing.
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# `backend/` is the import root, so a file at `backend/app/ai/prompts/x.md` is
# `app/ai/prompts/x.md` inside the built package.
BACKEND_DIR = REPO_ROOT / "backend"

# E0-12's scope and SPEC §13 both spell the directory.
PROMPTS_DIR = REPO_ROOT / "backend" / "app" / "ai" / "prompts"

# Exactly what `backend/Dockerfile` copies into its builder stage before running
# `pip wheel .` — `COPY pyproject.toml README.md ./` and `COPY backend ./backend`.
# Matching that list rather than copying the whole repository is what makes the
# wheel this test inspects the wheel the image installs, instead of a similar one
# built from a different set of files. LICENSE is absent from both, deliberately.
BUILD_INPUTS = ("pyproject.toml", "README.md", "backend")

# Never copied into the staging directory, so the build cannot reuse one. See
# `staged_source` for why this is the whole of the artifact hygiene here.
STALE_BUILD_ARTIFACTS = ("__pycache__", "*.pyc", "*.egg-info", "build", "dist", "*.whl", ".venv")

# A module that is certainly in the wheel, because setuptools ships `.py` files
# under a found package without being asked. The canary for the archive listing:
# if this is missing, the build produced something other than this project's
# package and every prompt would be reported missing for a reason that has
# nothing to do with `package-data`.
WHEEL_CANARY = "app/ai/contracts.py"

# A pure-Python wheel of this size builds in a few seconds. The timeout is here
# so that a build which hangs fails with a message rather than holding CI open.
BUILD_TIMEOUT_SECONDS = 300

# The PEP 517 hook every builder calls: `pip wheel`, `python -m build`, and the
# Dockerfile's line 46 all end up here, so this is the build's own entry point
# rather than a stand-in for it. Run in a subprocess, which keeps setuptools'
# warnings out of a suite configured with `error::DeprecationWarning` and keeps
# its `sys.path` edits out of this interpreter.
BUILD_SCRIPT = "import sys; from setuptools import build_meta; build_meta.build_wheel(sys.argv[1])"

# §7.4's first task, and the only one whose prompt E0-12 ships — the other four
# are "out of scope: prompt *content* beyond a first draft for the validity task
# — moderation, summary, draft, and draft-check prompts belong to E2, E4, E6,
# and E7."
VALIDITY_TASK_WORD = "validity"

# Files in the prompts directory that are not prompts. **This suite's choice**,
# and deliberately short: anything else found there is treated as a prompt and
# has to carry a version, because a template that does not is exactly the file
# this module exists to refuse.
NON_PROMPT_NAMES = ("readme.md", "readme", "__init__.py", ".gitkeep", ".gitignore")

README_NAME = "README.md"

# A word that appears in any README describing prompt files. The canary for the
# two searches below: if this is missing, the file being searched is not the
# document this test thinks it is, and the searches that follow would report
# absence rather than reporting that they had gone blind.
README_CANARY = "prompt"

# Names that look like a version and are not one, because the file they name is
# the one that gets overwritten. A `latest` is a pointer: the classification that
# recorded it cannot be reproduced, which is the property §7.4 asks the version
# to carry. **This suite's choice** of words; the rule behind it is the ticket's.
MUTABLE_POINTERS = ("latest", "current", "head", "new", "final", "wip", "tmp", "temp")

# The separators a version is likely to be attached with, so `validity.v1.md`,
# `validity_v1.md`, `validity-v1.md` and `v1/validity.md` are all read the same
# way. E0-12 does not pick one and neither does this file: what it asserts is
# that a version is *there*, in the path, under whichever punctuation.
TOKEN_SEPARATORS = (".", "-", "_", " ")


def prompt_files() -> list[Path]:
    """Every file under the prompts directory that is meant to be a prompt."""
    if not PROMPTS_DIR.is_dir():
        return []
    return sorted(
        path
        for path in PROMPTS_DIR.rglob("*")
        if path.is_file()
        and path.name.lower() not in NON_PROMPT_NAMES
        and "__pycache__" not in path.parts
    )


def path_tokens(path: Path) -> list[str]:
    """The words a prompt's path is made of, with its file extension dropped.

    The whole path below `prompts/` rather than the file name, so a layout that
    puts the version in a directory — `prompts/v3/validity.md` — is read as
    carrying a version just as `prompts/validity.v3.md` is. Neither is this
    file's preference; the ticket names no scheme and this asks only that one
    exists.
    """
    relative = path.relative_to(PROMPTS_DIR)
    parts = [*relative.parts[:-1], relative.name.removesuffix(relative.suffix)]
    tokens: list[str] = []
    for part in parts:
        current = part
        for separator in TOKEN_SEPARATORS[1:]:
            current = current.replace(separator, TOKEN_SEPARATORS[0])
        tokens.extend(token.lower() for token in current.split(TOKEN_SEPARATORS[0]) if token)
    return tokens


def readme_text() -> str:
    """The prompt directory's README, or an empty string if there is none."""
    readme = PROMPTS_DIR / README_NAME
    if not readme.is_file():
        return ""
    return readme.read_text(encoding="utf-8")


def assert_the_directory_exists() -> None:
    """The prompts directory is there, so a later assertion is about its contents."""
    assert PROMPTS_DIR.is_dir(), (
        f"{PROMPTS_DIR} does not exist. E0-12's scope: '`backend/app/ai/prompts/` directory "
        "structure, one file per task and version, with the version-naming scheme documented', "
        "and SPEC §13 places it in the same words."
    )


def test_the_prompt_directory_carries_a_prompt_for_the_validity_task() -> None:
    """Criterion 5, first half: the directory contains a validity prompt.

    E0-13 builds the comment-validity task end to end "against the E0-12
    contract and prompt", so this is the file that ticket loads. An empty
    directory, or one holding only a README describing a scheme nothing follows,
    fails here — which is the state this ticket would otherwise be able to ship,
    since no caller exists yet to notice the prompt is missing.

    Non-empty is asserted as well as present. A zero-byte placeholder satisfies
    every path-shaped check in this file and gives the gateway nothing to send.
    What the prompt *says* is not read: §9.3 answers that with eval sets, not
    with an assertion.
    """
    assert_the_directory_exists()
    files = prompt_files()

    assert files, (
        f"{PROMPTS_DIR} holds no prompt files (it holds "
        f"{sorted(path.name for path in PROMPTS_DIR.iterdir())}). Criterion 5: 'The prompt "
        "directory contains a versioned validity prompt and a README stating the naming scheme.'"
    )

    validity = [path for path in files if VALIDITY_TASK_WORD in " ".join(path_tokens(path))]

    assert validity, (
        f"No file under {PROMPTS_DIR} names the validity task; it holds "
        f"{[str(path.relative_to(PROMPTS_DIR)) for path in files]}. §7.4's first task is comment "
        "validity, E0-12 ships its prompt as a first draft, and E0-13 implements that task "
        "'against the E0-12 contract and prompt'."
    )

    empty = [path for path in validity if not path.read_text(encoding="utf-8").strip()]

    assert not empty, (
        f"The validity prompt is empty: {[str(path.relative_to(PROMPTS_DIR)) for path in empty]}. "
        "A placeholder passes every other check here and leaves E0-13's gateway with nothing to "
        "send. What it says is not asserted anywhere — that is §9.3's eval sets — but it has to "
        "say something."
    )


def test_every_prompt_file_carries_a_version_in_its_path() -> None:
    """Criterion 5's word "versioned", and the scope's "one file per task and version".

    The wrong implementation this catches is the plausible one: `prompts/
    validity.md`, a single file per task, edited when the prompt changes. It
    reads as versioned because the repository has history, and it is not. §7.4
    requires that "a specific prompt version and model ID produced a specific
    classification", and a stored version string that points at a file whose
    contents have since changed cannot reproduce anything — the audit record for
    a threat or self-harm classification (§6.2) is then a claim nobody can check.
    Two versions have to be able to exist side by side, which means the version
    is in the path.

    A token that names a moving target is refused for the same reason under a
    different disguise: `latest.md` is a file whose next edit rewrites what an
    existing classification claims to have come from.

    The scheme itself is not pinned. A version in the file name and a version in
    a directory both satisfy this, punctuated however the implementer likes; the
    README is where the choice is written down, and the next test asks for that.
    """
    assert_the_directory_exists()
    files = prompt_files()

    assert files, (
        f"{PROMPTS_DIR} holds no prompt files, so this test would report every prompt as "
        "versioned without having looked at one."
    )

    unversioned = []
    mutable = []
    for path in files:
        tokens = path_tokens(path)
        if not any(character.isdigit() for token in tokens for character in token):
            unversioned.append(str(path.relative_to(PROMPTS_DIR)))
        if any(token in MUTABLE_POINTERS for token in tokens):
            mutable.append(str(path.relative_to(PROMPTS_DIR)))

    assert not unversioned, (
        f"These prompt files carry no version anywhere in their path: {unversioned}. E0-12's "
        "scope asks for 'one file per task and version', and a path with no version in it can "
        "hold exactly one version — the next one overwrites it. §7.4: 'Prompts are versioned "
        "in-repo; every classification stores prompt version and model ID for reproducibility.' "
        "A version recorded against a file that is edited in place reproduces nothing."
    )

    assert not mutable, (
        f"These prompt paths name a moving target rather than a version: {mutable} (one of "
        f"{list(MUTABLE_POINTERS)}). A `latest` is a pointer: the file it names is the file that "
        "gets overwritten, so a classification recording it cannot be reproduced — the same "
        "defect as an unversioned name, wearing a version's clothes."
    )


def test_the_prompt_directory_has_a_readme_stating_the_version_naming_scheme() -> None:
    """Criterion 5, second half: a README stating the naming scheme.

    The scheme is a convention, and a convention nobody wrote down is one the
    next ticket invents a second version of — E2, E4, E6 and E7 each add a prompt
    to this directory, and none of them is written yet.

    **What this test can and cannot see, said plainly.** It can see that a README
    is there, that it is about prompts, and that it talks about versions. It
    cannot see whether the scheme it describes is the scheme the files follow;
    prose is not machine-readable and asserting otherwise would be a check that
    passes on any document containing the right words. The mechanical half of
    criterion 5 is the test above, which reads the files themselves; the test
    below closes the narrow gap between the two by requiring the README to
    mention the prompts that actually exist.

    The canary is the point of the first assertion: a search for "version" that
    finds nothing and a search over a file that was never opened produce the same
    result, and only the canary tells them apart.
    """
    assert_the_directory_exists()
    text = readme_text()

    assert README_CANARY in text.lower(), (
        f"{PROMPTS_DIR / README_NAME} is missing, empty, or does not contain the word "
        f"{README_CANARY!r} — it holds {text[:200]!r}. Criterion 5: 'The prompt directory "
        "contains a versioned validity prompt and a README stating the naming scheme', and "
        "E0-12's definition of done: 'Docs apply, briefly. The prompt-directory README "
        "documenting the versioning scheme.' This assertion is also the canary for the one "
        "below: a search for a word in a file that does not exist finds nothing, which is "
        "indistinguishable from a document that does not say it."
    )

    assert "version" in text.lower(), (
        f"{PROMPTS_DIR / README_NAME} never mentions versions. The scheme it is there to state "
        "is the version-naming scheme — E0-12's scope: 'one file per task and version, with the "
        "version-naming scheme documented'. Four later epics add prompts to this directory "
        "(E2, E4, E6, E7) and this file is the only thing telling them how to name one."
    )


def test_the_readme_names_the_prompts_that_are_on_disk() -> None:
    """The documented scheme covers the files that exist, rather than some other set.

    A README describing a naming scheme for prompts that are not there, or that
    is silent about the one prompt this ticket ships, is a record asserting
    something about a thing it does not describe — `docs/MISTAKES.md` entry 1,
    whose highest-risk shape is the index written once and never re-read.

    Deliberately loose: one word from a prompt's path has to appear in the
    README, not all of them. A file named `validity.system.v1.md` should not fail
    because the README's example does not happen to spell "system". What it does
    catch is a README that never names the task whose prompt sits beside it.
    """
    assert_the_directory_exists()
    files = prompt_files()
    text = readme_text().lower()

    assert files and text, (
        f"There are {len(files)} prompt files under {PROMPTS_DIR} and its README holds "
        f"{len(text)} characters. With either at zero this test would report full coverage "
        "without comparing anything — the two tests above own those two failures."
    )

    unmentioned = []
    for path in files:
        words = [
            token
            for token in path_tokens(path)
            if len(token) >= 4 and not any(character.isdigit() for character in token)
        ]
        if not any(word in text for word in words):
            unmentioned.append((str(path.relative_to(PROMPTS_DIR)), words))

    assert not unmentioned, (
        f"The README in {PROMPTS_DIR} names none of the words in these prompts' paths: "
        f"{unmentioned}. The README is what tells the four later epics adding prompts here how to "
        "name one, and a scheme documented without reference to the prompt sitting next to it is "
        "a record that has already come apart from what it describes."
    )


def test_the_token_reader_finds_a_version_in_a_name_and_in_a_directory_and_not_elsewhere() -> None:
    """The reader every assertion above depends on, run against both answers.

    Not a test of the ticket — a test of `path_tokens`. `docs/MISTAKES.md` entry
    3's rule for a pattern searched against a file is to run it against the text
    it is claimed to catch *and* against the text it is claimed to allow, because
    a reader that has gone blind reports the same thing as a directory that is
    clean. Every test above would go green against a prompt directory in any
    state if this function returned nothing, and only these three cases say
    otherwise.

    The paths are constructed rather than created: joining and `relative_to` are
    arithmetic on a path, and nothing here touches the filesystem.
    """
    in_the_name = path_tokens(PROMPTS_DIR / "validity.v1.md")
    in_a_directory = path_tokens(PROMPTS_DIR / "v1" / "validity.md")
    nowhere = path_tokens(PROMPTS_DIR / "validity.md")

    assert "v1" in in_the_name and VALIDITY_TASK_WORD in in_the_name, (
        f"`path_tokens` read `validity.v1.md` as {in_the_name}, losing the version or the task. "
        "Every prompt named that way would be reported as unversioned."
    )
    assert "v1" in in_a_directory and VALIDITY_TASK_WORD in in_a_directory, (
        f"`path_tokens` read `v1/validity.md` as {in_a_directory}, losing the version or the "
        "task. E0-12 names no scheme, so a version held in a directory has to be found too."
    )
    assert nowhere == [VALIDITY_TASK_WORD], (
        f"`path_tokens` read `validity.md` as {nowhere} rather than [{VALIDITY_TASK_WORD!r}]. "
        "That file is the wrong implementation this module exists to refuse — a single prompt "
        "per task, overwritten in place — and a reader that finds a version in it would pass it."
    )


# ---------------------------------------------------------------------------
# Reaching the package that actually ships
# ---------------------------------------------------------------------------


def staged_source(destination: Path) -> Path:
    """A copy of the build's inputs, with no build artifact anywhere in it.

    **No cleaning step, because there is nothing to clean.** A stale `build/` or
    `*.egg-info` beside `pyproject.toml` is reused by setuptools, so a wheel
    built over one reports what the *previous* build decided and looks entirely
    correct — `docs/MISTAKES.md` entry 12 one level up, where the thing that went
    stale is a build tree rather than a `.pyc`, and the reverted run and the
    mutated run again produce identical output. Deleting the two directories in
    the repository would work and would also reach into a working tree this test
    does not own, mid-run, while an editable install points at it. Copying the
    inputs into a directory that has never been built in makes the reuse
    impossible instead of undone.

    The copied set is the Dockerfile's own `COPY` lines. A test that built from
    the whole repository would be building something the image never builds.
    """
    source = destination / "source"
    source.mkdir(parents=True)
    for name in BUILD_INPUTS:
        origin = REPO_ROOT / name
        if not origin.exists():
            pytest.fail(
                f"{origin} does not exist, so the wheel this test builds would not be the wheel "
                f"`backend/Dockerfile` builds — it copies {list(BUILD_INPUTS)} and nothing else. "
                "This is a gap in this file or a change to the image's build inputs, not a "
                "failed criterion."
            )
        if origin.is_dir():
            shutil.copytree(
                origin, source / name, ignore=shutil.ignore_patterns(*STALE_BUILD_ARTIFACTS)
            )
        else:
            shutil.copy2(origin, source / name)
    return source


def build_the_wheel(source: Path, wheel_directory: Path) -> Path:
    """Build a wheel from `source` and return it, or fail with the build's own output."""
    wheel_directory.mkdir(parents=True)
    # S603: the command is this interpreter and the literal script above. Nothing
    # in it comes from input, and the one argument is a path this test made.
    try:
        completed = subprocess.run(  # noqa: S603
            [sys.executable, "-c", BUILD_SCRIPT, str(wheel_directory)],
            cwd=source,
            capture_output=True,
            text=True,
            timeout=BUILD_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"Building a wheel from {source} did not finish in {BUILD_TIMEOUT_SECONDS} seconds. "
            "That is a gap in this file or a broken build environment rather than a failed "
            "criterion — a pure-Python wheel of this size takes a few seconds."
        )

    wheels = sorted(wheel_directory.glob("*.whl"))
    if not wheels:
        pytest.fail(
            f"No wheel was produced from {source} (exit status {completed.returncode}).\n"
            f"stdout:\n{completed.stdout[-2000:]}\nstderr:\n{completed.stderr[-2000:]}\n"
            "The project could not be built at all, which is a different failure from a prompt "
            "not being packaged, and it would stop the image being built too."
        )
    return wheels[0]


def test_every_prompt_in_the_source_tree_reaches_the_built_package(tmp_path: Path) -> None:
    """A prompt that exists in the repository and not in the wheel does not exist in production.

    Every other test in this module reads the source tree. The runtime image does
    not have the source tree: `backend/Dockerfile` builds a wheel and installs
    it, and setuptools packages `.py` modules and nothing else unless
    `[tool.setuptools.package-data]` says otherwise. So the whole of this module
    could be green — a versioned validity prompt, a README documenting the
    scheme — with the container holding `app/ai/contracts.py` and no prompt
    beside it. That is not hypothetical: it is what this ticket shipped until the
    wheel was opened, and it is `docs/MISTAKES.md` entry 16. This test is that
    entry's rule made automatic, because the rule as written is a thing a person
    has to remember to do, and entry 2 is what happens to a fix in
    `pyproject.toml` that nothing asserts — any later edit undoes it with every
    gate still green. It matters past this ticket because E2, E4, E6 and E7 each
    add a prompt to this directory.

    **The wrong implementations it catches**, in the order they are likely:

      - No `package-data` entry at all — every prompt missing, the defect as
        found.
      - A glob that does not cover the extension a later prompt uses.
        `prompts/*.md` is what is there now, and a `.txt`, `.jinja` or
        `.prompt` template added by E4 ships as nothing.
      - **A glob that does not descend.** `prompts/*.md` does not match
        `prompts/v2/validity.md`, and the version-in-a-directory layout is one
        this module's other tests deliberately admit. The pair of tests is the
        statement: lay the directory out however you like, and make the packaging
        follow it. Nothing in `pyproject.toml` reports this — the entry is
        present and correct-looking, and the file is simply not there.

    This is why the test builds rather than reading the configuration. An
    assertion that the `package-data` line exists would pass against every one of
    the last three, because each of them has the line.

    **What it does not cover**, since it reads stronger than it is otherwise:

      - It builds a wheel; it does not build or run the image. If the Dockerfile
        stops installing this wheel, nothing here notices — that is the `docker`
        gate's ground.
      - It asserts the file is *in the archive*, not that E0-13's loader can read
        it at the path it will look under. `importlib.resources` and a path
        derived from `__file__` fail differently, and the loader does not exist
        yet.
      - It asserts source ⊆ wheel, not the reverse. A prompt in the wheel that is
        no longer in the repository is not something this sees.
      - It costs a real build — seconds, not milliseconds, and the only test in
        this suite that shells out to one.
    """
    assert_the_directory_exists()
    prompts = prompt_files()

    assert prompts, (
        f"{PROMPTS_DIR} holds no prompt files, so this test would confirm that all of them ship "
        "without having built anything. The first test in this module owns that failure."
    )

    wheel = build_the_wheel(staged_source(tmp_path), tmp_path / "wheels")
    with zipfile.ZipFile(wheel) as archive:
        members = set(archive.namelist())

    assert WHEEL_CANARY in members, (
        f"The wheel built from this project does not contain {WHEEL_CANARY!r}; it contains "
        f"{sorted(members)[:20]}. setuptools ships a found package's modules without being asked, "
        "so a wheel missing that file is not this project's package — the assertion below would "
        "report every prompt as unpackaged for a reason that has nothing to do with prompts."
    )

    expected = [path.relative_to(BACKEND_DIR).as_posix() for path in prompts]
    missing = sorted(name for name in expected if name not in members)

    assert not missing, (
        f"These prompts are in the source tree and not in the wheel: {missing}. The wheel holds "
        f"{sorted(name for name in members if '/prompts/' in name)}. `backend/Dockerfile` builds "
        "this wheel and installs it into the runtime virtualenv, so a prompt that does not reach "
        "it does not exist in any container — while every other test in this module, and the "
        "whole of a developer's machine, still reads it straight off disk. SPEC §7.4: a "
        "classification records the prompt version that produced it, and the text behind that "
        "version has to be somewhere the process can read. `[tool.setuptools.package-data]` in "
        "`pyproject.toml` is what decides this; the glob has to cover the extension and the "
        "depth of the layout actually used."
    )
