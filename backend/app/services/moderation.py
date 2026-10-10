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

E6-02 adds the model call and the sweep that use this, and E6-03 adds the
instructor's decisions beside it.
"""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.ai.contracts import ModerationVerdict
from app.config import Settings
from app.models.survey import Answer, Response
from app.models.term import SurveyWindow
from app.services import clock

# The provenance a seed script or a test fixture plants a verdict under. Never a
# real prompt version or model id (E6-01 work order, decision 4).
SEED_PROMPT_VERSION = "seed"
SEED_MODEL_ID = "seed"


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
