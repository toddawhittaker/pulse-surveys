"""Celery job runtime (SPEC §13, §7.2).

Three modules, and the split is Celery's rather than ours: `celery_app.py`
builds the application that `celery -A` resolves, `schedules.py` is what beat
reads, and `tasks.py` is what the worker executes. Everything scheduled in this
product — window open and close (§3.1), the Monday report (§5.1), roster sync,
retention purges — lands in the last two.

A job is a caller of `app/services/`, never a second implementation of one.
The domain logic stays behind the authorization chokepoint so that the HTTP
API, the worker, and the future MCP server all reach it the same way (§13).
"""
