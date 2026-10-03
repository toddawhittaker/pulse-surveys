"""E5's benchmark sketch and E5-05's schema say the same thing, or differ on purpose.

E5's breakdown decision 8: the frontend tickets "build against fixtures shaped
like the sketch below and never wait on the backend", and "E5-05's Pydantic
schema is the authority the moment it merges". E4's own reconciliation module
holds the two to each other at the top level and at three nested members; this
one does the same job for the members E5-05 adds, which sit deeper than anything
that module reads: a series inside a stream's benchmark, a point inside that
series, and the two figures inside each workload population.

**Two divergences are declared here, both settled by E5-05's work order (decision
3) and recorded in its ADR.** Neither is a repair for a red:

  - **No series-level `suppressed` flag.** The sketch gives each series a
    `suppressed` and a `reason`; the service seals **per week** (E5-04 criterion
    7), so a whole-series flag would be a figure computed outside the chokepoint.
    A suppressed week is a present point whose `mean` is a suppressed figure.
  - **No flat workload figures.** The sketch gives each workload population a
    `suppressed` beside a bare `mean` and `median`; both statistics are sealed
    `ComparisonFigure`s instead, each suppressible on its own, because §4.1 item 7
    covers "a mean, a median, or any other statistic".

The top-level `workload_benchmark` member is a divergence from **E4's** sketch,
which is the one `test_the_payload_sketch_and_the_schema_are_reconciled.py`
reads; it is declared there, in that module's `DECLARED_DIVERGENCES`, not here.

**The canary** (`docs/MISTAKES.md` entry 3): the sketch heading and the fenced
block are located by strings copied whole out of `docs/tickets/e5/README.md`, and
every test asserts the sketch's own members before comparing them with the
schema's — so a reader that has gone blind says so rather than reporting two
sides that agree because both are empty.
"""

import json
import re
import typing
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BREAKDOWN = REPO_ROOT / "docs" / "tickets" / "e5" / "README.md"

# Copied whole from the file, the line the section starts on included.
SKETCH_HEADING = "## The payload sketch the frontend builds against"

FENCED_JSON = re.compile(r"```json\n(.*?)\n```", re.DOTALL)

# The sketch's own spelling of the members this ticket ships.
STREAMS_MEMBER = "streams"
INSTRUCTOR_KEY = "instructor"
BENCHMARK_MEMBER = "benchmark"
COMPARISON_POPULATION = "comparison"
UNIVERSITY_POPULATION = "university"
POINTS_FIELD = "points"
WORKLOAD_BENCHMARK_MEMBER = "workload_benchmark"
MEAN_FIELD = "mean"
MEDIAN_FIELD = "median"

# The two divergences, as sets of sketch members the schema deliberately does not
# carry. Widening either is a deliberate act with a sentence beside it.
SERIES_DIVERGENCE = frozenset({"suppressed", "reason"})
WORKLOAD_DIVERGENCE = frozenset({"suppressed"})


def sketch_section() -> str:
    """The text of the breakdown's payload-sketch section, heading to next heading."""
    assert BREAKDOWN.is_file(), f"{BREAKDOWN} does not exist, so this test read nothing."
    text = BREAKDOWN.read_text(encoding="utf-8")
    at = text.find(SKETCH_HEADING)
    assert at >= 0, (
        f"{BREAKDOWN.relative_to(REPO_ROOT)} carries no line {SKETCH_HEADING!r}. That heading is "
        "the anchor every assertion here stands on; a reader that cannot find the section would "
        "otherwise report a sketch with no members at all."
    )
    after = text.find("\n## ", at + len(SKETCH_HEADING))
    return text[at:] if after < 0 else text[at:after]


def sketched_payload() -> dict[str, Any]:
    """The sketch's own JSON object, parsed out of its fenced block."""
    blocks = FENCED_JSON.findall(sketch_section())
    assert len(blocks) == 1, (
        f"The sketch section holds {len(blocks)} fenced `json` blocks; this test reads the one that "
        "is the payload contract."
    )
    return json.loads(blocks[0])


