"""The premise every E5-05 assertion rests on: this world is the world it says it is.

Three modules read a report payload and say "this week clears both minimums" or
"this week is one person short". Each of those sentences is a claim about rows,
and `docs/MISTAKES.md` entry 3 is the record of what happens when nobody checks
it: a suppression asserted over a world that was never planted is emptiness
wearing a green tick, and it passes whatever the implementation does.

So this module asserts the *world* and nothing about E5-05 at all. It is
**green on a tree where E5-05 is unbuilt**, deliberately — every deliverable it
touches (E4-07's door, E5-01's tables, E5-03's set functions,
`tests/fixtures/report_benchmarks.py`'s planter) already exists. A red here is a
defect in the new test machinery, and reading it before reading the three modules
that stand on it is the difference between debugging a fixture and debugging a
schema.

**The counts are read back through E5-03's own set function**, which is the row
the benchmark minimums are compared against: `respondent_count` is distinct
students and `section_count` is distinct sections, per course week, over exactly
the sections the default set resolves to. A planter that dealt fifteen responses
to twelve people would satisfy every sentence in this ticket's docstrings and
fail here, which is `docs/MISTAKES.md` entry 50's shape — a threshold that
protects people crossed by a count of something else.

**The clock and the environment** are the door's; see
`tests/fixtures/report_benchmarks.py`.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fixtures.benchmark_views import SET_FUNCTION, set_function_rows
from fixtures.report_api import ReportDoor
from fixtures.report_benchmarks import (
    BENCHMARK_WEEKS,
    WEEK_CLEAR,
    WEEK_CLEAR_TWIN,
    WEEK_THIN_PEOPLE,
    WEEK_THIN_SECTIONS,
    course_levels,
    lead_faculty_course_ids,
    section_lengths,
)

pytestmark = [pytest.mark.integration]


def planted_counts(cohort: Any) -> dict[int, dict[str, Any]]:
    """What E5-03's set function says about the planted set, course week by course week."""
    world = cohort.world
    world.session.rollback()
    rows = set_function_rows(world.session, SET_FUNCTION, cohort.set_section_ids())
    return {int(row["course_week"]): row for row in rows}


def test_each_planted_week_holds_the_sections_and_the_people_its_plan_states(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """The four weeks, read back as counts of sections and of distinct people.

    Both counts per week, because the two near-miss weeks differ from the two
    passing ones by exactly one of them and a test asserting neither could not say
    which (`docs/MISTAKES.md` entry 53). The numbers are derived from the
    configured minimums and the plan's offsets, never transcribed.

    **What a red here means:** the planter in
    `tests/fixtures/report_benchmarks.py` is not building the world the three
    E5-05 modules describe, and every suppression they assert is about something
    else. It is not a statement about E5-05, which this module never touches.
    """
    minimums = report_api_contract.minimums()
    cohort = benchmark_cohort(report_door, minimums=minimums)
    counts = planted_counts(cohort)

    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]

    for course_week, plan in sorted(BENCHMARK_WEEKS.items()):
        row = counts.get(course_week)
        assert row is not None, (
            f"E5-03's `{SET_FUNCTION}` answers nothing for course week {course_week} over the "
            f"planted set ({sorted(counts)} came back). The planter answered that it dealt "
            f"{len(cohort.respondents_by_week[course_week])} respondents across "
            f"{len(cohort.sections_by_week[course_week])} of its sections that week."
        )
        assert int(row["section_count"]) == sections + plan.sections, (
            f"Course week {course_week} covers {row['section_count']} sections of the default set; "
            f"its plan asks for {sections + plan.sections} "
            f"(`{report_api_contract.minimum_sections}` is {sections}, offset {plan.sections})."
        )
        assert int(row["respondent_count"]) == respondents + plan.respondents, (
            f"Course week {course_week} was answered by {row['respondent_count']} distinct people; "
            f"its plan asks for {respondents + plan.respondents} "
            f"(`{report_api_contract.minimum_respondents}` is {respondents}, offset "
            f"{plan.respondents}). A count of responses is not a count of people "
            "(`docs/MISTAKES.md` entry 50), and this is the number both minimums are compared "
            "against."
        )


