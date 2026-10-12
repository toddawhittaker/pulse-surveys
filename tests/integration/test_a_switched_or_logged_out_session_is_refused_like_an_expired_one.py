"""E9-04 done-whens 3, 5, 6 and 8 — revocation, logout, the CSRF check, and the purge.

A session is a short-lived signed token that used to end only by expiring. E9-04
adds the `revoked_session` table: a switch revokes the old token's `jti`, logout
revokes the session's own, and `session_from_request` refuses a revoked `jti`
"with the same 401 an expired token gets". So every refusal here is asserted as
*equal to* an expired token's answer on the same route — the status, the body
and the challenge — and not as "some 401": a 401 for another reason (a role the
route does not admit, a malformed header) would pass a status check and say
nothing about revocation (`docs/MISTAKES.md` entry 3).

**Each revoked token is asked of the route that would admit it if it were not
revoked**: a student token at the student route, an instructor token at the
instructor route, a leadership token at the leadership route. Asked anywhere
else it would be refused by the role gate, and the test would pass with
revocation unbuilt. The control in the sibling module
(`test_minted_sessions_are_admitted_by_their_route_kind_and_expired_ones_are_refused`)
shows each probe admits a live token and refuses an expired one on today's tree.
The admin route kind waits for E9-06 (the ruling's first narrowing).

**The CSRF tests send the session as a cookie** (`docs/MISTAKES.md` entry 47:
over HTTP, against the built application). `_double_submit_verified` exempts a
Bearer header on purpose, so a CSRF test on that carrier passes against a route
that checks nothing.

**The purge is asked through `pulse_app`'s production connection**
(`application_session`, `docs/MISTAKES.md` entry 46): the table's grants are part
of what is under test, and the bootstrap superuser passes every grant.

**Predicted colour before E9-04:** every test fails on an assertion or on a
named missing deliverable (the routes answer 404; the table and the purge
function do not exist).
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fixtures.session_switch import (
    COOKIE,
    DEAN_HAT,
    INSTRUCTOR,
    INSTRUCTOR_HAT,
    LANDINGS_OK,
    LAUNCH,
    LEADERSHIP,
    LOGGED_OUT,
    PURGE_FUNCTION,
    ROLE_MEMBER,
    SESSION_MEMBER,
    SESSION_REFUSED,
    STUDENT,
    SWITCHED,
    is_a_clearing,
    nothing_was_issued,
    refusal_shape,
    require_revoked_session_table,
    session_function,
    set_cookie_headers,
    verified,
)
from fixtures.submit import CSRF_REFUSED_STATUS, csrf_token_for, session_cookie_names

pytestmark = pytest.mark.integration


def switched_away(world: Any, old: str, role: str) -> str:
    """Switch `old` into `role` over the Bearer carrier, requiring the 200, and return the new token."""
    answered = world.switch(old, role)
    assert answered.status_code == SWITCHED, (
        f"The switch into {role} answered {answered.status_code} rather than {SWITCHED}, so there "
        f"is no switched-away session to ask about. Body begins {answered.text[:300]!r}."
    )
    body = answered.json()
    assert (
        isinstance(body, dict) and body.get(ROLE_MEMBER) == role
    ), f"The switch answered {body!r}."
    new = body.get(SESSION_MEMBER)
    assert isinstance(new, str) and new, f"The switch carried no new token: {body!r}."
    world.jti_of(new)
    world.jti_of(old)
    return new


def assert_refused_like_expired(
    world: Any, *, ask: Any, token: str, expired: str, what: str
) -> None:
    """`ask(token)` answers exactly what `ask(expired)` answers, and that is a 401."""
    stale = ask(expired)
    assert stale.status_code == SESSION_REFUSED, (
        f"The expired token was answered {stale.status_code} on the route for {what}, so there is "
        "no expired-token answer to compare with."
    )
    revoked = ask(token)
    assert refusal_shape(revoked) == refusal_shape(stale), (
        f"{what}: the revoked token was answered {refusal_shape(revoked)!r}, and an expired token "
        f"for the same person and role {refusal_shape(stale)!r}. The ticket: "
        "`session_from_request` refuses a revoked id with the same 401 an expired token gets."
    )


# ---------------------------------------------------------------------------
# Done-when 3 — the old session ends.
# ---------------------------------------------------------------------------


def test_after_a_switch_the_old_student_token_is_refused_by_the_student_route(
    session_switch: Any,
) -> None:
    """Done-when 3, the student route kind.

    A teaching assistant (an instructor's assignment and a live enrollment)
    starts from her student session at a launch and switches to instructor. Her
    old student token is then answered by the student route exactly as an
    expired student token is.

    **The mutations it kills:** the switch not revoking the old `jti`; the
    revocation written and never read by `session_from_request`; a revoked id
    refused with a different status or body. **Its pair** is the control in the
    sibling module, where the same route admits a live student session.
    """
    world = session_switch
    person = world.person(hats=(INSTRUCTOR_HAT,), enrolled=True)
    old = world.mint(person, door=LAUNCH, role=STUDENT)
    assert (
        world.probe(STUDENT, old).status_code != SESSION_REFUSED
    ), "The student route refused the student session before any switch."

    switched_away(world, old, INSTRUCTOR)

    assert_refused_like_expired(
        world,
        ask=lambda token: world.probe(STUDENT, token),
        token=old,
        expired=world.expired(person, door=LAUNCH, role=STUDENT),
        what="the student route, after a switch away from student",
    )


def test_after_a_switch_the_old_instructor_token_is_refused_by_the_instructor_route(
    session_switch: Any,
) -> None:
    """Done-when 3, the instructor route kind: the two-hat person switches instructor to leadership.

    **The mutations it kills:** as above, on the instructor gate, which reads
    the session through its own dependency.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    old = world.mint(person, door=LAUNCH, role=INSTRUCTOR)
    assert (
        world.probe(INSTRUCTOR, old).status_code != SESSION_REFUSED
    ), "The instructor route refused the instructor session before any switch."

    switched_away(world, old, LEADERSHIP)

    assert_refused_like_expired(
        world,
        ask=lambda token: world.probe(INSTRUCTOR, token),
        token=old,
        expired=world.expired(person, door=LAUNCH, role=INSTRUCTOR),
        what="the instructor route, after a switch away from instructor",
    )


def test_after_a_switch_the_old_leadership_token_is_refused_by_the_leadership_route(
    session_switch: Any,
) -> None:
    """Done-when 3, the leadership route kind: the two-hat person switches leadership to instructor.

    **The mutations it kills:** as above, on the leadership gate.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    old = world.mint(person, door=LAUNCH, role=LEADERSHIP)
    assert (
        world.probe(LEADERSHIP, old).status_code != SESSION_REFUSED
    ), "The leadership route refused the leadership session before any switch."

    switched_away(world, old, INSTRUCTOR)

    assert_refused_like_expired(
        world,
        ask=lambda token: world.probe(LEADERSHIP, token),
        token=old,
        expired=world.expired(person, door=LAUNCH, role=LEADERSHIP),
        what="the leadership route, after a switch away from leadership",
    )


def test_after_a_switch_the_old_token_cannot_list_landings_or_switch_again(
    session_switch: Any,
) -> None:
    """Done-when 3 at E9-04's own routes: the landings route and the switch refuse the old token.

    Both read the session through the revocation-checked read (the landings
    route needs "any verified, unrevoked session"; the switch is gated by
    `csrf_verified_session`), so a switched-away token is answered at each
    exactly as an expired token is.

    **The mutations it kills:** the new routes reading the session through
    `verified_session` alone, which would let a revoked token switch again and
    mint a fresh session out of an ended one.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    old = world.mint(person, door=LAUNCH, role=INSTRUCTOR)
    switched_away(world, old, LEADERSHIP)
    expired = world.expired(person, door=LAUNCH, role=INSTRUCTOR)

    assert_refused_like_expired(
        world, ask=world.landings, token=old, expired=expired, what="the landings route"
    )
    assert_refused_like_expired(
        world,
        ask=lambda token: world.switch(token, LEADERSHIP),
        token=old,
        expired=expired,
        what="the switch route",
    )


# ---------------------------------------------------------------------------
# Done-when 5 — logout ends the session.
# ---------------------------------------------------------------------------


def test_after_logout_the_token_is_refused_like_an_expired_one(session_switch: Any) -> None:
    """Done-when 5: "After logout the token is refused".

    Logout answers 204 with no body; afterwards the token is answered by the
    leadership route and by the landings route exactly as an expired token is.

    **The mutations it kills:** a logout that clears the cookie and revokes
    nothing (the token, carried as a Bearer header, goes on working), and a
    revocation the session read never consults.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    token = world.mint(person, door=LAUNCH, role=LEADERSHIP)
    world.jti_of(token)
    assert (
        world.probe(LEADERSHIP, token).status_code != SESSION_REFUSED
    ), "The leadership route refused the session before logout."

    answered = world.logout(token)
    assert answered.status_code == LOGGED_OUT, (
        f"Logout answered {answered.status_code} rather than {LOGGED_OUT}. Body begins "
        f"{answered.text[:300]!r}."
    )
    assert answered.content == b"", f"Logout answered a body: {answered.text[:300]!r}."

    expired = world.expired(person, door=LAUNCH, role=LEADERSHIP)
    assert_refused_like_expired(
        world,
        ask=lambda candidate: world.probe(LEADERSHIP, candidate),
        token=token,
        expired=expired,
        what="the leadership route, after logout",
    )
    assert_refused_like_expired(
        world, ask=world.landings, token=token, expired=expired, what="the landings route"
    )


def test_logout_clears_the_session_cookie_and_the_csrf_cookie(session_switch: Any) -> None:
    """Done-when 5: "the cookie is cleared"; the settled interface clears both.

    **The mutations it kills:** a logout that revokes and leaves the cookies, so
    a browser carries a dead session and a CSRF token bound to it until they
    expire; and one that clears only the session cookie.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT,))
    token = world.mint(person, door=LAUNCH, role=LEADERSHIP)
    world.jti_of(token)

    answered = world.logout(token)

    session_cookie, csrf_cookie = session_cookie_names()
    headers = set_cookie_headers(answered)
    for name in (session_cookie, csrf_cookie):
        assert name in headers and is_a_clearing(headers[name]), (
            f"Logout answered {answered.status_code} with `Set-Cookie` {headers}, which does not "
            f"clear `{name}`."
        )