def sketched(*path: str) -> dict[str, Any]:
    """One object out of the sketch, by the path it sits at, with a message if it is not there."""
    here: Any = sketched_payload()
    walked: list[str] = []
    for name in path:
        assert isinstance(here, dict) and name in here, (
            f"The sketch carries no `{'.'.join(path)}`: at `{'.'.join(walked) or '.'}` it holds "
            f"{sorted(here) if isinstance(here, dict) else here!r}. These members are what E5-07, "
            "E5-08 and E5-10 build their fixtures from, so a sketch that has stopped describing "
            "them is the reconciliation failing from the sketch's side."
        )
        here = here[name]
        walked.append(name)
    assert isinstance(here, dict), f"The sketch's `{'.'.join(path)}` is {here!r}, not an object."
    return here


def peeled(annotation: Any) -> Any:
    """One annotation's single underlying class: `X | None`, `list[X]` and `Annotated[X, …]`."""
    while True:
        arguments = [
            argument for argument in typing.get_args(annotation) if argument is not type(None)
        ]
        if typing.get_origin(annotation) is None or not arguments:
            return annotation
        annotation = arguments[0]


def model_carrying(schema: Any, field: str, contract: Any) -> Any:
    """The one model in the schema module declaring `field`."""
    models = [
        value
        for name, value in vars(schema).items()
        if not name.startswith("_")
        and isinstance(value, type)
        and field in (getattr(value, "model_fields", None) or {})
    ]
    assert len(models) == 1, (
        f"`{contract.schema_module_name}` declares {len(models)} models carrying `{field}` "
        f"({[model.__name__ for model in models]}); this test reads the one that does."
    )
    return models[0]


def model_behind(owner: Any, member: str) -> Any:
    """The model one member of a model is annotated with."""
    field = (getattr(owner, "model_fields", None) or {}).get(member)
    assert field is not None, (
        f"`{owner.__name__}` declares {sorted(getattr(owner, 'model_fields', None) or {})} and no "
        f"`{member}`. E5-05's work order settles the wire shape member by member."
    )
    annotation = peeled(field.annotation)
    assert isinstance(annotation, type), (
        f"`{owner.__name__}.{member}` is annotated {field.annotation!r}, which is not a single "
        "class this test can ask for its fields."
    )
    return annotation


def stream_model(contract: Any) -> Any:
    """The model one stream of the payload is served as."""
    return model_carrying(contract.schema(), contract.distribution_field, contract)


def test_each_streams_benchmark_member_names_the_two_populations_the_sketch_does(
    report_api_contract: Any,
) -> None:
    """The panel's own member: a comparison series and a university series, and nothing else.

    SPEC §5.1's stacked pair carries "three lines — this section (hero), the
    **comparison set**, and **university-wide**"; the hero's line is E4's `trend`,
    and these two are what E5-05 adds beside it. The equality runs in both
    directions, because a member in the schema and not in the sketch is a payload
    E5-07's fixtures do not describe, and one in the sketch and not in the schema
    is a chart drawing a line that will never arrive.

    **The mutation this kills:** the university series dropped from the schema
    while the comparison one lands — two lines per panel where §5.1 asks for
    three, and a sketch that goes on promising the third.
    """
    sketched_benchmark = set(sketched(STREAMS_MEMBER, INSTRUCTOR_KEY, BENCHMARK_MEMBER))
    assert sketched_benchmark == {COMPARISON_POPULATION, UNIVERSITY_POPULATION}, (
        f"The sketch's stream benchmark describes {sorted(sketched_benchmark)}; this test is "
        f"written against `{COMPARISON_POPULATION}` and `{UNIVERSITY_POPULATION}`."
    )

    benchmark = model_behind(stream_model(report_api_contract), BENCHMARK_MEMBER)
    declared = set(benchmark.model_fields)
    assert declared == sketched_benchmark, (
        f"`{benchmark.__name__}` declares {sorted(declared)}; the sketch describes "
        f"{sorted(sketched_benchmark)}. In the schema and not in the sketch: "
        f"{sorted(declared - sketched_benchmark)}; in the sketch and not in the schema: "
        f"{sorted(sketched_benchmark - declared)}."
    )


