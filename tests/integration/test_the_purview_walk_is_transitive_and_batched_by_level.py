"""The walk is transitive, reaches six levels, and batches by level — E9-01, done-when 2 and 13.

> 2. In a generated chain `LEAD → CHAIR → ASSISTANT_DEAN → DEAN → VP`, each
>    assignment's purview contains every purview below it. A test with a chain of
>    six assignments reaches the bottom. The number of queries grows with the
>    depth and not with the number of assignments: a forest ten assignments wide
>    and one a single assignment wide, both of the same depth, issue the same
>    number of queries (counted).
> 13. `transitive_purview` no longer raises.

**Each link of the chain sits in its own college**, so containment cannot supply
what the walk is supposed to: the lead's course, the chair's department and the
dean's college are three disjoint subtrees, and a dean's purview holds the first
two only by walking down through the assistant dean. The VP at the top is scoped
to the one institution a deployment holds (SPEC §8), so containment does give
the VP everything; the chain is asserted at the VP as containment and nothing
more, and the discriminating assertions are made at the dean and the assistant
dean.

**Why the six-assignment chain is honest about its bottom.** SPEC §2.1 makes the
graph at most six assignments deep, and the only six-deep chain is
`INSTRUCTOR → LEAD → CHAIR → ASSISTANT_DEAN → DEAN → VP`. The lead clamp means an
instructor under a lead contributes nothing above the lead that the lead's own
grant does not hold, so the instructor here teaches a section of the lead's own
course: "reaching the bottom" is then the claim that the walk visits all six
levels and answers at every one of them, and that the section at the bottom is
in the dean's purview — which it is only through three edges.

**The chain and the clamp tests run over `application_session`**, the `pulse_app`
connection production serves requests over, on rows `committed_rows` commits
(`docs/MISTAKES.md` entry 46). The query count runs on `supervision_graph`'s
session, because it counts statements rather than asking a grant anything.

**Which failure a red is, before E9-01 lands.** `transitive_purview` raises
`NotImplementedError`, so every test here except the recorder control fails on
that exception. `test_the_statement_recorder_sees_the_statements_of_a_read` is a
control on the counting machinery: a red there means this module is broken, not
the walk.
"""

from typing import Any

import pytest
from fixtures.purview_walk import PURVIEW_LEVELS, covers, difference, joined, levels, written
from fixtures.statements import statements_recorded

pytestmark = pytest.mark.integration

# The two forest widths done-when 2 names.
WIDE = 10
NARROW = 1


def fresh_subtree(rows: Any) -> dict[str, Any]:
    """A new college, department, prefix, course and section, under the one institution."""
    rows.graph.scope("section")
    chain = rows.graph.new_branch("institution", "term")
    rows.seed("section", chain)
    return chain


def node_id(rows: Any, chain: dict[str, Any], level: str) -> Any:
    return rows.graph.key_of(level, chain[level])


def subtree_levels(rows: Any, chain: dict[str, Any], top: str) -> dict[str, frozenset[Any]]:
    """The levels a one-branch chain holds from `top` down, as an expectation."""
    order = ("college", "department", "prefix", "course", "section")
    out = {name: frozenset() for name in PURVIEW_LEVELS}
    for level in order[order.index(top) :]:
        out[f"{level}_ids"] = frozenset({node_id(rows, chain, level)})
    return out


def a_reporting_chain(rows: Any, *, with_an_instructor: bool) -> dict[str, Any]:
    """`[INSTRUCTOR →] LEAD → CHAIR → ASSISTANT_DEAN → DEAN → VP`, each in its own college.

    The lead's course, the chair's department and the dean's college are three
    fresh subtrees. The instructor, when asked for, teaches the section of the
    lead's own course. Committed on the way out.
    """
    graph = rows.graph
    key = graph.assignment_key
    led = fresh_subtree(rows)
    chaired = fresh_subtree(rows)
    deaned = fresh_subtree(rows)
    lead_person = graph.person()
    led_course = node_id(rows, led, "course")

    written(
        graph,
        lambda: graph.lead_mapping(person=lead_person, course=led_course),
        "The mapping of the led course",
    )
    vp = written(
        graph,
        lambda: graph.assign("VP_ACADEMICS", scope=graph.scope("institution"), reports_to=None),
        "The VP of Academics",
    )
    dean = written(
        graph,
        lambda: graph.assign("DEAN", scope=node_id(rows, deaned, "college"), reports_to=vp[key]),
        "The dean, on a college of their own",
    )
    assistant = written(
        graph,
        lambda: graph.assign(
            "ASSISTANT_DEAN", scope=node_id(rows, deaned, "college"), reports_to=dean[key]
        ),
        "The assistant dean, on the dean's college",
    )
    chair = written(
        graph,
        lambda: graph.assign(
            "CHAIR", scope=node_id(rows, chaired, "department"), reports_to=assistant[key]
        ),
        "The chair, on a department in another college",
    )
    lead = written(
        graph,
        lambda: graph.assign(
            "LEAD_FACULTY", scope=led_course, person=lead_person, reports_to=chair[key]
        ),
        "The lead, on a course in a third college",
    )
    chain = [lead, chair, assistant, dean, vp]
    names = ["LEAD_FACULTY", "CHAIR", "ASSISTANT_DEAN", "DEAN", "VP_ACADEMICS"]
    if with_an_instructor:
        instructor = written(
            graph,
            lambda: graph.assign(
                "INSTRUCTOR", scope=node_id(rows, led, "section"), reports_to=lead[key]
            ),
            "The instructor, on the section of the lead's own course",
        )
        chain.insert(0, instructor)
        names.insert(0, "INSTRUCTOR")
    rows.commit()
    return {
        "assignments": [row[key] for row in chain],
        "names": names,
        "led": led,
        "chaired": chaired,
        "deaned": deaned,
    }


