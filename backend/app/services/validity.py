"""Whether a submission counts, and what to do when the classifier cannot say (SPEC §3.3).

§13 gives this module the synchronous gating the submit path runs and the async
half that finishes the job afterwards. `app.ai.tasks` owns *how* a comment is
classified — the prompt, the budget, the floor, the stored row — and this module
owns what a **student-facing write path** does with the answer, which is a
different question with a person on the other end of it.

Three decisions live here and nowhere else.

**Which provider failures a student is refused for.** §3.3 sanctions exactly one
fail-open, and ADR 0056's table says which failures are inside it:
`AIProviderUnavailableError` — a read or write timeout, or an availability status
— never reaches this module at all, because `classify_comment_validity` absorbs it
and returns the character floor. The other three do reach it, and
[ADR 0114](../../../docs/adr/0114-an-unclassifiable-comment-refuses-rather-than-floors.md)
is the record of what happens then: an honest retryable refusal, `Retry-After: 60`,
and nothing stored. Catching `AIGatewayError` here instead would widen the one
sanctioned fail-open to every failure there is, including the ones an attacker can
force by dropping packets — which is ADR 0056's own argument for keeping them out.

**Whether a verdict bounces.** §3.3 refuses an `insufficient` or a `nonsense`
comment at submit time with coaching copy, "never silently penalized after the
fact". The rule reads the verdict and never asks what produced it: a floor verdict
and a model's verdict are the same type carrying the same vocabulary (ADR 0054), so
a comment the floor calls too brief is refused with the same sentence a model's
would be — the student can fix it, and the alternative is storing a submission
this system has already decided does not count.

**And a bounce keeps the verdict that produced it.** The judging is separate from
the recording (`verdict_for_submitted_comment` and `record_verdict`) so that the
submit path can ask the model once and then decide where the row goes: against the
`answer` row on an accepted submission, and against nothing on a bounced one,
where §3.3 stores nothing as submitted. Discarding it was the natural shape and
the wrong one — §7.4 rests auditability on "a specific prompt version and model ID
produced a specific classification", and a rolled-back row is the one way to lose
that which ADR 0055's grant cannot prevent, because the row is never committed at
all. ADR 0114 records the rule and what it costs, ruled 2026-09-03: the bounced
comment's *text* is not stored, so it is outside the reach of §5.2's moderation and
§6.2's Care queue.

**What `response.is_valid` says.** The latest verdict of each submitted comment,
and nothing else. A comment left blank has no verdict and no effect (§3.3 in as
many words), and a response with no comments at all is valid.

**The async half is a sweep and not a per-comment job**, and the shape follows
from §3.3's promise rather than from convenience. A floored submission is one the
provider could not judge, so the enqueue that follows it is very likely made while
the provider is still down; a task carrying one answer's id would fail and be gone,
while a sweep re-reads whatever is still unresolved every time it runs. That also
makes the scheduled entry and the enqueued call the same call, which is what
`docs/MISTAKES.md` entry 41 asks for — the request path's publish may fail
silently, and the beat covers the gap.

**Nothing here opens a connection or reads configuration.** Both the request path
and the Celery task hand in a session, and neither commits from inside this module
except where a sweep's per-answer savepoint says so: the submit path stores a
response, its answers and their verdicts together or stores none of them.
"""

import logging
from collections.abc import Iterable, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.ai.contracts import CommentValidityOutput, ValidityVerdict
from app.ai.gateway import (
    AIGateway,
    AIProviderRefusedError,
    AIProviderUnreachableError,
    AIResponseInvalidError,
)
from app.ai.tasks import (
    FLOOR_MODEL_ID,
    FLOOR_PROMPT_VERSION,
    classify_comment_validity,
    record_classification,
    verdict_for_comment,
)
from app.models.ai import Classification, ClassificationTask
from app.models.survey import Answer, Response

__all__ = [
    "REFUSED_VERDICTS",
    "REFUSED_VERDICT_TOKENS",
    "ClassifierUnavailableError",
    "enqueue_reclassification",
    "reclassify_floored_comments",
    "recompute_response_validity",
    "record_verdict",
    "refusing_verdict",
    "verdict_for_submitted_comment",
    "was_floored",
]

