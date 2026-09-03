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

__all__ = ["COMMENT_MAXIMUM_LENGTH", "SubmissionAccepted", "SubmissionRequest", "SubmittedAnswer"]

# How long a submitted comment may be. SPEC §3.2 makes both comments free text and
# gives them no length, and an unbounded one is a request body that reaches the
# model: a bill, a latency inside SPEC §10's 2.5-second whole-round-trip budget,
# and a prompt surface, all sized by whoever is typing. 4000 characters is several
# times the longest weekly comment a student writes and small enough that none of
# those three is a lever. It is enforced here rather than in the service so that an
# over-long comment is refused *before* the provider is asked — ADR 0062's one
# parse at the edge, and the difference between preventing the request and paying
# for it — and it refuses rather than truncating, because a truncation stores words
# the student did not write under their name and §5.1 shows those to the instructor.
#
# Not a configuration knob: an operator who could raise it would be raising
# somebody else's bill and spending this route's own latency budget, and §6.3's
# configuration surface does not name it.
COMMENT_MAXIMUM_LENGTH = 4000


class SubmittedAnswer(BaseModel):
    """One question of one submission, answered.

    Exactly one of the three value fields is expected to be filled, and that this
    is so is checked in the service beside the rest of the rules rather than here:
    the refusal a student sees for it is one of `app.copy`'s sentences, and a
    Pydantic validator's own message is not.

    **The one bound that does live here is the comment's length**, and the reason
    is the opposite of the one above: it is worth refusing before anything reads
    the body rather than in a service the request has already paid to reach. See
    `COMMENT_MAXIMUM_LENGTH`.
    """

    model_config = ConfigDict(extra="forbid")

    position: int = Field(ge=1)
    rating: int | None = None
    comment_text: str | None = Field(default=None, max_length=COMMENT_MAXIMUM_LENGTH)
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
