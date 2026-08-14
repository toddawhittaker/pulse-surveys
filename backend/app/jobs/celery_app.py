"""The Celery application (SPEC §13, §7.2).

Run against it with `celery --app app.jobs.celery_app <worker|beat>`; the
Compose `worker` and `beat` services do exactly that.

**The application is built at import time and lives at module level**, which is
the opposite of what `app.main` does with FastAPI and is deliberate: `celery -A`
resolves a module attribute and cannot call a factory. So this module reads
`Settings()` once, when it is imported, and a missing or malformed variable
stops the worker at startup with the same `ConfigurationError` the API raises.
See docs/adr/0010-the-celery-application-is-built-at-import-time.md, which
records that decision against the one in docs/adr/0006-settings-lifetime.md.

Everything below is configured from `Settings` rather than written as a literal,
and the two settings that come through are the two that break silently:

* **`REDIS_URL`** is the broker and the result backend (§7.1). A literal
  `redis://redis:6379/0` here would pass the Compose health check and the
  round-trip test — both run against the Compose `redis` service, which is
  where the literal points — and then ignore the configured broker in every
  deployment whose Redis is somewhere else.
* **`INSTITUTION_TIMEZONE`** is the timezone beat computes its crontabs in.
  §3.1 puts the survey window at Friday 18:00 in the institution timezone, so an
  application left on Celery's default UTC opens every window at the wrong hour
  while reporting healthy. Nothing in E0-03 is scheduled, so the first symptom
  would arrive in E2 looking like a scheduling bug rather than a configuration
  one.
"""

from celery import Celery

from app.config import Settings
from app.jobs import schedules

_settings = Settings()

# One URL for both roles. Redis keeps the broker's queues and the backend's
# `celery-task-meta-*` keys in one keyspace without colliding, and a second
# database number would be a second thing to configure, document, and get wrong
# — `.env.example` documents REDIS_URL as "the Celery broker and result
# backend" and this is the end of that wire. The database number a deployment
# wants is the one it writes into REDIS_URL.
_redis_url = _settings.redis_url.get_secret_value()

# Named `celery_app` rather than `app`, because `app` is this project's import
# root and a module global by that name reads as the package. `celery -A
# app.jobs.celery_app` finds it either way: `celery.app.utils.find_app` looks
# for `app`, then `celery`, then scans the module for a Celery instance.
celery_app = Celery(
    "pulse-surveys",
    broker=_redis_url,
    backend=_redis_url,
    # What the worker imports on start. Without it the worker connects, reports
    # healthy, and rejects every task it is sent as unregistered.
    include=["app.jobs.tasks"],
)

# `timezone` and not `enable_utc`: messages stay UTC on the wire, which is
# Celery's default and the right one, while crontab entries in
# `app.jobs.schedules` are evaluated in the institution's zone (§3.1).
celery_app.conf.timezone = _settings.institution_timezone

celery_app.conf.beat_schedule = schedules.BEAT_SCHEDULE
