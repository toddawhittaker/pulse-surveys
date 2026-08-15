"""Section codes: what one says, and the calendar it derives against a term.

SPEC §2.2. A section code is `{startLetter}{ordinal}{modality}` — `R3WW`,
`Q2FF` — and it is the only thing a section's calendar comes from: the start
position is looked up in its **term's** start-letter map (E0-06's
`start_letter_map`) for a length in weeks and a start date, the end date follows
from those two, and the suffix says whether the section is online or
face-to-face. Nothing about a section's dates is hand-entered (SPEC §8:
"LMS-owned data is never hand-edited in Pulse").

**The start position is not always a letter.** §2.2 numbers the 3-week sections
2 through 7 while every other length is lettered, so the first character of a
code is a *start position* — one character, a letter or a digit — and what makes
one legal is a row in the term's map, never the character's class or a numeric
range. The parts are still named "start letter" after the ticket and the spec.

**Every length and date comes from the term's map row and none from this
module.** The map is per-term admin configuration (§2.2, §6.3): next fall's `Q`
is a different date, and an admin editing the calendar (E11) changes what a code
means without changing any code. A letter table written into this module would
agree with Fall 2026 and be silently wrong for every term after it.

**Parsing is total.** Section codes arrive from an LMS roster feed, so every
input either parses or raises a `SectionCodeError` naming the part that was
wrong. Nothing here lets a builtin out: a `KeyError` off a suffix lookup or a
`ValueError` out of `int()` is not something a caller can catch on purpose, and
it reaches an operator as a 500 rather than as "this section code could not be
read". The grammar is one regular expression with no repetition of a repetition,
so it cannot backtrack catastrophically on a crafted code.

**The end date is the section's last day, inclusive**: `start_date + 7 *
length_weeks - 1`. §2.2's own seed map is what settles it — Fall 2026 runs 18
weeks from Monday 8/17 and seeds `Q` as a 12-week letter starting 9/28, so
inclusive both the term and `Q` end Sunday 12/20 and `Q` fits exactly. Exclusive,
`Q` would end 12/21, one day outside its own term, and the rejection below would
make a letter the spec seeds by name unusable in the term it is seeded for.
Monday start to Sunday end also agrees with §3.1, which closes a week's survey
window on Sunday: a section's last window closes on its last day.

**A section that would run past its term is refused here rather than in the
schema.** The comparison is against `term.end_date`, and a `CHECK` constraint
cannot read another table. It could be made local by carrying a copy of the
term's dates on `section` under a composite foreign key — the shape ADR 0018
uses for the two length rules — but that copy exists to make a *stored*
configuration value checkable, and a section's dates are derived on one path
that already holds the term. This service is that path.

**Where the four values land.** `apply_section_code` below is the only thing
that writes `section.length_weeks`, `start_date`, `end_date` and `modality`
(SPEC §8), so a section's calendar can never disagree with its code.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.org import Modality, Section
from app.models.term import StartLetterMap, Term, TermRow

# §2.2's grammar, and the whole of what is structural about a code: one start
# position, an ordinal, a modality suffix. The three groups are deliberately
# permissive about *content* — an ordinal that is absent and a suffix that is
# not one of the two both match here — so that each can be refused separately,
# by name, below. A single strict pattern would refuse `RWW` and `R3ZZ`
# identically, and criterion 3 asks for an error naming the offending part.
#
# The start position is one character (`[A-Z0-9]`, not `[A-Z0-9]+`), which is
# what makes `23WW` start position 2, ordinal 3 rather than ordinal 23 with no
# start position. Digits are greedy after that, so a two-digit ordinal reads as
# one number rather than as a start position that swallowed a digit.
#
# No group repeats a group, so there is nothing here to backtrack over: matching
# is linear in the length of the code however the code is crafted.
_STRUCTURE = re.compile(r"(?P<start>[A-Z0-9])(?P<ordinal>[0-9]*)(?P<modality>[A-Z]*)")

# §2.2: "Modality: `WW` online, `FF` face-to-face." A closed set of exactly two,
# and an unknown suffix is an error rather than a silent default — a section
# whose modality was guessed is compared against the wrong population in §5.1
# and nothing reports that it was.
_MODALITY_SUFFIXES: dict[str, Modality] = {
    "WW": Modality.ONLINE,
    "FF": Modality.FACE_TO_FACE,
}

_DAYS_PER_WEEK = 7


class SectionCodeError(Exception):
    """A section code, or something derived from one, that this service refuses.

    Every refusal below is one of these, so the roster sync (E1) has a single
    thing to catch and turn into "this section could not be read" rather than a
    500. The subclasses exist so a caller can tell the failures apart without
    reading English — criterion 3's word "distinct" — and each message names the
    part of the code that was wrong, because the person reading it is an
    operator looking at a roster feed and "invalid section code" sends them to
    work out which of three parts it was.
    """


class MalformedSectionCodeError(SectionCodeError):
    """The code is not `{startLetter}{ordinal}{modality}` under any reading."""


class MissingOrdinalError(SectionCodeError):
    """The code has a start position and a suffix but no ordinal between them.

    Not defaulted to 1, which is the tempting repair: every `RWW` in a feed
    would become section 1 of its course and either collide with the real `R1WW`
    under E0-06's uniqueness rule or, worse, run alongside it as a second
    section 1.
    """


class UnknownModalityError(SectionCodeError):
    """The suffix is not one of §2.2's two."""


