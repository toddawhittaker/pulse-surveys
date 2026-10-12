"""The lead clamp, the instructor hat, and a lead under two chairs — E9-01, done-when 3, 8 and 9.

> 3. An `INSTRUCTOR` assignment in sibling lead B's course that reports to lead A
>    adds nothing to A's purview and nothing to A's chair's purview through A. The
>    same section reaches the chair when it lies in the chair's own department,
>    through the department grant only.
> 8. A chair who also teaches a section in another department has a leadership
>    scope without that section, and the section is reached through the
>    instructor session only.
> 9. A person who holds two lead assignments, each reporting to a different
>    chair, hands both chairs every course mapped to that person, because the
>    mapping is per person. Test it as the spec's literal meaning.

**Each refusal-shaped assertion has a present twin** in the same test and the
same purview: the node that must be absent is asserted absent beside a node that
must be present, so a walk that answers nothing fails rather than passing
(`docs/MISTAKES.md` entry 3). The section that must not reach A is also shown to
be a real, reachable node — sibling lead B's purview holds it.

**On "refused".** A purview is a value, not a read; the ticket's done-whens here
are statements about what the value holds, so these tests compare values. The
refusal of a read *through* the purview is `scoped_reader`'s, asserted in
`test_a_scoped_reader_refuses_what_is_outside_the_purview.py`.

Every read runs over `application_session`, the `pulse_app` connection, on rows
`committed_rows` commits (`docs/MISTAKES.md` entry 46).

**Which failure a red is, before E9-01 lands.** `transitive_purview` raises
`NotImplementedError`, so the walked tests fail on that exception. Done-when 8
reads `resolve_scope`, which answers today and unions the instructor hat in, so
it fails on its assertion; done-when 9's chairs are walked and fail on the raise.
"""

from typing import Any

import pytest
from fixtures.purview_walk import levels, role_token, written

pytestmark = pytest.mark.integration

# Everything strictly above a course, plus the term: what a sibling course keeps.
ABOVE_A_COURSE = ("institution", "college", "department", "prefix", "term")


def department_branch(rows: Any) -> dict[str, Any]:
    """A fresh department under the shared college, with a prefix, a course and a section."""
    rows.graph.scope("section")
    chain = rows.graph.new_branch("institution", "college", "term")
    rows.seed("section", chain)
    return chain


def sibling_course(rows: Any, chain: dict[str, Any]) -> dict[str, Any]:
    """A second course, with a section, under the prefix `chain` already holds."""
    branch = {name: row for name, row in chain.items() if name in ABOVE_A_COURSE}
    rows.seed("section", branch)
    return branch


def node_id(rows: Any, chain: dict[str, Any], level: str) -> Any:
    return rows.graph.key_of(level, chain[level])


def walked(authz: Any, session: Any, assignment: Any, graph: Any) -> dict[str, frozenset[Any]]:
    return levels(authz.transitive_purview(session, assignment_id=assignment[graph.assignment_key]))


def a_lead(rows: Any, course: Any, *, reports_to: Any, person: Any = None) -> tuple[Any, Any]:
    """A person mapped to `course`, with a `LEAD_FACULTY` assignment on it. Returns (person, row)."""
    graph = rows.graph
    holder = graph.person() if person is None else person
    written(
        graph, lambda: graph.lead_mapping(person=holder, course=course), "A lead faculty mapping"
    )
    row = written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", scope=course, person=holder, reports_to=reports_to),
        "A lead faculty assignment",
    )
    return holder, row


