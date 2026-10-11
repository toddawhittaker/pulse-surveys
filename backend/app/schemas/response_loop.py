"""What the response loop's routes take and answer — E7-02 and E7-03, SPEC §5.3 and §5.4.

**E7-02: the student results route.**

One section-week, read by one of its own students: the week's state, and the
response a named person published to it. Nothing else. SPEC §5.4 puts the
aggregates, the comments and the small-N state on the same page; those are E8's
(the owner's ruling 8 for E7), and this contract has no member for any of them.

**Every model here refuses a member it never declared**, as every student schema
in `app.schemas.student` does (E5-11): a comparison figure, a benchmark or a
university average handed to one of these constructors raises rather than being
dropped in silence, so a later join cannot quietly carry one to a student (SPEC
§4.1 item 1). `tests/unit/test_the_student_results_payload_carries_nothing_of_a_
benchmark.py` measures it inside the invariant pass.

**The states are a closed set.** `awaiting`: the policy of record holds the week
and nobody has published. `published`: the first response was written as the
instructor. `on-behalf`: the first response was written under a leadership role.
`unanswered`: the week is encouraged and nobody has published. A week whose
report has not opened has no state; the route refuses it instead.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.loop import RESPONSE_TEXT_MAX, PolicyMode, PolicyRole, ResponseRole

__all__ = [
    "OnBehalfStream",
    "OnBehalfStreamName",
    "OnBehalfWeek",
    "OwedWeek",
    "PolicyCourse",
    "PolicyOverview",
    "PolicyPrefix",
    "PolicyWrite",
    "ResponseWrite",
    "StudentResponse",
    "StudentWeekResults",
    "WeekResponseView",
    "WeekState",
]

WeekState = Literal["awaiting", "published", "on-behalf", "unanswered"]


class StudentResponse(BaseModel):
    """The response a student reads for one week, and who wrote it (SPEC §5.3).

    The text and the time are the latest row's: an edit is a new row, and the
    latest row is what students read (ruling 3). The author and the role are the
    first row's, which is the same person, since only the person who first
    published a week's response may edit it.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="The response as it now reads.")
    author_name: str = Field(description="The name of the person who wrote it.")
    author_role: ResponseRole = Field(
        description=(
            "The role it was written under. LEAD_FACULTY or CHAIR means it was written on "
            "the instructor's behalf."
        )
    )
    published_at: datetime = Field(description="When the text now shown was published.")


class StudentWeekResults(BaseModel):
    """One week's state for one of the student's own sections, its response if any, and the
    course weeks a student may page through (SPEC §5.4: published weeks only)."""

    model_config = ConfigDict(extra="forbid")

    state: WeekState = Field(description="Whether the week is held, answered, or neither.")
    response: StudentResponse | None = Field(
        description="The published response; absent while awaiting and when unanswered."
    )
    published_weeks: list[int] = Field(
        description=(
            "The section's course weeks whose report has opened, ascending: the weeks the "
            "page may page through."
        )
    )


# ---------------------------------------------------------------------------
# E7-03: the publish and edit doors, the policy, the owed read and on behalf.
#
# Every model refuses a member it never declared, as the student models above
# do, so a later join cannot quietly carry a comment, a name or a time onto a
# leadership read (SPEC §4.1).
# ---------------------------------------------------------------------------


class ResponseWrite(BaseModel):
    """A response's text as its author publishes or edits it, and whether the AI draft seeded it.

    **Bounded and refused, never repaired** (`docs/MISTAKES.md` entry 29): a text
    over `RESPONSE_TEXT_MAX` characters, an empty one, or one of only whitespace
    is a 422 before anything is read, and nothing here strips or shortens it. The
    table's `CHECK` holds the same rule underneath.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(
        min_length=1,
        max_length=RESPONSE_TEXT_MAX,
        description="The response students will read, exactly as written.",
    )
    ai_seeded: bool = Field(description="Whether the text began as the AI draft.")

    @field_validator("text")
    @classmethod
    def _not_only_whitespace(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("A response needs some text.")
        return text


class WeekResponseView(BaseModel):
    """One week's state and its response, as students read them, for the response's author.

    What the instructor's response routes, and the on-behalf publish and edit,
    answer: the state a student of the section reads now, and the response with
    its author's name (through the staff-name definer, asked as the reader),
    role and time. Nothing a student does not read.
    """

    model_config = ConfigDict(extra="forbid")

    state: WeekState = Field(description="Whether the week is held, answered, or neither.")
    response: StudentResponse | None = Field(
        description="The published response; absent while awaiting and when unanswered."
    )


class PolicyWrite(BaseModel):
    """A switch of the response policy for every course of one prefix the reader sets it for."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: PolicyMode = Field(description="REQUIRED or ENCOURAGED.")


class PolicyCourse(BaseModel):
    """One course's response policy as one reader reads it (E7-03, decision 2).

    `mode` is the course's latest policy row now, or `ENCOURAGED` with none.
    `set_by_role` says which role set it, and only on a course the reader cannot
    set (a chair reading a course with a lead): on a course the reader sets, it is
    absent, so nothing on it moves with anybody else's change (done-when 4).
    Never a name: the setter's name is E9's.
    """

    model_config = ConfigDict(extra="forbid")

    course_id: UUID
    course_label: str = Field(description="The course's prefix, number and title.")
    mode: PolicyMode
    can_set: bool = Field(description="Whether this reader's switch for the prefix reaches it.")
    set_by_role: PolicyRole | None = Field(
        description="The role that set it; only for a course this reader cannot set."
    )


class PolicyPrefix(BaseModel):
    """One prefix and the courses of it this reader reads the policy of."""

    model_config = ConfigDict(extra="forbid")

    prefix_id: UUID
    prefix_code: str
    courses: list[PolicyCourse]


class PolicyOverview(BaseModel):
    """Every course whose response policy this reader sets or reads, by prefix."""

    model_config = ConfigDict(extra="forbid")

    prefixes: list[PolicyPrefix]


class OwedWeek(BaseModel):
    """One section-week owed a response now, in a course the reader answers for (decision 4).

    No instructor name (E9's) and no time: whether the on-behalf door is open is
    the one fact about the clock the list carries.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: UUID
    section_label: str = Field(description="The section's course label and section code.")
    course_week: int
    on_behalf_open: bool = Field(description="Whether a response may now be written on behalf.")


OnBehalfStreamName = Literal["instructor", "course"]


class OnBehalfStream(BaseModel):
    """One stream of one section-week as the on-behalf reader reads it: never a comment.

    The stored summary, or `null` where none is served to this reader (including
    one written before the week's latest exclusion, ruling 9); the week's
    response count; and the rating distribution, rating to count, as the report
    shows it.
    """

    model_config = ConfigDict(extra="forbid")

    stream: OnBehalfStreamName
    summary_text: str | None
    response_count: int = Field(description="How many responses the week received.")
    rating_distribution: dict[str, int] = Field(
        description="How many responses gave each rating, 1 to 5."
    )


class OnBehalfWeek(BaseModel):
    """What a lead (or a chair acting as lead) reads before responding on behalf (decision 5)."""

    model_config = ConfigDict(extra="forbid")

    section_label: str = Field(description="The section's course label and section code.")
    course_week: int
    streams: list[OnBehalfStream]
