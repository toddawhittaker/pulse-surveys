"""An undated log row sits in no time order, after every dated row — E9-14 fix round, P1.

E9-14 item 1 blanks `reason` and `decided_on` on a withheld row for a reader who
did not decide it (SPEC §5.2: a date beside held or released text places it in
a week). The privacy review on e88d4fc8 found the date still recoverable: the
log stays newest first, so an undated row sitting between two dated rows has
its date bracketed by its neighbours'. The fix round's rule: dated rows keep
newest-first order (ADR 0190), and undated rows follow them all as a trailing
group ordered by something that is not time — section label first, then
decision, then a stable non-temporal key.

**How "not time" is shown without naming the key further than the ruling
does.** Four withheld decisions are planted in two sections, interleaved in
time so that both insertion orders occur: section `F`, then `Q`, then `Q`, then
`F`. To the reader every one of them looks the same apart from its section
label (same decision, same role, flagged, no excerpt, no reason, no date). In
time order the trailing labels read `F, Q, Q, F` — the two orders mirrored. A
key that starts with the section label puts each section's rows together; a
key that follows time cannot. So the test requires each section's undated rows
to be contiguous. Three dated rows are planted between them in time, each a
day apart, and must all come first, newest first.

**The reader** is a dean of the college; every decision is the lead's, so none
is the dean's own (ADR 0206's wider read).

**Which failure a red is, on e88d4fc8.** The log is newest first throughout, so
the undated rows sit between the dated ones and in time order: FAILED on the
"after every dated row" assertion (and the grouping one).
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from fixtures.instructor_decisions import STORED_EXCLUDED
from fixtures.lead_review import (
    AS_LEAD_FACULTY,
    EXCERPT_LENGTH,
    LOG_DECIDED_ON,
    LOG_EXCERPT,
    LOG_REASON,
    LOG_SECTION_LABEL,
    LeadReviewWorld,
    Reader,
)
from fixtures.moderation import HARMFUL
from fixtures.report_api import FIRST_HELD_WEEK, FULL_WEEK, TAUGHT_COHORT, UNTAUGHT_COHORT
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

DEAN_ROLE = "DEAN"


def at(day: int) -> datetime:
    """Mid-afternoon UTC on a November 2026 day: the same date in the institution's zone."""
    return datetime(2026, 11, day, 15, 0, tzinfo=UTC)


# (kind, cohort, day decided). Dated rows are shown comments; undated rows are
# held ones. In time the held rows run F, Q, Q, F, with a dated row between pairs.
PLAN = (
    ("dated", TAUGHT_COHORT, 2),
    ("undated", TAUGHT_COHORT, 3),
    ("undated", UNTAUGHT_COHORT, 4),
    ("dated", TAUGHT_COHORT, 5),
    ("undated", UNTAUGHT_COHORT, 6),
    ("undated", TAUGHT_COHORT, 7),
    ("dated", TAUGHT_COHORT, 8),
)


def a_dean(review: LeadReviewWorld) -> Reader:
    return review.a_leader("e9-14-p1-dean", grants=((DEAN_ROLE, review.college),))


def plant(review: LeadReviewWorld) -> dict[str, int]:
    """Every planned decision, the lead's, in plan order; the dated rows' excerpts by day."""
    dated: dict[str, int] = {}
    for index, (kind, cohort, day) in enumerate(PLAN):
        text_ = f"E9-14 P1 decision {index}: a harmful comment in cohort {cohort}, {kind}"
        comment = review.plant(
            course_week=FULL_WEEK if kind == "dated" else FIRST_HELD_WEEK,
            stream=INSTRUCTOR_STREAM if kind == "dated" else COURSE_STREAM,
            text=text_,
            verdict=HARMFUL,
            cohort=cohort,
        )
        review.plant_decision(
            comment,
            STORED_EXCLUDED,
            decided_by=review.lead.person_id,
            decided_as=AS_LEAD_FACULTY,
            reason=f"E9-14 P1 the lead's reason {index}",
            decided_at=at(day),
        )
        if kind == "dated":
            dated[text_[:EXCERPT_LENGTH]] = day
    return dated


def section_of(review: LeadReviewWorld, row: dict[str, Any]) -> str | None:
    label = str(row.get(LOG_SECTION_LABEL))
    found = [c for c in (TAUGHT_COHORT, UNTAUGHT_COHORT) if review.code_of(c) in label]
    return found[0] if len(found) == 1 else None


def test_undated_rows_follow_every_dated_row_grouped_by_section_and_not_in_time_order(
    lead_review: LeadReviewWorld,
) -> None:
    """Dated rows first, newest first; then the undated rows, each section's together.

    **The mutations it kills:** the log ordered newest first over every row
    (e88d4fc8), which leaves an undated row's date bracketed by its dated
    neighbours; undated rows moved to the end but kept in time order among
    themselves (`F, Q, Q, F`), which still says which held decision came after
    which; undated rows sorted to the front. **The near miss it spares:** any
    order among one section's undated rows — they are indistinguishable to the
    reader — and the dated rows' newest-first order, which is the twin.
    """
    review = lead_review
    dean = a_dean(review)
    dated_days = plant(review)

    rows = review.log_rows(dean)
    ours = [row for row in rows if section_of(review, row) is not None]
    dated = [row for row in ours if row.get(LOG_EXCERPT) in dated_days]
    undated = [row for row in ours if row.get(LOG_EXCERPT) is None]

    assert len(dated) == 3 and len(undated) == 4, (
        f"The dean's log carries {len(dated)} dated and {len(undated)} withheld rows of this "
        f"world; three and four were planted. Rows: {ours}."
    )
    assert all(
        row.get(LOG_DECIDED_ON) is not None for row in dated
    ), f"A shown row lost its date: {dated}. The twin needs the dated rows dated."
    assert all(
        row.get(LOG_DECIDED_ON) is None and row.get(LOG_REASON) is None for row in undated
    ), (
        f"A withheld row read by a non-decider carries a reason or a date: {undated}. E9-14 item "
        "1 is the premise of this test."
    )
    days = [dated_days[row[LOG_EXCERPT]] for row in dated]
    assert days == sorted(
        days, reverse=True
    ), f"The present twin: the dated rows run on days {days}; ADR 0190's log is newest first."
    positions = {id(row): index for index, row in enumerate(ours)}
    last_dated = max(positions[id(row)] for row in dated)
    first_undated = min(positions[id(row)] for row in undated)
    assert last_dated < first_undated, (
        f"An undated row sits at position {first_undated}, before the dated row at "
        f"{last_dated}. Between two dated rows, its neighbours' dates bracket the date it had "
        "removed (the fix round's P1)."
    )
    sections = [section_of(review, row) for row in sorted(undated, key=lambda r: positions[id(r)])]
    runs = [
        section
        for index, section in enumerate(sections)
        if index == 0 or section != sections[index - 1]
    ]
    assert len(runs) == len(set(runs)), (
        f"The undated rows run by section as {sections}. Planted in time as F, Q, Q, F, they are "
        "in time order unless each section's rows sit together; the trailing group is ordered "
        "by section label, then decision, then a key that is not time."
    )
