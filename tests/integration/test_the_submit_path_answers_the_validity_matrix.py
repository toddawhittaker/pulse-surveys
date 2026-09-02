"""E2-08 criterion 1 — SPEC §3.3's matrix, one cell per test.

> The full §3.3 matrix, each cell a test: valid submit stores and answers
> success; "it was okay" (and a nonsense string) bounces with the copy;
> required-comment-missing refuses; blank optional comment stores as valid;
> closed window refuses; foreign section refuses; resubmit in-window replaces;
> resubmit after close refuses.

The three refusals the ticket's Scope adds beside them are here too, because each
is a "distinct, honest reason" the same route owes: an out-of-range value, an
off-step value, and a request that is not a student's. ADR 0056's taxonomy is
`test_the_submit_path_follows_adr_0056s_taxonomy.py`; the race is
`test_two_submissions_cannot_both_become_a_response.py`; the clock is
`test_a_submission_is_stamped_by_the_clock_service.py`.

**Every refused cell is written beside an accepted one** (`docs/MISTAKES.md`
entry 3, and the near-miss pairs E2-08's traps name). A 422 says only that the
route refused something; the submission that differs from it in one value is what
says the refusal was about that value. Where the accepted half needs a second
submission it is made by a **second student** in the same section and week, so
the resubmission rule is not what either half is measuring.

**The mock provider is told what to answer, in band.** E2-07 puts its selectors
inside the comment, so a cell about a verdict differs from the happy path in the
comment text and in nothing else. The marker strings are read off the mock's own
`/mock/rules` through `marker_for`, never copied.

**Statuses.** 401, 404, 409 and 422 are E2-08's work order, transcribed in
`tests/fixtures/submit.py`. The status a *bounce* answers with is not settled
anywhere, so the two bounce tests assert what the criterion says — a client
error, the registry's coaching text, and nothing stored — and deliberately do not
pin the number.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.submit import (
    COURSE_COMMENT_POSITION,
    COURSE_RATING_POSITION,
    INSTRUCTOR_COMMENT_POSITION,
    INSTRUCTOR_RATING_POSITION,
    SECTION_TABLE,
    SUBSTANTIVE_COMMENT,
    WORKLOAD_POSITION,
    SubmitWorld,
    a_valid_submission,
)

pytestmark = pytest.mark.integration

# The two workload values the step rule turns on. SPEC §3.2: "range 0-40,
# 0.5-hour steps" (transcribed with hyphens; the section writes en dashes and the
# linter reads those as confusables). 3.25 is inside the range and off the step,
# which is ADR 0110's own example of the edge a `CHECK` could not have caught.
ON_STEP_WORKLOAD = 3.5
OFF_STEP_WORKLOAD = 3.25

# The two ratings the range rule turns on. §3.2's Likert is 1 to 5.
IN_RANGE_RATING = 5
OUT_OF_RANGE_RATING = 6

# The two Likert values §3.2's conditional rule turns on: "Required if Q1 ≤ 2".
REQUIRES_A_COMMENT = 2
LEAVES_THE_COMMENT_OPTIONAL = 3


def a_student_in_an_open_window(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai_endpoint: Any,
    window: tuple[Any, Any],
) -> Any:
    """The whole standing arrangement: seeded world, running tool, signed-in student."""
    world = submit_world.build(opens_at=window[0], closes_at=window[1])
    client = open_submit_tool(ai_base_url=mock_ai_endpoint.base_url)
    return signed_in_student(client, world)


def accepted(response: Any, what: str) -> None:
    """Stop unless the route answered success, printing what it said instead."""
    assert 200 <= response.status_code < 300, (
        f"{what} answered {response.status_code} rather than success. Body begins "
        f"{response.text[:400]!r}."
    )


def marked(mock_ai: Any, verdict: str) -> str:
    """A comment over the character floor carrying the mock's selector for `verdict`."""
    return f"{SUBSTANTIVE_COMMENT} {mock_ai.marker_for(verdict)}"


