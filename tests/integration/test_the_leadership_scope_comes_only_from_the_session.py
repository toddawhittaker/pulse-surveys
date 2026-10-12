"""The chokepoint: `leadership_scope` resolves from the session's own person only — E9-01, done-when 10.

> 10. No leadership route accepts a person, assignment or scope id that decides
>     whose scope is resolved. A request carrying another person's id in a query
>     string, a path segment or a body is answered from the session's own person.

The ticket names the dependency: "A new dependency in `api/deps.py`,
`leadership_scope`, resolves the scope from the verified session's own
`person_id` and nothing else." The caller sweep that keeps it the only way to a
scope is `tests/unit/test_only_the_leadership_scope_dependency_calls_resolve_scope.py`.

**Two tests, each a different layer.**

  - **Behavioural, over HTTP against the built application** (`docs/MISTAKES.md`
    entry 47). E9-01 adds no leadership route of its own — the roll-ups, the
    drill-down and the named-set figures that consume the scope are later
    tickets' — so this test mounts probe routes on the application the decision
    door builds, each depending on `leadership_scope` exactly as a production
    route would and echoing the scope it was handed. Lead A asks with lead B's
    person id, B's assignment id and B's course id, in a query string, in path
    segments named `person_id`, `assignment_id` and `scope_id`, and in a JSON
    body; every answer is A's scope. The probe endpoint itself declares none of
    those parameters, so the only way one of them can reach the resolver is for
    `leadership_scope` (or something it depends on) to declare it — which is
    exactly the defect.
  - **Structural, over the dependency's declared inputs.** FastAPI binds a
    request value to a dependency only through a declared parameter, so
    `leadership_scope`'s whole dependency tree may declare no request input
    beyond what `require_leadership` and `verified_session` already declare to
    read the session. A planted dependency that takes a `person_id` is found by
    the same check, as its control (`docs/MISTAKES.md` entry 35).

**"Answered from", not "refused".** The ticket says a request carrying another
person's id "is answered from the session's own person", so the behavioural test
requires a success carrying A's scope. A refusal would fail it; that is the
ticket's choice, recorded here rather than made here.

**Which failure a red is, before E9-01 lands.** Both tests fail naming the
missing `app.api.deps.leadership_scope`. The planted-control half of the
structural test is green before and after.
"""

import importlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fixtures.lead_review import LeadReviewWorld, is_success

pytestmark = pytest.mark.integration

DEPS_MODULE = "app.api.deps"
DEPENDENCY = "leadership_scope"
SESSION_READERS = ("require_leadership", "verified_session")

# A path no application route can own: the probes are mounted for one test and
# removed in a `finally`.
PROBE = "/__e9-01-probe"

# The kinds of request input FastAPI binds to a declared parameter.
INPUT_KINDS = ("path_params", "query_params", "header_params", "cookie_params", "body_params")


def deps_symbol(name: str) -> Any:
    """One name off `app.api.deps`, or a failure naming it — never an import error."""
    module = importlib.import_module(DEPS_MODULE)
    found = getattr(module, name, None)
    if found is None:
        pytest.fail(
            f"`{DEPS_MODULE}` defines no `{name}`. E9-01: 'A new dependency in `api/deps.py`, "
            "`leadership_scope`, resolves the scope from the verified session's own `person_id` "
            "and nothing else.'"
        )
    return found


def request_inputs(call: Callable[..., Any]) -> set[tuple[str, str]]:
    """Every request input a dependency's whole tree declares, as (kind, name)."""
    from fastapi.dependencies.utils import get_dependant, get_flat_dependant

    flat = get_flat_dependant(get_dependant(path="/", call=call))
    found: set[tuple[str, str]] = set()
    for kind in INPUT_KINDS:
        for field in getattr(flat, kind, ()):
            found.add((kind, str(getattr(field, "alias", None) or field.name)))
    return found


@contextmanager
def probes_on(application: Any, leadership_scope: Any) -> Iterator[None]:
    """Mount four probe routes that depend on `leadership_scope` and echo the scope."""
    from fastapi import Depends

    def echo(scope: Any = Depends(leadership_scope)) -> dict[str, Any]:
        return {
            "person_id": str(scope.person_id),
            "course_ids": sorted(str(course) for course in scope.purview.course_ids),
        }

    before = list(application.router.routes)
    application.add_api_route(f"{PROBE}/by-query", echo, methods=["GET"])
    application.add_api_route(
        f"{PROBE}/by-path/{{person_id}}/{{assignment_id}}/{{scope_id}}", echo, methods=["GET"]
    )
    application.add_api_route(f"{PROBE}/by-body", echo, methods=["POST"])
    application.add_api_route(f"{PROBE}/plain", echo, methods=["GET"])
    added = [route for route in application.router.routes if route not in before]
    # First in the table, so no catch-all mounted earlier can answer these paths.
    for route in added:
        application.router.routes.remove(route)
    application.router.routes[0:0] = added
    try:
        yield
    finally:
        for route in added:
            if route in application.router.routes:
                application.router.routes.remove(route)


