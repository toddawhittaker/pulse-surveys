"""The admin gate lets an admin session through, refuses another role 403 and no session 401 — E9-02.

Done-when 10, as the ticket states it:

> **The route gate.** `require_admin` answers a missing token 401, a
> leadership, instructor, student or Care session 403 with
> `insufficient_scope`, and an admin session through. Driven over HTTP on
> one stub route the tests mount (MISTAKES entry 47), since the real routes
> are E9-06's.

and its "Owns": "`require_admin` and `csrf_verified_admin`. A session in another
role gets ADR 0196's 403 marked `insufficient_scope`; a missing or bad token gets
the existing 401."

**Both members are driven, on the same questions.** `csrf_verified_admin` is the
gate every admin write will carry (E9-06), and a member of that family that does
not reach the role gate is exactly the hole E5-06's battery found in its
leadership twin. Driven with a Bearer header — which ADR 0089's double-submit
check exempts on purpose — the only thing left on a POST that can refuse is the
role gate, so each question below is asked of both. The cookie carrier is
`test_every_csrf_verified_dependency_refuses_a_cookie_borne_write.py`'s.

**ADR 0196's 403, read as that record states it**: the status, a `WWW-Authenticate`
challenge carrying `insufficient_scope`, a body that is one sentence under
`detail` and nothing else, the same sentence for every role, and a sentence the
copy registry publishes (a student is served it, so it is inside SPEC §4.1 item
1's registry sweep, as ADR 0196's consequences say of its own). The settled
interface puts it at `admin_people.not_your_role`; it is compared by registry key
and its words are not spelled here.

**"The existing 401"** is asserted as the collapse ADR 0196 keeps: absent,
malformed, forged and expired tokens get one status, one body, and a challenge
that does not say `insufficient_scope` — so a caller trying tokens cannot tell a
real one from a forgery. The settled interface gives that body the sentence at
`admin_people.not_an_admin_session`, compared by key.

**The admin beside every refusal.** Each refusal is asked in a world where a
real admin, holding a live `ADMIN` assignment, is let through the same stub — so
a gate that refuses everything is red here, not green (`docs/MISTAKES.md`
entry 3).

**Which failure a red is, before E9-02 lands.** `app.api.deps` has no
`require_admin` or `csrf_verified_admin`, so every test but the control FAILS in
its body naming the missing dependency (`fixtures/admin_gate.py::
admin_dependency`), never an ERROR. The control is green today; a red control
means the stub instrument is broken, not the gate.

Not `invariant`-marked: this is the admin route gate, not a SPEC §4.1
confidentiality item.
"""

import base64
import json
import time
from typing import Any

import pytest
from fixtures.admin_gate import (
    ADMITTED_BODY,
    CSRF_VERIFIED_ADMIN,
    DEAN_ASSIGNMENT,
    INSUFFICIENT_SCOPE,
    REQUIRE_ADMIN,
    a_care_holder,
    a_person_holding,
    a_student,
    admin_dependency,
    an_admin,
    ask,
    minted,
    mount_stub,
    web_door,
)
from fixtures.lead_review import LeadReviewWorld
from fixtures.named_sets import LEADERSHIP_LANDING_ROLE
from fixtures.student_read import AUTHENTICATE_HEADER, DETAIL_MEMBER
from fixtures.submit import copy_texts

pytestmark = pytest.mark.integration

SIGNED_OUT_STATUS = 401
NOT_YOUR_ROLE_STATUS = 403

# The two members of the gate, and the method each is mounted on.
GATES = ((REQUIRE_ADMIN, "GET"), (CSRF_VERIFIED_ADMIN, "POST"))
GATE_IDS = [name for name, _method in GATES]

# The four kinds of session in another role the ticket names.
LEADERSHIP = "a leadership session"
INSTRUCTOR = "the instructor's launched session"
STUDENT = "a student session"
CARE = "a Care session"
OTHER_ROLES = (LEADERSHIP, INSTRUCTOR, STUDENT, CARE)

