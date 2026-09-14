"""E5-03 criterion 7 — no view applies a minimum, asserted so the layering is a fact.

"No view applies any minimum: a one-section cohort has a row here (the
suppression decision is E5-04's — asserted so the layering is a fact, not a
hope)."

The E5 breakdown's decomposition note says why the split is worth a test of its
own:

> **01, 03 and 04 split the schema, the arithmetic and the policy.** The views
> expose cohort numbers with no thresholds applied; the service is the only
> place minimums, self-exclusion and past-referencing live. … The alternative —
> views that pre-apply suppression — hides the policy in SQL where the
> chokepoint cannot see it and item 7's invariant cannot plant both sides.

That last clause is the whole reason this module exists. §4.1 item 7's assertion
is written by planting a cohort on each side of the minimum and requiring the
thin one to be suppressed and the thick one shown. If the *view* has already
dropped the thin cohort's row, the service suppresses it for the right-looking
reason — there is no figure — and the invariant passes without the chokepoint
ever having been asked. A guard that cannot see the case it is guarding is
`docs/MISTAKES.md` entry 9 wearing a green tick.

`backend/app/config.py` has carried `benchmark_min_sections_default` = 3 and
`benchmark_min_respondents_default` = 15 since E0, and the breakdown's decision
10 leaves both unsettled until E5-14. So the worlds below sit at 1 section and 1
respondent — under any minimum anybody might rule — and the control sits above
both, so a `HAVING` that arrived would fail the first and leave the second
green, naming itself.
"""

from decimal import Decimal

import pytest
from fixtures.benchmark_views import (
    BENCHMARK_VIEWS,
    COHORT_RATING_WEEK_VIEW,
    COHORT_WEEK_VIEW,
    COURSE_WEEK_VIEWS,
    INSTRUCTOR_STREAM,
    TERM_AXIS_VIEWS,
    UG,
    WORKLOAD_VIEWS,
    BenchmarkWorld,
    require_benchmark_view,
)
from fixtures.survey_windows import SEEDED_COHORTS

pytestmark = pytest.mark.integration

TWELVE_WEEKS = 12
THE_COURSE_WEEK = 2
THE_COHORT = "U"
# `U` starts in the term's first week, so its second course week is term week 2.
THE_TERM_WEEK = 2
THE_START_DATE = SEEDED_COHORTS[THE_COHORT][2]

THIN_HOURS = Decimal("3.5")
THIN_RATING = Decimal("4")

# The control's world: three sections, well above `benchmark_min_sections_default`
# as `config.py` carries it today, and each with its own respondent. Its job is
# to stay green when the thin world goes red, so that a failure names "a minimum
# was applied" rather than "the view returns nothing".
THICK_SECTIONS = 3
THICK_HOURS = Decimal("2.0")


def a_cohort_of_one_section_and_one_respondent(world: BenchmarkWorld) -> BenchmarkWorld:
    """The thinnest cohort that can exist: one section, one student, one response."""
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


def a_cohort_of_three_sections(world: BenchmarkWorld) -> BenchmarkWorld:
    """The control: a cohort above any minimum this project has configured."""
    world.build()
    for index in range(THICK_SECTIONS):
        label = f"section-{index}"
        world.plant_section(label, cohort=THE_COHORT, level=UG)
        world.respond(
            label,
            course_week=THE_COURSE_WEEK,
            subject=f"e5-03-thick-cohort-{index}",
            workload=THICK_HOURS,
            instructor_rating=THIN_RATING,
            course_rating=THIN_RATING,
        )
    return world


