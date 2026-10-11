"""The exclusion log — ticket E6-05, criterion 10, and work order decision 1's row.

> The log shows `EXCLUDED` and `KEPT` rows inside the reader's own grant, with the
> section, the role, flagged or the reason, and the date. A row whose comment its
> instructor cannot see carries no excerpt.

Decision 1 settles the row exactly — `{section_label, decided_as, flagged, reason,
decided_on, excerpt}`, plus `decision` (the stored state token, `EXCLUDED` or
`KEPT`), which the ruling on dispute E6-05-03 adds so each row says its direction
— and which rows: every `moderation_state` row with a decider
and state `EXCLUDED` or `KEPT`, inside the reader's own leadership grant, newest
first. `decided_on` is a date in the institution's zone; the excerpt is the first
140 characters, withheld when the comment is not visible on its own instructor's
report (a date beside text from a held stream would place that text in a week).

**The rows are planted, not driven**: each carries a reason this file chose, so a
row can be found in the log by it, and a decision instant this file chose, so the
date can be asserted. The decision instant is 03:30 UTC on 10 November 2026,
which is 22:30 on 9 November in New York (standard time) — so a date taken in UTC
is a different day from the one SPEC §3.1's institution zone gives, and is red.

**Which failure a red is, before E6-05 lands.** `lead_routes` fails naming the
routes — a FAILED, never an ERROR (`docs/MISTAKES.md` entry 44).
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from fixtures.instructor_decisions import STORED_EXCLUDED, STORED_KEPT
from fixtures.lead_review import (
    AS_CHAIR,
    AS_INSTRUCTOR,
    AS_LEAD_FACULTY,
    EXCERPT_LENGTH,
    LOG_DECIDED_AS,
    LOG_DECIDED_ON,
    LOG_DECISION,
    LOG_EXCERPT,
    LOG_FLAGGED,
    LOG_REASON,
    LOG_ROW_FIELDS,
    LOG_SECTION_LABEL,
    UNMAPPED_COHORT,
    LeadReviewWorld,
)
from fixtures.moderation import CLEAR, HARMFUL
from fixtures.report_api import FIRST_HELD_WEEK, FULL_WEEK, TAUGHT_COHORT, strings_in
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = pytest.mark.integration

INSTITUTION_TIMEZONE_VARIABLE = "INSTITUTION_TIMEZONE"
THE_ZONE_THESE_DATES_ARE_WRITTEN_FOR = "America/New_York"

# Decided late on a Monday evening in New York, which is already Tuesday in UTC.
ACROSS_MIDNIGHT = datetime(2026, 11, 10, 3, 30, tzinfo=UTC)
ITS_INSTITUTION_DATE = "2026-11-09"

# Three instants a day apart, for the order test, each well inside one date.
EARLIER = datetime(2026, 11, 3, 15, 0, tzinfo=UTC)
MIDDLE = datetime(2026, 11, 4, 15, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)

# A comment long enough that its first 140 characters are not the whole of it,
# so the whole text, or an excerpt of 139 or 141 characters, is a different
# string from the one asserted.
LONG_TEXT = (
    "E6-05 a long harmful comment: the instructor mocked a question in the live session, then "
    "repeated the joke in the forum, and several of us have stopped asking anything at all "
    "since — this sentence carries on well past the excerpt's end"
)


def the_zone_is_the_one_these_dates_are_for(review: LeadReviewWorld) -> None:
    zone = review.configured.get(INSTITUTION_TIMEZONE_VARIABLE)
    assert zone == THE_ZONE_THESE_DATES_ARE_WRITTEN_FOR, (
        f"The application was built with `{INSTITUTION_TIMEZONE_VARIABLE}` {zone!r}; this module's "
        f"expected dates are written by hand for {THE_ZONE_THESE_DATES_ARE_WRITTEN_FOR!r}. A broken "
        "test, not a red."
    )


def a_comment(review: LeadReviewWorld, text: str, *, verdict: str, held: bool = False) -> Any:
    return review.plant(
        course_week=FIRST_HELD_WEEK if held else FULL_WEEK,
        stream=COURSE_STREAM if held else INSTRUCTOR_STREAM,
        text=text,
        verdict=verdict,
        cohort=TAUGHT_COHORT,
    )


def row_with_reason(rows: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    found = [row for row in rows if row.get(LOG_REASON) == reason]
    assert len(found) == 1, (
        f"The log carries {len(found)} rows with the reason {reason!r}; one decision was planted "
        f"with it. The reasons it carries: {[row.get(LOG_REASON) for row in rows]}."
    )
    return found[0]


def test_a_flagged_exclusion_row_carries_the_section_the_role_the_date_and_the_excerpt(
    lead_review: LeadReviewWorld,
) -> None:
    """Decision 1's row, member by member, for an AI-flagged comment the instructor excluded.

    **The mutations this kill:** a row carrying a time, an author, a decider's
    name or an answer id (the key set is exact); a row without `decision`, the
    six members of the work order before the ruling on dispute E6-05-03 (the key
    set is exact); `decision` anything but the stored `EXCLUDED`; `decided_as`
    read off today's assignments rather than the stored role; `flagged` false
    for a harmful comment; the date taken in UTC (it would read `2026-11-10`);
    the excerpt the whole text, or not the first 140 characters. **The near
    misses:** an excerpt of 139 or 141 characters; `decision` in the lower-case
    form the instructor's card uses for `status` (`excluded`), which the ruling
    does not settle.
    """
    review = lead_review
    the_zone_is_the_one_these_dates_are_for(review)
    assert len(LONG_TEXT) > EXCERPT_LENGTH + 20
    comment = a_comment(review, LONG_TEXT, verdict=HARMFUL)
    review.plant_decision(
        comment,
        STORED_EXCLUDED,
        decided_by=review.door.person_id,
        decided_as=AS_INSTRUCTOR,
        decided_at=ACROSS_MIDNIGHT,
    )

    rows = review.log_rows(review.lead)
    found = [row for row in rows if row.get(LOG_EXCERPT) == LONG_TEXT[:EXCERPT_LENGTH]]
    assert len(found) == 1, (
        f"The lead's log carries no row whose excerpt is the first {EXCERPT_LENGTH} characters of "
        f"the excluded comment; its excerpts are {[row.get(LOG_EXCERPT) for row in rows]}."
    )
    row = found[0]
    assert (
        set(row) == LOG_ROW_FIELDS
    ), f"The log row carries {sorted(row)}; decision 1 settles exactly {sorted(LOG_ROW_FIELDS)}."
    code = review.code_of(TAUGHT_COHORT)
    assert (
        isinstance(row[LOG_SECTION_LABEL], str) and code in row[LOG_SECTION_LABEL]
    ), f"The row's section label is {row[LOG_SECTION_LABEL]!r}; it names the section {code!r}."
    described = (row[LOG_DECISION], row[LOG_DECIDED_AS], row[LOG_FLAGGED], row[LOG_REASON])
    assert described == (STORED_EXCLUDED, AS_INSTRUCTOR, True, None), (
        f"The row is {row!r}: the stored decision {STORED_EXCLUDED!r}, the stored role "
        f"{AS_INSTRUCTOR!r}, AI-flagged, and no reason."
    )
    assert row[LOG_DECIDED_ON] == ITS_INSTITUTION_DATE, (
        f"The row's date is {row[LOG_DECIDED_ON]!r}. The decision was made at {ACROSS_MIDNIGHT} "
        f"UTC, which is {ITS_INSTITUTION_DATE} in {THE_ZONE_THESE_DATES_ARE_WRITTEN_FOR}; decision "
        "1 dates the row in the institution zone, with no time."
    )


def test_an_unflagged_exclusion_row_carries_its_reason_and_says_it_was_not_flagged(
    lead_review: LeadReviewWorld,
) -> None:
    """SPEC §5.2's "AI-flagged vs unflagged-with-reason", the unflagged side.

    **The mutation this kills:** `flagged` read off the decision (an exclusion)
    rather than off the comment's moderation verdict, which makes every row
    flagged and hides the cherry-picking trail the log exists for.
    """
    review = lead_review
    reason = "E6-05 unflagged exclusion: off-topic, about another course entirely"
    comment = a_comment(
        review, "E6-05 a clear comment the instructor excluded anyway", verdict=CLEAR
    )
    review.plant_decision(
        comment,
        STORED_EXCLUDED,
        decided_by=review.door.person_id,
        decided_as=AS_INSTRUCTOR,
        reason=reason,
    )
    row = row_with_reason(review.log_rows(review.lead), reason)
    assert row[LOG_FLAGGED] is False, f"The unflagged exclusion's row says flagged: {row!r}."


def test_the_log_shows_kept_rows_as_well_as_excluded_ones_and_no_undecided_flag(
    lead_review: LeadReviewWorld,
) -> None:
    """Both directions (SPEC §5.2's open item, settled), and only decided rows.

    A harmful comment excluded by the instructor and another kept by the lead,
    each with a reason, both in the log with their stored roles. A third harmful
    comment, in the same shown week, holds only the router's flag — no decider —
    and is not in the log.

    Each row says its own direction in `decision` (ruling on dispute E6-05-03):
    the excluded row `EXCLUDED`, the kept row `KEPT`.

    **The mutations this kill:** a log of exclusions only (the keep is missing —
    the open item left unsettled); a log over every `moderation_state` row (the
    router's flag appears, excerpt and all); `decision` written as one constant
    for every row (one of the two rows reds); `decision` swapped, or read off
    the comment's moderation verdict rather than its stored state (both
    comments are harmful, so the kept row would not read `KEPT`). **The near
    miss:** a log keyed on "has a reason" rather than "has a decider" — the
    third comment has neither, and the first test in this module has a decider
    and no reason.
    """
    review = lead_review
    excluded_reason = "E6-05 both directions: excluded by the instructor"
    kept_reason = "E6-05 both directions: kept by the Lead Faculty after review"
    excluded = a_comment(review, "E6-05 a harmful comment, instructor-excluded", verdict=HARMFUL)
    kept = a_comment(review, "E6-05 a harmful comment the lead kept", verdict=HARMFUL)
    undecided_text = "E6-05 a harmful comment nobody has decided on, holding only its flag"
    a_comment(review, undecided_text, verdict=HARMFUL)
    review.plant_decision(
        excluded,
        STORED_EXCLUDED,
        decided_by=review.door.person_id,
        decided_as=AS_INSTRUCTOR,
        reason=excluded_reason,
    )
    review.plant_decision(
        kept,
        STORED_KEPT,
        decided_by=review.lead.person_id,
        decided_as=AS_LEAD_FACULTY,
        reason=kept_reason,
    )

    answered = review.log(review.lead)
    rows = review.log_rows(review.lead)
    excluded_row = row_with_reason(rows, excluded_reason)
    kept_row = row_with_reason(rows, kept_reason)
    assert excluded_row[LOG_DECIDED_AS] == AS_INSTRUCTOR
    assert (
        kept_row[LOG_DECIDED_AS] == AS_LEAD_FACULTY
    ), "The kept row does not carry the role it was decided under."
    assert excluded_row.get(LOG_DECISION) == STORED_EXCLUDED, (
        f"The excluded row's `{LOG_DECISION}` is {excluded_row.get(LOG_DECISION)!r}; the ruling on "
        f"dispute E6-05-03 settles the stored state token, {STORED_EXCLUDED!r}."
    )
    assert kept_row.get(LOG_DECISION) == STORED_KEPT, (
        f"The kept row's `{LOG_DECISION}` is {kept_row.get(LOG_DECISION)!r}; the ruling on dispute "
        f"E6-05-03 settles the stored state token, {STORED_KEPT!r}. Without it a reader cannot "
        "tell a kept comment from a dropped one (SPEC §5.2, §11 question 5)."
    )
    assert not [value for value in strings_in(answered.json()) if undecided_text[:40] in value], (
        "The log carries a comment that holds only the router's flag. Decision 1: the log is the "
        "rows with a decider, in state EXCLUDED or KEPT."
    )


def test_a_row_whose_comment_its_instructor_cannot_see_carries_no_excerpt(
    lead_review: LeadReviewWorld,
) -> None:
    """Criterion 10's second sentence: a held comment's row has its excerpt withheld.

    A harmful comment held below the threshold, excluded by the lead; a harmful
    comment in a shown week, excluded too (the canary — its excerpt is there).

    **The mutation this kills:** the excerpt taken from the answer for every row,
    which puts held text beside a date — the week, for anyone with a calendar.
    **The near miss:** the excerpt dropped for every row, which the canary reds.
    """
    review = lead_review
    held_text = "E6-05 a held harmful comment whose text must not sit beside a date in the log"
    held_reason = "E6-05 the held comment's exclusion, by the lead"
    shown_reason = "E6-05 the shown comment's exclusion, the canary"
    shown_text = "E6-05 a shown harmful comment whose excerpt the log does carry"
    held_comment = a_comment(review, held_text, verdict=HARMFUL, held=True)
    shown_comment = a_comment(review, shown_text, verdict=HARMFUL)
    for comment, reason in ((held_comment, held_reason), (shown_comment, shown_reason)):
        review.plant_decision(
            comment,
            STORED_EXCLUDED,
            decided_by=review.lead.person_id,
            decided_as=AS_LEAD_FACULTY,
            reason=reason,
        )

    answered = review.log(review.lead)
    rows = review.log_rows(review.lead)
    assert (
        row_with_reason(rows, shown_reason)[LOG_EXCERPT] == shown_text[:EXCERPT_LENGTH]
    ), "The canary: the shown comment's row does not carry its excerpt."
    assert row_with_reason(rows, held_reason)[LOG_EXCERPT] is None, (
        "The row of a comment held below the threshold carries an excerpt. A date beside held "
        "text places it in a week, which is what the threshold withholds."
    )
    assert not [
        value for value in strings_in(answered.json()) if held_text[:40] in value
    ], "The held comment's text is somewhere in the log's body."


def test_the_log_is_newest_first(lead_review: LeadReviewWorld) -> None:
    """Decision 1: "rows newest first".

    Three decisions a day apart, written in that order. **The mutations this
    kill:** oldest first; an order by section, reason or answer id; a shuffled
    log (it is an accountability record, read in time order).
    """
    review = lead_review
    reasons: list[str] = []
    for when, label in ((EARLIER, "earlier"), (MIDDLE, "middle"), (LATER, "later")):
        comment = a_comment(review, f"E6-05 a harmful comment decided {label}", verdict=HARMFUL)
        reason = f"E6-05 the {label} decision in the order test"
        review.plant_decision(
            comment,
            STORED_EXCLUDED,
            decided_by=review.door.person_id,
            decided_as=AS_INSTRUCTOR,
            reason=reason,
            decided_at=when,
        )
        reasons.append(reason)

    order = [row.get(LOG_REASON) for row in review.log_rows(review.lead)]
    mine = [reason for reason in order if reason in reasons]
    assert mine == list(reversed(reasons)), (
        f"The log lists this test's three decisions as {mine}; newest first is "
        f"{list(reversed(reasons))}."
    )


def test_the_chairs_log_holds_the_unmapped_course_and_not_the_courses_with_a_lead(
    lead_review: LeadReviewWorld,
) -> None:
    """The log's scope is the reader's own grant: a chair's is the department's unmapped courses.

    **The mutations this kill:** a chair's log over the whole department subtree
    (the led course's row appears); a chair's log that finds nothing. The row
    the chair decides on carries `CHAIR`.
    """
    review = lead_review
    unmapped_reason = "E6-05 the unmapped course's exclusion, decided by the chair"
    led_reason = "E6-05 the led course's exclusion, which the chair does not see"
    unmapped = review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text="E6-05 a harmful comment in the course nobody leads",
        verdict=HARMFUL,
        cohort=UNMAPPED_COHORT,
    )
    led = a_comment(review, "E6-05 a harmful comment in the led course", verdict=HARMFUL)
    review.plant_decision(
        unmapped,
        STORED_EXCLUDED,
        decided_by=review.chair.person_id,
        decided_as=AS_CHAIR,
        reason=unmapped_reason,
    )
    review.plant_decision(
        led,
        STORED_EXCLUDED,
        decided_by=review.lead.person_id,
        decided_as=AS_LEAD_FACULTY,
        reason=led_reason,
    )

    chairs = review.log_rows(review.chair)
    assert row_with_reason(chairs, unmapped_reason)[LOG_DECIDED_AS] == AS_CHAIR
    assert led_reason not in [row.get(LOG_REASON) for row in chairs], (
        "The chair's log carries a row from a course that has a lead. Decision 3: a chair's grant "
        "here is the department's courses that have no lead."
    )
