"""The grant picker's organization nodes: `GET /admin/org-nodes?role=<role>` (E9-10, SPEC §6.3).

The People editor grants a role on a node (SPEC §2.1's table: a chair on a
department, a dean on a college, a lead on a course, and the vice president,
Care and Admin on the institution). The picker asks the server which nodes a
role can be scoped to, and the server answers them by name, with the name of
the node that contains each. The settled interface:

    `GET /admin/org-nodes?role=<AssignmentRole>`, gated by `require_admin`,
    answering `Cache-Control: no-store` and `{"nodes": [{node_id, label,
    parent_label}]}`, sorted by name, then parent name, then id. VP_ACADEMICS,
    CARE and ADMIN answer institutions; ASSISTANT_DEAN and DEAN colleges; CHAIR
    departments; LEAD_FACULTY courses; INSTRUCTOR an empty list. The names are
    read from `public.org_node_label` (E9-07's view).

**The expected answer is read from the view, not from the route's own code.**
Each test reads `org_node_label` as `pulse_app` (the role production connects
as, `docs/MISTAKES.md` entry 46) through `application_engine`, and the route
rides the built application on the same database (`fixtures/people_editor.py`).

**Other tests share the database** and plant and remove org nodes while this
module runs. So the view is read once before the request and once after it: an
answered node must be in one of the two reads, and a node in both reads must be
answered. That is exact for every node nobody else touched during the request,
and it does not fail because a neighbour's department came or went.

Written after the code (heavy lane, E9-10). Each test names the mutation it
kills and the near miss it spares. On 8e502622 every test here is expected to
pass; a red is an assertion naming the route, never an error in setup.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.people_editor import PeopleEditor
from fixtures.supervision import require_table, seed_row, single_primary_key
from sqlalchemy import text

from app.copy.admin_people import NOT_ADMIN, NOT_ADMIN_ROLE

pytestmark = pytest.mark.integration

ORG_NODES_PATH = "/admin/org-nodes"

# The settled role-to-level map (SPEC §2.1's table of scopes).
LEVEL_OF_ROLE = {
    "VP_ACADEMICS": "institution",
    "CARE": "institution",
    "ADMIN": "institution",
    "ASSISTANT_DEAN": "college",
    "DEAN": "college",
    "CHAIR": "department",
    "LEAD_FACULTY": "course",
}
INSTRUCTOR = "INSTRUCTOR"
EVERY_ROLE = (*LEVEL_OF_ROLE, INSTRUCTOR)

ENVELOPE_FIELDS = frozenset({"nodes"})
NODE_FIELDS = frozenset({"node_id", "label", "parent_label"})

# Each node at one level, with its own name and its containing node's name, as
# `pulse_app` reads them from the view. The institution's parent name is NULL.
LEVEL_FROM_THE_VIEW = text(
    "SELECT c.node_id, c.name, p.name AS parent_name "
    "FROM public.org_node_label c "
    "LEFT JOIN public.org_node_label p ON p.node_id = c.parent_id "
    "WHERE c.level::text = :level"
)


def org_nodes_url(role: str) -> str:
    return f"{ORG_NODES_PATH}?role={role}"


def view_at(application_engine: Any, level: str) -> dict[str, tuple[str, str | None]]:
    """`node id -> (name, parent name)` for every node the view holds at `level`."""
    with application_engine.connect() as connection:
        rows = connection.execute(LEVEL_FROM_THE_VIEW, {"level": level}).mappings()
        return {str(row["node_id"]): (row["name"], row["parent_name"]) for row in rows}


def nodes_in(answer: Any, what: str) -> list[dict[str, Any]]:
    """The answered node list, after requiring a 200 and the `{"nodes": [...]}` envelope."""
    assert answer.status_code == 200, (
        f"{what} answered {answer.status_code}, not 200. Body begins {answer.text[:400]!r}. "
        f"E9-10 settles `GET {ORG_NODES_PATH}?role=<AssignmentRole>` for an admin session."
    )
    body = answer.json()
    assert isinstance(body, dict) and isinstance(body.get("nodes"), list), (
        f"{what} answered {str(body)[:400]!r}; the settled answer is `OrgNodes`, an object "
        "holding the list under `nodes`."
    )
    return list(body["nodes"])


# ---------------------------------------------------------------------------
# The gate, over HTTP.
# ---------------------------------------------------------------------------


def test_the_org_node_picker_refuses_a_request_with_no_session_401(
    people_editor: PeopleEditor,
) -> None:
    """No session: 401 and the admin gate's own sentence.

    **The mutation it kills:** the route mounted without `require_admin` (or
    with a gate that lets an anonymous request through), so the organization
    tree is answered to anyone. **The near miss it spares:** none; the admin
    routes all answer this exactly.
    """
    # `PeopleEditor.ask` falls back to the admin's token when `token` is None, so
    # the request is made on the world itself, with no token at all.
    answered = people_editor.review.ask("GET", org_nodes_url("CHAIR"), token=None)
    assert answered.status_code == 401, (
        f"`GET {ORG_NODES_PATH}` with no session answered {answered.status_code}: "
        f"{answered.text[:400]!r}."
    )
    assert answered.json() == {"detail": NOT_ADMIN}


@pytest.mark.parametrize("who", ["leadership", "care"])
def test_the_org_node_picker_refuses_a_leadership_or_care_session_403(
    people_editor: PeopleEditor, who: str
) -> None:
    """A verified session in another role: 403 and the not-an-admin sentence.

    **The control:** the admin's own session is answered 200 on the same URL,
    so the refusal is the gate and not a route that answers nothing.

    **The mutations it kills:** the route gated by `require_leadership` or by
    "any verified session" instead of `require_admin`; Care admitted because
    Care and Admin are both institution-scoped. **The near miss it spares:** none.
    """
    url = org_nodes_url("CHAIR")
    admitted = people_editor.ask("GET", url)
    assert admitted.status_code == 200, (
        f"The admin's own session was answered {admitted.status_code} on `GET {url}`, so a "
        f"refusal below would not show the gate. Body begins {admitted.text[:400]!r}."
    )

    if who == "leadership":
        chair = people_editor.review.chair
        assert chair is not None, "The lead review world planted no chair. A broken world."
        token = chair.token
    else:
        token = people_editor.care_holder().token
    refused = people_editor.ask("GET", url, token=token)
    assert refused.status_code == 403, (
        f"A {who} session was answered {refused.status_code} on `GET {url}`: "
        f"{refused.text[:400]!r}."
    )
    assert refused.json() == {"detail": NOT_ADMIN_ROLE}


# ---------------------------------------------------------------------------
# What it answers.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", list(LEVEL_OF_ROLE))
def test_each_role_is_answered_exactly_the_views_nodes_at_its_level_named_with_their_parent(
    people_editor: PeopleEditor, application_engine: Any, role: str
) -> None:
    """Exactly the view's nodes at the role's level, each named as the view names it and its parent.

    **The control:** the view holds at least one node at the level, and the
    route answers at least one, so the equality below is not between two empty
    sets. The world plants an institution, a college, a department and three
    courses, so every level has one.

    **The mutations it kills:** a role mapped to the wrong level (a chair
    offered colleges, an assistant dean offered departments, a lead offered
    prefixes or sections); a level filter dropped, so every node is offered;
    nodes dropped by an inner join (a node whose parent has no name); the label
    taken from the parent or the parent label from the node; the parent label
    taken from the grandparent (a course labelled with its department rather
    than its prefix); a node answered twice; `Cache-Control` left cacheable.
    **The near misses it spares:** any order (the order has its own test); a
    neighbour's node planted or removed during the request.
    """
    level = LEVEL_OF_ROLE[role]
    before = view_at(application_engine, level)
    answered = people_editor.ask("GET", org_nodes_url(role))
    after = view_at(application_engine, level)

    assert before and after, (
        f"`org_node_label` read as `pulse_app` holds no `{level}` node, so this test would "
        "compare two empty sets. A broken world, not a red."
    )
    nodes = nodes_in(answered, f"`GET {org_nodes_url(role)}`")
    assert nodes, (
        f"`GET {org_nodes_url(role)}` answered no node, and the view holds {len(before)} "
        f"`{level}` nodes."
    )
    assert answered.headers.get("cache-control") == "no-store", (
        f"`GET {org_nodes_url(role)}` answered `Cache-Control: "
        f"{answered.headers.get('cache-control')}`, not `no-store`."
    )

    ids = [str(node.get("node_id")) for node in nodes]
    repeated = sorted({node for node in ids if ids.count(node) > 1})
    not_at_the_level = sorted(set(ids) - set(before) - set(after))
    not_answered = sorted((set(before) & set(after)) - set(ids))
    assert not (repeated or not_at_the_level or not_answered), (
        f"`GET {org_nodes_url(role)}` does not answer exactly the view's `{level}` nodes. "
        f"Answered and not a `{level}` node in the view: {not_at_the_level}. A `{level}` node "
        f"the view held throughout and the route did not answer: {not_answered}. Answered more "
        f"than once: {repeated}."
    )

    misnamed: list[tuple[str, Any, list[Any]]] = []
    for node in nodes:
        key = str(node.get("node_id"))
        named_by_the_view = {before.get(key), after.get(key)} - {None}
        served = (node.get("label"), node.get("parent_label"))
        if served not in named_by_the_view:
            misnamed.append((key, served, sorted(named_by_the_view, key=str)))
    assert not misnamed, (
        f"(node, answered (label, parent label), the view's (name, parent's name)) where they "
        f"differ for role {role}: {misnamed}."
    )


def test_an_instructor_role_is_answered_an_empty_list(people_editor: PeopleEditor) -> None:
    """`INSTRUCTOR` answers no node: the editor never writes a teaching grant (README decision 11).

    **The control:** the same session asking for `CHAIR` is answered at least
    one node, so the empty list is the role's answer and not a route that
    answers nothing.

    **The mutations it kills:** `INSTRUCTOR` mapped to sections (or to any level),
    so the picker offers a grant the editor must not write; `INSTRUCTOR` refused
    with an error the picker would show. **The near miss it spares:** none.
    """
    control = nodes_in(people_editor.ask("GET", org_nodes_url("CHAIR")), "The CHAIR control")
    assert control, f"`GET {org_nodes_url('CHAIR')}` answered no node. A broken world, not a red."

    nodes = nodes_in(
        people_editor.ask("GET", org_nodes_url(INSTRUCTOR)), f"`GET {org_nodes_url(INSTRUCTOR)}`"
    )
    assert nodes == [], (
        f"`GET {org_nodes_url(INSTRUCTOR)}` answered {len(nodes)} nodes (first: {nodes[:3]}); "
        "the settled answer is an empty list."
    )


def test_every_answer_carries_only_node_id_label_and_parent_label(
    people_editor: PeopleEditor,
) -> None:
    """The envelope holds `nodes` alone, and each node exactly `node_id`, `label`, `parent_label`.

    **The control:** at least one role answers at least one node, so the field
    check reaches a node.

    **The mutations it kills:** a node carrying its level, its parent's id, a
    count of sections or people under it, or a holder's name; the envelope
    carrying a total beside the list. **The near miss it spares:** the three
    fields in any order.
    """
    checked = 0
    wrong: list[tuple[str, Any]] = []
    for role in EVERY_ROLE:
        answered = people_editor.ask("GET", org_nodes_url(role))
        nodes = nodes_in(answered, f"`GET {org_nodes_url(role)}`")
        envelope = set(answered.json())
        if envelope != ENVELOPE_FIELDS:
            wrong.append((f"{role} envelope", sorted(envelope)))
        for node in nodes:
            checked += 1
            if not isinstance(node, dict) or set(node) != NODE_FIELDS:
                wrong.append((role, sorted(node) if isinstance(node, dict) else node))
    assert checked, "No role answered a single node, so no node's fields were checked."
    assert not wrong, (
        f"These answers carry fields other than {sorted(ENVELOPE_FIELDS)} around the list and "
        f"{sorted(NODE_FIELDS)} on each node: {wrong[:10]}."
    )


# ---------------------------------------------------------------------------
# The order.
# ---------------------------------------------------------------------------


def _a_college(editor: PeopleEditor, name: str) -> Any:
    """One new college under the one institution, named `name`; its row."""
    graph = editor.review.graph
    graph.scope("institution")
    return seed_row(
        graph.session, graph.tables, "college", graph.new_branch("institution"), name=name
    )


def _a_department(editor: PeopleEditor, college: Any, name: str) -> Any:
    """One new department in `college`, named `name`; its key."""
    graph = editor.review.graph
    chain = {**graph.new_branch("institution"), "college": college}
    row = seed_row(graph.session, graph.tables, "department", chain, name=name)
    return row[single_primary_key(require_table(graph.tables, "department"))]


def _rename_college(editor: PeopleEditor, college: Any, name: str) -> None:
    graph = editor.review.graph
    table = require_table(graph.tables, "college")
    key = single_primary_key(table)
    graph.session.execute(table.update().where(table.c[key] == college[key]).values(name=name))


def test_nodes_are_ordered_by_name_then_by_parent_name_then_by_id(
    people_editor: PeopleEditor, application_engine: Any
) -> None:
    """Name first, then the parent's name for two same-named departments, then id.

    Two departments with one name, under two colleges, follow their colleges'
    names; a department whose name sorts first comes first even though its
    college sorts last. The world: `<token> dept 1` in `<token> college 3`, and two departments
    named `<token> dept 2`, one in `<token> college 1` and one in `<token>
    college 2`. The college names are given after the departments exist, so the
    twin with the greater id sits in the college that sorts first: id order and
    parent-name order disagree.

    **The control:** the view names all three as planted, with their colleges,
    so the order is asked of rows that are really there.

    **The mutations it kills:** sorting by parent name before name (the single
    department would come last); ties on name broken by id, or by insertion
    order, instead of by parent name (the twins would come out reversed, for
    id order); no sort at all. **The near miss it spares:** where other tests'
    departments fall among these three; the comparison is of these three only.
    """
    for table in ("college", "department"):
        if "name" not in require_table(people_editor.review.graph.tables, table).c:
            pytest.fail(f"`{table}` carries no `name` column; this test plants named nodes.")

    token = uuid4().hex[:10]
    single_college = _a_college(people_editor, f"{token} college 3")
    twin_colleges = [_a_college(people_editor, f"{token} college {uuid4().hex}") for _ in range(2)]
    single = _a_department(people_editor, single_college, f"{token} dept 1")
    twins = [_a_department(people_editor, college, f"{token} dept 2") for college in twin_colleges]
    # The twin with the greater id gets the college that sorts first.
    by_id = sorted(range(2), key=lambda index: str(twins[index]), reverse=True)
    _rename_college(people_editor, twin_colleges[by_id[0]], f"{token} college 1")
    _rename_college(people_editor, twin_colleges[by_id[1]], f"{token} college 2")
    people_editor.review.rows.commit()
    expected = [
        (str(single), f"{token} dept 1", f"{token} college 3"),
        (str(twins[by_id[0]]), f"{token} dept 2", f"{token} college 1"),
        (str(twins[by_id[1]]), f"{token} dept 2", f"{token} college 2"),
    ]

    in_view = view_at(application_engine, "department")
    planted_as_named = [(key, in_view.get(key)) for key, _name, _parent in expected]
    assert all(
        in_view.get(key) == (name, parent) for key, name, parent in expected
    ), f"The view does not name the three planted departments as planted: {planted_as_named}."

    nodes = nodes_in(people_editor.ask("GET", org_nodes_url("CHAIR")), "The CHAIR read")
    answered = [
        (str(node.get("node_id")), node.get("label"), node.get("parent_label"))
        for node in nodes
        if str(node.get("node_id")) in {key for key, _name, _parent in expected}
    ]
    assert answered == expected, (
        f"The three planted departments came out as {answered}; ordered by name, then parent "
        f"name, then id they are {expected}."
    )
