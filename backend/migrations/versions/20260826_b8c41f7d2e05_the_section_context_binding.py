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

**The downgrade preserves every section's binding before it drops it**, into
`section_binding_preserved` — one row per section, carrying the section's own
primary key, its `lms_context_id` and its `lti_deployment_id` — and the upgrade
restores from that table, by key, and drops it. So the round trip is the
identity this docstring used to claim it was without doing anything to earn it.
It also restores the wider grant and leaves the two enum labels in place:
Postgres cannot remove a label from a type, so the upgrade adds them with
`IF NOT EXISTS` and re-running it after a downgrade is a no-op rather than an
error.

**What the preserve/restore is worth, stated plainly** (the E1 boundary review's
H2). Before it, a downgrade and re-upgrade left every bound section reading
`pre-binding-section-<uuid>`: the backfill below cannot tell a section whose
binding was just dropped from one that never had a binding, so it invented one.
Nothing a platform issues looks like that value, and the application holds no
`UPDATE` on the column, so every staff launch from the section's real context
was refused as a `context_collision` from then on, permanently, with nothing in
the failure saying a downgrade had caused it.
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

# Where a downgrade puts the bindings it is about to drop, and where the upgrade
# looks for them. Not in `Base.metadata` and not meant to be: it exists only
# between a downgrade and the upgrade that restores from it, and the upgrade
# drops it — so a database standing at head never has it and `alembic check`
# never sees it.
PRESERVED_TABLE = "section_binding_preserved"
PRESERVED_KEY_COLUMN = "section_id"

# Keep every section's binding, keyed by the section's own primary key.
#
# **Keyed, and not merely kept.** Restoring two preserved pairs onto the wrong
# two sections would leave the set of stored bindings exactly right and point
# each section at the other's context — the repointing the binding was added to
# prevent, arriving through a migration instead of through a launch. The key is
# the primary key, and it is the primary key of this table too, so a second copy
# of a section's binding cannot be written at all.
#
# **Dropped first, so a second trip is like the first.** A downgrade is the
# operation somebody repeats, and a `CREATE TABLE` that raised on the leftovers
# of the last trip — or an insert that added a second copy per section beside
# them — is a failure that only ever shows up the second time.
PRESERVE_THE_BINDINGS = f"""
DROP TABLE IF EXISTS public.{PRESERVED_TABLE};
CREATE TABLE public.{PRESERVED_TABLE} (
    {PRESERVED_KEY_COLUMN} uuid PRIMARY KEY,
    {CONTEXT_ID_COLUMN} text NOT NULL,
    {DEPLOYMENT_COLUMN} uuid NOT NULL
);
INSERT INTO public.{PRESERVED_TABLE}
    ({PRESERVED_KEY_COLUMN}, {CONTEXT_ID_COLUMN}, {DEPLOYMENT_COLUMN})
SELECT id, {CONTEXT_ID_COLUMN}, {DEPLOYMENT_COLUMN} FROM public.section;
"""

# Give every section its preserved binding back, then take the table away.
#
# **One PL/pgSQL block, for `BIND_EXISTING_SECTIONS`'s reason**: `alembic upgrade
# --sql` has to carry this, and it has to do the right thing on a database that
# never went down — where the table is simply absent and there is nothing to
# restore. `to_regclass` answers NULL for a table that is not there rather than
# raising, which is what makes that check a branch instead of an error.
#
# It runs **before** the backfill, so a section whose binding came back is not
# unbound by the time the backfill counts, and the `registrations <> 1` refusal
# below cannot fire over rows that were never in question.
#
# The table is dropped on the way out: it exists to carry values across one
# round trip, and a database at head that still had it would be one `alembic
# check` reports a difference for.
RESTORE_PRESERVED_BINDINGS = f"""
DO $$
BEGIN
    IF to_regclass('public.{PRESERVED_TABLE}') IS NULL THEN
        RETURN;
    END IF;

    UPDATE public.section AS s
       SET {CONTEXT_ID_COLUMN} = kept.{CONTEXT_ID_COLUMN},
           {DEPLOYMENT_COLUMN} = kept.{DEPLOYMENT_COLUMN}
      FROM public.{PRESERVED_TABLE} AS kept
     WHERE kept.{PRESERVED_KEY_COLUMN} = s.id;

    DROP TABLE public.{PRESERVED_TABLE};
END
$$;
"""

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
    """Bind sections to their contexts, widen the defect kinds, narrow the `user` read.

    **The restore comes before the backfill**, and the order is the whole of what
    makes the round trip an identity: a section whose binding a downgrade
    preserved gets it back first, so the backfill sees it as bound and invents
    nothing for it. On a database that has never been downgraded there is no
    preserved table, the restore returns, and this reads exactly as it did.
    """
    for kind in NEW_DEFECT_KINDS:
        op.execute(f"ALTER TYPE launch_defect_kind ADD VALUE IF NOT EXISTS '{kind}'")

    op.add_column("section", sa.Column(CONTEXT_ID_COLUMN, sa.Text(), nullable=True))
    op.add_column("section", sa.Column(DEPLOYMENT_COLUMN, sa.Uuid(), nullable=True))
    op.execute(RESTORE_PRESERVED_BINDINGS)
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
    """Undo this revision: the binding kept then dropped, the wider grant back, the labels left.

    **What is preserved, and where.** Every section's `lms_context_id` and
    `lti_deployment_id` are copied into `public.section_binding_preserved`, one
    row per section keyed by the section's own primary key, before the columns
    are dropped — and `upgrade` restores from that table by key and drops it. A
    downgrade is not a discard here: the values are the platform's own, the
    application holds no `UPDATE` on the column, and a section that lost them
    would be refused on every staff launch from its real context for ever (the
    E1 boundary review, H2).

    The preserved table is left standing while the database sits at the older
    revision — that is where the values live in the meantime — and the only
    thing that removes it is the upgrade that puts them back. A database walked
    down and then abandoned keeps a small table nothing reads, which is the
    right trade against losing bindings nothing can reconstruct.
    """
    op.execute(PRESERVE_THE_BINDINGS)
    op.execute('REVOKE SELECT (id) ON public."user" FROM pulse_app')
    op.execute('GRANT SELECT ON public."user" TO pulse_app')
    op.drop_constraint(op.f("uq_section_lti_deployment_id_lms_context_id"), "section", type_="unique")
    op.drop_constraint(
        op.f("fk_section_lti_deployment_id_lti_deployment"), "section", type_="foreignkey"
    )
    op.drop_column("section", DEPLOYMENT_COLUMN)
    op.drop_column("section", CONTEXT_ID_COLUMN)
