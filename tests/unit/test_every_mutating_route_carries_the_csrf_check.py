"""Nothing may write without the CSRF check unless the ledger below says why — ticket E3-07.

Carried from E2 (`docs/tickets/e3/carried-from-e2.md`): "`require_student` and
`csrf_verified_student` sit beside each other and nothing makes a writing route
reach for the checked one, so the next mutating route is one import away from
being unprotected in the way that reads as fine in review." Its done-when is this
module — "a sweep over the built application's routes, asserted in both
directions so a stale exemption fails as loudly as an unguarded route".

**The inventory is the built application's own route table.** Not a list somebody
maintains: a hand-kept inventory is how a new route joins a system with nothing
swept over it (`docs/MISTAKES.md` entry 2). `app.main.create_app()` is built here
and walked with `tests/fixtures/routing.py::every_route`, because on the pinned
FastAPI `include_router` appends an `_IncludedRouter` carrying no `path` and no
`dependant` and the obvious walk over `application.routes` sees four
documentation paths and nothing this project serves (dispute E2-04-01).

**What counts as a mutating route, which is this sweep's whole inventory.** Every
route object carrying a `methods` attribute where `methods is None` — the
any-method registration `backend/app/api/dev.py` uses, which matches every verb —
or where `set(methods) - {"GET", "HEAD", "OPTIONS"}` is non-empty. The rule is by
method and nothing else: not by body, not by anything a route declares about
itself, because those are properties an author chooses per route and this
inventory has to hold routes whose author never heard of it.

**Its disclosed limits, written down the way the denial-module sweep's were.**
Three things are outside this sweep by construction, and each is a fact rather
than an oversight:

  - **a state-changing `GET` escapes it.** A route registered for `GET` alone is
    not in the inventory however much it writes. Nothing structural closes this;
    what closes it is that a `GET` which writes is a defect of its own, caught by
    review rather than here.
  - **a mutating endpoint inside a `Mount` escapes it.** A `Mount` carries no
    `methods` attribute, so it is not in the inventory and neither is anything
    behind it. Today this application mounts one thing, the SPA's static files
    (`backend/app/main.py`), which serves `GET` and nothing else.
  - **a WebSocket route escapes it.** A `WebSocketRoute` carries no `methods`
    either. There are none in this tree today, and the day one arrives it is
    outside this sweep until somebody widens the rule deliberately.
  - **an include-level dependency is refused rather than seen.** A check attached
    as `include_router(..., dependencies=[...])` reaches no route on the pinned
    `fastapi` 0.141.1 — measured on 2026-09-05 when this module's own control
    came back empty: `route.dependencies` is `[]` and the `dependant` graph holds
    only the endpoint's own dependencies, the list surviving on the wrapper's
    private `include_context.dependencies` and nowhere else. Reading it would
    mean accumulating private state down through nested includes, which is the
    closed-set guard defeated one level out, so the sweep **fails loudly** on any
    include carrying dependencies and names where to attach it instead. This is
    the one disclosed limit that is not a blind spot: the attachment cannot pass
    unnoticed, it simply cannot be used. ADR 0140 records the measurement and the
    refusal (E3-07's work order, D13a).

**The check is held in two currencies, and each has a control that finds it.**
`docs/MISTAKES.md` entry 35 is the recurring shape here — a guard that enumerates
the ways a privilege can be held misses the way the design actually uses:

  1. **The dependency.** `app.api.deps.csrf_verified_student`, matched as the
     **object** and never by name, anywhere in the route's `dependant` graph at
     any depth. A route may hold it as a parameter default, in the route
     decorator's `dependencies=`, or on its `APIRouter`, and all three are shown
     found below on routes that certainly have them. A fourth attachment exists
     and is **refused rather than read** — see the fourth disclosed limit.
  2. **The route class.** `isinstance(route, app.api.dev.DevControlRoute)`.
     A route appended straight onto `router.routes` carries no dependency graph
     at all — the two clock controls are exactly that shape — so a sweep reading
     only currency 1 could not see a same-origin check written into a route class
     even when it was there.

**What the ledger may hold, and what an entry costs.** Four entries, each a path
mapped to one sentence saying why that route cannot carry the check. An entry
costs the sentence and both directions of assertion below: the path must still be
a mutating route this application serves, and the route must carry **neither**
currency, so an exemption that has quietly become unnecessary is red and the
ledger shrinks. `/dev/passback` is deliberately not on it — a development route
is refused outside development by the environment guard, which is a different
control from CSRF (the ticket's own known trap).

**Which failure a red here is.** Before E3-07 lands, every test naming
`DevControlRoute` is expected red on a `pytest.fail` saying `app.api.dev` exposes
no such class — a plain call in the test body, never in a fixture, so an unbuilt
tree reads as FAILED naming the deliverable rather than as a wall of setup errors
(`docs/MISTAKES.md` entry 44).

**The controls come first and they must be green today. A red in that section
means these tests are broken, not the code.**
"""

import importlib
from typing import Any, NamedTuple

import pytest
from fixtures.dev_console import (
    ANY_METHOD_ROUTE,
    DEV_CONTROL_ROUTE,
    any_method_route_class,
    declared_passback_path,
    dev_control_route_class,
)
from fixtures.line_item_creation import named_in
from fixtures.routing import (
    INCLUDE_CONTEXT_ATTRIBUTE,
    INCLUDE_CONTEXT_DEPENDENCIES,
    INCLUDED_ROUTER_ATTRIBUTE,
    dependencies_of,
    every_route,
)
from fixtures.submit import submit_route

ENVIRONMENT_VARIABLE = "ENVIRONMENT"

# The whole `/dev` surface, and this sweep, are read under the one environment
# where every route this project serves is registered and reachable (ADR 0063,
# ADR 0079). Stated here rather than inherited, which is `docs/MISTAKES.md` entry
# 40's rule.
DEVELOPMENT = "development"

# Where currency 1 comes from. `app.api.deps` is E2-08's; currency 2's names and
# the trigger's path are E3-07's and are imported above from
# `tests/fixtures/dev_console.py`, the one place this ticket's settled names are
# spelled (`docs/MISTAKES.md` entry 13).
DEPS_MODULE = "app.api.deps"
CSRF_DEPENDENCY = "csrf_verified_student"

