"""Only one module assigns a section's derived calendar — ticket E0-35.

[ADR 0021](../../docs/adr/0021-a-sections-derived-calendar-has-one-writer.md): the
four columns are `NOT NULL` and "`app.services.section_codes.apply_section_code` is
the only thing that writes them". E0-07 asked for the same thing — "populated
through this service, so there is exactly one path that sets them" — and SPEC §2.2
is where the rule comes from: "Section start/end dates derive from the letter +
term calendar; **nothing is hand-entered per section**."

**What was already asserted, and the half that was not.** Two tests catch a second
writer that *disagrees* with `apply_section_code`, by comparing what a section ends
up with against what the code and the map say it should be. A second writer that
*agrees* is invisible to them, and so is one that writes the same values by a route
nobody compares. E0-08's security review grepped and found no bypass, so the rule
is true — and it is convention, not enforcement, which ADR 0021 records
deliberately. This module is E0-35 turning it into enforcement, in the shape of the
static sweep the read side already uses.

**The rule asserted here.** Every place under `backend/app/` that assigns
`length_weeks`, `start_date`, `end_date` or `modality` onto a section is inside
`backend/app/services/section_codes.py`.

**The grain is the module, not the function.** ADR 0021 names the function, and a
sweep at function grain would go red on a refactor that split a private helper out
of it — a change that alters nothing about the rule, because a helper in that
module called by that function is the same path. One module is the unit the rule
can be stated in without the statement being about the shape of the code inside it.

**What it cannot see, so that nothing here is cited as more than it is** (ADR 0062
states the same limits for the mock-idp gate, and the first two are the same):

  - **It is syntactic, not dataflow.** It sees the shape of an assignment, never
    what is being assigned to. `setattr(row, name, value)` with a computed `name`,
    a bulk update built from a dict assembled at run time, or a write through a
    helper that takes the column name as an argument, are all invisible.
  - **It reads the source rather than the running application**, so an assignment
    reached through a mapper event, an ORM cascade or a library call is invisible
    too.
  - **It says nothing about correctness.** A second module that assigned these
    four columns with the right values would fail here, and a `section_codes.py`
    that assigned the wrong ones would pass. The two tests over the derivation are
    the other half, and neither implies the other.
  - **The one control below is load-bearing, and it is the honest limit.** If this
    sweep cannot find the sanctioned writer, then it cannot see the way this
    codebase actually sets these columns, and its silence about every other module
    is worth nothing. E0-35 anticipates that outcome and names the alternative:
    amend ADR 0021 to say plainly that "exactly one path" is unenforced. The
    failure message says so, because a red control here is a decision to make and
    not a line to adjust.
"""

import ast
from pathlib import Path
from typing import Any, NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"
SANCTIONED_MODULE = APP_ROOT / "services" / "section_codes.py"
SANCTIONED_FUNCTION = "apply_section_code"

# The four columns ADR 0021 gives one writer. §8 names three of them — "section
# `length_weeks` and start/end dates derive from the section code via
# `start_letter_map`" — and §2.2 adds the modality, "`{startLetter}{ordinal}
# {modality}`… Modality: `WW` online, `FF` face-to-face."
DERIVED_COLUMNS = ("length_weeks", "start_date", "end_date", "modality")

# Directories with no source of ours in them.
UNSWEPT_DIRECTORIES = frozenset({"__pycache__", ".mypy_cache", ".ruff_cache"})

# Calls that carry column names into a row. Narrow on purpose: an ordinary helper
# with a `start_date=` parameter is not a writer, and a sweep that flagged one
# would be red against arithmetic that ADR 0021 puts in this very service.
#
# Two of these names are ordinary English as well as ORM verbs. A dictionary
# updated with `mapping.update(start_date=…)` outside the sanctioned service is
# read here as a write, which over-flags — and over-flagging in a rule with one
# permitted module fails loudly and is fixed in a line, where under-flagging is
# the failure this whole sweep exists to stop being silent.
PERSISTENCE_CALLS = frozenset(
    {"values", "update", "insert", "merge", "add", "bulk_insert_mappings", "bulk_update_mappings"}
)


