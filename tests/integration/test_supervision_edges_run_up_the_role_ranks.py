"""A supervision edge only ever points at a role above it — ticket E0-11.

E0-11's first acceptance criterion, and the first of the two rules E0-09 left
measured and unenforced: "**A `LEAD_FACULTY → LEAD_FACULTY` edge and a
role-inverted edge such as `CHAIR ← VP_ACADEMICS` are refused**, or the resolver
ignores them and an ADR says why that is the right place."

**The rule lives in the database**, in a migration that extends E0-09's
`role_assignment` trigger with a role-rank check, so it holds for E0-17's seed
script, E9's CSV import and any future admin path as well as for the resolver —
the same argument [ADR 0027](../../docs/adr/0027-supervision-edges-are-policed-by-one-row-level-trigger.md)
makes for the three rules already there. This module is therefore about what the
server stores, not about what a service returns.

**Why the rank is a property of the two assignments and never of the person
holding them.** SPEC §2.1 attaches the edge to the assignment — "`reportsTo`
edges connect **role assignments, not people or org nodes**" — and calls
two-hat people ordinary: "a chair's lead-faculty assignment may report to their
own chair assignment — legal and expected". A rank rule written over the person
passes every refusal below and makes the commonest arrangement in the institution
unwritable, which is the same trap ADR 0027 records for the cycle walk: "a guard
written over `person_id` passes every cycle test in the suite". The three
person-shaped tests near the end are what hold that line, and they are the reason
this module is not only the matrix.

**What the two refused shapes cost, in §2.1's own terms.** Purview is "own grant
∪ purviews of all assignments transitively reporting to it". A
`LEAD_FACULTY → LEAD_FACULTY` edge therefore puts one lead's courses inside a
sibling lead's purview, which is §4.1 invariant 2 — the invariant §2.1 restates
as "never sibling leads' courses, **at any point in the union**". A
`VP_ACADEMICS → CHAIR` edge puts the whole institution inside that chair's
purview. Neither row is wrong on its face and neither errors; both were accepted
against the shipped migration when E0-09 measured them.

**Care is not tested here.** E0-09 already refuses a `CARE` assignment an edge in
both directions, by a check constraint and by the trigger, and
`tests/integration/test_role_assignment_graph.py` asserts both. Repeating it here
would give two failures for one defect.

**Nor is `LEAD_FACULTY → CHAIR` for one person**, for the same reason: it is
`test_a_person_may_hold_two_assignments_where_one_reports_to_the_other` in that
module, and a rank rule that reads people rather than roles turns it red. That is
the test to look at first if this ticket's migration breaks a two-hat write.
"""

from typing import Any

import pytest

pytestmark = pytest.mark.integration

# SPEC §2.1's canonical chain read as an order: `INSTRUCTOR(section) →
# LEAD_FACULTY(course) → CHAIR(department) → DEAN(college) → VP_ACADEMICS`, with
# the assistant dean inserted between chair and dean by the same paragraph —
# "some chairs in a college report through an assistant dean while others report
# straight to the dean".
#
# **Deliberately written out rather than derived** (`docs/MISTAKES.md` entry 19).
# The order is a sentence in the spec, and the only other copy of it will be
# inside the guard under test; a test that read the ranks back out of the trigger
# would be checking the rule against itself, and both could be renumbered
# together with this file green.
ROLE_RANK = {
    "INSTRUCTOR": 1,
    "LEAD_FACULTY": 2,
    "CHAIR": 3,
    "ASSISTANT_DEAN": 4,
    "DEAN": 5,
    "VP_ACADEMICS": 6,
}

# Every ordered pair of ranked roles, split by the rule. `ADMIN` is in neither
# list: it holds no rank at all, and the pair of tests below assert that an edge
# touching one is refused from either end — fail closed, the shape ADR 0025's
# `ELSE false` gives the scope grain rule.
LEGAL_EDGES = [
    (child, parent)
    for child in ROLE_RANK
    for parent in ROLE_RANK
    if ROLE_RANK[child] < ROLE_RANK[parent]
]
REFUSED_EDGES = [
    (child, parent)
    for child in ROLE_RANK
    for parent in ROLE_RANK
    if ROLE_RANK[child] >= ROLE_RANK[parent]
]

