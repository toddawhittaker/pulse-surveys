"""Storing one student's weekly answers, and every reason not to (SPEC §3.1, §3.2, §3.3, §8).

The write path behind `app.api.student`. §13's closing rule puts the decisions here
and leaves the router thin, so everything this module raises is a *reason* and the
router is what turns a reason into a status code.

**The order the checks run in is the design, not a detail**, and it is written out
here because it changed once already and a paragraph describing the old order is
worse than none. In the order the code runs them:

1. **Whether the section is one this student can reach**, answered identically for
   a section that does not exist (SPEC §4.1 item 1 — a refusal that told the two
   apart would answer "does this section exist" for any signed-in student, one
   request at a time). This is first, so a caller probing section ids is refused
   before anything else happens at all: no window is read, no question is loaded,
   no model is asked, and the two answers are indistinguishable in content and in
   the work they cost.
2. **The open window**, a fact about time, from E2-06's one function through
   E2-04's clock.
3. **The submitted values against the questions they answer** — the shape, the
   range and the step (ADR 0110), and §3.2's conditional requirement.
4. **The model**, once per submitted comment. Everything above is decided before a
   student waits on a provider, and everything above is decided about the
   student's own week rather than about anything they cannot see.
5. **The write**, and the two refusals it can still raise: the duplicate the
   uniqueness constraint refuses, and the withdrawal of a comment a verdict names
   (ADR 0115).

**So the model call precedes every write, and steps 5's two refusals are decided
after it.** That is the reverse of the order this path shipped with and it is
deliberate: a bounce has to be able to keep its verdict, and a verdict written
inside the transaction a bounce rolls back is a verdict that is never committed at
all (ADR 0114). What it costs is that a racing duplicate and a withdrawn judged
comment each spend one provider call before being refused. Neither is a §4.1
concern — both are facts about the student's own week, which they may ask about
freely — and neither is reachable without a valid student session and an
enrollment in the section, both established at step 1.

**A bounce stores its verdict rows and nothing else.** Not "nothing", which is what
this paragraph used to claim and is no longer true: §3.3 refuses an `insufficient`
comment "before submission", so no `response` and no `answer` row is written — a
bounce that stored the response and marked it invalid would be the "silently
penalized after the fact" the same sentence forbids — and the classification that
refused it *is* committed, against no answer, because SPEC §7.4 rests auditability
on the pair that produced a verdict. Because the gate runs before the write, that
is achieved by never creating the rows rather than by rolling them back.

What is *not* kept is the comment's text: ADR 0055 keeps a classification row free
of it, and what that costs — a bounced comment reaches neither §5.2's moderation
nor §6.2's Care queue — was ruled on 2026-09-03 and is recorded in ADR 0114 as a
decision with its grounds. The count of those rows is still unbounded per attempt;
`docs/tickets/e2/deferred.md` carries that entry, and the ruling on it is a cap
whose value belongs to the ticket that implements it.

**A resubmission revises its answer rows in place** rather than deleting them and
inserting fresh ones, and
[ADR 0115](../../../docs/adr/0115-a-resubmission-revises-its-answers-in-place.md)
is why: `classification.answer_id` names the comment a verdict judged, under
`ON DELETE RESTRICT`, so an answer a model has judged is one the database will not
let this path delete. The one case that still needs a deletion — a comment answered
last time and left blank this time — is refused with a reason of its own rather
than left to surface as a constraint error under a student.

**The uniqueness constraint is the backstop and this path is the mechanism.** A
resubmission is found by looking, and two requests that both look and both find
nothing are what `uq_response_user_id_section_id_week_id` exists for: the second
insert is refused by the database and this module turns that into the duplicate
refusal rather than a stack trace where a student is standing.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.contracts import CommentValidityOutput, ValidityVerdict
from app.ai.gateway import AIGateway
from app.config import Settings
from app.models.ai import Classification
from app.models.identity import Enrollment
from app.models.org import Section
from app.models.survey import Answer, Question, QuestionKind, QuestionSet, Response
from app.schemas.survey import SubmissionRequest, SubmittedAnswer
from app.services import clock
from app.services.survey_windows import open_window_for_section
from app.services.validity import (
    ClassifierUnavailableError,
    recompute_response_validity,
    record_verdict,
    refusing_verdict,
    verdict_for_submitted_comment,
    was_floored,
)

__all__ = [
    "RefusalReason",
    "StoredSubmission",
    "SubmissionBouncedError",
    "SubmissionRefusedError",
    "store_submission",
]

logger = logging.getLogger(__name__)

# Postgres' SQLSTATE for a unique violation. Named because the alternative is
# treating *every* integrity error at the insert as a duplicate, which would
# report "you have already submitted" for a foreign key that did not resolve.
UNIQUE_VIOLATION = "23505"

# Which of `answer`'s three value columns each question shape is answered in.
# Read off `QuestionKind` rather than off the position, because §3.2's set is
# versioned and a later set's question 3 need not be a rating.
COMMENT_COLUMN = "comment_text"
VALUE_COLUMN_OF_KIND: Mapping[QuestionKind, str] = {
    QuestionKind.LIKERT: "rating",
    QuestionKind.COMMENT: COMMENT_COLUMN,
    QuestionKind.WORKLOAD: "workload_hours",
}


class RefusalReason(StrEnum):
    """Why a submission was refused, spelled as the copy key that says so.

    The member's *value* is the registry key, so a reason and the sentence a
    student reads cannot come apart: there is no second mapping to keep in step,
    and a reason with no copy fails at the lookup rather than serving a blank.
    The HTTP status each reason answers with is `app.api.student`'s, because a
    status is a statement about the protocol rather than about the survey.
    """

    SECTION_UNAVAILABLE = "submit.section_unavailable"
    WINDOW_CLOSED = "submit.window_closed"
    ALREADY_SUBMITTED = "submit.already_submitted"
    ANSWER_REQUIRED = "submit.answer_required"
    VALUE_OUT_OF_RANGE = "submit.value_out_of_range"
    VALUE_OFF_STEP = "submit.value_off_step"
    ANSWER_NOT_RECOGNISED = "submit.answer_not_recognised"
    COMMENT_ALREADY_JUDGED = "submit.comment_already_judged"


class SubmissionRefusedError(Exception):
    """This submission was not stored, for a reason a student is owed in words."""

    def __init__(self, reason: RefusalReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


class SubmissionBouncedError(Exception):
    """SPEC §3.3's synchronous gate: a submitted comment did not read as an answer.

    Carries the verdict rather than a sentence, because the sentence is the
    registry's and the two verdicts get two different ones.
    """

    def __init__(self, verdict: ValidityVerdict) -> None:
        super().__init__(verdict.value)
        self.verdict = verdict

    @property
    def copy_key(self) -> str:
        """The registry key of this verdict's coaching copy."""
        return f"submit.bounce.{self.verdict.value}"


