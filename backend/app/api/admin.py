"""The admin console's people editor: the People & reporting table and the Lead Faculty mapping table.

SPEC §6.3 gives both tables column sorting, pagination, and CSV import and
export where an import always shows a dry-run diff before applying. A handler
here resolves the session, hands the work to `app.services.people`, and turns
what comes back into an HTTP answer; the shapes are `app.schemas.admin`.

**Every route carries `require_admin`, and every write `csrf_verified_admin`.**
That makes the surface findable by any sweep that walks the routes' dependency
graphs, as the leadership routes are.

**The acting admin is the session's person and nothing else (ADR 0200).** The
definers check that the key they are given holds an `ADMIN` assignment, but they
cannot tell whose key it is. So no route takes an actor from its path, query or
body; each passes `person_of(claims)` and only that. A person id in a path is
the record being changed, never the person changing it.

**Refusals.** The definers' named refusals become one sentence each from
`app.copy.admin_people`: a record that is not there is 404, a session whose
person holds no `ADMIN` assignment is 403, and every other refusal (the record
is in a state that forbids the change) is 409. An import line that cannot be
read or applied is 422 naming the line, and an apply whose dry run is out of date
is 409; neither changes anything.

**Every answer carries `Cache-Control: no-store`**, as the other read paths do.
"""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import csrf_verified_admin, person_of, require_admin
from app.db import get_session
from app.models.identity import AssignmentRole
from app.schemas.admin import (
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    Granted,
    GrantWrite,
    ImportApply,
    ImportFile,
    MappingDiff,
    MappingPage,
    MappingWrite,
    PeopleDiff,
    PeoplePage,
    PersonCreated,
    PersonWrite,
    ReportsToOptions,
    ReportsToWrite,
    WebLoginWrite,
)
from app.services import people
from app.services.people import ImportLineRefusedError, ImportStaleError, PeopleRefusedError
from app.services.session import SessionClaims

router = APIRouter(tags=["admin"])

PEOPLE_PATH = "/admin/people"
PERSON_PATH = f"{PEOPLE_PATH}/{{person_id}}"
GRANT_PATH = f"{PERSON_PATH}/assignments"
WEB_LOGIN_PATH = f"{PERSON_PATH}/web-login"
PEOPLE_EXPORT_PATH = f"{PEOPLE_PATH}/export"
PEOPLE_DRY_RUN_PATH = f"{PEOPLE_PATH}/import/dry-run"
PEOPLE_IMPORT_PATH = f"{PEOPLE_PATH}/import"

ASSIGNMENT_PATH = "/admin/assignments/{assignment_id}"
REPORTS_TO_PATH = f"{ASSIGNMENT_PATH}/reports-to"
REPORTS_TO_OPTIONS_PATH = "/admin/reports-to-options"

MAPPINGS_PATH = "/admin/lead-mappings"
MAPPING_PATH = f"{MAPPINGS_PATH}/{{course_id}}"
MAPPINGS_EXPORT_PATH = f"{MAPPINGS_PATH}/export"
MAPPINGS_DRY_RUN_PATH = f"{MAPPINGS_PATH}/import/dry-run"
MAPPINGS_IMPORT_PATH = f"{MAPPINGS_PATH}/import"

CREATED = 201
NO_CONTENT = 204
NOT_FOUND = 404
FORBIDDEN = 403
CONFLICT = 409
UNPROCESSABLE = 422

NO_STORE = "no-store"
CSV_MEDIA_TYPE = "text/csv; charset=utf-8"
CSV_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {"content": {"text/csv": {"schema": {"type": "string"}}}}
}

# The refusals that are about a record not being there, and the one about who
# is asking. Every other named refusal is a conflict with the record's state.
_NOT_FOUND_KEYS = frozenset(
    {
        "admin_people.no_such_person",
        "admin_people.no_such_assignment",
        "admin_people.no_such_course",
    }
)
_FORBIDDEN_KEYS = frozenset({"admin_people.actor_not_an_admin"})

Page = Query(1, ge=1)
PageSize = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX)
Order = Query("asc")


def _refused(refusal: PeopleRefusedError) -> HTTPException:
    if refusal.key in _NOT_FOUND_KEYS:
        status = NOT_FOUND
    elif refusal.key in _FORBIDDEN_KEYS:
        status = FORBIDDEN
    else:
        status = CONFLICT
    return HTTPException(status_code=status, detail=refusal.text)


def _import_refused(error: ImportLineRefusedError | ImportStaleError) -> HTTPException:
    if isinstance(error, ImportStaleError):
        return HTTPException(status_code=CONFLICT, detail=error.text)
    return HTTPException(status_code=UNPROCESSABLE, detail=error.text)


