"""What a student's weekly survey looks like to them, right now — ticket E2-09.

E2-10's form asks one question — *for me, right now, what is there?* — and this
module answers the whole of it: which sections the reader is enrolled in today,
which of them has a survey open at this instant, the questions to answer, and
what the reader has already submitted for that week. The router above it does no
work of its own beyond turning this into a response (SPEC §13's thin routers).

**A module of its own, and §13's list names none that fits.**
`app.services.survey_windows` schedules windows and answers whether one is open;
`app.services.validity` is E2-07's gating and says so in its own first paragraph;
`app.services.authz` decides what a session may *act as*. Assembling one person's
own view is none of those, and putting it in any of them would make a service
about scheduling, or about gating, or about authorization, also the place a screen
is built.

## The one predicate this module exists to get right

SPEC §4.1 item 1: "Students never see comparables, benchmarks, university
averages, or **other sections** — in charts, text, tooltips, exports, or aria
labels." Every read below is filtered by the reader's own key, and there is no
parameter anywhere in this module by which a caller could name a section, a
course, a term or another person. The two filters that carry the whole rule are:

* the enrollment read, which is `enrollment.user_id = <the session's own user>`
  and a day inside `started_on`/`ended_on`; and
* the submission read, which is the reader **together with** the section and the
  week — E2-05's uniqueness key with nobody left out. A lookup over the section
  and the week alone returns a classmate's answers in a section of two, which is
  the mutation `test_a_classmates_submission_is_never_in_this_students_answer`
  is written against.

**This is a person reading themself, which is why no view stands between it and
the tables.** ADR 0001's identity separation constrains instructor and leadership
reads: a view selects the columns a staff caller may see and structurally cannot
reach a name. Nothing here reads another person's row at all, so a view over these
tables would select every column of its source and exist only to satisfy the shape
of the rule. What *does* stand between this module and the institution's data is
the grant: `pulse_app` holds `SELECT` and nothing else on the five relations this
adds, and the scoping is the two filters above.

## What decides "now"

`app.services.clock`, through `app.services.survey_windows.open_window_for_section`
and through `clock.today` for the enrollment day. Both readings move with the
development `clock_override` row (ADR 0109), which is what lets a developer walk
a section through a window opening and closing; neither reads the process clock,
because a window compared against real time answers the same thing however the
console is driven.

**The enrollment day is the institution's day**, never UTC's — SPEC §8 makes the
timezone a deployment setting and a boundary evaluated in UTC puts everybody
enrolled from tonight a calendar day out. `clock.today` is the one place that
conversion lives.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.identity import Enrollment
from app.models.org import Section
from app.models.survey import Answer, Question, QuestionSet, Response
from app.models.term import SurveyWindow, Term, Week
from app.schemas.student import (
    EnrolledSection,
    OpenSurvey,
    OwnSubmission,
    StudentSurveyView,
    SubmittedAnswer,
    SurveyQuestion,
)
from app.services import clock
from app.services.section_codes import week_of_the_term
from app.services.survey_windows import open_window_for_section

__all__ = ["survey_for_student"]


def survey_for_student(session: Session, *, user_id: UUID, settings: Settings) -> StudentSurveyView:
    """Everything the form needs for one reader, in one round trip.

    `user_id` is the `user` row the reader's own session carries — resolved at the
    door out of the verified launch (E1-12) and never taken from a request
    parameter, because a read path that accepted one would be a read path that can
    be asked about somebody else.

    A reader enrolled in nothing today gets an empty list rather than a refusal:
    somebody between terms is an ordinary state, and a refusal would tell them
    something went wrong.
    """
    today = clock.today(session, settings=settings)
    sections = [
        _section_view(session, section=section, term=term, user_id=user_id, settings=settings)
        for section, term in _live_enrollments(session, user_id=user_id, today=today)
    ]
    return StudentSurveyView(sections=sections)


def _live_enrollments(
    session: Session, *, user_id: UUID, today: date
) -> list[tuple[Section, Term]]:
    """The sections this reader is enrolled in on `today`, each with its term.

    **`user_id` is the whole of the scoping**, and it is written here once and
    plainly rather than assembled from anything a caller passed. Dropping it, or
    widening the join to the section's course or to the term, returns sections the
    reader is not in — which is SPEC §4.1 item 1's failure and the mutation the
    invariant suite kills.

    **The window is inclusive at both ends**, matching ADR 0020's `'[]'`
    convention and `app.services.authz`'s own reading of the same rule: somebody
    whose enrollment ends today is enrolled today, and a `NULL` `ended_on` is the
    open window a roster sync leaves on a member it is still seeing (ADR 0023).
    The `IS NULL` arm is what stops three-valued logic answering "unknown" for
    every current student.

    **The term is joined rather than fetched per section**, and the join is inner
    because `section.term_id` is `NOT NULL` behind a foreign key — the database is
    what makes "a section with no term" unrepresentable, so there is no row this
    quietly drops.

    Ordered by section code so two reads of an unchanged database answer
    byte-identically; the code is unique within a term and the row's own key
    breaks any tie across terms.
    """
    return list(
        session.execute(
            select(Section, Term)
            .join(Enrollment, Enrollment.section_id == Section.id)
            .join(Term, Term.id == Section.term_id)
            .where(
                Enrollment.user_id == user_id,
                Enrollment.started_on <= today,
                or_(Enrollment.ended_on.is_(None), Enrollment.ended_on >= today),
            )
            .order_by(Section.lms_section_code, Section.id)
        )
        .tuples()
        .all()
    )


def _section_view(
    session: Session, *, section: Section, term: Term, user_id: UUID, settings: Settings
) -> EnrolledSection:
    """One enrolled section, with its open survey if there is one.

    A section whose window has not opened, or has closed, is still reported: the
    enrollment does not come and go with the window, and a student whose survey is
    shut is owed "there is nothing to answer this minute" rather than an answer
    that leaves out the course they are in.
    """
    window = open_window_for_section(session, section, settings=settings)
    return EnrolledSection(
        section_id=section.id,
        section_code=section.lms_section_code,
        survey_is_open=window is not None,
        open_survey=(
            None
            if window is None
            else _open_survey(session, window=window, section=section, term=term, user_id=user_id)
        ),
    )


def _open_survey(
    session: Session, *, window: SurveyWindow, section: Section, term: Term, user_id: UUID
) -> OpenSurvey:
    """The open window, the questions to answer, and this reader's own answers."""
    term_week = _term_week_of(session, window)
    question_set, questions = _current_question_set(session)
    return OpenSurvey(
        window_id=window.id,
        course_week=_course_week(term_week, section=section, term=term),
        term_week=term_week,
        opens_at=window.opens_at,
        closes_at=window.closes_at,
        question_set_version=question_set.version,
        questions=[
            SurveyQuestion(
                id=question.id,
                position=question.position,
                kind=question.kind,
                name=question.name,
                prompt=question.prompt,
                required_if_position=question.required_if_position,
                required_if_at_most=question.required_if_at_most,
                minimum_value=question.minimum_value,
                maximum_value=question.maximum_value,
                step=question.step,
            )
            for question in questions
        ],
        submission=_own_submission(session, window=window, section=section, user_id=user_id),
    )


