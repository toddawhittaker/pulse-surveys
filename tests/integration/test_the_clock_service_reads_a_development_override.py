"""What `app.services.clock` answers, with an override row and without one — E2-04.

The service is the one place this codebase asks what time it is for scheduling
purposes: the effective instant in UTC, and the effective date in the
institution's timezone (SPEC §3.1 puts every survey window at a wall-clock time
in that zone). E2-04 gives it a development-only override — a pretended instant
paired with the real instant it was anchored at — and this module is where the
meaning of that pair is pinned.

**The override is an offset, not a freeze, and that is the whole design.** A
freeze stops the clock at the instant somebody typed, so a stack left overridden
never reaches the next minute and nothing that depends on elapsed time can be
driven by hand at all. An offset moves the origin and lets time keep flowing from
there, which is what makes `Friday 18:00` reachable on a Tuesday afternoon and
still lets a window close. Three tests below separate those two readings, and
none of them is redundant: the anchored-just-now case says the answer *is* the
pretended instant, the anchored-an-hour-ago case says the elapsed hour was added,
and the two-reads case says the answer keeps moving.

**Both directions of the environment gate.** The override applies only where
`is_development(settings)`; in any other environment the row is dead weight even
if it is present. A test that only ever showed the override working could not
tell that rule from an implementation that had never heard of it, so the inert
direction is asserted with the same row in place and the environment the only
thing changed (criterion 3, `docs/MISTAKES.md` entry 2).

**Every test states the environment it runs under**, through `settings_in`, which
takes the name from the test's own body (`docs/MISTAKES.md` entry 40). Nothing
here reads `os.environ` and nothing here depends on a developer's `.env`:
`configured_env` moves the working directory to an empty one first.

**The pretend instant is years away from real time**, deliberately. A pretended
now a few seconds from the real one would be satisfied by an implementation that
ignored the row entirely, and no tolerance a test could choose would tell the two
apart (`docs/MISTAKES.md` entry 30). Five years apart, a sixty-second tolerance
is generous to a slow container and still cannot admit the wrong answer.

The `/dev` control that writes this row is
`tests/integration/test_the_dev_console_sets_and_clears_the_clock.py`; its refusal
outside development is `tests/unit/test_dev_clock_control_exposure.py`.
"""

import time
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fixtures.clock import (
    ANCHORED_AT_COLUMN,
    DEVELOPMENT,
    INSTITUTION_TIMEZONE_VARIABLE,
    PRETEND_NOW_COLUMN,
)

pytestmark = pytest.mark.integration

# The pretended instant every case below is built on. Five years out, so it cannot
# be confused with real time by any tolerance, and at 10:30 UTC — the one hour of
# the day in which UTC+14 has already turned the page and UTC-11 has not yet
# reached it, which is what makes the three dates in `PRETEND_DAY_IN` distinct.
PRETEND_NOW = datetime(2031, 3, 14, 10, 30, tzinfo=UTC)

# What that instant's calendar date is, per zone. **Three different days**, and
# that is the point: a `today` that answered UTC's day would pass in neither zone,
# and one that answered a fixed zone would pass in only one of them. Both are
# real IANA zones with no daylight saving, so nothing here depends on the tzdata
# edition beyond the offsets themselves.
PRETEND_DAY_IN = {
    "Pacific/Kiritimati": date(2031, 3, 15),  # UTC+14
    "Pacific/Niue": date(2031, 3, 13),  # UTC-11
}
PRETEND_DAY_IN_UTC = date(2031, 3, 14)

# A zone to run the cases that are not about zones under. Named rather than left
# to `.env.example`'s default, because a test that depends on the institution's
# timezone states it (`docs/MISTAKES.md` entry 40) — and SPEC §3.1's own default
# is `America/New_York`, so this is the realistic one.
A_STATED_TIMEZONE = "America/New_York"

# Deployment names the override must not apply under. Two, for the reason ADR 0063
# gives: the comparison is an equality against the one safe name, so a guard that
# special-cased a single deployment spelling would be caught by the other.
DEPLOYMENT_ENVIRONMENTS = ("production", "staging")

