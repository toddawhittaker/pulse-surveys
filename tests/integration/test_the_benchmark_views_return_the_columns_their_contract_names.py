"""E5-03 criterion 1 — what the benchmark arithmetic returns, and what is absent from it.

**Re-pointed by E9-12** (the file keeps its E5-03 name). E9-12 retires the four
cohort views (README decision 10), and every benchmark figure is now computed by
`benchmark_set_week` and `benchmark_set_rating_week`. The rules this module
pinned on the views are pinned on those two functions:

  - **That none of them names a person.** The dispute's outcome
    (`docs/disputes/E5-03-01.md`: "section id and numbers, never a person"),
    read off the catalog's own record of what each function returns.
  - **What a course week has a row for**, three states:

    | the week | the row |
    |---|---|
    | nobody answered | no row — absence, not zeros |
    | answered, no workload figures | a row, with its counts and **null** workload figures |
    | answered with hours | a row, with figures |

  - **One row per course week** over one section set.

**Deleted, and why:** `test_each_benchmark_view_returns_exactly_the_columns_its_
contract_names` and `test_the_four_benchmark_views_are_the_four_this_ticket_ships`
asserted the four views' column lists and their existence — their whole subject
was the views. Each function's own argument and result list is held as an
equality by `test_each_set_function_takes_and_answers_exactly_its_contract` in
`test_the_benchmark_set_functions_answer_over_a_section_set.py`, and the views'
absence by `test_the_four_cohort_views_are_retired.py`.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    BENCHMARK_FUNCTIONS,
    SET_FUNCTION,
    SET_RATING_FUNCTION,
    UG,
    BenchmarkWorld,
    require_benchmark_function,
)
from sqlalchemy import text

pytestmark = pytest.mark.integration

# Every spelling this schema has for a person, read as substrings of a column
# name. **`respondent_count` is deliberately not one of them**: a count of people
# is a number, and it is the number the ruling requires the arithmetic to carry.
PERSON_KEY_FRAGMENTS = ("user_id", "person_id", "respondent_id", "student_id", "lms_user")

# The columns a function returns, out of `pg_proc`: the names of its OUT,
# INOUT and TABLE arguments, which is what a caller reads.
RESULT_COLUMNS = text(
    "SELECT a.name FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
    "CROSS JOIN LATERAL unnest(p.proargnames, p.proargmodes::text[]) AS a(name, mode) "
    "WHERE n.nspname = 'public' AND p.proname = :name AND a.mode IN ('o', 'b', 't')"
)

THE_COURSE_WEEK = 2
AN_UNANSWERED_COURSE_WEEK = 4
A_WORKLOAD = Decimal("3.5")
A_RATING = Decimal("4")

# The third state: a course week whose responses carry ratings and no workload
# answer. Two respondents in one week and one in another, so the week with no
# hours has counts worth carrying and the week with hours is the contrast.
RATING_ONLY_COURSE_WEEK = 3
RATING_ONLY_RESPONDENTS = 2
A_LATER_WORKLOAD = Decimal("4.0")


def rows_at(world: BenchmarkWorld, function: str, course_week: int, *labels: str) -> list[Any]:
    read = world.set_week if function == SET_FUNCTION else world.set_rating_week
    return [row for row in read(*labels) if row["course_week"] == course_week]


@pytest.mark.invariant
@pytest.mark.parametrize("function", sorted(BENCHMARK_FUNCTIONS), ids=sorted(BENCHMARK_FUNCTIONS))
def test_no_benchmark_set_function_names_a_person_in_any_currency(
    db_session: Any, function: str
) -> None:
    """The dispute's outcome, asserted where it can be broken: no result column names a person.

    **Asserted over the catalog**, not over the contract constant: comparing a
    constant against itself passes for as long as nobody edits it. **The
    non-vacuity guard** is that the catalog's result columns include
    `course_week`, the one key every row carries — "no person key here" is true
    of a function whose results the read cannot see (`docs/MISTAKES.md` entry 3).

    **The mutation it exists to survive**: `user_id` added to a function's result
    "so the service can join", and the withdrawn `benchmark_respondent_week`
    re-introduced as a function returning its person key. **The near miss it
    tolerates**: `respondent_count`, a count of people rather than a person.
    """
    require_benchmark_function(db_session, function)
    present = [str(row[0]) for row in db_session.execute(RESULT_COLUMNS, {"name": function})]
    assert "course_week" in present, (
        f"The catalog's result columns for `public.{function}` are {present}; the read cannot see "
        "the function's results, so the sweep below would pass over nothing."
    )
    named = sorted(
        column
        for column in present
        if any(fragment in column.lower() for fragment in PERSON_KEY_FRAGMENTS)
    )
    assert not named, (
        f"`public.{function}` returns {named}, which names a person; it returns {present}. E5-03's "
        "scope allows the building block 'section id and numbers, never a person', and the ruling "
        "on `docs/disputes/E5-03-01.md` withdrew the person-keyed read on exactly that sentence."
    )


@pytest.mark.parametrize("function", sorted(BENCHMARK_FUNCTIONS), ids=sorted(BENCHMARK_FUNCTIONS))
def test_a_course_week_nobody_answered_has_no_row(
    benchmark_world: BenchmarkWorld, function: str
) -> None:
    """Absence, not zeros — the contract E5-04 is written against.

    One section answers in its second course week and in no other. Asked for
    every course week, the function answers no row for the fourth, which the
    section runs: no zero mean, no null row, no fabricated count. The answered
    week is required to have its row first, so the absence is not a function
    that answers nothing (`docs/MISTAKES.md` entry 3).

    **The mutation it exists to survive**: a `LEFT JOIN` from `week` or from
    `survey_window` that emits a row per course week asked for.
    """
    world = benchmark_world.build()
    world.plant_section("hero", cohort="U", level=UG)
    world.respond(
        "hero",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-absence",
        workload=A_WORKLOAD,
        instructor_rating=A_RATING,
        course_rating=A_RATING,
    )

    answered = rows_at(world, function, THE_COURSE_WEEK, "hero")
    assert answered, (
        f"`{function}` answers no row for the course week that was answered, so the absence below "
        "would be equally true of a function that answers nothing at all."
    )
    empty = rows_at(world, function, AN_UNANSWERED_COURSE_WEEK, "hero")
    assert empty == [], (
        f"`{function}` answers {empty} for course week {AN_UNANSWERED_COURSE_WEEK}, which the "
        "section runs and in which nobody submitted anything. The arithmetic answers what was "
        "answered; a cohort of nobody and a week nobody answered must not arrive looking the same."
    )


def a_week_answered_without_hours(world: BenchmarkWorld) -> BenchmarkWorld:
    """One section: a course week of ratings and no workload, and a later week with hours."""
    world.build()
    world.plant_section("hero", cohort="U", level=UG)
    for index in range(RATING_ONLY_RESPONDENTS):
        world.respond(
            "hero",
            course_week=RATING_ONLY_COURSE_WEEK,
            subject=f"e5-03-no-hours-{index}",
            instructor_rating=A_RATING,
            course_rating=A_RATING,
        )
    world.respond(
        "hero",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-with-hours",
        workload=A_LATER_WORKLOAD,
        instructor_rating=A_RATING,
    )
    return world


def test_a_course_week_answered_without_workload_still_has_a_row_with_its_counts(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The third state: the week exists, so the row does, carrying its true counts.

    Two students answered both ratings and neither reported hours. ADR 0165: the
    row is there with two responses, two respondents and one section, because
    those are facts about the week whatever the hours column holds.

    **The non-vacuity guard is the rating function**, read first.

    **The mutation it exists to survive**: the row derived from the workload
    answers — an inner join to the hours — which drops the whole week, counts and
    all, the moment nobody reports hours.
    """
    world = a_week_answered_without_hours(benchmark_world)

    assert rows_at(world, SET_RATING_FUNCTION, RATING_ONLY_COURSE_WEEK, "hero"), (
        f"`{SET_RATING_FUNCTION}` answers no row for course week {RATING_ONLY_COURSE_WEEK}, in "
        f"which {RATING_ONLY_RESPONDENTS} students submitted both ratings."
    )
    rows = rows_at(world, SET_FUNCTION, RATING_ONLY_COURSE_WEEK, "hero")
    assert len(rows) == 1, (
        f"`{SET_FUNCTION}` answers {rows} for course week {RATING_ONLY_COURSE_WEEK}, in which "
        f"{RATING_ONLY_RESPONDENTS} students responded and none reported hours; the ruling is one "
        "row with null workload figures."
    )
    row = rows[0]
    assert (row["response_count"], row["respondent_count"], row["section_count"]) == (
        RATING_ONLY_RESPONDENTS,
        RATING_ONLY_RESPONDENTS,
        1,
    ), f"The row is {row}; two students answered, one response each, in one section."


