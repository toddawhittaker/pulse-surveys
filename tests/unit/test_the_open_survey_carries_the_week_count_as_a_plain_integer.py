"""The week count is a plain integer on `OpenSurvey`, never an optional one — ticket E4-17.

E4-17's Known traps, in as many words: "**A count of zero or a null is not a
shorter course.** The column is `NOT NULL` on the section row, so the field is a
plain integer rather than an optional one; an optional field would invite the
component to render a half-eyebrow rather than fail loudly where the data is
wrong."

**Why this is a test and not a review note.** The read-path integration test
beside it cannot see the difference: a field declared `int | None = None` that
happens to be filled correctly answers exactly what a required `int` answers, so
that suite is green over both. What the optional declaration changes is what
happens on the day the read path stops filling it — the answer carries `null`,
`WeekEyebrow` renders `COURSE WK 04 / , TERM WK 07`, and nothing fails. This is
the declaration, asserted where the declaration is.

**What it deliberately does not assert.** Where the member sits in the answer,
what it is described as, and what else `OpenSurvey` carries. The ticket settles a
field on that schema and leaves its neighbours alone, and a test comparing the
whole model would be pinning every one of them.

The member's spelling is `tests/fixtures/student_read.py`'s single transcription,
and it is **not settled by the ticket** — see the note beside it there, and
E4-17's manifest.
"""

from importlib import import_module
from typing import Any, get_type_hints

import pytest
from fixtures.student_read import LENGTH_WEEKS_FIELD, OPEN_SURVEY_CLASS, STUDENT_SCHEMAS_MODULE


def open_survey_schema() -> Any:
    """`app.schemas.student.OpenSurvey`, or a failure naming the deliverable.

    A plain helper called as the first statement of the test rather than a
    fixture, because `docs/MISTAKES.md` entry 44 makes a tests-first red a FAILED
    and never an ERROR: a guard that raises in a fixture turns this module's red
    into a setup error, which proves nothing about the assertion below it and
    reads to a hurried eye as a broken suite.
    """
    try:
        module = import_module(STUDENT_SCHEMAS_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{STUDENT_SCHEMAS_MODULE}` does not import ({missing}). E2-09 puts the student read "
            "path's response schemas there and E4-17 adds one field to one of them."
        )
    schema = getattr(module, OPEN_SURVEY_CLASS, None)
    if not isinstance(schema, type):
        pytest.fail(
            f"`{STUDENT_SCHEMAS_MODULE}` exposes no class `{OPEN_SURVEY_CLASS}`; it exposes "
            f"{sorted(name for name in vars(module) if not name.startswith('_'))}. E4-17's Scope "
            "names the schema outright — it is the answer a student's open survey is served as."
        )
    return schema


def test_the_open_survey_declares_the_week_count_as_a_required_integer() -> None:
    """Criterion 1 and the ticket's null trap: the count is a plain `int`, always present.

    **The mutations this kills.** The field declared `int | None`, or `Optional[
    int]`, or with a default of `None` — each of which lets a read path that
    found no section answer a half-eyebrow instead of failing where the data is
    wrong. The field declared `str`, which renders identically for a
    twelve-week section and makes `"12"` and `12` the same to every assertion
    over the wire. And the field absent, which is the first thing this reds on.

    **The near miss it must survive**: any description, any position among its
    neighbours, and any other member `OpenSurvey` carries. Only the one field's
    type and requiredness are read.
    """
    schema = open_survey_schema()
    annotations = get_type_hints(schema)
    assert LENGTH_WEEKS_FIELD in annotations, (
        f"`{OPEN_SURVEY_CLASS}` declares no `{LENGTH_WEEKS_FIELD}`; it declares "
        f"{sorted(annotations)}.\n\n"
        "E4-17 adds the section's own week count so the eyebrow can render the brief's `/ N` — "
        "the total the frontend is forbidden to derive, because the letter-to-length map is the "
        "institution's. If the member is spelled some other way, that is the naming gap E4-17's "
        "manifest reports rather than a defect: the spelling is one constant in "
        "`tests/fixtures/student_read.py`."
    )
    declared = annotations[LENGTH_WEEKS_FIELD]
    assert declared is int, (
        f"`{OPEN_SURVEY_CLASS}.{LENGTH_WEEKS_FIELD}` is declared {declared!r}, and the ticket's "
        'known trap makes it a plain `int`: "the column is `NOT NULL` on the section row, so the '
        "field is a plain integer rather than an optional one; an optional field would invite the "
        'component to render a half-eyebrow rather than fail loudly where the data is wrong".\n\n'
        "`int | None` and `Optional[int]` are the two spellings that fail here and pass every "
        "assertion made over the wire: a null is not a shorter course, it is a read path that "
        "found no section, and the eyebrow would print `COURSE WK 04 / , TERM WK 07` rather than "
        'fail. `str` is the other: it renders identically and makes `"12"` and `12` the same to '
        "every test that reads the answer."
    )

    fields = getattr(schema, "model_fields", None)
    assert isinstance(fields, dict) and LENGTH_WEEKS_FIELD in fields, (
        f"`{OPEN_SURVEY_CLASS}` exposes no pydantic `model_fields` entry for "
        f"`{LENGTH_WEEKS_FIELD}`; it exposes {fields if fields is None else sorted(fields)}. Every "
        "other member of this answer is a pydantic field, and requiredness is a property of the "
        "field rather than of the annotation — a `= None` default on an `int` annotation is the "
        "mutation this last assertion exists for."
    )
    assert fields[LENGTH_WEEKS_FIELD].is_required(), (
        f"`{OPEN_SURVEY_CLASS}.{LENGTH_WEEKS_FIELD}` carries a default, so an answer built without "
        "it validates and serializes a number nobody read off a section. The count is a fact about "
        "the section the window belongs to and there is no sensible default for it."
    )
