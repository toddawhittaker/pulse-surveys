"""Celery tasks (SPEC §13).

`ping` exists only to prove the round trip and `effective_now` only to prove that
the worker reads the same clock the tool does (E2-04); `purge_launch_nonces` is
E1-08's daily maintenance of the two launch tables, the two `sync_*` tasks are
E1-11's roster pull, `derive_survey_windows` is E2-06's hourly reconciler over the
weekly rhythm (§3.1), `reclassify_floored_comments` is E2-08's async half of
§3.3's fail-open, `create_line_item` is E3-05's half of §3.4's line item "created
by the tool on first launch", and `post_participation_scores` is E3-06's weekly
recompute of §3.4's score. Summaries (§7.4) are E4's, and every one of these is a
call into `app/services/` from here rather than domain logic written in this file
— which is exactly the shape every task below takes: it opens a session and calls
a service.

**Who commits is part of that shape, and one task departs from it on purpose.**
Every task here opens the session and commits it, because the service decides and
writes while the caller owns the transaction. `post_participation_scores` does
not: its service commits after each section, because the rows it writes are the
record of scores that have already reached somebody else's gradebook and cannot be
allowed to depend on a walk over the whole institution finishing. That task's
docstring carries the argument, and it is the place to read before making this
file consistent with itself.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from app.config import Settings
from app.db import SessionLocal
from app.jobs.celery_app import celery_app
from app.lti.ags import AgsError
from app.lti.in_flight import purge_expired_launch_states
from app.lti.replay_guard import purge_expired_nonces
from app.services import clock
from app.services.grading import ensure_line_item, post_scores_for_all_sections
from app.services.roster_sync import sync_all_rosters, sync_section
from app.services.survey_windows import derive_windows_for_all_sections
from app.services.validity import (
    reclassify_floored_comments as sweep_unresolved_floored_comments,
)

logger = logging.getLogger(__name__)


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
def create_line_item(section_id: str) -> None:
    """Create one section's participation column, or reconcile to the one already there.

    SPEC §3.4's "created by the tool on first launch", which
    `app.services.grading.request_line_item_creation` publishes after a staff
    launch has been committed and `app.api.lti.launch` is what calls that.

    A thin wrapper, like every task above: the session, the configuration and the
    commit are this task's, and every decision — whether the section needs one, what
    the platform is asked for, and whether the answered address may be recorded — is
    `app.services.grading`'s.

    **The section is a string on the wire and a `UUID` here**, for
    `sync_section_roster`'s reason: a Celery argument is serialised to JSON and a
    `UUID` is not a JSON type. Parsing it here rather than accepting either shape
    means a caller that enqueued something else fails in the worker log with a
    `ValueError` naming the value, instead of reaching a query that matches no
    section at all.

    **No retry, and the `AgsError` family propagates, after the calls it recorded
    are committed.** A platform that refused this call is not more likely to accept
    it a second later, and the next qualifying launch of the section is the retry
    (ADR 0135). What reaches the worker log is the section, the outcome and the
    call — creation carries no score, no ledger and no LMS user id, which is what
    E3's breakdown decision 10 settled the log could hold.

    **A failed attempt keeps the `ags_call` rows it wrote before it raised.** Every
    failing AGS path calls `_record_call` and then raises an `AgsError`; without the
    commit below, `SessionLocal.__exit__` would roll those rows back on the raise,
    so a successful creation would be durable on SPEC §6.1's console and a failed
    one would leave no trace at all. Creation has no hourly backstop the way the
    roster sync does, so an attacker who can provoke the failure could probe a
    platform's gradebook endpoints and stay invisible in the one log built to show
    the attempt. So the `AgsError` family is caught, the recorded calls are
    committed, and the error is re-raised unchanged — the worker still sees the
    failure, and the row survives it.

    **`AgsError` specifically, never a bare `Exception`.** A failure inside that
    family has already recorded its row and left the session clean to commit; a
    failure outside it — a bug that left the session mid-flush — must roll back
    rather than commit half a row. A `RegistrationAddressError` refused inside
    `ensure_line_item` never reaches here: it is logged and returned, so its own row
    is committed by the ordinary success path below.
    """
    settings = Settings()
    with SessionLocal() as session:
        try:
            ensure_line_item(session, UUID(section_id), settings=settings)
        except AgsError:
            session.commit()
            raise
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


@celery_app.task
def post_participation_scores() -> dict[str, int]:
    """Post every participation score that has changed since it was last sent (E3-06, SPEC §3.4).

    The weekly recompute `app.jobs.schedules` runs on `crontab(day_of_week="mon",
    hour="2", minute="20")`. SPEC §3.4: "Re-posted whenever a recomputation changes
    the value, ordinarily after each week closes; fully automatic, no instructor
    action or override."

    A thin wrapper, like every task above: the session and the configuration are
    this task's, and every decision — which sections are still inside the sweep's
    bound, which students hold a live enrollment, what counts as a difference, and
    which bytes a retry carries — is `app.services.grading`'s.

    **The commit is not this task's, and it is the one task here that says so**
    (work order D15). The service commits after each section, and this task does
    not commit at all.

    The convention every task above keeps — the caller owns the transaction, the
    service decides and writes — is about transaction hygiene, and it is right
    wherever the work is reversible: a roster half-applied is a roster nobody has
    seen, so holding it to the end costs nothing and buys atomicity. This walk is
    not that. Each section posts a score to somebody else's gradebook, and a score
    that has arrived does not un-arrive because a worker died on the next section.
    So the `grade_sync` and `ags_call` rows are the record of a side effect that has
    already happened outside this process, and their durability is a correctness
    property of the service rather than a matter of when the caller happens to
    commit. Under one commit at the end, a worker killed mid-walk leaves every score
    it had already posted in a gradebook with no record here that Pulse put it
    there — and the next Monday posts them all again as new deliveries, because
    `grade_sync` no longer says otherwise. `create_line_item` above makes the same
    argument for a single creation; a walk needs it per section.

    **There is deliberately no trailing commit here as a tail-cover.** Nothing in
    the service writes outside a section, so by the time this returns there is
    nothing left to commit — and a commit on this line would tell the next reader
    that the task owns durability, which is the belief this docstring exists to
    correct. `SessionLocal()`'s context manager discards whatever open transaction
    a run leaves behind.

    **This log line is the one place a number about the run belongs.** E3's
    breakdown decision 10 allows this job's stream the section, the outcome and the
    call, and no score, no ledger line and no LMS user id; the totals are counts of
    posts rather than anything about a student, and they are written once for the
    run rather than once per section.

    Answers how many posts the platform took and how many it did not — the dict the
    service composed, unchanged, for §6.1's console to render.
    """
    settings = Settings()
    with SessionLocal() as session:
        counts = post_scores_for_all_sections(session, settings=settings)
        logger.info(
            "the weekly participation sweep finished: %d score(s) posted, %d not",
            counts["posted"],
            counts["failed"],
        )
        return counts
