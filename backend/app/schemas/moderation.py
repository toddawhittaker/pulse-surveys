"""The Lead Faculty review queue, a leader's decision, and the exclusion log, on the wire (SPEC §5.2).

`app.api.leadership` serves three routes over these shapes; E6-06 renders them.

**A queue item is three members and no fourth** (E6-05, decision 1): the
comment's key, its text and the label of the section it was written in. No week,
no date, no time and no count — the queue shows a lead text from below the
threshold (ruling 1), and a week or an instant beside it would place the text in
a week the threshold hides. The order is drawn again on every read.

**A log row is six members** (decision 1): the section label, the role the
decision was made under, whether the AI flagged the comment, the stated reason,
the date in the institution's zone, and an excerpt of the comment that is null
whenever its own instructor's report does not show the comment in a week.

Each list travels as the only member of an object, so nothing can sit beside it:
the obvious thing to put there, a count, is what decision 1 forbids on the queue.

Every model is frozen, the way `app.schemas.report`'s are.
"""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

__all__ = [
    "ExclusionLog",
    "LeadDecision",
    "LogRow",
    "QueueItem",
    "ReviewQueue",
]


class QueueItem(BaseModel):
    """One harmful, undecided comment awaiting this reader's review."""

    model_config = ConfigDict(frozen=True)

    answer_id: UUID
    text: str
    # The course label with the section's code and term, as the instructor's
    # report names the same section (`section_codes.course_label`).
    section_label: str


class ReviewQueue(BaseModel):
    """The reader's review queue, in an order drawn for this request."""

    model_config = ConfigDict(frozen=True)

    items: list[QueueItem]


class LeadDecision(BaseModel):
    """What a lead or chair sends to exclude or keep one queued comment.

    Two actions: a leader has no undo (decision 1). `reason` is optional, because
    every queued comment was flagged by the AI, and is checked by the decision
    service as it was sent, before any trimming (`docs/MISTAKES.md` entry 29).
    """

    model_config = ConfigDict(frozen=True)

    action: Literal["exclude", "keep"]
    reason: str | None = None


class LogRow(BaseModel):
    """One decision a person made about a comment inside the reader's own grant."""

    model_config = ConfigDict(frozen=True)

    section_label: str
    # The role the decision was stored under, not the decider's role today.
    decided_as: Literal["INSTRUCTOR", "LEAD_FACULTY", "CHAIR"]
    # Whether the comment holds a harmful or privacy verdict.
    flagged: bool
    reason: str | None
    # The decision's date in the institution's zone, and never its time.
    decided_on: date
    # The first 140 characters of the comment, or null when its instructor's
    # report does not show it in a week.
    excerpt: str | None


class ExclusionLog(BaseModel):
    """The reader's exclusion log, newest decision first."""

    model_config = ConfigDict(frozen=True)

    rows: list[LogRow]
