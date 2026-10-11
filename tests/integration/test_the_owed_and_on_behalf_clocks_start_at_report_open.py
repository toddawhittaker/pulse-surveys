"""The owed and on-behalf clocks start at report open — E7-03, done-when 6 (SPEC §5.3, §5.6 rule 4).

> **The clocks start at report open (ruling 2).** Owed and on-behalf are each
> false one second before report open + 48h and + 96h, and true at it, with the
> clock pinned. An encouraged week and a published week are never owed.

Work order decision 3: `is_owed(session, *, section_id, course_week, now)` and
`on_behalf_open(...)` in `services/response_loop.py`, pure on read. They take
`now`, so every pair here stands on the second itself and nothing reads a moving
clock. Every instant is counted from course week 1's report opening, 2026-10-05
10:00 UTC, written by hand in `tests/fixtures/report_api.py` — never from today.

**Why the opening and not the window's close.** Course week 1's window closes six
hours before its report opens (Sunday 23:59:59 and Monday 06:00 in New York), so
a clock started at the close is true at `open + 48h - 1s`, which the first half of
each pair refuses.

**Which failure a red is, before E7-03 lands.** `the_predicate` fails naming
`is_owed` or `on_behalf_open`.
"""

from datetime import timedelta

import pytest
from fixtures.lead_review import SIBLING_COHORT
from fixtures.response_loop_doors import (
    IS_OWED,
    ON_BEHALF_AFTER,
    ON_BEHALF_OPEN,
    ON_BEHALF_WEEK,
    ONE_SECOND,
    OWED_AFTER,
    LoopWorld,
)
from fixtures.the_hold import FIRST_ROW_AFTER_OPENING, INSTRUCTOR, report_opens

pytestmark = pytest.mark.integration

CLOCKS = [(IS_OWED, OWED_AFTER), (ON_BEHALF_OPEN, ON_BEHALF_AFTER)]


@pytest.mark.parametrize(("predicate", "after"), CLOCKS)
def test_each_clock_is_false_one_second_before_its_edge_and_true_at_it(
    response_loop: LoopWorld, predicate: str, after: timedelta
) -> None:
    """Required, unanswered: false at `open + after - 1s`, true at `open + after`.

    **The mutations this kill:** the clock started at the window's close (true one
    second early); `>` for `>=` (false at the edge); 48 and 96 swapped (`is_owed`
    false at +48h, or `on_behalf_open` true at +48h — the cross-check below); the
    edge counted in the institution's local time with the offset dropped (four
    hours either way).
    """
    world = response_loop
    world.own_course_required()
    edge = report_opens(ON_BEHALF_WEEK) + after
    section = world.hold.taught

    before = world.predicate(
        predicate, section_id=section, course_week=ON_BEHALF_WEEK, now=edge - ONE_SECOND
    )
    at = world.predicate(predicate, section_id=section, course_week=ON_BEHALF_WEEK, now=edge)

    assert (before, at) == (False, True), (
        f"`{predicate}` answered {before} one second before report open + {after} and {at} at it. "
        "Done-when 6: false, then true."
    )


def test_between_the_edges_the_week_is_owed_and_on_behalf_is_still_shut(
    response_loop: LoopWorld,
) -> None:
    """At `open + 96h - 1s`: owed true, on-behalf false. At `open + 48h`: on-behalf false.

    **The mutations this kill:** one predicate implemented as the other; on-behalf
    opening with owed.
    """
    world = response_loop
    world.own_course_required()
    opens = report_opens(ON_BEHALF_WEEK)
    section = world.hold.taught

    def ask(name: str, offset: timedelta) -> bool:
        return world.predicate(
            name, section_id=section, course_week=ON_BEHALF_WEEK, now=opens + offset
        )

    assert ask(IS_OWED, ON_BEHALF_AFTER - ONE_SECOND) is True
    assert ask(ON_BEHALF_OPEN, ON_BEHALF_AFTER - ONE_SECOND) is False
    assert (
        ask(ON_BEHALF_OPEN, OWED_AFTER) is False
    ), "`on_behalf_open` is true at report open + 48h; SPEC §5.3: on-behalf enables at +96h."


def test_an_encouraged_week_is_never_owed_and_never_open_on_behalf(
    response_loop: LoopWorld,
) -> None:
    """The sibling course has no policy row: false at +96h and a week later; the own course, required, true.

    **The mutations this kill:** a predicate that ignores the policy (every
    unanswered week owed); a missing policy read as required. **The near miss:**
    the own course's required week at the same instant, true.
    """
    world = response_loop
    world.own_course_required()
    world.hold.windows_for(SIBLING_COHORT, ON_BEHALF_WEEK)
    opens = report_opens(ON_BEHALF_WEEK)
    encouraged = world.hold.sibling_course_section
    required = world.hold.taught

    for later in (ON_BEHALF_AFTER, ON_BEHALF_AFTER + timedelta(days=7)):
        for name in (IS_OWED, ON_BEHALF_OPEN):
            answered = world.predicate(
                name, section_id=encouraged, course_week=ON_BEHALF_WEEK, now=opens + later
            )
            assert answered is False, (
                f"`{name}` is true for an encouraged week at report open + {later}. Done-when 6: an "
                "encouraged week is never owed."
            )
    control = world.predicate(
        IS_OWED, section_id=required, course_week=ON_BEHALF_WEEK, now=opens + ON_BEHALF_AFTER
    )
    assert (
        control is True
    ), "The required week is not owed at +96h, so the false above is not the policy's doing."


def test_a_published_week_is_not_owed_from_the_moment_its_response_exists(
    response_loop: LoopWorld,
) -> None:
    """Owed at +96h; the teacher's response is planted; read again at the same instant: neither predicate.

    Entry 51's pair either side of the one change.

    **The mutations this kill:** a predicate that ignores the response (a published
    week still owed, still open on behalf); a response looked up in the wrong week.
    **The near miss:** the first read, owed and open.
    """
    world = response_loop
    world.own_course_required()
    now = report_opens(ON_BEHALF_WEEK) + ON_BEHALF_AFTER
    section = world.hold.taught

    def both() -> tuple[bool, bool]:
        return (
            world.predicate(IS_OWED, section_id=section, course_week=ON_BEHALF_WEEK, now=now),
            world.predicate(
                ON_BEHALF_OPEN, section_id=section, course_week=ON_BEHALF_WEEK, now=now
            ),
        )

    before = both()
    world.hold.a_response(
        section_id=section,
        course_week=ON_BEHALF_WEEK,
        author=world.teacher_id,
        role=INSTRUCTOR,
        body="E7-03 a published response",
        published_at=report_opens(ON_BEHALF_WEEK) + FIRST_ROW_AFTER_OPENING,
    )
    after = both()

    assert before == (True, True), f"Before the response the week read {before}."
    assert after == (False, False), (
        f"After the response the week read owed={after[0]}, on-behalf={after[1]}. Done-when 6: a "
        "published week is never owed."
    )
