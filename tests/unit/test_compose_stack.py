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
    file entirely. No dynamic gate can see this. `docker compose up` merges
    `docker-compose.override.yml` automatically, so a developer's laptop only
    ever exercises the merged topology; the `docker` job now also brings the
    stack up on the base file alone, but that pass exists to catch a packaging
    regression — the override mounts the checkout over the installed wheel — and
    it inspects health, not published ports. So a `ports:` entry added to the
    base file publishes Postgres to the host of every non-development deployment
    and still breaks nothing anyone runs.

    (Until E0-03 this paragraph said CI never ran the base file alone. That was
    true when it was written and the base-file-only pass made it false. The
    assertion below is unaffected, which is the reason to correct the sentence
    rather than the test: what changed is that CI *starts* that topology, not
    that anything looks at its ports.)

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

Most tests below read the base file, because that is the one every deployment
runs. The three credential rules read both files, and the line between the two
groups is worth stating precisely, because the original reason for leaving the
override alone still holds everywhere else here.

That reason was: judging the override means modelling Compose's merge rules for
`env_file` and `environment`, and those are not rules to guess at without a
daemon. It applies to any *relative* question — does this override entry
overwrite that base entry, does this service still publish the port the base
file gave it — and none of those are asked of the override.

It does not apply to a question whose answer is the same under every merge. A
value written in either file is a value some container gets, so "no file may
write this credential" needs no merge model; nor does "this service must be
blanked somewhere", since a blank in the base file survives unless the override
re-supplies, and re-supplying is what the other two rules forbid outright.

