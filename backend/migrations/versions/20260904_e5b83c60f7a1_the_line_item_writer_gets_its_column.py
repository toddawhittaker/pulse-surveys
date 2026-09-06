"""the line-item writer gets the one column it writes

Revision ID: e5b83c60f7a1
Revises: a7c2f4e18b30
Create Date: 2026-09-04 00:00:00.000000

E3-05's whole schema change, which is not a schema change at all: one
column-scoped privilege, executed from `grade_passback_grants_v002.sql`.

`c7e2a41b90f5` created `section.ags_line_item_url` and deliberately left it
ungranted — E3-02 wrote nothing to it, and a grant issued for a writer that does
not exist is the convenience grant this scheme exists to make visible. E3-05 is
the writer: SPEC §3.4's line item is created on the first staff launch and its id
is recorded on the section so that every later post can address it without
walking a container (ADR 0128). ADR 0136 records the decision and what it
deliberately does not grant.

**No table, column, type or index is touched**, so there is nothing here for a
database with rows in it to do and nothing for `alembic check` to compare: the
models describe relations and this revision describes a privilege.
"""

from collections.abc import Sequence

from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "e5b83c60f7a1"
down_revision: str | Sequence[str] | None = "a7c2f4e18b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SECTION_TABLE = "section"
AGS_LINE_ITEM_COLUMN = "ags_line_item_url"

# What the downgrade takes back, and it names the column for the same reason
# `c7e2a41b90f5`'s note gives about the container address one revision below: a
# privilege granted at column grain lives in `pg_attribute.attacl`, and `REVOKE
# UPDATE ON public.section` does not reach it. A table-grain revoke here would
# read as correct, run without error, and leave the application connection able to
# write the column the rollback was meant to take away.
#
# It also names one column and not the role: `REVOKE UPDATE ON public.section FROM
# pulse_app` — or anything wider — would take E3-02's `UPDATE
# (lms_ags_line_items_url)` with it, and the database that leaves is one where a
# staff launch can no longer store the gradebook address its platform advertised.
REVOKE_THE_LINE_ITEM_COLUMN = (
    f"REVOKE UPDATE ({AGS_LINE_ITEM_COLUMN}) ON public.{SECTION_TABLE} FROM pulse_app"
)


def upgrade() -> None:
    """Apply this revision: the one column-scoped UPDATE the line-item writer spends."""
    op.execute(read_sql("grade_passback_grants_v002"))


def downgrade() -> None:
    """Reverse this revision: the column grant back, and nothing else disturbed.

    The column itself belongs to `c7e2a41b90f5` and stays, along with every other
    privilege on it; a database walked back to here keeps the gradebook address
    its launches store and loses only the ability to record a line item's id.
    """
    op.execute(REVOKE_THE_LINE_ITEM_COLUMN)
