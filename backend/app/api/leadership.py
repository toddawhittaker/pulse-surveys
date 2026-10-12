"""Leadership's routes: the named comparison sets (SPEC §5.1) and moderation review (SPEC §5.2).

§13's tree gives the leadership-facing API this module, and §13's closing rule
keeps it thin: a handler here resolves the session, hands the work to
`app.services.comparison_sets`, and turns what comes back into an HTTP answer.
Every decision — who may change which set, what a set may be, how wide one is —
is in that service, and the payload's shape is `app.schemas.comparison_sets`.

**Eight named-set routes.** The institution's sets, one set, the choices a
set is defined out of, and the three writes; plus the preview, which is how a
definer sees what a set reaches before anything renders a figure over it. E5-09
consumes those seven. The eighth (E9-05) is a set's figures for one leader:
the only one scoped to the reader's purview, through `leadership_scope`, and the
only one serving a figure (E9-11 draws it).

**Three moderation review routes** (E6-05), after the sets: the
reader's review queue, a decision on one queued comment, and the exclusion log.

**The response loop's routes** (ADR 0194): the response policy (read and
switch), the responses owed, and the five on-behalf doors. Like the review
routes, each is scoped to the reader's own leadership grant
(`app.services.authz.lead_review_courses`), with one widening (ADR 0206): the
exclusion log and the policy read also answer an assistant dean, a dean or a
vice president over their purview, taken from `leadership_scope`. Each section
below says what its routes refuse.

**The drill-down** (SPEC §5.5, ADR 0206), last: one section's Monday report,
read-only, for a section inside the reader's purview.

**`/leadership/comparison-sets/options` is declared before
`/leadership/comparison-sets/{set_id}`, and that is load-bearing.** FastAPI
matches in declaration order, so with the keyed route first this path is read as
a set id that is not a uuid and the whole definition form answers a validation
error. The two are written in that order here and
`tests/integration/test_the_named_set_options_offer_only_the_valid_choices.py`
holds them in it.

**Every route carries one of `app.api.deps`' two leadership dependencies rather
than a check of its own.** That is what makes them findable: a sweep asking the
running application which routes carry `require_leadership` gets this module's
whole surface, and a route that resolved a session for itself would be a
leadership route outside every such walk — the shape `app.api.student` and
`app.api.instructor` already hold. The reads carry `require_leadership` and the
three writes carry `csrf_verified_leadership`, which is the same gate plus ADR
0089's double-submit check.

**Scope is asymmetric, and the asymmetry is the decision** (ADR 0173). Every
leadership session reads every set in the institution — §5.1's set-definition
surface is one list, and two leaders looking at different halves of it would
define the same cohort twice. Only the leader whose `person` row defined a set
may edit or delete it, which is what `editable` on the list says and what the
403 below answers. Purview over the supervision graph is E9's.

**Four refusals and three layers, which is why they are four sentences.** The
dependency answers two (E7-08, ADR 0196): a request carrying no session it can
verify — absent, malformed, expired or signed with another key — gets one 401
with a `Bearer` challenge, and a real, verified session in another role gets a
403 with an `insufficient_scope` challenge, so the pages can say "not part of
your role" rather than that the session ended. Past the gate, a set id nothing
defined is a 404, and another leader's set on a write is a 403 with no
challenge. The 404 comes before the 403 on a write, deliberately: a set
that is not there is not there for anybody, and answering 403 for an unknown id
would tell a caller that a set exists and belongs to somebody else — the
enumeration `app.api.instructor`'s own refusal pair exists to prevent, in the one
place here where it has a foothold.

**The five write refusals are translations rather than checks.** A length of
at least one week, §8's levels and §5.1's exact level match are all held by
Postgres (E5-01, ADR 0164, E5-14); the service attempts the write and maps the constraint that
fired to one sentence. So a 422 from here carries a sentence out of
`app.copy.leadership_sets` rather than a list of field errors, and a body that
carried field errors would mean the wire model had refused the value before the
database saw it. **One refusal is the wire model's by design:** a set name that is
empty once its spaces are stripped is refused by `SetWrite` itself (E5-14's
ruling), so its 422 carries the framework's standard field errors and no sentence
from the copy registry — the one 422 here whose body is a list of field errors.

**The preview answers two counts and nothing else.** SPEC §4.1 item 7 suppresses
statistics computed over a comparison set below the configured minimums; a count
of member courses and a count of resolved sections say how wide a cohort is and
nothing about what anybody in it answered, which is what makes them safe at
definition time. A name, a section code or a mean here would be a figure reaching
a reader outside E4-07's suppression chokepoint.

**Every answer carries `Cache-Control: no-store`.** A leadership answer sitting
in a shared cache is a set definition, and the list of every cohort in the
institution, served to whoever asks next on the same machine. The student and
instructor read paths set the same header for the same reason.

**No `audit_log` row is written by any of this** (ADR 0174). What is recorded is
on the set's own row — the creator and `created_at` on a create, `updated_at` on
an edit — and `docs/tickets/e5/deferred.md` carries what a delete leaves behind,
which is nothing.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.ai.gateway import AIGatewayError
from app.api.deps import (
    csrf_verified_leadership,
    leadership_scope,
    person_of,
    require_leadership,
)
from app.api.instructor import assistant_busy, assistant_unusable
from app.config import Settings
from app.copy.instructor_report import SECTION_UNAVAILABLE, WEEK_UNAVAILABLE
from app.copy.leadership_moderation import (
    NO_REVIEW_GRANT,
    NOT_IN_QUEUE,
    REASON_BLANK,
    REASON_TOO_LONG,
)
from app.copy.leadership_rollup import TERM_UNAVAILABLE
from app.copy.leadership_sets import NOT_THE_SETS_DEFINER, SET_UNAVAILABLE
from app.copy.response_loop import NO_POLICY_TO_SET, ON_BEHALF_UNAVAILABLE
from app.db import get_session
from app.schemas.comparison_sets import (
    NamedSetSeries,
    SetDetail,
    SetList,
    SetOptions,
    SetPreview,
    SetWrite,
)
from app.schemas.moderation import ExclusionLog, LeadDecision, LogRow, QueueItem, ReviewQueue
from app.schemas.report import (
    DraftCheckRequest,
    DraftCheckView,
    InstructorReport,
    ResponseDraftView,
)
from app.schemas.response_loop import (
    OnBehalfWeek,
    OwedWeek,
    PolicyOverview,
    PolicyWrite,
    ResponseWrite,
    WeekResponseView,
)
from app.services.authz import ActorScope
from app.services.comparison_sets import (
    NotTheSetsDefinerError,
    SetUnavailableError,
    TermUnavailableError,
    WriteRefusedError,
    create_set,
    definition_options,
    delete_set,
    edit_set,
    listed_sets,
    named_set_figures,
    preview_of,
    read_set,
)
from app.services.moderation import (
    CommentNotInQueueError,
    DecisionAction,
    DecisionNotAllowedError,
    NoReviewGrantError,
    ReasonBlankError,
    ReasonTooLongError,
    decide_as_leader,
    exclusion_log,
    review_queue,
)
from app.services.reporting import (
    AssistantBusyError,
    CourseWeekUnavailableError,
    SectionUnavailableError,
    UnusableAnswerError,
    leadership_report,
    one_assistant_call_at_a_time,
)
from app.services.response_loop import (
    NoPolicyToSetError,
    OnBehalfUnavailableError,
    edit_on_behalf,
    on_behalf_check,
    on_behalf_draft,
    on_behalf_week,
    policy_overview,
    publish_on_behalf,
    responses_owed,
    set_policy,
)
from app.services.session import SessionClaims

router = APIRouter(tags=["leadership"])

# Where the institution's sets are listed and where one is defined. Written out
# in full rather than carried on a router prefix, so that what a route is
# registered at is what this file says it is — the convention `app.api.student`
# settled and `app.api.instructor` follows.
SETS_PATH = "/leadership/comparison-sets"

# The choices a set is defined out of. **Declared before the keyed paths below**
# — see the module docstring — and written out in full like its siblings.
OPTIONS_PATH = f"{SETS_PATH}/options"

# One set, and what it reaches.
SET_PATH = f"{SETS_PATH}/{{set_id}}"
PREVIEW_PATH = f"{SET_PATH}/preview"
# One set's figures for the reader, in the term named by the `term_id` query.
SET_SERIES_PATH = f"{SET_PATH}/series"

# The statuses the three keyed refusals answer with. 404 for an id nothing
# defined and 403 for another leader's set: the two are different facts and a
# leader may read every set, so saying "this one is not yours" discloses nothing
# the list does not already show.
SET_UNAVAILABLE_STATUS = 404
NOT_THE_SETS_DEFINER_STATUS = 403
# A term id no term carries, on the series route. Terms are no secret.
TERM_UNAVAILABLE_STATUS = 404

CREATED = 201
NO_CONTENT = 204

NO_STORE = "no-store"


@router.get(SETS_PATH, summary="Every comparison set this institution has defined")
def read_sets(
    response: Response,
    claims: SessionClaims = Depends(require_leadership),
    session: Session = Depends(get_session),
) -> SetList:
    """The institution's sets, in name order, each marked editable or not.

    **Institution-wide rather than this session's own** (ADR 0173). The reader
    still comes from the session and from nowhere else: `editable` is decided
    against the `person` row this session was resolved to at the door, so no part
    of this request's own text decides which sets it may change.

    **Synchronous, and FastAPI runs it in a threadpool**, for the reason
    `app.api.instructor` gives: the session is synchronous (ADR 0013) and every
    statement behind this blocks, so an `async` handler would take them on the
    event loop.
    """
    response.headers["Cache-Control"] = NO_STORE
    return SetList(sets=listed_sets(session, person_id=person_of(claims)))


@router.post(SETS_PATH, status_code=CREATED, summary="Define a comparison set")
def define_set(
    write: SetWrite,
    request: Request,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_leadership),
    session: Session = Depends(get_session),
) -> SetDetail:
    """Define a set for whoever this session is, or translate what the database refused.

    **The definer comes from the session and never from the body**, and it is
    what every later edit and delete of this set is scoped by.
    """
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = NO_STORE
    try:
        return create_set(session, write=write, person_id=person_of(claims), settings=settings)
    except NotTheSetsDefinerError:
        raise _not_the_definer() from None
    except WriteRefusedError as refused:
        raise _refused(refused) from None


@router.get(OPTIONS_PATH, summary="The lengths, levels and courses a set may be defined out of")
def read_options(
    response: Response,
    claims: SessionClaims = Depends(require_leadership),
    session: Session = Depends(get_session),
) -> SetOptions:
    """The closed choices the definition form offers. Declared before `{set_id}`.

    It takes no parameter, so there is nothing in the request to refuse and no
    refusal here beyond the role gate. The courses it lists are every course this
    institution runs, because the form is where a new cohort is built.
    """
    response.headers["Cache-Control"] = NO_STORE
    return definition_options(session)


@router.get(SET_PATH, summary="One comparison set, whoever defined it")
def read_one_set(
    set_id: UUID,
    response: Response,
    claims: SessionClaims = Depends(require_leadership),
    session: Session = Depends(get_session),
) -> SetDetail:
    """One set and its membership.

    **A set id that is not a uuid is refused before this runs**, by FastAPI's own
    parsing of the path parameter — which is an answer about the shape of a
    request rather than about a set. ADR 0016 makes every key a uuid, so a
    malformed value is not a set id at all and never reaches the lookup.
    """
    response.headers["Cache-Control"] = NO_STORE
    try:
        return read_set(session, set_id=set_id, person_id=person_of(claims))
    except SetUnavailableError:
        raise _unavailable() from None


@router.put(SET_PATH, summary="Replace the definition of a set I defined")
def replace_set(
    set_id: UUID,
    write: SetWrite,
    request: Request,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_leadership),
    session: Session = Depends(get_session),
) -> SetDetail:
    """Replace a set's whole definition, for the leader who defined it.

    The three refusals in order: an id nothing defined is a 404, another leader's
    set is a 403, and a definition the database will not store is one of the five
    translated sentences.
    """
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = NO_STORE
    try:
        return edit_set(
            session,
            set_id=set_id,
            write=write,
            person_id=person_of(claims),
            settings=settings,
        )
    except SetUnavailableError:
        raise _unavailable() from None
    except NotTheSetsDefinerError:
        raise _not_the_definer() from None
    except WriteRefusedError as refused:
        raise _refused(refused) from None


@router.delete(SET_PATH, status_code=NO_CONTENT, summary="Delete a set I defined")
def remove_set(
    set_id: UUID,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_leadership),
    session: Session = Depends(get_session),
) -> None:
    """Delete a set, taking its membership rows and nothing else (ADR 0164).

    204 and no body, because there is nothing left to describe. A course named by
    the set is untouched and stays undeletable while any set names it, which is
    the opposite direction of the same rule.
    """
    response.headers["Cache-Control"] = NO_STORE
    try:
        delete_set(session, set_id=set_id, person_id=person_of(claims))
    except SetUnavailableError:
        raise _unavailable() from None
    except NotTheSetsDefinerError:
        raise _not_the_definer() from None


@router.get(SET_SERIES_PATH, summary="A comparison set's figures over my purview, one term")
def read_set_series(
    set_id: UUID,
    term_id: UUID,
    request: Request,
    response: Response,
    scope: ActorScope = Depends(leadership_scope),
    session: Session = Depends(get_session),
) -> NamedSetSeries:
    """One set's figures for the session's own reader, in the term asked for (E9-05).

    **The reader's scope comes from `leadership_scope` and from nothing in the
    request** (ADR 0199): a query string carrying another person's id is not
    read, so it is answered with the session's own scope. The figures are
    computed over the set's sections inside that purview, per start cohort, and
    a set wholly outside it answers exactly what a thin set inside it does.

    Two refusals past the gate, in order: a set id nothing defined is the 404
    every keyed route here answers, and a term id no term carries is a 404 of its
    own. A `term_id` that is absent or not a uuid is FastAPI's own 422.
    """
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = NO_STORE
    try:
        return named_set_figures(
            session, set_id=set_id, scope=scope, term_id=term_id, settings=settings
        )
    except SetUnavailableError:
        raise _unavailable() from None
    except TermUnavailableError:
        raise HTTPException(
            status_code=TERM_UNAVAILABLE_STATUS, detail=TERM_UNAVAILABLE.text
        ) from None


@router.get(PREVIEW_PATH, summary="How many courses and sections a set reaches")
def read_preview(
    set_id: UUID,
    response: Response,
    claims: SessionClaims = Depends(require_leadership),
    session: Session = Depends(get_session),
) -> SetPreview:
    """Two counts and nothing else — see the module docstring on what that costs and why.

    Answered for every set, not only for this session's own: a count is what
    makes an institution-wide list usable, and it says nothing about anybody.
    """
    response.headers["Cache-Control"] = NO_STORE
    try:
        return preview_of(session, set_id=set_id)
    except SetUnavailableError:
        raise _unavailable() from None


def _unavailable() -> HTTPException:
    """The 404 for a set id nothing defined, carrying one sentence and nothing it was handed."""
    return HTTPException(status_code=SET_UNAVAILABLE_STATUS, detail=SET_UNAVAILABLE)


def _not_the_definer() -> HTTPException:
    """The 403 for another leader's set on a write."""
    return HTTPException(status_code=NOT_THE_SETS_DEFINER_STATUS, detail=NOT_THE_SETS_DEFINER)


