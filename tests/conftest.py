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
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
BASE_COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
OVERRIDE_COMPOSE_PATH = REPO_ROOT / "docker-compose.override.yml"
COMPOSE_PATHS = (BASE_COMPOSE_PATH, OVERRIDE_COMPOSE_PATH)

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


def load_compose(path: Path) -> dict[str, Any]:
    """Parse one Compose file on its own, with no override merged over it.

    Reading the files separately is deliberate and `docker compose config` is
    not a substitute: it merges the override back in, which hides the one
    property `tests/unit/test_compose_stack.py` exists to check.

    Returns an empty mapping when the file is absent, so a test reports a failed
    assertion naming the missing deliverable rather than a fixture error.
    """
    if not path.is_file():
        return {}
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return document if isinstance(document, dict) else {}


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
