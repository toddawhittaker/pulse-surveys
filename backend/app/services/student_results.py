"""A student's week results (SPEC §5.4): the read behind the student results route.

**`student_week_results`** reaches the section through the student's live
enrollment, as the survey read does. While the week is `awaiting` it serves the
course label and the state and nothing about the week; otherwise the streams,
the workload median and, on the latest published week while nothing is held,
the release group (ADR 0197).

The hold itself is decided in `services/response_loop.py`
(`response_loop._state_and_response` and `response_loop._week_clocks`), which
this module calls by module attribute rather than importing the names.

The comments come through `report_comments.student_comments` and
`student_released_comments`, the only names this module takes from that module
(the student import sweep holds it to them).
"""

from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import Settings
from app.models.grades import GradeSyncOutcome, latest_grade_sync
from app.models.survey import REPORT_STREAMS
from app.schemas.response_loop import (
    StudentParticipation,
    StudentReleasedComment,
    StudentWeekResults,
)
from app.services import clock, reporting, response_loop, survey_read
from app.services.report_comments import student_comments, student_released_comments

__all__ = [
    "ResultsUnavailableError",
    "student_week_results",
]


class ResultsUnavailableError(Exception):
    """There are no results this student may read for that section and course week.

    **One exception for every refusal, and it carries nothing.** A section the
    student is not enrolled in, an enrollment that has ended, a week whose report
    has not opened, and a section or a week that does not exist all leave by it,
    so the route answers them with one status and one sentence (ADR 0193).
    Telling them apart would tell a student that a section they are not in
    exists, or how long their own section runs.
    """


def student_week_results(
    session: Session,
    *,
    user_id: UUID,
    section_id: UUID,
    course_week: int | None,
    settings: Settings,
) -> StudentWeekResults:
    """One week's state and response, for a student of the section, once its report has opened.

    `course_week` names the week; `None` asks for the latest published week, which
    is the week the student's page opens on. Either way the payload lists every
    course week of the section whose report has opened, ascending, so the page
    can page back through published weeks only (SPEC §5.4). A section with no
    published week is refused, as an unopened week is.

    **The section is found among the student's own live enrollments**, through
    the survey read's `_live_enrollments`, and never read by its key first: a
    section the student is not enrolled in today is not found, exactly as one
    that does not exist is not. **The week is found among the section's
    published weeks** (`reporting._published_weeks`, the instructor report's own
    selection, ADR 0184), so an unopened week and a week the section never runs
    are not found either. Only then is a response read, so nothing of a refused
    week is ever loaded.

    The author's name comes through the staff-name definer, asked as this
    student. It answers anyone who has published to the section, so a response
    whose author it does not answer is a broken invariant, and raises rather than
    serving the response unattributed.

    Raises `ResultsUnavailableError` for every refusal.
    """
    today = clock.today(session, settings=settings)
    section = next(
        (
            enrolled
            for enrolled, _term, _course, _prefix in survey_read._live_enrollments(
                session, user_id=user_id, today=today
            )
            if enrolled.id == section_id
        ),
        None,
    )
    if section is None:
        raise ResultsUnavailableError
    published = sorted(
        reporting._published_weeks(session, section=section, settings=settings),
        key=lambda opened: opened.course_week,
    )
    if course_week is None:
        week = published[-1] if published else None
    else:
        week = next((opened for opened in published if opened.course_week == course_week), None)
    if week is None:
        raise ResultsUnavailableError
    published_weeks = [opened.course_week for opened in published]

    label = reporting._course_label(session, section)
    # A staff name, not a figure about the week, so it is read before the hold
    # decides anything and carried in every state.
    lead_name = response_loop.section_lead_name(
        session, section_id=section.id, reader_user_id=user_id, settings=settings
    )

    state, response = response_loop._state_and_response(
        session,
        section=section,
        week_id=week.week_id,
        closes_at=week.closes_at,
        settings=settings,
        reader_user_id=user_id,
    )
    participation = _own_participation(session, user_id=user_id, section_id=section.id)
    if state == "awaiting":
        # The hold (SPEC §5.3): nothing about the week, read or served, until a
        # response releases it. Decided before any figure or comment is read.
        return StudentWeekResults(
            course_label=label,
            lead_name=lead_name,
            state=state,
            response=response,
            published_weeks=published_weeks,
            streams=None,
            workload_median=None,
            released=None,
            participation=participation,
        )

    held_week_ids = {
        clock_.week_id
        for clock_ in response_loop._week_clocks(session, sections=[section], settings=settings)
        if clock_.required and not clock_.answered
    }
    readable = [opened for opened in published if opened.week_id not in held_week_ids]
    streams, workload_median = reporting.student_streams(
        session,
        section_id=section.id,
        week_id=week.week_id,
        trend=[
            (opened.course_week, opened.week_id)
            for opened in readable
            if opened.course_week <= week.course_week
        ],
        comments={
            token: [
                comment.text
                for comment in student_comments(
                    session, section_id=section.id, week_id=week.week_id, stream=token
                )
            ]
            for token in REPORT_STREAMS
        },
    )
    # ADR 0197: the release group only on the latest published week's
    # page, only while no published week is held, and only the batches cut
    # before this week's report opened.
    released = None
    if week.course_week == published[-1].course_week and len(readable) == len(published):
        as_of = reporting.report_opens_at(
            week.closes_at, zone=ZoneInfo(settings.institution_timezone)
        )
        released = [
            StudentReleasedComment(text=comment.text, stream=comment.stream.lower())
            for token in REPORT_STREAMS
            for comment in student_released_comments(
                session,
                section_id=section.id,
                term_id=section.term_id,
                stream=token,
                as_of=as_of,
            )
        ]
    return StudentWeekResults(
        course_label=label,
        lead_name=lead_name,
        state=state,
        response=response,
        published_weeks=published_weeks,
        streams=streams,
        workload_median=workload_median,
        released=released,
        participation=participation,
    )


def _own_participation(
    session: Session, *, user_id: UUID, section_id: UUID
) -> StudentParticipation | None:
    """The reader's own newest accepted score for the section, as posted, or `None`.

    Keyed by the session's user and the section already found among that user's
    live enrollments, so no other student's row and no other section's row is
    reachable. A `failed` row is never a score (ADR 0198).
    """
    latest = latest_grade_sync(
        session, section_id=section_id, user_id=user_id, outcome=GradeSyncOutcome.POSTED
    )
    if latest is None:
        return None
    return StudentParticipation(score_text=latest.score_text, ledger_text=latest.ledger_text)
