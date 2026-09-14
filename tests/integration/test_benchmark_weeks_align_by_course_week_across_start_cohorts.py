"""E5-03 criterion 4 — week N with week N, never with the calendar twin.

"Week alignment is course-week: week 2 of a section started 9/7 aggregates with
week 2 of one started 8/17, not with its calendar twin — asserted with two
cohorts §2.2's Fall seed actually contains."

SPEC §5.1: "Benchmarks are **past-referencing**: week N of a 12-week section is
compared against week N of 12-week sections of the same level in the current
*and prior* terms, regardless of start date." And SPEC §2.2 gives the reason a
term week cannot stand in for a course week: "averaging week-3-of-course across
cohorts that began five weeks apart would be meaningless."

**The two cohorts are the seed's own.** §2.2's Fall 2026 start-letter map has
"12-week U/R/Q starting 8/17, 9/7, 9/28", and `tests/fixtures/survey_windows.py`
transcribes it from `scripts/seed.py`. `U` runs from term week 1 and `R` from
term week 4, so:

  - course week 2 of `U` is **term week 2**;
  - course week 2 of `R` is **term week 5**;
  - course week 5 of `U` is **term week 5** — `R`'s course week 2's calendar
    twin, and the row it must not be in.

One world holds all three facts, so the match and the mismatch are asserted
against the same rows rather than against two worlds that could differ for
another reason.

**The property at the foot of the file is the general case.** Two cohorts prove
the rule is not "the term week"; they do not prove it is not "the term week
minus four". The Hypothesis property draws any of the twenty seeded cohorts and
any course week inside its length, and requires the row to be keyed by the
course week drawn — which is the whole start-letter map rather than the two
letters a hand-written test happened to pick (`docs/MISTAKES.md` entry 15 is a
generator that excluded the case its own docstring named, so the draw includes
the three-week cohorts and the ones that start in the term's first week, where
the two axes agree).
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    COHORT_WEEK_VIEW,
    UG,
    BenchmarkWorld,
    require_benchmark_view,
)
from fixtures.survey_windows import SEEDED_COHORTS
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

pytestmark = pytest.mark.integration

TWELVE_WEEKS = 12

# §2.2's Fall 2026 map, for the two cohorts this module is written on. Written
# out rather than read from `SEEDED_COHORTS`, because these three numbers are
# what the test *claims* and the transcription is what
# `test_the_benchmark_calendar_literals_are_the_seeded_start_letter_map` checks:
# a test that read its own expectation out of the table it is asserting about
# would agree with any table (`docs/MISTAKES.md` entry 19).
EARLY_COHORT = "U"  # 12 weeks, starts 2026-08-17, the term's first week
LATE_COHORT = "R"  # 12 weeks, starts 2026-09-07, the term's fourth week
THE_COURSE_WEEK = 2
EARLY_TERM_WEEK_FOR_COURSE_WEEK_TWO = 2
LATE_TERM_WEEK_FOR_COURSE_WEEK_TWO = 5
THE_TWIN_COURSE_WEEK = 5  # of the early cohort — the same term week as the late cohort's week 2

# Hours far enough apart that every wrong grouping is a different number:
#
#   - aligned by course week (right):   2.0 and 3.0 together -> 2.5
#   - aligned by term week (the twin):  3.0 and 7.0 together -> 5.0
#   - everything in one row:            2.0, 3.0, 7.0        -> 4.0
EARLY_WEEK_TWO_HOURS = Decimal("2.0")
LATE_WEEK_TWO_HOURS = Decimal("3.0")
EARLY_WEEK_FIVE_HOURS = Decimal("7.0")

ALIGNED_MEAN = Decimal("2.5")
MEAN_IF_ALIGNED_BY_TERM_WEEK = Decimal("5.0")
MEAN_IF_EVERYTHING_IS_ONE_ROW = Decimal("4.0")

# The property's own figure. One section, one response, so the only thing it can
# get wrong is which row the response lands in.
A_PROPERTY_WORKLOAD = Decimal("4.5")


def two_start_cohorts(world: BenchmarkWorld) -> BenchmarkWorld:
    """One 8/17 section and one 9/7 section, twelve weeks and undergraduate both."""
    world.build()
    world.plant_section("early", cohort=EARLY_COHORT, level=UG)
    world.plant_section("late", cohort=LATE_COHORT, level=UG)

    world.respond(
        "early",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-early-week-two",
        workload=EARLY_WEEK_TWO_HOURS,
    )
    world.respond(
        "late",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-late-week-two",
        workload=LATE_WEEK_TWO_HOURS,
    )
    world.respond(
        "early",
        course_week=THE_TWIN_COURSE_WEEK,
        subject="e5-03-early-week-five",
        workload=EARLY_WEEK_FIVE_HOURS,
    )
    return world


def test_course_week_two_of_two_start_cohorts_is_one_row(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 4's match half: week 2 with week 2, five weeks apart on the calendar.

    The two sections started three weeks apart, so their second course weeks are
    three term weeks apart. §5.1 compares "week N … regardless of start date",
    so both belong to one cohort row: two sections, two respondents, a mean of
    2.5.

    **The premise is asserted before the property.** Both responses are required
    to have reached the view — through the section count — because "the two are
    in one row" is trivially true of a row holding one of them and a view that
    lost the late cohort entirely would otherwise read as a pass with a wrong
    mean nobody looked at.

    **The mutation it exists to survive**: `course_week` computed as the `week`
    row's own number, which is the calendar twin and puts these two responses
    three rows apart; and the offset frozen at the term's first week — `week
    number - term.first_week + 1` — which is the same thing written as if it
    were arithmetic about the section.
    """
    world = two_start_cohorts(benchmark_world)

    row = world.cohort_week(length_weeks=TWELVE_WEEKS, level=UG, course_week=THE_COURSE_WEEK)
    assert row is not None, (
        f"`{COHORT_WEEK_VIEW}` has no row at course week {THE_COURSE_WEEK} for the "
        f"{TWELVE_WEEKS}-week {UG} cohort, in which two sections answered their second course "
        f"week — one started 8/17 in term week {EARLY_TERM_WEEK_FOR_COURSE_WEEK_TWO}, the other "
        f"9/7 in term week {LATE_TERM_WEEK_FOR_COURSE_WEEK_TWO}. An absent row here would make "
        "every assertion below vacuous."
    )
    assert row["section_count"] == 2, (
        f"`section_count` is {row['section_count']!r} at course week {THE_COURSE_WEEK}. Both "
        "planted sections answered their second course week, and §5.1 aligns week N with week N "
        "'regardless of start date'. A 1 means the second cohort's response landed in some other "
        f"row — most likely at course week {THE_TWIN_COURSE_WEEK}, its term week, which is what "
        "the test below is about."
    )
    assert row["workload_mean"] == ALIGNED_MEAN, (
        f"`workload_mean` is {row['workload_mean']!r} at course week {THE_COURSE_WEEK}. The two "
        f"sections' second weeks carry {EARLY_WEEK_TWO_HOURS} and {LATE_WEEK_TWO_HOURS} hours, a "
        f"mean of {ALIGNED_MEAN}. {MEAN_IF_EVERYTHING_IS_ONE_ROW} is all three responses in one "
        "row, which is a view with no week in its key at all."
    )


