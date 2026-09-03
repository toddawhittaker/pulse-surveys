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

**One cell of the matrix above lives next door, and E2-14 is why.** The
foreign-section cell — "a section the student is not enrolled in answers exactly
as an unknown one" — is a SPEC §4.1 denial, and it held its `invariant` marker on
the test rather than on this module, which is the currency
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
refuses. It moved unchanged to
`test_the_submit_paths_refusal_names_nothing_about_another_section.py`, whose
name carries a denial shape so that the sweep governs it; that module's docstring
records the direction and why widening the shape list was rejected. Nothing about
the cell changed, and it is collected into the isolated pass exactly as it was.

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
`tests/fixtures/submit.py`. Two more were open while this module was first
written and both were ruled in the security fix round: a **bounce is 422** — the
work order named that status without saying a bounce was one of its cases, and
these tests asserted only "a client error" until it was settled — and a failed
CSRF check is **403**, which ADR 0114's status table records because ADR 0089
settles the double-submit mechanism and no status. Every refusal in this module
now asserts a number rather than a range.
"""

from typing import Any

import pytest
from fixtures.submit import (
    BEARER_SESSION,
    CLASSIFICATION_TABLE,
    COMMENT_MAXIMUM_LENGTH,
    COOKIE_SESSION,
    COURSE_COMMENT_POSITION,
    COURSE_RATING_POSITION,
    INSTRUCTOR_COMMENT_POSITION,
    INSTRUCTOR_RATING_POSITION,
    SECTION_TABLE,
    SUBSTANTIVE_COMMENT,
    WORKLOAD_POSITION,
    SubmitWorld,
    a_valid_submission,
    csrf_token_for,
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
    submit_contract: Any,
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

    **The status is 422, ruled in this ticket's security fix round.** E2-08's work
    order settled 401, 404, 409, 422 and 503 and said which refusal each belonged
    to without saying which one a bounce is; this test asserted only "a client
    error" until that gap was closed. It asserts the number now, so a bounce that
    starts answering 409 or 400 is a change somebody has to make deliberately.

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

    assert bounced.status_code == submit_contract.unprocessable, (
        f"A comment the classifier called {verdict!r} was answered {bounced.status_code} rather "
        f"than {submit_contract.unprocessable}. §3.3 bounces it before submission; a 2xx is the "
        "submission being accepted and a 5xx is the student meeting an error. Body begins "
        f"{bounced.text[:400]!r}."
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

    **What this asserts is the criterion, not the mechanism, and ADR 0115 is why
    that distinction earns its keep.** E2-08's work order settled the mechanism as
    delete-the-answer-rows-and-insert-fresh; the ticket's own
    `classification.answer_id` under `ON DELETE RESTRICT` makes that impossible
    the first time a classified comment is revised, so the implementer's ADR
    replaces it with a revision in place. Nothing here moves: "the stored workload
    is the second submission's" and "one response row" are true of either
    mechanism and false of a path that appends or that leaves the first value
    standing. A test written against the delete would have had to be rewritten by
    the ADR, which is the shape `docs/MISTAKES.md` entry 1 is about.
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
    the first submission survives untouched. A route that had already revised the
    answer rows in place (ADR 0115) and only then discovered the window was closed
    would answer 409 and hand back the second submission's values under the first
    submission's timestamps — the student's week overwritten by a submission that
    was refused. The comparison is against the whole row set rather than against a
    count, so a revision that left the number of rows unchanged is caught.

    **The mutation it kills:** the window check made only on the insert branch, so
    a resubmission — which takes the revise branch — is accepted for as long as
    the row exists. And the window check made after the write rather than before
    it, which is the one the assertion below is aimed at.
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
        f"{stored_after}. A refusal that has already revised the prior answers (ADR 0115) costs "
        "the student the week it was protecting."
    )


def test_a_comment_that_has_been_classified_cannot_be_withdrawn_by_a_resubmission(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    submit_contract: Any,
    registry_texts: Any,
) -> None:
    """ADR 0115's product rule: a judged comment can be revised and cannot be emptied.

    > A question answered before and not now has its row deleted — **unless a
    > classification names it**, which is checked before anything is deleted. That
    > case is refused with its own reason and its own sentence
    > (`submit.comment_already_judged`, HTTP 409), rather than left to surface as
    > a constraint error under a student.

    The rule is not an acceptance criterion of this ticket; it is a rule the
    ticket *creates*, and it is asserted here because a rule that ships with
    nothing asserting it is `docs/MISTAKES.md` entry 2 in as many words. What
    makes it a rule rather than a preference is `classification.answer_id` under
    `ON DELETE RESTRICT`: without the check, the delete reaches Postgres and a
    student meets a 500 on the first resubmission that empties a comment anybody
    has ever classified.

    **The judgement is shown, not assumed.** A `classification` row naming the
    comment is read back before the withdrawal is attempted — otherwise a 409
    would be equally well explained by a route that refuses every resubmission,
    and `docs/MISTAKES.md` entry 9's rule is that a guard is executed against the
    case it is claimed to stop rather than cited.

    **The second submission also revises the rating**, from 4 to 5, and both are
    above §3.2's "Required if Q1 ≤ 2" threshold — so the comment stays optional
    and the refusal cannot be the missing-required-field 422 wearing a different
    number. That revision is also what makes the stored-row comparison say
    something: it is a change the route would have applied had it not refused.

    **The stored rows are compared whole, against the whole-refusal reading.** ADR
    0115 refuses "that case", and the natural reading is that the resubmission is
    refused rather than partly applied — a refusal a student is shown while their
    rating has quietly moved is two different answers to one request. If the
    implementation applies the rest and refuses only the withdrawal, this is where
    that surfaces: the 409 and the copy pass and the comparison below fails. That
    is a disagreement about what the ADR means, and it belongs in a dispute that
    settles it explicitly rather than in a test quietly widened to accept both.

    **The mutation it kills:** the classification-existence check dropped from in
    front of the delete. ADR 0115 rejects `ON DELETE SET NULL` and `ON DELETE
    CASCADE` by name — the first rewrites an append-only audit row through a path
    the grants cannot see, the second erases the record that a model judged an
    earlier comment — so with the check gone there is no legal way for the delete
    to succeed, and the student meets a constraint error instead of a sentence.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world

    first = a_valid_submission(comment=marked(mock_ai, "substantive"))
    first[INSTRUCTOR_RATING_POSITION] = LEAVES_THE_COMMENT_OPTIONAL + 1
    accepted(student.submit(first), "A first submission carrying a comment")

    stored_before = world.answers_of(world.responses()[0])
    comments = [row for row in stored_before if row["comment_text"] is not None]
    assert len(comments) == 1, (
        f"The first submission stored {len(comments)} comment answers: {stored_before}. This test "
        "withdraws exactly one comment, so a different number means the withdrawal below is not "
        "the thing being refused."
    )
    judged = world.classifications_of(comments[0])
    assert judged, (
        "No classification names the comment the first submission stored, so there is nothing for "
        "ADR 0115's rule to be about and a refusal below could only be about something else. The "
        "mock was told to answer `substantive`, so §3.3's synchronous gating should have recorded "
        "a verdict against this answer through `classification.answer_id`."
    )

    withdrawn = a_valid_submission(comment=None)
    withdrawn[INSTRUCTOR_RATING_POSITION] = IN_RANGE_RATING
    refused = student.submit(withdrawn)

    assert refused.status_code == submit_contract.conflict, (
        f"Withdrawing a comment that has been classified was answered {refused.status_code} "
        f"rather than {submit_contract.conflict}. ADR 0115 refuses it 'with its own reason and "
        "its own sentence ... rather than left to surface as a constraint error under a student', "
        f"and a 5xx here is that constraint error arriving unhandled. Body begins "
        f"{refused.text[:400]!r}."
    )
    published = registry_texts()
    assert submit_contract.comment_already_judged_key in published, (
        f"The copy registry publishes no `{submit_contract.comment_already_judged_key}` — it "
        f"publishes {sorted(published)}. ADR 0115 settles that key, and the sentence it holds is "
        "a product rule a student meets rather than an error they have to decode."
    )
    expected = published[submit_contract.comment_already_judged_key]
    assert expected in refused.text, (
        f"The refusal served {refused.text[:300]!r}, which does not carry the registry's "
        f"`{submit_contract.comment_already_judged_key}` text {expected!r}. Criterion 4 covers "
        "this refusal as much as any other."
    )

    stored_after = world.answers_of(world.responses()[0])
    assert stored_after == stored_before, (
        f"The stored answers changed under a refused withdrawal: {stored_before} became "
        f"{stored_after}. Two things this is about, and they fail the same way. The comment has "
        "to still be there — ADR 0115's whole point is that 'a comment cannot be withdrawn once "
        "it has been classified; it can only be revised', and a withdrawal that succeeded would "
        "either lose the verdict's subject or leave the student's words in the instructor's "
        "report (§5.1) believing they had removed them. And the rating has to be unrevised: this "
        "request was refused, and a refusal that applied the rest of the submission is two "
        "answers to one request, with the student shown the one that says nothing happened."
    )


