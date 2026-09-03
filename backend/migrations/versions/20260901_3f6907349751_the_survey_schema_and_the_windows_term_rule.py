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

**The new column is backfilled, and the sentence this paragraph used to carry was
false by the time it was written.** It read that `survey_window` "is empty in
every environment — nothing writes a window until E2-06 — so the column is added
`NOT NULL` in one statement". E2-06 landed and windows have been stored ever
since: the development database held 188 of them when the E2 boundary review
measured this revision, and adding the column `NOT NULL` in one statement aborts
with a `NotNullViolation` on every one of them. So the column is added nullable,
filled from `section.term_id` — which is `NOT NULL` and covers every window,
because a window's section is what its term has to agree with anyway — and only
then made `NOT NULL`.

**The downgrade preserves what is not derivable, and the upgrade restores it**
(E2-16, the same house pattern `b8c41f7d2e05` is the worked example of).
`question_set`, `question`, `response` and `answer` are dropped whole, taking
every stored submission with them, and nothing left behind can reconstruct one —
so each is copied into a scratch table first and put back by the upgrade, keyed by
the row's own primary key. A down-and-up trip is then an identity rather than a
data loss followed by a plausible-looking migration.

**`survey_window.term_id` is the column that is *not* preserved, and the
distinction is the rule rather than an exception to it.** The composite foreign
key this revision adds makes a window's term its section's term, so the backfill
above computes exactly what a preserve would have carried — the two are the same
value for every row that can exist at head. Both were written at first, and the
E2-16 mutation battery measured what that cost: deleting either one alone left
every round-trip test green, because the other silently covered for it. One
guarantee held in two places is a guarantee neither place holds. The backfill
stays and the preserve is gone, which is the test `b1e7d4a90c26` states for the
same column on `response` — a preserve is owed for what cannot be recomputed, and
for nothing else.

**Both halves are edits to this revision rather than a new one, deliberately.**
A later revision can add a column, and it cannot repair a `downgrade()` — the
broken path *is* this file's, and it is the one a new revision could never be
reached through. What has already run everywhere is this revision's `upgrade()`
against an empty database, where every backfill and every restore below is a
no-op; CI builds from empty for the same reason. So the edit changes nothing that
has happened and repairs the two paths that have never run anywhere: the
downgrade, and the re-upgrade after one.

**Written by hand rather than taken from autogenerate as it stands.** The
timestamp columns are `sa.DateTime(timezone=True)` spelled out, because the model
declares `AwareDateTime`, a `TypeDecorator` whose guard is a property of the
application's write path and not of the schema (ADR 0019) — the DDL it emits is
exactly this, and `alembic check` compares the compiled type, so the two stay in
step. The enum type is bound to a name so the downgrade has an object to drop:
`op.drop_table` leaves a type behind, and a second `upgrade()` would then fail on
a type that already exists.

Constraint names on the four new tables come from `op.f(...)`, the naming
convention on `Base.metadata` rendering them (`app/models/base.py`). The six
names in the constants below are hand-written — the two referenced uniques and
the four foreign-key names on `survey_window`, where this revision replaces
constraints another revision created — and each is spelled to match the same
convention character for character, which `alembic check` keeps honest.

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

# ---------------------------------------------------------------------------
# What the downgrade keeps, and where. None of these tables is in
# `Base.metadata` and none is meant to be: each exists only between a downgrade
# and the upgrade that restores from it, and the upgrade drops it — so a database
# standing at head never has one and `alembic check` never sees it.
# ---------------------------------------------------------------------------

