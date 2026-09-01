"""A Celery worker reads the same clock the backend does — E2-04, criterion 2.

"In development, setting the pretend now from `/dev` changes what the backend
**and the worker** both answer; clearing it returns them to real time." The
backend half is `tests/integration/test_the_dev_console_sets_and_clears_the_clock.py`;
this is the worker half, and it is the reason the override is a database row at
all. A process-local override — an environment variable, a module global, a
monkeypatched function — would move the API container and leave the worker
running on real time, and E2-06's weekly scheduling runs in the worker. The two
processes agreeing is the whole design, so it is asserted across a real broker
rather than in one interpreter.

**The shape is E0-03's**, `tests/integration/test_celery_ping_roundtrip.py`: a
Redis container on the image the Compose file names, and a real Celery worker
started in a thread by `celery.contrib.testing.worker.start_worker`. The broker
fixture is shared with that module from `tests/fixtures/celery_broker.py` —
E2-04 moved it there when this became the second caller, because two copies of
"which Redis does this project run" is `docs/MISTAKES.md` entry 13.

**The task is `effective_now`**, which E2-04 adds beside `ping` in
`app.jobs.tasks`: it opens a session the way every task there does and answers
`clock.now(...)` as an ISO string. It is a permanent stack probe on the same
justification `ping` has — the round trip it proves is not provable any other way.

**The environment is stated by this module** (`docs/MISTAKES.md` entry 40): the
container's database coordinates through `care_service_environment`, the broker
this test started through `REDIS_URL`, and `ENVIRONMENT` set to `development`
explicitly rather than inherited from `.env.example`'s value, because whether the
override applies at all is decided by exactly that variable.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

import pytest
from celery.contrib.testing.worker import start_worker
from fixtures.celery_broker import REDIS_URL_VARIABLE
from fixtures.clock import DEVELOPMENT, ENVIRONMENT_VARIABLE

pytestmark = pytest.mark.integration

CELERY_APP_MODULE = "app.jobs.celery_app"
TASKS_MODULE = "app.jobs.tasks"
EFFECTIVE_NOW_TASK_ATTRIBUTE = "effective_now"

# The pretended instant, five years out so no tolerance a test could choose could
# confuse it with real time (`docs/MISTAKES.md` entry 30). Written here rather
# than shared with the service suite deliberately: each module chooses the value
# it is about, so an edit made for one cannot silently change what another asserts.
PRETEND_NOW = datetime(2031, 3, 14, 10, 30, tzinfo=UTC)

# How far from the expected instant an answer may land. Generous, because it has
# to cover a task's queue time, a worker's wake-up and a database round trip on a
# cold CI runner; tiny beside the five years between the two possible answers.
TOLERANCE = timedelta(minutes=5)

# E0-03's numbers, and its reasoning: long enough that a cold runner starting a
# worker is not a flake, short enough that a task that never returns fails the job
# in under a minute.
RESULT_TIMEOUT_SECONDS = 30.0
WORKER_SHUTDOWN_SECONDS = 30.0


def answered_instant(value: Any, what: str) -> datetime:
    """The instant a task answered, parsed, with both ways it could be wrong named."""
    assert isinstance(value, str), (
        f"{what} answered {value!r}, which is not a string. E2-04's work order settles "
        f"`{EFFECTIVE_NOW_TASK_ATTRIBUTE}` as returning the effective now as an ISO string — a "
        "datetime does not survive the JSON serializer Celery is configured with, so a task that "
        "returned one would fail in the worker rather than here."
    )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as bad:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"{what} answered {value!r}, which is not an ISO 8601 instant ({bad}). The task's whole "
            "job is to report what `clock.now` said in a form another process can compare."
        )
    assert parsed.utcoffset() is not None, (
        f"{what} answered {value!r}, which carries no UTC offset. `clock.now` answers a "
        "timezone-aware instant (ADR 0019 keeps naive datetimes out of this codebase), and an ISO "
        "string that drops the offset is a different moment on every reader."
    )
    return parsed


def test_the_worker_answers_the_overridden_clock_and_real_time_once_it_is_cleared(
    configured_env: dict[str, str],
    care_service_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    broker_url: str,
    committed_clock_overrides: Any,
    import_app_module: Callable[[str], ModuleType | None],
    celery_application_in: Callable[[ModuleType], Any],
) -> None:
    """Criterion 2's worker half, both directions, across a real broker.

    **The mutation this kills**: an override that lives anywhere but the database —
    a module global set by the `/dev` handler, an environment variable, a cached
    offset computed once per process. Every one of those moves the API container
    and leaves the worker on real time, and the disagreement is invisible until
    E2-06 schedules a window in one process and reads it in the other.

    **The near miss it must not pass on**: a worker that reads the row once and
    keeps the offset. That is what the second half is for — the row is cleared
    while the same worker is still running, and the next answer has to be real
    time again. A worker whose session held an open transaction from the first
    call would also fail there, which is the same defect wearing a different hat.

    **Why this is one test and not two.** The claim is a transition — the answer
    moves, then comes back — and splitting it would leave the second half asserting
    against a state the first half produced, on a worker the second half would have
    to start again. E0-03's own round-trip test states the same reason.

    **The preconditions are not ceremony.** Each is a way this test could go green
    while proving nothing, and they are the ones `test_celery_ping_roundtrip.py`
    enumerates, for the same reasons: eager mode runs the task in this process and
    never touches the broker; an application ignoring `REDIS_URL` would, on a
    developer's machine with the Compose stack up, pass against a Redis it never
    configured; and a result backend that is not Redis makes `get()` block rather
    than fail on a line that says why.
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, DEVELOPMENT)
    monkeypatch.setenv(REDIS_URL_VARIABLE, broker_url)

    celery_module = import_app_module(CELERY_APP_MODULE)
    assert celery_module is not None, (
        f"`{CELERY_APP_MODULE}` does not exist. E0-03 ships it under `backend/app/jobs/` "
        "(SPEC §13)."
    )
    tasks_module = import_app_module(TASKS_MODULE)
    assert tasks_module is not None, (
        f"`{TASKS_MODULE}` does not exist. E0-03 ships `ping` there and E2-04 adds "
        f"`{EFFECTIVE_NOW_TASK_ATTRIBUTE}` beside it."
    )

    application = celery_application_in(celery_module)
    assert application is not None, (
        f"`{CELERY_APP_MODULE}` exposes no Celery application at module level, so there is nothing "
        "for `celery -A` — or for this test — to run tasks with."
    )
    effective_now = getattr(tasks_module, EFFECTIVE_NOW_TASK_ATTRIBUTE, None)
    assert effective_now is not None and hasattr(effective_now, "delay"), (
        f"`{TASKS_MODULE}.{EFFECTIVE_NOW_TASK_ATTRIBUTE}` is missing or is not a Celery task: it "
        "has no `.delay`, so it cannot be enqueued. E2-04 adds it as the diagnostic that proves "
        "the worker and the backend read one clock."
    )

    assert not application.conf.task_always_eager, (
        "`task_always_eager` is set, so `delay()` runs the task in this process and returns an "
        "EagerResult. Every assertion below would pass without a worker existing, which defeats "
        "the entire point of this test: the claim is that a *separate* process reads the same "
        "override."
    )
    assert urlsplit(str(application.conf.broker_url)).port == urlsplit(broker_url).port, (
        f"The application's broker is {application.conf.broker_url!r}, not the Redis this test "
        f"started ({broker_url}). It ignored {REDIS_URL_VARIABLE}."
    )
    assert str(application.conf.result_backend or "").startswith("redis"), (
        f"The result backend is {application.conf.result_backend!r}; with no backend, `get()` "
        "below blocks or raises instead of failing on this line, which says less."
    )

    committed_clock_overrides.set(pretend_now=PRETEND_NOW, anchored_at=datetime.now(UTC))
    assert len(committed_clock_overrides.rows()) == 1, (
        f"`clock_override` holds {committed_clock_overrides.rows()} rather than the single row "
        "this test committed. The worker connects for itself and sees only what has been "
        "committed, so an uncommitted row would make the first assertion below fail for a reason "
        "that has nothing to do with the worker."
    )

    with start_worker(
        application,
        perform_ping_check=False,
        shutdown_timeout=WORKER_SHUTDOWN_SECONDS,
    ):
        moved = answered_instant(
            effective_now.delay().get(timeout=RESULT_TIMEOUT_SECONDS),
            f"`{EFFECTIVE_NOW_TASK_ATTRIBUTE}` with the clock overridden",
        )
        assert PRETEND_NOW - TOLERANCE <= moved <= PRETEND_NOW + TOLERANCE, (
            f"The worker answered {moved!r} while `clock_override` pretended it was "
            f"{PRETEND_NOW!r}. Real time is about {datetime.now(UTC)!r}, five years away. A "
            "worker on real time here is an override that lives in the API process rather than "
            "in the database — which is precisely what E2-04 stores a row to avoid."
        )

        committed_clock_overrides.clear()
        assert committed_clock_overrides.rows() == [], (
            f"The clear left {committed_clock_overrides.rows()} in `clock_override`, so the "
            "assertion below would be about an override that is still standing."
        )

        before = datetime.now(UTC)
        restored = answered_instant(
            effective_now.delay().get(timeout=RESULT_TIMEOUT_SECONDS),
            f"`{EFFECTIVE_NOW_TASK_ATTRIBUTE}` with the override cleared",
        )
        after = datetime.now(UTC)

    assert before - TOLERANCE <= restored <= after + TOLERANCE, (
        f"The worker answered {restored!r} after the override row was deleted, and real time ran "
        f"from {before!r} to {after!r} around the call. The same worker answered the pretended "
        "instant a moment earlier, so this is an offset cached for the life of the process, or a "
        "session holding a transaction open from the first call — either way, clearing the clock "
        "from `/dev` would appear to do nothing until the worker restarted."
    )
