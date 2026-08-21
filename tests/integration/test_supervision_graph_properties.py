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

**What E0-11's rank rule changed here, and why these generators moved.** Both
properties used to build every node as a chair reporting to another chair, and
[ADR 0044](../../docs/adr/0044-a-supervision-edge-must-climb-the-role-rank.md)
makes that row unwritable: an edge is stored only where `rank(child) <
rank(parent)` over SPEC §2.1's chain, so a same-role edge is refused. The
generators now draw a **strictly increasing** role sequence out of that chain,
which is what makes every edge they require to be *accepted* a reporting line the
product actually has. Two consequences are visible below rather than hidden:

  - **the longest chain the schema can hold is six assignments**, because every
    edge climbs and there are six ranks. So the cycle length comes down from eight
    to six, and eight was not a bound worth keeping — it named a graph that cannot
    exist;
  - **a rank-drawn cycle contains exactly one edge that does not climb**, and it
    is refused wherever it is attempted rather than only when it is written last.
    The cycle property asserts that, which is a stronger statement than the
    rotation it replaces, and it deliberately **does not name which guard
    answered**: the rank rule and E0-09's cycle walk can both refuse that edge, and
    a behavioural test cannot say which one did (`docs/MISTAKES.md` entry 3). The
    tests that *can* distinguish them are the planted-edge ones in
    `test_role_assignment_graph.py`.

**What these generators do not reach**, stated because a property test declares
its claim in the docstring and its scope in the strategy, and only the second one
runs (`docs/MISTAKES.md` entry 15):

  - cycles longer than six assignments, which the rank rule makes a space the
    schema no longer admits, and forests wider than ten. The width bound is about
    how long a database-backed property takes, not about what is plausible.
  - the institution-scoped top of the chain, in the **forest** property only.
    `fresh_scope` never duplicates the institution — a deployment holds exactly
    one (SPEC §8, held by `uq_institution_one_row` since E0-22) — so two
    `VP_ACADEMICS` assignments in one generated forest would share one scope node,
    and a uniqueness rule no ticket mentions could then refuse a row and be read as
    the rank or the cycle guard firing (`docs/MISTAKES.md` entry 13). The forest
    therefore draws from the five ranks below it, and chains inside it reach five
    assignments rather than six. The cycle property keeps all six, because a
    rank-drawn cycle uses each rank exactly once — so one example writes at most
    one institution-scoped assignment. The twenty examples do share one
    transaction, though, so a schema that allowed only one `VP_ACADEMICS`
    assignment per institution would refuse the second six-length example; that
    failure names the row that was refused rather than any guard, and the answer
    would be to draw the cycle from the five lower ranks and leave length six to
    `test_a_six_assignment_cycle_is_refused`, which writes one VP per test.
  - one institution, for the same reason.
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

# SPEC §2.1's canonical chain read as an order — `INSTRUCTOR(section) →
# LEAD_FACULTY(course) → CHAIR(department) → DEAN(college) → VP_ACADEMICS`, with
# the assistant dean inserted between chair and dean by the same paragraph. Every
# edge these properties require to be accepted goes from a role in this tuple to
# one later in it, which is ADR 0044's rule and the reason a generated graph is
# writable at all. A second copy of the order lives in
# `test_supervision_edges_run_up_the_role_ranks.py`, deliberately written out
# there for the reason that file gives.
CLIMBING_CHAIN = ("INSTRUCTOR", "LEAD_FACULTY", "CHAIR", "ASSISTANT_DEAN", "DEAN", "VP_ACADEMICS")

# Bounds on the generated shapes. See the module docstring for what they cost.
LONGEST_CYCLE = len(CLIMBING_CHAIN)
FOREST_CHAIN = CLIMBING_CHAIN[:-1]
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


