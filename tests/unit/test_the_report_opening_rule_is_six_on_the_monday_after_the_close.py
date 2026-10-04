"""When a week's report opens, as a pure function — E5.1-05, criterion C6.

> **C6.** A week is unavailable at 05:59 and published at 06:00 Monday in the
> institution's time zone, on the effective clock. `published_course_weeks` and
> `instructor_report` share one predicate.

The owner's ruling of 2026-10-03, as the work order transcribes it: a week's report
opens at **the first Monday 06:00 in the institution's time zone that is strictly
later than the window's `closes_at`**. For the default rhythm (closes Sunday
23:59:59) that is the next morning; a window closing Monday 05:00 opens that same
day at 06:00; a window closing exactly Monday 06:00:00 opens the following Monday.

**The interface is the work order's, not this file's.** In
`backend/app/services/reporting.py`:

  - `REPORT_OPENS_AT` — the hour, `time(6, 0)`;
  - `report_opens_at(closes_at, *, zone)` — the instant above, timezone-aware;
  - `week_is_published(closes_at, *, now, zone)` — `now >= report_opens_at(...)`,
    the one predicate both readers call.

**This is where the exact-instant pairs live.** Through the effective clock a
boundary can only be stood on to the minute (ADR 0109: the clock drifts forward
while it is read), so 05:59:59.999999 against 06:00:00 is asserted here, on the
function, and the integration modules stand at 05:59:00 and 06:00:00.

**Every expected instant is a literal written by hand** (`docs/MISTAKES.md` entry
19), never computed with `datetime.combine` or with the rule under test. Each
literal's comment gives the wall time it stands for, so a reader can check it
against a calendar. The 2026 daylight-saving dates in `America/New_York` are
Sunday 8 March (spring forward, 02:00 becomes 03:00) and Sunday 1 November (fall
back, 02:00 becomes 01:00).

**The property test states the rule's consequences, not its construction.** Over
generated closes in several zones — two with daylight saving on different dates,
one with a half-hour shift, two without — the opening is a Monday at 06:00 local,
strictly after the close, no more than seven wall-clock days after it, and the
predicate flips exactly there. None of those produces an expected instant.

**Which failure a red is.** Today's tree has none of the three names, and they
are looked up inside each test body (`reporting_names`), so every test here is a
FAILED naming the missing symbol rather than a collection ERROR
(`docs/MISTAKES.md` entry 44).
"""

from datetime import UTC, datetime, time, timedelta
from importlib import import_module
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

REPORTING_MODULE = "app.services.reporting"
HOUR_NAME = "REPORT_OPENS_AT"
OPENS_NAME = "report_opens_at"
PUBLISHED_NAME = "week_is_published"

NEW_YORK = ZoneInfo("America/New_York")
HONOLULU = ZoneInfo("Pacific/Honolulu")

ONE_MICROSECOND = timedelta(microseconds=1)
MONDAY = 0

# ---------------------------------------------------------------------------
# The cases, by hand.
# ---------------------------------------------------------------------------

# An ordinary week, on daylight time throughout. Closes Sunday 18 October 2026
# 23:59:59 EDT; opens Monday 19 October 06:00 EDT.
ORDINARY_CLOSE = datetime(2026, 10, 19, 3, 59, 59, tzinfo=UTC)
ORDINARY_OPENS = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)
# 05:59:59.999999 EDT that Monday.
ORDINARY_LAST_UNPUBLISHED = datetime(2026, 10, 19, 9, 59, 59, 999999, tzinfo=UTC)

# The fall-back week. The window opened on Friday 30 October at 18:00 EDT
# (UTC-4) and closes Sunday 1 November 23:59:59 EST (UTC-5), the day daylight time
# ends. Opens Monday 2 November 06:00 EST, 11:00 UTC. A computation carrying the
# window's opening offset (EDT) would say 10:00 UTC, so 10:30 UTC — 05:30 EST — is
# the clock that tells the two apart.
FALL_BACK_CLOSE = datetime(2026, 11, 2, 4, 59, 59, tzinfo=UTC)
FALL_BACK_OPENS = datetime(2026, 11, 2, 11, 0, 0, tzinfo=UTC)
FALL_BACK_HALF_AN_HOUR_EARLY = datetime(2026, 11, 2, 10, 30, 0, tzinfo=UTC)

