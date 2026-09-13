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

**The course-week half moved on 2026-09-07, and this file is where it moves**
(ticket E4-17). That ruling adds the section's own length to the eyebrow, on the
course-week half — `COURSE WK 04 / 12, TERM WK 07` — so the exact text this
module pinned for `student_survey.course_week_eyebrow` became false the moment
the copy file was correct. The old assertion was right for FIX-01 and is
superseded rather than wrong; the repair is here because the implementer may not
edit `tests/`, which is `docs/MISTAKES.md` entry 22's shape and the reason it is
taken in the tests-first commit rather than discovered in a red run.

Its replacement is a **pattern**, not a second exact string, and the difference
is deliberate: the ruling settles what a reader sees — `COURSE WK`, the number,
a spaced solidus, the total, the comma — and settles nothing about what the new
substitution hole is *called*. Pinning a name here would choose it for the
implementer. `student_survey.term_week_eyebrow` keeps its exact text, which is
the other half of the same criterion: the ruling "adds a total rather than
removing an axis", so the term-week label is unchanged and a total that arrived
on it instead would fail below.

**What this module deliberately does not assert.** Whether the entries are
*rendered*, and what they render to for a given week — that is the end-to-end
spec's, against a real browser and a real clock. And it does not require the two
keys item 1 replaces to be gone: an unused entry is untidy rather than wrong, and
demanding its removal would be pinning a mechanism the criteria do not name.
"""

import re

from fixtures.copy_inventory import FRONTEND_COPY_DIRECTORY, collect_frontend_copy, display

# A key the survey surface certainly ships today, and has since E2-10. The canary
# on the parse: this module's whole claim is about strings the collector *did not*
# find, and a collector that found nothing at all — a moved directory, a parse
# that raised and was swallowed, a file renamed — would make that claim true of an
# empty reading (`docs/MISTAKES.md` entries 3 and 35). Item 5's own subject, so
# `tests/unit/test_the_shipped_copy_inventory_holds_to_items_four_and_five.py`
# already requires it to be there for a second reason.
A_KEY_THE_SURVEY_ALREADY_SHIPS = "student_survey.confidentiality"

# The entries FIX-01 adds whose text is exact and has stayed exact.
#
# The eyebrow is two entries because it renders as two spans and E2-10's
# `WeekEyebrow` keeps them apart; the comma is part of the first string rather
# than punctuation the component adds, so that the whole of what a reader sees is
# inside the governed inventory and the FORBIDDEN_COMPARISONS sweep reads it.
#
# The course-week half is no longer in this table — E4-17 grew it, and its
# assertion is `COURSE_WEEK_EYEBROW` below. The term-week half stays here spelled
# exactly, and it is now doing two jobs: FIX-01's wording, and E4-17's "the
# term-week label unchanged". A total that arrived on this half instead of on the
# course-week one fails right here.
#
# `student_survey.section_closed_body` is deliberately absent from this table: it
# stays exactly as it is, for a section with no future window, and a test naming
# it here would be re-pinning E2-10's wording under FIX-01's name.
RULED_COPY = {
    "student_survey.term_week_eyebrow": "TERM WK {week}",
    "student_survey.section_closed_body_dated": (
        "When the next survey for this course opens at {time} on {day}, it appears here."
    ),
}

# The course-week half, as the owner's ruling of 2026-09-07 leaves it (E4-17):
# "the total attaches to the course-week half, giving `COURSE WK 04 / 12, TERM WK
# 07 · closes Sun 11:59 PM`".
#
# **A pattern rather than a second exact string**, because everything a reader
# sees is ruled and the new substitution hole's *name* is not: `{total}`,
# `{length}` and `{weeks}` all render identically, the ticket picks none of them,
# and a test demanding one would make the implementer's choice for them.
#
# What it pins is the ruling's, character for character: the words `COURSE WK`,
# the `{week}` hole spelled as it already ships, a solidus with one space either
# side, a second hole, and the comma this half has carried since FIX-01. What it
# leaves open is that hole's name, and nothing else.
COURSE_WEEK_EYEBROW_KEY = "student_survey.course_week_eyebrow"
COURSE_WEEK_EYEBROW = re.compile(r"^COURSE WK \{week\} / \{[A-Za-z_][A-Za-z0-9_]*\},$")
COURSE_WEEK_EYEBROW_SHAPE = "COURSE WK {week} / {<a hole named by the implementer>},"


def test_the_strings_the_2026_09_03_rulings_add_are_governed_copy() -> None:
    """FIX-01's Constraints: the ruled wordings live in the copy file, spelled exactly.

    Two of the three now; the course-week eyebrow moved to the test below when
    the ruling of 2026-09-07 grew it, and the name of this test moved with it
    rather than going on saying "three" (`docs/MISTAKES.md` entry 1).

    **The mutations this kills.** The term-week eyebrow sentence assembled in
    `WeekEyebrow.tsx` out of a template literal and a week number — which renders
    identically and is invisible to every §4.1 sweep. That same half grown a
    total of its own, which is where E4-17's addition does *not* go. The dated
    placeholder written inline in `StudentWeeklySurvey.tsx` beside the formatter
    that fills it, which is where it would most naturally go. And a key spelled
    some other way, which leaves the old entries in the inventory and the new
    sentence outside it.

    **The near miss it must survive**: the copy file carrying more than these
    entries. Only the ones the rulings add are named, and they are looked for
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
        "The eyebrow reads `COURSE WK NN / NN, TERM WK NN` (FIX-01 acceptance criterion 1, with "
        "the total E4-17's ruling of 2026-09-07 adds to the course-week half), split over two "
        "entries with the comma inside the first so that nothing a reader sees is assembled "
        "outside the inventory. The half asserted here is the term-week one, which that ruling "
        "leaves alone. The placeholder's shape is exact (item 4), and its two holes are "
        "`{time}` and `{day}` because the zone abbreviation is derived from the date by "
        "`Intl.DateTimeFormat` and is never written down anywhere — that derivation is the whole "
        "point of the ruling."
    )


