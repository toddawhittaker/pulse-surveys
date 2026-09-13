"""The reveal takes its subject from the record, not from the caller — ticket E4-01.

The carried entry this closes is
`docs/tickets/e1/carried-from-e0.md`, "The reveal's actor check and an
instructor's read scope compose". Three facts that are individually correct
compose into one that is not: `ActorScope` carries `holds_care` beside the
purview so Care can never be unioned into a scope; `section_roster` hands
instructor-scoped code the `user_id` of every enrolled student, which is the
view's whole point; and `reveal_identity` used to check only that the *actor*
holds Care, asking nothing about where the subject came from. A Care officer who
also teaches — §2.1 permits her, §6.2 spends a paragraph on her — could take a
`user_id` off her own roster, reveal it, and leave an audit row indistinguishable
from a legitimate access.

The entry's "done when" is what this module asserts: "the capability cannot be
exercised against a subject the actor reached through a reporting scope … proved
by a test that fails on the composition itself: a two-hat actor, a roster row
from her own section, a reveal that must be refused."

**The shape E4-01 settles**, written out here because a test cannot be written
against an interface that does not exist:

    reveal_identity(
        *, actor_person_id: UUID, answer_id: UUID, case_id: UUID | None = None
    ) -> RevealedIdentity | None

`subject_user_id` is **deleted, not deprecated**. The subject is derived inside
the Care session: `answer_id` → `answer.response_id` → `response.user_id`. The
order of checks is E0-10's, unchanged: a non-Care actor gets `NotCareStaffError`
first, and only then is a subject derived, an `answer_id` matching no row raising
`UnknownRevealSubjectError` and writing no audit record.

**Two refusals, and telling them apart is a criterion rather than a nicety.**
The ticket asks that "the refusal is proven to come from the subject-derivation
guard, not from the actor check", because a guard test whose outcome a second
defence layer also produces proves nothing (`docs/MISTAKES.md` entry 3, and the
ticket's own trap section). Every refusal here is therefore driven with the layer
under test as the *only* thing that can be wrong, and pinned by exception type —
never by a message, never by an absence.

**Denial, not absence.** Where a test is about a subject that may not be reached,
it asserts that the call was *refused*, not that a name was missing from a
result. An absence is satisfied by a call that returned nothing for an unrelated
reason. The one absence asserted anywhere here is the audit row a refused
derivation must not write, and it is asserted as a forbidden state beside a
control proving the same reader finds the row a successful reveal does write
(entry 2, "prefer asserting the forbidden state", and entry 3 for the control).

**What this module deliberately does not assert** (`docs/MISTAKES.md` entry 14):
that the answer's latest classification is in the threat or self-harm set. The
moderation task is E6's, `ClassificationTask` has one member today, and the work
order defers the predicate to E6 in ADR 0144 rather than silently — so the guard
under test is subject-from-record, and a test demanding a verdict vocabulary
would be asserting a design this ticket does not build. Nor does it touch the
`record_identity_reveal` definer's own contract, which the ADR keeps for E10 with
the case model.

**One thing that must be read before a red here is believed.** `pulse_care` holds
`SELECT` on `role_assignment` and on nothing else — no view, no other base table
(`RUNTIME_BASE_TABLE_PRIVILEGES` in `tests/integration/test_identity_grants.py`,
an equality asserted in both directions) — and the derivation runs on that
connection. It reaches `answer` and `response` through a **third `SECURITY
DEFINER` function**, `reveal_subject_for_answer(answer_id uuid) RETURNS uuid`,
ruled at build time and recorded in ADR 0144: a grant would have handed the Care
role a standing walk from any answer id to any user id *outside* the door, while
a definer keeps that connection's own read surface at zero — which is what every
refusal in the grants module is written against. Until that function exists these
tests fail on a missing function or on `permission denied` rather than on the
guard, and
`test_identity_grants.py::test_pulse_care_may_execute_exactly_the_functions_the_care_door_is_made_of`
is where its absence is diagnosed by name.

**The refusal stays in Python.** That function answers NULL for an answer id
matching no row, and the service turns the NULL into
`UnknownRevealSubjectError`: the error *types* are what E10's queue tells the two
refusals apart by, and a database error crossing that boundary is the `__cause__`
leak
`test_care_service_reveal.py::test_the_refusal_carries_no_part_of_the_students_identity`
exists to catch.
"""

import inspect
from typing import Any
from uuid import uuid4