# ---------------------------------------------------------------------------
# Scoping. SPEC §4.1's discipline: a section the student cannot reach is
# indistinguishable from one that does not exist. That cell —
# `test_a_section_the_student_is_not_enrolled_in_answers_exactly_as_an_unknown_one`
# — is in `test_the_submit_paths_refusal_names_nothing_about_another_section.py`
# from E2-14, unchanged; this module's docstring says why it moved. It is
# mentioned here rather than left to be missed by a reader walking the matrix.
# ---------------------------------------------------------------------------


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
    the foreign-section test gives (it is in
    `test_the_submit_paths_refusal_names_nothing_about_another_section.py` from
    E2-14): asserting only that the instructor was
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


# ---------------------------------------------------------------------------
# ADR 0089's double-submit check, which this route is the first to consume.
# ---------------------------------------------------------------------------


def test_a_cookie_borne_submit_is_refused_without_the_csrf_token_and_accepted_with_it(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    submit_contract: Any,
    registry_key_of: Any,
) -> None:
    """ADR 0089: "E2's first mutating endpoint consumes the check." This is that endpoint.

    > **CSRF, live because of `SameSite=None`:** a double-submit token bound to
    > the session's `jti` by HMAC (`issue_csrf_token`/`verify_csrf_token`). A
    > tossed cookie without the secret still fails, and a token minted for one
    > session does not verify against another's `jti`. Its cookie is not
    > `HttpOnly` — the SPA echoes it in `X-Pulse-CSRF`. E2's first mutating
    > endpoint consumes the check; E1-15 carries the line so it cannot arrive
    > unowned.

    The check exists and, until this route, had **no caller** — which is
    `docs/MISTAKES.md` entry 2 exactly: a primitive that is written, unit-tested
    and never reached is a convention. The cookie is `SameSite=None` because the
    tool lives in a cross-site iframe for the whole visit, so a browser sends it
    on a cross-site form post; the double-submit pair is the only thing between
    that and any page on the internet writing a student's weekly survey.

    **Three submissions, and the third is the one that makes this a test of
    verification.** The accepted one carries the pair; the second carries neither;
    the third carries a *valid* token minted for **another session** — in both the
    cookie and the header, because an attacker who can make a browser send a
    cross-site request can also toss a cookie and therefore controls both halves
    of a double submit. So a check that reads "a token is present", or one that
    compares the cookie to the header, answers the third case exactly as it
    answers the accepted one. Only ADR 0089's HMAC against *this* session's `jti`
    refuses it, which is the whole of what that record buys: "a tossed cookie
    without the secret still fails, and a token minted for one session does not
    verify against another's `jti`."

    Each submission differs from the accepted one in exactly one thing — the
    token — with the same body, section, student class and open window. The
    accepted half is made by a second student so that the resubmission rule is
    not what any of the three is measuring.

    **The status is 403, and ADR 0089 is not where it comes from.** That record
    settles the mechanism, the `X-Pulse-CSRF` header and the binding to `jti` and
    settles no status; this ticket's security fix round ruled 403 and **ADR 0114's
    status table records it** beside the refusals that record already carries. 403
    rather than 401 because the session is valid and the *request* is not — a
    `WWW-Authenticate` challenge here would invite the client to do something that
    would not help, which is the same distinction the 401 tests above turn on.

    **The mutations it kills:** the check omitted from the route; the check
    applied to a presence rather than to a verification — `verify_csrf_token`
    never called, which the security round's re-mutation battery measured
    **surviving** the first version of this test, because that version only ever
    sent the token and its absence (`docs/disputes/E2-08-06.md`, M1c); and the
    verification performed without the binding to `jti`, which the third case
    reaches because the token it sends is genuine under the same secret and wrong
    only about whose session it is.

    **What it still does not kill, said plainly:** a check that verifies the
    header and ignores the cookie entirely. That is not a weakening — a
    header-only check is *stronger* than a double submit, since the header is the
    half a cross-site request cannot set — so there is no mutation there worth
    naming, and this test would go on passing if the cookie half were dropped.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world
    other = signed_in_student(student.client, world, world.another_student())
    submission = a_valid_submission(comment=marked(mock_ai, "substantive"))

    with_the_token = other.submit(submission, via=COOKIE_SESSION, csrf=True)
    accepted(with_the_token, "A cookie-borne submission carrying ADR 0089's double-submit pair")

    without = student.submit(submission, via=COOKIE_SESSION, csrf=False)

    assert without.status_code == submit_contract.csrf_refused, (
        f"A cookie-authenticated submission carrying no CSRF token was answered "
        f"{without.status_code} rather than {submit_contract.csrf_refused}. ADR 0089 makes the "
        "session cookie `SameSite=None` — the tool is inside a cross-site iframe for the whole "
        "visit — so a browser sends it on a cross-site form post, and the double-submit pair is "
        "the only thing that distinguishes the student's own request from any page on the "
        f"internet. Body begins {without.text[:400]!r}."
    )
    registry_key_of(without)

    # A token that is genuine — minted through the tool's own primitive, under
    # the same secret — and belongs to the *other* student's session. Sent as
    # both the cookie and the header, so nothing short of verifying it against
    # this session's `jti` can refuse it.
    another_sessions_token = csrf_token_for(other.token, other.secret)
    assert another_sessions_token != csrf_token_for(student.token, student.secret), (
        "The two students' CSRF tokens are the same string, so the request below is not carrying "
        "another session's token at all and this case could not pose its question. ADR 0089 binds "
        "the token to the session's `jti` by HMAC, and two sessions have two `jti`s."
    )
    wrong = student.submit(submission, via=COOKIE_SESSION, csrf_token=another_sessions_token)

    assert wrong.status_code == submit_contract.csrf_refused, (
        f"A cookie-authenticated submission carrying another session's CSRF token was answered "
        f"{wrong.status_code} rather than {submit_contract.csrf_refused}. The token is valid — it "
        "was minted by this tool, under this secret — and it is bound to a different `jti`. A "
        "check that accepts it is checking that a token is *present*, or that the cookie and the "
        "header agree, and an attacker who can send a cross-site request can arrange both. ADR "
        "0089: 'a token minted for one session does not verify against another's `jti`'. Body "
        f"begins {wrong.text[:400]!r}."
    )
    registry_key_of(wrong)

    stored = [
        row for row in world.responses() if row["user_id"] == world.student[world.key_of("user")]
    ]
    assert stored == [], (
        f"A submission refused for a missing or wrong CSRF token stored {stored}. The check is "
        "worth nothing if the write has already happened by the time it runs."
    )


def test_a_bearer_borne_submit_needs_no_csrf_token(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
) -> None:
    """The exemption, and it is the near-miss pair for the test above.

    ADR 0089's cookieless path: "the SPA captures the fragment into
    `sessionStorage`, strips it from the address bar, and sends it as
    `Authorization: Bearer` thereafter. `session_from_request` reads the Bearer
    header before the cookie, so the Bearer path carries the session with no
    cookie required." A Bearer header is not something a cross-site form or an
    image tag can make a browser send, so a request carrying one is not a request
    a browser can be tricked into making, and there is nothing for the check to
    protect.

    **Without this half the fix has an obvious wrong shape that passes.**
    Requiring the token unconditionally refuses every request the SPA actually
    makes — ADR 0089 says the SPA does not depend on the cookie at all — so the
    product would be broken for the one client it has while the test above went
    green. It is also the shape that reads as "more secure" in review, which is
    why it is written down rather than left to judgement.

    **The request carries no cookie at all**, which the fixture clears before and
    after every submission: a leftover CSRF cookie from another request would
    make this pass while the route was in fact demanding one.

    **The mutation it kills:** the check applied to every request rather than to
    a cookie-authenticated one.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world

    answered = student.submit(
        a_valid_submission(comment=marked(mock_ai, "substantive")),
        via=BEARER_SESSION,
        csrf=False,
    )

    accepted(answered, "A Bearer-authenticated submission carrying no CSRF token")
    assert len(world.responses()) == 1, (
        f"The submission left {len(world.responses())} responses. ADR 0089 makes Bearer the path "
        "the SPA uses for every request after the launch, so a route that refuses it refuses the "
        "only client this product has."
    )


