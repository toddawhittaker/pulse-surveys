"""the report schema, and the stream a question asks about

Revision ID: a1e7c4b60d92
Revises: c4a8e51db9f3
Create Date: 2026-09-06 00:00:00.000000

E4-02. Everything E4 stores, before anything writes it — E3-02's pattern for
E3-02's reason: the writers are separate tickets and a separate epic, and the
schema they share is reviewed once, whole, rather than accreted one writer at a
time.

**Four tables and one column.** `weekly_summary` holds SPEC §5.1's generated
summary, one row per section, course week and stream, with the prompt version
and model id §7.4 requires of every model output. `moderation_state` holds
§5.2's lifecycle as an append-only record beside `classification` — the latest
row governs, and a comment with no row is published. `release_batch` and
`release_batch_member` hold §4's cumulative release: a batch row carrying the
one time in the design, and a membership row carrying a comment and its batch
and deliberately nothing else. `question.stream` says which of §5.1's two groups
a question asks about, which nothing in the schema said before.
`app/models/report.py` and ADRs 0145 and 0146 carry the reasoning; what follows
is what this revision does to a database.

**The order of the column's three statements is the whole risk in this file.**
`question` holds rows in every environment, and the first `CHECK` refuses a
non-workload question with no stream. So the column is added nullable, every row
is filled, and only then are the two constraints created. Created first, the
constraint aborts the upgrade against any database with a question set in it and
succeeds against an empty one — which is to say it passes CI and fails on the
machine that matters. `3f6907349751` records the same lesson about
`survey_window.term_id`, learned the same way.

**The backfill is total, and it is written by kind first and by ordinal
second.** A workload question carries no stream, whatever ordinal it sits at;
every other question carries one. §3.2's five are the ordinals the mapping is
read from — 1 and 2 ask about the instructor, 3 and 4 about the course — and the
`ELSE` limb is a different decision rather than a continuation of that mapping,
which is why it is written separately even though it happens to produce the same
token. A question outside §3.2's shape is one no record places, and `COURSE` is
the placeholder because the alternative is worse in a specific way: `INSTRUCTOR`
files an unplaced comment under a heading about a named individual. ADR 0145
records it. At the moment this revision runs there is no such row anywhere —
`scripts/seed.py` writes exactly §3.2's five and nothing else in the system
writes a question — so the placeholder is reachable only by a hand-written row
and no reader depends on the value it gives one.

**A `WHERE position IN (1, 2, 3, 4)` backfill would pass every test written
against the shipped set and abort the upgrade on any database whose question set
has ever changed.** `question_set` is versioned precisely so that a set can be a
different size (§3.2), and this suite's own fixtures write questions at other
ordinals. Totality is not a nicety here: it is the difference between an upgrade
that completes and one that leaves an operator below this revision.

**Rows in the four new tables are not preserved by the downgrade, and nothing
here pretends otherwise.** E2-16's preserve-and-restore exists for a downgrade
that narrows something a database already holds; this revision creates the
objects it drops, so a database that goes down and comes back up gets the schema
it had rather than the rows. That is the stance `c7e2a41b90f5` takes for the two
tables it creates, in its own words. `question.stream` is not preserved either,
and there is a second reason there: the upgrade's backfill is what fills the
column, so a preserve would make a round trip green while saying nothing about
the statement this revision exists to get right.

**The downgrade drops the membership table before the batch it references**, and
that ordering is not cosmetic — dropping the parent first succeeds on an empty
database and is refused on a populated one, which is precisely the case
`tests/integration/test_the_report_migration_round_trips_on_a_seeded_database.py`
runs against a seeded database rather than an empty one.

**No grants.** No application code reads or writes any of these four tables yet:
the summary's writer is E4-06, the release path is E4-04, and every moderation
writer is E6. Each grants what it spends, which keeps the privilege beside the
code that justifies it (ADR 0055) and keeps this revision from widening the
runtime role for a writer that does not exist.

**Written by hand rather than taken from autogenerate as it stands.** The
timestamp columns are `sa.DateTime(timezone=True)` spelled out, because the model
declares `AwareDateTime`, a `TypeDecorator` whose guard is a property of the
application's write path and not of the schema (ADR 0019). Constraint names come
from `op.f(...)`, the naming convention on `Base.metadata` rendering them
(`app/models/base.py`). Nothing here creates a Postgres enum type: both closed
sets and `question.stream` are `Text` plus a `CHECK`, so this revision creates no
object the two E4 revisions taking the chain slots beside it have to know about
when they are re-pointed at merge.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1e7c4b60d92"
down_revision: str | Sequence[str] | None = "c4a8e51db9f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Spelled out rather than imported from `app.models.base`, for the reason every
# other revision here gives: a migration records what was applied on the day it
# ran, and a type read from today's code would change meaning under a database
# that has already been migrated.
TIMESTAMP = sa.DateTime(timezone=True)

WEEKLY_SUMMARY = "weekly_summary"
MODERATION_STATE = "moderation_state"
RELEASE_BATCH = "release_batch"
RELEASE_BATCH_MEMBER = "release_batch_member"

MODERATION_STATE_ANSWER_INDEX = "ix_moderation_state_answer_id"

QUESTION = "question"
STREAM_COLUMN = "stream"
STREAM_AGREES_WITH_KIND = "ck_question_stream_is_absent_exactly_for_the_workload_question"
STREAM_IS_ONE_OF_TWO = "ck_question_stream_is_one_the_report_groups_by"

# The two `CHECK`s the column is held to, as the model declares them character
# for character (`app/models/survey.py`). The first is an equivalence rather than
# "a stream is required": a workload question carrying `INSTRUCTOR` would put a
# 0-40 hours figure inside the instructor's comment group and onto a chart whose
# y-scale is 1 to 5.
STREAM_AGREES_WITH_KIND_RULE = "(kind = 'workload') = (stream IS NULL)"
STREAM_IS_ONE_OF_TWO_RULE = "stream IN ('INSTRUCTOR', 'COURSE')"

# SPEC §3.2's five, by ordinal, and the fallback for anything else. Three limbs
# rather than two: the `ELSE` is a placeholder decision about rows no record
# places, and collapsing it into the `COURSE` limb above would make the two look
# like one rule and let a later edit to either change the other silently.
BACKFILL_THE_STREAMS = f"""
    UPDATE public.{QUESTION}
    SET {STREAM_COLUMN} = CASE
        WHEN kind = 'workload' THEN NULL
        WHEN position IN (1, 2) THEN 'INSTRUCTOR'
        WHEN position IN (3, 4) THEN 'COURSE'
        ELSE 'COURSE'
    END
