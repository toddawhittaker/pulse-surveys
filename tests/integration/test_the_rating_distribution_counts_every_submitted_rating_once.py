"""E4-03 criteria 2 and 7 — what the per-stream rating distribution counts.

`report_rating_distribution` returns one row per `(section_id, week_id, stream,
rating)` with the number of submitted ratings of that value. Four things have to
be true of it, and each has a test here:

  - **every submitted rating is counted exactly once** — the ticket's second
    criterion, proven at the boundary it names: a five-response week whose counts
    sum to five, in each stream;
  - **a rating belongs to the section it was submitted in** — the same
    criterion's other half, driven in both directions, because a student enrolled
    in two sections is the case where a missing `section_id` in a `GROUP BY` or a
    join through `user` rather than through `response` shows up;
  - **only ratings are counted** — a comment and a workload figure are answers
    too, and a view that counted `answer` rows rather than rating values would
    put a workload of 6.5 in a Likert distribution;
  - **the stream comes from the question set in force** — the seventh criterion,
    proven with a second planted version whose positions carry the other stream.

**The wrong answer here is invisible**, which is the ticket's first known trap:
a distribution that double-counts, drops a stream or maps a stream by position
renders as a plausible bar chart. So every test below asserts the **whole** set
of rows the view returns for the week rather than looking up the value it expects
— a row the view invented has nowhere to hide in a list comparison — and each
names the mutation it is written to kill.

**The counts are arithmetic this file does by hand over values it supplied.**
Nothing here asks the view what it holds and then checks that against a rule; the
five ratings are written out, and the counts under them are written out
(`docs/MISTAKES.md` entries 19 and 30).
"""

from decimal import Decimal

import pytest
from fixtures.report_views import (
    A_COMMENT,
    COURSE_STREAM,
    DEFAULT_COHORT,
    FIRST_VERSION,
    INSTRUCTOR_STREAM,
    RESPONSE_COUNTS_VIEW,
    SECOND_COHORT,
    SECOND_VERSION,
    SWAPPED_QUESTION_LAYOUT,
    ReportWorld,
)

pytestmark = pytest.mark.integration

# SPEC §3.2's five positions, as this module answers them. Named rather than
# spelled inline so a test reads as the submission it is.
INSTRUCTOR_RATING = 1
INSTRUCTOR_COMMENT = 2
COURSE_RATING = 3
COURSE_COMMENT = 4
WORKLOAD = 5

# Both sections run term week 7 — cohort `F` is six weeks from term week 7 and
# cohort `Q` is twelve from the same week — so the cross-section case differs in
# the section and in nothing else.
SHARED_WEEK = 7
SECOND_WEEK = 8

# The five students' ratings, written out. The instructor stream repeats a value
# and the course stream repeats another: a rating counted with `COUNT(DISTINCT
# rating)` rather than `COUNT(*)` answers 4 and 2 where these answer 5 and 5, and
# a week of five different values could not tell the two apart.
INSTRUCTOR_RATINGS = (Decimal("5"), Decimal("4"), Decimal("4"), Decimal("3"), Decimal("1"))
COURSE_RATINGS = (Decimal("2"), Decimal("2"), Decimal("2"), Decimal("5"), Decimal("5"))

# What those five submissions are, counted by hand.
FIVE_RESPONSES = sorted(
    [
        (INSTRUCTOR_STREAM, Decimal("5"), 1),
        (INSTRUCTOR_STREAM, Decimal("4"), 2),
        (INSTRUCTOR_STREAM, Decimal("3"), 1),
        (INSTRUCTOR_STREAM, Decimal("1"), 1),
        (COURSE_STREAM, Decimal("2"), 3),
        (COURSE_STREAM, Decimal("5"), 2),
    ]
)

# A workload figure no Likert scale can hold, so a row carrying it in a rating
# distribution is unmistakable rather than a plausible 5.
A_WORKLOAD = Decimal("6.5")