def _refused(refused: WriteRefusedError) -> HTTPException:
    """One translated constraint refusal, with the status that rule is answered under."""
    return HTTPException(status_code=refused.status_code, detail=refused.detail)


# ---------------------------------------------------------------------------
# Moderation review (E6-05, SPEC §5.2).
#
# Every route reads the reader's own leadership grant, and refuses three ways
# past the role gate: a reader whose grant covers no course is a 403
# (`NO_REVIEW_GRANT`); a decision on anything not in the reader's queue now is
# one 404 (`NOT_IN_QUEUE`), the same body for a sibling lead's comment, a decided
# one, a Care-class one and an id nothing holds, so nothing says the comment
# exists; and a stated reason that is blank or too long is a 422.
# ---------------------------------------------------------------------------

MODERATION_PATH = "/leadership/moderation"
QUEUE_PATH = f"{MODERATION_PATH}/queue"
DECISIONS_PATH = f"{MODERATION_PATH}/comments/{{answer_id}}/decisions"
LOG_PATH = f"{MODERATION_PATH}/log"

NO_REVIEW_GRANT_STATUS = 403
NOT_IN_QUEUE_STATUS = 404
REASON_REFUSED_STATUS = 422

# What a leader's two actions mean to the decision service. Typed so that the
# door cannot be handed an undo, which a leader does not have.
LEAD_ACTIONS: dict[str, Literal[DecisionAction.EXCLUDE, DecisionAction.KEEP]] = {
    "exclude": DecisionAction.EXCLUDE,
    "keep": DecisionAction.KEEP,
}


