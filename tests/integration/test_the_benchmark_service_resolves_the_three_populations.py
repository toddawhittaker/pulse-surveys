"""E5-04 criteria 3, 4, 5 and 6 — which sections a comparison figure is computed over.

SPEC §5.1 settles three populations and E5's breakdown settles what each
contains:

> The default comparison set is the same Lead Faculty's courses filtered to
> matching length+level; leadership can define named sets … The university-wide
> line is all same-length+level sections institution-wide.

and, in the same paragraph:

> Benchmarks are **past-referencing**: week N of a 12-week section is compared
> against week N of 12-week sections of the same level in the current *and
> prior* terms, regardless of start date.

**Three of these four criteria are about a population and one is about a
value**, so this module asserts both grains. The resolvers are public for
exactly that reason — the work order exposes them "for tests" — and a test that
only ever read figures could not tell a set resolved wrongly from a set whose
figures were computed wrongly.

**Every suppression assertion has a passing control in the same world**
(`docs/MISTAKES.md` entry 3), and the controls here are not ceremony: the whole
subject is that two populations over one world give two different answers, so
each test asks both questions of one set of rows and requires them to differ in
the direction the criterion names.

**Past-referencing is planted where the two axes disagree.** The hero's cohort
starts in the term's fourth week and the prior term's sections start in its
first, so course week 2 is term week 5 for one and term week 2 for the other,
and they fall in different months. A service that aligned on the term week or on
the calendar finds nothing in the prior term and suppresses — which is why
criterion 4's world is built out of those two cohorts rather than two that start
together.

**The clock is pinned** (ADR 0142), for the reason the sibling module states.

**Which failure a red here is, before E5-04 lands.** Every test reaches the
service through `benchmarks_api` inside its own body, so the first red is a
FAILED naming `app.services.benchmarks` (`docs/MISTAKES.md` entry 44).
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    BENCHMARK_WORKLOAD,
    CURRENT_TERM,
    DEFAULT_SET_POPULATION,
    INSTRUCTOR_STREAM,
    NAMED_SET_TREND,
    NAMED_SET_WORKLOAD,
    PRIOR_TERM,
    RESOLVE_DEFAULT_SET,
    RESOLVE_NAMED_SET,
    RESOLVE_UNIVERSITY,
    UG,
    UNIVERSITY_POPULATION,
    BenchmarkWorld,
    a_population,
    benchmarks_api,
    carries,
    figures_in,
    mean_and_median,
    reporting_symbol,
    serialized_figure,
    spread,
)
from fixtures.benchmark_views import (
    COMPARISON_FIGURE_TYPE as FIGURE_TYPE_NAME,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

HERO = "hero"
THE_LEAD = "the-lead"
A_SIBLING_LEAD = "a-sibling-lead"

LEVEL = UG
TWELVE_WEEKS = 12
EIGHT_WEEKS = 8

# The current term's 12-week cohort that starts in its **fourth** week, against
# the prior term's 12-week cohort that starts in its first. Same length, same
# level, so §5.1 makes them comparable; different term weeks and different
# months, so course week 2 is the only axis on which they meet.
LATE_STARTING_COHORT = "R"
PRIOR_COHORT = "U"

# A cohort that starts in the current term's first week, for the worlds where the
# term axis is not the subject.
EARLY_COHORT = "U"

THE_COURSE_WEEK = 2

# What the comparison population answered, and what everybody outside it
# answered. Two values far apart, so a figure carrying one of them says which
# population it was computed over — and the arithmetic that distinguishes them is
# written out by hand in the test that asserts it.
SET_HOURS = Decimal("2.5")
OUTSIDE_HOURS = Decimal("9.0")
A_RATING = Decimal("4")

# How many people answer outside the comparison set in the two-lines world: the
# hero's own three and a sibling lead's two, all of them reporting
# `OUTSIDE_HOURS`. Both counts are small on purpose — the university line's
# minimums are cleared by the set's own respondents, so these five are what move
# the *figure* and nothing else.
HERO_RESPONDENTS = 3
SIBLING_RESPONDENTS = 2


def the_university_mean(respondents: int) -> Decimal:
    """The mean of the two-lines world's twenty responses, by hand.

    `(respondents x 2.5 + 5 x 9.0) / (respondents + 5)` — arithmetic over values
    this module supplied, never a number read back from anything
    (`docs/MISTAKES.md` entries 19 and 30). Written as a function rather than as
    a literal because the set's size is the configured respondent minimum, and a
    literal would be this file's copy of a value `.env.example` may move.
    """
    outside = HERO_RESPONDENTS + SIBLING_RESPONDENTS
    return (respondents * SET_HOURS + outside * OUTSIDE_HOURS) / (respondents + outside)


def resolved(world: BenchmarkWorld, name: str, **arguments: Any) -> list[Any]:
    """One resolver's answer, as a list of section ids."""
    api = benchmarks_api()
    return list(api[name](world.session, **arguments))


