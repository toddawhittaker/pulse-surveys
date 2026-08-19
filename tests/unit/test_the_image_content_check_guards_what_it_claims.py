"""The image-content check plants what it guards, and keeps what it refuses — findings 3 and 4.

`scripts/ci/check_image_contents.sh` plants one file per `.dockerignore`
re-exclusion, builds the runtime image and looks inside it, so that deleting a
line from `.dockerignore` fails the Docker gate and names the line that went.
E0-36's independent security review found two things about it, both reproduced.

**Finding 3 — the battery is short by two lines, and the comment beside it says
the wrong reason.** `.dockerignore`'s new comment says the last four suffixes were
singled out "because the package-data glob in `pyproject.toml` makes this one
directory a path into the image that the others do not have". That is false, and
`.dockerignore:44-45` is the counterexample: `backend/**/*.pem` and
`backend/**/*.key` reach the same directory through the same glob. Measured by
planting four files and listing the installed prompts directory inside a built
image — `probe.pem` and `probe.key` were **excluded**, and nothing guards the two
lines that excluded them. So those two lines are the only lines in the file whose
deletion ships a private key, and they were the ungated ones.

**Finding 4 — the cleanup deletes the file the script refused to overwrite.** The
plant loop refuses a pre-existing file with one of its own names and calls `fail`,
because silently truncating something in a working tree is not the check's
business. `trap cleanup EXIT` is installed before the loop and `cleanup` removes
all four fixed names unconditionally, so the refusal is followed immediately by
the deletion it exists to avoid. Reproduced: a decoy at
`e0-36-image-content-check.bak`, the script exits 1 printing "Delete it if it is
debris from an interrupted run", and the decoy is gone. **The stated contract is
defeated by its own cleanup**, and a re-run then succeeds with nothing recording
the loss.

**What this module can and cannot say.** It asserts the check's *inventory* — a
planted file exists for every suffix a floor names — and its *refusal behaviour*,
which needs no Docker daemon because the refusal path exits before any build. It
does not and cannot assert that the `.pem` and `.key` lines work: only building
the image proves that, which is the script's own job in the Docker gate. An
inventory test is what stops the battery silently covering less than it claims;
the build is what makes covering it mean something.

**Not addressed here, and nothing below should be read as fixing it.** The same
measurement found that `probe.pfx` and `probe.secret` *reached* the runtime image,
because no line in `.dockerignore` matches them. That is a coverage gap rather
than a fidelity gap — closing it means adding patterns, which changes what is
guarded — and it is going to a followup ticket with the measurement attached.

Separate from `test_the_docker_gate_and_the_makefile_run_the_same_checks.py`,
whose subject is the two callers agreeing about which checks run. This one is
about what one of those checks contains and how it behaves.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "ci" / "check_image_contents.sh"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"

# The suffixes the planted battery may not fall below, each with the record that
# put it there. **Written down here rather than derived from `.dockerignore`**,
# because an inventory taken from the guarded structure cannot notice that
# structure shrinking: delete a line from `.dockerignore` and a derived floor
# would agree that nothing is missing (`docs/MISTAKES.md` entry 35).
#
# The first four are E0-12's, added because `pyproject.toml` ships
# `app/ai/prompts/**/*` as package data. The last two are `.dockerignore:44-45`,
# and they are here on a measurement rather than on symmetry: planting `probe.pem`
# and `probe.key` and listing the installed prompts directory showed both
# excluded, so those two lines are the only lines in that file whose deletion
# ships a private key into the runtime image.
GUARDED_SUFFIXES = {
    "~": "backend/**/*~ — E0-12, an editor backup beside a prompt",
    ".orig": "backend/**/*.orig — E0-12, merge debris",
    ".rej": "backend/**/*.rej — E0-12, merge debris",
    ".bak": "backend/**/*.bak — E0-12, an editor backup",
    ".pem": "backend/**/*.pem — .dockerignore:44, measured as one of the two lines "
    "standing between a private key and the image",
    ".key": "backend/**/*.key — .dockerignore:45, the other one",
}

# The check's own inventory and the directory it plants into, read out of the
# script. These are inputs rather than expectations: the names are the script's to
# choose, and what this module holds is the floor above, which the script cannot
# shrink.
PLANTED_ARRAY = re.compile(r"PLANTED_FILES=\((?P<body>[^)]*)\)", re.DOTALL)
QUOTED = re.compile(r'"(?P<value>[^"]+)"')
PROMPTS_DIRECTORY = re.compile(r'PROMPTS_SOURCE_DIRECTORY="(?P<path>[^"]+)"')

SHELL_COMMENT = re.compile(r"#.*$")

# The refusal path exits before `docker build`, so it is milliseconds. A run that
# takes longer than this has got past the plant loop and may be building an image
# inside a unit test, which is a broken test rather than a slow one.
REFUSAL_TIMEOUT_SECONDS = 60

# The claim in `.dockerignore` that finding 3 falsifies, quoted as it stands with
# its wrap, and the searches run against it before they are run against the file
# (`docs/MISTAKES.md` entry 3, third incident: a pattern that matched nothing
# across a comment wrap and reported success against the exact comment it existed
# to find).
FALSE_EXCLUSIVITY_NOTE = (
    "# yet guards the patterns above this block the same way; the four here were\n"
    "# singled out because the package-data glob in `pyproject.toml` makes this one\n"
    "# directory a path into the image that the others do not have."
)

# Narrow on purpose. A rewritten comment that names a *smaller* unguarded set —
# the `.env` patterns, the `mock-lms` and `mock-idp` blocks — is true and must
# stay green, so neither search may fire on the words alone.
EXCLUSIVITY_CLAIM = re.compile(r"a path into the image that the others do not have", re.IGNORECASE)
NOTHING_ELSE_GUARDED_CLAIM = re.compile(
    r"nothing\s+yet\s+guards\s+the\s+patterns\s+above\s+this\s+block", re.IGNORECASE
)

# A string certainly in `.dockerignore`, so that a search finding nothing says so
# rather than passing. It is one of the two lines finding 3 is about.
DOCKERIGNORE_CANARY = "backend/**/*.pem"


def collapsed(text: str) -> str:
    """`text` with every run of whitespace and comment marker flattened to one space.

    So that a claim wrapped across three comment lines reads as one sentence, which
    is how a human reads it and is not how a file stores it.
    """
    return re.sub(r"[\s#]+", " ", text)


def uncommented(text: str) -> str:
    """`text` with shell comments cut, so a commented-out assignment stops counting."""
    return "\n".join(SHELL_COMMENT.sub("", line) for line in text.splitlines())


def planted_names(script: str) -> list[str]:
    """The file names the check plants, in the order it plants them."""
    match = PLANTED_ARRAY.search(uncommented(script))
    if match is None:
        return []
    return [found.group("value") for found in QUOTED.finditer(match.group("body"))]


def prompts_directory(script: str) -> str | None:
    """Where in the source tree the check plants, as the script spells it."""
    match = PROMPTS_DIRECTORY.search(uncommented(script))
    return match.group("path") if match else None


def read_check_script() -> str:
    """The check script's text, or a failure saying it is not there."""
    if not CHECK_SCRIPT.is_file():
        pytest.fail(
            f"{CHECK_SCRIPT.relative_to(REPO_ROOT)} does not exist. It is the only thing that "
            "notices a deleted line in `.dockerignore`: without it, deleting one leaves every "
            "gate green while an untracked file beside a prompt is packaged into the wheel and "
            "installed into the runtime image."
        )
    return CHECK_SCRIPT.read_text(encoding="utf-8")


