"""The admin's people editor: the two tables, their writes, and their CSV import (SPEC §6.3).

Every read and every write goes through E9-02's `SECURITY DEFINER` functions in
`app/views_sql/people_graph_v001.sql` (ADR 0200) and `people_graph_v002.sql`. This module never touches
`person`, `role_assignment`, `lead_faculty_mapping` or `web_login_subject`
itself; it orders, pages and diffs what the definers answer, and it turns their
named refusals into the sentences in `app.copy.admin_people`.

**The acting admin is a parameter every function takes, and the caller takes it
from the verified session.** The definers check that the key holds an `ADMIN`
assignment, but they cannot tell whose key it is, so the route is the real
check (ADR 0200). Nothing here reads a request.

**A refusal is translated only when the database named it.** A definer raises
SQLSTATE `P0001` with a copy key as its message; anything else is re-raised,
so a defect here is a 500 rather than a polite refusal blaming the caller.

**The import (ADR 0204).** Each line of a file states one record: a person's
name and category, or a course's lead (a blank lead unmaps it). A record the
file does not name is left as it is. A dry run applies the file inside the
request's transaction, reads the named records back, diffs them against what it
read before, and rolls back. Its digest is a hash over the file and the named
records' before-state, and an apply recomputes it inside a `SERIALIZABLE`
transaction before writing, so an apply makes the dry run's changes or none: if
a named record moved, a concurrent writer collided, or any one line was
refused, the whole file is rolled back. An apply that commits leaves one
`IMPORT_APPLIED` audit row holding its kind and its diff, written by
`admin_record_import` (`people_graph_v002.sql`) in the same transaction; a dry
run leaves none.
"""

import csv
import hashlib
import io
import json
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeVar
from uuid import UUID

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.copy.admin_people import COPY
from app.models.identity import AssignmentRole
from app.models.org import Course, Prefix
from app.schemas.admin import (
    AssignmentLine,
    Category,
    MappingChange,
    MappingDiff,
    MappingLine,
    MappingPage,
    PeopleDiff,
    PeoplePage,
    PersonChange,
    PersonLine,
    PersonName,
    PersonValues,
    ReportsToOption,
    ReportsToOptions,
    UnmappedCourse,
)
from app.services.section_codes import course_label

__all__ = [
    "MAPPING_HEADER",
    "PEOPLE_HEADER",
    "SUPERVISION_CHAIN",
    "ImportLineRefusedError",
    "ImportStaleError",
    "PeopleRefusedError",
    "apply_mappings",
    "apply_people",
    "create_person",
    "dry_run_mappings",
    "dry_run_people",
    "edit_person",
    "export_mappings",
    "export_people",
    "grant_role",
    "link_web_login",
    "map_lead",
    "mappings_page",
    "name_sort_key",
    "people_page",
    "reports_to_options",
    "revoke_role",
    "set_reports_to",
    "unlink_web_login",
    "unmap_lead",
]

# SPEC §2.1's chain, lowest first: the order the edge trigger's
# `supervision_chain` array holds (ADR 0044). The trigger's array lives inside
# a function body no caller can read, so this copy is held to it by
# `tests/integration/test_the_people_editor_selector_lists_only_higher_ranks.py`.
SUPERVISION_CHAIN: tuple[AssignmentRole, ...] = (
    AssignmentRole.INSTRUCTOR,
    AssignmentRole.LEAD_FACULTY,
    AssignmentRole.CHAIR,
    AssignmentRole.ASSISTANT_DEAN,
    AssignmentRole.DEAN,
    AssignmentRole.VP_ACADEMICS,
)

# The categories in hierarchy order, top first, as `design/AdminConsole.dc.html`
# offers them. `person.category` is free text, so a category outside this list
# sorts after every listed one, by its own spelling.
CATEGORY_ORDER: tuple[str, ...] = (
    "VP of Academics",
    "Dean",
    "Assistant Dean",
    "Department Chair",
    "Lead Faculty",
)

# Titles stripped from the front of a name before sorting by last name.
TITLES: frozenset[str] = frozenset(
    {"dr", "prof", "professor", "mr", "mrs", "ms", "mx", "miss", "rev", "sr", "sra"}
)

PEOPLE_HEADER: tuple[str, ...] = ("person_id", "name", "category")
MAPPING_HEADER: tuple[str, ...] = ("course_id", "course", "person_id", "lead")

