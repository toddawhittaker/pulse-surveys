"""What the engine may say out loud — ticket E0-04, definition of done.

"**Security review applies but is light.** Confirm the database URL is never
logged and that the engine does not echo SQL in a non-development environment."

Both of those are properties of `backend/app/db.py` at import time, so neither
needs a database: `create_engine` does not connect, and what is under test is
what the module says while building the engine, not what it says while using it.

Two shapes of leak, and they are worth separating because the fix for one does
not touch the other.

**The URL.** `DATABASE_URL` carries the application role's password (ADR 0008
builds it from `DB_APP_PASSWORD`). A line like `logger.info("connecting to %s",
settings.database_url)` at import puts that password in the container startup
log, which SPEC §10 rules out and which CI itself prints on failure
(`docker compose logs` in the `docker` job). `tests/unit/test_config_settings.py`
holds the same property for `Settings`; this is the module that consumes it.

**The SQL.** `echo=True` writes every statement and every bound parameter to
stdout. In development that is a debugging tool. In any other environment it is
a copy of every row the application reads or writes, student comments included
(§4, §10 — no student PII in logs), in a stream a deployment ships to whatever
aggregates its logs.

Nothing here asserts that the engine *does* echo in development. The definition
of done asks for one direction only, and an implementation that never echoes
satisfies it; requiring the other direction would invent a feature the ticket
does not ask for. `docs/MISTAKES.md` entry 2's rule applies as written — assert
the forbidden state, not the permitted one.

The engine is found rather than named, in the spirit of `celery_application_in`
in `tests/conftest.py`: E0-04 says `db.py` holds "a SQLAlchemy 2.0 engine and
session factory" and does not say what either is called.
"""

import logging
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest

DB_MODULE = "app.db"

DATABASE_URL_VARIABLE = "DATABASE_URL"
ENVIRONMENT_VARIABLE = "ENVIRONMENT"
LOG_LEVEL_VARIABLE = "LOG_LEVEL"

# Obvious fakes, long and unlikely-looking so that any fragment appearing in a
# log line is unambiguously a leak and not a coincidence. Named `...CREDENTIAL`
# rather than `...PASSWORD` because ruff's S105 flags the latter as a hardcoded
# password; `tests/unit/test_config_settings.py` made the same choice.
FAKE_DATABASE_CREDENTIAL = "fake-db-pw-Qr8XtLm3Vn6ZbKwP"
CREDENTIAL_BEARING_DATABASE_URL = (
    f"postgresql+psycopg://pulse_app:{FAKE_DATABASE_CREDENTIAL}@db:5432/pulse"
)

# Length of the contiguous run of a password that counts as leaked. Checking for
# the whole password is not enough: a truncating formatter can print all but one
# character of a secret and still not contain the exact string.
LEAK_FRAGMENT_LENGTH = 8

# Environments that are not development, each paired with a log level, because
# the two plausible ways to derive `echo` fail on different rows. `echo =
# settings.environment != "production"` passes the first row and echoes in
# staging; `echo = settings.log_level == "DEBUG"` passes the staging rows and
# echoes in a production deployment that has been turned up to debug a problem
# — which is exactly when it is most likely to be turned up.
NON_DEVELOPMENT_ENVIRONMENTS = (
    ("production", "INFO"),
    ("production", "DEBUG"),
    ("staging", "DEBUG"),
)


def engine_in(module: ModuleType) -> Any:
    """The SQLAlchemy engine a module exposes, whatever it is named.

    Falls back to the bind of a session factory, since a module can reasonably
    keep the engine private and expose only the factory that uses it. An
    `AsyncEngine` is unwrapped to the engine it drives, so the assertions below
    read the same configuration either way.

    Returns `None` rather than asserting, so the test does the asserting.
    """
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import sessionmaker

    def unwrapped(value: Any) -> Any:
        inner = getattr(value, "sync_engine", None)
        return inner if isinstance(inner, Engine) else value

    for name in sorted(vars(module)):
        candidate = unwrapped(getattr(module, name, None))
        if isinstance(candidate, Engine):
            return candidate

    for name in sorted(vars(module)):
        candidate = getattr(module, name, None)
        if isinstance(candidate, sessionmaker):
            bind = unwrapped(candidate.kw.get("bind"))
            if isinstance(bind, Engine):
                return bind
    return None


def leaked_fragments(text: str, secret: str, size: int = LEAK_FRAGMENT_LENGTH) -> list[str]:
    """Every contiguous run of `secret` of length `size` that appears in `text`."""
    windows = (secret[start : start + size] for start in range(len(secret) - size + 1))
    return sorted({window for window in windows if window in text})


