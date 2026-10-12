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
NAMED = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(RESOLVER)}(?![A-Za-z0-9_])")


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


def references(source: str, where: str) -> list[tuple[int, tuple[str, ...], bool]]:
    """Every reference to the resolver: (line, enclosing function names, is an import).

    A reference is an imported name, a name bound to it by an import alias and
    then used, an attribute access, or a non-docstring string naming it.
    """
    try:
        tree = ast.parse(source, filename=where)
    except SyntaxError as failure:  # pragma: no cover - a broken source tree
        pytest.fail(f"{where} does not parse ({failure}); this sweep would report it clean.")
    excused = docstring_nodes(tree)
    aliases = {RESOLVER}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == RESOLVER and alias.asname:
                    aliases.add(alias.asname)

    found: list[tuple[int, tuple[str, ...], bool]] = []

    def visit(node: ast.AST, enclosing: tuple[str, ...]) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            enclosing = (*enclosing, node.name)
        if isinstance(node, ast.ImportFrom) and any(a.name == RESOLVER for a in node.names):
            found.append((node.lineno, enclosing, True))
        elif (
            isinstance(node, ast.Name)
            and node.id in aliases
            or isinstance(node, ast.Attribute)
            and node.attr == RESOLVER
            or (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in excused
                and NAMED.search(node.value) is not None
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
