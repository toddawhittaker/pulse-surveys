"""The wire shape of a weekly submission, parsed once at the edge (SPEC §3.2, ADR 0062).

§13 puts "Pydantic request/response contracts" here, and ADR 0062 says what a
contract is for: **one parse, at the edge, into typed values; every check reads
what that parse produced.** So the route declares these models and hands them to
`app.services.submissions`, and nothing downstream reaches back into the request
body, re-reads a field or coerces a value a second time.

**A submission names its questions by position, and its values by the column they
are stored in.** Both spellings are E2-05's rather than this module's: `position`
is the ordinal §3.2 numbers its five questions by and writes its conditional rules
against ("Required if Q1 ≤ 2"), and `rating`, `comment_text` and `workload_hours`
are the three columns an `answer` row holds exactly one of. Naming the question by
its primary key instead would make the form's markup carry a UUID per question for
no gain, and naming a value "value" would lose the shape the schema already knows.

**An omitted answer is an absent member, never a member holding null.** "The
comment is blank" and "the required comment is missing" look the same on the wire,
and the difference between them is the Likert rating beside it — §3.2's rule —
rather than anything about the request. `answer` stores a blank comment as no row
at all (it holds exactly one value), so this is the wire shape agreeing with the
table.

**Nothing here validates a value against its question**, and that is deliberate
rather than an omission. The bounds live on the `question` row (ADR 0110) and the
conditional rule is about *other answers in the same submission*, so neither is a
statement a field validator can make; both are `app.services.submissions`'.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["SubmissionAccepted", "SubmissionRequest", "SubmittedAnswer"]


class SubmittedAnswer(BaseModel):
    """One question of one submission, answered.

    Exactly one of the three value fields is expected to be filled, and that this
    is so is checked in the service beside the rest of the rules rather than here:
    the refusal a student sees for it is one of `app.copy`'s sentences, and a
    Pydantic validator's own message is not.
    """

    model_config = ConfigDict(extra="forbid")

    position: int = Field(ge=1)
    rating: int | None = None
    comment_text: str | None = None
    workload_hours: Decimal | None = None


class SubmissionRequest(BaseModel):
    """One student's answers to one section's open weekly survey.

    The week is deliberately absent: SPEC §3.1 gives a section exactly one open
    survey at a time, so the week a submission belongs to is a fact the server
    resolves from the open window rather than a value a caller may choose. A
    request that could name its own week could name a week that has closed.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: UUID
    answers: list[SubmittedAnswer]


class SubmissionAccepted(BaseModel):
    """What a stored submission answers with: the student's own row, and nothing else.

    `is_valid` is this submission's own §3.3 verdict, which the student is entitled
    to — the section's validity *rate* is an instructor and leadership surface
    (§3.3, §4.1 item 1) and is no part of this answer.
    """

    response_id: UUID
    is_valid: bool
    first_submitted_at: datetime
    last_submitted_at: datetime