# How far from the expected instant an answer may land. Generous enough for a cold
# testcontainers Postgres and a query round trip; tiny beside the five years that
# separate every right answer below from every wrong one.
TOLERANCE = timedelta(seconds=60)

# How long the anchored-in-the-past case pretends to have been running. An hour,
# because it has to be far outside `TOLERANCE` for the assertion to distinguish
# "the elapsed time was added" from "the pretended instant was returned as it is".
ELAPSED = timedelta(hours=1)


def real_dates_around(zone: str) -> set[date]:
    """The dates that could be called "today" in `zone` while a test runs.

    A pair rather than a day, because a test that started at 23:59:59.9 and
    asserted at 00:00:00.1 would otherwise fail on the calendar rather than on the
    code. Everything these are compared against is years away, so widening by a
    day costs nothing.
    """
    now = datetime.now(ZoneInfo(zone))
    return {(now - timedelta(minutes=1)).date(), (now + timedelta(minutes=1)).date()}


# ---------------------------------------------------------------------------
# The control on the override writer, before anything is believed of it. A red
# here means these tests are broken, not that the service is.
# ---------------------------------------------------------------------------


def test_the_override_writer_puts_one_row_in_and_takes_one_out(clock_overrides: Any) -> None:
    """The control on every case below (`docs/MISTAKES.md` entry 3).

    Each test after this one says what the service answers *given a row*, and each
    of the inert cases says what it answers *given a row it must ignore*. A writer
    that silently wrote nothing would make the first group fail for the wrong
    reason and the second group pass for no reason at all — the second is the
    dangerous half, because "the override moved nothing outside development" is
    exactly what an empty table looks like.

    So the writer is shown here putting a row in, storing both instants it was
    given, and taking it out again.

    **Needs no service, only the model and the migration.** If this is red, E2-04's
    `clock_override` table does not exist or does not carry both columns, and
    nothing else in this module means what it says.
    """
    anchored = datetime.now(UTC)

    clock_overrides.set(pretend_now=PRETEND_NOW, anchored_at=anchored)
    written = clock_overrides.rows()

    assert len(written) == 1, (
        f"The writer left {len(written)} rows in `clock_override`: {written}. The override is a "
        "single row — E2-04 enforces that with a unique index over `(true)`, the way `institution` "
        "does — so anything but one here is a table that cannot answer the question the service "
        "asks of it."
    )
    assert written[0][PRETEND_NOW_COLUMN] == PRETEND_NOW, (
        f"The row carries `{PRETEND_NOW_COLUMN}` {written[0][PRETEND_NOW_COLUMN]!r} and this test "
        f"wrote {PRETEND_NOW!r}. Every assertion below is about what the service does with the "
        "value in this column, so a column that does not keep it makes all of them meaningless."
    )
    assert written[0][ANCHORED_AT_COLUMN] == anchored, (
        f"The row carries `{ANCHORED_AT_COLUMN}` {written[0][ANCHORED_AT_COLUMN]!r} and this test "
        f"wrote {anchored!r}. The anchor is the real instant the override was set at, and the "
        "offset the service applies is measured from it."
    )

    clock_overrides.clear()
    assert clock_overrides.rows() == [], (
        f"After `clear` the table still holds {clock_overrides.rows()}. The clearing half of "
        "criterion 2 — 'clearing it returns them to real time' — is asserted below by writing a "
        "row and removing it, and a `clear` that removed nothing would make that case pass while "
        "the override was still in force."
    )


# ---------------------------------------------------------------------------
# With no override at all: the service is real time.
# ---------------------------------------------------------------------------


