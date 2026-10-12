"""E9-02 — the people-graph definers, called the way production calls them, and read back.

Four test modules ask the same twelve functions questions, so the calling, the
seeding and the reading live here and each module asserts (`docs/MISTAKES.md`
entry 13). The names below are the orchestrator's settled interface for E9-02
(`e9-02-interface.md` in the build's scratchpad, transcribed): nothing here is
read off the implementation.

**Every call rides `application_session`**, which connects as `pulse_app`
holding only what the migrations grant (`docs/MISTAKES.md` entry 46). A suite run
on the migrating engine would pass every call whether or not `pulse_app` may
execute the function, and would say nothing about the grant.

**Every read-back rides `committed_rows`' session**, the bootstrap identity on a
second connection, after the call's transaction is committed or rolled back. So
"written" and "not written" are statements about committed rows, never about
what the calling transaction can see of its own work.

**A named refusal is SQLSTATE `P0001` with the copy key as the message**
(settled: `RAISE EXCEPTION '<copy key>' USING ERRCODE = 'raise_exception'`). A
missing `EXECUTE` gives 42501 and a broken constraint class 23, so a test that
asserts the code *and* the key cannot be satisfied by either.

**Nothing here decides an answer.** It seeds rows, calls functions and reads rows
back; every expectation is written in the test that makes it. The world is
seeded only with machinery that already exists (`fixtures/supervision.py`,
`fixtures/web_identity.py`), so the fixture builds today and an unbuilt E9-02 is
a FAILED in each test body — a call to a function that does not exist answers
SQLSTATE 42883, which no assertion here accepts — never an ERROR in setup
(`docs/MISTAKES.md` entry 44).
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, NamedTuple
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from fixtures.supervision import ROLE_SCOPE_GRAIN

# ---------------------------------------------------------------------------
# The settled interface, spelled once.
# ---------------------------------------------------------------------------

OWNER_ROLE = "pulse_people_graph_definer"
APPLICATION_ROLE = "pulse_app"

NAMED_REFUSAL = "P0001"
UNDEFINED_FUNCTION = "42883"

# The writes: function name -> the parameters after the acting admin's key, with
# the type each is cast to. The actor is always first (`in_actor_person_id uuid`).
WRITES: dict[str, tuple[tuple[str, str], ...]] = {
    "admin_create_person": (("identity_name", "text"), ("category", "text")),
    "admin_edit_person": (("person", "uuid"), ("identity_name", "text"), ("category", "text")),
    "admin_grant_role": (("person", "uuid"), ("role", "public.assignment_role"), ("scope", "uuid")),
    "admin_revoke_role": (("assignment", "uuid"),),
    "admin_set_reports_to": (("assignment", "uuid"), ("reports_to", "uuid")),
    "admin_map_lead_course": (("person", "uuid"), ("course", "uuid")),
    "admin_unmap_lead_course": (("course", "uuid"),),
    "admin_link_web_login": (("person", "uuid"), ("issuer", "text"), ("subject", "text")),
    "admin_unlink_web_login": (("person", "uuid"),),
}

# The reads and the columns each returns, exactly (settled R1 to R3).
READS: dict[str, tuple[str, ...]] = {
    "admin_read_people": ("person_id", "identity_name", "category", "idp_issuer"),
    "admin_read_role_assignments": (
        "assignment_id",
        "person_id",
        "role",
        "scope_node_id",
        "reports_to",
    ),
    "admin_read_lead_mappings": ("person_id", "course_id"),
}

# The refusal keys (settled §3).
ACTOR_NOT_AN_ADMIN = "admin_people.actor_not_an_admin"
NO_SUCH_PERSON = "admin_people.no_such_person"
NO_SUCH_ASSIGNMENT = "admin_people.no_such_assignment"
INSTRUCTOR_IS_LMS_OWNED = "admin_people.instructor_is_lms_owned"
SCOPE_IS_NOT_THE_ROLES_NODE = "admin_people.scope_is_not_the_roles_node"
ASSIGNMENT_HAS_REPORTS = "admin_people.assignment_has_reports"
EDGE_DOES_NOT_CLIMB = "admin_people.edge_does_not_climb"
NO_SUCH_COURSE = "admin_people.no_such_course"
COURSE_ALREADY_LED = "admin_people.course_already_led"
COURSE_NOT_LED = "admin_people.course_not_led"
SUBJECT_LINKED_TO_ANOTHER = "admin_people.subject_linked_to_another"
PERSON_ALREADY_LINKED = "admin_people.person_already_linked"
PERSON_NOT_LINKED = "admin_people.person_not_linked"

# The audit actions (settled §4); each stored value equals its name.
ROLE_GRANTED = "ROLE_GRANTED"
ROLE_REVOKED = "ROLE_REVOKED"
REPORTS_TO_SET = "REPORTS_TO_SET"
LEAD_MAPPING_CHANGED = "LEAD_MAPPING_CHANGED"
WEB_LOGIN_LINKAGE_CHANGED = "WEB_LOGIN_LINKAGE_CHANGED"

# The scope columns of `role_assignment`, in the order R2's `coalesce` reads them.
SCOPE_COLUMNS = ("institution_id", "college_id", "department_id", "course_id", "section_id")

AUDIT_COLUMNS = (
    "action",
    "actor_person_id",
    "subject_person_id",
    "subject_user_id",
    "case_id",
    "role",
    "scope_node_id",
    # Fix round 1, F2: the new parent of a `REPORTS_TO_SET` row, NULL on every other.
    "parent_assignment_id",
)


def token(value: Any) -> Any:
    """An enum member's name, or the value itself: how a stored role or action is compared."""
    if value is None:
        return None
    return getattr(value, "name", None) or str(value)


