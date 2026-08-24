"""The beat schedule (SPEC §13, §3.1).

Wired to the application in `app.jobs.celery_app` and empty of real entries.
Both halves matter. Empty, because every scheduled job in this product belongs
to a later ticket — window open and close is E2, the Monday report is E4,
roster sync is E1, retention purges are E13 — and E0-03 exists to give them a
runtime that already works. Wired, because a schedule module nothing loads is
one beat never reads: the first entry added here would be scheduled by nobody,
with beat still reporting healthy, and a window that never opens looks exactly
like a window nobody configured.

Entries go here rather than in `celery_app.py` so that adding one is a diff in
a file whose only subject is the schedule. Beat computes every entry in
`Celery.timezone`, which follows `INSTITUTION_TIMEZONE` — see `celery_app.py`,
and §3.1 for why that is not UTC.
"""

from typing import Any

# Celery's `beat_schedule` mapping: entry name to entry definition. The value
# type is Celery's own (`task`, `schedule`, `args`, `kwargs`, `options`), so it
# is annotated as loosely as Celery accepts it rather than modelled here.
BEAT_SCHEDULE: dict[str, dict[str, Any]] = {}
