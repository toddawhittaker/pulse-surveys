"""Celery tasks (SPEC §13).

`ping` exists only to prove the round trip and `effective_now` only to prove that
the worker reads the same clock the tool does (E2-04); `purge_launch_nonces` is
E1-08's daily maintenance of the two launch tables, the two `sync_*` tasks are
E1-11's roster pull, `derive_survey_windows` is E2-06's hourly reconciler over the
weekly rhythm (§3.1), and `reclassify_floored_comments` is E2-08's async half of
§3.3's fail-open. Summaries and grade passback (§7.4, §3.4) are E4 and E3's work,
and each of those is a call into `app/services/` from here rather than domain logic
written in this file — which is exactly the shape every task below takes: it opens
a session and calls a service.
"""

from datetime import UTC, datetime
from uuid import UUID

from app.config import Settings
from app.db import SessionLocal
from app.jobs.celery_app import celery_app
from app.lti.in_flight import purge_expired_launch_states
from app.lti.replay_guard import purge_expired_nonces
from app.services import clock
from app.services.roster_sync import sync_all_rosters, sync_section
from app.services.survey_windows import derive_windows_for_all_sections
from app.services.validity import (
    reclassify_floored_comments as sweep_unresolved_floored_comments,
)


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
def effective_now() -> str:
    """Return what `app.services.clock` says the time is, as an ISO 8601 string.

    The worker half of E2-04's criterion 2: "setting the pretend now from `/dev`
    changes what the backend **and the worker** both answer". The override is a
    database row precisely so two processes can agree about it, and this task is how
    the worker's answer is asked for at all — nothing else in the tree can report
    what time the worker thinks it is.

    **A permanent stack probe, on `ping`'s justification** (E0-03): it proves a
    round trip that is not provable any other way. `ping` proves the broker path;
    this proves that the clock a worker reads is the clock the tool moved, which is
    where E2-06's weekly scheduling runs — `derive_survey_windows` below is that
    job, on this same connection and this same clock.

    **A string and not a `datetime`**, because Celery here is configured with the
    JSON serializer and a `datetime` would fail inside the worker rather than at the
    caller. The offset rides in the string: `clock.now` answers an aware instant, and
    an ISO rendering that dropped the offset would be a different moment on every
    reader.

    Opens a session the way every task below does, so the row is read on the
    worker's own connection every time and no offset is held anywhere in this
    process.
    """
    settings = Settings()
    with SessionLocal() as session:
        return clock.now(session, settings=settings).isoformat()


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


@celery_app.task
def derive_survey_windows() -> None:
    """Derive every section's survey windows from its calendar (E2-06, SPEC §3.1).

    The hourly reconciler `app.jobs.schedules` runs on `crontab(minute="30")`. A
    section that appeared in the middle of a term — a staff launch or a roster sync
    creates one at any hour — gets its windows without anybody running anything, and
    a pass that finds nothing new writes nothing, because the derivation skips a
    `(section_id, week_id)` that already has a row.

    A thin wrapper, like the two tasks above: the session, the configuration and the
    commit are this task's, and every decision — the rhythm, the two week axes, what
    to do about a term short of `week` rows — is
    `app.services.survey_windows`'s, which is the one writer of that table.

    **One commit at the end rather than one per section**, and the walk already
    survives a section that fails: `derive_windows_for_all_sections` runs each
    section in its own savepoint and logs the ones it could not derive. What a
    per-section commit would buy is keeping the sections written so far when the
    *worker* dies mid-run, and the next hour re-derives everything either way.
    """
    settings = Settings()
    with SessionLocal() as session:
        derive_windows_for_all_sections(session, settings=settings)
        session.commit()


@celery_app.task
def reclassify_floored_comments() -> int:
    """Re-run every comment §3.3's fail-open floor stood in for (E2-08, SPEC §3.3).

    "on provider timeout, the heuristic floor applies and the submission is
    accepted, **then classified async**." This is that second half, and it is run
    from two places for one reason each: the submit path publishes it the moment it
    stores a floored submission, so a provider that has come back is used within
    seconds; and `app.jobs.schedules` runs it hourly, because the request-side
    publish is made with retries off and swallowed if the broker is down
    (`docs/MISTAKES.md` entry 41), so the schedule is what makes the promise good
    when it fails.

    A thin wrapper, like every task above: the session, the configuration and the
    commit are this task's, and which comments are unresolved, how each is re-run
    and what it does to `response.is_valid` are all
    `app.services.validity`'s — the module the submit path's synchronous half
    already reads, so the two halves cannot disagree about what a floored row is.

    **One commit at the end, over a walk that already survives a comment that
    fails.** Each comment runs inside its own savepoint in the service and a
    failure there is logged and stepped over, so the commit stores whatever the
    pass managed; the next run picks up whatever is still unresolved, because that
    is a fact about the stored rows rather than about this process.

    Answers how many comments were re-run, which is what a worker log line and an
    operator asking "is the backlog moving" both want.
    """
    with SessionLocal() as session:
        reclassified = sweep_unresolved_floored_comments(session)
        session.commit()
        return reclassified
