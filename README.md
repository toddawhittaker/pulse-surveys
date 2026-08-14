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

Early. The backend package exists — a FastAPI application factory, the
environment-driven settings object, and a health endpoint — and it runs in a
container alongside a Celery worker, a Celery beat scheduler, Postgres, Redis,
and Mailpit. CI enforces lint, typing, dependency audit, license compatibility,
and that the stack comes up healthy. The job runtime is wired but does no work
yet: the beat schedule is empty, and the only task is a `ping` that proves the
round trip. There is no database schema and no frontend yet.

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
at `/docs`, the captured mail is at <http://localhost:8025>, and Postgres and
Redis are on their usual ports. All of them bind to `127.0.0.1` only.

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

## Working on the backend without containers

Python 3.13 or newer (SPEC §7.1), and a virtual environment of your own making.

```sh
python3 -m venv .venv && source .venv/bin/activate
make tools          # the pinned CI tools: ruff, mypy, pip-audit, pip-licenses, pip-tools
make install        # the locked dependencies, plus this package, editable
cp .env.example .env
uvicorn app.main:create_app --factory --reload
```

One catch. `DATABASE_URL` and `REDIS_URL` in `.env.example` name the Compose
services `db` and `redis`, because CI copies that file and starts the stack from
it, so it has to be a file the stack can actually start from. Outside a
container those names do not resolve. Either start the backing services with
`make up` and point the two URLs at `localhost`:

```sh
# in your own .env, replacing the two lines copied from .env.example
DATABASE_URL=postgresql+psycopg://${DB_APP_USER}:${DB_APP_PASSWORD}@localhost:5432/${DB_NAME}
REDIS_URL=redis://localhost:6379/0
```

— or just use `make up`, which needs no such edit. Nothing in the backend opens
either connection yet (E0-04 is where that starts), so today this only matters
if you are working ahead.

Configuration is entirely environment-driven and documented in
[`.env.example`](.env.example), which a unit test keeps in sync with
`app.config.Settings`. Six variables have no default, because a working default
for a deployment-specific value is a misconfiguration that starts successfully:
the application refuses to start without them and names the one it is missing.
The `DB_*` entries are in that file for Compose rather than for the application
— Compose cannot parse a URL, so the `db` service is handed the parts
`DATABASE_URL` is built from, and each password stays written once.

They describe two database roles, and the difference matters. `DB_SUPERUSER` is
the role Postgres creates on first start; it is the cluster superuser, and it is
what migrations and system-level tasks use. `DB_APP_USER` is created alongside
it by [`scripts/db-init`](scripts/db-init) and is granted only the right to
connect. It is what `DATABASE_URL` points at, so an injection in application
code cannot reach a shell in the database container or read past a row-level
security policy.

`DATABASE_URL` must never point at `DB_SUPERUSER`, and the Compose file keeps
that credential out of the application container entirely. See
[ADR 0009](docs/adr/0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)
for which identity does what, and
[ADR 0001](docs/adr/0001-identity-separation-by-database-role.md) for why the
runtime role is scoped the way it is.

```sh
make ci             # every gate, in the same order as CI
make lint           # ruff check + ruff format --check
make typecheck      # mypy, strict over app/services/
make test           # pytest with coverage
make lock           # recompile the lockfiles after editing dependencies
```

`make ci` includes the Docker build gate, so it needs a running daemon, a free
port 8000, and a `.env`.

`make ci` is the same set of gates as `.github/workflows/ci.yml`, so a green run
here should mean a green run there. Where the two disagree, the workflow is
right and the `Makefile` is the bug.

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
