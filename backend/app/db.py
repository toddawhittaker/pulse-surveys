"""SQLAlchemy engine, session factory, and the per-request session (SPEC §13).

**The session is synchronous**, and so is the engine. FastAPI is async-native
(§7.1) and this is the choice a reader will want a reason for: the same session
has to serve HTTP handlers and Celery tasks, Celery is synchronous, and
`pylti1p3` is synchronous. One synchronous session factory is one thing to
learn, one thing to mock, and one set of idioms across both entry points. The
cost — handlers that touch the database are written `def` and FastAPI runs them
in its threadpool — and the alternatives are in
docs/adr/0013-the-database-session-is-synchronous.md.

**The engine is built when this module is imported**, from a `Settings()` of its
own, which is what ADR 0010 already does for the Celery application and what
docs/adr/0006-settings-lifetime.md deliberately left open for later entry
points. It is recorded in ADR 0013 rather than assumed.

**`Base` is re-exported here and declared in `app.models.base`.** That module
reads no configuration, so `backend/migrations/env.py` can import the metadata
without importing this one — an `env.py` that imported this module would need
the whole §6.3 configuration surface set before it could run a migration. See
docs/adr/0012-the-migration-environment-builds-its-own-superuser-connection.md.

**Two things this module must never do**, both from E0-04's definition of done,
and `tests/unit/test_db_engine_configuration.py` holds each of them:

* *Log the URL.* `DATABASE_URL` carries the application role's password (ADR
  0008). Import time is where this goes wrong — "connecting to ..." next to the
  engine is a natural line to write, it runs once per container start, and the
  startup log is the most widely read log a deployment has. Nothing here writes
  the URL anywhere. SQLAlchemy does not either: a malformed URL raises
  `ArgumentError("Could not parse SQLAlchemy URL from given URL string")` and an
  unknown dialect raises `NoSuchModuleError` naming only the dialect. Both were
  run against a credential-bearing URL rather than assumed, so no wrapper is
  needed to keep the value out of the traceback.
* *Echo SQL outside development.* `echo=True` writes every statement and every
  bound parameter to stdout. From E0-05 those parameters are survey answers and
  free-text comments, so an echoing engine in a deployed environment copies the
  confidential material §4 protects into the one place §4.1's views and grants
  do not reach.

  **`echo` is not what keeps those parameters out of the log, and E0-37 item 1
  is that correction.** `Connection.__init__` takes `self._echo` from
  `logger.isEnabledFor(INFO)` on `sqlalchemy.engine.Engine`, not from the flag —
  so a deployment whose logging configuration names `sqlalchemy` or
  `sqlalchemy.engine`, which a `dictConfig` plausibly does, gets every statement
  and every bound parameter written with `echo=False`. Measured on the pinned
  SQLAlchemy 2.0.52. The two things that do close it are here: the `WARNING`
  pin `pin_sqlalchemy_logging` applies outside development, which is the pin
  `backend/alembic.ini` has always applied on the migration side, and
  `hide_parameters=True` in `engine_options`, which holds when a later
  configuration turns the logger back up. `_echoes_sql` is correct as written
  and is not what changed.
"""

import logging
from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import DEVELOPMENT_ENVIRONMENT, Settings
from app.models import Base

__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "engine_options",
    "get_session",
    "pin_sqlalchemy_logging",
]

# The logger `backend/alembic.ini` pins on the migration side, and the one whose
# effective level decides whether a `Connection` writes a statement and its
# parameters at all. Pinning the parent covers `sqlalchemy.engine` and everything
# else the library logs under it.
SQLALCHEMY_LOGGER = "sqlalchemy"

# Which environment may see SQL in the log is `app.config`'s to say: the constant
# is declared beside the `environment` field it describes and imported here
# (E0-37 item 2). This module used to carry its own copy, which is two spellings
# of one convention with nothing comparing them — `docs/MISTAKES.md` entry 3.


def _is_development(settings: Settings) -> bool:
    """Whether this process is running on a developer's machine.

    A comparison against a convention rather than against an enumeration
    `Settings` enforces: `ENVIRONMENT` is free-form — **not by SPEC §6.3**, which
    is the admin console's configuration surface and names no environment
    variable — and `.env.example` documents the vocabulary. Anything that is not
    that exact string is a deployment, which is the safe direction for both of
    the rules below.
    """
    return settings.environment == DEVELOPMENT_ENVIRONMENT