# A secret the application was certainly not built with. This module's own value.
ANOTHER_SECRET = b"e9-02-a-secret-this-application-was-never-configured-with"

# ADR 0089 gives a session sixty minutes; two days is past that by a margin no
# clock drift reaches, and is not the boundary (`tests/unit/test_session_module.py`
# owns the boundary pair).
EXPIRED_BY_SECONDS = 2 * 24 * 60 * 60

# The token the e2e suite already uses for "a session the server will not verify".
MALFORMED = "not.a.session"

# The gate's two sentences, by registry key (settled interface §3): the 401's and
# the 403's, both in `app.copy.admin_people`. Keys, never words (MISTAKES entry 19).
SIGNED_OUT_KEY = "admin_people.not_an_admin_session"
NOT_YOUR_ROLE_KEY = "admin_people.not_your_role"

# The one header every response carries that differs between two identical requests.
ALWAYS_VARIES = frozenset({"date"})


# ---------------------------------------------------------------------------
# Helpers. Each returns what it read; every assertion is in a test body.
# ---------------------------------------------------------------------------


class Stub:
    """One mounted stub, and how many requests its endpoint was reached by."""

    def __init__(
        self, review: LeadReviewWorld, request: pytest.FixtureRequest, gate: str, method: str
    ) -> None:
        self.review = review
        self.method = method
        self.reached: list[Any] = []
        dependency = admin_dependency(gate)
        self.path, remove = mount_stub(
            review.door.door.application, method, dependency, self.reached.append
        )
        request.addfinalizer(remove)

    def ask(self, token: Any) -> Any:
        return ask(self.review, self.method, self.path, token)


def session_of(review: LeadReviewWorld, who: str) -> str:
    """A live, verified session for one of the four other-role readers."""
    if who == LEADERSHIP:
        assert review.lead is not None
        return review.lead.token
    if who == INSTRUCTOR:
        return review.instructor_token
    if who == STUDENT:
        return a_student(review)
    if who == CARE:
        return a_care_holder(review).token
    raise AssertionError(f"No session kind {who!r}.")


def detail_or_none(answered: Any) -> Any:
    try:
        body = answered.json()
    except ValueError:
        return None
    return body.get(DETAIL_MEMBER) if isinstance(body, dict) else None


def body_members(answered: Any) -> Any:
    try:
        body = answered.json()
    except ValueError:
        return None
    return sorted(body) if isinstance(body, dict) else None


def challenge(answered: Any) -> str:
    return str(answered.headers.get(AUTHENTICATE_HEADER, ""))


def unsecured(token: str) -> str:
    """The same claims re-encoded `alg: none` with an empty signature (RFC 7519 §6)."""

    def padded(segment: str) -> bytes:
        return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))

    header_b64, claims_b64, _signature = token.split(".")
    header = {**json.loads(padded(header_b64)), "alg": "none"}
    encoded = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).rstrip(b"=")
    return f"{encoded.decode('ascii')}.{claims_b64}."


def stable_headers(answered: Any, varies: set[str]) -> dict[str, str]:
    return {
        name.lower(): value
        for name, value in answered.headers.items()
        if name.lower() not in varies and name.lower() not in ALWAYS_VARIES
    }


# ---------------------------------------------------------------------------
# Control on the instrument. A red here means the stub is broken, not the gate.
# ---------------------------------------------------------------------------


