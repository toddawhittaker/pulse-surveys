"""Which weeks are in a student's denominator — SPEC §3.4's three tiers, ticket E3-03.

SPEC §3.4: "Late adds and missed weeks select **which weeks' items form the
denominator** … The denominator starts at the student's first enrolled week (from
NRPS enrollment data). Where the platform supplies no enrollment dates — most
supply none — a student counts as enrolled from the section's start date, except
that a student who first appears in a roster sync later than their section's
first sync counts from the week of that sync."

E3-03's work order resolves those three sentences into a rule with a boundary,
and ADR 0131 records it:

  - **tier 1** — `enrollment.lms_window_start` is not NULL: the first week is the
    earliest course week whose `closes_at` is **at or after** that instant;
  - **tier 3** — otherwise, where the section has at least one `nrps_call` row and
    `started_on` is **later than** the institution-timezone date of the section's
    earliest `called_at`: the first week is the earliest course week whose
    `closes_at` is at or after the start of that day in the institution timezone;
  - **tier 2** — otherwise: course week 1.

The rule in one sentence is "a week counts if the student could still have
answered it", and every test below is one side of a line. **Each line is asserted
from both sides** (`docs/MISTAKES.md` entry 3, and the ticket's third criterion
says so in as many words): the tier-1 instant a microsecond before, exactly on,
and a microsecond after a window's close; the tier-3 date on the Sunday a window
closes and on the Monday after it; and the tier-3 *selection* on the day of the
section's first sync and the day after it.

**Nobody answers anything in this module.** A student with no answers has a
numerator of zero whatever the tiers say, so the denominator and the ledger are
the only things that move — which is what makes each assertion a statement about
week selection and nothing else.
"""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from fixtures.grading import A_MOMENT, GradingWorld, ledger_of

pytestmark = pytest.mark.integration

# Four of the section's six weeks have closed in every test here.
ELAPSED_WEEKS = 4
ITEMS_PER_WEEK = 5

# The course week whose close every boundary in this module is measured against.
# Cohort `F`'s course week 3 is term week 9, closing 2026-10-19 03:59:59Z —
# 23:59:59 on Sunday 18 October in `America/New_York`.
BOUNDARY_WEEK = 3

# The two days either side of that instant, as `enrollment.started_on` is stored:
# a date. A student first seen on the Sunday could still have answered that week;
# one first seen on the Monday could not, and the whole of tier 3's boundary is
# those two dates being on opposite sides of one second.
# `test_the_grading_machinery_stands_up_what_it_claims.py` checks both against the
# calendar rather than leaving them as unverified literals.
THE_SUNDAY_THAT_WEEK_CLOSES_ON = date(2026, 10, 18)
THE_MONDAY_AFTER = date(2026, 10, 19)

# The section's first roster sync, and the institution-timezone day it falls on:
# 11:00 on Saturday 17 October, EDT. Late in the term on purpose — tier 3's
# *selection* compares `started_on` with this day, and a first sync in week 1
# would put both sides of that comparison in the same tier-3 answer and make the
# pair undiscriminating.
FIRST_SYNC_AT = datetime(2026, 10, 17, 15, 0, tzinfo=UTC)
THE_DAY_OF_THE_FIRST_SYNC = date(2026, 10, 17)


def ledger_from(first_week: int) -> str:
    """The ledger of a student who answered nothing, credited from `first_week` on."""
    return ledger_of([(week, 0, ITEMS_PER_WEEK) for week in range(first_week, ELAPSED_WEEKS + 1)])


def weeks_from(first_week: int) -> int:
    """How many items a student credited from `first_week` has in their denominator."""
    return (ELAPSED_WEEKS - first_week + 1) * ITEMS_PER_WEEK


