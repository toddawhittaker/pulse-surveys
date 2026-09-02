"""The weekly survey: the versioned question set, and the responses and answers it collects.

SPEC §3.2, §3.3 and §8. §13 gives this module the four tables E2-05 creates —
`question_set`, `question`, `response` and `answer` — and nothing else. The
survey *window* lives in `app.models.term` beside the calendar it is cut from,
which is why nothing here names it.

**The instrument is data, not code.** §3.2 fixes five questions and calls the
set "v1 fixed", and it says in the same breath why the table is versioned: the
future feature where each oversight level appends its own questions "will need
no schema migration". So everything a form has to know about a question — its
ordinal, its shape, the sentence it asks, the rule that makes it required, and
the range its answer runs over — is a column here rather than a branch in
E2-10's renderer. A question that only the frontend understands is a question
this table cannot version.

**Two of §3.2's rules are carried as data, and each is a pair of columns.** The
conditional requirement ("Required if Q1 ≤ 2") is the position it depends on and
the value at or below which it applies. A numeric range is a minimum, a maximum
and a step. Each pair is whole or absent, held there by a CHECK, because half a
rule reads as configured and is not: a dependency with no threshold is a form
that knows a field is conditional on Q1 and not on what.

**The ranges live on `question` and nowhere else, and `answer` carries no range
check at all.** A CHECK constraint cannot read another table — ADR 0018's
opening problem — so a rating bounded on `answer` would either be a second copy
of the range that could disagree with the first, or a composite foreign key
carrying the bounds onto every answer row. Neither is taken; E2-08's write path
validates a submitted value against the question it answers.
[ADR 0110](../../../docs/adr/0110-answer-values-are-validated-by-the-write-path.md)
records the decision and what it costs, which is that a hand-written `INSERT`
can store a rating of 9.

**Nothing here writes anything.** E2-06 opens the windows, E2-08 writes a
response and its answers, E2-09 reads them. This module is the shape those three
are written against, plus the constraints that make a nonsensical row
unwritable.

**Timestamps are timezone-aware and refuse a naive value** ([ADR 0019](../../../docs/adr/0019-a-naive-datetime-is-refused-by-the-column-type.md)),
and the two on `response` carry **no server default of any kind**. E2-08 writes
them through E2-04's clock service, and a `now()` on the column would win
silently on any insert that omitted it — making the server's wall clock the
writer of record and E2-04's injectable clock unobservable in every test written
afterwards.

**`Base` comes from `app.models.base` and not from `app.db`**, which builds an
engine out of `Settings()` at import: `migrations/env.py` and CI's
`migration-drift` job supply the database variables alone, so a model module
that needed an AI provider URL would import here and fail there.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AwareDateTime, Base, UuidPrimaryKey

# The widest a question's name may be. §3.2's five are two or three words each
# ("Instructor rating", "Course comment"), so this is room to spare rather than a
# measurement — but a bound rather than `Text`, because a name is a label on a
# form and a paragraph pasted into one is a defect to refuse at the column.
QUESTION_NAME_MAX_LENGTH = 100

# The precision every numeric value in this module is held at: three digits and
# one decimal place. §3.2's two ranges are a Likert 1 to 5 and a workload slider
# running 0 to 40 in half hours, and one decimal place is exactly what a half
# hour needs. Wider would invite a stored 12.25 that no control can produce and
# no reader expects; `Float` would make "0.5 hours" a value that does not compare
# equal to itself across a round trip.
VALUE_PRECISION = 4
VALUE_SCALE = 1


class QuestionKind(StrEnum):
    """Which of §3.2's three answer shapes a question has.

    Three, and the section is where each comes from: two Likert ratings, two free
    text comments, and the workload slider. The kind is what tells E2-10 which
    control to render and E2-08 which of `answer`'s three value columns a
    submission may fill, so a question of the wrong kind is a question that
    cannot be answered.

    `workload` is its own member rather than a second numeric alongside `likert`
    because the two differ in everything except being numbers: one is a five
    point agreement scale that §5.1 plots as a distribution, the other is hours
    "stored as a decimal so reporting can show true means and medians rather than
    band midpoints".

    **The member values are the labels in the database**, so the type is declared
    with `values_callable` below rather than storing the member names — the two
    spellings would otherwise differ by case alone, which is the kind of
    difference nobody notices until a query returns nothing. That is the reasoning
    `LaunchDefectKind` in `app.models.lti` gives for the same choice.
    """

    LIKERT = "likert"
    COMMENT = "comment"
    WORKLOAD = "workload"


class QuestionSet(UuidPrimaryKey, Base):
    """One version of the survey instrument. SPEC §3.2 ships exactly one: v1.

    "Question text is stored in a versioned `question_set` table even though v1
    ships one fixed set — this is the extension point for the future feature
    where each oversight level can append its own questions to the courses in
    their purview. No schema migration will be needed to add it."

    **The version is the natural key**, and it is unique because a version is
    what names a set: the demo seed matches v1 on it, and every `answer` resolves
    its text through its question's set, so two rows sharing a version leave "the
    v1 set" with two answers and nothing to choose between them.

    Versions start at 1 rather than at 0, which is how §3.2 spells the one that
    exists. A set at 0 or below sorts ahead of it in every "latest version" query
    written afterwards, which is a wrong answer rather than an odd one.

    **Nothing here decides which set is in force.** §3.2 fixes v1 and no ticket
    has yet specified how a second one would be selected — per institution, per
    level, per term — so there is no `is_active` column and no ordering rule. The
    feature that adds a set is the ticket that answers that question.
    """

    __tablename__ = "question_set"
    __table_args__ = (
        UniqueConstraint("version"),
        CheckConstraint("version >= 1", name="version_is_at_least_one"),
    )

    # No index of its own: it is the whole of `uq_question_set_version`, which
    # serves the only lookup anyone makes of this table — the set at a version.
    version: Mapped[int] = mapped_column(Integer, nullable=False)


class Question(UuidPrimaryKey, Base):
    """One question of one set, with everything a form needs to render it (SPEC §3.2).

    The five of v1, in the section's own order: the instructor rating, the
    instructor comment, the course rating, the course comment, and the workload
    slider. `position` is that ordinal, unique within its set and starting at 1 —
    §3.2 numbers its questions from 1 and writes its conditional rules by that
    number, so a question at position 0 is one no rule can name and one the form
    renders before the first.

    **Unique within the set and not across the table.** A second set starts at
    position 1 again, which is the whole of what "no schema migration will be
    needed" means.

    **`prompt` is NULL wherever §3.2 quotes no sentence.** The section quotes one
    for each Likert rating and none for the two comments or the slider. A prompt
    invented here would be user-facing copy shipped through a schema ticket with
    no copy review; the display copy for those three is E2-10's, governed by
    E2-11's copy inventory. NULL says "the spec quotes nothing", which is a
    different fact from an empty string.

    **`required_if_position` and `required_if_at_most` are §3.2's conditional
    rule as data.** "Required if Q1 ≤ 2" is the position depended on and the
    threshold, and §3.3 reads the pair when it scores a response valid ("all
    required fields answered"). Both or neither, held by `conditional_rule_is_whole`:
    a rule naming a question with no threshold cannot be evaluated by E2-10's
    form or applied by §3.3's check, and it reads as a configured rule rather
    than as a missing one.

    **The position is depended on rather than the question's id**, because that
    is how §3.2 writes the rule and because a set is a self-contained document:
    a rule pointing at a row of another set would be a rule this table's
    versioning cannot copy forward. The pair is deliberately *not* a foreign key
    to the sibling row — `(question_set_id, required_if_position)` referencing
    `(question_set_id, position)` is available and is not taken, because it would
    forbid loading a set in §3.2's order, where Q2's rule names Q1 but Q4's
    would be written before Q3 exists in any loader that inserted out of order.
    A rule naming a position no question occupies is refused by E2-08 and E2-10
    finding no such question, and the seeded set is asserted whole in
    `tests/integration/test_demo_seed_script.py`.

    **`minimum_value`, `maximum_value` and `step` are §3.2's ranges as data** —
    "Likert 1-5" and "range 0-40, 0.5-hour steps". All three or none of the
    three (`bounds_are_whole`), because a range with a minimum and no maximum is
    a slider with one end; and running upward with a step that moves
    (`bounds_are_ordered`), because an inverted pair is a validation no answer
    can satisfy and a step of zero divides by zero wherever a range is counted
    out. Both comment questions carry none of the three.

    These three columns are the **only** statement of the ranges anywhere in the
    system: ADR 0110 puts no range check on `answer`, so E2-08 validates against
    them and E2-10 renders the slider from them, and there is nothing left for a
    wrong value here to disagree with.
    """

    __tablename__ = "question"
    __table_args__ = (
        UniqueConstraint("question_set_id", "position"),
        CheckConstraint("position >= 1", name="position_is_at_least_one"),
        CheckConstraint(
            "num_nonnulls(required_if_position, required_if_at_most) IN (0, 2)",
            name="conditional_rule_is_whole",
        ),
        CheckConstraint(
            "num_nonnulls(minimum_value, maximum_value, step) IN (0, 3)",
            name="bounds_are_whole",
        ),
        # Null wherever the bounds are absent, and a CHECK passes on NULL, so
        # this says nothing about a question with no range — which is what
        # `bounds_are_whole` beside it is for.
        CheckConstraint(
            "maximum_value > minimum_value AND step > 0",
            name="bounds_are_ordered",
        ),
    )

    # Not indexed on its own: it leads `uq_question_question_set_id_position`,
    # which serves the read every caller makes — a set's questions in order.
    # Same reasoning as `course.prefix_id` in `app/models/org.py`.
    question_set_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_set.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[QuestionKind] = mapped_column(
        Enum(
            QuestionKind,
            name="question_kind",
            values_callable=lambda enumeration: [member.value for member in enumeration],
        ),
        nullable=False,
    )
    # §3.2's bold heading for the question, verbatim — "Instructor rating".
    name: Mapped[str] = mapped_column(String(QUESTION_NAME_MAX_LENGTH), nullable=False)
    # The sentence §3.2 quotes, where it quotes one. `Text` and not a bounded
    # string: a prompt is a sentence a later set may write at any length, and
    # nothing reads a prefix of it.
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_if_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_if_at_most: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minimum_value: Mapped[Decimal | None] = mapped_column(
        Numeric(VALUE_PRECISION, VALUE_SCALE), nullable=True
    )
    maximum_value: Mapped[Decimal | None] = mapped_column(
        Numeric(VALUE_PRECISION, VALUE_SCALE), nullable=True
    )
    step: Mapped[Decimal | None] = mapped_column(
        Numeric(VALUE_PRECISION, VALUE_SCALE), nullable=True
    )


class Response(UuidPrimaryKey, Base):
    """One student's submission for one section in one week (SPEC §8).

    "`response` is unique per (student, section, week)", and the database is what
    refuses the second one. Two rows are two votes: §3.3's validity rate and
    §3.4's participation score both count responses, and the denominator is weeks
    rather than rows, so a duplicate doubles a student's weight in every §5
    aggregate while participation stays at one.

    All three columns are in the key and each is load-bearing. Without the week,
    a student could answer a section's survey once per term. Without the section,
    a student taking four courses would answer one survey a week across all of
    them — §3.1 gives them "exactly one open survey at a time **per section**".

    **The student key is `user_id`, spelled the way `enrollment` spells it.** The
    identity behind it sits on `user_identity`, which the application role is
    granted no `SELECT` on; §4's de-identification rules are about what a *view*
    of this table may carry, not about a column on the row.

    **The two submission timestamps carry no server default**, and that is a
    criterion of E2-05 rather than a style: E2-08 writes them through E2-04's
    clock service, and a `now()` default wins silently on any insert that omits
    the column, making the server's wall clock the writer of record. They are
    ordered, and equal is the ordinary case — a response submitted once and never
    revised has the same value in both — so the rule is `>=` and a strict `>`
    would refuse every first submission there will ever be.

    **No link to `survey_window`, and no cross-term rule of its own.** A response
    belongs to a section and a week; whether that pair had an open window when it
    arrived is a question about *time*, which a foreign key cannot ask, and
    E2-08's write path consults the window before it writes. Adding a
    `survey_window_id` here would make a response unwritable for a section whose
    window E2-06 has not opened, which is a rule about scheduling stored in the
    wrong table.

    **Resubmission semantics are E2-08's**, which owns what a second submit does
    to the answers. This table gives it the two columns and the ordering rule and
    nothing more.

    **`is_valid` is §3.3's verdict about the whole submission**, added by E2-08
    with the path that writes it. It is a stored answer rather than a query over
    `classification` because §3.4's participation score is computed over these
    rows and the verdicts behind it are append-only — "the latest classification
    of each of this response's comments" is a window function every reader would
    otherwise have to get right. What keeps the stored answer honest is that one
    module writes it: `app.services.validity`, at submit and again when the async
    re-classification revises a floored verdict.
    """

    __tablename__ = "response"
    __table_args__ = (
        UniqueConstraint("user_id", "section_id", "week_id"),
        # The read every report and every window-close job makes: this section's
        # responses for this week. `uq_response_user_id_section_id_week_id` leads
        # with the student, so it serves a lookup by student and no lookup by
        # section — Postgres 17 has no skip scan, and an index that merely
        # contains a column serves no lookup by it.
        Index("ix_response_section_id_week_id", "section_id", "week_id"),
        CheckConstraint(
            "last_submitted_at >= first_submitted_at",
            name="last_submission_is_not_before_the_first",
        ),
    )

    # Not indexed on its own: it leads the unique constraint above, so a lookup
    # of one student's responses is already served.
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    # Not indexed on its own either: it leads `ix_response_section_id_week_id`.
    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("section.id", ondelete="RESTRICT"), nullable=False
    )
    # Indexed, and this is the same justification `survey_window.week_id` carries
    # in `app/models/term.py`: the other read is by week — everything submitted
    # in the week that has just closed, which §3.4 recomputes participation from
    # — and this column leads no constraint and no composite index.
    week_id: Mapped[UUID] = mapped_column(
        ForeignKey("week.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    first_submitted_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    last_submitted_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    # Whether this submission counts for participation (§3.3, §3.4), written by
    # the submit path alone from the classification verdicts of the comments it
    # carried. NOT NULL and no server default, for both halves of the reason the
    # timestamps above carry none: E3's participation formula reads this column,
    # and a default would let a row that nothing decided about look decided.
    #
    # It moves after the fact, and that is the point rather than an oversight: a
    # submission accepted on §3.3's fail-open floor is stored valid and the async
    # re-classification revises it when a model finally judges the comment
    # (`app.services.validity`). A blank optional comment never affects it —
    # §3.3 says so in as many words — because there is no verdict to read.
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)


class Answer(UuidPrimaryKey, Base):
    """One question of one response, answered (SPEC §8).

    "`answer` rows link to versioned `question` rows; workload is stored as a
    decimal." The link is to the `question` row and not to a position or a name,
    which is what makes the set versionable: a response answered under v1 goes on
    reading as v1 after v2 exists.

    **One answer per question per response.** Two rows for one question give
    every read path two values and no rule for choosing — a rating distribution
    that double-counts one student, and a comment list that shows one student
    twice under §4's de-identification.

    **A row holds exactly one of the three value columns**, and `= 1` is the
    rule rather than `<= 1`: a row holding none says a student answered a
    question and records no answer, which §3.3's completeness check counts and
    §5.1's distribution cannot plot, and which is indistinguishable from the
    question being skipped — that is the absence of a row.

    **Three columns rather than one polymorphic value.** A rating is an integer,
    a comment is text, and workload is a decimal because §3.2 says so — "stored
    as a decimal so reporting can show true means and medians rather than band
    midpoints". One `Text` column holding all three would make every average a
    cast and every cast a place where a bad row is discovered at read time.

    **No range check here, deliberately** — ADR 0110. The ranges are data on
    `question`, a CHECK cannot read another table, and a second copy of the range
    on this table is a rule two constraints both have to satisfy, which is the
    shape that quietly disagrees. E2-08's write path is where a submitted value
    is checked against its question's bounds.

    **`comment_text` is a student's own words and is not an identity column.** It
    can name anybody at all, which is why §5.2 moderates it and §4 randomises its
    display order and shows no timestamp beside it. It holds no key to a person,
    and marking it would put every comment in the set the identity-separated
    views may not read — the opposite of what §5.1 requires of the instructor
    report.

    **Deletion is refused, not cascaded.** Every foreign key here is `RESTRICT`,
    so nothing removes a response's answers by removing something else. What a
    retention policy eventually deletes, and in what order, is the retention
    epic's to decide, and a cascade written now would decide it silently.
    """

    __tablename__ = "answer"
    __table_args__ = (
        UniqueConstraint("response_id", "question_id"),
        CheckConstraint(
            "num_nonnulls(rating, comment_text, workload_hours) = 1",
            name="holds_exactly_one_value",
        ),
    )

    # Not indexed on its own: it leads `uq_answer_response_id_question_id`, which
    # serves the read E2-08 and E2-09 both make — the answers of one response.
    response_id: Mapped[UUID] = mapped_column(
        ForeignKey("response.id", ondelete="RESTRICT"), nullable=False
    )
    # Not indexed either, and nothing measured says it should be: every read of
    # this table starts from a section and a week and reaches answers through
    # their responses. An index here would serve "every answer to question N
    # ever", which no surface in SPEC §5 asks for.
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("question.id", ondelete="RESTRICT"), nullable=False
    )
    # A Likert selection. An integer because §3.2's scale is 1 to 5 in whole
    # steps; the bounds themselves are on the question (ADR 0110).
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Hours, to the half hour. `Numeric` and not `Float`: §3.2's slider moves in
    # 0.5-hour steps, and a binary float makes "3.5 hours" a value that does not
    # always compare equal to itself once §5.1 has taken a mean of it.
    workload_hours: Mapped[Decimal | None] = mapped_column(
        Numeric(VALUE_PRECISION, VALUE_SCALE), nullable=True
    )