def test_the_stub_route_runs_the_gate_its_endpoint_declares(
    lead_review: LeadReviewWorld, request: pytest.FixtureRequest
) -> None:
    """CONTROL — green today. A mounted stub is served, and the gate in its endpoint runs.

    Every other test here rests on two facts about the instrument: a route added
    to the built application after it was built is dispatched, and a `Depends`
    in its endpoint's signature runs at dispatch (`docs/MISTAKES.md` entry 47's
    rule: the gate must live in the endpoint). So the stub is mounted twice with
    gates that are not E9-02's — one that lets everything through and one that
    refuses everything with a status nothing else in this stack answers — and
    both answers are required, on both methods.

    **The mutations it kills (in the instrument):** a stub mounted where the
    route table never reaches it (every request then 404s, and every refusal
    test reads a 404 as "not let through"); a gate put on the route object
    rather than the endpoint, which is inert at dispatch.
    """
    from fastapi import HTTPException

    def lets_through() -> str:
        return "through"

    def refuses() -> str:
        raise HTTPException(status_code=418, detail="e9-02 control gate")

    for method in ("GET", "POST"):
        reached: list[Any] = []
        open_path, remove_open = mount_stub(
            lead_review.door.door.application, method, lets_through, reached.append
        )
        request.addfinalizer(remove_open)
        shut_path, remove_shut = mount_stub(
            lead_review.door.door.application, method, refuses, reached.append
        )
        request.addfinalizer(remove_shut)

        opened = ask(lead_review, method, open_path, None)
        assert (opened.status_code, opened.json()) == (200, ADMITTED_BODY), (
            f"A {method} stub whose gate lets everything through answered {opened.status_code} "
            f"{opened.text[:300]!r}. The instrument does not serve the route it mounted."
        )
        assert reached == ["through"], f"The endpoint was reached with {reached}, not once."

        shut = ask(lead_review, method, shut_path, None)
        assert shut.status_code == 418, (
            f"A {method} stub whose gate refuses everything answered {shut.status_code}. The gate "
            "in the endpoint's signature did not run, so nothing here can say whether "
            "`require_admin` does."
        )
        assert reached == ["through"], "The refused request reached the endpoint anyway."


# ---------------------------------------------------------------------------
# An admin session is let through.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("gate", "method"), GATES, ids=GATE_IDS)
def test_an_admin_session_is_let_through(
    lead_review: LeadReviewWorld, request: pytest.FixtureRequest, gate: str, method: str
) -> None:
    """Done-when 10's admitted half: an admin session, holding a live `ADMIN` assignment.

    **The mutations it kills:** a gate that refuses every session (the role
    check inverted, or compared against the wrong member); a `csrf_verified_admin`
    that refuses a Bearer-borne write, which ADR 0089 exempts from the
    double-submit check. **Expected red before E9-02 lands:** a FAILED naming
    the missing dependency.
    """
    stub = Stub(lead_review, request, gate, method)
    admin = an_admin(lead_review)

    answered = stub.ask(admin.token)

    assert answered.status_code == 200, (
        f"`{gate}` answered {answered.status_code} to an admin session whose person holds a live "
        f"`ADMIN` assignment. Body begins {answered.text[:400]!r}."
    )
    assert len(stub.reached) == 1, (
        f"The stub answered 200 and its endpoint was reached {len(stub.reached)} times. The answer "
        "is a claim that the gate let the request through."
    )


