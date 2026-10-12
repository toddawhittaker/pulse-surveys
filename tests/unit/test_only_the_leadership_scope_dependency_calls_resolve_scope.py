"""Only `leadership_scope` reaches `resolve_scope` — E9-01, done-when 10's caller sweep.

> The caller sweep finds `resolve_scope` called only from `leadership_scope` and
> the services it passes the scope to, with a planted second caller going red and
> the allowed caller found as a control (MISTAKES entry 35).

**Why.** `resolve_scope(session, person_id=…)` answers any person's leadership
scope. The chokepoint is that the application asks it about one person only —
the verified session's own — and asks it in one place, `api/deps.py`'s
`leadership_scope`. A second caller could pass any person it liked.

**The rule, under `backend/app/`:**

  - `services/authz.py` defines `resolve_scope` and may use it freely (the
    chokepoint module; `leadership_grant_covers` answers on the same purview,
    ADR 0108).
  - `api/deps.py` may import it anywhere, and may reference it — by name, by an
    import alias, as an attribute, or as a string — only inside `def
    leadership_scope`.
  - Every other module references it nowhere. The services `leadership_scope`
    hands the scope to receive an `ActorScope`; they have no reason to name the
    resolver, so "and the services it passes the scope to" adds no exemption.

**The device** is `test_only_the_response_loop_service_names_the_staff_name_
definer.py`'s, copied rather than shared (`docs/MISTAKES.md` entry 37): each
module's syntax tree is walked; docstrings are not read; comments never reach the
tree. **Disclosed limit** (`docs/MISTAKES.md` entry 14): a name assembled at run
time is not matched; nor is anything outside `backend/app/` (scripts, migrations,
tests).

**Controlled in both directions** (`docs/MISTAKES.md` entries 3, 35 and 53): the
matcher against planted references and near misses; the walk against a planted
tree holding a second caller, an aliased caller in `api/deps.py` outside the
dependency, and the allowed shape; and the real `api/deps.py` required to be
*found* calling `resolve_scope` inside `leadership_scope`. A red in a control
means this module is broken, not the code — except the real-tree control before
E9-01 lands, which is red because `leadership_scope` does not exist yet.

**The walk itself is a second door, and is held shut here too** (the E9-01
privacy review). `resolve_scope` is reached by person; `transitive_purview` is
reached by assignment id, and answers that assignment's whole purview. A route
that called it with an assignment id read off the request would resolve somebody
else's scope without ever naming `resolve_scope`, and the rule above would stay
green. So the walk's names — `transitive_purview`, and the two private helpers
that perform it, `_transitive_purview_of` and `_clamped_subtree` — are
referenced nowhere under `backend/app/` but `services/authz.py`:

  - `services/authz.py` defines the walk. It is the only sanctioned caller:
    every other module gets a purview out of the `ActorScope` the
    `leadership_scope` dependency hands it (E9-01: "no route takes a person,
    assignment or scope id from the request to resolve a scope").
  - `api/deps.py` gets **no** exemption for the walk. The dependency resolves a
    scope by the session's person through `resolve_scope`; it has no reason to
    hold an assignment id, and an exemption there would be the door this rule
    closes.

At the time this rule was written, nothing outside `services/authz.py` named any
of the three, so the rule is a closed set of one module. It is controlled the
same three ways: the matcher against planted references (an aliased import and a
call through an aliased module among them — one level out, entry 53) and near
misses; the walk over a planted tree; and the real `services/authz.py` required
to be *found* referencing each guarded name, so a misspelt name cannot make the
sweep vacuous (entry 35).

**The seal's helper is a third door** (E9-05's privacy review, P1).
`authz.leadership_section_ids(session, *, person_id)` answers any person's whole
leadership purview, as a set of section ids, for the benchmark seal (E9-05: "only
`authz.py` may resolve a person's purview for the seal"). A route that called it
with a person id off the request would read somebody else's purview without
naming `resolve_scope` or the walk. So it is referenced nowhere under
`backend/app/` but two modules:

  - `services/authz.py`, which defines it;
  - `services/benchmarks.py`, the seal, which uses the purview only to decide
    what to withhold and never returns it.

Controlled the same three ways: planted references (an aliased import and a call
through an aliased module, entry 53) and near misses; a planted tree with a
caller in each of `api/` and another service; and both allowed modules required
to be *found* referencing it (entry 35).

**Two more doors, carried into E9-12** (its work order, items C1 and C4), held by
the same closed-set rule and controlled the same three ways:

  - `authz.leadership_grant_covers(session, *, person_id, …)` answers on any
    person's leadership grant (ADR 0108). It may be named only in
    `services/authz.py`, which defines it, and `services/provisioning.py` (the
    E9-01 residue, C1).
  - `authz.admin_grant_nodes(session, *, role)` is E9-10's unscoped read of every
    org node at a level, for the admin's grant picker. It may be named only in
    `services/authz.py`, which defines it, and `api/admin.py`, its one caller
    (C4). **Its found-reference controls are red until E9-10 merges into the
    epic branch**, because neither module names it on a branch without E9-10;
    the rule itself is green either way.
"""

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"
THE_CHOKEPOINT = Path("services/authz.py")
THE_DEPENDENCY_MODULE = Path("api/deps.py")
THE_DEPENDENCY = "leadership_scope"
RESOLVER = "resolve_scope"
# The walk's names: the public door by assignment id, and the two private
# helpers that perform it. Each is a way to a purview without going through
# `resolve_scope`.
THE_WALK = ("transitive_purview", "_transitive_purview_of", "_clamped_subtree")
# The seal's helper (E9-05), and the only modules that may name it.
THE_SEAL_HELPER = "leadership_section_ids"
THE_SEAL = Path("services/benchmarks.py")
THE_SEAL_HELPER_MODULES = (THE_CHOKEPOINT, THE_SEAL)