def test_now_answers_an_aware_utc_instant_close_to_real_time_with_no_override(
    clock_overrides: Any, clock_service: Any, settings_in: Any, db_session: Any
) -> None:
    """With nothing in `clock_override`, the service answers the real clock.

    The base case, and the one every other assertion in the product rests on: a
    stack nobody has overridden behaves exactly as it did before E2-04 existed.

    **The mutations this kill**: a service that applies an offset when no row is
    there — reading a missing row as a zero pretend instant, which lands the whole
    product in 1970 — and one that answers a naive datetime, which ADR 0019 spends
    a whole type decorator keeping out of this codebase and which would compare
    wrongly against every aware value the schema holds.

    The table is asserted empty first, because "the service answers real time" is
    trivially true of a service that answers real time *always*, and the case that
    tells those apart is the next one along; here the point is that the premise is
    the empty table and not a row this test forgot to look at.
    """
    settings = settings_in(DEVELOPMENT, **{INSTITUTION_TIMEZONE_VARIABLE: A_STATED_TIMEZONE})

    assert clock_overrides.rows() == [], (
        f"`clock_override` already holds {clock_overrides.rows()} before this test wrote anything. "
        "This case is about the absence of an override, and a row left behind by something else "
        "would make it a case about the presence of one."
    )

    before = datetime.now(UTC)
    answered = clock_service.now(db_session, settings=settings)
    after = datetime.now(UTC)

    assert isinstance(answered, datetime), (
        f"`clock.now` answered {answered!r}, which is not a datetime. The service's whole job is "
        "to be the one place the codebase asks for the current instant."
    )
    assert answered.utcoffset() is not None, (
        f"`clock.now` answered {answered!r}, which carries no UTC offset. ADR 0019 refuses a naive "
        "datetime at the column boundary precisely because a naive value is a different instant on "
        "every connection; a service that produced one would hand that value to every writer in "
        "the product."
    )
    assert before - TOLERANCE <= answered <= after + TOLERANCE, (
        f"`clock.now` answered {answered!r} with no override row, and real time during this call "
        f"ran from {before!r} to {after!r}. With nothing in `clock_override` the service is the "
        "system clock."
    )


def test_today_answers_the_institutions_current_date_with_no_override(
    clock_overrides: Any, clock_service: Any, settings_in: Any, db_session: Any
) -> None:
    """With nothing overridden, `today` is the institution's own calendar day.

    SPEC §3.1 puts the window at a wall-clock time in the institution timezone and
    §8 makes that zone a deployment-level setting, so "today" is a fact about the
    institution's calendar and never about the server's. E1-11 already ruled this
    for provisioning (`docs/adr` and
    `tests/integration/test_provisioning_reads_its_environment_and_its_day_from_settings.py`);
    the service inherits the rule rather than restating it.

    **The mutation this kills**: `datetime.now(UTC).date()`, which is what every
    call site read before E2-04 replaced it and what the shortest correct-looking
    implementation of `today` would be.

    Asserted against a two-value band for the reason `real_dates_around` gives, and
    the zone is stated by this test rather than inherited from `.env.example`.
    """
    settings = settings_in(DEVELOPMENT, **{INSTITUTION_TIMEZONE_VARIABLE: A_STATED_TIMEZONE})

    assert clock_overrides.rows() == [], (
        f"`clock_override` already holds {clock_overrides.rows()}, so this is not the no-override "
        "case it says it is."
    )

    expected = real_dates_around(A_STATED_TIMEZONE)
    answered = clock_service.today(db_session, settings=settings)

    assert answered in expected, (
        f"`clock.today` answered {answered!r} with no override row; today in "
        f"{A_STATED_TIMEZONE} is one of {sorted(expected)}. UTC's date right now is "
        f"{datetime.now(UTC).date()}, which is what a service reading the server's clock rather "
        "than the institution's would answer."
    )


# ---------------------------------------------------------------------------
# In development, with an override: the answers move, and keep moving.
# ---------------------------------------------------------------------------


