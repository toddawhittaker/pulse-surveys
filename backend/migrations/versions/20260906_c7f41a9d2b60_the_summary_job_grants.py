"""the summary job grants what it spends

Revision ID: c7f41a9d2b60
Revises: 688cbcf91b15
Create Date: 2026-09-06 00:00:00.000000

E4-06's whole schema change, which is not a schema change at all: two privileges,
executed from `weekly_summary_grants_v001.sql` and
`moderation_state_grants_v001.sql`.

`a1e7c4b60d92` created all four of E4's report tables and granted nothing on any
of them, deliberately — "a privilege lands in the change that spends it" (ADR
0145). E4-06 is the first ticket to spend one. Its Monday walk runs in a Celery
worker on the connection `pulse_app` holds, and it does two things a grant has to
permit: it writes one `weekly_summary` row per stream for every closed
section-week that has none, and it reads `moderation_state` to leave out the
comments a moderator is holding, which is SPEC §5.1's "exclude flagged-held
content".

`SELECT, INSERT` on `weekly_summary` and `SELECT` on `moderation_state` is the
whole of it. Each file names the sentence every verb comes from and the verbs it
withholds; the short version is that nothing here may rewrite a summary an
instructor has read (the E4 breakdown's decision 2 rules out regeneration) and
nothing here may write a moderation decision (E6 owns every one of those).

**The second grant is disputed and is shipped anyway**, which is
`docs/disputes/E4-06-01.md`. Two of this ticket's own tests require the filter
that grant makes executable, and two more assert that `moderation_state` holds no
privilege; the repair is a test-side record the implementer may not write. The
grant is what makes the walk correct, so it lands and the objection names the
assertions that have to move with it.

**No table, column, type or index is touched**, so there is nothing here for a
database with rows in it to do and nothing for `alembic check` to compare: the
models describe relations and this revision describes two privileges.
`tests/integration/test_identity_grants.py` pins them instead, as an equality
against `RUNTIME_BASE_TABLE_PRIVILEGES`, and
`tests/integration/test_the_summary_writer_is_granted_insert_and_select_and_nothing_wider.py`
drives the write over the application connection rather than reading the catalog
alone (`docs/MISTAKES.md` entry 46).

**Cut from `688cbcf91b15`, and expected to be re-pointed at merge.** E4-04 builds
its own revision off the same head in a parallel worktree, as E4-01, E4-02 and
E4-03 did off `c4a8e51db9f3`. Whichever merges second has its `down_revision` and
this docstring's `Revises` line moved onto the new head in the same change as the
merge. No test constant names this revision as a parent.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "c7f41a9d2b60"
down_revision: str | Sequence[str] | None = "688cbcf91b15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUMMARY_TABLE = "weekly_summary"
MODERATION_TABLE = "moderation_state"

# What the downgrade takes back, spelled as the exact mirror of each GRANT. Both
# relations belong to `a1e7c4b60d92` and outlive this revision, so the privileges
# have to be revoked by hand — a revision that drops nothing takes no ACL entry
# with it. Every verb granted is named rather than `REVOKE ALL`: `ALL` would also
# remove a privilege some later revision granted on the same relation for its own
# reason, which is the ordinary way a rollback quietly widens or narrows something
# it was never about.
REVOKE_THE_SUMMARY_WRITE = f"REVOKE SELECT, INSERT ON public.{SUMMARY_TABLE} FROM pulse_app"
REVOKE_THE_MODERATION_READ = f"REVOKE SELECT ON public.{MODERATION_TABLE} FROM pulse_app"


def upgrade() -> None:
    """Apply this revision: the summary walk's write, and the read its filter spends."""
    op.execute(read_sql("weekly_summary_grants_v001"))
    op.execute(read_sql("moderation_state_grants_v001"))


def downgrade() -> None:
    """Reverse this revision: both grants back, and nothing else disturbed.

    The four report tables, their rows and their constraints all belong to
    `a1e7c4b60d92` and stay. A database walked back to here keeps every one of
    them and loses only the application connection's ability to store a summary
    and to read the decisions that say which comments may feed one — which is
    exactly the state E4-02 left behind.
    """
    op.execute(REVOKE_THE_MODERATION_READ)
    op.execute(REVOKE_THE_SUMMARY_WRITE)
