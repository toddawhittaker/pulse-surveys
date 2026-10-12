"""E5-03 criterion 7 — the benchmark arithmetic applies no minimum, asserted so the layering is a fact.

"No view applies any minimum: a one-section cohort has a row here (the
suppression decision is E5-04's — asserted so the layering is a fact, not a
hope)."

**Re-pointed by E9-12** (the file keeps its E5-03 name). E9-12 retires the four
cohort views (README decision 10); the arithmetic they did is now done only by
the two `SECURITY DEFINER` set functions, `benchmark_set_week` and
`benchmark_set_rating_week`, over the section set E5-04's service resolves. The
criterion moves with the arithmetic: **no set function applies a minimum** — a
one-section set has a row, carrying the counts that explain how thin it is.

**Deleted, and why:** `test_the_term_axis_applies_no_minimum_either` asserted the
same of the two term-axis views. There is no term-axis arithmetic in SQL any
more — the term axis is assembled by `named_set_series` and the roll-up service
from the set functions, and those are policy layers that **do** apply the
minimums, by design (SPEC §5.5) — so its whole subject was the views.

The E5 breakdown's decomposition note says why the split is worth a test of its
own:

> **01, 03 and 04 split the schema, the arithmetic and the policy.** The views
> expose cohort numbers with no thresholds applied; the service is the only
> place minimums, self-exclusion and past-referencing live. … The alternative —
> views that pre-apply suppression — hides the policy in SQL where the
> chokepoint cannot see it and item 7's invariant cannot plant both sides.

§4.1 item 7's assertion is written by planting a population on each side of the
minimum and requiring the thin one to be suppressed and the thick one shown. If
the *arithmetic* has already dropped the thin population's row, the service
suppresses it for the right-looking reason — there is no figure — and the
invariant passes without the chokepoint ever having been asked
(`docs/MISTAKES.md` entry 9).

SPEC §11 question 1 settles the two minimums at 3 sections and 10 respondents.
The thin worlds below sit at 1 section and 1 respondent, and the control sits at
both minimums, with the respondent count read from `Settings`, so a `HAVING` that
arrived would fail the thin tests and leave the control green, naming itself.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    BENCHMARK_FUNCTIONS,
    INSTRUCTOR_STREAM,
    SET_FUNCTION,
    SET_RATING_FUNCTION,
    UG,
    BenchmarkWorld,
)
from fixtures.report_api import BENCHMARK_MIN_RESPONDENTS, configured_benchmark_minimums

pytestmark = pytest.mark.integration

THE_COURSE_WEEK = 2
THE_COHORT = "U"

THIN_HOURS = Decimal("3.5")
THIN_RATING = Decimal("4")

# The control's world: three sections, and as many respondents as the configured
# respondent minimum, dealt round-robin so every section is answered.
THICK_SECTIONS = 3
THICK_HOURS = Decimal("2.0")
THICK_LABELS = tuple(f"section-{index}" for index in range(THICK_SECTIONS))


def the_configured_respondent_minimum() -> int:
    """`benchmark_min_respondents_default` as `Settings` reads it, from a test body."""
    return configured_benchmark_minimums()[BENCHMARK_MIN_RESPONDENTS]


def a_cohort_of_one_section_and_one_respondent(world: BenchmarkWorld) -> BenchmarkWorld:
    """The thinnest population that can exist: one section, one student, one response."""
    world.build()
    world.plant_section("only", cohort=THE_COHORT, level=UG)
    world.respond(
        "only",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-thin-cohort",
        workload=THIN_HOURS,
        instructor_rating=THIN_RATING,
        course_rating=THIN_RATING,
    )
    return world


def a_cohort_of_three_sections(world: BenchmarkWorld, *, respondents: int) -> BenchmarkWorld:
    """The control: a population at both configured minimums."""
    if respondents < THICK_SECTIONS:
        pytest.fail(
            f"{respondents} respondents cannot answer in all {THICK_SECTIONS} sections, so the "
            "control would not hold the section count it claims."
        )
    world.build()
    for label in THICK_LABELS:
        world.plant_section(label, cohort=THE_COHORT, level=UG)
    for index in range(respondents):
        world.respond(
            THICK_LABELS[index % THICK_SECTIONS],
            course_week=THE_COURSE_WEEK,
            subject=f"e5-03-thick-cohort-{index:02d}",
            workload=THICK_HOURS,
            instructor_rating=THIN_RATING,
            course_rating=THIN_RATING,
        )
    return world


def rows_at_the_week(world: BenchmarkWorld, function: str, *labels: str) -> list[dict[str, Any]]:
    read = world.set_week if function == SET_FUNCTION else world.set_rating_week
    return [row for row in read(*labels) if row["course_week"] == THE_COURSE_WEEK]


@pytest.mark.parametrize("function", sorted(BENCHMARK_FUNCTIONS), ids=sorted(BENCHMARK_FUNCTIONS))
def test_a_one_section_set_has_a_row(benchmark_world: BenchmarkWorld, function: str) -> None:
    """Criterion 7: the thinnest possible set is a row here, and suppression is E5-04's.

    One section, one student, one response. Both set functions answer the row,
    and the counts say exactly how thin it is — which is what E5-04 needs in
    order to suppress it.

    **The mutation it exists to survive**: `HAVING count(DISTINCT section_id) >=
    3`, `HAVING count(DISTINCT <person key>) >= 10`, or a `WHERE` narrowing to
    sets of more than one section, in either function — each reds this and leaves
    `test_a_set_at_every_configured_minimum_has_a_row_too` green.
    """
    world = a_cohort_of_one_section_and_one_respondent(benchmark_world)
    rows = rows_at_the_week(world, function, "only")
    assert rows, (
        f"`{function}` answers no row for a set of one section with one respondent. E5-03's "
        "criterion 7: the suppression decision is E5-04's, made by `comparison_after_suppression` "
        "in `app.services.reporting`. A minimum applied in SQL suppresses the figure *and* the "
        "counts that explain why, so §4.1 item 7's invariant can no longer plant both sides."
    )


def test_the_thin_sets_row_carries_the_counts_that_explain_it(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The counts are 1 and 1, which is what makes the row useful to the layer above.

    **The mutation it exists to survive**: a `greatest(count(...), 3)` or a
    `NULLIF` on either count, and the figure suppressed while the row is kept.
    """
    world = a_cohort_of_one_section_and_one_respondent(benchmark_world)
    rows = rows_at_the_week(world, SET_FUNCTION, "only")
    assert len(rows) == 1, f"`{SET_FUNCTION}` answered {rows} for the one-section set."
    row = rows[0]
    assert row["section_count"] == 1, (
        f"`section_count` is {row['section_count']!r} for a set of exactly one section. E5-04 "
        "compares it against `benchmark_min_sections_default`."
    )
    assert row["respondent_count"] == 1, (
        f"`respondent_count` is {row['respondent_count']!r} for a set one student answered. E5-04 "
        "compares it against `benchmark_min_respondents_default` (`docs/MISTAKES.md` entry 50)."
    )
    assert row["workload_mean"] == THIN_HOURS, (
        f"`workload_mean` is {row['workload_mean']!r} where the one respondent submitted "
        f"{THIN_HOURS} hours. A function that suppressed the figure and kept the row would be the "
        "same policy in a quieter place."
    )


