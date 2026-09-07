"""What the Monday report stores before an instructor opens it (SPEC §5.1, §3.1).

SPEC §13 names this module for §5.1 — "distributions, trend lines, benchmark
assembly" — and E4-06 is the first ticket to need it. What lands here first is
not one of those three: it is the walk that *generates* §5.1's per-stream AI
summaries, once per section-week, after the window closes and before Monday
morning. The read side (E4-07's payload layer, which divides the counts E4-03's
views return) is the same section of the spec and belongs beside it rather than
in a module of its own, so the name §13 chose is the name used.

**One section-week is the unit of work, and it is one transaction.** §5.1 leads
each of a week's two comment groups with its own summary and E4-11 renders both;
a week that ends with the instructor's summary written and the course one missing
is a report whose halves came from different runs, and there is no regeneration
(the E4 breakdown's decision 2) to repair it. So both streams are written or
neither is, and a provider failure costs its own section-week and nothing else.

**The walk is idempotent and the beat entry is the ordinary trigger rather than
the definition of the work** — E3-06's shape in `app.services.grading`,
deliberately copied. A run selects the section-weeks that have *no* summary rows,
so a re-run fills the gaps a failed run left and writes nothing where rows
already exist. That matters more here than it does for a score: a summary an
instructor has already read must not change under them, and this walk runs again
after every failure and every restart.

**Nothing here logs a comment, a summary, a theme label or a student.** SPEC §10
forbids student personally identifiable information in logs and SPEC §4 makes a
comment the most identifying thing a student writes — the display order is
randomised and no timestamp is ever shown beside one, while a log line carries a
timestamp by construction. E3's breakdown decision 10 already held this job's
neighbour to the section, the outcome and the call; a generated summary is the
addition E4 makes to that list, because it is a paraphrase of two or three
students in a thin week and it is the value this walk is holding at exactly the
moment a debugging line would interpolate it. So the failure path below names the
section and the classes of what was raised, and nothing else.
"""

import logging
import time
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.contracts import CommentStream, WeeklySummaryRecord
from app.ai.gateway import AIGateway, AIGatewayError
from app.ai.tasks import summarize_stream
from app.config import Settings
from app.models.report import WeeklySummary
from app.models.survey import REPORT_STREAMS, Answer, Question, QuestionKind, Response
from app.models.term import SurveyWindow
from app.services import clock
from app.services.report_comments import reported_status_of

logger = logging.getLogger(__name__)

# Which `CommentStream` a stored stream token asks a model about, built from the
# tuple `app.models.survey` publishes rather than typed out again: the tokens are
# the database's (`weekly_summary.stream` and `question.stream` share the `CHECK`)
# and the enum is the contract's, and a second hand-written list of the pair is
# the copy `docs/MISTAKES.md` entry 13 is about. `CommentStream`'s member names
# are these tokens, so the mapping is derived rather than asserted.
STREAM_ASKED_ABOUT: dict[str, CommentStream] = {
    token: CommentStream[token] for token in REPORT_STREAMS
}

# The two states a moderator is holding a comment in. SPEC §5.1: the summaries
# "exclude flagged-held content". `FLAGGED_COLLAPSED` is where a comment waits for
# review and `EXCLUDED` is where it lands when the instructor takes it out; `KEPT`
# is §5.2's undo — "Keep for students" publishes the comment — so it is not here,
# and neither is `PUBLISHED`.
#
# **Held is read off the latest row and never off the history.** A comment
# excluded on Monday and kept on Tuesday feeds the summary, which is the whole
# reason E4-02 stores decisions rather than a column; a filter asking "does this
# comment have an EXCLUDED row" refuses it for ever.
HELD_MODERATION_STATES = ("FLAGGED_COLLAPSED", "EXCLUDED")