def test_the_workload_figures_of_a_week_with_no_hours_are_null_rather_than_zero(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The other half: an absent figure is null, and null is not nought.

    **The contrast week is the discriminator**: the same world's other course
    week carries one submitted figure and must report it.

    **The mutation it exists to survive**: `coalesce(avg(...), 0)` and
    `coalesce(percentile_cont(...), 0)`, and `avg(coalesce(hours, 0))`.
    """
    world = a_week_answered_without_hours(benchmark_world)

    with_hours = rows_at(world, SET_FUNCTION, THE_COURSE_WEEK, "hero")
    assert len(with_hours) == 1 and with_hours[0]["workload_mean"] == A_LATER_WORKLOAD, (
        f"The week that carries hours reads {with_hours}, where one student submitted "
        f"{A_LATER_WORKLOAD}."
    )
    rows = rows_at(world, SET_FUNCTION, RATING_ONLY_COURSE_WEEK, "hero")
    assert len(rows) == 1, f"`{SET_FUNCTION}` answers {rows} for the week with no hours."
    present = {
        figure: rows[0][figure]
        for figure in ("workload_mean", "workload_median")
        if rows[0][figure] is not None
    }
    assert not present, (
        f"{present} are reported for a course week in which nobody submitted a workload figure; "
        f"the whole row is {rows[0]}. Null is the honest answer."
    )


def test_the_workload_function_answers_one_row_for_one_course_week(
    benchmark_world: BenchmarkWorld,
) -> None:
    """One row per course week over one set, which is what makes every figure readable.

    Two sections answer in the same course week; the workload-and-counts function
    carries no stream, so that is **one** row.

    **The mutation it exists to survive**: `section_id` or `stream` left in the
    function's `GROUP BY`, producing a row per section or per stream.
    """
    world = benchmark_world.build()
    world.plant_section("one", cohort="U", level=UG)
    world.plant_section("two", cohort="U", level=UG)
    for label in ("one", "two"):
        world.respond(
            label,
            course_week=THE_COURSE_WEEK,
            subject=f"e5-03-one-row-{label}",
            workload=A_WORKLOAD,
            instructor_rating=A_RATING,
            course_rating=A_RATING,
        )

    rows = rows_at(world, SET_FUNCTION, THE_COURSE_WEEK, "one", "two")
    assert (
        len(rows) == 1
    ), f"`{SET_FUNCTION}` answers {len(rows)} rows for one course week over two sections: {rows}."
