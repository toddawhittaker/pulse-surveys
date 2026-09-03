"""E2-08 — the comment length bound lives on the request model, not in the service.

ADR 0062 settles where a value is judged:

> **One parse, at the edge, into typed values; every check and every echo reads
> what that parse produced or what actually arrived.**

The bound itself — 4000 characters — is the security fix round's, and
`tests/integration/test_the_submit_path_answers_the_validity_matrix.py::
test_a_comment_over_the_length_bound_is_refused_before_the_provider_is_asked`
asserts what a student gets: 4000 accepted, 4001 refused 422, nothing stored, no
classification row. **This module asserts the other half, and it exists because
that one cannot.** §3.3's gate runs after all value validation, so a bound
written into the submission service also refuses before the provider is asked and
also leaves no row — the two are indistinguishable over HTTP. The security
round's re-mutation battery measured that mutation surviving
(`docs/disputes/E2-08-06.md`, M2c), and this is the repair the ruling asks for:
assert the bound where it now lives.

**The model is found, not named.** E2-08's work order settles "one Pydantic
request model" for this route and settles no class name, so pinning one would
make a rename a red in a test about a length. The route module is walked for
every Pydantic model it can *reach* — the ones in its namespace and the ones
nested in their field annotations — and the one holding the comment field is the
subject. A `comment_text` field is E2-05's own column name, which
`tests/fixtures/submit.py` already builds every request body from.

**Reachable, and it took two corrections to get there.** The first version kept
only classes whose `__module__` was the route module's, and found nothing: SPEC
§13 gives schemas a home of their own, so the models are declared in
`app/schemas/survey.py` and imported. The second kept the namespace, and found
`SubmissionRequest` but not `SubmittedAnswer` — the request model carries
`answers: list[SubmittedAnswer]`, and the bound is on the nested class, which is
never bound to a name in the route module at all. Neither restriction bought
anything: a `comment_text` field is what identifies the model and no library
model has one. Both cost the whole test, which failed on its own discovery each
time while its failure message printed the namespace that led to the answer.

That is `docs/MISTAKES.md` entry 35's shape twice over, and the third time in
this ticket — `docs/disputes/E2-08-02.md` was the first, over a Celery task's
`__module__` reporting `celery.local`. Each repair widened the walk by exactly
the one level the last failure exposed, which is a class of defect being fixed
one instance at a time.

**The entry's own rule is applied now, in `the_comment_model` below**: the walk
has to *find* something certainly present before it may report something absent,
because "found nothing" is what a broken walk says too. The same control is in
`reclassification_entry_point` in `tests/fixtures/submit.py`, over the other walk
this ticket got wrong. Neither is a test of its own — a control that had to be
run separately would be a control somebody could forget to run — and both fail
inside the walk they guard, naming it.

**Nothing here builds a database or an application.** A request model is a class;
if judging a comment's length needed a session, the bound would not be at the
edge.
"""

from types import ModuleType
from typing import Any, get_args

import pytest
from fixtures.submit import (
    COMMENT_MAXIMUM_LENGTH,
    COMMENT_TEXT_COLUMN,
    RATING_COLUMN,
    STUDENT_API_MODULE,
    WORKLOAD_HOURS_COLUMN,
)

# One character over and one character under the bound, which is the whole of
# what an off-by-one can be. Named rather than inlined so a failure message can
# say which side it is about.
AT_THE_BOUND = COMMENT_MAXIMUM_LENGTH
OVER_THE_BOUND = COMMENT_MAXIMUM_LENGTH + 1

# E2-05's three answer value columns, one of which any parse of a submission has
# to land in — SPEC §3.2 gives an answer three shapes and E2-05 gives `answer`
# one column for each. They are the control on the walk below: a route that
# parses a submission at all reaches a model declaring at least one of them,
# whatever the envelope is called and however deep the nesting goes.
ANSWER_VALUE_FIELDS = (RATING_COLUMN, COMMENT_TEXT_COLUMN, WORKLOAD_HOURS_COLUMN)


def models_within(annotation: Any) -> list[Any]:
    """Every Pydantic model reachable inside one field's annotation.

    `list[SubmittedAnswer]`, `SubmittedAnswer | None`, `dict[str, SubmittedAnswer]`
    and an `Annotated[...]` wrapper all answer the same way, because
    `typing.get_args` unwraps each of them and this recurses through whatever it
    hands back. An annotation that is itself a model answers itself; anything
    else — a `str`, a `Decimal`, a `FieldInfo` sitting in `Annotated` metadata —
    answers nothing.
    """
    from pydantic import BaseModel

    if isinstance(annotation, type):
        if issubclass(annotation, BaseModel) and annotation is not BaseModel:
            return [annotation]
        return []
    return [model for argument in get_args(annotation) for model in models_within(argument)]


