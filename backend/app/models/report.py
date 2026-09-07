"""What the weekly report stores: the generated summary, a comment's moderation state, and the batch a held comment was released in.

SPEC §13 lists no home for a reporting model. `survey.py` holds what a student
submitted and `ai.py` holds the verdicts a model returned about one comment, and
none of the three tables here is either of those things — so E4-02 adds this
module and
[ADR 0145](../../../docs/adr/0145-the-report-schema-has-its-own-module-and-moderation-starts-by-absence.md)
argues the home rather than leaving the choice to whoever reads the imports.

**Nothing here writes anything, and that is the whole ticket.** E4-06 writes a
summary, E4-04 writes a release batch, and E6 writes every moderation state.
This module is the shape those three are written against, plus the constraints
that make a nonsensical row unwritable — E3-02's pattern, for E3-02's reason:
the schema an epic shares is reviewed once, whole, rather than accreted a writer
at a time. **No grant is issued for any of these tables either**, for the same
reason: a privilege lands in the change that spends it, and a `GRANT` written
for a writer that does not exist yet widens the runtime role for nobody.

**Absence is the initial moderation state, and there is no default.** A comment
with no `moderation_state` row is published; the latest row governs from there,
which is the shape `classification` in `app.models.ai` already has and which
SPEC §5.2 needs, because its lifecycle has an undo in both directions and §8
requires both directions logged. A mutable column on `answer` could hold the
current state and could not hold the trail, and a column *beside* this record
would be a second answer to one question. ADR 0145 weighs both.

**No per-comment release time exists anywhere in this module.** SPEC §4
surfaces held comments "batched so that timing cannot identify an author", and
one line down: "timestamps are never shown with comments". The batch's `cut_at`
is the only time in the design, and `release_batch_member` carries a comment and
a batch and nothing else —
[ADR 0146](../../../docs/adr/0146-a-release-is-a-batch-row-and-a-membership-row.md)
records the grain. A stored timestamp nobody exposes today is a leak someone
ships tomorrow, so the rule is that the column does not exist rather than that
no view selects it.

**Text plus a `CHECK` rather than a Postgres enum**, for both closed sets here
and for `question.stream` beside them. `classification.verdict` gives the
reasoning in `app.models.ai`, and the mechanical half matters more in E4 than it
did there: several tickets of this epic take migration slots off one head, and a
shared enum *type* created by one of them is an object the other two have to
know about to be re-pointable at merge. A `CHECK` is local to the table it is
on.

**`Base` comes from `app.models.base` and not from `app.db`**, which builds an
engine out of `Settings()` at import: `migrations/env.py` and CI's
`migration-drift` job supply the database variables alone, so a model module
that needed an AI provider URL would import here and fail there.

**Timestamps are timezone-aware and refuse a naive value**
([ADR 0019](../../../docs/adr/0019-a-naive-datetime-is-refused-by-the-column-type.md)).
Both of them carry a server default of `now()`, which is the opposite of what
`response`'s two submission timestamps do and is not an inconsistency: those two
are written through E2-04's injectable clock and a default would make the
server's wall clock the writer of record. `generated_at` and `cut_at` record
when this system did something, not when a user did, and the same argument
`classification.classified_at` makes applies — a server default is what lets two
rows be ordered by when they were written whatever wrote them.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AwareDateTime, Base, UuidPrimaryKey
from app.models.survey import REPORT_STREAMS

# SPEC §5.2's lifecycle, plus the state a comment starts in: "`published` →
# `flagged-collapsed` … → `excluded` (with Undo) or `kept`". Upper case with the
# hyphen written as an underscore, which is how `classification.verdict` and
# `role_assignment.role` are already spelled in this schema.
#
# `PUBLISHED` is in the set even though absence is what a published comment
# ordinarily looks like: §5.2's Undo "returns it to review" and a `kept` comment
# is published by an instructor's decision, so E6 needs a token for a state
# reached deliberately as well as one reached by never having been touched.
MODERATION_STATES = ("PUBLISHED", "FLAGGED_COLLAPSED", "EXCLUDED", "KEPT")


def _in_the_vocabulary(column: str, tokens: tuple[str, ...]) -> str:
    """`column IN (…)`, written from the tuple beside it rather than typed twice.

    The same construction `classification`'s verdict check uses in
    `app.models.ai`, and for the same reason: a token added to or renamed in the
    tuple above moves the constraint with it, where a second copy in a string
    would have been the one nobody updates (`docs/MISTAKES.md` entry 13).
    """
    return f"{column} IN ({', '.join(repr(token) for token in tokens)})"


class WeeklySummary(UuidPrimaryKey, Base):
    """The AI summary of one section's course week, in one of SPEC §5.1's two streams.

    §5.1 puts "de-identified comments grouped under 'About the instructor' /
    'About the course,' each group led by its own AI summary", so the grain is a
    section, a course week and a stream — and the unique constraint over those
    three is the whole of it. Two rows at that grain are two answers to one
    question and §5.1 renders one; a constraint one column short refuses the
    second summary the report requires every week.

    **`prompt_version` and `model_id` are both `NOT NULL`**, which is SPEC §7.4
    applied to a model output that is not a classification: "every classification
    stores prompt version and model ID for reproducibility", and a summary an
    instructor reads about their own teaching is the output that most needs to be
    attributable. An optional column here would give every reader an auditability
    field and every row permission to carry nothing.

    **`response_count` is what §5.1 requires the summary to state** — "state the
    response count they draw from" — and zero is a value it may take. §5.1
    generates summaries "even in small-N weeks — there, the summary is the only
    comment signal", and a week nobody answered is the smallest of those. The
    `CHECK` is therefore `>= 0` and not `> 0`; below zero is not a small number
    but a writer that has subtracted something, and the value is rendered.

    **`themes` is nullable and its shape is E4-06's to settle.** §5.1 asks a
    summary to "preserve clearly critical themes (never sanded off)"; what
    structure that is stored in is a question about the generation job's contract,
    which does not exist yet. `JSONB` and a null say "the job that writes this has
    not been built", which is a different fact from an empty list.

    **The week is referenced plainly, and `response`'s composite pattern is
    deliberately not copied here.** `response` carries a `term_id` and two
    composite foreign keys so that a section in one term cannot be paired with a
    week in another (E2-16, ADR 0018). This table takes the simple `week_id`
    instead, and ADR 0145 names the residual risk rather than hiding it: the only
    writer §5.1 admits is E4-06's Monday job, which derives both keys from a
    `survey_window` row, and that table already enforces the pairing. A summary
    written by hand over a mismatched pair would be accepted here, which is a
    hand-written `INSERT` producing a nonsense row — the same cost ADR 0110
    accepts on `answer`.

    **Deletion is refused, not cascaded**, as everywhere else in this schema:
    what a retention policy eventually deletes is the retention epic's decision
    to make out loud.
    """

    __tablename__ = "weekly_summary"
    __table_args__ = (
        UniqueConstraint("section_id", "week_id", "stream"),
        CheckConstraint(
            _in_the_vocabulary("stream", REPORT_STREAMS),
            name="stream_is_one_the_report_groups_by",
        ),
        CheckConstraint("response_count >= 0", name="response_count_is_not_negative"),
    )

    # Not indexed on its own: it leads `uq_weekly_summary_section_id_week_id_stream`,
    # which serves the read E4-07 makes — this section's summaries for this week.
    # Same reasoning as `course.prefix_id` in `app/models/org.py`.
    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("section.id", ondelete="RESTRICT"), nullable=False
    )
    week_id: Mapped[UUID] = mapped_column(
        ForeignKey("week.id", ondelete="RESTRICT"), nullable=False
    )
    # Which of §5.1's two groups this summary heads. `Text` plus the `CHECK`
    # above, as the module docstring explains, and the same two tokens
    # `question.stream` carries — a summary of a stream no question belongs to
    # would head a group with nothing under it.
    stream: Mapped[str] = mapped_column(Text, nullable=False)
    # The generated sentences themselves. `Text` and not a bounded string: a
    # summary is model output at whatever length the prompt asks for, and nothing
    # reads a prefix of it.
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_count: Mapped[int] = mapped_column(Integer, nullable=False)
    themes: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    # The prompt file's path stem, and the provider's own identifier for the
    # model, spelled as the provider spells it — the pair `classification` carries
    # for the same SPEC §7.4 reason (ADR 0031, ADR 0032).
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        AwareDateTime, nullable=False, server_default=text("now()")
    )


class ModerationState(UuidPrimaryKey, Base):
    """One decision about one comment, appended (SPEC §5.2, §8).

    §8 records moderation transitions as rows with "both directions logged", and
    §5.2's lifecycle is why: a comment moves from `flagged-collapsed` to
    `excluded` or `kept`, "Undo returns it to review", and the exclusion log is
    the anti-cherry-picking mechanism the section is built around. A record that
    held one row per comment could express none of that — the second decision
    would overwrite the first, and the trail would be the current state and
    nothing else. So there is deliberately **no** unique constraint on
    `answer_id`, and the latest row governs.

    **A comment with no row here is published.** That is the initial state and it
    is an absence rather than a default, which is what makes "exactly one value
    ever written during E4" (the breakdown's decision 3) a count of zero writes
    and leaves every writer to E6. ADR 0145 records it, and the alternative — a
    `state` column on `answer` beside this table — is rejected there because two
    places answering one question disagree the first time either is written
    alone.

    **This table carries no decider and no reason**, and both are E6's. §5.2's
    log records "instructor, excerpt, AI-flagged vs unflagged-with-reason, date",
    which is a log of who did what; a `decided_by` column added now would be a
    person reference on a table nothing yet writes, and a person reference is the
    one kind of column this epic may not add speculatively (SPEC §4). What is
    here is the comment, the state and when it was decided.
    """

    __tablename__ = "moderation_state"
    __table_args__ = (
        CheckConstraint(
            _in_the_vocabulary("state", MODERATION_STATES),
            name="state_is_in_the_lifecycle_vocabulary",
        ),
    )

    # Indexed, and the read it anticipates is the one every reader makes: "the
    # decisions about this comment", newest first, which is how a moderation view
    # resolves the state a comment is in. The column leads no constraint — there
    # is deliberately no unique over it — so nothing else would serve it. Same
    # justification `classification.answer_id` carries one module over.
    answer_id: Mapped[UUID] = mapped_column(
        ForeignKey("answer.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # One of §5.2's four. `Text` plus the `CHECK` above; the constraint is the
    # entire enforcement, which is what choosing `Text` over an enum costs.
    state: Mapped[str] = mapped_column(Text, nullable=False)
    # Server-side, so that two decisions about one comment can be ordered by when
    # they were written whatever wrote them — which is the whole mechanism by
    # which "the latest row governs" is well defined.
    decided_at: Mapped[datetime] = mapped_column(
        AwareDateTime, nullable=False, server_default=text("now()")
    )


class ReleaseBatch(UuidPrimaryKey, Base):
    """One cumulative release of a section's held comments, and when it was cut (SPEC §4).

    §4 holds comments from under-threshold weeks and surfaces them "once the
    section's cumulative comment volume for the term crosses the threshold,
    batched so that timing cannot identify an author". The threshold is
    cumulative *for the term*, so a batch names the section and the term it was
    cut for; the breakdown's decision 7 stores the crossing rather than computing
    it, because a release re-derived at read time changes as data changes and
    leaks through its own timing.

    **`cut_at` is the only release time in the design.** It is a time about a set
    of comments rather than about any one of them, which is exactly what makes
    the batching work: the membership rows beside it carry nothing.

    **The term is referenced plainly beside the section**, for the reason
    `weekly_summary` takes a plain `week_id`: the writer is E4-04, which derives
    both from the section it is releasing for. ADR 0145 names the accepted risk.
    """

    __tablename__ = "release_batch"

    # Not indexed. The read E4-04 will make is this section's batches for this
    # term, and no measurement in this repository says how that query is shaped
    # yet — `app/models/survey.py` makes the same call about `answer.question_id`,
    # and `c4a8e51db9f3` is the worked example of an index arriving in the ticket
    # that measured the read rather than in the ticket that guessed at it.
    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("section.id", ondelete="RESTRICT"), nullable=False
    )
    term_id: Mapped[UUID] = mapped_column(
        ForeignKey("term.id", ondelete="RESTRICT"), nullable=False
    )
    cut_at: Mapped[datetime] = mapped_column(
        AwareDateTime, nullable=False, server_default=text("now()")
    )


class ReleaseBatchMember(UuidPrimaryKey, Base):
    """One comment, and the batch it went out in. Nothing else (SPEC §4).

    **The column list is the confidentiality guarantee**, not an incidental
    shape. §4 batches a release "so that timing cannot identify an author" and
    says one line later that "timestamps are never shown with comments"; a
    `released_at` here would give one comment a time of its own, and the ordering
    of a term's held comments would be recoverable one row at a time by anyone
    who could read the table. Adding any column to this row is a change to what
    the table is, and
    `tests/integration/test_report_schema.py` asserts the whole inventory rather
    than searching for a name, so a column spelled any way at all reds.

    **`answer_id` is unique and `batch_id` is not.** A comment is released at
    most once — two memberships give one comment two release times, and the
    difference between them is the signal the batching exists to remove. A batch,
    on the other hand, is a *set*: that is the whole of what batching means, and
    a unique over `batch_id` would make every batch a single comment and restore
    the per-comment timing §4 removes.
    """

    __tablename__ = "release_batch_member"
    __table_args__ = (UniqueConstraint("answer_id"),)

    # Not indexed on its own. The read is a batch's members, which E4-04 builds;
    # see the note on `release_batch.section_id` for why the index waits for the
    # ticket that measures it.
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("release_batch.id", ondelete="RESTRICT"), nullable=False
    )
    # Not indexed either: it is the whole of `uq_release_batch_member_answer_id`,
    # which serves the lookup every reader makes — has this comment been released.
    answer_id: Mapped[UUID] = mapped_column(
        ForeignKey("answer.id", ondelete="RESTRICT"), nullable=False
    )
