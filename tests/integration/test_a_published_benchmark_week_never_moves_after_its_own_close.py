"""The owner's "freeze at close" ruling, through the report route — E5-14, boundary finding HIGH.

The owner's ruling of 2026-09-22, as the E5-14 work order records it:

> A comparison or university figure for course week *w* on a section's report
> counts only responses that were fixed at the moment the report's own section's
> week-*w* survey window closed. … with *T(w)* = the reported section's own
> `survey_window.closes_at` for course week *w*: a response contributes to week
> *w* only if the window it was submitted in … has `closes_at <= T(w)`, **and**
> its `last_submitted_at <= T(w)`. Prior terms therefore count in full. A
> later-starting section of the same term joins the comparison for a course week
> only if its own week-*w* window closed by *T(w)*. So a published figure is a
> pure function of rows fixed at or before *T(w)*, and it never moves again.

**The defect this closes** (the boundary review's privacy-authz HIGH): the report
recomputed each comparison on every read, over responses still arriving in a
later-starting section's open window for the same course week, so a published
figure moved one student at a time and one student's rating was recoverable from
consecutive reads. `docs/MISTAKES.md` entry 51 is the class: a property that held
in every payload and failed across the sequence of them. So every test here reads
the payload **twice**, before and after one change, and compares.

**What this module owns and what it does not.** The SQL functions' two `<=`
comparisons and their per-week pairing are pinned, at the microsecond, in
`test_the_benchmark_set_functions_count_only_what_each_weeks_cutoff_had_fixed.py`.
This module asserts the report's half: that the instant it hands in is the
reported section's own week-*w* close, read from that section's window — no
later (a later cutoff lets the late rows in) and no earlier (an earlier one drops
the report's own cohort, whose windows close at the same instant).

**The world.** `tests/fixtures/report_benchmarks.py`'s cohort — the hero's lead's
default set at both minimums in the hero's own six-week cohort `F` — plus two more
of that lead's six-week sections at the same level: `later`, in cohort `H`, which
starts six weeks after the hero's so its course week 2 is open long after the
hero's week 2 published; and `prior`, in the prior term's cohort `E`, whose week 2
closed months before. The clock stands inside `later`'s course week 2 window,
which is the moment the finding describes.

**Every "unmoved" sits beside a proof that the members could move.** Byte-identical
members are what a route serving nothing twice also produces, so each unmoved
test first requires the reported week's comparison and university figures to be
shown, and the two "moved" tests below prove the same comparison sees a counted
change (`docs/MISTAKES.md` entries 3 and 9).

**Marked `invariant`**: §4.1 item 7 is "no figure computed from a comparison set
is shown below the benchmark minimum", and a figure that moves one student at a
time is a figure over one student.

**Which failure a red is on today's tree:** the three "unmoved" tests fail on
their comparison — the report recomputes over open windows and late rows — and
the two "moved" tests pass (they are the controls, and must stay green).
"""

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import PRIOR_TERM
from fixtures.report_api import PAYLOAD_STREAM_KEY, STREAMS_MEMBER, ReportDoor, member
from fixtures.report_benchmarks import (
    BENCHMARK_MEMBER,
    COMPARISON_POPULATION,
    MEAN_FIELD,
    UNIVERSITY_POPULATION,
    WEEK_CLEAR,
    WORKLOAD_BENCHMARK_MEMBER,
    PlantedBenchmarkCohort,
    hero_window_close,
    numbers_of,
    plant_a_section_beside,
    points_of,
    workload_figures,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.survey_windows import WINDOWS_BY_TERM_WEEK

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

STREAMS = (INSTRUCTOR_STREAM, COURSE_STREAM)

# The published week every read here is of: the cohort's week at both minimums.
REPORTED_WEEK = WEEK_CLEAR

# The two further sections of the lead's, and the start letters that make each
# what it is for. `H` is SPEC §2.2's third six-week letter, starting in term week
# 13; `E` in the prior term's map starts in its first week.
LATER = "later"
LATER_LETTER = "H"
PRIOR = "prior"
PRIOR_LETTER = "E"
SAME_CLOSE = "same-close"
SAME_CLOSE_LETTER = "F"

ONE_MICROSECOND = timedelta(microseconds=1)
AN_HOUR = timedelta(hours=1)

# What every planted change answers. Far from every value the cohort plants
# (hours 3.5-12.5, ratings 1-5 spread), so a change that counts moves the means.
A_CHANGE_OF_HOURS = Decimal("30.0")
A_REVISED_HOURS = Decimal("0.5")
A_RATING = 1


def later_week_opens(cohort: PlantedBenchmarkCohort) -> datetime:
    """When `later`'s course week 2 window opened — term week 12 + 2, Friday 18:00."""
    term_week = cohort.world.term_week_of(LATER, REPORTED_WEEK)
    return WINDOWS_BY_TERM_WEEK[term_week][0]


def a_world_with_a_later_cohort_and_a_prior_term(
    door: ReportDoor, contract: Any, plant: Callable[..., PlantedBenchmarkCohort]
) -> tuple[PlantedBenchmarkCohort, datetime, Any]:
    """The cohort, `later` and `prior`, one existing response in `later`, and the clock inside it.

    Answers the cohort, *T(2)* read back from the hero's own window, and the
    existing `later` response. That response is there for the revision test and
    harmless to the rest: its window closes after *T(2)*, so under the ruling it
    is outside every figure read here.
    """
    cohort = plant(door, minimums=contract.minimums())
    plant_a_section_beside(cohort, LATER, letter=LATER_LETTER)
    plant_a_section_beside(cohort, PRIOR, letter=PRIOR_LETTER, term=PRIOR_TERM)
    cutoff = hero_window_close(cohort.world, door, REPORTED_WEEK)

    opens = later_week_opens(cohort)
    if not opens > cutoff:
        pytest.fail(
            f"`{LATER}`'s course week {REPORTED_WEEK} opens at {opens.isoformat()}, which is not "
            f"after the hero's own week-{REPORTED_WEEK} close {cutoff.isoformat()}. This world is "
            "built on a later-starting cohort whose same course week is open after the hero's "
            "published; with the letters moved, it is not that world."
        )
    world = cohort.world
    student = world.student("e5-14-freeze-later-existing", enrolled_in=(LATER,))
    existing = world.respond(
        LATER,
        course_week=REPORTED_WEEK,
        student=student,
        workload=A_CHANGE_OF_HOURS,
        instructor_rating=A_RATING,
        course_rating=A_RATING,
        last_submitted_at=opens + AN_HOUR,
    )
    door.commit()
    door.pretend(opens + 2 * AN_HOUR)
    return cohort, cutoff, existing


def benchmark_members(door: ReportDoor) -> dict[str, str]:
    """Every benchmark member of the reported week's payload, serialized for byte comparison.

    Both streams' `benchmark` member and the top-level `workload_benchmark`,
    each as canonical JSON — so "unmoved" means unmoved in every figure, every
    point and every flag, not only in the one number a test chose to look at.
    """
    body, answered = door.payload(course_week=REPORTED_WEEK)
    found = {
        f"streams.{key}.{BENCHMARK_MEMBER}": member(
            body, STREAMS_MEMBER, key, BENCHMARK_MEMBER, answered=answered
        )
        for key in PAYLOAD_STREAM_KEY.values()
    }
    found[WORKLOAD_BENCHMARK_MEMBER] = member(body, WORKLOAD_BENCHMARK_MEMBER, answered=answered)
    return {where: json.dumps(held, sort_keys=True) for where, held in found.items()}


def assert_the_reported_week_is_shown(door: ReportDoor) -> None:
    """The control every "unmoved" needs: the figures under comparison are real ones.

    Both populations, both panels and the workload mean, at the reported week.
    Byte-identical suppressed members prove nothing about a freeze.
    """
    body, answered = door.payload(course_week=REPORTED_WEEK)
    for stream in STREAMS:
        for population in (COMPARISON_POPULATION, UNIVERSITY_POPULATION):
            points = points_of(body, stream, population, answered=answered)
            assert REPORTED_WEEK in points and numbers_of(points[REPORTED_WEEK]), (
                f"The control failed before the assertion it protects: the {stream} panel's "
                f"{population} figure for course week {REPORTED_WEEK} is "
                f"{points.get(REPORTED_WEEK)!r}. A suppressed figure is identical across any two "
                "reads, so the comparison below would say nothing about a freeze."
            )
    for population in (COMPARISON_POPULATION, UNIVERSITY_POPULATION):
        mean = workload_figures(body, population, answered=answered)[MEAN_FIELD]
        assert numbers_of(mean), (
            f"The control failed before the assertion it protects: the {population} workload mean "
            f"for course week {REPORTED_WEEK} is {mean!r}."
        )


def moved(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """The members whose serialization differs between two reads."""
    return sorted(where for where in before if before[where] != after.get(where))


def a_respondent_answers(
    cohort: PlantedBenchmarkCohort, label: str, *, subject: str, last_submitted_at: datetime
) -> None:
    """One new student in `label` answers the reported week, every question, far from the set."""
    world = cohort.world
    student = world.student(subject, enrolled_in=(label,))
    world.respond(
        label,
        course_week=REPORTED_WEEK,
        student=student,
        workload=A_CHANGE_OF_HOURS,
        instructor_rating=A_RATING,
        course_rating=A_RATING,
        last_submitted_at=last_submitted_at,
    )


def test_a_submission_into_a_later_cohorts_open_window_leaves_the_published_week_unmoved(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """The finding itself: a new response in the same course week of a section still open.

    `later`'s course week 2 is open now, and the hero's course week 2 published
    weeks ago. A student submits there. Under the ruling that row is outside the
    hero's week 2 for good — its window closes after *T(2)* — so every benchmark
    member of the hero's week-2 report is byte-identical before and after.

    **The mutation it kills:** the report reading without cutoffs, or with the
    read's own instant as the cutoff (the window is open, so `closes_at <= now`
    excludes it today — and admits it the day it closes, which is the same leak
    a week later; the stamp test below catches that form). **Its near miss** is
    `test_a_response_in_a_window_closing_exactly_at_the_reported_close_moves_the_week`,
    where the new row is counted and the members must move.
    """
    cohort, _cutoff, _existing = a_world_with_a_later_cohort_and_a_prior_term(
        report_door, report_api_contract, benchmark_cohort
    )
    assert_the_reported_week_is_shown(report_door)
    before = benchmark_members(report_door)

    a_respondent_answers(
        cohort,
        LATER,
        subject="e5-14-freeze-later-new",
        last_submitted_at=later_week_opens(cohort) + AN_HOUR,
    )
    report_door.commit()
    after = benchmark_members(report_door)

    assert not moved(before, after), (
        f"A submission into `{LATER}`'s open course-week-{REPORTED_WEEK} window moved "
        f"{moved(before, after)} on the hero's published week {REPORTED_WEEK}.\n\n"
        "The owner's ruling: a later-starting section joins the comparison for a course week only "
        "if its own week-w window closed by T(w), the hero's own close. This is the measured "
        "defect — a published figure moving one student at a time, so that consecutive reads "
        "recover one student's answer."
    )


def test_a_revision_in_a_later_cohorts_window_leaves_the_published_week_unmoved(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """A resubmission, not a new row: the existing `later` response changes its hours.

    **The mutation it kills:** the same unfrozen read as above, reached through an
    `UPDATE` rather than an `INSERT` — a report that froze on a count of rows but
    recomputed their values would pass the test above and fail this one.
    """
    cohort, _cutoff, existing = a_world_with_a_later_cohort_and_a_prior_term(
        report_door, report_api_contract, benchmark_cohort
    )
    assert_the_reported_week_is_shown(report_door)
    before = benchmark_members(report_door)

    cohort.world.revise(
        existing,
        workload=A_REVISED_HOURS,
        last_submitted_at=later_week_opens(cohort) + 2 * AN_HOUR - ONE_MICROSECOND,
    )
    report_door.commit()
    after = benchmark_members(report_door)

    assert not moved(before, after), (
        f"Revising a response in `{LATER}`'s open course-week-{REPORTED_WEEK} window moved "
        f"{moved(before, after)} on the hero's published week {REPORTED_WEEK}. Under the ruling "
        "that response was never part of the published figure, before or after the revision."
    )


def test_a_response_changed_after_the_reported_close_leaves_the_published_week_unmoved(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """A window that closed long before *T(w)*, and a row last submitted one microsecond after it.

    The prior term's course week 2 closed months before the hero's. A response
    there stamped *T(2)* + 1 µs is the respond-on-behalf or late-revision case:
    the window rule counts it and the stamp rule does not, so it is out.

    **The mutation it kills:** the report handing in a cutoff later than its own
    week's close — the read's own instant, the end of the week, the close plus a
    grace period — every one of which counts this row. **Its near miss** is
    `test_a_prior_term_response_fixed_by_the_reported_close_moves_the_week`, the
    same row stamped exactly *T(2)*.
    """
    cohort, cutoff, _existing = a_world_with_a_later_cohort_and_a_prior_term(
        report_door, report_api_contract, benchmark_cohort
    )
    assert_the_reported_week_is_shown(report_door)
    before = benchmark_members(report_door)

    a_respondent_answers(
        cohort, PRIOR, subject="e5-14-freeze-prior-late", last_submitted_at=cutoff + ONE_MICROSECOND
    )
    report_door.commit()
    after = benchmark_members(report_door)

    assert not moved(before, after), (
        f"A prior-term response last submitted at {(cutoff + ONE_MICROSECOND).isoformat()}, one "
        f"microsecond after the hero's week-{REPORTED_WEEK} close {cutoff.isoformat()}, moved "
        f"{moved(before, after)}. The ruling counts a response only if its `last_submitted_at <= "
        "T(w)`; a report whose cutoff is anything later than its own close lets this row rewrite a "
        "published week."
    )


def test_a_prior_term_response_fixed_by_the_reported_close_moves_the_week(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """CONTROL, and the stamp's equal side: a prior-term row stamped exactly *T(2)* counts.

    "Prior terms therefore count in full" — and a row fixed at the cutoff is
    fixed. Its arrival after the first read is the test's device, not the
    world's: it is what shows the byte comparison above can see a counted change.

    **The mutation it kills:** `last_submitted_at < T(w)`, and a report that
    leaves prior terms out of a frozen figure. **Its near miss** is the test
    above, one microsecond later.

    **Must be green on today's tree**, where nothing is frozen and every row
    counts; a red here means the byte comparison is blind.
    """
    cohort, cutoff, _existing = a_world_with_a_later_cohort_and_a_prior_term(
        report_door, report_api_contract, benchmark_cohort
    )
    assert_the_reported_week_is_shown(report_door)
    before = benchmark_members(report_door)

    a_respondent_answers(
        cohort, PRIOR, subject="e5-14-freeze-prior-fixed", last_submitted_at=cutoff
    )
    report_door.commit()
    after = benchmark_members(report_door)

    changed = moved(before, after)
    assert changed, (
        f"A prior-term response in a window that closed months before the hero's week "
        f"{REPORTED_WEEK}, last submitted at exactly {cutoff.isoformat()} (the hero's own close), "
        "moved no benchmark member. The ruling counts it — prior terms count in full, and "
        "`last_submitted_at <= T(w)` includes the equal case — so either it is being refused, or "
        "the comparison the three 'unmoved' tests rest on cannot see a change at all."
    )
    assert WORKLOAD_BENCHMARK_MEMBER in changed, (
        f"The members that moved were {changed}; the response reported {A_CHANGE_OF_HOURS} hours, "
        "far from every value the set planted, so the workload member has to be among them."
    )


def test_a_response_in_a_window_closing_exactly_at_the_reported_close_moves_the_week(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """CONTROL, and the window's equal side: a same-cohort section closing at *T(2)* counts.

    Every section of the hero's own cohort closes its course week 2 at the same
    instant the hero's does, which is the ordinary case: the ruling's
    `closes_at <= T(w)` has to include it, or a same-cohort default set is never
    a benchmark at all.

    **The mutation it kills:** `closes_at < T(w)`, and a report whose cutoff is
    earlier than its own close (the window's opening, say). **Its near miss** is
    the first test in this module, whose window closes weeks after *T(2)*; the
    microsecond version is in the SQL module.

    **Must be green on today's tree**, for the reason the control above gives.
    """
    cohort, cutoff, _existing = a_world_with_a_later_cohort_and_a_prior_term(
        report_door, report_api_contract, benchmark_cohort
    )
    same_close = plant_a_section_beside(cohort, SAME_CLOSE, letter=SAME_CLOSE_LETTER)
    report_door.commit()
    assert same_close.first_term_week == cohort.world.section(cohort.labels[0]).first_term_week, (
        f"`{SAME_CLOSE}` starts in term week {same_close.first_term_week} and the cohort's set in "
        f"{cohort.world.section(cohort.labels[0]).first_term_week}, so its course week "
        f"{REPORTED_WEEK} does not close at the hero's instant and this is not the equal case."
    )
    assert_the_reported_week_is_shown(report_door)
    before = benchmark_members(report_door)

    a_respondent_answers(
        cohort, SAME_CLOSE, subject="e5-14-freeze-same-close", last_submitted_at=cutoff - AN_HOUR
    )
    report_door.commit()
    after = benchmark_members(report_door)

    assert moved(before, after), (
        f"A response in `{SAME_CLOSE}`, whose course-week-{REPORTED_WEEK} window closes at the "
        f"hero's own instant {cutoff.isoformat()}, last submitted an hour before it, moved no "
        "benchmark member. The ruling counts a window with `closes_at <= T(w)`, and the hero's own "
        "cohort is exactly that case."
    )
