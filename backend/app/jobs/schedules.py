"""The beat schedule (SPEC §13, §3.1).

Wired to the application in `app.jobs.celery_app`. E0-03 gave it a runtime that
already works while every scheduled job still belonged to a later ticket — window
open and close is E2, the Monday report is E4, roster sync is E1. The first real
entry is E1-08's: the daily purge of the launch replay ledger, which replaces the
native TTL a Redis nonce store would have had (ADR 0089). Wired matters as much as
present: a schedule module nothing loads is one beat never reads, so
`test_celery_app.py` follows the mapping end to end rather than asserting it was
imported.

Entries go here rather than in `celery_app.py` so that adding one is a diff in
a file whose only subject is the schedule. Beat computes every entry in
`Celery.timezone`, which follows `INSTITUTION_TIMEZONE` — see `celery_app.py`,
and §3.1 for why that is not UTC.
"""

from typing import Any

from celery.schedules import crontab

# Celery's `beat_schedule` mapping: entry name to entry definition. The value
# type is Celery's own (`task`, `schedule`, `args`, `kwargs`, `options`), so it
# is annotated as loosely as Celery accepts it rather than modelled here.
#
# The purge runs once a day, well off any hour a launch is likely to arrive. A
# spent nonce only needs to outlive the launch that spent it (an hour), so daily
# is generous; the exact minute is this module's choice and is not a §6.3 knob.
BEAT_SCHEDULE: dict[str, dict[str, Any]] = {
    "purge-expired-launch-nonces": {
        "task": "app.jobs.tasks.purge_launch_nonces",
        "schedule": crontab(hour="3", minute="15"),
    },
}