logger = logging.getLogger(__name__)

# SPEC §3.3's two refused verdicts. A submission carrying either is bounced with
# the verdict's coaching copy rather than stored, whatever produced the verdict.
REFUSED_VERDICTS = frozenset({ValidityVerdict.INSUFFICIENT, ValidityVerdict.NONSENSE})

# The same two as the **tokens** a stored row carries. Two constants and not one,
# because `ValidityVerdict` is a plain `Enum` rather than a `StrEnum`: a member
# hashes by its name, so `"insufficient" in REFUSED_VERDICTS` is `False` at runtime
# and silently makes every stored verdict look acceptable. The second set is
# derived from the first rather than typed out, so a verdict added to the contract
# reaches both (ADR 0030 makes the member's value "the token stored, serialised and
# compared everywhere outside Python", which is exactly what `classification.verdict`
# holds).
REFUSED_VERDICT_TOKENS = frozenset(verdict.value for verdict in REFUSED_VERDICTS)

# The provider failures ADR 0056 keeps outside SPEC §3.3's floor, enumerated
# rather than caught by their common base class. `AIGatewayError` is the base, and
# matching on it would be a decision about every subclass including the ones added
# after this line is written — ADR 0056 says so in as many words, and it is the
# mistake that record's own rewrite corrects.
UNCLASSIFIABLE = (
    AIProviderUnreachableError,
    AIProviderRefusedError,
    AIResponseInvalidError,
)


class ClassifierUnavailableError(Exception):
    """The provider could not be asked, and ADR 0056 keeps this case out of the floor.

    Raised for a connection that reached no endpoint, an endpoint that answered
    about our own request, and an answer that was not the contract twice. The
    submit path turns it into ADR 0114's retryable refusal; nothing is stored,
    because a student who is told to try again in a minute must not be resubmitting
    over a row they were never told existed.
    """


def verdict_for_submitted_comment(
    comment: str, gateway: AIGateway | None = None
) -> CommentValidityOutput:
    """One submitted comment's verdict, with `ClassifierUnavailableError` for ADR 0056's raises.

    A thin boundary over `app.ai.tasks.verdict_for_comment`, and the whole of
    what it adds is the taxonomy decision: the availability shapes floor inside
    that function and never arrive here, and the three that do arrive become one
    exception this path answers for.

    **It judges and stores nothing**, which is what lets the submit path decide
    where the row goes once it knows whether the submission was accepted — see
    `record_verdict` below.
    """
    try:
        return verdict_for_comment(comment, gateway)
    except UNCLASSIFIABLE as failure:
        raise ClassifierUnavailableError(str(failure)) from failure


def record_verdict(
    session: Session, output: CommentValidityOutput, *, answer_id: UUID | None
) -> None:
    """Store one verdict, against the answer it judged or against nothing.

    `answer_id` is the `answer` row on an accepted submission, and `None` on a
    bounced one — where SPEC §3.3 stores nothing as submitted, so there is no
    answer row for the verdict to name. ADR 0055's rule that a classification "names
    no comment" is what makes the second case legal: the column is nullable, and
    the comment's **text** is deliberately not stored beside it, because a comment
    is "short and often formulaic … so a digest of one is recoverable by dictionary
    in seconds".

    Why a bounced verdict is stored at all: §7.4 rests auditability on "a specific
    prompt version and model ID produced a specific classification", and a student
    bounced three times is three model calls that were made, answered and paid for.
    A bounce that discarded them would leave §6.1's drift panel sampling none of
    them and an administrator asking why a student's comment keeps being refused
    with no row to look at. ADR 0114 records the rule and the limitation it leaves.

    One line, and it exists so that `app.services.submissions` reaches
    `app.ai.tasks.record_classification` — still the one place a classification row
    is written — through this module rather than importing the AI layer to write an
    audit row.
    """
    record_classification(session, ClassificationTask.COMMENT_VALIDITY, output, answer_id=answer_id)


