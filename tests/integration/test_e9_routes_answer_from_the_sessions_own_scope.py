"""No leadership route resolves another person's scope — E9-12 done-when 2.

> 2. **No route resolves another person's scope.** Every leadership route,
>    called with another person's id in a query string, path or body, answers
>    from the session's own scope. Marked `invariant`.

E9-01 proved the dependency on probe routes it mounted itself, and E9-05 proved
its one series route; this module proves it **through E9's own read routes**,
each as a leader meets it, and then over **every** route behind the leadership
gate structurally.

**Behavioural, over HTTP** (`docs/MISTAKES.md` entry 47). In E6-05's lead-review
world, lead A asks each of the four read routes three ways beside her plain
request: with lead B's person id, B's assignment id and B's course id in the
query string (under every name a route might take them by); with the same ids in
a JSON body; and with B's person id in the path slot where a node, set or section
id goes. **Every answer must equal A's plain answer**, compared as sets (comment
order is randomised, SPEC §4). **The control for each route:** B's own session,
asking the same URL plainly, is answered differently from A — so A's answer is
not a constant, and an answer resolved from B's ids would be visibly B's.

**Structural, over the route table.** FastAPI binds a request value to code only
through a declared parameter. So no route behind `require_leadership` or
`csrf_verified_leadership` may declare, anywhere in its dependency tree or in a
body model, an input naming a person, a user, an assignment, an actor, a reader
or a scope — beyond what the two session readers declare to read the session.
The set of routes is derived from the built application by dependency object
(`tests/fixtures/leadership_gate.py`'s device), never listed, so a route added
later is swept the day it is registered. **The canary:** a planted route carrying
the gate and a `person_id` query parameter, and a planted body model carrying a
`reader_id`, are found by the same check (`docs/MISTAKES.md` entries 3 and 35).

**Expected green on today's branch**; each test names its mutation and near miss.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.e9_invariant_pass import (
    a_named_set,
    answer,
    body_of,
    canonical,
    drill_down_url,
    figures_url,
    series_url,
    term_of,
    tree_nodes,
    tree_url,
)
from fixtures.lead_review import LeadReviewWorld
from fixtures.named_sets import CSRF_VERIFIED_LEADERSHIP, REQUIRE_LEADERSHIP, leadership_dependency
from fixtures.report_api import FULL_WEEK, TAUGHT_COHORT
from fixtures.routing import dependencies_of, every_route

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

SIX_WEEKS = 6

# What a parameter naming another person (or their assignment, or a scope to
# resolve) looks like, by stem. Read case-insensitively off every declared input
# and every body model's field names and aliases.
PERSON_SHAPED = ("person", "user", "assignment", "actor", "reader", "scope", "impersonat")

# The kinds of request input FastAPI binds to a declared parameter (E9-01's list).
INPUT_KINDS = ("path_params", "query_params", "header_params", "cookie_params", "body_params")

DEPS_MODULE = "app.api.deps"
SESSION_READERS = ("require_leadership", "verified_session", "csrf_verified_leadership")


def the_routes(review: LeadReviewWorld) -> dict[str, str]:
    """Lead A's four plain URLs: her tree, her course's and prefix's figures, a series, a drill-down."""
    assert review.lead is not None
    term = term_of(review)
    tree = body_of(review.ask("GET", tree_url(term), token=review.lead.token), "Lead A's tree")
    prefixes = [node for node in tree_nodes(tree) if node.get("kind") == "prefix"]
    assert prefixes, "Lead A's tree holds no prefix node."
    set_id = a_named_set(review, review.own_course, length=SIX_WEEKS, level_of=review.own_course)
    return {
        "the tree": tree_url(term),
        "her course's figures": figures_url("course", review.own_course, term),
        "her prefix's figures": figures_url("prefix", prefixes[0]["id"], term),
        "a named set's series": series_url(set_id, term),
        "her section's drill-down": drill_down_url(
            review.world.section_id(TAUGHT_COHORT), FULL_WEEK
        ),
    }


