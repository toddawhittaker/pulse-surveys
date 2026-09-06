"""The beat schedule (SPEC §13, §3.1).

Wired to the application in `app.jobs.celery_app`. E0-03 gave it a runtime that
already works while every scheduled job still belonged to a later ticket — the
Monday report is E4, retention is E13. Five entries have landed: E1-08's daily
purge of the launch replay ledger, which replaces the native TTL a Redis nonce
store would have had (ADR 0089), E1-11's hourly roster pull (SPEC §7.3), E2-06's
hourly survey-window reconciler, which derives the windows a section's calendar
implies (SPEC §3.1, ADR 0111), E2-08's hourly sweep of the comments §3.3's
fail-open floor stood in for, and E3-06's weekly recompute of §3.4's participation
score. Note that the window reconciler is scheduled on real time like every entry
here: beat's own firing is outside the development clock override (ADR 0109),
which is exactly why E2-06 materializes its rows in advance rather than at the
moment a window opens — and why E3-06's Monday slot is a real Monday however far a
development clock has been moved.

Wired matters as much as present: a schedule module nothing loads is
one beat never reads, so `test_celery_app.py` follows the mapping end to end
rather than asserting it was imported.

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
    # SPEC §7.3's scheduled half: "Roster sync: NRPS pulled on schedule and on
    # launch (debounced)." On the hour, and a `crontab` rather than a `timedelta`
    # because "hourly" and "every 3600 seconds" are different schedules — a
    # `timedelta` entry drifts with every restart, so which minute of the hour an
    # institution's rosters are pulled in would depend on when beat last came up.
    #
    # The *walk* is scheduled and not the per-section task: `sync_rosters` visits
    # every section that carries a stored roster address, which is the whole of the
    # discovery the scheduled half has. `sync_section_roster` beside it is what a
    # staff launch's debounced trigger enqueues, for the one section it touched.
    "roster-sync-hourly": {
        "task": "app.jobs.tasks.sync_rosters",
        "schedule": crontab(minute="0"),
    },
    # E2-06's reconciler: every section's survey windows, derived from its calendar
    # (SPEC §3.1, §2.2). A `crontab` for the same reason the roster sync is one,
    # and **minute 30 rather than minute 0** because that minute is already the
    # roster sync's and the two each walk every section in the institution.
    #
    # It exists because a section can appear in the middle of a term — a staff
    # launch or a roster sync creates one at any hour — and E2-06 deliberately
    # does not hook the writer into those flows, which would put its diff inside
    # E2-02's ingestion surface. Staleness of up to an hour is the cost, recorded
    # in ADR 0111. The pass is idempotent, so running it hourly forever writes
    # nothing after the first time it reaches a section.
    "derive-survey-windows-hourly": {
        "task": "app.jobs.tasks.derive_survey_windows",
        "schedule": crontab(minute="30"),
    },
    # E2-08's async half of SPEC §3.3's fail-open: every comment the character
    # floor stood in for, asked of a model again. A `crontab` for the reason the
    # two entries above are one, and **minute 45** because minutes 0 and 30 are
    # already taken by walks over every section in the institution.
    #
    # The submit path publishes this same task the moment it stores a floored
    # submission, so this entry is not how the work usually gets done. It is what
    # makes the promise good when that publish does not go out — it is made with
    # retries off and caught broadly, because a request may not fail or wait
    # because a broker was down (`docs/MISTAKES.md` entry 41), and closing that
    # gap is exactly what this entry is for. A pass that finds nothing unresolved
    # writes nothing.
    "reclassify-floored-comments-hourly": {
        "task": "app.jobs.tasks.reclassify_floored_comments",
        "schedule": crontab(minute="45"),
    },
    # E3-06's weekly recompute of SPEC §3.4's participation score: every section
    # still inside the sweep's own term bound, every student holding a live
    # enrollment, posted only where the computed value differs from the last one
    # sent (ADR 0137).
    #
    # **Monday** because §3.1 closes every window on Sunday at 23:59:59 in the
    # institution's timezone, so Monday is the first day on which the week that
    # just ended can be scored at all. A run on any other day either scores a week
    # that has not finished or leaves the finished one unposted for up to six days,
    # which is a delay a student sees.
    #
    # **02:20** because the reclassification entry above runs at 00:45 and 01:45,
    # so by then the floored comments of the week that just closed have had two
    # attempts at a real verdict — a sweep in front of them posts a score computed
    # from provisional verdicts and then posts again when they land, turning §3.3's
    # fail-open promise into two visible grade changes for one week. The minute is
    # 20 rather than a rounder one because 0, 15, 30 and 45 are already taken by
    # the entries beside it, three of which walk every section in the institution.
    #
    # Weekly rather than hourly because the sweep is idempotent but not free: it
    # reads every enrolled student's answers in every live term, and an hourly run
    # would pay that to discover a difference that only a week's close or a late
    # reclassification can produce. A reclassification arriving mid-week waits for
    # the next Monday, which ADR 0137 records as the cost.
    "post-participation-scores-weekly": {
        "task": "app.jobs.tasks.post_participation_scores",
        "schedule": crontab(day_of_week="mon", hour="2", minute="20"),
    },
}