@router.get(QUEUE_PATH, summary="The comments awaiting my review")
def read_review_queue(
    response: Response,
    claims: SessionClaims = Depends(require_leadership),
    session: Session = Depends(get_session),
) -> ReviewQueue:
    """The reader's review queue: text and section, no week, no time, no count, a fresh order."""
    response.headers["Cache-Control"] = NO_STORE
    try:
        queued = review_queue(session, person_id=person_of(claims))
    except NoReviewGrantError:
        raise _no_review_grant() from None
    return ReviewQueue(
        items=[
            QueueItem(answer_id=item.answer_id, text=item.text, section_label=item.section_label)
            for item in queued
        ]
    )


@router.post(
    DECISIONS_PATH,
    status_code=NO_CONTENT,
    summary="Exclude or keep one comment in my review queue",
)
def decide_on_queued_comment(
    answer_id: UUID,
    decision: LeadDecision,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_leadership),
    session: Session = Depends(get_session),
) -> None:
    """One decision on one queued comment, written under the role whose grant covers it.

    204 and no body: the comment leaves the queue, and the queue and the log
    are the two reads that show what happened.
    """
    response.headers["Cache-Control"] = NO_STORE
    try:
        decide_as_leader(
            session,
            person_id=person_of(claims),
            answer_id=answer_id,
            action=LEAD_ACTIONS[decision.action],
            reason=decision.reason,
        )
    except NoReviewGrantError:
        raise _no_review_grant() from None
    except (CommentNotInQueueError, DecisionNotAllowedError):
        raise HTTPException(status_code=NOT_IN_QUEUE_STATUS, detail=NOT_IN_QUEUE.text) from None
    except ReasonBlankError:
        raise HTTPException(status_code=REASON_REFUSED_STATUS, detail=REASON_BLANK.text) from None
    except ReasonTooLongError:
        raise HTTPException(
            status_code=REASON_REFUSED_STATUS, detail=REASON_TOO_LONG.text
        ) from None


