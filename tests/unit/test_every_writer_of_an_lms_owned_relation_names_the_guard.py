"""A module that writes an LMS-owned relation names the chokepoint — ticket E0-35.

[ADR 0045](../../docs/adr/0045-the-chokepoint-refuses-an-lms-owned-write-at-table-grain-plus-one-row.md)
gives `guard_write` a rule and then says what holds it up: "a caller can bypass it
by not calling it. `guard_write` is a function, not a grant, so it holds for the
write paths that go through the chokepoint and for no others." Eight tests in
`tests/unit/test_lms_owned_writes_are_refused_at_the_chokepoint.py` call the guard
directly, so they assert it answers correctly when asked. None of them can notice
a write path that never asks. That is `docs/MISTAKES.md` entry 2 — a rule stated
in a docstring with nothing that would notice when a new piece of code stops
holding it — and this module is the sweep E0-35 builds for it.

**The rule asserted here.** A module under `backend/app/` that writes `course`,
`section`, `enrollment`, `user`, or a `role_assignment` row whose role is
`INSTRUCTOR`, has to call `guard_write` somewhere in the same module.

**Where the guarded set comes from, and why it is not a list.** It is
`authz.LMS_OWNED_TABLES` unioned with the three tables SPEC §2.1 puts on the LMS's
side of the ownership sentence — courses, sections, enrollments. Both halves are
load-bearing. Reading the guard's own set means the sweep grows when the guard
does, which is how `user` is in scope here: ADR 0045 put it in the set because
`user.lms_user_id` is the `sub` claim verbatim, and E0-35's own criterion, written
by hand, names only three tables and is already one short. Reading the spec's
three as a floor means the sweep cannot be shrunk by an edit to the module it is
guarding — an inventory the guarded structure can shrink is not a control
(`docs/MISTAKES.md` entry 35). That `LMS_OWNED_TABLES` covers the spec's three is
asserted next door, in
`test_the_refusal_set_names_the_tables_the_spec_puts_on_the_lms_side`, and is not
restated here; that assertion is what makes the floor and the discovered set agree
rather than diverge quietly. A name in `LMS_OWNED_TABLES` that is not a real table
is diagnosed there too, and costs nothing here: the matchers simply never fire on
it.

**Read out of the syntax tree, not out of the file text**, for the reason
`tests/unit/test_no_service_reads_an_identity_table_directly.py` gives at length: a
correct module is very likely to *say* "this never inserts into `course`" in a
docstring, and a text search would turn that sentence into a failure and teach the
next person to delete the comment. Docstrings are subtracted by name below.

**The controls come first, and they have to find things.** Over today's tree this
sweep's subject set is empty — E0 ships no write path at all, which E0-35 records
as correct — so the sweep walks every module, finds no writer, and passes. A guard
whose only evidence is that it reported nothing on a tree containing nothing has
told you nothing (`docs/MISTAKES.md` entry 35). So each write shape is proven
detectable against a sample carried in this file, the near-miss beside it is proven
to be allowed, and the ORM half is required to resolve every guarded table to a
mapped class it can actually recognise. What this file asserts today is that the
detector can see a write; what it asserts from E1 is that every writer routes.

**What it cannot see, so that nothing here is cited as more than it is**
(ADR 0062 states the same three limits for the mock-idp gate, and they are the
same three):

  - **It is syntactic, not dataflow.** It sees the shape of a call, never where
    the value came from. A write reached through a helper in another module, an
    ORM cascade off a relationship, or a relation named by a variable is invisible
    to it.
  - **The grain is the module, not the path.** "Names the guard" means the module
    calls `guard_write` somewhere. A module that guards one function and writes in
    another passes here. Proving the guard runs before the write on the same path
    needs the session-level hook E0-35 weighed and rejected, and would cost a
    refused legitimate write in production as its failure mode rather than a red
    test.
  - **The subject is `backend/app/`, the application.** `scripts/seed.py` writes
    every one of these relations by design (E0-17, ADR 0063) and
    `backend/migrations/` writes whatever a migration writes; neither is an
    application write path and neither is swept.
  - **A `role_assignment` write whose role is a variable is not flagged.** ADR
    0045 permits every role on that table except `INSTRUCTOR`, so flagging the
    table outright would be wrong — it would fail §6.3's People editor, which is
    the control `test_a_role_assignment_the_lms_does_not_own_is_permitted` exists
    to hold. Under-flagging is the direction consistent with the guard, and it is
    a hole.

**One thing this rule does not answer, and E1 will have to.** ADR 0045 names the
launch path that creates a `user` row, and E1's roster sync that writes the other
three, as *sanctioned* writers. Nothing records how a sanctioned writer satisfies
"calls `guard_write`", given that `guard_write(table="course")` refuses. This sweep
asserts E0-35's criterion as written — the module names the guard — and a
sanctioned writer that cannot honestly do that is a question for the ADR rather
than a line to add to an exclusion list here. There is no exclusion list, on
purpose.
"""

