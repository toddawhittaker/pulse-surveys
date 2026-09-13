"""A week that has not closed is not a week to read — E4-07's security round, the HIGH.

Both reviews found the same hole and reached it the same way. `instructor_report`
serves any course week that has a `survey_window` row, including one still taking
responses, so an instructor can poll the report mid-window and read the
**difference** between two views of it. That difference is one student's
submission: the response count moves by one, a distribution bar moves by one, and
a comment appears. SPEC §4 randomizes comment display order precisely so that
position says nothing about who wrote what — and a reader who keeps the previous
view is subtracting rather than reading, which is `docs/MISTAKES.md` entry 51 in
as many words:

> A guarantee proven over one response, one report or one export is a guarantee
> about one payload, and a reader who keeps the previous one is subtracting
> rather than reading.

The shuffle cannot help here. It destroys the order rows came back in; it cannot
destroy the fact that a comment was absent at noon and present at one o'clock, and
in a week under the threshold the set of people who could have written it is
small. E4-04 built the whole small-N path to keep that inference out of the
report, and an open week hands it over through the report's own front door.

**The ruled behaviour:** the report route refuses a course week that is not in the
published set, with exactly the refusal it already gives a week the section does
not run — same status, same body, no oracle. "Published" is E4's breakdown
decision 6's, unchanged: a course week whose survey window has closed, per the
clock service. Nothing is stored to make a week published, so this is a comparison
against the clock and the pair below is driven by moving it.

**The pair is the unit, and the control sits inside the refusing half.** A route
that refused every week satisfies the first half; one that refused none satisfies
the second. And a refusal proves nothing about *openness* unless a week that has
closed is served at the same clock position — which is what course week 1 is doing
in the first test.

**Marked `invariant` at the module level**, which puts it in the isolated §4.1
pass and satisfies
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`.

**The instants are transcribed, not imported from a sibling test module.** A test
module importing its sibling resolves only because of where pytest puts `tests/`
on `sys.path` (`tests/fixtures/report_comments.py` says the same about
`test_report_schema.py`), so the two constants this shares with
`test_the_published_week_list_holds_only_the_closed_weeks.py` are spelled in both
and each says so. What is shared for real — the calendar itself — comes from
`tests/fixtures/survey_windows.py`, which is where SPEC §3.1's Fall 2026 instants
are written out by hand.
"""

from typing import Any

import pytest
from fixtures.report_api import (
    EITHER_SIDE_OF_A_CLOSE,
    TERM_WEEK_OF_COURSE_WEEK,
    ReportDoor,
)
from fixtures.survey_windows import WINDOWS_BY_TERM_WEEK

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The week the clock is put inside. Course week 4 rather than 1 or 6, so that
# weeks have closed before it and weeks are still to come after it: a refusal in
# the middle of a term is the case an instructor actually meets, and it leaves
# course week 1 available as the control that the route is not refusing
# everything.
OPEN_COURSE_WEEK = 4

# A week that has certainly closed at every clock position this module uses, and
# is therefore served throughout. It is the non-vacuity control.
CLOSED_COURSE_WEEK = 1

# A course week this six-week section does not run at all. The other half of the
# no-oracle pair: an open week and a week that was never scheduled have to be
# indistinguishable, or the difference between them says which weeks a section
# has — and, week by week, when its term began.
A_COURSE_WEEK_THE_SECTION_DOES_NOT_RUN = 99

# Course week 4's window, out of the hand-written calendar. Nothing here
# re-derives SPEC §3.1's Friday-to-Sunday rhythm: a fixture that did would agree
# with an implementation that made the same mistake (`docs/MISTAKES.md` entry 19).
OPEN_WINDOW_OPENS_AT, OPEN_WINDOW_CLOSES_AT = WINDOWS_BY_TERM_WEEK[
    TERM_WEEK_OF_COURSE_WEEK[OPEN_COURSE_WEEK]
]

# Six hours either side of that close, the same offset the published-week
# boundary pair uses and for the same reason: ADR 0109 makes the effective instant
# `real + (pretend_now - anchored_at)`, so it keeps moving while it is read and a
# value placed a second from an edge is a boundary nothing can stand on. Six hours
# before this close is inside the window — asserted, not assumed, in
# `assert_the_clock_is_inside_the_window` below — which is what makes this module
# about an **open** week rather than one that has not begun.
WHILE_THE_WINDOW_IS_OPEN = OPEN_WINDOW_CLOSES_AT - EITHER_SIDE_OF_A_CLOSE
ONCE_THE_WINDOW_HAS_CLOSED = OPEN_WINDOW_CLOSES_AT + EITHER_SIDE_OF_A_CLOSE


def assert_the_clock_is_inside_the_window() -> None:
    """The premise every test here rests on, from the hand-written calendar.

    "Still taking responses" and "not yet begun" are two different states and only
    one of them is this module's subject: a window that has not opened holds no
    responses, so a report over it leaks no delta and refusing it would be a
    different rule. If the clock this module pretends is not between the two
    instants, every assertion below is about the wrong state and one of them still
    passes.
    """
    assert OPEN_WINDOW_OPENS_AT < WHILE_THE_WINDOW_IS_OPEN < OPEN_WINDOW_CLOSES_AT, (
        f"The clock this module pretends, {WHILE_THE_WINDOW_IS_OPEN.isoformat()}, is not inside "
        f"course week {OPEN_COURSE_WEEK}'s window "
        f"({OPEN_WINDOW_OPENS_AT.isoformat()} to {OPEN_WINDOW_CLOSES_AT.isoformat()}). This module "
        "is about a week still taking responses, which is not the same state as a week that has "
        "not opened."
    )