import pytest
from fixtures.care_subject import (
    ACTOR_PARAMETER,
    ANSWER_PARAMETER,
    AUDIT_CASE_COLUMN,
    AUDIT_SUBJECT_COLUMN,
    AUDIT_TIMESTAMP_COLUMN,
    CASE_PARAMETER,
    DELETED_SUBJECT_PARAMETER,
    NOT_CARE_STAFF_ERROR,
    REVEAL,
    REVEAL_PARAMETERS,
    UNKNOWN_SUBJECT_ERROR,
    a_user_id_from_the_roster_of,
    audit_rows_for,
    identity_values,
    plant_a_comment_answer,
    require_the_reveal_interface,
    the_two_hat_actor,
)

pytestmark = pytest.mark.integration

# The vocabulary a parameter naming a student would be spelled in. **This file's
# choice**, and the canary in
# `test_no_parameter_of_the_reveal_can_be_handed_a_student_identifier` is what
# makes a wrong guess fail loudly rather than quietly: it requires the vocabulary
# to recognise `subject_user_id`, which is the parameter this ticket deletes and
# therefore the one spelling that is certainly in the set.
STUDENT_IDENTIFIER_FRAGMENTS = ("user", "subject", "student", "learner", "respondent", "sub")


def reveal_and_refusals(care_service: Any) -> tuple[Any, Any, Any]:
    """The three names every test below needs, after the interface guard has run."""
    return (
        getattr(care_service, REVEAL),
        getattr(care_service, NOT_CARE_STAFF_ERROR),
        getattr(care_service, UNKNOWN_SUBJECT_ERROR),
    )


# ---------------------------------------------------------------------------
# Criterion 1 — the signature itself makes the old call unwritable.
# ---------------------------------------------------------------------------


def test_the_reveal_takes_exactly_the_three_parameters_the_ticket_settles(
    care_service: Any,
) -> None:
    """Criterion 1: no caller-supplied identifier reaches the reveal as its subject.

    E4-01's scope: "`reveal_identity` stops accepting a bare `subject_user_id` …
    a caller can no longer name an arbitrary student", and "no compatibility shim
    stays behind". An equality rather than a membership test, in both directions,
    because both directions are the criterion: a missing parameter is a call the
    queue cannot make, and an *extra* one is the shim the ticket forbids.

    Keyword-only is asserted with them and is not decoration. The two arguments
    are "a comment" and "the staff member asking about it"; positionally they are
    two uuids, and a caller that swapped them would be making a reveal that
    succeeds and audits the wrong person — which is the one thing
    `test_care_service_reveal.py` has refused to guess at since E0-10.

    **The mutation this kills**: keeping `subject_user_id` beside `answer_id` as
    an optional parameter — the "validate the id against a record" alternative the
    ticket rejects by name, which leaves the bare id in the signature and is the
    shape the carried entry warns about. **The near miss it tolerates**: a
    parameter renamed in a later ticket, which fails here with both sets printed
    rather than silently.
    """
    require_the_reveal_interface(care_service)
    reveal, _, _ = reveal_and_refusals(care_service)

    parameters = inspect.signature(reveal).parameters
    assert tuple(parameters) == REVEAL_PARAMETERS, (
        f"`{REVEAL}` takes {list(parameters)}; E4-01 settles {list(REVEAL_PARAMETERS)}.\n\n"
        f"If `{DELETED_SUBJECT_PARAMETER}` is still there, the criterion is unmet: the ticket "
        "deletes it rather than deprecating it, because 'keeping `subject_user_id` and validating "
        "it against such a record leaves the bare id in the signature and is the shape the carried "
        "entry warns about'."
    )
    positional = [
        name
        for name, parameter in parameters.items()
        if parameter.kind is not parameter.KEYWORD_ONLY
    ]
    assert not positional, (
        f"`{REVEAL}` accepts {positional} positionally. Both of its required arguments are uuids — "
        "a comment and the person asking about it — so a transposed call is a reveal that succeeds "
        "and audits the wrong person, and nothing in the type system would catch it."
    )


