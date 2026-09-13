"""the summary job grants what it spends

Revision ID: c7f41a9d2b60
Revises: d4c1a7e93f26
Create Date: 2026-09-06 00:00:00.000000

E4-06's whole schema change, which is not a schema change at all: one privilege
pair, executed from `weekly_summary_grants_v001.sql`.

`a1e7c4b60d92` created all four of E4's report tables and granted nothing on any
of them, deliberately — "a privilege lands in the change that spends it" (ADR
0145). Its Monday walk runs in a Celery worker on the connection `pulse_app`
holds, and it does two things a grant has to permit: it writes one
`weekly_summary` row per stream for every closed section-week that has none, and
it reads `moderation_state` to leave out the comments a moderator is holding,
which is SPEC §5.1's "exclude flagged-held content".

`SELECT, INSERT` on `weekly_summary` is the whole of what **this** revision
issues. `weekly_summary_grants_v001.sql` names the sentence every verb comes from
and the verbs it withholds; the short version is that nothing here may rewrite a
summary an instructor has read (the E4 breakdown's decision 2 rules out
regeneration).

**The `moderation_state` read is spent here and granted one revision below.**
E4-06's own build issued it too, from `moderation_state_grants_v001.sql`, because
the two tickets were built in parallel worktrees off one head and each has to be
able to run alone. `d4c1a7e93f26` — E4-04's revision, directly below this one —
grants `SELECT ON public.moderation_state TO pulse_app` in
`report_comment_grants_v001.sql`, so at merge this revision stopped issuing it and
its grants file went with it. A `GRANT` is idempotent and nothing in CI can see
two of them, but the `REVOKE`s are not: each revision's `downgrade()` would have
taken back a privilege the other still depends on, so a rollback of either would
have left the surviving path unable to read the moderation record it filters on.
One grantor, one revoker. Dispute `docs/disputes/E4-06-01.md` settled *that*
`pulse_app` must hold this read, against a work order that said "`weekly_summary`
and nothing wider"; the ruling stands and only the revision that issues it moved.

**No table, column, type or index is touched**, so there is nothing here for a
database with rows in it to do and nothing for `alembic check` to compare: the
models describe relations and this revision describes two privileges.
`tests/integration/test_identity_grants.py` pins them instead, as an equality
against `RUNTIME_BASE_TABLE_PRIVILEGES`, and
`tests/integration/test_the_summary_writer_is_granted_insert_and_select_and_nothing_wider.py`
drives the write over the application connection rather than reading the catalog
alone (`docs/MISTAKES.md` entry 46).

**Cut from `688cbcf91b15`, and re-pointed at merge, which is what that plan said
would happen.** E4-04 built its own revision off the same head in a parallel
worktree, as E4-01, E4-02 and E4-03 did off `c4a8e51db9f3`. E4-04 merged first and
keeps `688cbcf91b15`; this revision's `down_revision` and this docstring's
`Revises` line moved onto `d4c1a7e93f26` in the same change as the merge, leaving
one head. No test constant names this revision as a parent.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "c7f41a9d2b60"
down_revision: str | Sequence[str] | None = "d4c1a7e93f26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUMMARY_TABLE = "weekly_summary"

# What the downgrade takes back, spelled as the exact mirror of the GRANT. The
# relation belongs to `a1e7c4b60d92` and outlives this revision, so the privilege
# has to be revoked by hand — a revision that drops nothing takes no ACL entry
# with it. Every verb granted is named rather than `REVOKE ALL`: `ALL` would also
# remove a privilege some later revision granted on the same relation for its own
# reason, which is the ordinary way a rollback quietly widens or narrows something
# it was never about. **There is deliberately no revoke of `moderation_state`
# here**: `d4c1a7e93f26` grants that read and is the only revision that may take
# it back, or a rollback of this one would break E4-04's suppression path.
REVOKE_THE_SUMMARY_WRITE = f"REVOKE SELECT, INSERT ON public.{SUMMARY_TABLE} FROM pulse_app"


def upgrade() -> None:
    """Apply this revision: the summary walk's write. The filter's read is `d4c1a7e93f26`'s."""
    op.execute(read_sql("weekly_summary_grants_v001"))


def downgrade() -> None:
    """Reverse this revision: the summary grant back, and nothing else disturbed.

    The four report tables, their rows and their constraints all belong to
    `a1e7c4b60d92` and stay. A database walked back to here keeps every one of
    them and loses only the application connection's ability to store a summary.
    The `moderation_state` read stays, because `d4c1a7e93f26` below still grants
    it and E4-04's suppression path still spends it; revoking it from here would
    make a rollback of this revision break a path this revision is not about.
    """
    op.execute(REVOKE_THE_SUMMARY_WRITE)
