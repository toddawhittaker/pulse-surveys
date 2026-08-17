"""An assignment's own grant is its scope restricted by role grain — ticket E0-11.

SPEC §2.1: "**Purview(assignment) = own grant union the purviews of all
assignments transitively reporting to it**, with the own grant restricted by
role grain: a Lead Faculty's grant is only the courses they lead (never sibling
leads' courses, at any point in the union); a chair's is the department subtree;
a dean's the college."

The union is E9's and raises here (ADR 0003,
`tests/unit/test_deferred_authz_seams_fail_closed.py`). The own grant is E0-11's,
and it is the whole of what this module asserts: the role grains, the lead's
authority question, and §4.1 invariant 2 at the level it can already be broken.

**The assistant dean was the grain with no test, and it is the one §2.1 argues
about.** SPEC §2.1's canonical chain ranks six roles; the tests below covered the
grain of instructor, lead, chair, dean and VP, and the role the spec picks as its
own worked example had nothing standing behind it. That role is the case §2.1
makes *against* reading a grant off a containment node: "the assistant dean is
the worked example for why purview comes from the graph: own led courses union
every supervised chair's department — a set no single containment node holds",
and §2's table says the same from the other side, giving the scope as "College
(same node as the dean — **authority comes from the supervision graph, not the
scope**)". §2.1's own-grant sentence names a lead, a chair and a dean, and
pointedly does not name an assistant dean.

So the own grant of an `ASSISTANT_DEAN` assignment is empty. Both halves of the
set §2.1 describes arrive from somewhere else: the led courses from the person's
own `LEAD_FACULTY` assignment, and the supervised chairs' departments from E9's
transitive walk, which is the deferred seam that raises here. An assistant dean
therefore sees nothing in E0, which is what ADR 0003 already says about
leadership landing views in this epic. A security review of E0-11 measured the
opposite — the college, a supervised department, an unsupervised department and
an unsupervised section, all present in the own grant — and the tests under the
last heading in this file are that gap closed.

**Every read runs over a `pulse_app` connection.** `db_session` connects as the
bootstrap superuser, which passes every grant; from E0-10 on, `pulse_app` holds
`SELECT` on the two read views and on nothing else, so a resolver that works over
a superuser session and not over this one is a resolver that works in the test
suite and nowhere else. The rows are therefore seeded through `committed_rows`,
which commits them so a second connection can see them and removes them
afterwards, and read back through `application_session`. A test in this file that
fails with "permission denied" is reporting a missing grant or a missing view, and
that is a real half of the criterion rather than an obstacle to it.

**A purview is compared whole, not level by level.** Every assertion below is one
equality over all six levels, because the failures worth catching are asymmetric:
a chair whose `prefix_ids` are right and whose `section_ids` are empty renders a
tree with no leaves, and a chair who also holds `college_ids` sees a sibling
department. Comparing the whole value names which level moved, in one line, and
does not go quietly green when a level nobody thought about is populated.

**Where the sets are exact and where they are not.** Everything a test seeds under
its own department or college is private to it, so those comparisons are exact.
The institution is not: `SupervisionGraph` deliberately never writes a second one
— whether a deployment holds one institution or many is an open spec question
([E0-22](../../docs/tickets/e0/E0-22-spec-questions-from-e0-05.md)) — so the VP
test asserts containment of what it seeded rather than equality with it, and says
so where it does.
"""

from typing import Any

import pytest

pytestmark = pytest.mark.integration

# The six levels of a `Purview`, in SPEC §2.1's containment order. Transcribed
# from E0-11's settled surface rather than read off the dataclass
# (`docs/MISTAKES.md` entry 19); `tests/unit/test_a_purview_holds_nodes_and_
# never_a_capability.py` is where the field list itself is asserted.
PURVIEW_LEVELS = (
    "institution_ids",
    "college_ids",
    "department_ids",
    "prefix_ids",
    "course_ids",
    "section_ids",
)

