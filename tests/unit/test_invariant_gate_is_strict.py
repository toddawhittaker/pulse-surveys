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

**E0-36 item 3 gave the gate a second half, and it belongs here for the same
reason.** `check_invariants.py` reads the JUnit XML a run produced, so it can see
a skip, an xfail and an empty collection — and cannot see a test that ran and
asserted nothing, which counts toward the "N invariant test(s) ran, none skipped,
none failed" it prints. `scripts/ci/check_invariant_assertions.py` reads the test
sources instead and refuses a marked test whose body carries no assertion. Two
checkers, one gate, and the same failure available to each: a caller that stops
invoking one of them is greener than a caller that invokes it tolerantly, and
nothing else in this repository would notice. So the test at the foot of this
module asks of both checkers what the test above asks of one.

What that test does **not** assert is that the two run in the same *step*. The
ticket describes them that way and it is how they land; a second step in the same
job runs just as unconditionally, and a test that forbade it would be refusing a
shape nobody has argued against. What matters is that both run, in both callers.
"""

import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE_PATH = REPO_ROOT / "Makefile"

CHECKER = "scripts/ci/check_invariants.py"
TOLERANCE_FLAG = "--allow-empty"

# E0-36 item 3's checker: the half of the gate that reads the tests rather than
# the run they produced. Named here rather than discovered, because the ticket
# names it; if it lands under another name, this constant moves with it.
ASSERTION_CHECKER = "scripts/ci/check_invariant_assertions.py"

# A shell comment and everything after it on the line, cut before a line is read
# as an invocation. A `#` inside a `run:` block, or inside a Makefile recipe, is a
# line that ships without executing, and both of the assertions in this module are
# about whether a checker *runs*. It also keeps the Makefile's own prose out: the
# comment above the `invariants` target names `check_invariants.py` twice, and
# without this a target that had stopped invoking the checker would still look
# like one that invokes it.
#
# Cutting after the continuation join, not before, loses a command in one shape —
# `# something \` followed by a real command, which the shell would run and this
# swallows. That direction fails red, which is the direction to be wrong in.
SHELL_COMMENT = re.compile(r"#.*$")

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


def commands_in(text_: str) -> list[str]:
    """Every line of `text_` that could execute something, continuations joined, comments cut."""
    joined = text_.replace("\\\n", " ")
    found: list[str] = []
    for raw in joined.splitlines():
        line = SHELL_COMMENT.sub("", raw).strip()
        if line:
            found.append(line)
    return found


def checker_invocations(text_: str, checker: str) -> list[str]:
    """Every command in `text_` that runs `checker`.

    Takes the checker as an argument rather than closing over one, so that the two
    halves of the invariant gate are asked the same question by the same code. Two
    copies of "what counts as an invocation" would be free to disagree, and the
    one place that would show is a caller that had stopped invoking one of them
    (`docs/MISTAKES.md` entry 13).
    """
    return [line for line in commands_in(text_) if checker in line]


def test_neither_ci_nor_the_makefile_tolerates_an_empty_invariant_run(ci_workflow: Any) -> None:
    """Criterion: the `--allow-empty` flag is gone from both CI and the Makefile.

    **The canary is the first assertion, not decoration.** "No invocation passes
    the flag" is perfectly true of a file that no longer invokes the checker at
    all — which is the same green checkmark and a worse state than the one this
    ticket is fixing. So each file is required to invoke it first
    (`docs/MISTAKES.md` entry 3).

    The workflow is read through the parsed document rather than as text, so a
    `run:` block that has been commented out stops counting as an invocation at
    the moment it stops being one. A `#` *inside* a `run:` block, and inside a
    Makefile recipe, is cut by `commands_in` for the same reason one layer down —
    which is what this canary had been missing: the Makefile's prose above the
    `invariants` target names `check_invariants.py` while explaining it, so until
    E0-36 the guard was satisfied by the comment whether or not the recipe still
    ran anything.
    """
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    workflow_commands = "\n".join(strings_in(ci_workflow))

    invocations = {
        "Makefile": checker_invocations(makefile, CHECKER),
        ".github/workflows/ci.yml": checker_invocations(workflow_commands, CHECKER),
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


def test_both_callers_run_both_halves_of_the_invariant_gate(ci_workflow: Any) -> None:
    """E0-36 item 3: the assertion checker is wired into CI and into the Makefile.

    A gate that exists in `scripts/ci/` and is invoked by nobody is a file, not a
    gate. This module already carries that lesson for `check_invariants.py` — "a
    pipeline that stopped running the checker is greener than one that runs it
    with `--allow-empty`, not safer" — and the second half arrives with the same
    exposure and one more: it is new, so there is no habit of it being there for a
    reviewer to miss.

    **Both checkers are required of both callers, and that is one property rather
    than a canary bolted onto an assertion.** E0-36 puts the new checker in the
    same gate as the old one; a workflow that ran the assertion checker and
    dropped `check_invariants.py` would have traded a skip gate for an assertion
    gate and told nobody. Asking for both, in both files, is the whole of what
    "the gate has two halves" means from here.

    **The mutation this survives:** delete the
    `python scripts/ci/check_invariant_assertions.py` line from the "Invariant
    suite" step in `.github/workflows/ci.yml`, or from the `invariants` target in
    the `Makefile` — either one alone. **The near miss that must stay green:**
    moving that invocation into a step of its own inside the same job, or giving
    it a different path argument than the Makefile passes.
    """
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    workflow_commands = "\n".join(strings_in(ci_workflow))

    # Run against the text it claims to catch and the text it claims to allow,
    # before its answer about the two files is believed (`docs/MISTAKES.md` entry
    # 3). The comment-stripping above is exactly the kind of change that blinds a
    # search silently, and the shape it would blind is the second sample.
    found = f"          python {ASSERTION_CHECKER} tests"
    commented = f"          # python {ASSERTION_CHECKER} tests"
    assert checker_invocations(found, ASSERTION_CHECKER), (
        f"This test's own search does not find {found!r}, which is the invocation it exists to "
        "look for. It has gone blind, and the assertion below would report the gate missing from "
        "a workflow that runs it."
    )
    assert not checker_invocations(commented, ASSERTION_CHECKER), (
        f"This test's own search counts {commented!r} as an invocation. A commented-out line "
        "ships without executing, so the gate would read as wired in while running nothing — "
        "which is the shape of failure this whole module is about."
    )

    missing = {
        where: sorted(
            checker
            for checker in (CHECKER, ASSERTION_CHECKER)
            if not checker_invocations(text_, checker)
        )
        for where, text_ in (
            ("Makefile", makefile),
            (".github/workflows/ci.yml", workflow_commands),
        )
    }
    missing = {where: absent for where, absent in missing.items() if absent}

    assert not missing, "\n".join(
        [
            f"The invariant gate is incomplete: {missing}.",
            "",
            "The §4.1 invariants are assertions about what a student can never see, and CLAUDE.md "
            "makes this the one gate that may never be skipped. It has two halves and they see "
            "different things:",
            f"  {CHECKER} reads the JUnit XML the run produced, so it catches a skip, an xfail "
            "and an empty collection.",
            f"  {ASSERTION_CHECKER} reads the test sources, so it catches the case the first one "
            "cannot see at all — a marked test that ran and asserted nothing, which counts "
            'toward the "N invariant test(s) ran, none skipped, none failed" the first one '
            "prints.",
            "",
            "Both run in both callers. `make ci` runs the same gates as the workflow (CLAUDE.md), "
            "and a half present in only one of them is a half that whoever runs the other never "
            "runs.",
        ]
    )