@pytest.mark.parametrize("view", sorted(COURSE_WEEK_VIEWS), ids=sorted(COURSE_WEEK_VIEWS))
def test_a_one_section_cohort_has_a_row_on_the_course_week_axis(
    benchmark_world: BenchmarkWorld, view: str
) -> None:
    """Criterion 7: the thinnest possible cohort is a row here, and suppression is E5-04's.

    One section, one student, one response. Both course-week views carry the
    row, and the counts say exactly how thin it is — which is the information
    E5-04 needs in order to suppress it. A view that withheld the row would
    withhold the *reason* along with the figure.

    **This is asserted as a fact rather than as a hope**, in the criterion's own
    words, because the failure it prevents is invisible from downstream: with a
    `HAVING` in the view, every §4.1 item 7 test E5-05 writes still passes, and
    the chokepoint E4 built to be the one place suppression happens is quietly
    no longer the only one. Two places that both suppress are two places that
    can disagree, and the one in SQL is the one no invariant reads.

    **The mutation it exists to survive**: `HAVING count(DISTINCT section_id) >=
    3`, `HAVING count(DISTINCT <person key>) >= 15`, or a `WHERE` narrowing to
    cohorts with more than one section — each of which reds this and leaves
    `test_a_cohort_above_every_configured_minimum_has_a_row_too` green, which is
    the pair that names the defect as a threshold rather than as an empty view.
    """
    world = a_cohort_of_one_section_and_one_respondent(benchmark_world)

    rows = world.rows(
        view,
        length_weeks=TWELVE_WEEKS,
        level=UG,
        term_id=world.term_id(),
        course_week=THE_COURSE_WEEK,
    )
    assert rows, (
        f"`public.{view}` has no row for a cohort of one section with one respondent. E5-03's "
        "criterion 7: 'No view applies any minimum: a one-section cohort has a row here'. The "
        "suppression decision is E5-04's, and it is made by `comparison_after_suppression` in "
        "`app.services.reporting` — the chokepoint E4 built so that E5 could not route around it "
        "(the E5 breakdown's decision 2). A minimum applied in SQL suppresses the figure *and* the "
        "counts that explain why, so §4.1 item 7's invariant can no longer plant both sides of the "
        "threshold: the thin case looks the same as a cohort nobody answered.\n\n"
        "If this view is empty for some other reason, "
        "`test_a_cohort_above_every_configured_minimum_has_a_row_too` in this module is red too, "
        "and the defect is the arithmetic rather than a threshold."
    )


