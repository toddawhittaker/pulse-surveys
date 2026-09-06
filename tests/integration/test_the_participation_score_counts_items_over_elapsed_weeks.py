"""Completed items over total items, across the student's elapsed weeks — ticket E3-03.

SPEC §3.4, ruled 2026-09-04: "Score = **completed items ÷ total items** across
the student's elapsed weeks … A week carries one item per question in the survey
definition, and a student who answers four of a week's five items earns four
fifths of that week rather than nothing." And: "one line per elapsed week, of the
form `Week 1: 4 of 5 items`, in course-week order."

This module is the ticket's first two criteria and the ledger. The section is a
six-week cohort starting in term week 7, so **course week 1 is term week 7** and a
ledger numbered on the wrong axis is red here rather than invisible (SPEC §2.2's
two axes).

**The denominator is the part that can be wrong while both numbers look right**,
which is criterion 1's own sentence, so every test below asserts the total
outright rather than only the percentage — and the 100% and 0% cases are asked of
two students in one world, so a denominator built from what was answered has to
answer differently for the two.

**What is not here.** Which weeks a student is credited with is §3.4's tier
question and lives in `test_the_first_enrolled_week_follows_the_three_tiers.py`;
what a refused comment costs is in `test_a_refused_comment_costs_its_item.py`;
where the denominator comes from is in
`test_the_denominator_comes_from_the_weeks_question_set.py`.
"""

from typing import Any

import pytest
from fixtures.grading import (
    PARTICIPATION_FUNCTION,
    RESPONSE_IS_VALID_COLUMN,
    SCORE_FIELDS,
    GradingWorld,
    ledger_line,
    ledger_of,
    score_fields,
)
from fixtures.submit import RESPONSE_TABLE, USER_TABLE
from fixtures.supervision import require_table

pytestmark = pytest.mark.integration

# Three of the section's six weeks have closed in most tests here, and SPEC §3.2's
# set carries five questions, so a day-one student's denominator is fifteen items.
# Written as two numbers and their product rather than as `15`, so a failure says
# which of the two moved.
ELAPSED_WEEKS = 3
ITEMS_PER_WEEK = 5

# The position SPEC §3.2 gives the instructor comment. Left unanswered where a
# test wants four of five items: §3.3 as amended says a blank optional comment
# "does cost its **item** in §3.4's participation score".
INSTRUCTOR_COMMENT = 2


def answered_positions_without_the_comment(world: GradingWorld) -> list[int]:
    """Every position but the instructor comment — a week answered four items of five."""
    return [position for position in world.positions if position != INSTRUCTOR_COMMENT]


