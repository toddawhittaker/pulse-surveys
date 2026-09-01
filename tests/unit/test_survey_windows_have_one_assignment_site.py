"""Only one module writes a survey window — ticket E2-06, criterion 4.

"No code outside the one writer writes `survey_window` (the E0-35 sweep pattern
already used for section calendars extends or its absence is recorded in the
ADR)." This module is the extension, and it is deliberately the same instrument
as `tests/unit/test_a_sections_derived_calendar_has_one_assignment_site.py` —
same AST walk, same three shapes, same control-first discipline — over a
different table.

**Why the rule is worth enforcing rather than reviewing.** ADR 0021's shape is
one writer per derived thing, and a window is derived: from the section's course
weeks, the term's calendar and §3.1's rhythm. A second writer that *agrees*
costs nothing the day it lands and is invisible to every test in
`tests/integration/test_survey_windows_derive_from_the_term_calendar.py`, which
compares what the service produced against hand-written instants. It becomes
visible the first time the institution's timezone is edited, or the first time
somebody fixes the daylight-saving conversion in one of the two places — and by
then two sections in the same term have windows an hour apart with nothing
saying which is right. E2-08's submissions and §3.4's participation denominator
are both keyed to these rows.

**Two column sets, not one, and the split is the whole design of this sweep.**

  - `opens_at` and `closes_at` belong to `survey_window` and to nothing else in
    this schema, so an assignment of either, on any subject, is a window being
    written. They are swept in every shape.
  - `section_id`, `week_id` and `term_id` are ordinary foreign keys that half the
    schema carries — `role_assignment.section_id`, `week.term_id`,
    `start_letter_map.term_id`, `section.term_id`, and every launch and roster
    path that creates one of those rows. A sweep that flagged them on any subject
    would be red against code E1 and E0 shipped correctly, and the repair
    somebody reaches for is to delete the sweep. So those three are swept only
    where the surrounding statement names the window's own mapped class.

The consequence is stated plainly rather than left to be discovered: a second
writer that sets **only** `section_id`, `week_id` and `term_id` through a
statement that never names `SurveyWindow` is invisible here. It is also a writer
that cannot insert a row, because `opens_at` and `closes_at` are `NOT NULL`
(E2-05) — which is what makes the narrow set sufficient for the shapes that
matter and not merely convenient.

**What it cannot see, so that nothing here is cited as more than it is.** The
same four limits E0-35's module lists, unchanged, because it is the same
instrument: it is syntactic rather than dataflow, so a `setattr` over a computed
name or a mapping assembled at run time is invisible; it reads the source rather
than the running application, so a mapper event or an ORM cascade is invisible;
it says nothing about correctness, which is the derivation suites' half; and the
positive control below is load-bearing — a sweep that cannot find the sanctioned
writer is a sweep whose silence about every other module is worth nothing.
"""

import ast
from pathlib import Path
from typing import Any, NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"

# E2-06's work order: the one writer is a new service module, because nothing
# existing fits — `section_codes` is calendar parsing and `clock` is time.
SANCTIONED_MODULE = APP_ROOT / "services" / "survey_windows.py"
SANCTIONED_FUNCTION = "derive_windows_for_section"

# The table, and the mapped class discovered from it rather than named.
SURVEY_WINDOW_TABLE = "survey_window"

# `survey_window`'s own two columns: the instants SPEC §3.1's rhythm produces.
# Nothing else in this schema carries either name.
WINDOW_ONLY_COLUMNS = ("opens_at", "closes_at")

# The three keys E2-05 gives the window, each of which is an ordinary foreign key
# elsewhere. Swept only inside a statement that names the window's mapped class.
SHARED_KEY_COLUMNS = ("section_id", "week_id", "term_id")

WINDOW_COLUMNS = (*SHARED_KEY_COLUMNS, *WINDOW_ONLY_COLUMNS)

# Directories with no source of ours in them.
UNSWEPT_DIRECTORIES = frozenset({"__pycache__", ".mypy_cache", ".ruff_cache"})

