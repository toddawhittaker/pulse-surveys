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

**`echo` is not what keeps the parameters out, and E0-37 item 1 is that
correction.** `Connection.__init__` sets `self._echo` from
`logger.isEnabledFor(INFO)` on `sqlalchemy.engine.Engine`, not from the `echo`
flag — so with that logger configured at INFO **by name**, which a `dictConfig`
plausibly does, `echo=False` still writes every statement and every bound
parameter. Measured on the pinned SQLAlchemy 2.0.52. From E0-05 those parameters
are survey answers and free-text comments, material §10 keeps out of logs and
§4.1's views and grants do not reach. What closes it is `hide_parameters=True`
outside development, plus the `WARNING` pin `backend/alembic.ini` already applies
on the migration side — so the assertion that carries the property is a captured
log around a marker statement, and `not engine.echo` is kept below only as
E0-04's own smaller criterion, labelled as such.

**The way out is a second question, and the security review of this batch is
where it was measured.** `hide_parameters` covers what goes *to* the database.
SQLAlchemy's cursor logs `Row %r` for every row it hands *back*, at DEBUG, with
no `hide_parameters` check on that path — and `pin_sqlalchemy_logging` pinned the
parent logger `sqlalchemy`, which does not reach a child that a `dictConfig` has
given an explicit level of its own. So `sqlalchemy.engine` at DEBUG, set before
import, left the statements' parameters hidden and their answers written out in
full. The pin covers both loggers now, `backend/alembic.ini` having pinned
`qualname = sqlalchemy.engine` on the migration side all along, and
`test_no_result_row_reaches_the_log_outside_development` is what holds it.

**One residual is left open deliberately, and is written down rather than
implied away.** A logging configuration applied *after* `app.db` is imported wins
over the pin, because the last writer does, and nothing in the engine's options
covers returned rows the way `hide_parameters` covers parameters. That is an
operator action with the same standing as setting `echo=True` in a deployment; it
is recorded here and in ADR 0013, and no test in this file claims otherwise.

Nothing here asserts that the engine *does* echo in development, or that a bound
parameter or a row *is* visible there. The definition of done asks for one
direction only, and an implementation that never echoes and never shows either
satisfies it; requiring the other direction would invent a feature no ticket asks
for. `docs/MISTAKES.md` entry 2's rule applies as written — assert the forbidden
state, not the permitted one. The two controls that do assert a marker is
*present* build their own engines — one with no options at all, one with
`hide_parameters=True` — so each says something about this file's log capture and
nothing about what `app.db` chose.