def was_floored(output: CommentValidityOutput) -> bool:
    """Did §3.3's character floor produce this verdict rather than a model?

    Asked of the audit pair, which is the whole point of ADR 0054: a floored row
    "names no prompt file and no model", so a reader — and this sweep — can tell a
    verdict a model produced from one produced during an outage. Both halves are
    compared, because either alone is a value a provider could in principle report.
    """
    return output.prompt_version == FLOOR_PROMPT_VERSION and output.model_id == FLOOR_MODEL_ID


def refusing_verdict(outputs: Iterable[CommentValidityOutput]) -> ValidityVerdict | None:
    """The first verdict that bounces this submission, or `None` if none does.

    First rather than all of them: §3.3 tells the student one thing, and a page
    listing every comment that fell short is a shape the ticket does not ask for
    and the copy is not written in.
    """
    for output in outputs:
        if output.verdict in REFUSED_VERDICTS:
            return output.verdict
    return None


# ---------------------------------------------------------------------------
# What `response.is_valid` says, and the one place it is computed.
# ---------------------------------------------------------------------------


def _latest_verdicts(session: Session, response_id: UUID) -> Sequence[str]:
    """The most recent verdict of each of one response's comments.

    `classification` is append-only (ADR 0055), so a comment classified twice has
    two rows and the later one is the current answer. The ordering is
    `classified_at` and then the row's own key: the timestamp is a server default
    at second-and-microsecond resolution, and two rows written inside one
    transaction can carry the same value, so a tie-break that is not the clock is
    what keeps this deterministic.
    """
    answer_ids = select(Answer.id).where(
        Answer.response_id == response_id, Answer.comment_text.is_not(None)
    )
    verdicts: list[str] = []
    for answer_id in session.scalars(answer_ids):
        latest = session.scalars(
            select(Classification.verdict)
            .where(
                Classification.answer_id == answer_id,
                Classification.task == ClassificationTask.COMMENT_VALIDITY,
            )
            .order_by(Classification.classified_at.desc(), Classification.id.desc())
            .limit(1)
        ).first()
        if latest is not None:
            verdicts.append(latest)
    return verdicts


def recompute_response_validity(session: Session, response: Response) -> bool:
    """Set `response.is_valid` from the current verdicts of its comments, and answer it.

    The one writer of that column, so "what makes a week count" is a question with
    one place to read (§3.3). It is called twice on a response's life: by the submit
    path, over the verdicts it has just obtained, and by the sweep below when a
    model finally judges a comment the floor stood in for.

    **A comment with no verdict contributes nothing**, rather than making the
    response invalid. That state is unreachable through the submit path — every
    submitted comment is classified before anything is committed — and if it is ever
    reached, a row nobody classified is not evidence that a student wrote a poor
    answer.
    """
    verdicts = _latest_verdicts(session, response.id)
    response.is_valid = not any(verdict in REFUSED_VERDICT_TOKENS for verdict in verdicts)
    session.flush()
    return response.is_valid


# ---------------------------------------------------------------------------
# The async half of §3.3's fail-open.
# ---------------------------------------------------------------------------


# The connection this publish is made on, and it is deliberately not the one the
# worker uses. `docs/MISTAKES.md` entry 41's three protections turned out not to be
# enough on their own, and this is the measurement:
#
#     apply_async(retry=False, ignore_result=True)   against a closed port
#         → kombu.exceptions.OperationalError after 6.04s
#
# `retry=False` governs the *publish* retry policy and nothing else.
# `kombu.Connection.default_channel` — which the publish reaches through when it is
# handed no connection — runs `_ensure_connection` with kombu's own defaults
# (`interval_start=2, interval_step=2`), so a broker that refuses instantly is
# retried on a schedule of its own before the publish is ever attempted. Six
# seconds is under entry 41's twenty and over SPEC §10's 2.5-second budget for the
# whole submit round trip, so the request is still hanging on a background
# dependency — just less obviously.
#
# So the connection is made here, for this publish, with the retries off where they
# actually live, and its socket timeouts bounded. Measured on the same closed port:
# **0.037s**; against a blackholed address, where the refusal never comes at all,
# **1.04s** rather than the two minutes the operating system would otherwise spend.
# Against a broker that answers, the message is published in 0.046s.
#
# **Scoped to this connection and not set on `celery_app`.** A worker whose broker
# blips must reconnect rather than give up, so `broker_transport_options` is the
# wrong place for `max_retries: 0` — it is the request path that may not wait, and
# only the request path.
PUBLISH_TRANSPORT_OPTIONS = {
    "max_retries": 0,
    "socket_connect_timeout": 1.0,
    "socket_timeout": 1.0,
}
PUBLISH_CONNECT_TIMEOUT = 1.0


