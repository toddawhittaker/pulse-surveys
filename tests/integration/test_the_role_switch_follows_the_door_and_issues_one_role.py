"""E9-04 done-whens 1, 2 and 4 — the landings at a door, and the switch between them.

SPEC §2: "multi-role people get a role/assignment switcher", and "Care is
deliberately not composable with reporting roles". SPEC §2.1's door rules: the
instructor and student roles reach Pulse through a launch, Care and Admin through
the web login only, and leadership through both. The ticket turns those into
three routes; this module asks the first two.

**Everything is driven over HTTP against the built application**
(`docs/MISTAKES.md` entry 47): a gate's behaviour is what a request is answered
with, not what the route table says is attached.

**Every person's hats are written in the test that uses them**, through
`session_switch.person(hats=...)`, because which roles a door offers is the
question (`docs/MISTAKES.md` entry 30). The expected lists are written out here
too, from SPEC §2.1's door table and the settled precedence (leadership,
instructor, care, admin), never read off `LANDING_PRECEDENCE`
(`docs/MISTAKES.md` entry 19).

**Boundary pairs, both directions.** Each refusal sits beside a test where the
same request, one fact different, is admitted: Care refused at a launch beside
Care admitted at the web door, a revoked leadership hat beside a held one, a Care
session refused at the leadership route beside a leadership session admitted.
A route that refused everything would pass every refusal here, and the pairs are
what stop that reading.

**The door refusals that touch Care are marked `invariant`.** §6.2 makes the
Care queue the one surface that can re-identify a student, and §2.1 keeps it off
the launch door because the person who administers the LMS controls what a launch
says. Each marked test asserts its refusal in its own body
(`scripts/ci/check_invariant_assertions.py`).

**Predicted colour before E9-04:** every test that asks one of the new routes
fails on an assertion (the route answers 404). The control at the top passes and
must: a red control means this module's machinery is broken, not the code.
"""

from typing import Any

import pytest
from fixtures.session_switch import (
    ADMIN,
    ADMIN_HAT,
    CARE,
    CARE_HAT,
    CURRENT_MEMBER,
    DEAN_HAT,
    INSTRUCTOR,
    INSTRUCTOR_HAT,
    LANDINGS_MEMBER,
    LANDINGS_OK,
    LAUNCH,
    LEADERSHIP,
    ROLE_MEMBER,
    SESSION_MEMBER,
    SESSION_REFUSED,
    STUDENT,
    SWITCH_REFUSED,
    SWITCHED,
    UNKNOWN_ROLE,
    WEB,
    nothing_was_issued,
    refusal_shape,
    set_cookie_values,
    verified,
)
from fixtures.submit import externalized_key_for, session_cookie_names
from fixtures.web_identity import PERSON_ID_CLAIM, claims_in_session

pytestmark = pytest.mark.integration

# A role value that names no `LandingRole` member, for the 422 case.
A_ROLE_NOBODY_HAS = "e9-04-not-a-role"


# ---------------------------------------------------------------------------
# Readers.
# ---------------------------------------------------------------------------


def landings_of(answered: Any, what: str) -> tuple[Any, list[str]]:
    """The `current` role and the `landings` list one landings answer carries."""
    assert answered.status_code == LANDINGS_OK, (
        f"{what} answered {answered.status_code} rather than {LANDINGS_OK}. E9-04's landings route "
        f"is `GET /session/landings`. Body begins {answered.text[:300]!r}."
    )
    body = answered.json()
    assert isinstance(body, dict), f"{what} answered {body!r}, not a JSON object."
    landings = body.get(LANDINGS_MEMBER)
    assert isinstance(landings, list) and all(isinstance(entry, str) for entry in landings), (
        f"{what} carries `{LANDINGS_MEMBER}` = {landings!r}; the settled shape is a list of "
        "lowercased `LandingRole` names."
    )
    return body.get(CURRENT_MEMBER), landings