def test_transitive_purview_answers_a_purview_where_it_used_to_raise(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """Done-when 13, asserted as the new behaviour rather than as an old raise removed.

    A chair with nothing reporting to it: the walk answers a `Purview`, and it is
    the chair's own grant, compared whole against `own_grant` on the same
    session. (`tests/unit/test_deferred_authz_seams_fail_closed.py` asserted the
    raise until E9-01 and is rewritten by it, in its own commit.)

    **The mutations this kills:** the `NotImplementedError` left in place; a walk
    that returns something other than a `Purview` (a set, a list of grants); a
    walk that loses the starting assignment's own grant.
    """
    rows = committed_rows
    graph = rows.graph
    department = fresh_subtree(rows)
    chair = written(
        graph,
        lambda: graph.assign("CHAIR", scope=node_id(rows, department, "department")),
        "A chair with nothing reporting to it",
    )
    rows.commit()

    key = graph.assignment_key
    answered = authz.transitive_purview(application_session, assignment_id=chair[key])
    own = levels(authz.own_grant(application_session, assignment_id=chair[key]))

    assert isinstance(answered, authz.Purview), (
        f"`transitive_purview` answered {answered!r}, which is not a `Purview`. SPEC §2.1 defines "
        "the purview as a union of purviews, and every caller in E9 unions and compares it."
    )
    assert any(own.values()), "The chair's own grant is empty, so the comparison below is vacuous."
    assert levels(answered) == own, (
        f"A chair with nothing below it walked to {levels(answered)}; its own grant is {own}. With "
        "no reporting assignment, SPEC §2.1's union is the own grant alone."
    )


@pytest.mark.invariant
def test_each_assignment_in_a_five_link_chain_holds_every_purview_below_it(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """Done-when 2's first sentence, with each link in its own college.

    `LEAD → CHAIR → ASSISTANT_DEAN → DEAN → VP`. Every assignment's purview holds
    every purview below it, at every level. **The assistant dean's purview is also
    compared exactly**: its own grant is empty (ADR 0046), so it is precisely the
    chair's department subtree plus the lead's course and section — §2.1's
    worked example in miniature, "a set no single containment node holds".

    **The mutations this kills:** a one-level union (the dean holds the assistant
    dean's empty grant and nothing of the chair or the lead); a walk that unions
    own grants of *direct* reports only; a depth bound below four; the assistant
    dean's own grant read off its college (it would then hold the dean's college,
    and the exact comparison is red).
    """
    rows = committed_rows
    chain = a_reporting_chain(rows, with_an_instructor=False)
    walked = [
        levels(authz.transitive_purview(application_session, assignment_id=assignment))
        for assignment in chain["assignments"]
    ]
    names = chain["names"]

    assert node_id(rows, chain["led"], "course") in walked[0]["course_ids"], (
        f"The lead's purview {walked[0]} does not hold the course the mapping gives them, so every "
        "containment below is about a chain whose bottom holds nothing (docs/MISTAKES.md entry 3)."
    )

    expected_assistant = subtree_levels(rows, chain["chaired"], "department")
    expected_assistant["course_ids"] |= {node_id(rows, chain["led"], "course")}
    expected_assistant["section_ids"] |= {node_id(rows, chain["led"], "section")}
    assistant = names.index("ASSISTANT_DEAN")
    assert walked[assistant] == expected_assistant, (
        f"The assistant dean walked to {difference(walked[assistant], expected_assistant)} away "
        "from SPEC §2.1's answer: own grant (empty, ADR 0046) union the chair's department "
        "subtree union the lead's own grant."
    )

    uncovered = [
        f"{names[upper]} does not hold {names[lower]}: "
        f"{difference(walked[upper], joined(walked[upper], walked[lower]))}"
        for upper in range(len(walked))
        for lower in range(upper)
        if not covers(walked[upper], walked[lower])
    ]
    assert not uncovered, (
        f"The chain is not transitive: {uncovered}. SPEC §2.1: 'own grant union the purviews of "
        "all assignments transitively reporting to it'."
    )


@pytest.mark.invariant
def test_a_six_assignment_chain_is_walked_to_its_bottom(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """Done-when 2's second sentence: the deepest chain the schema holds, walked from every level.

    `INSTRUCTOR → LEAD → CHAIR → ASSISTANT_DEAN → DEAN → VP`, six assignments, the
    bound SPEC §2.1 states ("at most six assignments deep"). Every level answers,
    every level holds every level below it, and the section at the bottom is in
    the dean's and the VP's purviews. See the module docstring for why the
    instructor teaches the lead's own course.

    **The mutations this kills:** a depth bound of five or fewer that raises or
    stops on a six-deep chain; a walk from the top that loses the levels below
    the assistant dean.
    """
    rows = committed_rows
    chain = a_reporting_chain(rows, with_an_instructor=True)
    names = chain["names"]
    assert len(chain["assignments"]) == 6, f"The chain holds {names}, not six assignments."

    walked = [
        levels(authz.transitive_purview(application_session, assignment_id=assignment))
        for assignment in chain["assignments"]
    ]
    bottom = node_id(rows, chain["led"], "section")

    assert walked[0]["section_ids"] == frozenset(
        {bottom}
    ), f"The instructor at the bottom walked to {walked[0]}, not to the one section it teaches."
    missing_bottom = [names[i] for i in range(1, 6) if bottom not in walked[i]["section_ids"]]
    assert not missing_bottom, (
        f"The section at the bottom of a six-assignment chain is missing from {missing_bottom}. "
        "SPEC §2.1 bounds the graph at six assignments, and the walk has to reach all six."
    )
    uncovered = [
        f"{names[upper]} does not hold {names[lower]}"
        for upper in range(6)
        for lower in range(upper)
        if not covers(walked[upper], walked[lower])
    ]
    assert not uncovered, f"The six-assignment chain is not transitive: {uncovered}."


def test_the_statement_recorder_sees_the_statements_of_a_read(supervision_graph: Any) -> None:
    """The control on the counting machinery. **A red means this module is broken, not the walk.**

    The query-count assertion below compares two counts for equality, and two
    zeros are equal. So the recorder is asked first whether it sees a statement
    this test sends itself on the same session (`docs/MISTAKES.md` entry 3).
    """
    from sqlalchemy import text

    with statements_recorded() as recorded:
        supervision_graph.session.execute(text("SELECT 1"))
    assert recorded, "The statement recorder saw nothing while a SELECT was sent on this session."


def a_forest_of_width(graph: Any, width: int) -> Any:
    """A dean, an assistant dean, and `width` branches of chair, lead and two instructors.

    Every branch has the same shape — `CHAIR` under the assistant dean, a `LEAD`
    and an `INSTRUCTOR` under the chair, an `INSTRUCTOR` under the lead — so a
    forest of width ten and one of width one have the same depth and the same
    roles at every level, and differ only in how many assignments each level
    holds. Every assignment has its own person and its own scope node (`node`).
    """
    key = graph.assignment_key
    dean = graph.node("DEAN", reports_to=None)
    assistant = graph.node("ASSISTANT_DEAN", reports_to=dean[key])
    for _ in range(width):
        chair = graph.node("CHAIR", reports_to=assistant[key])
        lead = graph.node("LEAD_FACULTY", reports_to=chair[key])
        graph.node("INSTRUCTOR", reports_to=chair[key])
        graph.node("INSTRUCTOR", reports_to=lead[key])
    return dean[key]


def test_a_wide_forest_and_a_narrow_one_of_the_same_depth_issue_the_same_number_of_queries(
    authz: Any, supervision_graph: Any
) -> None:
    """Done-when 2's last sentence: the number of statements grows with depth, not with width.

    Two forests of the same depth and the same roles per level, ten branches wide
    and one branch wide, walked from their roots. The ticket: "It batches the own
    grant queries one level at a time rather than one per assignment." So the two
    walks send the same number of statements. A warm-up walk runs first, so a
    one-time statement (a cache fill, a settings read) is not counted against
    either.

    **Both counts are asserted non-zero first** — the recorder control above is
    about the recorder; this is about the walk having been measured at all.

    **The mutations this kills:** an `own_grant` call per assignment inside the
    walk (ten branches send ten times the statements); a per-child query for the
    next level. **The near miss that must stay green:** any number of statements
    per level, so long as it does not depend on the level's width.
    """
    graph = supervision_graph
    session = graph.session
    wide_root = a_forest_of_width(graph, WIDE)
    narrow_root = a_forest_of_width(graph, NARROW)

    authz.transitive_purview(session, assignment_id=narrow_root)

    with statements_recorded() as narrow:
        authz.transitive_purview(session, assignment_id=narrow_root)
    with statements_recorded() as wide:
        authz.transitive_purview(session, assignment_id=wide_root)

    assert narrow and wide, (
        f"The walk sent {len(narrow)} statements for the narrow forest and {len(wide)} for the "
        "wide one. A walk that reads nothing cannot have read the graph."
    )
    assert len(wide) == len(narrow), (
        f"A forest {WIDE} branches wide sent {len(wide)} statements and one {NARROW} branch wide "
        f"sent {len(narrow)}, at the same depth. The ticket: the walk 'batches the own grant "
        "queries one level at a time rather than one per assignment'. The wide walk sent:\n"
        + "\n".join(statement.sql[:160] for statement in wide)
    )
