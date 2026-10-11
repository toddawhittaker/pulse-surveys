"""The instructor excludes, keeps and undoes — ticket E6-03, criterion 1 and decision 3.

> An instructor excludes a flagged comment, keeps it, and undoes each. After each
> undo the comment reports the state it held before. Each step is one appended row
> naming the instructor and their role.

SPEC §5.2's lifecycle, driven over HTTP against the built application, through the
route E6-03's work order settles (`POST …/comments/{answer_id}/decisions`, body
`{"action", "reason"}`), as the teaching instructor of the canonical report world
(`tests/fixtures/report_api.py`). Every comment decided on here sits in course week
1's instructor stream, which is at the n-threshold, so the instructor's report
returns it and the door has no visibility reason to refuse.

**Every step is asserted three ways**: the answer (200 and the comment's new
`CommentView`), the record (exactly one new `moderation_state` row, naming the
door's `person` and the role `INSTRUCTOR`, read on the bootstrap connection in
`sequence` order), and the report (what a fresh read of the week says the comment's
status is). A route that answered 200 and wrote nothing, or wrote a row the read
path does not follow, fails a different one of the three.

**Decision 3's transition table** is asserted in both directions: the edges it
allows, and the 409s for everything else, each with a permitted action on the same
comment as its control, so a door that refuses everything is red.

**Undo has one rule (the coordinator's ruling on the open question, 2026-10-10).**
`undo` looks at the comment's **latest row only**. It succeeds only if that row is a
non-undo decision written by this same person under `INSTRUCTOR`, and then appends
a row holding the state from before that decision, `is_undo = true`, with the same
decider and role. Anything else is 409 and writes nothing — so an undo of an undo
is 409, a second undo in a row is 409, and an undo after somebody else's later
decision is 409.

**Which failure a red is, before E6-03 lands.** `decision_route` fails inside the
test body naming the route the work order owes — a FAILED, never an ERROR
(`docs/MISTAKES.md` entry 44). The world and the launch are E4-07's and build on
this tree.
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import (
    AS_INSTRUCTOR,
    AS_LEAD_FACULTY,
    CONFLICT,
    DECIDED_AS_COLUMN,
    DECIDER_COLUMN,
    EXCLUDE,
    EXCLUDED,
    FLAGGED,
    IS_UNDO_COLUMN,
    KEEP,
    KEPT,
    OK,
    PUBLISHED,
    STATE_COLUMN,
    STORED_EXCLUDED,
    STORED_FLAGGED,
    STORED_KEPT,
    STORED_PUBLISHED,
    UNDO,
    DecisionDoor,
    governed_sentence_of,
    latest,
    require_decision_columns,
)
from fixtures.moderation import CLEAR, HARMFUL
from fixtures.report_api import ANSWER_ID_FIELD, DECIDED_BY_YOU_FIELD, FULL_WEEK
from fixtures.report_views import INSTRUCTOR_STREAM

pytestmark = pytest.mark.integration

A_STATED_REASON = "It names a classmate's medical condition, which they did not choose to share."


def a_flagged_comment(door: DecisionDoor, text: str) -> Any:
    """A `harmful` comment in the shown stream: the definer flags it, and the report returns it."""
    return door.plant_a_comment(
        course_week=FULL_WEEK, stream=INSTRUCTOR_STREAM, text=text, verdict=HARMFUL
    )


def a_published_comment(door: DecisionDoor, text: str) -> Any:
    """A `clear` comment in the shown stream: no row at all, so it is published."""
    return door.plant_a_comment(
        course_week=FULL_WEEK, stream=INSTRUCTOR_STREAM, text=text, verdict=CLEAR
    )


def status_in_report(door: DecisionDoor, answer_id: Any) -> Any:
    """The status a fresh read of course week 1 gives the comment, or a failure if it is absent."""
    card = door.card(door.payload(FULL_WEEK), answer_id)
    assert card is not None, (
        f"Course week 1's report carries no card with `{ANSWER_ID_FIELD}` {answer_id}, so the "
        "status a decision left cannot be read where the instructor reads it."
    )
    return card["status"]


def step(
    door: DecisionDoor,
    answer_id: Any,
    action: str,
    *,
    reason: Any = None,
    stored: str,
    reported: str,
    undo: bool,
) -> None:
    """One decision, and the three things it must leave: the answer, one row, and the report."""
    before = door.rows(answer_id)
    answered = door.decide(answer_id, action, reason)
    assert answered.status_code == OK, (
        f"`{action}` on a comment the instructor's report returns was answered "
        f"{answered.status_code}; body begins {answered.text[:400]!r}."
    )
    view = answered.json()
    assert str(view.get(ANSWER_ID_FIELD)) == str(answer_id) and view.get("status") == reported, (
        f"`{action}` answered {view!r}; the work order settles 200 with the comment's new "
        f"`CommentView`, which here reports {reported!r} for answer {answer_id}."
    )
    assert view.get(DECIDED_BY_YOU_FIELD) is True, (
        f"`{action}` answered `{DECIDED_BY_YOU_FIELD}` {view.get(DECIDED_BY_YOU_FIELD)!r} for the "
        "decision the reader just made."
    )

    after = door.rows(answer_id)
    assert len(after) == len(before) + 1, (
        f"`{action}` left {len(after)} `moderation_state` rows where there were {len(before)}. "
        "Each step is one appended row (criterion 1, ADR 0145: append-only, latest governs) — an "
        "undo that deleted the row it undoes leaves one fewer, and a step that wrote nothing leaves "
        "the same number."
    )
    assert (
        after[: len(before)] == before
    ), "The rows that were there before the decision changed under it; the record is append-only."
    row = latest(after)
    assert (
        row[STATE_COLUMN],
        str(row[DECIDER_COLUMN]),
        row[DECIDED_AS_COLUMN],
        row[IS_UNDO_COLUMN],
    ) == (stored, str(door.person_id), AS_INSTRUCTOR, undo), (
        f"`{action}` appended {row!r}. Criterion 1: the row names the instructor (`person` "
        f"{door.person_id}) and the role the decision was made under ({AS_INSTRUCTOR!r}), holds "
        f"{stored!r}, and is marked as an undo exactly when it is one (work order decision 3)."
    )
    assert (
        status_in_report(door, answer_id) == reported
    ), f"After `{action}`, the report gives the comment a status other than {reported!r}."


def test_an_excluded_flagged_comment_is_flagged_again_after_undo(
    decision_door: DecisionDoor,
) -> None:
    """Exclude, then undo: the comment reports `flagged_collapsed` again, by an appended row.

    **The mutations this kills:** a decision that writes no row (the record is
    unchanged); a row with no decider, or one naming a role read off today's
    assignments rather than the one the decision was made under; an undo that
    deletes the exclusion row (one row fewer — the trail §5.2's log is built on is
    gone); and an undo that is not marked `is_undo`.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = a_flagged_comment(door, "E6-03 a flagged comment the instructor excludes and undoes")
    assert [row[STATE_COLUMN] for row in door.rows(comment)] == [STORED_FLAGGED], (
        "The harmful verdict did not leave exactly the definer's one flag row, so this test does "
        "not start where it says it does."
    )

    step(door, comment, EXCLUDE, stored=STORED_EXCLUDED, reported=EXCLUDED, undo=False)
    step(door, comment, UNDO, stored=STORED_FLAGGED, reported=FLAGGED, undo=True)


