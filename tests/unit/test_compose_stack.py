"""Compose topology properties no running stack can check — ticket E0-02.

Almost every acceptance criterion in E0-02 needs Docker: the stack reaching
healthy, `curl localhost:8000/healthz`, `down -v` then `up -d` twice, and the
API container's `id -u`. Those are the CI `docker` job's job, and the ticket's
definition of done says so plainly — "the health gate in CI is the test". None
of them are restated here.

What is here is the small set of properties that go green in every dynamic
check and are still wrong. There are two kinds:

1.  **Host port publishing belongs to the dev override, not the base file.**
    The definition of done names an exposed port in the base Compose file as a
    security defect, and SPEC §7.2 puts the reverse proxy outside the compose
    file entirely. No dynamic gate can see this: `docker compose up` merges
    `docker-compose.override.yml` automatically, so CI and a developer's laptop
    both exercise the merged topology and never the base file alone. A `ports:`
    entry added to the base file publishes Postgres to the host of every
    non-development deployment and breaks nothing anyone runs.

2.  **Declarations `wait_for_health.sh api` does not reach.** That script fails
    a service that declares no health check, which is why the api health check
    needs no test — but E0-02 names `api` alone, so nothing waits on `redis`,
    and nothing checks that `api` waits for `db`. In E0-02 the api health check
    does not touch Postgres (see `.env.example`: nothing connects to the
    database yet), so a missing `depends_on` condition passes the whole
    pipeline today and starts mattering silently in E0-04.

Each test asserts the property rather than a spelling: `expose:` is not
`ports:`, a health check is not a particular command, and `depends_on` as a
plain list is a different thing from `depends_on` with a health condition.
Where Compose allows several spellings of the same property, all of them are
accepted.

Parsing is `yaml.safe_load` over the raw files, deliberately: `docker compose
config` would merge the override back in and hide the property in item 1. That
means Compose's own `!reset` and `!override` YAML tags would raise here rather
than parse; nothing in this ticket's scope needs them.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
OVERRIDE_COMPOSE_PATH = REPO_ROOT / "docker-compose.override.yml"

# Named in acceptance criterion 2 — `curl localhost:8000/healthz` returns 200 —
# so this is the ticket's number, not a choice made here.
API_HOST_PORT = "8000"


def load_compose(path: Path) -> dict[str, Any]:
    """Parse one Compose file on its own, with no override merged in.

    Returns an empty mapping when the file is absent, so that a test reports a
    failed assertion naming the missing deliverable rather than a fixture
    error. Every test below asserts the document is non-empty before drawing a
    conclusion from it, because "no services declare ports" is true of a file
    that does not exist.
    """
    if not path.is_file():
        return {}
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return document if isinstance(document, dict) else {}


def services_of(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The `services` block, with each empty service body normalised to a mapping."""
    services = document.get("services") or {}
    if not isinstance(services, dict):
        return {}

    normalised: dict[str, dict[str, Any]] = {}
    for name, body in services.items():
        if body is None:
            normalised[name] = {}
        elif isinstance(body, dict):
            normalised[name] = body
    return normalised


def host_ports_published_by(service: dict[str, Any]) -> set[str]:
    """Host-side ports this service publishes, across all of Compose's spellings.

    Handles the short forms (`"8000:8000"`, `"127.0.0.1:8000:8000"`, with or
    without a `/tcp` suffix) and the long form (`{target: 8000, published:
    8000}`). A bare container port (`"8000"`) publishes to a host port the
    daemon picks, so it contributes nothing: no fixed host port is declared.
    """
    published: set[str] = set()
    for entry in service.get("ports") or []:
        if isinstance(entry, dict):
            value = entry.get("published")
            if value is not None:
                published.add(str(value))
            continue
        parts = str(entry).rsplit("/", 1)[0].split(":")
        if len(parts) >= 2:
            published.add(parts[-2])
    return published


def test_base_compose_file_publishes_no_host_ports() -> None:
    """The base file binds nothing to the host; that is the dev override's job.

    E0-02 definition of done, security review: "an unnecessarily exposed port in
    the base Compose file (as opposed to the dev override)". SPEC §7.2 puts the
    reverse proxy or tunnel outside the compose file, so the base file has no
    port to publish. `expose:` is untouched by this — it publishes nothing to
    the host.
    """
    base = load_compose(BASE_COMPOSE_PATH)
    assert base, (
        f"{BASE_COMPOSE_PATH} does not exist or declares nothing. E0-02 ships the base "
        "Compose file at the repository root (SPEC §13)."
    )

    publishing = {
        name: sorted(ports)
        for name, body in services_of(base).items()
        if (ports := host_ports_published_by(body))
    }

    assert not publishing, (
        f"docker-compose.yml publishes ports to the host: {publishing}. Host port "
        "publishing belongs in docker-compose.override.yml, which is development-only. "
        "A port published here is published in every deployment that runs the base file "
        "alone, and no dynamic check can see it because `docker compose up` merges the "
        "override in. Use `expose:` if the intent is documentation."
    )


