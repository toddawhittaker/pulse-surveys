"""Every division the report makes — ticket E4-07, criterion 7 and ADR 0147's re-homed pair.

ADR 0147 settles that the three report views return **counts** and that "E4-07's
payload layer divides", that "no view names `enrollment`, and the enrolled
denominator is not here", and that only the section-weeks which were answered get
a row at all. It then re-homes two of E4-03's own acceptance criteria onto this
ticket, and E4-07's work order takes them:

  - **the mean's semantics** — "the weekly mean is the mean of that week's
    submitted ratings; an absent response contributes nothing to the mean (it
    costs the response rate, not the average)";
  - **the enrolment-window boundary** — "a student enrolled for weeks 1-3 of a
    6-week section is in week 2's denominator and not week 5's, driven on both
    sides of the boundary".

Criterion 7 is the third thing here, and it is the one a silent 404 would make
unrenderable: a zero-response published week returns the full shape. The work
order settles what "zero rates" means, and it is not "everything is zero":

> with enrolled > 0 and zero responses, `response_rate` is 0.0; a `validity_rate`
> over zero responses has no value and uses the schema's explicit absent state
> (it is not 0 — zero would assert "all invalid").

**Where each expectation comes from.** The counts come from the views E4-03
shipped, read on this suite's own session — which is the layer ADR 0147 says the
payload divides, so a payload that agreed with a *different* set of counts is red
rather than merely different. The denominators come from the rows this world
seeded, written out in the test that asserts them. Nothing here re-derives a rate
with the arithmetic the payload uses (`docs/MISTAKES.md` entry 19); every
assertion names its two numbers.

**Which failure a red is, before E4-07 lands.** `report_api_contract`'s lookups
and `member` are `pytest.fail` calls naming the deliverable, so the first red is a
FAILED naming the router, the schema or the missing member
(`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.report_api import (
    FULL_WEEK,
    FULL_WEEK_COURSE_RATINGS,
    FULL_WEEK_INSTRUCTOR_RATINGS,
    IN_DENOMINATOR_WEEK,
    OUT_OF_DENOMINATOR_WEEK,
    RESPONSES_IN_WEEK,
    SECOND_HELD_WEEK,
    SILENT_WEEK,
    TAUGHT_COHORT,
    TERM_WEEK_OF_COURSE_WEEK,
    ReportDoor,
    a_student_enrolled,
)
from fixtures.report_views import response_counts_row
from fixtures.survey_windows import SEEDED_COHORTS, WINDOWS_BY_TERM_WEEK

pytestmark = pytest.mark.integration

# The world's own enrolment, written out rather than counted by the assertion
# that reads it. Five respondents are enrolled from the section's first day with
# no end date; one leaver is enrolled from the same day until after course week
# 3's survey window has closed and before course week 4's has opened. So six
# people are enrolled across course weeks 1-3 and five across 4-6, and the tests
# below assert that premise before they assert a denominator.
#
# **The leaver's date is chosen against the stored window instants and not
# against the calendar** — `LEAVER_ENDED_ON` in `tests/fixtures/report_api.py`
# carries the incident, which is this suite's own: a date read off the
# institution's wall clock lands a day inside the previous week in UTC.
ENROLLED_WITH_THE_LEAVER = 6
ENROLLED_WITHOUT_THE_LEAVER = 5

# **The platform-dated late add this ticket's boundary review added**, and the two
# weeks that tell a denominator reading `started_on` from one reading SPEC §3.4's
# enrolment window.
#
# He is enrolled with `started_on` at the section's own start date — which is what
# a roster sync writes when it first sights a member, and what a day-one student
# carries — and with `lms_window_start` at the opening instant of course week 4's
# survey window, which is the platform saying when his enrolment actually began.
# E3-04's tier 1 is "the earliest course week whose `closes_at >= lms_window_start`",
# so his first enrolled week is course week 4.
#
# So the denominators do not move for course weeks 1 to 3 and gain one from course
# week 4 onwards. Course week 2 still holds the six the leaver is part of; course
# week 5 holds the five that are left after she goes, plus him — six again, and the
# equality of the two numbers is a coincidence of this world rather than the claim.
# The claim is the pair: **week 2 must not count him and week 5 must.**
LATE_ADD_FIRST_COURSE_WEEK = SECOND_HELD_WEEK
ENROLLED_IN_WEEK_TWO_WITH_THE_LATE_ADD = ENROLLED_WITH_THE_LEAVER
ENROLLED_IN_WEEK_FIVE_WITH_THE_LATE_ADD = ENROLLED_WITHOUT_THE_LEAVER + 1

# The full week's instructor mean, written out. Four of the five respondents
# answered the instructor rating, with 5, 4, 4 and 3; the fifth left it
# unanswered. 16 / 4 = 4.0, and 16 / 5 = 3.2 is the number a payload that divided
# by the *response* count would produce.
FULL_WEEK_INSTRUCTOR_MEAN = 4.0
FULL_WEEK_COURSE_MEAN = 3.0


def counts_for(door: ReportDoor, course_week: int) -> dict[str, Any] | None:
    """`report_response_counts` for one course week, read on this suite's own session.

    The layer ADR 0147 says the payload divides. Read here so that an assertion
    about a rate names the two counts it is a ratio of, rather than comparing one
    computed number against another computed number.
    """
    return response_counts_row(
        door.world.session,
        section_id=door.rows.taught_section_id,
        week_id=door.rows.week_id(course_week),
    )


def test_the_response_rate_is_the_weeks_responses_over_its_enrolment(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The division ADR 0147 moves out of SQL, with both of its numbers named.

    **The mutation this kills:** a response rate divided by the wrong denominator
    — the number of respondents the week happens to hold, which makes every rate
    1.0, or the section's whole enrolment counted without the week. The first is
    the shape a payload reaches for when the enrolment helper is awkward to call;
    the second is the defect the boundary pair below is about.
    """
    stored = counts_for(report_door, FULL_WEEK)
    assert stored is not None and int(stored["responses"]) == RESPONSES_IN_WEEK[FULL_WEEK], (
        f"`report_response_counts` holds {stored} for course week {FULL_WEEK}, and this world "
        f"planted {RESPONSES_IN_WEEK[FULL_WEEK]} responses in it. Every assertion below is a ratio "
        "of that count."
    )
    assert len(report_door.rows.enrolled_user_ids()) == ENROLLED_WITH_THE_LEAVER, (
        f"This world enrolled {len(report_door.rows.enrolled_user_ids())} people in the taught "
        f"section and the denominators below are written for {ENROLLED_WITH_THE_LEAVER}."
    )

    body, answered = report_door.payload(course_week=FULL_WEEK)
    rates = report_api_contract.member(body, report_api_contract.rates_member, answered=answered)

    assert rates[report_api_contract.responses_field] == RESPONSES_IN_WEEK[FULL_WEEK], (
        f"`rates.{report_api_contract.responses_field}` is "
        f"{rates[report_api_contract.responses_field]}; the week holds "
        f"{RESPONSES_IN_WEEK[FULL_WEEK]} responses."
    )
    assert rates[report_api_contract.enrolled_field] == ENROLLED_WITH_THE_LEAVER, (
        f"`rates.{report_api_contract.enrolled_field}` is "
        f"{rates[report_api_contract.enrolled_field]}; course week {FULL_WEEK} runs while all "
        f"{ENROLLED_WITH_THE_LEAVER} enrolments this world wrote are live."
    )
    assert rates[report_api_contract.response_rate_field] == pytest.approx(
        RESPONSES_IN_WEEK[FULL_WEEK] / ENROLLED_WITH_THE_LEAVER
    ), (
        f"`rates.{report_api_contract.response_rate_field}` is "
        f"{rates[report_api_contract.response_rate_field]}, and the week is "
        f"{RESPONSES_IN_WEEK[FULL_WEEK]} responses over {ENROLLED_WITH_THE_LEAVER} enrolled."
    )


