"""the roster sync's windows, its call log, and the doors it resolves through

Revision ID: e2c94b6a1f70
Revises: b8c41f7d2e05
Create Date: 2026-08-27 11:40:00.000000

E1-11's schema, in one revision, because none of it is separable: the sync cannot
write an enrollment without resolving a member, cannot resolve one without the
definer functions, and cannot be told apart from a section nobody ever synced
without the call log.

**`enrollment` gains the platform's own window.** `lms_window_start` and
`lms_window_end` carry the ADR 0048 extension's values verbatim, nullable, and
NULL means the platform supplied none — SPEC §3.4 has a different denominator for
that student, and it can only choose if the absence was stored honestly. E0-08's
`started_on` and `ended_on` are untouched and keep their meaning as Pulse's own
record of when a member was first and last seen by a sync, which is the open
question that ticket left for E1's sync to settle. ADR 0095 records the semantics.

**`nrps_call` arrives**: one row per NRPS HTTP call, which is SPEC §6.1's call
log, the discriminator between a never-synced section and a synced-empty one, and
the memory the launch trigger's debounce is measured against.

**`user_identity.identity_name` becomes nullable.** ADR 0050 measured that the
roster exposes "an address and no name", so the sync has an address to store for a
user it has no name for; a NOT NULL name would leave it inventing one or storing
nothing. Nullable is a widening, so the downgrade below cannot simply put it back —
see `downgrade`.

**Three SQL files are executed**, in this order and for these reasons:

  - `identity_resolution_v001.sql` — ADR 0094's point-resolution functions, shipped
    byte-identical from E1-11 and E1-12. Whichever branch merges second replays it:
    `CREATE OR REPLACE`, a `pg_roles`-guarded role creation and idempotent `GRANT`s
    make that a no-op rather than an error.
  - `roster_email_v001.sql` — E1-11's D7, the one door an email address reaches
    `user_identity` through. Executed *after* the `identity_name` widening, because
    its function inserts a row naming only `user_id` and `identity_email`.
  - `roster_sync_grants_v001.sql` — D8, what `pulse_app` may do on the three
    relations the sync writes. Executed last, because it grants on `nrps_call`.

**No data migration.** Every column added is nullable, `nrps_call` is empty, and
the widening refuses nothing, so a database with rows in it needs nothing done to
it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "e2c94b6a1f70"
down_revision: str | Sequence[str] | None = "b8c41f7d2e05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCRIPTS = ("identity_resolution_v001", "roster_email_v001", "roster_sync_grants_v001")

WINDOW_START_COLUMN = "lms_window_start"
WINDOW_END_COLUMN = "lms_window_end"

NRPS_CALL_TABLE = "nrps_call"

# What the downgrade puts in `user_identity.identity_name` for a row that has none,
# so the column can be made NOT NULL again. A widening cannot be undone without
# deciding what the rows it permitted become, and the honest answer for a name
# nobody ever supplied is a marker that reads as one rather than an empty string
# somebody's screen would render as a person with no name.
UNKNOWN_NAME = "(name not supplied by the roster)"

# **The two definer roles are emptied and kept, not dropped**, which is E0-10's
# decision for `pulse_reveal_definer` applied unchanged: "a NOLOGIN role holding
# nothing is inert, which the revokes below are what make true", and `DROP ROLE`
# "would also fail against any object elsewhere in the cluster that depends on it,
# which is a confusing way for a downgrade to stop halfway".
#
# It is not a hypothetical here. An earlier spelling of this block did drop them,
# and `role "pulse_resolve_definer" cannot be dropped because some objects depend
# on it` stopped the downgrade with seven column grants still standing —
# `REVOKE … ON ALL TABLES` does not reach a column-grain ACL entry the way a
# table-grain one is reached. And this revision has a second reason E0-10 did not:
# `identity_resolution_v001.sql` ships identically from E1-12, so on a database
# holding both revisions the role belongs to the other one as much as to this.
#
# Each revoke is guarded on the role existing, for the reason that revision gives:
# `REVOKE … FROM <role>` is an error rather than a no-op when the role is absent,
# and a downgrade is exactly the moment somebody is already dealing with a database
# in a state nobody planned. Column grants are revoked at column grain, because
# that is the grain they were granted at.
EMPTY_THE_DEFINER_ROLES = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_resolve_definer') THEN
        REVOKE SELECT (id, lti_platform_id, lms_user_id) ON public."user"
            FROM pulse_resolve_definer;
        REVOKE SELECT (id, user_id) ON public.person FROM pulse_resolve_definer;
        REVOKE ALL ON public."user" FROM pulse_resolve_definer;
        REVOKE ALL ON public.person FROM pulse_resolve_definer;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pulse_roster_definer') THEN
        REVOKE INSERT (user_id, identity_email) ON public.user_identity
            FROM pulse_roster_definer;
        REVOKE UPDATE (identity_email) ON public.user_identity FROM pulse_roster_definer;
        REVOKE SELECT (user_id, identity_email) ON public.user_identity
            FROM pulse_roster_definer;
        REVOKE ALL ON public.user_identity FROM pulse_roster_definer;
    END IF;
END
$$;
"""