# ---------------------------------------------------------------------------
# A verified session in another role gets ADR 0196's 403.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("who", OTHER_ROLES)
@pytest.mark.parametrize(("gate", "method"), GATES, ids=GATE_IDS)
def test_a_session_in_another_role_gets_the_403_marked_insufficient_scope(
    lead_review: LeadReviewWorld,
    request: pytest.FixtureRequest,
    gate: str,
    method: str,
    who: str,
) -> None:
    """Done-when 10's refused half: leadership, instructor, student and Care each get the 403.

    The Care holder is the case ruling 1 makes worth naming: Care and Admin are
    the two roles SPEC §6.2 keeps apart, and since the editor can grant either to
    anyone, the gate is what keeps a Care session off the people graph.

    **The mutations it kills:** a gate admitting any staff role (`role is not
    STUDENT`), which lets the leadership, instructor and Care sessions through;
    a gate admitting the web-door roles (`CARE` or `ADMIN`), which lets Care
    through; the leadership gate's 401 copied for another role, which the pages
    would read as an ended session; a 403 without ADR 0196's challenge, which
    the pages would not read as "not your role"; a refusal answered after the
    endpoint ran. **The near miss it spares:** a real admin on the same stub,
    let through (the admin beside the refusal).
    """
    stub = Stub(lead_review, request, gate, method)
    token = session_of(lead_review, who)

    refused = stub.ask(token)

    assert refused.status_code == NOT_YOUR_ROLE_STATUS, (
        f"`{gate}` answered {refused.status_code} to {who}, a real, verified, live session in "
        f"another role. ADR 0196: such a session gets {NOT_YOUR_ROLE_STATUS}. Body begins "
        f"{refused.text[:400]!r}."
    )
    assert INSUFFICIENT_SCOPE in challenge(refused), (
        f"`{gate}`'s 403 to {who} carries the challenge {challenge(refused)!r}. ADR 0196: the 403 "
        f'carries `WWW-Authenticate: Bearer error="{INSUFFICIENT_SCOPE}"`, which is how a page '
        "tells this refusal from every other 403 on the same routes."
    )
    assert body_members(refused) == [DETAIL_MEMBER] and isinstance(detail_or_none(refused), str), (
        f"`{gate}`'s 403 to {who} answered the body {refused.text[:400]!r}. ADR 0196: one sentence "
        f"under `{DETAIL_MEMBER}` and nothing beside it, so a refusal has nowhere to name anything."
    )
    assert stub.reached == [], f"`{gate}` refused {who} after the endpoint ran: {stub.reached}."

    admitted = stub.ask(an_admin(lead_review).token)
    assert admitted.status_code == 200, (
        f"`{gate}` answered {admitted.status_code} to a real admin beside the refusal of {who}, so "
        "the refusal above is a gate that refuses everybody."
    )


@pytest.mark.parametrize(("gate", "method"), GATES, ids=GATE_IDS)
def test_the_403_is_one_sentence_for_every_other_role_and_the_copy_registry_publishes_it(
    lead_review: LeadReviewWorld, request: pytest.FixtureRequest, gate: str, method: str
) -> None:
    """ADR 0196's body rule: one fixed sentence, the same for every role, held in the registry.

    **The mutations it kills:** a sentence formatted with the reader's role or
    the route (two roles, two sentences); an inline sentence the registry does
    not hold, which SPEC §4.1 item 1's registry sweep cannot read although a
    student is served it. **Why one sentence:** a constant that is the same for
    every reader cannot carry anything particular to one of them.
    """
    stub = Stub(lead_review, request, gate, method)

    sentences: dict[str, str] = {}
    for who in OTHER_ROLES:
        refused = stub.ask(session_of(lead_review, who))
        assert refused.status_code == NOT_YOUR_ROLE_STATUS, (
            f"`{gate}` answered {refused.status_code} to {who}; the body rule below is about the "
            f"403. Body begins {refused.text[:400]!r}."
        )
        sentences[who] = str(detail_or_none(refused))

    distinct = set(sentences.values())
    assert len(distinct) == 1, (
        f"`{gate}`'s 403 is {len(distinct)} sentences across the four roles: {sentences}. ADR "
        "0196: one sentence, the same for every role and route."
    )
    (sentence,) = distinct
    assert sentence in set(copy_texts().values()), (
        f"`{gate}`'s 403 sentence {sentence!r} is not a string the copy registry publishes. A "
        "student is served it, so it has to be inside SPEC §4.1 item 1's registry sweep."
    )
    expected = copy_texts().get(NOT_YOUR_ROLE_KEY)
    assert sentence == expected, (
        f"`{gate}`'s 403 sentence is {sentence!r}; the settled interface puts it at "
        f"`{NOT_YOUR_ROLE_KEY}` (constant `NOT_ADMIN_ROLE` in `app.copy.admin_people`), which the "
        f"registry holds as {expected!r}. The leadership gate's sentence says 'leadership' and is "
        "not this one."
    )


