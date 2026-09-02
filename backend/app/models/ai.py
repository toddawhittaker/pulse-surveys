"""What a model was asked, what it answered, and which prompt and model produced it (SPEC §7.4, §8).

SPEC §13 gives this module `classification` and `summary`; E0-13 creates the
first of them and E4 adds the second.

**One row is one classification, and rows are never edited.** SPEC §8:
"`classification` is append-only (re-runs create new rows) with prompt/model
versioning." §6.1's drift panel samples earlier answers to compare against later
ones, §9.3's eval floors compare runs of different prompts and different models,
and a disputed participation grade under §3.3 is answered from the verdict that
decided it — all three read a row that a re-run must not have rewritten.

Append-only is an instrument here rather than a rule somebody remembers:
`classification_grants_v001.sql` gives `pulse_app` `SELECT` and `INSERT` and
nothing else, so the connection the API and the worker hold cannot `UPDATE` or
`DELETE` a row however the application is written
([ADR 0055](../../../docs/adr/0055-a-classification-row-names-its-task-and-no-comment.md)).

**The row names the comment it judged, and E2-08 is what made that possible.**
`classification` shipped without a subject: `response` and `answer` (SPEC §8)
arrived with E2, so there was nothing for a foreign key to point at, and the two
ways to write a subject anyway were both worse than the absence — a nullable
`answer_id` that nothing ever fills, or a hash of the comment text, which is a
re-identification vector over strings as short and as repetitive as "it was okay".
ADR 0055 recorded the choice and promised the reference to E2. `answer_id` is that
reference. It stays **nullable**, because the rows written before E2-08 name no
answer and there is nothing to backfill them from; every row this system writes
from E2-08 onward carries it, and the async re-classification finds a floored
verdict's comment through it.

**Nothing here reads configuration or opens a connection.** `Base` comes from
`app.models.base` rather than from `app.db`, which builds an engine out of
`Settings()` at import time — the epic README's second settled rule, and this is
the module it warns about by name: the gateway that legitimately needs
`AI_PROVIDER_BASE_URL` sits one directory away, and CI's `migration-drift` job
supplies the database variables alone. `app.ai.contracts` is imported, and is
safe to import for the same reason: it declares Pydantic models and reads nothing.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.contracts import ValidityVerdict
from app.models.base import AwareDateTime, Base, UuidPrimaryKey


class ClassificationTask(StrEnum):
    """Which of SPEC §7.4's tasks produced a row's verdict.

    One member, because comment validity is the only task with a caller today.
    Each later ticket that classifies something adds its member in the same
    change as the code that writes it, so the type lists what actually happens
    rather than what is planned — `AuditAction` in `app/models/audit.py` gives
    the same reasoning for the same shape.

    The column is not optional and not a convenience. Two of §7.4's five tasks
    produce a verdict, and their vocabularies overlap without agreeing:
    `nonsense` is a comment-validity verdict *and* a moderation verdict, so a
    stored `nonsense` with no task beside it says two different things and
    cannot be read as either.

    The member's value is its name, as every other enum in this model layer does
    it — one spelling in Python and in the database.
    """

    COMMENT_VALIDITY = "COMMENT_VALIDITY"


# The tokens a comment-validity verdict may be stored as, read off the contract
# rather than spelled again here. ADR 0030 makes the enum member's *value* "the
# token stored, serialised and compared everywhere outside Python", so this is
# that list by construction: a verdict added to or renamed in
# `app/ai/contracts.py` moves the constraint with it, and a second copy would
# have been the one nobody updates (`docs/MISTAKES.md` entry 13).
VALIDITY_VERDICT_TOKENS = tuple(member.value for member in ValidityVerdict)


class Classification(UuidPrimaryKey, Base):
    """One model verdict about one thing, with the pair that reproduces it.

    The prompt version and the model ID are what SPEC §7.4 asks a stored
    classification to carry — "every classification stores prompt version and
    model ID for reproducibility" — and both are `NOT NULL` because an optional
    one gives every reader an auditability field and every row permission to
    carry nothing.

    A row written by the §3.3 fail-open floor carries the pair too, and it says
    so: no prompt file and no model, spelled out in
    `app/ai/tasks.py`'s two constants and recorded in
    [ADR 0054](../../../docs/adr/0054-a-floored-classification-names-the-floor-in-its-audit-pair.md).
    That is what lets a reader tell a verdict a model produced from one produced
    during an outage, which is the difference between failing open and skipping
    a classification silently.
    """

    __tablename__ = "classification"
    __table_args__ = (
        # A verdict is only meaningful inside its task's closed set, and the
        # server is where that holds: the gateway validates the model's answer
        # against the Pydantic contract, and the gateway is not the only writer
        # this table will ever have — E2's async re-classification, a backfill,
        # a repair script. A `nonsense` from the moderation task in a
        # comment-validity row would read as a §3.3 participation decision.
        CheckConstraint(
            f"task <> '{ClassificationTask.COMMENT_VALIDITY}'"
            f" OR verdict IN ({', '.join(repr(token) for token in VALIDITY_VERDICT_TOKENS)})",
            name="verdict_is_in_its_tasks_vocabulary",
        ),
    )

    # Server-side, so that two rows for the same comment can be ordered by when
    # they were written whatever wrote them. `AwareDateTime` refuses a naive
    # value (ADR 0019).
    classified_at: Mapped[datetime] = mapped_column(
        AwareDateTime, nullable=False, server_default=text("now()")
    )
    # The comment this verdict is about (ADR 0055's promised reference, added by
    # E2-08). Nullable for the rows written before there was an `answer` table to
    # point at, and indexed because the read this column exists for is by answer:
    # "every verdict about this comment", which is how the async re-classification
    # finds the floored ones and how a disputed participation grade is answered.
    #
    # `RESTRICT`, like every other foreign key on the survey tables: nothing here
    # removes an audit row by removing something else, and what a retention policy
    # eventually deletes is the retention epic's decision to make out loud.
    answer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("answer.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    task: Mapped[ClassificationTask] = mapped_column(
        Enum(ClassificationTask, name="classification_task"), nullable=False
    )
    # Text rather than a Postgres enum, because one column carries the verdicts
    # of two tasks whose sets differ, and no single enum type is both. The check
    # constraint above is what keeps it closed per task.
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    # The prompt file's path stem — `validity.v1` — so the value names exactly
    # one immutable file with no lookup table between them (ADR 0031, ADR 0032).
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    # The provider's own identifier for the model, as the provider spells it:
    # §9.3's eval floors compare runs of different models, and a normalised name
    # loses the distinction the comparison is about (ADR 0031).
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
