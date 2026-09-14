"""E5-05 criterion 5 — nothing in the live payload path still says a comparison set does not exist.

> The E4-era "no comparison set exists" reason is gone from the live payload
> path, and the schema no longer admits it — a record sweep catches any prose
> still asserting the placeholder era (MISTAKES entry 1).

E4 shipped the `comparison` member with the chokepoint standing over nothing, and
said so in its own code: the suppression was explained as "no comparison set
exists until E5 builds them". Once E5-05 lands, that sentence is false wherever a
reader meets it, and a reader meeting it beside the assembly code will conclude
that a suppressed figure means "E5 has not run" rather than "below the configured
minimum". That is `docs/MISTAKES.md` entry 1 exactly — a record going on
asserting something the change had made false — and this is the sweep the work
order makes the last content commit of the ticket.

**Scope, and what is deliberately outside it.** The claim in criterion 5 is about
the *live payload path*, so the sweep reads `backend/app/` and nothing else. Two
exclusions are named rather than left to be discovered:

  - **`docs/adr/`.** ADR 0155 records what E4 built and why, in the past tense;
    an architecture decision record is history, and rewriting it to match today
    would destroy the thing it is for. If a reader of 0155 needs to know that E5
    has since filled the member, the repair is a pointer line in that ADR, not a
    deleted sentence, and it is not something a test can assert.
  - **`tests/`.** E4-07's own item-7 module carries the sentence in its docstring
    and in two failure messages, and this ticket's criterion 6 requires that
    module to pass **untouched** — so the ticket cannot both sweep it and leave it
    alone. E5-05's work order limits the sweep to "any test docstring under
    `tests/` that this ticket touches", which is a rule for the author rather than
    an assertion, and E4-07's module is not one of them.

**The canary** (`docs/MISTAKES.md` entry 3): the pattern is run against a line
copied whole out of a file in this repository that certainly carries the claim,
and against a whole line of ordinary prose about comparison sets that it must not
match. A search that has gone blind — a pattern that matches nothing anywhere —
is then a failure here rather than a clean sweep.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PAYLOAD_PATH = REPO_ROOT / "backend" / "app"

# The claim, as the work order's own grep spells it: `grep -rn "no comparison
# set" backend tests docs/adr`. Case-insensitive, because the sentence starts a
# comment as often as it sits mid-line.
PLACEHOLDER_CLAIM = re.compile(r"no comparison set", re.IGNORECASE)

# A line that certainly carries the claim, copied whole — the line the sentence
# starts on included — out of `docs/tickets/e5/E5-05-report-benchmark-lines.md`.
# Retyping a sentence from where you think it begins is the thing this sample
# exists to disprove.
A_LINE_THAT_CARRIES_THE_CLAIM = (
    '5. The E4-era "no comparison set exists" reason is gone from the live'
)

# A whole line of ordinary prose about comparison sets, from
# `docs/tickets/e5/README.md`'s decision 4, which the pattern must leave alone. A
# sweep that matched every mention of a comparison set would be unpassable, and a
# reviewer would widen the exclusion list rather than the prose.
A_LINE_THE_SWEEP_MUST_ALLOW = (
    "   set can be created, edited and resolved but no report renders it — the"
)


def test_the_sweeps_pattern_finds_the_claim_and_leaves_ordinary_prose_alone() -> None:
    """The canary, executed before the sweep it guards.

    A pattern searched against a tree is a guard, and a guard nobody has run
    against the text it claims to catch is a comment (`docs/MISTAKES.md` entries 3
    and 9). Both directions are driven: the claim is found, and prose about a
    comparison set that is not the claim is not.

    **The mutation this kills:** the pattern narrowed or mistyped so that the
    sweep below passes over a tree that still carries the sentence — a green tick
    reporting that nothing was found because nothing could be.
    """
    assert PLACEHOLDER_CLAIM.search(A_LINE_THAT_CARRIES_THE_CLAIM), (
        f"The sweep's pattern {PLACEHOLDER_CLAIM.pattern!r} does not match a line that certainly "
        f"carries the claim: {A_LINE_THAT_CARRIES_THE_CLAIM!r}. Until it does, the sweep below "
        "reports a clean tree because it can see nothing at all."
    )
    assert not PLACEHOLDER_CLAIM.search(A_LINE_THE_SWEEP_MUST_ALLOW), (
        f"The sweep's pattern matches ordinary prose about a comparison set: "
        f"{A_LINE_THE_SWEEP_MUST_ALLOW!r}. A sweep that cannot be passed is one somebody will "
        "exclude a directory from."
    )


def test_no_module_in_the_payload_path_still_says_a_comparison_set_does_not_exist() -> None:
    """The sweep itself, over `backend/app/`.

    Every occurrence is a sentence a reader of the assembly code meets while
    working out what a suppressed member means. The reason the chokepoint gives is
    now one thing — below a configured minimum — and the prose beside it has to
    say the same thing, or the next person to touch this code will reintroduce the
    placeholder case to match the comment.

    **The mutation this kills:** the placeholder retired in the code and its
    explanation left in place, which is the state that made `docs/MISTAKES.md`
    entry 1 the second-most-caught entry in this repository.

    **What a red looks like:** a list of files and line numbers. Each is a
    sentence to rewrite, not a pattern to narrow.
    """
    assert PAYLOAD_PATH.is_dir(), f"{PAYLOAD_PATH} is not a directory, so this test read nothing."

    found: list[str] = []
    read = 0
    for path in sorted(PAYLOAD_PATH.rglob("*.py")):
        read += 1
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if PLACEHOLDER_CLAIM.search(line):
                found.append(f"{path.relative_to(REPO_ROOT)}:{number}: {line.strip()}")

    assert read > 0, (
        f"This sweep read no Python files under {PAYLOAD_PATH.relative_to(REPO_ROOT)}, so its green "
        "means nothing."
    )
    assert not found, "\n".join(
        [
            "These lines under the live payload path still assert the placeholder era:",
            *found,
            "",
            "E5-05 criterion 5: the E4-era 'no comparison set exists' reason is gone from the live "
            "payload path. A comparison set now exists for every section whose Lead Faculty leads "
            "matching courses, and the one reason the chokepoint gives is that the population is "
            "below a configured minimum. Prose that still explains the suppression the other way "
            "sends the next reader looking for a case that no longer exists.",
        ]
    )
