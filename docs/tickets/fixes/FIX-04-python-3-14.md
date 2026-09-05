# FIX-04 — The runtime moves to Python 3.14

**ID:** FIX-04
**Branch:** `fix/python-3-14`
**Depends on:** E3 merged to `main`. A runtime change under an in-flight epic
adds a variable for no gain; ruled 2026-09-05 to wait.
**Lane:** heavy — `Dockerfile*` (any directory) and `.github/workflows/` are
named rows in `.claude/heavy-lane-paths.md`.
**Security-relevant:** the base-image digests and the lockfile hash sets
change; the per-PR security review reads both.

## Context

The runtime is pinned at Python 3.13.15 in seven places: eight `FROM
python:3.13.15-slim-bookworm@sha256:...` lines across the four Dockerfiles
(`backend/`, `mock-lms/`, `mock-idp/`, `mock-ai/`), `PYTHON_VERSION` in
`.github/workflows/ci.yml`, `requires-python` and the mypy `python_version`
in `pyproject.toml`, and a mention in `docker-compose.yml`.

Python 3.14 has been stable since October 2025; the compiled dependencies
(pydantic-core, psycopg, greenlet, cryptography) have shipped 3.14 wheels for
months. Python 3.15 is due October 2026 and stays out of scope: its compiled
wheels need months to mature, and 3.14 is the proven target.

Two behavior changes in 3.14 need one careful full run rather than argument:
annotations are lazy by default (PEP 649), and multiprocessing on Linux
defaults to `forkserver` instead of `fork` — Celery's prefork pool is the spot
to watch.

## Scope

1. **The pins move.** All eight Dockerfile `FROM` lines move to the current
   3.14-patch `slim-bookworm` image, pinned by digest; `PYTHON_VERSION`
   becomes `'3.14'`; `pyproject.toml`'s `requires-python` and mypy
   `python_version` and the `docker-compose.yml` mention follow.
2. **The lockfiles are rebuilt on 3.14.** `make lock` runs under a 3.14
   interpreter so the hash sets cover the 3.14 wheels. Version bumps the
   re-lock forces ride this PR and are named in its body; bumps it does not
   force are not taken.
3. **The two behavior changes are checked, not assumed.** A grep for direct
   `__annotations__` readers in application code, and a Celery worker booting
   and running a task on the compose stack.

## Acceptance criteria

1. Full CI is green on the PR, including the Docker gate and the isolated
   invariant pass with all invariant tests collected.
2. `make ci` passes locally on a rebuilt 3.14 virtualenv installed from the
   committed lockfiles.
3. No `3.13` reference remains in the seven pinned places, proven by grep.
4. A Celery worker on the rebuilt images accepts and completes a task.

## Out of scope

- Python 3.15, until its wheels mature.
- Dependency upgrades beyond what the re-lock forces — those belong to
  Dependabot's normal path.
