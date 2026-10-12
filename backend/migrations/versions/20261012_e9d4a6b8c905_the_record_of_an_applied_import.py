"""the record of an applied import

Revision ID: e9d4a6b8c905
Revises: e9a7c9e1b807
Create Date: 2026-10-12 13:00:00.000000

E9-06's fix round, ADR 0204. SPEC §8 makes `audit_log` include every import
"with their dry-run diffs", and an applied import wrote no row of its own:

  - a new `audit_action` value, `IMPORT_APPLIED`, added in an autocommit block
    because PostgreSQL refuses to use an enum value in the transaction that added
    it, and the checks below name it;
  - a nullable `audit_log.detail jsonb`, held by a two-way check to exactly the
    `IMPORT_APPLIED` rows;
  - E9-02's `an_admin_write_names_its_person` check widened, keeping its name, so
    an import row names no subject person (an import is about many), while every
    other admin write still names one and a reveal still names none;
  - `people_graph_v002.sql`: `admin_record_import`, owned by E9-02's
    `pulse_people_graph_definer`, which gains `INSERT` on `detail`, with
    `EXECUTE` for `pulse_app`.

**The downgrade refuses while any `IMPORT_APPLIED` row exists**, before touching
anything, as E9-02's does for its own rows: going down drops `detail`, and with it
the diff of every recorded import. Otherwise it drops the function, revokes the
owner's grant on `detail`, restores E9-02's check and drops the column and its
check. The enum value stays: PostgreSQL cannot drop one, and `ADD VALUE IF NOT
EXISTS` makes the next upgrade a no-op for it.

**Chained after `e9a7c9e1b807`.** Written off `e9c3f5a7b403`; when E9-05's
revision merged into the epic branch first, this one's `down_revision` moved onto
it, so the chain stays linear, with no change to what this revision does.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.views_sql import read_sql

revision: str = "e9d4a6b8c905"
down_revision: str | Sequence[str] | None = "e9a7c9e1b807"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUDIT_LOG = "audit_log"

# Spelled out rather than read from `app.models.audit`: a migration records what
# was applied on the day it ran (E6-01's reasoning).
DETAIL_CHECK = "only_an_import_carries_a_detail"
DETAIL_CHECK_RULE = "(action = 'IMPORT_APPLIED') = (detail IS NOT NULL)"
ADMIN_WRITE_CHECK = "an_admin_write_names_its_person"
ADMIN_WRITE_CHECK_RULE = (
    "(action IN ('IDENTITY_REVEAL', 'IMPORT_APPLIED')) = (subject_person_id IS NULL)"
)
E9_02_ADMIN_WRITE_CHECK_RULE = "(action = 'IDENTITY_REVEAL') = (subject_person_id IS NULL)"


def upgrade() -> None:
    """Apply this revision: the action, the column and its checks, then the definer."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'IMPORT_APPLIED'")

    op.add_column(AUDIT_LOG, sa.Column("detail", postgresql.JSONB(), nullable=True))
    op.create_check_constraint(op.f(f"ck_audit_log_{DETAIL_CHECK}"), AUDIT_LOG, DETAIL_CHECK_RULE)
    op.drop_constraint(op.f(f"ck_audit_log_{ADMIN_WRITE_CHECK}"), AUDIT_LOG, type_="check")
    op.create_check_constraint(
        op.f(f"ck_audit_log_{ADMIN_WRITE_CHECK}"), AUDIT_LOG, ADMIN_WRITE_CHECK_RULE
    )

    op.execute(read_sql("people_graph_v002"))


def downgrade() -> None:
    """Reverse this revision.

    Raises `RuntimeError`, having changed nothing, when `audit_log` holds an
    `IMPORT_APPLIED` row: going down would destroy the diff it records.
    """
    connection = op.get_bind()
    # Writes to `audit_log` are blocked from here to the commit (`SHARE` mode lets
    # reads through), so no import can be recorded between the count and the drop.
    connection.execute(sa.text(f"LOCK TABLE public.{AUDIT_LOG} IN SHARE MODE"))
    held = connection.execute(
        sa.text(
            f"SELECT count(*) FROM public.{AUDIT_LOG} "  # noqa: S608
            "WHERE action = 'IMPORT_APPLIED'"
        )
    ).scalar_one()
    if held:
        raise RuntimeError(
            "This database holds audit rows recording applied people and mapping imports: "
            f"{held} of them. Going below this revision drops the column those rows keep each "
            "import's dry-run diff in, which SPEC §8 says the log keeps. Nothing was changed. "
            "Keep the database at this revision, or export those rows and remove them "
            "deliberately first."
        )

    op.execute("DROP FUNCTION public.admin_record_import(uuid, text, jsonb)")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles "
        "WHERE rolname = 'pulse_people_graph_definer') THEN "
        "REVOKE INSERT (detail) ON public.audit_log FROM pulse_people_graph_definer; "
        "END IF; END $$"
    )

    op.drop_constraint(op.f(f"ck_audit_log_{ADMIN_WRITE_CHECK}"), AUDIT_LOG, type_="check")
    op.create_check_constraint(
        op.f(f"ck_audit_log_{ADMIN_WRITE_CHECK}"), AUDIT_LOG, E9_02_ADMIN_WRITE_CHECK_RULE
    )
    op.drop_constraint(op.f(f"ck_audit_log_{DETAIL_CHECK}"), AUDIT_LOG, type_="check")
    op.drop_column(AUDIT_LOG, "detail")
