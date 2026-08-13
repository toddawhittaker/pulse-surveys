"""Properties of the Compose files that no running stack checks — ticket E0-02.

Almost every acceptance criterion in E0-02 needs Docker: the stack reaching
healthy, `curl localhost:8000/healthz`, `down -v` then `up -d` twice, and the
API container's `id -u`. Those are the CI `docker` job's job, and the ticket's
definition of done says so plainly — "the health gate in CI is the test". None
of them are restated here.

What is here is the small set of properties that go green in every dynamic
check and are still wrong. There are three kinds:

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
    needs no test here. `db` and `redis` are reached only through `api`'s
    `depends_on`, so the conditions on it are load-bearing for the health gate
    covering acceptance criterion 1 at all. In E0-02 the api health check does
    not touch Postgres, so a `depends_on` weakened to the list form passes the
    whole pipeline today and starts mattering silently in E0-04.

3.  **The superuser credential does not reach an application container.**
    ADR 0009 sanctions a superuser role and bounds it with two rules. That the
    application must never *connect* as it is asserted in
    `test_env_example_resolves.py`; that the credential must never *reach* the
    application is asserted here. `api` pulls the whole of `.env` in through
    `env_file`, superuser pair included, and blanks both in its own
    `environment:` block to take them back out — two hand-written lines on one
    service, with nothing checking them. E0-03 adds `worker` and `beat`
    "sharing the API image", and the natural way to write that is to copy the
    `api` block; copy it without those two lines and both containers hold
    `replace-me-admin`, with `db:5432` reachable from them and its `pg_hba.conf`
    accepting that role over scram. Those are also the containers that will run
    E0-13's gateway over untrusted comment text.

A property that used to be asserted here and no longer is: that the dev
override publishes the API on host port 8000. The `docker` job now makes a real
request to `http://localhost:8000/healthz` against the running stack, which
proves the port is published, reachable, and answering. A static assertion about
where the port is declared is strictly weaker than that, and it also pinned a
spelling the ticket left open, so it went when the real check arrived. It was
the paired half of the base-file test above — without it, publishing nothing
anywhere would satisfy that test — and CI now holds that half.

Each test asserts the property rather than a spelling: `expose:` is not
`ports:`, a health check is not a particular command, and `depends_on` as a
plain list is a different thing from `depends_on` with a health condition.
Where Compose allows several spellings of the same property, all of them are
accepted.

The Compose files are parsed in `tests/conftest.py`, unmerged and one at a time,
which is the whole point of item 1 — `docker compose config` would merge the
override back in and hide it.

Everything below reads the base file, because that is the one every deployment
runs and the one E0-03 will add services to. The override is out of scope
deliberately: judging it would mean modelling Compose's merge rules for
`env_file` and `environment`, and those rules are not something to guess at
without a daemon to check the guess against.
"""

from pathlib import Path
from typing import Any

import pytest

# The credential ADR 0009 bounds. Named here rather than derived, because these
# two are the subject of the rule rather than an incidental pair of variables;
# a third would be a change to the ADR and should be a deliberate edit here too.
SUPERUSER_VARIABLES = ("DB_SUPERUSER", "DB_SUPERUSER_PASSWORD")


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


def declares_env_file(service: dict[str, Any]) -> bool:
    """Whether this service pulls a whole env file into its container.

    Three spellings, all of which hand the file's entire contents over: a bare
    string, a list of strings, and the Compose 2.24 list of mappings with a
    `path:` key. Which file is not inspected — requiring the blanking of a
    service that turns out to read some other env file costs nothing, and
    getting it wrong in the other direction is the failure this test exists to
    prevent.
    """
    declared = service.get("env_file")
    return bool(declared) and isinstance(declared, str | list)


