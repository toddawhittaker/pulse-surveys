"""E5-03 criterion 5 — the past-referencing building block: a prior term stands beside this one.

"Prior-term rows aggregate beside current-term rows when the key spans terms —
the past-referencing building block, proven with a planted prior-term section."

SPEC §5.1: "Benchmarks are **past-referencing**: week N of a 12-week section is
compared against week N of 12-week sections of the same level in the current
*and prior* terms, regardless of start date." The E5 breakdown's decision 6 adds
that this reaches "every term retention still holds", with no second horizon.

**Re-pointed by E9-12.** This module read `benchmark_cohort_week`, whose `term_id`
key put each term's cohort on a row of its own for E5-04 to union. E9-12 retires
the view (README decision 10); the union is now done before the arithmetic — the
university resolver answers a population spanning both terms, and
`benchmark_set_week` computes over it. So the two halves of the criterion are
asserted where they now live:

  - **inclusion**: a prior term's section of the same length and level is in the
    current section's university population (and the other way round), so the
    earlier term is resolved rather than filtered away; and
  - **beside, at the same course week**: over that population, the set function
    answers one row at course week 2 counting both terms' sections and people,
    and over each term's section alone it answers that term's own figure — so
    the per-term arithmetic is intact and the union is a union, not a re-weighted
    mean of means.

**Nothing here reads a clock**, which is what the inclusion test kills: the
natural way to write "this term only" is a join to whichever term contains today.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    CURRENT_TERM,
    PRIOR_TERM,
    RESOLVE_UNIVERSITY,
    SET_FUNCTION,
    UG,
    BenchmarkWorld,
    benchmarks_api,
)

pytestmark = pytest.mark.integration

THE_COURSE_WEEK = 2

# One section per term, both twelve-week and undergraduate, both answering their
# second course week. The union's mean, 4.0, is a figure neither term's students
# submitted, so a union is visible as a number.
CURRENT_HOURS = Decimal("2.0")
PRIOR_HOURS = Decimal("6.0")
MEAN_OVER_BOTH_TERMS = Decimal("4.0")


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


def university_of(world: BenchmarkWorld, label: str) -> set[str]:
    world.session.flush()
    return {
        str(section)
        for section in benchmarks_api()[RESOLVE_UNIVERSITY](
            world.session, section_id=world.section_id(label)
        )
    }


def the_row(world: BenchmarkWorld, *labels: str) -> dict[str, Any]:
    rows = [row for row in world.set_week(*labels) if row["course_week"] == THE_COURSE_WEEK]
    assert len(rows) == 1, (
        f"`{SET_FUNCTION}` answered {len(rows)} rows at course week {THE_COURSE_WEEK} over "
        f"{list(labels)}, every one of which answered then: {rows}."
    )
    return rows[0]


def test_a_prior_term_section_is_in_the_current_sections_population(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 5's inclusion half: the earlier term is resolved, not filtered away.

    **The control first:** the current section's population holds the current
    section itself, so a resolver answering nothing cannot pass.

    **The mutation it exists to survive**: the population narrowed to one term —
    a join to the term containing today, an `end_date >= current_date`, or the
    newest term by `ORDER BY start_date DESC LIMIT 1`. Each makes every
    past-referencing figure impossible while every other test stays green.
    """
    world = one_section_in_each_term(benchmark_world)
    now, before = str(world.section_id("now")), str(world.section_id("before"))

    current_population = university_of(world, "now")
    assert now in current_population, (
        f"The control failed: the current section's university population "
        f"{sorted(current_population)} does not hold the section itself."
    )
    assert before in current_population, (
        "The current section's university population does not hold the prior term's twelve-week "
        f"{UG} section. SPEC §5.1 makes benchmarks past-referencing across 'the current *and prior* "
        "terms', and the E5 breakdown's decision 6 puts the horizon at retention."
    )
    assert now in university_of(world, "before"), (
        "The prior section's university population does not hold the current one: the rule is "
        "about a length and a level, and reads no term as 'now'."
    )


def test_the_two_terms_count_beside_each_other_at_one_course_week(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 5's "beside" half: one course week across both terms, each term's own figure intact.

    Over both sections, course week 2 is one row: two sections, two people, a
    mean of 4.0. Over each section alone, the row is that term's own figure. So
    E5-04 can count the minimums over the whole set (breakdown decision 2) and
    no term's arithmetic is lost in the union.

    **The mutation it exists to survive**: a course week derived against the
    wrong term's calendar for the prior section (its response lands at another
    course week and the union row holds one section); a respondent counted once
    per term rather than once per person (two different students here, so 2).
    **The near miss it tolerates**: two terms' sections in one row, which is
    what past-referencing is.
    """
    world = one_section_in_each_term(benchmark_world)

    union = the_row(world, "now", "before")
    current = the_row(world, "now")
    prior = the_row(world, "before")

    assert (union["section_count"], union["respondent_count"]) == (2, 2), (
        f"Over both terms' sections course week {THE_COURSE_WEEK} is {union}; one section and one "
        "student answered it in each term."
    )
    assert union["workload_mean"] == MEAN_OVER_BOTH_TERMS, (
        f"The union's mean is {union['workload_mean']!r}; {CURRENT_HOURS} and {PRIOR_HOURS} hours "
        f"average to {MEAN_OVER_BOTH_TERMS}."
    )
    assert current["workload_mean"] == CURRENT_HOURS and prior["workload_mean"] == PRIOR_HOURS, (
        f"Each term alone answers {current} and {prior}; each section submitted its own term's "
        f"hours ({CURRENT_HOURS}, {PRIOR_HOURS})."
    )