class AssignmentSite(NamedTuple):
    """One place a module sets a derived calendar column on a row."""

    path: Path
    line: int
    column: str
    shape: str
    source: str


def called_name(node: ast.Call) -> str | None:
    """The name being called, whether it is a method or a bare function."""
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def assigned_attributes(target: ast.AST) -> list[ast.Attribute]:
    """Every attribute being assigned to under one assignment target.

    Walks the target so that `section.start_date, section.end_date = window` counts
    as two sites rather than none — a tuple assignment is the shortest way to write
    the thing this rule forbids, and it is the one a careful implementer reaches
    for when the values arrive together.
    """
    return [
        node
        for node in ast.walk(target)
        if isinstance(node, ast.Attribute) and node.attr in DERIVED_COLUMNS
    ]


def assignment_sites(
    source: str, path: Path, section_classes: tuple[str, ...]
) -> list[AssignmentSite]:
    """Every place `source` sets one of the four derived columns on a row.

    Three shapes, each of which has to be one somebody would actually write:
    assigning the attribute, `setattr` with the name spelled out, and handing the
    column to a call that persists it — either a section's own constructor or a
    statement's `values`.
    """
    tree = ast.parse(source)
    found: list[AssignmentSite] = []

    def record(node: ast.AST, column: str, shape: str) -> None:
        found.append(
            AssignmentSite(
                path=path,
                line=getattr(node, "lineno", 0),
                column=column,
                shape=shape,
                source=ast.get_source_segment(source, node) or "",
            )
        )

    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign | ast.AugAssign):
            targets = [node.target]
        for target in targets:
            for attribute in assigned_attributes(target):
                record(node, attribute.attr, "an attribute assignment")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = called_name(node)

        if name == "setattr" and len(node.args) >= 2:
            named = node.args[1]
            if isinstance(named, ast.Constant) and named.value in DERIVED_COLUMNS:
                record(node, str(named.value), "a `setattr` with the column named")

        if name not in PERSISTENCE_CALLS and name not in section_classes:
            continue
        shape = (
            "a section constructed with the column"
            if name in section_classes
            else "a column handed to a call that persists it"
        )
        for keyword in node.keywords:
            if keyword.arg in DERIVED_COLUMNS:
                record(node, str(keyword.arg), shape)
        for argument in node.args:
            for inner in ast.walk(argument):
                if not isinstance(inner, ast.Dict):
                    continue
                for key in inner.keys:
                    if isinstance(key, ast.Constant) and key.value in DERIVED_COLUMNS:
                        record(node, str(key.value), shape)
    return found


def swept_modules(root: Path) -> list[Path]:
    """Every Python source file under `root`, in a stable order."""
    return sorted(
        path
        for path in root.rglob("*.py")
        if not any(part in UNSWEPT_DIRECTORIES for part in path.parts)
    )


def mapped_classes_for(import_app_module: Any, table_name: str) -> tuple[str, ...]:
    """The mapped classes over one table, discovered rather than listed.

    The same discovery, for the same reason, as
    `tests/unit/test_every_writer_of_an_lms_owned_relation_names_the_guard.py`: a
    class name written into a test file is a second spelling of something the
    registry already knows, and it goes stale on a rename with nothing failing.
    """
    package = import_app_module("app.models")
    if package is None:
        pytest.fail(
            "There is no `app.models` package, so no mapped class can be discovered and this "
            "sweep cannot recognise a section being constructed. "
            "`tests/unit/test_org_models_registered.py` diagnoses the absence."
        )
    base_module = import_app_module("app.models.base")
    registry = getattr(getattr(base_module, "Base", None), "registry", None)
    if registry is None:
        pytest.fail(
            "`app.models.base` is missing, or exposes no `Base` with a `registry`. E0-04 ships "
            "the declarative base there."
        )
    return tuple(
        sorted(
            mapper.class_.__name__
            for mapper in registry.mappers
            if any(table.name == table_name for table in mapper.tables)
        )
    )


