"""The response loop's two records: a published response, and a response policy (SPEC §5.3, §8).

E7-01, ADR 0192. SPEC §5.3 has an instructor (or the lead, on the instructor's
behalf) post a short response to the week's report, and lets a lead require one.
The owner's ruling 7 for E7 makes these two tables **the record** of both: every
response and every on-behalf response with its author, and every policy change
with who made it. There is no `audit_log` row for either, as E6's ruling 3
decided for exclusions, and `audit_log.subject_user_id` must hold a student
anyway.

**Both tables are append-only.** Every edit of a response is a new row and the
latest row is what students see (ruling 3), and a policy change is a new row
too. `pulse_app` holds `SELECT` and column-grain `INSERT` on both and no
`UPDATE` or `DELETE` (`views_sql/response_loop_grants_v001.sql`). "Latest" is
`sequence`, the database's insertion order, exactly as on `moderation_state`
(ADR 0187): the two time columns are written by the application from
`services/clock.now` so that the development clock stays coherent, and a time a
writer supplies is never the order.

**The role is on the row, and on-behalf is the role.** A response records the
role its author wrote under (`INSTRUCTOR`, `LEAD_FACULTY`, or `CHAIR` for the
chair acting as lead of a course with no lead), so there is no second flag that
could disagree with it. A policy records the role it was set under, which is how
a person who both leads courses and chairs the department is keyed (ADR 0192).

**The author and the setter are `person` keys, never names.** A name reaches a
reader only through the staff-name definer (`views_sql/section_staff_names_v001.sql`
and `_v002.sql`, ADRs 0191 and 0201), whose reader check decides who may read it.

**Who may write a row is checked when it is written** (ADR 0192,
`views_sql/response_loop_guard_v001.sql`). A `BEFORE INSERT` trigger on each
table refuses a row unless its author or setter holds the stated role there at
that moment, and the response trigger also refuses a second author for one
section-week, under an advisory lock so two writers cannot race past it. The
staff-name definer answers a response's author, so without the first check the
connection every screen runs on could make it answer any person's name.

Written in the `models/report.py` style: text plus a `CHECK` for each closed
set, `RESTRICT` foreign keys, and `UuidPrimaryKey`.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AwareDateTime, Base, UuidPrimaryKey
from app.models.report import NOT_ONLY_WHITESPACE, _in_the_vocabulary

# The longest response text, in characters, measured as sent. One constant: the
# table's `CHECK` below is written from it, and so is every request schema that
# bounds a response (E7-02, E7-03).
RESPONSE_TEXT_MAX = 4000


class ResponseRole(StrEnum):
    """The role a response was written under; the value is the stored token.

    `LEAD_FACULTY` and `CHAIR` are the on-behalf roles: SPEC §5.3 has the lead
    respond for the instructor, and ruling 5 has the chair act as lead for a
    course with no lead.
    """

    INSTRUCTOR = "INSTRUCTOR"
    LEAD_FACULTY = "LEAD_FACULTY"
    CHAIR = "CHAIR"


class PolicyRole(StrEnum):
    """The role a response policy was set under. An instructor sets no policy (SPEC §5.3)."""

    LEAD_FACULTY = "LEAD_FACULTY"
    CHAIR = "CHAIR"


class PolicyMode(StrEnum):
    """Whether a response is encouraged or required for the courses a policy covers."""

    ENCOURAGED = "ENCOURAGED"
    REQUIRED = "REQUIRED"


RESPONSE_ROLES = tuple(role.value for role in ResponseRole)
POLICY_ROLES = tuple(role.value for role in PolicyRole)
POLICY_MODES = tuple(mode.value for mode in PolicyMode)


class InstructorResponse(UuidPrimaryKey, Base):
    """One published response to one section's course week, appended (SPEC §5.3).

    One response per section-week (ruling 3), held as a trail: an edit is a new
    row and the row with the largest `sequence` is the response students see.
    There is therefore deliberately no unique constraint on the section-week.
    """

    __tablename__ = "instructor_response"
    __table_args__ = (
        CheckConstraint(
            _in_the_vocabulary("role", RESPONSE_ROLES),
            name="role_is_a_responding_role",
        ),
        CheckConstraint(
            f"length(body) <= {RESPONSE_TEXT_MAX} AND body {NOT_ONLY_WHITESPACE}",
            name="body_is_stated_and_bounded",
        ),
        # The week belongs to the section's term: two composite keys through
        # `term_id`, the pattern `response` uses (ADR 0018), in place of plain keys
        # on the two columns.
        ForeignKeyConstraint(
            ["section_id", "term_id"],
            ["section.id", "section.term_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["week_id", "term_id"],
            ["week.id", "week.term_id"],
            ondelete="RESTRICT",
        ),
        # The read every later ticket makes: this section-week's responses, latest
        # first. It also serves the staff-name definer's "who has published to this
        # section" and the write trigger's one-author check, which lead on the
        # same columns.
        Index("ix_instructor_response_section_id_week_id", "section_id", "week_id"),
    )

    section_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    # The course week, as the report keys a week (`weekly_summary.week_id`).
    week_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    # The term the section and the week must agree on. `NOT NULL`, because a
    # composite key is skipped under `MATCH SIMPLE` when any column is null.
    term_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    # `RESTRICT`, as `moderation_state.decided_by_person_id` is: deleting a member
    # of staff may not erase, or orphan, what they published to students.
    author_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    # Whether the text began as the AI draft (SPEC §5.3). `NOT NULL`: "was it
    # seeded?" has two answers.
    ai_seeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    # The order the rows were inserted in, assigned by the database (ADR 0187's
    # reasoning). `ALWAYS`, so no writer can choose a value.
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)


class ResponsePolicy(UuidPrimaryKey, Base):
    """One change to the response policy for one course, appended (SPEC §5.3, ADR 0192, ADR 0193).

    **A row covers one course, fixed when it is written** (E7-02's M2, ADR 0193).
    Lead mappings keep no history, so "who was responsible for this course when
    the week's report opened" cannot be asked afterwards; the row names the course
    instead. A setter's switch for a prefix (ruling 1) is written as one row per
    course `authz.lead_review_courses` gives them there under the role they set it
    as (`services.response_loop.record_policy`), and the policy of record for a
    section-week is the latest row by `sequence` for the section's course recorded
    by the week's report opening (`services.response_loop.policy_of_record`).

    The row still names the prefix, the person and the role it was set under,
    because that is what the setter did; the composite key holds the course
    inside that prefix, and the guard trigger holds the setter to that course.
    """

    __tablename__ = "response_policy"
    __table_args__ = (
        CheckConstraint(_in_the_vocabulary("role", POLICY_ROLES), name="role_is_a_policy_role"),
        CheckConstraint(_in_the_vocabulary("mode", POLICY_MODES), name="mode_is_a_policy_mode"),
        # The course is in the row's prefix: a composite key, as `instructor_response`
        # holds its week in its section's term.
        ForeignKeyConstraint(
            ["course_id", "prefix_id"],
            ["course.id", "course.prefix_id"],
            ondelete="RESTRICT",
        ),
        # The one read the policy is made for: the latest row for a course.
        Index("ix_response_policy_course_id_sequence", "course_id", "sequence"),
    )

    # The course this row covers (M2). `NOT NULL`: a row covering no course is a
    # switch the hold never finds.
    course_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)

    prefix_id: Mapped[UUID] = mapped_column(
        ForeignKey("prefix.id", ondelete="RESTRICT"), nullable=False
    )
    set_by_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    set_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)