def test_no_parameter_of_the_reveal_can_be_handed_a_student_identifier(
    care_service: Any,
) -> None:
    """Criterion 1, in the second currency: no parameter *reads* as a student.

    The test above pins the exact set, which goes red on any deliberate rename and
    has to be updated when one happens. This one keeps saying something after that
    update: whatever the parameters are called, none of them but the actor's may be
    the name of a student. A ticket that renamed `answer_id` to `subject_answer_id`
    would pass the equality after one line of maintenance and fail here, which is
    the direction that matters — the carried entry is about an identifier arriving
    from the caller, not about a particular spelling.

    **The canary** is `docs/MISTAKES.md` entry 3's rule for a pattern searched
    against text: the vocabulary is run against the string it certainly must catch
    — `subject_user_id`, the parameter this ticket deletes — before its silence
    about the real signature is believed. Without it, a fragment tuple that had
    gone blind (a typo, an empty tuple) would report a clean signature for any
    parameter list at all.

    **The mutation this kills**: reintroducing the caller-supplied subject under
    another name — `student_id`, `user_id`, `respondent` — which the equality above
    would also catch today but which is exactly what a later widening of that
    constant would let through.
    """
    require_the_reveal_interface(care_service)
    reveal, _, _ = reveal_and_refusals(care_service)

    def names_a_student(parameter: str) -> bool:
        lowered = parameter.lower()
        return any(fragment in lowered for fragment in STUDENT_IDENTIFIER_FRAGMENTS)

    assert names_a_student(DELETED_SUBJECT_PARAMETER), (
        f"The vocabulary {list(STUDENT_IDENTIFIER_FRAGMENTS)} does not recognise "
        f"`{DELETED_SUBJECT_PARAMETER}`, which is the parameter this ticket deletes and therefore "
        "the one spelling it certainly has to catch. Its silence about the real signature below "
        "would mean nothing."
    )

    offenders = sorted(
        name
        for name in inspect.signature(reveal).parameters
        if name != ACTOR_PARAMETER and names_a_student(name)
    )
    assert not offenders, (
        f"`{REVEAL}` takes {offenders}, which read as a student rather than as the record Care is "
        "acting on. The carried entry: 'the reveal takes its subject from a Care case rather than "
        "from any caller-supplied id, or an equivalent guard'. A parameter a caller fills with a "
        "`user_id` is the composition being closed, whatever it is called."
    )


# ---------------------------------------------------------------------------
# Criterion 2 — the two-hat composition, refused, and by the right layer.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_a_roster_user_id_cannot_be_named_as_the_subject_by_a_care_officer_who_teaches(
    care_service: Any, committed_rows: Any
) -> None:
    """The composition itself: her own roster's key, and no call that accepts it.

    This is the carried entry's "done when" in its strongest available form. The
    actor holds a live `CARE` assignment *and* an `INSTRUCTOR` assignment; the
    `user_id` comes off an enrollment in the very section she teaches, which is
    what `section_roster` hands instructor-scoped code; and the assertion is that
    there is no call to make. `TypeError` is the refusal, raised by the interpreter
    before a line of the service runs, which is the ticket's criterion 1 stated as
    behaviour rather than as a signature.

    **The control runs first and is not ceremony.** The same actor, in the same
    test, reveals a legitimately planted comment's author — so the refusal is
    attributable to the parameter and not to an actor who cannot reveal anything,
    a service that cannot reach its connection, or a fixture that seeded nothing
    (`docs/MISTAKES.md` entry 3). Without it, a `reveal_identity` that raised
    `TypeError` on every call would pass this perfectly.

    **The mutation this kills**: `subject_user_id` kept as an optional parameter
    beside `answer_id`, with the derivation used only when it is absent. Every
    other test in this module stays green against that implementation, and the
    capability the carried entry describes is still exercisable.
    """
    require_the_reveal_interface(care_service)
    reveal, _, _ = reveal_and_refusals(care_service)

    actor = the_two_hat_actor(committed_rows)
    roster_user_id = a_user_id_from_the_roster_of(committed_rows, actor.taught_section_id)
    planted = plant_a_comment_answer(committed_rows)

    allowed = reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: planted.answer_id})
    assert identity_values(allowed) & planted.identity_values, (
        f"The control failed: the two-hat actor was handed a legitimately planted comment and "
        f"`{REVEAL}` answered {allowed!r} rather than the seeded "
        f"{sorted(planted.identity_values)}. The refusal below would then say nothing about the "
        "roster key — a door shut to everybody refuses it just as convincingly. "
        "`test_the_reveal_answers_the_author_of_the_comment_it_was_given` is where that is "
        "diagnosed."
    )

    with pytest.raises(TypeError):
        reveal(**{ACTOR_PARAMETER: actor.person, DELETED_SUBJECT_PARAMETER: roster_user_id})


