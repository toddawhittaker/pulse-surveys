"""E9-04 fix round 1, rulings G1 and G2 — a switch is not a refresh, and a token switches once.

**G1.** Before this round every switch issued a fresh sixty-minute token, and a
switch to the role already held was allowed, so `/session/switch` was an endless
refresh: a stolen token, or an access the LMS or identity provider had ended,
could be kept alive for ever. The ruling: (a) the switched token keeps the old
token's `exp` exactly (`issue_session` gains a keyword-only `expires_at`, and
`iat` is still now); (b) a switch to the session's own role is refused with the
same 403 and copy as any other refused switch, issuing and revoking nothing.

**Every old token here is minted twenty minutes in the past**, so its `exp` is
forty minutes away while a freshly issued token's would be sixty. A token minted
now would carry the same `exp` as a fresh one to the second, and a test comparing
the two would pass against the defect (`docs/MISTAKES.md` entry 3).

**G2.** Two switches running at the same time with one old token both succeeded,
so one token became two live sessions. The ruling: the switch's revocation insert
is `ON CONFLICT DO NOTHING RETURNING jti`, in the same transaction as the issue;
no row back means the token was already spent, and the switch answers the
expired-token 401 and issues nothing.

The race is posed with two connections. "Switch A" is a transaction this test
opens on its own connection, which inserts the old token's revocation row and
holds the transaction open: the state switch A is in after revoking and before
committing. "Switch B" is a real switch over HTTP, sent from a worker thread; its
insert has to wait on A's uncommitted row. A then commits, and B must answer the
401. **Every wait is bounded**: B's blocking is polled for in `pg_stat_activity`
for at most `BLOCK_WAIT_SECONDS`, and B's answer is awaited for at most
`ANSWER_WAIT_SECONDS`. A's transaction is ended in a `finally`, so a failing test
never leaves B blocked behind it. **The pair** rolls A back instead, and B must
then switch: a switch that refused whenever it had waited on a lock would pass
the first test alone.

**Predicted colour on 72564c10:** the G1 tests fail on an assertion (the new
`exp` is sixty minutes out; a same-role switch answers 200). The G2 race test
fails on an assertion (B answers 200 with a token, or a 500 from a plain insert).
The G2 pair is expected to pass already, and must stay passing.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, datetime
from typing import Any

import pytest
from fixtures.session_switch import (
    COOKIE,
    DEAN_HAT,
    INSTRUCTOR,
    INSTRUCTOR_HAT,
    LANDINGS_OK,
    LAUNCH,
    LEADERSHIP,
    ROLE_MEMBER,
    SESSION_MEMBER,
    SESSION_REFUSED,
    SWITCH_REFUSED,
    SWITCHED,
    nothing_was_issued,
    refusal_shape,
    require_revoked_session_table,
    verified,
)
from fixtures.submit import externalized_key_for

pytestmark = pytest.mark.integration

# How far in the past every old token here is minted. Twenty minutes inside a
# sixty-minute lifetime: still live, and its `exp` is twenty minutes short of a
# fresh token's.
MINTED_AGO_SECONDS = 20 * 60

# The bounded waits for the race. Blocking is a lock wait inside one Postgres
# statement, so it shows within milliseconds; ten seconds is generous without
# letting a hang stall the suite.
BLOCK_WAIT_SECONDS = 10.0
ANSWER_WAIT_SECONDS = 15.0
POLL_SECONDS = 0.05

# The statement switch A runs before holding its transaction open, and the probe
# that sees switch B waiting on it. Written out whole, with the settled names.
REVOKE_AS_SWITCH_A = "INSERT INTO revoked_session (jti, expires_at) VALUES (:jti, :expires_at)"
CLEAR_THE_STATISTICS_SNAPSHOT = "SELECT pg_stat_clear_snapshot()"
SESSIONS_WAITING_ON_A_LOCK = (
    "SELECT count(*) FROM pg_stat_activity "
    "WHERE wait_event_type = 'Lock' AND datname = current_database() AND pid <> pg_backend_pid()"
)


def an_old_token(world: Any, person: Any, role: str) -> str:
    """A live token for `person` in `role`, minted `MINTED_AGO_SECONDS` ago, its `jti` recorded."""
    token = world.mint(person, door=LAUNCH, role=role, now=int(time.time()) - MINTED_AGO_SECONDS)
    world.jti_of(token)
    return token


def new_token_of(world: Any, answered: Any, role: str, what: str) -> str:
    """The token a successful switch answers with."""
    assert answered.status_code == SWITCHED, (
        f"{what} answered {answered.status_code} rather than {SWITCHED}. Body begins "
        f"{answered.text[:300]!r}."
    )
    body = answered.json()
    assert isinstance(body, dict) and body.get(ROLE_MEMBER) == role, f"{what} answered {body!r}."
    token = body.get(SESSION_MEMBER)
    assert isinstance(token, str) and token, f"{what} carried no token: {body!r}."
    world.jti_of(token)
    return token


# ---------------------------------------------------------------------------
# G1 (a) — the switched token keeps the old token's expiry.
# ---------------------------------------------------------------------------


def test_a_bearer_switch_keeps_the_old_tokens_expiry_and_stamps_a_new_issue_time(
    session_switch: Any,
) -> None:
    """G1 (a), the Bearer path: the new token's `exp` is the old one's exactly; its `iat` is now.

    **The mutations it kills:** the switch issuing a fresh lifetime (the `exp`
    moves forty minutes to sixty); `expires_at` ignored by `issue_session`;
    `switch_session` passing anything but `claims.exp`; and `iat` copied from
    the old token along with `exp` (the near miss: the ruling keeps `iat` as now).
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    old = an_old_token(world, person, INSTRUCTOR)
    before = verified(old, world.secret)

    new = new_token_of(world, world.switch(old, LEADERSHIP), LEADERSHIP, "A Bearer switch")
    after = verified(new, world.secret)

    assert int(after.exp) == int(before.exp), (
        f"The switched token expires at {after.exp}; the token it was switched from expires at "
        f"{before.exp}. Ruling G1: a switch keeps the old `exp` exactly, or switching is a refresh."
    )
    assert int(after.iat) > int(before.iat), (
        f"The switched token's `iat` is {after.iat}, not later than the old token's {before.iat}. "
        "Ruling G1 keeps `iat` as the time of the switch."
    )


