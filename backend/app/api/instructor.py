"""The instructor's Monday report: the three reads her page is built on (SPEC §5.1).

§13's tree gives the instructor-facing API this module, and §13's closing rule
keeps it thin: a handler here resolves the session, hands the work to a service,
and turns what comes back into an HTTP answer. Every decision — which sections
this session may read, which weeks are published, how a rate divides, what a
comment may say — is in `app.services.reporting`, and the payload's shape is
`app.schemas.report`.

**Three routes and no others.** The report for one section and one course week,
the list of course weeks a reader may page to, and the list of sections she
teaches. E4-11 consumes all three; E4-15 drives them against the running stack.

**The third one is what makes the other two askable** (E4-18, ADR 0156). Both of
them take a section key in the path, and until it shipped nothing a client holds
supplied one: a launch redirect carries the role and the session, and the session
claims carry keys and never sections. So `read_taught_sections` is the menu and
the other two are what a reader opens from it, which is the shape
`app.api.student` already holds — a parameterless read of the reader's own scope,
and then the pages behind it.

**All three carry `app.api.deps.require_instructor` rather than a check of their
own.** That is what makes them findable: a sweep asking the running application
which routes carry that dependency gets this module's whole surface, and a route
that resolved a session for itself would be an instructor route outside it — the
shape `app.api.student` already holds for the student side.

**Authorization is narrow on purpose: the session's own taught sections, nothing
else.** SPEC §4.1's chokepoint rule is that a request resolves only its own
authenticated subject's scope, so a section id in the path is a thing to check
against the teaching grant rather than a thing to trust. Leadership's read of this
same report is E9's drill-down and is refused here by role (see
`require_instructor`); E9 widens `app.services.reporting._readable_section` rather
than adding a route beside these.

**The refusal pair is the confidentiality property the two keyed routes own.** A section
this instructor does not teach and a section that does not exist are answered with
the same status, the same body, and the same code path — because a reader who can
tell the two apart can enumerate which sections the institution has by asking about
them, one id at a time. That is why there is one `SECTION_UNAVAILABLE` sentence
below and not two, why it interpolates nothing it was handed, and why the check
that produces it is a single query in the service rather than an existence test
followed by a scope test.

**A course week with no published report is a different refusal**, and it is safe
to be: it is only ever reached after the section has been established as this
instructor's own, so it says nothing about anything she may not already see. Its
own two cases — a window still taking responses, and a week the section never runs
— share one status and one body, because telling them apart would hand back the
section's calendar a week at a time. A mid-window report is refused rather than
served at all: read twice, the difference between two views of an open week is one
student's submission.

**The section list has no refusal of either kind, and that is not an omission.**
It takes no parameter, so there is nothing in the request to refuse: a caller
cannot ask it about somebody else's section, because a caller cannot ask it about
any section at all. The two states that look like candidates — a person who
teaches nothing, and a session naming nobody — are ordinary and are answered 200
with an empty list, the way the student surface answers a reader who is between
terms. A 404 invented here by analogy with the two routes above would refuse a new
instructor on the day she is hired, and would say something about the institution
to an anonymous caller that the 401 already says nothing about.

**Every answer carries `Cache-Control: no-store`.** A report holds this week's raw
student comments, and a stored copy outlives the reason it was shown — a browser
back button, or the next person on a shared machine after she has signed out. The
list names what she teaches, which outlives it the same way. The student read path
sets the same header for the same reason.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import require_instructor
from app.config import Settings
from app.db import get_session
from app.schemas.report import InstructorReport, PublishedWeeks, TaughtSections
from app.services.reporting import (
    CourseWeekUnavailableError,
    SectionUnavailableError,
    instructor_report,
    published_course_weeks,
    taught_sections,
)
from app.services.session import SessionClaims

router = APIRouter(tags=["instructor"])

# Where the report is read from, and where week navigation reads its weeks. Both
# under `/instructor/sections/{section_id}` because everything this module serves
# is about one section, and each written out in full rather than carried on a
# router prefix so that what a route is registered at is what this file says it is
# — the convention `app.api.student` settled.
REPORT_PATH = "/instructor/sections/{section_id}/report/{course_week}"
PUBLISHED_WEEKS_PATH = "/instructor/sections/{section_id}/published-weeks"

# And where a reader finds out which sections those two may be asked about. The
# same path without the key, written out in full like its two siblings.
SECTIONS_PATH = "/instructor/sections"

# The refusal both halves of the pair get. 404 rather than 403, and one sentence
# rather than two: see this module's docstring. It names nothing — no section, no
# course, no reason — because a body that echoed the id it was handed could not be
# identical to the body for a different id, and the pair is the point.
SECTION_UNAVAILABLE_STATUS = 404
SECTION_UNAVAILABLE = "There is no report here for you to read."

# And the week there is no published report for — whether its window is still open
# or the section never runs it. One sentence for both, for the same no-oracle reason
# the section pair has one: the difference between "not yet" and "never" is a fact
# about the section's calendar. A separate sentence from the refusal above because it
# is a different fact and the instructor can act on it, and because it is reached only
# after the section has already been established as hers.
COURSE_WEEK_UNAVAILABLE = "There is no report for that week of this section."

NO_STORE = "no-store"


@router.get(REPORT_PATH, summary="The Monday report for one of my sections and one course week")
def read_report(
    section_id: UUID,
    course_week: int,
    request: Request,
    response: Response,
    claims: SessionClaims = Depends(require_instructor),
    session: Session = Depends(get_session),
) -> InstructorReport:
    """Answer §5.1's whole report for one section-week, for whoever this session is.

    **The reader comes from the session and from nowhere else.**
    `require_instructor` verified the token and refused anybody who is not an
    instructor; the `person` row it carries was resolved at the door out of the
    verified launch (E1-12), and that is what the teaching grant is asked about. No
    part of this request's own text decides whose sections these are.

    **A section id that is not a uuid is refused before this runs**, by FastAPI's
    own parsing of the path parameter, which is a 422 about the shape of a request
    rather than an answer about a section. ADR 0016 makes every key a uuid, so a
    malformed value is not a section id at all and never reaches the scope query.

    **Synchronous, and FastAPI runs it in a threadpool.** The session is
    synchronous (ADR 0013) and every statement behind this is a blocking read, so a
    handler declared `async` would take them on the event loop and block every other
    request on the process.
    """
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = NO_STORE
    try:
        return instructor_report(
            session,
            person_id=_person_of(claims),
            section_id=section_id,
            course_week=course_week,
            settings=settings,
        )
    except SectionUnavailableError:
        raise _unavailable(SECTION_UNAVAILABLE) from None
    except CourseWeekUnavailableError:
        raise _unavailable(COURSE_WEEK_UNAVAILABLE) from None


@router.get(PUBLISHED_WEEKS_PATH, summary="The course weeks of my section a report may be read for")
def read_published_weeks(
    section_id: UUID,
    request: Request,
    response: Response,
    claims: SessionClaims = Depends(require_instructor),
    session: Session = Depends(get_session),
) -> PublishedWeeks:
    """The closed course weeks of one of this session's own sections.

    **Behind the same scope as the report, because scope is a property of the
    session and the section rather than of one endpoint.** A route that listed any
    section's weeks to anybody who asked would give away the shape of a term's
    calendar for a section the reader has no relationship with, from the endpoint
    nobody thinks of as the report.
    """
    settings: Settings = request.app.state.settings
    response.headers["Cache-Control"] = NO_STORE
    try:
        weeks = published_course_weeks(
            session,
            person_id=_person_of(claims),
            section_id=section_id,
            settings=settings,
        )
    except SectionUnavailableError:
        raise _unavailable(SECTION_UNAVAILABLE) from None
    return PublishedWeeks(published_weeks=weeks)


@router.get(SECTIONS_PATH, summary="The sections I teach, and may read a report for")
def read_taught_sections(
    response: Response,
    claims: SessionClaims = Depends(require_instructor),
    session: Session = Depends(get_session),
) -> TaughtSections:
    """The sections this session's person teaches — the menu the other two routes need.

    **Why it exists.** Both routes above take a section key in the path and nothing
    a client holds supplies one: the launch redirect carries the role and the
    session, and the session claims carry keys and never sections. This answers that
    question the way the student surface answers its own — a parameterless read of
    the reader's own scope (ADR 0156).

    **The reader comes from the session and from nowhere else**, exactly as above,
    and there is nothing else in this request at all: no path parameter, no query
    string, nothing a caller could substitute for whose sections these are.

    **No refusal pair, because there is nothing here to refuse.** A person who
    teaches nothing and a session naming nobody are both answered 200 with an empty
    list — see the module docstring.

    **Synchronous, and FastAPI runs it in a threadpool**, for the reason
    `read_report` above gives: every statement behind this is a blocking read on a
    synchronous session (ADR 0013).
    """
    response.headers["Cache-Control"] = NO_STORE
    return TaughtSections(sections=taught_sections(session, person_id=_person_of(claims)))


def _person_of(claims: SessionClaims) -> UUID | None:
    """The `person` row this session was resolved to, or `None` where it names none.

    A claim in a JWT is JSON, so `person_id` is a string here and a `uuid.UUID` in
    the service (ADR 0016). A value that is not one is a token this deployment did
    not issue in the shape it issues them, and it resolves to nobody rather than to
    a 500 from inside the parse — which the service answers exactly as it answers a
    session naming a person who teaches nothing.
    """
    if claims.person_id is None:
        return None
    try:
        return UUID(claims.person_id)
    except ValueError:
        return None


def _unavailable(detail: str) -> HTTPException:
    """One 404, carrying one of this module's two sentences and nothing else."""
    return HTTPException(status_code=SECTION_UNAVAILABLE_STATUS, detail=detail)
