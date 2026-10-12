"""The walk refuses a chain deeper than six assignments, and admits six — E9-01's depth bound.

SPEC §2.1 makes the supervision graph "at most six assignments deep", and the
ticket bounds the walk the same way: breadth-first down `reports_to`, "at most
six levels". ADR 0044's consequence is why that holds of every graph the schema
accepts: every edge strictly climbs a six-rank order, so no chain is longer than
the chain. A walk that meets a deeper chain is therefore reading a graph no rule
in the schema looked at, and refuses it rather than answering a purview.

**Nothing in a legal graph reaches the bound**, which is why a mutation battery
found the guard unexercised: the lead clamp stops the walk at a lead, so the
deepest legal walk from the top (`VP → DEAN → ASSISTANT_DEAN → CHAIR →` a lead or
an instructor) reads five levels. So these tests plant chains of `CHAIR`
assignments, each on a department of its own, with every `CHAIR → CHAIR` edge
stored past the rank rule the way ADR 0027 measured a superuser can:
`SET session_replication_role = replica`. That setting is superuser-only (the
same ADR measured `pulse_app` refused it), so this widens nothing the
application can reach; it runs on `supervision_graph`'s bootstrap session and is
rolled back with it. The plant is copied from
`tests/integration/test_role_assignment_graph.py`'s
`plant_an_edge_that_does_not_climb` rather than imported (test modules are not
imported by name here), with its three checks: the edge refused without the
bypass, the setting back on `origin`, and the edge read back.

**The boundary is derived from the spec, not from the loop.** This module's
author could not read `services/authz.py` (the test author's read is denied), so
"six admitted, seven refused" is SPEC §2.1's "at most six assignments deep". If
the loop counts so that it admits seven, the seven-chain test goes red on the
current code, and that is a disagreement between the guard and the spec to
settle, not a test to loosen.

**Which exception.** The ticket does not name one; the guard raises
`RuntimeError`. `NotImplementedError` and `RecursionError` are both subclasses
of `RuntimeError`, so the refusal test rejects them by name: the first is the
old seam, the second a walk that recursed until it fell over.
"""

from itertools import pairwise
from typing import Any

import pytest
from fixtures.purview_walk import levels, written
from sqlalchemy import text

pytestmark = pytest.mark.integration

# SPEC §2.1: "the graph is at most six assignments deep".
DEEPEST_CHAIN = 6

BYPASS_THE_TRIGGER = "SET session_replication_role = replica"
RESTORE_THE_TRIGGER = "SET session_replication_role = origin"
BYPASS_STATE = "SHOW session_replication_role"


def plant_an_edge_that_does_not_climb(graph: Any, child: Any, parent: Any) -> None:
    """Store one `CHAIR → CHAIR` edge the rank rule refuses, and prove it landed.

    A copy of the helper in `tests/integration/test_role_assignment_graph.py`;
    see there for why each of the three checks is load-bearing.
    """
    session = graph.session
    key = graph.assignment_key

    unbypassed = graph.refusal(lambda: graph.repoint(child, parent[key]))
    assert unbypassed is not None, (
        f"The edge {child[key]} → {parent[key]} between two chairs was stored with no bypass. ADR "
        "0044 refuses an equal-rank edge, so either the rank rule is gone or this chain is legal "
        "and the depth below is not the depth the schema refuses."
    )

    session.execute(text(BYPASS_THE_TRIGGER))
    try:
        planted = graph.refusal(lambda: graph.repoint(child, parent[key]))
    finally:
        session.execute(text(RESTORE_THE_TRIGGER))

    setting = session.execute(text(BYPASS_STATE)).scalar_one()
    assert setting == "origin", (
        f"`session_replication_role` is {setting!r} after the plant rather than 'origin', so the "
        "walk under test would read with the database's triggers off."
    )
    if planted is not None:
        pytest.fail(
            f"The planted edge was refused even with `{BYPASS_THE_TRIGGER}` in force: {planted}. "
            "If the rank rule now holds against a replica session, a chain deeper than six cannot "
            "be planted at all, and the depth guard defends a state the database cannot hold — "
            "say so rather than loosening this test."
        )
    assert graph.parent_of(child[key]) == parent[key], (
        f"The planted edge did not land: {child[key]} reports to "
        f"{graph.parent_of(child[key])} rather than to {parent[key]}."
    )


