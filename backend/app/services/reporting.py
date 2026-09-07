"""The Monday report: what is written before an instructor opens it, and what she reads.

SPEC §13 names this module for §5.1 — "distributions, trend lines, benchmark
assembly" — and it now holds both halves of that section. E4-06 landed the write
half first: the walk that *generates* §5.1's per-stream AI summaries, once per
section-week, after the window closes and before Monday morning. E4-07 added the
read half beside it — the payload layer that divides the counts E4-03's views
return, derives §2.2's week axis, and assembles what
`app.api.instructor` serves. They are the same section of the spec and share the
same rows, so the name §13 chose is the name used and no second module was made.

**The two halves and where the line between them is.** Everything down to
`_responses_that_week` is the summary walk, and everything from `ComparisonFigure`
onwards is the read. Nothing on the read path writes, and nothing on it commits;
what it reads is E4-03's three views, E4-04's comment service, E4-02's summary
table, and the section's own calendar.

**Where E9's leadership drill-down attaches.** SPEC §5.5 renders this same report
read-only inside a leadership shell, and E4-07 deliberately took the narrowest
possible authorization — the requesting session's own taught sections — so that
E9 has one thing to widen rather than a second payload to build.
`_readable_section` is that one thing: E9 adds a purview-based way of reaching a
section beside the teaching check, and every function below it is untouched.
Forking `instructor_report` instead would give the institution two answers to
"what does this report say", which is how a suppression rule comes to hold on one
surface and not the other.

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
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, PrivateAttr
from sqlalchemy import column, func, or_, select, table
from sqlalchemy.orm import Session

from app.ai.contracts import CommentStream, WeeklySummaryRecord
from app.ai.gateway import AIGateway, AIGatewayError
from app.ai.tasks import summarize_stream
from app.config import Settings
from app.models.identity import Enrollment
from app.models.org import Course, Prefix, Section
from app.models.report import WeeklySummary
from app.models.survey import REPORT_STREAMS, Answer, Question, QuestionKind, Response
from app.models.term import SurveyWindow, Term, Week
from app.services import clock
from app.services.authz import section_scoped_assignees, teaching_instructor_assigned
from app.services.identity import person_for_user
from app.services.report_comments import (
    ReportComment,
    released_comments,
    reported_status_of,
    visible_comments,
)
from app.services.section_codes import week_of_the_term

if TYPE_CHECKING:  # pragma: no cover - imported for annotations only
    # `app.schemas.report` imports `ComparisonFigure` from this module, because
    # item 7's token has to be private to the module that holds the helper. So the
    # dependency between the two runs schema → service at import time, and the one
    # place this module needs the schema back — `_payload`, which builds the
    # response — imports it inside the function. See that function's docstring.
    from app.schemas.report import CommentView, InstructorReport, SummaryView

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


# ---------------------------------------------------------------------------
# The read side: SPEC §4.1 item 7's chokepoint, and the payload built around it.
# ---------------------------------------------------------------------------

# E4-03's three views, declared as the relations they are — the shape
# `app.services.report_comments` declares `report_comment` in, and for the same
# reason: a view is not a model (SPEC §13), and the declaration doubles as the
# list of what this module is able to ask each of them.
#
# Every column named here is a count or a statistic. ADR 0147 keeps every
# division, every denominator and every label out of SQL and in the functions
# below, so that the rule for a zero denominator is written once where a reviewer
# can read it.
RESPONSE_COUNTS_VIEW = table(
    "report_response_counts",
    column("section_id"),
    column("week_id"),
    column("responses"),
    column("valid_responses"),
    schema="public",
)

RATING_DISTRIBUTION_VIEW = table(
    "report_rating_distribution",
    column("section_id"),
    column("week_id"),
    column("stream"),
    column("rating"),
    column("responses"),
    schema="public",
)

WORKLOAD_VIEW = table(
    "report_workload",
    column("section_id"),
    column("week_id"),
    column("workload_mean"),
    column("workload_median"),
    schema="public",
)

# SPEC §3.2's Likert scale, written out because the histogram draws a bar per
# value whether or not anybody chose it — and because a week nobody answered has
# to arrive as five zeros rather than as an empty object, which is the difference
# between a chart with no bars and a chart of a quiet week.
LIKERT_VALUES = (1, 2, 3, 4, 5)

# What a suppressed comparison says about itself. One word for one reason, because
# E4 has exactly one: no comparison set exists until E5 builds them, so every
# figure over one is below the minimum by construction.
BELOW_MINIMUM = "below-minimum"

# **The token SPEC §4.1 item 7's chokepoint is made of.** A module-level object
# with no name outside this file: importing `ComparisonFigure` gets a caller the
# type and never this, and the constructor refuses anything else. So the only way
# a comparison value exists anywhere in this system is `comparison_after_suppression`
# below — not by convention, and not because a reviewer will notice.
#
# E4's breakdown decision 4 asks for exactly that, and `docs/MISTAKES.md` entry 22
# is why it is structural rather than a rule: a closed-set guard is defeated one
# level out, and "every caller remembers to call the helper" is a guard with a
# door beside it.
_COMPARISON_TOKEN = object()


class ComparisonFigure(BaseModel):
    """One §5.1 comparison figure, or the statement that it is suppressed.

    SPEC §4.1 item 7: "No figure computed from a comparison set is shown below the
    benchmark minimum — a mean, a median, or any other statistic, not only a drawn
    line." This type is where that rule is enforced for the whole product, because
    it is the only type the report schema's `comparison` member accepts.

    **`figure` is `None` whenever `suppressed` is true, and the helper is what
    guarantees it.** A value carrying both would be a suppressed figure on the
    wire, which is the exact thing item 7 forbids.

    **Two checks, at two boundaries, because the constructor alone is not one.**
    E4-07's security round found the reason: the token guards `__init__`, and
    pydantic offers two documented ways of producing a model instance that never
    calls it. `model_construct` skips validation and initialisation both, and
    `model_copy(update=...)` rewrites the fields of a value the helper had already
    suppressed. Both were demonstrated ending in a serialized payload carrying a
    figure §5.1 means to suppress.

      - **The constructor's token** is the front door and still closes it.
      - **The seal below is the wire**, checked by the report schema's own
        validation of its `comparison` member — see `refuse_an_unsealed_comparison`.

    §4.1 item 7 is a rule about what is *shown*, so the boundary that has to hold
    it is the one the payload crosses, and a guard standing only in `__init__` is
    walked past by every entry point that does not call `__init__`.

    **E5 fills this, and it fills it through the same helper.** Until then every
    report carries a suppressed value with no number in it, which is what gives
    the invariant something to stand on before there is any data to suppress.
    """

    model_config = ConfigDict(frozen=True)

    suppressed: bool
    reason: str | None = None
    figure: float | None = None

    # **The seal: the field values this instance was built with, recorded at the
    # moment the token was accepted.** A private attribute, so it is not a field,
    # is never serialized, and cannot be handed in by a caller.
    #
    # It binds the *values* rather than merely recording that a token was seen,
    # and that is the whole of why it survives both side doors. `model_construct`
    # sets no private attribute at all, so an instance it produces carries `None`
    # and matches nothing. `model_copy(update=...)` copies the private attribute
    # from the value it is copying and then rewrites the fields, so the seal is
    # over the *old* values and disagrees with the new ones — which a seal
    # recording only "a token was seen" would not.
    _sealed_over: tuple[Any, ...] | None = PrivateAttr(default=None)

    def __init__(self, token: object = None, **values: Any) -> None:
        """Refuse any construction that does not come from this module, and seal the rest.

        The token is positional and defaulted so that the ordinary mistake — a
        caller elsewhere writing `ComparisonFigure(suppressed=False, figure=4.2)`
        because the fields are right there in the schema — is refused rather than
        silently accepted with a `None` token.

        `object.__setattr__` because the model is frozen: the seal is written once,
        here, after validation has settled what the fields are, and there is no
        supported way for anything else to write it.
        """
        if token is not _COMPARISON_TOKEN:
            raise TypeError(
                "A comparison figure can only be built by "
                "`app.services.reporting.comparison_after_suppression`, which holds the token this "
                "constructor demands. SPEC §4.1 item 7 suppresses every figure computed from a "
                "comparison set below the configured benchmark minimums, and that suppression is "
                "this constructor rather than a rule callers are asked to remember."
            )
        super().__init__(**values)
        object.__setattr__(self, "_sealed_over", _the_seal_over(self))


def _the_seal_over(figure: ComparisonFigure) -> tuple[Any, ...]:
    """What a sealed comparison's fields are, in one order, for the two sites that compare them.

    Written once rather than spelled at the constructor and again at the check: two
    tuples that fell out of step would make every legitimate value fail the wire
    boundary, or — the direction that matters — make every smuggled one pass it.
    Derived from `model_fields` so a field added to the type is inside the seal by
    existing, which is the difference between a seal and a list somebody has to
    remember to extend (`docs/MISTAKES.md` entry 22).
    """
    return tuple(getattr(figure, name) for name in sorted(type(figure).model_fields))


def refuse_an_unsealed_comparison(figure: ComparisonFigure) -> None:
    """Refuse a comparison value the suppression helper did not produce — the wire boundary.

    Called by `app.schemas.report.InstructorReport`'s own validation of its
    `comparison` member, which is the boundary a smuggled instance cannot skip:
    whatever built the value, it becomes part of a report only by being validated
    into that model, and a field validator runs there even for a value that is
    already an instance of the field's type.

    **What it compares, and why that and not the token.** The seal is over the
    field values as they stood when the token was accepted. So a value produced by
    `comparison_after_suppression` matches; one produced by `model_construct`
    carries no seal; and one produced by `model_copy(update=...)` carries a seal
    over the values it had *before* the update. A check that only asked "was a
    token ever seen" would pass the third, because `model_copy` copies private
    attributes along with everything else — which is the closed-set defeat one
    level out that `docs/MISTAKES.md` entry 22 records, and it was found here by a
    security review rather than by this module's own reasoning.

    **It raises rather than quietly emptying the member**, and that is deliberate.
    Nothing in this system can reach here except code that built a comparison value
    outside the one helper, which is a defect in a confidentiality path rather than
    a state to render — so it fails loudly, at the boundary, before anything is
    serialized. `ValueError` because a pydantic validator turns it into a
    `ValidationError` on the field, which is what the payload boundary answers with.
    """
    if figure._sealed_over != _the_seal_over(figure):
        raise ValueError(
            "This comparison figure was not produced by "
            "`app.services.reporting.comparison_after_suppression`: it carries no seal, or a seal "
            "over field values it no longer has. SPEC §4.1 item 7 suppresses every figure computed "
            "from a comparison set below the configured benchmark minimums, and the suppression is "
            "decided once, by that helper, over both minimums. A value built past it — with "
            "`model_construct`, or by copying a suppressed one with the figure written back in — is "
            "refused here rather than shown."
        )


def comparison_after_suppression(
    figure: float | None, *, sections: int, respondents: int
) -> ComparisonFigure:
    """SPEC §5.1's benchmark minimums, applied to one figure — the only way in.

    Both minimums, and each on its own. §11 question 1 names the pair —
    `benchmark_min_sections_default` and `benchmark_min_respondents_default` — and
    E4's breakdown decision 4 says why writing both out matters: a helper built
    against one of two thresholds passes a mean over three sections and four
    respondents, which is a figure §5.1 means to suppress. The two are different
    units as well as different numbers, a count of sections and a count of people,
    which is `docs/MISTAKES.md` entry 50's shape.

    **At the minimum is enough; below it is not.** §5.1 suppresses a figure
    "computed from fewer than the configured number of sections", so the configured
    number itself passes and `n - 1` does not.

    **`figure` may be `None`, and that is E4's own case.** No comparison set exists
    until E5 builds them, so the report calls this with no figure over no sections
    and no respondents and gets back the suppressed value the payload carries. E5
    calls the same function with real numbers, and gets suppression or passage from
    the same two comparisons.

    The minimums are read from `Settings` here rather than taken as parameters, the
    way `visible_comments` reads the n-threshold: the promise §4.1 item 7 makes is
    about the *configured* numbers, and a caller that could supply them could
    supply different ones.
    """
    settings = Settings()
    if (
        sections < settings.benchmark_min_sections_default
        or respondents < settings.benchmark_min_respondents_default
    ):
        return ComparisonFigure(
            _COMPARISON_TOKEN, suppressed=True, reason=BELOW_MINIMUM, figure=None
        )
    return ComparisonFigure(_COMPARISON_TOKEN, suppressed=False, reason=None, figure=figure)


class SectionUnavailableError(Exception):
    """This session may not read that section — or there is no such section.

    **One exception for both, deliberately, and it carries nothing.** E4-07's
    refusal pair is "a section she does not teach refuses exactly as one that does
    not exist", so the two have to be indistinguishable in status *and* in body. An
    exception that named which case it was would be an existence oracle waiting for
    the first caller who logs it or renders it, and one carrying the section id
    would put that id in a refusal that must not echo what it was handed.
    """


class CourseWeekUnavailableError(Exception):
    """There is no report for that course week of this section — one refusal for two states.

    **A week whose survey window has not closed, and a week the section never runs,
    raise this same exception from the same line, and that is the point.** E4-07's
    security round found the first of those served: `instructor_report` answered any
    course week with a `survey_window` row, so an instructor could poll a week that
    was still taking responses and read the *difference* between two views of it —
    which is one student's submission, a count that moved by one and a comment that
    was not there an hour ago. SPEC §4 randomizes comment order so that position
    says nothing; it cannot make a comment that has just appeared look like one that
    was always there, and in an under-threshold week the set of people who could
    have written it is small.

    Telling the two states apart would be its own disclosure, one level down: the
    difference between "not yet" and "never" is a fact about the section's calendar,
    so a caller could walk the course weeks and learn how long the section runs and
    where in the term it sits. Hence one exception, one sentence, one code path —
    the rule the section pair already follows, applied to weeks.

    Distinct from `SectionUnavailableError` and safe to be: this is only ever raised
    after the section has been established as this instructor's own, so it says
    nothing about anything she may not already see.
    """


@dataclass(frozen=True, slots=True)
class _SectionWeek:
    """One week of one section, on both of SPEC §2.2's axes, with its window.

    Frozen, and holding plain values rather than rows, for the reason
    `app.services.survey_windows._Calendars` gives: a `Week` instance held across
    the assembly is one the session can expire, and the next attribute read would
    be a lazy refresh nobody can see.
    """

    week_id: UUID
    term_week: int
    course_week: int
    opens_at: datetime
    closes_at: datetime


def instructor_report(
    session: Session,
    *,
    person_id: UUID | None,
    section_id: UUID,
    course_week: int,
    settings: Settings,
) -> "InstructorReport":
    """The Monday report for one of this person's own sections and one course week.

    **Authorization is the first thing that happens and it is driven from the
    session's own person.** SPEC §4.1's chokepoint rule is that a request resolves
    only its own authenticated subject's scope, so `section_id` is a thing to check
    rather than a thing to trust; see `_readable_section`.

    **Being published is a precondition, and the asked week is selected out of the
    published set rather than out of the calendar.** SPEC §3.1 puts the report after
    the window closes and this ticket's own context is "one published course week";
    serving a week still taking responses lets an instructor read the same report
    twice and subtract, which is one student's submission each time
    (`docs/MISTAKES.md` entry 51, and `CourseWeekUnavailableError` carries the
    argument). Selecting from `published` rather than testing against it afterwards
    is what makes an open week and a week the section never runs leave this function
    by the same line, with nothing to tell them apart.

    Raises `SectionUnavailableError` and `CourseWeekUnavailableError`; the router
    is what turns each into an HTTP answer.
    """
    section = _readable_section(session, person_id=person_id, section_id=section_id)
    now = clock.now(session, settings=settings)
    published = [week for week in _section_weeks(session, section) if week.closes_at < now]

    asked = next((week for week in published if week.course_week == course_week), None)
    if asked is None:
        raise CourseWeekUnavailableError(
            "This section has no published report for that course week."
        )
    return _payload(session, section=section, week=asked, published=published, settings=settings)


def published_course_weeks(
    session: Session, *, person_id: UUID | None, section_id: UUID, settings: Settings
) -> list[int]:
    """The course weeks of this person's own section whose survey window has closed.

    E4's breakdown decision 6: "a published week is a course week whose survey
    window has closed, per the clock service … Nothing is stored to make a week
    published." So this is a comparison between a stored instant and the effective
    clock (ADR 0109) and never a flag, which is what lets a developer move the
    clock and watch a week appear.

    **It is the same derivation the payload's own `week.published_weeks` makes**,
    through the same two functions, so the list a reader pages across and the list
    inside the report she is reading cannot disagree.
    """
    section = _readable_section(session, person_id=person_id, section_id=section_id)
    now = clock.now(session, settings=settings)
    return [week.course_week for week in _section_weeks(session, section) if week.closes_at < now]


def _readable_section(session: Session, *, person_id: UUID | None, section_id: UUID) -> Section:
    """The section this person teaches, or one refusal for everything else.

    **One question, asked of the teaching grant, and both halves of the refusal
    pair fail it the same way.** A section outside this person's teaching set has
    no `INSTRUCTOR` `role_assignment` row for her; a section that does not exist
    has no row for anybody. Neither reaches the `section` read below, so there is
    no code path, no timing difference and no body that tells the two apart.

    **The grant is asked through `app.services.authz`**, which is SPEC §13's one
    authorization chokepoint and the only module that reads `assignment_scope`. A
    join written here would be a second answer to "whose sections are these", and
    the first thing that diverges is a widening nobody can see.

    **A session carrying no person reads nothing rather than everything.** A
    `person_id` is absent for somebody the people graph has no row for, which is
    the ordinary state of a student (ADR 0028) — and a scope query with its
    subject left empty is the failure this refuses instead of.
    """
    if person_id is None or not teaching_instructor_assigned(
        session, person_id=person_id, section_id=section_id
    ):
        raise SectionUnavailableError
    section = session.get(Section, section_id)
    if section is None:  # pragma: no cover - the assignment's foreign key holds this
        raise SectionUnavailableError
    return section


def _section_weeks(session: Session, section: Section) -> list[_SectionWeek]:
    """Every week this section has a survey window for, on both of §2.2's axes.

    **The stored windows, not the derived ones.** `survey_windows.windows_for_section`
    answers what the calendar *implies*; `survey_window` holds what was written, and
    "the window has closed" is a statement about the row a student answered against
    — the same instants `generate_missing_summaries` above compares. A read that
    derived its own instants would answer a different question the day a calendar
    is corrected under windows already written.

    **The course week is arithmetic over the term axis and is not re-derived from
    the section code.** `week_of_the_term` is this codebase's one reading of §2.2's
    two axes, and a second copy of it here is how a course-level page and an
    aggregate page come to disagree about the same section (`docs/MISTAKES.md`
    entry 19). Course weeks count from 1, which is the inclusive `+ 1` below.
    """
    term = session.get(Term, section.term_id)
    if term is None:  # pragma: no cover - `section.term_id` is a non-null foreign key
        raise SectionUnavailableError
    first_term_week = week_of_the_term(
        1, section_start=section.start_date, term_start=term.start_date
    )
    rows = session.execute(
        select(
            SurveyWindow.week_id,
            Week.number,
            SurveyWindow.opens_at,
            SurveyWindow.closes_at,
        )
        .join(Week, Week.id == SurveyWindow.week_id)
        .where(SurveyWindow.section_id == section.id)
        .order_by(Week.number)
    ).all()
    return [
        _SectionWeek(
            week_id=week_id,
            term_week=number,
            course_week=number - first_term_week + 1,
            opens_at=opens_at,
            closes_at=closes_at,
        )
        for week_id, number, opens_at, closes_at in rows
    ]


def _payload(
    session: Session,
    *,
    section: Section,
    week: _SectionWeek,
    published: list[_SectionWeek],
    settings: Settings,
) -> "InstructorReport":
    """Assemble one report out of the views, the comment service and the summary table.

    **The one import this module makes inside a function, and why.**
    `app.schemas.report` types its `comparison` member with `ComparisonFigure`,
    which has to live here because the token that guards it is private to this
    module — so the schema imports the service. This is the one place the service
    needs the schema back, and importing it here rather than at module scope is
    what keeps that from being a cycle. The alternative was a second payload type
    for the router to translate, which is two shapes for one contract to drift
    between.

    **Nothing is widened at the assembly layer.** The comments are exactly what
    `visible_comments` and `released_comments` answer with, in the same three
    fields; the summary is what the row holds, and an absent row is an absent
    member rather than an empty string. §4.1 item 6's spirit is that a suppression
    decided one layer down is not undone by the layer that renders it.
    """
    from app.schemas import report as schema

    responses, valid_responses = _response_counts(
        session, section_id=section.id, week_id=week.week_id
    )
    enrolled = _enrolled_students(session, section=section, week=week, settings=settings)
    ratings = _rating_counts(
        session,
        section_id=section.id,
        week_ids=[week.week_id, *(other.week_id for other in published)],
    )
    summaries = _stored_summaries(session, section_id=section.id, week_id=week.week_id)
    released = _released(session, section=section, week=week, published=published)

    streams = {
        token: schema.StreamReport(
            trend=[
                schema.TrendPoint(
                    course_week=other.course_week,
                    mean=_mean_of(ratings.get((other.week_id, token), {})),
                )
                for other in published
            ],
            distribution={
                str(value): ratings.get((week.week_id, token), {}).get(value, 0)
                for value in LIKERT_VALUES
            },
            summary=summaries.get(token),
            comments=_comment_views(
                # **The same `Settings` object the `small_n` member below prints
                # from.** The threshold an instructor is shown and the threshold
                # that decided what she is shown are one number, read once, so the
                # label cannot describe a gate that applied a different one.
                visible_comments(
                    session,
                    section_id=section.id,
                    week_id=week.week_id,
                    stream=token,
                    settings=settings,
                )
            ),
        )
        for token in REPORT_STREAMS
    }

    workload_mean, workload_median = _workload(session, section_id=section.id, week_id=week.week_id)
    return schema.InstructorReport(
        section=schema.SectionView(
            code=section.lms_section_code,
            course_label=_course_label(session, section),
            length_weeks=section.length_weeks,
        ),
        week=schema.WeekView(
            course_week=week.course_week,
            term_week=week.term_week,
            published_weeks=[other.course_week for other in published],
        ),
        rates=schema.RatesView(
            response_rate=None if enrolled == 0 else responses / enrolled,
            validity_rate=None if responses == 0 else valid_responses / responses,
            responses=responses,
            enrolled=enrolled,
            valid_responses=valid_responses,
        ),
        streams=schema.StreamsView(
            instructor=streams["INSTRUCTOR"],
            course=streams["COURSE"],
        ),
        workload=schema.WorkloadView(mean=workload_mean, median=workload_median),
        # E4 computes no comparison set, so the figure is asked for over nothing —
        # and it is asked for through the same helper E5 will use, because there is
        # no other way to build this member (SPEC §4.1 item 7).
        comparison=comparison_after_suppression(None, sections=0, respondents=0),
        small_n=schema.SmallNView(
            suppressed=responses < settings.n_threshold_default,
            threshold=settings.n_threshold_default,
        ),
        released_from_earlier_weeks=_comment_views(released),
    )


def _comment_views(comments: Sequence[ReportComment]) -> list["CommentView"]:
    """E4-04's comments, one field for one field and nothing added.

    Written as one function rather than three comprehensions so there is one place
    a fourth field could ever be introduced, and so the review that forbids one has
    one line to read. SPEC §4 keeps display order random and timestamps away from
    comments; an index or a submitted-at added for a frontend's convenience would
    hand back the order the suppression exists to remove.
    """
    from app.schemas.report import CommentView

    return [
        CommentView(text=comment.text, status=comment.status, stream=comment.stream)
        for comment in comments
    ]


def _released(
    session: Session,
    *,
    section: Section,
    week: _SectionWeek,
    published: list[_SectionWeek],
) -> list[ReportComment]:
    """The from-earlier-weeks release, in the latest published week's report only.

    ADR 0152: "Released comments appear in the latest published week's report under
    a from-earlier-weeks heading, with no week attribution anywhere." Carrying the
    same batch in every week's report would put it beside six different weeks of
    data, and a reader paging back through the term would meet it once per page —
    which is the week attribution ADR 0153 removed, arriving through the navigation
    instead of through a field.

    Both streams, because §5.1 heads two comment groups and a batch may hold
    comments from either; the stream each comment belongs to travels on the comment,
    as it does everywhere else.
    """
    if not published or week.course_week != max(other.course_week for other in published):
        return []
    return [
        comment
        for token in REPORT_STREAMS
        for comment in released_comments(
            session, section_id=section.id, term_id=section.term_id, stream=token
        )
    ]


def _response_counts(session: Session, *, section_id: UUID, week_id: UUID) -> tuple[int, int]:
    """This week's responses and valid responses, or two zeros where the view holds no row.

    ADR 0147 gives a row only to the section-weeks somebody answered, so absence is
    the ordinary state of a quiet week and this is where it becomes a number. Zero
    responses is a true statement about such a week; what is *not* true of it is a
    validity rate, and that absence is decided by the caller rather than here.
    """
    row = session.execute(
        select(RESPONSE_COUNTS_VIEW.c.responses, RESPONSE_COUNTS_VIEW.c.valid_responses).where(
            RESPONSE_COUNTS_VIEW.c.section_id == section_id,
            RESPONSE_COUNTS_VIEW.c.week_id == week_id,
        )
    ).one_or_none()
    return (0, 0) if row is None else (int(row[0]), int(row[1]))


def _rating_counts(
    session: Session, *, section_id: UUID, week_ids: Sequence[UUID]
) -> dict[tuple[UUID, str], dict[int, int]]:
    """Every rating count this report needs, by week and stream, in one statement.

    One query for the requested week's histogram *and* for every published week's
    trend point, because they are the same rows read at two grains — ADR 0147
    rejected a fourth view over them for the same reason (`docs/MISTAKES.md`
    entry 13). Zero-filling happens at the caller, in one loop, so a stored zero
    and a week with no row never arrive looking the same.
    """
    counted: dict[tuple[UUID, str], dict[int, int]] = {}
    for week_id, stream, rating, responses in session.execute(
        select(
            RATING_DISTRIBUTION_VIEW.c.week_id,
            RATING_DISTRIBUTION_VIEW.c.stream,
            RATING_DISTRIBUTION_VIEW.c.rating,
            RATING_DISTRIBUTION_VIEW.c.responses,
        ).where(
            RATING_DISTRIBUTION_VIEW.c.section_id == section_id,
            RATING_DISTRIBUTION_VIEW.c.week_id.in_(list(week_ids)),
        )
    ):
        counted.setdefault((week_id, stream), {})[int(rating)] = int(responses)
    return counted


def _mean_of(counts: dict[int, int]) -> float | None:
    """The mean of the ratings behind one week of one stream, or `None` for none of them.

    ADR 0147's re-homed criterion 3, as arithmetic: "the weekly mean is the mean of
    that week's submitted ratings; an absent response contributes nothing to the
    mean (it costs the response rate, not the average)". The denominator is the
    ratings that were given and never the week's response count — a response that
    left this stream's rating blank is in `report_response_counts` and in no bar
    here, which is exactly what E4-03 asserts one layer down.

    `None` rather than zero for a week nobody rated: zero is outside SPEC §3.2's
    1-to-5 scale and would plot below every real point.
    """
    total = sum(counts.values())
    if total == 0:
        return None
    return sum(rating * responses for rating, responses in counts.items()) / total


def _workload(
    session: Session, *, section_id: UUID, week_id: UUID
) -> tuple[float | None, float | None]:
    """This week's workload mean and median, or two absences where nobody answered."""
    row = session.execute(
        select(WORKLOAD_VIEW.c.workload_mean, WORKLOAD_VIEW.c.workload_median).where(
            WORKLOAD_VIEW.c.section_id == section_id,
            WORKLOAD_VIEW.c.week_id == week_id,
        )
    ).one_or_none()
    if row is None:
        return (None, None)
    return (
        None if row[0] is None else float(row[0]),
        None if row[1] is None else float(row[1]),
    )


