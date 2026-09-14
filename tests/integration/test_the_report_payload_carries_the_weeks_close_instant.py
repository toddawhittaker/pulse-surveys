"""The reported week's own close instant, and the zone it is read in — ticket E5-02.

> 1. The payload carries both question texts and the close instant; the schema
>    types them and the route serves them.
> 3. The close instant equals the reported week's window row's close, not the
>    current week's — asserted on a back-navigated week.
> 6. Each half proven against the mockup, per the carried entry's done-when.

The mockup's eyebrow reads `responses closed Sun 11:59 PM`
(`design/InstructorMondayReport.dc.html:227`) and nothing on the payload carries
the instant behind it. The instant is on the `survey_window` row the report read
already holds, so this is a member rather than a query — and the whole of
criterion 3 is *which* window row: a report is paged back across published weeks
(SPEC §5.1, "week navigation pages across published weeks"), so the close that
means anything is the reported week's, never today's.

**The pair.** A single week proves nothing here: a read hard-coded to the section's
first window passes a test asserting a back-navigated week, and a read hard-coded
to the latest passes one asserting the latest. So both are asserted, against the
hand-written calendar's own instants, and each test names the other's value in its
failure message.

**The timezone half is measured across the fall-back boundary.** The institution's
zone is what the eyebrow formats in — never the browser's guess, which is the
ticket's own known trap — so the payload carries the IANA name beside the instant.
Course week 5 of this world is term week 11, whose window closes on 2026-11-01,
the Sunday `America/New_York` puts its clocks back on
(`tests/fixtures/survey_windows.py`, and the calendar test that pins it). Read in
the served zone, that instant is a Sunday at 23:59:59 like every other week's; read
against a fixed offset, or with UTC served as the zone, it is not.

**Which failure a red is, before E5-02 lands.** `report_api_contract`'s `member` is
a `pytest.fail` naming the missing payload member, so the first red is a FAILED
naming what is owed (`docs/MISTAKES.md` entry 44).
"""

