"""A moderation verdict never moves participation credit — E6-01, criterion 11.

SPEC §3.4 credits a comment item when it is answered and its most recent
**validity** classification (§3.3) is not in the refused set. Moderation is a
different question about the same comment — is it safe to show — and E6-01 stores
its answer on the same `classification` table under a second task. So from E6-01
on, "a comment's most recent classification" has two readings, and only one of
them is §3.4's.

The readers that get this wrong do so plausibly: a participation query written
before moderation existed asks for the latest row by `classified_at` for an
answer, with no task in the `WHERE` clause, and every test it had was green
because every row was a validity row. A moderation verdict is written at window
close or later — after the validity verdict — so it becomes "the latest row".

**One case per moderation verdict**, because each one breaks a task-blind reader
differently: `clear`, `harmful`, `privacy`, `threat` and `self_harm` are not in
the refused set, so a task-blind reader credits a comment the validity classifier
refused; `nonsense` *is* a refused token in §3.3's vocabulary too, so a task-blind
reader refuses a comment the validity classifier accepted. The week below holds
one of each kind of validity verdict, so every case moves a task-blind score in at
least one direction.

**Before and after, on one student.** The score is read with no moderation verdict
anywhere, then the verdict is routed for both comments through the definer, then
the score is read again. The two must be equal in every field — the completed
items, the total, the percentage and the ledger line.

**Not marked `invariant`**: SPEC §3.4 is the grade, not a §4.1 visibility rule.
"""

from typing import Any

import pytest
from fixtures.grading import INSUFFICIENT, SUBSTANTIVE, GradingWorld
from fixtures.moderation import EVERY_VERDICT, UNMODERATED

pytestmark = pytest.mark.integration

ITEMS_PER_WEEK = 5

# SPEC §3.2's two comment questions.
INSTRUCTOR_COMMENT = 2
COURSE_COMMENT = 4


@pytest.mark.parametrize("verdict", EVERY_VERDICT)
def test_a_moderation_verdict_of_every_kind_leaves_participation_credit_unchanged(
    verdict: str, grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Criterion 11: the same student, the same week, before and after one moderation verdict.

    A fully answered week whose instructor comment is `substantive` and whose
    course comment is `insufficient` — four items of five, the premise read first.
    Then this case's moderation verdict is routed for both comments, and the score
    is read again.

    **The mutations this kills:** the participation query reading the latest
    classification row with no task filter (`nonsense` lowers the score; every
    other verdict raises it); a Care-class verdict treated as removing the item
    (`threat`, `self_harm`); a flagging verdict treated as removing it
    (`harmful`, `privacy`). **The premise** is what makes the equality mean
    something: a score that ignored comments entirely is equal before and after,
    and it is not four of five.
    """
    world = grading_world.build()
    student = world.student(f"e6-01-credit-{verdict}")
    answers = world.answer_week(
        student,
        1,
        verdicts={INSTRUCTOR_COMMENT: SUBSTANTIVE, COURSE_COMMENT: INSUFFICIENT},
        moderation={INSTRUCTOR_COMMENT: UNMODERATED, COURSE_COMMENT: UNMODERATED},
    )
    world.elapsed_through(clock_overrides, 1)

    before = world.score_for(student, settings=window_settings)
    assert (before.completed, before.total) == (ITEMS_PER_WEEK - 1, ITEMS_PER_WEEK), (
        f"Before any moderation verdict the week is credited {before.completed} of {before.total}; "
        f"one `substantive` and one `insufficient` comment make it {ITEMS_PER_WEEK - 1} of "
        f"{ITEMS_PER_WEEK}. Until that holds, the equality below can be satisfied by a score that "
        "never looked at a comment."
    )

    world.moderate(answers[INSTRUCTOR_COMMENT], verdict)
    world.moderate(answers[COURSE_COMMENT], verdict)

    after = world.score_for(student, settings=window_settings)
    assert after == before, (
        f"A {verdict!r} moderation verdict moved the student's credit from {before} to {after}. "
        "SPEC §3.4 credits a comment on its validity classification; moderation decides whether "
        "a comment is shown, never whether it was a complete answer. A participation query "
        "reading the latest `classification` row without its task reads a moderation verdict as a "
        "validity one."
    )