def test_a_kept_flagged_comment_is_flagged_again_after_undo(decision_door: DecisionDoor) -> None:
    """Keep, then undo: SPEC §5.2's "Undo returns it to review".

    **The mutations this kills:** `keep` written as `PUBLISHED` rather than `KEPT`
    (the report says `published` and §5.2's quiet logged-decision line has nothing
    to read); and the undo of a keep writing anything but the state before it.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = a_flagged_comment(door, "E6-03 a flagged comment the instructor keeps and undoes")

    step(door, comment, KEEP, stored=STORED_KEPT, reported=KEPT, undo=False)
    step(door, comment, UNDO, stored=STORED_FLAGGED, reported=FLAGGED, undo=True)


def test_undoing_the_exclusion_of_a_published_comment_publishes_it_again(
    decision_door: DecisionDoor,
) -> None:
    """The state *before* the decision, not the flag: an unflagged exclusion undone is published.

    The comment holds a `clear` verdict and no row, so it is published; it is
    excluded with a stated reason, then the exclusion is undone.

    **The mutation this kills — the near miss of the two tests above:** an undo
    that always writes `FLAGGED_COLLAPSED`, which passes both of them, and here
    turns a published comment the instructor excluded by mistake into a flagged one
    that students can no longer see.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = a_published_comment(door, "E6-03 a published comment excluded then restored")
    assert door.rows(comment) == [], "A `clear` comment carries a moderation row already."

    step(
        door,
        comment,
        EXCLUDE,
        reason=A_STATED_REASON,
        stored=STORED_EXCLUDED,
        reported=EXCLUDED,
        undo=False,
    )
    step(door, comment, UNDO, stored=STORED_PUBLISHED, reported=PUBLISHED, undo=True)


