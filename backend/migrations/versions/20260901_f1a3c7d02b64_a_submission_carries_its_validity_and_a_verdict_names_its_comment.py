"""a submission carries its validity and a verdict names its comment

Revision ID: f1a3c7d02b64
Revises: c9b4e0a71d38
Create Date: 2026-09-01 00:00:00.000000

E2-08 writes the first student submission, and it needs two columns and nine
privileges that do not exist yet.

**`response.is_valid`, `NOT NULL` and with no server default.** SPEC §3.3 gates
participation on a "complete, reasonable submission", and §3.4 counts "valid weeks
completed ÷ weeks elapsed to date" — so whether a week counted is a fact about the
row, read later by E3's participation formula and E4's reporting. It is written by
the submit path alone, from the verdicts of the comments the submission carried,
and revised by the async re-classification when a model finally judges a comment
§3.3's fail-open floor stood in for.

No server default in the final schema, for the reason
`app.models.survey.Response`'s two timestamps carry none: a default wins silently
on any insert that omits the column, and a row nobody decided about would then look
decided. The column is added *with* a default and the default is dropped in the
same revision, which is the only way to add a `NOT NULL` column to a table that may
already hold rows; `information_schema.columns` reports none afterwards, which is
what `tests/integration/test_survey_schema.py` asks. `true` rather than `false` for
the backfill because a response that exists was a submission somebody made and no
verdict says otherwise — and because there are no such rows in any environment
today, so the value is a statement about intent rather than a migration of data.

**`classification.answer_id`, nullable, `RESTRICT`, indexed.** ADR 0055 shipped
`classification` with no subject and said why: `answer` did not exist, and the two
ways to name a comment anyway — a column nothing fills, or a hash of the text —
were both worse than the absence. It promised the reference to E2, and this is it.

Nullable because the rows written before this revision name no answer and there is
nothing to backfill them from. `RESTRICT` like every other foreign key on these
tables: an answer a model has judged is one nothing removes as a side effect, which
is what makes the audit trail mean something — and it is also the constraint
[ADR 0115](../../../docs/adr/0115-a-resubmission-revises-its-answers-in-place.md)
is written about, since it is why a resubmission revises its answer rows in place
rather than deleting them. Indexed because the read this column exists for is by
answer: "every verdict about this comment", which is how the re-classification
sweep finds the floored ones.

**The grants.** `survey_submission_grants_v001.sql` carries the whole argument,
including which verbs are withheld and why. In short: `SELECT` on `question_set`
and `question`, because ADR 0110 makes those rows the only statement of §3.2's
ranges and rules; `SELECT, INSERT, UPDATE` on `response`; `SELECT, INSERT, UPDATE,
DELETE` on `answer`. Nothing on `classification`, which already holds `SELECT,
INSERT` and is append-only by the absence of the other two.

**This revision turns `tests/integration/test_identity_grants.py`'s privilege
equality red until its constant gains those nine entries**, and that is the designed
cost rather than a surprise: `RUNTIME_BASE_TABLE_PRIVILEGES` is hand-written and not
derived from these `.sql` files, so that a widening cannot justify itself. The entry
is raised as `docs/disputes/E2-08-03.md`, the same shape `docs/disputes/E2-06-03.md`
took for `survey_window`. `response`'s new column and `classification`'s new
reachability do the same to `tests/integration/test_identity_column_marker.py`'s
record of what carries nothing, raised as `docs/disputes/E2-08-04.md`.

**Chained after `c9b4e0a71d38`**, E2-06's survey-window grants, which is the head
this branch was cut from and the head `alembic heads` reports. E2-09 is being built
in parallel and adds a revision of its own against the same head; whichever merges
second re-points its `down_revision`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "f1a3c7d02b64"
down_revision: str | Sequence[str] | None = "c9b4e0a71d38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The scripts this revision runs. Written out rather than globbed, for the reason
# E0-10's revision gives: a directory listing is not a dependency order, and a file
# added to the directory does nothing until a revision names it.
SCRIPTS = ("survey_submission_grants_v001",)


def upgrade() -> None:
    """Apply this revision."""
    op.add_column(
        "response",
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    # Dropped immediately, so the migrated table matches the model — which declares
    # no default — and so the criterion E2-05 wrote against these rows goes on
    # meaning what it says. See this revision's docstring.
    op.alter_column("response", "is_valid", server_default=None)

    op.add_column("classification", sa.Column("answer_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_classification_answer_id"), "classification", ["answer_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_classification_answer_id_answer"),
        "classification",
        "answer",
        ["answer_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    for script in SCRIPTS:
        op.execute(read_sql(script))


def downgrade() -> None:
    """Undo this revision."""
    op.execute(
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON public.answer FROM pulse_app"
    )
    op.execute("REVOKE SELECT, INSERT, UPDATE ON public.response FROM pulse_app")
    op.execute("REVOKE SELECT ON public.question FROM pulse_app")
    op.execute("REVOKE SELECT ON public.question_set FROM pulse_app")

    op.drop_constraint(
        op.f("fk_classification_answer_id_answer"), "classification", type_="foreignkey"
    )
    op.drop_index(op.f("ix_classification_answer_id"), table_name="classification")
    op.drop_column("classification", "answer_id")
    op.drop_column("response", "is_valid")