# ---------------------------------------------------------------------------
# A call's outcome.
# ---------------------------------------------------------------------------


class Called(NamedTuple):
    """What one call answered: its value, or the database error it raised."""

    value: Any
    failure: Any

    @property
    def sqlstate(self) -> str | None:
        return getattr(getattr(self.failure, "orig", None), "sqlstate", None)

    @property
    def message(self) -> str | None:
        diag = getattr(getattr(self.failure, "orig", None), "diag", None)
        return getattr(diag, "message_primary", None)

    @property
    def detail(self) -> str | None:
        diag = getattr(getattr(self.failure, "orig", None), "diag", None)
        return getattr(diag, "message_detail", None)

    def describe(self) -> str:
        if self.failure is None:
            return f"answered {self.value!r}"
        return (
            f"raised SQLSTATE {self.sqlstate!r} with message {self.message!r} and detail "
            f"{self.detail!r} ({self.failure.orig!r})"
        )


class Prepared(NamedTuple):
    """One write set up to be made: the function, its parameters, and how its effect is read."""

    function: str
    params: dict[str, Any]
    observe: Callable[[], Any]
    audited: bool


# ---------------------------------------------------------------------------
# The world.
# ---------------------------------------------------------------------------


class PeopleGraphWorld:
    """An admin, three non-admins, and the means to call the definers and read rows back."""

    def __init__(
        self,
        rows: Any,
        web_identity: Any,
        application_session: Any,
        migrated_engine: Any,
    ) -> None:
        self.rows = rows
        self.web_identity = web_identity
        self.app = application_session
        self.engine = migrated_engine
        self.graph = rows.graph
        self.admin = self.holding_person("ADMIN")
        self.dean = self.holding_person("DEAN")
        self.care = self.holding_person("CARE")
        self.nobody = self.a_person()
        self.category = self.person_row(self.admin)["category"]

    # -- seeding (bootstrap identity, committed) -------------------------------

    def a_person(self) -> Any:
        return self.web_identity.person()

    def scope(self, role: str) -> Any:
        """A scope node for `role`: the one institution, or a node of the role's grain of its own."""
        grain = ROLE_SCOPE_GRAIN[role]
        key = self.graph.fresh_scope(grain)
        self.rows.commit()
        return key

    def assignment(self, role: str, *, person: Any = None, reports_to: Any = None) -> Any:
        """One committed `role_assignment` at a scope of its own; its id."""
        values: dict[str, Any] = {}
        if reports_to is not None:
            values["reports_to"] = reports_to
        row = self.graph.assign(
            role,
            scope=self.scope(role),
            person=self.a_person() if person is None else person,
            **values,
        )
        self.rows.commit()
        return row[self.graph.assignment_key]

    def holding_person(self, role: str) -> Any:
        person = self.a_person()
        self.assignment(role, person=person)
        return person

    def a_course(self) -> Any:
        key = self.graph.fresh_scope("course")
        self.rows.commit()
        return key

    def a_mapping(self, *, person: Any, course: Any) -> None:
        self.graph.lead_mapping(person=person, course=course)
        self.rows.commit()

    def a_linkage(self, *, person: Any, subject: str | None = None) -> str:
        subject = subject or f"e9-02-subject-{uuid4().hex}"
        self.web_identity.link_web_subject(
            issuer="https://e9-02-issuer.invalid", subject=subject, person_id=person
        )
        return subject

    # -- calling (as `pulse_app`) ----------------------------------------------

    def call(self, function: str, actor: Any, **params: Any) -> Called:
        """One call of a write definer as `pulse_app`; committed if it succeeded."""
        signature = WRITES[function]
        arguments = ["CAST(:actor AS uuid)"] + [
            f"CAST(:{name} AS {cast})" for name, cast in signature
        ]
        statement = f"SELECT public.{function}({', '.join(arguments)})"
        values = {"actor": None if actor is None else str(actor)}
        for name, _cast in signature:
            value = params[name]
            values[name] = None if value is None else str(value)
        return self._run(statement, values, scalar=True)

    def read(self, function: str, actor: Any) -> tuple[list[str], list[dict[str, Any]], Any]:
        """One call of a read definer as `pulse_app`: (column names, rows, failure)."""
        statement = f"SELECT * FROM public.{function}(CAST(:actor AS uuid))"  # noqa: S608
        try:
            result = self.app.execute(
                text(statement), {"actor": None if actor is None else str(actor)}
            )
            keys = list(result.keys())
            rows = [dict(row) for row in result.mappings()]
        except DatabaseError as failure:
            self.app.rollback()
            return [], [], failure
        self.app.rollback()
        return keys, rows, None

    def _run(self, statement: str, values: dict[str, Any], *, scalar: bool) -> Called:
        try:
            value = self.app.execute(text(statement), values).scalar() if scalar else None
        except DatabaseError as failure:
            self.app.rollback()
            return Called(None, failure)
        self.app.commit()
        return Called(value, None)

    def prepare(self, function: str) -> Prepared:
        """A fresh target for `function`, and the reader of its effect (see `_PREPARERS`)."""
        return _PREPARERS[function](self)

    # -- reading back (bootstrap identity, second connection) ------------------

    def _rows(self, statement: str, values: dict[str, Any]) -> list[dict[str, Any]]:
        self.rows.session.rollback()
        found = self.rows.session.execute(text(statement), values).mappings().all()
        return [dict(row) for row in found]

    def person_row(self, person: Any) -> dict[str, Any]:
        found = self._rows(
            "SELECT id, identity_name, category FROM public.person WHERE id = CAST(:p AS uuid)",
            {"p": str(person)},
        )
        assert len(found) == 1, f"Person {person} is found {len(found)} times. A broken world."
        return found[0]

    def people_named(self, name: str) -> int:
        return len(self._rows("SELECT id FROM public.person WHERE identity_name = :n", {"n": name}))

    def assignments_of(self, person: Any) -> list[dict[str, Any]]:
        columns = ", ".join(("id", "person_id", "role", "reports_to", *SCOPE_COLUMNS))
        return self._rows(
            f"SELECT {columns} FROM public.role_assignment "  # noqa: S608
            "WHERE person_id = CAST(:p AS uuid) ORDER BY id",
            {"p": str(person)},
        )

    def assignment_row(self, assignment: Any) -> dict[str, Any] | None:
        columns = ", ".join(("id", "person_id", "role", "reports_to", *SCOPE_COLUMNS))
        found = self._rows(
            f"SELECT {columns} FROM public.role_assignment "  # noqa: S608
            "WHERE id = CAST(:a AS uuid)",
            {"a": str(assignment)},
        )
        return found[0] if found else None

    def reports_to_of(self, assignment: Any) -> Any:
        row = self.assignment_row(assignment)
        assert row is not None, f"Assignment {assignment} is not there. A broken world."
        return row["reports_to"]

    def mappings_of_course(self, course: Any) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT person_id, course_id FROM public.lead_faculty_mapping "
            "WHERE course_id = CAST(:c AS uuid)",
            {"c": str(course)},
        )

    def linkages_of(self, person: Any) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT idp_issuer, idp_subject, person_id FROM public.web_login_subject "
            "WHERE person_id = CAST(:p AS uuid)",
            {"p": str(person)},
        )

    def linkages_of_subject(self, subject: str) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT idp_issuer, idp_subject, person_id FROM public.web_login_subject "
            "WHERE idp_subject = :s",
            {"s": subject},
        )

    def audit_rows(self, actor: Any) -> list[dict[str, Any]]:
        """Every `audit_log` row naming `actor` as the actor, with the settled columns."""
        if actor is None:
            return []
        return self._rows(
            f"SELECT {', '.join(AUDIT_COLUMNS)} FROM public.audit_log "  # noqa: S608
            "WHERE actor_person_id = CAST(:a AS uuid) ORDER BY occurred_at, id",
            {"a": str(actor)},
        )

    def scope_node_of(self, row: dict[str, Any]) -> Any:
        return next((row[column] for column in SCOPE_COLUMNS if row[column] is not None), None)

    # -- the planted audit failure ---------------------------------------------

    @contextmanager
    def audit_insert_fails_for(self, actor: Any) -> Iterator[tuple[str, str]]:
        """A committed `BEFORE INSERT` trigger on `audit_log` that raises for `actor`'s rows.

        Yields the `(sqlstate, message)` it raises. It fires only for rows naming
        this world's own actor, so nothing else that writes the audit log is
        touched, and it is dropped however the block ends. The trigger function
        is the test's own, created and dropped by the bootstrap identity; a
        trigger fires whatever role inserts, so the definer's owner needs no
        privilege on it.
        """
        suffix = uuid4().hex[:12]
        function = f"e9_02_planted_audit_failure_{suffix}"
        trigger = f"e9_02_planted_audit_failure_{suffix}"
        sqlstate, message = PLANTED_SQLSTATE, f"e9-02 planted audit failure {suffix}"
        # No open transaction may hold a lock on `audit_log` while the trigger is created.
        self.rows.session.rollback()
        self.app.rollback()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    f"CREATE FUNCTION public.{function}() RETURNS trigger LANGUAGE plpgsql AS $$ "
                    f"BEGIN IF NEW.actor_person_id = '{actor}'::uuid THEN "
                    f"RAISE EXCEPTION '{message}' USING ERRCODE = '{sqlstate}'; END IF; "
                    "RETURN NEW; END $$"
                )
            )
            connection.execute(text(f"REVOKE ALL ON FUNCTION public.{function}() FROM PUBLIC"))
            connection.execute(
                text(
                    f"CREATE TRIGGER {trigger} BEFORE INSERT ON public.audit_log "
                    f"FOR EACH ROW EXECUTE FUNCTION public.{function}()"
                )
            )
        try:
            yield sqlstate, message
        finally:
            self.rows.session.rollback()
            self.app.rollback()
            with self.engine.begin() as connection:
                connection.execute(text(f"DROP TRIGGER IF EXISTS {trigger} ON public.audit_log"))
                connection.execute(text(f"DROP FUNCTION IF EXISTS public.{function}()"))


