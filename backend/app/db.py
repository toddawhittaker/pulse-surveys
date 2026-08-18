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
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import Base

__all__ = ["Base", "SessionLocal", "engine", "get_session"]

# The only environment name that may see SQL in the log. Free-form — but **not by
# SPEC §6.3**, which is where an earlier version of this comment sent the reader.
# That section is the admin console's configuration surface and names no
# environment variable; `ENVIRONMENT` and `healthz` each appear zero times in the
# spec. The vocabulary is documented in `.env.example` and the field is E0-01's.
# So this is a comparison against a convention rather than against an enumeration
# `Settings` enforces; anything that is not this string gets no echo.
DEVELOPMENT_ENVIRONMENT = "development"


def _echoes_sql(settings: Settings) -> bool:
    """Whether the engine may write statements and bound parameters to stdout.

    Both halves are required, and each covers a way the other fails. Keying on
    the environment alone echoes in development for a developer who never asked
    for it; keying on the log level alone echoes in production the moment
    somebody turns the deployment up to DEBUG to investigate an incident — which
    is exactly when the log is being read by the most people and shipped to
    whatever aggregates it.
    """
    return settings.environment == DEVELOPMENT_ENVIRONMENT and settings.log_level.upper() == "DEBUG"


_settings = Settings()

engine = create_engine(
    # `get_secret_value()` is the explicit act ADR 0008's `SecretStr` choice
    # exists to make searchable. It goes no further than this call: the URL is
    # held inside the engine, whose own `repr` masks the password.
    _settings.database_url.get_secret_value(),
    echo=_echoes_sql(_settings),
    # A pooled connection can be dead before it is handed out — Postgres
    # restarts, a network drops an idle socket — and without this the first
    # statement of a request fails instead of the pool quietly replacing it.
    # The cost is one round trip per checkout.
    pool_pre_ping=True,
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
