"""The control on E2-06's hand-computed window calendar — it must be green today.

`tests/fixtures/survey_windows.py` holds thirty-six UTC literals: the instant every
Fall 2026 survey window opens and closes, one pair per term week. Every assertion
E2-06 makes about the derivation compares the service's answer against those
literals rather than against arithmetic (`docs/MISTAKES.md` entry 19), which means
a wrong literal is a wrong test rather than a caught defect — and the failure
would read as a defect in the service.

**So this module is the fixture's own control, and a red here means these tests
are broken, not that the code is.** It needs no database, no service and no
implementation: it reads each literal back into `America/New_York` and requires
it to be the thing SPEC §3.1 describes, on the term-week Monday
`scripts/seed.py`'s calendar puts it on. It is green before E2-06 is written and
stays green afterwards.

**`ZoneInfo` here is not the thing under test.** The service converts a wall time
in the institution's zone to an aware UTC instant; this module converts the other
way, off a literal a person wrote, to check the person. Nothing in E2-06 is
consulted, so this is not a test holding its expectation in a copy of its subject
— it is the sample being checked against the standard library's tz database,
which is also what makes a container with a stale tzdata edition fail here,
naming the tzdata, rather than three modules away naming the derivation.

The two things it exists to catch, both of which have a name in this project:

  - **A literal typed one hour out at the daylight-saving boundary.** Term week 11
    opens at UTC-4 and closes at UTC-5, and it is the only week in the term that
    does. Every window assertion that matters rests on that row being right, and
    it is the one row a reader is most likely to "correct".
  - **A cohort's first term week written down wrong.** `SEEDED_COHORTS` carries
    both the seed's own start date and this suite's reading of which term week
    that date is. Checking the two against each other is what stops a section's
    whole window set being asserted against the wrong six weeks of the calendar.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fixtures.survey_windows import (
    CLOSES_WALL_CLOCK,
    CLOSES_WEEKDAY,
    DST_FALL_BACK_SUNDAY,
    DST_FALL_BACK_TERM_WEEK,
    FALL_2026_TERM_END,
    FALL_2026_TERM_START,
    FALL_2026_TERM_WEEKS,
    INSTITUTION_TIMEZONE,
    MONDAY,
    OPENS_WALL_CLOCK,
    OPENS_WEEKDAY,
    SEEDED_COHORTS,
    WINDOWS_BY_TERM_WEEK,
)

DAYS_PER_WEEK = 7

# The offsets `America/New_York` runs on, as `utcoffset()` reports them. Daylight
# time is UTC-4 and standard time is UTC-5, and 2026's transition back is the
# first Sunday in November.
DAYLIGHT_OFFSET = timedelta(hours=-4)
STANDARD_OFFSET = timedelta(hours=-5)


def institution_local(instant: datetime) -> datetime:
    """One UTC literal, read back as a wall time in the institution's zone."""
    return instant.astimezone(ZoneInfo(INSTITUTION_TIMEZONE))


def test_the_term_calendar_matches_the_seeds_own_dates() -> None:
    """The premise everything else in this file rests on: eighteen weeks from a Monday.

    `scripts/seed.py` writes `TERM_START = date(2026, 8, 17)`, `TERM_END =
    date(2026, 12, 20)` and `TERM_LENGTH_WEEKS = 18`, and ADR 0020 makes the end
    date the last day inclusive. If those three do not agree, every term-week
    Monday below is off and so is every window on it.
    """
    assert FALL_2026_TERM_START.weekday() == MONDAY, (
        f"{FALL_2026_TERM_START} is not a Monday. SPEC §2.2's Fall 2026 calendar runs from a "
        "Monday, and the Friday and Sunday of each term week are counted from it."
    )
    last_day = FALL_2026_TERM_START + timedelta(days=FALL_2026_TERM_WEEKS * DAYS_PER_WEEK - 1)
    assert last_day == FALL_2026_TERM_END, (
        f"Eighteen weeks from {FALL_2026_TERM_START} ends {last_day}, and the seed writes "
        f"{FALL_2026_TERM_END}. The two disagree, so either the length or the end date "
        "transcribed from `scripts/seed.py` is wrong."
    )


def test_every_term_week_has_a_hand_written_window_and_no_others_do() -> None:
    """The table covers the term exactly — eighteen rows, numbered 1 to 18.

    A missing row would make the section that runs through that week assert
    against fewer windows than it has, and the assertion would still be an
    equality of two lists — it would just be the wrong pair. An extra row would
    put a window in a week the term does not have.
    """
    assert set(WINDOWS_BY_TERM_WEEK) == set(range(1, FALL_2026_TERM_WEEKS + 1)), (
        f"The hand-written calendar covers term weeks {sorted(WINDOWS_BY_TERM_WEEK)}, and Fall "
        f"2026 has weeks 1 to {FALL_2026_TERM_WEEKS}. E0-06 emits a term's weeks as 1..N."
    )