# ---------------------------------------------------------------------------
# The cell every other cell is measured against.
# ---------------------------------------------------------------------------


def test_a_complete_submission_is_stored_and_answered_success(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
) -> None:
    """§3.3's first cell: a complete, reasonable submission stores and answers success.

    Four `answer` rows rather than five, and that is the schema's doing rather
    than a slack assertion: the optional course comment is left blank, and E2-05
    makes an `answer` hold exactly one value, so a blank comment is the absence of
    a row and not a row holding nothing.

    **The mutation it kills:** a route that answers 200 and writes nothing — the
    shape every other test in this module would still pass against, because a
    refusal is what they look for. **What makes it non-vacuous:** the values
    written are read back and compared against the ones submitted, so a path that
    stored a response with no answers, or the wrong student's, fails here.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world
    comment = marked(mock_ai, "substantive")

    answered = student.submit(a_valid_submission(comment=comment))

    accepted(answered, "A complete submission inside an open window")
    responses = world.responses()
    assert len(responses) == 1, (
        f"A complete submission left {len(responses)} `response` rows: {responses}. §3.3 gates "
        "participation on a stored response, and a route that answers success and writes nothing "
        "costs the student the week."
    )
    stored = responses[0]
    assert stored["user_id"] == world.student[world.key_of("user")], (
        f"The stored response belongs to {stored['user_id']!r} and the session was the student "
        f"{world.student[world.key_of('user')]!r}. E2-05's scope makes the student key 'the same "
        "identity spelling `enrollment` uses', and a response filed against anybody else is a "
        "week of somebody else's participation."
    )
    assert stored["section_id"] == world.section[world.key_of(SECTION_TABLE)]
    assert stored["week_id"] == world.week[world.key_of("week")]

    written = world.answers_of(stored)
    assert len(written) == 4, (
        f"The submission stored {len(written)} answers: {written}. Four questions were answered — "
        "two ratings, one comment and the workload — and the optional course comment was left "
        "blank, which E2-05 stores as no row at all rather than as a row holding nothing."
    )


# ---------------------------------------------------------------------------
# §3.3's synchronous gating: the two verdicts that bounce.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verdict", ["insufficient", "nonsense"])
def test_a_comment_the_classifier_refuses_bounces_with_the_registrys_coaching_copy(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    registry_key_of: Any,
    verdict: str,
) -> None:
    """§3.3: "it was okay" is told immediately, and nothing is stored as submitted.

    > a student typing "it was okay" is told immediately that the answer is too
    > brief to count, before submission — never silently penalized after the
    > fact, with coaching copy and one concrete example, never a shame state.

    **An accepted submission runs first**, by a second student in the same section
    and week, differing only in what the comment tells the mock to answer. Without
    it a bounce is equally well explained by a route that refuses everything, and
    the parametrised pair would agree with it twice.

    **The status is deliberately not pinned.** E2-08's work order settles 401,
    404, 409, 422 and 503 and does not say which one a bounce is, so what is
    asserted is the criterion: a client error, the coaching copy the registry
    holds, and no response stored.

    **The mutation it kills:** a bounce that stores the response anyway and marks
    it invalid — "silently penalized after the fact" in as many words — and a
    bounce whose sentence is written inline in the route, which
    `externalized_key_for` refuses because no registry string appears in the body.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world
    other = signed_in_student(student.client, world, world.another_student())

    control = other.submit(a_valid_submission(comment=marked(mock_ai, "substantive")))
    accepted(control, "A submission whose comment the classifier calls substantive")

    bounced = student.submit(a_valid_submission(comment=marked(mock_ai, verdict)))

    assert 400 <= bounced.status_code < 500, (
        f"A comment the classifier called {verdict!r} was answered {bounced.status_code}. §3.3 "
        "bounces it before submission; a 2xx is the submission being accepted and a 5xx is the "
        f"student meeting an error. Body begins {bounced.text[:400]!r}."
    )
    key = registry_key_of(bounced)
    assert verdict in key.lower(), (
        f"The bounce served the registry string {key!r}, which does not name the {verdict!r} "
        "verdict. §3.3 bounces with 'the verdict's coaching copy', and one sentence for both "
        "verdicts tells a student who wrote a terse real answer that they typed nonsense."
    )
    assert len(world.responses()) == 1, (
        f"A bounced submission left {len(world.responses())} responses, and one of them is the "
        "control student's. The ticket's Scope: 'nothing is stored as submitted on a bounce'."
    )


