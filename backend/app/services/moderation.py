"""SPEC §5.2 and §6.2's moderation: the call that writes a verdict (E6-01) and a person's decision (E6-03).

A comment reaches no reader until it holds a moderation verdict
(`report_comment` v004, ADR 0187), and a verdict is written only through the
routing definer `public.route_moderation_verdict`
(`app/views_sql/moderation_routing_v001.sql`). That function writes the
verdict and its route in one call: a `FLAGGED_COLLAPSED` decision for a harmful
or privacy verdict, a Care case for a threat or self-harm verdict, nothing more
for clear or nonsense. A trigger refuses a moderation verdict written any other
way, so the verdict half of this module holds no insert of its own; it is the
`services/roster_sync.py` pattern for `end_teaching_instructor`. The one insert
here is a person's decision, below.

**Seeds and fixtures plant verdicts here too**, under `SEED_PROMPT_VERSION` and
`SEED_MODEL_ID`. A real prompt version names a prompt file (`moderation.v1`, say,
ADR 0031), so `"seed"` can never be mistaken for one, and §6.1's drift panel and
§9.3's eval floors can leave seeded rows out by that value.

**A verdict is written only once its comment's window has closed.** An answer is
revised in place when a student resubmits (ADR 0115), and every reader keys "holds
a verdict" on the answer id, so a verdict written while the window is open would
vouch for text the student can still replace: `clear` on Friday, a self-harm
disclosure resubmitted into the same row on Sunday, shown as moderated and routed
to nobody. So `route_verdict` refuses an answer whose survey window has not closed
by the app clock (ADR 0109), and refuses one with no window at all, before writing
anything. The definer does not repeat the check, because the close is judged by
the app clock, which the database cannot read, and every writer comes through
here (ADR 0187).

**The sweep** (`sweep_unmoderated_comments`) is what asks a model for those
verdicts: hourly, over every comment whose window has closed and which holds no
verdict yet (ADR 0188). A failed call is retried by the next sweep, and an
unusable answer counts toward an attempt cap of six, after which the comment
stays held for good. Two sweeps never run at once, and each comment's outcome is
committed before the next is asked about.

## A person's decision (E6-03)

SPEC §5.2's lifecycle: a flagged comment is collapsed, and the instructor
excludes it or keeps it, each with an Undo; excluding a comment the AI did not
flag needs a stated reason. Every step is one row appended to
`moderation_state`, naming the decider and the role the decision was made under
(the owner's rulings 3 and 4), so §8's "both directions logged" is the table
itself.

**Two layers, and the visibility rule is in the door, not the write.**
`decide_as_instructor` is the instructor's door: it accepts only a comment the
reader's own report currently returns, found by
`app.services.reporting.comment_on_instructor_report`, which walks the report's
own reads rather than rebuilding the rule from the answer. `_record_decision`
is the shared write: the transition table, the undo rule, the reason rule and
the insert. It takes the comment's card and the decider and role from its
caller, and nothing that widens what it accepts. E6-05 adds the Lead Faculty's
door with a check of its own; a second door calls the same write and cannot
loosen the first.

**The write appends and never orders.** What it needs to know about the latest
row it asks `app.services.report_comments.latest_decision`, the one home of
that ordering. Two decisions about one comment are serialized by a
transaction-scoped advisory lock on the comment, so an undo cannot be judged
against a row a colleague is replacing at the same moment.

**Undo has one rule** (the owner's ruling of 2026-10-10): it looks at the
comment's latest row only, and succeeds only when that row is a decision (not
an undo) made by this same person under this same role. It appends a row
holding the state from before that decision, marked `is_undo`. Anything else,
including an undo of an undo, is refused and writes nothing.

**No audit-log row.** A decision is its own record; SPEC §8's audit log holds no
exclusion or keep.
"""

import logging
from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import ColumnElement, SQLColumnExpression, func, insert, select, text
from sqlalchemy.orm import Session

from app.ai.contracts import ModerationVerdict
from app.ai.gateway import (
    AIGateway,
    AIProviderRefusedError,
    AIProviderUnavailableError,
    AIProviderUnreachableError,
    AIResponseInvalidError,
)
from app.ai.tasks import classify_comment_moderation
from app.config import Settings
from app.models.ai import Classification, ClassificationTask, ModerationAttempt
from app.models.report import REASON_BOUND, DeciderRole, ModerationState
from app.models.survey import Answer, Question, QuestionKind, Response
from app.models.term import SurveyWindow
from app.services import clock
from app.services.survey_windows import closed_by

