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

`publish_once` at the foot of the file is the other half of what this module
owns: the single bounded publish every request path enqueues through, and the
home of the transport options that make it bounded. It lives here rather than in
any one service because three services now need it (E3-05), and
`docs/MISTAKES.md` entry 41 is a rule about how a request path publishes rather
than about what any one of them publishes.
"""

from typing import Any

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


# ---------------------------------------------------------------------------
# The one publish a request path is allowed to make.
# ---------------------------------------------------------------------------


# The connection a request-path publish is made on, and it is deliberately not the
# one the worker uses. `docs/MISTAKES.md` entry 41's three protections turned out
# not to be enough on their own, and this is the measurement:
#
#     apply_async(retry=False, ignore_result=True)   against a closed port
#         → kombu.exceptions.OperationalError after 6.04s
#
# `retry=False` governs the *publish* retry policy and nothing else.
# `kombu.Connection.default_channel` — which the publish reaches through when it is
# handed no connection — runs `_ensure_connection` with kombu's own defaults
# (`interval_start=2, interval_step=2`), so a broker that refuses instantly is
# retried on a schedule of its own before the publish is ever attempted. Six
# seconds is under entry 41's twenty and over SPEC §10's 2.5-second budget for the
# whole submit round trip, so the request is still hanging on a background
# dependency — just less obviously.
#
# So the connection is made per publish, with the retries off where they actually
# live, and its socket timeouts bounded. Measured on the same closed port:
# **0.037s**; against a blackholed address, where the refusal never comes at all,
# **1.04s** rather than the two minutes the operating system would otherwise spend.
# Against a broker that answers, the message is published in 0.046s.
#
# **Scoped to this connection and not set on `celery_app`.** A worker whose broker
# blips must reconnect rather than give up, so `broker_transport_options` is the
# wrong place for `max_retries: 0` — it is the request path that may not wait, and
# only the request path.
PUBLISH_TRANSPORT_OPTIONS = {
    "max_retries": 0,
    "socket_connect_timeout": 1.0,
    "socket_timeout": 1.0,
}
PUBLISH_CONNECT_TIMEOUT = 1.0


def publish_once(task: Any, *, args: tuple[Any, ...] = ()) -> None:
    """Publish one task from a request path: one attempt, bounded, result ignored.

    `docs/MISTAKES.md` entry 41's rule in one function, so that the three handlers
    that enqueue work from a request cannot each carry their own copy of it — entry
    13's rule about a hazard worked around in only one of the places facing it.
    Every clause is load-bearing:

      - **`retry=False`** — the publish is attempted once. Entry 41's incident is
        `task.delay(...)` against a Redis that was not there, holding each request
        "for roughly twenty seconds and then raising", out of a handler that had
        already done its own job.
      - **a connection made for this publish**, carrying the transport options
        above. Without it the flags still leave six seconds on a request SPEC §10
        gives two and a half, because the client library opens the connection under
        a retry policy of its own before the publish is attempted.
      - **`ignore_result=True`** — nothing reads these tasks' answers, and the
        result backend has a connection and a retry policy of its own. A task whose
        result nobody wants must not consult it.

    **Failures propagate**, and that is the division of labour. What to do about a
    broker that is not there is the caller's question and it is answered differently
    per caller — which record to write, what to tell the person waiting, what covers
    the gap — so each caller keeps its own broad `except`, its own error log and its
    own answer. What none of them keeps is a second opinion about how to publish.

    Under `task_always_eager` the task runs inline and this connection is never
    dialled: kombu connects lazily, and `apply_async` takes the eager branch before
    any publish is attempted.
    """
    with celery_app.connection_for_write(
        transport_options=PUBLISH_TRANSPORT_OPTIONS,
        connect_timeout=PUBLISH_CONNECT_TIMEOUT,
    ) as connection:
        task.apply_async(args=args, retry=False, ignore_result=True, connection=connection)
