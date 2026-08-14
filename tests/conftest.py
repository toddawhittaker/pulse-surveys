"""Fixtures shared by the test suite.

The tests under `tests/unit/` for tickets E0-01 and E0-02 are written from those
tickets' acceptance criteria, not from the implementation. Where a criterion
needs a name the ticket does not spell — an environment variable, a JSON key —
the choice is made once, in a named constant, and marked as the test's choice so
it is cheap to change.

`.env` has two readers from E0-02 onwards: `app.config.Settings` and Compose.
The helpers below parse both sides of that, and they parse the Compose files
once, here, so that two test modules cannot end up disagreeing about what a
Compose file says.

E0-03 adds two fixtures of a different kind — `import_app_module` and
`celery_application_in`. They are here for the same reason as the parsers: the
unit tests and the integration test both need them, and two copies of a rule
about how a module is imported, or about where a Celery application is found,
could drift apart and leave the two suites checking different things.
"""

import importlib
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
BASE_COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
OVERRIDE_COMPOSE_PATH = REPO_ROOT / "docker-compose.override.yml"
COMPOSE_PATHS = (BASE_COMPOSE_PATH, OVERRIDE_COMPOSE_PATH)
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# Compose interpolation. The alternatives are ordered so that `$$` is consumed
# first and registers nothing, which matters: the `$$POSTGRES_USER` in the `db`
# health check reaches the container as a literal `$POSTGRES_USER` and is
# expanded by the shell inside it, out of the environment Compose has already
# built. Compose never looks that name up in `.env`, so counting it would let a
# health check vouch for an entry nothing supplies.
#
# `${NAME}`, `${NAME:-default}`, `${NAME:?error}`, `${NAME:+alt}` and the bare
# `$NAME` all read NAME, so the name is taken and the rest of the expression is
# not parsed.
COMPOSE_INTERPOLATION = re.compile(
    r"\$\$|\$\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)|\$(?P<bare>[A-Za-z_][A-Za-z0-9_]*)"
)


def strip_inline_comment(value: str) -> str:
    """Remove a trailing ` # ...` comment, matching dotenv and Compose behaviour.

    A `#` that is not preceded by whitespace is part of the value, which is how
    `docker compose --env-file` and `python-dotenv` both read it.
    """
    if value[:1] in {"'", '"'}:
        quote = value[0]
        closing = value.find(quote, 1)
        return value[1:closing] if closing != -1 else value[1:]
    head, separator, _ = value.partition(" #")
    return head.rstrip() if separator else value


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse dotenv text into an ordered mapping of variable name to value."""
    entries: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        entries[name.strip()] = strip_inline_comment(value.strip())
    return entries


def load_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML file into a mapping.

    Returns an empty mapping when the file is absent or holds something other
    than a mapping, so a test reports a failed assertion naming the missing
    deliverable rather than a fixture error. Every test that consumes one of
    these asserts it is non-empty first, because "nothing in this file is wrong"
    is true of a file that could not be read.
    """
    if not path.is_file():
        return {}
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return document if isinstance(document, dict) else {}


def load_compose(path: Path) -> dict[str, Any]:
    """Parse one Compose file on its own, with no override merged over it.

    Reading the files separately is deliberate and `docker compose config` is
    not a substitute: it merges the override back in, which hides the one
    property `tests/unit/test_compose_stack.py` exists to check.
    """
    return load_yaml(path)


def interpolated_variables(node: Any) -> set[str]:
    """Every environment variable name a parsed Compose document interpolates.

    Walks the parsed document rather than the file text, and that is the point.
    A parser has already discarded the comments, so a `${DB_NAME}` that someone
    commented out stops counting as a reader at the moment it stops being one.
    Scanning raw text would let a commented-out interpolation go on vouching for
    an `.env.example` entry that nothing supplies.

    Names are uppercased, matching how `test_env_example_sync.py` compares them.
    """
    found: set[str] = set()
    if isinstance(node, str):
        for match in COMPOSE_INTERPOLATION.finditer(node):
            name = match.group("braced") or match.group("bare")
            if name:
                found.add(name.upper())
    elif isinstance(node, dict):
        for key, value in node.items():
            found |= interpolated_variables(key)
            found |= interpolated_variables(value)
    elif isinstance(node, list):
        for item in node:
            found |= interpolated_variables(item)
    return found


@pytest.fixture
def base_compose_path() -> Path:
    """Where the base Compose file must live (SPEC §13). Asserted by the test, not here."""
    return BASE_COMPOSE_PATH


@pytest.fixture
def base_compose() -> dict[str, Any]:
    """`docker-compose.yml` parsed alone, with no override merged in."""
    return load_compose(BASE_COMPOSE_PATH)


@pytest.fixture
def override_compose_path() -> Path:
    """Where the development override lives. Asserted by the test, not here."""
    return OVERRIDE_COMPOSE_PATH


@pytest.fixture
def override_compose() -> dict[str, Any]:
    """`docker-compose.override.yml` parsed alone, with no base file under it.

    Added in E0-03, after a reviewer found that nothing read this file at all
    while `worker` and `beat` configuration had moved into it. Parsed on its own
    for the same reason as the base file: the merged view is what every dynamic
    check already sees, and the questions worth asking here are about what this
    file says by itself.

    YAML anchors are resolved by the parser, so a service that merges
    `<<: *development-source` arrives here holding those keys. That is what makes
    a rule about services reach a shared anchor without this fixture knowing
    anchors exist.
    """
    return load_compose(OVERRIDE_COMPOSE_PATH)