def a_chain_of_chairs(graph: Any, length: int) -> list[tuple[Any, Any]]:
    """`length` chairs, top first, each on a fresh department, each reporting to the one above.

    Answers `(assignment row, department id)` per chair. The ancestry of the
    bottom chair is read back from the database and checked, so the chain the
    walk meets is the chain the test claims.
    """
    graph.scope("section")
    key = graph.assignment_key
    chairs: list[tuple[Any, Any]] = []
    for index in range(length):
        department = graph.fresh_scope("department")
        row = written(
            graph,
            lambda department=department: graph.assign("CHAIR", scope=department, reports_to=None),
            f"Chair {index} of the chain, with no parent yet",
        )
        chairs.append((row, department))
    for (upper, _), (lower, _) in pairwise(chairs):
        plant_an_edge_that_does_not_climb(graph, lower, upper)

    bottom = chairs[-1][0][key]
    ancestry = graph.ancestors(bottom)
    assert ancestry == [row[key] for row, _ in reversed(chairs[:-1])], (
        f"The bottom chair's ancestry is {ancestry}, not the {length - 1} chairs planted above it, "
        "so the walk below would not meet the chain this test is named for."
    )
    return chairs


def test_a_chain_one_assignment_deeper_than_six_is_refused_by_the_walk(
    authz: Any, supervision_graph: Any
) -> None:
    """Seven chairs in a chain: the walk from the top raises; from the second, it answers.

    The control is in the same graph: walking from the second chair meets six
    assignments and the same `CHAIR → CHAIR` edges, and must answer. So the
    refusal from the top is about the seventh level and not about the walk
    objecting to non-climbing edges, which would refuse both
    (`docs/MISTAKES.md` entry 3).

    **The mutation this kills (M9):** the depth guard removed — the walk then
    reads all seven levels and answers a purview. A guard loosened to admit seven
    is killed the same way. **The near miss it spares:** a guard at exactly six,
    which answers from the second chair.
    """
    graph = supervision_graph
    key = graph.assignment_key
    chairs = a_chain_of_chairs(graph, DEEPEST_CHAIN + 1)

    try:
        below_the_top = levels(
            authz.transitive_purview(graph.session, assignment_id=chairs[1][0][key])
        )
    except RuntimeError as refused:
        pytest.fail(
            f"The walk from the second chair, six assignments deep, raised {refused!r}. Either the "
            "walk refuses a `CHAIR → CHAIR` edge by itself, so the refusal from the top below "
            "would not be about depth, or its bound admits fewer than SPEC §2.1's six."
        )
    assert chairs[-1][1] in below_the_top["department_ids"], (
        "The walk from the second chair answered without the bottom chair's department, so it "
        "stopped short instead of refusing; the control below is about a walk that never reaches "
        "the seventh level."
    )

    with pytest.raises(RuntimeError) as refused:
        authz.transitive_purview(graph.session, assignment_id=chairs[0][0][key])
    assert not isinstance(refused.value, NotImplementedError | RecursionError), (
        f"The walk from the top of a seven-assignment chain raised {refused.value!r}, which is "
        "not the depth refusal: a `NotImplementedError` is the old seam and a `RecursionError` a "
        "walk with no bound at all."
    )


def test_the_six_assignment_chain_the_bound_admits_is_walked_to_its_bottom(
    authz: Any, supervision_graph: Any
) -> None:
    """Six chairs in a chain: the walk from the top answers, holding every chair's department.

    SPEC §2.1's bound is six assignments, so six is the longest chain the walk
    admits; the test above is the one more that raises.

    **The mutation this kills (M10):** the bound tightened to five — the walk
    then refuses this chain, or answers without the bottom chair's department.
    **The near miss it spares:** a bound of exactly six.
    """
    graph = supervision_graph
    key = graph.assignment_key
    chairs = a_chain_of_chairs(graph, DEEPEST_CHAIN)

    try:
        walked = levels(authz.transitive_purview(graph.session, assignment_id=chairs[0][0][key]))
    except RuntimeError as refused:
        pytest.fail(
            f"The walk refused a chain of exactly six assignments, raising {refused!r}. SPEC "
            "§2.1: 'the graph is at most six assignments deep', so six is inside the bound."
        )
    departments = [department for _, department in chairs]
    missing = [
        index
        for index, department in enumerate(departments)
        if department not in walked["department_ids"]
    ]
    assert not missing, (
        f"The walk from the top of a six-chair chain is missing the departments of chairs "
        f"{missing} (0 is the top). Every chair's own grant is its department, and the walk has "
        "to reach all six."
    )
