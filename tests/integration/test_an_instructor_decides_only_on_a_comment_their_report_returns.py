"""The instructor decides only on a comment their report returns — ticket E6-03, criterion 3.

> A decision on a comment in a held stream, on a comment of a section the
> instructor does not teach, or on an answer id that is not a comment, is refused,
> and writes no row. The same world holds a decision that succeeds (entry 3).

The ticket's rule is the strict one: "a shown stream, or a release batch". The
looser rule — any comment in a section they teach — would let them act on a
comment they cannot see, and the work order (decision 2) settles how the door finds
the comment: by calling `visible_comments` / `released_comments` for their taught
sections and accepting only an answer id those return, never by rebuilding the rule
from the decision's own inputs (`docs/MISTAKES.md` entries 35 and 53). So the cases
here are the ones a rebuilt rule gets wrong, **one level out** from the obvious:

  - a comment in a **held stream** of a week they teach (the looser rule accepts);
  - a comment in the **other stream of a shown week** — same section, same week,
    the stream below the threshold (a rule keyed on the week accepts);
  - a comment in a **section they do not teach**, at the threshold there (a rule
    that checks only that the comment is shown somewhere accepts);
  - an answer id that is **a rating, not a comment**, in their own shown week;
  - an id **nothing holds**;
  - a **threat** and a **self-harm** comment in their own shown stream — v004 never
    returns them, and the door must not be the place that finds them;
  - and, the one level out in the other direction, a **released** comment: refused
    while it is held, accepted once a batch releases it.

**Every refusal is the same refusal** (work order decision 1): 404, the same body,
a sentence from `app.copy.instructor_report`, and no row — so the answer reveals
nothing about which of these the id was. A Care-class comment answered differently
from an id nothing holds would tell an instructor that a comment exists and is being
hidden from them.

**Asserted as refusals, not as absences**: each case is a request the door
answers, and the status, the body and the record are what is read — never "the
comment was not in some list" (CLAUDE.md, §4.1 confidentiality tests). Marked
`invariant` at the module level.

**Which failure a red is, before E6-03 lands:** a FAILED naming M2's columns or the
decision route (entry 44).
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.instructor_decisions import (
    EXCLUDE,
    NOT_FOUND,
    OK,
    DecisionDoor,
    governed_sentence_of,
    require_decision_columns,
)
from fixtures.moderation import CLEAR, HARMFUL, SELF_HARM, THREAT
from fixtures.report_api import (
    FIRST_HELD_WEEK,
    FULL_WEEK,
    FULL_WEEK_COMMENTS,
    HELD_COMMENTS,
    UNTAUGHT_COHORT,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# Sent with every request here, so that the reason rule can never be what answers:
# a stated reason, well inside the bound.
A_REASON = "E6-03: a reason sent so that only the visibility rule can refuse this request."


def refused_unseen(door: DecisionDoor, answer_id: Any, what: str) -> Any:
    """One exclusion of `answer_id`, required to be the door's 404 and to write nothing."""
    before = door.rows(answer_id)
    answered = door.decide(answer_id, EXCLUDE, A_REASON)
    assert answered.status_code == NOT_FOUND, (
        f"{what}: the decision was answered {answered.status_code}, not {NOT_FOUND}. The door "
        "accepts only an answer id the instructor's report currently returns — a shown stream or "
        f"a release batch. Body begins {answered.text[:400]!r}."
    )
    governed_sentence_of(answered, f"The 404 for {what}")
    assert door.rows(answer_id) == before, f"{what}: a refused decision wrote a row."
    return answered.json()


