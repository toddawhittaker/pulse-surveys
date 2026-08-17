"""Swapping the provider library touches one file — ticket E0-13.

E0-13's sixth acceptance criterion: "The gateway interface is small enough that
swapping the provider library touches one file — state the file count in the pull
request." SPEC §7.4 says why the ticket cares: `pydantic-ai` "is young and
fast-moving, so pin it and keep the gateway interface thin enough that replacing
it is a day's work."

Half of that criterion is a sentence in a pull request and cannot be asserted.
The half that can is the half that decides it: **how many modules under
`backend/app/` name the provider library at all.** One is the criterion met; two
is a replacement that touches two files however thin the interface reads, and
nothing but a sweep will ever say so — an import added to `app/jobs/tasks.py`
during E2 is a diff nobody would question.

The sweep parses each module rather than searching its text, so a library named
in a comment or in a docstring is not counted as a dependency and a
`from … import …` is counted the same as an `import …`.

**Two guards, because this asserts an absence** (`docs/MISTAKES.md` entry 3). The
sweep has to find some Python to read, and it has to find the provider library
imported *somewhere* — a repository where nothing imports one satisfies "exactly
one module does" the way an empty set satisfies anything, and that is precisely
the state before this ticket lands.

**What is deliberately left open.** Which library is used is §7.4's call rather
than this file's: it names `pydantic-ai` as the intended implementation, and a
gateway that speaks the OpenAI wire protocol through a plain HTTP client is a
defensible different choice that would want an ADR. So the sweep looks for any of
a small set of provider libraries and reports what it found; the failure message
says what to do if the answer is "none of them, deliberately".
"""

import ast
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "backend" / "app"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

# E0-13's scope and SPEC §13 both spell the file: "`backend/app/ai/gateway.py` —
# provider-agnostic client against an OpenAI-compatible base URL".
GATEWAY_PATH = APP_DIR / "ai" / "gateway.py"

# The libraries that would make a module a place the provider is reached from,
# mapped to the distribution that supplies each. **This suite's choice** of set;
# §7.4 names only the first, and the others are here so that a deliberate
# different choice fails as "the wrong file imports it" rather than as "nothing
# imports anything".
PROVIDER_LIBRARIES = {
    "pydantic_ai": "pydantic-ai",
    "openai": "openai",
    "anthropic": "anthropic",
    "litellm": "litellm",
}

# A module certainly under `backend/app/`, so a sweep that read nothing says so
# instead of reporting a clean tree. E0-12 shipped it and this ticket builds on
# it.
SWEEP_CANARY = APP_DIR / "ai" / "contracts.py"


