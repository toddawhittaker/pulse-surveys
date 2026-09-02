"""the application may read a student's own survey

Revision ID: d3a71b5c8e42
Revises: c9b4e0a71d38
Create Date: 2026-09-01 00:00:00.000000

E2-09 is the first code that reads `public.week`, `public.question_set`,
`public.question`, `public.response` and `public.answer`. `GET /student/survey`
answers one question — for this reader, right now, what is there? — and it runs on
the connection `pulse_app` holds, so this revision is where the grants land, with
the code that spends them. `SELECT` on all five, and nothing else.

**Only what this ticket reads.** E2-09 reads; E2-08 writes, and the verbs its
submit path needs on `response` and `answer` land in its own revision beside the
code that issues them. A privilege granted in advance of its use is a privilege
nobody can point at the statement for.

**`week` repairs a gap that predates this ticket**, and it is worth saying here
rather than only in the SQL: `app.services.survey_windows.derive_windows_for_section`
already selects `week` rows on this same connection, and no revision had granted
it. It lands in E2-09 because this is the ticket whose read needs it.

**The withheld verbs are the load-bearing half.** No `UPDATE` and no `DELETE`
anywhere in this file. The read path structurally cannot revise a submission, and
the application role structurally cannot reword a question under answers already
given to it or renumber a week under windows already derived against it — the
question set is standardized and versioned (SPEC §3.2) and the term calendar is
institution configuration (§2.2), both an administrator's to edit on a surface E11
builds rather than something a request-time read can touch.

**There is no schema change here at all**, so `alembic check` has nothing to
compare: a grant is not part of `Base.metadata` and autogenerate has never emitted
one. That is the ordinary state of every grants file in this tree
(`survey_window_grants_v001.sql`, `clock_override_grants_v001.sql`), and it is why
`tests/integration/test_identity_grants.py` pins what each runtime role holds as an
equality read out of the catalog — the drift gate cannot see this and a
hand-written catalog assertion can.

**This revision turns that equality red until its constant gains the five
entries**, and that is the designed cost rather than a surprise.
`RUNTIME_BASE_TABLE_PRIVILEGES` is deliberately hand-written and not derived from
these `.sql` files, so that a widening cannot justify itself; the entry is raised
as `docs/disputes/E2-09-02.md`, the same shape `docs/disputes/E2-06-03.md` took for
`survey_window` and `docs/disputes/E2-04-02.md` for `clock_override`.

**The downgrade revokes.** All five tables outlive this revision, so unlike a
grant on a table its own revision drops, these would survive a downgrade that
dropped nothing. The `REVOKE` is written here rather than as a second `.sql` file:
ADR 0041 makes a versioned file the immutable record of what an upgrade applied,
and an un-grant is not a record of anything.

**Chained after `c9b4e0a71d38`**, E2-06's survey-window grant, which is the head
this branch was cut from and the head `alembic heads` reports. E2-08 is being
built in parallel and adds a revision of its own; whichever of the two merges
second re-chains onto the other.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "d3a71b5c8e42"
down_revision: str | Sequence[str] | None = "c9b4e0a71d38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The scripts this revision runs. Written out rather than globbed, for the reason
# E0-10's revision gives: a directory listing is not a dependency order, and a
# file added to the directory does nothing until a revision names it.
SCRIPTS = ("student_read_grants_v001",)

# What the upgrade granted, undone one relation at a time. Written out rather
# than looped over a shared list because the grant itself is the `.sql` file's
# record and this is a separate statement of what to take back.
REVOKES = (
    "REVOKE SELECT ON public.week FROM pulse_app",
    "REVOKE SELECT ON public.question_set FROM pulse_app",
    "REVOKE SELECT ON public.question FROM pulse_app",
    "REVOKE SELECT ON public.response FROM pulse_app",
    "REVOKE SELECT ON public.answer FROM pulse_app",
)


def upgrade() -> None:
    """Apply this revision."""
    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Undo this revision."""
    for statement in REVOKES:
        op.execute(statement)
