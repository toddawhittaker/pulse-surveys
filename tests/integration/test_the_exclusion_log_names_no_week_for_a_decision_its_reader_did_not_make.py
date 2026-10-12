"""A log row whose excerpt is withheld carries no reason and no date for anyone but its decider — E9-14 item 1.

SPEC §5.2: "The excerpt is withheld when the comment's own instructor's report
does not show it under its week (a held stream, a week not yet fully moderated,
or a release batch), because a date beside that text would place it in a week."
The E9 boundary threat review found the other half of that sentence open: the
assistant dean, the dean and the vice president read the log over their purview
(ADR 0206) and also read the section's drill-down, which shows a release batch's
comments. A withheld row still carried the decider's free-text reason and the
decision date. A reason that quotes or paraphrases the comment, beside a date,
puts the released comment back in its week, which is exactly what the release
drops (ADR 0153; ADR 0190 named the reason as an accepted residual for a lead
reading their own decisions).

**The settled interface (E9-14):** wherever a row's excerpt is withheld and the
reader is not that decision's decider, `reason` and `decided_on` are `null` in the
response. The members stay on the row. The decider still reads their own reason
and date. A row whose excerpt is shown keeps every member.

**How rows are found without their reason.** A withheld row for a non-decider
carries neither text nor reason, so it is found by what it still carries: its
section label (which names the section's code, as
`test_the_exclusion_log_shows_both_directions_inside_the_readers_grant.py`
asserts) and its null excerpt. The present twins are found by excerpt or, for
the decider, by reason.

**Which failure a red is, before E9-14 lands.** The log serves `reason` and
`decided_on` on every row, so each test FAILS on the assertion that the withheld
row's `reason` (or `decided_on`) is null. The twins are green today.
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import STORED_EXCLUDED
from fixtures.lead_review import (
    AS_CHAIR,
    AS_INSTRUCTOR,
    AS_LEAD_FACULTY,
    ASSISTANT_DEAN_ROLE,
    EXCERPT_LENGTH,
    LOG_DECIDED_ON,
    LOG_EXCERPT,
    LOG_REASON,
    LOG_SECTION_LABEL,
    UNMAPPED_COHORT,
    LeadReviewWorld,
    Reader,
)
from fixtures.moderation import HARMFUL
from fixtures.report_api import (
    COMMENT_TEXT_FIELD,
    FIRST_HELD_WEEK,
    FULL_WEEK,
    HELD_COMMENTS,
    RELEASED_MEMBER,
    SILENT_WEEK,
    TAUGHT_COHORT,
    strings_in,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

DEAN_ROLE = "DEAN"
VP_ROLE = "VP_ACADEMICS"

RELEASED_TEXT = HELD_COMMENTS[FIRST_HELD_WEEK][0]
HELD_TEXT = "E9-14 a harmful comment in a held course stream, decided on by the lead"
SHOWN_TEXT = "E9-14 a harmful comment in a shown week, whose row keeps every member"

# Each reason paraphrases its comment, which is the residual ADR 0190 named: a
# reason is free text, and beside a date it says which week the comment was in.
RELEASED_REASON = "E9-14 released: the recording cut out about twenty minutes in, said rudely"
HELD_REASON = "E9-14 held: an attack on the instructor in the course stream"
SHOWN_REASON = "E9-14 shown: the canary whose reason and date every reader keeps"


# ---------------------------------------------------------------------------
# The three wider readers, built as the wider-roles module builds them.
# ---------------------------------------------------------------------------


def an_assistant_dean_over_the_lead(review: LeadReviewWorld) -> Reader:
    """An assistant dean of the college whom the lead's assignment reports to (ADR 0199)."""
    reader = review.a_leader(
        "e9-14-assistant-dean", grants=((ASSISTANT_DEAN_ROLE, review.college),)
    )
    (dean_assignment,) = review.graph.assignments_of(reader.person_id)
    (lead_assignment,) = review.graph.assignments_of(review.lead.person_id)
    review.graph.repoint({review.graph.assignment_key: lead_assignment}, dean_assignment)
    review.rows.commit()
    return reader


def a_dean(review: LeadReviewWorld) -> Reader:
    return review.a_leader("e9-14-dean", grants=((DEAN_ROLE, review.college),))


def a_vice_president(review: LeadReviewWorld) -> Reader:
    institution = review.session.execute(
        text("SELECT institution_id FROM college WHERE id = :college"),
        {"college": review.college},
    ).scalar_one()
    return review.a_leader("e9-14-vice-president", grants=((VP_ROLE, institution),))


