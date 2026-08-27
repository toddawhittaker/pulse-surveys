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
`authz.LMS_OWNED_TABLES` unioned with a floor of four tables, and both halves are
load-bearing. Reading the guard's own set means the sweep grows when the guard
does — E0-35's own criterion, written by hand, names three tables and is already
one short. Reading the floor means the sweep cannot narrow below those four when
the guard does, because an inventory the guarded structure can shrink is not a
control (`docs/MISTAKES.md` entry 35). Below those four, and no further: a table
the guard holds above the floor can leave it again with nothing here noticing,
which the floor test below states as its own limit.

**The floor's four entries do not all come from the same record, and the
difference matters.** Three are SPEC §2.1's ownership sentence — courses,
sections, enrollments. The fourth, `user`, is **ADR 0045's and not the spec's**:
§2.1's list is courses, sections, section codes, enrollments and teaching
instructors, and it names no user record; ADR 0045 puts `user` in the guarded set
because `user.lms_user_id` is the `sub` claim verbatim and SPEC §4 keys every
response to it.

**The union alone would only make a narrowing quiet, so a narrowing below the
floor is asserted directly.** Measured in E0-35's review: deleting `"user"` from
`LMS_OWNED_TABLES` left the union answering three tables, both sweeps covering
less, and the only red came from
`test_every_column_marked_lms_owned_sits_on_a_table_the_chokepoint_refuses`, which
noticed only because `user` happens to carry an `lms_`-prefixed column — a guarded
table without one would have had no backstop at all.
`test_the_guard_names_every_table_in_the_floor_this_sweep_may_not_fall_below`
below is the direct assertion, and it is this module's, not next door's: the
chokepoint suite's `test_the_refusal_set_names_the_tables_the_spec_puts_on_the_lms_side`
covers the spec's three and cannot cover `user`, which the spec does not name. A
name in `LMS_OWNED_TABLES` that is not a real table is diagnosed there, and costs
nothing here: the matchers simply never fire on it.

**Read out of the syntax tree, not out of the file text**, for the reason
`tests/unit/test_no_service_reads_an_identity_table_directly.py` gives at length: a
correct module is very likely to *say* "this never inserts into `course`" in a
docstring, and a text search would turn that sentence into a failure and teach the
next person to delete the comment. Docstrings are subtracted by name below.

**The controls come first, and they have to find things.** From E0-35 until E1-10
this sweep's subject set was empty — E0 shipped no write path at all, which E0-35
records as correct — so the sweep walked every module, found no writer, and
passed. A guard whose only evidence is that it reported nothing on a tree
containing nothing has told you nothing (`docs/MISTAKES.md` entry 35). So each
write shape is proven detectable against a sample carried in this file, the
near-miss beside it is proven to be allowed, and the ORM half is required to
resolve every guarded table to a mapped class it can actually recognise. Those
controls are what the file asserts about the *detector*; from E1-10 it also
asserts something about the codebase, because `app.services.provisioning` is a
real writer of three of these relations and the live assertion below finally has a
subject.

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

**How a *sanctioned* writer satisfies this rule, answered by E1-10.** ADR 0045
names the launch path that creates a `user` row, and E1's roster sync that writes
the other three, as *sanctioned* writers, and until 2026-08-26 nothing recorded
what that meant operationally: `guard_write(table="course")` refused
unconditionally, so a sanctioned writer could not honestly call it and this rule
was satisfiable only because nothing under `backend/app/` called the guard at all.
E1-10 arrives with the first real writer and settles it, and the answer changes
nothing about what this file asserts:

  **A sanctioned writer still calls `guard_write`.** It calls it with a
  `sanction` the catalog grants — `authz.SANCTIONED_WRITERS` maps a writer's name
  to the tables it may write, `sanction_for` resolves one, and `guard_write`
  consults the catalog rather than the sanction it was handed. So "the module
  names the guard" is exactly as true of the launch writer as of anything else,
  the rule below is unchanged, and **there is still no exclusion list, on
  purpose.** What a sanction is and what it refuses is asserted in
  `tests/unit/test_a_sanctioned_writer_satisfies_the_chokepoint.py`, including
  that a write with no sanction is refused exactly as it is today.

