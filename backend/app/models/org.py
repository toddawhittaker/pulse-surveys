"""The containment hierarchy: institution → college → department → prefix → course → section.

SPEC §2.1 and §8. Containment drives navigation, aggregation and drill-down, and
it is deliberately **not** where purview comes from — that is the supervision
graph over role assignments (E0-09). Nothing in this module knows about roles,
and nothing here should learn about them: the moment a containment row carries a
purview fact, the two structures §2.1 keeps decoupled have quietly merged.

**What is a database constraint here, and why.** SPEC §8's containment rules are
enforced by the server rather than by anything in `app/services/`:

  - a department groups one or more prefixes, and a course belongs to exactly
    one prefix — non-nullable foreign keys, so a row that says otherwise cannot
    be written down;
  - deleting a node that still contains something is refused (`ON DELETE
    RESTRICT`) rather than cascading, because losing a department silently loses
    every course and section under it;
  - `course.level` derives from `course.lms_number` and is never set
    independently of it — a stored generated column, so no write path anywhere
    can set it and no later edit can let it drift from the number.

**A course reaches a department by exactly one path.** Through its prefix, and
there is no second reference to an ancestor on `course` — no `department_id`,
no composite key carrying one. That is not an omission: with one path the
contradictory row (a course in one department whose prefix is in another) cannot
be expressed at all, which is stronger than a constraint that refuses it.

**LMS-owned columns carry an `lms_` name prefix** — `lms_number`,
`lms_section_code`, `lms_title` — so that a write path can see from the name
alone that Pulse does not own the value (SPEC §2.1's ownership list; ADR 0014).
`level` carries no prefix: the LMS supplies the number and Pulse derives the
level, and a generated column cannot be written by anyone in any case.

**Not here, on purpose.** `section` has no term foreign key yet — `term` is
E0-06's table, and the foreign key lands with it. Section length, start and end
dates and modality derive from `lms_section_code` and are E0-07's. Relationship
attributes are left until a query needs one.
"""

from enum import StrEnum
from uuid import UUID

from sqlalchemy import Computed, Enum, ForeignKey, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CourseLevel(StrEnum):
    """The five course levels in SPEC §8's band table.

    Stored as a Postgres enum type, so the closed set is in the database rather
    than in a convention every later view has to remember.
    """

    DEV = "DEV"
    UG = "UG"
    UGGR = "UGGR"
    GR = "GR"
    DR = "DR"


# SPEC §8's bands, as the one expression that holds them. Read that section for
# the table; it is not copied here, and the arms below are in its order.
#
# Three things about this expression are load-bearing and none of them is
# obvious. All three were measured against the pinned Postgres before it was
# written — see docs/tickets/e0/.attempts/E0-05.md.
#
# **The enum cast is on every arm rather than around the whole CASE.** Postgres
# requires a generation expression to be immutable. `(CASE ... END)::course_level`
# is a run-time text→enum conversion through `enum_in`, which is only *stable*
# because enum labels can be added later, and `CREATE TABLE` refuses it with
# "generation expression is not immutable". A cast on a literal is folded at
# parse time into an enum constant, which is immutable.
#
# **The width test guards the cast, and the nesting is what makes that a
# promise.** SPEC §8: a three-digit number is valid only in 000-799 and a
# four-digit one only in 8000-9999, so width is part of the rule and not an
# accident of it. A `CASE` never evaluates an arm it does not need, so
# `lms_number::integer` is only ever reached for something already known to be
# all digits — `12A` derives NULL rather than raising. Flattened into
# `... ~ '^[0-9]{4}$' AND lms_number::integer BETWEEN ...` the same values happen
# to work today, but `AND` carries no evaluation-order guarantee.
#
# **A number in no band derives NULL, and `level` is NOT NULL**, which is what
# refuses the write. There is deliberately no second CHECK constraint restating
# the bands on `lms_number`: it would be a copy of this table that can drift from
# it, and it would refuse exactly the same set. SPEC §8 asks for the row to be
# rejected at write time, not for a particular error message.
#
# **Why it is spelled this way and not more tersely.** `>= … AND … <=` rather
# than `BETWEEN`, `'…'::text` on the patterns, an explicit `ELSE NULL::…` on
# every arm: this is the shape Postgres deparses the expression into, character
# for character once whitespace, parentheses and quotes are stripped. Alembic
# cannot alter a generated column, so its whole response to a changed generation
# expression is one crude normalised string comparison and a warning — and a
# comparison that never matches warns on every run, which is a warning nobody
# reads. Written in the server's own shape, `alembic check` is silent while the
# two agree and says so when they stop agreeing. Editing this expression means
# writing a migration and pasting the new deparse back here; `pg_get_expr` on
# `pg_attrdef` prints it. Note that `alembic check` still *exits zero* on such a
# drift — the warning is the only signal, not a gate.
COURSE_LEVEL_DERIVATION = """
CASE
    WHEN lms_number ~ '^[0-9]{3}$'::text THEN
        CASE
            WHEN lms_number::integer >= 0 AND lms_number::integer <= 99 THEN 'DEV'::course_level
            WHEN lms_number::integer >= 100 AND lms_number::integer <= 499 THEN 'UG'::course_level
            WHEN lms_number::integer >= 500 AND lms_number::integer <= 599 THEN 'UGGR'::course_level
            WHEN lms_number::integer >= 600 AND lms_number::integer <= 799 THEN 'GR'::course_level
            ELSE NULL::course_level
        END
    WHEN lms_number ~ '^[0-9]{4}$'::text THEN
        CASE
            WHEN lms_number::integer >= 8000 AND lms_number::integer <= 9999 THEN 'DR'::course_level
            ELSE NULL::course_level
        END
    ELSE NULL::course_level
END
"""


