"""The course length is the API's alone — nothing in `frontend/src/` derives it — ticket E4-17.

E4-17's fourth criterion: "The count is the API's alone: no letter-to-length map,
no term calendar, and no arithmetic over the section code exists anywhere in
`frontend/src/`, asserted so the derivation this ticket rejects cannot arrive
later by accident."

**Why the criterion exists.** SPEC §2.2 puts a section's length in a per-term
start-letter map, which is admin-configured institution data. The section code is
already on the student's screen, so the total is two lines of TypeScript away:
take the first character, look it up. The ticket rejects that, and the deferred
entry it closes gives the reason — a client-side derivation is a second copy of
`start_letter_map`, "the shape `docs/MISTAKES.md` entry 19 is about, and one that
reads right in review because the arithmetic is simple". A guard is the only
thing that keeps a rejected option rejected after the ticket that rejected it has
merged.

**This sweep names a catalog, not a concept.** A guard that refused "a
letter-to-length map" would be a sentence, and the next reader would have to
decide what counts as one; entry 19's known miss is exactly that, a check that
names the idea and sees none of its instances. So the six refused shapes below
are written as the concrete things. **The start-letter map, both of its
columns**: the fourteen start letters SPEC §2.2's Fall 2026 seed uses paired with
one of the eight section lengths, and the same letters paired with one of the
term's own dates — §2.2's letter "encodes length + start date", so a letter-keyed
table of dates is that map with its other column showing. **The term's own
calendar**: an identifier naming its start, end, length or calendar, and two or
more of its dates on one line. **The section code taken apart**: an index or
slice out of a code, and the words `startLetter` and `start_letter` in any
casing. Every letter, length and date comes from `SEEDED_COHORTS` and
`FALL_2026_TERM_*` in `tests/fixtures/`, which the guarded tree cannot shrink: a
frontend change can delete a derivation but cannot delete the catalog that finds
it.

**Both directions, before either verdict** (`docs/MISTAKES.md` entries 3 and 35).
A search for something that is not there is satisfied perfectly by a search that
has gone blind, and a guard that only ever reports absence cannot say which
mechanisms it can see. So every shape carries sources that certainly have it and
sources that certainly do not, run through the same matcher the tree walk uses,
and the walk itself has to find two files this ticket names by name before its
silence counts.

**One pattern per shape, and that is structural rather than tidy.** A shape
holding two patterns is checked against controls that only prove the shape, so a
blind pattern hides behind its sibling exactly as a blind shape would hide behind
the union — the same defect one level in. `RefusedShape.pattern` is singular so
that the control test's "each shape found its own control" is, by construction,
"each pattern found its own control".

**Disclosed limits, stated rather than discovered.**

  - The numbered cohorts (`2` through `7`, SPEC §2.2's three-week sections) are
    deliberately *not* in the letter half of the first two shapes. A bare digit
    used as an object key is indistinguishable from a Likert bucket or a chart
    index, and a guard that reddened on `{ 3: 6 }` would fire on the rating
    fixtures E4-08 through E4-10 are building. They are reachable only by reading
    a section code's first character, which the last two shapes are about.
  - **A lone date literal is not refused, and that is the repair of a measured
    false positive.** The first version of this module refused any bare
    occurrence of one of the term's dates, and it reddened on two lines that hold
    no calendar at all: `submittedAt="2026-09-07"`, a prop value on
    `CommentCard.test.tsx`, and a prose date in a comment naming the day of the
    owner's ruling. A single date cannot derive a course length — the two things
    that can are a letter-keyed table and an index into a section code, and both
    are refused above. So the date half of the catalog is kept and bound to what
    makes it a calendar: a start letter beside it, or a second of the term's own
    dates on the same line. Both false positives are now `certainly_not`
    controls, so the tightening cannot silently go further.
  - Comments are read like code. A derivation written in prose is inert, so a
    hit inside a comment is a false positive — a loud one, in a named line, and
    cheaper than a parser that could be wrong about where a comment ends. The
    corollary is that prose about the *concept* must not trip a shape: "the start
    letter encodes the length" is a sentence this file's own neighbours write,
    and it is a control below.
  - This reads files. It cannot see a derivation assembled at runtime out of
    values that arrive from somewhere else, and nothing here claims otherwise.
"""