def test_a_second_logout_with_the_same_token_answers_as_the_first(session_switch: Any) -> None:
    """Done-when 5: "a second logout with the same token answers the same as the first without error".

    The settled interface reads logout's token with signature and expiry checks
    only, so a revoked token can still log out; the revocation is an insert that
    does nothing on conflict. Two logouts: the same status, the same body, the
    same cookies cleared, and one revocation row for the `jti`.

    **The mutations it kills:** logout reading the token through the
    revocation-checked read (the second call answers 401); a plain insert (the
    second call fails on the primary key); a second row for the same `jti`.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT,))
    token = world.mint(person, door=LAUNCH, role=LEADERSHIP)
    jti = world.jti_of(token)

    first = world.logout(token)
    second = world.logout(token)

    assert first.status_code == LOGGED_OUT, f"The first logout answered {first.status_code}."
    assert (second.status_code, second.content) == (first.status_code, first.content), (
        f"The second logout answered {second.status_code} {second.text[:200]!r}; the first "
        f"answered {first.status_code} {first.text[:200]!r}."
    )
    assert sorted(set_cookie_headers(second)) == sorted(set_cookie_headers(first)), (
        f"The two logouts set different cookies: {sorted(set_cookie_headers(first))} then "
        f"{sorted(set_cookie_headers(second))}."
    )
    rows = world.revocation_rows()
    assert jti in rows, f"After two logouts, `revoked_session` holds no row for `{jti}`."


def test_logout_with_no_session_answers_204_and_clears_the_cookies(session_switch: Any) -> None:
    """The settled interface: with no valid token at all, logout still answers 204 and clears.

    **The mutation it kills:** a logout that refuses a caller with no session,
    which strands a browser holding a cookie the server no longer accepts.
    """
    world = session_switch

    answered = world.logout(None)

    assert (
        answered.status_code == LOGGED_OUT
    ), f"Logout with no session answered {answered.status_code} rather than {LOGGED_OUT}."
    session_cookie, csrf_cookie = session_cookie_names()
    headers = set_cookie_headers(answered)
    for name in (session_cookie, csrf_cookie):
        assert name in headers and is_a_clearing(
            headers[name]
        ), f"Logout with no session set {headers}, which does not clear `{name}`."


def test_logout_ends_only_its_own_session(session_switch: Any) -> None:
    """Logout revokes the session's `jti`, not the person: a second session of hers survives.

    **The mutation it kills:** revocation keyed by person or subject rather than
    by `jti`, which is not what the table holds (it has no person column) and
    would end a session the person is still using elsewhere. **It is also the
    pair** of the logout refusal above: the same route admits a token logout did
    not name.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT,))
    ended = world.mint(person, door=LAUNCH, role=LEADERSHIP)
    other = world.mint(person, door=LAUNCH, role=LEADERSHIP)
    world.jti_of(ended)

    assert world.logout(ended).status_code == LOGGED_OUT, "Logout did not answer 204."

    still = world.probe(LEADERSHIP, other)
    assert still.status_code != SESSION_REFUSED, (
        f"Logging one session out ended another session of the same person "
        f"({still.status_code}). Logout revokes the session's own `jti`."
    )