NAMED_REFUSAL = "P0001"
SERIALIZATION_FAILURE = "40001"

# A spreadsheet runs a cell that starts with one of these as a formula. The
# export writes such a cell, and any cell starting with the escape itself, with
# one `'` in front; the import removes exactly that one.
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
_ESCAPE = "'"

_NAME = TypeAdapter(PersonName)
_CATEGORY = TypeAdapter(Category)

T = TypeVar("T")


class PeopleRefusedError(Exception):
    """A definer refused the write, with the governed sentence for it."""

    def __init__(self, key: str, text: str) -> None:
        super().__init__(key)
        self.key = key
        self.text = text


class ImportLineRefusedError(Exception):
    """One line of an import file was refused, so nothing was imported."""

    def __init__(self, line: int, reason: str) -> None:
        super().__init__(line)
        self.line = line
        self.text = COPY["admin_people.import_line_refused"].text.format(line=line, reason=reason)


class ImportHeaderError(ImportLineRefusedError):
    def __init__(self) -> None:
        super().__init__(1, COPY["admin_people.import_header_wrong"].text)


class ImportStaleError(Exception):
    """The tables changed after the dry run, or a concurrent write collided with the apply."""

    text = COPY["admin_people.import_stale"].text


# ---------------------------------------------------------------------------
# Calling the definers.
# ---------------------------------------------------------------------------


def _sqlstate(error: DBAPIError) -> str | None:
    return getattr(error.orig, "sqlstate", None)


def _translated(error: DBAPIError) -> PeopleRefusedError:
    """The governed refusal a definer raised, or the original error re-raised."""
    diagnostic: Any = getattr(error.orig, "diag", None)
    key: str | None = getattr(diagnostic, "message_primary", None)
    if _sqlstate(error) != NAMED_REFUSAL or key is None or key not in COPY:
        raise error
    entry = COPY[key]
    if key == "admin_people.assignment_has_reports":
        detail = getattr(diagnostic, "message_detail", None) or ""
        if not detail.isdigit():
            raise error
        return PeopleRefusedError(key, entry.text.format(count=int(detail)))
    return PeopleRefusedError(key, entry.text)


def _call(session: Session, statement: str, values: dict[str, Any]) -> Any:
    """One definer call; a named refusal becomes `PeopleRefusedError`. Does not commit."""
    try:
        return session.execute(text(statement), values).scalar()
    except DBAPIError as error:
        if _sqlstate(error) == SERIALIZATION_FAILURE:
            raise ImportStaleError from None
        raise _translated(error) from None


def _key(value: UUID | None) -> str | None:
    return None if value is None else str(value)


def _write(session: Session, statement: str, values: dict[str, Any]) -> Any:
    """One definer call committed on success and rolled back on any failure."""
    try:
        result = _call(session, statement, values)
    except BaseException:
        session.rollback()
        raise
    session.commit()
    return result


_CREATE = "SELECT public.admin_create_person(CAST(:actor AS uuid), :name, :category)"


def create_person(session: Session, *, actor: UUID | None, name: str, category: str) -> UUID:
    created = _write(
        session,
        _CREATE,
        {"actor": _key(actor), "name": name, "category": category},
    )
    return UUID(str(created))


def edit_person(
    session: Session, *, actor: UUID | None, person_id: UUID, name: str, category: str
) -> None:
    _write(session, _EDIT_PERSON, _edit_values(actor, person_id, name, category))


_EDIT_PERSON = (
    "SELECT public.admin_edit_person(CAST(:actor AS uuid), CAST(:person AS uuid), :name, :category)"
)


def _edit_values(actor: UUID | None, person_id: UUID, name: str, category: str) -> dict[str, Any]:
    return {"actor": _key(actor), "person": str(person_id), "name": name, "category": category}


def grant_role(
    session: Session,
    *,
    actor: UUID | None,
    person_id: UUID,
    role: AssignmentRole,
    scope_node_id: UUID,
) -> UUID:
    granted = _write(
        session,
        "SELECT public.admin_grant_role(CAST(:actor AS uuid), CAST(:person AS uuid), "
        "CAST(:role AS public.assignment_role), CAST(:scope AS uuid))",
        {
            "actor": _key(actor),
            "person": str(person_id),
            "role": role.value,
            "scope": str(scope_node_id),
        },
    )
    return UUID(str(granted))


