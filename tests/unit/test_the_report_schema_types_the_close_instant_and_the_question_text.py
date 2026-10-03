"""The report schema types E5-02's three members — ticket E5-02, criterion 1.

> 1. The payload carries both question texts and the close instant; the schema
>    types them and the route serves them.

The route half is driven over HTTP in
`tests/integration/test_the_report_payload_carries_the_served_question_texts.py`
and `..._the_weeks_close_instant.py`. This module is the schema half, and it is a
separate module because the two fail for different reasons: a schema that does
not declare the member cannot serve it, and a schema that declares it while the
read leaves it unpopulated is a different defect entirely.

**Where the three members land** is settled by E5-02's work order, decision 1 —
`closes_at` on the week model, `question_text` on each stream's model, and a
top-level `institution_timezone` mirroring the student payload. Nothing here
names a class: each model is found by a member it already carries (the week model
by `course_week`, the stream model by `distribution`, the payload by `streams`),
which is the device `tests/unit/test_the_payload_sketch_and_the_schema_are_
reconciled.py` already uses and which survives a class being renamed.

**Every member is asserted to be required.** A member typed `datetime | None` with
a default of `None` satisfies "the schema declares it" while serving nothing, and
that is the shape a member added under time pressure takes — the frontend then
renders the absent-field path for ever and no test says why.
"""

import typing
from datetime import datetime
from typing import Any

import pytest

# What the work order settles as the source of each member, quoted where a
# failure message needs it.
CLOSES_AT_IS_OWED = (
    "E5-02 work order decision 1: the week member gains `closes_at: datetime` (aware), the value "
    "from the reported week's `survey_window.closes_at` — the row the report read already holds. "
    "The mockup's eyebrow renders it as 'responses closed Sun 11:59 PM' "
    "(design/InstructorMondayReport.dc.html:227), and nothing on the payload carries it today."
)

QUESTION_TEXT_IS_OWED = (
    "E5-02 work order decision 1: each stream gains `question_text: str`, the served text of that "
    "stream's rating question. SPEC §3.2 versions that wording server-side — 'Question text is "
    "stored in a versioned `question_set` table' — so it is served rather than copied into the "
    "frontend, where a second copy would drift the first time a set is re-versioned."
)

TIMEZONE_IS_OWED = (
    "E5-02 work order decision 1: the payload's top level gains `institution_timezone: str`, the "
    "IANA name from `settings.institution_timezone`, mirroring the student payload. The eyebrow "
    "formats the close instant with that zone explicitly rather than with the browser's guess, so "
    "a payload carrying the instant and not the zone cannot be rendered correctly."
)


def underlying(annotation: Any) -> Any:
    """One field annotation with `Annotated[...]` and `X | None` peeled off.

    A member may legitimately be spelled `Annotated[datetime, ...]` — a Pydantic
    validator, a JSON-schema example — and that is still a `datetime`. `X | None`
    is peeled too so the *optionality* is asserted once, by `is_required()`,
    rather than twice and in two vocabularies.
    """
    while True:
        arguments = [
            argument for argument in typing.get_args(annotation) if argument is not type(None)
        ]
        if typing.get_origin(annotation) is None or not arguments:
            return annotation
        annotation = arguments[0]


def model_carrying(schema: Any, field: str) -> Any:
    """The one model in the schema module already declaring `field`.

    Found rather than named, so a class rename is not a red here, and required to
    be exactly one so that an ambiguous tree fails naming the ambiguity instead of
    binding to whichever model `vars()` happened to answer first.
    """
    models = [
        value
        for name, value in vars(schema).items()
        if not name.startswith("_")
        and isinstance(value, type)
        and field in (getattr(value, "model_fields", None) or {})
    ]
    if len(models) != 1:
        pytest.fail(
            f"The report schema declares {len(models)} models carrying `{field}` "
            f"({[model.__name__ for model in models]}); this test reads the one that does. The "
            "module declares "
            f"{sorted(name for name, value in vars(schema).items() if isinstance(value, type))}."
        )
    return models[0]


def declared(model: Any, field: str) -> Any:
    """One `FieldInfo` off a model, or `None` where the model does not declare it."""
    return (getattr(model, "model_fields", None) or {}).get(field)


def model_behind_member(schema: Any, member: str, report_api_contract: Any) -> Any:
    """The model the report payload's `member` is annotated with.

    **Read off the payload's own annotation rather than found by a field it
    carries.** "The model declaring `course_week`" is two models on this tree: the
    week member's, and each trend point's — a point carries the course week it
    plots. A selector demanding exactly one of them fails *in the selector*,
    before any assertion runs, and goes on failing whatever the implementer
    builds. The payload names its week member in one place and keeps naming it
    when a third model grows a `course_week` of its own.
    """
    payload = model_carrying(schema, report_api_contract.streams_member)
    field = declared(payload, member)
    assert field is not None, (
        f"`{payload.__name__}` declares {sorted(payload.model_fields)}, with no `{member}` member, "
        "so this test cannot find the model behind it."
    )
    annotation = underlying(field.annotation)
    assert isinstance(annotation, type) and getattr(annotation, "model_fields", None) is not None, (
        f"`{payload.__name__}.{member}` is annotated {field.annotation!r}, which is not a single "
        "model this test can ask for its fields."
    )
    return annotation


