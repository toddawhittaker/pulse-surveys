"""The policy in force when a week's report opens governs that week — E7-02, done-when 4.

> **The policy of record is the policy in force at report open.** A switch to
> required recorded after the week's report opened does not hold that week; a
> switch to encouraged recorded after it opened does not release a held week.
> Both cases are tested at one second either side of the opening. If the
> course's responsible person changes after the report opens, a held week stays
> held; this too is tested one second either side of the opening.

Work order decision 2: the policy of record for a section-week is the latest
`response_policy` row **by `sequence`** for the section's course with `set_at <=
report_opens_at(week close)`; none is encouraged; no person lookup at read time.
Decision 1 (ADR 0193): a row covers one course, fixed when written.

**Where the second sits.** Each boundary is planted as a row's `set_at`, written
to the second by the superuser, and read with the clock an hour past the opening —
so the boundary is a stored instant and never a moving clock (ADR 0109's
effective clock drifts while it is read; a second on the *clock* is a boundary
nothing can stand on). Three instants where decision 2 settles the edge itself:
one second before, the opening exactly (`<=`, in force), one second after.

**Course week 2** of `F1WW`, whose report opens 2026-10-12 10:00 UTC
(`REPORT_OPENS_BY_TERM_WEEK`, hand-written and checked against the calendar).

**Which failure a red is, before E7-02 lands.** Every test fails naming M2's
`course_id` (`require_the_policy_course`) in its first planted row.
"""

from datetime import datetime, timedelta

import pytest
from fixtures.lead_review import SIBLING_COHORT, UNMAPPED_COHORT
from fixtures.the_hold import (
    AWAITING,
    CHAIR,
    ENCOURAGED,
    HELD_WEEK,
    LEAD_FACULTY,
    ONE_SECOND,
    REQUIRED,
    STATE,
    UNANSWERED,
    WEEK_BEFORE,
    HoldWorld,
    report_opens,
)

pytestmark = pytest.mark.integration

# Decision 2's edge, written as offsets from the opening.
BOUNDARY = {
    "one-second-before": -ONE_SECOND,
    "at-the-opening": timedelta(0),
    "one-second-after": ONE_SECOND,
}
# The ticket's third case asks for the two sides only.
EITHER_SIDE = {"one-second-before": -ONE_SECOND, "one-second-after": ONE_SECOND}

# A day before the opening: a row far from the edge, for the policy a later switch
# is measured against.
WELL_BEFORE = timedelta(days=1)

NEW_LEAD_NAME = "Peregrine Ashcombe-Leads-Now"


def opening() -> datetime:
    return report_opens(HELD_WEEK)


def by_the_lead(world: HoldWorld, mode: str, set_at: datetime) -> None:
    world.a_policy(
        course=world.own_course,
        setter=world.person(world.names.lead).person_id,
        role=LEAD_FACULTY,
        mode=mode,
        set_at=set_at,
    )


def state_read(world: HoldWorld, label: str) -> str:
    """One student of `F1WW` reads course week 2 an hour after it opens; the state."""
    student = world.a_student(label, world.taught)
    world.stand_after_the_opening(HELD_WEEK)
    return str(world.payload(student, course_week=HELD_WEEK)[STATE])


@pytest.mark.parametrize("edge", sorted(BOUNDARY))
def test_a_switch_to_required_holds_the_week_only_if_recorded_by_the_opening(
    hold: HoldWorld, edge: str
) -> None:
    """One `REQUIRED` row at the opening plus `BOUNDARY[edge]`; no response.

    Before and at the opening: `awaiting`. One second after: `unanswered`, the
    week is encouraged as it opened.

    **The mutations this kill:** the policy of record read as of the reading
    clock (the row after the opening holds the week); the comparison written `<`
    (the row at the opening is not in force); a comparison against the window's
    close rather than the report's opening (every row here is after the close, so
    none would hold).
    """
    world = hold
    by_the_lead(world, REQUIRED, opening() + BOUNDARY[edge])

    found = state_read(world, f"required-{edge}")

    expected = UNANSWERED if BOUNDARY[edge] > timedelta(0) else AWAITING
    assert found == expected, (
        f"A switch to required recorded {edge} of the opening ({opening()}) read {found!r}. "
        f"Decision 2: in force only if `set_at <= report_opens_at`, so {expected!r}."
    )


@pytest.mark.parametrize("edge", sorted(BOUNDARY))
def test_a_switch_to_encouraged_releases_the_week_only_if_recorded_by_the_opening(
    hold: HoldWorld, edge: str
) -> None:
    """`REQUIRED` a day before; `ENCOURAGED` at the opening plus `BOUNDARY[edge]`; no response.

    Before and at the opening the switch is in force: `unanswered`. One second
    after, the week opened held and stays held: `awaiting`.

    **The mutations this kill:** the latest row as of the reading clock (the late
    switch releases a held week — the ticket's "a later change never releases a
    week already held"); `<` for `<=`; and a policy of record that takes any
    `REQUIRED` row before the opening regardless of what followed it (the
    one-second-before case would hold).
    """
    world = hold
    by_the_lead(world, REQUIRED, opening() - WELL_BEFORE)
    by_the_lead(world, ENCOURAGED, opening() + BOUNDARY[edge])

    found = state_read(world, f"encouraged-{edge}")

    expected = AWAITING if BOUNDARY[edge] > timedelta(0) else UNANSWERED
    assert found == expected, (
        f"Required a day before, then encouraged {edge} of the opening ({opening()}): the week "
        f"read {found!r}. Decision 2: {expected!r}."
    )


