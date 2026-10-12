"""E5-03 criterion 6 — §2.2's term axis, one line per start cohort.

"The term-axis view yields one row per start cohort per term week, and a cohort
with no data yields no fabricated zeros."

SPEC §2.2, the two-axes bullet:

> Aggregate pages plot the **term axis** (TERM 01-18) with one line per start
> cohort and a cohort selector (e.g., "U sections · started 8/17") — averaging
> week-3-of-course across cohorts that began five weeks apart would be
> meaningless.

**Re-pointed by E9-12** (the file keeps its E5-03 name). The two term-axis views
this module read are retired by E9-12 (README decision 10); E9 draws the term
axis from the set functions, per start cohort, in `benchmarks.named_set_series`
(E9-05) and in the roll-up service (E9-07). The rules move with it and are
asserted on `named_set_series`, the term-axis read a test can drive at the
service:

  - **one line per start cohort**, keyed by its start date: two cohorts that meet
    at one term week are two lines, each carrying its own figure;
  - **a cohort is a line, not a section**: two sections of one cohort are one
    line, and its figure is over both;
  - **no fabricated zeros**: a week the cohort runs and nobody answered carries
    no number at all (the series answers every week of a published cohort,
    shown or suppressed — E9-05's interface — so the rule is now "no number",
    not "no row");
  - **the streams are separate**: the instructor and course means of one week
    are each their own stream's.

**The world** is E9-05's `PurviewWorld` (`tests/fixtures/named_set_figures.py`):
level `UGGR`, two twelve-week cohorts of §2.2's Fall seed — `U`, started 8/17,
and `R`, started 9/7 — three sections each (the section minimum), each cohort
answered by the respondent minimum, so every figure the series computes is
shown unless the rule under test withholds it. A twelve-week named set holds both
courses, and the reader chairs the department holding everything, so the seal
subtracts nothing (SPEC §5.1). Every expected number is written here.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import serialized_figure
from fixtures.comparison_sets import (
    COMPARISON_SET_TABLE,
    LENGTH_COLUMN,
    LEVEL_COLUMN,
    member_of,
    membership_table,
)
from fixtures.named_set_figures import (
    COURSE_FIGURE,
    INSTRUCTOR_FIGURE,
    LEVEL,
    NAMED_SET_SERIES,
    WEEK_TERM_WEEK_MEMBER,
    WORKLOAD_MEAN,
    PurviewWorld,
    benchmarks_symbol,
    carries_value,
    is_shown,
    member,
    start_dates,
    the_week,
    week_figures,
)

pytestmark = pytest.mark.integration

TWELVE_WEEKS = 12

# §2.2's Fall 2026 seed: "12-week U/R/Q starting 8/17, 9/7, 9/28". Written out
# because these dates are what the assertions claim.
EARLY_COHORT = "U"
EARLY_START = date(2026, 8, 17)
LATE_COHORT = "R"
LATE_START = date(2026, 9, 7)

# Term week 5 is where the two cohorts meet on this axis: the early cohort's fifth
# course week and the late cohort's second.
THE_TERM_WEEK = 5
EARLY_COURSE_WEEK = 5
LATE_COURSE_WEEK = 2
# A week the early cohort runs and nobody answers: its sixth (term week 6).
AN_UNANSWERED_EARLY_COURSE_WEEK = 6

EARLY_HOURS = Decimal("3.0")
LATE_HOURS = Decimal("9.0")
# Equal numbers of people on each side, so a fold is the plain average.
MEAN_IF_THE_COHORTS_ARE_FOLDED = Decimal("6.0")

INSTRUCTOR_RATING = Decimal("2")
COURSE_RATING = Decimal("4")
MEAN_IF_THE_STREAMS_ARE_FOLDED = Decimal("3")

READER = "the reader"


def two_start_cohorts(world: PurviewWorld) -> Any:
    """Three 8/17 sections and three 9/7 sections, both answered at term week 5; the set's key."""
    world.build()
    sections, respondents = world.sections_minimum, world.respondents_minimum
    world.course("early", department="home")
    world.course("late", department="home")
    early = [f"early-{index}" for index in range(sections)]
    late = [f"late-{index}" for index in range(sections)]
    for label in early:
        world.section(label, course="early", cohort=EARLY_COHORT)
    for label in late:
        world.section(label, course="late", cohort=LATE_COHORT)
    world.chair(READER, "home")

    world.answer(
        early,
        respondents=respondents,
        prefix="e9-12-axis-early",
        rating=INSTRUCTOR_RATING,
        course_rating=COURSE_RATING,
        hours=EARLY_HOURS,
        course_week=EARLY_COURSE_WEEK,
    )
    world.answer(
        late,
        respondents=respondents,
        prefix="e9-12-axis-late",
        rating=INSTRUCTOR_RATING,
        course_rating=COURSE_RATING,
        hours=LATE_HOURS,
        course_week=LATE_COURSE_WEEK,
    )

    stored = world.world.seed(
        COMPARISON_SET_TABLE, {}, **{LENGTH_COLUMN: TWELVE_WEEKS, LEVEL_COLUMN: LEVEL}
    )
    for course in ("early", "late"):
        member_of(
            world.world.seed, membership_table(world.world.tables), stored, world.course_row(course)
        )
    world.session.flush()
    return stored[world.key_of(COMPARISON_SET_TABLE)]


def the_series(world: PurviewWorld, set_id: Any) -> Any:
    world.session.flush()
    read = benchmarks_symbol(NAMED_SET_SERIES)
    return read(
        world.session,
        set_id=set_id,
        scope=world.scope(READER),
        term_id=world.world.term_id(),
        settings=world.settings,
    )