def the_workload(
    world: BenchmarkWorld, population: str, *, course_week: int = THE_COURSE_WEEK
) -> Any:
    """`benchmark_workload` for the hero section over one population."""
    api = benchmarks_api()
    return api[BENCHMARK_WORKLOAD](
        world.session,
        section_id=world.section_id(HERO),
        population=a_population(population),
        course_week=course_week,
    )


def set_labels(sections: int) -> tuple[str, ...]:
    """The labels of the lead's other courses, nameable before the world is built."""
    return tuple(f"set-{index}" for index in range(sections))


def a_hero_and_a_lead_with_more_courses(
    world: BenchmarkWorld, *, sections: int, respondents: int
) -> tuple[str, ...]:
    """The hero, `sections` more sections under its own lead, and one under a sibling lead.

    The sibling's section is what makes "the lead's courses" a *subset* of the
    university rather than the same thing minus the hero, which is criterion 5's
    world in one sentence. §4.1 item 2 is the reason the sibling is a second lead
    rather than a second course under the first.

    `sections` is the configured section minimum at every call site, so the
    default set here stands exactly at it and the figures below are about the
    population rather than about the threshold.
    """
    labels = set_labels(sections)
    world.build()
    world.plant_section(HERO, cohort=EARLY_COHORT, level=LEVEL)
    for label in labels:
        world.plant_section(label, cohort=EARLY_COHORT, level=LEVEL)
    world.plant_section("siblings", cohort=EARLY_COHORT, level=LEVEL)

    world.lead(THE_LEAD, HERO, *labels)
    world.lead(A_SIBLING_LEAD, "siblings")

    world.answer_the_plan(
        dict(
            spread(
                labels,
                respondents=respondents,
                subject_prefix="e5-04-population",
            )
        ),
        course_week=THE_COURSE_WEEK,
        workload=SET_HOURS,
        instructor_rating=A_RATING,
    )
    world.answer_the_plan(
        dict(spread((HERO,), respondents=HERO_RESPONDENTS, subject_prefix="e5-04-population-hero")),
        course_week=THE_COURSE_WEEK,
        workload=OUTSIDE_HOURS,
        instructor_rating=A_RATING,
    )
    world.answer_the_plan(
        dict(
            spread(
                ("siblings",),
                respondents=SIBLING_RESPONDENTS,
                subject_prefix="e5-04-population-sibling",
            )
        ),
        course_week=THE_COURSE_WEEK,
        workload=OUTSIDE_HOURS,
        instructor_rating=A_RATING,
    )
    world.session.flush()
    return labels


