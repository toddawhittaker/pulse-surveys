"""The purview walk over generated forests and mappings — E9-01, done-when 4 to 7.

> 4. Over generated forests and mappings (assistant-dean insertions, two-hat
>    people, cross-department led courses, instructor edges into leads), no
>    `LEAD_FACULTY` assignment's purview contains a course mapped to another
>    person. Marked `invariant`. The generator draws the instructor-edge-into-a-
>    lead case, and a test asserts that it does (MISTAKES entry 15).
> 5. For every edge, the parent's purview contains the child's clamped purview.
> 6. For every assignment, its purview equals a set the test computes on its
>    own … The person's leadership scope equals the union of those sets across
>    their leadership assignments.
> 7. Adding a `CARE` or `ADMIN` assignment to any person in a generated forest
>    changes no leadership scope.

The worlds come from `tests/fixtures/purview_walk.py::world_plans`, which reuses
E0-09's `climbing_forest` and widens it with a containment tree, people who wear
several hats, a Lead Faculty mapping, and a planted instructor edge into a lead
on a sibling lead's course. The expected purviews are computed there from the
plan alone (`docs/MISTAKES.md` entry 19), never by calling `authz`.

**The calls under test, as the ticket names them.** `authz.transitive_purview(
session, assignment_id=…)` is E0-11's seam signature, now answering a `Purview`;
`authz.resolve_scope(session, person_id=…)` is the leadership scope the ticket's
chokepoint resolves ("`resolve_scope` (or whatever replaces it)"). Both run on
the `supervision_graph` session — the bootstrap identity, inside one rolled-back
transaction, the way E0-09's properties run. The production connection is
exercised by the example tests beside this module and by the seeded worked
example (`docs/MISTAKES.md` entry 46).

**One reading the ticket leaves to its own done-when 3, stated here.**
Done-when 5 says "for every edge, the parent's purview contains the child's
clamped purview", and done-when 3 says an instructor reporting to lead A from a
sibling lead's course "adds nothing to A's purview". Both hold only if
done-when 5 is read over edges whose parent is not a `LEAD_FACULTY` assignment:
the clamp is exactly that a lead's purview does not cover what reports to it. So
property 5 below ranges over every edge into a chair, an assistant dean or a
dean, and property 4 and 6 carry the lead's side.

**Which failure a red is, before E9-01 lands.** Every property calls
`transitive_purview`, which raises `NotImplementedError` today, so each is a
FAILED on that exception in its first example. The generator-coverage tests are
green before and after: they assert what the plan strategy draws and touch no
code under test. A red there means this module's generator is broken, not the
walk.
"""

from typing import Any

import pytest
from fixtures.purview_walk import (
    LEADERSHIP_ROLES,
    WorldPlan,
    build_world,
    covers,
    difference,
    expected_purviews,
    expected_scope,
    has_a_cross_department_lead,
    has_a_two_hat_person,
    has_an_assistant_dean_insertion,
    has_an_instructor_edge_into_a_lead_on_another_persons_course,
    joined,
    levels,
    world_plans,
    written,
)
from hypothesis import HealthCheck, find, given, settings
from hypothesis import strategies as st
from hypothesis.errors import NoSuchExample

pytestmark = [pytest.mark.integration, pytest.mark.slow]

DATABASE_BACKED = settings(
    max_examples=20,
    deadline=None,
    # One `supervision_graph`, one transaction, twenty examples — the arrangement
    # `test_supervision_graph_properties.py` uses and explains. Every example
    # writes fresh colleges and fresh people, so no example can see another's.
    suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
    ],
)