# ---------------------------------------------------------------------------
# Anything that is not a live session gets the one 401.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("gate", "method"), GATES, ids=GATE_IDS)
def test_an_absent_malformed_or_forged_token_gets_one_identical_401(
    lead_review: LeadReviewWorld, request: pytest.FixtureRequest, gate: str, method: str
) -> None:
    """The ticket's "a missing or bad token gets the existing 401", as ADR 0196's collapse.

    Five credentials: none; `not.a.session`; the real admin's own claims signed
    with another key; the same re-encoded `alg: none`; and the admin's claims
    issued two days ago. Each must be 401 with a challenge that does not say
    `insufficient_scope`, and all five must be indistinguishable — equal bodies,
    and equal headers once the headers that differ between two identical
    absent-token requests are set aside (measured, not listed).

    **The mutations it kills:** the role read off a token before its signature
    or expiry is checked — the forged admin token is then let through, or the
    forged student-shaped ones get the 403, which tells a caller trying tokens
    which are real; a challenge on some refusals and not others. **The near miss
    it spares:** the real admin, let through beside them.
    """
    stub = Stub(lead_review, request, gate, method)
    admin = an_admin(lead_review)
    signed_elsewhere = minted(
        lead_review,
        role="ADMIN",
        person_id=admin.person_id,
        user_id=admin.user_id,
        subject=admin.subject,
        door=web_door(),
        secret=ANOTHER_SECRET,
    )
    expired = minted(
        lead_review,
        role="ADMIN",
        person_id=admin.person_id,
        user_id=admin.user_id,
        subject=admin.subject,
        door=web_door(),
        now=int(time.time()) - EXPIRED_BY_SECONDS,
    )
    credentials = {
        "no token": None,
        "a malformed token": MALFORMED,
        "the admin's claims signed with another key": signed_elsewhere,
        "the admin's token re-encoded alg none": unsecured(admin.token),
        "the admin's claims issued two days ago": expired,
    }

    admitted = stub.ask(admin.token)
    assert admitted.status_code == 200, (
        f"`{gate}` answered {admitted.status_code} to the real admin, so every 401 below is a "
        "gate that refuses everybody."
    )
    first, second = stub.ask(None), stub.ask(None)
    varies = {
        name
        for name in {*first.headers.keys(), *second.headers.keys()}
        if first.headers.get(name) != second.headers.get(name)
    }

    answers = {what: stub.ask(token) for what, token in credentials.items()}
    for what, answered in answers.items():
        assert answered.status_code == SIGNED_OUT_STATUS, (
            f"`{gate}` answered {answered.status_code} to {what}; a token that is not a live "
            f"session gets the existing {SIGNED_OUT_STATUS}. Body begins {answered.text[:400]!r}."
        )
        assert challenge(answered), f"`{gate}` refused {what} with no `{AUTHENTICATE_HEADER}`."
        assert INSUFFICIENT_SCOPE not in challenge(answered), (
            f"`{gate}`'s 401 to {what} carries {challenge(answered)!r}. `{INSUFFICIENT_SCOPE}` "
            "says the token is real and lacks the privilege, which is the one thing a 401 to a "
            "token that did not verify must not say."
        )

    reference = answers["no token"]
    expected = copy_texts().get(SIGNED_OUT_KEY)
    assert detail_or_none(reference) == expected, (
        f"`{gate}`'s 401 says {detail_or_none(reference)!r}; the settled interface puts it at "
        f"`{SIGNED_OUT_KEY}` (constant `NOT_ADMIN` in `app.copy.admin_people`), which the registry "
        f"holds as {expected!r}."
    )
    for what, answered in answers.items():
        assert answered.content == reference.content, (
            f"`{gate}` answered {what} with a body that differs from the absent token's: "
            f"{answered.content[:300]!r} against {reference.content[:300]!r}."
        )
        assert stable_headers(answered, varies) == stable_headers(reference, varies), (
            f"`{gate}` answered {what} with headers that differ from the absent token's: "
            f"{stable_headers(answered, varies)} against {stable_headers(reference, varies)}."
        )
    assert len(stub.reached) == 1, (
        f"The endpoint was reached {len(stub.reached)} times; only the real admin's request "
        "should have reached it."
    )


