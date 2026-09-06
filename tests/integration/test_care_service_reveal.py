"""The Care service's own check on the acting person — ticket E0-10.

E0-10 settles a design its first draft left contradictory, and the sentence is
the whole subject of this module:

> The `SECURITY DEFINER` function **takes the acting person as an argument and
> verifies a live `CARE` assignment itself**, and `services/safety.py` verifies
> independently before calling it. Neither alone; a caller reaching the function
> by any other route still gets nothing, and a routing mistake inside the service
> still gets nothing.

The function's half is asserted against the database, with no service anywhere in
the picture, in `test_identity_grants.py`. **This is the service's half.**

**The two halves are told apart by the *type* of the refusal.** The service
raises `NotCareStaffError`; the function raises a database error. So a service
that skipped its own check and let the function's refusal surface fails the test
below with a different exception and a different message. The one case this
cannot separate is a service that catches the database error and re-raises
`NotCareStaffError` — the two checks then look identical from here, and the pull
request owes a sentence saying which it did (`docs/MISTAKES.md` entry 14: this is
the boundary of the search, not a proof).

**E4-01 moved these three tests onto a new signature, and this paragraph is why
the assertions still mean what they meant.** `reveal_identity` no longer takes a
`subject_user_id`: it takes the identifier of a comment and derives the author
server-side (`answer_id` → `answer.response_id` → `response.user_id`), because
the carried entry "The reveal's actor check and an instructor's read scope
compose" records that the old parameter was exactly the key `section_roster`
hands an instructor-scoped caller. Nothing about *this* module's subject changed
— it is still the service's own actor check, still asserted by the type of the
refusal — but the student it asks about is now reached through a planted comment
rather than named directly, so the fixture plants one. The **guessing machinery
is gone with the change**: this module used to bind arguments by matching
parameter names against fragments, because E0-10 spelled no signature and a test
that guessed one would have settled an interface the ticket left open. E4-01
spells all three parameters, so the calls are written out, exactly as E0-26 item
1's ticket let `test_identity_grants.py` stop guessing at the database door's.

**What E4-01's own criteria are asserted by, and it is not this module.**
`tests/integration/test_the_reveal_derives_its_subject.py` holds the derivation,
the two-hat composition, the audit row's subject and the second refusal
(`UnknownRevealSubjectError`). The line between the two: **this module asks
whether the service's actor check holds; that one asks where the subject comes
from.** A test about a roster key, an unknown record, or which of the two guards
refused belongs there.

**Why this module needs machinery no other database test needs.** ADR 0001 binds
the Care pool to the service module rather than to the actor, so
`app.services.safety` opens its own connection from `CARE_DATABASE_URL` — and it
therefore cannot see a single row written inside `db_session`'s transaction. The
rows have to be committed, which is `committed_rows` in
`tests/fixtures/authz_data.py`, and the environment has to point at this
container, which is `care_service_environment` beside it. Both undo themselves:
the teardown removes whatever *appeared*, including the audit row the service
writes on its own connection, which nothing on this side could have tracked by
key.

**Nothing here reaches for a private name.** `_care_engine`, `_care_sessions` and
`_care_session` are private because a caller may never choose its own pool, and a
test that imported one to make itself easier would be asserting the opposite of
the rule it is here to check. The public surface — `reveal_identity`,
`NotCareStaffError`, `UnknownRevealSubjectError`, `RevealedIdentity` — is the
whole interface this module uses, and
`tests/unit/test_care_session_is_bound_to_the_care_service.py` is what holds the
line between the two.
"""

from typing import Any

import pytest
from fixtures.care_subject import (
    ACTOR_PARAMETER,
    ANSWER_PARAMETER,
    NOT_CARE_STAFF_ERROR,
    REVEAL,
    PlantedAnswer,
    TwoHatActor,
    identity_values,
    plant_a_comment_answer,
    require_the_reveal_interface,
    the_two_hat_actor,
)

pytestmark = pytest.mark.integration


def a_planted_comment_and_the_two_hat_actor(
    committed_rows: Any,
) -> tuple[TwoHatActor, PlantedAnswer]:
    """A comment to ask about, a Care staffer who may, and a lead who may not.

    Committed, because the service reads on its own connection and would otherwise
    be asked about a comment that, from where it is standing, does not exist.

    The Care staffer is E0-09's two-hat person — a `CARE` assignment and a
    teaching assignment on one person, which §2.1 permits and §6.2 spends a
    paragraph on — so the positive case below is the awkward one rather than the
    easy one.

    **A plain helper called from the test body rather than a fixture.** Every red
    in a tests-first module has to be a FAILED and not an ERROR at setup
    (`docs/MISTAKES.md` entry 44), and both of these seed against an interface
    E4-01 has not landed yet.
    """
    return the_two_hat_actor(committed_rows), plant_a_comment_answer(committed_rows)


