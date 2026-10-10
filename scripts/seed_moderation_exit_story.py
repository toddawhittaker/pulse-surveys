"""E6's exit story for `BIOL-215-R3WW`: three late weeks of answers, written into a development stack.

SPEC §14.3's E6 exit: "the anti-cherry-picking trail is visible up-chain, and a
welfare-flagged comment in a 3-response week provably reaches Care with no trace
in the instructor view." `tests/e2e/exit-moderation.spec.ts` drives that clause,
and this file writes the answers it drives over. Course weeks 9 to 11, which no
other drive writes:

  - **Course week 9: three responses and no comment.** The week whose summary
    is the empty-week sentence, for the welfare week to be compared with.
  - **Course week 10: eight responses, comments shown in both streams.** Six
    students comment on the instructor and five on the course, so both streams
    clear SPEC §4's threshold of five. One instructor comment carries the mock
    provider's `harmful` marker, which the instructor keeps; another carries no
    marker, which the instructor excludes with a reason. This is the trail, and
    the canary week whose comments do show.
  - **Course week 11: three responses, one comment.** The comment carries the
    mock provider's `self-harm` marker.

**It writes no moderation verdict, no summary and no release.** Moderation is
the hourly sweep's (ADR 0188) and asks the mock provider, whose markers decide
the verdict; the summaries are the summary walk's. The drive runs both jobs
after it moves the clock past the close, so the routing to Care is the
product's own and not this file's (`docs/MISTAKES.md` entry 30).

**What this file shares with `scripts/seed_exit_story.py`, and why it is a
copy.** The section, the instrument, the respondents and the one-response and
one-answer writers are that file's shape in a smaller form. `scripts/` is not
in the `api` image, so each seeder is piped into `python -` whole and cannot
import the other. That file's docstring holds the long argument for each rule
kept here: it refuses outside development (ADR 0063), provisions nothing and
refuses loudly instead (`docs/MISTAKES.md` entry 48), sets `response.is_valid`
through `app.services.validity` (ADR 0147), and writes validity verdicts under a
pair the floored sweep does not hunt (ADR 0054).

**Idempotent by natural key.** A response is matched on `(user_id, section_id,
week_id)` and an answer on `(response_id, question_id)`. A response in these
three weeks that the plan does not describe is a refusal, because this
connection may not delete one: `clearTheWeek` in `tests/e2e/support/survey.ts`
clears the section, and the drive calls it before this runs.
"""

import sys
from collections.abc import Mapping
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
from app.models.org import Section
from app.models.survey import REPORT_STREAMS, Answer, Question, QuestionKind, QuestionSet, Response
from app.models.term import SurveyWindow, Term, Week
from app.services.identity import subject_for_user
from app.services.section_codes import week_of_the_term
from app.services.validity import recompute_response_validity, record_verdict

SECTION_CODE = "R3WW"
SECTION_LABEL = "BIOL-215-R3WW"

LEARNER = "mock-lms-user-learner"


def student(ordinal: int) -> str:
    """One of `BIOL-215-R3WW`'s per-section students, by the `sub` the platform sends."""
    return f"mock-lms-user-{SECTION_LABEL.lower()}-student-{ordinal:02d}"


# The section's stable day-one members, less ordinals 4 and 7, whom the mock
# platform adds late and drops (`scripts/seed_exit_story.py` says why).
THE_EIGHT = (
    LEARNER,
    student(1),
    student(2),
    student(3),
    student(5),
    student(6),
    student(8),
    student(9),
)
THE_THREE = THE_EIGHT[:3]

# The sentences, each over SPEC §3.3's twenty-five-character floor, holding no
# `|` (the separator the drive's database reads come back on), and distinct
# inside their first forty characters. The drive transcribes the four it asserts.
#
# The two the instructor decides on, in course week 10's instructor stream.
EXCLUDED_WITH_A_REASON = (
    "Moderation exit unflagged: the instructor mentioned a classmate's grade aloud in lab."
)
FLAGGED_AND_KEPT = (
    "Moderation exit flagged: the lectures are a waste of everybody's time this term. "
    "mock-ai:harmful"
)
# The welfare comment, course week 11's course stream, and its only comment.
WELFARE_COMMENT = (
    "Moderation exit welfare: I do not see the point of going on with any of this anymore. "
    "mock-ai:self-harm"
)
# Course week 10's other voices: plain, unmarked, and shown.
INSTRUCTOR_VOICES = (
    "Moderation exit voice two, instructor: the worked examples were easy to follow.",
    "Moderation exit voice three, instructor: questions in class got clear answers.",
    "Moderation exit voice four, instructor: the pace felt right for the material.",
    "Moderation exit voice five, instructor: the feedback on the quiz was specific.",
)
COURSE_VOICES = (
    "Moderation exit voice one, course: the lab manual matched the lecture this week.",
    "Moderation exit voice two, course: the reading was manageable beside other work.",
    "Moderation exit voice three, course: the assignment matched what we practised.",
    "Moderation exit voice four, course: the module pages were easy to find my way in.",
    "Moderation exit voice five, course: the quiz covered what the week had promised.",
)

SEED_PROMPT_VERSION = "development-seed.moderation-exit-story"


