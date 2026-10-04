"""`enrollment_windows.live_on` and the landing rule answer the same on every boundary day.

Two places decide whether an enrolment is live on a day. `app.services.authz`
writes it in SQL for the landing decision, and `app.services.enrollment_windows.
live_on` is the expression every other service reads. A copy that drifts is one
rule meaning two things, so this holds the two side by side on each side of each
bound: the first day, the day before it, the last day, the day after it, and an
open end.

Each case also asserts the expected answer, not only agreement: two predicates
that are both wrong agree (`docs/MISTAKES.md` entry 19). The expected answers are
ADR 0020's `'[]'` convention, inclusive at both ends, with a `NULL` end open.
"""

from datetime import date, timedelta
from typing import Any

import pytest
from fixtures.grading import GradingWorld
from sqlalchemy import exists, select

from app.models.identity import Enrollment
from app.services.authz import _A_LIVE_ENROLLMENT
from app.services.enrollment_windows import live_on

pytestmark = pytest.mark.integration

# The day each case is asked about. Inside the Fall 2026 term the world is built
# over, so nothing about the term itself could make an answer false.
DAY = date(2026, 9, 15)

# (subject, started_on, ended_on, live on DAY)
CASES = [
    ("starts-on-the-day", DAY, None, True),
    ("starts-the-day-after", DAY + timedelta(days=1), None, False),
    ("ends-on-the-day", DAY - timedelta(days=10), DAY, True),
    ("ended-the-day-before", DAY - timedelta(days=10), DAY - timedelta(days=1), False),
    ("open-ended", DAY - timedelta(days=10), None, True),
]


def landing_answer(session: Any, user_id: Any) -> bool:
    return bool(session.execute(_A_LIVE_ENROLLMENT, {"user_id": user_id, "today": DAY}).scalar())


def live_on_answer(session: Any, user_id: Any) -> bool:
    return bool(session.scalar(select(exists().where(Enrollment.user_id == user_id, live_on(DAY)))))


@pytest.mark.parametrize(
    ("subject", "started_on", "ended_on", "expected"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_live_on_and_the_landing_rule_give_the_expected_answer(
    grading_world: GradingWorld,
    subject: str,
    started_on: date,
    ended_on: date | None,
    expected: bool,
) -> None:
    world = grading_world.build()
    student = world.student(subject, started_on=started_on, ended_on=ended_on)

    landing = landing_answer(world.session, student.user_id)
    shared = live_on_answer(world.session, student.user_id)

    assert landing is expected, (
        f"The landing rule says {landing} for an enrolment from {started_on} to {ended_on} "
        f"asked on {DAY}; ADR 0020's inclusive window says {expected}."
    )
    assert shared is expected, (
        f"`live_on` says {shared} for an enrolment from {started_on} to {ended_on} asked on "
        f"{DAY}; ADR 0020's inclusive window says {expected}, and the landing rule says {landing}."
    )
