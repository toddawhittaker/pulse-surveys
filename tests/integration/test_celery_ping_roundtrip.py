"""`ping` goes out through Redis and its result comes back — ticket E0-03.

Acceptance criterion 2: "Calling the `ping` task from the API container returns
its result through the Redis backend within a timeout." The definition of done
asks for exactly one integration test for it, marked `integration`, and puts it
here because it needs a broker.

**What is a real broker and what is not.** The broker is a Redis container
started by testcontainers, running the same image `docker-compose.yml` gives the
`redis` service — read out of the Compose file rather than pinned a second time
here, for the reason `test_image_pins_agree.py` gives about the Postgres in the
migration-drift job: a round trip proved against a Redis the project does not
deploy proves something about a different system. The worker is a real Celery
worker, started in a thread by `celery.contrib.testing.worker.start_worker`
against that broker. The CI `test` job has a Docker daemon and no Compose stack,
so the container is how this test gets a broker at all.

**Criterion 2 says "from the API container", and this test does not run there.**
What the container adds over this test is the network path from `api` to
`redis` and the worker being a separate process — both of which the `docker`
job exercises, and neither of which pytest can. What this test holds that no
container check does is the part that survives the stack: that the application's
own `ping`, enqueued through its own configuration, comes back as a result and
not as a timeout. The two halves are listed in the report for this ticket rather
than left implied.

**Why this is not two tests.** Enqueue-and-return is one behaviour; splitting it
into "it was enqueued" and "a result came back" would need the second half to
assert against a result the first half produced, which is one test written in
two places. The preconditions below assert separately because each is a
different, specific way this test could go green while proving nothing.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

import pytest
from celery.contrib.testing.worker import start_worker

# `testcontainers.community.redis`, not `testcontainers.redis`: on the locked
# testcontainers 4.15.0 the shorter path raises a DeprecationWarning at import,
# and `filterwarnings = ["error::DeprecationWarning"]` in pyproject.toml turns
# that into a collection error that aborts the whole run. Moving the import is
# the fix; a warning filter here would suppress the pyproject setting for
# everything else this module imports, Celery included.
from testcontainers.community.redis import RedisContainer

# The definition of done names the marker. `pyproject.toml` describes it as
# testcontainers-backed, which this is; its description was widened in this same
# change because it named Postgres specifically and this test needs a broker.
pytestmark = pytest.mark.integration

CELERY_APP_MODULE = "app.jobs.celery_app"
TASKS_MODULE = "app.jobs.tasks"
PING_TASK_ATTRIBUTE = "ping"

REDIS_URL_VARIABLE = "REDIS_URL"
REDIS_SERVICE_NAME = "redis"
REDIS_CONTAINER_PORT = 6379

# The criterion says "within a timeout" and does not give a number, so this is
# **this test's choice**. Generous enough that a cold CI runner pulling an image
# and starting a worker is not a flake, short enough that a task that never
# returns fails the job in under a minute rather than sitting on the six-hour
# GitHub Actions ceiling.
RESULT_TIMEOUT_SECONDS = 30.0
WORKER_SHUTDOWN_SECONDS = 30.0


@pytest.fixture
def broker_url(base_compose: dict[str, Any], base_compose_path: Path) -> Iterator[str]:
    """A real Redis, on the image the stack runs, reachable from this process.

    Started per test rather than per session: there is one test in this module,
    and a shared broker would let a leftover result from one test satisfy
    another. If a second test arrives and the second start becomes expensive,
    widen the scope deliberately and say what stops the two sharing state.
    """
    services = base_compose.get("services") or {}
    service = services.get(REDIS_SERVICE_NAME) or {}
    image = service.get("image") if isinstance(service, dict) else None

    if not isinstance(image, str) or not image:
        pytest.fail(
            f"{base_compose_path} declares no image for the `{REDIS_SERVICE_NAME}` service, so "
            "this test has no broker image to run and cannot fall back to one without testing "
            "a Redis the project does not deploy. SPEC §7.2 runs Redis as the broker and "
            "result backend; E0-02 ships the service."
        )

    with RedisContainer(image=image) as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(REDIS_CONTAINER_PORT)
        yield f"redis://{host}:{port}/0"


def test_ping_result_comes_back_through_the_redis_backend(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    broker_url: str,
    import_app_module: Callable[[str], ModuleType | None],
    celery_application_in: Callable[[ModuleType], Any],
) -> None:
    """Criterion 2: enqueue `ping`, get its result back within the timeout.

    The three preconditions between the imports and the worker are each a way
    this test could pass while proving nothing, and none of them is ceremony:

      - **Eager mode.** With `task_always_eager` set, `delay()` runs the task in
        this process and hands back an `EagerResult`. Every assertion below
        would pass and the broker would never be touched.
      - **A broker that is not the one this test started.** If the application
        ignored `REDIS_URL` and kept a literal `redis://redis:6379/0`, then on a
        developer's machine with the Compose stack up this test would pass
        against *that* Redis and prove nothing about the configured one. On CI
        it would hang instead, which is a slower way to learn the same thing.
      - **A result backend that is not Redis.** The criterion names the backend,
        not just the queue: a result that never leaves the process is not the
        round trip the ticket asks about.

    What is asserted about the result deliberately stops short of its value. The
    ticket says `ping` is trivial and does not say what it returns, so `"pong"`
    is not asserted; that the task reached a worker and its result travelled
    back is the whole of criterion 2, and `AsyncResult.get()` returning at all
    means the backend delivered a record for it.
    """
    monkeypatch.setenv(REDIS_URL_VARIABLE, broker_url)

    celery_module = import_app_module(CELERY_APP_MODULE)
    assert celery_module is not None, (
        f"`{CELERY_APP_MODULE}` does not exist. E0-03 ships it under `backend/app/jobs/` "
        "(SPEC §13)."
    )
    tasks_module = import_app_module(TASKS_MODULE)
    assert tasks_module is not None, (
        f"`{TASKS_MODULE}` does not exist. E0-03 ships one trivial `ping` task there, used "
        "only to prove this round trip."
    )

    application = celery_application_in(celery_module)
    assert application is not None, (
        f"`{CELERY_APP_MODULE}` exposes no Celery application at module level, so there is "
        "nothing for `celery -A` — or for this test — to run tasks with."
    )
    ping = getattr(tasks_module, PING_TASK_ATTRIBUTE, None)
    assert ping is not None and hasattr(ping, "delay"), (
        f"`{TASKS_MODULE}.{PING_TASK_ATTRIBUTE}` is missing or is not a Celery task: it has "
        "no `.delay`, so it cannot be enqueued."
    )

    assert not application.conf.task_always_eager, (
        "`task_always_eager` is set, so `delay()` runs the task in this process and returns "
        "an EagerResult. Every assertion below would pass without the broker existing, which "
        "is the one outcome this test must not have."
    )
    assert urlsplit(str(application.conf.broker_url)).port == urlsplit(broker_url).port, (
        f"The application's broker is {application.conf.broker_url!r}, not the Redis this "
        f"test started ({broker_url}). It ignored {REDIS_URL_VARIABLE}. Where a developer "
        "has the Compose stack running, a literal `redis://redis:6379/0` would make this "
        "test pass against a broker it never configured."
    )
    assert str(application.conf.result_backend or "").startswith("redis"), (
        f"The result backend is {application.conf.result_backend!r}. Criterion 2 is that the "
        "result comes back *through the Redis backend*; with no backend, `get()` below "
        "raises or blocks forever instead of failing on this line, which says less."
    )

    with start_worker(
        application,
        perform_ping_check=False,
        shutdown_timeout=WORKER_SHUTDOWN_SECONDS,
    ):
        async_result = ping.delay()
        value = async_result.get(timeout=RESULT_TIMEOUT_SECONDS)

    assert async_result.successful(), (
        f"`ping` finished in state {async_result.state!r} rather than succeeding, and the "
        f"result carried back was {value!r}."
    )