def _csv(body: str, filename: str) -> Response:
    return Response(
        content=body,
        media_type=CSV_MEDIA_TYPE,
        headers={
            "Cache-Control": NO_STORE,
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# --- The People & reporting table -------------------------------------------


@router.get(PEOPLE_PATH, summary="The people graph, sorted and paged")
def read_people(
    response: Response,
    sort: Literal["name", "category"] = Query("name"),
    order: Literal["asc", "desc"] = Order,
    page: int = Page,
    page_size: int = PageSize,
    claims: SessionClaims = Depends(require_admin),
    session: Session = Depends(get_session),
) -> PeoplePage:
    """Every person, their assignments, and whom each assignment reports to.

    Names sort by last name with titles stripped; category sorts by hierarchy
    rank. A page past the end answers no people and the same total.
    """
    response.headers["Cache-Control"] = NO_STORE
    return people.people_page(
        session,
        actor=person_of(claims),
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


@router.post(PEOPLE_PATH, status_code=CREATED, summary="Add a person")
def add_person(
    write: PersonWrite,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_admin),
    session: Session = Depends(get_session),
) -> PersonCreated:
    response.headers["Cache-Control"] = NO_STORE
    try:
        person_id = people.create_person(
            session, actor=person_of(claims), name=write.name, category=write.category
        )
    except PeopleRefusedError as refusal:
        raise _refused(refusal) from None
    return PersonCreated(person_id=person_id)


@router.put(PERSON_PATH, status_code=NO_CONTENT, summary="Edit a person's name and category")
def edit_person(
    person_id: UUID,
    write: PersonWrite,
    claims: SessionClaims = Depends(csrf_verified_admin),
    session: Session = Depends(get_session),
) -> Response:
    try:
        people.edit_person(
            session,
            actor=person_of(claims),
            person_id=person_id,
            name=write.name,
            category=write.category,
        )
    except PeopleRefusedError as refusal:
        raise _refused(refusal) from None
    return Response(status_code=NO_CONTENT, headers={"Cache-Control": NO_STORE})


@router.post(GRANT_PATH, status_code=CREATED, summary="Grant a person a role")
def grant_role(
    person_id: UUID,
    write: GrantWrite,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_admin),
    session: Session = Depends(get_session),
) -> Granted:
    """Any Pulse-owned role, Care and Admin included, to anyone, the acting admin included.

    A teaching assignment is the roster's, and the definer refuses it.
    """
    response.headers["Cache-Control"] = NO_STORE
    try:
        assignment_id = people.grant_role(
            session,
            actor=person_of(claims),
            person_id=person_id,
            role=write.role,
            scope_node_id=write.scope_node_id,
        )
    except PeopleRefusedError as refusal:
        raise _refused(refusal) from None
    return Granted(assignment_id=assignment_id)


@router.delete(ASSIGNMENT_PATH, status_code=NO_CONTENT, summary="Revoke a role assignment")
def revoke_role(
    assignment_id: UUID,
    claims: SessionClaims = Depends(csrf_verified_admin),
    session: Session = Depends(get_session),
) -> Response:
    """Revoking deletes. An assignment others report to is refused, with how many."""
    try:
        people.revoke_role(session, actor=person_of(claims), assignment_id=assignment_id)
    except PeopleRefusedError as refusal:
        raise _refused(refusal) from None
    return Response(status_code=NO_CONTENT, headers={"Cache-Control": NO_STORE})


@router.put(
    REPORTS_TO_PATH, status_code=NO_CONTENT, summary="Set or clear whom an assignment reports to"
)
def set_reports_to(
    assignment_id: UUID,
    write: ReportsToWrite,
    claims: SessionClaims = Depends(csrf_verified_admin),
    session: Session = Depends(get_session),
) -> Response:
    try:
        people.set_reports_to(
            session,
            actor=person_of(claims),
            assignment_id=assignment_id,
            reports_to=write.reports_to,
        )
    except PeopleRefusedError as refusal:
        raise _refused(refusal) from None
    return Response(status_code=NO_CONTENT, headers={"Cache-Control": NO_STORE})


@router.get(REPORTS_TO_OPTIONS_PATH, summary="The assignments a new assignment may report to")
def read_reports_to_options(
    response: Response,
    role: AssignmentRole,
    claims: SessionClaims = Depends(require_admin),
    session: Session = Depends(get_session),
) -> ReportsToOptions:
    """Only assignments whose role ranks above `role` (ADR 0044)."""
    response.headers["Cache-Control"] = NO_STORE
    return people.reports_to_options(session, actor=person_of(claims), role=role)


@router.put(WEB_LOGIN_PATH, status_code=NO_CONTENT, summary="Link a web-login subject to a person")
def link_web_login(
    person_id: UUID,
    write: WebLoginWrite,
    claims: SessionClaims = Depends(csrf_verified_admin),
    session: Session = Depends(get_session),
) -> Response:
    try:
        people.link_web_login(
            session,
            actor=person_of(claims),
            person_id=person_id,
            idp_issuer=write.idp_issuer,
            idp_subject=write.idp_subject,
        )
    except PeopleRefusedError as refusal:
        raise _refused(refusal) from None
    return Response(status_code=NO_CONTENT, headers={"Cache-Control": NO_STORE})


@router.delete(WEB_LOGIN_PATH, status_code=NO_CONTENT, summary="Unlink a person's web login")
def unlink_web_login(
    person_id: UUID,
    claims: SessionClaims = Depends(csrf_verified_admin),
    session: Session = Depends(get_session),
) -> Response:
    try:
        people.unlink_web_login(session, actor=person_of(claims), person_id=person_id)
    except PeopleRefusedError as refusal:
        raise _refused(refusal) from None
    return Response(status_code=NO_CONTENT, headers={"Cache-Control": NO_STORE})


@router.get(PEOPLE_EXPORT_PATH, response_class=Response, responses=CSV_RESPONSE)
def export_people(
    claims: SessionClaims = Depends(require_admin),
    session: Session = Depends(get_session),
) -> Response:
    """The people as CSV, in the shape the import reads back."""
    return _csv(people.export_people(session, actor=person_of(claims)), "people.csv")


@router.post(PEOPLE_DRY_RUN_PATH, summary="What a people file would change, changing nothing")
def dry_run_people(
    upload: ImportFile,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_admin),
    session: Session = Depends(get_session),
) -> PeopleDiff:
    response.headers["Cache-Control"] = NO_STORE
    try:
        return people.dry_run_people(session, actor=person_of(claims), body=upload.csv)
    except PeopleRefusedError as refusal:
        raise _refused(refusal) from None
    except (ImportLineRefusedError, ImportStaleError) as error:
        raise _import_refused(error) from None


