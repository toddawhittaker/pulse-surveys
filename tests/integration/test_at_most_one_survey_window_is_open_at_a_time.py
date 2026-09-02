"""One open survey at a time, and which one the clock says — ticket E2-06, criteria 2 and 3.

SPEC §3.1: "Students see exactly one open survey at a time per section. Missed
weeks cannot be back-filled." E2-06's scope makes both halves assertions rather
than assumptions — "asserted, not assumed, across a term's worth of derived
windows including the term-break weeks §2.2's calendar carries" — and adds the
boundary pair: with the clock at Friday 18:05 a seeded section answers open, at
Sunday 23:59:59 it still answers open, and at Monday 00:00:01 it answers closed
(`docs/MISTAKES.md` entry 3, both sides of every line).

**Two subjects, and they are not the same claim.** The one-open rule is a
property of the *derived rows*: no instant falls inside two of a section's
windows. Which window is open *now* is a property of the read path, and it goes
through the E2-04 clock — so those tests move the development clock and ask
`open_window_for_section`. A suite that only did the second could not tell "one
window is open" from "the query returns the first row it finds".

**The generator includes the boundary instants themselves** (`docs/MISTAKES.md`
entry 15). A property named for a boundary whose strategy cannot produce it is
the defect that entry is about, and the boundaries here are exactly where two
windows could touch: the second before a window opens, the instant it opens, the
second after; and the same three around its close. All of them are drawn from
explicitly, alongside instants spread across the term.

**Two ways of asking, because one instrument cannot do both jobs.** The
development clock is an offset on real time (ADR 0109), not a freeze: the
effective now is `real + (pretend_now - anchored_at)`, so a test can put the
clock a known distance from a boundary and can never put it *on* one. That makes
the clock the right instrument for "does the read path consult the clock at all"
and the wrong one for "which comparison is written there" — inclusive and
exclusive differ at exactly one instant, and no offset clock can land on it.

So `open_window_for_section` takes `at: datetime | None = None`. Every production
caller leaves it `None` and the instant comes from `clock.now`; a test passes
`at=` to stand exactly on a boundary. Both halves are exercised below and neither
replaces the other:

  - the **one-second cases** move the development clock and leave `at` alone, so
    they go red if the service stops reading the clock — which is the whole of
    what makes the `/dev` control useful, and which the `at=` cases cannot see
    because they never consult it;
  - the **exact-instant cases** pass `at=` and stand on `opens_at`, on
    `closes_at`, and one microsecond either side, so they go red if `<=` becomes
    `<` at either end — which the one-second cases cannot see, because the two
    readings of the operator agree everywhere except on the boundary itself.

The exact-instant cases run with the development clock deliberately set inside a
*different* window, so a service that ignored `at` answers the wrong window
rather than `None` and all four cases fail rather than one pair passing by
accident (`docs/MISTAKES.md` entry 3).
"""

from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