class UnknownStartPositionError(SectionCodeError):
    """The term's start-letter map has no row for this code's start position.

    A question about one term's configuration, never about the alphabet: `A` is
    a perfectly good start letter in a term whose admin configured it, and `3`
    is one in every term §2.2's seed map describes.
    """


class SectionOutsideItsTermError(SectionCodeError):
    """The map row resolves to a section that starts or ends outside its term."""


class CourseWeekOutsideItsSectionError(SectionCodeError):
    """A course week that the section does not have (§2.2's two week axes)."""


class UnknownTermError(SectionCodeError):
    """A section names a term that is not in the session."""


@dataclass(frozen=True, slots=True)
class ParsedSectionCode:
    """`R3WW` split into the three parts §2.2 gives a section code.

    `start_letter` is one character and may be a digit — see the module
    docstring. It carries the spec's name rather than "start position" because
    that is what §2.2 and the ticket call it.

    Frozen because a parsed code is a reading of a string, not a thing to edit:
    a caller that wants a different code parses a different code.
    """

    start_letter: str
    ordinal: int
    modality: Modality


@dataclass(frozen=True, slots=True)
class SectionCalendar:
    """The four values a section's code and its term derive to (SPEC §8).

    Named for the columns they land in on `section`, so that the derivation and
    the schema cannot drift into two vocabularies for one thing.
    """

    length_weeks: int
    start_date: date
    end_date: date
    modality: Modality


def parse_section_code(code: str) -> ParsedSectionCode:
    """Read `code` as `{startLetter}{ordinal}{modality}`, or refuse it by name.

    The grammar only. Whether the start position means anything is a question
    about a term's start-letter map, and it is asked by
    `derive_section_calendar` below, which has one.
    """
    match = _STRUCTURE.fullmatch(code)
    if match is None:
        raise MalformedSectionCodeError(
            f"Section code {code!r} is not of the form {{startLetter}}{{ordinal}}{{modality}} "
            "(SPEC §2.2): one start position, an ordinal, and a two-character modality suffix, "
            "such as 'R3WW'."
        )

    ordinal = match["ordinal"]
    if not ordinal:
        raise MissingOrdinalError(
            f"Section code {code!r} carries no ordinal between its start position "
            f"{match['start']!r} and its modality {match['modality']!r}. The ordinal is what "
            "tells one section of a course in a term from the next (SPEC §2.2)."
        )

    modality = _MODALITY_SUFFIXES.get(match["modality"])
    if modality is None:
        raise UnknownModalityError(
            f"Section code {code!r} ends in {match['modality']!r}, which is not a modality this "
            f"institution uses. SPEC §2.2 has exactly two: "
            f"{sorted(_MODALITY_SUFFIXES)} for online and face-to-face."
        )

    return ParsedSectionCode(start_letter=match["start"], ordinal=int(ordinal), modality=modality)


