"""a response names one term's section and week, and the sweep gets its index

Revision ID: b1e7d4a90c26
Revises: f1a3c7d02b64
Create Date: 2026-09-03 00:00:00.000000

E2-16, items 3 and 4. Two changes that are not the same subject and travel
together because they are one ticket's schema and there is no second migration
in this batch to carry either.

**`response` gets the term-agreement rule `survey_window` has had since E2-05.**
ADR 0018's problem, on the table that stores what students actually submitted: a
`CHECK` cannot read another table, so "this response's section and its week
belong to the same term" is expressible only as a term carried on the row and two
composite foreign keys that make the two references agree with it. The
epic-boundary data-model review wrote a response pairing a section in one term
with a week in another **by insert**, and the database took it — SPEC §2.2 puts
the week axis inside a term, so that row records a submission against a week its
own section's calendar does not contain, and §3.4's participation ratio is then
counted over two different calendars.

The mechanism is `survey_window`'s, spelled the same way and referencing the same
two uniques (`uq_section_id_term_id`, `uq_week_id_term_id`, both created by
`3f6907349751`): `(section_id, term_id)` into `section (id, term_id)` and
`(week_id, term_id)` into `week (id, term_id)`, and the two plain foreign keys
they replace are dropped, so a reference is checked once rather than twice.

**`term_id` is `NOT NULL`, and that is what makes both limbs bite.** Postgres
evaluates a composite foreign key under `MATCH SIMPLE`, which skips the check
entirely when any column of the key is null — so a nullable term column would be a
documented way of storing the exact row this revision exists to refuse. It is
added nullable, backfilled from `section.term_id` (`NOT NULL` since E0-06, and a
section belongs to exactly one term), and only then made `NOT NULL`; a stored
response whose section is in a term is a response in that term, which is the same
statement the composite key then holds.

**`ix_classification_task_prompt_version`.** The re-classification sweep's floored
leg selects one task's rows written under the floor's prompt version (ADR 0054's
audit pair), and without an index on that pair it reads the whole of
`classification` on every run — on a beat and on every floored submission, at a
table that grows with every comment ever classified. The boundary review measured
the sweep at 72 seconds over ~300k rows, 46 with this index alone, and 166ms with
this index beside the anti-join rewrite in `app/services/validity.py`, which is
why both halves ship together and neither is the other's substitute.

**Nothing is preserved and the downgrade is a clean reverse**, which is not the
disposition the two revisions below this one now take. What this revision adds is
derivable: `response.term_id` is `section.term_id` for the row's own section, so a
downgrade that drops it loses nothing an upgrade cannot compute again — and it
does, from the same statement. An index carries no data at all. That is the test
for whether a preserve is owed, rather than a habit of writing one.

**No grants.** `pulse_app` already holds `SELECT, INSERT, UPDATE` on
`public.response` as table privileges (`survey_submission_grants_v001.sql`), and a
table privilege covers a column added afterwards, so a column needs no new verb —
checked against `RUNTIME_BASE_TABLE_PRIVILEGES` in
`tests/integration/test_identity_grants.py`, which is a table-and-verb inventory
and is unchanged by this revision. An index is not a grantable object.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1e7d4a90c26"
down_revision: str | Sequence[str] | None = "f1a3c7d02b64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The uniques the two composite limbs reference. Created by `3f6907349751` for
# `survey_window`'s copy of this rule, and referenced rather than re-created:
# `section` and `week` each carry exactly one, and a second would be a second
# rule that can disagree with the first.
SECTION_TERM_UNIQUE = "uq_section_id_term_id"
WEEK_TERM_UNIQUE = "uq_week_id_term_id"

# The two plain foreign keys this revision replaces, as `3f6907349751` named them,
# and the composite ones that take their place. Spelled to match the naming
# convention on `Base.metadata` character for character, which `alembic check`
# keeps honest.
SECTION_FK = "fk_response_section_id_section"
WEEK_FK = "fk_response_week_id_week"
SECTION_TERM_FK = "fk_response_section_id_term_id_section"
WEEK_TERM_FK = "fk_response_week_id_term_id_week"

TERM_COLUMN = "term_id"

# The pair the sweep's floored leg filters on, in the order it filters them:
# `classification.task` first, because it is the equality that is always present,
# and the prompt version beside it.
SWEEP_INDEX = "ix_classification_task_prompt_version"
SWEEP_INDEX_COLUMNS = ["task", "prompt_version"]

# Every response takes its own section's term. One statement rather than a
# PL/pgSQL block, because it only changes data and never refuses: `section.term_id`
# is `NOT NULL` and `response.section_id` is a foreign key into `section`, so there
# is no response this leaves unfilled and no state for a refusal to describe. An
# `alembic upgrade --sql` script carries it as it stands.
BACKFILL_THE_TERMS = f"""
UPDATE public.response AS r
   SET {TERM_COLUMN} = s.{TERM_COLUMN}
  FROM public.section AS s
 WHERE s.id = r.section_id
"""


def upgrade() -> None:
    """Apply this revision: the response's term rule, then the sweep's index.

    The order the server needs: the column, filled, made `NOT NULL`, then the
    limbs that reference it — and the plain foreign keys dropped last, after the
    composite ones that replace them, so there is no moment inside this
    transaction when a response's section or week is unreferenced.
    """
    op.add_column("response", sa.Column(TERM_COLUMN, sa.Uuid(), nullable=True))
    op.execute(BACKFILL_THE_TERMS)
    op.alter_column("response", TERM_COLUMN, nullable=False)

    op.create_foreign_key(
        SECTION_TERM_FK,
        "response",
        "section",
        ["section_id", TERM_COLUMN],
        ["id", TERM_COLUMN],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        WEEK_TERM_FK,
        "response",
        "week",
        ["week_id", TERM_COLUMN],
        ["id", TERM_COLUMN],
        ondelete="RESTRICT",
    )
    op.drop_constraint(SECTION_FK, "response", type_="foreignkey")
    op.drop_constraint(WEEK_FK, "response", type_="foreignkey")

    op.create_index(op.f(SWEEP_INDEX), "classification", SWEEP_INDEX_COLUMNS, unique=False)


def downgrade() -> None:
    """Reverse this revision: `response` back to two plain keys, the index gone.

    A true reversal, and it preserves nothing because there is nothing here that
    an upgrade cannot recompute: `term_id` is the row's own section's term, which
    `upgrade` fills from `section` whenever it runs. The plain foreign keys are
    put back before the composite ones are dropped, for the reason the upgrade
    gives in the other direction.
    """
    op.drop_index(op.f(SWEEP_INDEX), table_name="classification")

    op.create_foreign_key(
        SECTION_FK, "response", "section", ["section_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(WEEK_FK, "response", "week", ["week_id"], ["id"], ondelete="RESTRICT")
    op.drop_constraint(SECTION_TERM_FK, "response", type_="foreignkey")
    op.drop_constraint(WEEK_TERM_FK, "response", type_="foreignkey")
    op.drop_column("response", TERM_COLUMN)