WIDER_READERS = {
    "assistant dean": an_assistant_dean_over_the_lead,
    "dean": a_dean,
    "vice president": a_vice_president,
}


# ---------------------------------------------------------------------------
# Planting and reading.
# ---------------------------------------------------------------------------


def excluded(
    review: LeadReviewWorld, comment: Any, *, by: Any, decided_as: str, reason: str
) -> None:
    review.plant_decision(
        comment, STORED_EXCLUDED, decided_by=by, decided_as=decided_as, reason=reason
    )


def cut_the_release(review: LeadReviewWorld, comment_contract: Any) -> Any:
    """The product's own cutter over the world's held weeks; the released comment's answer id."""
    door = review.door
    door.door.refresh()
    cut = comment_contract.cut()(door.world.session)
    door.world.session.commit()
    assert int(cut) >= 1, (
        f"The cutter cut {cut} batches over a world built to open the release gate, so there is "
        "no released comment for this test to read. A broken world, not a red."
    )
    released = door.payload(SILENT_WEEK).get(RELEASED_MEMBER) or []
    assert RELEASED_TEXT in {card.get(COMMENT_TEXT_FIELD) for card in released}, (
        f"The instructor's released list in course week {SILENT_WEEK} does not carry "
        f"{RELEASED_TEXT!r}. A broken world, not a red."
    )
    return door.answer_id_of(RELEASED_TEXT)


def the_log(review: LeadReviewWorld, reader: Reader) -> tuple[Any, list[dict[str, Any]]]:
    """The reader's whole log body and its rows, after requiring a 200."""
    answered = review.log(reader)
    assert answered.status_code == 200, (
        f"The log answered {answered.status_code} to {reader.label}. Body begins "
        f"{answered.text[:300]!r}."
    )
    return answered.json(), review.log_rows(reader)


def withheld_rows_of(
    review: LeadReviewWorld, rows: list[dict[str, Any]], cohort: str
) -> list[dict[str, Any]]:
    """The rows of the cohort's section whose excerpt is withheld."""
    code = review.code_of(cohort)
    return [
        row
        for row in rows
        if code in str(row.get(LOG_SECTION_LABEL)) and row.get(LOG_EXCERPT) is None
    ]


def row_with_excerpt(rows: list[dict[str, Any]], text_: str) -> dict[str, Any]:
    found = [row for row in rows if row.get(LOG_EXCERPT) == text_[:EXCERPT_LENGTH]]
    assert len(found) == 1, (
        f"The log carries {len(found)} rows whose excerpt is {text_[:EXCERPT_LENGTH]!r}; one was "
        f"planted. Its excerpts: {[row.get(LOG_EXCERPT) for row in rows]}."
    )
    return found[0]


def row_with_reason(rows: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    found = [row for row in rows if row.get(LOG_REASON) == reason]
    assert len(found) == 1, (
        f"The log carries {len(found)} rows with the reason {reason!r}; one decision was planted "
        f"with it. Its reasons: {[row.get(LOG_REASON) for row in rows]}."
    )
    return found[0]


def week_naming_members(row: dict[str, Any]) -> dict[str, Any]:
    """The two members that place a withheld row in a week, each required present."""
    missing = [member for member in (LOG_REASON, LOG_DECIDED_ON) if member not in row]
    assert not missing, (
        f"The log row {row!r} lacks {missing}. E9-14's settled interface keeps both members on "
        "every row and makes them null where they would name a week."
    )
    return {LOG_REASON: row[LOG_REASON], LOG_DECIDED_ON: row[LOG_DECIDED_ON]}


def plant_the_three_rows(review: LeadReviewWorld, comment_contract: Any) -> None:
    """The released, the held and the shown comment, each excluded by the lead with a reason."""
    released = cut_the_release(review, comment_contract)
    excluded(
        review,
        released,
        by=review.lead.person_id,
        decided_as=AS_LEAD_FACULTY,
        reason=RELEASED_REASON,
    )
    held = review.plant(
        course_week=FIRST_HELD_WEEK,
        stream=COURSE_STREAM,
        text=HELD_TEXT,
        verdict=HARMFUL,
        cohort=TAUGHT_COHORT,
    )
    excluded(review, held, by=review.lead.person_id, decided_as=AS_LEAD_FACULTY, reason=HELD_REASON)
    shown = review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=SHOWN_TEXT,
        verdict=HARMFUL,
        cohort=TAUGHT_COHORT,
    )
    excluded(
        review, shown, by=review.lead.person_id, decided_as=AS_LEAD_FACULTY, reason=SHOWN_REASON
    )


