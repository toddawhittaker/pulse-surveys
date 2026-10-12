"""The people-graph writes follow rulings 1 and 7, decision 11, ADR 0044 and the linkage rules — E9-02.

> 3. **Every Pulse-owned role is grantable, to anyone (ruling 1).** An admin
>    grants `CARE` to another person, `ADMIN` to another person, and `CARE`,
>    `ADMIN` and `DEAN` to their own person; each write succeeds.
> 4. **`INSTRUCTOR` stays LMS-owned (decision 11).** Granting or revoking an
>    `INSTRUCTOR` assignment, and setting an edge whose child is one, are
>    refused with a named refusal; the roster sync's own writes are unchanged.
> 6. **Revoke deletes (ruling 7).** Revoking a childless assignment deletes the
>    row. Revoking one that another assignment reports to is refused with a
>    named refusal naming the children's count, and deletes nothing; after the
>    children are re-pointed, it succeeds.
> 7. **Edges still climb.** Setting an edge from a `CHAIR` to a `LEAD_FACULTY`
>    parent is refused by ADR 0044's trigger, surfaced as a named refusal, not a
>    500.
> 8. **The linkage is admin-only and one-to-one.** Linking a web-login subject
>    already linked to another person is refused; unlinking then linking
>    succeeds; each is audited.

Every call is the admin's, as `pulse_app` (`tests/fixtures/people_graph.py`);
done-when 1 is where non-admins are refused. Every effect is read back on a
second connection. Every refusal is asserted as `P0001` *and* its settled key,
so a missing grant (42501), a raw constraint (class 23) or a missing function
(42883) cannot satisfy one.

"The roster sync's own writes are unchanged" (done-when 4's last clause) is held
by the roster suites that already drive `record_teaching_instructor` and
`end_teaching_instructor`; E9-02 does not touch either function, and nothing
here re-asserts them.

**Which failure a red is, before E9-02 lands.** Every call answers 42883 (no such
function), which fails the success or the named-refusal assertion — a FAILED.
"""

from uuid import uuid4

import pytest
from fixtures.people_graph import (
    ASSIGNMENT_HAS_REPORTS,
    COURSE_ALREADY_LED,
    COURSE_NOT_LED,
    EDGE_DOES_NOT_CLIMB,
    INSTRUCTOR_IS_LMS_OWNED,
    NAMED_REFUSAL,
    PERSON_ALREADY_LINKED,
    PERSON_NOT_LINKED,
    SCOPE_IS_NOT_THE_ROLES_NODE,
    SUBJECT_LINKED_TO_ANOTHER,
    WEB_LOGIN_LINKAGE_CHANGED,
    Called,
    PeopleGraphWorld,
    token,
)
from fixtures.submit import copy_texts

pytestmark = pytest.mark.integration

ISSUER = "https://e9-02-issuer.invalid"


def refused_with(called: Called, key: str) -> bool:
    return (called.sqlstate, called.message) == (NAMED_REFUSAL, key)


# ---------------------------------------------------------------------------
# Done-when 3 (ruling 1).
# ---------------------------------------------------------------------------

GRANTS = (
    ("another person", "CARE"),
    ("another person", "ADMIN"),
    ("their own person", "CARE"),
    ("their own person", "ADMIN"),
    ("their own person", "DEAN"),
)