def test_dev_override_publishes_the_api_port_to_the_host() -> None:
    """The dev override is where host publishing lives, and it publishes the API.

    The paired half of the test above: a stack that publishes nothing anywhere
    satisfies "the base file publishes nothing" and fails acceptance criterion
    2, `curl localhost:8000/healthz`. Together the two assert the real property
    — publishing happens, and only in the override.
    """
    override = load_compose(OVERRIDE_COMPOSE_PATH)
    assert override, (
        f"{OVERRIDE_COMPOSE_PATH} does not exist or declares nothing. E0-02 ships the "
        "development override with the source bind-mount, hot reload, and exposed ports."
    )

    api = services_of(override).get("api")
    assert api is not None, (
        "docker-compose.override.yml declares no `api` service, so nothing publishes the "
        f"API to the host and `curl localhost:{API_HOST_PORT}/healthz` cannot reach it."
    )

    published = host_ports_published_by(api)
    assert API_HOST_PORT in published, (
        f"The dev override publishes host ports {sorted(published) or 'none'} for `api`, "
        f"not {API_HOST_PORT}. Acceptance criterion 2 is `curl localhost:{API_HOST_PORT}"
        "/healthz` returns 200 against the running stack."
    )


@pytest.mark.parametrize("service_name", ["db", "redis"])
def test_backing_service_declares_a_health_check(service_name: str) -> None:
    """`db` and `redis` each declare a health check in the base file.

    Acceptance criterion 1 — the stack "reaches healthy on `api`, `db`, and
    `redis`" — and the scope list, which names `pg_isready` and `redis-cli
    ping`. The command is not asserted; only that the service can report
    whether it works.

    The base file and not the merged view, on purpose. A health check that lives
    in the development override is absent from every other deployment, and
    `depends_on: {db: {condition: service_healthy}}` has nothing to wait on
    there. Neither image ships a `HEALTHCHECK` of its own, so Compose is the
    only place this can be declared.
    """
    base = load_compose(BASE_COMPOSE_PATH)
    assert base, (
        f"{BASE_COMPOSE_PATH} does not exist or declares nothing. E0-02 ships the base "
        "Compose file at the repository root (SPEC §13)."
    )

    service = services_of(base).get(service_name)
    assert service is not None, (
        f"docker-compose.yml declares no `{service_name}` service. E0-02 brings up `api`, "
        "`db`, `redis`, and `mailpit` (SPEC §7.2)."
    )

    healthcheck = service.get("healthcheck")
    assert healthcheck, (
        f"`{service_name}` declares no healthcheck in docker-compose.yml. Without one the "
        "service reports no health at all, which `scripts/ci/wait_for_health.sh` treats as "
        "a configuration gap rather than as healthy — and nothing else in the pipeline "
        f"waits on `{service_name}`, so its absence is otherwise invisible."
    )


def test_api_waits_for_a_healthy_database() -> None:
    """`api` starts only after `db` reports healthy, not merely after it exists.

    From the scope list, spelled out there exactly: `api` declares
    `depends_on: {db: {condition: service_healthy}}`. The short list form,
    `depends_on: [db]`, waits for the container to start and not for Postgres to
    accept connections, which is a different guarantee rather than a different
    style. Nothing catches the difference today — in E0-02 the API's health
    check does not touch the database — and it starts mattering in E0-04.
    """
    base = load_compose(BASE_COMPOSE_PATH)
    assert base, (
        f"{BASE_COMPOSE_PATH} does not exist or declares nothing. E0-02 ships the base "
        "Compose file at the repository root (SPEC §13)."
    )

    api = services_of(base).get("api")
    assert api is not None, "docker-compose.yml declares no `api` service."

    depends_on = api.get("depends_on")
    assert isinstance(depends_on, dict), (
        f"`api` declares `depends_on: {depends_on!r}`. The list form waits for the `db` "
        "container to start, not for Postgres to accept connections. E0-02 requires the "
        "long form with a health condition."
    )

    db_dependency = depends_on.get("db") or {}
    condition = db_dependency.get("condition") if isinstance(db_dependency, dict) else None
    assert condition == "service_healthy", (
        f"`api` waits on `db` with condition {condition!r}, not 'service_healthy'. The API "
        "must not start against a Postgres that is not yet accepting connections."
    )
