"""E5.1-03 criterion 6 — the dead parts are gone, and each helper has one home.

> One `_person_of` helper exists, its callers are moved, and the copies are
> deleted. `LTI_LOGIN_COOKIE` is gone, and the web door's cookie helpers live in
> `api/auth.py`.

The work order settles the shape (rulings R8 and R9):

  - **one `person_of`.** It becomes public `person_of(claims)` in
    `app/api/deps.py`, the module that holds what a router needs from the
    request. `api/instructor.py` and `api/leadership.py` delete their copies and
    import it;
  - **`LTI_LOGIN_COOKIE` is deleted**, from its definition and from `__all__`;
  - **the web door's cookie half moves to `app/api/auth.py`**:
    `OIDC_LOGIN_COOKIE`, `LOGIN_COOKIE_LIFETIME_SECONDS`, `COOKIE_ALGORITHM`,
    `carry_across`, `carried_across`, `clear_carried` and `with_query`.

**Read from the source, not from the imported modules.** Every rule here is a
question about where a name is *defined*, and an imported module cannot answer
it: `deps.OIDC_LOGIN_COOKIE` exists whether `deps.py` defines it or re-imports it
from `auth.py`, and the criterion is that it lives in one place. So each module
is parsed with `ast` and its module-level bindings are read — a `def`, a
`class`, an assignment, or an import alias. Nothing here imports the
application.

**The controls come first.** The binding reader is run on samples written here,
in both directions, before it is believed about the tree (`docs/MISTAKES.md`
entry 3). **A red in a control means these tests are broken, not the code.**

**Which failure a red is, before E5.1-03 lands.** The controls are green. Every
rule is red on an assertion: `_person_of` is defined in two routers, no
`person_of` exists, `LTI_LOGIN_COOKIE` is still in `deps.py`, and the cookie
helpers are defined there rather than in `auth.py`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
APP_ROOT = BACKEND_ROOT / "app"
API_ROOT = APP_ROOT / "api"

DEPS = "app/api/deps.py"
AUTH = "app/api/auth.py"

# R8's names: the helper as it is copied today, and as it is after the move.
PRIVATE_HELPER = "_person_of"
PUBLIC_HELPER = "person_of"

# The two routers that hold a copy today and call the shared one afterwards.
FORMER_DEFINERS = ("app/api/instructor.py", "app/api/leadership.py")

# R9's names.
DEAD_COOKIE = "LTI_LOGIN_COOKIE"
WEB_DOOR_COOKIE_HALF = (
    "OIDC_LOGIN_COOKIE",
    "LOGIN_COOKIE_LIFETIME_SECONDS",
    "COOKIE_ALGORITHM",
    "carry_across",
    "carried_across",
    "clear_carried",
    "with_query",
)

# A sample module binding names every way a module can, and naming one more
# that it only uses. Written here; nothing in it is copied from the tree.
A_BINDING_SAMPLE = "\n".join(
    [
        '"""A sample module."""',
        "",
        "from collections.abc import Mapping as SAMPLE_IMPORTED",
        "import json",
        "",
        "SAMPLE_ASSIGNED = 'a value'",
        "SAMPLE_ANNOTATED: int = 3",
        "SAMPLE_FIRST, SAMPLE_SECOND = 1, 2",
        "",
        "",
        "def sample_function(claims):",
        "    nested_only = 1",
        "    return SAMPLE_USED_ONLY(claims)",
        "",
        "",
        "async def sample_coroutine():",
        "    return None",
        "",
        "",
        "class SampleClass:",
        "    attribute_only = 1",
        "",
    ]
)

SAMPLE_BOUND = (
    "SAMPLE_IMPORTED",
    "json",
    "SAMPLE_ASSIGNED",
    "SAMPLE_ANNOTATED",
    "SAMPLE_FIRST",
    "SAMPLE_SECOND",
    "sample_function",
    "sample_coroutine",
    "SampleClass",
)
SAMPLE_NOT_BOUND = ("SAMPLE_USED_ONLY", "nested_only", "attribute_only", "Mapping")

# A helper defined at module level, and the same name nested inside a function.
# Both are definitions; the public twin of the name is not.
A_DEFINITION_SAMPLE = "\n".join(
    [
        "def _person_of(claims):",
        "    return claims",
        "",
        "",
        "def handler(claims):",
        "    def _person_of(inner):",
        "        return inner",
        "",
        "    return _person_of(claims)",
        "",
        "",
        "def person_of(claims):",
        "    return claims",
        "",
    ]
)


# ---------------------------------------------------------------------------
# The readers.
# ---------------------------------------------------------------------------


def parsed(relative: str) -> ast.Module:
    """One module under `backend/`, parsed, or a failure naming the file that is missing."""
    path = BACKEND_ROOT / relative
    if not path.is_file():
        pytest.fail(
            f"backend/{relative} does not exist, so this rule would read nothing. E5.1-03's "
            "criterion 6 is a statement about that file."
        )
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def bound_at_module_level(tree: ast.Module) -> dict[str, str]:
    """Every name a module binds at its top level, and how: defined or imported.

    Top level only, deliberately: a name a function binds locally is not
    something another module can import, and an attribute set in a class body is
    the class's. `if`/`try` blocks at module level are read through, because a
    definition guarded by a condition is still a definition.
    """
    found: dict[str, str] = {}

    def visit(statements: list[ast.stmt]) -> None:
        for statement in statements:
            if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                found[statement.name] = "defined"
            elif isinstance(statement, ast.Assign):
                for target in statement.targets:
                    for node in ast.walk(target):
                        if isinstance(node, ast.Name):
                            found[node.id] = "defined"
            elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                found[statement.target.id] = "defined"
            elif isinstance(statement, ast.Import | ast.ImportFrom):
                for alias in statement.names:
                    found[alias.asname or alias.name.split(".")[0]] = "imported"
            elif isinstance(statement, ast.If | ast.Try):
                visit(statement.body)
                visit(statement.orelse)
                for handler in getattr(statement, "handlers", []):
                    visit(handler.body)
                visit(getattr(statement, "finalbody", []))

    visit(tree.body)
    return found


def definitions_of(tree: ast.AST, name: str) -> list[int]:
    """The line of every `def` or `async def` called `name`, at any depth."""
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
    )


def spelled_by(node: ast.AST) -> tuple[str | None, ...]:
    """Every name one node spells: a definition, a use, an attribute, a string or an alias."""
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return (node.name,)
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        return (node.attr,)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return (node.value,)
    if isinstance(node, ast.alias):
        return (node.name, node.asname)
    return ()


def mentions_of(tree: ast.AST, name: str) -> list[int]:
    """The line of every place `name` appears: a definition, a use, an attribute or a string."""
    return sorted(getattr(node, "lineno", 0) for node in ast.walk(tree) if name in spelled_by(node))


def calls_to(tree: ast.AST, name: str) -> list[int]:
    """The line of every call made through `name`, bare or as an attribute."""
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name | ast.Attribute)
        and spelled_by(node.func) == (name,)
    )


def modules_under(root: Path) -> dict[str, ast.Module]:
    """Every `.py` file under `root`, parsed, keyed by its path relative to `backend/`."""
    if not root.is_dir():
        pytest.fail(f"{root.relative_to(REPO_ROOT)} is not a directory, so nothing was read.")
    found: dict[str, ast.Module] = {}
    for path in sorted(root.rglob("*.py")):
        name = path.relative_to(BACKEND_ROOT).as_posix()
        found[name] = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    if not found:
        pytest.fail(f"{root.relative_to(REPO_ROOT)} holds no Python module, so nothing was read.")
    return found


# ---------------------------------------------------------------------------
# Controls. A red here means these tests are broken, not the code.
# ---------------------------------------------------------------------------


def test_the_binding_reader_finds_every_way_a_module_binds_a_name() -> None:
    """Defined, assigned, annotated, unpacked, imported: each is a module-level binding.

    **The mutation it kills:** a reader that sees `def` and plain assignment
    only, which reports a cookie constant re-imported into `deps.py` as absent
    from it — the exact shape a half-done move takes. **Its near miss** is the
    second assertion: a name only used, a local, a class attribute and an
    import's original name under an alias are not bindings of the module. **A
    red here means this module is broken, not that the code is.**
    """
    bound = bound_at_module_level(ast.parse(A_BINDING_SAMPLE))
    missing = [name for name in SAMPLE_BOUND if name not in bound]
    assert not missing, f"The reader missed {missing}; it read {bound}."
    extra = [name for name in SAMPLE_NOT_BOUND if name in bound]
    assert not extra, (
        f"The reader counted {extra} as module-level bindings. They are a name only used, a local, "
        "a class attribute and an import's name under its alias."
    )
    assert bound["SAMPLE_IMPORTED"] == "imported" and bound["SAMPLE_ASSIGNED"] == "defined", (
        f"The reader could not tell an import from a definition: {bound}. Criterion 6 says where "
        "a helper lives, so the difference is the whole question."
    )


def test_the_definition_reader_finds_a_nested_copy_and_spares_the_public_name() -> None:
    """A `def _person_of` is found at module level and nested; `def person_of` is not it.

    **The mutation it kills:** a reader of module-level definitions only, which
    misses a copy pasted inside a handler; and a substring match, which counts
    the public helper as a copy of the private one. **A red here means this
    module is broken.**
    """
    tree = ast.parse(A_DEFINITION_SAMPLE)
    assert definitions_of(tree, PRIVATE_HELPER) == [1, 6], (
        f"The reader found `{PRIVATE_HELPER}` at lines {definitions_of(tree, PRIVATE_HELPER)}; the "
        "sample defines it at line 1 and again, nested, at line 6."
    )
    assert definitions_of(tree, PUBLIC_HELPER) == [12], (
        f"The reader found `{PUBLIC_HELPER}` at lines {definitions_of(tree, PUBLIC_HELPER)}; the "
        "sample defines it once, at line 12."
    )


# ---------------------------------------------------------------------------
# The rules.
# ---------------------------------------------------------------------------


def test_no_module_under_the_api_package_defines_a_private_person_of() -> None:
    """R8: the two copies of `_person_of` are deleted.

    **The mutation it kills:** the shared helper added and one or both copies
    left behind, which is the shape that closes the carried entry on paper. **Its
    near miss** is the public `person_of` in `deps.py`, which the reader is shown
    not to count.
    """
    found = {
        name: lines
        for name, tree in modules_under(API_ROOT).items()
        if (lines := definitions_of(tree, PRIVATE_HELPER))
    }
    assert not found, (
        f"`{PRIVATE_HELPER}` is still defined in {found} (module to lines). R8 replaces both copies "
        f"with one public `{PUBLIC_HELPER}` in `{DEPS}`, which the two routers import."
    )


def test_exactly_one_person_of_is_defined_and_it_is_in_api_deps() -> None:
    """R8: one helper exists, in the module that holds what a router needs from the request.

    **The mutation it kills:** the helper defined in one of the routers and
    imported by the other, which leaves a router importing from a router; and a
    second definition added later under the public name. **Its near miss** is a
    module importing `person_of`, which is a use and not a definition.
    """
    found = {
        name: lines
        for name, tree in modules_under(APP_ROOT).items()
        if (lines := definitions_of(tree, PUBLIC_HELPER) + definitions_of(tree, PRIVATE_HELPER))
    }
    assert list(found) == [DEPS] and len(found[DEPS]) == 1, (
        f"`{PUBLIC_HELPER}` (or its private spelling) is defined at {found} (module to lines). "
        f"Criterion 6 is one helper, and R8 puts it in `{DEPS}` as `{PUBLIC_HELPER}(claims)`."
    )


@pytest.mark.parametrize("router", FORMER_DEFINERS)
def test_each_former_copy_holder_calls_the_shared_person_of(router: str) -> None:
    """R8: the callers are moved — each router that held a copy now uses the shared one.

    **The mutation it kills:** a router whose copy is deleted along with the
    only call to it, its reads rewritten some other way — the copy gone and the
    behaviour forked rather than shared. **Its near miss** is the import line on
    its own: a router that imports the helper and never calls it is not using
    it, so a call is what is required.
    """
    calls = calls_to(parsed(router), PUBLIC_HELPER)
    assert calls, (
        f"`backend/{router}` makes no call to `{PUBLIC_HELPER}`. It held a copy of "
        f"`{PRIVATE_HELPER}` until E5.1-03, and R8 moves its callers onto the one in `{DEPS}`."
    )


def test_the_dead_lti_login_cookie_is_named_nowhere_in_the_application() -> None:
    """R9: `LTI_LOGIN_COOKIE` is deleted — its definition and its `__all__` entry both.

    Read as every mention, a string included, because `__all__` names it as a
    string and a definition deleted with the `__all__` entry left behind is an
    export of nothing. **The mutation it kills:** the constant deleted and the
    string left in `__all__`, or the other way round. **Its near miss** is
    `OIDC_LOGIN_COOKIE`, a different name the reader does not count.
    """
    found = {
        name: lines
        for name, tree in modules_under(APP_ROOT).items()
        if (lines := mentions_of(tree, DEAD_COOKIE))
    }
    assert not found, (
        f"`{DEAD_COOKIE}` is still named in {found} (module to lines). Nothing reads it — the LTI "
        "door carries its handshake in the server-side `state` — and R9 deletes it."
    )


@pytest.mark.parametrize("name", WEB_DOOR_COOKIE_HALF)
def test_the_web_doors_cookie_helper_is_not_bound_in_api_deps(name: str) -> None:
    """R9, the leaving half: `deps.py` neither defines nor re-imports the web door's cookie.

    A re-import is refused as firmly as a definition: a name `deps.py` still
    exports is a name its callers go on importing from there, and the move is
    then a copy with an alias. **The mutation it kills:** the helper copied into
    `auth.py` and left in `deps.py`, or moved and re-imported back. **Its pair**
    is the next test, which requires the same name to be defined in `auth.py`.
    """
    bound = bound_at_module_level(parsed(DEPS))
    assert name not in bound, (
        f"`backend/{DEPS}` still binds `{name}` ({bound[name]}). R9 moves the web door's cookie "
        f"half to `{AUTH}`; the role gates, the CSRF check, the landing tail and the door pages "
        "are what stay."
    )


@pytest.mark.parametrize("name", WEB_DOOR_COOKIE_HALF)
def test_the_web_doors_cookie_helper_is_defined_in_api_auth(name: str) -> None:
    """R9, the arriving half: the web door's cookie helpers are defined in `auth.py`.

    Defined, not imported: an import from `deps.py` would mean the helper never
    moved. **The mutation it kills:** the helper deleted from `deps.py` and
    defined nowhere, which the leaving half alone would read as done. **Its
    pair** is the test above.
    """
    bound = bound_at_module_level(parsed(AUTH))
    assert bound.get(name) == "defined", (
        f"`backend/{AUTH}` binds `{name}` as {bound.get(name)!r}, not as a definition of its own. "
        "R9 moves the web door's cookie helpers there, with the cookie half of `deps.py`'s module "
        "docstring."
    )