def b_ids(review: LeadReviewWorld) -> dict[str, str]:
    assert review.sibling_lead is not None
    assignments = review.graph.assignments_of(review.sibling_lead.person_id)
    assert assignments, "Lead B holds no assignment, so B's assignment id cannot be sent."
    person = str(review.sibling_lead.person_id)
    return {
        "person_id": person,
        "user_id": person,
        "reader_id": person,
        "actor_id": person,
        "as_person": person,
        "assignment_id": str(assignments[0]),
        "scope_id": str(review.sibling_course),
    }


def with_query(url: str, ids: dict[str, str]) -> str:
    joiner = "&" if "?" in url else "?"
    return url + joiner + "&".join(f"{name}={value}" for name, value in ids.items())


def test_every_e9_read_route_answers_a_request_carrying_another_persons_ids_from_the_session(
    lead_review: LeadReviewWorld,
) -> None:
    """Lead A, carrying B's ids in the query string and in a body, is answered A's own answer.

    **The control, per route:** B's plain request to the same URL is answered
    differently, so each route shows whose scope it read.

    **The mutation it kills:** `leadership_scope` (or any route) taking a
    `person_id`, `assignment_id` or `scope_id` from the request when present and
    resolving that person's scope — "read the purview by person". **The near
    miss it spares:** the request ignoring unknown query parameters and body
    members, which FastAPI does by default.
    """
    review = lead_review
    assert review.lead is not None and review.sibling_lead is not None
    routes = the_routes(review)
    ids = b_ids(review)

    crossed: dict[str, Any] = {}
    uncontrolled: list[str] = []
    for what, url in routes.items():
        plain = answer(review.ask("GET", url, token=review.lead.token))
        assert plain[0] == 200, f"The control failed: A's plain {what} answered {plain}."
        by_query = answer(review.ask("GET", with_query(url, ids), token=review.lead.token))
        by_body = answer(review.ask("GET", url, token=review.lead.token, json=ids))
        theirs = answer(review.ask("GET", url, token=review.sibling_lead.token))
        if canonical(theirs) == canonical(plain):
            uncontrolled.append(what)
        for channel, got in (("query string", by_query), ("JSON body", by_body)):
            if canonical(got) != canonical(plain):
                crossed[f"{what}, {channel}"] = (got[0], str(got[1])[:300])

    assert not uncontrolled, (
        f"The control failed for {uncontrolled}: B's own request is answered exactly as A's, so "
        "those routes do not show whose scope they read."
    )
    assert not crossed, (
        f"Lead A's requests carrying B's ids were answered otherwise than her plain ones: "
        f"{crossed}. E9-01: the scope comes from the verified session's own person and nothing "
        "else."
    )


CONTEXT_PATH = "/leadership/context"


def test_the_context_route_answers_a_request_carrying_the_chairs_ids_with_the_leads_own_roles(
    lead_review: LeadReviewWorld,
) -> None:
    """Lead A's `GET /leadership/context`, carrying the chair's ids, answers A's own roles.

    The chair is the other person here rather than lead B, because B holds the
    same role as A and a context resolved from B's ids would look exactly like
    A's. **The control:** the chair's own plain request is answered `CHAIR`, so a
    context resolved from the chair's ids would be visibly the chair's; A's own
    plain request is answered `LEAD_FACULTY` alone.

    **The mutation it kills:** the context route (E9-11) resolving its roles from
    a `person_id` (or `user_id`, `assignment_id`, `scope_id`) in the query string
    or the body when one is present — "read the purview by person". **The near
    miss it spares:** unknown query parameters and body members ignored, which
    FastAPI does by default.
    """
    review = lead_review
    assert review.lead is not None and review.chair is not None
    assignments = review.graph.assignments_of(review.chair.person_id)
    assert assignments, "The chair holds no assignment, so her assignment id cannot be sent."
    chair = str(review.chair.person_id)
    ids = {
        "person_id": chair,
        "user_id": chair,
        "reader_id": chair,
        "actor_id": chair,
        "as_person": chair,
        "assignment_id": str(assignments[0]),
        "scope_id": str(review.department),
    }

    plain = answer(review.ask("GET", CONTEXT_PATH, token=review.lead.token))
    chairs = answer(review.ask("GET", CONTEXT_PATH, token=review.chair.token))
    by_query = answer(review.ask("GET", with_query(CONTEXT_PATH, ids), token=review.lead.token))
    by_body = answer(review.ask("GET", CONTEXT_PATH, token=review.lead.token, json=ids))

    assert plain[0] == 200 and plain[1].get("roles") == ["LEAD_FACULTY"], (
        f"The control failed: lead A's plain context answered {plain}; she holds one Lead "
        "Faculty assignment."
    )
    assert chairs[0] == 200 and chairs[1].get("roles") == ["CHAIR"], (
        f"The control failed: the chair's plain context answered {chairs}, so a context resolved "
        "from her ids would not be told apart from A's."
    )
    crossed = {
        channel: got
        for channel, got in (("query string", by_query), ("JSON body", by_body))
        if canonical(got) != canonical(plain)
    }
    assert not crossed, (
        f"Lead A's context requests carrying the chair's ids were answered otherwise than her "
        f"plain one ({plain}): {crossed}. E9-01: the scope comes from the verified session's "
        "own person and nothing else."
    )


