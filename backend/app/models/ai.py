"""What a model was asked, what it answered, and which prompt and model produced it (SPEC §7.4, §8).

SPEC §13 gives this module `classification`, which E0-13 creates. The stored
summary §13 once put here lives in `report.py` as `weekly_summary` (ADR 0145).

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

**A moderation row has one writer.** Since E6-01 a `MODERATION` row is written
only by the routing definer `public.route_moderation_verdict`, which writes its
route in the same call, and a trigger refuses one written by any other role, so
the `INSERT` above writes validity rows only (`moderation_routing_v001.sql`,
ADR 0187).

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

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.contracts import ModerationVerdict, ValidityVerdict
from app.models.base import AwareDateTime, Base, UuidPrimaryKey


class ClassificationTask(StrEnum):
    """Which of SPEC §7.4's tasks produced a row's verdict.

    Two members. Comment validity arrived with E0-13; moderation arrived with
    E6-01, in the same change as its one writer, the routing definer
    `public.route_moderation_verdict` (`views_sql/moderation_routing_v001.sql`,
    ADR 0187). Each later ticket that classifies something adds its member in the
    same change as the code that writes it, so the type lists what actually
    happens rather than what is planned — `AuditAction` in `app/models/audit.py`
    gives the same reasoning for the same shape.

    The column is not optional and not a convenience. Two of §7.4's five tasks
    produce a verdict, and their vocabularies overlap without agreeing:
    `nonsense` is a comment-validity verdict *and* a moderation verdict, so a
    stored `nonsense` with no task beside it says two different things and
    cannot be read as either.

    The member's value is its name, as every other enum in this model layer does
    it — one spelling in Python and in the database.
    """

    COMMENT_VALIDITY = "COMMENT_VALIDITY"
    MODERATION = "MODERATION"


# The tokens a comment-validity verdict may be stored as, read off the contract
# rather than spelled again here. ADR 0030 makes the enum member's *value* "the
# token stored, serialised and compared everywhere outside Python", so this is
# that list by construction: a verdict added to or renamed in
# `app/ai/contracts.py` moves the constraint with it, and a second copy would
# have been the one nobody updates (`docs/MISTAKES.md` entry 13).
VALIDITY_VERDICT_TOKENS = tuple(member.value for member in ValidityVerdict)
# The moderation task's six, read off its contract the same way (E6-01).
MODERATION_VERDICT_TOKENS = tuple(member.value for member in ModerationVerdict)

# Which verdicts each task may store. Every member of `ClassificationTask` has an
# entry, and the verdict `CHECK` below is built from this mapping, so a task with
# no vocabulary cannot store a row at all rather than storing any word it likes.
VERDICT_TOKENS_OF_TASK: dict[ClassificationTask, tuple[str, ...]] = {
    ClassificationTask.COMMENT_VALIDITY: VALIDITY_VERDICT_TOKENS,
    ClassificationTask.MODERATION: MODERATION_VERDICT_TOKENS,
}


def verdict_is_in_its_tasks_vocabulary() -> str:
    """The verdict `CHECK`'s body: each task's row holds one of that task's own tokens.

    One disjunct per task, each pairing the task with its own closed set. A single
    `verdict IN (...)` over the union of the two sets would accept a `MODERATION`
    row saying `substantive` and a validity row saying `threat`; a validity row
    that says `threat` routes nothing and counts toward nobody's credit, and a
    moderation row that says `substantive` would be a comment shown with no
    moderation decision at all (E6-01 criterion 6). `nonsense` is in both sets
    and is accepted under both tasks, which is correct.
    """
    return " OR ".join(
        f"(task = '{task.value}' AND verdict IN ({', '.join(repr(token) for token in tokens)}))"
        for task, tokens in VERDICT_TOKENS_OF_TASK.items()
    )


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
        #
        # Per task since E6-01, which added the second task: the body is built
        # from `VERDICT_TOKENS_OF_TASK` above, one disjunct per task.
        CheckConstraint(
            verdict_is_in_its_tasks_vocabulary(),
            name="verdict_is_in_its_tasks_vocabulary",
        ),
        # The pair `app.services.validity`'s re-classification sweep filters on:
        # one task's rows, written under the floor's prompt version (ADR 0054's
        # audit pair, which is how a floored verdict is told from a model's).
        # Without it the sweep reads the whole table on every run — on a beat and
        # on every floored submission, at a table that grows with every comment
        # ever classified. Added by E2-16, whose boundary review measured the
        # sweep at 72 seconds over ~300k rows and 46 with this index alone; the
        # anti-join rewrite in that service is the other half and neither is the
        # other's substitute.
        #
        # `task` leads because it is the equality both legs always carry.
        Index("ix_classification_task_prompt_version", "task", "prompt_version"),
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


class ModerationAttempt(UuidPrimaryKey, Base):
    """One moderation call about one comment that failed, appended (E6-01, E6-02).

    A comment is shown to no reader until it holds a moderation verdict
    (`report_comment` v004, ADR 0187), so a comment whose moderation call keeps
    failing would hold its whole section-week back for ever. E6-02's sweep caps
    the attempts per comment, and this table is what it counts: one row per failed
    call, never edited. E6-01 creates it so that E6-02 needs no migration of its
    own; nothing in E6-01 writes or reads it.

    **Two columns beyond the key, and no model answer**, because a failed call has
    none. `pulse_app` holds `SELECT` and `INSERT` here and nothing else
    (`moderation_attempt_grants_v001.sql`), so a failed attempt cannot be erased
    to reset a cap.
    """

    __tablename__ = "moderation_attempt"

    # The comment the call was about. `RESTRICT`, like every other foreign key on
    # the survey tables (see `Classification.answer_id`), and indexed because the
    # cap's read is "the attempts about this comment".
    answer_id: Mapped[UUID] = mapped_column(
        ForeignKey("answer.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # When the call failed. A server default, as on `classified_at`, so rows can be
    # ordered by when they were written whatever wrote them.
    attempted_at: Mapped[datetime] = mapped_column(
        AwareDateTime, nullable=False, server_default=text("now()")
    )
