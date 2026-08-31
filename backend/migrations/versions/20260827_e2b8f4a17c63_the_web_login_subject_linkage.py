"""the web login subject linkage

Revision ID: e2b8f4a17c63
Revises: b8c41f7d2e05
Create Date: 2026-08-27 11:05:00.000000

E1-12 makes a verified subject resolve to a stored identity at both doors. This
revision is the storage and the mechanism.

**The table.** `public.web_login_subject` maps an identity provider's
`(issuer, sub)` pair to a `person`, with the pair unique and the person unique.
The reasoning is on the model in `app.models.identity`, and ADR 0097 records the
decision it comes from — the identity is the `person` row, a merge is never
inferred from a mutable claim, and a subject with no row here is a defined state
rather than an error.

**The marker.** The table carries an identity comment, which is ADR 0022's third
marker shape and marks every column of it. The text is imported from the model
rather than written here, because `alembic check` does not compare comments and
two copies would drift with nothing reporting it (`docs/MISTAKES.md` entry 13);
`tests/integration/test_identity_column_marker.py` compares the two sides.

**Two SQL files, in this order.** `identity_resolution_v001.sql` creates the
`pulse_resolve_definer` role and the launch door's two point resolvers;
`web_identity_resolution_v001.sql` grants that role its read of the new table and
creates the web door's one. The order is not cosmetic: the second file's `GRANT`
and `ALTER … OWNER` name a role the first file creates, and a SQL-language
function body is parsed when it is created, so the table has to exist first.

**The first file also ships from E1-11, under its own revision** (ADR 0094).
`CREATE OR REPLACE`, the guarded `DO` block and idempotent `GRANT`s make whichever
revision runs second a harmless replay.

**`alembic check` compares the table** — it is on `Base.metadata` — and compares
none of the rest: not the grants, not the role, not the functions, not the
comment. `tests/integration/test_identity_grants.py` pins the grants and the
definer's whole privilege list instead, and the marker module pins the comment.

**The downgrade drops only what this revision alone owns**: the web door's
resolver and the table, whose grant goes with it. The role, its two column grants
and the launch door's two resolvers are left standing, because E1-11's revision
ships the identical file and a downgrade of this one must not remove objects that
one created. They are inert without a caller — each returns a uuid and reads no
identity column — and the next upgrade replaces them in place.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.models.identity import WEB_LOGIN_SUBJECT_COMMENT
from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "e2b8f4a17c63"
down_revision: str | Sequence[str] | None = "b8c41f7d2e05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The scripts this revision runs, in dependency order and named rather than
# globbed — a directory listing is not a dependency order, and these two have a
# real one. See the module docstring.
SCRIPTS = ("identity_resolution_v001", "web_identity_resolution_v001")


def upgrade() -> None:
    """Create the linkage table, then the resolution scheme that reads it."""
    op.create_table(
        "web_login_subject",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("idp_issuer", sa.Text(), nullable=False),
        sa.Column("idp_subject", sa.Text(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name=op.f("fk_web_login_subject_person_id_person"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_web_login_subject")),
        sa.UniqueConstraint(
            "idp_issuer", "idp_subject", name=op.f("uq_web_login_subject_idp_issuer_idp_subject")
        ),
        sa.UniqueConstraint("person_id", name=op.f("uq_web_login_subject_person_id")),
        comment=WEB_LOGIN_SUBJECT_COMMENT,
    )
    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Drop the web door's resolver and the table; leave the shared scheme alone."""
    op.execute("DROP FUNCTION IF EXISTS public.resolve_web_person(text, text)")
    op.drop_table("web_login_subject")
