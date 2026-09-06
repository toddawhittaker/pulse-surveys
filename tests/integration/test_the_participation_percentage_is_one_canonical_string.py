"""One rounding rule, one formatting rule, one string — ticket E3-03.

E3-03's scope: "The canonical percentage: one rounding rule, one formatting rule,
one string, produced here and consumed unchanged by everything downstream." The
work order settles it exactly: `Decimal(completed)/Decimal(total)*100`, quantized
to one decimal place, **ROUND_HALF_UP**, formatted with exactly one decimal
always.

It matters more than a display choice, and ADR 0052 is why: that record rejected
deduplicating AGS bodies partly because `61.5` and `61.50` are different bodies.
E3-02's `grade_sync` stores this string and E3-04 re-sends it verbatim, so a
formatting difference is a re-post of an unchanged score, every week, for every
student.

**The half-up case is the one that can be wrong silently.** Python's own default
for `Decimal.quantize` is `ROUND_HALF_EVEN`, so a rounding rule written without
naming one is banker's rounding — correct on every value that is not an exact
half at the second decimal, and one tenth low on those that are. One item of
sixteen is exactly 6.25%, which is `6.3` half up and `6.2` half even, and it is
the only case in this ticket that tells the two apart.
"""

from typing import Any

import pytest
from fixtures.grading import GradingWorld

pytestmark = pytest.mark.integration

# Four questions across four elapsed weeks is a denominator of sixteen, which is
# what puts an exact half at the second decimal within reach: one item of sixteen
# is 6.25%.
QUESTIONS_IN_THE_SET = 4
ELAPSED_WEEKS = 4
ITEMS_IN_ALL = QUESTIONS_IN_THE_SET * ELAPSED_WEEKS

# Two positions of that set, neither of them the comment (the set cycles rating,
# comment, workload, rating), so every numerator here is decided by answer rows
# alone.
A_RATING_POSITION = 1
A_WORKLOAD_POSITION = 3


def test_an_exact_half_at_the_second_decimal_rounds_up_rather_than_to_even(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """One item of sixteen is 6.25%, and the canonical string is "6.3".

    **The mutation this kills:** `quantize(Decimal("0.1"))` with no rounding
    argument, which is `ROUND_HALF_EVEN` and answers "6.2". Every other percentage
    asserted anywhere in this ticket is identical under both rules, so without
    this case the suite states a rounding rule it never checks.

    It also kills truncation, which answers "6.2" here as well and is what
    `f"{value:.1f}"` over a float does not do but `int(value * 10) / 10` does.
    """
    world = grading_world.build(question_count=QUESTIONS_IN_THE_SET)
    student = world.student("e3-03-half-up")
    world.answer_week(student, 1, positions=[A_RATING_POSITION])
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    score = world.score_for(student, settings=window_settings)

    assert (score.completed, score.total) == (1, ITEMS_IN_ALL), (
        f"This world is meant to put one completed item over {ITEMS_IN_ALL}, and the score is "
        f"{score.completed} of {score.total}. The rounding assertion below means nothing over a "
        "different fraction."
    )
    assert score.percentage == "6.3", (
        f"One item of {ITEMS_IN_ALL} is exactly 6.25%, and the percentage is {score.percentage!r} "
        "rather than '6.3'. The work order settles ROUND_HALF_UP; Python's default is half even, "
        "which answers '6.2'."
    )


def test_a_whole_percentage_still_carries_exactly_one_decimal(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Eight items of sixteen is "50.0" — a string, with the decimal that is not needed.

    **The mutations this kill:** a percentage rendered as a number and stringified
    (`"50"`, or `"50.0"` only by luck of the type), a `%g` format, and a value
    handed back as a `Decimal` or a `float` for a caller to format. ADR 0052 makes
    the exact characters the thing that decides whether a re-post happens, so the
    type is asserted beside the value.
    """
    world = grading_world.build(question_count=QUESTIONS_IN_THE_SET)
    student = world.student("e3-03-whole-number")
    for course_week in range(1, ELAPSED_WEEKS + 1):
        world.answer_week(student, course_week, positions=[A_RATING_POSITION, A_WORKLOAD_POSITION])
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    score = world.score_for(student, settings=window_settings)

    assert (score.completed, score.total) == (2 * ELAPSED_WEEKS, ITEMS_IN_ALL), (
        f"This world is meant to put half the items in, and the score is {score.completed} of "
        f"{score.total}."
    )
    assert isinstance(score.percentage, str), (
        f"The percentage came back as {type(score.percentage).__name__} rather than a string. "
        "E3-03 produces the string E3-02 stores and E3-04 re-sends; a caller that formats a number "
        "itself is a second formatting rule."
    )
    assert score.percentage == "50.0", (
        f"The percentage is {score.percentage!r} rather than '50.0'. Exactly one decimal, always — "
        "'100.0', '0.0', '50.0'."
    )