def climbing_forest(shape: list[tuple[int, int]]) -> tuple[list[int | None], list[str]]:
    """Turn a generated shape into a parent per node and a role per node.

    Two properties hold of everything this returns, and each is a rule the schema
    enforces rather than a convenience:

      - **it is acyclic**, because a node's parent is always a node created
        earlier — SPEC §2.1: "the graph is a forest/DAG over assignments";
      - **every edge climbs**, because a node's role is drawn strictly below its
        parent's position in `FOREST_CHAIN` (ADR 0044). A node whose drawn parent
        already sits at the bottom of the chain has nothing to climb to, so it
        becomes a root instead — which is why the shapes stay a mixture of roots,
        chains, branches and shared parents rather than collapsing to one ladder.

    The role is drawn from the whole band below the parent rather than one step
    below it, so the skips SPEC §2.1 requires are inside the space: "a course with
    no mapping falls to its department chair" is `INSTRUCTOR → CHAIR`, two ranks
    apart.
    """
    parents: list[int | None] = []
    ranks: list[int] = []
    for index, (raw_parent, raw_rank) in enumerate(shape):
        parent = None if raw_parent < 0 or index == 0 else raw_parent % index
        if parent is not None and ranks[parent] == 0:
            parent = None
        ceiling = len(FOREST_CHAIN) if parent is None else ranks[parent]
        ranks.append(raw_rank % ceiling)
        parents.append(parent)
    return parents, [FOREST_CHAIN[rank] for rank in ranks]


@DATABASE_BACKED
@given(
    length=st.integers(min_value=2, max_value=LONGEST_CYCLE),
    attempted_first=st.integers(min_value=0, max_value=LONGEST_CYCLE - 1),
)
def test_a_cycle_of_any_length_is_refused_whatever_order_its_edges_are_attempted_in(
    supervision_graph: Any, length: int, attempted_first: int
) -> None:
    """A rank-drawn loop has exactly one edge that does not climb, and it is always refused.

    `length` assignments are created unconnected, one per rank from the bottom of
    SPEC §2.1's chain upwards, and the `length` edges of a full cycle are then
    attempted in a rotated order so that each example reaches the loop from a
    different position. Every edge but one climbs; the one that closes the ring
    runs from the top rank down to the bottom.

    **Two assertions, and the second is the control.** The non-climbing edge is
    refused wherever in the order it is attempted — not only when it is written
    last, which is what the previous version of this property could say. And every
    climbing edge is accepted, which is what stops a guard that refuses the second
    edge of anything from satisfying this test at every length: those edges form a
    path, and a path is somebody's reporting line.

    **It does not say which guard refused.** Both the rank rule (ADR 0044) and
    E0-09's cycle walk can refuse that edge and a behavioural test cannot tell
    them apart (`docs/MISTAKES.md` entry 3). What it does say is that the loop is
    unreachable from every rotation, which is what the ticket's security review
    asks — "whether cycle rejection can be bypassed by writing rows in a
    particular order".

    **The mutation it is written against**: a guard that answers only for the row
    being written and not for the parent it is being pointed at, and a guard whose
    answer depends on the order the edges arrive in. Either is right for some
    rotations and wrong for others.
    """
    graph = supervision_graph
    key = graph.assignment_key
    roles = CLIMBING_CHAIN[:length]

    rows: list[Any] = []
    for index, role in enumerate(roles):
        holder: dict[str, Any] = {}

        def build(role: str = role, holder: dict[str, Any] = holder) -> None:
            holder["row"] = graph.node(role, reports_to=None)

        refused = graph.refusal(build)
        assert refused is None, (
            f"Creating unconnected assignment {index} of {length} as a {role} was refused: "
            f"{refused}. These are ordinary rows with no parent at all, so nothing in this test "
            "can mean anything until they insert — and a schema that refuses them has no "
            "supervision graph to test."
        )
        rows.append(holder["row"])

    # Node i reports to node i+1, wrapping. As a set that is exactly one cycle,
    # and exactly one of its edges — from the top of the chain back to the bottom —
    # does not climb.
    edges = [(index, (index + 1) % length) for index in range(length)]
    does_not_climb = (length - 1, 0)
    start = attempted_first % length
    order = edges[start:] + edges[:start]

    for child, parent in order:
        refused = graph.refusal(
            lambda child=child, parent=parent: graph.repoint(rows[child], rows[parent][key])
        )
        if (child, parent) == does_not_climb:
            assert refused is not None, (
                f"The edge {child} → {parent} was stored, closing a cycle of {length} assignments "
                f"(attempted at position {order.index((child, parent))} of {length}). It runs from "
                f"a {roles[child]} assignment to a {roles[parent]} one, so it is both the edge "
                "that closes the loop and the only edge here that does not climb SPEC §2.1's "
                "chain. "
                "E0-09: 'Reject assignment-level cycles at write time'; ADR 0044: an edge is "
                "accepted only where `rank(child) < rank(parent)`. §2.1 defines purview as a "
                "transitive union over this graph, and over a loop that union does not terminate — "
                "so the failure is not a wrong answer on a report, it is the report never arriving."
            )
        else:
            assert refused is None, (
                f"Building a {length}-assignment path was refused at the edge {child} → {parent}: "
                f"{refused}. That edge runs from a {roles[child]} assignment to a {roles[parent]} "
                "one, which climbs SPEC §2.1's chain, and the edges attempted so far form a path "
                "rather than a loop. A guard that refuses this refuses ordinary reporting lines."
            )

    assert graph.parent_of(rows[length - 1][key]) is None, (
        f"The {roles[length - 1]} assignment at the top of the chain came back reporting to "
        f"{graph.parent_of(rows[length - 1][key])}. Its only edge in this test is the one that "
        "closes the loop, which was refused, so a stored parent means the refusal was reported and "
        "the row was written anyway."
    )


