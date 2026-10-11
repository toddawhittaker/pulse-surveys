"""The results payload lists the published weeks, and a no-week read opens on the latest — E7-02's amendment.

The amendment before review (for E7-06's page, which pages back through published
weeks only, SPEC §5.4, and opens on the latest one):

> A1. `StudentWeekResults` gains `published_weeks: list[int]`: the section's
>     course weeks whose report has opened at `now` (the same `_published_weeks`
>     the read uses), ascending. Same for every state.
> A2. `GET /api/student/sections/{section_id}/results` (no week): the same
>     payload for the latest published week. The same single 404 when the section
>     has no published week, or for every case the week route refuses.
> A3. … `published_weeks` never lists a week whose report has not opened (one
>     second either side of the opening); the latest route equals the week route
>     for that week …

The refusals and the student-route sweeps for the no-week route are in
`test_a_refused_results_read_names_nothing_of_the_section.py` and the two sweep
modules; this module is the answered half.

**The pair stands on the clock**, unlike done-when 4's ±1s pairs, which stand on
a stored `set_at`: whether a week is published is a question about `now`. ADR
0109's effective clock only drifts forward while it is read, so the listed side
stands at the opening itself, and the not-yet side 30 seconds before it — wide
enough for the time between setting the clock and the read under `-n 4`.

**Which failure a red is, before the amendment lands.** Every test fails in
`payload_of`, on a payload without `published_weeks`, or naming the missing
no-week route (`latest_results_route`).
"""

from datetime import timedelta

import pytest
from fixtures.report_api import UNTAUGHT_COHORT
from fixtures.the_hold import (
    AWAITING,
    FIRST_ROW_AFTER_OPENING,
    HELD_WEEK,
    INSTRUCTOR,
    LEAD_FACULTY,
    PUBLISHED,
    PUBLISHED_WEEKS,
    REQUIRED,
    RESPONSE,
    STATE,
    TEXT,
    WEEK_BEFORE,
    HoldWorld,
    report_opens,
)

pytestmark = pytest.mark.integration

WEEK_ONE_TEXT = "E7-02 the teacher's reply to course week one"
WEEK_TWO_TEXT = "E7-02 the teacher's reply to course week two"

# The not-yet side stands 30 seconds before the opening, not one: the clock moves
# while it is read, and under `-n 4` more than a second can pass between setting
# it and the read. The listed side stands at the opening itself, which forward
# drift can only move further past.
EITHER_SIDE = {"thirty-seconds-before": -timedelta(seconds=30), "at-the-opening": timedelta(0)}


def reply_to(world: HoldWorld, course_week: int, text: str) -> None:
    world.a_response(
        section_id=world.taught,
        course_week=course_week,
        author=world.person(world.names.teacher).person_id,
        role=INSTRUCTOR,
        body=text,
        published_at=report_opens(course_week) + FIRST_ROW_AFTER_OPENING,
    )


@pytest.mark.parametrize("edge", sorted(EITHER_SIDE))
def test_published_weeks_lists_a_week_only_once_its_report_has_opened(
    hold: HoldWorld, edge: str
) -> None:
    """The clock at course week 2's opening plus `EITHER_SIDE[edge]`: week 1's payload lists [1] or [1, 2].

    **The mutations this kill:** the list built from the section's windows (all
    six weeks, every one with a window); and from closed windows (week 2's closed
    six hours before its report opens, so it would be listed early). The exact
    instant (`>=`) is the unit suite's (`week_is_published`), not this pair's.
    **The near miss:** the at-the-opening side, which lists week 2.
    """
    world = hold
    student = world.a_student(f"weeks-{edge}", world.taught)
    world.stand_at(report_opens(HELD_WEEK) + EITHER_SIDE[edge])

    weeks = world.payload(student, course_week=WEEK_BEFORE)[PUBLISHED_WEEKS]

    expected = [WEEK_BEFORE, HELD_WEEK] if EITHER_SIDE[edge] >= timedelta(0) else [WEEK_BEFORE]
    assert weeks == expected, (
        f"{edge} of course week {HELD_WEEK}'s opening ({report_opens(HELD_WEEK)}), "
        f"`{PUBLISHED_WEEKS}` is {weeks}; A1: the weeks whose report has opened, ascending — "
        f"{expected}."
    )


