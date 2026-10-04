"""A week's report opens at 06:00 on the Monday after it closes — E5.1-05, criterion C6.

> **C6.** A week is unavailable at 05:59 and published at 06:00 Monday in the
> institution's time zone, on the effective clock. `published_course_weeks` and
> `instructor_report` share one predicate, which ADR 0184 records.

The owner's ruling of 2026-10-03 says when: the first Monday 06:00, in the
institution's zone, strictly after the window's `closes_at`. Before E5.1-05 a week
was readable the moment its window closed (E4's breakdown decision 6), hours
before the Monday summary job (02:20) had written the summary the report leads
with. This module drives the **report route** across that hour; the published-week
list is driven across the same hour in
`test_the_published_week_list_holds_only_the_closed_weeks.py`, and the
exact-instant pair (05:59:59.999999 against 06:00:00) belongs to the pure
function, in `tests/unit/test_the_report_opening_rule_is_six_on_the_monday_after_the_close.py`.

**Every boundary is a pair, and each refusal carries its own control.** A route
that refused every week satisfies a refusal; one that served every week satisfies
a served half. So each refusal is read beside course week 1, which published
weeks earlier and must be served at the same clock, and each refusal has a served
twin at the opening instant.

**The refusal is the one a week the section never runs gets** — work order:
"The refusal for a closed-but-unopened week is the existing
`CourseWeekUnavailableError`, from the same line, indistinguishable from a week the
section never runs." That is asserted on the wire, by status and by body, against
course week 99, the same comparison
`test_the_report_names_nothing_from_a_week_still_taking_responses.py` makes for a
week still taking responses.

**Where the clock stands, and why it can stand there.** ADR 0109 makes the
effective instant `real + (pretend_now - anchored_at)`, so it drifts forward
while it is read. The opening instant itself is therefore safe to stand on — the
drift only moves further onto the published side — and one minute before it is
safe for the few seconds a read takes. Each refusing test reads the boundary week
first, straight after moving the clock, and the control after.

**Every instant is a literal** (`docs/MISTAKES.md` entry 19). The New York
opening comes from `REPORT_OPENS_BY_TERM_WEEK` in `tests/fixtures/report_api.py`;
the Honolulu opening is written out here. Neither is computed by the rule under
test, and a premise check in each test body confirms each is a Monday 06:00 in its
zone after the close without producing it.

**The zone is part of the subject, so it is named in each test's own chain**
(`docs/MISTAKES.md` entry 40): `America/New_York` for the ordinary pair, and
`Pacific/Honolulu` — a zone this repository configures nowhere, with no daylight
saving — for the pair that proves the hour is read in the *configured* zone rather
than in a zone written into the code.

**Which failure a red is, before E5.1-05 lands.** The refusals at 05:59 are
assertion failures: today's tree serves a week the moment it closes, so the
boundary week answers 200 where 404 is required. The served halves at 06:00 are
green on today's tree as well, and are here as the pairs that stop a builder
refusing too much. Nothing here imports a symbol E5.1-05 adds.
"""

from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fixtures.clock import INSTITUTION_TIMEZONE_VARIABLE
from fixtures.report_api import (
    FULL_WEEK,
    INSTRUCTOR_ROLE,
    REPORT_OPENS_BY_TERM_WEEK,
    TERM_WEEK_OF_COURSE_WEEK,
    ReportDoor,
    assert_the_report_openings_are_what_this_file_says,
)
from fixtures.student_read import A_NON_DEFAULT_INSTITUTION_TIMEZONE
from fixtures.survey_windows import INSTITUTION_TIMEZONE, WINDOWS_BY_TERM_WEEK

pytestmark = pytest.mark.integration

# The week walked across the hour. Course week 4 (term week 10) rather than the
# last one, so weeks have published before it — course week 1 is the control —
# and weeks are still to come after it.
BOUNDARY_COURSE_WEEK = 4
BOUNDARY_TERM_WEEK = TERM_WEEK_OF_COURSE_WEEK[BOUNDARY_COURSE_WEEK]

# The control: published weeks before any clock this module stands at.
LONG_PUBLISHED_WEEK = FULL_WEEK

# A course week this six-week section does not run at all, the other half of the
# no-oracle comparison. The same number the open-week module uses.
A_COURSE_WEEK_THE_SECTION_DOES_NOT_RUN = 99

# Course week 4's close: Sunday 25 October 2026 23:59:59 EDT, from the hand-written
# calendar.
BOUNDARY_CLOSES_AT = WINDOWS_BY_TERM_WEEK[BOUNDARY_TERM_WEEK][1]