# ---------------------------------------------------------------------------
# §3.2's conditional requirement, both directions.
# ---------------------------------------------------------------------------


def test_a_comment_left_out_is_refused_when_its_likert_is_two(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    submit_contract: Any,
    registry_key_of: Any,
) -> None:
    """§3.2: the instructor comment is "*Required if Q1 ≤ 2*", read off the question row.

    **The accepted half is the same submission with the comment present**, made by
    a second student at the same Likert 2. So the refusal cannot be about the
    rating being low, about the section, or about the window — only about the
    missing comment.

    **The mutation it kills:** the rule hardcoded as "position 2 is required when
    position 1 is at most 2" rather than read from `required_if_position` and
    `required_if_at_most`, which passes here and stops being true the moment §3.2's
    versioned set gains a question (ADR 0110: "read the rule from the question
    rows, not hardcoded"). It also kills the rule dropped altogether, which is the
    cheaper defect and the one that silently gives participation credit for a
    2-rating with no explanation attached.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world
    other = signed_in_student(student.client, world, world.another_student())

    control = other.submit(
        a_valid_submission(
            comment=marked(mock_ai, "substantive"), instructor_rating=REQUIRES_A_COMMENT
        )
    )
    accepted(control, "A Likert 2 submitted with the comment §3.2 requires beside it")

    refused = student.submit(
        {
            INSTRUCTOR_RATING_POSITION: REQUIRES_A_COMMENT,
            INSTRUCTOR_COMMENT_POSITION: None,
            COURSE_RATING_POSITION: IN_RANGE_RATING,
            COURSE_COMMENT_POSITION: None,
            WORKLOAD_POSITION: ON_STEP_WORKLOAD,
        }
    )

    assert refused.status_code == submit_contract.unprocessable, (
        f"A required comment left out was answered {refused.status_code} rather than "
        f"{submit_contract.unprocessable}. Body begins {refused.text[:400]!r}."
    )
    registry_key_of(refused)
    assert len(world.responses()) == 1, (
        "A submission missing a required field was stored. §3.3 requires 'all required fields "
        "answered' before a response counts, and the control student's is the one response there "
        "should be."
    )


def test_a_comment_left_out_is_accepted_when_its_likert_is_three(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
) -> None:
    """§3.3: "Optional comments left blank do not affect validity."

    The other direction of the line the test above stands on: one Likert higher
    and the same missing comment is an ordinary complete submission, valid, with
    nothing classified.

    **The mutation it kills:** a comment made unconditionally required, which
    refuses the majority of real submissions; and validity computed as "every
    comment was substantive" over a submission with no comments, which turns
    every blank-comment week invalid and is the reading §3.3's sentence exists to
    forbid. **Why no classification is expected:** the classifier is asked about
    *submitted* comments, and none was submitted.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world

    answered = student.submit(
        {
            INSTRUCTOR_RATING_POSITION: LEAVES_THE_COMMENT_OPTIONAL,
            INSTRUCTOR_COMMENT_POSITION: None,
            COURSE_RATING_POSITION: IN_RANGE_RATING,
            COURSE_COMMENT_POSITION: None,
            WORKLOAD_POSITION: ON_STEP_WORKLOAD,
        }
    )

    accepted(answered, "A submission whose optional comments are both blank")
    responses = world.responses()
    assert len(responses) == 1, f"The submission left {len(responses)} responses: {responses}."
    assert responses[0]["is_valid"] is True, (
        f"A complete submission with both comments left blank stored `is_valid` "
        f"{responses[0]['is_valid']!r}. §3.3: 'Optional comments left blank do not affect "
        "validity', and E3's participation formula reads this column."
    )
    assert world.answers_of(
        responses[0]
    ), "The response holds no answers at all, so `is_valid` above is true of nothing."


