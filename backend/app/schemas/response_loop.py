"""What the response loop's routes take and answer — SPEC §5.3 and §5.4.

**The student results route.**

One section-week, read by one of its own students, under the hold (ADR 0193,
ADR 0197): the course label, the week's state and the response a named person
published to it in every state; and, once the week is not `awaiting`, the two
streams' trend, distributions, small-N state and published comments, the
workload median, and on the latest published week the comments released from
earlier weeks. No count of anybody and no benchmark (SPEC §4.1 item 1, §5.4).

**Every model here refuses a member it never declared**, as every student schema
in `app.schemas.student` does: a comparison figure, a benchmark or a university
average handed to one of these constructors raises rather than being dropped in
silence, so a later join cannot quietly carry one to a student (SPEC §4.1 item
1). `tests/unit/test_the_student_payload_schema_carries_nothing_of_a_benchmark.py`
walks every model the results payload reaches inside the invariant pass.

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
    "StudentComment",
    "StudentReleasedComment",
    "StudentResponse",
    "StudentStream",
    "StudentStreamName",
    "StudentTrendPoint",
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


class StudentParticipation(BaseModel):
    """The student's own latest accepted participation score, exactly as it was posted.

    Both strings are the characters sent to the platform (SPEC §3.4, ADR 0125);
    nothing here is recomputed. It is the student's own record and not an
    aggregate of the week, so it does not follow the week's hold.
    """

    model_config = ConfigDict(extra="forbid")

    score_text: str = Field(description="The score as it was sent to the gradebook.")
    ledger_text: str = Field(description="The per-week ledger sent beside the score.")


StudentStreamName = Literal["instructor", "course"]


class StudentTrendPoint(BaseModel):
    """One week's rating mean in one stream, for a week a student may read (SPEC §5.4's trend).

    A week fewer than the threshold of students rated has a point with no mean
    (ruling 8). A held week has no point at all (ADR 0197).
    """

    model_config = ConfigDict(extra="forbid")

    course_week: int
    mean: float | None = Field(
        description="The mean of the week's ratings; null if too few students rated."
    )


class StudentComment(BaseModel):
    """One published or kept comment under its stream: its words and nothing else.

    No key, status, time or week: SPEC §4 never shows a time with a comment, and
    any handle would let a reader line it up with something else.
    """

    model_config = ConfigDict(extra="forbid")

    text: str


class StudentReleasedComment(BaseModel):
    """One comment from a release batch: its words and its stream, and never its week (ADR 0153)."""

    model_config = ConfigDict(extra="forbid")

    text: str
    stream: StudentStreamName


class StudentStream(BaseModel):
    """One of a released week's two streams, as a student of the section reads it (SPEC §5.4).

    `small_n` is true when the stream's comments are withheld (SPEC §4.1 item 3),
    and then `comments` is empty. The ratings are shares, never counts, and are
    withheld when too few students rated (ruling 8). No count of anybody, here or
    anywhere on the payload (SPEC §5.4).
    """

    model_config = ConfigDict(extra="forbid")

    stream: StudentStreamName
    trend: list[StudentTrendPoint] = Field(
        description="One point per readable week up to this one; a held week has none."
    )
    shares: dict[str, int] | None = Field(
        description=(
            "Each rating's whole-number percentage, keyed 1 to 5, summing to 100; null "
            "when too few students rated."
        )
    )
    small_n: bool = Field(description="Whether this stream's comments are withheld this week.")
    comments: list[StudentComment] = Field(
        description="The published and kept comments, in a random order; empty when small_n."
    )


class StudentWeekResults(BaseModel):
    """One week of one of the student's own sections, under the hold (SPEC §5.3, §5.4).

    In every state: the course label, the state, the response if any, and the
    course weeks a student may page through (published weeks only). While the
    week is `awaiting`, `streams`, `workload_median` and `released` are null:
    nothing about the week is served until a response releases it (ADR 0193,
    ADR 0197).
    """

    model_config = ConfigDict(extra="forbid")

    course_label: str = Field(description="The course's label, with its section code and term.")
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
    streams: list[StudentStream] | None = Field(
        description="The instructor stream, then the course stream; null while awaiting."
    )
    workload_median: float | None = Field(
        description="The median of the week's workload answers; null while awaiting or if too few."
    )
    released: list[StudentReleasedComment] | None = Field(
        description=(
            "Comments released from earlier weeks, with no week named. Present on the "
            "latest published week only, and only while no published week is awaiting."
        )
    )
    participation: StudentParticipation | None = Field(
        default=None,
        description=(
            "The student's latest accepted participation score; absent before any score "
            "has been posted. Shown in every state."
        ),
    )


# ---------------------------------------------------------------------------
# The publish and edit doors, the policy, the owed read and on behalf (ADR 0194).
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
    role and time, and `can_edit`, true exactly when the reader first published
    the week's response (SPEC §5.3: only that person may edit). Nothing else a
    student does not read.
    """

    model_config = ConfigDict(extra="forbid")

    state: WeekState = Field(description="Whether the week is held, answered, or neither.")
    response: StudentResponse | None = Field(
        description="The published response; absent while awaiting and when unanswered."
    )
    can_edit: bool = Field(
        description="Whether this reader first published the week's response, so may edit it."
    )


class PolicyWrite(BaseModel):
    """A switch of the response policy for every course of one prefix the reader sets it for."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: PolicyMode = Field(description="REQUIRED or ENCOURAGED.")


class PolicyCourse(BaseModel):
    """One course's response policy as one reader reads it (ADR 0194).

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
    response: WeekResponseView | None = Field(
        description="Null while unanswered; the response, for the reader who first published it."
    )
