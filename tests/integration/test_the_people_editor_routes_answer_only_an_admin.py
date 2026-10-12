"""Every people-editor route answers no session 401 and a non-admin session 403 (SPEC §6.3).

Each route under `/admin/` is found on the running application, not listed
here, so a route added later is asked the same two questions. Beside the
refusals, the admin's own session gets past the gate on every read, so a gate
refusing everything is red here.
"""

from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fixtures.people_editor import PeopleEditor
from fixtures.routing import dependencies_of, every_route

from app.copy.admin_people import NOT_ADMIN, NOT_ADMIN_ROLE

pytestmark = pytest.mark.integration


def _admin_routes(editor: PeopleEditor) -> list[tuple[str, str, APIRoute]]:
    application = editor.review.door.door.application
    found = [
        (method, route.path, route)
        for route in every_route(application)
        if isinstance(route, APIRoute) and route.path.startswith("/admin/")
        for method in sorted(route.methods)
    ]
    assert len(found) == 18, f"{len(found)} admin routes were found, not 18: {found}."
    return found


def _concrete(path: str) -> str:
    """The path with each `{parameter}` filled by a fresh uuid."""
    parts = [str(uuid4()) if part.startswith("{") else part for part in path.split("/")]
    return "/".join(parts)


def test_every_admin_route_declares_the_admin_gate_and_every_write_the_csrf_one(
    people_editor: PeopleEditor,
) -> None:
    # Imported after the application is built, which reloads the app modules.
    from app.api.deps import csrf_verified_admin, require_admin

    for method, path, route in _admin_routes(people_editor):
        gates = set(dependencies_of(route.dependant))
        assert require_admin in gates, f"{method} {path} does not carry `require_admin`."
        if method != "GET":
            assert (
                csrf_verified_admin in gates
            ), f"{method} {path} writes and does not carry `csrf_verified_admin`."


def test_every_admin_route_refuses_no_session_401_and_a_care_session_403(
    people_editor: PeopleEditor,
) -> None:
    care = people_editor.care_holder()
    for method, path, _route in _admin_routes(people_editor):
        url = _concrete(path)
        body = {} if method != "GET" else None
        missing = people_editor.review.ask(method, url, token=None, json=body)
        assert missing.status_code == 401, f"{method} {path} answered {missing.status_code}."
        assert missing.json() == {"detail": NOT_ADMIN}
        other_role = people_editor.review.ask(method, url, token=care.token, json=body)
        assert (
            other_role.status_code == 403
        ), f"{method} {path} answered a Care session {other_role.status_code}."
        assert other_role.json() == {"detail": NOT_ADMIN_ROLE}


def test_the_admin_session_reads_every_table(people_editor: PeopleEditor) -> None:
    for path in (
        "/admin/people",
        "/admin/lead-mappings",
        "/admin/people/export",
        "/admin/lead-mappings/export",
        "/admin/reports-to-options?role=CHAIR",
    ):
        answer = people_editor.ask("GET", path)
        assert answer.status_code == 200, f"{path}: {answer.status_code} {answer.text}"
        assert answer.headers["cache-control"] == "no-store"