# ---------------------------------------------------------------------------
# ADR 0110's two edges: a value outside its question's range, and a value inside
# the range that is not a multiple of the step.
# ---------------------------------------------------------------------------


def test_a_workload_off_the_half_hour_step_is_refused_and_one_on_it_is_not(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    submit_contract: Any,
) -> None:
    """ADR 0110: "range AND step separately (3.25 must refuse)".

    > E2-08 owes a validation step and owes tests for it, including the two edges
    > a constraint would have caught: a value outside its question's range, and a
    > value inside the range that is not a multiple of the step.

    3.25 is *inside* 0 to 40, so a validation that checks only the range accepts
    it — which is the whole reason this edge is written down. The accepted half is
    3.5, one step away, by a second student.

    **The mutation it kills:** the step check left out, or written against a
    hardcoded 0.5 rather than against `question.step`. ADR 0110 makes those three
    columns "the only statement of the ranges in the system", so a hardcoded step
    is a second statement that is right until §3.2's versioned set changes.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world
    other = signed_in_student(student.client, world, world.another_student())

    comment = marked(mock_ai, "substantive")
    on_step = a_valid_submission(comment=comment)
    on_step[WORKLOAD_POSITION] = ON_STEP_WORKLOAD
    accepted(other.submit(on_step), f"A workload of {ON_STEP_WORKLOAD} hours")

    off_step = a_valid_submission(comment=comment)
    off_step[WORKLOAD_POSITION] = OFF_STEP_WORKLOAD
    refused = student.submit(off_step)

    assert refused.status_code == submit_contract.unprocessable, (
        f"A workload of {OFF_STEP_WORKLOAD} hours was answered {refused.status_code} rather than "
        f"{submit_contract.unprocessable}. It is inside SPEC §3.2's 0-to-40 range and is not a "
        f"multiple of the 0.5-hour step, so a range check alone accepts it. Body begins "
        f"{refused.text[:400]!r}."
    )
    assert len(world.responses()) == 1, (
        "An off-step workload was stored. `answer` carries no range check at all (ADR 0110), so "
        "this path is the only thing between a slider value and the reporting mean §5.1 computes."
    )


def test_a_rating_above_its_questions_maximum_is_refused_and_the_maximum_itself_is_not(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    submit_contract: Any,
) -> None:
    """ADR 0110's other edge: a value outside its question's range.

    **The accepted half is the maximum itself**, 5, which is the boundary a
    validation written `<` rather than `<=` refuses — so a fix that overshoots
    fails at the control rather than passing here.

    **The mutation it kills:** the range check left out. ADR 0110 states the cost
    plainly — "A `rating` of 9 is storable by anything that is not E2-08" — and a
    9 in a section's week distorts every figure §5.1 draws from it.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world
    other = signed_in_student(student.client, world, world.another_student())

    comment = marked(mock_ai, "substantive")
    at_maximum = a_valid_submission(comment=comment)
    at_maximum[COURSE_RATING_POSITION] = IN_RANGE_RATING
    accepted(other.submit(at_maximum), f"A rating of {IN_RANGE_RATING}, the scale's maximum")

    above = a_valid_submission(comment=comment)
    above[COURSE_RATING_POSITION] = OUT_OF_RANGE_RATING
    refused = student.submit(above)

    assert refused.status_code == submit_contract.unprocessable, (
        f"A rating of {OUT_OF_RANGE_RATING} was answered {refused.status_code} rather than "
        f"{submit_contract.unprocessable}. SPEC §3.2's Likert runs 1 to 5 and E2-05 stores that "
        f"range on the question row. Body begins {refused.text[:400]!r}."
    )
    assert len(world.responses()) == 1, "A rating outside its question's range was stored."