from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fixtures.report_api import (
    CONFIG_MODULE,
    IN_DENOMINATOR_WEEK,
    OUT_OF_DENOMINATOR_WEEK,
    SILENT_WEEK,
    TERM_WEEK_OF_COURSE_WEEK,
    ReportDoor,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.survey_windows import (
    CLOSES_WALL_CLOCK,
    CLOSES_WEEKDAY,
    DST_FALL_BACK_SUNDAY,
    DST_FALL_BACK_TERM_WEEK,
    INSTITUTION_TIMEZONE,
    WINDOWS_BY_TERM_WEEK,
)

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
MOCKUP = REPO_ROOT / "design" / "InstructorMondayReport.dc.html"

# Three lines of the mockup, **copied whole out of the file** — the rule
# `docs/MISTAKES.md` entry 3 gives for building a canary sample, because a
# sentence retyped from where you think it begins is the thing the sample exists
# to disprove. The first two are the histogram titles E5-02's question texts feed;
# the third is the eyebrow note the close instant feeds.
MOCKUP_HISTOGRAM_TITLES = (
    '<dc-import name="RatingHistogram" title="“My instructor supported my learning”"',
    '<dc-import name="RatingHistogram" title=' '"“Materials and activities supported my learning”"',
)
MOCKUP_EYEBROW_NOTE = "      eyebrowNote: 'responses closed Sun 11:59 PM',"

# The name of the `Settings` field the work order reads the zone from: "the IANA
# name from settings.institution_timezone". Spelled rather than discovered,
# because the work order settles it and `.env.example` documents the variable.
INSTITUTION_TIMEZONE_SETTING = "institution_timezone"

BOTH_STREAMS = (INSTRUCTOR_STREAM, COURSE_STREAM)


def mockup_text() -> str:
    """The design mockup, with the canary that says the reader still finds it.

    A test that located nothing in this file would otherwise report "the mockup
    asks for no close note" — the silent pass `docs/MISTAKES.md` entry 3 is about.
    """
    assert MOCKUP.is_file(), (
        f"{MOCKUP} does not exist, so this test read nothing. It is the design artifact E5-02's "
        "criterion 6 is proven against."
    )
    text = MOCKUP.read_text(encoding="utf-8")
    missing = [line for line in (*MOCKUP_HISTOGRAM_TITLES, MOCKUP_EYEBROW_NOTE) if line not in text]
    assert not missing, (
        f"{MOCKUP.relative_to(REPO_ROOT)} no longer carries {missing}. These lines are copied whole "
        "out of the mockup and are what this test reads the design's two server-fed details off; if "
        "the mockup has been re-cut, the constants at the top of this module are what change — a "
        "reader that cannot find them would otherwise report a design that needs nothing."
    )
    return text


def served_close(door: ReportDoor, contract: Any, *, course_week: int) -> datetime:
    """The close instant one report serves for its week, parsed and required to be aware."""
    body, answered = door.payload(course_week=course_week)
    found = contract.member(body, contract.week_member, contract.closes_at_field, answered=answered)
    assert isinstance(found, str) and found, (
        f"`{contract.week_member}.{contract.closes_at_field}` for course week {course_week} came "
        f"back as {found!r}; a datetime member serialises to an ISO 8601 string on the wire."
    )
    parsed = datetime.fromisoformat(found)
    assert parsed.tzinfo is not None and parsed.utcoffset() is not None, (
        f"The close instant served for course week {course_week} is {found!r}, which carries no "
        "offset. ADR 0019 stores every window instant as aware UTC, and a naive instant on the wire "
        "is one the browser resolves in whatever zone it is standing in."
    )
    return parsed


def served_timezone(door: ReportDoor, contract: Any, *, course_week: int) -> str:
    """The IANA zone name one report serves at its top level."""
    body, answered = door.payload(course_week=course_week)
    found = contract.member(body, contract.institution_timezone_member, answered=answered)
    assert isinstance(found, str) and found, (
        f"`{contract.institution_timezone_member}` came back as {found!r}; E5-02 serves the IANA "
        "name of the institution's zone, mirroring the student payload."
    )
    return found


def configured_institution_timezone() -> str:
    """`Settings.institution_timezone`, or a failure naming the field.

    Built here rather than compared against a constant this file holds, for the
    reason `tests/fixtures/report_api.py::configured_benchmark_minimums` gives:
    the claim under test is that the payload names *the configured zone*, and a
    comparison against a zone this module invented would assert something else.
    """
    module = import_module(CONFIG_MODULE)
    settings_class = getattr(module, "Settings", None)
    assert settings_class is not None, f"`{CONFIG_MODULE}` exposes no `Settings`."
    found = getattr(settings_class(), INSTITUTION_TIMEZONE_SETTING, None)
    assert isinstance(found, str) and found, (
        f"`Settings.{INSTITUTION_TIMEZONE_SETTING}` is {found!r}. `.env.example` documents "
        "`INSTITUTION_TIMEZONE`, and SPEC §3.1 makes it the zone every window instant is read in."
    )
    return found


def test_a_back_navigated_weeks_report_carries_that_weeks_own_close_instant(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """Criterion 3, stated as it is written: not the current week's.

    Course week 2 of this six-week section, read with the clock standing after the
    last window has closed, so every week is published and the requested one is
    five weeks behind the latest.

    **The mutation this kills:** the close taken from the section's latest window,
    or from the window the clock is standing in, rather than from the reported
    week's row — a read that is right on the one week an instructor opens by
    default and wrong on every week they page back to.
    """
    term_week = TERM_WEEK_OF_COURSE_WEEK[IN_DENOMINATOR_WEEK]
    expected = WINDOWS_BY_TERM_WEEK[term_week][1]
    latest = WINDOWS_BY_TERM_WEEK[TERM_WEEK_OF_COURSE_WEEK[SILENT_WEEK]][1]
    assert expected != latest, (
        f"Course week {IN_DENOMINATOR_WEEK} and course week {SILENT_WEEK} close at the same instant "
        f"({expected}), so this test could not tell the reported week's window from the latest one."
    )

    served = served_close(report_door, report_api_contract, course_week=IN_DENOMINATOR_WEEK)

    assert served == expected, (
        f"The report for course week {IN_DENOMINATOR_WEEK} serves {served.isoformat()} as its "
        f"week's close. That week is term week {term_week}, whose window closes {expected.isoformat()} "
        f"in the hand-written Fall 2026 calendar; the latest published week's window closes "
        f"{latest.isoformat()}."
    )


def test_the_latest_published_weeks_report_carries_its_own_close_instant(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The other half of the pair: the back-navigated assertion alone is satisfiable.

    A read that served the section's *first* window for every week would pass the
    test above whenever the test's week is the first one — and would pass this
    module with one assertion in it. The latest week is where that read is wrong,
    so it is asserted here, against the same hand-written calendar.

    **The mutation this kills:** the close taken from the section's earliest window
    (a `min`, or the first row of an ordered window list) rather than the reported
    week's.
    """
    term_week = TERM_WEEK_OF_COURSE_WEEK[SILENT_WEEK]
    expected = WINDOWS_BY_TERM_WEEK[term_week][1]
    earliest = WINDOWS_BY_TERM_WEEK[TERM_WEEK_OF_COURSE_WEEK[IN_DENOMINATOR_WEEK]][1]

    served = served_close(report_door, report_api_contract, course_week=SILENT_WEEK)

    assert served == expected, (
        f"The report for course week {SILENT_WEEK} serves {served.isoformat()} as its week's close. "
        f"That week is term week {term_week}, whose window closes {expected.isoformat()}; course "
        f"week {IN_DENOMINATOR_WEEK}'s closes {earliest.isoformat()}."
    )


def test_the_payload_names_the_institution_timezone_the_deployment_is_configured_with(
    report_door: ReportDoor, report_api_contract: Any, configured_env: Any
) -> None:
    """Criterion 1 for the third member: the zone the instant is rendered in, served.

    The close instant is stored aware and travels as an instant; the eyebrow
    renders it as a weekday and a wall-clock time, which is a statement in one
    particular zone. The institution's zone is configuration the server holds and
    the browser does not, so a payload carrying the instant without the zone
    cannot be rendered correctly by any client.

    **The mutation this kills:** the member hard-coded to `America/New_York` or to
    `UTC` rather than read from settings, which is correct on the development
    stack and wrong for the first deployment that configures anything else.
    """
    configured = configured_institution_timezone()
    served = served_timezone(report_door, report_api_contract, course_week=IN_DENOMINATOR_WEEK)

    assert served == configured, (
        f"The payload names {served!r} as the institution's zone and this deployment is configured "
        f"with `{INSTITUTION_TIMEZONE_SETTING}={configured}`."
    )
    ZoneInfo(served)


def test_the_close_instant_read_in_the_served_zone_is_the_sunday_night_the_eyebrow_shows(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The two members used together, on the week where a shortcut is wrong.

    Course week 5 of this world is term week 11, whose window closes on
    2026-11-01 — the Sunday `America/New_York` returns to standard time. SPEC
    §3.1 closes every window at 23:59:59 in the institution's zone, and the
    mockup's eyebrow says `responses closed Sun 11:59 PM`, so reading the served
    instant in the served zone has to give a Sunday at 23:59:59 on that date.

    **The mutation this kills:** a close instant converted with a fixed offset —
    the summer one, which puts this week's close at 00:59:59 on the Monday, or the
    winter one, which does the same to every week before the boundary; and the
    zone member served as `UTC`, which puts every close on a Monday morning. Both
    are invisible on the weeks either side of the transition, and both would ship
    an eyebrow that names the wrong day.
    """
    term_week = TERM_WEEK_OF_COURSE_WEEK[OUT_OF_DENOMINATOR_WEEK]
    assert term_week == DST_FALL_BACK_TERM_WEEK, (
        f"Course week {OUT_OF_DENOMINATOR_WEEK} is term week {term_week} in this world, and the "
        f"fall-back week of Fall 2026 is term week {DST_FALL_BACK_TERM_WEEK}. This test is written "
        "for the week the clocks change in; if the world's cohort moves, the course week this reads "
        "moves with it."
    )

    served = served_close(report_door, report_api_contract, course_week=OUT_OF_DENOMINATOR_WEEK)
    zone = served_timezone(report_door, report_api_contract, course_week=OUT_OF_DENOMINATOR_WEEK)
    local = served.astimezone(ZoneInfo(zone))

    assert local.date() == DST_FALL_BACK_SUNDAY, (
        f"The close instant served for course week {OUT_OF_DENOMINATOR_WEEK} is "
        f"{served.isoformat()}, which is {local.isoformat()} in the served zone {zone!r}. Term week "
        f"{term_week}'s window closes on {DST_FALL_BACK_SUNDAY}, the Sunday the clocks go back."
    )
    assert local.weekday() == CLOSES_WEEKDAY, (
        f"Read in {zone!r} the close lands on weekday {local.weekday()} ({local.isoformat()}). SPEC "
        "§3.1 closes every window on the Sunday, and the mockup's eyebrow says so in as many words: "
        f"{MOCKUP_EYEBROW_NOTE.strip()}"
    )
    assert (local.hour, local.minute, local.second) == CLOSES_WALL_CLOCK, (
        f"Read in {zone!r} the close is at {local.time()}, and SPEC §3.1 closes the window at "
        f"{CLOSES_WALL_CLOCK[0]:02d}:{CLOSES_WALL_CLOCK[1]:02d}:{CLOSES_WALL_CLOCK[2]:02d} in the "
        "institution's zone. An hour out here is a zone conversion done with one offset for the "
        "whole term."
    )
    assert zone == INSTITUTION_TIMEZONE, (
        f"This world's windows are written as UTC instants of SPEC §3.1's rhythm in "
        f"{INSTITUTION_TIMEZONE!r}, and the payload serves {zone!r}. The assertions above are only "
        "about the wall clock they were written for while those two agree."
    )


def test_the_payload_carries_a_datum_for_every_mockup_detail_that_needs_the_server(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """Criterion 6's backend half: what the design needs, the wire carries.

    The carried E4-21 entry defers exactly two mockup details because "the payload
    does not carry the data", and this is the payload side of its done-when. The
    mockup titles **two** histograms, one per stream, each with a question rather
    than a stream label, and prints **one** eyebrow note per week. So the wire owes
    one question text per stream — not one per report — and one close instant on
    the week.

    The rendering half is the implementer's, beside the components (ADR 0151's
    conventions): a served string appearing in a histogram title, and an eyebrow
    that renders the note from a close instant and renders unchanged without one.
    Nothing here asserts anything about rendering.

    **The mutation this kills:** a single `question_text` hung off the top level,
    which satisfies "the payload carries the question text" and leaves the second
    histogram with nothing of its own to be titled with.
    """
    mockup_text()

    body, answered = report_door.payload(course_week=IN_DENOMINATOR_WEEK)
    texts = [
        report_api_contract.stream_member(
            body, stream, report_api_contract.question_text_field, answered=answered
        )
        for stream in BOTH_STREAMS
    ]

    assert len(texts) == len(MOCKUP_HISTOGRAM_TITLES), (
        f"The payload carries {len(texts)} question texts and the mockup titles "
        f"{len(MOCKUP_HISTOGRAM_TITLES)} histograms with a question each."
    )
    assert all(isinstance(text, str) and text.strip() for text in texts), (
        f"The two streams' question texts are {texts!r}; each histogram is titled with the wording "
        "of its own stream's rating question."
    )
    assert len(set(texts)) == len(texts), (
        f"Both streams serve the same question text ({texts!r}). The mockup's two titles are two "
        "different questions — the instructor's and the course's — and a report that titles both "
        "histograms identically tells a reader nothing about which is which."
    )

    week = report_api_contract.member(body, report_api_contract.week_member, answered=answered)
    assert report_api_contract.closes_at_field in week, (
        f"The week member carries {sorted(week)}, with no "
        f"`{report_api_contract.closes_at_field}`. The mockup's eyebrow reads "
        f"{MOCKUP_EYEBROW_NOTE.strip()} and `WeekEyebrow` already takes an optional close instant "
        "that nothing supplies."
    )