def test_now_answers_the_pretend_instant_when_the_override_was_just_anchored(
    clock_overrides: Any, clock_service: Any, settings_in: Any, db_session: Any
) -> None:
    """Criterion 2, the setting half: what was typed is what the service answers.

    An override anchored at this moment has no elapsed time to add, so the
    effective now is the pretended instant itself, give or take the test's own
    round trip.

    **The mutations this kills**: a service that ignores the row (answers real time
    — five years out); one that adds the pretend instant to the real one rather
    than the offset (answers some time in 4057); and one that applies the offset
    backwards, `real - (pretend - anchored)`, which lands five years in the *past*
    and is the single easiest sign error to write here.

    **The near miss it must not be trusted alone against**: a service that returns
    `pretend_now` verbatim and never moves. It passes this test perfectly, and the
    two tests below are what fail it.
    """
    settings = settings_in(DEVELOPMENT, **{INSTITUTION_TIMEZONE_VARIABLE: A_STATED_TIMEZONE})
    clock_overrides.set(pretend_now=PRETEND_NOW, anchored_at=datetime.now(UTC))

    answered = clock_service.now(db_session, settings=settings)

    assert PRETEND_NOW - TOLERANCE <= answered <= PRETEND_NOW + TOLERANCE, (
        f"`clock.now` answered {answered!r} under an override pretending it is {PRETEND_NOW!r}, "
        f"anchored a moment ago. Real time is about {datetime.now(UTC)!r}; an answer near that is "
        "the row being ignored, and an answer near neither is the offset being applied with the "
        "wrong sign or against the wrong operand."
    )


def test_now_adds_the_real_time_elapsed_since_the_override_was_anchored(
    clock_overrides: Any, clock_service: Any, settings_in: Any, db_session: Any
) -> None:
    """The override is an offset: an hour of real time is an hour of pretended time.

    The anchor is set an hour into the real past, which is exactly what a stack
    overridden an hour ago looks like. The effective now is then the pretended
    instant plus that hour — `real + (pretend_now - anchored_at)` — and not the
    pretended instant itself.

    **The mutation this kills**: storing the pretended instant and returning it, a
    freeze. It is the obvious implementation, it passes the test above, and it
    makes the whole feature useless for the thing the ticket wants it for: a stack
    frozen at Friday 18:00 never reaches Sunday 23:59:59, so no window ever closes
    and nothing that depends on elapsed time can be driven by hand.

    **The near miss it must not pass on**: an implementation that measures the
    offset from the row's own `created_at`, or from the moment of the call, rather
    than from `anchored_at`. Both answer the pretended instant here, an hour out,
    and fail on this assertion — which is why the anchor is in the past rather than
    at the moment of the call.
    """
    settings = settings_in(DEVELOPMENT, **{INSTITUTION_TIMEZONE_VARIABLE: A_STATED_TIMEZONE})
    clock_overrides.set(pretend_now=PRETEND_NOW, anchored_at=datetime.now(UTC) - ELAPSED)

    expected = PRETEND_NOW + ELAPSED
    answered = clock_service.now(db_session, settings=settings)

    assert expected - TOLERANCE <= answered <= expected + TOLERANCE, (
        f"`clock.now` answered {answered!r}. The override pretends it was {PRETEND_NOW!r} when it "
        f"was set, and it was set {ELAPSED} of real time ago, so the effective now is "
        f"{expected!r}. An answer of {PRETEND_NOW!r} is a frozen clock: time stopped where "
        "somebody typed it, and a survey window opened that way never closes."
    )


def test_two_reads_of_now_under_an_override_strictly_increase(
    clock_overrides: Any, clock_service: Any, settings_in: Any, db_session: Any
) -> None:
    """Time keeps flowing while the override is in force.

    The other half of "an offset, not a freeze", and the half that is a property of
    the answers rather than of one answer: two reads a moment apart are two
    different instants, in order.

    **The mutation this kills**: returning `pretend_now` from the row, which makes
    every read of the clock identical for as long as the override stands.

    **Why the sleep is the instrument and not a courtesy**: without it the two
    reads could in principle land in the same microsecond on a coarse clock, and
    the assertion would fail against a correct implementation. Ten milliseconds is
    far above any real clock's resolution and far below anything a reader would
    call a wait.
    """
    settings = settings_in(DEVELOPMENT, **{INSTITUTION_TIMEZONE_VARIABLE: A_STATED_TIMEZONE})
    clock_overrides.set(pretend_now=PRETEND_NOW, anchored_at=datetime.now(UTC))

    first = clock_service.now(db_session, settings=settings)
    time.sleep(0.01)
    second = clock_service.now(db_session, settings=settings)

    assert second > first, (
        f"Two reads of `clock.now` ten milliseconds apart answered {first!r} and {second!r}. Under "
        "an override the clock is offset, not stopped: the row holds a pretended instant and the "
        "real instant it was anchored at, and the difference between them is added to real time on "
        "every read. Equal answers are a frozen clock."
    )


