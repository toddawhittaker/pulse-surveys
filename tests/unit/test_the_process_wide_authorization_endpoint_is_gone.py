"""The process-wide authorization endpoint is deleted, not demoted — E1-05, criterion 2.

The criterion: "`grep -r LTI_PLATFORM_AUTHORIZATION_ENDPOINT` over the tree finds
only history (ADRs, tickets); no code, config, example, or Compose reference."
The carried entry it comes from says why the distinction matters — the setting
has to be **gone** from `Settings` and `.env.example` "rather than left as a
default the column falls back to". A setting that survives as a fallback is the
finding still open: one address standing in for every registration that does not
carry its own, reached now through an `or` instead of directly.

**Why a sweep rather than an assertion about `Settings`.** Reading the field off
the settings object answers for one of the four places the criterion names.
The value also reached `backend/app/api/lti.py`, `backend/app/api/dev.py`,
`.env.example`, this suite's own door fixtures and two docstrings, and a
deletion that leaves any of those is a repository that still describes a setting
nothing supplies (`docs/MISTAKES.md` entry 1). One search over everything git
tracks is the shape that covers all of them and covers the next one nobody has
written yet.

**Matched without regard to case, which is not a detail.** The variable is
`LTI_PLATFORM_AUTHORIZATION_ENDPOINT` and the pydantic field behind it is
`lti_platform_authorization_endpoint`; the reader in `app/api/lti.py` spells only
the lower-case one. A case-sensitive sweep for the upper-case spelling reports
this criterion met over a tree where the field, its default and its two readers
are all exactly where they were — green for a reason unrelated to what it
asserts. So the needle is one identifier, folded, and the control below shows it
finding both spellings.

**Three directories are allowed, and they are the ones that hold history.** ADRs,
tickets and the mistakes log describe decisions that were true when they were
written; ADR 0075 chose this setting and ADR 0077 records what it left standing,
and rewriting either would be falsifying a record rather than finishing a
ticket.

**The planted-positive control is not optional here** (`docs/MISTAKES.md` entry
3). A sweep that reports a clean tree and a sweep that has gone blind print the
same thing, and this one has three ways to go blind: an enumeration that returns
nothing, a needle that matches nothing, and a folded comparison applied to only
one side. So the matcher is run against a planted line in both spellings, against
two near misses it must not claim, and against the tree's own remaining history —
which must still be found, or the search is looking at nothing.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The identifier, assembled at run time. Written out, this module would be its own
# offender and would also be what a person greps up when they go looking for the
# real thing — `tests/unit/test_no_unresolved_merge_conflicts.py` builds its
# markers the same way and for the same two reasons.
NEEDLE = "LTI_PLATFORM_" + "AUTHORIZATION_ENDPOINT"

# Where history is allowed to go on naming it. Paths as `git ls-files` reports
# them, so the comparison is a prefix on a repository-relative POSIX path.
HISTORY_DIRECTORIES = ("docs/adr/", "docs/tickets/", "docs/mistakes/")

# Every text file here is UTF-8. A tracked file that will not decode is a binary
# — an image, the design prototype's thumbnail — and cannot carry an identifier.
ENCODING = "utf-8"

# What the planted control writes: the line `.env.example` actually carried,
# assembled from the needle rather than transcribed, so that a rename of the
# constant above moves the plant with it.
PLANTED_LINE = f"{NEEDLE}=http://localhost:8080/oidc/authorize"

# The near misses the sweep must not claim, and they are live rather than
# hypothetical. `OIDC_AUTHORIZATION_ENDPOINT` is the web door's own setting,
# which this ticket does not touch, and `authorization_endpoint` is the name of
# the **column** E1-05 adds — after this ticket it appears in the model, the
# migration, the seed, the fixtures and this suite. A sweep matching either would
# report the criterion failed by the thing that satisfies it.
NEAR_MISSES = (
    "OIDC_AUTHORIZATION_ENDPOINT=https://idp.example.edu/oidc/authorize",
    "    authorization_endpoint: Mapped[str | None]",
    "platform.authorization_endpoint",
)


def tracked_files() -> list[Path]:
    """Every path in the index, as git reports it.

    `git ls-files` rather than a filesystem walk. It is the enumeration the
    criterion means — a value that is not committed is not a reference this
    repository ships — and it excludes `.venv`, `node_modules` and `.git` by
    construction rather than by a list here that a new build directory would slip
    past. A new directory is swept the moment it is added.

    A copy of the same helper in `tests/unit/test_no_unresolved_merge_conflicts.py`,
    which is the other sweep over the whole index. Two copies rather than a
    shared one because each is four lines and the shared version would live in a
    fixtures module that both sweeps would then depend on for their subject.
    """
    git = shutil.which("git")
    if git is None:  # pragma: no cover - git is present in CI and in `make ci`
        pytest.fail(
            "git is not on PATH, so this sweep cannot enumerate tracked files. It fails rather "
            "than skipping: a skip here is indistinguishable from a tree that no longer names "
            "the setting."
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


def mentions_the_setting(path: Path) -> list[tuple[int, str]]:
    """The lines of one file that name the setting, folded, with their numbers."""
    try:
        text = path.read_text(encoding=ENCODING)
    except (UnicodeDecodeError, FileNotFoundError):
        # Binary, or tracked-but-absent in this checkout. Neither can carry an
        # identifier anybody reads.
        return []
    needle = NEEDLE.lower()
    return [
        (number, line.strip())
        for number, line in enumerate(text.splitlines(), start=1)
        if needle in line.lower()
    ]


def is_history(path: Path) -> bool:
    """Whether a tracked path is one of the three directories that hold history."""
    relative = path.relative_to(REPO_ROOT).as_posix()
    return relative.startswith(HISTORY_DIRECTORIES)


# ---------------------------------------------------------------------------
# The controls, first, because everything below is only as good as they are.
# **A red in this section means these tests are broken, not the code.**
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spelling", ("upper", "lower"))
def test_the_sweep_finds_a_planted_setting_in_either_spelling(
    tmp_path: Path, spelling: str
) -> None:
    """The planted positive: the matcher is shown finding the thing it exists to find.

    A sweep that reports a clean tree and a sweep whose needle matches nothing
    print the same result, and the second is `docs/MISTAKES.md` entry 3's third
    case exactly. Both spellings are planted because the pydantic field is
    lower-case and the environment variable is upper-case, and a sweep folding
    only one side of the comparison finds the variable and misses the field —
    which is the half that actually holds the value.

    The planted line is the one `.env.example` carried, assembled from the same
    constant the sweep uses rather than typed out again.
    """
    line = PLANTED_LINE.upper() if spelling == "upper" else PLANTED_LINE.lower()
    planted = tmp_path / "planted.env"
    planted.write_text(
        f"# a file that names the setting\n{line}\nDATABASE_URL=x\n", encoding=ENCODING
    )

    found = mentions_the_setting(planted)

    assert [number for number, _ in found] == [2], (
        f"The matcher found {found} in a file whose second line is {line!r}. Every assertion in "
        "this module is made with it, so it is wrong here before it is wrong about the tree."
    )


@pytest.mark.parametrize("near_miss", NEAR_MISSES)
def test_the_sweep_does_not_claim_a_near_miss(tmp_path: Path, near_miss: str) -> None:
    """The other direction, and after this ticket it is the one that would bite.

    `authorization_endpoint` becomes a column name in the model, the migration,
    the seed and this suite's own fixtures, and `OIDC_AUTHORIZATION_ENDPOINT` is
    the web door's setting, which this ticket does not touch. A needle written as
    `AUTHORIZATION_ENDPOINT` matches all of them, so the criterion would be
    reported failed by exactly the change that satisfies it — and the next person
    would widen the allow-list rather than narrow the needle.
    """
    planted = tmp_path / "near_miss.py"
    planted.write_text(f"{near_miss}\n", encoding=ENCODING)

    assert not mentions_the_setting(planted), (
        f"The matcher reads {near_miss!r} as naming the deleted setting. The needle is the whole "
        f"identifier {NEEDLE!r}; a shorter one catches the column E1-05 adds and the web door's "
        "own setting."
    )


def test_the_sweep_still_finds_the_setting_in_the_records_that_decided_it() -> None:
    """The canary: the search is run against text this repository certainly holds.

    ADR 0075 chose this setting and ADR 0077 recorded what it left standing, and
    neither may be rewritten — a record that described a decision truthfully when
    it was made is history rather than a stale reference. That makes those files
    a string this sweep must go on finding, which is the cheapest available proof
    that the enumeration and the matcher are both alive.

    **A red here means the sweep is looking at nothing**, or that a record was
    edited to remove a decision it documents. Either way the assertion below is
    passing over an absence until it is fixed.
    """
    tracked = tracked_files()
    assert tracked, (
        "git ls-files reported nothing tracked, so this sweep looked at no files at all and would "
        "report any tree clean."
    )

    still_named = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in tracked
        if is_history(path) and mentions_the_setting(path)
    )

    assert still_named, (
        "No file under "
        f"{list(HISTORY_DIRECTORIES)} names {NEEDLE}. Those directories hold the ADRs and tickets "
        "that decided it and the carried entry that ends it, so either this sweep is reading "
        "nothing or a record has been edited to remove a decision it documents. Until this is "
        "fixed, the sweep below is asserting an absence it cannot distinguish from blindness."
    )


# ---------------------------------------------------------------------------
# The criterion itself.
# ---------------------------------------------------------------------------


def test_no_tracked_file_outside_the_records_names_the_process_wide_setting() -> None:
    """Criterion 2: the tree names it only where history is kept.

    **The mutations this kills:** the field left on `Settings` with its default
    intact and nothing reading it, which is the shape a deletion takes when
    somebody removes the *reader* and stops; the `.env.example` block left in
    place, which documents a variable nothing supplies and which the next
    deployment sets in good faith; and the door fixtures left naming it, which
    would keep this suite configuring a setting the application ignores — green,
    and asserting nothing about where a browser is sent.

    **What a legitimate red looks like** is a new file under `docs/adr/` that
    argues about this decision and sits outside the three history directories.
    The answer then is the directory, not the allow-list: a record belongs with
    the other records.
    """
    offenders = {
        path.relative_to(REPO_ROOT).as_posix(): lines
        for path in tracked_files()
        if not is_history(path) and (lines := mentions_the_setting(path))
    }

    assert not offenders, (
        f"These tracked files still name {NEEDLE} outside "
        f"{list(HISTORY_DIRECTORIES)}:\n"
        + "\n".join(
            f"  {name}:{number}: {line}"
            for name, lines in sorted(offenders.items())
            for number, line in lines
        )
        + "\n\nE1-05's second criterion is that the grep finds only history. The carried entry it "
        "comes from asks for the setting to be gone rather than left as a default the column "
        "falls back to — a surviving field with a working default is the finding still open, "
        "reached through an `or` instead of directly. `Settings`, `.env.example`, "
        "`backend/app/api/lti.py`, `backend/app/api/dev.py`, `backend/app/lti/launch.py`'s "
        "docstring and `backend/app/models/lti.py`'s all named it when this ticket was written."
    )