@dataclass(frozen=True, slots=True)
class StoredSubmission:
    """What was stored, read off the row before the caller commits.

    A frozen record rather than the ORM object, so the router can answer after the
    commit without a second read and without holding a mapped instance whose
    attributes expire underneath it.

    `floored` is what tells the caller to enqueue the async re-classification: at
    least one comment's verdict came from §3.3's character floor rather than from a
    model, so a model still owes this response an answer.
    """

    response_id: UUID
    is_valid: bool
    first_submitted_at: datetime
    last_submitted_at: datetime
    floored: bool


# ---------------------------------------------------------------------------
# Who may write here, and into which week.
# ---------------------------------------------------------------------------


def _reachable_section(
    session: Session, *, student_id: UUID, section_id: UUID, settings: Settings
) -> Section:
    """The section this student may submit into, or the one refusal both misses get.

    **`SECTION_UNAVAILABLE` for a section that does not exist and for one the
    student is not enrolled in, with no way to tell them apart.** SPEC §4.1 item 1
    is asserted from E2 because this is the first student-visible path, and the
    difference between "no such section" and "not yours" is a membership oracle
    over every section in the institution.

    Enrollment is a *window* rather than a flag (E0-08), so the question is asked
    about the institution's current day — which comes from `app.services.clock`, so
    a moved development clock moves this answer with everything else it moves.
    """
    section = session.get(Section, section_id)
    if section is None:
        raise SubmissionRefusedError(RefusalReason.SECTION_UNAVAILABLE)

    day = clock.today(session, settings=settings)
    enrolled = session.scalars(
        select(Enrollment.id)
        .where(
            Enrollment.user_id == student_id,
            Enrollment.section_id == section_id,
            Enrollment.started_on <= day,
            (Enrollment.ended_on.is_(None)) | (Enrollment.ended_on >= day),
        )
        .limit(1)
    ).first()
    if enrolled is None:
        raise SubmissionRefusedError(RefusalReason.SECTION_UNAVAILABLE)
    return section


