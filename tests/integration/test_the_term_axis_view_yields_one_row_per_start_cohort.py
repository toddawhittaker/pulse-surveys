"""E5-03 criterion 6 — §2.2's term axis, one line per start cohort.

"The term-axis view yields one row per start cohort per term week, and a cohort
with no data yields no fabricated zeros."

SPEC §2.2, the two-axes bullet, whole:

> **Two week axes.** Course-level pages (instructor report, student results)
> plot **course week** ("WK 01…") with a quiet term-week sub-label ("TERM 04…")
> from the section's start offset. Aggregate pages plot the **term axis** (TERM
> 01-18) with one line per start cohort and a cohort selector (e.g., "U sections
> · started 8/17") — averaging week-3-of-course across cohorts that began five
> weeks apart would be meaningless.

The course-week views are that sentence's first half; these two are its second.
The cohort is identified by its **start date** rather than by its letter, which
the ruling settles and the breakdown's decision 7 explains: a start letter is
per-term admin data (§2.2's map is "admin-configured data" seeded per term), so
a key on the letter would compare two different cohorts across two terms
whenever an administrator reused it. A date is the same cohort in any term that
has one.

**Nothing in E5 renders these rows** (decision 7: "proven by test, rendered by
E9, nothing in E5 draws it"). That is exactly why they are asserted here rather
than left for the epic that draws them: a read nobody has exercised is a read
that gets built inside a ⚠ epic under time pressure.
"""

from datetime import date
from decimal import Decimal

import pytest
from fixtures.benchmark_views import (
    COHORT_RATING_TERM_AXIS_VIEW,
    COHORT_TERM_AXIS_VIEW,
    COURSE_STREAM,
    INSTRUCTOR_STREAM,
    TERM_AXIS_VIEWS,
    UG,
    BenchmarkWorld,
    require_benchmark_view,
)

pytestmark = pytest.mark.integration

TWELVE_WEEKS = 12

# §2.2's Fall 2026 seed: "12-week U/R/Q starting 8/17, 9/7, 9/28". Written out
# because these dates are what the assertions claim, and the transcription in
# `tests/fixtures/survey_windows.py` is what the calendar control checks.
EARLY_COHORT = "U"
EARLY_START = date(2026, 8, 17)
LATE_COHORT = "R"
LATE_START = date(2026, 9, 7)

# Term week 5 is where the two cohorts meet on this axis and part on the other:
# it is the early cohort's fifth course week and the late cohort's second.
THE_TERM_WEEK = 5
AN_UNANSWERED_TERM_WEEK = 6

# One figure per section. Two sections of the early cohort so the "one row per
# cohort" half has something to fold correctly, and one of the late cohort so
# the "not one row for both cohorts" half has something to keep apart.
EARLY_FIRST_HOURS = Decimal("2.0")
EARLY_SECOND_HOURS = Decimal("4.0")
LATE_HOURS = Decimal("9.0")

EARLY_MEAN = Decimal("3.0")
LATE_MEAN = Decimal("9.0")
MEAN_IF_THE_COHORTS_ARE_FOLDED = Decimal("5.0")

# The ratings, for the rating half of the axis. Each cohort answers both streams
# with a value of its own, so a view that dropped `stream` from the key averages
# a section's instructor rating against its course rating.
EARLY_INSTRUCTOR_RATING = Decimal("2")
EARLY_COURSE_RATING = Decimal("4")
MEAN_IF_THE_STREAMS_ARE_FOLDED = Decimal("3")


def two_start_cohorts_at_one_term_week(world: BenchmarkWorld) -> BenchmarkWorld:
    """Two 8/17 sections and one 9/7 section, all answering in term week 5."""
    world.build()
    world.plant_section("early-first", cohort=EARLY_COHORT, level=UG)
    world.plant_section("early-second", cohort=EARLY_COHORT, level=UG)
    world.plant_section("late", cohort=LATE_COHORT, level=UG)

    # Term week 5 is course week 5 for the 8/17 cohort and course week 2 for the
    # 9/7 one; `respond` takes the course week, so the term week the three rows
    # share is stated here through two different course weeks on purpose.
    world.respond(
        "early-first",
        course_week=5,
        subject="e5-03-axis-early-first",
        workload=EARLY_FIRST_HOURS,
        instructor_rating=EARLY_INSTRUCTOR_RATING,
        course_rating=EARLY_COURSE_RATING,
    )
    world.respond(
        "early-second",
        course_week=5,
        subject="e5-03-axis-early-second",
        workload=EARLY_SECOND_HOURS,
        instructor_rating=EARLY_INSTRUCTOR_RATING,
        course_rating=EARLY_COURSE_RATING,
    )
    world.respond(
        "late",
        course_week=2,
        subject="e5-03-axis-late",
        workload=LATE_HOURS,
        instructor_rating=EARLY_INSTRUCTOR_RATING,
        course_rating=EARLY_COURSE_RATING,
    )
    return world


