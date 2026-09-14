"""E5-05 criterion 2 — every new member, at every depth, refuses a figure the chokepoint never sealed.

> Every benchmark member at every depth refuses an unsealed value: constructing
> the payload with a hand-built figure fails validation, per member
> (mutation-proven, not read-proven).

E4-07 built this defence for one member and found out the hard way how many
levels it has: the constructor's private token closes the direct door,
`model_construct` and `model_copy(update=…)` walk past it, and the guard
therefore has to stand at the boundary the payload crosses. E5-05 adds three more
places a comparison figure can sit — a point's `mean`, and the workload
population's `mean` and `median` — and the work order's decision 4 puts the same
seal on each: `frozen=True`, `revalidate_instances="always"`, and a field
validator per figure field calling `refuse_an_unsealed_comparison`.

**One test per member, and that is the point of the module.** The battery row for
each member is "remove that member's validator", and each test below has to be
the one that goes red for its own member. A single test that tampered with all
three at once would stay red with two of the three guards deleted, which is a
test reporting the state of the member somebody remembered.

**The value is smuggled past the constructor, not handed to it.** A dict would be
refused by the field's own type before any validator ran, and a test that
accepted that refusal would be green with the whole seal deleted — that is how
E4-07's first version of this test survived its mutation. So the figure is built
with `model_construct`, which runs no validation and no `__init__`, and it is
built **unsuppressed carrying a number**, because that is the dangerous state:
§4.1 item 7 is about the figure, not the flag.

**The report these tests smuggle into is the one the service builds**, not a
payload re-validated from its own served JSON. The ruling on
`docs/disputes/E5-05-01.md` settles that: a served body carries its figures as
plain mappings, the seal is a private attribute that is deliberately never
serialized, and so re-validating a body that carries a *shown* figure is refused
before any smuggling happens — for every implementation that satisfies criterion
1, which is to say the tests had a second way to be green that had nothing to do
with their subject. Starting from the service's own object also puts these tests
on the layer they claim: sealed instances crossing the revalidation the response
performs over whatever the route hands back.

**A refusal counts only if it names the member that was tampered with**
(`tests/fixtures/report_benchmarks.py::through_the_boundary`). A reader counting
any exception has a second way to be green — a payload that will not round-trip
through its own schema raises here too — and this repository has been caught by
that shape before.

**Which failure a red is, before E5-05 lands.** The members are read through the
fixture module's readers, which `pytest.fail` naming what the work order owes.
"""

from collections.abc import Callable, Sequence
from typing import Any, NamedTuple

import pytest
from fixtures.report_api import PAYLOAD_STREAM_KEY, STREAMS_MEMBER, ReportDoor
from fixtures.report_benchmarks import (
    BENCHMARK_MEMBER,
    COMPARISON_POPULATION,
    MEAN_FIELD,
    MEDIAN_FIELD,
    POINT_MEAN_FIELD,
    POINT_WEEK_FIELD,
    POINTS_FIELD,
    WEEK_CLEAR,
    WORKLOAD_BENCHMARK_MEMBER,
    an_instructor_report,
    an_unsealed_figure,
    carries_number,
    through_the_boundary,
)
from fixtures.report_views import INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The number the smuggled figure carries. Not a value anything in this world
# computes — no mean, no median, no count, no minimum, and not one of E4-07's own
# hero figures — so finding it in a served payload is finding *this* figure and
# never a coincidence (`docs/MISTAKES.md` entry 3).
A_SMUGGLED_MEAN = 4.25

MISSING = object()


def child(node: Any, name: Any) -> Any:
    """One member of a report object, whether the level is a model, a mapping or a list."""
    if isinstance(name, int):
        if not isinstance(node, Sequence) or isinstance(node, str) or len(node) <= name:
            pytest.fail(f"{node!r} has no item {name}; this walk expected a list of points there.")
        return node[name]
    if isinstance(node, dict):
        if name not in node:
            pytest.fail(f"{sorted(node)} carries no `{name}`.")
        return node[name]
    found = getattr(node, name, MISSING)
    if found is MISSING:
        declared = sorted(getattr(type(node), "model_fields", None) or {})
        pytest.fail(
            f"`{type(node).__name__}` declares {declared} and carries no `{name}`. E5-05's work "
            "order settles the wire shape member by member, and this walk follows it."
        )
    return found