import re
from pathlib import Path
from typing import NamedTuple

from fixtures.survey_windows import FALL_2026_TERM_END, FALL_2026_TERM_START, SEEDED_COHORTS

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SOURCE = REPO_ROOT / "frontend" / "src"
SOURCE_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")

# Two files E4-17 names in its own text, required to be among what the walk read
# before any silence about the rest counts. A moved directory, a renamed suffix
# or an `rglob` that matched nothing would otherwise make this module's whole
# claim true of an empty reading (`docs/MISTAKES.md` entry 3).
FILES_THE_WALK_MUST_FIND = (
    "frontend/src/components/WeekEyebrow.tsx",
    "frontend/src/copy/studentSurvey.ts",
)

# ---------------------------------------------------------------------------
# The catalog. Every name in it comes from `tests/fixtures/survey_windows.py`,
# which transcribes `scripts/seed.py`'s `START_LETTER_MAP` — the institution's
# configuration SPEC §2.2 makes a section's length come from. Nothing here is
# read out of `frontend/src/`, which is the tree this file judges.
# ---------------------------------------------------------------------------

START_LETTERS = tuple(sorted(letter for letter in SEEDED_COHORTS if letter.isalpha()))

# §2.2's course lengths: "3, 6, 8, 10, 12, 15, 16 (plus an 18-week dissertation
# length)". The first seven are read from the seed's own map; 18 is written in
# because the Fall 2026 seed has no dissertation cohort and a catalog missing a
# length is a catalog with a hole in it. It is also the term's own length, which
# is the near miss criterion 5 names on the wire.
DISSERTATION_LENGTH = 18
SEEDED_LENGTHS = {length for length, _first_week, _start in SEEDED_COHORTS.values()}
SECTION_LENGTHS = tuple(sorted(SEEDED_LENGTHS | {DISSERTATION_LENGTH}))

# The term's own calendar: its first and last day, and every cohort start date
# the map holds. A bare one of these in a `.ts` file is the term calendar
# arriving in the browser; the same date inside an instant (`...T18:00:00Z`) is a
# window's opening or closing time, which the read answer legitimately carries.
SEEDED_STARTS = {start.isoformat() for _length, _first_week, start in SEEDED_COHORTS.values()}
TERM_DATES = tuple(
    sorted(SEEDED_STARTS | {FALL_2026_TERM_START.isoformat(), FALL_2026_TERM_END.isoformat()})
)


def alternation(values: tuple[object, ...]) -> str:
    """The catalog as a regular-expression alternation, longest first.

    Longest first so that `16` is preferred over `1`, and no date is matched as
    the prefix of a longer one.
    """
    return "|".join(re.escape(str(value)) for value in sorted(values, key=lambda v: -len(str(v))))


class RefusedShape(NamedTuple):
    """One derivation this ticket refuses, its one pattern, and its two controls.

    `certainly` and `certainly_not` are sources written here rather than quoted
    from `frontend/src/`: a control copied out of the tree being swept goes blind
    with it.

    **One pattern, not a tuple of them**, for the reason the module docstring
    gives: the control test proves a *shape* against its own sources, so a shape
    holding two patterns could carry a blind one indefinitely. A new mechanism is
    a new entry in `REFUSED`, with the two controls that entry owes.
    """

    name: str
    why: str
    pattern: re.Pattern[str]
    certainly: tuple[str, ...]
    certainly_not: tuple[str, ...]