# The inventory the control samples are read against. Synthetic, so a control does
# not pass by borrowing whatever the real discovery happened to return.
CONTROL_CLASSES = ("Section",)
CONTROL_MODULE = Path("roster_sync.py")

# One of each shape that has to be caught. `docs/MISTAKES.md` entry 35: a guard has
# to be made to *find* each mechanism on a subject that certainly has it, or its
# silence over the application is a fact about the guard. Nothing here is executed.
ASSIGNMENTS_MUST_CATCH = {
    "an attribute assignment": "section.length_weeks = derived.length_weeks\n",
    "a tuple assignment of two columns": "section.start_date, section.end_date = window\n",
    "an augmented assignment": "section.length_weeks += 1\n",
    "an annotated assignment": "section.modality: str = code.modality\n",
    "a `setattr` with the column named": 'setattr(section, "modality", modality)\n',
    "a section constructed with its calendar": (
        "session.add(Section(length_weeks=weeks, start_date=start))\n"
    ),
    "a Core update naming the column": (
        "session.execute(update(Section).values(length_weeks=weeks))\n"
    ),
    "a Core update built from a dict literal": (
        'session.execute(update(Section).values({"end_date": end}))\n'
    ),
}

# The near misses. Each is a line the sanctioned service, a report, or a model is
# entitled to write, and each differs from something above by one property: what is
# being assigned to, or what is being called.
ASSIGNMENTS_MUST_ALLOW = {
    "a local variable of the same name": "start_date = row.start_date\n",
    "a read of the column": "if section.start_date is None:\n    return None\n",
    "a model declaring the column": (
        "class Section(Base):\n    length_weeks: Mapped[int] = mapped_column()\n"
    ),
    "a helper called with the column names as parameters": (
        "weeks = weeks_between(start_date=term.start_date, end_date=term.end_date)\n"
    ),
    "a value object built from the derivation": (
        "return DerivedCalendar(length_weeks=weeks, start_date=start, end_date=end)\n"
    ),
    # Allowed, and it is a hole rather than a virtue. A mapping built here and
    # handed to a persistence call somewhere else writes the calendar and is
    # invisible to a syntactic sweep, which is the first limit in the module
    # docstring written as a sample so that nobody has to infer it
    # (`docs/MISTAKES.md` entry 14: an enumeration is not an impossibility).
    "a dict literal that is not handed to a persistence call": (
        'payload = {"start_date": start, "end_date": end}\n'
    ),
    "prose in a docstring": '"""Only `apply_section_code` sets `start_date` on a section."""\n',
}


def test_the_assignment_sweep_finds_every_shape_it_claims_to_and_allows_their_near_misses() -> None:
    """The control, run before this file's silence over `backend/app/` counts as evidence.

    The allow half is the expensive one. `apply_section_code` computes dates from a
    map row, so the sanctioned service itself is full of local variables called
    `start_date` and helpers called with them; a sweep that read those as writes
    would be red against the one implementation the rule exists to permit, and the
    fix somebody reaches for is to delete the sweep.

    The sharpest pair is the model declaration against the attribute assignment.
    `length_weeks: Mapped[int] = mapped_column()` is an assignment to a bare name in
    a class body, and `section.length_weeks = ...` is an assignment to an attribute
    on a row; a rule that could not tell them apart would fail the model that
    declares the columns in the first place.
    """
    for case, sample in sorted(ASSIGNMENTS_MUST_CATCH.items()):
        found = assignment_sites(sample, CONTROL_MODULE, CONTROL_CLASSES)
        assert found, (
            f"The sweep found no assignment in {case} ({sample!r}), which sets a derived calendar "
            "column on a row. A detector that has gone blind reads exactly like an application "
            "with one writer in it."
        )

    for case, sample in sorted(ASSIGNMENTS_MUST_ALLOW.items()):
        found = assignment_sites(sample, CONTROL_MODULE, CONTROL_CLASSES)
        assert not found, (
            f"The sweep read {[site.column for site in found]} out of {case} ({sample!r}), which "
            "assigns nothing onto a section. Every assertion in this module rests on the detector "
            "saying no to code the sanctioned service is entitled to contain."
        )