def test_the_course_week_eyebrow_states_how_long_the_course_runs() -> None:
    """E4-17 criteria 3 and 6: the total is on the course-week half, inside the inventory.

    The owner's ruling of 2026-09-07 makes the eyebrow read `COURSE WK 04 / 12,
    TERM WK 07`. The number after the solidus is how many weeks the section runs
    for, and it arrives from the read answer — so the string that holds it is a
    governed entry with two holes in it, and the component fills both.

    **The mutations this kills.** The total appended in `WeekEyebrow.tsx` — a
    template literal around the copy entry, or a second `<span>` with `/ 12` in
    it — which renders the ruled sentence perfectly and puts half of what a
    reader sees outside the inventory SPEC §4.1 items 4 and 5 are checked over.
    The entry left at FIX-01's `COURSE WK {week},`, which is the state this test
    is first written red against. The solidus written without its spaces
    (`{week}/{total}`), or the comma dropped, or the total put in front of the
    week — each a different string a reader would notice and no containment check
    would.

    **The near miss it must survive**: the hole's name. `{total}`, `{length}` and
    `{weeks}` are all the same sentence to a reader, and the ticket names none of
    them, so the pattern accepts any identifier and pins everything around it.
    The other near miss is the one the test above owns — the total added to the
    term-week half instead, which fails there against an exact string.

    **The canary, first**, for the reason the test above gives: a collector that
    read nothing agrees with every claim made about what it did not find.
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
    assert COURSE_WEEK_EYEBROW_KEY in published, (
        f"The governed copy inventory holds no `{COURSE_WEEK_EYEBROW_KEY}`. It holds "
        f"{sorted(published)}. That key has carried the first half of the eyebrow since FIX-01, so "
        "its absence is not this ticket's change — it is the eyebrow leaving the inventory."
    )

    text = published[COURSE_WEEK_EYEBROW_KEY]
    assert COURSE_WEEK_EYEBROW.fullmatch(text), (
        f"`{COURSE_WEEK_EYEBROW_KEY}` reads {text!r}; the ruling of 2026-09-07 makes it "
        f"{COURSE_WEEK_EYEBROW_SHAPE!r}.\n\n"
        "The eyebrow renders `COURSE WK 04 / 12, TERM WK 07`: the total attaches to the "
        "course-week half, the term-week label is unchanged, and the whole of what a reader sees "
        "stays inside the governed inventory — a total the component appends around this entry is "
        "a shipped string SPEC §4.1's sweeps cannot see.\n\n"
        "The second hole may be called anything; everything else in the pattern is the ruling's, "
        "including the spaces around the solidus and the trailing comma."
    )
