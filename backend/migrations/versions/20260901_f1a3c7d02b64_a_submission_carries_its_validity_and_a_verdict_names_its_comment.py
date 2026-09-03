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

**Chained after `d3a71b5c8e42`**, E2-09's student-read grants. This branch was cut
from `c9b4e0a71d38`, E2-06's survey-window grants, and E2-09 was built in parallel
against the same head; both revisions said whichever merged second would re-point
its `down_revision`, and this is the one that did.

**Two consequences of merging second, and both are in the code below.** The
`SELECT` privileges this revision's `.sql` file grants on `question_set`,
`question`, `response` and `answer` are already held by the time it runs — a
`GRANT` of a privilege a role has is a no-op, and the file stays as it was written
because a versioned script is the immutable record of what its author applied
(ADR 0041). And the `downgrade()` takes back **only the verbs this revision adds**:
`INSERT` and `UPDATE` on `response`, `INSERT`, `UPDATE` and `DELETE` on `answer`.
Revoking `SELECT` on the four would leave the schema at `d3a71b5c8e42` with E2-09's
read path unable to read, which is a downgrade undoing somebody else's revision.

**The downgrade preserves both columns and the upgrade restores them** (E2-16).
Neither is derivable from what the downgrade leaves, and both failed silently:
the upgrade's `true` backfill wrote *valid* over every response, so a submission a
model had judged nonsense came back counting toward §3.4's participation, and
`classification.answer_id` came back NULL, so a floored verdict named no comment.
The second is the worse of the two. Both legs of `app/services/validity.py`'s
re-classification sweep filter `answer_id IS NOT NULL`, and `classification` takes
no `UPDATE` (ADR 0055) — so a verdict that lost its answer is invisible to the
sweep for ever and nothing can repair it.

**The repair is an edit to this revision rather than a new one.** A later revision
can add a column and cannot repair a `downgrade()`; the broken path is this file's.
What has already run everywhere is this revision's `upgrade()` against a `response`
table with no rows in it, where the backfill and the restore below are both
no-ops — so the edit changes nothing that has happened and repairs the two paths
that have never run anywhere.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.views_sql import read_sql

# revision identifiers, used by Alembic.
revision: str = "f1a3c7d02b64"
down_revision: str | Sequence[str] | None = "d3a71b5c8e42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The scripts this revision runs. Written out rather than globbed, for the reason
# E0-10's revision gives: a directory listing is not a dependency order, and a file
# added to the directory does nothing until a revision names it.
SCRIPTS = ("survey_submission_grants_v001",)

# ---------------------------------------------------------------------------
# What the downgrade keeps, and where (E2-16). Neither scratch table is in
# `Base.metadata` and neither is meant to be: each exists only between a
# downgrade and the upgrade that restores from it, and the upgrade drops it — so
# a database standing at head never has one and `alembic check` never sees it.
#
# Both are keyed by the row's own primary key. A restore that put two responses'
# verdicts back on each other would leave the set of stored values exactly right
# and swap which week counted, and one that swapped two verdicts' answers would
# attribute a model's judgement to a comment it never read; neither raises
# anything, and a keyed restore is what makes both unwritable.
# ---------------------------------------------------------------------------
VALIDITY_PRESERVED = "response_is_valid_preserved"
VERDICT_ANSWER_PRESERVED = "classification_answer_id_preserved"

PRESERVE_THE_VALIDITIES = f"""
DROP TABLE IF EXISTS public.{VALIDITY_PRESERVED};
CREATE TABLE public.{VALIDITY_PRESERVED} (
    response_id uuid PRIMARY KEY,
    is_valid boolean NOT NULL
);
INSERT INTO public.{VALIDITY_PRESERVED} (response_id, is_valid)
SELECT id, is_valid FROM public.response;
"""