def test_a_five_response_week_sums_to_five_in_each_stream(report_world: ReportWorld) -> None:
    """Criterion 2: every submitted rating counted exactly once, at the boundary the ticket names.

    Five students answer both rating questions, and the whole set of rows the view
    returns for that section-week is compared against the six counted by hand.
    The sums are asserted as well as the rows, because "sums to five" is the
    sentence the criterion is written in and a reader of a failure should see
    both.

    **The mutation it exists to survive**: `COUNT(*)` rewritten as
    `COUNT(DISTINCT …)` over the rating, which the repeated 4 and the repeated 2
    turn into 4 and 2; a `GROUP BY` that drops `stream`, which merges the two
    streams into one set of rows; and a join that multiplies a rating by the
    number of answers on its response, which turns every 1 into a 5.
    **The near miss it tolerates**: nothing about which week or section the rows
    belong to — that is the next test's subject, and this one filters to one
    section-week so a leak would show up there rather than here.
    """
    world = report_world.build()
    for index, (instructor, course) in enumerate(
        zip(INSTRUCTOR_RATINGS, COURSE_RATINGS, strict=True)
    ):
        student = world.student(f"e4-03-five-{index}")
        world.respond(
            student,
            term_week=SHARED_WEEK,
            answers={INSTRUCTOR_RATING: instructor, COURSE_RATING: course},
        )

    rows = world.distribution(term_week=SHARED_WEEK)
    assert rows == FIVE_RESPONSES, (
        f"`report_rating_distribution` returned {rows} for the section-week five students answered."
        f" Counted by hand from what they submitted: {FIVE_RESPONSES}. The instructor ratings were "
        f"{[str(value) for value in INSTRUCTOR_RATINGS]} and the course ratings "
        f"{[str(value) for value in COURSE_RATINGS]}."
    )

    for stream in (INSTRUCTOR_STREAM, COURSE_STREAM):
        counted = sum(count for row_stream, _rating, count in rows if row_stream == stream)
        assert counted == len(INSTRUCTOR_RATINGS), (
            f"The {stream} rows sum to {counted} where five students each submitted one "
            f"{stream.lower()} rating. E4-03's second criterion is that the distribution counts "
            "every submitted rating exactly once, and a five-response week whose counts sum to "
            "five is how the ticket asks for it to be proven."
        )


# **This test alone is `invariant`-marked, and the module is not.** The rest of
# this file is arithmetic — that a distribution counts each submitted rating once,
# that an unanswered question contributes nothing — and getting that wrong is a
# wrong number rather than a disclosure. This one is the section boundary: §4.1
# item 6, no view widening what one section's reader may see. A view whose
# `section_id` predicate is dropped or joined loosely reports another section's
# students inside this section's figures, and in a small week a distribution *is*
# an identification channel. Marking the module whole would put four arithmetic
# tests in the isolated pass and dilute what that pass means.
@pytest.mark.invariant
def test_a_rating_is_counted_for_the_section_it_was_submitted_in(
    report_world: ReportWorld,
) -> None:
    """Criterion 2's boundary, driven in both directions.

    One student enrolled in two sections answers the same week in each, with a
    different rating in each. Each section's distribution is asserted whole, so
    the two failures this is about are distinguishable in the message: a rating
    that leaked *into* a section is a surplus row, and one that leaked *out* is a
    missing one.

    **The mutation it exists to survive**: `section_id` dropped from the `GROUP
    BY` (both sections' ratings arrive in one row, and each section's page shows
    the other's students); and a join reaching `answer` through `user` or through
    `enrollment` rather than through `response`, which is the shape that makes a
    student's rating appear wherever they are enrolled.
    **The near miss it tolerates**: the two sections share a term week and a
    student, so nothing here can pass by keying on the week or on the respondent.
    """
    world = report_world.build()
    world.section(SECOND_COHORT)
    student = world.student("e4-03-two-sections", cohorts=(DEFAULT_COHORT, SECOND_COHORT))

    world.respond(
        student,
        term_week=SHARED_WEEK,
        cohort=DEFAULT_COHORT,
        answers={INSTRUCTOR_RATING: Decimal("1"), COURSE_RATING: Decimal("2")},
    )
    world.respond(
        student,
        term_week=SHARED_WEEK,
        cohort=SECOND_COHORT,
        answers={INSTRUCTOR_RATING: Decimal("5"), COURSE_RATING: Decimal("4")},
    )

    here = world.distribution(cohort=DEFAULT_COHORT, term_week=SHARED_WEEK)
    there = world.distribution(cohort=SECOND_COHORT, term_week=SHARED_WEEK)

    assert here == sorted(
        [(INSTRUCTOR_STREAM, Decimal("1"), 1), (COURSE_STREAM, Decimal("2"), 1)]
    ), (
        f"The first section's distribution is {here}. Its one respondent rated the instructor 1 "
        "and the course 2 there, and rated 5 and 4 in the other section they are enrolled in, in "
        "the same term week. Anything else in this list came from the other section."
    )
    assert there == sorted(
        [(INSTRUCTOR_STREAM, Decimal("5"), 1), (COURSE_STREAM, Decimal("4"), 1)]
    ), (
        f"The second section's distribution is {there}. Its one respondent rated the instructor 5 "
        "and the course 4 there, and rated 1 and 2 in the other section, in the same term week."
    )