That is also what makes this file's live assertion stop being vacuous. It swept a
tree with no writer in it from E0-35 until E1-10, so its silence was the silence
of an empty subject set;
`test_the_launch_writer_is_a_routed_write_site_this_sweep_can_actually_see` below
is the assertion that the subject set is no longer empty, and it is the one that
turns every other sentence here into a claim about this codebase rather than about
a parser.

**E1-11 adds the second subject, and it is the one ADR 0045 was written about.**
`app.services.roster_sync` writes `enrollment` and the `INSTRUCTOR`
`role_assignment` row — the two relations of the four that no code in this project
had ever written — under a catalog entry of its own, and
`test_the_roster_sync_is_a_routed_write_site_and_its_unguarded_twin_is_not` below
is its criterion 5. The rule, the sweep and the absence of an exclusion list are
all unchanged; what changes is that both of ADR 0045's named sanctioned writers
now exist, so this file's silence is finally about a tree with writers in it.
"""

import ast
import re
from pathlib import Path
from typing import Any, NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"

# The floor the guarded set may not fall below. **Read out of the records, not out
# of the module under test** (`docs/MISTAKES.md` entry 19): taking it from
# `LMS_OWNED_TABLES` would make it a copy of the thing it is holding up. Three
# entries are SPEC §2.1's ownership sentence; `user` is ADR 0045's, on the ground
# that `user.lms_user_id` is the `sub` claim verbatim and SPEC §4 keys every
# response to it. See the module docstring for why the two authorities are kept
# apart rather than blurred into "the spec's tables".
GUARDED_TABLE_FLOOR = ("course", "section", "enrollment", "user")

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


def unrouted_write_sites(
    source: str,
    path: Path,
    tables: tuple[str, ...],
    models: dict[str, tuple[str, ...]],
) -> list[WriteSite]:
    """The guarded writes in `source` that nothing in the same module routes.

    The verdict, as one function, so that the planted-offender control below and
    the live sweep at the foot of this file reach it by the same route. When the
    two were spelled separately — a control that reasoned about the parts and a
    sweep that combined them — a detector could pass the control and answer
    differently over the application, which is `docs/MISTAKES.md` entry 9's shape:
    a guard cited for a case it was never run against.
    """
    sites = write_sites(source, path, tables, models)
    return [] if names_the_guard(source) else sites


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
    """The LMS-owned tables, from the guard's own set and from the floor.

    The union is what makes this grow when ADR 0045's grain grows, and what keeps
    the *sweep* covering the floor when the guard stops. It does not stop the
    *guard* narrowing, and reading it as though it did is the error E0-35's review
    found: the union is silent about a table deleted from `LMS_OWNED_TABLES`, which
    is what
    `test_the_guard_names_every_table_in_the_floor_this_sweep_may_not_fall_below`
    is for — for the four the floor names, and, as that test says of itself, for no
    table the guard holds above them.
    """
    return tuple(sorted(set(GUARDED_TABLE_FLOOR) | set(authz.LMS_OWNED_TABLES)))


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

# E1-10's shape: the same write, guarded with the sanction the catalog grants. It
# is a third sample rather than an edit to `GUARDED_MODULE`, because the two say
# different things and both have to hold — the second-argument call is what a
# real writer under ADR 0090 looks like, and a `names_the_guard` written as a
# match on the exact source text `guard_write(table=` would pass the sample above
# and fail this one while every module in the application routed correctly.
SANCTIONED_MODULE = (
    "def provision_course(session, claims):\n"
    '    guard_write(table="course", sanction=sanction_for("launch_provisioning"))\n'
    "    session.add(Course(lms_number=claims.number))\n"
)

# The planted offender E1-10's criterion 3 requires this sweep to be *run* against
# rather than reasoned about (`docs/MISTAKES.md` entry 9). It is a module that
# writes two guarded relations through the ORM and names no guard at all — the
# shape a second, unsanctioned writer takes when somebody adds one beside the
# launch writer — and it is judged by `verdict_on` below, the same function the
# live sweep uses, so a detector that stopped seeing this would stop seeing the
# real thing too.
PLANTED_UNSANCTIONED_WRITER = (
    "def store_the_roster(session, roster):\n"
    "    session.add(Section(lms_section_code=roster.code))\n"
    '    session.execute(text("INSERT INTO enrollment (section_id) VALUES (:id)"))\n'
)


def test_the_write_sweep_finds_every_shape_it_claims_to_and_allows_their_near_misses() -> None:
    """The control, run before this file's silence over `backend/app/` counts as evidence.

    E0-35 recorded that nothing called `guard_write` and that this was correct: E0
    shipped no write path. So the sweep below walked the application, found no
    writer, iterated over nothing and passed — and would have passed just as
    quietly on the day a real writer landed unrouted, if the shape it used were one
    this file cannot see. `docs/MISTAKES.md` entry 35's rule is the one that
    applies: require the guard to find each mechanism on a subject that certainly
    has it.

    E1-10's `app.services.provisioning` is the first such subject in the tree, and
    it does not retire this control: it exercises three of these ten shapes at
    most, and the point of the sample set is the seven it does not.

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