def test_the_validity_rate_divides_the_views_two_counts(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """§3.3's rate, and work-order decision 4's `valid_responses` member beside it.

    SPEC §3.3: "Validity rate = valid responses ÷ responses". ADR 0147 puts both
    numerators in `report_response_counts` and neither division in SQL, and the
    work order adds `valid_responses` to `rates` as a named divergence from the
    README sketch — E4-09's components consume the count, not only the ratio, and
    its source is `response.is_valid` and never `classification`.

    **The mutation this kills:** a validity rate computed over the *enrolment*
    rather than over the responses, which reads as a plausible percentage and is a
    different statement about a week. **The near miss:** the member present and
    always equal to the response count, which the comparison against the view's
    own `valid_responses` catches.
    """
    stored = counts_for(report_door, FULL_WEEK)
    assert stored is not None, (
        f"`report_response_counts` holds no row for course week {FULL_WEEK}, so there is nothing "
        "for this test to compare a rate against."
    )
    responses = int(stored["responses"])
    valid = int(stored["valid_responses"])
    assert responses > 0, "The week holds no responses; every ratio below would be about nothing."

    body, answered = report_door.payload(course_week=FULL_WEEK)
    rates = report_api_contract.member(body, report_api_contract.rates_member, answered=answered)

    assert rates[report_api_contract.valid_responses_field] == valid, (
        f"`rates.{report_api_contract.valid_responses_field}` is "
        f"{rates[report_api_contract.valid_responses_field]} and `report_response_counts."
        f"valid_responses` is {valid} for the same section-week. The member's source is "
        "`response.is_valid` as `app/services/validity.py` maintains it (ADR 0147)."
    )
    assert rates[report_api_contract.validity_rate_field] == pytest.approx(valid / responses), (
        f"`rates.{report_api_contract.validity_rate_field}` is "
        f"{rates[report_api_contract.validity_rate_field]}, and the week is {valid} valid responses "
        f"over {responses} responses."
    )


def test_a_student_enrolled_through_course_week_three_is_in_week_twos_denominator(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """ADR 0147's re-homed criterion 5, the half where the leaver counts.

    §3.4's enrolment-window rules decide which weeks' items form a denominator,
    and ADR 0147 keeps them in the Python that already implements them rather
    than re-reading them in SQL. The leaver here is enrolled from the section's
    first day until after course week 3's window has closed, so course week 2 is
    wholly inside her enrolment and she is one of that week's six.

    **The mutation this kills:** a denominator counting only enrolments that are
    live *now* — the shape `enrollment.ended_on IS NULL` produces, which is right
    for a student read path and wrong for a report about a week in the past. It
    answers five here and five in the pair below, so only the pair catches it.
    """
    assert len(report_door.rows.enrolled_user_ids()) == ENROLLED_WITH_THE_LEAVER, (
        f"This world enrolled {len(report_door.rows.enrolled_user_ids())} people in the taught "
        f"section; the pair is written for {ENROLLED_WITH_THE_LEAVER} with the leaver and "
        f"{ENROLLED_WITHOUT_THE_LEAVER} without her."
    )

    body, answered = report_door.payload(course_week=IN_DENOMINATOR_WEEK)
    enrolled = report_api_contract.member(
        body,
        report_api_contract.rates_member,
        report_api_contract.enrolled_field,
        answered=answered,
    )
    assert enrolled == ENROLLED_WITH_THE_LEAVER, (
        f"Course week {IN_DENOMINATOR_WEEK} reports {enrolled} enrolled and this world has "
        f"{ENROLLED_WITH_THE_LEAVER} people enrolled across it: five who never leave, and one whose "
        "enrolment runs from the section's first day until after course week 3 closed. Answering "
        f"{ENROLLED_WITHOUT_THE_LEAVER} means the leaver was dropped from a week she was there for."
    )


def test_the_same_student_is_absent_from_course_week_fives_denominator(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """ADR 0147's re-homed criterion 5, the half where the leaver does not count.

    The other side of the same boundary, over the same rows, one week apart from
    the window that ends her enrolment.

    **The mutation this kills:** a denominator that counts every enrolment the
    section has ever held — the shape a plain `count(*)` over `enrollment`
    produces. It answers six here *and* six in the test above, so the half above
    is green against it and only this half is red. That is why the two are
    written as a pair and why neither is worth reading alone.
    """
    body, answered = report_door.payload(course_week=OUT_OF_DENOMINATOR_WEEK)
    enrolled = report_api_contract.member(
        body,
        report_api_contract.rates_member,
        report_api_contract.enrolled_field,
        answered=answered,
    )
    assert enrolled == ENROLLED_WITHOUT_THE_LEAVER, (
        f"Course week {OUT_OF_DENOMINATOR_WEEK} reports {enrolled} enrolled. The leaver's enrolment "
        "ended before course week 4's window opened, so this week has "
        f"{ENROLLED_WITHOUT_THE_LEAVER} people in it and the week in the paired test above has "
        f"{ENROLLED_WITH_THE_LEAVER}."
    )


def test_the_weekly_mean_is_the_mean_of_the_ratings_that_were_submitted(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """ADR 0147's re-homed criterion 3: an absent answer costs the rate, never the average.

    Four of the full week's five respondents rated the instructor — 5, 4, 4, 3 —
    and the fifth left that question unanswered while answering the course rating
    and the workload figure. So the instructor mean is 16/4 and the course mean is
    15/5, and the two streams disagree, which is what makes the assertion about
    *this* stream rather than about arithmetic in general.

    **The mutation this kills:** a mean divided by the week's response count
    rather than by the number of ratings behind it — 16/5 = 3.2, a number that
    looks like a mean and is a quiet penalty for silence. **The near miss:** the
    course stream's own mean, 3.0, which a payload reading the wrong stream
    produces and which neither of the other two numbers is.
    """
    answered_ratings = [rating for rating in FULL_WEEK_INSTRUCTOR_RATINGS if rating is not None]
    assert len(answered_ratings) < len(FULL_WEEK_INSTRUCTOR_RATINGS), (
        "Every respondent in the full week answered the instructor rating, so there is no absent "
        "answer for this test to be about."
    )

    body, answered = report_door.payload(course_week=FULL_WEEK)
    trend = report_api_contract.stream_member(
        body,
        report_api_contract.instructor_stream,
        report_api_contract.trend_field,
        answered=answered,
    )
    point = [entry for entry in trend if entry[report_api_contract.course_week_field] == FULL_WEEK]
    assert (
        len(point) == 1
    ), f"The instructor trend carries {len(point)} points for course week {FULL_WEEK}: {trend}."
    assert point[0][report_api_contract.trend_mean_field] == pytest.approx(
        FULL_WEEK_INSTRUCTOR_MEAN
    ), (
        f"The instructor mean for course week {FULL_WEEK} is "
        f"{point[0][report_api_contract.trend_mean_field]}; the ratings submitted were "
        f"{answered_ratings}, which average {FULL_WEEK_INSTRUCTOR_MEAN}. Dividing by the week's "
        f"{RESPONSES_IN_WEEK[FULL_WEEK]} responses instead gives 3.2; the course stream's own mean "
        f"over {list(FULL_WEEK_COURSE_RATINGS)} is {FULL_WEEK_COURSE_MEAN}."
    )


def test_the_unanswered_rating_still_costs_the_weeks_response_rate(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The other half of that sentence: the response is counted even where the answer is not.

    ADR 0147 keeps the two halves apart on purpose — E4-03 asserts that a
    response which rated one stream and not the other "adds nothing to the other
    stream's distribution and is still counted in `report_response_counts`", and
    the payload half of it is here: five responses, five in the numerator, whatever
    each of them left blank.

    **The mutation this kills:** a response rate counted over the *ratings* a
    stream received rather than over the week's responses — the mirror image of
    the mean's mutation one test up, and one that reads as a section with worse
    participation than it has. The full week is the only place the two numerators
    differ: four instructor ratings against five responses.

    **The docstring used to claim that kill and the body could not make it.** It
    asserted `rates.responses` and never read `response_rate`, so a rate computed
    over the ratings would have left this test green and been caught — if at all —
    by the sibling three tests up. Both numbers are read now, and the near miss is
    named rather than merely avoided: the value a ratings-denominated rate would
    produce is computed from the payload's own distribution and required to be
    absent. `docs/MISTAKES.md` entry 2's rule is to assert the forbidden state,
    and this is what that looks like when the permitted one is a plausible
    neighbour of it.
    """
    body, answered = report_door.payload(course_week=FULL_WEEK)
    rates = report_api_contract.member(body, report_api_contract.rates_member, answered=answered)
    distribution = report_api_contract.stream_member(
        body,
        report_api_contract.instructor_stream,
        report_api_contract.distribution_field,
        answered=answered,
    )
    rated = sum(int(count) for count in distribution.values())
    enrolled = rates[report_api_contract.enrolled_field]

    assert 0 < rated < RESPONSES_IN_WEEK[FULL_WEEK], (
        f"The instructor stream holds {rated} ratings and the week holds "
        f"{RESPONSES_IN_WEEK[FULL_WEEK]} responses. The two have to differ, and neither may be "
        "zero, or the wrong denominator and the right one produce the same rate and this test "
        "cannot tell them apart."
    )
    assert rates[report_api_contract.responses_field] == RESPONSES_IN_WEEK[FULL_WEEK], (
        f"`rates.{report_api_contract.responses_field}` is "
        f"{rates[report_api_contract.responses_field]} and the week holds "
        f"{RESPONSES_IN_WEEK[FULL_WEEK]} responses, one of which left the instructor rating "
        "unanswered. An absent answer costs the rate and not the average, so it is still a response."
    )
    assert rates[report_api_contract.response_rate_field] == pytest.approx(
        RESPONSES_IN_WEEK[FULL_WEEK] / enrolled
    ), (
        f"`rates.{report_api_contract.response_rate_field}` is "
        f"{rates[report_api_contract.response_rate_field]}; the week is "
        f"{RESPONSES_IN_WEEK[FULL_WEEK]} responses over {enrolled} enrolled. Counted over the "
        f"{rated} instructor ratings instead it would be {rated / enrolled}, which is the number "
        "this test exists to refuse."
    )
    assert rates[report_api_contract.response_rate_field] != pytest.approx(rated / enrolled), (
        f"`rates.{report_api_contract.response_rate_field}` is {rated / enrolled}, which is the "
        f"{rated} ratings this stream received over {enrolled} enrolled rather than the week's "
        f"{RESPONSES_IN_WEEK[FULL_WEEK]} responses. A student who answered and left one question "
        "blank is a student who answered."
    )


def test_a_zero_response_published_week_answers_a_response_rate_of_zero(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """Criterion 7: "nobody responded" is a state, not a 404.

    > A zero-response published week returns the full shape — zero rates, empty
    > distributions, the week in navigation — because a silent 404 there would
    > make "nobody responded" unrenderable.

    ADR 0147 gives only answered section-weeks a row in the views, so this is the
    week where the payload layer has nothing to read and must still answer. With
    enrolled above zero the response rate has a defined value and it is 0.0.

    **The mutation this kills:** a 404, or an absent `response_rate`, for a week
    the views hold no row for. **The premise:** the view genuinely holds no row,
    asserted before the read, or this test would be about an ordinary week.
    """
    assert counts_for(report_door, SILENT_WEEK) is None, (
        f"`report_response_counts` holds a row for course week {SILENT_WEEK}, which this world "
        "planted no responses in. ADR 0147 gives a row only to the section-weeks that were "
        "answered, so this test would otherwise not be about the absent-row case at all."
    )

    answered = report_door.report(course_week=SILENT_WEEK)
    assert answered.status_code == 200, (
        f"A published week with no responses answered {answered.status_code}. Criterion 7 is that "
        "the full shape comes back: a silent 404 makes 'nobody responded' unrenderable, and it is "
        f"the state most weeks are in early in a term. Body begins {answered.text[:400]!r}."
    )
    body = answered.json()
    rates = report_api_contract.member(body, report_api_contract.rates_member, answered=answered)
    assert rates[report_api_contract.responses_field] == 0, (
        f"`rates.{report_api_contract.responses_field}` is "
        f"{rates[report_api_contract.responses_field]} for a week nobody answered."
    )
    assert rates[report_api_contract.enrolled_field] > 0, (
        f"`rates.{report_api_contract.enrolled_field}` is "
        f"{rates[report_api_contract.enrolled_field]} for a week this world enrolled people "
        "through, so the zero-denominator rule rather than the zero-numerator one would apply and "
        "this test would be about the other case."
    )
    assert rates[report_api_contract.response_rate_field] == pytest.approx(0.0), (
        f"`rates.{report_api_contract.response_rate_field}` is "
        f"{rates[report_api_contract.response_rate_field]} over "
        f"{rates[report_api_contract.enrolled_field]} enrolled and no responses. The work order "
        "settles it: with enrolled > 0 and zero responses the response rate is 0.0 — a real "
        "number about a real week, not an absence."
    )


def test_a_zero_response_week_leaves_the_validity_rate_explicitly_absent(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The zero-denominator rule the work order settles, on the rate that has no value.

    > a `validity_rate` over zero responses has no value and uses the schema's
    > explicit absent state (it is not 0 — zero would assert "all invalid").

    This is the assertion the criterion's own words are easiest to get wrong: a
    payload that answered `0.0` here would satisfy a reading of criterion 7's
    "zero rates" and would tell an instructor that every response that week was
    invalid, in a week that had none.

    **The mutation this kills:** `validity_rate = valid / responses or 0`, and its
    sibling `0 if not responses else …`. **The near miss:** the member dropped
    from the payload altogether, which E4-09's components cannot tell from a
    schema that never had it — so the member must be *present* and null.
    """
    body, answered = report_door.payload(course_week=SILENT_WEEK)
    rates = report_api_contract.member(body, report_api_contract.rates_member, answered=answered)

    assert report_api_contract.validity_rate_field in rates, (
        f"`rates` carries {sorted(rates)} and no `{report_api_contract.validity_rate_field}`. The "
        "explicit absent state is a member holding null, not a member that is gone: E4-09 renders "
        "the absence, and a missing key and a schema that never declared one look the same on the "
        "wire."
    )
    assert rates[report_api_contract.validity_rate_field] is None, (
        f"`rates.{report_api_contract.validity_rate_field}` is "
        f"{rates[report_api_contract.validity_rate_field]!r} for a week with no responses. Zero "
        "would say every response that week was invalid; there were none."
    )


def test_the_zero_response_week_is_still_in_the_week_navigation(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """Criterion 7's last clause: the week is in navigation.

    A week nobody answered is still a week that closed, so it is published and an
    instructor can page to it. A payload that reported the full shape and then
    left the week out of its own navigation would render a page nobody can reach.

    **The mutation this kills:** a published-week list built from the weeks the
    report views hold rows for — which is the join an implementation reaches for
    once it has those rows in hand, and which silently drops every quiet week.
    """
    body, answered = report_door.payload(course_week=SILENT_WEEK)
    published = report_api_contract.member(
        body,
        report_api_contract.week_member,
        report_api_contract.published_weeks_field,
        answered=answered,
    )
    assert SILENT_WEEK in published, (
        f"Course week {SILENT_WEEK} is not in {published}, and its window closed before the clock "
        "this door pretends. Nobody answered it, which is a fact about responses and not about the "
        "calendar."
    )
    assert TERM_WEEK_OF_COURSE_WEEK[SILENT_WEEK] not in published, (
        f"{published} carries this week's *term* number "
        f"{TERM_WEEK_OF_COURSE_WEEK[SILENT_WEEK]} rather than its course number {SILENT_WEEK}."
    )


def _enrol_the_platform_dated_late_add(door: ReportDoor) -> Any:
    """One member the platform dated into course week 4, committed so the tool sees him.

    `started_on` is the section's own start date — the value a roster sync writes
    when it first sights a member, and the one a day-one student carries — while
    `lms_window_start` is the platform's own statement of when his enrolment began.
    The two disagree on purpose: that disagreement is the whole of what this pair
    is about, and a late add whose `started_on` already pointed at course week 4
    would be counted correctly by a denominator that reads nothing but `started_on`.
    """
    world = door.rows.world
    _length, _first, section_starts = SEEDED_COHORTS[TAUGHT_COHORT]
    opens_at, _closes_at = WINDOWS_BY_TERM_WEEK[
        TERM_WEEK_OF_COURSE_WEEK[LATE_ADD_FIRST_COURSE_WEEK]
    ]
    late_add = a_student_enrolled(
        world,
        "e4-15-platform-dated-late-add",
        started_on=section_starts,
        ended_on=None,
        lms_window_start=opens_at,
    )
    door.commit()
    return late_add


def _enrolled_in(door: ReportDoor, contract: Any, course_week: int) -> int:
    """The enrolled denominator one course week's payload reports."""
    body, answered = door.payload(course_week=course_week)
    rates = contract.member(body, contract.rates_member, answered=answered)
    return int(rates[contract.enrolled_field])


def test_a_platform_dated_late_add_is_outside_the_denominator_of_the_weeks_before_him(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """SPEC §3.4's first enrolment tier, applied to the report's own denominator.

    §3.4: "the denominator starts at the student's first enrolled week (from NRPS
    enrollment data)", and E3-04 built that as three tiers with
    `enrollment.lms_window_start` as the first of them — a member the platform
    dated is credited from the week that date falls in. ADR 0147 says the report's
    denominator is computed "on the clock and enrolment helpers
    `app/services/grading.py` already uses, so §3.4's window rules are read once".
    This is the test of that sentence.

    The member here is dated by the platform into course week 4 and carries a
    `started_on` at the section's start, so a denominator that reads `started_on`
    and `ended_on` alone counts him in every week of the section — including the
    three before he arrived.

    **The pair is in this test rather than in a sibling**, because both halves must
    be the same world one week apart: course week 2 must not count him and course
    week 5 must. Two separately built worlds could differ in the leaver's dates and
    the boundary would stop being the only thing that moved.

    **The mutation this kills:** the denominator reading `started_on`/`ended_on`
    only — which is what ships today, and which ADR 0147's own claim about reading
    §3.4's rules once says it does not. A wrong denominator renders as a plausible
    percentage: the response rate for the section's first three weeks is quietly
    understated for the rest of the term.

    **The near miss it must survive:** a denominator that reads `lms_window_start`
    and stops reading `started_on`, which would count him from week 1 again for any
    member the platform did *not* date. The three tests above this one are what hold
    that half — the leaver and the day-one respondents carry no platform window at
    all and their denominators are asserted there.

    **What it does not reach** (`docs/MISTAKES.md` entry 14): E3-04's tier 3, the
    member first seen in a later roster sync. That tier is decided by the
    `nrps_call` log rather than by an enrolment column, and no world in this suite
    writes one.
    """
    contract = report_api_contract
    before = _enrolled_in(report_door, contract, IN_DENOMINATOR_WEEK)
    assert before == ENROLLED_WITH_THE_LEAVER, (
        f"Course week {IN_DENOMINATOR_WEEK} reports {before} enrolled before this test adds "
        f"anybody, and the canonical world holds {ENROLLED_WITH_THE_LEAVER}. Every number below is "
        "a comparison against that starting state."
    )

    _enrol_the_platform_dated_late_add(report_door)

    after = _enrolled_in(report_door, contract, IN_DENOMINATOR_WEEK)
    assert after == ENROLLED_IN_WEEK_TWO_WITH_THE_LATE_ADD, (
        f"Course week {IN_DENOMINATOR_WEEK}'s denominator is {after} with a member the platform "
        f"dated into course week {LATE_ADD_FIRST_COURSE_WEEK}. He was not enrolled that week: "
        "`enrollment.lms_window_start` is the platform's own statement of when his enrolment "
        "began, and SPEC §3.4 starts a denominator at the student's first enrolled week from that "
        "data.\n\n"
        f"{ENROLLED_IN_WEEK_TWO_WITH_THE_LATE_ADD + 1} here is a denominator reading `started_on` "
        "and `ended_on` and nothing else. His `started_on` is the section's start date, because "
        "that is what a roster sync writes when it first sights somebody — so on that reading he "
        "is a day-one student, three weeks of this section's response rates are divided by one too "
        "many, and every one of them renders as a plausible percentage. ADR 0147's own claim is "
        "that this layer reads §3.4's window rules once rather than a second time in SQL."
    )

    later = _enrolled_in(report_door, contract, OUT_OF_DENOMINATOR_WEEK)
    assert later == ENROLLED_IN_WEEK_FIVE_WITH_THE_LATE_ADD, (
        f"Course week {OUT_OF_DENOMINATOR_WEEK}'s denominator is {later} and this world holds "
        f"{ENROLLED_WITHOUT_THE_LEAVER} live enrolments there plus the late add — "
        f"{ENROLLED_IN_WEEK_FIVE_WITH_THE_LATE_ADD}.\n\n"
        "This is the half that stops the fix being 'exclude him everywhere': a member the platform "
        "dated into course week "
        f"{LATE_ADD_FIRST_COURSE_WEEK} is in the denominator of every week from that one onward, "
        "and a denominator that dropped him for the whole term would understate the later weeks "
        "exactly as reading `started_on` alone overstates the earlier ones."
    )