def switched_token(answered: Any, role: str, what: str) -> str:
    """The new token a successful switch answers with, after checking the answer's shape."""
    assert answered.status_code == SWITCHED, (
        f"{what} answered {answered.status_code} rather than {SWITCHED}. E9-04's switch is "
        f"`POST /session/switch` with `{{'role': ...}}`. Body begins {answered.text[:300]!r}."
    )
    body = answered.json()
    assert (
        isinstance(body, dict) and body.get(ROLE_MEMBER) == role
    ), f"{what} answered {body!r}; the settled body is `{{'role': {role!r}, 'session': <token>}}`."
    token = body.get(SESSION_MEMBER)
    assert (
        isinstance(token, str) and token
    ), f"{what} carries no `{SESSION_MEMBER}` token: {body!r}."
    return token


def the_refused_switch(world: Any, answered: Any, old_token: str, what: str) -> None:
    """A refused switch: 403, a registry sentence, nothing issued, and the old session alive."""
    assert answered.status_code == SWITCH_REFUSED, (
        f"{what} answered {answered.status_code} rather than {SWITCH_REFUSED}. Body begins "
        f"{answered.text[:300]!r}."
    )
    externalized_key_for(answered)
    nothing_was_issued(answered, what)
    still = world.landings(old_token)
    assert still.status_code == LANDINGS_OK, (
        f"After {what} was refused, the session it was asked from answered "
        f"{still.status_code} at the landings route. A refused switch leaves the old session "
        "working; only a switch that issues a new one revokes it."
    )


# ---------------------------------------------------------------------------
# The machinery, before anything is asserted with it. A must-be-green control.
# ---------------------------------------------------------------------------


def test_minted_sessions_are_admitted_by_their_route_kind_and_expired_ones_are_refused(
    session_switch: Any,
) -> None:
    """The control on every probe this ticket's tests lean on.

    Each route kind's gated read admits a freshly minted session in the role it
    gates (anything but 401), and refuses a correctly signed token for the same
    person and role that expired an hour ago (401). Every "the old token is
    refused" assertion in E9-04 compares a revoked token's answer with that
    expired token's, so both halves have to be true of today's tree first.

    **The mutations it kills:** a probe path that no longer exists or no longer
    gates by role (the first half would read 404 or 200 for any token, and the
    revocation tests would pass on it), and an expired-token mint that is not
    expired (the second half). **Needs no implementation and is green now. A red
    here means these tests are broken, not the code.**
    """
    world = session_switch
    teaching_assistant = world.person(hats=(INSTRUCTOR_HAT,), enrolled=True)
    two_hats = world.person(hats=(INSTRUCTOR_HAT, DEAN_HAT))
    cases = (
        (teaching_assistant, STUDENT),
        (two_hats, INSTRUCTOR),
        (two_hats, LEADERSHIP),
    )
    for person, role in cases:
        fresh = world.probe(role, world.mint(person, door=LAUNCH, role=role))
        assert fresh.status_code != SESSION_REFUSED, (
            f"A freshly minted {role} session was refused by the {role} route "
            f"({fresh.status_code}, {fresh.text[:200]!r}), so it cannot show a revoked session "
            "being refused."
        )
        stale = world.probe(role, world.expired(person, door=LAUNCH, role=role))
        assert (
            stale.status_code == SESSION_REFUSED
        ), f"An expired {role} token was answered {stale.status_code} by the {role} route."