def named(name: str) -> re.Pattern[str]:
    """`name` as a whole identifier inside a string, not as part of a longer one."""
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")


def docstring_nodes(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(id(body[0].value))
    return found


def references(
    source: str, where: str, name: str = RESOLVER
) -> list[tuple[int, tuple[str, ...], bool]]:
    """Every reference to `name`: (line, enclosing function names, is an import).

    A reference is an imported name, a name bound to it by an import alias and
    then used, an attribute access, or a non-docstring string naming it.
    """
    try:
        tree = ast.parse(source, filename=where)
    except SyntaxError as failure:  # pragma: no cover - a broken source tree
        pytest.fail(f"{where} does not parse ({failure}); this sweep would report it clean.")
    excused = docstring_nodes(tree)
    pattern = named(name)
    aliases = {name}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == name and alias.asname:
                    aliases.add(alias.asname)

    found: list[tuple[int, tuple[str, ...], bool]] = []

    def visit(node: ast.AST, enclosing: tuple[str, ...]) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            enclosing = (*enclosing, node.name)
        if isinstance(node, ast.ImportFrom) and any(a.name == name for a in node.names):
            found.append((node.lineno, enclosing, True))
        elif (
            (isinstance(node, ast.Name) and node.id in aliases)
            or (isinstance(node, ast.Attribute) and node.attr == name)
            or (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in excused
                and pattern.search(node.value) is not None
            )
        ):
            found.append((node.lineno, enclosing, False))
        for child in ast.iter_child_nodes(node):
            visit(child, enclosing)

    visit(tree, ())
    return found


def offending(relative: Path, source: str) -> list[int]:
    """The lines of one module that reference the resolver where the rule forbids it."""
    if relative == THE_CHOKEPOINT:
        return []
    found = references(source, str(relative))
    if relative == THE_DEPENDENCY_MODULE:
        return [
            line
            for line, enclosing, is_import in found
            if not is_import and THE_DEPENDENCY not in enclosing
        ]
    return [line for line, _, _ in found]


def offenders_under(root: Path) -> list[str]:
    out: list[str] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        for line in offending(relative, path.read_text(encoding="utf-8")):
            out.append(f"{relative}:{line}")
    return out


PLANTED_REFERENCES = {
    "a direct import": "from app.services.authz import resolve_scope\n",
    "an attribute call": (
        "from app.services import authz\n\n\n"
        "def read(session, person):\n"
        "    return authz.resolve_scope(session, person_id=person)\n"
    ),
    "an aliased call": (
        "from app.services.authz import resolve_scope as scope_of\n\n\n"
        "def read(session, person):\n"
        "    return scope_of(session, person_id=person)\n"
    ),
    "a getattr by string": (
        "from app.services import authz\n\nRESOLVE = getattr(authz, 'resolve_scope')\n"
    ),
}

PLANTED_NEAR_MISSES = {
    "prose": (
        '"""Scopes come from resolve_scope, through the dependency."""\n\n'
        "# resolve_scope is called by leadership_scope only.\n\n\n"
        "def ping():\n"
        '    """This never calls resolve_scope."""\n'
        "    return 'pong'\n"
    ),
    "a longer name": "resolve_scope_label = 'Scope'\nFLAG = 'resolve_scopes'\n",
    "the scope it hands out": ("def read(scope):\n    return sorted(scope.purview.section_ids)\n"),
}

PLANTED_TREE = {
    "services/authz.py": (
        "def resolve_scope(session, *, person_id):\n    return None\n\n\n"
        "def leadership_grant_covers(session, *, person_id):\n"
        "    return resolve_scope(session, person_id=person_id)\n"
    ),
    "api/deps.py": (
        "from app.services.authz import resolve_scope\n"
        "from app.services.authz import resolve_scope as scope_of\n\n\n"
        "def leadership_scope(session, person_id):\n"
        "    return resolve_scope(session, person_id=person_id)\n\n\n"
        "def another_dependency(session, person_id):\n"
        "    return scope_of(session, person_id=person_id)\n"
    ),
    "services/rollups.py": (
        "from app.services import authz\n\n\n"
        "def tree(session, person_id):\n"
        "    return authz.resolve_scope(session, person_id=person_id)\n"
    ),
    "api/leadership.py": ("def rollup(scope):\n    return scope.purview\n"),
}


def test_the_matcher_finds_planted_references_and_spares_its_near_misses() -> None:
    """The instrument, both directions. **A red means this module is broken.**

    **The mutations this kills:** a matcher reading `ast.Name` only (misses the
    attribute call and the alias), one reading import statements only, a plain
    substring search (flags the longer names), and the docstring exemption
    dropped (flags prose).
    """
    found = {name: bool(references(source, name)) for name, source in PLANTED_REFERENCES.items()}
    missed = sorted(name for name, hit in found.items() if not hit)
    assert not missed, f"The matcher missed these planted references: {missed}."

    spared = {name: references(source, name) for name, source in PLANTED_NEAR_MISSES.items()}
    flagged = {name: hits for name, hits in spared.items() if hits}
    assert not flagged, f"The matcher flagged these near misses: {flagged}."


def test_the_walk_flags_a_second_caller_and_an_aliased_caller_and_spares_the_allowed_ones(
    tmp_path: Path,
) -> None:
    """The control on the walk and the rule: a planted second caller goes red.

    **The mutations this kills:** the walk narrowed to one directory; the
    exemption written as the whole of `api/deps.py` (the aliased caller outside
    the dependency walks free); the exemption written as `services/` (the planted
    roll-up service walks free); an import alias not followed.
    """
    for name, source in PLANTED_TREE.items():
        planted = tmp_path / name
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(source, encoding="utf-8")
    assert offenders_under(tmp_path) == ["api/deps.py:10", "services/rollups.py:5"]


def test_the_real_dependency_is_found_calling_the_resolver() -> None:
    """The allowed caller, found: `api/deps.py` references `resolve_scope` inside `leadership_scope`.

    `docs/MISTAKES.md` entry 35: a guard that only ever reports absence cannot
    tell you what it can see. **Red before E9-01 lands**, because
    `leadership_scope` does not exist; afterwards, a red means this sweep has
    gone blind.
    """
    deps = APP_ROOT / THE_DEPENDENCY_MODULE
    assert deps.is_file(), f"{deps.relative_to(REPO_ROOT)} does not exist."
    inside = [
        line
        for line, enclosing, is_import in references(deps.read_text(encoding="utf-8"), str(deps))
        if not is_import and THE_DEPENDENCY in enclosing
    ]
    assert inside, (
        f"The sweep finds no reference to `{RESOLVER}` inside `def {THE_DEPENDENCY}` in "
        f"{deps.relative_to(REPO_ROOT)}. E9-01: 'A new dependency in `api/deps.py`, "
        "`leadership_scope`, resolves the scope from the verified session's own `person_id`.' "
        "Either the dependency is missing, or it reaches the resolver some way this sweep cannot "
        "see — and then the sweep below reports a clean tree it did not read."
    )


def test_no_module_but_the_leadership_scope_dependency_calls_resolve_scope() -> None:
    """The rule over the real tree: no second caller of `resolve_scope` under `backend/app`.

    **The mutation this kills:** a route, a service or a task calling
    `resolve_scope` itself with a person id of its own choosing — which is the
    one thing the chokepoint exists to prevent. **The non-emptiness control:** the
    walk reads more than the two modules the rule names.
    """
    assert APP_ROOT.is_dir(), f"{APP_ROOT} is not a directory, so this sweep walked nothing."
    swept = list(APP_ROOT.rglob("*.py"))
    assert len(swept) > 2, f"{APP_ROOT} holds next to nothing to sweep."
    offenders = offenders_under(APP_ROOT)
    assert not offenders, (
        f"`{RESOLVER}` is referenced outside `{THE_CHOKEPOINT}` and `{THE_DEPENDENCY}` in "
        f"`{THE_DEPENDENCY_MODULE}`: {offenders}. E9-01: 'no route takes a person, assignment or "
        "scope id from the request to resolve a scope'; take an `ActorScope` from the "
        f"`{THE_DEPENDENCY}` dependency instead."
    )


# ---------------------------------------------------------------------------
# The walk: `transitive_purview` and the helpers that perform it.
# ---------------------------------------------------------------------------


def walk_offending(relative: Path, source: str) -> list[int]:
    """The lines of one module that reference any of the walk's names where the rule forbids it.

    The rule is a closed set of one module: `services/authz.py`. `api/deps.py` is
    deliberately not exempt — see the module docstring.
    """
    if relative == THE_CHOKEPOINT:
        return []
    lines: set[int] = set()
    for name in THE_WALK:
        lines.update(line for line, _, _ in references(source, str(relative), name))
    return sorted(lines)


def walk_offenders_under(root: Path) -> list[str]:
    out: list[str] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        for line in walk_offending(relative, path.read_text(encoding="utf-8")):
            out.append(f"{relative}:{line}")
    return out


def walk_references(source: str, where: str) -> list[tuple[str, int]]:
    """Every reference to any of the walk's names, as (name, line)."""
    return [(name, line) for name in THE_WALK for line, _, _ in references(source, where, name)]


PLANTED_WALK_REFERENCES = {
    "an aliased import, called with an id off the request": (
        "from app.services.authz import transitive_purview as walk\n\n\n"
        "def read(session, request):\n"
        "    return walk(session, assignment_id=request.query_params['assignment'])\n"
    ),
    "a call through an aliased module": (
        "from app.services import authz as az\n\n\n"
        "def read(session, assignment_id):\n"
        "    return az.transitive_purview(session, assignment_id=assignment_id)\n"
    ),
    "the private door, through the dotted module path": (
        "import app.services.authz\n\n\n"
        "def read(session, row):\n"
        "    return app.services.authz._transitive_purview_of(session, row)\n"
    ),
    "the subtree helper, by string": (
        "from app.services import authz\n\nWALK = getattr(authz, '_clamped_subtree')\n"
    ),
}

PLANTED_WALK_NEAR_MISSES = {
    "prose": (
        '"""A purview comes from transitive_purview, inside the authz module."""\n\n'
        "# _clamped_subtree and _transitive_purview_of are private to authz.\n\n\n"
        "def ping():\n"
        '    """This never calls transitive_purview."""\n'
        "    return 'pong'\n"
    ),
    "longer and shorter names": (
        "transitive_purview_label = 'Purview'\n"
        "FLAG = 'transitive_purviews'\n"
        "OTHER = 'transitive_purview_of'\n"
        "COUNT = '_clamped_subtree_count'\n"
    ),
    "the purview a scope carries": ("def read(scope):\n    return scope.purview.section_ids\n"),
}

PLANTED_WALK_TREE = {
    "services/authz.py": (
        "def _clamped_subtree(session, frontier):\n    return frontier\n\n\n"
        "def _transitive_purview_of(session, root):\n"
        "    return _clamped_subtree(session, [root])\n\n\n"
        "def transitive_purview(session, *, assignment_id):\n"
        "    return _transitive_purview_of(session, assignment_id)\n"
    ),
    "api/deps.py": (
        "from app.services.authz import resolve_scope, transitive_purview\n\n\n"
        "def leadership_scope(session, person_id, assignment_id):\n"
        "    return transitive_purview(session, assignment_id=assignment_id)\n"
    ),
    "api/leadership.py": (
        "from app.services import authz as az\n\n\n"
        "def rollup(session, assignment_id):\n"
        "    return az.transitive_purview(session, assignment_id=assignment_id)\n"
    ),
    "services/tree.py": (
        "from app.services.authz import _transitive_purview_of as walk_from\n\n\n"
        "def tree(session, row):\n"
        "    return walk_from(session, row)\n"
    ),
    "services/rollups.py": ("def tree(scope):\n    return scope.purview\n"),
}


def test_the_walk_matcher_finds_planted_references_and_spares_its_near_misses() -> None:
    """The instrument for the walk's names, both directions. **A red means this module is broken.**

    **The mutations this kills:** a matcher reading `ast.Name` only (misses the
    call through the aliased module and the dotted path); one that does not
    follow an import alias (misses `walk(...)`); one guarding `transitive_purview`
    only (misses both private helpers); one dropping the string branch (misses the
    `getattr`). **The near misses it spares:** a plain substring search flags
    `transitive_purview_label`, `transitive_purview_of` and
    `_clamped_subtree_count`; a matcher that reads docstrings flags the prose.
    """
    found = {
        name: walk_references(source, name) for name, source in PLANTED_WALK_REFERENCES.items()
    }
    missed = sorted(name for name, hits in found.items() if not hits)
    assert not missed, f"The walk matcher missed these planted references: {missed}."

    spared = {
        name: walk_references(source, name) for name, source in PLANTED_WALK_NEAR_MISSES.items()
    }
    flagged = {name: hits for name, hits in spared.items() if hits}
    assert not flagged, f"The walk matcher flagged these near misses: {flagged}."


def test_the_walk_sweep_flags_every_caller_outside_authz_including_the_dependency(
    tmp_path: Path,
) -> None:
    """The control on the walk rule over a planted tree: three callers go red, `authz` does not.

    **The mutations this kills:** the walk rule given `api/deps.py`'s exemption
    for `leadership_scope` (the planted dependency calling `transitive_purview`
    with an assignment id walks free); the rule exempting all of `services/` (the
    planted `services/tree.py` walks free); a module alias not followed one level
    out (the planted `api/leadership.py` walks free — `docs/MISTAKES.md` entry 53).
    **The near miss it spares:** `services/authz.py` defining and calling all
    three names, and a service reading `scope.purview`.
    """
    for name, source in PLANTED_WALK_TREE.items():
        planted = tmp_path / name
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(source, encoding="utf-8")
    assert walk_offenders_under(tmp_path) == [
        "api/deps.py:1",
        "api/deps.py:5",
        "api/leadership.py:5",
        "services/tree.py:1",
        "services/tree.py:5",
    ]


def test_the_real_authz_module_is_found_referencing_every_name_of_the_walk() -> None:
    """The allowed caller, found: `services/authz.py` references each guarded name.

    `docs/MISTAKES.md` entry 35. The rule below reports absence, and absence of a
    misspelt name is guaranteed; so each name in `THE_WALK` is required to be
    *found* in the one module that defines it. **A red here means a guarded name
    is wrong or has been renamed, and the rule below has gone blind to it** —
    update `THE_WALK`, never delete the name.
    """
    chokepoint = APP_ROOT / THE_CHOKEPOINT
    assert chokepoint.is_file(), f"{chokepoint.relative_to(REPO_ROOT)} does not exist."
    source = chokepoint.read_text(encoding="utf-8")
    unseen = [name for name in THE_WALK if not references(source, str(chokepoint), name)]
    assert not unseen, (
        f"The sweep finds no reference to {unseen} in {chokepoint.relative_to(REPO_ROOT)}. Each "
        "name in `THE_WALK` is a door to the purview walk; one the sweep cannot see in the module "
        "that defines it is one it cannot see anywhere else either."
    )


def test_no_module_but_authz_reaches_the_purview_walk() -> None:
    """The rule over the real tree: `transitive_purview` and its helpers are called from `authz` only.

    **The mutation this kills:** a route or a service calling
    `transitive_purview(session, assignment_id=…)` with an id read off the
    request — the E9-01 privacy review's second door, which the `resolve_scope`
    rule above does not see. **The non-emptiness control:** the walk reads more
    than the one module the rule names.
    """
    assert APP_ROOT.is_dir(), f"{APP_ROOT} is not a directory, so this sweep walked nothing."
    swept = list(APP_ROOT.rglob("*.py"))
    assert len(swept) > 2, f"{APP_ROOT} holds next to nothing to sweep."
    offenders = walk_offenders_under(APP_ROOT)
    assert not offenders, (
        f"The purview walk ({', '.join(THE_WALK)}) is referenced outside `{THE_CHOKEPOINT}`: "
        f"{offenders}. E9-01: 'no route takes a person, assignment or scope id from the request "
        f"to resolve a scope'; take an `ActorScope` from the `{THE_DEPENDENCY}` dependency instead."
    )


# ---------------------------------------------------------------------------
# The seal's helper: `leadership_section_ids` (E9-05).
# ---------------------------------------------------------------------------


def seal_helper_offending(relative: Path, source: str) -> list[int]:
    """The lines of one module that reference the seal's helper where the rule forbids it.

    A closed set of two modules: `services/authz.py` and `services/benchmarks.py`.
    `api/deps.py` gets no exemption; the dependency resolves a scope through
    `resolve_scope`, never a bare set of section ids.
    """
    if relative in THE_SEAL_HELPER_MODULES:
        return []
    return sorted({line for line, _, _ in references(source, str(relative), THE_SEAL_HELPER)})


def seal_helper_offenders_under(root: Path) -> list[str]:
    out: list[str] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        for line in seal_helper_offending(relative, path.read_text(encoding="utf-8")):
            out.append(f"{relative}:{line}")
    return out


PLANTED_SEAL_HELPER_REFERENCES = {
    "an aliased import, called with a person off the request": (
        "from app.services.authz import leadership_section_ids as purview_of\n\n\n"
        "def read(session, request):\n"
        "    return purview_of(session, person_id=request.query_params['person'])\n"
    ),
    "a call through an aliased module": (
        "from app.services import authz as az\n\n\n"
        "def read(session, person_id):\n"
        "    return az.leadership_section_ids(session, person_id=person_id)\n"
    ),
    "a call through the dotted module path": (
        "import app.services.authz\n\n\n"
        "def read(session, person_id):\n"
        "    return app.services.authz.leadership_section_ids(session, person_id=person_id)\n"
    ),
    "a getattr by string": (
        "from app.services import authz\n\nIDS = getattr(authz, 'leadership_section_ids')\n"
    ),
}

PLANTED_SEAL_HELPER_NEAR_MISSES = {
    "prose": (
        '"""The seal asks leadership_section_ids, inside the benchmarks module."""\n\n'
        "# leadership_section_ids is the seal's alone.\n\n\n"
        "def ping():\n"
        '    """This never calls leadership_section_ids."""\n'
        "    return 'pong'\n"
    ),
    "longer and shorter names": (
        "leadership_section_ids_label = 'Sections'\n"
        "FLAG = 'leadership_section_idss'\n"
        "OTHER = 'leadership_section'\n"
    ),
    "the section ids a scope carries": (
        "def read(scope):\n    return frozenset(scope.purview.section_ids)\n"
    ),
}

PLANTED_SEAL_HELPER_TREE = {
    "services/authz.py": (
        "def leadership_section_ids(session, *, person_id):\n    return frozenset()\n"
    ),
    "services/benchmarks.py": (
        "from app.services.authz import leadership_section_ids\n\n\n"
        "def _known(session, person_id):\n"
        "    return leadership_section_ids(session, person_id=person_id)\n"
    ),
    "api/deps.py": (
        "from app.services.authz import leadership_section_ids\n\n\n"
        "def leadership_scope(session, person_id):\n"
        "    return leadership_section_ids(session, person_id=person_id)\n"
    ),
    "api/leadership.py": (
        "from app.services.authz import leadership_section_ids as purview_of\n\n\n"
        "def rollup(session, request):\n"
        "    return purview_of(session, person_id=request.query_params['person'])\n"
    ),
    "services/rollups.py": (
        "from app.services import authz as az\n\n\n"
        "def tree(session, person_id):\n"
        "    return az.leadership_section_ids(session, person_id=person_id)\n"
    ),
    "services/reports.py": ("def read(scope):\n    return frozenset(scope.purview.section_ids)\n"),
}


def test_the_seal_helper_matcher_finds_planted_references_and_spares_its_near_misses() -> None:
    """The instrument for the seal's helper, both ways. **A red means this module is broken.**

    **The mutations this kills:** a matcher that does not follow an import alias
    (misses `purview_of(...)`); one reading `ast.Name` only (misses the call
    through the aliased module and the dotted path); one dropping the string
    branch (misses the `getattr`). **The near misses it spares:** a plain
    substring search flags `leadership_section_ids_label` and
    `leadership_section_idss`; a matcher that reads docstrings flags the prose;
    one matching `section_ids` alone flags a scope's own purview.
    """
    found = {
        name: references(source, name, THE_SEAL_HELPER)
        for name, source in PLANTED_SEAL_HELPER_REFERENCES.items()
    }
    missed = sorted(name for name, hits in found.items() if not hits)
    assert not missed, f"The seal-helper matcher missed these planted references: {missed}."

    spared = {
        name: references(source, name, THE_SEAL_HELPER)
        for name, source in PLANTED_SEAL_HELPER_NEAR_MISSES.items()
    }
    flagged = {name: hits for name, hits in spared.items() if hits}
    assert not flagged, f"The seal-helper matcher flagged these near misses: {flagged}."


def test_the_seal_helper_sweep_flags_callers_one_level_out_and_spares_authz_and_the_seal(
    tmp_path: Path,
) -> None:
    """The control on the rule, over a planted tree: three callers red, `authz` and the seal not.

    **The mutations this kills:** the rule exempting all of `services/` (the
    planted `services/rollups.py` walks free); `api/deps.py` given the
    `resolve_scope` exemption here too (the planted dependency calling the helper
    walks free); an import alias or a module alias not followed one level out
    (the planted `api/leadership.py` or `services/rollups.py` walks free —
    `docs/MISTAKES.md` entry 53). **The near misses it spares:** `services/authz.py`
    defining the helper, `services/benchmarks.py` calling it, and a service
    reading `scope.purview.section_ids`.
    """
    for name, source in PLANTED_SEAL_HELPER_TREE.items():
        planted = tmp_path / name
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(source, encoding="utf-8")
    assert seal_helper_offenders_under(tmp_path) == [
        "api/deps.py:1",
        "api/deps.py:5",
        "api/leadership.py:1",
        "api/leadership.py:5",
        "services/rollups.py:5",
    ]


@pytest.mark.parametrize(
    "allowed", THE_SEAL_HELPER_MODULES, ids=[str(module) for module in THE_SEAL_HELPER_MODULES]
)
def test_each_allowed_module_is_found_referencing_the_seal_helper(allowed: Path) -> None:
    """The allowed modules, found: `authz` defines `leadership_section_ids`, the seal calls it.

    `docs/MISTAKES.md` entry 35: the rule below reports absence, and absence of a
    misspelt or renamed helper is guaranteed. **A red in `services/authz.py`
    means the helper is renamed or gone** and the rule has gone blind to it;
    **a red in `services/benchmarks.py` means the seal reaches a person's purview
    some way this sweep does not name** — update `THE_SEAL_HELPER`, never delete
    this check.
    """
    module = APP_ROOT / allowed
    assert module.is_file(), f"{module.relative_to(REPO_ROOT)} does not exist."
    found = references(module.read_text(encoding="utf-8"), str(module), THE_SEAL_HELPER)
    assert found, (
        f"The sweep finds no reference to `{THE_SEAL_HELPER}` in {module.relative_to(REPO_ROOT)}. "
        "E9-05: the seal resolves a person's purview through this one helper in `authz.py`."
    )


def test_no_module_but_authz_and_the_seal_names_leadership_section_ids() -> None:
    """The rule over the real tree: `leadership_section_ids` lives in `authz` and the seal only.

    **The mutation this kills:** a route or a service calling
    `leadership_section_ids(session, person_id=…)` with a person id of its own
    choosing — reading another person's whole purview as section ids, past
    both `resolve_scope` and the walk rules above (E9-05's privacy review, P1).
    **The non-emptiness control:** the walk reads more than the two modules the
    rule names.
    """
    assert APP_ROOT.is_dir(), f"{APP_ROOT} is not a directory, so this sweep walked nothing."
    swept = list(APP_ROOT.rglob("*.py"))
    assert len(swept) > 2, f"{APP_ROOT} holds next to nothing to sweep."
    offenders = seal_helper_offenders_under(APP_ROOT)
    assert not offenders, (
        f"`{THE_SEAL_HELPER}` is referenced outside {[str(m) for m in THE_SEAL_HELPER_MODULES]}: "
        f"{offenders}. It answers any person's leadership purview; every other module takes an "
        f"`ActorScope` from the `{THE_DEPENDENCY}` dependency instead."
    )


# ---------------------------------------------------------------------------
# E9-12's carried doors: `leadership_grant_covers` (C1) and `admin_grant_nodes` (C4).
# ---------------------------------------------------------------------------

# Each guarded name and the only modules that may name it. `api/deps.py` gets no
# exemption for either: the dependency resolves a scope through `resolve_scope`.
CLOSED_DOORS: dict[str, tuple[Path, ...]] = {
    "leadership_grant_covers": (THE_CHOKEPOINT, Path("services/provisioning.py")),
    "admin_grant_nodes": (THE_CHOKEPOINT, Path("api/admin.py")),
}


def door_offenders_under(root: Path, name: str) -> list[str]:
    """Every reference to `name` under `root` outside its allowed modules, as "path:line"."""
    allowed = CLOSED_DOORS[name]
    out: list[str] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if relative in allowed:
            continue
        lines = sorted(
            {
                line
                for line, _, _ in references(path.read_text(encoding="utf-8"), str(relative), name)
            }
        )
        out.extend(f"{relative}:{line}" for line in lines)
    return out


def planted_references(name: str) -> dict[str, str]:
    """The four reference shapes, one level out included, for one guarded name."""
    return {
        "an aliased import, called with a person off the request": (
            f"from app.services.authz import {name} as door\n\n\n"
            "def read(session, request):\n"
            "    return door(session, person_id=request.query_params['person'])\n"
        ),
        "a call through an aliased module": (
            "from app.services import authz as az\n\n\n"
            "def read(session, person_id):\n"
            f"    return az.{name}(session, person_id=person_id)\n"
        ),
        "a call through the dotted module path": (
            "import app.services.authz\n\n\n"
            "def read(session, person_id):\n"
            f"    return app.services.authz.{name}(session, person_id=person_id)\n"
        ),
        "a getattr by string": (
            f"from app.services import authz\n\nDOOR = getattr(authz, '{name}')\n"
        ),
    }


def planted_near_misses(name: str) -> dict[str, str]:
    return {
        "prose": (
            f'"""Only authz names {name}."""\n\n'
            f"# {name} is a closed door.\n\n\n"
            "def ping():\n"
            f'    """This never calls {name}."""\n'
            "    return 'pong'\n"
        ),
        "longer and shorter names": (
            f"{name}_label = 'Door'\nFLAG = '{name}s'\nOTHER = '{name[:-1]}'\n"
        ),
    }


def planted_tree(name: str) -> dict[str, str]:
    """The allowed modules naming `name`, and three callers one level out."""
    allowed = CLOSED_DOORS[name]
    tree = {
        str(allowed[0]): f"def {name}(session, **kwargs):\n    return frozenset()\n",
        str(allowed[1]): (
            f"from app.services.authz import {name}\n\n\n"
            "def allowed(session):\n"
            f"    return {name}(session)\n"
        ),
        "api/deps.py": (
            f"from app.services.authz import {name}\n\n\n"
            "def leadership_scope(session, person_id):\n"
            f"    return {name}(session, person_id=person_id)\n"
        ),
        "api/leadership.py": (
            f"from app.services.authz import {name} as door\n\n\n"
            "def rollup(session, request):\n"
            "    return door(session, person_id=request.query_params['person'])\n"
        ),
        "services/rollups.py": (
            "from app.services import authz as az\n\n\n"
            "def tree(session, person_id):\n"
            f"    return az.{name}(session, person_id=person_id)\n"
        ),
    }
    return tree


@pytest.mark.parametrize("name", sorted(CLOSED_DOORS))
def test_the_closed_door_matcher_finds_planted_references_and_spares_near_misses(
    name: str,
) -> None:
    """The instrument for each carried door, both ways. **A red means this module is broken.**

    **The mutations it kills (in the sweep):** an import alias not followed; a
    module alias or the dotted path not followed one level out
    (`docs/MISTAKES.md` entry 53); the string branch dropped. **The near misses
    it spares:** prose, docstrings, and longer or shorter names.
    """
    found = {
        what: references(source, what, name) for what, source in planted_references(name).items()
    }
    missed = sorted(what for what, hits in found.items() if not hits)
    assert not missed, f"The matcher missed these planted references to `{name}`: {missed}."
    spared = {
        what: references(source, what, name) for what, source in planted_near_misses(name).items()
    }
    flagged = {what: hits for what, hits in spared.items() if hits}
    assert not flagged, f"The matcher flagged these near misses of `{name}`: {flagged}."


@pytest.mark.parametrize("name", sorted(CLOSED_DOORS))
def test_the_closed_door_sweep_flags_callers_one_level_out_and_spares_the_allowed_modules(
    name: str, tmp_path: Path
) -> None:
    """The control on each rule, over a planted tree: three callers red, the allowed two not.

    **The mutations it kills:** the rule exempting all of `services/` (the
    planted roll-up walks free); `api/deps.py` given an exemption (the planted
    dependency walks free); an alias not followed (the planted leadership route
    walks free). **A red means this module is broken.**
    """
    for relative, source in planted_tree(name).items():
        planted = tmp_path / relative
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(source, encoding="utf-8")
    assert door_offenders_under(tmp_path, name) == [
        "api/deps.py:1",
        "api/deps.py:5",
        "api/leadership.py:1",
        "api/leadership.py:5",
        "services/rollups.py:5",
    ]


@pytest.mark.parametrize(
    ("name", "allowed"),
    [(name, module) for name, modules in sorted(CLOSED_DOORS.items()) for module in modules],
    ids=[
        f"{name}-{module}" for name, modules in sorted(CLOSED_DOORS.items()) for module in modules
    ],
)
def test_each_allowed_module_is_found_naming_its_carried_door(name: str, allowed: Path) -> None:
    """The found-reference control (`docs/MISTAKES.md` entry 35): each allowed module names its door.

    A rule that reports absence is satisfied by a misspelt or renamed name. **A
    red for `services/authz.py` means the door is renamed or gone; a red for the
    other module means it reaches the door some way this sweep cannot see.**
    `admin_grant_nodes` is E9-10's, so both of its rows are red until E9-10 merges
    into the epic branch.
    """
    module = APP_ROOT / allowed
    assert module.is_file(), f"{module.relative_to(REPO_ROOT)} does not exist."
    found = references(module.read_text(encoding="utf-8"), str(module), name)
    assert found, f"The sweep finds no reference to `{name}` in {module.relative_to(REPO_ROOT)}."


@pytest.mark.parametrize("name", sorted(CLOSED_DOORS))
def test_no_module_but_the_allowed_two_names_a_carried_door(name: str) -> None:
    """The rule over the real tree, for each carried door.

    **The mutation it kills:** a route or a service calling
    `leadership_grant_covers` (any person's grant) or `admin_grant_nodes` (every
    org node, unscoped) itself — a read past `leadership_scope` and past the
    admin gate. **The non-emptiness control:** the walk reads more than the two
    allowed modules.
    """
    assert APP_ROOT.is_dir(), f"{APP_ROOT} is not a directory, so this sweep walked nothing."
    assert len(list(APP_ROOT.rglob("*.py"))) > 2, f"{APP_ROOT} holds next to nothing to sweep."
    offenders = door_offenders_under(APP_ROOT, name)
    assert (
        not offenders
    ), f"`{name}` is referenced outside {[str(m) for m in CLOSED_DOORS[name]]}: {offenders}."
