"""A comment item completes only if its latest verdict does not refuse it — ticket E3-03.

SPEC §3.4, ruled 2026-09-04: "A rating or workload item is completed by being
answered; a comment item is completed by being answered *and* not classified into
the refused set of §3.3. The score is computed from the student's submitted
answers and each comment's most recent classification, so a week is a fraction
rather than a pass or a fail."

E3-03's fifth criterion: "A comment whose latest classification is `insufficient`
or `nonsense` does not count its item, and a later classification row changes the
answer — asserted by adding a row, not by editing one, because the table is
append-only."

**Every case here is a pair.** A refused verdict is asserted against the same
world with a substantive one, because "the item did not count" is also what a
formula that lost the answer entirely would say. And the ordering case is asserted
in both directions: a later row that refuses, and a later row that does not.

SPEC §3.2 puts a comment at positions 2 and 4 of the five-question set, so a fully
answered week here carries two comments and three items that complete by existing
alone. Refusing one comment leaves four items of five; refusing both leaves three.
That second case is what distinguishes the item formula from the pass-or-fail week
it replaced.
"""

from datetime import timedelta
from typing import Any

import pytest
from fixtures.grading import (
    CLASSIFICATION_VERDICT_COLUMN,
    INSUFFICIENT,
    NONSENSE,
    SUBSTANTIVE,
    GradingWorld,
    ledger_line,
)

pytestmark = pytest.mark.integration

ITEMS_PER_WEEK = 5

# SPEC §3.2's two comment questions.
INSTRUCTOR_COMMENT = 2
COURSE_COMMENT = 4

# Where the classification rows sit relative to the week's close. All of them are
# in the past of the moved clock, so nothing here turns on a verdict written after
# the instant the score is asked at — that is E3-06's question and this module
# deliberately does not pose it.
FIRST_VERDICT_BEFORE_CLOSE = timedelta(hours=2)
SECOND_VERDICT_BEFORE_CLOSE = timedelta(minutes=10)