# ---------------------------------------------------------------------------
# The bound on a submitted comment. ADR 0062: parsed once, at the edge.
# ---------------------------------------------------------------------------


def test_a_comment_over_the_length_bound_is_refused_before_the_provider_is_asked(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    submit_contract: Any,
) -> None:
    """A comment of 4000 characters is accepted and one of 4001 is refused, unasked.

    SPEC §3.2 makes both comments free text and gives them no length, so an
    unbounded comment is a request body that reaches the model: a bill, a latency
    inside SPEC §10's 2.5-second budget, and a prompt surface, all chosen by
    whoever is typing. The bound is 4000 characters, ruled in this ticket's
    security fix round.

    **The boundary is the pair, and it is exact.** 4000 is accepted and 4001 is
    refused, so a bound written `<` where it should be `<=` fails at the accepted
    half rather than passing here — the off-by-one is the whole reason a bound
    gets a test rather than a review comment. Both comments carry the mock's
    forced-verdict marker, which counts toward the length like any other
    character, so the two differ by exactly one character of padding.

    **That no classification row is written says the refusal happened before the
    provider was asked**, which is the property with a bill attached: a bound
    enforced after the call refuses the submission and has already spent the
    request it was written to prevent, and a status assertion alone cannot tell
    the two apart. The count is taken immediately before the over-length
    submission and again after, so the accepted half's own classification is not
    what is being counted.

    **It does not say the bound is on the request model, and it used to claim it
    did.** §3.3's gate runs after all value validation, so a bound in the service
    also refuses before the provider is asked and also leaves no row — the
    security round's re-mutation battery measured exactly that mutation surviving
    this test (`docs/disputes/E2-08-06.md`, M2c). ADR 0062's "one parse, at the
    edge, into typed values" is a claim about *where* the value is judged, and
    only a test that reaches the request model can make it:
    `tests/unit/test_a_submitted_comment_is_bounded_at_the_edge.py` is that test,
    and it is where a bound moved into the service goes red.

    **The mutations it kills:** the bound absent; the bound off by one in either
    direction, which the exact pair above is for; and the bound written as a
    truncation, which is worse than no bound — it stores words the student did
    not write under their name, and §5.1 shows them to the instructor.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world
    other = signed_in_student(student.client, world, world.another_student())
    marker = mock_ai.marker_for("substantive")

    def comment_of(length: int) -> str:
        assert length > len(marker), (
            f"A comment of {length} characters cannot carry the mock's {marker!r} selector, which "
            f"is {len(marker)} characters. Without the selector the mock judges by its own length "
            "threshold and this test stops being about the tool's bound."
        )
        built = marker + "a" * (length - len(marker))
        assert len(built) == length, f"Built a comment of {len(built)} characters, not {length}."
        return built

    at_the_bound = other.submit(a_valid_submission(comment=comment_of(COMMENT_MAXIMUM_LENGTH)))
    accepted(at_the_bound, f"A comment of exactly {COMMENT_MAXIMUM_LENGTH} characters")

    before = len(world.rows_of(CLASSIFICATION_TABLE))
    over = student.submit(a_valid_submission(comment=comment_of(COMMENT_MAXIMUM_LENGTH + 1)))

    assert over.status_code == submit_contract.unprocessable, (
        f"A comment of {COMMENT_MAXIMUM_LENGTH + 1} characters was answered {over.status_code} "
        f"rather than {submit_contract.unprocessable}. One character over the bound is the case "
        f"the bound exists for. Body begins {over.text[:400]!r}."
    )
    stored = [
        row for row in world.responses() if row["user_id"] == world.student[world.key_of("user")]
    ]
    assert stored == [], f"An over-length comment stored {stored}."
    assert len(world.rows_of(CLASSIFICATION_TABLE)) == before, (
        f"The over-length submission left {len(world.rows_of(CLASSIFICATION_TABLE))} "
        f"classification rows where there were {before}. A row means the comment reached the "
        "provider — the request was sent, paid for and judged — and only then refused, which is "
        "the whole of what this bound was added to prevent. ADR 0062 puts the parse at the edge "
        "precisely so a value is judged before anything downstream acts on it."
    )
