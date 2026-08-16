"""One typed output contract per §7.4 task — ticket E0-12.

SPEC §7.4 lists five tasks and, for each, what it outputs. E0-12's first
acceptance criterion is "one Pydantic model per task in §7.4's table, with
enum-typed verdicts", and the ticket's context says why the models are written
before any of them has a caller: the same object is the runtime contract, the API
response schema and the eval fixture (§9.3), so a contract change breaks its
evals at type-check time instead of passing silently.

**Nothing here names a class inside `app.ai.contracts`.** E0-12 spells the module
(`backend/app/ai/contracts.py`), the five tasks, the two closed verdict sets, and
the two fields every model carries. It spells no class name, no field name, and
no inheritance. So the models are *found* — by matching a task's word against the
names of the Pydantic models the module defines itself — and every name this file
does supply is a constant marked as this suite's choice, because pinning one here
would make the implementer build to this file instead of to the ticket. The same
mechanism, and the same reason, as `SectionCodeService` in `tests/conftest.py`.

**The task table and the verdict sets are read from `docs/SPEC.md`, not copied
into this file.** They were copied once, and an eval-gate review showed the cost:
the assertions are generic, driven by whatever the constant holds, so folding
self-harm into threat needed no defeat of a test — deleting the member from the
enum and from the tuple in the same change left the whole suite green
(`docs/MISTAKES.md` entry 19). An expectation stored beside the code it checks is
inside the blast radius of the change it exists to catch. Reading §7.4's own
table means losing a verdict now requires editing the spec, which is a reviewed
act with rules of its own. Three literals survive that policy on purpose, and say
so where they are written: they are the second, independent statement of the
threat and self-harm distinction, and a second opinion that shares a source is
not one.

**What the tests are built from, since it is not the implementation.** Each
contract is exercised through a payload assembled from its *own* declared fields:
a JSON-ready value per field, chosen by type. That is scaffolding, not an
assertion — where it cannot build a value for a required field it stops with a
message saying the fixture could not build an example, so a fixture problem never
arrives dressed as a failed criterion (`docs/MISTAKES.md` entry 13). Every test
that asserts a payload is *refused* validates the unmodified payload first, so
the refusal is attributable to the one thing the test removed or changed rather
than to some second rule in the same model — entry 3's fifth case, where "the
model said no" did not say which part of it said so.

**What is deliberately not asserted here.** How a model is *called*, what the
gateway does with it, retries, timeouts and the classification row are E0-13's,
and an assertion about any of them would be this file reaching into the next
ticket. Prompt *content* is not asserted anywhere: §9.3 makes that an eval
question, where correct is a distribution rather than a comparison.
"""

import collections.abc
import contextlib
import datetime as dt
import decimal
import enum
import json
import re
import tomllib
import types
import typing
import uuid
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import pytest
from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
SPEC_PATH = REPO_ROOT / "docs" / "SPEC.md"

# Spelled by E0-12's scope — "`backend/app/ai/contracts.py`" — and by SPEC §13,
# which gives `ai/contracts.py` the three jobs. The package root is `backend/`,
# so the import path is `app.ai.contracts`.
CONTRACTS_MODULE = "app.ai.contracts"
CONTRACTS_PATH = REPO_ROOT / "backend" / "app" / "ai" / "contracts.py"


class AiTask(NamedTuple):
    """One row of SPEC §7.4's task table.

    `fragments` and `excluded` are **this suite's choice** and the only place a
    class name is guessed at: a contract is matched by a word from the task's
    own name appearing in the model's class name, with `excluded` separating the
    two tasks whose names overlap. `ResponseDraft` and `DraftCheck` both carry
    "draft", so the draft task refuses a name that also carries "check".
    """

    key: str
    label: str
    output: str
    fragments: tuple[str, ...]
    excluded: tuple[str, ...]


# SPEC §7.4's table, one entry per row, with the Output column quoted so a
# failure carries the sentence the contract is supposed to satisfy.
TASKS = (
    AiTask(
        key="validity",
        label="Comment validity",
        output="substantive / insufficient / nonsense",
        fragments=("validity", "valid"),
        excluded=(),
    ),
    AiTask(
        key="moderation",
        label="Moderation",
        output="clear / harmful / privacy / nonsense / threat / self-harm",
        fragments=("moderation", "moderat"),
        excluded=(),
    ),
    AiTask(
        key="summary",
        label="Weekly summary",
        output="Per-stream, per-node themed summaries under the §5.1 contracts",
        fragments=("summary", "summar"),
        excluded=(),
    ),
    AiTask(
        key="response_draft",
        label="Response draft",
        output="Draft class response from the week's actual themes + ratings",
        fragments=("draft",),
        excluded=("check",),
    ),
    AiTask(
        key="draft_check",
        label="Draft check",
        output="Names themes the draft hasn't addressed, with comment counts; clears on edit",
        fragments=("check",),
        excluded=(),
    ),
)

TASKS_BY_KEY = {task.key: task for task in TASKS}

# **The verdict sets are read out of `docs/SPEC.md`, not written here.** They
# used to be two tuples copied from §7.4's Output column, and an eval-gate review
# showed what that costs: the assertion below is generic, driven by whichever
# tuple it is handed, and this file's own idiom invites editing its constants
# ("the one line that changes"). So folding self-harm into threat did not have to
# defeat the test — deleting the member from the enum *and* from the tuple left
# the whole suite green. A copy of the spec that lives beside the code is not a
# second opinion; it is the same opinion, and the fold edits both.
#
# Reading the table instead means the spec and the contract have to agree. Losing
# a verdict now takes an edit to `docs/SPEC.md`, which is a reviewed act with its
# own rules (CLAUDE.md: a change that contradicts the spec is raised, not worked
# around), rather than a plausible-looking fixture tweak.
SPEC_TASK_TABLE_HEADING = "### 7.4"
SPEC_TASK_TABLE_HEADER = ("Task", "Trigger", "Output")

# What a verdict looks like in that Output cell: one lowercase word, possibly
# hyphenated. The guard that stops a prose cell — "Per-stream, per-node themed
# summaries…" — or a table whose punctuation changed from being read as a closed
# set of verdicts. A parse that goes wrong has to fail loudly rather than hand
# back something plausible.
VERDICT_TOKEN = re.compile(r"^[a-z][a-z-]{2,19}$")

# **Deliberately literal, and the only literals of their kind in this file.**
# `test_the_moderation_contract_keeps_threat_and_self_harm_as_two_distinct_verdicts`
# exists to be a second, independent statement of the distinction §6.2's queue
# and §9.3's recall floor are built on, so it must not share a source with the
# derived set above — two assertions reading the same value are one assertion.
# The point is that a fold has to defeat a test whose name says what was lost.
THREAT_VERDICT = "threat"
SELF_HARM_VERDICT = "self-harm"
MODERATION_VERDICT_COUNT = 6

# A key no contract declares. Sent to prove the model refuses what it does not
# know about, which is what `extra="forbid"` buys and what §7.4 has the gateway
# retry on.
UNDECLARED_PROVIDER_KEY = "e0_12_undeclared_provider_key"


class AuditField(NamedTuple):
    """One of the two values §7.4 requires a classification to carry.

    `names` are **this suite's choice**: E0-12 says "prompt version and model
    ID" and spells no field. They are compared with underscores and hyphens
    removed, so `prompt_version`, `promptVersion` and `PROMPT_VERSION` are one
    spelling. If a contract carries the value under a word none of these
    reaches, that is a one-line change here and a sentence in the pull request.
    """

    key: str
    label: str
    names: tuple[str, ...]
    sentinel: str
    why: str


AUDIT_FIELDS = (
    AuditField(
        key="prompt_version",
        label="prompt version",
        names=("promptversion", "promptrevision", "promptid"),
        sentinel="e0-12-example-prompt-v1",
        why=(
            "SPEC §7.4: 'Prompts are versioned in-repo; every classification stores prompt "
            "version and model ID for reproducibility', and the single-shot boundary is "
            "justified by exactly this — 'the threat/self-harm classifier must be auditable, "
            "meaning a specific prompt version and model ID produced a specific classification "
            "for a specific comment'."
        ),
    ),
    AuditField(
        key="model_id",
        label="model ID",
        names=("modelid", "model", "modelname", "modelversion"),
        sentinel="e0-12-example-model-id",
        why=(
            "SPEC §7.4's single-shot boundary: a specific prompt version and model ID produced "
            "a specific classification. Without the model ID a stored verdict cannot be "
            "reproduced, and §9.3's eval floors compare runs of different models."
        ),
    ),
)

