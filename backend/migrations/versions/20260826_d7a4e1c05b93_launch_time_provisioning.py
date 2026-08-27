"""launch-time provisioning: the title marker, the roster address and the defect record

Revision ID: d7a4e1c05b93
Revises: c4f81a2e6b39
Create Date: 2026-08-26 17:40:00.000000

E1-10 makes the first staff launch of a section the thing that discovers it
(SPEC §7.3, §2.1), and this revision is the schema that write needs:

  - `course.title_is_fallback`, Pulse's own record of whether `lms_title` is the
    platform's value or the "PREFIX NUMBER" stand-in launch-time ingestion writes
    when a context carries no title (ADR 0091). `NOT NULL DEFAULT false`, so every
    row that existed before this column claims the title it holds is the LMS's,
    which is true of all of them.
  - `section.lms_context_memberships_url`, §7.3's stored roster service address —
    nullable, because a section nobody has staff-launched has none and that is a
    state rather than a missing value.
  - `launch_defect`, the append-only record of a launch whose context could not be
    ingested, with `launch_defect_kind` as the closed set of the five rules that
    refuse one. Its field set is deliberately five values beside the key and is
    asserted as an equality in the ticket's own suite (SPEC §10).

It then executes `launch_provisioning_grants_v001.sql`, which is the instrument
ADR 0045 deferred to E1: the narrowest grant this writer needs, with `UPDATE` at
column grain so the application connection cannot reach ADR 0021's derived
calendar or `course.lms_number`. The reasoning for every line of it is in that
file, and the models carry the reasoning for the columns.

**`alembic check` compares the columns and the table** — all three are on
`Base.metadata` — and does not compare the grant, which
`tests/integration/test_identity_grants.py` pins as equalities against
`RUNTIME_BASE_TABLE_PRIVILEGES` and `RUNTIME_COLUMN_PRIVILEGES`.

**The downgrade** drops the table (its privileges go with the relation), drops the
enum type the table's column created, revokes what this file granted on relations
that outlive it, and drops the two columns.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "d7a4e1c05b93"
down_revision: str | Sequence[str] | None = "c4f81a2e6b39"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)

# Spelled out rather than imported from `app.models.lti`, for the reason E0-05's
# and E0-07's revisions both give: a migration records what was applied on the day
# it ran, and importing an application enum would make this revision change
# meaning whenever that class did.
LAUNCH_DEFECT_KIND = sa.Enum(
    "unparseable_context_label",
    "unknown_prefix",
    "out_of_band_course_number",
    "no_term_for_launch_date",
    "section_code_underivable",
    name="launch_defect_kind",
)

SCRIPTS = ("launch_provisioning_grants_v001",)

# The grants this revision issues on relations that survive its downgrade. Written
# out as statements rather than assembled from the file above, because a revoke is
# not the mechanical inverse of a grant — `REVOKE UPDATE` removes the column
# privileges with it — and because the file is immutable while this list is what
# this revision did (ADR 0041).
REVOKES = (
    "REVOKE SELECT ON public.prefix FROM pulse_app",
    "REVOKE SELECT ON public.term FROM pulse_app",
    "REVOKE SELECT ON public.start_letter_map FROM pulse_app",
    "REVOKE SELECT, INSERT, UPDATE ON public.course FROM pulse_app",
    "REVOKE SELECT, INSERT, UPDATE ON public.section FROM pulse_app",
    'REVOKE SELECT, INSERT ON public."user" FROM pulse_app',
)


def upgrade() -> None:
    """Add the two columns, create the defect record, and grant the launch writer."""
    op.add_column(
        "course",
        sa.Column(
            "title_is_fallback",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column("section", sa.Column("lms_context_memberships_url", sa.Text(), nullable=True))
    op.create_table(
        "launch_defect",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("kind", LAUNCH_DEFECT_KIND, nullable=False),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("deployment_id", sa.Text(), nullable=False),
        sa.Column("context_id", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_launch_defect")),
    )
    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Undo this revision, privileges first on the relations that outlive it."""
    for statement in REVOKES:
        op.execute(statement)
    op.drop_table("launch_defect")
    # Autogenerate does not emit this. `CREATE TYPE` rode in with the `kind`
    # column above, so without the matching drop the type outlives the table that
    # used it and the next upgrade fails with "type launch_defect_kind already
    # exists" — a downgrade that cannot be undone.
    LAUNCH_DEFECT_KIND.drop(op.get_bind())
    op.drop_column("section", "lms_context_memberships_url")
    op.drop_column("course", "title_is_fallback")
