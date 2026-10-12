"""An admin session ended by logout or by a switch is refused like an expired one.

SPEC §6.3 puts the people editor behind the admin role, and a session ended by
logout or by a switch is refused "with the same 401 an expired token gets"
(ADR 0089 for the carriers). Each refusal is compared with an expired admin
token's answer on the same route: status, body and challenge, not "some 401".
Each route is first shown to admit the same token while it is live, so a gate
that refused every admin would not pass.

The token rides the Bearer header, the carrier ADR 0089 exempts from the CSRF
check, so the write is refused by the session read and not by the CSRF gate.
"""

from typing import Any

import pytest
from fixtures.session_switch import (
    ADMIN,
    ADMIN_HAT,
    DEAN_HAT,
    LEADERSHIP,
    LOGGED_OUT,
    ROLE_MEMBER,
    SESSION_MEMBER,
    SESSION_REFUSED,
    SWITCHED,
    WEB,
    refusal_shape,
)

from app.services.people import PEOPLE_HEADER

pytestmark = pytest.mark.integration

READ_PATH = "/admin/people"
WRITE_PATH = "/admin/people/import/dry-run"
# A file of the header alone: the dry run answers an empty diff and changes nothing.
HEADER_ONLY = {"csv": ",".join(PEOPLE_HEADER) + "\n"}


def _read(world: Any, token: str) -> Any:
    return world.send("GET", READ_PATH, token=token)


def _write(world: Any, token: str) -> Any:
    return world.send("POST", WRITE_PATH, token=token, json=HEADER_ONLY)


def _admitted(world: Any, token: str) -> None:
    for ask, what in ((_read, "read"), (_write, "write")):
        answered = ask(world, token)
        assert answered.status_code == 200, (
            f"The admin {what} route answered a live admin session {answered.status_code}: "
            f"{answered.text[:300]!r}."
        )


def _refused_like_expired(world: Any, token: str, expired: str, how: str) -> None:
    for ask, what in ((_read, "read"), (_write, "write")):
        stale = ask(world, expired)
        assert (
            stale.status_code == SESSION_REFUSED
        ), f"The admin {what} route answered an expired token {stale.status_code}."
        ended = ask(world, token)
        assert refusal_shape(ended) == refusal_shape(stale), (
            f"After {how}, the admin {what} route answered {refusal_shape(ended)!r}; an expired "
            f"admin token gets {refusal_shape(stale)!r}."
        )


def test_after_logout_an_admin_token_is_refused_on_the_admin_routes(
    session_switch: Any,
) -> None:
    world = session_switch
    person = world.person(hats=(ADMIN_HAT,))
    token = world.mint(person, door=WEB, role=ADMIN)
    world.jti_of(token)
    _admitted(world, token)

    assert world.logout(token).status_code == LOGGED_OUT

    expired = world.expired(person, door=WEB, role=ADMIN)
    _refused_like_expired(world, token, expired, "logout")


def test_after_a_switch_away_the_old_admin_token_is_refused_on_the_admin_routes(
    session_switch: Any,
) -> None:
    world = session_switch
    person = world.person(hats=(ADMIN_HAT, DEAN_HAT))
    old = world.mint(person, door=WEB, role=ADMIN)
    world.jti_of(old)
    _admitted(world, old)

    switched = world.switch(old, LEADERSHIP)
    assert switched.status_code == SWITCHED, switched.text[:300]
    assert switched.json()[ROLE_MEMBER] == LEADERSHIP
    world.jti_of(switched.json()[SESSION_MEMBER])

    expired = world.expired(person, door=WEB, role=ADMIN)
    _refused_like_expired(world, old, expired, "a switch to leadership")
