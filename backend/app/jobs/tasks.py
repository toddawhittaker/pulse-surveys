"""Celery tasks (SPEC §13).

One task, and it exists only to prove the round trip: enqueued from the API
container, executed by the worker, its result read back through the Redis
backend. Async classification, summaries, and grade passback (§7.4, §3.4) are
E3 and E13's work, and each of those is a call into `app/services/` from here
rather than domain logic written in this file.
"""

from app.jobs.celery_app import celery_app


@celery_app.task
def ping() -> str:
    """Return a constant, so that getting a result back means the path works.

    Deliberately touches nothing: no database, no AI provider, no network of
    its own. When this fails, the broker, the worker, or the result backend is
    at fault and nothing else can be, which is the whole reason to keep a task
    this dull in the tree.
    """
    return "pong"
