"""E5-04 criteria 1, 2 and 7 — both minimums, on every figure, per figure.

SPEC §4.1 item 7, which these tests are the E5 half of:

> No figure computed from a comparison set is shown below the benchmark minimum
> — a mean, a median, or any other statistic, not only a drawn line. A
> comparison figure over fewer than the configured number of sections is
> suppressed exactly as a line is (§5.1).

E4-07 built the chokepoint and proved that a figure handed to
`comparison_after_suppression` below either minimum does not reach the wire.
What E4 could not prove is the half this ticket owes: that the numbers handed to
that helper are the *real* counts of a *real* population. A service that passed
a section count of nine over a set of two would satisfy every test E4 wrote.

**Both minimums, each driven to its own boundary with the other cleared**
(`docs/MISTAKES.md` entry 22's catalog rule, and this ticket's first criterion in
as many words). The two are different units — a count of sections and a count of
people — and entry 50 is the record of a threshold crossed by a count of
something else, which is why criterion 2 has a world of its own where the
responses clear the respondent minimum and the people do not.

**Every world is driven at the minimum and one below it, never far below.** SPEC
§5.1 suppresses a figure "computed from fewer than the configured number of
sections", so the configured number itself passes and one less does not; a pair
driven at ten above and ten below is green against `>` where `>=` belongs. The
numbers themselves are read from `Settings` rather than written here, because the
promise is about the *configured* minimum.

**Every suppression assertion sits beside a passing control in the same world**
(`docs/MISTAKES.md` entry 3). Each near-miss world is asked a second question it
must answer with a figure — the university line over the same sections plus the
hero, or another course week of the same set — so "no figure came back" cannot
be satisfied by a service that answers nothing to everything, by an empty world,
or by a resolution that found no sections at all.

**The clock is pinned** (ADR 0142). Nothing here asserts a date, and that is
exactly why the pin matters: whether a course week is one the hero has
*published* is a reading of the clock, and a suite whose worlds silently fall out
of the published range would report a missing trend point as a suppressed one.

**Which failure a red here is, before E5-04 lands.** `benchmarks_api` is called
inside every test body, so the first red is a FAILED naming
`app.services.benchmarks` and the eleven names its work order settles — not a
collection error (`docs/MISTAKES.md` entry 44).
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    BENCHMARK_TREND,
    BENCHMARK_WORKLOAD,
    DEFAULT_SET_POPULATION,
    INSTRUCTOR_STREAM,
    UG,
    UNIVERSITY_POPULATION,
    BenchmarkWorld,
    a_population,
    benchmarks_api,
    carries,
    mean_and_median,
    points_by_week,
    serialized_figure,
    spread,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The hero section and the lead who leads it. The default set is "the same Lead
# Faculty's courses filtered to matching length+level, minus the hero section
# itself", so a world without a lead has no default set to resolve at all.
HERO = "hero"
THE_LEAD = "the-lead"

# One 12-week cohort at one level, so every section in these worlds is comparable
# to every other by SPEC §5.1's rule and the only thing that varies is how many
# of them there are and how many people answered.
COHORT = "U"
LEVEL = UG

# The two course weeks these worlds use. Week 2 rather than week 1 so that a
# service keying on "the first week" is not accidentally right.
FULL_WEEK = 2
SECOND_WEEK = 3

# What everybody answered. One value everywhere, so the mean and the median are
# both exactly this whatever the composition of the set — which means a figure
# carrying it is a figure that was computed, and the test says nothing about
# arithmetic that is E5-03's and E5-08's subject.
HOURS = Decimal("2.5")

# The rating the full week carries and the rating the thin week carries. Two
# different values, so the per-week test can tell a figure that was computed from
# the wrong week from one that was suppressed.
A_FULL_WEEK_RATING = Decimal("4")
A_THIN_WEEK_RATING = Decimal("2")

# The hero's own answers, which are never part of its own comparison set
# (decision 5) but are what make the hero a section with a published week to
# compare.
HERO_RATING = Decimal("3")

# One below a minimum, and one above nothing. Named rather than written inline so
# that "one below" is legible at every call site.
ONE = 1


def set_labels(sections: int) -> tuple[str, ...]:
    """The labels of a default set of `sections` sections, nameable before the world is built."""
    return tuple(f"set-{index}" for index in range(sections))


def a_default_set_world(
    world: BenchmarkWorld,
    *,
    plan: dict[str, tuple[str, ...]],
    subject_prefix: str,
    course_week: int = FULL_WEEK,
) -> BenchmarkWorld:
    """A hero, the sections `plan` names, one lead over all of them, and the plan answered.

    **Both counts are the caller's and neither is derived.** The sections come
    from the plan's own labels and the respondents are its keys, so the test that
    wrote the plan can read `len(plan)` and the sum of its values and assert both
    — `docs/MISTAKES.md` entry 53's rule, which a world that planted one count
    and let the other fall out does not meet.

    The hero answers too, in its own section and never in the set, so that every
    world here has a section with a published week to compare and so that the
    comparison is over a population the hero is not in.
    """
    labels = sorted({label for entry in plan.values() for label in entry})
    world.build()
    world.plant_section(HERO, cohort=COHORT, level=LEVEL)
    for label in labels:
        world.plant_section(label, cohort=COHORT, level=LEVEL)
    world.lead(THE_LEAD, HERO, *labels)

    world.answer_the_plan(
        plan, course_week=course_week, workload=HOURS, instructor_rating=A_FULL_WEEK_RATING
    )
    world.respond(
        HERO,
        course_week=course_week,
        subject=f"{subject_prefix}-hero",
        workload=HOURS,
        instructor_rating=HERO_RATING,
    )
    world.session.flush()
    return world


def assert_the_plan_holds(
    plan: dict[str, tuple[str, ...]], *, sections: int, respondents: int
) -> None:
    """Both counts, stated by the test and checked before the world is measured.

    `docs/MISTAKES.md` entry 53: every acceptance world plants both counts
    explicitly. A near-miss world differs from its passing world by exactly one
    of these two numbers, and a test that asserted neither could not say which.
    """
    planted_sections = len({label for entry in plan.values() for label in entry})
    assert (planted_sections, len(plan)) == (sections, respondents), (
        f"This test's plan covers {planted_sections} sections and {len(plan)} people; it was "
        f"written for {sections} and {respondents}. Both counts are the premise of every "
        "assertion below, and the near-miss discipline is that a failing world differs from the "
        "passing one by exactly the count under test."
    )


def the_workload(world: BenchmarkWorld, population: str, *, course_week: int = FULL_WEEK) -> Any:
    """`benchmark_workload` for the hero section over one population."""
    api = benchmarks_api()
    return api[BENCHMARK_WORKLOAD](
        world.session,
        section_id=world.section_id(HERO),
        population=a_population(population),
        course_week=course_week,
    )


def test_a_default_set_at_both_minimums_yields_a_workload_mean_and_median(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """Criterion 1's passing world, driven **at** each minimum rather than above it.

    SPEC §5.1 suppresses a figure "computed from fewer than the configured number
    of sections", so the configured number is the first value that passes. A
    service written with `>` where `>=` belongs suppresses here and is green on
    both near-miss tests below, so this is the only test that catches it — and
    without it those two are satisfied by a service that suppresses everything,
    which is `docs/MISTAKES.md` entry 3 exactly.

    **Both figures are asserted**, because §4.1 item 7 covers "a mean, a median,
    or any other statistic": a service that sealed the mean and returned the
    median raw, or that suppressed one of the two, is a defect this test names
    and no other does.

    **The mutation it kills:** the comparison written as `>` on either minimum;
    and a workload answer that carries only one of the two statistics.
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]

    plan = dict(spread(set_labels(sections), respondents=respondents, subject_prefix="e5-04-both"))
    assert_the_plan_holds(plan, sections=sections, respondents=respondents)
    a_default_set_world(benchmark_world, plan=plan, subject_prefix="e5-04-both")

    mean, median = mean_and_median(the_workload(benchmark_world, DEFAULT_SET_POPULATION))

    assert carries(mean, HOURS), (
        f"The comparison workload mean over {sections} sections and {respondents} respondents — "
        f"both exactly the configured minimums — does not carry {HOURS}: {serialized_figure(mean)}. "
        "Every response in the set reported those hours, so that is the mean; at the minimum the "
        "figure is shown, because §5.1 suppresses one computed from *fewer* than the configured "
        "number."
    )
    assert carries(median, HOURS), (
        f"The comparison workload median is {serialized_figure(median)} and does not carry "
        f"{HOURS}. §4.1 item 7 covers the median as much as the mean — 'a mean, a median, or any "
        "other statistic, not only a drawn line' — and a service that seals one of the two has "
        "half a chokepoint."
    )


