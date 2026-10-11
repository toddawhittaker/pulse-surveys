"""The response-loop exit story for `MATH-140-E1FF`: two weeks of answers, for a dev stack.

SPEC §14.3's exit for the response loop: "a required-mode section shows nothing
to students until a named human publishes." `tests/e2e/exit-response-loop.spec.ts`
drives the clause. This file writes the one thing the drive does not write
through a page: three students' answers to course weeks 3 and 4, ratings and a
workload and no comment, so each week has responses for its report and for the
AI draft to count.

**It writes no policy, no response from staff, and no grant.** The Lead
Faculty's switch to required goes through the policy page, and so through the
writer every switch goes through; the instructor's and the lead's responses go
through their pages. A row this file planted there would be the drive agreeing
with itself (`docs/MISTAKES.md` entry 30). This connection holds no privilege on
the grant tables in any case.

**Why `MATH-140-E1FF`.** The drive needs a student who can open the results
page, and the mock platform's launch page offers one learner. Of the sections
she is enrolled in, `BIOL-215-R3WW`'s response table is read empty by
`tests/e2e/instructor-response.spec.ts`, and the response table is append-only,
so the story is told in `MATH-140-E1FF`.

**It provisions nothing** (`docs/MISTAKES.md` entry 48). The section, its
windows and the respondents' enrollments are the staff launch's, the roster
sync's and the window job's; each missing piece is a refusal naming it.

**Idempotent by natural key**: a response is matched on `(user_id, section_id,
week_id)` and an answer on `(response_id, question_id)`.

`scripts/` is not in the `api` image, so this file is piped into `python -` whole
(`tests/e2e/support/stack.ts`). It imports only `app.*` and the standard library,
which is why the shapes below repeat `scripts/seed_moderation_exit_story.py`'s
rather than import them.
"""

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, is_development
from app.db import SessionLocal
from app.models.identity import Enrollment
from app.models.org import Section
from app.models.survey import REPORT_STREAMS, Answer, Question, QuestionKind, QuestionSet, Response
from app.models.term import SurveyWindow, Term, Week
from app.services.identity import subject_for_user
from app.services.section_codes import week_of_the_term
from app.services.validity import recompute_response_validity

SECTION_CODE = "E1FF"
SECTION_LABEL = "MATH-140-E1FF"

# The first is the week the instructor answers, the second the week the lead
# answers on the instructor's behalf; the drive reads both off this section's
# own windows.
EXIT_WEEKS = (3, 4)

LEARNER = "mock-lms-user-learner"


def student(ordinal: int) -> str:
    """One of `MATH-140-E1FF`'s per-section students, by the `sub` the platform sends."""
    return f"mock-lms-user-{SECTION_LABEL.lower()}-student-{ordinal:02d}"


RESPONDENTS = (LEARNER, student(1), student(2))
INSTRUCTOR_RATING_POINTS = 4
COURSE_RATING_POINTS = 3
WORKLOAD_HOURS = Decimal("6")

# SPEC §3.2's three non-comment questions, by position, as `scripts/seed.py` writes them.
INSTRUCTOR_RATING, COURSE_RATING, WORKLOAD = 1, 3, 5
INSTRUCTOR_STREAM, COURSE_STREAM = REPORT_STREAMS
EXPECTED_INSTRUMENT: Mapping[int, tuple[QuestionKind, str | None]] = {
    INSTRUCTOR_RATING: (QuestionKind.LIKERT, INSTRUCTOR_STREAM),
    COURSE_RATING: (QuestionKind.LIKERT, COURSE_STREAM),
    WORKLOAD: (QuestionKind.WORKLOAD, None),
}


class StoryRefusedError(Exception):
    """The world this story needs is not there, and this file will not invent it."""


@dataclass(frozen=True)
class WeekOfTheSection:
    """One course week of this section: its `week` key and its window's opening."""

    course_week: int
    week_id: UUID
    opens_at: datetime


def the_section(session: Session) -> Section:
    """The one `section` row `MATH-140-E1FF` reached this database as."""
    found = list(session.scalars(select(Section).where(Section.lms_section_code == SECTION_CODE)))
    if len(found) != 1:
        raise StoryRefusedError(
            f"{SECTION_LABEL} matches {len(found)} section row(s), and this story needs exactly "
            "one. Zero means no staff launch has provisioned it; this file creates no section."
        )
    return found[0]


def the_weeks(session: Session, section: Section) -> tuple[WeekOfTheSection, ...]:
    """The story's course weeks, through the codebase's one reading of SPEC §2.2's two axes."""
    term = session.get(Term, section.term_id)
    if term is None:  # pragma: no cover - `section.term_id` is a non-null foreign key
        raise StoryRefusedError(f"{SECTION_LABEL} names a term that holds no row.")
    weeks: list[WeekOfTheSection] = []
    for course_week in EXIT_WEEKS:
        term_week = week_of_the_term(
            course_week, section_start=section.start_date, term_start=term.start_date
        )
        week_id = session.scalars(
            select(Week.id).where(Week.term_id == term.id, Week.number == term_week)
        ).one_or_none()
        opens_at = None
        if week_id is not None:
            opens_at = session.scalars(
                select(SurveyWindow.opens_at).where(
                    SurveyWindow.section_id == section.id, SurveyWindow.week_id == week_id
                )
            ).one_or_none()
        if week_id is None or opens_at is None:
            raise StoryRefusedError(
                f"Course week {course_week} of {SECTION_LABEL} (term week {term_week}) has no "
                "`week` row or no `survey_window`. `derive_survey_windows` writes the windows "
                "after a launch; this file creates neither."
            )
        weeks.append(WeekOfTheSection(course_week=course_week, week_id=week_id, opens_at=opens_at))
    return tuple(weeks)