@pytest.mark.parametrize("zone", sorted(PRETEND_DAY_IN))
def test_today_answers_the_pretend_days_date_in_the_institution_timezone(
    zone: str, clock_overrides: Any, clock_service: Any, settings_in: Any, db_session: Any
) -> None:
    """`today` is the overridden instant read in the institution's zone, not in UTC.

    The two zones are chosen so that the one pretended instant falls on **three
    different calendar days**: 2031-03-15 in Kiritimati (UTC+14), 2031-03-14 in
    UTC, and 2031-03-13 in Niue (UTC-11). A service that answered UTC's day is
    wrong in both cases, and one that answered a hardcoded zone is wrong in one —
    a single zone could not tell either apart.

    **The mutations this kills**: `clock.now(...).date()`, which is UTC's day and
    is the one-line implementation somebody would reach for once `now` exists; and
    a `today` that applies the override to the date but resolves the zone from
    somewhere other than `settings.institution_timezone`.

    The three expected days are asserted to be distinct before anything else, so a
    zone whose offset changed under the tzdata this container carries fails saying
    the arithmetic is wrong rather than failing as though the service were.
    """
    expected = PRETEND_DAY_IN[zone]
    assert expected != PRETEND_DAY_IN_UTC, (
        f"The pretended instant {PRETEND_NOW!r} falls on {expected} in {zone} and on "
        f"{PRETEND_DAY_IN_UTC} in UTC, and this test needs those to differ — otherwise a service "
        "reading UTC's day answers correctly here and the case proves nothing."
    )

    settings = settings_in(DEVELOPMENT, **{INSTITUTION_TIMEZONE_VARIABLE: zone})
    clock_overrides.set(pretend_now=PRETEND_NOW, anchored_at=datetime.now(UTC))

    answered = clock_service.today(db_session, settings=settings)

    assert answered == expected, (
        f"`clock.today` answered {answered!r} with `{INSTITUTION_TIMEZONE_VARIABLE}` set to "
        f"{zone!r} and the clock overridden to {PRETEND_NOW!r}. That instant is {expected} in "
        f"{zone} and {PRETEND_DAY_IN_UTC} in UTC. SPEC §3.1 puts every survey window at a "
        "wall-clock time in the institution's zone, so the day a window belongs to is that zone's "
        "day and never the server's."
    )


def test_clearing_the_override_returns_the_service_to_real_time(
    clock_overrides: Any, clock_service: Any, settings_in: Any, db_session: Any
) -> None:
    """Criterion 2, the clearing half: the row goes and the clock comes back.

    Set, read, clear, read — one test, because the claim is about the transition
    and splitting it would leave the second half asserting against a state the
    first half produced.

    **The mutations this kill**: a service that caches the offset after its first
    read, so a cleared override goes on applying for the life of the process; and a
    `clear` that writes a zero-offset row rather than removing one, which is
    indistinguishable from this side until something asserts the table is empty —
    so that is asserted too.

    The moved reading is taken first and required to be moved. Without it, "the
    clock is real after clearing" is satisfied by an override that never applied,
    which is the whole of what this pair exists to rule out (`docs/MISTAKES.md`
    entry 3).
    """
    settings = settings_in(DEVELOPMENT, **{INSTITUTION_TIMEZONE_VARIABLE: A_STATED_TIMEZONE})
    clock_overrides.set(pretend_now=PRETEND_NOW, anchored_at=datetime.now(UTC))

    moved = clock_service.now(db_session, settings=settings)
    assert PRETEND_NOW - TOLERANCE <= moved <= PRETEND_NOW + TOLERANCE, (
        f"`clock.now` answered {moved!r} while the override was in force, and the override "
        f"pretends it is {PRETEND_NOW!r}. The clock never moved, so the assertion below — that it "
        "comes back — would be about a clock that never left."
    )

    clock_overrides.clear()
    assert clock_overrides.rows() == [], (
        f"`clear` left {clock_overrides.rows()} in `clock_override`. A cleared override is an "
        "absent row; a row holding a zero offset answers the same instants today and is a state "
        "nothing else in this product knows how to read."
    )

    before = datetime.now(UTC)
    restored = clock_service.now(db_session, settings=settings)
    after = datetime.now(UTC)

    assert before - TOLERANCE <= restored <= after + TOLERANCE, (
        f"`clock.now` answered {restored!r} after the override was cleared, and real time during "
        f"that call ran from {before!r} to {after!r}. The offset outlived the row it came from, "
        "which on a running stack means clearing the clock from `/dev` appears to do nothing until "
        "the process restarts."
    )


