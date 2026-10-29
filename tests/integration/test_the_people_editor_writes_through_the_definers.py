"""The people editor's writes, over HTTP: grants, revokes, edges, linkage and the acting admin.

SPEC §6.3 and ADR 0200: every Pulse-owned role is grantable, Care and Admin
included, to anyone, the acting admin included; a teaching grant is the
roster's; revoking deletes, and an assignment others report to is refused with
how many; the web-login linkage is set and cleared here. The acting admin is the
verified session's person only, whatever the request names.
"""

from uuid import uuid4

import pytest
from fixtures.admin_gate import a_person_holding
from fixtures.people_editor import PeopleEditor

from app.copy.admin_people import COPY

pytestmark = pytest.mark.integration


def _text(key: str, **values: object) -> str:
    return COPY[f"admin_people.{key}"].text.format(**values)


def _grant(editor: PeopleEditor, person: object, role: str, scope: object, **kw: object):
    return editor.ask(
        "POST",
        f"/admin/people/{person}/assignments",
        json={"role": role, "scope_node_id": str(scope)},
        **kw,
    )


def test_care_and_admin_are_granted_to_anyone_and_to_the_acting_admin(
    people_editor: PeopleEditor,
) -> None:
    institution = people_editor.scope("CARE")
    somebody = people_editor.person()
    for person, role in (
        (somebody, "CARE"),
        (somebody, "ADMIN"),
        (people_editor.admin.person_id, "CARE"),
        (people_editor.admin.person_id, "ADMIN"),
    ):
        answer = _grant(people_editor, person, role, institution)
        assert answer.status_code == 201, f"{role} to {person}: {answer.text}"
        granted = answer.json()["assignment_id"]
        held = {str(row["id"]): row["role"] for row in people_editor.assignments_of(person)}
        assert held.get(granted) == role


def test_a_teaching_grant_is_refused_with_its_sentence(people_editor: PeopleEditor) -> None:
    person = people_editor.person()
    answer = _grant(people_editor, person, "INSTRUCTOR", people_editor.scope("INSTRUCTOR"))
    assert answer.status_code == 409
    assert answer.json() == {"detail": _text("instructor_is_lms_owned")}
    assert people_editor.assignments_of(person) == []


def test_revoking_a_childless_assignment_deletes_it(people_editor: PeopleEditor) -> None:
    lead = people_editor.assignment("LEAD_FACULTY")
    answer = people_editor.ask("DELETE", f"/admin/assignments/{lead.assignment}")
    assert answer.status_code == 204, answer.text
    assert people_editor.assignments_of(lead.person) == []


def test_revoking_an_assignment_with_reports_names_how_many_and_keeps_it(
    people_editor: PeopleEditor,
) -> None:
    chair = people_editor.assignment("CHAIR")
    for _ in range(2):
        people_editor.assignment("LEAD_FACULTY", reports_to=chair.assignment)
    answer = people_editor.ask("DELETE", f"/admin/assignments/{chair.assignment}")
    assert answer.status_code == 409
    assert answer.json() == {"detail": _text("assignment_has_reports", count=2)}
    assert [row["id"] for row in people_editor.assignments_of(chair.person)] == [chair.assignment]


def test_an_edge_is_set_and_cleared_and_never_under_a_teaching_grant(
    people_editor: PeopleEditor,
) -> None:
    chair = people_editor.assignment("CHAIR")
    lead = people_editor.assignment("LEAD_FACULTY")
    path = f"/admin/assignments/{lead.assignment}/reports-to"
    assert (
        people_editor.ask("PUT", path, json={"reports_to": str(chair.assignment)}).status_code
        == 204
    )
    assert people_editor.assignments_of(lead.person)[0]["reports_to"] == chair.assignment
    assert people_editor.ask("PUT", path, json={"reports_to": None}).status_code == 204
    assert people_editor.assignments_of(lead.person)[0]["reports_to"] is None

    teaching = people_editor.assignment("INSTRUCTOR")
    refused = people_editor.ask(
        "PUT",
        f"/admin/assignments/{teaching.assignment}/reports-to",
        json={"reports_to": str(lead.assignment)},
    )
    assert refused.status_code == 409
    assert refused.json() == {"detail": _text("instructor_is_lms_owned")}
    assert people_editor.assignments_of(teaching.person)[0]["reports_to"] is None


