"""E4-03 criterion 4 — the workload mean and median, over the stored decimals.

SPEC §3.2 stores the workload figure "as a decimal so reporting can show true
means and medians rather than band midpoints", and §5.1 asks the report for
"workload mean/median for the section … (true numeric statistics — §3.2)". So
`report_workload` owes two numbers per section-week and both have to be exact:
the arithmetic mean of the hours submitted, and the conventional midpoint of the
middle pair where the count is even.

**Every value below is a multiple of half an hour**, which is SPEC §3.2's step,
and the fixtures are chosen so that the two ways of getting this wrong are
visible:

  - **The mean of the odd-count week is 2.9**, which no binary float holds
    exactly. A view that computed it in `double precision` answers
    2.899999999999999911…, and `Decimal("2.9")` is not equal to that — so the
    assertion fails on the value rather than needing anybody to inspect a type.
    This is the "61.5"-shaped fixture the memory warns about, avoided: 61.5 *is*
    exact in binary, so a test written on it passes against a float computation
    and proves nothing.
  - **The median of the even-count week is 2.75**, the midpoint of 2.0 and 3.5.
    `percentile_disc` answers 2.0, an `ORDER BY … LIMIT 1 OFFSET n/2` answers 2.0
    or 3.5, and a mean-as-median answers 3.375. Every one of those is a different
    number here, which is what makes the row discriminate.

A median over half-hour steps is always a multiple of 0.25 and therefore always
exact in binary, so no value of it can expose a `double precision` result — which
is why `test_the_workload_figures_are_exact_decimals_rather_than_floats` asks the
type instead. `percentile_cont` returns `double precision` whatever it is given,
so that cast back is a thing the SQL has to do rather than a thing it gets for
free (E4-03's work order names this trap).
"""

from decimal import Decimal

import pytest
from fixtures.report_views import (
    DEFAULT_COHORT,
    RATING_DISTRIBUTION_VIEW,
    SECOND_COHORT,
    WORKLOAD_VIEW,
    ReportWorld,
)

pytestmark = pytest.mark.integration

WORKLOAD = 5
INSTRUCTOR_RATING = 1

# Cohort `F` runs term weeks 7 to 12; these three are weeks it has.
ODD_COUNT_WEEK = 7
EVEN_COUNT_WEEK = 8
NO_WORKLOAD_WEEK = 9

# Five students' hours, and the two statistics counted by hand from them.
# 0.5 + 1.5 + 3.5 + 4.0 + 5.0 = 14.5, and 14.5 / 5 = 2.9 exactly in decimal and
# in no float. Sorted, the middle value is 3.5.
ODD_COUNT_HOURS = (Decimal("0.5"), Decimal("1.5"), Decimal("3.5"), Decimal("4.0"), Decimal("5.0"))
ODD_COUNT_MEAN = Decimal("2.9")
ODD_COUNT_MEDIAN = Decimal("3.5")

# Four students' hours. 1.5 + 2.0 + 3.5 + 6.5 = 13.5, so the mean is 3.375; the
# middle pair is 2.0 and 3.5, so the conventional median is 2.75. The three wrong
# answers a reader should recognise in a failure are named on the constants below.
EVEN_COUNT_HOURS = (Decimal("1.5"), Decimal("2.0"), Decimal("3.5"), Decimal("6.5"))
EVEN_COUNT_MEAN = Decimal("3.375")
EVEN_COUNT_MEDIAN = Decimal("2.75")
LOWER_OF_THE_MIDDLE_PAIR = Decimal("2.0")
UPPER_OF_THE_MIDDLE_PAIR = Decimal("3.5")

# The two sections' hours for one shared term week, for the boundary below.
HOURS_HERE = (Decimal("2.0"), Decimal("3.0"))
HOURS_THERE = (Decimal("8.0"), Decimal("9.0"))
MEAN_HERE = Decimal("2.5")
MEAN_THERE = Decimal("8.5")


def submit_hours(world: ReportWorld, hours: tuple[Decimal, ...], *, week: int, cohort: str) -> None:
    """One student per figure, each submitting that week's workload answer and nothing else."""
    for index, value in enumerate(hours):
        student = world.student(f"e4-03-workload-{cohort}-{week}-{index}", cohorts=(cohort,))
        world.respond(student, term_week=week, cohort=cohort, answers={WORKLOAD: value})