# ---------------------------------------------------------------------------
# Done-when 6 — CSRF, over HTTP, on the cookie carrier.
# ---------------------------------------------------------------------------


def test_a_cookie_borne_switch_without_the_token_or_with_another_sessions_is_refused(
    session_switch: Any,
) -> None:
    """Done-when 6, the switch: refused without the double-submit token, and nothing happens.

    The session rides the cookie with no `Authorization` header. Asked with no
    CSRF pair, and with a genuine token bound to another session sent as the
    cookie and the header both: each is answered 403 (ADR 0114's CSRF status),
    issues nothing, and leaves the old session working.

    **The mutations it kills:** the switch route without `csrf_verified_session`
    (or with a member of the family that verifies nothing); a check comparing
    the cookie with the header rather than verifying against this session's
    `jti`; a refusal that still revokes the old session. **Its pair** is the next
    test.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    old = world.mint(person, door=LAUNCH, role=INSTRUCTOR)
    forged = csrf_token_for(world.mint(person, door=LAUNCH, role=INSTRUCTOR), world.secret)

    for csrf, how in ((None, "with no CSRF token"), (forged, "with another session's token")):
        answered = world.switch(old, LEADERSHIP, carrier=COOKIE, csrf=csrf)
        assert answered.status_code == CSRF_REFUSED_STATUS, (
            f"A cookie-borne switch {how} answered {answered.status_code} rather than "
            f"{CSRF_REFUSED_STATUS}. Body begins {answered.text[:300]!r}."
        )
        nothing_was_issued(answered, f"a cookie-borne switch {how}")
    assert world.landings(old).status_code == LANDINGS_OK, (
        "After two refused cookie-borne switches the old session no longer works; a refusal "
        "revoked it."
    )


def test_a_cookie_borne_switch_carrying_the_bound_token_is_admitted(session_switch: Any) -> None:
    """The pair to the refusal above: the same request with this session's token switches.

    **The mutation it kills:** a switch route that refuses every cookie-borne
    request, which passes the refusal above and breaks the browser's fallback.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    old = world.mint(person, door=LAUNCH, role=INSTRUCTOR)
    world.jti_of(old)

    answered = world.switch(old, LEADERSHIP, carrier=COOKIE)

    assert answered.status_code == SWITCHED, (
        f"A cookie-borne switch carrying its own CSRF token answered {answered.status_code}. "
        f"Body begins {answered.text[:300]!r}."
    )
    world.jti_of(answered.json()[SESSION_MEMBER])