LETTER = rf"""['"`]?\b(?:{alternation(START_LETTERS)})\b['"`]?\s*(?::|,|=>|=)\s*"""
DATE = rf"(?<!\d)(?:{alternation(TERM_DATES)})(?![\dT])"

REFUSED = (
    RefusedShape(
        name="a start letter mapped to a section length",
        why=(
            "SPEC §2.2's start-letter map is admin-configured institution data. A copy of it in "
            "TypeScript is a second source of truth for how long a section runs, and it drifts "
            "the first time a term configures its letters differently"
        ),
        pattern=re.compile(rf"{LETTER}(?:return\s+)?(?:{alternation(SECTION_LENGTHS)})\b"),
        certainly=(
            "const lengthOf = { U: 12, R: 12, E: 6 };",
            "const lengths = new Map([['Q', 12], ['H', 6]]);",
            "switch (letter) { case 'K': return 16; }",
        ),
        certainly_not=(
            "const distribution = { 1: 3, 2: 6, 3: 8, 4: 10, 5: 12 };",
            "const labels = { A: 'excellent', B: 'good' };",
            "const courseWeek = 12;",
        ),
    ),
    RefusedShape(
        name="a start letter mapped to one of the term's own dates",
        why=(
            "the other column of the same map. §2.2's start letter encodes length *and* start "
            "date, so a letter-keyed table of dates is the institution's calendar in the browser "
            "under a different heading, and a length is one subtraction away from it"
        ),
        pattern=re.compile(rf"""{LETTER}['"`]?{DATE}"""),
        certainly=(
            "const startsOn = { U: '2026-08-17', R: '2026-09-07' };",
            "const firstDay = new Map([['Q', '2026-09-28']]);",
        ),
        certainly_not=(
            '<CommentCard submittedAt="2026-09-07" />',
            "const closesAt = '2026-08-17T18:00:00Z';",
        ),
    ),
    RefusedShape(
        name="an identifier naming the term's own calendar",
        why=(
            "the term's dates and length are institution configuration too, and a screen holding "
            "them can compute a week axis the server never sent — the same second copy, one table "
            "over"
        ),
        pattern=re.compile(
            r"\b(?:TERM_(?:START|END|WEEKS|LENGTH|CALENDAR)"
            r"|term(?:Start|End|Weeks|Length|Calendar))\b"
        ),
        certainly=(
            "const TERM_START = '2026-08-17';",
            "const termWeeks = 18;",
            "export const termCalendar = buildCalendar();",
        ),
        certainly_not=(
            "const termWeek = 4;",
            "const opensAt = new Date(nextWindowOpensAt);",
        ),
    ),
    RefusedShape(
        name="two or more of the term's own dates on one line",
        why=(
            "one of the term's dates is a datum — a prop, a fixture, a date in a sentence — and "
            "two of them side by side is a table of them; the discriminator is what keeps a "
            "comment-card prop and a prose date out of a guard about the institution's calendar"
        ),
        pattern=re.compile(rf"{DATE}[^\n]*?{DATE}"),
        certainly=(
            "const weekStarts = ['2026-08-17', '2026-09-07', '2026-09-28'];",
            "const bounds = { first: '2026-08-17', last: '2026-12-20' };",
        ),
        certainly_not=(
            '<CommentCard submittedAt="2026-09-07" />',
            "// the owner's ruling of 2026-09-07 settled where the total sits",
            "const held = { opensAt: '2026-09-07T18:00:00Z', closesAt: '2026-09-13T23:59:59Z' };",
        ),
    ),
    RefusedShape(
        name="the words `start letter` run together, in any casing",
        why=(
            "a name for the thing being read out of the code. Nothing on this surface has any "
            "business holding one: the letter is the server's to resolve, and a variable named "
            "for it is a derivation that has already started"
        ),
        # No closing `\b`, deliberately: `START_LETTER_MAP` — the name the
        # deferred entry warns about by name — continues into another word
        # character, and a trailing boundary would walk straight past it. The
        # opening boundary is kept, so a word merely ending in these letters is
        # not caught.
        pattern=re.compile(r"(?i)\bstart_?letter"),
        certainly=(
            "const startLetter = code.charAt(0);",
            "const START_LETTER_MAP = { U: 12 };",
            "const startLetters = Object.keys(lengths);",
        ),
        certainly_not=(
            "// the start letter encodes the length, and the server resolves it",
            "const letter = 'U';",
        ),
    ),
    RefusedShape(
        name="an index or slice taken out of a section code",
        why=(
            "the start letter is the first character of a code the student is already shown, so "
            "the derivation this ticket rejects is one index away; the count comes from the read "
            "answer or it does not come at all"
        ),
        pattern=re.compile(
            r"(?i)\b\w*section_?code\w*\s*"
            r"(?:\[\s*0\s*\]|\.charAt\(|\.slice\(|\.substring\(|\.at\(|\.codePointAt\()"
        ),
        certainly=(
            "const letter = section.lms_section_code.charAt(0);",
            "const first = sectionCode.slice(0, 1);",
            "const head = sectionCode[0];",
        ),
        certainly_not=(
            "const code = section.lms_section_code;",
            "const opening = title.slice(0, 3);",
            "const label = `${courseLabel} ${sectionCode}`;",
        ),
    ),
)