@DATABASE_BACKED
@given(
    shape=st.lists(
        st.tuples(
            st.integers(min_value=-1, max_value=WIDEST_FOREST),
            st.integers(min_value=0, max_value=len(FOREST_CHAIN) - 1),
        ),
        min_size=1,
        max_size=WIDEST_FOREST,
    )
)
def test_any_acyclic_forest_of_assignments_is_accepted_and_stored_as_written(
    supervision_graph: Any, shape: list[tuple[int, int]]
) -> None:
    """An arbitrary forest inserts, and the edges read back as the ones asked for.

    Node `i` is given a parent among nodes `0…i-1`, or none, and a role strictly
    below its parent's in SPEC §2.1's chain — so every generated shape is both
    acyclic by construction and made only of edges that climb. That is a forest
    with any mixture of roots, chains, branches and shared parents. §2.1 calls the
    graph "a forest/DAG over assignments", so all of these are shapes the product
    has to store.

    **Reading the edges back is half the property.** A guard that answered "no
    cycle" by quietly setting `reports_to` to null, or by keeping the row's
    previous parent, would satisfy every rejection test in this suite and every
    acceptance test that only checks the write succeeded — and the purview it
    produced would be too small, which nobody reports as a bug because a missing
    row looks like a permission working. E0-11's rank rule does not change that
    half: a `BEFORE` trigger that cleared the column would pass every refusal in
    the ticket's own matrix.
    """
    graph = supervision_graph
    key = graph.assignment_key

    parents, roles = climbing_forest(shape)
    drawn = list(zip(parents, roles, strict=True))

    rows: list[Any] = []
    for index, (parent, role) in enumerate(drawn):
        parent_id = None if parent is None else rows[parent][key]
        holder: dict[str, Any] = {}

        def build(
            parent_id: Any = parent_id, role: str = role, holder: dict[str, Any] = holder
        ) -> None:
            holder["row"] = graph.node(role, reports_to=parent_id)

        refused = graph.refusal(build)
        assert refused is None, (
            f"Node {index} of the forest {drawn} was refused: {refused}. Every parent here is a "
            "node created earlier and holds a role above this one in SPEC §2.1's chain, so the "
            "shape is acyclic by construction and every edge in it climbs — §2.1: 'The graph is a "
            "forest/DAG over assignments', and ADR 0044 accepts exactly the climbing edges. A "
            "guard that refuses one of these refuses a reporting line somebody has."
        )
        rows.append(holder["row"])

    for index, (parent, _) in enumerate(drawn):
        expected = None if parent is None else rows[parent][key]
        assert graph.parent_of(rows[index][key]) == expected, (
            f"Node {index} of the forest {drawn} was stored reporting to "
            f"{graph.parent_of(rows[index][key])} rather than to {expected}. The write was "
            "accepted, so the edge was changed rather than refused — which is the failure mode no "
            "rejection test in this suite can see, and it makes somebody's purview quietly "
            "smaller than it should be."
        )
