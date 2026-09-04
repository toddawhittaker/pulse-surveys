"""Properties of the participation formula over generated enrollments — ticket E3-03.

SPEC §9.1: "Grade math: property-based tests (Hypothesis) for the participation
formula across adds, drops, missed weeks, and partially answered weeks — the
fourth case arriving with the item-based formula of §3.4, where a week can
contribute a fraction rather than a one or a zero."

Three properties, none of which recomputes the formula. A property that
re-derived the expected percentage would be a second implementation for the code
to agree with (`docs/MISTAKES.md` entry 19), and it would agree with any mistake
both copies made. What is asserted instead are relations that have to hold
whatever the arithmetic is:

  - the ledger and the three numbers beside it are the same arithmetic — the
    lines sum to the numerator and to the denominator, and they run up the course
    weeks from the student's first enrolled week;
  - the denominator is a fact about the enrollment and not about the submission —
    two students enrolled identically have the same total and the same per-week
    `of Y`, however differently they answered;
  - a drop changes nothing at all.

**The generator provably includes the four cases §9.1 names** (`docs/MISTAKES.md`
entry 15). They are drawn from explicitly, as `NAMED_SHAPES`, alongside the
generated space — and `test_the_named_shapes_cover_every_case_spec_9_1_names`
asserts each case is present rather than leaving it to be believed. That control
also runs the classifier against a shape carrying none of the four, so a
classifier that answered "yes" to everything would be caught rather than read as
coverage.

**What this space does not reach**, stated rather than left as a claim of
totality: sections other than the six-week cohort `F`, question sets other than
SPEC §3.2's five, tier-3 dating (the sync-dated add, which
`test_the_first_enrolled_week_follows_the_three_tiers.py` drives from both sides
of its boundary), and clocks other than a minute past course week 4's close. The
world is built once and every generated example enrols new students into it, so
one section accumulates students across examples — which is realistic and is what
keeps a property affordable against a real database.
"""

import re
from datetime import date
from typing import Any, NamedTuple
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fixtures.grading import (
    A_MOMENT,
    INSUFFICIENT,
    GradingWorld,
    Student,
    ledger_line,
)
from fixtures.survey_windows import INSTITUTION_TIMEZONE
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

pytestmark = [pytest.mark.integration, pytest.mark.slow]

# Four of the six-week section's weeks have closed, and SPEC §3.2's set carries
# five questions. Both are fixed here so the generated space is about enrollment
# shape, which is what §9.1 names.
ELAPSED_WEEKS = 4
POSITIONS = (1, 2, 3, 4, 5)