# The containment rows a second course shares with the first. Everything strictly
# above a course in §2.1's hierarchy, plus the term, since two courses in two
# terms would not be siblings in any sense a purview cares about.
ABOVE_A_COURSE = ("institution", "college", "department", "prefix", "term")


def written(graph: Any, action: Any, what: str) -> Any:
    """Perform a write that has to succeed, and fail naming it when it does not.

    A copy of the helper in `tests/integration/test_role_assignment_graph.py`; see
    that module's docstring for why these are copied rather than imported.
    """
    holder: dict[str, Any] = {}

    def perform() -> None:
        holder["row"] = action()

    refused = graph.refusal(perform)
    assert refused is None, (
        f"{what} was refused: {refused}. It is a control rather than the subject: nothing after "
        "it in this test can mean anything (`docs/MISTAKES.md` entry 3)."
    )
    return holder.get("row")


def subtree(rows: Any, *shared: str) -> dict[str, Any]:
    """A prefix, a course and a section, sharing `shared` with the graph's own chain.

    Seeding a `section` builds every ancestor it needs and stops there, so naming
    the levels to keep is the whole of what makes two subtrees siblings: keep the
    department and they are two prefixes in it, keep only the college and they are
    two departments.
    """
    chain = rows.graph.new_branch(*shared)
    rows.seed("section", chain)
    return chain


def sibling_course(rows: Any, chain: dict[str, Any]) -> dict[str, Any]:
    """A second course, with a section, under the prefix `chain` already holds."""
    branch = {name: row for name, row in chain.items() if name in ABOVE_A_COURSE}
    rows.seed("section", branch)
    return branch


def sibling_section(rows: Any, chain: dict[str, Any]) -> dict[str, Any]:
    """A second section under the course `chain` already holds."""
    branch = {name: row for name, row in chain.items() if name != "section"}
    rows.seed("section", branch)
    return branch


def node_id(rows: Any, chain: dict[str, Any], level: str) -> Any:
    """The primary key of the row `chain` holds at one containment level."""
    return rows.graph.key_of(level, chain[level])


def levels(purview: Any) -> dict[str, Any]:
    """Every level of one purview, by name, for a single whole-value comparison."""
    return {name: frozenset(getattr(purview, name)) for name in PURVIEW_LEVELS}


def grant(authz: Any, session: Any, assignment: Any, graph: Any) -> dict[str, Any]:
    """`own_grant` for one assignment row, as a mapping of level to ids."""
    return levels(authz.own_grant(session, assignment_id=assignment[graph.assignment_key]))


def expected(**populated: Any) -> dict[str, Any]:
    """A purview with the named levels populated and every other one empty.

    Written this way round on purpose: the levels a role does **not** hold are the
    assertion. A chair that also holds its college is not a slightly wrong answer,
    it is every sibling department in that college, and it is invisible to anyone
    it happens to.
    """
    return {name: frozenset(populated.get(name, ())) for name in PURVIEW_LEVELS}


