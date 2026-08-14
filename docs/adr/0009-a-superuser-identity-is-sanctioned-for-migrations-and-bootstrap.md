# 0009 — A superuser identity is sanctioned for migrations and bootstrap

**Status:** Accepted
**Date:** 2026-08-13
**Tickets:** E0-02 (decided here), E0-04, E0-10
**Amends:** [ADR 0001](0001-identity-separation-by-database-role.md) — one
consequence of it, not its decision. ADR 0001's rule that *runtime* roles must
not own tables and must not be superuser is untouched and is the thing this
record exists to protect.

## Context

E0-02's security review found the application connecting to Postgres as the
cluster superuser: `rolsuper=t`, `rolbypassrls=t`, `COPY … FROM PROGRAM 'id'`
returning `uid=999(postgres)`, and a `SELECT` reading straight through a
`FORCE ROW LEVEL SECURITY` deny-all policy. The official Postgres image creates
exactly one role, from `POSTGRES_USER`, and `initdb` makes it a superuser.

The fix added a second role from `/docker-entrypoint-initdb.d` and pointed
`DATABASE_URL` at it. That closed the finding and opened a different question,
because ADR 0001 had already decided the mechanism for roles:

> **Local development gets more setup**: roles are created in migrations so a
> fresh `docker compose up` still works in one command.

and [E0-10](../tickets/e0/E0-10-identity-separated-views.md) scopes "three
database roles, **established as migrations**". Provisioning a role at `initdb`
departs from both.

There is also a circularity that ADR 0001 does not address. Migrations have to
run as *some* role, and that role has to exist before the first migration runs,
so it cannot itself be created by a migration. On the official image the only
role that exists at that moment is the one `initdb` made.

Todd ruled on it:

> "Let's soften our constraint and allow a superuser role in the database to
> simplify things. Update docs accordingly. Only system-level migrations and
> other absolutely necessary tasks will use this role. Day-to-day use will
> continue to be security-scoped."

## Decision

**A superuser identity is permitted, named, and bounded.** Three identities,
each with a stated job:

| Identity | Created by | Used for | Never used for |
|---|---|---|---|
| **Bootstrap / migration** — `DB_SUPERUSER` | `initdb`, from `POSTGRES_USER` | Alembic migrations, creating roles, extensions, and the `views_sql/` grants E0-10 needs | Serving a request. It is not delivered to the application container at all. |
| **Application** — `DB_APP_USER` | `scripts/db-init`, at first start | Everything the running application does. This is what `DATABASE_URL` points at | Owning tables. Running migrations. Anything requiring superuser |
| **E0-10's read roles** | Migrations, unchanged | The identity-separated read paths in SPEC §8 and §4.1 | Unchanged by this record |

**Migrations run as the bootstrap identity.** That answers the question E0-04
was carrying: Alembic uses `DB_SUPERUSER`, not `Settings.database_url`, and the
application role is never granted `CREATE`. *How* the connection is assembled
was left to E0-04 and is
[ADR 0012](0012-the-migration-environment-builds-its-own-superuser-connection.md):
the address comes from `DATABASE_URL`, the identity from `DB_SUPERUSER` and
`DB_SUPERUSER_PASSWORD`.

**What is still forbidden**, and this is the whole of "day-to-day use will
continue to be security-scoped":

- The application must never connect as `DB_SUPERUSER`. `DATABASE_URL` points at
  `DB_APP_USER`, and a unit test asserts the file cannot resolve it to the
  superuser.
- The superuser credential must not reach the application container.
  `docker-compose.yml` blanks `DB_SUPERUSER` and `DB_SUPERUSER_PASSWORD` on
  `api`, because `env_file: .env` would otherwise deliver both.
- ADR 0001 line 71 stands unchanged: runtime roles must not own tables and must
  not be superuser. E0-10 still tests it.

**Who provisions the application role depends on where Postgres comes from**,
and this is what previously had two mechanisms and no owner:

| Where | Provisioned by | Note |
|---|---|---|
| The Compose stack | `scripts/db-init`, via `/docker-entrypoint-initdb.d` | Runs once, on an empty volume |
| `migration-drift` in CI | `scripts/db-init/01-application-role.sh`, run as a job step over TCP | Settled by E0-04 ([ADR 0012](0012-the-migration-environment-builds-its-own-superuser-connection.md)). The same script the stack runs, not a second copy; the job keeps its own `services.postgres` |
| E0-04's testcontainers fixture | `provision_application_role` in `tests/conftest.py` | Settled by E0-04. A container started by testcontainers has no init hook, so the fixture creates the role itself, `NOSUPERUSER` and `CONNECT` only |
| A managed Postgres | The operator | No `initdb` hook exists. Documented in E13's operator guide, with ADR 0001's degradation note |

**E0-10's migration must tolerate a role that already exists.** `.env.example`
defaults `DB_APP_USER=pulse_app`, which is the name E0-10 creates, so on any
volume initialised by this stack that migration would abort with
`role "pulse_app" already exists`. E0-10 owns the fix and its ticket carries it.

## Alternatives rejected

**Keep ADR 0001's constraint and create every role in a migration.** Rejected
because of the circularity above: the migration identity must exist before the
first migration, so at least one role is always provisioned outside migrations.
ADR 0001 did not notice this because no ticket had yet had to run a migration.
Holding the line would also mean the application role holds `CREATE` until the
migration that demotes it runs, which is the finding this record closes.

**Grant the application role `CREATE` so it can run its own migrations.**
Rejected by ADR 0001 line 71 — a runtime role that owns tables bypasses the
grants the whole scheme rests on — and Todd's ruling reaffirms that half rather
than softening it.

**Defer all of it to E0-10.** Rejected because E0-04 opens the first connection
and E0-05 through E0-13 add query-building code and untrusted LTI launches. That
window is exactly the one the security review measured, and it is several
tickets long.

**A non-superuser migration role, owning the schema but not the cluster.**
Genuinely better on paper, and the direction to revisit at E13 when the operator
guide is written. Rejected now because it does not remove the bootstrap role —
something still has to create it — so it adds a third credential and a third
provisioning step to buy a reduction in a privilege that is already confined to
migrations. Todd's ruling says simplify, and this is the thing it simplifies.

## Consequences

- **ADR 0001's "roles are created in migrations" consequence no longer holds**
  for the bootstrap and application pair. It still holds for E0-10's read roles.
  ADR 0001 carries a pointer to this record.
- **There are now two provisioning mechanisms**, and the table above is the only
  thing that says which owns what. If a third environment appears, it needs a
  row, or its Postgres will have no application role and the failure will be an
  authentication error a long way from the cause.
- **A superuser credential exists in `.env`**, and `.env` is one file with two
  readers (ADR 0008). Keeping it out of the application container is therefore a
  per-service override rather than a property of the file, and every service
  that inherits the file needs it. E0-03 brought `worker` and `beat`, and wrote
  the override once instead of three times: `docker-compose.yml` carries the
  shared part of the three application services in an `x-application` anchor
  they all merge, so a service copied from another cannot arrive with the two
  blanking lines dropped. A service written without the anchor still can, which
  is why `tests/unit/test_compose_stack.py` asserts the rule over every service
  declaring `env_file` rather than over a list of names.
- **"The application must not connect as superuser" is now the load-bearing
  rule**, and it is enforced by a test rather than by there being no superuser to
  connect as. That is a weaker guarantee than the one ADR 0001 imagined, and it
  is the cost of the simplification.
- **E13's operator documentation gains a required step.** A managed Postgres has
  no `initdb` hook, so whoever installs Pulse must create the application role by
  hand. ADR 0001 already required documenting the degraded case; this adds a
  second thing to write down.
