"""The Lead Faculty review queue — ticket E6-05, criteria 1 and 2, and work order decision 1.

> 1. A Lead Faculty member sees a harmful, undecided comment from a course they
>    lead, in a week below the threshold, with its text and section and no week,
>    time or count. A privacy comment, a decided comment and a clear comment in
>    the same course are not in the queue.
> 2. A comment in a course with no lead is in its department chair's queue and
>    in no Lead Faculty member's.

Every read is over HTTP against the built application, which connects as
`pulse_app` — the connection production uses (`docs/MISTAKES.md` entry 46). The
world is `tests/fixtures/lead_review.py`'s: the report world's own course led by
`lead`, a sibling course led by `sibling_lead`, and an unmapped course that falls
to `chair`, all three in one department.

**The absent comments are asserted beside a present one in the same read**, so a
queue that answered nothing at all is red on the canary rather than green on the
absences (`docs/MISTAKES.md` entry 3).

**Which failure a red is, before E6-05 lands.** `lead_routes` fails inside the
test body naming the three routes the work order owes — a FAILED, never an ERROR
(`docs/MISTAKES.md` entry 44). The world itself is built from existing machinery.
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import STORED_EXCLUDED
from fixtures.lead_review import (
    AS_INSTRUCTOR,
    ITEM_ANSWER_ID,
    ITEM_SECTION_LABEL,
    ITEM_TEXT,
    QUEUE_ITEM_FIELDS,
    SIBLING_COHORT,
    UNMAPPED_COHORT,
    LeadReviewWorld,
)
from fixtures.moderation import CLEAR, HARMFUL, PRIVACY
from fixtures.report_api import FIRST_HELD_WEEK, FULL_WEEK, TAUGHT_COHORT, UNTAUGHT_COHORT
from fixtures.report_comments import configured_threshold
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = pytest.mark.integration

# How many reads the order test makes. With three queued items there are six
# orders; a uniform shuffle shows the same one on all twenty reads with
# probability (1/6)^19, which is below one in 10^14.
ORDER_READS = 20


def held_harmful(review: LeadReviewWorld, text: str, *, cohort: str = TAUGHT_COHORT) -> Any:
    """A harmful comment in course week 3's course stream, which is below the threshold."""
    answer_id = review.plant(
        course_week=FIRST_HELD_WEEK, stream=COURSE_STREAM, text=text, verdict=HARMFUL, cohort=cohort
    )
    if cohort == TAUGHT_COHORT:
        commenters = review.door.door.rows.commenters_in(FIRST_HELD_WEEK, COURSE_STREAM)
        assert 0 < commenters < configured_threshold(), (
            f"Course week {FIRST_HELD_WEEK}'s course stream holds {commenters} commenters against a "
            f"threshold of {configured_threshold()}; criterion 1 is about a week below it."
        )
    return answer_id


def item_for(items: list[dict[str, Any]], answer_id: Any) -> dict[str, Any] | None:
    found = [item for item in items if str(item.get(ITEM_ANSWER_ID)) == str(answer_id)]
    assert len(found) <= 1, f"The queue carries {len(found)} items for one comment."
    return found[0] if found else None


def test_a_lead_sees_a_held_harmful_comment_of_their_course_with_its_text_and_section(
    lead_review: LeadReviewWorld,
) -> None:
    """Criterion 1, the shown half: the item carries the text and the section, and nothing else.

    **The mutations this kills:** a queue keyed on the instructor's visibility
    (the comment is in a held stream, so a queue reading `visible_comments` shows
    nothing); an item carrying a week, a date, an arrival time or a count beside
    the three settled fields (the key set is asserted exactly); a section label
    naming the wrong section (it must carry this section's own code, `F1WW`, and
    the untaught section's `Q1WW` is in the same course). **The near miss:** an
    item whose `text` is an excerpt rather than the comment — the full text is
    asserted.
    """
    review = lead_review
    text = (
        "E6-05 held harmful: the instructor was openly contemptuous in the forum thread and it "
        "made several of us stop posting"
    )
    comment = held_harmful(review, text)

    items = review.items(review.lead)
    item = item_for(items, comment)
    assert item is not None, (
        f"The lead's queue carries {len(items)} items and not the harmful, undecided comment from "
        "a held week of the course they lead. SPEC §5.2 routes it to the course's Lead Faculty "
        "review queue, and ruling 1 shows its text at any threshold."
    )
    assert set(item) == QUEUE_ITEM_FIELDS, (
        f"The queue item carries {sorted(item)}; work order decision 1 settles exactly "
        f"{sorted(QUEUE_ITEM_FIELDS)} — no week, no time, no date and no count."
    )
    assert item[ITEM_TEXT] == text, f"The item's text is {item[ITEM_TEXT]!r}, not the comment."
    label = item[ITEM_SECTION_LABEL]
    own_code = review.code_of(TAUGHT_COHORT)
    assert isinstance(label, str) and own_code in label and label != own_code, (
        f"The item's section label is {label!r}. Decision 1 makes it the course label and the "
        f"section's code ({own_code!r}) through `section_codes.course_label`."
    )
    for other in (UNTAUGHT_COHORT, SIBLING_COHORT, UNMAPPED_COHORT):
        other_code = review.code_of(other)
        assert (
            other_code not in label
        ), f"The section label {label!r} names {other_code!r}, a section the comment is not in."