import pytest
from fixtures.survey_windows import (
    DST_FALL_BACK_TERM_WEEK,
    SEEDED_COHORTS,
    WINDOW_CLOSES_COLUMN,
    WINDOW_OPENS_COLUMN,
    WINDOWS_BY_TERM_WEEK,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

pytestmark = pytest.mark.integration

ONE_SECOND = timedelta(seconds=1)

# The smallest step either side of a boundary that both Python and Postgres can
# hold: `timestamptz` keeps microseconds, so `closes_at + 1µs` is a genuinely
# different instant and not a value that rounds back onto the boundary.
ONE_MICROSECOND = timedelta(microseconds=1)

# The cohort the read-path cases are driven against: twelve weeks from the term's
# first, so it holds term week 11 — the one window in Fall 2026 whose two ends sit
# on different UTC offsets, and therefore the sharpest week to ask "is it open" in.
A_TWELVE_WEEK_COHORT = "U"

# How far apart two readings of real time may be before this module stops
# believing it knows which side of a boundary the clock was on.
#
# **This is a broken-run signal and never a red.** The development clock is an
# offset: the effective now the service reads is the pretended instant plus
# whatever real time passed between this test writing the override row and the
# service reading it. Where a case sits one second from a boundary, a reading that
# took longer than a second could have crossed it, and the answer would then be
# correct for an instant the test did not choose. So the elapsed time is measured
# and the case stops with a message saying the machine was too slow — rather than
# failing as though the service had answered wrongly.
MAXIMUM_READING_DRIFT = ONE_SECOND

# The term week the exact-instant cases point the *clock* at while they ask about
# term week 11 through `at=`. The week after, which the twelve-week cohort also
# runs, so the clock is standing inside a window this very section has open — a
# service that ignored `at` answers that window, and every one of the four cases
# fails rather than the two `None` ones passing for the wrong reason.
A_NEIGHBOURING_TERM_WEEK = DST_FALL_BACK_TERM_WEEK + 1
A_CLOCK_INSIDE_ANOTHER_WINDOW = WINDOWS_BY_TERM_WEEK[A_NEIGHBOURING_TERM_WEEK][0] + timedelta(
    minutes=5
)

# Two naive datetimes for the refusal case, one either side of the boundary. The
# first is the wall-clock spelling of an instant five minutes into the window
# under test and the second of a Wednesday outside every window, each with its
# offset stripped — which is exactly the shape a value arrives in when somebody
# parses an ISO string without a zone, or reads an HTML `datetime-local` field.
# **Naive on purpose; the `noqa` is the reason.**
NAIVE_INSIDE_THE_WINDOW = datetime(2026, 10, 30, 22, 5, 0)  # noqa: DTZ001
NAIVE_OUTSIDE_THE_WINDOW = datetime(2026, 10, 28, 12, 0, 0)  # noqa: DTZ001

# Instants outside every window of the twelve-week cohort. The first is before the
# term begins, the second is a Wednesday between two windows (term week 10 closed
# on the Monday and term week 11 opens on the Friday), and the third is after the
# cohort's last window has closed and after the term itself has ended.
BEFORE_THE_TERM = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
MIDWEEK_BETWEEN_TWO_WINDOWS = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
AFTER_THE_TERM = datetime(2026, 12, 25, 12, 0, 0, tzinfo=UTC)

# The span the generated instants are drawn from: the term's first Monday to a
# week past its last day. **Naive on purpose, and the `noqa` is the reason**:
# `st.datetimes` takes naive bounds and applies the `timezones` strategy to them,
# so an aware bound is a `TypeError` inside the generator. Every instant the
# strategy hands a test is aware UTC.
GENERATED_SPAN_START = datetime(2026, 8, 17, 0, 0, 0)  # noqa: DTZ001
GENERATED_SPAN_END = datetime(2026, 12, 27, 0, 0, 0)  # noqa: DTZ001

# Every instant at which two of a term's windows could touch, drawn from
# explicitly (`docs/MISTAKES.md` entry 15). Six per term week: the second before
# each end, the end itself, and the second after.
BOUNDARY_INSTANTS = tuple(
    sorted(
        {
            instant
            for opens_at, closes_at in WINDOWS_BY_TERM_WEEK.values()
            for instant in (
                opens_at - ONE_SECOND,
                opens_at,
                opens_at + ONE_SECOND,
                closes_at - ONE_SECOND,
                closes_at,
                closes_at + ONE_SECOND,
            )
        }
    )
)


def instants_across_the_term() -> st.SearchStrategy[datetime]:
    """Instants to ask the one-open question at, boundaries included by construction.

    Two strategies in one: the exhaustive set of window boundaries, and instants
    anywhere between the term's first Monday and a week after its last day. The
    first half is what `docs/MISTAKES.md` entry 15 asks for — a property about
    boundaries whose generator draws from a continuous range will not land on one
    in any number of examples — and the second is what finds an overlap in the
    middle of a week nobody thought about.

    **What it does not reach, stated rather than left as a claim of totality**:
    instants outside the term, and sub-second offsets other than a whole second
    from a boundary. Neither is where two windows of one section can touch, since
    every window in the calendar is expressed to the second.
    """
    return st.one_of(
        st.sampled_from(BOUNDARY_INSTANTS),
        st.datetimes(
            min_value=GENERATED_SPAN_START,
            max_value=GENERATED_SPAN_END,
            timezones=st.just(UTC),
        ),
    )


def window_instant(window: Any, column: str) -> datetime:
    """One end of the window the service answered with, or a failure naming the gap."""
    found = getattr(window, column, None)
    if not isinstance(found, datetime):
        pytest.fail(
            f"The window the service answered with carries no `{column}` datetime (it carries "
            f"{found!r}). E2-05 gives `survey_window` its `{WINDOW_OPENS_COLUMN}` and "
            f"`{WINDOW_CLOSES_COLUMN}` columns and E2-06 answers with a `SurveyWindow`, so a test "
            "cannot say *which* window is open without them."
        )
    return found


class ClockedReading:
    """One answer from `open_window_for_section`, with the instants it could have seen.

    The effective now the service read is somewhere in `[earliest, latest]`: the
    pretended instant, plus however much real time passed between this test
    anchoring the override and the service reading the clock. Holding both ends is
    what lets a case say "the whole interval is on one side of the boundary" rather
    than assuming the reading landed where it was aimed.
    """

    def __init__(self, answered: Any, earliest: datetime, latest: datetime) -> None:
        self.answered = answered
        self.earliest = earliest
        self.latest = latest


def read_at(
    pretend_now: datetime,
    *,
    clock_overrides: Any,
    service: Any,
    session: Any,
    section: Any,
    settings_object: Any,
) -> ClockedReading:
    """Ask which window is open with the development clock moved to `pretend_now`.

    **`at` is deliberately not passed.** This is the clock path: the question is
    whether the service reads `clock.now` at all, and a call that supplied the
    instant would answer correctly over a service that never consults the clock —
    which is the state the `/dev` control is useless in and the one E2-04 exists
    to make impossible.
    """
    anchored_at = datetime.now(UTC)
    clock_overrides.set(pretend_now=pretend_now, anchored_at=anchored_at)
    answered = service.open_window_for_section(session, section, settings=settings_object)
    elapsed = datetime.now(UTC) - anchored_at
    return ClockedReading(answered, pretend_now, pretend_now + elapsed)


def answer_at(
    instant: Any,
    *,
    service: Any,
    session: Any,
    section: Any,
    settings_object: Any,
) -> Any:
    """Ask which window is open **at exactly `instant`**, through the `at=` seam.

    The counterpart to `read_at` above and not a replacement for it: this one
    stands on a boundary and says nothing about whether the clock is ever read,
    and that one moves the clock and can never stand on a boundary. Each is the
    only instrument for its own half.
    """
    return service.open_window_for_section(session, section, settings=settings_object, at=instant)


def require_the_reading_landed_where_it_was_aimed(
    reading: ClockedReading, *, inside: bool, opens_at: datetime, closes_at: datetime
) -> None:
    """Stop unless the whole interval the service could have read is on the expected side.

    A slow reading is a run this module cannot draw a conclusion from, and saying
    so is the difference between a broken test and a red one. `docs/MISTAKES.md`
    entry 9's second half is the rule being kept here: never write a prediction
    that explains away the evidence of its own failure.
    """
    span = reading.latest - reading.earliest
    if span > MAXIMUM_READING_DRIFT:
        pytest.fail(
            f"Reading the clock took {span}, longer than the {MAXIMUM_READING_DRIFT} this case "
            "sits from its boundary, so the effective now could have been on either side of it "
            "and no assertion here would mean anything. This is a broken run rather than a red: "
            "the development clock is an offset on real time (ADR 0109), not a freeze, so a "
            "machine slow enough to cross a one-second step between writing the override row and "
            "reading it cannot pose this question. Re-run; if it recurs, the boundary step in "
            "this module has to grow and the pull request says by how much and why."
        )
    if inside:
        landed = reading.earliest >= opens_at and reading.latest <= closes_at
    else:
        landed = reading.latest < opens_at or reading.earliest > closes_at
    if not landed:
        pytest.fail(
            f"The effective now was somewhere in [{reading.earliest}, {reading.latest}] and the "
            f"window runs {opens_at} to {closes_at}. This case aimed "
            f"{'inside' if inside else 'outside'} it and the interval straddles the boundary, so "
            "the answer below would be about an instant nobody chose."
        )


# ---------------------------------------------------------------------------
# Criterion 2 — the one-open rule, over the derived rows.
# ---------------------------------------------------------------------------


def test_no_two_windows_of_any_seeded_cohort_overlap_and_none_is_inverted(
    fall_2026: Any,
    survey_window_service: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """Criterion 2 over the whole seeded start-letter map, deterministically.

    Every one of §2.2's twenty Fall 2026 cohorts, derived into one term, and three
    properties over each set: the windows are one per course week, each opens
    before it closes, and each opens strictly after the one before it closed. The
    third is what "exactly one open survey at a time" reduces to for a sequence of
    intervals on a line.

    **The mutations this kills.**

      - *A window that closes before it opens.* The Friday and the Sunday taken
        from different weeks, or the two swapped, gives a section a window nothing
        can ever be submitted into — and a `closes_at < opens_at` row is not
        refused by anything in E2-05's schema.
      - *Windows on the term's weeks rather than the section's*, which for a
        cohort of fewer than eighteen weeks writes more rows than there are course
        weeks and duplicates some of them.
      - *Every course week written against the same term week*, which is what a
        derivation reading the section's start date instead of the course week's
        offset produces. Twelve identical windows overlap perfectly and the
        one-open rule is broken twelve ways.

    **The non-emptiness guard is not ceremony** (`docs/MISTAKES.md` entry 3): "no
    two windows overlap" is true of a section with no windows, and true of a
    service that wrote nothing at all. Each cohort's count is asserted against the
    length its start letter carries before any interval is compared.
    """
    calendar = fall_2026.build()

    for letter in sorted(SEEDED_COHORTS):
        length_weeks, _first, _start = SEEDED_COHORTS[letter]
        _row, section = calendar.cohort(letter)
        survey_window_service.derive_windows_for_section(
            db_session, section, settings=window_settings
        )
        windows = calendar.windows_of(section)

        assert len(windows) == length_weeks, (
            f"Cohort {letter!r} runs {length_weeks} course weeks and derived {len(windows)} "
            f"windows: {windows}. SPEC §3.1 gives a section one window per active course week, "
            "and every interval property below is vacuous over a set that is empty or short."
        )
        for window in windows:
            assert window["opens_at"] < window["closes_at"], (
                f"Cohort {letter!r}'s window on term week {window['term_week']} opens at "
                f"{window['opens_at']} and closes at {window['closes_at']}. A window that closes "
                "before it opens is one no student can ever submit into, and nothing in E2-05's "
                "schema refuses the row."
            )
        for earlier, later in pairwise(windows):
            assert earlier["closes_at"] < later["opens_at"], (
                f"Cohort {letter!r}'s windows on term weeks {earlier['term_week']} and "
                f"{later['term_week']} overlap: the first closes at {earlier['closes_at']} and the "
                f"second opens at {later['opens_at']}. SPEC §3.1: students see exactly one open "
                "survey at a time per section, and consecutive Friday-to-Sunday spans cannot "
                "overlap unless the derivation put two course weeks on one term week."
            )


@pytest.mark.slow
@settings(
    max_examples=30,
    deadline=None,
    # The database session is function-scoped, so Hypothesis is right to warn that
    # examples share it. Each one runs inside its own savepoint and rolls back,
    # which is the state reset the health check is asking about — the same shape
    # `tests/integration/test_section_date_derivation.py` uses.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(letter=st.sampled_from(sorted(SEEDED_COHORTS)), instant=instants_across_the_term())
def test_no_instant_falls_inside_two_of_one_sections_derived_windows(
    letter: str,
    instant: datetime,
    fall_2026: Any,
    survey_window_service: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """Criterion 2 as a property: at most one window contains any instant.

    The deterministic test above compares each window with the one beside it,
    which is the right shape for a sorted sequence and says nothing about a
    derivation that produced them out of order or produced two sets. This one asks
    the question the rule is actually written in — pick any instant, count the
    windows containing it — over every cohort in §2.2's map and over instants
    drawn from the whole term, boundaries included.

    Containment is inclusive at both ends, which is E2-06's settled rule: a
    window is open when `opens_at <= now <= closes_at`. Under the *stricter*
    exclusive reading two windows sharing an endpoint would still be counted once
    here, so this property is the conservative one and a set that passes it passes
    under either reading.

    **The mutations this kills**: a term-break week given a window belonging to
    two course weeks at once; a fifty-four-hour window written as a seven-day one,
    which overlaps its neighbour at both ends; and an off-by-one that puts course
    weeks N and N+1 on the same term week.

    **The premise is asserted before the property.** "At most one" is trivially
    true of zero, so a cohort's whole set is required to be there first — over a
    service that has not been written yet, the property alone would be green.
    """
    savepoint = db_session.begin_nested()
    try:
        calendar = fall_2026.build()
        _row, section = calendar.cohort(letter)
        survey_window_service.derive_windows_for_section(
            db_session, section, settings=window_settings
        )
        windows = calendar.windows_of(section)

        assert len(windows) == SEEDED_COHORTS[letter][0], (
            f"Cohort {letter!r} derived {len(windows)} windows and its start letter gives it "
            f"{SEEDED_COHORTS[letter][0]} course weeks. At most one of an empty set contains any "
            "instant, so the property below says nothing until this holds."
        )

        containing = [
            window["term_week"]
            for window in windows
            if window["opens_at"] <= instant <= window["closes_at"]
        ]
        assert len(containing) <= 1, (
            f"At {instant} the derived windows of a {letter!r} section are open on term weeks "
            f"{containing}. SPEC §3.1: students see exactly one open survey at a time per section. "
            f"The section's windows are {windows}."
        )
    finally:
        savepoint.rollback()


# ---------------------------------------------------------------------------
# The read path — which window the E2-04 clock says is open.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("step", "expected_open", "why"),
    [
        (
            -ONE_SECOND,
            False,
            "a second before Friday 18:00 the week's survey has not opened",
        ),
        (
            timedelta(0),
            True,
            "at Friday 18:00 the week's survey is open",
        ),
        (
            ONE_SECOND,
            True,
            "a second after Friday 18:00 the week's survey is open",
        ),
    ],
)
def test_the_window_opens_at_its_friday_and_not_before(
    step: timedelta,
    expected_open: bool,
    why: str,
    fall_2026: Any,
    survey_window_service: Any,
    window_settings: Any,
    clock_overrides: Any,
    db_session: Any,
) -> None:
    """The opening line, from both sides (`docs/MISTAKES.md` entry 3).

    SPEC §3.1 opens the window Friday 18:00 in the institution's timezone, and the
    week under test is the one whose Friday is 30 October 2026 — daylight time, so
    22:00Z. The three cases sit a second either side of that instant and on it.

    **The mutations these kill**: a window read as open for the whole week, which
    fails a second before the Friday; a comparison in the wrong direction, which
    fails on the two after; and an opening time resolved in UTC rather than in the
    institution's zone, which is four hours out and fails all three.

    **The near miss they must not pass on**: an implementation that answers "open"
    for whichever window is nearest. Every case here asserts *which* window came
    back, not merely that one did, and the case before the Friday requires
    `None` — a section with no open survey is a state the product has to be able
    to express, because it is the state a section is in for five days a week.

    **What no case here can be**: exactly on the boundary. The development clock
    is an offset on real time (ADR 0109), so the effective now is the pretended
    instant plus whatever real time elapsed. The middle case therefore asserts "at
    or just after Friday 18:00", which is a consequence of the inclusive reading
    and not the reading itself —
    `test_the_opening_instant_itself_is_inside_the_window` below stands on the
    boundary through `at=` and is what tells `<=` from `<`. **This test is not
    redundant against it**: it is the only one of the two that fails if the
    service stops reading the clock.
    """
    calendar = fall_2026.build()
    _row, section = calendar.cohort(A_TWELVE_WEEK_COHORT)
    survey_window_service.derive_windows_for_section(db_session, section, settings=window_settings)

    opens_at, closes_at = WINDOWS_BY_TERM_WEEK[DST_FALL_BACK_TERM_WEEK]
    reading = read_at(
        opens_at + step,
        clock_overrides=clock_overrides,
        service=survey_window_service,
        session=db_session,
        section=section,
        settings_object=window_settings,
    )
    require_the_reading_landed_where_it_was_aimed(
        reading, inside=expected_open, opens_at=opens_at, closes_at=closes_at
    )

    if not expected_open:
        assert reading.answered is None, (
            f"With the clock at {opens_at + step} — {why} — the service answered "
            f"{reading.answered!r} rather than `None`. That instant is before the window's "
            f"{opens_at} opening and after the previous week's close, so no survey is open: "
            "SPEC §3.1's rhythm leaves a section closed from Monday morning to Friday evening, "
            "and a service that cannot say so opens every week's survey five days early."
        )
        return

    assert reading.answered is not None, (
        f"With the clock at {opens_at + step} — {why} — the service answered `None`. The section's "
        f"windows are {calendar.windows_of(section)}."
    )
    answered_span = (
        window_instant(reading.answered, WINDOW_OPENS_COLUMN),
        window_instant(reading.answered, WINDOW_CLOSES_COLUMN),
    )
    assert answered_span == (opens_at, closes_at), (
        f"With the clock at {opens_at + step} the service answered the window {answered_span}, and "
        f"the window containing that instant is {(opens_at, closes_at)}. Answering *a* window "
        "rather than *the* window is what a query with no clock comparison in it does."
    )


@pytest.mark.parametrize(
    ("step", "expected_open", "why"),
    [
        (
            -ONE_SECOND,
            True,
            "a second before Sunday 23:59:59 the week's survey is still open",
        ),
        (
            ONE_SECOND,
            False,
            "one second past Sunday 23:59:59 is Monday 00:00:00 and the survey has closed",
        ),
    ],
)
def test_the_window_closes_at_its_sunday_and_not_after(
    step: timedelta,
    expected_open: bool,
    why: str,
    fall_2026: Any,
    survey_window_service: Any,
    window_settings: Any,
    clock_overrides: Any,
    db_session: Any,
) -> None:
    """The closing line, from both sides, on the week where the two ends differ.

    Term week 11 closes at 23:59:59 on Sunday 1 November 2026, which is 04:59:59Z
    on the Monday because daylight time ended that morning. One second later is
    Monday 00:00:00 local, and E2-06's scope says the section answers closed there
    — "reports come after window close" (§3.1), so a window that is still open on
    Monday morning is a report generated over a week that can still change.

    **The mutations these kill**: a close resolved on the *opening* end's UTC
    offset, which puts the boundary an hour early and fails the case before it; a
    close read as the end of Sunday rather than 23:59:59, which fails the case
    after it; and a comparison written `now < closes_at` against a `closes_at`
    taken from the following Monday, which fails both.

    **The near miss they must not pass on**: an implementation that answers the
    *next* window once this one has closed. The Monday case requires `None`, and
    the next window does not open until the Friday.

    Exactly on 23:59:59 is not reachable through an offset clock — the module
    docstring says why — so `test_the_closing_instant_itself_is_inside_the_window`
    below stands on it through `at=`. **The two are not redundant**: only this one
    fails if the service stops consulting the clock, and only that one fails if
    the closing comparison is written `<` instead of `<=`.
    """
    calendar = fall_2026.build()
    _row, section = calendar.cohort(A_TWELVE_WEEK_COHORT)
    survey_window_service.derive_windows_for_section(db_session, section, settings=window_settings)

    opens_at, closes_at = WINDOWS_BY_TERM_WEEK[DST_FALL_BACK_TERM_WEEK]
    reading = read_at(
        closes_at + step,
        clock_overrides=clock_overrides,
        service=survey_window_service,
        session=db_session,
        section=section,
        settings_object=window_settings,
    )
    require_the_reading_landed_where_it_was_aimed(
        reading, inside=expected_open, opens_at=opens_at, closes_at=closes_at
    )

    if not expected_open:
        assert reading.answered is None, (
            f"With the clock at {closes_at + step} — {why} — the service answered "
            f"{reading.answered!r} rather than `None`. The section's windows are "
            f"{calendar.windows_of(section)}."
        )
        return

    assert reading.answered is not None, (
        f"With the clock at {closes_at + step} — {why} — the service answered `None`. The window "
        f"runs {opens_at} to {closes_at}, and the clock is inside it."
    )
    assert window_instant(reading.answered, WINDOW_CLOSES_COLUMN) == closes_at, (
        f"With the clock at {closes_at + step} the service answered a window closing at "
        f"{window_instant(reading.answered, WINDOW_CLOSES_COLUMN)}, and the window containing that "
        f"instant closes at {closes_at}."
    )


@pytest.mark.parametrize(
    ("pretend_now", "why"),
    [
        (BEFORE_THE_TERM, "before the section's first window has opened"),
        (MIDWEEK_BETWEEN_TWO_WINDOWS, "on a Wednesday, between two windows"),
        (AFTER_THE_TERM, "after the section's last window has closed"),
    ],
)
def test_a_section_answers_no_open_window_outside_every_one_of_its_windows(
    pretend_now: datetime,
    why: str,
    fall_2026: Any,
    survey_window_service: Any,
    window_settings: Any,
    clock_overrides: Any,
    db_session: Any,
) -> None:
    """Closed means closed: a past window never reopens and a missed week is not back-filled.

    E2-06's scope: "a window in the past never reopens, a missed week is not
    back-filled". The third case is the one that matters most — the term is over,
    every window has closed, and a service that answered the last one would let a
    student submit against a week that ended in November, which §3.4 then counts
    into a participation denominator that has already been posted.

    **The mutations these kill**: an answer of "the most recent window" or "the
    next window" rather than "the window containing now"; a comparison on the
    *date* rather than the instant, which leaves the whole of Sunday and the whole
    of Friday open; and a query ordered by `opens_at` with no bound at all, which
    answers the section's first window forever.

    **The premise is asserted first.** `None` is what a section with no windows at
    all answers, and that is exactly the state before E2-06 is written — so the
    derived set is read back and required to be complete before the `None` means
    anything (`docs/MISTAKES.md` entry 3).
    """
    calendar = fall_2026.build()
    _row, section = calendar.cohort(A_TWELVE_WEEK_COHORT)
    survey_window_service.derive_windows_for_section(db_session, section, settings=window_settings)

    derived = calendar.windows_of(section)
    assert len(derived) == SEEDED_COHORTS[A_TWELVE_WEEK_COHORT][0], (
        f"The section carries {len(derived)} windows and cohort {A_TWELVE_WEEK_COHORT!r} runs "
        f"{SEEDED_COHORTS[A_TWELVE_WEEK_COHORT][0]} course weeks. A section with no windows "
        "answers `None` at every instant, which is what this test would then be measuring."
    )
    containing = [
        window["term_week"]
        for window in derived
        if window["opens_at"] <= pretend_now <= window["closes_at"]
    ]
    assert not containing, (
        f"{pretend_now} was chosen as an instant {why}, and it falls inside the section's windows "
        f"on term weeks {containing}. This case would then be asserting that an open window "
        "answers `None`."
    )

    reading = read_at(
        pretend_now,
        clock_overrides=clock_overrides,
        service=survey_window_service,
        session=db_session,
        section=section,
        settings_object=window_settings,
    )

    assert reading.answered is None, (
        f"With the clock {why} — {pretend_now} — the service answered {reading.answered!r} rather "
        f"than `None`. The section's windows are {derived}. SPEC §3.1: exactly one open survey at "
        "a time, and a section spends most of its life with none."
    )


def test_the_section_the_clock_is_asked_about_is_the_one_answered_for(
    fall_2026: Any,
    survey_window_service: Any,
    window_settings: Any,
    clock_overrides: Any,
    db_session: Any,
) -> None:
    """Two cohorts, one instant, and each is answered its own window or none.

    At Friday 30 October 18:05 a `U` section — twelve weeks from the term's first —
    is in its eleventh course week, and an `H` section — six weeks from term week
    13 — has not started. Both live in the same term, both have derived windows,
    and the honest answer differs.

    **The mutation this kills, and nothing else in this module reaches it**: a
    read that ignores its `section` argument. A query filtered only on the clock
    answers the first window in the table whose span contains the instant, which
    is some other section's — and every single-section test above passes over it,
    because with one section in the term the wrong answer and the right one are
    the same row. That is `docs/MISTAKES.md` entry 3 exactly, and the fix is a
    second section in the same term whose answer differs.

    It is also the first assertion in E2 of SPEC §4.1 invariant 1 in its structural
    form — a student's read path resolving to another section — but it is not
    marked `invariant`: this is a scheduling answer rather than a confidentiality
    denial, and E2-09 owns the read path and the assertion that goes with it.
    """
    calendar = fall_2026.build()
    _running_row, running = calendar.cohort(A_TWELVE_WEEK_COHORT)
    _later_row, later = calendar.cohort("H")

    for section in (running, later):
        survey_window_service.derive_windows_for_section(
            db_session, section, settings=window_settings
        )

    opens_at, _closes_at = WINDOWS_BY_TERM_WEEK[DST_FALL_BACK_TERM_WEEK]
    inside = opens_at + timedelta(minutes=5)

    for label, section, expected in ((A_TWELVE_WEEK_COHORT, running, True), ("H", later, False)):
        reading = read_at(
            inside,
            clock_overrides=clock_overrides,
            service=survey_window_service,
            session=db_session,
            section=section,
            settings_object=window_settings,
        )
        if expected:
            answered_opens = (
                None
                if reading.answered is None
                else window_instant(reading.answered, WINDOW_OPENS_COLUMN)
            )
            assert answered_opens == opens_at, (
                f"At {inside} the {label!r} section answered a window opening at "
                f"{answered_opens}; its own window for that instant opens at {opens_at}. This "
                f"cohort runs through term week {DST_FALL_BACK_TERM_WEEK}."
            )
        else:
            assert reading.answered is None, (
                f"At {inside} the {label!r} section answered {reading.answered!r} rather than "
                f"`None`. That cohort starts in term week {SEEDED_COHORTS['H'][1]}, five weeks "
                "later, so it has no window then — an answer here is a read that took whichever "
                "window the clock matched, whoever it belonged to."
            )


# ---------------------------------------------------------------------------
# The comparison itself, stood on exactly, through `at=`.
#
# Both ends of a window are inclusive: open iff `opens_at <= at <= closes_at`.
# That sentence differs from the exclusive readings at exactly two instants in the
# whole term week, and the four cases below are those two instants and the two
# microseconds outside them. Nothing here consults the clock; the cases above are
# what say the clock is consulted at all, and the two halves are not
# interchangeable.
# ---------------------------------------------------------------------------


@pytest.fixture
def a_derived_section(
    fall_2026: Any,
    survey_window_service: Any,
    window_settings: Any,
    clock_overrides: Any,
    db_session: Any,
) -> Any:
    """A twelve-week section with its windows derived, under a deliberately wrong clock.

    The clock is left standing five minutes into term week 12's window — a window
    *this same section* has — so that a service which ignored `at` would answer
    that window rather than `None`. Without it, the two cases below that expect
    `None` would pass over a service that never looked at `at` at all and simply
    found nothing open at real time (`docs/MISTAKES.md` entry 3: prefer a premise
    that makes the wrong implementation visible to one that makes it invisible).
    """
    calendar = fall_2026.build()
    _row, section = calendar.cohort(A_TWELVE_WEEK_COHORT)
    survey_window_service.derive_windows_for_section(db_session, section, settings=window_settings)
    clock_overrides.set(pretend_now=A_CLOCK_INSIDE_ANOTHER_WINDOW, anchored_at=datetime.now(UTC))
    return section


def test_the_misleading_clock_the_exact_instant_cases_run_under_really_is_misleading(
    a_derived_section: Any,
    survey_window_service: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """The control on the premise of the four cases below, and it must be green.

    Those four pass `at=` and expect the service to ignore the standing clock.
    That is only evidence if the clock, left alone, would give a *different* and
    visibly wrong answer — so this test asks the same section with no `at` at all
    and requires the neighbouring week's window back.

    A red here means one of three things and none of them is the comparison under
    test: the clock override did not take, the section has no window in the term
    week after the one under test, or the service does not read the clock — and
    the last is what the one-second cases above are for. **A red control means
    these tests are broken, not that the code is.**
    """
    answered = survey_window_service.open_window_for_section(
        db_session, a_derived_section, settings=window_settings
    )
    expected_opens, _expected_closes = WINDOWS_BY_TERM_WEEK[A_NEIGHBOURING_TERM_WEEK]

    assert answered is not None, (
        f"With the clock at {A_CLOCK_INSIDE_ANOTHER_WINDOW} and no `at` given, the service "
        "answered `None`. That instant is five minutes into the section's term week "
        f"{A_NEIGHBOURING_TERM_WEEK} window, so the four exact-instant cases below would be "
        "asking a service that answers `None` at that clock anyway — and their two `None` cases "
        "would pass without `at` having been read."
    )
    assert window_instant(answered, WINDOW_OPENS_COLUMN) == expected_opens, (
        f"With the clock at {A_CLOCK_INSIDE_ANOTHER_WINDOW} the service answered a window opening "
        f"at {window_instant(answered, WINDOW_OPENS_COLUMN)}, and term week "
        f"{A_NEIGHBOURING_TERM_WEEK}'s opens at {expected_opens}. The cases below rest on this "
        "being the answer `at` has to override."
    )


def test_the_opening_instant_itself_is_inside_the_window(
    a_derived_section: Any,
    survey_window_service: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """At exactly `opens_at`, the window is open — the `<=` half at the opening end.

    E2-06 settles the rule as `opens_at <= now <= closes_at`, both ends inclusive.
    This case stands on `opens_at` — 18:00:00.000000 on Friday 30 October 2026 in
    the institution's timezone — and requires the section's own window back.

    **The mutation this kills, and it is the only test in this repository that
    can**: `opens_at <= at` written as `opens_at < at`. Under that reading the
    survey is shut for the microsecond it is supposed to open at and open ever
    after, so every other test in this module agrees with it — the one-second case
    above sits a whole second past the boundary, where the two readings are
    identical, and the derivation tests never ask the question at all. It is a
    one-character edit with no symptom outside this assertion.

    **The near miss it must not pass on**: a service that answers the nearest
    window, or that ignores `at` and reads the clock. The clock is standing five
    minutes inside the *next* term week's window, so an implementation doing
    either answers that one and this fails on the instants.
    """
    opens_at, closes_at = WINDOWS_BY_TERM_WEEK[DST_FALL_BACK_TERM_WEEK]
    answered = answer_at(
        opens_at,
        service=survey_window_service,
        session=db_session,
        section=a_derived_section,
        settings_object=window_settings,
    )

    assert answered is not None, (
        f"At exactly {opens_at} — the instant SPEC §3.1 opens the week's survey — the service "
        "answered `None`. E2-06 settles both ends of the window as inclusive: `opens_at <= at`, "
        "so the opening instant is inside. A `<` here shuts the survey for the moment it is "
        "supposed to open at, which nothing else in this suite can see."
    )
    answered_span = (
        window_instant(answered, WINDOW_OPENS_COLUMN),
        window_instant(answered, WINDOW_CLOSES_COLUMN),
    )
    assert answered_span == (opens_at, closes_at), (
        f"At exactly {opens_at} the service answered the window {answered_span}, and the window "
        f"that instant opens is {(opens_at, closes_at)}. The development clock is standing at "
        f"{A_CLOCK_INSIDE_ANOTHER_WINDOW}, inside term week {A_NEIGHBOURING_TERM_WEEK}'s window, "
        "so an answer of that window is a service that ignored `at`."
    )


def test_one_microsecond_before_the_opening_instant_the_window_is_shut(
    a_derived_section: Any,
    survey_window_service: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """A microsecond before `opens_at`, nothing is open — the other side of that line.

    Paired with the test above and worth nothing without it. "The window is open
    at its opening instant" is satisfied by a service that reports every window
    open always; this is the case that refuses that, one microsecond away, where
    no rounding and no clock drift can explain the difference.

    **The mutation this kills**: an opening comparison dropped altogether, or
    widened to the start of the day, the Friday, or the term week's Monday. Each
    leaves the survey open for hours or days before §3.1 opens it, and each is
    invisible to a test that only ever asks inside the window.

    The clock is standing inside the *next* term week's window, so `None` here is
    `at` having been read and honoured rather than a service that happened to find
    nothing open.
    """
    opens_at, _closes_at = WINDOWS_BY_TERM_WEEK[DST_FALL_BACK_TERM_WEEK]
    just_before = opens_at - ONE_MICROSECOND
    answered = answer_at(
        just_before,
        service=survey_window_service,
        session=db_session,
        section=a_derived_section,
        settings_object=window_settings,
    )

    assert answered is None, (
        f"At {just_before} — one microsecond before the window opens at {opens_at} — the service "
        f"answered {answered!r} rather than `None`. SPEC §3.1 opens the survey Friday at 18:00 in "
        "the institution's timezone and not before; a section open a microsecond early is one "
        "open for however much longer the comparison is wrong by, and this is the only case that "
        "puts a bound on it."
    )


def test_the_closing_instant_itself_is_inside_the_window(
    a_derived_section: Any,
    survey_window_service: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """At exactly `closes_at`, the window is still open — the `<=` half at the closing end.

    SPEC §3.1 closes the survey at 23:59:59, and E2-06 reads that inclusively: the
    second named is the last second a student can submit in. This case stands on
    23:59:59.000000 on Sunday 1 November 2026 — 04:59:59Z, because daylight time
    ended that morning — and requires the window back.

    **The mutation this kills, and it is the only test in this repository that
    can**: `at <= closes_at` written as `at < closes_at`. That shuts the survey a
    microsecond early, which is a whole second early in every spelling a person
    reads, and it makes §3.1's own sentence false — the window would close at
    23:59:58.999999 while the spec, the console and the copy all say 23:59:59.
    Every other case in this module sits at least a second from the boundary,
    where `<` and `<=` agree.

    **The near miss it must not pass on**: a `closes_at` taken as the following
    Monday's midnight, which is also "open at 23:59:59". The instants of the
    answered window are compared, not merely its existence, and
    `test_the_window_closes_at_its_sunday_and_not_after` is what refuses the
    Monday from the other side.
    """
    opens_at, closes_at = WINDOWS_BY_TERM_WEEK[DST_FALL_BACK_TERM_WEEK]
    answered = answer_at(
        closes_at,
        service=survey_window_service,
        session=db_session,
        section=a_derived_section,
        settings_object=window_settings,
    )

    assert answered is not None, (
        f"At exactly {closes_at} — the instant SPEC §3.1 names as the survey's close — the "
        "service answered `None`. E2-06 settles both ends as inclusive, so 23:59:59 is inside the "
        "window and not past it. A `<` here takes the last second of the week away from every "
        "student, and no other test in this suite can tell it from a correct implementation."
    )
    answered_span = (
        window_instant(answered, WINDOW_OPENS_COLUMN),
        window_instant(answered, WINDOW_CLOSES_COLUMN),
    )
    assert answered_span == (opens_at, closes_at), (
        f"At exactly {closes_at} the service answered the window {answered_span}, and the window "
        f"that instant closes is {(opens_at, closes_at)}."
    )


def test_one_microsecond_after_the_closing_instant_the_window_is_shut(
    a_derived_section: Any,
    survey_window_service: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """A microsecond past `closes_at`, nothing is open — the other side of that line.

    The pair to the test above, and the reason it is not satisfied by a service
    that reports every window open forever. One microsecond past 23:59:59 on the
    Sunday, the section has no open survey, and it will not have another until the
    next Friday.

    **The mutation this kills**: a close widened to the end of the Sunday, to the
    following Monday's midnight, or to the section's end date. The first of those
    is one second wide and is exactly what somebody writes when they read "closes
    Sunday 23:59:59" as "closes at the end of Sunday" — a distinction the
    one-second case above cannot make, because Monday 00:00:00 is closed under
    both readings.

    Together with the three cases above this fixes both ends of the window to the
    microsecond, in both directions, which is what E2-06's scope asks for and what
    `docs/MISTAKES.md` entry 3 means by a boundary asserted from both sides.
    """
    _opens_at, closes_at = WINDOWS_BY_TERM_WEEK[DST_FALL_BACK_TERM_WEEK]
    just_after = closes_at + ONE_MICROSECOND
    answered = answer_at(
        just_after,
        service=survey_window_service,
        session=db_session,
        section=a_derived_section,
        settings_object=window_settings,
    )

    assert answered is None, (
        f"At {just_after} — one microsecond after the window closed at {closes_at} — the service "
        f"answered {answered!r} rather than `None`. SPEC §3.1 puts the report after the close, so "
        "a window that outlives its own closing instant is a week that can still change under a "
        "report already generated. The clock is standing at "
        f"{A_CLOCK_INSIDE_ANOTHER_WINDOW}, so an answer here may also be `at` having been ignored "
        "— either way the comparison is not the one E2-06 settles."
    )


@pytest.mark.parametrize(
    ("naive", "why"),
    [
        (NAIVE_INSIDE_THE_WINDOW, "an instant that would be inside the window if it were aware"),
        (NAIVE_OUTSIDE_THE_WINDOW, "an instant that would be outside the window if it were aware"),
    ],
)
def test_a_naive_instant_passed_as_at_is_refused(
    naive: datetime,
    why: str,
    a_derived_section: Any,
    survey_window_service: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """`at` must carry an offset, and a value that does not is refused rather than read.

    ADR 0019 spends a whole `TypeDecorator` keeping naive datetimes out of this
    schema, because "the same value on two differently configured connections is
    two different moments" — and a naive `at` is that hazard one layer up, where
    no column type can catch it. The window instants it would be compared against
    are aware UTC, so a naive value is either an error or a silent reinterpretation
    in whatever zone the reader assumes, and E2-06 settles it as an error.

    **Both directions of the boundary are attempted**, because a guard written
    after the comparison rather than before it refuses only one of them: a naive
    value that falls outside every window can be answered `None` without any
    comparison ever being made. This is `docs/MISTAKES.md` entry 29's shape — a
    value handled before the check that should have refused it — asked from both
    sides so that the check's position is pinned as well as its existence.

    **The near miss it must not pass on, and it is the whole reason the type is
    asserted**: Python raises `TypeError` all by itself when a naive datetime is
    compared with an aware one. That is what an implementation with *no guard at
    all* produces, it arrives with a message about offset-naive and offset-aware
    values that names neither the argument nor the caller's mistake, and a test
    that only asserted "something was raised" would pass over it. So the refusal
    is required to be a deliberate one — a `ValueError`, which is the exception
    ADR 0019 raises for exactly this condition at the column boundary, or an error
    this project defines. Which of those two E2-06 chooses is not settled by the
    work order, and this test admits either.
    """
    with pytest.raises(Exception) as refused:
        answer_at(
            naive,
            service=survey_window_service,
            session=db_session,
            section=a_derived_section,
            settings_object=window_settings,
        )

    raised = refused.value
    assert not isinstance(raised, TypeError), (
        f"Passing {naive!r} as `at` — {why} — raised {raised!r}. A `TypeError` here is Python "
        "refusing to compare an offset-naive datetime with an offset-aware one, which is what a "
        "service with no guard at all does: the message names neither the argument nor what to "
        "attach to it, and the refusal happens only on the code path that reaches a comparison. "
        "E2-06 refuses a naive `at` deliberately, the way ADR 0019 refuses one at the column "
        "boundary."
    )
    defined_here = type(raised).__module__.split(".")[0] == "app"
    assert isinstance(raised, ValueError) or defined_here, (
        f"Passing {naive!r} as `at` raised {type(raised).__name__} from "
        f"{type(raised).__module__}. The refusal has to be one a caller can catch on purpose: a "
        "`ValueError`, which is what ADR 0019's `AwareDateTime` raises for a naive value, or an "
        "error this project defines. Anything else leaked out of something that was not deciding "
        "about this."
    )
