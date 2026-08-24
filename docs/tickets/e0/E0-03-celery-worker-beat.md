# E0-03 — Celery worker and beat

**ID:** E0-03
**Branch:** `e0/celery-worker-beat`
**Depends on:** E0-02

## Context

Nearly every scheduled behavior in this product is a job: window open and close,
Monday report generation, roster sync, retention purges. This ticket stands up
the Celery application, a worker, and a beat scheduler with health checks, so
later epics add tasks to a working runtime rather than building one.

Read first: SPEC §13 (`jobs/`), §3 (the weekly cycle, for what will eventually
be scheduled), §10.

## Scope

- `backend/app/jobs/celery_app.py` — Celery application configured from
  `Settings`, Redis broker and result backend, timezone from institution config.
- `backend/app/jobs/schedules.py` — beat schedule module, empty of real entries
  but wired and importable.
- `backend/app/jobs/tasks.py` — one trivial `ping` task used only to prove the
  round-trip.
- `worker` and `beat` services in `docker-compose.yml`, sharing the API image.
- A meaningful `HEALTHCHECK` on each: `celery inspect ping` for the worker, and
  a beat liveness check based on schedule-file freshness rather than mere
  process existence.
- A named volume for beat's schedule file, so last-run times survive a restart.
- Restore `wait_for_health.sh api worker beat` in the CI `docker` job.

## A note on criterion 3

It originally read "restarts cleanly and does not double-schedule". That has no
observable in this ticket: the same scope requires the beat schedule to be empty
of real entries, so nothing exists that *could* fire twice. The criterion is
narrowed above to the two things that are checkable now — beat returns to
healthy, and its schedule file persists — because persistence is the mechanism
that makes "does not double-schedule" true once E2 lands the first real entry.
The property itself is first testable in E2 and should be asserted there.

## Out of scope

- Any real scheduled task — window scheduling is E2, reports are E4, roster sync
  is E1, retention is E13.
- Task retry and failure policy beyond Celery defaults; the AGS retry work is
  E3.
- Flower or any job dashboard (E11).

## Acceptance criteria

- [ ] `docker compose up -d` reaches healthy on `api`, `worker`, and `beat`.
- [ ] Calling the `ping` task from the API container returns its result through
      the Redis backend within a timeout.
- [ ] `beat` restarts cleanly after `docker compose restart beat`: it returns to
      healthy, and its schedule file survives the restart rather than being
      recreated empty.
- [ ] The worker health check fails (not passes) when Redis is stopped —
      verify by stopping `redis` and observing the container go unhealthy.
- [ ] The CI `docker` job waits on all three services and passes.

## Definition of done

**Tests apply.** One integration test that enqueues `ping` and asserts the
result comes back, marked `integration`. It needs a broker, so it belongs in
`tests/integration/`.

**Docs apply.** `README.md` notes how to run a worker locally and how to tail
job logs.

**AI evals do not apply.**

**Accessibility does not apply.**

**Security review applies but is light.** Confirm the broker is not exposed
outside the Compose network in the base file and that the worker image carries
no extra privilege beyond the API image.
