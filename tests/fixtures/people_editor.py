"""The admin's people editor, driven over HTTP on the built application (SPEC §6.3).

`people_editor` is `lead_review`'s world (the built application on `pulse_app`'s
production connection, `docs/MISTAKES.md` entry 46) with one admin session
minted at the web door, and the means to plant people, assignments, courses and
mappings with the bootstrap identity and read rows back.

**Other tests share the database**, so every read the editor answers holds
their people and mappings too. Each test plants its own records and looks only
at those, by key; nothing asserts on a whole table.
"""

from typing import Any, NamedTuple
from uuid import uuid4

import pytest
from sqlalchemy import text

from fixtures.admin_gate import Staff, a_care_holder, an_admin
from fixtures.lead_review import LeadReviewWorld
from fixtures.supervision import ROLE_SCOPE_GRAIN


class Planted(NamedTuple):
    person: Any
    assignment: Any


class PeopleEditor:
    """An admin session, and the planting and reading the editor's tests share."""

    def __init__(self, review: LeadReviewWorld) -> None:
        self.review = review
        self.admin: Staff = an_admin(review)

    # -- requests ----------------------------------------------------------------

    def ask(self, method: str, path: str, *, json: Any = None, token: Any = None) -> Any:
        """One request as the admin (or as `token`), carried as a Bearer header."""
        return self.review.ask(method, path, token=token or self.admin.token, json=json)

    def other_admin(self) -> Staff:
        return an_admin(self.review, "other-admin")

    def care_holder(self) -> Staff:
        return a_care_holder(self.review)

    # -- planting (bootstrap identity, committed) ---------------------------------

    def person(self, name: str | None = None, category: str = "Lead Faculty") -> Any:
        name = name or f"Person {uuid4().hex[:8]}"
        return self.review.web_identity.person(identity_name=name, category=category)

    def scope(self, role: str) -> Any:
        key = self.review.graph.fresh_scope(ROLE_SCOPE_GRAIN[role])
        self.review.rows.commit()
        return key

    def assignment(self, role: str, *, person: Any = None, reports_to: Any = None) -> Planted:
        person = self.person() if person is None else person
        values: dict[str, Any] = {}
        if reports_to is not None:
            values["reports_to"] = reports_to
        row = self.review.graph.assign(role, scope=self.scope(role), person=person, **values)
        self.review.rows.commit()
        return Planted(person, row[self.review.graph.assignment_key])

    def course(self) -> Any:
        return self.scope("LEAD_FACULTY")

    def mapping(self, *, person: Any, course: Any) -> None:
        self.review.graph.lead_mapping(person=person, course=course)
        self.review.rows.commit()

    # -- reading back (bootstrap identity) ---------------------------------------

    def rows(self, statement: str, **values: Any) -> list[dict[str, Any]]:
        session = self.review.rows.session
        session.rollback()
        found = session.execute(text(statement), {k: str(v) for k, v in values.items()})
        return [dict(row) for row in found.mappings()]

    def person_row(self, person: Any) -> dict[str, Any]:
        (row,) = self.rows(
            "SELECT identity_name, category FROM public.person WHERE id = CAST(:p AS uuid)",
            p=person,
        )
        return row

    def lead_of(self, course: Any) -> Any:
        found = self.rows(
            "SELECT person_id FROM public.lead_faculty_mapping WHERE course_id = CAST(:c AS uuid)",
            c=course,
        )
        return found[0]["person_id"] if found else None

    def assignments_of(self, person: Any) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT id, role::text AS role, reports_to FROM public.role_assignment "
            "WHERE person_id = CAST(:p AS uuid) ORDER BY id",
            p=person,
        )

    def audit_about(self, subject: Any) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT action::text AS action, actor_person_id, subject_person_id, role::text AS role "
            "FROM public.audit_log WHERE subject_person_id = CAST(:p AS uuid) "
            "ORDER BY occurred_at, id",
            p=subject,
        )


@pytest.fixture
def people_editor(lead_review: LeadReviewWorld) -> PeopleEditor:
    """`lead_review`'s world with an admin session. Its rows go with `committed_rows`."""
    return PeopleEditor(lead_review)