def revoke_role(session: Session, *, actor: UUID | None, assignment_id: UUID) -> None:
    _write(
        session,
        "SELECT public.admin_revoke_role(CAST(:actor AS uuid), CAST(:assignment AS uuid))",
        {"actor": _key(actor), "assignment": str(assignment_id)},
    )


def set_reports_to(
    session: Session, *, actor: UUID | None, assignment_id: UUID, reports_to: UUID | None
) -> None:
    _write(
        session,
        "SELECT public.admin_set_reports_to(CAST(:actor AS uuid), CAST(:assignment AS uuid), "
        "CAST(:parent AS uuid))",
        {"actor": _key(actor), "assignment": str(assignment_id), "parent": _key(reports_to)},
    )


def link_web_login(
    session: Session, *, actor: UUID | None, person_id: UUID, idp_issuer: str, idp_subject: str
) -> None:
    _write(
        session,
        "SELECT public.admin_link_web_login(CAST(:actor AS uuid), CAST(:person AS uuid), "
        ":issuer, :subject)",
        {
            "actor": _key(actor),
            "person": str(person_id),
            "issuer": idp_issuer,
            "subject": idp_subject,
        },
    )


def unlink_web_login(session: Session, *, actor: UUID | None, person_id: UUID) -> None:
    _write(
        session,
        "SELECT public.admin_unlink_web_login(CAST(:actor AS uuid), CAST(:person AS uuid))",
        {"actor": _key(actor), "person": str(person_id)},
    )


_MAP = (
    "SELECT public.admin_map_lead_course(CAST(:actor AS uuid), CAST(:person AS uuid), "
    "CAST(:course AS uuid))"
)
_UNMAP = "SELECT public.admin_unmap_lead_course(CAST(:actor AS uuid), CAST(:course AS uuid))"


def map_lead(session: Session, *, actor: UUID | None, course_id: UUID, person_id: UUID) -> None:
    """Map a course to a lead, replacing any current lead in the same transaction.

    ADR 0200 makes a change of lead an unmap followed by a map, which writes two
    audit rows; both commit together or neither does.
    """
    try:
        current = _mappings(session, actor).get(course_id)
        if current == person_id:
            session.rollback()
            return
        if current is not None:
            _call(session, _UNMAP, {"actor": _key(actor), "course": str(course_id)})
        _call(
            session,
            _MAP,
            {"actor": _key(actor), "person": str(person_id), "course": str(course_id)},
        )
    except BaseException:
        session.rollback()
        raise
    session.commit()


def unmap_lead(session: Session, *, actor: UUID | None, course_id: UUID) -> None:
    _write(session, _UNMAP, {"actor": _key(actor), "course": str(course_id)})


# ---------------------------------------------------------------------------
# Reading the definers.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Assignment:
    id: UUID
    person_id: UUID
    role: AssignmentRole
    scope_node_id: UUID
    reports_to: UUID | None


def _read(session: Session, function: str, actor: UUID | None) -> list[Any]:
    statement = text(f"SELECT * FROM public.{function}(CAST(:actor AS uuid))")  # noqa: S608
    return list(session.execute(statement, {"actor": _key(actor)}).mappings())


def _people(session: Session, actor: UUID | None) -> dict[UUID, Any]:
    return {row["person_id"]: row for row in _read(session, "admin_read_people", actor)}


def _assignments(session: Session, actor: UUID | None) -> list[_Assignment]:
    return [
        _Assignment(
            id=row["assignment_id"],
            person_id=row["person_id"],
            role=AssignmentRole(row["role"]),
            scope_node_id=row["scope_node_id"],
            reports_to=row["reports_to"],
        )
        for row in _read(session, "admin_read_role_assignments", actor)
    ]


def _mappings(session: Session, actor: UUID | None) -> dict[UUID, UUID]:
    """Course to lead, as the mappings definer answers it."""
    return {
        row["course_id"]: row["person_id"]
        for row in _read(session, "admin_read_lead_mappings", actor)
    }


