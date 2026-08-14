# 0012 — The migration environment builds its own superuser connection

**Status:** Accepted
**Date:** 2026-08-13
**Tickets:** E0-04
**Amends:** [ADR 0008](0008-env-has-two-readers-and-the-database-credential-is-split.md) —
its "two readers" count, not its decision. `.env` now has three.

## Context

[ADR 0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)
settled *which identity* runs migrations: `DB_SUPERUSER`, never the role
`DATABASE_URL` points at, which is granted `CONNECT` and cannot create a table.
It deliberately left three things to E0-04, and this record is those three.

**How `env.py` learns that connection.** The ticket named three candidates: a
new `Settings` field, an Alembic-only environment variable, or something
`env.py` assembles.

**Who provisions the application role where there is no `initdb` hook.** ADR
0009's provisioning table has a row for CI's `migration-drift` job and a row for
the testcontainers fixture, and both said "nothing yet".

**What `env.py` imports to autogenerate against.** Not obviously a decision at
all until the shape of `app/db.py` is fixed: the tests require an engine on that
module at import time, so importing it constructs a full `Settings()` — six
required variables, five of which have nothing to do with a schema.

[SPEC §13](../SPEC.md) names `backend/alembic.ini`, `backend/migrations/` and
`backend/app/db.py` and says nothing about how any of them is wired.

## Decision

**The address comes from `DATABASE_URL`; the identity comes from
`DB_SUPERUSER` and `DB_SUPERUSER_PASSWORD`.** `migrations/env.py` parses
`DATABASE_URL` for the driver, host, port and database, replaces the username
and password with the bootstrap pair, and builds its own engine:

```python
make_url(address).set(username=..., password=...)
```

One variable says *where* the database is — the same one every other part of the
system uses, so there is no second address to keep in step — and the pair says
who may change its shape. No new variable is introduced anywhere.

**The metadata comes from `app.models`, never from `app.db`.** `Base` and the
constraint naming convention live in `app/models/base.py`, which reads no
configuration; `app.db` re-exports `Base` so the application still writes
`from app.db import Base`. Importing `app.models` imports every model module,
which is what puts their tables on the metadata autogenerate compares against.

**`env.py` reads `.env` itself**, through `python-dotenv`, with
`override=False`. That makes it the third reader of that file, and amends ADR
0008's count. The precedence ADR 0008 records is preserved: the process
environment wins, and the file fills what it leaves unset.

**CI's `migration-drift` job runs `scripts/db-init/01-application-role.sh`**
against its `services.postgres` container, over TCP, with the same variables the
Compose `db` service passes it. The job then connects `DATABASE_URL` to
`pulse_app` and hands `env.py` the superuser pair separately, so the gate runs
against the role shape a deployment has. **The testcontainers fixture provisions
the same two roles** — that half lives in `tests/conftest.py`, which the ticket's
test author wrote.

**The job keeps its own `services.postgres` image reference.** ADR 0007 left
E0-04 to reconsider starting the Compose `db` service instead, which would
delete the duplicated pin. It stays: `tests/unit/test_image_pins_agree.py`
asserts that both documents name a Postgres image *and* that the two agree, so
removing the workflow's copy makes that test fail on an empty set — and the
guard against silent drift is worth more than one hand-maintained line.

## Alternatives rejected

**A new `Settings` field**, `alembic_database_url` or similar. Rejected on
security before ergonomics: `docker-compose.yml` blanks `DB_SUPERUSER` and
`DB_SUPERUSER_PASSWORD` on every application service precisely so the superuser
credential cannot reach a container that serves requests (ADR 0009). A required
`Settings` field would stop the API starting in exactly the environment where the
blanking works, and an optional one would put a superuser credential on the
object that lives on `app.state` and feeds the §6.3 configuration view. It would
also make every application container ask for a variable only Alembic uses.

**An Alembic-only environment variable**, `ALEMBIC_DATABASE_URL`. The obvious
answer, and the one with a scar. `.env.example` accepts an entry only when a
`Settings` field resolves to it or a Compose file interpolates it (ADR 0008), and
`env.py` is neither reader — so the variable could not be documented, and an
undocumented variable that Compose or an operator sets is the exact hole
`tests/unit/test_env_example_sync.py` was written to close, where a superuser DSN
reached three containers with every test green. Documenting it anyway would mean
weakening that test.

**Deriving the address from the parts instead of from `DATABASE_URL`**, i.e.
`DB_SUPERUSER@${DB_HOST}:${DB_PORT}/${DB_NAME}`. Rejected because `.env.example`
declares no host or port — they exist only inside `DATABASE_URL` — so this needs
two new documented variables that duplicate what one already says, and two
things that can disagree about which server is being migrated. The
testcontainers fixture settles it in practice: it hands the container's random
published port to `DATABASE_URL` and to nothing else.

**Declaring `Base` in `app/db.py`, where the ticket puts it, and importing that
from `env.py`.** Rejected because it makes a migration depend on the whole
application configuration. CI's drift job and the test fixture both supply the
database variables alone, so `env.py` would raise `ConfigurationError` about
`AI_PROVIDER_BASE_URL` before opening a connection. The re-export keeps the
ticket's import path without the coupling.

**A second copy of the role SQL in the workflow**, inline `psql -c "CREATE ROLE
..."`. Rejected because there would then be three statements of what the
application role is — the init script, the test fixture, and the workflow — and
the one in CI is the one nobody would remember to update. The fixture's copy is
unavoidable (it has no shell), and one unavoidable copy is enough.

**Sourcing `.env` in the Makefile recipes** instead of reading it in `env.py`.
Rejected because `set -a; . ./.env` overrides variables already exported in the
caller's shell, which inverts the precedence ADR 0008 records, and because it
only helps the two commands that go through `make` — a developer who types
`alembic upgrade head` in `backend/` still gets "DATABASE_URL — not set" while
the value sits in the file everything else reads.

## Consequences

- **`.env` has three readers.** ADR 0008's mechanism is untouched — a reader is
  still found rather than named, and the sync test still passes because `env.py`
  reads variables that already have readers — but its count is now wrong on its
  own page and is corrected there and in `.env.example`.
- **`python-dotenv` becomes a declared dependency.** It was already in the
  closure under `pydantic-settings`; an import we write is a dependency we
  declare rather than one we inherit, so the version we get cannot change because
  something else changed its requirement.
- **A migration can be run against any database `DATABASE_URL` can name**, which
  includes one an operator did not mean. There is no second variable saying
  "this is the migration target", so the safety here is the same as the
  application's: the URL is the deployment's, and it is right or it is not.
- **`make migrate` runs on the host**, against the published port, so a
  developer whose `DATABASE_URL` names the Compose service `db` has to point it
  at `localhost` first — the same edit `README.md` already documents for running
  uvicorn outside a container. Migrations are not in the image (the wheel ships
  `app/` only), so running them in an application container is not currently
  possible and would mean handing that container the superuser credential.
- **CI's drift gate now fails if `env.py` starts using `DATABASE_URL`'s
  identity**, with `permission denied for schema public`, because its
  `DATABASE_URL` names the application role. That was verified by mutation
  rather than reasoned about: reverting the `.set(...)` turns three integration
  tests red with that error.
- **The `migration-drift` job depends on `psql` being installed on the runner.**
  It is, in the GitHub-hosted image; the step installs `postgresql-client` if it
  is not, so a runner image that drops it fails on apt rather than on `command
  not found`.