def test_a_platform_dated_add_before_a_window_closes_is_credited_with_that_week(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Tier 1, the inside of the line: `lms_window_start` a microsecond before the close.

    The student could still have answered course week 3 — the window was open for
    another microsecond — so that week is in the denominator and heads the ledger.

    **The mutation this kills:** a tier-1 rule comparing against a window's
    `opens_at` rather than its close, which drops this week; and a rule that
    rounds the platform's instant to a day, which cannot tell this case from the
    one two tests below.
    """
    world = grading_world.build()
    student = world.student(
        "e3-03-tier-1-inside",
        lms_window_start=world.closes_at(BOUNDARY_WEEK) - A_MOMENT,
    )
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    score = world.score_for(student, settings=window_settings)

    assert score.total == weeks_from(BOUNDARY_WEEK), (
        f"A student the platform dated a microsecond before course week {BOUNDARY_WEEK}'s window "
        f"closed has a denominator of {score.total} rather than {weeks_from(BOUNDARY_WEEK)}. That "
        "week was still open to them, so it counts."
    )
    assert score.ledger == ledger_from(BOUNDARY_WEEK), (
        f"The ledger reads:\n{score.ledger}\n\nrather than:\n{ledger_from(BOUNDARY_WEEK)}\n\n"
        "SPEC §3.4: weeks before the student's first enrolled week appear nowhere."
    )


def test_a_platform_dated_add_at_the_instant_a_window_closes_is_credited_with_that_week(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Tier 1, standing exactly on the line: `closes_at >= lms_window_start` includes equality.

    **The mutation this kills** is the one character between `>=` and `>`. The two
    tests either side of this one both pass against a strict comparison; only this
    case distinguishes them, and it is reachable because both values are stored
    instants rather than a moving clock.
    """
    world = grading_world.build()
    student = world.student(
        "e3-03-tier-1-exactly",
        lms_window_start=world.closes_at(BOUNDARY_WEEK),
    )
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    score = world.score_for(student, settings=window_settings)

    assert score.total == weeks_from(BOUNDARY_WEEK), (
        f"A student the platform dated at exactly course week {BOUNDARY_WEEK}'s closing instant "
        f"has a denominator of {score.total} rather than {weeks_from(BOUNDARY_WEEK)}. The work "
        "order's rule is 'the earliest course week whose closes_at >= lms_window_start', and the "
        "window is open up to and including that instant (E2-06 treats both ends as inclusive)."
    )


def test_a_platform_dated_add_after_a_window_closed_is_not_credited_with_that_week(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Tier 1, the outside of the line: a microsecond after the close, the week is gone.

    **The mutation this kills:** a tier-1 rule that credits the week containing the
    instant however late in it the student arrived — which would charge this
    student for a week they could not have answered, and is the over-credit
    direction the boundary sentence exists to refuse.
    """
    world = grading_world.build()
    student = world.student(
        "e3-03-tier-1-outside",
        lms_window_start=world.closes_at(BOUNDARY_WEEK) + A_MOMENT,
    )
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    score = world.score_for(student, settings=window_settings)

    assert score.total == weeks_from(BOUNDARY_WEEK + 1), (
        f"A student the platform dated a microsecond after course week {BOUNDARY_WEEK}'s window "
        f"closed has a denominator of {score.total} rather than {weeks_from(BOUNDARY_WEEK + 1)}. "
        "SPEC §3.1 forbids back-filling a missed week, so a week that closed before they were "
        "enrolled is not theirs to have missed."
    )
    assert score.ledger == ledger_from(
        BOUNDARY_WEEK + 1
    ), f"The ledger reads:\n{score.ledger}\n\nrather than:\n{ledger_from(BOUNDARY_WEEK + 1)}"


def test_an_undated_member_of_a_section_with_no_sync_history_starts_at_week_one(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Tier 2: no platform dates and nothing to compare a first sighting against.

    SPEC §3.4: "Where the platform supplies no enrollment dates — most supply none
    — a student counts as enrolled from the section's start date." A section with
    no `nrps_call` rows at all is the state seeded data is in, and the work order
    settles it as tier 2 outright.

    **The mutation this kills:** a tier-3 rule that fires without a sync to compare
    against — reading `started_on` alone as "the date they were added" — which
    would credit this student from the section's start date resolved into a week
    and would answer differently the moment a seeded `started_on` fell mid-term.
    """
    world = grading_world.build()
    student = world.student("e3-03-tier-2")
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    score = world.score_for(student, settings=window_settings)

    assert score.total == weeks_from(1), (
        f"An undated member of a section with no roster-sync history has a denominator of "
        f"{score.total} rather than {weeks_from(1)}, which is every elapsed week."
    )
    assert score.ledger == ledger_from(
        1
    ), f"The ledger reads:\n{score.ledger}\n\nrather than:\n{ledger_from(1)}"


def test_a_member_first_seen_after_the_sections_first_sync_starts_at_the_week_of_that_sighting(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Tier 3, the inside of the line: first seen on the Sunday that week 3's window closes.

    The section's earliest `nrps_call` is on 17 October and this student was first
    seen on the 18th, so they are a late add the platform never dated. The start of
    18 October in `America/New_York` is 04:00Z, and course week 3's window closes
    at 03:59:59Z on the 19th — so that week was still open on the day they
    appeared, and it counts.

    **The mutation this kills:** resolving `started_on` at the *end* of its day, or
    in UTC rather than the institution timezone. Either moves this student off the
    week by hours, and the pair with the test below is what makes that visible.
    """
    world = grading_world.build()
    world.roster_sync_at(FIRST_SYNC_AT)
    student = world.student("e3-03-tier-3-inside", started_on=THE_SUNDAY_THAT_WEEK_CLOSES_ON)
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    score = world.score_for(student, settings=window_settings)

    assert score.total == weeks_from(BOUNDARY_WEEK), (
        f"A student first seen on {THE_SUNDAY_THAT_WEEK_CLOSES_ON}, in a section first synced on "
        f"{THE_DAY_OF_THE_FIRST_SYNC}, has a denominator of {score.total} rather than "
        f"{weeks_from(BOUNDARY_WEEK)}. Course week {BOUNDARY_WEEK}'s window was still open on that "
        "day."
    )
    assert score.ledger == ledger_from(
        BOUNDARY_WEEK
    ), f"The ledger reads:\n{score.ledger}\n\nrather than:\n{ledger_from(BOUNDARY_WEEK)}"


def test_a_member_first_seen_the_day_after_a_window_closed_is_not_credited_with_that_week(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Tier 3, the outside of the line: first seen on the Monday, one second too late.

    Start of 19 October in `America/New_York` is 04:00:00Z; course week 3's window
    closed at 03:59:59Z that morning. One second decides the week, and the two
    tests are one calendar day apart.

    **The mutation this kills:** a comparison that uses the day only — `started_on`
    against the window's closing *date* — which reads both this case and the one
    above as "the 18th/19th are in week 3's span" and credits both.
    """
    world = grading_world.build()
    world.roster_sync_at(FIRST_SYNC_AT)
    student = world.student("e3-03-tier-3-outside", started_on=THE_MONDAY_AFTER)
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    score = world.score_for(student, settings=window_settings)

    assert score.total == weeks_from(BOUNDARY_WEEK + 1), (
        f"A student first seen on {THE_MONDAY_AFTER} has a denominator of {score.total} rather "
        f"than {weeks_from(BOUNDARY_WEEK + 1)}. Course week {BOUNDARY_WEEK}'s window closed at "
        "23:59:59 the evening before, in the institution's timezone."
    )
    assert score.ledger == ledger_from(
        BOUNDARY_WEEK + 1
    ), f"The ledger reads:\n{score.ledger}\n\nrather than:\n{ledger_from(BOUNDARY_WEEK + 1)}"


def test_a_member_the_sections_first_sync_already_contained_is_not_a_late_add(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Tier 3's *selection* boundary: first seen on the day of the first sync is not "later than".

    SPEC §3.4 accepts the consequence in as many words: "A late add the platform
    never dated and the first sync already contained cannot be told from a day-one
    student; that under-credit is accepted, because no rule can recover data the
    platform never supplied." So this student is tier 2 and is credited with every
    elapsed week, including four that closed before anyone had ever synced the
    section.

    **The mutation this kills:** `started_on >= the first sync's day` instead of
    `>`, which would make every student in the first sync a late add dated by that
    sync — silently deleting most of the term from most denominators. It is one
    character, and the test below is the same date one day later, where the tier
    does fire.
    """
    world = grading_world.build()
    world.roster_sync_at(FIRST_SYNC_AT)
    student = world.student("e3-03-tier-3-selection", started_on=THE_DAY_OF_THE_FIRST_SYNC)
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    score = world.score_for(student, settings=window_settings)

    assert score.total == weeks_from(1), (
        f"A student first seen on {THE_DAY_OF_THE_FIRST_SYNC}, the same day as the section's "
        f"earliest roster sync, has a denominator of {score.total} rather than {weeks_from(1)}. "
        "They are not 'first seen in a roster sync later than their section's first sync', so tier "
        "2 applies and the denominator starts at course week 1."
    )
    assert score.ledger == ledger_from(
        1
    ), f"The ledger reads:\n{score.ledger}\n\nrather than:\n{ledger_from(1)}"


def test_the_platforms_own_date_decides_even_where_a_later_sync_would_say_otherwise(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """Tier 1 is consulted before tier 3, and the two are made to disagree.

    The platform says this student was enrolled from before course week 1's window
    closed; Pulse's own first sighting is a month later, in a section whose first
    sync is later still. §3.4 dates the denominator "from NRPS enrollment data" and
    falls back to the observed record only "where the platform supplies no
    enrollment dates", so the platform's answer wins and the student is credited
    with every elapsed week.

    **The mutation this kills:** the tiers evaluated in any other order — a rule
    that asks "was this student first seen after the first sync?" before asking
    whether the platform dated them, which is the more natural way to write the
    condition and gives this student one week instead of four.
    """
    world = grading_world.build()
    world.roster_sync_at(FIRST_SYNC_AT)
    student = world.student(
        "e3-03-tier-precedence",
        started_on=THE_MONDAY_AFTER,
        lms_window_start=world.closes_at(1) - A_MOMENT,
    )
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    score = world.score_for(student, settings=window_settings)

    assert score.total == weeks_from(1), (
        f"A student the platform dated inside course week 1, whose first sighting is "
        f"{THE_MONDAY_AFTER} and whose section was first synced on {THE_DAY_OF_THE_FIRST_SYNC}, "
        f"has a denominator of {score.total} rather than {weeks_from(1)}. Tier 1 is the platform's "
        "own window and it is consulted first; tier 3 exists for members the platform never dated."
    )
    assert score.ledger == ledger_from(
        1
    ), f"The ledger reads:\n{score.ledger}\n\nrather than:\n{ledger_from(1)}"