ADMIN_ROLE = "ADMIN"


def written(graph: Any, action: Any, what: str) -> Any:
    """Perform a write that has to succeed, and fail naming it when it does not.

    A copy of the helper in `tests/integration/test_role_assignment_graph.py`,
    marked as one for the reason that module's docstring gives: a test module
    importing the conftest module by name works only because of where pytest puts
    `tests/` on `sys.path`, and a collection error is not a failing test.

    Every "and then this is refused" assertion here is preceded by rows that must
    go in first. Writing them bare would end the test in a `DatabaseError` from
    inside its own setup — a broken test rather than a red one, reported as though
    the assertion had run.
    """
    holder: dict[str, Any] = {}

    def perform() -> None:
        holder["row"] = action()

    refused = graph.refusal(perform)
    assert refused is None, (
        f"{what} was refused: {refused}. It is a control rather than the subject: nothing after "
        "it in this test can mean anything, because a refusal that arrives before the row under "
        "test makes every later assertion pass for the wrong reason (`docs/MISTAKES.md` entry 3)."
    )
    return holder.get("row")


@pytest.mark.parametrize(("child", "parent"), LEGAL_EDGES, ids=lambda role: role.lower())
def test_an_edge_from_a_role_to_one_that_outranks_it_is_accepted(
    supervision_graph: Any, child: str, parent: str
) -> None:
    """Every reporting line SPEC §2.1's chain and its insertions can produce.

    Fifteen pairs, and they are the control for the twenty-one refusals below: the
    cheapest way to pass a refusal test is a rule that refuses more than it should,
    and a supervision graph that will not take an edge is a purview computation
    with nothing to union. §2.1 requires the insertions specifically — "with
    insertions supported without schema change" — so `CHAIR → DEAN` and
    `CHAIR → ASSISTANT_DEAN` have to be equally legal, and so does the skip from
    an instructor straight to a chair for a course with no lead ("a course with no
    mapping falls to its department chair").

    Each assignment is built with its own person and its own scope node, so no
    uniqueness rule from an earlier ticket can refuse a row and be read as this
    one firing.
    """
    graph = supervision_graph
    key = graph.assignment_key

    above = written(graph, lambda: graph.node(parent), f"A {parent} assignment")
    refused = graph.refusal(lambda: graph.node(child, reports_to=above[key]))

    assert refused is None, (
        f"A {child} assignment was refused an edge to a {parent} assignment: {refused}. SPEC "
        "§2.1's canonical chain is `INSTRUCTOR(section) → LEAD_FACULTY(course) → "
        "CHAIR(department) → DEAN(college) → VP_ACADEMICS`, with insertions supported without "
        f"schema change, and {ROLE_RANK[child]} < {ROLE_RANK[parent]} in that order. A rank rule "
        "that refuses this makes a real reporting line unwritable — and the symptom is not an "
        "error anybody sees later, it is a purview that is missing a branch."
    )


@pytest.mark.parametrize(("child", "parent"), REFUSED_EDGES, ids=lambda role: role.lower())
def test_an_edge_to_a_role_that_does_not_outrank_the_child_is_refused(
    supervision_graph: Any, child: str, parent: str
) -> None:
    """The rule itself: an edge is accepted only where `rank(child) < rank(parent)`.

    Twenty-one pairs, and they include the two the ticket names —
    `LEAD_FACULTY → LEAD_FACULTY`, which is §4.1 invariant 2 written as a row, and
    the inversion `VP_ACADEMICS → CHAIR`, which hands a chair the institution — as
    well as every equal-rank pair and every other inversion. E0-09 measured both
    of the named ones accepted against the shipped migration.

    **The control is the same parent taking a legal edge**, written first, in the
    same transaction. Without it a refusal here could equally be a parent that
    cannot take an edge at all, or an insert path that does not work, and the
    twenty-one cases would agree with each other for a reason none of them is
    about (`docs/MISTAKES.md` entry 3).
    """
    graph = supervision_graph
    key = graph.assignment_key

    above = written(graph, lambda: graph.node(parent), f"A {parent} assignment")
    below_rank = min(ROLE_RANK, key=lambda role: ROLE_RANK[role])
    if ROLE_RANK[parent] > ROLE_RANK[below_rank]:
        written(
            graph,
            lambda: graph.node(below_rank, reports_to=above[key]),
            f"A {below_rank} assignment reporting to that {parent}",
        )

    refused = graph.refusal(lambda: graph.node(child, reports_to=above[key]))
    assert refused is not None, (
        f"A {child} assignment was stored reporting to a {parent} assignment, and "
        f"{ROLE_RANK[child]} is not below {ROLE_RANK[parent]} in SPEC §2.1's chain. Purview is "
        "'own grant ∪ purviews of all assignments transitively reporting to it', so this edge "
        f"puts everything the {child} holds inside the {parent}'s purview. Neither row is wrong "
        "on its face and nothing errors: an equal-rank edge hands one lead a sibling lead's "
        "courses (§4.1 invariant 2, 'at any point in the purview union computation'), and an "
        "inverted one hands the lower role everything above it."
    )