@pytest.mark.invariant
def test_a_roster_user_id_offered_as_the_record_is_refused_by_the_subject_guard(
    care_service: Any, committed_rows: Any
) -> None:
    """The same composition through the one parameter that is left — and which layer refused.

    Criterion 2 asks that the refusal "is proven to come from the subject-derivation
    guard, not from the actor check". This is the case where that distinction is
    the whole assertion: the actor *does* hold Care, so the actor check has nothing
    to say, and the identifier she reached through her reporting scope is offered
    where the record belongs. A `user_id` names no answer, so the derivation is what
    refuses, and `UnknownRevealSubjectError` is what says so.

    Two controls, in this order. She can reveal a real comment's author, so a
    refusal is not "this actor is refused everything"; and the refusal is asserted
    to be the derivation's error rather than the actor's, so a service that gave up
    on the whole call with `NotCareStaffError` fails here rather than passing as a
    guard.

    **The mutation this kills**: a derivation that falls back to treating an
    unmatched `answer_id` as a user id — the "be liberal in what you accept" repair
    that reopens the composition through the surviving parameter. **The near miss**:
    raising a single error class for both refusals, which the ticket forbids by
    name so that E10's queue can tell them apart without string-matching, and which
    `test_the_two_refusals_are_different_classes` pins from the other side.
    """
    require_the_reveal_interface(care_service)
    reveal, not_care_staff, unknown_subject = reveal_and_refusals(care_service)

    actor = the_two_hat_actor(committed_rows)
    roster_user_id = a_user_id_from_the_roster_of(committed_rows, actor.taught_section_id)
    planted = plant_a_comment_answer(committed_rows)

    allowed = reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: planted.answer_id})
    assert identity_values(allowed) & planted.identity_values, (
        "The control failed: the two-hat actor could not reveal the author of a legitimately "
        f"planted comment ({allowed!r}). Her `CARE` assignment is what makes the refusal below "
        "attributable to the subject guard rather than to the actor check."
    )

    with pytest.raises(unknown_subject) as refused:
        reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: roster_user_id})

    assert not isinstance(refused.value, not_care_staff), (
        f"The refusal is a `{NOT_CARE_STAFF_ERROR}`, raised for an actor who holds a live `CARE` "
        "assignment. §6.2 makes the Care role the one role this door opens for, so a refusal "
        "attributed to her role is both wrong about her and useless to E10's queue, which has to "
        "tell 'not Care' from 'not a legitimate subject'."
    )


@pytest.mark.invariant
def test_a_refused_derivation_writes_no_audit_row(
    care_service: Any, committed_rows: Any, migrated_engine: Any
) -> None:
    """A subject that was never reached is not an access, so §4's log must not record one.

    The work order settles it: "an `answer_id` matching no answer row raises
    `UnknownRevealSubjectError`, and **no audit record is written for a refused
    derivation**". The reason it matters is §6.2's accountability model — the
    identity-access log is reviewed monthly outside the Care office, and a log
    padded with authorizations that revealed nobody makes that review read a
    fabricated pattern of access.

    **The forbidden state is what is asserted** (`docs/MISTAKES.md` entry 2), and
    the reader is required to *find* something first (entry 3). The successful
    reveal runs first with the same actor, and its row is counted on the same
    connection with the same query — so a reader that answers zero for everything,
    a wrong table or a filter that matches nothing fails the control instead of
    reporting the refused call as clean.

    **The mutation this kills**: recording the authorization before deriving the
    subject — the natural shape for an implementation that keeps E0-10's
    record-then-read order and adds the derivation after it. That implementation
    passes every other test in this module.
    """
    require_the_reveal_interface(care_service)
    reveal, _, unknown_subject = reveal_and_refusals(care_service)

    actor = the_two_hat_actor(committed_rows)
    planted = plant_a_comment_answer(committed_rows)

    reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: planted.answer_id})
    after_the_honest_call = audit_rows_for(migrated_engine, committed_rows, actor.person)
    assert len(after_the_honest_call) == 1, (
        f"The control failed: a successful reveal by this actor left "
        f"{len(after_the_honest_call)} audit row(s) rather than one, read on a second connection. "
        "Until that reader can see the row a real reveal writes, its silence about the refused "
        "call below is not evidence of anything."
    )

    with pytest.raises(unknown_subject):
        reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: uuid4()})

    after_the_refusal = audit_rows_for(migrated_engine, committed_rows, actor.person)
    assert len(after_the_refusal) == 1, (
        f"A refused derivation left an audit row: this actor has {len(after_the_refusal)} rows "
        f"after one successful reveal and one refusal ({after_the_refusal}). §4's record exists "
        "because 'every identity access is automatically audit-logged'; a call that reached no "
        "student is not an access, and a log that records it tells the monthly review outside the "
        "Care office that a student was named when none was."
    )


