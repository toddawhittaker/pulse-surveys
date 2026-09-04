"""Nothing to post is an absence, never a zero — ticket E3-03, criterion 4.

SPEC §3.4: "A section with no elapsed weeks has no score posted yet — an absent
score, never a posted zero, because a zero in a gradebook is a statement about a
student and only absence is true before the first week closes."

E3-03's fourth criterion: "Zero elapsed weeks produces no score at all — a
distinguishable 'nothing to post', not a zero. The caller cannot mistake the two."
The work order settles the distinction as membership: a student with no elapsed
enrolled week is **absent from the mapping**, and a student with one is present
with a real `"0.0"`.

**Both halves are asserted, on one world, a minute apart.** An absence assertion
on its own is satisfied by a function that answers nothing at all
(`docs/MISTAKES.md` entry 3), so the same student is scored again with the clock
moved past the close and has to be there. And the third test poses the case a
section-level elapsed set gets wrong: one student present and one absent, in the
same section, at the same instant.
"""

from datetime import date
from typing import Any

import pytest
from fixtures.grading import (
    A_MOMENT,
    PARTICIPATION_FUNCTION,
    GradingWorld,
    ledger_line,
)

pytestmark = pytest.mark.integration

ITEMS_PER_WEEK = 5

# A date inside the section's span, used only as a student's first sighting where
# a test needs one that is not the section's start.
LATE_ADD_WEEK = 3


def test_a_section_whose_first_week_has_not_closed_answers_no_scores_at_all(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """A minute before the first window closes: an empty mapping, not a zero for anybody.

    **The mutation this kills:** an entry built for every enrolled student
    regardless of their elapsed weeks, which posts `0.0` into a gradebook in week
    one — a statement about a student that is not true, and the reason §3.4 spells
    the case out at all.

    The whole mapping is asserted empty rather than just this student's key being
    missing: an implementation that answered an entry under some other key would
    satisfy "not in" and would still post something.
    """
    world = grading_world.build()
    student = world.student("e3-03-nothing-yet")
    world.not_yet_closed(clock_overrides, 1)

    answered = world.scores(settings=window_settings)

    assert answered == {}, (
        f"`{PARTICIPATION_FUNCTION}` answered {answered!r} for a section whose first window has "
        "not closed. SPEC §3.4: 'an absent score, never a posted zero'."
    )
    assert (
        student.user_id not in answered
    ), "The enrolled student has an entry before any week of their section has closed."


def test_the_same_student_is_present_with_a_real_zero_once_that_week_closes(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """A minute after the same window closes: present, with `"0.0"` over a full denominator.

    The other half of the pair above, and the half that makes it mean something: a
    formula that answered an empty mapping under all conditions would pass that
    test forever.

    **The mutation this kills:** a student omitted because they submitted nothing —
    which looks like the same "nothing to post" and is the opposite claim. A week
    they were enrolled for and did not answer is `0 of 5`, and it is posted.
    """
    world = grading_world.build()
    student = world.student("e3-03-real-zero")
    world.elapsed_through(clock_overrides, 1)

    score = world.score_for(student, settings=window_settings)

    assert (score.completed, score.total) == (0, ITEMS_PER_WEEK), (
        f"The student is credited with {score.completed} of {score.total} for one elapsed week of "
        f"five items that they did not answer."
    )
    assert score.percentage == "0.0", f"The percentage is {score.percentage!r} rather than '0.0'."
    assert score.ledger == ledger_line(1, 0, ITEMS_PER_WEEK), (
        f"The ledger reads {score.ledger!r} rather than {ledger_line(1, 0, ITEMS_PER_WEEK)!r}. An "
        "unanswered elapsed week is a line in the ledger, not an omission."
    )


def test_a_late_add_whose_own_first_week_has_not_closed_is_absent_beside_a_present_classmate(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Two students, one section, one instant: elapsed is per student, not per section.

    Two of the section's weeks have closed. The day-one student has two elapsed
    weeks and a score; the late add is dated into course week 3, which has not
    closed, so they have no elapsed enrolled week and nothing to post.

    **The mutation this kills:** an elapsed set computed once for the section and
    applied to everybody, which gives the late add a `0.0` over the two weeks they
    were not enrolled for — the worst possible wrong answer, since it is a real
    zero posted into a real gradebook for a student who could not have answered.
    An empty-mapping implementation is excluded by the classmate.
    """
    world = grading_world.build()
    day_one = world.student("e3-03-day-one")
    late = world.student(
        "e3-03-late-add",
        started_on=date(2026, 10, 18),
        lms_window_start=world.closes_at(LATE_ADD_WEEK) - A_MOMENT,
    )
    world.elapsed_through(clock_overrides, LATE_ADD_WEEK - 1)

    answered = world.scores(settings=window_settings)

    assert day_one.user_id in answered, (
        f"The day-one student has no entry although {LATE_ADD_WEEK - 1} of the section's weeks "
        "have closed. Without them present, the absence asserted below could be an empty mapping."
    )
    assert late.user_id not in answered, (
        f"The late add has an entry {answered.get(late.user_id)!r}. Their first enrolled week is "
        f"course week {LATE_ADD_WEEK}, whose window has not closed, so they have no elapsed "
        "enrolled week and nothing to post — while their classmate does."
    )