# `answer_id` is nullable, and a preserved null has to come back as a null: a
# bounce stores no comment (ADR 0114, the 2026-09-03 ruling), so its verdict names
# none and a restore that "repaired" it would invent a subject for a judgement
# about text this system deliberately does not keep. The column is nullable here
# for that reason.
PRESERVE_THE_VERDICT_ANSWERS = f"""
DROP TABLE IF EXISTS public.{VERDICT_ANSWER_PRESERVED};
CREATE TABLE public.{VERDICT_ANSWER_PRESERVED} (
    classification_id uuid PRIMARY KEY,
    answer_id uuid
);
INSERT INTO public.{VERDICT_ANSWER_PRESERVED} (classification_id, answer_id)
SELECT id, answer_id FROM public.classification;
"""

# The restore runs while `is_valid` is still carrying this revision's `true`
# default, and overwrites it for every response that has been here before. A
# response with no preserved row keeps the `true` — which is a database that has
# never been downgraded, where the value is a statement about intent and there are
# no rows to make it about anything else.
RESTORE_THE_VALIDITIES = f"""
DO $$
BEGIN
    IF to_regclass('public.{VALIDITY_PRESERVED}') IS NULL THEN
        RETURN;
    END IF;

    UPDATE public.response AS r
       SET is_valid = kept.is_valid
      FROM public.{VALIDITY_PRESERVED} AS kept
     WHERE kept.response_id = r.id;

    DROP TABLE public.{VALIDITY_PRESERVED};
END
$$;
"""

RESTORE_THE_VERDICT_ANSWERS = f"""
DO $$
BEGIN
    IF to_regclass('public.{VERDICT_ANSWER_PRESERVED}') IS NULL THEN
        RETURN;
    END IF;

    UPDATE public.classification AS c
       SET answer_id = kept.answer_id
      FROM public.{VERDICT_ANSWER_PRESERVED} AS kept
     WHERE kept.classification_id = c.id;

    DROP TABLE public.{VERDICT_ANSWER_PRESERVED};
END
$$;
"""


def upgrade() -> None:
    """Apply this revision.

    **Each restore runs before the constraint that would judge it.**
    `is_valid` is put back while the column is still defaulted and before the
    default is dropped; `answer_id` is put back before its foreign key exists, so a
    preserved answer whose row did not come back is reported by that key rather
    than silently accepted. Both are no-ops on a database that has never been
    downgraded, which is every database this revision has actually run against.
    """
    op.add_column(
        "response",
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.execute(RESTORE_THE_VALIDITIES)
    # Dropped immediately, so the migrated table matches the model — which declares
    # no default — and so the criterion E2-05 wrote against these rows goes on
    # meaning what it says. See this revision's docstring.
    op.alter_column("response", "is_valid", server_default=None)

    op.add_column("classification", sa.Column("answer_id", sa.Uuid(), nullable=True))
    op.execute(RESTORE_THE_VERDICT_ANSWERS)
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
    """Undo this revision, keeping the two columns' values for the upgrade to put back.

    **Preserved before anything is dropped**, and the scratch tables stay while the
    database sits at the older revision — that is where the values live in the
    meantime, and the upgrade is the only thing that removes them. See this
    revision's docstring for what each one loses without this.
    """
    op.execute(PRESERVE_THE_VALIDITIES)
    op.execute(PRESERVE_THE_VERDICT_ANSWERS)

    # Only the verbs this revision adds. `SELECT` on these four is
    # `d3a71b5c8e42`'s — see this revision's docstring — and taking it back here
    # would leave E2-09's read path unable to read at a revision that grants it.
    op.execute("REVOKE INSERT, UPDATE, DELETE ON public.answer FROM pulse_app")
    op.execute("REVOKE INSERT, UPDATE ON public.response FROM pulse_app")

    op.drop_constraint(
        op.f("fk_classification_answer_id_answer"), "classification", type_="foreignkey"
    )
    op.drop_index(op.f("ix_classification_answer_id"), table_name="classification")
    op.drop_column("classification", "answer_id")
    op.drop_column("response", "is_valid")
