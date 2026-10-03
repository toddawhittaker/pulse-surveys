"""SPEC §4.1 item 7 at the payload boundary, with real figures — ticket E5-05, criteria 3, 4 and 5.

> No figure computed from a comparison set is shown below the benchmark minimum —
> a mean, a median, or any other statistic, not only a drawn line. A comparison
> figure over fewer than the configured number of sections is suppressed exactly
> as a line is (§5.1).

E4-07 proved the chokepoint with nothing flowing through it, and E5-04 proved the
service hands it real counts. What neither could prove is this ticket's own half:
that the figures an instructor's browser receives are suppressed *per figure and
per week*, on both sides of **both** minimums, once there is something to
suppress. This module drives the route and reads the wire.

**Both minimums, each with its own near-miss week, each beside a passing twin in
the same world.** `tests/fixtures/report_benchmarks.py` plants four course weeks
around the section the door teaches: one at both configured minimums, one a
single person short, one a single section short, and one more at both minimums.
The two near misses differ from the passing weeks by exactly one count, which is
what makes a suppression attributable to a named minimum rather than to a world
that was thin in every direction (`docs/MISTAKES.md` entries 22 and 53). Neither
minimum is written down here; both are read from `Settings`, because the promise
is about the *configured* number.

**Every suppression sits beside a figure that arrived.** In each test the control
is asserted first and in the same payload: the passing weeks of the same series,
and the university line at a passing week. (Until E5-14 the university line at
the *thin* week served, as the same rows plus the hero; the university-sealing
ruling withholds it there now, and
`test_the_university_line_is_sealed_on_everyone_but_the_reported_section.py`
asserts that.) A suppression
asserted where no figure could have arrived is emptiness wearing a green tick
(`docs/MISTAKES.md` entries 3 and 9), and in this ticket that is the whole risk:
before the implementation lands, every one of these members is absent.

**"The same rows plus the hero" is a claim in two currencies, and it had to be
made true in both.** E5-04 seals each figure against its own contributors — the
distinct people who answered *that* stream — and E4-07's world writes the hero's
course rating in its own full week only, so at these four weeks the hero
contributed to the instructor panel and to nothing else, which made the
course-stream control false rather than the implementation wrong. Under the
ruling on `docs/disputes/E5-05-02.md`, `plant_the_benchmark_cohort` writes a
course rating onto each of the hero's existing responses in the benchmark weeks
— no new response and no moved count of people, only which questions those
people answered — and
`test_the_report_benchmark_world_plants_what_it_claims.py` reads back from the
database that it did.

**The respondent minimum is a count of people** (`docs/MISTAKES.md` entry 50).
The thin week is short by one *person*; its responses are not short of anything,
because each of this world's respondents answers once a week in one section. The
counts are read back from the database by
`test_the_report_benchmark_world_plants_what_it_claims.py`, which is this
module's premise and is green before E5-05 exists.

**Marked `invariant` at the module level**, which puts it in the isolated §4.1
pass CLAUDE.md says may never be skipped, and CI fails on an empty collection or
a skip. It is E4-07's item-7 module grown from the placeholder era into the data
era; that module keeps its own assertions untouched (criterion 6).

**Which failure a red is, before E5-05 lands.** Every member is read through
`tests/fixtures/report_benchmarks.py`, which `pytest.fail`s naming the member the
work order owes — a FAILED, never a collection error (`docs/MISTAKES.md`
entry 44).
"""

from collections.abc import Callable
from typing import Any