The engine is found rather than named, in the spirit of `celery_application_in`
in `tests/conftest.py`: E0-04 says `db.py` holds "a SQLAlchemy 2.0 engine and
session factory" and does not say what either is called.
"""

import logging
import sys
from collections.abc import Callable, Iterator
from types import ModuleType
from typing import Any

import pytest

DB_MODULE = "app.db"
CONFIG_MODULE = "app.config"

DATABASE_URL_VARIABLE = "DATABASE_URL"
ENVIRONMENT_VARIABLE = "ENVIRONMENT"
LOG_LEVEL_VARIABLE = "LOG_LEVEL"

# The two names E0-37 item 1 adds to `app.db`, written here in one place because
# every assertion about the SQL half goes through them.
#
#   engine_options(settings) -> dict   the `create_engine` keyword arguments
#   pin_sqlalchemy_logging(settings)   pins `sqlalchemy` **and** its child
#                                      `sqlalchemy.engine` to WARNING outside
#                                      development, and is called where the
#                                      engine is built
#
# Both are fetched with `getattr` and reported by a failing assertion rather than
# imported at module scope: a missing deliverable has to arrive as a red test
# naming it, not as a collection error that takes the other tests here down with
# it and says nothing about which one is the deliverable.
ENGINE_OPTIONS_FUNCTION = "engine_options"
LOGGING_PIN_FUNCTION = "pin_sqlalchemy_logging"

# The name of the constant that says which environment is the development one.
# Read out of `app.config` rather than spelled here — E0-37 item 2 makes that the
# single definition site, and a third copy in a test would be the same defect
# wearing a test's clothes.
DEVELOPMENT_ENVIRONMENT_CONSTANT = "DEVELOPMENT_ENVIRONMENT"

# The two loggers this module configures and restores, and both of them matter.
# `sqlalchemy.engine` is the one whose effective level decides whether
# `Connection` logs a statement and its parameters, and whether the cursor logs
# the rows it returns; `sqlalchemy` is its parent, which decides that too for as
# long as the child has no level of its own.
#
# **`backend/alembic.ini` pins the child**, and it is worth reading its section
# header twice: the section is called `[logger_sqlalchemy]`, and its `qualname`
# is `sqlalchemy.engine`. An earlier version of this comment said the migration
# side pinned the parent, from the section name — which is the record this batch
# keeps citing (`docs/MISTAKES.md` entry 1) arriving in a test file, and it
# mattered, because the parent is the one a pin can apply and still leave the
# rows going out.
SQLALCHEMY_LOGGER = "sqlalchemy"
SQLALCHEMY_ENGINE_LOGGER = "sqlalchemy.engine"

# An engine that needs no server and no driver beyond the standard library, so
# the SQL half stays a unit test. What is under test is what the *options* do to
# the log, and that is a property of SQLAlchemy's logging path rather than of any
# particular database.
IN_MEMORY_URL = "sqlite://"

# The value carried into the database as a bound parameter and looked for in the
# captured log. Long and unlikely-looking for the reason
# `FAKE_DATABASE_CREDENTIAL` above is, and it stands in for what a real bound
# parameter holds from E0-05 on: a survey answer, or a student's free-text
# comment.
#
# It is a *parameter* and never part of the statement text — `SELECT :probe`
# compiles to `SELECT ?`, so a log line containing this value can only have got
# it from the parameter list. A test that interpolated it into the SQL would go
# red against a perfectly hidden parameter.
PARAMETER_MARKER = "marker-Qb7ZxLm4VtR9NsWd"
PARAMETER_STATEMENT = "SELECT :probe"
PARAMETER_NAME = "probe"

# The second marker, and it travels a different way on purpose: in as a bound
# parameter, and back out as a **result row**. `hide_parameters` covers what goes
# in and says nothing about what comes back — SQLAlchemy's cursor logs `Row %r` at
# DEBUG with no `hide_parameters` check at all — so a value hidden on the way to
# the database is written in full on the way back.
#
# What comes back is the material §4 is about: from E0-05 a row read out of this
# database is a survey answer or a student's free-text comment, and over the Care
# connection it is a revealed identity (§6.2). The column below is called
# `comment` because that is what it stands in for.
#
# None of the three statements contains the marker, so a log line holding it took
# it from the parameter list or from a row — and both tests that use this hide
# parameters, which leaves the row.
ROW_MARKER = "row-marker-Wd5TnQx8Jm2VpLc"
ROW_TABLE_STATEMENT = "CREATE TABLE probe (comment TEXT)"
ROW_INSERT_STATEMENT = "INSERT INTO probe (comment) VALUES (:comment)"
ROW_SELECT_STATEMENT = "SELECT comment FROM probe"
ROW_PARAMETER_NAME = "comment"

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


def import_configuration_module(
    import_app_module: Callable[[str], ModuleType | None],
) -> ModuleType:
    """Import `app.config` against the environment the test has just set."""
    module = import_app_module(CONFIG_MODULE)
    if module is None:
        pytest.fail(
            f"`{CONFIG_MODULE}` does not exist. E0-01 ships it at `backend/app/config.py` "
            "(SPEC §13) with the `Settings` object every other module reads."
        )
    return module


def settings_now(import_app_module: Callable[[str], ModuleType | None]) -> Any:
    """A `Settings` built from the environment the test has just set."""
    config = import_configuration_module(import_app_module)
    settings_class = getattr(config, "Settings", None)
    assert settings_class is not None, (
        f"`{CONFIG_MODULE}` exposes no `Settings`, so there is nothing to hand the functions "
        "below. E0-01 ships it and every module here reads its fields."
    )
    return settings_class()


def development_environment_name(import_app_module: Callable[[str], ModuleType | None]) -> str:
    """The value of `ENVIRONMENT` that means development, read from its one definition.

    Not spelled in this file. E0-37 item 2 makes `app.config` the single
    definition site precisely so that "outside development" means the same thing
    in `db.py`, in `scripts/seed.py` and in the tests that hold them to it — and
    a literal here would be the fourth copy of the thing that item exists to
    remove.
    """
    config = import_configuration_module(import_app_module)
    name = getattr(config, DEVELOPMENT_ENVIRONMENT_CONSTANT, None)
    assert isinstance(name, str) and name, (
        f"`{CONFIG_MODULE}` exposes no `{DEVELOPMENT_ENVIRONMENT_CONSTANT}` string. E0-37 item 2 "
        "puts that constant beside the `environment` field and has `db.py` and `scripts/seed.py` "
        "import it; `tests/unit/test_development_environment_has_one_definition.py` is the module "
        "that owns the criterion. Everything here that says 'outside development' reads it."
    )
    return name


def forget_the_app_package() -> None:
    """Drop every `app.*` module, so the next import reads the environment set now.

    `import_app_module` does exactly this once, before the test body runs, and its
    docstring says why: a module that builds something out of `Settings` reads the
    environment at import and `sys.modules` keeps the answer.

    One test here has to look a constant up in `app.config` in order to know which
    environment to set, and then import `app.db` against it. Without this, `app.db`
    would import a configuration module that was already loaded — and `app.db`
    builds its engine at import (ADR 0013), so which import wins is the whole
    question that test asks. The fixture restores the interpreter afterwards
    either way.
    """
    for name in [n for n in list(sys.modules) if n == "app" or n.startswith("app.")]:
        sys.modules.pop(name, None)


def named_function(module: ModuleType, name: str, contract: str) -> Any:
    """One of E0-37 item 1's two new names, or a failure quoting what it must be."""
    found = getattr(module, name, None)
    assert callable(found), (
        f"`{DB_MODULE}` exposes no callable `{name}` (it has {sorted(vars(module))}).\n"
        f"  {contract}\n"
        "\n"
        "E0-37 item 1: `echo=False` is not what keeps SQL out of the log, because "
        "`Connection.__init__` reads `logger.isEnabledFor(INFO)` on `sqlalchemy.engine.Engine` "
        "rather than the flag. The fix is `hide_parameters=True` outside development plus the "
        "same `WARNING` pin `backend/alembic.ini` applies on the migration side."
    )
    return found


