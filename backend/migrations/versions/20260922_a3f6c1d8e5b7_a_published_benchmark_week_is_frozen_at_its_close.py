"""a published benchmark week is frozen at its close, and the set table's rules

Revision ID: a3f6c1d8e5b7
Revises: f1c86b40d2e7
Create Date: 2026-09-22 00:00:00.000000

E5-14's boundary fix round, in the database half. Four changes, each from a
ruling or a finding of the E5 boundary review:

  - **Freeze at close** (the owner's ruling of 2026-09-22). Both set functions
    take the course weeks asked for and one cutoff per week, and count a
    response toward a week only once its own window had closed and it had last
    been submitted by that week's cutoff. `benchmark_set_week_v003.sql` carries
    the reasoning. The one-argument `_v002` signatures are dropped.
  - **The definer reads the four columns that decision needs**:
    `response.last_submitted_at` and `survey_window (section_id, week_id,
    closes_at)`, column-grain (`benchmark_definer_v002.sql`).
  - **UPDATE on `comparison_set` becomes column-grain**: the name, the declared
    length and level, and `updated_at`, which are what an edit writes
    (`comparison_set_write_grants_v002.sql`).
  - **Two `CHECK`s on `comparison_set` change.** The declared length is any
    whole number of weeks from one up, as `section.length_weeks` is — the owner
    ruled that a set's length is data, so the list of SPEC §2.2's eight lengths
    goes. And a name is not blank once spaces are trimmed.

**The downgrade mirrors all four**, in reverse order, and it can refuse. The
list of eight lengths comes back as a `CHECK`, and Postgres validates a new
`CHECK` against every row, so a database holding a named set of a length not in
the list (a 4-week set, say) refuses the downgrade rather than keeping a row the
older schema forbids. That is a downgrade failing loudly on data it cannot
hold, and nothing is deleted to make it pass.

**Cut from `f1c86b40d2e7`, which was the single head when this was written.**
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "a3f6c1d8e5b7"
down_revision: str | Sequence[str] | None = "f1c86b40d2e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SET_TABLE = "comparison_set"

# The constraint names, rendered the way the naming convention on
# `Base.metadata` renders them (`ck_<table>_<name>`), so the models and this
# revision name the same constraints.
OLD_LENGTH_CHECK = "ck_comparison_set_length_is_a_calendar_length"
NEW_LENGTH_CHECK = "ck_comparison_set_length_weeks_is_at_least_one"
NAME_CHECK = "ck_comparison_set_name_is_not_blank"

# The two rules, written here rather than imported: a migration records what was
# applied and must not change when the model does. The old list is
# `b4d7e2a91c58`'s exactly, for the downgrade to put back.
LENGTH_IS_AT_LEAST_ONE_WEEK = "length_weeks >= 1"
NAME_IS_NOT_BLANK = "btrim(name) <> ''"
OLD_LENGTH_IS_A_CALENDAR_LENGTH = "length_weeks IN (3, 6, 8, 10, 12, 15, 16, 18)"

FROZEN_BODIES = ("benchmark_set_week_v003", "benchmark_set_rating_week_v003")
PREVIOUS_BODIES = ("benchmark_set_week_v002", "benchmark_set_rating_week_v002")

# Dropped before the `_v002` bodies are restored. A function is identified by
# its argument list, so the three-argument functions would otherwise stay beside
# the restored one-argument ones.
DROP_BEFORE_RESTORING = (
    "DROP FUNCTION IF EXISTS public.benchmark_set_week(uuid[], integer[], timestamptz[])",
    "DROP FUNCTION IF EXISTS public.benchmark_set_rating_week(uuid[], integer[], timestamptz[])",
)

# The mirror of `benchmark_definer_v002.sql`: exactly its four columns, so
# `benchmark_definer_v001.sql`'s eighteen stay.
REVOKE_THE_DEFINERS_NEW_COLUMNS = (
    "REVOKE SELECT (last_submitted_at) ON public.response FROM pulse_benchmark_definer",
    "REVOKE SELECT (section_id, week_id, closes_at) ON public.survey_window"
    " FROM pulse_benchmark_definer",
)

# The mirror of `comparison_set_write_grants_v002.sql`. A table-level REVOKE of
# UPDATE also revokes the column-level UPDATE grants, and then the table-wide
# grant `f1c86b40d2e7` issued is put back.
RESTORE_THE_TABLE_WIDE_UPDATE = (
    f"REVOKE UPDATE ON public.{SET_TABLE} FROM pulse_app",
    f"GRANT UPDATE ON public.{SET_TABLE} TO pulse_app",
)


def upgrade() -> None:
    """Apply this revision: the length and name rules, the narrowed UPDATE, the frozen bodies."""
    op.drop_constraint(op.f(OLD_LENGTH_CHECK), SET_TABLE, type_="check")
    op.create_check_constraint(op.f(NEW_LENGTH_CHECK), SET_TABLE, LENGTH_IS_AT_LEAST_ONE_WEEK)
    op.create_check_constraint(op.f(NAME_CHECK), SET_TABLE, NAME_IS_NOT_BLANK)
    op.execute(read_sql("comparison_set_write_grants_v002"))
    op.execute(read_sql("benchmark_definer_v002"))
    for body in FROZEN_BODIES:
        op.execute(read_sql(body))


def downgrade() -> None:
    """Reverse this revision: the `_v002` bodies, the definer's and the set's grants, the old rules.

    Refuses rather than deleting anything when a stored set has a length the old
    list does not hold; see the module docstring.
    """
    for statement in DROP_BEFORE_RESTORING:
        op.execute(statement)
    for body in PREVIOUS_BODIES:
        op.execute(read_sql(body))
    for statement in REVOKE_THE_DEFINERS_NEW_COLUMNS:
        op.execute(statement)
    for statement in RESTORE_THE_TABLE_WIDE_UPDATE:
        op.execute(statement)
    op.drop_constraint(op.f(NAME_CHECK), SET_TABLE, type_="check")
    op.drop_constraint(op.f(NEW_LENGTH_CHECK), SET_TABLE, type_="check")
    op.create_check_constraint(op.f(OLD_LENGTH_CHECK), SET_TABLE, OLD_LENGTH_IS_A_CALENDAR_LENGTH)