def test_another_persons_id_in_a_path_slot_is_answered_as_an_id_nothing_holds(
    lead_review: LeadReviewWorld,
) -> None:
    """B's person id where a node, set or section id goes: exactly the answer to a random id.

    **The control:** each route answers A's own id in that slot 200 (the slots are
    live), and the random-id answer is a 4xx.

    **The mutation it kills:** a route that, given an id it cannot find among
    nodes, sets or sections, tries it as a person and answers that person's
    scope. **The near miss it spares:** whatever refusal each route picks.
    """
    review = lead_review
    assert review.lead is not None and review.sibling_lead is not None
    term = term_of(review)
    set_id = a_named_set(review, review.own_course, length=SIX_WEEKS, level_of=review.own_course)
    person = review.sibling_lead.person_id
    slots = {
        "a node's figures": (
            figures_url("course", review.own_course, term),
            figures_url("course", person, term),
            figures_url("course", uuid4(), term),
        ),
        "a set's series": (
            series_url(set_id, term),
            series_url(person, term),
            series_url(uuid4(), term),
        ),
        "a section's drill-down": (
            drill_down_url(review.world.section_id(TAUGHT_COHORT), FULL_WEEK),
            drill_down_url(person, FULL_WEEK),
            drill_down_url(uuid4(), FULL_WEEK),
        ),
    }
    differ: dict[str, Any] = {}
    for what, (own, persons, nothing) in slots.items():
        mine = answer(review.ask("GET", own, token=review.lead.token))
        assert mine[0] == 200, f"The control failed: A's own id in {what} answered {mine}."
        as_person = answer(review.ask("GET", persons, token=review.lead.token))
        as_nothing = answer(review.ask("GET", nothing, token=review.lead.token))
        assert 400 <= as_nothing[0] < 500, f"A random id in {what} answered {as_nothing}."
        if as_person != as_nothing:
            differ[what] = {"B's person id": as_person, "an id nothing holds": as_nothing}
    assert not differ, f"B's person id in a path slot was answered as something: {differ}."


# ---------------------------------------------------------------------------
# Structural: every route behind the leadership gate.
# ---------------------------------------------------------------------------


def declared_inputs(dependant: Any) -> set[str]:
    """Every request input a dependant's whole tree declares, and every body model's field names."""
    found: set[str] = set()
    pending = [dependant]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        for kind in INPUT_KINDS:
            for field in getattr(current, kind, ()) or ():
                found.add(str(getattr(field, "alias", None) or getattr(field, "name", "")))
                found |= model_field_names(getattr(field, "type_", None))
                found |= model_field_names(
                    getattr(getattr(field, "field_info", None), "annotation", None)
                )
        pending.extend(getattr(current, "dependencies", ()) or ())
    return found


def model_field_names(annotation: Any, seen: set[int] | None = None) -> set[str]:
    """Every field name and alias of a pydantic model an annotation names, at any depth."""
    import typing

    from pydantic import BaseModel

    seen = set() if seen is None else seen
    found: set[str] = set()
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if id(annotation) in seen:
            return found
        seen.add(id(annotation))
        for name, field in annotation.model_fields.items():
            found.add(name)
            if isinstance(field.alias, str):
                found.add(field.alias)
            found |= model_field_names(field.annotation, seen)
        return found
    for argument in typing.get_args(annotation):
        found |= model_field_names(argument, seen)
    return found