@dataclass(frozen=True)
class StoryWeek:
    """One course week: who answers, their two ratings and workload, and who comments."""

    course_week: int
    respondents: tuple[str, ...]
    instructor_rating: int
    course_rating: int
    workload_hours: str
    instructor_comments: Mapping[int, str] = field(default_factory=dict)
    course_comments: Mapping[int, str] = field(default_factory=dict)


# Course weeks 9 and 11 carry the same ratings and workload, so the instructor
# reads two weeks that differ only in the comment nobody may see.
STORY: tuple[StoryWeek, ...] = (
    StoryWeek(
        course_week=9,
        respondents=THE_THREE,
        instructor_rating=4,
        course_rating=3,
        workload_hours="7",
    ),
    StoryWeek(
        course_week=10,
        respondents=THE_EIGHT,
        instructor_rating=4,
        course_rating=4,
        workload_hours="8",
        instructor_comments={
            0: EXCLUDED_WITH_A_REASON,
            1: FLAGGED_AND_KEPT,
            **dict(enumerate(INSTRUCTOR_VOICES, start=2)),
        },
        course_comments=dict(enumerate(COURSE_VOICES)),
    ),
    StoryWeek(
        course_week=11,
        respondents=THE_THREE,
        instructor_rating=4,
        course_rating=3,
        workload_hours="7",
        course_comments={0: WELFARE_COMMENT},
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

    week_id: UUID
    submitted_at: datetime


def the_section(session: Session) -> Section:
    """The one `section` row `BIOL-215-R3WW` reached this database as."""
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
    for plan in STORY:
        term_week = week_of_the_term(
            plan.course_week, section_start=section.start_date, term_start=term.start_date
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
                f"Course week {plan.course_week} of {SECTION_LABEL} (term week {term_week}) has no "
                "`week` row or no `survey_window`. `derive_survey_windows` writes the windows "
                "after a launch; this file creates neither."
            )
        weeks.append(WeekOfTheSection(week_id=week_id, submitted_at=opens_at))
    return tuple(weeks)


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


def the_respondents(session: Session, section: Section) -> dict[str, UUID]:
    """The respondents' `user` rows, found through their enrollments in this section."""
    found: dict[str, UUID] = {}
    for user_id in session.scalars(
        select(Enrollment.user_id).where(Enrollment.section_id == section.id)
    ):
        subject = subject_for_user(session, user_id)
        if subject in THE_EIGHT:
            found[subject] = user_id
    missing = [subject for subject in THE_EIGHT if subject not in found]
    if missing:
        raise StoryRefusedError(
            f"These respondents hold no enrollment in {SECTION_LABEL}: {missing}. The roster sync "
            "enrols them (SPEC §7.3); this file creates no user and no enrollment."
        )
    return found


def refuse_a_foreign_response(
    session: Session,
    section: Section,
    weeks: tuple[WeekOfTheSection, ...],
    respondents: Mapping[str, UUID],
) -> None:
    """Refuse if these three weeks hold a response the plan does not describe."""
    planned = {
        (respondents[subject], week.week_id)
        for week, plan in zip(weeks, STORY, strict=True)
        for subject in plan.respondents
    }
    foreign = [
        key
        for key in session.execute(
            select(Response.user_id, Response.week_id).where(
                Response.section_id == section.id,
                Response.week_id.in_([week.week_id for week in weeks]),
            )
        )
        if tuple(key) not in planned
    ]
    if foreign:
        raise StoryRefusedError(
            f"Course weeks 9 to 11 of {SECTION_LABEL} hold {len(foreign)} response(s) this story "
            "does not describe, and this connection may not delete a response. Clear the section "
            "first: `clearTheWeek` in `tests/e2e/support/survey.ts`."
        )


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


def write_the_story(session: Session) -> int:
    """Write the plan into `BIOL-215-R3WW`, and answer how many comments it wrote."""
    section = the_section(session)
    weeks = the_weeks(session, section)
    questions = the_instrument(session)
    respondents = the_respondents(session, section)
    refuse_a_foreign_response(session, section, weeks, respondents)

    comments = 0
    for week, plan in zip(weeks, STORY, strict=True):
        for seat, subject in enumerate(plan.respondents):
            response = one_response(
                session, section=section, week=week, user_id=respondents[subject]
            )
            one_answer(
                session,
                response=response,
                question_id=questions[INSTRUCTOR_RATING],
                rating=plan.instructor_rating,
            )
            one_answer(
                session,
                response=response,
                question_id=questions[COURSE_RATING],
                rating=plan.course_rating,
            )
            one_answer(
                session,
                response=response,
                question_id=questions[WORKLOAD],
                workload_hours=Decimal(plan.workload_hours),
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
    return comments


def main() -> int:
    """Refuse outside development, write the story, and say in one line what it wrote."""
    if not is_development(Settings()):
        print(
            "seed_moderation_exit_story refuses to run outside a development environment. See "
            "docs/adr/0063-the-demo-seed-runs-only-in-a-development-environment.md.",
            file=sys.stderr,
        )
        return 1
    with SessionLocal() as session:
        try:
            comments = write_the_story(session)
        except StoryRefusedError as refusal:
            session.rollback()
            print(f"seed_moderation_exit_story refused: {refusal}", file=sys.stderr)
            return 1
        session.commit()
    print(
        f"seed_moderation_exit_story wrote {SECTION_LABEL}: {comments} comments across course "
        f"weeks {STORY[0].course_week} to {STORY[-1].course_week}. No moderation verdict, "
        "summary or release: those are the jobs'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