def test_two_start_cohorts_at_one_term_week_are_two_rows(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 6's first half: one row per start cohort, keyed by its start date.

    Three sections answer in term week 5. Two of them started 8/17 and one
    started 9/7, so the axis carries two lines at that week — §2.2's "one line
    per start cohort" — and the 9/7 line is the section that is two weeks into
    its course while the others are five.

    **Both rows are asserted, not just the count.** "Two rows" is satisfied by a
    view keyed on the section id that happened to produce two of three, so each
    row's own section count and mean are checked: the early line is two sections
    averaging 3.0 and the late line is one section at 9.0.

    **The mutation it exists to survive**: `section_start_date` dropped from the
    key, which produces one row at 5.0 — the figure §2.2 calls meaningless in as
    many words. A key on the start *letter* instead of the date is the same
    mutation in the shape the breakdown warns about: it passes here and fails
    the moment two terms are in the world, because the letter map is
    per-term admin data.
    """
    world = two_start_cohorts_at_one_term_week(benchmark_world)

    early = world.term_axis(
        length_weeks=TWELVE_WEEKS,
        level=UG,
        term_week=THE_TERM_WEEK,
        section_start_date=EARLY_START,
    )
    assert early is not None, (
        f"`{COHORT_TERM_AXIS_VIEW}` has no row at term week {THE_TERM_WEEK} for the cohort that "
        f"started {EARLY_START}, in which two sections answered. §2.2 puts one line per start "
        "cohort on the aggregate axis, and an absent row makes everything below vacuous."
    )
    assert early["section_count"] == 2 and early["workload_mean"] == EARLY_MEAN, (
        f"The {EARLY_START} line at term week {THE_TERM_WEEK} is {early}. Its two sections "
        f"submitted {EARLY_FIRST_HOURS} and {EARLY_SECOND_HOURS} hours, a mean of {EARLY_MEAN}. A "
        f"mean of {MEAN_IF_THE_COHORTS_ARE_FOLDED} is the {LATE_START} cohort folded in, and a "
        "section count of 3 says the same thing in the other currency."
    )

    late = world.term_axis(
        length_weeks=TWELVE_WEEKS,
        level=UG,
        term_week=THE_TERM_WEEK,
        section_start_date=LATE_START,
    )
    assert late is not None, (
        f"`{COHORT_TERM_AXIS_VIEW}` has no row at term week {THE_TERM_WEEK} for the cohort that "
        f"started {LATE_START}, whose one section answered its second course week — the same "
        "calendar week the other two answered their fifth. That is the second line §2.2's cohort "
        "selector selects between; without it the axis has one line and the sentence has no "
        "subject."
    )
    assert late["section_count"] == 1 and late["workload_mean"] == LATE_MEAN, (
        f"The {LATE_START} line at term week {THE_TERM_WEEK} is {late}; its one section submitted "
        f"{LATE_HOURS} hours."
    )


def test_two_sections_of_one_start_cohort_are_one_row(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The other side of the same key: a cohort is a line, not a section.

    The two 8/17 sections are one row, which is what "one line per start cohort"
    means and what makes the axis an aggregate rather than a per-section chart.
    Without this, the test above is satisfied by a view keyed on the section id,
    which produces a row per section — three lines where §2.2 asks for two, each
    of them a single section's figures, and §4.1 item 7's minimum applied to
    rows that are already about one section.

    **The mutation it exists to survive**: `section_id` left in the term-axis
    view's `GROUP BY` — the shape that arrives when the view is written by
    copying the per-section report view and widening its key.
    """
    world = two_start_cohorts_at_one_term_week(benchmark_world)
    require_benchmark_view(world.session, COHORT_TERM_AXIS_VIEW)

    rows = world.rows(
        COHORT_TERM_AXIS_VIEW,
        length_weeks=TWELVE_WEEKS,
        level=UG,
        term_id=world.term_id(),
        term_week=THE_TERM_WEEK,
        section_start_date=EARLY_START,
    )
    assert len(rows) == 1, (
        f"`{COHORT_TERM_AXIS_VIEW}` returns {len(rows)} rows for one start cohort at one term "
        f"week: {rows}. Two sections of the {EARLY_START} cohort answered term week "
        f"{THE_TERM_WEEK}, and §2.2 draws them as one line. A row per section is the per-section "
        "view widened rather than an aggregate."
    )
    assert rows[0]["respondent_count"] == 2, (
        f"The {EARLY_START} line's `respondent_count` is {rows[0]['respondent_count']!r}; two "
        "students answered, one in each of the cohort's two sections."
    )


@pytest.mark.parametrize("view", sorted(TERM_AXIS_VIEWS), ids=sorted(TERM_AXIS_VIEWS))
def test_the_term_axis_fabricates_no_row_for_a_week_nobody_answered(
    benchmark_world: BenchmarkWorld, view: str
) -> None:
    """Criterion 6's second half: "a cohort with no data yields no fabricated zeros".

    Term week 6 is a week both cohorts run and neither answered. It has no row —
    not a zero mean, not a null one, not a respondent count of nought.

    **The answered week is asserted first**, in the same test, because "no row
    for term week 6" is equally true of a view that returns nothing at all
    (`docs/MISTAKES.md` entry 3).

    **The mutation it exists to survive**: a `LEFT JOIN` from `week`, or a cross
    join of the term's weeks against the start-letter map, which emits a row per
    cohort per term week whether or not anybody answered. On this axis that
    shape is especially tempting, because a chart wants eighteen points per line
    — and it is E9's job to draw the gap, not this view's job to invent a zero.
    A fabricated row also carries a respondent count of nought into E5-04, where
    it fails the minimum and reports a suppression for a cohort that has no data
    rather than no permission.
    """
    world = two_start_cohorts_at_one_term_week(benchmark_world)

    answered = world.rows(
        view,
        length_weeks=TWELVE_WEEKS,
        level=UG,
        term_id=world.term_id(),
        term_week=THE_TERM_WEEK,
        section_start_date=EARLY_START,
    )
    assert answered, (
        f"`public.{view}` has no row at term week {THE_TERM_WEEK} for the {EARLY_START} cohort, "
        "which two sections answered. The absence asserted below would be true of a view that "
        "returns nothing at all."
    )

    empty = world.rows(
        view,
        length_weeks=TWELVE_WEEKS,
        level=UG,
        term_id=world.term_id(),
        term_week=AN_UNANSWERED_TERM_WEEK,
        section_start_date=EARLY_START,
    )
    assert empty == [], (
        f"`public.{view}` returns {empty} at term week {AN_UNANSWERED_TERM_WEEK}, which both "
        "cohorts run and neither answered. These views return what was answered; a zero-filled "
        "week is E9's to draw as a gap and E5-04's to tell apart from a suppression, and neither "
        "can do it once the view has invented the row."
    )


def test_the_term_axis_rating_view_keys_by_stream_as_well_as_by_cohort(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The rating half of the axis: `stream` is a key column here too.

    Every section in this world rated the instructor 2 and the course 4, so the
    two streams are two rows with two means. A view that dropped `stream` from
    its key averages the two into 3 — a number that is about neither question,
    on the axis a dean reads.

    SPEC §5.1 puts the two streams in separate panels ("instructor stream above,
    course stream below"), and E4-02's `question.stream` is the column that says
    which is which. The ruling gives both rating views a `stream` key for that
    reason.

    **The mutation it exists to survive**: `stream` dropped from the term-axis
    rating view's key while the course-week one keeps it — the closed-set defeat
    (`docs/MISTAKES.md` entry 53's class) applied to a pair of views built from
    one template, where fixing the half somebody tested leaves the other half
    wrong.
    """
    world = two_start_cohorts_at_one_term_week(benchmark_world)
    require_benchmark_view(world.session, COHORT_RATING_TERM_AXIS_VIEW)

    rows = world.rows(
        COHORT_RATING_TERM_AXIS_VIEW,
        length_weeks=TWELVE_WEEKS,
        level=UG,
        term_id=world.term_id(),
        term_week=THE_TERM_WEEK,
        section_start_date=EARLY_START,
    )
    by_stream = {str(row["stream"]): row for row in rows}
    assert sorted(by_stream) == sorted((INSTRUCTOR_STREAM, COURSE_STREAM)), (
        f"The {EARLY_START} cohort's rating rows at term week {THE_TERM_WEEK} carry the streams "
        f"{sorted(by_stream)}; SPEC §3.2 has two, and the ruling makes `stream` a key column on "
        f"this view. The rows are {rows}. One row means the streams were folded together; none "
        "means the view has no rows here at all, which the workload tests in this module diagnose."
    )
    assert by_stream[INSTRUCTOR_STREAM]["rating_mean"] == EARLY_INSTRUCTOR_RATING, (
        f"The instructor line's `rating_mean` is "
        f"{by_stream[INSTRUCTOR_STREAM]['rating_mean']!r}; both sections of this cohort rated the "
        f"instructor {EARLY_INSTRUCTOR_RATING}. A mean of {MEAN_IF_THE_STREAMS_ARE_FOLDED} is the "
        "course ratings averaged in with them."
    )
    assert by_stream[COURSE_STREAM]["rating_mean"] == EARLY_COURSE_RATING, (
        f"The course line's `rating_mean` is {by_stream[COURSE_STREAM]['rating_mean']!r}; both "
        f"sections rated the course {EARLY_COURSE_RATING}."
    )
