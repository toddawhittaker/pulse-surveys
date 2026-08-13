# 0006 — Settings are built inside `create_app()` and hung on `app.state`

**Status:** Accepted
**Date:** 2026-08-12
**Tickets:** E0-01

## Context

E0-01 introduces `app.config.Settings`, a `pydantic-settings` object read
entirely from the environment ([SPEC §6.3](../SPEC.md)). The spec says what the
settings *are* and where their values come from. It says nothing about how many
of them exist in a process, when they are constructed, or how a handler reaches
one, and those are not questions it should answer — they are construction.

They are also genuinely contestable, because FastAPI has a well-known idiom for
exactly this and it is not what this ticket does. The common form is a
module-level accessor behind a cache:

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()

@app.get("/healthz")
def healthz(settings: Annotated[Settings, Depends(get_settings)]) -> ...:
```

It appears in FastAPI's own documentation, it reads well, and it is the shape a
reasonable engineer arrives at first. Choosing against it without a record
means the argument gets had again in the next ticket, and probably differently.

What forced the choice here was a test. `tests/unit/test_healthz.py` builds an
application and asserts `/healthz` reports the configured environment, and then
a second test sets `ENVIRONMENT` to a value no implementation would hardcode,
builds another application, and asserts the new value comes back. That is two
applications with two configurations in one process.

A cache keyed on nothing at all — which is what `@lru_cache` on a zero-argument
function is — makes the second application report the first one's environment.
This was measured rather than assumed: putting the idiom above into
`create_app()` turns
`test_healthz_reports_the_environment_it_was_configured_with` red, returning the
`development` placeholder the earlier test had already cached. Note the shape of
that failure. Nothing raises, nothing says "stale"; a health endpoint simply
reports the wrong environment, which is also how it would fail in a deployment.

## Decision

`Settings()` is constructed inside `create_app()` and attached to the
application as `app.state.settings`. There is no module-level `settings`
object, no `get_settings()` accessor, and no cache anywhere in the path.
Handlers that need configuration read it from `request.app.state.settings`.

The lifetime is therefore the application's: one settings object per
`create_app()` call, built at build time rather than at import time, discarded
with the application that owns it.

Constructing it at build time rather than at import time matters on its own.
`app/main.py` has no module-level application object for the same reason: a
missing environment variable then fails one startup, loudly and in a stack
frame that names it, rather than at import of whichever module first reached
`app.config`.

**This record covers E0-01 and nothing beyond it.** See the consequences.

## Alternatives rejected

**A cached `get_settings()` dependency (`@lru_cache`).** The idiom above.
Rejected because the cache has no key, so "the settings" becomes a
process-global whether or not it is written as a global — and the health
endpoint test builds two applications with different environments in one
process. Making it work would mean giving the cache a key nothing naturally
supplies, or clearing it between tests, which is a fixture every future test
author has to know about and a global whose reset is load-bearing. The `Depends`
ergonomics it buys are real but small: this application has one settings object
and handlers can reach it through the request they already have.

**A module-level `settings = Settings()` singleton.** Rejected for the two
problems above at once, plus a third: it moves configuration failure to import
time. A missing `DATABASE_URL` then raises during `import app.config`,
wherever that first happens — inside a test collection, inside a Celery worker
bootstrap, inside a migration — and the traceback points at an import rather
than at a startup.

**Passing `Settings` as an argument to `create_app(settings=...)`.** Not
rejected on the merits so much as deferred: it is strictly more flexible and it
would suit a test that wants to inject a configuration directly. Nothing needs
it yet — the tests configure through the environment, which is also how
production configures — and `create_app()` with no arguments is what
`uvicorn app.main:create_app --factory` calls. Adding the parameter later is a
compatible change; it can be made when something wants it.

**Reading `os.environ` at each use site.** Rejected because it is the thing
`Settings` exists to replace: no typing, no single documented surface, no
`.env.example` sync test, and no one place where a missing variable is refused.

## Consequences

- **Anything holding a `Settings` needs a route to the application object.** In
  a request handler that is `request.app.state.settings`, which is always
  available. Code that is not a request handler does not have one, and that is
  the constraint this decision imposes.
- **Later entry points construct their own, and this record does not say how.**
  E0-03 (Celery workers) and E0-04 (Alembic) both run outside any FastAPI
  application and cannot read `app.state`. Each will build a `Settings()` of its
  own. Whether they should share a mechanism, and what it should be, is
  deliberately left open here rather than settled for tickets that do not exist
  yet: a worker's lifetime and a migration's lifetime are not obviously the same
  as a web application's, and guessing now would put a shape in the way of
  whoever finds out. This is the open question a future reader should expect to
  find unanswered, not an omission.
- **`app.state` is untyped.** Starlette's `State` accepts any attribute, so
  `request.app.state.settings` typechecks as `Any` and a typo in the attribute
  name is an `AttributeError` at request time rather than a mypy error. The
  application is small enough that one attribute is not worth a typed wrapper;
  if `app.state` grows several entries, that judgement is worth revisiting.
- **Building settings per application is not free, and does not need to be.**
  It reads the environment and a `.env` file once per `create_app()` call. That
  happens once per process in production and once per test that asks for it.
- **A cache is now a change with a reason to argue about, not a tidy-up.**
  Reintroducing one has to answer the two-applications-in-one-process case
  first. That is the point of writing this down.
