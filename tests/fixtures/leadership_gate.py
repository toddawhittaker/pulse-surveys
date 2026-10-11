"""E7-08 — the leadership gate's two refusals, and the routes that carry it.

Ruling 11 of `docs/tickets/e7/README.md`, as E7-08 states it: "A real, verified
session in another role gets **403**. The first four cases stay 401, collapsed
together as now, so a caller trying tokens still cannot tell a real one from a
forgery." Several modules ask that of the same routes, so the three readers it
needs live here and each module asserts (`docs/MISTAKES.md` entry 13):

  - **Which routes carry the gate, found rather than listed.** The ticket's
    second known trap: "Check every leadership route, found by the sweep that
    finds routes carrying `require_leadership`, not a hand-written list." So
    `leadership_gated_routes` walks the built application's whole dependency
    graph for the two dependency **objects** (`fixtures/routing.py`'s
    `dependencies_of`, never a name match), and answers each served method and
    path once. A route E7-03 adds later is swept the day it is registered.

  - **The 401's sentence**, which is today's: `NOT_LEADERSHIP`, discovered by
    `fixtures/named_sets.py::refusal_sentence` exactly as E5-06's tests discover
    it. The work order keeps it: "Every other failure stays 401 with today's body."

  - **The 403's sentence, discovered and never spelled.** The ticket settles where
    it lives — "The backend copy entry for the 403 sentence, beside the leadership
    gate's existing refusal in `backend/app/copy/`" — and settles neither its
    constant's name nor its words. So `not_your_role_sentence` takes the sentence
    the gate actually answered and requires three things of it: it is a string
    constant declared in the same copy module that declares `NOT_LEADERSHIP`; it
    is not `NOT_LEADERSHIP`, nor any of the seven other E5-06 refusals declared
    there; and the copy registry publishes it (work order decision 2: "registered
    in the copy inventory"). A sentence this file wrote would be this suite
    choosing the product's copy, and a body compared against it would be red
    against a correct gate (`docs/MISTAKES.md` entry 19).

**Every guard here is a plain function called from a test body**, so a tree
where E7-08 is unbuilt goes red as a FAILED naming the missing deliverable, never
as an ERROR in setup (`docs/MISTAKES.md` entry 44). Nothing here decides what a
route should answer; the modules that import it write every expectation out.
"""

from typing import Any
from uuid import uuid4

import pytest

from fixtures.named_sets import (
    COPY_PACKAGE,
    CSRF_VERIFIED_LEADERSHIP,
    DETAIL_MEMBER,
    NOT_LEADERSHIP,
    REFUSAL_CONSTANTS,
    REQUIRE_LEADERSHIP,
    _copy_modules,
    detail_of,
    leadership_dependency,
    refusal_sentence,
)
from fixtures.report_api import PATH_PARAMETER
from fixtures.routing import dependencies_of, every_route
from fixtures.student_read import decoded
from fixtures.submit import copy_texts

# Ruling 11's two statuses, each named where a failure can quote it.
SIGNED_OUT_STATUS = 401
NOT_YOUR_ROLE_STATUS = 403

# The methods a route table lists that no reader of this module drives. FastAPI
# adds `HEAD` beside `GET` on some route kinds; neither is a method a page calls.
UNDRIVEN_METHODS = frozenset({"HEAD", "OPTIONS"})

# Every method a route here may carry that changes something, so a sweep knows
# which requests to send a body with.
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

NOT_YOUR_ROLE_IS_OWED = (
    "E7-08 (ruling 11): `require_leadership` and `csrf_verified_leadership` answer **403** to a "
    "real, verified, live session in another role, with one fixed sentence held in the backend "
    "copy beside the gate's existing `NOT_LEADERSHIP` refusal and registered in the copy "
    "inventory, identical for every non-leadership role. Absent, malformed, expired and wrongly "
    "signed tokens keep today's 401 and today's body."
)


def leadership_gated_routes(application: Any) -> list[tuple[str, str]]:
    """Every `(method, path)` the built application serves behind either leadership dependency.

    Derived from the application object, which is the thing that decides what is
    served, and from the dependency **objects** — so a route whose graph holds
    something else spelled the same way is not counted, and a route holding the
    gate one level down (a dependency of a dependency) is.
    """
    read = leadership_dependency(REQUIRE_LEADERSHIP)
    write = leadership_dependency(CSRF_VERIFIED_LEADERSHIP)
    found: set[tuple[str, str]] = set()
    for route in every_route(application):
        dependant = getattr(route, "dependant", None)
        path = getattr(route, "path", None)
        if dependant is None or not isinstance(path, str):
            continue
        graph = dependencies_of(dependant)
        if read not in graph and write not in graph:
            continue
        for method in getattr(route, "methods", None) or ():
            if str(method).upper() not in UNDRIVEN_METHODS:
                found.add((str(method).upper(), path))
    return sorted(found)


