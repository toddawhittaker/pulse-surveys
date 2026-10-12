"""The student-loop exit story for `MATH-140-E1FF`: two weeks of classmates' answers, for a dev stack.

SPEC §14.3's E8 exit: "the full weekly loop demos end-to-end from one student's
seat." `tests/e2e/exit-student-loop.spec.ts` drives it. The student whose seat
it is answers her own survey through the page; this file writes what her
classmates said, so the week she reads has figures and comments to show and a
stream small enough to be held:

  - **The exit week**: five classmates rate both streams and the workload. All
    five comment on the instructor, so that stream clears SPEC §4's threshold of
    five on its own; one comments on the course, so that stream stays below it
    and shows the student its small-N notice (SPEC §5.4).
  - **The week before it**: three classmates rate, give a workload and comment
    on the course. Three raters is below the threshold, so the student reads
    that week's ratings held and its course comments held (ruling 8).

**Which week.** The exit week is the first of course weeks 5 and 6 that holds
no `instructor_response`. Weeks 1 and 2 are `student-results.spec.ts`'s and 3
and 4 are `exit-response-loop.spec.ts`'s. The response table is append-only, so
a week the drive published into stays answered; a second run on one stack takes
week 6, and a third is refused with a sentence saying the stack needs to be
fresh. The drive reads the week back from the line this file prints.

**It writes no verdict, no policy, no response from staff and no grant.**
Moderation is the sweep's, and the mock provider's verdict on these unmarked
sentences is the product's own; the policy and the instructor's reply go
through their pages (`docs/MISTAKES.md` entry 30).

**It provisions nothing** (`docs/MISTAKES.md` entry 48). The section, its
windows and the classmates' enrollments are the staff launch's, the roster
sync's and the window job's; each missing piece is a refusal naming it.

**Idempotent by natural key**: a response is matched on `(user_id, section_id,
week_id)` and an answer on `(response_id, question_id)`. The drive clears the
section first (`clearTheWeek`), because this connection may not delete a row.

`scripts/` is not in the `api` image, so this file is piped into `python -`
whole (`tests/e2e/support/stack.ts`). It imports only `app.*` and the standard
library, which is why its shapes repeat `scripts/seed_moderation_exit_story.py`'s
rather than import them.
"""

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.contracts import CommentValidityOutput, ValidityVerdict
from app.ai.gateway import NOT_A_MODEL
from app.config import Settings, is_development
from app.db import SessionLocal
from app.models.identity import Enrollment
from app.models.loop import InstructorResponse
from app.models.org import Section
from app.models.survey import REPORT_STREAMS, Answer, Question, QuestionKind, QuestionSet, Response
from app.models.term import SurveyWindow, Term, Week
from app.services.identity import subject_for_user
from app.services.section_codes import week_of_the_term
from app.services.validity import recompute_response_validity, record_verdict

SECTION_CODE = "E1FF"
SECTION_LABEL = "MATH-140-E1FF"

# The course weeks no other drive publishes a response into, in the order they
# are taken.
EXIT_WEEK_CANDIDATES = (5, 6)


def student(ordinal: int) -> str:
    """One of `MATH-140-E1FF`'s per-section students, by the `sub` the platform sends."""
    return f"mock-lms-user-{SECTION_LABEL.lower()}-student-{ordinal:02d}"


CLASSMATES = tuple(student(ordinal) for ordinal in range(1, 6))
EARLIER_CLASSMATES = CLASSMATES[:3]

# Each over SPEC §3.3's twenty-five-character floor, carrying no mock-provider
# marker, and distinct inside its first forty characters. The drive transcribes
# the ones it asserts.
INSTRUCTOR_VOICES = (
    "Student loop voice one: the worked examples made the factoring steps clear.",
    "Student loop voice two: questions in class got patient and complete answers.",
    "Student loop voice three: the review at the start of class helped me catch up.",
    "Student loop voice four: office hours were easy to find and worth the trip.",
    "Student loop voice five: the instructor explained why each method works.",
)
LONE_COURSE_VOICE = "Student loop course voice: the problem sets ran longer than the reading."
EARLIER_COURSE_VOICES = (
    "Student loop earlier week: the quiz covered exactly what the module promised.",
    "Student loop earlier week: the module pages were easy to find my way around.",
    "Student loop earlier week: the practice problems matched the lecture well.",
)

SEED_PROMPT_VERSION = "development-seed.student-loop-exit-story"