# **This suite's choice.** Used only to break a tie when a contract carries more
# than one enum-typed field, so the tests can say which one is the task's
# verdict. A model with a single enum field never consults this list.
VERDICT_FIELD_NAMES = (
    "verdict",
    "label",
    "classification",
    "class",
    "status",
    "result",
    "category",
    "outcome",
    "decision",
)

# A value in neither closed set, for the "wrong enum value" half of criterion 4.
UNKNOWN_VERDICT = "spicy-take"

# **This suite's choice**, and narrower than the sweep
# `tests/integration/test_identity_column_marker.py` runs over columns. A plain
# substring search for "name" would refuse `instructor_name`, and an instructor's
# name is not confidential — §5.3 posts responses "non-anonymously under the
# instructor's name". So a field is refused when it carries the ADR 0022 identity
# marker, when it pairs a word for the student with a word for an identifier, or
# when it is one of the launch claims a response is keyed by (§4: "keyed to the
# LMS user ID (`sub` from the launch)").
IDENTITY_MARKER_PREFIX = "identity_"
STUDENT_WORDS = ("student", "learner", "respondent", "author")
IDENTIFIER_WORDS = ("name", "email", "id", "login", "sis", "handle")
IDENTITY_FIELD_NAMES = ("email", "sub", "userid", "lmsuserid", "usersub", "sisid")

# The flags E0-01's mypy override applies to `app.ai.contracts` and
# `app.services.*`. Criterion 6 says the contracts module "is in the strict
# profile"; this is that profile enumerated, so removing one of them from the
# override is a visible change rather than a quiet one. mypy does not accept
# `strict = true` in a per-module section, so the flags are the profile.
STRICT_PROFILE_FLAGS = (
    "disallow_untyped_defs",
    "disallow_incomplete_defs",
    "disallow_untyped_calls",
    "disallow_untyped_decorators",
    "disallow_any_generics",
    "disallow_subclassing_any",
    "warn_return_any",
    "strict_equality",
    "extra_checks",
)

# Values for the payload builder below. Every one is JSON-ready, because the
# payload an eval fixture holds is JSON text rather than Python objects.
EXAMPLE_TEXT = "e0-12 example text"
EXAMPLE_KEY = "example"
SCALAR_EXAMPLES: dict[Any, Any] = {
    str: EXAMPLE_TEXT,
    bool: True,
    int: 3,
    float: 4.5,
    decimal.Decimal: "3.5",
    uuid.UUID: "0f8b6c4e-6a3f-4f7c-9d21-3f1a5b8c7d90",
    dt.datetime: "2026-09-28T09:00:00+00:00",
    dt.date: "2026-09-28",
    dt.time: "09:00:00",
    type(None): None,
    Any: EXAMPLE_TEXT,
}

# The runtime origins `typing.get_origin` actually returns, which are the
# `collections.abc` classes rather than the `typing` aliases: `get_origin(
# Sequence[str])` is `collections.abc.Sequence`, and comparing against
# `typing.Sequence` would match nothing while looking as though it matched
# everything.
SEQUENCE_ORIGINS = (
    list,
    set,
    frozenset,
    tuple,
    collections.abc.Sequence,
    collections.abc.Iterable,
    collections.abc.Collection,
)
MAPPING_ORIGINS = (dict, collections.abc.Mapping, collections.abc.MutableMapping)


class UnbuildableError(Exception):
    """The payload builder has no example value for an annotation.

    Carries where it gave up so the failure names the field rather than the
    type alone.
    """

    def __init__(self, where: str, annotation: Any) -> None:
        super().__init__(f"no example value for `{where}`, annotated {annotation!r}")
        self.where = where
        self.annotation = annotation


# ---------------------------------------------------------------------------
# Reading §7.4's task table out of the spec
# ---------------------------------------------------------------------------


def spec_task_table() -> dict[str, str]:
    """§7.4's table, as task label to Output cell, read from `docs/SPEC.md`.

    Scoped to the §7.4 section rather than swept from the whole document,
    because SPEC.md holds other three-column tables — §7.1's stack, §8's course
    number bands — and a sweep that happened to match one of those would be
    reading a different table with the same shape.

    **This is a search over a file, which is the shape that fails silently**
    (`docs/MISTAKES.md` entry 3). Two guards, both of which stop rather than
    return something plausible: the section must contain the
    `| Task | Trigger | Output |` header — the canary, a string certainly
    present in the table this is looking for — and it must yield at least one
    row. An empty parse would otherwise flow into a set comparison and be read
    as a contract with the wrong verdicts.
    """
    if not SPEC_PATH.is_file():
        pytest.fail(
            f"{SPEC_PATH} does not exist, so the verdict sets asserted below have no source. "
            "They are read from §7.4's table rather than copied into this file on purpose."
        )

    lines = SPEC_PATH.read_text(encoding="utf-8").splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.startswith(SPEC_TASK_TABLE_HEADING)),
        None,
    )
    if start is None:
        pytest.fail(
            f"{SPEC_PATH} has no heading starting {SPEC_TASK_TABLE_HEADING!r}, so §7.4's task "
            "inventory could not be found. If the section was renumbered, this constant is what "
            "changes — and every task-set assertion in this file is downstream of it."
        )

    rows: dict[str, str] = {}
    header_seen = False
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) != 3:
            continue
        if tuple(cells) == SPEC_TASK_TABLE_HEADER:
            header_seen = True
            continue
        if all(cell and set(cell) <= {"-", ":"} for cell in cells):
            continue
        rows[cells[0]] = cells[2]

    if not header_seen:
        pytest.fail(
            f"The §7.4 section of {SPEC_PATH} holds no "
            f"`| {' | '.join(SPEC_TASK_TABLE_HEADER)} |` header row. That header is this "
            "reader's canary: without it, the parse below has found something other than the "
            "task table, and a search that has gone blind reports the same emptiness as a table "
            "with no rows in it."
        )
    if not rows:
        pytest.fail(f"The §7.4 task table in {SPEC_PATH} parsed to no rows at all.")
    return rows


def spec_verdicts(task: AiTask) -> tuple[str, ...]:
    """The closed set §7.4's Output column gives `task`, read from the spec."""
    table = spec_task_table()
    if task.label not in table:
        pytest.fail(
            f"§7.4's task table in {SPEC_PATH} has no row for '{task.label}'; it names "
            f"{sorted(table)}. Either the spec renamed the task — in which case `TASKS` in this "
            "file follows it — or the task was removed, which is a spec change this contract "
            "suite should be red about."
        )

    cell = table[task.label]
    verdicts = tuple(part.strip().lower() for part in cell.split("/") if part.strip())

    if len(verdicts) < 2 or not all(VERDICT_TOKEN.match(verdict) for verdict in verdicts):
        pytest.fail(
            f"§7.4's Output cell for '{task.label}' is {cell!r}, which does not read as a closed "
            f"set of verdicts — it parsed to {list(verdicts)}. Only the two classifier tasks have "
            "one; the other three rows carry prose, and asserting an enum against prose would be "
            "this file misreading the table rather than the contract being wrong."
        )
    return verdicts


# ---------------------------------------------------------------------------
# Finding the contracts without naming them
# ---------------------------------------------------------------------------


def normalised(name: str) -> str:
    """A field or member name with case, underscores and hyphens removed."""
    return name.lower().replace("_", "").replace("-", "").replace(" ", "")


def contracts_module(import_app_module: Callable[[str], ModuleType | None]) -> ModuleType:
    """`app.ai.contracts`, or a failure naming the missing deliverable.

    `import_app_module` answers `None` for a module that does not exist and
    re-raises an `ImportError` from *inside* one that does, so a module that was
    never written and a module that is broken are two different failures.
    """
    module = import_app_module(CONTRACTS_MODULE)
    if module is None:
        pytest.fail(
            f"There is no `{CONTRACTS_MODULE}` module. E0-12's scope: "
            "'`backend/app/ai/contracts.py` — a Pydantic output model per §7.4 task: comment "
            "validity, moderation, weekly summary, response draft, draft check.' SPEC §13 gives "
            "the file the same three jobs: runtime contract, API response schema, eval fixture."
        )
    return module


