"""The sketch and the schema say the same thing — ticket E4-07, criterion 8.

> The response schema and the README sketch are reconciled: divergences are
> deliberate, listed in the PR body, and the sketch section gets a pointer to the
> schema as authority.

E4's breakdown decision 5 is why this is a criterion rather than a courtesy: the
four frontend tickets "build against fixtures shaped like the sketch below and
never wait on the backend", and "E4-07's Pydantic schema is the authority the
moment it merges". A sketch that quietly stops describing the schema is a set of
component fixtures describing a payload that does not exist, discovered in E4-11
when the two are joined.

Half of the criterion is a pull-request obligation and is not assertable here —
"listed in the PR body" is a claim about a document this suite cannot see. The
two halves that *are* assertable are both here: the sketch section names the
schema as the authority, and the schema's own top-level members are the sketch's
plus exactly the divergences E4-07's work order settles.

**The divergences are named as a closed set on purpose.** Work-order decision 4
settles two — `rates.valid_responses` and the top-level
`released_from_earlier_weeks` — and a third that arrives without a record is
exactly what criterion 8 exists to catch. Widening `DECLARED_DIVERGENCES` is
therefore a deliberate act with a sentence beside it, never a repair for a red.

**The canary** (`docs/MISTAKES.md` entry 3): the sketch heading and the fenced
block are located by strings copied whole out of `docs/tickets/e4/README.md`, and
a reader that finds neither says so rather than reporting a file with no
divergences.

**E4-19 adds a third reconciliation, one level further down than the second.**
Breakdown decision 12 puts `term_week` inside each point of `streams.instructor
.trend` and `streams.course.trend`, a list nested two members deep that neither
the top-level test nor the rates test below it reads — so criterion 3's own
claim, "the reconciliation test holds the two to each other in both directions,
so neither may move alone," has nowhere to stand without a third test reaching
that depth.

**E5-02 adds two more of the same shape, and one top-level divergence.** That
ticket's members sit at three different depths: `institution_timezone` at the top
(so it joins `DECLARED_DIVERGENCES`), `closes_at` inside `week`, and
`question_text` inside each stream. The two nested ones get a test each, for the
reason E4-19's did — the top-level equality cannot see a member one object down,
and a sketch that stops describing the streams is a set of frontend fixtures
describing a payload that does not arrive.
"""

import json
import re
import typing
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BREAKDOWN = REPO_ROOT / "docs" / "tickets" / "e4" / "README.md"

# The heading the sketch sits under, copied whole from the file — the line the
# sentence starts on included, which is `docs/MISTAKES.md` entry 3's rule about
# building a canary sample.
SKETCH_HEADING = "## The payload sketch the frontend builds against"

# The path a pointer has to name for the sketch to say where the authority is.
# E4-07's work order settles the module: "Schema: new `backend/app/schemas/
# report.py`, mirroring the README sketch".
SCHEMA_PATH = "backend/app/schemas/report.py"

# The two members work-order decision 4 settles as deliberate departures from the
# sketch, with its own reasons: `valid_responses` because E4-09's components
# consume the count and the sketch omitted it, and the released list because
# ADR 0152 says E4-07 places it and the sketch predates that record.
#
# `institution_timezone` is E5-02's, and is the first entry here that no E4
# record settles: that ticket puts the IANA name of the institution's zone on the
# payload's top level, mirroring the student payload, because the week's close
# instant is rendered in the institution's zone and never in the browser's guess.
# It is a divergence rather than a sketch edit because the sketch is E4's frozen
# record and E5-02's work order (decision 1) names this test's own documented
# escape as where the member is declared.
DECLARED_DIVERGENCES = frozenset({"released_from_earlier_weeks", "institution_timezone"})

# Where the first of those two sits, since it is not a top-level member.
RATES_MEMBER = "rates"
RATES_DIVERGENCE = "valid_responses"