import ast
import re
from pathlib import Path
from typing import Any, NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"

# SPEC §2.1's ownership sentence, as the tables it lands on. **Read out of the
# spec, not out of the module under test** (`docs/MISTAKES.md` entry 19): this is
# the floor the guarded set cannot fall below, so taking it from `LMS_OWNED_TABLES`
# would make it a copy of the thing it is holding up.
SPEC_LMS_OWNED_TABLES = ("course", "section", "enrollment")

# §2.1's fifth owned item. It is a row rather than a table — the teaching
# instructor is an `INSTRUCTOR` assignment, and every other role on that table is
# Pulse's to write — so it is carried separately from the tables throughout.
ROLE_ASSIGNMENT_TABLE = "role_assignment"
INSTRUCTOR_ROLE = "INSTRUCTOR"

# The chokepoint's name, which is what a module has to say to pass.
GUARD = "guard_write"

# Directories with no source of ours in them.
UNSWEPT_DIRECTORIES = frozenset({"__pycache__", ".mypy_cache", ".ruff_cache"})

# The calls that put rows in a table, as opposed to reading them. `execute` is
# deliberately absent: `session.execute(insert(Course))` carries its own `insert`
# call, and `session.execute(text("INSERT INTO course …"))` carries its own SQL, so
# sweeping `execute` would add nothing but a way to flag every read.
ORM_WRITE_CALLS = frozenset(
    {
        "add",
        "add_all",
        "merge",
        "delete",
        "insert",
        "update",
        "bulk_save_objects",
        "bulk_insert_mappings",
        "bulk_update_mappings",
    }
)

# `INSTRUCTOR` as a word, so `ASSISTANT_INSTRUCTOR` — a role nobody has proposed,
# and exactly the sort of thing that arrives later — is not read as this one.
INSTRUCTOR_MENTION = re.compile(rf"\b{INSTRUCTOR_ROLE}\b")


class WriteSite(NamedTuple):
    """One place a module puts rows into a relation the LMS owns."""

    path: Path
    line: int
    relation: str
    shape: str
    source: str


def relation_reference(relations: tuple[str, ...]) -> re.Pattern[str]:
    """A statement that writes one of `relations`, in SQL text.

    The keyword pair is what keeps prose out. `UPDATE` requires its `SET`, so a
    log line reading "update course catalog nightly" is not a write; `INSERT` and
    `DELETE` carry `INTO` and `FROM` and need no extra help. Optional quoting is
    for `"user"`, which a model has to quote because it is a reserved word.
    """
    names = "|".join(sorted(relations, key=len, reverse=True))
    qualified = r"(?:public\s*\.\s*)?\"?"
    return re.compile(
        rf"\b(?:insert\s+into|merge\s+into|delete\s+from)\s+{qualified}({names})\"?\b"
        rf"|\bupdate\s+{qualified}({names})\"?\s+set\b",
        re.IGNORECASE,
    )