# ---------------------------------------------------------------------------
# The wider readers: the log beside the drill-down's release.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", sorted(WIDER_READERS))
def test_a_wider_reader_cannot_match_a_withheld_log_row_to_the_week_of_a_comment_the_drill_down_releases(
    lead_review: LeadReviewWorld, comment_contract: Any, role: str
) -> None:
    """The finding, end to end: the drill-down shows the released text; the log names no week for it.

    The reader opens the taught section's drill-down at its latest week and is
    shown the released comment (the premise: this reader can read the text a
    dated reason would place). The same reader's log then carries a row for each
    withheld decision of that section, and on each one `reason` and `decided_on`
    are null; the reasons appear nowhere in the body.

    **The mutation it kills:** the log serving the stored reason and date on a
    withheld row to a reader who did not decide (today's log); nulling only the
    excerpt; nulling the reason and keeping the date, or the reverse — either
    alone still dates a paraphrase or names the week a released comment's
    decision was made in. **The near miss it spares:** the shown row, which keeps
    its reason and date for the same reader (asserted below), and the decider's
    own read (the next test).
    """
    review = lead_review
    reader = WIDER_READERS[role](review)
    plant_the_three_rows(review, comment_contract)

    taught = review.world.section_id(TAUGHT_COHORT)
    drill_down = review.ask(
        "GET", f"/leadership/sections/{taught}/weeks/{SILENT_WEEK}/report", token=reader.token
    )
    assert drill_down.status_code == 200, (
        f"The {role}'s drill-down into the taught section answered {drill_down.status_code}; the "
        "premise is that this reader reads the section's release. A broken world, not a red."
    )
    shown_released = {
        card.get(COMMENT_TEXT_FIELD) for card in drill_down.json().get(RELEASED_MEMBER) or []
    }
    assert RELEASED_TEXT in shown_released, (
        f"The {role}'s drill-down at course week {SILENT_WEEK} does not show the released comment, "
        "so this reader has no text a dated reason could place. A broken world, not a red."
    )

    body, rows = the_log(review, reader)
    shown = row_with_excerpt(rows, SHOWN_TEXT)
    withheld = withheld_rows_of(review, rows, TAUGHT_COHORT)

    assert (shown[LOG_REASON], shown[LOG_DECIDED_ON] is not None) == (SHOWN_REASON, True), (
        f"The present twin failed: the shown row reads {shown!r} for the {role}. A row whose "
        "excerpt is shown keeps its reason and its date."
    )
    assert len(withheld) == 2, (
        f"The {role}'s log carries {len(withheld)} withheld rows of the taught section; two "
        f"decisions were planted there whose excerpt is withheld (released and held). Rows: {rows}."
    )
    named = [week_naming_members(row) for row in withheld]
    assert named == [{LOG_REASON: None, LOG_DECIDED_ON: None}] * 2, (
        f"The {role} did not decide these, and their excerpts are withheld, yet the rows carry "
        f"{named}. SPEC §5.2: a date beside that text would place it in a week; a reason beside a "
        "date does the same, and this reader reads the released text in the drill-down."
    )
    leaked = [
        reason
        for reason in (RELEASED_REASON, HELD_REASON)
        if any(reason in value for value in strings_in(body))
    ]
    assert not leaked, f"The {role}'s log body carries the withheld rows' reasons: {leaked}."


def test_the_decider_still_reads_their_own_reason_and_date_on_a_withheld_row(
    lead_review: LeadReviewWorld, comment_contract: Any
) -> None:
    """The present twin for the rule above: the lead who made the decisions reads both members.

    **The mutation it kills:** the reason and date nulled for every reader of a
    withheld row, the decider included, which takes the accountability record
    away from the person whose decision it is. **The near miss:** the excerpt,
    which stays withheld for the decider too.
    """
    review = lead_review
    plant_the_three_rows(review, comment_contract)

    _body, rows = the_log(review, review.lead)
    for reason in (RELEASED_REASON, HELD_REASON):
        row = row_with_reason(rows, reason)
        assert row[LOG_EXCERPT] is None, (
            f"The decider's row {reason!r} carries an excerpt; withholding the excerpt does not "
            "depend on who reads."
        )
        assert row[LOG_DECIDED_ON] is not None, (
            f"The decider's own row {reason!r} carries no date: {row!r}. The decider reads their "
            "own decision whole, apart from the excerpt."
        )


# ---------------------------------------------------------------------------
# A lead or a chair reading a row somebody else decided.
# ---------------------------------------------------------------------------


