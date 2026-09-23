"""A cutoff is an aware instant, and a figure's own week must have one — E5-14 battery survivors.

The mutation battery on ce9df73 killed 73 of 76. Two of the survivors were in
`app.services.benchmarks`, and each is a guard nothing exercised:

- **X1** — a cutoff without a time zone is refused. A naive `datetime` handed
  to `timestamptz[]` is read in the connection's time zone, so the same wall-clock
  instant cuts a published week hours earlier or later depending on where the
  database runs: a freeze that moves with a server setting. Deleting the refusal
  left the suite green.
- **X2** — a course week with no cutoff is refused loudly. A workload asked for
  course week 2 with a mapping that names only week 3 has no rule for week 2 at
  all; a service that defaulted (to "now", to "no cut", to an empty answer)
  would show an unfrozen figure or a silent blank. Deleting the refusal left the
  suite green.

Each is asked through the public figure door — `benchmark_workload`, with the
assumed `cutoffs` interface stated in `tests/fixtures/benchmark_views.py` — rather
than through the private helper the guard lives in, so the test holds whatever
shape the guard takes. **Each refusal is required to come from the service, not
from the database**: a `DatabaseError` would mean the value reached the SQL,
which is the thing the guard exists to stop, and would let a deleted guard pass
this test by accident (`docs/MISTAKES.md` entry 3). **Each has its accepted
twin**, in the same world: the aware cutoff, and the week that is named.

Green on ce9df73, where both guards exist; red under the battery's two
mutations. The exception's type and message are not pinned — the work order
settles that the value is refused, not how.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    BENCHMARK_WORKLOAD,
    DEFAULT_SET_POPULATION,
    PINNED_NOW,
    UG,
    BenchmarkWorld,
    a_population,
    benchmarks_api,
    carries,
    mean_and_median,
    serialized_figure,
    spread,
)
from sqlalchemy.exc import DatabaseError

pytestmark = [pytest.mark.integration]

HERO = "hero"
THE_LEAD = "the-lead"
COHORT = "U"
THE_COURSE_WEEK = 2
ANOTHER_WEEK = 3
HOURS = Decimal("2.5")
A_RATING = Decimal("4")

# `PINNED_NOW` with its zone taken off: the same wall-clock instant, naive.
A_NAIVE_CUTOFF = PINNED_NOW.replace(tzinfo=None)


def a_default_set_at_both_minimums(
    world: BenchmarkWorld, *, sections: int, respondents: int
) -> None:
    """The hero, `sections` of its lead's sections, and `respondents` people answering week 2."""
    labels = tuple(f"set-{index}" for index in range(sections))
    world.build()
    world.plant_section(HERO, cohort=COHORT, level=UG)
    for label in labels:
        world.plant_section(label, cohort=COHORT, level=UG)
    world.lead(THE_LEAD, HERO, *labels)
    world.answer_the_plan(
        dict(spread(labels, respondents=respondents, subject_prefix="e5-14-x")),
        course_week=THE_COURSE_WEEK,
        workload=HOURS,
        instructor_rating=A_RATING,
    )
    world.session.flush()


def the_workload(world: BenchmarkWorld, cutoffs: dict[int, datetime]) -> Any:
    """`benchmark_workload` for the hero at course week 2 over its default set."""
    return benchmarks_api()[BENCHMARK_WORKLOAD](
        world.session,
        section_id=world.section_id(HERO),
        population=a_population(DEFAULT_SET_POPULATION),
        course_week=THE_COURSE_WEEK,
        cutoffs=cutoffs,
    )


def refusal_of(call: Any) -> BaseException | None:
    """Run `call`; answer what it raised, or `None`."""
    try:
        call()
    except Exception as refused:
        return refused
    return None


def the_world(world: BenchmarkWorld, contract: Any) -> None:
    minimums = contract.minimums()
    a_default_set_at_both_minimums(
        world,
        sections=minimums[contract.minimum_sections],
        respondents=minimums[contract.minimum_respondents],
    )


def test_a_cutoff_without_a_time_zone_is_refused_by_the_service(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """X1: a naive cutoff never reaches the SQL.

    **The mutation it kills:** the time-zone check in `_cutoff_arguments`
    deleted — the battery's survivor. **Its near miss** is the twin below, the
    same instant with its zone, which is answered.
    """
    the_world(benchmark_world, report_api_contract)

    refused = refusal_of(lambda: the_workload(benchmark_world, {THE_COURSE_WEEK: A_NAIVE_CUTOFF}))

    assert refused is not None, (
        f"`benchmark_workload` answered for a cutoff with no time zone ({A_NAIVE_CUTOFF!r}). A "
        "naive instant bound to `timestamptz` is read in the connection's zone, so the week a "
        "published figure freezes at would move with a server setting."
    )
    assert not isinstance(refused, DatabaseError), (
        f"The naive cutoff was refused by the database ({type(refused).__name__}: {refused}), "
        "which means it reached the SQL — the service's own check did not stop it."
    )


def test_an_aware_cutoff_is_answered(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """X1's twin: the same instant with its zone is answered, with the set's figure.

    **The mutation it kills:** a check that refuses every cutoff, which the test
    above cannot tell from the right one.
    """
    the_world(benchmark_world, report_api_contract)

    mean, _median = mean_and_median(the_workload(benchmark_world, {THE_COURSE_WEEK: PINNED_NOW}))

    assert carries(mean, HOURS), (
        f"With an aware cutoff after every window, the default set's workload mean is "
        f"{serialized_figure(mean)} and does not carry {HOURS}, which every respondent reported."
    )


def test_a_course_week_the_cutoffs_do_not_name_is_refused_by_the_service(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """X2: asked for week 2 with a cutoff for week 3 only, the service refuses loudly.

    **The mutation it kills:** the missing-week check in `_the_weeks_cutoff`
    deleted — the battery's survivor — under which the service defaults the
    cutoff or answers an empty figure. **Its near miss** is the twin below.
    """
    the_world(benchmark_world, report_api_contract)

    refused = refusal_of(lambda: the_workload(benchmark_world, {ANOTHER_WEEK: PINNED_NOW}))

    assert refused is not None, (
        f"`benchmark_workload` answered course week {THE_COURSE_WEEK} with cutoffs naming only "
        f"week {ANOTHER_WEEK}. A week with no cutoff has no freeze rule, and a figure answered "
        "for it is unfrozen or silently blank."
    )
    assert not isinstance(refused, DatabaseError), (
        f"The missing week was refused by the database ({type(refused).__name__}: {refused}), "
        "not by the service's own check."
    )


def test_a_course_week_the_cutoffs_name_is_answered(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """X2's twin: the week named, among others, is answered with the set's figure.

    **The mutation it kills:** a check that refuses a mapping with more than the
    one week, or that looks the week up by position rather than by key.
    """
    the_world(benchmark_world, report_api_contract)

    mean, _median = mean_and_median(
        the_workload(benchmark_world, {ANOTHER_WEEK: PINNED_NOW, THE_COURSE_WEEK: PINNED_NOW})
    )

    assert carries(mean, HOURS), (
        f"Asked for course week {THE_COURSE_WEEK} with a cutoff for it, the default set's workload "
        f"mean is {serialized_figure(mean)} and does not carry {HOURS}."
    )