def test_the_service_answers_one_score_per_enrolled_student_keyed_by_the_user_id(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """The mapping is keyed by the enrollment's user id, one entry per enrolled student.

    **The mutation this kills:** a mapping keyed by the enrollment row's id, or by
    the LMS subject string, or a list of scores with the student inside. E3-02's
    `grade_sync` and E3-04's post both address a student by the user id, so a
    mapping keyed by anything else is a contract that silently posts nothing —
    every lookup misses.

    Both students are given answers and a closed week, so neither can be absent
    for the reason criterion 4 describes.
    """
    world = grading_world.build()
    first = world.student("e3-03-first")
    second = world.student("e3-03-second")
    world.answer_week(first, 1)
    world.answer_week(second, 1)
    world.elapsed_through(clock_overrides, 1)

    answered = world.scores(settings=window_settings)

    assert set(answered) == {first.user_id, second.user_id}, (
        f"`{PARTICIPATION_FUNCTION}` answered keys {sorted(map(str, answered))} for a section with "
        f"two enrolled students, whose user ids are {sorted(map(str, (first.user_id, second.user_id)))}. "
        "The work order settles the mapping as keyed by the enrollment's user id."
    )
    for key, value in answered.items():
        fields = score_fields(value)
        assert fields.total > 0, (
            f"The score for user {key} carries a total of {fields.total}. E3-03's contract: the "
            f"denominator is 'always > 0 when the object exists', because a student with no "
            "elapsed week is absent from the mapping rather than present with a zero denominator. "
            f"The four fields are {list(SCORE_FIELDS)}."
        )


def test_a_student_who_answered_every_item_of_every_elapsed_week_scores_a_hundred_percent(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Criterion 1's first half, with the denominator asserted rather than implied.

    **The mutations this kills:** a numerator that counts weeks rather than items
    (3 of 3 is also 100%, so the percentage alone cannot tell them apart — the
    totals can); a denominator taken from the answered rows, which is 15 here by
    coincidence and is asserted against the zero-answer student in the test below;
    and a percentage rendered without its decimal.
    """
    world = grading_world.build()
    student = world.student("e3-03-complete")
    for course_week in range(1, ELAPSED_WEEKS + 1):
        world.answer_week(student, course_week)
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    score = world.score_for(student, settings=window_settings)

    assert score.total == ELAPSED_WEEKS * ITEMS_PER_WEEK, (
        f"A student enrolled from day one with {ELAPSED_WEEKS} elapsed weeks and a five-question "
        f"set has a denominator of {score.total} rather than {ELAPSED_WEEKS * ITEMS_PER_WEEK}. "
        "SPEC §3.4: 'A week carries one item per question in the survey definition.'"
    )
    assert score.completed == score.total, (
        f"The student answered every item of every elapsed week and is credited with "
        f"{score.completed} of {score.total}."
    )
    assert score.percentage == "100.0", (
        f"The percentage is {score.percentage!r} rather than '100.0'. E3-03 produces one canonical "
        "string, stored by E3-02's `grade_sync` and re-sent verbatim by E3-04, and it always "
        "carries exactly one decimal."
    )


def test_a_student_who_answered_nothing_scores_zero_over_the_same_denominator(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Criterion 1's second half, and the pair that catches a denominator built from answers.

    Two students in one section: one answered everything, one answered nothing.
    Their denominators have to be identical, because the denominator is a fact
    about the weeks a student was enrolled for and not about what they submitted.

    **The mutation this kills:** a total counted from the `answer` rows found —
    which gives the second student 0 of 0, an undefined percentage or a "100.0"
    for having completed everything they attempted. That mutation passes every
    single-student test in this module.
    """
    world = grading_world.build()
    answering = world.student("e3-03-answering")
    silent = world.student("e3-03-silent")
    for course_week in range(1, ELAPSED_WEEKS + 1):
        world.answer_week(answering, course_week)
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    answered = world.score_for(answering, settings=window_settings)
    nothing = world.score_for(silent, settings=window_settings)

    assert (
        nothing.completed == 0
    ), f"A student who submitted nothing is credited with {nothing.completed} completed items."
    assert nothing.total == answered.total == ELAPSED_WEEKS * ITEMS_PER_WEEK, (
        f"The silent student's denominator is {nothing.total} and the answering student's is "
        f"{answered.total}; both were enrolled for the same {ELAPSED_WEEKS} elapsed weeks, so both "
        f"are {ELAPSED_WEEKS * ITEMS_PER_WEEK}. SPEC §3.4: a week the student did not answer "
        "contributes '0 of N, never omitted from the denominator'."
    )
    assert nothing.percentage == "0.0", (
        f"The percentage is {nothing.percentage!r} rather than '0.0'. A real zero is a posted "
        "value; the case with nothing to post is an absent entry, and criterion 4 is where that "
        "distinction is asserted."
    )


def test_a_week_answered_four_items_of_five_earns_four_fifths_and_says_so(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Criterion 2, in one elapsed week so the week's contribution *is* the score.

    The item left out is the optional instructor comment, which is exactly SPEC
    §3.3's amended sentence: a blank optional comment does not affect validity and
    does cost its item in §3.4's score.

    **The mutations this kill:** the superseded formula, under which a week
    answered four of five is a failed week and the score is 0.0; a numerator that
    credits the whole week for any submission at all, which gives 100.0; and a
    ledger line numbered on the term axis, which would read `Week 7` for this
    cohort.
    """
    world = grading_world.build()
    student = world.student("e3-03-four-of-five")
    world.answer_week(student, 1, positions=answered_positions_without_the_comment(world))
    world.elapsed_through(clock_overrides, 1)

    score = world.score_for(student, settings=window_settings)

    assert (score.completed, score.total) == (4, ITEMS_PER_WEEK), (
        f"A week of four answered items out of five is credited as {score.completed} of "
        f"{score.total}. SPEC §3.4: 'a student who answers four of a week's five items earns four "
        "fifths of that week rather than nothing'."
    )
    assert score.percentage == "80.0", f"The percentage is {score.percentage!r} rather than '80.0'."
    assert score.ledger == ledger_line(1, 4, ITEMS_PER_WEEK), (
        f"The ledger reads {score.ledger!r} rather than {ledger_line(1, 4, ITEMS_PER_WEEK)!r}. "
        "SPEC §3.4 gives the line's form outright, and the week it names is the **course** week — "
        f"this section's course week 1 is term week {world.term_week_of(1)}."
    )


def test_a_missed_week_contributes_no_completed_items_and_its_whole_denominator(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """SPEC §3.4: '0 of N, never omitted from the denominator'.

    **The mutation this kills:** a denominator assembled by walking the weeks a
    student *responded* in, which drops the missed week from both halves and turns
    a student who skipped a third of the term into a 100%. That mutation is
    invisible to every test where the student answered every week.

    Weeks 1 and 3 are answered and week 2 is missed, so a formula that dropped the
    missed week would answer 10 of 10 rather than 10 of 15.
    """
    world = grading_world.build()
    student = world.student("e3-03-missed-a-week")
    world.answer_week(student, 1)
    world.answer_week(student, 3)
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    score = world.score_for(student, settings=window_settings)

    assert score.total == ELAPSED_WEEKS * ITEMS_PER_WEEK, (
        f"The denominator is {score.total} for a student enrolled through {ELAPSED_WEEKS} elapsed "
        f"weeks who answered two of them. The missed week is worth its full "
        f"{ITEMS_PER_WEEK} items."
    )
    assert score.completed == 2 * ITEMS_PER_WEEK, (
        f"The numerator is {score.completed} for two fully answered weeks of {ITEMS_PER_WEEK} "
        "items."
    )
    assert score.percentage == "66.7", (
        f"The percentage is {score.percentage!r}; ten items of fifteen is 66.666…, which rounds "
        "half up to one decimal as '66.7'."
    )


def test_the_ledger_names_every_elapsed_week_once_in_course_week_order(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """The whole ledger string, for a student whose three weeks differ from each other.

    Five items, then none, then four: three different lines, so the assertion
    cannot be satisfied by a ledger that repeats one line or that renders the
    weeks in any other order.

    **The mutations this kills:** a ledger in reverse order or in insertion order;
    a ledger that omits the missed week; a line numbered on the term axis (`Week
    9` for this cohort's course week 3); and a ledger joined with something other
    than a newline.
    """
    world = grading_world.build()
    student = world.student("e3-03-ledger")
    world.answer_week(student, 1)
    world.answer_week(student, 3, positions=answered_positions_without_the_comment(world))
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    score = world.score_for(student, settings=window_settings)

    expected = ledger_of(
        [(1, ITEMS_PER_WEEK, ITEMS_PER_WEEK), (2, 0, ITEMS_PER_WEEK), (3, 4, ITEMS_PER_WEEK)]
    )
    assert score.ledger == expected, (
        f"The ledger reads:\n{score.ledger}\n\nand SPEC §3.4's form for these three weeks is:\n"
        f"{expected}\n\nOne line per elapsed week, in course-week order."
    )


def test_the_score_does_not_read_the_responses_validity_column(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """The item formula works from answer rows and classifications, never from `response.is_valid`.

    E3-03's ticket header says so outright: the module "does **not** read
    `response.is_valid`: the item-based formula ruled on 2026-09-04 works from the
    answer rows and each comment's most recent classification, which is a finer
    grain than a per-response verdict can carry."

    **The mutation this kills** is the superseded data path surviving as a filter:
    a numerator that counts only answers whose response is valid, or a week
    credited by its response's verdict. Both are one `where` clause, both look
    reasonable beside E2-08's column, and both would score the invalid student
    below at zero.

    The planted column is read back first, because a schema that ignored the value
    would make this a pair of identical rows and the assertion would hold for no
    reason (`docs/MISTAKES.md` entry 3).
    """
    from sqlalchemy import select

    world = grading_world.build()
    valid = world.student("e3-03-valid-response")
    invalid = world.student("e3-03-invalid-response")
    for course_week in range(1, ELAPSED_WEEKS + 1):
        world.answer_week(valid, course_week, is_valid=True)
        world.answer_week(invalid, course_week, is_valid=False)
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    table = require_table(world.tables, RESPONSE_TABLE)
    assert RESPONSE_IS_VALID_COLUMN in table.c, (
        f"`{RESPONSE_TABLE}` declares no `{RESPONSE_IS_VALID_COLUMN}`. E2-08 added it and E3-03's "
        "ticket keeps it — the correction that ticket makes is to the column's *justification*, "
        "not to the column. Without it this test plants nothing and proves nothing."
    )
    stored = world.session.execute(
        select(table.c[RESPONSE_IS_VALID_COLUMN]).where(
            table.c[world.link(RESPONSE_TABLE, USER_TABLE)] == invalid.user_id
        )
    ).scalars()
    stored_values = sorted({bool(value) for value in stored})
    assert stored_values == [False], (
        f"The invalid student's responses carry `{RESPONSE_IS_VALID_COLUMN}` values "
        f"{stored_values} rather than only `False`, so this test is not planting the state it "
        "claims to."
    )

    assert world.score_for(invalid, settings=window_settings) == world.score_for(
        valid, settings=window_settings
    ), (
        "Two students with identical answers scored differently because one's responses are "
        f"marked invalid. E3-03 reads answer rows and classifications; "
        f"`{RESPONSE_IS_VALID_COLUMN}` is E2-08's per-response verdict and is not an input to the "
        "item formula."
    )
