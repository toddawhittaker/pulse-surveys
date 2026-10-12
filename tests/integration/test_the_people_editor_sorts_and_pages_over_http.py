"""The people and mapping tables sort and page over HTTP (SPEC §6.3).

The shared database holds other tests' people, so the order is asserted over
the people this test planted, read out of one page wide enough to hold them in
the whole table's order. The exact slices are
`tests/unit/test_the_people_editor_sorts_and_pages.py`'s.
"""

from typing import Any

import pytest
from fixtures.people_editor import PeopleEditor

pytestmark = pytest.mark.integration


def _all(editor: PeopleEditor, path: str, member: str, **query: str) -> list[dict[str, Any]]:
    """Every row of a table, page by page, in the table's own order."""
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        params = "&".join(f"{k}={v}" for k, v in {**query, "page": page, "page_size": 100}.items())
        answer = editor.ask("GET", f"{path}?{params}")
        assert answer.status_code == 200, answer.text
        body = answer.json()
        rows.extend(body[member])
        if not body[member]:
            return rows
        page += 1


def test_planted_people_come_back_in_last_name_and_rank_order(
    people_editor: PeopleEditor,
) -> None:
    zeller = people_editor.person("Dr. Ana Zeller", "Lead Faculty")
    adams = people_editor.person("Bo Adams", "Department Chair")
    zimmer = people_editor.person("Prof. Cy Zimmer", "Dean")
    mine = {str(zeller), str(adams), str(zimmer)}

    def order(**query: str) -> list[str]:
        rows = _all(people_editor, "/admin/people", "people", **query)
        return list(dict.fromkeys(row["person_id"] for row in rows if row["person_id"] in mine))

    assert order(sort="name") == [str(adams), str(zeller), str(zimmer)]
    assert order(sort="name", order="desc") == [str(zimmer), str(zeller), str(adams)]
    assert order(sort="category") == [str(zimmer), str(adams), str(zeller)]


def test_a_page_past_the_end_answers_no_rows_and_a_total(people_editor: PeopleEditor) -> None:
    people_editor.person()
    for path, member in (("/admin/people", "people"), ("/admin/lead-mappings", "mappings")):
        answer = people_editor.ask("GET", f"{path}?page=100000&page_size=100")
        assert answer.status_code == 200, answer.text
        assert answer.json()[member] == []
        assert answer.json()["total"] >= 0
    assert people_editor.ask("GET", "/admin/people?page=100000").json()["total"] >= 1


def test_one_person_with_two_lead_assignments_shows_both_and_both_chairs(
    people_editor: PeopleEditor,
) -> None:
    lead = people_editor.person("Gil Twohat")
    chairs = [people_editor.assignment("CHAIR") for _ in range(2)]
    for chair in chairs:
        people_editor.assignment("LEAD_FACULTY", person=lead, reports_to=chair.assignment)
    rows = _all(people_editor, "/admin/people", "people", sort="name")
    row = next(row for row in rows if row["person_id"] == str(lead))
    parents = sorted(a["reports_to"] for a in row["assignments"] if a["role"] == "LEAD_FACULTY")
    assert parents == sorted(str(chair.assignment) for chair in chairs)
    names = {people_editor.person_row(chair.person)["identity_name"] for chair in chairs}
    assert {a["reports_to_name"] for a in row["assignments"]} == names
    assert {a["reports_to_role"] for a in row["assignments"]} == {"CHAIR"}


def test_mappings_sort_by_lead_last_name(people_editor: PeopleEditor) -> None:
    zeller = people_editor.person("Dr. Ana Zeller")
    adams = people_editor.person("Bo Adams")
    first, second = people_editor.course(), people_editor.course()
    people_editor.mapping(person=zeller, course=first)
    people_editor.mapping(person=adams, course=second)
    rows = _all(people_editor, "/admin/lead-mappings", "mappings", sort="name")
    wanted = {str(first), str(second)}
    mine = list(dict.fromkeys(row["course_id"] for row in rows if row["course_id"] in wanted))
    assert mine == [str(second), str(first)]