def test_the_two_near_miss_weeks_differ_from_the_passing_ones_by_one_count_each(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """The near-miss discipline, stated as an assertion rather than as a docstring.

    A world whose thin week is thin in *both* counts proves only that suppression
    happens, never which minimum did it — which is the closed-set defeat
    `docs/MISTAKES.md` entry 22 records, and the reason E5's breakdown names both
    thresholds by hand.

    **What a red here means:** the plan in `tests/fixtures/report_benchmarks.py`
    has drifted into a world where the two minimums cannot be told apart.
    """
    minimums = report_api_contract.minimums()
    cohort = benchmark_cohort(report_door, minimums=minimums)
    counts = planted_counts(cohort)

    clear = counts[WEEK_CLEAR]
    twin = counts[WEEK_CLEAR_TWIN]
    thin_people = counts[WEEK_THIN_PEOPLE]
    thin_sections = counts[WEEK_THIN_SECTIONS]

    assert (clear["section_count"], clear["respondent_count"]) == (
        twin["section_count"],
        twin["respondent_count"],
    ), (
        f"The two passing weeks are not twins: course week {WEEK_CLEAR} holds {dict(clear)} and "
        f"course week {WEEK_CLEAR_TWIN} holds {dict(twin)}."
    )
    assert thin_people["section_count"] == clear["section_count"], (
        f"Course week {WEEK_THIN_PEOPLE} is meant to be short of people and nothing else, and it "
        f"covers {thin_people['section_count']} sections against the passing week's "
        f"{clear['section_count']}."
    )
    assert thin_people["respondent_count"] == clear["respondent_count"] - 1, (
        f"Course week {WEEK_THIN_PEOPLE} was answered by {thin_people['respondent_count']} people "
        f"and the passing week by {clear['respondent_count']}; the near miss is exactly one person."
    )
    assert thin_sections["respondent_count"] == clear["respondent_count"], (
        f"Course week {WEEK_THIN_SECTIONS} is meant to be short of sections and nothing else, and "
        f"{thin_sections['respondent_count']} people answered it against the passing week's "
        f"{clear['respondent_count']}."
    )
    assert thin_sections["section_count"] == clear["section_count"] - 1, (
        f"Course week {WEEK_THIN_SECTIONS} covers {thin_sections['section_count']} sections and "
        f"the passing week {clear['section_count']}; the near miss is exactly one section."
    )


def test_the_hero_and_the_set_are_comparable_and_led_by_one_person(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """SPEC §5.1's two membership facts, read back rather than assumed.

    "To be comparable, sections must match on **both** length … *and* level", and
    "the default comparison set is the same Lead Faculty's courses filtered to
    matching length+level". A world where the hero's course and the set's carry
    different levels has no default set at all, and every suppression the E5-05
    modules assert would be true for that reason instead.

    **The hero's own section is not in the set** (E5 breakdown decision 5), which
    is asserted here because it is what makes the university line — which keeps
    the whole population — a control that differs from the comparison line by the
    hero alone.

    **What a red here means:** the planter built a world in which no comparison
    could be computed, so every absence the other modules read is vacuous.
    """
    minimums = report_api_contract.minimums()
    cohort = benchmark_cohort(report_door, minimums=minimums)
    world = cohort.world
    world.session.rollback()

    courses = [cohort.hero_course, *(cohort.course_of(label) for label in cohort.labels)]
    levels = course_levels(world, courses)
    assert len(set(levels)) == 1 and levels[0] is not None, (
        f"The hero's course and the set's courses carry the levels {levels}. SPEC §5.1 matches "
        "levels exactly — 'a `UGGR` section is compared against other `UGGR` sections' — so a set "
        "at another level is not this hero's comparison set at all."
    )

    lengths = section_lengths(world, [cohort.hero_section_id, *cohort.set_section_ids()])
    assert len(set(lengths)) == 1, (
        f"The hero's section and the set's run {sorted(set(lengths))} weeks. §5.1: 'an 8-week "
        "graduate course is never averaged against a 12-week undergraduate one'."
    )

    led = lead_faculty_course_ids(world, cohort.lead)
    course_key = world.key_of("course")
    owed = {cohort.hero_course[course_key]} | {
        cohort.course_of(label)[course_key] for label in cohort.labels
    }
    assert owed <= led, (
        f"The planted lead is mapped to {len(led)} courses and the world needs {len(owed)} of them "
        f"— the hero's course and every set course. Missing: {sorted(owed - led)}."
    )

    assert cohort.hero_section_id not in set(cohort.set_section_ids()), (
        "The hero's own section is inside its own comparison set. E5's breakdown decision 5: 'the "
        "hero section is excluded from its own comparison-set line', because a section compared "
        "against a set containing itself dampens exactly the divergence the chart exists to show."
    )