def test_the_workload_mean_is_the_exact_decimal_mean_of_the_hours_submitted(
    report_world: ReportWorld,
) -> None:
    """Criterion 4's first half: the mean, at a value only exact arithmetic reaches.

    Five students submit 0.5, 1.5, 3.5, 4.0 and 5.0 hours. Their mean is 2.9 —
    a number `double precision` cannot hold, so this fails on the value if the
    view computes in floating point anywhere along the way. The median of the same
    week is asserted beside it because an odd count is the other half of the
    boundary pair the even-count week below makes.

    **The mutation it exists to survive**: `avg` computed over a `float8` cast of
    the hours, and `avg` replaced by something that drops a row — the smallest or
    the largest — which moves 2.9 to 3.5 or to 2.375.
    """
    world = report_world.build()
    submit_hours(world, ODD_COUNT_HOURS, week=ODD_COUNT_WEEK, cohort=DEFAULT_COHORT)

    row = world.workload(term_week=ODD_COUNT_WEEK)
    assert row is not None, (
        "`report_workload` has no row for the section-week five students submitted a workload "
        f"figure in ({[str(value) for value in ODD_COUNT_HOURS]} hours)."
    )
    assert row["workload_mean"] == ODD_COUNT_MEAN, (
        f"`workload_mean` is {row['workload_mean']!r} where the five submitted figures "
        f"{[str(value) for value in ODD_COUNT_HOURS]} average to exactly {ODD_COUNT_MEAN}.\n\n"
        "A value that prints as 2.9 and fails this comparison is a **float**: 14.5 / 5 in "
        "`double precision` is 2.899999999999999911182158029987, and SPEC §3.2 stores these hours "
        "as a decimal precisely so reporting can show a true mean. A value that is a decimal and "
        "is not 2.9 is arithmetic over the wrong set of rows."
    )
    assert row["workload_median"] == ODD_COUNT_MEDIAN, (
        f"`workload_median` is {row['workload_median']!r} for the sorted hours "
        f"{[str(value) for value in sorted(ODD_COUNT_HOURS)]}, whose middle value is "
        f"{ODD_COUNT_MEDIAN}. An answer of {ODD_COUNT_MEAN} is the mean reported as the median."
    )


def test_an_even_count_weeks_median_is_the_midpoint_of_the_middle_pair(
    report_world: ReportWorld,
) -> None:
    """Criterion 4's second half: "the median of an even-count week is the conventional midpoint".

    Four students submit 1.5, 2.0, 3.5 and 6.5 hours. The middle pair is 2.0 and
    3.5, so the median is 2.75 — a number none of the wrong rules produces.

    **The mutation it exists to survive**: `percentile_cont` swapped for
    `percentile_disc`, which answers 2.0; a hand-rolled median as `ORDER BY …
    OFFSET count/2 LIMIT 1`, which answers 2.0 or 3.5 depending on how the offset
    rounds; and the mean reported as the median, which answers 3.375. The mean is
    asserted here too, so a view that returned one number twice is caught by
    whichever of the two it got wrong.
    """
    world = report_world.build()
    submit_hours(world, EVEN_COUNT_HOURS, week=EVEN_COUNT_WEEK, cohort=DEFAULT_COHORT)

    row = world.workload(term_week=EVEN_COUNT_WEEK)
    assert row is not None, (
        "`report_workload` has no row for the section-week four students submitted a workload "
        f"figure in ({[str(value) for value in EVEN_COUNT_HOURS]} hours)."
    )
    assert row["workload_median"] == EVEN_COUNT_MEDIAN, (
        f"`workload_median` is {row['workload_median']!r} for the sorted hours "
        f"{[str(value) for value in sorted(EVEN_COUNT_HOURS)]}. The conventional median of an "
        f"even-count set is the midpoint of its middle pair — ({LOWER_OF_THE_MIDDLE_PAIR} + "
        f"{UPPER_OF_THE_MIDDLE_PAIR}) / 2 = {EVEN_COUNT_MEDIAN}.\n\n"
        f"{LOWER_OF_THE_MIDDLE_PAIR} is `percentile_disc`, which picks an existing row rather than "
        f"interpolating. {UPPER_OF_THE_MIDDLE_PAIR} is the other member of the pair, which is what "
        f"an `OFFSET`-based median returns when the offset rounds up. {EVEN_COUNT_MEAN} is the "
        "mean. SPEC §5.1 asks for true numeric statistics, and §3.2 stores a decimal so this "
        "number can be one."
    )
    assert row["workload_mean"] == EVEN_COUNT_MEAN, (
        f"`workload_mean` is {row['workload_mean']!r} where "
        f"{[str(value) for value in EVEN_COUNT_HOURS]} average to {EVEN_COUNT_MEAN}."
    )


def test_the_workload_figures_are_exact_decimals_rather_than_floats(
    report_world: ReportWorld,
) -> None:
    """The type, because no median value over half-hour steps could expose it.

    Every median this view can produce from SPEC §3.2's 0.5-hour steps is a
    multiple of 0.25, and every multiple of 0.25 is exact in binary — so a median
    returned as `double precision` compares equal to the decimal answer and the
    test above cannot see it. `percentile_cont` returns `double precision`
    whatever it is handed, which makes this the ordinary way the column arrives
    wrong rather than an exotic one.

    It matters beyond tidiness because the payload layer divides and rounds these
    figures and E5 compares them against a comparison set: a float that entered
    here is a float in every figure computed from it, and §3.2's "true means and
    medians rather than band midpoints" is the sentence that would stop being
    true.

    **The mutation it exists to survive**: the `::numeric` cast dropped from the
    median expression, leaving `percentile_cont`'s own `double precision`.
    **The near miss it tolerates**: any decimal *scale* — the comparison is
    numeric, so `2.7500000000` passes and is the same number.
    """
    world = report_world.build()
    submit_hours(world, EVEN_COUNT_HOURS, week=EVEN_COUNT_WEEK, cohort=DEFAULT_COHORT)

    row = world.workload(term_week=EVEN_COUNT_WEEK)
    assert row is not None, "`report_workload` has no row for the week four students answered."

    figures = ("workload_mean", "workload_median")
    floats = sorted(name for name in figures if not isinstance(row[name], Decimal))
    kinds = [f"{name}={row[name]!r}" for name in figures]
    assert not floats, (
        f"{floats} come back as something other than an exact decimal. The row is {kinds}.\n\n"
        "SPEC §3.2 stores the workload figure as a decimal 'so reporting can show true means and "
        "medians rather than band midpoints', and §5.1 asks this report for true numeric "
        "statistics. `percentile_cont(0.5) WITHIN GROUP (ORDER BY …)` answers in `double "
        "precision` however exact its input was, so the median needs a cast back to `numeric`; "
        "`avg` over a numeric column does not."
    )