# ---------------------------------------------------------------------------
# Layer attribution — which check refused, pinned by type in both directions.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_a_person_with_no_care_assignment_is_refused_by_the_actor_check(
    care_service: Any, committed_rows: Any
) -> None:
    """A real comment, a real person, no Care hat: `NotCareStaffError` and not the other one.

    E0-10's rule is unchanged by this ticket and the work order says so — the
    actor check runs first, "exactly as now". This is the half that says the new
    guard did not replace it: the `answer_id` is a legitimately planted comment, so
    the derivation would succeed, and the only thing wrong with the call is the
    person making it.

    **The control is the same call with the Care actor**, so the refusal is
    attributable to the assignment rather than to a service that cannot reach its
    connection or a comment that does not exist.

    **The mutation this kills**: deriving the subject before checking the actor.
    That implementation refuses this call too — with the wrong error where the
    answer is absent, which is `test_a_person_with_no_care_assignment_is_refused_
    for_being_who_they_are_before_the_record_is_looked_up`'s subject — and hands a
    non-Care caller a working existence oracle over comment ids in the meantime.
    """
    require_the_reveal_interface(care_service)
    reveal, not_care_staff, unknown_subject = reveal_and_refusals(care_service)

    actor = the_two_hat_actor(committed_rows)
    planted = plant_a_comment_answer(committed_rows)

    allowed = reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: planted.answer_id})
    assert identity_values(allowed) & planted.identity_values, (
        "The control failed: the Care actor did not get the planted comment's author back, so the "
        "refusal below would say nothing about the assignment."
    )

    with pytest.raises(not_care_staff) as refused:
        reveal(**{ACTOR_PARAMETER: actor.reporting_person, ANSWER_PARAMETER: planted.answer_id})

    assert not isinstance(refused.value, unknown_subject), (
        f"A person with no `CARE` assignment was refused with `{UNKNOWN_SUBJECT_ERROR}` over a "
        "comment that certainly exists. The two refusals mean different things — one is about who "
        "is asking and one is about what they asked about — and this one is wrong in the direction "
        "that matters: it says the record is at fault when the role is."
    )


@pytest.mark.invariant
def test_a_person_with_no_care_assignment_is_refused_for_being_who_they_are_before_the_record_is_looked_up(
    care_service: Any, committed_rows: Any
) -> None:
    """Both things wrong at once: the actor check answers, and the derivation never runs.

    The work order preserves E0-10's order of checks and this is the case that can
    tell the two orders apart. A non-Care caller asks about an `answer_id` that
    matches nothing: under the settled order the answer is `NotCareStaffError`,
    and under the reversed one it is `UnknownRevealSubjectError`.

    **Why the order is worth a test rather than a comment.** A derivation that ran
    first would answer a caller with no Care assignment differently depending on
    whether the id names a real comment — an existence oracle over comment
    identifiers, handed to exactly the reporting-scoped caller this ticket exists
    to keep away from the queue, and one that leaves no audit row behind.

    **The mutation this kills**: moving the derivation above the actor check, which
    is the natural shape for an implementation that wants to fail fast on a bad
    identifier. Its near miss — deriving first but re-raising `NotCareStaffError` —
    is not distinguishable from here and is not meant to be
    (`docs/MISTAKES.md` entry 14): what is asserted is the answer the caller gets.
    """
    require_the_reveal_interface(care_service)
    reveal, not_care_staff, unknown_subject = reveal_and_refusals(care_service)

    actor = the_two_hat_actor(committed_rows)
    planted = plant_a_comment_answer(committed_rows)

    allowed = reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: planted.answer_id})
    assert identity_values(allowed) & planted.identity_values, (
        "The control failed: the Care actor could not reveal a planted comment's author, so "
        "nothing below distinguishes an order of checks from a door that is shut."
    )

    with pytest.raises(not_care_staff) as refused:
        reveal(**{ACTOR_PARAMETER: actor.reporting_person, ANSWER_PARAMETER: uuid4()})

    assert not isinstance(refused.value, unknown_subject), (
        f"A caller with no `CARE` assignment, asking about an id that names no comment, was told "
        f"the *record* was the problem (`{UNKNOWN_SUBJECT_ERROR}`). The derivation therefore ran "
        "before the actor check, and the difference between its two answers is an existence oracle "
        "over comment identifiers for a caller who may not use this door at all."
    )