# ---------------------------------------------------------------------------
# The instrument, and a submission judged against it.
# ---------------------------------------------------------------------------


def current_questions(session: Session) -> Sequence[Question]:
    """The questions of the question set in force, in §3.2's order.

    The set at the highest version. §3.2 ships exactly one — "v1 fixed" — and
    E2-05 deliberately gives `question_set` no `is_active` column because no ticket
    has yet specified how a second set would be chosen. Reading the highest version
    is the narrowest rule that answers today's question and does not pretend to
    answer tomorrow's; the ticket that adds a second set is the one that decides.
    """
    question_set = session.scalars(
        select(QuestionSet).order_by(QuestionSet.version.desc()).limit(1)
    ).first()
    if question_set is None:
        raise RuntimeError(
            "There is no `question_set` row, so this deployment has no survey to answer. "
            "`scripts/seed.py` writes SPEC §3.2's v1 set."
        )
    return list(
        session.scalars(
            select(Question)
            .where(Question.question_set_id == question_set.id)
            .order_by(Question.position)
        )
    )


def _submitted_value(answer: SubmittedAnswer) -> tuple[str, int | str | Decimal]:
    """The one value column this answer fills, and its value.

    Exactly one, which is `answer`'s own `holds_exactly_one_value` rule met at the
    edge rather than at the constraint: a row holding none says a student answered
    a question and recorded no answer, and a row holding two is a submission that
    means two things.
    """
    filled = [
        (column, value)
        for column, value in (
            ("rating", answer.rating),
            ("comment_text", answer.comment_text),
            ("workload_hours", answer.workload_hours),
        )
        if value is not None
    ]
    if len(filled) != 1:
        raise SubmissionRefusedError(RefusalReason.ANSWER_NOT_RECOGNISED)
    return filled[0]


def _check_bounds(question: Question, value: int | Decimal) -> None:
    """ADR 0110's two edges, checked separately against the question's own columns.

    Range **and** step, and the two are separate assertions because 3.25 hours is
    inside SPEC §3.2's 0-to-40 range and is not a multiple of its 0.5-hour step —
    ADR 0110's own example of the edge a `CHECK` on `answer` could not have caught.
    The numbers come from `question.minimum_value`, `maximum_value` and `step`,
    which that record makes "the only statement of the ranges in the system"; a
    literal here would be a second statement that is right until §3.2's versioned
    set changes.

    A question carrying no bounds is not checked, and cannot carry half of them:
    `bounds_are_whole` holds all three or none.
    """
    if question.minimum_value is None or question.maximum_value is None or question.step is None:
        return
    amount = Decimal(value)
    if amount < question.minimum_value or amount > question.maximum_value:
        raise SubmissionRefusedError(RefusalReason.VALUE_OUT_OF_RANGE)
    if (amount - question.minimum_value) % question.step != 0:
        raise SubmissionRefusedError(RefusalReason.VALUE_OFF_STEP)


def _values_by_question(
    submission: SubmissionRequest, questions: Sequence[Question]
) -> dict[UUID, tuple[str, int | str | Decimal]]:
    """Each submitted answer matched to the question it answers, and judged against it.

    Answers back the value column the answer fills as well as the value, because
    which column a value belongs in is decided here — once, against the question's
    own kind — and writing the row later should not have to re-derive it from the
    Python type it happens to have.

    Three things are refused, and each is a different defect: an answer at a
    position this set has no question at, two answers at one position, and a value
    in the wrong column for the question's shape. None of them is a wrong *answer*
    — they are submissions that do not match the instrument — so all three carry
    the same reason and the same sentence.
    """
    by_position = {question.position: question for question in questions}
    values: dict[UUID, tuple[str, int | str | Decimal]] = {}
    seen: set[int] = set()
    for answer in submission.answers:
        question = by_position.get(answer.position)
        if question is None or answer.position in seen:
            raise SubmissionRefusedError(RefusalReason.ANSWER_NOT_RECOGNISED)
        seen.add(answer.position)
        column, value = _submitted_value(answer)
        if column != VALUE_COLUMN_OF_KIND[question.kind]:
            raise SubmissionRefusedError(RefusalReason.ANSWER_NOT_RECOGNISED)
        if isinstance(value, str):
            # A comment sent as whitespace is a comment that was not written. It is
            # treated as absent rather than stored, so §3.2's conditional rule sees
            # the same thing a form that sent no member at all would show it.
            if not value.strip():
                continue
        else:
            _check_bounds(question, value)
        values[question.id] = (column, value)
    return values


