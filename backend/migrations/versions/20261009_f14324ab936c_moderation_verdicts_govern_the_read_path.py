"""moderation verdicts govern the read path

Revision ID: f14324ab936c
Revises: ad9da2d96664
Create Date: 2026-10-09 00:00:00.000000

E6-01, ADR 0187. Until this revision a comment nobody had moderated counted as
published, and nothing wrote a moderation verdict. This revision adds:

  - the `MODERATION` member of `classification_task`, and a verdict `CHECK` on
    `classification` that holds each task to its own vocabulary;
  - `moderation_state.sequence`, an identity column that orders the decisions
    about one comment when two share a transaction's `now()`;
  - `moderation_attempt`, one row per failed moderation call (E6-02 writes it),
    and `pulse_app`'s `SELECT` and `INSERT` on it;
  - `threat_case`, the row a Care case opens with;
  - `moderation_routing_v001.sql`: the NOLOGIN owner `pulse_moderation_definer`,
    the `SECURITY DEFINER` function `public.route_moderation_verdict` that writes a
    verdict and its route in one call, and the trigger that refuses a
    `MODERATION` row written any other way;
  - `report_comment_v004.sql`, which shows a comment only once it holds a
    moderation verdict and never once any verdict of it is threat or self-harm;
  - `reveal_subject_for_answer_v002.sql`, which answers only for a comment
    holding a threat or self-harm verdict.

**The enum value is committed before anything names it.** PostgreSQL refuses a
new enum label in the transaction that added it, and the `CHECK`, the view and
the reveal body all compare `task` with `'MODERATION'`. So the `ALTER TYPE` runs
in an autocommit block, and everything after it runs in the next transaction.
`ADD VALUE IF NOT EXISTS` keeps a re-run after a failure further down harmless.

The two tables are created before the SQL files, because the routing file grants
on `threat_case` and its function inserts into it.

**The downgrade** restores v003 of the view and v001 of the reveal, drops the
function, the trigger, both tables and the identity column, puts back the
validity-only `CHECK`, and empties the owner role and keeps it (E0-10's decision
for `pulse_reveal_definer`). The `MODERATION` label stays on the enum, because
PostgreSQL cannot drop one, and so do any `MODERATION` rows already written: the
restored `CHECK` constrains validity rows only, so it accepts them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.views_sql import read_sql

revision: str = "f14324ab936c"
down_revision: str | Sequence[str] | None = "ad9da2d96664"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CLASSIFICATION = "classification"
MODERATION_STATE = "moderation_state"
THREAT_CASE = "threat_case"
MODERATION_ATTEMPT = "moderation_attempt"
COMMENT_VIEW = "report_comment"

# Spelled out rather than read from `app.models.ai`: a migration records what was
# applied on the day it ran, and a value read from today's code would change
# under a database that has already been migrated.
VERDICT_CHECK = "ck_classification_verdict_is_in_its_tasks_vocabulary"
PER_TASK_VERDICTS = (
    "(task = 'COMMENT_VALIDITY' AND verdict IN ('substantive', 'insufficient', 'nonsense'))"
    " OR (task = 'MODERATION' AND verdict IN"
    " ('clear', 'harmful', 'privacy', 'nonsense', 'threat', 'self_harm'))"
)
# The rule this revision replaces, exactly as E0-13 wrote it, for the downgrade.
VALIDITY_ONLY_VERDICTS = (
    "task <> 'COMMENT_VALIDITY' OR verdict IN ('substantive', 'insufficient', 'nonsense')"
)

ADD_THE_TASK = "ALTER TYPE classification_task ADD VALUE IF NOT EXISTS 'MODERATION'"

DROP_THE_DOOR = (
    "DROP TRIGGER IF EXISTS classification_moderation_row_only_through_its_door"
    " ON public.classification",
    "DROP FUNCTION IF EXISTS public.classification_moderation_row_only_through_its_door()",
    "DROP FUNCTION IF EXISTS public.route_moderation_verdict(uuid, text, text, text)",
)

# v001 of the reveal is `CREATE FUNCTION`, so the v002 body is dropped first.
DROP_THE_REVEAL = "DROP FUNCTION public.reveal_subject_for_answer(uuid)"
REVOKE_THE_REVEALS_NEW_READ = (
    "REVOKE SELECT (answer_id, task, verdict) ON public.classification FROM pulse_reveal_definer"
)

DROP_THE_VIEW = f"DROP VIEW public.{COMMENT_VIEW}"
RESTORE_THE_APPLICATION_READ = f"GRANT SELECT ON public.{COMMENT_VIEW} TO pulse_app"

EMPTY_THE_DEFINER_ROLE = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_moderation_definer') THEN
        REVOKE SELECT (id) ON public.classification FROM pulse_moderation_definer;
        REVOKE ALL ON public.classification FROM pulse_moderation_definer;
        REVOKE ALL ON public.moderation_state FROM pulse_moderation_definer;
    END IF;
END
$$;
"""


