"""the comment read view, and what the small-N path may spend

Revision ID: d4c1a7e93f26
Revises: 688cbcf91b15
Create Date: 2026-09-06 00:00:00.000000

E4-04. The one view SPEC §4's small-N comment path selects text through, and the
four grants that let the application read it, read the moderation record beside
it, and write the release batches §4's cumulative rule produces.

`report_comment` returns `(section_id, week_id, stream, answer_id, comment_text)`
over the comment-kind answers that carry text — no column that names a person and
no instant of any spelling, which is §4.1's rule for a view an instructor reads.
The suppression itself is applied above it in
`backend/app/services/report_comments.py`, because SPEC §4's threshold is a
comparison against a count of responses and §5.2's concealment depends on the
append-only moderation record (ADR 0145), and one module deciding both is worth
more than a view that could hold neither whole.

**Two `views_sql/` scripts and no schema change.** Nothing is created here but one
view and four grants, so `alembic check` compares nothing in this revision: it
reads no `pg_class` entry for a view and no ACL. `446183e8cc5f` measured that and
its docstring records it. What notices a missing view or a widened grant is
`tests/integration/test_identity_grants.py`, `test_identity_column_marker.py`,
`test_identity_separated_views.py` and E4-04's own modules — several of those are
`invariant`-marked, so a skip is a build failure rather than a silent pass.

**The SQL is read from `backend/app/views_sql/` rather than written out here**,
which is the deliberate exception `446183e8cc5f` states at length: Postgres keeps
no record of the text a `CREATE VIEW` was written with, only a parse tree of oids,
so a view whose SQL lives inside a revision string is a view whose
schema-qualification nothing can check. ADR 0041 makes the file immutable once a
revision has executed it, so the file name fixes what ran.

**Order is stated rather than globbed.** The view first, because the grants name
it; the grants last. A file added to `views_sql/` does nothing until a revision
names it, which is the safe direction.

**The downgrade drops the view and writes three REVOKEs.** A privilege granted on
the view is recorded in that view's ACL and goes when the view goes, so there is
nothing to un-grant there. `moderation_state`, `release_batch` and
`release_batch_member` are E4-02's tables and outlive this revision, so their
privileges would survive a downgrade that dropped nothing — which is the
difference between this revision and `b2d9f0a7c341`, and the same shape
`c9b4e0a71d38` has for `survey_window`. The revokes are written here rather than
as a second `.sql` file because ADR 0041 makes a versioned file the record of what
an *upgrade* applied, and an un-grant is not a record of anything.

**No index is created.** ADR 0146 leaves both release tables unindexed beyond
their constraints — "the ticket that measures that read is the one that adds it,
as `c4a8e51db9f3` did for the passback" — and this ticket measures nothing. The
membership lookup the cutter makes is served by `uq_release_batch_member_answer_id`
already.

**This revision takes the chain slot below E4-14's.** A sibling E4 revision cuts
from the same head and the later of the two is re-pointed at merge; nothing here
creates a type, an index or a constraint, so that is a one-line change.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "d4c1a7e93f26"
down_revision: str | Sequence[str] | None = "688cbcf91b15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The scripts this revision runs, in the order it runs them. The view before the
# grants, because a grant names an object that has to exist.
SCRIPTS = (
    "report_comment_v001",
    "report_comment_grants_v001",
)

# What the downgrade removes. The three base-table privileges first, so that a
# downgrade interrupted between the two statements below leaves a role holding
# less rather than more; then the view, which takes its own grant with it.
# `IF EXISTS` is not used: a downgrade that cannot find what this revision made is
# a database that is not where it says it is, and it should say so.
UNDO = (
    "REVOKE SELECT ON public.moderation_state FROM pulse_app",
    "REVOKE SELECT, INSERT ON public.release_batch FROM pulse_app",
    "REVOKE SELECT, INSERT ON public.release_batch_member FROM pulse_app",
    "DROP VIEW public.report_comment",
)


def upgrade() -> None:
    """Apply this revision."""
    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Undo this revision."""
    for statement in UNDO:
        op.execute(statement)
