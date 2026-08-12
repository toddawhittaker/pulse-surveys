# E0-04 — Database session and Alembic baseline

**ID:** E0-04
**Branch:** `e0/db-session-alembic`
**Depends on:** E0-02

## Context

Every schema ticket after this one adds tables; this one builds the machinery
they add tables *to*. It also turns on the migration-drift gate, which is what
makes "a model was edited without a migration" a build failure rather than a
deploy-time surprise.

Read first: SPEC §8, §13, and the `migration-drift` job in
`.github/workflows/ci.yml`, which runs `alembic upgrade head && alembic check`.

## Scope

- `backend/app/db.py` — SQLAlchemy 2.0 engine and session factory, a declarative
  `Base`, and a FastAPI dependency yielding a session per request.
- `backend/alembic.ini` and `backend/migrations/` with `env.py` wired to
  `Base.metadata` and to `Settings.database_url`, so autogenerate sees the ORM.
- One baseline migration that creates nothing, establishing the revision chain.
- A naming convention for constraints and indexes on `Base.metadata`, so
  autogenerate produces stable names and `alembic check` does not churn.
- `tests/conftest.py` with a testcontainers Postgres fixture, migrations applied
  once per session, and a transaction-rollback fixture for per-test isolation.
- Enable the CI `migration-drift` job and the `test` job, removing both
  tolerance flags. The invariant checker keeps `--allow-empty` until E0-10 adds
  the first §4.1 invariant.
- `make migrate` works against the running stack.

## Out of scope

- Any actual table (E0-05 onward).
- Identity-separated views (E0-10) — those ship as migrations, but the pattern
  is established there, not here.
- Seed data (E0-17).

## Acceptance criteria

- [ ] `alembic upgrade head` succeeds against an empty database, and
      `alembic check` reports no drift.
- [ ] Deliberately adding a column to a model without a migration makes
      `alembic check` fail. Verify this by hand before merge, then revert.
- [ ] The testcontainers fixture starts Postgres, applies migrations, and tears
      down cleanly; a test that writes a row does not leak into the next test.
- [ ] Constraint names in the generated migration follow the configured
      convention rather than Postgres defaults.
- [ ] The CI `test` and `migration-drift` jobs run for real and pass.

## Definition of done

**Tests apply.** This ticket *is* largely test infrastructure. Include one
integration test proving the session dependency opens and closes a transaction,
and one asserting the rollback fixture isolates writes.

**Docs apply.** `README.md` gains "how to create a migration" — the autogenerate
command and the rule that a model change without a migration fails CI.

**AI evals do not apply.**

**Accessibility does not apply.**

**Security review applies but is light.** Confirm the database URL is never
logged and that the engine does not echo SQL in a non-development environment.