def _course_labels(session: Session, course_ids: Iterable[UUID]) -> dict[UUID, str]:
    wanted = set(course_ids)
    if not wanted:
        return {}
    rows = session.execute(
        select(Course.id, Course.lms_number, Course.lms_title, Prefix.code)
        .join(Prefix, Prefix.id == Course.prefix_id)
        .where(Course.id.in_(wanted))
    ).all()
    return {
        course_id: course_label(prefix_code=code, lms_number=number, lms_title=title)
        for course_id, number, title, code in rows
    }


# ---------------------------------------------------------------------------
# Sorting and paging.
# ---------------------------------------------------------------------------


def name_sort_key(name: str) -> tuple[str, str]:
    """Last name first, with leading titles ("Dr.", "Prof.") stripped (SPEC §6.3)."""
    words = name.split()
    while len(words) > 1 and words[0].rstrip(".").casefold() in TITLES:
        words = words[1:]
    return (words[-1].casefold() if words else "", " ".join(words).casefold())


def _category_sort_key(category: str) -> tuple[int, str]:
    rank = CATEGORY_ORDER.index(category) if category in CATEGORY_ORDER else len(CATEGORY_ORDER)
    return (rank, category.casefold())


def _page(items: Sequence[T], page: int, page_size: int) -> list[T]:
    start = (page - 1) * page_size
    return list(items[start : start + page_size])


PeopleSort = Literal["name", "category"]
MappingSort = Literal["name", "course"]
Order = Literal["asc", "desc"]


def _ordered(items: list[T], key: Callable[[T], Any], order: Order) -> list[T]:
    return sorted(items, key=key, reverse=order == "desc")


def people_page(
    session: Session,
    *,
    actor: UUID | None,
    sort: PeopleSort,
    order: Order,
    page: int,
    page_size: int,
) -> PeoplePage:
    people = _people(session, actor)
    assignments = _assignments(session, actor)
    session.rollback()
    by_id = {assignment.id: assignment for assignment in assignments}
    held: dict[UUID, list[AssignmentLine]] = {person: [] for person in people}
    for assignment in assignments:
        parent = by_id.get(assignment.reports_to) if assignment.reports_to else None
        held.setdefault(assignment.person_id, []).append(
            AssignmentLine(
                assignment_id=assignment.id,
                role=assignment.role,
                scope_node_id=assignment.scope_node_id,
                reports_to=assignment.reports_to,
                reports_to_name=(
                    people[parent.person_id]["identity_name"]
                    if parent and parent.person_id in people
                    else None
                ),
                reports_to_role=parent.role if parent else None,
            )
        )
    lines = [
        PersonLine(
            person_id=person_id,
            name=row["identity_name"],
            category=row["category"],
            web_login_linked=row["idp_issuer"] is not None,
            assignments=held.get(person_id, []),
        )
        for person_id, row in people.items()
    ]
    if sort == "category":
        ordered = _ordered(
            lines,
            lambda line: (_category_sort_key(line.category), str(line.person_id)),
            order,
        )
    else:
        ordered = _ordered(
            lines, lambda line: (name_sort_key(line.name), str(line.person_id)), order
        )
    return PeoplePage(
        total=len(ordered),
        page=page,
        page_size=page_size,
        people=_page(ordered, page, page_size),
    )


def reports_to_options(
    session: Session, *, actor: UUID | None, role: AssignmentRole
) -> ReportsToOptions:
    """The assignments a `role` assignment may report to: those ranked above it.

    ADR 0044's rule, read from `SUPERVISION_CHAIN`. Care and Admin hold no rank
    and report to nobody, and a teaching assignment's edge is the roster's
    (ADR 0200), so each of those is offered nothing.
    """
    if role not in SUPERVISION_CHAIN or role is AssignmentRole.INSTRUCTOR:
        return ReportsToOptions(options=[])
    rank = SUPERVISION_CHAIN.index(role)
    people = _people(session, actor)
    assignments = _assignments(session, actor)
    session.rollback()
    options = [
        ReportsToOption(
            assignment_id=assignment.id,
            person_id=assignment.person_id,
            name=people[assignment.person_id]["identity_name"],
            role=assignment.role,
        )
        for assignment in assignments
        if assignment.role in SUPERVISION_CHAIN
        and SUPERVISION_CHAIN.index(assignment.role) > rank
        and assignment.person_id in people
    ]
    options.sort(
        key=lambda option: (
            SUPERVISION_CHAIN.index(option.role),
            name_sort_key(option.name),
            str(option.assignment_id),
        )
    )
    return ReportsToOptions(options=options)


