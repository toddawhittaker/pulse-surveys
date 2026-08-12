# E0-02 — Backend Dockerfile and Compose stack

**ID:** E0-02
**Branch:** `e0/compose-stack`
**Depends on:** E0-01

## Context

`docker compose up` is the project's one-command entry point (SPEC §13), and the
CI build gate already knows how to wait on service health. This ticket brings up
the API alongside Postgres, Redis, and Mailpit, with real health checks so that
"the stack is up" is a claim the pipeline can verify.

Read first: SPEC §13, §10, and `scripts/ci/wait_for_health.sh` — it fails a
service that declares no `HEALTHCHECK`, which is deliberate.

## Scope

- `backend/Dockerfile` — multi-stage, non-root runtime user, no build toolchain
  in the final layer.
- `docker-compose.yml` with `api`, `db` (Postgres 16), `redis`, and `mailpit`.
- `docker-compose.override.yml` for development only: source bind-mount, hot
  reload, exposed ports.
- A `HEALTHCHECK` on `api` that hits `/healthz`, plus health checks on `db`
  (`pg_isready`) and `redis` (`redis-cli ping`). `api` declares
  `depends_on: {db: {condition: service_healthy}}`.
- Named volume for Postgres data; `docker compose down -v` gives a clean slate.
- Enable the CI `docker` job, calling `wait_for_health.sh api` only — worker and
  beat arrive in E0-03 and the argument list grows there.

## Out of scope

- `worker` and `beat` services (E0-03).
- `mock-lms` and `mock-idp` services (E0-14, E0-16).
- Frontend container — no frontend exists in E0.
- Any database schema; `db` comes up empty (E0-04).

## Acceptance criteria

- [ ] `docker compose up -d` reaches healthy on `api`, `db`, and `redis` from a
      clean checkout with `.env` copied from `.env.example`.
- [ ] `curl localhost:8000/healthz` returns 200 against the running stack.
- [ ] `docker compose down -v && docker compose up -d` succeeds twice in a row
      with no manual cleanup.
- [ ] The API container runs as a non-root user (`id -u` is not 0).
- [ ] The CI `docker` job builds the image and passes the health wait, with the
      tolerance notice removed.
- [ ] `make up`, `make down`, and `make logs` work against the stack.

## Definition of done

**Tests apply, lightly.** No unit tests — this is infrastructure. The health
gate in CI is the test, and it must run green on a real runner before merge.

**Docs apply.** `README.md` gains "run it locally" with the copy-`.env.example`
step and the `make` targets.

**AI evals do not apply.**

**Accessibility does not apply.**

**Security review applies and matters here.** Check the image for a root
runtime user, a leaked build secret in a layer, an unnecessarily exposed port in
the base Compose file (as opposed to the dev override), and any default
credential that would survive into a non-development deployment.
