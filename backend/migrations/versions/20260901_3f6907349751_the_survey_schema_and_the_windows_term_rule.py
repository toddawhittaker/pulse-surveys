"""the survey schema, and the window's term rule

Revision ID: 3f6907349751
Revises: d2f6a913c47e
Create Date: 2026-09-01 00:00:00.000000

E2-05. Two things travel together because they are one ticket's schema: SPEC
§8's four survey tables, and the rule ADR 0018 named as available to
`survey_window` and deferred to E2.

**The four tables.** `question_set` and `question` hold SPEC §3.2's instrument —
the versioned set, the five questions of v1, and the two rules that section
states in prose carried as data a form can read. `response` and `answer` hold
what students submit: one response per student per section per week (§8), and
one answer per question of a response, holding exactly one of three values.

**`response` has no server default on either submission timestamp**, and that is
a criterion of this ticket rather than an omission. E2-08 writes both through
E2-04's clock service; a `now()` here would win silently on any insert that left
the column out, making the server's wall clock the writer of record.
`tests/integration/test_survey_schema.py` asks `information_schema.columns` the
question over the live table rather than reading the model.

**`answer` carries no range check on its three value columns**, deliberately.
SPEC §3.2's ranges are data on `question`, a `CHECK` cannot read another table,
and a copy of the range here would be a second rule that can disagree with the
first. `docs/adr/0110-answer-values-are-validated-by-the-write-path.md` records
the decision, the composite-foreign-key alternative it rejects, and what it
costs.

**The window's term rule.** `survey_window` gains a `term_id`, `section` and
`week` each gain `UNIQUE (id, term_id)`, and the two plain foreign keys become
composite ones — `(section_id, term_id)` into `section (id, term_id)` and
`(week_id, term_id)` into `week (id, term_id)`. A window pairing a section in one
term with a week in another is then refused by one limb or the other. `term_id`
is `NOT NULL` because Postgres evaluates a composite foreign key under `MATCH
SIMPLE`, which skips the check entirely when any key column is null: a nullable
column would be a way around the rule this revision exists to add.

**The new column needs no backfill and no server default.** `survey_window` is
empty in every environment — nothing writes a window until E2-06 — so the column
is added `NOT NULL` in one statement. A revision run against a database that
somehow held a window row would fail loudly on that statement, which is the
right outcome: there would be no term to fill in.

**Written by hand rather than taken from autogenerate as it stands.** The
timestamp columns are `sa.DateTime(timezone=True)` spelled out, because the model
declares `AwareDateTime`, a `TypeDecorator` whose guard is a property of the
application's write path and not of the schema (ADR 0019) — the DDL it emits is
exactly this, and `alembic check` compares the compiled type, so the two stay in
step. The enum type is bound to a name so the downgrade has an object to drop:
`op.drop_table` leaves a type behind, and a second `upgrade()` would then fail on
a type that already exists.

Every constraint name comes from `op.f(...)`, which is the naming convention on
`Base.metadata` rendering it. None is hand-written; see `app/models/base.py`.

**No grants.** No application code reads or writes these four tables yet — this
ticket is schema, a seed and nothing else — so `pulse_app` is given nothing on
them here. E2-08 and E2-09 each grant what their path needs, which keeps the
privilege beside the code that justifies it (ADR 0055).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f6907349751"
down_revision: str | Sequence[str] | None = "d2f6a913c47e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Spelled out rather than imported from `app.models.base`, for the reason every
# other revision here gives: a migration records what was applied on the day it
# ran, and a type read from today's code would change meaning under a database
# that has already been migrated.
TIMESTAMP = sa.DateTime(timezone=True)

# SPEC §3.2's three answer shapes, as the labels this revision created. Bound to
# a name because the type is made as a side effect of the column below and the
# downgrade needs an object to call `.drop()` on.
QUESTION_KIND = sa.Enum("likert", "comment", "workload", name="question_kind")

# Three digits and one decimal place, which is what §3.2's two ranges need: a
# Likert 1 to 5, and a workload slider running 0 to 40 in half hours.
VALUE = sa.Numeric(precision=4, scale=1)

# The uniques the window's two composite foreign keys reference. Each is
# redundant beside its table's primary key and is required all the same: a
# foreign key must reference a unique constraint, so without these the composite
# limbs cannot be created at all.
SECTION_TERM_UNIQUE = "uq_section_id_term_id"
WEEK_TERM_UNIQUE = "uq_week_id_term_id"

# The two plain foreign keys this revision replaces, as E0-06's revision named
# them, and the composite ones that take their place.
SECTION_FK = "fk_survey_window_section_id_section"
WEEK_FK = "fk_survey_window_week_id_week"
SECTION_TERM_FK = "fk_survey_window_section_id_term_id_section"
WEEK_TERM_FK = "fk_survey_window_week_id_term_id_week"


def upgrade() -> None:
    """Apply this revision: the four survey tables, then the window's term rule."""
    op.create_table(
        "question_set",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version >= 1", name=op.f("ck_question_set_version_is_at_least_one")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_set")),
        sa.UniqueConstraint("version", name=op.f("uq_question_set_version")),
    )

    op.create_table(
        "question",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("question_set_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", QUESTION_KIND, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("required_if_position", sa.Integer(), nullable=True),
        sa.Column("required_if_at_most", sa.Integer(), nullable=True),
        sa.Column("minimum_value", VALUE, nullable=True),
        sa.Column("maximum_value", VALUE, nullable=True),
        sa.Column("step", VALUE, nullable=True),
        sa.CheckConstraint(
            "maximum_value > minimum_value AND step > 0",
            name=op.f("ck_question_bounds_are_ordered"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(minimum_value, maximum_value, step) IN (0, 3)",
            name=op.f("ck_question_bounds_are_whole"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(required_if_position, required_if_at_most) IN (0, 2)",
            name=op.f("ck_question_conditional_rule_is_whole"),
        ),
        sa.CheckConstraint("position >= 1", name=op.f("ck_question_position_is_at_least_one")),
        sa.ForeignKeyConstraint(
            ["question_set_id"],
            ["question_set.id"],
            name=op.f("fk_question_question_set_id_question_set"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question")),
        sa.UniqueConstraint(
            "question_set_id", "position", name=op.f("uq_question_question_set_id_position")
        ),
    )

    op.create_table(
        "response",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("week_id", sa.Uuid(), nullable=False),
        sa.Column("first_submitted_at", TIMESTAMP, nullable=False),
        sa.Column("last_submitted_at", TIMESTAMP, nullable=False),
        sa.CheckConstraint(
            "last_submitted_at >= first_submitted_at",
            name=op.f("ck_response_last_submission_is_not_before_the_first"),
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["section.id"],
            name=op.f("fk_response_section_id_section"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_response_user_id_user"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["week_id"], ["week.id"], name=op.f("fk_response_week_id_week"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_response")),
        sa.UniqueConstraint(
            "user_id",
            "section_id",
            "week_id",
            name=op.f("uq_response_user_id_section_id_week_id"),
        ),
    )
    op.create_index(
        "ix_response_section_id_week_id", "response", ["section_id", "week_id"], unique=False
    )
    op.create_index(op.f("ix_response_week_id"), "response", ["week_id"], unique=False)

    op.create_table(
        "answer",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("response_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("comment_text", sa.Text(), nullable=True),
        sa.Column("workload_hours", VALUE, nullable=True),
        sa.CheckConstraint(
            "num_nonnulls(rating, comment_text, workload_hours) = 1",
            name=op.f("ck_answer_holds_exactly_one_value"),
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["question.id"],
            name=op.f("fk_answer_question_id_question"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["response_id"],
            ["response.id"],
            name=op.f("fk_answer_response_id_response"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answer")),
        sa.UniqueConstraint(
            "response_id", "question_id", name=op.f("uq_answer_response_id_question_id")
        ),
    )

    # ADR 0018's rule, in the order the server needs it: the referenced uniques
    # first, then the column that carries the term, then the limbs. The plain
    # foreign keys go last, after the composite ones that replace them, so there
    # is no moment inside this transaction when a window's section or week is
    # unreferenced.
    op.create_unique_constraint(SECTION_TERM_UNIQUE, "section", ["id", "term_id"])
    op.create_unique_constraint(WEEK_TERM_UNIQUE, "week", ["id", "term_id"])
    op.add_column("survey_window", sa.Column("term_id", sa.Uuid(), nullable=False))
    op.create_foreign_key(
        SECTION_TERM_FK,
        "survey_window",
        "section",
        ["section_id", "term_id"],
        ["id", "term_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        WEEK_TERM_FK,
        "survey_window",
        "week",
        ["week_id", "term_id"],
        ["id", "term_id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(SECTION_FK, "survey_window", type_="foreignkey")
    op.drop_constraint(WEEK_FK, "survey_window", type_="foreignkey")


def downgrade() -> None:
    """Reverse this revision: the window back to two plain keys, the four tables gone.

    A true reversal in both halves. `survey_window` is left holding exactly the
    constraints and columns `216896354431` gave it, and the four tables and the
    `question_kind` type are gone — the type needs dropping by hand, because
    `op.drop_table` leaves it behind and a second `upgrade()` would then fail on
    a type that already exists.

    The tables are dropped children first: every foreign key here is `RESTRICT`,
    so dropping `question_set` before `question` would be refused.
    """
    op.create_foreign_key(
        SECTION_FK, "survey_window", "section", ["section_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        WEEK_FK, "survey_window", "week", ["week_id"], ["id"], ondelete="RESTRICT"
    )
    op.drop_constraint(SECTION_TERM_FK, "survey_window", type_="foreignkey")
    op.drop_constraint(WEEK_TERM_FK, "survey_window", type_="foreignkey")
    op.drop_column("survey_window", "term_id")
    op.drop_constraint(WEEK_TERM_UNIQUE, "week", type_="unique")
    op.drop_constraint(SECTION_TERM_UNIQUE, "section", type_="unique")

    op.drop_table("answer")
    op.drop_index(op.f("ix_response_week_id"), table_name="response")
    op.drop_index("ix_response_section_id_week_id", table_name="response")
    op.drop_table("response")
    op.drop_table("question")
    op.drop_table("question_set")
    QUESTION_KIND.drop(op.get_bind())