@pytest.mark.parametrize("term_week", sorted(WINDOWS_BY_TERM_WEEK))
def test_each_written_window_opens_friday_1800_and_closes_sunday_235959_in_the_institution_zone(
    term_week: int,
) -> None:
    """Each literal is SPEC §3.1's rhythm on that term week's own Friday and Sunday.

    §3.1: "opens Friday 18:00, closes Sunday 23:59:59 … in the institution
    timezone (default `America/New_York`)". Term week M's Monday is the term start
    plus `(M - 1) x 7` days, so the Friday is that Monday plus four days and the
    Sunday is that Monday plus six.

    **The mutation this kills is a typo, and typos in a table of thirty-six
    timestamps are invisible.** A literal an hour out, a day out, or on the wrong
    side of midnight reads exactly like the other thirty-five until something is
    compared against it.

    Both instants are also required to be aware and to be UTC, because the column
    they will be compared against refuses a naive value outright (ADR 0019) and an
    expectation written in local time would compare unequal to every correct
    answer.
    """
    opens_at, closes_at = WINDOWS_BY_TERM_WEEK[term_week]
    monday = FALL_2026_TERM_START + timedelta(days=(term_week - 1) * DAYS_PER_WEEK)

    for label, instant in (("opens_at", opens_at), ("closes_at", closes_at)):
        assert instant.tzinfo is not None and instant.utcoffset() == timedelta(0), (
            f"Term week {term_week}'s {label} is written as {instant!r}, which is not an aware UTC "
            "instant. ADR 0019 stores every window instant as aware UTC, so an expectation in any "
            "other zone — or a naive one — compares unequal to every correct answer."
        )

    opens_local = institution_local(opens_at)
    closes_local = institution_local(closes_at)

    assert (opens_local.date(), opens_local.weekday()) == (
        monday + timedelta(days=OPENS_WEEKDAY),
        OPENS_WEEKDAY,
    ), (
        f"Term week {term_week} opens at {opens_at!r}, which is {opens_local!r} in "
        f"{INSTITUTION_TIMEZONE}. That week's Monday is {monday}, so its Friday is "
        f"{monday + timedelta(days=OPENS_WEEKDAY)}."
    )
    assert (opens_local.hour, opens_local.minute, opens_local.second) == OPENS_WALL_CLOCK, (
        f"Term week {term_week} opens at {opens_local!r} local, and SPEC §3.1 opens the window at "
        f"{OPENS_WALL_CLOCK[0]:02d}:{OPENS_WALL_CLOCK[1]:02d}:{OPENS_WALL_CLOCK[2]:02d}."
    )

    assert (closes_local.date(), closes_local.weekday()) == (
        monday + timedelta(days=CLOSES_WEEKDAY),
        CLOSES_WEEKDAY,
    ), (
        f"Term week {term_week} closes at {closes_at!r}, which is {closes_local!r} in "
        f"{INSTITUTION_TIMEZONE}. That week's Monday is {monday}, so its Sunday is "
        f"{monday + timedelta(days=CLOSES_WEEKDAY)}."
    )
    assert (closes_local.hour, closes_local.minute, closes_local.second) == CLOSES_WALL_CLOCK, (
        f"Term week {term_week} closes at {closes_local!r} local, and SPEC §3.1 closes the window "
        f"at {CLOSES_WALL_CLOCK[0]:02d}:{CLOSES_WALL_CLOCK[1]:02d}:{CLOSES_WALL_CLOCK[2]:02d}."
    )