def hits_for(shape: RefusedShape, text: str, where: str) -> list[str]:
    """Every line of `text` that trips one shape, named by line and by what matched."""
    found: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = shape.pattern.search(line)
        if match is not None:
            found.append(f"{where}:{number}: {shape.name} — matched {match.group(0)!r}")
    return found


def refusals_in(text: str, where: str) -> list[str]:
    """Every refused shape this text trips, over all six.

    One function for the tree walk and for the negative controls, so a green over
    the tree comes from the same matcher the controls exercised
    (`docs/MISTAKES.md` entry 35). The positive controls go through `hits_for`
    instead, per shape: over the union, one shape catching another's control
    would let a blind pattern pass.
    """
    return [line for shape in REFUSED for line in hits_for(shape, text, where)]


def frontend_sources() -> list[Path]:
    """Every TypeScript source under `frontend/src/`, tests and fixtures included.

    Included rather than excluded: a component test or a fixture beside one is
    still a place a letter-to-length map can be written down, and the day one
    lands there is the day the next component reads it.
    """
    return sorted(
        path
        for path in FRONTEND_SOURCE.rglob("*")
        if path.is_file() and path.suffix in SOURCE_SUFFIXES
    )


def test_no_frontend_source_maps_a_start_letter_or_slices_a_section_code() -> None:
    """Criterion 4: the week count is the API's alone, everywhere under `frontend/src/`.

    **The mutations this kills**, each of which renders a correct eyebrow and
    passes every other test in this ticket: a start-letter map in TypeScript,
    keyed to lengths or to the term's dates, filled from the section code the
    screen already has, so the payload's count could be dropped and nothing would
    notice; a term calendar in the client, named or written out as a table of
    dates, which computes the same total a week later by another route; and
    `sectionCode[0]` anywhere, which is the whole derivation in one expression.

    **The near misses it must survive**, all of them controls beside this test:
    the code and the two week numbers are legitimately on this screen
    (`const code = section.lms_section_code`); an instant that falls on a term
    start date is a window's opening time (`'2026-08-17T18:00:00Z'`); and **one
    of the term's dates, on its own, is not a calendar** — `submittedAt=
    "2026-09-07"` on a comment card and a prose date in a comment are the two
    measured false positives this sweep was tightened against.

    **The canary, first.** The walk has to have read the two files E4-17 names by
    name. A sweep over an empty file list is silent about everything, and its
    silence is what this test would otherwise report as compliance.
    """
    read = frontend_sources()
    relative = {str(path.relative_to(REPO_ROOT)) for path in read}
    missing = sorted(name for name in FILES_THE_WALK_MUST_FIND if name not in relative)
    assert not missing, (
        f"The walk over {FRONTEND_SOURCE} did not read {missing}; it read {len(read)} files. Both "
        "are named in E4-17's own text as files this ticket changes, so their absence means this "
        "sweep is reading somewhere else — and a judgement made over nothing is silent about "
        "everything."
    )

    findings: list[str] = []
    for path in read:
        where = str(path.relative_to(REPO_ROOT))
        findings.extend(refusals_in(path.read_text(encoding="utf-8"), where))
    assert not findings, (
        "These lines under `frontend/src/` derive how long a section runs, or hold the data to:\n\n"
        + "\n".join(findings)
        + "\n\n"
        + "\n".join(f"- {shape.name}: {shape.why}." for shape in REFUSED)
        + "\n\nE4-17 puts the count on the read answer precisely so none of this exists. If a line "
        "above is a coincidence rather than a derivation — a comment, or a constant that means "
        "something else — the answer is to say so in the change that adds it, in this file, beside "
        "the shape it trips. Loosening a pattern to make a red go away gives back the guarantee "
        "the criterion asks for."
    )


