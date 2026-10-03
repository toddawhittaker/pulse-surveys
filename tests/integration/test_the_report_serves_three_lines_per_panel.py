"""E5-05 criterion 1 — the positive control: a seeded world serves all of it through the route.

> A seeded world serves both panels' comparison and university series and the
> workload comparison figures through the route — the positive control.

SPEC §5.1 is what "three lines per panel" means: "each panel carries three lines
— this section (hero), the **comparison set**, and **university-wide**" — and,
beside the charts, "workload mean/median for the section against comparison-set
and university figures (true numeric statistics — §3.2)".

**This module is the reason the suppression module beside it means anything.**
Every assertion here is that a figure *arrives*, with its value written out by
hand over the answers this world planted. Without it, `docs/MISTAKES.md` entries
3 and 9 are the whole story: a route that served an empty benchmark member for
every world would satisfy every suppression assertion in this ticket.

**Every expected number is arithmetic this module writes**, over the values
`tests/fixtures/report_benchmarks.py` plants — and the multiset it planted is
asserted first, so a drifted value table is a named failure here rather than four
wrong expectations that still agree with each other (`docs/MISTAKES.md` entries
19 and 30). No expected value is a number the payload could also hold for another
reason: none is a count, a minimum, a rate, or one of the hero's own figures.

**Which failure a red is, before E5-05 lands.** The benchmark members are read
through `tests/fixtures/report_benchmarks.py`, whose readers `pytest.fail` naming
the member the work order owes, so the first red is a FAILED naming a deliverable
rather than a `KeyError` or a collection error (`docs/MISTAKES.md` entry 44).
"""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from fixtures.report_api import ReportDoor
from fixtures.report_benchmarks import (
    BENCHMARK_WEEKS,
    COMPARISON_POPULATION,
    FIGURE_FIELD,
    HERO_WORKLOAD_HOURS,
    MEAN_FIELD,
    MEDIAN_FIELD,
    SUPPRESSED_FIELD,
    UNIVERSITY_POPULATION,
    WEEK_CLEAR,
    carries_number,
    numbers_of,
    points_of,
    workload_figures,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration]

# The week every assertion here is driven at: the one planted at both configured
# minimums exactly. At the minimum rather than above it, because SPEC §5.1
# suppresses a figure "computed from fewer than the configured number of
# sections" — so the configured number itself is shown, and an implementation
# written with `>` where `>=` belongs is red here and green on every suppression
# test beside it.
REPORTED_WEEK = WEEK_CLEAR

# What the ten people who answered that week reported, as multisets — ten because
# the week is planted at the respondent minimum and SPEC §11 question 1 settles
# that minimum at 10. Written out here and checked against the planter's tables
# before anything is read, so that the four expectations below rest on values this
# module can see rather than on a fixture's promise (`docs/MISTAKES.md` entry 19).
PLANTED_HOURS = (*(Decimal("7.5"),) * 6, *(Decimal("9.5"),) * 4)
PLANTED_INSTRUCTOR_RATINGS = (*(4,) * 8, *(2,) * 2)
PLANTED_COURSE_RATINGS = (*(1,) * 4, *(4,) * 6)

# The arithmetic, by hand:
#   hours   6 x 7.5 + 4 x 9.5 = 45 + 38 = 83, over 10 responses -> 8.3; sorted,
#           the fifth and sixth of ten are both 7.5, so the median is 7.5.
#   ratings 8 x 4 + 2 x 2 = 36 over 10 -> 3.6, and 4 x 1 + 6 x 4 = 28 over 10
#           -> 2.8.
# Sixteen distinct numbers across this world's four weeks, none of them a count,
# a minimum, a rate, or one of E4-07's own hero figures (10, 9, 4, 3).
COMPARISON_WORKLOAD_MEAN = 8.3
COMPARISON_WORKLOAD_MEDIAN = 7.5
COMPARISON_RATING_MEAN = {INSTRUCTOR_STREAM: 3.6, COURSE_STREAM: 2.8}