# The spring-forward week. Closes Sunday 8 March 2026 23:59:59 EDT — daylight time
# began at 02:00 that morning — and opens Monday 9 March 06:00 EDT, 10:00 UTC. A
# computation on standard time (the offset the window opened on, Friday 6 March)
# would say 11:00 UTC.
SPRING_FORWARD_CLOSE = datetime(2026, 3, 9, 3, 59, 59, tzinfo=UTC)
SPRING_FORWARD_OPENS = datetime(2026, 3, 9, 10, 0, 0, tzinfo=UTC)
# 05:59:59 EDT that Monday.
SPRING_FORWARD_A_SECOND_EARLY = datetime(2026, 3, 9, 9, 59, 59, tzinfo=UTC)

# A window closing on a Monday before six: Monday 19 October 2026 05:00 EDT. Opens
# the same morning at 06:00 EDT.
MONDAY_FIVE_CLOSE = datetime(2026, 10, 19, 9, 0, 0, tzinfo=UTC)
MONDAY_FIVE_OPENS = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)

# A window closing exactly at Monday 06:00:00 EDT, 19 October 2026. "Strictly
# later" makes its report open the following Monday, 26 October 06:00 EDT — still
# daylight time, so 10:00 UTC again.
MONDAY_SIX_CLOSE = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)
MONDAY_SIX_OPENS = datetime(2026, 10, 26, 10, 0, 0, tzinfo=UTC)
# 05:59:59.999999 EDT on Monday 26 October.
MONDAY_SIX_LAST_UNPUBLISHED = datetime(2026, 10, 26, 9, 59, 59, 999999, tzinfo=UTC)

# A window closing midweek: Wednesday 21 October 2026 12:00 EDT. Opens on the next
# Monday, 26 October 06:00 EDT — not the next morning.
WEDNESDAY_CLOSE = datetime(2026, 10, 21, 16, 0, 0, tzinfo=UTC)
WEDNESDAY_OPENS = datetime(2026, 10, 26, 10, 0, 0, tzinfo=UTC)

# The ordinary close read in `Pacific/Honolulu` (UTC-10, no daylight saving):
# 2026-10-19T03:59:59Z is Sunday 18 October 17:59:59 HST, so the report opens
# Monday 19 October 06:00 HST, 16:00 UTC.
HONOLULU_OPENS = datetime(2026, 10, 19, 16, 0, 0, tzinfo=UTC)


class Reporting(NamedTuple):
    hour: Any
    opens_at: Any
    is_published: Any


def reporting_names() -> Reporting:
    """The three names E5.1-05 adds, or a failure naming the ones missing.

    Looked up in the test body rather than imported at the top, so a tree
    without them reports a FAILED per test naming the symbol rather than one
    collection ERROR (`docs/MISTAKES.md` entry 44). The module itself exists on
    every tree since E4-03; an import error raised from inside it is not this
    file's subject and is left to propagate.
    """
    module = import_module(REPORTING_MODULE)
    missing = [
        name
        for name in (HOUR_NAME, OPENS_NAME, PUBLISHED_NAME)
        if getattr(module, name, None) is None
    ]
    if missing:
        pytest.fail(
            f"`{REPORTING_MODULE}` exposes no {missing}. E5.1-05's work order settles all three "
            "there: `REPORT_OPENS_AT = time(6, 0)`; `report_opens_at(closes_at, *, zone)`, the first "
            "Monday 06:00 in `zone` strictly after `closes_at`; and `week_is_published(closes_at, *, "
            "now, zone)`, the one predicate `instructor_report` and `published_course_weeks` share."
        )
    return Reporting(
        getattr(module, HOUR_NAME), getattr(module, OPENS_NAME), getattr(module, PUBLISHED_NAME)
    )