def test_two_start_cohorts_at_one_term_week_are_two_lines(purview_world: PurviewWorld) -> None:
    """One line per start cohort, keyed by its start date, each with its own figure at term week 5.

    **Both lines are asserted, with their figures**: the early line's term-week-5
    point carries 3.0 hours and the late line's 9.0; both points sit at term
    week 5.

    **The mutation it exists to survive**: the cohort dropped from the series'
    key (one line at 6.0 — the figure §2.2 calls meaningless), or cohorts keyed by
    start letter rather than start date.
    """
    world = purview_world
    series = the_series(world, two_start_cohorts(world))

    assert sorted(start_dates(series)) == [EARLY_START, LATE_START], (
        f"The series' cohorts start on {start_dates(series)}; the set's sections start on "
        f"{EARLY_START} and {LATE_START}, and §2.2 draws one line per start cohort."
    )
    early = the_week(series, start=EARLY_START, course_week=EARLY_COURSE_WEEK)
    late = the_week(series, start=LATE_START, course_week=LATE_COURSE_WEEK)
    for what, week in (("early", early), ("late", late)):
        assert member(week, WEEK_TERM_WEEK_MEMBER, "A week") == THE_TERM_WEEK, (
            f"The {what} cohort's point is at term week "
            f"{member(week, WEEK_TERM_WEEK_MEMBER, 'A week')}, not {THE_TERM_WEEK}."
        )
    early_mean = week_figures(early)[WORKLOAD_MEAN]
    late_mean = week_figures(late)[WORKLOAD_MEAN]
    assert carries_value(early_mean, EARLY_HOURS) and carries_value(late_mean, LATE_HOURS), (
        f"At term week {THE_TERM_WEEK} the early line's workload mean is "
        f"{serialized_figure(early_mean)} and the late line's {serialized_figure(late_mean)}; "
        f"they answered {EARLY_HOURS} and {LATE_HOURS}. {MEAN_IF_THE_COHORTS_ARE_FOLDED} is the "
        "two cohorts folded into one line."
    )


def test_two_sections_of_one_start_cohort_are_one_line(purview_world: PurviewWorld) -> None:
    """A cohort is a line, not a section: the three 8/17 sections are one cohort entry.

    **The mutation it exists to survive**: the section left in the series' key —
    a cohort per section, each a single section's figures.
    """
    world = purview_world
    series = the_series(world, two_start_cohorts(world))
    starts = start_dates(series)
    assert starts.count(EARLY_START) == 1, (
        f"The series carries {starts.count(EARLY_START)} cohorts starting {EARLY_START}: {starts}. "
        "The set's three sections of that cohort are one line on §2.2's axis."
    )
    figure = week_figures(the_week(series, start=EARLY_START, course_week=EARLY_COURSE_WEEK))
    assert is_shown(figure[WORKLOAD_MEAN]), (
        f"The 8/17 line's point at term week {THE_TERM_WEEK} is {serialized_figure(figure[WORKLOAD_MEAN])}; "
        "its three sections and the respondent minimum meet both minimums, so it is shown only if "
        "the line is over all three."
    )


def test_a_week_nobody_answered_carries_no_fabricated_zero(purview_world: PurviewWorld) -> None:
    """No number for a week the cohort runs and nobody answered; the answered week has one.

    **The answered week is asserted first** (`docs/MISTAKES.md` entry 3).

    **The mutation it exists to survive**: a zero-filled week (`coalesce(...,
    0)`), which draws a line to zero and says something no student said.
    """
    world = purview_world
    series = the_series(world, two_start_cohorts(world))
    answered = week_figures(the_week(series, start=EARLY_START, course_week=EARLY_COURSE_WEEK))
    assert all(
        is_shown(figure) for figure in answered.values()
    ), f"The answered week's figures are {[serialized_figure(f) for f in answered.values()]}."
    empty = week_figures(
        the_week(series, start=EARLY_START, course_week=AN_UNANSWERED_EARLY_COURSE_WEEK)
    )
    carried = {
        name: serialized_figure(figure)
        for name, figure in empty.items()
        if serialized_figure(figure).get("figure") is not None
    }
    assert not carried, (
        f"Course week {AN_UNANSWERED_EARLY_COURSE_WEEK} of the 8/17 cohort, which nobody answered, "
        f"carries {carried}. A week with no data has no figure, never a zero."
    )


def test_the_instructor_and_course_lines_are_each_their_own_streams(
    purview_world: PurviewWorld,
) -> None:
    """The streams are separate: the instructor mean is 2 and the course mean 4, never 3.

    **The mutation it exists to survive**: the stream dropped from the term-axis
    rating read, which averages the two questions into 3.
    """
    world = purview_world
    series = the_series(world, two_start_cohorts(world))
    figures = week_figures(the_week(series, start=EARLY_START, course_week=EARLY_COURSE_WEEK))
    assert carries_value(figures[INSTRUCTOR_FIGURE], INSTRUCTOR_RATING), (
        f"The instructor line is {serialized_figure(figures[INSTRUCTOR_FIGURE])}; everyone rated "
        f"the instructor {INSTRUCTOR_RATING}. {MEAN_IF_THE_STREAMS_ARE_FOLDED} is the streams folded."
    )
    assert carries_value(figures[COURSE_FIGURE], COURSE_RATING), (
        f"The course line is {serialized_figure(figures[COURSE_FIGURE])}; everyone rated the "
        f"course {COURSE_RATING}."
    )
