"""The exclusion log's excerpt rule, every case of it, in one read — E6-09, done-when 3.

> In one marked test, a row from a held stream, a row from a week not yet fully
> moderated, and a row whose comment was shown only by a release batch each have
> `excerpt is None`, and their text appears nowhere in the body. A row from a shown
> week carries its excerpt (the control).

SPEC §5.2: "The excerpt is withheld when the comment's own instructor's report
does not show it under its week (a held stream, or a release batch), because a
date beside that text would place it in a week." A week not yet fully moderated
shows nothing under it either (§5.2: "a section-week's comments appear together
once every comment in it holds one"), so it is the third case of the same rule.
`test_the_exclusion_log_shows_both_directions_inside_the_readers_grant.py` covers
the held stream, unmarked; this module covers all three, marked `invariant`.

**Every row is found the way the reader finds it**: through the log route, as the
Lead Faculty member who leads the course, by the reason each decision was planted
with (`docs/MISTAKES.md` entries 35 and 53). The release batch is cut by the
product's own cutter, never planted (entry 30), and the released comment is shown to
be in the instructor's released list before its row is read.

**The not-yet-moderated case is read twice** (`docs/MISTAKES.md` entry 51): once
while its week is fully moderated and shown — its excerpt is there, which is the
control that the week would otherwise show it — and once after one comment with no
verdict is added to that week. The only difference between the two reads is the
waiting comment.

**Which failure a red is.** The rule exists in the log today, so this may be green
on arrival; it is the §4.1 assertion the boundary review found missing. The
mutations below are what show each case can go red.
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import STORED_EXCLUDED
from fixtures.lead_review import (
    AS_LEAD_FACULTY,
    EXCERPT_LENGTH,
    LOG_EXCERPT,
    LOG_REASON,
    LeadReviewWorld,
)
from fixtures.moderation import CLEAR, HARMFUL
from fixtures.report_api import (
    COMMENT_TEXT_FIELD,
    FIRST_HELD_WEEK,
    FULL_WEEK,
    HELD_COMMENTS,
    IN_DENOMINATOR_WEEK,
    RELEASED_MEMBER,
    SILENT_WEEK,
    TAUGHT_COHORT,
    strings_in,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# How much of a comment's text counts as "its text" in a body search.
FRAGMENT = 40

# Every comment here is shorter than the excerpt, so a carried excerpt is the whole text.
SHOWN_TEXT = "E6-09 a harmful comment in a shown week, whose excerpt the log carries"
HELD_TEXT = "E6-09 a harmful comment in a held course stream, never beside a date"
PENDING_TEXT = "E6-09 a harmful comment in a week one comment of which still waits"
RELEASED_TEXT = HELD_COMMENTS[FIRST_HELD_WEEK][0]

SHOWN_REASON = "E6-09 excerpt rule: the shown week's exclusion, the control"
HELD_REASON = "E6-09 excerpt rule: the held stream's exclusion"
PENDING_REASON = "E6-09 excerpt rule: the exclusion in a week not yet fully moderated"
RELEASED_REASON = "E6-09 excerpt rule: the exclusion of a comment shown only in a release batch"

# How many other commenters the not-yet-moderated week's instructor stream is given,
# so that with the decided comment it is at or above the threshold and shown.
OTHER_COMMENTERS = 5


def excluded_by_the_lead(review: LeadReviewWorld, comment: Any, reason: str) -> None:
    review.plant_decision(
        comment,
        STORED_EXCLUDED,
        decided_by=review.lead.person_id,
        decided_as=AS_LEAD_FACULTY,
        reason=reason,
    )


def row_with(rows: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    found = [row for row in rows if row.get(LOG_REASON) == reason]
    assert len(found) == 1, (
        f"The lead's log carries {len(found)} rows with the reason {reason!r}; one decision was "
        f"planted with it. The reasons it carries: {[row.get(LOG_REASON) for row in rows]}."
    )
    return found[0]


def text_in(body: Any, text: str) -> list[str]:
    return [value for value in strings_in(body) if text[:FRAGMENT] in value]


def test_the_log_withholds_the_excerpt_of_a_held_a_pending_and_a_released_comment(
    lead_review: LeadReviewWorld, comment_contract: Any
) -> None:
    """One read of the lead's log: three withheld excerpts beside one carried.

    **The mutations this kills**, one per case: the shown set built without the
    threshold (the held stream's row carries its text); built without the
    section-week rule (the pending row carries its text on the second read);
    built from the released list as well as the shown streams (the released
    comment's row carries its text — and a date beside it names the week the
    release exists to hide, ADR 0153). **The near miss:** every excerpt withheld,
    which the shown row and the pending row's first read both catch.
    """
    review = lead_review
    door = review.door

    # The release batch, cut by the product's cutter over the world's two held weeks.
    door.door.refresh()
    cut = comment_contract.cut()(door.world.session)
    door.world.session.commit()
    assert int(cut) >= 1, (
        f"The cutter cut {cut} batches over a world built to open all three legs of the release "
        "gate, so there is no released comment for this test to read."
    )
    released_list = door.payload(SILENT_WEEK).get(RELEASED_MEMBER) or []
    assert RELEASED_TEXT in {card.get(COMMENT_TEXT_FIELD) for card in released_list}, (
        f"The instructor's released list in course week {SILENT_WEEK} does not carry "
        f"{RELEASED_TEXT!r}, so it is not a comment shown only by a release batch."
    )
    excluded_by_the_lead(review, door.answer_id_of(RELEASED_TEXT), RELEASED_REASON)

    # A held stream: one commenter in course week 3's course stream, after the cut.
    held = review.plant(
        course_week=FIRST_HELD_WEEK,
        stream=COURSE_STREAM,
        text=HELD_TEXT,
        verdict=HARMFUL,
        cohort=TAUGHT_COHORT,
    )
    excluded_by_the_lead(review, held, HELD_REASON)

    # A shown week: course week 1's instructor stream, at the threshold.
    shown = review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=SHOWN_TEXT,
        verdict=HARMFUL,
        cohort=TAUGHT_COHORT,
    )
    excluded_by_the_lead(review, shown, SHOWN_REASON)

    # The week that will wait: course week 2's instructor stream, made shown first.
    for index in range(OTHER_COMMENTERS):
        review.plant(
            course_week=IN_DENOMINATOR_WEEK,
            stream=INSTRUCTOR_STREAM,
            text=f"E6-09 a clear comment of course week 2, number {index}",
            verdict=CLEAR,
            cohort=TAUGHT_COHORT,
        )
    pending = review.plant(
        course_week=IN_DENOMINATOR_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=PENDING_TEXT,
        verdict=HARMFUL,
        cohort=TAUGHT_COHORT,
    )
    excluded_by_the_lead(review, pending, PENDING_REASON)

    first = review.log_rows(review.lead)
    assert row_with(first, PENDING_REASON)[LOG_EXCERPT] == PENDING_TEXT[:EXCERPT_LENGTH], (
        "The control for the pending case: while course week 2 is fully moderated and its "
        "instructor stream is at the threshold, its excluded comment's row should carry its "
        "excerpt. Without it, the absence after the waiting comment proves nothing."
    )

    review.plant(
        course_week=IN_DENOMINATOR_WEEK,
        stream=COURSE_STREAM,
        text="E6-09 a comment of course week 2 the sweep has not reached",
        verdict=None,
        cohort=TAUGHT_COHORT,
    )

    answered = review.log(review.lead)
    assert answered.status_code == 200, f"The log answered {answered.status_code}."
    body = answered.json()
    rows = review.log_rows(review.lead)

    assert row_with(rows, SHOWN_REASON)[LOG_EXCERPT] == SHOWN_TEXT[:EXCERPT_LENGTH], (
        "The control: the row of a comment its instructor's report shows under its week does not "
        "carry its excerpt, so every absence below could be a log that carries none."
    )
    withheld = {
        "held stream": (HELD_REASON, HELD_TEXT),
        "week not yet fully moderated": (PENDING_REASON, PENDING_TEXT),
        "shown only by a release batch": (RELEASED_REASON, RELEASED_TEXT),
    }
    carried = {
        case: row_with(rows, reason)[LOG_EXCERPT]
        for case, (reason, _text) in withheld.items()
        if row_with(rows, reason)[LOG_EXCERPT] is not None
    }
    assert not carried, (
        f"These rows carry an excerpt: {carried}. SPEC §5.2: the excerpt is withheld when the "
        "comment's own instructor's report does not show it under its week, because a date "
        "beside that text would place it in a week."
    )
    leaked = {case: text_in(body, text) for case, (_reason, text) in withheld.items()}
    leaked = {case: found for case, found in leaked.items() if found}
    assert not leaked, f"The log's body carries the text of withheld comments: {leaked}."