def enqueue_reclassification() -> bool:
    """Ask a worker to run the sweep below soon, and never fail or delay the request.

    `docs/MISTAKES.md` entry 41 is the whole design of these lines, and each
    protection is doing a different job:

      - **`retry=False`** — the publish is attempted once. Entry 41's incident is
        `task.delay(...)` against a Redis that was not there holding each request
        "for roughly twenty seconds and then raised", out of a handler that had
        already done its own job.
      - **a connection of this call's own, with `max_retries: 0` and bounded socket
        timeouts** — see `PUBLISH_TRANSPORT_OPTIONS` above, which carries the
        measurement. Without it the two protections above still leave six seconds
        on a request that SPEC §10 gives two and a half.
      - **`ignore_result=True`** — nothing reads this task's answer, and the result
        backend has a connection and a retry policy of its own. A task whose result
        nobody wants must not consult it.
      - **the broad `except`** — the submission is already stored and committed by
        the time this runs, and the one thing that must not happen is a student
        being told their week failed because a queue was unavailable. kombu,
        redis-py and Celery each raise their own family here, and an enumerated
        list of them is a list that goes stale into a failed submission.

    **The scheduled entry is what covers the gap.** `app.jobs.schedules` runs the
    same sweep hourly, so a publish that failed costs at most an hour of a floored
    verdict standing — which is exactly the trade entry 41's rule describes. The
    failure is logged at error level, which is the visibility.

    Answers whether the publish went out, for a caller that wants to say so; no
    caller has to.
    """
    # Imported here rather than at module scope because `app.jobs.tasks` imports
    # this module: the task is a thin wrapper over these functions, so a top-level
    # import would be a cycle. Same shape as `app.services.roster_sync`'s trigger.
    from app.jobs.celery_app import celery_app
    from app.jobs.tasks import reclassify_floored_comments as task

    try:
        with celery_app.connection_for_write(
            transport_options=PUBLISH_TRANSPORT_OPTIONS,
            connect_timeout=PUBLISH_CONNECT_TIMEOUT,
        ) as connection:
            task.apply_async(retry=False, ignore_result=True, connection=connection)
    except Exception:
        logger.exception(
            "a floored classification could not be enqueued for re-classification; the "
            "scheduled sweep will reach it"
        )
        return False
    return True


# The same table, read a second time as the verdict that would resolve a floored
# one. An alias rather than a second import, because both legs below are
# `classification` and the correlated condition has to be able to say which row it
# means.
_JudgedVerdict = aliased(Classification, name="judged_verdict")