def _mapping_lines(
    session: Session, mappings: dict[UUID, UUID], people: dict[UUID, Any]
) -> dict[UUID, MappingLine]:
    labels = _course_labels(session, mappings)
    return {
        course_id: MappingLine(
            course_id=course_id,
            course=labels.get(course_id, str(course_id)),
            person_id=person_id,
            name=people[person_id]["identity_name"] if person_id in people else "",
        )
        for course_id, person_id in mappings.items()
    }


def mappings_page(
    session: Session,
    *,
    actor: UUID | None,
    sort: MappingSort,
    order: Order,
    page: int,
    page_size: int,
) -> MappingPage:
    lines = list(
        _mapping_lines(session, _mappings(session, actor), _people(session, actor)).values()
    )
    session.rollback()
    if sort == "course":
        ordered = _ordered(lines, lambda line: (line.course.casefold(), str(line.course_id)), order)
    else:
        ordered = _ordered(
            lines,
            lambda line: (name_sort_key(line.name), line.course.casefold(), str(line.course_id)),
            order,
        )
    return MappingPage(
        total=len(ordered),
        page=page,
        page_size=page_size,
        mappings=_page(ordered, page, page_size),
    )


# ---------------------------------------------------------------------------
# CSV export.
# ---------------------------------------------------------------------------


def _cell(value: str) -> str:
    return _ESCAPE + value if value.startswith((*_FORMULA_STARTS, _ESCAPE)) else value


def _csv(header: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_cell(value) for value in row])
    return out.getvalue()


def export_people(session: Session, *, actor: UUID | None) -> str:
    people = _people(session, actor)
    session.rollback()
    ordered = sorted(
        people.values(),
        key=lambda row: (name_sort_key(row["identity_name"]), str(row["person_id"])),
    )
    return _csv(
        PEOPLE_HEADER,
        ((str(row["person_id"]), row["identity_name"], row["category"]) for row in ordered),
    )


def export_mappings(session: Session, *, actor: UUID | None) -> str:
    lines = _mapping_lines(session, _mappings(session, actor), _people(session, actor))
    session.rollback()
    ordered = sorted(lines.values(), key=lambda line: (line.course.casefold(), str(line.course_id)))
    return _csv(
        MAPPING_HEADER,
        ((str(line.course_id), line.course, str(line.person_id), line.name) for line in ordered),
    )


# ---------------------------------------------------------------------------
# CSV import.
# ---------------------------------------------------------------------------

_MALFORMED = COPY["admin_people.import_line_malformed"].text
_REPEATED = COPY["admin_people.import_key_repeated"].text
_UUID_SHAPE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _uncell(value: str, line: int) -> str:
    """A cell as the export wrote it, unescaped; anything the export would not write is refused."""
    if value.startswith(_ESCAPE):
        inner = value[1:]
        if not inner.startswith((*_FORMULA_STARTS, _ESCAPE)):
            raise ImportLineRefusedError(line, _MALFORMED)
        return inner
    if value.startswith(_FORMULA_STARTS):
        raise ImportLineRefusedError(line, _MALFORMED)
    return value


def _uuid(value: str, line: int) -> UUID:
    if not _UUID_SHAPE.fullmatch(value):
        raise ImportLineRefusedError(line, _MALFORMED)
    return UUID(value)


def _checked(adapter: TypeAdapter[str], value: str, line: int) -> str:
    try:
        return adapter.validate_python(value)
    except ValidationError:
        raise ImportLineRefusedError(line, _MALFORMED) from None


def _rows(body: str, header: Sequence[str]) -> list[tuple[int, list[str]]]:
    """Each data line with its line number (the header is line 1), cells unescaped."""
    try:
        parsed = list(csv.reader(io.StringIO(body, newline=""), strict=True))
    except csv.Error:
        raise ImportLineRefusedError(1, _MALFORMED) from None
    if not parsed or tuple(parsed[0]) != tuple(header):
        raise ImportHeaderError
    rows: list[tuple[int, list[str]]] = []
    for number, cells in enumerate(parsed[1:], start=2):
        if len(cells) != len(header):
            raise ImportLineRefusedError(number, _MALFORMED)
        rows.append((number, [_uncell(cell, number) for cell in cells]))
    return rows