def statement_log_of(
    options: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> str:
    """What `sqlalchemy.engine` writes while a statement carrying the marker runs.

    The logger is configured **by name**, at INFO, which is the whole scenario:
    that is what a `dictConfig` naming `sqlalchemy` or `sqlalchemy.engine` does,
    and it is the one configuration under which `echo=False` still logs every
    statement and every bound parameter.

    The marker travels as a bound parameter and never as part of the statement,
    so a log line holding it can only have taken it from the parameter list.
    """
    from sqlalchemy import create_engine, text

    caplog.set_level(logging.INFO, logger=SQLALCHEMY_ENGINE_LOGGER)

    try:
        engine = create_engine(IN_MEMORY_URL, **options)
    except TypeError as refused:
        pytest.fail(
            f"`{ENGINE_OPTIONS_FUNCTION}` returned {options!r}, which `create_engine` refused: "
            f"{refused}. E0-37 item 1 describes it as the keyword arguments the engine is built "
            "with — `echo`, `hide_parameters`, `pool_pre_ping` — so whatever it answers has to be "
            "a mapping `create_engine` accepts. A dialect-specific argument belongs beside the URL "
            "it goes with rather than in the answer this test builds a SQLite engine from."
        )

    with engine.connect() as connection:
        connection.execute(text(PARAMETER_STATEMENT), {PARAMETER_NAME: PARAMETER_MARKER})

    return caplog.text


def result_row_log_of(
    options: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> str:
    """What `sqlalchemy.engine` writes while a row carrying the marker is read back.

    **This one sets no logger level, and that is the point of it.**
    `caplog.set_level` configures the logger it is given, so a helper that called
    it would overwrite the very pin under test — the assertion would then be
    about a level this file had just set. The caller owns the levels here, and
    `restored_sqlalchemy_logging` puts them back.

    The marker goes in as a bound parameter and comes back as a result row.
    Reading it back is what makes this a different question from the one
    `statement_log_of` asks: the parameter is hidden by `hide_parameters` and the
    row is not covered by anything, so what is left in the log is the row or
    nothing.
    """
    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(IN_MEMORY_URL, **options)
    except TypeError as refused:
        pytest.fail(
            f"`create_engine` refused {options!r}: {refused}. See the same branch in "
            "`statement_log_of` above — whatever `engine_options` answers has to be a mapping "
            "`create_engine` accepts."
        )

    with engine.connect() as connection:
        connection.execute(text(ROW_TABLE_STATEMENT))
        connection.execute(text(ROW_INSERT_STATEMENT), {ROW_PARAMETER_NAME: ROW_MARKER})
        rows = connection.execute(text(ROW_SELECT_STATEMENT)).all()

    assert [tuple(row) for row in rows] == [(ROW_MARKER,)], (
        f"The round trip did not read the marker back — it read {[tuple(r) for r in rows]}. "
        "Nothing was logged about a row this test never received, so both assertions built on "
        "this helper would be about an empty result rather than about row logging."
    )

    return caplog.text


@pytest.fixture
def restored_sqlalchemy_logging() -> Iterator[None]:
    """Put the level of every logger these tests configure back afterwards.

    `caplog.set_level` restores the one logger it is given, and the pin tests
    below set `sqlalchemy` themselves and then ask `app.db` to change it. Left
    unrestored, a test that pinned the library to `WARNING` would silently decide
    what every later test in the session can see — which is the shape where a
    suite passes or fails on the order it ran in.
    """
    saved = {
        name: logging.getLogger(name).level
        for name in (SQLALCHEMY_LOGGER, SQLALCHEMY_ENGINE_LOGGER)
    }
    try:
        yield
    finally:
        for name, level in saved.items():
            logging.getLogger(name).setLevel(level)


@pytest.mark.parametrize(("environment", "log_level"), NON_DEVELOPMENT_ENVIRONMENTS)
def test_the_engine_does_not_turn_on_sql_echo_outside_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    import_app_module: Callable[[str], ModuleType | None],
    environment: str,
    log_level: str,
) -> None:
    """E0-04's own smaller criterion, and **not** the guard on bound parameters.

    "Confirm ... that the engine does not echo SQL in a non-development
    environment" is E0-04's definition of done, and this is the only thing in the
    repository that asserts it: with nothing here, `echo=True` could be set in a
    production deployment and every gate would stay green (`docs/MISTAKES.md`
    entry 2). So it stays, and what changes is that it no longer stands in for the
    property it cannot see.

    **Read the demotion, not just the assertion.** E0-37 item 1 measured that this
    keeps passing while every statement and every bound parameter is written to
    the log, because `Connection.__init__` takes `self._echo` from
    `logger.isEnabledFor(INFO)` on `sqlalchemy.engine.Engine` rather than from
    this flag. The test that closes that hole is
    `test_no_bound_parameter_reaches_the_log_outside_development` below; this one
    is about log volume in a deployment, which is a smaller and separate thing.

    Parametrized over an environment *and* a log level because the two obvious
    one-line derivations of `echo` each pass some of these rows and fail
    others. One test per row, so the failure names the combination that echoes.

    **The mutation this survives:** `echo=True` unconditionally, or an `echo`
    derived from `LOG_LEVEL`. **The near miss that must stay green:** anything at
    all done with `hide_parameters`, which this deliberately does not read.
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
        f"{LOG_LEVEL_VARIABLE}={log_level!r}. Every statement goes to the log, in a stream a "
        "deployment ships to whatever aggregates it. This is E0-04's criterion; the bound "
        "parameters are a separate property and a separate test."
    )


def test_the_log_capture_sees_a_bound_parameter_when_nothing_is_hiding_it(
    caplog: pytest.LogCaptureFixture,
    restored_sqlalchemy_logging: None,
) -> None:
    """The control for the test below, and the reason its silence can be believed.

    Not a test of `app.db` at all — the engine here is built with no options, so
    nothing in this file's subject can affect the answer. What it establishes is
    that the capture works: `sqlalchemy.engine` configured at INFO **by name**
    really does write bound parameters, and this module's marker really is
    findable in what it writes.

    Without it, `docs/MISTAKES.md` entry 3 in its plainest form — a capture that
    collected nothing, a statement that never ran, a marker that never reached the
    parameter list and a `hide_parameters` that does nothing all report exactly
    the same silence as a correctly hidden parameter, and the test below passes
    against every one of them.

    **A red here is a broken test, not a finding.** It says this module can no
    longer see what it claims to be looking for — SQLAlchemy's logging path
    changed, or the marker stopped travelling as a parameter — and the assertion
    below means nothing until it is green again.
    """
    written = statement_log_of({}, caplog)

    assert written.strip(), (
        "`sqlalchemy.engine` was configured at INFO by name and a statement ran, and nothing at "
        "all was captured. Every assertion about a parameter not appearing in this log is "
        "therefore vacuous, whatever the engine options do."
    )
    assert PARAMETER_MARKER in written, (
        f"The marker this module looks for did not appear in the log of an engine built with no "
        f"options, which is the engine that hides nothing.\n"
        f"  captured: {written}\n"
        "\n"
        "So the search below cannot see a bound parameter even when one is written in full, and "
        "the property it asserts — that no parameter reaches the log outside development — would "
        "pass against an engine that logged every one of them."
    )


@pytest.mark.parametrize(("environment", "log_level"), NON_DEVELOPMENT_ENVIRONMENTS)
def test_no_bound_parameter_reaches_the_log_outside_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    restored_sqlalchemy_logging: None,
    import_app_module: Callable[[str], ModuleType | None],
    environment: str,
    log_level: str,
) -> None:
    """E0-37 item 1's first acceptance criterion, asserted by capturing rather than by reading.

    With `sqlalchemy.engine` at INFO **by name** — which is what a `dictConfig`
    naming the library plausibly does, and the one residual risk two of three
    security passes agreed on — `echo=False` writes the statement *and its bound
    parameters*. From E0-05 those parameters are survey answers and free-text
    comments: material SPEC §10 keeps out of logs, in the one place §4.1's views
    and grants do not reach.

    So the assertion is about the log rather than about the flag. A marker value
    goes into the database as a bound parameter and must not come back out in
    anything `sqlalchemy.engine` wrote. Fragments rather than the whole value, for
    the reason `leaked_fragments` gives: a truncating formatter can print all but
    one character and still not contain the exact string.

    The options come from `app.db`, built against a real `Settings` for a real
    non-development environment, so what is under test is the answer the module
    gives rather than a dictionary this file wrote. The engine is SQLite in
    memory, because what those options do to SQLAlchemy's logging path is not a
    property of any particular database and a unit test may not need a server.

    Nothing here says a parameter *is* visible in development. That direction is
    the module docstring's rule and this file's long-standing one — assert the
    forbidden state — and the control above is what keeps the silence meaningful
    without claiming anything about a development engine.

    **The mutation this survives:** drop `hide_parameters` from
    `engine_options`, which leaves `not engine.echo` green above. **The near miss
    that must stay green:** hiding parameters in development too, which is
    stricter than the ticket asks and is nobody's defect.
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, environment)
    monkeypatch.setenv(LOG_LEVEL_VARIABLE, log_level)

    module = import_database_module(import_app_module)
    build_options = named_function(
        module,
        ENGINE_OPTIONS_FUNCTION,
        f"{ENGINE_OPTIONS_FUNCTION}(settings) answers the keyword arguments the engine is built "
        "with, and outside development they include `hide_parameters=True`.",
    )

    settings = settings_now(import_app_module)
    options = build_options(settings)
    written = statement_log_of(dict(options), caplog)

    fragments = leaked_fragments(written, PARAMETER_MARKER)
    assert not fragments, (
        f"A bound parameter reached the log with {ENVIRONMENT_VARIABLE}={environment!r} and "
        f"{LOG_LEVEL_VARIABLE}={log_level!r}: {fragments}.\n"
        f"  engine options: {options!r}\n"
        f"  captured:       {written}\n"
        "\n"
        "`sqlalchemy.engine` was configured at INFO by name, which is all it takes: "
        "`Connection.__init__` reads `logger.isEnabledFor(INFO)` on `sqlalchemy.engine.Engine` "
        "and not the `echo` flag, so `echo=False` hides nothing here. From E0-05 these parameters "
        "are survey answers and free-text comments (SPEC §10, §4.1), and `hide_parameters=True` "
        "outside development is what keeps them out of a stream the deployment ships elsewhere."
    )


