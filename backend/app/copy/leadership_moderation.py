"""The sentences the Lead Faculty review queue and the exclusion log refuse with — E6-05.

`app.api.leadership` serves SPEC §5.2's review queue, the decision a lead or a
chair makes on a queued comment, and the exclusion log. Past the role gate
(whose sentence is `app.copy.leadership_sets`' `NOT_LEADERSHIP`, the same for
every leadership route), they refuse four ways: a leader whose own grant puts
nothing under review, a comment that is not in this reader's queue, and a stated
reason that is blank or too long.

**The not-in-queue sentence is one sentence for every case.** A sibling lead's
comment, a decided one, a Care-class one and an id nothing holds are answered
alike, so the answer says nothing about whether the comment exists, where it is,
or what became of it (E6-05, decision 1).

**No reason-required sentence.** A comment reaches the queue only because the AI
flagged it, and SPEC §5.2 asks for a reason only when an unflagged comment is
excluded, so a lead's reason is optional and only its bounds are refused.

The keys sit under one prefix, `leadership_moderation.`, for the leadership
moderation screen that reads them (E6-06).
"""

from collections.abc import Mapping

from app.copy import CopyEntry

__all__ = [
    "COPY",
    "NO_REVIEW_GRANT",
    "NOT_IN_QUEUE",
    "REASON_BLANK",
    "REASON_TOO_LONG",
]

# The refusal for a leadership session whose own grant leads no course and chairs
# no department with an unled course: an assistant dean until E9, a dean, or a
# leadership session for somebody who holds only an instructor grant.
NO_REVIEW_GRANT = CopyEntry(
    key="leadership_moderation.no_review_grant",
    text="This leadership role has no review queue or exclusion log to read.",
)

# The 404 for a decision on anything that is not in this reader's queue now.
NOT_IN_QUEUE = CopyEntry(
    key="leadership_moderation.not_in_queue",
    text="There is no comment awaiting your review here. Nothing was changed.",
)

# The two reason refusals, with the bound the database holds (E6-03).
REASON_BLANK = CopyEntry(
    key="leadership_moderation.reason_blank",
    text="A stated reason has to contain some words, or be left out. Nothing was changed.",
)

REASON_TOO_LONG = CopyEntry(
    key="leadership_moderation.reason_too_long",
    text="A stated reason can be at most 500 characters long. Nothing was changed.",
)

COPY: Mapping[str, CopyEntry] = {
    entry.key: entry for entry in (NO_REVIEW_GRANT, NOT_IN_QUEUE, REASON_BLANK, REASON_TOO_LONG)
}