def contract_models(module: ModuleType) -> dict[str, type[BaseModel]]:
    """Every Pydantic model the contracts module defines itself.

    Defines *itself*: a `BaseModel` imported from somewhere else is not part of
    this module's surface, and counting one would let an unrelated schema answer
    for a task nobody modelled.
    """
    found: dict[str, type[BaseModel]] = {}
    for name, value in vars(module).items():
        if name.startswith("_"):
            continue
        if not isinstance(value, type) or not issubclass(value, BaseModel):
            continue
        if value.__module__ != CONTRACTS_MODULE:
            continue
        found[name] = value
    return found


def referenced_models(annotation: Any) -> set[type[BaseModel]]:
    """Every Pydantic model reachable from one annotation, without descending into it."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return {annotation}
    found: set[type[BaseModel]] = set()
    for argument in typing.get_args(annotation):
        found |= referenced_models(argument)
    return found


def composed_into_another(models: dict[str, type[BaseModel]]) -> set[str]:
    """Names of models that appear as a field type inside another model here.

    E0-12 says to compose rather than copy, so a contract may well be built out
    of smaller models declared beside it — a theme with its comment count, a
    per-stream summary. Those are parts, not task contracts, and this is what
    lets a part named `DraftCheckTheme` stop competing with `DraftCheckOutput`
    for the draft-check task. The test that resolves a tie this way says so, and
    a tie it cannot resolve is a failure rather than a guess.
    """
    used: set[str] = set()
    for owner in models.values():
        for field in owner.model_fields.values():
            for referenced in referenced_models(field.annotation):
                if referenced is not owner:
                    used.add(referenced.__name__)
    return used


def matching_models(models: dict[str, type[BaseModel]], task: AiTask) -> dict[str, type[BaseModel]]:
    """The models whose class name reads as `task`'s contract."""
    matches = {
        name: model
        for name, model in models.items()
        if any(fragment in normalised(name) for fragment in task.fragments)
        and not any(fragment in normalised(name) for fragment in task.excluded)
    }
    if len(matches) > 1:
        composed = composed_into_another(models)
        outermost = {name: model for name, model in matches.items() if name not in composed}
        if len(outermost) == 1:
            return outermost
    return matches


def one_contract(module: ModuleType, task: AiTask) -> type[BaseModel]:
    """The single contract for `task`, or a failure pointing at the test that owns that."""
    matches = matching_models(contract_models(module), task)
    if len(matches) != 1:
        pytest.fail(
            f"`{CONTRACTS_MODULE}` has {len(matches)} models for §7.4's '{task.label}' task "
            f"({sorted(matches)}), so this test has no single contract to exercise. "
            "test_the_task_table_has_exactly_one_contract_for_each_of_its_tasks says what that "
            "means and how to change it."
        )
    return next(iter(matches.values()))


# ---------------------------------------------------------------------------
# Reading a contract's fields
# ---------------------------------------------------------------------------


def field_path(
    model: type[BaseModel],
    names: tuple[str, ...],
    *,
    depth: int = 3,
    seen: frozenset[type[BaseModel]] = frozenset(),
) -> tuple[str, ...] | None:
    """Where `model` carries a field spelled as one of `names`, if it does.

    Returns a path rather than a name because E0-12 says to compose rather than
    copy, so the two audit values may legitimately sit on a shared sub-model
    every contract embeds. The top level is searched first, so a contract that
    carries them directly is read directly.
    """
    fields = model.model_fields
    for name in fields:
        if normalised(name) in names:
            return (name,)
    if depth <= 1:
        return None
    for name, field in fields.items():
        for nested in referenced_models(field.annotation):
            if nested in seen:
                continue
            below = field_path(nested, names, depth=depth - 1, seen=seen | {model, nested})
            if below is not None:
                return (name, *below)
    return None


def reachable_models(
    model: type[BaseModel],
    *,
    depth: int = 4,
    seen: frozenset[type[BaseModel]] = frozenset(),
) -> set[str]:
    """The names of every model a contract is built out of, in either direction.

    Its own name, the bases it inherits from — a shared envelope carrying the
    audit fields is the obvious way to satisfy "every model carries prompt
    version and model ID" — and every model reachable through its fields, which
    is what E0-12 means by composing rather than copying. What is left over after
    this is a model belonging to no task.
    """
    names = {base.__name__ for base in model.__mro__}
    if depth <= 1:
        return names
    for field in model.model_fields.values():
        for nested in referenced_models(field.annotation):
            if nested in seen:
                continue
            names |= reachable_models(nested, depth=depth - 1, seen=seen | {model, nested})
    return names


def all_field_names(
    model: type[BaseModel],
    *,
    depth: int = 3,
    seen: frozenset[type[BaseModel]] = frozenset(),
) -> set[str]:
    """Every field name on a contract and on the models composed into it."""
    names = set(model.model_fields)
    if depth <= 1:
        return names
    for field in model.model_fields.values():
        for nested in referenced_models(field.annotation):
            if nested in seen:
                continue
            names |= all_field_names(nested, depth=depth - 1, seen=seen | {model, nested})
    return names


def bare(annotation: Any) -> Any:
    """An annotation with `Annotated[...]` metadata and an optional `None` removed.

    Pydantic already splits constraints out of `FieldInfo.annotation`, so the
    `__metadata__` unwrapping is belt and braces for anything it hands back
    still wearing them.
    """
    while hasattr(annotation, "__metadata__"):
        annotation = annotation.__origin__
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        arguments = [
            argument for argument in typing.get_args(annotation) if argument is not type(None)
        ]
        if len(arguments) == 1:
            return bare(arguments[0])
    return annotation


def enum_in(annotation: Any) -> tuple[type[enum.Enum] | None, bool]:
    """The enum an annotation carries, and whether it carries several of them.

    A sequence of enum members is admitted rather than refused. §7.4's table
    reads as one label per task and §5.2 says the classifier "tags each comment"
    with one of four, but whether a contract may carry more than one label is not
    something E0-12 decides, and refusing a list here would decide it from the
    test suite. What every test below asserts is the *set* a label is drawn from,
    which is the same question either way.
    """
    annotation = bare(annotation)
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return annotation, False
    if typing.get_origin(annotation) in SEQUENCE_ORIGINS:
        for argument in typing.get_args(annotation):
            member = bare(argument)
            if isinstance(member, type) and issubclass(member, enum.Enum):
                return member, True
    return None, False


def verdict_field(model: type[BaseModel], task: AiTask) -> tuple[str, type[enum.Enum], bool]:
    """The field carrying `task`'s verdict: its name, its enum, and whether it is a sequence.

    The field is found by its *type* rather than by its name, and that is what
    makes the free-string near miss fail here: a contract whose verdict is a
    `str` — or a `Literal`, which cannot be imported and compared as a member by
    an eval case or by the moderation service — has no enum-annotated field at
    all, and this stops with the criterion quoted.
    """
    candidates: list[tuple[str, type[enum.Enum], bool]] = []
    annotations = {}
    for name, field in model.model_fields.items():
        annotations[name] = field.annotation
        found, sequence = enum_in(field.annotation)
        if found is not None:
            candidates.append((name, found, sequence))

    if not candidates:
        pytest.fail(
            f"No field on `{model.__name__}` is annotated with an enum, so §7.4's '{task.label}' "
            f"verdict is not a closed set. Its fields are {annotations}. E0-12's scope: 'Validity "
            "returns substantive / insufficient / nonsense. Moderation returns clear / harmful / "
            "privacy / nonsense / threat / self-harm. Model both as enums, not free strings.' A "
            "free string is what lets a provider return `Harmful`, `harm` or a sentence and have "
            "it stored as a verdict; an enum is also the thing an eval case (§9.3) and the "
            "routing in §5.2 compare against by member rather than by spelling."
        )
    if len(candidates) > 1:
        named = [
            candidate for candidate in candidates if normalised(candidate[0]) in VERDICT_FIELD_NAMES
        ]
        if len(named) == 1:
            return named[0]
        pytest.fail(
            f"`{model.__name__}` has more than one enum-typed field "
            f"({[candidate[0] for candidate in candidates]}), and none of them — or more than one "
            f"— is spelled like a verdict, so this cannot tell which one carries §7.4's "
            f"'{task.label}' output. Naming one here would pin an interface E0-12 leaves open: "
            "say in the pull request which it is, and `VERDICT_FIELD_NAMES` in this file is the "
            "one line that changes."
        )
    return candidates[0]