@pytest.mark.parametrize("which", ["privacy", "decided", "clear"])
def test_a_privacy_a_decided_and_a_clear_comment_are_not_in_the_queue(
    which: str, lead_review: LeadReviewWorld
) -> None:
    """Criterion 1, the withheld half, each with a queued harmful comment in the same read.

    "Only harmful goes to the queue; privacy stays with the instructor", and the
    queue "holds only undecided flags" (decision 1). Each case plants its comment
    and a held harmful one in the same course; the read must carry the harmful one
    (the canary) and not the case's.

    **The mutations this kill:** a queue over every `FLAGGED_COLLAPSED` row
    (privacy flags too); a queue over every harmful verdict whatever its latest
    state (the instructor's exclusion is ignored); a queue over every comment in
    the course. **The near miss:** a decided comment read off its *first* row,
    which is still the router's flag.
    """
    review = lead_review
    canary = held_harmful(review, f"E6-05 the queued canary beside a {which} comment, held")
    if which == "privacy":
        comment = review.plant(
            course_week=FIRST_HELD_WEEK,
            stream=INSTRUCTOR_STREAM,
            text="E6-05 a privacy comment naming a classmate's diagnosis, held below the threshold",
            verdict=PRIVACY,
            cohort=TAUGHT_COHORT,
        )
    elif which == "decided":
        comment = review.plant(
            course_week=FULL_WEEK,
            stream=INSTRUCTOR_STREAM,
            text="E6-05 a harmful comment the instructor has already excluded from the shown week",
            verdict=HARMFUL,
            cohort=TAUGHT_COHORT,
        )
        review.plant_decision(
            comment,
            STORED_EXCLUDED,
            decided_by=review.door.person_id,
            decided_as=AS_INSTRUCTOR,
        )
    else:
        comment = review.plant(
            course_week=FIRST_HELD_WEEK,
            stream=INSTRUCTOR_STREAM,
            text="E6-05 a clear comment about the reading list arriving late, held",
            verdict=CLEAR,
            cohort=TAUGHT_COHORT,
        )

    queued = review.queued_ids(review.lead)
    assert str(canary) in queued, (
        f"The lead's queue does not carry the held harmful comment planted beside the {which} one, "
        "so the absence asserted next would be about an empty queue (`docs/MISTAKES.md` entry 3)."
    )
    assert str(comment) not in queued, (
        f"The lead's queue carries the {which} comment. Decision 1: the queue holds harmful "
        "comments that are still flagged-collapsed, and nothing else."
    )


def test_a_comment_in_an_unmapped_course_is_in_the_chairs_queue_and_no_leads(
    lead_review: LeadReviewWorld,
) -> None:
    """Criterion 2: the unmapped course falls to the chair, and to no lead.

    One held harmful comment in each of the three courses. The chair's queue
    carries the unmapped course's and neither of the mapped courses'; neither
    lead's queue carries the unmapped course's, and each carries its own (the
    canaries).

    **The mutations this kill:** a chair grant read as the whole department
    subtree (the chair's queue carries both mapped courses' comments — work order
    decision 3 gives a chair "the department's courses that have no lead"); a
    chair grant that finds nothing (the chair's queue misses the unmapped
    comment); and a lead grant widened to unmapped courses near theirs. **The near
    miss, one level out (entry 53):** a chair whose department holds one mapped
    and one unmapped course, which is this world exactly.
    """
    review = lead_review
    own = held_harmful(review, "E6-05 a held harmful comment in the course the lead leads")
    sibling = held_harmful(
        review, "E6-05 a held harmful comment in the sibling lead's course", cohort=SIBLING_COHORT
    )
    unmapped = held_harmful(
        review, "E6-05 a held harmful comment in the course nobody leads", cohort=UNMAPPED_COHORT
    )

    chairs = review.queued_ids(review.chair)
    leads = review.queued_ids(review.lead)
    siblings = review.queued_ids(review.sibling_lead)

    assert str(unmapped) in chairs, (
        "The chair's queue does not carry the harmful comment from the unmapped course in their "
        "department. SPEC §2.1: a course with no mapping falls to its department chair."
    )
    assert str(own) in leads and str(sibling) in siblings, (
        "A lead's queue does not carry the harmful comment from the course they lead, so the "
        "absences asserted next would be about leads whose grants find nothing (entry 35)."
    )
    assert not {str(own), str(sibling)} & chairs, (
        "The chair's queue carries a comment from a course that has a lead. Decision 3: a chair's "
        "grant here is the department's courses that have no lead."
    )
    assert (
        str(unmapped) not in leads | siblings
    ), "A Lead Faculty member's queue carries the comment from the course nobody leads."


def test_the_queue_order_is_drawn_again_on_every_read(lead_review: LeadReviewWorld) -> None:
    """Decision 1 and SPEC §4: "shuffled per request" — the order varies across reads.

    Three queued comments, read twenty times; at least two different orders must
    appear, and every read carries the same three (entry 51: the property is
    asserted over the sequence of reads, not one).

    **The mutations this kill:** an order by answer id, by arrival or by text (one
    order on every read — and an arrival order is the queue telling a reader who
    looks every hour when each comment came); a shuffle seeded once per process
    or per reader. **The near miss:** a shuffle seeded per day, which is the same
    order on every read here.
    """
    review = lead_review
    planted = {
        str(held_harmful(review, f"E6-05 a held harmful comment for the order test, number {n}"))
        for n in range(3)
    }
    orders = []
    for read in range(ORDER_READS):
        ids = [str(item.get(ITEM_ANSWER_ID)) for item in review.items(review.lead)]
        assert (
            set(ids) == planted
        ), f"Read {read + 1} of the queue carries {ids}, not the three planted comments {planted}."
        orders.append(tuple(ids))
    assert len(set(orders)) > 1, (
        f"Twenty reads of a three-item queue all came back in the order {orders[0]}. Decision 1 "
        "shuffles the queue per request (SPEC §4: comment display order is randomized)."
    )