def generate_missing_summaries(
    session: Session,
    *,
    settings: Settings,
    gateway: AIGateway | None = None,
) -> dict[str, int]:
    """Summarize every closed section-week that has no summary yet (SPEC §5.1).

    `app.jobs.tasks.generate_weekly_summaries` runs this weekly. **The caller does
    not own the transaction**: this walk commits after each section-week, for the
    reason `post_scores_for_all_sections` beside it commits after each section —
    one failure may not cost the rest of the institution its Monday, and a walk
    held to one commit at the end loses every summary it had generated when the
    section after them fails.

    **A window that has closed, and the comparison is the complement of the one
    E2-06 already wrote.** `app.services.survey_windows._open_at` makes a window
    open when `opens_at <= t <= closes_at`, both ends inclusive, so closed is
    `closes_at < t` and no instant is ever both. The instant is the *effective*
    clock (ADR 0109), because which weeks have closed is exactly what a developer
    moves the clock to change — beat's own firing is outside that override, which
    is why this walk decides what to do from the database rather than from the day
    it woke up on.

    **Selected on "has no summary rows", not on "is recent".** That clause is the
    whole of the idempotence: the second of two consecutive runs finds nothing to
    do, asks the provider nothing, and leaves every stored row exactly as it was.
    An upsert would converge on the same table and rewrite what an instructor read
    this morning, which the E4 breakdown's decision 2 rules out.

    **A provider failure is absorbed and nothing else is.** ADR 0056's gateway
    classes are the interface a caller branches on, and they are what this catches:
    nobody waits on a Monday report, there is no heuristic that stands in for a
    summary (ADR 0148), and the schedule is the retry. A bare `except Exception`
    here would turn a broken query or a wrong keyword into "the provider was
    unavailable, we will try again on Monday" — every Monday, for ever, reporting
    a clean run over a silently empty report (`docs/MISTAKES.md` entry 26).

    Answers `{"written": w, "failed": f}` — the summary rows stored and the
    section-weeks whose provider call refused, which is what §6.1's console reads.
    """
    started = time.monotonic()
    awaiting = _section_weeks_awaiting_a_summary(
        session, closed_by=clock.now(session, settings=settings)
    )
    logger.info(
        "the summary walk found %d closed section-week(s) with no summary yet", len(awaiting)
    )

    written = 0
    failed = 0
    for section_id, week_id in awaiting:
        try:
            for token in REPORT_STREAMS:
                session.add(
                    _summary_row(
                        session,
                        section_id=section_id,
                        week_id=week_id,
                        token=token,
                        gateway=gateway,
                    )
                )
            # Both of §5.1's summaries are durable here, together, before the next
            # section-week is touched. A commit inside the loop above would leave a
            # half-summarized week the next run steps over, because the next run
            # asks whether the section-week has rows rather than how many.
            session.commit()
        except AIGatewayError as refused:
            session.rollback()
            # **The traceback is withheld and so are the failure's own arguments**,
            # which is where this diverges from a plain `logger.exception`. What a
            # provider puts in an error is its own business and this walk is
            # holding a week of student comments when it arrives; the classes name
            # which layer refused (`docs/MISTAKES.md` entry 49) and the run
            # reproduces the rest. The section is named because an operator reading
            # a failed Monday over five hundred sections cannot start without it.
            logger.warning(
                "the summary walk left %s alone for its %s course week after an %s (%s)",
                section_id,
                week_id,
                type(refused).__name__,
                type(refused.__cause__).__name__,
            )
            failed += 1
            continue
        written += len(REPORT_STREAMS)

    logger.info(
        "the summary walk finished: %d summary row(s) stored, %d section-week(s) left for the next "
        "run, in %.1fs",
        written,
        failed,
        time.monotonic() - started,
    )
    return {"written": written, "failed": failed}