def test_a_course_week_whose_window_is_still_open_is_refused(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The HIGH's own assertion: a mid-window report is not served at all.

    **The mutation this kills:** the week selection taken from `survey_window`
    alone — every week the section has a window row for — which is the shipped
    behaviour the security round found. It reads as obviously correct: the window
    row is the section's calendar, and the report is about a week of it.

    **The near miss it is written against, and why the control is in this test
    rather than beside it:** a route that refused every week would satisfy this
    assertion completely. So course week 1, whose window closed weeks before this
    clock, is read first and required to be served. The two reads differ in the
    week asked for and in nothing else — same session, same section, same instant
    (`docs/MISTAKES.md` entry 35).
    """
    assert_the_clock_is_inside_the_window()
    report_door.pretend(WHILE_THE_WINDOW_IS_OPEN)

    served = report_door.report(course_week=CLOSED_COURSE_WEEK)
    assert served.status_code == 200, (
        f"Course week {CLOSED_COURSE_WEEK}, whose window closed long before this clock, answered "
        f"{served.status_code}. Until a closed week is served, a refusal for the open one says "
        "only that this route refuses. Body begins "
        f"{served.text[:400]!r}."
    )

    answered = report_door.report(course_week=OPEN_COURSE_WEEK)
    assert answered.status_code == report_api_contract.out_of_scope_status, (
        f"Course week {OPEN_COURSE_WEEK} answered {answered.status_code} with its window still "
        f"open — it closes at {OPEN_WINDOW_CLOSES_AT.isoformat()} and the clock is at "
        f"{WHILE_THE_WINDOW_IS_OPEN.isoformat()}. A report served mid-window can be read twice, and "
        "the difference between two readings is one student's submission: the response count moves "
        "by one, a bar moves by one, and a comment appears. The shuffle destroys the order rows "
        "came back in; it cannot destroy the fact that a comment was not there an hour ago. Body "
        f"begins {answered.text[:400]!r}."
    )


def test_the_same_course_week_is_served_once_its_window_has_closed(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The other half: the refusal is about the clock and not about the week.

    Nothing changes between this test and the one above except where the
    development clock sits — the same section, the same session, the same window
    row, the same course week.

    **The mutation this kills:** a refusal that never lifts. A route that
    published a week only after the *term* ended, or that compared against
    `opens_at`, or that refused any week carrying an unreleased comment, would
    leave the first half of this pair green and this half red — which is why
    neither half is worth reading alone.
    """
    report_door.pretend(ONCE_THE_WINDOW_HAS_CLOSED)

    answered = report_door.report(course_week=OPEN_COURSE_WEEK)
    assert answered.status_code == 200, (
        f"Course week {OPEN_COURSE_WEEK} answered {answered.status_code} six hours after its window "
        f"closed at {OPEN_WINDOW_CLOSES_AT.isoformat()}. Its response count is final and E4's "
        "breakdown decision 6 makes it published; the whole report exists to be read then. Body "
        f"begins {answered.text[:400]!r}."
    )
    body = answered.json()
    published = report_api_contract.member(
        body,
        report_api_contract.week_member,
        report_api_contract.published_weeks_field,
        answered=answered,
    )
    assert OPEN_COURSE_WEEK in published, (
        f"Course week {OPEN_COURSE_WEEK} was served and is not in its own report's published weeks "
        f"{published}. The set a week is refused for not being in has to be the set the report "
        "prints, or week navigation offers a page the route will not serve."
    )


def test_an_open_weeks_refusal_is_the_one_a_week_the_section_never_runs_gets(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """No oracle: an open week and a week that does not exist answer identically.

    E4-07's known traps already name this shape for sections — "the refusal pair
    must be indistinguishable in body, not merely in status" — and the ruling
    extends it to weeks, because the difference between "not yet" and "never" is a
    fact about the section's calendar. Told apart, a caller can walk the course
    weeks of a section they cannot read and learn how long it runs and where in
    the term it sits.

    **The mutation this kills:** a distinct refusal for the open week — a 409, or a
    404 whose body says "not published yet" beside one that says "no such week".
    Both are the helpful thing to write and both are the oracle.
    """
    assert_the_clock_is_inside_the_window()
    report_door.pretend(WHILE_THE_WINDOW_IS_OPEN)

    still_open = report_door.report(course_week=OPEN_COURSE_WEEK)
    never_runs = report_door.report(course_week=A_COURSE_WEEK_THE_SECTION_DOES_NOT_RUN)

    assert still_open.status_code == report_api_contract.out_of_scope_status, (
        f"The open week answered {still_open.status_code}; this test compares two refusals and one "
        f"of them is not a refusal. Body begins {still_open.text[:400]!r}."
    )
    assert never_runs.status_code == still_open.status_code, (
        f"A course week this section does not run answered {never_runs.status_code} and an open "
        f"week answered {still_open.status_code}. Two statuses tell a caller which weeks a section "
        "has."
    )
    assert never_runs.text == still_open.text, (
        "The two refusals carry different bodies.\n"
        f"  window still open: {still_open.text[:300]!r}\n"
        f"  no such week:      {never_runs.text[:300]!r}\n\n"
        "Same status and same body, or the difference is the calendar."
    )
