"""What the weekly report stores: the generated summary, a comment's moderation state, and the batch a held comment was released in.

SPEC §13 listed no home for a reporting model when this module was added. `survey.py` holds what a student
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
with no `moderation_state` row is published, once it holds a moderation verdict
at all — since E6-01 a comment with none reaches no reader (`report_comment`
v004, ADR 0187); the latest row governs from there,
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
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
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


# The roles a moderation decision is made under (E6-03, its work order's decision
# 5): the teaching instructor, the course's Lead Faculty, and the department chair,
# who decides for a course with no lead. Stored on the row because SPEC §5.2's
# exclusion log shows the decider's role, and a role read off today's assignments
# would change when the assignments do. E6-03 writes only `INSTRUCTOR`; the other
# two are here so E6-05's door needs no migration of its own.
class DeciderRole(StrEnum):
    """A role a moderation decision is made under; the value is the stored token."""

    INSTRUCTOR = "INSTRUCTOR"
    LEAD_FACULTY = "LEAD_FACULTY"
    CHAIR = "CHAIR"


DECIDER_ROLES = tuple(role.value for role in DeciderRole)

# The longest stated reason a decision may carry, in characters, measured as sent
# (E6-03's decision 4, `docs/MISTAKES.md` entry 29).
REASON_BOUND = 500

# Every character Python's `str.strip()` removes, by code point and with no
# character class, which is how `report_comment_v003.sql` and its successor define
# a blank comment so that the test means the same thing under every collation
# (E5.1-12, migration `ad9da2d96664`). A reason is stated when it holds at least
# one character outside this set, which is what Python's `reason.strip() != ""`
# asks in the decision service. `btrim` alone would not do: it removes spaces and nothing
# else, so a tab would pass as a stated reason.
NOT_ONLY_WHITESPACE = (
    "~ '[^\\u0009-\\u000d\\u001c-\\u001f \\u0085\\u00a0\\u1680\\u2000-\\u200a"
    "\\u2028\\u2029\\u202f\\u205f\\u3000]'"
)


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

    **A comment with no row here is published**, once it holds a moderation
    verdict: since E6-01 a comment with none reaches no reader (`report_comment`
    v004, ADR 0187). That is the initial state and it is an absence rather than a
    default, which is what makes "exactly one value
    ever written during E4" (the breakdown's decision 3) a count of zero writes
    and leaves every writer to E6. ADR 0145 records it, and the alternative — a
    `state` column on `answer` beside this table — is rejected there because two
    places answering one question disagree the first time either is written
    alone.

    **Since E6-03 a row also says who decided, as what, and why** (its M2).
    SPEC §5.2's exclusion log records "instructor, excerpt, AI-flagged vs
    unflagged-with-reason, date", and the owner's ruling 3 puts that record here
    rather than on a table of its own. `decided_by_person_id` is the decider as a
    `person` key, the actor convention `audit_log.actor_person_id` uses;
    `decided_as` is the role the decision was made under; `reason` is the stated
    reason; `is_undo` marks a row that restores the state before the decision it
    undoes. A row with no decider is the routing definer's flag and nothing else:
    the `CHECK`s below say so, and a trigger refuses a decider-less row from any
    role but the definer (`moderation_decision_grants_v001.sql`, ADR 0189).
    """

    __tablename__ = "moderation_state"
    __table_args__ = (
        CheckConstraint(
            _in_the_vocabulary("state", MODERATION_STATES),
            name="state_is_in_the_lifecycle_vocabulary",
        ),
        CheckConstraint(
            _in_the_vocabulary("decided_as", DECIDER_ROLES),
            name="decided_as_is_a_deciding_role",
        ),
        CheckConstraint(
            "(decided_by_person_id IS NULL) = (decided_as IS NULL)",
            name="a_decider_and_a_role_come_together",
        ),
        CheckConstraint(
            "decided_by_person_id IS NOT NULL OR state = 'FLAGGED_COLLAPSED'",
            name="a_row_nobody_decided_is_a_flag",
        ),
        CheckConstraint(
            "reason IS NULL OR decided_by_person_id IS NOT NULL",
            name="a_reason_needs_a_decider",
        ),
        CheckConstraint(
            f"reason IS NULL OR (length(reason) BETWEEN 1 AND {REASON_BOUND}"
            f" AND reason {NOT_ONLY_WHITESPACE})",
            name="a_reason_is_stated_and_bounded",
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
    # The order the rows were written in, assigned by the database (E6-01, ADR
    # 0187). `decided_at` is `now()`, the transaction's timestamp, so two
    # decisions written in one transaction carry the same instant and cannot be
    # told apart by it; this column breaks that tie, and `reported_status_of`
    # orders by it alone. `ALWAYS`, so no writer can choose a value. It orders by
    # insert, not by commit: two concurrent writers are not a same-transaction
    # pair, and between them this column records which inserted first.
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)
    # Who decided, as a `person` key, and `RESTRICT` as `audit_log.actor_person_id`
    # is: deleting a staff member may not erase their decisions. Null on the
    # routing definer's flag, which nobody decided. Indexed for E6-05's exclusion
    # log, which reads a person's decisions.
    decided_by_person_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # The role the decision was made under, one of `DECIDER_ROLES`.
    decided_as: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SPEC §5.2's stated reason. Required by the decision service when an
    # unflagged comment is excluded; optional otherwise, and held to the same
    # bounds when given.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Whether this row restores the state before a decision it undoes. Undo
    # appends rather than deletes, so the log keeps both directions (SPEC §8).
    is_undo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


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

    **The section and the term have to agree, and since the E4 boundary round the
    database is what says so.** This paragraph used to read that the term is
    "referenced plainly beside the section … ADR 0145 names the accepted risk", and
    the boundary review wrote the row that permitted: a batch naming a section of
    one term and the id of another. Two single-column keys accept it, and it is a
    release attached to a crossing nobody evaluated — `released_comments` reads by
    exactly that pair, so such a batch is either invisible to its section's real
    report or attached to the wrong term's. The mechanism is `response`'s and
    `survey_window`'s, for ADR 0018's reason: a composite foreign key, because a
    `CHECK` cannot read another table. ADR 0146 carries the dated correction —
    that record's cost argument for keeping the keys plain was ADR 0145's, and it
    does not apply here, because `term_id` is already on the row.
    """

    __tablename__ = "release_batch"
    __table_args__ = (
        # The pairing, replacing the plain key to `section` rather than sitting
        # beside it: one check per reference, and the composite one is strictly the
        # stronger. It references `uq_section_id_term_id`, which `section` has
        # carried since `3f6907349751` gave `survey_window` the same rule.
        ForeignKeyConstraint(
            ["section_id", "term_id"],
            ["section.id", "section.term_id"],
            ondelete="RESTRICT",
        ),
        # Both of E4-04's release reads are keyed on this pair: `released_comments`
        # asks what this section has released this term, and `cut_due_release_batches`
        # asks it of every section in the institution once a week. The measurement
        # the original note asked for is the boundary review's, and this is the
        # index arriving in the ticket that made it.
        Index("ix_release_batch_section_id_term_id", "section_id", "term_id"),
    )

    # Referenced by the composite key above rather than by a `ForeignKey` here,
    # exactly as `response.section_id` and `survey_window.section_id` are. It leads
    # the index above, so a lookup by section alone is served too.
    section_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    # The plain key to `term` stays. The composite above implies it — a section's
    # own `term_id` is a foreign key into `term` — and it is kept because dropping
    # it is a separate decision about what a batch's term means, which no finding
    # asked for.
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

    # Indexed since the E4 boundary round, which is the ticket that measured the
    # read the original note here was waiting for. `released_comments` walks a
    # section's batches and then each batch's memberships, on every report of a
    # section with a release in it; without this the lookup scans every membership
    # row this institution has ever written. The unique on `answer_id` below cannot
    # serve it — it leads with the answer.
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("release_batch.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Not indexed either: it is the whole of `uq_release_batch_member_answer_id`,
    # which serves the lookup every reader makes — has this comment been released.
    answer_id: Mapped[UUID] = mapped_column(
        ForeignKey("answer.id", ondelete="RESTRICT"), nullable=False
    )
