"""The one route a student writes through: the weekly survey submission (SPEC §3.2, §3.3).

§13's tree gives the student-facing API this module, and §13's closing rule keeps
it thin: this file parses the request once (ADR 0062), asks
`app.services.submissions` to store it, and turns whatever comes back into an HTTP
answer. Every decision — who may submit, into which week, whether the values hold,
what a comment's verdict means — is in the service, and every sentence a student
reads is in `app.copy`.

**One POST route and no others.** The read path a form fetches is E2-09's and the
form itself is E2-10's; this is the write.

**What the router owns is the protocol, and only that.** A refusal reaches it as a
`RefusalReason`, which is a copy key; this module is what says a closed window is a
409 and an off-step workload a 422, because a status code is a statement about HTTP
rather than about the survey. The mapping is a table rather than a chain of `if`s so
that a reason with no status is a `KeyError` at the one place that would show it,
not a silent 500.

**Four statuses are worth their own sentence.**

  - **403 when a cookie-borne submission carries no valid double-submit token** —
    ADR 0089's check, which this route is the first mutating endpoint to consume,
    and which `app.api.deps.csrf_verified_student` applies. A Bearer-authenticated
    request is exempt by construction, because no cross-site page can make a
    browser attach an `Authorization` header.
  - **404 for a section the student is not enrolled in**, with the same body a
    section id that names nothing gets. SPEC §4.1 item 1, asserted from E2 because
    this is the first student-visible path: a 403 here, or a 404 whose body differed,
    would answer "does this section exist" for any signed-in student, one request at
    a time, over every id in the institution.
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

from app.api.deps import csrf_verified_student
from app.config import Settings
from app.copy.submit import COPY
from app.db import get_session
from app.schemas.survey import SubmissionAccepted, SubmissionRequest
from app.services.session import SessionClaims
from app.services.submissions import (
    RefusalReason,
    SubmissionBouncedError,
    SubmissionRefusedError,
    store_submission,
)
from app.services.validity import ClassifierUnavailableError, enqueue_reclassification

router = APIRouter(tags=["student"])

# Where a submission is posted. Under `/student` because the whole of this
# module's surface is the student's own, and named for the thing being created
# rather than for the act, which is what the method already says.
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
