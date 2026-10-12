"""E9-01 — generated worlds for the purview walk, and the purview computed without it.

SPEC §2.1: "**Purview(assignment) = own grant union the purviews of all
assignments transitively reporting to it**, with the own grant restricted by
role grain: a Lead Faculty's grant is only the courses they lead (never sibling
leads' courses, at any point in the union); a chair's is the department subtree;
a dean's the college." E9-01's ticket adds the clamp that makes "at any point in
the union" checkable: a `LEAD_FACULTY` assignment's purview is its own grant
only, whatever reports to it. Ruling 4 adds the leadership scope: the union of
the purviews of a person's `LEAD_FACULTY`, `CHAIR`, `ASSISTANT_DEAN`, `DEAN` and
`VP_ACADEMICS` assignments, with `INSTRUCTOR`, `CARE` and `ADMIN` contributing
nothing.

This module holds no fixtures, so it is imported rather than registered in
`pytest_plugins` (the conftest index lists it with the other import-only
modules). It holds four things:

  - **`climbing_forest`, moved here from
    `tests/integration/test_supervision_graph_properties.py`**, which imports it
    back. The ticket names that module's generators as the ones to reuse, and a
    second copy of a generator is a copy one ticket widens and the other does not.
  - **`world_plans`**, a Hypothesis strategy for a whole world as a pure value: a
    containment tree, a forest of assignments drawn by `climbing_forest`, who
    holds each assignment, and which person the Lead Faculty mapping gives each
    course. Pure, so `hypothesis.find` can ask what it draws without a database
    (`docs/MISTAKES.md` entry 15: a generator's reach is asserted, not assumed).
  - **`build_world`**, which writes a plan through `SupervisionGraph` and
    `seed_row` and answers the database ids of every node it wrote.
  - **`expected_purviews` and `expected_scope`**, which compute the answer from
    the plan alone, by SPEC §2.1's sentence and the ticket's clamp, and never by
    calling the code under test (`docs/MISTAKES.md` entry 19). The own grants
    they use are the grains `tests/integration/test_own_grant_follows_the_role_
    grain.py` already asserts on `own_grant`: an instructor's section; a lead's
    mapped courses and their sections, and no prefix; a chair's department
    subtree; an empty grant for an assistant dean; a dean's college subtree.

**What the plans do not reach**, stated because a property declares its claim in
the docstring and its scope in the strategy (`docs/MISTAKES.md` entry 15):

  - `VP_ACADEMICS` is not drawn. A deployment holds one institution (SPEC §8),
    so a VP's own grant is every row any test has committed, and an exact
    expectation over it is not available. The chain tests in
    `test_the_purview_walk_is_transitive_and_batched_by_level.py` put a VP on top
    and assert containment there instead.
  - Forests wider than ten assignments, and containment trees larger than two
    colleges of two departments of two prefixes of two courses of two sections.
    The bound is about how long a database-backed property takes.
"""

from dataclasses import dataclass
from typing import Any

import pytest
from hypothesis import strategies as st

from fixtures.supervision import ROLE_ALIASES, seed_row

# The six levels of a `Purview`, outermost first, as E0-11 settled them.
# Transcribed rather than read off the dataclass (`docs/MISTAKES.md` entry 19).
PURVIEW_LEVELS = (
    "institution_ids",
    "college_ids",
    "department_ids",
    "prefix_ids",
    "course_ids",
    "section_ids",
)

# SPEC §2.1's canonical chain read as an order, with the assistant dean inserted
# between chair and dean by the same paragraph. Every edge a generated forest
# holds runs from a role in this tuple to one later in it (ADR 0044).
CLIMBING_CHAIN = ("INSTRUCTOR", "LEAD_FACULTY", "CHAIR", "ASSISTANT_DEAN", "DEAN", "VP_ACADEMICS")
FOREST_CHAIN = CLIMBING_CHAIN[:-1]
WIDEST_FOREST = 10

