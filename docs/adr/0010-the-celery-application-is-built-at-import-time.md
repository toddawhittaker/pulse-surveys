# 0010 — The Celery application is built at import time, at module level

**Status:** Accepted
**Date:** 2026-08-13
**Tickets:** E0-03

## Context

E0-03 stands up the job runtime: a Celery application, a worker, and a beat
scheduler. [SPEC §13](../SPEC.md) puts them in `backend/app/jobs/` and §7.2 runs
each as its own container. Neither says when the application object is built or
how the process finds it, which is construction rather than behaviour.

[ADR 0006](0006-settings-lifetime.md) decided the same question for FastAPI and
decided it the other way: `Settings()` is built inside `create_app()`, there is
no module-level application, and configuration failure lands in one startup
rather than at import of whichever module reached `app.config` first. That
record left this ticket's half explicitly open — "later entry points construct
their own, and this record does not say how" — so the question arrives here
already framed, and answering it differently needs a reason better than
convenience.

The reason is mechanical. `celery -A app.jobs.celery_app worker` resolves the
application through `celery.app.utils.find_app`, which imports the module and
looks for an attribute named `app`, then one named `celery`, then scans the
module for a `Celery` instance. Every one of those is an attribute lookup on an
imported module. **There is no form of `-A` that calls a factory**, and the
worker, beat, and the `celery inspect ping` health check all reach the
application that way. A `make_celery()` that has to be called is an application
none of the three can use.

## Decision

`app/jobs/celery_app.py` builds `Settings()` at import time and assigns a
module-level `celery_app` from it. The broker, the result backend, and the
timezone are read from that object; nothing in the module is a literal.

The attribute is named `celery_app` rather than `app`, because `app` is this
project's import root and a module global by that name reads as the package to
anyone skimming the file. `find_app` reaches it by its third route, the module
scan — verified by running `celery -A app.jobs.celery_app inspect ping` against
the container, not by reading the function.

The consequence ADR 0006 warned about is accepted here and is not mitigated: a
missing or malformed variable now fails at *import* of `app.jobs.celery_app`.
In this entry point that is the right place for it. The import happens inside
the worker's own bootstrap, one frame below the command that started it, and the
container exits non-zero with `ConfigurationError` naming the variable. There is
no earlier moment to fail in: unlike a web application, a worker has no build
step between import and run.

## Alternatives rejected

**A factory, `make_celery() -> Celery`, matching `create_app()`.** The
symmetric choice, and the one that would keep one rule in the codebase instead
of two. Rejected because `celery -A` cannot call it: the worker, beat, and the
health check would each need a wrapper module that calls the factory and assigns
the result at module level — which is this decision with an extra file, and a
second place for the configuration to be read differently.

**A module-level application built from a lazily-read `Settings`.** Build the
`Celery` object at import but defer the environment read, through Celery's
`config_from_object` with a callable or a `@app.on_configure` hook, so that a
missing variable fails at first use rather than at import. Rejected because it
buys nothing and costs the failure's location: "first use" for a worker is the
first task it executes, which is minutes or days after the container reported
healthy, and the failure then looks like a broken task rather than a broken
deployment. Failing at import is failing early, which is what this codebase
wants everywhere except the §3.3 classifier.

**A `Celery` instance per worker process, built in a `worker_process_init`
signal.** Rejected as a solution to a problem nobody has: there is one
configuration per container, the settings object is small, and prefork children
inherit it through the fork.

## Consequences

- **Importing `app.jobs.celery_app` reads the environment.** Anything that
  imports it — the API container enqueuing a task, a test, a future management
  command — needs a configured environment, or the import raises
  `ConfigurationError`. That is already true of every entry point in this
  project; what is new is that it happens at import rather than at a call.
- **Two rules, and the difference between them has to stay legible.** The
  FastAPI application is built by a factory and the Celery application is not.
  The module docstring in `celery_app.py` says why and points here, because the
  next person to touch it will otherwise read the asymmetry as an oversight and
  tidy it.
- **Tests must import the module against the environment they mean.** Reading
  the environment at import time means `sys.modules` holds the result for the
  rest of the session, so a test that sets `REDIS_URL` and imports afterwards
  gets whatever the first importer got. `tests/conftest.py` already carries an
  `import_app_module` fixture that drops `app.*` from `sys.modules` for exactly
  this reason.
- **This record covers the Celery entry point only.** Alembic (E0-04) runs
  outside any application too and is not decided here. Its lifetime question is
  different — a migration runs once, under a different database identity
  ([ADR 0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md))
  — and guessing at it now would put a shape in the way of whoever finds out.
  *(E0-04 has since answered it, and answered it away from `Settings` entirely:
  `migrations/env.py` reads three environment variables directly and builds no
  `Settings` at all, because a migration needs a database and none of the rest
  of the §6.3 surface —
  [ADR 0012](0012-the-migration-environment-builds-its-own-superuser-connection.md).
  The engine `app.db` exposes is module-level like the Celery application, for
  the reasons in [ADR 0013](0013-the-database-session-is-synchronous.md).)*