@router.post(PEOPLE_IMPORT_PATH, summary="Apply a people file its dry run approved")
def apply_people(
    upload: ImportApply,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_admin),
    session: Session = Depends(get_session),
) -> PeopleDiff:
    response.headers["Cache-Control"] = NO_STORE
    try:
        return people.apply_people(
            session, actor=person_of(claims), body=upload.csv, digest=upload.digest
        )
    except PeopleRefusedError as refusal:
        raise _refused(refusal) from None
    except (ImportLineRefusedError, ImportStaleError) as error:
        raise _import_refused(error) from None


# --- The Lead Faculty mapping table -----------------------------------------


@router.get(MAPPINGS_PATH, summary="The lead faculty mappings, sorted and paged")
def read_mappings(
    response: Response,
    sort: Literal["name", "course"] = Query("course"),
    order: Literal["asc", "desc"] = Order,
    page: int = Page,
    page_size: int = PageSize,
    claims: SessionClaims = Depends(require_admin),
    session: Session = Depends(get_session),
) -> MappingPage:
    response.headers["Cache-Control"] = NO_STORE
    return people.mappings_page(
        session,
        actor=person_of(claims),
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


@router.put(MAPPING_PATH, status_code=NO_CONTENT, summary="Map a course to a lead")
def map_lead(
    course_id: UUID,
    write: MappingWrite,
    claims: SessionClaims = Depends(csrf_verified_admin),
    session: Session = Depends(get_session),
) -> Response:
    """Replaces any current lead; the unmap and the map commit together."""
    try:
        people.map_lead(
            session, actor=person_of(claims), course_id=course_id, person_id=write.person_id
        )
    except PeopleRefusedError as refusal:
        raise _refused(refusal) from None
    return Response(status_code=NO_CONTENT, headers={"Cache-Control": NO_STORE})


@router.delete(MAPPING_PATH, status_code=NO_CONTENT, summary="Unmap a course's lead")
def unmap_lead(
    course_id: UUID,
    claims: SessionClaims = Depends(csrf_verified_admin),
    session: Session = Depends(get_session),
) -> Response:
    try:
        people.unmap_lead(session, actor=person_of(claims), course_id=course_id)
    except PeopleRefusedError as refusal:
        raise _refused(refusal) from None
    return Response(status_code=NO_CONTENT, headers={"Cache-Control": NO_STORE})


@router.get(MAPPINGS_EXPORT_PATH, response_class=Response, responses=CSV_RESPONSE)
def export_mappings(
    claims: SessionClaims = Depends(require_admin),
    session: Session = Depends(get_session),
) -> Response:
    """The mappings as CSV, in the shape the import reads back."""
    return _csv(people.export_mappings(session, actor=person_of(claims)), "lead-mappings.csv")


@router.post(MAPPINGS_DRY_RUN_PATH, summary="What a mapping file would change, changing nothing")
def dry_run_mappings(
    upload: ImportFile,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_admin),
    session: Session = Depends(get_session),
) -> MappingDiff:
    response.headers["Cache-Control"] = NO_STORE
    try:
        return people.dry_run_mappings(session, actor=person_of(claims), body=upload.csv)
    except PeopleRefusedError as refusal:
        raise _refused(refusal) from None
    except (ImportLineRefusedError, ImportStaleError) as error:
        raise _import_refused(error) from None


@router.post(MAPPINGS_IMPORT_PATH, summary="Apply a mapping file its dry run approved")
def apply_mappings(
    upload: ImportApply,
    response: Response,
    claims: SessionClaims = Depends(csrf_verified_admin),
    session: Session = Depends(get_session),
) -> MappingDiff:
    response.headers["Cache-Control"] = NO_STORE
    try:
        return people.apply_mappings(
            session, actor=person_of(claims), body=upload.csv, digest=upload.digest
        )
    except PeopleRefusedError as refusal:
        raise _refused(refusal) from None
    except (ImportLineRefusedError, ImportStaleError) as error:
        raise _import_refused(error) from None