def test_a_benchmark_series_carries_its_points_and_neither_series_level_flag(
    report_api_contract: Any,
) -> None:
    """The first declared divergence: suppression is per week, so a series has no flag.

    E5-05's work order, decision 3: "the service seals per week (E5-04 criterion
    7) and a whole-series flag would be a figure computed outside the chokepoint.
    A suppressed week is a present point whose `mean` is a suppressed
    `ComparisonFigure`."

    A flag on the series is not a harmless extra: it is a statement about the
    whole set that nothing sealed, and the natural way to compute it is to look at
    the counts once — which is precisely the per-report suppression decision
    criterion 4 exists to forbid.

    **The mutation this kills:** `suppressed` and `reason` mirrored onto the
    series model "so the frontend has something simple to read", which restores a
    figure computed outside the chokepoint and makes a per-week seal invisible to
    anything drawing the panel.
    """
    sketched_series = set(sketched(STREAMS_MEMBER, INSTRUCTOR_KEY, BENCHMARK_MEMBER, "comparison"))
    assert sketched_series >= SERIES_DIVERGENCE, (
        f"The sketch's comparison series describes {sorted(sketched_series)} and carries neither "
        f"of {sorted(SERIES_DIVERGENCE)}, so there is no divergence here and this test is about "
        "nothing. If the sketch has been rewritten, this module's `SERIES_DIVERGENCE` and this "
        "test move together."
    )

    benchmark = model_behind(stream_model(report_api_contract), BENCHMARK_MEMBER)
    series = model_behind(benchmark, COMPARISON_POPULATION)
    declared = set(series.model_fields)

    assert declared == sketched_series - SERIES_DIVERGENCE, (
        f"`{series.__name__}` declares {sorted(declared)}; the sketch describes "
        f"{sorted(sketched_series)} and E5-05's decision 3 drops {sorted(SERIES_DIVERGENCE)} from "
        f"it. Unaccounted for: {sorted(declared - sketched_series)}; missing: "
        f"{sorted(sketched_series - SERIES_DIVERGENCE - declared)}."
    )
    assert POINTS_FIELD in declared, (
        f"`{series.__name__}` declares {sorted(declared)} and no `{POINTS_FIELD}`, so there is "
        "nowhere for a week's figure to sit."
    )
    assert model_behind(benchmark, UNIVERSITY_POPULATION) is series, (
        "The comparison series and the university series are different models "
        f"(`{series.__name__}` and `{model_behind(benchmark, UNIVERSITY_POPULATION).__name__}`). "
        "One shape answers for both lines; two would let a rule land on one of them."
    )


def test_a_series_point_names_its_course_week_and_carries_a_sealed_mean(
    report_api_contract: Any,
) -> None:
    """The point itself, and the type its figure is: the sketch's two members, sealed.

    E5-05's work order, decision 2: "Every figure is a `ComparisonFigure` sealed
    by the chokepoint, at every depth". A point whose `mean` is a bare float is a
    figure any caller can assemble, which is the chokepoint with a door beside it
    — the structural half of criterion 2, asserted here where the annotation lives
    rather than by driving a payload.

    **The mutation this kills:** the point typed `mean: float | None` with the
    suppression carried "somewhere else" — which type-checks, renders, and puts
    §4.1 item 7 back in the hands of whoever remembers it.
    """
    sketched_point = sketched_payload()[STREAMS_MEMBER][INSTRUCTOR_KEY][BENCHMARK_MEMBER][
        COMPARISON_POPULATION
    ][POINTS_FIELD]
    assert sketched_point, "The sketch's comparison series holds no points; this test reads one."
    sketched_keys = set(sketched_point[0])

    benchmark = model_behind(stream_model(report_api_contract), BENCHMARK_MEMBER)
    series = model_behind(benchmark, COMPARISON_POPULATION)
    point = model_behind(series, POINTS_FIELD)
    declared = set(point.model_fields)

    assert declared == sketched_keys, (
        f"`{point.__name__}` declares {sorted(declared)}; the sketch's point describes "
        f"{sorted(sketched_keys)}. In the schema and not in the sketch: "
        f"{sorted(declared - sketched_keys)}; in the sketch and not in the schema: "
        f"{sorted(sketched_keys - declared)}. A count or a section total added here is the "
        "disclosure §4.1 item 7 exists to prevent, whatever the figure beside it says."
    )
    assert model_behind(point, MEAN_FIELD) is report_api_contract.comparison_type(), (
        f"`{point.__name__}.{MEAN_FIELD}` is annotated "
        f"{point.model_fields[MEAN_FIELD].annotation!r}, and the sealed comparison type is "
        f"`{report_api_contract.comparison_type().__name__}`. Every figure at every depth is "
        "produced by the chokepoint and typed as what the chokepoint returns."
    )


