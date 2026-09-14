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
or the university line over the same rows plus the hero — which E5's breakdown
decision 5 keeps in the population the comparison set excludes. A suppression
asserted where no figure could have arrived is emptiness wearing a green tick
(`docs/MISTAKES.md` entries 3 and 9), and in this ticket that is the whole risk:
before the implementation lands, every one of these members is absent.

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
from fixtures.report_api import ReportDoor
from fixtures.report_benchmarks import (
    COMPARISON_POPULATION,
    FIGURE_FIELD,
    FIGURE_MEMBERS,
    MEAN_FIELD,
    MEDIAN_FIELD,
    REASON_FIELD,
    SUPPRESSED_FIELD,
    UNIVERSITY_POPULATION,
    WEEK_CLEAR,
    WEEK_CLEAR_TWIN,
    WEEK_THIN_PEOPLE,
    WEEK_THIN_SECTIONS,
    a_suppressed_figures_complaint,
    carries_number,
    every_benchmark_figure,
    numbers_of,
    points_of,
    workload_figures,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

STREAMS = (INSTRUCTOR_STREAM, COURSE_STREAM)

# The rating means each week's comparison set answered, by hand over the values
# `tests/fixtures/report_benchmarks.py` plants — see that file's tables. The two
# passing weeks' numbers are what a shown figure has to carry; the two near-miss
# weeks' numbers are what no benchmark member may carry anywhere.
#
#   week 2: 12 x 4 + 3 x 2 = 54 over 15 -> 3.6;   6 x 1 + 9 x 4 = 42 over 15 -> 2.8
#   week 3: 10 x 5 + 4 x 2 = 58 over 14;          10 x 4 + 4 x 1 = 44 over 14
#   week 4: 11 x 5 + 4 x 1 = 59 over 15;          11 x 4 + 4 x 1 = 48 over 15 -> 3.2
#   week 5:  9 x 5 + 6 x 1 = 51 over 15 -> 3.4;   3 x 1 + 12 x 3 = 39 over 15 -> 2.6
COMPARISON_RATING_MEAN = {
    WEEK_CLEAR: {INSTRUCTOR_STREAM: 3.6, COURSE_STREAM: 2.8},
    WEEK_THIN_PEOPLE: {INSTRUCTOR_STREAM: 58 / 14, COURSE_STREAM: 44 / 14},
    WEEK_THIN_SECTIONS: {INSTRUCTOR_STREAM: 59 / 15, COURSE_STREAM: 48 / 15},
    WEEK_CLEAR_TWIN: {INSTRUCTOR_STREAM: 3.4, COURSE_STREAM: 2.6},
}

# The workload statistics the thin weeks' hours would produce, which no member
# may carry: 10 x 4.5 + 4 x 11.5 = 91 over 14 -> 6.5, median 4.5; and
# 12 x 3.5 + 3 x 12.5 = 79.5 over 15 -> 5.3, median 3.5.
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
    about fourteen people who were promised fifteen.

    **The two controls, both in this payload.** The same series' two passing weeks
    carry their own means, and the university line over the same rows *plus the
    hero's own respondents* is shown at this very week — so "no figure" here is
    neither an empty series nor a route that answers nothing to everybody.

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
    assert WEEK_THIN_PEOPLE in university and numbers_of(university[WEEK_THIN_PEOPLE]), (
        f"The control failed before the assertion it protects: the university line at course week "
        f"{WEEK_THIN_PEOPLE} — the same people plus the hero's own respondents, which is above "
        f"`{report_api_contract.minimum_respondents}` of "
        f"{minimums[report_api_contract.minimum_respondents]} — carries no figure: "
        f"{university.get(WEEK_THIN_PEOPLE)!r}."
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
        f"{COMPARISON_RATING_MEAN[WEEK_THIN_PEOPLE][stream]}, the mean of what fourteen people "
        f"answered — one below the configured `{report_api_contract.minimum_respondents}` of "
        f"{minimums[report_api_contract.minimum_respondents]}, while its "
        f"{minimums[report_api_contract.minimum_sections]} sections clear the other minimum."
    )


@pytest.mark.parametrize("stream", STREAMS, ids=list(STREAMS))
def test_the_week_one_section_short_is_suppressed_while_the_university_line_is_shown(
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

    **The sharpest control available**, and it is in the same payload at the same
    week: the university line keeps the hero's own section (breakdown decision 5),
    so over these same rows it stands at exactly the section minimum and is shown.
    The two lines differ by one section, and a route that answered nothing to
    both, or copied one member into the other, is red here.

    **The mutation this kills:** the section count never compared, or compared
    against the respondent minimum; and the university series assembled as a copy
    of the comparison series.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]

    body, answered = report_door.payload(course_week=WEEK_CLEAR)
    comparison = points_of(body, stream, COMPARISON_POPULATION, answered=answered)
    university = points_of(body, stream, UNIVERSITY_POPULATION, answered=answered)

    assert_the_passing_weeks_are_shown(comparison, stream)
    assert WEEK_THIN_SECTIONS in university and numbers_of(university[WEEK_THIN_SECTIONS]), (
        f"The control failed before the assertion it protects: at course week "
        f"{WEEK_THIN_SECTIONS} the university line covers the set's {sections - 1} sections plus "
        f"the hero's own, which is exactly `{report_api_contract.minimum_sections}` of {sections}, "
        f"and it carries no figure: {university.get(WEEK_THIN_SECTIONS)!r}. Until it does, the "
        "suppression below is satisfied by a payload with no university line at all."
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


def test_a_suppressed_benchmark_member_carries_its_reason_and_nothing_else(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """Criterion 3's second half, over every benchmark member at every depth.

    The README sketch's rule: "a suppressed member says `suppressed` and a
    one-word reason and **nothing else** — no counts, no points, no set size,
    because '2 sections' under a suppression is itself the inference item 7 exists
    to prevent."

    Every member is walked, at every depth — both panels, both populations, every
    point, and both workload figures — because a rule enforced on the members
    somebody remembered is a rule with a door beside it, and the depth at which a
    figure sits has nothing to do with whether it is shown.

    **The control** is in the same payload and is asserted first: some member has
    to be carrying a figure, or "no member carries a count" is true of a payload
    with no members in it.

    **The mutation this kills:** a section count or a respondent count added to a
    suppressed member so the frontend can say "over 2 sections" — the exact
    disclosure the suppression exists to prevent.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    body, answered = report_door.payload(course_week=WEEK_THIN_PEOPLE)
    figures = every_benchmark_figure(body, answered=answered)

    shown = {where: figure for where, figure in figures.items() if numbers_of(figure)}
    assert shown, (
        "No benchmark member in this payload carries a figure at all, so every assertion below is "
        f"vacuous (`docs/MISTAKES.md` entry 3). The members read were {sorted(figures)}."
    )

    for where, figure in sorted(figures.items()):
        extra = sorted(set(figure) - FIGURE_MEMBERS)
        assert not extra, (
            f"`{where}` carries {extra} beside {sorted(FIGURE_MEMBERS)}: {figure!r}.\n\n"
            "A member that says how many sections or how many people are behind it hands back the "
            "inference the minimum exists to prevent, and it does so whether the member is "
            "suppressed or shown."
        )
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