# Its report opening in the documented zone — Monday 26 October 2026 06:00 EDT,
# 10:00 UTC — out of the hand-written table, and the minute before it.
NEW_YORK_OPENS = REPORT_OPENS_BY_TERM_WEEK[BOUNDARY_TERM_WEEK]
A_MINUTE_BEFORE_NEW_YORK_OPENS = NEW_YORK_OPENS - timedelta(minutes=1)

# **The same close read in `Pacific/Honolulu`, written out by hand.** The close is
# 2026-10-26T03:59:59Z, which in Honolulu (UTC-10, no daylight saving) is Sunday 25
# October 17:59:59. The first Monday 06:00 there strictly after it is Monday 26
# October 06:00 HST, which is 16:00 UTC. At 10:00 UTC — New York's opening — it is
# midnight in Honolulu, six hours short.
HONOLULU_OPENS = datetime(2026, 10, 26, 16, 0, 0, tzinfo=UTC)

MONDAY = 0
SIX = time(6, 0)


def assert_the_new_york_premises() -> None:
    """The New York pair's premises, in the test body (`docs/MISTAKES.md` entry 44)."""
    assert_the_report_openings_are_what_this_file_says()
    assert BOUNDARY_CLOSES_AT < A_MINUTE_BEFORE_NEW_YORK_OPENS < NEW_YORK_OPENS, (
        f"Course week {BOUNDARY_COURSE_WEEK} closes at {BOUNDARY_CLOSES_AT.isoformat()} and its "
        f"report opens at {NEW_YORK_OPENS.isoformat()}; the minute before the opening, "
        f"{A_MINUTE_BEFORE_NEW_YORK_OPENS.isoformat()}, is not between them. The refusing test "
        "would then be about a week still taking responses — another module's subject — and "
        "E5.1-05's hour would go unasserted."
    )


def assert_the_honolulu_premises() -> None:
    """`HONOLULU_OPENS` against the close it is the opening of, without computing it.

    It must be a Monday at 06:00 in Honolulu, after the close, within a day of it,
    and later than New York's opening — the last clause is what makes New York's
    opening a clock where the Honolulu-configured week is still unpublished.
    """
    zone = ZoneInfo(A_NON_DEFAULT_INSTITUTION_TIMEZONE)
    local = HONOLULU_OPENS.astimezone(zone)
    assert local.weekday() == MONDAY and local.time() == SIX, (
        f"`HONOLULU_OPENS` is {HONOLULU_OPENS.isoformat()}, which is {local.isoformat()} in "
        f"{A_NON_DEFAULT_INSTITUTION_TIMEZONE} — not a Monday at 06:00. The literal in this module "
        "is what to correct."
    )
    assert BOUNDARY_CLOSES_AT < HONOLULU_OPENS < BOUNDARY_CLOSES_AT + timedelta(days=1), (
        f"`HONOLULU_OPENS` is {HONOLULU_OPENS.isoformat()} and the close it follows is "
        f"{BOUNDARY_CLOSES_AT.isoformat()}."
    )
    assert NEW_YORK_OPENS < HONOLULU_OPENS, (
        f"New York's opening {NEW_YORK_OPENS.isoformat()} is not before Honolulu's "
        f"{HONOLULU_OPENS.isoformat()}, so standing at New York's opening proves nothing about "
        "which zone the hour is read in."
    )


def a_door_in(report_door_as: Callable[..., ReportDoor], zone: str) -> ReportDoor:
    """The teaching instructor's door, built with `INSTITUTION_TIMEZONE` set to `zone`."""
    return report_door_as(INSTRUCTOR_ROLE, **{INSTITUTION_TIMEZONE_VARIABLE: zone})


def assert_refused_beside_a_served_control(
    door: ReportDoor, contract: Any, *, clock: datetime, why: str
) -> Any:
    """Course week 4 refused and course week 1 served, at one clock; answers the refusal.

    The boundary week is read first, straight after the clock was moved, so the
    minute of slack is spent on one request rather than two.
    """
    refused = door.report(course_week=BOUNDARY_COURSE_WEEK)
    served = door.report(course_week=LONG_PUBLISHED_WEEK)
    assert served.status_code == 200, (
        f"Course week {LONG_PUBLISHED_WEEK}, which published weeks before {clock.isoformat()}, "
        f"answered {served.status_code}. Until a published week is served at this clock, a refusal "
        f"of course week {BOUNDARY_COURSE_WEEK} says only that this route refuses. Body begins "
        f"{served.text[:400]!r}."
    )
    assert refused.status_code == contract.out_of_scope_status, (
        f"Course week {BOUNDARY_COURSE_WEEK} answered {refused.status_code} with the clock at "
        f"{clock.isoformat()}. Its window closed at {BOUNDARY_CLOSES_AT.isoformat()}; {why} SPEC "
        "§3.1 (E5.1-05): a week's report opens at 06:00 on the first Monday after its close, in "
        "the institution's time zone, and is refused before then exactly as a week the section "
        f"never runs is refused ({contract.out_of_scope_status}). Body begins "
        f"{refused.text[:400]!r}."
    )
    return refused