# ---------------------------------------------------------------------------
# Done-when 1 — the landings follow the door.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_the_landings_at_the_launch_door_offer_instructor_and_leadership_and_never_care_or_admin(
    session_switch: Any,
) -> None:
    """Done-when 1, the launch half, on a person who holds all four assigned hats.

    > the landings route at the launch door lists their instructor and leadership
    > roles and no Care or Admin

    She holds `DEAN`, `INSTRUCTOR`, `CARE` and `ADMIN`, so the only thing that can
    keep Care and Admin off the list is the door. The expected list is SPEC
    §2.1's launch door in the settled order: leadership, then instructor.

    **The mutations it kills:** the door filter dropped (Care and Admin appear);
    the person's assignments read without `permits_launch`; the list built from
    every role the person holds anywhere. **Its pair** is the web-door test
    below, the same four hats, where Care and Admin must appear.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT, CARE_HAT, ADMIN_HAT))

    current, landings = landings_of(
        world.landings(world.mint(person, door=LAUNCH, role=LEADERSHIP)),
        "The landings asked from a launch session",
    )

    assert CARE not in landings and ADMIN not in landings, (
        f"A launch session was offered {landings}. SPEC §2.1: Care and Admin are web login only; "
        "the Care queue can re-identify a student (§6.2), and the LMS administrator controls what "
        "a launch says."
    )
    assert landings == [LEADERSHIP, INSTRUCTOR], (
        f"A launch session for a person holding a dean's and an instructor's assignment was "
        f"offered {landings}, not {[LEADERSHIP, INSTRUCTOR]} (every role held at this door, in "
        "the settled order)."
    )
    assert current == LEADERSHIP, f"`{CURRENT_MEMBER}` is {current!r} for a leadership session."


@pytest.mark.invariant
def test_the_landings_at_the_web_door_offer_leadership_care_and_admin_and_never_instructor_or_student(
    session_switch: Any,
) -> None:
    """Done-when 1, the web half: "leadership, and Care or Admin if held, and never instructor or student".

    The same four hats as above, and a live enrollment too, so the instructor
    and student landings are each one row away and only the door keeps them off.

    **The mutations it kills:** the door filter dropped (instructor appears);
    the enrollment fallback consulted at the web door (student appears); Care or
    Admin filtered at every door. **Its pair** is the launch test above.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT, CARE_HAT, ADMIN_HAT), enrolled=True)

    current, landings = landings_of(
        world.landings(world.mint(person, door=WEB, role=LEADERSHIP)),
        "The landings asked from a web session",
    )

    assert INSTRUCTOR not in landings and STUDENT not in landings, (
        f"A web session was offered {landings}. SPEC §2.1 gives the instructor and student roles "
        "the launch door only."
    )
    assert landings == [LEADERSHIP, CARE, ADMIN], (
        f"A web session for a person holding dean, instructor, Care and admin assignments was "
        f"offered {landings}, not {[LEADERSHIP, CARE, ADMIN]}."
    )
    assert current == LEADERSHIP, f"`{CURRENT_MEMBER}` is {current!r} for a leadership session."


def test_the_landings_at_the_web_door_offer_no_care_or_admin_to_a_person_who_holds_neither(
    session_switch: Any,
) -> None:
    """Done-when 1's "if held": the seeded two-hat person at the web door sees leadership alone.

    **The mutation it kills:** Care and Admin listed at the web door for
    everybody, which passes the four-hat test above. **The near miss it spares:**
    nothing; this person's instructor hat is the launch door's.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))

    _, landings = landings_of(
        world.landings(world.mint(person, door=WEB, role=LEADERSHIP)),
        "The two-hat person's landings at the web door",
    )

    assert landings == [
        LEADERSHIP
    ], f"The two-hat person was offered {landings} at the web door, not {[LEADERSHIP]}."


def test_the_landings_name_the_session_s_own_role_as_current(session_switch: Any) -> None:
    """The `current` member is the session's role, not the first landing in the list.

    The two-hat person's instructor session at a launch: the list is the same as
    for her leadership session, and `current` is `instructor`.

    **The mutation it kills:** `current` set to the first entry, or to the
    precedence's choice, which the leadership-session tests above cannot tell
    apart from the session's own role.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))

    current, landings = landings_of(
        world.landings(world.mint(person, door=LAUNCH, role=INSTRUCTOR)),
        "The two-hat person's landings from her instructor session",
    )

    assert current == INSTRUCTOR, f"`{CURRENT_MEMBER}` is {current!r}; the session is instructor."
    assert landings == [LEADERSHIP, INSTRUCTOR], f"The list is {landings}."