def derive_section_calendar(session: Session, code: str, term: TermRow) -> SectionCalendar:
    """Derive one section's length, dates and modality from its code and its term.

    The start position is looked up in *this* term's map. Both halves of that
    matter: a lookup by the letter alone finds whichever term's row it finds
    first, and the answer — a plausible Monday inside some term — is wrong in a
    way nothing downstream questions.
    """
    parsed = parse_section_code(code)
    term_id, term_start, term_end = _term_dates(term)

    row = session.scalars(
        select(StartLetterMap).where(
            StartLetterMap.term_id == term_id,
            StartLetterMap.letter == parsed.start_letter,
        )
    ).one_or_none()
    if row is None:
        raise UnknownStartPositionError(
            f"Section code {code!r} has the start letter {parsed.start_letter!r}, which this "
            "term's start-letter map has no row for. A start position means a length and a start "
            "date only through that map (SPEC §2.2), so either the code is wrong or the term's "
            "calendar has not been configured for that cohort."
        )

    start_date = row.start_date
    end_date = start_date + timedelta(days=row.length_weeks * _DAYS_PER_WEEK - 1)
    if start_date < term_start or end_date > term_end:
        raise SectionOutsideItsTermError(
            f"Section code {code!r} derives {row.length_weeks} weeks from {start_date} to "
            f"{end_date}, which is outside its term ({term_start} to {term_end}). The start "
            "letter map row and the term's dates disagree; the calendar is the thing to fix, not "
            "the section."
        )

    return SectionCalendar(
        length_weeks=row.length_weeks,
        start_date=start_date,
        end_date=end_date,
        modality=parsed.modality,
    )


def term_week_for_course_week(session: Session, code: str, term: TermRow, course_week: int) -> int:
    """Which week of the term a section's own week `course_week` falls in.

    SPEC §2.2's two week axes. A course-level page plots "WK 01…" with a quiet
    "TERM 04…" sub-label, and an aggregate page plots the term axis with one
    line per start cohort; this is the arithmetic that keeps two charts of the
    same data from disagreeing. Course week 1 of a section starting five weeks
    into its term is term week 6 — the week, not the five-week difference.

    The offset is whole weeks between the two start dates, so a section whose
    map row does not sit on a term-week boundary is counted into the term week
    its first day falls in rather than being rounded up into the next one.
    """
    calendar = derive_section_calendar(session=session, code=code, term=term)
    if not 1 <= course_week <= calendar.length_weeks:
        raise CourseWeekOutsideItsSectionError(
            f"Course week {course_week} is outside the section {code!r} runs, which is weeks 1 to "
            f"{calendar.length_weeks}."
        )

    _, term_start, _ = _term_dates(term)
    weeks_in = (calendar.start_date - term_start).days // _DAYS_PER_WEEK
    return course_week + weeks_in


def apply_section_code(session: Session, section: Section) -> Section:
    """Set a section's four derived columns from its code and its term.

    **The one path that writes them** (SPEC §8: they derive from the section
    code via `start_letter_map`, and LMS-owned data is never hand-edited in
    Pulse). The roster sync (E1) and the seed script (E0-17) call this rather
    than assigning the columns themselves, so a section whose calendar
    disagrees with its code is not something any write path can produce.

    The term is read from `section.term_id` rather than taken as an argument:
    handing this function a term would let a caller derive a section's calendar
    from a term it does not belong to, and that mistake produces a plausible
    date rather than an error.

    The section is returned for the caller to add or flush; nothing here writes.
    """
    term = session.get(Term, section.term_id)
    if term is None:
        raise UnknownTermError(
            f"Section {section.lms_section_code!r} names the term {section.term_id!r}, which this "
            "session cannot load. A section's calendar is derived against its term (SPEC §2.2), "
            "so there is nothing to derive it from."
        )

    calendar = derive_section_calendar(session=session, code=section.lms_section_code, term=term)
    section.length_weeks = calendar.length_weeks
    section.start_date = calendar.start_date
    section.end_date = calendar.end_date
    section.modality = calendar.modality
    return section


def _term_dates(term: TermRow) -> tuple[UUID, date, date]:
    """A term's id and the two dates a section is derived against.

    A `Term` instance is what the ORM and the admin editor hand around; a
    `RowMapping` is what a Core insert with `RETURNING` gives back, which is how
    the seed script (E0-17) creates a term. `app.models.term` reads a term both
    ways for the same reason, and a service that accepted only one of them would
    push a conversion onto whichever caller holds the other.
    """
    if isinstance(term, Mapping):
        mapping: Mapping[str, Any] = term
        return mapping["id"], mapping["start_date"], mapping["end_date"]
    return term.id, term.start_date, term.end_date
