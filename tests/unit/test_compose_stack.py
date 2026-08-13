"""Properties of the Compose files that no running stack checks — tickets E0-02, E0-03.

Almost every acceptance criterion in E0-02 needs Docker: the stack reaching
healthy, `curl localhost:8000/healthz`, `down -v` then `up -d` twice, and the
API container's `id -u`. Those are the CI `docker` job's job, and the ticket's
definition of done says so plainly — "the health gate in CI is the test". E0-03
is the same shape: `up -d` healthy on three services, a `restart beat` that does
not double-schedule, and a worker that goes unhealthy when Redis stops all need
a daemon. None of them are restated here.

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

E0-03 adds `worker` and `beat`, and they fall into the same three kinds rather
than into a fourth:

  - Their health checks are declared *in the base file*, which is item 2 again.
    `wait_for_health.sh` fails a service that declares no health check, so the
    `docker` job covers the merged view — and a health check that lives only in
    the development override satisfies that gate while every other deployment
    runs a worker and a beat that report no health at all. Beat's check also has
    to *read the schedule file*, which is item 2 in its sharpest form: reviewer
    pass 1 on pull request #16 replaced that check with `true` and every gate
    stayed green, because a health gate can only ever exercise the direction
    where the answer is yes. A check nobody has seen say no is a check nobody
    has seen.
  - Neither takes privilege the `api` service does not, which is the E0-03
    security-review item. Nothing dynamic looks at it: a `privileged: true` or a
    `user: root` on the worker makes the stack come up exactly as before, and
    the containers concerned are the ones that will run E0-13's gateway over
    untrusted comment text.
  - Both run the API image rather than an image of their own, which the ticket
    asks for and which no gate can see: a second build of the same Dockerfile
    passes every check and then drifts.

The other half of the security-review item — that the broker is not exposed
outside the Compose network — needs nothing new. The host-port test above
covers every service in the base file, `redis` included, and covering it a
second time by name would be the weaker rule written twice.

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

# The two services E0-03 adds. Both run the API image and both are compared
# against `api`, so the service they are compared with is named once too.
API_SERVICE = "api"
BEAT_SERVICE = "beat"
JOB_SERVICES = ("worker", "beat")

# How beat says where its schedule file lives. Celery spells the flag
# `-s, --schedule`; the two names are Celery's, not this test's choice. A
# container-side volume path counts too, because a schedule file that survives
# `docker compose restart beat` (criterion 3) has to be on one.
SCHEDULE_FLAGS = ("-s", "--schedule")

# Ways of reading a modification time. **This list is the test's choice** and is
# meant to grow: it exists to separate a check that asks *when the schedule file
# was last written* from one that asks only whether it is there. If a freshness
# check arrives that reads mtime by some route not listed here, add the route —
# the assertion that must not be weakened is that the check is time-aware.
FRESHNESS_TOKENS = (
    "-newer",
    "-mmin",
    "-mtime",
    "-cmin",
    "-ctime",
    "stat",
    "mtime",
    "date",
    "time.time",
    "monotonic",
)

# Compose keys that give a container more than its image does. Each is a real
# route out of the container or up to root, and none of them changes whether the
# stack comes up, so a dynamic gate sees none of it. `user` is here because the
# API image already fixes a non-root user (E0-02 asserts uid != 0 on the running
# container) and a service-level `user:` overrides it.
PRIVILEGE_KEYS = (
    "privileged",
    "user",
    "cap_add",
    "security_opt",
    "devices",
    "device_cgroup_rules",
    "sysctls",
    "group_add",
    "pid",
    "ipc",
    "userns_mode",
    "network_mode",
)

# Host paths whose contents are, in practice, the host. **This list is the
# test's choice**, not the ticket's: the ticket says "no extra privilege beyond
# the API image", and a bind mount is the everyday way one arrives. The docker
# socket is root on the host; /proc and /sys are the kernel; /etc holds the
# shadow file. A worker that mounts one of these while `api` does not has more
# than `api` has, whatever its `user:` says.
SENSITIVE_BIND_SOURCES = frozenset(
    {"/", "/dev", "/etc", "/proc", "/run/docker.sock", "/sys", "/var/run/docker.sock"}
)


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
    `redis`" — and the scope list, which names an authenticating `psql` probe
    for `db` and `redis-cli ping` for `redis`. The command is not asserted; only
    that the service can report whether it works. (This docstring said
    `pg_isready` until E0-03. The ticket's scope list said so too, and both were
    corrected when the probe changed: `pg_isready` never authenticates, so it
    reported healthy against a volume initialised under different credentials.)

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


# ---------------------------------------------------------------------------
# The job runtime: `worker` and `beat` — ticket E0-03.
# ---------------------------------------------------------------------------


def normalised_build(declared: Any) -> Any:
    """A build specification in a form two services can be compared by.

    Compose accepts a bare context string and a mapping, and means the same
    thing by `build: ./backend` and `build: {context: ./backend}`. Comparing the
    raw values would call those two different, which would fail a service that
    is doing exactly what the ticket asks.
    """
    if isinstance(declared, str):
        return (("context", declared),)
    if isinstance(declared, dict):
        return tuple(sorted((str(key), repr(value)) for key, value in declared.items()))
    return declared


def image_identity(service: dict[str, Any]) -> tuple[str, Any] | None:
    """What image this service runs, as something comparable between services.

    An explicit `image:` wins, because that is the tag Compose runs and the one
    a `build:` alongside it writes to. Failing that, the build specification
    stands in: two services built from one context and one Dockerfile cannot
    drift in content, which is what "sharing the API image" is protecting.

    `None` means the service declares neither, which Compose rejects anyway —
    it is returned rather than raised so the test reports it as a failed
    comparison naming the service.
    """
    image = service.get("image")
    if isinstance(image, str) and image:
        return ("image", image)
    build = service.get("build")
    if build:
        return ("build", normalised_build(build))
    return None


def privilege_declarations(service: dict[str, Any]) -> dict[str, Any]:
    """The privilege-granting keys this service declares, normalised for comparison.

    Falsy values are dropped: `privileged: false` grants nothing, and an empty
    `cap_add` is not a capability. Lists and mappings become frozensets so that
    reordering `security_opt` is not a difference and so a subset test means
    what it says.
    """
    declared: dict[str, Any] = {}
    for key in PRIVILEGE_KEYS:
        value = service.get(key)
        if not value:
            continue
        if isinstance(value, list):
            declared[key] = frozenset(str(item) for item in value)
        elif isinstance(value, dict):
            declared[key] = frozenset(f"{name}={item}" for name, item in value.items())
        else:
            declared[key] = value
    return declared


def dropped_capabilities(service: dict[str, Any]) -> frozenset[str]:
    """`cap_drop`, which runs the other way: more here is less privilege."""
    declared = service.get("cap_drop") or []
    if isinstance(declared, list):
        return frozenset(str(item).upper() for item in declared)
    return frozenset()


def bind_sources(service: dict[str, Any]) -> set[str]:
    """Host paths this service bind-mounts, in either of Compose's spellings.

    A named volume is not a bind mount and contributes nothing: it is a Docker
    volume, not a piece of the host filesystem, and `beat` may well want one for
    its schedule file. Only a source that starts with `/`, `.` or `~` names a
    host path.
    """
    sources: set[str] = set()
    for entry in service.get("volumes") or []:
        source: Any = None
        if isinstance(entry, dict):
            if entry.get("type") in (None, "bind"):
                source = entry.get("source")
        elif isinstance(entry, str):
            parts = entry.split(":")
            if len(parts) >= 2:
                source = parts[0]
        if isinstance(source, str) and source.startswith(("/", ".", "~")):
            sources.add(source.rstrip("/") or "/")
    return sources


@pytest.mark.parametrize("service_name", JOB_SERVICES)
def test_job_service_runs_the_api_image_rather_than_one_of_its_own(
    service_name: str,
    base_compose_path: Path,
    base_compose: dict[str, Any],
) -> None:
    """`worker` and `beat` share the API image, as E0-03's scope list requires.

    Two images built from two Dockerfiles run the same code only until one of
    them changes. Every gate stays green through that: each container starts,
    each reports healthy, and the worker executing a task against a dependency
    the API does not have is a runtime failure with no build-time signal. The
    ticket asks for one image for that reason, and this is the only place it can
    be checked — `docker compose build` is happy to build two.

    The comparison is by identity rather than by spelling. A shared `image:`
    tag and an identical `build:` both mean one Dockerfile and one context, and
    E0-03 does not choose between them.
    """
    assert base_compose, (
        f"{base_compose_path} does not exist or declares nothing. E0-02 ships the base "
        "Compose file at the repository root (SPEC §13)."
    )

    services = services_of(base_compose)
    api = services.get(API_SERVICE)
    assert api is not None, (
        f"docker-compose.yml declares no `{API_SERVICE}` service, so there is no API image "
        "for this test to compare against and the comparison below would be between two "
        "absences."
    )
    api_identity = image_identity(api)
    assert api_identity is not None, (
        f"`{API_SERVICE}` declares neither `image:` nor `build:`, so what image the worker "
        "and beat services are meant to share is undefined."
    )

    service = services.get(service_name)
    assert service is not None, (
        f"docker-compose.yml declares no `{service_name}` service. E0-03 adds `worker` and "
        "`beat` (SPEC §7.2 — Celery worker and Celery beat)."
    )

    assert image_identity(service) == api_identity, (
        f"`{service_name}` runs {image_identity(service)!r} while `{API_SERVICE}` runs "
        f"{api_identity!r}. E0-03 has the job services share the API image: the worker runs "
        "the same application code the API does, and a second image is a second thing to "
        "keep in step, with nothing to notice when it slips."
    )


@pytest.mark.parametrize("service_name", JOB_SERVICES)
def test_job_service_declares_its_health_check_in_the_base_file(
    service_name: str,
    base_compose_path: Path,
    base_compose: dict[str, Any],
) -> None:
    """`worker` and `beat` each report whether they work, in every deployment.

    E0-03 criterion 1 is that `up -d` reaches healthy on `api`, `worker` and
    `beat`, and the scope list asks for a meaningful check on each: `celery
    inspect ping` for the worker, and schedule-file freshness for beat.

    Whether the check is *meaningful* is decided elsewhere, in two places and
    not in this one. Beat's is held statically by
    `test_the_beat_health_check_reads_the_schedule_file` below, which reviewer
    pass 1 required after `test: ["CMD", "true"]` passed every gate. The
    worker's is held by the dynamic criterion that needs a daemon: it goes
    unhealthy when Redis is stopped. What is decided here is narrower than
    either and is the part no daemon sees. `wait_for_health.sh` already fails a
    service that declares no health check, so the `docker` job covers the
    *merged* view; a
    check declared in `docker-compose.override.yml` would satisfy that gate and
    be absent from every deployment that runs the base file alone.

    The disabled forms are asserted against rather than merely presence, because
    `disable: true` and `test: ["NONE"]` are both a declared health check that
    reports nothing — and `wait_for_health.sh` reads the second one as
    `no-healthcheck` and the first as a service that never leaves `starting`.
    """
    assert base_compose, (
        f"{base_compose_path} does not exist or declares nothing. E0-02 ships the base "
        "Compose file at the repository root (SPEC §13)."
    )

    service = services_of(base_compose).get(service_name)
    assert service is not None, (
        f"docker-compose.yml declares no `{service_name}` service. E0-03 adds `worker` and "
        "`beat` (SPEC §7.2)."
    )

    healthcheck = service.get("healthcheck")
    assert isinstance(healthcheck, dict) and healthcheck, (
        f"`{service_name}` declares no healthcheck in the base Compose file. E0-03 requires "
        "one on each so that `wait_for_health.sh api worker beat` means something, and it "
        "belongs here rather than in the development override: the override is not read by "
        "any other deployment, and a container that reports no health is one nothing "
        "notices has stopped working."
    )

    disabled = bool(healthcheck.get("disable"))
    test_command = healthcheck.get("test")
    if isinstance(test_command, list):
        disabled = disabled or [str(item).upper() for item in test_command] == ["NONE"]
    elif isinstance(test_command, str):
        disabled = disabled or test_command.strip().upper() == "NONE"

    assert not disabled, (
        f"`{service_name}` declares a health check that is switched off "
        f"({healthcheck!r}). A disabled check is not a check: the container reports no "
        "health at all, which is the state E0-03's first criterion exists to rule out."
    )


def command_tokens(service: dict[str, Any]) -> list[str]:
    """Every whitespace-separated word of a service's entrypoint and command.

    Both keys, and both of Compose's spellings for each, flattened into one list
    of words. `command: celery -A app.jobs.celery_app beat -s /x` and
    `command: ["celery", "-A", "app.jobs.celery_app", "beat", "-s", "/x"]` are
    the same instruction, and a list entry may itself hold several words when a
    service is started through `sh -c`.
    """
    words: list[str] = []
    for key in ("entrypoint", "command"):
        declared = service.get(key)
        if isinstance(declared, str):
            words.extend(declared.split())
        elif isinstance(declared, list):
            for item in declared:
                words.extend(str(item).split())
    return words


def schedule_anchors(service: dict[str, Any]) -> set[str]:
    """Paths at which this service says its beat schedule file lives.

    Two sources, because a service may name the file on the command line or
    place it by mounting the directory it goes in — and it usually does both.
    Anything a health check can honestly be anchored to has to be declared
    somewhere the service itself declares it, or the check and the file are two
    independent guesses about a path.
    """
    anchors: set[str] = set()
    tokens = command_tokens(service)
    for index, token in enumerate(tokens):
        for flag in SCHEDULE_FLAGS:
            if token == flag and index + 1 < len(tokens):
                anchors.add(tokens[index + 1])
            elif token.startswith(f"{flag}="):
                anchors.add(token.split("=", 1)[1])

    for entry in service.get("volumes") or []:
        if isinstance(entry, dict):
            target = entry.get("target")
            if isinstance(target, str):
                anchors.add(target)
        elif isinstance(entry, str):
            parts = entry.split(":")
            if len(parts) >= 2:
                anchors.add(parts[1])

    return {anchor for anchor in anchors if anchor and not anchor.startswith("-")}


def reference_candidates(anchor: str) -> set[str]:
    """The ways a health check might legitimately name `anchor`.

    The path itself, and the directory holding it. Celery's `--schedule` names a
    file while the shelve database it opens may be that name plus a suffix, so a
    check written with `find <directory> -name 'celerybeat-schedule*'` is
    reading exactly the right thing and never contains the file path as written.
    Accepting the parent keeps this test from failing a correct check on a
    detail of how the path was spelled.
    """
    candidates = {anchor}
    parent = anchor.rsplit("/", 1)[0]
    if parent and parent != anchor:
        candidates.add(parent)
    return candidates


def healthcheck_command(healthcheck: dict[str, Any]) -> str:
    """A service's health check as one string, in either of Compose's spellings."""
    declared = healthcheck.get("test")
    if isinstance(declared, str):
        return declared
    if isinstance(declared, list):
        return " ".join(str(item) for item in declared)
    return ""


def test_the_beat_health_check_reads_the_schedule_file(
    base_compose_path: Path,
    base_compose: dict[str, Any],
) -> None:
    """E0-03 scope: beat's liveness check is "based on schedule-file freshness".

    The scope list says what the check must not be — "rather than mere process
    existence" — because beat's failure mode is that the process is alive and
    the scheduler inside it is not. A check that reports on the process reports
    healthy through exactly the outage it exists to catch, and every gate in the
    pipeline agrees with it: the container is up, `wait_for_health.sh` passes,
    and no scheduled job has been missed yet because none exists to miss.

    Reviewer pass 1 on pull request #16 measured this. Replacing beat's health
    check with `test: ["CMD", "true"]` left every gate green, because presence
    and not-disabled were all that was asserted, and the dynamic checks only
    ever exercise the direction where the answer is yes.

    Two assertions, and the split is the point:

      - the command names the schedule file, which is what a process check, a
        pidfile check and `true` all fail; and
      - the command does something time-aware with it, which is what `test -f`
        fails — a file that exists is not a file that is being written to.

    Neither pins the command. The path is read out of what beat itself declares
    rather than written down here, so renaming the file or moving the volume
    needs no edit; the time-aware vocabulary is a named list that is meant to be
    extended rather than argued with.

    What is still not asserted here, and cannot be: whether the freshness window
    is the right size. A check with a two-hour tolerance passes both assertions
    below and reports healthy through two hours of a wedged scheduler. That is
    the dynamic side's to hold, by stopping the scheduler and watching the
    container go unhealthy — and by MISTAKES entry 7's rule, watching for longer
    than `retries x interval` before believing the answer.
    """
    assert base_compose, (
        f"{base_compose_path} does not exist or declares nothing. E0-02 ships the base "
        "Compose file at the repository root (SPEC §13)."
    )

    beat = services_of(base_compose).get(BEAT_SERVICE)
    assert beat is not None, (
        f"docker-compose.yml declares no `{BEAT_SERVICE}` service. E0-03 adds it (SPEC §7.2 "
        "— Celery beat: window open/close, Monday reports, retention)."
    )

    healthcheck = beat.get("healthcheck")
    assert isinstance(healthcheck, dict) and healthcheck, (
        f"`{BEAT_SERVICE}` declares no healthcheck, so there is no command for this test to "
        "read and its silence below would mean nothing."
    )
    command = healthcheck_command(healthcheck)
    assert command.strip(), (
        f"`{BEAT_SERVICE}`'s healthcheck declares no `test:` command ({healthcheck!r}). An "
        "empty command is not a check, and it would satisfy every search below by giving "
        "them nothing to look at."
    )

    anchors = schedule_anchors(beat)
    assert anchors, (
        f"`{BEAT_SERVICE}` says nowhere what its schedule file is: its command passes no "
        f"{' or '.join(SCHEDULE_FLAGS)} and it mounts no volume. A freshness check needs a "
        "file at a known path, and criterion 3 needs that file to survive `docker compose "
        "restart beat`, so both wants the same thing — name the schedule file explicitly "
        "and put it somewhere that persists."
    )

    referenced = sorted(
        anchor
        for anchor in anchors
        if any(candidate in command for candidate in reference_candidates(anchor))
    )
    assert referenced, (
        f"`{BEAT_SERVICE}`'s health check never mentions its schedule file. It runs "
        f"`{command}`, while the schedule lives at one of {sorted(anchors)}. A check that "
        "does not look at the schedule file is a check on the process, and beat's failure "
        "mode is a live process with a dead scheduler — `test: ['CMD', 'true']` and "
        "`pgrep celery` both report healthy through exactly that."
    )

    time_aware = sorted(token for token in FRESHNESS_TOKENS if token in command.lower())
    assert time_aware, (
        f"`{BEAT_SERVICE}`'s health check reads {referenced} but never asks when it was "
        f"last written. It runs `{command}`. The scope item is schedule-file *freshness*: "
        "the file a wedged beat leaves behind still exists, so existence reports healthy "
        "forever. Compare its modification time against now. If the mechanism used is not "
        f"in {list(FRESHNESS_TOKENS)}, add it to that list — it is this test's choice and "
        "is meant to grow — rather than dropping the assertion to existence."
    )


@pytest.mark.parametrize("service_name", JOB_SERVICES)
def test_job_service_takes_no_privilege_the_api_service_does_not(
    service_name: str,
    base_compose_path: Path,
    base_compose: dict[str, Any],
) -> None:
    """E0-03's security review: "no extra privilege beyond the API image".

    Sharing the image settles what is *inside* the container. It settles nothing
    about what Compose grants around it, and that is where privilege is actually
    handed out: `privileged: true`, a `user: root` that overrides the image's
    non-root user, an added capability, a relaxed seccomp profile, the host PID
    namespace, or the docker socket mounted in. Each of those makes the stack
    come up exactly as it did before, so criterion 1, the health gate and the
    round-trip test all stay green — this is `docs/MISTAKES.md` entry 2, where
    the guard is the thing with nothing asserting it.

    It is a real risk rather than a theoretical one on these two services
    specifically. The worker is where the beat schedule file gets written and
    where a permissions problem is met, and `user: root` is the first thing that
    makes such a problem go away. It is also the container that will run E0-13's
    AI gateway over untrusted comment text.

    Asserted as a comparison against `api` rather than as a fixed list of
    forbidden keys, so that a privilege the whole stack legitimately gains later
    does not have to be granted twice in two places — and so that the rule
    cannot be satisfied by granting it to `api` quietly, since `api` is the
    service E0-02 already checks the uid of on the running container.
    """
    assert base_compose, (
        f"{base_compose_path} does not exist or declares nothing. E0-02 ships the base "
        "Compose file at the repository root (SPEC §13)."
    )

    services = services_of(base_compose)
    api = services.get(API_SERVICE)
    assert api is not None, (
        f"docker-compose.yml declares no `{API_SERVICE}` service, so there is nothing to "
        "compare privilege against and this test would compare two empty sets."
    )
    service = services.get(service_name)
    assert service is not None, (
        f"docker-compose.yml declares no `{service_name}` service. E0-03 adds `worker` and "
        "`beat` (SPEC §7.2)."
    )

    api_grants = privilege_declarations(api)
    job_grants = privilege_declarations(service)

    problems: list[str] = []
    for key, value in sorted(job_grants.items()):
        allowed = api_grants.get(key)
        if isinstance(value, frozenset) and isinstance(allowed, frozenset):
            extra = sorted(value - allowed)
            if extra:
                problems.append(f"`{key}` adds {extra}, which `api` does not have")
        elif value != allowed:
            problems.append(f"`{key}` is {value!r}; `api` declares {allowed!r}")

    missing_drops = dropped_capabilities(api) - dropped_capabilities(service)
    if missing_drops:
        problems.append(
            f"`cap_drop` keeps {sorted(missing_drops)}, which `api` drops — dropping fewer "
            "capabilities is holding more"
        )

    reachable = (bind_sources(service) - bind_sources(api)) & SENSITIVE_BIND_SOURCES
    if reachable:
        problems.append(f"bind-mounts {sorted(reachable)} from the host, which `api` does not")

    assert not problems, "\n".join(
        [
            f"`{service_name}` is granted more than `{API_SERVICE}` is:",
            *problems,
            "",
            "E0-03's security review is that the job services carry no extra privilege "
            "beyond the API image. Nothing dynamic checks this: the stack comes up healthy "
            "either way. If the grant is genuinely needed, say why in the pull request and "
            "change this test deliberately — do not add it to `api` to make the comparison "
            "pass, because that widens the blast radius rather than narrowing it.",
        ]
    )
