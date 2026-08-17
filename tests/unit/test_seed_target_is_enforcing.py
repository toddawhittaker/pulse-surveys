"""`make seed` stops tolerating an absent script — ticket E0-17.

E0-17's scope ends with "`make seed` runs it against the running stack", and the
Makefile currently ships the tolerant version of that target:

    @if [ -f scripts/seed.py ]; then $(PYTHON) scripts/seed.py; \\
    else $(call skip,no scripts/seed.py yet); fi

That guard is the same device every other gate in this repository shipped with
and the same one every ticket removes when it lands the thing being guarded —
[ADR 0002](../../docs/adr/0002-ci-gates-ship-tolerant.md) and the epic README's
"How CI tightens" table. While it is there, deleting `scripts/seed.py` turns the
target into a no-op that prints a dim line and exits zero, so the demo
institution can go missing with `make seed` still "passing".

`tests/unit/test_ci_migration_and_test_gates.py` is the precedent, and both of
its lessons are taken. The recipe is read as *lines that could execute*, with `#`
comments truncated, because a commented-out command must not count as the target
running one. And the two halves are asserted together: "no tolerance" alone is
satisfied by a target with nothing left in it.

**Why the Makefile and not `.github/workflows/ci.yml`.** No CI job runs `make
seed` — the seed needs a stack, and CI's Compose pass brings one up without one.
So the Makefile is where this target lives and the only place its tolerance can
be removed.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE_PATH = REPO_ROOT / "Makefile"

# SPEC §13: "`scripts/` … `seed.py` — demo institution, hierarchy, term, sample
# sections", and E0-17's scope repeats the path.
SEED_SCRIPT_PATH = REPO_ROOT / "scripts" / "seed.py"

# The target E0-17 names. `make seed` is what the ticket and `README.md` tell a
# developer to run.
SEED_TARGET = "seed"

# What the tolerance looks like today, as fragments. Two rather than one because
# they are two mechanisms and either alone leaves a target that skips: the file
# test decides whether to run anything, and `$(call skip,...)` is this Makefile's
# own helper for printing a dim "skipped — …" line and exiting zero.
TOLERANCE_FRAGMENTS = ("-f scripts/seed.py", "$(call skip")

# What the target must still do once the tolerance is gone. Not a new
# requirement: it is what the recipe already runs, and it is here so that
# "no tolerance" cannot be satisfied by deleting the command.
REQUIRED_FRAGMENT = "scripts/seed.py"

SHELL_COMMENT = re.compile(r"#.*$")
CONTINUATION = re.compile(r"\\\s*\n\s*")


def makefile_text() -> str:
    """The Makefile, or a failure saying it is not there."""
    if not MAKEFILE_PATH.is_file():
        pytest.fail(
            f"{MAKEFILE_PATH} does not exist. SPEC §13 puts a Makefile at the repository root "
            "with 'up / test / lint / migrate / seed shortcuts', and this test is about one of "
            "them."
        )
    return MAKEFILE_PATH.read_text(encoding="utf-8")


def recipe_for(text: str, target: str) -> list[str]:
    """The lines of one target's recipe that could execute something.

    A recipe is the tab-indented block following `target:`. Continuations are
    joined first, so a command split across two lines is read as one; then a `#`
    and everything after it goes, because a commented-out command is a line that
    ships without executing — which is the distinction
    `test_ci_migration_and_test_gates.py` exists to keep.
    """
    joined = CONTINUATION.sub(" ", text)
    lines = joined.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if re.match(rf"^{re.escape(target)}\s*:(?!=)", line)
    ]
    if not starts:
        pytest.fail(
            f"The Makefile declares no `{target}:` target. E0-17's scope says '`make {target}` "
            "runs it against the running stack'; if the target has been renamed, rename it here "
            "too rather than leaving this test looking for something that is gone."
        )

    found: list[str] = []
    for start in starts:
        for line in lines[start + 1 :]:
            if not line.startswith("\t"):
                break
            body = SHELL_COMMENT.sub("", line).strip()
            if body:
                found.append(body)
    return found


def test_the_seed_target_no_longer_skips_when_the_script_is_absent() -> None:
    """The tolerance goes, and the target still runs the script.

    The two assertions are one property and cannot be separated. Requiring the
    guard to be gone, on its own, is satisfied by a recipe with no commands left;
    requiring the command to be there, on its own, is satisfied by a recipe that
    still skips it. Together they say `make seed` runs the seed unconditionally,
    which is what makes a missing seed script a failure rather than a dim line.
    """
    recipe = recipe_for(makefile_text(), SEED_TARGET)
    assert recipe, (
        f"The `{SEED_TARGET}:` target has an empty recipe, so it runs nothing at all. That "
        "passes the tolerance check below for the wrong reason, which is why the two are "
        "asserted together."
    )

    tolerant = [
        line for line in recipe if any(fragment in line for fragment in TOLERANCE_FRAGMENTS)
    ]
    assert not tolerant, "\n".join(
        [
            f"`make {SEED_TARGET}` still skips itself when `scripts/seed.py` is absent:",
            *(f"  {line}" for line in tolerant),
            "",
            "E0-17 is the ticket that writes that script, and landing it includes removing the "
            "guard — the same move every gate in the 'How CI tightens' table makes when the "
            "thing it guards arrives (ADR 0002). While the guard is there, deleting the seed "
            "script leaves `make seed` printing 'skipped' and exiting zero, so the demo "
            "institution every later epic develops against can disappear with nothing red.",
        ]
    )

    assert any(REQUIRED_FRAGMENT in line for line in recipe), "\n".join(
        [
            f"`make {SEED_TARGET}` no longer runs `{REQUIRED_FRAGMENT}`. It runs: {recipe}.",
            "",
            "This is the other half of the assertion above and not a separate requirement: a "
            "recipe whose command has been deleted has no tolerance guard either, so without "
            "this the test would pass most enthusiastically against a target that had stopped "
            "doing anything.",
        ]
    )


def test_the_seed_script_exists_where_the_spec_puts_it() -> None:
    """SPEC §13: `scripts/seed.py`. Asserted here because it needs no database.

    The integration module reports this too, from inside its fixture, but only on
    a machine with a Docker daemon — and this is the deliverable the whole ticket
    is, so it is worth one assertion that runs everywhere the unit suite does.
    """
    assert SEED_SCRIPT_PATH.is_file(), (
        f"{SEED_SCRIPT_PATH} does not exist. SPEC §13's repository layout puts the demo seed "
        "there — 'seed.py — demo institution, hierarchy, term, sample sections' — and E0-17 is "
        "the ticket that writes it. `tests/integration/test_demo_seed_script.py` is where what it "
        "loads is asserted."
    )