def relations_written(statement: str, reference: re.Pattern[str]) -> list[str]:
    """Which relations a piece of SQL writes, if any."""
    found: set[str] = set()
    for match in reference.finditer(statement):
        written = match.group(1) or match.group(2)
        if written:
            found.add(written.lower())
    return sorted(found)


def called_name(node: ast.Call) -> str | None:
    """The name being called, whether it is a method or a bare function."""
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def spellings_in(node: ast.AST) -> set[str]:
    """Every name and attribute spelled anywhere under `node`."""
    found: set[str] = set()
    for inner in ast.walk(node):
        spelling = getattr(inner, "id", None) or getattr(inner, "attr", None)
        if isinstance(spelling, str):
            found.add(spelling)
    return found


def docstring_constants(tree: ast.AST) -> set[int]:
    """The identity of every string node that is a docstring rather than a value.

    Subtracted from the SQL sweep so that prose naming a relation stays legal. A
    module explaining why it never inserts into `course` is doing the right thing,
    and a test that punished the explanation would train the next reader to remove
    it. The same helper, for the same reason, is in
    `tests/unit/test_no_service_reads_an_identity_table_directly.py`.
    """
    found: set[int] = set()
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = list(getattr(node, "body", []))
        if not body or not isinstance(body[0], ast.Expr):
            continue
        first = body[0].value
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            found.add(id(first))
    return found


def enclosing_statement(node: ast.AST, parents: dict[int, ast.AST]) -> ast.AST:
    """The nearest statement `node` sits inside, or `node` itself.

    The unit for "does this write name the `INSTRUCTOR` role", because the role and
    the write are routinely in different calls of one statement:
    `insert(RoleAssignment).values(role="INSTRUCTOR")` puts the model in the inner
    call and the role in the outer one.
    """
    current: ast.AST | None = node
    while current is not None and not isinstance(current, ast.stmt):
        current = parents.get(id(current))
    return current if current is not None else node


def names_the_instructor_role(node: ast.AST) -> bool:
    """Whether `node` names the one role on `role_assignment` that the LMS owns.

    Either spelling counts — the string `"INSTRUCTOR"` and the enum member
    `AssignmentRole.INSTRUCTOR` are the same fact written two ways, and a sweep
    that saw only one of them would miss whichever the implementer used
    (`docs/MISTAKES.md` entry 35).
    """
    for inner in ast.walk(node):
        if (
            isinstance(inner, ast.Constant)
            and isinstance(inner.value, str)
            and INSTRUCTOR_MENTION.search(inner.value.upper())
        ):
            return True
        spelling = getattr(inner, "id", None) or getattr(inner, "attr", None)
        if spelling == INSTRUCTOR_ROLE:
            return True
    return False


def write_sites(
    source: str,
    path: Path,
    tables: tuple[str, ...],
    models: dict[str, tuple[str, ...]],
) -> list[WriteSite]:
    """Every place `source` writes a guarded relation, by either route.

    `tables` are the LMS-owned tables; `role_assignment` is added here rather than
    passed in, because its rule is different from theirs and a caller that had to
    remember to include it could quietly drop it.
    """
    tree = ast.parse(source)
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    excluded = docstring_constants(tree)
    reference = relation_reference((*tables, ROLE_ASSIGNMENT_TABLE))
    found: list[WriteSite] = []

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in excluded:
            continue
        statement = enclosing_statement(node, parents)
        for relation in relations_written(node.value, reference):
            if relation == ROLE_ASSIGNMENT_TABLE and not names_the_instructor_role(statement):
                continue
            found.append(
                WriteSite(
                    path=path,
                    line=node.lineno,
                    relation=relation,
                    shape="a statement written as SQL",
                    source=" ".join(node.value.split()),
                )
            )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or called_name(node) not in ORM_WRITE_CALLS:
            continue
        spelled = spellings_in(node)
        statement = enclosing_statement(node, parents)
        for relation, classes in models.items():
            if not spelled.intersection(classes):
                continue
            if relation == ROLE_ASSIGNMENT_TABLE and not names_the_instructor_role(statement):
                continue
            found.append(
                WriteSite(
                    path=path,
                    line=node.lineno,
                    relation=relation,
                    shape="a mapped write",
                    source=ast.get_source_segment(source, node) or "",
                )
            )
    return found


