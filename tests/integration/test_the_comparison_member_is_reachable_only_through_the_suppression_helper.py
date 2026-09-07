"""SPEC §4.1 item 7's chokepoint — ticket E4-07, criterion 5.

> No figure computed from a comparison set is shown below the benchmark minimum —
> a mean, a median, or any other statistic, not only a drawn line. A comparison
> figure over fewer than the configured number of sections is suppressed exactly
> as a line is (§5.1).

E4 builds no comparison set — that is E5 — and E4's breakdown decision 4 is what
makes "asserted from E4" mean something anyway: the payload carries the
`comparison` member from day one, populated **only** through one suppression
helper that enforces both configured minimums, and E5's benchmarks flow through
that helper or fail their own invariant.

**Both minimums, each driven to both sides separately, named as a catalog rather
than as a concept** (`docs/MISTAKES.md` entry 22). The pair is
`benchmark_min_sections_default` and `benchmark_min_respondents_default`, and the
breakdown says why writing both out matters: "a guard built against one of two
thresholds is the closed-set defeat `docs/MISTAKES.md` records: E5 routes a mean
over three sections and four respondents through it and ships a figure §5.1 means
to suppress." The two are also different **units** — a count of sections and a
count of people — which is `docs/MISTAKES.md` entry 50's shape: a threshold
crossed by a count of something else. Neither number is written down here; both
are read from `Settings`, because the promise is about the *configured* number.

**The positive control is what makes an absence mean suppression.** Criterion 5
says so outright: in E4 the member is otherwise always empty, so an assertion on
absence alone would survive deleting the helper. A figure clearing both minimums
has to *appear*.

**And the mechanism is structural, not a convention.** Work-order decision 5
settles it as a module-private construction token: the comparison value's
constructor demands something only `app.services.reporting` holds, and the schema
field takes that type. So a later caller cannot assemble a comparison figure and
hand it to the schema — the type refuses to exist. That is the half a test can
prove without E5's data, and it is the half that has to survive E5 being written
by somebody who never read this ticket.

**Five doors, at three levels, and each level was found by looking one further
out than the last.** The constructor's token closes the direct one.
`model_construct` and `model_copy(update=...)` build a *figure* without calling
it, so the ruled chokepoint moved to the payload boundary — and the same two
methods build a *report* without running that boundary's own validator, so it
moved once more, to a revalidation the response performs whatever handed it the
object. Every step of that was found by execution rather than by argument, and
the sequence is `docs/MISTAKES.md` entry 22's lesson in three instalments: a
closed-set guard is defeated one level out, and the level you are looking at is
never the last one.

Every test that drives a door asserts the **outcome** — the figure does not reach
wire form — and never the mechanism, because the ticket settles that the check
exists and leaves its spelling to the implementer.

**Marked `invariant` at the module level**, which puts it in the isolated §4.1
pass CLAUDE.md says may never be skipped. It is named in the pull request body so
the exit ticket's collection count has a baseline (E4-07's known traps).

**Which failure a red is, before E4-07 lands.** The schema, the type and the
helper are all looked up inside test bodies through `report_api_contract`, each
with a `pytest.fail` naming what is owed, so the first red is a FAILED naming a
deliverable rather than a collection error (`docs/MISTAKES.md` entry 44).
"""

import dataclasses
import inspect
from typing import Any, get_args, get_origin

import pytest
from fixtures.report_api import FULL_WEEK, ReportDoor

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The figure driven through the helper. A mean of instructor ratings is what §5.1
# puts on the comparison line, and this value is exact in binary and is not a
# count anything else here holds — neither minimum, nor a section count, nor a
# respondent count — so finding it in a serialized payload is finding *this*
# figure and not a coincidence (`docs/MISTAKES.md` entry 3 on a value a mutation
# cannot change).
A_COMPARISON_MEAN = 4.25

# A token a caller can produce, for the construction test below. `object()` and
# not `None`: `None` is what a constructor with a defaulted token parameter falls
# back to, so refusing it could be the default being refused rather than this
# value being compared. A fresh object is unmistakably something only this test
# holds.
A_CALLERS_TOKEN = object()

# A string for whichever field carries the suppression reason. Its content is
# never read; what matters is that it *is* a string, so the field's own
# annotation has nothing to object to and the only layer left that can refuse the
# call is the token check.
A_REASON = "assembled by a caller that holds no token"

