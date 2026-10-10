"""A moderation verdict is routed only once its comment's window has closed — E6-01, fix round.

**The finding (privacy-authz, MEDIUM).** E6-01's "holds a verdict" rule keys on
the answer id, and ADR 0115 revises an answer *in place* when a student
resubmits. A verdict written while the window is still open therefore vouches for
text the student can still replace: `clear` routed on Friday, a self-harm
disclosure resubmitted on Sunday into the same row, and the view shows the new
text as moderated while no `threat_case` is ever opened for it.

**The settled fix.** `app.services.moderation.route_verdict` refuses an answer
whose survey window has not closed by the app clock (`app.services.clock.now()`
against the window's `closes_at`, ADR 0109). It raises `ModerationBeforeClose`, a
`ValueError` subclass defined in that module, and writes nothing — no
classification row and no route. `now == closes_at` counts as closed.

**How the clock is stood exactly on a boundary.** ADR 0109's development override
is an offset, so it keeps moving while it is read and no override can land on an
instant. The two tests that need an exact instant replace the clock service's
`now` — on `app.services.clock` and, where `route_verdict`'s module bound the name
itself (`from app.services.clock import now`), on that module too — with a
function answering the instant chosen. That is the seam the settled fix names
("judged by the app clock"); a `route_verdict` that read the system clock instead
would not see it and is one of the mutations below. The first test needs no
seam: a window that closes in 2099 is open by any clock.

**Every refusal is asserted on the rows as well as on the exception.** A body
that wrote the verdict and then raised would satisfy `pytest.raises` alone; the
verdict, the flag and the case are each read back on the same session afterwards.

**Which failure a red is, before the fix lands.** `ModerationBeforeClose` is
looked up in the test body and fails naming the module when absent
(`docs/MISTAKES.md` entry 44).
"""

from datetime import timedelta
from typing import Any

import pytest
from fixtures.moderation import (
    CLEAR,
    HARMFUL,
    MODERATION_BEFORE_CLOSE,
    THREAT,
    UNMODERATED,
    moderation_service,
    moderation_states,
    moderation_verdicts,
    named_in_moderation,
    plant_verdict,
    threat_cases,
)
from fixtures.report_comments import CommentWorld
from fixtures.report_views import INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

A_CLOSED_WEEK = 7
AN_OPEN_WEEK = 8
CLOCK_MODULE = "app.services.clock"

AN_HOUR = timedelta(hours=1)
# The smallest step a `timestamptz` holds.
ONE_TICK = timedelta(microseconds=1)


def the_refusal() -> type[BaseException]:
    """`ModerationBeforeClose`, or a failure naming what owes it."""
    refusal = named_in_moderation(MODERATION_BEFORE_CLOSE)
    assert isinstance(refusal, type) and issubclass(refusal, ValueError), (
        f"`{MODERATION_BEFORE_CLOSE}` is {refusal!r}; the fix round settles a `ValueError` subclass "
        "raised by `route_verdict` for a window that has not closed."
    )
    return refusal


def a_comment_in(world: CommentWorld, week: int, text: str) -> Any:
    """One comment in one week, holding no verdict, and its answer key."""
    _, written = world.submit(
        term_week=week,
        comments={INSTRUCTOR_STREAM: text},
        moderation={INSTRUCTOR_STREAM: UNMODERATED},
    )
    return world.answer_key(written[INSTRUCTOR_STREAM])


def nothing_was_written(world: CommentWorld, answer_id: Any) -> dict[str, list[Any]]:
    """Every row a routing call could have left for one answer, read on the world's session."""
    return {
        "verdicts": moderation_verdicts(world.session, answer_id),
        "states": moderation_states(world.session, answer_id),
        "cases": threat_cases(world.session, answer_id),
    }


def stand_the_clock_at(monkeypatch: pytest.MonkeyPatch, instant: Any) -> None:
    """Make the app clock answer `instant`, wherever `route_verdict` asks it from."""
    from importlib import import_module

    def fixed(*_args: Any, **_kwargs: Any) -> Any:
        return instant

    monkeypatch.setattr(import_module(CLOCK_MODULE), "now", fixed)
    monkeypatch.setattr(moderation_service(), "now", fixed, raising=False)