def names_the_guard(source: str) -> bool:
    """Whether the module calls `guard_write` anywhere.

    A call, not a mention: the criterion is "without calling `guard_write`", and a
    module that only imported the name, or named it in a comment, would be routing
    nothing.
    """
    tree = ast.parse(source)
    return any(isinstance(node, ast.Call) and called_name(node) == GUARD for node in ast.walk(tree))


def swept_modules(root: Path) -> list[Path]:
    """Every Python source file under `root`, in a stable order."""
    return sorted(
        path
        for path in root.rglob("*.py")
        if not any(part in UNSWEPT_DIRECTORIES for part in path.parts)
    )


def mapped_classes_by_table(import_app_module: Any) -> dict[str, tuple[str, ...]]:
    """Every mapped class on `Base`, keyed by the table it maps.

    Discovered rather than listed, so the ORM half of the sweep learns a model's
    spelling from the registry instead of from a constant in a test file that
    nobody edits when a class is renamed. Reached through `app.models` and not
    through one model module, because `migrations/env.py` imports the package and a
    module nobody imported is on no registry.
    """
    package = import_app_module("app.models")
    if package is None:
        pytest.fail(
            "There is no `app.models` package, so no mapped class can be discovered and the ORM "
            "half of this sweep would recognise nothing. "
            "`tests/unit/test_org_models_registered.py` is where that absence is diagnosed."
        )
    base_module = import_app_module("app.models.base")
    registry = getattr(getattr(base_module, "Base", None), "registry", None)
    if registry is None:
        pytest.fail(
            "`app.models.base` is missing, or exposes no `Base` with a `registry`, so there is "
            "nothing to discover mapped classes from. E0-04 ships the declarative base there."
        )

    found: dict[str, set[str]] = {}
    for mapper in registry.mappers:
        for table in mapper.tables:
            found.setdefault(table.name, set()).add(mapper.class_.__name__)
    return {name: tuple(sorted(classes)) for name, classes in found.items()}


def guarded_tables(authz: Any) -> tuple[str, ...]:
    """The LMS-owned tables, from the guard's own set and from the spec's floor.

    The union is the point. The guard's set is what makes this grow when ADR 0045's
    grain grows — `user` is here because of it — and the spec's three are what stop
    it shrinking, since an inventory the guarded module can edit downwards would
    let a sweep cover less while staying green.
    """
    return tuple(sorted(set(SPEC_LMS_OWNED_TABLES) | set(authz.LMS_OWNED_TABLES)))


def guarded_models(
    discovered: dict[str, tuple[str, ...]], tables: tuple[str, ...]
) -> dict[str, tuple[str, ...]]:
    """The mapped classes for the guarded relations, and nothing else."""
    return {name: discovered.get(name, ()) for name in (*tables, ROLE_ASSIGNMENT_TABLE)}


# The inventory the control samples are read against. Synthetic on purpose: a
# control that took the real inventory would pass whenever the real discovery
# happened to be right, and the two failures — a detector that cannot see a write,
# and a discovery that found no models — need different fixes.
CONTROL_TABLES = ("course", "section", "enrollment", "user")
CONTROL_MODELS = {
    "course": ("Course",),
    "section": ("Section",),
    "enrollment": ("Enrollment",),
    "user": ("User",),
    "role_assignment": ("RoleAssignment",),
}
CONTROL_MODULE = Path("roster_sync.py")