# How far past a minimum the clearing side of each pair sits. One, because the
# minimum itself is the first value that passes: SPEC §5.1 suppresses a figure
# "computed from fewer than the configured number of sections", so `n` sections
# is enough and `n - 1` is not. A pair driven at `n + 10` and `n - 10` would be
# green against an implementation using `>` where `>=` belongs.
ONE = 1


def serialized(value: Any) -> dict[str, Any]:
    """One comparison value as a payload would carry it, however the type spells itself.

    **Discovered rather than imposed**, because work-order decision 5 settles the
    mechanism and not the shape: a Pydantic model, a frozen dataclass, or a plain
    object with a `__dict__` are all types whose constructor can demand a token,
    and a test that required one of them would be choosing the implementation.
    A type none of these reaches is a failure naming the ambiguity.
    """
    dumped = getattr(value, "model_dump", None)
    if callable(dumped):
        return dict(dumped(mode="json"))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    held = getattr(value, "__dict__", None)
    if isinstance(held, dict):
        return dict(held)
    pytest.fail(
        f"This suite cannot read the members of a comparison value ({value!r}, a "
        f"{type(value).__name__}). It reads a Pydantic `model_dump`, a dataclass, or an object "
        "with a `__dict__`; a fourth spelling is taught in `serialized` in this module. The "
        "question it is asking is SPEC §4.1 item 7's: is the figure on the wire or is it not."
    )


def a_value_the_annotation_accepts(name: str, annotation: Any, owner: str) -> Any:
    """One value for a constructor field that the field's own annotation cannot object to.

    **This is half of the C4 repair, and it exists because the obvious version of
    it hid a survivor.** The first version of the construction test put `object()`
    into any annotation it did not recognise, which meant `str | None` and
    `float | None` both got one — so pydantic refused the call on the field types
    and the test never reached the token check at all. Filling each field with
    something its annotation admits leaves the token as the only thing that can
    say no.

    An optional annotation is unwrapped rather than answered with `None`, and
    `False` is chosen for a boolean rather than `True`, because the state this
    call is trying to reach is the dangerous one: a comparison figure that is
    **not** suppressed and carries a number. A refusal of a value that was
    suppressed and empty would prove much less.

    An annotation this cannot fill is a failure naming it rather than a guess —
    the guess is what went wrong the first time.

    Takes an annotation rather than an `inspect.Parameter`, because the same
    question is asked of a constructor's parameters and of a model's fields: the
    side doors below smuggle values in by field name, and a second copy of this
    reasoning for `FieldInfo` would be `docs/MISTAKES.md` entry 13.
    """
    optional = type(None) in get_args(annotation)
    members = [member for member in get_args(annotation) if member is not type(None)]
    base = members[0] if get_origin(annotation) is not None and len(members) == 1 else annotation

    if base is bool:
        return False
    if base is int or base is float:
        return A_COMPARISON_MEAN
    if base is str:
        return A_REASON
    if optional:
        return None
    pytest.fail(
        f"`{owner}` declares a field `{name}: {annotation}`, and this test has no value "
        "for it that the annotation certainly accepts. It fills a boolean, a number, a string and "
        "anything optional; a field of some other kind is taught in "
        "`a_value_the_annotation_accepts` in this module.\n\n"
        "Guessing here is exactly what let the C4 mutation survive: a value the field rejects makes "
        "pydantic refuse the construction before the token is consulted, and the test then passes "
        "whether or not the chokepoint exists."
    )


def figures_in(value: Any) -> list[Any]:
    """Every scalar a serialized comparison value holds, at any depth.

    At any depth because item 7 is about a *figure* rather than about a field: a
    mean nested under `statistics` or `set` is shown exactly as one at the top
    level is, and a scan of the first level only would report a suppressed value
    for a payload carrying the number one object down.
    """
    if isinstance(value, dict):
        return [found for item in value.values() for found in figures_in(item)]
    if isinstance(value, list | tuple):
        return [found for item in value for found in figures_in(item)]
    return [value]


def the_figure_is_in(node: Any) -> bool:
    """Whether the driven figure is anywhere inside an already-serialized structure."""
    return any(
        isinstance(found, int | float)
        and not isinstance(found, bool)
        and float(found) == pytest.approx(A_COMPARISON_MEAN)
        for found in figures_in(node)
    )