def service_environment(service: dict[str, Any]) -> dict[str, str | None]:
    """A service's `environment:` block, in either syntax, as a mapping.

    Compose accepts a mapping (`DB_SUPERUSER: ''`) and a list
    (`- DB_SUPERUSER=`) and means the same thing by them, so a test that
    understood only one would quietly stop checking if someone switched.

    `None` is the third case and a different thing again: `FOO:` in a mapping
    and a bare `- FOO` in a list both mean "pass this through from the host
    environment", which supplies a value rather than clearing one. It is kept
    distinct from `""` for that reason.
    """
    declared = service.get("environment")
    resolved: dict[str, str | None] = {}

    if isinstance(declared, dict):
        for key, value in declared.items():
            resolved[str(key)] = None if value is None else str(value)
    elif isinstance(declared, list):
        for entry in declared:
            if not isinstance(entry, str):
                continue
            name, separator, value = entry.partition("=")
            resolved[name.strip()] = value if separator else None

    return resolved


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


def test_base_compose_file_publishes_no_host_ports(
    base_compose_path: Path,
    base_compose: dict[str, Any],
) -> None:
    """The base file binds nothing to the host; that is the dev override's job.

    E0-02 definition of done, security review: "an unnecessarily exposed port in
    the base Compose file (as opposed to the dev override)". SPEC §7.2 puts the
    reverse proxy or tunnel outside the compose file, so the base file has no
    port to publish. `expose:` is untouched by this — it publishes nothing to
    the host.
    """
    assert base_compose, (
        f"{base_compose_path} does not exist or declares nothing. E0-02 ships the base "
        "Compose file at the repository root (SPEC §13)."
    )

    publishing = {
        name: sorted(ports)
        for name, body in services_of(base_compose).items()
        if (ports := host_ports_published_by(body))
    }

    assert not publishing, (
        f"docker-compose.yml publishes ports to the host: {publishing}. Host port "
        "publishing belongs in docker-compose.override.yml, which is development-only. "
        "A port published here is published in every deployment that runs the base file "
        "alone, and no dynamic check can see it because `docker compose up` merges the "
        "override in. Use `expose:` if the intent is documentation."
    )


@pytest.mark.parametrize("service_name", ["db", "redis"])
def test_backing_service_declares_a_health_check(
    service_name: str,
    base_compose_path: Path,
    base_compose: dict[str, Any],
) -> None:
    """`db` and `redis` each declare a health check in the base file.

    Acceptance criterion 1 — the stack "reaches healthy on `api`, `db`, and
    `redis`" — and the scope list, which names `pg_isready` and `redis-cli
    ping`. The command is not asserted; only that the service can report
    whether it works.

    The base file and not the merged view, on purpose. A health check that lives
    in the development override is absent from every other deployment, and
    `depends_on: {condition: service_healthy}` has nothing to wait on there.
    Neither image ships a `HEALTHCHECK` of its own, so Compose is the only place
    this can be declared.
    """
    assert base_compose, (
        f"{base_compose_path} does not exist or declares nothing. E0-02 ships the base "
        "Compose file at the repository root (SPEC §13)."
    )

    service = services_of(base_compose).get(service_name)
    assert service is not None, (
        f"docker-compose.yml declares no `{service_name}` service. E0-02 brings up `api`, "
        "`db`, `redis`, and `mailpit` (SPEC §7.2)."
    )

    healthcheck = service.get("healthcheck")
    assert healthcheck, (
        f"`{service_name}` declares no healthcheck in docker-compose.yml. Without one the "
        "service reports no health at all, which `scripts/ci/wait_for_health.sh` treats as "
        "a configuration gap rather than as healthy — and the health gate reaches "
        f"`{service_name}` only through `api`'s depends_on, so its absence is otherwise "
        "invisible."
    )