# ---------------------------------------------------------------------------
# The window.
# ---------------------------------------------------------------------------


def test_a_submission_into_a_closed_window_is_refused(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    closed_already: tuple[Any, Any],
    submit_contract: Any,
    registry_key_of: Any,
) -> None:
    """§3.1: "Missed weeks cannot be back-filled."

    The refusal is 409 rather than 404, and the work order says why: "the section
    is the student's own; nothing leaks". A student who missed the week is owed an
    honest reason, not the pretence that their own section does not exist.

    **What stands as its accepted half:** every other test in this module, which
    submits into a window built by the same fixture with the same instants moved
    to either side of now. The one thing that differs here is which side.

    **The mutation it kills:** the window resolved and then ignored, or resolved
    with `>=` where §3.1's close is inclusive-of-the-second and the comparison
    should refuse afterwards. Either way a submission lands in a week that has
    closed, and §3.4's score counts a week the report already published.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, closed_already
    )
    world = student.world

    refused = student.submit(a_valid_submission(comment=marked(mock_ai, "substantive")))

    assert refused.status_code == submit_contract.conflict, (
        f"A submission into a window that closed two days ago was answered "
        f"{refused.status_code} rather than {submit_contract.conflict}. Body begins "
        f"{refused.text[:400]!r}."
    )
    registry_key_of(refused)
    assert world.responses() == [], (
        f"A submission into a closed window stored {world.responses()}. §3.1 makes a missed week "
        "unfillable, and §3.4 scores 'valid weeks completed ÷ weeks elapsed to date' over exactly "
        "these rows."
    )


def test_a_resubmission_inside_the_window_replaces_the_prior_answers(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
) -> None:
    """The ticket's Scope: "Resubmission within the window replaces the prior answers".

    Three things are asserted and each is a different defect: one response row
    still (a second insert, refused by E2-05's constraint, would be a 5xx); the
    stored workload is the *second* submission's (answers appended rather than
    replaced leaves two rows for one question, which E2-05 refuses, or leaves the
    first value in place); and `first_submitted_at` is unchanged while
    `last_submitted_at` has moved, which is the work order's rule in as many words
    — "`first_submitted_at` never changes".

    **The mutation it kills:** `last_submitted_at` written to both columns on a
    resubmission, which loses the moment the student first answered and makes
    every "was this revised" query answer no.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world
    comment = marked(mock_ai, "substantive")

    first = a_valid_submission(comment=comment)
    first[WORKLOAD_POSITION] = ON_STEP_WORKLOAD
    accepted(student.submit(first), "A first submission")
    before = world.responses()
    assert len(before) == 1, f"The first submission left {len(before)} responses: {before}."
    first_stored = before[0]

    revised = a_valid_submission(comment=comment)
    revised[WORKLOAD_POSITION] = ON_STEP_WORKLOAD + 4
    accepted(student.submit(revised), "A resubmission inside the same open window")

    after = world.responses()
    assert len(after) == 1, (
        f"A resubmission left {len(after)} responses: {after}. SPEC §8 makes one response per "
        "(student, section, week), and the ticket makes the constraint 'the backstop, not the "
        "mechanism'."
    )
    stored = after[0]
    assert stored["first_submitted_at"] == first_stored["first_submitted_at"], (
        f"`first_submitted_at` moved from {first_stored['first_submitted_at']!r} to "
        f"{stored['first_submitted_at']!r} on a resubmission. The work order: "
        "'`first_submitted_at` never changes'."
    )
    assert stored["last_submitted_at"] > first_stored["last_submitted_at"], (
        f"`last_submitted_at` did not move on a resubmission — it is still "
        f"{stored['last_submitted_at']!r}. It is the only record that the answers below were "
        "revised."
    )

    workloads = [
        row["workload_hours"]
        for row in world.answers_of(stored)
        if row["workload_hours"] is not None
    ]
    assert len(workloads) == 1 and float(workloads[0]) == ON_STEP_WORKLOAD + 4, (
        f"The stored workload answers are {workloads}; the resubmission said "
        f"{ON_STEP_WORKLOAD + 4}. 'Replaces the prior answers' means the first submission's "
        "values are gone, not that a second set was added beside them."
    )


