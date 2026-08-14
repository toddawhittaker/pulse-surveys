"""baseline

Revision ID: 2f045e5e0336
Revises:
Create Date: 2026-08-13 22:12:58.016847

The first link in the chain, and it creates nothing on purpose (E0-04; the first
tables are E0-05's). What it does create is the `alembic_version` table, which
Alembic writes itself, so a database that has run this revision is one the
migration machinery has actually reached rather than one nobody has touched.

`sqlalchemy` and `alembic.op` are deliberately not imported here — there is
nothing to import them for. Generated revisions get them from
`migrations/script.py.mako`.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "2f045e5e0336"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""


def downgrade() -> None:
    """Undo this revision."""
