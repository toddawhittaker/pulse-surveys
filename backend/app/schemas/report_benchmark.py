"""SPEC §5.1's comparison and university figures, as the instructor's report serves them.

Five models, and every one of them is a holder for figures
`app.services.reporting.comparison_after_suppression` produced. SPEC §5.1 gives
each panel "three lines — this section (hero), the **comparison set**, and
**university-wide**" and puts the week's workload mean and median "against
comparison-set and university figures" beside the charts; E4 shipped the report
with one suppressed `comparison` member standing in for all of it, and E5-05 is
where the real figures arrive.

**Why these five models are not in `app/schemas/report.py` beside the rest of the
payload.** Two of them — `StreamBenchmark` and `WorkloadBenchmarkView` — declare
a member called `comparison`, and so does `InstructorReport`. E4-07 settled the
way the item-7 chokepoint is *found*: the sealed comparison type is whatever the
one model in `app.schemas.report` carrying a `comparison` member annotates it
with, so that the guarantee is stated as a property of the module rather than as
a class name anybody can copy (`tests/fixtures/report_api.py::comparison_field_type`
and `app.schemas.report`'s own docstring). Three models with that member in one
module makes that question unanswerable. Keeping the new holders here, and
importing this module rather than its classes into the report schema, leaves
`app.schemas.report` with exactly one `comparison` member — the top-level one —
and the discovery intact. [ADR 0170](../../../docs/adr/0170-a-benchmark-figure-is-sealed-at-every-point-and-the-e4-comparison-member-stays.md)
records it.

**Every figure at every depth is a `ComparisonFigure`, and every model that holds
one re-checks it.** SPEC §4.1 item 7 is a rule about what is *shown*, so the
boundary is the wire and not the constructor; `app.schemas.report`'s docstring
carries the three rounds of review that established it. What that means here is
two lines per holder, and neither is ceremony:

  - a `mode="after"` field validator per figure member, calling
    `refuse_an_unsealed_comparison` — one validator per member rather than one
    covering several, so that removing the seal from a single member is a
    single test going red;
  - `revalidate_instances="always"` on every model on the path from
    `InstructorReport` down to a figure, because pydantic accepts an instance of
    a nested model without re-validating it unless that model asks to be
    re-validated. A validator on a leaf that nothing on the path revalidates is
    a validator a caller walks past with `model_construct` one level up, which
    is exactly what E4-07's review found the first two times.

**There is no series-level `suppressed` flag and no flag over the workload
pair**, and both absences are deliberate. E5's payload sketch carries them;
E5-04 seals a comparison figure per week and per statistic, so a whole-series or
whole-pair flag would be a figure computed outside the chokepoint by whoever
assembled it. A suppressed week is a point that is present and whose `mean` says
it is suppressed, and a suppressed workload statistic is one of the two figures
saying so on its own. Both divergences are declared in
`tests/unit/test_the_benchmark_payload_sketch_and_the_schema_are_reconciled.py`
and argued in ADR 0170.
"""

from pydantic import BaseModel, ConfigDict, field_validator

from app.services.reporting import ComparisonFigure, refuse_an_unsealed_comparison

__all__ = [
    "BenchmarkSeries",
    "BenchmarkSeriesPoint",
    "StreamBenchmark",
    "WorkloadBenchmarkFigures",
    "WorkloadBenchmarkView",
]


class BenchmarkSeriesPoint(BaseModel):
    """One course week of one comparison line, and the sealed mean for that week.

    **A suppressed week is a point, not an absence.** E5-04 decides suppression
    week by week from that week's own contributors, so a week below either
    minimum arrives here with a suppressed figure in `mean` rather than being
    left out of the series: a gap in a chart invites the reader to conclude that
    nothing happened that week, and the notice §4.1 item 5 governs says something
    else entirely.

    Nothing else sits on a point. A count of sections or of respondents beside
    the week would hand back the inference the minimum exists to prevent, whether
    or not the figure beside it is shown.
    """

    model_config = ConfigDict(frozen=True, revalidate_instances="always")

    course_week: int
    mean: ComparisonFigure

    @field_validator("mean")
    @classmethod
    def _the_mean_is_the_helpers(cls, figure: ComparisonFigure) -> ComparisonFigure:
        """SPEC §4.1 item 7 at the deepest point a comparison figure sits."""
        refuse_an_unsealed_comparison(figure)
        return figure


class BenchmarkSeries(BaseModel):
    """One comparison line: the weeks it covers, each carrying its own sealed figure.

    One model answers for both populations, so a rule cannot land on the
    comparison-set line and miss the university one.
    """

    model_config = ConfigDict(frozen=True, revalidate_instances="always")

    points: list[BenchmarkSeriesPoint]


class StreamBenchmark(BaseModel):
    """The second and third of SPEC §5.1's three lines, for one of the two panels.

    The first line is the section's own, which is `StreamReport.trend`; these two
    are what it is read against. Both populations are served for both panels,
    because §5.1's stacked pair carries three lines each.
    """

    model_config = ConfigDict(frozen=True, revalidate_instances="always")

    comparison: BenchmarkSeries
    university: BenchmarkSeries


class WorkloadBenchmarkFigures(BaseModel):
    """One population's workload mean and median for the reported week, each sealed alone.

    SPEC §4.1 item 7 covers "a mean, a median, or any other statistic, not only a
    drawn line", so the two are suppressed independently and neither rides on the
    other's decision. The two validators below are separate functions for the
    same reason: one validator naming both members would be one thing to delete.
    """

    model_config = ConfigDict(frozen=True, revalidate_instances="always")

    mean: ComparisonFigure
    median: ComparisonFigure

    @field_validator("mean")
    @classmethod
    def _the_mean_is_the_helpers(cls, figure: ComparisonFigure) -> ComparisonFigure:
        """SPEC §4.1 item 7 over the workload mean."""
        refuse_an_unsealed_comparison(figure)
        return figure

    @field_validator("median")
    @classmethod
    def _the_median_is_the_helpers(cls, figure: ComparisonFigure) -> ComparisonFigure:
        """SPEC §4.1 item 7 over the workload median, which item 7 names beside the mean."""
        refuse_an_unsealed_comparison(figure)
        return figure


class WorkloadBenchmarkView(BaseModel):
    """§5.1's workload statistics against both populations, for the week being reported.

    "workload mean/median for the section against comparison-set and
    university figures (true numeric statistics — §3.2)". The section's own pair
    is `InstructorReport.workload`; this is what stands beside it.
    """

    model_config = ConfigDict(frozen=True, revalidate_instances="always")

    comparison: WorkloadBenchmarkFigures
    university: WorkloadBenchmarkFigures
