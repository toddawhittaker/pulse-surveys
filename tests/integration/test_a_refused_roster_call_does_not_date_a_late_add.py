"""A call that read no roster is not the sync a member was first seen in — E3-08's boundary round, LO-M4.

R5's ruling: "`_first_sync_day` counts only `nrps_call` rows from calls that
actually read a roster: filter `members_seen IS NOT NULL`."

**What the defect is.** SPEC §3.4's third tier credits an undated member "from the
week of that sync" when they first appear in a roster sync later than their
section's first, and ADR 0131 makes the comparison against the section's
**earliest** `nrps_call.called_at`. E3-02 and E1-11 both write a row for a call
that never read anything: a refused token, an address the fetched-address rules
declined, a transport that never connected — `members_seen` NULL, which ADR 0129
and ADR 0096 each give exactly that meaning.

So a section whose very first contact with a platform *failed* has an `nrps_call`
row dated before every successful one. Under the unfiltered rule that row is the
"first sync", and every undated member the first **real** roster brought in is
then "later than the first sync" — so every one of them is treated as a late add
and dated from the week their section's roster was actually read. A section whose
platform refused a token on the Monday of week one loses week one from every
undated member's denominator, permanently, and nothing anywhere reports it.

**Why it is a boundary and not an edge.** The failing first call is the *common*
case for a new registration: a tool is registered, the first scheduled sync runs
before the credentials are right, and it fails. That is a Tuesday, not an
exotic state.

**The pair, and neither half means anything alone.** A refusal row before the real
sync must not move anybody's tier; and a *successful* row in the same place must
move it. Without the second half this module passes against a build that ignores
`nrps_call` entirely and treats every undated member as tier 2 — which is a
different defect with the same green.

**Nothing here computes a denominator.** Both halves read
`participation_scores`' own answer for two students who differ in one value, and
the expectation is stated as "the same as the control's" rather than as a number
this file worked out — E3-03's suites own what the formula computes, and
`test_the_first_enrolled_week_follows_the_three_tiers.py` owns the tier rule
itself.

**Which failure a red here is.** Expected **RED** before the filter lands, on the
first test's assertion that the late add kept tier 2 — the refusal row will have
dated them. The second test is expected **green** both before and after, and is
here as the control that says the tier fires at all.
"""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from fixtures.grading import GradingWorld, ledger_of

pytestmark = pytest.mark.integration

# The same six-week cohort and four elapsed weeks the tier module uses, so the two
# read against one calendar.
ELAPSED_WEEKS = 4
ITEMS_PER_WEEK = 5

# The instant the section's roster was really read, and the institution-timezone
# day it falls on: 11:00 on Saturday 17 October, EDT. Transcribed from
# `test_the_first_enrolled_week_follows_the_three_tiers.py`, which checks both
# against the seeded calendar.
THE_REAL_SYNC_AT = datetime(2026, 10, 17, 15, 0, tzinfo=UTC)

# A refused call, a fortnight earlier — before every course week this module
# scores. **Earlier is the whole point**: tier 3 compares against the section's
# *earliest* row, so a refusal that sorts after the real read changes nothing and
# would make this test green against the defect.
THE_REFUSED_CALL_AT = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)

# The day the undated students were first seen: the day of the real sync. Under
# §3.4 that is *not* "later than" the section's first sync, so they are tier 2 and
# keep every elapsed week — provided the refused call does not count as the first
# sync. If it does, this day is a fortnight later than it and they become late
# adds credited from week 3.
THE_DAY_OF_THE_REAL_SYNC = date(2026, 10, 17)

# The day a genuine late add is first seen, for the control below: one day after
# the real sync, which is the side of §3.4's "later than" where tier 3 does fire.
THE_DAY_AFTER = date(2026, 10, 18)


def ledger_from(first_week: int) -> str:
    """The ledger of a student who answered nothing, credited from `first_week` on."""
    return ledger_of([(week, 0, ITEMS_PER_WEEK) for week in range(first_week, ELAPSED_WEEKS + 1)])


def weeks_from(first_week: int) -> int:
    """How many items a student credited from `first_week` has in their denominator."""
    return (ELAPSED_WEEKS - first_week + 1) * ITEMS_PER_WEEK