def _stored_summaries(
    session: Session, *, section_id: UUID, week_id: UUID
) -> dict[str, "SummaryView"]:
    """This section-week's generated summaries, by stream, exactly as the row holds them.

    An absent row is an absent key, which the caller renders as the schema's
    explicit absent state. `summary = row.text if row else ""` is the shape this
    exists to refuse: a blank summary above a comment group reads to an instructor
    as a model that had nothing to say about her week, rather than as a job that
    has not run yet.
    """
    from app.schemas.report import SummaryView

    return {
        stream: SummaryView(text=summary_text, response_count=response_count)
        for stream, summary_text, response_count in session.execute(
            select(
                WeeklySummary.stream,
                WeeklySummary.summary_text,
                WeeklySummary.response_count,
            ).where(WeeklySummary.section_id == section_id, WeeklySummary.week_id == week_id)
        )
    }


def _enrolled_students(
    session: Session, *, section: Section, week: _SectionWeek, settings: Settings
) -> int:
    """How many students were enrolled in this section while this week's window was open.

    **The denominator of §5.1's response rate, and it is a question about the week
    rather than about today.** ADR 0147 keeps it out of SQL precisely so that §3.4's
    enrolment-window rules are read in one language: a student who left in week
    three is in week two's denominator and not week five's, and a count of the
    enrolments that are live *now* would answer both with the same wrong number.

    **The test is overlap, and the reason is arithmetic.** An enrolment counts if it
    had begun by the day the window closed and had not ended before the day it
    opened. A narrower rule — enrolled on the day it closed, say — would put a
    student who answered on the Monday and dropped on the Tuesday in the numerator
    and not the denominator, and a response rate above 1 is a report nobody can
    read. The days are the institution's own, which is the zone every window's wall
    clock is stated in (SPEC §3.1).

    **Staff are not students** (§3.4: "completed items ÷ total items across the
    *student's* elapsed weeks"). A roster container lists the instructor too and
    E1-11 writes an `enrollment` row for her, so without this an instructor is one
    of the people her own response rate is divided by. The test is an assignment
    scoped to this section, asked in that direction because a student holds no
    assignment at all (ADR 0028) — `app.services.grading._live_enrollments` answers
    the same question about today and applies the same rule.
    """
    zone = ZoneInfo(settings.institution_timezone)
    opened_on = week.opens_at.astimezone(zone).date()
    closed_on = week.closes_at.astimezone(zone).date()
    enrolled = set(
        session.scalars(
            select(Enrollment.user_id).where(
                Enrollment.section_id == section.id,
                Enrollment.started_on <= closed_on,
                or_(Enrollment.ended_on.is_(None), Enrollment.ended_on >= opened_on),
            )
        )
    )
    staff = section_scoped_assignees(session, section_id=section.id)
    if not staff:
        return len(enrolled)
    # The hop from a member to their person is a definer call each (ADR 0024,
    # ADR 0094), so it is skipped entirely for a section nobody has entered in the
    # people graph — which is the shape `_live_enrollments` takes and why.
    return sum(1 for user_id in enrolled if person_for_user(session, user_id) not in staff)