def test_the_verdict_flags_a_planted_unsanctioned_writer_and_clears_a_sanctioned_one() -> None:
    """E1-10 criterion 3, both directions, **run** rather than reasoned about.

    "The E0-35 sweep still fails a planted unsanctioned writer, and the new
    sanctioned path passes it — both directions run, per MISTAKES entry 9." The
    two subjects are one line apart in what they mean and are nothing alike in
    what they contain: one writes `section` and `enrollment` and names no guard,
    the other writes `course` and names the guard with the sanction ADR 0090's
    catalog grants.

    **Why the sanctioned sample is not the same as `GUARDED_MODULE` above.** That
    one calls `guard_write(table="course")` with no second argument, which is the
    only shape that existed before this ticket. If `names_the_guard` were ever
    narrowed from "a call to `guard_write`" to a match on that exact text — the
    obvious way to make it stricter — the old sample would pass, this one would
    fail, and every correctly sanctioned writer in the application would be
    reported as an offender. The failure mode of a sweep that is red against
    correct code is that somebody deletes the sweep.

    The planted sample's non-emptiness is asserted before its verdict is, because
    "no unrouted write" is what this function answers for a module it cannot read
    at all.
    """
    planted = write_sites(
        PLANTED_UNSANCTIONED_WRITER, CONTROL_MODULE, CONTROL_TABLES, CONTROL_MODELS
    )
    assert {site.relation for site in planted} == {"section", "enrollment"}, (
        f"The sweep read {sorted({site.relation for site in planted})} out of the planted "
        "unsanctioned writer, which writes `section` through the ORM and `enrollment` as SQL. A "
        "control that cannot see the planted offender says nothing about the live sweep below, "
        "which is the only thing standing between a second writer and LMS-owned data."
    )
    assert unrouted_write_sites(
        PLANTED_UNSANCTIONED_WRITER, CONTROL_MODULE, CONTROL_TABLES, CONTROL_MODELS
    ), (
        "The planted unsanctioned writer was cleared by this file's own verdict. It writes two "
        "relations SPEC §2.1 makes LMS-owned and calls `guard_write` nowhere, so if this passes "
        "then the sweep at the foot of this module would pass a module exactly like it."
    )

    sanctioned = write_sites(SANCTIONED_MODULE, CONTROL_MODULE, CONTROL_TABLES, CONTROL_MODELS)
    assert sanctioned, (
        "The sweep found no write in the sanctioned control module, so it is not the subject this "
        "test needs — it would be cleared for having nothing to judge rather than for routing."
    )
    assert not unrouted_write_sites(
        SANCTIONED_MODULE, CONTROL_MODULE, CONTROL_TABLES, CONTROL_MODELS
    ), (
        f"The sanctioned control module writes `course` and calls `{GUARD}` with the sanction "
        "ADR 0090's catalog grants, and this file reported it as an offender. That is the sweep "
        "going red against the one shape E1-10 makes correct."
    )


