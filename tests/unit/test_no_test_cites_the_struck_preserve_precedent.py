"""No test cites the preserve/restore precedent the record struck — ticket E2-03.

E1's boundary record corrections found that the revision
`test_the_section_binding_survives_a_downgrade.py` cited as a preserve/restore
precedent does no data migration at all — its own docstring says so — and struck
the claim from `boundary-review.md` in the same merge. The test docstring went on
asserting it, which is `docs/MISTAKES.md` entry 1 exactly: a record kept saying
something a change had made false, in the place nobody re-reads.

E2-03's second acceptance criterion is that the docstring correction is in and
that a grep for the struck revision's id under `tests/` finds no claim the
record struck. This module is that grep, run by CI instead of by whoever
remembers. The correction itself is a one-line edit and would stay correct for
exactly as long as nobody copied the sentence into a second module
(`docs/MISTAKES.md` entry 2: after fixing something, try to reintroduce it — if
the suite stays green you have written a convention rather than a guarantee).

**The struck id is assembled at run time and is spelled nowhere in this file,
this sentence included.** The reason is the one
`test_no_unresolved_merge_conflicts.py` gives for assembling its conflict
markers rather than quoting them: the criterion is a grep over `tests/` that has
to come back empty, so a module that wrote the id out — in a constant or in its
own prose — would be the thing it forbids.

That is not hypothetical. The first version of this file quoted the id twice in
this docstring, and the sweep duly reported its own module as two offenders
while the sibling docstring it exists to guard was already correct. The repair
was to stop spelling it, and deliberately not to exempt this file from the
sweep: an exemption buys the green by making the guard blind to one file, and
the file it would have been blind to is the one most likely to carry the token
(`docs/MISTAKES.md` entry 3). So the sweep still reads its own source, and this
module is subject to its own rule.

**The sweep carries a canary.** A search that has gone blind — the wrong root, a
glob that matches nothing, a decode that silently swallows every file — reports
"no offenders" and reads as a pass. So the same reader is asked for a revision
identifier that is certainly cited under `tests/`, in a file that is not this
one, and has to find it (`docs/MISTAKES.md` entry 3).

Nothing here is about the migrations themselves. The struck revision is a real
revision, and the tree is full of legitimate references to its id —
`down_revision` chains, index-naming notes, the E1 records that document the
strike, and the ticket and the carried bullet that name it so a reader can find
it. Those stay, and none of them is under `tests/`. What was struck is a claim
made in a test's prose, and `tests/` is the scope the criterion names.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = REPO_ROOT / "tests"

# The struck revision, assembled so that this module is not itself an occurrence
# of what it forbids. Written as two halves of the same identifier and joined,
# rather than as anything cleverer, so a reader can see what it is.
STRUCK_REVISION = "e2c94b6a" + "1f70"

# A revision identifier that is certainly cited under `tests/`: the binding
# migration, which `test_the_section_binding_survives_a_downgrade.py` and
# `test_the_restore_refuses_a_binding_whose_registration_is_gone.py` both pin
# their work to by name. The canary — if the reader cannot find this, it has
# stopped reading and its silence about the struck one means nothing.
LIVE_REVISION = "b8c41f7d2e05"

ENCODING = "utf-8"

# Compiled bytecode is a copy of a source file this sweep already reads, and it
# is not text. Skipped rather than decoded.
SKIPPED_DIRECTORIES = ("__pycache__",)


def citations(token: str) -> dict[Path, list[tuple[int, str]]]:
    """Every line under `tests/` holding `token`, by file, with line numbers.

    Every file rather than only `*.py`: a claim in a fixture's data file or in a
    README beside the tests is the same claim, and the criterion's grep is over
    the directory.
    """
    found: dict[Path, list[tuple[int, str]]] = {}
    for path in sorted(TESTS_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIPPED_DIRECTORIES for part in path.parts):
            continue
        try:
            text = path.read_text(encoding=ENCODING)
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        lines = [
            (number, line.strip())
            for number, line in enumerate(text.splitlines(), start=1)
            if token in line
        ]
        if lines:
            found[path] = lines
    return found


def test_the_sweep_can_find_a_revision_that_is_cited() -> None:
    """The canary: this reader is reading, and it is reading somebody else's file.

    **The mutation this must kill:** a sweep pointed at nothing — the wrong root,
    a glob that matches no file, an exception swallowed per file. All of them make
    the test below pass while reading zero lines, which is `docs/MISTAKES.md`
    entry 3's shape and is the ordinary way a text guard dies.

    **The near miss it must survive:** finding only itself. This module names
    `LIVE_REVISION` in its own source, so "the token was found" is true of a
    reader that can see one file. The assertion is on a *different* file citing
    it.
    """
    found = citations(LIVE_REVISION)
    elsewhere = sorted(path for path in found if path != Path(__file__).resolve())

    assert elsewhere, (
        f"This sweep read the files under {TESTS_ROOT} and found no citation of "
        f"{LIVE_REVISION} in any of them except its own source. That revision is the subject of "
        "`test_the_section_binding_survives_a_downgrade.py` and of "
        "`test_the_restore_refuses_a_binding_whose_registration_is_gone.py`, both of which pin "
        "their work to it by name, so a reader that cannot see it there is not reading — and the "
        "test below would report 'no offenders' about a directory it never opened."
    )


def test_no_file_under_tests_cites_the_struck_preserve_precedent() -> None:
    """E2-03 criterion 2: the docstring names no precedent the record has struck.

    **The mutation this must kill, and it is the state of the tree today:** the
    module docstring of `test_the_section_binding_survives_a_downgrade.py`
    claiming that revision's downgrade "preserves into a scratch table" as the
    precedent for the fix shape. The E1 boundary corrections struck that claim as
    false in the same merge that made it, and it stayed in the test.

    **The near miss it must survive:** the sentence being moved rather than
    corrected — copied into a sibling module, a fixture, or a helper's docstring.
    The sweep is over the whole directory rather than over the one file the
    finding named, so a claim that relocates is still a claim.

    Its canary is `test_the_sweep_can_find_a_revision_that_is_cited` above.
    """
    offenders = citations(STRUCK_REVISION)

    assert not offenders, (
        f"{sum(len(lines) for lines in offenders.values())} line(s) under {TESTS_ROOT} cite the "
        "revision E1's boundary record corrections struck as a preserve/restore precedent — it "
        "does no data migration at all, and its own docstring says so:\n"
        + "\n".join(
            f"  {path.relative_to(REPO_ROOT)}:{number}: {line}"
            for path, lines in sorted(offenders.items())
            for number, line in lines
        )
        + "\n\nA test's prose is a record like any other (`docs/MISTAKES.md` entry 1). Describe "
        "the fix shape without a precedent, or cite the revision that actually does it — the "
        "binding migration preserves and restores its own pair, and this suite proves that it "
        "does."
    )