def upgrade() -> None:
    """Add the window columns and the call log, widen the name, open the three doors."""
    op.add_column(
        "enrollment", sa.Column(WINDOW_START_COLUMN, sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "enrollment", sa.Column(WINDOW_END_COLUMN, sa.DateTime(timezone=True), nullable=True)
    )

    op.create_table(
        NRPS_CALL_TABLE,
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("members_seen", sa.Integer(), nullable=True),
        sa.Column("called_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["section.id"],
            name=op.f("fk_nrps_call_section_id_section"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nrps_call")),
    )
    op.create_index(
        op.f("ix_nrps_call_section_id"), NRPS_CALL_TABLE, ["section_id"], unique=False
    )

    op.alter_column("user_identity", "identity_name", existing_type=sa.Text(), nullable=True)

    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Close the doors, drop the log, narrow the name back, remove the columns.

    **The name is filled before it is narrowed.** `identity_name` was NOT NULL one
    revision back and this revision permitted rows without one, so putting the
    constraint back has to say what those rows become. A marker that reads as a
    marker is the honest choice; the alternative — refusing the downgrade — leaves
    a database that cannot go back at all.

    **The two resolution functions go with it, and E1-12 is the reason to say so.**
    That ticket ships `identity_resolution_v001.sql` from its own branch, so on a
    database holding both revisions this downgrade removes a door the other one is
    still entitled to. That is the cost of two branches sharing one file, it is
    recorded in ADR 0094, and the repair is to re-run the other revision — which is
    a `CREATE OR REPLACE` replay and does nothing else.

    **The definer roles are emptied rather than dropped**, which E0-10 decided for
    `pulse_reveal_definer` and this follows; see `EMPTY_THE_DEFINER_ROLES` above for
    what dropping them actually did.
    """
    op.execute("DROP FUNCTION IF EXISTS public.record_roster_email(uuid, text)")
    op.execute("DROP FUNCTION IF EXISTS public.resolve_person_for_user(uuid)")
    op.execute("DROP FUNCTION IF EXISTS public.resolve_platform_user(uuid, text)")
    op.execute("REVOKE ALL ON public.enrollment FROM pulse_app")
    op.execute("REVOKE ALL ON public.role_assignment FROM pulse_app")

    op.drop_index(op.f("ix_nrps_call_section_id"), table_name=NRPS_CALL_TABLE)
    op.drop_table(NRPS_CALL_TABLE)

    op.execute(EMPTY_THE_DEFINER_ROLES)

    op.execute(
        sa.text(
            "UPDATE public.user_identity SET identity_name = :marker WHERE identity_name IS NULL"
        ).bindparams(marker=UNKNOWN_NAME)
    )
    op.alter_column("user_identity", "identity_name", existing_type=sa.Text(), nullable=False)

    op.drop_column("enrollment", WINDOW_END_COLUMN)
    op.drop_column("enrollment", WINDOW_START_COLUMN)
