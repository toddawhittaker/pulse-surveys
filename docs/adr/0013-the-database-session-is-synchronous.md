# 0013 — The database session is synchronous, and the engine is built at import

**Status:** Accepted
**Date:** 2026-08-13
**Tickets:** E0-04

## Context

E0-04 ships `backend/app/db.py`: an engine, a session factory, and a FastAPI
dependency that yields a session per request. Two questions have to be answered
to write those twelve lines, and neither is answered by the spec.

**Synchronous or asynchronous?** [SPEC §7.1](../SPEC.md) picks FastAPI because
it is "async-native" and SQLAlchemy 2.x because the idioms are current, and
§13 says only `db.py # SQLAlchemy engine/session`. SQLAlchemy 2.0 offers both
shapes over the same `postgresql+psycopg://` URL that `.env.example` already
names, so nothing in the configuration forces the answer. A reasonable engineer
reading "async-native" would reach for `AsyncSession`, and every ticket from
E0-05 onward writes query code against whatever is chosen here, so changing it
later is not a local edit.

**When is the engine built?** [ADR 0006](0006-settings-lifetime.md) builds
`Settings()` inside `create_app()` and rejects a module-level singleton, partly
because it moves configuration failure to import time. It also says explicitly
that later entry points are left open, and
[ADR 0010](0010-the-celery-application-is-built-at-import-time.md) answered the
Celery half the other way. The database is reached from both entry points, so it
cannot simply follow either.

## Decision

**The session is synchronous.** `create_engine`, `sessionmaker`, `Session`, and
a `get_session()` dependency that yields inside a `with` block. Handlers that
touch the database are written `def` rather than `async def`, and FastAPI runs
them in its threadpool.

**The engine and the session factory are module-level, built when `app.db` is
imported**, from a `Settings()` of that module's own — the same shape ADR 0010
chose for Celery, for a related reason: there is no application object for a
Celery task or an Alembic-adjacent script to read `app.state` from, and a
per-request engine would build a connection pool per request, which is the one
thing a pool exists to prevent.

Committing is the caller's job. The dependency opens a session, yields it, and
closes it; it does not commit, and it does not roll back on its own beyond what
closing an uncommitted session already does.

## Alternatives rejected

**`create_async_engine` and `AsyncSession` throughout.** The choice §7.1's
"async-native" points at, and it loses on where the code actually runs. Celery
tasks are synchronous functions, and §7.4 puts classification, summaries and
grade passback in them — all database work. An async session in a Celery worker
means `asyncio.run(...)` at every task boundary, or a second synchronous engine
beside the first, so the project ends up with two session shapes and a rule
about which to use where. `pylti1p3` (§7.1) is synchronous too. The load this
system carries is one institution's weekly survey; the concurrency an async
driver buys is not the constraint, and the second set of idioms is a permanent
cost paid by everyone who writes a query.

**Async in the API, synchronous in the worker.** Honest about the mismatch, and
rejected because it doubles the surface that has to be reviewed for
confidentiality: every read path in §4.1 would exist in two spellings, and
"duplication in confidentiality-critical paths is sometimes correct" is about
keeping identity-separated paths apart, not about writing every query twice.

**A lazily-built engine behind an accessor**, so nothing is constructed at
import. It answers ADR 0006's objection, and it is what a strict reading of that
record would ask for. Rejected on two counts: `tests/unit/
test_db_engine_configuration.py` asserts properties of the engine `app.db`
exposes, which requires one to exist on the module; and a lazy engine moves a
configuration failure from process start to the first request that needs a
database, which is a worse place to find out. The failure this trades away is
already covered — a missing `DATABASE_URL` raises `ConfigurationError` naming the
variable, whether that happens in `create_app()` or at import.

**A session that commits at teardown.** Common, and rejected because it makes
every read handler a write and commits the half-finished work of a handler that
raised after its first statement. A handler that means to write says so.

## Consequences

- **Handlers that use the database are `def`, not `async def`.** FastAPI runs
  those in a threadpool of bounded size, so a slow query holds a thread rather
  than the event loop. That is the trade, and it is the one this system can
  afford; if a future ticket has a genuinely concurrent workload, this record is
  what it has to argue against.
- **Importing `app.db` reads the environment.** Anything that imports it —
  including a test that only wants `Base` — needs `DATABASE_URL` and the rest of
  the required §6.3 surface set. That is why `Base` itself lives in
  `app/models/base.py`, which imports nothing of the sort
  ([ADR 0012](0012-the-migration-environment-builds-its-own-superuser-connection.md)).
- **One engine per process, and its pool is per process.** `app.main` does not
  import `app.db` yet; when a router does, the pool is built at import of the
  first module that reaches it, and a second `create_app()` in the same process
  shares it. That is correct for a pool and different from how `Settings`
  behaves, which is worth knowing before writing a test that expects two
  applications to have two databases.
- **`echo` is derived, not configured.** It is on only when `ENVIRONMENT` is
  `development` *and* `LOG_LEVEL` is `DEBUG`, so turning a production deployment
  up to debug an incident does not turn the statement stream on. There is no
  separate knob, and adding one would be adding a way to get this wrong.
- **`echo` is not what keeps survey answers out of the log**, and the bullet
  above used to say that it was. `Connection.__init__` takes `self._echo` from
  `logger.isEnabledFor(INFO)` on `sqlalchemy.engine.Engine` rather than from the
  flag, so a deployment whose logging configuration names `sqlalchemy` or
  `sqlalchemy.engine` — which a `dictConfig` plausibly does — gets every
  statement and every bound parameter written with `echo=False`. E0-37 item 1
  measured that on the pinned SQLAlchemy 2.0.52 and added the two things that do
  hold §4 and §10 here: `pin_sqlalchemy_logging`, which applies outside
  development the same `WARNING` pin `backend/alembic.ini` already had on the
  migration side, and `hide_parameters=True` in `engine_options`, which still
  holds if a later configuration turns that logger back up.
