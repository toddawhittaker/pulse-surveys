"""The two week axes and the chart's own weeks — ticket E4-07, and ADR 0147's zero-filling.

E4-07's scope names "the week axis done right: course week with the term-week
sub-label value (§2.2), derived server-side so every consumer agrees", and SPEC
§2.2 is where the pair comes from:

> Course-level pages (instructor report, student results) plot **course week**
> ("WK 01…") with a quiet term-week sub-label ("TERM 04…") from the section's
> start offset.

ADR 0147 adds the other half — the shape of the chart's own axis:

> Only the section-weeks that were answered get a row. Absence, not a zero row:
> the payload layer zero-fills the weeks the chart needs, in one place, so a
> stored zero and a missing week never arrive looking the same.

That sentence is a claim about two different things arriving differently, so it
takes two assertions over one quiet week: its **distribution** is zero-filled —
five ratings, five counts, each of them 0 — while its **trend point** carries no
mean at all, because no rating was submitted and a mean of zero is a statement
about ratings that were.

**The section this is measured over runs term weeks 7-12 as course weeks 1-6**,
so no wrong answer for one axis is a right answer for the other: the two sets are
disjoint. `COURSE_WEEK_OF_TERM_WEEK` in `tests/fixtures/report_api.py` is written
out by hand and checked against `SEEDED_COHORTS` before any of this runs, so
nothing here re-derives §2.2's start-letter calendar it is measuring
(`docs/MISTAKES.md` entry 19).

**Which failure a red is, before E4-07 lands.** `report_api_contract`'s lookups
and `member` are `pytest.fail` calls naming the deliverable, so the first red is a
FAILED naming what is missing (`docs/MISTAKES.md` entry 44).
"""

from collections import Counter
from typing import Any

import pytest
from fixtures.report_api import (
    FULL_WEEK,
    FULL_WEEK_COURSE_RATINGS,
    FULL_WEEK_INSTRUCTOR_RATINGS,
    IN_DENOMINATOR_WEEK,
    SILENT_WEEK,
    TAUGHT_COHORT,
    TAUGHT_LENGTH_WEEKS,
    TERM_WEEK_OF_COURSE_WEEK,
    ReportDoor,
)
from fixtures.survey_windows import (
    COHORT_SECTION_MODALITY,
    COHORT_SECTION_ORDINAL,
    SEEDED_COHORTS,
)

pytestmark = pytest.mark.integration

# SPEC §3.2's Likert range, written out. The distribution has a bar per value
# whether or not anybody chose it — the README sketch shows `{"1": 0, "2": 1, …}`
# with a zero in it — and E4-09's histogram renders five bars.
LIKERT_VALUES = ("1", "2", "3", "4", "5")

# The section code `Fall2026.section_row` writes for a cohort: the start letter,
# the ordinal and the modality. Composed from that fixture's own constants rather
# than written as `F1WW`, so a change to how the world spells a section code is
# one red naming the code rather than four.
TAUGHT_SECTION_CODE = f"{TAUGHT_COHORT}{COHORT_SECTION_ORDINAL}{COHORT_SECTION_MODALITY}"


def distribution_of(body: Any, contract: Any, stream: str, answered: Any) -> dict[str, int]:
    """One stream's this-week distribution, as a mapping of rating to count."""
    found = contract.stream_member(body, stream, contract.distribution_field, answered=answered)
    assert isinstance(found, dict), (
        f"`streams.{contract.payload_stream_key[stream]}.{contract.distribution_field}` came back "
        f"as {found!r}. The sketch spells it an object keyed by rating value."
    )
    return {str(key): int(value) for key, value in found.items()}


def expected_counts(ratings: tuple[Any, ...]) -> dict[str, int]:
    """The distribution the given ratings make, with a zero for every value nobody chose.

    Written here rather than read off anything the payload produced: the counts
    are a tally of the values this world submitted, which is the input side.
    `None` — a question left unanswered — contributes to no bar, which is the same
    sentence ADR 0147's re-homed criterion 3 makes about the mean.
    """
    tally = Counter(str(rating) for rating in ratings if rating is not None)
    return {value: tally.get(value, 0) for value in LIKERT_VALUES}