# E5-02's other two members, each one level down from the top: the reported
# week's own close instant on the `week` member, and the served text of a
# stream's rating question on each stream. Neither is visible to the top-level
# equality above, which is the same gap E4-19's `term_week` had.
WEEK_MEMBER = "week"
WEEK_DIVERGENCE = "closes_at"
STREAMS_MEMBER = "streams"
STREAM_DIVERGENCE = "question_text"

FENCED_JSON = re.compile(r"```json\n(.*?)\n```", re.DOTALL)


def sketch_section() -> str:
    """The text of the breakdown's payload-sketch section, heading to next heading."""
    assert BREAKDOWN.is_file(), f"{BREAKDOWN} does not exist, so this test read nothing."
    text = BREAKDOWN.read_text(encoding="utf-8")
    at = text.find(SKETCH_HEADING)
    assert at >= 0, (
        f"{BREAKDOWN.relative_to(REPO_ROOT)} carries no line {SKETCH_HEADING!r}. That heading is "
        "the anchor both assertions in this module stand on; if the section has been renamed, "
        "`SKETCH_HEADING` in this module is the one line that changes — a reader that cannot find "
        "the section would otherwise report it as carrying no pointer and no members."
    )
    after = text.find("\n## ", at + len(SKETCH_HEADING))
    return text[at:] if after < 0 else text[at:after]


def sketched_payload() -> dict[str, Any]:
    """The sketch's own JSON object, parsed out of its fenced block."""
    section = sketch_section()
    blocks = FENCED_JSON.findall(section)
    assert len(blocks) == 1, (
        f"The sketch section holds {len(blocks)} fenced `json` blocks; this test reads the one that "
        "is the payload contract."
    )
    return json.loads(blocks[0])


def test_the_sketch_section_names_the_schema_as_the_authority_over_it() -> None:
    """Criterion 8's assertable half of the pointer: the sketch says where the truth is.

    Breakdown decision 5 already says the schema wins from the moment it merges,
    and it says so in a decisions list at the top of a long file. The pointer
    belongs beside the sketch itself, because the reader who needs it is the one
    building a fixture off the JSON block — E4-08 through E4-11 — and that reader
    is looking at the block rather than at decision 5.

    **The mutation this kills:** the schema shipped and the sketch left exactly as
    it was, which is the state this repository's most-caught mistake describes —
    a record going on asserting something the change had made false
    (`docs/MISTAKES.md` entry 1). The sketch would then read as a contract while
    being a draft.
    """
    section = sketch_section()
    assert SCHEMA_PATH in section, (
        f"The payload-sketch section of {BREAKDOWN.relative_to(REPO_ROOT)} does not name "
        f"`{SCHEMA_PATH}`. Criterion 8: the sketch section gets a pointer to the schema as "
        "authority, in the same pull request that ships the schema. The section reads:\n\n"
        f"{section[:600]}"
    )


def test_the_schemas_top_level_members_are_the_sketchs_plus_the_declared_divergences(
    report_api_contract: Any,
) -> None:
    """The reconciliation itself, as an equality rather than as a subset.

    An equality in both directions, because the two failures it stands between are
    different and both matter: a member in the schema and not in the sketch is a
    payload the frontend fixtures do not describe, and a member in the sketch and
    not in the schema is a fixture describing a payload that will never arrive.
    Criterion 8 asks for divergences to be *deliberate*, and a set written down
    here with a record behind each entry is what deliberate means when the
    reviewer is a test.

    **The mutation this kills:** a member added to the schema during the build —
    a `generated_at`, a `section_id`, a `has_comments` — with the sketch and the
    pull-request body both untouched. **The near miss:** a member renamed rather
    than added, which the equality catches from both sides at once.
    """
    sketched = set(sketched_payload())
    schema = report_api_contract.schema()
    models = [
        value
        for name, value in vars(schema).items()
        if not name.startswith("_")
        and isinstance(value, type)
        and set(getattr(value, "model_fields", None) or {}) >= {report_api_contract.streams_member}
    ]
    assert len(models) == 1, (
        f"`{report_api_contract.schema_module_name}` declares {len(models)} models carrying a "
        f"`{report_api_contract.streams_member}` member "
        f"({[model.__name__ for model in models]}). This test reads the report payload's own model, "
        "and the sketch's `streams` is what identifies it."
    )
    declared = set(models[0].model_fields)

    assert declared == sketched | DECLARED_DIVERGENCES, "\n".join(
        [
            f"`{models[0].__name__}` declares {sorted(declared)}.",
            f"The sketch describes {sorted(sketched)}.",
            f"The divergences E4-07's work order settles are {sorted(DECLARED_DIVERGENCES)}.",
            "",
            "In the schema and not accounted for: "
            f"{sorted(declared - sketched - DECLARED_DIVERGENCES)}",
            f"In the sketch and not in the schema: {sorted(sketched - declared)}",
            "",
            "Criterion 8: divergences are deliberate and listed in the pull request body. A member "
            "added here without a record is what the frontend fixtures will not describe; one "
            "dropped is what E4-08 through E4-11 have already built against.",
        ]
    )