@router.get(LOG_PATH, summary="The exclusion log inside my own grant or purview")
def read_exclusion_log(
    request: Request,
    response: Response,
    scope: ActorScope = Depends(leadership_scope),
    session: Session = Depends(get_session),
) -> ExclusionLog:
    """Every exclusion, keep and undo a person made inside the reader's reach, newest first.

    A lead's or chair's own grant, and an assistant dean's, dean's or vice
    president's purview (ADR 0206); the scope is the session's own.
    """
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = NO_STORE
    try:
        logged = exclusion_log(session, scope=scope, settings=settings)
    except NoReviewGrantError:
        raise _no_review_grant() from None
    return ExclusionLog(
        rows=[
            LogRow(
                section_label=row.section_label,
                decision=row.decision,
                decided_as=row.decided_as.value,
                flagged=row.flagged,
                reason=row.reason,
                decided_on=row.decided_on,
                excerpt=row.excerpt,
                is_undo=row.is_undo,
            )
            for row in logged
        ]
    )


def _no_review_grant() -> HTTPException:
    """The 403 for a leader whose own grant puts no course under review."""
    return HTTPException(status_code=NO_REVIEW_GRANT_STATUS, detail=NO_REVIEW_GRANT.text)


# ---------------------------------------------------------------------------
# The response loop (E7-03, SPEC §5.3, ADR 0194).
#
# Every route reads the reader's own grant (`lead_review_courses`) and nothing
# wider. The policy switch refuses a prefix where the reader sets no course with
# one 404 (`NO_POLICY_TO_SET`), the same for a prefix that does not exist. Every
# on-behalf door refuses with one 404 (`ON_BEHALF_UNAVAILABLE`), the same bytes
# for a sibling lead's section in every state of its week, a section the reader
# teaches or taught, a week not open on behalf, an answered week and a key
# nothing holds. The draft and the check answer the instructor's one 502 for any
# answer they may not hand on, and its one 429 to a second request from a person
# with one in flight (`app.api.instructor`, where both are defined).
# ---------------------------------------------------------------------------

