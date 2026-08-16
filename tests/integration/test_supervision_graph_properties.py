"""Cycles are refused whatever their length and whatever order the edges arrive in — E0-09.

Two properties over the supervision graph, both generated. They exist because
E0-09's criteria name depths two and three, and a guard can be right at those two
depths and wrong everywhere else — a fixed-depth walk, a check that only looks at
the row being written, a guard that runs on INSERT and not on UPDATE. The
examples in `test_role_assignment_graph.py` name the shapes that have to be
refused; these say the same thing over a space nobody chose by hand.

The second property is the one that keeps the first honest. "Refuse every cycle"
is satisfied completely by a schema that refuses every edge, and by one that
refuses any chain deeper than two, and a suite made only of rejection tests
cannot tell those from a correct guard. So the forest property asserts that an
arbitrary acyclic shape inserts *and* that the edges read back as the ones that
were asked for — a guard that silently nulls an edge rather than refusing it
looks identical from the rejection side.

**What these generators do not reach**, stated because a property test declares
its claim in the docstring and its scope in the strategy, and only the second one
runs (`docs/MISTAKES.md` entry 15):

  - cycles longer than eight assignments, and forests wider than ten. Both bounds
    are about how long a database-backed property takes, not about what is
    plausible: a real institution's graph is deeper than eight in neither
    direction, but a guard whose limit is 16 would pass both of these.
  - one role and one scope grain per graph. Every generated node is a chair on
    its own department, so that no uniqueness rule this ticket does not mention
    can refuse a row and be read as the cycle guard firing.
  - one institution, because whether a deployment holds more than one is an open
    spec question (E0-22) and generating a second would answer it.
  - the *first* edge of a graph is always written by INSERT and every later one by
    UPDATE, which is deliberate: re-pointing an existing assignment is what an
    admin does in the People editor (§6.3), and it is the write that closes a
    loop in practice.
"""

from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

pytestmark = [pytest.mark.integration, pytest.mark.slow]

# Bounds on the generated shapes. See the module docstring for what they cost.
LONGEST_CYCLE = 8
WIDEST_FOREST = 10

