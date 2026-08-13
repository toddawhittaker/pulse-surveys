"""Fixtures shared by the test suite.

The tests under `tests/unit/` for ticket E0-01 are written from the ticket's
acceptance criteria, not from the implementation. Where a criterion needs a
name the ticket does not spell — an environment variable, a JSON key — the
choice is made once, in a named constant, and marked as the test's choice so it
is cheap to change.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"


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