def _check_required(
    questions: Sequence[Question], values: Mapping[UUID, tuple[str, int | str | Decimal]]
) -> None:
    """SPEC §3.3's first condition: "All required fields answered."

    Two rules, and both are read off the question rows rather than written here.
    A question that is not a free-text comment is always required — §3.2 gives the
    two ratings and the workload slider no way to be skipped. A comment is required
    when the question its row names, at the value its row names, was answered at or
    below that value: "Required if Q1 ≤ 2", carried as `required_if_position` and
    `required_if_at_most` so that a later set's rule travels with it.

    A rule naming a position this set has no question at is not a rule anything can
    evaluate, and it is ignored rather than guessed at — `app.models.survey` says
    the pair is deliberately not a foreign key and names this path as what refuses
    a dangling one.
    """
    answered_at = {
        question.position: values[question.id][1] for question in questions if question.id in values
    }
    for question in questions:
        if question.id in values:
            continue
        if question.kind is not QuestionKind.COMMENT:
            raise SubmissionRefusedError(RefusalReason.ANSWER_REQUIRED)
        if question.required_if_position is None or question.required_if_at_most is None:
            continue
        depends_on = answered_at.get(question.required_if_position)
        if isinstance(depends_on, int) and depends_on <= question.required_if_at_most:
            raise SubmissionRefusedError(RefusalReason.ANSWER_REQUIRED)


# ---------------------------------------------------------------------------
# The write.
# ---------------------------------------------------------------------------


def _existing_response(
    session: Session, *, student_id: UUID, section_id: UUID, week_id: UUID
) -> Response | None:
    """This student's response for this section and week, if there is one already."""
    return session.scalars(
        select(Response).where(
            Response.user_id == student_id,
            Response.section_id == section_id,
            Response.week_id == week_id,
        )
    ).first()


def _write_answers(
    session: Session, response: Response, values: Mapping[UUID, tuple[str, int | str | Decimal]]
) -> dict[UUID, Answer]:
    """Bring this response's answer rows into line with what was just submitted.

    In place, and ADR 0115 is the record of why: a row a model has judged is one
    `classification.answer_id`'s `ON DELETE RESTRICT` will not let this path
    delete. So a question answered again has its row revised, a question answered
    for the first time gets one, and a question no longer answered has its row
    removed — unless a verdict names it, which is the one case that is refused in
    words rather than left to the constraint.
    """
    existing = {
        answer.question_id: answer
        for answer in session.scalars(select(Answer).where(Answer.response_id == response.id))
    }

    withdrawn = [answer for question_id, answer in existing.items() if question_id not in values]
    if withdrawn:
        judged = session.scalars(
            select(Classification.answer_id).where(
                Classification.answer_id.in_([answer.id for answer in withdrawn])
            )
        ).first()
        if judged is not None:
            raise SubmissionRefusedError(RefusalReason.COMMENT_ALREADY_JUDGED)
        for answer in withdrawn:
            session.delete(answer)

    written: dict[UUID, Answer] = {}
    for question_id, (column, value) in values.items():
        found = existing.get(question_id)
        row = Answer(response_id=response.id, question_id=question_id) if found is None else found
        if found is None:
            session.add(row)
        # All three are written every time, and the two that are not this
        # question's shape are written `None`. A revision that only set the column
        # it had a value for would leave a row holding two values where a question
        # changed shape between sets, which `holds_exactly_one_value` refuses at
        # the flush — with the student standing in front of it.
        for candidate in VALUE_COLUMN_OF_KIND.values():
            setattr(row, candidate, value if candidate == column else None)
        written[question_id] = row
    session.flush()
    return written


