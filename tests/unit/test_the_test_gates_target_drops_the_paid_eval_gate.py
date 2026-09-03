"""E2-15 item 3 / criterion 3, structural half — `test-gates` no longer names `evals`.

`docs/tickets/e2/E2-15-student-surface-and-local-gate-repairs.md` scope item 3:

> `ci → test-gates → evals` runs `tests.evals.runner --enforce-floors` with no
> condition: red on a fresh clone (no key), roughly a hundred paid provider
> calls on a configured one ... Condition the Makefile the way CI is
> conditioned (or split the target out of `ci` with the README saying so) and
> correct both sentences.

The settled construction (this ticket's work order, "Settled decisions", item
3) is the split: `test-gates: test e2e` — `evals` dropped from that
prerequisite list — with the `evals` target itself left exactly as it is, one
command away, and two README sentences corrected to match. This module is the
structural half of criterion 3: the `test-gates` line's own prerequisite
list, and that `evals` is still a real target rather than deleted along with
its reference.

**What this module does not, and cannot, prove.** Criterion 3's behavioural
half — "`make ci` on a tree with no `AI_PROVIDER_API_KEY` completes green
without a live provider call" — is a claim about running `make`, not about
the text of the `Makefile`, and the work order assigns it to the verifier, by
execution (`make -n`'s expansion naming no `evals`), rather than to a standing
test. A test here that shelled out to `make ci` would need a live database,
broker and Docker daemon to reach the `build-gates` stage, which is not what
a unit test owns, and CLAUDE.md is explicit that a subagent worktree must
never run `make ci` for itself.

**Why prerequisites are parsed rather than matched with a substring.** A
substring check for `"evals"` would also match the `evals` target's own
header line and the `## ... AI evals` help comment on `test-gates`'s own
line, so the target's prerequisite list is isolated first and only that list
is compared.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE_PATH = REPO_ROOT / "Makefile"

TARGET = "test-gates"
EVALS_TARGET = "evals"

# E2-15's settled prerequisite list for `test-gates`, transcribed from the work
# order's "Settled decisions" item 3: "`test-gates: test e2e` (drop `evals`)".
# In order, because make prerequisites are order-sensitive for reporting
# purposes even though this repository's own convention
# (`tests/unit/test_ci_migration_and_test_gates.py`) does not otherwise rely
# on prerequisite order — comparing the list rather than the set still catches
# a duplicate or a third name slipped in beside the two.
EXPECTED_PREREQUISITES = ["test", "e2e"]

# The target's own header line, anchored at column zero so a recipe line
# (tab-indented) or the `## ...` help text on some other target's line cannot
# match. Multiline because the file is read whole.
TARGET_HEADER = re.compile(rf"^{re.escape(TARGET)}\s*:\s*(?P<prerequisites>[^\n]*)$", re.MULTILINE)

EVALS_HEADER = re.compile(rf"^{re.escape(EVALS_TARGET)}\s*:", re.MULTILINE)


def makefile_text() -> str:
    """The Makefile's own text, or a failure naming why nothing here means anything."""
    assert MAKEFILE_PATH.is_file(), (
        f"{MAKEFILE_PATH} does not exist. `test-gates` and `evals` are declared there, and "
        "CLAUDE.md's CI discipline rests on that file existing."
    )
    return MAKEFILE_PATH.read_text(encoding="utf-8")


def prerequisites_of(makefile: str, target: str) -> list[str]:
    """The whitespace-split prerequisite list a target's own header line declares.

    The trailing `## help text` — every target in this `Makefile` carries one,
    matching the `help` recipe's own `grep -hE '^[a-zA-Z_-]+:.*?## .*$'` — is
    stripped before splitting, by cutting the line at its first `#`: a `#`
    never appears inside a prerequisite name, so truncating there cannot lose
    a real one, and a target with no help comment is unaffected because it has
    no `#` to cut at.
    """
    match = TARGET_HEADER.search(makefile)
    if match is None:
        phony_pattern = re.compile(r"^\.PHONY:\s*(\S+)", re.MULTILINE)
        phony_targets = sorted(set(phony_pattern.findall(makefile)))
        pytest.fail(
            f"{MAKEFILE_PATH} declares no `{target}:` target at column zero. It declares these "
            f"phony targets: {phony_targets}."
        )
    line = match.group("prerequisites").split("#", 1)[0]
    return line.split()


def test_the_test_gates_targets_prerequisites_are_exactly_test_and_e2e() -> None:
    """Criterion 3, structural half: `test-gates` no longer names `evals` as a prerequisite.

    **The mutation this kills:** `test-gates: test e2e evals` — today's shipped
    line, per this ticket's own boundary-review finding — which runs the paid
    eval runner unconditionally on every `make ci`, red on a fresh clone with
    no key and roughly a hundred paid calls on a configured one.

    **The near miss this must survive:** `evals` moved to `ci`'s own
    prerequisite list instead of `test-gates`'s (`ci: fast test-gates
    build-gates supply-chain evals`), which would still make `make ci` spend
    unconditionally and satisfies nothing this test checks unless the target
    it is looking at is the right one — which is why the line is found by the
    target's own name rather than by a bare search for the word `evals`
    anywhere in the file.
    """
    prerequisites = prerequisites_of(makefile_text(), TARGET)
    assert prerequisites == EXPECTED_PREREQUISITES, (
        f"`{TARGET}`'s prerequisite list in {MAKEFILE_PATH} is {prerequisites!r}; E2-15's settled "
        f"construction is {EXPECTED_PREREQUISITES!r} — `evals` dropped, `test` and `e2e` "
        "unchanged.\n\n"
        "While `evals` is a prerequisite of `test-gates`, `make ci` (which depends on "
        "`test-gates`) runs `tests.evals.runner --enforce-floors` unconditionally: red on a "
        "fresh clone with no `AI_PROVIDER_API_KEY`, and roughly a hundred paid provider calls on "
        "a configured one — while CI itself conditions the live steps on AI-touching paths or "
        "manual dispatch."
    )


def test_the_evals_target_itself_still_exists() -> None:
    """Criterion 3's other half: the deliberate spend stays one command away.

    The work order's settled construction removes `evals` from `test-gates`'s
    prerequisite list and leaves the `evals` target itself untouched — `make
    evals` still runs the same paid gate, on purpose, when somebody asks for
    it by name.

    **The mutation this kills:** deleting the `evals` target along with the
    reference to it, which would also make the test above pass (there is
    nothing left named `evals` for `test-gates` to prerequisite) while
    removing the one deliberate local spend path entirely — the opposite of
    what E2-15's criterion 3 asks for ("the deliberate spend path is still one
    command away").
    """
    makefile = makefile_text()
    assert EVALS_HEADER.search(makefile), (
        f"{MAKEFILE_PATH} declares no `{EVALS_TARGET}:` target at column zero. E2-15's settled "
        f"construction drops `{EVALS_TARGET}` from `{TARGET}`'s prerequisites but leaves the "
        f"`{EVALS_TARGET}` target itself exactly as it is — the one deliberate local spend, one "
        "command away. A tree with no such target has lost that command entirely."
    )
