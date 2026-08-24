"""Reads go through the views, scoped, and a node outside the purview is refused — E0-11.

E0-11's scope: "A `ScopedSession`-style helper or query dependency that makes the
E0-10 views the default read path and makes bypassing it visibly deliberate", and
its third criterion: "Every read helper in the module goes through the E0-10
views."

**Refusal, never absence.** Every confidentiality assertion here is that the
reader *declined*, with `OutOfPurviewError`, rather than that a result set came
back without the section in it. An empty result is satisfied by a query that
returned nothing for an unrelated reason — an unseeded fixture, a filter that
excluded everything, a view that has been dropped — and
`.claude/review-fixtures/invariant-asserts-absence.diff` is that mistake written
down as a review fixture. Each refusal here is paired with a read that has to
succeed, on the same reader, in the same test, so the refusal is known to be
about the node and not about a reader that can do nothing at all.

**Why the sibling course is the case worth testing.** SPEC §4.1 invariant 2 is
about exactly this pair — two leads under one prefix — and §2.1 says what the
product may never show: "Lead Faculty get the **hierarchy view only** — never a
by-lead-faculty pivot (they must not see peers' courses)." A reader that scopes
nothing is not a screen that looks obviously wrong; it is the same screen with
one extra row on it.

The reads run over a `pulse_app` connection, which is where E0-10's grants are
(see `test_own_grant_follows_the_role_grain.py`'s docstring). A failure here that
says "permission denied" is a missing view or a missing grant, which is half the
criterion rather than an obstacle to it.
"""

from typing import Any

import pytest

pytestmark = pytest.mark.integration

# The containment rows a second course shares with the first: everything strictly
# above a course in SPEC §2.1's hierarchy, plus the term.
ABOVE_A_COURSE = ("institution", "college", "department", "prefix", "term")

# How many enrolled students each section is given. Two rather than one so that
# "the roster came back" is not satisfied by a reader that answers with a single
# row whatever it is asked.
ENROLLED_PER_SECTION = 2


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


def two_leads(rows: Any) -> dict[str, Any]:
    """Two lead faculty members with one course each, under one prefix, both enrolled.

    The §4.1 invariant 2 shape, built once because three tests ask the same
    question of it (`docs/MISTAKES.md` entry 13). Everything is committed on the
    way out, so the `pulse_app` connection the reads run on can see it.
    """
    graph = rows.graph
    mine = graph.person()
    theirs = graph.person()

    graph.scope("department")
    my_chain = graph.new_branch("institution", "college", "department")
    rows.seed("section", my_chain)
    their_chain = {name: row for name, row in my_chain.items() if name in ABOVE_A_COURSE}
    rows.seed("section", their_chain)

    for chain in (my_chain, their_chain):
        for _ in range(ENROLLED_PER_SECTION):
            rows.seed("enrollment", dict(chain))

    my_course = graph.key_of("course", my_chain["course"])
    their_course = graph.key_of("course", their_chain["course"])
    written(graph, lambda: graph.lead_mapping(person=mine, course=my_course), "My lead mapping")
    written(
        graph,
        lambda: graph.lead_mapping(person=theirs, course=their_course),
        "The sibling lead's mapping",
    )
    written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", scope=my_course, person=mine),
        "My lead-faculty assignment",
    )
    written(
        graph,
        lambda: graph.assign("LEAD_FACULTY", scope=their_course, person=theirs),
        "The sibling lead's assignment",
    )
    rows.commit()

    return {
        "person": mine,
        "course": my_course,
        "section": graph.key_of("section", my_chain["section"]),
        "sibling_course": their_course,
        "sibling_section": graph.key_of("section", their_chain["section"]),
    }


def reader_for(authz: Any, session: Any, person_id: Any) -> Any:
    """The scoped reader one person's resolved scope produces."""
    return authz.scoped_reader(session, authz.resolve_scope(session, person_id=person_id))