def sketched_trend_point(stream_key: str) -> dict[str, Any]:
    """One trend point out of the sketch's own JSON, for the stream named."""
    payload = sketched_payload()
    trend = payload["streams"][stream_key]["trend"]
    assert (
        trend
    ), f"The sketch's `streams.{stream_key}.trend` is empty; this test reads its first point."
    return trend[0]


def test_the_trend_points_term_week_is_named_on_both_sides_of_the_sketch_and_the_schema(
    report_api_contract: Any,
) -> None:
    """E4-19 criterion 3, one level further down than the rates test below.

    Neither equality test above reaches this: the top-level test compares the
    payload's own members, and the rates test is one level down from those,
    `rates` itself. E4-19's `term_week` (breakdown decision 12) lands inside
    each point of `streams.instructor.trend` and `streams.course.trend` — a
    list nested two members deep that neither of those tests reads. Criterion
    3's own words are "the sketch-reconciliation test passes with the member
    present on both sides, and reds if either side drops it" — which this test
    is, or nothing in this module is.

    **The mutation this kills:** the schema's `TrendPoint` gains `term_week`
    and the sketch's fenced trend example is left exactly as it was, or the
    reverse. Asserting membership on each side before comparing the two sets
    is what pins a failure to the side that stood still, rather than reporting
    the two sides equal because both still lack the member.
    """
    sketch_point = sketched_trend_point(
        report_api_contract.payload_stream_key[report_api_contract.instructor_stream]
    )
    sketch_keys = set(sketch_point)

    schema = report_api_contract.schema()
    trend_point_model = getattr(schema, "TrendPoint", None)
    assert trend_point_model is not None, (
        f"`{report_api_contract.schema_module_name}` declares no `TrendPoint`. E4-19's ticket names "
        "it directly: `term_week: int` lands on `app.schemas.report.TrendPoint`, populated in "
        "`_payload`'s trend builder from the `_SectionWeek` row in hand."
    )
    schema_keys = set(getattr(trend_point_model, "model_fields", None) or {})

    assert report_api_contract.term_week_field in schema_keys, (
        f"`TrendPoint` declares {sorted(schema_keys)}, with no "
        f"`{report_api_contract.term_week_field}`. Breakdown decision 12: the trend point gains the "
        "term week of the window row it was built from, so the chart's §2.2 sub-label has a wire "
        "source."
    )
    assert report_api_contract.term_week_field in sketch_keys, (
        f"The sketch's trend example is {sorted(sketch_keys)}, with no "
        f"`{report_api_contract.term_week_field}`. E4-19's scope is explicit: the sketch gains the "
        "member in the same change as the schema — neither may move alone."
    )
    assert schema_keys == sketch_keys, "\n".join(
        [
            f"`TrendPoint` declares {sorted(schema_keys)}.",
            f"The sketch's trend example describes {sorted(sketch_keys)}.",
            "No divergence is recorded for this member, so the two are supposed to name exactly "
            "the same fields.",
            f"In the schema and not in the sketch: {sorted(schema_keys - sketch_keys)}",
            f"In the sketch and not in the schema: {sorted(sketch_keys - schema_keys)}",
        ]
    )


