"""A week's total is its question set's size, never a constant — ticket E3-03, criterion 6.

SPEC §3.4: "The total for a week is derived from the `question_set` in force for
it (§3.2) and is never a constant: the set is versioned precisely so a week's item
count can change, and a formula holding a literal count would be wrong the first
time it does."

E3-03's sixth criterion asks for the proof directly: "The denominator is derived
from the week's question set and a test proves it: a question set with a different
number of questions produces a different denominator, with no constant `5`
anywhere in the module."

**Why this needs two tests and not one.** Exactly one question set exists in the
system today, so any rule at all — the set in force at the window's close, the set
the answered rows resolve to, or a literal five — produces the right answer.
The two tests below are the same world, the same student, the same two answered
items and the same single elapsed week; the *only* difference is the size of the
set in force. A formula holding a constant is green on the first and red on the
second, and nothing else in the ticket can tell them apart.

The other half of criterion 6 — that no literal `5` sits in the module — is
`tests/unit/test_the_grading_module_reaches_no_network_ags_or_job.py`, because it
is a statement about the source rather than about an answer.
"""

from typing import Any

import pytest
from fixtures.grading import GradingWorld, ledger_line

pytestmark = pytest.mark.integration

# The two items answered in both tests: the first question of the set and the
# third. Both exist in a five-question set and in a three-question one, and
# neither is a comment in either — so the numerator here is two, decided by the
# answer rows alone, with no classification in the way.
ANSWERED = (1, 3)

SPEC_3_2_QUESTION_COUNT = 5
A_SMALLER_SET = 3


def test_the_denominator_is_the_question_count_of_the_set_in_force(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """SPEC §3.2's five questions, two of them answered in the one elapsed week: 2 of 5.

    **The mutation this kills** on its own is a denominator counted from the
    answers found, which would answer 2 of 2 and score this student at 100%. The
    constant-five mutation survives this test and is killed by the next one.
    """
    world = grading_world.build(question_count=SPEC_3_2_QUESTION_COUNT)
    student = world.student("e3-03-five-question-set")
    world.answer_week(student, 1, positions=ANSWERED)
    world.elapsed_through(clock_overrides, 1)

    score = world.score_for(student, settings=window_settings)

    assert (score.completed, score.total) == (len(ANSWERED), SPEC_3_2_QUESTION_COUNT), (
        f"A week of five questions with two items answered is credited as {score.completed} of "
        f"{score.total} rather than {len(ANSWERED)} of {SPEC_3_2_QUESTION_COUNT}."
    )
    assert score.percentage == "40.0", f"The percentage is {score.percentage!r} rather than '40.0'."


def test_a_question_set_of_a_different_size_moves_the_denominator(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """A second version carrying three questions: the same two answers are now 2 of 3.

    **The mutations this kills:** a literal question count anywhere in the
    arithmetic, and a per-week total taken from a table that never changes.
    Everything else about this world is identical to the test above — one elapsed
    week, one day-one student, the same two positions answered — so a difference
    in the denominator can only have come from the set.

    It also fixes the consequence ADR 0130 states: a later version re-denominates
    the weeks that have already passed. That is the behaviour, and this is the
    test that says so out loud rather than leaving it to be discovered when a
    second version ships.
    """
    world = grading_world.build(question_count=SPEC_3_2_QUESTION_COUNT)
    world.plant_question_set(version=2, question_count=A_SMALLER_SET)
    student = world.student("e3-03-three-question-set")
    world.answer_week(student, 1, positions=ANSWERED)
    world.elapsed_through(clock_overrides, 1)

    score = world.score_for(student, settings=window_settings)

    assert score.total == A_SMALLER_SET, (
        f"With a version 2 question set of {A_SMALLER_SET} questions in force, the week's "
        f"denominator is {score.total}. SPEC §3.4: the total 'is derived from the `question_set` "
        "in force for it and is never a constant'."
    )
    assert score.completed == len(ANSWERED), (
        f"The numerator is {score.completed} rather than {len(ANSWERED)}. Two items were answered; "
        "changing the size of the set changes what the week is out of, not what was submitted."
    )
    assert score.ledger == ledger_line(1, len(ANSWERED), A_SMALLER_SET), (
        f"The ledger reads {score.ledger!r} rather than "
        f"{ledger_line(1, len(ANSWERED), A_SMALLER_SET)!r}. The ledger's `of Y` is the same "
        "denominator the percentage is over, and a line still saying 'of 5' would be reporting an "
        "arithmetic nobody performed."
    )
    assert score.percentage == "66.7", (
        f"The percentage is {score.percentage!r}. Two items of three is 66.666…, which is 66.7 to "
        "one decimal — the canonical string, produced here and consumed unchanged downstream."
    )
