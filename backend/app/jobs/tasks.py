"""Celery tasks (SPEC §13).

`ping` exists only to prove the round trip; `purge_launch_nonces` is E1-08's
daily maintenance of the two launch tables. Async classification, summaries, and
grade passback (§7.4, §3.4) are E3 and E13's work, and each of those is a call
into `app/services/` from here rather than domain logic written in this file —
which is exactly the shape `purge_launch_nonces` takes: it opens a session and
calls `app.lti.replay_guard` and `app.lti.in_flight`.
"""

from datetime import UTC, datetime

from app.db import SessionLocal
from app.jobs.celery_app import celery_app
from app.lti.in_flight import purge_expired_launch_states
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
    """Delete the expired rows of both launch tables, and return the total count.

    The replacement for the native TTL a Redis store would have had (ADR 0089):
    both the replay ledger (`lti_launch_nonce`) and the in-flight handshake store
    (`lti_launch_state`) live in Postgres, so a daily beat entry
    (`app.jobs.schedules`) reclaims their expired tails rather than letting either
    grow without bound. Runs on the worker's `pulse_app` connection, which holds
    `DELETE` on both for exactly this. One task rather than two beat entries — the
    schedule holds a single launch-housekeeping entry.
    """
    now = datetime.now(UTC)
    with SessionLocal() as session:
        removed = purge_expired_nonces(session, now=now)
        removed += purge_expired_launch_states(session, now=now)
        session.commit()
        return removed
