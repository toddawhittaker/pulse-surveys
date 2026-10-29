"""The named-set management API as it goes over the wire (SPEC §5.1, §8).

`app.api.leadership` serves eight routes over five shapes: what a set looks like
in a list, what it looks like on its own, what a client sends to create or edit
one, what the definition form is offered as choices, and (E9-05) a set's figures
for one leadership reader. E5-09 renders the first four; E9-11 draws the fifth.

**`SetWrite` types the length as a plain `int` and the level as a plain `str`,
and that is a decision rather than laziness.** SPEC §5.1's rules about a set —
a length of at least one week, one of §8's five levels, every member course at
the declared level — are held by Postgres, in a `CHECK`, an enum type and a
composite foreign key (E5-01, ADR 0164). E5-06's job is to *translate* what the
database refuses, not to refuse it a second time here: a constrained type on this
model would answer `0` and `"ug"` with Pydantic's own validation error before any
statement ran, which is a different layer, a different body, and a claim about
the wire model rather than about the constraint. `app.services.comparison_sets`
attempts the write and maps the constraint that fired to one sentence.

**`member_course_ids` is a list of keys and nothing else.** A member is a course
(ADR 0164: membership is at course grain, because a set of sections would age out
every term), and the level the membership row carries is read from the course row
by the service rather than sent by the client — a client-supplied level would be
a second statement of a fact the `course` table already holds.

**`editable` is what the scope decision looks like on the wire** (ADR 0173). Every
leadership session reads every set in the institution; only the leader who
defined one may edit or delete it. Without this member E5-09 would have to offer
an edit control that discovers its refusal by pressing it.

**The preview carries two counts and no third member.** SPEC §4.1 item 7
suppresses statistics computed over a comparison set below the configured
minimums; a count of member courses and a count of resolved sections say how wide
a cohort is and nothing about what anybody in it answered, which is what makes
them safe at definition time and what makes a third member here — a mean, a list
of section codes — a figure reaching a reader outside the suppression chokepoint.

Every model is frozen, the way `app.schemas.report`'s are: a payload assembled at
one moment and serialized at another is a payload those two can disagree about.

**The series payload carries figures, and each is sealed at the wire** (E9-05).
A named set's series, read by a leader, is the first payload here holding a
`ComparisonFigure`, so its three models follow `app.schemas.report_benchmark`'s
two rules: `revalidate_instances="always"` on every model on the path down to a
figure, and one `refuse_an_unsealed_comparison` validator per figure member. No
member is called `comparison`, which keeps E4-07's discovery rule (the one model
in `app.schemas.report` carrying that member) intact. Nothing sits beside a
figure: a count of sections or respondents there would hand back what the
minimums withhold.
"""

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from app.services.reporting import ComparisonFigure, refuse_an_unsealed_comparison

__all__ = [
    "CourseOption",
    "NamedSetCohort",
    "NamedSetSeries",
    "NamedSetWeek",
    "SetDetail",
    "SetList",
    "SetOptions",
    "SetPreview",
    "SetSummary",
    "SetWrite",
]


class SetWrite(BaseModel):
    """What a client sends to create or edit a comparison set.

    The same body on `POST` and on `PUT`, because an edit replaces a set's whole
    definition — its name, its declared pair, and its membership — rather than
    patching part of one. A partial edit would make "what is this set" a question
    about which fields arrived.

    `length_weeks` and `level` are deliberately unconstrained here. See the module
    docstring: the database holds both rules and this route translates what it
    refuses.

    **The name's surrounding spaces are stripped, and a name empty after that
    is refused here** (E5-14), so " Nursing" and "Nursing" are one name to the
    unique constraint, and a name of only spaces is answered with the framework's
    standard 422 before any statement runs. That is the one rule this model
    holds itself, and it is the ruling's choice over a new refusal sentence: the
    table's `name_is_not_blank` check stays underneath it for every other writer,
    but the translator names no sentence for it, so a blank name reaching the
    table from this route would be a 500.
    """

    model_config = ConfigDict(frozen=True)

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    length_weeks: int
    level: str
    member_course_ids: list[UUID]


