"""E5-04's fix round — a figure is sealed against the counts of the people and sections *it* aggregates.

The security review of this ticket found two HIGHs with one root cause, and the
cause is `docs/MISTAKES.md` entry 50's class rather than a slip: **a figure was
sealed against a count of something other than what the figure is about.**

  - A rating trend point's mean comes from the per-stream rating read, and it was
    sealed with the week's overall section and respondent counts — counts of
    anybody who answered anything that week. A stream answered inside one section
    could therefore be shown as a five-section figure.
  - The workload mean and median are computed over the responses that carry hours
    (ADR 0165's decision keeps the row when nobody reports any), and they were
    sealed with counts of every responder. Hours from two students could be shown
    as a figure over fifteen.
  - The term axis carried the same divergence a third time.

**The rule these tests bind to, and it is about behaviour rather than columns.**
Every figure is sealed with the counts of its own **contributors**: the distinct
students whose answers that figure aggregates, and the distinct sections those
students' responses belong to. The implementer ships whatever `_v002` bodies
carry those counts; nothing here names a column, and every assertion is made
through a value this module planted.

**Each world is a near miss on exactly one count.** The week's *overall* counts
always clear both minimums — that is what makes these tests about the divergence
rather than about the thresholds — and one figure's own contributors fall one
short in exactly one currency. A test that moved both at once could not say
which count the service had used.

**Every suppression assertion has its positive control in the same world**
(`docs/MISTAKES.md` entry 3), and every control sits **at** a minimum rather than
above it, so the same tests carry the "at the minimum is enough" boundary: §5.1
suppresses a figure "computed from fewer than the configured number of
sections", so the configured number itself is shown.

**The over-suppressing fix is a real risk and two tests exist for it.** The
cheap way to satisfy everything above is to seal every figure against the
smallest count in sight, which empties half the report.
`test_a_workload_comparison_at_the_hours_minimum_is_shown` and
`test_every_figure_shows_when_each_one_s_own_contributors_clear_both_minimums`
are green today and must stay green.

**Which failure a red here is.** The service exists, so these are assertion
reds — a figure carrying a value it should have suppressed — not missing
symbols.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    BENCHMARK_TREND,
    BENCHMARK_WORKLOAD,
    COURSE_STREAM,
    DEFAULT_SET_POPULATION,
    INSTRUCTOR_STREAM,
    NAMED_SET_TERM_AXIS,
    UG,
    BenchmarkWorld,
    a_population,
    benchmarks_api,
    carries,
    figures_in,
    mean_and_median,
    points_by_week,
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
COHORT = "U"
LEVEL = UG
TWELVE_WEEKS = 12
THE_COURSE_WEEK = 2

# The two ratings, one per stream. Different values, so a suppressed point cannot
# be satisfied by the other stream's figure arriving under the wrong label, and
# neither is a count any of these worlds holds — a `carries` reader that matched
# a section count would fire in the wrong direction and read as a broken test.
INSTRUCTOR_RATING = Decimal("4")
COURSE_RATING = Decimal("5")

# Hours where the workload figure is the subject and one value is enough: mean
# and median are both this, so a suppression assertion is about one number.
HOURS = Decimal("7.5")

# Hours for the all-pass control, where mean and median must be **different**
# numbers or a fix that copies one over the other is undetectable (the mutation
# battery's finding). Two thirds report the low value, so the median sits on it
# and the mean sits above.
LOW_HOURS = Decimal("2.5")
HIGH_HOURS = Decimal("8.5")

# How many extra students answer only the control's stream, in the worlds whose
# near miss is a section count. Two rather than one, so the extra section is not
# a section with a single respondent in it — which would be a second thin thing
# in a world about one.
A_FEW = 2

ONE = 1


def set_labels(sections: int, *, prefix: str = "set") -> tuple[str, ...]:
    return tuple(f"{prefix}-{index}" for index in range(sections))


def a_lead_and_a_hero(world: BenchmarkWorld, labels: tuple[str, ...]) -> None:
    """The hero, the labelled sections, and one lead over all of them.

    The comparison figures below are the hero's default set, which is every
    labelled section and never the hero itself (decision 5) — so the counts under
    test are the counts of the labelled sections' answers alone.
    """
    world.build()
    world.plant_section(HERO, cohort=COHORT, level=LEVEL)
    for label in labels:
        world.plant_section(label, cohort=COHORT, level=LEVEL)
    world.lead(THE_LEAD, HERO, *labels)


def the_hero_answers(world: BenchmarkWorld, *, subject: str, course_week: int) -> None:
    """One answer in the hero's own section, so the hero has a week to compare.

    Never part of any figure below — the hero is excluded from its own default
    set — and planted with both ratings and hours so that no assertion here can
    turn on the hero having been thin at something.
    """
    world.respond(
        HERO,
        course_week=course_week,
        subject=subject,
        workload=HOURS,
        instructor_rating=INSTRUCTOR_RATING,
        course_rating=COURSE_RATING,
    )


def the_trend(world: BenchmarkWorld, stream: str) -> dict[int, Any]:
    """The default-set trend for one stream, as `{course_week: figure}`."""
    api = benchmarks_api()
    return points_by_week(
        api[BENCHMARK_TREND](
            world.session,
            section_id=world.section_id(HERO),
            population=a_population(DEFAULT_SET_POPULATION),
            stream=stream,
        )
    )


def the_workload(world: BenchmarkWorld, *, course_week: int = THE_COURSE_WEEK) -> Any:
    """The default-set workload comparison for one course week."""
    api = benchmarks_api()
    return api[BENCHMARK_WORKLOAD](
        world.session,
        section_id=world.section_id(HERO),
        population=a_population(DEFAULT_SET_POPULATION),
        course_week=course_week,
    )


def test_a_rating_trend_point_suppresses_when_its_stream_spans_too_few_sections(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """HIGH 1, the section currency: the stream's own sections, not the week's.

    The week clears both minimums comfortably — every section was answered and
    more than enough people answered. Inside it, the instructor rating was
    answered only in the sections but one: enough *people* to clear the
    respondent minimum, one section short of the section minimum.

    **The course stream in the same world is the control**, and it stands at
    exactly the section minimum: the same rows, one question further along, shown
    because its own contributors clear both. So a suppressed instructor point
    cannot be a service that answers nothing, a world that was never planted, or
    a trend with no points in it.

    **The mutation it kills:** the point sealed with the week's overall section
    count — which is the defect as shipped. The per-stream rating read returns no
    section count at all, so the overall one was the number at hand, and it is a
    count of sections where *somebody answered something*.

    **The near miss it must not fire on:** the other stream's counts standing in
    for this stream's. The two streams differ here by exactly one section and by
    the value each carries, so a service that computed one stream's seal and used
    it for both is red on this test and green on nothing.
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]

    labels = set_labels(sections)
    thin = labels[:-1]

    a_lead_and_a_hero(benchmark_world, labels)
    benchmark_world.answer_the_plan(
        dict(spread(thin, respondents=respondents, subject_prefix="e5-04-stream-sections")),
        course_week=THE_COURSE_WEEK,
        workload=HOURS,
        instructor_rating=INSTRUCTOR_RATING,
        course_rating=COURSE_RATING,
    )
    benchmark_world.answer_the_plan(
        dict(spread(labels[-1:], respondents=A_FEW, subject_prefix="e5-04-stream-sections-last")),
        course_week=THE_COURSE_WEEK,
        workload=HOURS,
        course_rating=COURSE_RATING,
    )
    the_hero_answers(
        benchmark_world, subject="e5-04-stream-sections-hero", course_week=THE_COURSE_WEEK
    )
    benchmark_world.session.flush()

    instructor = the_trend(benchmark_world, INSTRUCTOR_STREAM)[THE_COURSE_WEEK]
    course = the_trend(benchmark_world, COURSE_STREAM)[THE_COURSE_WEEK]

    assert carries(course, COURSE_RATING), (
        f"The control failed before the assertion it protects: the course stream — answered by "
        f"{respondents + A_FEW} people across all {sections} sections, which is exactly the "
        f"configured section minimum — does not carry {COURSE_RATING}: "
        f"{serialized_figure(course)}."
    )
    assert not carries(instructor, INSTRUCTOR_RATING), (
        f"The instructor stream's point carries {INSTRUCTOR_RATING}: "
        f"{serialized_figure(instructor)}. That rating was answered in {sections - ONE} sections — "
        f"one below the configured minimum of {sections} — by {respondents} people, who clear the "
        "other minimum. The week as a whole had all "
        f"{sections} sections answered, and that is the count this figure was sealed with before "
        "the fix: §4.1 item 7 is about the figure, so the sections that count are the sections "
        "this mean was computed from."
    )
    assert not carries(instructor, COURSE_RATING), (
        f"The instructor stream's point carries the *course* stream's mean {COURSE_RATING}: "
        f"{serialized_figure(instructor)}. One stream's figure served under the other's label is a "
        "second defect this world can see, and it would make the suppression above meaningless."
    )


