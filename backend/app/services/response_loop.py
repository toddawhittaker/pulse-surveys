"""The response loop (SPEC §5.3): who a section's staff are, by name, for a reader of it.

The first piece is the one Python door to the staff-name definer,
`public.section_staff_names` (the set-based overload in
`views_sql/section_staff_names_v002.sql`, ADR 0201, which supersedes ADR 0191 in
part). SPEC §5.3 posts a response under its author's name, the survey page names
the section's professor, and E9's leadership pages name each section's lead,
chair and dean, so a reader has to be able to read a member of staff's name, and
`pulse_app` holds no privilege on `person`. The definer answers, for each section
passed that the reader may read, its live teaching instructors, anyone who has
published a response to it, its course's lead, its department's chair and its
college's dean, each as a row of its own role. Every reader check is inside it.

**This module is the only one under `backend/app/` that names the definer**
(`tests/unit/test_only_the_response_loop_service_names_the_staff_name_definer.py`).
The definer trusts the reader key and the reader's date it is handed, and it
answers chair and above for any section passed. So a caller must get three things
right: pass the reader of its own session — the student's `user` key or the
member of staff's `person` key — and never a key taken from a request; let the
door compute the date; and, for a leadership reader, pass the scope resolved for
that reader, so the door sends only purview sections. A second caller would be a
second place that could get them wrong.

**A refusal is an empty list**, the same answer a section with no instructor
gives, and nothing here logs what it was asked or what it answered: no refusal
may carry a staff name (ADR 0191), and a log line of an answer is one.

## The hold (ADR 0193)

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
    them do (ADR 0194), and the table's guard trigger refuses a row whose author or
    setter does not hold the role it names.
  - The student results route's read, which calls these, lives in its own
    module, `services/student_results.py`.

## The doors (ADR 0194)

Every door here decides who may write or read, then calls the writers above.

  - **The instructor's publish, edit and read** of one of their own published
    weeks, behind the report's own gate (`reporting._published_section_week`),
    so they refuse exactly what the report refuses. One response per
    section-week: a publish when one exists is refused, and only the person who
    first published may edit (ruling 3).
  - **The policy read and switch** over `authz.lead_review_courses` (ruling 1),
    and, for a chair, the read of the department's led courses
    (`authz.chaired_courses_with_a_lead`, ruling 5).
  - **`is_owed` and `on_behalf_open`**: a week required by its policy of record,
    unanswered, and 48 or 96 hours past its report opening (ruling 2).
  - **`responses_owed`**: the reader's owed section-weeks, set-based.
  - **The on-behalf doors**: one gate (`_on_behalf_door`) decides every refusal
    before anything that varies with the week's state is read, and every
    refusal is `OnBehalfUnavailableError`, which the route answers with one 404.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.ai.contracts import CheckTheme
from app.config import Settings
from app.models.loop import InstructorResponse, PolicyMode, PolicyRole, ResponsePolicy, ResponseRole
from app.models.org import Course, Prefix, Section
from app.models.term import SurveyWindow, Term, Week
from app.schemas.response_loop import (
    OnBehalfWeek,
    OwedWeek,
    PolicyCourse,
    PolicyOverview,
    PolicyPrefix,
    ResponseWrite,
    StudentResponse,
    WeekResponseView,
    WeekState,
)
from app.services import clock, reporting
from app.services.authz import (
    ActorScope,
    chaired_courses_with_a_lead,
    lead_review_courses,
    taught_or_once_taught_section_ids,
)
from app.services.reporting import SectionUnavailableError
from app.services.section_codes import course_label, course_week_of, week_of_the_term

__all__ = [
    "NoPolicyToSetError",
    "NotYoursToEditError",
    "OnBehalfUnavailableError",
    "ResponseAlreadyPublishedError",
    "StaffName",
    "StaffNameRole",
    "edit_as_instructor",
    "edit_on_behalf",
    "first_response",
    "instructor_week_response",
    "is_owed",
    "on_behalf_check",
    "on_behalf_draft",
    "on_behalf_open",
    "on_behalf_week",
    "policy_overview",
    "publish_as_instructor",
    "publish_on_behalf",
    "responses_owed",
    "set_policy",
    "latest_response",
    "policy_of_record",
    "publish_response",
    "record_policy",
    "section_lead_name",
    "section_staff_names",
    "week_state",
]

# The parameters are cast rather than written with `::`, because SQLAlchemy's
# `text()` stops reading a bind parameter at a colon, and an uncast null is
# untyped. The ids travel as one array, so a page's sections are one call.
_SECTION_STAFF_NAMES = text(
    "SELECT section_id, role, person_id, display_name FROM public.section_staff_names("
    "CAST(:section_ids AS uuid[]), CAST(:reader_user_id AS uuid), "
    "CAST(:reader_person_id AS uuid), CAST(:reader_date AS date))"
)


class StaffNameRole(StrEnum):
    """What a named member of staff is to the section the row names (ADR 0201)."""

    INSTRUCTOR = "INSTRUCTOR"
    AUTHOR = "AUTHOR"
    LEAD_FACULTY = "LEAD_FACULTY"
    CHAIR = "CHAIR"
    DEAN = "DEAN"


@dataclass(frozen=True)
class StaffName:
    """One row the definer answered: a section, a role there, a `person` key and a name.

    One person can be several rows: a teacher who also published is an
    `INSTRUCTOR` row and an `AUTHOR` row of the same section.
    """

    section_id: UUID
    role: StaffNameRole
    person_id: UUID
    display_name: str


def section_staff_names(
    session: Session,
    *,
    section_ids: Sequence[UUID],
    reader_user_id: UUID | None = None,
    reader_person_id: UUID | None = None,
    scope: ActorScope | None,
    settings: Settings | None = None,
) -> list[StaffName]:
    """The staff names one reader may read for a set of sections, in one definer call.

    Name the reader by exactly one key: a student by `reader_user_id` (a
    launched student has no `person`, ADR 0028), a member of staff by
    `reader_person_id`. Passing neither or both is a caller's mistake and raises
    `ValueError` here, rather than reaching the definer, which would answer it
    with nothing.

    **`scope` is required, and a leadership caller must pass the reader's
    resolved `ActorScope`.** It has no default, so every caller states its
    choice: `scope=None` is an explicit opt-out, written at the call site. The
    definer answers a reader holding `CHAIR`,
    `ASSISTANT_DEAN`, `DEAN` or `VP_ACADEMICS` for any section it is handed
    (ADR 0201), so the purview is applied here: given a scope, only the
    sections in `scope.purview.section_ids` reach the definer. A scope resolved
    for someone other than `reader_person_id`, or given with a user key, raises
    `ValueError`, before any statement is sent. With `scope=None` every id is
    passed, which is right for a student, an instructor or a lead, whom the
    definer checks per section, and wrong for chair and above.

    **The reader's date is the application clock's** (`clock.today`, in the
    institution's timezone, development override included), so the definer's
    live-enrollment check agrees with the survey read's. `settings` is the
    configuration the caller already holds; without one it is read here.

    Answered in the definer's order: by section, role, name and key. A list of
    ids that leaves nothing to ask answers an empty list without a call.
    """
    if (reader_user_id is None) == (reader_person_id is None):
        raise ValueError(
            "section_staff_names takes exactly one reader key: reader_user_id for a student, "
            "reader_person_id for a member of staff."
        )
    asked = list(dict.fromkeys(section_ids))
    if scope is not None:
        if scope.person_id != reader_person_id:
            raise ValueError(
                "section_staff_names was given a scope resolved for another reader than "
                "reader_person_id; a scope belongs to the member of staff it was resolved for."
            )
        asked = [section_id for section_id in asked if section_id in scope.purview.section_ids]
    if not asked:
        return []
    reader_date = clock.today(session, settings=Settings() if settings is None else settings)
    rows = session.execute(
        _SECTION_STAFF_NAMES,
        {
            "section_ids": [str(section_id) for section_id in asked],
            "reader_user_id": None if reader_user_id is None else str(reader_user_id),
            "reader_person_id": None if reader_person_id is None else str(reader_person_id),
            "reader_date": reader_date,
        },
    ).all()
    return [
        StaffName(
            section_id=row.section_id,
            role=StaffNameRole(row.role),
            person_id=row.person_id,
            display_name=row.display_name,
        )
        for row in rows
    ]


def section_lead_name(
    session: Session,
    *,
    section_id: UUID,
    reader_user_id: UUID | None = None,
    reader_person_id: UUID | None = None,
    settings: Settings | None = None,
) -> str | None:
    """The name of the section's course's Lead Faculty, for the header of a course page (§2.1).

    Asked through `section_staff_names` with the reader's own key and no scope:
    the two callers are the student's results page and the teaching
    instructor's report, readers the definer checks per section. Passing
    neither key or both raises `ValueError`, from that door.

    `None` when the reader may not read the section or the course has no lead.
    A course with no lead falls to its chair (SPEC §2.1), but the header names
    the Lead Faculty, so the chair's row is never read in its place.

    A course has at most one lead (`uq_lead_faculty_mapping_course_id`), so a
    second lead row is a broken invariant and raises rather than picking one.
    """
    leads = [
        staff.display_name
        for staff in section_staff_names(
            session,
            section_ids=[section_id],
            reader_user_id=reader_user_id,
            reader_person_id=reader_person_id,
            scope=None,
            settings=settings,
        )
        if staff.section_id == section_id and staff.role is StaffNameRole.LEAD_FACULTY
    ]
    if len(leads) > 1:
        raise RuntimeError("section_staff_names answered more than one lead for one section.")
    return leads[0] if leads else None


# ---------------------------------------------------------------------------
# The hold (ADR 0193).
# ---------------------------------------------------------------------------

# The two roles a response is written on the instructor's behalf under (SPEC §5.3,
# ruling 5).
_ON_BEHALF_ROLES = frozenset({ResponseRole.LEAD_FACULTY, ResponseRole.CHAIR})


def policy_of_record(session: Session, *, course_id: UUID, report_opens_at: datetime) -> PolicyMode:
    """The response policy that governs a week of this course whose report opens at `report_opens_at`.

    The latest row by `sequence` among the course's rows recorded at or before
    the opening. With no such row the week is encouraged. `sequence`, never
    `set_at`, decides "latest" (ADR 0187's reasoning, ADR 0192); `set_at` decides
    only which rows were in force at the opening (ruling 6).
    """
    rows = session.execute(
        select(ResponsePolicy.set_at, ResponsePolicy.mode)
        .where(ResponsePolicy.course_id == course_id)
        .order_by(ResponsePolicy.sequence)
    ).tuples()
    return _mode_in_force(rows, report_opens_at=report_opens_at)


def _mode_in_force(
    rows: Iterable[tuple[datetime, str]], *, report_opens_at: datetime
) -> PolicyMode:
    """The policy rule, written once: the last of a course's rows set at or before the opening.

    `rows` are one course's `(set_at, mode)` pairs in `sequence` order. With none
    set at or before `report_opens_at`, the week is encouraged. `policy_of_record`
    asks it about one course and `_week_clocks` about many, over rows each read
    in its own shape (ADR 0193, ADR 0197).
    """
    in_force = [mode for set_at, mode in rows if set_at <= report_opens_at]
    return PolicyMode(in_force[-1]) if in_force else PolicyMode.ENCOURAGED


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

    **It decides nothing about who may publish.** The doors check the reader,
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
    they may set a policy at all is the door's question (ADR 0194), and the table's
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
    of the two keys, as `section_staff_names` requires) about this one section.
    The definer answers anyone who has published to the section as an `AUTHOR`
    row, so a response whose author it does not answer is a broken invariant, and
    raises rather than serving the response unattributed.
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
            section_ids=[section.id],
            reader_user_id=reader_user_id,
            reader_person_id=reader_person_id,
            scope=None,
            settings=settings,
        )
        if staff.role is StaffNameRole.AUTHOR
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


# ---------------------------------------------------------------------------
# The doors (ADR 0194).
# ---------------------------------------------------------------------------

# SPEC §5.3 and ruling 2: owed from report open + 48 hours (§5.6 rule 4), and
# open on behalf from report open + 96 hours.
OWED_AFTER = timedelta(hours=48)
ON_BEHALF_AFTER = timedelta(hours=96)


class ResponseAlreadyPublishedError(Exception):
    """The instructor's publish, for a week that already has a response (ruling 3)."""


class NotYoursToEditError(Exception):
    """An edit of a week with no response, or of one the reader did not first publish.

    One exception for both causes, and the route one sentence: telling them
    apart would tell the reader whether somebody else had published.
    """


class NoPolicyToSetError(Exception):
    """A policy switch for a prefix where the reader sets no course, or no such prefix."""


class OnBehalfUnavailableError(Exception):
    """Every refusal of every on-behalf door, carrying nothing (ADR 0194).

    A course outside the reader's own, a section they teach or taught, a week
    not published, not required, already answered or not yet 96 hours past its
    report opening, an edit by anyone but the first publisher, and a key nothing
    holds all leave by this one exception, so the one 404 cannot say which.
    """


# -- the instructor's doors --------------------------------------------------


def publish_as_instructor(
    session: Session,
    *,
    person_id: UUID | None,
    section_id: UUID,
    course_week: int,
    write: ResponseWrite,
    settings: Settings,
) -> WeekResponseView:
    """Publish the week's response for one of this person's own published weeks.

    The report's gate first, so a section they do not teach, one that does not
    exist and a week not yet published are refused with the report's own
    exceptions (`SectionUnavailableError`, `CourseWeekUnavailableError`). A week
    that already has a response, whoever wrote it, raises
    `ResponseAlreadyPublishedError` and writes nothing.
    """
    section, week, author = _instructors_week(
        session,
        person_id=person_id,
        section_id=section_id,
        course_week=course_week,
        settings=settings,
    )
    if first_response(session, section_id=section.id, week_id=week.week_id) is not None:
        raise ResponseAlreadyPublishedError
    return _write_and_view(
        session,
        section=section,
        week=week,
        author=author,
        role=ResponseRole.INSTRUCTOR,
        write=write,
        settings=settings,
    )


def edit_as_instructor(
    session: Session,
    *,
    person_id: UUID | None,
    section_id: UUID,
    course_week: int,
    write: ResponseWrite,
    settings: Settings,
) -> WeekResponseView:
    """Append an edit to the week's response, for the person who first published it.

    The report's gate first. A week with no response, or one somebody else
    first published (a lead on the instructor's behalf, say), raises
    `NotYoursToEditError` and writes nothing. An edit never holds the week
    again: the first row decides the state (ruling 3, `week_state`).
    """
    section, week, author = _instructors_week(
        session,
        person_id=person_id,
        section_id=section_id,
        course_week=course_week,
        settings=settings,
    )
    first = first_response(session, section_id=section.id, week_id=week.week_id)
    if first is None or first.author_person_id != author:
        raise NotYoursToEditError
    return _write_and_view(
        session,
        section=section,
        week=week,
        author=author,
        role=ResponseRole.INSTRUCTOR,
        write=write,
        settings=settings,
    )


def instructor_week_response(
    session: Session,
    *,
    person_id: UUID | None,
    section_id: UUID,
    course_week: int,
    settings: Settings,
) -> WeekResponseView:
    """The week's state and response as students read them, for one of this person's weeks."""
    section, week, author = _instructors_week(
        session,
        person_id=person_id,
        section_id=section_id,
        course_week=course_week,
        settings=settings,
    )
    return _view(session, section=section, week=week, reader=author, settings=settings)


def _instructors_week(
    session: Session,
    *,
    person_id: UUID | None,
    section_id: UUID,
    course_week: int,
    settings: Settings,
) -> tuple[Section, "reporting._SectionWeek", UUID]:
    """The report's own gate, and the reader's `person` key, which it has just checked."""
    if person_id is None:
        raise SectionUnavailableError
    section, week, _ = reporting._published_section_week(
        session,
        person_id=person_id,
        section_id=section_id,
        course_week=course_week,
        settings=settings,
    )
    return section, week, person_id


def _write_and_view(
    session: Session,
    *,
    section: Section,
    week: "reporting._SectionWeek",
    author: UUID,
    role: ResponseRole,
    write: ResponseWrite,
    settings: Settings,
) -> WeekResponseView:
    """Append one row through the one writer, commit, and answer the week as students now read it."""
    publish_response(
        session,
        section_id=section.id,
        course_week=week.course_week,
        author_person_id=author,
        role=role,
        ai_seeded=write.ai_seeded,
        body=write.text,
    )
    session.commit()
    return _view(session, section=section, week=week, reader=author, settings=settings)


def _view(
    session: Session,
    *,
    section: Section,
    week: "reporting._SectionWeek",
    reader: UUID,
    settings: Settings,
) -> WeekResponseView:
    state, response = _state_and_response(
        session,
        section=section,
        week_id=week.week_id,
        closes_at=week.closes_at,
        settings=settings,
        reader_person_id=reader,
    )
    first = first_response(session, section_id=section.id, week_id=week.week_id)
    return WeekResponseView(
        state=state,
        response=response,
        can_edit=first is not None and first.author_person_id == reader,
    )


# -- the policy (rulings 1 and 5) ----------------------------------------------


def policy_overview(session: Session, *, person_id: UUID | None) -> PolicyOverview:
    """Every course whose policy this reader sets or reads, by prefix (ADR 0194).

    The courses `lead_review_courses` gives the reader, which they set, and for a
    chair the department's courses that have a lead, which they read and cannot
    set. Nothing else: a sibling lead's course is in neither set. A reader with
    neither reads an empty list, as an assistant dean, a dean and a vice
    president do until E9.

    `mode` is each course's latest row now, by `sequence`; the policy of record
    for a week is a different question (`policy_of_record`). `set_by_role` is
    carried only on a course the reader cannot set, so nothing on a course the
    reader sets moves with anybody else's change (done-when 4).
    """
    if person_id is None:
        return PolicyOverview(prefixes=[])
    settable = lead_review_courses(session, person_id=person_id)
    readable = set(settable) | chaired_courses_with_a_lead(session, person_id=person_id)
    if not readable:
        return PolicyOverview(prefixes=[])
    latest: dict[UUID, ResponsePolicy] = {}
    for row in session.scalars(
        select(ResponsePolicy)
        .where(ResponsePolicy.course_id.in_(list(readable)))
        .order_by(ResponsePolicy.sequence)
    ):
        latest[row.course_id] = row
    by_prefix: dict[UUID, tuple[str, list[PolicyCourse]]] = {}
    for course, prefix in session.execute(
        select(Course, Prefix)
        .join(Prefix, Prefix.id == Course.prefix_id)
        .where(Course.id.in_(list(readable)))
    ).tuples():
        current = latest.get(course.id)
        can_set = course.id in settable
        entry = PolicyCourse(
            course_id=course.id,
            course_label=course_label(
                prefix_code=prefix.code, lms_number=course.lms_number, lms_title=course.lms_title
            ),
            mode=PolicyMode.ENCOURAGED if current is None else PolicyMode(current.mode),
            can_set=can_set,
            set_by_role=None if can_set or current is None else PolicyRole(current.role),
        )
        by_prefix.setdefault(prefix.id, (prefix.code, []))[1].append(entry)
    return PolicyOverview(
        prefixes=[
            PolicyPrefix(
                prefix_id=prefix_id,
                prefix_code=code,
                courses=sorted(courses, key=lambda c: (c.course_label, str(c.course_id))),
            )
            for prefix_id, (code, courses) in sorted(
                by_prefix.items(), key=lambda item: (item[1][0], str(item[0]))
            )
        ]
    )


def set_policy(
    session: Session, *, person_id: UUID | None, prefix_id: UUID, mode: PolicyMode
) -> PolicyOverview:
    """Switch the policy of every course in the prefix this reader sets it for, and commit.

    One `record_policy` call per role the reader holds a course of the prefix
    under, so a lead who also chairs writes a `LEAD_FACULTY` row for the course
    they lead and a `CHAIR` row for the department's unled course, each the role
    `lead_review_courses` gives for it. A reader who sets no course of the
    prefix, and a prefix that does not exist, raise `NoPolicyToSetError` before
    anything is written.
    """
    if person_id is None:
        raise NoPolicyToSetError
    settable = lead_review_courses(session, person_id=person_id)
    in_prefix = session.scalars(
        select(Course.id).where(Course.prefix_id == prefix_id, Course.id.in_(list(settable)))
    ).all()
    if not in_prefix:
        raise NoPolicyToSetError
    for role in sorted({settable[course_id].value for course_id in in_prefix}):
        record_policy(
            session,
            setter_person_id=person_id,
            role=PolicyRole(role),
            prefix_id=prefix_id,
            mode=mode,
        )
    session.commit()
    return policy_overview(session, person_id=person_id)


# -- the clocks (ruling 2) ------------------------------------------------------


@dataclass(frozen=True)
class _WeekClock:
    """One published-or-not week of one section: when its report opens, and its two facts."""

    section: Section
    week_id: UUID
    course_week: int
    opens_at: datetime
    required: bool
    answered: bool

    def owed(self, now: datetime) -> bool:
        return self.required and not self.answered and now >= self.opens_at + OWED_AFTER

    def open_on_behalf(self, now: datetime) -> bool:
        return self.required and not self.answered and now >= self.opens_at + ON_BEHALF_AFTER


def is_owed(session: Session, *, section_id: UUID, course_week: int, now: datetime) -> bool:
    """Whether a response to this section's course week is owed at `now` (§5.6 rule 4).

    True when the week's policy of record is required, nobody has published a
    response, and `now` is at or after report open + 48 hours. Computed on read
    from `now`, so a caller pins the clock; E9's attention list calls this.
    False for a section or a course week that does not exist.
    """
    week = _clock_of(session, section_id=section_id, course_week=course_week, settings=Settings())
    return week is not None and week.owed(now)


def on_behalf_open(session: Session, *, section_id: UUID, course_week: int, now: datetime) -> bool:
    """Whether the responsible lead may respond on behalf at `now`: `is_owed`, at + 96 hours."""
    week = _clock_of(session, section_id=section_id, course_week=course_week, settings=Settings())
    return week is not None and week.open_on_behalf(now)


def _clock_of(
    session: Session, *, section_id: UUID, course_week: int, settings: Settings
) -> _WeekClock | None:
    section = session.get(Section, section_id)
    if section is None:
        return None
    return next(
        (
            week
            for week in _week_clocks(session, sections=[section], settings=settings)
            if week.course_week == course_week
        ),
        None,
    )


def _week_clocks(
    session: Session, *, sections: Sequence[Section], settings: Settings
) -> list[_WeekClock]:
    """Every week of these sections that has a window, with its opening and its two facts.

    **Set-based**: one read of the windows, one of the policy rows of the
    sections' courses, one of which section-weeks have a response, however many
    sections are asked about. The policy of record is `_mode_in_force`, the rule
    `policy_of_record` applies too, over the rows read once (ADR 0193). The opening is `reporting.report_opens_at` over the stored close,
    as the report computes it (ADR 0184).
    """
    if not sections:
        return []
    by_id = {section.id: section for section in sections}
    zone = ZoneInfo(settings.institution_timezone)
    windows = session.execute(
        select(
            SurveyWindow.section_id,
            SurveyWindow.week_id,
            Week.number,
            SurveyWindow.closes_at,
            Term.start_date,
        )
        .join(Week, Week.id == SurveyWindow.week_id)
        .join(Term, Term.id == Week.term_id)
        .where(SurveyWindow.section_id.in_(list(by_id)))
    ).all()
    policies: dict[UUID, list[tuple[datetime, str]]] = defaultdict(list)
    for course_id, set_at, mode in session.execute(
        select(ResponsePolicy.course_id, ResponsePolicy.set_at, ResponsePolicy.mode)
        .where(ResponsePolicy.course_id.in_({section.course_id for section in sections}))
        .order_by(ResponsePolicy.sequence)
    ):
        policies[course_id].append((set_at, mode))
    answered = set(
        session.execute(
            select(InstructorResponse.section_id, InstructorResponse.week_id)
            .where(InstructorResponse.section_id.in_(list(by_id)))
            .distinct()
        ).tuples()
    )
    clocks = []
    for section_id, week_id, number, closes_at, term_start in windows:
        section = by_id[section_id]
        opens_at = reporting.report_opens_at(closes_at, zone=zone)
        policy = _mode_in_force(policies[section.course_id], report_opens_at=opens_at)
        clocks.append(
            _WeekClock(
                section=section,
                week_id=week_id,
                course_week=course_week_of(
                    number, section_start=section.start_date, term_start=term_start
                ),
                opens_at=opens_at,
                required=policy is PolicyMode.REQUIRED,
                answered=(section_id, week_id) in answered,
            )
        )
    return clocks


def responses_owed(
    session: Session, *, person_id: UUID | None, settings: Settings
) -> list[OwedWeek]:
    """The section-weeks owed a response now, in the courses this reader answers for (decision 4).

    Over `lead_review_courses`, less every section the reader teaches or has
    taught (`taught_or_once_taught_section_ids`), on the effective clock (ADR
    0109). No instructor name and no time stamp. Ordered by label, course week
    and key, so the order says nothing about when anything happened.
    """
    if person_id is None:
        return []
    courses = lead_review_courses(session, person_id=person_id)
    if not courses:
        return []
    excluded = taught_or_once_taught_section_ids(session, person_id=person_id)
    sections = [
        section
        for section in session.scalars(select(Section).where(Section.course_id.in_(list(courses))))
        if section.id not in excluded
    ]
    now = clock.now(session, settings=settings)
    owed = [
        OwedWeek(
            section_id=week.section.id,
            section_label=reporting._course_label(session, week.section),
            course_week=week.course_week,
            on_behalf_open=week.open_on_behalf(now),
        )
        for week in _week_clocks(session, sections=sections, settings=settings)
        if week.owed(now)
    ]
    return sorted(owed, key=lambda w: (w.section_label, w.course_week, str(w.section_id)))


# -- on behalf (ruling 9) ---------------------------------------------------------


@dataclass(frozen=True)
class _OnBehalfDoor:
    """A section-week a reader may act on behalf in, and the role they answer for its course under."""

    section: Section
    week: "reporting._SectionWeek"
    reader: UUID
    role: ResponseRole


def _on_behalf_door(
    session: Session,
    *,
    person_id: UUID | None,
    section_id: UUID,
    course_week: int,
    settings: Settings,
    purpose: Literal["act", "edit", "read"],
) -> _OnBehalfDoor:
    """The one gate every on-behalf door passes, or `OnBehalfUnavailableError`.

    **In this order, and every refusal is the same exception** (decision 6):

      1. the section is in a course `lead_review_courses` gives the reader — one
         read that answers a sibling lead's section and a key nothing holds
         alike, before anything about the week is read;
      2. it is not a section the reader teaches or has taught (ADR 0190's rule,
         a grant the roster ended included);
      3. the course week's report has opened;
      4. to act: the week is open on behalf now (required, unanswered, 96 hours
         past its opening). To edit: the reader first published its response.
         To read: either of those (ADR 0194, as amended), so the first publisher
         can come back to an answered week and nobody else can.

    So a refusal for a course outside the reader's own never reads the week, and
    cannot vary with it. Nothing here calls a model or writes.
    """
    if person_id is None:
        raise OnBehalfUnavailableError
    answered_for = lead_review_courses(session, person_id=person_id)
    section = session.scalars(
        select(Section).where(Section.id == section_id, Section.course_id.in_(list(answered_for)))
    ).one_or_none()
    if section is None:
        raise OnBehalfUnavailableError
    if section.id in taught_or_once_taught_section_ids(session, person_id=person_id):
        raise OnBehalfUnavailableError
    week = next(
        (
            published
            for published in reporting._published_weeks(session, section=section, settings=settings)
            if published.course_week == course_week
        ),
        None,
    )
    if week is None:
        raise OnBehalfUnavailableError
    first = first_response(session, section_id=section.id, week_id=week.week_id)
    first_publisher = first is not None and first.author_person_id == person_id
    if purpose == "edit" or (purpose == "read" and first_publisher):
        if not first_publisher:
            raise OnBehalfUnavailableError
    else:
        clock_ = _clock_of(
            session, section_id=section.id, course_week=course_week, settings=settings
        )
        if clock_ is None or not clock_.open_on_behalf(clock.now(session, settings=settings)):
            raise OnBehalfUnavailableError
    return _OnBehalfDoor(
        section=section,
        week=week,
        reader=person_id,
        role=ResponseRole(answered_for[section.course_id].value),
    )


def on_behalf_week(
    session: Session,
    *,
    person_id: UUID | None,
    section_id: UUID,
    course_week: int,
    settings: Settings,
) -> OnBehalfWeek:
    """The section-week's stored summaries and ratings, as the on-behalf reader reads them.

    No comment text, at any threshold, and no summary written before the week's
    latest removal (`reporting.on_behalf_streams`). `response` is null while the
    week is unanswered; once it is answered the door admits only its first
    publisher, who reads the response to edit it (ADR 0194, as amended).
    """
    door = _on_behalf_door(
        session,
        person_id=person_id,
        section_id=section_id,
        course_week=course_week,
        settings=settings,
        purpose="read",
    )
    answered = first_response(session, section_id=door.section.id, week_id=door.week.week_id)
    return OnBehalfWeek(
        section_label=reporting._course_label(session, door.section),
        course_week=door.week.course_week,
        streams=reporting.on_behalf_streams(
            session, section_id=door.section.id, week_id=door.week.week_id
        ),
        response=None
        if answered is None
        else _view(
            session, section=door.section, week=door.week, reader=door.reader, settings=settings
        ),
    )


def on_behalf_draft(
    session: Session,
    *,
    person_id: UUID | None,
    section_id: UUID,
    course_week: int,
    settings: Settings,
) -> str:
    """04's draft over the on-behalf gather, once the gate has passed (no model call before it)."""
    door = _on_behalf_door(
        session,
        person_id=person_id,
        section_id=section_id,
        course_week=course_week,
        settings=settings,
        purpose="act",
    )
    return reporting.week_response_draft(
        session, section_id=door.section.id, week_id=door.week.week_id, author_role=door.role
    )


def on_behalf_check(
    session: Session,
    *,
    person_id: UUID | None,
    section_id: UUID,
    course_week: int,
    draft: str,
    settings: Settings,
) -> tuple[CheckTheme, ...]:
    """04's check over the on-behalf gather, once the gate has passed."""
    door = _on_behalf_door(
        session,
        person_id=person_id,
        section_id=section_id,
        course_week=course_week,
        settings=settings,
        purpose="act",
    )
    return reporting.week_draft_check(
        session,
        section_id=door.section.id,
        week_id=door.week.week_id,
        draft=draft,
        for_on_behalf=True,
    )


def publish_on_behalf(
    session: Session,
    *,
    person_id: UUID | None,
    section_id: UUID,
    course_week: int,
    write: ResponseWrite,
    settings: Settings,
) -> WeekResponseView:
    """Publish the week's response under the reader's own name and role for its course.

    Once a response exists the week is answered and this door is closed:
    editing is `edit_on_behalf`, for the first publisher only.
    """
    door = _on_behalf_door(
        session,
        person_id=person_id,
        section_id=section_id,
        course_week=course_week,
        settings=settings,
        purpose="act",
    )
    return _write_and_view(
        session,
        section=door.section,
        week=door.week,
        author=door.reader,
        role=door.role,
        write=write,
        settings=settings,
    )


def edit_on_behalf(
    session: Session,
    *,
    person_id: UUID | None,
    section_id: UUID,
    course_week: int,
    write: ResponseWrite,
    settings: Settings,
) -> WeekResponseView:
    """Append an edit to an on-behalf response, by its first publisher, while they answer for the course."""
    door = _on_behalf_door(
        session,
        person_id=person_id,
        section_id=section_id,
        course_week=course_week,
        settings=settings,
        purpose="edit",
    )
    return _write_and_view(
        session,
        section=door.section,
        week=door.week,
        author=door.reader,
        role=door.role,
        write=write,
        settings=settings,
    )