def test_a_resubmission_after_the_window_closes_is_refused(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    submit_contract: Any,
) -> None:
    """The other half of the resubmission line: "after close, resubmission refuses".

    The window is moved into the past between the two submissions, which is the
    only way to stand on this boundary without waiting for a real Friday —
    `open_window_for_section` answers from the `survey_window` rows, so moving the
    row moves the comparison from the other side.

    **The stored answers are read back afterwards**, because "refuses" has to mean
    the first submission survives untouched. A route that deleted the answers and
    then discovered the window was closed would answer 409 and lose the student's
    week.

    **The mutation it kills:** the window check made only on the insert branch, so
    a resubmission — which takes the update branch — is accepted for as long as
    the row exists.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world
    comment = marked(mock_ai, "substantive")

    first = a_valid_submission(comment=comment)
    first[WORKLOAD_POSITION] = ON_STEP_WORKLOAD
    accepted(student.submit(first), "A first submission while the window was open")
    stored_before = world.answers_of(world.responses()[0])

    world.close_the_window()

    revised = a_valid_submission(comment=comment)
    revised[WORKLOAD_POSITION] = ON_STEP_WORKLOAD + 4
    refused = student.submit(revised)

    assert refused.status_code == submit_contract.conflict, (
        f"A resubmission after the window closed was answered {refused.status_code} rather than "
        f"{submit_contract.conflict}. Body begins {refused.text[:400]!r}."
    )
    stored_after = world.answers_of(world.responses()[0])
    assert stored_after == stored_before, (
        f"The stored answers changed under a refused resubmission: {stored_before} became "
        f"{stored_after}. A refusal that has already deleted the prior answers costs the student "
        "the week it was protecting."
    )


# ---------------------------------------------------------------------------
# Scoping. SPEC §4.1's discipline: a section the student cannot reach is
# indistinguishable from one that does not exist.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_a_section_the_student_is_not_enrolled_in_answers_exactly_as_an_unknown_one(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    submit_contract: Any,
) -> None:
    """A foreign section is refused, and the refusal says nothing about its existing.

    SPEC §4.1 item 1 is asserted from E2 because this is the first epic with a
    student-visible path "and the scoping that gives 'another section' its
    meaning". A 403 here, or a 404 whose body differs from an unknown id's, tells
    a student which section codes are real — a membership oracle over the whole
    institution, one request at a time.

    **The refusal is asserted, not the absence of a name.** The two responses are
    compared to each other, byte for byte in status and body: a test that only
    checked the foreign section's code was missing from the body would pass
    against a route that answered 403 "not enrolled".

    **The foreign section has an open window of its own**, seeded with the same
    instants, so the only difference between it and the student's own section is
    the enrollment. Without that the refusal would be equally well explained by
    the section having no survey open.

    **The mutation it kills:** the enrollment check written as a 403, and the
    enrollment check dropped entirely — which would let any signed-in student
    write into any section in the deployment.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world
    foreign = world.foreign_section()
    submission = a_valid_submission(comment=marked(mock_ai, "substantive"))

    not_enrolled = student.submit(submission, section=foreign)
    unknown = student.submit(submission, section={world.key_of(SECTION_TABLE): uuid4()})

    assert not_enrolled.status_code == submit_contract.not_found, (
        f"A section the student is not enrolled in was answered {not_enrolled.status_code}. "
        f"E2-08's work order settles {submit_contract.not_found}, 'with the same body a truly "
        f"unknown section id gets'. Body begins {not_enrolled.text[:400]!r}."
    )
    assert unknown.status_code == submit_contract.not_found, (
        f"An unknown section id was answered {unknown.status_code}, so the comparison below "
        f"would be against the wrong baseline. Body begins {unknown.text[:400]!r}."
    )
    assert not_enrolled.text == unknown.text, (
        "A section the student is not enrolled in is distinguishable from one that does not "
        f"exist: {not_enrolled.text[:300]!r} against {unknown.text[:300]!r}. That difference is "
        "an oracle for which sections exist, answerable by any signed-in student against every "
        "section id in the institution."
    )
    assert (
        world.responses() == []
    ), f"A submission into a section the student is not enrolled in stored {world.responses()}."