def imported_roots(path: Path) -> set[str]:
    """The top-level packages one module imports, parsed rather than searched."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as failure:  # pragma: no cover - a broken module fails the ruff gate first
        pytest.fail(f"{path} could not be parsed: {failure}")

    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def app_modules() -> list[Path]:
    """Every Python module under `backend/app/`."""
    if not APP_DIR.is_dir():
        return []
    return sorted(path for path in APP_DIR.rglob("*.py") if "__pycache__" not in path.parts)


def test_exactly_one_module_reaches_the_provider_library() -> None:
    """Criterion 6, as far as a test can reach it: one file names the provider library.

    The wrong implementation this catches is not a bad gateway — it is a good one
    with a second caller. A task module that imports the library to build its own
    client, a job that constructs one for a batch run, a test helper shipped
    inside `app/`: each is one import, each looks harmless in its own diff, and
    together they are the day's work in §7.4 becoming a week's.

    It is also the enforcing half of the single-shot boundary's shape. §7.4 says
    "All model calls go through one internal `AIGateway`", and "one internal
    gateway" is a claim about where the client is constructed rather than about
    how the code reads.
    """
    modules = app_modules()
    assert modules, (
        f"There are no Python modules under {APP_DIR}, so this test swept nothing and would "
        "report the provider library as confined whatever the truth is."
    )
    assert SWEEP_CANARY in modules, (
        f"{SWEEP_CANARY} is not among the {len(modules)} modules this sweep found. E0-12 shipped "
        "it and E0-13 builds against it, so a sweep that misses it is reading the wrong tree."
    )

    importers: dict[Path, list[str]] = {}
    for path in modules:
        found = sorted(imported_roots(path) & set(PROVIDER_LIBRARIES))
        if found:
            importers[path] = found

    assert importers, (
        f"No module under {APP_DIR} imports any of {sorted(PROVIDER_LIBRARIES)}, so nothing here "
        "reaches a model provider and this test would report the library confined to one file "
        "without there being a file. E0-13's scope: '`backend/app/ai/gateway.py` — "
        "provider-agnostic client against an OpenAI-compatible base URL', and SPEC §7.4 names "
        "`pydantic-ai` as the intended implementation. If this gateway deliberately speaks the "
        "wire protocol through a plain HTTP client instead, that is a construction decision the "
        "spec does not settle and a reasonable engineer could differ on — it wants an ADR, and "
        "`PROVIDER_LIBRARIES` in this file is what changes with it."
    )

    found = {str(path.relative_to(REPO_ROOT)): names for path, names in importers.items()}

    assert sorted(importers) == [GATEWAY_PATH], (
        f"The modules under `backend/app/` that reach a model provider library are {found}, "
        f"rather than `{GATEWAY_PATH.relative_to(REPO_ROOT)}` alone. "
        "E0-13's sixth criterion: 'The gateway interface is small enough that swapping the "
        "provider library touches one file.' SPEC §7.4: 'All model calls go through one internal "
        "`AIGateway`', and the library is 'young and fast-moving, so pin it and keep the gateway "
        "interface thin enough that replacing it is a day's work.' Every extra importer is "
        "another file that replacement has to touch."
    )


def test_the_provider_library_the_gateway_imports_is_pinned() -> None:
    """SPEC §7.4: "it is young and fast-moving, so pin it".

    `CLAUDE.md` states the general rule — "Pin dependency versions and commit
    lockfiles. No floating ranges, no unpinned tool versions in CI" — and §7.4
    states it again for this one library, which is the signal that a caret range
    here is a different kind of risk from a caret range anywhere else: the
    gateway's whole design premise is that the library will change under it.

    Driven off what the sweep above actually found rather than off a name written
    here, so the pin asserted is the pin for the library in use. Two copies of
    "which library is this" could otherwise drift, and the one nobody edits is the
    one in the test.
    """
    assert GATEWAY_PATH.is_file(), (
        f"{GATEWAY_PATH} does not exist. E0-13's scope names the file and SPEC §13 places it: "
        "'`ai/gateway.py` — provider-agnostic client (OpenAI-compatible base_url)'."
    )

    used = sorted(imported_roots(GATEWAY_PATH) & set(PROVIDER_LIBRARIES))
    assert used, (
        f"{GATEWAY_PATH} imports none of {sorted(PROVIDER_LIBRARIES)}, so there is no pin to "
        "check. The test above owns that failure and says what to do if the choice was "
        "deliberate."
    )

    document = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    dependencies = document.get("project", {}).get("dependencies", [])
    assert dependencies, (
        f"{PYPROJECT_PATH} declares no project dependencies, so this test has nothing to look "
        "through and would report the library as unpinned whatever the truth is."
    )

    for root in used:
        distribution = PROVIDER_LIBRARIES[root]
        pinned = [
            entry
            for entry in dependencies
            if isinstance(entry, str) and entry.replace("_", "-").startswith(f"{distribution}==")
        ]
        assert pinned, (
            f"`{distribution}` is imported by {GATEWAY_PATH.name} and is not pinned with `==` in "
            f"{PYPROJECT_PATH}; the dependencies are {dependencies}. SPEC §7.4: '`pydantic-ai` is "
            "the intended implementation … it is young and fast-moving, so pin it.' CLAUDE.md: "
            "no floating ranges, and Dependabot proposes upgrades through the same gates as "
            "anything else."
        )