def test_a_cookie_borne_logout_without_the_token_or_with_another_sessions_is_refused(
    session_switch: Any,
) -> None:
    """Done-when 6, logout: a cookie-borne logout with no token, or another session's, is refused.

    The settled interface applies the double-submit check when the session
    arrives by cookie. Without it, another site could end a person's session by
    making her browser post to the logout route. Each refusal answers 403 and
    the session goes on working.

    **The mutations it kills:** logout with no CSRF check at all; a check that
    tests presence or compares the two halves; a refusal that revokes anyway.
    **Its pair** is the next test.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT,))
    token = world.mint(person, door=LAUNCH, role=LEADERSHIP)
    world.jti_of(token)
    forged = csrf_token_for(world.mint(person, door=LAUNCH, role=LEADERSHIP), world.secret)

    for csrf, how in ((None, "with no CSRF token"), (forged, "with another session's token")):
        answered = world.logout(token, carrier=COOKIE, csrf=csrf)
        assert answered.status_code == CSRF_REFUSED_STATUS, (
            f"A cookie-borne logout {how} answered {answered.status_code} rather than "
            f"{CSRF_REFUSED_STATUS}."
        )
    still = world.probe(LEADERSHIP, token)
    assert (
        still.status_code != SESSION_REFUSED
    ), "After two refused cookie-borne logouts the session no longer works; a refusal revoked it."


def test_a_cookie_borne_logout_carrying_the_bound_token_ends_the_session(
    session_switch: Any,
) -> None:
    """The pair to the refusal above: with this session's own token, logout answers 204 and ends it.

    **The mutation it kills:** a logout that refuses every cookie-borne request,
    which passes the refusal above and leaves the browser's own logout broken.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT,))
    token = world.mint(person, door=LAUNCH, role=LEADERSHIP)
    world.jti_of(token)

    answered = world.logout(token, carrier=COOKIE)

    assert (
        answered.status_code == LOGGED_OUT
    ), f"A cookie-borne logout carrying its own CSRF token answered {answered.status_code}."
    assert (
        world.probe(LEADERSHIP, token).status_code == SESSION_REFUSED
    ), "The session still works after a cookie-borne logout that answered 204."