class SetSummary(BaseModel):
    """One set as it appears in the institution-wide list.

    `member_count` is the number of member courses, not of resolved sections —
    the preview answers that, and the two are different numbers for every set
    whose courses run more than one section.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str
    length_weeks: int
    level: str
    member_count: int
    editable: bool


class SetDetail(SetSummary):
    """One set on its own: the summary, its membership, and when it was written.

    The two instants are the whole record that a set was created and edited (ADR
    0174): this ticket writes no `audit_log` row, and these columns are what is
    recorded instead.
    """

    model_config = ConfigDict(frozen=True)

    member_course_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


class SetList(BaseModel):
    """Every set in the institution, in name order."""

    model_config = ConfigDict(frozen=True)

    sets: list[SetSummary]


class CourseOption(BaseModel):
    """One course a set may name, as the definition form offers it.

    The level is carried beside the label so the form can offer only the courses
    a chosen level admits — the cross-level refusal exists for the API caller who
    is not using the form, and a form that let the choice be made would be
    offering a set the database will refuse at the moment of saving.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    label: str
    level: str


class SetOptions(BaseModel):
    """The closed choices a set is defined out of: the lengths, the levels, the courses."""

    model_config = ConfigDict(frozen=True)

    lengths: list[int]
    levels: list[str]
    courses: list[CourseOption]


class SetPreview(BaseModel):
    """What a set reaches, as two counts and nothing else. See the module docstring."""

    model_config = ConfigDict(frozen=True)

    member_count: int
    section_count: int


class NamedSetWeek(BaseModel):
    """One course week of one start cohort, on both of SPEC §2.2's week axes, every figure sealed.

    The two rating means and the workload mean and median, each suppressed or
    shown on its own decision (§4.1 item 7 covers "a mean, a median, or any
    other statistic"). One validator per member, so removing one seal is one
    test going red.
    """

    model_config = ConfigDict(frozen=True, revalidate_instances="always")

    course_week: int
    term_week: int
    instructor_mean: ComparisonFigure
    course_mean: ComparisonFigure
    workload_mean: ComparisonFigure
    workload_median: ComparisonFigure

    @field_validator("instructor_mean")
    @classmethod
    def _the_instructor_mean_is_the_helpers(cls, figure: ComparisonFigure) -> ComparisonFigure:
        """SPEC §4.1 item 7 over the instructor-stream rating mean."""
        refuse_an_unsealed_comparison(figure)
        return figure

    @field_validator("course_mean")
    @classmethod
    def _the_course_mean_is_the_helpers(cls, figure: ComparisonFigure) -> ComparisonFigure:
        """SPEC §4.1 item 7 over the course-stream rating mean."""
        refuse_an_unsealed_comparison(figure)
        return figure

    @field_validator("workload_mean")
    @classmethod
    def _the_workload_mean_is_the_helpers(cls, figure: ComparisonFigure) -> ComparisonFigure:
        """SPEC §4.1 item 7 over the workload mean."""
        refuse_an_unsealed_comparison(figure)
        return figure

    @field_validator("workload_median")
    @classmethod
    def _the_workload_median_is_the_helpers(cls, figure: ComparisonFigure) -> ComparisonFigure:
        """SPEC §4.1 item 7 over the workload median, which item 7 names beside the mean."""
        refuse_an_unsealed_comparison(figure)
        return figure


class NamedSetCohort(BaseModel):
    """One start cohort of the reader's purview in the viewed term, and its published weeks."""

    model_config = ConfigDict(frozen=True, revalidate_instances="always")

    section_start_date: date
    weeks: list[NamedSetWeek]


class NamedSetSeries(BaseModel):
    """A named set's figures for one leadership reader in one term, one series per start cohort.

    A set wholly outside the reader's purview answers exactly the shape a thin set
    inside it does: the purview's cohorts, every figure suppressed (E9-05).
    """

    model_config = ConfigDict(frozen=True, revalidate_instances="always")

    cohorts: list[NamedSetCohort]
