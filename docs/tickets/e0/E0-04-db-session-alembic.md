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

## Decide first: which identity runs migrations

E0-02 stopped the application connecting as the Postgres superuser, because a
superuser bypasses every grant and every row-level security policy and can reach
a shell in the database container — see
[ADR 0001](../../adr/0001-identity-separation-by-database-role.md) and the E0-02
security review. `DATABASE_URL` now points at an application role created by
`scripts/db-init` that holds **`CONNECT` and nothing else**.

That role deliberately cannot create a table:

```
ERROR:  permission denied for schema public
```

So `alembic upgrade head` cannot run as `Settings.database_url`, and this ticket
cannot simply grant it `CREATE` — ADR 0001 rules that out too ("runtime roles
must not own tables"), and doing so quietly would undo E0-02's fix.

This ticket has to choose, and record the choice:

- **A separate migration identity.** A second URL — a `MIGRATION_DATABASE_URL`
  setting, or the existing `DB_SUPERUSER` credentials — used by Alembic and by
  nothing else. This is the direction ADR 0001 points, and it makes the owner of
  the tables different from the role that queries them, which is what E0-10's
  three-role scheme needs to already be true.
- **Grant the application role what it needs and no more**, per object rather
  than on the schema, once the tables exist. Cheaper now, and it puts the
  runtime role back in the business of owning things.

Whichever wins, `scripts/db-init/01-application-role.sh` is where a grant would
be added, and an ADR is warranted: the spec does not settle it and a reasonable
engineer would argue either way.

Two smaller consequences of E0-02 land here as well:

- The `migration-drift` job's own `services.postgres` block still declares
  `POSTGRES_USER: postgres` and autogenerates as a superuser, so it would not
  notice a permission problem the real stack has. Consider starting the Compose
  `db` service instead, which would also delete the second pinned image
  reference that [ADR 0007](../../adr/0007-container-images-pinned-by-tag-and-digest.md)
  records as maintained by hand.
- The testcontainers fixture provisions its own Postgres and will need whatever
  role split this ticket settles on, or its tests will pass under privileges
  production does not have.

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