import pytest
from fixtures.benchmark_views import serialized_figure
from fixtures.report_api import FULL_WEEK, ReportDoor
from fixtures.report_benchmarks import (
    COMPARISON_POPULATION,
    FIGURE_FIELD,
    MEAN_FIELD,
    MEDIAN_FIELD,
    POPULATIONS,
    REASON_FIELD,
    SUPPRESSED_FIELD,
    UNIVERSITY_POPULATION,
    WEEK_CLEAR,
    WEEK_CLEAR_TWIN,
    WEEK_THIN_PEOPLE,
    WEEK_THIN_SECTIONS,
    a_suppressed_figures_complaint,
    after_the_close_of,
    benchmark_member_shapes,
    carries_number,
    every_benchmark_figure,
    numbers_of,
    points_of,
    published_course_weeks,
    workload_figures,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

STREAMS = (INSTRUCTOR_STREAM, COURSE_STREAM)

# The hero's own week that no comparison section answered in. E4-07's world puts
# five respondents in its full week — course week 1 — and this ticket's cohort
# plants nothing there, which is what makes it the "a hero week with no
# comparison data" half of the week-axis pair.
HERO_ONLY_WEEK = FULL_WEEK

# The rating means each week's comparison set answered, by hand over the values
# `tests/fixtures/report_benchmarks.py` plants — see that file's tables. The two
# passing weeks' numbers are what a shown figure has to carry; the two near-miss
# weeks' numbers are what no benchmark member may carry anywhere.
#
#   week 2: 8 x 4 + 2 x 2 = 36 over 10 -> 3.6;   4 x 1 + 6 x 4 = 28 over 10 -> 2.8
#   week 3: 7 x 5 + 2 x 2 = 39 over 9;           7 x 4 + 2 x 1 = 30 over 9
#   week 4: 7 x 5 + 3 x 1 = 38 over 10 -> 3.8;   7 x 4 + 3 x 1 = 31 over 10 -> 3.1
#   week 5: 6 x 5 + 4 x 1 = 34 over 10 -> 3.4;   2 x 1 + 8 x 3 = 26 over 10 -> 2.6
COMPARISON_RATING_MEAN = {
    WEEK_CLEAR: {INSTRUCTOR_STREAM: 3.6, COURSE_STREAM: 2.8},
    WEEK_THIN_PEOPLE: {INSTRUCTOR_STREAM: 39 / 9, COURSE_STREAM: 30 / 9},
    WEEK_THIN_SECTIONS: {INSTRUCTOR_STREAM: 3.8, COURSE_STREAM: 3.1},
    WEEK_CLEAR_TWIN: {INSTRUCTOR_STREAM: 3.4, COURSE_STREAM: 2.6},
}

# The workload statistics the thin weeks' hours would produce, which no member
# may carry: 6 x 4.5 + 3 x 10.5 = 58.5 over 9 -> 6.5, median the fifth of nine,
# 4.5; and 8 x 3.5 + 2 x 12.5 = 53 over 10 -> 5.3, median 3.5 (the fifth and sixth
# of ten are both 3.5).
THIN_WORKLOAD = {
    WEEK_THIN_PEOPLE: {MEAN_FIELD: 6.5, MEDIAN_FIELD: 4.5},
    WEEK_THIN_SECTIONS: {MEAN_FIELD: 5.3, MEDIAN_FIELD: 3.5},
}

# A figure driven through the chokepoint by hand, to read the one reason it gives.
# Not a number any of this world's figures is, so a payload carrying it would be
# unmistakable.
A_FIGURE = 4.25


def assert_the_passing_weeks_are_shown(points: dict[int, Any], stream: str) -> None:
    """The control, asserted before any suppression in the same series is read.

    The two passing weeks of the same panel, carrying the two means their own
    respondents answered. Without this, every assertion below is satisfied by a
    series with nothing in it, by a world nobody planted, and by a route that
    serves an empty benchmark member to everybody — which is the state of this
    payload before the implementation lands.
    """
    for week in (WEEK_CLEAR, WEEK_CLEAR_TWIN):
        assert week in points, (
            f"The {stream} panel's comparison series carries course weeks {sorted(points)} and not "
            f"{week}, which this world planted at both configured minimums."
        )
        expected = COMPARISON_RATING_MEAN[week][stream]
        assert carries_number(points[week], expected), (
            f"The control failed before the assertion it protects: course week {week} of the "
            f"{stream} panel cleared both minimums and does not carry {expected}: "
            f"{points[week]!r}. Until it does, the suppression asserted beside it is about a "
            "series that was never populated (`docs/MISTAKES.md` entry 3)."
        )


def assert_it_is_suppressed_and_empty(figure: Any, where: str) -> None:
    """One member that must be suppressed: the flag, the reason, and no statistic at all."""
    assert figure.get(SUPPRESSED_FIELD) is True, a_suppressed_figures_complaint(figure, where)
    assert figure.get(REASON_FIELD), a_suppressed_figures_complaint(figure, where)
    assert figure.get(FIGURE_FIELD) is None, a_suppressed_figures_complaint(figure, where)
    assert not numbers_of(figure), (
        f"{where} says it is suppressed and carries the numbers {numbers_of(figure)}: {figure!r}.\n\n"
        "§4.1 item 7 is about the figure, not about the flag. A payload whose `suppressed` reads "
        "true is one a frontend draws as an empty panel while the number rides along beside it in "
        "the response body, where anything reading the response can see it."
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_the_week_one_respondent_short_is_suppressed_beside_its_passing_twin(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """The respondent minimum, one person below it, with the section minimum cleared.

    The near miss is exactly one *person*: the same three sections, the same one
    response each, one fewer human being. A route whose figures came from a
    service comparing the respondent minimum against a count of responses, or
    against the section count, shows this figure — and the number it shows is
    about one person fewer than the configured minimum promised (at SPEC §11's
    settled minimum of ten, nine people who were promised ten).

    **The two controls, both in this payload.** The same series' two passing weeks
    carry their own means, and the university line is shown at the passing week —
    so "no figure" here is neither an empty series nor a route that answers
    nothing to everybody.

    **The university line is not a control at this week any more (E5-14).** It
    was, as "the same rows plus the hero's own respondents". The orchestrator's
    university-sealing ruling withholds a university figure whose contributors
    other than the reported section fall below either minimum — the reader knows
    her own section's count and sum and could subtract them — and at this week
    they do by one person. That withholding is asserted in
    `test_the_university_line_is_sealed_on_everyone_but_the_reported_section.py`.

    **The mutation this kills:** the respondent minimum dropped from the figures
    the route assembles, or a series-level suppression decision that reads the
    whole set's counts once. Both leave this week's number on an instructor's
    chart.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())
    minimums = report_api_contract.minimums()

    body, answered = report_door.payload(course_week=WEEK_CLEAR)
    comparison = points_of(body, stream, COMPARISON_POPULATION, answered=answered)
    university = points_of(body, stream, UNIVERSITY_POPULATION, answered=answered)

    assert_the_passing_weeks_are_shown(comparison, stream)
    assert WEEK_CLEAR in university and numbers_of(university[WEEK_CLEAR]), (
        f"The control failed before the assertion it protects: the university line at course week "
        f"{WEEK_CLEAR} — the set at both minimums plus the hero — carries no figure: "
        f"{university.get(WEEK_CLEAR)!r}."
    )

    assert WEEK_THIN_PEOPLE in comparison, (
        f"The {stream} panel's comparison series carries course weeks {sorted(comparison)}; course "
        f"week {WEEK_THIN_PEOPLE} was answered by one person fewer than the minimum and is missing "
        "altogether. A dropped point is a gap in a chart, not a suppression (criterion 4)."
    )
    assert_it_is_suppressed_and_empty(
        comparison[WEEK_THIN_PEOPLE],
        f"The {stream} panel's comparison figure for course week {WEEK_THIN_PEOPLE}",
    )
    assert not carries_number(
        comparison[WEEK_THIN_PEOPLE], COMPARISON_RATING_MEAN[WEEK_THIN_PEOPLE][stream]
    ), (
        f"Course week {WEEK_THIN_PEOPLE} of the {stream} comparison line carries "
        f"{COMPARISON_RATING_MEAN[WEEK_THIN_PEOPLE][stream]}, the mean of what that week's people "
        f"answered — one below the configured `{report_api_contract.minimum_respondents}` of "
        f"{minimums[report_api_contract.minimum_respondents]}, while its "
        f"{minimums[report_api_contract.minimum_sections]} sections clear the other minimum."
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_the_week_one_section_short_is_suppressed_beside_its_passing_twins(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """The section minimum, one section below it, with the respondent minimum cleared.

    The mirror of the test above, and the two are the catalog rather than the
    concept (`docs/MISTAKES.md` entry 22): each minimum is driven to its own
    boundary with the other one open, so an assembly that enforces one of the two
    is red on exactly one of these tests. §5.1's sentence is about this week: "a
    mean over one or two sections is a number about those sections".

    **Renamed at E5-14, and the control moved with the name.** It was "…while the
    university line is shown": the university line kept the hero's own section
    and stood at exactly the section minimum here. The orchestrator's
    university-sealing ruling withholds it now — its contributors other than the
    reported section are one section short — which
    `test_the_university_line_is_sealed_on_everyone_but_the_reported_section.py`
    asserts. The control here is the same series' two passing weeks, and the
    university line at the passing week.

    **The mutation this kills:** the section count never compared, or compared
    against the respondent minimum. (The university series assembled as a copy of
    the comparison series, which this test used to catch, is caught in the
    sealing module, where the two are compared at the passing week.)
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]

    body, answered = report_door.payload(course_week=WEEK_CLEAR)
    comparison = points_of(body, stream, COMPARISON_POPULATION, answered=answered)
    university = points_of(body, stream, UNIVERSITY_POPULATION, answered=answered)

    assert_the_passing_weeks_are_shown(comparison, stream)
    assert WEEK_CLEAR in university and numbers_of(university[WEEK_CLEAR]), (
        f"The control failed before the assertion it protects: the university line at course week "
        f"{WEEK_CLEAR} carries no figure: {university.get(WEEK_CLEAR)!r}. Until it does, the "
        "suppression below is satisfied by a payload with no benchmark lines at all."
    )

    assert WEEK_THIN_SECTIONS in comparison, (
        f"The {stream} panel's comparison series carries course weeks {sorted(comparison)}; course "
        f"week {WEEK_THIN_SECTIONS} covers one section fewer than the minimum and is missing "
        "altogether rather than suppressed (criterion 4)."
    )
    assert_it_is_suppressed_and_empty(
        comparison[WEEK_THIN_SECTIONS],
        f"The {stream} panel's comparison figure for course week {WEEK_THIN_SECTIONS}",
    )
    assert not carries_number(
        comparison[WEEK_THIN_SECTIONS], COMPARISON_RATING_MEAN[WEEK_THIN_SECTIONS][stream]
    ), (
        f"Course week {WEEK_THIN_SECTIONS} of the {stream} comparison line carries "
        f"{COMPARISON_RATING_MEAN[WEEK_THIN_SECTIONS][stream]}, the mean over {sections - 1} "
        f"sections — one below the configured `{report_api_contract.minimum_sections}` of "
        f"{sections} — while the people answering it clear the other minimum."
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_a_suppressed_week_stays_in_the_series_as_a_point_rather_than_being_dropped(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """Criterion 4, asserted at the wire: suppression is a point's state, never its absence.

    > A suppressed week inside a passing series renders as that week's
    > suppression, not as a dropped point (E5-04 criterion 7, asserted at the
    > wire).

    E5-04 already answers a per-week seal from the service; this is the half that
    can only be seen on the payload. A missing point and a suppressed point are
    different statements to a reader: the first is a chart with a gap in it, which
    invites the inference that nothing happened that week, and the second is the
    notice §4.1 item 5 governs.

    **The mutation this kills:** the assembler filtering suppressed points out of
    the series — the single most natural edit when a chart component complains
    about nulls, and the one that turns a confidentiality rule into a rendering
    detail.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    body, answered = report_door.payload(course_week=WEEK_CLEAR)
    comparison = points_of(body, stream, COMPARISON_POPULATION, answered=answered)

    assert_the_passing_weeks_are_shown(comparison, stream)
    missing = [week for week in (WEEK_THIN_PEOPLE, WEEK_THIN_SECTIONS) if week not in comparison]
    assert not missing, (
        f"The {stream} panel's comparison series carries course weeks {sorted(comparison)} and "
        f"drops {missing} — the two weeks this world planted below a minimum. The weeks either side "
        "of them are in the series carrying figures, so this is a series that leaves out what it "
        "suppresses rather than one that reports it."
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
@pytest.mark.parametrize("population", POPULATIONS, ids=list(POPULATIONS))
def test_a_series_carries_the_heros_own_published_weeks_and_no_others(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
    population: str,
) -> None:
    """The week axis of a series is the hero's own, and nothing about anybody else's term.

    The security round's MEDIUM, and it is an inference rather than a figure. A
    series whose points are the *union* of the hero's weeks and the comparison
    population's tells a reader which weeks other sections answered in: subtract
    your own published weeks from the points you were sent and what is left is a
    cohort's week-by-week activity, read straight off a fully suppressed series.
    Over an empty or thin set it is worse than an inference — a point that exists
    at all is an existence oracle for a population §4.1 item 7 means to say
    nothing about.

    Ruled in this ticket's fix round: a series carries **exactly** the hero
    section's own published weeks, one point each, shown or suppressed. The weeks
    are read from the payload's own `published_weeks` rather than counted here,
    because which weeks the hero has published is E4-07's answer against the
    clock and this test holds the series to it rather than to a number it chose.

    **The mutation this kills:** the assembler passing the comparison
    population's weeks into the trend call as extra weeks to plot — the union
    that shipped, which reads as generosity and is a disclosure.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())
    report_door.pretend(after_the_close_of(WEEK_THIN_SECTIONS))

    body, answered = report_door.payload(course_week=WEEK_THIN_SECTIONS)
    published = published_course_weeks(body, answered=answered)
    points = points_of(body, stream, population, answered=answered)

    assert WEEK_THIN_SECTIONS in published, (
        f"The payload says the hero has published {sorted(published)}, which does not include the "
        f"week it was just asked for ({WEEK_THIN_SECTIONS}). This suite reads "
        f"`{report_api_contract.published_weeks_field}` as course weeks; if it is a list of term "
        "weeks, `published_course_weeks` in tests/fixtures/report_benchmarks.py is where that is "
        "taught — until then this comparison is between two different currencies."
    )
    assert sorted(points) == sorted(published), (
        f"The {stream} panel's {population} series carries course weeks {sorted(points)} and the "
        f"hero has published {sorted(published)}.\n\n"
        f"In the series and not the hero's own: {sorted(set(points) - set(published))} — each one "
        "tells a reader that some other section answered in a week this instructor has not reached "
        "yet, which is the week-by-week activity of a population §4.1 item 7 exists to say nothing "
        "about. Missing from the series: "
        f"{sorted(set(published) - set(points))} — a dropped week is a gap in a chart rather than a "
        "suppression (criterion 4)."
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_a_week_only_the_comparison_population_answered_in_is_absent_from_both_series(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    stream: str,
) -> None:
    """The pair the ruling asks for, in one world and one payload.

    With the clock standing after the hero's fourth week closes, course week 5 is
    a week the comparison population answered in and the hero has not published.
    It must not be on the wire at all: not as a figure, and not as a suppressed
    point either, because a suppressed point still says *that week happened for
    somebody else*.

    Its twin is course week 1, which the hero published and the comparison set
    never answered in: that week **is** on the wire, as a point whose figure is
    suppressed, because it is one of the hero's own weeks and a chart that
    dropped it would show a term with a hole in it.

    Both halves in one test on purpose: the presence of one and the absence of
    the other are the same rule read in two directions, and a series that carried
    neither would satisfy half of this and be a chart with nothing on it.

    **The mutation this kills:** the union again, from the other side — and, in
    the opposite direction, an assembler that answered only the weeks the
    comparison population has data for, which would drop the hero's own early
    weeks and suppress by omission.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())
    report_door.pretend(after_the_close_of(WEEK_THIN_SECTIONS))

    body, answered = report_door.payload(course_week=WEEK_THIN_SECTIONS)
    comparison = points_of(body, stream, COMPARISON_POPULATION, answered=answered)
    university = points_of(body, stream, UNIVERSITY_POPULATION, answered=answered)

    assert WEEK_CLEAR in comparison and numbers_of(comparison[WEEK_CLEAR]), (
        f"The control failed before the assertions it protects: course week {WEEK_CLEAR}, planted "
        f"at both minimums and published by the hero, carries no figure in the {stream} panel: "
        f"{comparison.get(WEEK_CLEAR)!r}. With nothing on this series the two claims below are "
        "about an empty chart."
    )

    for population, series in (
        (COMPARISON_POPULATION, comparison),
        (UNIVERSITY_POPULATION, university),
    ):
        assert WEEK_CLEAR_TWIN not in series, (
            f"The {stream} panel's {population} series carries a point for course week "
            f"{WEEK_CLEAR_TWIN}: {series[WEEK_CLEAR_TWIN]!r}. The hero has not published that week "
            "— its window has not closed — and the only reason the week exists in this payload at "
            "all is that other sections answered in it. A point there, suppressed or not, is an "
            "existence oracle for a population this report is meant to say nothing about."
        )
        assert HERO_ONLY_WEEK in series, (
            f"The {stream} panel's {population} series carries course weeks {sorted(series)} and "
            f"not {HERO_ONLY_WEEK}, which the hero published and the comparison set never answered "
            "in. A week of the hero's own term is a point on the chart whether or not there is "
            "anything to compare it against; dropping it suppresses by omission (criterion 4)."
        )
        assert_it_is_suppressed_and_empty(
            series[HERO_ONLY_WEEK],
            f"The {stream} panel's {population} figure for course week {HERO_ONLY_WEEK}, where no "
            "comparison section answered",
        )


def test_a_suppressed_benchmark_member_carries_its_reason_and_nothing_else(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """Criterion 3's second half, over every benchmark member at every depth.

    The README sketch's rule: "a suppressed member says `suppressed` and a
    one-word reason and **nothing else** — no counts, no points, no set size,
    because '2 sections' under a suppression is itself the inference item 7 exists
    to prevent."

    Every member is walked, at every depth — both panels, both populations, every
    series, every point, every point's figure, the workload member, its two
    populations and their four statistics — because a rule enforced on the
    members somebody remembered is a rule with a door beside it, and the depth at
    which a count sits has nothing to do with what it discloses.

    **The first version of this test walked figures only, and that was a real
    gap.** A `sections` count added beside `course_week` and `mean` on a series
    *point* is the same disclosure and sits where no figure walk would ever look;
    it reached the wire in this ticket's own fix round and was caught by the
    reconciliation test rather than by the invariant that exists for it. The walk
    now holds every object to the member set the work order settles for it.

    **The control** is in the same payload and is asserted first: some member has
    to be carrying a figure, or "no member carries a count" is true of a payload
    with no members in it.

    **The mutation this kills:** a section count or a respondent count added
    anywhere under the benchmark members so the frontend can say "over 2
    sections" — on a figure, on a point, on a series, or on the member holding
    the two populations.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    body, answered = report_door.payload(course_week=WEEK_THIN_PEOPLE)
    figures = every_benchmark_figure(body, answered=answered)

    shown = {where: figure for where, figure in figures.items() if numbers_of(figure)}
    assert shown, (
        "No benchmark member in this payload carries a figure at all, so every assertion below is "
        f"vacuous (`docs/MISTAKES.md` entry 3). The members read were {sorted(figures)}."
    )

    for where, held, allowed in benchmark_member_shapes(body, answered=answered):
        extra = sorted(set(held) - allowed)
        assert not extra, (
            f"`{where}` carries {extra} beside {sorted(allowed)}: {held!r}.\n\n"
            "A member that says how many sections or how many people are behind it hands back the "
            "inference the minimum exists to prevent, and it does so whether the member is "
            "suppressed or shown, and whichever object it is hung on — a figure, a point, a "
            "series, or the member holding the two populations."
        )

    for where, figure in sorted(figures.items()):
        if figure.get(SUPPRESSED_FIELD) is True:
            assert_it_is_suppressed_and_empty(figure, f"`{where}`")


def test_every_suppressed_benchmark_member_gives_the_chokepoints_one_reason(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """Criterion 5 at the wire: the E4-era placeholder reason is gone from the payload.

    > The E4-era "no comparison set exists" reason is gone from the live payload
    > path, and the schema no longer admits it.

    E4 filled this member by asking the chokepoint for a figure over nothing, and
    the reason a reader saw meant "E5 has not run". Now that there is a comparison
    set, every suppression on this payload is one thing — below a configured
    minimum — and a second reason would be a second meaning for a frontend to
    render and for §4.1 item 5's copy inventory to police.

    **The reason is not written down here.** It is read from the chokepoint
    itself, by driving the suppression helper below both minimums and taking the
    reason it gives: a test holding a copy of that string would go on agreeing
    with a payload that had drifted away from the helper (`docs/MISTAKES.md`
    entry 19).

    **The mutation this kills:** a `NO_COMPARISON_SET` reason kept beside
    `BELOW_MINIMUM` for the empty-set case, which is exactly the state the
    placeholder era left behind and reads as harmless tidiness.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    the_chokepoints_reason = serialized_figure(
        report_api_contract.call_helper(A_FIGURE, sections=0, respondents=0)
    ).get(REASON_FIELD)
    assert the_chokepoints_reason, (
        "The suppression helper gave no reason at all for a figure over nothing, so this test has "
        "nothing to compare the payload against. E4-07's helper carries one reason and E5-05's "
        "decision 6 keeps it as the only one."
    )

    body, answered = report_door.payload(course_week=WEEK_THIN_PEOPLE)
    figures = every_benchmark_figure(body, answered=answered)
    suppressed = {
        where: figure for where, figure in figures.items() if figure.get(SUPPRESSED_FIELD) is True
    }
    assert suppressed, (
        "No benchmark member in this payload is suppressed, so this test read nothing. The reported "
        f"week is {WEEK_THIN_PEOPLE}, which this world planted one person below the respondent "
        f"minimum; the members read were {sorted(figures)}."
    )

    wrong = {
        where: figure.get(REASON_FIELD)
        for where, figure in suppressed.items()
        if figure.get(REASON_FIELD) != the_chokepoints_reason
    }
    assert not wrong, (
        f"These suppressed members give a reason the chokepoint does not: {wrong}. The helper's own "
        f"reason for a figure over nothing is {the_chokepoints_reason!r}, and E5-05's decision 6 "
        "leaves it as the chokepoint's one reason now that a comparison set exists."
    )


@pytest.mark.parametrize(
    "reported_week", (WEEK_THIN_PEOPLE, WEEK_THIN_SECTIONS), ids=("thin-people", "thin-sections")
)
def test_the_workload_figures_are_suppressed_for_a_thin_week_and_shown_for_its_twin(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    reported_week: int,
) -> None:
    """§5.1's workload statistics, on both sides of each minimum, read week by week.

    "The workload mean and median this section requires against comparison-set
    figures are covered by it exactly as the trend lines are." So the member the
    route serves for a thin week carries neither statistic, and the member it
    serves for the passing twin carries both — same world, same door, same
    comparison set, one different reported week.

    **Both statistics are asserted separately**, because §4.1 item 7 names them
    separately: a member that suppressed the mean and served the median would
    disclose the same population through the other number.

    **The twin is the control and it is a real read**, not a claim: the second
    payload in this test is the passing week's, so "the figures did not arrive"
    cannot be a route that serves this member to nobody.

    **The mutation this kills:** the workload member assembled for the section's
    own week without the week's own counts — one suppression decision taken from
    the set as a whole, which shows a thin week's hours beside a passing week's.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    twin, twin_answered = report_door.payload(course_week=WEEK_CLEAR)
    shown = workload_figures(twin, COMPARISON_POPULATION, answered=twin_answered)
    for name in (MEAN_FIELD, MEDIAN_FIELD):
        assert numbers_of(shown[name]), (
            f"The control failed before the assertion it protects: the comparison workload {name} "
            f"for course week {WEEK_CLEAR} — planted at both configured minimums — carries no "
            f"figure: {shown[name]!r}."
        )

    body, answered = report_door.payload(course_week=reported_week)
    figures = workload_figures(body, COMPARISON_POPULATION, answered=answered)
    for name in (MEAN_FIELD, MEDIAN_FIELD):
        assert_it_is_suppressed_and_empty(
            figures[name],
            f"The comparison workload {name} for course week {reported_week}",
        )
        assert not carries_number(figures[name], THIN_WORKLOAD[reported_week][name]), (
            f"The comparison workload {name} for course week {reported_week} carries "
            f"{THIN_WORKLOAD[reported_week][name]}, which is the {name} of the hours that week's "
            "respondents reported. That week is one count below a configured minimum and the week "
            f"beside it, {WEEK_CLEAR}, is shown — the suppression is per week and per figure."
        )
