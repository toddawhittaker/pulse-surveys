"""The roster sync's "first seen" date is the clock service's day — E2-04, criterion 1.

`app.services.roster_sync` stamps `enrollment.started_on` with the day it first saw
a member: SPEC §3.4's late-add rule reads that column — "a student who first
appears in a roster sync later than their section's first sync counts from the week
of that sync" — and E3's participation denominator is computed from it. Before
E2-04 the sync computed that day with its own
`datetime.now(ZoneInfo(settings.institution_timezone)).date()`; E2-04 routes it
through `clock.today(...)`, so a developer who has moved the clock forward can
drive a late add by hand instead of waiting three weeks for one.

**This is a scheduling read, and its two neighbours in the same module are not.**
The sync's NRPS debounce window and its call-log instants stay on real time — they
are protocol and observability facts, not calendar ones, and E2-04's ADR lists them
among the clocks the service does not touch. Nothing here asserts about those; the
line between them is the ADR's to draw and the review's to check.

**The member this sync serves carries no enrollment window**, deliberately. ADR
0048's extension is the platform's own dates and the sync stores them verbatim
(`tests/integration/test_the_roster_sync_records_enrollment_windows.py` is the
module that owns that distinction); `started_on` is Pulse's own record of when it
first saw the member, and it is the only one of the four columns a clock could
possibly reach.

**The environment is stated in the test body** (`docs/MISTAKES.md` entry 40): the
override applies only in development, and a case that let the variable default
would stop proving anything the day `.env.example` changed.
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fixtures.clock import DEVELOPMENT, ENVIRONMENT_VARIABLE

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# The pretended instant. Five years out, so it cannot be confused with the day a
# sync would stamp from the system clock by any band a test could choose
# (`docs/MISTAKES.md` entry 30).
PRETEND_NOW = datetime(2031, 3, 14, 10, 30, tzinfo=UTC)

# The widest offset any IANA zone carries, either way. The assertion below accepts
# any of the three dates the overridden instant could fall on, because which zone
# `today` resolves in is asserted directly on the service in
# `tests/integration/test_the_clock_service_reads_a_development_override.py` and
# does not need pinning a second time here (`docs/MISTAKES.md` entry 13).
WIDEST_ZONE_OFFSET = timedelta(hours=14)


def days_the_pretend_instant_could_fall_on() -> set[Any]:
    """Every calendar date the overridden instant could be, in any institution zone."""
    return {
        (PRETEND_NOW - WIDEST_ZONE_OFFSET).date(),
        PRETEND_NOW.date(),
        (PRETEND_NOW + WIDEST_ZONE_OFFSET).date(),
    }


def days_a_real_clock_could_stamp() -> set[Any]:
    """Every calendar date a sync reading the system clock could stamp right now."""
    now = datetime.now(UTC)
    return {
        (now - WIDEST_ZONE_OFFSET).date(),
        now.date(),
        (now + WIDEST_ZONE_OFFSET).date(),
    }


@pytest.fixture
def run_a_sync(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
) -> Any:
    """Serve one membership container at the section's address and sync it.

    The same three lines
    `tests/integration/test_the_roster_sync_records_enrollment_windows.py` runs its
    own cases through. A second copy rather than a shared fixture because that
    module is this suite's proven-green baseline for the sync, and moving its
    fixture out would put a diff on the baseline inside the pull request that uses
    it as one — the reason `tests/e2e/support/doors.ts` gives for leaving the six
    existing specs alone. If a third sync suite arrives, that is when it moves into
    `tests/fixtures/` (`docs/MISTAKES.md` entry 13).
    """

    def run(members: Any, size: int = 5) -> None:
        service_wire.serve(compose_a_roster(synced_section, members, size))
        roster_sync.call(
            roster_sync.sync_one_section,
            session=committed_rows.session,
            section_id=synced_section.id,
            http=service_wire.session(),
        )
        committed_rows.commit()

    return run


def test_a_member_first_seen_under_an_override_is_stamped_with_the_overridden_day(
    committed_clock_overrides: Any,
    monkeypatch: pytest.MonkeyPatch,
    run_a_sync: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
) -> None:
    """Criterion 1 for the roster sync's call site: `started_on` is the clock's day.

    **The mutation this kills**: the sync's own `_today(settings)` going on reading
    `datetime.now(...)`, which is HEAD. Under it a developer who moves the clock
    to next month and re-syncs gets a member stamped with today, and every late-add
    scenario SPEC §3.4 describes becomes untestable by hand — which is the whole
    reason E2-04 exists.

    **The near miss it must not pass on**: a sync that stamps the *section's* start
    date, or the platform's window, rather than the day it ran. The member served
    here carries no enrollment window at all, so there is no platform date for a
    wrong implementation to reach for, and the section's own calendar is years away
    from the overridden day.

    **The real day is asserted to be outside the accepted band first.** "The stamp
    is the overridden day" would be satisfied by a stamp of today if the two ever
    coincided, and five years apart they cannot — but the assertion is what says so
    rather than the reader having to work it out (`docs/MISTAKES.md` entry 3).

    `committed_clock_overrides` is first in the signature so its teardown runs
    after the sync's own connections are closed.
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, DEVELOPMENT)
    assert os.environ[ENVIRONMENT_VARIABLE] == DEVELOPMENT, (
        f"`{ENVIRONMENT_VARIABLE}` is {os.environ.get(ENVIRONMENT_VARIABLE)!r} at the moment this "
        "sync runs. The override applies only where the environment is exactly the development "
        "name, so under any other value this case would assert that a clock did not move and "
        "would pass against a sync that never read one."
    )

    expected = days_the_pretend_instant_could_fall_on()
    real = days_a_real_clock_could_stamp()
    assert not expected & real, (
        f"The days the overridden clock could name ({sorted(expected)}) overlap the days the "
        f"system clock could name ({sorted(real)}). The two have to be disjoint, or a sync reading "
        "either clock satisfies the assertion below."
    )

    committed_clock_overrides.set(pretend_now=PRETEND_NOW, anchored_at=datetime.now(UTC))

    subject = a_subject("clock")
    run_a_sync([roster_contract.member(subject)])

    written = roster_rows.enrollments_for(subject)
    assert len(written) == 1, (
        f"The member {subject!r} has {len(written)} enrollment rows and this test is about one: "
        f"{[dict(row) for row in written]}. Without exactly one row there is nothing whose "
        "`started_on` this case can be about."
    )

    stamped = written[0][roster_contract.started_on_column]
    assert stamped in expected, (
        f"The sync stamped `{roster_contract.started_on_column}` {stamped!r}. The clock is "
        f"overridden to {PRETEND_NOW!r}, so the day it first saw this member is one of "
        f"{sorted(expected)}; the days the system clock could name are {sorted(real)}. That column "
        "is what SPEC §3.4's late-add rule reads and what E3's participation denominator starts "
        "from, so a sync stamping the real day on an overridden stack makes every late add "
        "impossible to drive by hand."
    )