Two reviewer passes shaped that. Pass 2 found nothing read the override at all
while `worker` and `beat` configuration had moved into it: one line in the
shared `x-development-source` anchor put the superuser password into all three
application containers with every test green, and the privilege test below could
never have caught it, being relative to `api` — a shared anchor reaches `api`
too, so the comparison is between a service and itself. Pass 3 found the same
hole twice more: the credential travelling inside *another key's value*
(`ALEMBIC_DATABASE_URL: postgresql://${DB_SUPERUSER}:...`), and a service that
inherits the whole of `.env` in the override, which the blanking rule was still
reading the base file to find.
"""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

# The credential ADR 0009 bounds. Named here rather than derived, because these
# two are the subject of the rule rather than an incidental pair of variables;
# a third would be a change to the ADR and should be a deliberate edit here too.
SUPERUSER_VARIABLES = ("DB_SUPERUSER", "DB_SUPERUSER_PASSWORD")

# The one service that must hold the superuser credential: it is the server that
# `initdb` creates the role in, and it takes it as `POSTGRES_USER` and
# `POSTGRES_PASSWORD` (ADR 0009, and `.env.example`'s note on the pair).
#
# This is the only exemption by name in this module, and it is here because it
# cannot be derived. Every route to deriving it — "the service whose image is
# postgres", "the service that declares POSTGRES_PASSWORD" — names the same
# thing one step further away and reads as a rule when it is a list of one. A
# second service needing the credential is an amendment to ADR 0009, and the
# right way for that to arrive is this constant changing in a reviewed diff.
CREDENTIAL_OWNING_SERVICE = "db"

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

# Freshness is a *comparison*, and the three lists below exist to say so. An
# earlier version had one list holding `stat` and `date`, and reviewer pass 2
# broke it in one line: `stat <schedule-file>` reads the file's modification
# time, matches, and compares it to nothing — it reports healthy on a schedule
# last written in March. Reading a clock is not checking a clock.
#
# So a check qualifies two ways, and both are structural rather than a spelling:
#
#   1. it uses a find predicate that carries its own now-relative threshold, or
#   2. it reads the file's modification time *and* asks what time it is now.
#
# **All three lists are the test's choice** and are meant to grow. What must not
# be weakened is the shape: a mechanism that reads one clock is not freshness.

# `-mmin -2` is "modified less than two minutes ago" — threshold and comparison
# in one token, relative to now. Bare `-newer` is deliberately absent: it
# compares one file against another file, which is a comparison but not
# necessarily against now, and `find -newer /tmp/static-marker` never goes stale.
NOW_RELATIVE_FILE_PREDICATES = ("-mmin", "-mtime", "-cmin", "-ctime", "-amin", "-atime")

# `-newermt` and its siblings sat in that list until reviewer pass 3, and they
# do not belong there: their reference is an argument, so the token alone says
# nothing about now. `find <dir> -newermt '2020-01-01'` passed all fourteen
# tests in this module — a check that reports healthy forever once the file has
# been written once, which is the exact property bare `-newer` was excluded for
# three lines above. The comment claimed now-relative and the code did not
# check it.
#
# They count now only when the reference is itself relative to now. `\S+` is
# enough to capture it: `'-2 minutes'` yields `'-2`, which is relative once the
# quote comes off, and `'2020-01-01'` yields a year.
TIMESTAMP_PREDICATE = re.compile(r"-newer[aBcm]?t\s+(?P<reference>\S+)", re.IGNORECASE)

# What makes a `-newerXt` reference now-relative. A leading `-` or `+` is an
# offset (`-2 minutes`); `now` and `ago` are GNU date's own words for it; `$(`
# and a backtick are a command substitution, which is how `date` gets called.
# **This list is the test's choice.** An absolute timestamp is not on it, and
# that is the point.
NOW_RELATIVE_REFERENCE_TOKENS = ("now", "ago", "$(", "`")

# Reading the file's own clock: `stat -c %Y`, `find -printf '%T@'`,
# `os.path.getmtime`, `os.stat(...).st_mtime`.
FILE_TIME_READERS = ("stat", "getmtime", "st_mtime", "%t@", "-printf")

# Reading the wall clock: `date +%s`, `time.time()`, `datetime.now()`, bash's
# `$SECONDS`. This is the half `stat <file>` is missing.
CLOCK_READERS = (
    "date",
    "time.time",
    "datetime.now",
    "utcnow",
    "$seconds",
    "epochseconds",
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


ComposeDocuments = tuple[tuple[Path, dict[str, Any]], ...]
ServiceBodies = dict[str, list[tuple[Path, dict[str, Any]]]]


def services_across(documents: ComposeDocuments) -> ServiceBodies:
    """Every service in either Compose file, keyed by name, bodies kept separate.

    Not merged, because merging is the thing this module refuses to model. What
    is collected is "everything both files say about the service called `worker`",
    which is enough to ask a question of the form "is this true somewhere" or
    "is this false anywhere" without deciding which file wins.
    """
    collected: ServiceBodies = {}
    for path, document in documents:
        for name, body in services_of(document).items():
            collected.setdefault(name, []).append((path, body))
    return collected


def test_services_inheriting_the_env_file_do_not_hold_the_superuser_credential(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """A container handed the whole of `.env` has the superuser pair taken back out.

    ADR 0009's second bound. `env_file:` is all-or-nothing — Compose has no way
    to hand a container part of a file — so a service that wants the
    configuration surface receives the superuser credential along with it and
    has to blank what it must not hold. `environment:` beats `env_file:` on
    every Compose version, and an *empty value* is what removes a variable;
    omitting the entry leaves whatever `env_file` already set.

    **Both files, keyed by service name**, since reviewer pass 3. This rule read
    the base file only, while its own docstring claimed it reached every service
    with nothing carved out by name — and the override was carved out by
    accident. A `pgweb` service added there with `env_file: - .env` and no
    `environment:` block passed the whole suite while holding the credential.

    Reading both files needs no merge model, and the shape of the question is
    what keeps it out. A service must be blanked *somewhere*: blanking in the
    base file survives into the merged configuration, so a service that gains an
    `env_file` in the override and is blanked in the base is safe, and this rule
    says so rather than demanding the blank be repeated. The other direction —
    an override that *re-supplies* what the base blanked — is not this rule's to
    catch and is covered absolutely by the two tests below, which forbid the
    value outright in either file.

    `db` is not exempted and needs no exemption *here*: it declares no
    `env_file` in either file, taking what it needs through explicit
    `${DB_SUPERUSER:?...}` interpolation, which is the subject of the next test
    and is where its one exemption lives. If `db` ever gains an `env_file`, this
    test fails, and that failure is a question worth answering rather than noise
    to silence.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing. Both Compose files ship, and a file "
            "that did not parse contributes no services — which would narrow this rule "
            "silently rather than fail it."
        )

    inheriting = {
        name: bodies
        for name, bodies in services_across(documents).items()
        if any(declares_env_file(body) for _, body in bodies)
    }

    assert inheriting, (
        "No service in either Compose file declares `env_file`, so every service satisfies "
        "this test trivially and it has stopped checking anything. That may be correct — a "
        "service that enumerates its variables one by one inherits nothing to blank — but it "
        "is a change this test cannot interpret on its own. Work out which services now "
        "receive the superuser pair, and rewrite the rule below to match."
    )

    problems: list[str] = []
    for name, bodies in sorted(inheriting.items()):
        inherited_in = sorted(path.name for path, body in bodies if declares_env_file(body))
        environments = [service_environment(body) for _, body in bodies]
        for variable in SUPERUSER_VARIABLES:
            if not any(environment.get(variable) == "" for environment in environments):
                problems.append(
                    f"`{name}` inherits the whole of .env (in {inherited_in}) and no Compose "
                    f"file blanks {variable}"
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


def test_no_compose_file_hands_a_container_the_superuser_credential(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
) -> None:
    """ADR 0009's bound, stated absolutely, across both files.

    The test above it says a service that inherits the whole of `.env` must blank
    the superuser pair. This one says something simpler and wider: no service in
    any Compose file may *write* those variables into a container with a value in
    them. The two are complementary — that one is about the credential arriving
    implicitly through `env_file`, this one about it being handed over on
    purpose — and neither implies the other.

    **Absolute, and that is the whole point.** The privilege test in this module
    compares `worker` and `beat` against `api`, which is right for privilege and
    useless here: the override's `x-development-source` anchor is merged into all
    three application services, so anything granted through it reaches `api` too
    and a relative rule compares a service with itself. Reviewer pass 2 measured
    it — adding `DB_SUPERUSER: ${DB_SUPERUSER}` to that anchor, which is the
    natural one-line edit for "let the worker run a migration", delivered the
    real password to three containers with the whole unit suite green.

    No merge model is needed for this, which is why it is the one question this
    module asks of the override at all. `environment:` beats `env_file:`, and the
    override's `environment:` beats the base file's, so a non-empty value written
    in either file is a value the container gets. The rule over-approximates in
    the safe direction only: it can flag a value that some other file would have
    blanked, and it cannot miss one that is delivered.

    Three states, and only one of them is safe. An empty string removes what
    `env_file` set. A value — literal, or `${DB_SUPERUSER}`, or
    `${DB_SUPERUSER:-}` — supplies one. A *bare* name with no value is the one
    that reads as harmless and is not: `- DB_SUPERUSER` in a list, or
    `DB_SUPERUSER:` in a mapping, tells Compose to pass the variable through from
    the host environment, which is exactly where the real credential lives.

    `db` needs no exemption and gets none. It delivers `POSTGRES_USER` and
    `POSTGRES_PASSWORD`, interpolating `${DB_SUPERUSER}` into them; the variable
    it reads is not the variable it sets, and this rule is about what lands
    inside the container. If a container ever does need the superuser — E0-04's
    migrations are the live candidate — that is an ADR 0009 conversation and a
    deliberate edit here, not a line that slips through in a shared anchor.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing. Both Compose files ship — the base "
            "file from E0-02 and the override alongside it — and a file that did not parse "
            "supplies no services, which would make the search below silent rather than "
            "clean."
        )

    assert services_of(override_compose), (
        f"{override_compose_path.name} declares no services, so this test is no longer "
        "reading the file the finding was about. `worker` and `beat` configuration lives "
        "there as of ee2d496; if it has moved again, point this test at wherever it went "
        "rather than letting it pass over an empty mapping."
    )

    problems: list[str] = []
    for path, document in documents:
        for name, body in sorted(services_of(document).items()):
            environment = service_environment(body)
            for variable in SUPERUSER_VARIABLES:
                if variable not in environment:
                    continue
                value = environment[variable]
                if value is None:
                    problems.append(
                        f"{path.name}: `{name}` passes {variable} through from the host "
                        "environment, which is where the real credential is"
                    )
                elif value != "":
                    problems.append(f"{path.name}: `{name}` sets {variable} to {value!r}")

    assert not problems, "\n".join(
        [
            "A Compose file hands the database superuser credential to a container " "(ADR 0009):",
            *problems,
            "",
            "`db:5432` is reachable from every service on this network and its pg_hba.conf "
            "accepts that role over scram, so a container holding this is a working route to "
            "a role that bypasses every grant, bypasses row-level security, and can run "
            "COPY ... FROM PROGRAM. Set it to an empty string, or do not name it. If a "
            "service genuinely needs the superuser, that is an amendment to ADR 0009 and an "
            "edit to this test, made on purpose and reviewed as such.",
        ]
    )


def test_only_the_database_service_interpolates_the_superuser_credential(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    override_compose_path: Path,
    override_compose: dict[str, Any],
    interpolated_variables_in: Callable[[Any], set[str]],
) -> None:
    """The credential does not reach a container under some other name either.

    The rule above asks whether `DB_SUPERUSER` is an environment *key*. That is
    only one of the ways the value travels, and reviewer pass 3 found the other
    one by writing the line E0-04 is actually going to want:

        ALEMBIC_DATABASE_URL: postgresql://${DB_SUPERUSER}:${DB_SUPERUSER_PASSWORD}@db:5432/${DB_NAME}

    on the `x-application` anchor. Three containers received the real superuser
    password, under a key no rule was looking at, with the suite green. ADR
    0009's bound is about the credential reaching an application container, not
    about the spelling of the variable it arrives in.

    So this reads *values* rather than keys, and it walks the whole service body
    rather than an enumerated list of the places a value can hide.
    `environment:`, `command:`, `build.args`, `labels:`, a `healthcheck` — an
    enumeration would be a list to keep in step with Compose's schema, and a
    list nobody re-reads is the failure `docs/MISTAKES.md` entry 1 is mostly
    made of. A recursive walk needs no maintenance and cannot omit a key that
    was added later.

    The walker is `interpolated_variables`, the same one that decides which
    variables `.env.example` must document, so the two cannot disagree about
    what counts as reading a variable — and it works off the parsed document, so
    a commented-out interpolation stops counting the moment it stops being one.
    That last part is right rather than a gap: a `#`-prefixed line in a YAML
    file is not configuration, which is the exact opposite of a `#`-prefixed
    line inside a `run:` block, where the text is a comment but the step still
    ships.

    `db` is exempt, by name, and it is the only exemption in this module — see
    `CREDENTIAL_OWNING_SERVICE` for why it cannot be derived.
    """
    documents = (
        (base_compose_path, base_compose),
        (override_compose_path, override_compose),
    )
    for path, document in documents:
        assert document, (
            f"{path} does not exist or declares nothing. A file that did not parse holds no "
            "interpolations, and a search that finds none reports every service clean."
        )

    bounded = set(SUPERUSER_VARIABLES)
    owner = services_of(base_compose).get(CREDENTIAL_OWNING_SERVICE) or {}
    assert bounded & interpolated_variables_in(owner), (
        f"The `{CREDENTIAL_OWNING_SERVICE}` service interpolates neither of "
        f"{list(SUPERUSER_VARIABLES)}, which is the one service that has to. Either the "
        "walker is looking at the wrong thing or it is finding nothing at all, and a rule "
        "that finds nothing calls every service clean. If the database has genuinely stopped "
        "taking its credentials this way — a secrets file, say — this test needs rewriting "
        "around whatever replaced it, not deleting."
    )

    problems: list[str] = []
    for path, document in documents:
        for name, body in sorted(services_of(document).items()):
            if name == CREDENTIAL_OWNING_SERVICE:
                continue
            reached = sorted(bounded & interpolated_variables_in(body))
            if reached:
                problems.append(f"{path.name}: `{name}` interpolates {reached}")

    assert not problems, "\n".join(
        [
            "A service other than the database reads the superuser credential (ADR 0009):",
            *problems,
            "",
            "It does not matter which key it lands in — a connection URL, a build argument, "
            "a label — the container holds the password either way, and `db:5432` is "
            "reachable from all of them over scram. That role bypasses every grant, bypasses "
            "row-level security, and can run COPY ... FROM PROGRAM. If this is the migration "
            "identity E0-04 needs, ADR 0009 has a table for who provisions what: amend it, "
            "then change `CREDENTIAL_OWNING_SERVICE` deliberately.",
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


def scheduled_file_paths(service: dict[str, Any]) -> set[str]:
    """Where this service's command says the beat schedule file is."""
    paths: set[str] = set()
    tokens = command_tokens(service)
    for index, token in enumerate(tokens):
        for flag in SCHEDULE_FLAGS:
            if token == flag and index + 1 < len(tokens):
                paths.add(tokens[index + 1])
            elif token.startswith(f"{flag}="):
                paths.add(token.split("=", 1)[1])
    return {path for path in paths if path and not path.startswith("-")}


def volume_targets(service: dict[str, Any]) -> set[str]:
    """The container-side path of everything this service mounts."""
    targets: set[str] = set()
    for entry in service.get("volumes") or []:
        if isinstance(entry, dict):
            target = entry.get("target")
            if isinstance(target, str):
                targets.add(target)
        elif isinstance(entry, str):
            parts = entry.split(":")
            if len(parts) >= 2:
                targets.add(parts[1])
    return {target for target in targets if target}


def schedule_anchors(service: dict[str, Any]) -> set[str]:
    """Strings a health check can name the schedule file by, and no wider.

    Two sources: the file the command names, and the container-side path of
    anything the service mounts — a schedule that survives `docker compose
    restart beat` (criterion 3) is on a volume, so the mount is where it lives.

    **Only the command's file path is widened, and only to its own directory.**
    Celery's `--schedule` names a shelve database, and the files on disk are that
    name plus a suffix, so a check written as `find <directory> -name
    'beat-schedule*'` is reading exactly the right thing and never contains the
    path as spelled. That is the whole of the widening.

    Reviewer pass 2 broke the earlier version, which widened *every* anchor to
    its parent: a volume at `/var/lib/celery` made `/var/lib` count as naming the
    schedule, and `pgrep … && stat /var/lib` passed a test whose subject is
    whether the schedule file is being written. A mount point is already a
    directory; widening it says the health check may name the directory above the
    one the service asked for, which is a claim about a path nobody declared.
    """
    anchors: set[str] = set()
    for path in scheduled_file_paths(service):
        anchors.add(path)
        directory = path.rsplit("/", 1)[0]
        if directory:
            anchors.add(directory)
    anchors |= volume_targets(service)
    return {anchor for anchor in anchors if "/" in anchor}


def now_relative_timestamp_predicates(command: str) -> list[str]:
    """`-newerXt` predicates in `command` whose reference is relative to now.

    One that names a fixed date is not freshness — it is "has this file ever
    been written", asked in a way that looks like freshness — so it is not
    returned, and a command whose only time-awareness is such a predicate fails
    the assertion below.
    """
    found: list[str] = []
    for match in TIMESTAMP_PREDICATE.finditer(command):
        reference = match.group("reference").strip("'\"").lower()
        relative = reference.startswith(("-", "+"))
        relative = relative or any(token in reference for token in NOW_RELATIVE_REFERENCE_TOKENS)
        if relative:
            found.append(match.group(0))
    return found


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
      - the command compares that file's age against now, which is what `test -f`
        fails, and what `stat <file>` fails too.

    That second one is narrower than it was, twice over, and both narrowings
    were bought by someone breaking it. Reviewer pass 2: it accepted any mention
    of `stat` or `date`, so `stat /var/lib/celery/beat-schedule` passed — it
    reads the file's clock, compares it to nothing, and reports healthy on a
    schedule last written in March. Reading a clock is not checking a clock.
    Reviewer pass 3: `find <dir> -newermt '2020-01-01'` passed, because
    `-newermt` was listed as a now-relative predicate when its reference is an
    argument that may be any date at all — the same "never goes stale" property
    bare `-newer` had been excluded for, admitted three lines below the comment
    explaining the exclusion.

    The rule now is a find predicate that carries its own now-relative threshold
    (`-mmin -2`), or a `-newerXt` whose *reference* is relative to now, or a
    file-time reader and a wall-clock reader together — see the lists at the top
    of this module.

    Neither assertion pins the command. The path is read out of what beat itself
    declares rather than written down here, so renaming the file or moving the
    volume needs no edit, and the vocabularies are named lists meant to be
    extended when a mechanism arrives that they do not describe.

    There is no denylist of process-existence commands and there does not need to
    be. `pgrep -f 'celery.*beat'` names no schedule file and reads no clock, so it
    fails both assertions on its own; a command that checks the process *and*
    then checks the schedule file passes, which is correct — belt and braces is
    not the defect.

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

    referenced = sorted(anchor for anchor in anchors if anchor in command)
    assert referenced, (
        f"`{BEAT_SERVICE}`'s health check never mentions its schedule file. It runs "
        f"`{command}`, while the schedule lives at one of {sorted(anchors)}. A check that "
        "does not look at the schedule file is a check on the process, and beat's failure "
        "mode is a live process with a dead scheduler — `test: ['CMD', 'true']` and "
        "`pgrep celery` both report healthy through exactly that. Naming a directory above "
        "the one the service declares does not count either: `/var/lib` is not the schedule "
        "file just because the schedule file is somewhere under it."
    )

    lowered = command.lower()
    predicates = sorted(token for token in NOW_RELATIVE_FILE_PREDICATES if token in lowered)
    predicates += now_relative_timestamp_predicates(lowered)
    file_clock = sorted(token for token in FILE_TIME_READERS if token in lowered)
    wall_clock = sorted(token for token in CLOCK_READERS if token in lowered)

    if file_clock and not wall_clock:
        diagnosis = (
            f"It reads the file's modification time ({file_clock}) and then asks nobody what "
            "time it is, so it cannot tell a schedule written a second ago from one written "
            "last Tuesday."
        )
    elif wall_clock and not file_clock:
        diagnosis = (
            f"It reads the wall clock ({wall_clock}) but never the file's modification time, "
            "so its answer does not depend on the schedule at all."
        )
    else:
        diagnosis = "It reads neither the file's modification time nor the wall clock."

    assert predicates or (file_clock and wall_clock), "\n".join(
        [
            f"`{BEAT_SERVICE}`'s health check reads {referenced} but never compares its age "
            f"to now. It runs `{command}`.",
            diagnosis,
            "",
            "The scope item is schedule-file *freshness*. The file a wedged beat leaves "
            "behind still exists and still has an mtime; only its age says the scheduler "
            "stopped. Use a find predicate that carries its own threshold "
            f"({list(NOW_RELATIVE_FILE_PREDICATES)}), or read both clocks and subtract. If "
            "the mechanism is real and simply not described by those lists, add it there and "
            "say so — do not drop this assertion back to 'mentions a clock'.",
        ]
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