def test_the_rates_member_gains_the_count_the_work_order_adds_to_the_sketch(
    report_api_contract: Any,
) -> None:
    """The other declared divergence, one level down from the top.

    Work-order decision 4: "`rates` gains `valid_responses` (E4-09's components
    consume it; the sketch omitted it — the recorded E4-09 deferral). Its source is
    `response.is_valid` per ADR 0147, never `classification`." The top-level
    equality above cannot see it, because `rates` is one object down.

    **The mutation this kills:** the divergence recorded in the pull request body
    and not built, which leaves E4-09 rendering a ratio it cannot label.
    """
    sketched_rates = set(sketched_payload()[RATES_MEMBER])
    assert RATES_DIVERGENCE not in sketched_rates, (
        f"The sketch's `{RATES_MEMBER}` already carries `{RATES_DIVERGENCE}` "
        f"({sorted(sketched_rates)}), so it is not a divergence and this test is about nothing. If "
        "the sketch has been updated to include it, this module's `DECLARED_DIVERGENCES` and this "
        "test move together."
    )

    schema = report_api_contract.schema()
    holders = [
        value
        for name, value in vars(schema).items()
        if not name.startswith("_")
        and isinstance(value, type)
        and set(getattr(value, "model_fields", None) or {})
        >= {report_api_contract.response_rate_field}
    ]
    assert len(holders) == 1, (
        f"`{report_api_contract.schema_module_name}` declares {len(holders)} models carrying a "
        f"`{report_api_contract.response_rate_field}` member "
        f"({[holder.__name__ for holder in holders]}); this test reads the rates model."
    )
    declared = set(holders[0].model_fields)
    assert declared == sketched_rates | {RATES_DIVERGENCE}, (
        f"`{holders[0].__name__}` declares {sorted(declared)}; the sketch's `{RATES_MEMBER}` "
        f"describes {sorted(sketched_rates)} and the work order adds `{RATES_DIVERGENCE}` to it. "
        f"Unaccounted for: {sorted(declared - sketched_rates - {RATES_DIVERGENCE})}; missing: "
        f"{sorted((sketched_rates | {RATES_DIVERGENCE}) - declared)}."
    )


def model_carrying(schema: Any, field: str, report_api_contract: Any) -> Any:
    """The one model in the schema module declaring `field`, or a failure naming the count."""
    models = [
        value
        for name, value in vars(schema).items()
        if not name.startswith("_")
        and isinstance(value, type)
        and field in (getattr(value, "model_fields", None) or {})
    ]
    assert len(models) == 1, (
        f"`{report_api_contract.schema_module_name}` declares {len(models)} models carrying "
        f"`{field}` ({[model.__name__ for model in models]}); this test reads the one that does."
    )
    return models[0]


def model_behind_member(schema: Any, member: str, report_api_contract: Any) -> Any:
    """The model the report payload's `member` is annotated with.

    **The payload's own annotation, not a field the model happens to carry.** Two
    models on this tree declare `course_week` — the week member's and the trend
    point's, which carries the course week it plots — so a selector demanding one
    model with that field fails in the selector rather than on its assertion, and
    goes on failing however the schema is built. `X | None` and `Annotated[X, …]`
    are peeled, because either is a legitimate spelling for the same model.
    """
    payload = model_carrying(schema, report_api_contract.streams_member, report_api_contract)
    field = (getattr(payload, "model_fields", None) or {}).get(member)
    assert (
        field is not None
    ), f"`{payload.__name__}` declares {sorted(payload.model_fields)}, with no `{member}` member."
    annotation = field.annotation
    while True:
        arguments = [
            argument for argument in typing.get_args(annotation) if argument is not type(None)
        ]
        if typing.get_origin(annotation) is None or not arguments:
            break
        annotation = arguments[0]
    assert isinstance(annotation, type) and getattr(annotation, "model_fields", None) is not None, (
        f"`{payload.__name__}.{member}` is annotated {field.annotation!r}, which is not a single "
        "model this test can ask for its fields."
    )
    return annotation