@pytest.mark.parametrize("edge", sorted(EITHER_SIDE))
@pytest.mark.parametrize("successor", ["a-new-lead", "no-lead"])
def test_a_change_of_responsible_person_after_the_opening_leaves_the_week_as_it_opened(
    hold: HoldWorld, edge: str, successor: str
) -> None:
    """The lead records `REQUIRED` at the opening plus `EITHER_SIDE[edge]`; then the course changes hands.

    After the opening, and after the row exists, the lead's mapping and grant go,
    and the course is mapped to a new lead (`a-new-lead`) or to nobody, falling to
    the chair (`no-lead`). Neither successor has recorded anything. Before: the
    week opened held and stays `awaiting`. After: it opened encouraged and stays
    `unanswered`.

    **The mutation this kills:** the policy resolved through the course's
    responsible person *now* — ADR 0192's original keying, "the latest row for a
    prefix, person and role" — which finds no row for the successor and releases
    the held week. Decision 2: no person lookup at read time; ADR 0193: lead
    mappings keep no history. **The near miss:** the after-side, which the
    change must not hold either.
    """
    world = hold
    by_the_lead(world, REQUIRED, opening() + EITHER_SIDE[edge])
    successor_id = None
    if successor == "a-new-lead":
        successor_id = world.names.a_named_person(NEW_LEAD_NAME)
    world.move_the_lead(world.own_course, to=successor_id)

    found = state_read(world, f"handover-{successor}-{edge}")

    expected = UNANSWERED if EITHER_SIDE[edge] > timedelta(0) else AWAITING
    assert found == expected, (
        f"Required {edge} of the opening by the lead, then the course passed to {successor}: the "
        f"week read {found!r}. The ticket: a held week stays held when the responsible person "
        f"changes after the opening, and an unheld one stays unheld — {expected!r}."
    )


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [(ENCOURAGED, REQUIRED, AWAITING), (REQUIRED, ENCOURAGED, UNANSWERED)],
    ids=["required-inserted-last", "encouraged-inserted-last"],
)
def test_the_latest_policy_is_the_latest_by_sequence_not_by_set_at(
    hold: HoldWorld, first: str, second: str, expected: str
) -> None:
    """Two rows before the opening; the one inserted second carries the *earlier* `set_at`.

    `first` at the opening minus one hour, inserted first; `second` at the
    opening minus two hours, inserted second. Decision 2 reads the latest by
    `sequence`, so `second` governs. (A dev clock moved backwards between two
    switches writes exactly this.)

    **The mutation this kills:** "latest" read as the greatest `set_at`, which
    picks `first`. Both orders, so "required wins" survives neither.
    """
    world = hold
    by_the_lead(world, first, opening() - timedelta(hours=1))
    by_the_lead(world, second, opening() - timedelta(hours=2))

    found = state_read(world, f"sequence-{second}")

    assert found == expected, (
        f"{first} then {second}, the second with the earlier `set_at`: the week read {found!r}. "
        f"Decision 2 reads the latest row by `sequence` — {second} — so {expected!r}."
    )


@pytest.mark.parametrize("whose", ["the-sibling-lead", "the-chair"])
def test_another_courses_switch_in_the_same_prefix_holds_only_that_course(
    hold: HoldWorld, whose: str
) -> None:
    """The sibling lead requires the sibling course (or the chair the unled one); `F1WW` is free.

    Ruling 1: "A policy covers only its setter's own courses in that prefix." The
    twin, in the same world: a student of the other course's section reads
    `awaiting`, so the row is in force where it belongs.

    **The mutation this kills:** the policy of record keyed on the prefix (the
    latest row for any course in it), which holds `F1WW` under somebody else's
    switch — SPEC §4.1 item 2's sibling isolation, at the read.
    """
    world = hold
    if whose == "the-sibling-lead":
        course, setter, role, cohort = (
            world.sibling_course,
            world.person(world.names.sibling_lead).person_id,
            LEAD_FACULTY,
            SIBLING_COHORT,
        )
    else:
        course, setter, role, cohort = (
            world.unmapped_course,
            world.person(world.names.chair).person_id,
            CHAIR,
            UNMAPPED_COHORT,
        )
    world.windows_for(cohort, WEEK_BEFORE, HELD_WEEK)
    world.a_policy(
        course=course, setter=setter, role=role, mode=REQUIRED, set_at=opening() - WELL_BEFORE
    )
    theirs = world.a_student(f"{whose}-course", world.section_id(cohort))
    ours = world.a_student(f"{whose}-own", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    their_state = world.payload(theirs, course_week=HELD_WEEK)[STATE]
    our_state = world.payload(ours, course_week=HELD_WEEK)[STATE]

    assert (
        their_state == AWAITING
    ), f"The switch's own course read {their_state!r}; the row is in force there, so `awaiting`."
    assert our_state == UNANSWERED, (
        f"`F1WW` read {our_state!r} under {whose}'s switch for another course of the prefix. "
        "Ruling 1: a policy covers only its setter's own courses."
    )