def carries_the_figure(value: Any) -> bool:
    """Whether the driven figure is anywhere in a comparison value's serialization."""
    return the_figure_is_in(serialized(value))


def smuggled_field_values(comparison: Any) -> dict[str, Any]:
    """Every field of a comparison value, filled to make the figure visible and unsuppressed.

    By field name rather than by constructor parameter, because that is the
    currency both side doors take: `model_construct` and `model_copy(update=...)`
    are given field names and never see `__init__` at all. The values come from
    the same annotation reader the direct-construction test uses, so a field
    renamed or retyped moves both doors at once.
    """
    return {
        name: a_value_the_annotation_accepts(name, field.annotation, comparison.__name__)
        for name, field in comparison.model_fields.items()
    }


def report_payload_model(contract: Any) -> Any:
    """The schema model the report payload is served as — the wire boundary itself.

    Found by the member the sketch puts at the top of the payload, the same way
    the contract finds the comparison type: one model in `app.schemas.report`
    carrying a `comparison` member. Anything else is a failure naming the
    ambiguity rather than a guess about which model is the payload.
    """
    schema = contract.schema()
    models = [
        value
        for name, value in vars(schema).items()
        if not name.startswith("_")
        and isinstance(value, type)
        and contract.comparison_member in (getattr(value, "model_fields", None) or {})
    ]
    if len(models) != 1:
        pytest.fail(
            f"`{contract.schema_module_name}` declares {len(models)} models carrying a "
            f"`{contract.comparison_member}` member ({[model.__name__ for model in models]}). This "
            "suite needs one to hand a smuggled figure to."
        )
    return models[0]


def a_refusal_about_the_comparison_member(refused: BaseException, member: str) -> bool:
    """Whether a refusal is about the comparison member rather than about something else.

    **The re-pass asked for this, and the reason is worth stating.** A reader that
    counted *any* exception as a closed door has a second way to be green: a field
    that could not re-validate from its own serialized form would raise here, and
    the side-door tests would then pass with the boundary check deleted. That is
    `docs/MISTAKES.md` entry 3 one level below where round four found it — a guard
    test whose outcome a second layer also produces — and it is the third time
    this one chokepoint has produced that shape.

    Read off pydantic's own `loc`, which is the currency a field-level refusal is
    held in. A refusal that carries no `errors()` is matched on its text instead,
    so a boundary that refuses some other way still counts if it says what it
    refused — `docs/MISTAKES.md` entry 35's rule about enumerating currencies
    applies to this reader too, and the text is the second currency.
    """
    errors = getattr(refused, "errors", None)
    if callable(errors):
        try:
            reported = list(errors())
        except Exception:
            reported = []
        if reported:
            return any(
                member in tuple(str(part) for part in (error.get("loc") or ()))
                for error in reported
            )
    return member in str(refused)


def a_closed_door(refused: BaseException, member: str, what: str) -> tuple[bool, str]:
    """One refusal, judged: the guard firing, or a red no conclusion can be drawn from."""
    if a_refusal_about_the_comparison_member(refused, member):
        return False, f"{what} ({type(refused).__name__}: {refused})"
    pytest.fail(
        f"{what}, and the refusal does not name `{member}`: {type(refused).__name__}: {refused}.\n\n"
        "This test will not call that a pass, because it cannot tell a closed chokepoint from a "
        "payload that does not round-trip through its own schema. Either the boundary is refusing "
        "for a reason that has nothing to do with the comparison figure — in which case the "
        "smuggled payload is malformed and this test is measuring the wrong thing — or the guard "
        "names its field some other way, and `a_refusal_about_the_comparison_member` in this module "
        "is where that spelling is taught."
    )