def test_the_week_member_gains_the_close_instant_and_nothing_else(
    report_api_contract: Any,
) -> None:
    """E5-02's week-level divergence, one level down from the top.

    The sketch's `week` is `{"course_week", "term_week", "published_weeks"}`, and
    E5-02 adds the reported week's own survey-window close to it. The top-level
    equality above cannot see this member, because `week` is one object down —
    the same blind spot E4-19 found for the trend point.

    **The mutation this kills:** the close instant added to the schema with the
    sketch and this divergence list both untouched, so the frontend fixtures go on
    describing a week object that has no close time and the absent-field path is
    the only one anybody exercises. **The near miss:** a second member added to
    the week object in the same change — a `closed`, an `opens_at` — which the
    equality catches by name rather than by count.
    """
    sketched_week = set(sketched_payload()[WEEK_MEMBER])
    assert WEEK_DIVERGENCE not in sketched_week, (
        f"The sketch's `{WEEK_MEMBER}` already carries `{WEEK_DIVERGENCE}` "
        f"({sorted(sketched_week)}), so it is not a divergence and this test is about nothing."
    )

    schema = report_api_contract.schema()
    week_model = model_behind_member(schema, WEEK_MEMBER, report_api_contract)
    declared = set(week_model.model_fields)

    assert declared == sketched_week | {WEEK_DIVERGENCE}, (
        f"`{week_model.__name__}` declares {sorted(declared)}; the sketch's `{WEEK_MEMBER}` "
        f"describes {sorted(sketched_week)} and E5-02 adds `{WEEK_DIVERGENCE}` to it — the reported "
        "week's `survey_window.closes_at`, which the mockup's eyebrow renders as 'responses closed "
        f"Sun 11:59 PM'. Unaccounted for: {sorted(declared - sketched_week - {WEEK_DIVERGENCE})}; "
        f"missing: {sorted((sketched_week | {WEEK_DIVERGENCE}) - declared)}."
    )


def test_each_stream_member_gains_the_question_text_and_nothing_else(
    report_api_contract: Any,
) -> None:
    """E5-02's stream-level divergence, at the same depth as the trend list's holder.

    The sketch's `streams.instructor` is `{"trend", "distribution", "summary",
    "comments"}` and spells `streams.course` as "same shape", so one model answers
    for both. E5-02 adds that stream's rating-question wording to it.

    **The mutation this kills:** the wording added to only one stream's model, or
    hung off the top level as a pair of texts — either of which would leave the
    sketch describing a stream object the payload no longer matches, and the
    second of which puts the two texts somewhere a histogram component cannot
    reach them from its own props.
    """
    sketched_stream = set(
        sketched_payload()[STREAMS_MEMBER][
            report_api_contract.payload_stream_key[report_api_contract.instructor_stream]
        ]
    )
    assert STREAM_DIVERGENCE not in sketched_stream, (
        f"The sketch's instructor stream already carries `{STREAM_DIVERGENCE}` "
        f"({sorted(sketched_stream)}), so it is not a divergence and this test is about nothing."
    )

    schema = report_api_contract.schema()
    stream_model = model_carrying(
        schema, report_api_contract.distribution_field, report_api_contract
    )
    declared = set(stream_model.model_fields)

    assert declared == sketched_stream | {STREAM_DIVERGENCE}, (
        f"`{stream_model.__name__}` declares {sorted(declared)}; the sketch's stream object "
        f"describes {sorted(sketched_stream)} and E5-02 adds `{STREAM_DIVERGENCE}` to it — the "
        "served text of that stream's rating question, which the mockup uses as the histogram's "
        f"title. Unaccounted for: {sorted(declared - sketched_stream - {STREAM_DIVERGENCE})}; "
        f"missing: {sorted((sketched_stream | {STREAM_DIVERGENCE}) - declared)}."
    )