def the_instrument(session: Session) -> dict[int, UUID]:
    """The three non-comment questions of the set in force, by position, shape-checked."""
    question_set_id = session.scalars(
        select(QuestionSet.id).order_by(QuestionSet.version.desc()).limit(1)
    ).one_or_none()
    if question_set_id is None:
        raise StoryRefusedError("This database holds no `question_set`. Run `make seed` first.")
    asked = {
        position: (question_id, kind, stream)
        for question_id, position, kind, stream in session.execute(
            select(Question.id, Question.position, Question.kind, Question.stream).where(
                Question.question_set_id == question_set_id
            )
        )
    }
    for position, (kind, stream) in EXPECTED_INSTRUMENT.items():
        found = asked.get(position)
        if found is None or found[1] != kind or found[2] != stream:
            raise StoryRefusedError(
                f"Question {position} of the set in force is {found!r}, and this story is written "
                f"for a {kind.value} question on the {stream!r} stream."
            )
    return {position: asked[position][0] for position in EXPECTED_INSTRUMENT}


def the_respondents(session: Session, section: Section) -> dict[str, UUID]:
    """The respondents' `user` rows, found through their enrollments in this section."""
    found: dict[str, UUID] = {}
    for user_id in session.scalars(
        select(Enrollment.user_id).where(Enrollment.section_id == section.id)
    ):
        subject = subject_for_user(session, user_id)
        if subject in RESPONDENTS:
            found[subject] = user_id
    missing = [subject for subject in RESPONDENTS if subject not in found]
    if missing:
        raise StoryRefusedError(
            f"These respondents hold no enrollment in {SECTION_LABEL}: {missing}. The roster sync "
            "enrols them (SPEC §7.3); this file creates no user and no enrollment."
        )
    return found


def one_response(
    session: Session, *, section: Section, week: WeekOfTheSection, user_id: UUID
) -> Response:
    """This student's response for this week, matched on §8's own key or inserted."""
    response = session.scalars(
        select(Response).where(
            Response.user_id == user_id,
            Response.section_id == section.id,
            Response.week_id == week.week_id,
        )
    ).one_or_none()
    if response is None:
        response = Response(
            user_id=user_id,
            section_id=section.id,
            week_id=week.week_id,
            term_id=section.term_id,
            first_submitted_at=week.opens_at,
            last_submitted_at=week.opens_at,
            is_valid=True,
        )
        session.add(response)
    session.flush()
    return response


def one_answer(
    session: Session,
    *,
    response: Response,
    question_id: UUID,
    rating: int | None = None,
    workload_hours: Decimal | None = None,
) -> None:
    """One answer, matched on `(response_id, question_id)` or inserted, every value column set."""
    answer = session.scalars(
        select(Answer).where(Answer.response_id == response.id, Answer.question_id == question_id)
    ).one_or_none()
    if answer is None:
        answer = Answer(response_id=response.id, question_id=question_id)
        session.add(answer)
    answer.rating = rating
    answer.comment_text = None
    answer.workload_hours = workload_hours
    session.flush()


def write_the_story(session: Session) -> int:
    """Write the answers, and answer how many responses it wrote."""
    section = the_section(session)
    weeks = the_weeks(session, section)
    questions = the_instrument(session)
    respondents = the_respondents(session, section)

    responses = 0
    for week in weeks:
        for subject in RESPONDENTS:
            response = one_response(
                session, section=section, week=week, user_id=respondents[subject]
            )
            one_answer(
                session,
                response=response,
                question_id=questions[INSTRUCTOR_RATING],
                rating=INSTRUCTOR_RATING_POINTS,
            )
            one_answer(
                session,
                response=response,
                question_id=questions[COURSE_RATING],
                rating=COURSE_RATING_POINTS,
            )
            one_answer(
                session,
                response=response,
                question_id=questions[WORKLOAD],
                workload_hours=WORKLOAD_HOURS,
            )
            recompute_response_validity(session, response)
            responses += 1
    return responses


def main() -> int:
    """Refuse outside development, write the story, and say in one line what it wrote."""
    if not is_development(Settings()):
        print(
            "seed_response_loop_exit_story refuses to run outside a development environment. "
            "See docs/adr/0063-the-demo-seed-runs-only-in-a-development-environment.md.",
            file=sys.stderr,
        )
        return 1
    with SessionLocal() as session:
        try:
            responses = write_the_story(session)
        except StoryRefusedError as refusal:
            session.rollback()
            print(f"seed_response_loop_exit_story refused: {refusal}", file=sys.stderr)
            return 1
        session.commit()
    print(
        f"seed_response_loop_exit_story wrote {SECTION_LABEL}: {responses} responses across "
        f"course weeks {EXIT_WEEKS[0]} and {EXIT_WEEKS[1]}. No policy and no staff response: "
        "those are the pages'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
