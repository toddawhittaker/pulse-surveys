"""Every `csrf_verified_*` dependency refuses a cookie-borne write that carries no token.

**This module exists because a green suite said nothing.** E5-06's mutation
battery and its security pass found the same hole from two directions: gutting
`csrf_verified_leadership` to `return claims` left all 3716 tests green. Two
things had to be true at once for that, and both were. Every named-set request in
this suite rides an `Authorization: Bearer` header, and `_double_submit_verified`
exempts that carrier on purpose — a Bearer header is not sent by a cross-site
form, so there is nothing for the check to protect there. And the route sweep
that was supposed to hold the line,
`tests/unit/test_every_mutating_route_carries_the_csrf_check.py`, admits any
callable whose *name* begins `csrf_verified_`. A name is not a check
(`docs/MISTAKES.md` entry 2: behaviour shipped with nothing asserting it, and
entry 47: a sweep over the route table answers "is the dependency there", never
"does the gate run").

**So each member of the family is driven on the carrier the check exists for.**
The session goes in the cookie, no `Authorization` header is sent, and one
writing route per member is asked three times:

  - carrying no `X-Pulse-CSRF` at all → refused, and nothing written;
  - carrying a **genuine token bound to another session** → refused, and nothing
    written. Genuine rather than random, because an attacker who can make a
    browser send a cross-site request can toss a cookie too: the value goes in
    the cookie *and* the header, so a check that compares the two to each other
    passes for it and only ADR 0089's HMAC against *this* session's `jti`
    refuses it (`docs/disputes/E2-08-06.md`, mutation M1c);
  - carrying the correctly bound token → admitted, **and the write took effect**.

**The status and the sentence are pinned without either being transcribed
here.** The status is `tests/fixtures/submit.py`'s `CSRF_REFUSED_STATUS`, which
ADR 0114's table settles. The sentence is read back through the copy registry:
both refusals must resolve to one and the same registry key, which is what says
they came from the one shared helper rather than from two hand-written answers
that happen to agree today. `test_every_member_of_the_family_reaches_the_shared
_double_submit_check` is the cheap structural second line beside it.

**A member with no driver here reds by construction.** The family is discovered
by prefix off `app.api.deps` — the same discovery the route sweep uses
(`docs/MISTAKES.md` entry 13) — and `test_the_family_is_exactly_the_members_this
_module_drives` requires the discovered set to equal the set this module knows
how to drive. A future `csrf_verified_admin` that forgets the delegation is
therefore not quietly unswept: this module goes red naming it, and the repair is
to add its writing route to `DRIVERS` rather than to widen anything.

**Why the worlds are fetched inside the body.** Each member needs a different
world — the student's submit window, the leadership set surface — and a test
signature naming both builds both on every parameter. `request.getfixturevalue`
builds the one the parameter is about, which is the difference between two heavy
worlds per run and one.
"""

from typing import Any, NamedTuple

import pytest
from fixtures.named_sets import MINTED, NAME_FIELD, NamedSetDoor
from fixtures.submit import (
    COOKIE_SESSION,
    CSRF_DEPENDENCY_PREFIX,
    CSRF_REFUSED_STATUS,
    DOUBLE_SUBMIT_HELPER,
    SUBSTANTIVE_COMMENT,
    a_valid_submission,
    csrf_token_for,
    csrf_verified_dependencies,
    externalized_key_for,
    reaches_the_double_submit_check,
)

pytestmark = pytest.mark.integration

# The member of the family this module drives, and the writing route it is driven
# on. One route each is enough: the question is whether the *dependency* checks,
# and a dependency that checks on one route checks on every route that declares
# it — which is what the route sweep proves it does.
STUDENT = "csrf_verified_student"
LEADERSHIP = "csrf_verified_leadership"
DRIVERS = (STUDENT, LEADERSHIP)


class CookieBorneWrite(NamedTuple):
    """One member's writing route, driven three ways, with a reader for the effect.

    Each call is a thunk rather than a response, so the three requests are made
    in the order the test states — the two refusals before the acceptance, so
    that "nothing was written" is asked of a world nothing has written to yet.
    """

    what: str
    without_a_token: Any
    with_another_sessions_token: Any
    with_the_bound_token: Any
    writes: Any