def session_reader_inputs() -> set[str]:
    """What the session readers themselves declare to read the session — allowed, whatever it is."""
    import importlib

    from fastapi.dependencies.utils import get_dependant

    module = importlib.import_module(DEPS_MODULE)
    readers = [getattr(module, name) for name in SESSION_READERS if hasattr(module, name)]
    assert readers, f"`{DEPS_MODULE}` defines none of {SESSION_READERS}."
    allowed: set[str] = set()
    for reader in readers:
        allowed |= declared_inputs(get_dependant(path="/", call=reader))
    return allowed


def person_shaped(names: set[str], allowed: set[str]) -> list[str]:
    return sorted(
        name for name in names - allowed if any(stem in name.lower() for stem in PERSON_SHAPED)
    )


def gated_routes(application: Any) -> list[Any]:
    read = leadership_dependency(REQUIRE_LEADERSHIP)
    write = leadership_dependency(CSRF_VERIFIED_LEADERSHIP)
    found = []
    for route in every_route(application):
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        graph = dependencies_of(dependant)
        if read in graph or write in graph:
            found.append(route)
    return found


def test_the_input_sweep_finds_a_planted_person_parameter_and_a_planted_body_member() -> None:
    """The canary: a gated route with `person_id` in its query and `reader_id` in its body is found.

    **A red here means this module is broken, not the code.** **The mutations
    it kills (in the sweep):** reading the endpoint's own parameters only (the
    query parameter sits on a sub-dependency here); skipping body models.
    """
    from fastapi import Depends, FastAPI
    from pydantic import BaseModel

    read = leadership_dependency(REQUIRE_LEADERSHIP)

    def whose(person_id: str, session: Any = Depends(read)) -> str:
        return person_id

    class Planted(BaseModel):
        reader_id: str
        note: str

    application = FastAPI()

    @application.post("/planted")
    def planted(body: Planted, who: str = Depends(whose)) -> str:
        return who

    routes = gated_routes(application)
    assert len(routes) == 1, f"The planted gated route was found {len(routes)} times."
    found = person_shaped(declared_inputs(routes[0].dependant), session_reader_inputs())
    assert {"person_id", "reader_id"} <= set(
        found
    ), f"The sweep found {found} on the planted route; it carries `person_id` and `reader_id`."


def test_no_route_behind_the_leadership_gate_declares_an_input_naming_another_person(
    lead_review: LeadReviewWorld,
) -> None:
    """Every gated route of the built application: no person-, assignment- or scope-shaped input.

    **The non-emptiness control:** the sweep finds the four E9 read routes among
    the gated ones, so it walked the routes this ticket is about.

    **The mutation it kills:** a `person_id: UUID | None = None` (or an
    `assignment_id`, a `scope_id`, a body member naming a reader) added to any
    leadership route or to any dependency it carries. **The near miss it
    spares:** ids of nodes, sets, sections, comments and prefixes, which are what
    the routes are about.
    """
    application = lead_review.tool.app
    routes = gated_routes(application)
    paths = {str(getattr(route, "path", "")) for route in routes}
    wanted = (
        "/leadership/rollup",
        "/leadership/rollup/{kind}/{node_id}",
        "/leadership/comparison-sets/{set_id}/series",
        "/leadership/sections/{section_id}/weeks/{course_week}/report",
        "/leadership/context",
    )
    missing = [path for path in wanted if path not in paths]
    assert (
        not missing
    ), f"The gated routes the sweep found do not include {missing}; it found {sorted(paths)}."
    allowed = session_reader_inputs()
    offenders = {
        f"{sorted(getattr(route, 'methods', []) or [])} {route.path}": found
        for route in routes
        if (found := person_shaped(declared_inputs(route.dependant), allowed))
    }
    assert not offenders, (
        f"These leadership routes declare an input naming a person or a scope: {offenders}. "
        "E9-01: no route takes a person, assignment or scope id from the request."
    )