def import_database_module(
    import_app_module: Callable[[str], ModuleType | None],
) -> ModuleType:
    """Import `app.db` against the environment the test has just set."""
    module = import_app_module(DB_MODULE)
    if module is None:
        pytest.fail(
            f"`{DB_MODULE}` does not exist. E0-04 ships it at `backend/app/db.py` (SPEC §13) "
            "with the SQLAlchemy 2.0 engine and session factory."
        )
    return module


@pytest.mark.parametrize(("environment", "log_level"), NON_DEVELOPMENT_ENVIRONMENTS)
def test_the_engine_does_not_echo_sql_outside_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    import_app_module: Callable[[str], ModuleType | None],
    environment: str,
    log_level: str,
) -> None:
    """The definition of done's second security item.

    `echo=True` writes every statement and every bound parameter to stdout. From
    E0-05 those parameters are survey answers and free-text comments, so an
    echoing engine in a deployed environment is a copy of the confidential
    material in §4 sitting in the log stream — where §4.1's whole apparatus of
    views and grants does not reach.

    Parametrized over an environment *and* a log level because the two obvious
    one-line derivations of `echo` each pass some of these rows and fail
    others. One test per row, so the failure names the combination that echoes.
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, environment)
    monkeypatch.setenv(LOG_LEVEL_VARIABLE, log_level)

    module = import_database_module(import_app_module)
    engine = engine_in(module)

    assert engine is not None, (
        f"`{DB_MODULE}` exposes no SQLAlchemy engine and no session factory bound to one, so "
        "there is nothing here whose `echo` could be checked. E0-04 ships both."
    )
    assert not engine.echo, (
        f"The engine echoes SQL with {ENVIRONMENT_VARIABLE}={environment!r} and "
        f"{LOG_LEVEL_VARIABLE}={log_level!r}. Every statement and every bound parameter goes "
        "to the log — survey answers and free-text comments included from E0-05 — which is "
        "the one place the §4.1 views and grants cannot reach."
    )


def test_building_the_engine_does_not_log_the_database_url(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    import_app_module: Callable[[str], ModuleType | None],
) -> None:
    """The definition of done's first security item.

    Import time is where this goes wrong: a module that builds an engine out of
    `Settings` is the natural place to write "connecting to ..." and the value
    to hand it is right there. That line runs once per container start, and the
    startup log is the most-read log a deployment has — CI prints it on every
    `docker` job failure.

    **The guard before the assertion is the point.** "The password does not
    appear" is true of a module that never reads `DATABASE_URL` at all, of one
    that failed to build an engine, and of a capture that collected nothing;
    that is `docs/MISTAKES.md` entry 3 in its usual clothes. So the engine is
    first required to be holding the very credential being searched for. If it
    has it and the log does not, the property is real.

    Fragments rather than the whole password, for the reason
    `tests/unit/test_config_settings.py` gives: a truncating formatter can print
    all but one character of a secret and still not contain it as a substring.
    """
    monkeypatch.setenv(DATABASE_URL_VARIABLE, CREDENTIAL_BEARING_DATABASE_URL)
    caplog.set_level(logging.DEBUG)

    module = import_database_module(import_app_module)
    engine = engine_in(module)

    assert engine is not None, (
        f"`{DB_MODULE}` exposes no SQLAlchemy engine and no session factory bound to one, so "
        "nothing here ever held the URL and this test would report no leak from a module "
        "that does not connect at all."
    )
    configured = engine.url.password
    revealed = (
        configured.get_secret_value() if hasattr(configured, "get_secret_value") else configured
    )
    assert revealed == FAKE_DATABASE_CREDENTIAL, (
        f"The engine was built with the password {revealed!r}, not the one this test put in "
        f"{DATABASE_URL_VARIABLE}. It is connecting somewhere else, so finding no leak here "
        "says nothing about the credential the application actually uses."
    )

    captured = capsys.readouterr()
    for where, written in (
        ("the log records emitted while importing the module", caplog.text),
        ("standard output", captured.out),
        ("standard error", captured.err),
    ):
        fragments = leaked_fragments(written, FAKE_DATABASE_CREDENTIAL)
        assert not fragments, (
            f"The database password reached {where}: {fragments}. That stream is the "
            "container startup log, which CI prints on failure and a deployment ships to "
            "whatever aggregates its logs (SPEC §10 — secrets via environment or secret "
            f"store). What was written was:\n{written}"
        )
