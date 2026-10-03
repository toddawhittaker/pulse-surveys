"""the comparison set and its membership

Revision ID: b4d7e2a91c58
Revises: e5a2b81c47d3
Create Date: 2026-09-13 00:00:00.000000

E5-01. SPEC §5.1 lets leadership "define named sets" beside the default
comparison set, which is computed rather than stored (§13). This revision builds
the stored half: `comparison_set`, declaring one length and one level, and
`comparison_set_member`, one course in one set. `app/models/benchmark.py` and
ADR 0164 carry the reasoning; what follows is what this revision does to a
database.

**Three rules, all of them the database's.** The declared length is one of SPEC
§2.2's eight — "3, 6, 8, 10, 12, 15, 16 (plus an 18-week dissertation length)" —
written out rather than as a range, because the set has interior gaps and a
17-week set is a benchmark nothing can ever resolve. The declared level is one of
SPEC §8's five, held by the **existing** `course_level` enumerated type rather
than by a second type spelling the same labels. And a member course's level
equals the set's declared level, which is SPEC §5.1's exact match — "levels match
**exactly**; no level is folded into another".

**How the cross-table level rule is held.** A `CHECK` cannot read another table
(ADR 0018), so the membership row carries both levels and each is held to its own
table by a composite foreign key: `(set_id, set_level)` into `comparison_set
(id, level)` and `(course_id, course_level)` into `course (id, level)`. A
`CHECK` then compares two columns of one row. The mechanism is `response`'s,
`survey_window`'s and `release_batch`'s, unchanged.

**`course` gains `UNIQUE (id, level)` for that key to reference, and it refuses
no row.** `id` is a primary key, so every pair containing it is already unique;
the constraint adds a name and an index and forbids nothing, which is what makes
this safe to add to a table every fixture in the suite seeds. `course.level` is a
**stored generated** column and Postgres accepts both the unique over it and a
foreign key referencing it — verified against Postgres 17 before this revision
was written, since a refusal there would have meant a different mechanism rather
than a workaround.

**Deletion runs in opposite directions on purpose.** Member to course is
`RESTRICT`: a set silently shrinking is a benchmark silently changing, and
because benchmarks are past-referencing (§5.1) a course removed today moves
figures that were already published. Set to member is `CASCADE`: the set is the
aggregate root, E5-06 builds the delete, and a membership row outliving its set
is an orphan pointing at nothing.

**This revision adds no grant.** `pulse_app` holds no privilege on either table.
The first reader is E5-04 and the first writer is E5-06, and each grants what it
spends in its own change — E4-02's precedent, quoted in
`weekly_summary_grants_v001.sql`. A privilege that arrives before the change that
uses it is a privilege no reviewer ever weighed.

**The downgrade drops both tables, and every named set with them.** Both
tables are created by this revision, so going down removes them and their rows,
and coming back up creates them empty: a database walked down past this revision
and up again has lost every set leadership defined. Corrected at E5-14 from a
sentence that called this a true reversal. The order is the upgrade's in
reverse: the membership table first, then the set, then the unique constraint
`course` did not have before. The `course_level` type is
**not** dropped — it is E0-05's and `course.level` is typed against it, so
dropping it here would take that column with it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b4d7e2a91c58"
down_revision: str | Sequence[str] | None = "e5a2b81c47d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMPARISON_SET = "comparison_set"
MEMBER = "comparison_set_member"
COURSE = "course"

TIMESTAMP = sa.DateTime(timezone=True)

# The type E0-05 created, referenced and not created again: `create_type=False`
# is what keeps `op.create_table` from emitting a second `CREATE TYPE
# course_level` and aborting the upgrade.
COURSE_LEVEL = postgresql.ENUM(
    "DEV", "UG", "UGGR", "GR", "DR", name="course_level", create_type=False
)

# SPEC §2.2's eight lengths. Duplicated from `CALENDAR_LENGTHS` in
# `app/models/benchmark.py` on purpose and for the reason `COURSE_LEVEL_DERIVATION`
# gives in `8e376cdecc3b`: a migration is a historical record of what was applied
# and must not change when the model does.
LENGTH_IS_A_CALENDAR_LENGTH = "length_weeks IN (3, 6, 8, 10, 12, 15, 16, 18)"

# The unique `course` gains, named the way the convention on `Base.metadata`
# renders it, so `alembic check` compares the declaration against the database
# and finds nothing.
COURSE_ID_LEVEL_UNIQUE = "uq_course_id_level"


def upgrade() -> None:
    """Apply this revision: the unique `course` needs, then the two tables."""
    op.create_unique_constraint(op.f(COURSE_ID_LEVEL_UNIQUE), COURSE, ["id", "level"])

    op.create_table(
        COMPARISON_SET,
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("length_weeks", sa.Integer(), nullable=False),
        sa.Column("level", COURSE_LEVEL, nullable=False),
        sa.Column("created_by_person_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", TIMESTAMP, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TIMESTAMP, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            LENGTH_IS_A_CALENDAR_LENGTH,
            name=op.f("ck_comparison_set_length_is_a_calendar_length"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_person_id"],
            ["person.id"],
            name=op.f("fk_comparison_set_created_by_person_id_person"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comparison_set")),
        sa.UniqueConstraint("id", "level", name=op.f("uq_comparison_set_id_level")),
        sa.UniqueConstraint("name", name=op.f("uq_comparison_set_name")),
    )
    op.create_table(
        MEMBER,
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("set_id", sa.Uuid(), nullable=False),
        sa.Column("set_level", COURSE_LEVEL, nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("course_level", COURSE_LEVEL, nullable=False),
        sa.CheckConstraint(
            "set_level = course_level",
            name=op.f("ck_comparison_set_member_the_levels_agree"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id", "course_level"],
            ["course.id", "course.level"],
            name=op.f("fk_comparison_set_member_course_id_course_level_course"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["set_id", "set_level"],
            ["comparison_set.id", "comparison_set.level"],
            name=op.f("fk_comparison_set_member_set_id_set_level_comparison_set"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comparison_set_member")),
        sa.UniqueConstraint(
            "set_id", "course_id", name=op.f("uq_comparison_set_member_set_id_course_id")
        ),
    )


def downgrade() -> None:
    """Reverse this revision: both tables, then the unique `course` did not have.

    The membership table goes first because its keys hold `comparison_set` and
    `course` in place. The `course_level` type stays: it is E0-05's and
    `course.level` is typed against it.
    """
    op.drop_table(MEMBER)
    op.drop_table(COMPARISON_SET)
    op.drop_constraint(op.f(COURSE_ID_LEVEL_UNIQUE), COURSE, type_="unique")