def test_the_guard_names_every_table_in_the_floor_this_sweep_may_not_fall_below(
    authz: Any,
) -> None:
    """A table *named in the floor* cannot leave `LMS_OWNED_TABLES` without failing here.

    `guarded_tables` unions the guard's set with the floor, so a deleted table is
    still swept — and that is the whole trouble. The union makes the sweep's
    coverage survive the deletion and says nothing about the *guard*, which has
    just stopped refusing writes to a relation the LMS owns. Two different
    statements: the union keeps this file honest, and this assertion is the one
    that keeps the guard honest.

    **Measured in E0-35's review**, deleting `"user"` from `LMS_OWNED_TABLES`:
    `guarded_tables` answered `('course', 'enrollment', 'section')`, both sweeps
    quietly covered less, and the only red anywhere was
    `test_every_column_marked_lms_owned_sits_on_a_table_the_chokepoint_refuses` —
    which noticed by accident, because `user` carries `lms_user_id`. A guarded
    table with no `lms_`-prefixed column on it would have had no backstop at all.

    **What this does not cover, and it is the finding above one table over.** The
    assertion is a floor and not an equality. It refuses a shrink below the four
    tables `GUARDED_TABLE_FLOOR` names, and it says nothing whatever about a table
    the guard holds above them. The concrete path: E1 adds `user_identity` to
    `LMS_OWNED_TABLES` — ADR 0045 records that exclusion as deliberate and as
    E1's to revisit — and nothing requires the floor to grow with it, so a later
    edit takes it out again, `missing` is empty, this test is green, and both
    sweeps narrow in silence. What closes it is a habit rather than an assertion:
    a table added to the guard for a reason worth keeping is added to this floor
    in the same pull request, citing the record that put it there. ADR 0069
    carries the gap and its "done when".

    **Growth passes, and that is decided rather than incidental.** A table added
    to `LMS_OWNED_TABLES` is picked up by both sweeps through the same union,
    which is how `user` arrived here at all, and ADR 0069 chose that automatic
    growth on purpose. Making this an equality would close the gap above and
    reverse that choice in the same movement, so it is a deliberate change with
    its own record and not a line to tighten here.
    """
    named = frozenset(authz.LMS_OWNED_TABLES)
    missing = sorted(set(GUARDED_TABLE_FLOOR) - named)

    assert not missing, (
        f"`LMS_OWNED_TABLES` is {sorted(named)} and no longer names {missing}. Three of this "
        "floor's four entries are SPEC §2.1's ownership sentence — 'courses, sections, section "
        "codes, enrollments, teaching instructors' — and §8 restates it as a constraint: "
        "'LMS-owned data is never hand-edited in Pulse.' The fourth, `user`, is ADR 0045's: "
        "`user.lms_user_id` is the `sub` claim verbatim and SPEC §4 keys every response to it.\n"
        "\n"
        "A name removed from that set is a write the chokepoint has stopped refusing. The sweeps "
        "in this module and in "
        "`tests/unit/test_no_lms_owned_table_carries_an_unmarked_column.py` go on covering the "
        "table because they union this floor in, so nothing else here would have gone red.\n"
        "\n"
        "If the guard's grain genuinely changed, that is a change to ADR 0045 and this floor moves "
        "with it, in the same pull request. Editing the floor to match a narrowed guard is the "
        "one thing that turns this assertion back into the thing it replaced."
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
    it." E1-10 is that ticket: `app.services.provisioning` writes `course`,
    `section` and `user` at launch time, so this assertion has a subject for the
    first time and the test below it is what says so.

    The module count assertion first is not ceremony, and it is not the whole
    guard either: this test asserts a set is empty, and an empty set is what a
    sweep pointed at a renamed directory produces as readily as one pointed at
    correct code. The controls above are what make the emptiness mean something,
    and `test_the_launch_writer_is_a_routed_write_site_this_sweep_can_actually_see`
    is what stops the emptiness being the emptiness of a tree with no writer in
    it.
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
            sites = unrouted_write_sites(source, path, tables, models)
        except SyntaxError as failure:  # pragma: no cover - a broken source tree
            pytest.fail(
                f"{path.relative_to(REPO_ROOT)} does not parse ({failure}), so this sweep cannot "
                "read it and would report success having skipped it."
            )
        if sites:
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
            "other three — then it calls the guard like everything else and passes a `sanction` "
            "the catalog grants: `sanction_for(<writer>)` resolves one out of "
            "`authz.SANCTIONED_WRITERS`, and E1-10's ADR 0090 records the mechanism. A writer "
            "the catalog does not name is a grant nobody has made, and the honest answers are to "
            "add it there — in a pull request that says why, since "
            "`tests/unit/test_a_sanctioned_writer_satisfies_the_chokepoint.py` pins that catalog "
            "as an equality — or not to write the relation. There is no exclusion list in this "
            "file on purpose.",
        ]
    )