# A SQLSTATE nothing in PostgreSQL or this project raises, so a call that fails
# with it failed at the planted trigger and nowhere else. Class `E9` is unused by
# PostgreSQL's catalogue of codes.
PLANTED_SQLSTATE = "E9002"


# ---------------------------------------------------------------------------
# One fresh target per write. Each answers a reader the admin's call must change
# and a refused call must leave alone.
# ---------------------------------------------------------------------------


def _create_person(world: PeopleGraphWorld) -> Prepared:
    name = f"E9-02 Created Person {uuid4().hex[:8]}"
    return Prepared(
        "admin_create_person",
        {"identity_name": name, "category": world.category},
        lambda: world.people_named(name),
        audited=False,
    )


def _edit_person(world: PeopleGraphWorld) -> Prepared:
    target = world.a_person()
    name = f"E9-02 Edited Person {uuid4().hex[:8]}"
    return Prepared(
        "admin_edit_person",
        {"person": target, "identity_name": name, "category": world.category},
        lambda: world.person_row(target)["identity_name"],
        audited=False,
    )


def _grant_role(world: PeopleGraphWorld) -> Prepared:
    target = world.a_person()
    scope = world.scope("DEAN")
    return Prepared(
        "admin_grant_role",
        {"person": target, "role": "DEAN", "scope": scope},
        lambda: len(world.assignments_of(target)),
        audited=True,
    )


