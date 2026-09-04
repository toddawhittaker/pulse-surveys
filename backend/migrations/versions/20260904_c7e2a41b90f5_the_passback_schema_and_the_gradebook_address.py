"""the passback schema, and the gradebook address a launch supplies

Revision ID: c7e2a41b90f5
Revises: b1e7d4a90c26
Create Date: 2026-09-04 00:00:00.000000

E3-02's whole schema, in one revision, because everything E3 later writes to has
to exist before anything writes it. E0-33's forty-one fixtures broken inside their
own seeding is why the order is this way round: constraints and columns land
before the write paths and the fixtures that would violate them exist.

**`section` gains the two gradebook addresses.** `lms_ags_line_items_url` is the
AGS line-item container the platform advertises on a staff launch, stored as an
exact mirror of `lms_context_memberships_url` — same claim shape, same writer,
same judgement by `app.models.lti.refuse_invalid_fetched_address`, and a refused
address recorded as a defect rather than turned into a refused launch.
`ags_line_item_url` is the id of the line item this tool creates in that
container; E3-02 adds the column and E3-05 is what writes it. Both nullable, and
NULL is a state rather than a missing value: a platform that grants no gradebook
scope advertises no endpoint claim at all, which is a configuration and not a
fault.

**`launch_defect_kind` grows `ags_address_refused`**, the exact mirror of
`roster_address_refused`. The label is added with `IF NOT EXISTS`, which is what
makes re-running the upgrade after a downgrade a no-op — see the downgrade below.

**`grade_sync` arrives**: SPEC §8's append-only account of what Pulse posted to a
platform's gradebook, one row per post and a failed attempt a row too, with the
composite index that makes the latest row for one student in one section cheap.
ADR 0124 settles the grain and ADR 0129 settles what the outcome is made of — an
enum of two beside a nullable response code, with the platform's response body
rejected.

**`ags_call` arrives beside it**: SPEC §6.1's second call log, at the grain of one
HTTP call, modelled on `nrps_call`.

**One SQL file is executed**, after the tables exist because it grants on them:
`grade_passback_grants_v001.sql`, which gives `pulse_app` `SELECT` and `INSERT` on
both new tables and the one column-scoped `UPDATE` on `section` the gradebook
address's writer needs. No `SANCTIONED_WRITERS` entry is added: the address is
written by `launch_provisioning`, whose catalog entry already grants `section`.

**No data migration.** Both new `section` columns are nullable, both new tables
are empty, and nothing existing is narrowed — so a database with rows in it needs
nothing done to it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "c7e2a41b90f5"
down_revision: str | Sequence[str] | None = "b1e7d4a90c26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Spelled out rather than imported from `app.models`, for the reason every other
# revision here gives: a migration records what was applied on the day it ran, and
# a value read from today's code would change under a database that has already
# been migrated.
TIMESTAMP = sa.DateTime(timezone=True)

SECTION_TABLE = "section"
AGS_CONTAINER_COLUMN = "lms_ags_line_items_url"
AGS_LINE_ITEM_COLUMN = "ags_line_item_url"

GRADE_SYNC_TABLE = "grade_sync"
AGS_CALL_TABLE = "ags_call"

# The kind this revision adds to `launch_defect_kind`: a launch advertised an AGS
# container address the registration-address rules will not let this container
# fetch. Not the same fact as a launch that advertised none, which is a state and
# gets no record at all.
NEW_DEFECT_KIND = "ags_address_refused"

# SPEC §8's two outcomes, as the labels this revision created. Bound to a name
# because the type is made as a side effect of the column below and the downgrade
# needs an object to call `.drop()` on.
GRADE_SYNC_OUTCOME = sa.Enum("posted", "failed", name="grade_sync_outcome")

# The access path this table is laid out for: the newest row for one student in
# one section, which E3-06 runs per student per section on every sweep. The two
# keys lead because that is the equality it filters on; `created_at` follows
# because the ordering runs on it.
#
# **A plain ascending column list and not a text expression**, which is what makes
# the declaration comparable: `alembic check` reads all three key columns and holds
# this migration to them. A descending `created_at` performs identically —
# Postgres serves `ORDER BY … DESC LIMIT 1` from an ascending index by a backward
# scan — and can only be written as a text expression, which `check` cannot compare
# at all. E2-02 reversed `nrps_call`'s index for exactly that reason and
# `NrpsCall`'s own docstring records it.
GRADE_SYNC_INDEX = "ix_grade_sync_section_id_user_id_created_at"

# What the downgrade takes back from `pulse_app`. The two table grants disappear
# with their tables, so these are here for the column grant on `section`, which
# does not — a column ACL entry survives every drop in this revision and would be
# left standing on a table one revision back has no such column on. Revoked at
# column grain because that is the grain it was granted at: `REVOKE … ON
# public.section` does not reach a column-grain entry.
REVOKE_THE_GRADEBOOK_COLUMN = (
    f"REVOKE UPDATE ({AGS_CONTAINER_COLUMN}) ON public.{SECTION_TABLE} FROM pulse_app"
)


def upgrade() -> None:
    """Apply this revision: the two columns, the new defect kind, the two tables."""
    op.add_column(SECTION_TABLE, sa.Column(AGS_CONTAINER_COLUMN, sa.Text(), nullable=True))
    op.add_column(SECTION_TABLE, sa.Column(AGS_LINE_ITEM_COLUMN, sa.Text(), nullable=True))

    op.execute(f"ALTER TYPE launch_defect_kind ADD VALUE IF NOT EXISTS '{NEW_DEFECT_KIND}'")

    op.create_table(
        GRADE_SYNC_TABLE,
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("score_text", sa.Text(), nullable=False),
        sa.Column("score_timestamp", TIMESTAMP, nullable=False),
        sa.Column("ledger_text", sa.Text(), nullable=False),
        sa.Column("outcome", GRADE_SYNC_OUTCOME, nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["section.id"],
            name=op.f("fk_grade_sync_section_id_section"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_grade_sync_user_id_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grade_sync")),
    )
    op.create_index(
        GRADE_SYNC_INDEX,
        GRADE_SYNC_TABLE,
        ["section_id", "user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        AGS_CALL_TABLE,
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("called_at", TIMESTAMP, nullable=False),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["section.id"],
            name=op.f("fk_ags_call_section_id_section"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ags_call")),
    )

    op.execute(read_sql("grade_passback_grants_v001"))


def downgrade() -> None:
    """Reverse this revision: the grants back, the tables gone, the columns gone.

    **The order is the reverse of the upgrade's and each step needs the one before
    it.** The column grant is revoked while the column still exists, because a
    revoke naming a dropped column is an error rather than a no-op. The index goes
    with its table. The enum type is dropped after the column that uses it, because
    `DROP TYPE` is refused while anything is declared of that type.

    **The `launch_defect_kind` label is left in place**, which is the stance
    `b8c41f7d2e05` and `d2f6a913c47e` both take and for the same reason: Postgres
    cannot remove a value from an enum type. The upgrade adds it with `IF NOT
    EXISTS` so that coming back up succeeds, and a database walked back below this
    revision carries a label no writer in that revision's code ever writes.

    **Rows are not preserved and nothing here pretends otherwise.** Both new tables
    are dropped whole and both new `section` columns go with their values. E2-16's
    preserve-and-restore exists for a downgrade that narrows something a database
    already holds; this one removes objects it created, and a database that goes
    down and comes back up gets the schema it had rather than the rows.
    """
    op.execute(REVOKE_THE_GRADEBOOK_COLUMN)

    op.drop_table(AGS_CALL_TABLE)

    op.drop_index(GRADE_SYNC_INDEX, table_name=GRADE_SYNC_TABLE)
    op.drop_table(GRADE_SYNC_TABLE)
    GRADE_SYNC_OUTCOME.drop(op.get_bind())

    op.drop_column(SECTION_TABLE, AGS_LINE_ITEM_COLUMN)
    op.drop_column(SECTION_TABLE, AGS_CONTAINER_COLUMN)