def test_the_log_capture_sees_a_result_row_that_hide_parameters_does_not_cover(
    caplog: pytest.LogCaptureFixture,
    restored_sqlalchemy_logging: None,
) -> None:
    """The control for the test below, and the premise of the finding it is written against.

    Two things at once, and the second is why this is not only plumbing.

    It establishes that the capture sees **row** logging: `sqlalchemy.engine` at
    DEBUG really does write `Row %r` for every row read back, and this module's
    row marker is findable in what it writes. Without that, a broken capture and
    a correctly pinned logger report the same silence (`docs/MISTAKES.md` entry
    3), and the assertion below passes against a log full of student comments.

    And it establishes that **`hide_parameters` does not cover a returned row**.
    The engine here is built with `hide_parameters=True` and nothing else, so the
    value cannot have reached the log through the parameter list; none of the
    three statements contains the marker either. What is left is the row. That is
    the whole premise of the security finding this pair exists for — item 1 closed
    the way in and left the way out open — and it is asserted here rather than
    described, because a premise nobody executes is a comment.

    **A red here is a broken test, not a finding.** It says SQLAlchemy's row
    logging has changed shape, or the round trip stopped returning the marker, and
    the assertion below means nothing until it is green again.
    """
    logging.getLogger(SQLALCHEMY_ENGINE_LOGGER).setLevel(logging.DEBUG)

    written = result_row_log_of({"hide_parameters": True}, caplog)

    assert written.strip(), (
        f"`{SQLALCHEMY_ENGINE_LOGGER}` was set to DEBUG by name and a row was read back, and "
        "nothing at all was captured. Every assertion about a row not appearing in this log is "
        "therefore vacuous, whatever the logging pin does."
    )
    assert ROW_MARKER in written, (
        "A value read back out of the database did not appear in the log of an engine with "
        f"`{SQLALCHEMY_ENGINE_LOGGER}` at DEBUG and `hide_parameters=True`.\n"
        f"  captured: {written}\n"
        "\n"
        "Either this file can no longer see row logging — in which case the test below would "
        "pass against an engine that wrote every row — or `hide_parameters` has started covering "
        "returned rows as well as bound parameters, which would make the finding this pair is "
        "written against no longer true. They need different responses, so find out which before "
        "changing anything."
    )


