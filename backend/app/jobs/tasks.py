"""Celery tasks (SPEC §13).

`ping` exists only to prove the round trip; `purge_launch_nonces` is E1-08's
daily maintenance of the two launch tables, and the two `sync_*` tasks are
E1-11's roster pull. Async classification, summaries, and grade passback (§7.4,
§3.4) are E3 and E13's work, and each of those is a call into `app/services/`
from here rather than domain logic written in this file — which is exactly the
shape every task below takes: it opens a session and calls a service.
"""

from datetime import UTC, datetime
from uuid import UUID

from app.config import Settings
from app.db import SessionLocal
from app.jobs.celery_app import celery_app
from app.lti.in_flight import purge_expired_launch_states
from app.lti.replay_guard import purge_expired_nonces
from app.services.roster_sync import sync_all_rosters, sync_section


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


@celery_app.task
def sync_rosters() -> None:
    """Pull the roster of every section that carries a stored address (E1-11, D10).

    The hourly half of SPEC §7.3's "NRPS pulled on schedule and on launch
    (debounced)". `app.jobs.schedules` runs it on `crontab(minute="0")`, and the
    stored roster address is the whole of what it knows about which sections
    exist: "it has no way of its own to learn that a section exists."

    A thin wrapper, like `purge_launch_nonces` above: the session, the
    configuration and the commit are this task's, and every decision is
    `app.services.roster_sync`'s.

    **One commit at the end rather than one per section.** The walk already
    survives a section that fails — `sync_all_rosters` logs and moves on — so what
    a per-section commit would buy is keeping the sections that succeeded when the
    *worker* dies mid-run, and what it would cost is a partly-applied roster if a
    later section's write is refused. The next hour re-reads everything either way.
    """
    settings = Settings()
    with SessionLocal() as session:
        sync_all_rosters(session, settings=settings)
        session.commit()


@celery_app.task
def sync_section_roster(section_id: str) -> None:
    """Pull one section's roster — what a staff launch's debounced trigger enqueues.

    The launch half of SPEC §7.3's pair. `app.services.roster_sync.
    request_section_sync` is what decides whether to enqueue this at all, and
    `app.api.lti.launch` is what calls that after a launch has been committed.

    **The section is a string on the wire and a `UUID` here**, because a Celery
    argument is serialised to JSON and a `UUID` is not a JSON type. Parsing it here
    rather than accepting either shape means a caller that enqueued something else
    fails in the worker log with a `ValueError` naming the value, instead of
    reaching a query that silently matches no section.
    """
    settings = Settings()
    with SessionLocal() as session:
        sync_section(session, UUID(section_id), settings=settings)
        session.commit()
