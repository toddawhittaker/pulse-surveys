"""CSV import with a dry run that changes nothing, and an apply that is exactly the dry run (ADR 0204).

SPEC §6.3: "CSV import/export where import always shows a dry-run diff before
applying", and SPEC §2.1's diff: mappings added, changed, and a course
"unmapped, falls to chair". Each file names only this test's own records, and
every record an import touches was planted by the fixture rather than by an
earlier import (`docs/MISTAKES.md` entry 31).
"""

import csv
import io
from typing import Any
from uuid import uuid4

import pytest
from fixtures.people_editor import PeopleEditor

from app.copy.admin_people import COPY
from app.services.people import MAPPING_HEADER, PEOPLE_HEADER

pytestmark = pytest.mark.integration

MAPPINGS = "/admin/lead-mappings"
PEOPLE = "/admin/people"
NO_DIGEST = "0" * 64


def _text(key: str, **values: object) -> str:
    return COPY[f"admin_people.{key}"].text.format(**values)


def _csv(header: tuple[str, ...], rows: list[list[str]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue()


def _exported(editor: PeopleEditor, path: str, keys: set[str]) -> list[list[str]]:
    """The export's rows whose first cell is one of `keys`."""
    answer = editor.ask("GET", f"{path}/export")
    assert answer.status_code == 200, answer.text
    assert answer.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(answer.text)))
    return [row for row in rows[1:] if row[0] in keys]


def _dry_run(editor: PeopleEditor, path: str, body: str) -> Any:
    return editor.ask("POST", f"{path}/import/dry-run", json={"csv": body})


def _apply(editor: PeopleEditor, path: str, body: str, digest: str) -> Any:
    return editor.ask("POST", f"{path}/import", json={"csv": body, "digest": digest})


class _Mapped:
    """Three leads and four courses; the first three courses mapped one to each lead."""

    def __init__(self, editor: PeopleEditor) -> None:
        self.editor = editor
        self.leads = [editor.person(f"Lead {name} {uuid4().hex[:6]}") for name in "ABC"]
        self.courses = [editor.course() for _ in range(4)]
        for lead, course in zip(self.leads, self.courses, strict=False):
            editor.mapping(person=lead, course=course)

    def state(self) -> list[Any]:
        return [self.editor.lead_of(course) for course in self.courses]

    def audit(self) -> list[list[dict[str, Any]]]:
        return [self.editor.audit_about(lead) for lead in self.leads]

    def exported(self) -> list[list[str]]:
        rows = _exported(self.editor, MAPPINGS, {str(course) for course in self.courses})
        assert len(rows) == 3, f"The export holds {len(rows)} of the three planted mappings."
        return sorted(rows, key=lambda row: [str(c) for c in self.courses].index(row[0]))

    def edited(self) -> str:
        """Course 1 to lead B, course 2 unmapped, course 3 kept, course 4 mapped to lead A."""
        rows = self.exported()
        a, b, _c = (str(lead) for lead in self.leads)
        rows[0][2] = b
        rows[1][2] = ""
        rows.append([str(self.courses[3]), "label", a, "label"])
        return _csv(MAPPING_HEADER, rows)


def test_reimporting_an_export_answers_an_empty_diff(people_editor: PeopleEditor) -> None:
    world = _Mapped(people_editor)
    answer = _dry_run(people_editor, MAPPINGS, _csv(MAPPING_HEADER, world.exported()))
    assert answer.status_code == 200, answer.text
    diff = answer.json()
    assert (diff["added"], diff["changed"], diff["removed"], diff["unmapped"]) == ([], [], [], [])


def test_the_dry_run_answers_the_diff_and_changes_nothing(people_editor: PeopleEditor) -> None:
    world = _Mapped(people_editor)
    before, audit_before = world.state(), world.audit()
    answer = _dry_run(people_editor, MAPPINGS, world.edited())
    assert answer.status_code == 200, answer.text
    diff = answer.json()
    c1, c2, _c3, c4 = (str(course) for course in world.courses)
    a, b, _c = (str(lead) for lead in world.leads)
    assert [(row["course_id"], row["person_id"]) for row in diff["added"]] == [(c4, a)]
    assert [
        (change["before"]["person_id"], change["after"]["person_id"]) for change in diff["changed"]
    ] == [(a, b)]
    assert diff["changed"][0]["after"]["course_id"] == c1
    assert [(row["course_id"], row["person_id"]) for row in diff["removed"]] == [(c2, b)]
    (unmapped,) = diff["unmapped"]
    assert unmapped["course_id"] == c2
    assert unmapped["note"] == _text("unmapped_falls_to_chair", course=unmapped["course"])
    assert world.state() == before
    assert world.audit() == audit_before


def test_the_apply_makes_exactly_the_dry_runs_changes(people_editor: PeopleEditor) -> None:
    world = _Mapped(people_editor)
    body = world.edited()
    dry = _dry_run(people_editor, MAPPINGS, body).json()
    applied = _apply(people_editor, MAPPINGS, body, dry["digest"])
    assert applied.status_code == 200, applied.text
    assert applied.json() == dry
    a, b, c = world.leads
    assert world.state() == [b, None, c, a]


def test_an_apply_after_the_tables_moved_is_refused_and_changes_nothing(
    people_editor: PeopleEditor,
) -> None:
    world = _Mapped(people_editor)
    body = world.edited()
    dry = _dry_run(people_editor, MAPPINGS, body).json()
    people_editor.mapping(person=world.leads[2], course=world.courses[3])
    moved = world.state()
    refused = _apply(people_editor, MAPPINGS, body, dry["digest"])
    assert refused.status_code == 409
    assert refused.json() == {"detail": _text("import_stale")}
    assert world.state() == moved


