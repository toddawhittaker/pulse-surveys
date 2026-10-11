"""The response loop (SPEC §5.3): who a section's staff are, by name, for a reader of it.

E7-01 builds the first piece: the one Python door to the staff-name definer,
`public.section_staff_names` (`views_sql/section_staff_names_v001.sql`, ADR 0191).
SPEC §5.3 posts a response under its author's name, and the survey page names the
section's professor, so a student has to be able to read a member of staff's
name, and `pulse_app` holds no privilege on `person`. The definer answers one
section's live teaching instructors and anyone who has published a response to
it, and only to a reader of that section. Every reader check is inside it.

**This module is the only one under `backend/app/` that names the definer**
(`tests/unit/test_only_the_response_loop_service_names_the_staff_name_definer.py`).
The definer trusts the reader key it is handed, so the one thing a caller must
get right is to pass the reader of its own session — the student's `user` key
or the member of staff's `person` key — and never a key taken from a request. A
second caller would be a second place that could get it wrong.

**A refusal is an empty list**, the same answer a section with no instructor
gives, and nothing here logs what it was asked or what it answered: no refusal
may carry a staff name (E7-01, done-when 4), and a log line of an answer is one.

## The hold (E7-02, ADR 0193)

SPEC §5.3's required mode "holds the student-facing aggregate until a response is
published". The functions below are the gate every later reader calls rather than
copies:

  - **`policy_of_record`**: the latest `response_policy` row by `sequence` for the
    section's course whose `set_at` is at or before the week's report opening
    (`reporting.report_opens_at`, ADR 0184). None is encouraged. A policy row
    names its course (M2), so nothing here asks who is responsible now: a change
    of lead after the opening changes nothing about that week (ruling 6).
  - **`first_response` and `latest_response`**: the section-week's rows by
    `sequence`. The first row releases the week, for good (ruling 3); the latest
    row is the text students read.
  - **`week_state`**: the four states, from those three answers alone.
  - **`publish_response`** and **`record_policy`**: the two writers. Each appends
    rows and nothing else. Neither decides who may write: the doors in front of
    them do (E7-03), and the table's guard trigger refuses a row whose author or
    setter does not hold the role it names.
  - **`student_week_results`**: the student results route's read, through the
    student's live enrollment, as the survey read reaches a section.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.loop import InstructorResponse, PolicyMode, PolicyRole, ResponsePolicy, ResponseRole
from app.models.org import Course, Section
from app.models.term import Term, Week
from app.schemas.response_loop import StudentResponse, StudentWeekResults, WeekState
from app.services import clock, reporting, survey_read
from app.services.authz import lead_review_courses
from app.services.section_codes import week_of_the_term

__all__ = [
    "ResultsUnavailableError",
    "StaffName",
    "first_response",
    "latest_response",
    "policy_of_record",
    "publish_response",
    "record_policy",
    "section_staff_names",
    "student_week_results",
    "week_state",
]

# The parameters are cast rather than written with `::`, because SQLAlchemy's
# `text()` stops reading a bind parameter at a colon, and an uncast null is
# untyped.
_SECTION_STAFF_NAMES = text(
    "SELECT person_id, display_name FROM public.section_staff_names("
    "CAST(:section_id AS uuid), CAST(:reader_user_id AS uuid), "
    "CAST(:reader_person_id AS uuid))"
)


@dataclass(frozen=True)
class StaffName:
    """One member of staff the definer answered: their `person` key and their name."""

    person_id: UUID
    display_name: str


def section_staff_names(
    session: Session,
    *,
    section_id: UUID,
    reader_user_id: UUID | None = None,
    reader_person_id: UUID | None = None,
) -> list[StaffName]:
    """The staff names one reader may read for one section; empty for any other reader.

    Name the reader by exactly one key: a student by `reader_user_id` (a
    launched student has no `person`, ADR 0028), a member of staff by
    `reader_person_id`. Passing neither or both is a caller's mistake and raises
    `ValueError` here, rather than reaching the definer, which would answer it
    with nothing.

    Answered in the definer's order, by name and then by key.
    """
    if (reader_user_id is None) == (reader_person_id is None):
        raise ValueError(
            "section_staff_names takes exactly one reader key: reader_user_id for a student, "
            "reader_person_id for a member of staff."
        )
    rows = session.execute(
        _SECTION_STAFF_NAMES,
        {
            "section_id": str(section_id),
            "reader_user_id": None if reader_user_id is None else str(reader_user_id),
            "reader_person_id": None if reader_person_id is None else str(reader_person_id),
        },
    ).all()
    return [StaffName(person_id=row.person_id, display_name=row.display_name) for row in rows]


# ---------------------------------------------------------------------------
# The hold (E7-02, ADR 0193).
# ---------------------------------------------------------------------------

# The two roles a response is written on the instructor's behalf under (SPEC §5.3,
# ruling 5).
_ON_BEHALF_ROLES = frozenset({ResponseRole.LEAD_FACULTY, ResponseRole.CHAIR})


class ResultsUnavailableError(Exception):
    """There are no results this student may read for that section and course week.

    **One exception for every refusal, and it carries nothing.** A section the
    student is not enrolled in, an enrollment that has ended, a week whose report
    has not opened, and a section or a week that does not exist all leave by it,
    so the route answers them with one status and one sentence (E7-02, decision
    5). Telling them apart would tell a student that a section they are not in
    exists, or how long their own section runs.
    """


def policy_of_record(session: Session, *, course_id: UUID, report_opens_at: datetime) -> PolicyMode:
    """The response policy that governs a week of this course whose report opens at `report_opens_at`.

    The latest row by `sequence` among the course's rows recorded at or before
    the opening. With no such row the week is encouraged. `sequence`, never
    `set_at`, decides "latest" (ADR 0187's reasoning, ADR 0192); `set_at` decides
    only which rows were in force at the opening (ruling 6).
    """
    mode = session.execute(
        select(ResponsePolicy.mode)
        .where(
            ResponsePolicy.course_id == course_id,
            ResponsePolicy.set_at <= report_opens_at,
        )
        .order_by(ResponsePolicy.sequence.desc())
        .limit(1)
    ).scalar_one_or_none()
    return PolicyMode.ENCOURAGED if mode is None else PolicyMode(mode)


def first_response(
    session: Session, *, section_id: UUID, week_id: UUID
) -> InstructorResponse | None:
    """The section-week's first response row by `sequence`: the one that released the week."""
    return session.scalars(
        select(InstructorResponse)
        .where(InstructorResponse.section_id == section_id, InstructorResponse.week_id == week_id)
        .order_by(InstructorResponse.sequence.asc())
        .limit(1)
    ).first()


def latest_response(
    session: Session, *, section_id: UUID, week_id: UUID
) -> InstructorResponse | None:
    """The section-week's latest response row by `sequence`: the text students read."""
    return session.scalars(
        select(InstructorResponse)
        .where(InstructorResponse.section_id == section_id, InstructorResponse.week_id == week_id)
        .order_by(InstructorResponse.sequence.desc())
        .limit(1)
    ).first()


def week_state(*, policy: PolicyMode, first: InstructorResponse | None) -> WeekState:
    """A week's state for its students, from its policy of record and its first response.

    The first row decides, and only the first: a week is released by the first
    response and never held again (ruling 3), and whether students read it as
    written on the instructor's behalf is the role that row was written under.
    """
    if first is None:
        return "awaiting" if policy is PolicyMode.REQUIRED else "unanswered"
    return "on-behalf" if ResponseRole(first.role) in _ON_BEHALF_ROLES else "published"


def publish_response(
    session: Session,
    *,
    section_id: UUID,
    course_week: int,
    author_person_id: UUID,
    role: ResponseRole,
    ai_seeded: bool,
    body: str,
) -> InstructorResponse:
    """Append one response row for a section's course week, and do nothing else.

    **It decides nothing about who may publish.** E7-03's doors check the reader,
    the week and the clock first; the table's guard trigger refuses a row whose
    author does not hold `role` for the section, or a second author for the
    section-week. So this refuses only what the table refuses, by letting the
    database's error rise. A section, or a course week of it, that does not exist
    raises `LookupError`, because there is no row to write.

    `term_id` is the section's, and the week is course week `course_week` of the
    section on the term axis (`section_codes.week_of_the_term`, SPEC §2.2).
    `published_at` is the application clock's (ADR 0109). It flushes and does not
    commit: the caller owns the transaction.
    """
    section = session.get(Section, section_id)
    if section is None:
        raise LookupError(f"No section {section_id}, so there is no response to write.")
    week_id = _week_id_of(session, section=section, course_week=course_week)
    written = InstructorResponse(
        section_id=section.id,
        week_id=week_id,
        term_id=section.term_id,
        author_person_id=author_person_id,
        role=ResponseRole(role).value,
        ai_seeded=ai_seeded,
        body=body,
        published_at=clock.now(session, settings=Settings()),
    )
    session.add(written)
    session.flush()
    return written


def record_policy(
    session: Session,
    *,
    setter_person_id: UUID,
    role: PolicyRole,
    prefix_id: UUID,
    mode: PolicyMode,
) -> list[ResponsePolicy]:
    """Write a setter's switch for a prefix: one row per course they answer for there.

    Ruling 1: a switch covers only the courses in the prefix that
    `authz.lead_review_courses` gives the setter, under the role they set it as —
    as `LEAD_FACULTY` the courses they lead, as `CHAIR` the department's courses
    nobody leads (ruling 5). Each row names its course, fixed when written
    (ADR 0193), so a later change of lead cannot move a switch onto another
    person's course.

    All the rows carry one `set_at`, the application clock's. It flushes and does
    not commit, so the caller's one transaction holds every row or none. A setter
    who answers for no course in the prefix under `role` gets no rows: whether
    they may set a policy at all is the door's question (E7-03), and the table's
    guard trigger refuses any row whose setter does not hold the role for its
    course.
    """
    answered_for = {
        course_id
        for course_id, held in lead_review_courses(session, person_id=setter_person_id).items()
        if held.value == PolicyRole(role).value
    }
    course_ids = session.scalars(
        select(Course.id)
        .where(Course.prefix_id == prefix_id, Course.id.in_(answered_for))
        .order_by(Course.id)
    ).all()
    set_at = clock.now(session, settings=Settings())
    rows = [
        ResponsePolicy(
            course_id=course_id,
            prefix_id=prefix_id,
            set_by_person_id=setter_person_id,
            role=PolicyRole(role).value,
            mode=PolicyMode(mode).value,
            set_at=set_at,
        )
        for course_id in course_ids
    ]
    session.add_all(rows)
    session.flush()
    return rows


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

    state, response = _state_and_response(
        session,
        section=section,
        week_id=week.week_id,
        closes_at=week.closes_at,
        settings=settings,
        reader_user_id=user_id,
    )
    return StudentWeekResults(state=state, response=response, published_weeks=published_weeks)


def _state_and_response(
    session: Session,
    *,
    section: Section,
    week_id: UUID,
    closes_at: datetime,
    settings: Settings,
    reader_user_id: UUID | None = None,
    reader_person_id: UUID | None = None,
) -> tuple[WeekState, StudentResponse | None]:
    """One published section-week's state, and its response as students read it.

    The caller has already decided the reader may read this week. The author's
    name comes through the staff-name definer, asked as that reader (exactly one
    of the two keys, as `section_staff_names` requires). The definer answers
    anyone who has published to the section, so a response whose author it does
    not answer is a broken invariant, and raises rather than serving the response
    unattributed.
    """
    opens_at = reporting.report_opens_at(closes_at, zone=ZoneInfo(settings.institution_timezone))
    policy = policy_of_record(session, course_id=section.course_id, report_opens_at=opens_at)
    first = first_response(session, section_id=section.id, week_id=week_id)
    state = week_state(policy=policy, first=first)
    if first is None:
        return state, None

    latest = latest_response(session, section_id=section.id, week_id=week_id)
    if latest is None:  # pragma: no cover - the first row exists, so a latest one does
        raise RuntimeError("A section-week has a first response row and no latest one.")
    names = {
        staff.person_id: staff.display_name
        for staff in section_staff_names(
            session,
            section_id=section.id,
            reader_user_id=reader_user_id,
            reader_person_id=reader_person_id,
        )
    }
    if first.author_person_id not in names:
        raise RuntimeError(
            f"The staff-name definer did not answer the author of a response to section "
            f"{section.id}, though it answers anyone who has published to it."
        )
    return state, StudentResponse(
        text=latest.body,
        author_name=names[first.author_person_id],
        author_role=ResponseRole(first.role),
        published_at=latest.published_at,
    )


def _week_id_of(session: Session, *, section: Section, course_week: int) -> UUID:
    """The `week` row of the section's term that is course week `course_week` of the section."""
    term = session.get(Term, section.term_id)
    if term is None:  # pragma: no cover - `section.term_id` is a non-null foreign key
        raise LookupError(f"Section {section.id} names no term.")
    term_week = week_of_the_term(
        course_week, section_start=section.start_date, term_start=term.start_date
    )
    week_id = session.scalars(
        select(Week.id).where(Week.term_id == term.id, Week.number == term_week)
    ).one_or_none()
    if week_id is None:
        raise LookupError(
            f"Course week {course_week} of section {section.id} is term week {term_week}, which "
            "its term does not have."
        )
    return week_id