def test_a_rating_trend_point_suppresses_when_too_few_students_answered_that_stream(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """HIGH 1, the respondent currency: the stream's own people, not the week's.

    The mirror of the test above, and the two are the catalog rather than the
    concept (`docs/MISTAKES.md` entry 22): each currency is driven to its own
    boundary with the other cleared. Here the instructor rating reaches every
    section — so its section count is fine — and one person short of the
    respondent minimum answered it, while a further student answered the course
    question only.

    **The control is the course stream in the same world**, standing at exactly
    the respondent minimum and at exactly the section minimum.

    **The mutation it kills:** the point sealed with the week's overall
    respondent count, which counts the student who rated the course and never the
    instructor. `docs/MISTAKES.md` entry 50 in one sentence: the minimum is about
    the people behind *this* number.
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]

    labels = set_labels(sections)

    a_lead_and_a_hero(benchmark_world, labels)
    benchmark_world.answer_the_plan(
        dict(spread(labels, respondents=respondents - ONE, subject_prefix="e5-04-stream-people")),
        course_week=THE_COURSE_WEEK,
        workload=HOURS,
        instructor_rating=INSTRUCTOR_RATING,
        course_rating=COURSE_RATING,
    )
    benchmark_world.answer_the_plan(
        dict(spread(labels[:1], respondents=ONE, subject_prefix="e5-04-stream-people-last")),
        course_week=THE_COURSE_WEEK,
        workload=HOURS,
        course_rating=COURSE_RATING,
    )
    the_hero_answers(
        benchmark_world, subject="e5-04-stream-people-hero", course_week=THE_COURSE_WEEK
    )
    benchmark_world.session.flush()

    instructor = the_trend(benchmark_world, INSTRUCTOR_STREAM)[THE_COURSE_WEEK]
    course = the_trend(benchmark_world, COURSE_STREAM)[THE_COURSE_WEEK]

    assert carries(course, COURSE_RATING), (
        f"The control failed before the assertion it protects: the course stream — answered by "
        f"exactly {respondents} people across exactly {sections} sections, both at their "
        f"configured minimums — does not carry {COURSE_RATING}: {serialized_figure(course)}."
    )
    assert not carries(instructor, INSTRUCTOR_RATING), (
        f"The instructor stream's point carries {INSTRUCTOR_RATING}: "
        f"{serialized_figure(instructor)}. {respondents - ONE} people answered that question — one "
        f"below the configured minimum of {respondents} — across all {sections} sections, so the "
        "section count is not what is short here. The week's overall respondent count is "
        f"{respondents}, because one more student answered the course question, and that is the "
        "number this figure was sealed with before the fix."
    )


def test_a_workload_comparison_suppresses_when_too_few_students_reported_hours(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """HIGH 2: the hours' own people, not the week's responders.

    ADR 0165 keeps a cohort week's row when nobody reported hours — "null, never
    nought" — which means the workload figures are computed over a *subset* of
    the week's responses by design. One student here answered the ratings and
    left the hours blank, so the week has the respondent minimum's worth of
    people and the hours have one fewer.

    **Both figures are asserted**, because §4.1 item 7 covers "a mean, a median,
    or any other statistic": they are computed over the same contributors and
    suppress together, and a fix that sealed one and not the other would leave
    the median telling you what the mean was forbidden to.

    **The control in the same world is the instructor trend point**, which every
    one of those people answered — so the world is not thin, the service is not
    silent, and what is suppressed is the figure whose own contributors fell
    short.

    **The mutation it kills:** the pair sealed with the week's overall respondent
    count, which counts the student who reported no hours at all. Two students'
    hours can then be shown as a figure over fifteen people — the disclosure
    §4.1 item 7 exists to prevent, reached through a benchmark.
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]

    labels = set_labels(sections)

    a_lead_and_a_hero(benchmark_world, labels)
    benchmark_world.answer_the_plan(
        dict(spread(labels, respondents=respondents - ONE, subject_prefix="e5-04-hours-people")),
        course_week=THE_COURSE_WEEK,
        workload=HOURS,
        instructor_rating=INSTRUCTOR_RATING,
    )
    benchmark_world.answer_the_plan(
        dict(spread(labels[:1], respondents=ONE, subject_prefix="e5-04-hours-people-last")),
        course_week=THE_COURSE_WEEK,
        instructor_rating=INSTRUCTOR_RATING,
    )
    the_hero_answers(
        benchmark_world, subject="e5-04-hours-people-hero", course_week=THE_COURSE_WEEK
    )
    benchmark_world.session.flush()

    mean, median = mean_and_median(the_workload(benchmark_world))
    control = the_trend(benchmark_world, INSTRUCTOR_STREAM)[THE_COURSE_WEEK]

    assert carries(control, INSTRUCTOR_RATING), (
        f"The control failed before the assertion it protects: the instructor stream — answered by "
        f"all {respondents} people across all {sections} sections — does not carry "
        f"{INSTRUCTOR_RATING}: {serialized_figure(control)}."
    )
    assert not carries(mean, HOURS), (
        f"The comparison workload mean carries {HOURS}: {serialized_figure(mean)}. "
        f"{respondents - ONE} people reported hours — one below the configured minimum of "
        f"{respondents} — and the {respondents}th answered the ratings and left the hours blank. "
        "ADR 0165 keeps that response in the week's counts on purpose, so the week's respondent "
        "count is the minimum and the hours' own is one short: the figure has to be sealed against "
        "the people whose hours it averaged."
    )
    assert not carries(median, HOURS), (
        f"The comparison workload median carries {HOURS}: {serialized_figure(median)}. It is "
        "computed over the same hours as the mean beside it and is suppressed by the same count; a "
        "median shown where its mean was withheld discloses the same population."
    )