def replaced(node: Any, name: Any, value: Any) -> Any:
    """The same level with one member rewritten, and no validator run over the result.

    `model_copy` rather than a constructor, because the point of this walk is to
    build a report **no validator has seen** — if the rebuild validated, the guard
    under test would fire here rather than at the boundary, and the test would be
    asserting the wrong layer.
    """
    if isinstance(name, int):
        return [*node[:name], value, *node[name + 1 :]]
    if isinstance(node, dict):
        return {**node, name: value}
    copy = getattr(node, "model_copy", None)
    if not callable(copy):
        pytest.fail(
            f"`{type(node).__name__}` offers no `model_copy`, so this test cannot put a figure into "
            "it without running a validator. The work order settles these members as Pydantic "
            "models; a different kind of object is taught in `replaced` in this module."
        )
    return copy(update={name: value})


def walk(node: Any, path: Sequence[Any]) -> Any:
    """Follow a member path down a report object."""
    for name in path:
        node = child(node, name)
    return node


def with_member_replaced(node: Any, path: Sequence[Any], value: Any) -> Any:
    """A payload rebuilt from the leaf upward with one member replaced."""
    if not path:
        return value
    head = path[0]
    return replaced(node, head, with_member_replaced(child(node, head), path[1:], value))


SERIES_PATH = (
    STREAMS_MEMBER,
    PAYLOAD_STREAM_KEY[INSTRUCTOR_STREAM],
    BENCHMARK_MEMBER,
    COMPARISON_POPULATION,
    POINTS_FIELD,
)


def a_point_index(report: Any, course_week: int) -> int:
    """Where in the report's own series the point for one course week sits.

    Read off the **report object**, not a served body: the body is where the
    three tests used to start, and the ruling on `docs/disputes/E5-05-01.md`
    moved them off it.
    """
    points = walk(report, SERIES_PATH)
    weeks = [int(child(point, POINT_WEEK_FIELD)) for point in points]
    if course_week not in weeks:
        pytest.fail(
            f"The instructor panel's comparison series carries course weeks {weeks} and not "
            f"{course_week}, so there is no point to put a smuggled figure into."
        )
    return weeks.index(course_week)


class Smuggled(NamedTuple):
    """One smuggling run: what went in, what came out, and what the boundary did.

    **The assertions live in the test bodies rather than here**, and that is a
    rule rather than a preference: `scripts/ci/check_invariant_assertions.py`
    (E0-36 §3) does not chase helpers, so an `invariant`-marked test whose only
    `assert` sits in a shared function reads to the gate as a test that asserts
    nothing. This carries the evidence; each test says what it means.
    """

    before: Any
    served: Any
    what_happened: str | None
    member: str


def drive_one_member(
    door: ReportDoor,
    contract: Any,
    *,
    path: Sequence[Any] | Callable[[Any], Sequence[Any]],
    named: str,
) -> Smuggled:
    """Smuggle an unsealed figure into one member of a real report, and ask the boundary.

    **The report is the object the service builds, not a body re-validated from
    its own JSON**, which is the repair the ruling on
    `docs/disputes/E5-05-01.md` settles. A served body carries every figure as a
    plain mapping, and a figure rebuilt from a mapping can never carry the seal —
    it is a private attribute over the field values, deliberately not serialized,
    because a serialized seal is a forgeable one. So re-validating a payload that
    carries a *shown* figure is refused before any smuggling happens, for every
    implementation that satisfies criterion 1, and the tests would have had a
    second way to be green that has nothing to do with their subject.

    Starting from the service's own report also puts the test on the layer it
    says it is about: figures as sealed instances, crossing the revalidation the
    response performs over whatever the route hands back.

    Exactly one member is rewritten, with `model_copy(update=…)`, which runs no
    validator — so the object handed to the boundary is a report no validator has
    seen, and everything in it except that one member is what the service built.
    """
    report = an_instructor_report(door, contract, course_week=WEEK_CLEAR)
    resolved = tuple(path(report) if callable(path) else path)

    unsealed = an_unsealed_figure(contract.comparison_type(), figure=A_SMUGGLED_MEAN)
    smuggled = with_member_replaced(report, resolved, unsealed)

    # Read before the boundary is asked anything, so the canary the test asserts
    # describes what went in rather than whatever survived.
    before = smuggled.model_dump(mode="json")
    served, what_happened = through_the_boundary(type(report), smuggled, named=named)
    return Smuggled(
        before=before,
        served=served,
        what_happened=what_happened,
        member=".".join(str(step) for step in resolved),
    )