"""


def upgrade() -> None:
    """Apply this revision: the four report tables, and the column with its two rules."""
    op.create_table(
        WEEKLY_SUMMARY,
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("week_id", sa.Uuid(), nullable=False),
        sa.Column("stream", sa.Text(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("response_count", sa.Integer(), nullable=False),
        sa.Column("themes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("generated_at", TIMESTAMP, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "response_count >= 0",
            name=op.f("ck_weekly_summary_response_count_is_not_negative"),
        ),
        sa.CheckConstraint(
            STREAM_IS_ONE_OF_TWO_RULE,
            name=op.f("ck_weekly_summary_stream_is_one_the_report_groups_by"),
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["section.id"],
            name=op.f("fk_weekly_summary_section_id_section"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["week_id"],
            ["week.id"],
            name=op.f("fk_weekly_summary_week_id_week"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weekly_summary")),
        sa.UniqueConstraint(
            "section_id",
            "week_id",
            "stream",
            name=op.f("uq_weekly_summary_section_id_week_id_stream"),
        ),
    )
    op.create_table(
        MODERATION_STATE,
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("decided_at", TIMESTAMP, server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "state IN ('PUBLISHED', 'FLAGGED_COLLAPSED', 'EXCLUDED', 'KEPT')",
            name=op.f("ck_moderation_state_state_is_in_the_lifecycle_vocabulary"),
        ),
        sa.ForeignKeyConstraint(
            ["answer_id"],
            ["answer.id"],
            name=op.f("fk_moderation_state_answer_id_answer"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_moderation_state")),
    )
    # No unique over `answer_id`, deliberately: the record is append-only and one
    # comment carries a decision trail. The index serves the read every reader
    # makes of it — this comment's decisions, newest first.
    op.create_index(
        op.f(MODERATION_STATE_ANSWER_INDEX), MODERATION_STATE, ["answer_id"], unique=False
    )
    op.create_table(
        RELEASE_BATCH,
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("term_id", sa.Uuid(), nullable=False),
        sa.Column("cut_at", TIMESTAMP, server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["section.id"],
            name=op.f("fk_release_batch_section_id_section"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["term_id"],
            ["term.id"],
            name=op.f("fk_release_batch_term_id_term"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_release_batch")),
    )
    # A comment, the batch it went out in, and no time of its own. The unique is
    # on `answer_id` alone — a comment is released at most once, and a batch is a
    # set.
    op.create_table(
        RELEASE_BATCH_MEMBER,
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["answer_id"],
            ["answer.id"],
            name=op.f("fk_release_batch_member_answer_id_answer"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["release_batch.id"],
            name=op.f("fk_release_batch_member_batch_id_release_batch"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_release_batch_member")),
        sa.UniqueConstraint("answer_id", name=op.f("uq_release_batch_member_answer_id")),
    )

    # Nullable, then filled, then constrained — see this file's docstring for why
    # the order is the whole risk in it.
    op.add_column(QUESTION, sa.Column(STREAM_COLUMN, sa.Text(), nullable=True))
    op.execute(BACKFILL_THE_STREAMS)
    op.create_check_constraint(op.f(STREAM_AGREES_WITH_KIND), QUESTION, STREAM_AGREES_WITH_KIND_RULE)
    op.create_check_constraint(op.f(STREAM_IS_ONE_OF_TWO), QUESTION, STREAM_IS_ONE_OF_TWO_RULE)


def downgrade() -> None:
    """Reverse this revision: the column and its rules gone, the four tables gone.

    The exact reverse of the upgrade, and two orderings are load-bearing rather
    than tidy. The two `CHECK`s are dropped before the column they are written
    over, because dropping a column takes its constraints with it and a later
    `DROP CONSTRAINT` naming one of them is then an error rather than a no-op.
    And `release_batch_member` is dropped before `release_batch`: the other order
    succeeds on an empty database and is refused by the foreign key on a
    populated one.
    """
    op.drop_constraint(op.f(STREAM_IS_ONE_OF_TWO), QUESTION, type_="check")
    op.drop_constraint(op.f(STREAM_AGREES_WITH_KIND), QUESTION, type_="check")
    op.drop_column(QUESTION, STREAM_COLUMN)

    op.drop_table(RELEASE_BATCH_MEMBER)
    op.drop_table(RELEASE_BATCH)
    op.drop_index(op.f(MODERATION_STATE_ANSWER_INDEX), table_name=MODERATION_STATE)
    op.drop_table(MODERATION_STATE)
    op.drop_table(WEEKLY_SUMMARY)