def test_the_check_plants_a_file_for_every_suffix_the_floor_names() -> None:
    """Finding 3: the battery covers the two lines that stand between a key and the image.

    The four E0-12 suffixes each have a planted file, and that is the half that
    already worked. `.pem` and `.key` did not, and they are the ones the
    measurement singles out: planting `probe.pem` and `probe.key` and listing the
    installed prompts directory showed both **excluded** — by
    `.dockerignore:44-45`, through the same package-data glob that makes the four
    reachable. So those two lines are the only lines in the file whose deletion
    ships a private key, and until this they were the ungated ones.

    **The floor is written here and the names are read from the script**, and the
    direction matters. Taking the floor from `.dockerignore` would make it a copy
    of the thing it holds up — delete a line there and a derived floor agrees
    nothing is missing (`docs/MISTAKES.md` entry 35, and entry 19 for the same
    shape). Taking the *names* from the script is the opposite case: they are an
    input, the script's to choose, and the floor is what stops the list shrinking.

    **This asserts the inventory and not the guarantee.** Nothing here builds an
    image, so a planted `.pem` that the check forgets to look for would pass. The
    build is the script's own job in the Docker gate; what this stops is the
    battery quietly covering less than the comment beside it claims.

    **The mutation this survives:** delete the `.pem` entry from `PLANTED_FILES`
    in `scripts/ci/check_image_contents.sh`. **The near miss that must stay
    green:** renaming every planted file — the stem is the script's, and only the
    suffixes are held here.
    """
    script = read_check_script()

    # Run the reader against the shape it claims to read and the shape it must
    # ignore, before its answer about the real script is believed. A commented-out
    # array is the case that matters: it satisfies a floor perfectly while the
    # script plants nothing at all.
    sample = 'PLANTED_FILES=(\n  "probe.orig"   # backend/**/*.orig\n  "probe.pem"\n)\n'
    assert planted_names(sample) == ["probe.orig", "probe.pem"], (
        f"The reader in this test does not read {sample!r}, which is the shape of the array it "
        "exists to read. It has gone blind, and the assertion below would report every suffix "
        "missing from a script that plants them all."
    )
    commented = "# " + sample.replace("\n", "\n# ")
    assert not planted_names(commented), (
        "The reader in this test reads a commented-out `PLANTED_FILES`. A commented array plants "
        "nothing, so the floor below would be satisfied by a check that had been switched off."
    )

    names = planted_names(script)
    assert names, (
        f"No `PLANTED_FILES` array was read out of {CHECK_SCRIPT.relative_to(REPO_ROOT)}. Either "
        "the check no longer plants anything — in which case it builds an image and looks for "
        "files nobody put there, and reports success forever — or the array is spelled some other "
        "way now and this test needs pointing at it."
    )

    unplanted = {
        suffix: why
        for suffix, why in GUARDED_SUFFIXES.items()
        if not any(name.endswith(suffix) for name in names)
    }

    assert not unplanted, "\n".join(
        [
            "The image-content check plants no file for these patterns:",
            *(f"  {suffix} — {why}" for suffix, why in sorted(unplanted.items())),
            f"  it plants: {names}",
            "",
            "A pattern with no planted file is a line in `.dockerignore` whose deletion this "
            "check cannot notice, which is the state all four prompt-directory suffixes were in "
            "before E0-36 and all six are in without this.",
            "",
            "`.pem` and `.key` are here on a measurement, not on symmetry. Four files were "
            "planted in the prompts directory and the installed directory was listed inside a "
            "built image: `probe.pem` and `probe.key` were excluded — by `.dockerignore:44-45`, "
            "reached through the same `pyproject.toml` package-data glob that makes the other "
            "four reachable — and `probe.pfx` and `probe.secret` were carried into the image "
            "because no line matches them. The second half is a coverage gap going to a followup "
            "ticket; this assertion is about the first: the two lines that do hold, and had "
            "nothing watching them.",
        ]
    )


