"""the passback resolves a subject through a definer function

Revision ID: f3b7d05c9e42
Revises: e5b83c60f7a1
Create Date: 2026-09-05 00:00:00.000000

E3-06's whole schema change, and like `e5b83c60f7a1` it is not a schema change:
one `SECURITY DEFINER` function and the two privileges that make it a door,
executed from `identity_resolution_v002.sql`.

SPEC §3.4 posts a participation score to a platform's gradebook, and AGS 2.0
names the student in that score by the LTI `sub`. This system holds a `sub` in
exactly one column — `user.lms_user_id` — and E1-10's round-3 review revoked it
from `pulse_app` because "a connection able to read it can enumerate every
subject that ever launched and join a response back to the person who gave it".
That revocation stands, so the sweep resolves the subject the way every other
door resolves an identity: through ADR 0094's third mechanism, a point lookup
owned by `pulse_resolve_definer` that answers one row's value while the calling
connection holds no read on the column. ADR 0139 records the decision, what it
gives back and what it does not.

**The definer role gains nothing.** It already holds `SELECT (id,
lti_platform_id, lms_user_id)` on `user`, granted by `identity_resolution_v001`,
because `resolve_platform_user` matches on those same two columns. So this
revision issues no `GRANT` on any table and creates no role — a new column grant
here would mean the door reaches something the five columns did not, and
`tests/integration/test_identity_grants.py` holds that set as an equality.

**No table, column, type or index is touched**, so there is nothing here for a
database with rows in it to do and nothing for `alembic check` to compare: the
models describe relations and this revision describes a function and a privilege.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "f3b7d05c9e42"
down_revision: str | Sequence[str] | None = "e5b83c60f7a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUBJECT_RESOLVER = "public.resolve_subject_for_user(uuid)"

# What the downgrade takes away, named by its full signature rather than by its
# bare name. Two reasons, and both are the same reason `e5b83c60f7a1`'s revoke
# names a column: a `DROP FUNCTION` without an argument list is ambiguous the
# moment a second overload exists, and naming the signature is what makes this
# line say out loud which object leaves.
#
# `IF EXISTS` because a downgrade is exactly the moment somebody is already
# dealing with a database in a state nobody planned, and a rollback that stops
# halfway on an object that was never created is worse than one that says nothing
# happened.
#
# **The owner role is neither dropped nor emptied here.** It belongs to
# `e2c94b6a1f70`, it owns four other functions, and its column grants are what
# those four run on — the same decision E0-10 recorded for `pulse_reveal_definer`
# and `e2c94b6a1f70` repeated after `DROP ROLE` stopped a downgrade halfway. What
# leaves with this revision is one function and the `EXECUTE` that rode on it,
# which Postgres drops with the object.
DROP_THE_SUBJECT_RESOLVER = f"DROP FUNCTION IF EXISTS {SUBJECT_RESOLVER}"


def upgrade() -> None:
    """Apply this revision: the reverse point resolver, its owner and its one grant."""
    op.execute(read_sql("identity_resolution_v002"))


def downgrade() -> None:
    """Reverse this revision: the subject resolver is dropped and nothing else moves.

    A database walked back to here keeps every forward resolver, every column
    grant `pulse_resolve_definer` holds and the revocation E1-10 made — and loses
    only the ability to turn a `user` row id into the subject a score is posted
    under, which is E3-06's sweep and nothing else.
    """
    op.execute(DROP_THE_SUBJECT_RESOLVER)