def assert_opens_at(closes_at: datetime, zone: ZoneInfo, expected: datetime, case: str) -> None:
    """`report_opens_at` answers `expected`, compared as an instant."""
    found = reporting_names().opens_at(closes_at, zone=zone)
    assert isinstance(found, datetime) and found.tzinfo is not None, (
        f"{case}: `report_opens_at` answered {found!r}, which is not a timezone-aware datetime. "
        "The opening is an instant compared with an aware clock; a naive one cannot be."
    )
    assert found == expected, (
        f"{case}: `report_opens_at({closes_at.isoformat()}, zone={zone.key})` answered "
        f"{found.isoformat()} ({found.astimezone(zone).isoformat()} local). The report opens at "
        f"{expected.isoformat()} ({expected.astimezone(zone).isoformat()} local): the first "
        "Monday 06:00 in the institution's zone strictly after the close."
    )


def assert_published(
    closes_at: datetime, now: datetime, zone: ZoneInfo, *, expected: bool, case: str
) -> None:
    """`week_is_published` answers `expected` at `now`."""
    found = reporting_names().is_published(closes_at, now=now, zone=zone)
    assert found is expected, (
        f"{case}: `week_is_published({closes_at.isoformat()}, now={now.isoformat()}, "
        f"zone={zone.key})` answered {found!r}; it should be {expected}. `now` is "
        f"{now.astimezone(zone).isoformat()} in that zone."
    )


# ---------------------------------------------------------------------------
# The hour.
# ---------------------------------------------------------------------------


def test_the_hour_a_report_opens_at_is_six_in_the_morning() -> None:
    """`REPORT_OPENS_AT` is 06:00, a wall time with no zone of its own.

    **The mutation this kills:** the hour as 05:00 or 07:00, or carrying a
    `tzinfo` — a zone fixed on the hour would make it 06:00 in that zone whatever
    the institution's is.
    """
    hour = reporting_names().hour
    assert hour == time(6, 0) and getattr(hour, "tzinfo", None) is None, (
        f"`REPORT_OPENS_AT` is {hour!r}. The owner's ruling of 2026-10-03 opens a week's report "
        "at 06:00 Monday in the institution's time zone, so the constant is `time(6, 0)` with no "
        "zone: the zone is the institution's, supplied at the call."
    )


# ---------------------------------------------------------------------------
# An ordinary Sunday close: the microsecond pair.
# ---------------------------------------------------------------------------


def test_a_sunday_close_opens_at_six_the_next_morning() -> None:
    """Sunday 23:59:59 EDT closes; Monday 06:00 EDT opens.

    **The mutation this kills:** the opening at the close (E4-07's rule), at
    06:00 UTC (02:00 EDT), or on the Monday after next.
    """
    assert_opens_at(ORDINARY_CLOSE, NEW_YORK, ORDINARY_OPENS, "A Sunday 23:59:59 EDT close")


def test_a_sunday_close_given_in_the_institutions_zone_opens_at_the_same_instant() -> None:
    """The close's own offset does not matter; the institution's zone does.

    The stored `timestamptz` comes back in UTC, but nothing promises it always
    will. The same instant written as `2026-10-18T23:59:59-04:00` must give the
    same opening.

    **The mutation this kills:** a computation on the close's own wall date or
    offset — `closes_at.date()` read without converting to `zone` first — which
    agrees with the UTC spelling of some closes and not others. Its near miss is
    the test above, the same instant in UTC.
    """
    in_zone = datetime(2026, 10, 18, 23, 59, 59, tzinfo=NEW_YORK)
    assert in_zone == ORDINARY_CLOSE, "The two spellings of the close are not one instant."
    assert_opens_at(in_zone, NEW_YORK, ORDINARY_OPENS, "The same close, given in EDT")