@dataclass(frozen=True)
class _PersonRow:
    line: int
    person_id: UUID | None
    name: str
    category: str


def _people_rows(body: str) -> list[_PersonRow]:
    rows: list[_PersonRow] = []
    seen: set[UUID] = set()
    for line, (person, name, category) in _rows(body, PEOPLE_HEADER):
        person_id = None if person == "" else _uuid(person, line)
        if person_id is not None:
            if person_id in seen:
                raise ImportLineRefusedError(line, _REPEATED)
            seen.add(person_id)
        rows.append(
            _PersonRow(
                line=line,
                person_id=person_id,
                name=_checked(_NAME, name, line),
                category=_checked(_CATEGORY, category, line),
            )
        )
    return rows


def _mapping_rows(body: str) -> dict[UUID, tuple[int, UUID | None]]:
    """Course to (line, lead or `None` to unmap). `course` and `lead` are labels, never read."""
    wanted: dict[UUID, tuple[int, UUID | None]] = {}
    for line, (course, _label, person, _lead) in _rows(body, MAPPING_HEADER):
        course_id = _uuid(course, line)
        person_id = None if person == "" else _uuid(person, line)
        if course_id in wanted:
            raise ImportLineRefusedError(line, _REPEATED)
        wanted[course_id] = (line, person_id)
    return wanted


