"""a section is bound to the context it was discovered from

Revision ID: b8c41f7d2e05
Revises: d7a4e1c05b93
Create Date: 2026-08-26 22:15:00.000000

E1-10's round-3 security review, as schema. A section had no identity of its own:
it was resolved by what its context label parsed to — prefix, number, section
code — and a course copy reproduces all three, so a staff launch from the copy
resolved the *original* section and repointed its stored roster address. This
revision gives `section` the identity a copy cannot reproduce:

  - `lms_context_id`, the context claim's `id` — the platform's own value,
    verbatim;
  - `lti_deployment_id`, the registration it was issued under, because a context
    identifier is unique within a deployment and means nothing across them;
  - `UNIQUE (lti_deployment_id, lms_context_id)`, in the database rather than only
    in the writer, because ADR 0045's "a caller can bypass it by not calling it"
    applies to E1-11's sync as much as to anything else.

`launch_defect_kind` grows the two kinds the same review added, and
`launch_provisioning_grants_v002.sql` narrows the application role's read of
`user` from the table to its key column. ADR 0091 carries the reasoning for all
three.

**A separate revision rather than an edit to `d7a4e1c05b93`.** That revision is
applied on every reviewer's database and its grants file is immutable once the
branch is pushed (ADR 0041), and the `user` grant is the file that changes — so a
second revision with a `_v002.sql` beside it is the shape this repository already
uses for a narrowed grant (`identity_grants_v001` → `identity_grants_v002`).

**Existing sections.** Both binding columns are `NOT NULL`, and a database that
already holds sections has no binding to give them — the demo seed's sections are
fiction and were never launched. They are bound to the one registered deployment
under a synthetic context identifier no platform issues, so a later real launch
cannot collide with one; and where that cannot be done unambiguously — no
registration at all, or more than one — the upgrade **refuses and says so**,
which is the disposition `9a71c4be0d3f` already takes for rows a new rule cannot
be applied to. A fabricated binding that a real launch could collide with would be
worse than a refusal.

**The refusal points at registering a platform and at nothing else**, which the
round-3 security re-pass asked for: an earlier wording offered "or drop them" as
the second way out, and the reader of that sentence is somebody whose upgrade is
failing, under time pressure, taking anything the message sanctions. On the demo
stack those rows are fiction; on any database that matters they are sections with
responses hanging off them.

Both the backfill and that refusal are one PL/pgSQL block rather than a read in
Python, so `alembic upgrade --sql` emits a script that carries them; see the
comment on `BIND_EXISTING_SECTIONS`.

**The downgrade drops the columns and restores the wider grant**, and leaves the
two enum labels in place: Postgres cannot remove a label from a type, so the
upgrade adds them with `IF NOT EXISTS` and re-running it after a downgrade is a
no-op rather than an error.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "b8c41f7d2e05"
down_revision: str | Sequence[str] | None = "d7a4e1c05b93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCRIPTS = ("launch_provisioning_grants_v002",)

# The two kinds round 3 added. Spelled out rather than imported from
# `app.models.lti`, for the reason every other revision here gives: a migration
# records what was applied on the day it ran.
NEW_DEFECT_KINDS = ("context_collision", "roster_address_refused")

CONTEXT_ID_COLUMN = "lms_context_id"
DEPLOYMENT_COLUMN = "lti_deployment_id"

# What a section that predates the binding is stamped with. The prefix is not a
# value any platform issues — a context id is the platform's own opaque string —
# so a real launch cannot resolve one of these rows, which is the whole point of
# backfilling rather than refusing.
BACKFILL_CONTEXT_ID = "pre-binding-section-"

# Give every stored section a binding, or stop the upgrade and say why.
#
# **One PL/pgSQL block rather than a read in Python**, and that is about `alembic
# upgrade --sql`. `9a71c4be0d3f` faces the same question and answers it
# differently — it skips its validation offline and emits a comment saying so —
# and it can, because it only *checks*. This one has to **change data** before the
# `NOT NULL` two statements down, so a script that omitted it would not apply. In
# a block, the offline script carries the whole thing and does the right thing
# wherever it is run.
#
# The refusal is a `RAISE`, which aborts the transaction the migration runs in, so
# a database that cannot be bound unambiguously is left exactly as it was.
BIND_EXISTING_SECTIONS = f"""
DO $$
DECLARE
    unbound bigint;
    registrations bigint;
    only_registration uuid;
BEGIN
    SELECT count(*) INTO unbound
      FROM public.section WHERE {DEPLOYMENT_COLUMN} IS NULL;
    IF unbound = 0 THEN
        RETURN;
    END IF;

    SELECT count(*) INTO registrations FROM public.lti_deployment;
    IF registrations <> 1 THEN
        RAISE EXCEPTION
            'E1-10: % section(s) here predate the context binding and this database holds % '
            'registered deployment(s), so there is no unambiguous one to bind them to. Both '
            'binding columns are NOT NULL. Register the platform those sections came from — '
            'exactly one registration has to be resolvable — and run this again. A binding '
            'invented here would be one a real launch could collide with, which is the failure '
            'this revision exists to prevent.', unbound, registrations;
    END IF;

    SELECT id INTO only_registration FROM public.lti_deployment;
    UPDATE public.section
       SET {DEPLOYMENT_COLUMN} = only_registration,
           {CONTEXT_ID_COLUMN} = '{BACKFILL_CONTEXT_ID}' || id::text
     WHERE {DEPLOYMENT_COLUMN} IS NULL;
END
$$;
"""


def upgrade() -> None:
    """Bind sections to their contexts, widen the defect kinds, narrow the `user` read."""
    for kind in NEW_DEFECT_KINDS:
        op.execute(f"ALTER TYPE launch_defect_kind ADD VALUE IF NOT EXISTS '{kind}'")

    op.add_column("section", sa.Column(CONTEXT_ID_COLUMN, sa.Text(), nullable=True))
    op.add_column("section", sa.Column(DEPLOYMENT_COLUMN, sa.Uuid(), nullable=True))
    op.execute(BIND_EXISTING_SECTIONS)
    op.alter_column("section", CONTEXT_ID_COLUMN, nullable=False)
    op.alter_column("section", DEPLOYMENT_COLUMN, nullable=False)
    op.create_foreign_key(
        op.f("fk_section_lti_deployment_id_lti_deployment"),
        "section",
        "lti_deployment",
        [DEPLOYMENT_COLUMN],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        op.f("uq_section_lti_deployment_id_lms_context_id"),
        "section",
        [DEPLOYMENT_COLUMN, CONTEXT_ID_COLUMN],
    )

    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Undo this revision: the wider grant back, the binding gone, the labels left."""
    op.execute('REVOKE SELECT (id) ON public."user" FROM pulse_app')
    op.execute('GRANT SELECT ON public."user" TO pulse_app')
    op.drop_constraint(op.f("uq_section_lti_deployment_id_lms_context_id"), "section", type_="unique")
    op.drop_constraint(
        op.f("fk_section_lti_deployment_id_lti_deployment"), "section", type_="foreignkey"
    )
    op.drop_column("section", DEPLOYMENT_COLUMN)
    op.drop_column("section", CONTEXT_ID_COLUMN)