def unresolved_floored_answers(session: Session) -> Sequence[UUID]:
    """Every comment whose only verdicts came from the floor (ADR 0054, ADR 0055).

    Found by the audit pair rather than by a flag, which is what ADR 0054 spends
    the pair on: "E2's async re-classification finds the floor rows by exactly this
    pair, and if every row already looks classified there is nothing to find." A
    comment that has since been judged by a model has a row whose prompt version is
    a real prompt stem, and it drops out of this set — that is what "resolved"
    means, and it is read off the rows rather than written onto them, because
    `classification` takes no `UPDATE` (ADR 0055).

    **The anti-join is `NOT EXISTS` and may never go back to `NOT IN`** (E2-16
    item 4, and `tests/integration/test_the_floored_comment_sweep_survives_a_terms_volume.py`
    reads the statements off the wire to hold it). Postgres runs `NOT IN
    (SELECT …)` as a hashed subplan and abandons the hash once it outgrows
    `work_mem` — 4MB by default — after which it rescans `classification` once per
    outer row. The epic-boundary review measured this query at **72 seconds** over
    ~300k rows, 46 with the supporting index alone, and **166ms** in this shape
    with the index. The job is enqueued on every floored submission and again on a
    beat, so it runs hardest during the provider outage that produced the rows.

    The near miss that is not a repair: fetching the judged set into Python and
    sending it back as `NOT IN (:p1, :p2, …)`. That is the same unbounded set moved
    from the planner into the request.

    **The supporting index is `ix_classification_task_prompt_version`**, on the two
    columns both legs filter (`b1e7d4a90c26`). The rewrite and the index are not
    substitutes for each other and the measurements above are why.
    """
    # `answer_id IS NOT NULL` on the inner leg is implied by the correlation — a
    # null there can never equal the outer row's non-null answer — and it is kept
    # because it is the old shape's own filter and its absence would read as a
    # dropped condition rather than as an implication.
    judged = (
        select(_JudgedVerdict.id)
        .where(
            _JudgedVerdict.answer_id == Classification.answer_id,
            _JudgedVerdict.task == ClassificationTask.COMMENT_VALIDITY,
            _JudgedVerdict.prompt_version != FLOOR_PROMPT_VERSION,
            _JudgedVerdict.answer_id.is_not(None),
        )
        .correlate(Classification)
    )
    floored = (
        select(Classification.answer_id)
        .where(
            Classification.task == ClassificationTask.COMMENT_VALIDITY,
            Classification.prompt_version == FLOOR_PROMPT_VERSION,
            Classification.answer_id.is_not(None),
            ~judged.exists(),
        )
        .distinct()
    )
    return [answer_id for answer_id in session.scalars(floored) if answer_id is not None]


def reclassify_floored_comments(session: Session) -> int:
    """Re-run every unresolved floored classification, and answer how many were run.

    SPEC §3.3's second half: a submission accepted on the floor is "then classified
    async". Each comment is asked again and the answer is *appended* — ADR 0055
    makes `classification` append-only and the grant withholds `UPDATE`, so a re-run
    is a new row beside the floored one rather than an edit over it, and the audit
    trail says a floor decided first and a model decided later. The response's
    validity is recomputed from the new verdict, which is the only way
    `response.is_valid` ever changes after a submission is stored.

    **One comment's failure does not end the sweep.** Each runs inside a savepoint,
    a failure rolls back that comment's own partial work and is logged with its
    traceback, and the walk moves on — the shape
    `app.services.survey_windows.derive_windows_for_all_sections` already takes. The
    catch is broad on purpose: the provider is very often still down when this runs
    (that is why the comment was floored), and every one of ADR 0056's classes plus
    anything a driver raises would otherwise starve every later comment in the walk.

    **A comment the provider still cannot judge stays in the set**, because the row
    this run appends is another floored one. That is correct rather than wasteful:
    the whole point of finding the rows by their audit pair is that "not yet judged
    by a model" is a fact about the rows, so the next run picks the comment up
    again with nothing to remember.

    Commits nothing. The caller owns the transaction — `app.jobs.tasks` opens a
    session, calls this, and commits — for the same reason every other service in
    this tree leaves it to its caller.
    """
    answer_ids = unresolved_floored_answers(session)
    logger.info("the re-classification sweep found %d floored comment(s)", len(answer_ids))
    reclassified = 0
    for answer_id in answer_ids:
        savepoint = session.begin_nested()
        try:
            answer = session.get(Answer, answer_id)
            if answer is None or answer.comment_text is None:
                savepoint.rollback()
                continue
            classify_comment_validity(session, answer.comment_text, answer_id=answer.id)
            response = session.get(Response, answer.response_id)
            if response is not None:
                recompute_response_validity(session, response)
            savepoint.commit()
            reclassified += 1
        except Exception:
            savepoint.rollback()
            logger.exception(
                "the re-classification sweep could not re-run the verdict for answer %s", answer_id
            )
    return reclassified