def test_a_workload_comparison_suppresses_when_the_hours_come_from_too_few_sections(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """HIGH 2 in the other currency: the hours' own sections.

    The same divergence as the test above, counted in sections rather than in
    people — `docs/MISTAKES.md` entry 35's rule that a guard is named in every
    currency the thing it guards is held in. Hours were reported in every section
    but one, by enough people to clear the respondent minimum; the last section's
    students answered the instructor question and left the hours blank.

    **The control in the same world is the instructor trend point**, whose own
    contributors span every section — exactly the section minimum — and every
    respondent.

    **The mutation it kills:** the pair sealed with the week's overall section
    count. A fix that corrected only the respondent count — which is the half the
    review's second finding names — passes the sibling test above and is red
    here.
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]

    labels = set_labels(sections)
    thin = labels[:-1]

    a_lead_and_a_hero(benchmark_world, labels)
    benchmark_world.answer_the_plan(
        dict(spread(thin, respondents=respondents, subject_prefix="e5-04-hours-sections")),
        course_week=THE_COURSE_WEEK,
        workload=HOURS,
        instructor_rating=INSTRUCTOR_RATING,
    )
    benchmark_world.answer_the_plan(
        dict(spread(labels[-1:], respondents=A_FEW, subject_prefix="e5-04-hours-sections-last")),
        course_week=THE_COURSE_WEEK,
        instructor_rating=INSTRUCTOR_RATING,
    )
    the_hero_answers(
        benchmark_world, subject="e5-04-hours-sections-hero", course_week=THE_COURSE_WEEK
    )
    benchmark_world.session.flush()

    mean, median = mean_and_median(the_workload(benchmark_world))
    control = the_trend(benchmark_world, INSTRUCTOR_STREAM)[THE_COURSE_WEEK]

    assert carries(control, INSTRUCTOR_RATING), (
        f"The control failed before the assertion it protects: the instructor stream — answered in "
        f"all {sections} sections by {respondents + A_FEW} people — does not carry "
        f"{INSTRUCTOR_RATING}: {serialized_figure(control)}."
    )
    assert not carries(mean, HOURS), (
        f"The comparison workload mean carries {HOURS}: {serialized_figure(mean)}. The hours came "
        f"from {sections - ONE} sections — one below the configured minimum of {sections} — while "
        f"the week as a whole was answered in all {sections}. A mean over two sections' hours is a "
        "number about those two sections, which is the inference §5.1 says suppression exists to "
        "prevent."
    )
    assert not carries(
        median, HOURS
    ), f"The comparison workload median carries {HOURS}: {serialized_figure(median)}."


def test_a_workload_comparison_at_the_hours_minimum_is_shown(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """The twin of the hours world, differing by one student's single answer.

    Everything is as it is two tests above except that the last student reports
    hours too, so the contributors stand at exactly the respondent minimum across
    exactly the section minimum. Both figures are shown, because §5.1 suppresses
    a figure "computed from fewer than the configured number" and the configured
    number itself is enough.

    **This is the test the over-suppressing fix fails**, and that fix is the one
    to expect: sealing every figure against the smallest count in sight, or
    against the count of *responses* rather than of contributors, or with `>`
    where `>=` belongs. Each of those satisfies all four suppression tests above
    and empties half the report.

    **Green today** — before the fix the figure is sealed with the week's counts,
    which are the same numbers in this world — and green after it. The pair with
    its twin is what makes either mean anything: the two worlds differ by a
    single `workload=` value.
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]

    labels = set_labels(sections)

    a_lead_and_a_hero(benchmark_world, labels)
    benchmark_world.answer_the_plan(
        dict(spread(labels, respondents=respondents - ONE, subject_prefix="e5-04-hours-enough")),
        course_week=THE_COURSE_WEEK,
        workload=HOURS,
        instructor_rating=INSTRUCTOR_RATING,
    )
    benchmark_world.answer_the_plan(
        dict(spread(labels[:1], respondents=ONE, subject_prefix="e5-04-hours-enough-last")),
        course_week=THE_COURSE_WEEK,
        workload=HOURS,
        instructor_rating=INSTRUCTOR_RATING,
    )
    the_hero_answers(
        benchmark_world, subject="e5-04-hours-enough-hero", course_week=THE_COURSE_WEEK
    )
    benchmark_world.session.flush()

    mean, median = mean_and_median(the_workload(benchmark_world))

    assert carries(mean, HOURS), (
        f"The comparison workload mean over exactly {respondents} people reporting hours across "
        f"exactly {sections} sections — both at their configured minimums — does not carry "
        f"{HOURS}: {serialized_figure(mean)}. Every one of them reported those hours. A figure "
        "withheld here is a fix that suppresses whenever two counts differ, or one that reads the "
        "minimum as 'more than'."
    )
    assert carries(median, HOURS), (
        f"The comparison workload median over the same contributors does not carry {HOURS}: "
        f"{serialized_figure(median)}."
    )