def reachable_models(module: ModuleType) -> dict[str, Any]:
    """Every Pydantic model the route module can reach, its nested ones included.

    **Reachable, rather than defined or merely carried**, and each of those two
    widenings was a level of nesting an earlier version of this walk could not
    see:

    - `value.__module__ == module.__name__` found nothing at all, because SPEC
      §13 gives schemas a home of their own — the models are declared in
      `app/schemas/survey.py` and imported into the route module.
    - The namespace alone found `SubmissionRequest` and not `SubmittedAnswer`,
      because the request model carries `answers: list[SubmittedAnswer]` and the
      nested class is never bound to a name in the route module. The bound is on
      `SubmittedAnswer.comment_text`, one level below anything a namespace walk
      can see.

    So this expands transitively through field annotations, and the property it
    exists for survives a restructure in either direction: a flat request model
    carrying `comment_text` is found as a root, and a nested one is found through
    the field that reaches it. What identifies the model is the field, never a
    class name — E2-08's work order settles "one Pydantic request model" and no
    spelling.

    **Three walks in this ticket have reported a deliverable missing while it was
    present**: `docs/disputes/E2-08-02.md` over a Celery task's `__module__`,
    `E2-08-06.md`'s repair over the schemas module, and this one over the
    nesting. Each is `docs/MISTAKES.md` entry 35's shape. What this function does
    *not* carry is the repair — a walk cannot control itself, because a broken one
    would answer the control with the same silence — so the control lives one
    level up, in `the_comment_model`, which requires this to find a model
    declaring one of E2-05's answer value columns before it may say the comment
    field is nowhere.
    """
    from pydantic import BaseModel

    found: dict[str, Any] = {}
    pending = [
        value
        for name, value in vars(module).items()
        if not name.startswith("_")
        and isinstance(value, type)
        and issubclass(value, BaseModel)
        and value is not BaseModel
    ]
    while pending:
        model = pending.pop()
        if model.__name__ in found:
            continue
        found[model.__name__] = model
        for field in getattr(model, "model_fields", {}).values():
            pending.extend(models_within(field.annotation))
    return found


def the_comment_model(module: ModuleType) -> Any:
    """The one request model carrying a comment field, or a failure naming the gap.

    **The walk is made to find a model that is certainly there, before it reports
    that one is not** — `docs/MISTAKES.md` entry 35's rule, and the repair the two
    earlier versions of this walk did not get. Both of them answered "no model
    declares a comment field", in the same words they would have used had the
    bound genuinely been absent, and nothing in either message could tell a blind
    walk from a missing deliverable.

    The control is E2-05's three answer value columns rather than the comment
    alone, and the difference is what makes it a control instead of a restatement
    of the assertion. A route that parses a submission at all (ADR 0062) reaches
    a model carrying at least one of `rating`, `comment_text` or
    `workload_hours`, whatever the envelope is called and however deep it nests.
    So a walk that finds none of the three is blind; a walk that finds `rating`
    and no `comment_text` is working, and the failure that follows is about the
    field's spelling — which is the diagnosis a reader wants and the one neither
    earlier version could give.
    """
    available = reachable_models(module)
    namespace = sorted(name for name in vars(module) if not name.startswith("_"))
    parsing_an_answer = sorted(
        name
        for name, model in available.items()
        if set(getattr(model, "model_fields", {})) & set(ANSWER_VALUE_FIELDS)
    )
    if not parsing_an_answer:
        pytest.fail(
            f"This walk over `{STUDENT_API_MODULE}` reaches no model declaring any of "
            f"{list(ANSWER_VALUE_FIELDS)} — E2-05's three answer value columns, one of which any "
            "parse of a submission has to land in. It reaches "
            f"{sorted(available)}, out of a namespace holding {namespace}.\n\n"
            "**So this is a defect in `reachable_models`, not in E2-08's length bound.** Read it "
            "that way before reading anything else: the walk cannot see the request model, and "
            "whatever it goes on to say about where the bound lives is a statement it is not in a "
            "position to make. It has been blind twice — once keeping only classes whose "
            "`__module__` was the route module's, when SPEC §13 puts schemas in a home of their "
            "own, and once reading the namespace alone, when the bound sits on a model nested "
            "inside the one the route declares. This control exists so that a third such "
            "restriction fails here, naming itself, rather than further down naming a bound that "
            "is in fact exactly where it should be."
        )
    carrying = {
        name: model
        for name, model in available.items()
        if COMMENT_TEXT_COLUMN in getattr(model, "model_fields", {})
    }
    if len(carrying) != 1:
        pytest.fail(
            f"{len(carrying)} of the Pydantic models `{STUDENT_API_MODULE}` reaches declare a "
            f"`{COMMENT_TEXT_COLUMN}` field ({sorted(carrying)}); it reaches {sorted(available)}, "
            f"and its own namespace holds {namespace}. This module needs exactly one to ask about "
            "the bound. The field name is E2-05's own column name, which every request body in "
            "this ticket is built from — if the model spells it otherwise, `COMMENT_TEXT_COLUMN` "
            "in tests/fixtures/submit.py is the one line that changes."
        )
    return next(iter(carrying.values()))


def a_comment_of(length: int) -> str:
    """A comment of exactly `length` characters, and nothing else about it."""
    built = "a" * length
    assert len(built) == length, f"Built {len(built)} characters, not {length}."
    return built