def reaches_the_wire(smuggled: Any, door: Any, contract: Any) -> tuple[bool, str]:
    """Whether a comparison value built outside the helper survives to a serialized payload.

    **The question is the outcome and not the mechanism.** A boundary that refuses
    the value and one that serializes it with the figure gone are both correct and
    this reader accepts either; only a figure that comes out the other side is a
    failure. E4-07's work order settles that the chokepoint exists and does not
    settle how it is spelled, so a test that required a validator, or a particular
    exception type, would be choosing for the implementer.

    **A refusal counts only if it is about the comparison member.** See
    `a_refusal_about_the_comparison_member` for the near miss that rule closes:
    a reader that counted any exception has a second way to be green.

    A real payload is fetched first and its comparison member swapped, rather than
    a payload being assembled here: every other member is then exactly what the
    route serves, so nothing in this walk is a shape this test invented.
    """
    body, _answered = door.payload(course_week=FULL_WEEK)
    handed = dict(body)
    handed[contract.comparison_member] = smuggled

    model = report_payload_model(contract)
    try:
        validated = model.model_validate(handed)
    except Exception as refused:
        return a_closed_door(refused, contract.comparison_member, "the payload boundary refused it")
    try:
        served = validated.model_dump(mode="json")
    except Exception as refused:
        return a_closed_door(refused, contract.comparison_member, "serializing it was refused")

    carried = served.get(contract.comparison_member)
    return the_figure_is_in(carried), f"it serialized as {carried!r}"


def survives_as_a_report(smuggled_report: Any, contract: Any) -> tuple[bool, str]:
    """Whether a whole report carrying a smuggled figure survives to wire form.

    The same outcome question one level up. The value under test is a report
    instance that no validator has seen, and the boundary is the revalidation a
    response model performs over whatever the route hands it — which is what
    `model_validate` over an instance exercises and what `revalidate_instances`
    governs.
    """
    model = type(smuggled_report)
    try:
        validated = model.model_validate(smuggled_report)
    except Exception as refused:
        return a_closed_door(
            refused, contract.comparison_member, "the response boundary refused the report"
        )
    try:
        served = validated.model_dump(mode="json")
    except Exception as refused:
        return a_closed_door(
            refused, contract.comparison_member, "serializing the report was refused"
        )
    carried = served.get(contract.comparison_member)
    return the_figure_is_in(carried), f"the report serialized its comparison member as {carried!r}"


def a_report_built_with_model_construct(
    model: Any, validated: Any, smuggled: Any, member: str
) -> Any:
    """A report assembled field by field, with no validation run over any of them."""
    return model.model_construct(**{**dict(validated), member: smuggled})


def a_report_built_with_model_copy(model: Any, validated: Any, smuggled: Any, member: str) -> Any:
    """A validated report with its comparison member rewritten afterwards."""
    del model
    return validated.model_copy(update={member: smuggled})


# The two doors into a *report*, beside the two into a figure. Each puts a
# smuggled figure into a report without any validator seeing it, which is what
# makes a field-level guard skippable one level out.
SMUGGLED_REPORT_DOORS = (
    ("model_construct", a_report_built_with_model_construct),
    ("model_copy", a_report_built_with_model_copy),
)
REPORT_DOOR_IDS = [name for name, _build in SMUGGLED_REPORT_DOORS]


def test_a_figure_over_fewer_sections_than_the_minimum_is_suppressed(
    report_api_contract: Any, configured_env: Any
) -> None:
    """The section minimum, one below it, with the respondent minimum well cleared.

    §5.1: "a benchmark line is suppressed rather than shown thin, and a comparison
    mean or median is suppressed rather than shown at all". Driven one below
    rather than far below, so an implementation comparing with `>` rather than
    `>=` is caught by this test and its paired passage together.

    **The mutation this kills:** the helper reading only
    `benchmark_min_respondents_default` — the closed-set defeat E4's breakdown
    decision 4 names by hand. The respondent count here clears its minimum, so a
    helper that checks respondents alone lets this figure straight through.
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]
    assert sections >= 2, (
        f"`{report_api_contract.minimum_sections}` is {sections}, so there is no value below it "
        "that is still a comparison set and this pair cannot be driven."
    )

    thin = report_api_contract.call_helper(
        A_COMPARISON_MEAN, sections=sections - ONE, respondents=respondents
    )
    assert not carries_the_figure(thin), (
        f"A comparison mean of {A_COMPARISON_MEAN} over {sections - ONE} sections — one below the "
        f"configured `{report_api_contract.minimum_sections}` of {sections} — is on the wire: "
        f"{serialized(thin)}. Its respondent count of {respondents} clears the other minimum, so a "
        "helper reading only that one passes this figure through."
    )


def test_a_figure_over_fewer_respondents_than_the_minimum_is_suppressed(
    report_api_contract: Any, configured_env: Any
) -> None:
    """The respondent minimum, one below it, with the section minimum cleared.

    The mirror of the test above, and the two are the catalog rather than the
    concept: each minimum is driven to its own boundary with the other one open,
    so neither can stand in for the other and a helper enforcing one of the two is
    red on exactly one of these tests.

    **The mutation this kills:** the helper reading only
    `benchmark_min_sections_default`. **The unit trap it also covers**
    (`docs/MISTAKES.md` entry 50): a respondent count is a count of *people*, and
    a helper that compared this minimum against a count of responses or of
    sections would let a figure over one person's answers through — the number
    handed here is the count the promise is about, and the helper is asked for it
    by that name.
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]
    assert respondents >= 2, (
        f"`{report_api_contract.minimum_respondents}` is {respondents}, so there is no value below "
        "it to drive this half of the pair with."
    )

    thin = report_api_contract.call_helper(
        A_COMPARISON_MEAN, sections=sections, respondents=respondents - ONE
    )
    assert not carries_the_figure(thin), (
        f"A comparison mean of {A_COMPARISON_MEAN} over {respondents - ONE} respondents — one below "
        f"the configured `{report_api_contract.minimum_respondents}` of {respondents} — is on the "
        f"wire: {serialized(thin)}. Its section count of {sections} clears the other minimum."
    )