def test_a_term_axis_figure_suppresses_when_too_few_students_reported_hours_for_it(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """The same divergence on the second axis, through the door E5-06 and E9 read.

    The term axis carries the review's third instance, and it is the one no
    screen draws yet — which is why it is worth a test of its own rather than a
    line in someone's fix: a figure that leaves this module unsealed leaves it
    towards a surface nobody has written.

    **Two start cohorts in one named set**, so the control is a figure in the
    same answer rather than in another world. The first cohort's hours come from
    one person fewer than the minimum; the second's come from exactly the
    minimum, across exactly the section minimum's worth of sections. Each cohort
    carries its own hours value, so which figure is which is legible without this
    test knowing the row's shape — the shape is the implementer's, and a reader
    keyed on a member name would assert nothing the day it changed.

    **The mutation it kills:** the term-axis rows sealed with the cohort's
    overall counts, which is the third face of one defect. **The near miss:** a
    fix applied to the two set functions and not to the term-axis read, which
    leaves this test red alone and is exactly the shape of "fixed where the
    review pointed".
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]

    thin_labels = set_labels(sections, prefix="thin")
    full_labels = set_labels(sections, prefix="full")

    world = benchmark_world.build()
    for label in thin_labels:
        world.plant_section(label, cohort=COHORT, level=LEVEL)
    for label in full_labels:
        # A second start cohort of the same length and level: a different start
        # date, so it is a different row on the term axis and the same population
        # on the course-week one.
        world.plant_section(label, cohort="R", level=LEVEL)
    world.comparison_set(
        "named",
        length_weeks=TWELVE_WEEKS,
        level=LEVEL,
        courses_of=thin_labels + full_labels,
    )

    world.answer_the_plan(
        dict(spread(thin_labels, respondents=respondents - ONE, subject_prefix="e5-04-axis-thin")),
        course_week=THE_COURSE_WEEK,
        workload=HOURS,
        instructor_rating=INSTRUCTOR_RATING,
    )
    world.answer_the_plan(
        dict(spread(thin_labels[:1], respondents=ONE, subject_prefix="e5-04-axis-thin-last")),
        course_week=THE_COURSE_WEEK,
        instructor_rating=INSTRUCTOR_RATING,
    )
    world.answer_the_plan(
        dict(spread(full_labels, respondents=respondents, subject_prefix="e5-04-axis-full")),
        course_week=THE_COURSE_WEEK,
        workload=LOW_HOURS,
        instructor_rating=INSTRUCTOR_RATING,
    )
    world.session.flush()

    api = benchmarks_api()
    figure_type = reporting_symbol(FIGURE_TYPE_NAME)
    answered = api[NAMED_SET_TERM_AXIS](world.session, set_id=world.comparison_set_id("named"))
    figures = figures_in(answered, figure_type)

    assert figures, (
        f"The term axis answered {answered!r}, which holds no figure at all. Both start cohorts "
        "were answered at course week 2, so there is something to answer and the suppression "
        "asserted below would otherwise be a statement about an empty result."
    )
    assert any(carries(figure, LOW_HOURS) for figure in figures), (
        f"The control failed before the assertion it protects: no figure in the term axis carries "
        f"{LOW_HOURS}, which exactly {respondents} people reported across exactly {sections} "
        f"sections of the second start cohort — both counts at their configured minimums. What it "
        f"answered: {answered!r}."
    )
    assert not any(carries(figure, HOURS) for figure in figures), (
        f"A term-axis figure carries {HOURS}: {answered!r}. In that start cohort "
        f"{respondents - ONE} people reported hours — one below the configured minimum — while a "
        f"{respondents}th answered the ratings and left the hours blank, so the cohort's overall "
        "respondent count reaches the minimum and the hours' own does not. The axis is a second "
        "read of the same figures and takes the same rule: a figure is sealed against the people "
        "it was computed from."
    )


def test_every_figure_shows_when_each_one_s_own_contributors_clear_both_minimums(
    benchmark_world: BenchmarkWorld, report_api_contract: Any, pinned_benchmark_clock: Any
) -> None:
    """The anti-vacuity world: nothing diverges, so nothing is suppressed.

    Every student answers both ratings and reports hours, and the population
    stands at exactly both minimums. All four figures — the two streams' points,
    the workload mean and the workload median — are shown.

    **This is the whole of the guard against the bad fix.** Six tests in this
    module say "suppress", and a service that suppressed everything would pass
    all six. This one says what must still be visible, and it is the test to read
    first if the fix round turns the report into a page of notices.

    **Mean and median are different numbers here**, which the mutation battery
    asked for: two thirds of the students report the low value so the median sits
    on it, and the third reporting the high one pulls the mean above it. With one
    value everywhere the two figures coincide, and a fix that copied one over the
    other would be undetectable by construction.

    **Green today and green after the fix.**
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]

    labels = set_labels(sections)
    a_lead_and_a_hero(benchmark_world, labels)

    plan = dict(spread(labels, respondents=respondents, subject_prefix="e5-04-nothing-diverges"))
    subjects = sorted(plan)
    reporting_high = max(1, len(subjects) // 3)
    high, low = subjects[:reporting_high], subjects[reporting_high:]
    for hours, group in ((HIGH_HOURS, high), (LOW_HOURS, low)):
        benchmark_world.answer_the_plan(
            {subject: plan[subject] for subject in group},
            course_week=THE_COURSE_WEEK,
            workload=hours,
            instructor_rating=INSTRUCTOR_RATING,
            course_rating=COURSE_RATING,
        )
    the_hero_answers(
        benchmark_world, subject="e5-04-nothing-diverges-hero", course_week=THE_COURSE_WEEK
    )
    benchmark_world.session.flush()

    # By hand over the values this test planted, never read back from anything
    # (`docs/MISTAKES.md` entries 19 and 30). The median is the majority value
    # because the low group is more than half of them, which is asserted rather
    # than assumed.
    assert len(low) > len(high), (
        f"{len(low)} students report {LOW_HOURS} and {len(high)} report {HIGH_HOURS}, so the low "
        "value is not the majority and the median below is not the number this test says it is."
    )
    expected_mean = (LOW_HOURS * len(low) + HIGH_HOURS * len(high)) / len(plan)
    assert expected_mean != LOW_HOURS, (
        f"The planted hours give a mean of {expected_mean}, which is the median. The two figures "
        "have to be different numbers here or a fix that serves one of them twice is invisible."
    )

    instructor = the_trend(benchmark_world, INSTRUCTOR_STREAM)[THE_COURSE_WEEK]
    course = the_trend(benchmark_world, COURSE_STREAM)[THE_COURSE_WEEK]
    mean, median = mean_and_median(the_workload(benchmark_world))

    assert carries(instructor, INSTRUCTOR_RATING), (
        f"The instructor stream's point, answered by all {respondents} people across all "
        f"{sections} sections, does not carry {INSTRUCTOR_RATING}: {serialized_figure(instructor)}."
    )
    assert carries(course, COURSE_RATING), (
        f"The course stream's point, answered by the same people in the same sections, does not "
        f"carry {COURSE_RATING}: {serialized_figure(course)}."
    )
    assert carries(mean, expected_mean), (
        f"The workload mean does not carry {expected_mean}: {serialized_figure(mean)}. "
        f"{len(low)} students reported {LOW_HOURS} and {len(high)} reported {HIGH_HOURS}, all of "
        f"them across {sections} sections, which is the mean of those {len(plan)} figures."
    )
    assert carries(median, LOW_HOURS), (
        f"The workload median does not carry {LOW_HOURS}: {serialized_figure(median)}. More than "
        "half the contributors reported that value, so it is the middle one — and it is not the "
        f"mean, which is {expected_mean}."
    )
