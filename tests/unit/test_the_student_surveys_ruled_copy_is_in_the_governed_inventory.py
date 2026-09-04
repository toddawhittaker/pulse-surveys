"""The three strings the 2026-09-03 rulings add, in the file that governs copy — ticket FIX-01.

FIX-01's Constraints, in as many words: "Frontend strings go through
`frontend/src/copy/studentSurvey.ts` in that file's exact literal style (E2-11's
parser is strict); no comparative language (the FORBIDDEN_COMPARISONS sweep runs
over every string)." That constraint is not decoration. E2-11's inventory is what
SPEC §4.1 items 4 and 5 are checked over, and a sentence written straight into a
component is a shipped string those rules cannot see — the surface would read
correctly and the guard over it would be blind, which is
`docs/MISTAKES.md` entries 3 and 9 in one move.

So this module asserts the one thing an end-to-end spec cannot: that the ruled
wordings are *entries in the governed inventory*, not literals in a `.tsx`. A
screen rendering the right sentence from the wrong place passes every assertion
in `tests/e2e/student-survey-heading-and-next-window.spec.ts` and fails here.

**The texts are the owner's, transcribed from the ticket and its work order.**
Item 1 rules the eyebrow as `COURSE WK NN, TERM WK NN`, split across two entries
with the comma belonging to the first; item 4 rules the dated placeholder
"wording, shape exact". The two substitution holes in that sentence are `{time}`
and `{day}` — the work order settles them, because the zone abbreviation has to
come out of `Intl.DateTimeFormat` for the date in question rather than out of any
string written down. Nothing here is derived from the file it checks
(`docs/MISTAKES.md` entry 19).

**What this module deliberately does not assert.** Whether the entries are
*rendered*, and what they render to for a given week — that is the end-to-end
spec's, against a real browser and a real clock. And it does not require the two
keys item 1 replaces to be gone: an unused entry is untidy rather than wrong, and
demanding its removal would be pinning a mechanism the criteria do not name.
"""

from fixtures.copy_inventory import FRONTEND_COPY_DIRECTORY, collect_frontend_copy, display

# A key the survey surface certainly ships today, and has since E2-10. The canary
# on the parse: this module's whole claim is about strings the collector *did not*
# find, and a collector that found nothing at all — a moved directory, a parse
# that raised and was swallowed, a file renamed — would make that claim true of an
# empty reading (`docs/MISTAKES.md` entries 3 and 35). Item 5's own subject, so
# `tests/unit/test_the_shipped_copy_inventory_holds_to_items_four_and_five.py`
# already requires it to be there for a second reason.
A_KEY_THE_SURVEY_ALREADY_SHIPS = "student_survey.confidentiality"

# The three entries FIX-01 adds, keys and texts exact.
#
# The eyebrow is two entries because it renders as two spans and E2-10's
# `WeekEyebrow` keeps them apart; the comma is part of the first string rather
# than punctuation the component adds, so that the whole of what a reader sees is
# inside the governed inventory and the FORBIDDEN_COMPARISONS sweep reads it.
#
# `student_survey.section_closed_body` is deliberately absent from this table: it
# stays exactly as it is, for a section with no future window, and a test naming
# it here would be re-pinning E2-10's wording under FIX-01's name.
RULED_COPY = {
    "student_survey.course_week_eyebrow": "COURSE WK {week},",
    "student_survey.term_week_eyebrow": "TERM WK {week}",
    "student_survey.section_closed_body_dated": (
        "When the next survey for this course opens at {time} on {day}, it appears here."
    ),
}


def test_the_three_strings_the_2026_09_03_rulings_add_are_governed_copy() -> None:
    """FIX-01's Constraints: the ruled wordings live in the copy file, spelled exactly.

    **The mutations this kills.** Either eyebrow sentence assembled in
    `WeekEyebrow.tsx` out of a template literal and a week number — which renders
    identically and is invisible to every §4.1 sweep. The dated placeholder
    written inline in `StudentWeeklySurvey.tsx` beside the formatter that fills
    it, which is where it would most naturally go. And a key spelled some other
    way, which leaves the old entries in the inventory and the new sentence
    outside it.

    **The near miss it must survive**: the copy file carrying more than these
    three. Only the entries the ticket adds are named, and they are looked for
    among everything the collector published rather than compared against a whole
    expected file.

    **The canary, first.** A key the surface has shipped since E2-10 must be
    found, because a collector that read nothing would agree with this module
    about every string it did not see.
    """
    published = {
        string.key: string.text for string in collect_frontend_copy(FRONTEND_COPY_DIRECTORY)
    }
    assert A_KEY_THE_SURVEY_ALREADY_SHIPS in published, (
        f"The parse of {display(FRONTEND_COPY_DIRECTORY)} published no "
        f"`{A_KEY_THE_SURVEY_ALREADY_SHIPS}`; it published {sorted(published)}. That key has been "
        "on this surface since E2-10, so its absence means the collector is not reading the "
        "survey's copy at all — and every judgement below would be about an empty inventory."
    )

    missing = sorted(key for key in RULED_COPY if key not in published)
    assert not missing, (
        f"The governed copy inventory holds no {missing}. It holds {sorted(published)}.\n\n"
        "FIX-01's Constraints put every frontend string through "
        "`frontend/src/copy/studentSurvey.ts`, and SPEC §4.1 items 4 and 5 are checked over what "
        "E2-11 collects from there. A sentence rendered from a component is a shipped string the "
        "inventory cannot see: the page reads correctly and the sweep over it is silent."
    )

    wrong = {
        key: (published[key], text) for key, text in RULED_COPY.items() if published[key] != text
    }
    assert not wrong, (
        "These entries do not carry the wording the owner ruled on 2026-09-03 — `(published, "
        f"ruled)`: {wrong}.\n\n"
        "The eyebrow reads `COURSE WK NN, TERM WK NN` (acceptance criterion 1), split over two "
        "entries with the comma inside the first so that nothing a reader sees is assembled "
        "outside the inventory. The placeholder's shape is exact (item 4), and its two holes are "
        "`{time}` and `{day}` because the zone abbreviation is derived from the date by "
        "`Intl.DateTimeFormat` and is never written down anywhere — that derivation is the whole "
        "point of the ruling."
    )