def test_a_figure_clearing_both_minimums_is_carried(
    report_api_contract: Any, configured_env: Any
) -> None:
    """Criterion 5's positive control: the helper is not simply a function that returns nothing.

    > the item-7 invariant carries its own positive control, because in E4 the
    > member is otherwise always empty and an assertion on absence alone would
    > survive deleting the helper.

    Driven **at** each minimum rather than above it, because that is the first
    value §5.1 permits: "computed from fewer than the configured number of
    sections" suppresses, so the configured number itself passes. A helper written
    with `>` suppresses here and is caught by this test alone — the two
    suppression tests above are green against it.
    """
    minimums = report_api_contract.minimums()
    sections = minimums[report_api_contract.minimum_sections]
    respondents = minimums[report_api_contract.minimum_respondents]

    passed = report_api_contract.call_helper(
        A_COMPARISON_MEAN, sections=sections, respondents=respondents
    )
    assert carries_the_figure(passed), (
        f"A comparison mean of {A_COMPARISON_MEAN} over {sections} sections and {respondents} "
        f"respondents — both exactly the configured minimums — is not on the wire: "
        f"{serialized(passed)}. Without this, the two suppression assertions beside it are "
        "satisfied by a helper that suppresses everything, or by no helper at all."
    )


def test_the_comparison_value_cannot_be_constructed_without_the_helpers_token(
    report_api_contract: Any, configured_env: Any
) -> None:
    """The structural half of criterion 5: the helper is the only way in.

    > The helper is the only way to populate the member, proven structurally (the
    > member's type is private to the helper's module, or an equivalent the ADR
    > defends).

    Work-order decision 5 chooses the equivalent: a module-private construction
    token the constructor demands. So a caller outside `app.services.reporting` —
    E5's benchmark assembly, E9's drill-down, a later export — cannot build a
    comparison value at all, and the suppression cannot be walked around by
    building the payload some other way.

    **This test survived the mutation battery once, and how it survived is the
    whole reason it is written the way it is now.** The first version filled every
    parameter by annotation and put `object()` in anything it did not recognise —
    which was `reason: str | None` and `figure: float | None` — and then accepted
    *any* exception as the refusal. Pydantic objected to the field types long
    before the token was ever consulted, so replacing the token check with
    `if False:` left this test green: it was asserting that a value with two
    nonsense fields is refused, which is true whether or not the chokepoint
    exists. That is `docs/MISTAKES.md` entry 9's shape, and this repository's own
    sharpest version of it — a guard test whose outcome a second defence layer
    also produces.

    **So the repair is a pair, and neither half works alone.** Every field is
    given a value its own annotation accepts, so pydantic has no objection to
    make; and the refusal is required to be a `TypeError` specifically, which is
    the token check's and not pydantic's — a `ValidationError` is a `ValueError`.
    Fill the fields correctly but accept any exception, and a later model
    validator's complaint stands in for the token again; pin the exception type
    but leave `object()` in a field, and pydantic raises first. Together they
    leave exactly one layer that can refuse this call.

    **The token is supplied rather than omitted, deliberately.** Leaving it out
    would raise `TypeError` for a missing argument on a constructor whose check
    had been deleted — the same exception from the signature rather than from the
    guard, which is the near miss one level further out. This call hands over a
    value a caller *can* produce and requires the check itself to refuse it.

    **What this must do under mutation:** green on the shipped tree, red the
    moment the token comparison stops being made.
    """
    comparison = report_api_contract.comparison_type()
    signature = inspect.signature(comparison)
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) != 1:
        pytest.fail(
            f"`{comparison.__name__}{signature}` takes {len(positional)} positional parameters "
            f"({[parameter.name for parameter in positional]}); this test hands the token over in "
            "the one positional slot work-order decision 5 describes and fills the rest by keyword. "
            "A token spelled some other way is taught here, in this test."
        )
    filled = {
        parameter.name: a_value_the_annotation_accepts(
            parameter.name, parameter.annotation, comparison.__name__
        )
        for parameter in signature.parameters.values()
        if parameter.kind is parameter.KEYWORD_ONLY
    }

    built: Any = None
    raised: BaseException | None = None
    try:
        built = comparison(A_CALLERS_TOKEN, **filled)
    except Exception as refused:
        raised = refused

    assert raised is not None, (
        f"`{comparison.__name__}` was constructed by this test — which holds nothing private to "
        f"`{report_api_contract.reporting_module_name}` — as {built!r}. Every field was given a "
        "value its annotation accepts, so nothing but the token stood between this call and a "
        "comparison figure a caller assembled for itself. Work-order decision 5 makes the "
        "constructor demand a module-private token so that the suppression helper is the only way "
        "this member can be populated; a constructor anybody can call is a chokepoint with a door "
        "beside it, and §4.1 item 7 is then enforced by whoever remembers it."
    )
    assert isinstance(raised, TypeError), (
        f"The construction was refused by {type(raised).__name__}: {raised}. This test requires a "
        "`TypeError`, which is the token check's own refusal, because it cannot otherwise tell the "
        "chokepoint from the layer beside it — a pydantic `ValidationError` is a `ValueError`, and "
        "a test that accepted one would stay green with the token check deleted. That is not a "
        "hypothetical: it is how this test survived the C4 mutation on the first pass.\n\n"
        f"If the token layer legitimately refuses with {type(raised).__name__}, this assertion is "
        "the one line to change — but check first that the refusal is the token's and not a field "
        f"validator's, because the values handed over were {filled!r}."
    )