def spellings(member: enum.Enum) -> set[str]:
    """The ways one enum member could be spelling a verdict from the spec.

    Both the member's name and its value, each lowercased with underscores read
    as hyphens, so `SELF_HARM = "self_harm"` and `SelfHarm = "self-harm"` both
    answer to §7.4's `self-harm` and neither is favoured. Aliases are not
    consulted, because iterating an enum yields canonical members only — which is
    the point: an implementation that made `SELF_HARM` an alias of `THREAT` has
    five verdicts wearing six names, and the safety routing in §6.2 cannot tell
    the two apart.
    """
    found = {member.name.lower().replace("_", "-")}
    if isinstance(member.value, str):
        found.add(member.value.lower().replace("_", "-"))
    return found


def assert_closed_verdict_set(
    model: type[BaseModel], task: AiTask, expected: tuple[str, ...]
) -> None:
    """The task's verdict enum offers exactly the verdicts §7.4's table names."""
    _, verdicts, _ = verdict_field(model, task)
    members = list(verdicts)

    matched = {
        verdict for verdict in expected if any(verdict in spellings(member) for member in members)
    }
    unexpected = [member for member in members if not (spellings(member) & set(expected))]

    assert matched == set(expected) and not unexpected, (
        f"`{verdicts.__name__}` offers {[member.name for member in members]} "
        f"(values {[member.value for member in members]}). §7.4's table gives '{task.label}' the "
        f"output `{task.output}`, so the closed set is exactly {list(expected)}. Missing: "
        f"{sorted(set(expected) - matched)}. Not in the table: "
        f"{[member.name for member in unexpected]}. A verdict the table names and the enum lacks "
        "cannot be returned at all, whatever the model says; one the enum adds is a verdict no "
        "part of the spec routes, stores or evaluates."
    )


# ---------------------------------------------------------------------------
# Building a representative payload out of a contract's own declared fields
# ---------------------------------------------------------------------------


def example_json_value(annotation: Any, *, where: str, depth: int = 0) -> Any:
    """A JSON-ready example value for one annotation.

    JSON-ready rather than a Python object, because criterion 3 asks for a
    round trip through `model_validate_json` and the eval fixtures in §9.3 are
    text on disk before they are objects.
    """
    if depth > 6:
        raise UnbuildableError(where, annotation)
    annotation = bare(annotation)
    origin = typing.get_origin(annotation)

    if origin is typing.Literal:
        arguments = typing.get_args(annotation)
        if arguments:
            return arguments[0]
        raise UnbuildableError(where, annotation)

    if origin in (typing.Union, types.UnionType):
        for argument in typing.get_args(annotation):
            if argument is not type(None):
                return example_json_value(argument, where=where, depth=depth + 1)
        return None

    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        member = next(iter(annotation), None)
        if member is None:
            raise UnbuildableError(where, annotation)
        value = member.value
        return value if isinstance(value, str | int | float | bool) else member.name

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return example_payload(annotation, path=where, depth=depth + 1)

    if origin in SEQUENCE_ORIGINS:
        arguments = [
            argument for argument in typing.get_args(annotation) if argument is not Ellipsis
        ]
        if not arguments:
            return [EXAMPLE_TEXT]
        return [
            example_json_value(argument, where=f"{where}[]", depth=depth + 1)
            for argument in arguments[:1]
        ]

    if origin in MAPPING_ORIGINS:
        arguments = typing.get_args(annotation)
        if len(arguments) == 2:
            return {EXAMPLE_KEY: example_json_value(arguments[1], where=f"{where}[]", depth=depth)}
        return {EXAMPLE_KEY: EXAMPLE_TEXT}

    # An unhashable annotation cannot be a key here and is not a scalar.
    with contextlib.suppress(TypeError):
        if annotation in SCALAR_EXAMPLES:
            return SCALAR_EXAMPLES[annotation]

    raise UnbuildableError(where, annotation)


def example_payload(model: type[BaseModel], *, path: str = "", depth: int = 0) -> dict[str, Any]:
    """A JSON-ready payload filling every field of `model` this file can fill.

    Optional fields whose type this builder has no example for are left out
    rather than stopping the test — a contract is free to carry something exotic
    behind a default. A *required* field it cannot fill stops with `UnbuildableError`,
    which the caller turns into "the fixture could not build an example", because
    a test that cannot construct its subject has found nothing about the subject.
    """
    payload: dict[str, Any] = {}
    for name, field in model.model_fields.items():
        where = f"{path}.{name}" if path else f"{model.__name__}.{name}"
        try:
            payload[name] = example_json_value(field.annotation, where=where, depth=depth)
        except UnbuildableError:
            if field.is_required():
                raise
    return payload


def representative_payload(model: type[BaseModel]) -> dict[str, Any]:
    """`example_payload`, with a builder failure reported as a fixture failure."""
    try:
        return example_payload(model)
    except UnbuildableError as failure:
        pytest.fail(
            f"This test could not build an example payload for `{model.__name__}`: "
            f"{failure}. That is a gap in this file rather than a failed criterion — teach "
            "`SCALAR_EXAMPLES` or `example_json_value` the type and the assertion below runs "
            "again. Reported separately so a fixture that cannot construct its subject is never "
            "read as a contract that refused a valid payload (docs/MISTAKES.md entry 13)."
        )


def assert_the_control_validates(model: type[BaseModel], payload: dict[str, Any]) -> Any:
    """The unmodified payload validates, so a later refusal is attributable.

    Every test below that asserts a refusal removes or replaces exactly one
    thing in this payload first. Without this control, a `ValidationError` from
    some *other* required field this file filled badly would read as the
    criterion holding — `docs/MISTAKES.md` entry 3, whose fifth case is a refusal
    that arrived from a different rule than the one under test.
    """
    try:
        return model.model_validate(payload)
    except ValidationError as failure:
        pytest.fail(
            f"The example payload this file built for `{model.__name__}` does not validate: "
            f"{failure}. The payload was {payload!r}. Until it does, nothing below can say which "
            "rule refused the modified one. This is a gap in this file — a constraint on a field "
            "whose example value does not satisfy it — rather than a failed criterion."
        )