DATABASE_BACKED = settings(
    max_examples=15,
    deadline=None,
    # Every example shares one world, one section and one transaction: students
    # accumulate, which is the state a real section is in and is what makes a
    # database-backed property affordable at all.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

# One ledger line, read strictly. Anchored at both ends so a line carrying
# anything besides the four fixed words and three numbers fails to parse rather
# than being partially matched.
LEDGER_LINE_PATTERN = re.compile(r"^Week (\d+): (\d+) of (\d+) items$")

# §9.1's four names, as this module's classifier reports them.
AN_ADD = "an add"
A_DROP = "a drop"
A_MISSED_WEEK = "a missed week"
A_PARTIALLY_ANSWERED_WEEK = "a partially answered week"
THE_FOUR_CASES = (AN_ADD, A_DROP, A_MISSED_WEEK, A_PARTIALLY_ANSWERED_WEEK)


class Shape(NamedTuple):
    """One generated enrollment: when it starts, what was answered, what was refused, when it ends.

    `answered[i]` is the positions submitted in course week `i + 1`. A week before
    `first_week` is never answered — the student was not there — and an empty tuple
    from `first_week` on is a missed week.
    """

    first_week: int
    answered: tuple[tuple[int, ...], ...]
    refused_weeks: tuple[int, ...]
    dropped_after: int | None


def shape(
    first_week: int,
    answered: list[list[int]],
    refused_weeks: list[int],
    dropped_after: int | None,
) -> Shape:
    """A `Shape` from the lists Hypothesis draws, normalised to tuples."""
    return Shape(
        first_week=first_week,
        answered=tuple(tuple(sorted(set(week))) for week in answered),
        refused_weeks=tuple(sorted(set(refused_weeks))),
        dropped_after=dropped_after,
    )


def features_of(drawn: Shape) -> set[str]:
    """Which of §9.1's four cases one shape exhibits.

    Read over the weeks the student was actually enrolled for, because a week
    before their first is not a week they missed — it is a week that is not
    theirs, and counting it as a missed week would report coverage this space does
    not have.
    """
    found: set[str] = set()
    if drawn.first_week > 1:
        found.add(AN_ADD)
    if drawn.dropped_after is not None:
        found.add(A_DROP)
    for week, positions in enumerate(drawn.answered, start=1):
        if week < drawn.first_week:
            continue
        if not positions:
            found.add(A_MISSED_WEEK)
        elif len(positions) < len(POSITIONS):
            found.add(A_PARTIALLY_ANSWERED_WEEK)
    return found


# The shapes drawn from explicitly, so the four cases §9.1 names are in the space
# by construction rather than by luck (`docs/MISTAKES.md` entry 15). The first
# carries none of the four and is the control the classifier has to report empty.
EVERY_WEEK_IN_FULL = shape(1, [list(POSITIONS)] * ELAPSED_WEEKS, [], None)
A_LATE_ADD = shape(3, [[], [], list(POSITIONS), list(POSITIONS)], [], None)
A_STUDENT_WHO_LEFT = shape(1, [list(POSITIONS)] * ELAPSED_WEEKS, [], 2)
A_WEEK_NOBODY_ANSWERED = shape(1, [list(POSITIONS), [], list(POSITIONS), []], [], None)
A_WEEK_ANSWERED_IN_PART = shape(1, [[1, 3, 5], list(POSITIONS), [1], [2, 4]], [], None)
A_REFUSED_COMMENT = shape(1, [list(POSITIONS)] * ELAPSED_WEEKS, [1, 3], None)
A_LATE_ADD_WHO_LEFT_HAVING_ANSWERED_HALF = shape(2, [[], [1, 2], [], [3, 4, 5]], [2], 3)

NAMED_SHAPES = (
    EVERY_WEEK_IN_FULL,
    A_LATE_ADD,
    A_STUDENT_WHO_LEFT,
    A_WEEK_NOBODY_ANSWERED,
    A_WEEK_ANSWERED_IN_PART,
    A_REFUSED_COMMENT,
    A_LATE_ADD_WHO_LEFT_HAVING_ANSWERED_HALF,
)


def enrollment_shapes() -> st.SearchStrategy[Shape]:
    """The named shapes and a generated space, as one strategy.

    The generated half is what finds the case nobody thought of; the named half is
    what stops the property from claiming a case its own bounds exclude.
    """
    generated = st.builds(
        shape,
        first_week=st.integers(min_value=1, max_value=ELAPSED_WEEKS),
        answered=st.lists(
            st.lists(st.sampled_from(POSITIONS), unique=True, max_size=len(POSITIONS)),
            min_size=ELAPSED_WEEKS,
            max_size=ELAPSED_WEEKS,
        ),
        refused_weeks=st.lists(
            st.integers(min_value=1, max_value=ELAPSED_WEEKS), unique=True, max_size=ELAPSED_WEEKS
        ),
        dropped_after=st.one_of(st.none(), st.integers(min_value=1, max_value=ELAPSED_WEEKS)),
    )
    return st.one_of(st.sampled_from(NAMED_SHAPES), generated)


def parse_ledger(ledger: str) -> list[tuple[int, int, int]]:
    """Every ledger line as `(course week, completed, total)`, or a failure naming the line.

    Strict, and it fails rather than skipping: a line this cannot read is a ledger
    in a form SPEC §3.4 does not describe, and quietly dropping it would let a
    malformed ledger satisfy a property about the lines that parsed.
    """
    parsed: list[tuple[int, int, int]] = []
    for line in ledger.split("\n"):
        matched = LEDGER_LINE_PATTERN.match(line)
        if matched is None:
            pytest.fail(
                f"The ledger line {line!r} is not of SPEC §3.4's form `Week 1: 4 of 5 items`. The "
                f"whole ledger was:\n{ledger}"
            )
        parsed.append((int(matched.group(1)), int(matched.group(2)), int(matched.group(3))))
    return parsed


def enrol(world: GradingWorld, drawn: Shape, *, drop: bool = True) -> Student:
    """One student enrolled and answering as `drawn` says, with a subject nobody else has.

    A first week later than one is expressed as a platform-dated add, a microsecond
    before that week's window closes — §3.4's tier 1, which is the one tier whose
    input is an instant the test can place exactly.
    """
    student = world.student(
        f"e3-03-property-{uuid4().hex[:12]}",
        lms_window_start=(
            None if drawn.first_week == 1 else world.closes_at(drawn.first_week) - A_MOMENT
        ),
    )
    for week, positions in enumerate(drawn.answered, start=1):
        if week < drawn.first_week or not positions:
            continue
        verdicts = (
            {
                position: INSUFFICIENT
                for position in positions
                if world.shape_of[position] == "comment"
            }
            if week in drawn.refused_weeks
            else {}
        )
        world.answer_week(student, week, positions=positions, verdicts=verdicts)
    if drop and drawn.dropped_after is not None:
        world.drop(student, ended_on=local_day_of_close(world, drawn.dropped_after))
    return student


def local_day_of_close(world: GradingWorld, course_week: int) -> date:
    """The institution-timezone day one course week's window closes on, for a drop date."""
    return world.closes_at(course_week).astimezone(ZoneInfo(INSTITUTION_TIMEZONE)).date()


def built(world: GradingWorld, clock_overrides: Any) -> GradingWorld:
    """The one section every example enrols into, built on the first example only."""
    if world.section is None:
        world.build()
        world.elapsed_through(clock_overrides, ELAPSED_WEEKS)
    return world


def test_the_named_shapes_cover_every_case_spec_9_1_names() -> None:
    """`docs/MISTAKES.md` entry 15: the generator provably includes the cases it names.

    A property whose strategy cannot produce its own named case is the defect that
    entry is about, and the four cases here — adds, drops, missed weeks, partially
    answered weeks — are exactly the ones a bounded strategy drops. This asserts
    they are in the explicitly drawn half of the space, so no number of examples is
    needed for them to appear.

    **The classifier is run in both directions** (`docs/MISTAKES.md` entry 3): a
    shape carrying none of the four has to report none, or a classifier that
    answered "yes" to everything would report full coverage of a space it never
    examined.
    """
    covered: set[str] = set()
    for drawn in NAMED_SHAPES:
        covered |= features_of(drawn)

    assert covered == set(THE_FOUR_CASES), (
        f"The explicitly drawn shapes exhibit {sorted(covered)}, and §9.1 names "
        f"{sorted(THE_FOUR_CASES)}. A case missing here is a case the properties below claim and "
        "cannot reach."
    )
    assert features_of(EVERY_WEEK_IN_FULL) == set(), (
        f"A day-one student who answered every item of every week is reported as exhibiting "
        f"{sorted(features_of(EVERY_WEEK_IN_FULL))}. The classifier that decides coverage above "
        "has to be able to say no."
    )
    assert features_of(A_LATE_ADD_WHO_LEFT_HAVING_ANSWERED_HALF) == set(THE_FOUR_CASES), (
        "The shape written to carry all four cases at once exhibits "
        f"{sorted(features_of(A_LATE_ADD_WHO_LEFT_HAVING_ANSWERED_HALF))}."
    )


def test_the_ledger_reader_reads_the_line_the_spec_writes() -> None:
    """The parser the property below depends on, run against what it claims to read.

    Not a test of the ticket. `docs/MISTAKES.md` entry 3's rule for anything that
    parses text: run it against the text you claim it catches and the text you
    claim it refuses. A parser that quietly matched a substring would let a
    malformed ledger through, and the property that rests on it would be green.
    """
    assert parse_ledger(ledger_line(3, 4, 5)) == [(3, 4, 5)]
    assert parse_ledger("\n".join([ledger_line(1, 0, 5), ledger_line(2, 5, 5)])) == [
        (1, 0, 5),
        (2, 5, 5),
    ]
    assert LEDGER_LINE_PATTERN.match("Week 1: 4 of 5 items and a footnote") is None
    assert LEDGER_LINE_PATTERN.match("week 1: 4 of 5 items") is None
    assert LEDGER_LINE_PATTERN.match("Week 1: 4 of 5") is None


@DATABASE_BACKED
@given(drawn=enrollment_shapes())
def test_the_ledger_is_the_same_arithmetic_as_the_three_numbers_beside_it(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any, drawn: Shape
) -> None:
    """For any generated enrollment: the lines sum to the score and run up the course weeks.

    **The mutations this kills:** a ledger rendered from a different pass over the
    weeks than the numerator and denominator were — the two are separate loops and
    a filter added to one and not the other is invisible to any single-case test;
    a ledger in insertion or reverse order; and a ledger that starts before the
    student's first enrolled week, which SPEC §3.4 says appears nowhere.

    The first line's week is asserted against the shape's own first week, which is
    an *input* this test supplied rather than a recomputation of the tier rule.
    """
    world = built(grading_world, clock_overrides)
    student = enrol(world, drawn)

    score = world.score_for(student, settings=window_settings)
    lines = parse_ledger(score.ledger)

    assert lines, (
        f"The ledger is empty for a student credited with {score.completed} of {score.total}. Every "
        "student in the mapping has at least one elapsed enrolled week, and every elapsed week is "
        "a line."
    )
    weeks = [week for week, _completed, _total in lines]
    assert weeks == sorted(set(weeks)), (
        f"The ledger names weeks {weeks}, which is not strictly ascending. SPEC §3.4: one line per "
        "elapsed week, in course-week order."
    )
    assert weeks[0] == drawn.first_week, (
        f"The ledger begins at course week {weeks[0]} for a student enrolled from course week "
        f"{drawn.first_week}. Weeks before the first enrolled week appear nowhere."
    )
    assert weeks[-1] == ELAPSED_WEEKS, (
        f"The ledger ends at course week {weeks[-1]}, and {ELAPSED_WEEKS} weeks of this section "
        "have closed. An elapsed week is never omitted."
    )
    assert sum(completed for _week, completed, _total in lines) == score.completed, (
        f"The ledger's completed items sum to "
        f"{sum(completed for _week, completed, _total in lines)} and the score says "
        f"{score.completed}:\n{score.ledger}"
    )
    assert sum(total for _week, _completed, total in lines) == score.total, (
        f"The ledger's totals sum to {sum(total for _week, _completed, total in lines)} and the "
        f"score's denominator is {score.total}:\n{score.ledger}"
    )
    assert (
        0 <= score.completed <= score.total
    ), f"The score is {score.completed} of {score.total}, which is not a fraction of a whole."


@DATABASE_BACKED
@given(drawn=enrollment_shapes())
def test_the_denominator_is_decided_by_the_enrollment_and_not_by_the_submission(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any, drawn: Shape
) -> None:
    """Two students enrolled identically have the same denominator, whatever either answered.

    One answers as the shape says — missed weeks, partial weeks, refused comments
    and all — and the other answers nothing at all. SPEC §3.4 makes the denominator
    a fact about the weeks a student could have answered, so the two have to agree
    line for line on the `of Y` and on which weeks appear.

    **The mutations this kills:** a denominator counted from the `answer` rows
    found, from the responses submitted, or from the classifications present. Each
    is right for a student who answered everything and wrong for everyone else,
    and this property covers everyone else by construction.
    """
    world = built(grading_world, clock_overrides)
    answering = enrol(world, drawn)
    silent = enrol(world, drawn._replace(answered=((),) * ELAPSED_WEEKS))

    answered_score = world.score_for(answering, settings=window_settings)
    silent_score = world.score_for(silent, settings=window_settings)

    assert answered_score.total == silent_score.total, (
        f"A student who answered {drawn.answered} has a denominator of {answered_score.total} and "
        f"a classmate enrolled identically who answered nothing has {silent_score.total}."
    )
    assert (
        silent_score.completed == 0
    ), f"The student who answered nothing is credited with {silent_score.completed} items."
    answered_weeks = [
        (week, total) for week, _completed, total in parse_ledger(answered_score.ledger)
    ]
    silent_weeks = [(week, total) for week, _completed, total in parse_ledger(silent_score.ledger)]
    assert answered_weeks == silent_weeks, (
        f"The two ledgers name different weeks or different per-week totals: {answered_weeks} "
        f"against {silent_weeks}. What was submitted decides the left-hand number of a line and "
        "never the right-hand one."
    )


@DATABASE_BACKED
@given(drawn=enrollment_shapes(), drop_after=st.integers(min_value=1, max_value=ELAPSED_WEEKS))
def test_a_drop_leaves_the_whole_score_unchanged_for_any_generated_enrollment(
    grading_world: GradingWorld,
    clock_overrides: Any,
    window_settings: Any,
    drawn: Shape,
    drop_after: int,
) -> None:
    """The same enrollment and the same answers, scored with and without an `ended_on`.

    §3.4's "scores stop updating" is a rule about posting and E3-06 owns it; this
    module computes the same thing either way. The drop week is generated
    separately from the shape so that every example has one, rather than the
    property being about whichever examples happened to draw a drop.

    **The mutation this kills:** `ended_on` read anywhere in the computation — as a
    truncation of the elapsed weeks, as a filter on the answers, or as a reason to
    leave the student out of the mapping altogether.
    """
    world = built(grading_world, clock_overrides)
    still_here = enrol(world, drawn._replace(dropped_after=None))
    gone = enrol(world, drawn._replace(dropped_after=None))
    world.drop(gone, ended_on=local_day_of_close(world, drop_after))

    assert world.score_for(gone, settings=window_settings) == world.score_for(
        still_here, settings=window_settings
    ), (
        f"A student who dropped after course week {drop_after} scored differently from a classmate "
        "enrolled and answering identically who did not."
    )