@pytest.mark.invariant
def test_the_care_service_reveals_identity_to_a_person_holding_a_care_assignment(
    care_service: Any, committed_rows: Any
) -> None:
    """The door is open through the service, for the person §6.2 opens it for.

    **Marked `invariant` by E0-41.** SPEC §4 makes `reveal_identity` the single
    application-code path to a student's name — "re-identification is possible
    only through the Care queue (§6.2), only by the Care role" — and the isolated
    §4.1 pass ran none of it. This half is in that pass because the refusal beside
    it is worth nothing without it: a service that raised `NotCareStaffError` for
    everybody, or one that could not reach its own connection, satisfies the
    refusal perfectly, and inside the isolated pass the control would not even
    have been collected.

    This is the positive half of the pair, and it is a criterion in its own right
    — "the Care path must remain open, and this ticket proves it" — as well as
    the control that makes the refusal next door mean something.

    The returned object is compared against the identity that was seeded rather
    than merely being non-empty: a reveal that returns a row of nulls, or the
    user's key back, satisfies "it returned something" and reveals nobody.

    **The person here holds two hats**, a `CARE` assignment and a teaching one.
    §2.1 permits it and §6.2 expects it, and it is the case where "pick the pool
    from the actor's role" has no answer — so the service has to say yes to them
    *for their Care assignment* while every reporting path they touch stays on
    `pulse_app`.

    **What this does not assert, since E4-01**: that the identity returned is the
    author of *that* comment rather than of some other one. That is the
    derivation, and it is asserted where the derivation is —
    `test_the_reveal_derives_its_subject.py::test_the_reveal_answers_the_author_of_the_comment_it_was_given`
    plants two students and names which came back. Here the subject is a way of
    reaching a real identity, and the assertion is about the door.
    """
    require_the_reveal_interface(care_service)
    reveal = getattr(care_service, REVEAL)
    actor, planted = a_planted_comment_and_the_two_hat_actor(committed_rows)

    result = reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: planted.answer_id})

    assert identity_values(result) & planted.identity_values, (
        f"`{REVEAL}` returned {result!r} for a person holding a live `CARE` assignment, asking "
        f"about a comment whose author carries {sorted(planted.identity_values)}. E0-10 ships this "
        "as the proof that Care re-identification works before E10 replaces the stub — 'so that "
        "E10 inherits a door rather than a wall'. A reveal that returns no identity is a wall with "
        "a handle painted on it.\n\n"
        f"The comment was {planted.comment_text!r} on response {planted.response_id}, whose "
        f"`user_id` is {planted.author_user_id}."
    )


@pytest.mark.invariant
def test_the_care_service_refuses_a_person_with_no_live_care_assignment(
    care_service: Any, committed_rows: Any
) -> None:
    """The service's own check, which has to hold when the routing is wrong.

    **Marked `invariant` by E0-41**: this is §4's "identity is never displayed to
    instructors or any leadership role" at the one door that can display it, and
    the `holds_care` pre-check is the whole of the service's half. Unmarked, it
    could be skipped without the isolated pass noticing.

    E0-10: "`services/safety.py` verifies independently before calling it…
    Neither alone; a caller reaching the function by any other route still gets
    nothing, and a routing mistake inside the service still gets nothing." This
    is the second clause. The actor is a real person in the same graph holding a
    lead-faculty assignment and no Care assignment — the shape of a routing
    mistake, where the Care code path is reached on behalf of somebody who should
    never have been sent there.

    **The control runs first, in this test, with the same call.** The same
    arguments and the same service, differing only in which person is acting, so
    the refusal is attributable to the assignment rather than to a service that
    cannot reach the database, a wrong binding, or a fixture that seeded nothing.

    **The exception type is the assertion**, and nothing follows the `raises`
    block on purpose: `refused.value is not None` is the obvious next line and it
    cannot fail, which is `docs/MISTAKES.md` entry 3 in the shape that reads as
    thoroughness. What the refusal *carries* is asserted next door in
    `test_the_refusal_carries_no_part_of_the_students_identity`; **which of E4-01's
    two guards refused** is asserted in
    `test_the_reveal_derives_its_subject.py::test_a_person_with_no_care_assignment_is_refused_by_the_actor_check`,
    which is that ticket's criterion and not this one's. `NotCareStaffError` is
    the service's own refusal; the function's refusal is a database error. A
    service that skipped its check and let the function speak fails here, and
    fails saying what it raised instead.
    """
    require_the_reveal_interface(care_service)
    reveal = getattr(care_service, REVEAL)
    refusal_type = getattr(care_service, NOT_CARE_STAFF_ERROR)
    actor, planted = a_planted_comment_and_the_two_hat_actor(committed_rows)

    allowed = reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: planted.answer_id})
    assert identity_values(allowed) & planted.identity_values, (
        "The control call failed: a person holding a live `CARE` assignment did not get the "
        "seeded identity back, so the refusal below would say nothing about the assignment. "
        "`test_the_care_service_reveals_identity_to_a_person_holding_a_care_assignment` is where "
        "that is diagnosed."
    )

    with pytest.raises(refusal_type):
        reveal(**{ACTOR_PARAMETER: actor.reporting_person, ANSWER_PARAMETER: planted.answer_id})