def test_a_person_is_created_and_edited(people_editor: PeopleEditor) -> None:
    created = people_editor.ask(
        "POST", "/admin/people", json={"name": "Dr. Ana Zeller", "category": "Dean"}
    )
    assert created.status_code == 201, created.text
    person = created.json()["person_id"]
    assert people_editor.person_row(person) == {
        "identity_name": "Dr. Ana Zeller",
        "category": "Dean",
    }
    edited = people_editor.ask(
        "PUT", f"/admin/people/{person}", json={"name": "Ana Zeller", "category": "Lead Faculty"}
    )
    assert edited.status_code == 204, edited.text
    assert people_editor.person_row(person) == {
        "identity_name": "Ana Zeller",
        "category": "Lead Faculty",
    }


def test_a_name_with_spaces_at_its_ends_is_refused_and_not_trimmed(
    people_editor: PeopleEditor,
) -> None:
    person = people_editor.person("Bo Adams")
    answer = people_editor.ask(
        "PUT", f"/admin/people/{person}", json={"name": " Bo Adams", "category": "Dean"}
    )
    assert answer.status_code == 422
    assert people_editor.person_row(person)["identity_name"] == "Bo Adams"


def test_a_web_login_is_linked_and_unlinked_and_never_to_two_people(
    people_editor: PeopleEditor,
) -> None:
    first, second = people_editor.person(), people_editor.person()
    subject = {"idp_issuer": "https://idp.e9-06.invalid", "idp_subject": f"s-{uuid4().hex}"}

    def linked(person: object) -> list[dict[str, object]]:
        return people_editor.rows(
            "SELECT idp_subject FROM public.web_login_subject WHERE person_id = CAST(:p AS uuid)",
            p=person,
        )

    assert (
        people_editor.ask("PUT", f"/admin/people/{first}/web-login", json=subject).status_code
        == 204
    )
    assert linked(first) == [{"idp_subject": subject["idp_subject"]}]

    taken = people_editor.ask("PUT", f"/admin/people/{second}/web-login", json=subject)
    assert taken.status_code == 409
    assert taken.json() == {"detail": _text("subject_linked_to_another")}
    assert linked(second) == []

    assert people_editor.ask("DELETE", f"/admin/people/{first}/web-login").status_code == 204
    assert linked(first) == []


def test_the_acting_admin_is_the_sessions_person_whatever_the_request_names(
    people_editor: PeopleEditor,
) -> None:
    """Another admin's id in the query, the path and the body changes nothing about who acts."""
    other = people_editor.other_admin()
    institution = people_editor.scope("CARE")
    answer = people_editor.ask(
        "POST",
        f"/admin/people/{other.person_id}/assignments"
        f"?actor_person_id={other.person_id}&in_actor_person_id={other.person_id}",
        json={
            "role": "CARE",
            "scope_node_id": str(institution),
            "actor_person_id": str(other.person_id),
            "in_actor_person_id": str(other.person_id),
        },
    )
    assert answer.status_code == 201, answer.text
    rows = [row for row in people_editor.audit_about(other.person_id) if row["role"] == "CARE"]
    assert len(rows) == 1, rows
    assert rows[0]["action"] == "ROLE_GRANTED"
    assert rows[0]["actor_person_id"] == people_editor.admin.person_id
    assert rows[0]["subject_person_id"] == other.person_id


def test_an_admin_session_whose_person_is_no_admin_cannot_borrow_one_from_the_request(
    people_editor: PeopleEditor,
) -> None:
    """The control for the test above: the request's admin id would be accepted if it were read."""
    impostor = a_person_holding(
        people_editor.review, "no-admin", assignments=(), landing="ADMIN", at_the_web_door=True
    )
    real = people_editor.admin.person_id
    target = people_editor.person()
    answer = people_editor.ask(
        "POST",
        f"/admin/people/{target}/assignments?actor_person_id={real}",
        json={
            "role": "CARE",
            "scope_node_id": str(people_editor.scope("CARE")),
            "actor_person_id": str(real),
        },
        token=impostor.token,
    )
    assert answer.status_code == 403
    assert answer.json() == {"detail": _text("actor_not_an_admin")}
    assert people_editor.assignments_of(target) == []
