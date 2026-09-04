"""E2-08 criterion 5 — the submission's time comes from the clock service.

> A dev-clock submission stores the clock service's time: an integration test
> sets the override, submits, and reads the row's timestamp back inside the
> pretend window — the criterion that makes the no-server-default rule in E2-05
> mean something.

E2-05 asserted the *absence* of a server default on `response.first_submitted_at`
and `response.last_submitted_at`, off `information_schema.columns`. That is a
statement about the schema and it is satisfied by a path that calls
`datetime.now(UTC)` itself, which is the same defect one layer up: SPEC §3.1 puts
every window at a wall-clock time in the institution's zone, ADR 0109 makes the
development clock a database offset that every scheduling read goes through, and
§3.4's score counts the items of the week a response is filed under. A submission
stamped from the process clock while the window was resolved from the moved one is
a row that disagrees with itself: its timestamp falls outside the very window
whose week its answers are credited to.

**Both directions of the line are here** (`docs/MISTAKES.md` entry 3). The clock
is moved thirty days forward in both tests and only the window moves with it: in
the first the window brackets the pretended instant and the submission is
accepted; in the second it brackets the real one and the submission is refused.
A path that ignores the override fails the first; a path that ignores the
window's real bounds fails the second; a path that reads real time for one
question and pretended time for the other fails one of them.

**The environment is `development` and it is stated** (ADR 0109 part 4, and
`docs/MISTAKES.md` entry 40): the override applies there and nowhere else, so in
any other environment the row these tests write is dead weight and the service
answers real time. `open_submit_tool` states it.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fixtures.submit import SUBSTANTIVE_COMMENT, SubmitWorld, a_valid_submission

pytestmark = pytest.mark.integration

# How far the pretended clock is moved. Far enough that no window instant this
# module writes can be mistaken for the other test's — a month apart is not a
# rounding, a leap second or a daylight-saving hour.
PRETEND_OFFSET = timedelta(days=30)

# How close a stored timestamp has to be to the pretended instant. ADR 0109 makes
# the effective now `real + (pretend_now - anchored_at)`, so it keeps moving while
# it is read; the gap between setting the override and the submit path reading it
# is a container round trip. Five minutes is far below the thirty-day offset this
# is distinguishing from and far above anything a slow request costs.
STAMP_TOLERANCE = timedelta(minutes=5)


def test_a_submission_made_under_a_moved_clock_is_stamped_with_the_pretended_time(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    committed_clock_overrides: Any,
) -> None:
    """The criterion as it is written: set the override, submit, read the row back.

    The window brackets the *pretended* instant and excludes the real one by
    twenty-nine days, so the submission is only accepted at all if the window was
    resolved through the clock. Then the stored `first_submitted_at` is required
    to sit inside that same window and within minutes of the pretended instant:
    "a dev-clock submission must be internally consistent with the window that
    accepted it, because E3's participation formula will read both".

    **Two assertions and neither is redundant.** Inside the window is the
    consistency the ticket asks for and is satisfied by any instant in a two-day
    span; close to the pretended instant is what distinguishes the clock service
    from an arbitrary value the path happened to write, and a row stamped from
    `datetime.now(UTC)` is twenty-nine days outside the window as well as thirty
    days from the pretence.

    **The mutation it kills:** `datetime.now(UTC)` at the submit path in place of
    `app.services.clock.now(session, settings=settings)`. E2-05's schema test
    cannot see it — there is no server default either way — and every other test
    in this ticket passes with it, because they all run under a clock that is not
    moved.
    """
    pretend_now = datetime.now(UTC) + PRETEND_OFFSET
    committed_clock_overrides.set(pretend_now=pretend_now, anchored_at=datetime.now(UTC))

    world = submit_world.build(
        opens_at=pretend_now - timedelta(days=1), closes_at=pretend_now + timedelta(days=1)
    )
    client = open_submit_tool(ai_base_url=mock_ai_endpoint.base_url)
    student = signed_in_student(client, world)

    answered = student.submit(
        a_valid_submission(comment=f"{SUBSTANTIVE_COMMENT} {mock_ai.marker_for('substantive')}")
    )

    assert 200 <= answered.status_code < 300, (
        f"A submission into a window that is open under the moved clock was answered "
        f"{answered.status_code}. The override was set thirty days forward and the window "
        f"brackets that instant, so a refusal means the window was resolved against real time — "
        f"ADR 0109 makes the override apply to every scheduling read. Body begins "
        f"{answered.text[:400]!r}."
    )
    responses = world.responses()
    assert len(responses) == 1, f"The submission left {len(responses)} responses: {responses}."
    stamped = responses[0]["first_submitted_at"]

    assert world.window["opens_at"] <= stamped <= world.window["closes_at"], (
        f"The response is stamped {stamped!r}, outside the window that accepted it "
        f"({world.window['opens_at']!r} to {world.window['closes_at']!r}). E3 reads a submission's "
        "time and the week it belongs to together; a row whose stamp falls outside its own window "
        "makes those two facts disagree."
    )
    assert abs(stamped - pretend_now) < STAMP_TOLERANCE, (
        f"The response is stamped {stamped!r} and the clock service was pretending it was "
        f"{pretend_now!r} — {abs(stamped - pretend_now)} apart. E2-05 leaves both submission "
        "timestamps without a server default precisely so this path writes them through "
        "`app.services.clock`, and a stamp taken from the process clock is the value that "
        "default would have written."
    )


def test_a_window_open_only_in_real_time_is_closed_under_the_moved_clock(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    committed_clock_overrides: Any,
    submit_contract: Any,
) -> None:
    """The other direction: the clock decides the window is shut, and the path agrees.

    Same override, same offset, and the window left around real time instead. A
    path that resolves the window from `datetime.now(UTC)` accepts this
    submission, which is exactly the state the test above cannot detect on its
    own — it would fail there and be "fixed" by stamping from the clock while the
    window still came from real time, and this half is what refuses that repair.

    **The mutation it kills:** the clock consulted for the timestamp and not for
    the window resolution, which lets a student submit into a week the moved
    clock says closed a month ago and stamps the row with a time inside a window
    that has already been reported on.
    """
    committed_clock_overrides.set(
        pretend_now=datetime.now(UTC) + PRETEND_OFFSET, anchored_at=datetime.now(UTC)
    )

    world = submit_world.build(opens_at=open_now[0], closes_at=open_now[1])
    client = open_submit_tool(ai_base_url=mock_ai_endpoint.base_url)
    student = signed_in_student(client, world)

    refused = student.submit(
        a_valid_submission(comment=f"{SUBSTANTIVE_COMMENT} {mock_ai.marker_for('substantive')}")
    )

    assert refused.status_code == submit_contract.conflict, (
        f"A submission into a window that closed twenty-nine days ago by the clock service's "
        f"reckoning was answered {refused.status_code} rather than {submit_contract.conflict}. "
        f"The window's instants are around real time and the override is thirty days ahead of it. "
        f"Body begins {refused.text[:400]!r}."
    )
    assert (
        world.responses() == []
    ), f"A submission the moved clock puts a month past its window stored {world.responses()}."


def test_the_override_this_module_writes_is_visible_to_another_connection(
    committed_clock_overrides: Any,
) -> None:
    """The control on this module's own machinery (`docs/MISTAKES.md` entry 3).

    Both tests above rest on a `clock_override` row the *application* can see, and
    the application opens its own connection out of `DATABASE_URL`. An override
    written inside an uncommitted transaction is invisible to it, and both tests
    would then be measuring real time under two different descriptions — the
    first failing for a reason that reads like a missing clock call, the second
    passing for a reason that has nothing to do with the clock.

    **A red here means this module is broken, not the submit path.**
    """
    pretend_now = datetime.now(UTC) + PRETEND_OFFSET
    committed_clock_overrides.set(pretend_now=pretend_now, anchored_at=datetime.now(UTC))

    rows = committed_clock_overrides.rows()
    assert len(rows) == 1, (
        f"`clock_override` holds {len(rows)} rows after one `set`: {rows}. E2-04 permits at most "
        "one, and a read that sees none is a read inside a transaction the write is not in."
    )
    assert abs(rows[0]["pretend_now"] - pretend_now) < timedelta(seconds=1), (
        f"The stored override reads {rows[0]['pretend_now']!r} and this test wrote "
        f"{pretend_now!r}. The two tests above compare a stored submission timestamp against the "
        "value written here, so a value that does not survive the round trip makes both of them "
        "comparisons against something else."
    )
