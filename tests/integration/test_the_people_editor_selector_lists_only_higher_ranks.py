"""The reports-to selector lists only assignments ranked above the child's role (ADR 0044).

The selector reads `app.services.people.SUPERVISION_CHAIN`; the edge trigger
holds its own copy of the chain inside its function body. The first test reads
the trigger's source from the database and holds the two to one order.
"""

import re

import pytest
from fixtures.people_editor import PeopleEditor
from sqlalchemy import text

from app.services.people import SUPERVISION_CHAIN

pytestmark = pytest.mark.integration

TRIGGER_FUNCTION = "public.role_assignment_refuse_illegal_supervision_edge"


def test_the_selectors_chain_is_the_edge_triggers_chain(people_editor: PeopleEditor) -> None:
    session = people_editor.review.rows.session
    session.rollback()
    source = session.execute(
        text(f"SELECT pg_get_functiondef('{TRIGGER_FUNCTION}'::regproc)")
    ).scalar_one()
    declared = re.search(r"supervision_chain\s+constant[^:]*:=\s*ARRAY\[(.*?)\]", source, re.S)
    assert declared, f"No `supervision_chain` array in {TRIGGER_FUNCTION}'s source."
    trigger_chain = re.findall(r"'([A-Z_]+)'", declared.group(1))
    assert trigger_chain == [role.value for role in SUPERVISION_CHAIN]


def _options(editor: PeopleEditor, role: str) -> list[dict[str, object]]:
    answer = editor.ask("GET", f"/admin/reports-to-options?role={role}")
    assert answer.status_code == 200, answer.text
    return answer.json()["options"]


def test_a_new_lead_is_offered_chairs_and_above_and_a_chair_no_lead(
    people_editor: PeopleEditor,
) -> None:
    planted = {
        role: people_editor.assignment(role).assignment
        for role in ("LEAD_FACULTY", "CHAIR", "ASSISTANT_DEAN", "DEAN", "VP_ACADEMICS", "CARE")
    }
    expectations = {
        "LEAD_FACULTY": {"CHAIR", "ASSISTANT_DEAN", "DEAN", "VP_ACADEMICS"},
        "CHAIR": {"ASSISTANT_DEAN", "DEAN", "VP_ACADEMICS"},
    }
    for child, allowed in expectations.items():
        options = _options(people_editor, child)
        offered_roles = {option["role"] for option in options}
        assert offered_roles <= allowed, f"A new {child} is offered {offered_roles}."
        offered = {option["assignment_id"] for option in options}
        mine = {role for role, key in planted.items() if str(key) in offered}
        assert mine == allowed, f"Of the planted assignments a new {child} is offered {mine}."


def test_care_admin_and_teaching_assignments_are_offered_nothing(
    people_editor: PeopleEditor,
) -> None:
    people_editor.assignment("CHAIR")
    for role in ("CARE", "ADMIN", "INSTRUCTOR"):
        assert _options(people_editor, role) == []
