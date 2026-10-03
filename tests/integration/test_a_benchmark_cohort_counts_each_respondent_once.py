"""E5-03 criterion 2 — the respondent figure is a count of people.

"The respondent count is a count of **distinct students**, proven by a planted
student with two responses in cohort scope counting once (MISTAKES entry 50 —
the unit is the criterion)."

`docs/MISTAKES.md` entry 50 is the whole of why this module exists, and its rule
is one sentence: "a threshold is a promise about a candidate set — 'whoever
wrote this is one of at least *n* people' — so the number compared against it
has to be a count of the things the promise is about." `respondent_count` is
what E5-04 compares against `benchmark_min_respondents_default`, so it is that
number. A count of responses, of answers or of rows is not a count of people,
and a design that gives one person several of them — which a cohort does, by
construction, the moment a student takes two sections of one course — makes the
two diverge by a factor nobody states.

**The world plants the divergence rather than describing it.** One student is
enrolled in two sections of the same cohort and answers in both, in the same
course week. The cohort week therefore holds four responses from three people,
and every wrong unit answers four:

  - `count(*)` — four.
  - `count(user_id)` — four; the column is not null, so the only thing
    `DISTINCT` was doing is the thing that was dropped.
  - `count(DISTINCT response_id)` — four, and this is the near miss worth
    naming: it is a `DISTINCT` count, it reads as careful, and its unit is rows.
  - `count(DISTINCT answer_id)` — eight here, since each response carries a
    rating and a workload figure.

Only a distinct count over the response's person key answers three.

**The counts are asserted in two tests over one world**, because they are two
behaviours: that a repeat respondent counts once, and that the response figure
still counts both of their responses. A single test asserting both would go red
for either and name neither.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    COHORT_RATING_WEEK_VIEW,
    COHORT_WEEK_VIEW,
    INSTRUCTOR_STREAM,
    UG,
    BenchmarkWorld,
    require_benchmark_view,
)

pytestmark = pytest.mark.integration

THE_LENGTH = 12
THE_COURSE_WEEK = 2

# Four responses from three people. The shared student answers in both sections;
# the other two answer in one each.
#
# The hours are chosen so that the mean over all four is **4.25** — a quarter
# hour, so it is exact in binary and in decimal alike and cannot be confused
# with a floating-point artefact. What this module is about is which rows are
# counted, not how the arithmetic rounds; the mean is asserted anyway, because a
# respondent count that came out right while the mean came out over three rows
# would mean the two figures were computed over different sets.
SHARED_HOURS_IN_FIRST = Decimal("2.0")
SHARED_HOURS_IN_SECOND = Decimal("4.0")
FIRST_ONLY_HOURS = Decimal("5.0")
SECOND_ONLY_HOURS = Decimal("6.0")
COHORT_WORKLOAD_MEAN = Decimal("4.25")
COHORT_WORKLOAD_MEDIAN = Decimal("4.5")

EXPECTED_RESPONSES = 4
EXPECTED_RESPONDENTS = 3
EXPECTED_SECTIONS = 2

# The four figures as a reader sees them in a failure message, built once so the
# assertions below stay inside a readable line.
SUBMITTED_HOURS = (
    SHARED_HOURS_IN_FIRST,
    SHARED_HOURS_IN_SECOND,
    FIRST_ONLY_HOURS,
    SECOND_ONLY_HOURS,
)
HOURS_AS_WRITTEN = [str(value) for value in SUBMITTED_HOURS]
HOURS_IN_ORDER = [str(value) for value in sorted(SUBMITTED_HOURS)]

# The ratings, so the rating view's own count can be asserted on the same world.
# Four instructor ratings: 5, 5, 2, 4 — mean 4.0, and `rating_count` 4 rather
# than 3, because a rating count is a count of ratings and is not the figure the
# minimum is about. Naming both units in one module is deliberate: entry 50 is
# about a number whose unit was never said out loud.
SHARED_RATING_IN_FIRST = Decimal("5")
SHARED_RATING_IN_SECOND = Decimal("5")
FIRST_ONLY_RATING = Decimal("2")
SECOND_ONLY_RATING = Decimal("4")
EXPECTED_RATING_MEAN = Decimal("4")
EXPECTED_RATINGS = 4


def a_cohort_one_student_answered_twice(world: BenchmarkWorld) -> BenchmarkWorld:
    """Two sections of one cohort, four responses, three people.

    The shared student is enrolled in both sections, which is what makes the two
    responses "in cohort scope" rather than two unrelated rows: SPEC §5.1's
    comparison set is every section of a length and level, so one person
    appearing twice inside it is the ordinary case rather than an exotic one.
    """
    world.build()
    world.plant_section("first", cohort="U", level=UG)
    world.plant_section("second", cohort="U", level=UG)

    shared = world.student("e5-03-shared-respondent", enrolled_in=("first", "second"))
    world.respond(
        "first",
        course_week=THE_COURSE_WEEK,
        student=shared,
        workload=SHARED_HOURS_IN_FIRST,
        instructor_rating=SHARED_RATING_IN_FIRST,
    )
    world.respond(
        "second",
        course_week=THE_COURSE_WEEK,
        student=shared,
        workload=SHARED_HOURS_IN_SECOND,
        instructor_rating=SHARED_RATING_IN_SECOND,
    )
    world.respond(
        "first",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-first-only",
        workload=FIRST_ONLY_HOURS,
        instructor_rating=FIRST_ONLY_RATING,
    )
    world.respond(
        "second",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-second-only",
        workload=SECOND_ONLY_HOURS,
        instructor_rating=SECOND_ONLY_RATING,
    )
    return world


def the_cohort_row(world: BenchmarkWorld) -> dict[str, Any]:
    """The one workload-and-counts row, with the non-vacuity guard in front of it."""
    row = world.cohort_week(length_weeks=THE_LENGTH, level=UG, course_week=THE_COURSE_WEEK)
    assert row is not None, (
        f"`{COHORT_WEEK_VIEW}` has no row for the cohort week four students' worth of responses "
        f"were submitted in — two sections of a {THE_LENGTH}-week {UG} cohort, course week "
        f"{THE_COURSE_WEEK}. Every assertion about a count below would be vacuous against an "
        "absent row (`docs/MISTAKES.md` entry 3)."
    )
    return row


# **This test alone in this module is `invariant`-marked**, and the reason is
# §4.1 item 7 rather than arithmetic. That item forbids showing "a figure
# computed from a comparison set … below the benchmark minimum", and the number
# the minimum is compared against is this one: E5-04 reads `respondent_count`
# and compares it with `benchmark_min_respondents_default`, and the E5
# breakdown's decision 2 states in as many words that the respondent minimum
# counts distinct students, "never responses or answers". A figure that
# over-counts people is item 7 breached *in fact* while passing on paper — the
# comparison is shown, and it was computed from fewer people than the rule
# requires. The breach would live here, in the view, where no test of the
# chokepoint can see it, which is the kind of route the isolated §4.1 pass
# exists for. The two tests below are about the other figures' units and stay
# unmarked.
@pytest.mark.invariant
def test_a_student_who_answered_in_two_sections_of_a_cohort_counts_once(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 2, and `docs/MISTAKES.md` entry 50: the unit is people.

    Three people submitted the four responses this cohort week holds. The figure
    E5-04 compares against `benchmark_min_respondents_default` is three.

    **The response count is asserted first, and it is not ceremony.** It is what
    tells a reader of the failure whether the view lost a row or counted the
    right rows in the wrong unit — and without it, a view returning three
    responses from three people would satisfy this assertion while having
    dropped one of the shared student's submissions entirely, which is the same
    number reached by a defect in the opposite direction.

    **The mutation it exists to survive**: `count(DISTINCT <person key>)`
    replaced by `count(*)`, by `count(<person key>)`, or by
    `count(DISTINCT <response key>)` — all three answer 4. And the mutation one
    level out, which the ruling names: the figure computed per section and
    summed, which answers 4 here because sums of distincts are not distinct
    sums.
    **The near miss it tolerates**: one person submitting two *answers* inside
    one response, which is every response in this world and must not make them
    two respondents.
    """
    world = a_cohort_one_student_answered_twice(benchmark_world)
    row = the_cohort_row(world)

    assert row["response_count"] == EXPECTED_RESPONSES, (
        f"`response_count` is {row['response_count']!r} where four responses were submitted in "
        "this cohort week. This assertion is the premise of the one below rather than its subject: "
        "with the response count wrong, a respondent count of 3 could be three responses rather "
        f"than three people. The row is {row}."
    )
    assert row["respondent_count"] == EXPECTED_RESPONDENTS, (
        f"`respondent_count` is {row['respondent_count']!r}. Three people submitted the "
        f"{EXPECTED_RESPONSES} responses in this cohort week: one student is enrolled in both "
        "sections and answered in both.\n\n"
        "An answer of 4 is a count of rows wearing the name of a count of people — `count(*)`, "
        "`count(<person key>)` on a column that is never null, `count(DISTINCT <response key>)`, "
        "or a per-section distinct count summed across the sections. `docs/MISTAKES.md` entry 50 "
        "is this exact arithmetic: 'a threshold is a promise about a candidate set … so the number "
        "compared against it has to be a count of the things the promise is about'. E5-04 compares "
        "this figure against `benchmark_min_respondents_default`, so an over-count lets a cohort "
        "of three people pass a threshold that exists to keep one of them from being identified."
    )