# The hero's own two respondents report these hours in the reported week, and the
# university population keeps the hero (E5 breakdown decision 5) while the
# comparison set excludes it. So the university pair is the twelve values
# together:
#   mean   83 + 13.5 + 14.5 = 111, over 12 -> 9.25
#   median the sixth and seventh of the twelve sorted — the six 7.5s come first,
#          then four 9.5s, then the hero's two — so (7.5 + 9.5) / 2 = 8.5
# Four different numbers across the two populations, so neither member can be
# read as the other: a swap shows 8.3 where 9.25 belongs and 7.5 where 8.5 does.
PLANTED_HERO_HOURS = (Decimal("13.5"), Decimal("14.5"))
UNIVERSITY_WORKLOAD_MEAN = 9.25
UNIVERSITY_WORKLOAD_MEDIAN = 8.5

STREAMS = (INSTRUCTOR_STREAM, COURSE_STREAM)


def assert_the_planted_values_are_what_this_module_says() -> None:
    """The planter's tables against this module's copy of them, before anything is read.

    Not a recomputation of the means — that would be holding the expectation in a
    copy of the thing under test (`docs/MISTAKES.md` entry 19) — but a check that
    the *inputs* the hand arithmetic above was done over are still the inputs
    being planted. A value table that moved would otherwise make every expectation
    here wrong in a way that reads as an implementation defect.
    """
    plan = BENCHMARK_WEEKS[REPORTED_WEEK]
    assert sorted(plan.hours) == sorted(PLANTED_HOURS), (
        f"Course week {REPORTED_WEEK} is planted with the hours {sorted(plan.hours)}; the "
        f"arithmetic in this module is written over {sorted(PLANTED_HOURS)}."
    )
    assert sorted(plan.instructor_ratings) == sorted(PLANTED_INSTRUCTOR_RATINGS), (
        f"The instructor ratings planted in course week {REPORTED_WEEK} are "
        f"{sorted(plan.instructor_ratings)}; this module's mean is written over "
        f"{sorted(PLANTED_INSTRUCTOR_RATINGS)}."
    )
    assert sorted(plan.course_ratings) == sorted(PLANTED_COURSE_RATINGS), (
        f"The course ratings planted in course week {REPORTED_WEEK} are "
        f"{sorted(plan.course_ratings)}; this module's mean is written over "
        f"{sorted(PLANTED_COURSE_RATINGS)}."
    )
    assert sorted(HERO_WORKLOAD_HOURS) == sorted(PLANTED_HERO_HOURS), (
        f"The hero's own respondents report {sorted(HERO_WORKLOAD_HOURS)} in the reported week; "
        f"the university arithmetic in this module is written over {sorted(PLANTED_HERO_HOURS)}. "
        "Those two values are the whole of the difference between the university pair and the "
        "comparison pair on the wire."
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_each_panel_serves_the_comparison_sets_own_figure_for_the_reported_week(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """The comparison line, per panel, carrying the mean the set actually answered.

    Both panels, because SPEC §5.1's stacked pair is "instructor stream above,
    course stream below" and each carries its own three lines: a route that
    assembled one stream's series and reused it for the other would be green
    against a single-stream assertion and wrong on the page.

    **The value is the set's and nobody else's.** The two streams' means are 3.6
    and 2.8 over the same ten people, so a panel serving the other stream's
    figure is red here rather than plausible; and neither number is the hero's own
    trend mean, which E4-07's world puts at 4 and 3.

    **The mutation this kills:** the per-stream benchmark member left unpopulated
    — an empty series, or one assembled for the wrong stream — which every
    suppression assertion in this ticket is satisfied by.
    """
    assert_the_planted_values_are_what_this_module_says()
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    body, answered = report_door.payload(course_week=REPORTED_WEEK)
    points = points_of(body, stream, COMPARISON_POPULATION, answered=answered)

    assert REPORTED_WEEK in points, (
        f"The {stream} panel's comparison series carries course weeks {sorted(points)} and not "
        f"{REPORTED_WEEK}, which is the week this world planted at both configured minimums. A "
        "week left out of the series altogether is a gap in a chart rather than a figure."
    )
    figure = points[REPORTED_WEEK]
    expected = COMPARISON_RATING_MEAN[stream]
    assert carries_number(figure, expected), (
        f"The {stream} panel's comparison figure for course week {REPORTED_WEEK} is {figure!r} and "
        f"does not carry {expected}, which is the mean of the ratings the comparison set answered "
        f"that week ({sorted(BENCHMARK_WEEKS[REPORTED_WEEK].instructor_ratings)} and "
        f"{sorted(BENCHMARK_WEEKS[REPORTED_WEEK].course_ratings)} over the two streams). Both "
        "minimums are cleared exactly, and §5.1 suppresses a figure computed from *fewer* than the "
        "configured number."
    )
    assert figure.get(SUPPRESSED_FIELD) is False, (
        f"The figure carries the number and still says it is suppressed: {figure!r}. A frontend "
        "draws the flag, so a shown figure that claims suppression is an empty panel with the "
        "number riding along beside it in the response body."
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_each_panel_serves_a_university_line_beside_the_comparison_one(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """The third line: §5.1's university-wide series, on the same panel and the same week.

    Asserted as "a figure arrives" rather than against a hand-computed mean,
    deliberately: the university population is every matching section including
    the hero (E5 breakdown decision 5), so its value depends on E4-07's own world
    as well as this one, and an expectation built from both would be a copy of two
    fixtures rather than a claim about the route. What this ticket owes is the
    *line*, and that it was sealed by the chokepoint like every other figure.

    **The mutation this kills:** the university series never assembled — one line
    per panel where §5.1 asks for three. That the two series are not one member
    copied twice is asserted in
    `test_the_university_line_is_sealed_on_everyone_but_the_reported_section.py`,
    which compares the two at this week. (Until E5-14 it was asserted where the
    comparison line was suppressed and the university line shown; the
    university-sealing ruling withholds both there now.)
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    body, answered = report_door.payload(course_week=REPORTED_WEEK)
    university = points_of(body, stream, UNIVERSITY_POPULATION, answered=answered)

    assert REPORTED_WEEK in university, (
        f"The {stream} panel's university series carries course weeks {sorted(university)} and not "
        f"{REPORTED_WEEK}. SPEC §5.1: 'the university-wide line is all same-length+level sections "
        "institution-wide', and this world holds the hero and the set at one length and one level."
    )
    figure = university[REPORTED_WEEK]
    assert numbers_of(figure), (
        f"The {stream} panel's university figure for course week {REPORTED_WEEK} carries no number "
        f"at all: {figure!r}. The population is the comparison set plus the hero's own section, so "
        "it clears both minimums by more than the set does — a suppression here is a line §5.1 "
        "requires and nothing computed."
    )


def test_the_reported_weeks_workload_comparison_carries_a_mean_and_a_median(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """§5.1's workload statistics, against the comparison set, for the week being reported.

    > workload mean/median for the section against comparison-set and university
    > figures (true numeric statistics — §3.2)

    **Both figures, each asserted on its own**, because §4.1 item 7 covers "a
    mean, a median, or any other statistic, not only a drawn line": a member that
    served one of the two is half the requirement, and the two values here are
    different numbers (8.3 and 7.5) so neither can stand in for the other.

    **The mutation this kills:** the workload member assembled with one figure, or
    with the mean assigned to both slots — which reads as a rounding curiosity on
    a page and is a different statistic about the same people.
    """
    assert_the_planted_values_are_what_this_module_says()
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    body, answered = report_door.payload(course_week=REPORTED_WEEK)
    figures = workload_figures(body, COMPARISON_POPULATION, answered=answered)

    assert carries_number(figures[MEAN_FIELD], COMPARISON_WORKLOAD_MEAN), (
        f"The comparison workload mean for course week {REPORTED_WEEK} is {figures[MEAN_FIELD]!r} "
        f"and does not carry {COMPARISON_WORKLOAD_MEAN} — the mean of "
        f"{sorted(PLANTED_HOURS)}, which is what the set reported that week."
    )
    assert carries_number(figures[MEDIAN_FIELD], COMPARISON_WORKLOAD_MEDIAN), (
        f"The comparison workload median is {figures[MEDIAN_FIELD]!r} and does not carry "
        f"{COMPARISON_WORKLOAD_MEDIAN} — the fifth and sixth of the ten hours values sorted, "
        "which are equal. §4.1 item 7 covers the median as much as the mean, and a member that "
        "seals one of the two has half a chokepoint."
    )
    assert not carries_number(figures[MEDIAN_FIELD], COMPARISON_WORKLOAD_MEAN), (
        f"The median carries {COMPARISON_WORKLOAD_MEAN}, which is the *mean*: "
        f"{figures[MEDIAN_FIELD]!r}. Two slots filled from one figure is the shape this pair exists "
        "to catch."
    )


def test_the_reported_weeks_workload_university_figures_are_the_wider_populations_own(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """The other half of §5.1's sentence: the same two statistics over the wider population.

    E5-08's StatPair renders "section beside comparison-set beside university,
    mean and median, each column independently suppressible", so a payload
    carrying one population's pair is a component with a column it cannot fill.

    **Both values are asserted exactly, and that is the repair the mutation
    battery asked for.** While the hero reported no hours in this week the
    university pair was *numerically* the comparison pair over the same rows, so
    swapping the two populations behind `workload_benchmark` in the assembler
    changed nothing any test could see — two battery survivors, and
    `docs/MISTAKES.md` entry 30's shape: a world in which the right answer and the
    wrong one are the same number. The hero's own two respondents now report hours
    (`HERO_WORKLOAD_HOURS`), so the union's mean and median are numbers only the
    union produces.

    **The mutations this kills:** `population=UNIVERSITY` swapped for
    `population=DEFAULT_SET` behind `workload_benchmark.university` — which now
    shows 8.3 and 7.5 where 9.25 and 8.5 belong — and the university population
    never asked for at all, the member built from one call to the service instead
    of two.
    """
    assert_the_planted_values_are_what_this_module_says()
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    body, answered = report_door.payload(course_week=REPORTED_WEEK)
    figures = workload_figures(body, UNIVERSITY_POPULATION, answered=answered)

    assert carries_number(figures[MEAN_FIELD], UNIVERSITY_WORKLOAD_MEAN), (
        f"The university workload mean for course week {REPORTED_WEEK} is "
        f"{figures[MEAN_FIELD]!r} and does not carry {UNIVERSITY_WORKLOAD_MEAN} — the mean over "
        f"the comparison set's {sorted(PLANTED_HOURS)} together with the hero's own "
        f"{sorted(PLANTED_HERO_HOURS)}, which is the population §5.1 calls university-wide: 'all "
        "same-length+level sections institution-wide'."
    )
    assert carries_number(figures[MEDIAN_FIELD], UNIVERSITY_WORKLOAD_MEDIAN), (
        f"The university workload median is {figures[MEDIAN_FIELD]!r} and does not carry "
        f"{UNIVERSITY_WORKLOAD_MEDIAN}, the midpoint of the sixth and seventh of those twelve "
        "values sorted."
    )
    assert not carries_number(figures[MEAN_FIELD], COMPARISON_WORKLOAD_MEAN), (
        f"The university workload mean carries {COMPARISON_WORKLOAD_MEAN}, which is the "
        f"*comparison set's* mean: {figures[MEAN_FIELD]!r}. The two populations differ by the "
        "hero's own section, which decision 5 excludes from its own set and keeps in the "
        "university line, so this member has been filled from the wrong population."
    )
    assert not carries_number(figures[MEDIAN_FIELD], COMPARISON_WORKLOAD_MEDIAN), (
        f"The university workload median carries {COMPARISON_WORKLOAD_MEDIAN}, which is the "
        f"comparison set's: {figures[MEDIAN_FIELD]!r}."
    )


def test_the_two_workload_populations_are_different_numbers_in_this_world(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """The control that makes the four assertions above capable of failing.

    Every "this member carries the wrong population's number" assertion rests on
    the two populations being distinguishable *in this world at this week*. They
    were not until the hero reported hours here: with no hero hours the union and
    the set are the same ten values, and both members are correct whichever
    population the assembler asked for. A test suite cannot detect a swap in a
    world where the two answers coincide, and this is the assertion that says so
    out loud rather than leaving it to a reader of the fixture.

    **The mutation this kills:** the hero's hours quietly dropped from
    `plant_the_benchmark_cohort` — which reds nothing else in this module's
    neighbourhood while restoring the world the two battery survivors lived in.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    body, answered = report_door.payload(course_week=REPORTED_WEEK)
    comparison = workload_figures(body, COMPARISON_POPULATION, answered=answered)
    university = workload_figures(body, UNIVERSITY_POPULATION, answered=answered)

    for name in (MEAN_FIELD, MEDIAN_FIELD):
        assert numbers_of(comparison[name]) and numbers_of(university[name]), (
            f"One of the two workload {name} members carries no number at all — comparison "
            f"{comparison[name]!r}, university {university[name]!r} — so this control says nothing "
            "about telling them apart."
        )
        assert comparison[name] != university[name], (
            f"The comparison and university workload {name} are the same value on the wire: "
            f"{comparison[name]!r}. In a world where the two populations produce one number, a "
            "swap between them is undetectable by any test — which is exactly what two mutation "
            "battery survivors demonstrated before the hero's own respondents reported hours in "
            "this week."
        )


def test_the_top_level_comparison_member_carries_the_same_workload_mean_the_new_member_does(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """Criterion 6's additivity, at the one member E4 already shipped.

    E5-05's work order, decision 5: the existing top-level `comparison` member
    stays and "carries the default set's workload mean for the reported week — the
    same sealed object as `workload_benchmark.comparison.mean`, assigned twice,
    computed once". Retiring it would break every E4 reader; filling it with
    something *else* would give two members one name.

    Identity cannot be asserted across the wire, so what is asserted is the
    serialization: the two members say the same thing, number and flag alike.

    **The mutation this kills:** the E4-era member left permanently suppressed
    while the new one carries a figure — which passes every other test in this
    ticket and leaves the payload contradicting itself about the same statistic.
    """
    assert_the_planted_values_are_what_this_module_says()
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    body, answered = report_door.payload(course_week=REPORTED_WEEK)
    legacy = report_api_contract.member(
        body, report_api_contract.comparison_member, answered=answered
    )
    workload = workload_figures(body, COMPARISON_POPULATION, answered=answered)[MEAN_FIELD]

    assert carries_number(legacy, COMPARISON_WORKLOAD_MEAN), (
        f"The top-level `{report_api_contract.comparison_member}` member is {legacy!r} and does not "
        f"carry {COMPARISON_WORKLOAD_MEAN}, the comparison set's workload mean for course week "
        f"{REPORTED_WEEK}. E4 shipped the member with nothing behind it; E5-05 is the ticket that "
        "fills it."
    )
    assert legacy == workload, (
        f"The top-level `{report_api_contract.comparison_member}` serializes as {legacy!r} and "
        f"`workload_benchmark.comparison.{MEAN_FIELD}` as {workload!r}. They are one figure "
        "assigned twice; two spellings of the same statistic is a payload that contradicts itself."
    )
    assert legacy.get(FIGURE_FIELD) is not None, (
        f"The top-level member's `{FIGURE_FIELD}` is null while the member carries a number "
        f"elsewhere: {legacy!r}."
    )