def test_each_refused_shape_finds_a_source_that_certainly_carries_it() -> None:
    """The instrument, both ways: every shape is proven visible before its silence counts.

    `docs/MISTAKES.md` entry 35's rule, in as many words: "When a guard enumerates
    mechanisms, require it to *find* each one on a subject that certainly has it,
    as a control. A guard that only ever reports absence cannot tell you which
    mechanisms it can see."

    **The mutations this kills.** A pattern that compiles and matches nothing —
    an escaped character class, a catalog that came back empty, an alternation
    built from a map that no longer holds letters. And the opposite: a pattern
    broad enough to fire on the section code the screen legitimately renders, on
    a window instant that happens to fall on a term start date, or on a single
    date used as a prop or written in a sentence — each of which makes the sweep
    above red against correct code and gets it loosened until it sees nothing.

    **The last of those is measured rather than imagined**, which is why its two
    sources are quoted from the incident: the first version of this module
    refused any bare occurrence of a term date and reddened on
    `CommentCard.test.tsx`'s `submittedAt` prop and on a comment naming the date
    of the owner's ruling. The repair bound the date half of the catalog to a
    start letter or to a second date, and put both false positives here — so the
    tightening is held in place by a test rather than by a memory of it.

    Asserts nothing about what ships, so it carries no `invariant` marker: a red
    here means this module is broken, not that the frontend derives anything.
    """
    blind = {
        shape.name: [source for source in shape.certainly if not hits_for(shape, source, "control")]
        for shape in REFUSED
    }
    unseen = {name: sources for name, sources in blind.items() if sources}
    assert not unseen, (
        f"These refused shapes did not find sources that certainly carry them: {unseen}.\n\n"
        "Each of those lines is the derivation this ticket rejects, written out. A shape that "
        "cannot see its own control sees nothing in `frontend/src/` either, and the sweep beside "
        "this test would report a clean tree whatever the tree held.\n\n"
        f"The catalog it is built from: start letters {list(START_LETTERS)}, lengths "
        f"{list(SECTION_LENGTHS)}, term dates {list(TERM_DATES)}. An empty one is the first thing "
        "to check."
    )

    firing = {
        source: refusals_in(source, "control")
        for shape in REFUSED
        for source in shape.certainly_not
        if refusals_in(source, "control")
    }
    assert not firing, (
        f"These sources carry no derivation and were refused anyway: {firing}.\n\n"
        "Every one of them is something the survey screen legitimately does — render the section "
        "code it was given, format the instant a window opens, print the term week the read answer "
        "carries. A sweep that refuses them is red against correct code, and the next person to "
        "meet it will widen it until it is silent, which is how the guarantee is lost."
    )
