"""The student-loop exit story, read back through the student's own results read.

`tests/e2e/exit-student-loop.spec.ts` drives SPEC §14.3's E8 exit over the world
`scripts/seed_student_loop_exit_story.py` writes, and asserts what the page
shows: in the exit week, both streams' distributions, the workload median, the
instructor stream's comments and the course stream held; in the week before, both
streams' ratings held. Those are claims about what the seeded rows add up to under
SPEC §4's threshold, so this module checks them where they are decided, through
`student_results.student_week_results` (the read behind the results route), and
never through the seeder's own count (`docs/MISTAKES.md` entry 58).

**The world is a launched `MATH-140-E1FF`, planted** as the staff launch and
the roster sync would have left it (`plant_one_launch`): the section in Fall
2026, a window per course week and five classmates enrolled from the first day.
The seeder is then run as its runbook runs it, piped into `python -`. Only the
moderation verdicts are routed here, through the product's writer, as the
drive's sweep would route them; the mock provider's verdict on these unmarked
sentences is `clear`.

**The learner is not in this world.** On the stack she adds a sixth answer to the
exit week; the seeder's plan already clears the threshold in each stream it
means to show without her and stays below it in each stream it means to hold, so
the read here is the read she gets less her own answer.

**The dates are the seeded calendar's.** `MATH-140-E1FF` ran from 2026-08-17 for
six weeks, so every week is past and published by the real clock, whenever this
runs. No policy is set, so each week is `unanswered` and shows its figures.
"""

import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import pytest
from fixtures.benchmark_history import (
    DEVELOPMENT_ENVIRONMENT,
    ENVIRONMENT_VARIABLE,
    fall_2026,
    plant_one_launch,
)
from fixtures.repo import REPO_ROOT
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

SEEDER = REPO_ROOT / "scripts" / "seed_student_loop_exit_story.py"
LABEL = "MATH-140-E1FF"
CLASSMATES = 5
SEEDER_TIMEOUT_SECONDS = 120

# The seeder's words, transcribed (`docs/MISTAKES.md` entry 19).
INSTRUCTOR_VOICES = {
    "Student loop voice one: the worked examples made the factoring steps clear.",
    "Student loop voice two: questions in class got patient and complete answers.",
    "Student loop voice three: the review at the start of class helped me catch up.",
    "Student loop voice four: office hours were easy to find and worth the trip.",
    "Student loop voice five: the instructor explained why each method works.",
}
EXIT_WEEK = 5
PRINTED = "exit week 5, 8 responses, 9 comments."


@contextmanager
def the_environment_of(demo: Any) -> Iterator[None]:
    """This process's environment, for the duration, as the seeded database's own."""
    with pytest.MonkeyPatch.context() as patch:
        for name, value in demo.environment.items():
            patch.setenv(name, value)
        yield


def run_the_seeder(demo: Any) -> subprocess.CompletedProcess[str]:
    """Pipe the seeder into an interpreter against `demo`'s database, as the runbook does."""
    # S603: the command is this interpreter, and the program arrives on standard
    # input from a path built out of the repository root.
    return subprocess.run(  # noqa: S603
        [sys.executable, "-"],
        input=SEEDER.read_text(encoding="utf-8"),
        cwd=REPO_ROOT,
        env={**os.environ, **demo.environment, ENVIRONMENT_VARIABLE: DEVELOPMENT_ENVIRONMENT},
        capture_output=True,
        text=True,
        timeout=SEEDER_TIMEOUT_SECONDS,
        check=False,
    )


@pytest.fixture(scope="module")
def story(
    demo_databases: Callable[[], Any], plant_in: Any, metadata_tables: dict[str, Any]
) -> dict[str, Any]:
    """The launched section, the seeder's run over it, and its two weeks as a classmate reads them."""
    demo = demo_databases()
    seeded = demo.run()
    if not seeded.succeeded:
        return {"problem": f"`scripts/seed.py` failed:\n{seeded.report()}"}
    launch = plant_one_launch(
        demo,
        plant_in,
        metadata_tables,
        fall_2026(demo, metadata_tables, seeded),
        LABEL,
        students=CLASSMATES,
    )
    ran = run_the_seeder(demo)
    if ran.returncode != 0:
        return {"problem": f"The seeder refused.\n{ran.stdout}\n{ran.stderr}"}

    with the_environment_of(demo):
        from app.ai.contracts import ModerationVerdict
        from app.config import Settings
        from app.services.moderation import SEED_MODEL_ID, SEED_PROMPT_VERSION, route_verdict
        from app.services.student_results import student_week_results

        engine = create_engine(demo.database.application_url)
        try:
            with Session(engine) as session:
                comments = session.execute(
                    text(
                        "select a.id from answer a join response r on r.id = a.response_id "
                        "where r.section_id = :section and a.comment_text is not null"
                    ),
                    {"section": launch.section_id},
                ).scalars()
                for answer_id in list(comments):
                    route_verdict(
                        session,
                        answer_id,
                        ModerationVerdict.CLEAR,
                        prompt_version=SEED_PROMPT_VERSION,
                        model_id=SEED_MODEL_ID,
                    )
                session.commit()

                settings = Settings()
                classmate = UUID(str(launch.students[0]["id"]))
                weeks = {
                    course_week: student_week_results(
                        session,
                        user_id=classmate,
                        section_id=UUID(str(launch.section_id)),
                        course_week=course_week,
                        settings=settings,
                    )
                    for course_week in (EXIT_WEEK - 1, EXIT_WEEK)
                }
        finally:
            engine.dispose()
    return {"problem": None, "printed": ran.stdout, "weeks": weeks}


def test_the_exit_week_shows_the_instructor_stream_and_holds_the_course_streams_comments_and_the_week_before_holds_its_ratings(
    story: dict[str, Any],
) -> None:
    if story["problem"] is not None:
        pytest.fail(story["problem"])
    assert PRINTED in story["printed"], f"The seeder printed {story['printed']!r}."

    exit_week = story["weeks"][EXIT_WEEK]
    streams = {stream.stream: stream for stream in exit_week.streams}
    instructor, course = streams["instructor"], streams["course"]
    assert instructor.shares is not None and sum(instructor.shares.values()) == 100, (
        f"The exit week's instructor ratings read {instructor.shares!r}: five classmates rated, "
        "so the distribution shows, in shares summing to 100."
    )
    assert course.shares is not None and sum(course.shares.values()) == 100
    assert [
        point.mean is not None for point in instructor.trend if point.course_week == EXIT_WEEK
    ] == [True]
    # The five classmates' hours are 6, 7, 5, 8 and 6.
    assert exit_week.workload_median == 6.0
    assert not instructor.small_n
    assert {comment.text for comment in instructor.comments} == INSTRUCTOR_VOICES
    assert course.small_n, "One classmate commented on the course, so that stream is held."
    assert course.comments == []

    earlier = story["weeks"][EXIT_WEEK - 1]
    earlier_streams = {stream.stream: stream for stream in earlier.streams}
    for name, stream in earlier_streams.items():
        assert stream.shares is None, (
            f"The week before reads {name} shares {stream.shares!r}: three classmates rated, "
            "below the threshold, so the student sees the ratings held."
        )
        assert [point.mean for point in stream.trend if point.course_week == EXIT_WEEK - 1] == [
            None
        ]
    assert earlier.workload_median is None
    assert earlier_streams["course"].small_n and earlier_streams["course"].comments == []