def _revoke_role(world: PeopleGraphWorld) -> Prepared:
    assignment = world.assignment("DEAN")
    return Prepared(
        "admin_revoke_role",
        {"assignment": assignment},
        lambda: world.assignment_row(assignment) is not None,
        audited=True,
    )


def _set_reports_to(world: PeopleGraphWorld) -> Prepared:
    child = world.assignment("CHAIR")
    parent = world.assignment("DEAN")
    return Prepared(
        "admin_set_reports_to",
        {"assignment": child, "reports_to": parent},
        lambda: world.reports_to_of(child),
        audited=True,
    )


def _map_lead_course(world: PeopleGraphWorld) -> Prepared:
    course = world.a_course()
    person = world.a_person()
    # E9-14 item 2: a course is mapped only to a person holding a `LEAD_FACULTY`
    # assignment, so the target is given one; otherwise the admin's map would be
    # refused for a reason the tests using this preparer are not about.
    world.assignment("LEAD_FACULTY", person=person)
    return Prepared(
        "admin_map_lead_course",
        {"person": person, "course": course},
        lambda: len(world.mappings_of_course(course)),
        audited=True,
    )


def _unmap_lead_course(world: PeopleGraphWorld) -> Prepared:
    course = world.a_course()
    world.a_mapping(person=world.a_person(), course=course)
    return Prepared(
        "admin_unmap_lead_course",
        {"course": course},
        lambda: len(world.mappings_of_course(course)),
        audited=True,
    )