def _section_weeks_awaiting_a_summary(
    session: Session, *, closed_by: datetime
) -> list[tuple[UUID, UUID]]:
    """Every section-week whose window has closed and which carries no summary row.

    A list of key pairs rather than of rows, for the reason E3-06's walk gives: a
    commit expires every instance the session holds, and the next section-week's
    work begins after one.
    """
    summarized = select(WeeklySummary.id).where(
        WeeklySummary.section_id == SurveyWindow.section_id,
        WeeklySummary.week_id == SurveyWindow.week_id,
    )
    walked = session.execute(
        select(SurveyWindow.section_id, SurveyWindow.week_id)
        .where(SurveyWindow.closes_at < closed_by, ~summarized.exists())
        .order_by(SurveyWindow.section_id, SurveyWindow.week_id)
    ).all()
    return [(row[0], row[1]) for row in walked]


def _summary_row(
    session: Session,
    *,
    section_id: UUID,
    week_id: UUID,
    token: str,
    gateway: AIGateway | None,
) -> WeeklySummary:
    """One stream's summary for one section-week, as the row that stores it.

    **The provenance is copied off the record and never re-derived from a
    constant**, which is ADR 0148's consequence and the reason an empty stream's
    row can say a model did not write it: `summarize_stream` answers the stated
    empty sentence under `EMPTY_WEEK_PROMPT_VERSION` and the gateway's
    `NOT_A_MODEL` without making a call at all, and a walk reading its prompt
    version out of `app.ai.tasks` would file that row under the prompt the other
    stream rendered.

    **The response count is the week's responses and not the comments that fed the
    call** (SPEC §5.1, ADR 0148). §3.2 makes a comment optional above the rating
    threshold, so nine responses carry three comments in an ordinary week, and a
    count of the comments is a smaller, believable, wrong number under a summary
    that only the instructor could notice and cannot check. Counted before the
    moderation filter for the same reason: a moderator holding two comments has
    not made two students disappear.
    """
    record = _summary_of(
        session,
        section_id=section_id,
        week_id=week_id,
        token=token,
        gateway=gateway,
    )
    return WeeklySummary(
        section_id=section_id,
        week_id=week_id,
        stream=token,
        summary_text=record.summary.summary,
        response_count=record.response_count,
        # Stored as objects rather than as labels, because §5.3's draft check
        # "quietly names any theme not yet addressed (with its comment count)" and
        # E4-10 renders the count beside the label. A list of strings keeps both
        # labels and loses both numbers, and nothing downstream could recover them.
        themes=[
            {"label": theme.label, "comment_count": theme.comment_count}
            for theme in record.summary.themes
        ],
        prompt_version=record.summary.prompt_version,
        model_id=record.summary.model_id,
    )


def _summary_of(
    session: Session,
    *,
    section_id: UUID,
    week_id: UUID,
    token: str,
    gateway: AIGateway | None,
) -> WeeklySummaryRecord:
    """Ask E4-05's task about one stream of one section-week.

    One call per stream and never one for both, which is ADR 0148's second point:
    neither prompt carries the other stream's comments, so a course complaint
    cannot be summarized under §5.1's instructor heading in a way no shape check
    could catch. An empty stream still gets its record and reaches no model.
    """
    return summarize_stream(
        _comments_reaching_the_model(session, section_id=section_id, week_id=week_id, token=token),
        stream=STREAM_ASKED_ABOUT[token],
        response_count=_responses_that_week(session, section_id=section_id, week_id=week_id),
        gateway=gateway,
    )


