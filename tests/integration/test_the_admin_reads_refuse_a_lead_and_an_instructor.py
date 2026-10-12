"""Every admin read answers a lead's and an instructor's session nothing — E9-14 item 5(b).

The admin's people-graph reads hand out every staff member's name, category,
assignments and mappings (SPEC §6.3), and their CSV exports the same. The E9
boundary invariant-coverage review found the denial asserted only in unmarked
modules (`test_the_people_editor_routes_answer_only_an_admin.py` asks a Care
session; `test_the_people_graph_definers_answer_only_an_admin.py` asks a dean,
a Care holder and a person with no assignment), so CI's isolated §4.1 pass ran
none of it. This module asserts it, marked, for the two sessions most of the
institution holds: a Lead Faculty member's leadership session and a teaching
instructor's launched session.

**Over HTTP**, on the built application as `pulse_app` (`docs/MISTAKES.md`
entries 46 and 47): every `GET` route under `/admin/` is found on the running
application, not listed here, and asked by both sessions. Each must answer 403
with the gate's one sentence and nothing else — the body is compared whole, so
a 403 carrying rows, or a CSV, is red. The admin's own session reading the
tables (200) is the present twin.

**At the database**, on `pulse_app`'s connection: each admin read definer called
with the lead's and the instructor's person key answers zero rows, not an error,
beside the admin's non-empty answer in the same world (ADR 0200).

**Which failure a red is.** The gate and the definers' checks exist on this
branch, so every test is expected **green**.
"""

from typing import Any
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fixtures.people_editor import PeopleEditor
from fixtures.people_graph import READS, PeopleGraphWorld
from fixtures.routing import every_route

from app.copy.admin_people import NOT_ADMIN_ROLE

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

FORBIDDEN = 403

# The admin's own reads, each answering 200 with its table (the present twin).
# Two of them need a role to list for, as the editor's own tests ask them.
ADMIN_READS = (
    "/admin/people",
    "/admin/lead-mappings",
    "/admin/people/export",
    "/admin/lead-mappings/export",
    "/admin/reports-to-options?role=CHAIR",
    "/admin/org-nodes?role=CHAIR",
)


def admin_get_routes(editor: PeopleEditor) -> list[str]:
    """Every `GET` route path under `/admin/` on the running application."""
    application = editor.review.door.door.application
    return sorted(
        {
            route.path
            for route in every_route(application)
            if isinstance(route, APIRoute)
            and route.path.startswith("/admin/")
            and "GET" in route.methods
        }
    )


def concrete(path: str) -> str:
    """The path with each `{parameter}` filled by a fresh uuid."""
    return "/".join(str(uuid4()) if part.startswith("{") else part for part in path.split("/"))


def test_every_admin_read_answers_a_lead_and_an_instructor_403_and_nothing_else(
    people_editor: PeopleEditor,
) -> None:
    """Each `GET /admin/...` route, asked by a lead and by an instructor: 403, the one sentence.

    **The mutations it kills:** a read route without `require_admin` (it answers
    the lead the people table); a gate that admits any leadership session, or
    any staff session; a refusal that still carries data (the body is compared
    whole). **The near miss it spares:** the admin, who reads every table (the
    twin, asserted first so a gate refusing everyone is red).
    """
    editor = people_editor
    review = editor.review
    sessions = {
        "a Lead Faculty session": review.lead.token,
        "an instructor session": review.instructor_token,
    }
    paths = admin_get_routes(editor)

    admitted = {path: editor.ask("GET", path).status_code for path in ADMIN_READS}
    assert set(admitted.values()) == {200}, (
        f"The present twin: the admin's own reads answered {admitted}. Without the admin reading "
        "every table, the refusals below may be a gate that refuses everyone."
    )
    served = {path.split("?")[0] for path in ADMIN_READS}
    assert served <= set(paths), (
        f"The routes found are {paths}, which leave out {sorted(served - set(paths))}; the walk "
        "below would skip a read the admin is served."
    )

    answered: dict[tuple[str, str], tuple[int, Any]] = {}
    for who, token in sessions.items():
        for path in paths:
            response = review.ask("GET", concrete(path), token=token)
            try:
                body: Any = response.json()
            except ValueError:
                body = response.text
            answered[(who, path)] = (response.status_code, body)
    wrong = {
        f"{who} GET {path}": outcome
        for (who, path), outcome in answered.items()
        if outcome != (FORBIDDEN, {"detail": NOT_ADMIN_ROLE})
    }
    assert not wrong, (
        f"These admin reads did not answer 403 with the gate's sentence and nothing else: {wrong}. "
        "SPEC §6.3: the People editor is the admin's."
    )


@pytest.mark.parametrize("function", list(READS))
@pytest.mark.parametrize("holder", ["LEAD_FACULTY", "INSTRUCTOR"])
def test_an_admin_read_definer_answers_a_lead_or_an_instructor_key_zero_rows(
    people_graph: PeopleGraphWorld, function: str, holder: str
) -> None:
    """Each read definer, on `pulse_app`, with a lead's and an instructor's key: zero rows, no error.

    The holder is planted with that one assignment; the admin's answer to the
    same read in the same world is required non-empty, so "zero rows" is not
    what everybody gets. A mapping is planted so the mappings read has a row to
    withhold.

    **The mutation it kills:** a read definer whose admin check admits any live
    assignment, or any leadership one, which hands every staff record to any
    key `pulse_app` passes. **The near miss it spares:** the admin's call.
    """
    world = people_graph
    caller = world.holding_person(holder)
    world.a_mapping(person=world.admin, course=world.a_course())

    _keys, rows, failure = world.read(function, caller)
    _admin_keys, admin_rows, admin_failure = world.read(function, world.admin)

    assert admin_failure is None and admin_rows, (
        f"The present twin: `{function}` answered the admin {len(admin_rows)} rows "
        f"({admin_failure!r}), so an empty answer is what everybody gets."
    )
    assert failure is None, (
        f"`{function}` called with a {holder} key raised {failure!r}; settled (ADR 0200): a "
        "non-admin gets zero rows, not an error."
    )
    assert rows == [], f"`{function}` answered a {holder} key {len(rows)} rows: {rows[:3]}."