def test_a_refusal_leaves_the_file_it_refused_where_it_found_it(tmp_path: Path) -> None:
    """Finding 4: the cleanup must remove what the check planted, not what it found.

    The plant loop refuses rather than overwrites, and says why: the names are the
    script's own, so one already existing means a previous run died or somebody is
    using the name, and "silently truncating a file in the working tree is not this
    check's business." Then `trap cleanup EXIT`, installed before the loop, removes
    all four names unconditionally — so the file the script refused to overwrite is
    deleted a moment later, by the same run, and a re-run succeeds with nothing
    recording the loss.

    **Run against a copy of the script in a temporary tree**, never against this
    repository. The script derives its own repository root from `BASH_SOURCE`, so a
    copy at `<tmp>/repo/scripts/ci/` plants into `<tmp>/repo/`, and nothing here
    can leave debris in `backend/app/ai/prompts/` — which would be the check
    planting the exact file it exists to prevent. That assumption is self-checking:
    if the script ever locates its root some other way it will find no decoy in
    this tree, run on past the plant loop into `docker build`, and this test will
    fail on the timeout below rather than pass quietly.

    **Both positions are exercised**, because they ask different halves of one
    question. A decoy with the *first* planted name means the script wrote nothing
    before refusing, so the directory must afterwards hold the decoy alone. A decoy
    with the *last* means the earlier files really were planted, and they must be
    gone — a fix that made `cleanup` remove nothing at all would pass the first
    case and leave the check planting the debris it guards against.

    **The mutation this survives:** have `cleanup` iterate `PLANTED_FILES` again
    rather than the names it recorded as written. **The near miss that must stay
    green:** any bookkeeping that distinguishes the two — recording each name after
    its `printf` succeeds, or checking existence before the loop starts and
    skipping cleanup for what was already there.
    """
    script = read_check_script()
    names = planted_names(script)
    directory = prompts_directory(script)

    assert names, (
        f"No `PLANTED_FILES` array was read out of {CHECK_SCRIPT.relative_to(REPO_ROOT)}, so this "
        "test does not know a name the check would refuse. Planting a decoy it does not recognise "
        "would send it past the plant loop into a `docker build`, which is a broken test rather "
        "than a red one."
    )
    assert directory, (
        f"No `PROMPTS_SOURCE_DIRECTORY` was read out of {CHECK_SCRIPT.relative_to(REPO_ROOT)}, so "
        "this test does not know where the check plants and could not put a decoy in its way."
    )

    bash = shutil.which("bash")
    if bash is None:
        pytest.fail(
            "bash is not on PATH, so the check cannot be executed. This fails rather than "
            "skipping: a skip is indistinguishable from a refusal that preserved the file."
        )

    survivors: list[str] = []
    for label, decoy_name in (("the first name it plants", names[0]), ("the last", names[-1])):
        root = tmp_path / re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
        (root / "scripts" / "ci").mkdir(parents=True)
        copy = root / "scripts" / "ci" / CHECK_SCRIPT.name
        copy.write_text(script, encoding="utf-8")
        copy.chmod(0o755)
        (root / ".dockerignore").write_text(
            "# stand-in: the check only asserts this file exists before it plants.\n*\n!backend\n",
            encoding="utf-8",
        )
        prompts = root / directory
        prompts.mkdir(parents=True)

        decoy = prompts / decoy_name
        decoy.write_text("a developer's own file, not the check's\n", encoding="utf-8")

        try:
            # S603: the executable is a resolved absolute path and the script is a
            # copy of one from this repository, run inside a temporary directory.
            completed = subprocess.run(  # noqa: S603
                [bash, str(copy)],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                timeout=REFUSAL_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            pytest.fail(
                f"The check ran for more than {REFUSAL_TIMEOUT_SECONDS}s over a planted decoy "
                f"({decoy_name}). The refusal path exits before any `docker build`, so it got "
                "past the plant loop — most likely the decoy is no longer a name it plants, or it "
                "no longer finds its repository root beside itself. Either way this test is "
                "broken rather than red, and it may have started building an image."
            )

        remaining = sorted(path.name for path in prompts.iterdir())
        output = completed.stdout + completed.stderr

        if completed.returncode == 0:
            survivors.append(
                f"  decoy at {label} ({decoy_name}): the check exited 0 rather than refusing"
            )
        elif decoy_name not in output:
            survivors.append(
                f"  decoy at {label} ({decoy_name}): exited {completed.returncode} without naming "
                f"the file it refused\n    {output.strip()[:400]}"
            )
        elif remaining != [decoy_name]:
            survivors.append(
                f"  decoy at {label} ({decoy_name}): the directory afterwards holds {remaining}, "
                f"expected [{decoy_name!r}]"
            )

    assert not survivors, "\n".join(
        [
            "The image-content check does not leave a refused file where it found it:",
            *survivors,
            "",
            "The refusal exists because these names are the script's own, so one already there is "
            "either debris from an interrupted run or somebody else's file — and the script says "
            "so, printing 'Delete it if it is debris from an interrupted run'. `trap cleanup EXIT` "
            "is installed before the plant loop and removes every name in `PLANTED_FILES` "
            "whatever happened, so the refusal is followed by exactly the deletion it refused to "
            "make. Reproduced: the decoy is gone afterwards, a re-run succeeds, and nothing "
            "records the loss.",
            "",
            "The other half is asserted with it and is not a separate requirement: cleanup that "
            "removed nothing would keep the decoy and leave the check's own planted files sitting "
            "in `backend/app/ai/prompts/` — which is the check planting the exact file it exists "
            "to prevent.",
        ]
    )


def test_the_dockerignore_no_longer_calls_the_prompts_directory_a_path_the_others_do_not_have() -> (
    None
):
    """Finding 3's other half: the reason written beside the four suffixes is false.

    The comment says the four were singled out "because the package-data glob in
    `pyproject.toml` makes this one directory a path into the image that the others
    do not have", and that `.pem`/`.key` block eleven lines above it is the
    counterexample — same directory, same glob, and measurably excluded by those
    two lines. The sentence beside it, that "nothing yet guards the patterns above
    this block the same way", stops being true the moment the battery covers them.

    A false reason in a comment is more expensive than no reason: it tells the next
    reader that the other patterns are unreachable, which is the belief that leaves
    `backend/**/*.pem` ungated for a second ticket. `docs/MISTAKES.md` entry 1.

    This asserts the absence of two specific claims rather than the presence of a
    correct comment, because what the replacement should say is the implementer's
    to write. Both searches are deliberately narrow: a rewritten comment naming a
    genuinely unguarded set — the `.env` patterns, the two mock service blocks —
    is true and has to stay green.

    **The mutation this survives:** restore either sentence to `.dockerignore`.
    **The near miss that must stay green:** a comment saying that nothing yet
    guards the `.env` patterns or the `mock-lms` and `mock-idp` blocks, which is
    still true and worth keeping.
    """
    assert DOCKERIGNORE.is_file(), (
        f"{DOCKERIGNORE} does not exist. Without it the build context is everything in the tree, "
        "and every re-exclusion this ticket is about is gone rather than merely undocumented."
    )

    quoted = collapsed(FALSE_EXCLUSIVITY_NOTE)
    for pattern in (EXCLUSIVITY_CLAIM, NOTHING_ELSE_GUARDED_CLAIM):
        assert pattern.search(quoted), (
            f"The search {pattern.pattern!r} does not match the sentence it exists to find, "
            "quoted from `.dockerignore` as it stands. It has gone blind, and the assertions "
            "below would pass against any file at all."
        )

    text = collapsed(DOCKERIGNORE.read_text(encoding="utf-8"))
    assert DOCKERIGNORE_CANARY in text, (
        f"`{DOCKERIGNORE_CANARY}` is not in `.dockerignore` once comment markers and line breaks "
        "are collapsed. Either that re-exclusion is gone — which is the deletion this whole "
        "ticket is about, and `scripts/ci/check_image_contents.sh` is where it is diagnosed — or "
        "the flattening above has eaten the text. Both make the searches below silent, and a "
        "silent search passes."
    )

    still_claimed = [
        pattern.pattern
        for pattern in (EXCLUSIVITY_CLAIM, NOTHING_ELSE_GUARDED_CLAIM)
        if pattern.search(text)
    ]

    assert not still_claimed, "\n".join(
        [
            f"`.dockerignore` still carries {still_claimed}.",
            "",
            "Both claims are false. `backend/**/*.pem` and `backend/**/*.key` reach "
            "`backend/app/ai/prompts/` through the same `pyproject.toml` package-data glob that "
            "makes the four suffixes below them reachable — measured, by planting `probe.pem` and "
            "`probe.key` and listing the installed directory inside a built image, where both "
            "were excluded. So the prompts directory is not a path the other patterns do not "
            "have, and those two lines are in fact the only lines in this file whose deletion "
            "ships a private key.",
            "",
            "Say what is true instead: which patterns the gate plants a file for, and which it "
            "does not. A comment claiming the unguarded patterns are unreachable is what left "
            "these two ungated through a whole ticket about gate fidelity.",
        ]
    )