if TYPE_CHECKING:  # pragma: no cover - imported for annotations only
    from app.schemas.report import CommentView
    from app.services.report_comments import CommentCard

logger = logging.getLogger(__name__)

# The provenance a seed script or a test fixture plants a verdict under. Never a
# real prompt version or model id (E6-01 work order, decision 4).
SEED_PROMPT_VERSION = "seed"
SEED_MODEL_ID = "seed"


# How many unusable answers one comment may get before the sweep stops asking
# (ADR 0188). Six hourly sweeps: long enough to ride out a bad deploy of a prompt
# or a model, short enough that a comment no model can answer does not hold its
# section-week's summary back for days.
MODERATION_ATTEMPT_CAP = 6

# The one failure that counts toward the cap: the provider answered, and the
# answer was not the contract even after the gateway's re-ask. Something about
# this comment may be what breaks the model, so asking for ever is not safe.
COUNTED_FAILURES = (AIResponseInvalidError,)

# The failures that count nothing: a refusal (`AIProviderRefusedError`, HTTP 401,
# 429, 500 and the like: a key, a rate limit, a provider bug) and an outage
# (`AIProviderUnavailableError`, which includes a read timeout, or
# `AIProviderUnreachableError`). Each is about the provider or this account, not
# the comment, and lasts as long as it lasts. A cap that counted them would hold
# back for good exactly the comments swept during one, Care-class disclosures
# among them, so the comment is simply asked about again next hour (ADR 0188).
RETRIED_FAILURES = (
    AIProviderRefusedError,
    AIProviderUnavailableError,
    AIProviderUnreachableError,
)

# The Postgres advisory lock key that keeps two sweeps from running at once
# (ADR 0188). Any fixed bigint will do as long as no other lock uses it; this is
# the only advisory lock in the application. The digits are the ticket and the
# ADR (E6-02, 0188), so a reader of `pg_locks` can tell whose it is.
SWEEP_LOCK_KEY = 6_020_188


class ModerationBeforeClose(ValueError):  # noqa: N818 - the name the fix round settles
    """A verdict was asked for a comment whose survey window has not closed, and nothing was written.

    Also raised for an answer whose response has no survey window, or for an id
    that names no answer: with no close to judge against, the comment is treated
    as still open (fail closed). Carries the answer id and nothing else.
    """


_ROUTE_THE_VERDICT = text(
    "SELECT public.route_moderation_verdict("
    "CAST(:answer_id AS uuid), CAST(:verdict AS text), "
    "CAST(:prompt_version AS text), CAST(:model_id AS text))"
)


def route_verdict(
    session: Session,
    answer_id: UUID,
    verdict: ModerationVerdict,
    *,
    prompt_version: str,
    model_id: str,
) -> UUID:
    """Write one moderation verdict about one comment, and its route, in one call.

    Answers the new `classification` row's id. Runs inside the caller's
    transaction and commits nothing, so a caller writing several things together
    keeps them together. The stored token is the enum member's value (ADR 0030).

    Raises `ModerationBeforeClose`, writing nothing, when the comment's window has
    not closed by `app.services.clock` — closed is `closes_at < now`, the
    survey-window module's own `closed_by`, so the closing instant itself is
    still open — or when the comment has no window. Otherwise raises whatever the database raises: an
    unknown verdict or a failed route each fail the whole call, and the verdict is
    not stored without its route.
    """
    _refuse_before_the_close(session, answer_id)
    routed = session.execute(
        _ROUTE_THE_VERDICT,
        {
            "answer_id": str(answer_id),
            "verdict": verdict.value,
            "prompt_version": prompt_version,
            "model_id": model_id,
        },
    ).scalar_one()
    if not isinstance(routed, UUID):
        raise TypeError(
            f"public.route_moderation_verdict answered {type(routed).__name__}, not a uuid; "
            "the function's signature returns the new classification's id."
        )
    return routed