def _term_week_of(session: Session, window: SurveyWindow) -> int:
    """Which week of the term this window is over, out of the week row itself.

    Read rather than derived. The window names its week, the week carries the
    number, and re-computing it from the window's instants would be a second
    reading of SPEC §3.1's rhythm that agrees with the first only while both are
    right.
    """
    week = session.get(Week, window.week_id)
    if week is None:  # pragma: no cover - a foreign key makes this unreachable
        raise RuntimeError(
            f"Survey window {window.id} names week {window.week_id}, which does not exist. A "
            "window's week is a foreign key, so this is a database that has lost a row rather "
            "than a state this read path can answer around."
        )
    return week.number


def _course_week(term_week: int, *, section: Section, term: Term) -> int:
    """Which week of its own run the section is in, when the term is in `term_week`.

    SPEC §2.2's two axes, read backwards. `week_of_the_term` is the one place the
    mapping between them is computed, so the section's first course week is asked
    of it rather than derived here, and this subtracts: a section whose first week
    is the term's fourth is in its tenth week when the term is in its thirteenth.

    Course weeks count from 1, so the section's own first week is course week 1
    and not 0 — the inclusive `+ 1` §2.2 numbers a course week by, and the
    off-by-one this reads as arithmetic rather than as a magic number.
    """
    first_term_week = week_of_the_term(
        1, section_start=section.start_date, term_start=term.start_date
    )
    return term_week - first_term_week + 1


def _current_question_set(session: Session) -> tuple[QuestionSet, list[Question]]:
    """The question set a form is answered with today, and its questions in order.

    The highest version there is. SPEC §3.2 ships one — "the five questions
    (standardized, v1 fixed)" — and versioning is what a later edit gets; which
    version an *already submitted* week is read back against is a question E2-09
    leaves open and E8's results view will have to settle.

    A deployment with no question set at all cannot render a form, so this refuses
    loudly rather than answering an open window with nothing in it: a survey that
    silently offers no questions looks to a student like a product that is broken
    and to a log like nothing at all.
    """
    question_set = session.scalars(select(QuestionSet).order_by(QuestionSet.version.desc())).first()
    if question_set is None:
        raise RuntimeError(
            "There is no question set in this database, so there is nothing for a student to "
            "answer. SPEC §3.2's v1 set is seeded by `scripts/seed.py`; a deployment without it "
            "has an open survey window and no survey."
        )
    questions = list(
        session.scalars(
            select(Question)
            .where(Question.question_set_id == question_set.id)
            .order_by(Question.position)
        )
    )
    return question_set, questions


def _own_submission(
    session: Session, *, window: SurveyWindow, section: Section, user_id: UUID
) -> OwnSubmission | None:
    """What this reader has already submitted for this section and week, or nothing.

    **Three columns in the key, and the reader is one of them.** E2-05 makes
    `response` unique on `(user_id, section_id, week_id)`; a lookup written over
    the section and the week alone is that key with the author left out, it reads
    perfectly, and in a section where somebody else has answered it returns their
    submission. SPEC §5.4 gives a student their own section and never another
    individual's raw data, so the author is in the `WHERE` clause and not in a
    later check.

    The answers come back in question order so a form renders them beside the
    questions it was handed, and all three value columns travel: a join that read
    one of them would blank a field the student had filled in, and the resubmit
    would then overwrite what they wrote with nothing.
    """
    response = session.scalars(
        select(Response).where(
            Response.user_id == user_id,
            Response.section_id == section.id,
            Response.week_id == window.week_id,
        )
    ).first()
    if response is None:
        return None
    answers = session.execute(
        select(Answer)
        .join(Question, Question.id == Answer.question_id)
        .where(Answer.response_id == response.id)
        .order_by(Question.position)
    ).scalars()
    return OwnSubmission(
        first_submitted_at=response.first_submitted_at,
        last_submitted_at=response.last_submitted_at,
        answers=[
            SubmittedAnswer(
                question_id=answer.question_id,
                rating=answer.rating,
                comment_text=answer.comment_text,
                workload_hours=answer.workload_hours,
            )
            for answer in answers
        ],
    )