# The four tables the downgrade drops whole, in the order rows have to be put
# back: a parent before the child that references it. Each entry is the table, the
# columns a row is restored into, the expressions the preserve reads, and the
# expressions the restore writes — three lists rather than one because
# `question.kind` cannot be carried as it stands.
#
# **`question.kind` is preserved as text and cast back.** A scratch table holding
# a `question_kind` column is a column using the type, and the `DROP TYPE` at the
# end of `downgrade` is refused while any column uses it. Casting is not a
# convenience here: without it the downgrade fails on its last statement, having
# already dropped the four tables.
_QUESTION_SET_COLUMNS = "id, version"
_QUESTION_COLUMNS = (
    "id, question_set_id, position, kind, name, prompt, required_if_position, "
    "required_if_at_most, minimum_value, maximum_value, step"
)
_QUESTION_PRESERVED_COLUMNS = (
    "id, question_set_id, position, kind::text AS kind, name, prompt, required_if_position, "
    "required_if_at_most, minimum_value, maximum_value, step"
)
_QUESTION_RESTORED_COLUMNS = (
    "id, question_set_id, position, kind::question_kind, name, prompt, required_if_position, "
    "required_if_at_most, minimum_value, maximum_value, step"
)
# `response`'s column list is this revision's own and stops there. `is_valid`
# (`f1a3c7d02b64`) and `term_id` (`b1e7d4a90c26`) are added by later revisions and
# are therefore already gone by the time this downgrade runs — each of those
# revisions answers for its own column.
_RESPONSE_COLUMNS = "id, user_id, section_id, week_id, first_submitted_at, last_submitted_at"
_ANSWER_COLUMNS = "id, response_id, question_id, rating, comment_text, workload_hours"

DROPPED_WHOLE = (
    ("question_set", _QUESTION_SET_COLUMNS, _QUESTION_SET_COLUMNS, _QUESTION_SET_COLUMNS),
    ("question", _QUESTION_COLUMNS, _QUESTION_PRESERVED_COLUMNS, _QUESTION_RESTORED_COLUMNS),
    ("response", _RESPONSE_COLUMNS, _RESPONSE_COLUMNS, _RESPONSE_COLUMNS),
    ("answer", _ANSWER_COLUMNS, _ANSWER_COLUMNS, _ANSWER_COLUMNS),
)


def _preserved_name(table: str) -> str:
    """Where one dropped table's rows wait between a downgrade and the upgrade."""
    return f"{table}_preserved"


def _preserve_the_dropped_tables() -> str:
    """Copy every row of the four tables this revision created, before they are dropped.

    `DROP TABLE IF EXISTS` first, for `b8c41f7d2e05`'s reason: the upgrade drops
    these on the way out, so an ordinary down-up-down-up journey meets nothing —
    but a journey where the upgrade did not run, or did not finish, would otherwise
    fail on `CREATE TABLE` or leave a second copy of every row beside the first,
    and the operator would find out on the trip after the one that went wrong.
    """
    statements = []
    for table, _restore_into, preserved, _restored in DROPPED_WHOLE:
        kept = _preserved_name(table)
        statements.append(
            f"DROP TABLE IF EXISTS public.{kept};\n"
            f"CREATE TABLE public.{kept} AS SELECT {preserved} FROM public.{table};"
        )
    return "\n".join(statements)


def _restore_the_dropped_tables() -> str:
    """Put every preserved row back, parents first, and take the scratch tables away.

    One PL/pgSQL block for `b8c41f7d2e05`'s reason: `alembic upgrade --sql` has to
    carry this, and it has to do the right thing on a database that never went
    down, where the scratch tables are simply absent. `to_regclass` answers NULL
    for a table that is not there rather than raising, which is what makes that
    check a branch instead of an error.
    """
    body = []
    for table, restore_into, _preserved, restored in DROPPED_WHOLE:
        kept = _preserved_name(table)
        body.append(
            f"    IF to_regclass('public.{kept}') IS NOT NULL THEN\n"
            f"        INSERT INTO public.{table} ({restore_into})\n"
            f"        SELECT {restored} FROM public.{kept};\n"
            f"        DROP TABLE public.{kept};\n"
            f"    END IF;"
        )
    return "DO $$\nBEGIN\n" + "\n".join(body) + "\nEND\n$$;"