# How hard `find` looks for each shape before reporting that the generator never
# draws it. Pure Python, no database, so a generous budget costs little.
COVERAGE_BUDGET = settings(
    max_examples=2000,
    deadline=None,
    database=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


def walked(authz: Any, session: Any, world: Any, index: int) -> dict[str, frozenset[Any]]:
    """`transitive_purview` for one planned assignment, as levels."""
    return levels(authz.transitive_purview(session, assignment_id=world.assignments[index]))


def scoped(authz: Any, session: Any, world: Any, person: int) -> dict[str, frozenset[Any]]:
    """`resolve_scope`'s purview for one planned person, as levels."""
    return levels(authz.resolve_scope(session, person_id=world.persons[person]).purview)


def leaders(plan: WorldPlan) -> list[int]:
    """The planned people holding at least one leadership assignment.

    The ticket says what a leadership scope is for a person who holds a
    leadership assignment, and nothing about what resolving one answers for a
    person who holds none (an empty scope, or a refusal). So the scope properties
    range over leaders only, and that choice stays the builder's.
    """
    return sorted({node.person for node in plan.nodes if node.role in LEADERSHIP_ROLES})


# ---------------------------------------------------------------------------
# The generator reaches the shapes the ticket names (`docs/MISTAKES.md` entry 15).
# ---------------------------------------------------------------------------

PLAN_SHAPES = {
    "an instructor edge into a lead on another person's course": (
        has_an_instructor_edge_into_a_lead_on_another_persons_course
    ),
    "an assistant-dean insertion": has_an_assistant_dean_insertion,
    "a two-hat person": has_a_two_hat_person,
    "a cross-department led course": has_a_cross_department_lead,
}


@pytest.mark.parametrize(
    "shape",
    [
        pytest.param(
            "an instructor edge into a lead on another person's course",
            marks=pytest.mark.invariant,
            id="instructor-edge-into-a-lead",
        ),
        pytest.param("an assistant-dean insertion", id="assistant-dean-insertion"),
        pytest.param("a two-hat person", id="two-hat-person"),
        pytest.param("a cross-department led course", id="cross-department-lead"),
    ],
)
def test_the_generated_worlds_draw_each_shape_the_ticket_names(shape: str) -> None:
    """Done-when 4's last sentence, and the scope half of done-when 6's.

    "The generator draws the instructor-edge-into-a-lead case, and a test asserts
    that it does (MISTAKES entry 15)." The other three shapes are the ones the
    ticket lists in the same parenthesis, asserted the same way, because a
    property that names a shape in its docstring and never draws it is entry 15
    exactly. The instructor-edge case is marked `invariant` because the
    sibling-isolation properties below are only as strong as it.

    **Green before E9-01 lands, and a red means the generator is broken**, not
    the walk. **The mutation this kills:** a `world_plans` whose planted gadget
    is dropped and whose mapping never gives the instructor's course to a second
    person, which leaves every clamp assertion below vacuous.
    """
    predicate = PLAN_SHAPES[shape]
    try:
        found: WorldPlan = find(world_plans(), predicate, settings=COVERAGE_BUDGET)
    except NoSuchExample:
        pytest.fail(
            f"`world_plans` never drew {shape} in {COVERAGE_BUDGET.max_examples} attempts. The "
            "purview properties in this module name that shape, so without it they assert "
            "nothing about it (docs/MISTAKES.md entry 15). Widen the strategy in "
            "tests/fixtures/purview_walk.py."
        )
    assert predicate(found), f"`find` returned a plan that does not hold {shape}: {found}."


# ---------------------------------------------------------------------------
# Done-when 4 — sibling-lead disjointness.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
@DATABASE_BACKED
@given(plan=world_plans())
def test_no_lead_faculty_purview_holds_a_course_mapped_to_another_person(
    supervision_graph: Any, authz: Any, plan: WorldPlan
) -> None:
    """SPEC §4.1 item 2 over generated worlds: a lead's purview never holds another's course.

    For every `LEAD_FACULTY` assignment in the plan, its walked purview holds no
    course the mapping gives to a different person, and **no section of such a
    course either** — the instructor edge into a lead arrives as a section, so a
    walk that let it through would leave `course_ids` clean and put the sibling's
    section in `section_ids`.

    **The control in the body:** a lead whose person the mapping gives a course
    must hold at least one course, so a walk answering an empty purview for every
    lead is red here rather than vacuously disjoint (`docs/MISTAKES.md` entry 3).

    **The mutations this kills:** the clamp removed (a lead's purview unions what
    reports to it, so the planted instructor's sibling section arrives); a lead's
    courses read from the assignment's scope column or widened to its prefix (the
    sibling course under the same prefix arrives); the mapping read for every
    person rather than the lead's own. **The near miss that must stay green:** a
    lead mapped to two courses holds both.
    """
    world = build_world(supervision_graph, plan)
    session = supervision_graph.session
    course_ids, section_ids = world.ids["course"], world.ids["section"]

    leaks: list[str] = []
    empty_leads: list[int] = []
    for index, node in enumerate(plan.nodes):
        if node.role != "LEAD_FACULTY":
            continue
        held = walked(authz, session, world, index)
        theirs = {
            course_ids[course]
            for course, lead in enumerate(plan.lead_of_course)
            if lead is not None and lead != node.person
        }
        their_sections = {
            section_ids[section]
            for section, course in enumerate(plan.section_course)
            if course_ids[course] in theirs
        }
        if plan.courses_led_by(node.person) and not held["course_ids"]:
            empty_leads.append(index)
        crossed = (held["course_ids"] & theirs) | (held["section_ids"] & their_sections)
        if crossed:
            leaks.append(f"assignment {index} holds {sorted(map(str, crossed))}")

    assert not empty_leads, (
        f"Lead assignments {empty_leads} hold no course although the mapping gives their person "
        "at least one, so the disjointness below would be satisfied by a walk that answers "
        f"nothing (docs/MISTAKES.md entry 3). Plan: {plan}."
    )
    assert not leaks, (
        f"A Lead Faculty purview holds another person's course or one of its sections: {leaks}. "
        "SPEC §4.1 item 2: 'A Lead Faculty assignment never grants sibling leads' courses, at any "
        "point in the purview union computation.' The ticket's clamp: a LEAD_FACULTY "
        f"assignment's purview is its own grant only, whatever reports to it. Plan: {plan}."
    )


# ---------------------------------------------------------------------------
# Done-when 5 — parent covers child.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
@DATABASE_BACKED
@given(plan=world_plans())
def test_every_parent_above_a_lead_covers_its_childs_clamped_purview(
    supervision_graph: Any, authz: Any, plan: WorldPlan
) -> None:
    """For every edge into a chair, an assistant dean or a dean, the parent holds the child's purview.

    The child's purview is the clamped one: for a lead child that is its own
    grant, for anyone else the whole walk below it. Edges into a lead are
    excluded, and the module docstring says why — done-when 3 is the statement
    that a lead does *not* cover what reports to it.

    **The control in the body:** every child whose purview the plan says holds
    something must come back holding something, so a walk answering empty sets
    everywhere — under which every containment is trivially true — is red here.

    **The mutations this kills:** a one-level union (a dean's purview misses its
    assistant dean's chairs' departments); a walk that stops at a fixed depth
    shallower than the plan; a parent that takes a lead child's *unclamped* set
    and a child that loses it are told apart by property 6, not here.
    """
    world = build_world(supervision_graph, plan)
    session = supervision_graph.session
    wanted = expected_purviews(world)
    got = [walked(authz, session, world, index) for index in range(len(plan.nodes))]

    hollow = [
        index
        for index in range(len(plan.nodes))
        if any(wanted[index].values()) and not any(got[index].values())
    ]
    assert not hollow, (
        f"Assignments {hollow} came back holding nothing although the plan says they hold "
        "something, so the containments below would be satisfied by a walk that answers nothing "
        f"(docs/MISTAKES.md entry 3). Plan: {plan}."
    )

    uncovered = [
        f"{node.parent} ({plan.nodes[node.parent].role}) does not cover {index} ({node.role}): "
        f"{difference(got[node.parent], joined(got[node.parent], got[index]))}"
        for index, node in enumerate(plan.nodes)
        if node.parent is not None
        and plan.nodes[node.parent].role != "LEAD_FACULTY"
        and not covers(got[node.parent], got[index])
    ]
    assert not uncovered, (
        f"A parent's purview does not hold its child's: {uncovered}. SPEC §2.1: 'Purview"
        "(assignment) = own grant union the purviews of all assignments transitively reporting "
        f"to it'. Plan: {plan}."
    )


# ---------------------------------------------------------------------------
# Done-when 6 — equal to an independent computation.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
@DATABASE_BACKED
@given(plan=world_plans())
def test_every_purview_and_every_leadership_scope_equals_the_independent_computation(
    supervision_graph: Any, authz: Any, plan: WorldPlan
) -> None:
    """Each assignment's purview, and each person's leadership scope, equal the plan's own answer.

    The expectation is `expected_purviews` in `tests/fixtures/purview_walk.py`:
    the assignment's own grant by SPEC §2.1's role grain, together with the
    clamped purviews of its children, computed from the plan and never from the
    code under test (`docs/MISTAKES.md` entry 19). A person's leadership scope is
    the union of those sets over their `LEAD_FACULTY`, `CHAIR`, `ASSISTANT_DEAN`
    and `DEAN` assignments (ruling 4; VP is outside the generator, see the
    fixture's docstring). Every planned person holding a leadership assignment
    is checked — including two-hat people whose other hat is `INSTRUCTOR`, which
    ruling 4 keeps out of the scope. People holding no leadership assignment are
    not resolved: the ticket does not say whether that answers an empty scope or
    a refusal (see `leaders`).

    The generator's draw of an instructor edge into a lead is asserted by
    `test_the_generated_worlds_draw_each_shape_the_ticket_names`, as done-when 6
    asks.

    **The mutations this kills, the ticket's own first:** a walk that clamps a
    lead's own result but passes the unclamped set up to the chair (the planted
    sibling section appears in the chair's purview and in the chair holder's
    scope); a walk by person rather than by assignment (a two-hat person's
    instructor or lead edges merge into their other hat); `INSTRUCTOR`
    assignments contributing to a leadership scope; a one-level union; an
    assistant dean's own grant read off the college.
    """
    world = build_world(supervision_graph, plan)
    session = supervision_graph.session
    wanted = expected_purviews(world)

    wrong_purviews = {
        f"{index} ({node.role})": difference(walked(authz, session, world, index), wanted[index])
        for index, node in enumerate(plan.nodes)
    }
    wrong_purviews = {where: diff for where, diff in wrong_purviews.items() if diff}

    wrong_scopes = {
        person: difference(
            scoped(authz, session, world, person), expected_scope(world, wanted, person)
        )
        for person in leaders(plan)
    }
    wrong_scopes = {person: diff for person, diff in wrong_scopes.items() if diff}

    assert not wrong_purviews, (
        f"These assignments' walked purviews differ from SPEC §2.1's union computed from the plan: "
        f"{wrong_purviews}. Plan: {plan}."
    )
    assert not wrong_scopes, (
        f"These people's leadership scopes differ from the union of their leadership assignments' "
        f"purviews (ruling 4: LEAD_FACULTY, CHAIR, ASSISTANT_DEAN, DEAN and VP_ACADEMICS only): "
        f"{wrong_scopes}. Plan: {plan}."
    )


# ---------------------------------------------------------------------------
# Done-when 7 — Care and Admin never contribute.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
@DATABASE_BACKED
@given(
    plan=world_plans(),
    target=st.integers(min_value=0, max_value=63),
    role=st.sampled_from(("CARE", "ADMIN")),
)
def test_a_care_or_admin_assignment_changes_no_leadership_scope(
    supervision_graph: Any, authz: Any, plan: WorldPlan, target: int, role: str
) -> None:
    """Adding a `CARE` or `ADMIN` hat to any person in a generated world changes nobody's scope.

    SPEC §5.5 (ruling 4): "Care and Admin assignments never contribute to a
    purview." Both are scoped to the institution (SPEC §2's table), so a scope
    that unioned either in would hold the whole institution, and would hold it
    for a person who may also lead a course.

    **The control in the body, before the hat is added:** every planned person's
    scope equals the independent expectation, so "unchanged" cannot be satisfied
    by a resolver that answers an empty scope both times.

    **The mutations this kill:** `resolve_scope` dropping its skip of Care or of
    Admin (the institution arrives); the leadership-role filter widened to every
    role; a Care hat that makes the resolver refuse or empty the person's scope.
    """
    world = build_world(supervision_graph, plan)
    session = supervision_graph.session
    wanted = expected_purviews(world)

    resolved = leaders(plan)
    before = {person: scoped(authz, session, world, person) for person in resolved}
    off = {
        person: difference(before[person], expected_scope(world, wanted, person))
        for person in resolved
    }
    off = {person: diff for person, diff in off.items() if diff}
    assert not off, (
        f"Before any {role} hat was added, these scopes already differ from the expectation: {off}. "
        "The comparison below would then be about a resolver that is wrong for another reason; "
        "property 6 diagnoses it."
    )

    holder = target % plan.person_count
    written(
        supervision_graph,
        lambda: supervision_graph.assign(
            role, scope=world.institution, person=world.persons[holder], reports_to=None
        ),
        f"A {role} assignment at the institution for planned person {holder}",
    )

    after = {person: scoped(authz, session, world, person) for person in resolved}
    changed = {
        person: difference(after[person], before[person])
        for person in resolved
        if after[person] != before[person]
    }
    assert not changed, (
        f"Giving planned person {holder} a {role} assignment changed these leadership scopes: "
        f"{changed}. SPEC §5.5: 'Care and Admin assignments never contribute to a purview'; "
        f"§2: 'Care is deliberately not composable with reporting roles.' Leadership roles are "
        f"{LEADERSHIP_ROLES}. Plan: {plan}."
    )
