"""The participation note — ticket E6-03, criterion 7, and the owner's ruling 2.

> In a held stream with one harmful comment, the week carries one note with the
> count 1 and no category or stream. In the same world with one self-harm comment
> instead, the week carries no note. Keeping the harmful comment removes it from the
> count. Above the threshold, no note is carried, and the flagged comment shows its
> chip.

Ruling 2's rule, which E6-03 writes into SPEC §5.2: at most one note per
section-week; it names no stream and no category; it counts the comments in that
week's **held** streams that carry a harmful or privacy verdict and that a decision
has not kept; it never counts a threat or self-harm comment. The work order
(decision 7) puts it on the week report as `participation_note: {"held": n} | null`,
computed at read time, and null when the count is 0.

**Every week here is read twice in a row, and both reads are asserted**
(`docs/MISTAKES.md` entry 51): the note is a surface the instructor meets every time
they open the week, and a property that holds in one payload can fail across two —
a note that came and went between reads would itself be the signal. Where a test
changes the world (a keep, an exclusion), the week is read twice before and twice
after.

**Asserted as what the payload says, never as an absence alone.** The self-harm
week's `null` sits beside another week of the same world whose harmful comment
*does* carry a note (the control that the note is computed at all), and the
no-category scan has a canary: the same scan over the above-threshold week finds
the flag class on the chip, where it belongs.

The worlds are the canonical report world (`tests/fixtures/report_api.py`), read
over HTTP as the teaching instructor, on the connection production uses. Course
weeks 3 and 4 have three and two respondents, all commenting in the instructor
stream; a comment planted in their **course** stream is that stream's only one, so
that stream is held — read back against the configured threshold before anything is
asserted.

Marked `invariant` at the module level: a confidentiality denial.

**Which failure a red is, before E6-03 lands:** a FAILED from `note_of`, naming
the `participation_note` member the payload does not carry — never an error
(`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import (
    AS_LEAD_FACULTY,
    FLAGGED,
    STORED_EXCLUDED,
    STORED_KEPT,
    DecisionDoor,
    require_decision_columns,
)
from fixtures.moderation import HARMFUL, PRIVACY, SELF_HARM, THREAT
from fixtures.report_api import (
    FIRST_HELD_WEEK,
    FLAG_FIELD,
    FULL_WEEK,
    SECOND_HELD_WEEK,
    strings_in,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

NOTE_MEMBER = "participation_note"
HELD_FIELD = "held"
# The categories a note may never name, and the Care classes it may never count —
# ADR 0030's stored tokens (`tests/fixtures/moderation.py`), compared case-blind.
CATEGORY_WORDS = (HARMFUL, PRIVACY, THREAT, SELF_HARM, "self-harm")


def note_of(body: Any) -> Any:
    """The week's `participation_note`, or a failure naming the member if the payload lacks it."""
    if NOTE_MEMBER not in body:
        pytest.fail(
            f"The week report carries no `{NOTE_MEMBER}` member; it carries {sorted(body)}. E6-03's "
            f"work order (decision 7): `{NOTE_MEMBER}: ParticipationNote | None` on the week "
            f"report, `ParticipationNote` holding one field, `{HELD_FIELD}`, at least 1."
        )
    return body[NOTE_MEMBER]


def twice(door: DecisionDoor, course_week: int) -> list[Any]:
    """Two consecutive reads of one week's report (entry 51)."""
    return [door.payload(course_week), door.payload(course_week)]


def held_comment(door: DecisionDoor, course_week: int, verdict: str, text: str) -> Any:
    """One comment, the only one in its week's course stream, holding `verdict`."""
    return door.plant_a_comment(
        course_week=course_week, stream=COURSE_STREAM, text=text, verdict=verdict
    )


def assert_held(door: DecisionDoor, course_week: int, threshold: int) -> None:
    """The premise: the week's course stream is below the threshold of distinct commenters."""
    commenters = door.door.rows.commenters_in(course_week, COURSE_STREAM)
    assert 0 < commenters < threshold, (
        f"Course week {course_week}'s course stream holds {commenters} commenters and the threshold "
        f"is {threshold}; the note is about held streams, so it has to be under it and not empty."
    )


def categories_in(body: Any) -> list[str]:
    """Every string in a payload that names a moderation category, case-blind."""
    return [
        value
        for value in strings_in(body)
        if any(word == value.strip().lower() for word in CATEGORY_WORDS)
    ]