# ---------------------------------------------------------------------------
# The rank belongs to the assignment. Three shapes where reading the person
# instead gives a different answer, and every one of them is ordinary.
# ---------------------------------------------------------------------------


def test_an_instructor_who_also_leads_other_courses_may_still_report_to_another_lead(
    supervision_graph: Any,
) -> None:
    """A lead faculty member teaching a section in somebody else's course.

    §2.1 makes this ordinary twice over: "~95% adjuncts" teach sections, "a lead's
    practical span may cross prefixes and departments", and a person holds "one or
    more role assignments" with the views resolved from the assignment and "never
    from a person 'type'". So the person here holds a `LEAD_FACULTY` assignment on
    their own courses and an `INSTRUCTOR` assignment on a section of somebody
    else's, and the second reports to that other lead.

    A rank rule that ranks the **person** reads this as `LEAD_FACULTY →
    LEAD_FACULTY` — equal rank, refused — and every case in the matrix above
    stays green while it does, because each of those builds its assignments with
    a person of its own. The failure is not subtle when it lands: the roster sync
    cannot write the teaching assignment for any lead who also teaches, which is
    most of them.
    """
    graph = supervision_graph
    key = graph.assignment_key
    two_hatted = graph.person()

    written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", scope=graph.fresh_scope("course"), person=two_hatted),
        "The teaching person's own lead-faculty assignment on another course",
    )
    other_lead = written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", scope=graph.fresh_scope("course")),
        "Another person's lead-faculty assignment",
    )

    refused = graph.refusal(
        lambda: graph.assign(
            "INSTRUCTOR",
            scope=graph.scope("section"),
            person=two_hatted,
            reports_to=other_lead[key],
        )
    )
    assert refused is None, (
        f"A teaching assignment was refused an edge to the course's lead: {refused}. The two "
        "assignments are INSTRUCTOR and LEAD_FACULTY, which is the first link of SPEC §2.1's "
        "canonical chain; what is unusual about the row is only that the same person leads other "
        "courses. §2.1: 'People are not roles… every view is resolved from an assignment (or a "
        "union of them), never from a person type.' A rule that ranks the person instead of the "
        "assignment refuses this and passes every other refusal in this module."
    )


def test_an_instructor_who_also_holds_the_vp_assignment_may_still_report_to_a_lead(
    supervision_graph: Any,
) -> None:
    """The same trap at the other end of the ladder, where it inverts instead of tying.

    §2 is explicit that any combination is legal — "A chair can also lead courses;
    an assistant dean can hold a lead-faculty assignment while supervising a
    chair" — and nothing bounds it at the top. A person-ranked rule computes
    `rank(VP_ACADEMICS)=6 > rank(LEAD_FACULTY)=2` and refuses this as an
    inversion, which is the same defect as the test above wearing the other
    failure's clothes: there it is an equal-rank refusal, here an inverted one, and
    a fix for one does not fix the other.
    """
    graph = supervision_graph
    key = graph.assignment_key
    two_hatted = graph.person()

    written(
        graph,
        lambda: graph.assign("VP_ACADEMICS", person=two_hatted),
        "The teaching person's VP of Academics assignment",
    )
    lead = written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", scope=graph.scope("course")),
        "The course's lead-faculty assignment",
    )

    refused = graph.refusal(
        lambda: graph.assign(
            "INSTRUCTOR",
            scope=graph.scope("section"),
            person=two_hatted,
            reports_to=lead[key],
        )
    )
    assert refused is None, (
        f"A teaching assignment was refused an edge to its lead because the same person holds a "
        f"VP assignment elsewhere: {refused}. SPEC §2: 'A chair can also lead courses; an "
        "assistant dean can hold a lead-faculty assignment while supervising a chair.' The rank "
        "under test is a property of the two assignments an edge joins, and the person holding "
        "them is not one of its inputs."
    )