def test_a_figure_built_past_the_constructor_does_not_reach_the_serialized_payload(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The first side door: `model_construct` never calls `__init__` at all.

    The security round's MEDIUM. The token check lives in the constructor, and
    pydantic offers a documented way of building a model without running it —
    `model_construct` skips validation and initialisation both. Confirmed by
    execution: it builds an unsuppressed figure carrying a number, and the report
    schema then accepts and serializes it. So the chokepoint proven one test up is
    a chokepoint with a documented bypass beside it, which is
    `docs/MISTAKES.md` entry 22's shape exactly — a closed-set guard defeated one
    level out.

    **The ruled answer is the wire, not a second constructor.** However a
    comparison value was built, the payload boundary re-checks it, so a smuggled
    instance does not reach an instructor's screen. That is the property asserted
    here: this test hands the boundary a real payload with the smuggled figure in
    it and requires the figure not to come out the other side. A refusal at
    validation, a refusal while serializing, and a serialization with the figure
    gone are all correct — the ticket settles the property and not the mechanism.

    **The mutation this kills:** deleting the payload-boundary check, which
    restores exactly the state the reviewers demonstrated. **The canary:** the
    smuggled value is required to carry the figure *before* the boundary sees it,
    or "the figure did not reach the wire" is a statement about a smuggle that
    never worked (`docs/MISTAKES.md` entry 3).
    """
    comparison = report_api_contract.comparison_type()
    smuggled = comparison.model_construct(**smuggled_field_values(comparison))
    assert carries_the_figure(smuggled), (
        f"The smuggled value does not carry {A_COMPARISON_MEAN} before the boundary sees it: "
        f"{serialized(smuggled)}. Until it does, this test asserts that a figure nobody planted is "
        "absent."
    )

    reached, what_happened = reaches_the_wire(smuggled, report_door, report_api_contract)
    assert not reached, (
        f"A comparison figure built with `model_construct`, which never runs the constructor or "
        f"its token check, reached the serialized payload: {what_happened}.\n\n"
        "SPEC §4.1 item 7 is a rule about what is *shown*, so the boundary that has to hold it is "
        "the one the payload crosses. A guard that only stands in `__init__` is walked past by "
        "every pydantic entry point that does not call it."
    )


def test_a_suppressed_figure_cannot_be_unsuppressed_by_copying_it(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The second side door: `model_copy(update=...)` rewrites the fields of a legitimate value.

    Sharper than the first, because it starts from a value the helper itself
    produced — a figure the two minimums suppressed, which is the ordinary state
    of this member in E4 — and turns it into an unsuppressed one carrying the
    number. No construction happens at all, so no constructor can object;
    confirmed by execution in the security round.

    That is the shape §4.1 item 7 exists to stop reached through a copy: the
    suppression decision is made once, by the helper, over the two configured
    minimums, and then rewritten by a caller who never saw them.

    **The mutation this kills:** the same one — deleting the payload-boundary
    check. **The two canaries:** the value the helper produced must genuinely be
    suppressed and carry no figure, and the copy must genuinely carry it, or this
    test is comparing two absences.
    """
    minimums = report_api_contract.minimums()
    suppressed = report_api_contract.call_helper(
        A_COMPARISON_MEAN,
        sections=minimums[report_api_contract.minimum_sections] - ONE,
        respondents=minimums[report_api_contract.minimum_respondents] - ONE,
    )
    assert not carries_the_figure(suppressed), (
        f"The helper's own output already carries {A_COMPARISON_MEAN} below both minimums: "
        f"{serialized(suppressed)}. This test starts from a suppressed value; if suppression is "
        "broken, the pair at the top of this module is the red to read first."
    )

    smuggled = suppressed.model_copy(update=smuggled_field_values(type(suppressed)))
    assert carries_the_figure(smuggled), (
        f"Copying the suppressed value with the figure in the update did not put it there: "
        f"{serialized(smuggled)}. Until it does, this test asserts nothing about the boundary."
    )

    reached, what_happened = reaches_the_wire(smuggled, report_door, report_api_contract)
    assert not reached, (
        f"A suppressed comparison figure was unsuppressed with `model_copy(update=...)` and reached "
        f"the serialized payload: {what_happened}.\n\n"
        "The helper decided this figure was over too few sections and too few respondents to show. "
        "A copy that overwrites that decision, and a payload boundary that does not look again, "
        "means the two configured minimums are enforced only against callers who ask politely."
    )


@pytest.mark.parametrize(("door", "build"), SMUGGLED_REPORT_DOORS, ids=REPORT_DOOR_IDS)
def test_a_report_carrying_a_smuggled_figure_does_not_reach_wire_form(
    report_door: ReportDoor, report_api_contract: Any, door: str, build: Any
) -> None:
    """The same class one level out: the field guard is itself skippable.

    The re-pass found it, and the shape is by now familiar enough to name in
    advance: `docs/MISTAKES.md` entry 22 is a closed-set guard defeated one level
    out, and this chokepoint has now been defeated at three levels in a row — the
    constructor, then the field, and now the report that holds the field. A
    validator on `comparison` runs when a report is *validated*; neither
    `model_construct` nor `model_copy(update=...)` validates anything, and the
    reviewers proved by execution that a report built either way is served with an
    unsuppressed figure and a 200.

    **What is asserted is the wire, again, and only the wire.** However the report
    was assembled, the response boundary re-checks it, so a figure §5.1 means to
    suppress does not reach a screen. The ruled fix is one line of model
    configuration; this test names neither the line nor pydantic's spelling of it,
    because the property is what the ticket owes and the spelling is the
    implementer's.

    **The mutation this kills:** removing `revalidate_instances` from the report
    model's configuration, which restores exactly the state the reviewers
    demonstrated — a route that hands back an object nothing re-reads.

    **Both doors are driven**, because they fail differently: `model_construct`
    builds a report that never existed, and `model_copy(update=...)` rewrites one
    that did. A guard that caught only unvalidated construction would leave the
    second open, and the second is the one a caller reaches for when they have a
    real report in hand.

    **The canary:** the smuggled report has to carry the figure before any
    boundary is asked about it, or this test asserts the absence of something
    nobody planted (`docs/MISTAKES.md` entry 3).
    """
    comparison = report_api_contract.comparison_type()
    smuggled_figure = comparison.model_construct(**smuggled_field_values(comparison))

    body, _answered = report_door.payload(course_week=FULL_WEEK)
    model = report_payload_model(report_api_contract)
    validated = model.model_validate(body)
    assert report_api_contract.comparison_member in dict(validated), (
        f"A validated report exposes {sorted(dict(validated))} and none of them is "
        f"`{report_api_contract.comparison_member}`, so neither door below can put a figure into "
        "one."
    )

    smuggled_report = build(
        model, validated, smuggled_figure, report_api_contract.comparison_member
    )
    before_any_boundary = smuggled_report.model_dump(mode="json")
    assert the_figure_is_in(before_any_boundary), (
        f"The report built with `{door}` does not carry {A_COMPARISON_MEAN} before any boundary "
        "sees it; its comparison member is "
        f"{before_any_boundary.get(report_api_contract.comparison_member)!r}. Until it does, this "
        "test asserts that a figure nobody planted is absent."
    )

    survived, what_happened = survives_as_a_report(smuggled_report, report_api_contract)
    assert not survived, (
        f"A report assembled with `{door}`, carrying a comparison figure no validator ever saw, "
        f"reached wire form: {what_happened}.\n\n"
        "The guard on the comparison member runs when a report is validated, and neither of these "
        "doors validates anything — so a route that returns such an object serves the figure. "
        "§4.1 item 7 is a rule about what is shown, so the last boundary before the wire is the one "
        "that has to hold it, whatever built the object crossing it."
    )


def test_the_comparison_type_is_defined_beside_the_helper_that_holds_its_token(
    report_api_contract: Any, configured_env: Any
) -> None:
    """The token can only be private if the type and the helper share a module.

    Work-order decision 5 puts the suppression helper in `app.services.reporting`
    because benchmark assembly is that module's §13 mandate, and the token is
    private to it. A type defined in the schema module with the helper elsewhere
    could not have a private token at all — whatever it demanded would be
    reachable by anybody who can import the schema.

    **The mutation this kills:** the type moved into `app.schemas.report` "so the
    schema owns its own types", which reads as tidying and removes the privacy the
    whole mechanism rests on.
    """
    comparison = report_api_contract.comparison_type()
    helper = report_api_contract.helper()
    assert comparison.__module__ == report_api_contract.reporting_module_name, (
        f"`{comparison.__name__}` is defined in `{comparison.__module__}` and the suppression "
        f"helper in `{report_api_contract.reporting_module_name}`. The token is private to a "
        "module, so the two live in one."
    )
    assert (
        helper.__module__ == report_api_contract.reporting_module_name
    ), f"The helper `{helper.__name__}` is defined in `{helper.__module__}`."


def test_the_report_payload_carries_a_suppressed_comparison_member_before_e5_fills_it(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The member is on the wire from day one, suppressed, with no figure in it.

    Breakdown decision 4 and the exit table both say what E4 owes here: "no
    comparison figure appears anywhere (E5 has not run)", and the member exists
    "so item 7's chokepoint has a place to stand before E5 fills it". A payload
    that omitted the member until E5 arrived would give E5 a schema change to make
    and this invariant nothing to stand on.

    **The mutation this kills:** the member dropped from the payload while E4 has
    no benchmarks — which passes every other test in this epic and moves the
    chokepoint into E5's diff.
    """
    body, answered = report_door.payload(course_week=FULL_WEEK)
    comparison = report_api_contract.member(
        body, report_api_contract.comparison_member, answered=answered
    )
    assert comparison is not None, (
        f"`{report_api_contract.comparison_member}` is null. The README sketch spells it "
        '`{"suppressed": true, "reason": "below-minimum"}` — an object saying it has nothing, '
        "which E4-08 renders as a panel with one line rather than as a missing panel."
    )
    assert comparison.get(report_api_contract.suppressed_field) is True, (
        f"`{report_api_contract.comparison_member}` is {comparison!r}. E5 has not run, so there is "
        "no comparison set behind this section and every figure over it is suppressed."
    )
    numbers = [
        found
        for found in figures_in(comparison)
        if isinstance(found, int | float) and not isinstance(found, bool)
    ]
    assert not numbers, (
        f"`{report_api_contract.comparison_member}` carries the numbers {numbers} in an epic that "
        "computes no comparison set. §4.1 item 7 covers a mean, a median, or any other statistic — "
        "not only a drawn line."
    )