@pytest.mark.invariant
def test_an_instructor_on_a_sibling_leads_course_adds_nothing_to_the_lead_or_the_chair_above(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """Done-when 3's first sentence: the clamp, with B's course in another department.

    Chair C holds department D. Lead A leads a course in D and reports to C. Lead
    B leads a course in department D2, which C does not hold. An instructor on a
    section of B's course reports to A. Then A's purview is exactly A's own grant,
    and C's purview holds D's subtree and nothing of B's course: the section does
    not reach A, and does not reach C *through* A.

    **The control:** B's own purview holds the section, so it is a real node the
    walk can reach — the absence in A's and C's purviews is about the clamp.

    **The mutations this kill:** the clamp removed (A unions the instructor's
    section); the clamp applied to A's own result but the unclamped set passed up
    to C (the ticket names this one); a walk by person in which the instructor's
    holder and A's merge. **The near miss that must stay green:** A's own course
    and section, and every node of D, are present.
    """
    rows = committed_rows
    graph = rows.graph
    key = graph.assignment_key
    home = department_branch(rows)
    elsewhere = department_branch(rows)
    chair = written(
        graph,
        lambda: graph.assign("CHAIR", scope=node_id(rows, home, "department"), reports_to=None),
        "Chair C, on department D",
    )
    _, lead_a = a_lead(rows, node_id(rows, home, "course"), reports_to=chair[key])
    _, lead_b = a_lead(rows, node_id(rows, elsewhere, "course"), reports_to=None)
    siblings_section = node_id(rows, elsewhere, "section")
    written(
        graph,
        lambda: graph.assign("INSTRUCTOR", scope=siblings_section, reports_to=lead_a[key]),
        "An instructor on a section of B's course, reporting to A",
    )
    rows.commit()

    a_holds = walked(authz, application_session, lead_a, graph)
    b_holds = walked(authz, application_session, lead_b, graph)
    c_holds = walked(authz, application_session, chair, graph)

    assert siblings_section in b_holds["section_ids"], (
        f"Lead B's purview {b_holds} does not hold a section of B's own course, so the absences "
        "below say nothing about the clamp."
    )
    assert a_holds["course_ids"] == frozenset({node_id(rows, home, "course")}), (
        f"Lead A's purview holds courses {sorted(map(str, a_holds['course_ids']))}; the mapping "
        "gives A exactly one."
    )
    assert a_holds["section_ids"] == frozenset({node_id(rows, home, "section")}), (
        f"Lead A's purview holds sections {sorted(map(str, a_holds['section_ids']))}; A's own "
        f"grant is one section, and B's section {siblings_section} came through the instructor "
        "edge. The ticket: 'A LEAD_FACULTY assignment's purview is its own grant only, whatever "
        "reports to it.'"
    )
    assert (
        node_id(rows, home, "department") in c_holds["department_ids"]
    ), f"Chair C's purview {c_holds} does not hold C's own department."
    assert siblings_section not in c_holds["section_ids"], (
        f"Chair C's purview holds B's section {siblings_section}, which C reaches only through "
        "lead A. SPEC §4.1 item 2: a Lead Faculty assignment never grants sibling leads' "
        "courses, 'at any point in the purview union computation'."
    )
    assert (
        node_id(rows, elsewhere, "course") not in c_holds["course_ids"]
    ), "Chair C's purview holds B's course, which sits in a department C does not chair."


@pytest.mark.invariant
def test_the_same_section_reaches_the_chair_when_it_lies_in_the_chairs_own_department(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """Done-when 3's second sentence: the pair to the test above.

    The same arrangement, with B's course a sibling of A's under one prefix in
    department D. The instructor edge into A still adds nothing to A — the clamp
    does not depend on where the course is — and the section is in C's purview,
    because C's department grant holds it.

    **The mutations this kills:** a clamp written as "drop every section of a
    course mapped to someone else" from the chair's whole purview (C loses part
    of its own department); a chair grant that excludes courses with a lead.
    """
    rows = committed_rows
    graph = rows.graph
    key = graph.assignment_key
    home = department_branch(rows)
    beside = sibling_course(rows, home)
    chair = written(
        graph,
        lambda: graph.assign("CHAIR", scope=node_id(rows, home, "department"), reports_to=None),
        "Chair C, on department D",
    )
    _, lead_a = a_lead(rows, node_id(rows, home, "course"), reports_to=chair[key])
    a_lead(rows, node_id(rows, beside, "course"), reports_to=chair[key])
    siblings_section = node_id(rows, beside, "section")
    written(
        graph,
        lambda: graph.assign("INSTRUCTOR", scope=siblings_section, reports_to=lead_a[key]),
        "An instructor on a section of B's course, reporting to A",
    )
    rows.commit()

    a_holds = walked(authz, application_session, lead_a, graph)
    c_holds = walked(authz, application_session, chair, graph)

    assert (
        node_id(rows, home, "section") in a_holds["section_ids"]
    ), f"Lead A's purview {a_holds} does not hold A's own section."
    assert siblings_section not in a_holds["section_ids"], (
        f"Lead A's purview holds B's section {siblings_section} through the instructor edge. "
        "The clamp holds wherever B's course sits."
    )
    assert siblings_section in c_holds["section_ids"], (
        f"Chair C's purview does not hold section {siblings_section}, which lies in C's own "
        "department. SPEC §2.1: 'a chair's is the department subtree'."
    )


@pytest.mark.invariant
def test_a_chair_who_teaches_in_another_department_has_a_leadership_scope_without_that_section(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """Done-when 8 (ruling 4): the instructor hat stays out of the leadership scope.

    One person holds a `CHAIR` assignment on department D1 and an `INSTRUCTOR`
    assignment on a section in department D2, reporting to D2's lead. Their
    leadership scope holds D1's subtree and not the taught section; the scope's
    `grants` name the chair assignment and not the instructor one; and the
    section is reached through the instructor hat — `transitive_purview` on that
    assignment answers it — which is what the instructor session is resolved
    from.

    **The mutations this kill:** `resolve_scope` unioning every reporting
    assignment, `INSTRUCTOR` included (its behaviour before E9-01); `grants`
    built over every assignment the person holds. **The near miss that must stay
    green:** the instructor assignment's own purview still answers its section.
    """
    rows = committed_rows
    graph = rows.graph
    key = graph.assignment_key
    chaired = department_branch(rows)
    taught = department_branch(rows)
    person = graph.person()
    chair = written(
        graph,
        lambda: graph.assign(
            "CHAIR", scope=node_id(rows, chaired, "department"), person=person, reports_to=None
        ),
        "Their chair assignment, on D1",
    )
    _, other_lead = a_lead(rows, node_id(rows, taught, "course"), reports_to=None)
    section = node_id(rows, taught, "section")
    teaching = written(
        graph,
        lambda: graph.assign(
            "INSTRUCTOR", scope=section, person=person, reports_to=other_lead[key]
        ),
        "Their instructor assignment, on a section in D2",
    )
    rows.commit()

    scope = authz.resolve_scope(application_session, person_id=person)
    held = levels(scope.purview)
    granted = {str(entry[0]): role_token(entry[1]) for entry in scope.grants}
    through_the_teaching_hat = walked(authz, application_session, teaching, graph)

    assert (
        node_id(rows, chaired, "department") in held["department_ids"]
    ), f"The chair's leadership scope {held} does not hold their own department."
    assert section not in held["section_ids"], (
        f"The chair's leadership scope holds section {section}, which they reach only by "
        "teaching it. Ruling 4 (SPEC §5.5): 'Leadership views use the union of leadership "
        "assignments only. An instructor assignment is reached through the role switcher, never "
        "merged into a leadership tree.'"
    )
    assert (
        node_id(rows, taught, "course") not in held["course_ids"]
    ), "The chair's leadership scope holds the course of the section they teach."
    assert granted == {str(chair[key]): "CHAIR"}, (
        f"The scope's grants are {granted}; the person's one leadership assignment is the chair "
        f"assignment {chair[key]}. The ticket: `grants` holds 'one (assignment id, role, "
        "purview) per leadership assignment'."
    )
    assert through_the_teaching_hat["section_ids"] == frozenset({section}), (
        f"The instructor assignment walked to {through_the_teaching_hat}, not to the section it "
        "teaches; the section must stay reachable through that hat."
    )


@pytest.mark.invariant
def test_a_person_leading_under_two_chairs_hands_both_chairs_every_course_mapped_to_them(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """Done-when 9, as SPEC §2.1's literal meaning: the mapping is per person.

    Lead L holds two `LEAD_FACULTY` assignments: one on course c1 reporting to
    chair X of D1, one on course c2 reporting to chair Y of D2. The mapping gives
    L both courses, and both sit in a third department D3 that neither chair
    holds, so the only route to them is the walk. Each lead assignment's own
    grant is "only the courses they lead" — both — so each chair holds both.

    **Exact, not only present:** X's purview is D1's subtree plus c1, c2 and their
    sections, and nothing of D2.

    **The mutations this kill:** a lead's grant read off its assignment's scope
    column (X gets c1 only); a lead under X contributing to Y; a walk that dedupes
    by person and attaches L to one chair only.
    """
    rows = committed_rows
    graph = rows.graph
    key = graph.assignment_key
    first_chaired = department_branch(rows)
    second_chaired = department_branch(rows)
    led = department_branch(rows)
    also_led = sibling_course(rows, led)
    c1, c2 = node_id(rows, led, "course"), node_id(rows, also_led, "course")
    led_sections = {node_id(rows, led, "section"), node_id(rows, also_led, "section")}

    chair_x = written(
        graph,
        lambda: graph.assign(
            "CHAIR", scope=node_id(rows, first_chaired, "department"), reports_to=None
        ),
        "Chair X, on D1",
    )
    chair_y = written(
        graph,
        lambda: graph.assign(
            "CHAIR", scope=node_id(rows, second_chaired, "department"), reports_to=None
        ),
        "Chair Y, on D2",
    )
    lead_person, _ = a_lead(rows, c1, reports_to=chair_x[key])
    a_lead(rows, c2, reports_to=chair_y[key], person=lead_person)
    rows.commit()

    x_holds = walked(authz, application_session, chair_x, graph)
    y_holds = walked(authz, application_session, chair_y, graph)

    for name, held, own in (
        ("X", x_holds, first_chaired),
        ("Y", y_holds, second_chaired),
    ):
        assert (
            node_id(rows, own, "department") in held["department_ids"]
        ), f"Chair {name}'s purview {held} does not hold its own department."
        assert {c1, c2} <= held["course_ids"], (
            f"Chair {name}'s purview holds courses {sorted(map(str, held['course_ids']))}, not "
            f"both {c1} and {c2}. The mapping gives lead L both, and L's assignment under chair "
            f"{name} grants 'only the courses they lead' (SPEC §2.1) — every course mapped to L."
        )
        assert (
            led_sections <= held["section_ids"]
        ), f"Chair {name}'s purview is missing a section of L's courses."

    expected_x = {
        "institution_ids": frozenset(),
        "college_ids": frozenset(),
        "department_ids": frozenset({node_id(rows, first_chaired, "department")}),
        "prefix_ids": frozenset({node_id(rows, first_chaired, "prefix")}),
        "course_ids": frozenset({node_id(rows, first_chaired, "course"), c1, c2}),
        "section_ids": frozenset({node_id(rows, first_chaired, "section")}) | led_sections,
    }
    assert x_holds == expected_x, (
        f"Chair X walked to {x_holds} rather than D1's subtree plus L's two courses ({expected_x}). "
        "Anything of D2 here came from chair Y's side of the graph."
    )