# ---------------------------------------------------------------------------
# `require_student`. E2-08's work order: an absent or invalid session and a
# session that is not a student's are refused with **the same response**.
# ---------------------------------------------------------------------------


def test_a_request_with_no_session_is_refused_with_a_bearer_challenge(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    submit_contract: Any,
    registry_texts: Any,
) -> None:
    """`require_student` refuses an absent session with 401 and a `Bearer` challenge.

    The work order's contract, transcribed: "HTTP 401, `WWW-Authenticate: Bearer`,
    body `{"detail": "not signed in as a student"}` (copy key
    `student.not_a_student`)".

    **The same student then submits successfully**, so the 401 is known to be
    about the missing session rather than about the world being unbuildable — the
    near miss where a route is refused for some other reason and reads as an
    authentication check.

    **The mutation it kills:** the dependency left off the route, which makes the
    submit path writable by anyone who can reach it; and the sentence written
    inline, which is a user-facing string outside E2-11's inventory.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world
    submission = a_valid_submission(comment=marked(mock_ai, "substantive"))

    refused = student.submit(submission, authenticated=False)

    assert refused.status_code == submit_contract.unauthenticated, (
        f"A submission carrying no session was answered {refused.status_code} rather than "
        f"{submit_contract.unauthenticated}. Body begins {refused.text[:400]!r}."
    )
    challenge = refused.headers.get("www-authenticate", "")
    assert "bearer" in challenge.lower(), (
        f"The 401 carries `WWW-Authenticate: {challenge!r}`. RFC 6750 §3 makes the challenge how "
        "a client learns the scheme, and the work order settles `Bearer` for this API."
    )
    expected = registry_texts()[submit_contract.not_a_student_key]
    assert expected in refused.text, (
        f"The 401 served {refused.text[:300]!r}, which does not carry the registry's "
        f"`{submit_contract.not_a_student_key}` text {expected!r}."
    )
    assert world.responses() == [], "A request with no session wrote a response."

    accepted(student.submit(submission), "The same submission carrying the student's session")


def test_a_session_that_is_not_a_students_gets_the_same_answer_as_no_session_at_all(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    submit_contract: Any,
) -> None:
    """The work order: a non-student role is refused with **the same response**.

    An instructor's session is a valid session for a different surface, and this
    route answering it differently — 403 rather than 401, or a body naming the
    role — tells the holder of any session which routes exist for which role.

    **Both halves are compared to each other**, status and body, for the reason
    the foreign-section test gives: asserting only that the instructor was
    refused passes against a route that says "students only", which is the leak.

    **The mutation it kills:** `require_student` written as "any verified
    session", which would let an instructor write a student's response, and
    written as two different refusals for the two cases.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world
    instructor = signed_in_student(student.client, world, role_name="INSTRUCTOR")
    submission = a_valid_submission(comment=marked(mock_ai, "substantive"))

    as_instructor = instructor.submit(submission)
    with_no_session = student.submit(submission, authenticated=False)

    assert as_instructor.status_code == submit_contract.unauthenticated, (
        f"A session whose role is not `STUDENT` was answered {as_instructor.status_code} rather "
        f"than {submit_contract.unauthenticated}. Body begins {as_instructor.text[:400]!r}."
    )
    assert as_instructor.text == with_no_session.text, (
        f"A non-student session is answered {as_instructor.text[:300]!r} and an absent one "
        f"{with_no_session.text[:300]!r}. E2-08's work order refuses both 'with the same "
        "response', because the difference between them is a statement about what this route is."
    )
    assert world.responses() == [], "A non-student session wrote a response."