def payload_carrying(model: Any, comment: str) -> dict[str, Any]:
    """The smallest valid payload for `model`, with the comment the caller chose.

    Every field the model requires besides the comment is filled by *type*, with
    a value ordinary enough that no other rule can be what refuses it — §3.2's
    first question is at position 1 and its Likert starts at 1, so an integer of
    1 satisfies both the ordinal and a rating if the model happens to require
    either. A field this cannot fill stops the test with a message naming it,
    rather than being left out and refused for a reason that is not the length
    (`docs/MISTAKES.md` entry 13: when a test fails inside its own fixture,
    suspect the fixture first).
    """
    from decimal import Decimal

    payload: dict[str, Any] = {COMMENT_TEXT_COLUMN: comment}
    for name, field in getattr(model, "model_fields", {}).items():
        if name == COMMENT_TEXT_COLUMN or not field.is_required():
            continue
        annotation = field.annotation
        if annotation is int:
            payload[name] = 1
        elif annotation is float:
            payload[name] = 1.0
        elif annotation is Decimal:
            payload[name] = Decimal("1")
        elif annotation is str:
            payload[name] = "x"
        else:
            pytest.fail(
                f"`{model.__name__}` requires a field `{name}` of type {annotation!r}, which this "
                "test has no ordinary value for. It fills the model's other required fields so "
                "that the only thing varying between its two halves is the comment's length; a "
                "field left out would be refused for a reason this test is not about."
            )
    return payload


def test_the_request_model_accepts_a_comment_at_the_bound_and_refuses_one_over_it(
    configured_env: dict[str, str],
    import_app_module: Any,
) -> None:
    """4000 characters validate and 4001 do not, asked of the model rather than the route.

    **This is the assertion the integration test cannot make.** Over HTTP a bound
    on the request model and a bound in the submission service produce the same
    422, the same empty tables and the same absent classification row, because
    §3.3's gate runs after all value validation. ADR 0062's rule is about *where*
    the judgement happens — "one parse, at the edge, into typed values" — and the
    only place that difference is visible is here, where the model is constructed
    with no route, no session and no database in the way.

    **The accepted half is the boundary itself**, 4000, so a bound written `<`
    where it should be `<=` fails at the control rather than passing here. That
    is the same pairing the integration test makes and it is not redundant: this
    one says the model refuses, that one says a student is refused, and a bound
    that lives on the model while the route ignores the model would pass here and
    fail there.

    **The model asked is the one the bound sits on**, which the walk finds by the
    field rather than by a name: the route's own request model carries
    `answers: list[SubmittedAnswer]`, and `comment_text` — with its `max_length` —
    is a field of the nested class. Validating that class directly is the whole
    of what makes this a statement about *where* the bound lives; validating the
    outer model would go through the same nesting the route does and say nothing
    the integration test does not already say.

    **The mutation it kills:** the bound moved off the request model into the
    submission service — measured surviving the integration test in
    `docs/disputes/E2-08-06.md` (M2c) — and the bound removed altogether. It also
    kills a bound written as a `str` field with no constraint and a check in a
    validator that returns a truncation instead of raising, since a truncated
    value validates and this asserts a refusal.
    """
    from pydantic import ValidationError

    module = import_app_module(STUDENT_API_MODULE)
    assert module is not None, (
        f"There is no `{STUDENT_API_MODULE}` module. E2-08's work order puts the submit route "
        "there; the model it parses into may live in `app/schemas/`, be imported, and be nested "
        "inside another — all of which this walk follows."
    )
    # The model the bound is *on*, which is not necessarily the model the route
    # declares: the request carries `answers: list[SubmittedAnswer]` and the
    # comment is a field of the nested one. Validating the nested model directly
    # is what makes this a statement about where the bound lives.
    model = the_comment_model(module)

    try:
        at_the_bound = model.model_validate(payload_carrying(model, a_comment_of(AT_THE_BOUND)))
    except ValidationError as rejected:
        pytest.fail(
            f"A comment of exactly {AT_THE_BOUND} characters was refused by "
            f"`{model.__name__}`: {rejected}. That is the bound itself, and it is accepted — a "
            "rule written `<` where it should be `<=` refuses the longest comment a student is "
            "allowed to write, and the refusal below would then say nothing about where the "
            "bound sits."
        )
    assert len(getattr(at_the_bound, COMMENT_TEXT_COLUMN)) == AT_THE_BOUND, (
        f"A comment of {AT_THE_BOUND} characters came back from the model at "
        f"{len(getattr(at_the_bound, COMMENT_TEXT_COLUMN))}. The bound is inclusive, and a model "
        "that silently shortens a comment stores words the student did not write under their "
        "name — which §5.1 then shows to their instructor."
    )

    with pytest.raises(ValidationError) as refused:
        model.model_validate(payload_carrying(model, a_comment_of(OVER_THE_BOUND)))

    assert COMMENT_TEXT_COLUMN in str(refused.value), (
        f"The model refused a comment of {OVER_THE_BOUND} characters and the error does not name "
        f"`{COMMENT_TEXT_COLUMN}`: {refused.value}. A refusal about some other field would satisfy "
        "the `raises` above while the comment stayed unbounded."
    )
