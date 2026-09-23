"""E5-03 criterion 5 — the past-referencing building block, at the grain the views have.

"Prior-term rows aggregate beside current-term rows when the key spans terms —
the past-referencing building block, proven with a planted prior-term section."

SPEC §5.1: "Benchmarks are **past-referencing**: week N of a 12-week section is
compared against week N of 12-week sections of the same level in the current
*and prior* terms, regardless of start date." The E5 breakdown's decision 6 adds
that this reaches "every term retention still holds", with no second horizon.

**"Beside", not "into", and that is what the ruling's key makes it.** Both
cohort views carry `term_id` as a key column, so a prior term's responses are a
*second row* at the same length, level and course week rather than rows merged
into the current term's figures. That is the shape E5-04 needs: §5.1's
comparison set spans terms and its minimums are counted over the whole set, so
the service unions the rows and applies the policy — and it can only do that if
the arithmetic per term is intact and the terms are distinguishable. A view that
merged them would make a per-term figure unrecoverable, and a view that dropped
the prior one would make past-referencing silently impossible while every other
test in this suite stayed green.

So this module asserts two things, one per side:

  - the prior term's row **exists**, at the same course week as the current
    term's, which is the inclusion half; and
  - the two rows are **separate and each complete**, which is the separation
    half.

**Nothing here reads a clock.** These views take no `now`, so "the current term"
is not a thing they can ask for — which is exactly the mutation the first test
kills, because the natural way to write that filter is a join to whichever term
contains today.
"""

from decimal import Decimal

import pytest
from fixtures.benchmark_views import (
    COHORT_WEEK_VIEW,
    CURRENT_TERM,
    PRIOR_TERM,
    UG,
    BenchmarkWorld,
    require_benchmark_view,
)

pytestmark = pytest.mark.integration

TWELVE_WEEKS = 12
THE_COURSE_WEEK = 2

# One section per term, both twelve-week and undergraduate, both answering their
# second course week. The hours are far apart so that a merged row — the
# mutation where `term_id` leaves the key — is 4.0, a figure neither term's
# students submitted.
CURRENT_HOURS = Decimal("2.0")
PRIOR_HOURS = Decimal("6.0")
MEAN_IF_THE_TERMS_ARE_MERGED = Decimal("4.0")


def one_section_in_each_term(world: BenchmarkWorld) -> BenchmarkWorld:
    """A twelve-week undergraduate section in this term and one in the term before it."""
    world.build()
    world.build_prior_term()
    world.plant_section("now", cohort="U", level=UG, term=CURRENT_TERM)
    world.plant_section("before", cohort="U", level=UG, term=PRIOR_TERM)
    world.respond(
        "now",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-current-term",
        workload=CURRENT_HOURS,
    )
    world.respond(
        "before",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-prior-term",
        workload=PRIOR_HOURS,
    )
    return world