POLICY_PATH = "/leadership/response-policy"
POLICY_PREFIX_PATH = f"{POLICY_PATH}/{{prefix_id}}"
OWED_PATH = "/leadership/responses-owed"
ON_BEHALF_PATH = "/leadership/sections/{section_id}/weeks/{course_week}/on-behalf"
ON_BEHALF_DRAFT_PATH = f"{ON_BEHALF_PATH}/response-draft"
ON_BEHALF_CHECK_PATH = f"{ON_BEHALF_PATH}/draft-check"
ON_BEHALF_RESPONSE_PATH = f"{ON_BEHALF_PATH}/response"

NO_POLICY_TO_SET_STATUS = 404
ON_BEHALF_UNAVAILABLE_STATUS = 404


@router.get(POLICY_PATH, summary="The response policy of every course I set or read it for")
def read_response_policy(
    response: Response,
    scope: ActorScope = Depends(leadership_scope),
    session: Session = Depends(get_session),
) -> PolicyOverview:
    """The courses the reader sets the policy for, and those they read: a chair's led
    courses, and every course of an assistant dean's, dean's or vice president's purview."""
    response.headers["Cache-Control"] = NO_STORE
    return policy_overview(session, scope=scope)


@router.put(POLICY_PREFIX_PATH, summary="Switch the response policy for my courses in one prefix")
def switch_response_policy(
    prefix_id: UUID,
    write: PolicyWrite,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_leadership),
    scope: ActorScope = Depends(leadership_scope),
    session: Session = Depends(get_session),
) -> PolicyOverview:
    """One row per course of the prefix the reader sets the policy for; answered with the new read.

    `claims` is the CSRF-checked gate; the reader is the same session's `scope`.
    """
    response.headers["Cache-Control"] = NO_STORE
    try:
        return set_policy(session, scope=scope, prefix_id=prefix_id, mode=write.mode)
    except NoPolicyToSetError:
        raise HTTPException(
            status_code=NO_POLICY_TO_SET_STATUS, detail=NO_POLICY_TO_SET.text
        ) from None