def test_a_cookie_borne_switch_keeps_the_old_tokens_expiry(session_switch: Any) -> None:
    """G1 (a), the cookie path, with this session's own double-submit token.

    **The mutation it kills:** the expiry carried on one path and not the other
    (for instance, the cookie-carrier branch re-issuing through a helper that
    does not pass `expires_at`), and the new session cookie set with a token
    other than the one whose `exp` was kept.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    old = an_old_token(world, person, INSTRUCTOR)
    before = verified(old, world.secret)

    new = new_token_of(
        world, world.switch(old, LEADERSHIP, carrier=COOKIE), LEADERSHIP, "A cookie-borne switch"
    )

    assert int(verified(new, world.secret).exp) == int(before.exp), (
        f"The cookie-borne switch issued a token expiring at {verified(new, world.secret).exp}; the "
        f"old token expires at {before.exp}."
    )


def test_switching_back_and_forth_between_two_held_roles_never_moves_the_expiry(
    session_switch: Any,
) -> None:
    """G1 (a): four switches in a row, instructor and leadership alternately, and one `exp` throughout.

    **The mutation it kills:** the refresh by alternation, which a single
    same-role refusal does not stop: leadership to instructor and back, each
    switch issuing a fresh lifetime, keeps a session alive for ever without ever
    asking for the role it already holds.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    token = an_old_token(world, person, INSTRUCTOR)
    original = int(verified(token, world.secret).exp)

    for step, role in enumerate((LEADERSHIP, INSTRUCTOR, LEADERSHIP, INSTRUCTOR), start=1):
        token = new_token_of(world, world.switch(token, role), role, f"Switch {step} into {role}")
        exp = int(verified(token, world.secret).exp)
        assert exp == original, (
            f"After switch {step} (into {role}) the session expires at {exp}; it expired at "
            f"{original} before the first switch."
        )


# ---------------------------------------------------------------------------
# G1 (b) — a switch to the session's own role is refused.
# ---------------------------------------------------------------------------


def test_a_switch_to_the_role_the_session_already_holds_is_refused_and_changes_nothing(
    session_switch: Any,
) -> None:
    """G1 (b): a same-role switch answers the refused-switch 403 and copy, issues nothing, revokes nothing.

    The copy is required to be the same registry entry a switch to a role the
    person does not hold answers with, asked in the same test, so a same-role
    refusal with a sentence of its own is red.

    **The mutations it kills:** the same-role switch allowed (the refresh by
    asking for what you have); refused with a different status or sentence;
    refused after revoking the old token or after setting a cookie.
    """
    world = session_switch
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    old = an_old_token(world, person, LEADERSHIP)
    old_jti = world.jti_of(old)

    answered = world.switch(old, LEADERSHIP)

    assert answered.status_code == SWITCH_REFUSED, (
        f"A switch to the role the session already holds answered {answered.status_code} rather "
        f"than {SWITCH_REFUSED}. Ruling G1 (b): it is refused like any other refused switch."
    )
    reference = world.switch(old, "admin")
    assert reference.status_code == SWITCH_REFUSED, (
        f"The reference refusal (a switch to a role she does not hold) answered "
        f"{reference.status_code}, so there is no refused-switch copy to compare with."
    )
    assert externalized_key_for(answered) == externalized_key_for(
        reference
    ), "A same-role switch was refused with a different copy entry from any other refused switch."
    nothing_was_issued(answered, "a switch to the role the session already holds")
    assert (
        world.landings(old).status_code == LANDINGS_OK
    ), "After a refused same-role switch, the session it was asked from no longer works."
    assert (
        old_jti not in world.revocation_rows()
    ), "A refused same-role switch wrote a revocation row for the session it was asked from."


# ---------------------------------------------------------------------------
# G2 — two switches with one token: exactly one wins.
# ---------------------------------------------------------------------------