def test_a_file_with_one_unreadable_line_applies_nothing_and_names_the_line(
    people_editor: PeopleEditor,
) -> None:
    world = _Mapped(people_editor)
    rows = world.exported()
    rows[0][2] = str(world.leads[1])
    rows[2][2] = rows[2][2].upper()
    body = _csv(MAPPING_HEADER, rows)
    before = world.state()
    expected = _text("import_line_refused", line=4, reason=_text("import_line_malformed"))
    for answer in (
        _dry_run(people_editor, MAPPINGS, body),
        _apply(people_editor, MAPPINGS, body, NO_DIGEST),
    ):
        assert answer.status_code == 422
        assert answer.json() == {"detail": expected}
    assert world.state() == before


def test_a_line_the_database_refuses_rolls_back_the_lines_before_it(
    people_editor: PeopleEditor,
) -> None:
    world = _Mapped(people_editor)
    rows = world.exported()
    rows[0][2] = str(world.leads[1])
    rows.append([str(uuid4()), "label", str(world.leads[0]), "label"])
    body = _csv(MAPPING_HEADER, rows)
    before = world.state()
    answer = _dry_run(people_editor, MAPPINGS, body)
    assert answer.status_code == 422
    assert answer.json() == {
        "detail": _text("import_line_refused", line=5, reason=_text("no_such_course"))
    }
    assert world.state() == before


def test_a_file_without_the_exported_header_is_refused(people_editor: PeopleEditor) -> None:
    world = _Mapped(people_editor)
    body = _csv(("course_id", "person_id"), [[str(world.courses[0]), str(world.leads[1])]])
    answer = _dry_run(people_editor, MAPPINGS, body)
    assert answer.status_code == 422
    assert answer.json() == {
        "detail": _text("import_line_refused", line=1, reason=_text("import_header_wrong"))
    }


def test_a_people_import_adds_and_changes_after_its_dry_run(people_editor: PeopleEditor) -> None:
    tag = uuid4().hex[:8]
    kept = people_editor.person(f"Bo Adams {tag}", "Dean")
    edited = people_editor.person(f"=Formula {tag}", "Dean")
    rows = _exported(people_editor, PEOPLE, {str(kept), str(edited)})
    assert sorted(row[1] for row in rows) == sorted([f"'=Formula {tag}", f"Bo Adams {tag}"])

    unchanged = _dry_run(people_editor, PEOPLE, _csv(PEOPLE_HEADER, rows)).json()
    assert (unchanged["added"], unchanged["changed"]) == ([], [])

    for row in rows:
        if row[0] == str(edited):
            row[2] = "Lead Faculty"
    rows.append(["", f"New Person {tag}", "Department Chair"])
    body = _csv(PEOPLE_HEADER, rows)
    dry = _dry_run(people_editor, PEOPLE, body)
    assert dry.status_code == 200, dry.text
    diff = dry.json()
    assert diff["added"] == [{"name": f"New Person {tag}", "category": "Department Chair"}]
    assert [change["person_id"] for change in diff["changed"]] == [str(edited)]
    assert diff["changed"][0]["after"] == {"name": f"=Formula {tag}", "category": "Lead Faculty"}
    assert people_editor.person_row(edited)["category"] == "Dean"
    named_new = "SELECT id FROM public.person WHERE identity_name = :n"
    assert people_editor.rows(named_new, n=f"New Person {tag}") == []

    applied = _apply(people_editor, PEOPLE, body, diff["digest"])
    assert applied.status_code == 200, applied.text
    assert applied.json()["changed"] == diff["changed"]
    assert people_editor.person_row(edited)["category"] == "Lead Faculty"
    assert people_editor.person_row(kept) == {
        "identity_name": f"Bo Adams {tag}",
        "category": "Dean",
    }
    assert len(people_editor.rows(named_new, n=f"New Person {tag}")) == 1

    replayed = _apply(people_editor, PEOPLE, body, diff["digest"])
    assert replayed.status_code == 409
    assert len(people_editor.rows(named_new, n=f"New Person {tag}")) == 1


def test_a_file_of_new_people_alone_is_not_applied_twice(people_editor: PeopleEditor) -> None:
    name = f"Only New {uuid4().hex[:8]}"
    body = _csv(PEOPLE_HEADER, [["", name, "Dean"]])
    digest = _dry_run(people_editor, PEOPLE, body).json()["digest"]
    assert _apply(people_editor, PEOPLE, body, digest).status_code == 200
    assert _apply(people_editor, PEOPLE, body, digest).status_code == 409
    assert (
        len(people_editor.rows("SELECT id FROM public.person WHERE identity_name = :n", n=name))
        == 1
    )


def test_a_people_line_with_a_padded_name_is_refused_and_not_trimmed(
    people_editor: PeopleEditor,
) -> None:
    person = people_editor.person(f"Bo Adams {uuid4().hex[:8]}", "Dean")
    body = _csv(PEOPLE_HEADER, [[str(person), " Bo Adams", "Dean"]])
    answer = _dry_run(people_editor, PEOPLE, body)
    assert answer.status_code == 422
    assert answer.json() == {
        "detail": _text("import_line_refused", line=2, reason=_text("import_line_malformed"))
    }