def test_the_two_refusals_are_different_classes(care_service: Any) -> None:
    """Criterion: the refusal is "its own distinguishable error", without string-matching.

    E4-01's scope says why: E10's queue has to tell "not Care" from "not a
    legitimate subject", and a queue that told them apart by reading a message
    would break on the next reword. Neither may be the other, and neither may be a
    subclass of the other — a subclass is caught by `except` on its parent, which
    is the same conflation one level down and is the shape a tidying refactor
    reaches for.

    A shared base class above both is fine and is not asserted against: it is what
    lets a caller that genuinely wants "the reveal refused" say so once.

    **The mutation this kills**: `UnknownRevealSubjectError = NotCareStaffError`,
    or `class UnknownRevealSubjectError(NotCareStaffError)`. Every `pytest.raises`
    in this module still passes under the second one, because the tests that care
    assert the *other* class is not what arrived — and this is where that
    distinction is established rather than assumed.
    """
    require_the_reveal_interface(care_service)
    _, not_care_staff, unknown_subject = reveal_and_refusals(care_service)

    assert unknown_subject is not not_care_staff, (
        f"`{UNKNOWN_SUBJECT_ERROR}` and `{NOT_CARE_STAFF_ERROR}` are the same class, so a caller "
        "cannot tell a refused actor from a refused subject by type at all."
    )
    assert not issubclass(unknown_subject, not_care_staff), (
        f"`{UNKNOWN_SUBJECT_ERROR}` is a subclass of `{NOT_CARE_STAFF_ERROR}`, so E10's queue "
        f"catching `{NOT_CARE_STAFF_ERROR}` silently catches this one too and reports 'you are not "
        "Care staff' to a Care officer who asked about the wrong record."
    )
    assert not issubclass(not_care_staff, unknown_subject), (
        f"`{NOT_CARE_STAFF_ERROR}` is a subclass of `{UNKNOWN_SUBJECT_ERROR}`, which is the same "
        "conflation in the other direction: a queue handling an unknown record would swallow the "
        "refusal that says the caller may not use this door."
    )


# ---------------------------------------------------------------------------
# Criterion 3 — the legitimate derivation, both directions of the boundary.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_the_reveal_answers_the_author_of_the_comment_it_was_given(
    care_service: Any, committed_rows: Any
) -> None:
    """Criterion 3: a subject reached through the record the ADR names still resolves.

    The accepted half of the boundary, and the control every refusal in this module
    leans on: §4 and §6.2 keep this door open on purpose — "traceability exists for
    safety" — and a wall satisfies every denial test there is.

    Two students are planted and the assertion names which one came back. A reveal
    that answered *any* identity would satisfy "it returned something"; what is
    asserted is that it returned the author of the comment it was handed, and that
    the other student's name and address are not in the answer.

    **The mutation this kills**: a derivation that reads `response.user_id` from
    the wrong response — the first one, the latest one, the one belonging to the
    actor — which returns a real student's real identity and audits a real access
    to the wrong person's data.
    """
    require_the_reveal_interface(care_service)
    reveal, _, _ = reveal_and_refusals(care_service)

    actor = the_two_hat_actor(committed_rows)
    planted = plant_a_comment_answer(committed_rows)
    somebody_else = plant_a_comment_answer(committed_rows)

    revealed = reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: planted.answer_id})

    returned = identity_values(revealed)
    assert planted.identity_name in returned, (
        f"`{REVEAL}` answered {revealed!r} for the comment {planted.comment_text!r}, whose author "
        f"was seeded as {sorted(planted.identity_values)}. §6.2's queue exists to name that "
        "student to Care staff acting on a real case, and a reveal that returns no identity is a "
        "wall with a handle painted on it."
    )
    assert not (somebody_else.identity_values & returned), (
        f"The reveal of one comment's author returned {sorted(somebody_else.identity_values & returned)}, "
        "which belongs to the *other* student planted by this test. The derivation reached the "
        "wrong response, so a Care officer acting on one case is shown a different student — and "
        "the audit row records an access that names them."
    )