@pytest.mark.parametrize(("to", "role"), GRANTS, ids=[f"{role}-to-{to}" for to, role in GRANTS])
def test_an_admin_grants_every_pulse_owned_role_to_anyone_including_themselves(
    people_graph: PeopleGraphWorld, to: str, role: str
) -> None:
    """Ruling 1: no refusal of Care, Admin or a self-targeted grant. Each grant is read back.

    The row must exist under the id the definer returned, for the person named,
    with the role named, at the scope named (in the column the role's level
    calls for, read back as R2's `coalesce`), and with no parent.

    **The mutations it kills:** a code refusal of `CARE` or `ADMIN` (the design
    ruling 1 rejected); a refusal of a grant whose target is the actor; the
    scope written to the wrong level's column; a new grant written with a
    parent. **The near miss:** `INSTRUCTOR`, refused (done-when 4), and a scope
    of the wrong level, refused (below).
    """
    world = people_graph
    target = world.admin if to == "their own person" else world.a_person()
    scope = world.scope(role)
    before = len(world.assignments_of(target))

    granted = world.call("admin_grant_role", world.admin, person=target, role=role, scope=scope)

    assert granted.failure is None, (
        f"The admin granting `{role}` to {to} {granted.describe()}. Ruling 1: every Pulse-owned "
        "role is grantable to any person, the acting admin included."
    )
    row = world.assignment_row(granted.value)
    assert (
        row is not None
    ), f"The grant answered {granted.value!r} and no `role_assignment` row carries that id."
    assert (str(row["person_id"]), token(row["role"]), str(world.scope_node_of(row))) == (
        str(target),
        role,
        str(scope),
    ), f"The granted row is {row}; it should be `{role}` for {target} at scope {scope}."
    assert row["reports_to"] is None, f"A new grant carries a parent: {row['reports_to']}."
    assert len(world.assignments_of(target)) == before + 1


def test_a_grant_at_a_node_of_another_level_is_refused(people_graph: PeopleGraphWorld) -> None:
    """The scope is one id, put in the column the role's level calls for; a course id for a dean is not a college.

    **The mutation it kills:** the scope written without a level check, or into
    a column chosen by the id's own table, which grants a dean a course. **The
    near miss:** the same grant at a college, accepted (done-when 3's `DEAN`
    case).
    """
    world = people_graph
    target = world.a_person()

    refused = world.call(
        "admin_grant_role", world.admin, person=target, role="DEAN", scope=world.a_course()
    )

    assert refused_with(refused, SCOPE_IS_NOT_THE_ROLES_NODE), (
        f"A `DEAN` grant at a course {refused.describe()}; settled: "
        f"`{SCOPE_IS_NOT_THE_ROLES_NODE}`."
    )
    assert world.assignments_of(target) == [], "The refused grant left a row."


# ---------------------------------------------------------------------------
# Done-when 4 (decision 11).
# ---------------------------------------------------------------------------


def test_granting_an_instructor_assignment_is_refused_and_writes_nothing(
    people_graph: PeopleGraphWorld,
) -> None:
    """Decision 11: the editor writes no teaching grant; the roster sync is its one writer.

    **The mutation it kills:** a grant that accepts every role in the enum,
    which lets the People editor hand anyone a section's teaching rights — and,
    through ADR 0191's channel, a student's view of their name. **The near
    miss:** the other seven roles, granted (done-when 3).
    """
    world = people_graph
    target = world.a_person()
    section = world.scope("INSTRUCTOR")

    refused = world.call(
        "admin_grant_role", world.admin, person=target, role="INSTRUCTOR", scope=section
    )

    assert refused_with(
        refused, INSTRUCTOR_IS_LMS_OWNED
    ), f"Granting `INSTRUCTOR` {refused.describe()}; settled: `{INSTRUCTOR_IS_LMS_OWNED}`."
    assert world.assignments_of(target) == [], "The refused teaching grant left a row."
    assert world.audit_rows(world.admin) == [], "The refused teaching grant left an audit row."


def test_revoking_an_instructor_assignment_is_refused_and_deletes_nothing(
    people_graph: PeopleGraphWorld,
) -> None:
    """Decision 11 on the revoke: ending a teaching grant is `end_teaching_instructor`'s alone.

    **The mutation it kills:** a revoke that deletes any row by id, which ends
    a teaching grant outside the roster sync and skips its
    `ended_teaching_grant` record. **The near miss:** a `DEAN` row, revoked
    (done-when 6).
    """
    world = people_graph
    teaching = world.assignment("INSTRUCTOR")

    refused = world.call("admin_revoke_role", world.admin, assignment=teaching)

    assert refused_with(
        refused, INSTRUCTOR_IS_LMS_OWNED
    ), f"Revoking an `INSTRUCTOR` row {refused.describe()}; settled: `{INSTRUCTOR_IS_LMS_OWNED}`."
    assert world.assignment_row(teaching) is not None, "The refused revoke deleted the row."