@pytest.fixture
def ci_workflow_path() -> Path:
    """Where the CI workflow lives. Asserted by the test, not here."""
    return CI_WORKFLOW_PATH


@pytest.fixture
def ci_workflow() -> dict[str, Any]:
    """`.github/workflows/ci.yml`, parsed rather than grepped.

    A regex over the text cannot tell a job service's `image:` from any other
    line that spells the same word, and it keeps passing against a workflow
    whose shape has changed underneath it — which is the failure the test that
    uses this exists to make impossible.

    One quirk to know before adding anything that reads a top-level key here:
    PyYAML implements YAML 1.1, so the workflow's `on:` parses to the boolean
    `True` rather than to the string `"on"`. Nothing currently needs it.
    """
    return load_yaml(CI_WORKFLOW_PATH)


@pytest.fixture
def compose_read_variables() -> set[str]:
    """Every variable the Compose files read out of `.env`, uppercased.

    Deliberately asserts nothing, and the direction of that choice matters here.
    An empty set makes the test that consumes it *stricter* rather than weaker —
    it falls back to requiring a `Settings` field — so a Compose file that has
    gone missing or stopped parsing cannot quietly turn an assertion into a
    vacuous pass.
    """
    found: set[str] = set()
    for path in COMPOSE_PATHS:
        found |= interpolated_variables(load_compose(path))
    return found


@pytest.fixture
def interpolated_variables_in() -> Callable[[Any], set[str]]:
    """Hand `interpolated_variables` to a test that needs it on one service.

    `compose_read_variables` above answers "what does the whole stack read", and
    a rule about one service holding one credential needs the same question
    asked of one subtree. The same walker answers both, so the two cannot end up
    disagreeing about what counts as reading a variable — `$$` escaped, defaults
    and error forms unwrapped, commented-out interpolations already discarded by
    the parser.
    """
    return interpolated_variables


@pytest.fixture
def env_example_path() -> Path:
    """Where `.env.example` must live (SPEC §13). Asserted by the test, not here."""
    return ENV_EXAMPLE_PATH


@pytest.fixture
def documented_env() -> dict[str, str]:
    """Every variable documented in `.env.example`, with its placeholder value.

    Deliberately asserts nothing: a missing `.env.example` yields an empty
    mapping, so the test that cares reports a failed assertion rather than a
    fixture error. Tests that could pass vacuously on an empty mapping assert it
    is non-empty themselves.
    """
    if not ENV_EXAMPLE_PATH.is_file():
        return {}
    return parse_dotenv(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def import_app_module() -> Iterator[Callable[[str], ModuleType | None]]:
    """Import an `app.*` module against the environment the test has just set.

    A module that builds something out of `Settings` reads the environment once,
    at import time, and `sys.modules` then keeps the result for the rest of the
    session. So a test that sets `REDIS_URL` and imports `app.jobs.celery_app`
    gets the value it set only if nothing imported that module earlier — and if
    something did, the test passes or fails for a reason it did not choose,
    which is `docs/MISTAKES.md` entry 3 in its purest form. Every `app.*` module
    is therefore dropped from `sys.modules` before the test body runs, and the
    set that was there is put back afterwards, so the interpreter is left as it
    was found.

    The returned callable answers `None` for a module that does not exist, so a
    test reports a failed assertion naming the missing deliverable rather than a
    collection error — the same choice `load_yaml` makes above, for the same
    reason. An `ImportError` raised *inside* a module that does exist propagates
    untouched: a module that is broken and a module that was never written need
    different fixes, and a test must not report them as the same thing.
    """
    saved = {
        name: module
        for name, module in list(sys.modules.items())
        if name == "app" or name.startswith("app.")
    }
    for name in saved:
        sys.modules.pop(name, None)

    def import_module(name: str) -> ModuleType | None:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as exc:
            absent = exc.name
            if absent is not None and (name == absent or name.startswith(f"{absent}.")):
                return None
            raise

    try:
        yield import_module
    finally:
        for name in [n for n in list(sys.modules) if n == "app" or n.startswith("app.")]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


@pytest.fixture
def celery_application_in() -> Callable[[ModuleType], Any]:
    """Find the Celery application a module exposes, whatever it is named.

    This mirrors what `celery -A <module>` itself does — `celery.app.utils.
    find_app` looks for an attribute called `app`, then one called `celery`,
    and failing both scans the module for a `Celery` instance — because the
    worker and beat services reach the application that way and the E0-03 ticket
    names no attribute. Pinning a name here would turn the ticket's silence into
    this test suite's decision.

    What is *not* left open is that the application has to be reachable at module
    level: a factory that has to be called is not something `-A` can use, so a
    module that exposes only one answers `None` here and the test that asked
    fails saying so.

    Returns `None` rather than asserting, so the test does the asserting.
    """
    from celery import Celery

    def find(module: ModuleType) -> Any:
        for name in ("app", "celery", "celery_app"):
            candidate = getattr(module, name, None)
            if isinstance(candidate, Celery):
                return candidate
        for name in sorted(vars(module)):
            candidate = getattr(module, name, None)
            if isinstance(candidate, Celery):
                return candidate
        return None

    return find


@pytest.fixture
def configured_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    documented_env: dict[str, str],
) -> dict[str, str]:
    """A process environment that satisfies every documented variable.

    The working directory is moved to an empty temporary directory first, so a
    developer's own `.env` in the repository root cannot supply a value that the
    test believes it removed.
    """
    monkeypatch.chdir(tmp_path)
    for name, value in documented_env.items():
        monkeypatch.setenv(name, value)
    return dict(documented_env)