def assert_served_and_listed(door: ReportDoor, contract: Any, *, clock: datetime, why: str) -> None:
    """Course week 4 served at this clock, and named in its own report's published weeks."""
    answered = door.report(course_week=BOUNDARY_COURSE_WEEK)
    assert answered.status_code == 200, (
        f"Course week {BOUNDARY_COURSE_WEEK} answered {answered.status_code} with the clock at "
        f"{clock.isoformat()}. {why} Its window closed at {BOUNDARY_CLOSES_AT.isoformat()}, and "
        "SPEC §3.1 (E5.1-05) opens its report at 06:00 on the Monday after, in the institution's "
        f"time zone. Body begins {answered.text[:400]!r}."
    )
    published = contract.member(
        answered.json(), contract.week_member, contract.published_weeks_field, answered=answered
    )
    assert BOUNDARY_COURSE_WEEK in published, (
        f"Course week {BOUNDARY_COURSE_WEEK} was served at {clock.isoformat()} and is not in its "
        f"own report's published weeks {published}. E5.1-05: `published_course_weeks` and "
        "`instructor_report` share one predicate, so a week one of them serves is a week the other "
        "lists."
    )


# ---------------------------------------------------------------------------
# The hour, in the documented zone.
# ---------------------------------------------------------------------------


def test_a_closed_weeks_report_is_refused_a_minute_before_six_on_the_monday(
    report_door_as: Callable[..., ReportDoor], report_api_contract: Any
) -> None:
    """C6's first half: at 05:59 Monday, after the close, the week's report is not served.

    The clock stands at 05:59:00 EDT on Monday 26 October 2026. Course week 4's
    window closed six hours earlier, so its responses are final — and its report
    is still refused, because it opens at 06:00.

    **The mutations this kills:** the report's week selection left on
    `closes_at < now` (E4-07's rule, which this clock satisfies); the 06:00
    compared in UTC (02:00 EDT, which this clock is past); the published list
    moved to the new rule while the report route's own refusal was not, or the
    other way round.

    **The near miss:** a route refusing everything. Course week 1 is read at the
    same clock and must be served. **Its pair** is
    `test_the_same_weeks_report_is_served_at_six_on_the_monday`.
    """
    assert_the_new_york_premises()
    door = a_door_in(report_door_as, INSTITUTION_TIMEZONE)
    door.pretend(A_MINUTE_BEFORE_NEW_YORK_OPENS)

    assert_refused_beside_a_served_control(
        door,
        report_api_contract,
        clock=A_MINUTE_BEFORE_NEW_YORK_OPENS,
        why=f"this clock is 05:59 on the Monday after, in {INSTITUTION_TIMEZONE}.",
    )


def test_a_closed_but_unopened_weeks_refusal_is_the_one_a_week_the_section_never_runs_gets(
    report_door_as: Callable[..., ReportDoor], report_api_contract: Any
) -> None:
    """No oracle: "closed, not yet opened" and "never runs" answer identically.

    Work order: the refusal is the existing `CourseWeekUnavailableError`, "from
    the same line, indistinguishable from a week the section never runs". Told
    apart, a caller could walk a section's course weeks on a Monday morning and
    learn which week closed last night — how far into its term the section is.

    **The mutation this kills:** a distinct refusal for the closed-but-unopened
    week — a 425 or 409 "not yet", or a 404 whose body says "available at 06:00"
    beside one that says "no such week". Both are the helpful thing to write and
    both are the oracle.

    **The near miss:** two identical bodies because both are something other
    than a refusal. So the first is required to be the refusal status before the
    two are compared, and course week 1 is required to be served.
    """
    assert_the_new_york_premises()
    door = a_door_in(report_door_as, INSTITUTION_TIMEZONE)
    door.pretend(A_MINUTE_BEFORE_NEW_YORK_OPENS)

    not_yet = assert_refused_beside_a_served_control(
        door,
        report_api_contract,
        clock=A_MINUTE_BEFORE_NEW_YORK_OPENS,
        why=f"this clock is 05:59 on the Monday after, in {INSTITUTION_TIMEZONE}.",
    )
    never_runs = door.report(course_week=A_COURSE_WEEK_THE_SECTION_DOES_NOT_RUN)

    assert never_runs.status_code == not_yet.status_code, (
        f"A course week this section does not run answered {never_runs.status_code} and a week "
        f"that closed last night and has not opened answered {not_yet.status_code}. Two statuses "
        "tell a caller which week closed last."
    )
    assert never_runs.text == not_yet.text, (
        "The two refusals carry different bodies.\n"
        f"  closed, not yet opened: {not_yet.text[:300]!r}\n"
        f"  no such week:           {never_runs.text[:300]!r}\n\n"
        "Same status and same body, or the difference is the calendar."
    )