def _course_label(session: Session, section: Section) -> str:
    """How this course names itself on the report — FIX-01 item 2's governed form.

    "MATH 140 E1FF — College Algebra, Fall 2026": the prefix code, the LMS number,
    the §2.2 section code, an em dash, the LMS title, a comma and the term's name.
    The owner's ruling of 2026-09-03 settled that order for the student's own page,
    and the instructor reads the same course under the same name.

    **This is a second copy of `app.services.survey_read._course_label`'s
    composition, and it is one deliberately for now.** That function is private to a
    module E4-07 was told not to touch, and promoting it is a change to a shared
    signature — which this ticket proposes in its pull request rather than making.
    Two copies of a format string is `docs/MISTAKES.md` entry 13's shape and the
    proposal is what closes it; until then, the two are edited together or the
    student's page and her instructor's report name the same course differently.
    """
    term = session.get(Term, section.term_id)
    course = session.get(Course, section.course_id)
    if term is None or course is None:  # pragma: no cover - both are non-null foreign keys
        raise SectionUnavailableError
    prefix = session.get(Prefix, course.prefix_id)
    if prefix is None:  # pragma: no cover - a non-null foreign key
        raise SectionUnavailableError
    return (
        f"{prefix.code} {course.lms_number} {section.lms_section_code} — "
        f"{course.lms_title}, {term.name}"
    )