def test_one_harmful_comment_in_a_held_stream_is_one_note_of_one_naming_nothing_else(
    decision_door: DecisionDoor, comment_contract: Any
) -> None:
    """The ruling's first case, read twice: `{"held": 1}`, and no category or stream anywhere.

    One harmful comment, the only comment in course week 3's course stream. The week
    carries exactly `{"held": 1}` — one member, so no stream and no category ride on
    the note — and no string in the whole week's payload names a category (the chip
    and the flag-type hint are hidden below the threshold, SPEC §5.2). The course
    stream's comment list stays empty: the note is not a comment, and it does not
    feed the threshold (`docs/MISTAKES.md` entry 50 — it counts comments; the
    threshold counts people).

    **The mutations this kill:** no note (`null` or absent); a note per stream, or a
    `stream` or `category` member beside `held`; a count that is not 1 (the clear
    comments of the week's held instructor stream counted, or the week's every
    comment); a `flag` left on a hidden card, or a summary held-note type, naming the
    class below the threshold; and a note that differs between two reads.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    threshold = comment_contract.threshold()
    held_comment(door, FIRST_HELD_WEEK, HARMFUL, "E6-03 the one harmful held comment")
    assert_held(door, FIRST_HELD_WEEK, threshold)

    for read, body in enumerate(twice(door, FIRST_HELD_WEEK), start=1):
        assert note_of(body) == {HELD_FIELD: 1}, (
            f"Read {read} of course week 3 carries the note {note_of(body)!r}; ruling 2 settles one "
            f"note, `{{'{HELD_FIELD}': 1}}`, naming no stream and no category."
        )
        assert strings_in(body), "The canary: the scan found no strings in the payload at all."
        named = categories_in(body)
        assert not named, (
            f"Read {read} of a week whose harmful comment is held names a category: {named}. "
            "Below the threshold there is no chip and no flag-type hint (SPEC §5.2), and the note "
            "never reveals category."
        )
        shown = body["streams"]["course"]["comments"]
        assert shown == [], f"Read {read}: the held course stream shows {shown!r}."


def test_a_self_harm_comment_in_a_held_stream_leaves_no_note_where_a_harmful_one_would(
    decision_door: DecisionDoor, comment_contract: Any
) -> None:
    """The ruling's second case: a self-harm comment is never counted — and the control beside it.

    Course week 3's course stream holds one self-harm comment; course week 4's
    holds one harmful comment. Both read twice. Week 4 carries `{"held": 1}` — so
    the note is computed in this world — and week 3 carries none at all. Then a
    threat comment is added to week 3 too; still none.

    **The mutations this kill:** the note counted from every comment v004 hides, or
    from every held comment with any verdict but `clear` (a self-harm disclosure
    surfaces as "1 response held for review" — exactly the trace SPEC §6.2 and the
    E6 exit say a Care-class comment never leaves); and a note counted from the
    moderation verdicts without the Care-class exclusion, which `threat_case` rows
    never stop.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    threshold = comment_contract.threshold()
    held_comment(door, FIRST_HELD_WEEK, SELF_HARM, "E6-03 a held self-harm disclosure")
    held_comment(door, SECOND_HELD_WEEK, HARMFUL, "E6-03 a harmful comment held elsewhere")
    assert_held(door, FIRST_HELD_WEEK, threshold)
    assert_held(door, SECOND_HELD_WEEK, threshold)

    controls = [note_of(body) for body in twice(door, SECOND_HELD_WEEK)]
    assert controls == [{HELD_FIELD: 1}, {HELD_FIELD: 1}], (
        f"Course week 4, with one harmful comment held, carries {controls} over two reads. Until "
        "this control holds, the absence below is a note that is never computed."
    )
    notes = [note_of(body) for body in twice(door, FIRST_HELD_WEEK)]
    assert notes == [None, None], (
        f"Course week 3, whose only held flag is a self-harm comment, carries {notes} over two "
        "reads. Ruling 2: the note never counts a threat or self-harm comment."
    )

    held_comment(door, FIRST_HELD_WEEK, THREAT, "E6-03 a threat in the same held stream")
    notes = [note_of(body) for body in twice(door, FIRST_HELD_WEEK)]
    assert notes == [None, None], f"With a threat comment added, course week 3 carries {notes}."