def test_a_microsecond_before_six_the_week_is_not_published() -> None:
    """05:59:59.999999 EDT on the Monday: unpublished. The red half of the pair.

    **The mutation this kills:** `closes_at < now` (E4-07's rule — the window
    closed six hours ago), an opening at 05:00, and rounding `now` to the second
    or minute. **Its pair** is the next test.
    """
    assert_published(
        ORDINARY_CLOSE,
        ORDINARY_LAST_UNPUBLISHED,
        NEW_YORK,
        expected=False,
        case="A microsecond before 06:00 EDT",
    )


def test_at_six_exactly_the_week_is_published() -> None:
    """06:00:00 EDT on the Monday: published. The ruling: "06:00:00 exactly is published".

    **The mutation this kills:** `now > opens` where the rule is `now >= opens`,
    and an opening an hour late (standard time on a daylight-time Monday).
    """
    assert_published(
        ORDINARY_CLOSE, ORDINARY_OPENS, NEW_YORK, expected=True, case="06:00:00 EDT exactly"
    )


# ---------------------------------------------------------------------------
# Daylight saving, both directions.
# ---------------------------------------------------------------------------


def test_the_fall_back_week_opens_at_six_standard_time() -> None:
    """Closes Sunday 1 Nov 2026 23:59:59 EST; opens Monday 2 Nov 06:00 EST, 11:00 UTC.

    **The mutation this kills:** a fixed offset — the window's opening offset
    (EDT) carried across the Sunday daylight time ended, which says 10:00 UTC.
    """
    assert_opens_at(FALL_BACK_CLOSE, NEW_YORK, FALL_BACK_OPENS, "The fall-back week")


def test_the_fall_back_week_is_not_published_at_ten_thirty_utc() -> None:
    """10:30 UTC on Monday 2 Nov is 05:30 EST: unpublished.

    **The mutation this kills:** the EDT-offset computation again, through the
    predicate — it opens the week at 10:00 UTC and calls this clock published.
    **Its pair** is the next test.
    """
    assert_published(
        FALL_BACK_CLOSE,
        FALL_BACK_HALF_AN_HOUR_EARLY,
        NEW_YORK,
        expected=False,
        case="05:30 EST on the fall-back Monday",
    )


def test_the_fall_back_week_is_published_at_eleven_utc() -> None:
    """11:00 UTC on Monday 2 Nov is 06:00 EST: published."""
    assert_published(
        FALL_BACK_CLOSE,
        FALL_BACK_OPENS,
        NEW_YORK,
        expected=True,
        case="06:00 EST on the fall-back Monday",
    )


def test_the_spring_forward_week_opens_at_six_daylight_time() -> None:
    """Closes Sunday 8 Mar 2026 23:59:59 EDT; opens Monday 9 Mar 06:00 EDT, 10:00 UTC.

    **The mutation this kills:** the window's opening offset (EST, Friday 6
    March) carried across the Sunday daylight time began, which says 11:00 UTC.
    """
    assert_opens_at(SPRING_FORWARD_CLOSE, NEW_YORK, SPRING_FORWARD_OPENS, "The spring-forward week")


def test_the_spring_forward_week_is_not_published_a_second_before_ten_utc() -> None:
    """09:59:59 UTC on Monday 9 Mar is 05:59:59 EDT: unpublished.

    **The mutation this kills:** an opening computed early — 06:00 UTC, or the
    close plus a fixed six hours (05:59:59 EDT, which this clock is). **Its
    pair** is the next test.
    """
    assert_published(
        SPRING_FORWARD_CLOSE,
        SPRING_FORWARD_A_SECOND_EARLY,
        NEW_YORK,
        expected=False,
        case="05:59:59 EDT on the spring-forward Monday",
    )


def test_the_spring_forward_week_is_published_at_ten_utc() -> None:
    """10:00 UTC on Monday 9 Mar is 06:00 EDT: published.

    **The mutation this kills:** the EST-offset computation, which opens the week
    at 11:00 UTC and calls this clock unpublished.
    """
    assert_published(
        SPRING_FORWARD_CLOSE,
        SPRING_FORWARD_OPENS,
        NEW_YORK,
        expected=True,
        case="06:00 EDT on the spring-forward Monday",
    )