# The paths this module names. Each is settled somewhere outside this file:
# `/lti/login` and `/lti/launch` by the two mocks' own configuration
# (`tests/fixtures/doors.py`) and the clock pair by E2-04's work order. The
# submit route is **not** named here — E2-08 settles its module and not its URL,
# so it is discovered through `tests/fixtures/submit.py::submit_route`, the one
# helper that asks that question.
LTI_LOGIN_PATH = "/lti/login"
LTI_LAUNCH_PATH = "/lti/launch"
DEV_CLOCK_SET_PATH = "/dev/clock"
DEV_CLOCK_CLEAR_PATH = "/dev/clock/clear"

# The methods that read. A route answering only these is not in the inventory.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# What each currency is called in a failure message, so a reader can tell which
# of the two a route was found by.
BY_DEPENDENCY = f"the `{CSRF_DEPENDENCY}` dependency"
BY_ROUTE_CLASS = f"a `{DEV_CONTROL_ROUTE}` registration"

# The shortest a ledger sentence may be. A number rather than a judgement,
# because what this enforces is that an entry costs something: an exemption added
# with `""` or `"dev"` beside it is how a guard becomes a formality, and the
# ticket names that outcome by hand ("an exemption added without a sentence is
# how a guard becomes a formality").
SHORTEST_LEDGER_SENTENCE = 60

# ---------------------------------------------------------------------------
# The exemption ledger: a path, and one sentence saying why that route cannot
# carry the check. Four entries, and every one of them is asserted in both
# directions below.
# ---------------------------------------------------------------------------

EXEMPTIONS: dict[str, str] = {
    LTI_LOGIN_PATH: (
        "No session exists to bind a double-submit token to at the login leg — this is the "
        "request that begins one. The handshake's `state`, held server-side since E1-08, is this "
        "door's anti-forgery."
    ),
    LTI_LAUNCH_PATH: (
        "A launch is a deliberately cross-site POST: the platform's own form targets it from "
        "another origin, so a same-origin or double-submit rule would refuse every real launch. "
        "The `id_token`'s signature, its `nonce` and the stored `state` are the defence, and the "
        "route mints the session rather than riding one."
    ),
    DEV_CLOCK_SET_PATH: (
        "Appended as an any-method route with no dependency graph, and posted by a console page "
        "that holds no session, so there is neither a token to double-submit nor a dependency to "
        "hang the check on. It is development-only by the gate inside the handler; the residual "
        "risk — a cross-site page moving a developer's clock — is accepted here by name."
    ),
    DEV_CLOCK_CLEAR_PATH: (
        "Appended as an any-method route with no dependency graph, and posted by a console page "
        "that holds no session, so there is neither a token to double-submit nor a dependency to "
        "hang the check on. It is development-only by the gate inside the handler; the residual "
        "risk — a cross-site page moving a developer's clock — is accepted here by name."
    ),
}


# ---------------------------------------------------------------------------
# Currency 1's deliverable, named where a test can fail on it rather than error.
# Currency 2's guards — `dev_control_route_class`, `any_method_route_class` and
# `declared_passback_path` — are imported above from
# `tests/fixtures/dev_console.py` and behave the same way: plain functions,
# called as the first statement of a test body and never from a fixture, so an
# unbuilt tree reads as FAILED naming the deliverable (`docs/MISTAKES.md` entry
# 44).
# ---------------------------------------------------------------------------


