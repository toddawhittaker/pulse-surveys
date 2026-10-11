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
reader only through the staff-name definer (`views_sql/section_staff_names_v001.sql`,
ADR 0191), whose reader check decides who may read it.

Written in the `models/report.py` style: text plus a `CHECK` for each closed
set, `RESTRICT` foreign keys, and `UuidPrimaryKey`.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Identity, Index, Text
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
        # The read every later ticket makes: this section-week's responses, latest
        # first. It also serves the staff-name definer's "who has published to this
        # section", which leads on the same column.
        Index("ix_instructor_response_section_id_week_id", "section_id", "week_id"),
    )

    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("section.id", ondelete="RESTRICT"), nullable=False
    )
    # The course week, as the report keys a week (`weekly_summary.week_id`).
    week_id: Mapped[UUID] = mapped_column(
        ForeignKey("week.id", ondelete="RESTRICT"), nullable=False
    )
    # `RESTRICT`, as `moderation_state.decided_by_person_id` is: deleting a member
    # of staff may not erase, or orphan, what they published to students.
    author_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), nullable=False, index=True
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
    """One change to a prefix's response policy, appended (SPEC §5.3, ADR 0192).

    Keyed by prefix and by the person responsible (ruling 1), and by the role
    they set it under: a lead's row covers the courses in the prefix that
    `authz.lead_review_courses` gives them as `LEAD_FACULTY`, and a chair's row
    the ones it gives them as `CHAIR`. The latest row for a (prefix, person,
    role) is the policy in force.
    """

    __tablename__ = "response_policy"
    __table_args__ = (
        CheckConstraint(_in_the_vocabulary("role", POLICY_ROLES), name="role_is_a_policy_role"),
        CheckConstraint(_in_the_vocabulary("mode", POLICY_MODES), name="mode_is_a_policy_mode"),
    )

    prefix_id: Mapped[UUID] = mapped_column(
        ForeignKey("prefix.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    set_by_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    set_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)