def test_the_response_figure_still_counts_both_of_one_students_responses(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The pair to the test above: two figures, two units, and both are needed.

    `respondent_count` is people and `response_count` is submissions, and the
    cheapest way to make the test above pass forever is to make both of them
    distinct counts of people. That would be `docs/MISTAKES.md` entry 2 in the
    shape a pair of counts takes — the guard still there and no longer
    discriminating — and it would quietly change what E5-04's other figures mean.

    The workload statistics are asserted here too, over all four submissions:
    they are the reason `response_count` is the honest denominator, and a mean
    over three rows would say the deduplication reached the arithmetic as well
    as the count.

    **The mutation it exists to survive**: `response_count` written as
    `count(DISTINCT <person key>)` — the copy-paste from the line above it,
    which answers 3 — and a `DISTINCT ON (<person key>)` in the view's `FROM`,
    which drops one of the shared student's rows and moves the mean as well.
    """
    world = a_cohort_one_student_answered_twice(benchmark_world)
    row = the_cohort_row(world)

    assert row["response_count"] == EXPECTED_RESPONSES, (
        f"`response_count` is {row['response_count']!r} where four responses were submitted: two "
        "by one student in two sections of this cohort, and one each by two others. An answer of 3 "
        "is the respondent count copied into the response column, or a `DISTINCT ON` that dropped "
        "a row."
    )
    assert row["section_count"] == EXPECTED_SECTIONS, (
        f"`section_count` is {row['section_count']!r} where two sections answered. A 4 here is the "
        "response count in a third disguise; a 1 is a `DISTINCT` that reached the wrong column."
    )
    assert row["workload_mean"] == COHORT_WORKLOAD_MEAN, (
        f"`workload_mean` is {row['workload_mean']!r}. The four submitted figures are "
        f"{HOURS_AS_WRITTEN}, which average to exactly {COHORT_WORKLOAD_MEAN}. A mean over three "
        "of them is a deduplication that reached the arithmetic: a person counts once, and each "
        "of their responses still counts."
    )
    assert row["workload_median"] == COHORT_WORKLOAD_MEDIAN, (
        f"`workload_median` is {row['workload_median']!r}; the middle pair of {HOURS_IN_ORDER} is "
        f"4.0 and 5.0, whose midpoint is {COHORT_WORKLOAD_MEDIAN}. An answer of 4.0 is "
        "`percentile_disc`, which picks an existing row rather than interpolating; SPEC §5.1 asks "
        "for true numeric statistics and §3.2 stores a decimal so this number can be one."
    )


def test_the_rating_view_counts_ratings_rather_than_people(
    benchmark_world: BenchmarkWorld,
) -> None:
    """`rating_count`'s unit, said out loud on the same world.

    The rating pair carries `rating_count` and no respondent figure, and that is
    the ruling's shape rather than an omission: a rating mean is a statistic
    about ratings, and the figure a minimum is applied to lives on the
    workload-and-counts view beside the section count. Asserting the unit here
    keeps the two from drifting into each other — `docs/MISTAKES.md` entry 50 is
    about a number whose unit nobody said, and two numbers called "count" on two
    views of one ticket is where that starts.

    **The mutation it exists to survive**: `rating_count` written as
    `count(DISTINCT <person key>)`, which answers 3 where four ratings were
    submitted, and the mean computed over the deduplicated set with it — which
    would answer 3.67 rather than 4.
    """
    world = a_cohort_one_student_answered_twice(benchmark_world)
    require_benchmark_view(world.session, COHORT_RATING_WEEK_VIEW)

    row = world.cohort_rating_week(
        length_weeks=THE_LENGTH, level=UG, course_week=THE_COURSE_WEEK, stream=INSTRUCTOR_STREAM
    )
    assert row is not None, (
        f"`{COHORT_RATING_WEEK_VIEW}` has no {INSTRUCTOR_STREAM} row for this cohort week, in "
        "which four instructor ratings were submitted. The assertions below would be vacuous."
    )
    assert row["rating_count"] == EXPECTED_RATINGS, (
        f"`rating_count` is {row['rating_count']!r} where four instructor ratings were submitted — "
        "two of them by one student, in two sections of this cohort. A 3 is a distinct count of "
        "people applied to a figure whose unit is ratings; the count of people is "
        f"`respondent_count` on `{COHORT_WEEK_VIEW}`, and it is 3 there for the same reason it is "
        "not 3 here."
    )
    submitted = [
        str(value)
        for value in (
            SHARED_RATING_IN_FIRST,
            SHARED_RATING_IN_SECOND,
            FIRST_ONLY_RATING,
            SECOND_ONLY_RATING,
        )
    ]
    assert row["rating_mean"] == EXPECTED_RATING_MEAN, (
        f"`rating_mean` is {row['rating_mean']!r}; the four submitted instructor ratings "
        f"{submitted} average to {EXPECTED_RATING_MEAN}. A mean of 3.67 is the deduplicated set: "
        "one person's two ratings counted once, which is the respondent figure's rule applied to "
        "an arithmetic mean."
    )