def test_a_scoped_reader_returns_the_roster_of_a_section_inside_the_purview(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """The door has to be open before its being shut elsewhere means anything.

    A reader that refuses everything satisfies both refusal tests below and serves
    no screen: §5.1's instructor report, §5.5's roll-ups and §3.4's participation
    all start from a roster. This is also where the read path itself is exercised
    over the connection production uses — the view exists, `pulse_app` may select
    from it, and the reader reaches it.
    """
    rows = committed_rows
    fixture = two_leads(rows)

    reader = reader_for(authz, application_session, fixture["person"])
    roster = list(reader.section_roster(section_id=fixture["section"]))

    assert roster, (
        f"The scoped reader returned no roster rows for a section inside the lead's own purview, "
        f"and {ENROLLED_PER_SECTION} students are enrolled in it. Either the reader filters them "
        "out or the E0-10 view does; both are worth knowing, and neither is the refusal the tests "
        "below are about. Without this, 'the sibling's section is refused' would be true of a "
        "reader that answers nothing to anybody."
    )


@pytest.mark.invariant
def test_a_scoped_reader_refuses_the_roster_of_a_section_outside_the_purview(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """SPEC §4.1 invariant 2, asserted as a refusal at the read path.

    A lead asks for the roster of a section in another lead's course. The answer
    is `OutOfPurviewError` — not an empty list, which is what a reader that
    silently filters would return and which a caller cannot tell from a section
    with nobody in it.

    **The control is the lead's own section, read on the same reader**, so the
    refusal is attributable to the node rather than to the reader, the session or
    the grant.

    **The mutation this exists to survive** is a `section_roster` that takes the
    section id and forwards it to the view without consulting the scope — which is
    the shape the helper has before somebody remembers the purview, and which
    passes the test above.
    """
    rows = committed_rows
    fixture = two_leads(rows)
    reader = reader_for(authz, application_session, fixture["person"])

    assert list(reader.section_roster(section_id=fixture["section"])), (
        "The reader returned nothing for the lead's own section, so the refusal below cannot be "
        "told from a reader that refuses everything. The test above diagnoses this."
    )

    with pytest.raises(authz.OutOfPurviewError):
        reader.section_roster(section_id=fixture["sibling_section"])


def test_a_scoped_reader_returns_enrollment_counts_for_a_course_inside_the_purview(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """The second E0-10 view, through the same chokepoint, for a course the lead leads.

    §5.5's roll-ups and §5.1's response rate are both counts before they are
    anything else, and §2.1's display labels are literally counts — "course rows
    `N sections · Lead: {name}`". A reader that could not answer this would leave
    every leadership surface empty, which is the failure the refusal test below
    cannot see.
    """
    rows = committed_rows
    fixture = two_leads(rows)

    reader = reader_for(authz, application_session, fixture["person"])
    counts = list(reader.section_enrollment_counts(course_id=fixture["course"]))

    assert counts, (
        "The scoped reader returned no enrollment counts for a course inside the lead's own "
        f"purview, whose section holds {ENROLLED_PER_SECTION} enrolments. The refusal test below "
        "would then be true of a reader that answers nothing at all."
    )


@pytest.mark.invariant
def test_a_scoped_reader_refuses_enrollment_counts_for_a_course_outside_the_purview(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """The same invariant at course grain, which is where a lead's purview is defined.

    §2.1 makes a lead's grant "only the courses they lead (never sibling leads'
    courses, at any point in the union)", so a course id is the exact unit this
    check is about — and an aggregate is not a softer disclosure than a roster.
    §4.1 item 4 keeps aggregate language away from individuals for the same
    reason: a count over a small section, read beside a roll-up somebody else can
    see, is a fact about people.

    The control is the lead's own course on the same reader.
    """
    rows = committed_rows
    fixture = two_leads(rows)
    reader = reader_for(authz, application_session, fixture["person"])

    assert list(reader.section_enrollment_counts(course_id=fixture["course"])), (
        "The reader returned nothing for the lead's own course, so the refusal below cannot be "
        "told from a reader that refuses everything. The test above diagnoses this."
    )

    with pytest.raises(authz.OutOfPurviewError):
        reader.section_enrollment_counts(course_id=fixture["sibling_course"])