def _refuse_before_the_close(session: Session, answer_id: UUID) -> None:
    """Raise `ModerationBeforeClose` unless the answer's survey window has closed.

    The clock is read as `clock.now`, through the module, so that ADR 0109's
    effective clock (and a test standing it on an instant) is the one judged.
    "Closed" is `app.services.survey_windows.closed_by`, the negation of what
    that module calls open, so the router and the survey cannot disagree about
    the closing instant (E6-03, decision 8; ADR 0187's amendment).
    """
    now = clock.now(session, settings=Settings())
    closed = session.execute(
        select(closed_by(now))
        .join_from(Answer, Response, Response.id == Answer.response_id)
        .join(
            SurveyWindow,
            (SurveyWindow.section_id == Response.section_id)
            & (SurveyWindow.week_id == Response.week_id),
        )
        .where(Answer.id == answer_id)
    ).scalar_one_or_none()
    if closed is None:
        raise ModerationBeforeClose(
            f"{answer_id} names no comment with a survey window, so there is no close to judge "
            "its text at and no moderation verdict was written."
        )
    if not closed:
        raise ModerationBeforeClose(
            f"The survey window of {answer_id} has not closed, so its text can still be "
            "resubmitted and no moderation verdict was written (ADR 0187)."
        )


def under_the_attempt_cap(answer_id: SQLColumnExpression[Any]) -> ColumnElement[bool]:
    """True for an answer with fewer than `MODERATION_ATTEMPT_CAP` failed moderation calls.

    The one statement of the cap as SQL. The sweep reads it to decide what to ask
    about, and `app.services.report_comments.section_week_moderated` reads it to
    stop waiting on a comment the sweep has given up on.
    """
    attempts = (
        select(func.count(ModerationAttempt.id))
        .where(ModerationAttempt.answer_id == answer_id)
        .scalar_subquery()
    )
    return attempts < MODERATION_ATTEMPT_CAP


def holds_no_verdict(answer_id: SQLColumnExpression[Any]) -> ColumnElement[bool]:
    """True for an answer with no `MODERATION` classification."""
    return ~(
        select(Classification.id)
        .where(
            Classification.answer_id == answer_id,
            Classification.task == ClassificationTask.MODERATION,
        )
        .exists()
    )


def comments_awaiting_moderation(session: Session) -> Sequence[UUID]:
    """Every comment the sweep should ask about now.

    A comment (an answer to a `comment` question with text that is not blank)
    whose survey window has closed by the app clock, which holds no moderation
    verdict and is under the attempt cap. Closed is
    `app.services.survey_windows.closed_by`, the product's one definition of a
    closed window (`closes_at < now`, ADRs 0188 and 0189), which `route_verdict`
    asks too, so the sweep never picks a comment the router would refuse. The
    anti-join is `NOT EXISTS`, the shape
    `app.services.validity.unresolved_floored_answers` argues for.

    Blank is `str.strip()`, decided in Python as `report_comment_v003.sql` and
    `section_week_moderated` decide it; the text is read for that and nothing else.
    """
    now = clock.now(session, settings=Settings())
    rows = session.execute(
        select(Answer.id, Answer.comment_text)
        .join(Response, Response.id == Answer.response_id)
        .join(Question, Question.id == Answer.question_id)
        .join(
            SurveyWindow,
            (SurveyWindow.section_id == Response.section_id)
            & (SurveyWindow.week_id == Response.week_id),
        )
        .where(
            Question.kind == QuestionKind.COMMENT,
            Answer.comment_text.is_not(None),
            closed_by(now),
            holds_no_verdict(Answer.id),
            under_the_attempt_cap(Answer.id),
        )
        .order_by(Answer.id)
    ).all()
    return [answer_id for answer_id, written in rows if written is not None and written.strip()]


def sweep_unmoderated_comments(session: Session, gateway: AIGateway | None = None) -> int:
    """Ask a model about every comment awaiting moderation, and route each verdict.

    Answers how many verdicts were routed, for a log line. **This function owns
    the transaction**: it commits once it holds the lock, and again after each
    comment, so a verdict and its Care route are stored before the next comment
    is asked about and a later error cannot take them back.

    **Two sweeps never overlap.** The sweep first takes a Postgres session-level
    advisory lock on `SWEEP_LOCK_KEY`. If another run holds it, this one answers
    0 and touches nothing: two runs at once would ask twice, and one could give a
    verdict to a comment the other had just capped, after its week had been read
    without it. The lock is released in `finally`, on every path.

    - A verdict is routed through `route_verdict`, which writes it with its flag
      or its Care case.
    - An unusable answer (`COUNTED_FAILURES`) appends one `moderation_attempt`
      row. The one that reaches the cap is logged at error level, by answer id
      only; the comment then stays held, never given a verdict (ADR 0188).
    - A refusal or an outage (`RETRIED_FAILURES`) writes nothing and is logged at
      error level; the next sweep asks again.

    Anything else is rolled back to the last commit and propagates.
    """
    locked = session.execute(select(func.pg_try_advisory_lock(SWEEP_LOCK_KEY))).scalar_one()
    if not locked:
        logger.info("the moderation sweep found another run holding its lock and did nothing")
        return 0
    try:
        session.commit()
        return _moderate_each(session, gateway)
    except BaseException:
        session.rollback()
        raise
    finally:
        session.execute(select(func.pg_advisory_unlock(SWEEP_LOCK_KEY)))
        session.commit()