def test_the_launch_writer_is_a_routed_write_site_this_sweep_can_actually_see(
    authz: Any, import_app_module: Any
) -> None:
    """The sweep above stops being vacuous here, and only here.

    From E0-35 until E1-10 the sweep walked `backend/app/`, found no writer of any
    guarded relation, iterated over nothing and reported success — which is
    exactly what it would report on the day a real writer landed in a shape the
    detector cannot see. E0-35 recorded that as its own limit and `docs/MISTAKES.md`
    entry 35 is the rule: require the guard to *find* the thing on a subject that
    certainly has it.

    `app.services.provisioning` is that subject. E1-10 has it write `course`,
    `section` and `user` — three of the four tables in the floor — through the ORM,
    with `guard_write` called before each write in the same module.

    **Two assertions, and they are opposite.** The writes must be *visible* to
    this file's detector, or the sweep's silence about the application is the
    silence of a parser that reads nothing. And the module must be *cleared*, or
    the mechanism E1-10 designed does not satisfy the rule E0-35 wrote and one of
    the two is wrong.

    **The mutation this exists to survive**: `provisioning.py` writing its rows
    through a helper in another module, which is the first limit E0-35's docstring
    names — the sweep is syntactic and its grain is the module, so a write reached
    through a helper elsewhere is invisible to it. That mutation leaves the sweep
    above green and turns this red, which is the whole reason this test names a
    module rather than counting offenders.
    """
    path = APP_ROOT / "services" / "provisioning.py"
    assert path.is_file(), (
        f"There is no {path.relative_to(REPO_ROOT)}. E1-10 puts launch-time provisioning there — "
        "the first code in this project that writes an LMS-owned relation at all — and until it "
        "exists the sweep above walks a tree with no writer in it and its success means nothing "
        "(`docs/MISTAKES.md` entry 35)."
    )

    tables = guarded_tables(authz)
    models = guarded_models(mapped_classes_by_table(import_app_module), tables)
    source = path.read_text(encoding="utf-8")

    seen = {site.relation for site in write_sites(source, path, tables, models)}
    assert seen, (
        f"This file's detector reads no guarded write out of {path.relative_to(REPO_ROOT)}, which "
        "E1-10 makes the writer of `course`, `section` and `user`. Either the writes are reached "
        "through a helper in another module — the syntactic sweep's first stated limit, and a "
        "hole this rule then has no way to close — or the detector has gone blind, in which case "
        "the sweep above is passing for having read nothing."
    )

    assert not unrouted_write_sites(source, path, tables, models), (
        f"{path.relative_to(REPO_ROOT)} writes {sorted(seen)} and calls `{GUARD}` nowhere in the "
        "module. E1-10's whole mechanism is that a sanctioned writer satisfies this rule rather "
        "than being excused from it: it calls the guard and passes a sanction the catalog grants."
    )