@pytest.mark.parametrize("dependency", ["db", "redis"])
def test_api_waits_for_a_healthy_dependency(
    dependency: str,
    base_compose_path: Path,
    base_compose: dict[str, Any],
) -> None:
    """`api` starts only after its backing services report healthy.

    From the scope list, spelled out there exactly: `api` declares
    `depends_on: {db: {condition: service_healthy}}`. The short list form,
    `depends_on: [db]`, waits for the container to start and not for Postgres to
    accept connections, which is a different guarantee rather than a different
    style.

    Both conditions are asserted because the health gate leans on them. CI calls
    `wait_for_health.sh api` alone, and that covers acceptance criterion 1 —
    `api`, `db`, and `redis` all healthy — only for as long as `api` waits on
    both. Weaken either condition and the gate silently stops checking a
    service while still reporting green.
    """
    assert base_compose, (
        f"{base_compose_path} does not exist or declares nothing. E0-02 ships the base "
        "Compose file at the repository root (SPEC §13)."
    )

    api = services_of(base_compose).get("api")
    assert api is not None, "docker-compose.yml declares no `api` service."

    depends_on = api.get("depends_on")
    assert isinstance(depends_on, dict), (
        f"`api` declares `depends_on: {depends_on!r}`. The list form waits for the "
        f"`{dependency}` container to start, not for it to accept connections. E0-02 "
        "requires the long form with a health condition."
    )

    declared = depends_on.get(dependency) or {}
    condition = declared.get("condition") if isinstance(declared, dict) else None
    assert condition == "service_healthy", (
        f"`api` waits on `{dependency}` with condition {condition!r}, not 'service_healthy'. "
        f"`wait_for_health.sh api` reaches `{dependency}` only through this condition, so "
        "without it the health gate reports green having checked one service."
    )


def test_services_inheriting_the_env_file_do_not_hold_the_superuser_credential(
    base_compose_path: Path,
    base_compose: dict[str, Any],
) -> None:
    """A container handed the whole of `.env` has the superuser pair taken back out.

    ADR 0009's second bound. `env_file:` is all-or-nothing — Compose has no way
    to hand a container part of a file — so a service that wants the
    configuration surface receives the superuser credential along with it and
    has to blank what it must not hold. `environment:` beats `env_file:` on
    every Compose version, and an *empty value* is what removes a variable;
    omitting the entry leaves whatever `env_file` already set, which is why the
    check below distinguishes an empty string from an absent key and from a
    pass-through.

    `db` is not exempted and needs no exemption: it declares no `env_file` at
    all, taking its credentials through explicit `${DB_SUPERUSER:?...}`
    interpolation instead. So the rule reaches every service that inherits the
    file, with nothing carved out of it by name. If `db` ever gains an
    `env_file`, this test fails, and that failure is a question worth answering
    rather than noise to silence.
    """
    assert base_compose, (
        f"{base_compose_path} does not exist or declares nothing. E0-02 ships the base "
        "Compose file at the repository root (SPEC §13)."
    )

    inheriting = {
        name: body for name, body in services_of(base_compose).items() if declares_env_file(body)
    }

    assert inheriting, (
        f"No service in {base_compose_path.name} declares `env_file`, so every service "
        "satisfies this test trivially and it has stopped checking anything. That may be "
        "correct — a service that enumerates its variables one by one inherits nothing to "
        "blank — but it is a change this test cannot interpret on its own. Work out which "
        "services now receive the superuser pair, and rewrite the rule below to match."
    )

    problems: list[str] = []
    for name, body in sorted(inheriting.items()):
        environment = service_environment(body)
        for variable in SUPERUSER_VARIABLES:
            if variable not in environment:
                problems.append(f"`{name}` inherits {variable} from .env and never blanks it")
            elif environment[variable] != "":
                problems.append(
                    f"`{name}` sets {variable} to {environment[variable]!r}, which supplies "
                    "a value rather than removing one"
                )

    assert not problems, "\n".join(
        [
            "A service is handed the database superuser credential (ADR 0009):",
            *problems,
            "",
            "`db:5432` is reachable from every service on this network and its pg_hba.conf "
            "accepts that role over scram, so holding the credential is a working route to "
            "a role that bypasses every grant, bypasses row-level security, and can run "
            "COPY ... FROM PROGRAM. Blank it in that service's `environment:` block the way "
            "`api` does: an empty value removes what `env_file` set, and omitting the entry "
            "does not.",
        ]
    )