# Calls that carry column names into a row. The same narrow set E0-35's module
# uses, and narrow for the same reason: an ordinary helper with an `opens_at=`
# parameter is not a writer.
PERSISTENCE_CALLS = frozenset(
    {"values", "update", "insert", "merge", "add", "bulk_insert_mappings", "bulk_update_mappings"}
)


class AssignmentSite(NamedTuple):
    """One place a module sets a survey window's column on a row."""

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


def names_a_window(node: ast.AST, window_classes: tuple[str, ...]) -> bool:
    """Whether this expression mentions the window's mapped class or its table.

    What admits `section_id`, `week_id` and `term_id` into the sweep. A statement
    that names `SurveyWindow` — or the table by its own name — and hands it one of
    those three is writing a window; the same three handed to anything else are
    the foreign keys the rest of the schema is built out of.
    """
    wanted = {*window_classes, SURVEY_WINDOW_TABLE}
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and inner.id in wanted:
            return True
        if isinstance(inner, ast.Attribute) and inner.attr in wanted:
            return True
        if isinstance(inner, ast.Constant) and inner.value in wanted:
            return True
    return False


def assigned_attributes(target: ast.AST) -> list[ast.Attribute]:
    """Every window-only attribute being assigned to under one assignment target.

    Walks the target so that `window.opens_at, window.closes_at = span` counts as
    two sites rather than none — a tuple assignment is the shortest way to write
    the thing this rule forbids, and the two instants arrive together.
    """
    return [
        node
        for node in ast.walk(target)
        if isinstance(node, ast.Attribute) and node.attr in WINDOW_ONLY_COLUMNS
    ]


