"""The E3-03 fixtures really seed what the participation tests believe — ticket E3-03.

Every module in this ticket rests on three claims made by
`tests/fixtures/grading.py`: that the seeded section's windows are the instants
SPEC §3.1's rhythm produces, that the development clock lands on the side of a
window's close the helper was asked for, and that a comment answer carries the
verdict the test named. None of those is E3-03's subject, and all three are
assumed by every assertion that is.

**These tests must be green on a tree where `app.services.grading` does not
exist.** Nothing here imports it. A red in this module means the machinery is
broken and every other E3-03 module is measuring the wrong thing — not that the
formula is wrong. That is the same job
`test_the_submit_test_machinery_stands_up_what_it_claims.py` does for E2-08, and
it is `docs/MISTAKES.md` entry 3's rule applied to a fixture: a suite that never
checks its own instrument cannot tell a passing subject from a blind test.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fixtures.grading import (
    A_MINUTE,
    CLASSIFICATION_VERDICT_COLUMN,
    INSUFFICIENT,
    NONSENSE,
    REFUSED_VERDICTS_NAME,
    REFUSING_VERDICTS,
    SUBSTANTIVE,
    VALIDITY_SERVICE_MODULE,
    GradingWorld,
)
from fixtures.survey_windows import INSTITUTION_TIMEZONE, WINDOWS_BY_TERM_WEEK

pytestmark = pytest.mark.integration

# The three dates the tier tests name as literals, and the windows they are the
# local days of. Written here so the control below can check each one against the
# hand-computed calendar rather than against a second computation of it
# (`docs/MISTAKES.md` entry 19).
#
#   - course week 3 of cohort `F` is term week 9, whose window closes at
#     2026-10-19 03:59:59Z — 23:59:59 on Sunday 18 October in `America/New_York`;
#   - so a student first seen on the 18th could still have answered that week and
#     a student first seen on the 19th could not, which is §3.4's tier-3 boundary
#     with one second in it.
A_BOUNDARY_COURSE_WEEK = 3
THE_SUNDAY_THAT_WEEK_CLOSES_ON = date(2026, 10, 18)
THE_MONDAY_AFTER = date(2026, 10, 19)

# The instant the tier-3 tests seed the section's first roster sync at, and the
# institution-timezone day it falls on: 11:00 on Saturday 17 October, EDT.
A_FIRST_SYNC_AT = datetime(2026, 10, 17, 15, 0, tzinfo=UTC)
THE_DAY_OF_THAT_SYNC = date(2026, 10, 17)


def test_the_seeded_windows_are_the_hand_written_calendars_instants(
    grading_world: GradingWorld,
) -> None:
    """The six `survey_window` rows this world seeds are SPEC §3.1's instants for those weeks.

    The mutation this kills is in the fixture rather than in the code: a
    `seed_window` that wrote the wrong term week's instants, or that wrote the
    section's term weeks off by one, would make every elapsed-week assertion in
    this ticket measure a calendar nobody deploys — and each of them would still
    read as a statement about the formula.

    The count is asserted first because an empty read satisfies a comparison over
    an empty set (`docs/MISTAKES.md` entry 3).
    """
    world = grading_world.build()
    rows = world.calendar.windows_of(world.section)

    assert len(rows) == world.length_weeks, (
        f"The seeded section has {len(rows)} `survey_window` rows rather than {world.length_weeks}, "
        f"one per course week of cohort {world.cohort!r}. Every elapsed-week assertion in E3-03 "
        "rests on this set."
    )
    seeded = {row["term_week"]: (row["opens_at"], row["closes_at"]) for row in rows}
    expected = {
        world.term_week_of(course_week): WINDOWS_BY_TERM_WEEK[world.term_week_of(course_week)]
        for course_week in world.course_weeks
    }
    assert seeded == expected, (
        f"The seeded windows are {seeded}, and the hand-computed Fall 2026 calendar puts this "
        f"section's weeks at {expected}. `tests/fixtures/survey_windows.py` holds the literals and "
        "`test_the_fall_2026_window_calendar_is_spec_3_1s_rhythm.py` controls them against SPEC "
        "§3.1's rhythm, so a difference here is this fixture's arithmetic."
    )


def test_the_clock_lands_after_the_close_that_elapsed_through_named(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any, clock_service: Any
) -> None:
    """`elapsed_through(3)` really puts the clock after course week 3's window closed.

    Asked of `app.services.clock.now` — the reader E3-03's elapsed rule consults —
    rather than of the value the helper returned, because the question is whether
    the *service* sees the moved clock. ADR 0109 makes the override an offset, so
    the effective now keeps moving after it is set; this is the assertion that the
    minute of margin is enough.

    Paired with the test below. One of the two on its own would pass against a
    clock that had not moved at all.
    """
    world = grading_world.build()
    world.elapsed_through(clock_overrides, A_BOUNDARY_COURSE_WEEK)

    now = clock_service.now(world.session, settings=window_settings)
    closes_at = world.closes_at(A_BOUNDARY_COURSE_WEEK)

    assert now > closes_at, (
        f"With the override set a minute past course week {A_BOUNDARY_COURSE_WEEK}'s close, "
        f"`clock.now` answered {now}, which is not after {closes_at}. Either the override does not "
        "reach the service under these settings or the offset has drifted further than the margin "
        "this fixture leaves."
    )
    assert now < world.closes_at(A_BOUNDARY_COURSE_WEEK + 1), (
        f"`clock.now` answered {now}, which is past course week {A_BOUNDARY_COURSE_WEEK + 1}'s "
        "close as well. The helper is supposed to elapse exactly the weeks up to the one it was "
        "given, and a clock that overshoots would credit a week no test asked for."
    )


def test_the_clock_lands_before_the_close_that_not_yet_closed_named(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any, clock_service: Any
) -> None:
    """The other side: `not_yet_closed(1)` puts the clock inside course week 1's window.

    This is the state SPEC §3.4 calls "a section with no elapsed weeks", and the
    whole of criterion 4 rests on the clock really being there.
    """
    world = grading_world.build()
    world.not_yet_closed(clock_overrides, 1)

    now = clock_service.now(world.session, settings=window_settings)
    closes_at = world.closes_at(1)

    assert now < closes_at, (
        f"With the override set a minute before course week 1's close, `clock.now` answered {now}, "
        f"which is not before {closes_at}. Criterion 4's 'no score at all' case cannot be posed at "
        "all if the clock is past that instant."
    )
    assert now > closes_at - timedelta(hours=1), (
        f"`clock.now` answered {now}, more than an hour before {closes_at}. The helper sets a "
        f"margin of {A_MINUTE}; a much larger gap means the override is not being applied and the "
        "answer is real time."
    )


def verdict_tokens(refused: Any) -> list[str]:
    """The stored tokens behind a collection of verdicts, whatever type it holds them as.

    `getattr(member, "value", member)` reads an enum member and passes a plain
    string through, so this control keeps working whether `REFUSED_VERDICTS` is a
    set of `ValidityVerdict` members or of the tokens themselves — and it never
    sorts the members, which is what raised `TypeError` when this was first
    written.
    """
    return sorted(str(getattr(member, "value", member)) for member in refused)


def test_the_verdicts_this_suite_drives_are_the_set_validity_refuses(
    validity_module: Any,
) -> None:
    """The two verdicts these tests plant are exactly `REFUSED_VERDICTS`, and substantive is not.

    `tests/fixtures/grading.py` spells `insufficient` and `nonsense` from SPEC
    §3.3 rather than importing them, so that a suite about *credit* does not take
    its expectation from the module that decides *validity* (`docs/MISTAKES.md`
    entry 19). This is the control that keeps the two spellings from drifting: if
    E2-08's set ever changes, this test goes red naming the constant, instead of
    the comment tests quietly measuring a set nobody refuses any more.

    **The comparison is between stored tokens, not between Python objects.**
    `REFUSED_VERDICTS` holds `ValidityVerdict` members, which are neither strings
    nor orderable — comparing a set of members against a set of `str` is quietly
    `False` for every member, and sorting them raises. ADR 0030 makes the member's
    *value* "the token stored, serialised and compared everywhere outside Python",
    and the token is what this suite writes into `classification.verdict`, so the
    token is the right currency for this comparison (`docs/MISTAKES.md` entry 35 —
    a privilege, or here a vocabulary, held in a currency the guard did not
    enumerate).
    """
    refused = getattr(validity_module, REFUSED_VERDICTS_NAME, None)
    assert refused is not None, (
        f"`{VALIDITY_SERVICE_MODULE}` exposes no `{REFUSED_VERDICTS_NAME}`. E3-03's ticket cites it "
        "by file and line as 'the set that makes a comment not count'."
    )
    tokens = verdict_tokens(refused)
    assert set(REFUSING_VERDICTS) == set(tokens), (
        f"This suite plants {sorted(REFUSING_VERDICTS)} as the verdicts that cost a comment its "
        f"item, and `{REFUSED_VERDICTS_NAME}` holds {tokens}. The two have to be the same set or "
        "the comment tests are asserting about verdicts nothing refuses."
    )
    assert SUBSTANTIVE not in tokens, (
        f"`{REFUSED_VERDICTS_NAME}` contains {SUBSTANTIVE!r}, so the 'counts' half of every comment "
        "pair in this ticket is planting a verdict that refuses. Those pairs would then agree with "
        "any implementation at all."
    )


def test_the_course_week_axis_is_not_the_term_week_axis(grading_world: GradingWorld) -> None:
    """The section these tests use starts inside the term, so the two axes disagree.

    SPEC §2.2 has two week axes and §3.4's ledger names the **course** week. A
    cohort starting in term week 1 makes the two indistinguishable, and every
    ledger assertion in this ticket would then pass against an implementation that
    numbered lines on the term axis. This is the control that says the axes really
    are apart in the world these tests are run over.
    """
    world = grading_world.build()

    assert world.term_week_of(1) != 1, (
        f"Course week 1 of cohort {world.cohort!r} is term week {world.term_week_of(1)}. A cohort "
        "starting in the term's first week cannot tell a course week from a term week, and the "
        "ledger tests in this ticket would stop discriminating."
    )
    assert world.term_week_of(1) == world.first_term_week, (
        "The first course week is not the cohort's first term week, so this fixture's mapping "
        "between the two axes disagrees with `SEEDED_COHORTS`."
    )


def test_the_boundary_dates_the_tier_tests_name_are_the_days_those_instants_fall_on(
    grading_world: GradingWorld,
) -> None:
    """The three literal dates in the tier tests, checked against the calendar and the zone.

    §3.4's tier 3 compares a `started_on` **date** with a window's **instant**, so
    every tier-3 case in this ticket is written as a date literal. A literal that
    named the wrong day would make the boundary pair sit on the same side of the
    line and pass against anything (`docs/MISTAKES.md` entry 19 — the expectation
    must not be a second computation, and it must not be an unchecked guess
    either).
    """
    world = grading_world.build()
    zone = ZoneInfo(INSTITUTION_TIMEZONE)

    closing_day = world.closes_at(A_BOUNDARY_COURSE_WEEK).astimezone(zone).date()
    assert closing_day == THE_SUNDAY_THAT_WEEK_CLOSES_ON, (
        f"Course week {A_BOUNDARY_COURSE_WEEK}'s window closes on {closing_day} in "
        f"{INSTITUTION_TIMEZONE}, and the tier tests name {THE_SUNDAY_THAT_WEEK_CLOSES_ON}."
    )
    assert closing_day + timedelta(days=1) == THE_MONDAY_AFTER, (
        f"{THE_MONDAY_AFTER} is not the day after {closing_day}, so the tier-3 pair does not "
        "straddle the boundary it claims to."
    )
    sync_day = A_FIRST_SYNC_AT.astimezone(zone).date()
    assert sync_day == THE_DAY_OF_THAT_SYNC, (
        f"The seeded first sync at {A_FIRST_SYNC_AT} falls on {sync_day} in "
        f"{INSTITUTION_TIMEZONE}, and the tier tests name {THE_DAY_OF_THAT_SYNC}."
    )
    assert sync_day < THE_SUNDAY_THAT_WEEK_CLOSES_ON, (
        "The seeded first sync is not earlier than the boundary week's close, so a student added "
        "after it could not be distinguished from one the first sync already contained."
    )


def test_a_seeded_week_leaves_one_response_one_answer_per_position_and_one_verdict(
    grading_world: GradingWorld,
) -> None:
    """`answer_week` writes what the tests believe it writes.

    Non-vacuity for the whole ticket: every numerator assertion is a claim about
    `answer` rows, and a helper that silently wrote none would make "0 completed"
    true for a reason no test intends (`docs/MISTAKES.md` entry 30 in its second
    form — a fixture that supplies the answer by supplying nothing).
    """
    world = grading_world.build()
    student = world.student("e3-03-machinery")
    rows = world.answer_week(student, 1, verdicts={2: NONSENSE})

    assert sorted(rows) == world.positions, (
        f"A fully answered week left answers at positions {sorted(rows)} rather than at "
        f"{world.positions}."
    )
    comment_positions = world.comment_positions()
    assert comment_positions, (
        "The question set in force carries no comment question, so no test in this ticket could "
        "pose the classification rule at all."
    )
    for position in comment_positions:
        verdicts = [
            row[CLASSIFICATION_VERDICT_COLUMN] for row in world.classifications_of(rows[position])
        ]
        assert len(verdicts) == 1, (
            f"The comment at position {position} carries {len(verdicts)} classification rows "
            f"({verdicts}) rather than the one this helper wrote."
        )
    assert world.classifications_of(rows[2])[0][CLASSIFICATION_VERDICT_COLUMN] == NONSENSE, (
        "The verdict named in the call did not reach the row, so a test that plants "
        f"{INSUFFICIENT!r} or {NONSENSE!r} would be measuring whatever the default is."
    )


def test_the_question_set_in_force_carries_the_count_the_world_planted(
    grading_world: GradingWorld,
) -> None:
    """A world built for three questions really has three, and the five-question set is §3.2's.

    The denominator criterion is asked by planting a set of a different size, so a
    `plant_question_set` that ignored its count would make that pair two runs of
    the same case.
    """
    world = grading_world.build(question_count=5)
    assert world.positions == [1, 2, 3, 4, 5], (
        f"The five-question world carries positions {world.positions}. SPEC §3.2's set is five "
        "questions at positions 1 to 5."
    )
    assert world.shape_of[2] == "comment", (
        f"Position 2 of the five-question set is a {world.shape_of[2]!r}; SPEC §3.2 makes it the "
        "instructor comment, and the comment tests answer that position."
    )

    world.plant_question_set(version=2, question_count=3)
    assert world.positions == [
        1,
        2,
        3,
    ], f"After planting a three-question set the world carries positions {world.positions}."
    assert world.comment_positions(), (
        "The three-question set carries no comment question, so the classification rule cannot be "
        "posed against it."
    )


@pytest.fixture
def validity_module() -> Any:
    """`app.services.validity`, for the refused-verdict control alone.

    Imported here rather than in `tests/fixtures/grading.py` so that the E3-03
    fixtures depend on nothing but the schema: this is the one place in the ticket
    that reads E2-08's module, and it reads it to check a constant rather than to
    take an expectation from it.
    """
    try:
        return __import__(VALIDITY_SERVICE_MODULE, fromlist=["*"])
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{VALIDITY_SERVICE_MODULE}` does not import ({missing}). E2-08 ships it and E3-03's "
            f"ticket cites `{REFUSED_VERDICTS_NAME}` in it by line."
        )