def _moderate_each(session: Session, gateway: AIGateway | None) -> int:
    """The sweep's walk, under its lock: one comment at a time, one commit each."""
    answer_ids = comments_awaiting_moderation(session)
    logger.info("the moderation sweep found %d comment(s) awaiting a verdict", len(answer_ids))
    routed = 0
    for answer_id in answer_ids:
        comment = session.execute(
            select(Answer.comment_text).where(Answer.id == answer_id)
        ).scalar_one()
        if comment is None:
            continue
        try:
            output = classify_comment_moderation(comment, gateway)
        except COUNTED_FAILURES as failed:
            _record_a_failed_attempt(session, answer_id, failed)
            session.commit()
            continue
        except RETRIED_FAILURES as failed:
            logger.error(
                "the moderation sweep left answer %s for the next run after an %s",
                answer_id,
                type(failed).__name__,
            )
            continue
        route_verdict(
            session,
            answer_id,
            output.verdict,
            prompt_version=output.prompt_version,
            model_id=output.model_id,
        )
        session.commit()
        routed += 1
    return routed


def _record_a_failed_attempt(session: Session, answer_id: UUID, failed: Exception) -> None:
    """Append one attempt row, and log once at error level when it reaches the cap.

    Logged by answer id and the failure's class name only: the text of the
    comment, and whatever the provider put in its error, stay out of the log
    (SPEC §10).
    """
    session.add(ModerationAttempt(answer_id=answer_id))
    session.flush()
    attempts = session.execute(
        select(func.count(ModerationAttempt.id)).where(ModerationAttempt.answer_id == answer_id)
    ).scalar_one()
    if attempts == MODERATION_ATTEMPT_CAP:
        logger.error(
            "answer %s reached the moderation attempt cap of %d and stays held without a verdict",
            answer_id,
            MODERATION_ATTEMPT_CAP,
        )
    else:
        logger.warning(
            "the moderation sweep could not use the answer for answer %s (%s), attempt %d of %d",
            answer_id,
            type(failed).__name__,
            attempts,
            MODERATION_ATTEMPT_CAP,
        )


# ---------------------------------------------------------------------------
# A person's decision (E6-03).
# ---------------------------------------------------------------------------


class DecisionAction(StrEnum):
    """What a decider may ask for: SPEC §5.2's exclude and keep, and the Undo of either."""

    EXCLUDE = "exclude"
    KEEP = "keep"
    UNDO = "undo"


# The state each action leaves a comment in, and the states it may be taken from
# (E6-03's work order, decision 3). Asking for the state a comment already holds
# is not in the table, so it is refused rather than written twice.
EXCLUDED = "EXCLUDED"
KEPT = "KEPT"
LEAVES = {DecisionAction.EXCLUDE: EXCLUDED, DecisionAction.KEEP: KEPT}
ALLOWED_FROM = {
    DecisionAction.EXCLUDE: frozenset({"PUBLISHED", "FLAGGED_COLLAPSED", KEPT}),
    DecisionAction.KEEP: frozenset({"FLAGGED_COLLAPSED", EXCLUDED}),
}


class CommentNotOnReportError(LookupError):
    """The answer is not a comment the reader's report currently returns; nothing was written.

    One error for every case (a held comment, another section's, a rating, a
    Care-class comment, an id nothing holds), so the door can answer them alike.
    """


class DecisionNotAllowedError(ValueError):
    """The comment's current state, or its latest row, does not allow this action; nothing written."""


class ReasonRefusedError(ValueError):
    """The stated reason was refused as sent, and nothing was written."""


class ReasonMissingError(ReasonRefusedError):
    """An unflagged comment was excluded with no reason (SPEC §5.2)."""


class ReasonBlankError(ReasonRefusedError):
    """A reason was given and holds nothing but whitespace."""


class ReasonTooLongError(ReasonRefusedError):
    """A reason was given longer than `REASON_BOUND` characters, as sent."""


