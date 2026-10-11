"""No refusal carries a name — E7-01, done-when 4, and SPEC §4.1.

> A refused read, at the service and over HTTP, carries no staff name in its body,
> its headers or its log line. The test plants a distinctive name and searches
> every refusal for it.

**The name is planted and then shown to be reachable** before any refusal is
searched (`docs/MISTAKES.md` entry 3): at the service, the lead of the course is
answered the planted name in the same world; over HTTP, the enrolled student's own
read carries it. A search that finds nothing in a refusal means something only
when the same name is demonstrably on the other side of the door.

**Every log line is captured**, at `DEBUG`, from every logger (`caplog`), and the
capture is cleared between the twin and the refusals so a name the twin logged is
not mistaken for one the refusal logged.

**Which failure a red is, before E7-01 lands.** The service half fails on the
missing `app.services.response_loop`; the HTTP half on its control — the student's
own read carries no `instructors` member yet, so the planted name is not on it.
"""

import logging
from typing import Any

import pytest
from fixtures.report_api import INSTRUCTOR_ROLE
from fixtures.staff_names import (
    IDENTITY_NAME_COLUMN,
    STAFF_NAMES,
    TEACHER_NAME,
    StaffNameWorld,
    ask_the_definer,
    ask_the_service,
    require_the_application_role,
    require_the_definer,
)
from fixtures.student_read import StudentReadDoor, response_surface

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

PLANTED_NAME = "Perpetua Grindlewald-Never-In-A-Refusal"


def test_a_refused_service_read_carries_no_staff_name_in_its_answer_or_its_log(
    staff_names: StaffNameWorld, caplog: pytest.LogCaptureFixture
) -> None:
    """The sibling lead asks about `F1WW`: an empty answer, and no staff name logged.

    **The twin:** the lead of the course asks the same question and is answered
    the planted name, so the name is reachable through this door.

    **The mutation this kills:** a refusal that logs what it withheld ("reader X
    refused names [...] for section Y"), or raises an error whose message carries
    the rows it read, or answers a sentinel item naming the instructor.
    """
    world = staff_names
    require_the_application_role(world.application_session)
    require_the_definer(world.application_session)
    assert world.lead is not None and world.sibling_lead is not None
    caplog.set_level(logging.DEBUG)

    twin = ask_the_service(
        world.application_session, section_id=world.taught, reader_person_id=world.lead.person_id
    )
    assert twin == [TEACHER_NAME], f"The twin: the course's lead was answered {twin}."

    caplog.clear()
    by_service = ask_the_service(
        world.application_session,
        section_id=world.taught,
        reader_person_id=world.sibling_lead.person_id,
    )
    by_definer = ask_the_definer(
        world.application_session,
        section_id=world.taught,
        reader_person_id=world.sibling_lead.person_id,
    )
    assert by_service == [] and by_definer.rows == [], (
        f"The sibling lead was answered {by_service} by the service and {by_definer.rows} by the "
        "definer; a refused reader is answered nothing (done-when 3)."
    )
    surface = f"{by_service!r} {by_definer!r} {caplog.text}"
    leaked = [name for name in STAFF_NAMES if name in surface]
    assert not leaked, (
        f"A refused read of F1WW's names carried {leaked} in its answer or in what it logged:\n"
        f"{caplog.text[:1200]}\n\nE7-01 done-when 4: no refusal carries a staff name."
    )


def test_a_refused_http_read_carries_no_staff_name_in_its_body_headers_or_log(
    student_read_door: StudentReadDoor, web_identity: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """`GET /student/survey` refused twice — no session, and an instructor's — and the name in neither.

    **The control:** the enrolled student's own read carries the planted name, so
    the route the refusals are made against is one that serves it.

    **The mutation this kills:** a refusal body, header or log line built after
    the payload was assembled (a 401 that echoes the would-be answer, a debug log
    of the payload before the role check).
    """
    door = student_read_door
    person = web_identity.person(**{IDENTITY_NAME_COLUMN: PLANTED_NAME})
    door.world.rows.graph.assign(
        INSTRUCTOR_ROLE, scope=door.world.enrolled_section_id, person=person
    )
    door.world.rows.commit()
    caplog.set_level(logging.DEBUG)

    own = door.get()
    assert own.status_code == 200 and PLANTED_NAME in own.text, (
        f"The control: the enrolled student's own read answered {own.status_code} and does not "
        f"carry {PLANTED_NAME!r}, the name of the instructor of their section. Body begins "
        f"{own.text[:400]!r}. Without it, a refusal carrying no name proves nothing."
    )

    door.get_as_an_instructor()  # mint the instructor's session before the capture is cleared
    caplog.clear()
    refusals = {
        "with no session": door.get_without_a_session(),
        "with an instructor's session": door.get_as_an_instructor(),
    }
    for what, refused in refusals.items():
        assert refused.status_code == 401, (
            f"`GET /student/survey` {what} answered {refused.status_code}, not E2-09's 401; this "
            "test searches refusals, so a non-refusal here is a broken premise."
        )
        surface = response_surface(refused)
        assert PLANTED_NAME not in surface, (
            f"The refusal {what} carries {PLANTED_NAME!r} in its body or headers: "
            f"{surface[:600]!r}. E7-01 done-when 4."
        )
    assert PLANTED_NAME not in caplog.text, (
        f"A refused `GET /student/survey` logged {PLANTED_NAME!r}:\n{caplog.text[:1200]}\n\n"
        "E7-01 done-when 4: no refusal carries a staff name in its log line."
    )