def test_a_lead_reading_a_withheld_row_the_instructor_decided_sees_no_reason_or_date(
    lead_review: LeadReviewWorld, comment_contract: Any
) -> None:
    """The instructor excludes the released comment (it is in her release batch); the lead reads none of it.

    **The present twin:** the instructor's exclusion of a shown comment, in the
    same lead's same log read, keeps its reason and its date.

    **The mutation it kills:** the rule written for the wider roles only (by
    role rather than by decider), so a lead still reads an instructor's dated
    reason for a released comment. **The near miss it spares:** the shown row.
    """
    review = lead_review
    released = cut_the_release(review, comment_contract)
    excluded(
        review,
        released,
        by=review.door.person_id,
        decided_as=AS_INSTRUCTOR,
        reason=RELEASED_REASON,
    )
    shown = review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=SHOWN_TEXT,
        verdict=HARMFUL,
        cohort=TAUGHT_COHORT,
    )
    excluded(review, shown, by=review.door.person_id, decided_as=AS_INSTRUCTOR, reason=SHOWN_REASON)

    body, rows = the_log(review, review.lead)
    twin = row_with_excerpt(rows, SHOWN_TEXT)
    assert (twin[LOG_REASON], twin[LOG_DECIDED_ON] is not None) == (
        SHOWN_REASON,
        True,
    ), f"The present twin failed: the instructor's shown row reads {twin!r} for the lead."
    withheld = withheld_rows_of(review, rows, TAUGHT_COHORT)
    assert len(withheld) == 1, (
        f"The lead's log carries {len(withheld)} withheld rows of the taught section; the "
        f"instructor's exclusion of the released comment is one. Rows: {rows}."
    )
    assert week_naming_members(withheld[0]) == {LOG_REASON: None, LOG_DECIDED_ON: None}, (
        f"The lead did not decide the released comment's exclusion and reads {withheld[0]!r}. The "
        "rule is about the decider, not the role: a lead reading another person's withheld row "
        "gets no reason and no date."
    )
    assert not [
        value for value in strings_in(body) if RELEASED_REASON in value
    ], "The instructor's reason for excluding the released comment is in the lead's log body."


def test_a_chair_reading_a_withheld_row_another_person_decided_sees_no_reason_or_date(
    lead_review: LeadReviewWorld,
) -> None:
    """The unled course's held stream: the instructor's row is blank to the chair, the chair's own row is not.

    Two held comments in the cohort-`4` section (one commenter each in course
    week 1's instructor stream, below the threshold): one excluded by somebody
    teaching there, one by the chair.

    **The mutation it kills:** the rule applied on the lead's path only (the
    chair's grant is another currency, `docs/MISTAKES.md` entry 53). **The near
    miss it spares:** the chair's own decision in the same section and stream,
    whose reason and date the chair still reads.
    """
    review = lead_review
    other_reason = "E9-14 unled: the instructor's exclusion the chair did not make"
    own_reason = "E9-14 unled: the chair's own exclusion"
    for text_, by, decided_as, reason in (
        ("E9-14 unled held comment one", review.door.a_person(), AS_INSTRUCTOR, other_reason),
        ("E9-14 unled held comment two", review.chair.person_id, AS_CHAIR, own_reason),
    ):
        comment = review.plant(
            course_week=FULL_WEEK,
            stream=INSTRUCTOR_STREAM,
            text=text_,
            verdict=HARMFUL,
            cohort=UNMAPPED_COHORT,
        )
        excluded(review, comment, by=by, decided_as=decided_as, reason=reason)

    body, rows = the_log(review, review.chair)
    own = row_with_reason(rows, own_reason)
    assert own[LOG_EXCERPT] is None and own[LOG_DECIDED_ON] is not None, (
        f"The present twin: the chair's own held row reads {own!r}; it should carry no excerpt "
        "(the stream is held) and its date (the chair decided it)."
    )
    others = [row for row in withheld_rows_of(review, rows, UNMAPPED_COHORT) if row is not own]
    assert len(others) == 1, (
        f"The chair's log carries {len(others)} withheld rows of the unled section besides their "
        f"own; the instructor's exclusion is one. Rows: {rows}."
    )
    assert week_naming_members(others[0]) == {
        LOG_REASON: None,
        LOG_DECIDED_ON: None,
    }, f"The chair did not decide this held comment's exclusion and reads {others[0]!r}."
    assert not [
        value for value in strings_in(body) if other_reason in value
    ], "The instructor's reason for a held comment is in the chair's log body."
