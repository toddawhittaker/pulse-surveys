"""Each trend point carries both week axes — ticket E4-19, breakdown decision 12.

SPEC §2.2 puts both axes on every course-level page, and §5.1 applies that to the
report's trend charts: "the course week leads, the term week sits under it as a
quiet sub-label." `PulseTrendChart` (E4-08) takes both numbers per point and
computes neither — its copy file records why the client must not derive the term
week from an offset. Today the offset is a per-section constant — `_section_weeks`
computes each course week from the term number with one constant per section — so
a client could derive it; the wire states it anyway so the server's own reading of
the axis mapping, `week_of_the_term`, stays the only authority, rather than a
client freezing today's arithmetic into a second copy that would diverge silently
if the mapping ever stopped being affine. E4-07's shipped `TrendPoint` carries
`course_week` and `mean` only, so the sub-label has no wire source; this ticket
adds `term_week`, populated in `_payload`'s trend builder from the `_SectionWeek`
row each point is built from.

**The near-miss mutant is the point** (`docs/MISTAKES.md` entry 3): in a world
whose section starts week one of the term, `term_week = course_week` passes every
test here. So this module measures over the taught section
`tests/fixtures/report_api.py` already builds for E4-07 — cohort `F`, six course
weeks running from term week 7 — where the two axes are never the same number,
and a payload serving one where the other belongs is red rather than plausible.

**Which failure a red is, before E4-19 lands.** Every trend point in the payload
this ticket is measured over already exists (E4-07 shipped it); the only thing
missing is the `term_week` key on each one. So every red below is a FAILED
assertion — first a membership check (`"term_week" in point`), then a value
comparison — never a `KeyError` or an import error (`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.report_api import (
    FULL_WEEK,
    IN_DENOMINATOR_WEEK,
    TERM_WEEK_OF_COURSE_WEEK,
    ReportDoor,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "stream", [INSTRUCTOR_STREAM, COURSE_STREAM], ids=["instructor stream", "course stream"]
)
def test_every_trend_point_in_a_mid_term_section_carries_the_term_week_of_its_window_row(
    report_door: ReportDoor, report_api_contract: Any, stream: str
) -> None:
    """Acceptance criterion 1: every trend point states its own term week.

    This world's cohort runs course week 1 as term week 7 — never the same
    number as its course week, in either stream's trend — so a `term_week`
    that agrees with the point's own `course_week` is wrong here in a way it
    would not be on a section that starts when the term does.

    **The mutation this kills:** `term_week=other.course_week` in the trend
    builder — filling the new field from the value already in hand rather than
    from the window row's own term week. On a section starting week one of the
    term that mutant is an equivalent mutant, which is exactly why
    `docs/MISTAKES.md` entry 3 makes the proving world start mid-term instead.
    """
    course_week_field = report_api_contract.course_week_field
    term_week_field = report_api_contract.term_week_field

    body, answered = report_door.payload(course_week=FULL_WEEK)
    trend = report_api_contract.stream_member(
        body, stream, report_api_contract.trend_field, answered=answered
    )
    assert trend, f"The {stream} trend came back empty; this test has no points to check."

    for point in trend:
        course_week = point[course_week_field]
        assert term_week_field in point, (
            f"The {stream} trend point for course week {course_week} carries no "
            f"`{term_week_field}`: it holds {sorted(point)}. Breakdown decision 12 puts the term "
            "week of the window row on every trend point, the same way `week` already carries one "
            "for the report as a whole."
        )
        expected_term_week = TERM_WEEK_OF_COURSE_WEEK[course_week]
        assert course_week != expected_term_week, (
            f"Course week {course_week} is term week {expected_term_week} in this world's own "
            "table; if the two were the same number this test could not tell a correct term_week "
            "from one filled with the course week instead."
        )
        point_term_week = point[term_week_field]
        assert point_term_week == expected_term_week, (
            f"The {stream} trend point for course week {course_week} carries `{term_week_field}` = "
            f"{point_term_week!r}; this world's own table says course week {course_week} is term "
            f"week {expected_term_week}. A `term_week` equal to the point's own course week "
            f"({course_week}) would be the near-miss mutant `term_week=other.course_week` in the "
            "trend builder."
        )


def test_the_trend_point_for_the_requested_week_agrees_with_the_weeks_own_term_week(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """Acceptance criterion 2: the two statements of the axis pair cannot disagree.

    `week.term_week` is already on the wire (E4-07); this asks whether the
    trend point for that same course week states the same number the top-level
    `week` member does, over course week 2 of this world — term week 8, never
    week 2's own number.

    **The mutation this kills:** `term_week + 1` in the trend builder, an
    off-by-one that would land the point on term week 9 while `week` still
    reports 8.
    """
    body, answered = report_door.payload(course_week=IN_DENOMINATOR_WEEK)
    week = report_api_contract.member(body, report_api_contract.week_member, answered=answered)
    trend = report_api_contract.stream_member(
        body,
        report_api_contract.instructor_stream,
        report_api_contract.trend_field,
        answered=answered,
    )

    requested_course_week = week[report_api_contract.course_week_field]
    matching = [
        point
        for point in trend
        if point.get(report_api_contract.course_week_field) == requested_course_week
    ]
    assert len(matching) == 1, (
        f"The trend carries {len(matching)} points whose "
        f"`{report_api_contract.course_week_field}` is {requested_course_week} (the requested "
        f"week): {trend}. This test needs exactly one to compare against `week`'s own term week."
    )
    point = matching[0]

    term_week_field = report_api_contract.term_week_field
    assert term_week_field in point, (
        f"The trend point for the requested week carries no `{term_week_field}`: it holds "
        f"{sorted(point)}."
    )
    week_term_week = week[term_week_field]
    point_term_week = point[term_week_field]
    assert point_term_week == week_term_week, (
        f"`week.{term_week_field}` is {week_term_week!r} and the trend point whose "
        f"`{report_api_contract.course_week_field}` equals `week."
        f"{report_api_contract.course_week_field}` ({requested_course_week}) carries "
        f"`{term_week_field}` = {point_term_week!r} instead. The two statements of the axis pair "
        "cannot disagree; `term_week + 1` in the trend builder would land here, one term week ahead "
        "of what `week` itself reports."
    )


def test_the_trend_points_course_week_field_still_names_the_course_week(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The pair rule's other half: `term_week` arriving does not disturb `course_week`.

    **Expected green on today's tree.** `course_week` is E4-07's own shipped
    field, untouched by this ticket's scope (criterion 4: "no other payload
    member moves"), so this assertion reads nothing this ticket has any reason
    to change. A red here means these tests are broken, not the code.

    **The mutation this kills:** `course_week` and `term_week` swapped in the
    trend builder's constructor call — a point holding the right two numbers
    under each other's names, which the term_week-only assertions in this
    module cannot tell apart from correct because they never read
    `course_week`'s own value.
    """
    body, answered = report_door.payload(course_week=FULL_WEEK)
    published = report_api_contract.member(
        body,
        report_api_contract.week_member,
        report_api_contract.published_weeks_field,
        answered=answered,
    )
    trend = report_api_contract.stream_member(
        body,
        report_api_contract.instructor_stream,
        report_api_contract.trend_field,
        answered=answered,
    )
    plotted = [point[report_api_contract.course_week_field] for point in trend]

    assert sorted(plotted) == sorted(published), (
        f"The instructor trend's course weeks are {sorted(plotted)} and the published weeks are "
        f"{sorted(published)}. `term_week` landing beside `course_week` on the same points is not "
        "licence for `course_week` itself to move."
    )
