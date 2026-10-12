"""Both course-page payloads declare `lead_name`, required, a name or `null` — E9-08.

The settled interface (its "Payload members"): `StudentWeekResults.lead_name:
str | None` in `app.schemas.response_loop`, and `SectionView.lead_name: str |
None` in `app.schemas.report`, **both required with no default**. The server
always sends the member, so it is required on the wire; a default would make it
optional in the generated frontend types, and a course with no lead sends `null`
rather than leaving the member out (done-when 4: no lead name, and no
placeholder).

The behavioural half — which name each reader is sent — is
`tests/integration/test_the_course_pages_carry_the_lead_faculty_name.py` and
`test_a_student_is_named_the_lead_of_her_own_course_and_never_another.py`. This
module pins only the declaration, which those cannot see: a member with a
`None` default serialises the same way and reads the same in every payload test.

**Which failure a red is, before E9-08 lands:** `the_lead_field` fails naming
the model and the members it does declare.
"""

from importlib import import_module
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

LEAD_NAME_MEMBER = "lead_name"

COURSE_PAGE_MODELS = (
    ("app.schemas.response_loop", "StudentWeekResults"),
    ("app.schemas.report", "SectionView"),
)
MODEL_IDS = [name for _home, name in COURSE_PAGE_MODELS]


@pytest.fixture(autouse=True)
def _a_stated_environment(configured_env: dict[str, str]) -> None:
    """The schema modules may reach `app.db`, which builds `Settings()` at import (entry 40)."""


def the_lead_field(home: str, name: str) -> Any:
    """The model's `lead_name` field, or a failure naming what the model declares."""
    model = getattr(import_module(home), name, None)
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        pytest.fail(f"`{home}` declares no pydantic `{name}`.")
    field = model.model_fields.get(LEAD_NAME_MEMBER)
    if field is None:
        pytest.fail(
            f"`{home}.{name}` declares {sorted(model.model_fields)} and no "
            f"`{LEAD_NAME_MEMBER}`. E9-08's interface adds `{LEAD_NAME_MEMBER}: str | None`, "
            "required with no default."
        )
    return field


@pytest.mark.parametrize(("home", "name"), COURSE_PAGE_MODELS, ids=MODEL_IDS)
def test_the_lead_name_member_is_required_with_no_default(home: str, name: str) -> None:
    """`lead_name` has no default, so the member is required on the wire.

    **The mutation this kills:** `lead_name: str | None = None`, which every
    payload test reads identically and which turns the generated frontend type
    optional, so a page can be written that treats a missing member as "no
    lead". **The near miss:** the `None` value itself, admitted by the next test.
    """
    field = the_lead_field(home, name)

    assert field.is_required(), (
        f"`{home}.{name}.{LEAD_NAME_MEMBER}` has a default ({field.default!r}). E9-08's "
        "interface: required with no default; a course with no lead sends `null`."
    )


@pytest.mark.parametrize(("home", "name"), COURSE_PAGE_MODELS, ids=MODEL_IDS)
def test_the_lead_name_member_admits_a_name_and_null_and_nothing_shaped_otherwise(
    home: str, name: str
) -> None:
    """A string and `None` validate; an object does not.

    **The mutations this kill:** `lead_name: str` (an unled course cannot be
    sent at all, so the server has to invent a placeholder — done-when 4 forbids
    one), and `lead_name: Any` or a structured member (a staff row, with its
    person id, sent to a student's browser). **The near miss:** the two values
    admitted.
    """
    field = the_lead_field(home, name)
    adapter = TypeAdapter(field.annotation)

    assert (
        adapter.validate_python(None) is None
    ), f"`{home}.{name}.{LEAD_NAME_MEMBER}` refuses `None`; a course with no lead sends `null`."
    assert adapter.validate_python("A Lead Faculty name") == "A Lead Faculty name"
    with pytest.raises(ValidationError):
        adapter.validate_python({"display_name": "A name", "person_id": "an id"})