def test_a_prior_term_section_has_its_own_row_at_the_same_course_week(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 5's inclusion half: the earlier term is computed, not filtered away.

    The prior term's twelve-week undergraduate cohort has a row at course week
    2, carrying its own section, its own respondent and its own mean. §5.1 makes
    the comparison reach "the current *and prior* terms", and the E5 breakdown's
    decision 6 puts the horizon at retention rather than at a term count — so a
    view that computed only the newest term would make every past-referencing
    figure in E5-04 impossible to build, and would do it without failing
    anything else here.

    **The current term's row is asserted first**, and not as ceremony: "the
    prior term has a row" says nothing on its own about *which* row is which if
    the view emitted one row for both terms, and a world where neither term
    reached the view would fail this test for a reason that has nothing to do
    with past-referencing (`docs/MISTAKES.md` entry 3).

    **The mutation it exists to survive**: the view narrowed to one term — a
    join to the term containing `current_date`, a `WHERE term.end_date >=
    current_date`, or an `ORDER BY term.start_date DESC LIMIT 1` in a subquery.
    Each of those is how "the benchmark" quietly becomes "this term's
    benchmark", and each also puts a clock inside a view that is supposed to be
    a pure aggregate over stored rows.
    """
    world = one_section_in_each_term(benchmark_world)

    current = world.cohort_week(
        length_weeks=TWELVE_WEEKS, level=UG, course_week=THE_COURSE_WEEK, term=CURRENT_TERM
    )
    assert current is not None, (
        f"`{COHORT_WEEK_VIEW}` has no row for the current term's twelve-week {UG} cohort at course "
        "week 2, which one section answered. The prior-term assertion below would be about a view "
        "that computes nothing at all rather than about past-referencing."
    )

    prior = world.cohort_week(
        length_weeks=TWELVE_WEEKS, level=UG, course_week=THE_COURSE_WEEK, term=PRIOR_TERM
    )
    assert prior is not None, (
        f"`{COHORT_WEEK_VIEW}` has no row for the **prior** term's twelve-week {UG} cohort at "
        f"course week {THE_COURSE_WEEK}, where one section submitted {PRIOR_HOURS} hours. The "
        f"current term's row is there ({current}), so the view is computing — it is computing one "
        "term.\n\n"
        "SPEC §5.1 makes benchmarks past-referencing across 'the current *and prior* terms', and "
        "the E5 breakdown's decision 6 puts the horizon at whatever retention still holds rather "
        "than at a term count. A view that answers for the newest term only cannot be unioned into "
        "one by E5-04, and the usual way it happens is a filter that reads a clock — which is also "
        "a clock inside a view that is otherwise a pure aggregate over stored rows."
    )
    assert (
        prior["workload_mean"] == PRIOR_HOURS
    ), f"The prior term's row is {prior}; its one section submitted {PRIOR_HOURS} hours."


def test_the_two_terms_rows_are_separate_and_each_complete(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 5's separation half: `term_id` is a key column, so a term is a row.

    Each term's row holds one section, one respondent and its own mean. A single
    row over both terms would be the same responses reported as one cohort — and
    the figure a reader would see is 4.0, which is neither term's answer.

    That matters beyond tidiness. E5-04 applies `benchmark_min_sections_default`
    and `benchmark_min_respondents_default` to a comparison set that spans terms
    (breakdown decision 2), and it can only count the sections and the people in
    that set correctly if the per-term rows are intact — a merged row hands it a
    pre-aggregated mean it cannot re-weight, and a mean of means is not a mean.

    **The mutation it exists to survive**: `term_id` dropped from the `GROUP BY`
    or from the select list, which merges the two rows into one carrying 4.0.
    **The near miss it tolerates**: two sections of one term, which are one row
    and must stay one — asserted by the section count being 1 in each of these
    two rows rather than by an absence.
    """
    world = one_section_in_each_term(benchmark_world)
    require_benchmark_view(world.session, COHORT_WEEK_VIEW)

    current = world.cohort_week(
        length_weeks=TWELVE_WEEKS, level=UG, course_week=THE_COURSE_WEEK, term=CURRENT_TERM
    )
    prior = world.cohort_week(
        length_weeks=TWELVE_WEEKS, level=UG, course_week=THE_COURSE_WEEK, term=PRIOR_TERM
    )
    assert current is not None and prior is not None, (
        f"One of the two terms has no row at course week {THE_COURSE_WEEK}: current={current}, "
        f"prior={prior}. Which of them is missing is diagnosed by "
        "`test_a_prior_term_section_has_its_own_row_at_the_same_course_week` in this module; this "
        "test is about the two of them being separate."
    )

    assert current["term_id"] != prior["term_id"], (
        "The two rows carry the same `term_id`, so they are one cohort reported twice rather than "
        "two terms. The world plants one section in each of two terms."
    )
    assert current["section_count"] == 1 and current["workload_mean"] == CURRENT_HOURS, (
        f"The current term's row is {current}. Its one section submitted {CURRENT_HOURS} hours; "
        f"the prior term's submitted {PRIOR_HOURS}, and {MEAN_IF_THE_TERMS_ARE_MERGED} is the two "
        "of them averaged together — which is what a view with no term in its key answers, in both "
        "rows at once."
    )
    assert prior["section_count"] == 1 and prior["workload_mean"] == PRIOR_HOURS, (
        f"The prior term's row is {prior}. Its one section submitted {PRIOR_HOURS} hours, and a "
        f"mean of {MEAN_IF_THE_TERMS_ARE_MERGED} here is the current term's response folded in."
    )
    assert current["respondent_count"] == 1 and prior["respondent_count"] == 1, (
        f"The respondent counts are {current['respondent_count']!r} and "
        f"{prior['respondent_count']!r}. One student answered in each term, and they are different "
        "students; a 2 in either row is the other term's respondent counted here."
    )