def test_a_chair_may_report_through_an_assistant_dean_or_straight_to_the_dean(
    supervision_graph: Any,
) -> None:
    """§2.1's insertion case, as one graph rather than as two pairs.

    "Some chairs in a college report through an assistant dean
    (`CHAIR → ASSISTANT_DEAN → DEAN`) while others report straight to the dean."
    The matrix above accepts each of those edges on its own; this is the shape
    they make together, and it is the worked example §2.1 gives for why purview
    comes from the graph rather than from containment — the assistant dean's
    purview is "own led courses ∪ every supervised chair's department, a set no
    single containment node holds".

    The edges are read back rather than trusted, because an edge silently dropped
    looks identical to an edge accepted, and a rank rule implemented as a `BEFORE`
    trigger that returns `NEW` with a cleared column would do exactly that.
    """
    graph = supervision_graph
    key = graph.assignment_key

    dean = written(graph, lambda: graph.node("DEAN"), "A dean assignment")
    assistant = written(
        graph,
        lambda: graph.node("ASSISTANT_DEAN", reports_to=dean[key]),
        "An assistant dean reporting to that dean",
    )
    through = written(
        graph,
        lambda: graph.node("CHAIR", reports_to=assistant[key]),
        "A chair reporting through that assistant dean",
    )
    directly = written(
        graph,
        lambda: graph.node("CHAIR", reports_to=dean[key]),
        "A second chair reporting straight to the dean",
    )

    assert graph.ancestors(through[key]) == [assistant[key], dean[key]], (
        f"The chair that reports through the assistant dean has ancestors "
        f"{graph.ancestors(through[key])} rather than the assistant dean and then the dean. Every "
        "edge was accepted, so an edge that is not there was dropped rather than refused — and "
        "SPEC §2.1's purview union walks exactly this path."
    )
    assert graph.ancestors(directly[key]) == [dean[key]], (
        f"The chair that reports straight to the dean has ancestors "
        f"{graph.ancestors(directly[key])} rather than the dean alone. §2.1 requires both "
        "arrangements in one college, 'with insertions supported without schema change'."
    )


# ---------------------------------------------------------------------------
# Admin has no rank, so it has no edge — in either direction, fail closed.
# ---------------------------------------------------------------------------


def test_an_admin_assignment_may_be_written_without_an_edge(supervision_graph: Any) -> None:
    """The control for the two tests below: the role itself stays writable.

    §2's table gives Admin the observability console, LTI registration, org and
    people management and configuration, scoped to the institution — it is a real
    assignment that E0-17's seed script and §6.3's People editor both write. A
    rank rule that made the role unwritable would satisfy both refusals below and
    lock every administrator out of the product.
    """
    graph = supervision_graph
    written(graph, lambda: graph.assign(ADMIN_ROLE), "An Admin assignment with no edge")


