# Pulse Surveys

An LTI 1.3 / LTI Advantage tool that runs a brief, standardized weekly feedback
cycle in every enrolled course.

1. Students answer five questions each week inside the LMS.
2. Participation credit passes back to the gradebook automatically.
3. Every Monday, instructors get a report: rating distributions, workload data,
   de-identified comments, and an AI-generated summary.
4. Instructors publish a response (with advisory AI coaching); students see the
   aggregate results and that response, which closes the loop.
5. Academic leadership — lead faculty, chair, dean, VPAA — sees roll-up views
   across their span of oversight.

The design goal is trust. Students have to believe their responses are
confidential, and instructors have to believe the data is fair. Most of the
non-obvious requirements in the spec exist to protect one of those two beliefs.

## Status

Early, but no longer empty. The backend package exists — a FastAPI application
factory, the environment-driven settings object, a health endpoint, and a
database engine with a session per request — and it runs in a container
alongside a Celery worker, a Celery beat scheduler, Postgres, Redis, Mailpit,
and the mock LMS described below. CI enforces lint, typing, the test suite,
migration drift, dependency audit, license compatibility, and that the stack
comes up healthy.

The schema is real now. Migrations create the containment hierarchy
(institution through section), the term calendar and start-letter map, the
identity tables with `user` split from `user_identity`, the LTI registration
tables, and role assignments with the supervision graph. What sits on top of it
does not exist yet: no read views, no authorization, no HTTP routes beyond
`/healthz`, and no frontend. The job runtime is wired but does no work — the
beat schedule is empty, and the only task is a `ping` that proves the round
trip. The AI side has its typed contracts and versioned prompt directory but no
gateway to call a provider with.

## Run it locally

Docker, and nothing else.

```sh
cp .env.example .env
make up             # docker compose up -d
make logs           # follow the logs
make down           # docker compose down -v — discards the database too
```

`GET http://localhost:8000/healthz` answers with the service name, the version,
and the environment it was configured with. The interactive API documentation is
at `/docs`, the captured mail is at <http://localhost:8025>, the mock LMS is at
<http://localhost:8080>, and Postgres and Redis are on their usual ports. All of
them bind to `127.0.0.1` only.

`docker compose up` merges [`docker-compose.override.yml`](docker-compose.override.yml)
over the base file automatically, and that override is what publishes those
ports, mounts your checkout into the three application containers — `api`,
`worker` and `beat` — and turns on reload-on-edit for the API. Every other
deployment runs the base file alone, publishes nothing, and runs the code baked
into the image.

Copying `.env.example` is not optional: `docker-compose.yml` defaults no
credential, so a missing variable stops the stack with a message naming it.

## Background jobs

`make up` starts the job runtime along with everything else: `worker` runs the
Celery worker and `beat` runs the scheduler. Both run the API image over the
same configuration and, in development, over the same mounted checkout, so a
task is written once and reached the same way from an HTTP handler and from a
job.

**After editing anything under `backend/`, restart the two job containers.**

```sh
docker compose restart worker beat    # about three seconds; no rebuild
```

The API reloads itself and Celery does not, so without this the API runs your
edit while the worker runs the code it imported at startup. Neither one
complains. A task you have just added comes back as
`NotRegistered: app.jobs.tasks.your_task`, which at least names itself; a task
you have just *changed* comes back with the old answer and no error at all,
which is worse.

```sh
make logs                            # everything, interleaved
docker compose logs -f worker        # just the worker: tasks received and their results
docker compose logs -f beat          # just the scheduler: what it decided to fire, and when
docker compose exec api python -c "from app.jobs.tasks import ping; print(ping.delay().get(timeout=30))"
```

That last line is the whole round trip — the API container enqueues, the worker
executes, the result comes back through Redis — and it prints `pong`. Raise the
detail in both services with `LOG_LEVEL=DEBUG` in your `.env`; the worker and
beat commands read it.

To run a worker outside Docker, against the containerized Redis:

```sh
make up
celery --app app.jobs.celery_app worker --loglevel INFO
```

That needs `REDIS_URL` pointed at `localhost` in your own `.env`, for the same
reason the section below gives about `DATABASE_URL`.

The beat schedule ([`backend/app/jobs/schedules.py`](backend/app/jobs/schedules.py))
is deliberately empty: every scheduled job — window open and close, the Monday
report, roster sync, retention — belongs to a later epic. Beat keeps its
schedule file on a named volume, so the last-run times survive a restart and a
job that has already fired is not fired again when one of those entries lands.