@dataclass(frozen=True)
class StoryWeek:
    """One course week relative to the exit week: who answers, what, and who comments."""

    offset: int
    respondents: tuple[str, ...]
    instructor_ratings: tuple[int, ...]
    course_ratings: tuple[int, ...]
    workload_hours: tuple[str, ...]
    instructor_comments: Mapping[int, str] = field(default_factory=dict)
    course_comments: Mapping[int, str] = field(default_factory=dict)


STORY: tuple[StoryWeek, ...] = (
    StoryWeek(
        offset=-1,
        respondents=EARLIER_CLASSMATES,
        instructor_ratings=(4, 4, 3),
        course_ratings=(3, 3, 4),
        workload_hours=("5", "6", "7"),
        course_comments=dict(enumerate(EARLIER_COURSE_VOICES)),
    ),
    StoryWeek(
        offset=0,
        respondents=CLASSMATES,
        instructor_ratings=(4, 5, 3, 4, 4),
        course_ratings=(3, 4, 4, 2, 3),
        workload_hours=("6", "7", "5", "8", "6"),
        instructor_comments=dict(enumerate(INSTRUCTOR_VOICES)),
        course_comments={4: LONE_COURSE_VOICE},
    ),
)

# SPEC §3.2's five questions, by position, as `scripts/seed.py` writes them.
INSTRUCTOR_RATING, INSTRUCTOR_COMMENT, COURSE_RATING, COURSE_COMMENT, WORKLOAD = 1, 2, 3, 4, 5
INSTRUCTOR_STREAM, COURSE_STREAM = REPORT_STREAMS
EXPECTED_INSTRUMENT: Mapping[int, tuple[QuestionKind, str | None]] = {
    INSTRUCTOR_RATING: (QuestionKind.LIKERT, INSTRUCTOR_STREAM),
    INSTRUCTOR_COMMENT: (QuestionKind.COMMENT, INSTRUCTOR_STREAM),
    COURSE_RATING: (QuestionKind.LIKERT, COURSE_STREAM),
    COURSE_COMMENT: (QuestionKind.COMMENT, COURSE_STREAM),
    WORKLOAD: (QuestionKind.WORKLOAD, None),
}


class StoryRefusedError(Exception):
    """The world this story needs is not there, and this file will not invent it."""


@dataclass(frozen=True)
class WeekOfTheSection:
    """One course week of this section: its `week` key and its window's opening."""

    course_week: int
    week_id: UUID
    submitted_at: datetime


@dataclass(frozen=True)
class StoryWritten:
    """What one run wrote: the exit week, and how many responses and comments."""

    exit_week: int
    responses: int
    comments: int


def the_section(session: Session) -> Section:
    """The one `section` row `MATH-140-E1FF` reached this database as."""
    found = list(session.scalars(select(Section).where(Section.lms_section_code == SECTION_CODE)))
    if len(found) != 1:
        raise StoryRefusedError(
            f"{SECTION_LABEL} matches {len(found)} section row(s), and this story needs exactly "
            "one. Zero means no staff launch has provisioned it; this file creates no section."
        )
    return found[0]


def the_week(session: Session, section: Section, course_week: int) -> WeekOfTheSection:
    """One course week, through the codebase's one reading of SPEC §2.2's two axes."""
    term = session.get(Term, section.term_id)
    if term is None:  # pragma: no cover - `section.term_id` is a non-null foreign key
        raise StoryRefusedError(f"{SECTION_LABEL} names a term that holds no row.")
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
            f"Course week {course_week} of {SECTION_LABEL} (term week {term_week}) has no `week` "
            "row or no `survey_window`. `derive_survey_windows` writes the windows after a "
            "launch; this file creates neither."
        )
    return WeekOfTheSection(course_week=course_week, week_id=week_id, submitted_at=opens_at)


def the_exit_week(session: Session, section: Section) -> int:
    """The first candidate course week that holds no response from staff."""
    for course_week in EXIT_WEEK_CANDIDATES:
        week = the_week(session, section, course_week)
        answered = session.scalars(
            select(InstructorResponse.id)
            .where(
                InstructorResponse.section_id == section.id,
                InstructorResponse.week_id == week.week_id,
            )
            .limit(1)
        ).first()
        if answered is None:
            return course_week
    raise StoryRefusedError(
        f"Course weeks {list(EXIT_WEEK_CANDIDATES)} of {SECTION_LABEL} each hold a response from "
        "staff, which the response table keeps for good, so no week is left for the exit story. "
        "Run it on a fresh stack."
    )