def reached_the_wire(outcome: Smuggled) -> bool:
    """Whether the smuggled figure came out the other side of the boundary."""
    return outcome.served is not None and carries_number(outcome.served, A_SMUGGLED_MEAN)


def the_canary_complaint(outcome: Smuggled) -> str:
    """What to say when the smuggle never carried the figure in the first place."""
    return (
        f"The report smuggled into `{outcome.member}` does not carry {A_SMUGGLED_MEAN} before any "
        f"boundary sees it: {outcome.before!r}. Until it does, this test asserts that a figure "
        "nobody planted is absent (`docs/MISTAKES.md` entry 3)."
    )


def the_wire_complaint(outcome: Smuggled) -> str:
    """What to say when it did reach the wire."""
    return (
        f"A comparison figure built past the constructor — no token, no chokepoint, no minimum ever "
        f"consulted — reached the serialized payload through `{outcome.member}`.\n\n"
        "§4.1 item 7 is a rule about what is shown, so the boundary that has to hold it is the one "
        "the payload crosses, at every depth a figure can sit. Work-order decision 4 puts a field "
        "validator calling `refuse_an_unsealed_comparison` on this member and "
        "`revalidate_instances` on the model that holds it; without them the member is a door "
        "beside the chokepoint. What the boundary did: "
        f"{outcome.what_happened or 'it served the payload'}."
    )


def test_a_series_points_mean_refuses_a_figure_the_chokepoint_never_sealed(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """The deepest of the three: a figure two objects and a list down.

    `streams.<stream>.benchmark.comparison.points[].mean` is where every trend
    line's numbers live, and it is the member a seal is most easily left off —
    the class is small, it is built in a loop, and a validator on it looks like
    ceremony until a caller assembles a point for itself.

    **The mutation this kills:** the `mean` field validator removed from the
    series-point model, that one alone. The two workload tests below stay green
    against that tree, which is what makes this test the one that reports it.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    outcome = drive_one_member(
        report_door,
        report_api_contract,
        path=lambda report: (*SERIES_PATH, a_point_index(report, WEEK_CLEAR), POINT_MEAN_FIELD),
        named=POINT_MEAN_FIELD,
    )

    assert carries_number(outcome.before, A_SMUGGLED_MEAN), the_canary_complaint(outcome)
    assert not reached_the_wire(outcome), the_wire_complaint(outcome)


def test_the_workload_benchmarks_mean_refuses_a_figure_the_chokepoint_never_sealed(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """The workload mean, §5.1's "true numeric statistic" against the comparison set.

    **The mutation this kills:** the `mean` field validator removed from the
    workload-figures model, that one alone — leaving the median sealed beside it,
    which is how a half-sealed model reads to a reviewer as a sealed one.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    outcome = drive_one_member(
        report_door,
        report_api_contract,
        path=(WORKLOAD_BENCHMARK_MEMBER, COMPARISON_POPULATION, MEAN_FIELD),
        named=MEAN_FIELD,
    )

    assert carries_number(outcome.before, A_SMUGGLED_MEAN), the_canary_complaint(outcome)
    assert not reached_the_wire(outcome), the_wire_complaint(outcome)


def test_the_workload_benchmarks_median_refuses_a_figure_the_chokepoint_never_sealed(
    report_door: ReportDoor, report_api_contract: Any, benchmark_cohort: Callable[..., Any]
) -> None:
    """The median, which §4.1 item 7 names in the same breath as the mean.

    > a mean, a median, or any other statistic, not only a drawn line

    **The mutation this kills:** the `median` field validator removed, that one
    alone. It is the member most likely to be forgotten, because a model with one
    sealed field beside one unsealed one passes every reading eye and every test
    that drives the other field.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    outcome = drive_one_member(
        report_door,
        report_api_contract,
        path=(WORKLOAD_BENCHMARK_MEMBER, COMPARISON_POPULATION, MEDIAN_FIELD),
        named=MEDIAN_FIELD,
    )

    assert carries_number(outcome.before, A_SMUGGLED_MEAN), the_canary_complaint(outcome)
    assert not reached_the_wire(outcome), the_wire_complaint(outcome)
