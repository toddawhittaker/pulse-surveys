"""SPEC §5.2 and §6.2's moderation verdicts: the one Python call that writes one (E6-01).

A comment reaches no reader until it holds a moderation verdict
(`report_comment` v004, ADR 0187), and a verdict is written only through the
routing definer `public.route_moderation_verdict`
(`app/views_sql/moderation_routing_v001.sql`). That function writes the
verdict and its route in one call: a `FLAGGED_COLLAPSED` decision for a harmful
or privacy verdict, a Care case for a threat or self-harm verdict, nothing more
for clear or nonsense. A trigger refuses a moderation verdict written any other
way, so this module holds no insert of its own; it is the
`services/roster_sync.py` pattern for `end_teaching_instructor`.

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
stays held for good. E6-03 adds the instructor's decisions beside this.
"""

import logging
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, SQLColumnExpression, func, select, text
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
from app.models.survey import Answer, Question, QuestionKind, Response
from app.models.term import SurveyWindow
from app.services import clock

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

# The failures that count toward the cap: the provider answered and the answer
# could not be used. An outage (`AIProviderUnavailableError`, which includes a
# read timeout, or `AIProviderUnreachableError`) writes no attempt, so a comment
# is retried for as long as an outage lasts and is never parked by one. A cap
# that counted outages would hold back for good exactly the comments written
# during one, Care-class disclosures among them (ADR 0188).
COUNTED_FAILURES = (AIResponseInvalidError, AIProviderRefusedError)
OUTAGES = (AIProviderUnavailableError, AIProviderUnreachableError)


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
    not closed by `app.services.clock` — `now >= closes_at` is closed — or when
    the comment has no window. Otherwise raises whatever the database raises: an
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
    """
    closes_at = session.execute(
        select(SurveyWindow.closes_at)
        .join_from(Answer, Response, Response.id == Answer.response_id)
        .join(
            SurveyWindow,
            (SurveyWindow.section_id == Response.section_id)
            & (SurveyWindow.week_id == Response.week_id),
        )
        .where(Answer.id == answer_id)
    ).scalar_one_or_none()
    if closes_at is None:
        raise ModerationBeforeClose(
            f"{answer_id} names no comment with a survey window, so there is no close to judge "
            "its text at and no moderation verdict was written."
        )
    if clock.now(session, settings=Settings()) < closes_at:
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
    verdict and is under the attempt cap. Closed is `now >= closes_at`, the test
    `route_verdict` applies. The anti-join is `NOT EXISTS`, the shape
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
            SurveyWindow.closes_at <= now,
            holds_no_verdict(Answer.id),
            under_the_attempt_cap(Answer.id),
        )
        .order_by(Answer.id)
    ).all()
    return [answer_id for answer_id, written in rows if written is not None and written.strip()]


def sweep_unmoderated_comments(session: Session, gateway: AIGateway | None = None) -> int:
    """Ask a model about every comment awaiting moderation, and route each verdict.

    Answers how many verdicts were routed, for a log line. Each comment runs in
    its own savepoint, so one failure costs that comment and the walk moves on.

    - A verdict is routed through `route_verdict`, which writes it with its flag
      or its Care case.
    - An unusable answer (`COUNTED_FAILURES`) appends one `moderation_attempt`
      row. The one that reaches the cap is logged at error level, by answer id
      only; the comment then stays held, never given a verdict (ADR 0188).
    - An outage (`OUTAGES`) writes nothing; the next sweep asks again.

    Anything else propagates. Commits nothing; the caller owns the transaction.
    """
    answer_ids = comments_awaiting_moderation(session)
    logger.info("the moderation sweep found %d comment(s) awaiting a verdict", len(answer_ids))
    routed = 0
    for answer_id in answer_ids:
        comment = session.execute(
            select(Answer.comment_text).where(Answer.id == answer_id)
        ).scalar_one()
        savepoint = session.begin_nested()
        try:
            output = classify_comment_moderation(comment, gateway)
            route_verdict(
                session,
                answer_id,
                output.verdict,
                prompt_version=output.prompt_version,
                model_id=output.model_id,
            )
        except COUNTED_FAILURES as failed:
            savepoint.rollback()
            _record_a_failed_attempt(session, answer_id, failed)
            continue
        except OUTAGES as outage:
            savepoint.rollback()
            logger.warning(
                "the moderation sweep left answer %s for the next run after an %s",
                answer_id,
                type(outage).__name__,
            )
            continue
        except BaseException:
            savepoint.rollback()
            raise
        savepoint.commit()
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
