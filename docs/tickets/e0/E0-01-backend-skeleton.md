# E0-01 — Backend skeleton and configuration surface

**ID:** E0-01
**Branch:** `e0/backend-skeleton`
**Depends on:** none

## Context

The repository has CI, a branch model, and tooling configuration, but no Python
package for any of it to check. This ticket creates the FastAPI application
package and the env-driven settings object every later ticket reads from, and
flips the ruff, mypy, pip-audit, and license gates from tolerant to enforcing.

Read first: SPEC §13 (layout), §6.3 (configuration surface), §10
(non-functional requirements), `CLAUDE.md` (secrets, CI discipline).

## Scope

- `[project]` table in `pyproject.toml` with pinned runtime and dev
  dependencies: FastAPI, uvicorn, pydantic, pydantic-settings, SQLAlchemy,
  alembic, celery, redis, httpx, pytest, pytest-asyncio, testcontainers,
  hypothesis. Lockfile committed.
- `backend/app/__init__.py`, `backend/app/main.py` with an app factory
  (`create_app()`), and a mounted `/healthz` returning service name, version,
  and environment.
- `backend/app/config.py` — a `pydantic-settings` `Settings` class covering the
  §6.3 surface that exists this early: database URL, Redis URL, institution
  timezone, environment name, log level, AI provider base URL and model name,
  and the n-threshold and benchmark min-N defaults. Every field env-driven, no
  literal defaults for anything deployment-specific.
- `.env.example` listing every variable with placeholder values only. No real
  credential, per `CLAUDE.md`.
- Remove the `--allow-empty`-equivalent tolerance from the ruff and mypy jobs in
  `.github/workflows/ci.yml`, and from `pip-audit` and the license check.

## Out of scope

- Any Dockerfile or Compose service (E0-02).
- Database engine, session, or migrations (E0-04) — `config.py` declares the
  URL, nothing connects yet.
- Any ORM model (E0-05 onward).
- Celery app or task definitions (E0-03).

## Acceptance criteria

- [ ] `uvicorn app.main:create_app --factory` starts and `GET /healthz` returns
      200 with a JSON body naming the environment.
- [ ] `Settings` raises at startup when a required variable is absent, with a
      message naming the variable. No silent fallback to a working default.
- [ ] `.env.example` has one entry per `Settings` field; a test asserts the two
      are in sync so a new setting cannot be added without documenting it.
- [ ] `make ci` runs ruff and mypy against real code and passes, including the
      strict mypy profile on `app/services/` (empty package is acceptable).
- [ ] `pip-audit` and the license check run against real dependencies and pass.
- [ ] No `secrets.*` reference added to any workflow.

## Definition of done

**Tests apply.** Unit tests for `Settings`: required-field failure, type
coercion, and the `.env.example` sync assertion. No integration or e2e test —
there is nothing to integrate with yet.

**Docs apply.** `README.md` gains a short local-development section.
`.env.example` is itself the configuration documentation.

**AI evals do not apply** — no model task is touched.

**Accessibility does not apply** — no user interface.

**Security review applies but is light** (`/security-review` per `CLAUDE.md`).
The one surface worth a look is `config.py`: confirm no secret is logged at
startup and no default value embeds a credential.