class Institution(Base):
    """The top of the containment hierarchy (SPEC §2.1).

    The academic calendar and the timezone are institution *configuration* and
    live in `app.config.Settings` (`INSTITUTION_TIMEZONE`), not here — this row
    is the node the hierarchy hangs off.
    """

    __tablename__ = "institution"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)


class College(Base):
    """A college within an institution (e.g. College of Sciences)."""

    __tablename__ = "college"
    __table_args__ = (UniqueConstraint("institution_id", "name"),)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    institution_id: Mapped[UUID] = mapped_column(
        ForeignKey("institution.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class Department(Base):
    """A department within a college. Groups one or more prefixes (SPEC §2.1)."""

    __tablename__ = "department"
    __table_args__ = (UniqueConstraint("college_id", "name"),)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    college_id: Mapped[UUID] = mapped_column(
        ForeignKey("college.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class Prefix(Base):
    """A course prefix (e.g. BIOL), belonging to exactly one department.

    **`code` is unique across the whole table**, which is what `unique=True`
    enforces — not "unique per institution", which is what an earlier draft of
    this docstring claimed. The two coincide only while exactly one
    `institution` row exists, and this schema supports more than one, since
    `college` is unique per `institution_id` rather than globally. So the
    constraint carries a **single-institution assumption**: a second institution
    with its own MATH would be refused, and that is a migration to make, not a
    surprise to discover.

    It is deliberate. Scoping to the department instead would let `BIOL` sit
    under two departments and make `BIOL 215` ambiguous — the thing "a
    department groups one or more prefixes" (SPEC §2.1) rules out — and scoping
    to the institution would need `institution_id` denormalised onto this table,
    which is the second ancestor reference this module's docstring argues
    against. See ADR 0017.
    """

    __tablename__ = "prefix"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Indexed, unlike the other containment foreign keys, because nothing else
    # covers it: `college.institution_id`, `department.college_id` and
    # `course.prefix_id` are each the leading column of a composite unique
    # constraint, so Postgres already has a usable index for a lookup by
    # parent and a second one would be dead weight. `prefix` has no composite
    # constraint, and E0-09's purview walk fetches prefixes by department.
    department_id: Mapped[UUID] = mapped_column(
        ForeignKey("department.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)


class Course(Base):
    """A course under exactly one prefix (e.g. BIOL 215).

    LMS-owned and read-only in Pulse (SPEC §2.1), which is what the `lms_` names
    say. The number is text, not an integer: `MATH 040`'s leading zero is
    significant and an integer cannot hold it (SPEC §8). `level` derives from
    it; see `COURSE_LEVEL_DERIVATION` above.

    An earlier draft justified the same choice with "`0099` and `099` are two
    different courses", which this schema does not allow: `0099` is four digits
    and four digits are valid only in `8000`-`9999`, so it is refused at write
    time. SPEC §8 uses that pair to say what a numeric comparison *would* do
    without the width rule, which is an argument for the width rule rather than
    an example of two storable courses.
    """

    __tablename__ = "course"
    __table_args__ = (UniqueConstraint("prefix_id", "lms_number"),)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    prefix_id: Mapped[UUID] = mapped_column(
        ForeignKey("prefix.id", ondelete="RESTRICT"), nullable=False
    )
    lms_number: Mapped[str] = mapped_column(Text, nullable=False)
    lms_title: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[CourseLevel] = mapped_column(
        Enum(CourseLevel, name="course_level"),
        Computed(COURSE_LEVEL_DERIVATION, persisted=True),
        nullable=False,
    )


class Section(Base):
    """A term instance of a course, identified by its LMS section code (e.g. R3WW).

    Sections belong to exactly one course and one term (SPEC §8). The course is
    here; the term foreign key arrives with the `term` table in E0-06, and so
    does the uniqueness rule that goes with it — a section code identifies a
    section within a course *and term*, and a constraint written now without the
    term column would forbid the same code recurring next term.

    Length, start and end dates and modality all derive from
    `lms_section_code` via the start-letter map (SPEC §2.2) and are E0-07's.
    """

    __tablename__ = "section"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Indexed for the same reason as `prefix.department_id`, and this is the one
    # that matters: `section` is the leaf table and it grows by a row per
    # section per term, while E0-09's purview walk fetches sections by course
    # inside a loop over the purview set. Unindexed that is a sequential scan
    # per course, which is invisible on seed data and worsens every term.
    # `college.institution_id`, `department.college_id` and `course.prefix_id`
    # get no index on purpose — each leads a composite unique constraint, which
    # already serves a lookup by parent.
    #
    # E0-06 adds `term_id` here with a composite unique constraint over
    # `(course_id, term_id, lms_section_code)`. If it lands leading with
    # `course_id`, as that ticket's scope has it, this index becomes the dead
    # weight described above and that migration should drop it.
    course_id: Mapped[UUID] = mapped_column(
        ForeignKey("course.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lms_section_code: Mapped[str] = mapped_column(String(16), nullable=False)
