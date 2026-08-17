"""No tracked file carries an unresolved merge-conflict marker.

This exists because one did, for two pull requests and a merge to the epic
branch, and every gate stayed green the whole time. `docs/MISTAKES.md` was
merged with six conflicted regions and committed with the markers still in it
(commit `7f5b300`, pull request #24). Pull request #27 then re-sorted that same
file and did not notice them, because a marker in the middle of a paragraph
looks like prose to a reader who is scanning headings.

The reason nothing caught it is the interesting half. `ruff`, `mypy` and the
Python test suite only read `.py` files, so a conflicted Markdown document is
invisible to all three; the build gates read Compose files and Dockerfiles. The
repository's own documentation — the spec, the mistakes log, the ticket set —
is load-bearing here in a way it is not everywhere, since it is what every
agent reads before starting work, and nothing was checking it was well formed.

So this sweep is over everything git tracks rather than over the source tree. A
conflicted Markdown file is a wrong instruction, a conflicted YAML file is a
broken workflow, and a conflicted Python file is a syntax error — the third is
the only one anything else here would have caught.

The markers are assembled at run time rather than written literally, so that
this module does not fail itself, and so that a reader who greps for a marker
finds the real thing rather than this file.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# `<<<<<<< `, `=======` and `>>>>>>> ` as git writes them, built rather than
# quoted. A marker line starts at column zero; a line that merely contains one
# of these runs is not a conflict, which matters because `=======` under a
# heading is ordinary Markdown and appears in this repository already.
OURS = "<" * 7 + " "
THEIRS = ">" * 7 + " "
DIVIDER = "=" * 7

# Every text file in this repository is UTF-8. A tracked file that will not
# decode is a binary — an image, the design prototype's thumbnail — and git
# writes no marker into one, so it is skipped below rather than listed here.
ENCODING = "utf-8"


def tracked_files() -> list[Path]:
    """Every path in the index, as git reports it.

    `git ls-files` rather than a filesystem walk, so the sweep covers exactly
    what a merge can conflict in: an ignored file cannot be conflicted, and a
    file nobody tracks cannot reach another checkout. It also means a new
    directory is swept the moment it is added, with no list here to update.
    """
    git = shutil.which("git")
    if git is None:  # pragma: no cover - git is present in CI and in `make ci`
        pytest.fail(
            "git is not on PATH, so this sweep cannot enumerate tracked files. It fails "
            "rather than skipping: a skip here is indistinguishable from a clean tree."
        )

    # The argument list is a literal and the executable is a resolved absolute
    # path, so neither S603's untrusted input nor S607's partial path applies.
    listing = subprocess.run(  # noqa: S603
        [git, "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return [REPO_ROOT / name for name in listing.stdout.split("\0") if name]


def conflicted_lines(path: Path) -> list[tuple[int, str]]:
    """Marker lines in one file, with their line numbers, or nothing."""
    try:
        text = path.read_text(encoding=ENCODING)
    except (UnicodeDecodeError, FileNotFoundError):
        # Binary, or tracked-but-absent in this checkout. Neither can hold a
        # marker git would have written.
        return []
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.startswith(OURS) or line.startswith(THEIRS) or line == DIVIDER:
            found.append((number, line))
    return found


def test_the_index_holds_no_conflict_marker() -> None:
    tracked = tracked_files()
    assert tracked, (
        "git ls-files reported nothing tracked, so this sweep looked at no files "
        "and would pass against a repository full of conflict markers."
    )

    offenders = {
        path.relative_to(REPO_ROOT): lines for path in tracked if (lines := conflicted_lines(path))
    }

    assert not offenders, "Unresolved merge-conflict markers are committed:\n" + "\n".join(
        f"  {name}:{number}: {line}"
        for name, lines in sorted(offenders.items())
        for number, line in lines
    )
