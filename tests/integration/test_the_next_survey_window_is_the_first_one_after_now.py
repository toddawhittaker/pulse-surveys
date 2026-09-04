"""The window a closed section is waiting for — ticket FIX-01, item 4.

FIX-01's fourth item needs one fact the system holds and does not answer: for a
section whose survey is not open, when does the next materialized window open?
The work order settles the reader as
`next_window_for_section(session, section, *, settings, at: datetime | None =
None) -> SurveyWindow | None`, beside E2-06's `open_window_for_section` and with
the same `at` seam.

**`at` is the only way a boundary can be stood on**, and `tests/fixtures/
survey_windows.py` says why: ADR 0109 makes the development clock an *offset*
rather than a freeze, so the effective now keeps moving while it is read and no
override can land exactly on an instant. The two cases this module exists for are
exactly one microsecond apart, so they are asked through that parameter.

**Strictly after, never at.** `open_window_for_section` treats both ends of a
window as inclusive, so at exactly `opens_at` the survey is *open*: that instant
belongs to "open" and never to "next". A `>=` here gives a student a page that
offers this week's form and also announces when the next survey starts, and it is
one character away from correct — which is why the pair below is a microsecond
either side of one literal rather than a day.

**Every instant is transcribed, never computed.** They are
`WINDOWS_BY_TERM_WEEK`'s, the hand-written Fall 2026 calendar that
`tests/unit/test_the_fall_2026_window_calendar_is_spec_3_1s_rhythm.py` controls
against SPEC §3.1's rhythm. Nothing here resolves a Friday, an offset or a zone
(`docs/MISTAKES.md` entry 19).

**The rows are written by hand rather than derived**, for the reason
`tests/fixtures/student_read.py` gives about the same table: routing the fixture
through E2-06's `derive_windows_for_section` would make every assertion here rest
on that service being right as well, and a red would name the wrong ticket. The
instants written are the ones a correct derivation writes, and the control below
reads them back before anything else is believed.

**What is not here.** What the read answer does with this — null while a survey
is open, the reader's own section and no other — is
`test_the_student_read_answer_names_the_next_window.py`'s, over the wire. This
module is the question underneath it.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fixtures.survey_windows import (
    NEXT_WINDOW_FUNCTION,
    SECTION_TABLE,
    SEEDED_COHORTS,
    SURVEY_WINDOW_SERVICE_MODULE,
    SURVEY_WINDOW_TABLE,
    TERM_TABLE,
    WEEK_TABLE,
    WINDOW_CLOSES_COLUMN,
    WINDOW_OPENS_COLUMN,
    WINDOW_SECTION_COLUMN,
    WINDOW_TERM_COLUMN,
    WINDOW_WEEK_COLUMN,
    WINDOWS_BY_TERM_WEEK,
)

pytestmark = pytest.mark.integration

# The section this module asks about, and a second one to be confused with it.
# `U` runs twelve weeks from term week 1 and `R` twelve from term week 4, so both
# of the term weeks below are inside both spans — which means either section
# *could* legally hold either window, and which one actually does is a fact about
# the rows rather than about the calendar.
A_TWELVE_WEEK_COHORT = "U"
A_SECOND_COHORT = "R"

# The two consecutive term weeks the boundary pair is measured across. Away from
# either end of both cohorts' spans, and away from term week 11 — the one week in
# Fall 2026 whose two ends sit on different UTC offsets — so nothing here turns
# on daylight saving, which is E2-06's own case.
BOUNDARY_TERM_WEEK = 7
FOLLOWING_TERM_WEEK = 8

BOUNDARY_OPENS_AT, BOUNDARY_CLOSES_AT = WINDOWS_BY_TERM_WEEK[BOUNDARY_TERM_WEEK]
FOLLOWING_OPENS_AT, FOLLOWING_CLOSES_AT = WINDOWS_BY_TERM_WEEK[FOLLOWING_TERM_WEEK]

# The smallest step a `timestamptz` can tell apart: PostgreSQL stores microseconds
# (ADR 0019's column type), so this is the narrowest gap that survives a round
# trip through the database. A nanosecond would be truncated to nothing and the
# two halves of the pair would be the same instant — a pair that cannot fail.
A_MOMENT = timedelta(microseconds=1)

# A day past the last window's opening, for the "nothing ahead" case. A whole day
# rather than a microsecond because that case is not a boundary: what it asks is
# whether a reader with no candidate rows answers `None` or reaches backwards.
WELL_PAST = timedelta(days=1)

# A Wednesday between term week 6's close and term week 7's open, written out
# rather than computed. Term week 6's window closes at 2026-09-28 03:59:59Z and
# term week 7's opens at 2026-10-02 22:00Z (`WINDOWS_BY_TERM_WEEK`), so noon on
# the 30th of September is inside the gap with days to spare at either end. Used
# only by the scoping case, where what matters is that both sections' windows are
# still ahead.
BETWEEN_TWO_WEEKS = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
def next_window_reader(survey_window_service: Any) -> Any:
    """`next_window_for_section`, or a failure naming the symbol FIX-01 owes.

    The same shape as `survey_window_service` itself and for the same reason: a
    missing name has to be a red *inside* a test that says which deliverable is
    absent, not an `AttributeError` a reader has to decode. It is looked up here
    rather than added to that fixture's required-name list because every E2-06
    suite asks for the same fixture, and a third required name would turn all of
    them red on a symbol their own ticket never promised (`docs/MISTAKES.md`
    entry 22).
    """
    reader = getattr(survey_window_service, NEXT_WINDOW_FUNCTION, None)
    if not callable(reader):
        pytest.fail(
            f"`{SURVEY_WINDOW_SERVICE_MODULE}` exposes no callable `{NEXT_WINDOW_FUNCTION}`; it "
            f"exposes {sorted(n for n in vars(survey_window_service) if not n.startswith('_'))}.\n\n"
            "FIX-01's work order settles it beside `open_window_for_section`, with the same shape: "
            f"`{NEXT_WINDOW_FUNCTION}(session, section, *, settings, at: datetime | None = None) "
            "-> SurveyWindow | None`, answering the first materialized window for that section "
            "whose `opens_at` is strictly after the instant. Item 4's placeholder — 'When the next "
            "survey for this course opens at … it appears here.' — has no date without it."
        )
    return reader


def seed_window(seed_rows: Any, calendar: Any, row: Any, term_week: int) -> Any:
    """One `survey_window` over `term_week` for one seeded section.

    The instants come out of the hand-written table, so the row is the one a
    correct derivation writes; which weeks a section gets is this module's input
    and never its expectation (`docs/MISTAKES.md` entry 30).
    """
    opens_at, closes_at = WINDOWS_BY_TERM_WEEK[term_week]
    return seed_rows(
        SURVEY_WINDOW_TABLE,
        {},
        **{
            WINDOW_SECTION_COLUMN: row[calendar.key_of(SECTION_TABLE)],
            WINDOW_WEEK_COLUMN: calendar.weeks[term_week][calendar.key_of(WEEK_TABLE)],
            WINDOW_TERM_COLUMN: calendar.term[calendar.key_of(TERM_TABLE)],
            WINDOW_OPENS_COLUMN: opens_at,
            WINDOW_CLOSES_COLUMN: closes_at,
        },
    )


def opening_of(answered: Any, what: str) -> Any:
    """One answered window's `opens_at`, or a failure saying what came back instead."""
    assert answered is not None, (
        f"`{NEXT_WINDOW_FUNCTION}` answered `None` {what}, and there is a materialized window "
        "ahead of that instant for this section."
    )
    opens_at = getattr(answered, WINDOW_OPENS_COLUMN, None)
    assert opens_at is not None, (
        f"`{NEXT_WINDOW_FUNCTION}` answered {answered!r}, which carries no "
        f"`{WINDOW_OPENS_COLUMN}`. The work order settles the return as a `SurveyWindow`, and the "
        "sentence FIX-01 renders is built out of that column."
    )
    return opens_at


