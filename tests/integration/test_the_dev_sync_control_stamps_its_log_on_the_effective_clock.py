"""The development sync control writes its call log on the pretended clock, and nothing else does — E3-08.

**What this protects, and why the exit drive cannot protect it.** ADR 0142's
third decision: "`sync_section`, `sync_all_rosters` and `_record_call` take an
optional `called_at`; every production caller omits it and gets
`datetime.now(UTC)`. The development control reads `clock.now` once and passes
it, which bounds a drive's `first_sync_day` at the first dev-sync instant and
makes every tier deterministic whatever the real date is."

That last clause is the whole point, and it is exactly the part
`tests/e2e/exit-grade-passback.spec.ts` cannot check. SPEC §3.4's third tier
credits a member who first appears in a later sync "from the week of that sync",
and the comparison behind it reads a section's earliest `nrps_call.called_at`
against enrollment dates written from `app.services.clock`. Those are two clock
currencies (ADR 0109 lists the call log among the instants the development
override deliberately does not move), so the drive's tier-3 row gets the right
answer for the wrong reason on any real date that happens to precede the
pretended one — which every real date does today. **The mutation battery measured
that:** the control stamping `datetime.now(UTC)` instead of the effective clock
survives the entire six-position drive, and would go on surviving it until a real
2026-10-05 made the two orderings disagree. A protection that only starts working
next month is not a protection; this module is the one that fails on that
mutation **today**.

**The mutation each direction kills.**

  1. *The development control stamps `datetime.now(UTC)`* — the row it writes then
     sits on the real axis, `first_sync_day` becomes the day CI happened to run,
     and §3.4's tier arithmetic in the exit drive silently depends on the
     calendar. Killed by the first test, which stands the clock eighteen months
     ahead of any date this suite can really be run on and reads the stamp.
  2. *The fix applied one level too wide* — every `nrps_call` moved onto the
     effective clock, or a clock threaded into `roster_sync` itself. That is the
     opposite defect and ADR 0142 rejected it in as many words: it "would move an
     observability instant in production — a §6.1 console answering 'when was this
     section called' with a pretended time — which is exactly what ADR 0109 lists
     this log as exempt from". Killed by the second test, which runs the ordinary
     entry point while the identical override stands and requires real time.

Neither test means much alone: the first is satisfied by a build that put every
sync on the pretended clock, and the second by one that put none of them there.
Together they say the exception is exactly one caller wide, which is the whole of
what decision 3 claims.

**Neither test asserts that a roster was read.** What is under test is the
instant a call row carries, not what the call returned — and
`tests/integration/test_the_roster_sync_refuses_an_address_it_was_told_to_fetch.py`
establishes that the log records attempts the tool decided not to make as well as
ones that were answered ("the refused page is a call the tool decided not to
make, and it is a distinct row from the first page's 200"). So `response_code` is
deliberately not read here, and a row is required to *exist* before its timestamp
is judged — an assertion about "the newest row's stamp" over an empty set is the
plainest form of `docs/MISTAKES.md` entry 3.

**The environment.** `dev_console_tool` builds the tool through `tool_doors` over
`configured_env`'s documented values (`docs/MISTAKES.md` entry 40) and
development is required twice over: it is the only environment where the clock
override applies at all (ADR 0109 part 4) and the only one where the `/dev`
surface is served.

**Which failure a red here is.** `declared_roster_sync_path` is a plain call in
each test body, so a tree with no `DEV_ROSTER_SYNC_PATH` reports a FAILED naming
the deliverable rather than an ERROR in a fixture (`docs/MISTAKES.md` entry 44).
Both tests are expected **green** on the tree E3-08 leaves behind, and both
**red** under the mutation named above.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fixtures.dev_console import (
    DEV_MODULE,
    ORIGIN_HEADER,
    redirected_to_the_console,
    same_origin_of,
)
from fixtures.line_item_creation import named_in

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `synced_section`, `roster_rows`, `roster_sync`, `roster_contract`,
# `service_wire` and `compose_a_roster` come from `tests/fixtures/roster_sync.py`;
# `committed_clock_overrides` from `tests/fixtures/clock.py`; `dev_console_tool`
# from `tests/fixtures/dev_console.py`. All are reached as fixtures rather than
# imported, for the reason every module in this suite gives: an import of a
# fixtures module by name depends on where pytest put `tests/` on `sys.path`, and
# an import error is not a red.

# ADR 0142 decision 2's path and the constant that must hold it, on E3-07's
# pattern for `DEV_PASSBACK_PATH`: the console's own form and every test that
# drives the control address one value, so a rename is deliberate everywhere.
DEV_ROSTER_SYNC_PATH = "/dev/roster-sync"
ROSTER_SYNC_PATH_NAME = "DEV_ROSTER_SYNC_PATH"

ROSTER_SYNC_PATH_IS_OWED = (
    f"E3-08's work order puts `{ROSTER_SYNC_PATH_NAME} = {DEV_ROSTER_SYNC_PATH!r}` in "
    f"`{DEV_MODULE}` beside `DEV_PASSBACK_PATH`, and registers a `DevControlRoute` there: "
    "development-only, POST-only, same-origin `Origin` check, runs the roster sync for every "
    "registered section synchronously and answers 303 back to the console (ADR 0142, decision 2). "
    "The constant is named rather than the string being written into the route."
)

# **The pretended instant, and it is chosen to be unreachable by accident.**
# Eighteen months past any date this suite can really be run on, so a stamp taken
# from `datetime.now(UTC)` and a stamp taken from the effective clock are not
# merely different — they are different by more than a year, which no rounding,
# zone conversion or offset drift can close. A pretended instant a few days out
# would be a test whose answer changed with the calendar, which is the very defect
# it exists to stop.
PRETEND_NOW = datetime(2028, 3, 9, 12, 0, tzinfo=UTC)

# How far from the instant it means a stamp may land. ADR 0109 makes the
# development clock an **offset** rather than a freeze, so the effective now goes
# on advancing from the moment the override was anchored: the row this control
# writes carries `PRETEND_NOW` plus however long the request took. Five minutes is
# four orders of magnitude more than that and eleven orders less than the gap
# between the two clocks, so it cannot be the thing that decides either test.
A_GENEROUS_MARGIN = timedelta(minutes=5)

# How far apart the two clocks must be for a stamp to be attributable to one of
# them rather than the other. Thirty days: shorter than the eighteen-month gap by
# a wide margin, and longer than any offset drift, retry or zone error.
UNMISTAKABLY_FAR = timedelta(days=30)


def declared_roster_sync_path() -> str:
    """`app.api.dev.DEV_ROSTER_SYNC_PATH`, required to be the value ADR 0142 settles.

    A plain function called from a test body, never a fixture: on a tree without
    the control each test here must go red as a FAILED naming the deliverable
    rather than as an ERROR in somebody's setup (`docs/MISTAKES.md` entry 44).
    """
    import importlib

    declared = named_in(
        importlib.import_module(DEV_MODULE), ROSTER_SYNC_PATH_NAME, ROSTER_SYNC_PATH_IS_OWED
    )
    assert declared == DEV_ROSTER_SYNC_PATH, (
        f"`{DEV_MODULE}.{ROSTER_SYNC_PATH_NAME}` is {declared!r} and ADR 0142 settles "
        f"{DEV_ROSTER_SYNC_PATH!r}. The console's form, the exit drive's spec and this module all "
        "address that one value."
    )
    return str(declared)


def call_rows(roster_rows: Any, section_id: Any) -> dict[Any, dict[str, Any]]:
    """Every `nrps_call` row for one section, keyed by its own primary key.

    Keyed rather than counted, so "which rows are new" is a set difference and not
    an assumption about ordering — SPEC §6.1 puts a row per HTTP call and says
    nothing that would let this module predict how many a single sync makes.
    """
    key = roster_rows.key("nrps_call")
    return {row[key]: dict(row) for row in roster_rows.calls_for(section_id)}


def the_row_this_sync_wrote(
    roster_rows: Any,
    section_id: Any,
    before: dict[Any, dict[str, Any]],
    roster_contract: Any,
    what: str,
) -> datetime:
    """The `called_at` of a call row that was not there before, or a failure saying there is none.

    **The non-vacuity guard, and it is the load-bearing half of this module**
    (`docs/MISTAKES.md` entry 3). Every assertion below is of the form "the stamp
    is near one clock and far from the other", and both halves of that are
    satisfied perfectly by no stamp at all. So the row is required first, and the
    message names the two things its absence would mean.

    Where a sync wrote more than one row — a walk over several pages is several
    calls — the earliest is answered, because that is the one §3.4's tier-3
    comparison reads (`min(nrps_call.called_at)` for the section) and it is the
    one the drive's determinism actually rests on.
    """
    after = call_rows(roster_rows, section_id)
    written = [after[key] for key in set(after) - set(before)]
    if not written:
        pytest.fail(
            f"{what} left no new `nrps_call` row for this section. It held {len(before)} rows "
            f"before and holds {len(after)} now.\n\n"
            "Two things look like this and they need different fixes. Either the control did not "
            "run the sync at all — in which case the timestamp assertions below are about nothing "
            "and this test is reporting a control that does not work rather than one that stamps "
            "the wrong clock. Or the sync could not begin: SPEC §6.1 logs a row per HTTP call and "
            "`test_the_roster_sync_refuses_an_address_it_was_told_to_fetch.py` shows that even a "
            "call the tool *declined to make* is recorded, so no row at all means the walk stopped "
            "before it had an address to record against. If the second, this module needs the "
            "control to be reachable with a transport and a resolver the test supplies — a seam "
            "ADR 0142 does not name — and that is an interface question for the ticket rather than "
            "something to work around here."
        )
    stamps = sorted(row[roster_contract.called_at_column] for row in written)
    earliest = stamps[0]
    assert isinstance(earliest, datetime) and earliest.tzinfo is not None, (
        f"{what} wrote a call row whose `{roster_contract.called_at_column}` is {earliest!r}, which "
        "is not an aware datetime. ADR 0019 refuses a naive datetime at bind, so this is a column "
        "declared as something other than `AwareDateTime` — and every comparison below would then "
        "be between values in no particular zone."
    )
    return earliest.astimezone(UTC)


def stand_the_clock_far_ahead(committed_clock_overrides: Any) -> datetime:
    """Put the development clock eighteen months out, and answer the real instant it was anchored at.

    Both values are this test's own input; nothing about what any clock *answers*
    is decided here (`docs/MISTAKES.md` entry 30).
    """
    anchored_at = datetime.now(UTC)
    committed_clock_overrides.set(pretend_now=PRETEND_NOW, anchored_at=anchored_at)
    return anchored_at


# ---------------------------------------------------------------------------
# Direction 1 — the development control writes on the pretended clock.
# ---------------------------------------------------------------------------


def test_the_dev_sync_control_stamps_its_call_log_with_the_pretended_instant(
    synced_section: Any,
    roster_rows: Any,
    roster_contract: Any,
    committed_clock_overrides: Any,
    dev_console_tool: Any,
) -> None:
    """ADR 0142 decision 3: the row this control writes carries `clock.now`, not real now.

    One registered platform, one section carrying a roster address, the
    development clock stood at 2028-03-09, and a same-origin POST to
    `/dev/roster-sync`. The `nrps_call` row that appears must be stamped on the
    pretended clock.

    **The mutation this kills, and it is the battery's one measured survivor:**
    the control stamping `datetime.now(UTC)` — omitting `called_at`, or passing
    real time, or reading a clock that is not the development one. A drive's
    `first_sync_day` is then the day CI ran rather than the first dev-sync
    instant, and SPEC §3.4's tier-3 comparison — a section's earliest
    `nrps_call.called_at` against enrollment dates written from the effective
    clock — starts depending on the calendar. **That mutation survives the whole
    six-position exit drive today**, because every real date this suite can be run
    on still precedes the seeded term, so the pretended October sync is "later"
    than a log written now and the drive's answers come out right for the wrong
    reason. It stops surviving on a real 2026-10-05, which is a protection that
    begins after the epic ships.

    **Both halves of the stamp are asserted, and the second is the one that names
    the mutation.** Near the pretended instant, *and* far from real time. The
    first alone would pass a stamp that happened to be near both — impossible
    here, but the assertion should say what it means — and the second alone would
    pass any wrong instant at all as long as it was not today's.

    **The margin is not a fudge.** ADR 0109 makes the development clock an offset
    rather than a freeze, so the effective now advances from the anchor while the
    request runs: the stamp is `PRETEND_NOW` plus the duration of the sync. Five
    minutes is far more than that and far less than the eighteen months between
    the two clocks, so no plausible drift can decide this test either way.

    **The row is required to exist before its stamp is read**, and
    `the_row_this_sync_wrote` says why at length: "the stamp is near one clock and
    far from the other" is satisfied perfectly by no stamp at all.
    """
    declared = declared_roster_sync_path()
    before = call_rows(roster_rows, synced_section.id)
    anchored_at = stand_the_clock_far_ahead(committed_clock_overrides)

    client = dev_console_tool()
    answered = client.post(declared, headers={ORIGIN_HEADER: same_origin_of(client)})
    redirected_to_the_console(answered, f"`POST {declared}` with a same-origin `{ORIGIN_HEADER}`")

    stamped = the_row_this_sync_wrote(
        roster_rows,
        synced_section.id,
        before,
        roster_contract,
        f"`POST {declared}`",
    )

    assert stamped >= PRETEND_NOW, (
        f"The call row this control wrote is stamped {stamped.isoformat()} and the development "
        f"clock was standing at {PRETEND_NOW.isoformat()} when it ran. ADR 0109 makes the override "
        "an offset, so the effective now can only be at or after the pretended instant — a stamp "
        "before it did not come from that clock at all."
    )
    assert stamped - PRETEND_NOW < A_GENEROUS_MARGIN, (
        f"The call row is stamped {stamped.isoformat()}, which is {stamped - PRETEND_NOW} after "
        f"the pretended instant {PRETEND_NOW.isoformat()}. The offset advances by the duration of "
        f"one request, so anything beyond {A_GENEROUS_MARGIN} is a different clock rather than "
        "drift."
    )

    real_now = datetime.now(UTC)
    assert abs(stamped - real_now) > UNMISTAKABLY_FAR, (
        f"The call row this control wrote is stamped {stamped.isoformat()}, which is within "
        f"{UNMISTAKABLY_FAR} of real time ({real_now.isoformat()}) while the development clock "
        f"stood at {PRETEND_NOW.isoformat()} (anchored at {anchored_at.isoformat()}).\n\n"
        "**This is the mutation ADR 0142 decision 3 exists to stop**: the development control "
        "stamping `datetime.now(UTC)` rather than reading `clock.now` and passing it as "
        "`called_at`. With the log on the real axis, a drive's `first_sync_day` is the day CI "
        "happened to run, and SPEC §3.4's third tier — 'a student who first appears in a roster "
        "sync later than their section's first sync counts from the week of that sync' — compares "
        "that real day against enrollment dates written from the effective clock. The exit drive "
        "then gets its tier-3 row right or wrong according to the calendar, and it gets it right "
        "on every date this project can be run on today, which is why nothing else in the suite "
        "can see this."
    )


# ---------------------------------------------------------------------------
# Direction 2 — and nothing else does. ADR 0109's choice, in the other
# direction.
# ---------------------------------------------------------------------------


def test_a_production_sync_still_stamps_real_time_while_the_same_override_stands(
    synced_section: Any,
    roster_rows: Any,
    roster_contract: Any,
    roster_sync: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    committed_clock_overrides: Any,
) -> None:
    """The near miss: the ordinary entry point is untouched, under the identical clock.

    The same section and the same override, synced the way SPEC §7.3's hourly beat
    and the launch trigger sync it — `roster_sync.sync_one_section`, through
    `RosterSyncService.call`, which fills only the roles this test offers and so
    **omits `called_at` exactly as every production caller does**. The row must
    carry real time.

    **The mutation this kills is the fix applied one level too wide:** every
    `nrps_call` moved onto the effective clock, or a clock threaded into
    `roster_sync` so the service reads it for itself. ADR 0142 rejected both by
    name — the first "would move an observability instant in production, a §6.1
    console answering 'when was this section called' with a pretended time, which
    is exactly what ADR 0109 lists this log as exempt from"; the second because "a
    movable clock inside a service ADR 0109 keeps real is a standing invitation to
    read it somewhere else". A developer whose stack is standing in 2028 would
    then find every section's call history in 2028, and the §6.1 console would
    stop being able to say when anything actually happened.

    **This is the half that makes the other one mean something.** Read alone, the
    test above passes against a build that put *every* sync on the pretended clock
    — which is the wider defect, not the fix. Read alone, this one passes against
    a build that put none of them there, which is the mutation. The pair says the
    exception is exactly one caller wide, and that is the whole of ADR 0142's
    third decision.

    **The override is set before the sync and not cleared**, deliberately: a
    production path that stamps real time *because no override exists* would prove
    nothing at all. The row has to be written while the clock is demonstrably
    somewhere else.

    A roster is served on the wire so this call has somewhere to go and performs
    no name lookup — `tests/fixtures/roster_sync.py`'s standing rule that no test
    in this repository may resolve a hostname. Nothing is asserted about what came
    back: what is under test is the instant on the row.
    """
    before = call_rows(roster_rows, synced_section.id)
    stand_the_clock_far_ahead(committed_clock_overrides)

    service_wire.serve(compose_a_roster(synced_section, []))
    began = datetime.now(UTC)
    roster_sync.call(
        roster_sync.sync_one_section,
        session=committed_rows.session,
        section_id=synced_section.id,
        http=service_wire.session(),
    )
    committed_rows.commit()

    stamped = the_row_this_sync_wrote(
        roster_rows,
        synced_section.id,
        before,
        roster_contract,
        "The ordinary per-section sync",
    )

    ended = datetime.now(UTC)
    assert began - A_GENEROUS_MARGIN <= stamped <= ended + A_GENEROUS_MARGIN, (
        f"The ordinary sync wrote a call row stamped {stamped.isoformat()}, and the call ran "
        f"between {began.isoformat()} and {ended.isoformat()} in real time. ADR 0109 lists the "
        "call log among the instants the development override deliberately does not move, and ADR "
        "0142 keeps that true by giving `called_at` a default of `datetime.now(UTC)` that every "
        "production caller takes."
    )
    assert abs(stamped - PRETEND_NOW) > UNMISTAKABLY_FAR, (
        f"The ordinary sync wrote a call row stamped {stamped.isoformat()}, within "
        f"{UNMISTAKABLY_FAR} of the pretended instant {PRETEND_NOW.isoformat()} that the "
        "development clock was standing at.\n\n"
        "**This is the opposite defect from the one the test above guards**, and ADR 0142 rejected "
        "it in as many words: stamping every `nrps_call` on the effective clock 'would move an "
        'observability instant in production — a §6.1 console answering "when was this section '
        "called\" with a pretended time'. The exception belongs to the one development control "
        "that passes `called_at`; a service that reads a movable clock for itself has moved a "
        "production record, and a developer would find a section's whole call history in whatever "
        "year their stack was pretending it was."
    )
