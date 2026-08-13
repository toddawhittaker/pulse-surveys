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

## Settled before you start: migrations run as the superuser identity

This was an open question during E0-02 and is not one any more.
[ADR 0009](../../adr/0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)
decides it: **Alembic connects as `DB_SUPERUSER`, not as
`Settings.database_url`.**

The reason it needed deciding: E0-02 stopped the application connecting as the
Postgres superuser, so `DATABASE_URL` now points at an application role that is
granted `CONNECT` and deliberately cannot create a table —

```
ERROR:  permission denied for schema public
```

— and this ticket must not grant it `CREATE` to work around that.
[ADR 0001](../../adr/0001-identity-separation-by-database-role.md) line 71 still
forbids a runtime role owning tables, and ADR 0009 reaffirms that half
explicitly while sanctioning the superuser for migrations.

So this ticket needs a second database URL for Alembic, distinct from
`Settings.database_url`, built from `DB_SUPERUSER` and `DB_SUPERUSER_PASSWORD`.
Whether that is a new `Settings` field, an Alembic-only environment variable, or
something `env.py` assembles is a construction choice this ticket makes — but
*which identity* is no longer open, and no ADR is needed for that part.

Three consequences of E0-02 land here as well:

- **The `migration-drift` job provisions no application role.**
  `scripts/db-init` runs only where the Compose `initdb` hook exists, and
  `services.postgres` has no such hook. ADR 0009's provisioning table names this
  job as E0-04's to settle: give it the role, or start the Compose `db` service
  instead — the second would also delete the duplicate pinned image reference
  that [ADR 0007](../../adr/0007-container-images-pinned-by-tag-and-digest.md)
  records as maintained by hand.
- **The testcontainers fixture has the same gap** and needs the same answer, or
  its tests pass under privileges production does not have.
- The job currently autogenerates as `postgres`, a superuser, which is now the
  correct identity for migrations — but it should use the same *database* shape
  the stack deploys, application role included, or `alembic check` cannot see a
  grant problem.

## Scope

- Pin the `psycopg` driver package. E0-01 shipped `SQLAlchemy` and `alembic`
  without it, and both `.env.example` and the `migration-drift` job already name
  a `postgresql+psycopg://` URL — so nothing can open a connection until this
  ticket adds the driver. Raised by the E0-01 security review.
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