def without(payload: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    """A copy of `payload` with the value at `path` removed."""
    head, *rest = path
    copy = dict(payload)
    if not rest:
        copy.pop(head, None)
        return copy
    nested = copy.get(head)
    if isinstance(nested, dict):
        copy[head] = without(nested, tuple(rest))
    return copy


def replaced(payload: dict[str, Any], path: tuple[str, ...], value: Any) -> dict[str, Any]:
    """A copy of `payload` with the value at `path` replaced."""
    head, *rest = path
    copy = dict(payload)
    if not rest:
        copy[head] = value
        return copy
    nested = copy.get(head)
    if isinstance(nested, dict):
        copy[head] = replaced(nested, tuple(rest), value)
    return copy


def at(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    """The value at `path`, or `None` where the path is not there."""
    current: Any = payload
    for step in path:
        if not isinstance(current, dict):
            return None
        current = current.get(step)
    return current


def json_values(document: Any) -> list[Any]:
    """Every leaf value in a parsed JSON document."""
    if isinstance(document, dict):
        return [leaf for value in document.values() for leaf in json_values(value)]
    if isinstance(document, list):
        return [leaf for item in document for leaf in json_values(item)]
    return [document]


def refusal(model: type[BaseModel], payload: dict[str, Any], expectation: str) -> ValidationError:
    """The `ValidationError` validating `payload` raised, or a failure saying it raised none."""
    try:
        accepted = model.model_validate(payload)
    except ValidationError as failure:
        return failure
    pytest.fail(f"{expectation} Instead `{model.__name__}` accepted it and returned {accepted!r}.")


# ---------------------------------------------------------------------------
# One contract per task
# ---------------------------------------------------------------------------


def test_the_task_inventory_this_file_transcribes_is_the_one_the_spec_publishes() -> None:
    """`TASKS` is §7.4's table, and this is what makes that claim checkable.

    Every per-task assertion in this file is parametrised over `TASKS`, so the
    tuple decides what "complete" means. A hand transcription that the spec has
    moved past is a suite that reports full coverage of a table it invented:
    if §7.4 grows a sixth task, nothing else here notices, because a
    parametrisation cannot fail for a case it was never given.

    Both halves are asserted. The task set, so a task added to or removed from
    the inventory shows up as a missing or surplus contract rather than as
    silence. And the Output column, because this file quotes it into failure
    messages — a message that tells the implementer what §7.4 requires, while
    quoting a version of the table that no longer exists, is `docs/MISTAKES.md`
    entry 1 aimed at exactly the person trying to fix something.
    """
    published = spec_task_table()
    transcribed = {task.label: task.output for task in TASKS}

    assert set(published) == set(transcribed), (
        f"§7.4's table in {SPEC_PATH} names {sorted(published)}; this file transcribes "
        f"{sorted(transcribed)}. Missing here: {sorted(set(published) - set(transcribed))}. Not "
        f"in the spec: {sorted(set(transcribed) - set(published))}. A task in the spec and not in "
        "`TASKS` is a model call nothing in this suite asks for a contract for; a task in `TASKS` "
        "and not in the spec is a contract required by a table that no longer says so."
    )

    misquoted = {
        label: (transcribed[label], published[label])
        for label in transcribed
        if label in published and transcribed[label] != published[label]
    }

    assert not misquoted, (
        f"These Output cells are transcribed differently from {SPEC_PATH} — "
        f"{{task: (this file, the spec)}}: {misquoted}. The transcription is quoted into the "
        "failure messages this suite produces, so a stale copy misinforms the person reading a "
        "red test about what the contract is supposed to return."
    )


@pytest.mark.parametrize("task", TASKS, ids=[task.key for task in TASKS])
def test_the_task_table_has_exactly_one_contract_for_each_of_its_tasks(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    task: AiTask,
) -> None:
    """Criterion 1: one Pydantic model per task in §7.4's table.

    Parametrised per task rather than written as one set comparison, so a task
    nobody modelled fails under its own name. That is the omission this ticket
    exists to make impossible to ship: the models are written before any of them
    has a caller, so nothing else in the system will notice that the summary
    task, or the draft check, was never given a shape.

    **Two contracts for one task fails as well as none**, and it is the more
    interesting half. E0-12's scope: "Do **not** fork these models for API or
    eval use — `CLAUDE.md` forbids it. If an API response needs a different
    shape, compose rather than copy." A `ValidityResult` beside a
    `ValidityResponse` is that fork, and §7.4's whole argument for the shared
    model is that an eval case is a typed object rather than a string
    comparison — which stops being true the moment the eval set and the runtime
    hold two models that can drift apart.

    A model composed *into* another one — a theme with its comment count — is not
    a second contract, and `composed_into_another` discounts it before this
    counts. A tie it cannot resolve fails here rather than being guessed at.

    `configured_env` sets every variable `.env.example` documents before the
    import. Nothing in a contracts module should need configuration; a module
    that reaches anything through `app.db` builds an engine out of `Settings()`
    at import — the epic README's second settled rule — and this makes that a
    failure with a message rather than a collection error.
    """
    module = contracts_module(import_app_module)
    models = contract_models(module)

    assert models, (
        f"`{CONTRACTS_MODULE}` defines no Pydantic models at all, so this test would report "
        "every task as missing without having looked at anything. E0-12's scope asks for one "
        "output model per §7.4 task."
    )

    matches = matching_models(models, task)

    assert len(matches) == 1, (
        f"`{CONTRACTS_MODULE}` has {len(matches)} contracts for §7.4's '{task.label}' task "
        f"({sorted(matches)}); it defines {sorted(models)}. The table gives that task the output "
        f"`{task.output}`. Zero means a task the spec names that nothing models, which is the "
        "omission this ticket exists to prevent — the contracts are written before any caller "
        "exists, so nothing downstream will report it. More than one means either the fork "
        "E0-12 forbids ('compose rather than copy'), or a class this file cannot tell from the "
        f"contract: matching is by {list(task.fragments)} in the class name, minus "
        f"{list(task.excluded)}, and `TASKS` in this file is the one line that changes."
    )


def test_every_model_in_the_contracts_module_belongs_to_a_task_in_the_inventory(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
) -> None:
    """The other direction of "one contract per task", and the half that catches a quiet fork.

    The per-task test above asks whether every task has a contract. This asks
    whether every model in the file belongs to a task — because the fork E0-12
    forbids does not have to be named after the task it duplicates. A
    `CommentCheckPayload` sitting beside the validity contract matches no task
    word, leaves the per-task count at one, and is exactly what the ticket means
    by "Do not fork these models for API or eval use. If an API response needs a
    different shape, compose rather than copy."

    §7.4 is the reason the closure matters in this direction too: "All model
    calls go through one internal `AIGateway` with per-task prompts", and the
    task inventory is that table. A sixth output model in this file is either a
    fork of one of the five or a model call the spec does not know about, and
    both are things to see rather than to discover in E2.

    A shared base class and a composed part are not strays — `reachable_models`
    accounts for both, in the two directions a contract is legitimately built.
    """
    module = contracts_module(import_app_module)
    models = contract_models(module)

    assert models, (
        f"`{CONTRACTS_MODULE}` defines no Pydantic models at all, so nothing here is accounted "
        "for and nothing is stray. The per-task test above owns that failure."
    )

    contracts = {}
    for task in TASKS:
        matches = matching_models(models, task)
        if len(matches) == 1:
            contracts[task.key] = next(iter(matches.values()))

    assert contracts, (
        f"None of §7.4's five tasks matched exactly one of {sorted(models)}, so this test has no "
        "contract to account from and would report every model as stray. The per-task test above "
        "says which tasks are missing and how the matching works."
    )

    accounted: set[str] = set()
    for contract in contracts.values():
        accounted |= reachable_models(contract)

    stray = sorted(name for name in models if name not in accounted)

    assert not stray, (
        f"`{CONTRACTS_MODULE}` defines {stray}, which no §7.4 task's contract inherits from, "
        f"composes, or is. The contracts matched were {sorted(contracts)}. Either one of these "
        "is the fork E0-12 forbids — the same shape twice, free to drift apart, which is what "
        "makes §7.4's claim that an eval case is a typed object stop being true — or it is a "
        "contract for a task whose word this file's `TASKS` fragments did not match, and the "
        "per-task test above will be red alongside this one."
    )


# ---------------------------------------------------------------------------
# Auditability: prompt version and model ID
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("audit", AUDIT_FIELDS, ids=[audit.key for audit in AUDIT_FIELDS])
@pytest.mark.parametrize("task", TASKS, ids=[task.key for task in TASKS])
def test_a_contract_cannot_be_built_without_the_field_that_makes_it_auditable(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    task: AiTask,
    audit: AuditField,
) -> None:
    """Criterion 2: constructing a contract without prompt version or model ID fails validation.

    Two failures, one criterion. The field can be *absent*, which no other test
    here would notice; or it can be present and optional — `prompt_version: str
    | None = None` — which is the near miss, because every reader of the model
    then sees an auditability field and every record written through it can
    carry nothing. §7.4 rests the entire single-shot argument on the opposite:
    "a specific prompt version and model ID produced a specific classification
    for a specific comment."

    Removing the field is asserted at every level of its path, so a contract that
    composes the two values onto a shared sub-model is required to make the
    sub-model itself mandatory rather than optional. Composition is what E0-12
    asks for; an optional envelope around the audit values gives back exactly
    what requiring them was for.

    The unmodified payload is validated first. Without that control, a contract
    whose example values this file got wrong would refuse the reduced payload for
    an unrelated reason and be recorded as satisfying the criterion.
    """
    module = contracts_module(import_app_module)
    model = one_contract(module, task)
    payload = representative_payload(model)
    assert_the_control_validates(model, payload)

    path = field_path(model, audit.names)

    assert path is not None, (
        f"`{model.__name__}` carries no {audit.label} field: its fields are "
        f"{sorted(all_field_names(model))}. E0-12's scope: 'Every model carries the fields needed "
        f"for auditability: prompt version and model ID.' {audit.why} If it is carried under a "
        f"word none of {list(audit.names)} reaches, `AUDIT_FIELDS` in this file is the one line "
        "that changes — say so in the pull request."
    )

    for depth in range(1, len(path) + 1):
        prefix = path[:depth]
        reduced = without(payload, prefix)
        refusal(
            model,
            reduced,
            f"`{model.__name__}` validated a payload with `{'.'.join(prefix)}` removed, so its "
            f"{audit.label} is optional rather than required. Criterion 2: 'Every model requires "
            "prompt version and model ID; constructing one without them fails validation.' "
            f"{audit.why}",
        )


@pytest.mark.parametrize("audit", AUDIT_FIELDS, ids=[audit.key for audit in AUDIT_FIELDS])
@pytest.mark.parametrize("task", TASKS, ids=[task.key for task in TASKS])
def test_a_contracts_audit_field_survives_being_serialised(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    task: AiTask,
    audit: AuditField,
) -> None:
    """The prompt version and model ID a contract was validated with are in the JSON it emits.

    Criterion 2 asks that the field be required and criterion 3 that the model
    round-trip; between them sits a shape that satisfies both and defeats the
    point. A field declared `Field(..., exclude=True)`, or held as a
    `PrivateAttr`, is required at construction, is invisible in
    `model_dump_json`, and is therefore absent from the API response §7.4 says
    this model is, and from the eval fixture §9.3 says it is. The stored
    classification then has a verdict and no record of what produced it.

    The value is looked for anywhere in the emitted document rather than under a
    particular key, so a contract is free to name and nest the field as it likes.
    What it is not free to do is drop the value.
    """
    module = contracts_module(import_app_module)
    model = one_contract(module, task)
    payload = representative_payload(model)

    path = field_path(model, audit.names)
    assert path is not None, (
        f"`{model.__name__}` carries no {audit.label} field, so there is nothing to follow "
        "through serialisation. test_a_contract_cannot_be_built_without_the_field_that_makes_it_"
        "auditable is the test that owns that criterion."
    )

    built = at(payload, path)
    sentinel = audit.sentinel if isinstance(built, str) else built
    payload = replaced(payload, path, sentinel)
    validated = assert_the_control_validates(model, payload)

    emitted = json.loads(validated.model_dump_json())

    assert sentinel in json_values(emitted), (
        f"`{model.__name__}` was validated with a {audit.label} of {sentinel!r} and serialised to "
        f"{emitted!r}, which does not carry it. §7.4 makes this one model the runtime contract, "
        "the API response schema and the eval fixture at once, so a value that survives "
        f"construction and not serialisation is a value the classification record never gets. "
        f"{audit.why}"
    )


# ---------------------------------------------------------------------------
# The round trip that makes a contract usable as an eval fixture
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("task", TASKS, ids=[task.key for task in TASKS])
def test_a_contract_round_trips_through_model_validate_json(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    task: AiTask,
) -> None:
    """Criterion 3: each contract round-trips a representative payload through JSON.

    This is the ticket's "usable as an eval fixture" asserted rather than
    assumed. §9.3: "Cases are typed objects built from the same Pydantic
    contracts the tasks return (§7.4), so a contract change breaks its evals at
    type-check time rather than silently passing." An eval set is JSON on disk;
    it becomes a typed object through `model_validate_json`, and the same object
    has to serialise back to something the contract accepts, or the set cannot be
    grown from admin overrides (§6.1) and written back.

    The near miss this fails against is a field with a validation alias:
    `Field(alias="promptVersion")` accepts the alias and, by default,
    `model_dump_json` emits the field name — so the model refuses its own output
    and every fixture in the set has to be written in whichever spelling happens
    to work. It also fails against a field whose type cannot be serialised at
    all, which is the other way a contract stops being a fixture.

    The payload is built from the contract's own declared fields, which is
    scaffolding rather than an assertion: what is asserted is that text in and
    text out describe the same object.
    """
    module = contracts_module(import_app_module)
    model = one_contract(module, task)
    payload = representative_payload(model)
    text = json.dumps(payload)

    try:
        loaded = model.model_validate_json(text)
    except ValidationError as failure:
        pytest.fail(
            f"`{model.__name__}` refused the example payload this file built for it: {failure}. "
            f"The JSON was {text}. That is a gap in this file rather than a failed criterion — "
            "see `representative_payload`."
        )

    emitted = loaded.model_dump_json()

    try:
        again = model.model_validate_json(emitted)
    except ValidationError as failure:
        pytest.fail(
            f"`{model.__name__}` accepted {text}, serialised it to {emitted}, and then refused "
            f"its own output: {failure}. Criterion 3 wants a contract that round-trips through "
            "`model_validate_json`, and §9.3 builds every eval case out of exactly this. A "
            "validation alias that serialisation does not use is the usual cause."
        )

    assert again == loaded, (
        f"`{model.__name__}` round-tripped to a different object. In: {loaded!r}. Out: {again!r}. "
        "An eval case (§9.3) is written as JSON, loaded as a typed object and compared against "
        "what a task returned; a contract whose JSON form loses or changes a field compares two "
        "things that were never the same."
    )


# ---------------------------------------------------------------------------
# The two closed verdict sets
# ---------------------------------------------------------------------------


def test_the_validity_contract_offers_exactly_the_three_verdicts_the_task_table_names(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
) -> None:
    """Criterion 1's second half for the validity task: substantive / insufficient / nonsense.

    §7.4's table and E0-12's scope both spell the three. The verdict is reached
    by finding the enum-typed field, so a contract that types it `str` fails here
    with the criterion quoted — that is the near miss, since a free string
    satisfies every other test in this file.

    Both a missing and an extra member fail. Validity gates participation (§3.3),
    so a fourth verdict nobody specified is a value the gating code has no branch
    for, and a missing one is an answer the model is asked for and cannot give.
    """
    task = TASKS_BY_KEY["validity"]
    module = contracts_module(import_app_module)
    model = one_contract(module, task)

    assert_closed_verdict_set(model, task, spec_verdicts(task))


def test_the_moderation_contract_offers_exactly_the_six_verdicts_the_task_table_names(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
) -> None:
    """Criterion 1 for moderation: clear / harmful / privacy / nonsense / threat / self-harm.

    Six, and the last two are why the count matters. §5.2 routes abuse aimed at
    the instructor to the Lead Faculty queue and self-harm to Care immediately;
    §6.2 gives threat-of-harm and self-harm risk their own queue, suppressed from
    every instructor and leadership view; §9.3 makes the threat and self-harm
    recall floor the strictest gate in the suite because false negatives are the
    expensive error.

    A contract that models five verdicts by folding threat and self-harm into
    one — or that reaches the same place by making one an alias of the other,
    which `spellings` refuses by iterating canonical members only — cannot express
    the distinction §6.2's queue is built on, and a recall floor measured over the
    merged label is measuring something else. That is the reason this is asserted
    as an exact set rather than as "at least the six".
    """
    task = TASKS_BY_KEY["moderation"]
    module = contracts_module(import_app_module)
    model = one_contract(module, task)

    assert_closed_verdict_set(model, task, spec_verdicts(task))


def test_the_moderation_contract_keeps_threat_and_self_harm_as_two_distinct_verdicts(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
) -> None:
    """Threat and self-harm are two verdicts, and nothing else in this suite says so twice.

    The set comparison above already fails when one of them goes. This exists
    because of *how* it fails: it is a generic assertion driven by a set, so a
    fold arrives as a diff between two sorted lists, which reads like a fixture
    that needs updating. The failure someone acts on correctly is one whose test
    name says what was lost.

    It is also the second line of defence, and deliberately does not share a
    source with the first. The set above is derived from §7.4's table; the three
    values below are literals in this file. Two assertions reading the same value
    are one assertion, and the eval-gate review found exactly that: the old
    hand-copied tuple meant a fold could edit the enum and the expectation
    together and stay green.

    **Why this pair specifically.** §5.2 routes self-harm to Care immediately and
    abuse aimed at the instructor to the Lead Faculty queue — different
    destinations for different harms. §6.2 gives threat-of-harm and self-harm
    risk a queue suppressed from every instructor and leadership view. §9.3 makes
    the threat and self-harm recall floor the strictest gate in the suite because
    false negatives are the expensive error. A single merged verdict satisfies
    "the contract has a harm value" and quietly makes that floor a measurement
    over a label the spec does not have.

    **The durable second half of this is behavioural and is not here.** E6 owns
    §5.2's routing and should assert a threat and a self-harm classification each
    reach Care as distinct cases; E10 sets the recall floor and must report
    recall per verdict rather than over a merged label. This test is a contract
    assertion and cannot reach either.
    """
    task = TASKS_BY_KEY["moderation"]
    module = contracts_module(import_app_module)
    model = one_contract(module, task)
    _, verdicts, _ = verdict_field(model, task)
    members = list(verdicts)

    threat = [member for member in members if THREAT_VERDICT in spellings(member)]
    self_harm = [member for member in members if SELF_HARM_VERDICT in spellings(member)]

    assert len(threat) == 1 and len(self_harm) == 1, (
        f"`{verdicts.__name__}` does not carry {THREAT_VERDICT!r} and {SELF_HARM_VERDICT!r} as "
        f"one member each: it offers {[member.name for member in members]} with values "
        f"{[member.value for member in members]}, matching {[m.name for m in threat]} for threat "
        f"and {[m.name for m in self_harm]} for self-harm. §7.4's table names both. Folding them "
        "into one verdict — or making one an alias of the other, which leaves it out of the "
        "canonical members iterated here — means §6.2's Care queue cannot tell a threat from a "
        "student at risk, and §9.3's recall floor measures a label the spec does not have."
    )
    assert threat[0] is not self_harm[0], (
        f"`{verdicts.__name__}.{threat[0].name}` and `{verdicts.__name__}.{self_harm[0].name}` "
        "are the same member. An enum with two names for one value routes both harms to "
        "whichever branch is written first, and every `is` comparison in §5.2's routing agrees "
        "with itself while being wrong."
    )
    assert len(members) == MODERATION_VERDICT_COUNT, (
        f"`{verdicts.__name__}` has {len(members)} canonical members "
        f"({[member.name for member in members]}), not {MODERATION_VERDICT_COUNT}. §7.4's table "
        "gives moderation six. This count is written here rather than derived on purpose: it is "
        "the check that survives an edit to the spec table and to the enum in the same change."
    )


CLASSIFIER_TASKS = (TASKS_BY_KEY["validity"], TASKS_BY_KEY["moderation"])


@pytest.mark.parametrize("task", CLASSIFIER_TASKS, ids=[task.key for task in CLASSIFIER_TASKS])
def test_a_verdict_outside_the_closed_set_is_refused_rather_than_coerced(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    task: AiTask,
) -> None:
    """Criterion 4, first half: a wrong enum value raises `ValidationError` rather than coercing.

    The payload differs from the control by one value, so the refusal is
    attributable to that value and to nothing else in the model.

    This is what §7.4 means by "the gateway validates against that model, retries
    on shape violations, and surfaces persistent failures as errors rather than
    letting a malformed classification propagate". A contract that accepts an
    unknown string has nothing for the gateway to retry on: the malformed
    classification is stored, and for the moderation task it is stored as
    something §5.2's routing has no branch for.
    """
    module = contracts_module(import_app_module)
    model = one_contract(module, task)
    payload = representative_payload(model)
    assert_the_control_validates(model, payload)

    name, verdicts, sequence = verdict_field(model, task)
    unknown = [UNKNOWN_VERDICT] if sequence else UNKNOWN_VERDICT

    refusal(
        model,
        replaced(payload, (name,), unknown),
        f"`{model.__name__}` accepted {UNKNOWN_VERDICT!r} as its {name}, which is not a member of "
        f"`{verdicts.__name__}` ({[member.name for member in verdicts]}). Criterion 4: 'A "
        "malformed payload — wrong enum value, missing field — raises `ValidationError` rather "
        f"than coercing.' §7.4's table gives '{task.label}' the output `{task.output}`, and a "
        "verdict outside it is the shape violation the gateway is supposed to retry on.",
    )


@pytest.mark.parametrize("task", CLASSIFIER_TASKS, ids=[task.key for task in CLASSIFIER_TASKS])
def test_a_payload_with_no_verdict_is_refused_rather_than_defaulted(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    task: AiTask,
) -> None:
    """Criterion 4, second half: a missing field raises rather than falling back to a default.

    Separated from the wrong-value case because the wrong implementation is
    different and, for moderation, worse. A verdict field with a default —
    `verdict: Verdict = Verdict.CLEAR` — accepts a provider response that
    contains no verdict at all and stores "clear". Nothing raises, nothing
    retries, and the comment is published: a false negative produced by the
    contract rather than by the model, invisible to §9.3's recall floor because
    the eval case never sees a malformed response.

    The control validates first, so the refusal below is attributable to the
    missing verdict rather than to anything else this file put in the payload.
    """
    module = contracts_module(import_app_module)
    model = one_contract(module, task)
    payload = representative_payload(model)
    assert_the_control_validates(model, payload)

    name, verdicts, _ = verdict_field(model, task)

    refusal(
        model,
        without(payload, (name,)),
        f"`{model.__name__}` validated a payload carrying no `{name}`, so its verdict has a "
        f"default. Criterion 4 refuses that: a missing field raises `ValidationError` rather than "
        f"coercing. A defaulted `{verdicts.__name__}` turns a provider response with no verdict "
        f"into a stored '{task.label}' answer that no retry and no eval case will ever see.",
    )


@pytest.mark.parametrize("task", CLASSIFIER_TASKS, ids=[task.key for task in CLASSIFIER_TASKS])
def test_a_null_verdict_is_refused_rather_than_stored_as_no_finding(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    task: AiTask,
) -> None:
    """An explicit `null` is refused, not only an absent key.

    The test above removes the key. This one sends it as `null`, and they are
    different implementations: a verdict typed `ModerationVerdict | None` with no
    default is *required* — omitting it raises, so the test above passes — and
    `{"verdict": null}` validates, round-trips, and satisfies every other
    assertion in this file. An eval-gate review found it by retyping the field
    and watching the whole suite stay green.

    The end state is the one the defaulted-`CLEAR` shape produces, reached by a
    different route. No `is THREAT` and no `is SELF_HARM` branch matches a null,
    so under §5.2 the comment publishes and never reaches Care (§6.2), and
    §9.3's recall cannot see it either: an eval set holds verdicts and never a
    null, so the case that produces this is not in the measurement. A provider
    that answers `{"verdict": null}` on a comment it found difficult is the
    single most plausible malformed response there is, and it is the one that
    must raise so the gateway retries (§7.4).

    Optionality is the thing being refused, not the value, so this is a claim
    about the annotation: `X | None` cannot be the type of a verdict drawn from a
    closed set, because the set has no member meaning "no finding".
    """
    module = contracts_module(import_app_module)
    model = one_contract(module, task)
    payload = representative_payload(model)
    assert_the_control_validates(model, payload)

    name, verdicts, _ = verdict_field(model, task)

    refusal(
        model,
        replaced(payload, (name,), None),
        f"`{model.__name__}` validated a payload whose `{name}` is null, so its verdict is "
        f"optional — `{verdicts.__name__} | None` or equivalent. §7.4 gives '{task.label}' the "
        f"closed set `{task.output}`, and none of those members means 'no finding'. A null "
        "reaches §5.2's routing as a value no branch matches, so the comment publishes rather "
        "than reaching Care, and §9.3's recall floor never sees the case because an eval set "
        "holds verdicts and never a null. Removing the key already raises; this is the same "
        "absence spelled a way the model currently accepts.",
    )


# ---------------------------------------------------------------------------
# The model configuration the contracts rest on
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("task", TASKS, ids=[task.key for task in TASKS])
def test_a_contract_refuses_a_key_it_does_not_declare(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    task: AiTask,
) -> None:
    """An undeclared key is a shape violation, not something to ignore.

    `extra="forbid"` is what makes that true, and until now nothing asserted it:
    an eval-gate review rewrote the shared `model_config` to `extra="ignore"` and
    every contract test stayed green. That configuration is load-bearing in a way
    the other settings are not. §7.4: "The gateway validates against that model,
    retries on shape violations, and surfaces persistent failures as errors
    rather than letting a malformed classification propagate." A model that
    silently drops keys it does not recognise has no shape violation to report
    for anything a provider *invents* — a `confidence`, a `reason`, a
    `verdict_2`, a misspelled field name — so the retry never fires and the
    classification stored is a partial reading of a response nobody looked at.

    It is asserted **behaviourally and on every contract**, not by reading
    `model_config` off the base class. A later contract can set its own config,
    and reading the base would report a guarantee the subclass had already
    dropped. The payload differs from the control by one key.

    The value sent is a string, so this cannot be passing because of a type
    error: the only thing wrong with the payload is that the model does not
    declare the key.
    """
    module = contracts_module(import_app_module)
    model = one_contract(module, task)
    payload = representative_payload(model)
    assert_the_control_validates(model, payload)

    assert UNDECLARED_PROVIDER_KEY not in all_field_names(model), (
        f"`{model.__name__}` declares a field called {UNDECLARED_PROVIDER_KEY!r}, which this test "
        "sends precisely because no contract should. Rename the constant at the top of this file."
    )

    refusal(
        model,
        {**payload, UNDECLARED_PROVIDER_KEY: "a key no contract declares"},
        f"`{model.__name__}` accepted a payload carrying {UNDECLARED_PROVIDER_KEY!r}, a key it "
        "does not declare, so its model configuration is `extra='ignore'` or `extra='allow'` "
        "rather than `extra='forbid'`. §7.4 has the gateway retry on shape violations and "
        "surface persistent ones as errors; a contract that quietly discards what it does not "
        "recognise turns a provider returning the wrong shape into a classification that looks "
        "clean. Set on the base or per contract — this asserts the behaviour, not where it is "
        "written.",
    )


@pytest.mark.parametrize("task", TASKS, ids=[task.key for task in TASKS])
def test_a_validated_contract_cannot_be_changed_afterwards(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    task: AiTask,
) -> None:
    """`frozen=True`, asserted by trying to write to a validated object.

    The same review flipped `frozen=True` to `frozen=False` with the suite green.
    What it buys is that a contract means one thing for its whole life: §7.4
    makes this object the runtime value, the API response and the eval fixture at
    once, and every one of those readings assumes that what was validated is what
    is read. A mutable contract lets a caller adjust a verdict — or a prompt
    version, or a model ID — after validation, and the auditability §7.4 rests on
    ("a specific prompt version and model ID produced a specific classification")
    becomes a claim about whatever was written last. Nothing would raise, and the
    stored row and the validated object would simply differ.

    **The value assigned is the one the field already holds**, so the assignment
    cannot be refused for being invalid. The only thing wrong with it is that it
    is an assignment. Asserted per contract for the same reason as the test
    above: a subclass can set its own config.

    Any of the three refusals pydantic can raise counts — the property is that
    the write does not land, not which exception carries the news.
    """
    module = contracts_module(import_app_module)
    model = one_contract(module, task)
    payload = representative_payload(model)
    validated = assert_the_control_validates(model, payload)

    fields = list(model.model_fields)
    assert fields, (
        f"`{model.__name__}` declares no fields, so there is nothing to try to write to and this "
        "test would report it immutable whatever the truth is."
    )

    name = fields[0]
    unchanged = getattr(validated, name)

    try:
        setattr(validated, name, unchanged)
    except (ValidationError, TypeError, AttributeError):
        return

    pytest.fail(
        f"`{model.__name__}.{name}` could be assigned after validation, so the contract is not "
        "frozen. §7.4 makes this one object the runtime contract, the API response schema and "
        "the eval fixture, and all three readers assume it still says what it said when it was "
        "validated. A verdict, a prompt version or a model ID that can be rewritten in place "
        "means the classification record and the object it came from can disagree with nothing "
        "raising — and the value assigned here was the field's own, so nothing but the write "
        "itself was wrong with it."
    )


# ---------------------------------------------------------------------------
# What a contract may not carry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("task", TASKS, ids=[task.key for task in TASKS])
def test_no_contract_field_carries_a_students_identity(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    task: AiTask,
) -> None:
    """E0-12's security note: no contract field would carry raw student identity.

    "Worth confirming no contract field would carry raw student identity into an
    AI payload." These models are the output side, and they are also the API
    response schema and the eval fixture (§7.4) — an eval set is a file in the
    repository, so a field named for a student is confidential text checked into
    git and served to whoever can read the response. §4 permits re-identification
    only through the Care queue, only by the Care role, and only with an audit
    entry; a field on a moderation contract is none of those things.

    **This asserts an absence, and an absence is the weak shape** (`docs/
    MISTAKES.md` entry 3): it is satisfied by a contract with no fields at all.
    The guard against that is asserting the contract has fields first, and saying
    here what the assertion cannot see — a field named `handle` or `sortable`
    holding an email address is invisible to any check that reads names, which is
    the same boundary ADR 0022's consequences section draws for the column
    convention it created. The stronger form — assert the query is refused rather
    than that the name is absent — needs a read path, and this ticket ships none.
    """
    module = contracts_module(import_app_module)
    model = one_contract(module, task)
    names = all_field_names(model)

    assert names, (
        f"`{model.__name__}` declares no fields, so this test would report no identity field "
        "whatever the truth is. A contract with no fields is not a contract."
    )

    def carries_identity(name: str) -> bool:
        lowered = name.lower()
        if lowered.startswith(IDENTITY_MARKER_PREFIX):
            return True
        if normalised(name) in IDENTITY_FIELD_NAMES:
            return True
        return any(word in lowered for word in STUDENT_WORDS) and any(
            word in lowered for word in IDENTIFIER_WORDS
        )

    identifying = sorted(name for name in names if carries_identity(name))

    assert not identifying, (
        f"`{model.__name__}` carries {identifying}, which read as a student's identity. E0-12's "
        "definition of done asks the security review to confirm no contract field would carry "
        "raw student identity into an AI payload, and §7.4 makes this model the API response and "
        "the eval fixture as well as the runtime contract — so the name lands in a checked-in "
        "eval file and in an HTTP response. §4: identity is never displayed to instructors or "
        "any leadership role, in any view, and traceability exists only through the audited Care "
        "reveal (§6.2). If one of these is legitimate — an instructor is not anonymous under "
        "§5.3 — the word list at the top of this file is where that is recorded, with the reason."
    )


# ---------------------------------------------------------------------------
# Where the contracts live
# ---------------------------------------------------------------------------


def test_the_contracts_are_the_file_the_strict_mypy_profile_names() -> None:
    """Criterion 6: `app/ai/contracts.py` exists and is in the strict profile.

    Two halves of one sentence, asserted together because the way this fails is
    that they come apart. `pyproject.toml` has named `app.ai.contracts` in the
    strict override since E0-01, before the file existed, and mypy's
    `files = ["backend/app"]` means a contracts *package* — `ai/contracts/
    __init__.py` plus modules beside it — would still be type-checked while every
    submodule fell out of the strict profile, with the gate green. So would
    deleting the module from the override, which is `docs/MISTAKES.md` entry 2:
    the guarantee is in the configuration, and nothing else asserts it is there.

    The flags rather than a `strict = true`, because mypy does not accept that
    key in a per-module section. `STRICT_PROFILE_FLAGS` is the profile E0-01
    wrote, and a deliberate change to it is a change here in the same pull
    request.
    """
    assert CONTRACTS_PATH.is_file(), (
        f"{CONTRACTS_PATH} does not exist. E0-12's scope names the file, SPEC §13 places it, and "
        "criterion 6 requires mypy strict to pass on it. The mypy override in pyproject.toml has "
        "named `app.ai.contracts` since E0-01."
    )

    document = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    overrides = document.get("tool", {}).get("mypy", {}).get("overrides", [])

    assert overrides, (
        f"{PYPROJECT_PATH} declares no per-module mypy overrides, so this test has nothing to "
        "look through and would report the contracts module as unprofiled whatever the truth is."
    )

    def modules_named_by(override: dict[str, Any]) -> list[str]:
        """The modules one override section applies to.

        mypy accepts `module` as a string or as a list of them, and this project
        uses the list form. Reading only one of the two shapes would let a
        rewritten section drop the contracts module with this test still green.
        """
        named = override.get("module")
        if isinstance(named, str):
            return [named]
        return [entry for entry in named or [] if isinstance(entry, str)]

    strict = [override for override in overrides if CONTRACTS_MODULE in modules_named_by(override)]

    assert strict, (
        f"No mypy override in {PYPROJECT_PATH} names `{CONTRACTS_MODULE}`; they name "
        f"{[override.get('module') for override in overrides]}. Criterion 6: the module 'is in "
        "the strict profile'. §7.4 makes it the runtime contract, the API schema and the eval "
        "fixture at once, so an untyped escape in it is an eval hole that type-checking is "
        "supposed to close."
    )

    for override in strict:
        missing = [flag for flag in STRICT_PROFILE_FLAGS if override.get(flag) is not True]
        assert not missing, (
            f"The mypy override naming `{CONTRACTS_MODULE}` does not enable {missing}. Criterion "
            "6 calls this the strict profile, and these flags are what it is made of — mypy "
            "takes no `strict` key per module. Dropping one is a deliberate change and belongs "
            "in a pull request that says which guarantee was given up."
        )