# Ruling 4 of `docs/tickets/e9/README.md`, transcribed: "the union of the purviews
# of the person's leadership assignments only: LEAD_FACULTY, CHAIR,
# ASSISTANT_DEAN, DEAN and VP_ACADEMICS".
LEADERSHIP_ROLES = ("LEAD_FACULTY", "CHAIR", "ASSISTANT_DEAN", "DEAN", "VP_ACADEMICS")

# The containment kind each drawn role is scoped to (SPEC §2's table).
GRAIN = {
    "INSTRUCTOR": "section",
    "LEAD_FACULTY": "course",
    "CHAIR": "department",
    "ASSISTANT_DEAN": "college",
    "DEAN": "college",
}

# The roles a planted lead may report to: every role above it in the forest chain.
ABOVE_A_LEAD = ("CHAIR", "ASSISTANT_DEAN", "DEAN")

KINDS = ("college", "department", "prefix", "course", "section")
LEVEL_OF_KIND = {
    "institution": "institution_ids",
    "college": "college_ids",
    "department": "department_ids",
    "prefix": "prefix_ids",
    "course": "course_ids",
    "section": "section_ids",
}

Levels = dict[str, frozenset[Any]]


def climbing_forest(shape: list[tuple[int, int]]) -> tuple[list[int | None], list[str]]:
    """Turn a generated shape into a parent per node and a role per node.

    Moved verbatim from `tests/integration/test_supervision_graph_properties.py`
    (E0-09, widened by E0-11), which imports it from here. Two properties hold of
    everything this returns, and each is a rule the schema enforces:

      - **it is acyclic**, because a node's parent is always a node created
        earlier — SPEC §2.1: "the graph is a forest/DAG over assignments";
      - **every edge climbs**, because a node's role is drawn strictly below its
        parent's position in `FOREST_CHAIN` (ADR 0044). A node whose drawn parent
        already sits at the bottom of the chain has nothing to climb to, so it
        becomes a root instead.

    The role is drawn from the whole band below the parent rather than one step
    below it, so the skips SPEC §2.1 requires are inside the space: "a course with
    no mapping falls to its department chair" is `INSTRUCTOR → CHAIR`.
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


# ---------------------------------------------------------------------------
# Reading a purview, and joining expectations.
# ---------------------------------------------------------------------------


def levels(purview: Any) -> Levels:
    """Every level of one purview, by name, for whole-value comparison."""
    return {name: frozenset(getattr(purview, name)) for name in PURVIEW_LEVELS}


def nothing() -> Levels:
    """A purview holding nothing at any level."""
    return {name: frozenset() for name in PURVIEW_LEVELS}


def joined(*many: Levels) -> Levels:
    """The level-by-level union of several expectations."""
    out = nothing()
    for one in many:
        out = {name: out[name] | one[name] for name in PURVIEW_LEVELS}
    return out


def covers(outer: Levels, inner: Levels) -> bool:
    """Whether `outer` holds every node `inner` holds, at every level."""
    return all(inner[name] <= outer[name] for name in PURVIEW_LEVELS)


def difference(got: Levels, wanted: Levels) -> dict[str, dict[str, list[str]]]:
    """Per level, what `got` lacks and what it holds beyond `wanted`. Empty when equal."""
    out: dict[str, dict[str, list[str]]] = {}
    for name in PURVIEW_LEVELS:
        missing = sorted(str(node) for node in wanted[name] - got[name])
        extra = sorted(str(node) for node in got[name] - wanted[name])
        if missing or extra:
            out[name] = {"missing": missing, "extra": extra}
    return out


def role_token(role: Any) -> str:
    """The canonical spelling of a role value, whether an enum member or a string.

    `ActorScope.grants` carries a role per entry, and nothing settles whether it is
    the `role_assignment` enum member or its text. Both are reduced to SPEC §2.1's
    spelling through `ROLE_ALIASES` (`tests/fixtures/supervision.py`), so a test
    comparing roles decides neither.
    """
    spelled = str(getattr(role, "name", None) or getattr(role, "value", role)).upper()
    for canonical, aliases in ROLE_ALIASES.items():
        if spelled in aliases:
            return canonical
    return spelled


def written(graph: Any, action: Any, what: str) -> Any:
    """Perform a write that has to succeed, and fail naming it when it does not.

    A copy of the helper in `tests/integration/test_role_assignment_graph.py`. A
    control that was refused makes everything after it meaningless
    (`docs/MISTAKES.md` entry 3).
    """
    holder: dict[str, Any] = {}

    def perform() -> None:
        holder["row"] = action()

    refused = graph.refusal(perform)
    if refused is not None:
        pytest.fail(
            f"{what} was refused: {refused}. It is a premise of the world, not the subject of "
            "the test, so nothing after it can mean anything — a broken world, not a red."
        )
    return holder.get("row")


# ---------------------------------------------------------------------------
# The plan: a whole world as a pure value.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedNode:
    """One assignment: its role, its parent (an index), its holder, its scope (an index)."""

    role: str
    parent: int | None
    person: int
    scope: int


@dataclass(frozen=True)
class WorldPlan:
    """A containment tree, an assignment forest, and the Lead Faculty mapping.

    Each containment tuple gives, per node, the index of its parent one level up:
    `department_college[d]` is department `d`'s college, and so on down to
    `section_course`. `lead_of_course[c]` is the person the mapping gives course
    `c`, or `None` for an unmapped course (SPEC §2.1: "a course with no mapping
    falls to its department chair"). `planted` names the three nodes of the
    sibling-lead gadget when one was drawn: lead A, lead B, and the instructor on
    a section of B's course who reports to A.
    """

    college_count: int
    department_college: tuple[int, ...]
    prefix_department: tuple[int, ...]
    course_prefix: tuple[int, ...]
    section_course: tuple[int, ...]
    nodes: tuple[PlannedNode, ...]
    person_count: int
    lead_of_course: tuple[int | None, ...]
    planted: tuple[int, int, int] | None

    # -- containment, read from the plan --------------------------------------

    def college_of_department(self, department: int) -> int:
        return self.department_college[department]

    def department_of_course(self, course: int) -> int:
        return self.prefix_department[self.course_prefix[course]]

    def course_of_section(self, section: int) -> int:
        return self.section_course[section]

    def children_of(self, index: int) -> list[int]:
        return [child for child, node in enumerate(self.nodes) if node.parent == index]

    def courses_led_by(self, person: int) -> list[int]:
        return [course for course, lead in enumerate(self.lead_of_course) if lead == person]


def _containment(draw: Any) -> tuple[int, list[int], list[int], list[int], list[int]]:
    """Two colleges at most, each node with one or two children, two courses at least."""
    college_count = draw(st.integers(min_value=1, max_value=2))
    department_college: list[int] = []
    for college in range(college_count):
        department_college += [college] * draw(st.integers(min_value=1, max_value=2))
    prefix_department: list[int] = []
    for department in range(len(department_college)):
        prefix_department += [department] * draw(st.integers(min_value=1, max_value=2))
    course_prefix: list[int] = []
    for prefix in range(len(prefix_department)):
        course_prefix += [prefix] * draw(st.integers(min_value=1, max_value=2))
    if len(course_prefix) < 2:
        # The sibling gadget needs two courses, and two leads need two courses to
        # be siblings at all.
        course_prefix.append(len(prefix_department) - 1)
    section_course: list[int] = []
    for course in range(len(course_prefix)):
        section_course += [course] * draw(st.integers(min_value=1, max_value=2))
    return college_count, department_college, prefix_department, course_prefix, section_course


@st.composite
def world_plans(draw: Any) -> WorldPlan:
    """A generated world. See the module docstring for what it reaches and what it does not.

    **Four shapes the ticket names are inside this space**, and
    `test_the_purview_walk_holds_over_generated_forests.py` asserts each is
    actually drawn rather than trusting this docstring:

      - **assistant-dean insertions** — `climbing_forest` draws `CHAIR` under
        `ASSISTANT_DEAN` under `DEAN` as freely as any other climbing edge;
      - **two-hat people** — each assignment's holder is drawn from the people
        already in the plan or a new one, so one person holds several hats,
        including a lead hat under their own chair hat;
      - **cross-department led courses** — the mapping draws each course's lead
        from every person in the plan, with no regard to where the course sits;
      - **an instructor edge into a lead, on a sibling lead's course** — drawn
        by the random forest when it happens to, and planted as a gadget on about
        half the plans so the case the clamp exists for is common rather than
        rare: lead A (under an existing chair, assistant dean or dean when there
        is one), lead B on a different course, and an instructor on a section of
        B's course reporting to A.
    """
    college_count, department_college, prefix_department, course_prefix, section_course = (
        _containment(draw)
    )
    pools = {
        "college": college_count,
        "department": len(department_college),
        "course": len(course_prefix),
        "section": len(section_course),
    }

    shape = draw(
        st.lists(
            st.tuples(
                st.integers(min_value=-1, max_value=WIDEST_FOREST),
                st.integers(min_value=0, max_value=len(FOREST_CHAIN) - 1),
                st.integers(min_value=0, max_value=WIDEST_FOREST),
                st.integers(min_value=0, max_value=63),
            ),
            min_size=1,
            max_size=WIDEST_FOREST,
        )
    )
    parents, roles = climbing_forest(
        [(raw_parent, raw_rank) for raw_parent, raw_rank, _, _ in shape]
    )

    nodes: list[PlannedNode] = []
    person_count = 0
    held: set[tuple[int, str, int]] = set()
    for (_, _, raw_person, raw_scope), parent, role in zip(shape, parents, roles, strict=True):
        scope = raw_scope % pools[GRAIN[role]]
        person = raw_person % (person_count + 1)
        if person == person_count or (person, role, scope) in held:
            # A new person, or a hat this person already wears on this node: give
            # it to somebody new rather than writing the same row twice.
            person = person_count
            person_count += 1
        held.add((person, role, scope))
        nodes.append(PlannedNode(role=role, parent=parent, person=person, scope=scope))

    overrides: dict[int, int] = {}
    planted: tuple[int, int, int] | None = None
    if draw(st.booleans()):
        above = [index for index, node in enumerate(nodes) if node.role in ABOVE_A_LEAD]
        pick = draw(st.integers(min_value=-1, max_value=len(above) - 1))
        lead_parent = above[pick] if pick >= 0 else None
        course_count = len(course_prefix)
        own_course = draw(st.integers(min_value=0, max_value=course_count - 1))
        sibling_course = draw(st.integers(min_value=0, max_value=course_count - 2))
        if sibling_course >= own_course:
            sibling_course += 1
        sibling_sections = [s for s, c in enumerate(section_course) if c == sibling_course]
        section = sibling_sections[
            draw(st.integers(min_value=0, max_value=len(sibling_sections) - 1))
        ]
        lead_a, lead_b, teacher = person_count, person_count + 1, person_count + 2
        person_count += 3
        a_index = len(nodes)
        nodes.append(PlannedNode("LEAD_FACULTY", lead_parent, lead_a, own_course))
        b_index = len(nodes)
        nodes.append(PlannedNode("LEAD_FACULTY", None, lead_b, sibling_course))
        teacher_index = len(nodes)
        nodes.append(PlannedNode("INSTRUCTOR", a_index, teacher, section))
        overrides = {own_course: lead_a, sibling_course: lead_b}
        planted = (a_index, b_index, teacher_index)

    raw_mapping = draw(
        st.lists(
            st.integers(min_value=-1, max_value=WIDEST_FOREST + 3),
            min_size=len(course_prefix),
            max_size=len(course_prefix),
        )
    )
    lead_of_course = tuple(
        overrides[course] if course in overrides else (None if raw < 0 else raw % person_count)
        for course, raw in enumerate(raw_mapping)
    )

    return WorldPlan(
        college_count=college_count,
        department_college=tuple(department_college),
        prefix_department=tuple(prefix_department),
        course_prefix=tuple(course_prefix),
        section_course=tuple(section_course),
        nodes=tuple(nodes),
        person_count=person_count,
        lead_of_course=lead_of_course,
        planted=planted,
    )


# ---------------------------------------------------------------------------
# What a plan draws, asked of the plan alone (`docs/MISTAKES.md` entry 15).
# ---------------------------------------------------------------------------


def has_an_instructor_edge_into_a_lead_on_another_persons_course(plan: WorldPlan) -> bool:
    """An `INSTRUCTOR` reporting to a `LEAD_FACULTY` whose section's course is mapped to someone else."""
    for node in plan.nodes:
        if node.role != "INSTRUCTOR" or node.parent is None:
            continue
        parent = plan.nodes[node.parent]
        if parent.role != "LEAD_FACULTY":
            continue
        owner = plan.lead_of_course[plan.course_of_section(node.scope)]
        if owner is not None and owner != parent.person:
            return True
    return False


def has_an_assistant_dean_insertion(plan: WorldPlan) -> bool:
    """A `CHAIR` reporting to an `ASSISTANT_DEAN` that reports to a `DEAN`."""
    for node in plan.nodes:
        if node.role != "CHAIR" or node.parent is None:
            continue
        middle = plan.nodes[node.parent]
        if (
            middle.role == "ASSISTANT_DEAN"
            and middle.parent is not None
            and plan.nodes[middle.parent].role == "DEAN"
        ):
            return True
    return False


def has_a_two_hat_person(plan: WorldPlan) -> bool:
    """One person holding two leadership assignments of different roles."""
    roles: dict[int, set[str]] = {}
    for node in plan.nodes:
        if node.role in LEADERSHIP_ROLES:
            roles.setdefault(node.person, set()).add(node.role)
    return any(len(held) >= 2 for held in roles.values())


def has_a_cross_department_lead(plan: WorldPlan) -> bool:
    """A person holding a lead assignment who is mapped to courses in two departments."""
    leads = {node.person for node in plan.nodes if node.role == "LEAD_FACULTY"}
    for person in leads:
        departments = {plan.department_of_course(c) for c in plan.courses_led_by(person)}
        if len(departments) >= 2:
            return True
    return False


# ---------------------------------------------------------------------------
# Writing a plan, and the ids it was written under.
# ---------------------------------------------------------------------------


@dataclass
class BuiltWorld:
    """A plan written to the database: the id of every node, person and assignment."""

    plan: WorldPlan
    ids: dict[str, list[Any]]
    persons: list[Any]
    assignments: list[Any]
    institution: Any


def build_world(graph: Any, plan: WorldPlan) -> BuiltWorld:
    """Write `plan` through `SupervisionGraph`, fresh colleges down, and answer its ids.

    Every college here is new, so a dean's college subtree holds exactly what the
    plan put under it; every person is new, so a lead's mapped courses are exactly
    the plan's. The shared chain `graph.scope("section")` seeds is used only for
    its institution and term.
    """
    session, tables = graph.session, graph.tables
    graph.scope("section")
    base = graph.new_branch("institution", "term")

    chains: dict[str, list[dict[str, Any]]] = {kind: [] for kind in KINDS}

    def child(kind: str, parent_chain: dict[str, Any]) -> dict[str, Any]:
        chain = dict(parent_chain)
        seed_row(session, tables, kind, chain)
        return chain

    for _ in range(plan.college_count):
        chains["college"].append(child("college", base))
    for college in plan.department_college:
        chains["department"].append(child("department", chains["college"][college]))
    for department in plan.prefix_department:
        chains["prefix"].append(child("prefix", chains["department"][department]))
    for prefix in plan.course_prefix:
        chains["course"].append(child("course", chains["prefix"][prefix]))
    for course in plan.section_course:
        chains["section"].append(child("section", chains["course"][course]))

    ids = {kind: [graph.key_of(kind, chain[kind]) for chain in chains[kind]] for kind in KINDS}
    persons = [graph.person() for _ in range(plan.person_count)]

    key = graph.assignment_key
    assignments: list[Any] = []
    for index, node in enumerate(plan.nodes):
        parent = None if node.parent is None else assignments[node.parent]
        scope = ids[GRAIN[node.role]][node.scope]
        row = written(
            graph,
            lambda node=node, scope=scope, parent=parent: graph.assign(
                node.role, scope=scope, person=persons[node.person], reports_to=parent
            ),
            f"Planned assignment {index} ({node.role}, reporting to {node.parent})",
        )
        assignments.append(row[key])

    for course, lead in enumerate(plan.lead_of_course):
        if lead is None:
            continue
        written(
            graph,
            lambda course=course, lead=lead: graph.lead_mapping(
                person=persons[lead], course=ids["course"][course]
            ),
            f"The mapping of planned course {course} to planned person {lead}",
        )

    return BuiltWorld(
        plan=plan,
        ids=ids,
        persons=persons,
        assignments=assignments,
        institution=graph.scope("institution"),
    )


# ---------------------------------------------------------------------------
# The answer, computed from the plan alone.
# ---------------------------------------------------------------------------


def _subtree_of_department(world: BuiltWorld, department: int) -> Levels:
    plan, ids = world.plan, world.ids
    prefixes = [p for p, d in enumerate(plan.prefix_department) if d == department]
    courses = [c for c, p in enumerate(plan.course_prefix) if p in prefixes]
    sections = [s for s, c in enumerate(plan.section_course) if c in courses]
    out = nothing()
    out["department_ids"] = frozenset({ids["department"][department]})
    out["prefix_ids"] = frozenset(ids["prefix"][p] for p in prefixes)
    out["course_ids"] = frozenset(ids["course"][c] for c in courses)
    out["section_ids"] = frozenset(ids["section"][s] for s in sections)
    return out


def _subtree_of_college(world: BuiltWorld, college: int) -> Levels:
    plan, ids = world.plan, world.ids
    departments = [d for d, k in enumerate(plan.department_college) if k == college]
    out = joined(*(_subtree_of_department(world, d) for d in departments))
    out["college_ids"] = frozenset({ids["college"][college]})
    return out


def _courses_with_sections(world: BuiltWorld, courses: list[int]) -> Levels:
    plan, ids = world.plan, world.ids
    out = nothing()
    out["course_ids"] = frozenset(ids["course"][c] for c in courses)
    out["section_ids"] = frozenset(
        ids["section"][s] for s, c in enumerate(plan.section_course) if c in courses
    )
    return out


def expected_own_grant(world: BuiltWorld, index: int) -> Levels:
    """One assignment's own grant, by SPEC §2.1's role grains, from the plan."""
    node = world.plan.nodes[index]
    if node.role == "INSTRUCTOR":
        out = nothing()
        out["section_ids"] = frozenset({world.ids["section"][node.scope]})
        return out
    if node.role == "LEAD_FACULTY":
        return _courses_with_sections(world, world.plan.courses_led_by(node.person))
    if node.role == "CHAIR":
        return _subtree_of_department(world, node.scope)
    if node.role == "DEAN":
        return _subtree_of_college(world, node.scope)
    if node.role == "ASSISTANT_DEAN":
        return nothing()
    pytest.fail(f"The plan holds a {node.role} assignment, which this expectation does not grade.")


def expected_purviews(world: BuiltWorld) -> list[Levels]:
    """Every assignment's purview: own grant, plus each child's clamped purview.

    A `LEAD_FACULTY` assignment's purview is its own grant and nothing else (the
    ticket's clamp), so a lead child contributes its own grant only, and nothing
    that reports to a lead reaches the lead or anyone above it through the lead.
    """
    plan = world.plan
    own = [expected_own_grant(world, index) for index in range(len(plan.nodes))]
    memo: dict[int, Levels] = {}

    def purview(index: int) -> Levels:
        if index not in memo:
            if plan.nodes[index].role == "LEAD_FACULTY":
                memo[index] = own[index]
            else:
                memo[index] = joined(own[index], *(purview(c) for c in plan.children_of(index)))
        return memo[index]

    return [purview(index) for index in range(len(plan.nodes))]


def expected_scope(world: BuiltWorld, purviews: list[Levels], person: int) -> Levels:
    """A person's leadership scope: the union over their leadership assignments only (ruling 4)."""
    return joined(
        *(
            purviews[index]
            for index, node in enumerate(world.plan.nodes)
            if node.person == person and node.role in LEADERSHIP_ROLES
        )
    )