# One of each write shape that has to be caught. `docs/MISTAKES.md` entry 35: a
# guard that enumerates mechanisms has to be made to *find* each one on a subject
# that certainly has it, because a guard that only ever reports absence cannot tell
# you which mechanisms it can see — and today, over `backend/app/`, absence is all
# it reports. Nothing here is executed; these are subjects for a parser.
WRITES_MUST_CATCH = {
    "an ORM add of a course": 'session.add(Course(lms_number="BIOL 215"))\n',
    "a mapped insert of a section": (
        'session.execute(insert(Section).values(lms_section_code="R3WW"))\n'
    ),
    "an ORM merge of a user": "session.merge(User(lms_user_id=sub))\n",
    "a bulk save of enrollments": "session.bulk_save_objects([Enrollment(section_id=key)])\n",
    "a textual insert": 'session.execute(text("INSERT INTO course (lms_number) VALUES (:n)"))\n',
    "a textual update": 'session.execute(text("UPDATE section SET lms_section_code = :code"))\n',
    "a textual delete": 'session.execute(text("DELETE FROM enrollment WHERE id = :id"))\n',
    "a quoted textual write to the reserved table name": (
        "session.execute(text('INSERT INTO \"user\" (lms_user_id) VALUES (:sub)'))\n"
    ),
    "an instructor assignment written through the ORM": (
        "session.add(RoleAssignment(role=AssignmentRole.INSTRUCTOR, section_id=key))\n"
    ),
    "an instructor assignment whose role is set in a later call": (
        'session.execute(insert(RoleAssignment).values(role="INSTRUCTOR"))\n'
    ),
}

# The near misses. Every one of them is a line a correct module is entitled to
# write, and each differs from something above by one property: the role on the
# assignment, the table's owner, the direction of the statement. A sweep that
# fires on any of these is worse than no sweep — it is red against correct code,
# and the fix somebody reaches for is to delete the sweep.
WRITES_MUST_ALLOW = {
    "a leadership assignment, which is Pulse's to write": (
        "session.add(RoleAssignment(role=AssignmentRole.LEAD_FACULTY, course_id=key))\n"
    ),
    "a chair assignment written through Core": (
        'session.execute(insert(RoleAssignment).values(role="CHAIR"))\n'
    ),
    "a write to a table SPEC §2.1 puts on Pulse's side": "session.add(Person(name=name))\n",
    "a mapped read of a course": "rows = session.execute(select(Course)).all()\n",
    "a textual read of a course": 'session.execute(text("SELECT * FROM course WHERE id = :id"))\n',
    "a model declaring which table it maps": 'class Course(Base):\n    __tablename__ = "course"\n',
    "the guard's own inventory": 'LMS_OWNED_TABLES = ("course", "section", "user")\n',
    "prose in a log line": 'logger.info("update course catalog nightly")\n',
    "prose in a docstring": '"""Nothing here runs INSERT INTO course; the guard refuses it."""\n',
}

# Two whole modules, differing only in whether the write is routed. This is the
# near-miss the rule stands or falls on: a module that writes `course` and *does*
# call the guard has to pass, or the sweep is a rule against writing rather than a
# rule about routing.
GUARDED_MODULE = (
    "def create_course(session, payload):\n"
    '    guard_write(table="course")\n'
    "    session.add(Course(lms_number=payload.number))\n"
)
UNGUARDED_MODULE = (
    "def create_course(session, payload):\n" "    session.add(Course(lms_number=payload.number))\n"
)