def test_the_section_table_carries_the_four_columns_this_sweep_names(
    configured_env: dict[str, str], import_app_module: Any
) -> None:
    """The names are checked against the schema, not against this file.

    `DERIVED_COLUMNS` is four strings written by hand, and a sweep for a column that
    has been renamed finds nothing and reports success — `docs/MISTAKES.md` entry 1,
    a record going on asserting something a change has made false, in the form where
    nothing goes red. E0-07 adds these four to `section` and ADR 0021 makes them
    `NOT NULL`, so they are all present or the rule is about something else now.
    """
    package = import_app_module("app.models")
    assert package is not None, (
        "There is no `app.models` package to walk. `tests/unit/test_org_models_registered.py` "
        "diagnoses the absence."
    )
    base_module = import_app_module("app.models.base")
    metadata = getattr(getattr(base_module, "Base", None), "metadata", None)
    assert metadata is not None, (
        "`app.models.base` exposes no `Base` with `metadata`, so there is nothing to check the "
        "column names against."
    )

    table = metadata.tables.get("section")
    assert table is not None, (
        f"No `section` table on `Base.metadata` (it holds {sorted(metadata.tables)}). E0-05 "
        "creates it and E0-07 adds the derived columns to it."
    )

    present = {column.name for column in table.columns}
    missing = sorted(set(DERIVED_COLUMNS) - present)
    assert not missing, (
        f"`section` has no {missing} column — it has {sorted(present)}. `DERIVED_COLUMNS` in this "
        "file is the sweep's whole subject, so a column spelled differently in the schema is a "
        "column this module sweeps for and never finds, and every assertion below would pass by "
        "looking for something that is not there."
    )


def test_the_sanctioned_writer_is_visible_to_this_sweep(
    configured_env: dict[str, str], import_app_module: Any
) -> None:
    """The one subject that certainly has the property, which the sweep must find.

    `docs/MISTAKES.md` entry 35: when a guard enumerates mechanisms, require it to
    find each one on a subject that certainly has it. `apply_section_code` sets all
    four of these columns — that is what ADR 0021 records — so a sweep that cannot
    see it there cannot see the way this codebase writes them at all, and its
    silence about every other module is a fact about the sweep.

    **A failure here is a decision, not an adjustment.** E0-35's criterion has two
    branches: "a second assignment site for any of the four derived section columns
    fails something, **or** ADR 0021 is amended to say plainly that this is
    unenforced and why that is acceptable." If the writer sets these columns in a
    shape no syntactic sweep can follow — a `setattr` over a computed name, a
    mapping built at run time, a helper that takes the column as an argument — then
    the first branch is not available and the second is the honest answer. Do not
    widen the shapes in this file until they happen to match; that produces a sweep
    shaped like today's implementation, which passes for it and for nothing else.
    """
    assert SANCTIONED_MODULE.is_file(), (
        f"{SANCTIONED_MODULE.relative_to(REPO_ROOT)} does not exist. ADR 0021 puts the one writer "
        f"of the derived calendar there, in `{SANCTIONED_FUNCTION}`, and E0-07 shipped it."
    )

    section_classes = mapped_classes_for(import_app_module, "section")
    assert section_classes, (
        "No mapped class over the `section` table was found on `Base.registry`, so this sweep "
        "cannot recognise a section being constructed with its calendar — one of the three "
        "shapes it claims to see."
    )

    source = SANCTIONED_MODULE.read_text(encoding="utf-8")
    sites = assignment_sites(source, SANCTIONED_MODULE, section_classes)
    seen = {site.column for site in sites}
    unseen = sorted(set(DERIVED_COLUMNS) - seen)

    assert not unseen, "\n".join(
        [
            f"This sweep found no assignment of {unseen} in "
            f"{SANCTIONED_MODULE.relative_to(REPO_ROOT)}, which ADR 0021 makes the only writer of "
            "all four.",
            "",
            f"It found: {sorted((site.column, site.shape) for site in sites)}.",
            "",
            "Two possibilities, and they need different fixes. Either the writer has moved, in "
            "which case this file's `SANCTIONED_MODULE` is wrong and ADR 0021 is out of date with "
            "it — or the writer sets these columns in a shape a syntactic sweep cannot follow, in "
            "which case E0-35's second branch applies: amend ADR 0021 to say plainly that "
            "'exactly one path' is unenforced and why that is acceptable. What is not an answer "
            "is widening the shapes in this file until they match the current implementation.",
        ]
    )


