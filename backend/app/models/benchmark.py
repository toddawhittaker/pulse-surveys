"""The comparison set — a cohort leadership names, and the courses in it (SPEC §13).

SPEC §5.1 lets leadership "define named sets" beside the default comparison set,
which is computed rather than stored. This module holds the stored half: a named
set that declares **one length and one level**, and a membership list of courses
of that level. Resolution — which sections a set actually produces, in this term
and prior ones — is E5-04's and lives in a service; nothing here computes
anything.

**Why the pair is declared on the set rather than derived from its members.**
SPEC §5.1 makes comparability an exact match on both length and level, and a
section's length is a property of the *section* rather than of the course: one
course runs 6-week and 12-week sections in the same term. So a set that named
only courses would leave the length unstated, and resolution would have to guess
it. The set declares the pair once, membership is held to the level half of it,
and E5-04 selects member courses' sections of the declared length.

**Why membership is at course grain.** Benchmarks are past-referencing (SPEC
§5.1: week N is compared against prior terms as well as the current one), and a
section exists in exactly one term. A set of sections would therefore age out
every term and leadership would rebuild it each time; a set of courses keeps
meaning as terms come and go. ADR 0164 records the choice and what it costs.

**Every rule here is a database rule, and that is the ticket's point.** The
length is at least one week, the level is one of SPEC §8's five, and a member
course's level equals the set's declared level — all three refused by
Postgres rather than by a route, because a route is one caller among the several
that will exist by the time E5-06 and E5-09 are built. The level agreement is
held the way `response` and `release_batch` hold theirs: a composite foreign key,
because a `CHECK` cannot read another table (ADR 0018).

**Each grant on these tables arrived with the ticket that spends it** — E4-02's
precedent. E5-01 granted `pulse_app` nothing; E5-04 granted the read and E5-06
the writes, and E5-14 narrowed `UPDATE` on the set table to the four columns an
edit writes. `tests/integration/test_the_comparison_set_tables_are_refused_
to_the_application_connection.py` drives each grant, and each withheld one, on
the connection production opens.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AwareDateTime, Base, UuidPrimaryKey
from app.models.org import CourseLevel

# A declared length is any whole number of weeks from one up, the rule
# `section.length_weeks` is held to. It was SPEC §2.2's eight calendar lengths
# written out until E5-14: the owner ruled that a set's length is data, because
# §2.2 makes the calendar configuration, so a length a section can have is a
# length a set can declare. `definition_options` offers the lengths sections
# actually have. ADR 0164's length paragraph is superseded on this point.
LENGTH_IS_AT_LEAST_ONE_WEEK = "length_weeks >= 1"

# A name is what a set is chosen by on every later surface, so one that is empty
# once its spaces are trimmed is a set nobody can pick out of a list. The request
# schema strips the spaces before the write; this is the rule underneath it.
NAME_IS_NOT_BLANK = "btrim(name) <> ''"


class ComparisonSet(UuidPrimaryKey, Base):
    """A named cohort: one declared length, one declared level, and a list of courses.

    **The name is unique across the table** rather than per anything. A
    deployment serves exactly one institution (SPEC §8), and two sets sharing a
    name are two cohorts nobody can tell apart in E5-06's list or E5-09's form.

    **`(id, level)` is unique too**, which reads redundantly and is not: it is
    what `comparison_set_member`'s composite key references, and a composite
    foreign key needs a unique constraint over exactly the columns it names.
    Adding it costs nothing and forbids nothing — `id` is already unique, so the
    pair is unique for free.

    **A set may be empty.** A set under construction has no members yet, and
    E5-06 creates one before anything is added to it. What an empty set *means*
    when it is resolved is E5-04's: suppressed, like any set below the benchmark
    minimum (SPEC §4.1 item 7).

    **The creator is a foreign key to `person` and nothing more**, the actor
    convention `audit_log` already uses. `RESTRICT`, as every other reference to
    `person` is: deleting somebody out of the people graph must not silently
    delete the record of who defined a benchmark. No name is copied onto this
    row, so `tests/integration/test_identity_column_marker.py` records the table
    as carrying nothing.
    """

    __tablename__ = "comparison_set"
    __table_args__ = (
        UniqueConstraint("name"),
        # Referenced by `comparison_set_member`'s composite key. See the class
        # docstring: `id` is already unique, so this forbids nothing.
        UniqueConstraint("id", "level"),
        CheckConstraint(LENGTH_IS_AT_LEAST_ONE_WEEK, name="length_weeks_is_at_least_one"),
        CheckConstraint(NAME_IS_NOT_BLANK, name="name_is_not_blank"),
    )

    # What leadership calls the cohort — "College of Nursing, 6-week
    # undergraduate". It describes courses and never a person, which is why it is
    # the one entry in `NAMES_THAT_HOLD_NO_PERSON`: the sweep recognises the word
    # `name`, and marking this column would forbid the read SPEC §5.1 requires of
    # every surface that offers a named set.
    name: Mapped[str] = mapped_column(Text, nullable=False)
    length_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    # The **existing** `course_level` type, not a second one spelling the same
    # five labels: `course.level` is typed against it already, and two types
    # would have to be kept in step by hand.
    level: Mapped[CourseLevel] = mapped_column(
        Enum(CourseLevel, name="course_level"), nullable=False
    )
    created_by_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        AwareDateTime, nullable=False, server_default=text("now()")
    )
    # Set by whoever edits the set. A server default rather than an `onupdate`,
    # because the writer is E5-06's service and a default is what makes an insert
    # from a migration or a seed carry a value too.
    updated_at: Mapped[datetime] = mapped_column(
        AwareDateTime, nullable=False, server_default=text("now()")
    )


class ComparisonSetMember(UuidPrimaryKey, Base):
    """One course in one set, with the level both of them agree on.

    **The two level columns are denormalized on purpose and are the mechanism.**
    SPEC §5.1's exact level match is a rule *across* two tables, and a `CHECK`
    cannot read another table (ADR 0018). So the row carries the set's level and
    the course's level, each held to its own table by a composite foreign key —
    `(set_id, set_level)` into `comparison_set (id, level)` and
    `(course_id, course_level)` into `course (id, level)` — and a `CHECK` compares
    the two columns of the one row. Neither can drift: changing a set's level or
    a course's number breaks the key rather than the invariant. This is the shape
    `response` and `release_batch` already use for the section/term pairing.

    **Deleting a member course is refused; deleting the set takes its members.**
    A set silently shrinking is a benchmark silently changing — and because
    benchmarks are past-referencing, a course removed today would move figures
    already published, with nothing on the chart to say so. Deleting the set, by
    contrast, is an ordinary act: the set is the aggregate root, so its
    memberships go with it and every course stays exactly where it was. ADR 0164
    records both.

    **The unique is on the pair.** A course counted twice weights its sections
    twice in every figure the set produces, and twice in the section count the
    benchmark minimum is measured against (SPEC §4.1 item 7) — so a duplicate
    could carry a thin cohort over the minimum without adding a section to it.
    Unique on the course alone would be the opposite mistake: a course belongs to
    as many named cohorts as leadership has questions.
    """

    __tablename__ = "comparison_set_member"
    __table_args__ = (
        ForeignKeyConstraint(
            ["set_id", "set_level"],
            ["comparison_set.id", "comparison_set.level"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["course_id", "course_level"],
            ["course.id", "course.level"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("set_level = course_level", name="the_levels_agree"),
        UniqueConstraint("set_id", "course_id"),
    )

    # Referenced by the composite keys above rather than by a `ForeignKey` here,
    # exactly as `release_batch.section_id` is.
    set_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    set_level: Mapped[CourseLevel] = mapped_column(
        Enum(CourseLevel, name="course_level"), nullable=False
    )
    course_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    course_level: Mapped[CourseLevel] = mapped_column(
        Enum(CourseLevel, name="course_level"), nullable=False
    )