def test_the_same_weeks_report_is_served_at_six_on_the_monday(
    report_door_as: Callable[..., ReportDoor], report_api_contract: Any
) -> None:
    """C6's second half: at 06:00:00 Monday the same week's report is served.

    The clock stands on the opening instant itself, 06:00:00 EDT on Monday 26
    October 2026 (10:00 UTC). The rows are the ones the refusing test reads; only
    the clock differs.

    **The mutations this kills:** a refusal that never lifts, or lifts late — the
    hour read as 07:00, the opening put a week late on the Monday after next, or
    06:00 on standard time where this Monday is on daylight time (11:00 UTC). Each
    leaves the refusing test green and this one red.
    """
    assert_the_new_york_premises()
    door = a_door_in(report_door_as, INSTITUTION_TIMEZONE)
    door.pretend(NEW_YORK_OPENS)

    assert_served_and_listed(
        door,
        report_api_contract,
        clock=NEW_YORK_OPENS,
        why=f"That is 06:00:00 on the Monday after its close, in {INSTITUTION_TIMEZONE}.",
    )


# ---------------------------------------------------------------------------
# The hour is read in the configured zone.
# ---------------------------------------------------------------------------


def test_six_oclock_in_new_york_is_too_early_when_the_institution_is_in_honolulu(
    report_door_as: Callable[..., ReportDoor], report_api_contract: Any
) -> None:
    """The zone is the configured one: at New York's 06:00, Honolulu's week is still shut.

    With `INSTITUTION_TIMEZONE=Pacific/Honolulu`, course week 4's close
    (2026-10-26T03:59:59Z) is Sunday 17:59:59 local, and its report opens at
    Monday 06:00 HST, 16:00 UTC. The clock stands at 10:00 UTC — 06:00 in New
    York, midnight in Honolulu — where the week must be refused.

    **The mutation this kills:** the zone written into the code as
    `America/New_York` rather than read from `Settings.institution_timezone`. It
    says this clock is past the opening, and it passes every New York test in this
    module, which is why this one exists. (A zone written in as UTC is caught
    here too, and by the New York refusal already.) **Its pair** is the next test,
    at 06:00 HST, where the same week is served under the same configuration.
    """
    assert_the_new_york_premises()
    assert_the_honolulu_premises()
    door = a_door_in(report_door_as, A_NON_DEFAULT_INSTITUTION_TIMEZONE)
    door.pretend(NEW_YORK_OPENS)

    assert_refused_beside_a_served_control(
        door,
        report_api_contract,
        clock=NEW_YORK_OPENS,
        why=(
            f"with INSTITUTION_TIMEZONE={A_NON_DEFAULT_INSTITUTION_TIMEZONE} this clock is "
            "midnight on the Monday, six hours before the report opens there. 06:00 in New York "
            "is the right hour in the wrong zone."
        ),
    )


def test_the_same_week_is_served_at_six_in_honolulu_when_the_institution_is_there(
    report_door_as: Callable[..., ReportDoor], report_api_contract: Any
) -> None:
    """The pair: at 06:00 HST, under the same configuration, the week's report is served.

    **The mutation this kills:** a refusal under a non-default zone that never
    lifts — the configured zone parsed wrongly and replaced with something that
    puts the opening later still, or a rule that refuses every week whenever the
    zone is not the default. Without this half, the test above would be satisfied
    by a route that refuses everything under `Pacific/Honolulu`.
    """
    assert_the_honolulu_premises()
    door = a_door_in(report_door_as, A_NON_DEFAULT_INSTITUTION_TIMEZONE)
    door.pretend(HONOLULU_OPENS)

    assert_served_and_listed(
        door,
        report_api_contract,
        clock=HONOLULU_OPENS,
        why=(
            f"That is 06:00:00 on the Monday after its close in "
            f"{A_NON_DEFAULT_INSTITUTION_TIMEZONE}, the configured zone."
        ),
    )
