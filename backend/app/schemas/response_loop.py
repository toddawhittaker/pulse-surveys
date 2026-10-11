"""What the student results route answers with — E7-02, SPEC §5.3 and §5.4.

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

from pydantic import BaseModel, ConfigDict, Field

from app.models.loop import ResponseRole

__all__ = ["StudentResponse", "StudentWeekResults", "WeekState"]

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
    """One week's state for one of the student's own sections, and its response if any."""

    model_config = ConfigDict(extra="forbid")

    state: WeekState = Field(description="Whether the week is held, answered, or neither.")
    response: StudentResponse | None = Field(
        description="The published response; absent while awaiting and when unanswered."
    )