def test_a_comment_and_a_workload_figure_are_not_ratings(report_world: ReportWorld) -> None:
    """Ratings only: the other two answer shapes appear nowhere in the distribution.

    One student answers all five of SPEC §3.2's questions. The distribution has
    exactly two rows — one rating per stream — and the workload figure, which no
    Likert scale can hold, is absent from it.

    **The mutation it exists to survive**: the filter that keeps the view to
    rating answers deleted, so it counts `answer` rows instead. That view returns
    a row for the workload figure and two rows a comment cannot fill, and a
    reader of the chart sees a distribution with five submissions in a week that
    had one.
    **The near miss it tolerates**: a comment answer whose row carries no rating
    value at all is invisible either way, which is why the workload figure — a
    stored number in a different column — is the one that discriminates.
    """
    world = report_world.build()
    student = world.student("e4-03-whole-submission")
    world.respond(
        student,
        term_week=SHARED_WEEK,
        answers={
            INSTRUCTOR_RATING: Decimal("4"),
            INSTRUCTOR_COMMENT: A_COMMENT,
            COURSE_RATING: Decimal("3"),
            COURSE_COMMENT: A_COMMENT,
            WORKLOAD: A_WORKLOAD,
        },
    )

    rows = world.distribution(term_week=SHARED_WEEK)
    assert rows == sorted(
        [(INSTRUCTOR_STREAM, Decimal("4"), 1), (COURSE_STREAM, Decimal("3"), 1)]
    ), (
        f"`report_rating_distribution` returned {rows} for a week in which one student answered "
        "all five of SPEC §3.2's questions: an instructor rating of 4, a course rating of 3, two "
        f"comments and a workload figure of {A_WORKLOAD}. Only the two ratings are ratings. A row "
        "carrying the workload figure means the view counts answers rather than submitted rating "
        "values."
    )


def test_a_response_that_rated_one_stream_adds_nothing_to_the_other(
    report_world: ReportWorld,
) -> None:
    """An unanswered rating costs the response rate, never the distribution.

    Five students respond; four rate both streams and the fifth rates only the
    instructor. E2-05 refuses an `answer` row holding no value and ADR 0115
    deletes a withdrawn answer's row, so an absent row is this schema's only
    spelling for "that question was not answered" — the state the ticket's third
    criterion describes as costing the response rate rather than the average.

    Both sides are asserted together, which is what makes it a boundary rather
    than a single reading: the instructor stream counts five ratings, the course
    stream counts four, and `report_response_counts` still counts five responses
    for the same week.

    **The mutation it exists to survive**: a view that counts *responses* per
    stream rather than submitted ratings — which would answer five for the course
    stream and put a submission in a distribution nobody added to it.
    """
    world = report_world.build()
    for index in range(4):
        student = world.student(f"e4-03-both-streams-{index}")
        world.respond(
            student,
            term_week=SHARED_WEEK,
            answers={INSTRUCTOR_RATING: Decimal("4"), COURSE_RATING: Decimal("4")},
        )
    silent = world.student("e4-03-instructor-only")
    world.respond(silent, term_week=SHARED_WEEK, answers={INSTRUCTOR_RATING: Decimal("4")})

    rows = world.distribution(term_week=SHARED_WEEK)
    assert rows == sorted(
        [(INSTRUCTOR_STREAM, Decimal("4"), 5), (COURSE_STREAM, Decimal("4"), 4)]
    ), (
        f"`report_rating_distribution` returned {rows}. Five students submitted in this week; all "
        "five rated the instructor 4 and four of them rated the course 4. The fifth answered no "
        "course rating at all, which is an absent `answer` row rather than a null one, and it "
        "contributes nothing to the course stream."
    )

    counts = world.counts(term_week=SHARED_WEEK)
    assert counts is not None and counts["responses"] == 5, (
        f"`{RESPONSE_COUNTS_VIEW}` says {counts} for the same week. Five students submitted, and "
        "the one who left a rating unanswered still submitted a response — SPEC §3.3's rule is "
        "that an unanswered optional question costs its item, not its response. This is the other "
        "half of the boundary above: the missing rating leaves the distribution alone and is still "
        "counted here."
    )