@pytest.mark.invariant
def test_an_answer_id_that_names_no_comment_is_refused_rather_than_answered(
    care_service: Any, committed_rows: Any
) -> None:
    """The refused half of the same boundary, driven by the Care actor.

    The pair to the test above: same actor, same call, one thing different — an
    identifier that matches no `answer` row. The settled answer is
    `UnknownRevealSubjectError`, raised rather than an empty result, because
    `None` is already the answer to a different question (a derived author with no
    identity on file) and a queue cannot tell those two apart if they arrive the
    same way.

    **The mutation this kills**: returning `None` for an id that matches nothing.
    That implementation passes the legitimate path, passes the no-identity path,
    and quietly turns "there is no such record" into "this student has no name on
    file" — which is what a Care officer would then be told about a case they are
    working.
    """
    require_the_reveal_interface(care_service)
    reveal, _, unknown_subject = reveal_and_refusals(care_service)

    actor = the_two_hat_actor(committed_rows)
    planted = plant_a_comment_answer(committed_rows)

    allowed = reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: planted.answer_id})
    assert identity_values(allowed) & planted.identity_values, (
        "The control failed: the same actor could not reveal a planted comment's author, so the "
        "refusal below is not attributable to the identifier."
    )

    with pytest.raises(unknown_subject):
        reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: uuid4()})


@pytest.mark.invariant
def test_an_author_with_no_identity_on_file_comes_back_as_none_rather_than_as_a_refusal(
    care_service: Any, committed_rows: Any
) -> None:
    """`None` still means "this student has no identity row", and that is not an error.

    The work order preserves it: "`None` still means the derived author has no
    identity row". It survives this ticket because the case is real — the roster
    sync stores an address for a member it has no name for (ADR 0050), and a
    student who has never been through a door that records one has no row at all —
    and because §6.2's queue renders it as "no identity on file" rather than as a
    failure.

    **The control is the student who does have one**, planted and revealed in the
    same test: without it, "it returned `None`" is equally true of a reveal that
    returns `None` for everybody, which is the wall this whole door exists not to
    be (`docs/MISTAKES.md` entry 3).

    **The mutation this kills**: folding the empty result into
    `UnknownRevealSubjectError` — a tidy-looking simplification that collapses "no
    such record" and "no name on file" into one answer, which is the collapse
    `test_an_answer_id_that_names_no_comment_is_refused_rather_than_answered`
    guards from the other side.
    """
    require_the_reveal_interface(care_service)
    reveal, _, _ = reveal_and_refusals(care_service)

    actor = the_two_hat_actor(committed_rows)
    with_identity = plant_a_comment_answer(committed_rows)
    without_identity = plant_a_comment_answer(committed_rows, with_identity=False)

    control = reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: with_identity.answer_id})
    assert identity_values(control) & with_identity.identity_values, (
        "The control failed: a student who does have an identity row did not come back with it, "
        f"so `{REVEAL}` answering `None` below would say nothing about the student who has none."
    )

    revealed = reveal(
        **{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: without_identity.answer_id}
    )
    assert revealed is None, (
        f"`{REVEAL}` answered {revealed!r} for a comment whose author has no `user_identity` row "
        "at all. The settled answer is `None` — the queue renders that as 'no identity on file' — "
        "and anything else either invents an identity or turns a legitimate state into a failure."
    )