def test_an_edge_whose_child_is_an_instructor_assignment_is_refused(
    people_graph: PeopleGraphWorld,
) -> None:
    """Decision 11 on the edge: a teaching grant gets no parent from the editor.

    The parent is a `LEAD_FACULTY` assignment, which ADR 0044's trigger would
    accept (an instructor ranks below a lead), so only the definer's own
    `INSTRUCTOR` refusal can refuse this — and the key says which did.

    **The mutation it kills:** the `INSTRUCTOR` check left out of the edge
    write, relying on the trigger, which here says yes. **The near miss:** a
    `CHAIR` under a `DEAN`, accepted (done-when 7's pair).
    """
    world = people_graph
    teaching = world.assignment("INSTRUCTOR")
    lead = world.assignment("LEAD_FACULTY")

    refused = world.call("admin_set_reports_to", world.admin, assignment=teaching, reports_to=lead)

    assert refused_with(refused, INSTRUCTOR_IS_LMS_OWNED), (
        f"An edge from an `INSTRUCTOR` child {refused.describe()}; settled: "
        f"`{INSTRUCTOR_IS_LMS_OWNED}`."
    )
    assert world.reports_to_of(teaching) is None, "The refused edge was written."


# ---------------------------------------------------------------------------
# Done-when 6 (ruling 7).
# ---------------------------------------------------------------------------


def test_revoking_a_childless_assignment_deletes_the_row(people_graph: PeopleGraphWorld) -> None:
    """Ruling 7: revoke deletes. No end date, no flag — the row is gone.

    **The mutation it kills:** a soft revoke (an `ended_on`, a status column),
    which leaves the row every read predicate counts as live. **The near
    miss:** a row with children, refused (below).
    """
    world = people_graph
    assignment = world.assignment("DEAN")

    revoked = world.call("admin_revoke_role", world.admin, assignment=assignment)

    assert revoked.failure is None, f"Revoking a childless `DEAN` row {revoked.describe()}."
    assert world.assignment_row(assignment) is None, "The revoked row is still there."


@pytest.mark.parametrize("children", [1, 3])
def test_revoking_a_parent_is_refused_with_its_child_count_until_the_children_are_repointed(
    people_graph: PeopleGraphWorld, children: int
) -> None:
    """Ruling 7's `RESTRICT`, turned into a named refusal carrying the count; then the retry.

    One child and three children, so the count in the detail is read from the
    rows and not a constant. Then every child is re-pointed (cleared through
    `admin_set_reports_to`) and the same revoke succeeds.

    **The mutations it kills:** the database's foreign-key error left to reach
    the caller (23503, a 500 at the route); a count hard-coded or reported as a
    boolean; the parent deleted with its children cascaded or orphaned; a
    refusal that stays after the children are gone. **The near miss:** the
    childless revoke above.
    """
    world = people_graph
    parent = world.assignment("DEAN")
    kids = [world.assignment("CHAIR", reports_to=parent) for _ in range(children)]
    template = copy_texts().get(ASSIGNMENT_HAS_REPORTS)
    assert template is not None and "{count}" in template, (
        f"`{ASSIGNMENT_HAS_REPORTS}` is {template!r} in the copy registry; settled: its text "
        "carries the placeholder `{count}`, filled from the refusal's detail."
    )

    refused = world.call("admin_revoke_role", world.admin, assignment=parent)

    assert refused_with(refused, ASSIGNMENT_HAS_REPORTS), (
        f"Revoking a `DEAN` row {children} assignments report to {refused.describe()}; settled: "
        f"`{ASSIGNMENT_HAS_REPORTS}`."
    )
    assert refused.detail == str(children), (
        f"The refusal's detail is {refused.detail!r}; settled: the children's count, digits only "
        f"— here {children}."
    )
    assert world.assignment_row(parent) is not None, "The refused revoke deleted the parent."
    assert [str(world.reports_to_of(kid)) for kid in kids] == [
        str(parent)
    ] * children, "The refused revoke moved a child."

    for kid in kids:
        cleared = world.call("admin_set_reports_to", world.admin, assignment=kid, reports_to=None)
        assert cleared.failure is None, f"Clearing a child's edge {cleared.describe()}."
    retried = world.call("admin_revoke_role", world.admin, assignment=parent)

    assert (
        retried.failure is None
    ), f"Revoking the parent after every child was re-pointed {retried.describe()}."
    assert world.assignment_row(parent) is None, "The parent is still there after the retry."