def _echoes_sql(settings: Settings) -> bool:
    """Whether the engine may write statements and bound parameters to stdout.

    Both halves are required, and each covers a way the other fails. Keying on
    the environment alone echoes in development for a developer who never asked
    for it; keying on the log level alone echoes in production the moment
    somebody turns the deployment up to DEBUG to investigate an incident — which
    is exactly when the log is being read by the most people and shipped to
    whatever aggregates it.
    """
    return _is_development(settings) and settings.log_level.upper() == "DEBUG"


def engine_options(settings: Settings) -> dict[str, Any]:
    """The keyword arguments the engine is built with, apart from the URL.

    A function rather than a literal in the `create_engine` call because two of
    the three answers depend on the environment, and because a test can then hold
    the options to what they must be without building the application's engine.
    The URL is not here: it is a secret, and the one place it is unwrapped stays
    the call below.

    `hide_parameters=True` outside development is the guard on bound parameters,
    and it is not the same guard as `echo`. It survives a logging configuration
    that names `sqlalchemy.engine` and turns it up to INFO, where `echo=False`
    hides nothing — the module docstring has the mechanism. In development it
    stays off, because a developer who asked for the echo asked for the values in
    it and nothing there is a real student's.
    """
    return {
        "echo": _echoes_sql(settings),
        # From E0-05 a bound parameter is a survey answer or a free-text comment
        # (SPEC §4, §10). Outside development, SQLAlchemy writes the placeholder
        # instead of the value.
        "hide_parameters": not _is_development(settings),
        # A pooled connection can be dead before it is handed out — Postgres
        # restarts, a network drops an idle socket — and without this the first
        # statement of a request fails instead of the pool quietly replacing it.
        # The cost is one round trip per checkout.
        "pool_pre_ping": True,
    }


def pin_sqlalchemy_logging(settings: Settings) -> None:
    """Outside development, hold the `sqlalchemy` logger at WARNING.

    The same pin `backend/alembic.ini` carries as `[logger_sqlalchemy] level =
    WARNING`, applied on the side that serves requests. Without it the two halves
    of one deployment disagree: the parameters of a migration statement are
    withheld and the parameters of an application statement — a survey answer, a
    free-text comment — are written.

    **In development this does nothing at all**, deliberately. `echo` is a
    debugging tool there, and a pin applied unconditionally would take the
    library's own logger down to WARNING for a developer who had just turned it
    up, with no indication of what had done it.

    **What it cannot promise.** A logging configuration read *after* this module
    is imported wins, because the last writer does. This closes the ordinary case
    — a configuration applied at startup before the application package is
    imported — and `hide_parameters` in `engine_options` above is what holds the
    property when it does not.
    """
    if _is_development(settings):
        return
    logging.getLogger(SQLALCHEMY_LOGGER).setLevel(logging.WARNING)


_settings = Settings()

# Before the engine, so that anything SQLAlchemy logs while building one is
# already covered.
pin_sqlalchemy_logging(_settings)

engine = create_engine(
    # `get_secret_value()` is the explicit act ADR 0008's `SecretStr` choice
    # exists to make searchable. It goes no further than this call: the URL is
    # held inside the engine, whose own `repr` masks the password.
    _settings.database_url.get_secret_value(),
    **engine_options(_settings),
)

# The factory, not a session. A session is per unit of work: sharing one across
# requests shares an open transaction, so one request's uncommitted rows become
# visible to another and one request's rollback discards another's work.
SessionLocal = sessionmaker(bind=engine)


def get_session() -> Iterator[Session]:
    """Yield a session for one request, and close it when the request ends.

    `Depends(get_session)` in a router. The `with` block is what makes the
    closing unconditional: a handler that raises leaves the transaction rolled
    back and the connection returned to the pool, and a dependency that yielded
    without one would leak a connection per failed request until the pool
    emptied, a long way from the code that caused it.

    Committing is the caller's job. A session that committed itself at teardown
    would turn every read handler into a write and would commit the half-done
    work of a handler that failed after its first statement.
    """
    with SessionLocal() as session:
        yield session
