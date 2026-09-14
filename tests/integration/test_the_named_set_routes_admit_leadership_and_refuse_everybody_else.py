"""Every named-set route answers a leadership session and refuses every other one — E5-06.

Criterion 1: "Each route refuses an unauthenticated call and a student or
instructor session, and answers a leadership session — both directions, per
route, driven over HTTP against the built application (`docs/MISTAKES.md` entry
47)." Criterion 2's trap is folded in where it belongs, at the door: the
two-hat person holds an `INSTRUCTOR` assignment and a `DEAN` assignment at once,
and her *instructor* session is refused every one of these routes while her
*leadership* session is admitted — the same person, twice, differing only in
which hat the session names. SPEC §2.1: scope resolves by role assignment and
never by identity.

**Both directions, per route, and that is the whole design of the module.** A
refusal test alone is satisfied by a route nobody registered: an application
serving no `/leadership/comparison-sets` at all refuses every session that asks
for it, with a 404 rather than a 401, and a module reading only "it did not
answer 200" would report that as a pass. So each route is parametrized in both
directions, and the admitted half runs first in every failure message a reader
reaches for.

**A refusal pins the layer through the body, not the status.** 401 is a status
several things in this stack answer with; `NOT_LEADERSHIP` is a sentence exactly
one of them holds, and the work order puts it on the dependency. So each
refusal asserts the sentence and the `WWW-Authenticate: Bearer` challenge
together — which is what says the gate ran in `app.api.deps` rather than
somewhere inside a handler that had already read a set.

**Why the refused sessions are minted.** Three of the four are tokens no launch
in this suite can issue for this world: a second launch would build a second
term and a second set of sections, and a two-hat person's launch lands at
exactly one of her two views, which is `LANDING_PRECEDENCE`'s business and not
this ticket's. They are minted through `app.services.session`, the module both
doors issue through, exactly as `tests/fixtures/instructor_sections.py` mints
E4-18's two — and the control section below is what says a minted token is a
token this application accepts.

**Which failure a red here is, before E5-06 lands.** Every request goes to a
path the work order fixes outright, so an application without the router answers
404 and each admitted case fails on its status naming `ROUTER_IS_OWED`; the
refusal cases fail on the sentence, because `refusal_sentence` cannot find a
copy constant that does not exist yet. Both are FAILEDs naming a deliverable,
never errors in setup (`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.named_sets import NamedSetDoor

pytestmark = pytest.mark.integration

# The seven routes, by the name a failure message calls them, with the status
# the work order's contract block fixes for each when it is answered.
ADMITTED_STATUS = {
    "list": 200,
    "create": 201,
    "options": 200,
    "read": 200,
    "edit": 200,
    "delete": 204,
    "preview": 200,
}

ROUTES = tuple(ADMITTED_STATUS)

# The four sessions that are not a leadership session. `none` is criterion 1's
# unauthenticated call — no header and an emptied cookie jar — and the other
# three are minted.
REFUSED_SESSIONS = ("none", "student", "instructor", "two-hat instructor")


def ask(door: NamedSetDoor, route: str, *, token: Any) -> Any:
    """One request to one of the seven routes, carrying exactly the named credential.

    The set it names is the one this world's leadership person defined, so an
    admitted call reaches a real row and a refused call is refused for its
    session rather than for a set that is not there — the difference between a
    401 and a 404 is what tells the role gate from the scope read.
    """
    world = door.world
    hers = world.hers
    if route == "list":
        return door.list_sets(token=token)
    if route == "create":
        return door.create(world.a_write(), token=token)
    if route == "options":
        return door.options(token=token)
    if route == "read":
        return door.read(hers.set_id, token=token)
    if route == "edit":
        return door.edit(hers.set_id, world.a_write(name=hers.name), token=token)
    if route == "delete":
        return door.remove(hers.set_id, token=token)
    if route == "preview":
        return door.preview(hers.set_id, token=token)
    raise AssertionError(f"{route!r} is not one of {ROUTES}")


def token_for(door: NamedSetDoor, which: str) -> Any:
    """The credential one refused case carries. `None` means no credential at all."""
    world = door.world
    if which == "none":
        return None
    if which == "student":
        return world.a_student_session()
    if which == "instructor":
        return world.an_instructor_session()
    if which == "two-hat instructor":
        return world.two_hat_sessions()[0]
    raise AssertionError(f"{which!r} is not one of {REFUSED_SESSIONS}")


# ---------------------------------------------------------------------------
# Controls on the instrument. A red in this section means these tests are
# broken, not that the code is.
# ---------------------------------------------------------------------------


def test_the_two_hat_person_holds_both_assignments_and_two_sessions_that_differ_only_in_role(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """CONTROL — green today. The trap is planted before anything is asserted about it.

    Criterion 2's known trap is "a person who is both instructor and leader
    resolves scope by role assignment, not by identity; plant one". If the two
    sessions named different people, or if the person held one assignment rather
    than two, the refusal and the admission below would be about two different
    subjects and the trap would be asserted by nothing (`docs/MISTAKES.md` entry
    30).

    **The mutation it kills:** a fixture that minted the two sessions for two
    people, which is the shape this plant would silently take if the second
    assignment failed to land — and then "her instructor session is refused" is
    a statement about somebody else.
    """
    world = named_sets.world
    instructor, leadership = world.two_hat_sessions()

    hats = named_set_contract.claims_in_session(instructor)
    dean = named_set_contract.claims_in_session(leadership)
    person = named_set_contract.person_id_claim

    assert hats.get(person) == dean.get(person) is not None, (
        f"The two minted sessions name {hats.get(person)!r} and {dean.get(person)!r}. They are "
        "meant to be one person wearing two hats: the whole of criterion 2's trap is that the same "
        "person is refused through one session and admitted through the other."
    )
    assert hats.get(named_set_contract.subject_claim) == dean.get(named_set_contract.subject_claim)
    assert len(world.rows.graph.assignments_of(world.two_hat_person_id)) == 2, (
        "The two-hat person does not hold two assignments. With one of them missing she is an "
        "ordinary instructor or an ordinary dean, and this module's most interesting pair says "
        "nothing."
    )


def test_the_minted_leadership_session_carries_what_the_launched_one_carries(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """CONTROL — green today. A minted token is the same three claims a launch issues.

    `docs/MISTAKES.md` entry 35: a guard that only ever reports absence cannot
    say what it can see. Three of the four refused sessions below are minted, so
    a minting that produced a token this application rejects for a reason of its
    own would turn every one of those refusals into a pass that says nothing
    about a role gate.

    **The mutation it kills:** a `minted` that drops the person claim or signs
    with a secret out of `os.environ` rather than out of the mapping the
    application was built under (`docs/MISTAKES.md` entry 40) — either produces
    a token refused for a reason no test here is about.
    """
    world = named_sets.world
    launched = named_set_contract.claims_in_session(world.door.token)
    reminted = named_set_contract.claims_in_session(
        world.a_leadership_session_for_the_launched_leader()
    )

    for claim in (
        named_set_contract.subject_claim,
        named_set_contract.person_id_claim,
        named_set_contract.user_id_claim,
    ):
        assert str(reminted.get(claim)) == str(launched.get(claim)), (
            f"The re-minted leadership session carries {reminted.get(claim)!r} for `{claim}` and "
            f"the launched one carries {launched.get(claim)!r}. The two are meant to be the same "
            "session issued twice; if they are not, a refusal of a minted token says nothing about "
            "the role it names."
        )


# ---------------------------------------------------------------------------
# Criterion 1, both directions, per route.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route", ROUTES, ids=ROUTES)
def test_a_leadership_session_is_answered_by_every_named_set_route(
    named_sets: NamedSetDoor, named_set_contract: Any, route: str
) -> None:
    """The admitted half of criterion 1, per route, over HTTP against the built application.

    This is the half that keeps the refusals honest: an application that never
    registered the router refuses every session that asks, and a module
    asserting only refusals would call that a pass (`docs/MISTAKES.md` entry 3).

    **The mutations it kills:** the router built and never included in
    `create_app`; `options` declared *after* `{set_id}`, which makes
    `/leadership/comparison-sets/options` parse as a uuid and answer 422 to a
    session that is entitled to it; and a write route wired to the read
    dependency, which answers here and is caught by the CSRF sweep instead.

    **Expected red before E5-06 lands:** a FAILED naming the router, because the
    application answers 404 to a path nothing serves.
    """
    answered = ask(named_sets, route, token=named_sets.door.token)

    assert answered.status_code == ADMITTED_STATUS[route], (
        f"The `{route}` route answered {answered.status_code} to the leadership session this "
        f"world launched; the contract fixes {ADMITTED_STATUS[route]}. Body begins "
        f"{answered.text[:400]!r}."
    )
    assert answered.headers.get(named_set_contract.cache_control_header) == (
        named_set_contract.no_store
    ), (
        f"The `{route}` route answered with "
        f"`{named_set_contract.cache_control_header}: "
        f"{answered.headers.get(named_set_contract.cache_control_header)!r}`. Every route in this "
        f"application's API sets `{named_set_contract.no_store}` — a leadership answer sitting in "
        "a shared cache is a set definition served to whoever asks next."
    )


@pytest.mark.parametrize("route", ROUTES, ids=ROUTES)
@pytest.mark.parametrize("session", REFUSED_SESSIONS, ids=REFUSED_SESSIONS)
def test_a_session_that_is_not_leadership_is_refused_by_every_named_set_route(
    named_sets: NamedSetDoor, named_set_contract: Any, route: str, session: str
) -> None:
    """The refused half of criterion 1, per route and per session, with the layer pinned.

    Four sessions: none at all, a student, an instructor, and the two-hat
    person's instructor session — the last being criterion 2's trap, where the
    person *is* a leader and the session is not.

    **The body is what pins the layer.** A 401 is answered by several things in
    this stack; `NOT_LEADERSHIP` is the one sentence the work order puts on the
    dependency, so a body carrying it says the gate ran in `app.api.deps` before
    any handler read a set. A refusal test reading the status alone would be
    satisfied by a route that refused for a reason nobody chose
    (`docs/MISTAKES.md` entry 3, and the ticket's second known trap).

    **The mutations it kills:** a role gate written as "not a student", which
    admits the instructor sessions; a gate keyed on the person's *assignments*
    rather than on the session's role, which admits the two-hat person's
    instructor session and is the exact defect the trap exists to catch; a
    dependency declared on some routes and not others; and a 403 in place of the
    401 + Bearer challenge, which tells a client it is authenticated when it is
    not.

    **Expected red before E5-06 lands:** a FAILED naming the copy constant
    `NOT_LEADERSHIP`, which no module under `app.copy` declares yet.
    """
    expected = named_set_contract.sentence(named_set_contract.not_leadership)

    answered = ask(named_sets, route, token=token_for(named_sets, session))

    assert answered.status_code == named_set_contract.role_refused, (
        f"The `{route}` route answered {answered.status_code} to the {session} session; E5-06 "
        f"refuses it with {named_set_contract.role_refused}. Body begins "
        f"{answered.text[:400]!r}.\n\n"
        "A 404 here means the router is not registered and this test is not yet about a gate; a "
        "200 means the gate is not there at all."
    )
    assert named_set_contract.detail_of(answered) == expected, (
        f"The `{route}` route refused the {session} session with "
        f"{named_set_contract.detail_of(answered)!r} rather than with the `NOT_LEADERSHIP` "
        f"sentence {expected!r}. The sentence is how this test says *which layer* refused: the "
        "dependency, before a handler read anything."
    )
    assert answered.headers.get(named_set_contract.authenticate_header), (
        f"The `{route}` route refused the {session} session with no "
        f"`{named_set_contract.authenticate_header}` header. The work order settles 'the same "
        "401 + Bearer challenge shape' the student and instructor dependencies answer with."
    )


@pytest.mark.parametrize("route", ROUTES, ids=ROUTES)
def test_the_two_hat_persons_leadership_session_is_admitted_where_her_instructor_one_was_refused(
    named_sets: NamedSetDoor, route: str
) -> None:
    """Criterion 2's trap, the other way round: the same person, admitted through the other hat.

    The refusal above proves that her instructor session is turned away. On its
    own that is equally explained by a gate that refuses *her* — by person, by
    assignment, by anything about the human being — and the product's rule is
    that a session is judged by the role it names. So the same person's
    leadership session must be answered by the same route.

    **The mutation it kills:** a gate that resolves the session to a person and
    then reads that person's assignments, admitting or refusing by identity.
    Such a gate would admit her instructor session (she holds a `DEAN` row) and
    is caught by the refusal above; a gate that refused both would be caught
    here.

    **Expected red before E5-06 lands:** a FAILED naming the router.
    """
    _instructor, leadership = named_sets.world.two_hat_sessions()

    answered = ask(named_sets, route, token=leadership)

    assert answered.status_code == ADMITTED_STATUS[route], (
        f"The `{route}` route answered {answered.status_code} to the leadership session of the "
        f"person who holds both hats; it answers {ADMITTED_STATUS[route]} to the leadership "
        "session this world launched, and the two differ in nothing but who is holding them. Body "
        f"begins {answered.text[:400]!r}."
    )


# ---------------------------------------------------------------------------
# Criterion 6: every route composes `deps.py`'s chain.
# ---------------------------------------------------------------------------


def test_every_named_set_route_declares_one_of_the_two_leadership_dependencies(
    named_sets: NamedSetDoor, named_set_contract: Any
) -> None:
    """Criterion 6: no bespoke session read — the gate is a declared dependency.

    The behavioural pair above says the gate *runs*; this says it is held where
    every sweep in this repository can see it. `docs/MISTAKES.md` entry 47 is
    why both exist: a sweep over the route table answers "is the dependency
    there", never "does the gate run", and a route whose behaviour lives
    anywhere but its endpoint is inert at dispatch while staying visible to
    every walk.

    Reads must hold `require_leadership` and writes `csrf_verified_leadership`,
    matched as **objects** in the route's whole dependency graph — a route whose
    graph happens to contain something else spelled the same way is not a route
    carrying this project's gate.

    **The mutations it kills:** a handler calling `session_from_request` itself,
    which is invisible to the §4.1 item-1 route inventory derived from these
    dependencies; a write route holding the read dependency, which leaves it
    without ADR 0089's double-submit check; and the gate attached at
    `include_router(..., dependencies=[...])`, which on the pinned FastAPI
    reaches no route at all (ADR 0140).

    **Expected red before E5-06 lands:** a FAILED naming `require_leadership` as
    a symbol `app.api.deps` does not expose.
    """
    from fixtures.routing import dependencies_of, every_route

    read = named_set_contract.dependency(named_set_contract.require_leadership_name)
    write = named_set_contract.dependency(named_set_contract.csrf_leadership_name)
    named_set_contract.api()

    routes = [
        route
        for route in every_route(named_sets.door.application)
        if getattr(getattr(route, "endpoint", None), "__module__", None)
        == named_set_contract.api_module
    ]

    def described(route: Any) -> str:
        methods = sorted(str(method).upper() for method in (getattr(route, "methods", None) or []))
        return f"{methods} {getattr(route, 'path', '?')}"

    assert len(routes) == len(ROUTES), (
        f"`{named_set_contract.api_module}` defines {len(routes)} routes on the built application "
        f"and the contract fixes {len(ROUTES)}: {[described(route) for route in routes]}."
    )

    carried = {}
    for route in routes:
        methods = {str(method).upper() for method in (getattr(route, "methods", None) or set())}
        dependant = getattr(route, "dependant", None)
        graph = [] if dependant is None else dependencies_of(dependant)
        wanted = read if methods <= {"GET", "HEAD", "OPTIONS"} else write
        carried[described(route)] = wanted in graph

    missing = sorted(name for name, held in carried.items() if not held)
    assert not missing, (
        f"These named-set routes declare neither of the dependencies their method calls for: "
        f"{missing}. A read carries `{named_set_contract.require_leadership_name}` and a write "
        f"carries `{named_set_contract.csrf_leadership_name}`, declared and never called, so that "
        "the session read happens in the one module SPEC §4.1's route inventory is derived from."
    )