def csrf_dependency() -> Any:
    """`app.api.deps.csrf_verified_student` — the object, which is currency 1."""
    try:
        module = importlib.import_module(DEPS_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (
            absent == DEPS_MODULE or DEPS_MODULE.startswith(f"{absent}.")
        ):
            raise
        pytest.fail(
            f"`{DEPS_MODULE}` does not exist. E1-13 puts this project's shared route dependencies "
            "there and E2-08 adds the CSRF-checked student session beside `require_student`."
        )
    return named_in(
        module,
        CSRF_DEPENDENCY,
        "E2-08 ships it: the student-session dependency that also requires ADR 0089's "
        "double-submit token from a request whose session rides the cookie. It is the dependency "
        "this sweep requires of every mutating route, so without it there is no check to sweep for.",
    )


# ---------------------------------------------------------------------------
# The instrument.
# ---------------------------------------------------------------------------


class NoRouteIsThis:
    """A class no route is an instance of, passed where currency 2 is not the subject.

    The ledger's own machinery is asserted below on applications built in this
    file, which carry no `DevControlRoute` and are not about it. Passing this
    rather than the real class keeps those controls **green on today's tree**, so
    a red in them is a broken instrument rather than an unbuilt deliverable —
    which is the whole reason a control section exists.
    """


def is_mutating(route: Any) -> bool:
    """Whether `route` is in this sweep's inventory. See the module docstring for the rule."""
    if not hasattr(route, "methods"):
        return False
    methods = route.methods
    if methods is None:
        return True
    return bool({str(method).upper() for method in methods} - SAFE_METHODS)


def included_paths(route: Any) -> list[str]:
    """The paths of the router one `_IncludedRouter` wrapped, for a message that names it."""
    included = getattr(route, INCLUDED_ROUTER_ATTRIBUTE, None)
    if included is None:
        return []
    return sorted(
        path
        for path in (getattr(member, "path", None) for member in included.routes)
        if isinstance(path, str)
    )


def refuse_include_level_dependencies(application: Any) -> None:
    """Fail if any reachable `include_router(...)` was given `dependencies=`.

    **The ruling of 2026-09-05 (E3-07's work order, D13a), and it is a
    measurement rather than a preference.** On the pinned `fastapi` 0.141.1 a
    dependency passed at the include is attached to no route: `route.dependencies`
    is `[]` and the `dependant` graph holds only the endpoint's own. It survives
    on the wrapper's private `include_context.dependencies` and nowhere else. A
    sweep whose inventory is the dependant graph therefore **cannot** see it, and
    the two ways out are to attribute private state down through nested includes —
    the defeated-one-level-out shape — or to refuse the attachment. This refuses
    it, and says where to put the dependency instead.

    Run on every walk rather than in one test, so an include-level dependency
    added to `app.main` tomorrow reddens the sweep on the day it lands rather than
    being reported as a route carrying nothing.

    **The pinned attribute names are required to exist**, and that is the half a
    reader should look at twice. Reading them through a `getattr` default would
    make a FastAPI that renames either one answer "no include-level dependencies
    anywhere" for the whole tree — a guard gone silently blind while every test
    around it stays green (`docs/MISTAKES.md` entry 3). So an `_IncludedRouter`
    missing either name is reported as a stale pin, in its own sentence, naming
    the constant to re-measure.
    """
    for route in every_route(application):
        if getattr(route, INCLUDED_ROUTER_ATTRIBUTE, None) is None:
            continue
        if not hasattr(route, INCLUDE_CONTEXT_ATTRIBUTE):
            pytest.fail(
                f"An `{type(route).__name__}` carries `{INCLUDED_ROUTER_ATTRIBUTE}` and no "
                f"`{INCLUDE_CONTEXT_ATTRIBUTE}`; it carries "
                f"{sorted(name for name in dir(route) if not name.startswith('__'))}.\n\n"
                "That pin is how this sweep refuses an include-level dependency it cannot see, and "
                "it was measured against `fastapi` 0.141.1 on 2026-09-05. A FastAPI that renamed it "
                "must be re-measured and the constant in `tests/fixtures/routing.py` moved in the "
                "same change: read through a default instead, this check would answer 'no "
                "include-level dependencies' for every application forever."
            )
        context = getattr(route, INCLUDE_CONTEXT_ATTRIBUTE)
        if not hasattr(context, INCLUDE_CONTEXT_DEPENDENCIES):
            pytest.fail(
                f"`{INCLUDED_ROUTER_ATTRIBUTE}`'s `{INCLUDE_CONTEXT_ATTRIBUTE}` is {context!r}, "
                f"which has no `{INCLUDE_CONTEXT_DEPENDENCIES}` attribute. The 2026-09-05 "
                "measurement found the include's dependency list there, read as an attribute; if "
                "this build holds it as a mapping key or under another name, re-measure and move "
                "the constant in `tests/fixtures/routing.py` rather than letting this check pass "
                "over something it can no longer read."
            )
        declared = getattr(context, INCLUDE_CONTEXT_DEPENDENCIES) or []
        if declared:
            pytest.fail(
                f"A router covering {included_paths(route)} was registered with "
                f"`include_router(..., {INCLUDE_CONTEXT_DEPENDENCIES}=[...])`, carrying "
                f"{len(declared)} dependency(ies).\n\n"
                "This sweep refuses that attachment rather than reading it. Measured on `fastapi` "
                "0.141.1: a dependency passed at the include reaches no route — `route.dependencies` "
                "is empty and the `dependant` graph holds only the endpoint's own — so every route "
                "under this include looks unguarded to any sweep derived from that graph, including "
                "this one, and would have to be excused by hand.\n\n"
                "Attach it where the graph holds it: `APIRouter(dependencies=[...])` on the router "
                "itself, `@router.post(..., dependencies=[...])` on the route, or a parameter "
                "default. All three are shown found on routes that certainly have them in "
                "`test_every_way_the_csrf_dependency_can_be_held_is_found_on_a_route_that_has_it`."
            )


def mutating_routes(application: Any) -> list[Any]:
    """Every route of `application` that answers a method which is not a read.

    The include-level refusal runs first, on every walk, so an
    `include_router(..., dependencies=[...])` anywhere in the application reddens
    whatever asked for the inventory rather than showing up as a set of routes
    that carry nothing.
    """
    refuse_include_level_dependencies(application)
    return [route for route in every_route(application) if is_mutating(route)]


def path_of(route: Any) -> str:
    """One route's path, or a description of it, so a message names something findable."""
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else f"<{type(route).__name__} with no path: {route!r}>"


def paths_of(routes: list[Any]) -> set[str]:
    """The paths of a set of routes."""
    return {path_of(route) for route in routes}


def methods_of(route: Any) -> list[str]:
    """The methods a route answers, spelled for a message. `None` means every one of them."""
    methods = getattr(route, "methods", None)
    return ["ANY"] if methods is None else sorted(str(method).upper() for method in methods)


def currencies_of(route: Any, *, dependency: Any, route_class: type) -> list[str]:
    """Which of the two currencies this route holds the check in, if either.

    The dependency is matched on the **object** rather than on its name — a route
    whose graph happens to contain some other `csrf_verified_student` is not a
    route that carries this project's check — and the route class by
    `isinstance`, which is the only thing an appended route offers to read.
    """
    found: list[str] = []
    dependant = getattr(route, "dependant", None)
    if dependant is not None and dependency in dependencies_of(dependant):
        found.append(BY_DEPENDENCY)
    if isinstance(route, route_class):
        found.append(BY_ROUTE_CLASS)
    return found


class LedgerReport(NamedTuple):
    """What the ledger and the route table say about each other, in three lists.

    All three are computed together and each is asserted by its own test, so a
    failure names one direction rather than "the ledger is wrong".
    """

    stale: list[str]
    now_guarded: dict[str, list[str]]
    unguarded: dict[str, list[str]]


def ledger_report(
    application: Any,
    ledger: dict[str, str],
    *,
    dependency: Any,
    route_class: type,
) -> LedgerReport:
    """Compare `ledger` against what `application` actually serves, both directions."""
    routes = mutating_routes(application)
    served = paths_of(routes)
    stale = sorted(path for path in ledger if path not in served)
    now_guarded: dict[str, list[str]] = {}
    unguarded: dict[str, list[str]] = {}
    for route in routes:
        path = path_of(route)
        carried = currencies_of(route, dependency=dependency, route_class=route_class)
        if path in ledger:
            if carried:
                now_guarded[path] = carried
        elif not carried:
            unguarded.setdefault(path, methods_of(route))
    return LedgerReport(stale=stale, now_guarded=now_guarded, unguarded=unguarded)


def application_in(environment: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    """`create_app()` with `ENVIRONMENT` set to `environment`.

    Built inside the test rather than in a fixture, the way
    `tests/unit/test_dev_console_exposure.py` builds it, so a factory that raises
    fails one test loudly instead of erroring every collection. No database is
    touched: nothing here serves a request.
    """
    from app.main import create_app

    monkeypatch.setenv(ENVIRONMENT_VARIABLE, environment)
    return create_app()


class ApplicationUnderTest(NamedTuple):
    """An object with an `.app`, which is all `submit_route` asks of its argument.

    `tests/fixtures/submit.py::submit_route` discovers the one `POST` route
    `app.api.student` defines and takes a `TestClient` because its own callers
    have one. This sweep has an application and no client, and asking that
    question a second way here would be a second inventory of "where is the
    submit route" (`docs/MISTAKES.md` entry 13).
    """

    app: Any


# ---------------------------------------------------------------------------
# Controls on the instrument. **A red here means these tests are broken, not the
# code**, and every one of them is green on a tree where E3-07 is unbuilt.
# ---------------------------------------------------------------------------


def test_the_inventory_finds_a_planted_post_route_and_spares_its_get_twin() -> None:
    """The method rule, both directions, on an application built here.

    `docs/MISTAKES.md` entry 3: a sweep that reports "every mutating route is
    guarded" over an inventory it cannot fill is silence dressed as a pass. So a
    `POST` route with no dependency at all must be **in** the inventory, and a
    `GET` route identical but for its method must not.

    **Registered through `include_router`, which is the half that matters.** On
    the pinned FastAPI a router's routes are not copied onto the application; an
    `_IncludedRouter` is appended carrying no `path` and no `methods`, and a walk
    over `application.routes` finds nothing of it (dispute E2-04-01). The real
    application registers every one of its routers that way, so a control that
    decorated the application object directly would prove the sweep works on the
    one shape it never meets.

    **The mutations this kills:** a walk without `every_route`'s recursion, which
    reports the real application as serving no mutating route at all and makes
    every assertion below vacuous; and an inventory rule that enrols reads, which
    would be red against every correct application and would be deleted rather
    than fixed.
    """
    from fastapi import APIRouter, FastAPI

    planted_post = "/e3-07-planted/writes"
    planted_get = "/e3-07-planted/reads"
    router = APIRouter()

    @router.post(planted_post)
    def a_planted_write() -> dict[str, str]:
        return {}  # pragma: no cover - never called; only its registration is read

    @router.get(planted_get)
    def a_planted_read() -> dict[str, str]:
        return {}  # pragma: no cover - never called; only its registration is read

    application = FastAPI()
    application.include_router(router)

    found = paths_of(mutating_routes(application))

    assert planted_post in found, (
        f"The inventory did not find `{planted_post}`, a `POST` route registered through "
        f"`include_router`. It found {sorted(found)}. A sweep that cannot see a mutating route "
        "reports a clean application however many unguarded ones it serves; the likeliest cause is "
        "walking `application.routes` rather than `tests/fixtures/routing.py::every_route`."
    )
    assert planted_get not in found, (
        f"The inventory also claimed `{planted_get}`, which answers `GET` and `HEAD` alone. The "
        "rule is by method, and a sweep that enrols reads demands a CSRF check of every page this "
        "project serves."
    )
    assert found == {planted_post}, (
        f"The inventory over an application whose only writing route is `{planted_post}` is "
        f"{sorted(found)}. The extra members are the third thing this control exists to catch: "
        "FastAPI's own four documentation routes are reads and must not be enrolled, and the "
        "`_IncludedRouter` wrapper `include_router` appends carries no path — if it has come to "
        "carry a `methods` attribute on some later FastAPI, it enters the inventory as a route "
        "with no path, on no ledger and holding no currency, and the sweep over the real "
        "application goes red for a reason that has nothing to do with any route."
    )


def test_every_way_the_csrf_dependency_can_be_held_is_found_on_a_route_that_has_it() -> None:
    """Currency 1, found on three routes that certainly hold it, and spared on one that does not.

    `docs/MISTAKES.md` entry 35, which the ticket names as a known trap: "a
    dependency can be attached at the route, at the router, or through a nested
    include, and a sweep that reads only one of the three reports clean over a
    real gap". So every way the **dependant graph** can hold the dependency is
    planted on one application and each must be found:

      - as a parameter default, `_: Any = Depends(csrf_verified_student)`;
      - in the route decorator's `dependencies=[...]`;
      - on the `APIRouter(dependencies=[...])` the route sits on.

    **The fourth way is `include_router(..., dependencies=[...])` and it is not
    here, because it is refused rather than found** — the ruling of 2026-09-05
    (D13a), measured: on `fastapi` 0.141.1 that dependency reaches no route at
    all, so no dependant-graph walk can see it. Its control is
    `test_an_include_level_dependency_is_refused_rather_than_read_off_the_route`
    below, which plants exactly that call and requires the sweep to go red naming
    it. The two tests are the pair: this one says the three legal attachments are
    seen, that one says the fourth is refused instead of silently missed.

    **The near miss it must spare** is a fourth route with none of them: a sweep
    that answered "guarded" for everything would be green over the real gap this
    module exists to close, and would be indistinguishable from a correct one
    until somebody planted this case.

    **The mutation this kills:** matching the dependency by *name* rather than by
    object, which enrols any route whose graph happens to contain something else
    spelled `csrf_verified_student`; and a graph walk one level deep, which finds
    the parameter default and misses a dependency declared on a dependency.

    Green today: `csrf_verified_student` is E2-08's and every mechanism here is
    FastAPI's.
    """
    from fastapi import APIRouter, Depends, FastAPI

    dependency = csrf_dependency()
    by_parameter = "/e3-07-planted/by-parameter-default"
    by_decorator = "/e3-07-planted/by-decorator"
    by_router = "/e3-07-planted/by-router"
    by_nothing = "/e3-07-planted/by-nothing"

    plain = APIRouter()

    @plain.post(by_parameter)
    def held_as_a_parameter_default(_: Any = Depends(dependency)) -> dict[str, str]:
        return {}  # pragma: no cover - never called; only its dependency graph is read

    @plain.post(by_decorator, dependencies=[Depends(dependency)])
    def held_by_the_decorator() -> dict[str, str]:
        return {}  # pragma: no cover - never called; only its dependency graph is read

    @plain.post(by_nothing)
    def held_nowhere() -> dict[str, str]:
        return {}  # pragma: no cover - never called; only its dependency graph is read

    on_the_router = APIRouter(dependencies=[Depends(dependency)])

    @on_the_router.post(by_router)
    def held_by_the_router() -> dict[str, str]:
        return {}  # pragma: no cover - never called; only its dependency graph is read

    application = FastAPI()
    application.include_router(plain)
    application.include_router(on_the_router)

    carried = {
        path_of(route): currencies_of(route, dependency=dependency, route_class=NoRouteIsThis)
        for route in mutating_routes(application)
    }

    for path in (by_parameter, by_decorator, by_router):
        assert carried.get(path) == [BY_DEPENDENCY], (
            f"The sweep read `{path}` as carrying {carried.get(path)}. That route holds "
            f"`{CSRF_DEPENDENCY}` — this test declared it there — and a sweep that cannot see one "
            "of the three ways a dependency reaches the dependant graph reports a clean "
            f"application over a route that has no check at all. What it read of the four planted "
            f"routes: {carried}."
        )
    assert carried.get(by_nothing) == [], (
        f"The sweep read `{by_nothing}` as carrying {carried.get(by_nothing)}, and that route "
        "declares no dependency of any kind. A sweep that finds the check everywhere is green "
        "against exactly the defect this module exists to catch."
    )


def test_an_include_level_dependency_is_refused_rather_than_read_off_the_route() -> None:
    """The fourth attachment: refused loudly, because no dependant-graph walk can see it.

    **The ruling of 2026-09-05 (D13a), and it began as this module's own red.**
    The first version of the control above planted four attachments and required
    all four found; `include_router(..., dependencies=[Depends(dep)])` came back
    carrying nothing, and measuring it against the library said why. On the pinned
    `fastapi` 0.141.1 that dependency is attached to no route at all —
    `route.dependencies` is `[]` and the `dependant` graph holds only the
    endpoint's own — and it survives solely on the wrapper's private
    `include_context.dependencies`. Reading it would mean accumulating private
    state down through nested includes to decide what each route inherited, which
    is the closed-set guard defeated one level out, so the sweep refuses the
    attachment instead and names where to put the dependency.

    **What is planted:** an application built here whose one writing route holds
    the check *only* at the include. The sweep must go red on it, and the failure
    must name the include rather than reporting the route as unguarded — the two
    are different diagnoses and only one of them sends the reader to the line that
    is wrong.

    **The near miss, and it is exercised rather than asserted twice**: an include
    carrying no `dependencies=` passes through untouched. Every other control in
    this section registers its routers exactly that way — `test_the_inventory_
    finds_a_planted_post_route_and_spares_its_get_twin`, the three-attachment
    control above, and the ledger controls below all call plain
    `include_router(router)` — so a refusal that fired on any include at all would
    redden all of them rather than showing up only here. That is the pairing, and
    it is stated rather than duplicated.

    **The mutation this kills:** the refusal check reading
    `include_context.dependencies` through a `getattr` default. Under a FastAPI
    that renamed either name, the default answers "no include-level dependencies"
    for every application forever, the sweep reports a clean tree, and nothing
    else in this module would notice — a guard gone silently blind
    (`docs/MISTAKES.md` entry 3). This plant is what catches it: with the attribute
    unreadable the refusal below does not fire and this test fails.

    Green today: every mechanism here is FastAPI's and `csrf_verified_student` is
    E2-08's.
    """
    from fastapi import APIRouter, Depends, FastAPI

    dependency = csrf_dependency()
    by_include = "/e3-07-planted/by-include"

    through_the_include = APIRouter()

    @through_the_include.post(by_include)
    def held_only_at_the_include() -> dict[str, str]:
        return {}  # pragma: no cover - never called; only its registration is read

    application = FastAPI()
    application.include_router(through_the_include, dependencies=[Depends(dependency)])

    try:
        found = mutating_routes(application)
    except pytest.fail.Exception as refusal:
        # `pytest.fail`'s `Failed` is a `BaseException`, so this catches the
        # refusal and nothing else — an ordinary error inside the walk still
        # travels out as itself rather than being read as the refusal under test
        # (the reasoning `tests/unit/test_a_sanctioned_writer_satisfies_the_
        # chokepoint.py::must_raise` gives about the same class).
        message = str(refusal)
        assert by_include in message, (
            f"The sweep refused the include, and its message does not name `{by_include}` — the "
            f"path under the offending `include_router` call. The message was:\n\n{message}\n\n"
            "A refusal that does not say which include it is about sends the reader looking "
            "through every registration in the application."
        )
        assert INCLUDE_CONTEXT_DEPENDENCIES in message, (
            f"The sweep refused the include without naming `{INCLUDE_CONTEXT_DEPENDENCIES}`, the "
            f"keyword that caused it. The message was:\n\n{message}"
        )
        return

    pytest.fail(
        "The sweep walked an application whose only writing route holds "
        f"`{CSRF_DEPENDENCY}` at `include_router(..., {INCLUDE_CONTEXT_DEPENDENCIES}=[...])` and "
        f"did not refuse: it answered {[path_of(route) for route in found]}.\n\n"
        "Measured on `fastapi` 0.141.1, that dependency reaches no route, so the sweep either "
        "refuses the attachment or reports every route under the include as unguarded and waits "
        "for somebody to excuse them by hand. D13a settles the first. If this test is failing "
        "after a FastAPI upgrade, the likeliest cause is that "
        f"`{INCLUDE_CONTEXT_ATTRIBUTE}.{INCLUDE_CONTEXT_DEPENDENCIES}` was renamed and the check "
        "is now reading nothing — re-measure and move the constants in "
        "`tests/fixtures/routing.py`."
    )


def test_the_structural_currency_finds_an_appended_dev_control_route_not_its_parent() -> None:
    """Currency 2, on the registration shape that carries no dependency graph at all.

    The ticket's first known trap: "a route registered by appending to
    `router.routes` rather than by a decorator is exactly the shape that escapes a
    decorator walk, and `dev.py` already contains two of them". Those two are the
    clock controls and they are exempt; the trigger E3-07 adds is the same shape
    and is **not** exempt, so the sweep needs a currency it can read off such a
    route. `isinstance` is it.

    **The near miss it must spare** is an `AnyMethodRoute` that is not a
    `DevControlRoute`, appended the same way: the parent class carries no origin
    check, and a sweep matching on the parent would report every clock control as
    guarded and would then have nothing to say the day a third any-method route
    is appended without the check.

    **The mutation this kills:** currency 2 written as `type(route).__name__ ==
    "DevControlRoute"`, which a rename breaks silently, or as an `isinstance`
    against `AnyMethodRoute`, which is the near miss below.

    **Expected red before E3-07 lands:** a FAILED naming `DevControlRoute` as a
    class `app.api.dev` does not expose.

    **How the two routes are constructed.** `route_class(path, endpoint)` — the
    `starlette.routing.Route` signature `AnyMethodRoute` extends. The work order
    settles the class and not its constructor, so a `TypeError` here is reported
    as this control's own assumption rather than as a failure of the sweep, and
    the parent is constructed the same way in the same test so the two cases
    cannot come apart.
    """
    from fastapi import APIRouter, FastAPI

    control_class = dev_control_route_class()
    parent_class = any_method_route_class()
    dependency = csrf_dependency()
    control_path = "/e3-07-planted/dev-control"
    parent_path = "/e3-07-planted/any-method"

    def an_endpoint(request: Any) -> Any:
        return None  # pragma: no cover - never called; only the registration is read

    def appended(route_class: Any, path: str) -> Any:
        try:
            return route_class(path, an_endpoint)
        except TypeError as refused:  # pragma: no cover - a red, not a branch
            pytest.fail(
                f"`{route_class.__name__}({path!r}, endpoint)` was refused ({refused}). This "
                "control constructs both route classes with the two positional arguments "
                "`starlette.routing.Route` takes, which is what `AnyMethodRoute` extends. If "
                f"`{DEV_CONTROL_ROUTE}`'s constructor takes something else, that is a decision "
                "E3-07's work order left open and this line is the one to change — the property "
                "under test is `isinstance`, not the signature."
            )

    router = APIRouter()
    router.routes.append(appended(control_class, control_path))
    router.routes.append(appended(parent_class, parent_path))
    application = FastAPI()
    application.include_router(router)

    carried = {
        path_of(route): currencies_of(route, dependency=dependency, route_class=control_class)
        for route in mutating_routes(application)
    }

    assert control_path in carried, (
        f"`{control_path}` is not in the mutating inventory at all; it holds "
        f"{sorted(carried)}. A `{DEV_CONTROL_ROUTE}` appended to a router's routes answers every "
        "method, which the inventory rule counts as mutating — and if the sweep cannot see it, the "
        "route E3-07 adds is outside this sweep on the day it lands."
    )
    assert carried[control_path] == [BY_ROUTE_CLASS], (
        f"The sweep read the appended `{DEV_CONTROL_ROUTE}` as carrying {carried[control_path]}. "
        "It is the one currency an appended route can be read by: there is no dependency graph on "
        "it to find anything else in."
    )
    assert carried.get(parent_path) == [], (
        f"The sweep read an appended `{ANY_METHOD_ROUTE}` as carrying {carried.get(parent_path)}. "
        f"That class carries no origin check — it is what the two clock controls are, and they are "
        "on the ledger for exactly that reason — so a sweep matching the parent class would report "
        "them guarded and would spare the next unchecked any-method route somebody appends."
    )


def test_every_exemption_carries_a_sentence_saying_why() -> None:
    """Criterion 5's price: an exemption without a sentence is how a guard becomes a formality.

    The ticket settles "what the exemption list is allowed to hold, and what a new
    entry costs". This is the cost, made mechanical: an entry is a path **and** a
    sentence long enough to be a reason. A ledger of bare paths would satisfy
    every other assertion in this module while saying nothing about why four
    writing routes in this application have no CSRF check.

    **The mutation this kills:** an entry added with `""`, `"dev"` or `"TODO"`
    beside it, which reads as a ledger entry in a diff and is not one.

    Green today: the ledger is this file's.
    """
    assert EXEMPTIONS, (
        "The exemption ledger is empty, so the both-direction assertions below are about nothing "
        "and the sweep's whole exemption machinery is untested. Four routes in this application "
        "cannot carry the check and each is named here with a sentence."
    )
    thin = {
        path: sentence
        for path, sentence in EXEMPTIONS.items()
        if len(sentence.strip()) < SHORTEST_LEDGER_SENTENCE
    }
    assert not thin, (
        f"These ledger entries carry no reason worth the name: {thin}. An exemption costs a "
        f"sentence of at least {SHORTEST_LEDGER_SENTENCE} characters saying why that route cannot "
        "hold the check — the number is arbitrary and what it enforces is not: a path added with a "
        "word beside it is an exemption nobody argued for."
    )


def test_the_ledger_is_red_on_a_stale_entry_and_on_an_entry_that_now_carries_the_check() -> None:
    """Criterion 4, both directions, planted on applications built here.

    The criterion is that the sweep "is red when an exemption names a route that
    no longer exists, and red when a route that should be exempt is not named —
    both directions, both planted". The second half is the one that decays: an
    exemption written for a route that later grows the check is a permanent hole
    in the sweep, and nothing else would ever notice, so the ledger is required to
    **shrink** rather than merely to be honest when it was written.

    Both are posed against `ledger_report`, the same function the two real-
    application tests below use, so what is proven here is the instrument they
    are read through.

    **The near miss:** a ledger naming a route that exists and carries no check
    must produce no complaint at all — a report that flagged everything would be
    red against a correct application and would be deleted rather than fixed.

    Green today: `csrf_verified_student` is E2-08's, and currency 2 is not the
    subject here, so `NoRouteIsThis` stands in for the class E3-07 owes.
    """
    from fastapi import APIRouter, Depends, FastAPI

    dependency = csrf_dependency()
    exempt_path = "/e3-07-planted/exempt"
    guarded_path = "/e3-07-planted/exempt-but-guarded"
    a_sentence = "Planted by this control; the route is exempt for the length of this test."
    gone_path = "/e3-07-planted/deleted-last-year"

    router = APIRouter()

    @router.post(exempt_path)
    def an_exempt_route() -> dict[str, str]:
        return {}  # pragma: no cover - never called; only its registration is read

    @router.post(guarded_path, dependencies=[Depends(dependency)])
    def an_exempt_route_that_grew_a_check() -> dict[str, str]:
        return {}  # pragma: no cover - never called; only its dependency graph is read

    application = FastAPI()
    application.include_router(router)

    honest = ledger_report(
        application,
        {exempt_path: a_sentence, guarded_path: a_sentence},
        dependency=dependency,
        route_class=NoRouteIsThis,
    )
    assert honest.now_guarded == {guarded_path: [BY_DEPENDENCY]}, (
        f"An exemption naming a route that carries `{CSRF_DEPENDENCY}` was reported as "
        f"{honest.now_guarded}. The ledger has to shrink: an entry excusing a route that is now "
        "checked keeps that route outside the sweep forever, and the day the check is removed "
        "again nothing goes red."
    )
    assert honest.stale == [], (
        f"The report called {honest.stale} stale while this application serves both paths. A "
        "report that flags a live exemption is red against a correct ledger."
    )
    assert honest.unguarded == {}, (
        f"The report called {honest.unguarded} unguarded while every mutating route here is either "
        f"on the ledger or carrying the dependency. A report that flags everything proves nothing "
        "when it flags the real application."
    )

    stale = ledger_report(
        application,
        {exempt_path: a_sentence, gone_path: a_sentence},
        dependency=dependency,
        route_class=NoRouteIsThis,
    )
    assert stale.stale == [gone_path], (
        f"An exemption naming `{gone_path}`, which this application does not serve, was reported "
        f"as {stale.stale}. A stale entry is an excuse nobody can check, and it is the shape a "
        "ledger takes when a route is renamed: the entry goes on excusing a path that is gone "
        "while the route under its new name is swept as if it had never been argued about."
    )

    unnamed = ledger_report(
        application,
        {guarded_path: a_sentence},
        dependency=dependency,
        route_class=NoRouteIsThis,
    )
    assert unnamed.unguarded == {exempt_path: ["POST"]}, (
        f"A mutating route on no ledger and carrying no check was reported as "
        f"{unnamed.unguarded}. That is the carried E2 entry in one line — 'the next mutating route "
        "is one import away from being unprotected in the way that reads as fine in review' — and "
        "if this report cannot see it, neither can the sweep below."
    )


# ---------------------------------------------------------------------------
# Canaries on the real application (criterion 6, and the ticket's appended-pair
# trap). A collector that has gone blind says so here.
# ---------------------------------------------------------------------------


def test_the_submit_route_is_found_carrying_the_csrf_dependency(
    configured_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 6's canary for currency 1, on the one route that certainly has it.

    E2-08's submit path is correct — the carried entry says so in as many words,
    "the submit path itself is correct; the guard is what is missing" — so it is
    the subject a sweep for currency 1 must be shown *finding*. Without this, an
    application whose every route had quietly lost the dependency would satisfy
    the sweep below by having an empty inventory of guarded routes and a ledger
    that happened to cover the rest.

    **The route is discovered, not named.** E2-08 settles the module its route
    lives in and not its URL, so it is found through
    `tests/fixtures/submit.py::submit_route`, the one helper that asks that
    question.

    **The mutation this kills:** a dependency walk that reads only the first
    layer of the graph, or that matches on a name — either reports the submit
    route as unguarded, which is a red naming the wrong file, or reports every
    route as guarded, which is a green over the whole ticket.

    Green today.
    """
    application = application_in(DEVELOPMENT, monkeypatch)
    dependency = csrf_dependency()
    submit_path = submit_route(ApplicationUnderTest(application))

    guarded = {
        path_of(route)
        for route in mutating_routes(application)
        if BY_DEPENDENCY in currencies_of(route, dependency=dependency, route_class=NoRouteIsThis)
    }

    assert submit_path in guarded, (
        f"The sweep does not see `{submit_path}` carrying `{CSRF_DEPENDENCY}`; it sees "
        f"{sorted(guarded)} carrying it. That route is the one this project certainly protects "
        "(E2-08, ADR 0089), so a sweep that cannot find the check there cannot find it anywhere, "
        "and every 'this route is guarded' below would be a statement about a collector that has "
        "gone blind (`docs/MISTAKES.md` entries 3 and 35)."
    )


def test_the_passback_route_is_found_carrying_the_dev_control_currency(
    configured_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 6's canary for currency 2, and the ticket's trap made an assertion.

    The trigger E3-07 adds is a mutating route and is **subject to its own
    sweep**. The ticket names the temptation by hand: "writing the sweep and the
    route in one ticket makes it tempting to exempt the route because it is a
    development route. It is not exempt." So the honest state is not an absence
    from the ledger — it is a presence in the guarded set, found by the currency
    a route with no dependency graph can be read by.

    **The mutation this kills:** `/dev/passback` added to `EXEMPTIONS` instead of
    to `DevControlRoute`, which turns the whole second half of this ticket into a
    line of prose; and a trigger registered as a plain `AnyMethodRoute` beside the
    clock pair, which has no origin check and would be indistinguishable from the
    correct build to every other test in this module.

    **Expected red before E3-07 lands:** a FAILED naming `DevControlRoute` as a
    class `app.api.dev` does not expose. Once it exists and the route is not
    registered with it, the red is the assertion below.
    """
    application = application_in(DEVELOPMENT, monkeypatch)
    dependency = csrf_dependency()
    route_class = dev_control_route_class()
    passback_path = declared_passback_path()

    carried = {
        path_of(route): currencies_of(route, dependency=dependency, route_class=route_class)
        for route in mutating_routes(application)
    }

    assert passback_path in carried, (
        f"`{passback_path}` is not a mutating route of this application; the mutating routes are "
        f"{sorted(carried)}. E3-07 registers the development passback trigger there, as a POST, "
        "and until it is registered the assertion below is about a route nobody wrote."
    )
    assert passback_path not in EXEMPTIONS, (
        f"`{passback_path}` is on the exemption ledger. `/dev` routes are refused outside "
        "development by the environment guard, which is a **different control** from CSRF: a "
        "developer's browser, on a page some other site served, can be made to POST to a "
        "development stack. The trigger runs a passback against a real gradebook, so it carries "
        "the check like every other writing route."
    )
    assert BY_ROUTE_CLASS in carried[passback_path], (
        f"`{passback_path}` carries {carried[passback_path]}. E3-07's work order (D4) registers it "
        f"as a `{DEV_CONTROL_ROUTE}`, whose wrapper refuses a request whose `Origin` is not this "
        "application's own — and that class is the only currency a route appended with no "
        "dependency graph can hold the check in."
    )


def test_the_appended_clock_pair_is_in_the_mutating_inventory(
    configured_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The proof that the walk sees routes nobody decorated — the ticket's first trap.

    "A closed-set guard is defeated one level out. The sweep's inventory is the
    routes it can see; a route registered by appending to `router.routes` rather
    than by a decorator is exactly the shape that escapes a decorator walk, and
    `dev.py` already contains two of them. Build the inventory from the
    application's own route table, and prove it finds the appended pair."

    This is that proof, on the real application rather than on a plant: both clock
    paths must be in the mutating inventory. They are also the ledger's two
    riskiest entries, and an inventory that could not see them would report the
    ledger's other direction — "every exempt path is still served" — as a failure
    for a reason that has nothing to do with the ledger.

    **The mutation this kills:** an inventory built by walking decorated route
    functions, or one that requires `methods` to be a non-empty set, which drops
    an any-method registration whose `methods` is `None`.

    Green today: E2-04 shipped both routes.
    """
    application = application_in(DEVELOPMENT, monkeypatch)
    served = paths_of(mutating_routes(application))

    missing = [path for path in (DEV_CLOCK_SET_PATH, DEV_CLOCK_CLEAR_PATH) if path not in served]
    assert not missing, (
        f"The mutating inventory does not hold {missing}; it holds {sorted(served)}. Those two are "
        "appended to `dev.router.routes` as any-method registrations rather than declared with a "
        "decorator, and they write the row that moves the clock every survey window, term lookup "
        "and live-enrollment check reads. If this sweep cannot see them it cannot see the shape "
        "E3-07's own trigger is registered in either."
    )


# ---------------------------------------------------------------------------
# The sweep, over the application this project actually serves.
# ---------------------------------------------------------------------------


def test_every_exemption_names_a_mutating_route_this_application_still_serves(
    configured_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 4's first direction: a stale exemption fails as loudly as an unguarded route.

    An entry naming a path nothing serves is an excuse nobody can check, and it is
    what the ledger becomes when a route is renamed: the entry goes on excusing a
    path that is gone, while the route under its new name is swept as if it had
    never been argued about — or, worse, is added to the ledger a second time by
    somebody who reads the file and assumes the case was settled.

    **The mutation this kills:** a route deleted or renamed with the ledger left
    alone. **The near miss it must not pass on:** a path that is served but only
    for reads, which is not in the mutating inventory and is therefore an
    exemption from a sweep that was never going to reach it.

    `test_the_ledger_is_red_on_a_stale_entry_and_on_an_entry_that_now_carries_the_check`
    is the control that this direction can fail at all.
    """
    application = application_in(DEVELOPMENT, monkeypatch)
    report = ledger_report(
        application,
        EXEMPTIONS,
        dependency=csrf_dependency(),
        route_class=NoRouteIsThis,
    )

    assert report.stale == [], (
        f"The ledger excuses {report.stale}, and this application serves no mutating route at any "
        f"of those paths. Its mutating routes are {sorted(paths_of(mutating_routes(application)))}."
        "\n\nAn exemption is an argument about a specific route; when the route goes, the argument "
        "goes with it, and the entry is deleted in the same change rather than left as a reason "
        "the next reader cannot check."
    )


def test_no_exemption_names_a_route_that_now_carries_the_check(
    configured_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 4's second direction: the ledger shrinks when a route stops needing it.

    An exemption is a hole in this sweep for as long as it stands. A route that
    has since grown either currency does not need one, and leaving the entry there
    keeps that route outside the sweep permanently — so the day somebody removes
    the check again, nothing goes red. This is the direction that decays quietly,
    and it is why the ledger is asserted in both.

    **The mutation this kills:** the check added to an exempt route and the entry
    left behind — which reads in a diff as a strictly safer change.

    **Expected red before E3-07 lands:** a FAILED naming `DevControlRoute`. Once
    the class exists, this test judges the four entries against both currencies.
    """
    application = application_in(DEVELOPMENT, monkeypatch)
    report = ledger_report(
        application,
        EXEMPTIONS,
        dependency=csrf_dependency(),
        route_class=dev_control_route_class(),
    )

    assert report.now_guarded == {}, (
        f"These exempt routes now carry the check: {report.now_guarded}. Each entry in "
        "`EXEMPTIONS` is an argument that a particular route *cannot* hold it — no session to bind "
        "a token to, a deliberately cross-site POST, an appended route with no dependency graph — "
        "and a route that holds it has outlived its own excuse. Delete the entry in the same "
        "change; a ledger that only ever grows is a sweep that only ever covers less."
    )


def test_every_mutating_route_outside_the_ledger_carries_the_csrf_check(
    configured_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The carried E2 entry, closed: nothing writes without the check unless the ledger says why.

    "`require_student` and `csrf_verified_student` sit beside each other and
    nothing makes a writing route reach for the checked one, so the next mutating
    route is one import away from being unprotected in the way that reads as fine
    in review." This is the structural force that was missing. A route added
    tomorrow with `require_student` where `csrf_verified_student` belonged is red
    here on the day it lands, and the only two ways to make it green are to fix
    it or to argue for it in the ledger with a sentence.

    **The mutations this kills:** a new mutating route composed from the unchecked
    dependency; the check removed from an existing one; and E3-07's own trigger
    registered as an ordinary any-method route, which would leave a POST that runs
    a passback against a live gradebook reachable from any page a developer's
    browser happens to be showing.

    **The inventory is required non-empty first** (`docs/MISTAKES.md` entry 3): a
    sweep over no routes reports every application clean, including one whose
    routers were never registered.

    **Expected red before E3-07 lands:** a FAILED naming `DevControlRoute`.
    """
    application = application_in(DEVELOPMENT, monkeypatch)
    routes = mutating_routes(application)

    assert routes, (
        "This application serves no mutating route at all, so this sweep judged nothing and its "
        "silence means nothing. It serves at least the submit path, the two LTI door legs and the "
        "two clock controls; an empty inventory means the routers were never registered or the "
        f"walk went blind. The paths it does serve: {sorted(paths_of(every_route(application)))}."
    )

    report = ledger_report(
        application,
        EXEMPTIONS,
        dependency=csrf_dependency(),
        route_class=dev_control_route_class(),
    )
    assert report.unguarded == {}, (
        f"These routes write and carry neither currency: {report.unguarded} (path to methods).\n\n"
        f"A mutating route must hold {BY_DEPENDENCY} somewhere in its dependency graph, or be "
        f"registered as {BY_ROUTE_CLASS}, or be named in `EXEMPTIONS` with a sentence saying why "
        "it can hold neither. Those are the only three states, and 'it is a development route' is "
        "not one of them: the environment guard and the CSRF check answer different questions.\n\n"
        "If the route above is new, the fix is almost always one import — "
        f"`{CSRF_DEPENDENCY}` rather than `require_student`, which is the pair the carried E2 entry "
        "names as one import apart."
    )