@pytest.mark.parametrize("verdict", [HARMFUL, THREAT], ids=["flag-route", "care-route"])
def test_a_verdict_for_a_comment_whose_window_is_still_open_is_refused_and_writes_nothing(
    verdict: str, comment_world: CommentWorld
) -> None:
    """The pair, under the real clock: a window open until 2099 is refused, one closed in 2020 is not.

    Two comments in one section, written identically, routed the same verdict. The
    one in a week whose window closes in 2099 is refused with
    `ModerationBeforeClose`, and afterwards it holds no `MODERATION` row, no
    `moderation_state` row and no `threat_case`. The one in a week closed in 2020 is
    routed: its verdict and its route are there (the control — the refusal is about
    the window, not about a call that can never succeed).

    A case per route, because "writes nothing" is a claim about each table the call
    could have written: `harmful` would leave a flag, `threat` a case.

    **The mutations this kills:** no check at all (the open comment is routed); a
    check that writes the verdict, or its route, before raising (rows are left
    behind); a check that compares against the window's `opens_at` (open since
    2020, so routed).
    """
    refusal = the_refusal()
    world = comment_world
    world.build()
    world.close_week(A_CLOSED_WEEK)
    world.open_week(AN_OPEN_WEEK)
    closed = a_comment_in(world, A_CLOSED_WEEK, "e6-01 a comment whose window has closed")
    still_open = a_comment_in(world, AN_OPEN_WEEK, "e6-01 a comment whose window is still open")

    with pytest.raises(refusal):
        plant_verdict(world.session, still_open, verdict)
    left = nothing_was_written(world, still_open)
    assert left == {"verdicts": [], "states": [], "cases": []}, (
        f"`route_verdict` refused a comment whose window closes in 2099 and left {left}. A refusal "
        "writes nothing: a verdict left behind vouches for text the student can still replace "
        "(ADR 0115), and a route left behind is a flag or a case no verdict opened."
    )

    plant_verdict(world.session, closed, verdict)
    routed = nothing_was_written(world, closed)
    assert [row["verdict"] for row in routed["verdicts"]] == [verdict], (
        f"The comment whose window closed in 2020 was not routed: {routed}. Until it is, the "
        "refusal above may be a call that refuses everything."
    )
    assert (
        routed["states"] if verdict == HARMFUL else routed["cases"]
    ), f"The closed comment's {verdict!r} verdict landed with no route: {routed}."


def test_the_same_comment_is_refused_before_its_close_and_routed_after_it(
    comment_world: CommentWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One comment, two clocks: an hour before its window closes, then an hour after.

    The same answer is routed `threat` twice, with only the app clock moved between
    the calls. Before the close: refused, nothing written. After it: routed, with
    its case.

    **The mutations this kills:** `route_verdict` reading the system clock rather
    than `app.services.clock` (the window closed in 2020, so the first call is
    routed — ADR 0109 makes the app clock the one place this codebase asks the
    time, and the development clock is how every drive moves it); and the check
    removed.
    """
    refusal = the_refusal()
    world = comment_world
    world.build()
    world.close_week(A_CLOSED_WEEK)
    answer = a_comment_in(world, A_CLOSED_WEEK, "e6-01 routed either side of its close")
    closes_at = world.instants[A_CLOSED_WEEK][1]

    stand_the_clock_at(monkeypatch, closes_at - AN_HOUR)
    with pytest.raises(refusal):
        plant_verdict(world.session, answer, THREAT)
    assert nothing_was_written(world, answer) == {
        "verdicts": [],
        "states": [],
        "cases": [],
    }, "A refused call left rows behind."

    stand_the_clock_at(monkeypatch, closes_at + AN_HOUR)
    plant_verdict(world.session, answer, THREAT)
    after = nothing_was_written(world, answer)
    assert [row["verdict"] for row in after["verdicts"]] == [THREAT] and len(
        after["cases"]
    ) == 1, f"An hour after the window closed, the same comment was not routed: {after}."


def test_one_tick_before_the_close_is_refused_and_the_close_itself_is_accepted(
    comment_world: CommentWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The boundary, both sides: `now == closes_at` counts as closed (the fix round's ruling).

    Two comments in one closed week. With the app clock one microsecond before the
    window's `closes_at`, the first is refused and leaves nothing. With the clock
    at `closes_at` exactly, the second is routed.

    **The mutations this kills:** the comparison written `now <= closes_at` as
    "still open" (the second call is refused — SPEC §3.1 shuts the window at
    23:59:59, so its last instant is inside it and the next one is not, and the fix
    round settles the close itself as closed); and `now < closes_at - something`, a
    grace that lets the last microsecond of a window through (the first call is
    routed).
    """
    refusal = the_refusal()
    world = comment_world
    world.build()
    world.close_week(A_CLOSED_WEEK)
    before = a_comment_in(world, A_CLOSED_WEEK, "e6-01 a comment routed one tick before close")
    at_close = a_comment_in(world, A_CLOSED_WEEK, "e6-01 a comment routed at the close itself")
    closes_at = world.instants[A_CLOSED_WEEK][1]

    stand_the_clock_at(monkeypatch, closes_at - ONE_TICK)
    with pytest.raises(refusal):
        plant_verdict(world.session, before, CLEAR)
    assert (
        nothing_was_written(world, before)["verdicts"] == []
    ), "A call refused one microsecond before the close left a verdict behind."

    stand_the_clock_at(monkeypatch, closes_at)
    plant_verdict(world.session, at_close, CLEAR)
    assert [row["verdict"] for row in moderation_verdicts(world.session, at_close)] == [CLEAR], (
        "With the app clock at the window's `closes_at` exactly, the verdict was not routed. The "
        "fix round settles `now == closes_at` as closed."
    )