def raised_surface(failure: BaseException) -> str:
    """Everything a caller can read off a refusal: its text, its arguments, its chain.

    The chain matters as much as the message. A service that let the database's
    own error become the `__cause__` of its refusal hands the caller whatever that
    error quoted — and a Postgres error quotes the row it was raised about — so a
    scan of `str(failure)` alone would report a clean refusal over a leaked name.
    """
    seen: list[str] = []
    current: BaseException | None = failure
    while current is not None and len(seen) < 10:
        seen.append(f"{type(current).__name__}: {current!s} {current.args!r}")
        current = current.__cause__ or current.__context__
    return "\n".join(seen)


@pytest.mark.invariant
def test_the_refusal_carries_no_part_of_the_students_identity(
    care_service: Any, committed_rows: Any
) -> None:
    """A refusal that quotes the student has revealed them while saying no — E0-41.

    SPEC §4: identity "is never displayed to instructors or any leadership role,
    in any view", and §6.2 keeps re-identification to the Care role "only via the
    audited reveal action". A `NotCareStaffError` that reads "Alex Rivera may not
    be revealed to …" has performed the reveal on the error path, where nothing is
    audited: §4's traceability record is written by the reveal, and this call did
    not get that far.

    **The mutation this kills:** a refusal built from the row the service had
    already fetched — the natural shape when a service reads the subject first and
    checks the actor second, and equally the shape of a service that lets the
    database error surface as its `__cause__`. **E4-01 makes that shape more
    likely rather than less**, which is why this test matters more after it than
    before: the service now has a derivation step that reaches the student's row,
    and an implementation that ran it before the actor check would have the name
    in hand at the moment it refuses.

    **Why this is not an assertion about emptiness.** The denial itself is
    asserted next door and is what makes this meaningful; here the seeded identity
    is known, the control call proves the reveal really can produce it, and the
    scan is shown finding those very strings in a sample built from them. Without
    those three, "the message did not contain a name" would be equally true of a
    service that never ran (`docs/MISTAKES.md` entry 3).
    """
    require_the_reveal_interface(care_service)
    reveal = getattr(care_service, REVEAL)
    refusal_type = getattr(care_service, NOT_CARE_STAFF_ERROR)
    actor, planted = a_planted_comment_and_the_two_hat_actor(committed_rows)

    allowed = reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: planted.answer_id})
    assert identity_values(allowed) & planted.identity_values, (
        "The control call failed: a person holding a live `CARE` assignment did not get the "
        "seeded identity back, so this test does not yet know that the values it is scanning for "
        "are ones this door can produce at all."
    )
    canary = " ".join(sorted(planted.identity_values))
    assert all(value in canary for value in planted.identity_values), (
        "The scan below cannot find the seeded identity in a sample built out of it, so its "
        "silence about the refusal means nothing."
    )

    with pytest.raises(refusal_type) as refused:
        reveal(**{ACTOR_PARAMETER: actor.reporting_person, ANSWER_PARAMETER: planted.answer_id})

    surface = raised_surface(refused.value)
    leaked = sorted({value for value in planted.identity_values if value in surface})
    assert not leaked, (
        f"The refusal handed back to a person with no `CARE` assignment carries {leaked}, which is "
        f"the identity it refused to reveal. What it carries:\n{surface}\n\n"
        "§6.2 gives identity access to the Care role and to no other, through the audited reveal "
        "and no other route — and this path writes no audit record, because the check that "
        "produced this error is what stops the reveal happening. A refusal that quotes the student "
        "has revealed them to exactly the person the check exists to refuse."
    )