## The mock LMS

Pulse is launched from a learning management system over LTI 1.3, and nobody has
a spare Canvas. So the stack brings its own platform to launch from: `mock-lms`,
a small FastAPI application in [`mock-lms/`](mock-lms/) that does the platform
half of a launch — it signs the `id_token` that Pulse will one day validate
(SPEC §9.2). It is development and test only. Nothing in Pulse trusts it unless a
row in `lti_platform` says so.

`make up` starts it with everything else. Open <http://localhost:8080>, choose a
seeded user and a placement, and press **Launch**: the page posts a
third-party-initiated login request at the tool, exactly as a real platform
would. Until E1 builds the tool's side of the launch, that post lands on a 404 —
which is the honest state of a platform whose tool does not exist yet.

To register it with Pulse, take the values from
<http://localhost:8080/registration>. The keys are the column names they go into,
so `issuer`, `client_id`, `jwks_url` and `deployment_id` fill in `lti_platform`
and `lti_deployment` without translation. The same block is on the launch page.

Two things about it are worth knowing before debugging anything:

- **Its issuer key is generated per process, and never written down.** Restart
  the container and it is a different platform with a different key set, so
  anything that cached the old key set stops verifying. That is deliberate: SPEC
  §9.1 asks for issuer keys generated per test run rather than fixtures checked
  into the repository, and no private key is committed anywhere in this
  repository — a test sweeps the tree to make sure.
- **It has no reload.** The development override mounts your checkout into the
  three application containers and not into this one, so editing `mock-lms/`
  means `docker compose up -d --build mock-lms`.

Two seeded users, one a learner and one an instructor, are enrolled in two
sections. One of those sections deliberately has no title, because LTI 1.3 makes
the context claim's title optional and Pulse's own `course.lms_title` is not —
so the ingestion path in E1 meets the awkward case in a test rather than in a
deployment. The roster and grade services, and a larger seed, are E0-15's.

## Working on the backend without containers

Python 3.13 or newer (SPEC §7.1), and a virtual environment of your own making.

```sh
python3 -m venv .venv && source .venv/bin/activate
make tools          # the pinned CI tools: ruff, mypy, pip-audit, pip-licenses, pip-tools
make install        # the locked dependencies, plus this package, editable
cp .env.example .env
uvicorn app.main:create_app --factory --reload
```

One catch. `DATABASE_URL`, `CARE_DATABASE_URL` and `REDIS_URL` in `.env.example`
name the Compose services `db` and `redis`, because CI copies that file and
starts the stack from it, so it has to be a file the stack can actually start
from. Outside a container those names do not resolve. Either start the backing
services with `make up` and point the three URLs at `localhost`:

```sh
# in your own .env, replacing the three lines copied from .env.example
DATABASE_URL=postgresql+psycopg://${DB_APP_USER}:${DB_APP_PASSWORD}@localhost:5432/${DB_NAME}
CARE_DATABASE_URL=postgresql+psycopg://${DB_CARE_USER}:${DB_CARE_PASSWORD}@localhost:5432/${DB_NAME}
REDIS_URL=redis://localhost:6379/0
```

— or just use `make up`, which needs no such edit for the application. It is not
optional for migrations: `make migrate` and `make migration-check` run `alembic`
here on your machine, and `db` is a name only the Compose network resolves.

Configuration is entirely environment-driven and documented in
[`.env.example`](.env.example), which a unit test keeps in sync with
`app.config.Settings`. Seven variables have no default, because a working
default for a deployment-specific value is a misconfiguration that starts
successfully: the application refuses to start without them and names the one it
is missing.
The `DB_*` entries are in that file for Compose rather than for the application
— Compose cannot parse a URL, so the `db` service is handed the parts
`DATABASE_URL` is built from, and each password stays written once.

They describe three database roles, and the differences matter. `DB_SUPERUSER`
is the role Postgres creates on first start; it is the cluster superuser, and it
is what migrations and system-level tasks use. `DB_APP_USER` is created
alongside it by [`scripts/db-init`](scripts/db-init) and is granted only the
right to connect and to read the views in
[`backend/app/views_sql/`](backend/app/views_sql). It is what `DATABASE_URL`
points at, so an injection in application code cannot reach a shell in the
database container, read past a row-level security policy, or read a student's
name — it holds no privilege of any kind on `user_identity`. `DB_CARE_USER`
serves the Care queue (SPEC §6.2) and is the only role that can re-identify a
student, through one `SECURITY DEFINER` function that writes an audit row in the
same transaction as the read. It holds no direct `SELECT` on that table either,
so a name cannot be obtained without leaving a record.

