"""One log read costs the same queries however much it covers — E6-09, done-when 8.

> The shown set is computed once for all the reader's decisions, with grouped
> queries, not once per section, week and stream. A test counts the statements one
> log read issues over at least two section-weeks and two sections, and the count
> does not grow with them.

**What is counted.** Every read (`SELECT` or `WITH`) any engine is sent while one
`GET` of the log is served, recorded by `tests/fixtures/statements.py`, which
listens for `before_cursor_execute` on the `Engine` class and so sees the
application's own engine. The request is served in this process
(`fastapi.testclient.TestClient`), so its statements are the ones recorded.

**The comparison.** The lead's log is read over one section-week (two decisions,
one in each stream of course week 1 of the taught section), then over four
section-weeks across two sections (the same two, plus decisions in course week 3
of the taught section and in course weeks 1 and 3 of the sibling section of the
same course). The second count must **equal** the first. A grouped computation
issues the same statements whatever the rows; a computation per section, week or
stream issues more for every one added. Equality rather than a bound, because the
ticket's sentence is "does not grow", and the only allowance a bound would make is
for the growth it forbids.

**The warm-up.** The first measured read is preceded by an unmeasured one over the
same rows, so a statement issued once per process or per connection (a type
lookup, a cache fill) is not counted in one read and not the other.

**The controls** (`docs/MISTAKES.md` entry 3): the recorder saw reads at all, and
the second read's log really does cover more rows than the first's, so the equality
is about a larger log and not about two identical ones.

**Which failure a red is, before E6-09 lands.** The log computes visibility per
section, week and stream, so the second count is larger: the equality fails naming
both counts.
"""

import pytest
from fixtures.instructor_decisions import STORED_EXCLUDED
from fixtures.lead_review import AS_LEAD_FACULTY, LOG_REASON, LeadReviewWorld
from fixtures.moderation import HARMFUL
from fixtures.report_api import FIRST_HELD_WEEK, FULL_WEEK, TAUGHT_COHORT, UNTAUGHT_COHORT
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.statements import reads, statements_recorded

pytestmark = pytest.mark.integration

# (cohort, course week, stream) of each decision, by stage. The first stage is one
# section-week, both streams; the second adds a second week and a second section.
ONE_SECTION_WEEK = (
    (TAUGHT_COHORT, FULL_WEEK, INSTRUCTOR_STREAM),
    (TAUGHT_COHORT, FULL_WEEK, COURSE_STREAM),
)
THREE_MORE_SECTION_WEEKS = (
    (TAUGHT_COHORT, FIRST_HELD_WEEK, COURSE_STREAM),
    (UNTAUGHT_COHORT, FULL_WEEK, INSTRUCTOR_STREAM),
    (UNTAUGHT_COHORT, FULL_WEEK, COURSE_STREAM),
    (UNTAUGHT_COHORT, FIRST_HELD_WEEK, COURSE_STREAM),
)


def plant(review: LeadReviewWorld, decisions: tuple[tuple[str, int, str], ...]) -> list[str]:
    """One excluded harmful comment per entry; the reasons, which find the rows in the log."""
    reasons: list[str] = []
    for cohort, course_week, stream in decisions:
        reason = f"E6-09 query count: {cohort} course week {course_week} {stream}"
        comment = review.plant(
            course_week=course_week,
            stream=stream,
            text=f"E6-09 a harmful comment in {cohort}, course week {course_week}, {stream}",
            verdict=HARMFUL,
            cohort=cohort,
        )
        # Decided by the reading lead: E9-14 item 1 blanks a withheld row's reason
        # for any other reader, and several of these rows are held, so the reasons
        # that find the rows below would otherwise be null.
        review.plant_decision(
            comment,
            STORED_EXCLUDED,
            decided_by=review.lead.person_id,
            decided_as=AS_LEAD_FACULTY,
            reason=reason,
        )
        reasons.append(reason)
    return reasons


def measured_read(review: LeadReviewWorld) -> tuple[int, list[str]]:
    """One log read as the lead: how many reads it sent, and the reasons it answered."""
    with statements_recorded() as recorded:
        answered = review.log(review.lead)
    assert answered.status_code == 200, f"The log answered {answered.status_code} to the lead."
    rows = review.log_rows(review.lead)
    return len(reads(recorded)), [str(row.get(LOG_REASON)) for row in rows]


def test_a_log_over_four_section_weeks_in_two_sections_costs_what_one_section_week_costs(
    lead_review: LeadReviewWorld,
) -> None:
    """Count one log read over one section-week, then over four in two sections: equal.

    **The mutation this kills:** the shown set computed inside a loop over the
    reader's decisions' (section, week, stream) — one comment read, threshold
    count or moderation check per group — which adds statements for every group
    the second stage plants. **The near miss:** a per-section loop with the weeks
    grouped (the second stage adds a section, so it grows too).
    """
    review = lead_review
    first_reasons = plant(review, ONE_SECTION_WEEK)
    review.log(review.lead)  # the warm-up, unmeasured
    before, answered_before = measured_read(review)
    assert before > 0, (
        "The recorder saw no reads while the log was served, so it is not listening where the "
        "application's statements pass, and every count here would be zero for that reason."
    )
    assert set(first_reasons) <= set(
        answered_before
    ), f"The first read answered {answered_before}, without the planted {first_reasons}."

    more_reasons = plant(review, THREE_MORE_SECTION_WEEKS)
    after, answered_after = measured_read(review)
    assert set(first_reasons + more_reasons) <= set(answered_after), (
        f"The second read answered {answered_after}, without all of "
        f"{first_reasons + more_reasons}; the count below would compare two reads of one log."
    )
    assert after == before, (
        f"One log read sent {before} reads over one section-week and {after} over four "
        "section-weeks in two sections. E6-09 done-when 8: the shown set is computed once for "
        "all the reader's decisions, with grouped queries, so the count does not grow with the "
        "section-weeks the log covers."
    )