# ---------------------------------------------------------------------------
# Closes that are not Sunday night.
# ---------------------------------------------------------------------------


def test_a_close_at_five_on_a_monday_opens_that_same_morning() -> None:
    """Closes Monday 05:00 EDT; opens Monday 06:00 EDT, the same day.

    **The mutation this kills:** "the Monday after the close's date" — the next
    Monday strictly after the close's *day* — which says 26 October.
    """
    assert_opens_at(MONDAY_FIVE_CLOSE, NEW_YORK, MONDAY_FIVE_OPENS, "A Monday 05:00 EDT close")


def test_a_close_at_six_exactly_on_a_monday_opens_the_following_monday() -> None:
    """Closes Monday 06:00:00 EDT; opens the following Monday 06:00 EDT.

    "Strictly later than the window's `closes_at`." **The mutation this kills:**
    `>=` where the ruling says strictly later — which opens the report at the
    close itself, before anyone could have read a final count. **Its near miss**
    is the 05:00 close above, which opens the same day.
    """
    assert_opens_at(MONDAY_SIX_CLOSE, NEW_YORK, MONDAY_SIX_OPENS, "A Monday 06:00:00 EDT close")


def test_a_monday_six_close_is_unpublished_at_its_close_and_until_the_next_monday() -> None:
    """Through the predicate: unpublished at the close and a microsecond before next Monday six.

    **The mutation this kills:** the non-strict rule again, seen as the
    predicate — it calls the week published at the instant it closes.
    """
    assert_published(
        MONDAY_SIX_CLOSE,
        MONDAY_SIX_CLOSE,
        NEW_YORK,
        expected=False,
        case="A Monday 06:00 EDT close, read at its own close",
    )
    assert_published(
        MONDAY_SIX_CLOSE,
        MONDAY_SIX_LAST_UNPUBLISHED,
        NEW_YORK,
        expected=False,
        case="A Monday 06:00 EDT close, read at 05:59:59.999999 EDT the following Monday",
    )


def test_a_close_at_six_on_a_monday_is_published_at_six_the_following_monday() -> None:
    """The pair of the test above: published at 06:00:00 EDT the following Monday."""
    assert_published(
        MONDAY_SIX_CLOSE,
        MONDAY_SIX_OPENS,
        NEW_YORK,
        expected=True,
        case="A Monday 06:00 EDT close, read at 06:00 EDT the following Monday",
    )


def test_a_midweek_close_opens_on_the_next_monday_not_the_next_morning() -> None:
    """Closes Wednesday 12:00 EDT; opens the next Monday 06:00 EDT.

    **The mutation this kills:** "06:00 the morning after the close", which is
    the same answer as the rule for every Sunday close and the wrong one for
    every other day.
    """
    assert_opens_at(WEDNESDAY_CLOSE, NEW_YORK, WEDNESDAY_OPENS, "A Wednesday 12:00 EDT close")


# ---------------------------------------------------------------------------
# The zone is the argument's.
# ---------------------------------------------------------------------------


def test_the_same_close_opens_at_six_in_the_zone_it_is_given() -> None:
    """The ordinary close, in `Pacific/Honolulu`: Monday 06:00 HST, 16:00 UTC.

    **The mutation this kills:** a zone written into the function —
    `America/New_York` or UTC — ignoring the `zone` argument. Its near miss is
    the ordinary New York case, which those mutations pass.
    """
    assert_opens_at(ORDINARY_CLOSE, HONOLULU, HONOLULU_OPENS, "The ordinary close, in Honolulu")


# ---------------------------------------------------------------------------
# The rule's consequences, over generated closes.
# ---------------------------------------------------------------------------

# Zones chosen for what each varies: two with daylight saving on different dates
# and in different hemispheres, one whose shift is half an hour, one with a
# half-hour standard offset and daylight saving, and two with none. In every one
# of them the 2026-2027 clock changes fall well away from 06:00, so a Monday 06:00
# wall time always exists exactly once.
ZONES = (
    "America/New_York",
    "Europe/London",
    "Australia/Lord_Howe",
    "America/St_Johns",
    "Pacific/Honolulu",
    "Asia/Kolkata",
)