def test_a_chairs_own_grant_is_its_department_and_everything_under_it(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """SPEC §2.1: "a chair's is the department subtree".

    Two prefixes hang off the department, each with a course and a section, so the
    assertion is about a *subtree* rather than about a single chain — a resolver
    that joins one prefix deep and stops passes a one-prefix fixture.

    §2.1's display labels are what the levels are for: "department rows `N
    prefixes · N sections`", and "chair [starts] at prefixes". A grant that
    reaches the courses and not the prefixes renders a tree with no roots.
    """
    rows = committed_rows
    graph = rows.graph
    department = graph.scope("department")
    first = subtree(rows, "institution", "college", "department")
    second = subtree(rows, "institution", "college", "department")
    chair = written(graph, lambda: graph.assign("CHAIR", scope=department), "A chair assignment")
    rows.commit()

    held = grant(authz, application_session, chair, graph)

    assert held == expected(
        department_ids={department},
        prefix_ids={node_id(rows, first, "prefix"), node_id(rows, second, "prefix")},
        course_ids={node_id(rows, first, "course"), node_id(rows, second, "course")},
        section_ids={node_id(rows, first, "section"), node_id(rows, second, "section")},
    ), (
        f"A chair scoped to one department resolved to {held}. SPEC §2.1 makes the own grant the "
        "scope restricted by role grain, and a chair's is the department subtree: the department, "
        "its prefixes, their courses and those courses' sections — and nothing above it. A "
        "`college_ids` or `institution_ids` here is every sibling department in the college, "
        "which is a widening nobody it happens to can detect."
    )


def test_a_chairs_own_grant_holds_no_sibling_department_and_nothing_under_one(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """The same grain from the other side, which is the side that is a confidentiality rule.

    E0-11's criterion: "A chair's grant covers its department's prefixes and no
    sibling department." The test above already compares the whole value, so this
    one is not new coverage — it is the failure message the next reader needs, and
    it survives a later change from exact equality to containment. §2.1 gives a
    college several departments and gives each its own chair; a resolver that
    walked from the college down, or that read the assignment's `college_id`
    because the coalesce over ADR 0025's five scope columns found it first, hands
    every one of them to every other.
    """
    rows = committed_rows
    graph = rows.graph
    department = graph.scope("department")
    mine = subtree(rows, "institution", "college", "department")
    theirs = subtree(rows, "institution", "college")
    chair = written(graph, lambda: graph.assign("CHAIR", scope=department), "A chair assignment")
    rows.commit()

    held = grant(authz, application_session, chair, graph)
    somebody_elses = {
        "department_ids": {node_id(rows, theirs, "department")},
        "prefix_ids": {node_id(rows, theirs, "prefix")},
        "course_ids": {node_id(rows, theirs, "course")},
        "section_ids": {node_id(rows, theirs, "section")},
    }

    overlap = {
        level: sorted(held[level] & nodes)
        for level, nodes in somebody_elses.items()
        if held[level] & nodes
    }
    assert node_id(rows, mine, "prefix") in held["prefix_ids"], (
        f"The chair's grant does not hold its own department's prefix: {held}. The disjointness "
        "assertion below is satisfied by a grant that holds nothing at all, so this comes first "
        "(`docs/MISTAKES.md` entry 3)."
    )
    assert not overlap, (
        f"A chair's grant reaches into a sibling department: {overlap}. SPEC §2.1 scopes a chair "
        "to one department and computes the own grant from that node; the sibling has a chair of "
        "its own, and neither of them is entitled to the other's sections."
    )


def test_a_deans_own_grant_is_its_college_and_everything_under_it(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """SPEC §2.1: "a dean's the college", and §2's table scopes the assignment there.

    Two departments under the college, each with a prefix, a course and a section,
    so the grant has to cross a department boundary — the level a chair's grant
    stops at. §2.1's tree roots make the same distinction visible: "VP starts at
    colleges, dean at departments, chair at prefixes".
    """
    rows = committed_rows
    graph = rows.graph
    college = graph.scope("college")
    first = subtree(rows, "institution", "college")
    second = subtree(rows, "institution", "college")
    dean = written(graph, lambda: graph.assign("DEAN", scope=college), "A dean assignment")
    rows.commit()

    held = grant(authz, application_session, dean, graph)

    assert held == expected(
        college_ids={college},
        department_ids={node_id(rows, first, "department"), node_id(rows, second, "department")},
        prefix_ids={node_id(rows, first, "prefix"), node_id(rows, second, "prefix")},
        course_ids={node_id(rows, first, "course"), node_id(rows, second, "course")},
        section_ids={node_id(rows, first, "section"), node_id(rows, second, "section")},
    ), (
        f"A dean scoped to one college resolved to {held}. §2.1 gives the dean the college and "
        "everything the containment hierarchy puts under it. An `institution_ids` here is every "
        "other college in the university — the widening ADR 0025 names as its worked example: 'a "
        "dean scoped to the institution hands one college's dean every college'."
    )


def test_a_vp_of_academics_own_grant_reaches_the_whole_institution(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """§2's table: the VP of Academics is scoped to the institution.

    **Containment rather than equality, and the reason is the fixture and not the
    rule.** `SupervisionGraph` refuses to write a second institution, because
    whether a deployment holds one or many is an open spec question (E0-22), so
    every row any test in this session seeds is under the one institution this
    test's VP holds. Asserting equality would make this test fail whenever another
    test's rows outlive it, which is a flake rather than a finding. What it can
    assert exactly is the top of the tree — `institution_ids` is the one node —
    and that everything seeded here is reachable from it.
    """
    rows = committed_rows
    graph = rows.graph
    institution = graph.scope("institution")
    first = subtree(rows, "institution")
    second = subtree(rows, "institution", "college")
    vp = written(graph, lambda: graph.assign("VP_ACADEMICS", scope=institution), "A VP assignment")
    rows.commit()

    held = grant(authz, application_session, vp, graph)
    seeded = {
        "college_ids": {node_id(rows, first, "college"), node_id(rows, second, "college")},
        "department_ids": {
            node_id(rows, first, "department"),
            node_id(rows, second, "department"),
        },
        "prefix_ids": {node_id(rows, first, "prefix"), node_id(rows, second, "prefix")},
        "course_ids": {node_id(rows, first, "course"), node_id(rows, second, "course")},
        "section_ids": {node_id(rows, first, "section"), node_id(rows, second, "section")},
    }

    assert held["institution_ids"] == frozenset({institution}), (
        f"The VP's grant holds {held['institution_ids']} at the institution level rather than the "
        f"one institution the assignment is scoped to. §2's table scopes the role there, and §2.1 "
        "starts its tree at the colleges under it."
    )
    missing = {
        level: sorted(nodes - held[level]) for level, nodes in seeded.items() if nodes - held[level]
    }
    assert not missing, (
        f"The VP's grant is missing {missing}. §2.1's own grant is the scope restricted by role "
        "grain and the VP's scope is the institution, so every node the containment hierarchy "
        "puts under it is held. A grant that stops at colleges renders a roll-up with no "
        "sections in it, which reads as missing data rather than as a scoping defect."
    )


def test_an_instructors_own_grant_is_exactly_its_own_section(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """§2's table: an instructor is scoped to a section, "per term".

    A second section of the same course is seeded so that the grant has something
    adjacent to be wrong about. §5.1's instructor report is per section and §4
    keeps the comparison set out of the section's own numbers, so an instructor
    whose grant reached the course would read another instructor's section as
    their own — and the two are usually taught by different adjuncts (§2: "~95%
    adjuncts").
    """
    rows = committed_rows
    graph = rows.graph
    mine = subtree(rows, "institution", "college", "department")
    theirs = sibling_section(rows, mine)
    instructor = written(
        graph,
        lambda: graph.assign("INSTRUCTOR", scope=node_id(rows, mine, "section")),
        "An instructor assignment on one section",
    )
    rows.commit()

    held = grant(authz, application_session, instructor, graph)

    assert held == expected(section_ids={node_id(rows, mine, "section")}), (
        f"An instructor scoped to one section resolved to {held}; the other section of the same "
        f"course is {node_id(rows, theirs, 'section')}. §2's table gives the instructor 'own "
        "reports, moderation, response publishing' for their section, and a grant carrying the "
        "course carries every other section in it — including the sections of colleagues whose "
        "weekly ratings §4 keeps to themselves."
    )


def test_a_lead_facultys_own_grant_is_exactly_the_courses_the_mapping_gives_them(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """SPEC §2.1: "a Lead Faculty's grant is only the courses they lead".

    **The mapping is what says which courses those are**, and this ticket settles
    it: `RoleAssignment`'s own docstring says "a purview resolver reads the
    mapping to decide which courses a lead holds, and reads this table only for
    the edges", and ADR 0025 says the assignment table's grain rule is "necessary
    and **not** sufficient" for §4.1 invariant 2. So a lead with three mapped
    courses resolves to three courses, whatever number of assignment rows they
    happen to hold.

    Three courses under one prefix, and `prefix_ids` empty in the expectation. That
    is not an oversight: ADR 0025 refuses a lead a prefix-shaped scope precisely
    because "it would grant the lead every course under that prefix, sibling
    leads' courses included, which is §4.1 invariant 2", and a purview that lists
    the prefix invites exactly the reading the scope column was denied. §2.1's
    "tree roots are the prefixes of their led courses" is a statement about where
    a *navigation tree starts*, computed from the courses, and not about what the
    lead holds.
    """
    rows = committed_rows
    graph = rows.graph
    lead_of = graph.person()
    first = subtree(rows, "institution", "college", "department")
    second = sibling_course(rows, first)
    third = sibling_course(rows, first)
    led = [first, second, third]

    for chain in led:
        written(
            graph,
            lambda chain=chain: graph.lead_mapping(
                person=lead_of, course=node_id(rows, chain, "course")
            ),
            "A lead-faculty mapping for one of the led courses",
        )
    assignment = written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", scope=node_id(rows, first, "course"), person=lead_of),
        "The lead's own assignment",
    )
    rows.commit()

    held = grant(authz, application_session, assignment, graph)

    assert held == expected(
        course_ids={node_id(rows, chain, "course") for chain in led},
        section_ids={node_id(rows, chain, "section") for chain in led},
    ), (
        f"A lead faculty member with three mapped courses resolved to {held}. §2.1: 'a mapping of "
        "individuals to the courses they lead (people and courses are not 1:1)', and the grant is "
        "'only the courses they lead'. One course means the resolver read the assignment's scope "
        "column instead of the mapping, which is the reading ADR 0025 rules out; a `prefix_ids` "
        "or `department_ids` means it walked upward, and everything under those nodes belongs to "
        "somebody else."
    )


@pytest.mark.invariant
def test_a_lead_faculty_assignment_on_another_leads_course_moves_no_grant(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """E0-11's criterion: "a test asserts a conflicting assignment row changes nothing".

    E0-09 left this measured and unclosed: "One lead per course is enforced on
    `lead_faculty_mapping` only — a table `role_assignment` does not reference.
    Two `LEAD_FACULTY` assignment rows on one course are accepted, and so is an
    assignment on a course whose mapping names a different person." This ticket
    answers it by deciding which table the resolver reads, so the assertion has
    two halves and needs both: the conflicting row **is written successfully**,
    and it **moves nothing**. Without the first half, a schema that had grown a
    constraint would satisfy the second by refusing the row, and the resolver
    could read whichever table it liked.

    Marked `invariant` because the state it describes is §4.1 item 2 exactly: a
    lead holding a course the mapping gives to somebody else is a lead seeing a
    sibling lead's course. The row is one an admin can write by hand today, and
    nothing about it looks wrong.
    """
    rows = committed_rows
    graph = rows.graph
    mine = graph.person()
    theirs = graph.person()
    my_chain = subtree(rows, "institution", "college", "department")
    their_chain = sibling_course(rows, my_chain)
    my_course = node_id(rows, my_chain, "course")
    their_course = node_id(rows, their_chain, "course")

    written(
        graph,
        lambda: graph.lead_mapping(person=mine, course=my_course),
        "The mapping that says which course is mine",
    )
    written(
        graph,
        lambda: graph.lead_mapping(person=theirs, course=their_course),
        "The mapping that gives the other course to somebody else",
    )
    my_assignment = written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", scope=my_course, person=mine),
        "My own lead-faculty assignment",
    )
    conflicting = written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", scope=their_course, person=mine),
        "A second lead-faculty assignment for me, on the course the mapping gives to somebody "
        "else — accepted by the schema, which is the premise of this criterion",
    )
    rows.commit()

    from_my_own = grant(authz, application_session, my_assignment, graph)
    from_the_conflicting_row = grant(authz, application_session, conflicting, graph)
    expected_grant = expected(
        course_ids={my_course}, section_ids={node_id(rows, my_chain, "section")}
    )

    assert from_my_own == expected_grant, (
        f"My own assignment resolved to {from_my_own} rather than {expected_grant}. A second "
        "assignment row elsewhere changed the answer, so the resolver is reading "
        "`role_assignment` for a lead's courses. `RoleAssignment`'s docstring settles the other "
        "reading: the mapping decides which courses a lead holds, and the assignment table is "
        "read only for the edges."
    )
    assert from_the_conflicting_row == expected_grant, (
        f"The conflicting assignment row resolved to {from_the_conflicting_row}, which hands me a "
        "course the mapping gives to another lead. SPEC §4.1 invariant 2: 'A Lead Faculty "
        "assignment never grants sibling leads' courses, at any point in the purview union "
        "computation.' The row was accepted by the schema — E0-09 measured that and left it — so "
        "the resolver is the only thing standing between it and a sibling's sections."
    )


@pytest.mark.invariant
def test_two_leads_with_courses_under_one_prefix_resolve_to_disjoint_purviews(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """SPEC §4.1 invariant 2, at the level E0-11 can already break it.

    "A Lead Faculty assignment never grants sibling leads' courses, at any point
    in the purview union computation." The union is E9's; the own grant is here,
    and if two leads under one prefix already overlap, no union can separate them
    later.

    Disjointness is asserted at **every** level and not only at `course_ids`,
    because the leak does not have to arrive as a course. A resolver that put the
    shared prefix in `prefix_ids` has given each lead a node whose subtree is the
    other's courses, and the next reader — a tree renderer, a benchmark
    comparison set, E9's union — is entitled to expand it. §2.1 is explicit about
    what a lead may see: "Lead Faculty get the **hierarchy view only** — never a
    by-lead-faculty pivot (they must not see peers' courses)."

    Both purviews are asserted non-empty first: two empty sets are disjoint, and a
    resolver that returns nothing at all would otherwise pass this
    (`docs/MISTAKES.md` entry 3).
    """
    rows = committed_rows
    graph = rows.graph
    mine = graph.person()
    theirs = graph.person()
    my_chain = subtree(rows, "institution", "college", "department")
    their_chain = sibling_course(rows, my_chain)
    my_course = node_id(rows, my_chain, "course")
    their_course = node_id(rows, their_chain, "course")

    written(graph, lambda: graph.lead_mapping(person=mine, course=my_course), "My mapping")
    written(
        graph,
        lambda: graph.lead_mapping(person=theirs, course=their_course),
        "The sibling lead's mapping",
    )
    my_assignment = written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", scope=my_course, person=mine),
        "My lead-faculty assignment",
    )
    their_assignment = written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", scope=their_course, person=theirs),
        "The sibling lead's assignment",
    )
    rows.commit()

    ours = grant(authz, application_session, my_assignment, graph)
    yours = grant(authz, application_session, their_assignment, graph)

    assert any(ours.values()) and any(yours.values()), (
        f"One of the two leads resolved to an empty purview — mine {ours}, theirs {yours}. Two "
        "empty sets are disjoint, so the assertion below would pass against a resolver that "
        "returns nothing for anybody."
    )

    shared = {
        level: sorted(ours[level] & yours[level]) for level in ours if ours[level] & yours[level]
    }
    assert not shared, (
        f"Two lead faculty members under one prefix share {shared}. SPEC §4.1 invariant 2: 'A "
        "Lead Faculty assignment never grants sibling leads' courses, at any point in the purview "
        "union computation.' A shared prefix or department is the same failure one level up — "
        "whatever expands that node holds the other lead's courses — and §2.1 gives leads the "
        "hierarchy view precisely so that a peer's courses have nowhere to appear."
    )


# ---------------------------------------------------------------------------
# The assistant dean, whose own grant is empty. See the module docstring for why
# that is the spec's answer rather than a gap in this file.
# ---------------------------------------------------------------------------


def test_an_assistant_deans_own_grant_is_empty_at_every_level(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """§2's table: the assistant dean sits on the dean's node and draws no authority from it.

    "College (same node as the dean — **authority comes from the supervision
    graph, not the scope**)." The scope column on this row says where the person
    works, not what they may read, and §2.1's own-grant sentence — which spells
    out what a lead, a chair and a dean each hold — does not give this role a
    grain at all. What it says instead is that the assistant dean's purview is
    "own led courses union every supervised chair's department", and neither half
    of that is reachable from this assignment: the courses belong to the person's
    separate `LEAD_FACULTY` assignment, and the departments come from E9's
    transitive walk.

    **The control is a `DEAN` assignment on the same college**, resolved on the
    same session against the same rows. The two differ in one column — the role —
    so an `own_grant` mutated to return an empty purview for everything passes the
    assertion below and fails the control (`docs/MISTAKES.md` entry 3). Without
    it, "the assistant dean sees nothing" is equally true of a resolver that sees
    nothing for anybody, which over a `pulse_app` connection is what a missing
    grant looks like.

    **The mutation it exists to survive** is the state E0-11's security review
    measured: the whole college subtree returned for this role because the
    resolver coalesced over the scope columns and found `college_id` populated.
    Nothing about that reads as wrong — the row genuinely is scoped to the college
    — and it hands one assistant dean every department in it, supervised or not.
    """
    rows = committed_rows
    graph = rows.graph
    college = graph.scope("college")
    under_the_college = subtree(rows, "institution", "college")
    assistant = written(
        graph,
        lambda: graph.assign("ASSISTANT_DEAN", scope=college),
        "An assistant dean assignment on the college",
    )
    dean = written(
        graph, lambda: graph.assign("DEAN", scope=college), "A dean assignment on the same college"
    )
    rows.commit()

    deans = grant(authz, application_session, dean, graph)
    theirs = grant(authz, application_session, assistant, graph)

    assert any(deans.values()), (
        f"The dean on the same college resolved to {deans}, so `own_grant` answers nothing for "
        "anybody on this session and the assertion below would be satisfied by a resolver with no "
        "answers at all (`docs/MISTAKES.md` entry 3). "
        "`test_a_deans_own_grant_is_its_college_and_everything_under_it` is where that is "
        "diagnosed."
    )
    assert theirs == expected(), (
        f"An `ASSISTANT_DEAN` assignment resolved to {theirs} rather than to an empty purview. The "
        f"dean on the same college node resolved to {deans}, which is what that node grants — so "
        "anything here was taken from the containment hierarchy, and SPEC §2's table says in "
        "parentheses that it must not be: 'same node as the dean — authority comes from the "
        "supervision graph, not the scope'. The department seeded under that college is "
        f"{node_id(rows, under_the_college, 'department')}; nobody has said this assistant dean "
        "supervises its chair, and under §2.1 its sections are in their purview only if a "
        "reporting line puts them there."
    )


def test_an_assistant_deans_own_grant_stays_empty_when_a_chair_reports_to_it(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """The supervised department is E9's to supply, and it is still not the own grant.

    **Read this before "fixing" it.** The natural objection to the test above is
    that it proves nothing, because no chair reported to that assistant dean —
    surely the supervised department is exactly what the own grant is for. It is
    not. SPEC §2.1 defines `Purview(assignment) = own grant union the purviews of
    all assignments transitively reporting to it`, so a supervised chair's
    department enters through the **second** term, by the walk over reporting
    lines that E9 implements and that raises here (ADR 0003,
    `tests/unit/test_deferred_authz_seams_fail_closed.py`). Adding it to the own
    grant would compute the right answer for this shape by the wrong route, and
    the route is the whole of what §2.1 argues: "a set no single containment node
    holds".

    The rows are E0-09's `assistant_dean_shape`, which that ticket built as "a
    fixture builder for the assistant-dean shape that E9 will reuse" — a dean, an
    assistant dean on the same college, two chairs reporting to the assistant
    dean, and a third chair reporting straight to the dean whose department holds
    the course the assistant dean leads.

    **The control is one of the supervised chairs**, whose own grant has to be
    non-empty: it is the department this assistant dean will eventually see
    *through that chair*, and if it resolves to nothing then the emptiness below
    is a resolver that answers nothing rather than a grain rule.
    """
    rows = committed_rows
    graph = rows.graph
    shape = written(
        graph, lambda: graph.assistant_dean_shape(), "SPEC §2.1's assistant-dean worked example"
    )
    rows.commit()

    chairs = grant(authz, application_session, shape["supervised_chairs"][0], graph)
    theirs = grant(authz, application_session, shape["assistant_dean"], graph)

    assert any(chairs.values()), (
        f"A chair reporting to the assistant dean resolved to {chairs}, so `own_grant` answers "
        "nothing on this session and the emptiness asserted below means nothing "
        "(`docs/MISTAKES.md` entry 3). "
        "`test_a_chairs_own_grant_is_its_department_and_everything_under_it` diagnoses that."
    )
    assert theirs == expected(), (
        f"An `ASSISTANT_DEAN` assignment with two chairs reporting to it resolved to {theirs}. "
        f"Their supervised departments are {shape['supervised_departments']} and the department "
        f"nobody put under them is {shape['unsupervised_department']} — both sit in the college "
        "this assignment is scoped to, which is why reading the scope column hands over the "
        "second one along with the first. SPEC §2.1 computes the supervised half from the "
        "reporting lines: 'own grant union the purviews of all assignments transitively reporting "
        "to it'. That union is E9's and raises here, so an assistant dean sees nothing in E0 — "
        "which is what ADR 0003 says about leadership landing views in this epic, and is a "
        "deliberate outcome rather than a missing feature."
    )


def test_a_person_with_an_assistant_dean_and_a_lead_assignment_resolves_to_their_led_course(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """§2.1's "own led courses", which come from the lead assignment and not from the other one.

    SPEC §2: "People are not roles… every view is resolved from an assignment (or
    a union of them), never from a person 'type'", and the sentence naming this
    exact combination is in the same paragraph: "an assistant dean can hold a
    lead-faculty assignment while supervising a chair". So the person resolves to
    the courses their `LEAD_FACULTY` assignment gives them, and the
    `ASSISTANT_DEAN` assignment beside it adds nothing at all.

    **Nothing reports to either assignment here, deliberately.** The person in
    `test_an_assistant_deans_own_grant_stays_empty_when_a_chair_reports_to_it`
    has supervised chairs, and a resolver that reached for §2.1's second term
    would raise on them; this test is about which of the person's two assignments
    the grant comes from, so the shape is built with no reporting lines and the
    deferred union has nothing to be asked about.

    **The control is inside the expectation.** The led course is not asserted
    absent from something — it is asserted present, exactly, with every other
    level empty, so a resolver that returned nothing fails this as loudly as one
    that returned the college. The course sits in its own department under the
    same college as the assistant dean assignment, which is the arrangement §2.1
    describes and the one where a scope-column read looks right: it would return
    this course too, along with every other course in the college.
    """
    rows = committed_rows
    graph = rows.graph
    person = graph.person()
    college = graph.scope("college")
    led = subtree(rows, "institution", "college")
    led_course = node_id(rows, led, "course")

    written(
        graph,
        lambda: graph.lead_mapping(person=person, course=led_course),
        "The mapping naming the course this person leads",
    )
    written(
        graph,
        lambda: graph.assign("ASSISTANT_DEAN", scope=college, person=person),
        "Their assistant dean assignment, on the college",
    )
    written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", scope=led_course, person=person),
        "Their lead-faculty assignment, on the course they lead",
    )
    rows.commit()

    scope = authz.resolve_scope(application_session, person_id=person)
    held = levels(scope.purview)

    assert held == expected(course_ids={led_course}, section_ids={node_id(rows, led, "section")}), (
        f"A person holding an `ASSISTANT_DEAN` assignment and a `LEAD_FACULTY` assignment "
        f"resolved to {held}, and the course the mapping gives them is {led_course}. SPEC §2.1 "
        "gives this person 'own led courses union every supervised chair's department' — they "
        "supervise nobody here, so the first term is the whole answer. A `college_ids` or a "
        "`department_ids` came from the assistant dean assignment's scope node, which §2's table "
        "says is not where its authority comes from; an empty purview means the lead assignment "
        "stopped granting its courses when a second assignment appeared beside it."
    )