def _comments_reaching_the_model(
    session: Session, *, section_id: UUID, week_id: UUID, token: str
) -> Sequence[str]:
    """One stream's comments for one section-week, less the ones a moderator holds.

    **The stream comes from `question.stream` and never from a position.**
    `question_set` is versioned (§3.2), so the ordinal that carries the instructor
    comment today is not promised to in the next set — E4-02 added the column to be
    the fact, and E4-03's distribution view already reads it for the same reason.

    **Under-threshold comments are included.** SPEC §4: comments from
    under-threshold weeks "are not discarded — they feed the summary", and §5.1
    generates a summary "even in small-N weeks — there, the summary is the only
    comment signal". So nothing here counts the week before deciding to read it.

    **Moderation-held comments are excluded, and today that filter is vacuous.**
    E6 writes the first `moderation_state` row this system will hold. It is written
    now rather than when the states arrive because a summary is never regenerated
    (the E4 breakdown's decision 2): a comment an instructor excluded which is
    already inside a generated summary stays there for the rest of the term, and a
    filter deferred to the epic that populates the table is a filter discovered
    missing after that has happened.

    **What is *not* excluded here, stated because the asymmetry is deliberate.**
    SPEC §5.2's last bullet routes one class of comment around the moderation
    lifecycle altogether: "Threat/self-harm classifications bypass this flow
    entirely (§6.2) and are never shown to the instructor." Bypassing the flow
    means bypassing the record, so such a comment never acquires a
    `moderation_state` row — and the rule above reads an absent row as published.
    So the class §6.2 keeps furthest from an instructor is the class this gather
    would send to a provider, and a paraphrase of it would sit in a summary nothing
    regenerates. That is the honest shape of what this filter covers and what it
    does not.

    **No predicate for it is written today, and that is a decision rather than an
    oversight.** There is nothing to select on. `ClassificationTask` has exactly one
    member and no writer of a harm verdict exists anywhere in this system, so a
    closed set written now would be a guess at a vocabulary E6 has not designed — a
    set built before the thing it closes over, which reads as a guarantee and is
    not one. The same argument keeps `WeeklySummaryRecord.held_note_type` a string
    for the length of this epic.

    **What is mechanical instead is the precondition.** While that vocabulary has
    one member the gap is unreachable, so the run above is safe for the reason
    stated rather than by luck. `docs/tickets/e4/deferred.md` carries the entry with
    its owner (E6) and its done-when, and
    `tests/integration/test_the_summary_job_feeds_no_moderation_held_comment_to_the_model.py::test_no_harm_classification_task_exists_yet_for_this_filter_to_have_missed`
    is the alarm: it pins that enum's membership as an equality, so a second task
    reds it *before* any classifier writes a verdict. The repair when it reds is
    here, in this function, and never in that test's expected set.

    The order is the answer key's — arbitrary, stable, and carrying nothing. §4
    keeps submission times away from comments, and ordering a prompt by one would
    put the week's arrival sequence in front of a model for no reason.
    """
    return list(
        session.scalars(
            select(Answer.comment_text)
            .join(Response, Response.id == Answer.response_id)
            .join(Question, Question.id == Answer.question_id)
            .where(
                Response.section_id == section_id,
                Response.week_id == week_id,
                Question.kind == QuestionKind.COMMENT,
                Question.stream == token,
                # Two conditions and neither is the other's spare, which is the
                # note E4-03's distribution view carries: `kind` says what was
                # asked and the value says what this row holds. `answer`'s own
                # constraint permits a row filling `comment_text` under a question
                # of another kind, and a read is not the place to trust a write.
                Answer.comment_text.is_not(None),
                func.btrim(Answer.comment_text) != "",
                # The one resolution of "which decision is current", called rather
                # than written again: `app.services.report_comments` owns it
                # (ADR 0145), and E4-07 closed the deferral that had this module
                # carrying a second copy of the ordering and of the default.
                reported_status_of(Answer.id).not_in(HELD_MODERATION_STATES),
            )
            .order_by(Answer.id)
        )
    )


def _responses_that_week(session: Session, *, section_id: UUID, week_id: UUID) -> int:
    """How many students submitted for one section-week — SPEC §5.1's stated count.

    Every submission, with no validity clause: §5.1 has the summary "state the
    response count they draw from", and §3.4's validity rule decides what a
    participation score counts rather than how many people answered. A count
    narrowed here would report a thinner week than the rating distributions on the
    same page do.
    """
    counted = session.scalar(
        select(func.count())
        .select_from(Response)
        .where(Response.section_id == section_id, Response.week_id == week_id)
    )
    return int(counted or 0)
