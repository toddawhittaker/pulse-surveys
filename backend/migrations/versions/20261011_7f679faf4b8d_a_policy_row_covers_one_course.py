"""a policy row covers one course

Revision ID: 7f679faf4b8d
Revises: 2c3d5a0de424
Create Date: 2026-10-11 18:00:00.000000

E7-02 (M2), ADR 0193. A `response_policy` row covers one course, fixed when it is
written. Lead mappings keep no history, so the hold cannot ask who was responsible
for a course when a week's report opened; the row says which course it covers
instead, and the hold reads the latest row for the section's course.

  - `course` gains the unique pair `(id, prefix_id)`. It forbids nothing, since
    `id` alone is unique; it gives the composite key below something to
    reference, as `(id, level)` does for `comparison_set_member`;
  - `response_policy.course_id`, `NOT NULL`, with the composite key
    `(course_id, prefix_id) → course (id, prefix_id)` (`RESTRICT`), so a row's
    course is always in the row's prefix;
  - the index `(prefix_id, set_by_person_id, role, sequence)` is replaced by
    `(course_id, sequence)`, the read the hold makes;
  - `response_loop_grants_v002.sql`: `pulse_app`'s column `INSERT` gains
    `course_id`;
  - `response_loop_guard_v002.sql`: the policy trigger checks the setter against
    the row's course rather than the prefix.

`response_policy` holds no rows anywhere yet (E7-01 shipped no writer), so the new
column needs no backfill and is added `NOT NULL` at once. **The upgrade checks
that first** and raises a readable `RuntimeError` over a row, having changed
nothing, rather than failing on a not-null violation half way: a row written
before this revision says nothing about which course it covered, and no backfill
could know.

**The downgrade refuses while `response_policy` holds a row**, as M1's does: going
down drops `course_id`, and with it the only record of which course each policy
change covered. Over an empty table it restores M1's index and M1's guard, and
drops the column and the unique pair.

**Both directions lock the table before they count** (`SHARE` mode, which lets
reads through and blocks writes), so no row can be written between the count and
the change that would refuse it or destroy it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

from app.views_sql import read_sql

revision: str = "7f679faf4b8d"
down_revision: str | Sequence[str] | None = "2c3d5a0de424"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESPONSE_POLICY = "response_policy"
COURSE_ID_PREFIX_ID_UNIQUE = "uq_course_id_prefix_id"
POLICY_COURSE_KEY = "fk_response_policy_course_id_prefix_id_course"
M1_POLICY_INDEX = "ix_response_policy_prefix_id_set_by_person_id_role_sequence"
M2_POLICY_INDEX = "ix_response_policy_course_id_sequence"

# Going down restores M1's policy function by re-running M1's guard file whole,
# which creates both triggers, so both are dropped first. The response trigger
# comes back exactly as it was.
DROP_BOTH_TRIGGERS = (
    "DROP TRIGGER instructor_response_is_written_by_its_role ON public.instructor_response",
    "DROP TRIGGER response_policy_is_set_by_its_role ON public.response_policy",
)


def _policy_rows() -> int | None:
    """How many `response_policy` rows there are, with writes to it blocked until commit.

    `None` in offline mode (`alembic upgrade --sql`), where there is no database to
    count: the lock is emitted into the script and the caller decides.
    """
    op.execute(f"LOCK TABLE public.{RESPONSE_POLICY} IN SHARE MODE")
    if context.is_offline_mode():
        return None
    connection = op.get_bind()
    return int(
        connection.execute(sa.text(f"SELECT count(*) FROM public.{RESPONSE_POLICY}")).scalar_one()  # noqa: S608
    )


def upgrade() -> None:
    """Apply this revision: the course a policy row covers, its key, its grant and its guard.

    Raises `RuntimeError`, having changed nothing, when `response_policy` holds a
    row: such a row does not say which course it covered.
    """
    # Offline there is nothing to count; the generated script still fails loudly
    # over a row, on the `NOT NULL` column, when someone runs it.
    held = _policy_rows()
    if held:
        raise RuntimeError(
            f"This database holds {held} rows in `public.{RESPONSE_POLICY}`, written before a "
            "policy row named its course. This revision makes `course_id` required, and nothing "
            "can tell which course each of those rows covered. Nothing was changed. Export those "
            "rows and remove them deliberately, then upgrade, and have their setters record "
            "their policies again."
        )
    op.create_unique_constraint(COURSE_ID_PREFIX_ID_UNIQUE, "course", ["id", "prefix_id"])
    op.add_column(RESPONSE_POLICY, sa.Column("course_id", sa.Uuid(), nullable=False))
    op.create_foreign_key(
        POLICY_COURSE_KEY,
        RESPONSE_POLICY,
        "course",
        ["course_id", "prefix_id"],
        ["id", "prefix_id"],
        ondelete="RESTRICT",
    )
    op.drop_index(M1_POLICY_INDEX, table_name=RESPONSE_POLICY)
    op.create_index(M2_POLICY_INDEX, RESPONSE_POLICY, ["course_id", "sequence"], unique=False)

    op.execute(read_sql("response_loop_grants_v002"))
    op.execute(read_sql("response_loop_guard_v002"))


def downgrade() -> None:
    """Reverse this revision.

    Raises `RuntimeError`, having changed nothing, when `response_policy` holds a
    row: going down would lose which course each policy change covered.
    """
    held = _policy_rows()
    if held is None:
        raise RuntimeError(
            "This revision's downgrade cannot be generated offline: it must count the rows in "
            f"`public.{RESPONSE_POLICY}` first, and dropping `course_id` over a row would destroy "
            "the record of which course it covered. Run it against the database instead."
        )
    if held:
        raise RuntimeError(
            f"This database holds {held} rows in `public.{RESPONSE_POLICY}`. Going below this "
            "revision drops `course_id`, the only record of which course each policy change "
            "covered, so it would destroy it. Nothing was changed. Keep the database at this "
            "revision, or export those rows and remove them deliberately first."
        )
    for statement in DROP_BOTH_TRIGGERS:
        op.execute(statement)
    op.execute(read_sql("response_loop_guard_v001"))

    op.drop_index(M2_POLICY_INDEX, table_name=RESPONSE_POLICY)
    op.create_index(
        M1_POLICY_INDEX,
        RESPONSE_POLICY,
        ["prefix_id", "set_by_person_id", "role", "sequence"],
        unique=False,
    )
    op.drop_constraint(POLICY_COURSE_KEY, RESPONSE_POLICY, type_="foreignkey")
    op.drop_column(RESPONSE_POLICY, "course_id")
    op.drop_constraint(COURSE_ID_PREFIX_ID_UNIQUE, "course", type_="unique")
