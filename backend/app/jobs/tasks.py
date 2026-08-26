"""Celery tasks (SPEC §13).

`ping` exists only to prove the round trip; `purge_launch_nonces` is E1-08's
daily maintenance of the replay ledger. Async classification, summaries, and
grade passback (§7.4, §3.4) are E3 and E13's work, and each of those is a call
into `app/services/` from here rather than domain logic written in this file —
which is exactly the shape `purge_launch_nonces` takes: it opens a session and
calls `app.lti.replay_guard`.
"""

from datetime import UTC, datetime

from app.db import SessionLocal
from app.jobs.celery_app import celery_app
from app.lti.replay_guard import purge_expired_nonces


@celery_app.task
def ping() -> str:
    """Return a constant, so that getting a result back means the path works.

    Deliberately touches nothing: no database, no AI provider, no network of
    its own. When this fails, the broker, the worker, or the result backend is
    at fault and nothing else can be, which is the whole reason to keep a task
    this dull in the tree.
    """
    return "pong"


@celery_app.task
def purge_launch_nonces() -> int:
    """Delete the launch nonces whose lifetime has passed, and return the count.

    The replacement for the native TTL a Redis nonce store would have had (ADR
    0089): the ledger lives in Postgres, so a daily beat entry
    (`app.jobs.schedules`) reclaims the expired tail rather than letting it grow
    without bound. Runs on the worker's `pulse_app` connection, which holds
    `DELETE` on the table for exactly this.
    """
    with SessionLocal() as session:
        removed = purge_expired_nonces(session, now=datetime.now(UTC))
        session.commit()
        return removed
