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
container alongside Postgres, Redis, and Mailpit. CI enforces lint, typing,
dependency audit, license compatibility, and that the stack comes up healthy.
There is no database schema, no background worker, and no frontend yet.

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
ports, mounts your checkout into the API container, and turns on reload-on-edit.
Every other deployment runs the base file alone and publishes nothing.

Copying `.env.example` is not optional: `docker-compose.yml` defaults no
credential, so a missing variable stops the stack with a message naming it.

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

Two of them are two different roles, and the difference matters. `DB_SUPERUSER`
is the role Postgres creates on first start, which is unavoidably the cluster
superuser. `DB_APP_USER` is created alongside it by
[`scripts/db-init`](scripts/db-init) and holds nothing but the right to connect;
it is what `DATABASE_URL` points at, so an injection in application code cannot
reach a shell in the database container or read past a row-level security
policy. See [ADR 0001](docs/adr/0001-identity-separation-by-database-role.md).
Nothing but administration should use `DB_SUPERUSER`.

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
