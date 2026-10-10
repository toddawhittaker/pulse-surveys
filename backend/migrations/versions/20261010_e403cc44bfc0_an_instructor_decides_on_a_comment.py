"""an instructor decides on a comment

Revision ID: e403cc44bfc0
Revises: f14324ab936c
Create Date: 2026-10-10 00:00:00.000000

E6-03, ADR 0189. Until this revision only the routing definer wrote
`moderation_state`, and a row said which comment, which state and when. This
revision adds what a person's decision needs:

  - four columns: `decided_by_person_id` (a `person` key, `RESTRICT`, as
    `audit_log.actor_person_id` is), `decided_as` (the role the decision was made
    under), `reason` (the stated reason) and `is_undo`;
  - `CHECK`s: the role is one of three; a decider names a role and a role names a
    decider; a row with no decider is the router's and is `FLAGGED_COLLAPSED`; a
    reason needs a decider; a reason is non-blank and at most 500 characters;
  - `moderation_decision_grants_v001.sql`: `pulse_app`'s `INSERT` on the six
    columns a decision writes, at column grain;
  - `moderation_state_router_rows_v001.sql`: the trigger that refuses a
    decider-less row from any role but `pulse_moderation_definer`.

**Every existing row is the router's flag**, written by E6-01's definer with no
decider, so each new `CHECK` holds over the rows already there and `is_undo`'s
default fills them.

**The constraint text is spelled out rather than read from `app.models.report`**:
a migration records what was applied on the day it ran (E6-01's reasoning).

**The downgrade** drops the trigger and its function, revokes the six column
grants by name (and nothing else, so E4-04's `SELECT` survives), then drops the
`CHECK`s, the index and the columns.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.views_sql import read_sql

revision: str = "e403cc44bfc0"
down_revision: str | Sequence[str] | None = "f14324ab936c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "moderation_state"

# Name, then condition, for each `CHECK` this revision adds. The names match the
# model's `CheckConstraint`s under the naming convention's `ck_%(table)s_` prefix.
CHECKS = (
    (
        "decided_as_is_a_deciding_role",
        "decided_as IN ('INSTRUCTOR', 'LEAD_FACULTY', 'CHAIR')",
    ),
    (
        "a_decider_and_a_role_come_together",
        "(decided_by_person_id IS NULL) = (decided_as IS NULL)",
    ),
    (
        "a_row_nobody_decided_is_a_flag",
        "decided_by_person_id IS NOT NULL OR state = 'FLAGGED_COLLAPSED'",
    ),
    (
        "a_reason_needs_a_decider",
        "reason IS NULL OR decided_by_person_id IS NOT NULL",
    ),
    (
        "a_reason_is_stated_and_bounded",
        # Non-blank is "holds a character Python's `str.strip()` would keep", by
        # code point, the way `report_comment_v003.sql` defines a blank comment.
        "reason IS NULL OR (length(reason) BETWEEN 1 AND 500"
        " AND reason ~ '[^\\u0009-\\u000d\\u001c-\\u001f \\u0085\\u00a0\\u1680\\u2000-\\u200a"
        "\\u2028\\u2029\\u202f\\u205f\\u3000]')",
    ),
)

DROP_THE_TRIGGER = (
    f"DROP TRIGGER moderation_state_router_rows_only_from_the_router ON public.{TABLE}",
    "DROP FUNCTION public.moderation_state_router_rows_only_from_the_router()",
)
REVOKE_THE_DECISION_GRANT = (
    "REVOKE INSERT (answer_id, state, decided_by_person_id, decided_as, reason, is_undo)"
    f" ON public.{TABLE} FROM pulse_app"
)
DECIDER_INDEX = "ix_moderation_state_decided_by_person_id"


def upgrade() -> None:
    """Apply this revision: the decision columns, their rules, the grant and the trigger."""
    op.add_column(TABLE, sa.Column("decided_by_person_id", sa.Uuid(), nullable=True))
    op.add_column(TABLE, sa.Column("decided_as", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("reason", sa.Text(), nullable=True))
    op.add_column(
        TABLE,
        sa.Column("is_undo", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_foreign_key(
        op.f("fk_moderation_state_decided_by_person_id_person"),
        TABLE,
        "person",
        ["decided_by_person_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f(DECIDER_INDEX), TABLE, ["decided_by_person_id"], unique=False)
    for name, condition in CHECKS:
        op.create_check_constraint(op.f(f"ck_{TABLE}_{name}"), TABLE, condition)

    op.execute(read_sql("moderation_decision_grants_v001"))
    op.execute(read_sql("moderation_state_router_rows_v001"))


def downgrade() -> None:
    """Reverse this revision, leaving E4-04's `SELECT` on the table in place."""
    for statement in DROP_THE_TRIGGER:
        op.execute(statement)
    op.execute(REVOKE_THE_DECISION_GRANT)
    for name, _condition in reversed(CHECKS):
        op.drop_constraint(op.f(f"ck_{TABLE}_{name}"), TABLE, type_="check")
    op.drop_index(op.f(DECIDER_INDEX), table_name=TABLE)
    op.drop_constraint(
        op.f("fk_moderation_state_decided_by_person_id_person"), TABLE, type_="foreignkey"
    )
    op.drop_column(TABLE, "is_undo")
    op.drop_column(TABLE, "reason")
    op.drop_column(TABLE, "decided_as")
    op.drop_column(TABLE, "decided_by_person_id")