def scope_answered(review: LeadReviewWorld, method: str, url: str, token: str, **kw: Any) -> Any:
    answered = review.ask(method, url, token=token, json=kw.get("json"))
    assert is_success(answered.status_code), (
        f"{method} {url} answered {answered.status_code} to a leadership session; body begins "
        f"{answered.text[:400]!r}. The ticket says such a request 'is answered from the session's "
        "own person'."
    )
    return answered.json()


@pytest.mark.invariant
def test_a_request_naming_another_persons_ids_is_answered_with_the_sessions_own_scope(
    lead_review: LeadReviewWorld,
) -> None:
    """Lead A's session, carrying lead B's ids in every channel, is answered with A's scope.

    **The control:** B's own session, asking plainly, is answered with B's scope,
    so the probe reflects whose session asked and A's answer is not a constant.

    **The mutations this kill:** `leadership_scope` taking a `person_id` (or an
    `assignment_id`, or a `scope_id`) query, path or body parameter that, when
    present, decides whose scope is resolved; a dependency that resolves from a
    `person_id` claim the request can override.
    """
    review = lead_review
    leadership_scope = deps_symbol(DEPENDENCY)
    lead_a, lead_b = review.lead, review.sibling_lead
    assert lead_a is not None and lead_b is not None, "The lead review world has no two leads."
    b_assignments = review.graph.assignments_of(lead_b.person_id)
    assert b_assignments, "Lead B holds no assignment, so B's assignment id cannot be sent."
    b_ids = {
        "person_id": str(lead_b.person_id),
        "assignment_id": str(b_assignments[0]),
        "scope_id": str(review.sibling_course),
    }
    mine = {"person_id": str(lead_a.person_id), "course_ids": [str(review.own_course)]}
    theirs = {"person_id": str(lead_b.person_id), "course_ids": [str(review.sibling_course)]}

    with probes_on(review.tool.app, leadership_scope):
        control = scope_answered(review, "GET", f"{PROBE}/plain", lead_b.token)
        plain = scope_answered(review, "GET", f"{PROBE}/plain", lead_a.token)
        query = "&".join(f"{name}={value}" for name, value in b_ids.items())
        by_query = scope_answered(review, "GET", f"{PROBE}/by-query?{query}", lead_a.token)
        path = "/".join(b_ids[name] for name in ("person_id", "assignment_id", "scope_id"))
        by_path = scope_answered(review, "GET", f"{PROBE}/by-path/{path}", lead_a.token)
        by_body = scope_answered(review, "POST", f"{PROBE}/by-body", lead_a.token, json=b_ids)

    assert control == theirs, (
        f"Lead B's own session was answered with {control}, not B's scope {theirs}, so the probe "
        "does not show whose scope was resolved and the comparisons below mean nothing."
    )
    assert plain == mine, f"Lead A's plain request was answered with {plain}, not {mine}."
    answered = {"query string": by_query, "path segments": by_path, "JSON body": by_body}
    crossed = {channel: body for channel, body in answered.items() if body != mine}
    assert not crossed, (
        f"Lead A's session, carrying lead B's ids, was answered with another scope: {crossed}. "
        "E9-01: the leadership scope is resolved 'from the verified session's own `person_id` and "
        "nothing else: no route takes a person, assignment or scope id from the request to "
        "resolve a scope.'"
    )


@pytest.mark.invariant
def test_the_leadership_scope_dependency_declares_no_request_input_beyond_the_session(
    configured_env: dict[str, str],
) -> None:
    """`leadership_scope`'s dependency tree reads nothing from a request but the session.

    FastAPI hands a request value to a dependency only through a declared
    parameter. So the set of inputs `leadership_scope`'s whole tree declares must
    be a subset of what `require_leadership` and `verified_session` declare to
    read the session — whatever those are, which this test does not decide.

    **The control:** a planted dependency that takes a `person_id` beside the
    session is found by the same check, so the check can see a declared id at all
    (`docs/MISTAKES.md` entry 35).

    **The mutation this kills:** a `person_id: UUID | None = None` (or an
    assignment or scope id) on `leadership_scope` or anything it depends on.
    """
    from fastapi import Depends

    module = importlib.import_module(DEPS_MODULE)
    readers = [getattr(module, name) for name in SESSION_READERS if hasattr(module, name)]
    assert readers, f"`{DEPS_MODULE}` defines none of {SESSION_READERS}."
    allowed: set[tuple[str, str]] = set()
    for reader in readers:
        allowed |= request_inputs(reader)

    def planted(person_id: str, session: Any = Depends(readers[0])) -> Any:
        return person_id

    planted_extra = request_inputs(planted) - allowed
    assert ("query_params", "person_id") in planted_extra, (
        f"A planted dependency taking `person_id` beside the session declared {planted_extra} "
        "beyond the session readers' inputs, so this check cannot see a declared id. A red here "
        "means this test is broken, not the code."
    )

    extra = request_inputs(deps_symbol(DEPENDENCY)) - allowed
    assert not extra, (
        f"`{DEPENDENCY}` declares request inputs beyond the session's: {sorted(extra)}. E9-01: "
        "it 'resolves the scope from the verified session's own `person_id` and nothing else'."
    )
