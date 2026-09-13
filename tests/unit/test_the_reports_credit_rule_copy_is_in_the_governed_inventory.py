"""E4-12 criterion 4 — the credit-rule note is an entry, not a sentence in a component.

> 4. The credit-rule copy ships on the report surface, in the inventory,
>    answering what the validity rate means and that a posted score can move down
>    later — without inventing a score display.

The carried entry behind it is `docs/tickets/e4/carried-from-e3.md`'s "A lowered
participation score is not announced, and nothing explains the credit rule to
anybody". SPEC §3.3 says a comment classified as too brief or as nonsense makes
its response invalid, and that a later re-classification lowers a score that has
already posted; SPEC §3.4 says a participation score is completed items over total
items, with the per-week arithmetic visible only in the gradebook comment's
ledger. Nothing on any Pulse surface said either thing to an instructor.

**What this module asserts, and what it deliberately does not.** It asserts that
the note is a collected entry under the report's own prefix — which is the half
an end-to-end spec cannot see, because a screen rendering the right sentence out
of a literal in `InstructorMondayReport.tsx` reads identically and is governed by
nothing. It does not assert the wording. The sentence is the copy author's, it
will be refined, and a test holding a copy of it would redden on the next edit
while proving nothing about what an instructor reads (`docs/MISTAKES.md` entry
19).

**Nor does it assert that the note renders.** That is a frontend test's, against
the Participation region of the report page.

**What the rest of the suite then guarantees about this entry**, without anything
here restating it: the invariant-marked inventory rules sweep it for item 4's
vocabulary along with every other collected string, and the exactly-once rule
requires the report surface to carry one confidentiality line and no more — so a
credit note written in words the recogniser reads as an identity promise reddens
`test_each_line_carrying_surface_carries_exactly_one_confidentiality_line`
rather than passing quietly.
"""

from __future__ import annotations

from fixtures.copy_inventory import FRONTEND_COPY_DIRECTORY, collect_frontend_copy, display

# The key the work order settles, on the page module because the note renders in
# the page's Participation region rather than inside the trend, statistic or
# comment components.
CREDIT_NOTE_KEY = "instructor_report_page.participation_credit_note"

# A key the report certainly ships, and has since E4-11. The canary on the parse:
# this module's claim is about a key the collector did *not* find, and a collector
# that found nothing at all — a moved directory, a renamed file — makes that claim
# true of an empty reading (`docs/MISTAKES.md` entries 3 and 35).
A_KEY_THE_REPORT_ALREADY_SHIPS = "instructor_report_page.comments_note"


def test_the_credit_rule_note_is_a_collected_entry_on_the_report_surface() -> None:
    """Criterion 4's testable half: the note is in the inventory, under the report's prefix.

    **The mutations this kills.** The note written straight into
    `InstructorMondayReport.tsx` beside the rate bar, which is where it would most
    naturally go and which renders identically while no §4.1 rule can read it. The
    note added to a copy module that is still outside the walked copy directory,
    which is the state all four report modules were in before this ticket. And the
    entry spelled under some other prefix — a `report.` or a `participation.` —
    which lands it on a surface the governance map does not claim and reddens the
    inventory rather than joining it.

    **The near miss this must not become:** an assertion about the sentence. The
    wording is the copy author's and will be refined; what is pinned is that there
    is an entry, that it is not empty, and that it belongs to the report.
    """
    collected = {
        string.key: string.text for string in collect_frontend_copy(FRONTEND_COPY_DIRECTORY)
    }
    assert A_KEY_THE_REPORT_ALREADY_SHIPS in collected, (
        f"The parse of {display(FRONTEND_COPY_DIRECTORY)} published no "
        f"{A_KEY_THE_REPORT_ALREADY_SHIPS!r}, so it has not read the report's copy at all and the "
        "assertion below would be about an empty reading rather than about a missing note. It "
        f"published {sorted(collected)}."
    )

    assert CREDIT_NOTE_KEY in collected, (
        f"The inventory holds no {CREDIT_NOTE_KEY!r}.\n"
        "\n"
        "SPEC §3.3 and §3.4 are explained to an instructor nowhere: what the validity rate counts, "
        "that a comment judged too brief or nonsense costs its item, that a posted participation "
        "score is completed items over total items with the per-week arithmetic in the gradebook "
        "comment, and that a later re-classification can lower a score that has already posted. "
        "The note that says so belongs on the report surface and in the governed inventory, "
        "because a sentence written into the page component is one SPEC §4.1 items 4 and 5 cannot "
        "reach."
    )
    assert collected[CREDIT_NOTE_KEY].strip(), (
        f"{CREDIT_NOTE_KEY!r} is collected and empty. An empty entry satisfies every vocabulary "
        "rule in the inventory and tells an instructor nothing."
    )