def test_the_roster_sync_is_a_routed_write_site_and_its_unguarded_twin_is_not(
    authz: Any, import_app_module: Any
) -> None:
    """E1-11 criterion 5, both directions, **run** against the real module.

    "The E0-35 sweep passes with the sync as a sanctioned writer; a planted
    unsanctioned write in the sync module still fails it."

    `app.services.roster_sync` is the second real subject this sweep has ever had,
    and it is the more interesting one: E1-10's writer touches `course`, `section`
    and `user`, and this one touches `enrollment` and the `INSTRUCTOR`
    `role_assignment` row — the two relations of ADR 0045's four that nothing in
    this project had written before, and the two whose write paths that record
    named as "E1's roster sync" when it could not yet say what a sanctioned writer
    was.

    **The planted offender is this module with its guard calls taken out**, which
    is the strongest form the sweep's own grain permits and is worth saying plainly.
    "Names the guard" means the module calls `guard_write` *somewhere*, so a write
    planted into a module that also routes one is cleared by design — that limit is
    in this file's docstring and this test does not pretend otherwise. What the
    twin proves is the thing that matters: the clearance above is earned by the
    guard calls and not by a detector that cannot see these writes at all.

    **The mutation this exists to survive**: the sync reaching its writes through a
    helper in another module, which the docstring names as the sweep's first limit
    and which would leave the live sweep green while this test goes red.

    **The rename is checked before it is believed** (`docs/MISTAKES.md` entry 3, and
    the "check the mutation landed" habit): a substitution that matched nothing
    would produce an identical twin, the twin would be cleared for the same reason
    the original is, and this test would report a working sweep having tested
    nothing.
    """
    path = APP_ROOT / "services" / "roster_sync.py"
    assert path.is_file(), (
        f"There is no {path.relative_to(REPO_ROOT)}. E1-11's work order (D1) puts every line of "
        "the roster sync there — 'Every write of `user`, `enrollment`, and the INSTRUCTOR "
        "`role_assignment` happens in this module, each immediately preceded by its `guard_write` "
        "call in the same module (the E0-35 static sweep reads per-module)'."
    )

    tables = guarded_tables(authz)
    models = guarded_models(mapped_classes_by_table(import_app_module), tables)
    source = path.read_text(encoding="utf-8")

    seen = {site.relation for site in write_sites(source, path, tables, models)}
    assert {"enrollment", "user"} <= seen, (
        f"This file's detector reads {sorted(seen)} out of {path.relative_to(REPO_ROOT)}, and "
        "E1-11 makes it the writer of `enrollment` and `user`. Either the writes are reached "
        "through a helper in another module — the syntactic sweep's first stated limit — or the "
        "detector cannot see the shape they are written in, in which case the live sweep is "
        "passing for having read nothing."
    )
    assert ROLE_ASSIGNMENT_TABLE in seen, (
        f"The detector reads no `{ROLE_ASSIGNMENT_TABLE}` write naming `{INSTRUCTOR_ROLE}` out of "
        f"{path.relative_to(REPO_ROOT)}. E1-11 writes the teaching instructor's assignment — SPEC "
        "§2.1's fifth owned item, and a purview grant — so either it does not, which is a missing "
        "deliverable, or it writes the row with the role named somewhere this sweep's "
        "`names_the_instructor_role` cannot reach, which is the one write in this project that "
        "hands somebody oversight of a section."
    )
    assert not unrouted_write_sites(source, path, tables, models), (
        f"{path.relative_to(REPO_ROOT)} writes {sorted(seen)} and calls `{GUARD}` nowhere in the "
        "module. ADR 0090's mechanism is that a sanctioned writer satisfies this rule rather than "
        "being excused from it, and there is no exclusion list in this file on purpose."
    )

    unguarded = source.replace(f"{GUARD}(", "a_write_nobody_routed(")
    assert unguarded != source, (
        f"Replacing `{GUARD}(` in {path.relative_to(REPO_ROOT)} changed nothing, so the twin below "
        f"is the original module and would be cleared for calling `{GUARD}` exactly as the "
        "original does. Either the module calls the guard under another spelling — which "
        "`names_the_guard` would also miss, and the clearance above is then meaningless — or this "
        "substitution has gone stale."
    )
    assert unrouted_write_sites(unguarded, path, tables, models), (
        "The sync module with every `guard_write` call renamed was still cleared by this file's "
        "own verdict, so the clearance above is not earned by the guard calls: a copy of this "
        "module that routed nothing would pass the live sweep too, and that sweep is the only "
        "thing standing between an unsanctioned writer and LMS-owned data."
    )