def test_the_workload_benchmark_member_carries_a_sealed_mean_and_median_per_population(
    report_api_contract: Any,
) -> None:
    """The second declared divergence: two sealed statistics in place of a flat, flagged pair.

    The sketch gives each workload population `{suppressed, mean, median}` — one
    flag over two numbers. E5-05's decision 3 replaces it with two sealed figures,
    each suppressible on its own, because §4.1 item 7 names them separately: "a
    mean, a median, or any other statistic, not only a drawn line". E5-08's
    StatPair already renders each column "independently suppressible".

    **The mutation this kills:** one `suppressed` flag kept over both statistics,
    which makes a median shown where its mean was suppressed impossible to express
    and — the dangerous direction — a mean shown where the median's own counts
    would have suppressed it.
    """
    schema = report_api_contract.schema()
    payload = model_carrying(schema, report_api_contract.streams_member, report_api_contract)

    sketched_workload = set(sketched(WORKLOAD_BENCHMARK_MEMBER))
    assert sketched_workload == {COMPARISON_POPULATION, UNIVERSITY_POPULATION}, (
        f"The sketch's `{WORKLOAD_BENCHMARK_MEMBER}` describes {sorted(sketched_workload)}; this "
        f"test is written against the two populations."
    )
    workload = model_behind(payload, WORKLOAD_BENCHMARK_MEMBER)
    assert set(workload.model_fields) == sketched_workload, (
        f"`{workload.__name__}` declares {sorted(workload.model_fields)}; the sketch describes "
        f"{sorted(sketched_workload)}."
    )

    sketched_figures = set(sketched(WORKLOAD_BENCHMARK_MEMBER, COMPARISON_POPULATION))
    assert sketched_figures >= WORKLOAD_DIVERGENCE, (
        f"The sketch's workload population describes {sorted(sketched_figures)} and carries none "
        f"of {sorted(WORKLOAD_DIVERGENCE)}, so this divergence is about nothing."
    )

    comparison = model_behind(workload, COMPARISON_POPULATION)
    declared = set(comparison.model_fields)
    assert declared == sketched_figures - WORKLOAD_DIVERGENCE, (
        f"`{comparison.__name__}` declares {sorted(declared)}; the sketch describes "
        f"{sorted(sketched_figures)} and E5-05's decision 3 drops {sorted(WORKLOAD_DIVERGENCE)} "
        "from it, sealing each statistic on its own instead. Unaccounted for: "
        f"{sorted(declared - sketched_figures)}; missing: "
        f"{sorted(sketched_figures - WORKLOAD_DIVERGENCE - declared)}."
    )
    for name in (MEAN_FIELD, MEDIAN_FIELD):
        assert model_behind(comparison, name) is report_api_contract.comparison_type(), (
            f"`{comparison.__name__}.{name}` is annotated "
            f"{comparison.model_fields[name].annotation!r}; the sealed comparison type is "
            f"`{report_api_contract.comparison_type().__name__}`. §4.1 item 7 covers a mean and a "
            "median alike, and a statistic typed as a bare number is one nothing sealed."
        )
    assert model_behind(workload, UNIVERSITY_POPULATION) is comparison, (
        "The workload comparison figures and the university figures are different models. One "
        "shape answers for both populations."
    )
