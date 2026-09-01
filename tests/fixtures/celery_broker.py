"""A real Redis broker, on the image the stack deploys — E0-03's, shared from E2-04.

`tests/integration/test_celery_ping_roundtrip.py` built this for the `ping` round
trip and was the only caller. E2-04 adds a second: the development clock override
has to reach a Celery worker, and proving that needs the same broker started the
same way. Two copies of "which Redis does this project run" is
`docs/MISTAKES.md` entry 13 exactly — a question answered at one of the two sites
facing it — so the answer moved here and both modules ask for `broker_url` by name.

**The image is read out of `docker-compose.yml`**, not pinned a second time here,
for the reason `tests/unit/test_image_pins_agree.py` gives about the Postgres in
the migration-drift job: a round trip proved against a Redis the project does not
deploy is a proof about a different system.

**The CI `test` job has a Docker daemon and no Compose stack**, so a container
started by testcontainers is how a host-side test gets a broker at all.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

# `testcontainers.community.redis`, not `testcontainers.redis`: on the locked
# testcontainers 4.15.0 the shorter path raises a DeprecationWarning at import,
# and `filterwarnings = ["error::DeprecationWarning"]` in pyproject.toml turns
# that into a collection error that aborts the whole run.
from testcontainers.community.redis import RedisContainer

REDIS_SERVICE_NAME = "redis"
REDIS_CONTAINER_PORT = 6379

# The variable the application reads its broker and result backend out of.
REDIS_URL_VARIABLE = "REDIS_URL"


@pytest.fixture
def broker_url(base_compose: dict[str, Any], base_compose_path: Path) -> Iterator[str]:
    """A real Redis, on the image the stack runs, reachable from this process.

    **Started per test rather than per session**, and now that two modules use it
    the reason is stronger than when E0-03 wrote it: a shared broker would let a
    result left by one test satisfy another, and the two tests using this ask
    different questions of the same task name. If the start ever becomes the cost
    that matters, widen the scope deliberately and say what stops the tests
    sharing state.
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