# ---------------------------------------------------------------------------
# Done-when 8 — revocations purge.
# ---------------------------------------------------------------------------

# The instant the purge is handed. Far from the real clock on purpose: a purge
# that read the clock instead of `now` keeps both rows below (they expire in 2100),
# so the deletion assertion can only pass if `now` is what was compared.
PURGE_NOW = datetime(2100, 1, 1, tzinfo=UTC)
ONE_SECOND = timedelta(seconds=1)


def test_the_purge_deletes_a_revocation_past_its_expiry_and_keeps_one_before_it(
    session_switch: Any, application_session: Any
) -> None:
    """Done-when 8: "A revoked id past its token's expiry is deleted by the purge; one before it is kept."

    Three rows: one that expired a second before `now`, one that expires at
    `now` exactly, one a second after. The settled purge deletes `expires_at <
    now`, so one row goes and two stay, and it answers how many it deleted. It is
    called over `pulse_app`'s production connection, so a missing grant on the
    new table fails here (`docs/MISTAKES.md` entry 46).

    **The mutations it kills:** a purge that deletes nothing, or everything; `<`
    written `<=` (the row at `now` goes); a purge that reads the clock rather
    than `now` (nothing goes, since every row expires in 2100); and a missing
    `DELETE` grant to `pulse_app`.
    """
    world = session_switch
    require_revoked_session_table(world.rows.session)
    purge = session_function(PURGE_FUNCTION)
    past, edge, future = (f"e9-04-purge-{which}-{uuid4()}" for which in ("past", "edge", "future"))
    world.plant_revocation(past, PURGE_NOW - ONE_SECOND)
    world.plant_revocation(edge, PURGE_NOW)
    world.plant_revocation(future, PURGE_NOW + ONE_SECOND)

    deleted = purge(application_session, PURGE_NOW)
    application_session.commit()

    remaining = world.revocation_rows()
    assert (
        past not in remaining
    ), f"The revocation that expired a second before {PURGE_NOW} survived the purge."
    assert edge in remaining and future in remaining, (
        f"The purge deleted a revocation whose token had not expired before {PURGE_NOW}: of "
        f"`{edge}` (at it) and `{future}` (after it), {sorted({edge, future} - set(remaining))} "
        "are gone. A revoked token is refused until its own expiry."
    )
    assert deleted == 1, f"The purge answered {deleted!r}; it deleted one row."


def test_a_logout_purges_expired_revocations_and_records_its_own_until_the_token_expires(
    session_switch: Any,
) -> None:
    """The ticket: the table "holds revoked session ids until their tokens' own expiry, and purges rows past it".

    The settled interface has `revoke_session` delete expired rows in the same
    transaction, so the table purges itself with no job. One row planted as
    expired in 2000 and one live until 2100; a logout then revokes a session.
    Afterwards the 2000 row is gone, the 2100 row stays, and the logged-out
    `jti` has a row whose `expires_at` is its token's own `exp`.

    **The mutations it kills:** a revocation that never purges (the table grows
    for ever); one that purges live rows; and an `expires_at` that is the
    revocation time, or a fixed horizon, rather than the token's expiry.
    """
    world = session_switch
    require_revoked_session_table(world.rows.session)
    stale = f"e9-04-stale-{uuid4()}"
    live = f"e9-04-live-{uuid4()}"
    world.plant_revocation(stale, datetime(2000, 1, 1, tzinfo=UTC))
    world.plant_revocation(live, datetime(2100, 1, 1, tzinfo=UTC))
    person = world.person(hats=(DEAN_HAT,))
    token = world.mint(person, door=LAUNCH, role=LEADERSHIP)
    jti = world.jti_of(token)

    assert world.logout(token).status_code == LOGGED_OUT, "Logout did not answer 204."

    rows = world.revocation_rows()
    assert stale not in rows, "A revocation that expired in 2000 survived a later revocation."
    assert live in rows, "A revocation live until 2100 was deleted by a later revocation."
    assert jti in rows, f"Logout left no `revoked_session` row for `{jti}`."
    expected = verified(token, world.secret).exp
    assert int(rows[jti].timestamp()) == int(expected), (
        f"The logged-out session's row expires at {rows[jti]!r}; its token expires at epoch "
        f"{expected}. A revocation is held until the token's own expiry."
    )