`DATABASE_URL` must never point at `DB_SUPERUSER`, and the Compose file keeps
that credential out of the application container entirely. See
[ADR 0009](docs/adr/0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)
for which identity does what,
[ADR 0001](docs/adr/0001-identity-separation-by-database-role.md) for why the
runtime roles are scoped the way they are, and
[ADR 0042](docs/adr/0042-the-care-pool-has-its-own-credential-and-opens-on-first-use.md)
for why the Care queue gets a credential rather than a `SET ROLE`.

**Upgrading an existing stack past E0-10 needs `docker compose down -v`.**
`scripts/db-init` runs only against an empty data directory, so on a volume
created before this ticket `pulse_care` exists — the migration creates it — with
no password and no way to log in, and the Care connection fails to
authenticate.

```sh
make ci             # every gate, in the same order as CI
make lint           # ruff check + ruff format --check
make typecheck      # mypy, strict over app/services/
make test           # pytest with coverage
make migrate        # alembic upgrade head, against the running stack
make lock           # recompile the lockfiles after editing dependencies
```

`make ci` includes the Docker build gate, so it needs a running daemon, a free
port 8000, and a `.env`. It also includes the migration drift gate, so it needs a
database to migrate — `make up`, with `DATABASE_URL` pointed at `localhost` as
above.

`make ci` is the same set of gates as `.github/workflows/ci.yml`, so a green run
here should mean a green run there. Where the two disagree, the workflow is
right and the `Makefile` is the bug.

## How to create a migration

Every table in the schema is created by a migration, and the models are the
source those migrations are generated from. After editing anything under
[`backend/app/models/`](backend/app/models):

```sh
make up                                              # the database has to be running
cd backend
alembic revision --autogenerate -m "what you changed"
```

Read the generated file before committing it. Autogenerate is a good first
draft and not an answer: it does not see a rename (it emits a drop and an add,
which discards the data), and it cannot know what to backfill.

```sh
make migrate        # apply it: alembic upgrade head
make migration-check  # what CI runs: upgrade, then `alembic check`
```

**A model change with no migration behind it fails the build.** The
`migration-drift` job runs `alembic upgrade head && alembic check` against a
Postgres of its own, and `alembic check` exits non-zero when the tables the
models describe differ from the tables the migrations produce. That is a build
failure on the pull request rather than a surprise at deploy time, and it is why
the two commits belong together.

Two things worth knowing before writing one:

- **Migrations connect as `DB_SUPERUSER`, not as the role in `DATABASE_URL`.**
  That role is granted `CONNECT` and deliberately cannot create a table, so a
  migration run under it stops with `permission denied for schema public`. See
  [ADR 0009](docs/adr/0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)
  and [ADR 0012](docs/adr/0012-the-migration-environment-builds-its-own-superuser-connection.md).
- **A model module nobody imports is invisible to autogenerate.** Adding
  `backend/app/models/<aggregate>.py` means adding it to that package's
  `__init__.py` in the same change, or `alembic check` will cheerfully report no
  drift for a table that exists in no database.
- **`alembic check` sees tables, and nothing else this schema relies on.** It
  reads neither `pg_roles`, nor `pg_class` for views, nor `pg_proc`, so dropping
  a read view, a trigger, the Care reveal function, or a grant leaves the check
  green. A read view's SQL lives in
  [`backend/app/views_sql/`](backend/app/views_sql) as a versioned file a
  revision executes and never edits afterwards
  ([ADR 0041](docs/adr/0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md)),
  and the integration tests are the only thing that notices when one changes.

## Documents

- [`docs/SPEC.md`](docs/SPEC.md) — product and technical specification.
- [`docs/DESIGN_BRIEF.md`](docs/DESIGN_BRIEF.md) — visual and interaction brief.
- [`design/`](design/) — exported prototype components, design tokens, and the
  data model for roles and reporting. This is the visual contract the frontend
  implements.
- [`CLAUDE.md`](CLAUDE.md) — the constraints that must not be violated,
  condensed from the two documents above.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — the branch and pull request model.

## Deployment model

Single tenant, self-hosted.

## License

MIT. See [`LICENSE`](LICENSE).
