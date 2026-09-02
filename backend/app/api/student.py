"""The student's own weekly survey (SPEC §13's student routes) — ticket E2-09.

One route today: the read E2-10's form is built on. It is the first
student-visible path this product serves, which is why SPEC §4.1 item 1 —
"students never see … other sections" — has its assertion from this ticket and
not from an earlier one: until now there was nowhere for the rule to bite.

**No path parameters and no query parameters, and that is the interface rather
than a simplification.** The route answers "for me, right now, what is there?"
for the session's own reader. A parameter would be a way to ask this path *about*
a section, and the first section anybody would ask it about is one they are not
in — so the shape of the route is itself part of the confidentiality argument, and
`test_naming_another_section_is_answered_exactly_as_naming_one_that_does_not_exist`
is what holds it to that by requiring the ordinary spellings of such a parameter
to change nothing at all.

**Thin, per SPEC §13.** The assembly is `app.services.survey_read`; what is here
is the session dependency, the database session, and the settings the clock is
read against.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import require_student
from app.config import Settings
from app.db import get_session
from app.schemas.student import StudentSurveyView
from app.services.session import SessionClaims
from app.services.survey_read import survey_for_student

router = APIRouter(prefix="/student", tags=["student"])


@router.get("/survey", summary="This student's enrollments and the survey open for each")
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