# Hypothesis takes naive bounds and attaches the zone itself; the closes it
# generates are aware, in UTC, the way a stored `timestamptz` comes back.
GENERATED_FROM = datetime(2026, 1, 1)  # noqa: DTZ001
GENERATED_TO = datetime(2027, 12, 31)  # noqa: DTZ001
CLOSES = st.datetimes(min_value=GENERATED_FROM, max_value=GENERATED_TO, timezones=st.just(UTC))


@settings(max_examples=300, deadline=None)
@given(closes_at=CLOSES, zone_name=st.sampled_from(ZONES))
@example(closes_at=MONDAY_SIX_CLOSE, zone_name="America/New_York")
@example(closes_at=MONDAY_FIVE_CLOSE, zone_name="America/New_York")
@example(closes_at=FALL_BACK_CLOSE, zone_name="America/New_York")
@example(closes_at=SPRING_FORWARD_CLOSE, zone_name="America/New_York")
@example(closes_at=datetime(2026, 10, 19, 16, 0, 0, tzinfo=UTC), zone_name="Pacific/Honolulu")
def test_the_opening_is_the_first_monday_six_after_the_close_in_every_zone(
    closes_at: datetime, zone_name: str
) -> None:
    """For any close and zone: a Monday at 06:00 local, after the close, within a week.

    Four consequences of the ruling, none of which produces an expected value:

      - the opening is strictly after the close;
      - in the given zone it is a Monday, at 06:00:00;
      - it is no more than seven wall-clock days after the close — the
        "first" in "the first Monday 06:00", since a later Monday 06:00 would be
        more than seven days on;
      - the predicate is false a microsecond before it and true at it.

    The explicit examples are the cases the generator is least likely to reach:
    a close exactly at Monday 06:00 local (in New York and in Honolulu, where
    16:00 UTC is 06:00 HST), a close just before one, and both daylight-saving
    weeks (`docs/MISTAKES.md` entry 15).

    **The mutations this kills:** any fixed-offset computation (fails the
    "06:00 local" clause in some zone and season), a non-strict comparison
    (fails "strictly after" at the explicit examples), an opening one week late
    (fails "within seven days"), and a predicate that is not
    `now >= report_opens_at(...)`.
    """
    names = reporting_names()
    zone = ZoneInfo(zone_name)
    opens = names.opens_at(closes_at, zone=zone)

    assert opens > closes_at, (
        f"In {zone_name}, a window closing at {closes_at.isoformat()} opens its report at "
        f"{opens.isoformat()}, which is not strictly after the close."
    )
    local = opens.astimezone(zone)
    assert local.weekday() == MONDAY and local.time() == time(6, 0), (
        f"In {zone_name}, a window closing at {closes_at.isoformat()} opens its report at "
        f"{local.isoformat()} local, which is not a Monday at 06:00:00."
    )
    wall_gap = local.replace(tzinfo=None) - closes_at.astimezone(zone).replace(tzinfo=None)
    assert wall_gap <= timedelta(days=7), (
        f"In {zone_name}, a window closing at {closes_at.astimezone(zone).isoformat()} local opens "
        f"its report at {local.isoformat()}, {wall_gap} of wall time later. A Monday 06:00 comes "
        "round every seven days, so the first one after the close is never further than that."
    )
    assert names.is_published(closes_at, now=opens - ONE_MICROSECOND, zone=zone) is False, (
        f"In {zone_name}, the week closing at {closes_at.isoformat()} is published a microsecond "
        f"before its own opening {opens.isoformat()}."
    )
    assert names.is_published(closes_at, now=opens, zone=zone) is True, (
        f"In {zone_name}, the week closing at {closes_at.isoformat()} is unpublished at its own "
        f"opening {opens.isoformat()}. The ruling: 06:00:00 exactly is published."
    )