# ---------------------------------------------------------------------------
# Criterion 4 — the audit write is unchanged in grain and in content.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_the_audit_row_names_the_derived_author_and_not_anything_the_caller_supplied(
    care_service: Any, committed_rows: Any, migrated_engine: Any
) -> None:
    """Criterion 4: what is recorded about a reveal is unchanged — including who it was about.

    §4: "every identity access is automatically audit-logged with actor,
    timestamp, and case." This ticket narrows how a subject is *named*, so the one
    thing that could quietly change is the value in the subject column — and it is
    the value the monthly review outside the Care office reads to know which
    student was named.

    The three values it must not be are each asserted, because each is a plausible
    implementation slip and each looks like a working reveal from the caller's
    side: the actor (recording who asked twice over), the `answer_id` (recording
    the comment rather than its author, which is a foreign key into the wrong
    table), and `NULL` (a record of an access that names nobody).

    **The mutation this kills**: passing `answer_id` through to
    `record_identity_reveal`'s `in_subject_user_id` — the shape an implementation
    falls into when it derives the subject *after* recording, and one that leaves a
    perfectly plausible audit row behind.
    """
    require_the_reveal_interface(care_service)
    reveal, _, _ = reveal_and_refusals(care_service)

    actor = the_two_hat_actor(committed_rows)
    planted = plant_a_comment_answer(committed_rows)

    revealed = reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: planted.answer_id})
    assert identity_values(revealed) & planted.identity_values, (
        "The control failed: the reveal did not return the planted author, so the row read below "
        "is not the record of the access this test is about."
    )

    rows = audit_rows_for(migrated_engine, committed_rows, actor.person)
    assert len(rows) == 1, (
        f"One reveal left {len(rows)} audit rows for this actor: {rows}. §4's record is one row "
        "per authorization — E0-26 item 1 settles the grain — so more than one is a second write "
        "nobody sanctioned and none is the guarantee gone."
    )
    row = rows[0]
    assert row[AUDIT_SUBJECT_COLUMN] == planted.author_user_id, (
        f"The audit row names {row[AUDIT_SUBJECT_COLUMN]} as the student revealed; the comment's "
        f"author is {planted.author_user_id}. What was actually shown to the Care officer was that "
        "author's name and address, so the record and the access disagree about which student was "
        "identified — and the record is the only thing the review outside the Care office ever "
        "sees.\n\n"
        f"For orientation: the actor is {actor.person}, the comment is {planted.answer_id} and its "
        f"response is {planted.response_id}."
    )
    assert row[AUDIT_TIMESTAMP_COLUMN] is not None, (
        "The audit row carries no timestamp. §4 requires actor, timestamp and case, and §6.2's "
        "monthly review is over access records in time order."
    )


@pytest.mark.invariant
def test_the_audit_row_carries_the_case_the_caller_named_and_a_null_when_none_is_named(
    care_service: Any, committed_rows: Any, migrated_engine: Any
) -> None:
    """The case column stays nullable and stays the caller's — both directions.

    Criterion 3 asks for "the (still-nullable) case column" and criterion 4 for a
    write unchanged in grain. There is no case model until E10, so a reveal today
    ordinarily names none; E10's queue will name one, and the column has to carry
    it. Both directions are asserted in one test because a single direction is
    satisfied by an implementation that ignores the parameter entirely — a service
    that always wrote `NULL` passes the first half, and one that invented an id
    would pass the second.

    **The mutation this kills**: dropping `case_id` from the call to
    `record_identity_reveal` while keeping it in the signature, which is invisible
    to every other test here and would silently un-case every record E10 writes.
    """
    require_the_reveal_interface(care_service)
    reveal, _, _ = reveal_and_refusals(care_service)

    actor = the_two_hat_actor(committed_rows)
    uncased = plant_a_comment_answer(committed_rows)
    cased = plant_a_comment_answer(committed_rows)
    case = uuid4()

    reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: uncased.answer_id})
    reveal(
        **{
            ACTOR_PARAMETER: actor.person,
            ANSWER_PARAMETER: cased.answer_id,
            CASE_PARAMETER: case,
        }
    )

    rows = audit_rows_for(migrated_engine, committed_rows, actor.person)
    assert len(rows) == 2, (
        f"Two reveals left {len(rows)} audit rows for this actor: {rows}. One row per "
        "authorization is the grain this ticket must not change."
    )
    by_subject = {row[AUDIT_SUBJECT_COLUMN]: row for row in rows}
    assert set(by_subject) == {uncased.author_user_id, cased.author_user_id}, (
        f"The two rows name {sorted(map(str, by_subject))} as their subjects; the two comments' "
        f"authors are {uncased.author_user_id} and {cased.author_user_id}. Neither half below can "
        "be attributed to a call until each row is known to be the record of one."
    )
    assert by_subject[uncased.author_user_id][AUDIT_CASE_COLUMN] is None, (
        "A reveal made without naming a case recorded "
        f"{by_subject[uncased.author_user_id][AUDIT_CASE_COLUMN]!r} in the case column. There is "
        "no case model until E10 and the column is nullable for exactly that reason; a value here "
        "is a reference to a case that does not exist."
    )
    assert by_subject[cased.author_user_id][AUDIT_CASE_COLUMN] == case, (
        f"A reveal naming case {case} recorded "
        f"{by_subject[cased.author_user_id][AUDIT_CASE_COLUMN]!r}. §4 requires the record to carry "
        "the case, and §6.2's 'mark resolved' is reached from it — a record that drops the case "
        "the caller named is an access nobody can attach to the work it was done for."
    )
