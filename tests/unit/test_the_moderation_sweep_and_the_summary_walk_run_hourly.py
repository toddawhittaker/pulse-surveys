"""The two hourly entries ADR 0188 settles, and how they line up with the Monday report.

The moderation sweep runs at minute 10 and the summary walk at minute 50. A
window closes on Sunday at 23:59:59 and the report opens at 06:00 on Monday
(ADR 0184), so an ordinary week is moderated at 00:10 and summarized at 00:50.
"""

from typing import Any


def beat_schedule() -> dict[str, Any]:
    from app.jobs.schedules import BEAT_SCHEDULE

    return BEAT_SCHEDULE


def test_the_moderation_sweep_runs_hourly_at_minute_ten(configured_env: dict[str, str]) -> None:
    from celery.schedules import crontab

    entry = beat_schedule()["moderate-closed-windows-hourly"]
    assert entry["task"] == "app.jobs.tasks.moderate_closed_windows"
    assert entry["schedule"] == crontab(minute="10")


def test_the_summary_walk_runs_forty_minutes_after_the_sweep_every_hour(
    configured_env: dict[str, str],
) -> None:
    from celery.schedules import crontab

    entry = beat_schedule()["generate-weekly-summaries"]
    assert entry["schedule"] == crontab(minute="50")
    assert entry["schedule"] != crontab(day_of_week="mon", hour="2", minute="50")


def test_the_sweep_task_is_registered_and_beat_can_fire_it_without_arguments(
    configured_env: dict[str, str],
) -> None:
    import inspect

    from app.jobs.celery_app import celery_app
    from app.jobs.tasks import moderate_closed_windows

    assert moderate_closed_windows.name in celery_app.tasks
    parameters = inspect.signature(moderate_closed_windows.run).parameters.values()
    assert all(parameter.default is not parameter.empty for parameter in parameters)