def test_the_thin_sets_rating_row_is_there(benchmark_world: BenchmarkWorld) -> None:
    """The rating function applies no minimum either, which is the closed-set half.

    §4.1 item 7 says "a mean, a median, or **any other statistic**"; if the rating
    function withheld a thin set's row while the workload one kept it, half the
    suppression would be in SQL and half at the chokepoint.

    **The mutation it exists to survive**: a `HAVING` added to the rating function
    only.
    """
    world = a_cohort_of_one_section_and_one_respondent(benchmark_world)
    rows = [
        row
        for row in rows_at_the_week(world, SET_RATING_FUNCTION, "only")
        if row["stream"] == INSTRUCTOR_STREAM
    ]
    assert len(rows) == 1, (
        f"`{SET_RATING_FUNCTION}` answered {rows} for the {INSTRUCTOR_STREAM} stream of a "
        f"one-section set, where one student rated {THIN_RATING}."
    )
    assert (
        rows[0]["rating_count"] == 1 and rows[0]["rating_mean"] == THIN_RATING
    ), f"The thin set's instructor rating row is {rows[0]}; one student rated {THIN_RATING}."


@pytest.mark.parametrize("function", sorted(BENCHMARK_FUNCTIONS), ids=sorted(BENCHMARK_FUNCTIONS))
def test_a_set_at_every_configured_minimum_has_a_row_too(
    benchmark_world: BenchmarkWorld, function: str
) -> None:
    """The control, and the half that has to stay green.

    Three sections and as many distinct respondents as
    `benchmark_min_respondents_default`, read from `Settings`. Both functions
    answer a row. If a minimum is added to a function, this stays green and the
    thin tests go red, so the failure reads as "a threshold was applied" rather
    than "the functions answer nothing" (`docs/MISTAKES.md` entry 3). If a value
    makes this world thin, the world grows; the assertion does not move.
    """
    respondents = the_configured_respondent_minimum()
    world = a_cohort_of_three_sections(benchmark_world, respondents=respondents)
    rows = rows_at_the_week(world, function, *THICK_LABELS)
    assert rows, (
        f"`{function}` answers no row for a set of {THICK_SECTIONS} sections and {respondents} "
        "respondents, at both minimums. This is the control for the thin tests in this module."
    )
    if function == SET_FUNCTION:
        assert rows[0]["section_count"] == THICK_SECTIONS, (
            f"`section_count` is {rows[0]['section_count']!r} where {THICK_SECTIONS} sections "
            f"answered. The row is {rows[0]}."
        )