def test_exclude_from_kept_and_keep_from_excluded_are_allowed(decision_door: DecisionDoor) -> None:
    """Decision 3's other two edges: `exclude` from `KEPT`, and `keep` from `EXCLUDED`.

    **The mutations this kill:** a transition table that allows `exclude` only from
    `FLAGGED_COLLAPSED` and `PUBLISHED` (an instructor who kept a comment can never
    change their mind), or `keep` only from `FLAGGED_COLLAPSED`.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = a_flagged_comment(door, "E6-03 a flagged comment decided three times over")

    step(door, comment, KEEP, stored=STORED_KEPT, reported=KEPT, undo=False)
    step(door, comment, EXCLUDE, stored=STORED_EXCLUDED, reported=EXCLUDED, undo=False)
    step(door, comment, KEEP, stored=STORED_KEPT, reported=KEPT, undo=False)


# Each case: how the comment starts, what is done to it first, the refused action,
# and a permitted action on the same comment afterwards (the control).
REFUSED_TRANSITIONS = {
    "keep-a-published-comment": ("published", (), KEEP, (EXCLUDE, A_STATED_REASON)),
    "exclude-an-excluded-comment": ("flagged", ((EXCLUDE, None),), EXCLUDE, (KEEP, None)),
    "keep-a-kept-comment": ("flagged", ((KEEP, None),), KEEP, (EXCLUDE, None)),
    "undo-with-nothing-decided": ("flagged", (), UNDO, (KEEP, None)),
}


@pytest.mark.parametrize("case", sorted(REFUSED_TRANSITIONS))
def test_an_action_the_comments_state_does_not_allow_is_refused_409_and_writes_nothing(
    case: str, decision_door: DecisionDoor
) -> None:
    """Work order decision 3's refusals: 409, a governed sentence, and no row.

    `keep` is allowed only from `FLAGGED_COLLAPSED` and `EXCLUDED`; asking for the
    state the comment already holds is 409; an undo with no decision of this
    person's to undo is 409 (the router's flag is not a decision anybody made).

    **The control in every case** is a permitted action on the same comment,
    straight after: a door that answered 409 to everything passes the refusal half
    and fails here.

    **The mutations this kills:** no transition check (each refused action is
    answered 200 and a row is written); a duplicate row for a state already held (the
    exclusion log shows two exclusions of one comment); an undo that "undoes" the
    router's flag by publishing the comment; and a refusal answered with an inline
    sentence or a framework message rather than one in
    `app.copy.instructor_report`.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    starts, first, refused, control = REFUSED_TRANSITIONS[case]
    text = f"E6-03 a comment for the refused transition {case}"
    plant = a_flagged_comment if starts == "flagged" else a_published_comment
    comment = plant(door, text)
    for action, reason in first:
        assert (
            door.decide(comment, action, reason).status_code == OK
        ), f"The setup step `{action}` was refused, so the case is not the one it names."

    before = door.rows(comment)
    answered = door.decide(comment, refused, None)
    assert answered.status_code == CONFLICT, (
        f"{case}: `{refused}` was answered {answered.status_code}, not {CONFLICT}. Body begins "
        f"{answered.text[:400]!r}."
    )
    governed_sentence_of(answered, f"The 409 for {case}")
    assert door.rows(comment) == before, f"{case}: a refused `{refused}` wrote a row."

    action, reason = control
    allowed = door.decide(comment, action, reason)
    assert allowed.status_code == OK, (
        f"{case}: the permitted `{action}` on the same comment was answered "
        f"{allowed.status_code}, so the 409 above may be a door that refuses everything."
    )


