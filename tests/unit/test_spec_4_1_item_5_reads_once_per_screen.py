"""SPEC §4.1 item 5 says which surface it means — ticket E2-17 item 6.

E2-17's sixth criterion has two halves, and this module is the second: "at a
two-window clock the page renders the confidentiality sentence exactly once
(e2e), **and SPEC §4.1 item 5 says per screen**". The first half is
`tests/e2e/student-survey-confidentiality.spec.ts`.

**Why a test over a sentence in the spec.** §4.1 is the one list in this project
that says of itself "each of these is an automated assertion in the test suite,
not a convention", and item 5's parenthetical is the part of it that says *what
counts as one surface*. Until the ruling of 2026-09-03 it read "(survey: in the
submit bar)", which is a placement rather than a count, and the survey shipped
rendering the sentence once per section — twice on the screen of a student
enrolled in two courses whose windows are open at once. The e2e test next door
now fails against that reading; a spec line still stating it would leave the two
records disagreeing, with the browser test looking like the thing that was
wrong. `docs/MISTAKES.md` entry 1 is exactly this: a record going on asserting
something the change had made false.

**This branch owns that one line and no other.** §7.3's sentence about the same
item belongs to E2-16 and is deliberately untouched, which is why the assertion
below is scoped to §4.1's item 5 rather than run over the file.

**The canary comes first.** A search for a phrase inside a file is satisfied by a
search that has gone blind (`docs/MISTAKES.md` entry 3), so item 5's line is
located and required to be item 5 — by the words that have been in it since E0 —
before anything is asserted about the parenthetical.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "docs" / "SPEC.md"

# The heading item 5 lives under, and the opening of the item itself. Both have
# stood since E0 and neither is what this ticket changes, so they are what makes
# the search below a search for the right line.
INVARIANTS_HEADING = "### 4.1 Hard visibility invariants (testable)"
ITEM_FIVE_OPENING = "Confidentiality copy appears exactly once per surface"

# The parenthetical E2-17 settles, and the one it replaces. The first is the
# ruling of 2026-09-03 written out; the second is what shipped from E0 to E2-16.
SETTLED_PARENTHETICAL = "(survey: once per screen, in the submit area)"
SUPERSEDED_PARENTHETICAL = "(survey: in the submit bar)"


def item_five() -> str:
    """The one line of `docs/SPEC.md` that is §4.1's item 5.

    Found under §4.1's own heading rather than anywhere in the file, because
    other sections quote the same rule — §7.3's sentence is E2-16's and this
    ticket does not touch it — and a search over the whole document would be
    answered by whichever copy came first.
    """
    text = SPEC_PATH.read_text(encoding="utf-8")
    assert INVARIANTS_HEADING in text, (
        f"{SPEC_PATH} carries no `{INVARIANTS_HEADING}` heading, so this test cannot find the "
        "list item 5 sits in and every assertion below would be about the wrong part of the "
        "document — or about a document that has moved."
    )
    section = text.split(INVARIANTS_HEADING, 1)[1].split("\n## ", 1)[0]
    matching = [line for line in section.splitlines() if ITEM_FIVE_OPENING in line]
    if len(matching) != 1:
        pytest.fail(
            f"{len(matching)} lines under `{INVARIANTS_HEADING}` open with "
            f"{ITEM_FIVE_OPENING!r}: {matching}. Item 5 is one line of that list, and this test "
            "reads it by the words that have not changed since E0. Zero means the item has been "
            "reworded — in which case this test is the record that has to move with it — and two "
            "means the list has grown a duplicate."
        )
    return matching[0]


def test_item_five_counts_a_surface_as_a_screen() -> None:
    """Criterion 6, second half: item 5's parenthetical says per screen.

    **The mutation this kills**: the e2e count changed and the spec left saying
    "in the submit bar". The submit bar is per section, so the old parenthetical
    is a rule a compliant screen breaks — and the next person to read §4.1 would
    take the browser test for the defect.

    **Both directions.** The settled wording has to be there and the superseded
    wording has to be gone; asserting only the first passes against a line that
    carries both, which is the shape a careless edit takes.

    **The near miss it must survive**: §7.3's own sentence about the same rule is
    E2-16's and is deliberately not touched. `item_five` scopes the read to §4.1,
    so a change there — or the absence of one — is invisible here.
    """
    line = item_five()

    assert SETTLED_PARENTHETICAL in line, (
        f"SPEC §4.1 item 5 reads:\n\n  {line.strip()}\n\n"
        f"E2-17 item 6 sharpens its parenthetical to {SETTLED_PARENTHETICAL!r}. The ruling of "
        "2026-09-03 reads 'once per surface' as once per screen: the sentence was rendered by the "
        "per-section submit bar, so a student enrolled in two courses whose windows are open at "
        "the same minute met it twice on one screen, and "
        "`tests/e2e/student-survey-confidentiality.spec.ts` now refuses that. A spec still saying "
        "'in the submit bar' would leave the browser test looking like the thing that was wrong."
    )
    assert SUPERSEDED_PARENTHETICAL not in line, (
        f"SPEC §4.1 item 5 still carries {SUPERSEDED_PARENTHETICAL!r} as well as the wording that "
        f"replaced it:\n\n  {line.strip()}\n\n"
        "Two answers to the same question in the one list that calls itself testable."
    )