def test_the_thin_cohorts_row_carries_the_counts_that_explain_it(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The counts are 1 and 1, which is what makes the row useful to the layer above.

    E5-04 compares `section_count` against `benchmark_min_sections_default` and
    `respondent_count` against `benchmark_min_respondents_default` (the
    breakdown's decision 2, both halves). A row that arrived with those figures
    rounded up, floored at a minimum, or omitted would let a thin cohort pass a
    threshold that exists to protect the people in it.

    **The mutation it exists to survive**: a `greatest(count(...), 3)` or a
    `NULLIF` on either count — the shape somebody writes to "make the numbers
    look sensible" — and a `section_count` that counts responses, which is 1
    here too and is caught instead by the module that plants four responses in
    two sections.
    """
    world = a_cohort_of_one_section_and_one_respondent(benchmark_world)

    row = world.cohort_week(length_weeks=TWELVE_WEEKS, level=UG, course_week=THE_COURSE_WEEK)
    assert row is not None, (
        f"`{COHORT_WEEK_VIEW}` has no row for the one-section cohort; the parametrised test above "
        "is where that is diagnosed."
    )
    assert row["section_count"] == 1, (
        f"`section_count` is {row['section_count']!r} for a cohort of exactly one section. "
        "E5-04 compares this figure against `benchmark_min_sections_default`, which "
        "`backend/app/config.py` carries as 3, so a floor applied here would let a one-section "
        "benchmark through as if it were three."
    )
    assert row["respondent_count"] == 1, (
        f"`respondent_count` is {row['respondent_count']!r} for a cohort one student answered. "
        "E5-04 compares it against `benchmark_min_respondents_default`, which is 15 today, and "
        "`docs/MISTAKES.md` entry 50 is what happens when the number crossing a people-protecting "
        "threshold is not a count of people."
    )
    assert row["workload_mean"] == THIN_HOURS, (
        f"`workload_mean` is {row['workload_mean']!r} where the one respondent submitted "
        f"{THIN_HOURS} hours. A view that suppressed the figure and kept the row would be the same "
        "policy in a quieter place."
    )


def test_the_thin_cohorts_rating_row_is_there_for_both_streams(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The rating pair applies no minimum either, which is the closed-set half.

    A guard built against one of two thresholds is the closed-set defeat, and so
    is a rule asserted of one of two view families. §4.1 item 7 says "a mean, a
    median, or **any other statistic**, not only a drawn line" — the rating mean
    is one of those statistics, and if the rating view withheld a thin cohort's
    row while the workload view kept it, half the suppression would be happening
    in SQL and half at the chokepoint.

    **The mutation it exists to survive**: a `HAVING` added to the rating views
    only, which is what happens when the four view files are written from one
    template and the threshold is removed from the two somebody tested.
    """
    world = a_cohort_of_one_section_and_one_respondent(benchmark_world)
    require_benchmark_view(world.session, COHORT_RATING_WEEK_VIEW)

    row = world.cohort_rating_week(
        length_weeks=TWELVE_WEEKS, level=UG, course_week=THE_COURSE_WEEK, stream=INSTRUCTOR_STREAM
    )
    assert row is not None, (
        f"`{COHORT_RATING_WEEK_VIEW}` has no {INSTRUCTOR_STREAM} row for a cohort of one section "
        "with one respondent, which submitted a rating of "
        f"{THIN_RATING}. §4.1 item 7 covers 'a mean, a median, or any other statistic', and the "
        "layer that suppresses all of them is E5-04's chokepoint."
    )
    assert (
        row["rating_count"] == 1 and row["rating_mean"] == THIN_RATING
    ), f"The thin cohort's instructor rating row is {row}; one student rated {THIN_RATING}."


@pytest.mark.parametrize("view", sorted(TERM_AXIS_VIEWS), ids=sorted(TERM_AXIS_VIEWS))
def test_the_term_axis_applies_no_minimum_either(
    benchmark_world: BenchmarkWorld, view: str
) -> None:
    """And the other axis, for the same closed-set reason.

    Four views ship in this ticket and a threshold could arrive in any of them.
    The term axis is the likeliest place for one to be *added later* without
    argument, because decision 7 means nothing in E5 renders it — so the epic
    that draws it is the epic that meets the thin cohort, in E9, where a `HAVING`
    is a two-line change to a file nobody is currently reading.

    **The mutation it exists to survive**: any minimum in either term-axis view.
    """
    world = a_cohort_of_one_section_and_one_respondent(benchmark_world)

    rows = world.rows(
        view,
        length_weeks=TWELVE_WEEKS,
        level=UG,
        term_id=world.term_id(),
        term_week=THE_TERM_WEEK,
        section_start_date=THE_START_DATE,
    )
    assert rows, (
        f"`public.{view}` has no row at term week {THE_TERM_WEEK} for the one-section cohort that "
        f"started {THE_START_DATE}. E5-03 applies no minimum anywhere; E5-04 is the only place a "
        "figure is withheld, and E9 reads these rows through it."
    )


@pytest.mark.parametrize("view", sorted(BENCHMARK_VIEWS), ids=sorted(BENCHMARK_VIEWS))
def test_a_cohort_above_every_configured_minimum_has_a_row_too(
    benchmark_world: BenchmarkWorld, view: str
) -> None:
    """The control, and the half that has to stay green.

    Three sections, three respondents — above `benchmark_min_sections_default`
    as configuration carries it today. Every one of the four views has a row.

    Its job is to be the *other* half of a pair: if a minimum is added to a
    view, this stays green and the thin tests go red, and the failure reads as
    "a threshold was applied" rather than as "the views return nothing". Without
    it the two states are indistinguishable in the output, which is
    `docs/MISTAKES.md` entry 3 in the direction people forget — a red that
    cannot be attributed is nearly as expensive as a green that cannot be
    trusted.

    It is also the one test in this module that must **not** change when the
    minimums are settled at E5-14 (breakdown decision 10). If a future value
    makes this world thin, the world grows; the assertion does not move.
    """
    world = a_cohort_of_three_sections(benchmark_world)

    if view in TERM_AXIS_VIEWS:
        rows = world.rows(
            view,
            length_weeks=TWELVE_WEEKS,
            level=UG,
            term_id=world.term_id(),
            term_week=THE_TERM_WEEK,
            section_start_date=THE_START_DATE,
        )
    else:
        rows = world.rows(
            view,
            length_weeks=TWELVE_WEEKS,
            level=UG,
            term_id=world.term_id(),
            course_week=THE_COURSE_WEEK,
        )

    assert rows, (
        f"`public.{view}` has no row for a cohort of {THICK_SECTIONS} sections and "
        f"{THICK_SECTIONS} respondents, which is above every minimum "
        "`backend/app/config.py` carries. This is the control for the thin-cohort tests in this "
        "module: with it red, their reds say nothing about thresholds, because the views are "
        "answering nothing for anybody."
    )
    if view in WORKLOAD_VIEWS:
        assert rows[0]["section_count"] == THICK_SECTIONS, (
            f"`section_count` is {rows[0]['section_count']!r} where {THICK_SECTIONS} sections "
            f"answered. The row is {rows[0]}."
        )