# Every window takes its section's term, and this is the **only** mechanism that
# fills the column — there is no preserve beside it and there must not be.
#
# **Why a preserve would be dead code here.** The composite foreign key created
# three statements later says a window's term is its section's term, so for every
# row that can exist at head the two values are the same value. A scratch table
# holding what the downgrade dropped would therefore always be restoring exactly
# what this statement computes — which the E2-16 mutation battery measured: with
# both in place, deleting either one alone kept every round-trip test green, and
# only deleting both together reddened them. That is one guarantee held in two
# places, so neither is held by anything.
#
# It is the backfill that stays, rather than the preserve, because a preserve is
# owed only for what is **not** derivable — the test `b1e7d4a90c26` states and
# applies to `response.term_id`, and this revision now applies to the same column
# on `survey_window`. `response`, `answer`, `question_set` and `question` are
# preserved below precisely because nothing left behind can reconstruct them.
#
# **And where the two would disagree, the backfill is the right one.** If a
# section's term is edited while the database sits at the older revision, a
# preserved value would put the window in a term its section is no longer in, and
# the composite key three statements later would refuse the upgrade; the section's
# own term is correct for the state the database is actually in.
#
# `section.term_id` is `NOT NULL` (E0-06) and every window references a section, so
# this covers every row — verified against the development database's 188 windows,
# which is where the abort this replaces was measured. The strand test in
# `tests/integration/test_the_survey_schema_survives_a_downgrade.py` is what holds
# it: remove this statement and the re-upgrade aborts on the `NOT NULL` below.
BACKFILL_THE_WINDOW_TERMS = """
UPDATE public.survey_window AS w
   SET term_id = s.term_id
  FROM public.section AS s
 WHERE s.id = w.section_id
   AND w.term_id IS NULL
"""


def upgrade() -> None:
    """Apply this revision: the four survey tables, then the window's term rule.

    **The restore comes after the four tables and before anything reads them**,
    and it is a no-op on a database that has never been downgraded — the scratch
    tables are simply not there, which is every database this revision has
    actually run against, CI's included.

    **The window's term is backfilled and not restored**, and that is a
    distinction rather than an omission: it is derivable from the section, so
    there is nothing for a preserve to carry that the backfill does not compute.
    See `BACKFILL_THE_WINDOW_TERMS`.
    """
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

    op.execute(_restore_the_dropped_tables())

    # ADR 0018's rule, in the order the server needs it: the referenced uniques
    # first, then the column that carries the term, then the limbs. The plain
    # foreign keys go last, after the composite ones that replace them, so there
    # is no moment inside this transaction when a window's section or week is
    # unreferenced.
    op.create_unique_constraint(SECTION_TERM_UNIQUE, "section", ["id", "term_id"])
    op.create_unique_constraint(WEEK_TERM_UNIQUE, "week", ["id", "term_id"])
    # Added nullable, filled, then made NOT NULL. Adding it NOT NULL in one
    # statement is what stranded a database holding windows; see this revision's
    # docstring.
    op.add_column("survey_window", sa.Column("term_id", sa.Uuid(), nullable=True))
    op.execute(BACKFILL_THE_WINDOW_TERMS)
    op.alter_column("survey_window", "term_id", nullable=False)
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

    **Nothing that cannot be recomputed is discarded.** Every row of the four
    tables is copied into a scratch table first and put back by `upgrade`. A
    downgrade here used to lose every stored submission outright, and the
    re-upgrade then re-added `term_id` `NOT NULL` over windows it could not fill —
    so the database was stranded below every revision E2 added, with the responses
    already gone. The scratch tables stay while the database sits at the older
    revision, which is where those rows live in the meantime; the upgrade is the
    only thing that removes them.

    **`survey_window.term_id` is deliberately not among them.** It is dropped and
    not kept, because the composite foreign key this revision adds makes it the
    section's term — so `upgrade`'s backfill computes exactly what a preserve
    would have carried, and a second copy of one guarantee is a guarantee neither
    copy holds. `BACKFILL_THE_WINDOW_TERMS` carries the measurement that showed it.
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

    op.execute(_preserve_the_dropped_tables())
    op.drop_table("answer")
    op.drop_index(op.f("ix_response_week_id"), table_name="response")
    op.drop_index("ix_response_section_id_week_id", table_name="response")
    op.drop_table("response")
    op.drop_table("question")
    op.drop_table("question_set")
    QUESTION_KIND.drop(op.get_bind())
