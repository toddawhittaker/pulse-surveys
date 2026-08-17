"""The §4.1 invariant gate stops tolerating an empty run — ticket E0-10.

Two of E0-10's acceptance criteria are about the gate rather than about the
database: "CI fails if an invariant test is skipped or xfailed", and "the
invariant checker's `--allow-empty` flag is gone from both CI and the Makefile".
The first is what `scripts/ci/check_invariants.py` already does and what
`scripts/ci/test_ci_scripts.py` already asserts; the second is a change to two
files that no test reads, which is exactly the shape that ships and is never
noticed.

`ADR 0002` records why the gates shipped tolerant and the epic README carries the
table of which ticket makes each one enforcing. This is that row: "§4.1 invariant
suite — no skips permitted | 10". The tolerance is not a detail of the flag —
with `--allow-empty` in place, a pipeline where the invariant suite collected
nothing at all is green, and a green checkmark is indistinguishable from one
where every §4.1 assertion ran and passed.

**Both halves are asserted, and the second is why this file exists at all.** The
flag has to be gone from the two invocations; and the Makefile comment that says
it "stays until E0-10 adds the first §4.1 invariant" has to be gone with it,
because a record that goes on asserting something a change has made false is
`docs/MISTAKES.md` entry 1 — nine incidents, and the most expensive of them was
the one a reader trusted over the code.
"""

import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE_PATH = REPO_ROOT / "Makefile"

CHECKER = "scripts/ci/check_invariants.py"
TOLERANCE_FLAG = "--allow-empty"

# The claim the Makefile carries today, quoted as it stands, wrap included. The
# search below is run against this sample before it is run against the file,
# because `docs/MISTAKES.md` entry 3's third incident was a pattern that matched
# nothing across a comment wrap and went green against the exact comment it
# existed to catch. The pattern is short enough to sit inside one line of the
# current wrap, and the text is normalised anyway so that re-wrapping the comment
# — which is what an editor does to a sentence somebody has edited — cannot
# quietly blind it.
STALE_TOLERANCE_NOTE = (
    "# `--allow-empty` stays until E0-10 adds the first §4.1 invariant; the workflow\n"
    "# passes it too, and the two move together."
)

STALE_TOLERANCE_PATTERN = re.compile(r"stays\s+until\s+E0-10", re.IGNORECASE)


def collapsed(text_: str) -> str:
    """`text_` with every run of whitespace and comment marker flattened to one space.

    So that a claim wrapped across two comment lines reads as one sentence, which
    is how a human reads it and is not how a file stores it.
    """
    return re.sub(r"\s+", " ", text_.replace("#", " "))


def strings_in(node: Any) -> list[str]:
    """Every string anywhere in a parsed YAML document."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [
            found for key, value in node.items() for found in strings_in(key) + strings_in(value)
        ]
    if isinstance(node, list):
        return [found for item in node for found in strings_in(item)]
    return []


def checker_invocations(text_: str) -> list[str]:
    """Every command in `text_` that runs the invariant checker, line continuations joined."""
    joined = text_.replace("\\\n", " ")
    return [line.strip() for line in joined.splitlines() if CHECKER in line]


def test_neither_ci_nor_the_makefile_tolerates_an_empty_invariant_run(ci_workflow: Any) -> None:
    """Criterion: the `--allow-empty` flag is gone from both CI and the Makefile.

    **The canary is the first assertion, not decoration.** "No invocation passes
    the flag" is perfectly true of a file that no longer invokes the checker at
    all — which is the same green checkmark and a worse state than the one this
    ticket is fixing. So each file is required to invoke it first
    (`docs/MISTAKES.md` entry 3).

    The workflow is read through the parsed document rather than as text, so a
    `run:` block that has been commented out stops counting as an invocation at
    the moment it stops being one.
    """
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    workflow_commands = "\n".join(strings_in(ci_workflow))

    invocations = {
        "Makefile": checker_invocations(makefile),
        ".github/workflows/ci.yml": checker_invocations(workflow_commands),
    }

    for where, commands in invocations.items():
        assert commands, (
            f"{where} no longer runs `{CHECKER}` at all. The §4.1 invariant suite is the one gate "
            "CLAUDE.md says may never be skipped, and a pipeline that stopped running the checker "
            "is greener than one that runs it with `--allow-empty`, not safer. If the invocation "
            "moved, this test needs to be pointed at where it went."
        )

    tolerant = {
        where: [command for command in commands if TOLERANCE_FLAG in command]
        for where, commands in invocations.items()
    }
    tolerant = {where: commands for where, commands in tolerant.items() if commands}
    assert not tolerant, (
        f"The invariant checker is still invoked with `{TOLERANCE_FLAG}`: {tolerant}. E0-10 is the "
        "ticket that removes it — the epic README's 'How CI tightens' table gives this gate to "
        "ticket 10 — because this ticket lands the first §4.1 invariants. With the flag in place, "
        "a suite that collected zero invariant tests exits 0, so deleting every §4.1 assertion in "
        "the repository is a green pipeline. `scripts/ci/check_invariants.py` keeps the flag as an "
        "option; what has to go is passing it."
    )


def test_the_makefile_no_longer_says_the_tolerance_lasts_until_this_ticket() -> None:
    """The record beside the flag has to go with the flag.

    `docs/MISTAKES.md` entry 1 is a record that went on asserting something a
    change had made false, twelve times across four tickets, and its rule is to
    ask what else in the repository makes a claim about the thing you changed.
    The Makefile makes one, one line above the invocation: "`--allow-empty` stays
    until E0-10 adds the first §4.1 invariant; the workflow passes it too, and
    the two move together." After this ticket both halves of that sentence are
    false.

    **The pattern is run against the text it claims to catch before it is
    believed.** The incident behind that rule is a search that matched nothing
    across a comment wrap and reported success against the exact comment it
    existed to catch (entry 3, third incident).
    """
    assert STALE_TOLERANCE_PATTERN.search(collapsed(STALE_TOLERANCE_NOTE)), (
        "The search in this test does not match the very sentence it exists to find, quoted from "
        "the Makefile as it stands. It has gone blind, and the assertion below would pass against "
        "any Makefile at all."
    )

    makefile = collapsed(MAKEFILE_PATH.read_text(encoding="utf-8"))
    match = STALE_TOLERANCE_PATTERN.search(makefile)
    assert match is None, (
        f"The Makefile still says {makefile[max(match.start() - 80, 0) : match.end() + 80]!r}. "
        "The tolerance it describes is what this ticket removes, so the sentence is now a record "
        "asserting something the change made false — `docs/MISTAKES.md` entry 1, whose rule is to "
        "sweep for what else in the repository claims something about the thing you changed. One "
        "other place makes a claim about this flag and is worth the same sweep: "
        "`tests/integration/test_application_role_privileges.py`'s docstring explains why nothing "
        "there is marked `invariant`, quoting E0-04 that the checker keeps `--allow-empty` 'until "
        "E0-10 adds the first §4.1 invariant'."
    )