def test_published_weeks_is_the_same_on_a_held_week_and_a_released_one(hold: HoldWorld) -> None:
    """Week 1 released, week 2 held, read at one instant: both payloads list [1, 2].

    **The mutations this kill:** the list carried only by a released payload (a
    held week's page has nothing to page back through); and the list built from
    the weeks that have a response (week 2 has none, and is published all the
    same). A1: "Same for every state."
    """
    world = hold
    world.a_policy(
        course=world.own_course,
        setter=world.person(world.names.lead).person_id,
        role=LEAD_FACULTY,
        mode=REQUIRED,
        set_at=report_opens(WEEK_BEFORE) - timedelta(days=1),
    )
    reply_to(world, WEEK_BEFORE, WEEK_ONE_TEXT)
    student = world.a_student("weeks-every-state", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    released = world.payload(student, course_week=WEEK_BEFORE)
    held = world.payload(student, course_week=HELD_WEEK)

    assert (released[STATE], held[STATE]) == (PUBLISHED, AWAITING), (
        f"The premise: week 1 released and week 2 held; they read {released[STATE]!r} and "
        f"{held[STATE]!r}."
    )
    assert released[PUBLISHED_WEEKS] == held[PUBLISHED_WEEKS] == [WEEK_BEFORE, HELD_WEEK], (
        f"Week 1's payload lists {released[PUBLISHED_WEEKS]} and week 2's {held[PUBLISHED_WEEKS]}; "
        f"both are [{WEEK_BEFORE}, {HELD_WEEK}]."
    )


def test_published_weeks_are_the_sections_own(hold: HoldWorld) -> None:
    """`Q1WW` has a window for course week 1 only; at the same instant `F1WW` lists [1, 2] and `Q1WW` [1].

    **The mutation this kills:** the list computed for the course, the term or the
    cohort's calendar rather than from the section's own windows — the shape that
    puts a week on a student's page their section never ran.
    """
    world = hold
    world.windows_for(UNTAUGHT_COHORT, WEEK_BEFORE)
    ours = world.a_student("weeks-own", world.taught)
    theirs = world.a_student("weeks-sibling", world.sibling_section)
    world.stand_after_the_opening(HELD_WEEK)

    our_weeks = world.payload(ours, course_week=WEEK_BEFORE)[PUBLISHED_WEEKS]
    their_weeks = world.payload(theirs, course_week=WEEK_BEFORE)[PUBLISHED_WEEKS]

    assert our_weeks == [WEEK_BEFORE, HELD_WEEK], f"`F1WW` lists {our_weeks}."
    assert their_weeks == [
        WEEK_BEFORE
    ], f"`Q1WW`, with a window for course week 1 only, lists {their_weeks}."


def test_the_latest_route_answers_exactly_what_the_week_route_answers_for_that_week(
    hold: HoldWorld,
) -> None:
    """An hour after course week 2 opens, with a reply in weeks 1 and 2: no-week read == week-2 read.

    **The mutations this kill:** the latest week taken as the section's last
    window (course week 6, whose report has not opened); as the first published
    week; as the latest week with a response; and a no-week payload assembled by
    a second code path that drifts from the week route's.
    """
    world = hold
    reply_to(world, WEEK_BEFORE, WEEK_ONE_TEXT)
    reply_to(world, HELD_WEEK, WEEK_TWO_TEXT)
    student = world.a_student("latest-equals-week", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    latest = world.latest_payload(student)
    week = world.payload(student, course_week=HELD_WEEK)

    assert latest == week, (
        f"The no-week read answered {latest!r}; the week route for course week {HELD_WEEK}, the "
        f"latest published, answered {week!r}. A2: the same payload."
    )
    assert latest[RESPONSE][TEXT] == WEEK_TWO_TEXT


def test_the_latest_route_moves_to_a_week_when_its_report_opens(hold: HoldWorld) -> None:
    """Read an hour before course week 2 opens and an hour after: week 1's payload, then week 2's.

    `docs/MISTAKES.md` entry 51's pair, on the page's opening read: the first
    carries week 1's reply and lists [1], the second week 2's reply and lists
    [1, 2], and week 2's reply is nowhere in the first.

    **The mutations this kill:** a latest week computed once and kept; and a
    latest week that runs ahead of its report (week 2's reply served before the
    opening). **The near miss:** the before-read, which must answer week 1.
    """
    world = hold
    reply_to(world, WEEK_BEFORE, WEEK_ONE_TEXT)
    reply_to(world, HELD_WEEK, WEEK_TWO_TEXT)
    student = world.a_student("latest-moves", world.taught)

    world.stand_before_the_opening(HELD_WEEK)
    before_answer = world.latest(student)
    before = world.latest_payload(student)
    world.stand_after_the_opening(HELD_WEEK)
    after = world.latest_payload(student)

    assert (before[RESPONSE][TEXT], before[PUBLISHED_WEEKS]) == (WEEK_ONE_TEXT, [WEEK_BEFORE]), (
        f"An hour before course week 2 opens the no-week read answered {before!r}; the latest "
        "published week is week 1."
    )
    assert (
        WEEK_TWO_TEXT not in before_answer.text
    ), "Before course week 2's report opened, the no-week read carried week 2's reply."
    assert (after[RESPONSE][TEXT], after[PUBLISHED_WEEKS]) == (
        WEEK_TWO_TEXT,
        [WEEK_BEFORE, HELD_WEEK],
    ), f"An hour after course week 2 opens the no-week read answered {after!r}."