# ---------------------------------------------------------------------------
# Done-when 7 (ADR 0044).
# ---------------------------------------------------------------------------


def test_an_edge_from_a_chair_to_a_lead_is_refused_as_a_named_refusal(
    people_graph: PeopleGraphWorld,
) -> None:
    """ADR 0044's trigger refuses an edge that does not climb; the definer names it.

    **The mutations it kills:** the trigger's `check_violation` left to reach
    the caller (23514, a 500 at the route); the trigger bypassed or dropped by
    the migration. **The near miss:** a `CHAIR` under a `DEAN` (below).
    """
    world = people_graph
    chair = world.assignment("CHAIR")
    lead = world.assignment("LEAD_FACULTY")

    refused = world.call("admin_set_reports_to", world.admin, assignment=chair, reports_to=lead)

    assert refused_with(
        refused, EDGE_DOES_NOT_CLIMB
    ), f"A `CHAIR` under a `LEAD_FACULTY` {refused.describe()}; settled: `{EDGE_DOES_NOT_CLIMB}`."
    assert world.reports_to_of(chair) is None, "The refused edge was written."


def test_an_edge_that_climbs_is_set_and_then_cleared(people_graph: PeopleGraphWorld) -> None:
    """The accepted half of done-when 7, and the settled clear (a null parent clears the edge).

    **The mutations it kills:** an edge write that refuses every edge; a clear
    refused, or a null parent read as "leave it".
    """
    world = people_graph
    chair = world.assignment("CHAIR")
    dean = world.assignment("DEAN")

    set_ = world.call("admin_set_reports_to", world.admin, assignment=chair, reports_to=dean)
    assert set_.failure is None, f"A `CHAIR` under a `DEAN` {set_.describe()}."
    assert str(world.reports_to_of(chair)) == str(dean), "The climbing edge was not stored."

    cleared = world.call("admin_set_reports_to", world.admin, assignment=chair, reports_to=None)
    assert cleared.failure is None, f"Clearing the edge {cleared.describe()}."
    assert world.reports_to_of(chair) is None, "The cleared edge is still stored."


# ---------------------------------------------------------------------------
# The mapping: one lead per course.
# ---------------------------------------------------------------------------


def test_a_course_with_a_lead_is_refused_a_second_until_it_is_unmapped(
    people_graph: PeopleGraphWorld,
) -> None:
    """One lead per course, by the existing unique constraint, surfaced by name; unmap then map.

    **The mutations it kills:** the unique violation left raw (23505); a map
    that replaces the lead silently (an upsert), which changes a course's lead
    with one audit row where the settled change is two. **The near miss:** the
    unmap-then-map, accepted.
    """
    world = people_graph
    course = world.a_course()
    first, second = world.a_person(), world.a_person()
    world.a_mapping(person=first, course=course)

    refused = world.call("admin_map_lead_course", world.admin, person=second, course=course)
    assert refused_with(
        refused, COURSE_ALREADY_LED
    ), f"Mapping a second lead {refused.describe()}; settled: `{COURSE_ALREADY_LED}`."
    assert [str(row["person_id"]) for row in world.mappings_of_course(course)] == [str(first)]

    unmapped = world.call("admin_unmap_lead_course", world.admin, course=course)
    mapped = world.call("admin_map_lead_course", world.admin, person=second, course=course)
    assert (
        unmapped.failure is None and mapped.failure is None
    ), f"Unmap {unmapped.describe()}; map {mapped.describe()}."
    assert [str(row["person_id"]) for row in world.mappings_of_course(course)] == [str(second)]


def test_unmapping_a_course_with_no_lead_is_refused(people_graph: PeopleGraphWorld) -> None:
    """The settled `course_not_led`. **The mutation it kills:** a silent no-op that still audits."""
    world = people_graph
    refused = world.call("admin_unmap_lead_course", world.admin, course=world.a_course())
    assert refused_with(
        refused, COURSE_NOT_LED
    ), f"Unmapping an unled course {refused.describe()}; settled: `{COURSE_NOT_LED}`."
    assert world.audit_rows(world.admin) == [], "The refused unmap left an audit row."