def test_the_landings_route_refuses_an_expired_session_as_the_student_gate_does(
    session_switch: Any,
) -> None:
    """The settled interface: a missing or bad session gets `require_student`'s 401, body and challenge.

    Asked twice, with an expired token and with no token at all, and each answer
    compared whole with the student route's answer to the same request.

    **The mutations it kills:** the landings route answering a refusal of its
    own shape (a 403, a body naming the reason), and the route left ungated (a
    200 for an expired token).
    """
    world = session_switch
    person = world.person(hats=(INSTRUCTOR_HAT,), enrolled=True)
    expired = world.expired(person, door=LAUNCH, role=STUDENT)

    for token, what in ((expired, "an expired token"), (None, "no session at all")):
        at_landings = world.landings(token)
        at_student = world.probe(STUDENT, token)
        assert at_student.status_code == SESSION_REFUSED, (
            f"The student route answered {at_student.status_code} to {what}; this comparison "
            "needs its 401."
        )
        assert refusal_shape(at_landings) == refusal_shape(at_student), (
            f"To {what}, the landings route answered {refusal_shape(at_landings)!r} and the "
            f"student route {refusal_shape(at_student)!r}. The settled interface gives the "
            "landings route `require_student`'s refusal: the same status, body and challenge."
        )


# ---------------------------------------------------------------------------
# Done-when 2 — a switch re-checks.
# ---------------------------------------------------------------------------


def test_a_switch_to_a_role_held_at_this_door_answers_a_new_session_in_that_role(
    session_switch: Any,
) -> None:
    """Done-when 2's accepting half: "answers a new session in that role".

    The two-hat person's instructor session at a launch switches to leadership.
    The answer is 200 with the new token; the token verifies, names leadership,
    the same door and the same person, and carries a new `jti`; the session and
    CSRF cookies are set, the session cookie to that token; and the new token is
    admitted by the leadership route.

    **The mutations it kills:** the old token handed back (same `jti`); the role
    in the body and the role in the token disagreeing; the door rewritten (a
    launch session switched into a web session); another person's session; no
    cookie set. **It is the pair** of every refusal below.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    old = world.mint(person, door=LAUNCH, role=INSTRUCTOR)

    answered = world.switch(old, LEADERSHIP)
    new = switched_token(answered, LEADERSHIP, "A switch from instructor to leadership")

    claims = verified(new, world.secret)
    world.jti_of(new)
    assert claims.role.name == LEADERSHIP.upper(), f"The new token names {claims.role!r}."
    assert (
        claims.door.name == LAUNCH
    ), f"The new token names door {claims.door!r}; it was asked from a launch session."
    assert str(claims.jti) != str(
        verified(old, world.secret).jti
    ), "The new token carries the old one's `jti`. A switch issues a new session."
    assert str(claims_in_session(new).get(PERSON_ID_CLAIM)) == str(person.person_id), (
        f"The new token names person {claims_in_session(new).get(PERSON_ID_CLAIM)!r}, not "
        f"{person.person_id!r}."
    )
    session_cookie, csrf_cookie = session_cookie_names()
    cookies = set_cookie_values(answered)
    assert cookies.get(session_cookie) == new, (
        f"The switch set `{session_cookie}` to {cookies.get(session_cookie)!r}, not to the new "
        "token it answered with."
    )
    assert cookies.get(csrf_cookie), f"The switch set no fresh `{csrf_cookie}`; it set {cookies}."
    assert (
        world.probe(LEADERSHIP, new).status_code != SESSION_REFUSED
    ), "The leadership route refused the leadership session the switch just issued."


def test_a_switch_to_a_role_the_person_does_not_hold_is_refused_and_issues_nothing(
    session_switch: Any,
) -> None:
    """Done-when 2: "A switch to a role they do not hold ... is refused and issues nothing".

    The two-hat person, at the web door, asks for admin, which she holds nowhere.

    **The mutations it kills:** a switch that trusts the requested role; one
    that checks only that the role is a `LandingRole`; and a refusal that sets
    a cookie or revokes the old session anyway.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    old = world.mint(person, door=WEB, role=LEADERSHIP)

    answered = world.switch(old, ADMIN)

    assert (
        answered.status_code == SWITCH_REFUSED
    ), f"A switch to a role the person does not hold answered {answered.status_code}."
    the_refused_switch(world, answered, old, "a switch to admin by a person holding no admin hat")