def the_instrument(session: Session) -> dict[int, UUID]:
    """SPEC §3.2's five questions of the set in force, by position, shape-checked."""
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


def the_classmates(session: Session, section: Section) -> dict[str, UUID]:
    """The classmates' `user` rows, found through their enrollments in this section."""
    found: dict[str, UUID] = {}
    for user_id in session.scalars(
        select(Enrollment.user_id).where(Enrollment.section_id == section.id)
    ):
        subject = subject_for_user(session, user_id)
        if subject in CLASSMATES:
            found[subject] = user_id
    missing = [subject for subject in CLASSMATES if subject not in found]
    if missing:
        raise StoryRefusedError(
            f"These classmates hold no enrollment in {SECTION_LABEL}: {missing}. The roster sync "
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
            first_submitted_at=week.submitted_at,
            last_submitted_at=week.submitted_at,
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
    comment_text: str | None = None,
    workload_hours: Decimal | None = None,
) -> Answer:
    """One answer, matched on `(response_id, question_id)` or inserted, every value column set."""
    answer = session.scalars(
        select(Answer).where(Answer.response_id == response.id, Answer.question_id == question_id)
    ).one_or_none()
    if answer is None:
        answer = Answer(response_id=response.id, question_id=question_id)
        session.add(answer)
    answer.rating = rating
    answer.comment_text = comment_text
    answer.workload_hours = workload_hours
    session.flush()
    return answer


def write_the_weeks(
    session: Session,
    *,
    section: Section,
    weeks: Sequence[WeekOfTheSection],
    questions: Mapping[int, UUID],
    classmates: Mapping[str, UUID],
) -> tuple[int, int]:
    """Write `STORY` into `weeks` (one per story week, in order); answer responses and comments."""
    responses = comments = 0
    for week, plan in zip(weeks, STORY, strict=True):
        for seat, subject in enumerate(plan.respondents):
            response = one_response(
                session, section=section, week=week, user_id=classmates[subject]
            )
            one_answer(
                session,
                response=response,
                question_id=questions[INSTRUCTOR_RATING],
                rating=plan.instructor_ratings[seat],
            )
            one_answer(
                session,
                response=response,
                question_id=questions[COURSE_RATING],
                rating=plan.course_ratings[seat],
            )
            one_answer(
                session,
                response=response,
                question_id=questions[WORKLOAD],
                workload_hours=Decimal(plan.workload_hours[seat]),
            )
            written = {
                questions[INSTRUCTOR_COMMENT]: plan.instructor_comments.get(seat),
                questions[COURSE_COMMENT]: plan.course_comments.get(seat),
            }
            for question_id, text in written.items():
                if text is None:
                    continue
                answer = one_answer(
                    session, response=response, question_id=question_id, comment_text=text
                )
                record_verdict(
                    session,
                    CommentValidityOutput(
                        verdict=ValidityVerdict.SUBSTANTIVE,
                        prompt_version=SEED_PROMPT_VERSION,
                        model_id=NOT_A_MODEL,
                    ),
                    answer_id=answer.id,
                )
                comments += 1
            recompute_response_validity(session, response)
            responses += 1
    return responses, comments


def write_the_story(session: Session) -> StoryWritten:
    """Choose the exit week, write both weeks, and answer what was written."""
    section = the_section(session)
    exit_week = the_exit_week(session, section)
    weeks = [the_week(session, section, exit_week + plan.offset) for plan in STORY]
    responses, comments = write_the_weeks(
        session,
        section=section,
        weeks=weeks,
        questions=the_instrument(session),
        classmates=the_classmates(session, section),
    )
    return StoryWritten(exit_week=exit_week, responses=responses, comments=comments)


def main() -> int:
    """Refuse outside development, write the story, and say in one line what it wrote."""
    if not is_development(Settings()):
        print(
            "seed_student_loop_exit_story refuses to run outside a development environment. "
            "See docs/adr/0063-the-demo-seed-runs-only-in-a-development-environment.md.",
            file=sys.stderr,
        )
        return 1
    with SessionLocal() as session:
        try:
            written = write_the_story(session)
        except StoryRefusedError as refusal:
            session.rollback()
            print(f"seed_student_loop_exit_story refused: {refusal}", file=sys.stderr)
            return 1
        session.commit()
    print(
        f"seed_student_loop_exit_story wrote {SECTION_LABEL}: exit week {written.exit_week}, "
        f"{written.responses} responses, {written.comments} comments."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