def _digest(kind: str, body: str, state: Any) -> str:
    payload = json.dumps({"kind": kind, "file": body, "state": state}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _on_line(line: int, session: Session, statement: str, values: dict[str, Any]) -> Any:
    """A definer call for one line; its refusal names the line, except the admin check."""
    try:
        return _call(session, statement, values)
    except PeopleRefusedError as refused:
        if refused.key == "admin_people.actor_not_an_admin":
            raise
        raise ImportLineRefusedError(line, refused.text) from None


def _begin(session: Session, *, applying: bool) -> None:
    """An apply runs `SERIALIZABLE`, so a write landing between its check and its commit fails it."""
    if applying:
        session.connection(execution_options={"isolation_level": "SERIALIZABLE"})


_RECORD_IMPORT = (
    "SELECT public.admin_record_import(CAST(:actor AS uuid), :kind, CAST(:diff AS jsonb))"
)


def _record_import(
    session: Session,
    actor: UUID | None,
    kind: Literal["people", "lead_mappings"],
    diff: PeopleDiff | MappingDiff,
) -> None:
    """The apply's one `IMPORT_APPLIED` audit row (SPEC §8), in its transaction, before its commit.

    The diff recorded is the one the apply answers, without its digest. The
    apply only reaches this point when its digest matched, so that is the diff
    the dry run answered. A failure here fails the apply.
    """
    recorded = diff.model_dump(mode="json", exclude={"digest"})
    values = {"actor": _key(actor), "kind": kind, "diff": json.dumps(recorded)}
    _call(session, _RECORD_IMPORT, values)


def _finish(session: Session, *, applying: bool) -> None:
    if not applying:
        session.rollback()
        return
    try:
        session.commit()
    except DBAPIError as error:
        if _sqlstate(error) == SERIALIZATION_FAILURE:
            raise ImportStaleError from None
        raise


def _import_people(
    session: Session, *, actor: UUID | None, body: str, digest: str | None
) -> PeopleDiff:
    rows = _people_rows(body)
    named = {row.person_id for row in rows if row.person_id is not None}
    applying = digest is not None
    try:
        _begin(session, applying=applying)
        everyone = _people(session, actor)
        before = {person: everyone[person] for person in named if person in everyone}
        # A new person's line is held to the people already bearing its name, so
        # applying the same file twice is refused rather than creating two copies.
        new_names = {row.name for row in rows if row.person_id is None}
        watched = {
            person: row
            for person, row in everyone.items()
            if person in named or row["identity_name"] in new_names
        }
        state = sorted(
            [str(person), row["identity_name"], row["category"]] for person, row in watched.items()
        )
        expected = _digest("people", body, state)
        if applying and digest != expected:
            raise ImportStaleError
        created: list[UUID] = []
        for row in rows:
            if row.person_id is None:
                values = {"actor": _key(actor), "name": row.name, "category": row.category}
                new = _on_line(row.line, session, _CREATE, values)
                created.append(UUID(str(new)))
                continue
            current = before.get(row.person_id)
            if current is not None and (current["identity_name"], current["category"]) == (
                row.name,
                row.category,
            ):
                continue
            edit = _edit_values(actor, row.person_id, row.name, row.category)
            _on_line(row.line, session, _EDIT_PERSON, edit)
        everyone_after = _people(session, actor)
        diff = PeopleDiff(
            digest=expected,
            added=[_values(everyone_after[person]) for person in created],
            changed=[
                PersonChange(
                    person_id=person,
                    before=_values(before[person]),
                    after=_values(everyone_after[person]),
                )
                for person in sorted(before, key=str)
                if _values(before[person]) != _values(everyone_after[person])
            ],
        )
        if applying:
            _record_import(session, actor, "people", diff)
        _finish(session, applying=applying)
    except BaseException:
        session.rollback()
        raise
    return diff


def _values(row: Any) -> PersonValues:
    return PersonValues(name=row["identity_name"], category=row["category"])


def dry_run_people(session: Session, *, actor: UUID | None, body: str) -> PeopleDiff:
    """What the file would add and change, computed by applying it and rolling back."""
    return _import_people(session, actor=actor, body=body, digest=None)


def apply_people(session: Session, *, actor: UUID | None, body: str, digest: str) -> PeopleDiff:
    """Apply the file if its people are as the dry run saw them; all of it or none."""
    return _import_people(session, actor=actor, body=body, digest=digest)


def _import_mappings(
    session: Session, *, actor: UUID | None, body: str, digest: str | None
) -> MappingDiff:
    wanted = _mapping_rows(body)
    applying = digest is not None
    try:
        _begin(session, applying=applying)
        everything = _mappings(session, actor)
        before = {course: everything[course] for course in wanted if course in everything}
        state = sorted([str(course), _key(before.get(course)) or ""] for course in wanted)
        expected = _digest("mappings", body, state)
        if applying and digest != expected:
            raise ImportStaleError
        for course, (line, person) in wanted.items():
            current = before.get(course)
            if current == person:
                continue
            if current is not None:
                values = {"actor": _key(actor), "course": str(course)}
                _on_line(line, session, _UNMAP, values)
            if person is not None:
                values = {"actor": _key(actor), "person": str(person), "course": str(course)}
                _on_line(line, session, _MAP, values)
        everything_after = _mappings(session, actor)
        after = {
            course: everything_after[course] for course in wanted if course in everything_after
        }
        diff = _mapping_diff(session, expected, before, after, _people(session, actor))
        if applying:
            _record_import(session, actor, "lead_mappings", diff)
        _finish(session, applying=applying)
    except BaseException:
        session.rollback()
        raise
    return diff


def _mapping_diff(
    session: Session,
    digest: str,
    before: dict[UUID, UUID],
    after: dict[UUID, UUID],
    people: dict[UUID, Any],
) -> MappingDiff:
    lines_before = _mapping_lines(session, before, people)
    lines_after = _mapping_lines(session, after, people)

    def by_course(line: MappingLine) -> tuple[str, str]:
        return (line.course.casefold(), str(line.course_id))

    added = sorted((lines_after[c] for c in after if c not in before), key=by_course)
    removed = sorted((lines_before[c] for c in before if c not in after), key=by_course)
    changed = sorted(
        (
            MappingChange(before=lines_before[c], after=lines_after[c])
            for c in after
            if c in before and before[c] != after[c]
        ),
        key=lambda change: by_course(change.after),
    )
    note = COPY["admin_people.unmapped_falls_to_chair"].text
    unmapped = [
        UnmappedCourse(
            course_id=line.course_id, course=line.course, note=note.format(course=line.course)
        )
        for line in removed
    ]
    return MappingDiff(
        digest=digest, added=added, changed=changed, removed=removed, unmapped=unmapped
    )


def dry_run_mappings(session: Session, *, actor: UUID | None, body: str) -> MappingDiff:
    """What the file would add, change and remove, computed by applying it and rolling back."""
    return _import_mappings(session, actor=actor, body=body, digest=None)


def apply_mappings(session: Session, *, actor: UUID | None, body: str, digest: str) -> MappingDiff:
    """Apply the file if its courses are mapped as the dry run saw them; all of it or none."""
    return _import_mappings(session, actor=actor, body=body, digest=digest)