def test_a_refused_call_before_the_real_sync_leaves_an_undated_member_at_week_one(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """LO-M4: a row with `members_seen` NULL is not a sync anybody was seen in.

    Two `nrps_call` rows: a refused one a fortnight before the roster was really
    read, and the real read itself. An undated student first seen on the day of the
    real read is **not** "first seen in a roster sync later than their section's
    first sync" — §3.4's tier 2 — and keeps every elapsed week.

    **The mutation this kills:** `_first_sync_day` taking `min(called_at)` over
    every row, which is the state LO-M4 found. The refused call is then the
    section's "first sync", the real read is a fortnight "later", and every undated
    member the first working roster brought in is silently re-dated as a late add.
    A section whose platform refused a token on the Monday of week one loses week
    one from every undated member's denominator for the rest of the term.

    **Why the refusal is dated *before* the real read.** Tier 3 compares against
    the section's earliest row, so a refusal that sorted after the real one would
    change nothing and this test would be green against the defect it is written
    for. The fortnight is four orders of magnitude more than any clock skew.

    **The premise is asserted rather than assumed.** Both rows must be there, and
    the refusal must be the earlier of the two — a fixture that wrote one row, or
    wrote them the other way round, would make this a tier-2 test with a tier-2
    expectation and it would pass against anything.

    **The control is the test below**, where a student one day later *is* dated by
    the real sync. Without it, "the refusal did not move the tier" is satisfied by
    a build that reads no `nrps_call` row at all.
    """
    world = grading_world.build()
    refused = world.roster_sync_at(THE_REFUSED_CALL_AT, members_seen=None)
    real = world.roster_sync_at(THE_REAL_SYNC_AT)
    assert refused is not None and real is not None, (
        "This test needs both an refused call row and a real one; the fixture seeded "
        f"{refused!r} and {real!r}. With one of them missing the comparison below is about a "
        "section with a single sync, which is not the state LO-M4 is about."
    )
    assert THE_REFUSED_CALL_AT < THE_REAL_SYNC_AT, (
        "The refused call is not the earlier of the two rows, so it cannot be what a "
        "`min(called_at)` over every row would pick — and this test would pass against the very "
        "rule it exists to refuse."
    )

    student = world.student("e3-08-after-a-refusal", started_on=THE_DAY_OF_THE_REAL_SYNC)
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    score = world.score_for(student, settings=window_settings)

    assert score.total == weeks_from(1), (
        f"An undated student first seen on {THE_DAY_OF_THE_REAL_SYNC} — the day the section's "
        f"roster was actually read — has a denominator of {score.total} rather than "
        f"{weeks_from(1)}.\n\n"
        f"The section also carries a **refused** call dated {THE_REFUSED_CALL_AT.date()}, with "
        "`members_seen` NULL: a call that read no roster at all. E3-08's boundary round (LO-M4) "
        "narrows tier 3's comparison to rows that actually read one, because a call that saw no "
        "member cannot be the sync a member was first seen in. Counting it makes the real read a "
        "fortnight 'later than the first sync', so every undated member the first working roster "
        "brought in is re-dated as a late add — and a new registration whose first scheduled sync "
        "ran before its credentials were right is the ordinary way a section gets into this state."
    )
    assert score.ledger == ledger_from(1), (
        f"The ledger reads:\n{score.ledger}\n\nrather than:\n{ledger_from(1)}\n\nThe percentage "
        "can coincide across two tiers when a student answered nothing; the ledger names the weeks "
        "and cannot."
    )


def test_a_real_sync_still_dates_a_member_first_seen_after_it(
    grading_world: GradingWorld, clock_overrides: Any, window_settings: Any
) -> None:
    """The control: the tier still fires, and the filter did not switch it off.

    The same two rows, and a student first seen one day *after* the real read. §3.4
    dates them from the week of that sync, so their denominator starts at the
    course week whose window closes on or after 17 October — not at week 1.

    **The mutation this kills:** the filter written as something that excludes
    every row — `members_seen IS NULL`, inverted; or a narrowing to some status the
    real read does not carry either. Tier 3 then never fires, every undated member
    is tier 2, and the test above passes for exactly the wrong reason. That is the
    failure mode a one-sided fix produces, and this is the half that sees it.

    **The expected week is not stated as a literal here.** What is asserted is that
    the denominator is *smaller* than a day-one member's — the tier fired — while
    `test_the_first_enrolled_week_follows_the_three_tiers.py` owns which week it
    lands on and asserts that boundary from both sides. Two modules pinning one
    week number would be one rule in two inventories.
    """
    world = grading_world.build()
    world.roster_sync_at(THE_REFUSED_CALL_AT, members_seen=None)
    world.roster_sync_at(THE_REAL_SYNC_AT)

    late = world.student("e3-08-genuine-late-add", started_on=THE_DAY_AFTER)
    world.elapsed_through(clock_overrides, ELAPSED_WEEKS)

    score = world.score_for(late, settings=window_settings)

    assert score.total < weeks_from(1), (
        f"A student first seen on {THE_DAY_AFTER}, the day after the section's roster was really "
        f"read, has a denominator of {score.total} — the same as a day-one member's "
        f"({weeks_from(1)}). §3.4's third tier credits them 'from the week of that sync', so some "
        "weeks are not theirs.\n\n"
        "This is the half that says LO-M4's filter narrowed the rule rather than switched it off. "
        "A filter written the wrong way round — or one narrowing to a status a successful read "
        "does not carry — makes tier 3 fire for nobody, and the test above then passes because "
        "*every* member is tier 2."
    )
    assert score.total > 0, (
        f"The late add's denominator is {score.total}. A student credited with no elapsed week at "
        "all has no score to post rather than a small one (§3.4), which is a different state from "
        "the one this control is about — and it would satisfy the comparison above for a reason "
        "that has nothing to do with the tier."
    )
