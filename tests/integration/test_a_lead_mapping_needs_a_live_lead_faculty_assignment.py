"""A course is mapped only to a Lead Faculty holder, and a lead who still leads is not revoked — E9-14 item 2.

The E9 boundary spec-conformance review found two definitions of "led": the
mapping table (`lead_faculty_mapping`) and the `LEAD_FACULTY` assignment. A
course mapped to a person with no `LEAD_FACULTY` assignment is "led" for the
roll-up's by-lead grouping and for the chair's fallback (a led course does not
fall to the chair, SPEC §2.1), yet ADR 0190's review queue reads a lead only
"with a `LEAD_FACULTY` assignment" — so that course's harmful comments reach no
queue at all, the lead's or the chair's. Revoking the assignment of a person
who still has mappings makes the same state from the other end.

**The settled interface (E9-14):** `views_sql/people_graph_v003.sql` replaces
`admin_map_lead_course` and `admin_revoke_role` with the same names and
signatures. Two new named refusals, each SQLSTATE `P0001` with the copy key as
the message (`app/copy/admin_people.py`):

  - `admin_people.lead_needs_the_lead_role` — mapping a course to a person with
    no live `LEAD_FACULTY` assignment;
  - `admin_people.lead_still_leads_courses` — revoking a `LEAD_FACULTY`
    assignment while its person still has `lead_faculty_mapping` rows; "the
    route's sentence names the count, as `assignment_has_reports` does". That
    refusal carries its count in the error's detail, digits only, and its text
    holds `{count}`
    (`test_the_people_graph_definers_follow_the_rulings.py`), so this one is
    asserted the same way.

The CSV import goes through the same definers (ADR 0204), so its mapping file
inherits the first refusal; a mapping file revokes nothing, so the second has
no import path to test.

Every definer call rides `pulse_app`'s connection and every effect is read back
on a second connection (`tests/fixtures/people_graph.py`, `docs/MISTAKES.md`
entry 46); the route and import tests ride the built application over HTTP
(entry 47).

**Which failure a red is, before E9-14 lands.** The refused calls succeed today:
each FAILS on the named-refusal assertion (the map writes a row; the revoke
deletes the assignment). The HTTP and import refusals FAIL on the status. The
twins are green today; a `KeyError` on a new copy key fails inside a test body.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.people_editor import PeopleEditor
from fixtures.people_graph import (
    NAMED_REFUSAL,
    Called,
    PeopleGraphWorld,
    token,
)
from fixtures.submit import copy_texts
from test_the_people_editor_imports_after_a_dry_run import (
    MAPPINGS,
    NO_DIGEST,
    _apply,
    _csv,
    _dry_run,
)

from app.services.people import MAPPING_HEADER

pytestmark = pytest.mark.integration

LEAD_NEEDS_THE_LEAD_ROLE = "admin_people.lead_needs_the_lead_role"
LEAD_STILL_LEADS_COURSES = "admin_people.lead_still_leads_courses"


def refused_with(called: Called, key: str) -> bool:
    return (called.sqlstate, called.message) == (NAMED_REFUSAL, key)


def _text(key: str, **values: object) -> str:
    from app.copy.admin_people import COPY

    return COPY[key].text.format(**values)


# ---------------------------------------------------------------------------
# Mapping a course: only to a Lead Faculty holder.
# ---------------------------------------------------------------------------

# What the person holds when the admin maps a course to them, and why each is here.
NOT_A_LEAD = {
    "nothing at all": (),
    # A leadership role of another level, so "holds some leadership role" is not
    # the rule the definer checks.
    "a chair assignment only": ("CHAIR",),
    # A teaching grant, which E9-01's purview never unions into a leadership tree.
    "an instructor assignment only": ("INSTRUCTOR",),
}


@pytest.mark.parametrize("holds", list(NOT_A_LEAD), ids=list(NOT_A_LEAD))
def test_mapping_a_course_to_a_person_holding_no_lead_faculty_assignment_is_refused_and_writes_nothing(
    people_graph: PeopleGraphWorld, holds: str
) -> None:
    """`lead_needs_the_lead_role`, no mapping row, no audit row.

    **The mutation it kills:** v001's map, which writes any person; a check that
    accepts any assignment at all (the chair and the instructor cases); a check
    made after the insert, with the refusal raised but the row committed. **The
    near miss it spares:** a `LEAD_FACULTY` holder, mapped (the next test).
    """
    world = people_graph
    person = world.a_person()
    for role in NOT_A_LEAD[holds]:
        world.assignment(role, person=person)
    course = world.a_course()

    refused = world.call("admin_map_lead_course", world.admin, person=person, course=course)

    assert refused_with(refused, LEAD_NEEDS_THE_LEAD_ROLE), (
        f"Mapping a course to a person holding {holds} {refused.describe()}; settled: "
        f"`{LEAD_NEEDS_THE_LEAD_ROLE}` (SQLSTATE {NAMED_REFUSAL})."
    )
    assert world.mappings_of_course(course) == [], "The refused map wrote a mapping row."
    assert world.audit_rows(world.admin) == [], "The refused map wrote an audit row."


def test_mapping_a_course_to_a_lead_faculty_holder_writes_the_mapping(
    people_graph: PeopleGraphWorld,
) -> None:
    """The present twin: a person holding a `LEAD_FACULTY` assignment is mapped.

    The assignment is at another course than the one mapped: the rule is that
    the person holds the role, not that it is scoped to this course.

    **The mutation it kills:** a map that refuses everyone; a check scoped to
    the mapped course, which would make the first mapping of a new lead
    impossible to write.
    """
    world = people_graph
    lead = world.a_person()
    world.assignment("LEAD_FACULTY", person=lead)
    course = world.a_course()

    mapped = world.call("admin_map_lead_course", world.admin, person=lead, course=course)

    assert mapped.failure is None, f"Mapping a course to a Lead Faculty holder {mapped.describe()}."
    assert [str(row["person_id"]) for row in world.mappings_of_course(course)] == [str(lead)]


# ---------------------------------------------------------------------------
# Revoking: not while the person still leads.
# ---------------------------------------------------------------------------


def lead_with_courses(world: PeopleGraphWorld, count: int) -> tuple[Any, Any, list[Any]]:
    """A person, their `LEAD_FACULTY` assignment, and `count` courses mapped to them."""
    lead = world.a_person()
    assignment = world.assignment("LEAD_FACULTY", person=lead)
    courses = [world.a_course() for _ in range(count)]
    for course in courses:
        world.a_mapping(person=lead, course=course)
    return lead, assignment, courses


@pytest.mark.parametrize("count", [1, 3])
def test_revoking_a_lead_faculty_assignment_whose_person_still_leads_is_refused_with_the_count(
    people_graph: PeopleGraphWorld, count: int
) -> None:
    """`lead_still_leads_courses` with the mapping count in the detail; nothing deleted; then the retry.

    One course and three, so the count is read from the rows and not a
    constant. After every course is unmapped through the definer, the same
    revoke succeeds.

    **The mutations it kills:** v001's revoke, which deletes the assignment and
    leaves the mappings naming a person with no lead role; a count hard-coded
    or reported as a boolean; the mappings deleted along with the assignment (a
    cascade the ruling did not make); a refusal that stays after the mappings
    are gone. **The near miss it spares:** the retry, and the dean assignment of
    a lead (below).
    """
    world = people_graph
    lead, assignment, courses = lead_with_courses(world, count)
    template = copy_texts().get(LEAD_STILL_LEADS_COURSES)
    assert template is not None and "{count}" in template, (
        f"`{LEAD_STILL_LEADS_COURSES}` is {template!r} in the copy registry; settled: the route's "
        "sentence names the count, as `assignment_has_reports` does, so its text carries "
        "`{count}`."
    )

    refused = world.call("admin_revoke_role", world.admin, assignment=assignment)

    assert refused_with(refused, LEAD_STILL_LEADS_COURSES), (
        f"Revoking a `LEAD_FACULTY` assignment whose person leads {count} courses "
        f"{refused.describe()}; settled: `{LEAD_STILL_LEADS_COURSES}`."
    )
    assert refused.detail == str(count), (
        f"The refusal's detail is {refused.detail!r}; as `assignment_has_reports` carries its "
        f"children's count, this one carries the mappings' count, digits only — here {count}."
    )
    assert (
        world.assignment_row(assignment) is not None
    ), "The refused revoke deleted the assignment."
    still = sorted(
        str(row["person_id"]) for course in courses for row in world.mappings_of_course(course)
    )
    assert still == [str(lead)] * count, f"The refused revoke moved the mappings: {still}."
    assert world.audit_rows(world.admin) == [], "The refused revoke wrote an audit row."

    for course in courses:
        unmapped = world.call("admin_unmap_lead_course", world.admin, course=course)
        assert unmapped.failure is None, f"Unmapping a course {unmapped.describe()}."
    retried = world.call("admin_revoke_role", world.admin, assignment=assignment)

    assert (
        retried.failure is None
    ), f"Revoking the assignment after every course was unmapped {retried.describe()}."
    assert (
        world.assignment_row(assignment) is None
    ), "The assignment is still there after the retry."


def test_revoking_another_assignment_of_a_person_who_leads_courses_is_not_refused(
    people_graph: PeopleGraphWorld,
) -> None:
    """A lead who also holds `DEAN`: the dean assignment is revoked; the lead assignment and mappings stay.

    **The mutation it kills:** the refusal keyed on the person ("has mappings")
    without the assignment's role, which makes every other role of a lead
    unrevocable. **The near miss:** the lead assignment itself, refused above.
    """
    world = people_graph
    lead, lead_assignment, courses = lead_with_courses(world, 1)
    dean_assignment = world.assignment("DEAN", person=lead)

    revoked = world.call("admin_revoke_role", world.admin, assignment=dean_assignment)

    assert (
        revoked.failure is None
    ), f"Revoking the `DEAN` assignment of a person who leads a course {revoked.describe()}."
    assert world.assignment_row(dean_assignment) is None, "The dean assignment is still there."
    remaining = [token(row["role"]) for row in world.assignments_of(lead)]
    assert remaining == ["LEAD_FACULTY"], f"The lead now holds {remaining}."
    assert [str(row["person_id"]) for row in world.mappings_of_course(courses[0])] == [str(lead)]
    assert world.assignment_row(lead_assignment) is not None


def test_revoking_a_lead_faculty_assignment_of_a_person_with_no_mappings_deletes_it(
    people_graph: PeopleGraphWorld,
) -> None:
    """The present twin: a lead who leads nothing is revoked as any childless assignment is (ruling 7).

    **The mutation it kills:** a refusal on every `LEAD_FACULTY` revoke.
    """
    world = people_graph
    _lead, assignment, _courses = lead_with_courses(world, 0)

    revoked = world.call("admin_revoke_role", world.admin, assignment=assignment)

    assert revoked.failure is None, f"Revoking a lead with no mappings {revoked.describe()}."
    assert world.assignment_row(assignment) is None, "The revoked assignment is still there."


# ---------------------------------------------------------------------------
# Over HTTP: the route's sentence names the count.
# ---------------------------------------------------------------------------


def test_the_revoke_route_answers_a_lead_who_still_leads_409_with_the_count(
    people_editor: PeopleEditor,
) -> None:
    """`DELETE /admin/assignments/{id}` for a lead of two courses: 409, the sentence with 2, nothing deleted.

    **The mutations it kills:** the new refusal left unmapped at the route (a
    500), or answered with another sentence; the count dropped from the
    sentence. **The near miss it spares:** a lead with no course, revoked (204).
    """
    editor = people_editor
    lead = editor.assignment("LEAD_FACULTY")
    for _ in range(2):
        editor.mapping(person=lead.person, course=editor.course())
    idle = editor.assignment("LEAD_FACULTY")

    refused = editor.ask("DELETE", f"/admin/assignments/{lead.assignment}")
    revoked = editor.ask("DELETE", f"/admin/assignments/{idle.assignment}")

    assert revoked.status_code == 204, (
        f"The present twin: revoking a lead with no course answered {revoked.status_code} "
        f"{revoked.text[:300]!r}."
    )
    assert (
        refused.status_code == 409
    ), f"Revoking a lead of two courses answered {refused.status_code} {refused.text[:300]!r}."
    assert refused.json() == {"detail": _text(LEAD_STILL_LEADS_COURSES, count=2)}
    assert [row["id"] for row in editor.assignments_of(lead.person)] == [lead.assignment]


# ---------------------------------------------------------------------------
# The CSV import inherits the map's refusal.
# ---------------------------------------------------------------------------


def a_mapping_file(course: Any, person: Any) -> str:
    """A mapping file of one line, mapping `course` to `person` (line 2, after the header)."""
    return _csv(MAPPING_HEADER, [[str(course), "label", str(person), "label"]])


def test_a_mapping_file_naming_a_person_with_no_lead_role_is_refused_at_its_line_and_applies_nothing(
    people_editor: PeopleEditor,
) -> None:
    """Dry run and apply both answer 422 naming line 2 and the new refusal; the course stays unled.

    **The present twin:** the same file naming a Lead Faculty holder dry-runs
    to a diff adding that mapping.

    **The mutations it kills:** an import that writes the mapping table without
    the definer (the ADR 0204 path bypassed); an import line refusal that maps
    the new key to no sentence (a 500). **The near miss it spares:** the twin.
    """
    editor = people_editor
    course = editor.course()
    nobody = editor.person(f"Not A Lead {uuid4().hex[:6]}")
    lead = editor.assignment("LEAD_FACULTY").person
    refused_body = a_mapping_file(course, nobody)
    expected = {
        "detail": _text(
            "admin_people.import_line_refused", line=2, reason=_text(LEAD_NEEDS_THE_LEAD_ROLE)
        )
    }

    twin = _dry_run(editor, MAPPINGS, a_mapping_file(course, lead))
    assert twin.status_code == 200, (
        f"The present twin: a file mapping the course to a Lead Faculty holder answered "
        f"{twin.status_code} {twin.text[:300]!r}."
    )
    added = [(row["course_id"], row["person_id"]) for row in twin.json()["added"]]
    assert added == [(str(course), str(lead))], f"The twin's diff adds {added}."

    for what, answered in (
        ("the dry run", _dry_run(editor, MAPPINGS, refused_body)),
        ("the apply", _apply(editor, MAPPINGS, refused_body, NO_DIGEST)),
    ):
        assert answered.status_code == 422, (
            f"{what.capitalize()} of a file mapping a course to a person with no lead role "
            f"answered {answered.status_code} {answered.text[:300]!r}."
        )
        assert answered.json() == expected, f"{what.capitalize()} answered {answered.json()}."
    assert editor.lead_of(course) is None, "The refused file mapped the course."
