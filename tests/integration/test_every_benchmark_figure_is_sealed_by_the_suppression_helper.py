"""E5-04 criterion 8 — nothing in the benchmark service can emit an unsealed figure.

> Nothing in the module can emit an unsealed figure: the module's tests drive
> every public function and assert provenance via `refuse_an_unsealed_comparison`.

E4-07 made the comparison type's constructor demand a token private to
`app.services.reporting`, and made the payload boundary re-check every value
whatever built it (ADR 0155). That closes the door a *caller* would walk through.
What it cannot say is that this service went through the helper at all: a
figure assembled by some other route inside `app.services.reporting`'s own
module namespace, or a value copied out of a sealed one, reaches the boundary
looking like anything. `refuse_an_unsealed_comparison` is the question E4-07
left for exactly this ticket to ask, and this module asks it of every figure
every public function answers.

**Every door is driven** — both streams of the default-set trend, both
populations of the workload comparison, the named-set trend, the named-set
workload and the term-axis pass-through — because a chokepoint is defeated one
level out (`docs/MISTAKES.md` entry 22) and a function nobody drove is one level
out. The term-axis door matters most here and is the one E5 does not draw yet:
E5-06's preview and E9 consume it, so a figure that leaves this module unsealed
leaves it towards a surface nobody has written yet.

**The figures are found by type, never by member name.** The work order leaves
`named_set_term_axis`'s row shape to the implementer, so a sweep keyed on a
member would assert nothing about a shape it did not predict — and would go
quietly green the day the shape changed.

**Two canaries, and neither is ceremony** (`docs/MISTAKES.md` entries 3 and 9).
Each door must answer at least one figure, or "every figure was sealed" is a
statement about an empty list. And `refuse_an_unsealed_comparison` must be shown
to refuse *something* — an unsealed value built past the constructor — or the
whole module is satisfied by a check that returns for everything.

**Marked `invariant`**: this is SPEC §4.1 item 7's provenance, and CI runs it in
the isolated pass where a skip is a failure.

**Which failure a red here is, before E5-04 lands.** The service is looked up
inside each test body, so the first red is a FAILED naming
`app.services.benchmarks` (`docs/MISTAKES.md` entry 44).
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    BENCHMARK_TREND,
    BENCHMARK_WORKLOAD,
    COMPARISON_FIGURE_TYPE,
    COURSE_STREAM,
    DEFAULT_SET_POPULATION,
    INSTRUCTOR_STREAM,
    NAMED_SET_TERM_AXIS,
    NAMED_SET_TREND,
    NAMED_SET_WORKLOAD,
    PINNED_NOW,
    PROVENANCE_CHECK,
    UG,
    UNIVERSITY_POPULATION,
    BenchmarkWorld,
    a_population,
    benchmarks_api,
    figures_in,
    reporting_symbol,
    serialized_figure,
    spread,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

HERO = "hero"
THE_LEAD = "the-lead"
COHORT = "U"
LEVEL = UG
TWELVE_WEEKS = 12
THE_COURSE_WEEK = 2

# **The hours are a spread rather than one value, and the mutation battery is why.**
# Every respondent here used to report 2.5, so the cohort's mean and its median
# were both 2.5 — and a mutation that copied one of the two figures over the
# other changed nothing observable in this world. Two thirds report `LOW_HOURS`
# and one third `HIGH_HOURS`, which puts the median on the majority value and the
# mean above it, so the two figures are distinguishable by construction. Nothing
# in this module asserts either number; what the spread buys is that a *later*
# battery run against these doors cannot be undetectable by arithmetic accident.
LOW_HOURS = Decimal("2.5")
HIGH_HOURS = Decimal("8.5")
A_RATING = Decimal("4")


def a_world_every_door_answers_over(
    world: BenchmarkWorld, *, sections: int, respondents: int
) -> None:
    """One world in which all five doors have something to answer.

    The hero's lead leads every other section, so the default set resolves; every
    one of those sections' courses is in a named set, so the named-set doors
    resolve the same population; and everybody answers both a workload figure and
    a rating in both streams, so no door is empty for want of a value. A door
    that answered nothing would make this module vacuous, which is why the world
    is built to satisfy all of them at once and each test says so out loud.

    The hours are split two ways (see `LOW_HOURS`), and the split is taken off
    the plan's own subjects, which `spread` has already dealt round-robin across
    the sections — so every section carries both values and no section's own
    figures are a single number either.
    """
    labels = tuple(f"set-{index}" for index in range(sections))
    world.build()
    world.plant_section(HERO, cohort=COHORT, level=LEVEL)
    for label in labels:
        world.plant_section(label, cohort=COHORT, level=LEVEL)
    world.lead(THE_LEAD, HERO, *labels)
    world.comparison_set("named", length_weeks=TWELVE_WEEKS, level=LEVEL, courses_of=labels)

    plan = dict(spread(labels, respondents=respondents, subject_prefix="e5-04-sealed"))
    subjects = sorted(plan)
    reporting_high = max(1, len(subjects) // 3)
    for hours, group in (
        (HIGH_HOURS, subjects[:reporting_high]),
        (LOW_HOURS, subjects[reporting_high:]),
    ):
        world.answer_the_plan(
            {subject: plan[subject] for subject in group},
            course_week=THE_COURSE_WEEK,
            workload=hours,
            instructor_rating=A_RATING,
            course_rating=A_RATING,
        )
    world.respond(
        HERO,
        course_week=THE_COURSE_WEEK,
        subject="e5-04-sealed-hero",
        workload=LOW_HOURS,
        instructor_rating=A_RATING,
        course_rating=A_RATING,
    )
    world.session.flush()


# E5-14's freeze at close makes a cutoff per course week a required argument of
# the four figure doors (the assumed interface is stated in
# `tests/fixtures/benchmark_views.py`, beside `CUTOFFS_PARAMETER`). This module is
# about provenance, not about the freeze, so every door is asked for the one week
# its world answers with a cutoff after every window: nothing is excluded.
THE_CUTOFFS = {THE_COURSE_WEEK: PINNED_NOW}


def a_default_trend(world: BenchmarkWorld, api: dict[str, Any], stream: str) -> Any:
    return api[BENCHMARK_TREND](
        world.session,
        section_id=world.section_id(HERO),
        population=a_population(DEFAULT_SET_POPULATION),
        stream=stream,
        cutoffs=THE_CUTOFFS,
    )


THE_DOORS = (
    pytest.param(
        lambda world, api: a_default_trend(world, api, INSTRUCTOR_STREAM),
        id="benchmark_trend-instructor",
    ),
    pytest.param(
        lambda world, api: a_default_trend(world, api, COURSE_STREAM),
        id="benchmark_trend-course",
    ),
    pytest.param(
        lambda world, api: api[BENCHMARK_WORKLOAD](
            world.session,
            section_id=world.section_id(HERO),
            population=a_population(DEFAULT_SET_POPULATION),
            course_week=THE_COURSE_WEEK,
            cutoffs=THE_CUTOFFS,
        ),
        id="benchmark_workload-default-set",
    ),
    pytest.param(
        lambda world, api: api[BENCHMARK_WORKLOAD](
            world.session,
            section_id=world.section_id(HERO),
            population=a_population(UNIVERSITY_POPULATION),
            course_week=THE_COURSE_WEEK,
            cutoffs=THE_CUTOFFS,
        ),
        id="benchmark_workload-university",
    ),
    pytest.param(
        lambda world, api: api[NAMED_SET_TREND](
            world.session,
            set_id=world.comparison_set_id("named"),
            stream=INSTRUCTOR_STREAM,
            cutoffs=THE_CUTOFFS,
        ),
        id="named_set_trend",
    ),
    pytest.param(
        lambda world, api: api[NAMED_SET_WORKLOAD](
            world.session,
            set_id=world.comparison_set_id("named"),
            course_week=THE_COURSE_WEEK,
            cutoffs=THE_CUTOFFS,
        ),
        id="named_set_workload",
    ),
    pytest.param(
        lambda world, api: api[NAMED_SET_TERM_AXIS](
            world.session, set_id=world.comparison_set_id("named")
        ),
        id="named_set_term_axis",
    ),
)


@pytest.mark.parametrize("door", THE_DOORS)
def test_every_figure_a_public_benchmark_function_answers_passes_the_provenance_check(
    benchmark_world: BenchmarkWorld,
    report_api_contract: Any,
    pinned_benchmark_clock: Any,
    door: Any,
) -> None:
    """Criterion 8, one public function at a time.

    Every comparison figure this door answers is handed to
    `refuse_an_unsealed_comparison`, which must accept all of them. The check is
    E4-07's own and the ticket names it, so this asserts the property the ticket
    owes rather than a mechanism of this module's choosing: whatever route the
    service takes to a figure, the seal has to be on it.

    **The canary comes first**: the door must answer at least one figure. A door
    that answered none would pass this test with the seal deleted, which is
    `docs/MISTAKES.md` entry 3 in the form this kind of sweep always takes.

    **The mutation it kills:** a `ComparisonFigure` built anywhere in
    `app.services.benchmarks` by a route that does not run
    `comparison_after_suppression` — a `model_copy` of a sealed figure with a new
    number in it, a figure carried over from one week to the next, or a
    convenience constructor added later "for the term axis". Each of those is a
    number on an instructor's chart that no minimum was ever compared against,
    and none of them changes any other assertion in this epic.

    **The near miss it tolerates:** a door that answers a *suppressed* figure.
    Suppressed is a sealed state — it is what the helper returns below either
    minimum — so this test is about provenance and never about whether a number
    is shown. The suppression module beside it owns that half.
    """
    minimums = report_api_contract.minimums()
    a_world_every_door_answers_over(
        benchmark_world,
        sections=minimums[report_api_contract.minimum_sections],
        respondents=minimums[report_api_contract.minimum_respondents],
    )

    api = benchmarks_api()
    figure_type = reporting_symbol(COMPARISON_FIGURE_TYPE)
    refuse = reporting_symbol(PROVENANCE_CHECK)

    answered = door(benchmark_world, api)
    figures = figures_in(answered, figure_type)
    assert figures, (
        f"This door answered {answered!r}, which holds no `{COMPARISON_FIGURE_TYPE}` at all. Every "
        "figure below would then be sealed by default and this test would pass against a service "
        "that had deleted the seal. The world it was asked over stands at both configured "
        "minimums, so the door has something to answer."
    )

    for figure in figures:
        try:
            refuse(figure)
        except Exception as refused:
            pytest.fail(
                f"`{PROVENANCE_CHECK}` refused a figure this door answered: "
                f"{type(refused).__name__}: {refused}. The figure was "
                f"{serialized_figure(figure)}.\n\n"
                "SPEC §4.1 item 7 is enforced at one chokepoint, and a figure that did not come "
                "through `comparison_after_suppression` is a number no minimum was compared "
                "against. E5-04's own criterion: 'the module never constructs a ComparisonFigure "
                "any way but through the helper'."
            )


def test_the_provenance_check_refuses_a_figure_that_never_met_the_helper(
    configured_env: dict[str, str],
) -> None:
    """The discriminating control: the check is not a function that returns for everything.

    Without this, every assertion in this module is satisfied by a
    `refuse_an_unsealed_comparison` whose body is `return None` — a guard nobody
    has watched discriminate, which is `docs/MISTAKES.md` entry 9 and the reason
    E4-07's own chokepoint tests carry canaries of their own.

    **Built past the constructor on purpose.** `model_construct` runs neither
    `__init__` nor a validator, which is precisely how E4-07's security round
    produced an unsealed figure, so it is the shape the check exists to catch and
    the one this control is written in.

    **Green on today's tree** — the check ships with E4-07 — and its value is
    that it goes red the moment the check stops distinguishing anything.
    """
    figure_type = reporting_symbol(COMPARISON_FIGURE_TYPE)
    refuse = reporting_symbol(PROVENANCE_CHECK)

    build = getattr(figure_type, "model_construct", None)
    if not callable(build):
        pytest.fail(
            f"`{COMPARISON_FIGURE_TYPE}` offers no `model_construct`, so this control cannot build "
            "a figure that never met the helper. Another way of producing one is taught here, in "
            "this test; what must not happen is this module asserting that a check accepts "
            "everything it was handed without ever showing that it refuses anything."
        )

    unsealed = build()
    raised: BaseException | None = None
    try:
        refuse(unsealed)
    except BaseException as refused:
        raised = refused

    assert raised is not None, (
        f"`{PROVENANCE_CHECK}` accepted {unsealed!r}, which was built with `model_construct` and "
        "therefore never passed through `comparison_after_suppression`. A check that accepts an "
        "unsealed figure makes every provenance assertion in this module vacuous, and E5-04's "
        "criterion 8 is asserted through this check by name."
    )