def test_a_default_set_one_section_below_the_minimum_suppresses_both_figures(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """Criterion 1's section near miss: one section fewer, the same people.

    The respondent count clears its own minimum, so a service enforcing only that
    one passes this figure straight through. That is the closed-set defeat
    `docs/MISTAKES.md` entry 22 records, written against the catalog this ticket
    names: `benchmark_min_sections_default` and
    `benchmark_min_respondents_default`.

    **The control in the same world is the university line**, which includes the
    hero section (decision 5) and therefore stands at exactly the minimum over
    the same rows. So "nothing came back" cannot be a resolution that found no
    sections, a world that was never planted, or a service that answers nothing
    to everything — the same world answers one of the two questions with a
    figure.

    **The mutation it kills:** the section count never compared, or compared
    against the respondent minimum; and a section count taken from the number of
    *ids resolved* rather than from the sections that actually carry rows.
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]
    assert sections >= 2, (
        f"`{report_api_contract.minimum_sections}` is {sections}, so there is no value below it "
        "that is still a comparison set and this pair cannot be driven."
    )

    plan = dict(
        spread(
            set_labels(sections - ONE),
            respondents=respondents,
            subject_prefix="e5-04-thin-sections",
        )
    )
    assert_the_plan_holds(plan, sections=sections - ONE, respondents=respondents)
    a_default_set_world(benchmark_world, plan=plan, subject_prefix="e5-04-thin-sections")

    mean, median = mean_and_median(the_workload(benchmark_world, DEFAULT_SET_POPULATION))
    control_mean, _control_median = mean_and_median(
        the_workload(benchmark_world, UNIVERSITY_POPULATION)
    )

    assert carries(control_mean, HOURS), (
        f"The control failed before the assertion it protects: the university line over the same "
        f"world — {sections - ONE} set sections plus the hero, which decision 5 includes — does "
        f"not carry {HOURS}: {serialized_figure(control_mean)}. Until it does, the suppression "
        "asserted below is satisfied by a world nobody planted or by a service that answers "
        "nothing at all (`docs/MISTAKES.md` entry 3)."
    )
    assert not carries(mean, HOURS), (
        f"A comparison workload mean over {sections - ONE} sections — one below the configured "
        f"`{report_api_contract.minimum_sections}` of {sections} — carries {HOURS}: "
        f"{serialized_figure(mean)}. Its {respondents} respondents clear the other minimum, so a "
        "service reading only that one shows this figure. §5.1: 'a mean over one or two sections "
        "is a number about those sections — the same inference small-N suppression exists to "
        "prevent, reached through a benchmark rather than through a comment'."
    )
    assert not carries(median, HOURS), (
        f"The median over the same {sections - ONE} sections carries {HOURS}: "
        f"{serialized_figure(median)}. The minimum covers every figure computed from the set, and "
        "a median shown where its mean was suppressed discloses the same population."
    )


def test_a_default_set_one_respondent_below_the_minimum_suppresses_both_figures(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """Criterion 1's respondent near miss: one person fewer, the same sections.

    The mirror of the test above, and the two together are the catalog rather
    than the concept: each minimum is driven to its own boundary with the other
    cleared, so neither can stand in for the other and a service enforcing one of
    the two is red on exactly one of these tests.

    **The control in the same world** is again the university line, which adds
    the hero's own respondent and its section, putting the population at exactly
    both minimums over the same rows. It is the sharpest control available here:
    the two calls differ by one person and one section, so a service that answers
    a figure to the first and not the second is measuring what it should be.

    **The mutation it kills:** the respondent minimum never compared, and the
    respondent count taken from the number of responses — which this world's
    sibling, criterion 2, plants in its own right.
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]
    assert respondents >= 2, (
        f"`{report_api_contract.minimum_respondents}` is {respondents}, so there is no value below "
        "it to drive this half of the pair with."
    )

    plan = dict(
        spread(
            set_labels(sections),
            respondents=respondents - ONE,
            subject_prefix="e5-04-thin-people",
        )
    )
    assert_the_plan_holds(plan, sections=sections, respondents=respondents - ONE)
    a_default_set_world(benchmark_world, plan=plan, subject_prefix="e5-04-thin-people")

    mean, median = mean_and_median(the_workload(benchmark_world, DEFAULT_SET_POPULATION))
    control_mean, _control_median = mean_and_median(
        the_workload(benchmark_world, UNIVERSITY_POPULATION)
    )

    assert carries(control_mean, HOURS), (
        f"The control failed before the assertion it protects: the university line over the same "
        f"world — the same {sections} sections plus the hero, and the hero's own respondent, which "
        f"is {respondents} people — does not carry {HOURS}: {serialized_figure(control_mean)}."
    )
    assert not carries(mean, HOURS), (
        f"A comparison workload mean over {respondents - ONE} respondents — one below the "
        f"configured `{report_api_contract.minimum_respondents}` of {respondents} — carries "
        f"{HOURS}: {serialized_figure(mean)}. Its {sections} sections clear the other minimum."
    )
    assert not carries(median, HOURS), (
        f"The median over the same {respondents - ONE} respondents carries {HOURS}: "
        f"{serialized_figure(median)}."
    )


