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

**Two of these tests search text for a pattern, which is a shape that fails
silently** (`docs/MISTAKES.md` entry 3, third case — a regex that matched nothing
and went green against the exact text it existed to catch). Both carry a canary:
a string that must be present in any README of prompts at all, asserted before
the search that matters, so a search over the wrong file or over an empty string
says so instead of passing.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# E0-12's scope and SPEC §13 both spell the directory.
PROMPTS_DIR = REPO_ROOT / "backend" / "app" / "ai" / "prompts"

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