@pytest.mark.invariant
def test_a_launch_session_cannot_switch_into_care_held_only_at_the_web_door(
    session_switch: Any,
) -> None:
    """Done-when 2: "or held only at the other door", the direction §6.2 cares about.

    She holds a Care assignment, and asks for it from a launch session. SPEC
    §2.1 keeps Care off the launch door, so the switch re-reads her assignments
    *at this door* and finds none that lands on Care.

    **The mutations it kills:** the switch checking the role against every
    assignment the person holds, ignoring the door. **Its pair** is
    `test_a_care_session_issued_by_a_switch_reaches_no_leadership_or_instructor_route`
    below, where the same hat is switched into from the web door.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT, CARE_HAT))
    old = world.mint(person, door=LAUNCH, role=INSTRUCTOR)

    answered = world.switch(old, CARE)

    assert answered.status_code == SWITCH_REFUSED, (
        f"A launch session asking to switch into Care answered {answered.status_code}. SPEC §2.1 "
        "makes Care web login only; the Care queue is the one surface that can re-identify a "
        "student (§6.2)."
    )
    the_refused_switch(world, answered, old, "a switch into Care from a launch session")


def test_a_web_session_cannot_switch_into_instructor_held_only_at_the_launch_door(
    session_switch: Any,
) -> None:
    """Done-when 2's other door: an instructor hat does not reach the web door.

    **The mutation it kills:** the same door-blind check as above, which a
    Care-only test would not see if the filter were written as "no Care at a
    launch" rather than as the door's whole permission column.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    old = world.mint(person, door=WEB, role=LEADERSHIP)

    answered = world.switch(old, INSTRUCTOR)

    assert (
        answered.status_code == SWITCH_REFUSED
    ), f"A web session asking to switch into instructor answered {answered.status_code}."
    the_refused_switch(world, answered, old, "a switch into instructor from a web session")


def test_a_switch_after_the_assignment_was_revoked_since_listing_is_refused(
    session_switch: Any,
) -> None:
    """Done-when 2: "A switch after the assignment was revoked (between listing and switching)".

    The landings route lists leadership; her dean's assignment is then deleted
    (ruling 7: revoking an assignment deletes it); the switch to leadership is
    refused, because the switch re-reads the assignments when it is asked.

    **The mutations it kills:** a switch that trusts what the landings route
    answered earlier (a cached list, or a list carried in the session).
    **Its pair** is the accepting test above, identical but for the deletion.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    old = world.mint(person, door=LAUNCH, role=INSTRUCTOR)
    _, before = landings_of(world.landings(old), "The landings before the revocation")
    assert LEADERSHIP in before, (
        f"Before the revocation the landings were {before}, so there is nothing to revoke between "
        "listing and switching."
    )

    world.revoke_assignment(person, DEAN_HAT)
    answered = world.switch(old, LEADERSHIP)

    assert answered.status_code == SWITCH_REFUSED, (
        f"A switch to leadership after the dean's assignment was deleted answered "
        f"{answered.status_code}."
    )
    the_refused_switch(world, answered, old, "a switch to a role revoked since it was listed")


def test_a_switch_naming_no_role_is_unprocessable_and_issues_nothing(session_switch: Any) -> None:
    """The settled interface: a value that names no role gets FastAPI's 422.

    **The mutation it kills:** an unknown value mapped onto a default role, or
    onto the precedence's first choice, which would issue a session for a role
    nobody asked for.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    old = world.mint(person, door=LAUNCH, role=INSTRUCTOR)

    answered = world.switch(old, A_ROLE_NOBODY_HAS)

    assert answered.status_code == UNKNOWN_ROLE, (
        f"A switch to {A_ROLE_NOBODY_HAS!r} answered {answered.status_code} rather than "
        f"{UNKNOWN_ROLE}."
    )
    nothing_was_issued(answered, "a switch naming no role")


# ---------------------------------------------------------------------------
# Done-when 4 — one role per session.
# ---------------------------------------------------------------------------


