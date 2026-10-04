"""Which weeks a report can page across — ticket E4-07, criterion 3, and E5.1-05's C6.

> The published-week list contains exactly the closed weeks, both boundaries
> driven on the dev clock: the week whose window closes tonight is absent now and
> present after.

E4's breakdown decision 6 settled what published means and where the answer comes
from: "A published week is a course week whose survey window has closed, per the
clock service — the same currency E3's decision 6 used. Week navigation lists
exactly those weeks. Nothing is stored to make a week published." **E5.1-05 moved
the line, and only the line.** A week's report opens at 06:00 on the first Monday,
in the institution's time zone, strictly after its window closes (SPEC §3.1;
"unavailable at 05:59 and published at 06:00 Monday ... on the effective clock").
So a closed week is not yet a published one for the hours between Sunday night's
close and Monday at six, and the list still comes from comparing stored instants
with the clock — nothing is stored.

**So there are now three clock positions, not two.** Before the close, the week is
absent. After the close and before 06:00 Monday, it is still absent — the new
forbidden state, written as its own test so a list built from `closes_at < now`
fails by name. At 06:00 Monday, it is present.

**Each boundary is a pair.** A route that published every week satisfies the
"present" halves alone; one that published none satisfies the "absent" ones.
Neither half means anything without the other, which is why both are here and why
each names the other in its message.

**Nothing here re-derives SPEC §3.1's rhythm or the 06:00 rule.** The window
instants are `WINDOWS_BY_TERM_WEEK`, the hand-written table E2-06's suites are
measured against; the opening instants are `REPORT_OPENS_BY_TERM_WEEK`, written out
by hand in `tests/fixtures/report_api.py` (`docs/MISTAKES.md` entry 19). The
"before the close" clock is six hours before one close, because ADR 0109 makes the
effective instant `real + (pretend_now - anchored_at)`: it keeps moving while it is
read, so a value placed a second from an edge is a boundary nothing can stand on.
The 06:00 pair stands at one minute before the opening and at the opening itself:
the clock only drifts forward, so the opening instant is safe to stand on, and the
minute before it is safe for the few seconds a read takes. The exact-instant pair
(05:59:59.999999 against 06:00:00) is the pure function's, in
`tests/unit/test_the_report_opening_rule_is_six_on_the_monday_after_the_close.py`.

**The zone is stated, not inherited** (`docs/MISTAKES.md` entry 40): the two
06:00 tests build their door with `INSTITUTION_TIMEZONE=America/New_York` named in
their own chain, because 06:00 is a wall time and the zone is part of the
subject.

**Which failure a red is, before E4-07 lands.** `report_api_contract`'s lookups
are `pytest.fail` calls naming the router and the schema, so the first red is a
FAILED naming the deliverable rather than a collection error
(`docs/MISTAKES.md` entry 44).
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fixtures.clock import INSTITUTION_TIMEZONE_VARIABLE
from fixtures.report_api import (
    EITHER_SIDE_OF_A_CLOSE,
    FULL_WEEK,
    INSTRUCTOR_ROLE,
    REPORT_OPENS_BY_TERM_WEEK,
    TAUGHT_TERM_WEEKS,
    TERM_WEEK_OF_COURSE_WEEK,
    ReportDoor,
    assert_the_report_openings_are_what_this_file_says,
)
from fixtures.survey_windows import INSTITUTION_TIMEZONE, WINDOWS_BY_TERM_WEEK

pytestmark = pytest.mark.integration

# The week the clock is walked across. Course week 4 rather than 1 or 6, so that
# *both* answers are non-trivial: three weeks are published before the crossing
# and four after, and a list that was simply empty or simply everything fails one
# side or the other rather than passing by luck.
BOUNDARY_COURSE_WEEK = 4

# The weeks that are closed on both sides of that crossing, and are therefore the
# non-vacuity control inside each half of the pair.
ALREADY_PUBLISHED = (1, 2, 3)

# The weeks that are still open on both sides of it.
STILL_OPEN = (5, 6)

BOUNDARY_TERM_WEEK = TERM_WEEK_OF_COURSE_WEEK[BOUNDARY_COURSE_WEEK]
BOUNDARY_CLOSES_AT = WINDOWS_BY_TERM_WEEK[BOUNDARY_TERM_WEEK][1]
JUST_BEFORE_THE_CLOSE = BOUNDARY_CLOSES_AT - EITHER_SIDE_OF_A_CLOSE

# The boundary week's report opening — Sunday 25 October 2026 23:59:59 EDT closes
# it, so Monday 26 October 06:00 EDT, 10:00 UTC — out of the hand-written table,
# and the minute before it, 05:59:00 EDT. That minute is after the close by six
# hours less a minute: it is the clock this ticket's criterion names
# ("unavailable at 05:59"), and it is within a minute of where E4-07's "six hours
# after the close" used to stand and call the week published.
REPORT_OPENS = REPORT_OPENS_BY_TERM_WEEK[BOUNDARY_TERM_WEEK]
A_MINUTE_BEFORE_THE_REPORT_OPENS = REPORT_OPENS - timedelta(minutes=1)


def a_door_in_the_documented_zone(report_door_as: Callable[..., ReportDoor]) -> ReportDoor:
    """The instructor's door, with the institution's zone named rather than inherited."""
    return report_door_as(INSTRUCTOR_ROLE, **{INSTITUTION_TIMEZONE_VARIABLE: INSTITUTION_TIMEZONE})


def assert_the_minute_is_between_the_close_and_the_opening() -> None:
    """The premise of the 06:00 pair, checked in the test body (`docs/MISTAKES.md` entry 44).

    If the minute before the opening were not after the close, the "still absent"
    test would be about a week still taking responses — the first test's subject,
    green for the old reason — and the new rule would go unasserted.
    """
    assert_the_report_openings_are_what_this_file_says()
    assert BOUNDARY_CLOSES_AT < A_MINUTE_BEFORE_THE_REPORT_OPENS < REPORT_OPENS, (
        f"Course week {BOUNDARY_COURSE_WEEK}'s window closes at {BOUNDARY_CLOSES_AT.isoformat()} "
        f"and its report opens at {REPORT_OPENS.isoformat()}; the clock this module stands at, "
        f"{A_MINUTE_BEFORE_THE_REPORT_OPENS.isoformat()}, is not between the two."
    )


def published_weeks_of(body: Any, contract: Any, answered: Any) -> list[int]:
    """The course weeks the report payload says are published.

    Read at the sketch's own path — `week.published_weeks` — because
    `docs/tickets/e4/README.md` freezes it there and breakdown decision 5 makes a
    divergence something the pull request lists rather than something a test
    absorbs.
    """
    found = contract.member(
        body, contract.week_member, contract.published_weeks_field, answered=answered
    )
    assert isinstance(found, list) and all(isinstance(week, int) for week in found), (
        f"`{contract.week_member}.{contract.published_weeks_field}` came back as {found!r}. The "
        "sketch spells it a list of course-week numbers, and week navigation pages across it."
    )
    return found


def weeks_the_list_route_returns(answered: Any, contract: Any) -> list[int]:
    """The course weeks the published-week list route answers with, however it shapes them.

    **Found by walking rather than by indexing**, because E4-07 settles that the
    route exists and settles no response shape for it: a bare list of numbers, a
    list of objects each carrying a course week, or an object with one member
    holding either — all three satisfy the ticket, and a test that wrote
    `body["weeks"]` would be choosing among them. An answer this cannot read is a
    failure naming the ambiguity rather than a guess.
    """
    body = answered.json()

    def numbers(node: Any) -> list[int] | None:
        if isinstance(node, list):
            if all(isinstance(item, int) and not isinstance(item, bool) for item in node):
                return list(node)
            if node and all(
                isinstance(item, dict) and contract.course_week_field in item for item in node
            ):
                return [int(item[contract.course_week_field]) for item in node]
        return None

    direct = numbers(body)
    if direct is not None:
        return direct
    if isinstance(body, dict):
        candidates = [found for value in body.values() if (found := numbers(value)) is not None]
        if len(candidates) == 1:
            return candidates[0]
    pytest.fail(
        f"This suite cannot read a list of course weeks out of the published-week list route's "
        f"answer: {answered.text[:400]!r}. E4-07 settles the route and no response shape, so this "
        "reader accepts a list of numbers, a list of objects carrying "
        f"`{contract.course_week_field}`, or an object with exactly one member holding either. A "
        "fourth spelling is taught in `weeks_the_list_route_returns` in this module."
    )


def test_a_week_whose_window_has_not_closed_yet_is_absent_from_the_published_weeks(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """Criterion 3's first half: before the close, the week is not there.

    **The mutation this kills:** a published-week list built from the section's
    calendar — every course week the section runs — rather than from the windows
    that have closed. That list is right for a section at the end of its term and
    wrong every week before it, which is every week an instructor actually reads
    the report in.

    **The near miss it is written against:** an empty list, which would satisfy
    "week 4 is absent" for a reason that has nothing to do with the clock. So the
    three weeks that certainly *have* closed are asserted present in the same
    breath (`docs/MISTAKES.md` entry 3).
    """
    report_door.pretend(JUST_BEFORE_THE_CLOSE)
    body, answered = report_door.payload(course_week=FULL_WEEK)
    published = published_weeks_of(body, report_api_contract, answered)

    assert set(ALREADY_PUBLISHED) <= set(published), (
        f"With the clock at {JUST_BEFORE_THE_CLOSE.isoformat()} the published weeks are "
        f"{published}, and course weeks {list(ALREADY_PUBLISHED)} closed before it. A list missing "
        "them is empty for some reason other than the boundary, and the assertion below would be "
        "true of nothing."
    )
    assert BOUNDARY_COURSE_WEEK not in published, (
        f"Course week {BOUNDARY_COURSE_WEEK} is published with the clock six hours *before* its "
        f"window closes at {BOUNDARY_CLOSES_AT.isoformat()}. Published weeks are {published}. A "
        "week publishes at 06:00 on the Monday after its window closes, per the clock service "
        "(SPEC §3.1, E5.1-05) — nothing is stored to make a week published."
    )
    assert not set(STILL_OPEN) & set(published), (
        f"Course weeks {sorted(set(STILL_OPEN) & set(published))} are published and their windows "
        f"close later still. Published weeks are {published}."
    )


def test_a_week_whose_window_has_closed_is_still_absent_until_six_on_the_monday(
    report_door_as: Callable[..., ReportDoor], report_api_contract: Any
) -> None:
    """E5.1-05's forbidden state: closed, and not yet published, at 05:59 Monday.

    The clock stands at 05:59:00 on Monday 26 October 2026 in `America/New_York`
    — after course week 4's window closed at 23:59:59 the night before, and a
    minute before its report opens. Both answers to "which weeks are published"
    must leave week 4 out: the report payload's own `published_weeks` and the
    published-week list route. E5.1-05: "A week is unavailable at 05:59 and
    published at 06:00 Monday in the institution's time zone, on the effective
    clock", and the two readers "share one predicate".

    **The mutations this kills:** the publication test left as `closes_at < now`
    (E4-07's rule, which this clock satisfies); the 06:00 compared in UTC rather
    than in the institution's zone (06:00 UTC is 02:00 EDT, so the week would be
    published here); and either reader moved to the new rule while the other kept
    the old one — which is why both are read at the same clock.

    **The near miss it is written against:** an empty list, or a route that
    refuses, satisfies "week 4 is absent". So the three weeks that published days
    ago are required present in both answers first (`docs/MISTAKES.md` entry 3).
    **Its pair** is the next test, at 06:00:00, where the same week is present.
    """
    assert_the_minute_is_between_the_close_and_the_opening()
    door = a_door_in_the_documented_zone(report_door_as)
    door.pretend(A_MINUTE_BEFORE_THE_REPORT_OPENS)

    body, answered = door.payload(course_week=FULL_WEEK)
    listed = door.published_weeks()
    in_payload = published_weeks_of(body, report_api_contract, answered)
    assert listed.status_code == 200, (
        f"The published-week list answered {listed.status_code} for the section this session "
        f"teaches. Body begins {listed.text[:400]!r}."
    )
    from_route = weeks_the_list_route_returns(listed, report_api_contract)

    for where, published in (("the report payload", in_payload), ("the list route", from_route)):
        assert set(ALREADY_PUBLISHED) <= set(published), (
            f"With the clock at {A_MINUTE_BEFORE_THE_REPORT_OPENS.isoformat()} {where} answers "
            f"{published}, and course weeks {list(ALREADY_PUBLISHED)} published days before it. "
            "Missing them, the list is empty for some reason other than the boundary, and the "
            "assertion below would be true of nothing."
        )
        assert BOUNDARY_COURSE_WEEK not in published, (
            f"Course week {BOUNDARY_COURSE_WEEK} is in {where} ({published}) with the clock at "
            f"{A_MINUTE_BEFORE_THE_REPORT_OPENS.isoformat()} — 05:59 on the Monday in "
            f"{INSTITUTION_TIMEZONE}. Its window closed at {BOUNDARY_CLOSES_AT.isoformat()}, and its "
            f"report opens at {REPORT_OPENS.isoformat()}, 06:00 that Monday (SPEC §3.1, E5.1-05). "
            "A week published at its close is E4-07's rule, which this ticket replaced; a week "
            "published here under a 06:00 is that hour read in UTC."
        )


def test_the_same_week_is_published_at_six_on_the_monday_after_its_close(
    report_door_as: Callable[..., ReportDoor], report_api_contract: Any
) -> None:
    """Criterion 3's second half, at E5.1-05's hour: at 06:00 Monday the week is there.

    The clock stands at exactly 06:00:00 on Monday 26 October 2026 in
    `America/New_York`, the instant course week 4's report opens. The effective
    clock only drifts forward while it is read, so standing on the instant is
    standing on the published side of it.

    **The mutations this kills:** a comparison that reads the wall clock rather
    than the clock service, or `opens_at` rather than `closes_at`; an hour
    compared strictly (`now > opens`), which at the instant itself is a drift of
    a few milliseconds from failing and is caught by the unit pair instead; a
    report opening a whole week late (the following Monday); and a 06:00 read on
    standard time where this Monday is on daylight time (11:00 UTC, an hour after
    this clock). Each leaves the test above green and this one red, which is why
    the two are a pair over one boundary.

    The only thing that changes between this test and the one above is where the
    development clock sits; the rows are identical. Both readers are asked, for
    the reason the test above gives.
    """
    assert_the_minute_is_between_the_close_and_the_opening()
    door = a_door_in_the_documented_zone(report_door_as)
    door.pretend(REPORT_OPENS)

    body, answered = door.payload(course_week=FULL_WEEK)
    listed = door.published_weeks()
    in_payload = published_weeks_of(body, report_api_contract, answered)
    assert listed.status_code == 200, (
        f"The published-week list answered {listed.status_code} for the section this session "
        f"teaches. Body begins {listed.text[:400]!r}."
    )
    from_route = weeks_the_list_route_returns(listed, report_api_contract)

    for where, published in (("the report payload", in_payload), ("the list route", from_route)):
        assert BOUNDARY_COURSE_WEEK in published, (
            f"Course week {BOUNDARY_COURSE_WEEK} is absent from {where} ({published}) with the "
            f"clock at {REPORT_OPENS.isoformat()} — 06:00 on the Monday after its window closed at "
            f"{BOUNDARY_CLOSES_AT.isoformat()}, in {INSTITUTION_TIMEZONE}. SPEC §3.1 (E5.1-05) "
            "opens the report then. Its window row has not moved between this test and the one "
            "before it — only the clock has."
        )
        assert not set(STILL_OPEN) & set(published), (
            f"Course weeks {sorted(set(STILL_OPEN) & set(published))} are in {where} and their "
            f"windows have not closed at {REPORT_OPENS.isoformat()}. Published weeks are "
            f"{published}. A list that grew to everything at the first crossing is not reading the "
            "clock either."
        )


def test_the_published_weeks_are_course_weeks_and_not_the_terms_own_numbering(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """§2.2's two axes, told apart by a section whose course weeks are not its term weeks.

    Cohort `F` runs six weeks from term week 7, so the published list is
    `[1 … 6]` and never `[7 … 12]` — and the two sets are disjoint, so a payload
    serving the term axis where the course axis belongs is red rather than
    plausible. §2.2 is explicit that course-level pages plot the course week with
    the term week as a quiet sub-label, and week navigation pages across published
    weeks of that axis.

    **The mutation this kills:** `week.number` served straight out of the `week`
    row — the join is already there, the numbers look like weeks, and every
    section that happens to start in term week 1 would agree.
    """
    body, answered = report_door.payload(course_week=FULL_WEEK)
    published = published_weeks_of(body, report_api_contract, answered)

    assert set(published) == set(TERM_WEEK_OF_COURSE_WEEK), (
        f"With every one of this section's windows closed, the published weeks are {published} and "
        f"its course weeks are {sorted(TERM_WEEK_OF_COURSE_WEEK)}."
    )
    assert not set(published) & set(TAUGHT_TERM_WEEKS), (
        f"The published weeks {published} overlap this section's *term* weeks "
        f"{list(TAUGHT_TERM_WEEKS)}. The section runs term weeks 7-12 as course weeks 1-6, so the "
        "two axes cannot share a number and an overlap means the term axis is on the wire."
    )


def test_the_published_week_list_route_answers_the_same_weeks_as_the_payload(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The two routes agree — one answer to "which weeks may I page to", not two.

    E4-07 ships both the payload's own `published_weeks` and a list route the week
    navigation calls, and E4-11 consumes both. Two derivations of one question is
    `docs/MISTAKES.md` entry 13's shape in production code: the day one of them
    learns about a re-derived window, the other does not, and a reader pages to a
    week the report will not serve.

    **The mutation this kills:** the list route computing its own answer from the
    section's calendar while the payload computes its from the clock.
    """
    report_door.pretend(JUST_BEFORE_THE_CLOSE)

    body, answered = report_door.payload(course_week=FULL_WEEK)
    in_payload = published_weeks_of(body, report_api_contract, answered)

    listed = report_door.published_weeks()
    assert listed.status_code == 200, (
        f"The published-week list answered {listed.status_code} for the section this session "
        f"teaches. Body begins {listed.text[:400]!r}."
    )
    from_route = weeks_the_list_route_returns(listed, report_api_contract)

    assert sorted(from_route) == sorted(in_payload), (
        f"The list route answers {sorted(from_route)} and the report payload's "
        f"`{report_api_contract.week_member}."
        f"{report_api_contract.published_weeks_field}` answers {sorted(in_payload)}, with one "
        "clock and one section between them."
    )
    assert from_route, (
        "Both answers are empty, so this test compared nothing with nothing. Three of this "
        "section's windows closed before the clock this test set."
    )
