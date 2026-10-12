"""E9-08 — the Lead Faculty name on the two course pages: the names, and the readers.

Two test modules ask the student results payload, the instructor report payload
and the new name door the same questions, so the reading lives here and each
module asserts (`docs/MISTAKES.md` entry 13). **This file defines no pytest
fixture**, as `tests/fixtures/student_week.py` defines none: every module takes
E7-02's `hold` world (`tests/fixtures/the_hold.py`) and passes it to the plain
functions below, so nothing has to be registered and a tree without E9-08 fails
inside a test body naming what is missing (entry 44).

**The names E9-08's settled interface fixes, transcribed once:**

  - `StudentWeekResults.lead_name: str | None` (`app.schemas.response_loop`) and
    `SectionView.lead_name: str | None` (`app.schemas.report`, the report
    payload's `section` member), both **required with no default**, `null` for a
    course with no lead;
  - the door `app.services.response_loop.section_lead_name(session, *,
    section_id, reader_user_id=None, reader_person_id=None) -> str | None`, which
    answers the `display_name` of E9-03's `LEAD_FACULTY` row for that section, or
    `None` for a refused reader or an unled course, and raises `ValueError` when
    given neither reader key or both.

**Nothing here decides an answer.** It reads and fails naming the interface;
every expectation is written in the test that makes it (entries 19 and 30).
"""

from collections.abc import Mapping
from importlib import import_module
from typing import Any

import pytest

LEAD_NAME_MEMBER = "lead_name"

SERVICE_MODULE = "app.services.response_loop"
LEAD_DOOR = "section_lead_name"

INTERFACE = (
    "E9-08's settled interface: `StudentWeekResults.lead_name: str | None` and "
    "`SectionView.lead_name: str | None` (the instructor report's `section` member), both "
    "required with no default and `null` for a course with no lead; the lead's name is read "
    f"through `{SERVICE_MODULE}.{LEAD_DOOR}(session, *, section_id, reader_user_id=None, "
    "reader_person_id=None) -> str | None`, which asks E9-03's door with the reader's own key "
    "and answers the `LEAD_FACULTY` row's `display_name`."
)


def lead_name_in(payload: Any, what: str) -> Any:
    """The payload's `lead_name`, or a failure naming the interface when it has none.

    The member is required to be **present**, `null` included: a course with no
    lead sends `null`, never leaves the member out, so a missing key is a red and
    not a reading of "no lead".
    """
    if not isinstance(payload, Mapping):
        pytest.fail(f"{what} is {str(payload)[:300]!r}, not an object.\n\n{INTERFACE}")
    if LEAD_NAME_MEMBER not in payload:
        pytest.fail(f"{what} carries {sorted(payload)} and no `{LEAD_NAME_MEMBER}`.\n\n{INTERFACE}")
    return payload[LEAD_NAME_MEMBER]


def report_section(body: Any, what: str) -> Mapping[str, Any]:
    """The instructor report's `section` member, or a failure naming it."""
    section = body.get("section") if isinstance(body, Mapping) else None
    if not isinstance(section, Mapping):
        pytest.fail(f"{what} carries no `section` object: {str(body)[:300]!r}.")
    return section


def the_lead_door() -> Any:
    """`response_loop.section_lead_name`, or a failure naming the interface."""
    module = import_module(SERVICE_MODULE)
    door = getattr(module, LEAD_DOOR, None)
    if not callable(door):
        pytest.fail(
            f"`{SERVICE_MODULE}` exposes no callable `{LEAD_DOOR}`; it exposes "
            f"{sorted(name for name in vars(module) if not name.startswith('_'))}.\n\n{INTERFACE}"
        )
    return door


def ask_for_the_lead(
    session: Any, *, section_id: Any, reader_user_id: Any = None, reader_person_id: Any = None
) -> Any:
    """Call the door on `pulse_app`'s own connection (entry 46); what it answered.

    The transaction is ended afterwards so the next call sees whatever a test
    committed in between.
    """
    door = the_lead_door()
    try:
        answered = door(
            session,
            section_id=section_id,
            reader_user_id=reader_user_id,
            reader_person_id=reader_person_id,
        )
    except TypeError as mismatch:
        session.rollback()
        pytest.fail(f"`{LEAD_DOOR}` refused the settled keywords: {mismatch}\n\n{INTERFACE}")
    session.rollback()
    if answered is not None and not isinstance(answered, str):
        pytest.fail(
            f"`{LEAD_DOOR}` answered {type(answered).__name__} {answered!r}; the interface "
            "settles `str | None`."
        )
    return answered