def concrete(path: str) -> str:
    """A path template with a fresh uuid in every parameter.

    The gate runs before any parameter is read (it is a declared dependency), so a
    refused request is refused for its session and not for an identifier; and the
    admitted half of every pair reads "past the gate", not "answered 200", for the
    same reason — an unknown id is a 404 *after* the gate.
    """
    return PATH_PARAMETER.sub(lambda _match: str(uuid4()), path)


def body_for(method: str) -> Any:
    """`{}` for a write and nothing for a read: enough to reach the gate, never enough to write."""
    return {} if method in WRITE_METHODS else None


def signed_out_sentence() -> str:
    """The 401's sentence: today's `NOT_LEADERSHIP`, read out of the copy package."""
    return refusal_sentence(NOT_LEADERSHIP)


def the_gates_copy_module() -> Any:
    """The one module under `app.copy` that declares `NOT_LEADERSHIP` itself."""
    homes = [
        module for module in _copy_modules() if isinstance(vars(module).get(NOT_LEADERSHIP), str)
    ]
    # A package that re-exports the constant is not where it is declared; the
    # package itself is chosen only when no module inside it holds the name.
    inside = [module for module in homes if module.__name__.startswith(f"{COPY_PACKAGE}.")]
    chosen = inside or homes
    if len(chosen) != 1:
        pytest.fail(
            f"{len(chosen)} modules under `app.copy` declare `{NOT_LEADERSHIP}` "
            f"({sorted(module.__name__ for module in chosen)}). E7-08 puts the 403's sentence "
            "beside the gate's existing refusal, so there has to be exactly one place that is."
        )
    return chosen[0]


def not_your_role_sentence(answered: Any, what: str) -> str:
    """The 403's `detail`, after requiring it to be the gate's own sentence, or a failure.

    **What makes it the gate's and not some other 403's.** This stack already
    answers 403 for other reasons: a cookie-borne write without its double-submit
    token, `NOT_THE_SETS_DEFINER` from the named-set scope read, and ADR 0190's
    refusal of a dean at the review queue. A status alone cannot say which layer
    spoke, so the sentence is required to be a constant the gate's own copy module
    declares and none of E5-06's eight refusals.
    """
    if answered.status_code != NOT_YOUR_ROLE_STATUS:
        pytest.fail(
            f"{what} answered {answered.status_code}, not {NOT_YOUR_ROLE_STATUS}. Body begins "
            f"{answered.text[:400]!r}.\n\n{NOT_YOUR_ROLE_IS_OWED}"
        )
    sentence = detail_of(answered)
    module = the_gates_copy_module()
    beside = {
        name: value
        for name, value in vars(module).items()
        if not name.startswith("_")
        and name.isupper()
        and isinstance(value, str)
        and name not in REFUSAL_CONSTANTS
    }
    holding = sorted(name for name, value in beside.items() if value == sentence)
    if not holding:
        pytest.fail(
            f"{what} was refused with {sentence!r}, and no constant beside `{NOT_LEADERSHIP}` in "
            f"`{module.__name__}` holds that sentence (the constants there that are not E5-06's "
            f"eight: {sorted(beside)}).\n\n{NOT_YOUR_ROLE_IS_OWED}"
        )
    if sentence == signed_out_sentence():
        pytest.fail(
            f"{what} answered {NOT_YOUR_ROLE_STATUS} with the `{NOT_LEADERSHIP}` sentence, which is "
            "the ended-session refusal. The page reads the status, and a reader of the body would "
            "still be told the session ended."
        )
    if sentence not in set(copy_texts().values()):
        pytest.fail(
            f"{what}'s sentence {sentence!r} is declared in `{module.__name__}` and the copy "
            "registry does not publish it. Work order decision 2: both sentences are registered in "
            "the copy inventory, which is what puts this one inside the §4.1 item 1 copy sweep — "
            "a student is served it."
        )
    return sentence


def the_whole_body_is_the_sentence(answered: Any, what: str) -> None:
    """The refusal's body is `{"detail": <sentence>}` and nothing beside it.

    Criterion 1: "the body names no route, section or person". A body with a
    second member is a body with somewhere to name one.
    """
    body = decoded(answered, what)
    if not isinstance(body, dict) or set(body) != {DETAIL_MEMBER}:
        pytest.fail(
            f"{what} answered {str(body)[:400]!r}. The refusal is one sentence under "
            f"`{DETAIL_MEMBER}` and nothing else; a second member is a place a route, a section or a "
            "person could be named."
        )