@pytest.mark.parametrize(("environment", "log_level"), NON_DEVELOPMENT_ENVIRONMENTS)
def test_no_result_row_reaches_the_log_outside_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    restored_sqlalchemy_logging: None,
    import_app_module: Callable[[str], ModuleType | None],
    environment: str,
    log_level: str,
) -> None:
    """The child logger has to be pinned too, or the rows go out whatever the parameters do.

    **The finding, measured.** `pin_sqlalchemy_logging` pins the *parent* logger,
    `sqlalchemy`. A `dictConfig` that names the **child**, `sqlalchemy.engine`,
    sets that logger's own level — and an explicit level on a child is not
    something a parent's level can override, so the pin applied at import leaves
    the child exactly where the configuration put it. At DEBUG, SQLAlchemy's
    cursor logs `Row %r` for every row it hands back, with no `hide_parameters`
    check anywhere on that path. So the parameters of a statement are hidden and
    its *answers* are written in full: from E0-05 that is a survey answer or a
    student's free-text comment (SPEC §10, §4.1).

    The child is the logger that matters and there is a precedent for saying so:
    `backend/alembic.ini` pins `qualname = sqlalchemy.engine`, not the parent. So
    the fix pins both, and this test is the one that fails if either goes.

    **The order is the test.** The child is set to DEBUG *before* `app.db` is
    imported, which is the ordinary case the pin is for — a logging configuration
    read at startup, before the application package is imported. A pin that ran
    and pinned only the parent leaves the child at DEBUG and this goes red.

    **What this deliberately does not cover, and it is a residual rather than an
    oversight.** A configuration applied *after* `app.db` is imported wins,
    because the last writer does: something that names `sqlalchemy.engine` at
    DEBUG at that point logs result rows again, and nothing in the engine's
    options covers rows the way `hide_parameters` covers parameters. There is no
    fix for it on this side — it is an operator action equivalent to setting
    `echo=True` in a deployment — and it is recorded as that in this module's
    docstring and in ADR 0013 rather than being quietly implied away here.

    The pair above is what makes this silence mean something: it proves the
    capture sees row logging at all, and that `hide_parameters=True` does not
    suppress it.

    **The mutation this survives:** pin `sqlalchemy` alone, which is what the
    function did when this was written. **The near miss that must stay green:**
    pinning the child by any route — directly, or by pinning every logger under
    `sqlalchemy` — since nothing here reads how the pin is applied.
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, environment)
    monkeypatch.setenv(LOG_LEVEL_VARIABLE, log_level)
    logging.getLogger(SQLALCHEMY_ENGINE_LOGGER).setLevel(logging.DEBUG)

    module = import_database_module(import_app_module)
    build_options = named_function(
        module,
        ENGINE_OPTIONS_FUNCTION,
        f"{ENGINE_OPTIONS_FUNCTION}(settings) answers the keyword arguments the engine is built "
        "with, and outside development they include `hide_parameters=True`.",
    )

    settings = settings_now(import_app_module)
    written = result_row_log_of(dict(build_options(settings)), caplog)

    fragments = leaked_fragments(written, ROW_MARKER)
    assert not fragments, (
        f"A row read back out of the database reached the log with "
        f"{ENVIRONMENT_VARIABLE}={environment!r} and {LOG_LEVEL_VARIABLE}={log_level!r}: "
        f"{fragments}.\n"
        f"  captured: {written}\n"
        "\n"
        f"`{SQLALCHEMY_ENGINE_LOGGER}` was set to DEBUG by name before `{DB_MODULE}` was "
        "imported — a `dictConfig` read at startup does exactly that — and an explicit level on "
        f"the child is not something a pin on `{SQLALCHEMY_LOGGER}` can override. At DEBUG the "
        "cursor logs every row it returns, and no engine option covers that: `hide_parameters` "
        "is about what goes in.\n"
        "\n"
        f"`backend/alembic.ini` pins `qualname = {SQLALCHEMY_ENGINE_LOGGER}` for the migration "
        "side already. Pinning both is what closes this; from E0-05 the rows are survey answers "
        "and free-text comments, and over the Care connection they are revealed identities "
        "(SPEC §10, §4.1, §6.2)."
    )


def hidden_parameters_of(engine: Any) -> Any:
    """Whether this engine hides bound parameters, wherever SQLAlchemy keeps that flag.

    Read off the engine or off its dialect, because which of the two holds it is
    a detail of the library rather than of this project, and a test that guessed
    one would report a version change as a defect in `app.db`. `None` means
    neither has it, which the caller reports as this module needing an update.
    """
    for holder in (engine, getattr(engine, "dialect", None)):
        if holder is None:
            continue
        found = getattr(holder, "hide_parameters", None)
        if found is not None:
            return found
    return None


@pytest.mark.parametrize(("environment", "log_level"), NON_DEVELOPMENT_ENVIRONMENTS)
def test_the_engine_the_module_builds_hides_its_bound_parameters_outside_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    import_app_module: Callable[[str], ModuleType | None],
    environment: str,
    log_level: str,
) -> None:
    """The options have to reach the engine the application actually uses.

    `test_no_bound_parameter_reaches_the_log_outside_development` above asserts
    what `engine_options` *answers*, over an engine this file builds. That is one
    `create_engine` call away from the property anybody cares about: a module can
    ship a correct `engine_options`, never call it, and keep building its engine
    the way it did before, with every assertion in this file green and every bound
    parameter still going to the log. `docs/MISTAKES.md` entry 23 — a validation
    that creates the appearance of a behaviour — and entry 2's rule that a fix
    with nothing asserting it is a convention.

    So this reads the flag off the engine `app.db` built at import, for the
    environment the test configured. The engine is found rather than named, in the
    spirit of the rest of this module.

    **The mutation this survives:** define `engine_options` and build the engine
    without it. **The near miss that must stay green:** building the engine any
    other way that ends with the parameters hidden — the flag is read from the
    engine, not the call.
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, environment)
    monkeypatch.setenv(LOG_LEVEL_VARIABLE, log_level)

    module = import_database_module(import_app_module)
    engine = engine_in(module)

    assert engine is not None, (
        f"`{DB_MODULE}` exposes no SQLAlchemy engine and no session factory bound to one, so "
        "there is nothing here whose parameter handling could be read. E0-04 ships both."
    )

    hidden = hidden_parameters_of(engine)
    assert hidden is not None, (
        "Neither this engine nor its dialect carries a `hide_parameters` flag, so this test "
        "cannot read the property it is about. That is this module needing an update for the "
        "SQLAlchemy in `requirements.txt` — a broken test rather than a finding — and the "
        "captured-log test above is the one that still means something until it is fixed."
    )
    assert hidden is True, (
        f"The engine `{DB_MODULE}` built with {ENVIRONMENT_VARIABLE}={environment!r} and "
        f"{LOG_LEVEL_VARIABLE}={log_level!r} does not hide its bound parameters "
        f"(`hide_parameters` is {hidden!r}).\n"
        "\n"
        "E0-37 item 1: with `sqlalchemy.engine` configured at INFO by name, every statement and "
        "every bound parameter is written whatever `echo` says — and from E0-05 those parameters "
        "are survey answers and free-text comments, which SPEC §10 keeps out of logs. An "
        "`engine_options` that answers correctly and is not used to build this engine leaves the "
        "hole exactly where it was."
    )