def test_the_calendar_twin_week_is_not_aggregated_with_it(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 4's mismatch half, on the same world: the term week is not the course week.

    The early cohort's course week 5 falls in term week 5, which is also where
    the late cohort's course week 2 falls. §2.2 is explicit that these are not
    the same week for this purpose — "averaging week-3-of-course across cohorts
    that began five weeks apart would be meaningless" — so course week 5 is the
    early section's week and nobody else's: one section, a mean of 7.0.

    **The mutation it exists to survive**: exactly the one above, seen from the
    other side. A view keyed on the term week puts the late cohort's second week
    in this row and answers 5.0 — the mean of two sections at two quite
    different points in their own courses, which is the number §2.2's sentence
    exists to prevent. Asserted twice, from both ends, because a single-sided
    test is satisfied by a view that lost a row rather than misplaced one.
    """
    world = two_start_cohorts(benchmark_world)
    require_benchmark_view(world.session, COHORT_WEEK_VIEW)

    row = world.cohort_week(length_weeks=TWELVE_WEEKS, level=UG, course_week=THE_TWIN_COURSE_WEEK)
    assert row is not None, (
        f"`{COHORT_WEEK_VIEW}` has no row at course week {THE_TWIN_COURSE_WEEK}, which the early "
        f"section answered with {EARLY_WEEK_FIVE_HOURS} hours. The assertions below would be "
        "vacuous, and 'the late cohort is not in this row' would be true of an empty result."
    )
    assert row["section_count"] == 1, (
        f"`section_count` is {row['section_count']!r} at course week {THE_TWIN_COURSE_WEEK}. Only "
        "the 8/17 section is five course weeks in; the 9/7 section is two course weeks in, and "
        f"they share term week {LATE_TERM_WEEK_FOR_COURSE_WEEK_TWO} rather than a course week."
    )
    assert row["workload_mean"] == EARLY_WEEK_FIVE_HOURS, (
        f"`workload_mean` is {row['workload_mean']!r} at course week {THE_TWIN_COURSE_WEEK}, where "
        f"one section submitted {EARLY_WEEK_FIVE_HOURS} hours. "
        f"{MEAN_IF_ALIGNED_BY_TERM_WEEK} is the calendar twin folded in — the late cohort's second "
        f"course week, which falls in the same term week — and that is the figure §2.2 calls "
        "meaningless."
    )


@pytest.mark.slow
@settings(
    max_examples=30,
    deadline=None,
    # The database session is function-scoped, so Hypothesis is right to warn
    # that examples share it. Each one runs inside its own savepoint and rolls
    # back, which is the state reset the health check is asking about — the same
    # shape `tests/integration/test_at_most_one_survey_window_is_open_at_a_time.py`
    # uses.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(data=st.data(), letter=st.sampled_from(sorted(SEEDED_COHORTS)))
def test_a_response_lands_in_the_course_week_the_start_letter_map_puts_it_in(
    data: st.DataObject, letter: str, benchmark_world: BenchmarkWorld, db_session: Any
) -> None:
    """Criterion 4 over the whole start-letter map, not the two letters a test picked.

    A cohort letter is drawn from all twenty §2.2 seeds and a course week from
    inside that cohort's own length. One section, one response, and the row it
    lands in has to be keyed by the course week drawn.

    **Every letter is in the draw, including the ones where the two axes agree.**
    A cohort starting in the term's first week cannot tell a course week from a
    term week, and the three-week cohorts are the shortest thing in the map;
    excluding either would be `docs/MISTAKES.md` entry 15 — a generator that
    skipped the case its own docstring named. They are in, and they are why the
    assertion is stated as "the row is keyed by the drawn course week" rather
    than as "the row is not keyed by the term week".

    **What this adds over the two hand-written cases above**: those prove the
    key is not the term week. This proves it is not the term week minus a
    constant, not the term week for one length and the course week for another,
    and not an offset read off the term rather than off the section — because
    the offset differs per letter and every letter is drawn.

    **The mutation it exists to survive**: a course week special-cased for one
    length (`CASE WHEN length_weeks = 12 THEN … ELSE week.number END`), and an
    offset computed from the term's own start rather than from the section's,
    which is right for exactly the cohorts that start in term week 1 — six of
    the twenty, so a hand-written test has a fair chance of drawing one.
    """
    savepoint = db_session.begin_nested()
    try:
        length_weeks, first_term_week, start = SEEDED_COHORTS[letter]
        course_week = data.draw(st.integers(min_value=1, max_value=length_weeks), label="week")

        world = benchmark_world.build()
        world.plant_section("drawn", cohort=letter, level=UG)
        world.respond(
            "drawn",
            course_week=course_week,
            subject=f"e5-03-property-{letter}-{course_week}",
            workload=A_PROPERTY_WORKLOAD,
        )

        row = world.cohort_week(length_weeks=length_weeks, level=UG, course_week=course_week)
        assert row is not None, (
            f"`{COHORT_WEEK_VIEW}` has no row at course week {course_week} of the "
            f"{length_weeks}-week {UG} cohort. One section of start cohort {letter!r} — which "
            f"§2.2's seed starts in term week {first_term_week}, on {start} — answered that "
            f"course week with {A_PROPERTY_WORKLOAD} hours, so the row is somewhere: most likely "
            f"at course week {first_term_week + course_week - 1}, which is the term week the "
            "response hangs on and what a view keyed off `week.number` would answer."
        )
        assert row["section_count"] == 1 and row["workload_mean"] == A_PROPERTY_WORKLOAD, (
            f"The row at course week {course_week} of the {length_weeks}-week cohort is {row}. "
            f"One section of cohort {letter!r} answered it with {A_PROPERTY_WORKLOAD} hours, and "
            "nothing else in this world answered anything."
        )
    finally:
        savepoint.rollback()