def decide_as_instructor(
    session: Session,
    *,
    person_id: UUID | None,
    answer_id: UUID,
    action: DecisionAction,
    reason: str | None,
    settings: Settings,
) -> "CommentView":
    """The instructor's door: one decision on a comment their own report returns, committed.

    **The comment is found the way the report finds it**, by
    `comment_on_instructor_report`, and an answer it does not return is refused
    with `CommentNotOnReportError` before anything else is asked, so the refusal
    is the same whatever the id was. A session naming no person decides nothing.

    Then the shared write judges the action, and the decision is committed.
    Answers the comment as the report now shows it, read back through the same
    walk, so the answer and the next report cannot disagree.

    Raises `CommentNotOnReportError`, `DecisionNotAllowedError` or a
    `ReasonRefusedError`, each having written nothing.
    """
    # Imported here rather than at module scope: `app.services.report_comments`
    # imports this module for the attempt cap (E6-02), so a module-scope import
    # back would be a cycle. The same device `app.services.reporting._payload`
    # uses for its schema.
    from app.services.reporting import comment_on_instructor_report, comment_view

    if person_id is None:
        raise CommentNotOnReportError
    card = comment_on_instructor_report(
        session, person_id=person_id, answer_id=answer_id, settings=settings
    )
    if card is None:
        raise CommentNotOnReportError
    _record_decision(
        session,
        card=card,
        action=action,
        reason=reason,
        decided_by=person_id,
        decided_as=DeciderRole.INSTRUCTOR,
    )
    session.commit()
    after = comment_on_instructor_report(
        session, person_id=person_id, answer_id=answer_id, settings=settings
    )
    if after is None:  # pragma: no cover - a decision never takes a comment off the report
        raise RuntimeError(f"{answer_id} left the report its decision was made on.")
    return comment_view(after, reader=person_id)


def _record_decision(
    session: Session,
    *,
    card: "CommentCard",
    action: DecisionAction,
    reason: str | None,
    decided_by: UUID,
    decided_as: DeciderRole,
) -> None:
    """The shared write: judge one action on one comment, and append its row.

    The caller has already decided this person may act on this comment; this
    decides whether the action is allowed now, and writes it. In order:

      1. the comment is locked against a concurrent decision, for this
         transaction;
      2. the action is judged against the latest row (`latest_decision`): the
         transition table for exclude and keep, the one undo rule for undo;
      3. the reason is judged as it was sent, before any trimming
         (`docs/MISTAKES.md` entry 29);
      4. one row is inserted, naming exactly the six columns `pulse_app` may
         insert (`moderation_decision_grants_v001.sql`).

    Raises `DecisionNotAllowedError` or a `ReasonRefusedError`, having written
    nothing. Commits nothing.
    """
    # At call time, for the cycle `decide_as_instructor` describes.
    from app.services.report_comments import INITIAL_STATE, latest_decision

    session.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(str(card.answer_id), 0)))
    )
    latest = latest_decision(session, card.answer_id)
    if action is DecisionAction.UNDO:
        if (
            latest is None
            or latest.is_undo
            or latest.decided_by != decided_by
            or latest.decided_as != decided_as.value
        ):
            raise DecisionNotAllowedError
        state, is_undo = latest.state_before, True
    else:
        current = INITIAL_STATE if latest is None else latest.state
        if current not in ALLOWED_FROM[action]:
            raise DecisionNotAllowedError
        state, is_undo = LEAVES[action], False

    _refuse_the_reason(reason, required=action is DecisionAction.EXCLUDE and card.flag is None)

    session.execute(
        insert(ModerationState).values(
            answer_id=card.answer_id,
            state=state,
            decided_by_person_id=decided_by,
            decided_as=decided_as.value,
            reason=reason,
            is_undo=is_undo,
        )
    )


def _refuse_the_reason(reason: str | None, *, required: bool) -> None:
    """Refuse a reason as it was sent: missing where one is required, blank, or too long.

    SPEC §5.2: excluding a comment the AI did not flag requires a stated reason.
    A reason given anywhere else is optional and held to the same bounds. The
    length is measured before anything is trimmed, so a reason padded past the
    bound is refused rather than repaired (`docs/MISTAKES.md` entry 29); blank is
    `str.strip()`'s whitespace, the set the table's `CHECK` lists by code point.
    """
    if reason is None:
        if required:
            raise ReasonMissingError
        return
    if len(reason) > REASON_BOUND:
        raise ReasonTooLongError
    if not reason.strip():
        raise ReasonBlankError