@pytest.mark.parametrize(("environment", "log_level"), NON_DEVELOPMENT_ENVIRONMENTS)
def test_importing_the_database_module_pins_the_sqlalchemy_logger_outside_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    restored_sqlalchemy_logging: None,
    import_app_module: Callable[[str], ModuleType | None],
    environment: str,
    log_level: str,
) -> None:
    """The asymmetry E0-37 item 1 names: the migration side is pinned and the application side is not.

    `backend/alembic.ini` already carries `[logger_sqlalchemy] level = WARNING`
    — a section whose `qualname` is `sqlalchemy.engine` — so a deployment that
    configures logging by name gets the parameters of every migration statement
    withheld and the parameters of every application statement written. Item 1's
    fix is the same pin, applied where the engine is built.

    **This test reads the parent, and it is not the whole of the pin.** The
    child, `sqlalchemy.engine`, has to be pinned too, and
    `test_no_result_row_reaches_the_log_outside_development` is what says so: a
    child with a level of its own ignores its parent's, and at DEBUG the cursor
    writes out every row it returns. Both are asserted because either one alone
    can be satisfied while the other is missing.

    **The logger is turned up first, and that is the whole test.** SQLAlchemy
    pins `sqlalchemy` to `WARNING` itself at import when it is `NOTSET`, so
    asserting `WARNING` over an untouched interpreter would pass against a module
    that does nothing at all — `docs/MISTAKES.md` entry 3, in the form where the
    library under test supplies the answer. Setting `DEBUG` before the import is
    what makes the assertion about `app.db`.

    **What this cannot promise, said rather than implied.** A `dictConfig` that
    runs *after* `app.db` is imported wins, because the last writer does. The pin
    closes the ordinary case — a logging configuration read at startup before the
    application package is imported — and the parameter-hiding test above is what
    holds the property when it does not.

    **The mutation this survives:** delete the call from the module body, or make
    it a function nobody calls, or pin the child alone and leave the parent
    where it was. **The near miss that must stay green:** pinning more than these
    two — every logger under `sqlalchemy`, say — which takes nothing away.
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, environment)
    monkeypatch.setenv(LOG_LEVEL_VARIABLE, log_level)
    logging.getLogger(SQLALCHEMY_LOGGER).setLevel(logging.DEBUG)

    module = import_database_module(import_app_module)
    named_function(
        module,
        LOGGING_PIN_FUNCTION,
        f"{LOGGING_PIN_FUNCTION}(settings) pins `{SQLALCHEMY_LOGGER}` and its child "
        f"`{SQLALCHEMY_ENGINE_LOGGER}` to WARNING outside development, and is called where the "
        "engine is built.",
    )

    pinned = logging.getLogger(SQLALCHEMY_LOGGER).level
    assert pinned == logging.WARNING, (
        f"Importing `{DB_MODULE}` with {ENVIRONMENT_VARIABLE}={environment!r} left the "
        f"`{SQLALCHEMY_LOGGER}` logger at {logging.getLevelName(pinned)}, and this test had set it "
        "to DEBUG beforehand — exactly as a deployment's own `dictConfig` would.\n"
        "\n"
        "`backend/alembic.ini` pins that logger to WARNING for the migration side already, so "
        "without this the two halves of one deployment disagree about whether the parameters of a "
        "statement may be written down. From E0-05 those parameters are survey answers and "
        "free-text comments (SPEC §10)."
    )


def test_importing_the_database_module_leaves_the_sqlalchemy_logger_alone_in_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    restored_sqlalchemy_logging: None,
    import_app_module: Callable[[str], ModuleType | None],
) -> None:
    """In development the pin is a no-op, because `echo` is a debugging tool there.

    E0-37 item 1 is explicit that `_echoes_sql` is correct as written and is not
    what changes. A pin applied unconditionally would take the library's own
    loggers down to `WARNING` in development too, and a developer who turned
    `sqlalchemy` or `sqlalchemy.engine` up to see a query would get nothing back
    with no indication why — the fix quietly removing the tool the ticket says to
    keep. Both loggers are checked, because the pin covers both since the
    security review of this batch and an unconditional pin on either is the same
    defect.

    **This passes on the tree as it stands**, which is what it is for: it is the
    near miss beside the pin above, and the two are only worth having together.

    The development environment's name is read from `app.config`, not spelled
    here, for the reason `development_environment_name` gives.

    **The mutation this survives:** pin unconditionally — drop the environment
    check from `pin_sqlalchemy_logging`, or call it before reading the settings.
    **The near miss that must stay green:** any spelling of the check that reads
    the constant, since nothing here looks at how the decision is made.
    """
    development = development_environment_name(import_app_module)
    forget_the_app_package()
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, development)
    for name in (SQLALCHEMY_LOGGER, SQLALCHEMY_ENGINE_LOGGER):
        logging.getLogger(name).setLevel(logging.DEBUG)

    import_database_module(import_app_module)

    moved = {
        name: logging.getLevelName(logging.getLogger(name).level)
        for name in (SQLALCHEMY_LOGGER, SQLALCHEMY_ENGINE_LOGGER)
        if logging.getLogger(name).level != logging.DEBUG
    }
    assert not moved, (
        f"Importing `{DB_MODULE}` with {ENVIRONMENT_VARIABLE}={development!r} moved these "
        f"loggers away from the DEBUG this test had set them to: {moved}.\n"
        "\n"
        "E0-37 item 1 pins them *outside* development and says `_echoes_sql` is correct as "
        "written. A pin that also fires in development takes away the echo the ticket keeps, and "
        "does it silently: the developer who turned the logger up sees nothing and has no way to "
        "tell that the application turned it back down.\n"
        "\n"
        "Both loggers, because the pin covers both — the parent and the child `sqlalchemy.engine` "
        "the security review found unpinned — so a fix applied unconditionally to either one is "
        "the same defect."
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
