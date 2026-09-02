"""E2-08 criterion 3 — the race, with the constraint seen refusing.

> A second submission racing the first cannot produce two responses for one
> (student, section, week) — the constraint is seen refusing, not cited
> (MISTAKES entry 9).

`docs/MISTAKES.md` entry 9's rule is the whole design of this module: "Before
citing a guard, execute it against the case you claim it stops and the case you
claim it allows. A guard that has never been run is a comment." E2-05 built
`uq_response_user_id_section_id_week_id` and asserts it with two `INSERT`s;
what is unexecuted until here is the *submit path* meeting it — the branch where
a request has decided there is no response yet, has classified a comment, and
then finds that another request wrote one while it was doing so.

**The race window is opened deliberately rather than hoped for.** Both requests
carry the mock's stall selector, so each spends the classifier's whole budget
inside the handler; both have therefore looked for an existing response, found
none, and are on their way to inserting one before either has committed. Without
that the two requests serialise, the second is an ordinary in-window
resubmission, and the constraint is never asked anything — which is why the
overlap is **asserted** rather than assumed. A run where they did not overlap
fails here saying so, instead of passing and reporting that a guard held.

**Two clients rather than two threads on one**, because a submission is a whole
request and the point is two of them in flight; the two are built from one
application factory against one database, which is the shape a second uvicorn
worker has.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, NamedTuple

import pytest
from fixtures.submit import (
    SECTION_TABLE,
    SUBSTANTIVE_COMMENT,
    USER_TABLE,
    SubmitWorld,
    a_valid_submission,
    copy_texts,
)

pytestmark = pytest.mark.integration

# How long a worker waits for its partner at the barrier before giving up. Long
# enough that a slow container start is not what fails this, short enough that a
# partner which never arrives is a failure rather than a hung suite.
BARRIER_TIMEOUT_SECONDS = 30


class Attempt(NamedTuple):
    """One submission, with the wall-clock interval it occupied."""

    status: int
    body: str
    started: float
    finished: float


def test_two_submissions_in_flight_leave_one_response_and_one_refusal(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    submit_contract: Any,
) -> None:
    """Two requests for one (student, section, week) produce one response, and one 409.

    **The constraint is seen refusing.** One of the two requests reaches its
    insert after the other has committed, and E2-05's uniqueness rule is what
    stops it; the handler turns that into the duplicate refusal rather than into a
    5xx. Both halves are asserted, because they fail differently: an unhandled
    `IntegrityError` is a 500 with a stack trace where a student is standing, and
    a route that swallows it is a submission silently lost.

    **The accepted half is the other request**, in the same test — one of the two
    has to succeed, or "the constraint refused a duplicate" would be equally well
    explained by a route that refuses everything under load.

    **The mutation it kills:** the check-then-insert written without the
    constraint behind it, which under two concurrent requests writes two rows for
    one week — two votes in every §5 aggregate while §3.4's denominator stays at
    one — and the `IntegrityError` left to escape, which is the same defect
    wearing a 500.

    **What a red that names the overlap means:** the two requests serialised, so
    this test could not pose its question. That is a defect in this test's timing
    rather than in the path, and it is reported as itself rather than as a pass.
    """
    world = submit_world.build(opens_at=open_now[0], closes_at=open_now[1])
    first_client = open_submit_tool(ai_base_url=mock_ai_endpoint.base_url)
    second_client = open_submit_tool(ai_base_url=mock_ai_endpoint.base_url)
    students = [
        signed_in_student(first_client, world),
        signed_in_student(second_client, world),
    ]
    submission = a_valid_submission(comment=f"{SUBSTANTIVE_COMMENT} {mock_ai.marker_for('stall')}")
    barrier = threading.Barrier(len(students))

    def attempt(student: Any) -> Attempt:
        barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
        started = time.perf_counter()
        answered = student.submit(submission)
        return Attempt(answered.status_code, answered.text, started, time.perf_counter())

    with ThreadPoolExecutor(max_workers=len(students)) as pool:
        attempts = list(pool.map(attempt, students))

    overlapped = attempts[0].started < attempts[1].finished and (
        attempts[1].started < attempts[0].finished
    )
    assert overlapped, (
        f"The two submissions did not overlap: {attempts[0].started:.2f}-"
        f"{attempts[0].finished:.2f} against {attempts[1].started:.2f}-"
        f"{attempts[1].finished:.2f}. They serialised, so the second was an ordinary in-window "
        "resubmission and the uniqueness constraint was never asked anything. This test could not "
        "pose its question — which is a defect in its timing, not a guard that held."
    )

    statuses = sorted(attempt.status for attempt in attempts)
    server_errors = [attempt for attempt in attempts if attempt.status >= 500]
    assert not server_errors, (
        f"A racing submission answered {[a.status for a in server_errors]}: "
        f"{[a.body[:200] for a in server_errors]}. The uniqueness constraint refusing is a "
        "condition this path expects — the work order makes the handler 'turn it into the 409 "
        "duplicate refusal' — and an unhandled `IntegrityError` is a stack trace where a student "
        "is standing."
    )
    assert any(200 <= status < 300 for status in statuses), (
        f"Neither racing submission succeeded ({statuses}). One of the two has to store the "
        "response, or the refusal below says nothing about a duplicate."
    )
    assert submit_contract.conflict in statuses, (
        f"The two racing submissions answered {statuses}. One of them reached its insert after "
        "the other had committed, and E2-05's `(user, section, week)` uniqueness rule is what "
        f"stops it — the work order makes that a {submit_contract.conflict}."
    )

    student_id = world.student[world.key_of(USER_TABLE)]
    section_id = world.section[world.key_of(SECTION_TABLE)]
    week_id = world.week[world.key_of("week")]
    stored = [
        row
        for row in world.responses()
        if (row["user_id"], row["section_id"], row["week_id"]) == (student_id, section_id, week_id)
    ]
    assert len(stored) == 1, (
        f"Two racing submissions left {len(stored)} responses for one (student, section, week): "
        f"{stored}. SPEC §8 makes that triple unique, and two rows are two votes in every §5 "
        "aggregate while §3.4's participation denominator stays at one week."
    )

    refusal = next(attempt for attempt in attempts if attempt.status == submit_contract.conflict)
    published = sorted(key for key, text in copy_texts().items() if text and text in refusal.body)
    assert len(published) == 1, (
        f"The duplicate refusal served {refusal.body[:300]!r}, and {len(published)} of the copy "
        f"registry's strings appear in it ({published}). Criterion 4 covers this refusal as much "
        "as any other: it is a sentence a student reads, and E2-11's inventory reads the registry."
    )


def test_the_barrier_makes_two_threads_start_together() -> None:
    """The control on this module's own machinery (`docs/MISTAKES.md` entry 3).

    The overlap assertion above rests on two threads reaching the barrier and
    being released together. A barrier that let one through early — a wrong party
    count, a timeout swallowed — would make the test above report "they
    serialised" against a path that is perfectly concurrent, and a reader would
    spend the afternoon on the wrong module.

    **A red here means this module is broken, not the submit path.**
    """
    barrier = threading.Barrier(2)
    releases: list[float] = []

    def wait_and_stamp(delay: float) -> None:
        time.sleep(delay)
        barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
        releases.append(time.perf_counter())

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(wait_and_stamp, [0.0, 0.3]))

    assert len(releases) == 2, f"The barrier released {len(releases)} threads, not two."
    assert abs(releases[0] - releases[1]) < 0.2, (
        f"The two threads were released {abs(releases[0] - releases[1]):.2f}s apart, though one "
        "waited 0.3s longer than the other before arriving. A barrier that does not hold the "
        "early thread cannot open the race window the test above depends on."
    )