def test_the_week_model_types_the_close_instant_as_a_required_datetime(
    report_api_contract: Any,
) -> None:
    """Criterion 1's schema half for the close instant.

    **The mutation this kills:** the member declared as `str` — an ISO string the
    read formats itself — which type-checks, serialises, and takes the timezone
    decision away from the one layer that knows the institution's zone; and the
    member declared `datetime | None = None`, which serves an absent field for
    ever while looking present in the schema.
    """
    schema = report_api_contract.schema()
    week_model = model_behind_member(schema, report_api_contract.week_member, report_api_contract)
    field = declared(week_model, report_api_contract.closes_at_field)

    assert field is not None, (
        f"`{week_model.__name__}` declares {sorted(week_model.model_fields)}, with no "
        f"`{report_api_contract.closes_at_field}`.\n\n{CLOSES_AT_IS_OWED}"
    )
    annotation = underlying(field.annotation)
    assert isinstance(annotation, type) and issubclass(annotation, datetime), (
        f"`{week_model.__name__}.{report_api_contract.closes_at_field}` is annotated "
        f"{field.annotation!r}. The work order types it `datetime`: the instant travels as an "
        "instant, and the rendering — which is the only layer that knows the institution's zone and "
        "the reader's locale — formats it.\n\n"
        f"{CLOSES_AT_IS_OWED}"
    )
    assert field.is_required(), (
        f"`{week_model.__name__}.{report_api_contract.closes_at_field}` is optional, with default "
        f"{field.get_default()!r}. Every reported week has a `survey_window` row and that row has a "
        "close instant, so there is no week for which this member is absent — and an optional "
        "member is one the read can leave unpopulated without any test noticing."
    )


def test_each_streams_model_types_the_question_text_as_a_required_string(
    report_api_contract: Any,
) -> None:
    """Criterion 1's schema half for the served question wording.

    **The mutation this kills:** `question_text` declared `str | None = None`, so
    a read that could not resolve the wording quietly serves nothing and the
    histogram silently falls back to its stream label — which is exactly today's
    behaviour, shipped under a new field name.
    """
    schema = report_api_contract.schema()
    stream_model = model_carrying(schema, report_api_contract.distribution_field)
    field = declared(stream_model, report_api_contract.question_text_field)

    assert field is not None, (
        f"`{stream_model.__name__}` declares {sorted(stream_model.model_fields)}, with no "
        f"`{report_api_contract.question_text_field}`.\n\n{QUESTION_TEXT_IS_OWED}"
    )
    annotation = underlying(field.annotation)
    assert annotation is str, (
        f"`{stream_model.__name__}.{report_api_contract.question_text_field}` is annotated "
        f"{field.annotation!r}; the work order types it `str`.\n\n{QUESTION_TEXT_IS_OWED}"
    )
    assert field.is_required(), (
        f"`{stream_model.__name__}.{report_api_contract.question_text_field}` is optional, with "
        f"default {field.get_default()!r}. E5-02's read has an answer for every week — the wording "
        "the week's responses answered, or the newest set's where nobody answered — so there is no "
        "week with no wording to serve, and an optional member is one the read can leave empty "
        "while every schema test stays green."
    )


def test_the_payload_types_the_institution_timezone_as_a_required_string(
    report_api_contract: Any,
) -> None:
    """Criterion 1's schema half for the zone the close instant is rendered in.

    **The mutation this kills:** the instant shipped without the zone, leaving the
    eyebrow to format in whatever zone the browser guesses — the known trap the
    ticket names, and one that is invisible on a developer machine already set to
    the institution's zone.
    """
    schema = report_api_contract.schema()
    payload_model = model_carrying(schema, report_api_contract.streams_member)
    field = declared(payload_model, report_api_contract.institution_timezone_member)

    assert field is not None, (
        f"`{payload_model.__name__}` declares {sorted(payload_model.model_fields)}, with no "
        f"`{report_api_contract.institution_timezone_member}`.\n\n{TIMEZONE_IS_OWED}"
    )
    annotation = underlying(field.annotation)
    assert annotation is str, (
        f"`{payload_model.__name__}.{report_api_contract.institution_timezone_member}` is annotated "
        f"{field.annotation!r}; the work order types it `str`, the IANA name.\n\n{TIMEZONE_IS_OWED}"
    )
    assert field.is_required(), (
        f"`{payload_model.__name__}.{report_api_contract.institution_timezone_member}` is optional, "
        f"with default {field.get_default()!r}. Every deployment is configured with a zone "
        "(`INSTITUTION_TIMEZONE`, documented in `.env.example`), so there is no report for which "
        "this is absent."
    )
