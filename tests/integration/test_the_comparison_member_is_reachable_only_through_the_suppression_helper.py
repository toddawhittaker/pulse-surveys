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
from typing import Any

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


def carries_the_figure(value: Any) -> bool:
    """Whether the driven figure is anywhere in a comparison value's serialization."""
    return any(
        isinstance(found, int | float)
        and not isinstance(found, bool)
        and float(found) == pytest.approx(A_COMPARISON_MEAN)
        for found in figures_in(serialized(value))
    )


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

    This drives it: every parameter of the constructor is filled with a value a
    caller could produce, and the construction must be refused. A class that
    accepts them has a token that is either absent or unchecked, and
    `docs/MISTAKES.md` entry 22 is the record of a closed-set guard defeated one
    level out — which is exactly what a comparison value anybody can construct is.
    """
    comparison = report_api_contract.comparison_type()
    filled = {}
    for parameter in inspect.signature(comparison).parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        annotation = parameter.annotation
        if annotation is bool:
            filled[parameter.name] = True
        elif annotation in (int, float):
            filled[parameter.name] = A_COMPARISON_MEAN
        elif annotation is str:
            filled[parameter.name] = "constructed by a caller that holds no token"
        else:
            filled[parameter.name] = object()

    with pytest.raises(Exception) as refused:
        comparison(**filled)
    assert refused.value is not None, (
        f"`{comparison.__name__}({', '.join(sorted(filled))})` was constructed by this test, which "
        "holds nothing private to `app.services.reporting`. Work-order decision 5 makes the "
        "constructor demand a module-private token so that the suppression helper is the only way "
        "this member can be populated; a constructor anybody can call is a chokepoint with a door "
        "beside it."
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