def a_student_submitting(request: pytest.FixtureRequest) -> CookieBorneWrite:
    """E2-08's submit route, driven by a student whose session rides the cookie."""
    submit_world = request.getfixturevalue("submit_world")
    open_submit_tool = request.getfixturevalue("open_submit_tool")
    signed_in_student = request.getfixturevalue("signed_in_student")
    mock_ai = request.getfixturevalue("mock_ai")
    mock_ai_endpoint = request.getfixturevalue("mock_ai_endpoint")
    opens_at, closes_at = request.getfixturevalue("open_now")

    world = submit_world.build(opens_at=opens_at, closes_at=closes_at)
    client = open_submit_tool(ai_base_url=mock_ai_endpoint.base_url)
    student = signed_in_student(client, world)
    other = signed_in_student(client, world, world.another_student())
    body = a_valid_submission(comment=f"{SUBSTANTIVE_COMMENT} {mock_ai.marker_for('substantive')}")
    forged = csrf_token_for(other.token, other.secret)
    assert forged != csrf_token_for(student.token, student.secret), (
        "The two students' CSRF tokens are the same string, so the forged case is not carrying "
        "another session's token at all. ADR 0089 binds the token to the session's `jti` by HMAC, "
        "and two sessions have two `jti`s."
    )

    return CookieBorneWrite(
        what="a student's submission",
        without_a_token=lambda: student.submit(body, via=COOKIE_SESSION, csrf=False),
        with_another_sessions_token=lambda: student.submit(
            body, via=COOKIE_SESSION, csrf_token=forged
        ),
        with_the_bound_token=lambda: student.submit(body, via=COOKIE_SESSION, csrf=True),
        writes=lambda: len(world.responses()),
    )


def a_leader_defining_a_set(request: pytest.FixtureRequest) -> CookieBorneWrite:
    """E5-06's create route, driven by a leader whose session rides the cookie."""
    door: NamedSetDoor = request.getfixturevalue("named_sets")
    world = door.world
    body = world.a_write()
    another_session = world.two_hat_sessions()[1]
    forged = csrf_token_for(another_session, world.secret)
    assert forged != csrf_token_for(door.door.token, world.secret), (
        "The two leadership sessions' CSRF tokens are the same string, so the forged case is not "
        "carrying another session's token at all."
    )

    def stored() -> int:
        """How many sets carry the name this request sends — 0 before, 1 after a create."""
        return len([row for row in world.set_rows() if row[NAME_FIELD] == body[NAME_FIELD]])

    return CookieBorneWrite(
        what="a leader's set definition",
        without_a_token=lambda: door.create_as_a_browser(body, csrf_token=None),
        with_another_sessions_token=lambda: door.create_as_a_browser(body, csrf_token=forged),
        with_the_bound_token=lambda: door.create_as_a_browser(body, csrf_token=MINTED),
        writes=stored,
    )


DRIVE = {STUDENT: a_student_submitting, LEADERSHIP: a_leader_defining_a_set}


def test_the_family_is_exactly_the_members_this_module_drives() -> None:
    """A new `csrf_verified_*` dependency reds here until somebody drives it.

    The hole this module closes is a member of the family that verifies nothing,
    and the route sweep admits a member by name. So the set this module executes
    has to be the whole family: a `csrf_verified_admin` added tomorrow, wired to
    an admin write route and delegating to nothing, is otherwise swept by a rule
    that reads its name and by no rule that reads its behaviour.

    **The mutation it kills:** a new member added with no behavioural driver —
    which is not a defect somebody would notice, because every other test in the
    repository goes on passing.

    **The repair when it fires** is a driver in `DRIVE`, never a name removed
    from the discovery.
    """
    discovered = sorted(csrf_verified_dependencies())

    assert discovered == sorted(DRIVERS), (
        f"`app.api.deps` exposes the `{CSRF_DEPENDENCY_PREFIX}` family {discovered}, and this "
        f"module drives {sorted(DRIVERS)}.\n\n"
        "A member with no driver is a member nothing executes: the route sweep admits it by name "
        "and this module never asks it a question. Add its writing route to `DRIVE` — one cookie "
        "session, one write, three requests — rather than narrowing what is discovered."
    )