# ---------------------------------------------------------------------------
# Done-when 8.
# ---------------------------------------------------------------------------


def test_linking_a_subject_already_linked_to_another_person_is_refused_and_writes_nothing(
    people_graph: PeopleGraphWorld,
) -> None:
    """Done-when 8's refusal: one subject is one person (ADR 0097's unique pair).

    **The mutations it kills:** the unique violation left raw; a link that
    re-points the subject to the new person (an upsert), which hands one
    person's web login to another — the ticket's "links someone else's web
    login to a privileged person". **The near miss:** unlink then link (below).
    """
    world = people_graph
    holder, other = world.a_person(), world.a_person()
    subject = world.a_linkage(person=holder)

    refused = world.call(
        "admin_link_web_login", world.admin, person=other, issuer=ISSUER, subject=subject
    )

    assert refused_with(refused, SUBJECT_LINKED_TO_ANOTHER), (
        f"Linking a subject held by another person {refused.describe()}; settled: "
        f"`{SUBJECT_LINKED_TO_ANOTHER}`."
    )
    assert [str(row["person_id"]) for row in world.linkages_of_subject(subject)] == [str(holder)]
    assert world.linkages_of(other) == [], "The refused link gave the other person a linkage."
    assert world.audit_rows(world.admin) == [], "The refused link left an audit row."


def test_unlinking_then_linking_moves_the_subject_and_each_is_audited(
    people_graph: PeopleGraphWorld,
) -> None:
    """Done-when 8's accepted half: unlink, then link the same subject to another person; two audit rows.

    **The mutations it kills:** an unlink that leaves the row; a link refused
    after an unlink (a stale check); either write unaudited, or audited about
    the wrong person.
    """
    world = people_graph
    holder, other = world.a_person(), world.a_person()
    subject = world.a_linkage(person=holder)

    unlinked = world.call("admin_unlink_web_login", world.admin, person=holder)
    linked = world.call(
        "admin_link_web_login", world.admin, person=other, issuer=ISSUER, subject=subject
    )

    assert unlinked.failure is None, f"Unlinking {unlinked.describe()}."
    assert linked.failure is None, f"Linking after the unlink {linked.describe()}."
    assert world.linkages_of(holder) == [], "The unlinked person still has a linkage."
    assert [str(row["person_id"]) for row in world.linkages_of_subject(subject)] == [str(other)]
    audited = [
        (token(row["action"]), str(row["subject_person_id"]))
        for row in world.audit_rows(world.admin)
    ]
    assert audited == [
        (WEB_LOGIN_LINKAGE_CHANGED, str(holder)),
        (WEB_LOGIN_LINKAGE_CHANGED, str(other)),
    ], f"The unlink and the link left the audit rows {audited}."


def test_a_person_with_a_web_login_is_refused_a_second(people_graph: PeopleGraphWorld) -> None:
    """One web account per person (ADR 0097's second unique constraint), surfaced by name.

    **The mutation it kills:** the two unique constraints told apart wrongly,
    so this answers `subject_linked_to_another`, which tells the admin the wrong
    thing to fix.
    """
    world = people_graph
    person = world.a_person()
    world.a_linkage(person=person)

    refused = world.call(
        "admin_link_web_login",
        world.admin,
        person=person,
        issuer=ISSUER,
        subject=f"e9-02-second-{uuid4().hex}",
    )

    assert refused_with(refused, PERSON_ALREADY_LINKED), (
        f"A second web login for one person {refused.describe()}; settled: "
        f"`{PERSON_ALREADY_LINKED}`."
    )
    assert len(world.linkages_of(person)) == 1


def test_unlinking_a_person_with_no_web_login_is_refused(people_graph: PeopleGraphWorld) -> None:
    """The settled `person_not_linked`. **The mutation it kills:** a silent no-op that still audits."""
    world = people_graph
    refused = world.call("admin_unlink_web_login", world.admin, person=world.a_person())
    assert refused_with(
        refused, PERSON_NOT_LINKED
    ), f"Unlinking an unlinked person {refused.describe()}; settled: `{PERSON_NOT_LINKED}`."
    assert world.audit_rows(world.admin) == [], "The refused unlink left an audit row."