def test_undo_refuses_a_decision_another_person_made(decision_door: DecisionDoor) -> None:
    """Decision 3: undo reverses only the reader's own decision, under the instructor role.

    A flagged comment is kept by somebody else (a row planted with another `person`
    and the role `INSTRUCTOR` — a co-instructor). The door's undo is refused 409 and
    writes nothing. **The control**, on the same comment: the door then excludes it
    (allowed from `KEPT`) and undoes *that* — which must restore `KEPT`, the state
    before their decision, not the flag.

    **The mutations this kills:** an undo that reverses whatever the latest row is,
    whoever made it (an instructor silently reversing a colleague's or the Lead
    Faculty's decision, with nothing in the log saying whose); and an undo that
    always returns the comment to review.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = a_flagged_comment(door, "E6-03 a flagged comment a co-instructor kept")
    door.plant_a_decision(
        comment, STORED_KEPT, decided_by=door.a_person(), decided_as=AS_INSTRUCTOR
    )

    before = door.rows(comment)
    answered = door.decide(comment, UNDO)
    assert (
        answered.status_code == CONFLICT
    ), f"Undo of another person's keep was answered {answered.status_code}, not {CONFLICT}."
    governed_sentence_of(answered, "The 409 for undoing another person's decision")
    assert door.rows(comment) == before, "A refused undo wrote a row."

    step(door, comment, EXCLUDE, stored=STORED_EXCLUDED, reported=EXCLUDED, undo=False)
    step(door, comment, UNDO, stored=STORED_KEPT, reported=KEPT, undo=True)


def test_undo_refuses_this_persons_decision_made_under_another_role(
    decision_door: DecisionDoor,
) -> None:
    """Decision 3: "written by this same person **under the instructor role**".

    Two flagged comments. On the first, a row naming the door's own `person` under
    `LEAD_FACULTY` — the same human, deciding through E6-05's door. On the second,
    the same row under `INSTRUCTOR`. Undo of the first is refused 409; undo of the
    second is accepted and restores the flag.

    **The mutation this kills:** an undo that checks the person and not the role,
    which lets the instructor door reverse a decision its owner made with the Lead
    Faculty's authority. The second comment is the near miss that keeps the check
    from being "refuse every planted row".
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    as_lead = a_flagged_comment(door, "E6-03 excluded by the same person as Lead Faculty")
    as_instructor = a_flagged_comment(door, "E6-03 excluded by the same person as instructor")
    door.plant_a_decision(
        as_lead, STORED_EXCLUDED, decided_by=door.person_id, decided_as=AS_LEAD_FACULTY
    )
    door.plant_a_decision(
        as_instructor, STORED_EXCLUDED, decided_by=door.person_id, decided_as=AS_INSTRUCTOR
    )

    before = door.rows(as_lead)
    refused = door.decide(as_lead, UNDO)
    assert (
        refused.status_code == CONFLICT
    ), f"Undo of the reader's own Lead Faculty decision was answered {refused.status_code}."
    assert door.rows(as_lead) == before, "A refused undo wrote a row."

    step(door, as_instructor, UNDO, stored=STORED_FLAGGED, reported=FLAGGED, undo=True)


def test_undo_refuses_when_somebody_else_decided_after_the_reader(
    decision_door: DecisionDoor,
) -> None:
    """The undo ruling: the comment's latest row must be the reader's own decision.

    The door excludes a flagged comment; somebody else then keeps it; the door's
    undo is refused 409 and writes nothing, because the latest row is not the
    reader's.

    **The mutation this kills:** an undo that finds the reader's latest row and
    reverses it regardless of what came after — which here writes `FLAGGED_COLLAPSED`
    over a colleague's later keep.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = a_flagged_comment(door, "E6-03 excluded by the reader, then kept by a colleague")
    step(door, comment, EXCLUDE, stored=STORED_EXCLUDED, reported=EXCLUDED, undo=False)
    door.plant_a_decision(
        comment, STORED_KEPT, decided_by=door.a_person(), decided_as=AS_INSTRUCTOR
    )

    before = door.rows(comment)
    answered = door.decide(comment, UNDO)
    assert (
        answered.status_code == CONFLICT
    ), f"Undo with a later decision by somebody else was answered {answered.status_code}."
    assert door.rows(comment) == before, "A refused undo wrote a row."


def refused_undo(door: DecisionDoor, comment: Any, what: str) -> None:
    """One undo, required to be the door's 409 with a governed sentence, writing nothing."""
    before = door.rows(comment)
    answered = door.decide(comment, UNDO)
    assert answered.status_code == CONFLICT, (
        f"{what}: the undo was answered {answered.status_code}, not {CONFLICT}. The undo ruling: "
        "only a latest row that is the reader's own non-undo decision under INSTRUCTOR can be "
        f"undone. Body begins {answered.text[:400]!r}."
    )
    governed_sentence_of(answered, f"The 409 for {what}")
    assert door.rows(comment) == before, f"{what}: a refused undo wrote a row."


