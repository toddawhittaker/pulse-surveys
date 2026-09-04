"""A dropped student is computed exactly like an enrolled one — ticket E3-03.

SPEC §3.4 says one thing about drops: "scores stop updating; the LMS owns what
happens to the column." That is a rule about **posting**, and E3-03 still has to
answer what it *computes* for a dropped student. The ticket settles it and the
work order repeats it: the module computes the same thing it always did, and
E3-06 is what stops posting — one behaviour in one place.

So `enrollment.ended_on` is not an input to this module at all, and each test
below says that in a different currency: the score is identical to an active
student's, the denominator is not truncated at the drop, and the ledger still
names every elapsed week.

**Each is a pair against the same world.** "The dropped student scored the same"
is checked against a classmate who did not drop and answered identically, so a
formula that had broken for both alike could not satisfy it.
"""

from datetime import date
from typing import Any

import pytest
from fixtures.grading import GradingWorld, ledger_of

pytestmark = pytest.mark.integration

ELAPSED_WEEKS = 3
ITEMS_PER_WEEK = 5

# A Thursday inside course week 2 (term week 8, whose window closes on Sunday 11
# October). Late enough that one elapsed week precedes it and two follow, so a
# truncation at the drop would be visible in every one of the three assertions
# below.
DROPPED_ON = date(2026, 10, 8)


def scored_world(world: GradingWorld, clock_overrides: Any) -> tuple[Any, Any]:
    """Two students who answered week 1 fully and nothing since, one of them dropped."""
    world.build()
    active = world.student("e3-03-still-enrolled")
    dropped = world.student("e3-03-dropped")
    world.answer_week(active, 1)
    world.answer_week(dropped, 1)
    world.drop(dropped, ended_on=DROPPED_ON)
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)
    return active, dropped


def test_a_dropped_student_scores_exactly_what_an_active_one_with_the_same_answers_scores(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """The whole score, field for field, is the same on both sides of a drop.

    **The mutation this kills:** any use of `ended_on` in the computation at all —
    a denominator that stops at the drop, a numerator that ignores answers after
    it, a student omitted from the mapping because they are gone. All three are
    reasonable-looking readings of "scores stop updating", and all three put the
    posting rule inside the formula, where E3-06 cannot then see it.
    """
    world = grading_world
    active, dropped = scored_world(world, clock_overrides)

    assert world.score_for(dropped, settings=window_settings) == world.score_for(
        active, settings=window_settings
    ), (
        "A student who dropped scored differently from a classmate with identical answers. E3-03 "
        "computes the same thing for both; E3-06 is what stops posting for the one who left."
    )


def test_a_drop_does_not_truncate_the_denominator(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """The forbidden state, named: the dropped student's total is every elapsed week's items.

    The equality test above holds if *both* students were truncated, so this one
    asserts the absolute number. Two of the three elapsed weeks fall after
    `DROPPED_ON`, so a truncating formula answers 5 and a formula that stopped at
    the drop's own week answers 10.
    """
    world = grading_world
    _active, dropped = scored_world(world, clock_overrides)

    score = world.score_for(dropped, settings=window_settings)

    assert score.total == ELAPSED_WEEKS * ITEMS_PER_WEEK, (
        f"The dropped student's denominator is {score.total} rather than "
        f"{ELAPSED_WEEKS * ITEMS_PER_WEEK}. They dropped on {DROPPED_ON}, inside course week 2, "
        "and the weeks after that are still in the computation."
    )
    assert score.completed == ITEMS_PER_WEEK, (
        f"The dropped student is credited with {score.completed} items rather than "
        f"{ITEMS_PER_WEEK}; they answered course week 1 in full and nothing afterwards."
    )


def test_a_dropped_students_ledger_still_names_every_elapsed_week(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """The third currency: the ledger is not cut short at the drop either.

    A total can be right while the ledger is truncated — they are produced by
    different lines of code, and the ledger is what a person reads in the
    gradebook. SPEC §3.4 makes it one line per elapsed week, and a drop is not
    among the things that removes one.
    """
    world = grading_world
    _active, dropped = scored_world(world, clock_overrides)

    score = world.score_for(dropped, settings=window_settings)

    expected = ledger_of(
        [
            (1, ITEMS_PER_WEEK, ITEMS_PER_WEEK),
            (2, 0, ITEMS_PER_WEEK),
            (3, 0, ITEMS_PER_WEEK),
        ]
    )
    assert (
        score.ledger == expected
    ), f"The dropped student's ledger reads:\n{score.ledger}\n\nrather than:\n{expected}"