@pytest.mark.parametrize("end", ["child", "parent"])
def test_an_edge_touching_an_admin_assignment_is_refused(supervision_graph: Any, end: str) -> None:
    """Admin holds no rank, and an unranked role is refused rather than defaulted.

    §2.1's supervision graph is a chain of reporting roles and Admin is not one of
    them: §2's table gives it a console rather than a scope over other people's
    data, and nothing in the spec says who an administrator answers to or who
    answers to them. The direction of the failure is what this asserts. An edge
    *into* an Admin assignment gives it a transitive purview — "own grant ∪
    purviews of all assignments transitively reporting to it" — which turns the
    role that manages the org chart into a role that reads everybody's reports,
    and it is one row in the People editor away. An edge *out of* one puts the
    administrator's own grant, whatever a later ticket decides that is, inside
    somebody else's.

    Fail closed is the same choice ADR 0025 records for the scope grain rule,
    whose `CASE` ends in `ELSE false` so that "a role added to the enum without a
    grain cannot be written down at all". A rank rule that treated an unranked
    role as rank zero would accept every edge out of it, silently.
    """
    graph = supervision_graph
    key = graph.assignment_key

    administrator = written(graph, lambda: graph.assign(ADMIN_ROLE), "An Admin assignment")
    chair = written(graph, lambda: graph.node("CHAIR"), "A chair assignment")
    written(
        graph,
        lambda: graph.node("LEAD_FACULTY", reports_to=chair[key]),
        "A lead reporting to that chair, on the same parent the Admin edge is tried against",
    )

    if end == "child":
        refused = graph.refusal(
            lambda: graph.assign(ADMIN_ROLE, reports_to=chair[key], person=graph.person())
        )
    else:
        refused = graph.refusal(lambda: graph.node("CHAIR", reports_to=administrator[key]))

    assert refused is not None, (
        f"An edge with an Admin assignment as the {end} was stored. Admin holds no rank in SPEC "
        "§2.1's chain — the chain is `INSTRUCTOR → LEAD_FACULTY → CHAIR → DEAN → VP_ACADEMICS` "
        "and §2's table gives Admin a console rather than a place in it — so there is no ordering "
        "against which this edge could be checked, and the fail-closed answer is the only one "
        "that does not invent a purview. The same row was accepted with no edge one statement "
        "earlier, so this is about the edge and not about the role."
    )


# ---------------------------------------------------------------------------
# The `UPDATE` path, which is how a reporting line actually changes.
# ---------------------------------------------------------------------------


def test_re_pointing_a_lead_at_a_sibling_lead_is_refused_on_update(
    supervision_graph: Any,
) -> None:
    """The same rule on the statement §6.3's People editor runs.

    E0-09's trigger is `AFTER INSERT OR UPDATE`, and an edge written by moving an
    existing `reports_to` reaches the same stored state as an edge written by
    inserting a row. A guard added to the insert path alone leaves the row a
    single `UPDATE` away — and re-pointing is the *ordinary* way a reporting line
    changes: an administrator edits somebody's supervisor in the People editor,
    which is one statement over a row that already exists.

    The end state is §4.1 invariant 2: a lead whose assignment reports to another
    lead is inside that lead's purview union, so a sibling's courses appear in a
    hierarchy view that §2.1 says may never show them ("Lead Faculty get the
    hierarchy view only — never a by-lead-faculty pivot; they must not see peers'
    courses").

    **The control is the same row re-pointed at a legal parent**, so that a
    refusal is known to be about the new parent rather than about the `UPDATE`
    being refused at all.
    """
    graph = supervision_graph
    key = graph.assignment_key

    chair = written(graph, lambda: graph.node("CHAIR"), "A chair assignment")
    lead = written(
        graph,
        lambda: graph.node("LEAD_FACULTY", reports_to=chair[key]),
        "A lead reporting to that chair",
    )
    sibling = written(graph, lambda: graph.node("LEAD_FACULTY"), "A sibling lead's assignment")
    written(
        graph,
        lambda: graph.repoint(lead, chair[key]),
        "Re-pointing that lead at the same chair it already reports to",
    )

    refused = graph.refusal(lambda: graph.repoint(lead, sibling[key]))
    assert refused is not None, (
        "A lead-faculty assignment was re-pointed at a sibling lead's assignment and the edge was "
        "stored. E0-09's trigger fires `AFTER INSERT OR UPDATE`, and the rank rule has to answer "
        "on both: this is the statement §6.3's People editor issues, and the state it reaches is "
        "the one SPEC §4.1 invariant 2 forbids — 'a Lead Faculty assignment never grants sibling "
        "leads' courses, at any point in the purview union computation'. The same row was "
        "accepted re-pointed at its own chair one statement earlier."
    )
