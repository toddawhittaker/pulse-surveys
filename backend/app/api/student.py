"""The student's own weekly survey: the read a form is built on, and the write it posts.

§13's tree gives the student-facing API this module, and §13's closing rule keeps
it thin: a handler here resolves the session, hands the work to a service, and
turns what comes back into an HTTP answer. Every decision — who may read or
submit, into which week, whether the values hold, what a comment's verdict means —
is in `app.services.survey_read` and `app.services.submissions`, and every
sentence a student reads is in `app.copy`.

**Two routes and no others.** `GET /student/survey` (E2-09) answers the form's
whole question, and `POST /student/submissions` (E2-08) is the weekly submission.
The form itself is E2-10's.

**Both carry `app.api.deps.require_student` rather than a check of their own**,
which is what puts every route this module serves inside SPEC §4.1 item 1's sweep
the day it is written: that sweep builds its inventory of student-visible routes
by asking the running application which routes carry that dependency. The write
carries `csrf_verified_student`, which is `require_student` plus ADR 0089's
double-submit check, so it is in the same inventory.

**The read takes no path parameters and no query parameters, and that is the
interface rather than a simplification.** It answers "for me, right now, what is
there?" for the session's own reader. A parameter would be a way to ask this path
*about* a section, and the first section anybody would ask it about is one they are
not in — so the shape of the route is itself part of the confidentiality argument,
and
`test_naming_another_section_is_answered_exactly_as_naming_one_that_does_not_exist`
is what holds it to that by requiring the ordinary spellings of such a parameter to
change nothing at all.

**What the router owns on the write is the protocol, and only that.** A refusal
reaches it as a `RefusalReason`, which is a copy key; this module is what says a
closed window is a 409 and an off-step workload a 422, because a status code is a
statement about HTTP rather than about the survey. The mapping is a table rather
than a chain of `if`s so that a reason with no status is a `KeyError` at the one
place that would show it, not a silent 500.

**Four statuses are worth their own sentence.**

  - **403 when a cookie-borne submission carries no valid double-submit token** —
    ADR 0089's check, which this route is the first mutating endpoint to consume,
    and which `app.api.deps.csrf_verified_student` applies. A Bearer-authenticated
    request is exempt by construction, because no cross-site page can make a
    browser attach an `Authorization` header.
  - **404 for a section the student is not enrolled in**, with the same body a
    section id that names nothing gets. SPEC §4.1 item 1, asserted from E2 because
    this is the first student-visible surface: a 403 here, or a 404 whose body
    differed, would answer "does this section exist" for any signed-in student, one
    request at a time, over every id in the institution.
  - **409 for a closed window**, which is *not* the same shape. The section is the
    student's own and nothing about it is secret; a student who missed the week is
    owed an honest reason rather than the pretence that their own course is not
    there (SPEC §3.1: "Missed weeks cannot be back-filled").
  - **503 with `Retry-After: 60` when the classifier cannot be asked** — ADR 0114,
    for the provider failures ADR 0056 keeps outside §3.3's floor. Sixty seconds
    because it is a length of time a student will actually wait, and because the
    header is the difference between a refusal somebody can act on and one that
    reads as the tool being broken.

**The enqueue happens after the commit, and it cannot fail the request.** A
submission accepted on §3.3's floor still owes a model's verdict, so a sweep is
published for it — with retries off, with the result backend out of it, and inside
a broad `except` (`docs/MISTAKES.md` entry 41). All three of those live in
`app.services.validity.enqueue_reclassification`, which is also what the hourly beat
entry runs, so the request path and the schedule cannot come apart.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import csrf_verified_student, require_student
from app.config import Settings
from app.copy.submit import COPY
from app.db import get_session
from app.schemas.student import StudentSurveyView
from app.schemas.survey import SubmissionAccepted, SubmissionRequest
from app.services.session import SessionClaims
from app.services.submissions import (
    RefusalReason,
    SubmissionBouncedError,
    SubmissionRefusedError,
    store_submission,
)
from app.services.survey_read import survey_for_student
from app.services.validity import ClassifierUnavailableError, enqueue_reclassification

router = APIRouter(tags=["student"])

# Where the form reads from, and where a submission is posted. Both under
# `/student` because the whole of this module's surface is the student's own, and
# each named for the thing rather than for the act, which the method already says.
# The paths are written out in full rather than carried on a router prefix, so that
# what a route is registered at is what this file says it is.
SURVEY_PATH = "/student/survey"
SUBMIT_PATH = "/student/submissions"

# SPEC §3.3's bounce: a client error, because the submission is well formed and
# does not satisfy the gate. 422 rather than 400 for the same reason every other
# value refusal here is a 422 — the request was understood and its content was not
# acceptable.
BOUNCED_STATUS = 422

# ADR 0114's honest retryable refusal, and how long to wait. Not a setting: there
# is one right answer for a provider blip, and a knob for it would only ever be
# turned up until the number stopped meaning anything.
CLASSIFIER_DOWN_STATUS = 503
RETRY_AFTER_SECONDS = "60"

# Which status each refusal answers with. See the module docstring for the three
# that are decisions rather than bookkeeping.
STATUS_OF_REASON: dict[RefusalReason, int] = {
    RefusalReason.SECTION_UNAVAILABLE: 404,
    RefusalReason.WINDOW_CLOSED: 409,
    RefusalReason.ALREADY_SUBMITTED: 409,
    RefusalReason.COMMENT_ALREADY_JUDGED: 409,
    RefusalReason.ANSWER_REQUIRED: 422,
    RefusalReason.VALUE_OUT_OF_RANGE: 422,
    RefusalReason.VALUE_OFF_STEP: 422,
    RefusalReason.ANSWER_NOT_RECOGNISED: 422,
}


@router.get(SURVEY_PATH, summary="This student's enrollments and the survey open for each")
def student_survey(
    request: Request,
    claims: SessionClaims = Depends(require_student),
    session: Session = Depends(get_session),
) -> StudentSurveyView:
    """Answer the form's whole question for whoever this session belongs to.

    **The reader comes from the session and from nowhere else.**
    `require_student` verified the token and refused anybody who is not a student;
    the `user` row it carries was resolved at the door out of the verified launch
    (E1-12), so no part of this request's own text reaches the query.

    **A session carrying no `user` row reads nothing rather than everything.** A
    student landing is reached through an enrollment (ADR 0028), so a `STUDENT`
    session without one is a token from before that resolution existed; the honest
    answer is that this reader is enrolled in nothing, and the dangerous one would
    be a query with its scoping left empty.

    **Synchronous, and FastAPI runs it in a threadpool.** The session is
    synchronous (ADR 0013) and every statement here is a blocking read, so a
    handler declared `async` would take them on the event loop and block every
    other request on the process.
    """
    settings: Settings = request.app.state.settings
    if claims.user_id is None:
        return StudentSurveyView(sections=[])
    return survey_for_student(session, user_id=UUID(claims.user_id), settings=settings)


@router.post(SUBMIT_PATH, summary="Submit this week's survey for one of my sections")
def submit_weekly_survey(
    request: Request,
    submission: SubmissionRequest,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_student),
    session: Session = Depends(get_session),
) -> SubmissionAccepted:
    """Store one student's answers to one section's open weekly survey.

    A plain `def` rather than `async def`, so FastAPI runs it in a threadpool: the
    session is synchronous (ADR 0013) and the classifier is a real HTTP call with a
    four-second budget, either of which would block every other request on the
    process if it were taken on the event loop.

    **The student is the session's, never the request's.** `response.user_id` is
    written from `SessionClaims.user_id`, which E1-12 sealed into the token at the
    door; a submission cannot name whose week it is, so there is nothing here for a
    caller to file somebody else's participation under.

    **A session carrying no `user_id` is answered exactly as an unreachable section
    is.** That is the web door's session — it resolves a person and no LMS subject —
    and §2.1 gives a student the launch door alone, so such a session has no
    enrollment to check and no row to write. Answering it with the same 404 keeps
    this route from reporting which door a session came through, which is the same
    discipline the enrollment check itself is written under.
    """
    settings: Settings = request.app.state.settings
    try:
        # A claim in a JWT is JSON, so `user_id` is a string here and a `uuid.UUID`
        # in the schema (ADR 0016). A value that is not one is a token this
        # deployment did not issue in the shape it issues them, and it gets the
        # same answer an absent one does rather than a 500 from inside the parse.
        student_id = UUID(claims.user_id or "")
    except ValueError:
        raise _refusal(RefusalReason.SECTION_UNAVAILABLE) from None

    try:
        stored = store_submission(
            session,
            student_id=student_id,
            submission=submission,
            settings=settings,
        )
    except SubmissionRefusedError as refused:
        raise _refusal(refused.reason) from refused
    except SubmissionBouncedError as bounced:
        raise HTTPException(
            status_code=BOUNCED_STATUS,
            detail={"verdict": bounced.verdict.value, "message": COPY[bounced.copy_key].text},
        ) from bounced
    except ClassifierUnavailableError as unavailable:
        raise HTTPException(
            status_code=CLASSIFIER_DOWN_STATUS,
            detail=COPY["submit.classifier_down"].text,
            headers={"Retry-After": RETRY_AFTER_SECONDS},
        ) from unavailable

    session.commit()
    if stored.floored:
        enqueue_reclassification()
    response.headers["Cache-Control"] = "no-store"
    return SubmissionAccepted(
        response_id=stored.response_id,
        is_valid=stored.is_valid,
        first_submitted_at=stored.first_submitted_at,
        last_submitted_at=stored.last_submitted_at,
    )


def _refusal(reason: RefusalReason) -> HTTPException:
    """One refusal, carrying the status this module gives the reason and the registry's words.

    The sentence is looked up rather than written, so every string this route serves
    is one E2-11's inventory can find; the key *is* the reason's value, so there is
    no second mapping for the two to disagree in.
    """
    return HTTPException(status_code=STATUS_OF_REASON[reason], detail=COPY[reason.value].text)