def test_the_write_sweep_finds_every_shape_it_claims_to_and_allows_their_near_misses() -> None:
    """The control, run before this file's silence over `backend/app/` counts as evidence.

    E0-35 records that nothing calls `guard_write` today and that this is correct:
    E0 ships no write path. So the sweep below walks the application, finds no
    writer, iterates over nothing and passes — and would pass just as quietly on
    the day E1's roster sync lands unrouted, if the shape it uses is one this file
    cannot see. `docs/MISTAKES.md` entry 35's rule is the one that applies: require
    the guard to find each mechanism on a subject that certainly has it.

    The allow half costs as much as the catch half. `RoleAssignment(role=…)` with
    a leadership role is one token away from the instructor case and has to pass,
    because ADR 0045 permits every role on that table but one and §6.3's People
    editor writes them all.
    """
    for case, sample in sorted(WRITES_MUST_CATCH.items()):
        found = write_sites(sample, CONTROL_MODULE, CONTROL_TABLES, CONTROL_MODELS)
        assert found, (
            f"The sweep found no write in {case} ({sample!r}), which writes a relation the LMS "
            "owns. A detector that has gone blind reads exactly like an application with no "
            "write path in it, and today those two look the same from here."
        )

    for case, sample in sorted(WRITES_MUST_ALLOW.items()):
        found = write_sites(sample, CONTROL_MODULE, CONTROL_TABLES, CONTROL_MODELS)
        assert not found, (
            f"The sweep read {[site.relation for site in found]} out of {case} ({sample!r}), "
            "which writes no LMS-owned relation. Every assertion in this module rests on the "
            "detector saying no to something a correct module is entitled to write."
        )


def test_the_verdict_passes_a_routed_write_and_fails_an_unrouted_one() -> None:
    """The verdict, both ways, on two modules that differ by one line.

    The rule is about routing and not about writing. If the guarded module failed
    here, the sweep would be a prohibition on writing `course` at all, which no
    ticket asks for and which E1 cannot satisfy; if the unguarded one passed, the
    sweep would be nothing.
    """
    guarded = write_sites(GUARDED_MODULE, CONTROL_MODULE, CONTROL_TABLES, CONTROL_MODELS)
    assert guarded, (
        "The sweep found no write in the guarded control module, so it is not the subject this "
        "test needs — it would be passing for having nothing to judge rather than for being "
        "routed."
    )
    assert names_the_guard(GUARDED_MODULE), (
        f"The guarded control module writes `course` and calls `{GUARD}`, and this file did not "
        f"see the call. A module that routes correctly would be reported as an offender, which "
        "is the failure mode that gets a sweep deleted."
    )

    unguarded = write_sites(UNGUARDED_MODULE, CONTROL_MODULE, CONTROL_TABLES, CONTROL_MODELS)
    assert unguarded, "The sweep found no write in the unguarded control module."
    assert not names_the_guard(UNGUARDED_MODULE), (
        f"This file read a call to `{GUARD}` in a module that makes none, so every module would "
        "pass the sweep below whatever it writes."
    )


def test_every_guarded_relation_resolves_to_a_mapped_class_the_sweep_can_recognise(
    authz: Any, import_app_module: Any
) -> None:
    """The ORM half is required to know what a `course` is called in Python.

    The SQL half reads table names, which are the names the spec and ADR 0045 use.
    The ORM half needs class names, which appear in neither, so it takes them from
    the mapper registry. A table that resolves to no class is a relation the ORM
    half cannot see at all — `session.add(Course(...))` would pass — and the
    failure is silent, because a sweep with one blind half still reports success
    over a tree that has no writers in it.

    This is `docs/MISTAKES.md` entry 35 applied to the inventory rather than to the
    shapes: the control is that the discovery *finds* something on subjects that
    certainly have it, since E0-05, E0-08 and E0-11 have already shipped models for
    every relation named here.
    """
    tables = guarded_tables(authz)
    assert set(SPEC_LMS_OWNED_TABLES).issubset(tables), (
        f"The guarded set is {tables} and does not cover SPEC §2.1's three tables "
        f"{SPEC_LMS_OWNED_TABLES}. The union in `guarded_tables` exists so this cannot happen; "
        "if it has, the floor in this file has been edited rather than the guard."
    )

    discovered = mapped_classes_by_table(import_app_module)
    assert discovered, (
        "No mapped class was discovered on `Base.registry` at all, so the ORM half of this sweep "
        "recognises nothing and its silence means nothing."
    )

    models = guarded_models(discovered, tables)
    unrecognised = sorted(name for name, classes in models.items() if not classes)
    assert not unrecognised, (
        f"{unrecognised} have no mapped class on `Base.registry` (it maps "
        f"{sorted(discovered)}). The ORM half of this sweep looks for a model's *class* name, so "
        "a relation with no class is one it cannot see: a write to it through the ORM would pass "
        "unnoticed while the SQL half went on reporting success. Either the model is missing — "
        "`tests/unit/test_org_models_registered.py` and its siblings diagnose that — or a table "
        "in the guarded set is spelled in a way nothing maps, which "
        "`test_the_refusal_set_names_the_tables_the_spec_puts_on_the_lms_side` names."
    )