# ---------------------------------------------------------------------------
# Outside development: the same row, and nothing moves.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("environment", DEPLOYMENT_ENVIRONMENTS)
def test_the_override_moves_neither_now_nor_today_outside_development(
    environment: str,
    clock_overrides: Any,
    clock_service: Any,
    settings_in: Any,
    db_session: Any,
) -> None:
    """Criterion 3: the row is dead weight in any environment but development.

    The paired opposite of every case above, and the pairing is what makes it worth
    anything: the same row, written the same way, with the environment the only
    thing changed. E2-04's ticket states the rule as "the service applies the
    override **only when `is_development(settings)`** — in any other environment
    the row is dead weight even if present", and the security note above it says
    why a row that reached a deployment must not be able to move anything.

    **The mutation this kills**: the environment check missing from the service, or
    written the wrong way round. A `clock_override` row reaching a deployment — by
    a restored dump, a copied database, a migration that seeded one — would then
    move every survey window and every live-enrollment check in the product, with
    nothing in the schema marking the row as development-only.

    **The near miss this must not pass on**: an empty table. "Nothing moved" is
    exactly what a missing row looks like, so the row is read back and required to
    be present and to hold an instant years from now, before either answer is
    believed (`docs/MISTAKES.md` entry 3).

    Both `now` and `today` are asserted, because they are two functions and a guard
    applied to one of them is the shape this repository has shipped before.
    """
    settings = settings_in(environment, **{INSTITUTION_TIMEZONE_VARIABLE: A_STATED_TIMEZONE})
    clock_overrides.set(pretend_now=PRETEND_NOW, anchored_at=datetime.now(UTC))

    present = clock_overrides.rows()
    assert len(present) == 1 and present[0][PRETEND_NOW_COLUMN] == PRETEND_NOW, (
        f"`clock_override` holds {present} rather than one row pretending it is {PRETEND_NOW!r}. "
        "Both assertions below say the clock did not move, and an empty table would satisfy them "
        "without the environment gate existing at all."
    )

    expected_days = real_dates_around(A_STATED_TIMEZONE)
    before = datetime.now(UTC)
    answered_now = clock_service.now(db_session, settings=settings)
    after = datetime.now(UTC)
    answered_today = clock_service.today(db_session, settings=settings)

    assert before - TOLERANCE <= answered_now <= after + TOLERANCE, (
        f"`clock.now` answered {answered_now!r} with `ENVIRONMENT` set to {environment!r} and an "
        f"override row pretending it is {PRETEND_NOW!r}. Real time during the call ran from "
        f"{before!r} to {after!r}. Outside development the row is dead weight: a deployment that "
        "acquired one — a restored dump, a copied database — must go on reading the real clock."
    )
    assert answered_today in expected_days, (
        f"`clock.today` answered {answered_today!r} with `ENVIRONMENT` set to {environment!r}; "
        f"today in {A_STATED_TIMEZONE} is one of {sorted(expected_days)} and the override's own "
        f"day is {PRETEND_DAY_IN_UTC}. The gate has to hold on both functions, not on the one "
        "somebody remembered."
    )