def test_the_stream_of_a_rating_comes_from_the_question_set_and_not_from_its_position(
    report_world: ReportWorld,
) -> None:
    """Criterion 7, with the control that makes it a proof rather than a coincidence.

    Two question-set versions are planted over one section. In the first, SPEC
    §3.2's own order, position 1 is the instructor rating and position 3 the
    course rating; in the second the two streams are exchanged. One week is
    answered through each, with the same two values in the same two positions —
    1 at position 1 and 5 at position 3.

    So the two weeks differ in the question set and in nothing else, and a view
    that read a stream off the position answers them identically. The correct
    answer is that they are mirror images.

    **The mutation it exists to survive**: `question.stream` replaced by a `CASE`
    over `question.position`, which is exactly the hard-coding the ticket's
    Context forbids ("the mapping derives from the question rows in force for the
    week, never from a hard-coded position"); and the two stream values exchanged
    in the view's SQL, which the mirrored pair also catches, in both weeks at
    once.
    **The near miss it tolerates**: nothing about which version is "current" —
    the view is asked about a week, and each week's answers name their own
    questions.
    """
    world = report_world.build()
    world.plant_question_set(version=SECOND_VERSION, layout=SWAPPED_QUESTION_LAYOUT)

    through_spec_order = world.student("e4-03-set-v1")
    world.respond(
        through_spec_order,
        term_week=SHARED_WEEK,
        version=FIRST_VERSION,
        answers={INSTRUCTOR_RATING: Decimal("1"), COURSE_RATING: Decimal("5")},
    )
    through_swapped_order = world.student("e4-03-set-v2")
    world.respond(
        through_swapped_order,
        term_week=SECOND_WEEK,
        version=SECOND_VERSION,
        answers={INSTRUCTOR_RATING: Decimal("1"), COURSE_RATING: Decimal("5")},
    )

    first = world.distribution(term_week=SHARED_WEEK)
    second = world.distribution(term_week=SECOND_WEEK)

    assert first == sorted(
        [(INSTRUCTOR_STREAM, Decimal("1"), 1), (COURSE_STREAM, Decimal("5"), 1)]
    ), (
        f"The week answered through SPEC §3.2's own question order gives {first}. Position 1 is "
        "the instructor rating there and was answered 1; position 3 is the course rating and was "
        "answered 5. This is the control: if it is wrong, the mirrored week below proves nothing."
    )
    assert second == sorted(
        [(INSTRUCTOR_STREAM, Decimal("5"), 1), (COURSE_STREAM, Decimal("1"), 1)]
    ), (
        f"The week answered through the planted second question-set version gives {second}. In "
        "that version position 1 carries the **course** stream and position 3 the **instructor** "
        "stream, and the student answered 1 at position 1 and 5 at position 3 — the same two "
        "values, in the same two positions, as the control week above. So the instructor stream "
        "holds the 5 here and the 1 there.\n\n"
        "Getting this the same way round as the control week is a view mapping a rating to a "
        "stream by its position rather than by `question.stream`. E4-03's seventh criterion and "
        "the ticket's Context both refuse that: the question set is versioned, so a position is "
        "not a stream."
    )