DATABASE_BACKED = settings(
    max_examples=20,
    deadline=None,
    # Every example shares one `supervision_graph`, and therefore one
    # transaction, which is exactly what is wanted here: the ticket's security
    # review asks whether the guard can be bypassed "inside a single
    # transaction", and this is that question asked twenty times.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


@DATABASE_BACKED
@given(
    length=st.integers(min_value=2, max_value=LONGEST_CYCLE),
    written_last=st.integers(min_value=0, max_value=LONGEST_CYCLE - 1),
)
def test_a_cycle_of_any_length_is_refused_whichever_edge_closes_it(
    supervision_graph: Any, length: int, written_last: int
) -> None:
    """Every edge but one goes in; the last one closes the loop and must be refused.

    `length` assignments are created unconnected, and the `length` edges of a full
    cycle are then written in a rotated order, so that each example closes the
    loop from a different position. Removing any one edge from a cycle leaves a
    path, so every write but the last is legal and has to be accepted — that is
    the control, and without it a guard that refused the second edge of anything
    would satisfy this test at every length.

    The rotation is what the ticket's security review asks for: "whether cycle
    rejection can be bypassed by writing rows in a particular order". A guard that
    checks the ancestors of the row being written, but not the descendants of the
    parent it is being pointed at, is right for some of these rotations and wrong
    for others.
    """
    graph = supervision_graph
    key = graph.assignment_key

    rows: list[Any] = []
    for index in range(length):
        holder: dict[str, Any] = {}

        def build(holder: dict[str, Any] = holder) -> None:
            holder["row"] = graph.node("CHAIR", reports_to=None)

        refused = graph.refusal(build)
        assert refused is None, (
            f"Creating unconnected assignment {index} of {length} was refused: {refused}. These "
            "are ordinary rows with no parent at all, so nothing in this test can mean anything "
            "until they insert — and a schema that refuses them has no supervision graph to test."
        )
        rows.append(holder["row"])
    # Node i reports to node i-1, wrapping: as a set, exactly one cycle.
    edges = [(index, (index - 1) % length) for index in range(length)]
    closing = written_last % length
    order = edges[closing + 1 :] + edges[: closing + 1]

    for child, parent in order[:-1]:
        refused = graph.refusal(
            lambda child=child, parent=parent: graph.repoint(rows[child], rows[parent][key])
        )
        assert refused is None, (
            f"Building a {length}-assignment path was refused at the edge {child} → {parent}: "
            f"{refused}. These edges form a path, not a cycle — every assignment but one has a "
            "distinct parent and the loop is not closed until the last write. A guard that "
            "refuses this refuses ordinary reporting lines."
        )

    child, parent = order[-1]
    refused = graph.refusal(lambda: graph.repoint(rows[child], rows[parent][key]))
    assert refused is not None, (
        f"A cycle of {length} assignments was stored, closed by the edge {child} → {parent} "
        f"(rotation {closing}). E0-09: 'Reject assignment-level cycles at write time', and "
        "criterion 3 asks for the transitive case rather than the direct one. SPEC §2.1 defines "
        "purview as a transitive union over this graph; over a loop that union does not "
        "terminate, so the failure is not a wrong answer on a report — it is the report never "
        "arriving."
    )


@DATABASE_BACKED
@given(
    shape=st.lists(
        st.integers(min_value=-1, max_value=WIDEST_FOREST),
        min_size=1,
        max_size=WIDEST_FOREST,
    )
)
def test_any_acyclic_forest_of_assignments_is_accepted_and_stored_as_written(
    supervision_graph: Any, shape: list[int]
) -> None:
    """An arbitrary forest inserts, and the edges read back as the ones asked for.

    Node `i` is given a parent among nodes `0…i-1`, or none, so every generated
    shape is acyclic by construction: a forest with any mixture of roots, chains,
    branches and shared parents. SPEC §2.1 calls the graph "a forest/DAG over
    assignments", so all of these are shapes the product has to store.

    **Reading the edges back is half the property.** A guard that answered "no
    cycle" by quietly setting `reports_to` to null, or by keeping the row's
    previous parent, would satisfy every rejection test in this suite and every
    acceptance test that only checks the write succeeded — and the purview it
    produced would be too small, which nobody reports as a bug because a missing
    row looks like a permission working.
    """
    graph = supervision_graph
    key = graph.assignment_key

    parents = [None if raw < 0 or index == 0 else raw % index for index, raw in enumerate(shape)]

    rows: list[Any] = []
    for index, parent in enumerate(parents):
        parent_id = None if parent is None else rows[parent][key]
        holder: dict[str, Any] = {}

        def build(parent_id: Any = parent_id, holder: dict[str, Any] = holder) -> None:
            holder["row"] = graph.node("CHAIR", reports_to=parent_id)

        refused = graph.refusal(build)
        assert refused is None, (
            f"Node {index} of the forest {parents} was refused: {refused}. Every parent here is a "
            "node created earlier, so the shape is acyclic by construction — SPEC §2.1: 'The "
            "graph is a forest/DAG over assignments'. A guard that refuses one of these refuses a "
            "reporting line somebody has."
        )
        rows.append(holder["row"])

    for index, parent in enumerate(parents):
        expected = None if parent is None else rows[parent][key]
        assert graph.parent_of(rows[index][key]) == expected, (
            f"Node {index} of the forest {parents} was stored reporting to "
            f"{graph.parent_of(rows[index][key])} rather than to {expected}. The write was "
            "accepted, so the edge was changed rather than refused — which is the failure mode no "
            "rejection test in this suite can see, and it makes somebody's purview quietly "
            "smaller than it should be."
        )
