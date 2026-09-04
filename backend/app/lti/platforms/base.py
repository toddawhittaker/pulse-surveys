"""What a `PlatformProfile` is, and the conformant answer for a platform nothing is written for.

SPEC §7.3 asks for "a thin `PlatformProfile` adapter (Canvas, Moodle, D2L,
Blackboard) for known deviations in AGS score semantics and NRPS paging — quirks
live in one file each, nothing leaks into domain logic". This is the seam half of
that: the values `app.lti.ags` consults, and the conformant answer.

**Every field is what a platform that deviates in nothing does**, so a profile
written later states only its own deviation and inherits the rest. That is what
makes "quirks live in one file each" true rather than aspirational — a profile
that had to restate the conformant values would be a place for one of them to
drift.

**Two progress members and a page size, and no more, because that is what has a
caller.** SPEC §7.3 names AGS score semantics and NRPS paging as the two places
platforms deviate, and E3-04 posts scores and walks a line-item container. A
field added here for a deviation nobody has met is a field nobody knows what to
put in — E3's later tickets and whichever ticket meets a real platform are the
ones that will know. See ADR 0132.

**Nothing here is a configuration knob.** These are facts about somebody else's
software, resolved from the registration's issuer; an operator has no more say in
them than in which LMS the institution runs.
"""

from dataclasses import dataclass
from typing import Final

# AGS 2.0's own words for "the student finished the activity" and "this number is
# the grade". SPEC §3.4 posts a participation percentage that is complete as it
# stands — the week has closed, the arithmetic is done — so a conformant platform
# is told exactly that. Both are exact strings out of AGS 2.0's two fixed
# vocabularies; a near miss is a word Canvas answers 422 to and D2L accepts into a
# column that never shows a grade.
CONFORMANT_ACTIVITY_PROGRESS: Final[str] = "Completed"
CONFORMANT_GRADING_PROGRESS: Final[str] = "FullyGraded"

# How many line items this tool asks a container for at a time. A request, not an
# expectation: AGS lets a platform cap what a client asks for and clamp to its own
# maximum, so a walk still follows `rel="next"` to the end whatever comes back.
# A hundred is past any real gradebook's line-item count for one section — the
# tool creates exactly one — so the ordinary walk is a single page, and a platform
# that pages at five still answers correctly.
CONFORMANT_CONTAINER_PAGE_SIZE: Final[int] = 100


@dataclass(frozen=True)
class PlatformProfile:
    """One platform's deviations from AGS 2.0, or none.

    Frozen, because a profile is a statement about somebody else's software for
    the life of the process and nothing in a request should be able to edit it.
    """

    activity_progress: str = CONFORMANT_ACTIVITY_PROGRESS
    grading_progress: str = CONFORMANT_GRADING_PROGRESS
    container_page_size: int = CONFORMANT_CONTAINER_PAGE_SIZE


# What a platform nothing is written for gets. Not `None`: a caller that had to
# ask "is there a profile?" before every read would have the conformant defaults
# written into it at each call site, which is the seam not being consulted
# (`docs/MISTAKES.md` entry 9) wearing the shape of a null check.
CONFORMANT_PROFILE: Final[PlatformProfile] = PlatformProfile()
