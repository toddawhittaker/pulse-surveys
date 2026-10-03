"""the benchmark set functions answer each figure's own counts

Revision ID: c4b8f37e5a19
Revises: d9e5b13c7a42
Create Date: 2026-09-14 00:00:00.000000

E5-04's security fix round, in the database half. A review of this ticket found
that a comparison figure was sealed against counts of a population other than
the one it aggregates, which is `docs/MISTAKES.md` entry 50's class:

  - a rating trend point's mean is per stream, and `benchmark_set_rating_week`
    answered no count of people and no count of sections at all, so the service
    sealed it with the *week's* counts — everybody who answered anything, in
    every section anybody answered in;
  - the workload mean and median are computed over the responses carrying hours
    (ADR 0165 keeps the row when nobody reports any), and they were sealed with
    counts of every responder.

Both diverge in the disclosing direction: a figure computed from two people, or
from one section, could be shown as a figure over fifteen people across five.
SPEC §4.1 item 7 suppresses a figure below the minimum, and the minimum is about
the population *that figure* is computed from.

So `benchmark_set_week` gains `workload_respondent_count` and
`workload_section_count`, and `benchmark_set_rating_week` gains
`rating_respondent_count` and `rating_section_count`. Each file says what its
two new numbers count and why the old ones stay. `app.services.benchmarks` then
seals every figure with its own pair.

**Nothing is granted or revoked here.** Both bodies compute the new counts from
`response.user_id`, `section.id` and `answer.workload_hours`, which
`pulse_benchmark_definer` already holds column-grain `SELECT` on — ADR 0165's
2026-09-13 amendment names every pair it holds, and the column-equality test in
`tests/integration/test_the_roster_definers_answer_a_point_query_and_nothing_more.py`
is what keeps that true across this revision rather than a sentence here. The
`EXECUTE` grant to `pulse_app` is re-issued by each file because a dropped
function takes its ACL with it, and the inventory that admits those two doors is
unchanged: the same two names, the same one verb.

**Dropped and recreated rather than replaced, which is measured rather than
assumed.** Postgres refuses `CREATE OR REPLACE FUNCTION` when the return type
changes, and two more `OUT` columns in a `RETURNS TABLE` is a changed return
type — it answers `cannot change return type of existing function` (42P13). Each
`_v002.sql` therefore drops its own function first.

**No table, column, type or index is touched**, so there is nothing for
`alembic check` to compare: the models describe relations and this revision
describes two function bodies.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "c4b8f37e5a19"
down_revision: str | Sequence[str] | None = "d9e5b13c7a42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The two bodies this revision installs, and the two it puts back. Named as a
# pair because the downgrade is the mirror rather than a drop: `a7c3e9d21f84`
# created both functions and a database walked back to here still has callers
# expecting them, so the reversal restores the previous body instead of leaving
# a hole. Each `_v001.sql` drops nothing and re-creates its own function through
# `CREATE OR REPLACE` — which works in that direction, because fewer `OUT`
# columns is still a changed return type and the file that follows this one down
# is the one that measured it.
FIXED_BODIES = ("benchmark_set_week_v002", "benchmark_set_rating_week_v002")
PREVIOUS_BODIES = ("benchmark_set_week_v001", "benchmark_set_rating_week_v001")

# Dropped before the v001 bodies are restored, for the same reason the v002
# files drop before creating: the return type is narrowing, and Postgres refuses
# to replace across a return-type change in either direction.
DROP_BEFORE_RESTORING = (
    "DROP FUNCTION IF EXISTS public.benchmark_set_week(uuid[])",
    "DROP FUNCTION IF EXISTS public.benchmark_set_rating_week(uuid[])",
)


def upgrade() -> None:
    """Apply this revision: each set function answers the counts its figures are sealed with."""
    for body in FIXED_BODIES:
        op.execute(read_sql(body))


def downgrade() -> None:
    """Reverse this revision: the two previous bodies, with their owner and grant intact.

    The functions are restored rather than dropped. `a7c3e9d21f84` created them
    and E5-04's service calls them, so a database walked back to here keeps two
    working doors that answer the week's counts and not each figure's own — which
    is the state this revision corrects, and the state the revision below it
    describes.
    """
    for statement in DROP_BEFORE_RESTORING:
        op.execute(statement)
    for body in PREVIOUS_BODIES:
        op.execute(read_sql(body))
