"""What a student's weekly survey read answers with — ticket E2-09, SPEC §3.1.

One question, answered in one round trip: *for me, right now, what is there?*
E2-10's form is written against this contract and, through SPEC §7.6's OpenAPI
document, generated from it.

**Everything here is about the reader's own sections and nobody else's.** SPEC
§4.1 item 1 forbids a student surface naming another section, in any form, and
this contract is the shape that rule is enforced over: there is no member for a
comparison, an average, a classmate, or a section the reader is not enrolled in,
and `app.services.survey_read` is scoped so that none could be filled. What keeps
the two halves honest is
`tests/integration/test_the_student_read_path_names_nothing_outside_the_enrollment.py`,
which reads this answer over the wire and scans it for anything shaped like the
other section.

**Two week numbers, under both names** (SPEC §2.2). A course-level page plots the
course week with a quiet term-week sub-label, so both travel and the form renders
one under the other. `course_week` counts from the section's own start — a
15-week section that began in term week 4 is in its tenth week when the term is
in its thirteenth — and serving one in the other's place tells a student they are
three weeks further through their course than they are.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.survey import QuestionKind


class SurveyQuestion(BaseModel):
    """One question of the set, as the form has to render it (SPEC §3.2).

    The conditional rule and the numeric bounds travel with the question rather
    than being restated in the form: §3.2 makes the instructor comment required
    when the instructor rating is 2 or less, and the workload figure a number in a
    range with a step, and a form that carried its own copy of either would
    disagree with the validity check the moment a set is versioned.
    """

    id: UUID = Field(description="The question row, which an answer is keyed to.")
    position: int = Field(description="Ordinal within the set, 1-based, ascending.")
    kind: QuestionKind = Field(description="What sort of answer this question takes.")
    name: str = Field(description="The stable machine name of the question.")
    prompt: str | None = Field(description="The wording a person reads.")
    required_if_position: int | None = Field(
        description="Position of the question whose answer can make this one required."
    )
    required_if_at_most: int | None = Field(
        description="This question is required when that answer is at most this value."
    )
    minimum_value: Decimal | None = Field(description="Lowest value this question accepts.")
    maximum_value: Decimal | None = Field(description="Highest value this question accepts.")
    step: Decimal | None = Field(description="The increment values must fall on.")


class SubmittedAnswer(BaseModel):
    """One answer this reader already gave, in whichever of the three it holds.

    All three value columns travel, and the reason is a defect this shape makes
    impossible rather than a convenience: a read that returned the comment and not
    the workload figure renders a resubmit form with a field silently blanked, and
    the student's stored hours are then overwritten by the empty box.
    """

    question_id: UUID = Field(description="The question this answers.")
    rating: int | None = Field(description="A Likert answer, 1-5.")
    comment_text: str | None = Field(description="A free-text answer.")
    workload_hours: Decimal | None = Field(description="An hours-per-week answer.")


class OwnSubmission(BaseModel):
    """What this reader has already submitted for this week, if anything.

    Their own and only ever their own. SPEC §5.4 gives a student their own section
    and never another individual's raw data, and §4 keys every response to its
    author; the lookup behind this is over the reader, the section and the week
    together, and the denial suite is what proves the reader is in that key.
    """

    first_submitted_at: datetime = Field(description="When this week was first answered.")
    last_submitted_at: datetime = Field(description="When it was last revised.")
    answers: list[SubmittedAnswer] = Field(description="The answers, in question order.")


class OpenSurvey(BaseModel):
    """The one survey open for a section right now (SPEC §3.1's one-open rule).

    Present only while the window is open. §3.1 says a missed week cannot be
    back-filled, so a closed week is not something the form can answer and is not
    offered as one; the section it belonged to is still reported, which is how a
    student is told they are enrolled and there is nothing to do this minute.
    """

    window_id: UUID = Field(description="The survey window this answers over.")
    course_week: int = Field(
        description="Which week of this section's own run the window covers, counting from 1."
    )
    term_week: int = Field(description="Which week of the term the same window covers.")
    opens_at: datetime = Field(description="When the window opened.")
    closes_at: datetime = Field(description="When it closes.")
    question_set_version: int = Field(description="Version of the question set being served.")
    questions: list[SurveyQuestion] = Field(description="The questions, in position order.")
    submission: OwnSubmission | None = Field(
        description="What this reader has already submitted for this week, or null."
    )


class EnrolledSection(BaseModel):
    """One section this reader is enrolled in today, and its survey state."""

    section_id: UUID = Field(description="The section row.")
    section_code: str = Field(description="The section code a person reads (SPEC §2.2).")
    survey_is_open: bool = Field(
        description="Whether a survey is open for this section at this moment."
    )
    open_survey: OpenSurvey | None = Field(
        description="The open survey, or null when none is open."
    )


class StudentSurveyView(BaseModel):
    """Everything a student's weekly survey form needs, in one answer.

    A list rather than a single section, because a student may be enrolled in
    several and the form asks about all of them at once. An empty list is an
    ordinary answer: somebody between terms is enrolled in nothing today and is
    told so, rather than refused.
    """

    sections: list[EnrolledSection] = Field(
        description="The reader's live enrollments, in section-code order."
    )