@router.get(OWED_PATH, summary="The weeks of my courses that are owed a response now")
def read_responses_owed(
    request: Request,
    response: Response,
    claims: SessionClaims = Depends(require_leadership),
    session: Session = Depends(get_session),
) -> list[OwedWeek]:
    """Section and course week, and whether on behalf is open: no name, no time."""
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = NO_STORE
    return responses_owed(session, person_id=person_of(claims), settings=settings)


@router.get(ON_BEHALF_PATH, summary="One owed week's summaries and ratings, before I respond")
def read_on_behalf(
    section_id: UUID,
    course_week: int,
    request: Request,
    response: Response,
    claims: SessionClaims = Depends(require_leadership),
    session: Session = Depends(get_session),
) -> OnBehalfWeek:
    """Stored summaries, response count and rating distributions; never a comment."""
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = NO_STORE
    try:
        return on_behalf_week(
            session,
            person_id=person_of(claims),
            section_id=section_id,
            course_week=course_week,
            settings=settings,
        )
    except OnBehalfUnavailableError:
        raise _on_behalf_unavailable() from None


@router.post(ON_BEHALF_DRAFT_PATH, summary="An AI draft of a response on the instructor's behalf")
def draft_on_behalf(
    section_id: UUID,
    course_week: int,
    request: Request,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_leadership),
    session: Session = Depends(get_session),
) -> ResponseDraftView:
    """The instructor's draft task over the on-behalf gather; the gate before any model call."""
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = NO_STORE
    person_id = person_of(claims)
    try:
        with one_assistant_call_at_a_time(person_id):
            text = on_behalf_draft(
                session,
                person_id=person_id,
                section_id=section_id,
                course_week=course_week,
                settings=settings,
            )
    except AssistantBusyError:
        raise assistant_busy() from None
    except OnBehalfUnavailableError:
        raise _on_behalf_unavailable() from None
    except (UnusableAnswerError, AIGatewayError):
        raise assistant_unusable() from None
    return ResponseDraftView(text=text)


