"""The student's comment models, structurally — E8-01, done-when 6.

> 6. **Nothing identifies a comment or its week.** No comment in the payload
>    carries an `answer_id`, a status, a time or a week.

The work order settles the models whole: `StudentComment {text}`,
`StudentReleasedComment {text, stream}` with `stream` one of `instructor` and
`course`, `StudentTrendPoint {course_week, mean}` (renamed from the work order's
`TrendPoint`, which collides with the report's class in OpenAPI), and `StudentStream {stream, trend,
distribution, small_n, comments}`, every one `extra="forbid"`. So the assertion
is an **equality over each model's declared fields** — not a search for
`answer_id`, which a `handle`, a `week` or a `submitted_at` walks past — and a
refusal, by name, of each identifying member planted on a comment model.

The behavioural half, over served payloads, is
`tests/integration/test_no_comment_a_student_reads_carries_its_id_status_time_or_week.py`.

**The controls.** Each model constructs from its own members, so a model that
refused everything cannot pass the refusals; the library's default for an
unknown member is pinned by
`test_the_student_payload_schema_carries_nothing_of_a_benchmark.py`'s control.

**Which failure a red is, before E8-01 lands:** `the_model` fails naming the
class and the module.
"""

from importlib import import_module
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

pytestmark = [pytest.mark.invariant]

HOME = "app.schemas.response_loop"

FIELDS = {
    "StudentComment": {"text"},
    "StudentReleasedComment": {"text", "stream"},
    "StudentTrendPoint": {"course_week", "mean"},
    "StudentStream": {"stream", "trend", "distribution", "small_n", "comments"},
}

# What would identify a comment or place it in a week, planted on each model that
# carries a comment.
IDENTIFYING = ("answer_id", "status", "submitted_at", "week", "course_week", "cut_at")
COMMENT_MODELS = ("StudentComment", "StudentReleasedComment")

A_TEXT = "E8-01 a comment a student reads"


def the_model(name: str) -> type[BaseModel]:
    module = import_module(HOME)
    model = getattr(module, name, None)
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        pytest.fail(
            f"`{HOME}` declares no pydantic `{name}`. E8-01's work order settles it there, with "
            f"exactly {sorted(FIELDS[name])}."
        )
    return model


def complaints_about(model: type[BaseModel], values: dict[str, Any], key: str) -> list[Any]:
    try:
        model(**values)
    except ValidationError as refused:
        return [error for error in refused.errors() if tuple(error.get("loc", ()))[:1] == (key,)]
    return []


def whole(name: str) -> dict[str, Any]:
    """One valid set of each model's own members, built from the settled shapes."""
    if name == "StudentComment":
        return {"text": A_TEXT}
    if name == "StudentReleasedComment":
        return {"text": A_TEXT, "stream": "instructor"}
    if name == "StudentTrendPoint":
        return {"course_week": 1, "mean": 4.0}
    return {
        "stream": "course",
        "trend": [{"course_week": 1, "mean": None}],
        "distribution": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
        "small_n": True,
        "comments": [],
    }


@pytest.mark.parametrize("name", sorted(FIELDS))
def test_each_model_constructs_from_its_own_members(name: str) -> None:
    """The control: the settled shape builds. **A red here means the shape moved, or this broke.**"""
    built = the_model(name)(**whole(name))

    assert set(type(built).model_fields) == FIELDS[name]


@pytest.mark.parametrize("name", sorted(FIELDS))
def test_each_model_declares_exactly_its_settled_fields(name: str) -> None:
    """An equality over the declared fields.

    **The mutation this kills:** any member added to a comment, a released item, a
    trend point or a stream — the likeliest being the instructor card's
    `answer_id`, `flag` or `decided_by_you`, or a `week` "so the page can group
    the release". **The near miss:** the settled fields themselves.
    """
    declared = set(the_model(name).model_fields)

    assert declared == FIELDS[name], (
        f"`{name}` declares {sorted(declared)}; E8-01's work order settles {sorted(FIELDS[name])}. "
        "SPEC §4: no comment carries a time, and a release carries no week."
    )


@pytest.mark.parametrize("planted", IDENTIFYING)
@pytest.mark.parametrize("name", COMMENT_MODELS)
def test_a_comment_model_refuses_a_member_that_would_identify_it(name: str, planted: str) -> None:
    """Each identifying member, planted on an otherwise whole comment: a complaint naming it.

    **The mutation this kills:** a comment model left at `extra="ignore"` (the
    work order: `extra="forbid"`), under which a service passing `answer_id` has
    it dropped today and served the day the model grows the field.
    """
    complaints = complaints_about(the_model(name), {**whole(name), planted: "x"}, planted)

    assert complaints, f"`{name}` accepted `{planted}`, a member it does not declare."


@pytest.mark.parametrize("stream", ["INSTRUCTOR", "COURSE", "benchmark", ""])
def test_a_released_comment_names_one_of_the_two_streams_only(stream: str) -> None:
    """`stream` is `instructor` or `course`. **The mutation this kills:** `stream: str`."""
    model = the_model("StudentReleasedComment")

    complaints = complaints_about(model, {"text": A_TEXT, "stream": stream}, "stream")

    assert complaints, f"`StudentReleasedComment` admitted the stream {stream!r}."
