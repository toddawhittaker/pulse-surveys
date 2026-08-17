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

### What it is seeded with

Three sections in one term, each with a roster of its own. Small on purpose: the
full demo institution is E0-17's and lives in Pulse's own database.

| Section | Course | Modality | Roster |
|---|---|---|---|
| `BIOL-215-R3WW` | Cell Biology | online, 12 weeks | 12 members — three pages |
| `MATH-140-E1FF` | College Algebra | face-to-face, 6 weeks | 7 members — two pages |
| `NURS-8100-Q2FF` | Doctoral Practice Inquiry | face-to-face, 12 weeks | 5 members — one page |

Course numbers are picked against SPEC §8's bands rather than from the prototype
screens in `design/`, every one of which is invalid under them. The section codes
are §2.2's `{startLetter}{ordinal}{modality}`, and they use more than one start
letter and both modalities so that E0-07's parser has real input.

**Who to launch as.** The launch page offers the two people enrolled in every
section, so any combination of its two selectors is a launch that works:

| Launch as | Role | What they are for |
|---|---|---|
| `mock-lms-user-instructor` | Instructor | every instructor surface |
| `mock-lms-user-learner` | Learner | every student surface |

Everybody else is a student who takes one section, and they exist so that a
roster pages and so that E3 has its edge cases. Two of them are not ordinary:
in `BIOL-215-R3WW`, student 04 enrolls three weeks after their classmates and
student 07 drops six weeks in — reported `Inactive`, with an enrollment `end`,
and still on the roster, because SPEC §3.4 has the tool learn about a drop from
the roster rather than from an absence.

Nobody has a name. Every person carries an email address and nothing else
personal, and every address is at a domain RFC 2606 reserves so that it can never
be delivered to. See [ADR 0050](docs/adr/0050-the-mock-roster-exposes-an-address-and-no-name.md).

### The roster and grade services

The platform serves LTI Advantage as well as the launch, and a tool finds both
services the way a real tool does — out of the two service claims inside the
`id_token`, never from a path it assembled. Nothing here is authenticated: a real
platform puts these behind an OAuth 2.0 client-credentials grant, and whichever
of E1 and E3 needs a token first is where that belongs.

- **NRPS 2.0** serves one section's roster five members at a time, and says where
  the next page is in an RFC 8288 `Link` header — never in the body. Enrollment
  windows ride on a namespaced member extension, because NRPS defines no date on
  a member at all ([ADR 0048](docs/adr/0048-enrollment-windows-ride-on-a-namespaced-nrps-extension.md)).
- **AGS 2.0** creates line items, lists them filtered by `resource_link_id`,
  `resource_id` or `tag` and paged the same way the roster is, and takes scores.
  Nothing is seeded: §3.4 has the tool create "Pulse Participation" on first
  launch, so what the container answers is only what a tool put there.
- **What the Score service refuses** is as much of the contract as what it takes,
  because a score this mock accepts is a score a tool learns to send. A
  `scoreGiven` with no `scoreMaximum`, a non-positive maximum, an
  `activityProgress` or `gradingProgress` outside AGS's two fixed vocabularies,
  and a `timestamp` that is not RFC 3339 with an offset are all refused. A score
  older than the one already held for that student on that line item is `409`;
  one at the *same* instant is taken, because a passback that times out re-sends
  an identical body and a `409` there would say the retry failed. And a
  `scoreMaximum` that disagrees with the line item's own is refused rather than
  rescaled — stricter than AGS, deliberately, so that post against the line
  item's maximum is the habit E3 forms
  ([ADR 0051](docs/adr/0051-a-disagreeing-score-maximum-is-refused-rather-than-rescaled.md)).
- **The conformant `Result`** is served per line item, filtered by `user_id`, and
  at its own URL — which is also the `resultUrl` a score post answers with, so a
  tool can follow what the platform just handed it.
- **`GET /mock/posted-scores`** answers with every score the platform has been
  sent, verbatim and in arrival order. It is outside the AGS namespace on
  purpose — a conformant `Result` has no timestamp and no progress fields, so
  this is the only place what the tool sent can be read back, and a tool that
  learned this route would have learned something no real platform serves
  ([ADR 0047](docs/adr/0047-the-posted-score-readback-is-a-mock-only-route.md)).

All of that is per-process and in memory: restart the container and the line
items and the posted scores are gone
([ADR 0049](docs/adr/0049-the-mock-gradebook-is-per-application-state-in-memory.md)).

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
`app.config.Settings`. The deployment-specific variables have no default,
because a working default for such a value is a misconfiguration that starts
successfully: the application refuses to start without them and names the one it
is missing.

`CARE_DATABASE_URL` is the exception, and deliberately. It is the one credential
in the cluster that can re-identify a student, so `docker-compose.yml` hands it
to `api` alone and blanks it — with the `DB_CARE_USER` and `DB_CARE_PASSWORD`
parts it is built from — on `worker` and `beat`. Those two never serve the Care
queue, and `worker` is the process that ships comment text to a third-party
model provider. `Settings` is built the same way in all three processes, so the
field has to be optional for that to be expressible at all; a reveal attempted
in a process without it fails naming the variable. See
[ADR 0042](docs/adr/0042-the-care-pool-has-its-own-credential-and-opens-on-first-use.md),
whose reversal section is why.
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
student, through one `SECURITY DEFINER` function that writes an audit row before
it reads the name and in the same transaction. It holds no direct `SELECT` on
that table either, so every route to a name goes through that function. One gap
is known and stated rather than papered over: a caller that runs the reveal and
then rolls back its own transaction keeps the name and discards the audit row,
because the rows are streamed before the caller decides. Closing that needs a
second connection for the audit write and is E0-26 item 1. It is also why only
the `api` process is given this credential.

A fourth role, `pulse_reveal_definer`, appears in `\du` and in none of this
file. It owns the reveal function and holds three grants, so that the one
function able to read a name runs with a readable list of privileges rather than
the migration identity's. It cannot log in, has no password anywhere, and needs
nothing from an operator —
[ADR 0043](docs/adr/0043-the-reveal-function-has-an-owner-of-its-own.md) is why
it exists and what it does not protect against.

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
