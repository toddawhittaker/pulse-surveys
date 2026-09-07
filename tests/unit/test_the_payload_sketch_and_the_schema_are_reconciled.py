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
"""

import json
import re
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
DECLARED_DIVERGENCES = frozenset({"released_from_earlier_weeks"})

# Where the first of those two sits, since it is not a top-level member.
RATES_MEMBER = "rates"
RATES_DIVERGENCE = "valid_responses"

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