@pytest.mark.parametrize(("gate", "method"), GATES, ids=GATE_IDS)
def test_an_expired_admin_token_gets_the_401_where_the_same_admin_live_is_let_through(
    lead_review: LeadReviewWorld, request: pytest.FixtureRequest, gate: str, method: str
) -> None:
    """The boundary pair: one admin, two tokens, differing only in when they were issued.

    **The mutations it kills:** expiry ignored for the admin role; the role
    honoured before expiry is checked. **The near miss:** the same admin's live
    token, let through on the same stub — without it, "the expired one got 401"
    is equally true of a gate that refuses everybody.
    """
    stub = Stub(lead_review, request, gate, method)
    admin = an_admin(lead_review)
    expired = minted(
        lead_review,
        role="ADMIN",
        person_id=admin.person_id,
        user_id=admin.user_id,
        subject=admin.subject,
        door=web_door(),
        now=int(time.time()) - EXPIRED_BY_SECONDS,
    )

    live = stub.ask(admin.token)
    late = stub.ask(expired)

    assert live.status_code == 200, (
        f"`{gate}` answered {live.status_code} to the admin's live token. Body begins "
        f"{live.text[:400]!r}."
    )
    assert late.status_code == SIGNED_OUT_STATUS, (
        f"`{gate}` answered {late.status_code} to the same admin's token issued "
        f"{EXPIRED_BY_SECONDS} seconds ago. An expired session is an ended one. Body begins "
        f"{late.text[:400]!r}."
    )


# ---------------------------------------------------------------------------
# The session's role decides, not the person's assignments.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("gate", "method"), GATES, ids=GATE_IDS)
def test_an_admin_and_dean_is_refused_under_her_leadership_session_and_let_in_under_admin(
    lead_review: LeadReviewWorld, request: pytest.FixtureRequest, gate: str, method: str
) -> None:
    """One person, two sessions, differing only in the role each names.

    She holds a live `ADMIN` and a live `DEAN` assignment. **The mutations it
    kills:** a gate that reads the person's assignments rather than the
    session's role — it lets her leadership session through, because she holds
    `ADMIN`; a gate that refuses the person — it refuses her admin session too.
    E9-04's switcher issues one session per hat, so this is the shape every
    two-hat admin arrives in.
    """
    stub = Stub(lead_review, request, gate, method)
    admin_hat = a_person_holding(
        lead_review,
        "two-hat",
        assignments=("ADMIN", DEAN_ASSIGNMENT),
        landing="ADMIN",
        at_the_web_door=True,
    )
    leadership_hat = minted(
        lead_review,
        role=LEADERSHIP_LANDING_ROLE,
        person_id=admin_hat.person_id,
        user_id=admin_hat.user_id,
        subject=admin_hat.subject,
    )

    refused = stub.ask(leadership_hat)
    admitted = stub.ask(admin_hat.token)

    assert refused.status_code == NOT_YOUR_ROLE_STATUS, (
        f"`{gate}` answered {refused.status_code} to the leadership session of a person who also "
        "holds `ADMIN`. The gate reads the session's role, not the person's assignments. Body "
        f"begins {refused.text[:400]!r}."
    )
    assert INSUFFICIENT_SCOPE in challenge(
        refused
    ), f"`{gate}`'s refusal of her leadership session carries {challenge(refused)!r}."
    assert admitted.status_code == 200, (
        f"`{gate}` answered {admitted.status_code} to the same person's admin session. Body "
        f"begins {admitted.text[:400]!r}."
    )