def test_exactly_one_term_week_straddles_the_daylight_saving_fall_back() -> None:
    """Week 11 opens on daylight time and closes on standard time, and no other week does.

    This is the row the whole "one zone conversion per instant" claim rests on,
    so it is checked as a property of the calendar rather than left implicit in
    one literal among thirty-six. Daylight time in the United States ends on the
    first Sunday in November — 2026-11-01 — which is the Sunday term week 11
    closes on, and 18:00 on the Friday before it is still daylight time.

    **The mutation this kills**: a calendar rewritten so that both ends of week 11
    carry the same offset. That is precisely the wrong answer an implementation
    computing one offset per window would give, so a fixture holding it would make
    the defect and the expectation agree.
    """
    straddling = sorted(
        term_week
        for term_week, (opens_at, closes_at) in WINDOWS_BY_TERM_WEEK.items()
        if institution_local(opens_at).utcoffset() != institution_local(closes_at).utcoffset()
    )

    assert straddling == [DST_FALL_BACK_TERM_WEEK], (
        f"Term weeks {straddling} open and close on different UTC offsets, and exactly "
        f"[{DST_FALL_BACK_TERM_WEEK}] should. Daylight time ends on {DST_FALL_BACK_SUNDAY}, the "
        "Sunday term week 11 closes on."
    )

    opens_at, closes_at = WINDOWS_BY_TERM_WEEK[DST_FALL_BACK_TERM_WEEK]
    assert institution_local(opens_at).utcoffset() == DAYLIGHT_OFFSET, (
        f"Term week {DST_FALL_BACK_TERM_WEEK} opens at {opens_at!r}, which is not on daylight "
        f"time ({DAYLIGHT_OFFSET}). Friday 30 October 2026 18:00 is two days before the switch."
    )
    assert institution_local(closes_at).utcoffset() == STANDARD_OFFSET, (
        f"Term week {DST_FALL_BACK_TERM_WEEK} closes at {closes_at!r}, which is not on standard "
        f"time ({STANDARD_OFFSET}). The clocks go back at 02:00 on {DST_FALL_BACK_SUNDAY}, so "
        "23:59:59 that evening is UTC-5."
    )
    assert institution_local(closes_at).date() == DST_FALL_BACK_SUNDAY, (
        f"Term week {DST_FALL_BACK_TERM_WEEK} does not close on {DST_FALL_BACK_SUNDAY}, so this "
        "module is naming the wrong week as the daylight-saving one."
    )


@pytest.mark.parametrize("letter", sorted(SEEDED_COHORTS))
def test_each_cohorts_first_term_week_is_the_week_the_seeds_own_start_date_falls_in(
    letter: str,
) -> None:
    """The two numbers in `SEEDED_COHORTS` are checked against each other.

    Each row carries the start date `scripts/seed.py::START_LETTER_MAP` writes and
    the term week this suite reads it as. Only the date is transcribed; the week
    number is a reading, and a reading that is one out moves a section's entire
    window set one week along the calendar — where every instant is still a
    plausible Friday 18:00 and nothing looks wrong.

    Each cohort is also required to end inside the term. A cohort whose last
    course week has no term week has no `week` row either, which is ADR 0018's
    gap — a case E2-06 tolerates on purpose and one no criterion-1 assertion
    should be silently resting on.
    """
    length_weeks, first_term_week, start = SEEDED_COHORTS[letter]
    expected_start = FALL_2026_TERM_START + timedelta(days=(first_term_week - 1) * DAYS_PER_WEEK)

    assert start == expected_start, (
        f"Cohort {letter!r} is read here as starting in term week {first_term_week}, whose Monday "
        f"is {expected_start}, and `scripts/seed.py` gives it {start}. One of the two is wrong, "
        "and a section asserted against the wrong weeks of the calendar fails against a correct "
        "derivation."
    )
    assert start.weekday() == MONDAY, (
        f"Cohort {letter!r} starts on {start}, a {start.strftime('%A')}. Every start date in "
        "§2.2's map is a Monday, which is what makes a course week line up with a term week at "
        "all."
    )
    last_term_week = first_term_week + length_weeks - 1
    assert last_term_week <= FALL_2026_TERM_WEEKS, (
        f"Cohort {letter!r} runs {length_weeks} weeks from term week {first_term_week}, ending in "
        f"term week {last_term_week}, and Fall 2026 has {FALL_2026_TERM_WEEKS}. The seeded "
        "calendar fits every cohort inside the term; a cohort that did not would be ADR 0018's "
        "missing-week case rather than criterion 1's."
    )


def test_the_calendar_and_the_cohorts_are_not_empty() -> None:
    """The non-emptiness guard the two parametrized tests above cannot make for themselves.

    `docs/MISTAKES.md` entry 3: a `parametrize` over an empty collection collects
    nothing and reports green, so "every window is Friday 18:00" and "every cohort
    lines up" are both trivially true of a fixture whose tables have been emptied.
    This is the one assertion in the module that would notice.

    The counts are the spec's own: §2.2's Fall 2026 map names twenty start
    positions, and fall terms are eighteen weeks.
    """
    assert len(WINDOWS_BY_TERM_WEEK) == FALL_2026_TERM_WEEKS, (
        f"The window calendar holds {len(WINDOWS_BY_TERM_WEEK)} term weeks and Fall 2026 has "
        f"{FALL_2026_TERM_WEEKS}."
    )
    assert len(SEEDED_COHORTS) == 20, (
        f"`SEEDED_COHORTS` holds {len(SEEDED_COHORTS)} start positions. SPEC §2.2's Fall 2026 map "
        "names twenty — 12-week U/R/Q, 6-week E/F/H, 8-week X/Y/Z, 10-week S/T, 15-week V/D, "
        "16-week K, and the 3-week sections numbered 2 through 7 — and `scripts/seed.py` seeds "
        "all of them."
    )