# ---------------------------------------------------------------------------
# The control on this module's own seeding. A red here means these tests are
# broken, not that the service is.
# ---------------------------------------------------------------------------


def test_the_two_seeded_windows_carry_the_instants_this_module_measures_against(
    fall_2026: Any, seed_rows: Any
) -> None:
    """The premise every assertion below rests on, asserted before any of them.

    Two consecutive windows for one section, at the hand-written Fall 2026
    instants, and nothing else for that section. Each test below then says what
    the reader answered *given* those two rows — so a fixture that wrote one row,
    or three, or the same week twice, would fail the boundary cases against a
    correct implementation and the failure would name the service
    (`docs/MISTAKES.md` entry 13: when a test fails inside its own fixture,
    suspect the fixture first).

    It also asserts the two term weeks sit inside the cohort's span. A window over
    a week the section does not run in is a row nothing would ever derive, and an
    assertion about it would be about a world the product cannot reach.

    **Green today and green after FIX-01 lands**: it names E0-06's `term` and
    `week`, E0-07's derived section columns and E2-05's `survey_window`, and
    nothing this ticket ships.
    """
    length_weeks, first_term_week, _start = SEEDED_COHORTS[A_TWELVE_WEEK_COHORT]
    span = range(first_term_week, first_term_week + length_weeks)
    outside = [week for week in (BOUNDARY_TERM_WEEK, FOLLOWING_TERM_WEEK) if week not in span]
    assert not outside, (
        f"Term week(s) {outside} are outside cohort {A_TWELVE_WEEK_COHORT!r}'s span, which runs "
        f"{length_weeks} weeks from term week {first_term_week}. A window seeded there is a row no "
        "derivation would ever write, so the cases below would be about a world the product cannot "
        "reach."
    )
    assert BOUNDARY_OPENS_AT < FOLLOWING_OPENS_AT, (
        f"Term week {BOUNDARY_TERM_WEEK} opens at {BOUNDARY_OPENS_AT} and term week "
        f"{FOLLOWING_TERM_WEEK} at {FOLLOWING_OPENS_AT}; the second has to be the later, or "
        "'the next one' below names whichever the table happened to order first."
    )

    calendar = fall_2026.build()
    row, section = calendar.cohort(A_TWELVE_WEEK_COHORT)
    for term_week in (BOUNDARY_TERM_WEEK, FOLLOWING_TERM_WEEK):
        seed_window(seed_rows, calendar, row, term_week)

    found = [
        (window["term_week"], window["opens_at"], window["closes_at"])
        for window in calendar.windows_of(section)
    ]
    assert found == [
        (BOUNDARY_TERM_WEEK, BOUNDARY_OPENS_AT, BOUNDARY_CLOSES_AT),
        (FOLLOWING_TERM_WEEK, FOLLOWING_OPENS_AT, FOLLOWING_CLOSES_AT),
    ], (
        f"The section carries {found}. This module seeds exactly two windows, over term weeks "
        f"{BOUNDARY_TERM_WEEK} and {FOLLOWING_TERM_WEEK}, at SPEC §3.1's instants over those "
        "weeks. A third row means something else wrote into this section's table and every "
        "'the next one is…' assertion below would be about a window nobody here chose."
    )