def test_a_decision_on_a_comment_the_report_does_not_return_is_refused_alike_and_writes_nothing(
    decision_door: DecisionDoor, comment_contract: Any
) -> None:
    """Every case above, in one world, each answered the same 404; then a decision that succeeds.

    **The mutations this kills:** the looser rule — any comment in a taught section
    (the held stream and the other stream are accepted); a rule rebuilt from the
    decision's inputs that checks the week and not the stream (the other stream);
    one that checks the comment is shown to *somebody* (the other section); a door
    that looks the answer up without asking whether it is a comment (the rating);
    a door that reads `answer` rather than the report's view (the threat and
    self-harm comments, which v004 never returns); and a refusal whose body differs
    by case, which turns the 404 into an oracle.

    **The control**, last and in the same world: an exclusion of a comment in their
    shown stream is answered 200 and writes one row. Without it every refusal here
    is satisfied by a route that refuses everything.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    threshold = comment_contract.threshold()

    other_section = [
        door.plant_a_comment(
            course_week=FULL_WEEK,
            stream=INSTRUCTOR_STREAM,
            text=f"E6-03 a shown comment in a section they do not teach ({index + 1})",
            verdict=HARMFUL,
            cohort=UNTAUGHT_COHORT,
        )
        for index in range(threshold)
    ]
    cases = {
        "a comment in a held stream": door.answer_id_of(HELD_COMMENTS[FIRST_HELD_WEEK][0]),
        "a comment in the held stream of a shown week": door.plant_a_comment(
            course_week=FULL_WEEK,
            stream=COURSE_STREAM,
            text="E6-03 a course-stream comment in a week whose instructor stream is shown",
            verdict=HARMFUL,
        ),
        "a comment of a section they do not teach": other_section[0],
        "an answer that is a rating, not a comment": door.a_rating_answer_in(FULL_WEEK),
        "an id nothing holds": uuid4(),
        "a threat comment in their shown stream": door.plant_a_comment(
            course_week=FULL_WEEK,
            stream=INSTRUCTOR_STREAM,
            text="E6-03 a threat comment in a shown stream, which no instructor view returns",
            verdict=THREAT,
        ),
        "a self-harm comment in their shown stream": door.plant_a_comment(
            course_week=FULL_WEEK,
            stream=INSTRUCTOR_STREAM,
            text="E6-03 a self-harm comment in a shown stream, which no instructor view returns",
            verdict=SELF_HARM,
        ),
    }

    bodies = {what: refused_unseen(door, answer_id, what) for what, answer_id in cases.items()}
    first = next(iter(bodies.values()))
    differing = {what: body for what, body in bodies.items() if body != first}
    assert not differing, (
        f"The refusals did not all answer the same body. The first was {first!r}; these differ: "
        f"{differing!r}. Work order decision 1: every case is the same 404 and the same sentence, "
        "so the refusal reveals nothing about which one the id was."
    )

    control = door.answer_id_of(FULL_WEEK_COMMENTS[0])
    before = door.rows(control)
    accepted = door.decide(control, EXCLUDE, A_REASON)
    assert accepted.status_code == OK, (
        f"An exclusion of a comment in their shown stream was answered {accepted.status_code}, "
        f"so every refusal above may be a door that refuses everything. Body begins "
        f"{accepted.text[:400]!r}."
    )
    assert len(door.rows(control)) == len(before) + 1, "The accepted decision wrote no row."


def test_a_held_comment_is_refused_until_a_batch_releases_it_and_accepted_after(
    decision_door: DecisionDoor, comment_contract: Any
) -> None:
    """The release batch is half of "what their report returns": one level out the other way.

    One held comment, asked about twice: before E4-04's cutter runs it is in a held
    stream and the door answers 404 with no row; after the cutter releases it (the
    canonical world is built to open all three legs of ADR 0152's gate) it is in the
    report's released list and the same request is answered 200 with one row.

    **The mutations this kills:** a door that asks only `visible_comments` (the
    released comment is refused for ever — an instructor can see it and cannot act
    on it); and a door that accepts any held comment in a taught section (the first
    request is accepted).
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    world = door.world

    door.door.refresh()
    held_texts = set(HELD_COMMENTS[FIRST_HELD_WEEK])
    comment = door.answer_id_of(HELD_COMMENTS[FIRST_HELD_WEEK][0])
    refused_unseen(door, comment, "a held comment before any release")

    door.door.refresh()
    cut = comment_contract.cut()(world.session)
    world.session.commit()
    assert int(cut) == 1, (
        "The cutter cut no batch over the canonical world, which is built to open all three legs "
        "of ADR 0152's gate. Until a batch exists there is no released comment to decide on."
    )
    door.door.refresh()
    released = comment_contract.released()(
        world.session,
        section_id=door.door.rows.taught_section_id,
        term_id=door.door.rows.term_id,
        stream=INSTRUCTOR_STREAM,
    )
    released_texts = {str(item.text) for item in released}
    assert HELD_COMMENTS[FIRST_HELD_WEEK][0] in released_texts, (
        f"The batch released {sorted(released_texts)}, which does not include the comment this "
        f"test asked about; the held comments were {sorted(held_texts)}."
    )

    before = door.rows(comment)
    accepted = door.decide(comment, EXCLUDE, A_REASON)
    assert accepted.status_code == OK, (
        f"A released comment — one their report's released list returns — was answered "
        f"{accepted.status_code}. Body begins {accepted.text[:400]!r}."
    )
    assert len(door.rows(comment)) == len(before) + 1, "The accepted decision wrote no row."


def test_a_comment_with_a_clear_verdict_in_their_shown_stream_is_theirs_to_decide_on(
    decision_door: DecisionDoor,
) -> None:
    """The plainest acceptance, kept apart so its failure names itself.

    A comment planted in their shown stream with a `clear` verdict, excluded with a
    reason: 200 and one row. If this is red, every refusal in this module is
    unmeasured, and the failure says so here rather than inside a longer test.
    """
    require_decision_columns(decision_door.world.tables)
    door = decision_door
    comment = door.plant_a_comment(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text="E6-03 a clear comment in their shown stream",
        verdict=CLEAR,
    )
    accepted = door.decide(comment, EXCLUDE, A_REASON)
    assert accepted.status_code == OK, (
        f"An exclusion of a shown comment was answered {accepted.status_code}. Body begins "
        f"{accepted.text[:400]!r}."
    )
    assert len(door.rows(comment)) == 1, "The accepted decision wrote no row."