def test_no_module_outside_the_sanctioned_service_assigns_a_derived_calendar_column(
    configured_env: dict[str, str], import_app_module: Any
) -> None:
    """The criterion: a second assignment site fails something.

    ADR 0021 rejected a `CHECK` tying the calendar columns together as "a second
    authority for one rule: the arithmetic already lives in the one service path
    that produces these values from a map row the database constrains". That
    argument holds exactly as long as there *is* one service path. A second writer
    that agrees with the first is invisible to the derivation tests, costs nothing
    the day it lands, and is what makes the schema's silence about these columns
    correct — until the map is edited, or the inclusive end-date convention of
    ADR 0020 is read differently in the second place than in the first.

    **The mutation this exists to survive** is E1's roster sync filling the four
    columns as it creates a section, with the same arithmetic, because calling the
    service for each row looked like an extra query. Nothing would have failed.
    """
    modules = swept_modules(APP_ROOT)
    assert modules, (
        f"There are no Python modules under {APP_ROOT.relative_to(REPO_ROOT)}, so this sweep read "
        "nothing and would report success. SPEC §13 puts the application there."
    )

    section_classes = mapped_classes_for(import_app_module, "section")
    sanctioned = SANCTIONED_MODULE.resolve()

    offenders: list[str] = []
    for path in modules:
        if path.resolve() == sanctioned:
            continue
        source = path.read_text(encoding="utf-8")
        try:
            sites = assignment_sites(source, path, section_classes)
        except SyntaxError as failure:  # pragma: no cover - a broken source tree
            pytest.fail(
                f"{path.relative_to(REPO_ROOT)} does not parse ({failure}), so this sweep cannot "
                "read it and would report success having skipped it."
            )
        offenders.extend(
            f"  {path.relative_to(REPO_ROOT)}:{site.line}  {site.column} — {site.shape}: "
            f"{site.source}"
            for site in sites
        )

    assert not offenders, "\n".join(
        [
            "These assign a section's derived calendar outside the one path that owns it:",
            *offenders,
            "",
            "SPEC §2.2: 'Section start/end dates derive from the letter + term calendar; nothing "
            "is hand-entered per section.' ADR 0021: the four columns are NOT NULL and "
            f"`app.services.section_codes.{SANCTIONED_FUNCTION}` is the only thing that writes "
            "them — it reads the section's term from `section.term_id` rather than taking a term "
            "as an argument, so no caller can derive a section's calendar from a term it does not "
            "belong to. A second site is a second reading of the start-letter map, and the two "
            "disagree the first time one of them is fixed.",
            "",
            f"Call `{SANCTIONED_FUNCTION}` instead. If a second path genuinely has to set these "
            "columns, that contradicts ADR 0021 and the record has to change before the code "
            "does.",
        ]
    )