def test_the_default_set_leaves_the_hero_out_and_the_university_line_takes_it_in(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """Criterion 3 and decision 5, asserted on the populations themselves.

    The default set is the lead's courses "minus the hero section itself", and
    the university line is every section of the same length and level with the
    hero among them. Both are asked of one world, so the difference between the
    two answers is exactly the decision.

    **The sibling lead's section is the second half of the assertion.** A default
    set that happened to be "every section but the hero" would pass a test that
    only checked for the hero's absence, and it would hand a Lead Faculty a
    benchmark drawn over a colleague's courses — §4.1 item 2's own shape, reached
    through a benchmark.

    **The mutation it kills:** the exclusion dropped (the hero left in its own
    comparison set, which flatters or damns a section against itself), and the
    exclusion applied to the university line too.
    """
    minimums = report_api_contract.minimums()
    respondents = minimums[report_api_contract.minimum_respondents]
    labels = a_hero_and_a_lead_with_more_courses(
        benchmark_world,
        sections=minimums[report_api_contract.minimum_sections],
        respondents=respondents,
    )

    hero_id = benchmark_world.section_id(HERO)
    default_set = resolved(benchmark_world, RESOLVE_DEFAULT_SET, section_id=hero_id)
    university = resolved(benchmark_world, RESOLVE_UNIVERSITY, section_id=hero_id)

    lead_sections = {benchmark_world.section_id(label) for label in labels}
    sibling_section = benchmark_world.section_id("siblings")

    assert set(default_set) == lead_sections, (
        f"The default set resolves to {sorted(map(str, default_set))}; the lead's other "
        f"{len(lead_sections)} courses are {sorted(map(str, lead_sections))}. The hero section is "
        f"{hero_id} and the sibling lead's section is {sibling_section}: the first is excluded by "
        "decision 5, and the second was never this lead's to be compared against."
    )
    assert hero_id in university, (
        f"The university line resolves to {sorted(map(str, university))}, which does not include "
        f"the hero section {hero_id}. Decision 5 puts the hero in the institution-wide population "
        "and takes it out of its own set; a line that excluded it from both would be two "
        "exclusions where the record has one."
    )
    assert lead_sections | {hero_id, sibling_section} == set(university), (
        f"The university line resolves to {sorted(map(str, university))}. Every section in this "
        "world is the same length and the same level, so §5.1's 'all same-length+level sections "
        "institution-wide' is every section this world holds — the lead's, the hero's and the "
        "sibling lead's alike."
    )


def test_the_two_lines_answer_two_different_figures_over_one_world(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """Criteria 3 and 5 at the figure grain: the populations differ, so the numbers do.

    The lead's own sections reported 2.5 hours each; the hero's three
    respondents and the sibling lead's two reported 9.0. So the comparison line
    is exactly 2.5 and the university line is `the_university_mean` above —
    arithmetic this module writes out over values it supplied, never read back
    from anything (`docs/MISTAKES.md` entry 30).

    **Each figure is the other's control.** A service that resolved one
    population for both lines answers the same number twice, and a service that
    resolved neither answers nothing twice; both are caught here without a third
    call.

    **The mutation it kills:** the hero's own responses folded into its
    comparison set — which moves the comparison line to the university's figure
    and is invisible on any test that only asks whether a figure came back. And
    the university line
    computed over the lead's courses, which is the same defect from the other
    side and would make §5.1's two lines one line drawn twice.
    """
    minimums = report_api_contract.minimums()
    respondents = minimums[report_api_contract.minimum_respondents]
    a_hero_and_a_lead_with_more_courses(
        benchmark_world,
        sections=minimums[report_api_contract.minimum_sections],
        respondents=respondents,
    )
    expected_university_mean = the_university_mean(respondents)

    comparison_mean, comparison_median = mean_and_median(
        the_workload(benchmark_world, DEFAULT_SET_POPULATION)
    )
    university_mean, _university_median = mean_and_median(
        the_workload(benchmark_world, UNIVERSITY_POPULATION)
    )

    assert carries(comparison_mean, SET_HOURS), (
        f"The comparison workload mean is {serialized_figure(comparison_mean)} and does not carry "
        f"{SET_HOURS}, which is what every response in the lead's own sections reported. "
        f"{expected_university_mean} here would be the hero's own hours and the sibling lead's "
        "folded into the set."
    )
    assert carries(comparison_median, SET_HOURS), (
        f"The comparison workload median is {serialized_figure(comparison_median)}; every response "
        f"in the set reported {SET_HOURS}, so that is the median as well as the mean."
    )
    assert carries(university_mean, expected_university_mean), (
        f"The university workload mean is {serialized_figure(university_mean)} and does not carry "
        f"{expected_university_mean}. {respondents} responses at {SET_HOURS} from the lead's "
        "sections, "
        f"{HERO_RESPONDENTS} at {OUTSIDE_HOURS} from the hero and {SIBLING_RESPONDENTS} at "
        f"{OUTSIDE_HOURS} from a sibling lead's section. A mean of {SET_HOURS} is the university "
        "line computed over the comparison set, which draws §5.1's two lines from one population."
    )


def test_a_cohort_thin_in_this_term_is_a_benchmark_once_prior_terms_are_counted(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """Criterion 4: past-referencing, aligned course week to course week.

    Two 12-week sections in the current term and two in the prior one. Two is
    below the section minimum, so the figure exists only if the prior term counts
    — and the prior term's sections start in *its* first week while the hero's
    cohort starts in the current term's fourth, so their course week 2 is a
    different term week and a different month. A service aligning on the term
    week, or on dates, finds nothing there and suppresses.

    **The control is the resolution beside the figure.** The population is
    asserted to hold two sections from each term, so "a figure came back" cannot
    be a world with four current-term sections in it that this test misread.

    **The mutation it kills:** a resolution filtered to the current term — which
    is the most natural query to write, is right for every cohort with enough
    sections this term, and silently empties the benchmark for exactly the thin
    cohorts §5.1 introduced past-referencing for. Also a join on `week.number`
    rather than on the course week, which is right only while every section
    starts in its term's first week.
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]
    assert sections >= 3, (
        f"`{report_api_contract.minimum_sections}` is {sections}; this world is built to hold two "
        "current-term sections and two prior-term ones, which is a statement about the minimum "
        "only while it is 3 or more."
    )

    world = benchmark_world.build()
    world.build_prior_term()
    world.plant_section(HERO, cohort=LATE_STARTING_COHORT, level=LEVEL, term=CURRENT_TERM)
    world.plant_section("this-term", cohort=LATE_STARTING_COHORT, level=LEVEL, term=CURRENT_TERM)
    world.plant_section("last-term-a", cohort=PRIOR_COHORT, level=LEVEL, term=PRIOR_TERM)
    world.plant_section("last-term-b", cohort=PRIOR_COHORT, level=LEVEL, term=PRIOR_TERM)

    labels = (HERO, "this-term", "last-term-a", "last-term-b")
    plan = dict(spread(labels, respondents=respondents, subject_prefix="e5-04-terms"))
    assert len({label for entry in plan.values() for label in entry}) == len(labels), (
        "The plan does not reach all four sections, so the section count this world plants is not "
        "the one it was written for."
    )
    world.answer_the_plan(
        plan, course_week=THE_COURSE_WEEK, workload=SET_HOURS, instructor_rating=A_RATING
    )
    world.session.flush()

    hero_id = world.section_id(HERO)
    university = set(resolved(world, RESOLVE_UNIVERSITY, section_id=hero_id))
    this_term = {world.section_id(label) for label in (HERO, "this-term")}
    last_term = {world.section_id(label) for label in ("last-term-a", "last-term-b")}

    assert university == this_term | last_term, (
        f"The university population resolves to {sorted(map(str, university))}. It should hold the "
        f"two current-term sections {sorted(map(str, this_term))} and the two prior-term ones "
        f"{sorted(map(str, last_term))}: §5.1 compares week N 'against week N of 12-week sections "
        "of the same level in the current *and prior* terms, regardless of start date', and "
        "decision 6 adds no horizon beyond §4's retention rule."
    )

    mean, median = mean_and_median(the_workload(world, UNIVERSITY_POPULATION))
    assert carries(mean, SET_HOURS), (
        f"The workload mean over a population of {len(university)} sections — two of them in the "
        f"prior term — does not carry {SET_HOURS}: {serialized_figure(mean)}. The current term "
        f"holds only two sections of this cohort, one below the configured minimum of {sections}, "
        "so a figure here exists only if the prior term's are counted, and only if course week 2 "
        "of a section starting in the prior term's first week is compared with course week 2 of "
        "one starting in this term's fourth."
    )
    assert carries(median, SET_HOURS), (
        f"The workload median over the same population is {serialized_figure(median)}; every "
        f"response reported {SET_HOURS}."
    )


def a_named_set_world(world: BenchmarkWorld, *, sections: int, respondents: int) -> tuple[str, ...]:
    """A resolvable set, an empty set, and a set declaring a length nothing runs.

    The resolvable one holds as many member courses as the configured section
    minimum, so it stands at the threshold and the suppression the other two
    produce is about *them* rather than about a set that was thin anyway.
    """
    world.build()
    world.plant_section(HERO, cohort=EARLY_COHORT, level=LEVEL)
    members = tuple(f"named-{index}" for index in range(sections))
    for label in members:
        world.plant_section(label, cohort=EARLY_COHORT, level=LEVEL)

    world.comparison_set("resolvable", length_weeks=TWELVE_WEEKS, level=LEVEL, courses_of=members)
    world.comparison_set("empty", length_weeks=TWELVE_WEEKS, level=LEVEL)
    world.comparison_set("wrong-length", length_weeks=EIGHT_WEEKS, level=LEVEL, courses_of=members)

    world.answer_the_plan(
        dict(spread(members, respondents=respondents, subject_prefix="e5-04-named")),
        course_week=THE_COURSE_WEEK,
        workload=SET_HOURS,
        instructor_rating=A_RATING,
    )
    world.session.flush()
    return members


def test_an_empty_named_set_answers_suppressed_figures_rather_than_an_error(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """Criterion 6: "never an error and never an absent member".

    ADR 0164 lets a set be empty and leaves what that means to this ticket: it
    resolves to no sections, and no sections is a figure suppressed exactly as a
    thin one is. E5-06 previews a set while leadership is still building it, so
    the empty set is the ordinary first state of every named set rather than an
    edge case — a service that raised would make the preview unreachable at
    precisely the moment somebody is using it.

    **The control is the populated set in the same world**, over the same three
    courses' sections, which must answer a figure. Without it "both figures are
    suppressed" is satisfied by a service that suppresses every named set there
    is.

    **`mean` and `median` must both be present.** "Never an absent member" is the
    criterion's own words: a `None` where a figure belongs is what makes a panel
    throw rather than draw a suppression notice, which is a defect this epic has
    already met once (`docs/tickets/e5/deferred.md`).

    **The mutation it kills:** an empty section list short-circuiting to `None`,
    to an empty list of points, or to a raised exception — and a resolution that
    answered the *whole cohort* when it found no members, which is the failure
    that shows a figure rather than withholding one.
    """
    minimums = report_api_contract.minimums()
    respondents = minimums[report_api_contract.minimum_respondents]
    a_named_set_world(
        benchmark_world,
        sections=minimums[report_api_contract.minimum_sections],
        respondents=respondents,
    )

    api = benchmarks_api()
    empty_id = benchmark_world.comparison_set_id("empty")
    resolvable_id = benchmark_world.comparison_set_id("resolvable")

    assert resolved(benchmark_world, RESOLVE_NAMED_SET, set_id=empty_id) == [], (
        "A comparison set with no member courses resolves to sections. ADR 0164 makes membership "
        "the whole of what a set contains, so there is nothing for those sections to have come "
        "from — a cohort answered in place of an empty set is a benchmark leadership never "
        "defined."
    )

    control = api[NAMED_SET_WORKLOAD](
        benchmark_world.session, set_id=resolvable_id, course_week=THE_COURSE_WEEK
    )
    control_mean, _control_median = mean_and_median(control)
    assert carries(control_mean, SET_HOURS), (
        f"The control failed before the assertion it protects: the populated set in the same "
        f"world does not carry {SET_HOURS}: {serialized_figure(control_mean)}. Until it does, the "
        "suppression below is satisfied by a service that answers nothing to every named set."
    )

    empty_workload = api[NAMED_SET_WORKLOAD](
        benchmark_world.session, set_id=empty_id, course_week=THE_COURSE_WEEK
    )
    empty_mean, empty_median = mean_and_median(empty_workload)
    assert not carries(empty_mean, SET_HOURS), (
        f"The workload mean over an empty comparison set carries {SET_HOURS}: "
        f"{serialized_figure(empty_mean)} — which is the figure the *populated* set answers. A set "
        "with no members resolves to no sections, and a number over no sections came from "
        "somewhere it should not have."
    )
    assert not carries(empty_median, SET_HOURS), (
        f"The median over an empty comparison set carries {SET_HOURS}: "
        f"{serialized_figure(empty_median)}."
    )


def test_a_named_set_declaring_a_length_none_of_its_courses_runs_is_suppressed(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """Criterion 6's other half: unresolvable, not empty.

    The set names the same courses as the resolvable one and declares eight
    weeks; every section those courses run is twelve. ADR 0164 makes the declared length part of what a set
    *is* — "the member courses' sections of the declared length" — so this set
    resolves to nothing while holding three members, which is a different state
    from the empty one and the state a length changed after the fact produces.

    **The control is the twelve-week set over the same three courses**, in the
    same world, which answers a figure. So the suppression asserted here is about
    the declared length and not about the courses, the sections, the week or the
    world.

    **The mutation it kills:** the declared length ignored, which turns a named
    set into "every section of its member courses" and quietly compares an
    eight-week cohort against twelve-week sections — the averaging §5.1 forbids
    in its first sentence.
    """
    minimums = report_api_contract.minimums()
    respondents = minimums[report_api_contract.minimum_respondents]
    members = a_named_set_world(
        benchmark_world,
        sections=minimums[report_api_contract.minimum_sections],
        respondents=respondents,
    )

    api = benchmarks_api()
    wrong_length = benchmark_world.comparison_set_id("wrong-length")
    resolvable = benchmark_world.comparison_set_id("resolvable")

    assert resolved(benchmark_world, RESOLVE_NAMED_SET, set_id=wrong_length) == [], (
        "A set declaring eight weeks resolves to sections whose courses run twelve. §5.1: "
        "'to be comparable, sections must match on both length and level', and ADR 0164 puts the "
        "length on the set row precisely so that the sections it resolves to are held to it."
    )
    assert len(resolved(benchmark_world, RESOLVE_NAMED_SET, set_id=resolvable)) == len(members), (
        "The control failed before the assertion it protects: the twelve-week set over the same "
        f"{len(members)} courses resolves to something other than their sections, so a resolution "
        "of nothing above says nothing about the declared length."
    )

    mean, median = mean_and_median(
        api[NAMED_SET_WORKLOAD](
            benchmark_world.session, set_id=wrong_length, course_week=THE_COURSE_WEEK
        )
    )
    control_mean, _control_median = mean_and_median(
        api[NAMED_SET_WORKLOAD](
            benchmark_world.session, set_id=resolvable, course_week=THE_COURSE_WEEK
        )
    )

    assert carries(control_mean, SET_HOURS), (
        f"The twelve-week set over the same courses does not carry {SET_HOURS}: "
        f"{serialized_figure(control_mean)}."
    )
    assert not carries(mean, SET_HOURS), (
        f"The workload mean over a set declaring a length none of its courses runs carries "
        f"{SET_HOURS}: {serialized_figure(mean)} — the figure the twelve-week set answers. The "
        "declared length is not a label on the set; it is half of what makes its sections "
        "comparable."
    )
    assert not carries(
        median, SET_HOURS
    ), f"The median over the same set carries {SET_HOURS}: {serialized_figure(median)}."


def test_a_named_sets_trend_over_an_empty_set_answers_suppressed_points_without_raising(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """Criterion 6 on the trend door, which is the one a preview draws.

    The workload test above drives one of the two named-set entry points; this
    drives the other, because "never an error" is a promise about the door a
    caller uses and E5-06's preview asks for a series. Whatever the series holds
    — no points at all, or a point per week carrying nothing — every figure in it
    must be empty, and the call must return.

    **The control is the populated set's own trend in the same world**, which has
    to carry the rating the three sections reported. An empty answer from both
    would otherwise satisfy this test completely.

    **The mutation it kills:** a division by the section count, a `strict`
    unnest, or any other body that raises on the empty list — the shapes E5-03's
    own empty-set test names — reached this time through the service rather than
    through the function.
    """
    minimums = report_api_contract.minimums()
    respondents = minimums[report_api_contract.minimum_respondents]
    a_named_set_world(
        benchmark_world,
        sections=minimums[report_api_contract.minimum_sections],
        respondents=respondents,
    )

    api = benchmarks_api()
    figure_type = reporting_symbol(FIGURE_TYPE_NAME)

    control = api[NAMED_SET_TREND](
        benchmark_world.session,
        set_id=benchmark_world.comparison_set_id("resolvable"),
        stream=INSTRUCTOR_STREAM,
    )
    shown = [figure for figure in figures_in(control, figure_type) if carries(figure, A_RATING)]
    assert shown, (
        f"The control failed before the assertion it protects: the populated set's trend carries "
        f"no figure holding {A_RATING}, which is what all {respondents} responses rated the "
        f"instructor. What it answered: {control!r}."
    )

    empty = api[NAMED_SET_TREND](
        benchmark_world.session,
        set_id=benchmark_world.comparison_set_id("empty"),
        stream=INSTRUCTOR_STREAM,
    )
    leaked = [figure for figure in figures_in(empty, figure_type) if carries(figure, A_RATING)]
    assert not leaked, (
        f"The trend over an empty comparison set carries the populated set's rating {A_RATING} in "
        f"{len(leaked)} of its figures: {empty!r}. A set with no members has no sections, and "
        "every figure over it is suppressed rather than borrowed."
    )