def test_the_respondent_minimum_counts_people_rather_than_responses(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """Criterion 2, and `docs/MISTAKES.md` entry 50: a threshold crossed by a count of something else.

    One below the respondent minimum in *people*, and above it in *responses* —
    the students who take two of the lead's courses answer in both. A service
    comparing `response_count` against `benchmark_min_respondents_default` shows
    this figure, and the number it showed it on is a count of submissions rather
    than of the people the minimum exists to protect.

    **The control is the same sections at another course week**, answered by
    exactly the minimum number of people. Same world, same set, same lead — the
    only difference between the suppressed answer and the shown one is how many
    people are behind it.

    **The mutation it kills:** `respondent_count` swapped for `response_count`,
    which is the single most plausible edit in this module's subject: the two sit
    beside each other in the set function's row and one of them is always the
    larger.
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]

    labels = set_labels(sections)
    plan = dict(spread(labels, respondents=respondents - ONE, subject_prefix="e5-04-people"))

    # Two of those students also answer in a second section of the same set, so
    # the responses climb past the minimum while the people stay one below it.
    # The same person, a second response — never a second subject, which would
    # move the very count under test.
    doubled = sorted(plan)[:2]
    for subject in doubled:
        already = plan[subject][0]
        second = next(label for label in labels if label != already)
        plan[subject] = (already, second)

    assert_the_plan_holds(plan, sections=sections, respondents=respondents - ONE)
    a_default_set_world(benchmark_world, plan=plan, subject_prefix="e5-04-people")

    responses = sum(len(sections_for) for sections_for in plan.values())
    assert responses >= respondents, (
        f"This world holds {responses} responses and the respondent minimum is {respondents}, so "
        "it is not entry 50's world at all: the responses have to clear the minimum the people "
        "fail, or a service counting responses would suppress here for the right answer by "
        "accident."
    )

    thin_mean, thin_median = mean_and_median(the_workload(benchmark_world, DEFAULT_SET_POPULATION))

    # The control: one more person answers the same set at another course week,
    # putting that week at exactly the minimum in people.
    benchmark_world.answer_the_plan(
        dict(spread(labels, respondents=respondents, subject_prefix="e5-04-people-control")),
        course_week=SECOND_WEEK,
        workload=HOURS,
        instructor_rating=A_FULL_WEEK_RATING,
    )
    benchmark_world.session.flush()
    control_mean, _control_median = mean_and_median(
        the_workload(benchmark_world, DEFAULT_SET_POPULATION, course_week=SECOND_WEEK)
    )

    assert carries(control_mean, HOURS), (
        f"The control failed before the assertion it protects: course week {SECOND_WEEK} of the "
        f"same set, answered by {respondents} distinct people, does not carry {HOURS}: "
        f"{serialized_figure(control_mean)}."
    )
    assert not carries(thin_mean, HOURS), (
        f"A comparison workload mean over {respondents - ONE} *people* — who submitted "
        f"{responses} responses between them — carries {HOURS}: {serialized_figure(thin_mean)}.\n\n"
        f"`{report_api_contract.minimum_respondents}` is a count of people, and "
        "`docs/MISTAKES.md` entry 50 is the record of a threshold crossed by a count of something "
        "else. The set function answers `respondent_count` and `response_count` side by side; only "
        "the first is the number this promise is about."
    )
    assert not carries(thin_median, HOURS), (
        f"The median over the same {respondents - ONE} people carries {HOURS}: "
        f"{serialized_figure(thin_median)}."
    )


def test_a_trend_series_suppresses_the_thin_week_and_shows_the_full_one(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """Criterion 7: suppression is per figure, not per report.

    One set, two course weeks: week 2 answered by enough people and week 3 by one
    of them. A service that decided suppression once for the series would either
    hide both weeks or show both, and the second of those puts a comparison
    figure computed from one person's answer on an instructor's chart.

    **Both halves are in one test on purpose.** The shown week is the control for
    the suppressed week and vice versa, in the same series from one call — there
    is no world here in which "no figure" could mean "no series".

    **The two weeks carry different ratings**, so a suppressed week 3 cannot be
    satisfied by a service that answered week 2's figure twice, and a shown week
    2 cannot be week 3's figure under another label.

    **The mutation it kills:** one suppression decision taken over the whole
    trend from the first week's counts, or from the series' totals across weeks —
    which is the arithmetic that turns a week nobody answered into part of a week
    everybody did.
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]

    labels = set_labels(sections)
    plan = dict(spread(labels, respondents=respondents, subject_prefix="e5-04-weeks"))
    assert_the_plan_holds(plan, sections=sections, respondents=respondents)
    a_default_set_world(benchmark_world, plan=plan, subject_prefix="e5-04-weeks")

    # Week 3: one person answers, in one section of the same set, rating it 2.
    benchmark_world.answer_the_plan(
        {"e5-04-weeks-thin": (labels[0],)},
        course_week=SECOND_WEEK,
        workload=HOURS,
        instructor_rating=A_THIN_WEEK_RATING,
    )
    benchmark_world.respond(
        HERO,
        course_week=SECOND_WEEK,
        subject="e5-04-weeks-hero-second",
        workload=HOURS,
        instructor_rating=HERO_RATING,
    )
    benchmark_world.session.flush()

    api = benchmarks_api()
    trend = api[BENCHMARK_TREND](
        benchmark_world.session,
        section_id=benchmark_world.section_id(HERO),
        population=a_population(DEFAULT_SET_POPULATION),
        stream=INSTRUCTOR_STREAM,
    )
    weeks = points_by_week(trend)

    assert {FULL_WEEK, SECOND_WEEK} <= set(weeks), (
        f"The trend carries course weeks {sorted(weeks)}; the hero answered in {FULL_WEEK} and "
        f"{SECOND_WEEK} and both are weeks it has to compare. A week left out of the series "
        "altogether is a gap in a chart rather than the suppression §4.1 item 7 asks for: E5-05 "
        "draws what this answers, and a missing point and a suppressed point are different "
        "statements to a reader."
    )
    assert carries(weeks[FULL_WEEK], A_FULL_WEEK_RATING), (
        f"Course week {FULL_WEEK}, answered by {respondents} people across {sections} sections — "
        f"both minimums cleared — does not carry the comparison rating mean "
        f"{A_FULL_WEEK_RATING}: {serialized_figure(weeks[FULL_WEEK])}. Without this the "
        "suppression asserted below is satisfied by a series with nothing in it."
    )
    assert not carries(weeks[SECOND_WEEK], A_THIN_WEEK_RATING), (
        f"Course week {SECOND_WEEK} of the same comparison set — answered by one person in one "
        f"section — carries {A_THIN_WEEK_RATING}: {serialized_figure(weeks[SECOND_WEEK])}. "
        "Suppression is per figure: the week beside it cleared both minimums and is shown, and "
        "this one is a number about one student."
    )
    assert not carries(weeks[SECOND_WEEK], A_FULL_WEEK_RATING), (
        f"Course week {SECOND_WEEK} carries {A_FULL_WEEK_RATING}, which is the *other* week's "
        f"figure: {serialized_figure(weeks[SECOND_WEEK])}. A series that repeats one week's "
        "comparison across every point is suppressed nowhere and wrong everywhere."
    )