@router.post(ON_BEHALF_CHECK_PATH, summary="The week's themes an on-behalf draft does not address")
def check_on_behalf(
    section_id: UUID,
    course_week: int,
    check: DraftCheckRequest,
    request: Request,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_leadership),
    session: Session = Depends(get_session),
) -> DraftCheckView:
    """The instructor's check task over the on-behalf gather; the gate before any model call."""
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = NO_STORE
    person_id = person_of(claims)
    try:
        with one_assistant_call_at_a_time(person_id):
            themes = on_behalf_check(
                session,
                person_id=person_id,
                section_id=section_id,
                course_week=course_week,
                draft=check.draft,
                settings=settings,
            )
    except AssistantBusyError:
        raise assistant_busy() from None
    except OnBehalfUnavailableError:
        raise _on_behalf_unavailable() from None
    except (UnusableAnswerError, AIGatewayError):
        raise assistant_unusable() from None
    return DraftCheckView(unaddressed=themes)


@router.post(
    ON_BEHALF_RESPONSE_PATH,
    status_code=CREATED,
    summary="Publish a response on the instructor's behalf",
)
def publish_on_behalf_response(
    section_id: UUID,
    course_week: int,
    write: ResponseWrite,
    request: Request,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_leadership),
    session: Session = Depends(get_session),
) -> WeekResponseView:
    """Under the reader's own name and the role they answer for the course under."""
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = NO_STORE
    try:
        return publish_on_behalf(
            session,
            person_id=person_of(claims),
            section_id=section_id,
            course_week=course_week,
            write=write,
            settings=settings,
        )
    except OnBehalfUnavailableError:
        raise _on_behalf_unavailable() from None


@router.put(
    ON_BEHALF_RESPONSE_PATH, summary="Edit a response I published on the instructor's behalf"
)
def edit_on_behalf_response(
    section_id: UUID,
    course_week: int,
    write: ResponseWrite,
    request: Request,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_leadership),
    session: Session = Depends(get_session),
) -> WeekResponseView:
    """By the person who first published it, while they still answer for the course."""
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = NO_STORE
    try:
        return edit_on_behalf(
            session,
            person_id=person_of(claims),
            section_id=section_id,
            course_week=course_week,
            write=write,
            settings=settings,
        )
    except OnBehalfUnavailableError:
        raise _on_behalf_unavailable() from None


def _on_behalf_unavailable() -> HTTPException:
    """The one 404 every on-behalf door answers, whatever the cause, naming nothing."""
    return HTTPException(
        status_code=ON_BEHALF_UNAVAILABLE_STATUS, detail=ON_BEHALF_UNAVAILABLE.text
    )


# ---------------------------------------------------------------------------
# The drill-down (SPEC §5.5, ADR 0206).
#
# One section's Monday report, wholesale and read-only, for a section inside the
# reader's purview. A section outside it and a section that does not exist get
# the instructor report's one 404 and sentence; a week with no published report
# gets its other one. The route carries no write, and the report it serves
# carries no action.
# ---------------------------------------------------------------------------

DRILL_DOWN_PATH = "/leadership/sections/{section_id}/weeks/{course_week}/report"
DRILL_DOWN_UNAVAILABLE_STATUS = 404


@router.get(DRILL_DOWN_PATH, summary="One section's Monday report, read-only, inside my purview")
def read_drill_down(
    section_id: UUID,
    course_week: int,
    request: Request,
    response: Response,
    scope: ActorScope = Depends(leadership_scope),
    session: Session = Depends(get_session),
) -> InstructorReport:
    """The instructor's report of one section-week, as a leader reads it (SPEC §5.5).

    The scope comes from `leadership_scope` and from nothing in the request
    (ADR 0199). Comments show under the section's own per-stream threshold and
    release batches, exactly as its instructor reads them; no comment is marked
    as the reader's decision, and the benchmark lines are sealed against the
    reader (SPEC §5.1).
    """
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = NO_STORE
    try:
        return leadership_report(
            session,
            scope=scope,
            section_id=section_id,
            course_week=course_week,
            settings=settings,
        )
    except SectionUnavailableError:
        raise HTTPException(
            status_code=DRILL_DOWN_UNAVAILABLE_STATUS, detail=SECTION_UNAVAILABLE.text
        ) from None
    except CourseWeekUnavailableError:
        raise HTTPException(
            status_code=DRILL_DOWN_UNAVAILABLE_STATUS, detail=WEEK_UNAVAILABLE.text
        ) from None
