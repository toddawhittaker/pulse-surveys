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

**What the sweep is looking for is the claim, and not the words.** The E4-era
sentences say that *no comparison set can exist yet* — the suppression reason "no
comparison set exists until E5 builds them", and E4's own "E4 computes no
comparison set". A sentence saying that *one particular* set does not exist is a
different statement and a legitimate one: E5-06 ships "There is no comparison set
here." as the copy a leadership reader sees when a set id names nothing. The
first version of this sweep matched the second along with the first, and the
repair was the pattern rather than the copy — see `PLACEHOLDER_CLAIM` for the two
shapes it now reads, and the sweep's own docstring for how to tell a hit of one
kind from a hit of the other.

**The canary** (`docs/MISTAKES.md` entry 3): the pattern is run against two whole
lines copied out of files in this repository that certainly carry the claim, one
per shape, and against two whole lines that must not match — ordinary prose about
comparison sets, and E5-06's shipped copy. A search that has gone blind — a
pattern that matches nothing anywhere — is then a failure here rather than a
clean sweep, and so is a pattern that has been widened back over the copy.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PAYLOAD_PATH = REPO_ROOT / "backend" / "app"

# **The claim, not every mention of an absent set.** The work order's own grep is
# `grep -rn "no comparison set" backend tests docs/adr`, and that is the right
# reading tool for a person and the wrong one for a standing gate: E5-06 ships
# the sentence "There is no comparison set here." as the copy a leadership reader
# sees when a set id names nothing, which is a statement about *one* set that does
# not exist and not the placeholder-era claim that *none can*. The two E4-era
# shapes this sweep is for both say the second thing:
#
#   - the suppression reason itself — "no comparison set exists", which criterion
#     5 quotes in as many words, and its longer form "no comparison set exists
#     until E5 builds them";
#   - E4's own statement about what it computes — "E4 computes no comparison set",
#     "E4 builds no comparison set".
#
# So the pattern is the reason's own words, or a verb of *making* in front of the
# noun. `is`/`are` are deliberately absent from that verb list, because "there is
# no comparison set here" is the sentence this gate must leave alone.
# Case-insensitive, because either shape starts a comment as often as it sits
# mid-line; `\s+` between the verb and the noun, because a comment wrap puts a
# newline where a space was.
PLACEHOLDER_CLAIM = re.compile(
    r"no comparison set exists|(?:computes|computed|builds|built)\s+no comparison set",
    re.IGNORECASE,
)

# Two lines that certainly carry the claim, one per shape, each copied whole —
# the line the sentence starts on included — out of a file in this repository:
# `docs/tickets/e5/E5-05-report-benchmark-lines.md` line 56, and
# `docs/tickets/e4/README.md` line 91. Retyping a sentence from where you think
# it begins is the thing these samples exist to disprove, and a pattern narrowed
# to one shape while the other still ships is exactly what a two-sample canary
# catches.
LINES_THAT_CARRY_THE_CLAIM = (
    '5. The E4-era "no comparison set exists" reason is gone from the live',
    "   E4 builds no comparison set — that is E5 — but the report payload carries",
)

# Whole lines the pattern must leave alone. The first is ordinary prose about
# comparison sets, from `docs/tickets/e5/README.md`'s decision 4. The second is
# E5-06's shipped copy, quoted from `backend/app/copy/leadership_sets.py` line 75
# in this ticket's fix round: a leadership reader who opens a set id that names
# nothing is told so, and that sentence is not the era claim. It is the sample
# this canary most needs, because it is the one a widened pattern eats — and a
# sweep that cannot be passed is one somebody deletes a line of copy for.
LINES_THE_SWEEP_MUST_ALLOW = (
    "   set can be created, edited and resolved but no report renders it — the",
    'SET_UNAVAILABLE = "There is no comparison set here."',
)


def test_the_sweeps_pattern_finds_the_claim_and_leaves_ordinary_prose_alone() -> None:
    """The canary, executed before the sweep it guards.

    A pattern searched against a tree is a guard, and a guard nobody has run
    against the text it claims to catch is a comment (`docs/MISTAKES.md` entries 3
    and 9). Both directions are driven, in both shapes: each E4-era claim is
    found, and each sentence that merely mentions an absent comparison set is
    left alone.

    **The second allowed sample is the one that earned this test its keep.** The
    pattern was `no comparison set` until E5-06 landed, and it matched that
    ticket's shipped 404 copy — a sentence telling a leadership reader that the
    set id they opened names nothing. Nothing was wrong with the copy; the
    pattern was reading "a set that does not exist" as "no set can exist". Both
    halves of this canary now carry two samples apiece, so narrowing the pattern
    to let the copy through cannot quietly let an E4 shape through with it.

    **The mutation this kills:** the pattern narrowed or mistyped so that the
    sweep below passes over a tree that still carries one of the era sentences —
    a green tick reporting that nothing was found because nothing could be.
    """
    for sample in LINES_THAT_CARRY_THE_CLAIM:
        assert PLACEHOLDER_CLAIM.search(sample), (
            f"The sweep's pattern {PLACEHOLDER_CLAIM.pattern!r} does not match a line that "
            f"certainly carries the claim: {sample!r}. Until it does, the sweep below reports a "
            "clean tree because it can see nothing at all."
        )
    for sample in LINES_THE_SWEEP_MUST_ALLOW:
        assert not PLACEHOLDER_CLAIM.search(sample), (
            f"The sweep's pattern matches a sentence that is not the placeholder-era claim: "
            f"{sample!r}. A sentence about one comparison set that does not exist — E5-06's copy "
            "for a set id that names nothing — is ordinary user-facing prose, and a sweep that "
            "cannot be passed is one somebody deletes a line of copy for."
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

    **What a red looks like:** a list of files and line numbers, and each is
    ordinarily a sentence to rewrite rather than a pattern to narrow. Once it was
    the other way round, and the case is worth carrying: E5-06 shipped "There is
    no comparison set here." as the copy for a set id that names nothing, the
    pattern was `no comparison set`, and the hit was the pattern's fault. The
    difference is what the sentence claims — that *one* set does not exist, which
    is a true thing a reader may be told, against the placeholder-era claim that
    *none can exist until E5 builds them*, which is what this sweep is for. Read
    the hit before deciding which of the two it is; the canary above holds a
    sample of each, so narrowing is a change with two tests over it rather than a
    quiet widening of what may ship.
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