def test_the_payload_names_the_course_week_and_its_term_week_sub_label(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """§2.2's two axes, on a section where they are different numbers.

    Course week 2 of this section is term week 8. A payload serving 8 in the
    course week's place, or 2 in the term week's, is red rather than plausible —
    which is the whole reason the world runs cohort `F` from term week 7 rather
    than a section that starts when the term does.

    **The mutation this kills:** `term_week` filled from the `week` row and
    `course_week` filled from the same value; and the offset taken without §2.2's
    inclusive `+ 1`, which answers 1 where 2 belongs.
    """
    term_week = TERM_WEEK_OF_COURSE_WEEK[IN_DENOMINATOR_WEEK]
    assert term_week != IN_DENOMINATOR_WEEK, (
        f"Course week {IN_DENOMINATOR_WEEK} is term week {term_week} in this world's own table; if "
        "they were the same number this test could not tell the two axes apart."
    )

    body, answered = report_door.payload(course_week=IN_DENOMINATOR_WEEK)
    week = report_api_contract.member(body, report_api_contract.week_member, answered=answered)

    assert week[report_api_contract.course_week_field] == IN_DENOMINATOR_WEEK, (
        f"`week.{report_api_contract.course_week_field}` is "
        f"{week[report_api_contract.course_week_field]} for the report this test asked for by "
        f"course week {IN_DENOMINATOR_WEEK}."
    )
    assert week[report_api_contract.term_week_field] == term_week, (
        f"`week.{report_api_contract.term_week_field}` is "
        f"{week[report_api_contract.term_week_field]}; course week {IN_DENOMINATOR_WEEK} of a "
        f"six-week section beginning in term week {TERM_WEEK_OF_COURSE_WEEK[1]} is term week "
        f"{term_week}. §2.2 makes the term week the quiet sub-label beside the course week, so "
        "both are on the wire and E4-08 renders one under the other."
    )


def test_the_section_member_carries_the_code_and_the_length_the_start_letter_gives_it(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The sketch's `section` member, against the row this world seeded.

    §2.2 derives a section's length and start date from its code through the
    term's start-letter map, and E4-08's trend axis needs the length to know how
    many weeks it is drawing. The values here are *inputs* this world wrote, so
    the assertion is that the payload reports the section it was asked about —
    the near miss being a payload that reports some other section of the same
    course, which shares everything above the section row.

    **The mutation this kills:** `length_weeks` taken from the term (18) rather
    than from the section (6), which is the column one join away and is the number
    an aggregate page would want.
    """
    length, _first_term_week, _start = SEEDED_COHORTS[TAUGHT_COHORT]
    assert length == TAUGHT_LENGTH_WEEKS, (
        f"Cohort {TAUGHT_COHORT!r} is {length} weeks in `SEEDED_COHORTS` and this module is written "
        f"for {TAUGHT_LENGTH_WEEKS}."
    )

    body, answered = report_door.payload(course_week=FULL_WEEK)
    section = report_api_contract.member(
        body, report_api_contract.section_member, answered=answered
    )

    assert section["code"] == TAUGHT_SECTION_CODE, (
        f"`section.code` is {section['code']!r} and this world's taught section is "
        f"{TAUGHT_SECTION_CODE!r}. The other section in this world — the one she does not teach — "
        "sits under the same course, so a payload naming it would agree with everything above the "
        "section row and differ exactly here."
    )
    assert section["length_weeks"] == TAUGHT_LENGTH_WEEKS, (
        f"`section.length_weeks` is {section['length_weeks']} and the section runs "
        f"{TAUGHT_LENGTH_WEEKS} weeks. The term it belongs to runs 18."
    )


def test_the_trend_holds_a_point_for_every_published_week_including_the_quiet_ones(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """ADR 0147's zero-filling: the chart's weeks come from the calendar, not from the rows.

    The views hold a row only for a section-week somebody answered, and ADR 0147
    rejects the alternative — a zero row per week the section runs — because "a
    zero row asserts something the data does not say". What it puts here instead
    is the fill: "E4-07 knows which weeks the section runs, because it is the
    layer that already derives the course-week axis, and zero-filling there is one
    loop in one place."

    **The mutation this kills:** a trend built by iterating the distribution's own
    rows, which draws a line straight through every quiet week and makes a term
    with two silent weeks look like a term with four.
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
    plotted = [entry[report_api_contract.course_week_field] for entry in trend]

    assert sorted(plotted) == sorted(published), (
        f"The instructor trend plots course weeks {sorted(plotted)} and the published weeks are "
        f"{sorted(published)}. Course week {SILENT_WEEK} was answered by nobody, so the views hold "
        "no row for it and it is exactly the week a trend built out of those rows loses."
    )
    assert len(plotted) == len(set(plotted)), (
        f"The trend plots {plotted}, which repeats a week. Two points for one week is a fill that "
        "ran beside the rows rather than over them."
    )


def test_a_week_nobody_rated_is_a_point_with_no_mean_rather_than_a_point_at_zero(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """ "A stored zero and a missing week never arrive looking the same" — both halves of it.

    The quiet week is the one place the sentence can be measured, and it takes two
    assertions because the two members answer it differently. The **distribution**
    is filled: five Likert values, five counts, every one of them zero, which is a
    true statement — nobody chose any of them. The **mean** is not: no rating was
    submitted, and 0.0 is outside SPEC §3.2's 1-5 range and would draw a line to
    the floor of the chart.

    **The mutation this kills:** a fill that writes `0` into every member of a
    quiet week, mean included, which is exactly what "zero-fill" reads like to
    somebody implementing it from the ADR's own verb.
    """
    body, answered = report_door.payload(course_week=SILENT_WEEK)

    quiet = distribution_of(
        body, report_api_contract, report_api_contract.instructor_stream, answered
    )
    assert quiet == dict.fromkeys(LIKERT_VALUES, 0), (
        f"The instructor distribution for the quiet week is {quiet}; SPEC §3.2's five Likert values "
        "each hold a count, and in a week nobody answered every one of them is zero. An empty "
        "object leaves E4-09's histogram with no bars to draw rather than five empty ones."
    )

    trend = report_api_contract.stream_member(
        body,
        report_api_contract.instructor_stream,
        report_api_contract.trend_field,
        answered=answered,
    )
    point = [
        entry for entry in trend if entry[report_api_contract.course_week_field] == SILENT_WEEK
    ]
    assert len(point) == 1, f"The trend carries {len(point)} points for the quiet week: {trend}."
    assert point[0][report_api_contract.trend_mean_field] is None, (
        f"The quiet week's trend mean is "
        f"{point[0][report_api_contract.trend_mean_field]!r}. Nobody rated that week, so there is "
        "no mean; a zero is a rating value nobody can give and would plot below every real one."
    )


def test_the_distribution_counts_the_ratings_each_stream_was_given(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The two streams' this-week distributions, over ratings the two streams disagree about.

    E4-03 derives the stream from `question.stream` and never from a question's
    ordinal; this is the payload's half of that — the instructor bars and the
    course bars are different tallies, and a payload that served one where the
    other belongs is red rather than approximately right.

    **The mutation this kills:** both streams served from one query, or the two
    swapped. **The absent answer:** the fifth respondent's missing instructor
    rating contributes to no bar, which is the same sentence the mean test makes
    one member over.
    """
    body, answered = report_door.payload(course_week=FULL_WEEK)

    instructor = distribution_of(
        body, report_api_contract, report_api_contract.instructor_stream, answered
    )
    course = distribution_of(body, report_api_contract, report_api_contract.course_stream, answered)

    assert instructor == expected_counts(FULL_WEEK_INSTRUCTOR_RATINGS), (
        f"The instructor distribution is {instructor}; the ratings submitted to that stream were "
        f"{list(FULL_WEEK_INSTRUCTOR_RATINGS)}, where `None` is a question left unanswered."
    )
    assert course == expected_counts(FULL_WEEK_COURSE_RATINGS), (
        f"The course distribution is {course}; the ratings submitted to that stream were "
        f"{list(FULL_WEEK_COURSE_RATINGS)}."
    )
    assert instructor != course, (
        "Both streams answered the same distribution, and this world gave them different ratings "
        f"on purpose — {list(FULL_WEEK_INSTRUCTOR_RATINGS)} against "
        f"{list(FULL_WEEK_COURSE_RATINGS)}. One query serving both members satisfies every "
        "assertion above that is about a shape."
    )