def race_switch_b_against_switch_a(
    world: Any, migrated_engine: Any, *, a_commits: bool
) -> tuple[Any, str, Any]:
    """Run the two-connection race and answer B's response, the old token, and the person.

    A inserts the old token's revocation row on its own connection and holds the
    transaction open; B, a real switch over HTTP, is sent from a worker thread;
    B must be seen waiting on a lock within the bound, or the test fails; then A
    commits or rolls back, and B's answer is awaited with a bound.
    """
    from sqlalchemy import text

    require_revoked_session_table(world.rows.session)
    person = world.person(hats=(DEAN_HAT, INSTRUCTOR_HAT))
    old = an_old_token(world, person, INSTRUCTOR)
    claims = verified(old, world.secret)

    switch_a = migrated_engine.connect()
    transaction = switch_a.begin()
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        switch_a.execute(
            text(REVOKE_AS_SWITCH_A),
            {"jti": str(claims.jti), "expires_at": datetime.fromtimestamp(int(claims.exp), UTC)},
        )
        switch_b = executor.submit(world.switch, old, LEADERSHIP)

        # Postgres keeps one snapshot of `pg_stat_activity` per transaction, so
        # the watcher clears it before every poll; without that it reads the
        # state from its first poll for ever and never sees B start waiting.
        seen_waiting = False
        deadline = time.monotonic() + BLOCK_WAIT_SECONDS
        with migrated_engine.connect() as watcher:
            while not switch_b.done() and time.monotonic() < deadline:
                watcher.execute(text(CLEAR_THE_STATISTICS_SNAPSHOT))
                if watcher.execute(text(SESSIONS_WAITING_ON_A_LOCK)).scalar_one():
                    seen_waiting = True
                    break
                time.sleep(POLL_SECONDS)
        if not seen_waiting:
            pytest.fail(
                f"Switch B was not seen waiting on a lock within {BLOCK_WAIT_SECONDS}s while switch "
                f"A held the old token's revocation row uncommitted (B "
                f"{'had already answered' if switch_b.done() else 'was still running'}). B's "
                "revocation insert has to wait on A's row: a B that answered without waiting "
                "never tried to spend the token in the same transaction as its issue."
            )

        if a_commits:
            transaction.commit()
        else:
            transaction.rollback()
        try:
            answered = switch_b.result(timeout=ANSWER_WAIT_SECONDS)
        except FutureTimeout:
            pytest.fail(
                f"Switch B had not answered {ANSWER_WAIT_SECONDS}s after switch A "
                f"{'committed' if a_commits else 'rolled back'}. A switch that waits on A's row "
                "must finish once A's transaction ends."
            )
    finally:
        if transaction.is_active:
            transaction.rollback()
        switch_a.close()
        executor.shutdown(wait=False)
    return answered, old, person


def test_a_switch_racing_another_switch_of_the_same_token_answers_401_and_issues_nothing(
    session_switch: Any, migrated_engine: Any
) -> None:
    """G2: switch A revokes and commits first; switch B, blocked behind it, gets 401 and no token.

    B's answer is compared whole with an expired token's answer at the switch
    route (status, body, challenge): the ruling's "the same body as a revoked
    token on any gate".

    **The mutations it kills:** the revocation insert without `ON CONFLICT DO
    NOTHING` (B fails with a 500 on the primary key); `ON CONFLICT DO NOTHING`
    without reading `RETURNING` (B issues a second live session from one token);
    the revocation committed separately from the issue; and B refused with a
    status or body of its own. **Its pair** is the next test.
    """
    world = session_switch

    answered, _old, person = race_switch_b_against_switch_a(world, migrated_engine, a_commits=True)

    expired = world.expired(person, door=LAUNCH, role=INSTRUCTOR)
    reference = world.switch(expired, LEADERSHIP)
    assert reference.status_code == SESSION_REFUSED, (
        f"An expired token at the switch route answered {reference.status_code}, so there is no "
        "expired-token 401 to compare with."
    )
    assert refusal_shape(answered) == refusal_shape(reference), (
        f"Switch B, racing a switch that spent the same token first, answered "
        f"{refusal_shape(answered)!r}; an expired token at the switch route answers "
        f"{refusal_shape(reference)!r}. Ruling G2: a spent token gets the expired-token 401."
    )
    nothing_was_issued(answered, "a switch whose token another switch had already spent")


def test_a_switch_waiting_on_another_that_rolls_back_still_switches(
    session_switch: Any, migrated_engine: Any
) -> None:
    """G2's pair: if switch A rolls back, its revocation never happened, and switch B succeeds.

    **The mutation it kills:** a switch that refuses whenever it had to wait on
    a lock, or that decides "spent" by something other than the row its own
    insert returned, which passes the race test above and refuses an honest
    switch whenever two requests overlap.
    """
    world = session_switch

    answered, old, _person = race_switch_b_against_switch_a(world, migrated_engine, a_commits=False)

    new_token_of(world, answered, LEADERSHIP, "Switch B, after switch A rolled back")
    assert world.landings(old).status_code == SESSION_REFUSED, (
        "Switch B succeeded and the token it switched from still works; B's own revocation did not "
        "land."
    )