def store_submission(
    session: Session,
    *,
    student_id: UUID,
    submission: SubmissionRequest,
    settings: Settings,
    gateway: AIGateway | None = None,
) -> StoredSubmission:
    """Store one weekly submission, or raise the reason it was not stored.

    The whole of SPEC §3.3's gate, in the order the module docstring gives. What
    this does *not* do is commit: the caller owns the transaction, because the
    response, its answers and their verdicts are stored together or not at all —
    and every refusal below rolls the transaction back before it raises, so a
    caller that forgets is not what makes "nothing was stored" true.
    """
    section = _reachable_section(
        session, student_id=student_id, section_id=submission.section_id, settings=settings
    )
    window = open_window_for_section(session, section, settings=settings)
    if window is None:
        raise SubmissionRefusedError(RefusalReason.WINDOW_CLOSED)

    questions = current_questions(session)
    try:
        values = _values_by_question(submission, questions)
        _check_required(questions, values)
    except SubmissionRefusedError:
        session.rollback()
        raise

    # §3.3's synchronous gate runs **before** anything is written, and the order is
    # the whole of how a bounce keeps its verdict (ADR 0114). Nothing below this
    # point happens for a submission that does not pass the gate, so a bounce
    # cannot roll a response back — there is none — and the one row it does leave
    # is the audit record §7.4 requires, written against no answer because there is
    # no answer to name.
    verdicts: dict[UUID, CommentValidityOutput] = {}
    try:
        for question_id, (column, value) in values.items():
            if column != COMMENT_COLUMN:
                continue
            verdicts[question_id] = verdict_for_submitted_comment(str(value), gateway)
    except ClassifierUnavailableError:
        # ADR 0114: the provider could not be asked, and this is one of the cases
        # ADR 0056 keeps outside §3.3's floor. Nothing has been written yet, and the
        # rollback ends the read transaction rather than undoing work — so a student
        # who is told to try again in a minute is not retrying over a row they were
        # never told existed, and that is true by construction here rather than by
        # the caller remembering.
        session.rollback()
        raise

    bounced = refusing_verdict(verdicts.values())
    if bounced is not None:
        session.rollback()
        # The one place this module commits, and the exception is deliberate. The
        # rule "the caller owns the transaction" exists so that a response and its
        # answers are stored together or not at all; a bounce stores neither, and
        # what is committed here is only the verdicts that refused it. Losing them
        # is the one way to break `classification`'s append-only guarantee that
        # ADR 0055's grant cannot catch, because the row is never committed at all.
        for output in verdicts.values():
            record_verdict(session, output, answer_id=None)
        session.commit()
        raise SubmissionBouncedError(bounced)

    instant = clock.now(session, settings=settings)
    response = _existing_response(
        session, student_id=student_id, section_id=section.id, week_id=window.week_id
    )
    if response is None:
        response = Response(
            user_id=student_id,
            section_id=section.id,
            week_id=window.week_id,
            first_submitted_at=instant,
            last_submitted_at=instant,
            # Set so the row can be written at all; `recompute_response_validity`
            # below is what decides it, from the verdicts of the comments this
            # submission carried.
            is_valid=True,
        )
        session.add(response)
        try:
            session.flush()
        except IntegrityError as clash:
            # The other half of the race: another request for this (student,
            # section, week) committed between the lookup above and this insert,
            # and `uq_response_user_id_section_id_week_id` refused the second row.
            # That is the constraint doing the job this path relies on it for, and
            # the student is told their answers are already recorded rather than
            # being shown a 500.
            session.rollback()
            if getattr(clash.orig, "sqlstate", None) != UNIQUE_VIOLATION:
                raise
            raise SubmissionRefusedError(RefusalReason.ALREADY_SUBMITTED) from clash
    else:
        response.last_submitted_at = instant

    try:
        written = _write_answers(session, response, values)
    except SubmissionRefusedError:
        session.rollback()
        raise

    # The verdicts obtained above, recorded now that there are answer rows for them
    # to name (ADR 0055's promised reference). One row per comment and one model
    # call per comment: the judging happened once, before the write, and this is
    # the only place it is stored on the accepted path.
    for question_id, output in verdicts.items():
        record_verdict(session, output, answer_id=written[question_id].id)

    stored = StoredSubmission(
        response_id=response.id,
        is_valid=recompute_response_validity(session, response),
        first_submitted_at=response.first_submitted_at,
        last_submitted_at=response.last_submitted_at,
        floored=any(was_floored(output) for output in verdicts.values()),
    )
    logger.info(
        "stored a weekly submission for section %s week %s (valid=%s, floored=%s)",
        section.id,
        window.week_id,
        stored.is_valid,
        stored.floored,
    )
    return stored