@pytest.mark.parametrize("member", DRIVERS, ids=DRIVERS)
def test_a_cookie_borne_write_is_refused_without_the_token_and_with_another_sessions(
    request: pytest.FixtureRequest, member: str
) -> None:
    """The pair the battery survivor asks for, on the carrier the exemption does not cover.

    **The mutation this kills** is the one the battery measured surviving:
    `csrf_verified_leadership` gutted to `return claims`. Every other test of the
    named-set API rides a Bearer header, which `_double_submit_verified` exempts,
    so the gutted dependency answered every one of them exactly as the real one
    does. Here the session rides the cookie — which is what a browser sends on a
    cross-site form post, and the whole reason ADR 0089's check exists, because
    the session cookie is `SameSite=None` for the life of an iframe visit.

    **And the near miss that makes the refusal mean something:** a token that is
    genuine under this application's own secret and bound to a *different*
    session, sent as the cookie and the header both. A check that tests for
    presence passes it; a check that compares the cookie against the header
    passes it; only verification against this session's `jti` refuses it.

    **The write is required not to have taken effect**, because a refusal that
    answers 403 after writing is the same defect with a better status.

    **The sentence is pinned as the registry key both refusals resolve to**,
    rather than transcribed here: one shared helper answers both, so two
    different keys would mean two hand-written answers that agree today, and an
    inline sentence resolves to no key at all.
    """
    subject = DRIVE[member](request)
    before = subject.writes()

    refusals = {
        "carrying no CSRF token": subject.without_a_token(),
        "carrying another session's CSRF token": subject.with_another_sessions_token(),
    }
    keys: dict[str, str] = {}
    for how, answered in refusals.items():
        assert answered.status_code == CSRF_REFUSED_STATUS, (
            f"{subject.what} {how}, with the session in the cookie and no `Authorization` header, "
            f"was answered {answered.status_code} rather than {CSRF_REFUSED_STATUS} by "
            f"`{member}`.\n\n"
            "A 2xx here is the hole E5-06's battery found: a dependency in this family that "
            "verifies nothing answers every Bearer-borne request correctly, because "
            f"`{DOUBLE_SUBMIT_HELPER}` exempts that carrier — and this is the carrier it does not. "
            f"Body begins {answered.text[:400]!r}."
        )
        keys[how] = externalized_key_for(answered)

    assert subject.writes() == before, (
        f"{subject.what} was refused and written anyway: the count moved from {before} to "
        f"{subject.writes()}. A refusal that takes effect is the defect with a better status on it."
    )
    assert len(set(keys.values())) == 1, (
        f"The two refusals served two different copy keys: {keys}. Both are answered by the one "
        f"shared `{DOUBLE_SUBMIT_HELPER}`, so two keys mean two sentences written by hand that "
        "agree with each other today."
    )


@pytest.mark.parametrize("member", DRIVERS, ids=DRIVERS)
def test_a_cookie_borne_write_carrying_the_bound_token_is_admitted_and_takes_effect(
    request: pytest.FixtureRequest, member: str
) -> None:
    """The twin, without which every refusal above is satisfied by a route that refuses everything.

    `docs/MISTAKES.md` entry 3. A `csrf_verified_*` that raised unconditionally
    would pass both refusals and break the product for every browser that uses
    the cookie carrier — which is the SPA's fallback path whenever the fragment
    was not captured.

    **The write is required to have taken effect**, not merely answered: a 2xx
    over a service that wrote nothing is a different green.

    **The mutation this kills:** a check that verifies the token against the
    wrong secret, or against the session in the header rather than the one in
    the cookie — both refuse the correctly bound token and are invisible to a
    test that only ever sends a bad one.
    """
    subject = DRIVE[member](request)
    before = subject.writes()

    answered = subject.with_the_bound_token()

    assert 200 <= answered.status_code < 300, (
        f"{subject.what} carrying the double-submit token this session is entitled to — minted "
        "through the application's own `issue_csrf_token`, in the cookie and the header — was "
        f"answered {answered.status_code} by `{member}`. Body begins {answered.text[:400]!r}."
    )
    assert subject.writes() == before + 1, (
        f"{subject.what} was answered {answered.status_code} and the count did not move: "
        f"{before} before, {subject.writes()} after. The answer is a claim that the write "
        "happened."
    )


@pytest.mark.parametrize("member", DRIVERS, ids=DRIVERS)
def test_every_member_of_the_family_reaches_the_shared_double_submit_check(member: str) -> None:
    """The cheap second line: the delegation is written, in one assertion per member.

    It reads source and runs nothing, so it cannot say the check executed — the
    two tests above are what say that. What it adds is a red that names the
    missing line rather than a 2xx a reader has to diagnose, and it costs no
    world.

    **The mutation it kills:** a member of the family that never calls the shared
    helper — the battery's survivor, in its structural form.

    **If a member delegates indirectly** — through a helper of its own that calls
    the check — this is the constant to correct (`DOUBLE_SUBMIT_HELPER` in
    `tests/fixtures/submit.py`), not the behavioural pair to weaken.
    """
    family = csrf_verified_dependencies()
    dependency = family.get(member)
    assert (
        dependency is not None
    ), f"`app.api.deps` exposes no `{member}`; it exposes {sorted(family)}."

    assert reaches_the_double_submit_check(dependency), (
        f"`{member}`'s source does not name `{DOUBLE_SUBMIT_HELPER}`, and neither does anything it "
        "wraps. Every member of this family is the same mechanism bound to a different role gate, "
        "and the mechanism is that one helper: a member that does not reach it is a name in the "
        "family and nothing more, which is exactly what E5-06's battery found surviving."
    )