def _link_web_login(world: PeopleGraphWorld) -> Prepared:
    person = world.a_person()
    return Prepared(
        "admin_link_web_login",
        {
            "person": person,
            "issuer": "https://e9-02-issuer.invalid",
            "subject": f"e9-02-subject-{uuid4().hex}",
        },
        lambda: len(world.linkages_of(person)),
        audited=True,
    )


def _unlink_web_login(world: PeopleGraphWorld) -> Prepared:
    person = world.a_person()
    world.a_linkage(person=person)
    return Prepared(
        "admin_unlink_web_login",
        {"person": person},
        lambda: len(world.linkages_of(person)),
        audited=True,
    )


_PREPARERS: dict[str, Callable[[PeopleGraphWorld], Prepared]] = {
    "admin_create_person": _create_person,
    "admin_edit_person": _edit_person,
    "admin_grant_role": _grant_role,
    "admin_revoke_role": _revoke_role,
    "admin_set_reports_to": _set_reports_to,
    "admin_map_lead_course": _map_lead_course,
    "admin_unmap_lead_course": _unmap_lead_course,
    "admin_link_web_login": _link_web_login,
    "admin_unlink_web_login": _unlink_web_login,
}

AUDITED_WRITES = tuple(
    name for name in WRITES if name not in {"admin_create_person", "admin_edit_person"}
)


@pytest.fixture
def people_graph(
    committed_rows: Any,
    web_identity: Any,
    application_session: Any,
    migrated_engine: Any,
) -> PeopleGraphWorld:
    """An admin, a dean, a Care holder and a person with no assignment, committed.

    Built from existing machinery only, so it builds before E9-02 lands. The
    rows are removed by `committed_rows`' diff at teardown, including every row
    a definer wrote on `pulse_app`'s connection.
    """
    return PeopleGraphWorld(committed_rows, web_identity, application_session, migrated_engine)