# ---------------------------------------------------------------------------
# The boundary: strictly after, never at.
# ---------------------------------------------------------------------------


def test_a_moment_before_a_window_opens_that_window_is_the_next_one(
    fall_2026: Any,
    seed_rows: Any,
    next_window_reader: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """One microsecond before term week 7 opens, term week 7 is what is coming.

    The ordinary case, and the half of the pair that says the reader can see a
    window at all. A student reading their page at this instant has a closed
    section and a survey minutes away, and the placeholder is entitled to name it.

    **The mutations this kills.** A reader written `>=` on the *closing* instant
    rather than the opening one, which answers term week 8 here — the window after
    the one about to start. A reader ordered descending, which answers the last
    window of the term. And a reader that returns nothing until the window is
    already open, which is the field never being filled.

    **The near miss it must survive** is its sibling below, a microsecond later,
    where this same window must stop being the answer. Either test alone passes
    against a comparison written the wrong way round.

    **The seeding is controlled** by the test above, which reads both rows back
    at these instants before any of this is believed.
    """
    calendar = fall_2026.build()
    row, section = calendar.cohort(A_TWELVE_WEEK_COHORT)
    for term_week in (BOUNDARY_TERM_WEEK, FOLLOWING_TERM_WEEK):
        seed_window(seed_rows, calendar, row, term_week)

    answered = next_window_reader(
        db_session, section, settings=window_settings, at=BOUNDARY_OPENS_AT - A_MOMENT
    )
    opens_at = opening_of(answered, f"a microsecond before {BOUNDARY_OPENS_AT}")

    assert opens_at == BOUNDARY_OPENS_AT, (
        f"A microsecond before term week {BOUNDARY_TERM_WEEK}'s window opens, "
        f"`{NEXT_WINDOW_FUNCTION}` answered a window opening at {opens_at} — and the window about "
        f"to open is {BOUNDARY_OPENS_AT}.\n\n"
        f"{FOLLOWING_OPENS_AT} is the week after the one that is about to start: a comparison made "
        "against `closes_at` rather than `opens_at`, or an ordering that skipped the first row. "
        "This is the instant a student refreshing the page just before six on a Friday is reading "
        "at."
    )


def test_at_the_instant_a_window_opens_it_is_no_longer_the_one_coming_next(
    fall_2026: Any,
    seed_rows: Any,
    next_window_reader: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """Exactly at term week 7's opening, the next window is term week 8's.

    The other half of the pair, one microsecond later. At `opens_at` the survey is
    **open** — `open_window_for_section` reads both ends of a window inclusively —
    so this window is the one on screen and not the one being waited for. The
    reader has to be strictly `>`, and this is the case that says so.

    **The mutation this kills** is exactly one character: `>=` in place of `>`.
    It answers term week 7's own instant here, which is the moment the page is
    rendering a form for, and no other test in this repository can see it — the
    development clock is an offset that keeps moving, so nothing but this `at`
    seam can stand on the instant itself.

    **The near miss it must survive**: the correct answer, term week 8's opening,
    which is the window genuinely coming next. A reader that answered `None` here
    would also be wrong — there *is* a window ahead — and fails on the same
    assertion, naming what it gave.

    **The seeding is controlled** by this module's first test.
    """
    calendar = fall_2026.build()
    row, section = calendar.cohort(A_TWELVE_WEEK_COHORT)
    for term_week in (BOUNDARY_TERM_WEEK, FOLLOWING_TERM_WEEK):
        seed_window(seed_rows, calendar, row, term_week)

    answered = next_window_reader(
        db_session, section, settings=window_settings, at=BOUNDARY_OPENS_AT
    )
    opens_at = opening_of(answered, f"exactly at {BOUNDARY_OPENS_AT}")

    assert opens_at == FOLLOWING_OPENS_AT, (
        f"Asked at exactly {BOUNDARY_OPENS_AT} — the instant term week {BOUNDARY_TERM_WEEK}'s "
        f"window opens — `{NEXT_WINDOW_FUNCTION}` answered a window opening at {opens_at}. The "
        f"window coming next is term week {FOLLOWING_TERM_WEEK}'s, at {FOLLOWING_OPENS_AT}.\n\n"
        f"{BOUNDARY_OPENS_AT} is the `>=` defect, and it is one character: at that instant the "
        "survey is open, because a window includes both its ends. A page would then offer this "
        "week's form and, beside it, announce when the next survey opens — which is the closed "
        "state's sentence shown to somebody who has a form in front of them."
    )


def test_a_section_whose_windows_have_all_opened_has_nothing_coming_next(
    fall_2026: Any,
    seed_rows: Any,
    next_window_reader: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """Past the last window, the answer is `None` and never the one behind.

    FIX-01 item 4 keeps the undated sentence for "a section with no future
    window", and that sentence is reached through this `None`. A section at the
    end of its term has every window behind it, and a reader that reached
    backwards would render a date that has already gone.

    **The mutations this kills.** A reader that drops its instant comparison
    altogether and answers the section's first window, which is months in the
    past. One ordered descending with no comparison, which answers the last. And
    one that answers the *closest* window in either direction, which reads as
    helpful and is wrong every time.

    **The near miss it must survive** is the pair above, where windows do lie
    ahead and one of them must be named — so this `None` is a statement about the
    instant rather than about a reader that never finds anything
    (`docs/MISTAKES.md` entry 3).
    """
    calendar = fall_2026.build()
    row, section = calendar.cohort(A_TWELVE_WEEK_COHORT)
    for term_week in (BOUNDARY_TERM_WEEK, FOLLOWING_TERM_WEEK):
        seed_window(seed_rows, calendar, row, term_week)

    answered = next_window_reader(
        db_session, section, settings=window_settings, at=FOLLOWING_OPENS_AT + WELL_PAST
    )

    assert answered is None, (
        f"A day after the last of this section's windows opened, `{NEXT_WINDOW_FUNCTION}` answered "
        f"{answered!r}, opening at {getattr(answered, WINDOW_OPENS_COLUMN, None)}. Its two windows "
        f"opened at {BOUNDARY_OPENS_AT} and {FOLLOWING_OPENS_AT}, both behind this instant.\n\n"
        "A window behind the reader is not a window coming next, and the sentence built out of one "
        "promises a survey on a date that has passed. FIX-01 item 4: a section with no future "
        "window keeps the undated sentence."
    )


# ---------------------------------------------------------------------------
# Whose window it is.
# ---------------------------------------------------------------------------


def test_the_next_window_is_this_sections_own_and_not_the_earliest_in_the_term(
    fall_2026: Any,
    seed_rows: Any,
    next_window_reader: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """Two sections of one course, and the earlier window belongs to the other one.

    The section asked about holds one window, over term week 8. A sibling section
    of the same course and the same term holds one over term week 7 — earlier, and
    still ahead of the instant both are read at. So the earliest future window in
    the database is not this section's, and a reader that ordered by `opens_at`
    without naming a section answers the wrong one.

    **The order of the pair is the whole test.** Were the asked-for section's
    window the earlier of the two, an unscoped query would return exactly what the
    correct query returns and the mutation would survive with the suite green —
    which is the shape `docs/MISTAKES.md` entry 3 is about and the shape E2-09's
    mutation battery measured on this project's other section-scoped read.

    **The mutations this kills.** A `select` with no `section_id` predicate. One
    joined to the course, to the term or to the week — `Fall2026` seeds every
    section it is asked for under one containment chain, so all three reach the
    sibling's row. And a predicate written against the *week's* section rather
    than the window's.

    **The near miss it must survive**: the correct answer, term week 8's instant,
    which is this section's only window and is genuinely ahead.

    **The canary, first**: both rows are required to exist, at the instants this
    test names, and the sibling's is required to be the earlier.
    """
    assert BOUNDARY_OPENS_AT < FOLLOWING_OPENS_AT, (
        f"The sibling's window ({BOUNDARY_OPENS_AT}) is not earlier than this section's "
        f"({FOLLOWING_OPENS_AT}), so an unscoped lookup would answer correctly anyway."
    )
    assert BETWEEN_TWO_WEEKS < BOUNDARY_OPENS_AT, (
        f"{BETWEEN_TWO_WEEKS} is not before the sibling's window opens at {BOUNDARY_OPENS_AT}, so "
        "that window is not something an unscoped 'next' query would reach and this test asserts "
        "nothing."
    )

    calendar = fall_2026.build()
    mine_row, mine = calendar.cohort(A_TWELVE_WEEK_COHORT)
    sibling_row, sibling = calendar.cohort(A_SECOND_COHORT)
    seed_window(seed_rows, calendar, mine_row, FOLLOWING_TERM_WEEK)
    seed_window(seed_rows, calendar, sibling_row, BOUNDARY_TERM_WEEK)

    assert [window["term_week"] for window in calendar.windows_of(mine)] == [
        FOLLOWING_TERM_WEEK
    ] and [window["term_week"] for window in calendar.windows_of(sibling)] == [
        BOUNDARY_TERM_WEEK
    ], (
        "The two sections did not get one window each over the weeks this test names: the asked-for "
        f"section carries {calendar.windows_of(mine)} and the sibling "
        f"{calendar.windows_of(sibling)}."
    )

    answered = next_window_reader(db_session, mine, settings=window_settings, at=BETWEEN_TWO_WEEKS)
    opens_at = opening_of(answered, f"at {BETWEEN_TWO_WEEKS}")

    assert opens_at == FOLLOWING_OPENS_AT, (
        f"Asked for this section at {BETWEEN_TWO_WEEKS}, `{NEXT_WINDOW_FUNCTION}` answered a "
        f"window opening at {opens_at}. This section's own next window opens at "
        f"{FOLLOWING_OPENS_AT}; {BOUNDARY_OPENS_AT} belongs to a sibling section of the same "
        "course.\n\n"
        "The earlier instant here is a lookup with no `section_id` predicate, or one joined to the "
        "course, the term or the week. SPEC §4.1 item 1: a student is never shown another section, "
        "and the date a page announces is a fact about somebody's calendar."
    )