def test_an_undo_cannot_itself_be_undone(decision_door: DecisionDoor) -> None:
    """The undo ruling: undo-of-undo is 409, and it writes nothing.

    A flagged comment is excluded, then the exclusion is undone (the flag is back,
    by an undo row). A second undo is refused: the latest row is an undo, and an
    undo is never undone.

    **The mutations this kill:** an undo that reverses an undo row (it would write
    `EXCLUDED` again — the exclusion the reader just took back, restored by a
    button labelled Undo); and an undo that skips undo rows and looks further back,
    which here finds the exclusion and writes `FLAGGED_COLLAPSED` a second time.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = a_flagged_comment(door, "E6-03 an exclusion undone, then undone again")
    step(door, comment, EXCLUDE, stored=STORED_EXCLUDED, reported=EXCLUDED, undo=False)
    step(door, comment, UNDO, stored=STORED_FLAGGED, reported=FLAGGED, undo=True)

    refused_undo(door, comment, "An undo straight after an undo")
    assert status_in_report(door, comment) == FLAGGED, "The refused undo moved the comment."


def test_a_second_undo_in_a_row_does_not_reach_back_to_an_earlier_decision(
    decision_door: DecisionDoor,
) -> None:
    """The undo ruling's near miss: two of the reader's own decisions, and only the latest undoes.

    The reader keeps a flagged comment, then excludes it — both decisions theirs,
    under `INSTRUCTOR`. One undo restores `KEPT` (the state before the exclusion).
    A second undo is refused 409: the latest row is now an undo, so there is
    nothing the reader may undo, even though their earlier keep is still in the
    record.

    **The mutation this kills:** undo read as "the reader's latest *non-undo*
    decision" — which here finds the keep and writes `FLAGGED_COLLAPSED`, walking
    the comment back through the reader's history one click at a time. The ruling
    makes undo reverse exactly one decision.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = a_flagged_comment(door, "E6-03 kept, excluded, undone once, then undone again")
    step(door, comment, KEEP, stored=STORED_KEPT, reported=KEPT, undo=False)
    step(door, comment, EXCLUDE, stored=STORED_EXCLUDED, reported=EXCLUDED, undo=False)
    step(door, comment, UNDO, stored=STORED_KEPT, reported=KEPT, undo=True)

    refused_undo(door, comment, "A second undo in a row")
    assert status_in_report(door, comment) == KEPT, "The refused undo moved the comment."


def test_decided_by_you_follows_the_latest_decisions_decider(decision_door: DecisionDoor) -> None:
    """Decision 6's `decided_by_you`: true exactly when the latest row's decider is the reader.

    One flagged comment, read three times: before any decision (the router's row has
    no decider — false); after the door excludes it (true); after somebody else
    keeps it (false).

    **The mutations this kills:** `decided_by_you` true whenever the reader made
    *any* decision on the comment (the third read); true for any decided row (the
    third read); and a constant (the first or the second).
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = a_flagged_comment(door, "E6-03 a comment whose decider changes")

    def decided_by_you() -> Any:
        card = door.card(door.payload(FULL_WEEK), comment)
        assert card is not None, "The flagged comment is not on course week 1's report."
        return card.get(DECIDED_BY_YOU_FIELD)

    assert (
        decided_by_you() is False
    ), "Before any decision, the router's flag reads as the reader's."
    assert door.decide(comment, EXCLUDE).status_code == OK
    assert (
        decided_by_you() is True
    ), "After the reader's own exclusion, the card does not read as theirs."
    door.plant_a_decision(
        comment, STORED_KEPT, decided_by=door.a_person(), decided_as=AS_INSTRUCTOR
    )
    assert (
        decided_by_you() is False
    ), "After a colleague's later keep, the card still says the reader decided."