def assignment_sites(
    source: str, path: Path, window_classes: tuple[str, ...]
) -> list[AssignmentSite]:
    """Every place `source` writes a survey window's columns onto a row."""
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
            if isinstance(named, ast.Constant) and named.value in WINDOW_ONLY_COLUMNS:
                record(node, str(named.value), "a `setattr` with the column named")

        if name not in PERSISTENCE_CALLS and name not in window_classes:
            continue
        shape = (
            "a window constructed with the column"
            if name in window_classes
            else "a column handed to a call that persists it"
        )
        # The shared keys count only where the statement says which table it is
        # about; the window's own two instants count wherever they appear.
        columns = (
            WINDOW_COLUMNS
            if name in window_classes or names_a_window(node, window_classes)
            else WINDOW_ONLY_COLUMNS
        )
        for keyword in node.keywords:
            if keyword.arg in columns:
                record(node, str(keyword.arg), shape)
        for argument in node.args:
            for inner in ast.walk(argument):
                if not isinstance(inner, ast.Dict):
                    continue
                for key in inner.keys:
                    if isinstance(key, ast.Constant) and key.value in columns:
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

    A third copy of this discovery, and deliberately so: E0-35's module says the
    same about the second, "a class name written into a test file is a second
    spelling of something the registry already knows, and it goes stale on a
    rename with nothing failing". Sharing it would mean editing a shipped
    ticket's test module to import from this one.
    """
    package = import_app_module("app.models")
    if package is None:
        pytest.fail(
            "There is no `app.models` package, so no mapped class can be discovered and this "
            "sweep cannot recognise a window being constructed. "
            "`tests/unit/test_term_models_registered.py` diagnoses the absence."
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
CONTROL_CLASSES = ("SurveyWindow",)
CONTROL_MODULE = Path("jobs/tasks.py")

# One of each shape that has to be caught. `docs/MISTAKES.md` entry 35: a guard
# has to be made to *find* each mechanism on a subject that certainly has it, or
# its silence over the application is a fact about the guard. Nothing here runs.
ASSIGNMENTS_MUST_CATCH = {
    "an attribute assignment of an instant": "window.opens_at = friday_evening\n",
    "a tuple assignment of both instants": "window.opens_at, window.closes_at = span\n",
    "an augmented assignment": "window.closes_at += timedelta(hours=1)\n",
    "an annotated assignment": "window.opens_at: datetime = opens\n",
    "a `setattr` with the column named": 'setattr(window, "closes_at", closes)\n',
    "a window constructed with its instants": (
        "session.add(SurveyWindow(opens_at=opens, closes_at=closes))\n"
    ),
    "a window constructed with only its keys": (
        "session.add(SurveyWindow(section_id=section.id, week_id=week.id, term_id=term.id))\n"
    ),
    "a Core insert naming the instants": (
        "session.execute(insert(SurveyWindow).values(opens_at=opens))\n"
    ),
    "a Core update naming a key beside the table": (
        "session.execute(update(SurveyWindow).values(week_id=week.id))\n"
    ),
    "a Core insert built from a dict literal": (
        'session.execute(insert(SurveyWindow).values({"closes_at": closes}))\n'
    ),
}

# The near misses. Each is a line the application is entitled to contain, and each
# differs from something above by one property: what is being assigned to, or what
# is being named in the statement.
ASSIGNMENTS_MUST_ALLOW = {
    "a local variable of the same name": "opens_at = window.opens_at\n",
    "a read of the column": "if window.closes_at < now:\n    return None\n",
    "a model declaring the column": (
        "class SurveyWindow(Base):\n    opens_at: Mapped[datetime] = mapped_column()\n"
    ),
    "a helper called with the instants as parameters": (
        "span = window_span(opens_at=friday, closes_at=sunday)\n"
    ),
    "a value object built from the derivation": (
        "return DerivedWindow(opens_at=opens, closes_at=closes)\n"
    ),
    # The three that make the split at the top of this module worth having. Each
    # writes a foreign key `survey_window` also carries, onto a different table,
    # which E0-09, E0-07 and E1-10 all do legitimately.
    "an assignment naming a section on a role assignment": (
        "session.add(RoleAssignment(section_id=section.id, role=role))\n"
    ),
    "a week row constructed with its term": (
        "session.add(Week(term_id=term.id, number=number, term_length_weeks=term.length_weeks))\n"
    ),
    "a section moved to a term": "section.term_id = term.id\n",
    # Allowed, and it is a hole rather than a virtue — the module docstring names
    # it (`docs/MISTAKES.md` entry 14: an enumeration is not an impossibility).
    "a dict literal that is not handed to a persistence call": (
        'payload = {"opens_at": opens, "closes_at": closes}\n'
    ),
    "prose in a docstring": '"""Only `derive_windows_for_section` writes `opens_at`."""\n',
}


def test_the_window_sweep_finds_every_shape_it_claims_to_and_allows_their_near_misses() -> None:
    """The control, run before this file's silence over `backend/app/` counts as evidence.

    `docs/MISTAKES.md` entry 3: a pattern searched against a file is a case of a
    test passing for an unrelated reason and looks like none, so it is run against
    the text it claims to catch *and* the text it claims to allow.

    **The allow half is the expensive one here, and it is what the two column sets
    exist for.** `section_id`, `week_id` and `term_id` are written legitimately all
    over this application — a role assignment scoped to a section, a week row
    carrying its term, a section provisioned into one — and a sweep that read those
    as windows being written would be red against three shipped tickets at once.
    The three near misses in the middle of `ASSIGNMENTS_MUST_ALLOW` are exactly
    those lines, and the two "constructed with only its keys" and "naming a key
    beside the table" cases above are the same three columns in a statement that
    does name the window. If a change makes those two groups indistinguishable,
    this test says so before any conclusion is drawn from the sweep's silence.

    The sharpest pair is still E0-35's: a model declaring the column against an
    attribute assignment. `opens_at: Mapped[datetime] = mapped_column()` is an
    assignment to a bare name in a class body and `window.opens_at = ...` is an
    assignment to an attribute on a row; a rule that could not tell them apart
    would fail the model that declares the columns in the first place.
    """
    for case, sample in sorted(ASSIGNMENTS_MUST_CATCH.items()):
        found = assignment_sites(sample, CONTROL_MODULE, CONTROL_CLASSES)
        assert found, (
            f"The sweep found no assignment in {case} ({sample!r}), which writes a survey window. "
            "A detector that has gone blind reads exactly like an application with one writer in "
            "it."
        )

    for case, sample in sorted(ASSIGNMENTS_MUST_ALLOW.items()):
        found = assignment_sites(sample, CONTROL_MODULE, CONTROL_CLASSES)
        assert not found, (
            f"The sweep read {[site.column for site in found]} out of {case} ({sample!r}), which "
            "writes no survey window. Every assertion in this module rests on the detector saying "
            "no to code the rest of the application is entitled to contain."
        )


def test_the_survey_window_table_carries_the_columns_this_sweep_names(
    configured_env: dict[str, str], import_app_module: Any
) -> None:
    """The names are checked against the schema, not against this file.

    `WINDOW_COLUMNS` is five strings written by hand, and a sweep for a column that
    has been renamed finds nothing and reports success — `docs/MISTAKES.md` entry
    1, a record going on asserting something a change has made false, in the form
    where nothing goes red. E0-06 created `opens_at`, `closes_at`, `section_id` and
    `week_id`; E2-05 added `term_id` and made it `NOT NULL`.

    It also asserts that `opens_at` and `closes_at` are on **no other table**,
    which is the premise the narrow set rests on: those two are swept on any
    subject precisely because nothing else in this schema is called either.
    """
    package = import_app_module("app.models")
    assert package is not None, (
        "There is no `app.models` package to walk. `tests/unit/test_term_models_registered.py` "
        "diagnoses the absence."
    )
    base_module = import_app_module("app.models.base")
    metadata = getattr(getattr(base_module, "Base", None), "metadata", None)
    assert metadata is not None, (
        "`app.models.base` exposes no `Base` with `metadata`, so there is nothing to check the "
        "column names against."
    )

    table = metadata.tables.get(SURVEY_WINDOW_TABLE)
    assert table is not None, (
        f"No `{SURVEY_WINDOW_TABLE}` table on `Base.metadata` (it holds {sorted(metadata.tables)}). "
        "E0-06 creates it in `backend/app/models/term.py` and E2-05 adds its term rule."
    )

    present = {column.name for column in table.columns}
    missing = sorted(set(WINDOW_COLUMNS) - present)
    assert not missing, (
        f"`{SURVEY_WINDOW_TABLE}` has no {missing} column — it has {sorted(present)}. "
        "`WINDOW_COLUMNS` in this file is the sweep's whole subject, so a column spelled "
        "differently in the schema is one this module sweeps for and never finds, and every "
        "assertion below would pass by looking for something that is not there."
    )

    elsewhere = sorted(
        f"{name}.{column}"
        for name, other in metadata.tables.items()
        if name != SURVEY_WINDOW_TABLE
        for column in WINDOW_ONLY_COLUMNS
        if column in other.c
    )
    assert not elsewhere, (
        f"These columns share a name with a survey window's own instants: {elsewhere}. This sweep "
        f"flags {list(WINDOW_ONLY_COLUMNS)} on any subject at all, on the strength of nothing else "
        "in the schema being called either — so a second table with one of these names makes the "
        "sweep red against a module writing that other table, and the two column sets at the top "
        "of this file have to be re-cut before anything here is believed."
    )


def test_the_sanctioned_writer_is_visible_to_this_sweep(
    configured_env: dict[str, str], import_app_module: Any
) -> None:
    """The one subject that certainly has the property, which the sweep must find.

    `docs/MISTAKES.md` entry 35: when a guard enumerates mechanisms, require it to
    find each one on a subject that certainly has it. E2-06's service writes both
    instants onto every window it creates — that is what the ticket is — so a
    sweep that cannot see it there cannot see the way this codebase writes windows
    at all, and its silence about every other module is a fact about the sweep.

    **A failure here is a decision, not an adjustment.** E2-06's criterion 4 has
    two branches, in the ticket's own words: the sweep "extends **or** its absence
    is recorded in the ADR". If the writer creates windows in a shape no syntactic
    sweep can follow — a mapping built at run time, a bulk insert assembled from
    tuples, a `setattr` over a computed name — then the first branch is not
    available and the second is the honest answer: ADR 0111 says plainly that
    "one writer" is unenforced here and why that is acceptable. Do not widen the
    shapes in this file until they happen to match; that produces a sweep shaped
    like today's implementation, which passes for it and for nothing else.
    """
    assert SANCTIONED_MODULE.is_file(), (
        f"{SANCTIONED_MODULE.relative_to(REPO_ROOT)} does not exist. E2-06 puts the one writer of "
        f"`{SURVEY_WINDOW_TABLE}` there, in `{SANCTIONED_FUNCTION}`."
    )

    window_classes = mapped_classes_for(import_app_module, SURVEY_WINDOW_TABLE)
    assert window_classes, (
        f"No mapped class over the `{SURVEY_WINDOW_TABLE}` table was found on `Base.registry`, so "
        "this sweep cannot recognise a window being constructed — one of the three shapes it "
        "claims to see, and the one the sanctioned writer is most likely to use."
    )

    source = SANCTIONED_MODULE.read_text(encoding="utf-8")
    sites = assignment_sites(source, SANCTIONED_MODULE, window_classes)
    seen = {site.column for site in sites}
    unseen = sorted(set(WINDOW_ONLY_COLUMNS) - seen)

    assert not unseen, "\n".join(
        [
            f"This sweep found no assignment of {unseen} in "
            f"{SANCTIONED_MODULE.relative_to(REPO_ROOT)}, which E2-06 makes the only writer of "
            "every one of them.",
            "",
            f"It found: {sorted((site.column, site.shape) for site in sites)}.",
            "",
            "Two possibilities, and they need different fixes. Either the writer has moved, in "
            "which case this file's `SANCTIONED_MODULE` is wrong — or the writer creates windows "
            "in a shape a syntactic sweep cannot follow, in which case criterion 4's second "
            "branch applies and ADR 0111 records that the rule is unenforced and why. What is not "
            "an answer is widening the shapes in this file until they match the implementation.",
        ]
    )


def test_no_module_outside_the_sanctioned_service_writes_a_survey_window(
    configured_env: dict[str, str], import_app_module: Any
) -> None:
    """Criterion 4: a second write site fails something.

    **The mutation this exists to survive** is the Celery task writing the rows
    itself. E2-06's work order puts a `derive_survey_windows` task in
    `app/jobs/tasks.py` that opens a session, walks the sections and calls the
    service — and the shortest way to write that task is to inline the loop, since
    the arithmetic is four lines and the task already has the session. Nothing
    would fail: the rows would be identical the day it landed, and the two copies
    would disagree the first time the institution's timezone changed or the
    daylight-saving conversion was fixed in one of them.

    The second is `scripts/seed.py`, which the same work order has calling the
    service after `seed_sections()`. That file is outside `backend/app/` and so
    outside this sweep — named here rather than left implicit, because a reader
    checking whether the rule is enforced everywhere should not have to infer the
    boundary from `APP_ROOT`.
    """
    modules = swept_modules(APP_ROOT)
    assert modules, (
        f"There are no Python modules under {APP_ROOT.relative_to(REPO_ROOT)}, so this sweep read "
        "nothing and would report success. SPEC §13 puts the application there."
    )

    window_classes = mapped_classes_for(import_app_module, SURVEY_WINDOW_TABLE)
    sanctioned = SANCTIONED_MODULE.resolve()

    offenders: list[str] = []
    for path in modules:
        if path.resolve() == sanctioned:
            continue
        source = path.read_text(encoding="utf-8")
        try:
            sites = assignment_sites(source, path, window_classes)
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
            "These write a survey window outside the one path that owns it:",
            *offenders,
            "",
            "SPEC §3.1 makes a section's windows a derivation from its calendar and the "
            "institution's rhythm, and E2-06 puts that derivation in one service so there is one "
            f"reading of it. Call `{SANCTIONED_FUNCTION}` instead. If a second path genuinely has "
            "to write these rows, that contradicts the ticket's fourth criterion and ADR 0111, "
            "and the record has to change before the code does.",
        ]
    )