def test_a_comment_whose_latest_verdict_is_insufficient_does_not_count_its_item(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """One refused comment in a fully answered week: four items of five.

    **The mutations this kills:** a comment item counted by the existence of its
    answer row alone, which gives 5 of 5 and is what the rating and workload rule
    looks like if it is applied to every shape; and the superseded pass-or-fail
    week, which gives 0 of 5 because the response is not valid.
    """
    world = grading_world.build()
    student = world.student("e3-03-insufficient")
    world.answer_week(student, 1, verdicts={INSTRUCTOR_COMMENT: INSUFFICIENT})
    world.elapsed_through(clock_overrides, 1)

    score = world.score_for(student, settings=window_settings)

    assert (score.completed, score.total) == (4, ITEMS_PER_WEEK), (
        f"A week of five answered items, one of them a comment classified {INSUFFICIENT!r}, is "
        f"credited as {score.completed} of {score.total} rather than 4 of {ITEMS_PER_WEEK}."
    )
    assert score.ledger == ledger_line(
        1, 4, ITEMS_PER_WEEK
    ), f"The ledger reads {score.ledger!r} rather than {ledger_line(1, 4, ITEMS_PER_WEEK)!r}."


def test_a_comment_whose_latest_verdict_is_nonsense_does_not_count_its_item(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """The other refused verdict, asked separately.

    **The mutation this kills:** a rule written against one token — `verdict !=
    'insufficient'` — which is the shape a hand-written comparison takes and which
    credits every nonsense comment in the system. The refused set has two members
    and both are asked, rather than one being assumed to stand for the other
    (`docs/MISTAKES.md` entry 15).
    """
    world = grading_world.build()
    student = world.student("e3-03-nonsense")
    world.answer_week(student, 1, verdicts={INSTRUCTOR_COMMENT: NONSENSE})
    world.elapsed_through(clock_overrides, 1)

    score = world.score_for(student, settings=window_settings)

    assert (score.completed, score.total) == (4, ITEMS_PER_WEEK), (
        f"A comment classified {NONSENSE!r} left the week credited as {score.completed} of "
        f"{score.total} rather than 4 of {ITEMS_PER_WEEK}."
    )


def test_a_substantive_comment_counts_its_item(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """The other half of both tests above: the same week, with a verdict that does not refuse.

    Without this, "the item did not count" is satisfied by an implementation that
    never counts a comment item at all — and both refusal tests would be green
    against a formula that had lost the comments entirely (`docs/MISTAKES.md`
    entry 3).
    """
    world = grading_world.build()
    student = world.student("e3-03-substantive")
    world.answer_week(student, 1, verdicts={INSTRUCTOR_COMMENT: SUBSTANTIVE})
    world.elapsed_through(clock_overrides, 1)

    score = world.score_for(student, settings=window_settings)

    assert (score.completed, score.total) == (ITEMS_PER_WEEK, ITEMS_PER_WEEK), (
        f"A week whose two comments are both {SUBSTANTIVE!r} is credited as {score.completed} of "
        f"{score.total} rather than {ITEMS_PER_WEEK} of {ITEMS_PER_WEEK}. Nothing in this week is "
        "refused, so nothing is deducted."
    )
    assert (
        score.percentage == "100.0"
    ), f"The percentage is {score.percentage!r} rather than '100.0'."


def test_two_refused_comments_cost_two_items_and_not_the_whole_week(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Both comments refused: three items of five, not zero and not four.

    **The mutation this kills** is the item rule collapsing back into a week rule.
    A formula that treats any refused comment as failing the week answers 0 of 5
    here and 0 of 5 in the single-refusal test too, so only a week with *two*
    refusals distinguishes "one item each" from "the week is spoiled". SPEC §3.4:
    "a week is a fraction rather than a pass or a fail".
    """
    world = grading_world.build()
    student = world.student("e3-03-both-refused")
    world.answer_week(
        student,
        1,
        verdicts={INSTRUCTOR_COMMENT: INSUFFICIENT, COURSE_COMMENT: NONSENSE},
    )
    world.elapsed_through(clock_overrides, 1)

    score = world.score_for(student, settings=window_settings)

    assert (score.completed, score.total) == (3, ITEMS_PER_WEEK), (
        f"A week whose two comments are both refused is credited as {score.completed} of "
        f"{score.total} rather than 3 of {ITEMS_PER_WEEK}: the two ratings and the workload still "
        "count, because they complete by being answered."
    )


def test_a_later_classification_row_lowers_the_score_without_editing_anything(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Criterion 5's second half: the answer changes because a row was **added**.

    The comment is judged substantive, the score is asked, a second row refusing it
    is appended, and the score is asked again. This is E2-08's asynchronous
    re-classification seen from E3-03's side, and the module's own docstring is
    required to say that its answer is a function of the current classification
    state rather than of the week.

    **The mutations this kill:** a rule reading the *first* verdict, which never
    moves; a rule reading *any* refusing verdict, which would already have refused
    at the first call; and an implementation that cached the week's answer. The row
    count is asserted afterwards because the criterion is specifically about an
    append — the table is append-only by grant (ADR 0055), so a test that edited a
    row would be testing something the application cannot do.
    """
    world = grading_world.build()
    student = world.student("e3-03-reclassified")
    answers = world.answer_week(student, 1, verdicts={INSTRUCTOR_COMMENT: SUBSTANTIVE})
    world.elapsed_through(clock_overrides, 1)

    before = world.score_for(student, settings=window_settings)
    assert before.completed == ITEMS_PER_WEEK, (
        f"Before the re-classification the student is credited with {before.completed} of "
        f"{before.total}, and every item of the week is answered and unrefused. The rest of this "
        "test measures a change against this number, so it has to be right first."
    )

    world.classify(
        answers[INSTRUCTOR_COMMENT],
        INSUFFICIENT,
        classified_at=world.closes_at(1) - SECOND_VERDICT_BEFORE_CLOSE,
    )

    after = world.score_for(student, settings=window_settings)
    assert after.completed == ITEMS_PER_WEEK - 1, (
        f"After a second classification refusing the comment, the student is credited with "
        f"{after.completed} of {after.total} rather than {ITEMS_PER_WEEK - 1}. The governing "
        "verdict is the latest row, never the only row."
    )
    assert after.total == before.total, (
        f"The denominator moved from {before.total} to {after.total} when a classification was "
        "appended. A verdict decides whether an item is completed and never how many items there "
        "are."
    )

    rows = world.classifications_of(answers[INSTRUCTOR_COMMENT])
    verdicts = sorted(row[CLASSIFICATION_VERDICT_COLUMN] for row in rows)
    assert verdicts == sorted([SUBSTANTIVE, INSUFFICIENT]), (
        f"The comment carries the classification rows {verdicts}. This test has to change the "
        "answer by adding a row and not by editing one, and both rows have to still be there for "
        "the assertion above to mean 'the latest governs' rather than 'the only row governs'."
    )


def test_the_governing_verdict_is_the_latest_by_classified_at_not_the_last_inserted(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """The refusing row is written first and dated last; the counting row is written second.

    `app/services/validity.py` orders the latest verdict by `classified_at DESC,
    id DESC`, and the work order requires this module to mirror it. Insertion
    order and classification order disagree here, so exactly one of the two rules
    can be right about this world.

    **The mutation this kills:** `ORDER BY id DESC` alone, or `LIMIT 1` over an
    unordered read, both of which pick the substantive row and credit the item.
    A re-classification that arrives out of order — a sweep re-running an old
    floored verdict while a newer one is already stored — is exactly how that
    happens in production.
    """
    world = grading_world.build()
    student = world.student("e3-03-out-of-order")
    answers = world.answer_week(student, 1, verdicts={INSTRUCTOR_COMMENT: INSUFFICIENT})
    world.classify(
        answers[INSTRUCTOR_COMMENT],
        SUBSTANTIVE,
        classified_at=world.closes_at(1) - FIRST_VERDICT_BEFORE_CLOSE,
    )
    world.elapsed_through(clock_overrides, 1)

    score = world.score_for(student, settings=window_settings)

    assert score.completed == ITEMS_PER_WEEK - 1, (
        f"The comment's rows are {INSUFFICIENT!r} at the later `classified_at` and "
        f"{SUBSTANTIVE!r} at the earlier one, inserted in that order, and the student is credited "
        f"with {score.completed} of {score.total} rather than {ITEMS_PER_WEEK - 1}. The governing "
        "verdict is the latest by `classified_at`, which is the row that refuses."
    )


def test_a_comment_with_no_classification_at_all_still_counts_its_item(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """The state the fail-open floor makes unreachable, answered the way fail-open requires.

    E3-03's ticket: "There is no 'unclassified' state. A comment that fell to the
    fail-open floor already carries a verdict, written under `FLOOR_MODEL_ID` and
    `FLOOR_PROMPT_VERSION`." The work order settles what happens if one ever
    occurred anyway: it counts, because SPEC §3.3's whole posture is that a
    student is never penalised for an outage.

    **The mutation this kills:** an inner join from `answer` to `classification`,
    which is the natural way to write "the comment's latest verdict" and which
    silently drops the item instead of counting it. The two readings differ only
    on this row, and no other test in the ticket can tell them apart.
    """
    world = grading_world.build()
    student = world.student("e3-03-unclassified")
    answers = world.answer_week(student, 1, unclassified=[INSTRUCTOR_COMMENT])
    world.elapsed_through(clock_overrides, 1)

    assert world.classifications_of(answers[INSTRUCTOR_COMMENT]) == [], (
        "The comment this test plants carries classification rows, so it is not the state the "
        "test is about."
    )

    score = world.score_for(student, settings=window_settings)

    assert (score.completed, score.total) == (ITEMS_PER_WEEK, ITEMS_PER_WEEK), (
        f"A comment with no classification row is credited as {score.completed} of {score.total} "
        f"rather than {ITEMS_PER_WEEK} of {ITEMS_PER_WEEK}. Nothing has refused it, and fail open "
        "means an absent verdict never costs a student."
    )