def test_no_session_issued_by_a_switch_carries_two_roles(session_switch: Any) -> None:
    """Done-when 4: "No session issued by the switch carries two roles."

    A person holding leadership, Care and admin at the web door switches into
    each in turn. Each new token's `role` claim is one string naming the role
    asked for, and no other value in its claim set names another role she
    holds; each answer's body carries `role` and `session` and nothing else.

    **The mutations it kills:** a merged session (a `roles` list, or the old
    role carried beside the new one in another claim), and an answer body that
    lists several roles.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, CARE_HAT, ADMIN_HAT))
    held = {LEADERSHIP, CARE, ADMIN}
    token = world.mint(person, door=WEB, role=LEADERSHIP)

    for role in (CARE, ADMIN, LEADERSHIP):
        answered = world.switch(token, role)
        token = switched_token(answered, role, f"A switch into {role}")
        world.jti_of(token)
        assert set(answered.json()) == {ROLE_MEMBER, SESSION_MEMBER}, (
            f"The switch into {role} answered members {sorted(answered.json())}; the settled body "
            "is `role` and `session`."
        )
        claims = claims_in_session(token)
        assert isinstance(claims.get(ROLE_MEMBER), str), (
            f"The session issued into {role} carries `role` = {claims.get(ROLE_MEMBER)!r}, which "
            "is not one role."
        )
        assert (
            claims[ROLE_MEMBER].lower() == role
        ), f"The session issued into {role} names {claims[ROLE_MEMBER]!r}."
        others = held - {role}
        naming = sorted(
            f"{name}={value!r}"
            for name, value in claims.items()
            for entry in (value if isinstance(value, list) else [value])
            if isinstance(entry, str) and entry.lower() in others
        )
        assert not naming, (
            f"The session issued into {role} also names {naming}. SPEC §2: a session holds one "
            "role, and Care is never combined with a reporting role, nor Admin."
        )


@pytest.mark.invariant
def test_a_care_session_issued_by_a_switch_reaches_no_leadership_or_instructor_route(
    session_switch: Any,
) -> None:
    """Done-when 4: "a Care session issued by a switch reaches no leadership or instructor route".

    A person holding dean, instructor and Care switches from her web leadership
    session into Care; the Care session is refused (401) by the leadership route
    and by the instructor route. (The other half, "a leadership session reaches
    no Care route", waits for E10's Care routes: the ruling's second narrowing.)

    **The mutations it kills:** a switch that adds Care to the session rather
    than replacing the role, and a gate that admits a session by the person's
    assignments rather than by the session's role. **Its pair** is the next
    test, where the switch back into leadership is admitted.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT, CARE_HAT))
    old = world.mint(person, door=WEB, role=LEADERSHIP)

    care = switched_token(world.switch(old, CARE), CARE, "A switch into Care")
    world.jti_of(care)

    at_leadership = world.probe(LEADERSHIP, care)
    at_instructor = world.probe(INSTRUCTOR, care)
    assert at_leadership.status_code == SESSION_REFUSED, (
        f"A Care session issued by a switch was answered {at_leadership.status_code} by the "
        "leadership route. SPEC §2: Care is deliberately not composable with reporting roles."
    )
    assert at_instructor.status_code == SESSION_REFUSED, (
        f"A Care session issued by a switch was answered {at_instructor.status_code} by the "
        "instructor route."
    )


def test_a_leadership_session_issued_by_a_switch_reaches_the_leadership_route(
    session_switch: Any,
) -> None:
    """The pair to the Care refusal above: the switch back into leadership is admitted.

    **The mutation it kills:** a leadership route that refuses every session a
    switch issued, which would make the Care refusal above pass for the wrong
    reason.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT, CARE_HAT))
    old = world.mint(person, door=WEB, role=CARE)

    leadership = switched_token(world.switch(old, LEADERSHIP), LEADERSHIP, "A switch to leadership")
    world.jti_of(leadership)

    answered = world.probe(LEADERSHIP, leadership)
    assert answered.status_code != SESSION_REFUSED, (
        f"The leadership route refused a leadership session a switch issued "
        f"({answered.status_code}, {answered.text[:200]!r})."
    )