def test_a_week_whose_responses_carry_no_workload_answer_has_no_workload_row(
    report_world: ReportWorld,
) -> None:
    """A week with submissions and no hours is absent here, not a zero.

    Two students submit an instructor rating and nothing else. The distribution
    has their ratings, and `report_workload` has no row at all — no zero mean, no
    null row.

    The distribution is asserted first and is not ceremony: without it, "the
    workload view has no row" is equally true of a week nothing was submitted in,
    and the two are different states with different causes (`docs/MISTAKES.md`
    entry 3).

    **The mutation it exists to survive**: the workload view built from
    `response` with a `LEFT JOIN` to the hours, which emits a row per response
    with a null mean — an "average workload: —" on a report whose week had no
    workload answer, and a divide-by-null at the payload layer.
    """
    world = report_world.build()
    for index in range(2):
        student = world.student(f"e4-03-no-workload-{index}")
        world.respond(
            student, term_week=NO_WORKLOAD_WEEK, answers={INSTRUCTOR_RATING: Decimal("4")}
        )

    ratings = world.rows(RATING_DISTRIBUTION_VIEW, term_week=NO_WORKLOAD_WEEK)
    assert ratings, (
        "The rating distribution has no row for this week either, so nothing was submitted at all "
        "and the absence below says nothing about the workload view. Two students submitted an "
        "instructor rating in it."
    )

    rows = world.rows(WORKLOAD_VIEW, term_week=NO_WORKLOAD_WEEK)
    assert rows == [], (
        f"`report_workload` returns {rows} for a week whose two responses carry no workload answer."
        " The work order settles the report views as rows for what was answered, with zero-filling "
        "left to E4-07's payload layer: a row here with a null mean is a week that looks answered "
        "and is not."
    )


# **This test alone is `invariant`-marked, and the module is not** — the same call
# and the same reason as its two sibling view modules. The rest of this file is
# §3.2's "true means and medians rather than band midpoints", which is a statistics
# claim. This one is the section boundary: §4.1 item 6. A mean or a median computed
# over more than this section's own responses is a figure about people the reader
# is not entitled to, and §4.1 item 7 says in as many words that a statistic over a
# comparison set is governed exactly as a drawn line is — a figure silently drawn
# from two sections is that rule defeated before E5 has built anything.
@pytest.mark.invariant
def test_a_sections_workload_figures_are_computed_over_its_own_responses(
    report_world: ReportWorld,
) -> None:
    """The cross-section boundary, in both directions, for the statistics as well as the counts.

    Two sections share a term week. Two students in each submit hours, and the two
    means are far apart, so a view that pooled them would answer 5.5 in both
    places — a number neither section's students submitted.

    **The mutation it exists to survive**: `section_id` dropped from the `GROUP
    BY`, which is the same mutation the distribution's cross-section test kills
    and is worth killing twice: a mean is a single number per week, so a pooled
    one is not visibly wrong on a page the way a doubled bar chart is.
    """
    world = report_world.build()
    world.section(SECOND_COHORT)
    submit_hours(world, HOURS_HERE, week=ODD_COUNT_WEEK, cohort=DEFAULT_COHORT)
    submit_hours(world, HOURS_THERE, week=ODD_COUNT_WEEK, cohort=SECOND_COHORT)

    here = world.workload(term_week=ODD_COUNT_WEEK, cohort=DEFAULT_COHORT)
    there = world.workload(term_week=ODD_COUNT_WEEK, cohort=SECOND_COHORT)

    assert here is not None and here["workload_mean"] == MEAN_HERE, (
        f"The first section's workload row is {here}. Its two respondents submitted "
        f"{[str(value) for value in HOURS_HERE]} hours, which average to {MEAN_HERE}. The other "
        f"section's respondents submitted {[str(value) for value in HOURS_THERE]} in the same term "
        "week; pooling all four gives 5.5."
    )
    assert there is not None and there["workload_mean"] == MEAN_THERE, (
        f"The second section's workload row is {there}. Its two respondents submitted "
        f"{[str(value) for value in HOURS_THERE]} hours, which average to {MEAN_THERE}."
    )