def upgrade() -> None:
    """Apply this revision: the task, the tables, the door, the view and the narrowed reveal."""
    with op.get_context().autocommit_block():
        op.execute(ADD_THE_TASK)

    op.drop_constraint(op.f(VERDICT_CHECK), CLASSIFICATION, type_="check")
    op.create_check_constraint(op.f(VERDICT_CHECK), CLASSIFICATION, PER_TASK_VERDICTS)

    op.add_column(
        MODERATION_STATE,
        sa.Column("sequence", sa.BigInteger(), sa.Identity(always=True), nullable=False),
    )

    op.create_table(
        MODERATION_ATTEMPT,
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["answer_id"],
            ["answer.id"],
            name=op.f("fk_moderation_attempt_answer_id_answer"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_moderation_attempt")),
    )
    op.create_index(
        op.f("ix_moderation_attempt_answer_id"), MODERATION_ATTEMPT, ["answer_id"], unique=False
    )

    op.create_table(
        THREAT_CASE,
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column("classification_id", sa.Uuid(), nullable=False),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["answer_id"],
            ["answer.id"],
            name=op.f("fk_threat_case_answer_id_answer"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["classification_id"],
            ["classification.id"],
            name=op.f("fk_threat_case_classification_id_classification"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_threat_case")),
        sa.UniqueConstraint("answer_id", name=op.f("uq_threat_case_answer_id")),
    )
    op.create_index(
        op.f("ix_threat_case_classification_id"), THREAT_CASE, ["classification_id"], unique=False
    )

    op.execute(read_sql("moderation_routing_v001"))
    op.execute(read_sql("moderation_attempt_grants_v001"))
    op.execute(read_sql(f"{COMMENT_VIEW}_v004"))
    op.execute(read_sql("reveal_subject_for_answer_v002"))


def downgrade() -> None:
    """Reverse this revision, leaving the enum label and any moderation rows in place.

    A database walked back to here shows every comment unmoderated, which is the
    defect this revision corrects, and its reveal door answers for any comment.
    """
    op.execute(DROP_THE_REVEAL)
    op.execute(read_sql("reveal_subject_for_answer_v001"))
    op.execute(REVOKE_THE_REVEALS_NEW_READ)

    op.execute(DROP_THE_VIEW)
    op.execute(read_sql(f"{COMMENT_VIEW}_v003"))
    op.execute(RESTORE_THE_APPLICATION_READ)

    for statement in DROP_THE_DOOR:
        op.execute(statement)

    op.drop_index(op.f("ix_threat_case_classification_id"), table_name=THREAT_CASE)
    op.drop_table(THREAT_CASE)
    op.drop_index(op.f("ix_moderation_attempt_answer_id"), table_name=MODERATION_ATTEMPT)
    op.drop_table(MODERATION_ATTEMPT)

    op.drop_column(MODERATION_STATE, "sequence")

    op.drop_constraint(op.f(VERDICT_CHECK), CLASSIFICATION, type_="check")
    op.create_check_constraint(op.f(VERDICT_CHECK), CLASSIFICATION, VALIDITY_ONLY_VERDICTS)

    op.execute(EMPTY_THE_DEFINER_ROLE)