def test_keeping_a_held_harmful_comment_takes_it_out_of_the_count_and_excluding_one_does_not(
    decision_door: DecisionDoor, comment_contract: Any
) -> None:
    """The ruling's third case, and its near miss: "that a decision has not **kept**".

    Two harmful comments in course week 3's course stream: `{"held": 2}` over two
    reads. One is kept (by the Lead Faculty, the reviewer ruling 1 gives a
    below-threshold harmful comment): `{"held": 1}` over two reads. The other is
    excluded: still `{"held": 1}` over two reads — an exclusion is a decision that
    did not keep it.

    **The mutations this kill:** a count that ignores decisions (still 2 after the
    keep); a count of comments whose *latest* row is `FLAGGED_COLLAPSED` (0 after the
    exclusion — the near miss the third pair of reads exists for); and a note that
    disappears when any decision has been made in the week.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    threshold = comment_contract.threshold()
    kept = held_comment(door, FIRST_HELD_WEEK, HARMFUL, "E6-03 a held harmful comment, kept")
    excluded = held_comment(door, FIRST_HELD_WEEK, HARMFUL, "E6-03 a held harmful one, excluded")
    assert_held(door, FIRST_HELD_WEEK, threshold)

    def notes() -> list[Any]:
        return [note_of(body) for body in twice(door, FIRST_HELD_WEEK)]

    before = notes()
    assert before == [
        {HELD_FIELD: 2},
        {HELD_FIELD: 2},
    ], f"Two held harmful comments read as {before} over two reads."
    lead = door.a_person()
    door.plant_a_decision(kept, STORED_KEPT, decided_by=lead, decided_as=AS_LEAD_FACULTY)
    after_keep = notes()
    assert after_keep == [{HELD_FIELD: 1}, {HELD_FIELD: 1}], (
        f"After one of the two was kept, course week 3 carries {after_keep}. Ruling 2 counts the "
        "comments a decision has not kept."
    )
    door.plant_a_decision(excluded, STORED_EXCLUDED, decided_by=lead, decided_as=AS_LEAD_FACULTY)
    after_exclusion = notes()
    assert after_exclusion == [{HELD_FIELD: 1}, {HELD_FIELD: 1}], (
        f"After the other was excluded, course week 3 carries {after_exclusion}. An exclusion is "
        "not a keep; the excluded comment is still held."
    )


@pytest.mark.parametrize("verdict", [HARMFUL, PRIVACY])
def test_above_the_threshold_no_note_is_carried_and_the_flagged_comment_shows_its_chip(
    verdict: str, decision_door: DecisionDoor, comment_contract: Any
) -> None:
    """The ruling's fourth case: the note is for held streams only, and a shown flag is a chip.

    A flagged comment in course week 1's instructor stream, which is at the
    threshold of distinct commenters with it. Read twice: no note, and the comment's
    card is `flagged_collapsed` with `flag` equal to its verdict's class. **This is
    also the canary for the no-category scan** in the first test: here the class is
    on the page, where §5.2 puts it, and the scan finds it.

    **The mutations this kill:** a note counted over every stream, shown ones
    included (a second, redundant count of the chips on the page); a chip missing
    its class (`flag` null on a flagged card); and the class from the wrong verdict.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    threshold = comment_contract.threshold()
    comment = door.plant_a_comment(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=f"E6-03 a {verdict} comment in a shown stream",
        verdict=verdict,
    )
    commenters = door.door.rows.commenters_in(FULL_WEEK, INSTRUCTOR_STREAM)
    assert commenters >= threshold, (
        f"Course week 1's instructor stream holds {commenters} commenters against a threshold of "
        f"{threshold}; this test is about a shown stream."
    )

    for read, body in enumerate(twice(door, FULL_WEEK), start=1):
        assert note_of(body) is None, (
            f"Read {read} of a week whose only flag is on a shown stream carries the note "
            f"{note_of(body)!r}. Ruling 2: the note counts held streams."
        )
        card = door.card(body, comment)
        assert card is not None, f"Read {read}: the flagged comment is not on the shown stream."
        assert (card.get("status"), card.get(FLAG_FIELD)) == (FLAGGED, verdict), (
            f"Read {read}: the flagged comment's card is {card!r}. Above the threshold it is "
            f"`{FLAGGED}` with its chip — `flag` {verdict!r} (SPEC §5.2, work order decision 6)."
        )
        assert verdict in categories_in(
            body
        ), "The canary for the no-category scan: the shown chip's class is not found by it."