def test_no_module_under_the_application_writes_a_guarded_relation_without_naming_the_guard(
    authz: Any, import_app_module: Any
) -> None:
    """E0-35's criterion, over every module the application has.

    ADR 0045: "a caller can bypass it by not calling it… E0 ships no HTTP write
    path at all, so today the set of callers is empty and the guard is scaffolding
    with tests on it. E1 is the first ticket that has to route a real write through
    it." E1's roster sync writes `course`, `section`, `enrollment` and the
    `INSTRUCTOR` `role_assignment` row — every relation the guard names, all four
    in one module — so this is the assertion that is empty today and load-bearing
    on the day that module lands.

    The module count assertion first is not ceremony, and it is not the whole
    guard either: this test asserts a set is empty, and an empty set is what a
    sweep pointed at a renamed directory produces as readily as one pointed at
    correct code. The controls above are what make the emptiness mean something,
    because today the tree genuinely holds no writer.
    """
    modules = swept_modules(APP_ROOT)
    assert modules, (
        f"There are no Python modules under {APP_ROOT.relative_to(REPO_ROOT)}, so this sweep read "
        "nothing and would report success. SPEC §13 puts the application there."
    )

    tables = guarded_tables(authz)
    models = guarded_models(mapped_classes_by_table(import_app_module), tables)

    offenders: dict[str, list[str]] = {}
    for path in modules:
        source = path.read_text(encoding="utf-8")
        try:
            sites = write_sites(source, path, tables, models)
            routed = names_the_guard(source)
        except SyntaxError as failure:  # pragma: no cover - a broken source tree
            pytest.fail(
                f"{path.relative_to(REPO_ROOT)} does not parse ({failure}), so this sweep cannot "
                "read it and would report success having skipped it."
            )
        if sites and not routed:
            offenders[str(path.relative_to(REPO_ROOT))] = [
                f"line {site.line}: {site.relation} — {site.shape}: {site.source}" for site in sites
            ]

    reported = [
        line
        for path, sites in sorted(offenders.items())
        for line in [f"  {path}", *(f"    {site}" for site in sites)]
    ]

    assert not offenders, "\n".join(
        [
            f"These modules write a relation the LMS owns and never call `{GUARD}`:",
            *reported,
            "",
            "SPEC §2.1 makes courses, sections, section codes, enrollments and teaching "
            "instructors LMS-owned and read-only in Pulse; §8 restates it as a constraint, 'LMS-"
            "owned data is never hand-edited in Pulse.' ADR 0045 puts the refusal in "
            f"`{GUARD}` and records the hole this sweep closes: 'a caller can bypass it by not "
            "calling it.'",
            "",
            "The failure it prevents is quiet. An edit to LMS-owned data is not rejected by the "
            "LMS and does not error; it is overwritten at the next hourly sync, so the symptom is "
            "a value that changes back by itself, which reads as a sync bug rather than as a "
            "write path that should not exist.",
            "",
            f"Route the write through `{GUARD}`. If this module is a *sanctioned* writer — ADR "
            "0045 names the launch path that creates a `user` row, and E1's roster sync for the "
            "other three — then note that no record yet says how a sanctioned writer satisfies "
            f"this rule, since `{GUARD}(table='course')` refuses. That is a question for the ADR "
            "and a deliberate change to this rule, not an exclusion added here; there is no "
            "exclusion list in this file on purpose.",
        ]
    )
